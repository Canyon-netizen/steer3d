"""Static 2x2 summary figure for the steering design report.

Matplotlib is imported lazily so the report builder stays usable in
environments without it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


def render_figure(report: Mapping[str, Any], out_path: Path) -> Path:
    root = Path(__file__).resolve().parents[2]
    cache = root / ".cache/mpl"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    fig.suptitle("Steering design guide: readout is positive, control effect is negative", fontsize=12)

    # --- layer support -----------------------------------------------------
    ax = axes[0, 0]
    layers = report["layers"]
    ys = np.arange(len(layers))
    support = [float(row["support"]) for row in layers]
    colors = ["#fb7185" if row["action"] == "supporting" else "#2dd4bf" if row["action"] == "compensating" else "#94a3b8" for row in layers]
    ax.barh(ys, support, color=colors)
    ax.set_yticks(ys)
    ax.set_yticklabels([str(row["layer"]) for row in layers])
    ax.axvline(0, color="#334155", lw=1)
    ax.set_title("Layer support = -(block + restore) / 2")
    ax.set_xlabel("positive = with the net (+v) effect; negative = compensating")
    span = max(max(support), 0.0) - min(min(support), 0.0)
    pad = 0.22 * max(span, 0.01)
    ax.set_xlim(min(min(support), 0.0) - pad, max(max(support), 0.0) + pad)
    offset = 0.012 * max(span, 0.01)
    for y, value in zip(ys, support):
        ax.text(value + (offset if value >= 0 else -offset), y, "%+.3f" % value,
                va="center", ha="left" if value >= 0 else "right", fontsize=8)
    ax.invert_yaxis()

    # --- dose / direction --------------------------------------------------
    ax = axes[0, 1]
    plus = report["dose"]["w+"]
    minus = report["dose"]["w-"]
    xs = [float(row["dose"]) for row in plus]
    ax.plot(xs, [float(row["mean"]) for row in plus], "o-", color="#fb7185", label="+v")
    ax.plot(xs, [float(row["mean"]) for row in minus], "o-", color="#2dd4bf", label="-v")
    ax.axhline(float(report["dose"]["random_primary"]), color="#a78bfa", ls="--", lw=1, label="random (primary)")
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xlabel("dose (fraction of input norm)")
    ax.set_ylabel("score change (correct - incorrect)")
    ax.set_title("Dose / direction")
    ax.legend(fontsize=8)

    # --- logit lens --------------------------------------------------------
    ax = axes[1, 0]
    values = [float(value) for value in report["readout"]["logit_lens"]["per_layer_mean_p_final"]]
    ax.plot(range(len(values)), values, color="#60a5fa", lw=2)
    ax.axvline(18, color="#fbbf24", ls="--", lw=1)
    ax.set_xlabel("layer")
    ax.set_ylabel("mean p(final token)")
    ax.set_title("Logit lens: answer information emerges late")
    ax.text(18, max(values) * 0.55, " layer 18", color="#b45309", fontsize=8)

    # --- marker readout ----------------------------------------------------
    ax = axes[1, 1]
    markers = report["readout"]["marker"]["per_id"]
    ids = [str(marker["id"]) for marker in markers]
    dots = [float(marker["dot"]) for marker in markers]
    ax.bar(ids, dots, color="#2dd4bf")
    ax.set_title("Static readout w.U per marker id")
    ax.set_ylabel("w.U")
    ax.tick_params(axis="x", rotation=45)
    for index, value in enumerate(dots):
        ax.text(index, value + 0.002, "%+.3f" % value, ha="center", fontsize=8)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path

