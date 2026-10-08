#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""位置/层号对齐闸门：**任何拿 npz 隐状态去驱动本地模型的脚本，都必须先过这里。**

## 为什么要有这个文件

`causal_inject.py` 第一版用
`tk(prompt + generated_text)` 重新分词再切 `[:t]`，
把生成段坐标系当成了全序列坐标系，**注入位置整个错开**，
而 6 案例读数照样照常打印、照样单调 —— **不报任何错**。

⇒ 「坐标不错」是**必须主动证明**的性质，不能靠读代码时想当然。
   本文件把三件必须同时成立的事写成硬断言。

## 三项断言（缺一不可）

| 断言 | 判据 | 实测（aime__1983…think） |
|---|---|---|
| **A1 权重同一** | 本地模型在生成段每一位的 top-1 与 npz `topk_indices[g,0]` 一致 | 一致率 **0.9912** |
| **A2 行映射** | npz 第 g 行 == 全序列第 `P+g−1` 位 | 偏移扫描 off=−1 最优 |
| **A3 末端同一** | npz `last_hidden[g]` == HF `hidden_states[28]` 同位 | 余弦 **0.99993**，相对误差 **0.0119** |

其中 P = len(prompt_token_ids)。
A3 是最强的判据：末层能对上，说明**输入序列、偏移、权重三者同时正确**。

## 一个必须记住的坑

A2 的含义容易被读反：
**npz 第 g 行不是「第 g 个 token 自己的隐状态」，而是「预测出第 g 个 token 的那个位置」的隐状态。**
所以 `hinge.json` 里标记词下标 `t`，对应的 npz 行是 `t`，
而它在全序列里的位置是 `P+t−1`，**即标记词前一个 token 的位置**。
探针必须读 `h(t−1)` 这一点，在本文件里表现为「行 t = 前一位」。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/mutbak/causal_align.py [--traj ID]

退出码 0 = 三项全过；非 0 = 别跑注入实验。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
MODEL = os.path.join(ROOT, "datasets", "models", "Qwen3-1.7B")
MIN_TOP1 = 0.98        # A1
MAX_LAST_COS = 0.999   # A3（余弦）
MAX_LAST_REL = 0.05    # A3（相对误差）


def check(tid: str, verbose: bool = True) -> dict:
    import torch
    from transformers import AutoModelForCausalLM

    z = np.load(os.path.join(NPZ_DIR, tid + ".npz"))
    pids = z["prompt_token_ids"].astype(np.int64)
    gids = z["token_ids"].astype(np.int64)
    P = len(pids)
    full = np.concatenate([pids, gids])

    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32)
    model.eval()
    with torch.no_grad():
        out = model(torch.as_tensor(full)[None, :], output_hidden_states=True)
    lg = out.logits[0].float().numpy()
    hs = out.hidden_states

    # ---- A1 权重同一：生成段 top-1 ----
    G = len(gids)
    mine = lg[P - 1:P - 1 + G].argmax(-1)
    npz_top1 = z["topk_indices"][:, 0].astype(np.int64)[:G]
    rate = float((mine == npz_top1).mean())

    # ---- A2 行映射：扫偏移，取余弦最高 ----
    g = min(400, G - 1)
    cands = []
    for off in (-3, -2, -1, 0, 1, 2):
        f = g + P + off
        ref = hs[20][0, f].float().numpy().astype(np.float64)
        got = z["hidden_states"][g, 20].astype(np.float64)
        cands.append((off, float(got @ ref / (np.linalg.norm(got) * np.linalg.norm(ref)))))
    best_off, best_cos = max(cands, key=lambda kv: kv[1])

    # ---- A3 末端同一 ----
    f = g + P - 1
    ref = hs[28][0, f].float().numpy().astype(np.float64)
    got = z["last_hidden"][g].astype(np.float64)
    cos = float(got @ ref / (np.linalg.norm(got) * np.linalg.norm(ref)))
    rel = float(np.linalg.norm(got - ref) / np.linalg.norm(ref))

    r = {"traj": tid, "n_prompt": P, "n_gen": G,
         "A1_top1_rate": rate, "A1_ok": rate >= MIN_TOP1,
         "A2_scan": {str(o): c for o, c in cands},
         "A2_best_off": best_off, "A2_best_cos": best_cos, "A2_ok": best_off == -1,
         "A3_cos": cos, "A3_rel": rel,
         "A3_ok": bool(cos >= MAX_LAST_COS and rel <= MAX_LAST_REL)}
    r["ok"] = bool(r["A1_ok"] and r["A2_ok"] and r["A3_ok"])

    if verbose:
        print(f"  轨迹 {tid}  prompt {P} + gen {G}")
        print(f"    A1 权重同一：top-1 一致率 {rate:.4f} "
              f"{'✅' if r['A1_ok'] else '❌ < ' + str(MIN_TOP1)}")
        print(f"    A2 行映射  ：偏移 " +
              " ".join(f"{o:+d}:{c:.3f}" for o, c in cands) +
              f"  ⇒ 最佳 off={best_off:+d} {'✅' if r['A2_ok'] else '❌'}")
        print(f"    A3 末端同一：余弦 {cos:.5f} 相对误差 {rel:.5f} "
              f"{'✅' if r['A3_ok'] else '❌'}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, ".cache", "mutbak",
                                                  "causal_align.json"))
    a = ap.parse_args()
    tids = ([a.traj] if a.traj else
            sorted(f[:-4] for f in os.listdir(NPZ_DIR) if f.endswith(".npz")))
    # 默认只查一条：模型载入 ~3 s，28 条要 1.5 分钟
    tids = tids[:1] if not a.traj else tids
    print("=== 位置/层号对齐闸门 ===")
    rows = [check(t) for t in tids]
    allok = all(r["ok"] for r in rows)
    print(f"\n  ⇒ {'三项全过，可以跑注入实验' if allok else '**未通过，禁止跑注入实验**'}")
    json.dump({"rows": rows, "ok": allok},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {a.out}")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
