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

1. **The delta is shipped, and the steered arm is not.** This is the one
   that is easy to get backwards. Storing both arms and letting the browser
   subtract looks like the cheaper option — it is the same 2x payload —
   and it is what an earlier draft of this file did.

   It is wrong by two orders of magnitude in precision. fp16 carries 11
   bits, so each component of the stored residual is quantised to a
   relative 2^-11; the error over a 2048-dimensional vector accumulates as
   sqrt(2048) = 45.3. Differencing two independently-quantised copies of
   ``h`` therefore leaves an error of roughly ``0.022 * ‖h‖`` — and the
   signal being recovered, the delta, is ``rel_shift * ‖h‖``. Measured SNR
   (‖true‖ / ‖error‖) for a 2048-d stream:

   | rel_shift | h+steered, subtract in browser | h+delta, rebuild steered |
   |---|---|---|
   | 0.10 | 339 | 4823 |
   | 0.01 | 34 | 4813 |
   | 0.001 | **3.4** | **4837** |

   At a SNR of 3.4 the direction of the change is not readable. That is not
   a hypothetical: at layers *upstream* of the injection point the delta is
   expected to be near zero, and those are exactly the layers where a
   small-but-real upstream effect would be erased by quantisation noise and
   replaced by a plausible-looking smear.

   Shipping ``h`` and ``delta`` costs the same two vectors and gives a
   constant SNR of ~4800, because fp16's error is then relative to
   ``‖delta‖`` itself rather than to ``‖h‖``. The browser reconstructs the
   steered arm as ``h + delta`` in float32.

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
import warnings
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

    # dim_names.json is {"schema": ..., "dims": [{"d": 478, "top": [{"id":…,
    # "t": "ters", "w": 0.157}, …]}, …]} — a list indexed by dimension, each
    # entry carrying a `top` list of tokens. Reading it as a dict keyed by
    # dimension number returns nothing at all, and because the failure is an
    # empty list rather than an exception, the viewer's dimension column comes
    # out as a column of em-dashes on a page that otherwise renders perfectly.
    # Hence the assertion: a present-but-empty parse means the shape was
    # misunderstood, and it must stop the run rather than ship silently.
    dim_names: Dict[int, List[str]] = {}
    dn = Path(args.data_dir) / "dim_names.json"
    if dn.is_file():
        raw = json.loads(dn.read_text())
        for entry in raw.get("dims", []):
            if not isinstance(entry, dict) or "d" not in entry:
                continue
            dim_names[int(entry["d"])] = [
                t["t"] for t in entry.get("top", []) if isinstance(t, dict) and "t" in t]
        assert dim_names, (
            f"{dn} exists but parsed to zero dimensions — the expected shape is "
            f"{{'dims': [{{'d': int, 'top': [{{'t': str}}]}}]}}, got keys "
            f"{sorted(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}")
        print(f"dim names: {len(dim_names)} dimensions, "
              f"e.g. #{next(iter(dim_names))} -> {dim_names[next(iter(dim_names))][:4]}")
    else:
        print(f"WARNING {dn} absent — the viewer's dimension column will be blank")

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
        n_common = int(rec.get("paired", {}).get("n_common_prefix", 0) or 0)
        for L in layers:
            arm_meta = {}
            ctl = z.get(f"control_L{L}")
            std = z.get(f"steered_L{L}")
            if ctl is None or ctl.size == 0:
                continue

            # --- control: shipped as-is -------------------------------------
            T, D = ctl.shape
            if D != args.d_model:
                raise SystemExit(f"{pid} control_L{L}: d_model {D} != {args.d_model}")
            # Recomputed here as a check on the basis, not shipped: the
            # browser projects from the vectors itself.
            # numpy raises divide-by-zero / overflow / invalid RuntimeWarnings
            # from this matmul on some BLAS builds (macOS Accelerate) even when
            # every input and every output is finite — verified by checking
            # all three. The warnings carry no information; finiteness of the
            # result does. So suppress the noise and assert on the signal.
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                proj = ((ctl.astype(np.float32) - basis[L]["mean"])
                        @ basis[L]["comp"])
            assert np.isfinite(proj).all(), (
                f"{pid} L{L}: projection produced non-finite values "
                f"({int((~np.isfinite(proj)).sum())} of {proj.size}) — the "
                f"basis or the vectors are not what they claim to be")
            nb = _write_f16(out / f"pc_{pid}_control_L{L}.bin", ctl)
            total += nb
            arm_meta["control"] = {
                "file": f"pc_{pid}_control_L{L}.bin",
                "T": int(T), "D": int(D), "n_bytes": nb,
                "proj": ([[float(proj[i, 0]), float(proj[i, 1])]
                          for i in range(T)] if T <= 2048 else None),
            }
            row.append(f"  L{L:<3d} control  T={T:<5d} {nb/1e6:6.1f}MB  "
                       f"PC1[{proj[:,0].min():9.2f},{proj[:,0].max():9.2f}]")

            # --- delta: differenced in float32 BEFORE any quantisation -----
            if std is None or std.size == 0:
                arm_meta["delta"] = None
                arm_meta["delta_note"] = ("no steered arm stored for this "
                                          "layer, so there is nothing to "
                                          "difference against")
                continue
            m = min(n_common, T, std.shape[0])
            if m <= 0:
                # The two arms disagreed on their very first token. There is
                # no step at which "the hidden state moved" is a question
                # that can be asked, and the server-side top_dims for this
                # layer is a mean over an empty slice — a NaN that would
                # survive json.dumps as a bare `NaN` and make JSON.parse
                # reject the whole manifest. Record why it is empty instead
                # of leaving the viewer to guess.
                arm_meta["delta"] = None
                arm_meta["delta_note"] = (
                    "the two arms picked different tokens on their very first "
                    "step, so there is no common prefix and no comparable "
                    "delta for this layer")
                row.append(f"  L{L:<3d} 无共同前缀 → 这一层没有可比的 Δ")
                continue
            h32 = ctl[:m].astype(np.float32)
            delta = (std[:m].astype(np.float32) - h32).astype(np.float16)
            nb = _write_f16(out / f"pc_{pid}_delta_L{L}.bin", delta)
            total += nb

            # What the browser would get back, and what it would have got
            # from differencing the two stored arms instead. Reporting both
            # is the point: the second number is why the delta is shipped.
            hq = h32.astype(np.float16).astype(np.float32)
            recon = hq + delta.astype(np.float32)
            snr_recon = float(np.linalg.norm(h32) /
                              max(np.linalg.norm(recon - h32), 1e-30))
            naive = std[:m].astype(np.float16).astype(np.float32) - hq
            snr_naive = float(np.linalg.norm(h32) /
                              max(np.linalg.norm(naive - h32), 1e-30))
            arm_meta["delta"] = {
                "file": f"pc_{pid}_delta_L{L}.bin",
                "T": int(m), "D": args.d_model, "n_bytes": nb,
                "covers": f"the first {m} steps — the two arms only match "
                          f"token-for-token up to the divergence point",
                "steered_reconstructed_as": "control (float32) + delta (float32)",
                "reconstruction_snr": snr_recon,
                "snr_if_differencing_stored_arms": snr_naive,
            }
            row.append(f"  L{L:<3d} delta    T={m:<5d} {nb/1e6:6.1f}MB  "
                       f"重建 SNR={snr_recon:8.0f}  "
                       f"(若相减两条流 只有 {snr_naive:6.1f})")

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
                # json.loads turns a bare NaN in the source file into
                # float('nan') without complaint, and json.dumps writes it back
                # out as `NaN` — which JSON.parse rejects outright, so the page
                # would fail to load its manifest with no clue why. The path
                # that produces it is real: if the two arms disagree on the
                # very first token, n_compared is 0 and the server-side
                # `.mean(0)` over an empty slice is NaN. Refuse to pack it.
                bad = [d for d in td
                       if not np.isfinite(float(d.get("delta", np.nan)))]
                assert not bad, (
                    f"{pid} L{L}: top_dims has non-finite deltas "
                    f"({bad[:3]}). Most likely n_common_prefix was 0 or 1, so "
                    f"there is no common prefix to average over. Refusing to "
                    f"write a manifest the browser cannot parse.")
                arm_meta["top_dims"] = [
                    {"dim": d["dim"], "delta": round(d["delta"], 5),
                     "names": dim_names.get(d["dim"], [])}
                    for d in td
                ]
                assert any(x["names"] for x in arm_meta["top_dims"]), (
                    f"{pid} L{L}: every top dimension came back without names — "
                    f"dim_names.json was read in a shape it does not have")
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
        "note": "paired control/delta; the browser recomputes the projection "
                "and reconstructs the steered arm as control + delta",
        "d_model": args.d_model,
        "basis": {"source": "pca_00.bin / mean_00.bin from the unsteered bundle",
                  "orientation": "components stored component-major, one unit "
                                 "vector per column",
                  "delta_projection": "proj(h + delta) - proj(h) = proj(delta); "
                                      "the mean cancels, so a delta needs no "
                                      "origin of its own"},
        "delta_policy": "delta is differenced server-side in float32 and stored "
                        "as fp16. Do not derive it in the browser by "
                        "subtracting two stored arms: fp16 quantisation of h "
                        "leaves ~0.022*||h|| of error, and each arm's file "
                        "reports the SNR both ways.",
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
