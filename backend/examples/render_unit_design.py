#!/usr/bin/env python3
"""Render the unit-basis design curve from unit_design.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments/unit_design_v1/unit_design.json"
OUT = ROOT / "experiments/unit_design_v1/unit_design.png"
COLORS = {"7196": "#fb7185", "10061": "#60a5fa", "6771": "#2dd4bf"}


def main() -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    markers = list(data["markers"])
    k_grid = data["k_grid"]
    cache = ROOT / ".cache/mpl"
    cache.mkdir(parents=True, exist_ok=True)
    matplotlib.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2), constrained_layout=True)

    ax = axes[0]
    for marker in markers:
        entry = data["markers"][marker]
        ax.plot(k_grid, [entry["reconstruction_cos"][str(k)] for k in k_grid], marker="o", color=COLORS.get(marker), label="marker " + marker)
    ax.axhline(0.9, color="#94a3b8", ls="--", lw=1, label="0.90 reconstruction")
    ax.set_xscale("log")
    ax.set_xlabel("k units (log)")
    ax.set_ylabel("cos(reconstruction, mean g)")
    ax.set_title("native unit basis: reconstruction")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)

    ax = axes[1]
    for marker in markers:
        entry = data["markers"][marker]
        delta = [next(row for row in entry["curve"] if row["k"] == k)["rows"]["0.02"]["mean_delta_logp"] for k in k_grid]
        ax.plot(k_grid, delta, marker="o", color=COLORS.get(marker), label="unit_k " + marker)
        base = entry["baselines"]["mean_g"]["0.02"]["mean_delta_logp"]
        ax.axhline(base, color=COLORS.get(marker), ls=":", lw=1.2)
    ax.set_xscale("log")
    ax.set_xlabel("k units (log)")
    ax.set_ylabel("held-out delta log p @ dose 0.02")
    ax.set_title("effect vs sparsity (dotted = mean g)")
    ax.grid(alpha=0.2)

    ax = axes[2]
    for marker in markers:
        entry = data["markers"][marker]
        kl = [next(row for row in entry["curve"] if row["k"] == k)["rows"]["0.02"]["mean_kl"] for k in k_grid]
        ax.plot(k_grid, kl, marker="o", color=COLORS.get(marker), label="unit_k " + marker)
        base = entry["baselines"]["mean_g"]["0.02"]["mean_kl"]
        ax.axhline(base, color=COLORS.get(marker), ls=":", lw=1.2)
    ax.axhline(data["kl_budget"], color="#94a3b8", ls="--", lw=1, label="KL budget")
    ax.set_xscale("log")
    ax.set_xlabel("k units (log)")
    ax.set_ylabel("held-out KL @ dose 0.02")
    ax.set_title("side effect vs sparsity")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)

    fig.suptitle("Unit-basis steering design: how many native units are needed?", fontsize=14)
    fig.savefig(OUT, dpi=170)
    print("[ok]", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

