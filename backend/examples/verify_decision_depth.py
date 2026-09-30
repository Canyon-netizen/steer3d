"""Does the decision-depth finding predict where steering works?

Finding 8 measures that the chosen-vs-runner-up logit gap only becomes
distinguishable from a random-token baseline in the last few layers. That is
an observation, and an observation about where a *difference* lives is not
the same as a claim about where an *intervention* lands. The two can come
apart: a layer can carry the decision without being the layer where changing
the state changes the decision.

This script tests the prediction that follows from Finding 8 anyway, because
it is falsifiable and cheap. If the decision is made in L20–L24, then:

  * steering in the **late** window (where the gap is actually formed)
    should change the model's token choice more often, and

  * steering in the **early** window (where the lens shows the model is
    still disagreeing with the eventual answer) should change it less,

even though every layer receives an identical vector of identical norm. The
existing `layer_scan.py` already shows that a fixed norm means wildly
different things at different depths — 343% of ‖h‖ at L4 versus 4% at L26.
That confound is controlled here by expressing every injection as a
*fraction of that layer's measured state norm*, so an early-layer
injection is proportionally as large as a late-layer one.

The honest reading if the prediction fails is "the lens depth and the
effective intervention depth are different things", which is itself a
result worth having — it is the same reason Finding 6 exists, where reading
the direction out at a different layer than it is applied changed the effect
by 2.15×.

Control: strength 0.0 at every layer, which must be exactly inert. Any
non-zero divergence there is the harness, not the intervention.

Usage:
    python3 backend/examples/verify_decision_depth.py \
        --model-path /path/to/Qwen3-1.7B \
        --problems-file /tmp/problem_index.json \
        --layers 8 12 16 20 22 24 26 \
        --out backend/examples/output/intervention/decision_depth_causal.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List, Optional


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--problems-file", required=True)
    ap.add_argument("--layers", type=int, nargs="+",
                    default=[8, 12, 16, 20, 22, 24, 26])
    ap.add_argument("--strength", type=float, default=0.2)
    ap.add_argument("--frac-of-state-norm", type=float, default=0.2,
                    help="inject this fraction of the layer's own measured "
                         "‖h‖, so an early injection is proportionally as "
                         "large as a late one")
    ap.add_argument("--max-new-tokens", type=int, default=48)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="bfloat16",
                    help="bf16 is fine here: this measures the effect of an "
                         "injection on the argmax, not a logit-lens "
                         "read-out, which is where bf16 fails.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import sys
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent))
    sys.path.insert(0, str(here))
    from run_intervention import load_model, run_dual_stream  # noqa: E402
    from core.steering import SteeringRegistry  # noqa: E402
    import numpy as np  # noqa: E402

    registry = SteeringRegistry(None)
    if not registry.load():
        raise SystemExit(f"could not load vectors: {registry.load_error}")

    profiles_path = here / "output" / "layer_profiles.json"
    norms: Dict[int, float] = {}
    if profiles_path.exists():
        prof = json.loads(profiles_path.read_text())
        rows = prof.get("layers", prof) if isinstance(prof, dict) else prof
        if isinstance(rows, list):
            for rec in rows:
                if isinstance(rec, dict) and "layer" in rec and "mean_norm" in rec:
                    norms[int(rec["layer"])] = float(rec["mean_norm"])
        elif isinstance(rows, dict):
            for k, rec in rows.items():
                if isinstance(rec, dict) and "mean_norm" in rec:
                    norms[int(k)] = float(rec["mean_norm"])

    def layer_norm(L: int) -> Optional[float]:
        return norms.get(int(L))

    problems = json.loads(Path(args.problems_file).read_text())
    if isinstance(problems, dict):
        if "problems" in problems:
            problems = problems["problems"]
        else:
            problems = [dict(v, label=v.get("id", k)) if isinstance(v, dict)
                         else {"label": k, "prompt": str(v)}
                         for k, v in problems.items()]

    direction = "confidence_up"
    vec = registry.unit_vector(direction)
    if vec is None:
        raise SystemExit(f"no {direction} vector in registry")
    vec = np.asarray(vec, dtype=np.float32)
    vec = vec / (np.linalg.norm(vec) + 1e-8)

    model, tok = load_model(args.model_path, args.device, args.dtype)

    results: List[dict] = []
    for pi, prob in enumerate(problems):
        text = prob.get("prompt") or prob.get("text") or ""
        if not text:
            continue
        templ = tok.apply_chat_template(
            [{"role": "user", "content": text}],
            tokenize=False, add_generation_prompt=True,
        ) if getattr(tok, "chat_template", None) else text

        for L in args.layers:
            ln = layer_norm(L)
            if ln is None:
                print(f"  (no measured norm for L{L}, skipping)")
                continue
            scale = args.frac_of_state_norm * ln
            injected = vec * scale
            for strength in (0.0, args.strength):
                res = run_dual_stream(
                    model, tok, templ,
                    steer_vec=(injected * strength) if strength else injected,
                    layer=L,
                    max_new_tokens=args.max_new_tokens,
                    track_shadow=True,
                )
                s = res["shadow"].summary()
                results.append({
                    "problem": prob.get("label"),
                    "layer": L,
                    "strength": strength,
                    "injected_norm": float(scale * strength),
                    "frac_of_state_norm": args.frac_of_state_norm * strength,
                    "n_steps": s.get("n_steps"),
                    "token_agreement": s.get("token_agreement"),
                    "mean_logit_kl": s.get("mean_logit_kl"),
                    "first_diverged_step": s.get("first_diverged_step"),
                    "primary_text": res["primary_text"],
                    "shadow_text": res["shadow_text"],
                })
            got = results[-1]
            print(f"[{pi+1}/{len(problems)}] {prob.get('label','?')} "
                  f"L{L} |‖v‖={scale:.1f} ({args.frac_of_state_norm*100:.0f}% of "
                  f"‖h‖) agree={got['token_agreement']:.3f} "
                  f"KL={got['mean_logit_kl']:.4f}")

    # --- aggregate by layer, and split late vs early ---
    by_layer: Dict[int, Dict[float, List[dict]]] = {}
    for r in results:
        by_layer.setdefault(r["layer"], {}).setdefault(r["strength"], []).append(r)

    summary = []
    for L in sorted(by_layer):
        cells = by_layer[L]
        ctrl = cells.get(0.0, [])
        act = cells.get(args.strength, [])
        summary.append({
            "layer": L,
            "n": len(act),
            "control_agreement": statistics.fmean(
                [c["token_agreement"] for c in ctrl]) if ctrl else None,
            "control_kl": statistics.fmean(
                [c["mean_logit_kl"] for c in ctrl]) if ctrl else None,
            "token_agreement": statistics.fmean(
                [a["token_agreement"] for a in act]) if act else None,
            "mean_logit_kl": statistics.fmean(
                [a["mean_logit_kl"] for a in act]) if act else None,
            "frac_problems_diverged": (
                sum(1 for a in act if a["first_diverged_step"] is not None)
                / len(act)) if act else None,
        })

    out = {
        "model": args.model_path,
        "direction": direction,
        "strength": args.strength,
        "frac_of_state_norm": args.frac_of_state_norm,
        "n_problems": len(problems),
        "note": (
            "Every layer receives a vector of the same norm *relative to its "
            "own measured state norm*, so a fixed-norm confound is not what "
            "separates the layers here. strength 0.0 is the harness control "
            "and must be exactly inert."
        ),
        "by_layer": summary,
        "runs": results,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print(f"\n{'layer':>6}{'ctrl agr':>10}{'ctrl KL':>10}"
          f"{'agr':>8}{'KL':>9}{'diverged':>10}")
    print("-" * 53)
    for s in summary:
        print(f"{s['layer']:>6}{s['control_agreement']:>10.4f}"
              f"{s['control_kl']:>10.4f}{s['token_agreement']:>8.4f}"
              f"{s['mean_logit_kl']:>9.4f}"
              f"{s['frac_problems_diverged']:>10.2f}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
