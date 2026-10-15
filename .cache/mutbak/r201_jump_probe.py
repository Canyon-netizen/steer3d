#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定点测量：Δlogit 的**实际跳变步长**（修订 201）。

要解决的问题（修订 200 §200.2 / §200.5）：
    三条线索互不相等 ——
        logit 量级 ~2.9      ⇒ bf16_ulp 0.015625
        norm 输出 144–150   ⇒ bf16_ulp 1.0
        34 个实测读数 gcd   ⇒ **0.125**（唯一直接实测的那条）
    ⇒ 读数路径上**还有一步没定位到的取整**。

⚗⚠ 本脚本**不再去推量级**，而是**直接扫**：同一前向下把注入 α 从负扫到正，
⚗⚠ 逐点记录 Δlogit，看它实际是**连续变**还是**跳变**、跳多少。
⚗⚠ 若跳变步长是 0.125 ⇒ 那一步取整就在这条链路上，且**不必再问它来自哪个张量**。

⚠ 只读性质：**只读 w 与模型**，不改剂量阶梯、不换注入层、不动 pos_offset。
⚠ α 的扫描范围是**诊断用的极小步进**，与 P3 的 `{0.5, 1.0}` 无关 ——
⚠ 它只用来定位量化地板，**不产生任何 P6 读数**。

用法：
    python3 r201_jump_probe.py --npz-dir gen_b2_max32768/aime \\
        --sidecar-dir gen_b2_max32768/aime --labels r194_label.json \\
        --w /tmp/w_p2a.npy --n-steps 400 --gpu-uuid <裸 UUID>

退出码：0 量到 / 2 用法错 / 3 一条都没量到
"""

import argparse
import json
import os
import sys
from fractions import Fraction
from math import gcd
from pathlib import Path

import numpy as np
import torch

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279          # ' the '
LAYER = 20


def lse_t(v):
    m = float(v.max())
    return m + float(torch.log(torch.exp(v.float() - m).sum()))


def gcd_step(vals):
    """全部读数的公共步长（用 1/1000 精度整数化后取 gcd）。"""
    g = 0
    for v in vals:
        g = gcd(g, abs(int(round(v * 1000))))
    return g / 1000.0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--w", required=True, help="w 的 .npy（诊断只读它）")
    ap.add_argument("--tid", default=None,
                    help="指定轨迹；不给就取第一条 think")
    ap.add_argument("--pos-frac", type=float, default=0.5,
                    help="注入位置取轨迹的百分之几处（默认 0.5，与 P9 口径一致）")
    ap.add_argument("--n-steps", type=int, default=400)
    ap.add_argument("--alpha-max", type=float, default=60.0,
                    help="α 扫描半宽。w·U≈0.043 ⇒ α=60 时 Δ≈±2.6，"
                         "足以看出跳变结构")
    ap.add_argument("--gpu-uuid", default=None, help="**裸 UUID**（不带 GPU- 前缀）")
    a = ap.parse_args()

    if a.gpu_uuid:
        os.environ["CUDA_VISIBLE_DEVICES"] = (
            "GPU-" + a.gpu_uuid if not a.gpu_uuid.startswith("GPU-")
            else a.gpu_uuid)

    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16).to("cuda:0").eval()

    W = np.load(a.w).astype(np.float32)
    W = W / np.linalg.norm(W)

    d = json.load(open(a.labels, encoding="utf-8"))
    rows = d["rows"] if isinstance(d, dict) and "rows" in d else d
    cand = sorted(r["traj"] for r in rows if r["traj"].endswith("__think"))
    if not cand:
        print("[错误] 标注里没有 think 轨迹")
        return 2
    tid = a.tid or cand[0]

    z = np.load(Path(a.npz_dir) / (tid + ".npz"))
    gen = z["token_ids"].tolist()
    z.close()
    cti = json.load(open(Path(a.sidecar_dir) / (tid + ".json"), encoding="utf-8"))
    pid = tok(cti["chat_template_input"], return_tensors="pt",
              add_special_tokens=False).input_ids[0].tolist()
    P = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)
    n = len(gen)
    t = max(1, int(n * a.pos_frac))
    ids = torch.tensor([(pid + gen)[: P + t]],
                       dtype=torch.long, device="cuda:0")
    inj = ids.shape[1] - 1

    mk = torch.tensor(MARKER_IDS, device="cuda:0")
    ctl = torch.tensor([CONTROL_ID], device="cuda:0")

    def forward(vec, alpha):
        blk = model.model.layers[LAYER]

        def pre(mod, inp):
            if alpha == 0.0:
                return None
            h = inp[0]
            v = torch.as_tensor(vec, dtype=h.dtype, device=h.device)
            h = h.clone()
            h[:, inj, :] = h[:, inj, :] + alpha * v
            return (h,) + inp[1:]

        hk = blk.register_forward_pre_hook(pre)
        try:
            with torch.no_grad():
                o = model(input_ids=ids, use_cache=False, return_dict=True)
        finally:
            hk.remove()
        return o.logits[0, -1].float()

    base = forward(W, 0.0)
    b_mark = lse_t(base[mk])
    b_ctl = lse_t(base[ctl])
    print("=== 定点测量：Δlogit 随注入的跳变结构 ===")
    print("  轨迹 %s   位置 t=%d（P=%d, n_gen=%d）" % (tid, t, P, n))
    print("  基线 lse(marker)=%.6f   lse(' the ')=%.6f" % (b_mark, b_ctl))
    print("  |w|=1   扫描 α ∈ [−%.1f, +%.1f]，%d 点"
          % (a.alpha_max, a.alpha_max, a.n_steps))

    alphas = np.linspace(-a.alpha_max, a.alpha_max, a.n_steps)
    recs = []
    for al in alphas:
        lg = forward(W, float(al))
        recs.append((float(al), lse_t(lg[mk]) - b_mark, lse_t(lg[ctl]) - b_ctl))
        if len(recs) % 50 == 0:
            print("    ... %d/%d" % (len(recs), len(alphas)))

    dm = np.array([r[1] for r in recs])
    dc = np.array([r[2] for r in recs])
    nz = dm[dm != 0.0]
    print()
    print("  Δ(marker) 范围 [%.4f, %.4f]   非零点数 %d/%d"
          % (dm.min(), dm.max(), len(nz), len(dm)))
    print("  Δ(' the ') 范围 [%.4f, %.4f]" % (dc.min(), dc.max()))

    # ---- 核心：跳变步长 ----
    diffs = np.diff(dm)
    diffs = diffs[diffs != 0.0]
    if diffs.size:
        ad = np.abs(diffs)
        q_min = float(ad.min())
        # ⚠⚠ 用**最小非零跳变**，不用 gcd。
        # ⚠⚠ gcd_step 走 1/1000 精度，分辨不出一级跳变（实测会把
        # ⚠⚠ [0.0156, 0.0313] 判成 0.001 —— 那是精度下限的产物，不是步长）。
        # ⚠⚠ 「读数能分辨多细」的正确统计量就是**最小非零跳变**。
        print()
        print("  ★ 最小非零跳变 = %.6f" % q_min)
        print("    跳变次数 %d" % len(diffs))
        uniq = sorted({round(float(x), 6) for x in ad})
        print("    出现的跳变幅度（前 12 个）: %s" % uniq[:12])
        print("    ⚗ 若最小跳变明显大于 0 ⇒ Δlogit 是**跳变**而非连续 ⇒ 存在取整步骤")
        print()
        for name, cand_q in (("logit 量级推导 0.015625", 0.015625),
                             ("norm 量级推导 1.0", 1.0),
                             ("修订 200 实测 gcd 0.125", 0.125)):
            print("    最小跳变 / %-28s = %.3f"
                  % (name, q_min / cand_q if cand_q else float("nan")))
    else:
        print("  ⚠ 全程没有非零跳变 —— 扫描范围可能太小，或注入没生效")

    # 线性拟合斜率 vs 预测 α·(w·U)
    slope = float(np.polyfit(alphas, dm, 1)[0]) if len(set(dm.tolist())) > 1 else float("nan")
    print()
    print("  实测斜率 d(Δ)/dα = %.6f" % slope)
    print("  ⚠ 对照：同位置下 w·U[marker] 的实测值需另跑 w_unembed_align.py 取，")
    print("    本脚本**不重算**它（避免两处口径各算各的）。")

    np.savetxt("/tmp/r201_scan.tsv",
               np.column_stack([alphas, dm, dc]), delimiter="\t",
               header="alpha\td_marker\td_control", comments="")
    print("  扫描表写到 /tmp/r201_scan.tsv")
    q_res = ("%.6f" % q_min) if diffs.size else "n/a"
    print("RESULT r201_jump_probe  OK  n=%d  n_jump=%d  min_jump=%s"
          % (len(dm), len(diffs) if diffs.size else 0, q_res))
    print("  ⚠⚠ **min_jump 不是地板**：它只说明读数在这条轨迹这个位置上是"
          "连续/细粒度的。")
    print("     ⚠ 若残差 std ≫ 信号斜率，说明它是**噪声受限**而不是分辨率受限，")
    print("     ⚗ 两者是**不同的失效模式**，判据完全不同（见修订 201）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
