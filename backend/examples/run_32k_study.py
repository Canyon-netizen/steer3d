#!/usr/bin/env python
"""One process for the whole 32k study.

Why a single process
--------------------
`import torch` from this box's NFS-backed home takes minutes — it has been
measured over 290 s without finishing, and copying the env to local disk is
not viable either: the mount is shared, load average sits near 39, and a
whole-env tar stream measured 0.00 MB/s under that contention. Both the
32k calibration and the 32k measurement need torch and the model, so
splitting them across two processes would pay that cost twice for no gain.

More importantly, the phase-2 budget is *derived from* phase 1. Asking how
many tokens Qwen3 needs before it closes `</think>` has to happen before
the dual-stream runs can be sized at all. Doing both in one process means
the answer feeds straight into the next phase with no hand-off, no
intermediate file to go stale, and no second interpreter start-up.

Phases
------
A. calibrate — unsteered, single stream, 32768 budget. Records where
   `</think>` actually closes, or that it never does.
B. size      — budget = max observed close + headroom, clamped to 32768.
C. measure   — dual stream (steered + counterfactual shadow) at that
   budget, every problem, with an exactly-zero control.

If phase A shows the chain never closes even at 32768, that is itself the
answer: the answer-level effect stays structurally unmeasurable at this
budget, and phase C is skipped rather than run at a length that is known
in advance not to close.

Usage:
    python3 run_32k_study.py --model-path /models/Qwen3-1.7B \
        --device cuda:0 --calibrate-n 3 --measure-n 24 \
        --directions confidence_up --sweep 0.2 --layer 20 \
        --out-dir output/long32
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

_T0 = time.time()


def _phase(msg: str) -> None:
    print(f"\n{'=' * 68}\n== [{time.time() - _T0:7.1f}s] {msg}\n{'=' * 68}",
          flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--problems-file", default="output/problem_index.json")
    ap.add_argument("--calibrate-n", type=int, default=3)
    ap.add_argument("--measure-n", type=int, default=24)
    ap.add_argument("--directions", nargs="+", default=["confidence_up"])
    ap.add_argument("--sweep", nargs="+", type=float, default=[0.2])
    ap.add_argument("--layer", type=int, default=20)
    ap.add_argument("--track-stride", type=int, default=64)
    ap.add_argument("--max-positions", type=int, default=32768,
                    help="Hard ceiling for the budget; the model's own "
                         "position limit is checked separately")
    ap.add_argument("--headroom", type=float, default=1.15,
                    help="Multiply the longest observed chain by this to get "
                         "the measurement budget. Below 1.0 the measurement "
                         "would truncate the very runs it is trying to close.")
    ap.add_argument("--no-control", action="store_true")
    ap.add_argument("--out-dir", default="output/long32")
    args = ap.parse_args()

    # torch is imported here, not at module scope, so the elapsed-time line
    # in _phase() above stays truthful about how long the import cost.
    _phase("importing torch (this is the slow part on this filesystem)")
    t = time.time()
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    print(f"  torch {torch.__version__}  cuda={torch.cuda.is_available()}  "
          f"({time.time() - t:.1f}s)")

    _phase("importing project modules")
    t = time.time()
    from analyse_cot_divergence import _selftest as extractor_selftest
    from run_long_cot import build_prompt, generate, load_problems
    from run_intervention import load_model
    from core.steering import SteeringRegistry
    print(f"  ok ({time.time() - t:.1f}s)")

    _phase("answer-extractor self-test")
    extractor_selftest()
    print("  ok — a wrong extractor would report a clean '0 answers known'")

    _phase("loading model")
    t = time.time()
    model, tok = load_model(args.model_path, args.device, args.dtype)
    print(f"  {args.model_path}")
    print(f"  layers={model.config.num_hidden_layers} "
          f"hidden={model.config.hidden_size} "
          f"maxpos={model.config.max_position_embeddings} "
          f"({time.time() - t:.1f}s)")
    limit = model.config.max_position_embeddings
    if args.max_positions > limit - 512:
        print(f"  WARNING budget {args.max_positions} exceeds position limit "
              f"{limit}; clamping to {limit - 1024}")
        args.max_positions = limit - 1024

    problems = load_problems(args.problems_file, None)
    print(f"  {len(problems)} problem(s) available")
    if not problems:
        print("ERROR: no problems")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- A
    _phase(f"PHASE A — calibrate on {args.calibrate_n} problem(s), "
           f"{args.max_positions} budget, unsteered")
    cal = []
    for prob in problems[: args.calibrate_n]:
        prompt = build_prompt(tok, prob["prompt"])
        print(f"\n  [{prob['id']}] {prob['prompt'][:90]}")
        r = generate(model, tok, prompt, args.max_positions,
                     steer_vec=None, layer=args.layer, track_stride=0)
        rec = {
            "label": prob["id"],
            "n_steps": r["n_steps"],
            "budget": r["budget"],
            "hit_eos": r["hit_eos"],
            "truncated": not r["hit_eos"] and r["n_steps"] >= r["budget"],
            "closed_think": r["closed_think"],
            "think_close_step": r["think_close_step"],
            "n_reason_chars": r["n_reason_chars"],
            "n_answer_chars": r["n_answer_chars"],
            "answer": r["answer"],
            "wallclock_s": r["wallclock_s"],
            "tail": r["primary_text"][-300:],
        }
        cal.append(rec)
        print(f"    steps={rec['n_steps']} "
              f"truncated={rec['truncated']} "
              f"</think> at {rec['think_close_step']} "
              f"reason={rec['n_reason_chars']}ch answer={rec['answer']} "
              f"({rec['wallclock_s']/60:.1f} min)")
    (out_dir / "calibrate.json").write_text(
        json.dumps(cal, indent=2, ensure_ascii=False))

    closed = [c for c in cal if c["closed_think"]]
    print(f"\n  closed </think>: {len(closed)}/{len(cal)}")
    if not closed:
        longest = max(c["n_steps"] for c in cal)
        print(f"  NO chain closed even at {args.max_positions} tokens "
              f"(longest ran {longest}).")
        print("  => the answer-level effect is STILL structurally "
              "unmeasurable at 32k.")
        print("  => phase C is deliberately NOT run: a dual-stream pass at a")
        print("     length known in advance not to close buys nothing.")
        (out_dir / "verdict.json").write_text(json.dumps({
            "phase_a": cal,
            "closed": len(closed), "n": len(cal),
            "verdict": "answer_effect_structurally_unmeasurable_at_32k",
            "reason": "no </think> within the 32768-token budget",
        }, indent=2, ensure_ascii=False))
        return 0

    # ---------------------------------------------------------------- B
    longest = max(c["think_close_step"] for c in closed)
    budget = int(min(args.max_positions, longest * args.headroom))
    print(f"\n  longest chain: {longest} steps")
    print(f"  headroom x{args.headroom} -> measurement budget {budget}")
    (out_dir / "budget.json").write_text(json.dumps({
        "observed_longest_close_step": longest,
        "headroom": args.headroom,
        "budget": budget,
        "ceiling": args.max_positions,
    }, indent=2))

    # ---------------------------------------------------------------- C
    _phase("loading steering vectors")
    registry = SteeringRegistry(
        Path("output/steering_vectors") if Path("output/steering_vectors").is_dir()
        else None)
    if not registry.load():
        print(f"ERROR: {registry.load_error}")
        return 1
    n_cal = registry.load_layer_scales(Path("output/layer_profiles.json"))
    if n_cal and registry.has_rms(args.layer):
        rms = registry.layer_rms(args.layer)
        print(f"  layer L{args.layer} ‖h‖ = {rms:.2f}  "
              f"[layer_profiles.json, {n_cal} layers]")
    else:
        rms = 1.0
        print(f"  WARNING no measured scale for L{args.layer}; using 1.0")
    registry.set_layer_rms(args.layer, rms)

    cells = []
    if not args.no_control:
        # Zeros, never None: None disables the shadow stream, which would
        # turn the control into "no comparison at all" instead of
        # "a comparison that must come out at exactly zero".
        cells.append(("control_zero",
                      np.zeros(model.config.hidden_size, dtype=np.float32)))
    for d in args.directions:
        for s in args.sweep:
            v = registry.scaled(d, s, args.layer)
            if v is None:
                print(f"  !! no vector for {d} @ L{args.layer}")
                continue
            cells.append((f"{d}@{s}", v))
    print(f"  cells: {[c for c, _ in cells]}")

    # ---------------------------------------------------------------- D
    _phase(f"PHASE C — measure on {args.measure_n} problem(s) x "
           f"{len(cells)} cell(s), budget {budget}")
    recs = []
    for pi, prob in enumerate(problems[: args.measure_n]):
        prompt = build_prompt(tok, prob["prompt"])
        for name, vec in cells:
            print(f"\n  [{pi+1}/{args.measure_n}] {prob['id']} · {name}",
                  flush=True)
            r = generate(model, tok, prompt, budget, steer_vec=vec,
                         layer=args.layer, track_stride=args.track_stride)
            rec = {
                "label": prob["id"], "cell": name,
                "n_steps": r["n_steps"], "budget": budget,
                "hit_eos": r["hit_eos"],
                "truncated": not r["hit_eos"] and r["n_steps"] >= budget,
                "closed_think": r["closed_think"],
                "shadow_closed_think": r["shadow_closed_think"],
                "think_close_step": r["think_close_step"],
                "n_reason_chars": r["n_reason_chars"],
                "n_answer_chars": r["n_answer_chars"],
                "answer": r["answer"], "shadow_answer": r["shadow_answer"],
                "answer_known": r["answer"] is not None,
                "answer_changed": (None if r["answer"] is None
                                   or r["shadow_answer"] is None
                                   else r["answer"] != r["shadow_answer"]),
                "injected_norm": float(np.linalg.norm(vec)),
                "wallclock_s": r["wallclock_s"],
                "summary": r["acc"].summary() if r["acc"] else None,
            }
            recs.append(rec)
            (out_dir / "measure.json").write_text(
                json.dumps(recs, indent=2, ensure_ascii=False))
            s = rec["summary"] or {}
            print(f"    steps={rec['n_steps']} trunc={rec['truncated']} "
                  f"closed={rec['closed_think']} "
                  f"answer={rec['answer']} shadow={rec['shadow_answer']}")
            print(f"    agree={s.get('token_agreement')} "
                  f"KL={s.get('mean_logit_kl')} "
                  f"first_div={s.get('first_diverged_step')} "
                  f"tracked={s.get('n_tracked')}/{s.get('n_steps')} "
                  f"({rec['wallclock_s']/60:.1f} min)")

    _phase("roll-up")
    by_cell = {}
    for r in recs:
        by_cell.setdefault(r["cell"], []).append(r)
    for cell, rs in by_cell.items():
        known = [r for r in rs if r["answer_known"]]
        chg = [r for r in known if r["answer_changed"] is not None]
        ag = [r["summary"]["token_agreement"] for r in rs
              if r["summary"] and r["summary"].get("token_agreement") is not None]
        kl = [r["summary"]["mean_logit_kl"] for r in rs
              if r["summary"] and r["summary"].get("mean_logit_kl") is not None]
        print(f"  {cell:22s} n={len(rs):3d} "
              f"closed={sum(1 for r in rs if r['closed_think']):3d} "
              f"answer_known={len(known):3d} "
              f"changed={sum(1 for r in chg if r['answer_changed']):3d} "
              f"agree={np.mean(ag) if ag else float('nan'):.4f} "
              f"KL={np.mean(kl) if kl else float('nan'):.5f}")

    (out_dir / "summary.json").write_text(json.dumps({
        "model": args.model_path, "layer": args.layer,
        "budget": budget, "measure_n": args.measure_n,
        "cells": {c: len(r) for c, r in by_cell.items()},
    }, indent=2, ensure_ascii=False))
    print(f"\n  wrote {out_dir}/measure.json + summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
