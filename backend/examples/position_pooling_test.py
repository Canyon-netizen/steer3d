"""Does pooling the contrast over token positions destroy the direction?

The user's GGUF control vectors contain two groups that differ in exactly
one recorded field, `token_pos`:

  entry_01  sound/flawed  30 pairs  token_pos=-1   -> 0 negative adjacent
                                                         cosines, 0.76 mean
  entry_05  sound/flawed  29 pairs  token_pos=all   -> 7 negative, 9 sign
                                                         changes, 0.36 mean
  entry_07  sound/flawed  10 pairs  token_pos=all   -> 8 negative, 10 sign
                                                         changes, 0.26 mean

Same contrast, near-identical sample size, and the layer-to-layer
orientation goes from smooth to alternating. That is the mechanical
version of "the interpretability of these vectors is low", and it is
worth reproducing on data we control rather than only observing in
someone else's files.

This script extracts one contrast three ways from the same 48
trajectories, at every layer, and reports how the direction behaves:

  last   one position per trajectory (the last self-check token and the
         last other token) — an analogue of token_pos=-1
  tail   positions in the final 20% of each trajectory
  all    every position in the trajectory — an analogue of token_pos=all

A difference of means is only as stable as the number of INDEPENDENT
samples behind it. `all` contributes tens of thousands of positions but
only 48 trajectories, and positions within a trajectory are strongly
correlated, so the effective sample size stays at 48 however many
positions are pooled. That is the mechanism this measures.

Reported per mode:
  * adjacent-layer cosine of the extracted direction, and its sign
    changes — an alternating sign means the orientation is not a
    property of the contrast but of the noise
  * the same after removing the component shared by all layers, which
    would otherwise inflate every cosine
  * ||mean_pos - mean_neg|| relative to the per-coordinate spread, as a
    scale-free stand-in for effect size (an exact Cohen's d needs a
    second pass over the raw activations, so this is labelled as the
    proxy it is)

Usage:
    python3 backend/examples/position_pooling_test.py \
        --data-root datasets/aime_qwen3_1p7b_16k_fp16/aime \
        --out backend/examples/output/position_pooling.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

SELF_CHECK_RE = re.compile(
    r"(?:wait|hold on|hmm|actually|but wait|no,|let me|double.?check|"
    r"alternatively|on second thought)", re.IGNORECASE)


class PoolAccumulator:
    """Per-layer class means and spreads for one extraction mode.

    Accumulates sums rather than the activations themselves so the whole
    48-trajectory corpus can be held in a few megabytes across all
    layers at once.
    """

    def __init__(self, n_layers: int, d_model: int):
        self.n_layers = n_layers
        self.d_model = d_model
        self.sum = {c: np.zeros((n_layers, d_model), np.float64)
                    for c in ("pos", "neg")}
        self.sumsq = {c: np.zeros((n_layers, d_model), np.float64)
                      for c in ("pos", "neg")}
        self.n = {c: np.zeros(n_layers, np.int64) for c in ("pos", "neg")}

    def add(self, layer_slice: np.ndarray, pos_mask: np.ndarray,
            neg_mask: np.ndarray) -> None:
        """layer_slice: (T, L, D); masks: (T,) over token positions."""
        for cls, mask in (("pos", pos_mask), ("neg", neg_mask)):
            if not mask.any():
                continue
            X = layer_slice[mask].astype(np.float64)     # (n, L, D)
            self.sum[cls] += X.sum(axis=0)
            self.sumsq[cls] += (X * X).sum(axis=0)
            self.n[cls] += X.shape[0]

    def directions(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(directions, separation, counts).

        `directions` is (L, D) unit-norm, `separation` is
        ||mean_pos - mean_neg|| divided by the RMS per-coordinate spread
        in the same units — a scale-free stand-in for effect size.
        """
        dirs, sep = [], []
        for L in range(self.n_layers):
            np_, nn_ = self.n["pos"][L], self.n["neg"][L]
            if np_ < 2 or nn_ < 2:
                dirs.append(np.zeros(self.d_model))
                sep.append(np.nan)
                continue
            mp = self.sum["pos"][L] / np_
            mn = self.sum["neg"][L] / nn_
            v = mp - mn
            nv = np.linalg.norm(v)
            dirs.append(v / nv if nv > 1e-9 else v)
            # Pooled per-coordinate spread of the two classes.
            vp = np.maximum(self.sumsq["pos"][L] / np_ - mp ** 2, 0.0)
            vn = np.maximum(self.sumsq["neg"][L] / nn_ - mn ** 2, 0.0)
            sd = np.sqrt((vp + vn) / 2.0)
            rms = np.sqrt((sd ** 2).mean())
            sep.append(float(nv / rms) if rms > 1e-9 else np.nan)
        return (np.stack(dirs),
                np.array(sep),
                self.n["pos"].copy())


def load_one(npz_path: Path, is_self_check_flag: bool) -> Optional[dict]:
    """Read one trajectory's hidden states plus the token flags we need."""
    d = np.load(npz_path, allow_pickle=True)
    if "hidden_states" not in d.files:
        return None
    hs = d["hidden_states"]
    if hs.ndim != 3:
        return None
    sidecar = npz_path.with_suffix(".json")
    if not sidecar.exists():
        return None
    meta = json.loads(sidecar.read_text())
    tokens = meta.get("tokens", [])
    if len(tokens) != hs.shape[0]:
        return None
    flags = [bool(t.get("is_self_check", False)) for t in tokens]
    if not any(flags):
        flags = [bool(SELF_CHECK_RE.search(t["token"] or "")) for t in tokens]
    return {"hs": hs, "self_check": np.array(flags)}


def build_modes(hs: np.ndarray, sc: np.ndarray,
                rng: np.random.Generator) -> Dict[str, Tuple]:
    """The position-handling variants, plus a null control, as masks.

    `random` partitions the same number of positions into two groups at
    random. Its difference of means is pure noise, so whatever the
    adjacent-layer cosine does there is the floor for this metric — the
    baseline a contrast with no signal cannot beat. Without it, a cosine
    of 0.7 is uninterpretable: it might mean "stable" or it might mean
    "the residual stream's shared direction dominates at every layer".
    """
    T = hs.shape[0]
    n_pos = int(sc.sum())
    tail_start = int(T * 0.8)
    last = np.zeros(T, bool)
    if sc.any():
        last[np.flatnonzero(sc)[-1]] = True
    last_other = np.zeros(T, bool)
    if (~sc).any():
        last_other[np.flatnonzero(~sc)[-1]] = True

    # Null control: same group sizes, assigned at random.
    idx = rng.permutation(T)
    rand_pos = np.zeros(T, bool)
    rand_pos[idx[:n_pos]] = True
    rand_neg = np.zeros(T, bool)
    rand_neg[idx[n_pos:2 * n_pos]] = True

    return {
        # one position per trajectory, paired
        "last": (last, last_other),
        # final fifth of each trajectory
        "tail": (sc & (np.arange(T) >= tail_start),
                 (~sc) & (np.arange(T) >= tail_start)),
        # every position
        "all": (sc, ~sc),
        # null control
        "random": (rand_pos, rand_neg),
    }


def _unit(M: np.ndarray) -> np.ndarray:
    """Row-normalise, leaving degenerate rows at zero rather than NaN.

    A layer with too few samples to estimate a difference of means gets a
    zero row; normalising that would divide by ~0 and poison every
    downstream matrix product with NaN.
    """
    n = np.linalg.norm(M, axis=1, keepdims=True)
    bad = (n[:, 0] < 1e-9) | ~np.isfinite(n[:, 0])
    out = np.where(n > 1e-9, M / np.where(n > 1e-9, n, 1.0), 0.0)
    out[bad] = 0.0
    return out


def orientation_stats(V: np.ndarray) -> dict:
    """How coherent is this direction across depth?"""
    Vn = _unit(V)
    C = Vn @ Vn.T
    k = len(V)
    adj = np.array([C[i, i + 1] for i in range(k - 1)])
    signs = np.sign(adj)
    n_flips = int((np.diff(signs) != 0).sum()) if len(signs) > 1 else 0
    far = np.array([C[i, j] for i in range(k) for j in range(i + 4, k)])

    # Remove the component every layer shares. A difference of means in a
    # transformer picks up a common direction, and that shared part
    # inflates every cosine above — including the ones being used to
    # judge whether the layers agree.
    mu = _unit(Vn.mean(axis=0, keepdims=True))[0]
    R = Vn - np.outer(Vn @ mu, mu)
    Rn = _unit(R)
    Cr = Rn @ Rn.T
    adjr = np.array([Cr[i, i + 1] for i in range(k - 1)])

    return {
        "adjacent_mean": float(adj.mean()),
        "adjacent_min": float(adj.min()),
        "n_negative": int((adj < 0).sum()),
        "n_sign_changes": n_flips,
        "far_mean": float(far.mean()) if far.size else None,
        "first_last": float(C[0, k - 1]) if k > 1 else None,
        "common_component_share": float(
            1.0 - np.linalg.norm(R, axis=1).mean()),
        "adjacent_mean_residual": float(adjr.mean()),
        "adjacent_min_residual": float(adjr.min()),
    }


def main(args) -> int:
    root = Path(args.data_root)
    files = sorted(root.glob("*.npz"))
    if not files:
        print(f"no .npz under {root}")
        return 1
    files = files[: args.limit]
    print(f"{len(files)} trajectories from {root}")

    # First file fixes the shape.
    first = load_one(files[0], True)
    if first is None:
        print("could not read the first trajectory")
        return 1
    n_layers, d_model = first["hs"].shape[1], first["hs"].shape[2]

    accs = {m: PoolAccumulator(n_layers, d_model)
            for m in ("last", "tail", "all", "random")}
    rng = np.random.default_rng(0)
    n_traj = 0
    for i, p in enumerate(files):
        rec = load_one(p, True)
        if rec is None:
            continue
        hs, sc = rec["hs"], rec["self_check"]
        if sc.shape[0] != hs.shape[0] or not sc.any():
            continue
        for mode, (pm, nm) in build_modes(hs, sc, rng).items():
            accs[mode].add(hs, pm, nm)
        n_traj += 1
        if (i + 1) % 12 == 0:
            print(f"  {i+1}/{len(files)} …")

    print(f"\n{n_traj} trajectories contributed")
    print("=" * 72)
    print("Does pooling the contrast over positions destabilise it?")
    print("=" * 72)

    results = {}
    for mode in ("last", "tail", "all", "random"):
        V, sep, npos = accs[mode].directions()
        st = orientation_stats(V)
        st["separation_by_layer"] = [None if not np.isfinite(s) else round(s, 4)
                                     for s in sep]
        st["n_pos_samples"] = int(npos.max())
        st["n_trajectories"] = n_traj
        results[mode] = st

        tag = "  <- NULL: no signal, this is the floor" if mode == "random" else ""
        print(f"\n  mode = {mode}{tag}")
        print(f"    pos samples / layer : {int(npos.max())}  "
              f"(from {n_traj} trajectories)")
        print(f"    separation  L0/L10/L20/L27: "
              + " / ".join(f"{sep[i]:.2f}" for i in
                           (0, min(10, n_layers - 1),
                            min(20, n_layers - 1), n_layers - 1)
                           if np.isfinite(sep[i])))
        print(f"    adjacent cosine   : mean {st['adjacent_mean']:+.3f}  "
              f"min {st['adjacent_min']:+.3f}")
        print(f"    sign changes      : {st['n_sign_changes']}   "
              f"negative pairs: {st['n_negative']}/{n_layers - 1}")
        print(f"    shared component  : {st['common_component_share']:.1%} "
              f"of ||v|| is common to all layers")
        print(f"    after removing it : mean {st['adjacent_mean_residual']:+.3f}"
              f"  min {st['adjacent_min_residual']:+.3f}")

    print()
    print("  " + "-" * 68)
    null = results["random"]
    print(f"  NULL control      : adjacent mean {null['adjacent_mean']:+.3f}, "
          f"{null['n_sign_changes']} sign changes")
    print(f"  real contrast     : adjacent mean "
          f"{results['all']['adjacent_mean']:+.3f}, "
          f"{results['all']['n_sign_changes']} sign changes")
    print("  " + "-" * 68)
    print("  A cosine above the null floor is evidence the contrast is real;")
    print("  the sign changes are what a direction built from too few")
    print("  independent samples looks like.")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {"n_layers": n_layers, "d_model": d_model, "n_trajectories": n_traj,
             "modes": results}, indent=2))
        print(f"\nwrote {args.out}")
    return 0


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--data-root",
                    default="datasets/aime_qwen3_1p7b_16k_fp16/aime")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=str, default=None)
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
