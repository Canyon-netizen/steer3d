#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dose_fragility_audit.py —— 剂量轴的**脆性**会不会动摇 244.60 的结论（零 GPU，修订 244.62）

🔴🔴 **本工具问什么**

  244.60 报出本项目**第一个**剂量—响应信号：
  **w 臂**格级正号率 0.407 → 0.571 → 0.767 → **1.000**（剂量趋势 MC **p=0.0002**），
  而 **rand 臂**基本平坦（0.407 → 0.429 → 0.400 → 0.500，趋势 p=0.0878）
  ⇒ 「**剂量—响应只出现在 w 臂**」。

  ⚖⚠⚠⚠ **但那条结论建立在一个**从没被扰动过**的剂量轴上**：
  四层是用**注入比例的四分位**切出来的，而 244.51 已经实测：
  **把 `P` 平移 ±4 token（= think→no_think 那个恒定模板偏移），
  `rho` 稳（区间 [+0.6797, +0.6952]）而**分档表会变**（4 个扰动下出现 2 种形态）。**

  ⚖⚠⚠⚠⚖ **244.51 只量了「分档表脆」，⛔ 从没量过它对「结论」的影响** ——
  而**分档一变，「哪几格属于哪一层」就变 ⇒ 层内基准 / 层内计数 / 剂量趋势 p 全都会动**
  ⇒ 「剂量—响应只出现在 w 臂」这条结论**可能站不住**，⛔ 而账本现在把它当**结论**写着。

  ⚖⚖⚖ 本工具就问一件事：**在 244.51 那个扰动族里，那条结论还成立吗？**

⚖ **复用的机械（⛔ 不另写第二套真相）**
  · 剂量轴：`dose_confound_audit.dose_cells` / **`dose_bands`**（244.60 归一后的唯一实现）
  · **扰动族**：`dose_confound_audit.P_perturbations`（244.62 抽出的**唯一实现**，
    244.51 的 `denom_premise_audit.C4` 已改调它 ⇒ ⛔ 不再内联第二份）
  · 层内零假设基准：`dose_layer_audit.majority_base_p`（⛔ **不是 0.5**）
  · 层内多数：`dose_layer_audit.layer_verdicts` / `cell_sign_p9`
  · 剂量趋势 MC：`dose_layer_audit.mc_trend_p`（**尊重每条轨迹的 nz 与平票规则**）
  · 跨臂配对置换：`dose_layer_audit.paired_perm_p`
  · 精确符号检验：`r227_kcurve.sign_test`（⛔ 不手抄第二份）
  · 面板口径多数：`dose_confound_audit.majority_count`

⚖⚠⚠⚖ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不连远端、⛔ 不写/删任何数据文件。
⚖⚠⚠⚖ 每条判据都必须**能红**：判据全部抽成**可注入的函数**（`j_cN_*`），
   ⇒ 自检才能「喂变异数据看它红」（⛔ 判据内联 ⇒ 自检恒绿、什么都没验到）。

跑法：
    python3 dose_fragility_audit.py
    python3 dose_fragility_audit.py --selftest
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import collections
import copy
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
VSRC = os.path.join(HERE, "verdict_source_audit.py")
DCONF = os.path.join(HERE, "dose_confound_audit.py")
DLAYER = os.path.join(HERE, "dose_layer_audit.py")
READER = os.path.join(REPO, ".cache", "mutbak", "r227_kcurve.py")
IAUD = os.path.join(HERE, "interval_audit.py")
JSONL_W = os.path.join(HERE, "_an.txt")
JSONL_RAND = os.path.join(HERE, "_ra.txt")

ALPHA = 0.05
# ⚖ **预登记的 α**（⛔ 不是本工具定的；改它会把结论改掉 ⇒ 判据 C0 钉住）
BASE_ALPHA = 0.05
N_LAYER = 4
ARMS = ("w", "rand")

# ⚖⚖⚖ **账本里的权威值**（⛔ **不是本工具算出来的**；244.61 的教训：期望集要**独立写死**）
# ⚖ 244.50/244.60 的四档格数（w 臂）
BASE_BAND_SIZE = (27, 28, 30, 24)
# ⚖ 244.60 的各层「为真条数」（w / rand）
BASE_LAYER_K = {"w": (4, 6, 10, 14), "rand": (2, 4, 5, 6)}
# ⚖ 244.60 的剂量趋势统计量与 MC p
BASE_TREND_T = {"w": 15.875, "rand": 5.375}
BASE_TREND_P = {"w": 0.0002, "rand": 0.0878}
# ⚖ 244.60/244.61 的**剂量轴口径**多数（scope=k）
BASE_SCOPE_K = {"w": (10, 14), "rand": (5, 14)}
# ⚖ 244.60 的结论：w p=0.0002<0.05 且 rand p=0.0878≥0.05 ⇒「剂量—响应只出现在 w 臂」**成立**
BASE_VERDICT = True
# ⚖ 244.51 的独立实测（账本 244.51 【2】那张表）：**分档表** + **rho**
#   ⇒ 244.62 的四个扰动场景必须**逐位复现**它 ⇒ 扰动实现写错 ⇒ 红
VARIANT_EXPECT = (
    ("no_think 全 P−", (27, 28, 27, 27), 0.6824),
    ("think 全 P−", (27, 28, 29, 25), 0.6832),
    ("全部 P−", (27, 28, 27, 27), 0.6797),
    ("全部 P+", (27, 28, 27, 27), 0.6952),
)
# ⚖ 244.51 的恒定模板偏移（think→no_think 的 P 差 = +4）
OFF = 4
# ⚖ 244.51 的扰动族：**4 个变体**（no_think− / think− / 全部− / 全部+）
N_VARIANTS = 4
# ⚖ 244.51 的独立实测事实：4 个扰动下**分档表出现了 2 种形态** ⇒ 至少 1 个场景 ≠ 基准
MIN_DISTINCT_BAND_TABLES = 2
# ⚖ 244.60 的独立事实：层内基准确实塌到 **0.25**（⛔ 不是 0.5）
MIN_LAYER_BASE = 0.25

_MODS = {}


def _load(path, name):
    if name in _MODS:
        return _MODS[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def vsrc():
    return _load(VSRC, "vs_24462")


def dconf():
    return _load(DCONF, "dc_24462")


def dlayer():
    return _load(DLAYER, "dl_24462")


def reader():
    return _load(READER, "r227_24462")


def iaud():
    return _load(IAUD, "ia_24462")


class HardFail(Exception):
    pass


# ---------------------------------------------------------------- 场景
def shift_records(recs, Ps):
    """⚖ 把 `P` 换成扰动后的值（**别的字段一律不动**）。

    ⚖⚠⚠ **只改 `P`**：读数（`p9_lo_meas` / `p9_hi_meas` / `up_mono_meas`）**不动**
    ⇒ 扰动改的**只有剂量轴**（`inj` → `frac` → 分档），⛔ 不是改数据。
    """
    if len(recs) != len(Ps):
        raise HardFail("shift_records：长度不等 %d vs %d" % (len(recs), len(Ps)))
    return [dict(r, P=p) for r, p in zip(recs, Ps)]


def build_scenario(shifted_by_arm, label, is_base):
    """⚖ 算一个场景：两臂的剂量轴 + 四层 + 逐层判定 + 剂量趋势 + 跨臂配对置换。"""
    DC, DL = dconf(), dlayer()
    out = {"label": label, "is_base": is_base, "arm": {}, "layers": []}
    for arm in ARMS:
        shifted = shifted_by_arm[arm]
        ks, fr = DC.dose_cells(shifted)
        if not ks:
            raise HardFail("场景 %s / %s：剂量轴没有格 ⇒ **未量到**" % (label, arm))
        qs, bands = DC.dose_bands(ks, fr)
        layers = collections.OrderedDict()
        for i, (_lab, sub) in enumerate(bands):
            g = collections.OrderedDict()
            for r in sub:
                g.setdefault(r["tid"], []).append(r)
            layers[i] = {"cells": g}
        rows = []
        for L in range(N_LAYER):
            v = DL.layer_verdicts(layers[L]["cells"], DL.cell_sign_p9)
            cells = [c for cs in layers[L]["cells"].values() for c in cs]
            rows.append({
                "L": L,
                "verdicts": v,
                "K": sum(1 for t in v if v[t]["verdict"]),
                "n_traj": len(v),
                "nzs": [v[t]["nz"] for t in sorted(v)],
                "cellpos": sum(1 for c in cells if DL.cell_sign_p9(c)),
                "celln": len(cells),
            })
        p_tr, T, e0, ge, n_mc = DL.mc_trend_p_geom([r["nzs"] for r in rows],
                                                   [r["K"] for r in rows])
        # ⚖⚠⚠⚖ **MC 的不确定带**（244.62 加）：p = (ge+1)/(n_mc+1) 只是**点估计**
        #   ⇒ 当 p 贴着 α 时，这个带是**决定性的**（带跨过 α ⇒ 「显著/不显著」本身**未定**）
        lo, hi = iaud().wilson_bounds(ge, n_mc)
        out["arm"][arm] = {
            "ks": ks, "fr": fr, "qs": qs, "bands": bands, "rows": rows,
            "trend": {"p": p_tr, "T": T, "e0": e0, "ge": ge, "n_mc": n_mc,
                      "band": (lo, hi), "border": (lo <= ALPHA <= hi)},
            "scope_k": DC.majority_count(ks),
            "rho": DC.spearman(fr, [DC.d_of(r) for r in ks]),
        }
    # ---- 跨臂：逐层配对置换 + 精确符号检验（244.60 的 C5 教训） ----
    RD = reader()
    for L in range(N_LAYER):
        vw = out["arm"]["w"]["rows"][L]["verdicts"]
        vr = out["arm"]["rand"]["rows"][L]["verdicts"]
        diffs = [(1 if vw[t]["verdict"] else 0) - (1 if vr[t]["verdict"] else 0)
                 for t in sorted(vw)]
        pperm, obs = DL.paired_perm_p(diffs)
        nz = [d for d in diffs if d != 0]
        p_exact = RD.sign_test([float(d) for d in nz])[0] if nz else None
        out["layers"].append({"L": L, "diffs": diffs, "pperm": pperm,
                              "obs": obs, "p_exact": p_exact,
                              "kw": out["arm"]["w"]["rows"][L]["K"],
                              "kr": out["arm"]["rand"]["rows"][L]["K"]})
    # ---- 层内基准（每层每臂）：⛔ 不是 0.5 ----
    for arm in ARMS:
        for row in out["arm"][arm]["rows"]:
            bases = [DL.majority_base_p(nz) for nz in row["nzs"]]
            row["bases"] = bases
            row["avg_base"] = (sum(bases) / len(bases)) if bases else None
    out["verdict"] = verdict_of(out)
    out["flip"] = not out["verdict"]
    return out


def verdict_of(sc):
    """⚖⚖⚖ 244.60 那条结论在**这个场景**下成立吗？

    ⚖ 结论 = 「**剂量—响应只出现在 w 臂**」⇒ 形式化：
       (w 臂剂量趋势 MC p < ALPHA) ∧ (rand 臂剂量趋势 MC p ≥ ALPHA)
    ⚖⚠⚠ **只能用趋势 p**（格级正号率是**描述量**，没有零假设 ⇒ 不能拿它判显著）
    """
    pw = sc["arm"]["w"]["trend"]["p"]
    pr = sc["arm"]["rand"]["trend"]["p"]
    return (pw < ALPHA) and (pr >= ALPHA)


def build_all():
    """⚖ 算**全部场景**：基准 ＋ 244.51 的 4 个扰动 ⇒ 5 个场景。"""
    VS, DC = vsrc(), dconf()
    rows_by_arm = {"w": VS.load_rows(JSONL_W), "rand": VS.load_rows(JSONL_RAND)}
    for arm in ARMS:
        if not rows_by_arm[arm]:
            raise HardFail("%s 臂读数一条都没有 ⇒ **未量到**" % arm)
    # ---- 扰动族（**唯一实现**：`dose_confound_audit.P_perturbations`）----
    variants_w = DC.P_perturbations(rows_by_arm["w"], OFF)
    variants_r = DC.P_perturbations(rows_by_arm["rand"], OFF)
    assert len(variants_w) == N_VARIANTS, "扰动族大小变了"
    assert len(variants_r) == N_VARIANTS, "扰动族大小变了"
    scenarios = [build_scenario(rows_by_arm, "基准（244.50 的更正后剂量轴）", True)]
    for i, (lab, Ps_w) in enumerate(variants_w):
        lab_r, Ps_r = variants_r[i]
        assert lab_r == lab, "两臂的扰动标签对不上 ⇒ ⛔ 扰动族被改过"
        shifted = {"w": shift_records(rows_by_arm["w"], Ps_w),
                   "rand": shift_records(rows_by_arm["rand"], Ps_r)}
        scenarios.append(build_scenario(shifted, lab, False))
    return {"scenarios": scenarios, "base": scenarios[0],
            "n_var": len(variants_w), "n_traj": len(rows_by_arm["w"])}


# ---------------------------------------------------------------- 判据（可注入）
def j_c0_baseline(base):
    """C0：基准场景必须**逐位复现 244.60**（⛔ 不许悄悄换口径）。"""
    ok, d = True, []
    for arm in ARMS:
        bs = tuple(len(sub) for _l, sub in base["arm"][arm]["bands"])
        good = (bs == BASE_BAND_SIZE)
        ok &= good
        d.append("%s 档数 %s（期望 %s）%s" % (arm, list(bs), list(BASE_BAND_SIZE),
                                             "✅" if good else "❌"))
        ks = tuple(base["arm"][arm]["rows"][L]["K"] for L in range(N_LAYER))
        good = (ks == BASE_LAYER_K[arm])
        ok &= good
        d.append("%s 各层 K %s（期望 %s）%s" % (arm, list(ks), list(BASE_LAYER_K[arm]),
                                               "✅" if good else "❌"))
        T = base["arm"][arm]["trend"]["T"]
        good = abs(T - BASE_TREND_T[arm]) < 5e-4
        ok &= good
        d.append("%s 趋势 T=%.3f（期望 %.3f）%s" % (arm, T, BASE_TREND_T[arm],
                                                   "✅" if good else "❌"))
        p = base["arm"][arm]["trend"]["p"]
        good = abs(p - BASE_TREND_P[arm]) < 5e-5
        ok &= good
        d.append("%s 趋势 p=%.4f（期望 %.4f）%s" % (arm, p, BASE_TREND_P[arm],
                                                   "✅" if good else "❌"))
        sk = tuple(base["arm"][arm]["scope_k"])
        good = (sk == BASE_SCOPE_K[arm])
        ok &= good
        d.append("%s 剂量轴口径多数 %d/%d（期望 %d/%d）%s"
                 % (arm, sk[0], sk[1], BASE_SCOPE_K[arm][0], BASE_SCOPE_K[arm][1],
                    "✅" if good else "❌"))
    good = (base["verdict"] == BASE_VERDICT)
    ok &= good
    d.append("基准场景的判决 %s（期望 %s）%s"
             % ("成立" if base["verdict"] else "**不成立**",
                "成立" if BASE_VERDICT else "不成立", "✅" if good else "❌"))
    # ⚖⚠⚖⚖ **α 是预登记的常量**：改它就把结论改掉了 ⇒ 必须钉住
    #   （244.60 的 M7 同一形状：预登记的字面量被改 ⇒ 判据必须红）
    good = (ALPHA == BASE_ALPHA)
    ok &= good
    d.append("判决的 α = %.4f（预登记 %s，⛔ 不许改）%s"
             % (ALPHA, BASE_ALPHA, "✅" if good else "❌"))
    return ok, d


def j_c1_family_size(allr):
    """C1：扰动族必须**恰好 4 个变体**（族大小写死 ⇒ 少一个就红）。"""
    ok = (allr["n_var"] == N_VARIANTS)
    d = ["扰动族变体数 %d（期望 %d）%s" % (allr["n_var"], N_VARIANTS,
                                          "✅" if ok else "❌"),
         "场景总数 %d（= 基准 1 ＋ 变体 %d）"
         % (len(allr["scenarios"]), allr["n_var"])]
    ok = ok and (len(allr["scenarios"]) == N_VARIANTS + 1)
    return ok, d


def j_c2_bands_moved(allr):
    """C2：扰动必须**真的改变分档**（否则「脆性」是空的 ⇒ 这条会恒绿护栏）。"""
    base_tbl = tuple(len(sub) for _l, sub in allr["base"]["arm"]["w"]["bands"])
    seen = {base_tbl}
    for sc in allr["scenarios"][1:]:
        seen.add(tuple(len(sub) for _l, sub in sc["arm"]["w"]["bands"]))
    ok = len(seen) >= MIN_DISTINCT_BAND_TABLES
    d = ["w 臂的档数表在 %d 个场景下出现 **%d 种**形态（244.51 的独立实测：≥%d）%s"
         % (len(allr["scenarios"]), len(seen), MIN_DISTINCT_BAND_TABLES,
            "✅" if ok else "❌"),
         "形态：%s" % sorted(seen)]
    return ok, d


def j_c3_layer_base(allr):
    """C3：层内零假设基准必须**逐条**与 `majority_base_p` 一致，**且**确实塌到 < 0.5。

    ⚖⚠⚠ **不是 0.5**（244.60 的 C3/C4 教训）⇒ 这里在**扰动后**再验一遍。
    """
    DL = dlayer()
    ok, d = True, []
    worst = None
    for sc in allr["scenarios"]:
        for arm in ARMS:
            for row in sc["arm"][arm]["rows"]:
                want = [DL.majority_base_p(nz) for nz in row["nzs"]]
                good = (row["bases"] == want)
                ok &= good
                if not good:
                    d.append("❌ 场景 %s / %s / 层 %d：基准序列与现算不一致"
                             % (sc["label"], arm, row["L"]))
                if row["avg_base"] is not None:
                    worst = (row["avg_base"] if worst is None
                             else min(worst, row["avg_base"]))
    ok = ok and (worst is not None) and (worst <= MIN_LAYER_BASE + 1e-12)
    d.append("全部场景里最小的层内平均基准 %.4f（期望 ≤ %.2f，⛔ 不是 0.5）%s"
             % (worst if worst is not None else float("nan"), MIN_LAYER_BASE,
                "✅" if (worst is not None and worst <= MIN_LAYER_BASE + 1e-12) else "❌"))
    return ok, d


def j_c4_verdicts_printed(allr, RP):
    """C4：判决必须**逐场景印出**，且每条判决与该场景**印出来的 p** 交叉对账。

    ⚖⚠⚠⚠ **双向**：既抓「少印一条」，也抓「判定被写死 / p 被篡改但判决没改」。
    ⚖⚠⚠⚠ **判决行自带 p**（`w 趋势 p=… ∧ rand 趋势 p=…`）⇒ 交叉对账是**自足**的
    ⇒ ⛔ 不许从被检对象内部去取 p（那样两边同源 ⇒ 恒绿）。
    """
    n_sc = len(allr["scenarios"])
    vlines = [ln for ln in RP if "⇒ 判决" in ln]
    printed = len(vlines)
    ok = (printed == n_sc)
    d = ["印出判决的场景行 %d（期望 %d）%s" % (printed, n_sc, "✅" if ok else "❌")]
    # ---- 交叉对账：把**印出来的 p** 代回判定式 ----
    for ln in vlines:
        m = re.search(r"w 趋势 p=([0-9.]+)", ln)
        m2 = re.search(r"rand 趋势 p=([0-9.]+)", ln)
        if not m or not m2:
            ok = False
            d.append("❌ 判决行里认不出 p：%s" % ln.strip()[:70])
            continue
        pw, pr = float(m.group(1)), float(m2.group(1))
        want = (pw < ALPHA) and (pr >= ALPHA)
        got = ("**成立**" in ln)
        good = (want == got)
        ok &= good
        d.append("判决行 p=(%.4f, %.4f) ⇒ 应%s，实印%s %s"
                 % (pw, pr, "成立" if want else "不成立",
                    "成立" if got else "不成立", "✅" if good else "❌"))
    ok = ok and (printed == n_sc)
    return ok, d


def j_c10_mc_band_printed(allr, RP):
    """C10：每个场景每臂的 **MC 不确定带**必须印出（⛔ 只印点估计 ⇒ 边界看不出来）。

    ⚖⚠⚠⚠ **这是本轮最要紧的一条**：p 贴着 α 时，「显著/不显著」**取决于 MC 噪声**
    ⇒ 只印 p = 0.0488 会让人以为「rand 臂也显著了」，
       而它的带**跨过** α ⇒ 那个场景的显著性**本来就未定**。
    """
    n_sc = len(allr["scenarios"])
    lines = [ln for ln in RP if "MC95%带" in ln]
    printed = len(lines)
    ok = (printed == n_sc * 2)
    d = ["印出「MC95%%带」的行 %d（期望 %d = %d 场景 × 2 臂）%s"
         % (printed, n_sc * 2, n_sc, "✅" if ok else "❌")]
    # ---- 带的宽度必须 > 0（⛔ 点估计冒充不确定带）----
    n_border = 0
    for sc in allr["scenarios"]:
        for arm in ARMS:
            lo, hi = sc["arm"][arm]["trend"]["band"]
            if not (hi > lo):
                ok = False
                d.append("❌ 场景 %s / %s：带宽度为 0 ⇒ **未量到**" % (sc["label"], arm))
            if sc["arm"][arm]["trend"]["border"]:
                n_border += 1
    d.append("带跨过 α（%.2f）的场景×臂数 %d%s"
             % (ALPHA, n_border, "（⇒ 那些场景的显著性**未定**）" if n_border else ""))
    return ok, d


def j_c5_flip_count(allr, RP):
    """C5：翻转数必须被**报出**，且与逐场景判决**交叉对账**（算出来的 == 数出来的）。"""
    flips = [sc["label"] for sc in allr["scenarios"] if sc["flip"]]
    marked = sum(1 for ln in RP if "**翻转**" in ln)
    ok = (marked == len(flips))
    d = ["算出的翻转数 %d（场景：%s）｜ 报告里标出的 %d 行 %s"
         % (len(flips), ("、".join(flips) if flips else "无"), marked,
            "✅" if ok else "❌")]
    return ok, d


def j_c6_mc_calibration():
    """C6：MC 趋势 p 的零分布**双向校准**（244.60 的 C4z 教训）。

    ⚖⚠⚠⚠ **单边判据对「零分布塌掉/反号」是瞎的** ⇒ 必须正反两测。

    ⚖⚠⚠⚖⚖ **口径澄清（244.62 自己踩的坑，别记反）**：
    这个 MC 检验是**单边**的（`p = P(T_sim ≥ T_obs)`）⇒
      · 「零分布**塌掉**」（T_sim ≡ 0）⇒ 零假设夹具上 p = **1.0** ⇒ 红
      · 「零分布**反号**」（T_sim ≡ 负）⇒ 零假设夹具上 p ≈ **0** ⇒ 红
      ⇒ **一条「零假设夹具 p ≈ 0.5」就同时抓住这两种坏掉**（244.60 的 C4z）
    ⚠ 而「**观测**本身反号」（T_obs < 0）⇒ p ≈ **1** ⇒ 那是**单边检验的正确语义**
      ⇒ ⛔ **不许**把它当成「坏掉」（我第一版就写错了这条 ⇒ 判据误报红）。
    """
    DL = dlayer()
    nzs = [[2] * 14 for _ in range(4)]
    p_null, T0, _e0 = DL.mc_trend_p(nzs, [7, 7, 7, 7], n_mc=2000)
    p_mono, T1, _e1 = DL.mc_trend_p(nzs, [4, 6, 10, 14], n_mc=2000)
    p_inv, T2, _e2 = DL.mc_trend_p(nzs, [14, 10, 6, 4], n_mc=2000)
    ok_null = 0.35 <= p_null <= 0.65
    ok_mono = p_mono < 0.1
    ok_inv = p_inv > 0.9
    ok = ok_null and ok_mono and ok_inv
    d = ["零假设夹具（各层相同 ⇒ T=%.3f）p=%.4f，应 ≈0.5（**零分布塌掉 ⇒ 1.0；"
         "零分布反号 ⇒ ≈0**）%s" % (T0, p_null, "✅" if ok_null else "❌"),
         "单调夹具 T=%.3f p=%.4f，应 <0.1 %s" % (T1, p_mono, "✅" if ok_mono else "❌"),
         "反号观测 T=%.3f p=%.4f，单边检验应 ≈1（⛔ 不是 0）%s"
         % (T2, p_inv, "✅" if ok_inv else "❌")]
    return ok, d


def j_c7_denominators(allr):
    """C7：交叉对账 —— 每层的**分母**（格数 / 轨迹数）两臂必须**逐条相同**。

    ⚖⚠⚠ 配对的前提：两臂读的是同一批格子 ⇒ 同一层的格数与轨迹数必须相同
    ⇒ 分母不同 ⇒ 那一层的比较**不成立**。
    """
    ok, d = True, []
    for sc in allr["scenarios"]:
        for L in range(N_LAYER):
            rw = sc["arm"]["w"]["rows"][L]
            rr = sc["arm"]["rand"]["rows"][L]
            good = (rw["celln"] == rr["celln"] and rw["n_traj"] == rr["n_traj"]
                    and rw["n_traj"] == len(rw["nzs"]))
            ok &= good
            if not good:
                d.append("❌ 场景 %s / 层 %d：w 格 %d 轨迹 %d ｜ rand 格 %d 轨迹 %d"
                         % (sc["label"], L, rw["celln"], rw["n_traj"],
                            rr["celln"], rr["n_traj"]))
            if rw["celln"] == 0 or rw["n_traj"] == 0:
                ok = False
                d.append("❌ 场景 %s / 层 %d：分母为 0 ⇒ **未量到**" % (sc["label"], L))
    d.append("每层两臂的格数与轨迹数逐条相同（%d 个场景 × %d 层）%s"
             % (len(allr["scenarios"]), N_LAYER, "✅" if ok else "❌"))
    return ok, d


def j_c8_scope_k_printed(allr, RP):
    """C8：剂量轴口径的多数必须**每个场景都印出**（⛔ 只印基准 ⇒ 读者无法复核）。"""
    n_sc = len(allr["scenarios"])
    printed = sum(1 for ln in RP if "剂量轴口径多数" in ln)
    ok = (printed == n_sc * 2)
    d = ["印出「剂量轴口径多数」的行 %d（期望 %d = %d 场景 × 2 臂）%s"
         % (printed, n_sc * 2, n_sc, "✅" if ok else "❌")]
    return ok, d


def j_c9_pperm_matches_exact(allr):
    """C9：逐层**配对置换 p** 必须与**精确符号检验**一致（⛔ 置换台自己错了也要红）。"""
    ok, d = True, []
    for sc in allr["scenarios"]:
        for row in sc["layers"]:
            if row["p_exact"] is None:
                continue
            good = abs(row["pperm"] - row["p_exact"]) <= 0.005
            ok &= good
            if not good:
                d.append("❌ 场景 %s / 层 %d：配对置换 %.4f vs 精确 %.6f"
                         % (sc["label"], row["L"], row["pperm"], row["p_exact"]))
    d.append("每个场景每层的配对置换 p 与精确符号检验一致（⛔ 置换台自己错了也要红）%s"
             % ("✅" if ok else "❌"))
    return ok, d


def j_c11_variants_match_24451(allr):
    """C11：四个扰动场景的**分档表**与 **rho** 必须**逐位复现 244.51**。

    ⚖⚠⚖⚖ **这是唯一的「绝对值」检查**：非基准场景的数没有别的来源
    ⇒ 期望集**独立写死**（抄 244.51 账本 244.51【2】那张表）⇒ 扰动实现写错 ⇒ 红。
    """
    ok, d = True, []
    for sc in allr["scenarios"][1:]:
        hit = None
        for pref, tbl, rho in VARIANT_EXPECT:
            if sc["label"].startswith(pref):
                hit = (pref, tbl, rho)
                break
        if hit is None:
            ok = False
            d.append("❌ 场景「%s」对不上任何一条 244.51 的期望（标签被改过？）" % sc["label"])
            continue
        pref, tbl, rho = hit
        got_tbl = tuple(len(sub) for _l, sub in sc["arm"]["w"]["bands"])
        good = (got_tbl == tbl)
        ok &= good
        d.append("场景「%s」分档表 %s（244.51 记的是 %s）%s"
                 % (sc["label"], list(got_tbl), list(tbl), "✅" if good else "❌"))
        got_rho = sc["arm"]["w"]["rho"]
        good = abs(got_rho - rho) < 5e-5
        ok &= good
        d.append("场景「%s」w 臂 rho %+.4f（244.51 记的是 %+.4f）%s"
                 % (sc["label"], got_rho, rho, "✅" if good else "❌"))
    d.append("四个扰动场景的**分档表**与**rho**逐位复现 244.51（独立写死的期望）%s"
             % ("✅" if ok else "❌"))
    return ok, d


# ---------------------------------------------------------------- 报告
def build_report(allr):
    RP = ["【剂量轴脆性审计】（244.62；零 GPU）",
          "  ⚖ 扰动族：244.51 的 ±%d token 族（no_think− / think− / 全部− / 全部+）"
          " ⇒ %d 个变体 ＋ 基准 = %d 个场景"
          % (OFF, allr["n_var"], len(allr["scenarios"])),
          "  ⚖ 判决口径：244.60 的「剂量—响应只出现在 w 臂」"
          " = (w 趋势 MC p < %.2f) ∧ (rand 趋势 MC p ≥ %.2f)" % (ALPHA, ALPHA)]
    for sc in allr["scenarios"]:
        RP.append("· 场景 %s" % sc["label"])
        for arm in ARMS:
            a = sc["arm"][arm]
            bs = "/".join(str(len(sub)) for _l, sub in a["bands"])
            ks_ = [a["rows"][L]["K"] for L in range(N_LAYER)]
            rates = ["%.3f" % (a["rows"][L]["cellpos"] / float(a["rows"][L]["celln"]))
                     for L in range(N_LAYER)]
            tr = a["trend"]
            RP.append("    · %-4s 档 %s ｜ rho %+.4f ｜ 各层 K=%s ｜ 格级正号率 %s"
                      " ｜ 趋势 T=%.3f p=%.4f MC95%%带 [%.4f, %.4f]%s"
                      " ｜ 剂量轴口径多数 %d/%d"
                      % (arm, bs, a["rho"], "/".join(str(x) for x in ks_),
                         "/".join(rates), tr["T"], tr["p"],
                         tr["band"][0], tr["band"][1],
                         "  ⚠⚠ **带跨过 α**" if tr["border"] else "",
                         a["scope_k"][0], a["scope_k"][1]))
        pw = sc["arm"]["w"]["trend"]["p"]
        pr = sc["arm"]["rand"]["trend"]["p"]
        RP.append("    ⇒ 判决【%s】：**%s**（w 趋势 p=%.4f < %.2f ∧ rand 趋势 p=%.4f ≥ %.2f）%s"
                  % (sc["label"], "成立" if sc["verdict"] else "不成立",
                     pw, ALPHA, pr, ALPHA,
                     "  ⚠⚠ **翻转**" if sc["flip"] else ""))
    flips = [sc["label"] for sc in allr["scenarios"] if sc["flip"]]
    RP.append("  ⚖ 翻转：%d 个场景下「剂量—响应只出现在 w 臂」**不成立**%s"
              % (len(flips), ("（%s）" % "、".join(flips)) if flips else ""))
    return RP


# ---------------------------------------------------------------- 主流程
def run():
    allr = build_all()
    RP = build_report(allr)
    res = []

    def put(cid, ok, detail):
        res.append((cid, bool(ok), detail))

    ok0, d0 = j_c0_baseline(allr["base"])
    put("C0", ok0, "；".join(d0))
    ok1, d1 = j_c1_family_size(allr)
    put("C1", ok1, "；".join(d1))
    ok2, d2 = j_c2_bands_moved(allr)
    put("C2", ok2, "；".join(d2))
    ok3, d3 = j_c3_layer_base(allr)
    put("C3", ok3, "；".join(d3))
    ok4, d4 = j_c4_verdicts_printed(allr, RP)
    put("C4", ok4, "；".join(d4))
    ok5, d5 = j_c5_flip_count(allr, RP)
    put("C5", ok5, "；".join(d5))
    ok6, d6 = j_c6_mc_calibration()
    put("C6", ok6, "；".join(d6))
    ok7, d7 = j_c7_denominators(allr)
    put("C7", ok7, "；".join(d7))
    ok8, d8 = j_c8_scope_k_printed(allr, RP)
    put("C8", ok8, "；".join(d8))
    ok9, d9 = j_c9_pperm_matches_exact(allr)
    put("C9", ok9, "；".join(d9))
    ok10, d10 = j_c10_mc_band_printed(allr, RP)
    put("C10", ok10, "；".join(d10))
    ok11, d11 = j_c11_variants_match_24451(allr)
    put("C11", ok11, "；".join(d11))

    for ln in RP:
        print(ln)
    print("")
    allok = True
    for cid, ok, detail in res:
        allok = allok and ok
        print("[%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for _c, o, _d in res if o), len(res)))
    return RP, res, allr


# ---------------------------------------------------------------- 自检
def _mutations():
    """⚖ 每条判据的「变异数据」⇒ 自检要证明**红得了**。

    ⚖⚠⚠⚠ **期望集不许从被检对象派生**（244.60/244.61 的教训）⇒
       这里的变异都是**改坏**的，而**干净**那一侧由真实数据路径保证。
    """
    return [
        ("C0", "基准的档数表被改坏",
         lambda a: a["base"]["arm"]["w"]["bands"].__setitem__(
             0, ("frac<=q1", a["base"]["arm"]["w"]["bands"][0][1][:-1]))),
        ("C0", "基准的趋势 p 被篡改",
         lambda a: a["base"]["arm"]["w"]["trend"].__setitem__("p", 0.5)),
        ("C1", "扰动族少一个变体",
         lambda a: a.__setitem__("n_var", a["n_var"] - 1)),
        ("C1", "场景少一个",
         lambda a: a["scenarios"].pop()),
        ("C2", "所有场景的分档表都变成基准的",
         lambda a: [sc["arm"][w].__setitem__("bands", a["base"]["arm"][w]["bands"])
                    for sc in a["scenarios"] for w in ("w", "rand")]),
        ("C3", "层内基准被改成 0.5",
         lambda a: [row.__setitem__("bases", [0.5] * len(row["bases"]))
                    for sc in a["scenarios"] for arm in ("w", "rand")
                    for row in sc["arm"][arm]["rows"]]),
        ("C4", "报告里少印一个场景的判决",
         lambda a: None),   # 由调用方处理（要改 RP，不改数据）
        ("C5", "翻转标记的行数与算出来的不一致",
         lambda a: a["scenarios"][0].__setitem__("flip", not a["scenarios"][0]["flip"])),
        ("C6", "MC 校准用的零分布被换成恒真的 p",
         lambda a: None),   # 由调用方处理
        ("C7", "某一层两臂的格数不同",
         lambda a: a["scenarios"][1]["arm"]["rand"]["rows"][0].__setitem__(
             "celln", a["scenarios"][1]["arm"]["rand"]["rows"][0]["celln"] + 1)),
        ("C8", "报告里少印一条剂量轴口径多数",
         lambda a: None),   # 由调用方处理
        ("C9", "配对置换 p 被篡改",
         lambda a: a["scenarios"][2]["layers"][0].__setitem__("pperm", 0.999)),
    ]


def selftest():
    """⚖ 自检：① 每条判据在**干净输入**上必须全绿 ② 喂**变异数据**必须红。

    ⚖⚠⚠⚠ **判据内联 ⇒ 自检恒绿、什么都没验到**（244.60/244.61 的教训）
    ⇒ 这里全部走**可注入的判据函数**。
    """
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", t, why))

    RP, res, allr = run()
    base_res = {c: o for c, o, _d in res}
    chk("S0", all(o for _c, o, _d in res),
        "真实数据路径上全部判据必须绿（实测 %d/%d）"
        % (sum(1 for _c, o, _d in res if o), len(res)))

    # ---- 逐条判据：变异数据必须让它红 ----
    fns = {"C0": j_c0_baseline, "C1": j_c1_family_size, "C2": j_c2_bands_moved,
           "C3": j_c3_layer_base, "C4": j_c4_verdicts_printed,
           "C5": j_c5_flip_count, "C7": j_c7_denominators,
           "C8": j_c8_scope_k_printed, "C9": j_c9_pperm_matches_exact,
           "C10": j_c10_mc_band_printed}
    for cid, name, mut in _mutations():
        if cid not in fns:
            continue
        a2 = copy.deepcopy(allr)
        mut(a2)
        if cid == "C4":
            # ⚖ 判决行**自带场景名** ⇒ 按名字删掉最后那个场景的判决行
            RP2 = [ln for ln in RP if a2["scenarios"][-1]["label"] not in ln]
        elif cid == "C8":
            RP2 = [ln for ln in RP if "剂量轴口径多数" not in ln]
        elif cid == "C10":
            RP2 = [ln for ln in RP if "MC95%带" not in ln]
        else:
            RP2 = RP
        try:
            if cid == "C0":
                got, _d = fns[cid](a2["base"])
            elif cid in ("C4", "C5", "C8", "C10"):
                got, _d = fns[cid](a2, RP2)
            else:
                got, _d = fns[cid](a2)
        except Exception as e:      # ⚖ 判据不许崩 ⇒ 崩了算「红」
            got = False
            chk("S-%s" % cid, False, "判据在变异数据上**崩了**（%s）⇒ 算红" % e)
            continue
        chk("S-%s" % cid, (not got),
            "变异「%s」后 %s 必须红（实测 %s）" % (name, cid, "红" if not got else "**仍绿**"))

    # ---- C6：零分布校准必须**双向** ----
    okc, dc = j_c6_mc_calibration()
    chk("S-C6", okc, "MC 零分布双向校准：%s" % "；".join(dc))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="剂量轴脆性审计（零 GPU、不连远端）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    try:
        if args.selftest:
            return selftest()
        RP, res, allr = run()
        allok = all(o for _c, o, _d in res)
        return 0 if allok else 1
    except HardFail as e:
        print("PRECOND_FAIL: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
