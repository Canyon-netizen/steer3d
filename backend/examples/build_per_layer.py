"""Precompute per-layer PCA / terrain / trajectory-projection artifacts.

For every trajectory in a root directory this script writes a sibling
``__layers.json`` file containing, **for each of the 28 layers**:

  * the fitted 2-component PCA (mean + components) so the viewer can
    re-project if needed
  * the (T, 2) projection of every generated token at that layer
  * an IDW-interpolated terrain mesh whose height at each grid cell
    is the perplexity of the nearest tokens

This is the "importable artifact" used by ``view_per_layer.html``.
The viewer never has to read the raw ``.npz`` files — it just fetches
these lightweight JSONs.

Usage::

    python examples/build_per_layer.py --root datasets/aime_qwen3_1p7b_16k_fp16
    python examples/build_per_layer.py --root datasets/aime_qwen3_1p7b_32k_fp32 \
        --cache-dir datasets/aime_qwen3_1p7b_32k_fp32/viewer_cache
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.standard import TrajectoryDataset


# ---------------------------------------------------------------------------
# IDW terrain (same algorithm as build_multilayer_viewer.make_grid_payload)
# ---------------------------------------------------------------------------


def idw_grid(pts: np.ndarray, values: np.ndarray, grid_n: int = 70,
             smooth: float = 1.4) -> dict:
    """Build a height-map from (pts, values) using bucketed mean + IDW
    refinement.

    Algorithm:
      1. Quantise pts to grid cells (one pass, O(T)).
      2. Compute per-cell mean of values (terrain base).
      3. For empty cells, fill by IDW from the nearest non-empty cell.

    For T ≤ 2048 and grid_n ≤ 70 this runs in <0.1s per layer, vs >80s
    for the naive IDW broadcast.
    """
    pmin = pts.min(axis=0)
    pmax = pts.max(axis=0)
    rng = pmax - pmin
    rng[rng == 0] = 1.0
    pn = (pts - pmin) / rng
    margin = 0.05
    coords = np.linspace(-margin, 1 + margin, grid_n)
    gx, gy = np.meshgrid(coords, coords)

    # Snap each point to a grid cell (with margin)
    cell = np.clip((pn + margin) / (1 + 2 * margin) * grid_n, 0, grid_n - 1).astype(np.int32)
    ci = np.minimum(cell[:, 0], grid_n - 1)
    cj = np.minimum(cell[:, 1], grid_n - 1)
    flat = cj * grid_n + ci

    # Per-cell mean and count
    sums = np.zeros(grid_n * grid_n, dtype=np.float64)
    counts = np.zeros(grid_n * grid_n, dtype=np.int64)
    np.add.at(sums, flat, values)
    np.add.at(counts, flat, 1)

    filled = counts > 0
    z = np.where(filled, sums / np.maximum(counts, 1), 0.0).reshape(grid_n, grid_n)

    # Fill empty cells via nearest non-empty neighbour using KDTree.
    empty = ~filled.reshape(grid_n, grid_n)
    if empty.any():
        from scipy.spatial import cKDTree
        filled_idx = np.argwhere(filled.reshape(grid_n, grid_n))
        empty_idx = np.argwhere(empty)
        tree = cKDTree(filled_idx)
        _, nearest = tree.query(empty_idx)
        z[empty_idx[:, 0], empty_idx[:, 1]] = z[
            filled_idx[nearest, 0], filled_idx[nearest, 1]
        ]

    ppl_clip = float(np.percentile(values, 95))
    z_clip = np.clip(z, 1.0, ppl_clip)
    z_log = np.log1p(z_clip - 1.0)
    z_log -= z_log.min()
    z_log /= (z_log.max() + 1e-6)
    heights = (z_log * 8.0).astype(np.float32)

    # Colours by height
    colors = np.zeros((grid_n * grid_n, 3), dtype=np.uint8)
    for j in range(grid_n):
        for i in range(grid_n):
            t = float(heights[j, i] / 8.0)
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
            colors[j * grid_n + i] = (
                min(255, int(r * boost)),
                min(255, int(g * boost)),
                min(255, int(b * boost)),
            )

    # Vertex positions in scene space (x, y, z)
    positions = np.zeros((grid_n * grid_n, 3), dtype=np.float32)
    scene_scale = 18.0
    for j in range(grid_n):
        for i in range(grid_n):
            x, y = gx[j, i], gy[j, i]
            positions[j * grid_n + i] = [
                (x - 0.5) * scene_scale,
                float(heights[j, i]),
                (y - 0.5) * scene_scale,
            ]

    # Triangle indices (two triangles per quad)
    indices = []
    for j in range(grid_n - 1):
        for i in range(grid_n - 1):
            a = j * grid_n + i
            indices.extend([a, a + 1, a + grid_n,
                            a + 1, a + grid_n + 1, a + grid_n])

    return {
        "grid_n": grid_n,
        "positions": positions.reshape(-1).tolist(),
        "indices": indices,
        "colors": colors.reshape(-1).tolist(),
        "scene_scale": scene_scale,
    }


# ---------------------------------------------------------------------------
# Build one trajectory's per-layer artifact
# ---------------------------------------------------------------------------


def build_artifact(traj, grid_n: int = 70) -> Dict:
    """Compute 28 (pca + terrain + proj) bundles for one trajectory."""
    from sklearn.decomposition import PCA

    hs = traj.hidden_states            # (T, L, D)
    T, L, D = hs.shape
    ppl = np.array([r.perplexity or 1.0 for r in traj.meta.tokens],
                   dtype=np.float32)

    # Pick a fast SVD solver when T (number of tokens) is large.
    # Full SVD on a 2048×2048 matrix takes ~30s per layer; randomized
    # gives the same 2-D projection in <1s with negligible error.
    if T >= 800:
        solver = "randomized"
        svd_solver_kw = {"n_oversamples": 10}
    else:
        solver = "auto"
        svd_solver_kw = {}

    layers_out: List[Dict] = []
    for li in range(L):
        v = hs[:, li, :].astype(np.float32)        # (T, D)
        if v.shape[0] < 2:
            layers_out.append({"layer_idx": li, "empty": True})
            continue
        pca = PCA(n_components=2, svd_solver=solver, **svd_solver_kw)
        proj = pca.fit_transform(v).astype(np.float32)   # (T, 2)
        terrain = idw_grid(proj, ppl, grid_n=grid_n)
        layers_out.append({
            "layer_idx": li,
            "pca_mean": pca.mean_.astype(np.float32).tolist(),
            "pca_components": pca.components_.astype(np.float32).reshape(-1).tolist(),
            "proj_2d": proj.reshape(-1).tolist(),
            "ppl_mean": float(ppl.mean()),
            "ppl_max": float(ppl.max()),
            "terrain": terrain,
        })

    tokens = [{
        "step_id": r.step_id,
        "token_id": r.token_id,
        "token": r.token,
        "ppl": r.perplexity,
        "ent": r.entropy,
        "top1_prob": r.top1_prob,
        "in_think": r.is_in_think_block,
        "after_think": r.is_after_think,
    } for r in traj.meta.tokens]

    return {
        "schema_version": "1.0",
        "artifact_kind": "per_layer_v1",
        "trajectory_id": traj.meta.trajectory_id,
        "problem_id": traj.meta.problem_id,
        "dataset": traj.meta.dataset,
        "split": traj.meta.split,
        "mode": traj.mode,
        "n_layers": L,
        "d_model": D,
        "n_tokens": T,
        "ground_truth": traj.meta.ground_truth,
        "generated_answer": traj.meta.generated_answer,
        "is_correct": traj.is_correct,
        "stored_dtype": traj.stored_dtype,
        "tokens": tokens,
        "layers": layers_out,
    }


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


def build_index(cache_dir: Path) -> Dict:
    """Scan cache_dir and produce an index of all artifacts."""
    items = []
    for jp in sorted(cache_dir.glob("*__layers.json")):
        try:
            d = json.loads(jp.read_text())
            items.append({
                "trajectory_id": d["trajectory_id"],
                "problem_id": d["problem_id"],
                "dataset": d.get("dataset", ""),
                "split": d.get("split", ""),
                "mode": d.get("mode", ""),
                "n_tokens": d.get("n_tokens", 0),
                "n_layers": d.get("n_layers", 0),
                "is_correct": d.get("is_correct"),
                "filename": jp.name,
            })
        except Exception as e:
            print(f"[skip] {jp.name}: {e}")
    return {
        "schema_version": "1.0",
        "n_artifacts": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True,
                    help="Directory holding *.json + *.npz trajectories")
    ap.add_argument("--cache-dir", default=None,
                    help="Where to write __layers.json + index.json "
                         "(default: <root>/../viewer_cache/<root.name>)")
    ap.add_argument("--grid-n", type=int, default=70)
    ap.add_argument("--limit", type=int, default=None,
                    help="Process at most N trajectories (smoke test)")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"root does not exist: {root}")

    cache_dir = (Path(args.cache_dir) if args.cache_dir
                 else root.parent / "viewer_cache" / root.name)
    cache_dir.mkdir(parents=True, exist_ok=True)

    ds = TrajectoryDataset(root)
    ids = ds.ids()
    if args.limit:
        ids = ids[:args.limit]
    print(f"[per-layer] root={root}  cache={cache_dir}  n={len(ids)}")

    n_ok = 0
    n_skip = 0
    for tid in ids:
        out_path = cache_dir / f"{tid}__layers.json"
        if out_path.exists() and not args.overwrite:
            print(f"  · {tid}: SKIP (exists)")
            n_skip += 1
            continue
        t = ds.get(tid)
        if t.hidden_states is None:
            print(f"  · {tid}: SKIP (no hidden_states)")
            n_skip += 1
            continue
        print(f"  · {tid}: building {t.meta.n_layers} layers... ", end="", flush=True)
        try:
            art = build_artifact(t, grid_n=args.grid_n)
            out_path.write_text(json.dumps(art))
            size_mb = out_path.stat().st_size / (1024 * 1024)
            print(f"OK ({size_mb:.1f} MB)")
            n_ok += 1
        except Exception as e:
            print(f"ERROR: {e}")

    # Index
    idx = build_index(cache_dir)
    idx_path = cache_dir / "index.json"
    idx_path.write_text(json.dumps(idx, indent=2))
    print(f"\n[per-layer] wrote index: {idx_path}  ({idx['n_artifacts']} entries)")
    print(f"[per-layer] built {n_ok}, skipped {n_skip}, cache={cache_dir}")


if __name__ == "__main__":
    main()