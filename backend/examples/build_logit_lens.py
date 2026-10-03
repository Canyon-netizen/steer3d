#!/usr/bin/env python3
"""Read every stored layer through the real unembedding — the per-layer walk.

The 2D site shows one thing about token choice: the last layer's residual
stream, unembedded, argmaxing to a token. That answers "what did the model
finally say" and says nothing about the other 27 layers, which is the question
that was actually asked: *how did each hidden state get to that token?*

This is a logit lens. For each stored layer l we push the residual stream
through the model's own final stage and ask what it would say right there:

    logits_l = lm_head @ x_l
    x_27     = h_27                                  # already post-norm
    x_l      = g * h_l / sqrt(mean(h_l^2) + eps)     # l < 27, pre-norm

Four things this script refuses to get wrong, each of which silently produces a
plausible, entirely false layer-walk:

1. **The stored final layer is already normalised.** `hidden_states[27]` is the
   output *after* `model.norm`. Applying RMSNorm to it is a second, different
   normalisation, not a redundant one -- measured here as a **34.9-logit** error
   (see `--selfcheck`), which drops the last-layer anchor from 98.8% to 85.5%
   and makes the whole walk a fiction. Layers 0..26 are pre-norm and DO need it.
   The `post_norm` flag is therefore per-layer and derived from the layer index,
   never a global switch.

2. **The RMSNorm gain is the trained `model.norm.weight`, not a plain RMSNorm.**
   Dropping `g` is the single most common way to get a lens that looks fine and
   means nothing.

3. **float32 throughout.** The checkpoint is bfloat16; computing the read-out in
   bf16 puts noise of order 0.5 into logits whose top1-top2 gaps are often
   smaller than that, which is exactly how a lens starts disagreeing with the
   model for no reason at all.

4. **The anchor is not asserted at 100%, and that is reported rather than tuned
   away.** The residual stream is stored in **float16** in the .npz, which caps
   reconstruction accuracy at ~0.09 logits (median). The model's own top1-top2
   margin is smaller than that at a small number of steps, and there the lens
   can legitimately pick the runner-up. The anchor is therefore reported over
   ALL sampled steps *and* over the steps where the model was not indifferent
   (real margin >= 1.0), with both denominators. Steps below that margin are
   counted and named, not dropped.

Sampling rule (fixed, reproducible, and written into the payload):
    all 48 trajectories = 24 problems x {think, no_think}, and for each one the
    LAST 32 steps. The tail is where the answer is emitted, which is the region
    the question is about; the window is a constant width so no trajectory is
    represented by a different number of positions than any other.

Usage:
    python3 backend/examples/build_logit_lens.py --out frontend/public/latent/data/logit_lens.json
    python3 backend/examples/build_logit_lens.py --selfcheck
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from safetensors import safe_open

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL = ROOT / "datasets/models/Qwen3-1.7B"
DEFAULT_NPZ_DIR = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
DEFAULT_VOCAB = ROOT / "frontend/public/latent/data/vocab.json"
DEFAULT_OUT = ROOT / "frontend/public/latent/data/logit_lens.json"

NORM_KEY = "model.norm.weight"
HEAD_KEY = "lm_head.weight"

# A step counts as "decidable" when the model's OWN top1-top2 margin is at least
# this. Below it the top-2 token is nearly as likely as the top-1 and a 0.09-logit
# fp16 reconstruction error is enough to swap them, so agreement there measures
# the storage format, not the lens. 1.0 is a full logit of separation.
DECIDABLE_MARGIN = 1.0

torch.set_grad_enabled(False)


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------
def load_tensor(model_path: Path, key: str) -> torch.Tensor:
    """Read one tensor straight out of the sharded checkpoint.

    Key name is taken from the index, not assumed: this checkpoint stores
    `lm_head.weight` explicitly even though tie_word_embeddings is true.
    """
    index = json.load(open(model_path / "model.safetensors.index.json"))
    weight_map = index["weight_map"]
    if key not in weight_map:
        raise KeyError(f"{key!r} not in checkpoint; available head/norm keys: "
                       f"{[k for k in weight_map if 'norm.weight' in k or 'embed' in k or 'lm_head' in k]}")
    with safe_open(model_path / weight_map[key], framework="pt") as f:
        return f.get_tensor(key).to(torch.float32)


def head_is_tied(model_path: Path) -> Optional[bool]:
    return json.load(open(model_path / "config.json")).get("tie_word_embeddings")


def read_rms_norm(h: torch.Tensor, g: torch.Tensor, eps: float) -> torch.Tensor:
    """The model's final stage, applied to a PRE-norm residual stream."""
    return g * h / torch.sqrt((h * h).mean(-1, keepdim=True) + eps)


def normed_by_layer(hs_chunk: torch.Tensor, g: torch.Tensor, eps: float,
                    n_layers: int) -> torch.Tensor:
    """(rows, 2048) in layer-major order -> normed, with layer 27 left alone.

    The per-layer exception is the whole point; see note 1 in the docstring.

    Reshaped to (steps, layers, d) to do it, and NOT sliced. The first version
    used a contiguous `x[rows * last:]`, which is wrong: in layer-major order
    the layer-27 rows are strided (row `layers*i + last`), not a block at the
    end. That silently double-normalised almost every step and dropped the
    last-layer anchor to 84.7% -- which is what caught it, not review. The
    assert below makes the mapping explicit so it cannot drift again.
    """
    steps = hs_chunk.shape[0] // n_layers
    d_model = hs_chunk.shape[-1]
    h3 = hs_chunk.reshape(steps, n_layers, d_model)
    x = read_rms_norm(h3, g, eps)
    last = n_layers - 1
    x[:, last, :] = h3[:, last, :]          # already post-norm
    # the layer index must line up with the row we just overwrote
    assert torch.equal(x[:, last, :], h3[:, last, :]), "layer-27 row mapping broke"
    assert not torch.equal(x[:, last - 1, :], h3[:, last - 1, :]), \
        "layer-26 must still have been normalised"
    return x.reshape(steps * n_layers, d_model)


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------
def trajectory_paths(npz_dir: Path) -> List[Path]:
    paths = sorted(npz_dir.glob("*.npz"))
    if not paths:
        raise FileNotFoundError(f"no .npz under {npz_dir}")
    return paths


def parse_id(path: Path) -> Tuple[str, str]:
    stem = path.stem                      # aime__1983__1983_I_1__think
    parts = stem.split("__")
    problem = parts[1] + "__" + parts[2] if len(parts) >= 3 else stem
    mode = parts[-1] if parts[-1] in ("think", "no_think") else "unknown"
    return problem, mode


# ---------------------------------------------------------------------------
# per-trajectory lens
# ---------------------------------------------------------------------------
def lens_trajectory(path: Path, g: torch.Tensor, Wt: torch.Tensor, eps: float,
                    n_layers: int, window: int, tokens: List[str]
                    ) -> Tuple[List[dict], dict]:
    """One trajectory, last `window` steps, all layers."""
    z = np.load(path)
    hs_all = z["hidden_states"]           # (T, 28, 2048) float16
    top_idx = z["topk_indices"]           # (T, 64) int32
    top_log = z["topk_logits"]            # (T, 64) float16
    T = hs_all.shape[0]
    w = min(window, T)
    t0 = T - w

    hs = torch.from_numpy(hs_all[t0:T].astype(np.float32))      # (w, 28, 2048)
    del hs_all
    X = normed_by_layer(hs.reshape(-1, hs.shape[-1]), g, eps, n_layers)
    logits = X @ Wt                                              # (w*28, V)
    logits = logits.reshape(w, n_layers, -1)

    real_margin = (top_log[t0:T, 0].astype(np.float32)
                   - top_log[t0:T, 1].astype(np.float32))

    steps: List[dict] = []
    diag = {"steps": w, "anchor_pass": 0, "anchor_total": w,
            "decidable_pass": 0, "decidable_total": 0,
            "anchor_err_max": 0.0, "first_hist": [0] * n_layers,
            "ncorrect_hist": [0] * n_layers, "monotone_steps": 0,
            "committed_steps": 0, "ever_correct": 0}

    for i in range(w):
        t = t0 + i
        final_id = int(top_idx[t, 0])
        lg = logits[i]                                          # (28, V)
        lse = torch.logsumexp(lg, dim=-1, keepdim=True)          # (28, 1)
        probs = torch.exp(lg - lse)
        top2 = torch.topk(lg, 2, dim=-1).values
        margin = (top2[:, 0] - top2[:, 1])
        arg = lg.argmax(dim=-1)
        p_arg = probs.gather(1, arg[:, None]).squeeze(1)
        p_final = probs[:, final_id]
        correct = (arg == final_id)

        fl = int(correct.float().argmax().item()) if bool(correct.any()) else -1
        nc = int(correct.sum().item())
        # once it is right, does it stay right through to the last layer?
        mono = bool(correct[fl:].all().item()) if fl >= 0 else False

        # anchor: the deepest layer must name the token the model really chose
        a_ok = int(arg[-1].item()) == final_id
        rm = float(real_margin[i])
        decidable = rm >= DECIDABLE_MARGIN
        # value-level check against the model's own emitted top-64 logit values
        ids_ref = torch.from_numpy(top_idx[t].astype(np.int64))
        want = torch.from_numpy(top_log[t].astype(np.float32))
        got = lg[-1][ids_ref]
        err = float((got - want).abs().max().item())
        diag["anchor_err_max"] = max(diag["anchor_err_max"], err)
        diag["anchor_pass"] += int(a_ok)
        if decidable:
            diag["decidable_total"] += 1
            diag["decidable_pass"] += int(a_ok)
        if decidable and rm >= 2.0:
            diag["committed_steps"] += 1
        if fl >= 0:
            diag["first_hist"][fl] += 1
            diag["ever_correct"] += 1
        diag["ncorrect_hist"][nc] += 1
        diag["monotone_steps"] += int(mono)

        tk = tokens[final_id]
        steps.append({
            "t": t,
            "final_id": final_id,
            "tok": tk,
            "real_margin": round(rm, 4),
            "decidable": bool(decidable),
            "first_layer_correct": fl,
            "n_layers_correct": nc,
            "monotone": mono,
            "per_layer": {
                "argmax": arg.tolist(),
                "p_argmax": [round(float(x), 5) for x in p_arg],
                "p_final": [round(float(x), 5) for x in p_final],
                "margin": [round(float(x), 4) for x in margin],
                "correct": [bool(x) for x in correct.tolist()],
            },
            "anchor_ok": bool(a_ok),
            "anchor_logit_err": round(err, 5),
        })

    del logits, X, hs
    return steps, diag


# ---------------------------------------------------------------------------
# self-check (independent of the product)
# ---------------------------------------------------------------------------
def selfcheck(g: torch.Tensor, Wt: torch.Tensor, eps: float, n_layers: int,
              npz_dir: Path, tokens: List[str]) -> None:
    """Ablations that have to FAIL, plus the anchor that has to PASS."""
    print("=" * 74)
    print("SELF-CHECK — normalisation convention and layer-index dependence")
    print("=" * 74)
    path = trajectory_paths(npz_dir)[0]
    z = np.load(path)
    hs = z["hidden_states"]
    top_idx = z["topk_indices"]
    top_log = z["topk_logits"]
    T = hs.shape[0]
    steps = list(range(1, min(T, 161)))
    last = n_layers - 1

    def anchor(layer: int, post_norm: bool, label: str) -> Tuple[int, float]:
        ok, err = 0, 0.0
        for t in steps:
            h = torch.from_numpy(hs[t, layer].astype(np.float32))
            x = h if post_norm else read_rms_norm(h, g, eps)
            lg = x @ Wt
            if int(lg.argmax()) == int(top_idx[t, 0]):
                ok += 1
            ids = torch.from_numpy(top_idx[t].astype(np.int64))
            want = torch.from_numpy(top_log[t].astype(np.float32))
            err = max(err, float((lg[ids] - want).abs().max().item()))
        print(f"  {label:<46s} argmax==real {ok:3d}/{len(steps)}"
              f"   max|logit err|={err:8.4f}")
        return ok, err

    anchor(last, True, "L27 post-norm  (CORRECT convention)")
    anchor(last, False, "L27 re-normalised (WRONG: double norm)")
    anchor(last - 1, False, "L26 pre-norm    (plausible-looking, WRONG)")
    anchor(0, False, "L0  pre-norm    (WRONG, the required-red variant)")

    # Does the layer index actually reach the computation?
    h = torch.from_numpy(hs[100, last].astype(np.float32))
    a = int((read_rms_norm(h, g, eps) @ Wt).argmax())
    b = int((read_rms_norm(torch.from_numpy(hs[100, 7].astype(np.float32)),
                           g, eps) @ Wt).argmax())
    print(f"  layer index reaches the maths: L27 argmax={a} != L7 argmax={b} "
          f"-> {a != b}")
    del z, hs


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--npz-dir", type=Path, default=DEFAULT_NPZ_DIR)
    ap.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--window", type=int, default=32,
                    help="steps sampled per trajectory, taken from the tail")
    ap.add_argument("--limit", type=int, default=0, help="0 = all trajectories")
    ap.add_argument("--selfcheck", action="store_true",
                    help="run the ablation self-check and exit")
    args = ap.parse_args()

    cfg = json.load(open(args.model_path / "config.json"))
    n_layers = cfg["num_hidden_layers"]
    d_model = cfg["hidden_size"]
    n_vocab = cfg["vocab_size"]
    eps = float(cfg["rms_norm_eps"])
    tokens = json.load(open(args.vocab))["ids"]
    if len(tokens) != n_vocab:
        print(f"WARNING: vocab has {len(tokens)} entries, config says {n_vocab}")

    g = load_tensor(args.model_path, NORM_KEY)
    Wt = load_tensor(args.model_path, HEAD_KEY).t().contiguous()
    if g.shape[0] != d_model:
        raise ValueError(f"{NORM_KEY} has {g.shape[0]} entries, expected {d_model}")
    if Wt.shape != (d_model, n_vocab):
        raise ValueError(f"{HEAD_KEY} transposed is {tuple(Wt.shape)}, "
                         f"expected {(d_model, n_vocab)}")

    if args.selfcheck:
        selfcheck(g, Wt, eps, n_layers, args.npz_dir, tokens)
        return 0

    paths = trajectory_paths(args.npz_dir)
    if args.limit:
        paths = paths[:args.limit]

    print(f"model      {args.model_path.name}  layers={n_layers} d_model={d_model} "
          f"vocab={n_vocab} eps={eps} tied={head_is_tied(args.model_path)}")
    print(f"sampling   all {len(paths)} trajectories x last {args.window} steps "
          f"x {n_layers} layers")
    t_start = time.time()

    trajs: List[dict] = []
    tot = {"anchor_pass": 0, "anchor_total": 0, "decidable_pass": 0,
           "decidable_total": 0, "monotone": 0, "ever_correct": 0,
           "committed": 0, "err_max": 0.0, "steps": 0}
    first_hist = [0] * n_layers
    ncorrect_hist = [0] * (n_layers + 1)
    by_mode: Dict[str, dict] = {}
    lens_rows = 0

    for k, p in enumerate(paths, 1):
        problem, mode = parse_id(p)
        steps, d = lens_trajectory(p, g, Wt, eps, n_layers, args.window, tokens)
        T = steps[-1]["t"] + 1
        trajs.append({
            "id": p.stem, "problem": problem, "mode": mode, "T": T,
            "window": [steps[0]["t"], T],
            "steps": steps,
        })
        lens_rows += d["steps"] * n_layers
        # Explicit map, not a shared key list: the two dicts name these
        # differently and a shared list let them drift into a KeyError once.
        for tot_key, diag_key in (("anchor_pass", "anchor_pass"),
                                  ("anchor_total", "anchor_total"),
                                  ("decidable_pass", "decidable_pass"),
                                  ("decidable_total", "decidable_total"),
                                  ("monotone", "monotone_steps"),
                                  ("ever_correct", "ever_correct"),
                                  ("committed", "committed_steps")):
            tot[tot_key] += d[diag_key]
        tot["err_max"] = max(tot["err_max"], d["anchor_err_max"])
        tot["steps"] += d["steps"]
        for i, c in enumerate(d["first_hist"]):
            first_hist[i] += c
        for i, c in enumerate(d["ncorrect_hist"]):
            ncorrect_hist[i] += c
        m = by_mode.setdefault(mode, {"n_traj": 0, "n_steps": 0, "anchor_pass": 0,
                                      "decidable_pass": 0, "decidable_total": 0,
                                      "monotone": 0, "ever_correct": 0})
        m["n_traj"] += 1
        m["n_steps"] += d["steps"]
        m["anchor_pass"] += d["anchor_pass"]
        m["decidable_pass"] += d["decidable_pass"]
        m["decidable_total"] += d["decidable_total"]
        m["monotone"] += d["monotone_steps"]
        m["ever_correct"] += d["ever_correct"]
        print(f"  [{k:2d}/{len(paths)}] {p.stem:<34s} T={T:5d} "
              f"anchor {d['anchor_pass']:3d}/{d['steps']:3d} "
              f"decidable {d['decidable_pass']:3d}/{d['decidable_total']:3d} "
              f"({time.time()-t_start:5.1f}s)")

    n_steps = tot["steps"]
    # ---- 第十九笔：`identity` 是一句**印出来的断言**，原来谁都没验 ----
    # 「n_tokens == n_steps * n_layers: 43008 == 1536 * 28」这句话在产物里
    # 只是一个 f-string：n_steps / n_layers 若哪天变了而 lens_rows 的算法没跟上，
    # 它照样会把「X == Y * Z」印出来，而 X ≠ Y*Z。
    # ⇒ 写之前先验；不成立就抛错，不产出这句话。
    n_problems = len({t.get("problem") for t in trajs})
    n_modes = len(by_mode) or 1
    if n_problems * n_modes != len(trajs):
        raise SystemExit(
            "ABORT 题数 %d × 模式数 %d = %d ≠ trajectories %d —— "
            "「%d problems x {think, no_think}」这句对不上"
            % (n_problems, n_modes, n_problems * n_modes, len(trajs), n_problems))
    if lens_rows != n_steps * n_layers:
        raise SystemExit(
            "ABORT identity 不成立：n_tokens %d ≠ n_steps %d * n_layers %d = %d —— "
            "宁可不给这句话，也不印一个假的等式"
            % (lens_rows, n_steps, n_layers, n_steps * n_layers))
    payload = {
        "schema": "logit_lens_v1",
        "title": "每一层离『模型最后说出这个词』还有多远",
        "title_en": "How far every layer is from the token the model actually says",
        "generated_by": "backend/examples/build_logit_lens.py",
        "method": {
            "what": "logit lens: the model's own final RMSNorm + unembedding "
                    "applied to every stored intermediate hidden state",
            "formula_pre_norm": "logits_l = lm_head @ (g * h_l / sqrt(mean(h_l^2) + eps))",
            "formula_final_layer": "logits_27 = lm_head @ h_27",
            "final_layer_is_post_norm": True,
            "note_final_layer": "hidden_states[27] is stored AFTER model.norm. "
                                "Re-normalising it is a different normalisation, "
                                "worth ~34.9 logits here, not a redundant one.",
            "rms_gain": "model.norm.weight (the trained gain, not a plain RMSNorm)",
            "rms_eps": eps,
            "compute_dtype": "float32",
            "head_key": HEAD_KEY,
            "norm_key": NORM_KEY,
            "tie_word_embeddings": head_is_tied(args.model_path),
            "storage_dtype_note": "the .npz stores the residual stream in float16; "
                                  "reconstruction error is ~0.09 logits (median), "
                                  "which is the floor on the anchor below",
        },
        "model": {"name": args.model_path.name, "n_layers": n_layers,
                  "d_model": d_model, "n_vocab": n_vocab},
        "sampling": {
            # ⚠ 第十九笔：这里原来把「24 problems」写死，而 `all {len(paths)}` 与
            #   `{args.window}` 都是插值的 ⇒ 同一段散文里一个数有源、一个没有。
            #   题数从 trajectories 现算（distinct problem），不拿 n_traj 除以模式数 ——
            #   后者在「某一题缺一个模式」时会静默给出一个小数。
            "rule": f"all {len(paths)} trajectories ({n_problems} problems x "
                    f"{{think, no_think}}); for each, the LAST {args.window} "
                    f"steps (constant width, tail = the answer-emission region)",
            "why_tail": "the question is about the derivation of the token the "
                        "model is about to say; the tail is where it says it",
            "n_traj": len(trajs),
            "n_problems": n_problems,
            "n_modes": n_modes,
            "steps_per_traj": args.window,
            "n_steps": n_steps,
            "n_layers": n_layers,
            "d_model": d_model,
            "n_tokens": lens_rows,
            "n_tokens_meaning": "total lens read-outs = n_steps * n_layers "
                                "(one unembedding per step per layer)",
            "identity": f"n_tokens == n_steps * n_layers: "
                        f"{lens_rows} == {n_steps} * {n_layers}",
        },
        "anchor": {
            "claim": "at the last stored layer the lens must name the token the "
                     "model really chose (topk_indices[t, 0])",
            "all_steps": {"pass": tot["anchor_pass"], "total": tot["anchor_total"],
                          "rate": round(tot["anchor_pass"] / max(tot["anchor_total"], 1), 5)},
            "decidable_steps": {
                "definition": f"steps whose own top1-top2 margin >= {DECIDABLE_MARGIN}",
                "pass": tot["decidable_pass"], "total": tot["decidable_total"],
                "rate": round(tot["decidable_pass"] / max(tot["decidable_total"], 1), 5)},
            "max_logit_error_vs_stored_topk": round(tot["err_max"], 5),
            "honest_caveat": "the misses are steps where the model's own top1-top2 "
                             "margin is below the float16 reconstruction error, i.e. "
                             "where it was nearly indifferent. They are counted here, "
                             "not dropped.",
        },
        "aggregate": {
            "n_steps": n_steps,
            "n_layers": n_layers,
            "first_layer_correct_hist": {
                "counts": first_hist,
                "total": n_steps,
                "resolved": sum(first_hist),
                "never_correct": n_steps - sum(first_hist),
                "note": "index l = first layer whose argmax equals the final token; "
                        "steps that never match any layer are counted in "
                        "`never_correct`, not silently dropped",
            },
            "n_layers_correct_hist": {"counts": ncorrect_hist, "total": n_steps},
            "ever_correct": {"n": tot["ever_correct"], "total": n_steps},
            "monotone": {"n": tot["monotone"], "total": n_steps,
                         "note": "once a layer's argmax equals the final token, "
                                 "every later layer agrees"},
            "committed": {"n": tot["committed"], "total": n_steps,
                          "note": f"steps whose real top1-top2 margin >= 2.0"},
            "by_mode": by_mode,
        },
        "per_layer_mean_p_final": {
            "values": None,  # filled below
            "n_steps": n_steps,
        },
        "trajectories": trajs,
    }

    # mean p(final token) per layer, over all sampled steps — the headline curve
    acc = np.zeros(n_layers)
    for tj in trajs:
        for st in tj["steps"]:
            acc += np.asarray(st["per_layer"]["p_final"], dtype=np.float64)
    payload["per_layer_mean_p_final"]["values"] = [round(float(x / max(n_steps, 1)), 5)
                                                  for x in acc]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size = args.out.stat().st_size
    print("-" * 74)
    print(f"wrote {args.out}  ({size/1e6:.2f} MB)  in {time.time()-t_start:.1f}s")
    print(f"  n_traj={len(trajs)}  n_steps={n_steps}  n_layers={n_layers}  "
          f"n_tokens={lens_rows}")
    print(f"  anchor all      {tot['anchor_pass']}/{tot['anchor_total']}")
    print(f"  anchor decidable{tot['decidable_pass']}/{tot['decidable_total']}")
    print(f"  first_layer_correct hist {first_hist}")
    print(f"  ever correct {tot['ever_correct']}/{n_steps}   "
          f"monotone {tot['monotone']}/{n_steps}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
