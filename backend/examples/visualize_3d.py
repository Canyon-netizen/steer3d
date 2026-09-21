"""Render the Qwen3-1.7B reasoning trajectories as 3-D plots.

Reads ``backend/examples/output/qwen3_1p7b_runs.json`` (produced by
``run_qwen3_real.py``) and writes three artefacts under
``backend/examples/output/``:

  1. ``trajectories_3d.png``        — single static 3-D scatter
  2. ``trajectories_grid.png``      — 2x4 small-multiple grid, one per prompt
  3. ``trajectories_anim.gif``      — animated growing trajectory (bonus)

Color encodes tag (easy / hard) and correctness (✓ / ✗). Per-token
perplexity controls marker size — confident tokens get small dots,
uncertain tokens get larger ones (helps locate "self-check"
moments).
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers 3-D projection)
import numpy as np

HERE = Path(__file__).resolve().parent
JSON_PATH = HERE / "output" / "qwen3_1p7b_runs.json"


def load_runs():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def color_for(run):
    """(tag, correct) -> RGB color."""
    tag = run["tag"]
    correct = run.get("correct", False)
    if tag == "easy" and correct:
        return (0.20, 0.65, 0.30, 0.85)   # green
    if tag == "easy" and not correct:
        return (0.95, 0.65, 0.10, 0.85)   # orange
    if tag == "hard" and correct:
        return (0.15, 0.45, 0.85, 0.85)   # blue  (very rare!)
    return (0.85, 0.20, 0.25, 0.85)       # red


def plot_single_overview(runs, out_path):
    """All trajectories on one 3-D scatter."""
    fig = plt.figure(figsize=(11, 8.5))
    ax = fig.add_subplot(111, projection="3d")

    for run in runs:
        frames = [f for f in run["frames"] if f["step_id"] >= 0]
        if len(frames) < 2:
            continue
        xs = np.array([f["x"] for f in frames])
        ys = np.array([f["y"] for f in frames])
        zs = np.array([f["z"] for f in frames])
        ppl = np.array([f["perplexity"] or 1.0 for f in frames])
        # Larger perplexity -> larger dot
        sizes = 8 + 28 * np.clip((ppl - 1.0) / 6.0, 0, 1)
        col = color_for(run)
        ax.plot(xs, ys, zs, color=col[:3], linewidth=1.4, alpha=0.55)
        ax.scatter(xs, ys, zs, s=sizes, c=[col[:3]], edgecolors="black",
                   linewidths=0.25, alpha=0.85)

        # mark the first & last token
        ax.scatter([xs[0]], [ys[0]], [zs[0]], s=70, marker="o",
                   c=[col[:3]], edgecolors="black", linewidths=1.0)
        ax.scatter([xs[-1]], [ys[-1]], [zs[-1]], s=120, marker="*",
                   c=[col[:3]], edgecolors="black", linewidths=1.0)

    ax.set_xlabel("PC 1")
    ax.set_ylabel("PC 2")
    ax.set_zlabel("PC 3")
    ax.set_title(
        "Qwen3-1.7B reasoning trajectories (layer 14)\n"
        "green = easy ✓, blue = hard ✓, orange = easy ✗, red = hard ✗",
        fontsize=11,
    )

    # Legend
    handles = [
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=(0.20, 0.65, 0.30),
                   markersize=10, label='easy ✓'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=(0.95, 0.65, 0.10),
                   markersize=10, label='easy ✗'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=(0.85, 0.20, 0.25),
                   markersize=10, label='hard ✗'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=(0.15, 0.45, 0.85),
                   markersize=10, label='hard ✓'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='gray',
                   markersize=10, label='● start'),
        plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='gray',
                   markersize=14, label='★ end'),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=9, framealpha=0.92)

    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_grid(runs, out_path):
    """One small subplot per prompt."""
    n = len(runs)
    cols = 4
    rows = math.ceil(n / cols)
    fig = plt.figure(figsize=(4.3 * cols, 4.0 * rows))
    for i, run in enumerate(runs):
        ax = fig.add_subplot(rows, cols, i + 1, projection="3d")
        frames = [f for f in run["frames"] if f["step_id"] >= 0]
        if len(frames) < 2:
            continue
        xs = np.array([f["x"] for f in frames])
        ys = np.array([f["y"] for f in frames])
        zs = np.array([f["z"] for f in frames])
        ppl = np.array([f["perplexity"] or 1.0 for f in frames])
        sizes = 6 + 22 * np.clip((ppl - 1.0) / 6.0, 0, 1)
        col = color_for(run)
        ax.plot(xs, ys, zs, color=col[:3], linewidth=1.1, alpha=0.65)
        ax.scatter(xs, ys, zs, s=sizes, c=[col[:3]], edgecolors="black",
                   linewidths=0.15, alpha=0.85)

        tag = run["tag"]
        kind = run["kind"]
        ok = "✓" if run["correct"] else "✗"
        ax.set_title(f"{tag} {ok} · {kind}", fontsize=9.5)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])

    fig.suptitle("Per-prompt reasoning trajectories (Qwen3-1.7B layer 14)",
                 fontsize=13, y=1.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_anim(runs, out_path, fps=10):
    """Build a small gif that shows trajectories growing."""
    try:
        import matplotlib.animation as animation
    except ImportError:
        print("[anim] matplotlib.animation not available, skipping")
        return

    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection="3d")

    max_len = max(len([f for f in r["frames"] if f["step_id"] >= 0]) for r in runs)
    lines = []
    scatters = []
    for run in runs:
        col = color_for(run)
        line, = ax.plot([], [], [], color=col[:3], linewidth=1.4, alpha=0.8)
        scat = ax.scatter([], [], [], s=[], c=[col[:3]], alpha=0.85)
        lines.append((line, run))
        scatters.append((scat, run))

    ax.set_xlim(-15, 15); ax.set_ylim(-15, 15); ax.set_zlim(-15, 15)
    ax.set_title("Qwen3-1.7B live reasoning trace", fontsize=11)

    def update(t):
        artists = []
        for (line, run), (scat, _) in zip(lines, scatters):
            frames = [f for f in run["frames"] if f["step_id"] >= 0]
            cut = min(t + 1, len(frames))
            xs = [f["x"] for f in frames[:cut]]
            ys = [f["y"] for f in frames[:cut]]
            zs = [f["z"] for f in frames[:cut]]
            line.set_data(xs, ys)
            line.set_3d_properties(zs)
            ppl = np.array([f["perplexity"] or 1.0 for f in frames[:cut]])
            sizes = 6 + 22 * np.clip((ppl - 1.0) / 6.0, 0, 1)
            scat._offsets3d = (xs, ys, zs)
            scat.set_sizes(sizes.tolist())
            artists.append(line)
        ax.set_title(f"step {t+1}/{max_len}", fontsize=11)
        return artists

    anim = animation.FuncAnimation(fig, update, frames=max_len,
                                   interval=1000 // fps, blit=False)
    anim.save(out_path, writer="pillow", fps=fps)
    plt.close(fig)


def plot_pca_angle_signal(runs, out_path):
    """For each prompt, plot (x,y,z) over step_id — a quick 'shape' signal."""
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    comps = ["x", "y", "z"]
    for r in runs:
        frames = [f for f in r["frames"] if f["step_id"] >= 0]
        if not frames:
            continue
        steps = [f["step_id"] for f in frames]
        col = color_for(r)
        for ax, c in zip(axes, comps):
            ax.plot(steps, [f[c] for f in frames], color=col[:3], alpha=0.7,
                    linewidth=1.0,
                    label=f"{r['tag']} {r['kind']} ({'✓' if r['correct'] else '✗'})")
        # break — labels plot one line per run, axes[0] only
    axes[0].set_ylabel("PC 1")
    axes[1].set_ylabel("PC 2")
    axes[2].set_ylabel("PC 3")
    axes[2].set_xlabel("token step")
    axes[0].legend(loc="upper right", fontsize=7, ncol=2)
    axes[0].set_title("Per-coordinate trajectory over token steps (Qwen3-1.7B layer 14)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    runs = load_runs()
    out_dir = JSON_PATH.parent
    print(f"[viz] loaded {len(runs)} runs")

    p1 = out_dir / "trajectories_3d.png"
    p2 = out_dir / "trajectories_grid.png"
    p3 = out_dir / "trajectories_pca_signal.png"
    p4 = out_dir / "trajectories_anim.gif"

    print(f"[viz] writing {p1}")
    plot_single_overview(runs, p1)

    print(f"[viz] writing {p2}")
    plot_grid(runs, p2)

    print(f"[viz] writing {p3}")
    plot_pca_angle_signal(runs, p3)

    print(f"[viz] writing {p4}")
    plot_anim(runs, p4, fps=12)

    print("[viz] done")


if __name__ == "__main__":
    main()