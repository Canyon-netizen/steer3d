"""Report what is actually inside the user's GGUF control vectors.

These are llama.cpp `controlvector` files (method `pca_cv:center`). Their
structure is easy to misread, and this script exists because it was:

* One direction is stored PER LAYER — a Qwen3-1.7B file has 28 tensors
  named `direction.0`…`direction.27`, matching its `layer_count` of 28.
  The 28 `explained_variance.N` values are per layer, not per component.
* `n_pairs` says how many token pairs produced each direction. The
  Qwen3-1.7B files were built from 30.
* `correct_direction` records that the writer flipped the sign, which
  makes "up" a naming convention rather than a fact.

The user's read is that these vectors' interpretability is low. Three
things here bear on that, and they are separable:

1. **Sample size.** A difference of means over 30 pairs is a noisy
   estimate of a 2048-dimensional direction. Compare against the ~20,000
   tokens behind the vectors in this repo.
2. **Layer-to-layer stability.** If `direction.8` and `direction.24` are
   near-orthogonal, there is no single "sound vs flawed" axis to name.
   This repo measured exactly this for its own confidence vectors
   (L8↔L24 cosine 0.395).
3. **Provenance.** `pos_field`/`neg_field`/`token_pos` state what was
   contrasted and where. `token_pos = -1` means the contrast was read off
   the final token of each sequence only.

Usage:
    python3 backend/examples/inspect_control_vectors.py \
        --dir ~/test/vectors/Qwen3-1.7B

    # compare against vectors extracted by this repo, per layer
    python3 backend/examples/inspect_control_vectors.py \
        --dir ~/test/vectors/Qwen3-1.7B \
        --compare-dir /tmp/steer3d_vec_layers/L20 \
        --compare-name reasoning_deep
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

import numpy as np

from gguf_cv import ControlVector, read_control_vector


def _row_norm(M: np.ndarray) -> np.ndarray:
    return np.linalg.norm(M, axis=1) + 1e-12


def describe(cv: ControlVector) -> dict:
    M = cv.direction_matrix
    layers = cv.layer_indices or list(range(M.shape[0]))
    norms = _row_norm(M)
    Mn = M / norms[:, None]
    C = Mn @ Mn.T                       # cosine between layers

    k = len(layers)
    adjacent = np.array([C[i, i + 1] for i in range(k - 1)]) if k > 1 else np.array([])
    # |lag| >= 4 pairs stay meaningfully separated in depth while being
    # far enough apart to be a different point in the stack.
    far = np.array([C[i, j] for i in range(k) for j in range(i + 4, k)])

    ev = cv.explained_variance
    info = {
        "file": cv.path.name,
        "model_hint": cv.get("model_hint"),
        "method": cv.get("method"),
        "dataset": cv.get("dataset"),
        "pairs_file": cv.get("pairs_file"),
        "pos_field": cv.get("pos_field"),
        "neg_field": cv.get("neg_field"),
        "token_pos": cv.get("token_pos"),
        "n_pairs": cv.get_int("n_pairs"),
        "n_positive": cv.get_int("n_positive"),
        "n_negative": cv.get_int("n_negative"),
        "n_layers": k,
        "d_model": int(M.shape[1]),
        "n_components": cv.get_int("n_components"),
        "correct_direction": bool(cv.get("correct_direction")),
        "normalize": bool(cv.get("normalize")),
        "norm_per_layer": {
            "min": float(norms.min()), "max": float(norms.max()),
            "ratio": float(norms.max() / norms.min()),
        },
        "layer_cosine": {
            "adjacent_mean": float(adjacent.mean()) if adjacent.size else None,
            "adjacent_min": float(adjacent.min()) if adjacent.size else None,
            "first_last": float(C[0, k - 1]) if k > 1 else None,
            "far_mean": float(far.mean()) if far.size else None,
            "far_min": float(far.min()) if far.size else None,
        },
    }
    if ev.size:
        info["explained_variance"] = {
            "n": int(ev.size),
            "min": float(ev.min()), "max": float(ev.max()),
            "mean": float(ev.mean()),
        }
    info["_matrix"] = M
    info["_layers"] = layers
    return info


def compare_with_ours(info: dict, ours: np.ndarray, ours_layer: int,
                      name: str) -> dict:
    """Cosine between each of their per-layer directions and one of ours.

    Same d_model and same architecture, so this is meaningful. A low
    cosine everywhere would mean the two extractions are not measuring
    the same thing, whatever their names suggest.
    """
    M = info["_matrix"]
    layers = info["_layers"]
    if ours.shape[0] != M.shape[1]:
        return {"error": f"d_model mismatch: ours {ours.shape[0]} vs {M.shape[1]}"}
    a = ours / (np.linalg.norm(ours) + 1e-12)
    cos = (M / _row_norm(M)[:, None]) @ a
    return {
        "ours": name,
        "ours_layer": ours_layer,
        "by_layer": {int(l): float(c) for l, c in zip(layers, cos)},
        "max_abs": float(np.abs(cos).max()),
        "argmax_abs": int(layers[int(np.abs(cos).argmax())]),
        "mean_abs": float(np.abs(cos).mean()),
    }


def main(args) -> int:
    d = Path(args.dir).expanduser()
    files = sorted(d.glob("*.gguf"))
    if not files:
        print(f"no .gguf in {d}")
        return 1

    infos: List[dict] = []
    for f in files[: args.limit]:
        try:
            infos.append(describe(read_control_vector(f)))
        except Exception as e:
            print(f"{f.name}: ERROR {type(e).__name__}: {e}")
    if not infos:
        return 1

    first = infos[0]
    print("=" * 74)
    print(f"Control vectors in {d}")
    print("=" * 74)
    print(f"  model_hint     : {first['model_hint']}")
    print(f"  method         : {first['method']}")
    print(f"  layers         : {first['n_layers']}  x d_model "
          f"{first['d_model']}   (one direction PER LAYER)")
    print(f"  components     : {first['n_components']} per layer")
    print(f"  contrast       : {first['pos_field']} vs {first['neg_field']}")
    print(f"  dataset        : {first['dataset']}  "
          f"(token_pos={first['token_pos']})")
    print(f"  pairs          : {first['n_pairs']}  "
          f"(pos {first['n_positive']} / neg {first['n_negative']})")
    print(f"  correct_dir    : {first['correct_direction']}   "
          f"normalize: {first['normalize']}")
    nl = first["norm_per_layer"]
    print(f"  ||v|| per layer: {nl['min']:.2f} … {nl['max']:.2f} "
          f"({nl['ratio']:.1f}x spread)")

    npairs = first["n_pairs"]
    if npairs:
        print()
        if npairs < 200:
            print(f"  ** {npairs} pairs is a small sample. A difference of")
            print(f"     means over {npairs} pairs in {first['d_model']}-d is a")
            print(f"     noisy estimate; the noise lands in every direction")
            print(f"     equally, so the vector is only partly about the")
            print(f"     contrast it claims. Vectors in this repo use")
            print(f"     15,679-20,930 tokens. **")

    print()
    print("  layer-to-layer cosine (is there one stable axis?):")
    print(f"    {'file':>16}  adj.mean  adj.min  first↔last  far.mean  far.min")
    for i in infos:
        c = i["layer_cosine"]
        print(f"    {i['file']:>16}  {c['adjacent_mean']:8.3f}  "
              f"{c['adjacent_min']:7.3f}  {c['first_last']:10.3f}  "
              f"{c['far_mean']:8.3f}  {c['far_min']:7.3f}")
    fl = [i["layer_cosine"]["first_last"] for i in infos
          if i["layer_cosine"]["first_last"] is not None]
    if fl:
        m = float(np.mean(fl))
        print()
        print(f"    mean first↔last cosine {m:.3f} — " + (
            "one axis survives the whole stack" if m > 0.6 else
            "the direction rotates substantially with depth; there is no "
            "single 'sound vs flawed' axis" if m > 0.3 else
            "near-orthogonal end to end: each layer encodes something different"))

    if args.verbose:
        ev = first.get("explained_variance")
        if ev:
            print()
            print("  per-layer explained variance: " + " ".join(
                f"{v:.2f}" for v in
                read_control_vector(Path(d) / first["file"]).explained_variance))

    ours = None
    if args.compare_dir:
        p = Path(args.compare_dir).expanduser() / f"{args.compare_name}.npy"
        if p.exists():
            ours = np.load(p).astype(np.float32).reshape(-1)
            d = ours.shape[0]
            # Two independent random unit vectors in R^d have
            # E|cos| = sqrt(2/(pi*d)). Below that, the two are as
            # unrelated as noise allows and the comparison says nothing.
            floor = float(np.sqrt(2.0 / (np.pi * d)))
            print()
            print(f"  cosine vs our {args.compare_name} (extracted at "
                  f"L{args.compare_layer}); random floor |cos| = {floor:.3f}")
            for i in infos:
                c = compare_with_ours(i, ours, args.compare_layer, args.compare_name)
                if "error" in c:
                    print(f"    {i['file']}: {c['error']}")
                    continue
                bl = c["by_layer"]
                shown = {k: bl[k] for k in list(bl)[:4]}
                # Deliberately conservative bands. A bare cosine against a
                # floor is easy to overread — the lesson of Finding 7 is
                # that small excesses are not evidence, so only a
                # multiple well clear of the floor is called "related".
                ratio = c["mean_abs"] / floor if floor else 0.0
                over = ("unrelated (at the floor)" if ratio < 2.0 else
                        "barely related" if ratio < 3.0 else
                        "related")
                print(f"    {i['file']:>16}  L0..L3 " +
                      " ".join(f"{v:+.3f}" for v in shown.values()) +
                      f"   | max |cos| {c['max_abs']:.3f} at L{c['argmax_abs']}"
                      f"  mean {c['mean_abs']:.3f} = {ratio:.1f}x floor"
                      f" — {over}")
        else:
            print(f"  no {p}")

    if args.out:
        payload = [{k: v for k, v in i.items() if not k.startswith("_")}
                   for i in infos]
        Path(args.out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nwrote {args.out}")
    return 0


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dir", type=str, required=True)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--compare-dir", type=str, default=None,
                    help="directory of .npy vectors extracted by this repo")
    ap.add_argument("--compare-name", type=str, default="reasoning_deep")
    ap.add_argument("--compare-layer", type=int, default=20)
    ap.add_argument("--verbose", action="store_true")
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
