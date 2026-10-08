#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量前向等价性：差 2.6e-03 到底是**逻辑错**还是 **fp32 累加顺序噪声**？

## 触发

`causal_inject.py` 把每个案例的 29 个注入变体压成**一次**前向
（否则 121 个位置要跑十几小时）。`--check-unbatched` 报
「批量 vs 逐个前向：最大差 **2.556e-03**」。

2.6e-03 相对于本实验的效应量（marker Δ 最高 +0.42）只有 0.6%，
但**相对于我们同时要报的「Δ标记词本身」（~0.002）是同一量级** ——
也就是说它决定了哪些读数能被判成「零」。

## 怎么分辨

同一个变体集合，用三种批大小各跑一遍：

    B=1（逐个）   B=2（分块）   B=6（整批）

- 若 **B=1 与 B=2 也差 ~1e-3**、且 **B=1 与 B=6 也差 ~1e-3**，
  三者两两都在同一量级 ⇒ 差异与「批大小」无关，是 fp32 累加顺序
  造成的数值噪声 ⇒ hook 逻辑没问题，但**必须报噪声底**。
- 若 **B=1 与 B=2 几乎相同、只有 B=6 差很多** ⇒ 逻辑错，
  批量路径不可用。

## 顺带量出噪声底

噪声底 = B=1 三次重复之间的最大差（同输入同代码，应当逐位相同 ⇒ 0），
以及 B=1 与 B=2 的差。所有小于这个数的读数一律标「不可分辨」。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/mutbak/batch_equiv.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
import probe_hinge_layers as P   # noqa: E402
import causal_inject as CI       # noqa: E402

NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
MODEL = os.path.join(ROOT, "datasets", "models", "Qwen3-1.7B")
LAYER = 20
SEED = 20261007
OUT = os.path.join(ROOT, ".cache", "mutbak", "batch_equiv.json")


def main() -> int:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}
    W, _ = CI.train_direction(pos, tmap, SEED)
    gap = CI.class_gap(pos, tmap, SEED)
    rng = np.random.default_rng(SEED + 1)
    R = rng.normal(size=W.shape).astype(np.float32); R /= np.linalg.norm(R)

    tk = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32)
    model.eval()
    blk = model.model.layers[LAYER]
    mid, cid = CI.load_marker_ids(tk)
    U = model.lm_head.weight.detach().float().numpy()
    ref_tok = mid[0]

    # 6 个有代表性的变体：含零、含两个基准、含新梯两端
    vecs = [np.zeros_like(W), 0.5 * W, 2.0 * gap * W, -1.0 * gap * W,
            gap * (U[ref_tok] / np.linalg.norm(U[ref_tok])),
            gap * R]
    keys = ["w|abs0.0", "w|abs0.5", "w|rel+2.0", "w|rel-1.0", "Uref|rel+1.0",
            "rand|rel+1.0"]

    cases = CI.build_cases(pos, tmap)
    by = {}
    for c in cases:
        by.setdefault(c["traj"], []).append(c)
    tids = sorted(by)
    sel = [by[t][(j * 5) % len(by[t])] for j, t in enumerate(tids)][:2]

    def run(pre1, inj, group):
        """group 是一批向量的下标；按该批大小一次前向。"""
        V = [vecs[i] for i in group]
        B = len(V)
        L = pre1.shape[1]
        delta = torch.as_tensor(np.stack(V), dtype=torch.float32)
        pos_idx = torch.full((B,), inj, dtype=torch.long)
        bidx = torch.arange(B)

        def hook(mod, inp):
            h = inp[0].clone()
            h[bidx, pos_idx, :] = h[bidx, pos_idx, :] + delta
            return (h,) + inp[1:]

        hd = blk.register_forward_pre_hook(hook)
        try:
            with torch.no_grad():
                lg = model(pre1.expand(B, L)).logits[:, -1, :]
        finally:
            hd.remove()
        lp = torch.log_softmax(lg, dim=-1)
        mt = torch.as_tensor(mid)
        return np.stack([float(torch.logsumexp(lp[b][mt], dim=0)) for b in range(B)])

    rows = []
    for c in sel:
        z = np.load(os.path.join(NPZ_DIR, c["traj"] + ".npz"))
        full = np.concatenate([z["prompt_token_ids"].astype(np.int64),
                               z["token_ids"].astype(np.int64)])
        n_pre = len(z["prompt_token_ids"])
        if c["t"] >= len(z["token_ids"]):
            continue
        inj = n_pre + c["t"] - 1
        pre1 = torch.as_tensor(full[:inj + 1])[None, :]

        def by_b(B):
            out = []
            for s in range(0, len(vecs), B):
                out.append(run(pre1, inj, list(range(s, min(s + B, len(vecs))))))
            return np.concatenate(out)

        b1, b1b, b2, b6 = by_b(1), by_b(1), by_b(2), by_b(6)
        rows.append({
            "traj": c["traj"], "t": c["t"], "L": int(pre1.shape[1]),
            "v_b1": b1.tolist(),
            "d_b1_repeat": float(np.abs(b1 - b1b).max()),
            "d_b1_b2": float(np.abs(b1 - b2).max()),
            "d_b1_b6": float(np.abs(b1 - b6).max()),
            "d_b2_b6": float(np.abs(b2 - b6).max()),
        })
        r = rows[-1]
        print(f"  {r['traj'][:34]} L={r['L']}")
        print(f"    B=1 自身重复     {r['d_b1_repeat']:.3e}  "
              f"{'（确定性 ✅）' if r['d_b1_repeat'] == 0 else '❌ 非确定'}")
        print(f"    B=1 vs B=2       {r['d_b1_b2']:.3e}")
        print(f"    B=1 vs B=6       {r['d_b1_b6']:.3e}")
        print(f"    B=2 vs B=6       {r['d_b2_b6']:.3e}")

    # 判决
    d12 = max(r["d_b1_b2"] for r in rows)
    d16 = max(r["d_b1_b6"] for r in rows)
    d26 = max(r["d_b2_b6"] for r in rows)
    det = all(r["d_b1_repeat"] == 0.0 for r in rows)
    print(f"\n  跨案例最大： B1~B2 {d12:.3e}   B1~B6 {d16:.3e}   B2~B6 {d26:.3e}")
    print(f"  同输入重复运行逐位相同：{'是 ✅' if det else '否 ❌'}")

    logic_ok = d12 <= 1.05 * max(d16, 1e-12) or abs(d12 - d16) <= 0.2 * max(d12, d16)
    if det and logic_ok:
        verdict = ("数值噪声（fp32 累加顺序），不是逻辑错。"
                   "批量路径可用，但**所有小于该噪声底的读数只能标「不可分辨」**。")
    elif not det:
        verdict = "同输入重复运行结果不一致 ⇒ 非确定性问题，批量路径不可信。"
    else:
        verdict = ("B=1~B2 明显小于 B=1~B6 ⇒ 与批大小**相关**，"
                   "指向逻辑错（hook 的按元素加法在某处不对）。")
    print(f"\n  ⇒ {verdict}")

    floor = max(d12, d16, d26)
    print(f"  ⇒ 噪声底 {floor:.2e} nats。"
          f"本实验最小的效应量 +0.0409 是它的 {0.0409/floor:.1f} 倍（可分辨）；"
          f"而「Δ标记词本身」的读数 ~0.002 是它的 {0.002/floor:.1f} 倍 ⇒ **不可分辨**。")

    json.dump({"rows": rows, "noise_floor": floor, "deterministic": bool(det),
               "verdict": verdict},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())