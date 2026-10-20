#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_probe_24464_crosscheck.py —— 244.64/244.65 的**独立对账实现**（已入库的独立探针）

⚖⚖⚖⚖⚖ **本脚本自带分档器 + 自带 MC + 自带层内多数 + 自带零假设基准**
   （⛔ **不 import 待入库的口径实现**）⇒ 它顺带就是**第二份独立实现**
   ⇒ 工具 `dose_convention2_audit.py` 若与本脚本逐位一致 ⇒ 两份独立实现互证。

⚖ **只复用「判据层」的机械**（沿用 244.63 的做法）：
   `dose_confound_audit.d_of` / `frac_of` / `majority_count` / `spearman`
   / `verdict_source_audit.load_rows`（读数）
   ⚖⚠⚠⚠⚖⚖ **不复用**（244.65 起，**这三样正是本轮新改过的东西**）：
   `dose_bands_v` / `dose_cells` / **`mc_trend_p_geom`**
   / **`layer_verdicts`** / **`majority_base_p` / `majority_base_p2`**
   ⇒ 那几个**必须**由本脚本**自己**算 ⇒ 否则「两份实现互证」是假的。

⚖⚖⚖⚖⚖ **244.65 的更正（这就是本探针为什么必须改）**：
   244.65 查出 `layer_verdicts` 把**零格**也算进了零假设基准
   ⇒ 旧版探针（用 `layer_verdicts` + `majority_base_p`）**算的是修复前的数**
   ⇒ 它当时那句「504 字段 0 不一致」对**有零格**的组合**已经失效**
   ⇒ 本文件改为**自己**算零假设与 nz/nzero 拆分。

⚖ 对账的字段（36 组合 × 2 臂）：档表 / 各档 K / 趋势 T / 趋势 p / rho /
   剂量轴口径多数 / 检出状态 / **零格数** —— **逐位**比较。

跑法：python3 .cache/r244/_probe_24464_crosscheck.py
退出码：0 = 两份实现逐位一致；1 = 有不一致。
"""
import collections
import itertools
import math
import os
import random
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import dose_confound_audit as DC  # noqa: E402
import interval_audit as IA  # noqa: E402
import verdict_source_audit as VS  # noqa: E402

JSONL_W = os.path.join(HERE, "_an.txt")
JSONL_RAND = os.path.join(HERE, "_ra.txt")
ALPHA = 0.05
N_MC = 5000
MC_SEED = 20261020
ARMS = ("w", "rand")

QUANTILES = ("inclusive", "exclusive", "nearest_rank")
BAND_COUNTS = (3, 4, 5)
BOUNDARIES = ("prod", "alt")
ZERO_SPANS = ("keep", "drop")

BASE_COMBO = ("inclusive", 4, "prod", "keep")


# ================================================================ 自带分档器
def my_dose_cells(recs, zero_span="keep"):
    """⚖ **本脚本自己**的格集合（⛔ 不 import `dose_cells`）。"""
    meas = [r for r in recs if r.get("p9_lo_meas") is not None]
    ks = [r for r in meas if r["inject_scope"] == "k" and r.get("inject_n_sites")]
    if zero_span == "drop":
        ks = [r for r in ks if DC.d_of(r) != 0.0]
    return ks, [DC.frac_of(r) for r in ks]


def my_quantiles(fr, method, n):
    """⚖ **本脚本自己**的分位点（n 档 ⇒ n−1 个内切点）。"""
    n_fr = len(fr)
    if method == "inclusive":
        return list(st.quantiles(fr, n=n))
    if method == "exclusive":
        return list(st.quantiles(fr, n=n, method="exclusive"))
    if method == "nearest_rank":
        srt = sorted(fr)
        out = []
        for i in range(1, n):
            p = float(i) / n
            idx = int(math.ceil(p * n_fr)) - 1
            idx = max(0, min(n_fr - 1, idx))
            out.append(srt[idx])
        return out
    raise AssertionError("method %r" % method)


def my_bands(ks, fr, method, n, boundary):
    """⚖ **本脚本自己**的分档（prod：首档含 q1、中间左开右闭、末档开；
    alt：首档不含 q1、中间左闭右开、末档闭）。"""
    qs = my_quantiles(fr, method, n)
    out = []
    for i in range(n):
        if boundary == "prod":
            if i == 0:
                sel = [r for r, f in zip(ks, fr) if f <= qs[0]]
            elif i == n - 1:
                sel = [r for r, f in zip(ks, fr) if f > qs[-1]]
            else:
                sel = [r for r, f in zip(ks, fr) if qs[i - 1] < f <= qs[i]]
        else:
            if i == 0:
                sel = [r for r, f in zip(ks, fr) if f < qs[0]]
            elif i == n - 1:
                sel = [r for r, f in zip(ks, fr) if f >= qs[-1]]
            else:
                sel = [r for r, f in zip(ks, fr) if qs[i - 1] <= f < qs[i]]
        out.append(("band%d" % i, sel))
    return qs, out


# ============================================ 自带「层内多数 + 零假设基准」
def my_layer_verdicts(cells_by_tid):
    """⚖ **本脚本自己**的层内多数（⛔ 不 import `dose_layer_audit.layer_verdicts`）。

    ⚖ 规则 `nT > nF` ⇒ **平票算 False** ⇒ **零格恒为 False ⇒ 进分母**
    ⚖ `nz` = **非零**格数（零格**不进基准**，只进分母）
    ⚖⚠⚠ **为什么必须自己算**：`layer_verdicts` 的 `nz` 语义**正是 244.65 改的那一处**
    ⇒ 复用它 ⇒ 本探针就**验不了**它 ⇒ 「两份实现互证」变成空话。
    """
    out = {}
    for tid, cs in cells_by_tid.items():
        nT = sum(1 for c in cs if DC.d_of(c) > 0)
        nF = sum(1 for c in cs if not (DC.d_of(c) > 0))
        nzero = sum(1 for c in cs if DC.d_of(c) == 0.0)
        out[tid] = {"pos": nT, "neg": nF, "nz": len(cs) - nzero,
                    "nzero": nzero, "m": len(cs), "verdict": nT > nF}
    return out


def my_base(n_nz, n_zero):
    """⚖ **本脚本自己**的层内零假设基准（**零格不进基准**的正确版）。

    ⚖ 零假设：每个**非零**格的符号是公平硬币（`nT ~ Bin(n_nz, 0.5)`）；
       **零格恒为 False** ⇒ 判据 `npos·2 > n_nz + n_zero`（分母含零格 ⇒ 阈值抬高）
    ⚖⚠⚠⛔ **不复用** `majority_base_p2` ⇒ 它正是 244.65 新写的那个函数。
    """
    if n_nz <= 0:
        return 0.5
    tot = n_nz + n_zero
    return sum(math.comb(n_nz, j) * 0.5 ** n_nz
               for j in range(n_nz + 1) if j * 2 > tot)


def my_base_old(nz):
    """⚖ **旧写法**（244.65 之前）：把**零格也**当一次公平抛硬币。

    ⚖ 用途只有一个：当**零格数 > 0** 时，`my_base(nz, nzero)` 必须 **≠** `my_base_old(m)`
    ⇒ 这就是「零格被算进基准」这条缺陷**独立可见**的证据。
    """
    if nz <= 0:
        return 0.5
    return sum(math.comb(nz, j) * 0.5 ** nz
               for j in range(nz // 2 + 1, nz + 1))


def my_mc(rows, n_layer):
    """⚖ 剂量趋势 MC（**本脚本自己**一份，层数可变，零格不进基准）。

    ⚖⚠⚖⚖⚖ **随机流的消耗量必须与待验实现一致**（仍抽 `n_nz + n_zero` 次，
       只用前 `n_nz` 次）⇒ 否则 p **无法逐位比对**（不是「对不上」，
       是**比的不是同一件事**）。
    """
    e0 = [sum(my_base(nz, nz0) for nz, nz0 in rows[L]["nzs"])
          for L in range(n_layer)]
    w_off = (n_layer - 1) / 2.0
    t_obs = sum((L - w_off) * (rows[L]["K"] - e0[L]) for L in range(n_layer))
    rng = random.Random(MC_SEED)
    ge = 0
    for _ in range(N_MC):
        tot = 0.0
        for L in range(n_layer):
            k = 0
            for n_nz, n_zero in rows[L]["nzs"]:
                draws = [rng.random() for _ in range(n_nz + n_zero)]
                npos = sum(1 for r in draws[:n_nz] if r < 0.5)
                if npos * 2 > n_nz + n_zero:
                    k += 1
            tot += (L - w_off) * (k - e0[L])
        if tot >= t_obs - 1e-12:
            ge += 1
    return (ge + 1) / float(N_MC + 1), t_obs, e0, ge, N_MC


def my_combo(rows_by_arm, combo):
    """⚖ 一个口径组合 ⇒ 本脚本自己算出来的两臂结果。"""
    method, n, boundary, zero_span = combo
    out = {"arm": {}}
    for arm in ARMS:
        recs = rows_by_arm[arm]
        ks, fr = my_dose_cells(recs, zero_span=zero_span)
        if not ks:
            raise AssertionError("没有格")
        qs, bands = my_bands(ks, fr, method, n, boundary)
        rows = []
        for i, (_lab, sub) in enumerate(bands):
            g = collections.OrderedDict()
            for r in sub:
                g.setdefault(r["tid"], []).append(r)
            v = my_layer_verdicts(g)
            rows.append({"L": i, "K": sum(1 for t in v if v[t]["verdict"]),
                         "nzs": [(v[t]["nz"], v[t]["nzero"]) for t in sorted(v)]})
        p, T, e0, ge, n_mc = my_mc(rows, n)
        lo, hi = IA.wilson_bounds(ge, n_mc)
        out["arm"][arm] = {
            "bands": tuple(len(s) for _l, s in bands),
            "K": tuple(r["K"] for r in rows),
            "T": T, "p": p,
            "rho": DC.spearman(fr, [DC.d_of(r) for r in ks]),
            "scope": DC.majority_count(ks),
            "state": "「检出」" if p < ALPHA else "「未检出」",
            "ge": ge, "n_mc": n_mc, "band": (lo, hi),
            "border": (lo <= ALPHA <= hi),
            "zero_cells": sum(z for r in rows for (_nz, z) in r["nzs"]),
            "n_traj_with_zero": sum(1 for r in rows for (_nz, z) in r["nzs"] if z > 0),
        }
    # ⚖ 判决（**本脚本自己**的口径：w 检出 且 rand 未检出 ⇒ 判决成立）
    pw = out["arm"]["w"]["p"]
    pr = out["arm"]["rand"]["p"]
    out["verdict"] = (pw < ALPHA) and (pr >= ALPHA)
    out["flip"] = not out["verdict"]
    return out


def main():
    rows_by_arm = {"w": VS.load_rows(JSONL_W), "rand": VS.load_rows(JSONL_RAND)}
    combos = list(itertools.product(QUANTILES, BAND_COUNTS, BOUNDARIES, ZERO_SPANS))

    # ⚖ 工具的实现（被对账的那一侧）
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dc2_probe", os.path.join(HERE, "dose_convention2_audit.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    allr = tool.build_all()
    by = {s["combo"]: s for s in allr["scenarios"]}

    n_bad = 0
    n_cmp = 0
    print("== 36 组合 × 2 臂 × 10 字段 的逐位对账 ==")
    for c in combos:
        mine = my_combo(rows_by_arm, c)
        theirs = by[c]
        for arm in ARMS:
            a = mine["arm"][arm]
            b = theirs["arm"][arm]
            want = {
                "bands": a["bands"],
                "K": a["K"],
                "T": a["T"],
                "p": a["p"],
                "rho": a["rho"],
                "scope": a["scope"],
                "state": a["state"],
                "zero_cells": a["zero_cells"],
                "band": a["band"],
                "border": a["border"],
            }
            got = {
                "bands": tuple(len(x[1]) for x in b["bands"]),
                "K": tuple(r["K"] for r in b["rows"]),
                "T": b["trend"]["T"],
                "p": b["trend"]["p"],
                "rho": b["rho"],
                "scope": b["scope_k"],
                "state": b["state"],
                "zero_cells": sum(z for r in b["rows"] for (_nz, z) in r["nzs"]),
                "band": b["trend"]["band"],
                "border": b["trend"]["border"],
            }
            for k in want:
                n_cmp += 1
                if want[k] != got[k]:
                    n_bad += 1
                    print("❌ %s / %s / %s：独立实现 %r ≠ 工具 %r"
                          % (c[0], c[1], arm, want[k], got[k]))
    print("   比较了 %d 个字段，不一致 %d 个 ⇒ %s"
          % (n_cmp, n_bad, "✅ 两份独立实现逐位一致" if n_bad == 0 else "🔴"))

    # ---- 判决口径的独立复算 ----
    n_vbad = 0
    for c in combos:
        mine = my_combo(rows_by_arm, c)
        pw = mine["arm"]["w"]["p"]
        pr = mine["arm"]["rand"]["p"]
        want = (pw < ALPHA) and (pr >= ALPHA)
        got = by[c]["verdict"]
        if want != got:
            n_vbad += 1
            print("❌ %s：独立判定 %s ≠ 工具 %s" % (c, want, got))
    print("   36 个组合的判决独立复算：不一致 %d 个 ⇒ %s"
          % (n_vbad, "✅" if n_vbad == 0 else "🔴"))

    # ---- 零假设语义的**独立**自证（244.65 的核心更正）----
    print("")
    print("== 零假设基准语义的独立自证 ==")
    n_sbad = 0
    base = my_combo(rows_by_arm, BASE_COMBO)
    for arm in ARMS:
        a = base["arm"][arm]
        print("  %-5s 臂基准组合：零格 %d 个（%d 条轨迹带零格）"
              % (arm, a["zero_cells"], a["n_traj_with_zero"]))
        # 逐条轨迹：有零格 ⇒ 新基准必须 ≠ 旧基准；无零格 ⇒ 必须逐位相同
        for L in range(len(base["arm"][arm]["K"])):
            g = collections.OrderedDict()
            ks, fr = my_dose_cells(rows_by_arm[arm], zero_span="keep")
            qs, bands = my_bands(ks, fr, "inclusive", 4, "prod")
            for r in bands[L][1]:
                g.setdefault(r["tid"], []).append(r)
            v = my_layer_verdicts(g)
            for tid in sorted(v):
                nz, nzero = v[tid]["nz"], v[tid]["nzero"]
                new_b = my_base(nz, nzero)
                old_b = my_base_old(nz + nzero)
                if nzero > 0:
                    good = (new_b != old_b)
                else:
                    good = (new_b == old_b)
                if not good:
                    n_sbad += 1
                    print("    ❌ %s 层 %d 轨迹 %s：基准 %r vs 旧写法 %r"
                          % (arm, L, tid, new_b, old_b))
        print("    ⇒ 零格处基准**必须**与旧写法不同；无零格处**必须**逐位相同：%s"
              % ("✅" if n_sbad == 0 else "🔴"))

    ok = (n_bad == 0 and n_vbad == 0 and n_sbad == 0)
    print("")
    print("总判决：%s" % ("✅ 三项独立对账全部通过" if ok else "🔴 有不一致"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
