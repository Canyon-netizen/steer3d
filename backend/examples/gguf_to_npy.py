"""Export a llama.cpp control-vector GGUF into this project's .npy format.

The two formats do not match, and the mismatch is not cosmetic.

A control-vector GGUF holds one direction PER LAYER (`direction.0` …
`direction.L-1`) and nothing else — there is no field saying which layer
to apply it at, because llama.cpp applies it at whichever layer you ask
for. This project's registry holds one flat vector per named direction
and is injected at a single chosen layer. So exporting means picking a
layer, and saying which one.

The other mismatch is the sign. In the `token_pos=all` files the sign is
decided independently at each layer, so adjacent layers disagree — up to
13 of 27 adjacent pairs are anti-correlated, and a vector injected at
successive layers is applying a perturbation and then its negation.
`--sign-fix` repairs that by propagating one convention outward from an
anchor layer, and the report shows the before and after so the change is
visible rather than assumed.

Scale is the third thing, and the format genuinely cannot express it:
these vectors are unit-norm, while the residual stream grows ~80x from L4
to L26, so the same nominal strength is 343% of the state at L4 and 4% at
L26. `SteeringRegistry.load_layer_scales()` gets the per-layer scale from
the measured `layer_profiles.json`; that has to be supplied from outside
the GGUF and this script records which profile it was exported against.

Usage:
    python3 backend/examples/gguf_to_npy.py \
        --gguf ~/test/vectors/Qwen3-1.7B/entry_01.gguf \
        --name sound_vs_flawed --layer 20 --sign-fix \
        --out-dir backend/examples/output/steering_vectors_user

    # every layer, one directory each — for the layer scan
    python3 backend/examples/gguf_to_npy.py \
        --gguf ~/test/vectors/Qwen3-1.7B/entry_05.gguf \
        --name sound_vs_flawed --all-layers --sign-fix \
        --out-dir /tmp/user_vec_layers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gguf_cv import read_control_vector  # noqa: E402
from diagnose_vector_signs import adjacent_cos, sign_aligned_cos  # noqa: E402


def export(cv, layer: int, name: str, out_dir: Path, sign_fix: bool,
           anchor: Optional[int], layer_profiles: Optional[str]) -> dict:
    v = cv.direction_matrix[cv.layer_indices.index(layer)].copy()
    raw = v.copy()
    if sign_fix:
        v = v * sign_for_layer(cv.direction_matrix, layer, anchor)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / f"{name}.npy", v.astype(np.float32))

    meta = {
        "description": f"{cv.get('pos_field')} vs {cv.get('neg_field')} "
                       f"(from {cv.path.name})",
        "layer": layer,
        "d_model": int(v.shape[0]),
        "method": cv.get("method"),
        "source": str(cv.path),
        "source_model_hint": cv.get("model_hint"),
        "source_dataset": cv.get("dataset"),
        "source_pairs_file": cv.get("pairs_file"),
        "source_n_pairs": cv.get_int("n_pairs"),
        "source_token_pos": cv.get("token_pos"),
        "source_layer_count": cv.get_int("layer_count"),
        "source_correct_direction": bool(cv.get("correct_direction")),
        "norm": float(np.linalg.norm(v)),
        "sign_fixed": bool(sign_fix),
        "sign_anchor_layer": anchor if sign_fix else None,
        "flipped": bool(np.sign(raw[0]) != np.sign(v[0])),
        "layer_profiles": layer_profiles,
    }
    (out_dir / "steering_vectors.json").write_text(
        json.dumps({name: meta}, indent=2))
    return meta


def sign_for_layer(M: np.ndarray, layer: int, anchor: Optional[int]) -> float:
    """±1 to put `layer` in the anchor's convention.

    Propagates the anchor's sign outward through the layer stack, so the
    result is consistent with the anchor regardless of which layer the
    caller actually injects at.
    """
    idx = list(range(len(M)))
    a = idx.index(anchor if anchor is not None else 0)
    s = np.ones(len(M))
    # Walk up from the anchor.
    for i in range(a + 1, len(M)):
        if float(M[i] @ (M[i - 1] * s[i - 1])) < 0:
            s[i] = -1.0
    # And back down.
    for i in range(a - 1, -1, -1):
        if float(M[i] @ (M[i + 1] * s[i + 1])) < 0:
            s[i] = -1.0
    return float(s[layer])


def anchor_agreement(M: np.ndarray, target: int) -> dict:
    """Do different anchors agree on the direction, or just its sign?

    The fix makes the layers mutually consistent. It does not make the
    absolute sign meaningful: the same propagated vector anchored at a
    different layer can come out negated, and that is expected — it is
    what `correct_direction` records. What must hold is that anchors
    agree up to that negation. If two anchors disagree by more than a
    sign, the alternation is not a single consistent flip and one global
    convention does not repair it.
    """
    ref = M[target] * sign_for_layer(M, target, 0)
    ref = ref / (np.linalg.norm(ref) + 1e-12)
    rows = []
    for a in (0, len(M) // 2, len(M) - 1):
        v = M[target] * sign_for_layer(M, target, a)
        c = float(v @ ref / (np.linalg.norm(v) + 1e-12))
        rows.append((a, c))
    # Agreement up to a global sign means every anchor produces the same
    # unit vector, possibly negated. What matters is |cos| == 1 for all of
    # them, NOT that the signs are equal: anchors on opposite sides of a
    # flip legitimately give opposite signs, and counting distinct signs
    # would call that a disagreement when it is the expected result.
    offs = [abs(abs(c) - 1.0) for _, c in rows]
    agree = max(offs) < 1e-3
    return {
        "per_anchor": rows,
        "agree_up_to_sign": agree,
        "worst_deviation_from_unit": max(offs),
        "n_distinct_conventions": len({1 if c > 0 else -1 for _, c in rows}),
    }


def main(args) -> int:
    cv = read_control_vector(Path(args.gguf).expanduser())
    M = cv.direction_matrix
    layers = cv.layer_indices
    adj = adjacent_cos(M)
    fixed = sign_aligned_cos(M)

    print(f"source : {args.gguf}")
    print(f"         {cv.get('pos_field')} vs {cv.get('neg_field')}, "
          f"{cv.get_int('n_pairs')} pairs, token_pos={cv.get('token_pos')}, "
          f"{len(layers)} layers x {M.shape[1]}d")
    print()
    print(f"  adjacent-layer cosine as stored : "
          f"min {adj.min():+.3f}  mean {adj.mean():+.3f}  "
          f"{int((adj < 0).sum())}/{len(adj)} negative")
    print(f"  after sign propagation from L0  : "
          f"min {fixed.min():+.3f}  mean {fixed.mean():+.3f}  "
          f"{int((fixed < 0).sum())}/{len(fixed)} negative")
    if args.sign_fix:
        print("  -> exporting with the sign convention propagated; the "
              "stored vectors disagree per layer")
    elif int((adj < 0).sum()):
        print("  ** stored vectors have inconsistent per-layer signs. "
              "Re-run with --sign-fix, or the injected direction is "
              "arbitrary in sign at some layers. **")

    agr = anchor_agreement(M, args.layer)
    if int((adj < 0).sum()):
        desc = "  ".join(f"L{a}:{c:+.2f}" for a, c in agr["per_anchor"])
        print(f"  anchor agreement at L{args.layer}: {desc}")
        if agr["agree_up_to_sign"]:
            n = agr["n_distinct_conventions"]
            print(f"      -> every anchor yields the same vector up to a "
                  f"global sign ({n} convention"
                  f"{'s' if n > 1 else ''} across the stack), so one "
                  f"convention does repair the file. Which of the two "
                  f"conventions is right is not a fact — that is what "
                  f"correct_direction records.")
        else:
            print("      ** anchors give directions that are not even "
                  "parallel, so the alternation is not a consistent flip "
                  "and one global convention does NOT repair this file **")
    print()

    if args.all_layers:
        root = Path(args.out_dir).expanduser()
        for L in layers:
            d = root / f"L{L}"
            export(cv, L, args.name, d, args.sign_fix,
                   args.anchor, args.layer_profiles)
        print(f"  wrote {len(layers)} directories under {root} "
              f"(L{layers[0]}..L{layers[-1]})")
    else:
        d = Path(args.out_dir).expanduser()
        meta = export(cv, args.layer, args.name, d, args.sign_fix,
                      args.anchor, args.layer_profiles)
        print(f"  wrote {d / (args.name + '.npy')}  (layer {args.layer}, "
              f"norm {meta['norm']:.3f}"
              f"{', sign flipped' if meta['flipped'] else ''})")
        if not args.layer_profiles:
            print("  note: no --layer-profiles given, so the registry will "
                  "report this direction as uncalibrated and the UI will "
                  "show 'scale not measured'")
    return 0


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--name", required=True,
                    help="direction name to use in the registry")
    ap.add_argument("--layer", type=int, default=20)
    ap.add_argument("--all-layers", action="store_true",
                    help="one subdirectory per layer, for a layer scan")
    ap.add_argument("--sign-fix", action="store_true",
                    help="propagate one sign convention from the anchor")
    ap.add_argument("--anchor", type=int, default=None,
                    help="layer whose sign defines the convention "
                         "(default: layer 0)")
    ap.add_argument("--out-dir", default="backend/examples/output/steering_vectors_user")
    ap.add_argument("--layer-profiles", default=None,
                    help="layer_profiles.json this will be injected against")
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
