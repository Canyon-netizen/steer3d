"""Drive Qwen3-1.7B once, capturing raw hidden states.

We use a SINGLE global projector trained across ALL prompts so that
the 2D positions of every prompt's tokens live in the SAME coordinate
system. That's what makes a unified terrain map possible.

Output: ``output/qwen3_global.json`` with raw 2048-dim hidden states
projected to (x, y, z) using a global PCA.

Then ``build_terrain.py`` consumes that to build the terrain mesh.
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

# Same prompts as run_qwen3_real.py
sys.path.insert(0, str(HERE))
from run_qwen3_real import PROMPTS  # noqa: E402


def make_runner():
    from core.model_runner import qwen3_1p7b_runner
    return qwen3_1p7b_runner()


# Collect raw hidden states globally so we can fit a single PCA on them all.
GLOBAL_HIDDEN: list[np.ndarray] = []


class GlobalCollector:
    def __init__(self):
        self.frames = []  # store tokens, ppl, entropy, step, etc.

    def __call__(self, frame):
        raw = getattr(frame, "_raw_hidden", None)
        if raw is not None and not getattr(frame, "_is_end", False):
            GLOBAL_HIDDEN.append(np.asarray(raw, dtype=np.float32))
            self.frames.append(frame)
        elif not getattr(frame, "_is_end", False):
            self.frames.append(frame)


def _parse(frames):
    out = []
    for f in frames:
        if getattr(f, "_is_end", False):
            continue
        out.append({
            "ts": f.ts,
            "step_id": f.step_id,
            "token": f.token,
            "token_id": f.token_id,
            "perplexity": f.perplexity,
            "entropy": f.entropy,
            "is_self_check": f.is_self_check,
            "is_revisit": f.is_revisit,
        })
    return out


async def run_one(runner, item, layer=14, max_tokens=64):
    collector = GlobalCollector()
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
        "frames": _parse(collector.frames),
        "generated_text": full_text,
        "wallclock_s": dt,
        "n_tokens": sum(1 for f in collector.frames if f.token),
        "layer": layer,
    }


def fit_global_pca(d_model: int, target_dim: int = 3):
    """Fit a single batch PCA on every hidden state from every prompt.

    We snapshot the raw vectors, mean-center them, then SVD once. This
    gives a stable global coordinate frame across all prompts.
    """
    arr = np.stack(GLOBAL_HIDDEN, axis=0).astype(np.float64)  # (N, d)
    mean = arr.mean(axis=0)
    X = arr - mean
    # Add tiny jitter for numerical stability
    X += 1e-5 * np.random.standard_normal(X.shape)
    # SVD: principal axes are rows of Vt[:k]
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    components = Vt[:target_dim].T  # (d, k)
    return mean, components


class GlobalProjector:
    """Snapshot of a fitted PCA: project any vector to 3-D."""
    def __init__(self, mean, components):
        self.mean = mean
        self.components = components  # (d, k)

    def project(self, x):
        x = np.asarray(x, dtype=np.float64).reshape(-1)
        xc = x - self.mean
        c = self.components.T @ xc
        return c  # length k


async def main_async(args):
    runner = make_runner()
    print(f"[global] runner={type(runner).__name__} d_model={runner.d_model}")

    # Phase 1 — gather raw hidden states from all prompts
    results = []
    for i, item in enumerate(PROMPTS):
        print(f"\n[{i+1}/{len(PROMPTS)}] tag={item['tag']:>4s} kind={item['kind']:>11s}")
        res = await run_one(runner, item, layer=args.layer, max_tokens=args.max_tokens)
        gen = res["generated_text"].strip().lower()
        exp = (item.get("expected") or "").strip().lower()
        res["correct"] = bool(exp) and (exp in gen[:40])
        print(f"      gen: {gen[:100]!r}{'…' if len(gen) > 100 else ''}")
        print(f"      expected: {exp!r}  correct={res['correct']}  "
              f"tokens={res['n_tokens']}  wallclock={res['wallclock_s']:.2f}s")
        results.append(res)

    print(f"\n[global] collected {len(GLOBAL_HIDDEN)} hidden states")

    # Phase 2 — fit global PCA
    mean, components = fit_global_pca(runner.d_model, target_dim=3)
    proj = GlobalProjector(mean, components)

    # Phase 3 — project each frame's hidden state to (x, y, z) using global PCA
    idx = 0
    for res in results:
        for f in res["frames"]:
            v = GLOBAL_HIDDEN[idx]; idx += 1
            c = proj.project(v.astype(np.float64))
            f["x"] = float(c[0]); f["y"] = float(c[1]); f["z"] = float(c[2])

    # Save
    out_dir = HERE / "output"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "qwen3_global.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nSaved -> {out_file}  ({len(results)} prompts, {idx} tokens projected)")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", type=int, default=14)
    ap.add_argument("--max-tokens", type=int, default=64)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
