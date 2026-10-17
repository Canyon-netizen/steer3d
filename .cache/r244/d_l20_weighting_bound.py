#!/usr/bin/env python
"""How much does the weighted-vs-unweighted mismatch matter? (revision 244.12)

The problem, precisely:
  d_L20 is computed as  (alpha/atten) * mean_j( w.U[j] )        <- unweighted
  but the instrument P9 reads  lse(lg[MARKER_IDS]), whose first-order
  effect is  (alpha/atten) * sum_j p_j * (w.U[j])               <- p-weighted
  (the ledger states the weighted form itself, at R6_RERUN_PREREG.md:942)

They coincide only when every p_j is 1/7.  They are not.

Quantify WITHOUT a forward pass: the weighted sum of the dots is bounded by
min(dots) <= sum_j p_j*dot_j <= max(dots) for any probability vector p.
So the full range of possible d_L20 values is computable from the dots alone,
and if that range straddles zero then the mean-based number does not even
determine the SIGN of the predicted effect.

This is a bound, not a measurement.  It says: here is the interval inside which
the correct answer lies.  It does not say where inside it the truth is.

Exit: 0 printed; 2 precondition failure.
"""
import json
import os
import sys

import numpy as np

MODEL_DIR = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
W_NPY = "/tmp/w_p2a.npy"
W_META = "/tmp/w_p2a.npy.json"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279
ATTENUATION = 40.0


def main():
    if not os.path.isfile(W_NPY):
        print("PRECOND_FAIL: %s 不存在" % W_NPY)
        return 2
    from safetensors import safe_open

    w = np.load(W_NPY).astype(np.float64)
    gap = 1.0
    if os.path.isfile(W_META):
        gap = float(json.load(open(W_META, encoding="utf-8"))["class_gap"])
    scale = gap / ATTENUATION

    shard = None
    idx = os.path.join(MODEL_DIR, "model.safetensors.index.json")
    if os.path.isfile(idx):
        wm = json.load(open(idx, encoding="utf-8")).get("weight_map", {})
        shard = os.path.join(MODEL_DIR, wm.get(
            "lm_head.weight", wm.get("model.embed_tokens.weight", "")))
    if not shard or not os.path.isfile(shard):
        shard = os.path.join(MODEL_DIR, "model.safetensors")
    if not os.path.isfile(shard):
        print("PRECOND_FAIL: 找不到 safetensors")
        return 2

    with safe_open(shard, framework="pt") as f:
        keys = list(f.keys())
        key = "lm_head.weight" if "lm_head.weight" in keys else \
            "model.embed_tokens.weight"
        U = f.get_tensor(key).double().numpy()
    dots = U[MARKER_IDS] @ w
    del U

    mean = float(dots.mean())
    lo, hi = float(dots.min()), float(dots.max())
    pos = int((dots > 0).sum())

    print("alpha/atten = class_gap/40 = %.6f/40 = %.6f" % (gap, scale))
    print("dots (7 markers) = " + ", ".join("%+.6f" % x for x in dots))
    print("mean = %+.6f   min = %+.6f   max = %+.6f   为正 %d/7"
          % (mean, lo, hi, pos))
    print("")
    print("d_L20 若用算术均值（当前做法）：%+.4f" % (scale * mean))
    print("d_L20 若用概率加权（仪器的泛函）：")
    print("   下界（全权重压在最负的 marker）  %+.4f" % (scale * lo))
    print("   上界（全权重压在最正的 marker）  %+.4f" % (scale * hi))
    print("")
    if lo < 0 < hi:
        print("⚠⚠⚠ 这个区间**跨过 0** => 均值版的 d_L20 连**符号**都定不下来。")
        print("    符号由「高概率的 marker 恰好是哪个」决定，而不是由 7 个数的均值决定。")
    else:
        print("⚠ 区间不跨 0，但宽度相对均值版是 %.1f 倍。"
              % ((hi - lo) / mean if mean else float("nan")))
    print("")
    print("⚠ 这是**区间**，不是测量。要定出具体值需要 marker 的概率 p_j，")
    print("  那要一次前向传播 ⛔ 本轮 GPU 被 274 格占着，量不了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
