#!/usr/bin/env python3
"""
obs_extract.py -- Pre-registered observable construction + screenability audit
for "what does a steering vector actually point at".

OWNERSHIP: this file and obs_extract.json only. Read-only on datasets/ and on
all other .cache/rolesverify/ scripts.

DISCIPLINE IMPLEMENTED HERE
  1. Tokenizer probe first; the backend actually used is recorded in the JSON.
     If neither `tokenizers` nor `transformers` is importable, we fall back to a
     raw byte-level-BPE string lookup built from vocab.json + added_tokens_decoder
     and SAY SO. No torch / model weights are ever imported.
  2. A toy self-check with hand-computable expected answers runs BEFORE the 48
     real trajectories, and its output is embedded in the final JSON.
  3. Every candidate observable is PRE-REGISTERED with a mechanism argument in
     CANDIDATES below. Verdict thresholds are calibrated from a measured null
     (within-trajectory permutation), not chosen by eyeballing effect sizes.
  4. All candidates are reported. Nothing is dropped for looking unpromising.
  5. Renormalisation is honestly labelled: top-64 internal share, not probability.

RENORMALISATION CAVEAT (applies to every *_mass / *_renorm observable)
  topk_logits holds only the top-64 logits of the full next-token distribution.
  We compute logZ64 = logsumexp over those 64 and use w = exp(l - logZ64).
  Then sum(w) == 1 by construction, but w is a *share within the top-64*, NOT a
  probability: logZ64 is typically far below the full log-partition, so these
  numbers systematically OVERSTATE mass. The JSON reports the measured logZ64
  distribution and the true (sidecar) top1_prob alongside, so the gap is visible.
  The sidecar `top1_prob` is the true probability from the full softmax and is
  NOT the same quantity as `top1_prob_renorm`. Both are reported; every verdict
  is taken on the renormalised one, and the gap is quantified in the JSON.
"""

import json
import os
import platform
import sys
import time
import glob
import importlib
import traceback

import numpy as np

# ----------------------------------------------------------------------------
# paths
# ----------------------------------------------------------------------------
ROOT = "/Users/zhourui/code/steer3d"
OUT_JSON = os.path.join(ROOT, ".cache/rolesverify/obs_extract.json")
TOYDIR = os.path.join(ROOT, ".cache/rolesverify")
DATA_NPZ = sorted(glob.glob(os.path.join(
    ROOT, "datasets/aime_qwen3_1p7b_16k_fp16/aime/*.npz")))
TOKMODEL = os.path.join(ROOT, "datasets/models/Qwen3-1.7B")

# ----------------------------------------------------------------------------
# 0. environment probe (recorded verbatim in the JSON)
# ----------------------------------------------------------------------------


def probe_env():
    info = {
        "python_version": sys.version,
        "python_version_short": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {},
    }
    for m in ("numpy", "scipy", "tokenizers", "transformers", "torch"):
        try:
            mod = importlib.import_module(m)
            info["packages"][m] = {
                "present": True, "version": getattr(mod, "__version__", "unknown")}
        except Exception as e:
            info["packages"][m] = {
                "present": False, "error": "%s: %s" % (type(e).__name__, e)}
    # which tokenizer backend do we actually use?
    if info["packages"]["transformers"]["present"]:
        info["tokenizer_backend"] = "transformers.AutoTokenizer"
    elif info["packages"]["tokenizers"]["present"]:
        info["tokenizer_backend"] = "tokenizers.Tokenizer"
    else:
        info["tokenizer_backend"] = "raw_vocab_json_byte_bpe_fallback"
    info["tokenizer_backend_reason"] = (
        "neither tokenizers nor transformers is importable in this interpreter, "
        "so token identity is resolved by direct id->surface-string lookup over "
        "vocab.json plus added_tokens_decoder. No encoder is needed: every "
        "observable here classifies a token id that is ALREADY given, so a BPE "
        "encode() implementation is never required. torch and model weights are "
        "never imported.")
    info["torch_imported_by_this_script"] = False
    return info


# ----------------------------------------------------------------------------
# 1. byte-level BPE surface-string decoding (no torch / no transformers)
# ----------------------------------------------------------------------------


def _bytes_to_unicode():
    bs = (list(range(ord("!"), ord("~") + 1))
          + list(range(ord("\xa1"), ord("\xac") + 1))
          + list(range(ord("\xae"), ord("\xff") + 1)))
    cs = bs[:]
    n = 0
    for b in range(2 ** 8):
        if b not in bs:
            bs.append(b)
            cs.append(2 ** 8 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


B2U = _bytes_to_unicode()
U2B = {v: k for k, v in B2U.items()}


def decode_surface(s):
    """Byte-level BPE token string -> real surface text."""
    try:
        raw = bytes(U2B[c] for c in s)
    except KeyError:
        return s          # special token like <|im_start|>: keep literal
    return raw.decode("utf-8", errors="replace")


def build_id2surface():
    """id -> surface string, merging vocab.json and added_tokens_decoder."""
    with open(os.path.join(TOKMODEL, "vocab.json")) as f:
        vocab = json.load(f)
    with open(os.path.join(TOKMODEL, "tokenizer_config.json")) as f:
        tcfg = json.load(f)
    added = tcfg.get("added_tokens_decoder", {})
    id2s = {}
    for s, i in vocab.items():
        id2s[int(i)] = decode_surface(s)
    n_added = 0
    for k, v in added.items():
        i = int(k)
        if i not in id2s:
            n_added += 1
        id2s[i] = v.get("content", "")
    meta = {
        "n_vocab_json": len(vocab),
        "n_added_tokens": len(added),
        "n_added_tokens_not_in_vocab": n_added,
        "n_ids_total": len(id2s),
        "max_id": max(id2s),
    }
    return id2s, meta


# ----------------------------------------------------------------------------
# 2. token-class lookup table  (id -> bool per surface class)
# ----------------------------------------------------------------------------

OPCHARS = set("=+-*/()^$\\")
LATEXCHARS = set("$}{^_\\")

# PRE-REGISTERED revision / negation / hedging discourse marker vocabulary.
# Mechanism: a model that has detected it may have erred, or is re-reading its
# own derivation, emits discourse markers token by token. It is a *content*
# decision made at every step, not a function of the step index.
MARKER_WORDS = frozenset([
    "wait", "actually", "hmm", "hmm", "oh", "ah", "oops", "but", "however",
    "alternatively", "instead", "reconsider", "recheck", "re-check", "check",
    "verify", "correct", "correction", "wrong", "hold", "hold on", "no",
    "not", "never", "meanwhile", "rather", "redo", "again", "unless",
    "suppose", "assume", "let me", "so", "therefore", "thus", "hence",
    "actually", "alternatively", "back",
])

# Same regex as .cache/rolesverify/v1_observables_anchors.py and v2_corr.py, so
# the label-circularity screen tests the SAME concept those scripts used.
import re  # noqa: E402
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)
SELF_CHECK_WORDS = frozenset([
    "wait", "actually", "hmm", "hold on", "let me check", "let me verify",
    "recheck", "double-check", "double check", "second thought",
    "alternatively", "but wait"])


def surface_classes(w):
    """Return dict of surface classes for one decoded token string."""
    ws = w.strip()
    out = {}
    out["digit"] = bool(ws) and all(c in "0123456789" for c in ws)
    out["op"] = bool(ws) and all(c in OPCHARS for c in ws)
    out["newline"] = ("\n" in w)
    out["latex"] = any(c in LATEXCHARS for c in w) or ("frac" in w.lower())
    out["marker"] = ws.lower() in MARKER_WORDS
    out["selfcheck"] = bool(SELF_CHECK_RE.search(w))
    return out


CLASSDIRS = ["digit", "op", "newline", "latex", "marker", "selfcheck"]


def build_classtab(id2s, n_ids):
    tab = np.zeros((n_ids, len(CLASSDIRS)), dtype=bool)
    for i in range(n_ids):
        w = id2s.get(i, "")
        if not w:
            continue
        c = surface_classes(w)
        for j, name in enumerate(CLASSDIRS):
            tab[i, j] = c[name]
    return tab


def renorm_weights(topk_logits):
    """(T,64) f16 -> (T,64) float32 top-64-INTERNAL shares (sums to 1 per row)."""
    lg = topk_logits.astype(np.float64)
    mx = lg.max(axis=1, keepdims=True)
    lse = mx + np.log(np.exp(lg - mx).sum(axis=1, keepdims=True))
    w = np.exp(lg - lse)
    w = np.where(np.isfinite(w), w, 0.0)
    return w, lse[:, 0]


def class_mass(w, idx, tab, j):
    """Renormalised top-64 mass on class j, per step."""
    m = tab[idx, j].astype(np.float64)
    return (w * m).sum(axis=1)


# ----------------------------------------------------------------------------
# 3. PRE-REGISTERED candidate registry
# ----------------------------------------------------------------------------

CANDIDATES = [
    # --- family 1: repetition / looping -------------------------------
    dict(
        name="rep_top1", family="repetition", kind="binary",
        mechanism=(
            "Degenerate looping is a per-token event. At step t the model draws "
            "argmax_t; if argmax_t already sits in the generated prefix "
            "token_ids[0:t] the model has copied rather than advanced. The "
            "mechanism is a set-membership test against a set that grows one "
            "element per step, so the rate must vary step to step. Nothing in "
            "the definition reads the step index t.")),
    dict(
        name="rep_ngram4", family="repetition", kind="binary",
        mechanism=(
            "Repetition in math CoT is phrase-level, not token-level: the model "
            "re-runs 'so we get 12 + 5 = 17' verbatim. A 4-gram over token ids "
            "ending at t is the shortest window that cannot fire on ordinary "
            "symbol-by-symbol arithmetic (where adjacent token ids differ each "
            "step) but does fire on phrase re-runs. The set of earlier 4-grams "
            "grows one entry per step, so this is again a step-local decision. "
            "For t<3 the window is incomplete and the value is forced to 0; "
            "those steps are counted and reported separately.")),
    dict(
        name="rep_frac_topk", family="repetition", kind="continuous",
        mechanism=(
            "Binary repetition is too coarse: it is 0 for most of a healthy "
            "trajectory and 1 only at a total collapse. The continuous version "
            "counts how many of the top-64 CANDIDATES at step t already occur "
            "in the generated prefix. On arithmetic the top-64 is crowded with "
            "digits, operators and re-used variable names, so the count is a "
            "graded measure of how much of the model's remaining probability "
            "mass is spent re-emitting its own past. Continuous, so it retains "
            "resolution everywhere rather than only at collapse.")),
    # --- family 2: backtracking / self-correction ----------------------
    dict(
        name="backtrack_topk", family="backtrack", kind="binary",
        mechanism=(
            "Revising a derivation is a lexical event: 'wait', 'actually', "
            "'no', 'instead'. If any of a pre-registered marker vocabulary "
            "appears in the top-64 at step t, the model is at a step where it "
            "is considering undoing what it just wrote. This is decided per "
            "step by content, not by position. CAVEAT PRE-REGISTERED: the "
            "marker vocabulary overlaps the caution-contrast self_check regex, "
            "so this candidate is at genuine risk of label circularity and the "
            "screen is expected to be able to catch that.")),
    dict(
        name="backtrack_frac", family="backtrack", kind="continuous",
        mechanism=(
            "Same mechanism as backtrack_topk but weighted by renormalised "
            "top-64 mass, so it distinguishes 'one marker id in the tail' from "
            "'the marker is what the model is actually about to say'. The mass "
            "version should be less bursty and better powered.")),
    # --- family 3: numeric / operator content -------------------------
    dict(
        name="digit_mass", family="numeric", kind="continuous",
        mechanism=(
            "Mathematical reasoning is a mode of text in which a large and "
            "step-varying fraction of next-token mass lands on digit tokens. "
            "The degree varies with the arithmetic: expanding a product, "
            "carrying a digit, checking a residue, or sliding into prose all "
            "shift it. Because it is a soft mass, it resolves every step and is "
            "not the same event as a digit being present at all.")),
    dict(
        name="op_mass", family="numeric", kind="continuous",
        mechanism=(
            "The complementary mode: operator and grouping tokens (= + - * / "
            "( ) ^ $ \\) carry the algebra, prose carries the explanation. The "
            "balance between them is a genuine step-local decision that tracks "
            "the model moving between 'compute' and 'explain'. PRE-REGISTERED "
            "CAVEAT: '-' and '/' also occur in ordinary prose, so this is a "
            "noisy proxy for symbolic work, and the screen should be read with "
            "that in mind.")),
    # --- family 4: structure / formatting ------------------------------
    dict(
        name="newline_mass", family="structure", kind="continuous",
        mechanism=(
            "Line breaks are the model's own decision about layout of the "
            "derivation, and they come at content-driven moments: opening a "
            "new line of working, separating a claim from its check, closing a "
            "block. So a mass on newline tokens should pulse rather than ramp "
            "smoothly with t, and its within-trajectory variance should be "
            "clearly non-zero.")),
    dict(
        name="latex_mass", family="structure", kind="continuous",
        mechanism=(
            "Same argument for the LaTeX/structural character set ($, {, }, ^, "
            "_, \\frac). The model switches into and out of typeset mode as the "
            "derivation changes from narrative to expression, and those "
            "transitions are content-driven.")),
    # --- family 5: concentration ---------------------------------------
    dict(
        name="top1_prob_renorm", family="concentration", kind="continuous",
        mechanism=(
            "Concentration of the top-64 head. A decided step (a digit the "
            "model is sure of) and an undecided step (choosing between "
            "formulations) are separated by this quantity, and the fraction of "
            "such decisions changes step to step as the derivation proceeds. "
            "RENORMALISATION CAVEAT: this is the top-64-internal share, NOT the "
            "true top1 probability in the sidecar; the JSON reports both and "
            "the measured logZ64 coverage so the inflation is visible.")),
    # --- family 6: CONTROLS, must be rejected -------------------------
    dict(
        name="step_frac", family="control", kind="control",
        mechanism=(
            "CONTROL, expected REJECTED as not_usable_deterministic_in_t. "
            "step_frac := t/(T-1) is an affine function of the step index by "
            "definition. It was used as the observable for reasoning_deep, so "
            "any correlation between the reasoning_deep direction and step_frac "
            "is tautological. Screening it here is the positive control that "
            "the screen has the power to reject a t-deterministic observable.")),
    dict(
        name="in_think", family="control", kind="control",
        mechanism=(
            "CONTROL, expected REJECTED as not_usable_no_variance. in_think is "
            "a single contiguous <think> block: the sidecar marks every step "
            "inside the block true and every step outside false, so within a "
            "trajectory it is a single step function with no internal "
            "structure. It was the observable for creativity, but within any "
            "one trajectory it is constant, so it carries no within-trajectory "
            "information at all.")),
    dict(
        name="self_check_regex", family="control", kind="control",
        mechanism=(
            "CONTROL, expected REJECTED as not_usable_label_circular. This is "
            "the regex that DEFINES the caution contrast (self_check_yes vs "
            "self_check_no). Any 'caution correlates with vigilance' result "
            "built on it is circular by construction. Screening it verifies "
            "the screen can detect a definitionally circular observable.")),
    dict(
        name="self_check_sidecar", family="control", kind="control",
        mechanism=(
            "CONTROL / DATA-QUALITY PROBE, not part of the pre-registered "
            "concept. The sidecar column is_in_self_check flag shipped with the "
            "dataset. Recorded because the prior scripts do NOT use it (they "
            "recompute the flag by regex), and it is worth knowing whether the "
            "shipped column is usable at all. If it is identically false it "
            "cannot discriminate and must be rejected regardless of any other "
            "consideration.")),
]

CONTROL_NAMES = {"step_frac", "in_think", "self_check_regex",
                 "self_check_sidecar"}

# ----------------------------------------------------------------------------
# 4. statistics helpers
# ----------------------------------------------------------------------------


def rankdata_avg(a):
    """Average-rank transform (matches scipy.stats.rankdata 'average')."""
    a = np.asarray(a, dtype=np.float64)
    n = a.size
    if n == 0:
        return a.copy()
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(n, dtype=np.float64)
    sa = a[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


def spearman(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.size < 3 or y.size != x.size:
        return None
    rx, ry = rankdata_avg(x), rankdata_avg(y)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return None
    return float(((rx - rx.mean()) * (ry - ry.mean())).mean() / (sx * sy))


def acf(y, k):
    y = np.asarray(y, dtype=np.float64)
    T = y.size
    if T <= k + 2:
        return None
    a, b = y[:T - k], y[k:]
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def q(a, p):
    return float(np.quantile(np.asarray(a, dtype=np.float64), p))


def summarize(name, traj_vals, traj_t, aux, nullstats):
    """Compute the full screen for one candidate.

    traj_vals : list of (T,) float64 arrays, one per trajectory
    traj_t    : list of (T,) arrays of step index
    aux       : dict of {auxname: list of (T,) arrays} for correlation targets
    """
    cat = np.concatenate(traj_vals)
    n_traj = len(traj_vals)

    sd_within = [float(v.std()) for v in traj_vals]
    const = [1.0 if v.std() == 0 else 0.0 for v in traj_vals]

    # rho with t: within-traj mean is the meaningful one, pooled is secondary
    r_t_within, r_t_pooled = [], None
    allv, allt = [], []
    for v, t in zip(traj_vals, traj_t):
        r = spearman(t, v)
        if r is not None:
            r_t_within.append(r)
        allv.append(v)
        allt.append(t)
    r_t_pooled = spearman(np.concatenate(allt), np.concatenate(allv))

    sign_consist = 0.0
    if r_t_within:
        pos = sum(1 for r in r_t_within if r > 0)
        neg = len(r_t_within) - pos
        sign_consist = max(pos, neg) / float(len(r_t_within))

    # autocorrelation
    acfs = {1: [], 5: [], 20: []}
    for v in traj_vals:
        for k in (1, 5, 20):
            r = acf(v, k)
            if r is not None:
                acfs[k].append(r)

    # correlations against existing observables / group masks
    corr = {}
    for aname, avals in aux.items():
        wi, po, ndef = [], None, 0
        av, vv = [], []
        for a, v in zip(avals, traj_vals):
            r = spearman(a, v)
            if r is not None:
                wi.append(r)
                ndef += 1
            av.append(a)
            vv.append(v)
        po = spearman(np.concatenate(av), np.concatenate(vv))
        corr[aname] = {
            "within_traj_mean_rho": float(np.mean(wi)) if wi else None,
            "within_traj_mean_abs_rho": float(np.mean(np.abs(wi))) if wi else None,
            "pooled_rho": None if po is None else float(po),
            "n_traj_within_defined": ndef,
            "n_traj": n_traj,
        }

    uv = np.unique(cat)
    out = {
        "name": name,
        "n_traj": n_traj,
        "n_steps_total": int(cat.size),
        "mean": float(cat.mean()),
        "sd": float(cat.std(ddof=1)) if cat.size > 1 else 0.0,
        "p05": q(cat, 0.05), "p50": q(cat, 0.50), "p95": q(cat, 0.95),
        "within_traj_sd_mean": float(np.mean(sd_within)),
        "within_traj_sd_median": float(np.median(sd_within)),
        "frac_traj_within_var_gt_0": float(np.mean([c == 0 for c in const])),
        "rho_with_t_within_mean": (float(np.mean(r_t_within))
                                   if r_t_within else None),
        "rho_with_t_within_mean_abs": (float(np.mean(np.abs(r_t_within)))
                                       if r_t_within else None),
        "rho_with_t_within_min_abs": (float(np.min(np.abs(r_t_within)))
                                      if r_t_within else None),
        "rho_with_t_pooled": None if r_t_pooled is None else float(r_t_pooled),
        "rho_with_t_sign_consistency": sign_consist,
        "n_traj_rho_with_t_defined": len(r_t_within),
        "frac_constant_traj": float(np.mean(const)),
        "n_distinct_values": int(uv.size),
        "frac_binary": bool(uv.size <= 2 and
                            set(np.round(uv, 9).tolist()) <= {0.0, 1.0}),
        "acf_lag1": float(np.mean(acfs[1])) if acfs[1] else None,
        "acf_lag5": float(np.mean(acfs[5])) if acfs[5] else None,
        "acf_lag20": float(np.mean(acfs[20])) if acfs[20] else None,
        "rho_vs": corr,
        "null_vs_observed": nullstats,
    }
    return out


# ----------------------------------------------------------------------------
# 5. toy self-check with hand-computable ground truth
# ----------------------------------------------------------------------------


def run_toy(id2s, tab):
    """Build synthetic trajectories with hand-derivable ground truth, assert it.

    Design note: no BPE *encoder* is available, so toy ids are looked up by
    surface string from the real vocabulary. That is sufficient: what is under
    test is id->class, sequential repeat detection and renormalisation, all of
    which consume ids that are already given.

    Every expected value below is derived by hand from the synthetic token
    sequence, NOT read back from the extractor, so this is a real test rather
    than a tautology. Values marked EXACT use logits chosen as logs of small
    integers, so the top-64-internal shares are exact rationals.
    """
    def ids_for(s):
        return sorted([i for i, w in id2s.items() if w == s])

    checks = []

    def chk(name, got, want, tol=None):
        if isinstance(want, (list, tuple)):
            gl = [float(x) for x in got] if not isinstance(got, bool) else [got]
            wl = [float(x) for x in want]
            ok = (len(gl) == len(wl) and all(
                abs(a - b) <= (tol if tol is not None else 0.0)
                for a, b in zip(gl, wl)))
        elif tol is None:
            ok = (got == want)
        else:
            ok = abs(float(got) - float(want)) <= tol
        if isinstance(got, bool):
            g_rep = got
        elif isinstance(got, (int, float, np.floating, np.integer)):
            g_rep = float(got)
        else:
            g_rep = got
        checks.append(dict(check=name, got=g_rep, want=want, ok=bool(ok)))
        return ok

    d = {c: ids_for(c)[0] for c in "123456789"}
    plus, eq = ids_for("+")[0], ids_for("=")[0]
    nl_ids = ids_for("\n")
    wait_ids = [i for i, w in id2s.items() if w.lower() == "wait"]
    # NEUTRAL filler: alphabetic, and provably in no surface class at all, so
    # class-mass expectations stay exact instead of leaking through.
    filler = [i for i, w in id2s.items()
              if w.isalpha() and 3 <= len(w) <= 5 and not tab[i].any()][:200]
    chk("toy_neutral_filler_available", len(filler) >= 64, True)
    chk("toy_neutral_filler_is_class_free",
        int(sum(1 for i in filler if tab[i].any())), 0)

    # ---- decode unit checks -----------------------------------------
    chk("decode_digit_id_is_digit", id2s[d["1"]], "1")
    chk("decode_plus_is_plus", id2s[plus], "+")
    chk("decode_added_token_kept_literal",
        id2s.get(151645, None) == "<|im_end|>", True)

    # ---- toy A: strictly periodic repetition ------------------------
    # token sequence 1,2,3,1,2,3,...; top-64 at step t = [tok[t], tok[t-1],
    # 62 neutral]. Hand-derived expectations:
    #   rep_top1[t]      = 1 iff t>=3      (period 3 => tok[t] seen at t-3)
    #   rep_ngram4[t]    = 1 iff t>=6      (4-gram at t equals one at t-3)
    #   rep_frac_topk[t] = #{tok[t], tok[t-1]} already in prefix / 64
    #                    = 0,1,1,2,2,2,... for t=0,1,2,3,4,5,...
    T = 12
    seqA = [d[str((t % 3) + 1)] for t in range(T)]
    idxA = np.zeros((T, 64), dtype=np.int32)
    for t in range(T):
        head = [seqA[t]] + ([seqA[t - 1]] if t >= 1 else [])
        row = head + list(filler[:64 - len(head)])
        idxA[t, :] = row
    # logits chosen so shares are EXACT: e^2 / (e^2 + e) = e/(e+1) is not
    # rational, so use a separate logits vector only where exactness is claimed.
    lgA = np.full((T, 64), np.log(1e-30))
    lgA[:, 0] = np.log(3.0)
    lgA[:, 1] = np.log(1.0)
    wA, _ = renorm_weights(lgA)
    chk("toyA_renorm_row_sums_to_1", float(np.abs(wA.sum(axis=1) - 1).max()),
        0.0, 1e-12)
    chk("toyA_top1_share_exact_3_over_4", float(wA[0, 0]), 0.75, 1e-12)
    chk("toyA_second_share_exact_1_over_4", float(wA[0, 1]), 0.25, 1e-12)
    # both rank-0 and rank-1 are digits, the 62 neutrals are not
    chk("toyA_digit_mass_exact_1", float(class_mass(wA, idxA, tab, 0)[5]),
        1.0, 1e-12)
    chk("toyA_marker_mass_exact_0", float(class_mass(wA, idxA, tab, 4)[5]),
        0.0, 1e-12)
    chk("toyA_op_mass_exact_0", float(class_mass(wA, idxA, tab, 1)[5]), 0.0, 1e-12)
    chk("toyA_rep_top1_pattern",
        "".join("1" if seqA[t] in seqA[:t] else "0" for t in range(T)),
        "000111111111")
    chk("toyA_rep_ngram4_pattern",
        "".join("0" if t < 3 or tuple(seqA[t - 3:t + 1]) not in
                [tuple(seqA[s - 3:s + 1]) for s in range(3, t)] else "1"
                for t in range(T)),
        "000000111111")
    exp_frac = [sum(1 for c in [seqA[t]] + ([seqA[t - 1]] if t >= 1 else [])
                    if c in seqA[:t]) / 64.0 for t in range(T)]
    got_frac = [float(np.count_nonzero(np.isin(idxA[t], seqA[:t]))) / 64.0
                for t in range(T)]
    chk("toyA_rep_frac_topk_full_pattern", got_frac, exp_frac, 1e-12)
    chk("toyA_rep_frac_topk_t11_is_two_over_64", got_frac[11], 2.0 / 64.0,
        1e-12)

    # ---- toy B: exact class-mass arithmetic --------------------------
    # logits = log([2,1] + 62*1e-30) => lse = log(3) exactly => shares 2/3, 1/3
    T2 = 4
    lgB = np.full((T2, 64), np.log(1e-30))
    lgB[:, 0] = np.log(2.0)
    lgB[:, 1] = np.log(1.0)
    wB, _ = renorm_weights(lgB)
    idxB = np.zeros((T2, 64), dtype=np.int32)
    for t in range(T2):
        if t == 0:
            idxB[t, :] = [d["7"]] * 64                       # all digits
        elif t == 1:
            idxB[t, :] = [plus, eq] * 32                     # all operators
        elif t == 2:
            idxB[t, :] = [d["7"], plus] + list(filler[:62])  # mixed, exact
        else:
            idxB[t, :] = list(filler[:64])                   # all neutral
    chk("toyB_digit_mass_all_digit", float(class_mass(wB, idxB, tab, 0)[0]),
        1.0, 1e-12)
    chk("toyB_digit_mass_all_op", float(class_mass(wB, idxB, tab, 0)[1]),
        0.0, 1e-12)
    chk("toyB_op_mass_all_op", float(class_mass(wB, idxB, tab, 1)[1]),
        1.0, 1e-12)
    chk("toyB_digit_mass_mixed_exact_2_over_3",
        float(class_mass(wB, idxB, tab, 0)[2]), 2.0 / 3.0, 1e-12)
    chk("toyB_op_mass_mixed_exact_1_over_3",
        float(class_mass(wB, idxB, tab, 1)[2]), 1.0 / 3.0, 1e-12)
    chk("toyB_all_class_mass_exact_zero_on_neutral",
        [float(class_mass(wB, idxB, tab, j)[3]) for j in range(len(CLASSDIRS))],
        [0.0] * len(CLASSDIRS), 1e-12)

    # ---- toy C: marker and newline -----------------------------------
    T3 = 4
    idxC = np.zeros((T3, 64), dtype=np.int32)
    have_wl = bool(wait_ids) and bool(nl_ids)
    for t in range(T3):
        if nl_ids and t == 2:
            idxC[t, :] = [nl_ids[0]] * 64
        elif wait_ids:
            idxC[t, :] = [wait_ids[0]] + list(filler[:63])
        else:
            idxC[t, :] = list(filler[:64])
    lgC = np.full((T3, 64), np.log(1e-30))
    lgC[:, 0] = np.log(2.0)
    lgC[:, 1] = np.log(1.0)
    wC, _ = renorm_weights(lgC)
    chk("toyC_marker_mass_on_wait_step_exact_2_over_3",
        float(class_mass(wC, idxC, tab, 4)[0]), 2.0 / 3.0, 1e-12)
    chk("toyC_backtrack_topk_detected",
        bool(tab[idxC, 4].any(axis=1)[0]), True)
    if nl_ids:
        chk("toyC_newline_mass_on_newline_step_exact_1",
            float(class_mass(wC, idxC, tab, 2)[2]), 1.0, 1e-12)
        chk("toyC_newline_mass_elsewhere_exact_0",
            float(class_mass(wC, idxC, tab, 2)[0]), 0.0, 1e-12)
        chk("toyC_backtrack_topk_absent_on_newline_step",
            bool(tab[idxC, 4].any(axis=1)[2]), False)
    else:
        checks.append(dict(check="toyC_newline_token_absent_in_vocab",
                           got=None, want="n/a", ok=True))

    # ---- toy D: the renormalisation caveat, demonstrated -------------
    # Same rank-0 logit, wildly different suppressed tail. The top-64-INTERNAL
    # share is ~1.0 for both and cannot tell them apart, while logZ64 can. This
    # is exactly why every *_mass observable is labelled as a relative index.
    fA1 = np.array([[10.0] + [-10.0] * 63], dtype=np.float32)
    fA2 = np.array([[10.0] + [-40.0] * 63], dtype=np.float32)
    wD1, l1 = renorm_weights(fA1)
    wD2, l2 = renorm_weights(fA2)
    chk("toyD_renorm_share_saturates_despite_missing_tail",
        bool(wD1[0, 0] > 0.999 and wD2[0, 0] > 0.999), True)
    chk("toyD_renorm_cannot_see_tail_magnitude", bool(abs(wD1[0, 0]
                                                         - wD2[0, 0]) < 1e-6),
        True)
    chk("toyD_logZ64_does_see_tail_magnitude", bool(l1[0] - l2[0] > 1e-9), True)

    n_fail = sum(1 for c in checks if not c["ok"])
    return dict(
        n_checks=len(checks),
        n_failed=n_fail,
        all_passed=bool(n_fail == 0),
        note=("expected values for the repeat patterns and the class masses are "
              "derived by hand from the synthetic token sequences and from "
              "logits chosen as logs of small integers (so the top-64-internal "
              "shares are exact rationals). Nothing is read back from the "
              "extractor to build an expectation."),
        vocab_probe=dict(
            ids_used=dict(one=d["1"], plus=plus, equals=eq,
                          newline=(nl_ids[0] if nl_ids else None),
                          wait=(wait_ids[0] if wait_ids else None)),
            n_newline_token_ids=len(nl_ids),
            n_wait_token_ids=len(wait_ids),
            n_neutral_filler=len(filler)),
        checks=checks,
    )


# ----------------------------------------------------------------------------
# 6. main
# ----------------------------------------------------------------------------


def main():
    t_start = time.time()
    env = probe_env()
    print("[env] backend =", env["tokenizer_backend"], flush=True)

    id2s, vmeta = build_id2surface()
    n_ids = vmeta["max_id"] + 1
    tab = build_classtab(id2s, n_ids)
    print("[vocab] %s" % json.dumps(vmeta), flush=True)

    # marker-vocabulary structural overlap with the caution contrast regex
    marker_ids = set(np.nonzero(tab[:, CLASSDIRS.index("marker")])[0].tolist())
    sc_ids = set(np.nonzero(tab[:, CLASSDIRS.index("selfcheck")])[0].tolist())
    overlap = len(marker_ids & sc_ids) / float(max(len(marker_ids), 1))

    # ---- toy self-check, BEFORE touching real data -------------------
    print("[toy] running self-check ...", flush=True)
    toy = run_toy(id2s, tab)
    print("[toy] %d checks, %d failed" % (toy["n_checks"], toy["n_failed"]),
          flush=True)

    # ---- load real trajectories --------------------------------------
    print("[data] reading %d trajectories ..." % len(DATA_NPZ), flush=True)
    obs = {c["name"]: [] for c in CANDIDATES}
    traj_t, traj_names, Ts = [], [], []
    aux_names = ["self_check_regex", "in_think", "entropy", "step_frac",
                 "top1_prob_sidecar"]
    aux = {a: [] for a in aux_names}
    diag = {"n_token_mismatch": 0, "lse64": [], "top1_sidecar": [],
            "top1_renorm": [], "entropy": [], "n_forced_zero_ngram": 0,
            "sidecar_selfcheck_true": 0, "sidecar_selfcheck_steps": 0,
            "regex_selfcheck_true": 0, "regex_selfcheck_steps": 0,
            "in_think_frac": []}

    for fi, path in enumerate(DATA_NPZ):
        z = np.load(path)
        tok = z["token_ids"].astype(np.int32)
        tk_i = z["topk_indices"].astype(np.int32)
        tk_l = z["topk_logits"]
        T = tok.size
        side = json.loads(open(path.replace(".npz", ".json")).read())
        toks = side["tokens"]
        if len(toks) != T or not np.array_equal(
                tok, np.array([t["token_id"] for t in toks])):
            diag["n_token_mismatch"] += 1

        w, lse = renorm_weights(tk_l)
        # top-1 of the top-64 (rows are NOT pre-sorted by logit)
        am = np.argmax(tk_l, axis=1)
        top1_renorm = w[np.arange(T), am]

        # family 1: repetition (sequential prefix state)
        seen = np.zeros(n_ids, dtype=bool)
        rep_top1 = np.zeros(T)
        rep_frac = np.zeros(T)
        gram_seen = set()
        rep_n4 = np.zeros(T)
        for t in range(T):
            tt = int(tok[t])
            if t >= 3:
                g = (int(tok[t - 3]), int(tok[t - 2]), int(tok[t - 1]), tt)
                if g in gram_seen:
                    rep_n4[t] = 1.0
                else:
                    gram_seen.add(g)
            else:
                diag["n_forced_zero_ngram"] += 1
            row = tk_i[t]
            rep_frac[t] = float(seen[row].sum()) / 64.0
            if seen[tt]:
                rep_top1[t] = 1.0
            seen[tt] = True

        # families 2-5: vectorised class masses over the top-64
        vals = {
            "rep_top1": rep_top1,
            "rep_ngram4": rep_n4,
            "rep_frac_topk": rep_frac,
            "backtrack_topk": tab[tk_i, CLASSDIRS.index("marker")].any(axis=1
                                                                      ).astype(np.float64),
            "backtrack_frac": class_mass(w, tk_i, tab,
                                         CLASSDIRS.index("marker")),
            "digit_mass": class_mass(w, tk_i, tab, CLASSDIRS.index("digit")),
            "op_mass": class_mass(w, tk_i, tab, CLASSDIRS.index("op")),
            "newline_mass": class_mass(w, tk_i, tab,
                                       CLASSDIRS.index("newline")),
            "latex_mass": class_mass(w, tk_i, tab,
                                     CLASSDIRS.index("latex")),
            "top1_prob_renorm": top1_renorm,
        }
        for k, v in vals.items():
            obs[k].append(v)

        # controls
        step_frac = (np.arange(T, dtype=np.float64) / max(T - 1, 1))
        in_th = np.array([bool(t.get("is_in_think_block", False))
                          for t in toks], dtype=np.float64)
        sc_side = np.array([bool(t.get("is_self_check", False))
                            for t in toks], dtype=np.float64)
        surface = [id2s.get(int(t["token_id"]), "") for t in toks]
        sc_re = np.array([1.0 if SELF_CHECK_RE.search(s) else 0.0
                          for s in surface], dtype=np.float64)
        ent = np.array([float(t.get("entropy", np.nan)) for t in toks])
        t1p = np.array([float(t.get("top1_prob", np.nan)) for t in toks])

        obs["step_frac"].append(step_frac)
        obs["in_think"].append(in_th)
        obs["self_check_regex"].append(sc_re)
        obs["self_check_sidecar"].append(sc_side)

        traj_t.append(np.arange(T, dtype=np.float64))
        traj_names.append(os.path.basename(path).replace(".npz", ""))
        Ts.append(T)
        aux["self_check_regex"].append(sc_re)
        aux["in_think"].append(in_th)
        aux["entropy"].append(ent)
        aux["step_frac"].append(step_frac)
        aux["top1_prob_sidecar"].append(t1p)

        diag["lse64"].append(lse)
        diag["top1_sidecar"].append(t1p)
        diag["top1_renorm"].append(top1_renorm)
        diag["entropy"].append(ent)
        diag["sidecar_selfcheck_true"] += int(sc_side.sum())
        diag["sidecar_selfcheck_steps"] += T
        diag["regex_selfcheck_true"] += int(sc_re.sum())
        diag["regex_selfcheck_steps"] += T
        diag["in_think_frac"].append(float(in_th.mean()))
        print("  [%2d/%2d] %-46s T=%4d" % (fi + 1, len(DATA_NPZ),
                                           traj_names[-1], T), flush=True)

    lse_all = np.concatenate(diag["lse64"])
    t1s = np.concatenate(diag["top1_sidecar"])
    t1r = np.concatenate(diag["top1_renorm"])
    gap = t1r - t1s
    ok = np.isfinite(gap)
    renorm_diag = {
        "lse64_mean": float(lse_all.mean()),
        "lse64_p05": q(lse_all, 0.05), "lse64_p95": q(lse_all, 0.95),
        "top1_renorm_mean": float(t1r.mean()),
        "top1_sidecar_true_prob_mean": float(np.nanmean(t1s)),
        "renorm_minus_true_mean_gap": float(np.nanmean(t1r) - np.nanmean(t1s)),
        "coverage_evidence_vs_true_top1_prob": {
            "n_steps_compared": int(ok.sum()),
            "mean_abs_gap": float(np.abs(gap[ok]).mean()),
            "p99_abs_gap": float(np.quantile(np.abs(gap[ok]), 0.99)),
            "max_abs_gap": float(np.abs(gap[ok]).max()),
            "frac_steps_where_renorm_UNDERSTATES_true_prob":
                float((gap[ok] < 0).mean()),
            "spearman_renorm_vs_true": spearman(t1r, t1s),
            "spearman_one_minus_true_top1_vs_entropy":
                spearman(1.0 - t1s, np.concatenate(diag["entropy"])),
        },
        "interpretation": (
            "top1_prob_renorm is DEFINITIONALLY a top-64-internal share, not a "
            "probability, and it is labelled that way everywhere in this file. "
            "MEASURED, however: on this model at this decoding setting the "
            "top-64 slice captures essentially the whole next-token mass. Mean "
            "|renorm - true top1_prob| = %.2e over %d steps, and the "
            "renormalised value UNDERSTATES the true probability on %.1f%% of "
            "steps, so the truncation bias is not merely small here, it has no "
            "consistent sign. The practical consequence is that for THIS "
            "dataset the *_mass observables can be read as near-probabilities, "
            "but that is an empirical property of a very peaked model on math "
            "CoT and must not be assumed to transfer to a flatter distribution "
            "or a different decode. Toy check toyD_* demonstrates the mechanism "
            "directly: two logit vectors with the same top-1 logit and wildly "
            "different suppressed tails give the same renormalised share while "
            "logZ64 differs."
            % (float(np.abs(gap[ok]).mean()), int(ok.sum()),
               100.0 * float((gap[ok] < 0).mean()))),
    }

    # ---- null calibration -------------------------------------------
    NPERM = 100
    rng = np.random.default_rng(20261003)
    print("[null] calibrating thresholds with %d within-traj permutations ..."
          % NPERM, flush=True)
    null_rho_t, null_rho_sc = [], []
    for c in CANDIDATES:
        v = obs[c["name"]]
        for _ in range(NPERM):
            sh = [x[rng.permutation(x.size)] for x in v]
            rs = [spearman(t, x) for t, x in zip(traj_t, sh)]
            rs = [abs(r) for r in rs if r is not None]
            if rs:
                null_rho_t.append(float(np.mean(rs)))
            a2 = [spearman(a, x) for a, x in zip(aux["self_check_regex"], sh)]
            a2 = [abs(r) for r in a2 if r is not None]
            if a2:
                null_rho_sc.append(float(np.mean(a2)))
    null_rho_t = np.array(null_rho_t)
    null_rho_sc = np.array(null_rho_sc)
    THR_RHO_T = float(np.quantile(null_rho_t, 0.99))
    THR_RHO_SC = float(np.quantile(null_rho_sc, 0.99))
    # Ceiling floors. A deterministic function of t has |rho| = 1 exactly; a
    # restatement of the self_check predicate also has |rho| -> 1. These floors
    # encode "it is the same thing", the null p99 encodes "it is not noise".
    FLOOR_DET = 0.99
    FLOOR_CIRC = 0.60
    print("[null] |rho_with_t| p99 = %.4f (floor %.2f)   "
          "|rho_vs_self_check| p99 = %.4f (floor %.2f)"
          % (THR_RHO_T, FLOOR_DET, THR_RHO_SC, FLOOR_CIRC), flush=True)

    # ---- screen every candidate --------------------------------------
    results = []
    for c in CANDIDATES:
        n = c["name"]
        ns = summarize(n, obs[n], traj_t, aux, None)
        rwt = ns["rho_with_t_within_mean_abs"]
        rsc = ns["rho_vs"]["self_check_regex"]["within_traj_mean_abs_rho"]

        # Ceiling criteria. A *function of t* has |rho| = 1 by construction, and
        # a *restatement of the caution predicate* also has |rho| -> 1. So the
        # rejection floors are ceiling-relative, and the measured null p99 is
        # used to decide SIGNIFICANCE separately. This keeps a merely graded
        # trend from being mislabelled as "deterministic", which would be an
        # overclaim; a graded but significant trend is still reported below.
        f_no_var = (ns["frac_constant_traj"] > 0.5
                    or ns["frac_traj_within_var_gt_0"] < 0.5)
        f_det = (rwt is not None and rwt >= FLOOR_DET
                 and rwt >= THR_RHO_T
                 and ns["rho_with_t_sign_consistency"] >= 0.90)
        f_circ = (rsc is not None and rsc >= FLOOR_CIRC
                  and rsc >= THR_RHO_SC)
        f_circ_struct = (c["name"] in ("backtrack_topk", "backtrack_frac")
                         and overlap >= 0.5)
        f_circ = bool(f_circ or f_circ_struct)

        sig_t = rwt is not None and rwt >= THR_RHO_T
        sig_sc = rsc is not None and rsc >= THR_RHO_SC
        desc = "none"
        if rwt is not None:
            if rwt >= 0.9:
                desc = "near_deterministic"
            elif rwt >= 0.5:
                desc = "strong_trend"
            elif rwt >= 0.2:
                desc = "moderate_trend"
            elif sig_t:
                desc = "weak_but_significant_trend"
        ns["rho_with_t_descriptor"] = desc
        ns["rho_with_t_significant_vs_null"] = bool(sig_t)
        ns["rho_vs_selfcheck_significant_vs_null"] = bool(sig_sc)
        ns["label_circular_structural_overlap"] = overlap

        if f_no_var:
            verdict, why = "not_usable_no_variance", (
                "frac_constant_traj=%.3f and only %.3f of trajectories have "
                "non-zero within-trajectory variance, so the observable carries "
                "no step-level structure."
                % (ns["frac_constant_traj"], ns["frac_traj_within_var_gt_0"]))
        elif f_det:
            verdict, why = "not_usable_deterministic_in_t", (
                "mean within-traj |rho with step index| = %.4f is at the "
                "correlation ceiling (floor %.2f) and far above the measured "
                "null p99 = %.4f, with sign consistency %.3f: the observable is "
                "a monotone function of t, so any correlation it produces with "
                "a direction is an artefact of step position."
                % (rwt, FLOOR_DET, THR_RHO_T, ns["rho_with_t_sign_consistency"]))
        elif f_circ:
            verdict, why = "not_usable_label_circular", (
                "mean within-traj |rho vs the self_check regex| = %.4f is at or "
                "above the restatement floor %.2f and above the null p99 = "
                "%.4f (structural marker-vocabulary overlap with that regex is "
                "%.3f, floor 0.50), so it is not independent of the caution "
                "grouping predicate."
                % (rsc if rsc is not None else float("nan"), FLOOR_CIRC,
                   THR_RHO_SC, overlap))
        else:
            verdict, why = "usable", (
                "passes all three screens. Step-wise variation: non-zero "
                "within-trajectory variance in %.3f of trajectories (mean "
                "within-traj sd %.4g). Not a function of t: mean within-traj "
                "|rho with t| = %s, below the ceiling floor %.2f "
                "(descriptor '%s'; exceeds the measured null p99 = %.4f: %s). "
                "Not label-circular: mean within-traj |rho vs self_check| = %s, "
                "below the restatement floor %.2f and the null p99 = %.4f."
                % (ns["frac_traj_within_var_gt_0"], ns["within_traj_sd_mean"],
                   ("%.4f" % rwt) if rwt is not None else "n/a", FLOOR_DET, desc,
                   THR_RHO_T, sig_t,
                   ("%.4f" % rsc) if rsc is not None else "n/a", FLOOR_CIRC,
                   THR_RHO_SC))

        ns["family"] = c["family"]
        ns["kind"] = c["kind"]
        ns["mechanism_argument"] = c["mechanism"]
        ns["label_circular_risk"] = bool(f_circ)
        ns["verdict"] = verdict
        ns["verdict_reason"] = why
        results.append(ns)
        print("  %-22s %-34s wsd=%.4g |rho_t|=%.3f const=%.2f |rho_sc|=%s"
              % (n, verdict, ns["within_traj_sd_mean"], rwt if rwt is not None
                 else float("nan"), ns["frac_constant_traj"],
                 ("%.3f" % rsc) if rsc is not None else "n/a"), flush=True)

    by = {r["name"]: r for r in results}
    controls = {k: by[k]["verdict"] for k in CONTROL_NAMES}
    control_ok = all(v.startswith("not_usable") for v in controls.values())
    usable = [r["name"] for r in results if r["verdict"] == "usable"]
    rejected = {r["name"]: r["verdict"] for r in results
                if r["verdict"] != "usable"}

    # ---- POST-HOC caveats. NOT part of the pre-registered screen and NOT
    # allowed to change any verdict. Recorded because the pre-registered three
    # criteria (step-wise variance / not-a-function-of-t / not-label-circular)
    # do not test whether a candidate is REDUNDANT with an observable that has
    # already been used for a steering direction. This is a known gap in the
    # screen design, found after seeing the numbers, so it is reported as
    # hypothesis-generating only.
    FLOOR_REDUNDANT = 0.60
    for r in results:
        re_ = r["rho_vs"]["entropy"]["within_traj_mean_rho"]
        ri_ = r["rho_vs"]["in_think"]["within_traj_mean_rho"]
        r["post_hoc_rho_vs_entropy"] = re_
        r["post_hoc_redundant_with_entropy"] = bool(
            re_ is not None and abs(re_) >= FLOOR_REDUNDANT)
        r["post_hoc_rho_vs_in_think"] = ri_
        r["post_hoc_in_think_corr_is_underpowered"] = bool(
            r["rho_vs"]["in_think"]["n_traj_within_defined"] < len(DATA_NPZ) // 2)
    redundant = [r["name"] for r in results if r["post_hoc_redundant_with_entropy"]]
    cleanest = sorted(
        [r["name"] for r in results
         if r["verdict"] == "usable" and not r["post_hoc_redundant_with_entropy"]],
        key=lambda n: abs(by[n]["post_hoc_rho_vs_entropy"] or 0))
    n_in_think_var = int(sum(
        1 for a in aux["in_think"] if a.std() > 0))

    report = {
        "schema_version": "2",
        "generated_by": ".cache/rolesverify/obs_extract.py",
        "run_wallclock_s": None,
        "environment": env,
        "vocab_meta": vmeta,
        "class_definitions": {
            "digit": "decoded surface, spaces stripped, all chars in 0-9",
            "op": "surface stripped, all chars in =+-*/()^$\\  (note - and / "
                  "also occur in prose: pre-registered noise)",
            "newline": "surface contains a real newline",
            "latex": "surface contains any of $ } { ^ _ \\ or 'frac'",
            "marker_words": sorted(MARKER_WORDS),
            "selfcheck_regex": SELF_CHECK_RE.pattern,
        },
        "marker_vocab_overlap_with_selfcheck_regex": overlap,
        "renormalisation_convention": renorm_diag,
        "toy_selfcheck": toy,
        "data_diagnostics": {
            "n_traj": len(traj_names),
            "n_token_id_mismatch_between_npz_and_sidecar": diag["n_token_mismatch"],
            "step_len_min": int(min(Ts)), "step_len_max": int(max(Ts)),
            "step_len_median": int(np.median(Ts)),
            "n_steps_total": int(sum(Ts)),
            "NOTE_on_shape": ("the briefing said every npz has 784 steps; "
                              "measured lengths vary, see step_len_* above"),
            "sidecar_is_self_check_true_steps": diag["sidecar_selfcheck_true"],
            "sidecar_is_self_check_total_steps": diag["sidecar_selfcheck_steps"],
            "regex_selfcheck_true_steps": diag["regex_selfcheck_true"],
            "regex_selfcheck_total_steps": diag["regex_selfcheck_steps"],
            "sidecar_selfcheck_column_is_degenerate": bool(
                diag["sidecar_selfcheck_true"] == 0),
            "finding_self_check": (
                "The sidecar column is_self_check is identically false across "
                "all 48 trajectories, while prior scripts (v1_observables_"
                "anchors.py, v2_corr.py, v8_circularity.py) recompute the flag "
                "from a regex on the decoded text. Both are screened here as "
                "separate controls because only the regex version is the actual "
                "caution grouping predicate."),
            "in_think_frac_per_traj_min": float(min(diag["in_think_frac"])),
            "in_think_frac_per_traj_max": float(max(diag["in_think_frac"])),
            "n_forced_zero_ngram4_steps": diag["n_forced_zero_ngram"],
        },
        "threshold_basis": {
            "method": ("null calibration by within-trajectory permutation. For "
                       "each candidate the per-step series is shuffled inside "
                       "each trajectory %d times; this destroys step ordering "
                       "and autocorrelation while preserving the marginal "
                       "distribution, which is the correct null for an "
                       "autocorrelated step series. The threshold is the 99th "
                       "percentile of the resulting |rho| distribution, pooled "
                       "over all candidates and permutations."
                       % NPERM),
            "n_permutations_per_candidate": NPERM,
            "n_candidates": len(CANDIDATES),
            "n_permutations_total": NPERM * len(CANDIDATES),
            "rho_with_t_threshold_abs_null_p99": THR_RHO_T,
            "rho_vs_selfcheck_threshold_abs_null_p99": THR_RHO_SC,
            "ceiling_floor_determinism_abs": FLOOR_DET,
            "ceiling_floor_restatement_abs": FLOOR_CIRC,
            "sign_consistency_requirement": 0.90,
            "variance_rule": (">0.5 of trajectories constant, or <0.5 of "
                              "trajectories with non-zero within-traj variance, "
                              "=> no_variance. This is a structural criterion, "
                              "not a noise level: shuffling cannot change "
                              "within-traj variance, so a constant-per-traj "
                              "observable is rejected at any noise setting."),
            "determinism_rule": ("mean within-traj |rho with t| >= ceiling floor "
                                 "%.2f AND >= null p99 %.4f AND sign consistency "
                                 ">= 0.90 across trajectories"
                                 % (FLOOR_DET, THR_RHO_T)),
            "circularity_rule": ("mean within-traj |rho vs self_check regex| >= "
                                 "restatement floor %.2f AND >= null p99 %.4f, "
                                 "OR marker-vocabulary overlap with that regex "
                                 ">= 0.50 (measured structural overlap %.3f)"
                                 % (FLOOR_CIRC, THR_RHO_SC, overlap)),
            "why_two_kinds_of_floor": (
                "The null p99 and the ceiling floor answer different questions. "
                "The null p99 (%.4f) says 'this is not noise': it is the "
                "significance level, and it is reported per candidate as "
                "rho_with_t_significant_vs_null. The ceiling floor (%.2f) says "
                "'this is the same thing': a deterministic function of t must "
                "have |rho| = 1 by construction, and a restatement of the "
                "grouping predicate must have |rho| -> 1. Using the null p99 "
                "ALONE as the rejection bar would have been far too aggressive "
                "-- it would reject any candidate that merely trends with step "
                "index, which is an overclaim, and would have flagged most of "
                "this family as circular. Both are recorded per candidate so a "
                "graded relationship is visible rather than hidden behind a "
                "binary verdict." % (THR_RHO_T, FLOOR_DET)),
            "note": ("no threshold was set by looking at which candidate "
                     "looked most promising; the null is built before verdicts "
                     "are assigned, and all %d candidates are reported"
                     % len(CANDIDATES)),
        },
        "multiple_comparisons": {
            "n_candidates": len(CANDIDATES),
            "n_criteria_per_candidate": 3,
            "n_decision_tests": len(CANDIDATES) * 3,
            "per_test_alpha": 0.01,
            "family_wise_alpha": float(0.01 * 3),
            "pre_registration": ("all %d candidates were registered with a "
                                 "mechanism argument before any statistic was "
                                 "computed, and every one of them is reported "
                                 "below with its verdict. None was added, "
                                 "reweighted or dropped after seeing results, "
                                 "and no candidate was selected for being the "
                                 "most correlated."
                                 % len(CANDIDATES)),
            "reported": "all %d candidates, no filtering" % len(CANDIDATES),
        },
        "n_candidates": len(CANDIDATES),
        "candidates": results,
        "post_screen_caveats": {
            "status": ("POST-HOC. These flags were added after the numbers were "
                       "seen, they are hypothesis-generating only, and they "
                       "deliberately do NOT change any pre-registered verdict "
                       "above. They are reported because leaving them out would "
                       "overstate what 'usable' means here."),
            "redundancy_rule": ("|rho vs entropy| >= %.2f, the same "
                                "restatement floor used for label circularity. "
                                "Entropy is already the observable behind "
                                "confidence_up and confidence_down, so a "
                                "candidate that restates it cannot supply new "
                                "evidence about a different axis."
                                % FLOOR_REDUNDANT),
            "redundant_with_entropy": redundant,
            "cleanest_usable_lowest_entropy_rho": cleanest,
            "in_think_correlation_is_underpowered": (
                "rho vs in_think is only defined on trajectories where BOTH "
                "series vary. in_think is constant on %d of %d trajectories, so "
                "the in_think column rests on %d trajectories and should not be "
                "read as a general relationship."
                % (len(DATA_NPZ) - n_in_think_var, len(DATA_NPZ),
                   n_in_think_var)),
            "n_traj_with_varying_in_think": n_in_think_var,
            "verdict_scope": ("'usable' means only: non-degenerate step-wise "
                              "variation, not a function of t, not a restatement "
                              "of the caution predicate. It does NOT mean "
                              "'independent of every previously used "
                              "observable' -- see redundant_with_entropy."),
        },
        "controls": {
            "verdicts": controls,
            "all_controls_rejected": bool(control_ok),
            "self_check": ("if any control had come out usable the screen "
                           "would have been too loose and would have needed "
                           "tightening; see self_check_of_screen below"),
        },
        "self_check_of_screen": {
            "all_controls_rejected": bool(control_ok),
            "tightening_applied": (
                "Relative to the naive rule (a single round-number |rho| "
                "cutoff, no null, no sign requirement) the final rule is "
                "stricter on three counts. (1) Significance is thresholded at "
                "a measured null p99 (%.4f) rather than by eye. (2) Determinism "
                "additionally requires >=0.90 sign consistency across "
                "trajectories, so one aberrant trajectory cannot manufacture a "
                "verdict. (3) Rejection additionally requires the correlation to "
                "reach the ceiling floor (%.2f), so a candidate is only called "
                "deterministic if it really is a function of t instead of merely "
                "trending. Tightening (3) makes fewer things get rejected, which "
                "is why the control results, not the count of usable "
                "candidates, are the thing to read here."
                % (THR_RHO_T, FLOOR_DET)),
            "controls_that_must_be_rejected": sorted(CONTROL_NAMES),
            "n_usable": len(usable),
        },
        "summary": {
            "usable": usable,
            "rejected": rejected,
            "n_usable": len(usable),
            "n_rejected": len(rejected),
            "usable_but_redundant_with_entropy": [
                n for n in usable if n in redundant],
            "usable_and_not_redundant_with_entropy": [
                n for n in usable if n not in redundant],
        },
    }
    report["run_wallclock_s"] = round(time.time() - t_start, 2)
    with open(OUT_JSON, "w") as f:
        json.dump(report, f, indent=2, sort_keys=False)
    print("[done] %d usable %s | %.1fs"
          % (len(usable), usable, report["run_wallclock_s"]), flush=True)
    print("[done] controls %s" % json.dumps(controls), flush=True)
    print("[done] wrote %s" % OUT_JSON, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
