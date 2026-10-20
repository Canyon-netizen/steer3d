#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_probe_24464_crosscheck.py —— 244.64 的**独立对账实现**（一次性探针）

⚖⚠⚖⚖ **本脚本自带分档器 + 自带 MC**（⛔ **不 import 待入库的口径实现**）
   ⇒ 它顺带就是**第二份独立实现**
   ⇒ 工具 `dose_convention2_audit.py` 若与本脚本逐位一致 ⇒ 两份独立实现互证。

⚖ **只复用「判据层」的机械**（沿用 244.63 的做法）：
   `dose_layer_audit.layer_verdicts`（层内多数）/ `cell_sign_p9`（格级符号）
   / `majority_base_p`（层内零假设基准）
   / `dose_confound_audit.d_of` / `frac_of` / `majority_count` / `spearman`
   / `verdict_source_audit.load_rows`（读数）
   ⚖⚠⚠ **不复用**：`dose_bands_v` / `dose_cells` / `mc_trend_p_geom`
   ⇒ 那三个正是本轮**新改过**的东西 ⇒ 必须由本脚本**自己**算。

⚖ 对账的字段（36 组合 × 2 臂）：档表 / 各档 K / 趋势 T / 趋势 p / rho /
   剂量轴口径多数 / 检出状态 —— **逐位**比较。

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

import dose_layer_audit as DL  # noqa: E402
import dose_confound_audit as DC  # noqa: E402
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


def my_mc(rows, n_layer):
    """⚖ 剂量趋势 MC（**本脚本自己**一份，层数可变）。"""
    e0 = [sum(DL.majority_base_p(nz) for nz in rows[L]["nzs"]) for L in range(n_layer)]
    w_off = (n_layer - 1) / 2.0
    t_obs = sum((L - w_off) * (rows[L]["K"] - e0[L]) for L in range(n_layer))
    rng = random.Random(MC_SEED)
    ge = 0
    for _ in range(N_MC):
        tot = 0.0
        for L in range(n_layer):
            k = 0
            for nz in rows[L]["nzs"]:
                npos = sum(1 for _ in range(nz) if rng.random() < 0.5)
                if npos * 2 > nz:
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
            v = DL.layer_verdicts(g, DL.cell_sign_p9)
            rows.append({"L": i, "K": sum(1 for t in v if v[t]["verdict"]),
                         "nzs": [v[t]["nz"] for t in sorted(v)]})
        p, T, e0, ge, n_mc = my_mc(rows, n)
        out["arm"][arm] = {
            "bands": tuple(len(s) for _l, s in bands),
            "K": tuple(r["K"] for r in rows),
            "T": T, "p": p,
            "rho": DC.spearman(fr, [DC.d_of(r) for r in ks]),
            "scope": DC.majority_count(ks),
            "state": "「检出」" if p < ALPHA else "「未检出」",
        }
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
    print("== 36 组合 × 2 臂 × 7 字段 的逐位对账 ==")
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
            }
            got = {
                "bands": tuple(len(x[1]) for x in b["bands"]),
                "K": tuple(r["K"] for r in b["rows"]),
                "T": b["trend"]["T"],
                "p": b["trend"]["p"],
                "rho": b["rho"],
                "scope": b["scope_k"],
                "state": b["state"],
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

    return 0 if (n_bad == 0 and n_vbad == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
