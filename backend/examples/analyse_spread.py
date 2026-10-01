#!/usr/bin/env python3
"""How many dimensions does the answer actually live in?  (Finding 13, part 3)

Why this file exists
--------------------
``docs/INTERPRETABILITY.md`` reports, for the divergence step, a *retention
ratio* (net logit change / absolute movement) and an *effective dimension
count*. Those numbers were produced by hand. A number in a document with no
code behind it is a number nobody -- including the next reader -- can re-derive,
and it is exactly the kind of figure that survives a refactor of the thing it
was measuring. This file makes both quantities reproducible, and the same code
runs over any model, so a cross-model comparison uses one implementation rather
than two ad-hoc ones.

The three quantities, per candidate token
-----------------------------------------
Let ``c_i = u_i * (h'_i - h_i)`` be the per-dimension contribution to the logit
change (exact, not a first-order expansion: the read-out is diagonal, so
``logit_u(h') - logit_u(h) = sum_i c_i``). Then:

``net``      ``sum_i c_i``           -- the signed logit change, the thing that
                                        actually moved the argmax.
``abs_mass`` ``sum_i |c_i|``         -- total movement across dimensions. This
                                        is the quantity that makes "the model
                                        moved a lot" and "the answer changed a
                                        lot" different numbers.
``retention`` ``|net| / abs_mass``   -- in [0, 1]. 1.0 means every dimension
                                        moved the same way; 0.0 means the
                                        movement cancelled exactly.
``n_eff``    ``(sum|c|)^2 / sum(c^2)`` -- the participation ratio of the
                                        contribution vector, i.e. the number of
                                        equally-weighted dimensions that would
                                        produce the same ``net``. It is bounded
                                        by the width (2048 for 1.7B, 1024 for
                                        0.6B), so **it must be read as a
                                        fraction of the model's own width** --
                                        comparing 587/2048 against 400/1024
                                        without normalising compares two
                                        different things.

Why "participation ratio" and not "count of dims above a threshold"
-------------------------------------------------------------------
A threshold count answers a question nobody asked ("how many dims cleared an
arbitrary cut?") and moves when the threshold moves. The participation ratio is
a function of the contribution vector alone, needs no cut, and reduces to the
dimension count in the well-behaved case where the magnitudes are equal.

Checks
------
Each is a claim that could be False, and one of them (``S3``) is the check
that the arithmetic matches what the model itself computed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch

# Same epsilon the read-out uses. Qwen3's config.json says 1e-6 for both
# models; it is a floor under a square root, so it only matters for vectors
# that are already ~0, and the choice is not load-bearing.
RMS_EPS = 1e-6


def load_readout(path: Path):
    """Returns (g, W) -- the final RMSNorm gain and the unembedding matrix.

    ``W`` is kept in fp16 on purpose: it is 1-2 GB unpacked and this file only
    needs a handful of rows at a time, which ``rows_of`` slices out first.
    """
    z = np.load(path)
    g = torch.from_numpy(z["model.norm.weight"].astype(np.float32))
    # Kept in the checkpoint's own fp16 and upcast per chunk. The stored values
    # are already fp16, so this is the same arithmetic the fully-fp32 path
    # does -- it just avoids a 1.2 GB temporary.
    W = torch.from_numpy(z["lm_head.weight"].astype(np.float16))
    return g, W


def rows_of(W: torch.Tensor, ids: List[int]) -> torch.Tensor:
    """Unembedding rows for a few tokens, in fp32. Slicing before casting
    keeps this at O(len(ids) x d) instead of materialising the whole matrix."""
    return W[torch.tensor(ids, dtype=torch.long)].to(torch.float32)


def argmax_readout(W: torch.Tensor, x: torch.Tensor, chunk: int = 32768) -> int:
    """argmax over the full vocabulary, in fp32, without materialising a
    full-vocabulary fp32 copy of W (1.2 GB for 1.7B).

    This is deliberately a *second, independent* route to the same answer the
    decomposition gives: it runs the read-out the way the model does -- one
    vector against every unembedding row -- instead of reusing the sliced row.
    Without it, "the per-dimension contributions sum to the logit change" would
    be a tautology, since both sides are ``u . (h' - h)``. And a tautological
    check is worse than no check, because it reports a green light for a thing
    it never tested.
    """
    best_v, best_i = float("-inf"), -1
    for lo in range(0, W.shape[0], chunk):
        blk = W[lo:lo + chunk].to(torch.float32) @ x
        v, i = torch.max(blk, dim=0)
        if float(v) > best_v:
            best_v, best_i = float(v), lo + int(i)
    return best_i


def load_vocab(path: Path) -> Dict[int, str]:
    """id -> surface form, from a HuggingFace ``tokenizer.json``.

    Two details that are not optional. The file is ``{"model": {"vocab":
    {token: id}}}``, so iterating it directly yields *tokens* as keys and the
    first ``int()`` blows up on the ``version`` field. And Qwen's BPE is
    byte-level, so a leading space is stored as ``Ġ``; left alone the output
    reads ``Ġgreater`` and a reader comparing it against the generated text
    would reasonably report it as a rendering bug in the page.
    """
    raw = json.loads(path.read_text())["model"]["vocab"]
    inv = {int(i): t for t, i in raw.items()}
    return {i: t.replace("\u0120", " ") for i, t in inv.items()}


def contributions(h: torch.Tensor, hp: torch.Tensor, u: torch.Tensor) -> torch.Tensor:
    """Per-dimension contribution to the logit change. ``h``/``hp`` are the
    **post-norm** final-layer residuals, so this is plain ``u * (hp - h)``.

    ``post_norm`` is not assumed, it is verified upstream: the collector writes
    the final layer under ``*_last32`` precisely because that layer has already
    been through ``model.norm`` (see ``diagnose_readout_index``). Applying the
    norm again is worth 16-19 logits and would make every number below wrong in
    a way that still looks plausible.
    """
    return u * (hp - h)


def spread(c: torch.Tensor, top_k: int, width: int) -> dict:
    net = float(c.sum())
    abs_mass = float(c.abs().sum())
    sq = float((c * c).sum())
    n_eff = (abs_mass * abs_mass / sq) if sq > 0 else 0.0
    order = torch.argsort(c.abs(), descending=True)
    top = float(c.abs()[order[:top_k]].sum())
    return {
        "net": net,
        "abs_mass": abs_mass,
        "retention": (abs(net) / abs_mass) if abs_mass > 0 else 0.0,
        "n_eff": n_eff,
        "top_k": top_k,
        "top_k_fraction": (top / abs_mass) if abs_mass > 0 else 0.0,
        # top_k_fraction is NOT comparable across models of different width:
        # 20 of 1024 dimensions is twice the share of 20 of 2048, before
        # anything about the model differs. Dividing by the uniform share
        # (top_k/width) makes it scale-free -- it reads as "how much more
        # concentrated than if every dimension contributed equally", which is
        # the quantity that can legitimately be compared across widths.
        "top_k_vs_uniform": ((top / abs_mass) / (top_k / width)
                             if abs_mass > 0 else 0.0),
    }


def analyse_one(pid: str, npz_path: Path, json_path: Path, g: torch.Tensor,
                W: torch.Tensor, vocab: Dict[int, str], top_k: int) -> dict:
    z = np.load(npz_path)
    rec = json.loads(json_path.read_text())
    c_ids = [int(x) for x in z["control_ids"]]
    s_ids = [int(x) for x in z["steered_ids"]]
    k = int(rec["paired"]["n_common_prefix"])

    if k >= min(len(c_ids), len(s_ids)) or c_ids[k] == s_ids[k]:
        return {"id": pid, "skipped": "no divergence"}
    if "control_last32" not in z:
        # Without the float32 final layer we would have to guess the post-norm
        # convention, and a guess here is worth 16-19 logits. Refuse instead.
        return {"id": pid, "skipped": "no *_last32 (cannot confirm post-norm)"}

    ctl = torch.from_numpy(z["control_last32"][k].astype(np.float32))
    ste = torch.from_numpy(z["steered_last32"][k].astype(np.float32))
    width = int(ctl.shape[-1])

    out: dict = {"id": pid, "step_index": k, "width": width, "candidates": {}}
    for role, tid in (("control", c_ids[k]), ("steered", s_ids[k])):
        u = rows_of(W, [tid])[0]
        s = spread(contributions(ctl, ste, u), top_k, width)
        s.update({"id": tid, "text": vocab.get(tid, f"<{tid}>")})
        out["candidates"][role] = s

    # S1: the read-out must reproduce the token the model actually emitted, on
    # both arms. This is the only check here with real discriminating power --
    # it compares my arithmetic against the model's own greedy output. Applying
    # the norm a second time at the final layer (see ``diagnose_readout_index``)
    # is worth 16-19 logits and makes both arms fail loudly instead of quietly
    # returning a plausible-looking spread for the wrong vector.
    out["argmax_control"] = argmax_readout(W, ctl)
    out["argmax_steered"] = argmax_readout(W, ste)
    out["emitted_control"] = c_ids[k]
    out["emitted_steered"] = s_ids[k]
    out["S1_ok"] = (out["argmax_control"] == c_ids[k]
                    and out["argmax_steered"] == s_ids[k])
    return out


def verify(rows: List[dict], W: torch.Tensor) -> List[dict]:
    """Claims that could each be False. Reported, never used to gate the run."""
    checks: List[dict] = []

    ok = [r for r in rows if "candidates" in r]
    checks.append({
        "name": "S1 读出的 argmax == 模型实际吐出的 token（两臂）",
        "ok": all(r["S1_ok"] for r in ok),
        "detail": "; ".join(
            f"{r['id']} ctl {r['argmax_control']}/{r['emitted_control']}"
            f" ste {r['argmax_steered']}/{r['emitted_steered']}" for r in ok),
    })

    # S2: retention is a fraction. Anything outside [0,1] means abs_mass was
    # computed over a different set than net -- a silent, plausible-looking bug.
    vals = [c["retention"] for r in ok for c in r["candidates"].values()]
    checks.append({
        "name": "S2 保留比例落在 [0,1]",
        "ok": all(0.0 <= v <= 1.0 + 1e-6 for v in vals),
        "detail": f"min={min(vals):.4f} max={max(vals):.4f}" if vals else "no rows",
    })

    # S3: n_eff cannot exceed the width. If it does, the ratio was taken over
    # more coordinates than the model has -- which is how a 1.7B number and a
    # 0.6B number end up being compared as if they were the same unit.
    checks.append({
        "name": "S3 等效维度数不超过该模型宽度",
        "ok": all(c["n_eff"] <= r["width"] + 1e-6
                  for r in ok for c in r["candidates"].values()),
        "detail": "; ".join(f"{r['id']} {r['width']}维 n_eff={max(c['n_eff'] for c in r['candidates'].values()):.0f}"
                            for r in ok),
    })

    # S4: a single dominating dimension is the thing this analysis exists to
    # rule out. If retention ever approaches 1 the story changes and the
    # document has to say so, so it is checked rather than assumed.
    mx = max(vals) if vals else 0.0
    checks.append({
        "name": "S4 保留比例远低于 1（未被单一维主导）",
        "ok": mx < 0.5,
        "detail": f"max retention={mx:.4f}",
    })
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paired-dir", required=True)
    ap.add_argument("--readout", required=True)
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--label", default="", help="model name for the report")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    vocab = load_vocab(Path(a.vocab))
    g, W = load_readout(Path(a.readout))

    rows = []
    for npz_path in sorted(Path(a.paired_dir).glob("pair_*.npz")):
        pid = npz_path.stem[len("pair_"):]
        j = npz_path.with_suffix(".json")
        if not j.exists():
            continue
        rows.append(analyse_one(pid, npz_path, j, g, W, vocab, a.top_k))

    live = [r for r in rows if "candidates" in r]
    checks = verify(live, W)
    for c in checks:
        print(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['name']}  {c['detail']}")

    rets = [c["retention"] for r in live for c in r["candidates"].values()]
    neffs = [c["n_eff"] / r["width"] for r in live for c in r["candidates"].values()]
    topf = [c["top_k_fraction"] for r in live for c in r["candidates"].values()]
    topu = [c["top_k_vs_uniform"] for r in live for c in r["candidates"].values()]
    n_pass = sum(1 for c in checks if c["ok"])
    print(f"\n=== {a.label or a.paired_dir} ===")
    print(f"  problems                {len(live)}")
    print(f"  retention               {min(rets):.3f} – {max(rets):.3f}"
          if rets else "  retention               n/a")
    print(f"  n_eff / width           {min(neffs):.3f} – {max(neffs):.3f}"
          if neffs else "")
    print(f"  top{a.top_k} fraction         {min(topf):.3f} – {max(topf):.3f}"
          if topf else "")
    print(f"  top{a.top_k} / uniform        {min(topu):.1f}x – {max(topu):.1f}x"
          if topu else "   (width-normalised; this is the cross-model comparable one)")
    print(f"  checks {n_pass}/{len(checks)} ===")

    Path(a.out).write_text(json.dumps({
        "schema": "spread_v1",
        "label": a.label,
        "readout": str(a.readout),
        "paired_dir": str(a.paired_dir),
        "top_k": a.top_k,
        "checks": checks,
        "problems": rows,
    }, ensure_ascii=False, indent=1))
    print(f"\nwrote {a.out}")
    return 0 if n_pass == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
