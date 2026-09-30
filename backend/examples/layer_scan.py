"""Where in the network is a steering vector most effective?

The first sweep showed the confidence vector works at L20 and that
over-driving it past ~0.2 breaks the computation. It did not answer
the other half of the question: *which layer should you inject at?*

That matters because the obvious default — the layer you extracted
the vector from — is not obviously the right one. Two reasons it
might not be:

  * the extraction layer is where the contrast was *measured*, not
    where the model is most *modifiable*;
  * the layer profile (`measure_layers.py`) shows ‖h‖ only tracks
    token entropy in L17-23, so a confidence vector applied at L14
    may be pushing on a representation that does not carry that
    information at all.

This script holds the strength *constant in absolute terms* while
sweeping the injection layer, which is the only way to compare them:
normalising strength per-layer would hold the relative perturbation
fixed and confound "does this layer matter" with "is this layer big".

Usage:
    python3 backend/examples/layer_scan.py \
        --direction confidence_up --norm 130 --layers 8 12 14 16 18 20 22 24 26 \
        --model-path /tmp/qwen3/master

Output: JSON with one entry per layer, plus a printed table.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.steering import SteeringRegistry  # noqa: E402
from run_intervention import (  # noqa: E402
    AIME_SYSTEM,
    format_result,
    load_model,
    run_dual_stream,
)


def build_prompt(problem: str, tokenizer) -> str:
    msgs = [
        {"role": "system", "content": AIME_SYSTEM},
        {"role": "user", "content": problem},
    ]
    return tokenizer.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True
    )


def main(args) -> int:
    registry = SteeringRegistry(Path(args.vector_dir) if args.vector_dir else None)
    if not registry.load():
        print(f"ERROR: {registry.load_error}")
        return 1
    n_cal = registry.load_layer_scales(
        Path(args.layer_profiles) if args.layer_profiles else None
    )
    if not n_cal:
        print("WARNING: no layer_profiles.json — falling back to 1.0 scale, "
              "which makes cross-layer comparison meaningless.")

    if not registry.has(args.direction):
        print(f"ERROR: unknown direction '{args.direction}'; "
              f"have: {', '.join(registry.names)}")
        return 1

    model, tok = load_model(args.model_path, args.device, args.dtype)
    print(f"model loaded: {args.model_path}")
    print(f"direction: {args.direction}")
    print(f"injecting ‖v‖ = {args.norm:.1f} (constant) at each layer")
    print()

    prompt_text = build_prompt(args.prompt, tok)

    rows = []
    for layer in args.layers:
        # Same absolute norm everywhere: unit vector × args.norm, so
        # the only thing varying is where it lands.
        unit = registry.unit_vector(args.direction)
        if unit is None:
            print(f"ERROR: no vector for {args.direction}")
            return 1
        vec = (unit * args.norm).astype(np.float32)

        t0 = time.time()
        res = run_dual_stream(
            model, tok, prompt_text, vec, layer,
            max_new_tokens=args.max_new_tokens,
            track_shadow=True,
        )
        dt = time.time() - t0
        summ = res["shadow"].summary()

        print(format_result(res, args.direction, 0.0, layer, args.norm,
                            verbose=args.verbose))
        print(f"  wallclock: {dt:.1f}s")
        print()

        rows.append({
            "layer": layer,
            "norm": args.norm,
            "layer_rms": registry.layer_rms(layer),
            "n_steps": res["n_steps"],
            "token_agreement": summ.get("token_agreement"),
            "first_diverged_step": summ.get("first_diverged_step"),
            "mean_logit_kl": summ.get("mean_logit_kl"),
            "delta_entropy": (
                summ["mean_entropy_primary"] - summ["mean_entropy_shadow"]
                if np.isfinite(summ.get("mean_entropy_primary", float("nan")))
                and np.isfinite(summ.get("mean_entropy_shadow", float("nan")))
                else None
            ),
            "max_divergence": summ.get("max_divergence"),
            "mean_divergence": summ.get("mean_divergence"),
            "primary_text": res["primary_text"],
            "shadow_text": res["shadow_text"],
            "wallclock_s": dt,
        })

    print("=" * 72)
    print("  Cross-layer scan — constant ‖v‖, varying injection point")
    print("=" * 72)
    print(f"{'layer':>6} {'‖h‖':>9} {'rel':>7} {'agree':>7} {'Δentropy':>10} "
          f"{'maxdiv':>8} {'KL':>8}")
    for r in rows:
        rel = r["norm"] / (r["layer_rms"] or 1.0)
        de = r["delta_entropy"]
        print(
            f"{r['layer']:>6} {r['layer_rms']:>9.1f} {rel:>7.2%} "
            f"{(r['token_agreement'] or 0):>7.1%} "
            f"{(f'{de:+.4f}' if de is not None else 'n/a'):>10} "
            f"{r['max_divergence']:>8.4f} {(r['mean_logit_kl'] or 0):>8.4f}"
        )
    print()
    print("  'rel' is ‖v‖/‖h‖ at that layer — the size of the perturbation "
          "as a fraction of the state it perturbs.")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "direction": args.direction,
            "norm": args.norm,
            "prompt": args.prompt,
            "max_new_tokens": args.max_new_tokens,
            "rows": rows,
        }, indent=2, ensure_ascii=False))
        print(f"\nwrote {out}")
    return 0


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--prompt", type=str, required=True)
    ap.add_argument("--direction", type=str, default="confidence_up")
    ap.add_argument("--norm", type=float, required=True,
                    help="Absolute ‖v‖ to inject, held constant across layers")
    ap.add_argument("--layers", type=int, nargs="+",
                    default=[8, 12, 14, 16, 18, 20, 22, 24, 26])
    ap.add_argument("--max-new-tokens", type=int, default=80)
    ap.add_argument("--model-path", type=str,
                    default=os.environ.get("QWEN3_MODEL_PATH", "/tmp/qwen3/master"))
    ap.add_argument("--device", type=str, default="cuda:0")
    ap.add_argument("--dtype", default="bfloat16",
                    choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--vector-dir", type=str, default=None)
    ap.add_argument("--layer-profiles", type=str, default=None)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--verbose", action="store_true", default=True)
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
