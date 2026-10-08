#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现第 12 个案例的守卫判红：到底是剂量问题还是**位置**问题。

## 背景

38 案例的正式跑在第 12 个案例被逐案例守卫拦下：

    ABORT 装置符号：注入 +α·U 后对应 token 的 logprob 未上升
                    （Wait −1.4017， the +20.3922）

我先猜是**剂量**问题（log_softmax 是相对量，大剂量下别的 token
涨得更多就会把目标压下去），于是把守卫剂量从 α_rel=1.0 挪到 0.05。

**但 `guard_dose_scan.py` 否掉了这个猜测**：6 个案例 × 8 个剂量，
两个基准的 Δlogprob **全部为正且单调**，一直到 α_rel=1.0。
⇒ 剂量不是原因，那是**位置特有**。

本脚本用与正式跑**完全相同**的取样规则复现第 12 个案例，
印出它当时要预测的 token、基线、以及 α_rel=1.0 时
**logit 涨幅最大的 8 个 token** —— 看「谁把 Wait 压下去了」。

判别：
- 若 `Wait` 自己的 Δlogit **为正**但 Δlogprob 为负
  ⇒ 装置没问题，是别的 token 涨得更多（log_softmax 是相对量）。
  守卫本身是对的，但**不该逐案例判死** ——
  该判的是「符号约定是否反了」，而那要看 Δ**logit**，不是 Δlogprob。
- 若 `Wait` 自己的 Δlogit **为负** ⇒ 装置真的坏了，必须停。
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
OUT = os.path.join(ROOT, ".cache", "mutbak", "guard_case12.json")
NTH = 12                      # 判红的是第 12 个案例（1-based）
LADDER = (0.05, 0.25, 0.5, 1.0)


def main() -> int:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}
    gap = CI.class_gap(pos, tmap, CI.SEED)

    tk = AutoTokenizer.from_pretrained(CI.MODEL)
    mid, cid = CI.load_marker_ids(tk)
    ref_tok = mid[0]

    # ⚠ 用与正式跑**完全相同**的取样规则复现第 12 个案例
    cases = CI.build_cases(pos, tmap)
    by = {}
    for c in cases:
        by.setdefault(c["traj"], []).append(c)
    tids = sorted(by)
    sel, used = [], set()
    for i in range(2):
        for j, t in enumerate(tids):
            idx = (i * 5 + j * 3) % len(by[t])
            if (t, idx) not in used:
                used.add((t, idx))
                sel.append(by[t][idx])
    c = sel[NTH - 1]
    print(f"第 {NTH} 个案例：{c['traj']}  t={c['t']}")

    model = AutoModelForCausalLM.from_pretrained(CI.MODEL, dtype=torch.float32)
    model.eval()
    blk = model.model.layers[20]
    U = model.lm_head.weight.detach().float().numpy()
    Uref = U[ref_tok] / np.linalg.norm(U[ref_tok])

    z = np.load(os.path.join(NPZ_DIR, c["traj"] + ".npz"))
    gids = z["token_ids"].astype(np.int64)
    full = np.concatenate([z["prompt_token_ids"].astype(np.int64), gids])
    inj = len(z["prompt_token_ids"]) + c["t"] - 1
    pre = torch.as_tensor(full[:inj + 1])[None, :]
    actual = int(gids[c["t"]])

    def run(v):
        if v is None:
            with torch.no_grad():
                return model(pre).logits[0, -1].clone()
        vv = torch.as_tensor(v, dtype=torch.float32)
        h = blk.register_forward_pre_hook(
            lambda m, inp, _v=vv: ((torch.cat(
                [inp[0][:, :inj, :], inp[0][:, inj:inj + 1, :] + _v,
                 inp[0][:, inj + 1:, :]], dim=1),) + inp[1:]))
        try:
            with torch.no_grad():
                return model(pre).logits[0, -1].clone()
        finally:
            h.remove()

    b = run(None)
    bp = torch.log_softmax(b, dim=-1)
    b_lse = float(torch.logsumexp(b, 0))
    print(f"  该位置要预测：{tk.decode([actual])!r} (id={actual})，"
          f"在 marker 集合内：{actual in mid}")
    print(f"  基线 logprob：Wait {float(bp[ref_tok]):+.4f}   "
          f"the {float(bp[cid]):+.4f}   实际 {float(bp[actual]):+.4f}")

    rows = []
    print(f"\n  {'α_rel':>7s} {'ΔWait logprob':>14s} {'ΔWait logit':>12s} "
          f"{'Δthe logprob':>13s} {'Δlogsumexp':>11s}")
    for rel in LADDER:
        lg = run(rel * gap * Uref)
        lp = torch.log_softmax(lg, dim=-1)
        r = {"rel": rel,
             "d_logprob": float(lp[ref_tok]) - float(bp[ref_tok]),
             "d_logit": float(lg[ref_tok]) - float(b[ref_tok]),
             "d_ctl_lp": float(lp[cid]) - float(bp[cid]),
             "d_lse": float(torch.logsumexp(lg, 0)) - b_lse}
        rows.append(r)
        print(f"  {rel:7.2f} {r['d_logprob']:+14.4f} {r['d_logit']:+12.4f} "
              f"{r['d_ctl_lp']:+13.4f} {r['d_lse']:+11.4f}")

    lg = run(1.0 * gap * Uref)
    dl = (lg - b).numpy()
    order = np.argsort(dl)[::-1]
    rank = int((dl > dl[ref_tok]).sum()) + 1
    print(f"\n  α_rel=1.0：Wait 自己的 Δlogit = {dl[ref_tok]:+.3f}，"
          f"在 {len(dl)} 个 token 里排第 {rank} 名")
    print("  logit 涨幅最大的 8 个 token：")
    top = []
    for tid in order[:8]:
        top.append({"id": int(tid), "text": tk.decode([int(tid)]),
                    "d_logit": float(dl[tid])})
        print(f"    {tk.decode([int(tid)])!r:16s} id={int(tid):7d}  "
              f"Δlogit {dl[tid]:+8.3f}   基线 logit {float(b[tid]):+8.2f}")

    verdict = ("装置正常：Wait 的 logit 确实上升，只是别的 token 涨得更多，"
               "log_softmax 的相对性把它压成负的"
               if dl[ref_tok] > 0 else "装置异常：Wait 的 logit 本身没上升")
    print(f"\n  ⇒ {verdict}")

    json.dump({"case": {"traj": c["traj"], "t": c["t"]},
               "actual_token_id": actual,
               "actual_token_text": tk.decode([actual]),
               "d_logit_ref": float(dl[ref_tok]), "rank_of_ref": rank,
               "rows": rows, "top_gainers": top, "verdict": verdict},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())