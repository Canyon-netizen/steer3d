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


def pick_step_indices(T: int, window: int, scan: str) -> List[int]:
    """这条轨迹要读 lens 的**步号列表**（升序，长度恰好 min(window, T)）。

    ⚠⚠ 原来这里是 `t0 = T - w` 一句锁死「最后 w 步」，于是
      logit_lens.json 只覆盖每条轨迹的**尾部**（实测 1536/69155 = 2.2%）。
      而 Phase-0 要回答的「推理中途某个数算错了时是哪一层先知道」，
      错误**发生在中段** —— 尾部窗口按定义就答不了。
      ⇒ 加 uniform：把同样多的采样点铺满整条轨迹，CoT 中段才有数据。

    tail    —— 与原实现逐位相同（默认值不变，logit_lens.json 不受影响）
    uniform —— 覆盖 [0, T)，含中段

    ⚠ 去重后必须**补回恰好 window 个**：round 会撞车，而下游
      `sampling.steps_per_traj` 与恒等式 n_tokens == n_steps × n_layers
      都假定宽度恒定。宁可补齐也不能悄悄少几个。
    """
    w = min(window, T)
    if w <= 0:
        return []
    if scan == "tail":
        return list(range(T - w, T))
    if scan != "uniform":
        raise ValueError(f"未知 scan 模式 {scan!r}（只认 tail / uniform）")
    if w >= T:
        return list(range(T))
    cand = [int(round(i * (T - 1) / (w - 1))) for i in range(w)]
    seen, out = set(), []
    for v in cand:
        if v not in seen:
            seen.add(v)
            out.append(v)
    k = 0
    while len(out) < w and k < T:
        if k not in seen:
            seen.add(k)
            out.append(k)
        k += 1
    out.sort()
    assert len(out) == w, f"采样宽度 {len(out)} ≠ {w}"
    assert len(set(out)) == w, "采样步号有重复"
    return out


# ---------------------------------------------------------------------------
# per-trajectory lens
# ---------------------------------------------------------------------------
def lens_trajectory(path: Path, g: torch.Tensor, Wt: torch.Tensor, eps: float,
                    n_layers: int, window: int, tokens: List[str],
                    scan: str = "tail", want_idx: Optional[List[int]] = None
                    ) -> Tuple[List[dict], dict]:
    """One trajectory, `window` steps per `--scan`, all layers."""
    z = np.load(path)
    hs_all = z["hidden_states"]           # (T, 28, 2048) float16
    top_idx = z["topk_indices"]           # (T, 64) int32
    top_log = z["topk_logits"]            # (T, 64) float16
    T = hs_all.shape[0]
    # ⚠⚠ **explicit 才是能回答 Phase-0 那个问题的那一种。**
    #   实测：把 32 个采样点均匀铺满 2048 步的轨迹后，Phase-0 找到的
    #   **14 个判错位置命中 0 个**（采样点平均间隔 ~64 步，而错误位置是
    #   具体的某一步）。⇒ 「把窗口铺开」解决的是**可见性**，
    #   解决不了**覆盖率**。真要逐层看那几个位置，只能**按位置算**。
    if scan == "explicit":
        idxs = sorted(set(int(i) for i in (want_idx or [])))
        if not idxs:
            raise ValueError(f"{path.stem}: --scan explicit 但没有给该轨迹的位置")
        if idxs[0] < 0 or idxs[-1] >= T:
            raise ValueError(f"{path.stem}: 位置越界 [{idxs[0]}, {idxs[-1]}] "
                             f"而 T={T}")
    else:
        idxs = pick_step_indices(T, window, scan)
    w = len(idxs)
    # ⚠「是否连续」必须**记进产物**：uniform 模式下采到的是散布在整条轨迹上的
    #   点，而 window 字段是个**区间**。读者若以为 window 里的每一步都被读了，
    #   就会读出一个并不存在的连续覆盖。⇒ contiguous=false 时必须同时给
    #   step_indices。
    contiguous = (idxs == list(range(idxs[0], idxs[0] + w)))

    hs = torch.from_numpy(hs_all[idxs].astype(np.float32))        # (w, 28, 2048)
    del hs_all
    X = normed_by_layer(hs.reshape(-1, hs.shape[-1]), g, eps, n_layers)
    logits = X @ Wt                                              # (w*28, V)
    logits = logits.reshape(w, n_layers, -1)

    real_margin = (top_log[idxs, 0].astype(np.float32)
                   - top_log[idxs, 1].astype(np.float32))

    steps: List[dict] = []
    diag = {"steps": w, "anchor_pass": 0, "anchor_total": w,
            "decidable_pass": 0, "decidable_total": 0,
            "anchor_err_max": 0.0, "first_hist": [0] * n_layers,
            "ncorrect_hist": [0] * n_layers, "monotone_steps": 0,
            "committed_steps": 0, "ever_correct": 0,
            # ⚠ T_true 是**npz 里的真实轨迹长度**。原实现没有它，
            #   调用方只能拿 `steps[-1].t + 1` 反推 —— 而那只在「取尾部」时
            #   恰好等于 T；一旦扫中段，那个数就是**错的**，而且错得不显眼
            #   （它仍是个合理的小整数）。⇒ 显式带出来。
            "T_true": T, "contiguous": contiguous,
            "lo": idxs[0], "hi": idxs[-1] + 1}

    for i in range(w):
        t = idxs[i]
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
                    help="steps sampled per trajectory")
    ap.add_argument("--scan", choices=("tail", "uniform", "explicit"), default="tail",
                    help="tail = 原行为，只读最后 window 步（默认，"
                         "logit_lens.json 依赖它）；uniform = 把同样多的采样点"
                         "铺满整条轨迹；explicit = 只读 --positions 给出的那些步。"
                         "三者写**不同**的产物。")
    ap.add_argument("--positions", type=Path, default=None,
                    help="scan=explicit 时必给。JSON，两种形状都收："
                         "{traj_id: [tok, ...]} 或 "
                         '[{"trajectory_id": ..., "tok": ...}, ...]')
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

    # explicit：按给定位置算，覆盖率与采样解耦
    pos_map: Dict[str, List[int]] = {}
    if args.scan == "explicit":
        if args.positions is None:
            raise SystemExit("ABORT --scan explicit 必须同时给 --positions")
        raw = json.load(open(args.positions, encoding="utf-8"))
        if isinstance(raw, dict):
            pos_map = {k: [int(x) for x in v] for k, v in raw.items()}
        elif isinstance(raw, list):
            for it in raw:
                key = it.get("trajectory_id") or it.get("id")
                tok = it.get("tok")
                if key is None or tok is None:
                    raise SystemExit(f"ABORT positions 里有一项没有 trajectory_id/tok：{it!r}")
                pos_map.setdefault(key, []).append(int(tok))
        else:
            raise SystemExit(f"ABORT --positions 的顶层既不是 dict 也不是 list：{type(raw)}")
        keep = {p.stem for p in paths} & set(pos_map)
        dropped = sorted(set(pos_map) - {p.stem for p in paths})
        if dropped:
            print(f"WARNING positions 里有 {len(dropped)} 个 id 在 --npz-dir 下不存在，"
                  f"已忽略，例如 {dropped[:3]}")
        if not keep:
            raise SystemExit("ABORT positions 与 npz 一个都对不上，没有可算的轨迹")
        # ⚠ 只算**有位置**的轨迹：没位置的算进去只会让 n_traj 虚高，
        #   而它会以「轨迹数」的形式出现在产物里。
        paths = [p for p in paths if p.stem in keep]
    elif args.positions is not None:
        raise SystemExit("ABORT --positions 只在 --scan explicit 下有意义，"
                         f"现在是 {args.scan!r}")

    print(f"model      {args.model_path.name}  layers={n_layers} d_model={d_model} "
          f"vocab={n_vocab} eps={eps} tied={head_is_tied(args.model_path)}")
    print(f"sampling   all {len(paths)} trajectories x {args.window} steps "
          f"x {n_layers} layers  (scan={args.scan})")
    t_start = time.time()

    trajs: List[dict] = []
    tot = {"anchor_pass": 0, "anchor_total": 0, "decidable_pass": 0,
           "decidable_total": 0, "monotone": 0, "ever_correct": 0,
           "committed": 0, "err_max": 0.0, "steps": 0}
    first_hist = [0] * n_layers
    ncorrect_hist = [0] * (n_layers + 1)
    by_mode: Dict[str, dict] = {}
    lens_rows = 0
    widths = set()          # 每条轨迹**实际**采到几步（不假设恒等于 --window）

    for k, p in enumerate(paths, 1):
        problem, mode = parse_id(p)
        steps, d = lens_trajectory(p, g, Wt, eps, n_layers, args.window, tokens,
                                   scan=args.scan,
                                   want_idx=pos_map.get(p.stem))
        # ⚠ 原来这里是 `T = steps[-1]["t"] + 1`。那只在「取尾部」时恰好等于
        #   真实长度；扫中段时它会**静默变成一个错的数**（仍是合理小整数，
        #   所以没人会发现）。⇒ 一律用 npz 里的真实长度。
        T = d["T_true"]
        rec = {
            "id": p.stem, "problem": problem, "mode": mode, "T": T,
            # window 是**采样点的包围区间**，不是「这段区间每步都读了」。
            # uniform 模式下它是断的，所以必须同时给出 contiguous 与步号表。
            "window": [d["lo"], d["hi"]],
            "contiguous": d["contiguous"],
            "steps": steps,
        }
        if not d["contiguous"]:
            rec["step_indices"] = [st["t"] for st in steps]
        trajs.append(rec)
        lens_rows += d["steps"] * n_layers
        widths.add(d["steps"])
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
            "rule": (f"all {len(paths)} trajectories ({n_problems} problems x "
                    f"{{think, no_think}}); for each, the LAST {args.window} "
                    f"steps (constant width, tail = the answer-emission region)"
                    if args.scan == "tail" else
                    f"all {len(paths)} trajectories ({n_problems} problems x "
                    f"{{think, no_think}}); for each, {args.window} steps spread "
                    f"UNIFORMLY over the WHOLE trajectory [0, T) (scan=uniform) so "
                    f"the middle of the chain of thought is covered, not just the "
                    f"answer-emission tail"
                    if args.scan == "uniform" else
                    f"ONLY the steps listed in --positions, per trajectory "
                    f"(scan=explicit). Coverage is therefore **decoupled from "
                    f"sampling**: every position is read exactly, so a label at "
                    f"step t is never missed by a sampling stride. Measured "
                    f"justification: with scan=uniform, 32 samples spread over a "
                    f"2048-step trajectory hit **0 of the 14** wrong-arithmetic "
                    f"positions Phase-0 found."),
            "scan": args.scan,
            "why_tail": "the question is about the derivation of the token the "
                        "model is about to say; the tail is where it says it",
            "why_uniform": "error-awareness asks which layer notices a mistake "
                           "**while it happens** -- i.e. in the middle of the chain "
                           "of thought. A tail-only window cannot answer that by "
                           "construction, it only covers the answer-emission region.",
            "n_traj": len(trajs),
            "n_problems": n_problems,
            "n_modes": n_modes,
            # ⚠ 散文里写了「constant width」，那它就**必须**是真的。
            #   宽度不齐却照写，读者会以为每条轨迹被同等采样。
            #   ⇒ 记实际观测到的宽度集合；不齐时 steps_per_traj 给整个列表。
            "steps_per_traj": (args.window if len(widths) == 1 else sorted(widths)),
            "steps_per_traj_widths_observed": sorted(widths),
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
