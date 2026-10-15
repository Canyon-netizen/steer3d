#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量注入点处 marker logit 的**原始量级**（修订 200）。

为什么需要它：
    `p6_resolvability.py` 的 `--logit-mag` 是**必填无默认**的，
    而修订 198 那一次我传的是 `40.0` —— 那个数是从修订 7 的「±0.25」
    **反推**的，不是我在这批上量过的。
    ⚠⚠⚴ 一边说「这个参数不能给默认值」，一边拿没量的数去跑，就是自相矛盾。

    而 bf16 的 ulp = 2^⌊log₂v⌋ × 2^-7，**随量级变**：
        v∈[32,64) ⇒ 0.25      v∈[2,4) ⇒ 0.015625
    ⚗⇒ 量错了桶，判决可能整条反过来（本轮实测 ratio 在 40 桶是 0.490）。

    本脚本只做一件事：在**基线**（不注入）下前向一次，打印
      ① 每个 marker token 的原始 logit 值
      ② 它们的 max（lse 由它主导）
      ③ `lse(base[marker])` 与 `lse(base[' the '])` 的实际值
      ④ 由 ② 推出的 bf16 ulp，以及**用 ③ 反推的下界**
    不注入、不调剂量、不改任何预登记口径 —— **只读**。

用法：
    python3 r200_logit_mag_probe.py --npz-dir gen_b2_max32768/aime \\
        --sidecar-dir gen_b2_max32768/aime --labels r194_label.json \\
        --mode think --limit-traj 5 --gpu-uuid <裸 UUID>

退出码：0 量到 / 2 用法错 / 3 一条都没量到
"""

import argparse
import json
import os
import sys
from math import floor, log2
from pathlib import Path

import numpy as np
import torch

MODEL = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master"
MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
CONTROL_ID = 279          # ' the '
LAYER = 20


def bf16_ulp(mag):
    if mag <= 0:
        raise ValueError("量级必须为正，收到 %r" % (mag,))
    return 2.0 ** (floor(log2(mag)) - 7)


def _ulp_of_dtype(dt, mag):
    """按张量的**实际 dtype** 求 ulp，而不是假设 bf16。
    ⚠ 半精度尾数 10 位 ⇒ ulp = 2^⌊log₂v⌋ × 2^-10；fp32 是 2^-23。"""
    if mag <= 0:
        return float("nan")
    exp = {"float32": 23, "float16": 10, "bfloat16": 7}
    key = str(dt).replace("torch.", "")
    n = exp.get(key)
    if n is None:
        return float("nan")
    return 2.0 ** (floor(log2(mag)) - n)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--mode", default="think", choices=["think", "no_think"])
    ap.add_argument("--limit-traj", type=int, default=5)
    ap.add_argument("--gpu-uuid", default=None,
                    help="**裸 UUID**（不带 GPU- 前缀）")
    a = ap.parse_args()

    # ⚠ 与 r6_rerun.py 同一个坑：前缀由本脚本自己拼
    if a.gpu_uuid:
        os.environ["CUDA_VISIBLE_DEVICES"] = ("GPU-" + a.gpu_uuid
                                              if not a.gpu_uuid.startswith("GPU-")
                                              else a.gpu_uuid)

    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda:0").eval()

    d = json.load(open(a.labels, encoding="utf-8"))
    rows = d["rows"] if isinstance(d, dict) and "rows" in d else d
    want = [r["traj"] for r in rows
            if r["traj"].endswith("__" + a.mode)]
    want = sorted(want)[: a.limit_traj]
    if not want:
        print("[错误] 标注里没有 %s 臂的轨迹" % a.mode)
        return 2

    mk = torch.tensor(MARKER_IDS, device="cuda:0")
    ctl = torch.tensor([CONTROL_ID], device="cuda:0")

    def fwd(ids):
        with torch.no_grad():
            o = model(input_ids=ids).logits[0, -1]
        return o.float()

    # ⚠ 第一版这里在嵌套函数里写了 `self.hnorm` —— `main()` 里没有 self，
    # ⚠ 一调用就 NameError ⇒ 探针整轮白跑。改用外层可变容器。
    grabbed = {}

    def fwd2(ids):
        """同时抓 norm 之后的隐状态（lm_head 的输入）—— 量化可能发生在那里，
        而不是在 logits 上。**必须一起看，否则会把 ulp 归错地方。**"""
        grabbed.clear()

        def hook(_m, _i, out):
            grabbed["h"] = out[0] if isinstance(out, tuple) else out

        hk = model.model.norm.register_forward_hook(hook)
        try:
            with torch.no_grad():
                o = model(input_ids=ids)
        finally:
            hk.remove()
        grabbed["lg"] = o.logits[0, -1]
        return grabbed["lg"]

    print("=== 基线（不注入）marker logit 原始量级 ===")
    print("  %-34s %-10s %-10s %-12s %-10s" %
          ("轨迹@位置", "max(lg)", "lse(mark)", "lse(' the ')", "ulp(max)"))

    mags, lses, dtypes = [], [], []
    for tid in want:
        zp = Path(a.npz_dir) / (tid + ".npz")
        cp = Path(a.sidecar_dir) / (tid + ".json")
        if not (zp.exists() and cp.exists()):
            print("  [跳过] %s 缺 npz 或 sidecar" % tid)
            continue
        z = np.load(zp)
        gen = z["token_ids"].tolist()
        z.close()
        cti = json.load(open(cp, encoding="utf-8"))
        P = (cti.get("extra") or {}).get("prompt_tokens") or len(
            tok(cti["chat_template_input"], return_tensors="pt",
                add_special_tokens=False).input_ids[0].tolist())
        # 取三个位置（十等分位），与 P5 的抽样口径一致
        n = len(gen)
        for t in sorted({max(1, n // 10), max(1, n // 2), max(1, 9 * n // 10)}):
            if t >= n:
                continue
            ids = torch.tensor([tok(cti["chat_template_input"],
                                    return_tensors="pt",
                                    add_special_tokens=False).input_ids[0].tolist()
                                + gen][: P + t],
                               dtype=torch.long, device="cuda:0")
            lg = fwd2(ids)
            v = lg[mk]
            mx = float(v.max())
            sm = mx + float(torch.log(torch.exp(v.float() - mx).sum()))
            sc = float(torch.logsumexp(lg[ctl].float(), dim=0))
            mags.append(mx)
            lses.append(sm)
            hn = grabbed["h"]
            hmax = float(hn.abs().max())
            if not dtypes:
                print("  ⚠ dtype：logits=%s   norm 输出=%s   lm_head.weight=%s"
                      % (lg.dtype, hn.dtype, model.lm_head.weight.dtype))
                dtypes.append((str(lg.dtype), str(hn.dtype)))
                print("  ⚠ 由 logits 的**实际 dtype** 推出的 ulp = %.8f"
                      % _ulp_of_dtype(lg.dtype, mx))
                print("  ⚠ 由 norm 输出的实际量级(%.3f) 推出的 ulp = %.8f"
                      % (hmax, bf16_ulp(hmax)))
            print("  %-34s %-10.3f %-10.3f %-12.3f %-10.6f  |h|max=%-8.2f h_ulp=%.6f"
                  % ("%s@t=%d" % (tid[:24], t), mx, sm, sc,
                     bf16_ulp(mx), hmax, bf16_ulp(hmax)))

    if not mags:
        print("[错误] 一条都没量到")
        return 3

    mags = np.array(mags)
    lses = np.array(lses)
    ulp = bf16_ulp(float(mags.max()))
    print()
    print("  max(lg)  范围  [%.3f, %.3f]   中位 %.3f"
          % (mags.min(), mags.max(), float(np.median(mags))))
    print("  lse(mark) 范围 [%.3f, %.3f]   中位 %.3f"
          % (lses.min(), lses.max(), float(np.median(lses))))
    print("  ⇒ 由 max(lg) 推出的 bf16 ulp = %.6f" % ulp)
    print()
    print("  ⚠ 这是**读数用闸的参数**，不是一个结论。三点必须一起记：")
    print("     ① 它量的是**基线**下的 logit，不是注入后的差值本身；")
    print("        差值的分辨率受**两侧被相减的值**的 ulp 支配，故这里取上界口径。")
    print("     ② 不同位置/轨迹的 max 跨了 %.3f–%.3f，⚗ 若它们跨 2 的幂边界，"
          % (mags.min(), mags.max()))
    print("        ulp 会分桶不同 ⇒ `--logit-mag` 该取哪个桶**必须说明**，不许含糊。")
    print("     ③ 本轮**不改**任何预登记口径：不注入、不调剂量、不换注入层。")
    print()
    print("RESULT r200_logit_mag  OK  n=%d  max_lg=[%.3f,%.3f]  ulp=%.6f"
          % (len(mags), mags.min(), mags.max(), ulp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
