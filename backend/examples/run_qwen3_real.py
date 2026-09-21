"""Drive the Reasoning3D pipeline with the real Qwen3-1.7B model.

This script does not require the frontend — it loads Qwen3-1.7B,
runs several prompts (some easy, some that 1.7B gets wrong), and
saves the per-token hidden-state trajectory + rendered text to a
JSON file under ``backend/examples/output/``.

Each prompt is labeled with an expected category (easy / hard /
math / common-sense) so you can see whether the 3-D path shape
correlates with correctness.

Usage:
    python examples/run_qwen3_real.py

The script prints a summary at the end; the JSON file is ready to
be loaded by ``visualize_3d.py`` (the matplotlib 3-D scatter).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import numpy as np

# ---- prompts --------------------------------------------------------------
# Each prompt carries:
#   prompt  : the input text
#   tag     : 'easy' or 'hard' — labels whether Qwen3-1.7B typically
#              gets this right vs wrong. (Calibrated from public benchmarks.)
#   kind    : 'math' | 'commonsense' | 'fact' | 'reasoning'
#
# Sources for the calibration:
#   * GSM8K-style arithmetic where 1.7B has ~35-50% pass@1
#   * TriviaQA-style factual recall where 1.7B has ~30%
#   * HellaSwag-style commonsense where 1.7B has ~55%
#   * Simple definitions where 1.7B has ~95%

PROMPTS = [
    # ---- easy (model gets right) ------------------------------------------
    {
        "prompt": "What is the capital of France? Answer with one word.",
        "tag": "easy",
        "kind": "fact",
        "expected": "Paris",
    },
    {
        "prompt": "The cat is sitting on the ___. Fill the blank with one word.",
        "tag": "easy",
        "kind": "commonsense",
        "expected": "mat",
    },
    {
        "prompt": "Question: 2 + 2 = ? Answer with one number.\nAnswer:",
        "tag": "easy",
        "kind": "math",
        "expected": "4",
    },

    # ---- hard (model typically gets wrong) --------------------------------
    {
        "prompt": (
            "A bakery sells cupcakes at $3 each and cookies at $2 each. "
            "Yesterday they sold 12 cupcakes and 18 cookies. How much "
            "revenue did they make from cookies? Answer with a number."
        ),
        "tag": "hard",
        "kind": "math",
        "expected": "36",
    },
    {
        "prompt": (
            "If you have 3 boxes, each containing 4 bags, and each bag "
            "has 5 candies, how many candies do you have in total? "
            "Answer with one number."
        ),
        "tag": "hard",
        "kind": "math",
        "expected": "60",
    },
    {
        "prompt": (
            "A train leaves station A at 9:00 AM traveling at 60 km/h. "
            "Another train leaves station B (300 km away) at 10:00 AM "
            "traveling toward A at 90 km/h. At what time do they meet? "
            "Answer with HH:MM."
        ),
        "tag": "hard",
        "kind": "math",
        "expected": "12:00",
    },

    # ---- reasoning (medium difficulty) -----------------------------------
    {
        "prompt": (
            "If all roses are flowers and some flowers fade quickly, "
            "can we conclude that some roses fade quickly?"
        ),
        "tag": "hard",
        "kind": "reasoning",
        "expected": "no",
    },
    {
        "prompt": (
            "A is taller than B. B is taller than C. C is taller than D. "
            "Who is the shortest? Answer with one letter."
        ),
        "tag": "easy",
        "kind": "reasoning",
        "expected": "D",
    },
]


# ---- core runner -----------------------------------------------------------

def make_runner():
    """Build a Qwen3-1.7B runner. Lazily loads the model once."""
    from core.model_runner import qwen3_1p7b_runner
    return qwen3_1p7b_runner()


class FrameCollector:
    """Adapter that hands a Frame to the projector (OnlinePCA) and stores it."""

    def __init__(self, projector):
        self.projector = projector
        self.frames = []

    def __call__(self, frame):
        raw = getattr(frame, "_raw_hidden", None)
        if raw is not None and not getattr(frame, "_is_end", False):
            p = self.projector.update(np.asarray(raw, dtype=np.float64))
            frame.point.x = float(p.x)
            frame.point.y = float(p.y)
            frame.point.z = float(p.z)
        self.frames.append(frame)


def _parse_frames(frames):
    out = []
    for f in frames:
        if getattr(f, "_is_end", False):
            continue
        out.append({
            "ts": f.ts,
            "step_id": f.step_id,
            "token": f.token,
            "token_id": f.token_id,
            "x": f.point.x,
            "y": f.point.y,
            "z": f.point.z,
            "perplexity": f.perplexity,
            "entropy": f.entropy,
            "is_self_check": f.is_self_check,
            "is_revisit": f.is_revisit,
        })
    return out


async def run_one(runner, projector, item, layer=14, max_tokens=64):
    """Run one prompt through Qwen3-1.7B, return collected frames."""
    from core.model_runner import _SyntheticState  # noqa
    from core.projector import OnlinePCA

    # Fresh projector per prompt so trajectories don't bleed into each other
    local_p = OnlinePCA(d=runner.d_model, target_dim=3, window=256)

    collector = FrameCollector(local_p)
    state = {"paused": False, "cancelled": False, "speed": 1.0}

    def is_paused(): return state["paused"]
    def is_cancelled(): return state["cancelled"]
    def get_speed(): return state["speed"]

    t0 = time.time()
    await runner.stream(
        prompt=item["prompt"],
        layer=layer,
        on_frame=collector,
        is_paused=is_paused,
        is_cancelled=is_cancelled,
        set_speed=get_speed,
        inject_vector=None,
    )
    dt = time.time() - t0

    full_text = "".join(f.token for f in collector.frames if f.token)
    return {
        **item,
        "frames": _parse_frames(collector.frames),
        "generated_text": full_text,
        "wallclock_s": dt,
        "n_tokens": sum(1 for f in collector.frames if f.token),
        "layer": layer,
    }


async def main_async(args):
    runner = make_runner()
    print(f"[run] using runner={type(runner).__name__} d_model={runner.d_model}")

    # A single projector for the whole session (so we *can* compare across
    # prompts if needed, but for this script we keep each prompt independent).
    from core.projector import OnlinePCA
    projector = OnlinePCA(d=runner.d_model, target_dim=3, window=256)

    results = []
    for i, item in enumerate(PROMPTS):
        print(f"\n[{i+1}/{len(PROMPTS)}] tag={item['tag']:>4s} kind={item['kind']:>11s} | "
              f"prompt={item['prompt'][:70]!r}{'…' if len(item['prompt']) > 70 else ''}")
        res = await run_one(runner, projector, item, layer=args.layer, max_tokens=args.max_tokens)
        # Heuristic correctness: case-insensitive substring match
        gen = res["generated_text"].strip().lower()
        exp = (item.get("expected") or "").strip().lower()
        res["correct"] = bool(exp) and (exp in gen[:40])
        print(f"      gen   : {gen[:120]!r}{'…' if len(gen) > 120 else ''}")
        print(f"      expect: {exp!r}   correct={res['correct']}  "
              f"tokens={res['n_tokens']}  wallclock={res['wallclock_s']:.2f}s")
        results.append(res)

    # Save
    out_dir = HERE / "output"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "qwen3_1p7b_runs.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    by_tag = {"easy": [], "hard": []}
    for r in results:
        by_tag.setdefault(r["tag"], []).append(r)
    for tag in ("easy", "hard"):
        bucket = by_tag.get(tag, [])
        if not bucket:
            continue
        n_correct = sum(1 for r in bucket if r["correct"])
        avg_tokens = np.mean([r["n_tokens"] for r in bucket]) if bucket else 0
        print(f"  {tag:>4s}: {n_correct}/{len(bucket)} correct, "
              f"avg {avg_tokens:.1f} tokens")
    print(f"\nSaved {len(results)} prompts -> {out_file}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", type=int, default=14)
    ap.add_argument("--max-tokens", type=int, default=64)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()