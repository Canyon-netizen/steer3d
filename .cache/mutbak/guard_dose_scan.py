#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""装置符号基准的**剂量依赖性**：为什么守卫必须放在小剂量上。

## 触发

`causal_inject.py` 的逐案例装置符号守卫在第 12 个案例判红：

    ABORT 装置符号：注入 +α·U 后对应 token 的 logprob 未上升
                    （Wait −1.4017， the +20.3922）

` the` 涨了 20（守卫期望的形状），` Wait` 却跌了 1.4。
第一反应是「装置坏了」，但同一次运行里 ` the` 的形状是对的
⇒ 更可能是我**守卫的假设错了**。

## 假设错在哪

守卫的前提是「注入 `+α·U[tok]` ⇒ 该 token 的 logprob **必然**上升」。
这只在**小剂量**下成立：unembedding 有直接 logit 通路。

但 log_softmax 是**相对量**：

    logprob_tok = logit_tok − logsumexp(所有 logit)

只要**别的** token 的 logit 涨得比 `tok` 更多，`tok` 的 logprob
**照样会降**，哪怕它自己的 logit 一路涨。剂量越大，`U[tok]` 与
其他 unembedding 行的重叠部分越占主导，这个论证越不成立。

⇒ 「装置符号」是**符号约定**问题，属于小剂量极限；
   拿标定剂量去判它，等于用大剂量去检验一个小剂量的命题。

## 本脚本做什么

在同一个案例上，把两个 unembedding 基准从 α_rel = 0.005 扫到 1.0，
画出「Δlogprob 何时转负」⇒ 给出守卫该放在哪一档的**证据**，
而不是把阈值随手挪到「能过」为止。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/mutbak/guard_dose_scan.py
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
OUT = os.path.join(ROOT, ".cache", "mutbak", "guard_dose_scan.json")
LADDER = (0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0)


def main() -> int:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}
    gap = CI.class_gap(pos, tmap, CI.SEED)

    tk = AutoTokenizer.from_pretrained(CI.MODEL)
    mid, cid = CI.load_marker_ids(tk)
    ref_tok = mid[0]
    model = AutoModelForCausalLM.from_pretrained(CI.MODEL, dtype=torch.float32)
    model.eval()
    blk = model.model.layers[20]
    U = model.lm_head.weight.detach().float().numpy()
    Uref = U[ref_tok] / np.linalg.norm(U[ref_tok])
    Uctl = U[cid] / np.linalg.norm(U[cid])

    cases = CI.build_cases(pos, tmap)
    by = {}
    for c in cases:
        by.setdefault(c["traj"], []).append(c)
    tids = sorted(by)
    sel = [by[t][(j * 5) % len(by[t])] for j, t in enumerate(tids)][:6]

    rows = []
    for c in sel:
        z = np.load(os.path.join(NPZ_DIR, c["traj"] + ".npz"))
        full = np.concatenate([z["prompt_token_ids"].astype(np.int64),
                               z["token_ids"].astype(np.int64)])
        inj = len(z["prompt_token_ids"]) + c["t"] - 1
        if c["t"] >= len(z["token_ids"]):
            continue
        pre = torch.as_tensor(full[:inj + 1])[None, :]

        def run(v):
            if v is None:
                with torch.no_grad():
                    return model(pre).logits[0, -1]
            vv = torch.as_tensor(v, dtype=torch.float32)
            h = blk.register_forward_pre_hook(
                lambda m, inp, _v=vv: ((torch.cat(
                    [inp[0][:, :inj, :], inp[0][:, inj:inj + 1, :] + _v,
                     inp[0][:, inj + 1:, :]], dim=1),) + inp[1:]))
            try:
                with torch.no_grad():
                    return model(pre).logits[0, -1]
            finally:
                h.remove()

        def lp(lg, tid):
            return float(torch.log_softmax(lg, dim=-1)[tid])

        b = run(None)
        r = {"traj": c["traj"], "t": c["t"],
             "base_ref": lp(b, ref_tok), "base_ctl": lp(b, cid),
             "logit_ref": float(b[ref_tok]), "logit_ctl": float(b[cid]),
             "d": {}}
        for rel in LADDER:
            lr = run(rel * gap * Uref)
            lc = run(rel * gap * Uctl)
            r["d"][f"{rel:g}"] = {
                "ref_dlogprob": lp(lr, ref_tok) - r["base_ref"],
                "ctl_dlogprob": lp(lc, cid) - r["base_ctl"],
                # 同一 token 的 **logit** 变化（未归一化）
                "ref_dlogit": float(lr[ref_tok]) - r["logit_ref"],
                "ctl_dlogit": float(lc[cid]) - r["logit_ctl"],
            }
        rows.append(r)
        print(f"  {len(rows)}/{len(sel)}", end="\r", flush=True)
    print()

    def m(rel, k):
        return float(np.mean([r["d"][f"{rel:g}"][k] for r in rows]))

    print("\n=== 两个 unembedding 基准：logprob 变化 vs logit 变化 ===")
    print(f"  {'α_rel':>7s} {'|α_abs|':>9s} | "
          f"{'Wait Δlogit':>13s} {'Wait Δlogprob':>14s} | "
          f"{'the Δlogit':>12s} {'the Δlogprob':>13s}")
    print("  " + "-" * 78)
    for rel in LADDER:
        print(f"  {rel:7.3f} {rel * gap:9.1f} | "
              f"{m(rel, 'ref_dlogit'):+13.3f} {m(rel, 'ref_dlogprob'):+14.4f} | "
              f"{m(rel, 'ctl_dlogit'):+12.3f} {m(rel, 'ctl_dlogprob'):+13.4f}")

    # 守卫该放在哪一档：**所有**案例都必须为正
    print("\n  逐案例是否全为正（守卫的通过条件）：")
    safe = None
    for rel in LADDER:
        oks = [(r["d"][f"{rel:g}"]["ref_dlogprob"] > 0 and
                r["d"][f"{rel:g}"]["ctl_dlogprob"] > 0) for r in rows]
        n = sum(oks)
        mark = "  ← 守卫选这档" if rel == CI.CHK_REL else ""
        print(f"    α_rel={rel:<6g} 通过 {n}/{len(rows)} 案例{mark}")
        if n == len(rows) and safe is None:
            safe = rel
    print(f"\n  ⇒ 最大的「全部案例都通过」档位是 α_rel = {safe}")
    print(f"    脚本当前用的 CHK_REL = {CI.CHK_REL}"
          f"{'  ✅' if safe is not None and CI.CHK_REL <= safe else '  ⚠ 超出安全区'}")
    print("    ⚠ 关键对照：**logit 一路单调上升**，而 logprob 不是。")
    print("      这正是守卫必须看 logprob（小剂量）、而不能看 logit 的原因：")
    print("      logit 永远给你想要的符号，logprob 才反映「相对谁」。")

    json.dump({"rows": rows, "ladder": list(LADDER), "class_gap": gap,
               "max_safe_rel": safe, "chk_rel": CI.CHK_REL,
               "n_cases": len(rows)},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())