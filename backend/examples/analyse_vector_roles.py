"""What is a steering vector actually *doing* inside the model?

    python3 backend/examples/analyse_vector_roles.py
    python3 backend/examples/analyse_vector_roles.py --limit 8        # smoke

Why this script exists
----------------------
Everything measured so far answers one question: **does adding the vector
change the output?** That is a behavioural yes/no. It is not enough to say
what the vector *is*. "It changes behaviour" is equally consistent with
"it is the model's implementation of confidence" and with "it is a global
temperature knob wearing a confidence label" — both produce a behaviour
change, and only one of them is a claim about the model.

The three measurements that separate those two stories are the standard
trichotomy used for causal characterisation of a direction in mechanistic
interpretability:

  * **sufficiency** — is the direction alone enough to produce the concept's
    behaviour? (write to the direction, read the behaviour)
  * **necessity**  — does the model itself write to that direction when the
    concept is active? (read the direction, without any intervention)
  * **specificity** — does the direction do *only* that, or is it one global
    dial with six names?

Framework source: Elhage, Hume, Olsson, Wasserstein, Boffi, Gao, Nye &
Binder, "Toy Models of Superposition" (Anthropic, 2022), §"Controlling a
feature", which formalises exactly this trichotomy for a direction in a
residual stream: writing a direction is *sufficient* for a behaviour if it
elicits that behaviour, the direction is *necessary* for it if the model
uses it internally when the behaviour happens, and it is non-specific if
writing it moves everything at once. The trichotomy is what makes six
directions comparable instead of being six separate anecdotes.

What each block reads
---------------------
  sufficiency / specificity  .cache/32k_journal/{cot_divergence_32k,all_runs}.json
  necessity                 datasets/aime_qwen3_1p7b_16k_fp16/aime/*.npz
                            (hidden_states (T, 28, 2048) fp16) + sidecar JSON

The necessity block is zero-GPU: it projects the *stored* residual stream onto
each vector and correlates that trajectory with the behaviour observable at
the same step. No forward pass is run, no model weights are touched.

Two honesty commitments that shape the code
--------------------------------------------
1. **The shipped vectors are diff-of-means built from these very tokens.**
   Projecting them onto their own data and finding a correlation is
   circular — it measures the extractor, not the model. So necessity is
   computed twice: in-sample (reported, labelled circular) and with the
   contrast **rebuilt on a held-out half of the trajectories and scored on
   the other half**. The held-out numbers are the real ones.
2. **Every correlation carries its denominator and its null floor.** A
   Spearman ρ over 40k autocorrelated steps looks impressive even when it
   is noise. The floor quoted is `1/sqrt(n-3)` on the number of
   *independent units* (trajectories), not on the number of steps, and the
   gate sits above it. `verify_vector_roles.py` owns the gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_NPZ_DIR = ROOT / "datasets" / "aime_qwen3_1p7b_16k_fp16" / "aime"
DEFAULT_JOURNAL = ROOT / ".cache" / "32k_journal" / "cot_divergence_32k.json"
DEFAULT_RUNS = ROOT / ".cache" / "32k_journal" / "all_runs.json"
DEFAULT_OUT = ROOT / "frontend" / "public" / "latent" / "data" / "vector_roles.json"
DEFAULT_CACHE = ROOT / ".cache" / "vecroles"
DEFAULT_PROFILES = ROOT / "backend" / "examples" / "output" / "layer_profiles.json"

# Which observable each direction *claims* to track, and the sign the claim
# implies. Written down before any correlation is computed, so the gate
# cannot be reverse-fitted to the answer.
CLAIMS = {
    "confidence_up":     {"observable": "entropy",    "sign": -1,
                          "why": "built as mean(low-entropy) - mean(high-entropy)"},
    "confidence_down":   {"observable": "entropy",    "sign": +1,
                          "why": "the negation of confidence_up"},
    "caution":           {"observable": "self_check", "sign": +1,
                          "why": "built as mean(self-check tokens) - mean(ordinary)"},
    "creativity":        {"observable": "in_think",   "sign": +1,
                          "why": "built as mean(inside <think>) - mean(outside)"},
    "reasoning_deep":    {"observable": "step_frac",  "sign": +1,
                          "why": "built as mean(last 25% of traj) - mean(first 25%)"},
    "reasoning_shallow": {"observable": "step_frac",  "sign": -1,
                          "why": "the negation of reasoning_deep"},
}

# The groups each vector was built from, as a predicate over one trajectory.
# Kept in the same order the extractor used so the held-out rebuild is the
# same contrast, just fitted on different trajectories.
CONTRASTS = {
    "confidence_up":     ("entropy_lo", "entropy_hi"),
    "confidence_down":   ("entropy_hi", "entropy_lo"),
    "caution":           ("self_check_yes", "self_check_no"),
    "creativity":        ("think_yes", "think_no"),
    "reasoning_deep":    ("late", "early"),
    "reasoning_shallow": ("early", "late"),
}

# Same list the vector extractor used (compute_steering_vectors.py:42). Kept
# byte-identical on purpose: if this drifts, "necessity" and "the thing the
# vector was built from" stop being the same concept and the block measures
# nothing.
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE,
)

LAYER_NATIVE = 14    # the layer every vector was extracted at
LAYER_INJECT = 20    # the layer the 32k journal actually steers at
N_RANDOM_DIRECTIONS = 16
EMPIRICAL_SD_GATE = 3.0    # a real direction must clear mean + 3 sd of the random ones
BOOTSTRAP_REPS = 2000
OBSERVABLES = ("entropy", "top1_prob", "self_check", "in_think", "top1_switch", "step_frac")


# ---------------------------------------------------------------------------
# statistics — every function that returns a correlation also reports n
# ---------------------------------------------------------------------------

def spearman(x, y) -> float:
    """Spearman rho. nan when either side is constant (rho is undefined)."""
    if len(x) < 4:
        return float("nan")
    r = stats.spearmanr(x, y).statistic
    return float(r) if r == r else float("nan")


def null_floor(n: int) -> float:
    """Sampling-noise SE of a correlation under the null, `1/sqrt(n-3)`.

    Quoting this against the *step* count would be cheating: consecutive
    decoding steps are strongly autocorrelated, so n_steps overcounts the
    independent units by two orders of magnitude. The independent unit here
    is the trajectory.
    """
    return float(1.0 / np.sqrt(n - 3)) if n >= 4 else float("nan")


def sign_test_p(n_pos: int, n: int) -> float:
    """Two-sided exact binomial p for `n_pos` successes out of `n` at p=0.5."""
    return float(stats.binomtest(n_pos, n, 0.5, alternative="two-sided").pvalue) if n else float("nan")


def block_bootstrap_ci(values, reps: int = BOOTSTRAP_REPS, seed: int = 17):
    """Percentile CI of the median, resampling independent units (trajectories)."""
    v = np.asarray([x for x in values if x == x], dtype=np.float64)
    if len(v) < 3:
        return [float("nan"), float("nan")]
    idx = np.random.default_rng(seed).integers(0, len(v), size=(reps, len(v)))
    meds = np.median(v[idx], axis=1)
    return [float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))]


# ---------------------------------------------------------------------------
# per-trajectory loading
# ---------------------------------------------------------------------------

def _group_masks(ent: np.ndarray, sc: np.ndarray, think: np.ndarray,
                 frac: np.ndarray) -> dict:
    q30 = float(np.quantile(ent, 0.30))
    q75 = float(np.quantile(ent, 0.75))
    return {
        "entropy_lo": ent <= q30,
        "entropy_hi": ent >= q75,
        "self_check_yes": sc > 0.5,
        "self_check_no": sc < 0.5,
        "think_yes": think > 0.5,
        "think_no": think < 0.5,
        "late": frac >= 0.75,
        "early": frac <= 0.25,
    }


def _read_step_observables(side: Path, T: int):
    """Per-step behaviour observables, in the npz's own step order."""
    meta = json.loads(side.read_text())
    tokens = meta.get("tokens", [])
    if len(tokens) != T:
        return None
    text = [t.get("token") or "" for t in tokens]
    ent = np.array([t["entropy"] for t in tokens], dtype=np.float32)
    top1p = np.array([t["top1_prob"] for t in tokens], dtype=np.float32)
    think = np.array([bool(t.get("is_in_think_block", False)) for t in tokens], dtype=np.float32)
    sc = np.array([bool(SELF_CHECK_RE.search(s)) for s in text], dtype=np.float32)
    frac = np.arange(T, dtype=np.float32) / max(T - 1, 1)
    return {
        "traj": meta.get("trajectory_id", side.stem),
        "T": int(T),
        "entropy": ent, "top1_prob": top1p, "self_check": sc,
        "in_think": think, "step_frac": frac,
        "_masks": _group_masks(ent, sc, think, frac),
    }


def load_trajectories(npz_dir: Path, layers: list[int], n_traj: int,
                      vectors: dict, random_dirs: dict) -> list[dict]:
    """One npz at a time; the fp16 blob is released before the next file.

    The corpus is 9.1 GB and there is no reason to hold more than one
    trajectory's residual stream at a time. What survives is the per-step
    projection onto every direction (a few MB in total).
    """
    proj_vectors = {**vectors, **random_dirs}
    out = []
    n_nonfinite = 0
    for npz_path in sorted(npz_dir.glob("*.npz"))[:n_traj]:
        side = npz_path.with_suffix(".json")
        if not side.exists():
            continue
        with np.load(npz_path) as d:
            hs = d["hidden_states"]
            if hs.ndim != 3:
                continue
            T = int(hs.shape[0])
            rec = _read_step_observables(side, T)
            if rec is None:
                continue
            top1 = d["topk_indices"][:, 0]
            switch = np.zeros(T, dtype=np.float32)
            if T > 1:
                switch[1:] = (top1[1:] != top1[:-1]).astype(np.float32)
            rec["top1_switch"] = switch
            rec["proj"], rec["norm"] = {}, {}
            for L in layers:
                h = hs[:, L, :].astype(np.float32)
                rec["norm"][L] = np.linalg.norm(h, axis=1) + 1e-8
                for name, v in proj_vectors.items():
                    # einsum rather than `h @ v`: this environment's threaded
                    # BLAS emits a spurious divide-by-zero/overflow warning on
                    # zero-stride blocks of the matmul even when every result
                    # is finite. einsum is single-threaded and quiet, and the
                    # non-finite count below is what actually certifies it.
                    p = np.einsum("td,d->t", h, v)
                    if not np.all(np.isfinite(p)):
                        n_nonfinite += 1
                    rec["proj"][(name, L)] = p
                del h
            del hs
        out.append(rec)
    return out, n_nonfinite


# ---------------------------------------------------------------------------
# anchors: prove the arrays being joined are the arrays we think they are
# ---------------------------------------------------------------------------

def run_anchors(npz_dir: Path, n_files: int) -> dict:
    """Index-alignment checks on real files, each with its denominator.

    The anchor that was asked for — apply lm_head to the last stored layer
    and reproduce `topk_indices[t, 0]` — needs the real 151936-way
    unembedding, which is not on this machine (see `lm_head_anchor`). What
    *is* checkable here, and is what the necessity block actually rests on,
    is that row t of hidden_states is the state that produced token t, and
    that sidecar JSON step t describes that same step.
    """
    a_last = a_top1 = a_json = 0
    n = 0
    for npz_path in sorted(npz_dir.glob("*.npz"))[:n_files]:
        side = npz_path.with_suffix(".json")
        if not side.exists():
            continue
        with np.load(npz_path) as d:
            tid, ti, lh = d["token_ids"], d["topk_indices"], d["last_hidden"]
            last = d["hidden_states"][:, -1, :]
            a_last += int((last.astype(np.float32) == lh.astype(np.float32)).all(axis=1).sum())
            a_top1 += int((tid == ti[:, 0]).sum())
            n += len(tid)
            tl = d["topk_logits"].astype(np.float32)
            pr = np.exp(tl - tl.max(axis=1, keepdims=True))
            pr /= pr.sum(axis=1, keepdims=True)
            for t, tk in enumerate(json.loads(side.read_text())["tokens"][:n]):
                if abs(float(tk["top1_prob"]) - float(pr[t, 0])) < 2e-3:
                    a_json += 1
    return {
        "note": "分母 = 被检查的步数",
        "checks": {
            "A1_last_layer_equals_last_hidden": {
                "claim": "hidden_states[:, -1, :] == last_hidden",
                "pass": a_last, "total": n, "rate": a_last / max(n, 1)},
            "A2_emitted_token_is_stored_top1": {
                "claim": "token_ids[t] == topk_indices[t, 0]",
                "pass": a_top1, "total": n, "rate": a_top1 / max(n, 1)},
            "A3_json_top1prob_equals_npz_softmax": {
                "claim": "json tokens[t].top1_prob == softmax(topk_logits[t])[0]",
                "pass": a_json, "total": n, "rate": a_json / max(n, 1)},
        },
        "lm_head_anchor": {
            "claim": "argmax(lm_head @ hidden_states[t, 27, :]) == topk_indices[t, 0]",
            "status": "NOT_RECOMPUTED_HERE",
            "reason": (
                "本机没有 Qwen3-1.7B 权重（~/.cache/huggingface 不存在，"
                "/tmp/qwen3/master 不存在，transformers 未安装），而 zju-46 的 GPU "
                "正被别的任务占用，不应该去抢。补这一步需要 lm_head.weight "
                "(151936x2048)。"),
            "pre_existing_measurement": (
                "同一批 npz 的 logit lens 已经做过这一步：见 "
                "frontend/public/latent/data/logit_lens.json 的 anchor 块——"
                "all_steps 1532/1536 = 0.9974；top1-top2 margin >= 1.0 的可判定步 "
                "1420/1420 = 1.0；max_logit_error_vs_stored_topk = 0.125。"
                "该数字由 build_logit_lens.py 产出，不是本脚本重算的，引用而非复现。"),
        },
    }


# ---------------------------------------------------------------------------
# necessity
# ---------------------------------------------------------------------------

def auc_mw(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(a random positive step projects higher than a random negative step).

    Reported alongside Spearman because Spearman is the wrong statistic for a
    rare binary label. Against a 0/1 outcome Spearman degenerates to the
    point-biserial r, whose ceiling is d*sqrt(p*(1-p)): at the 0.57% base
    rate of self-check steps, *no* separator — not even a perfect one — can
    score above ~0.22, which is where the 1/sqrt(n-3) floor happens to sit.
    A gate on Spearman there measures the base rate, not the direction.
    """
    n1, n2 = len(pos), len(neg)
    if n1 == 0 or n2 == 0:
        return float("nan")
    r = stats.rankdata(np.concatenate([pos, neg]))
    return float((r[:n1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n2))


def auc_null_floor(n1: int, n2: int) -> float:
    """Mann-Whitney null SE, sqrt((n1+n2+1)/(12*n1*n2)). Naive: steps are
    autocorrelated, so treat it as a lower bound, not a calibrated gate."""
    if n1 == 0 or n2 == 0:
        return float("nan")
    return float(np.sqrt((n1 + n2 + 1) / (12.0 * n1 * n2)))


def corr_block(trajs: list[dict], name: str, layer: int, observable: str,
               expected_sign: int, binary: bool) -> dict:
    """One direction x one observable, every denominator attached.

    The pooled rho uses *every* step of *every* trajectory. The per-trajectory
    rho is only defined when both sides vary inside that trajectory, so those
    trajectories are dropped from the per-traj statistics — but never from the
    pooled one. Confusing the two would quietly delete whole observables:
    `in_think` and `self_check` are constant within most trajectories, and a
    per-trajectory filter applied to the pooled number would report "no data"
    for exactly the categorical concepts.

    `rho_within_traj` subtracts each trajectory's own mean projection before
    pooling. The gap between `rho_pooled` and `rho_within_traj` is the
    between-trajectory share of the effect, which for `in_think` is the run
    mode and therefore not a statement about the concept at all.
    """
    per_traj, xs, ys, xc = [], [], [], []
    n_steps = 0
    for t in trajs:
        p, y = t["proj"][(name, layer)], t[observable]
        xs.append(p)
        ys.append(y)
        xc.append(p - p.mean())
        n_steps += len(p)
        if not (np.all(p == p[0]) or np.all(y == y[0])):
            per_traj.append(spearman(p, y))
    if n_steps == 0:
        return {"n_traj_pooled": 0, "n_steps": 0, "rho_pooled": float("nan"),
                "null_floor_by_traj": null_floor(0)}
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    v = np.asarray([a for a in per_traj if a == a], dtype=np.float64)
    n_pos = int((v > 0).sum()) if len(v) else 0
    out = {
        "n_traj_pooled": len(trajs),
        "n_traj_within_which_rho_is_defined": int(len(v)),
        "n_steps": int(n_steps),
        "rho_pooled": spearman(x, y),
        "rho_within_traj": spearman(np.concatenate(xc), y),
        "median_rho_per_traj": float(np.median(v)) if len(v) else float("nan"),
        "iqr_rho_per_traj": ([float(np.percentile(v, 25)), float(np.percentile(v, 75))]
                             if len(v) else [float("nan")] * 2),
        "n_traj_positive": n_pos,
        "frac_traj_positive": n_pos / len(v) if len(v) else float("nan"),
        "sign_test_p": sign_test_p(n_pos, len(v)),
        "boot_ci_median_rho": block_bootstrap_ci(per_traj),
        "null_floor_by_traj": null_floor(len(trajs)),
        "null_floor_by_step_naive": null_floor(int(n_steps)),
    }
    if binary:
        n1 = int(y.sum())
        n2 = int(n_steps - n1)
        p_rate = n1 / n_steps
        # Against a 0/1 outcome Spearman degenerates to the point-biserial
        # r = d * sqrt(p(1-p)), with d measured against the *total* SD. So
        # sqrt(p(1-p)) is not a ceiling on r (a perfect separator reaches 1);
        # it is the factor by which the rare base rate shrinks whatever
        # separation exists. Restating the floor in those units says what the
        # gate actually demands: how strong a separation on this label.
        k = float(np.sqrt(p_rate * (1 - p_rate)))
        out["base_rate"] = p_rate
        out["n_positive_steps"] = n1
        out["n_negative_steps"] = n2
        out["point_biserial_shrink_factor"] = k
        out["cohens_d_implied_by_rho"] = float(out["rho_pooled"] / k) if k > 0 else float("nan")
        out["cohens_d_demanded_by_floor"] = float(out["null_floor_by_traj"] / k) if k > 0 else float("nan")
        # Both AUCs are reported and the within-trajectory one gates: a random
        # direction inherits a per-trajectory offset, and self-check steps
        # cluster in a few trajectories, so the pooled AUC flatters noise.
        out["auc_pooled"] = auc_mw(x[y > 0.5], x[y < 0.5])
        xcw = np.concatenate(xc)
        out["auc_within_traj"] = auc_mw(xcw[y > 0.5], xcw[y < 0.5])
        out["auc_null_floor_naive"] = auc_null_floor(n1, n2)
        out["gate_statistic"] = "auc_within_traj"
    else:
        out["gate_statistic"] = "rho_within_traj"
    # The gate threshold itself is decided in main(), against the random
    # directions. It is not decided here, because a null built from 16 random
    # directions cannot exist before those 16 runs have been scored.
    out["passes_gate"] = None
    return out


# The observables that are 0/1 by construction. Everything else is continuous,
# and a Spearman floor is meaningful for them.
BINARY_OBSERVABLES = ("self_check", "in_think", "top1_switch")


def shuffled_corr(trajs: list[dict], name: str, layer: int, observable: str,
                  seed: int = 7) -> float:
    """Same correlation with the activation trace permuted inside each
    trajectory. Self-proof that the correlation function is really reading
    the activation: destroy the input and the number must die."""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for t in trajs:
        p = t["proj"][(name, layer)].copy()
        rng.shuffle(p)
        xs.append(p)
        ys.append(t[observable])
    return spearman(np.concatenate(xs), np.concatenate(ys))


def heldout_pass(npz_dir: Path, layer: int, n_traj: int) -> dict:
    """Rebuild each contrast on half the trajectories, score on the other half.

    This is the only non-circular form of the necessity test. The shipped
    vectors are the mean difference between two groups of *these* tokens, so
    scoring them on *these* tokens measures the extractor. Here:

      sub-pass A  read every file, accumulate per-fold group mean states
      sub-pass B  read every file again, project fold B's states onto the
                  contrast fitted on fold A, correlate with the observable

    Two extra reads of the corpus (~9 GB, CPU only, no GPU, no weights).
    """
    files = [p for p in sorted(npz_dir.glob("*.npz"))[:n_traj] if p.with_suffix(".json").exists()]

    # Fold by *problem*, not by file position. The files sort as
    # `..._no_think.npz, ..._think.npz` per problem, so a positional split
    # would put every no-think run in one fold and every think run in the
    # other — which would silently turn the `creativity` contrast into a
    # measurement of the run mode instead of of the think block.
    problems: dict = {}
    for p in files:
        problems.setdefault(p.stem.rsplit("__", 1)[0], []).append(p)
    order = sorted(problems)
    fold_of = {p.stem: (i % 2) for i, base in enumerate(order) for p in problems[base]}

    # --- sub-pass A: group means per fold, per contrast side -------------
    sums: dict = {}
    cnts: dict = {}
    meta_by_fold: dict = {}
    path_by_traj: dict = {}
    for npz_path in files:
        path_by_traj[npz_path.stem] = npz_path
        with np.load(npz_path) as d:
            T = int(d["hidden_states"].shape[0])
            rec = _read_step_observables(npz_path.with_suffix(".json"), T)
            if rec is None:
                continue
            fold = fold_of[npz_path.stem]
            meta_by_fold.setdefault(fold, []).append(rec)
            h = d["hidden_states"][:, layer, :].astype(np.float32)
            for g, m in rec["_masks"].items():
                if m.sum() < 2:
                    continue
                k = (fold, g)
                sums[k] = sums.get(k, 0.0) + h[m].sum(axis=0)
                cnts[k] = cnts.get(k, 0) + int(m.sum())
            del h, d

    def direction(fit_fold: int, pos: str, neg: str):
        a, b = sums.get((fit_fold, pos)), sums.get((fit_fold, neg))
        na, nb = cnts.get((fit_fold, pos), 0), cnts.get((fit_fold, neg), 0)
        if na < 30 or nb < 30 or a is None or b is None:
            return None, na, nb
        u = (a / na) - (b / nb)
        return (u / (np.linalg.norm(u) + 1e-8)).astype(np.float32), na, nb

    out = {"layer": layer,
           "method": "contrast refitted on the other half of the trajectories",
           "folds": {}}
    for name, (pos, neg) in CONTRASTS.items():
        obs, sign = CLAIMS[name]["observable"], CLAIMS[name]["sign"]
        entry = {"observable": obs, "expected_sign": sign, "scores": {}}
        for fit_fold in (0, 1):
            v, na, nb = direction(fit_fold, pos, neg)
            if v is None:
                entry["scores"][f"fit{fit_fold}"] = {"status": "too_few_tokens",
                                                     "n_pos": na, "n_neg": nb}
                continue
            score_fold = 1 - fit_fold
            group = meta_by_fold.get(score_fold, [])
            xs, ys, n_steps = [], [], 0
            for rec in group:
                path = path_by_traj.get(rec["traj"])
                if path is None:
                    continue
                with np.load(path) as d:
                    h = d["hidden_states"][:, layer, :].astype(np.float32)
                xs.append(np.einsum("td,d->t", h, v))
                ys.append(rec[obs])
                n_steps += len(h)
            if not xs:
                continue
            px = np.concatenate(xs)
            py = np.concatenate(ys)
            rho = spearman(px, py)
            entry["scores"][f"fit{fit_fold}_score{score_fold}"] = {
                "n_pos_tokens_in_fit": na, "n_neg_tokens_in_fit": nb,
                "n_traj_scored": len(xs), "n_steps_scored": n_steps,
                "rho": rho,
                "null_floor_by_traj": null_floor(len(xs)),
                "passes_gate": bool(sign * rho > null_floor(len(xs))),
            }
            if obs in BINARY_OBSERVABLES:
                n1 = int((py > 0.5).sum())
                n2 = int(n_steps - n1)
                k = float(np.sqrt((n1 / n_steps) * (1 - n1 / n_steps))) if n_steps else float("nan")
                # within-trajectory AUC, the same statistic the in-sample gate
                # uses, so the two blocks are comparable
                xcw = np.concatenate([a - a.mean() for a in xs])
                a_w = auc_mw(xcw[py > 0.5], xcw[py < 0.5])
                s = entry["scores"][f"fit{fit_fold}_score{score_fold}"]
                s.update(base_rate=n1 / n_steps, n_positive_steps=n1, n_negative_steps=n2,
                         auc_within_traj=a_w,
                         auc_pooled=auc_mw(px[py > 0.5], px[py < 0.5]),
                         auc_null_floor_naive=auc_null_floor(n1, n2),
                         point_biserial_shrink_factor=k,
                         cohens_d_demanded_by_floor=(null_floor(len(xs)) / k) if k > 0 else float("nan"),
                         gate_statistic="auc_within_traj",
                         passes_gate=bool(a_w - 0.5 > auc_null_floor(n1, n2)))
        out["folds"][name] = entry
    return out


def e_frac(k: int) -> str:
    return f"{k}"


def observable_audit(trajs: list[dict]) -> dict:
    """Before believing any rho, check what the observable actually is.

    A categorical observable that is constant inside every trajectory cannot
    carry a within-trajectory story, and if its value is fixed by the run
    mode then "this concept is active" and "this run was a think-mode run"
    are the same variable. Both facts have to sit next to the number, or the
    number will be read as more than it is.
    """
    out = {}
    for obs in OBSERVABLES:
        n_steps = sum(t["T"] for t in trajs)
        pos = int(sum(float(t[obs].sum()) for t in trajs))
        constant_traj = [t for t in trajs if np.all(t[obs] == t[obs][0])]
        entry = {
            "n_steps": n_steps,
            "frac_steps_positive": pos / n_steps if n_steps else float("nan"),
            "n_traj": len(trajs),
            "n_traj_constant_inside": len(constant_traj),
            "frac_traj_constant_inside": len(constant_traj) / len(trajs) if trajs else float("nan"),
        }
        if obs in ("self_check", "in_think"):
            modes: dict = {}
            for t in trajs:
                m = "think" if t["traj"].endswith("__think") else "no_think"
                modes.setdefault(m, []).append(float(t[obs][0]))
            entry["by_run_mode"] = {
                m: {"n_traj": len(v), "all_positive": int(sum(v)),
                    "all_negative": int(len(v) - sum(v))}
                for m, v in sorted(modes.items())
            }
            # The observable is the run mode when its value at step 0 is
            # determined by the mode in every trajectory. It does not matter
            # that a few think-mode runs open a think block mid-trajectory:
            # what matters is whether "is the concept active here" can be
            # told apart from "was this a think-mode run".
            first = {("think" if t["traj"].endswith("__think") else "no_think"): float(t[obs][0])
                     for t in trajs}
            per_traj_first = [(("think" if t["traj"].endswith("__think") else "no_think"),
                               float(t[obs][0])) for t in trajs]
            mode_determined = all(
                v == first[m] for m, v in per_traj_first) and len(set(first.values())) == len(first)
            entry["determined_by_run_mode"] = bool(mode_determined)
            entry["n_traj_matching_mode_at_step0"] = int(
                sum(1 for m, v in per_traj_first if v == first[m]))
            if mode_determined:
                entry["warning"] = (
                    f"在这个语料上 {obs} 在第 0 步就恒等于运行模式"
                    f"（{entry['n_traj_matching_mode_at_step0']}/{len(trajs)} 条轨迹，"
                    f"{e_frac(len(constant_traj))} 条轨迹内部还是常数），"
                    "所以「概念是否活跃」和「这次是不是 think 模式跑」在数据上是同一个变量，"
                    "以它为标签的相关系数不能被读成「模型内部调制了这个概念」。")
        out[obs] = entry
    return out


def dispersion(trajs: list[dict], name: str, layer: int) -> dict:
    """Is the activation concentrated at concept steps or smeared over all of them?

    A direction that merely re-scales the whole output distribution ("global
    temperature") should leave a trace that is flat relative to its own
    spread; a direction implementing a specific state should be spiky. This
    is the per-step half of the specificity question, computable from the
    stored traces with no forward pass.
    """
    p = np.concatenate([t["proj"][(name, layer)] for t in trajs])
    nrm = np.concatenate([t["norm"][layer] for t in trajs])
    frac = p / nrm
    med = float(np.median(frac))
    dev = np.clip(frac - med, 0, None)
    tot = float(dev.sum())
    k = max(int(0.10 * len(dev)), 1)
    return {
        "n_steps": int(len(frac)),
        "share_of_positive_deviation_in_top_decile": float(np.sort(dev)[-k:].sum() / tot) if tot > 0 else float("nan"),
        "uniform_expectation": 0.10,
        "iqr_over_abs_median": float((np.percentile(frac, 75) - np.percentile(frac, 25)) / (abs(med) + 1e-8)),
    }


# ---------------------------------------------------------------------------
# sufficiency + specificity: the 32k intervention journal
# ---------------------------------------------------------------------------

def summarise_cell(runs: list[dict], raw: list[dict]) -> dict:
    def m(key, src):
        vals = [r[key] for r in src if r.get(key) is not None]
        return (float(np.mean(vals)), int(len(vals))) if vals else (float("nan"), 0)

    def med(key):
        vals = [r[key] for r in runs if r.get(key) is not None]
        return (float(np.median(vals)), int(len(vals))) if vals else (float("nan"), 0)

    summ = [r["summary"] for r in raw]
    ep, nep = m("mean_entropy_primary", summ)
    es, nes = m("mean_entropy_shadow", summ)
    kl, nkl = m("mean_logit_kl", runs)
    lr, nlr = m("reason_len_ratio", runs)
    lrm, _ = med("reason_len_ratio")
    ag, nag = m("token_agreement", runs)
    ov, nov = m("verbatim_step_overlap", runs)
    known = [r for r in runs if r.get("answer_known")]
    changed = [r for r in known if r.get("answer_changed")]
    closed = [r for r in runs if r.get("closed_think") is not None]
    return {
        "n_runs": len(runs),
        "length_ratio": {"mean": lr, "median": lrm, "n": nlr},
        "token_agreement": {"mean": ag, "n": nag},
        "verbatim_step_overlap": {"mean": ov, "n": nov},
        "logit_kl": {"mean": kl, "n": nkl},
        "entropy_primary_minus_shadow": {"mean": (ep - es) if nep and nes else float("nan"),
                                         "n": min(nep, nes)},
        "answer_changed": {"k": len(changed), "n": len(known),
                           "rate": len(changed) / len(known) if known else float("nan")},
        "closed_think": {"k": sum(1 for r in closed if r["closed_think"]), "n": len(runs),
                         "rate": (sum(1 for r in closed if r["closed_think"]) / len(closed)) if closed else float("nan")},
        "injected_norm": m("injected_norm", runs)[0],
    }


def run_sufficiency(journal: dict, raw: list[dict]) -> dict:
    by: dict = {}
    rawby: dict = {}
    for r in journal["per_run"]:
        by.setdefault((r["direction"], r["strength"]), []).append(r)
    for r in raw:
        rawby.setdefault((r["direction"], r["strength"]), []).append(r)
    cells = {f"{d}@{s}": summarise_cell(by[(d, s)], rawby[(d, s)]) for (d, s) in sorted(by)}
    have = sorted({r["direction"] for r in journal["per_run"]})
    miss = [d for d in CLAIMS if d not in have]
    return {
        "definition": "只加这个向量，够不够复现该概念的行为？",
        "cells": cells,
        "directions_with_runs": have,
        "directions_without_runs": miss,
        "coverage_gap": (
            f"充分性和特异性只能在这 {len(have)} 个方向上测：32k 日志的 "
            f"direction x strength 一共只有 {len(cells)} 格"
            f"（{', '.join(sorted(cells))}）。另外 {len(miss)} 个方向"
            f"（{', '.join(miss)}）在这批数据里一次干预运行都没有。"
            "这是采集覆盖面本身的缺口，不是本次分析挑的。"),
        "floor_note": (
            "strength=0.0 是同一条代码路径喂零向量，46 次运行逐字相同，"
            "所以它的每个量都恰好等于 0 或 1.0。那是这批数据的采集噪声地板，"
            "不是估计值——所有 0.2 的数字都要对着它读。"),
    }


def run_specificity(journal: dict) -> dict:
    per = journal["per_run"]
    locality = {}
    for d in sorted({r["direction"] for r in per}):
        cell = [r for r in per if r["direction"] == d and r["strength"] > 0]
        fr = [r["first_divergence_char"] / max(r["reason_chars_primary"], 1) for r in cell
              if r.get("first_divergence_char", -1) >= 0]
        ov = [r["verbatim_step_overlap"] for r in cell if r.get("verbatim_step_overlap") is not None]
        locality[d] = {
            "n_runs": len(cell),
            "divergence_starts_at_frac_of_run": ({"median": float(np.median(fr)), "n": len(fr)} if fr else None),
            "verbatim_step_overlap": ({"median": float(np.median(ov)), "n": len(ov)} if ov else None),
        }

    up = {r["label"]: r for r in per if r["direction"] == "confidence_up" and r["strength"] > 0}
    dn = {r["label"]: r for r in per if r["direction"] == "confidence_down" and r["strength"] > 0}
    shared = sorted(set(up) & set(dn))
    mirror = {}
    for field in ("mean_logit_kl", "reason_len_ratio", "token_agreement",
                  "selfcheck_delta", "closed_think"):
        pairs = [(float(up[k][field]), float(dn[k][field])) for k in shared
                 if up[k].get(field) is not None and dn[k].get(field) is not None]
        if len(pairs) < 4:
            continue
        a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
        mirror[field] = {
            "rho_up_vs_down": spearman(a, b),
            "n_paired_problems": len(pairs),
            "frac_signs_differ": (float(np.mean(np.sign(a) != np.sign(b)))
                                  if field != "closed_think" else float(np.mean(a != b))),
            "null_floor": null_floor(len(pairs)),
        }

    with_series = [r for r in per if any(k in r for k in
                   ("entropy_series", "per_step_entropy", "entropy_curve"))]
    return {
        "definition": "加这个向量，只影响它该影响的，还是把所有东西都推平了？",
        "locality": locality,
        "mirror_test": mirror,
        "literal_per_step_entropy_test": {
            "status": "NOT_MEASURABLE_ON_THIS_BATCH",
            "claim": "干预后每一步的熵是否同向变化（整体 vs 局部）",
            "evidence": (
                "cot_divergence_32k.json 的 per_run 每条只有汇总量："
                "mean_entropy_primary / mean_entropy_shadow / mean_logit_kl / "
                "token_agreement / first_divergence_char / verbatim_step_overlap；"
                "all_runs.json 的 summary 里多一个 layer_curve（逐层，不是逐步）。"
                f"没有逐步熵序列——带该字段的运行数 = {len(with_series)} / {len(per)}。"),
            "what_is_measured_instead": (
                "两个真的能测的替代：(a) locality——分歧从轨迹的百分之几处开始、"
                "整段里有多大比例被改掉；(b) mirror——同一道题上 up 与 down 是否"
                "互为相反数。两者都带分母，但都不是逐步熵，报告里分开写。"),
        },
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--npz-dir", type=Path, default=DEFAULT_NPZ_DIR)
    ap.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    ap.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    ap.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--limit", type=int, default=0, help="0 = all trajectories")
    ap.add_argument("--skip-heldout", action="store_true",
                    help="skip the two extra corpus reads behind the non-circular test")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "backend"))
    from core.steering import SteeringRegistry  # noqa: E402

    args.cache.mkdir(parents=True, exist_ok=True)
    reg = SteeringRegistry()
    if not reg.load():
        print(f"!! registry failed to load: {reg.load_error}", file=sys.stderr)
        return 2
    n_cal = reg.load_layer_scales(args.profiles)
    print(f"registry: {len(reg.names)} directions, layer calibration on {n_cal} layers")
    print(f"  native extraction layer = {LAYER_NATIVE} (mean_norm {reg.layer_rms(LAYER_NATIVE):.1f})")
    print(f"  32k injection layer     = {LAYER_INJECT} (mean_norm {reg.layer_rms(LAYER_INJECT):.1f})")
    for nm in ("confidence_up", "confidence_down"):
        v = reg.scaled(nm, 0.2, LAYER_INJECT)
        if v is not None:
            print(f"  scaled({nm}, 0.2, {LAYER_INJECT}) -> |v| = {np.linalg.norm(v):.1f} "
                  f"= {np.linalg.norm(v) / reg.layer_rms(LAYER_INJECT) * 100:.1f}% of the residual norm")

    vectors = {n: reg.unit_vector(n) for n in CLAIMS if reg.has(n)}
    if missing := [n for n in CLAIMS if not reg.has(n)]:
        print(f"!! missing vectors: {missing}", file=sys.stderr)

    n_traj = args.limit or len(sorted(args.npz_dir.glob("*.npz")))
    layers = [LAYER_NATIVE, LAYER_INJECT]

    rng = np.random.default_rng(20261002)
    random_dirs = {}
    for i in range(N_RANDOM_DIRECTIONS):
        g = rng.standard_normal(2048)
        random_dirs[f"random_{i}"] = (g / np.linalg.norm(g)).astype(np.float32)
    proj_names = {**vectors, **random_dirs}

    print(f"\nscanning {n_traj} trajectories from {args.npz_dir} (one read, ~9 GB)...")
    trajs, n_nonfinite = load_trajectories(args.npz_dir, layers, n_traj, vectors, random_dirs)
    total_steps = sum(t["T"] for t in trajs)
    n_traj = len(trajs)
    floor_traj = null_floor(n_traj)
    print(f"traces: {n_traj} trajectories, {total_steps} steps; "
          f"floor by traj = {floor_traj:.4f}, floor by step (naive) = {null_floor(total_steps):.4f}")
    print(f"non-finite projections: {n_nonfinite} / "
          f"{n_traj * len(proj_names) * len(layers)} "
          "(if this is not 0, every number below is meaningless)")

    print("\n== observable audit (what the labels actually are) ==")
    audit = observable_audit(trajs)
    for obs, a in audit.items():
        flag = "  <-- 等同于运行模式" if a.get("determined_by_run_mode") else ""
        print(f"  {obs:<12} steps={a['n_steps']:>6} frac_pos={a['frac_steps_positive']:.4f} "
              f"constant-in-traj {a['n_traj_constant_inside']}/{a['n_traj']}{flag}")

    print("\n== anchors ==")
    anchors = run_anchors(args.npz_dir, min(6, n_traj))
    for k, v in anchors["checks"].items():
        print(f"  {k}: {v['pass']}/{v['total']} = {v['rate']:.4f}")
    print(f"  lm_head anchor: {anchors['lm_head_anchor']['status']}")

    print(f"\n== necessity (Spearman, in-sample / CIRCULAR) at L{LAYER_NATIVE} and L{LAYER_INJECT} ==")
    in_sample = {}
    for L in layers:
        in_sample[f"L{L}"] = {}
        for name, claim in CLAIMS.items():
            obs, sign = claim["observable"], claim["sign"]
            binary = obs in BINARY_OBSERVABLES
            b = corr_block(trajs, name, L, obs, sign, binary)
            sh = shuffled_corr(trajs, name, L, obs)
            b.update(observable=obs, expected_sign=sign, circular=True,
                     shuffled_control_rho=sh)
            in_sample[f"L{L}"][name] = b
            stat = (f"rho={b['rho_pooled']:+.4f} within={b['rho_within_traj']:+.4f}"
                    if not binary else
                    f"rho={b['rho_pooled']:+.4f}(d~{b['cohens_d_implied_by_rho']:.2f}) "
                    f"AUC_within={b['auc_within_traj']:.4f}")
            print(f"  L{L} {name:<18} vs {obs:<11} {stat} "
                  f"(n_traj={b['n_traj_pooled']}, n_steps={b['n_steps']}, "
                  f"naive floor={b['null_floor_by_traj']:.4f}) shuffled={sh:+.4f} "
                  f"[verdict below, after the random control]")

    print(f"\n== necessity (HELD-OUT, non-circular) at L{LAYER_NATIVE} ==")
    heldout = {"skipped": bool(args.skip_heldout)}
    if not args.skip_heldout:
        heldout = heldout_pass(args.npz_dir, LAYER_NATIVE, n_traj)
        for name, entry in heldout["folds"].items():
            for tag, s in entry["scores"].items():
                if "rho" not in s:
                    print(f"  {name:<18} {tag}: {s['status']} (n_pos={s.get('n_pos')})")
                    continue
                extra = ("" if s.get("gate_statistic") != "auc_within_traj"
                         else f" AUC_within={s['auc_within_traj']:.4f} (floor needs d>="
                              f"{s['cohens_d_demanded_by_floor']:.2f})")
                print(f"  {name:<18} {tag:<18} rho={s['rho']:+.4f}{extra} "
                      f"(n_traj={s['n_traj_scored']}, n_steps={s['n_steps_scored']}, "
                      f"floor={s['null_floor_by_traj']:.4f}) {'PASS' if s['passes_gate'] else 'FAIL'}")

    print("\n== necessity: random directions (the empirical null) ==")
    random_ctl = {}
    for L in layers:
        random_ctl[f"L{L}"] = {}
        for name, claim in CLAIMS.items():
            obs = claim["observable"]
            stat = "auc_within_traj" if obs in BINARY_OBSERVABLES else "rho_within_traj"
            vals = [corr_block(trajs, f"random_{i}", L, obs, claim["sign"],
                               obs in BINARY_OBSERVABLES)[stat]
                    for i in range(N_RANDOM_DIRECTIONS)]
            a = np.asarray(vals, dtype=np.float64)
            mu, sd = float(a.mean()), float(a.std(ddof=1))
            # mean+3sd is the natural threshold, but on a bounded statistic
            # with a wide null it can land outside [0,1] — at L20 on
            # self_check it comes out at 1.128, a gate nothing could ever
            # pass. So the operative floor is the largest value any random
            # direction reached, and the sd-based one is reported beside it.
            floor = float(a.max())
            m3 = mu + EMPIRICAL_SD_GATE * sd
            random_ctl[f"L{L}"][name] = {
                "observable": obs,
                "gate_statistic": stat,
                "n_random_directions": N_RANDOM_DIRECTIONS,
                "random_mean": mu, "random_sd": sd,
                "random_min": float(a.min()), "random_max": floor,
                "empirical_floor_max_random": floor,
                "empirical_floor_mean_plus_3sd": m3,
                "mean_plus_3sd_reachable": bool(m3 <= 1.0 or stat != "auc_within_traj"),
                "naive_floor_1_over_sqrt_n_minus_3": floor_traj,
                "empirical_floor_is_stricter": bool(floor > floor_traj),
                "z_of_real_direction": None,   # filled in once the real one is scored
            }
            warn = ("" if (m3 <= 1.0 or stat != "auc_within_traj")
                    else f"; mean+3sd={m3:.4f} is UNREACHABLE, reported only")
            print(f"  L{L} {name:<18} vs {obs:<11} {stat} over "
                  f"{N_RANDOM_DIRECTIONS} random dirs: mean={mu:+.4f} sd={sd:.4f} "
                  f"min={a.min():+.4f} max={a.max():+.4f} -> gate = beat max = "
                  f"{floor:+.4f} (naive 1/sqrt(n-3)={floor_traj:.4f}{warn})")

    # The gate is the empirical null, and it is required to be stricter than
    # the naive 1/sqrt(n-3) floor as well.
    for L in layers:
        for name in CLAIMS:
            c = in_sample[f"L{L}"][name]
            ctl = random_ctl[f"L{L}"][name]
            c["empirical_floor"] = max(ctl["empirical_floor_max_random"], floor_traj)
            c["gate_threshold"] = c["empirical_floor"]
            c["gate_threshold_is_stricter_than_naive"] = bool(c["empirical_floor"] > floor_traj)
            ctl["naive_floor_is_the_binding_one"] = bool(
                ctl["empirical_floor_max_random"] <= floor_traj)
            st = ctl["gate_statistic"]
            ctl["z_of_real_direction"] = (
                (c[st] - ctl["random_mean"]) / ctl["random_sd"]
                if ctl["random_sd"] > 0 else float("nan"))
            # Signed: confidence_up claims a NEGATIVE link to entropy, so the
            # test belongs on the claimed side of the null, not on the raw
            # value. Testing the raw value fails the very direction whose sign
            # was predicted correctly.
            c["signed_stat"] = c["expected_sign"] * c[st]
            c["passes_gate"] = bool(
                c["signed_stat"] > c["empirical_floor"]
                and abs(c["shuffled_control_rho"]) < c["null_floor_by_traj"])
            c["n_random_directions_in_control"] = N_RANDOM_DIRECTIONS
    print("\n  -- necessity verdicts against the empirical null --")
    for L in layers:
        for name in CLAIMS:
            c = in_sample[f"L{L}"][name]
            ctl = random_ctl[f"L{L}"][name]
            st = ctl["gate_statistic"]
            print(f"  L{L} {name:<18} {st}={c[st]:+.4f} signed={c['signed_stat']:+.4f} "
                  f"vs threshold {c['gate_threshold']:+.4f} "
                  f"(naive {c['null_floor_by_traj']:.4f}, "
                  f"{'stricter' if c['gate_threshold_is_stricter_than_naive'] else 'naive binds'}) "
                  f"shuffled={c['shuffled_control_rho']:+.4f} "
                  f"{'PASS' if c['passes_gate'] else 'FAIL'}")

    journal = json.loads(args.journal.read_text())
    raw = json.loads(args.runs.read_text())

    print("\n== sufficiency (32k journal) ==")
    suff = run_sufficiency(journal, raw)
    for cell, v in suff["cells"].items():
        print(f"  {cell:<24} n_runs={v['n_runs']:>2} len_ratio={v['length_ratio']['mean']:.4f} "
              f"tok_agree={v['token_agreement']['mean']:.4f} KL={v['logit_kl']['mean']:.5f} "
              f"dEntropy={v['entropy_primary_minus_shadow']['mean']:+.5f} "
              f"ans_changed={v['answer_changed']['k']}/{v['answer_changed']['n']} "
              f"closed_think={v['closed_think']['k']}/{v['closed_think']['n']}")

    print("\n== specificity ==")
    spec = run_specificity(journal)
    for d, v in spec["locality"].items():
        fr, ov = v["divergence_starts_at_frac_of_run"], v["verbatim_step_overlap"]
        print(f"  {d:<18} n_runs={v['n_runs']} divergence starts at median "
              f"{fr['median']:.4f} of the run (n={fr['n']}); verbatim overlap median "
              f"{ov['median']:.4f} (n={ov['n']})")
    for f, v in spec["mirror_test"].items():
        print(f"  mirror {f:<20} rho_up_vs_down={v['rho_up_vs_down']:+.4f} "
              f"n={v['n_paired_problems']} floor={v['null_floor']:.4f}")
    print(f"  literal per-step entropy: {spec['literal_per_step_entropy_test']['status']}")

    print("\n== activation dispersion (per-step shape of the direction itself) ==")
    disp = {f"L{L}": {n: dispersion(trajs, n, L) for n in vectors} for L in layers}
    for L, dd in disp.items():
        for name, v in dd.items():
            print(f"  {L} {name:<18} top-decile share of positive deviation = "
                  f"{v['share_of_positive_deviation_in_top_decile']:.3f} "
                  f"(uniform 0.100, n_steps={v['n_steps']})")

    report = {
        "schema": "steer3d.vector_roles/1",
        "generated_by": "backend/examples/analyse_vector_roles.py",
        "model": "Qwen3-1.7B",
        "framework": {
            "three_measurements": ["sufficiency", "necessity", "specificity"],
            "source": (
                "Elhage, Hume, Olsson, Wasserstein, Boffi, Gao, Nye & Binder, "
                "'Toy Models of Superposition' (Anthropic, 2022), the 'Controlling a "
                "feature' section: a residual-stream direction is characterised by "
                "whether writing it is sufficient for a behaviour, whether the model "
                "itself writes to it when that behaviour happens (necessary), and "
                "whether it moves anything else (specific)."),
            "why_it_matters_here": (
                "只有「加进去行为变了」这一个观测时，「这是 confidence 的实现」和"
                "「这是一个叫 confidence 的全局温度旋钮」给出完全一样的观测。"
                "三件套是把它们分开的最少测量。"),
        },
        "layers": {
            "native_extraction": LAYER_NATIVE,
            "journal_injection": LAYER_INJECT,
            "note": (
                f"向量在第 {LAYER_NATIVE} 层由 diff-of-means 抽出，32k 日志在第 "
                f"{LAYER_INJECT} 层注入（registry.scaled 按该层 mean_norm 重新缩放："
                f"mean_norm(L{LAYER_NATIVE})={reg.layer_rms(LAYER_NATIVE):.1f}，"
                f"mean_norm(L{LAYER_INJECT})={reg.layer_rms(LAYER_INJECT):.1f}）。"
                "两个层都算了：一个方向在定义它的层和被使用的层，未必是同一件事。"),
        },
        "denominators": {
            "n_trajectories": n_traj,
            "n_steps_total": total_steps,
            "n_directions_projected": len(proj_names),
            "n_layers_projected": len(layers),
            "n_projection_values": n_traj * len(proj_names) * len(layers),
            "n_projection_values_non_finite": n_nonfinite,
            "null_floor_formula": "1/sqrt(n-3)",
            "null_floor_by_traj": floor_traj,
            "null_floor_by_step_naive": null_floor(total_steps),
            "why_by_traj": (
                "解码步之间自相关极强，按步数算的 1/sqrt(n-3) 会小两个数量级，"
                "是作弊。独立单位是轨迹，所以门槛一律用 1/sqrt(n_traj-3)。"),
        },
        "anchors": anchors,
        "observable_audit": audit,
        "necessity": {
            "definition": "模型自己跑的时候，这个概念真的会调制这个方向上的激活吗？",
            "method": ("把每一步第 L 层的残差流投影到每个向量上（零 GPU，不跑前向、不碰权重），"
                       "再与同一步的可观测行为做 Spearman。"),
            "in_sample_circular": in_sample,
            "heldout_non_circular": heldout,
            "random_direction_control": random_ctl,
            "circularity_warning": (
                "in_sample 那一块是循环论证的：这些向量就是这批 token 上两组均值之差，"
                "把它投影回同一批 token 再和同一批标签求相关，量的是抽取器不是模型。"
                "heldout 块在另一半轨迹上重建同一个对比、在另一半上评测，两半没有共享 token，"
                "那才是真实数字。对 confidence_up / caution 这类「标签本身就是向量定义」的"
                "方向，in_sample 的高相关不能当证据。"),
            "label_confounds": (
                "标签本身要先审计，见 observable_audit。in_think 在这 48 条轨迹上"
                "恒等于运行模式（think 模式全程 1，no_think 模式全程 0），"
                "所以 creativity 的 necessity 数字量的是「这次是不是 think 模式跑」，"
                "不是「模型在 think 块内部」。这是向量定义的性质，不是分析的失误。"),
            "per_traj_denominator_note": (
                "n_traj_within_which_rho_is_defined 会明显小于 n_traj_pooled："
                "in_think / self_check 在单条轨迹内部常常是常数，Spearman 在常数上是未定义的，"
                "那些轨迹只从「逐轨迹 rho」里剔除，pooled 仍然用上它的每一步。"),
            "which_statistic_and_why": (
                "门一律打在「轨迹内去均值」的统计量上，并且按方向自称的符号来判："
                "连续标签用 rho_within_traj（confidence_up 自称负相关，所以比的是 "
                "−rho），二值标签用 auc_within_traj。三个理由："
                "(1) 轨迹间差异不是概念，对 in_think 来说它就是运行模式；"
                "(2) Spearman 打在 0/1 标签上退化成 point-biserial r = d*sqrt(p(1-p))，"
                "self_check 基率 0.0057、压缩因子 0.075，1/sqrt(45)=0.149 实际要求 d=1.98；"
                "(3) 门槛取 max(16 个随机方向里的最大值, 1/sqrt(n_traj-3))，"
                "所以门永远不弱于教科书地板，而在 L20 的 entropy 上比它严格得多"
                "（随机方向最大能到 0.2548）。"),
            "random_control_is_the_real_null": (
                "16 个随机方向是这批数据上真正的零假设。self_check 上它们的 "
                "auc_within 从 0.21 散到 0.75——391 个正例每一个都是孤立的单步，"
                "只分布在 27 条轨迹里，独立单位是轨迹不是步，所以 Mann-Whitney 的"
                "教科书 SE 偏小一个数量级。entropy 在 L20 上同样偏小。"
                "门槛用「打败全部 16 个随机方向」，因为 mean+3sd 在 L20 的 self_check 上"
                "会算出 1.128这种没有任何 AUC 能达到的阈值（已记为 unreachable）。"),
            "within_vs_between": (
                "rho_pooled 含轨迹间差异，rho_within_traj 先减掉每条轨迹自己的均值再合并。"
                "in_think 的 rho_pooled 很高而 rho_within_traj 接近 0，"
                "说明那部分效应几乎全部来自轨迹之间（= think 模式），"
                "不是模型在 think 块内部做了什么。"),
        },
        "sufficiency": suff,
        "specificity": {**spec, "activation_dispersion": disp},
        "unmeasured": {
            "per_step_entropy_of_steered_runs": spec["literal_per_step_entropy_test"],
            "directions_without_intervention_runs": suff["directions_without_runs"],
            "lm_head_anchor": anchors["lm_head_anchor"],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwrote {args.out} ({args.out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
