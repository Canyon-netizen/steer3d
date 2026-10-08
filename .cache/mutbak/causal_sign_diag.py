#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAUSAL 符号/尺度诊断 —— **已被取代，且本文件的注入循环带 bug**。

## ⚠⚠⚠ 别直接跑这个文件

本文件的第 2 阶段（`inject_run`）用的写法是

    torch.cat([inp[0][:, :inj, :] + v, inp[0][:, inj:, :]], dim=1)

⚠ 它把 `v` 加到了前缀的**每一个**位置，不是只加 `inj` ——
长得像「截断拼接」，读过去以为只改了 inj 那一行。
**这正是 `CAUSAL_PREREG.md` 修订 2 的 R-8**：读数作废。

正确写法（`causal_inject.py` 里用的是这一支）：

    x = inp[0].clone(); x[bidx, pos_idx, :] = x[bidx, pos_idx, :] + delta

## 本文件仍然有效的部分

**阶段 0 / 阶段 1 的结论是对的**（它们只读 npz、不做注入）：

- `npz 第 g 行 == 全序列第 (P+g−1) 位`（偏移扫描 off=−1 最优）
- `‖h(动摇点, L20)‖ 中位 1014.3`，`w·h` 的类间间距 **+375.2**
  ⇒ 预登记的 α ∈ {0.5…4} 只有自然尺度的 ~1%

要跑符号/剂量基准请用 **`causal_signbench.py`** 或
**`causal_inject.py`**（两者都是单位置注入）。

## 保留它的理由

阶段 1 的自然尺度数字是「剂量为何要重标」的唯一出处，
删掉它这条推理链就断了。缺陷照登，不藏。

## 原文档

## 为什么要单独做这一步

`causal_inject.py --limit 6` 的读数是：注入 **+w** 让 marker logprob
**下降**（α=+0.5 → −0.0006，+4 → −0.0049），−w 让它上升。
而 `CAUSAL_PREREG.md` §1 写死的是「+w ⇒ 更容易动摇」。

⚠ **三条路都还开着**，本脚本的目的是**把它们分开**，而不是挑一个能解释
   现有读数的那个：

   (a) 装置把符号弄错了（注入进了与 `w` 不同的空间 / 符号反了）
   (b) 剂量的量纲错了（α 的单位与隐状态自然尺度不匹配，
       整个预登记剂量档都落在流形之外）
   (c) 预登记的因果假设本身错了（区分方向 ≠ 驱动方向）

## 三个阶段

- **阶段 0 空间对齐**：npz 的 `hidden_states[20]` 到底是 HF 的第几层？
  直接跑一次模型对照。这是 (a) 里唯一可能藏 bug 的地方。
- **阶段 1 自然尺度**：`‖h‖`、`w·h` 的类间差与类内标准差。
  如果 α 的步长比**整条轨迹上 hinge 与 random 的全部间距**还大，
  那 (b) 就不是猜测而是算术。
- **阶段 2 符号基准**：拿一个**因果方向无歧义**的向量 —— 某个 token 的
  unembedding 行 `U[tok]`。注入 +α·û，logprob **必然**上升。
  这条若不成立，(a) 成立，6 案例读数是管道假象。
  若成立，(a) 被证伪，(b)(c) 才是候选。

本脚本**不改** `CAUSAL_PREREG.md` 的任何判决规则，也不改口径。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
import probe_hinge_layers as P  # noqa: E402

NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
MODEL = os.path.join(ROOT, "datasets", "models", "Qwen3-1.7B")
LAYER = 20
OFF = 1
SEED = 20261007

# 细剂量梯：刻意覆盖**自然间距之内**，而预登记的档位全部在其之外
FINE = (0.0, 0.05, 0.10, 0.20, 0.30, 0.46, 0.70, 1.0, 2.0, 4.0)


def pick_spread(cases, per_traj=2):
    """跨轨迹均匀取样：每条轨迹最多 `per_traj` 个，避免全挤在一条上。

    ⚠ 第一版写成了「遍历到最深的那条轨迹的深度」，
      于是每条轨迹的**全部**动摇点都被收进来（121 个），
      `--per-traj` 形同虚设 ⇒ 一次诊断要跑 4500 次前向。
      顺带一个教训：**参数没生效时脚本不会报错，只会变慢**，
      所以打印出的案例数必须与 `--per-traj` 对得上才算数。
    """
    by = {}
    for c in cases:
        by.setdefault(c["traj"], []).append(c)
    tids = sorted(by)
    out, used = [], set()
    for i in range(per_traj):
        for j, t in enumerate(tids):
            # 每条轨迹用不同的相位取样，避免 22 条都取自己的第一个动摇点
            idx = (i * 5 + j * 3) % len(by[t])
            key = (t, idx)
            if key not in used:
                used.add(key)
                out.append(by[t][idx])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-traj", type=int, default=2)
    ap.add_argument("--out", default=os.path.join(ROOT, ".cache", "mutbak",
                                                  "causal_sign_diag.json"))
    a = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}
    sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
    import causal_inject as CI
    W, sep = CI.train_direction(pos, tmap, SEED)

    all_cases = CI.build_cases(pos, tmap)
    cases = pick_spread(all_cases, a.per_traj)
    print(f"诊断案例 {len(cases)} 个 / 轨迹 {len(set(c['traj'] for c in cases))}")

    tk = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32)
    model.eval()
    blk = model.model.layers[LAYER]
    print(f"tie_word_embeddings={getattr(model.config, 'tie_word_embeddings', '?')}"
          f"  lm_head.weight {tuple(model.lm_head.weight.shape)}")

    rng = np.random.default_rng(SEED + 1)
    R = rng.normal(size=W.shape).astype(np.float32)
    R /= np.linalg.norm(R)

    out = {"layer": LAYER, "off": OFF, "n_cases": len(cases),
           "n_traj": len(set(c["traj"] for c in cases))}

    # ==================================================================
    # 阶段 0：npz 的层索引对齐
    # ==================================================================
    tid0 = cases[0]["traj"]
    rec0 = json.load(open(os.path.join(NPZ_DIR, tid0 + ".json"), encoding="utf-8"))
    text0 = rec0.get("prompt", "") + rec0.get("generated_text", "")
    enc0 = tk(text0, return_tensors="pt")
    with torch.no_grad():
        hs = model(**enc0, output_hidden_states=True).hidden_states  # 29 个
    H = np.load(os.path.join(NPZ_DIR, tid0 + ".npz"))["hidden_states"]
    print(f"\n=== 阶段 0：npz 层索引对齐（轨迹 {tid0}）===")
    print(f"  HF hidden_states: {len(hs)} 层；npz hidden_states: {H.shape[1]} 层")
    tprobe = min(cases[0]["t"], H.shape[0] - 1, hs[0].shape[1] - 1)
    row = []
    for k in range(LAYER - 2, LAYER + 4):
        if k >= len(hs):
            continue
        ref = hs[k][0, tprobe].float().numpy().astype(np.float64)
        got = H[tprobe, k].astype(np.float64)
        denom = max(1e-9, float(np.linalg.norm(ref)))
        rel = float(np.linalg.norm(got - ref) / denom)
        row.append((k, rel))
        print(f"  npz[{tprobe},{k}] vs HF hidden_states[{k}]  相对误差 {rel:.5f}"
              f"{'   ← 最匹配' if rel == min(r for _, r in row) else ''}")
    best_k, best_rel = min(row, key=lambda kv: kv[1])
    out["stage0"] = {"traj": tid0, "t": int(tprobe), "rel_by_k": {str(k): r
                                                               for k, r in row},
                     "best_k": best_k, "best_rel": best_rel,
                     "aligned": bool(best_k == LAYER and best_rel < 0.05)}
    if best_k != LAYER:
        print(f"  ⚠⚠ npz 第 {LAYER} 层实际对应 HF 的第 {best_k} 层！"
              f" ⇒ 注入点错位 {best_k - LAYER:+d} 层，`w` 的空间与注入空间不同源。")
    else:
        print(f"  ⇒ npz[{LAYER}] = HF hidden_states[{LAYER}] = 第 {LAYER} 层**的输入**"
              f"（forward_pre_hook 落点正确）。")

    # ==================================================================
    # 阶段 1：自然尺度
    # ==================================================================
    print("\n=== 阶段 1：自然尺度 ===")
    negs = P.pick_negatives(pos, np.random.default_rng(SEED), tmap=tmap)
    X, y, _ = P.build_xy(pos, negs)
    Hpos = X[y == 1][:, LAYER, :].astype(np.float64)
    Hneg = X[y == 0][:, LAYER, :].astype(np.float64)
    nrm = np.linalg.norm(Hpos, axis=1)
    sp = Hpos @ W
    sn = Hneg @ W
    gap = float(sp.mean() - sn.mean())
    print(f"  ‖h(动摇点, L{LAYER})‖：中位 {np.median(nrm):.2f}"
          f"  范围 [{nrm.min():.1f}, {nrm.max():.1f}]")
    print(f"  w·h 动摇点：均值 {sp.mean():+.3f} ± {sp.std():.3f}"
          f"（n={len(sp)}）")
    print(f"  w·h 随机点：均值 {sn.mean():+.3f} ± {sn.std():.3f}（n={len(sn)}）")
    print(f"  ⇒ 类间间距 {gap:+.3f}，是随机点类内标准差的 "
          f"{gap / max(1e-9, sn.std()):.2f} 倍")
    print(f"  ⇒ 预登记最大剂量 α=4 是类间间距的 {4.0 / max(1e-9, abs(gap)):.1f} 倍，"
          f"是 ‖h‖ 的 {4.0 / max(1e-9, nrm.mean()):.1%}")
    out["stage1"] = {"norm_median": float(np.median(nrm)),
                     "norm_mean": float(nrm.mean()),
                     "score_pos_mean": float(sp.mean()), "score_pos_sd": float(sp.std()),
                     "score_neg_mean": float(sn.mean()), "score_neg_sd": float(sn.std()),
                     "class_gap": gap,
                     "alpha4_over_gap": float(4.0 / max(1e-9, abs(gap))),
                     "alpha4_over_norm": float(4.0 / max(1e-9, nrm.mean()))}

    # ==================================================================
    # 阶段 2：符号基准（unembedding 行）
    # ==================================================================
    print("\n=== 阶段 2：符号基准 —— 注入 unembedding 行 ===")
    mid, cid = CI.load_marker_ids(tk)
    U = model.lm_head.weight.detach().float().numpy()
    ref_tok = mid[0]                       # ` Wait`
    print(f"  基准 token = {tk.decode([ref_tok])!r} (id={ref_tok})；"
          f"第二基准 = {tk.decode([cid])!r} (id={cid})")
    Uref = U[ref_tok] / (np.linalg.norm(U[ref_tok]) + 1e-12)
    Uctl = U[cid] / (np.linalg.norm(U[cid]) + 1e-12)

    def inject_run(pre_ids, inj, vec):
        h = blk.register_forward_pre_hook(
            lambda mod, inp, _v=torch.as_tensor(vec, dtype=torch.float32): (
                (torch.cat([inp[0][:, :inj, :] + _v,
                            inp[0][:, inj:, :]], dim=1),) + inp[1:]))
        try:
            with torch.no_grad():
                return model(pre_ids).logits[0, -1]
        finally:
            h.remove()

    def read(lg, ids):
        lp = torch.log_softmax(lg, dim=-1)
        return float(torch.logsumexp(lp[torch.as_tensor(ids)], dim=0))

    rows = []
    for c in cases:
        tid = c["traj"]
        rec = json.load(open(os.path.join(NPZ_DIR, tid + ".json"), encoding="utf-8"))
        enc = tk(rec.get("prompt", "") + rec.get("generated_text", ""),
                 return_tensors="pt")
        n = enc["input_ids"].shape[1]
        if c["t"] >= n:
            continue
        pre = enc["input_ids"][:, :c["t"]]
        base = inject_run(pre, c["inj"], np.zeros_like(W))
        r = {"traj": tid, "t": c["t"], "inj": c["inj"],
             "b_ref": read(base, [ref_tok]), "b_ctl": read(base, [cid]),
             "b_mark": read(base, mid), "fine": {}}
        for al in FINE:
            for tag, dv in (("w", W), ("Uref", Uref), ("Uctl", Uctl), ("rand", R)):
                v = al * dv
                lg = inject_run(pre, c["inj"], v) if al != 0.0 else base
                r["fine"].setdefault(tag, {})[f"{al:+.2f}"] = {
                    "ref": read(lg, [ref_tok]) - r["b_ref"],
                    "ctl": read(lg, [cid]) - r["b_ctl"],
                    "mark": read(lg, mid) - r["b_mark"],
                }
        rows.append(r)
    out["n_done"] = len(rows)

    def m(tag, al, key):
        return float(np.mean([r["fine"][tag][f"{al:+.2f}"][key] for r in rows]))

    print(f"\n  {'α':>7s} | {'Δ logp(基准 Wait)':>18s} | {'Δ logp( the)':>14s} | "
          f"{'Δ logp(marker)':>15s}")
    print("  " + "-" * 66)
    for al in FINE:
        s = f"{al:+7.2f}"
        if al == 0.0:
            print(f"  {s} | {'0（基线）':>18s}")
            continue
        print(f"  {s} | Uref {m('Uref', al, 'ref'):+9.4f}     | "
              f"Uctl {m('Uctl', al, 'ctl'):+6.4f}   | "
              f"w {m('w', al, 'mark'):+7.4f}")
    print("\n  读法：Uref/Uctl 两行是**因果方向无歧义**的基准 ——")
    print("        注入 +α·U[tok] 必然抬高 tok 的 logprob。")
    print("        若这两行为负 ⇒ 装置符号反了 (a)。")
    print("        若这两行为正 ⇒ 装置符号正确，w 的效应是真实读数。")

    # 单调性：基准方向上，logp 是否随 α 单调上升
    def spearman(x, y):
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        rx -= rx.mean(); ry -= ry.mean()
        d = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
        return float((rx * ry).sum() / d) if d else 0.0

    pos_al = [x for x in FINE if x > 0]
    rho_ref = spearman([m("Uref", x, "ref") for x in pos_al], pos_al)
    rho_ctl = spearman([m("Uctl", x, "ctl") for x in pos_al], pos_al)
    rho_w = spearman([m("w", x, "mark") for x in pos_al], pos_al)
    print(f"\n  ρ(α, Δ基准 logp) = {rho_ref:+.3f}   "
          f"ρ(α, Δ'the' logp) = {rho_ctl:+.3f}   "
          f"ρ(α, Δmarker by w) = {rho_w:+.3f}")
    verdict_a = ("符号反了" if (rho_ref < 0 and rho_ctl < 0) else
                 ("符号正确" if (rho_ref > 0 and rho_ctl > 0) else "基准不明确"))
    print(f"  ⇒ 阶段 2 判决（仅针对 (a) 装置符号）：**{verdict_a}**")
    out["stage2"] = {"rho_Uref": rho_ref, "rho_Uctl": rho_ctl, "rho_w": rho_w,
                     "verdict_device_sign": verdict_a,
                     "ref_tok_id": int(ref_tok), "ctl_tok_id": int(cid),
                     "alphas": list(FINE)}

    # w 在**自然间距之内**的行为
    inside = [x for x in (0.05, 0.10, 0.20, 0.30, 0.46) if x > 0]
    print("\n  w 在类间间距之内（α ≤ 0.46）的 Δmarker：")
    for al in inside:
        print(f"    α={al:+.2f}  Δmarker {m('w', al, 'mark'):+.5f}  "
              f"Δ'the' {m('w', al, 'ctl'):+.5f}")
    out["w_inside"] = {f"{x:+.2f}": m("w", x, "mark") for x in inside}

    json.dump(out, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
