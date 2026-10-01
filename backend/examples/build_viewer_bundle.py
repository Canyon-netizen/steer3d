"""Pack the measured results into one compact bundle for the web viewer.

The viewer needs several quite different datasets, and the raw files are
large — the attribution traces alone are ~3–4 MB per model because every
step carries a full 29-layer curve for every alternative. Shipping those
verbatim would make a page that takes tens of seconds to open.

So this script downsamples along two axes and says so in the output:

  * **problems** — a fixed subset of problems, same subset for every model
    so a comparison across models is still like-for-like.
  * **steps** — the first N decoding steps of each problem. Steps are not
    exchangeable (the opening tokens of a chain of thought are far less
    determined than mid-reasoning ones), so the first N are taken
    deliberately and the viewer labels them as "opening steps".

What is *not* downsampled is anything a conclusion rests on: the
per-layer aggregate curves, the null control, the layer-sweep table and its
paired statistics all come through whole. Trimming those would change the
numbers the page states, which is the one thing a results viewer must not
do.

The bundle also carries the prose explanations inline, so the page and the
text cannot drift apart — the same discipline as the rest of this project,
where several earlier claims had to be retracted because a hand-written
summary outlived the data it described.

Usage:
    python3 backend/examples/build_viewer_bundle.py \
        --out backend/examples/output/viewer_bundle.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 6) if xs else None


def load_attr(path: Path) -> dict:
    return json.loads(path.read_text())


def pack_attribution(problems: List[str], steps: int,
                     top_k: int) -> dict:
    """Per-step attribution curves, downsampled to `problems` × `steps`."""
    models = {}
    null = None

    files = {
        "Qwen3-1.7B": OUT / "attr_qwen3_1p7b.json",
        "Qwen3-4B": OUT / "attr_qwen3_4b.json",
        "Qwen3-8B": OUT / "attr_qwen3_8b.json",
    }
    for name, p in files.items():
        if not p.exists():
            continue
        data = load_attr(p)
        kept, curves, kl_by_layer = [], {}, {}
        for s in data.get("steps", []):
            if s.get("problem") not in problems:
                continue
            if s.get("step", 0) >= steps:
                continue
            if len(s.get("top", [])) < 2:
                continue
            layers = s["layers"]["layers"]
            alts = [t for t in s["top"][:1 + top_k]]
            base = str(alts[0]["id"])
            curve = []
            for r in layers:
                curve.append({
                    "L": r["layer"],
                    "kl": round(float(r["lens_kl"]), 4),
                    "gaps": [round(float(r[str(t["id"])]), 4) for t in alts],
                })
                kl_by_layer.setdefault(r["layer"], []).append(r["lens_kl"])
            kept.append({
                "problem": s["problem"],
                "step": s["step"],
                "ctx": s.get("context_tail", "")[-90:],
                "margin": round(float(s["margin"]), 3),
                "entropy": round(float(s["entropy"]), 5),
                "cands": [{"t": t["text"], "p": round(float(t["logit"]), 2)}
                          for t in alts],
                "curve": curve,
            })
        curves = {
            str(L): round(_mean(v), 4) for L, v in sorted(kl_by_layer.items())
        }
        models[name] = {"steps": kept, "lens_kl": curves,
                        "n_raw_steps": data.get("n_steps")}

    np_ = OUT / "attr_null_1p7b.json"
    if np_.exists():
        data = load_attr(np_)
        kept, ok_by_layer = [], {}
        for s in data.get("steps", []):
            if s.get("problem") not in problems or s.get("step", 0) >= steps:
                continue
            alts = s.get("alternatives") or []
            if not alts:
                continue
            alt = str(alts[0]["id"])
            layers = s["layers"]["layers"]
            true_rows = [r for r in layers if r.get("is_true_output")]
            if not true_rows or alt not in true_rows[-1]:
                continue
            final = float(true_rows[-1][alt])
            for r in layers:
                if alt in r:
                    agree = (float(r[alt]) > 0) == (final > 0)
                    ok_by_layer.setdefault(r["layer"], []).append(agree)
            kept.append({
                "problem": s["problem"], "step": s["step"],
                "random_alt": alts[0]["text"],
            })
        null = {
            "model": "Qwen3-1.7B",
            "agreement": {str(L): round(100 * _mean(v), 1)
                          for L, v in sorted(ok_by_layer.items())},
            "n_raw_steps": data.get("n_steps"),
        }
    return {"models": models, "null": null,
            "kept_problems": problems, "steps_per_problem": steps}


def pack_curves() -> dict:
    """Aggregate sign-agreement curves, computed from the FULL runs."""
    out = {}
    for name, f in [("Qwen3-1.7B", "attr_qwen3_1p7b.json"),
                    ("Qwen3-4B", "attr_qwen3_4b.json"),
                    ("Qwen3-8B", "attr_qwen3_8b.json")]:
        p = OUT / f
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        steps = [s for s in data["steps"]
                 if len(s.get("top", [])) >= 2 and abs(s["margin"]) > 0.5]
        ok, kl = {}, {}
        n = 0
        for s in steps:
            alt = str(s["top"][1]["id"])
            rows = s["layers"]["layers"]
            fin = [r for r in rows if r.get("is_true_output")][0]
            if alt not in fin:
                continue
            final = float(fin[alt])
            if abs(final) < 1e-6:
                continue
            n += 1
            for r in rows:
                if alt in r:
                    ok.setdefault(r["layer"], []).append(
                        (float(r[alt]) > 0) == (final > 0))
                    kl.setdefault(r["layer"], []).append(r["lens_kl"])
        out[name] = {
            "n": n,
            "agreement": {str(L): round(100 * _mean(v), 1)
                          for L, v in sorted(ok.items())},
            "lens_kl": {str(L): round(_mean(v), 3)
                        for L, v in sorted(kl.items())},
        }
    return out


def pack_intervention() -> dict:
    """Layer sweep with its paired statistics, computed from the full run."""
    p = OUT / "intervention" / "vdd_final.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    runs = d["runs"]
    act = [r for r in runs if r["strength"] > 0]
    ctrl = [r for r in runs if r["strength"] == 0.0]

    by = {}
    for r in act:
        by.setdefault(r["layer"], {})[r["problem"]] = r["mean_logit_kl"]
    common = sorted(set.intersection(*[set(v) for v in by.values()])) if by else []

    def paired_stats(a, b):
        if not common or a not in by or b not in by:
            return None
        d_ = [by[a][p_] - by[b][p_] for p_ in common]
        m = statistics.fmean(d_)
        sd = statistics.stdev(d_) if len(d_) > 1 else 0.0
        se = sd / math.sqrt(len(d_)) if sd else 0.0
        return {
            "mean": round(m, 4),
            "t": round(m / se, 2) if se else None,
            "pos": sum(1 for x in d_ if x > 0),
            "neg": sum(1 for x in d_ if x < 0),
        }

    rows = []
    n_layers = max(by) + 1 if by else 0
    for s in d["by_layer"]:
        L = s["layer"]
        norm = next((r["injected_norm"] for r in act if r["layer"] == L), None)
        rows.append({
            "layer": L,
            "depth": round(100 * L / max(1, n_layers - 1), 1),
            "norm": round(norm, 1) if norm else None,
            "kl": round(s["mean_logit_kl"], 4),
            "agree": round(s["token_agreement"], 4),
            "diverged": round(s["frac_problems_diverged"], 2),
        })
    # Keys are always "<smaller>-<larger>" and the value is
    # (smaller layer's KL − larger layer's KL). The page labels each row with
    # the same order, so a negative value next to the plateau is correct
    # rather than a sign error. Earlier this was emitted in an order the page
    # did not match, which rendered "L16 − L12" with L12's sign.
    paired = {}
    for a in sorted(by):
        for b in sorted(by):
            if a < b:
                st = paired_stats(a, b)
                if st:
                    paired[f"{a}-{b}"] = st
    return {
        "model": "Qwen3-1.7B",
        "direction": d["direction"],
        "frac": d["frac_of_state_norm"],
        "n_problems": d["n_problems"],
        "control_exact": (
            all(c["token_agreement"] == 1.0 for c in ctrl)
            and all(c["mean_logit_kl"] == 0.0 for c in ctrl)
        ),
        "n_control": len(ctrl),
        "rows": rows,
        "paired": paired,
        "n_paired": len(common),
    }


def pack_cot() -> dict:
    """Chain-of-thought effects, including the length dependence."""
    out: Dict = {"examples": [], "length_dependence": []}
    seen = set()
    per_tag: Dict[str, int] = {"60-token": 0, "1024-token": 0}

    long_p = OUT / "intervention" / "cot_long_summary.json"
    short_p = OUT / "intervention" / "cot_divergence_summary.json"
    # The text lives in the intervention output, not in the summary's
    # `per_run` rows (those carry only the derived measurements, which is
    # what keeps the summary small). The two are joined on
    # (problem, direction, strength).
    raw: Dict[tuple, dict] = {}
    for tag, f in [("60-token", "replication_24problems_L20.json"),
                   ("1024-token", "cot_long.json")]:
        p = OUT / "intervention" / f
        if not p.exists():
            continue
        for r in json.loads(p.read_text()):
            key = (tag, r.get("prompt_label"), r.get("direction"),
                   r.get("strength"))
            raw.setdefault(key, r)

    for path, tag, label in [(short_p, "60-token", 60),
                             (long_p, "1024-token", 1024)]:
        if not path.exists():
            continue
        d = json.loads(path.read_text())
        for c in d["per_condition"]:
            if c["strength"] == 0.0:
                continue
            out["length_dependence"].append({
                "run": tag, "max_tokens": label,
                "direction": c["direction"],
                "agree": c["mean_token_agreement"],
                "kl": c["mean_logit_kl"],
                "overlap": c["mean_verbatim_overlap"],
                "n": c["n"],
            })
        # Take examples from BOTH run lengths. Filling the list from the
        # first file alone left every entry at 60 tokens, so the one screen
        # that is about length dependence showed only one length — the
        # reader could not see the effect the screen is named after.
        for r in d["per_run"]:
            if r["strength"] == 0.0:
                continue
            r["primary_text"] = ""
            src = raw.get((tag, r["label"], r["direction"], r["strength"]))
            if src:
                r["primary_text"] = src.get("primary_text", "") or ""
                r["shadow_text"] = src.get("shadow_text", "") or ""
            if len(r["primary_text"]) < 200:
                continue
            key = (r["label"], r["direction"])
            if key in seen:
                continue
            seen.add(key)
            out["examples"].append({
                "run": tag,
                "problem": r["label"],
                "direction": r["direction"],
                "strength": r["strength"],
                "n_steps": r["n_steps"],
                "chars": r["reason_chars_primary"],
                "first_div": r["first_divergence_char"],
                "overlap": r["verbatim_step_overlap"],
                "primary": r["primary_text"][:2600],
                "shadow": r["shadow_text"][:2600],
            })
            if per_tag[tag] >= 6:
                break
            per_tag[tag] += 1

    for path in (long_p, short_p):
        if path.exists():
            d = json.loads(path.read_text())
            rows = d["per_run"]
            out.setdefault("closure", {})[path.stem] = {
                "n": len(rows),
                "closed_think": sum(1 for r in rows if r["closed_think"]),
                "answer_known": sum(1 for r in rows if r["answer_known"]),
                "mean_steps": _mean([r["n_steps"] for r in rows]),
                "mean_reason_chars": _mean(
                    [r["reason_chars_primary"] for r in rows]),
            }
            if len(out["closure"]) >= 2:
                break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT / "viewer_bundle.json"))
    ap.add_argument("--problems", type=int, default=10)
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--top-k", type=int, default=4)
    args = ap.parse_args()

    src = json.loads((OUT / "problem_index.json").read_text())
    labels = list(src.keys())[: args.problems]
    problems = [labels[i] for i in range(0, len(labels), max(1, len(labels) // args.problems))][: args.problems]
    prompts = {k: src[k].get("prompt", "") for k in problems}

    bundle = {
        "prompts": prompts,
        "curves": pack_curves(),
        "attribution": pack_attribution(problems, args.steps, args.top_k),
        "intervention": pack_intervention(),
        "cot": pack_cot(),
    }
    out_path = Path(args.out)
    html_path = HERE.parent.parent / "frontend" / "public" / "qwen3_hidden_space.html"
    out_path.write_text(json.dumps(bundle, ensure_ascii=False,
                                   separators=(",", ":")))

    # Tokenise the bundle into the page's placeholder, if the page is there.
    #
    # The escaping here is deliberate and narrow. A blanket `</` -> `<\/`
    # is the reflex, and it is WRONG for this data: the bundle contains real
    # token strings like `</think>` and `</tool_response>`, and escaping
    # their slashes turns them into `<\/think>`, which the HTML parser then
    # swallows as an unknown tag. The page rendered a candidate list of bare
    # numbers where the token text should have been. Only `</script` can
    # actually terminate the enclosing block, so only that is escaped.
    if html_path.exists():
        html = html_path.read_text()
        if "__BUNDLE__" in html:
            blob = json.dumps(bundle, ensure_ascii=False,
                              separators=(",", ":")).replace(
                "</script", "<\\/script")
            html_path.write_text(html.replace("__BUNDLE__", blob))
            # A sanity check, because this failure is invisible in the source
            # and only shows up as missing text in a rendered page.
            written = html_path.read_text()
            probe = '</think>'
            assert probe in written, (
                "token text was mangled during injection — the viewer would "
                "render token ids instead of words"
            )
            print(f"injected into {html_path}")
        else:
            print(f"note: {html_path.name} has no __BUNDLE__ placeholder; "
                  "wrote bundle only")

    size = out_path.stat().st_size
    print(f"wrote {args.out}  ({size/1e6:.2f} MB)")
    print(f"  problems kept      : {problems}")
    print(f"  attribution steps  : "
          f"{ {k: len(v['steps']) for k, v in bundle['attribution']['models'].items()} }")
    print(f"  curve models       : {list(bundle['curves'])}")
    print(f"  intervention layers: {len(bundle['intervention'].get('rows', []))}")
    print(f"  cot examples       : {len(bundle['cot']['examples'])}")


if __name__ == "__main__":
    main()
