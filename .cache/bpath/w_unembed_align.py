"""决定性测量：w 与 marker token 的 unembedding 行是否同向。

## 为什么测这个

P9 装置符号基准在三种训练口径下都 FAIL：
`H[t]`（marker 自身）class_gap ~300 / `H[t-1]`（预测位）172 / 我那次错误修复 9.3。
剂量扫描又显示 no_think 正控 5/5 剂量步全单调升 ⇒ 装置与剂量都没问题。

那么剩下的唯一可能机制是：**w 指向的方向，抬不起 marker token 的 logit**。
注入抬高某 token logit 的必要条件近似是 `w · U[token] > 0`
（`U` = unembedding 矩阵，logit = h·U）。这可以直接算。

- `w·U_marker > 0` 却仍不生效 ⇒ 机制在别处（非线性/饱和/层选错）
- `w·U_marker <= 0` ⇒ **探针方向与该 token 的解码方向反向**，
  这是关于「位置判别方向 ≠ token 方向」的**定量证据**

## 判据（取数前写死）

  U1 报出 `w·U[marker]` 与 `w·U[control]`（control = `' the '`）的对照
  U2 `w·U[marker] > 0` 才叫「方向对得上 marker」
  U3 同一批 token 的**平均** logit 也要报，防止只看 7 个 id 撞运气
  U4 随机方向对照：随机单位向量与 U 的点积量级基线
  U5 **不改任何设计**，本脚本只测量，不判决通过与否
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import torch
from transformers import AutoModelForCausalLM

MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279          # `' the '`，r6_rerun.py 里的对照 token


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--w", nargs="+", default=None,
                    help="一个或多个 .npy（名称=路径 的 json 也接受）")
    ap.add_argument("--w-json", default=None,
                    help="{名称: 路径} 形式的 json，便于标注每个 w 的来源")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gpu-uuid", default=None)
    a = ap.parse_args()
    # --w 与 --w-json 至少给一个。原先 --w 是 required=True，
    # 于是走 --w-json 时也必须编一个用不上的 --w，纯属恶心人。
    if not a.w and not a.w_json:
        ap.error("必须给 --w 或 --w-json 之一")
    # CVD 必须在 import torch 之前设——本文件顶部已 import torch，
    # 所以这里只提示：真要指定卡，请在调用前 export CUDA_VISIBLE_DEVICES。
    if a.gpu_uuid:
        print(f"⚠ 本脚本已 import torch，--gpu-uuid 可能不生效；请改用外部 export。")

    model = AutoModelForCausalLM.from_pretrained(
        a.model, dtype=torch.bfloat16)
    # unembedding 行（Qwen3 是 tied 或独立 lm_head，取 lm_head 最保险）
    U = (model.lm_head.weight if hasattr(model, "lm_head")
         else model.get_output_embeddings().weight).detach().float().cpu().numpy()
    print(f"unembedding 形状 {U.shape}")

    rng = np.random.default_rng(42)
    R = rng.standard_normal(U.shape[1]).astype(np.float32)
    R /= np.linalg.norm(R)
    base = float(np.abs(R @ U.T).mean())
    print(f"U4 随机单位方向与全部 logit 的平均 |点积| 基线 = {base:.6f}")

    ws = {}
    if a.w_json:
        ws = json.load(open(a.w_json))
    else:
        for p in a.w:
            ws[p] = p

    out = {"random_baseline_mean_abs_dot": base, "rows": {}}
    for name, path in ws.items():
        try:
            w = np.load(path).astype(np.float32)
        except Exception as e:
            print(f"  跳过 {name}: {e}")
            continue
        n = float(np.linalg.norm(w))
        w = w / (n + 1e-12)
        dm = w @ U[MARKER_IDS].T          # (7,)
        dc = float(w @ U[CONTROL_ID])
        dall = w @ U.T                     # 全词表
        r = {
            "w_norm_raw": n,
            "dot_marker_mean": float(dm.mean()),
            "dot_marker_min": float(dm.min()),
            "dot_marker_all": [round(float(x), 5) for x in dm],
            "n_marker_positive": int((dm > 0).sum()),
            "dot_control": dc,
            "dot_vocab_mean": float(dall.mean()),
            "dot_vocab_p99": float(np.percentile(dall, 99)),
            "over_random_x": float(np.mean(np.abs(dall)) / base),
        }
        r["aligned"] = bool(r["n_marker_positive"] == len(MARKER_IDS))
        out["rows"][name] = r
        print(f"\n  [{name}]  |w|={n:.4f}")
        print(f"    w·U[marker]  逐 id {r['dot_marker_all']}")
        print(f"      为正的 marker 数 {r['n_marker_positive']}/{len(MARKER_IDS)}"
              f"   均值 {r['dot_marker_mean']:+.6f}")
        print(f"    w·U[control ' the '] = {r['dot_control']:+.6f}")
        print(f"    全词表 w·U  均值 {r['dot_vocab_mean']:+.6f}"
              f"  p99 {r['dot_vocab_p99']:+.6f}")
        print(f"    相对随机基线 {r['over_random_x']:.3f}×")
        print(f"    U2 方向与 marker 同向? {r['aligned']}")

    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print("\n写出", a.out, "（U5 本脚本只测量，不判决通过与否）")


if __name__ == "__main__":
    main()