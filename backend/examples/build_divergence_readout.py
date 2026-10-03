#!/usr/bin/env python3
"""Build the "why this token and not that one" payload for the viewer.

Two analysis outputs already exist per model, and between them they answer the
question the page currently cannot answer:

  analyse_divergence_logits.py -> per-layer, per-arm top-k readout taken AT the
      divergence step (the two candidate lists that actually raced).
  analyse_common_prefix.py     -> the top1-top2 margin at every shared prefix
      step, i.e. how close the model was to flipping before it flipped.

Neither was shipped. The page showed the two emitted tokens as bare labels, which
is an answer to "what changed" and not to "why".

Model attribution is by evidence, not by filename. Both models reuse the same six
problem ids (1983_I_1 .. 1988_I_1), so an id cannot tell them apart -- and a
mismatch here is exactly the "0.6B view citing 1.7B numbers" failure already paid
for once. Every problem is matched on (divergence step index, control token id,
steered token id) against the pair bundle that will be displayed next to it, and
the build fails unless all six match. Files that are off by dtype or strength
land at 0-3/6, so the gate has measured discriminative power rather than assumed
any.

Text is deliberately not shipped: the stored `text` fields in these files predate
the vocab fix that added `added_tokens`, so they still render token 151667 as the
placeholder "<151667>". The page already loads the real vocab and resolves ids
itself, so ids travel and the page owns the wording.
"""

import json
import os
import sys

import numpy as np

# backend/examples/ -> backend/ -> repo root
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LATENT = os.path.join(ROOT, "frontend", "public", "latent")
ANALYSIS = os.path.join(ROOT, ".cache", "analysis")

# model dir -> (divergence_logits, common_prefix). Still declared here so the
# build is reproducible from a clean checkout; the gate below is what decides
# whether a pairing is actually correct.
SOURCES = {
    "data": ("divergence_logits_v2.json", "common_prefix.json"),
    "data06": ("divergence_logits_0p6b.json", "common_prefix_0p6b.json"),
}

TOPK = 8
LAYERS = ["4", "12", "20", "26", "28"]


def r4(x):
    return round(float(x), 4)


def pair_truth(model_dir):
    """(divergence step, control token id, steered token id) per problem,
    read from the pair bundle the page will actually display."""
    meta = json.load(open(os.path.join(LATENT, model_dir, "pairs", "pairs.json")))
    out = {}
    for p in meta["pairs"]:
        base = os.path.join(LATENT, model_dir, "pairs", "pc_%s" % p["id"])
        cid = np.fromfile(base + "_control_ids.bin", dtype=np.int32)
        sid = np.fromfile(base + "_steered_ids.bin", dtype=np.int32)
        k = p["n_common_prefix"]
        if not (k < len(cid) and k < len(sid)):
            raise SystemExit("%s: %s has no token at step %d" % (model_dir, p["id"], k))
        out[p["id"]] = (int(k), int(cid[k]), int(sid[k]))
    return out


def gate(model_dir, div_path, pre_path, truth):
    """Every problem must line up on step index and both token ids. A partial
    match is the dangerous case -- some rows right, some from another run."""
    div = json.load(open(div_path))
    pre = json.load(open(pre_path))
    div_by = {q["id"]: q for q in div["problems"]}
    pre_by = {q["id"]: q for q in pre["problems"]}
    hits = []
    for pid, (k, c, s) in sorted(truth.items()):
        q = div_by.get(pid)
        w = pre_by.get(pid)
        ok_d = (q is not None and q["step_index"] == k
                and q["control_token"]["id"] == c and q["steered_token"]["id"] == s)
        row = w["rows"][w["k"]] if (w is not None and w["k"] < len(w["rows"])) else {}
        ok_p = (w is not None and w["k"] == k and row.get("token") == c)
        hits.append(ok_d and ok_p)
    n = sum(hits)
    if n != len(truth):
        bad = [pid for pid, ok in zip(sorted(truth), hits) if not ok]
        raise SystemExit(
            "alignment gate FAILED for %s: %d/%d matched (mismatched: %s)\n"
            "  %s\n  %s\nThese are different runs; refusing to ship one model's "
            "numbers under another's label." % (model_dir, n, len(truth), ", ".join(bad),
                                                 os.path.basename(div_path),
                                                 os.path.basename(pre_path)))
    return div, pre, n


def build(model_dir, div_name, pre_name):
    truth = pair_truth(model_dir)
    div, pre, n = gate(model_dir,
                       os.path.join(ANALYSIS, div_name),
                       os.path.join(ANALYSIS, pre_name),
                       truth)
    pre_by = {q["id"]: q for q in pre["problems"]}

    problems = {}
    for q in div["problems"]:
        pid = q["id"]
        k = q["step_index"]
        w = pre_by[pid]

        # Margin per shared step. Only steps the two arms actually share: past
        # the divergence each stream is its own thing and a two-arm margin stops
        # meaning anything.
        margin = []
        for r in w["rows"]:
            margin.append({
                "t": int(r["t"]),
                "c": r4(r["margin_control"]),
                "s": r4(r["margin_steered"]),
                "f": r4(r["distance_to_flip"]),
                "d": bool(r["is_divergence_step"]),
            })

        layers = {}
        for L in LAYERS:
            pl = q["per_layer"].get(L)
            if not pl:
                continue
            c, s = pl["control"], pl["steered"]
            layers[L] = {
                "c": [{"i": int(t["id"]), "g": r4(t["logit"])} for t in c["top"][:TOPK]],
                "s": [{"i": int(t["id"]), "g": r4(t["logit"])} for t in s["top"][:TOPK]],
                # how far this layer's readout is from the final one. Shallow
                # layers answer a different question entirely and the page has to
                # be able to say so instead of showing them as if they agreed.
                "kl": r4(c["kl_to_final_lens"]),
                "gc": r4(c["logit_chosen"]),
                "gs": r4(s["logit_chosen"]),
            }

        sm = w["summary"]
        problems[pid] = {
            "k": k,
            "c_id": q["control_token"]["id"],
            "s_id": q["steered_token"]["id"],
            "tail": q["common_tail"],
            "layers": layers,
            "margin": margin,
            "sum": {
                "m_c_med": r4(sm["margin_control_median"]),
                "m_c_min": r4(sm["margin_control_min"]),
                "m_c_last": r4(sm["margin_control_last"]),
                "m_s_med": r4(sm["margin_steered_median"]),
                "dlg_med": r4(sm["dlogit_prefix_median_abs"]),
                "dlg_at": r4(sm["dlogit_at_divergence"]),
                "dn_med": r4(sm["delta_norm_prefix_median"]),
                "dn_at": r4(sm["delta_norm_at_divergence"]),
                "flip_at": r4(sm["distance_to_flip_at_divergence"]),
            },
            "pct": r4(div["aggregate"]["direction_null_won_percentiles"].get(pid, 0.0)),
        }

    agg = div["aggregate"]
    # 每题用多少个同范数随机方向。页面上那句「同范数的 N 个随机方向里，
    # 有 X 的比例能扳出同样的词」原来把 N **写死成 128**。
    # 它可以推（总数 ÷ 题数），但「推出来的数」与「写死的那个数」
    # 之间没有任何绑定关系 —— 换一批数据，页面还印 128。
    # ⇒ 做成字段，页面读字段；除不尽就拒绝出这份产物。
    c4_hits = int(agg["C4_random_hits_informative"])
    c4_total = int(agg["C4_random_total_informative"])
    if n <= 0 or c4_total % n != 0:
        raise SystemExit(
            "%s: C4_random_total_informative=%d 除以题数 %d 除不尽 —— "
            "「每题 N 个随机方向」没有整数答案，页面不该印一个整数"
            % (model_dir, c4_total, n))
    c4_dirs_per_problem = c4_total // n
    if not (0 <= c4_hits <= c4_total):
        raise SystemExit("%s: C4 命中 %d 越界（总数 %d）"
                         % (model_dir, c4_hits, c4_total))
    out = {
        "schema": "steer3d.divergence_readout/1",
        "source": ["backend/examples/analyse_divergence_logits.py",
                   "backend/examples/analyse_common_prefix.py"],
        "note": ("Top-k logit-lens readout at the divergence step, both arms, "
                 "plus the top1-top2 margin at every shared step. `i` is a vocab "
                 "id; the page resolves the text from its own vocab."),
        "alignment_gate": "%d/%d problems matched on step index and both token ids" % (n, len(truth)),
        "inject_layer": div["inject_layer"],
        "layers": LAYERS,
        "final_layer": 28,
        "c4_random_hits": "%d/%d" % (c4_hits, c4_total),
        "c4_random_hits_n": c4_hits,
        "c4_random_hits_denom": c4_total,
        "c4_random_dirs_per_problem": c4_dirs_per_problem,
        "lens_argmax_offsets": agg["lens_argmax_offsets"],
        "problems": problems,
    }
    dest = os.path.join(LATENT, model_dir, "divergence_readout.json")
    with open(dest, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("%-7s %d problems  %6.1f KB  gate=%s" % (
        model_dir, len(problems), os.path.getsize(dest) / 1024.0, out["alignment_gate"]))


if __name__ == "__main__":
    for md, (dv, pr) in sorted(SOURCES.items()):
        build(md, dv, pr)
    print("ok")
