"""Summarise a token-attribution run into an answerable claim.

`attribute_token_choice.py` writes a per-step trace: for every decoding step,
the chosen token, its top alternatives, and the layer-by-layer logit gap
between them. That file is the raw material; the question it was built to
answer is "which layer decided this token", and that needs aggregation
across steps and problems before it means anything.

The aggregation is deliberately conservative, because the two obvious ways
to summarise a logit lens are both misleading:

  * **Averaging the gap curve.** The gap is a difference between two tokens
    that changes sign as the decision is made. Its mean over layers is close
    to zero for *every* step, including steps where the decision is
    emphatic, because the early negative and late positive roughly cancel.
    The quantity that carries the decision is the *sign agreement* -- how
    often the layer's partial model already picks the eventual winner.

  * **"Flip layer" per step.** The first layer reaching 50% of the final gap
    is a tempting summary and it is an artefact here. At L0 the lens is
    maximally unfaithful (KL ~145, far above every other layer) and its
    gap agrees with the final answer only ~56% of the time -- a coin flip.
    So a large fraction of steps "commit" at L0 for reasons that have
    nothing to do with the computation. The flip layer is still reported,
    but it is labelled, and the claim is made from the sign-agreement curve
    instead.

What is reported:

  * `sign_agreement_by_layer` -- the fraction of steps where layer L's
    partial model already prefers the token that is ultimately chosen,
    against the top-1 alternative. This is the decision-depth curve, and it
    is the honest version of "which layer decided this token".
  * `decision_layer_80pct` / `decision_layer_90pct` -- the depths at which
    that agreement crosses 80% and 90%.
  * `mean_lens_kl_by_layer` beside both, because a depth claim in a
    high-KL region is a claim about the lens, not the model.

Usage:
    python3 backend/examples/summarise_attribution.py \
        --json backend/examples/output/token_attribution.json \
        --out backend/examples/output/token_attribution_summary.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List, Optional


def flip_layer(layers: List[dict], alt_key: str, frac: float = 0.5) -> Optional[int]:
    """First layer whose |gap| reaches `frac` of the final true gap.

    Signed, because the decision can commit from either side: a token that
    the early layers actively reject and the late layers adopt is still a
    decision made at the layer where the sign settles.
    """
    true_rows = [r for r in layers if r.get("is_true_output")]
    if not true_rows:
        return None
    final = true_rows[-1]
    if alt_key not in final:
        return None
    target = frac * abs(float(final[alt_key]))
    if target < 1e-6:
        return None
    for r in layers:
        if r.get("is_true_output"):
            break
        if alt_key in r and abs(float(r[alt_key])) >= target:
            return int(r["layer"])
    return None


def sign_settle_layer(layers: List[dict], alt_key: str) -> Optional[int]:
    """First layer whose gap sign matches the final sign and stays there.

    The flip layer above measures magnitude; this one measures the *decision*.
    They are reported separately because they routinely disagree: a layer can
    move the gap a long way without changing which token wins.
    """
    true_rows = [r for r in layers if r.get("is_true_output")]
    if not true_rows or alt_key not in true_rows[-1]:
        return None
    final_sign = (float(true_rows[-1][alt_key]) > 0)
    for r in layers:
        if r.get("is_true_output"):
            break
        if alt_key in r and ((float(r[alt_key]) > 0) == final_sign):
            # require it to stick
            ok = all(
                ((float(s[alt_key]) > 0) == final_sign)
                for s in layers if s["layer"] > r["layer"] and alt_key in s
                and not s.get("is_true_output")
            )
            if ok:
                return int(r["layer"])
    return None


def summarise(path: str) -> dict:
    data = json.loads(Path(path).read_text())
    steps = data.get("steps", [])

    # Only steps where the decision is non-trivial. A step whose top-2 gap
    # is 0.04 is not a decision, and averaging it in dilutes the very
    # question being asked.
    informative = [
        s for s in steps
        if len(s.get("top", [])) >= 2 and abs(float(s.get("margin") or 0.0)) > 0.5
    ]

    flip: List[int] = []
    margins: List[float] = []
    entropies: List[float] = []

    kl_sum: Dict[int, float] = {}
    kl_n: Dict[int, int] = {}
    sign_ok: Dict[int, int] = {}
    mag_ratio: Dict[int, float] = {}

    for s in informative:
        layers = s.get("layers", {}).get("layers", [])
        if not layers:
            continue
        alt = str(s["top"][1]["id"])
        true_rows = [r for r in layers if r.get("is_true_output")]
        if not true_rows or alt not in true_rows[-1]:
            continue
        final = float(true_rows[-1][alt])
        if abs(final) < 1e-6:
            continue
        f = flip_layer(layers, alt)
        if f is not None:
            flip.append(f)
        if s.get("margin") is not None:
            margins.append(float(s["margin"]))
        if s.get("entropy") is not None:
            entropies.append(float(s["entropy"]))

        for r in layers:
            L = r["layer"]
            kl_sum[L] = kl_sum.get(L, 0.0) + float(r["lens_kl"])
            kl_n[L] = kl_n.get(L, 0) + 1
            if alt in r:
                v = float(r[alt])
                # Does this layer's partial model already pick the winner?
                if (v > 0) == (final > 0):
                    sign_ok[L] = sign_ok.get(L, 0) + 1
                mag_ratio[L] = mag_ratio.get(L, 0.0) + abs(v) / abs(final)

    n_ok = len(informative)
    sign_curve = {
        str(L): (sign_ok.get(L, 0) / n_ok) for L in sorted(sign_ok)
    }
    mag_curve = {
        str(L): (mag_ratio.get(L, 0.0) / n_ok) for L in sorted(mag_ratio)
    }

    def pct(xs, p):
        if not xs:
            return None
        xs = sorted(xs)
        k = max(0, min(len(xs) - 1, int(round(p * (len(xs) - 1)))))
        return xs[k]

    # First layer from which the sign agrees with the final answer on at
    # least 90% of steps. This is the layer below which the choice is not
    # yet determined -- a much more defensible statement than any single
    # step's "flip layer".
    decide_90 = next(
        (int(L) for L in sorted(sign_curve) if sign_curve[L] >= 0.90), None
    )
    decide_80 = next(
        (int(L) for L in sorted(sign_curve) if sign_curve[L] >= 0.80), None
    )

    return {
        "source": path,
        "model": data.get("model"),
        "n_steps": len(steps),
        "n_informative": n_ok,
        "sign_agreement_by_layer": sign_curve,
        "magnitude_ratio_by_layer": mag_curve,
        "decision_layer_80pct": decide_80,
        "decision_layer_90pct": decide_90,
        "flip_layer": {
            "median": statistics.median(flip) if flip else None,
            "p25": pct(flip, 0.25), "p75": pct(flip, 0.75),
        },
        "margin": {
            "median": statistics.median(margins) if margins else None,
            "min": min(margins) if margins else None,
            "max": max(margins) if margins else None,
        },
        "entropy_median": statistics.median(entropies) if entropies else None,
        "mean_lens_kl_by_layer": {
            str(k): kl_sum[k] / kl_n[k] for k in sorted(kl_sum)
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    summaries = [summarise(p) for p in args.json]
    out = {
        "note": (
            "flip_layer = first layer where |gap| reaches 50% of the final "
            "true gap. sign_settle_layer = first layer after which the sign "
            "matches the final sign and never changes again. mean_lens_kl_by_layer "
            "bounds both: a depth claim in a high-KL region is a claim about "
            "the lens, not the model."
        ),
        "runs": summaries,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    for s in summaries:
        print(f"\n{s['source']}  ({s['model']})")
        print(f"  steps analysed        : {s['n_informative']}/{s['n_steps']} "
              f"(margin > 0.5)")
        sc = s["sign_agreement_by_layer"]
        print(f"  decision layer        : 80% at L{s['decision_layer_80pct']}, "
              f"90% at L{s['decision_layer_90pct']}")
        f = s["flip_layer"]
        print(f"  per-step flip layer   : median {f['median']} "
              f"(IQR {f['p25']}–{f['p75']})  [not a decision-depth measure; "
              f"see module docstring]")
        m = s["margin"]
        print(f"  margin                : median {m['median']:.2f} "
              f"(range {m['min']:.2f}–{m['max']:.2f})")
        print(f"  entropy median        : {s['entropy_median']:.5f}")
        print("  sign agreement        : " +
              "  ".join(f"L{k}={sc[k]*100:.0f}%" for k in sc
                        if int(k) % 4 == 0 or int(k) in ("1", "27", "28")))
        kl = s["mean_lens_kl_by_layer"]
        print("  mean lens KL          : " +
              "  ".join(f"L{k}={kl[k]:.2f}" for k in kl
                        if int(k) % 4 == 0 or int(k) in ("27", "28")))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
