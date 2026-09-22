"""Convert qwen3_global.json (8 real Qwen3-1.7B trajectories) into the
`__layers.json` + `index.json` format expected by view_per_layer.html.

This lets the new per-layer viewer show real Qwen3 data without needing
the full numpy + sklearn + scipy stack that build_per_layer.py requires.

Output (in deploy_staging/):
  index.json                        — viewer index
  {tid}__layers.json (×8)           — per-trajectory artifact
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "output" / "qwen3_global.json"
OUT_DIR = Path(__file__).resolve().parents[2] / "deploy_staging"


# ---------------------------------------------------------------------------
# Pure-Python IDW height field (single layer, since qwen3_global has no
# per-layer hidden states — only the final 3D projection)
# ---------------------------------------------------------------------------

def build_terrain(pts, values, grid_n=70, smooth=1.4):
    """Bucket-mean + IDW fill. Same algorithm as build_per_layer.idw_grid,
    but pure Python so it runs without numpy."""
    if not pts:
        return {"grid_n": grid_n, "positions": [0]*(grid_n*grid_n*3),
                "indices": [], "colors": [0]*(grid_n*grid_n*3),
                "scene_scale": 18.0}
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pmin_x, pmax_x = min(xs), max(xs)
    pmin_y, pmax_y = min(ys), max(ys)
    rng_x = (pmax_x - pmin_x) or 1.0
    rng_y = (pmax_y - pmin_y) or 1.0
    pn_x = [(x - pmin_x) / rng_x for x in xs]
    pn_y = [(y - pmin_y) / rng_y for y in ys]

    margin = 0.05
    span = 1.0 + 2 * margin
    coords = [-margin + span * i / (grid_n - 1) for i in range(grid_n)]

    # Snap each point to a cell, then per-cell sums
    cell_sums = [[] for _ in range(grid_n * grid_n)]
    for k in range(len(pts)):
        ci = int(max(0, min(grid_n - 1,
            (pn_x[k] + margin) / span * grid_n)))
        cj = int(max(0, min(grid_n - 1,
            (pn_y[k] + margin) / span * grid_n)))
        cell_sums[cj * grid_n + ci].append(values[k])

    cell_mean = [
        sum(s) / len(s) if s else None for s in cell_sums
    ]

    # Fill empty cells via nearest non-empty neighbour
    filled_idx = [k for k, v in enumerate(cell_mean) if v is not None]
    empty_idx = [k for k, v in enumerate(cell_mean) if v is None]
    for k in empty_idx:
        # find nearest filled
        j, i = divmod(k, grid_n)
        best, bestd = None, 1e18
        for fi in filled_idx:
            fj2, fi2 = divmod(fi, grid_n)
            d = (fj2 - j) ** 2 + (fi2 - i) ** 2
            if d < bestd:
                bestd = d
                best = fi
        if best is not None:
            cell_mean[k] = cell_mean[best]

    z = [v if v is not None else 1.0 for v in cell_mean]
    zmin = min(z)
    zmax = max(z)
    zrange = zmax - zmin or 1.0
    heights = [(zi - zmin) / zrange * 8.0 for zi in z]

    # Colors (height-based)
    colors = []
    for h in heights:
        t = h / 8.0
        if t < 0.5:
            tt = t / 0.5
            r = int(20 + (90 - 20) * tt)
            g = int(80 + (180 - 80) * tt)
            b = int(180 + (200 - 180) * tt)
        else:
            tt = (t - 0.5) / 0.5
            r = int(90 + (240 - 90) * tt)
            g = int(180 + (80 - 180) * tt)
            b = int(200 + (60 - 200) * tt)
        boost = 0.7 + 0.4 * min(1.0, t)
        colors.extend([min(255, int(r * boost)),
                       min(255, int(g * boost)),
                       min(255, int(b * boost))])

    # Positions in scene coords
    scene_scale = 18.0
    positions = []
    for j in range(grid_n):
        for i in range(grid_n):
            x = (coords[i] - 0.5) * scene_scale
            z = (coords[j] - 0.5) * scene_scale
            positions.extend([x, heights[j * grid_n + i], z])

    indices = []
    for j in range(grid_n - 1):
        for i in range(grid_n - 1):
            a = j * grid_n + i
            indices.extend([a, a + 1, a + grid_n,
                            a + 1, a + grid_n + 1, a + grid_n])

    return {
        "grid_n": grid_n,
        "positions": positions,
        "indices": indices,
        "colors": colors,
        "scene_scale": scene_scale,
    }


# ---------------------------------------------------------------------------
# Build per-trajectory artifact
# ---------------------------------------------------------------------------

def build_artifact(run, idx):
    """Convert one run in qwen3_global.json → view_per_layer artifact."""
    frames = [f for f in run["frames"] if f.get("token")]
    n_tokens = len(frames)

    # Use x, z as the 2D projection (we have no per-layer data, only final PCA)
    pts = [[f["x"], f["z"]] for f in frames]
    ppls = [f.get("perplexity") or 1.0 for f in frames]

    # Build a single-layer terrain (since we don't have multi-layer data)
    terrain = build_terrain(pts, ppls, grid_n=70)

    # Synthetic PCA: identity in 2D (already projected)
    pca_mean = [0.0, 0.0]
    pca_components = [1.0, 0.0, 0.0, 1.0]  # 2x2 identity, flattened

    # Tokens (metadata only — viewer uses these for replay)
    tokens = []
    for f in frames:
        tokens.append({
            "step_id": f.get("step_id", -1),
            "token_id": f.get("token_id", -1),
            "token": f.get("token", ""),
            "ppl": f.get("perplexity"),
            "ent": f.get("entropy"),
            "top1_prob": 1.0 / (f.get("perplexity") or 1.0),
            "in_think": False,
            "after_think": False,
        })

    # Trajectory in scene coords (matching terrain scale)
    scene_scale = terrain["scene_scale"]
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    pmin_x = min(xs); pmax_x = max(xs)
    pmin_z = min(zs); pmax_z = max(zs)
    rng_x = (pmax_x - pmin_x) or 1.0
    rng_z = (pmax_z - pmin_z) or 1.0

    # ★ LAND on terrain: bilinear lookup at each (sx, sz)
    margin = 0.05
    span = 1.0 + 2 * margin
    heights_grid = terrain["positions"][2::3]  # y components
    g_n = terrain["grid_n"]

    def h_at(sx, sz):
        u = sx / scene_scale + 0.5
        v = sz / scene_scale + 0.5
        if u < -margin or u > 1 + margin or v < -margin or v > 1 + margin:
            return 0.0
        fi = (u + margin) / span * (g_n - 1)
        fj = (v + margin) / span * (g_n - 1)
        i0 = max(0, min(g_n - 1, int(math.floor(fi))))
        j0 = max(0, min(g_n - 1, int(math.floor(fj))))
        i1 = min(i0 + 1, g_n - 1)
        j1 = min(j0 + 1, g_n - 1)
        di = fi - i0; dj = fj - j0
        h00 = heights_grid[j0 * g_n + i0]
        h01 = heights_grid[j0 * g_n + i1]
        h10 = heights_grid[j1 * g_n + i0]
        h11 = heights_grid[j1 * g_n + i1]
        h0 = h00 * (1 - di) + h01 * di
        h1 = h10 * (1 - di) + h11 * di
        return h0 * (1 - dj) + h1 * dj

    scene_pts = []
    for p in pts:
        sx = ((p[0] - pmin_x) / rng_x - 0.5) * scene_scale
        sz = ((p[1] - pmin_z) / rng_z - 0.5) * scene_scale
        sy = h_at(sx, sz)  # ★ land on terrain
        scene_pts.append([sx, sy, sz])

    tid = f"qwen3_{idx:02d}_{run.get('kind', 'unk')}_{run.get('tag', 'unk')}"

    artifact = {
        "schema_version": "1.0",
        "artifact_kind": "per_layer_v1",
        "trajectory_id": tid,
        "problem_id": run.get("expected", f"q{idx}"),
        "dataset": "qwen3_1p7b_aime_8runs",
        "split": "test",
        "mode": "think" if run.get("tag") == "hard" else "nothink",
        "n_layers": 1,
        "d_model": 2048,
        "n_tokens": n_tokens,
        "ground_truth": run.get("expected", ""),
        "generated_answer": (run.get("generated_text", "") or "")[-50:],
        "is_correct": bool(run.get("correct")),
        "stored_dtype": "fp16",
        "tokens": tokens,
        "scene_pts": scene_pts,  # extra: lands-on-terrain 3D positions
        "layers": [
            {
                "layer_idx": 0,
                "pca_mean": pca_mean,
                "pca_components": pca_components,
                "proj_2d": [v for p in pts for v in p],
                "ppl_mean": float(sum(ppls) / len(ppls)),
                "ppl_max": float(max(ppls)),
                "terrain": terrain,
            }
        ],
    }
    return tid, artifact


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SOURCE.exists():
        print(f"  missing source: {SOURCE}")
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"loading {SOURCE}")
    with open(SOURCE) as f:
        data = json.load(f)

    items = []
    for i, run in enumerate(data):
        tid, artifact = build_artifact(run, i)
        out_path = OUT_DIR / f"{tid}__layers.json"
        out_path.write_text(json.dumps(artifact, ensure_ascii=False),
                            encoding="utf-8")
        items.append({
            "trajectory_id": tid,
            "problem_id": artifact["problem_id"],
            "dataset": artifact["dataset"],
            "split": artifact["split"],
            "mode": artifact["mode"],
            "n_tokens": artifact["n_tokens"],
            "n_layers": artifact["n_layers"],
            "is_correct": artifact["is_correct"],
        })
        print(f"  ✓ {tid}  ({artifact['n_tokens']} tokens, "
              f"{'correct' if artifact['is_correct'] else 'wrong'})")

    index = {"n_artifacts": len(items), "items": items}
    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nwrote {len(items)} artifacts + index.json to {OUT_DIR}")


if __name__ == "__main__":
    main()