"""At the divergence step, say **why** one token won instead of the other.

What the viewer could show before this file
------------------------------------------
Screens 1-4 establish that the two arms differ, by how much, in which
directions, and *which* token each of them chose at the step where they parted.
None of that is an explanation. "Control said ``greater``, steered said
``exceeding``" is a fact about the output; the question the user actually
asked -- *why this token and not that one* -- needs the read-out in the middle.

The instrument: a logit lens, which is a **pure read-out**
--------------------------------------------------------
For Qwen3 the final stage is RMSNorm then an unembedding, with no
mean-centering:

    x(h)   = g ⊙ h / sqrt(mean(h²) + ε)          # g = model.norm.weight
    logitᵥ = uᵥ · x(h)                            # uᵥ = lm_head row v

Both ``g`` and ``u`` are constants of the checkpoint. So the logit of any
candidate token at any stored layer is arithmetic over an ``.npz`` that is
already on disk — no forward pass, no KV cache, no prompt.

**But the final layer is already past the norm.** transformers' capture appends
``self.norm``'s output as the last entry of ``hidden_states``, so
``hidden_states[n_layers]`` is post-norm and re-normalising it is a *second*,
different normalisation worth 16–19 logits::

    lm_head(hs[n_layers])        max|diff| = 0.000e+00   <- the real logits
    lm_head(norm(hs[n_layers]))  max|diff| = 1.6e+01 … 1.9e+01

This was found the expensive way. The first pass through this file applied the
norm, and the read-out then "disagreed" with the emitted token on 2 of 6
problems — by 0.42 and 2.42 logits, always in favour of the *control* arm's
token. Each obvious explanation was ruled out by measurement before the
layer-index one was checked: the index convention was right at every offset in
{±1, ±2, ±3} and failed only at the divergence step; fp16 storage moved a logit
by 0.001–0.003 against top-2 gaps of 0.17–2.46, three orders of magnitude too
small to matter; and ``lm_head.weight`` and ``model.embed_tokens.weight`` are
bit-identical in the checkpoint, so a mis-tied unembedding was not it either.

So ``post_norm`` is threaded through every read-out in this file, per layer
rather than globally, and check A6 verifies it against the model's own stored
top-1 — which needs no model to run, only the data file.

The check that is easy to get backwards
--------------------------------------
"the lens predicts the token the arm actually emitted" is close to a tautology
at layer 26 -- the true logits come from layer 28, and 26 is two blocks away.
So the claim this file is built to test is narrower and falsifiable:

    the *direction* of Δ decides the flip, not merely its size.

Four read-outs of the same control residual at the divergence step, all at the
deepest stored layer:

    C1  Δ = 0                     → must reproduce the control's own token
    C2  Δ = the real one          → must produce the steered arm's token
    C3  Δ from a *different* problem, same layer and index
    C4  Δ = random, norm-matched, several seeds

C1 and C2 alone would be satisfied by a lens that simply echoes whatever it is
handed. C3 and C4 are what make the number mean something: if a norm-matched
random vector flips the token just as reliably, then "the steer caused this
token" is not supported by this data, and the script says so.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch

NORM_KEY = "model.norm.weight"
HEAD_KEY = "lm_head.weight"
# Qwen3 config.json: rms_norm_eps = 1e-06. Copied rather than re-read so that a
# mismatch against the checkpoint is a visible literal to edit, not a default
# that silently drifts.
RMS_EPS = 1e-6


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------
def load_readout(path: Path) -> tuple:
    z = np.load(path)
    g = torch.from_numpy(z[NORM_KEY].astype(np.float32))
    W = torch.from_numpy(z[HEAD_KEY].astype(np.float32))
    return g, W


def load_vocab(path: Path) -> Dict[int, str]:
    """id -> surface form.

    Qwen's BPE is byte-level, so the space is stored as ``Ġ``. Left as-is the
    words would print as ``Ġgreater``; a reader comparing them against the
    generated text would reasonably call that a bug in the page.
    """
    raw = json.loads(path.read_text())
    vocab = raw["model"]["vocab"]
    inv = {int(i): t for t, i in vocab.items()}
    # `model.vocab` stops at 151642. Everything from there on -- including
    # <think> at 151667, which the trajectories actually emit -- lives in
    # `added_tokens`. Reading only `model.vocab` therefore turned real tokens
    # into "<id 151667>" in the output, which reads like a decode bug and is
    # one: it is a vocab that stops 294 ids early.
    for t in raw.get("added_tokens", []):
        inv[int(t["id"])] = t["content"]
    return {i: t.replace("\u0120", " ") for i, t in inv.items()}


def load_dim_names(path: Optional[Path]) -> List[dict]:
    if path is None or not path.is_file():
        return []
    return json.loads(path.read_text())["dims"]


# --------------------------------------------------------------------------
# the read-out
# --------------------------------------------------------------------------
def lens(h: torch.Tensor, g: torch.Tensor, W: torch.Tensor,
         post_norm: bool = False) -> torch.Tensor:
    """Full-vocabulary read-out of one stored residual.

    ``post_norm`` is not a convenience flag; it is a measured fact about the
    collector's output and getting it wrong is worth 16-19 logits. See the
    module docstring of ``diagnose_readout_index``: transformers' capture
    appends ``self.norm``'s output as the **last** entry of ``hidden_states``,
    so ``hidden_states[n_layers]`` is already normalised and re-normalising it
    is a second, different normalisation. Intermediate layers are pre-norm and
    do need it.
    """
    x = h if post_norm else g * h / torch.sqrt((h * h).mean() + RMS_EPS)
    return W @ x


def lens_rows(h: torch.Tensor, g: torch.Tensor, rows: torch.Tensor,
              post_norm: bool = False) -> torch.Tensor:
    """Read-out for a *subset* of tokens. Same formula, fewer columns."""
    x = h if post_norm else g * h / torch.sqrt((h * h).mean() + RMS_EPS)
    return rows @ x


def decompose(h: torch.Tensor, hp: torch.Tensor, g: torch.Tensor,
              u: torch.Tensor, post_norm: bool = False) -> torch.Tensor:
    """Per-dimension contribution to ``logit_u(hp) - logit_u(h)``.

    Exact, not a first-order expansion: the read-out is a diagonal map, so the
    difference of the logits is the sum of the per-coordinate differences. For
    a pre-norm layer that is ``g_i * u_i * (x'_i - x_i)`` with ``x = h/rms(h)``;
    at the post-norm final layer the stored vector *is* ``x``, so it collapses
    to the plainer ``u_i * (h'_i - h_i)``. The sum is checked against the
    directly computed logit difference in ``verify``.
    """
    if post_norm:
        return u * (hp - h)
    x = h / torch.sqrt((h * h).mean() + RMS_EPS)
    xp = hp / torch.sqrt((hp * hp).mean() + RMS_EPS)
    return g * u * (xp - x)


def token_list(ids: List[int], vocab: Dict[int, str]) -> str:
    out = []
    for i in ids:
        t = vocab.get(int(i))
        out.append(t if t is not None else f"<id {i}>")
    return repr("".join(out))


# --------------------------------------------------------------------------
# controls
# --------------------------------------------------------------------------
def counterfactual(base: torch.Tensor, delta: torch.Tensor, g: torch.Tensor,
                   W: torch.Tensor, target: int, post_norm: bool = False) -> int:
    """Which token wins when ``delta`` is added to ``base`` at the readout."""
    return int(torch.argmax(lens(base + delta, g, W, post_norm)))


def flip_threshold(base: torch.Tensor, delta: torch.Tensor, g: torch.Tensor,
                   W: torch.Tensor, won: int, lost: int,
                   post_norm: bool = False) -> Optional[float]:
    """Smallest α in a 0..2 sweep at which ``won`` overtakes ``lost``.

    Restricted to those two tokens rather than taking a full-vocabulary argmax
    for each α, for two reasons. It is the race that actually decided the
    output, and a 151936-wide argmax per step of a 100-step sweep, times five
    donors times 64 random directions times six problems, is about forty
    thousand full matvecs -- minutes of compute to answer a question about two
    numbers. The full-vocabulary argmax is still computed once per control
    (see ``counterfactual``), so "did the whole distribution move" stays
    answerable.
    """
    rows = torch.stack([W[won], W[lost]])
    prev = False
    for a in np.arange(0.0, 2.0001, 0.02):
        lg = lens_rows(base + float(a) * delta, g, rows, post_norm)
        win = bool(lg[0] > lg[1])
        if win and not prev:
            return float(a)
        prev = win
    return None


# --------------------------------------------------------------------------
# per problem
# --------------------------------------------------------------------------
def analyse_one(pid: str, npz_path: Path, json_path: Path, g: torch.Tensor,
                W: torch.Tensor, vocab: Dict[int, str], dim_names: List[dict],
                n_random: int, seed: int) -> dict:
    z = np.load(npz_path)
    rec = json.loads(json_path.read_text())
    layers = [int(x) for x in z["layers"]]
    c_ids = [int(x) for x in z["control_ids"]]
    s_ids = [int(x) for x in z["steered_ids"]]

    k = int(rec["paired"]["n_common_prefix"])
    if k >= min(len(c_ids), len(s_ids)):
        return {"id": pid, "skipped": f"no divergence (n_common={k})"}
    c_chosen, s_chosen = c_ids[k], s_ids[k]
    if c_chosen == s_chosen:
        return {"id": pid, "skipped": f"n_common={k} but ids agree there"}

    deep_from_npz = max(layers)
    # The collector writes the final layer separately, in float32, under
    # ``*_last32`` -- and that layer is post-norm while the rest are pre-norm.
    has_last = "control_last32" in z
    deep = deep_from_npz
    post_norm = bool(has_last)
    stored_top = {}

    def hs(arm: str, L: int) -> torch.Tensor:
        if L == deep_from_npz and f"{arm}_last32" in z:
            return torch.from_numpy(z[f"{arm}_last32"][k].astype(np.float32))
        return torch.from_numpy(z[f"{arm}_L{L}"][k].astype(np.float32))

    out: dict = {
        "id": pid,
        "problem": rec.get("problem", "")[:80],
        "step_index": k,
        "common_tail": token_list(c_ids[max(0, k - 6):k], vocab),
        "control_token": {"id": c_chosen, "text": vocab.get(c_chosen, f"<{c_chosen}>")},
        "steered_token": {"id": s_chosen, "text": vocab.get(s_chosen, f"<{s_chosen}>")},
        "per_layer": {},
        "post_norm_final_layer": post_norm,
    }

    # ---- lens walk over the stored layers --------------------------------
    # Only the final layer is post-norm; the ones above it are pre-norm and
    # need the RMSNorm applied, so the flag is per-layer and not global.
    lens_store: Dict[tuple, torch.Tensor] = {}
    for L in layers:
        entry: dict = {}
        pn = post_norm and L == deep_from_npz
        for arm in ("control", "steered"):
            lg = lens(hs(arm, L), g, W, pn)
            lens_store[(arm, L)] = lg
            entry[arm] = {
                "argmax": int(torch.argmax(lg)),
                "logit_chosen": float(lg[c_chosen]),
                "logit_steered_chosen": float(lg[s_chosen]),
                "gap_steered_minus_control": float(lg[s_chosen] - lg[c_chosen]),
                "top": [{"id": int(t), "text": vocab.get(int(t), ""),
                         "logit": float(v)}
                        for v, t in zip(*[x.tolist() for x in
                                           torch.topk(lg, 8)])],
            }
        out["per_layer"][str(L)] = entry

    # Fidelity of each partial read-out, measured against the *deepest stored*
    # read-out. This is NOT fidelity against the model's true output, which
    # would need layer 28; the name says so.
    for L in layers:
        for arm in ("control", "steered"):
            a = torch.log_softmax(lens_store[(arm, deep_from_npz)], -1)
            b = torch.log_softmax(lens_store[(arm, L)], -1)
            kl = float((a.exp() * (a - b)).sum())
            out["per_layer"][str(L)][arm]["kl_to_final_lens"] = kl

    # ---- counterfactual controls at the deepest stored layer -------------
    base = hs("control", deep)
    real_delta = hs("steered", deep) - base
    norm_real = float(real_delta.norm())

    ctl_argmax = out["per_layer"][str(deep)]["control"]["argmax"]
    ste_argmax = out["per_layer"][str(deep)]["steered"]["argmax"]
    ctl_hits = (ctl_argmax == c_chosen)
    ste_hits = (ste_argmax == s_chosen)

    cf = {
        "layer": deep,
        "delta_norm": norm_real,
        "C1_zero": {"argmax": counterfactual(base, torch.zeros_like(base), g, W,
                                             c_chosen, post_norm),
                    "predicts_control": None},
        "C2_real": {"argmax": counterfactual(base, real_delta, g, W, s_chosen,
                                             post_norm),
                    "predicts_steered": None},
        "C3_shuffled": [],
        "C4_random": [],
    }
    cf["C1_zero"]["predicts_control"] = cf["C1_zero"]["argmax"] == c_chosen
    cf["C2_real"]["predicts_steered"] = cf["C2_real"]["argmax"] == s_chosen
    cf["flip_threshold_real"] = flip_threshold(base, real_delta, g, W,
                                            s_chosen, c_chosen, post_norm)

    # ---- the degeneracy that makes C2/C3/C4 vacuous ----------------------
    # If the *control* base state, read at the deepest stored layer, already
    # points at the steered arm's token, then C2 "predicting" the steered
    # token is not evidence of anything: the target was the argmax before any
    # delta was added, and so it will be the argmax after a random one too.
    #
    # This is not hypothetical. It is 2 of the 6 problems in this dataset, and
    # with it unguarded the C4 "random" control scored 15/48 instead of 0/30 --
    # a headline that would have read as "random perturbations reproduce the
    # steered token" and supported exactly the wrong conclusion. A probe that
    # a constant can satisfy must first check that the constant is not already
    # satisfying it.
    base_argmax = int(torch.argmax(lens(base, g, W, post_norm)))
    cf["base_argmax"] = base_argmax
    cf["base_already_target"] = bool(base_argmax == s_chosen)
    cf["informative"] = not cf["base_already_target"]

    # ---- index-convention diagnostic -------------------------------------
    # A2 failing does not by itself distinguish "the lens is unfaithful" from
    # "hs is off by one". If the convention were wrong the lens would name a
    # *neighbouring* token consistently, so record which offset it actually
    # matches: a scattered pattern means noise, a constant +/-1 means a
    # convention bug.
    off = None
    for d in (-1, 0, 1):
        j = k + d
        if 0 <= j < len(c_ids) and c_ids[j] == base_argmax:
            off = d
            break
    out["lens_argmax_offset"] = off

    # C1 doubles as a check on the index convention: if hs were off by one,
    # the zero-delta read-out would name a different token and this goes False.
    out["index_convention_ok"] = bool(ctl_hits)

    return {"_out": out, "_cf": cf, "_base": base, "_delta": real_delta,
            "_k": k, "_c_chosen": c_chosen, "_s_chosen": s_chosen,
            "_lens_store": lens_store, "_layers": layers, "_deep": deep,
            "_post_norm": post_norm, "_deep_from_npz": deep_from_npz,
            "_stored_top": {a: z[f"{a}_top_ids"][k] for a in ("control", "steered")
                            if f"{a}_top_ids" in z},
            "_norm_real": norm_real, "_vocab": vocab, "_dims": dim_names,
            "_n_random": n_random, "_seed": seed, "_npz": npz_path,
            "_unit": (torch.from_numpy(z["unit"].astype(np.float32))
                      if "unit" in z and z["unit"].size == base.numel() else None)}


def shuffled_control(state: dict, others: List[dict]) -> dict:
    """C3: another problem's Δ, same layer and the same relative position.

    The step index differs per problem (8..44), so the donor's Δ is taken at
    *its own* divergence index. That is deliberate: a donor slice at a
    matching absolute step would be a different kind of perturbation, and
    mixing the two would make a failure ambiguous.
    """
    base = state["_base"]
    pn = state["_post_norm"]
    hits, rows = 0, []
    for o in others:
        d = (o["_steered_at_deep"] - o["_control_at_deep"])
        got = counterfactual(base, d, state["_g"], state["_W"],
                             state["_s_chosen"], pn)
        ok = got == state["_s_chosen"]
        hits += int(ok)
        rows.append({"donor": o["_out"]["id"], "argmax": got, "predicted": ok,
                     "text": state["_vocab"].get(got, "")})
    return {"n": len(others), "hits": hits, "rows": rows}


def random_control(state: dict) -> dict:
    """C4: random direction, norm-matched. The direction is what is under test."""
    g, W = state["_g"], state["_W"]
    base, n = state["_base"], state["_norm_real"]
    pn = state["_post_norm"]
    gen = torch.Generator().manual_seed(state["_seed"])
    hits, thresh, rows = 0, [], []
    for t in range(state["_n_random"]):
        d = torch.randn(base.shape, generator=gen)
        d = d / d.norm() * n
        got = counterfactual(base, d, g, W, state["_s_chosen"], pn)
        ok = got == state["_s_chosen"]
        hits += int(ok)
        th = flip_threshold(base, d, g, W, state["_s_chosen"],
                            state["_c_chosen"], pn)
        thresh.append(th)
        rows.append({"seed_trials": t, "argmax": got, "predicted": ok,
                     "text": state["_vocab"].get(got, ""), "flip_alpha": th})
    fin = [t for t in thresh if t is not None]
    return {"n": state["_n_random"], "hits": hits,
            "median_flip_alpha": float(np.median(fin)) if fin else None,
            "n_never_flipped": state["_n_random"] - len(fin),
            "rows": rows}


def verify(state: dict, out: dict) -> List[dict]:
    """Explicit checks. Each one is a claim that could be False."""
    g, W, dims = state["_g"], state["_W"], state["_dims"]
    deep, k = state["_deep"], state["_k"]
    base, delta = state["_base"], state["_delta"]
    # A6 re-reads the file for the stored top-k, so make sure the fixture
    # really has it before the check claims anything.
    st = state.get("_stored_top") or {}
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    # A1. The injection layer is flat *by construction*. If this is not
    # bit-exact, the whole "the vector enters at L20" story is wrong, and every
    # downstream number is measuring a different experiment.
    z = np.load(state["_npz"])
    inj = int(state.get("_inject_layer", 20))
    if f"control_L{inj}" in z and f"steered_L{inj}" in z:
        a = z[f"control_L{inj}"][k]
        b = z[f"steered_L{inj}"][k]
        chk(f"A1 L{inj} 两臂逐位相同（注入层按构造为平）",
            bool(np.array_equal(a, b)),
            f"max|diff|={float(np.abs(a.astype(np.float32) - b.astype(np.float32)).max()):.3e}")

    # A2/A3. The lens at the deepest stored layer names each arm's own token.
    chk("A2 对照臂 lens argmax == 实际选中的 token", out["index_convention_ok"],
        f"lens={out['per_layer'][str(deep)]['control']['argmax']} "
        f"actual={out['control_token']['id']}")
    chk("A3 干预臂 lens argmax == 实际选中的 token",
        out["per_layer"][str(deep)]["steered"]["argmax"] == out["steered_token"]["id"],
        f"lens={out['per_layer'][str(deep)]['steered']['argmax']} "
        f"actual={out['steered_token']['id']}")

    # A4. The *between-arm* logit difference for each candidate must be exactly
    # 0 at the injection layer -- that is what "the vector enters inside block
    # 20" means -- and non-zero below it. The within-arm gap between the two
    # candidates is a different quantity and is reported as a separate field;
    # checking that one against 0 would be a category error.
    deep_e = out["per_layer"][str(deep)]
    inj_e = out["per_layer"][str(inj)]
    for tag, key in (("control", "logit_chosen"), ("steered", "logit_steered_chosen")):
        d_inj = inj_e["steered"][key] - inj_e["control"][key]
        d_deep = deep_e["steered"][key] - deep_e["control"][key]
        chk(f"A4 {tag} 候选词的臂间 logit 差：L{inj} 恰为 0，L{deep} 非 0",
            d_inj == 0.0 and d_deep != 0.0,
            f"L{inj}={d_inj:.6f}  L{deep}={d_deep:+.4f}")

    # A5. The decomposition sums back to the directly computed logit change.
    pn = state["_post_norm"]
    Wc = state["_W"]
    rows = torch.stack([Wc[state["_c_chosen"]], Wc[state["_s_chosen"]]])
    direct = (lens_rows(base + delta, g, rows, pn)
              - lens_rows(base, g, rows, pn))
    decomp = torch.stack([decompose(base, base + delta, g, Wc[state["_c_chosen"]], pn),
                          decompose(base, base + delta, g, Wc[state["_s_chosen"]], pn)])
    err = float((decomp.sum(1) - direct).abs().max())
    chk("A5 逐维贡献求和 == 直接算的 logit 变化", err < 1e-3,
        f"max|sum(contrib) - direct| = {err:.3e}")

    # A6. The read-out of the final residual must reproduce the model's own
    # stored top-1, with **no model present** -- this is the check that makes
    # the whole "why this token" claim verifiable from the data file.
    #
    # The control is the same read-out with the norm applied a second time.
    # Reporting both matters: a single passing number cannot distinguish "the
    # read-out is exact" from "the norm flag is being ignored somewhere", but
    # a passing number next to a failing one can.
    st = state["_stored_top"]
    if st:
        z2 = np.load(state["_npz"])
        deep_np = state["_deep_from_npz"]
        for arm, want in (("control", state["_c_chosen"]),
                          ("steered", state["_s_chosen"])):
            h = torch.from_numpy(z2[f"{arm}_last32"][k].astype(np.float32))
            good = int(torch.argmax(lens(h, g, W, True)))
            bad = int(torch.argmax(lens(h, g, W, False)))
            stored = int(st[arm][0])
            chk(f"A6 {arm} 末层读出 == 模型自己存的 top-1（无需模型）",
                good == stored == want,
                f"读出={good} 存储={stored} 实际吐出={want}   "
                f"（多套一次 norm 的版本会给出 {bad}，这就是负控）")
    return checks


def name_for(dims: List[dict], i: int) -> str:
    if i < len(dims) and dims[i].get("top"):
        return ", ".join(t["t"] for t in dims[i]["top"][:3])
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paired-dir", required=True)
    ap.add_argument("--readout", required=True)
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--dim-names", default="")
    ap.add_argument("--inject-layer", type=int, default=20)
    ap.add_argument("--top-dims", type=int, default=8)
    ap.add_argument("--random-trials", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261001)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    g, W = load_readout(Path(a.readout))
    vocab = load_vocab(Path(a.vocab))
    dims = load_dim_names(Path(a.dim_names) if a.dim_names else None)
    pdir = Path(a.paired_dir)

    results, checks_all, states = [], [], []
    for npz_path in sorted(pdir.glob("pair_*.npz")):
        pid = npz_path.stem.replace("pair_", "")
        state = analyse_one(pid, npz_path, pdir / f"pair_{pid}.json", g, W,
                            vocab, dims, a.random_trials, a.seed)
        if "skipped" in state:
            print(f"  {pid}: SKIP {state['skipped']}")
            continue
        out, cf = state["_out"], state["_cf"]
        state["_g"], state["_W"] = g, W
        state["_inject_layer"] = a.inject_layer
        z = np.load(npz_path)
        dnp, kk = state["_deep_from_npz"], state["_k"]

        def _at(arm: str) -> torch.Tensor:
            key = (f"{arm}_last32" if f"{arm}_last32" in z else f"{arm}_L{dnp}")
            return torch.from_numpy(z[key][kk].astype(np.float32))

        state["_control_at_deep"] = _at("control")
        state["_steered_at_deep"] = _at("steered")
        states.append(state)

        out["controls"] = cf
        out["checks"] = verify(state, out)
        checks_all.extend(out["checks"])
        results.append(out)
        print(f"  {pid}  step {out['step_index']:3d}  "
              f"{out['control_token']['text']!r} -> {out['steered_token']['text']!r}  "
              f"|Δ|={cf['delta_norm']:.3f}  base已命中靶={cf['base_already_target']}  "
              f"C2={cf['C2_real']['predicts_steered']}  offset={out['lens_argmax_offset']}")

    # C3 / C4 need every problem's Δ, so they run after the per-problem pass.
    for st, out in zip(states, results):
        others = [o for o in states if o is not st]
        out["controls"]["C3_shuffled"] = shuffled_control(st, others)
        out["controls"]["C4_random"] = random_control(st)
        c3, c4 = out["controls"]["C3_shuffled"], out["controls"]["C4_random"]
        print(f"  {out['id']}  C3 shuffled {c3['hits']}/{c3['n']}   "
              f"C4 random {c4['hits']}/{c4['n']}   "
              f"random median flip α={c4['median_flip_alpha']}")

    # ---- the decomposition, for the two tokens that actually decided it ----
    for st, out in zip(states, results):
        g_, W_, deep = st["_g"], st["_W"], st["_deep"]
        base, delta = st["_base"], st["_delta"]
        pn = st["_post_norm"]
        hp = base + delta
        block: dict = {}
        for tag, tid in (("won", st["_s_chosen"]), ("lost", st["_c_chosen"])):
            c = decompose(base, hp, g_, W_[tid], pn)
            order = torch.argsort(c.abs(), descending=True)[:a.top_dims]
            block[tag] = {
                "token": {"id": tid, "text": st["_vocab"].get(tid, "")},
                "dlogit": float(c.sum()),
                "top_dims": [{"dim": int(i), "contribution": float(c[i]),
                              "delta_x": float(c[i] / (g_[i] * W_[tid, i] + 1e-30)),
                              "names": name_for(st["_dims"], int(i))}
                             for i in order],
            }
        out["decomposition"] = {"layer": deep, **block}

    # ---- the direction null, and how much of Δ is the injected vector ----
    # At the exact read-out layer the counterfactual is well defined: add a
    # vector to the control's final residual, read out the real logits. So the
    # question "did *this* direction promote the winner" has a real null --
    # norm-matched random directions, same read-out, same arithmetic.
    #
    # What this deliberately does NOT do is re-claim C2. At the read-out layer
    # C2 is true by construction (Δ is *defined* as the difference of the two
    # final residuals), so a 6/6 there is arithmetic, not evidence. The
    # percentile of the real logit shift inside the random-direction null is
    # the part that could have come out the other way.
    for st, out in zip(states, results):
        g_, W_, base, delta = st["_g"], st["_W"], st["_base"], st["_delta"]
        won, lost = st["_s_chosen"], st["_c_chosen"]
        rows = torch.stack([W_[won], W_[lost]])
        real_shift = (lens_rows(base + delta, g_, rows, pn)
                      - lens_rows(base, g_, rows, pn))

        gen = torch.Generator().manual_seed(st["_seed"] + 991)
        null = []
        for _ in range(st["_n_random"]):
            d = torch.randn(base.shape, generator=gen)
            d = d / d.norm() * st["_norm_real"]
            null.append((lens_rows(base + d, g_, rows, pn)
                         - lens_rows(base, g_, rows, pn)))
        null = torch.stack(null)                       # (N, 2)

        def pct(j: int) -> float:
            v = float(real_shift[j])
            col = null[:, j]
            return float((col <= v).float().mean() * 100.0)

        out["direction_null"] = {
            "n": st["_n_random"],
            "real_dlogit_won": float(real_shift[0]),
            "real_dlogit_lost": float(real_shift[1]),
            "null_dlogit_won_mean": float(null[:, 0].mean()),
            "null_dlogit_won_sd": float(null[:, 0].std()),
            "null_dlogit_lost_mean": float(null[:, 1].mean()),
            "null_dlogit_lost_sd": float(null[:, 1].std()),
            "percentile_won": pct(0),
            "percentile_lost": pct(1),
        }

        # How much of the move at the read-out point is the injected vector
        # itself, carried through the blocks above it, rather than the network
        # reorganising in response to it. These are very different stories and
        # only the second one means "the model re-thought".
        u = st["_unit"]
        if u is not None:
            un = u / max(float(u.norm()), 1e-8)
            proj = float(delta @ un)
            out["along_injected_vector"] = {
                "delta_norm": st["_norm_real"],
                "proj": proj,
                "sq_fraction": float(proj ** 2 / max(st["_norm_real"] ** 2, 1e-12)),
            }

    # ---- verdict ----------------------------------------------------------
    # Everything that involves "did the read-out land on the steered token" is
    # counted only over the problems whose control base is not already sitting
    # on the target. Mixing the two populations produced a wrong headline once
    # already (see base_already_target above), so the two are reported apart.
    inf = [r for r in results if r["controls"]["informative"]]
    deg = [r for r in results if not r["controls"]["informative"]]
    n = len(results)
    agg = {
        "n_problems": n,
        "n_informative": len(inf),
        "n_degenerate_base": len(deg),
        "degenerate_ids": [r["id"] for r in deg],
        "index_convention_ok": sum(r["index_convention_ok"] for r in results),
        "lens_argmax_offsets": {r["id"]: r["lens_argmax_offset"] for r in results},
        "C2_real_hits_informative": sum(
            r["controls"]["C2_real"]["predicts_steered"] for r in inf),
        "C3_shuffled_hits_informative": sum(
            r["controls"]["C3_shuffled"]["hits"] for r in inf),
        "C3_shuffled_total_informative": sum(
            r["controls"]["C3_shuffled"]["n"] for r in inf),
        "C4_random_hits_informative": sum(
            r["controls"]["C4_random"]["hits"] for r in inf),
        "C4_random_total_informative": sum(
            r["controls"]["C4_random"]["n"] for r in inf),
        "direction_null_won_percentiles": {
            r["id"]: r.get("direction_null", {}).get("percentile_won")
            for r in results},
        "sq_fraction_along_injected": {
            r["id"]: r.get("along_injected_vector", {}).get("sq_fraction")
            for r in results},
    }
    print("\n=== 汇总 ===")
    for kk, vv in agg.items():
        print(f"  {kk:34s} {vv}")
    fails = [c for c in checks_all if not c["ok"]]
    print(f"\n=== 检查 {len(checks_all) - len(fails)}/{len(checks_all)} 通过 ===")
    for c in fails:
        print(f"  FAIL {c['name']}  {c['detail']}")

    payload = {"schema": "divergence_logits_v1",
               "rms_eps": RMS_EPS,
               "inject_layer": a.inject_layer,
               "aggregate": agg,
               "checks": checks_all,
               "problems": results}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nwrote {a.out}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
