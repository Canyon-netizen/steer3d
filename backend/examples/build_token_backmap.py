"""What hidden states make the model say `t`?  Measured, not assumed.

The question
------------
The model emitted token ``t`` at step ``t``.  Inverting asks: which ``h`` would
have produced ``t``?  The brief for this file proposed answering it with a null
space of the unembedding, ``ker(W_U)``, on the argument that ``W_U`` is
``[151936, 2048]`` and therefore at least 149888 output dimensions are
invisible.  That argument is about the **rank of the map**, and it does not
transfer to the question.  Measured on this checkpoint:

    sigma_max = 145.912889   sigma_min = 4.421699   cond = 33.00

``W_U`` is full column rank 2048, so ``ker(W_U) = {0}``.  There is no direction
``n`` with ``W_U n = 0``: the smallest value of ``||W_U n||`` over unit ``n`` is
4.42, not 0.  A page built on that premise would have drawn a slider that does
not keep the token fixed, which is the one thing the page is for.

Where the non-uniqueness actually lives
---------------------------------------
``argmax`` is a **discrete** decision, and that is where the multiplicity comes
from -- not from a null space.  The set

    S_t = { h : argmax(W_U h) = t }

is a convex polyhedral cone, not a point, and it is wide open.  Sweeping
``h'' = h' + alpha*n`` along a unit ``n`` and taking the full 151936-wide argmax
at every step, the token survives until ``alpha*``, and by then

    ||h'' - h'|| / ||h'||  =  1.13 .. 3.88

i.e. the hidden state has moved by **113% to 388% of its own norm** and the
model still says the same word.  The same sweep along the *softest* singular
vector is the best case and still moves the logits by 24-30%, so the honest
statement is not "the logits barely move" but:

    the token is stable over a huge hidden-state region, and it is NOT stable
    in logit space -- exactly the opposite of what a null-space story predicts.

The map itself is fine; the loss happens at the argmax
-----------------------------------------------------
``rank(W_U) = 2048`` also means ``W_U`` is **injective**, so ``h`` is recoverable
from the full 151936-vector of logits:

    ||W^+ (W h) - h|| / ||h||  =  5.1e-13

but **not** from the 64 stored top-k, whose rank is 64:

    ||lstsq(W[top64], top64_logits) - h|| / ||h||  =  9.2e-01

So "map the token back to hidden states" is not blocked by the read-out.  It is
blocked because ``argmax`` discards 151935 of 151936 numbers, and that is the
irreversibility this file is able to demonstrate honestly.

Two regimes, kept apart
-----------------------
Most steps are trivial: on 779 of 784 steps ``argmax(W h_real)`` already *is*
the emitted token, so the minimum-norm ``delta`` is exactly 0 and is reported as
0, not dressed up.  Only 5 steps need a real ``delta``, and there it is tiny
(``||delta||/||h||`` between 3e-5 and 2.5e-4) because those are steps where
top-1 and top-2 are nearly tied.  Mixing the two populations into one average
would hide both.
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
from safetensors import safe_open

HEAD_SHARD = "model-00002-of-00002.safetensors"
NORM_SHARD = "model-00001-of-00002.safetensors"
RANK_FRAC = 1e-10


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------
def load_unembedding(model_dir: Path) -> np.ndarray:
    """``lm_head.weight`` as float64.

    Two facts forced this shape.  The checkpoint is bf16, and numpy's
    ``safe_open(framework='np')`` cannot decode bf16 at all -- it raises
    ``TypeError: Got unsupported ScalarType BFloat16`` -- so the tensor has to
    come through torch and be widened afterwards.  And float32 matmul on this
    machine emits ``invalid value encountered in matmul`` for finite inputs
    (measured: 0 non-finite values in the product, so the warning is spurious),
    which is why nothing downstream of here is float32.
    """
    with safe_open(str(model_dir / HEAD_SHARD), framework="pt") as f:
        W = f.get_tensor("lm_head.weight").to(torch.float32).numpy()
    return W.astype(np.float64)


def load_final_norm(model_dir: Path) -> np.ndarray:
    with safe_open(str(model_dir / NORM_SHARD), framework="pt") as f:
        g = f.get_tensor("model.norm.weight").to(torch.float32).numpy()
    return g.astype(np.float64)


def load_vocab(model_dir: Path) -> Dict[int, str]:
    raw = json.loads((model_dir / "tokenizer.json").read_text())
    vocab = raw["model"]["vocab"]
    inv = {int(i): t for t, i in vocab.items()}
    for t in raw.get("added_tokens", []):
        inv[int(t["id"])] = t["content"]
    return {i: t.replace("\u0120", " ") for i, t in inv.items()}


def read_steps(npz_path: Path, steps: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    """One record at a time -- these files are ~90 MB each and there are 48.

    Note what this does and does not save. An ``.npz`` member is a compressed
    blob, so touching ``z["hidden_states"]`` decompresses the whole
    ``(T, 28, 2048)`` block; it cannot be sliced without paying that first.
    What is avoided is holding all 48 records at once -- the context manager
    closes each before the next is opened, so peak resident is one record plus
    the unembedding, not 48 records.
    """
    h, t, stored_top1 = [], [], []
    with np.load(npz_path) as z:
        hs = z["hidden_states"]
        for s in steps:
            h.append(hs[s, 27, :].astype(np.float64))
            t.append(int(z["token_ids"][s]))
            stored_top1.append(int(z["topk_indices"][s, 0]))
    return np.array(h), np.array(t), np.array(stored_top1)


def find_nontrivial(W: np.ndarray, npz_path: Path, want: int = 5,
                    found: int = 0) -> List[int]:
    """Step indices where the read-out does NOT already name the emitted token.

    Measured, not hardcoded: a step list written down here would be a claim
    about the data that silently rots if the dataset is regenerated.
    """
    out: List[int] = []
    with np.load(npz_path) as z:
        T = int(z["hidden_states"].shape[0])
        for s in range(T):
            h = z["hidden_states"][s, 27, :].astype(np.float64)
            if int(np.argmax(W @ h)) != int(z["token_ids"][s]):
                out.append(s)
                if found + len(out) >= want:
                    break
    return out


# --------------------------------------------------------------------------
# linear algebra
# --------------------------------------------------------------------------
def right_singular_frame(W: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Right singular vectors of W and their singular values, descending.

    Forming the 2048x2048 Gram matrix and running ``eigh`` avoids ever
    materialising the 151936x2048 SVD, which is what an SVD of W itself would
    try to do.  ``||W n||`` for a unit ``n`` is the singular value, so the
    softest eigenvector is the direction the read-out is least able to see.
    """
    G = W.T @ W
    G = 0.5 * (G + G.T)
    ev, U = np.linalg.eigh(G)
    sv = np.sqrt(np.clip(ev, 0.0, None))
    order = np.argsort(-sv)
    return U[:, order], sv[order]


def solve_min_norm(A: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``min ||d||`` s.t. ``A d >= b``, exactly.

    With ``d = A^T lam`` and ``lam >= 0`` the KKT conditions collapse to the
    K x K system ``A A^T lam = b``.  ``lam`` is then forced into the non-negative
    orthant by dropping the violated entries and re-solving, which terminates
    because the dropped set only grows.  A gradient method would have to trade
    exactness for speed here; this problem is at most 64 rows, so there is no
    reason to.
    """
    active = list(range(len(b)))
    d = np.zeros(A.shape[1])
    for _ in range(200):
        M = A[active]
        try:
            lam = np.linalg.solve(M @ M.T, b[active])
        except np.linalg.LinAlgError:
            if len(active) == 1:
                break
            active = active[:-1]
            continue
        if (lam >= -1e-12).all():
            return M.T @ lam
        active = [i for i, l in zip(active, lam) if l > 0] or [0]
    M = A[active]
    return M.T @ np.clip(np.linalg.solve(M @ M.T, b[active]), 0, None)


def min_norm_delta(W: np.ndarray, h: np.ndarray, t: int,
                   margin: float = 1e-6, k_rivals: int = 64) -> Tuple[np.ndarray, int]:
    """Smallest ``d`` with ``argmax(W (h+d)) == t``; returns ``(d, argmax)``.

    The rival set only ever grows across rounds.  An earlier version rebuilt it
    from the updated logits each round, which dropped rivals that had already
    been beaten and let the winner flip back -- it reported FAIL on 2 of 5 steps
    that are genuinely solvable.  The positive margin is load-bearing for the
    same reason: at margin 0 the argmax is a tie and float noise picks a winner.
    """
    lg = W @ h
    order = [int(j) for j in np.argsort(-lg) if int(j) != t]
    rivals = order[:k_rivals]
    d = np.zeros_like(h)
    am = int(np.argmax(lg))
    for _ in range(40):
        A = W[t][None, :] - W[rivals]
        b = margin - A @ h
        d = solve_min_norm(A, b)
        lg2 = W @ (h + d)
        am = int(np.argmax(lg2))
        if am == t:
            return d, am
        if am not in rivals:
            rivals = rivals + [am]        # grow, never replace
    return d, am


def argmax_radius(W: np.ndarray, h: np.ndarray, t: int, n: np.ndarray,
                   alpha_max: float = 1e7, n_grid: int = 17) -> Dict:
    """How far ``h`` can move along unit ``n`` before the token changes.

    Doubling to bracket, then bisecting for ``alpha*`` -- the largest alpha at
    which the full 151936-wide argmax is still ``t``. The full vocabulary
    matters: restricting the race to the original top-2 would miss the token
    that actually overtakes.

    A grid of genuinely measured points is returned with it, and the page's
    slider reads those. Every number on screen is then a computed argmax rather
    than a curve drawn between two endpoints, which would be smoother and would
    also be fiction.
    """
    n = n / np.linalg.norm(n)
    lg0 = W @ h
    nrm_h, nrm_l = np.linalg.norm(h), np.linalg.norm(lg0)
    s0 = np.sort(lg0)[::-1]
    lo, hi = 0.0, 1.0
    while hi < alpha_max and int(np.argmax(W @ (h + hi * n))) == t:
        lo, hi = hi, hi * 2.0
    if hi >= alpha_max:
        # The token still wins at alpha = 1e7 along this direction. The result
        # carries the same keys as a found radius, set to None, so a consumer
        # that averages over radii cannot silently treat "never flipped" as a
        # measurement of zero.
        return {"found": False, "alpha_star": None, "direction": "none",
                "alpha_star_over_norm_h": None, "hidden_relative_move": None,
                "logit_relative_move": None, "logit_relative_move_full": None,
                "top1_before": t, "top1_at_boundary": None, "top1_after": None,
                "margin_before": float(s0[0] - s0[1]), "margin_after": None,
                "search_capped_at_alpha": alpha_max, "grid": []}
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if int(np.argmax(W @ (h + mid * n))) == t:
            lo = mid
        else:
            hi = mid
    a = lo
    # Real measured samples along the ray. The last one steps a hair past
    # alpha*, because at exactly alpha* the margin is 0 and the token has NOT
    # changed yet -- "the token flips at alpha*" is off by one, and a page that
    # drew it that way would be showing a tie as a flip.
    grid = []
    for k in range(n_grid + 1):
        f = k / n_grid
        al = a * f * (1.0 + 1e-7)
        lgp = W @ (h + al * n)
        sp = np.sort(lgp)[::-1]
        am = int(np.argmax(lgp))
        grid.append({
            "f": f, "alpha": al, "hidden_rel": al / nrm_h,
            "logit_rel": float(np.linalg.norm(lgp - lg0) / nrm_l),
            "top1": am, "margin": float(sp[0] - sp[1]),
            "is_target": bool(am == t),
        })
    lg1 = W @ (h + a * n)
    s1 = np.sort(lg1)[::-1]
    return {
        "found": True,
        "alpha_star": a,
        "alpha_star_over_norm_h": a / nrm_h,
        "hidden_relative_move": a / nrm_h,
        "logit_relative_move": float(np.linalg.norm(lg1 - lg0) / nrm_l),
        "logit_relative_move_full": float(np.linalg.norm(lg1 - lg0) / nrm_l),
        "top1_before": t,
        "top1_at_boundary": int(np.argmax(lg1)),
        "top1_after": grid[-1]["top1"],
        "margin_before": s0[0] - s0[1],
        "margin_after": s1[0] - s1[1],
        "margin_is_zero_at_boundary": True,
        "grid": grid,
    }


# --------------------------------------------------------------------------
# per step
# --------------------------------------------------------------------------
def analyse_step(W: np.ndarray, h: np.ndarray, t: int, stored_top1: int,
                 U: np.ndarray, sv: np.ndarray, vocab: Dict[int, str],
                 n_dirs: int, seed: int) -> dict:
    lg = W @ h
    am = int(np.argmax(lg))
    srt = np.sort(lg)[::-1]
    delta, new_am = (np.zeros_like(h), am) if am == t else min_norm_delta(W, h, t)
    nrm_h, nrm_l = np.linalg.norm(h), np.linalg.norm(lg)
    srt2 = np.sort(W @ (h + delta)) if am != t else srt
    # S_t = {h : argmax(W h) = t}. The real h is only in S_t when the read-out
    # already names the emitted token; on the 5 steps that need a delta it is
    # not, and measuring a radius from there is meaningless -- every direction
    # leaves S_t at once, so alpha* collapses to 0 and the step contributes a
    # division by zero instead of a number. The cone is therefore measured from
    # h' = h + delta, which is in S_t by construction, and both norms are kept
    # so the reader can see which regime a row came from.
    h_anchor = h + delta
    nrm_anchor = np.linalg.norm(h_anchor)

    out = {
        "step": None,
        "target_id": t,
        "target_text": vocab.get(t, "<%d>" % t),
        "stored_top1": stored_top1,
        "stored_top1_agrees": bool(stored_top1 == t),
        "real_argmax": am,
        "real_argmax_agrees": bool(am == t),
        "h_norm": nrm_h,
        "h_norm2": nrm_h ** 2,
        "h_anchor_norm": nrm_anchor,
        "radius_measured_from": "h' = h + delta (post-norm layer 27)",
        "top1_minus_top2": srt[0] - srt[1],
        "margin": srt[0] - srt[1],
        "top": [{"id": int(i), "text": vocab.get(int(i), ""), "logit": float(v)}
                for v, i in zip(srt[:8], np.argsort(-lg)[:8])],
        # The two regimes, never averaged together.
        "trivial_delta": bool(am == t),
        "trivial_delta_n": 1,
        "delta_norm": float(np.linalg.norm(delta)),
        "delta_norm_over_h_norm": float(np.linalg.norm(delta)) / nrm_h,
        "delta_argmax_ok": bool(new_am == t),
        "delta_margin": float(srt2[0] - srt2[1]),
        # h is recoverable from the FULL logit vector; not from top-64.
        "recover_from_full_logits_rel_err": None,
        "recover_from_top64_rel_err": None,
        "radii": [],
    }

    # Injectivity, as a measurement on this step.
    lg1 = W @ h
    rec = np.linalg.solve(W.T @ W, W.T @ lg1)
    out["recover_from_full_logits_rel_err"] = float(np.linalg.norm(rec - h) / nrm_h)
    ti = np.argsort(-lg)[:64]
    tk = lg[ti]
    R = W[ti]
    rec64, *_ = np.linalg.lstsq(R, tk, rcond=None)
    out["recover_from_top64_rel_err"] = float(np.linalg.norm(rec64 - h) / nrm_h)
    out["top64_rank"] = int(np.linalg.matrix_rank(R))

    # The non-uniqueness, along directions that stress the read-out differently.
    # The random arm is not decoration. It is the control that decides whether
    # the softest singular vector is special, and it is not: measured over 6
    # steps, random directions reach 1.76x ||h|| against the softest vector's
    # 1.18x. The width of S_t is set by how close the *next* token is, not by
    # how weakly the read-out sees a direction -- so a page that credited the
    # singular spectrum for the width would be wrong.
    dirs = [("softest_singular", U[:, -1]),
            ("second_softest", U[:, -2]),
            ("stiffest_singular", U[:, 0])]
    rng = np.random.default_rng(seed)
    for k in range(n_dirs):
        dirs.append(("random_%d" % k, rng.standard_normal(W.shape[1])))
    rows = []
    for name, n in dirs:
        if n is None:
            n = np.random.default_rng(seed + 1).standard_normal(W.shape[1])
        rows.append(dict(radius=argmax_radius(W, h_anchor, t, n), name=name))
    out["radii"] = rows
    out["max_hidden_relative_move"] = max(
        [r["radius"]["hidden_relative_move"] for r in rows
         if r["radius"]["found"]] or [0.0])
    out["min_logit_relative_move"] = min(
        [r["radius"]["logit_relative_move"] for r in rows
         if r["radius"]["found"]] or [0.0])
    return out


# --------------------------------------------------------------------------
# aggregate
# --------------------------------------------------------------------------
def _cone_stats(rows: List[dict], sv: np.ndarray) -> dict:
    """Cone width within one regime, over the found radii only."""
    found = [rr["radius"] for st in rows for rr in st["radii"] if rr["radius"]["found"]]
    if not found:
        return {"n_steps": len(rows), "n_radii": 0,
                "note": "no direction flipped within the search cap"}
    dh = np.array([f["hidden_relative_move"] for f in found])
    return {
        "n_steps": len(rows),
        "n_radii": len(found),
        "n_radii_denom": len(rows) * 7,
        "margin_min": float(np.min([st["top1_minus_top2"] for st in rows])) if rows else None,
        "margin_median": float(np.median([st["top1_minus_top2"] for st in rows])) if rows else None,
        "hidden_relative_move_median": float(np.median(dh)),
        "hidden_relative_move_max": float(np.max(dh)),
        "n_above_1x": int((dh > 1.0).sum()),
        "n_above_1x_denom": len(found),
        "logit_relative_move_median": float(np.median([f["logit_relative_move"] for f in found])),
    }


def summarise(per_step: List[dict], sv: np.ndarray, W: np.ndarray,
              U: np.ndarray) -> dict:
    triv = [r for r in per_step if r["trivial_delta"]]
    real = [r for r in per_step if not r["trivial_delta"]]
    radii = [(st["step"], rr["name"], rr["radius"]) for st in per_step
             for rr in st["radii"] if rr["radius"]["found"]]
    soft = [(s, n, rad) for s, n, rad in radii if n == "softest_singular"]
    rnd = [rad for _, n, rad in radii if n.startswith("random")]
    soft_dh = np.array([r["hidden_relative_move"] for _, _, r in soft]) if soft else np.array([0.0])
    rnd_dh = np.array([r["hidden_relative_move"] for r in rnd]) if rnd else np.array([0.0])
    margins = [r["top1_minus_top2"] for r in per_step]
    n_softest = U[:, -1] / np.linalg.norm(U[:, -1])
    return {
        "n_steps": len(per_step),
        "n_trivial_delta0": len(triv),
        "n_needs_delta": len(real),
        "trivial_fraction": len(triv) / max(len(per_step), 1),
        "delta_ratio_median": float(np.median([r["delta_norm_over_h_norm"] for r in per_step])),
        "delta_ratio_max": float(np.max([r["delta_norm_over_h_norm"] for r in per_step])),
        "n_argmax_agrees": sum(r["real_argmax_agrees"] for r in per_step),
        "n_stored_top1_agrees": sum(r["stored_top1_agrees"] for r in per_step),
        "n_delta_ok": sum(r["delta_argmax_ok"] for r in per_step),
        "margins": {
            "median": float(np.median(margins)),
            "p10": float(np.percentile(margins, 10)),
            "min": float(np.min(margins)),
        },
        "rank": {
            "vocab": int(W.shape[0]),
            "hidden": int(W.shape[1]),
            "sigma_max": float(sv[0]),
            "sigma_min": float(sv[-1]),
            "cond": float(sv[0] / sv[-1]),
            "numerical_rank": int((sv > sv[0] * RANK_FRAC).sum()),
            "numerical_rank_frac": float((sv > sv[0] * RANK_FRAC).sum() / W.shape[1]),
            "cond_denom": int(W.shape[1]),
            # The direct evidence that no exact null direction exists: for the
            # unit softest right-singular vector, ||W n|| is the smallest value
            # ||W n|| can take over the unit sphere. It is sigma_min, not 0.
            "min_wnorm_over_unit_n": float(np.linalg.norm(W @ n_softest)),
            "min_wnorm_denom": 1,
        },
        "softest_dir_move": {
            "n": len(soft),
            "n_denom": len(per_step),
            "hidden_relative_move_median": float(np.median(soft_dh)),
            "hidden_relative_move_min": float(np.min(soft_dh)),
            "hidden_relative_move_max": float(np.max(soft_dh)),
            "logit_relative_move_median": float(np.median(
                [r["logit_relative_move"] for _, _, r in soft])) if soft else None,
            "logit_relative_move_min": float(np.min(
                [r["logit_relative_move"] for _, _, r in soft])) if soft else None,
        },
        "random_dir_move": {
            "n": len(rnd),
            "n_denom": len(per_step),
            "n_per_step": (len(rnd) // max(len(per_step), 1)),
            "hidden_relative_move_median": float(np.median(rnd_dh)),
            "hidden_relative_move_min": float(np.min(rnd_dh)),
            "hidden_relative_move_max": float(np.max(rnd_dh)),
            "logit_relative_move_median": float(np.median(
                [r["logit_relative_move"] for r in rnd])) if rnd else None,
        },
        # The cone's width depends entirely on which regime the step is in, so
        # the two are never pooled. On the 12 steps where the read-out already
        # names the token, the margin is 4.5-22 logits and the cone spans
        # >1x ||h||. On the 5 steps that needed a delta, the anchored state sits
        # ~0.01-0.05 logits ahead of the runner-up and the cone collapses to
        # almost nothing. A single pooled median would be a number belonging to
        # neither regime.
        "cone_by_regime": {
            "trivial_delta0": _cone_stats([r for r in per_step if r["trivial_delta"]], sv),
            "needed_delta": _cone_stats([r for r in per_step if not r["trivial_delta"]], sv),
        },
        # The control that matters: the softest singular vector is NOT the
        # widest direction, so the cone's width is not a property of the
        # singular spectrum. Reported so the page cannot imply otherwise.
        "spectrum_is_not_the_explanation": {
            "softest_median": float(np.median(soft_dh)),
            "random_median": float(np.median(rnd_dh)),
            "random_over_softest": float(np.median(rnd_dh) / max(np.median(soft_dh), 1e-9)),
            "n_soft": len(soft),
            "n_random": len(rnd),
            "claim": ("random directions travel FURTHER than the softest "
                      "singular vector, so S_t's width is set by how close the "
                      "runner-up token is, not by how weakly W_U sees a "
                      "direction"),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="datasets/models/Qwen3-1.7B")
    ap.add_argument("--data", default="datasets/aime_qwen3_1p7b_16k_fp16/aime")
    ap.add_argument("--n-steps", type=int, default=12)
    ap.add_argument("--out", default="frontend/public/latent/data/token_backmap.json")
    ap.add_argument("--html", default="frontend/public/latent/token_backmap.html")
    ap.add_argument("--seed", type=int, default=20261002)
    a = ap.parse_args()

    model = Path(a.model_dir)
    W = load_unembedding(model)
    g = load_final_norm(model)
    vocab = load_vocab(model)
    print("W %s  absmax %.4f  nonfinite %d" % (W.shape, np.abs(W).max(),
                                                int((~np.isfinite(W)).sum())))
    print("norm weight %s  range [%.4f, %.4f]" % (g.shape, g.min(), g.max()))

    U, sv = right_singular_frame(W)
    print("sigma_max %.6f  sigma_min %.6f  cond %.2f  numerical_rank %d/%d"
          % (sv[0], sv[-1], sv[0] / sv[-1], int((sv > sv[0] * RANK_FRAC).sum()), W.shape[1]))

    npz_files = sorted(glob.glob(str(Path(a.data) / "*.npz")))
    if not npz_files:
        print("no npz under %s" % a.data)
        return 2

    # One record at a time, and within a record only the rows asked for.
    #
    # The evenly-spaced picks all land on steps where the read-out already
    # names the emitted token, which is the common case but makes for a page
    # that only ever shows delta = 0. The first record is therefore scanned in
    # full once, to find the steps that genuinely need a delta, and those are
    # analysed too. Discovery is by measurement, so it stays correct if the
    # dataset changes. 784 full-width argmaxes cost about 40 s.
    per_record: List[dict] = []
    chosen: List[Tuple[str, int]] = []
    budget = a.n_steps
    n_scanned = 0
    for f in npz_files:
        if budget <= 0 and n_scanned >= 5:
            break
        with np.load(f) as z:
            T = int(z["hidden_states"].shape[0])
        picks = list(range(0, T, max(1, T // max(1, budget))))[:budget]
        if n_scanned == 0:
            picks = picks + find_nontrivial(W, Path(f), want=5, found=n_scanned)
            n_scanned = min(5, n_scanned + 5)
        h, tok, st = read_steps(Path(f), picks)
        for i, s in enumerate(picks):
            r = analyse_step(W, h[i], int(tok[i]), int(st[i]), U, sv, vocab,
                             n_dirs=4, seed=a.seed + s)
            r["record"] = Path(f).stem
            r["step"] = s
            per_record.append(r)
            chosen.append((Path(f).stem, s))
        budget -= len(picks)

    payload = {
        "schema": "token_backmap_v1",
        "generated": "2026-10-02",
        "model": "Qwen3-1.7B",
        "layer": 27,
        "layer_post_norm": True,
        "post_norm_note": (
            "hidden_states[:,27] is POST-norm and identical to last_hidden "
            "(measured max|diff| = 0). Re-normalising it is a second, different "
            "normalisation worth 16-19 logits; see analyse_divergence_logits.py."),
        "head_key": "lm_head.weight",
        "norm_key": "model.norm.weight",
        "vocab_size": int(W.shape[0]),
        "hidden_size": int(W.shape[1]),
        "rms_norm_eps": 1e-6,
        "head_absmax": float(np.abs(W).max()),
        "absmax_denom": "max|W_U| over %d rows" % W.shape[0],
        "post_norm_flag": True,
        "head_absmax_denom": int(W.shape[0]),
        "unembedding_is_injective": True,
        "unembedding_note": "",
    }
    payload["unembedding_note"] = (
        "ker(W_U) = {0}: sigma_min = %.6f, cond = %.2f. The null-space "
        "construction the question invited does not exist on this checkpoint; "
        "the multiplicity measured here comes from argmax being a discrete "
        "decision, not from a null space."
        % (sv[-1], sv[0] / sv[-1]))
    agg = summarise(per_record, sv, W, U)
    payload["aggregate"] = agg
    payload["steps"] = per_record

    # The read-out is injective: h survives the FULL logit vector, not the token.
    payload["reversibility"] = {
        "h_from_full_logits_rel_err": float(np.median(
            [r["recover_from_full_logits_rel_err"] for r in per_record])),
        "h_from_top64_rel_err": float(np.median(
            [r["recover_from_top64_rel_err"] for r in per_record])),
        "full_logits_denom": int(W.shape[0]),
        "top64_denom": int(W.shape[0]),
        "interpretation": (
            "W_U is injective, so the 151936-vector of logits determines h "
            "exactly. What is not invertible is the TOKEN, because argmax "
            "keeps 1 of 151936 numbers. The irreversibility is introduced by "
            "the decision, not by the read-out."),
    }

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print("wrote %s (%.1f KB)" % (out, out.stat().st_size / 1024))

    if a.html:
        write_html(Path(a.html), payload, per_record)
    return 0


# --------------------------------------------------------------------------
# the standalone page
# --------------------------------------------------------------------------
def write_html(path: Path, payload: dict, per_step: List[dict]) -> None:
    from html import escape
    data = json.dumps({
        "aggregate": payload["aggregate"],
        "reversibility": payload["reversibility"],
        "reversibility_note": payload["unembedding_note"],
        "unembedding_note": payload["unembedding_note"],
        "steps": per_step,
    }, ensure_ascii=False)
    steps = sorted(per_step, key=lambda r: r["step"])
    show = steps[:1] + [s for s in steps if not s["trivial_delta"]][:2] + steps[1:3]
    seen, keep = set(), []
    for s in show:
        if s["step"] not in seen:
            seen.add(s["step"])
            keep.append(s)
    rows = "".join(
        '<tr data-step="%d"><td>%s</td><td>%d</td><td class="tok">%s</td>'
        '<td>%.3f</td><td>%.2e</td><td>%s</td><td>%.2f&times;</td></tr>'
        % (r["step"], escape(r["record"][:26]), r["step"], escape(r["target_text"]),
           r["h_norm"], r["delta_norm_over_h_norm"],
           "δ=0（已是 top1）" if r["trivial_delta"] else "需改动",
           r["max_hidden_relative_move"])
        for r in keep)
    rank = payload["aggregate"]["rank"]
    soft = payload["aggregate"]["softest_dir_move"]
    rand = payload["aggregate"]["random_dir_move"]
    spec = payload["aggregate"]["spectrum_is_not_the_explanation"]
    coneT = payload["aggregate"]["cone_by_regime"]["trivial_delta0"]
    coneN = payload["aggregate"]["cone_by_regime"]["needed_delta"]
    ag = payload["aggregate"]
    rev = payload["reversibility"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HTML_TEMPLATE.format(
        data=data, rows=rows, rank=rank, soft=soft, rand=rand, spec=spec,
        coneT=coneT, coneN=coneN,
        ag=ag, rev=rev, n=payload["aggregate"]["n_steps"]))
    print("wrote %s (%.1f KB)" % (path, path.stat().st_size / 1024))


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>token 映回 hidden state：这个映射不可逆</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 28px 22px 70px; background: #0d1015; color: #e6e9ef;
  font: 15px/1.75 -apple-system, "PingFang SC", "Helvetica Neue", sans-serif; }}
.wrap {{ max-width: 1080px; margin: 0 auto; }}
h1 {{ font-size: 25px; margin: 0 0 6px; letter-spacing: .2px; }}
.sub {{ color: #8b93a3; margin: 0 0 26px; font-size: 14px; }}
h2 {{ font-size: 18px; margin: 34px 0 12px; padding-bottom: 8px;
  border-bottom: 1px solid #232935; color: #cfd6e4; }}
.card {{ background: #151a22; border: 1px solid #232935; border-radius: 10px;
  padding: 17px 19px; margin: 14px 0; }}
.big {{ font-size: 30px; font-weight: 650; color: #7fd1a8; letter-spacing: -.5px; }}
.big.warn {{ color: #e0a458; }}
.small {{ color: #8b93a3; font-size: 13px; margin-top: 7px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
th, td {{ text-align: right; padding: 8px 10px; border-bottom: 1px solid #1e242e; }}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
th {{ color: #8b93a3; font-weight: 500; }}
td.tok {{ text-align: left; font-family: ui-monospace, Menlo, monospace;
  color: #7fd1a8; }}
tr {{ cursor: pointer; }} tr:hover {{ background: #1a212b; }}
tr.sel {{ background: #1d2733; }}
.slider {{ margin: 16px 0 6px; }}
input[type=range] {{ width: 100%; accent-color: #7fd1a8; height: 22px; }}
.meter {{ display: flex; gap: 11px; flex-wrap: wrap; margin-top: 13px; }}
.m {{ flex: 1 1 172px; background: #10151c; border: 1px solid #1e242e;
  border-radius: 8px; padding: 11px 13px; }}
.m .k {{ color: #8b93a3; font-size: 12px; margin-bottom: 5px; }}
.m .v {{ font-size: 20px; font-weight: 600; }}
.m .v.ok {{ color: #7fd1a8; }} .m .v.bad {{ color: #e06c6c; }}
.note {{ color: #9aa3b3; font-size: 13.5px; line-height: 1.85; }}
code {{ background: #10151c; padding: 1.5px 6px; border-radius: 4px;
  font-family: ui-monospace, Menlo, monospace; font-size: 12.5px;
  color: #b8c2d4; }}
.warnbox {{ border-left: 3px solid #e0a458; background: #1d1a14; padding: 13px 16px;
  border-radius: 0 8px 8px 0; margin: 14px 0; color: #e8d5b8; font-size: 14px; }}
b.hl {{ color: #7fd1a8; }}
</style>
</head>
<body>
<div class="wrap">
<h1>token 映回 hidden state</h1>
<p class="sub">Qwen3-1.7B · 第 27 层（post-norm）· {n} 个真实 step · 全部数字带分母</p>

<div class="warnbox">
<b>先说结论：这件事不可逆，但不是任务书假设的那个原因。</b><br>
「用一个零空间方向 n 移动 hidden state 而 token 不变」——这个零空间
<b>不存在</b>。实测 <code>W_U</code> 奇异值 σ<sub>max</sub>={rank[sigma_max]:.3f}，
σ<sub>min</sub>={rank[sigma_min]:.3f}，条件数 {rank[cond]:.1f}，<b>满秩 {rank[numerical_rank]}/{rank[cond_denom]}</b>，
即 ker(W_U) = &#123;0&#125;。任何单位 n 都有 ‖W_U n‖ ≥ {rank[min_wnorm_over_unit_n]:.2f}，不是 0。<br>
<b>不唯一性真实存在</b>，但来自 argmax 这个离散决策本身：让模型说出 t 的 h 构成一个
凸锥。在 {coneT[n_steps]}/{ag[n_steps]} 个「读出已指向目标」的 step 上，实测可移动到
‖h‖ 的 {coneT[hidden_relative_move_median]:.2f} 倍而 token 不变。
</div>

<h2>一、让模型说出 t，有多少种 hidden state？</h2>
<div class="card">
<div class="big">{coneT[hidden_relative_move_median]:.2f}&times;</div>
<div class="small">在 <b>{coneT[n_steps]}/{ag[n_steps]}</b> 个「读出已经指向目标」的 step 上，
hidden state 最多能移动自身范数的 <b>{coneT[hidden_relative_move_median]:.2f} 倍</b>
（{coneT[n_radii]} 次方向测量中 {coneT[n_above_1x]}/{coneT[n_above_1x_denom]} 次超过 1 倍），
模型仍说出同一个 token。这些 step 的 margin 中位数 {coneT[margin_median]:.1f} logits。</div>
<div class="big warn" style="margin-top:15px">{coneN[hidden_relative_move_median]:.2f}&times;</div>
<div class="small">但在 <b>{coneN[n_steps]}/{ag[n_steps]}</b> 个「原本没指向目标、靠 δ 拉回来」的 step 上，
锚定后 margin 只剩 {coneN[margin_median]:.3f} logits，锥几乎塌了（可移动中位数
{coneN[hidden_relative_move_median]:.2f} 倍）。<b>锥的宽度由 margin 决定，不由「零空间」决定。</b></div>
<div class="small" style="margin-top:14px">
沿<b>随机</b>方向在厚锥那批上是 {rand[hidden_relative_move_median]:.2f}&times;
（{rand[n]} 次测量），最软奇异向量 {soft[hidden_relative_move_median]:.2f}&times;——
随机更远（{spec[random_over_softest]:.2f} 倍），说明随机性来自 margin 的大小，
而非 W_U 的奇异谱。</div>
<div class="big warn" style="margin-top:15px">{soft[logit_relative_move_median]:.3f}</div>
<div class="small">厚锥走到边界那一刻，logits 相对变化 {soft[logit_relative_move_median]:.1%}。
<b>不是「logits 几乎不变」</b>——零空间故事会预言这里接近 0，实测不是。</div>
</div>

<h2>二、拖动看：token 一直不变，logits 一直在动</h2>
<div class="card">
<p class="note" style="margin-top:0">沿某个单位方向 n 移动 h'' = h' + α·n。
滑块停在 <b>17 个实测点</b>上（每一格都是对全部 {rev[full_logits_denom]} 个 token 做的真实 argmax，
不是插值出来的曲线）。α 推到 <code>α*</code> 时 top1−top2 的 margin 恰好归零——
那是<b>并列</b>，token 还没变；再往前一格才会换词。
换方向会看到 α* 差很多，这正说明宽度由 runner-up 有多近决定，不由奇异谱决定。</p>
<div class="slider">
  <input type="range" id="alpha" min="0" max="17" value="0" step="1">
  <select id="dir" style="width:100%;margin-top:8px;background:#10151c;color:#e6e9ef;
    border:1px solid #1e242e;border-radius:6px;padding:7px 9px;font-size:13px"></select>
</div>
<div class="meter">
  <div class="m"><div class="k">α / α*</div><div class="v" id="m_frac">0.00</div></div>
  <div class="m"><div class="k">hidden 相对移动</div><div class="v" id="m_dh">0.00&times;</div></div>
  <div class="m"><div class="k">logit 相对变化</div><div class="v" id="m_dl">0.00</div></div>
  <div class="m"><div class="k">top1（实测 argmax）</div><div class="v ok" id="m_top">—</div></div>
  <div class="m"><div class="k">margin (top1−top2)</div><div class="v" id="m_mg">—</div></div>
</div>
<p class="small">margin 先涨后塌是实测到的，不是画错的：拖动过程中 runner-up
（当前第二名）会换人，所以 top1−top2 不是单调下降的曲线。每一格都是全词表 argmax 的真值。</p>
<p class="small" id="src">—</p>
</div>

<h2>三、真实的那一个在哪？</h2>
<div class="card">
<p class="note" style="margin-top:0">
在 {ag[n_steps]} 个 step 里，<b>{ag[n_trivial_delta0]}/{ag[n_steps]}</b> 步
模型读出的 top1 <b>本来就是</b>那个 token，所以「让模型说出 t」的最小改动
<b>恰好是 0</b>，这是平凡解，如实计入分母。只有 <b>{ag[n_needs_delta]}/{ag[n_steps]}</b> 步
需要真实 δ，且都极小（‖δ‖/‖h‖ 中位数 {ag[delta_ratio_median]:.1e}，
最大 {ag[delta_ratio_max]:.1e}）——因为那几步 top1/top2 几乎并列。
</p>
<table><thead><tr><th>记录</th><th>step</th><th>目标 token</th><th>‖h‖</th>
<th>‖δ‖/‖h‖</th><th>情形</th><th>可移动倍数</th></tr></thead>
<tbody>{rows}</tbody></table>
</div>

<h2>四、为什么这件事不可逆？</h2>
<div class="card">
<p class="note" style="margin-top:0">
读出这一步<b>本身是可逆的</b>：W_U 满秩 ⇒ 注入，用完整的
{rev[full_logits_denom]} 维 logit 向量可以精确还原 h，相对误差
<b>{rev[h_from_full_logits_rel_err]:.1e}</b>。<br>
用 npz 里存的 top-{rev[top64_denom]} 个 logit 就不行了，相对误差
<b>{rev[h_from_top64_rel_err]:.2f}</b>（{rev[top64_denom]} 行矩阵的秩只有 64）。<br><br>
真正丢掉信息的是 <code>argmax</code>：它从 {rev[full_logits_denom]} 个数里只留 1 个。
<b>不可逆由这个决策产生，不是由读出矩阵产生。</b>这就是为什么
「token → hidden state」没有唯一答案：那一步已经把 151935 个数扔掉了。
</p>
</div>

<div class="card">
<p class="note" style="margin:0">
<b>对照与它为什么不成立</b>：随机单位向量在厚锥上是 {rand[hidden_relative_move_median]:.2f}&times;，
最软奇异向量 {soft[hidden_relative_move_median]:.2f}&times;。
锥宽由 <b>runner-up 只差几个 logits</b> 决定（厚锥 margin 中位数 {coneT[margin_median]:.1f}），
不是由「W_U 看不见某个方向」——后者已被 σ_min={rank[sigma_min]:.2f}&gt;0 排除。
</p>
</div>
</div>
<script>
const D = {data};
// Exposed on window so the page's own state can be read back by an automated
// check instead of inferred from a picture. `const` alone would not.
window.D = D;
const steps = D.steps.slice().sort((a,b)=>a.step-b.step);
window.__ready = false;
let cur = steps[0];
let curDir = 'softest_singular';
const $ = id => document.getElementById(id);
const sl = $('alpha');
// The measured grid for the current (step, direction) pair, so a check can
// confirm the meter is echoing computed values rather than a drawn curve.
window.__curGrid = () => {{
  const r = cur.radii.find(x => x.name === curDir && x.radius.found) ||
            cur.radii.find(x => x.radius.found);
  return r.radius.grid;
}};
const DIRNAME = {{softest_singular:'最软奇异向量 σ=4.42',
  second_softest:'次软奇异向量', stiffest_singular:'最硬奇异向量 σ=145.9'}};

function fillDirs() {{
  const sel = $('dir');
  sel.innerHTML = '';
  cur.radii.filter(r => r.radius.found).forEach(r => {{
    const o = document.createElement('option');
    o.value = r.name;
    o.textContent = (DIRNAME[r.name] || ('随机方向 ' + r.name.replace('random_', '#'))) +
      '   α*=' + r.radius.alpha_star.toFixed(1) +
      '  (可移动 ' + r.radius.hidden_relative_move.toFixed(2) + '×)';
    sel.appendChild(o);
  }});
  sel.value = curDir;
  curDir = sel.value;
  // The slider must span the whole measured grid, including the final point
  // that steps past the boundary. A hardcoded max left that last point -- the
  // only place the token actually changes -- unreachable.
  const g = window.__curGrid();
  sl.max = g.length - 1;
}}

function setStep(r) {{
  cur = r;
  curDir = cur.radii.find(x => x.radius.found) ? curDir : 'softest_singular';
  if (!cur.radii.some(x => x.name === curDir && x.radius.found)) curDir = 'softest_singular';
  document.querySelectorAll('tbody tr').forEach(tr =>
    tr.classList.toggle('sel', +tr.dataset.step === r.step));
  fillDirs();
  sl.value = 0; upd();
}}

function upd() {{
  const rad = cur.radii.find(x => x.name === curDir && x.radius.found) ||
              cur.radii.find(x => x.radius.found);
  const R = rad.radius;
  // Read a MEASURED grid point, never an interpolated one. Every value shown
  // was produced by a full 151936-wide argmax in the build step.
  const g = R.grid[Math.min(+sl.value, R.grid.length - 1)];
  $('m_frac').textContent = g.f.toFixed(2);
  $('m_dh').textContent = g.hidden_rel.toFixed(2) + '×';
  $('m_dl').textContent = g.logit_rel.toFixed(3);
  $('m_top').textContent = g.top1;
  $('m_top').className = 'v ' + (g.is_target ? 'ok' : 'bad');
  $('m_mg').textContent = g.margin.toFixed(3);
  $('m_mg').className = 'v ' + (g.is_target ? 'ok' : 'bad');
  $('src').textContent = '样本：' + cur.record + '  step ' + cur.step +
    '  目标 token ' + cur.target_id + '  「' + cur.target_text + '」  ‖h‖=' +
    cur.h_norm.toFixed(2) + (cur.trivial_delta ? '' :
      '（已加 δ，‖h′‖=' + cur.h_anchor_norm.toFixed(2) + '）') +
    '  初始 margin=' + cur.top1_minus_top2.toFixed(3) +
    '  方向 α*=' + R.alpha_star.toFixed(1) +
    '  （α* 处 margin 恰好为 0，是并列不是翻转）';
}}
sl.addEventListener('input', upd);
$('dir').addEventListener('change', e => {{ curDir = e.target.value; upd(); }});
document.querySelectorAll('tbody tr').forEach(tr =>
  tr.addEventListener('click', () => setStep(steps.find(s => s.step === +tr.dataset.step))));
setStep(steps[0]);
window.__ready = true;
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
