#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAUSAL 符号基准 + 剂量标定：**两个问题一次问完**。

## 问什么

**(1) 装置的符号对不对？**
用一个**因果方向无歧义**的向量做基准：`U[tok]`，即某个 token 在
`lm_head.weight` 里那一行。注入 `+α·U[tok]`，该 token 的 logprob
**必然**上升 —— 这与任何学出来的方向无关。
- 若基准也是负的 ⇒ 装置符号反了，`w` 的读数全是管道假象。
- 若基准是正的 ⇒ 装置符号正确，`w` 的负效应是**真实读数**。

**(2) 剂量标定在什么尺度上？**
阶段 1 实测：‖h(动摇点, L20)‖ 中位 **1014**，而 `w·h` 的
动摇/随机类间间距只有 **375**。
预登记的 α ∈ {0.5, 1, 2, 4} 只有 ‖h‖ 的 **0.4%**、
类间间距的 **1%** ⇒ 整套剂量梯比数据的自然尺度小约两个数量级。
本脚本把剂量写成**相对类间间距**的倍数 `α_rel`，并同时扫
`w` 与两个 unembedding 基准。

⚠ 这不是「加大剂量直到读数好看」。锚点是**数据自己的尺度**
（实测出来的类间间距），且原剂量梯的读数原样保留在
`CAUSAL_PREREG.md` 修订 1 里。

## 位置映射

用 `.cache/mutbak/causal_align.py` 验过的那套：
npz 第 g 行 == 全序列第 `P+g−1` 位，P = len(prompt_token_ids)。
"""
from __future__ import annotations

import argparse
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


def spearman(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean(); ry -= ry.mean()
    d = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / d) if d else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(ROOT, ".cache", "mutbak",
                                                  "causal_signbench.json"))
    a = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}
    W, sep = CI.train_direction(pos, tmap, SEED)

    # ---- 自然尺度（用于标定）----
    negs = P.pick_negatives(pos, np.random.default_rng(SEED), tmap=tmap)
    X, y, _ = P.build_xy(pos, negs)
    Hpos = X[y == 1][:, LAYER, :].astype(np.float64)
    Hneg = X[y == 0][:, LAYER, :].astype(np.float64)
    nrm = float(np.median(np.linalg.norm(Hpos, axis=1)))
    gap = float(np.mean(Hpos @ W) - np.mean(Hneg @ W))
    print(f"自然尺度：‖h‖ 中位 {nrm:.1f}   w·h 类间间距 {gap:+.1f}")

    cases = CI.build_cases(pos, tmap)
    by = {}
    for c in cases:
        by.setdefault(c["traj"], []).append(c)
    tids = sorted(by)
    sel = [by[t][(j * 5) % len(by[t])] for j, t in enumerate(tids)][:a.n]
    print(f"案例 {len(sel)} 个 / 轨迹 {len(set(c['traj'] for c in sel))}")

    tk = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32)
    model.eval()
    blk = model.model.layers[LAYER]
    U = model.lm_head.weight.detach().float().numpy()
    mid, cid = CI.load_marker_ids(tk)
    ref_tok = mid[0]
    Uref = U[ref_tok] / np.linalg.norm(U[ref_tok])
    Uctl = U[cid] / np.linalg.norm(U[cid])
    rng = np.random.default_rng(SEED + 1)
    R = rng.normal(size=W.shape).astype(np.float32); R /= np.linalg.norm(R)

    # α_rel 是「相对类间间距的倍数」；α_abs = α_rel * gap
    REL = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0)
    dirs = {"w": W, "Uref": Uref, "Uctl": Uctl, "rand": R}

    rows = []
    for c in sel:
        z = np.load(os.path.join(NPZ_DIR, c["traj"] + ".npz"))
        n_pre = len(z["prompt_token_ids"])
        gids = z["token_ids"].astype(np.int64)
        if c["t"] >= len(gids):
            continue
        full = np.concatenate([z["prompt_token_ids"].astype(np.int64), gids])
        pos_read = n_pre + c["t"] - 1
        pre = torch.as_tensor(full[:pos_read + 1])[None, :]

        def run(vec):
            if vec is None:
                with torch.no_grad():
                    return model(pre).logits[0, -1]
            v = torch.as_tensor(vec, dtype=torch.float32)
            h = blk.register_forward_pre_hook(
                lambda m, inp, _v=v: ((torch.cat(
                    [inp[0][:, :pos_read, :] + _v, inp[0][:, pos_read:, :]], dim=1),)
                    + inp[1:]))
            try:
                with torch.no_grad():
                    return model(pre).logits[0, -1]
            finally:
                h.remove()

        def rd(lg, ids):
            lp = torch.log_softmax(lg, dim=-1)
            return float(torch.logsumexp(lp[torch.as_tensor(list(ids))], dim=0))

        base = run(None)
        b = {"ref": rd(base, [ref_tok]), "ctl": rd(base, [cid]), "mark": rd(base, mid),
             "cur": rd(base, [int(gids[c["t"]])])}
        rec = {"traj": c["traj"], "t": c["t"], "base": b, "d": {}}
        for nm, dv in dirs.items():
            for rel in REL:
                lg = run(rel * gap * dv)
                rec["d"].setdefault(nm, {})[f"{rel:g}"] = {
                    "ref": rd(lg, [ref_tok]) - b["ref"],
                    "ctl": rd(lg, [cid]) - b["ctl"],
                    "mark": rd(lg, mid) - b["mark"],
                    "cur": rd(lg, [int(gids[c["t"]])]) - b["cur"],
                }
        rows.append(rec)
        print(f"  {len(rows)}/{len(sel)}", end="\r", flush=True)
    print()

    def m(nm, rel, key):
        return float(np.mean([r["d"][nm][f"{rel:g}"][key] for r in rows]))

    print("\n=== 符号基准（Uref=' Wait', Uctl=' the'；注入 +α·U 必然抬高该 token）===")
    print(f"  {'α_rel':>7s} {'|α_abs|':>9s} | {'Uref':>9s} {'Uctl':>9s} | "
          f"{'w:marker':>10s} {'w:当前token':>12s} {'rand:marker':>11s}")
    print("  " + "-" * 78)
    for rel in REL:
        aabs = rel * gap
        print(f"  {rel:7.2f} {aabs:9.1f} | {m('Uref',rel,'ref'):+9.4f} "
              f"{m('Uctl',rel,'ctl'):+9.4f} | {m('w',rel,'mark'):+10.4f} "
              f"{m('w',rel,'cur'):+12.4f} {m('rand',rel,'mark'):+11.4f}")

    rr_ref = spearman([m("Uref", r, "ref") for r in REL], REL)
    rr_ctl = spearman([m("Uctl", r, "ctl") for r in REL], REL)
    rw = spearman([m("w", r, "mark") for r in REL], REL)
    rw_cur = spearman([m("w", r, "cur") for r in REL], REL)
    print(f"\n  ρ(α_rel, Δ基准logp):  Uref {rr_ref:+.3f}   Uctl {rr_ctl:+.3f}")
    print(f"  ρ(α_rel, Δmarker by w): {rw:+.3f}      "
          f"ρ(α_rel, Δ「标记词本身」的 logprob by w): {rw_cur:+.3f}")

    if rr_ref > 0.8 and rr_ctl > 0.8:
        v = "装置符号正确（+α·U 抬高对应 token）⇒ w 的读数是真实效应"
    elif rr_ref < -0.8 and rr_ctl < -0.8:
        v = "装置符号反了 ⇒ 全部读数作废"
    else:
        v = "基准不明确（两个 unembedding 方向不同向）"
    print(f"  ⇒ **符号判决：{v}**")

    print("\n=== w 的剂量曲线（找符号翻转点）===")
    print(f"  {'α_rel':>7s} {'Δmarker':>10s} {'Δ当前token':>12s} {'Δ the':>10s}")
    for rel in REL:
        print(f"  {rel:7.2f} {m('w',rel,'mark'):+10.4f} {m('w',rel,'cur'):+12.4f} "
              f"{m('w',rel,'ctl'):+10.4f}")

    json.dump({"layer": LAYER, "n_cases": len(rows), "norm_median": nrm,
               "class_gap": gap, "rel_ladder": list(REL),
               "rho_Uref": rr_ref, "rho_Uctl": rr_ctl, "rho_w_marker": rw,
               "rho_w_cur": rw_cur, "verdict_sign": v, "rows": rows},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())