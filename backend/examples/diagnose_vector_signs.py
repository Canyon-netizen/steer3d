"""Why is the sign flipping between adjacent layers?

The inspector found adjacent-layer cosines of -0.89 on some entries. A
difference-of-means direction for one semantic contrast should not rotate
180 degrees between two adjacent blocks — that is either a sign
convention applied per-file rather than per-layer, or an extraction that
took the sign from whichever side happened to have the larger norm.

This prints the per-entry provenance next to the full adjacent-cosine
profile, so the two can be compared. If the sign of a whole suffix of
layers is inverted, flipping it recovers a smooth profile; if the sign
alternates layer to layer, the direction itself is unstable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gguf_cv import read_control_vector  # noqa: E402


def adjacent_cos(M: np.ndarray) -> np.ndarray:
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)
    C = Mn @ Mn.T
    return np.array([C[i, i + 1] for i in range(len(M) - 1)])


def main(args) -> int:
    d = Path(args.dir).expanduser()
    for f in sorted(d.glob("*.gguf"))[: args.limit]:
        cv = read_control_vector(f)
        M = cv.direction_matrix
        adj = adjacent_cos(M)
        print(f"{f.name}  dataset={cv.get('dataset')}  "
              f"contrast={cv.get('pos_field')}/{cv.get('neg_field')}  "
              f"pairs={cv.get_int('n_pairs')}  token_pos={cv.get('token_pos')}")
        print("   adj: " + " ".join(f"{v:+.2f}" for v in adj))
        if (adj < 0).any():
            # A per-file sign convention applied to a per-layer contrast
            # would invert a contiguous run, not alternate. Count the
            # sign changes to tell the two apart.
            signs = np.sign(adj)
            n_flips = int((np.diff(signs) != 0).sum())
            neg = [i for i, v in enumerate(adj) if v < 0]
            print(f"   {len(neg)}/{len(adj)} adjacent pairs negative, "
                  f"{n_flips} sign changes"
                  f"   -> {'ALTERNATING (unstable direction)' if n_flips > 1 else 'contiguous run (sign convention)'}")
        print()
    return 0


def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--limit", type=int, default=12)
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
