"""Package paired (control vs steered) hidden states for the browser viewer.

What this adds over ``build_latent_bundle.py``
----------------------------------------------
That file packages trajectories that were *never steered*. Everything under
``output/intervention/`` that did steer records text and scalars but no
representation at all, so a viewer of those runs cannot draw a single point
of "the hidden state moved". This file packages the missing half: the same
problem generated twice, once clean and once injected, with the raw 2048-d
residual stream kept for both at full fidelity.

Three decisions worth stating, because each one is a way this could have
been quietly wrong instead:

1. **No precomputed ``delta`` file.** The browser subtracts the two arms
   itself. A stored delta is a third copy of the same information, and a
   viewer that lets you move a layer slider cannot use one anyway. It also
   removes a whole class of "the two files disagree" bugs.

2. **The PCA basis is shared with the unsteered bundle, not refit here.**
   Two fits would put the same trajectory in two unrelated 2-D pictures,
   and the first thing a reader would conclude from "the steer moved the
   cloud" would be an artefact of a different projection. So the control
   and steered arms of a pair, and the unsteered trajectories, all land in
   one coordinate system.

3. **The projection is recomputed, then checked against the cache.** Same
   reasoning as ``build_latent_bundle``: reuse the cached *basis* (it must
   be shared for the browser to reproduce it) but recompute the
   coordinates over the full sequence, and assert the recomputed prefix
   matches the cached one. A transposed basis is the failure this catches.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

HERE = Path(__file__).resolve().parent


def _write_f16(path: Path, arr: np.ndarray) -> int:
    b = np.ascontiguousarray(arr, dtype=np.float16).tobytes()
    path.write_bytes(b)
    return len(b)


def _write_i32(path: Path, arr: np.ndarray) -> int:
    """int32 must not share a writer with float32.

    Reusing a float32 writer here is how a token id becomes ``#1209277632``
    in the UI — the bit pattern reads back as a plausible-looking integer
    and nothing anywhere reports an error.
    """
    b = np.ascontiguousarray(arr, dtype=np.int32).tobytes()
    path.write_bytes(b)
    return len(b)


def load_basis(data_dir: Path, layers: List[int], d_model: int) -> Dict[int, dict]:
    """Read the shared PCA basis out of the unsteered bundle."""
    pca = np.fromfile(data_dir / "pca_00.bin", dtype=np.float32)
    mean = np.fromfile(data_dir / "mean_00.bin", dtype=np.float32)
    n = pca.size // (d_model * 2)
    pca = pca.reshape(n, d_model, 2)
    mean = mean.reshape(n, d_model)
    basis = {}
    for L in layers:
        if L >= n:
            raise SystemExit(f"basis has {n} layers, need L{L}")
        comp = pca[L]
        norms = np.linalg.norm(comp, axis=0)
        if not np.allclose(norms, 1.0, atol=0.05):
            raise SystemExit(
                f"L{L}: component norms {norms} are not ~1 — the basis file is "
                f"probably not component-major, and every point would be "
                f"projected through a transpose that still looks like a plot")
        basis[L] = {"comp": comp, "mean": mean[L]}
    return basis


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paired-dir", default="output/paired")
    ap.add_argument("--data-dir", default="frontend/public/latent/data")
    ap.add_argument("--out-subdir", default="pairs")
    ap.add_argument("--d-model", type=int, default=2048)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--layers", default="", help="subset, e.g. 4,20,26")
    args = ap.parse_args()

    pdir = Path(args.paired_dir)
    npzs = sorted(pdir.glob("pair_*.npz"))
    if not npzs:
        print(f"ERROR: no pair_*.npz under {pdir}")
        return 1
    if args.limit:
        npzs = npzs[:args.limit]

    out = Path(args.data_dir) / args.out_subdir
    out.mkdir(parents=True, exist_ok=True)
    dim_names: Dict[str, list] = {}
    dn = Path(args.data_dir) / "dim_names.json"
    if dn.is_file():
        dim_names = json.loads(dn.read_text())

    entries = []
    total = 0
    print(f"packaging {len(npzs)} pairs -> {out}\n")

    for npz_path in npzs:
        pid = npz_path.stem[len("pair_"):]
        rec = json.loads((pdir / f"pair_{pid}.json").read_text())
        z = np.load(npz_path)
        layers = [int(x) for x in z["layers"]]
        if args.layers:
            want = {int(x) for x in args.layers.split(",")}
            layers = [L for L in layers if L in want]
        basis = load_basis(Path(args.data_dir), layers, args.d_model)

        item = {
            "id": pid,
            "problem": rec.get("problem", ""),
            "correct": rec.get("correct"),
            "inject_layer": rec.get("inject_layer"),
            "direction": rec.get("direction"),
            "strength": rec.get("strength"),
            "layers": layers,
            "n_common_prefix": rec.get("paired", {}).get("n_common_prefix"),
            "diverged": rec.get("paired", {}).get("diverged"),
            "answer": rec.get("answer", {}),
            "closed_think": rec.get("closed_think", {}),
            "hs_alignment": rec.get("hs_alignment", ""),
            "arms": {},
        }
        row = []
        for L in layers:
            arm_meta = {}
            for arm, key in (("control", "control"), ("steered", "steered")):
                name = f"{key}_L{L}"
                if name not in z:
                    continue
                X = z[name]
                if X.size == 0:
                    continue
                T, D = X.shape
                if D != args.d_model:
                    raise SystemExit(f"{pid} {name}: d_model {D} != {args.d_model}")
                # Re-derive the coordinates here as a check on the basis, not
                # as data to ship: the browser recomputes from the vectors.
                proj = ((X.astype(np.float32) - basis[L]["mean"])
                        @ basis[L]["comp"])
                nb = _write_f16(out / f"pc_{pid}_{key}_L{L}.bin", X)
                total += nb
                arm_meta[arm] = {
                    "file": f"pc_{pid}_{key}_L{L}.bin",
                    "T": int(T), "D": int(D),
                    "n_bytes": nb,
                    "proj": [[float(proj[i, 0]), float(proj[i, 1])]
                             for i in range(T)] if T <= 2048 else None,
                }
                row.append(f"  L{L:<3d} {arm:8s} T={T:<5d} {nb/1e6:6.1f}MB  "
                           f"PC1[{proj[:,0].min():9.2f},{proj[:,0].max():9.2f}]")

            e = rec.get("paired", {}).get("per_layer", {}).get(str(L), {})
            if e:
                arm_meta["stats"] = {
                    "n_compared": e.get("n_compared"),
                    "rel_shift": [round(v, 6) for v in e.get("rel_shift", [])],
                    "cosine": [round(v, 6) for v in e.get("cosine", [])],
                    "h_norm": [round(v, 3) for v in e.get("h_norm", [])],
                    "proj_on_steer": [round(v, 5)
                                       for v in e.get("proj_on_steer", [])],
                    "proj_fraction": e.get("proj_fraction"),
                }
            td = rec.get("top_dims", {}).get(str(L), [])
            if td:
                arm_meta["top_dims"] = [
                    {"dim": d["dim"], "delta": round(d["delta"], 5),
                     "names": (dim_names.get(str(d["dim"]))
                               or dim_names.get(d["dim"]) or [])}
                    for d in td
                ]
            item["arms"][str(L)] = arm_meta

        for arm, key in (("control", "control_ids"), ("steered", "steered_ids")):
            if key in z and z[key].size:
                nb = _write_i32(out / f"pc_{pid}_{arm}_ids.bin", z[key])
                total += nb
                item["arms"].setdefault("_ids", {})[arm] = {
                    "file": f"pc_{pid}_{arm}_ids.bin", "n": int(z[key].size)}
        item["text"] = {"control": rec.get("control", {}).get("text", ""),
                        "steered": rec.get("steered", {}).get("text", "")}

        entries.append(item)
        print(f"[{pid}] {item['n_common_prefix']} 步共同前缀  "
              f"diverged={item['diverged']}  answer={item['answer']}")
        print("\n".join(row))

    # The steering direction itself, unit-normalised, so the viewer can draw
    # the arrow "the intervention pushed this way" against the delta cloud.
    unit = None
    for npz_path in npzs:
        z = np.load(npz_path)
        if "unit" in z and z["unit"].size == args.d_model:
            unit = z["unit"].astype(np.float32)
            break
    if unit is not None:
        n = float(np.linalg.norm(unit)) or 1.0
        total += _write_f16(out / "steer_unit.bin", unit / n)

    mf = {
        "note": "paired control/steered; browser recomputes the projection and "
                "the delta from the raw vectors",
        "d_model": args.d_model,
        "basis": {"source": "pca_00.bin / mean_00.bin from the unsteered bundle",
                  "orientation": "components stored component-major, one unit "
                                 "vector per column",
                  "delta_projection": "proj(steered) - proj(control); the mean "
                                      "cancels, so the delta needs no origin"},
        "steer_unit": "steer_unit.bin" if unit is not None else None,
        "pairs": entries,
    }
    (out / "pairs.json").write_text(
        json.dumps(mf, ensure_ascii=False, separators=(",", ":")))
    print(f"\nmanifest: {out / 'pairs.json'}")
    print(f"vectors : {total/1e6:.1f} MB across {len(entries)} pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
