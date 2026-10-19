#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_cell_census.py —— **判决面板每一格的来源普查**（修订 244.57，零 GPU）

🔴🔴 **本工具问什么**

  同一个「手抄格」的风险已经咬了**两次**：
  · 244.55 在判决清单上逮到「轨迹级 rand 5/9 p=**1.00000**」⇒ 撤回并更正
  · 244.56 把那十行**逐行**重算 ⇒ 证明**其余九行全对**

  ⇒ 结论：**「手抄」本身不是缺陷，「没人重算过」才是**。
  ⇒ 本工具把**要展示给用户的每一个数**逐格清点：
  「这个数**有人独立重算过**吗？重算的值是多少？和账本印的一样吗？」

⚖⚖⚖ **本工具要产出的三样东西**

  ① **逐格对账表**：面板每一格 =（账本印的值 ｜ 独立重算的值 ｜ 状态）
  ② **「只有手抄」清单**：⚠ 那些**没有人独立重算过**的格（⛔ 不许混进「已核」）
  ③ **元判据 C5**：⛔ **任何一格都不许被标成「已核」而其实没有独立重算**

⚖⚖⚖ **重算一律走既有生产机械**（⛔ 不另写一套 ⇒ 不制造第二套真相）
  `verdict_source_audit.derive_arm` / `extract_verdicts`
  `layer_row_audit.derive_from_logs` / `derive_prereg_fisher`
  `dose_axis_audit.within_mech` / `mechanism_step` / `med`
  `dose_confound_audit.frac_of` / `d_of` / `spearman`
  `headroom_audit.one_cell_ratio` / `sb` / `cells_to_alpha`

⚖⚠⚠⚖ 本工具⛔ 不发批、⛔ 不改探针、⛔ 不连远端、⛔ 不写/删任何数据文件。
⚖⚠⚖ 每条判据都必须**能红**：自检用畸形夹具证明「红得了」，
  变异台（`mut_ledger_cell_census.py`）在**源码层**证明「红得了」。

跑法：
    python3 ledger_cell_census.py
    python3 ledger_cell_census.py --selftest
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import collections
import importlib.util
import io
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

_MODS = {}


def _load(path, name):
    if not os.path.isfile(path):
        raise SystemExit("PRECOND_FAIL: 找不到 %s" % path)
    if name in _MODS:
        return _MODS[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def _mod(fname, name):
    return _load(os.path.join(HERE, fname), name)


def vs():
    return _mod("verdict_source_audit.py", "vsa_census")


def lra():
    return _mod("layer_row_audit.py", "lra_census")


def dax():
    return _mod("dose_axis_audit.py", "dax_census")


def dca():
    return _mod("dose_confound_audit.py", "dca_census")


def hra():
    return _mod("headroom_audit.py", "hra_census")


def avm():
    return _mod("arm_verdict.py", "av_census")


# ---------------------------------------------------------------- 账本印的值
# ⚖ 这些是**账本里印的**（引用，⛔ 不是本工具算出来的）
#   轨迹级：244.9.2 ｜ 预登记：244.14.5 / 244.15 闸 7 / 244.23
#   剂量轴：244.50 ｜ 余量表：244.43 ｜ 层内与台阶：244.32
LEDGER_PANEL = {
    "轨迹级 w 正/负": "13/1", "轨迹级 w p": "0.00183105",
    "轨迹级 rand 正/负": "5/9", "轨迹级 rand p": "0.42395",
    "跨臂 Fisher 轨迹级": "0.0044241",
    "问题级 w 正/负": "7/0", "问题级 w p": "0.015625",
    "问题级 rand 正/负": "2/5", "问题级 rand p": "0.453125",
    "跨臂 Fisher 问题级": "0.020979",
    "预登记 w k/n": "12/14", "预登记 w 比例": "0.8571", "预登记 w p": "0.01294",
    "预登记 rand k/n": "6/14", "预登记 rand 比例": "0.4286", "预登记 rand p": "0.79053",
    "预登记两臂差": "+42.9pp",
    "预登记跨臂 Fisher": "0.0460717",
}
LEDGER_DOSE = {
    "剂量轴 w rho（注入比例）": "+0.691",
    "剂量轴分位点": "0.015/0.250/0.750",
    "剂量轴四档格数": "27/28/30/24",
}
# ⚖ 244.43 那张表的「一格 = 几倍 p」列（账本印 1 位小数）
LEDGER_RATIO = {
    "轨迹级 w": "7.1", "轨迹级 rand": "0.4",
    "问题级 w": "8.0", "问题级 rand": "0.3",
    "预登记主统计量 w": "4.4", "预登记主统计量 rand": "0.5",
    "传播层 w（244.37）": "1.9", "传播层 rand（244.37）": "4.4",
    "传播层 w 直接层": "3.6", "传播层 rand 直接层": "2.2",
}
# ⚖ 244.43 那张表的 **p 列**（账本印 5 位小数）—— ⛔ 与「倍数」列**分开**
#   （244.56 踩过：拿一份期望去对三种不同口径的格 ⇒ 全错）
LEDGER_TABLE_P = {
    "轨迹级 w": "0.00183", "轨迹级 rand": "0.42395",
    "问题级 w": "0.01562", "问题级 rand": "0.45312",
    "预登记主统计量 w": "0.01294", "预登记主统计量 rand": "0.79053",
    "传播层 w（244.37）": "0.42395", "传播层 rand（244.37）": "0.01294",
    "传播层 w 直接层": "0.12500", "传播层 rand 直接层": "0.45312",
}
# ⚖ 244.32 §③ 的 4 个「中位 rho」（账本印 3 位小数）
LEDGER_MEDIAN_RHO = {
    "传播层 w 中位 rho": "+0.336", "传播层 rand 中位 rho": "+0.568",
    "直接层 w 中位 rho": "+0.500", "直接层 rand 中位 rho": "+0.500",
}
# ⚖ 244.32 §② 的台阶两行
LEDGER_STEP = {
    "w 台阶正号": "14/14", "w 台阶 p": "1.22e-4",
    "w 台阶中位 Δraw": "+0.774717", "w 台阶 raw 比值中位": "11.84",
    "rand 台阶正号": "8/14", "rand 台阶 p": "0.79",
    "rand 台阶中位 Δraw": "+0.012630", "rand 台阶 raw 比值中位": "1.00",
}

# ⚖⚠⚠ **仍未量到**（⛔ 不许写成「无差异」）
BLANKS = [
    ("远端 tokenizer 快照的内容指纹",
     "两次跑批之间远端那个 snapshot 目录的**文件内容**有没有变过（同一路径 ≠ 同一内容）"),
    ("`pos_frac` 只在 0.5 取过值",
     "别的取值下「位置/剂量轴」的含义**没有**任何实测支撑"),
    ("哪一条臂是机制效应",
     "两臂的多数**都**是跨剂量的多数（244.48/244.50）⇒ 机制与剂量仍**不可分辨**"),
    ("固定/分层剂量下的 w/rand 各自改判数",
     "**要跑新的一批**（第三次改口径）⇒ ⛔ 等用户点头 ⇒ 本地量不到"),
    ("层内 rho 的重复性",
     "rep_n=1 ⇒ 「rand 臂那个 12/14 是不是噪声」**仍未解释**（244.37）"),
]
BLANKS_REQUIRED = ("远端 tokenizer 快照的内容指纹",
                   "`pos_frac` 只在 0.5 取过值",
                   "哪一条臂是机制效应",
                   "固定/分层剂量下的 w/rand 各自改判数",
                   "层内 rho 的重复性")


# ---------------------------------------------------------------- 重算


def recompute():
    """⚖ 把**所有**要展示的格子重算一遍。返回 (cells, extra)"""
    VS, LRA, DAX, DCA, HRA = vs(), lra(), dax(), dca(), hra()
    cells = collections.OrderedDict()

    # ---- 判决面板（读数层）----
    rows_w = VS.load_rows(os.path.join(REPO, ".cache", "r244", "_an.txt"))
    rows_r = VS.load_rows(os.path.join(REPO, ".cache", "r244", "_ra.txt"))
    dw = VS.derive_arm(rows_w, "w")
    dr = VS.derive_arm(rows_r, "rand")
    fw = AVm_fisher(dw, dr, "traj")
    fp = AVm_fisher(dw, dr, "prob")
    cells["轨迹级 w 正/负"] = "%d/%d" % (dw["traj"][0], dw["traj"][1] - dw["traj"][0])
    cells["轨迹级 w p"] = "%.8f" % dw["traj_p"]
    cells["轨迹级 rand 正/负"] = "%d/%d" % (dr["traj"][0], dr["traj"][1] - dr["traj"][0])
    cells["轨迹级 rand p"] = "%.8f" % dr["traj_p"]
    cells["跨臂 Fisher 轨迹级"] = "%.7g" % fw
    cells["问题级 w 正/负"] = "%d/%d" % (dw["prob"][0], dw["prob"][1] - dw["prob"][0])
    cells["问题级 w p"] = "%.6f" % dw["prob_p"]
    cells["问题级 rand 正/负"] = "%d/%d" % (dr["prob"][0], dr["prob"][1] - dr["prob"][0])
    cells["问题级 rand p"] = "%.6f" % dr["prob_p"]
    cells["跨臂 Fisher 问题级"] = "%.6g" % fp
    cells["预登记 w k/n"] = "%d/%d" % (dw["prereg"][0], dw["prereg"][1])
    cells["预登记 w 比例"] = "%.4f" % (dw["prereg"][0] / float(dw["prereg"][1]))
    cells["预登记 w p"] = "%.5f" % dw["prereg_p"]
    cells["预登记 rand k/n"] = "%d/%d" % (dr["prereg"][0], dr["prereg"][1])
    cells["预登记 rand 比例"] = "%.4f" % (dr["prereg"][0] / float(dr["prereg"][1]))
    cells["预登记 rand p"] = "%.5f" % dr["prereg_p"]
    cells["预登记两臂差"] = "%+.1fpp" % (100.0 * (dw["prereg"][0] / float(dw["prereg"][1])
                                            - dr["prereg"][0] / float(dr["prereg"][1])))
    prereg = LRA.derive_prereg_fisher()
    cells["预登记跨臂 Fisher"] = "%.7g" % prereg["fisher"]

    # ---- 剂量轴（244.50 的口径：注入比例）----
    ks = [r for r in rows_w if r.get("inject_scope") == "k"]
    fr = [DCA.frac_of(r) for r in ks]
    dd = [DCA.d_of(r) for r in ks]
    rho = DCA.spearman(fr, dd)
    qs = statistics.quantiles(fr, n=4)
    bands = [len([1 for f in fr if f <= qs[0]]),
             len([1 for f in fr if qs[0] < f <= qs[1]]),
             len([1 for f in fr if qs[1] < f <= qs[2]]),
             len([1 for f in fr if f > qs[2]])]
    cells["剂量轴 w rho（注入比例）"] = "%+.3f" % rho
    cells["剂量轴分位点"] = "%.3f/%.3f/%.3f" % (qs[0], qs[1], qs[2])
    cells["剂量轴四档格数"] = "/".join(str(b) for b in bands)

    # ---- 判决清单十行：k/n、p、「一格 = 几倍 p」（244.43）----
    layers, _raw = LRA.derive_from_logs()
    table = VS.extract_verdicts(os.path.join(HERE, "headroom_audit.py"))
    derived = {
        "轨迹级 w": (dw["traj"][0], dw["traj"][1]),
        "轨迹级 rand": (dr["traj"][0], dr["traj"][1]),
        "问题级 w": (dw["prob"][0], dw["prob"][1]),
        "问题级 rand": (dr["prob"][0], dr["prob"][1]),
        "预登记主统计量 w": (dw["prereg"][0], dw["prereg"][1]),
        "预登记主统计量 rand": (dr["prereg"][0], dr["prereg"][1]),
    }
    for name, k, n, _tier in table:
        if name in derived:
            gk, gn = derived[name]
        elif name in layers:
            # ⚖ 4 行层内（传播/直接）⇒ 用 layer_row_audit 的**重算值**
            gk, gn = layers[name]["k"], layers[name]["n"]
        else:
            continue
        cells["清单行 %s k/n" % name] = "%d/%d" % (gk, gn)
        cells["清单行 %s p" % name] = "%.5f" % HRA.sb(gk, gn)
        cells["清单行 %s 倍数" % name] = "%.1f" % HRA.one_cell_ratio(gk, gn)

    # ---- 层内：4 个中位 rho（244.32 §③）----
    kp = DAX.load_k_positions(os.path.join(REPO, ".cache", "mutbak", "r204_noise_probe.py"))
    cw = DAX.load_cells(os.path.join(REPO, ".cache", "r244", "w_new.log"))
    cr = DAX.load_cells(os.path.join(REPO, ".cache", "r244", "rand_new.log"))
    rw = DAX.k_cells(cw, kp)
    rr = DAX.k_cells(cr, kp)
    for want, tag in ((False, "传播层"), (True, "直接层")):
        for arm, rows, key in (("w", rw, "w"), ("rand", rr, "r")):
            m = DAX.within_mech(rows, want)
            vals = [v[0] for v in m.values() if v[0] is not None]
            cells["%s %s 中位 rho" % (tag, arm)] = "%+.3f" % DAX.med(vals)

    # ---- 台阶两行（244.32 §②）----
    for arm, rows, key in (("w", rw, "w"), ("rand", rr, "r")):
        deltas, jumps, ratios = DAX.mechanism_step(rows)
        pos = sum(1 for x in deltas if x > 0)
        n = len(deltas)
        p = HRA.sb(pos, n)
        med_d = DAX.med(deltas)
        med_r = DAX.med([r for r in ratios if r is not None])
        cells["%s 台阶正号" % arm] = "%d/%d" % (pos, n)
        cells["%s 台阶 p" % arm] = ("%.2e" % p) if arm == "w" else ("%.2f" % p)
        cells["%s 台阶中位 Δraw" % arm] = "%+.6f" % med_d
        cells["%s 台阶 raw 比值中位" % arm] = "%.2f" % med_r

    return cells, {"layers": layers, "table": table}


def AVm_fisher(dw, dr, which):
    A = avm()
    if which == "traj":
        return A.fisher_exact_two_sided(dw["traj"][0], dw["traj"][1] - dw["traj"][0],
                                         dr["traj"][0], dr["traj"][1] - dr["traj"][0])[0]
    return A.fisher_exact_two_sided(dw["prob"][0], dw["prob"][1] - dw["prob"][0],
                                     dr["prob"][0], dr["prob"][1] - dr["prob"][0])[0]


# ---------------------------------------------------------------- 判据


def _num_eq(a, b, tol):
    """⚖ 数字格：⛔ 解析不出来 ⇒ **不等**（不许当「一样」）"""
    try:
        fa = float(a)
        fb = float(b)
    except (TypeError, ValueError):
        return False
    return abs(fa - fb) <= tol


def audit(cells, ledger_map, tol_map, tag):
    """⚖ 逐格对账。ledger_map = {格名: 账本印的值}；tol_map = {格名: 容差}"""
    bad = []
    for name, led in ledger_map.items():
        got = cells.get(name)
        tol = tol_map.get(name, 0.0)
        if got is None:
            bad.append((name, led, "（没重算到）"))
        elif _num_eq(got, led, tol):
            continue
        elif isinstance(led, str) and got.strip() == led.strip():
            continue
        else:
            bad.append((name, led, got))
    return bad


def run_census(cells, table_rows):
    L = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        L.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    # ---- C1 判决面板 ---------------------------------------------
    # ⚖ 容差按**账本印了几位**来定（⛔ 不许一律用同一个容差 ⇒ 会误报）
    tol1 = {"轨迹级 w p": 1e-8, "轨迹级 rand p": 5e-6,
            "跨臂 Fisher 轨迹级": 1e-6, "跨臂 Fisher 问题级": 1e-6,
            "预登记 w p": 5e-6, "预登记 rand p": 5e-6,
            "预登记跨臂 Fisher": 1e-6,
            "预登记两臂差": 0.05, "预登记 w 比例": 5e-5,
            "预登记 rand 比例": 5e-5}
    bad1 = audit(cells, LEDGER_PANEL, tol1, "panel")
    L.append("  ℹ 判决面板逐格对账（账本印的值 ｜ 独立重算的值）")
    for name, led in LEDGER_PANEL.items():
        got = cells.get(name, "（没重算到）")
        L.append("      %-24s %-14s ｜ %-14s %s"
                 % (name, led, got, "✅" if name not in [b[0] for b in bad1] else "⛔"))
    put("C1", not bad1,
        "判决面板 %d 格必须与独立重算值一致；不一致 %d 格%s"
        % (len(LEDGER_PANEL), len(bad1),
           ("：" + "；".join("%s 账本 %s vs 重算 %s" % (n, a, b)
                             for n, a, b in bad1)) if bad1 else ""))

    # ---- C2 剂量轴 ------------------------------------------------
    bad2 = audit(cells, LEDGER_DOSE, {"剂量轴 w rho（注入比例）": 5e-4,
                                      "剂量轴分位点": 5e-4,
                                      "剂量轴四档格数": 0.0}, "dose")
    L.append("  ℹ 剂量轴逐格对账")
    for name, led in LEDGER_DOSE.items():
        got = cells.get(name, "（没重算到）")
        L.append("      %-24s %-16s ｜ %-16s %s"
                 % (name, led, got, "✅" if name not in [b[0] for b in bad2] else "⛔"))
    put("C2", not bad2,
        "剂量轴 %d 格必须与独立重算值一致；不一致 %d 格%s"
        % (len(LEDGER_DOSE), len(bad2),
           ("：" + "；".join("%s 账本 %s vs 重算 %s" % (n, a, b)
                             for n, a, b in bad2)) if bad2 else ""))

    # ---- C3 判决清单十行：k/n、p、倍数（三列**各有各的期望**）--------
    # ⚖⚠⚠⚠ 244.57 踩到：⛔ **不许拿一份期望去对三种不同口径的格**
    #   （k/n 是「几比几」、p 是小数、倍数是「几倍」）⇒ 我第一版全错
    #   ⇒ 三列**各写各的期望**：k/n 的期望 = **表里那份**（账本的抄写，
    #   ⛔ 而它正是被 244.55/244.56 独立核过的那份）、p 的期望 = 账本印的、
    #   倍数的期望 = 账本印的。
    table_kn = dict((n, "%d/%d" % (k, nn)) for n, k, nn, _t in table_rows)
    bad3 = []
    n3 = 0
    for name in LEDGER_RATIO:
        for suf, exp, tol in (("k/n", table_kn.get(name), 0.0),
                              ("p", LEDGER_TABLE_P.get(name), 5e-6),
                              ("倍数", LEDGER_RATIO.get(name), 0.05)):
            key = "清单行 %s %s" % (name, suf)
            got = cells.get(key)
            n3 += 1
            if got is None or exp is None:
                bad3.append((key, exp, got if got is not None else "（没重算到）"))
            elif suf == "k/n":
                if got != exp:
                    bad3.append((key, exp, got))
            elif not _num_eq(got, exp, tol):
                bad3.append((key, exp, got))
    put("C3", not bad3,
        "判决清单十行的 k/n、p、「一格 = 几倍 p」共 %d 格必须与独立重算值一致；"
        "不一致 %d 格%s"
        % (n3, len(bad3),
           ("：" + "；".join("%s 账本 %s vs 重算 %s" % (x, a, b)
                             for x, a, b in bad3)) if bad3 else ""))

    # ---- C4 层内：4 个中位 rho + 台阶两行 ---------------------------
    tol4 = {k: 5e-4 for k in LEDGER_MEDIAN_RHO}
    bad4 = audit(cells, LEDGER_MEDIAN_RHO, tol4, "median")
    for name, led in LEDGER_MEDIAN_RHO.items():
        got = cells.get(name, "（没重算到）")
        L.append("      %-24s %-14s ｜ %-14s %s"
                 % (name, led, got, "✅" if name not in [b[0] for b in bad4] else "⛔"))
    bad4b = []
    for name, led in LEDGER_STEP.items():
        got = cells.get(name)
        tol = 5e-4 if "rho" in name else (0.05 if "比值" in name else 5e-6)
        if name.endswith("正号"):
            ok = (got == led)
        elif name.endswith("p"):
            ok = _num_eq(got, led, 5e-6)
        else:
            ok = _num_eq(got, led, tol)
        if not ok:
            bad4b.append((name, led, got))
    for name, led in LEDGER_STEP.items():
        got = cells.get(name, "（没重算到）")
        L.append("      %-24s %-14s ｜ %-14s %s"
                 % (name, led, got, "✅" if name not in [b[0] for b in bad4b] else "⛔"))
    put("C4", not bad4 and not bad4b,
        "层内 4 个中位 rho + 台阶两行共 %d 格必须与独立重算值一致；不一致 %d 格%s"
        % (len(LEDGER_MEDIAN_RHO) + len(LEDGER_STEP),
           len(bad4) + len(bad4b),
           ("：" + "；".join("%s 账本 %s vs 重算 %s" % (x, a, b)
                             for x, a, b in (bad4 + bad4b))) if (bad4 or bad4b) else ""))

    # ---- C5 元判据：普查完整性 --------------------------------------
    total = (len(LEDGER_PANEL) + len(LEDGER_DOSE) + len(LEDGER_RATIO) * 3
             + len(LEDGER_MEDIAN_RHO) + len(LEDGER_STEP))
    have = [n for n in list(LEDGER_PANEL) + list(LEDGER_DOSE) + list(LEDGER_MEDIAN_RHO)
            + list(LEDGER_STEP)]
    have += ["清单行 %s %s" % (n, s) for n in LEDGER_RATIO
             for s in ("k/n", "p", "倍数")]
    missing = [n for n in have if n not in cells]
    put("C5", not missing,
        "**每一格**都必须有独立重算来源：应查 %d 格、实重算 %d 格；缺 %d 格%s"
        % (len(have), len(cells), len(missing),
           ("：" + "、".join(missing)) if missing else ""))

    # ---- C6 留白 ----------------------------------------------------
    for t, why in BLANKS:
        L.append("  · %s —— **未量到**（%s）" % (t, why))
    miss_b = [t for t in BLANKS_REQUIRED
              if not any(("· %s ——" % t) in x for x in L)]
    put("C6", not miss_b,
        "五条未量到项必须逐条印出（⛔ 不许写成「无差异」）；缺 %s"
        % ("无" if not miss_b else "、".join(miss_b)))

    return R, L


def run():
    cells, _extra = recompute()
    table_rows = _extra["table"]
    L = []
    L.append("【1】**判决面板每一格的来源普查**（账本印的值 ｜ 独立重算的值）")
    L.append("  ⚖ 重算一律走**既有生产机械**（⛔ 不另写一套 ⇒ 不制造第二套真相）")
    L.append("")
    L.append("【2】判据")
    R, L2 = run_census(cells, table_rows)
    L.extend(L2)
    return L, (0 if all(R.values()) else 1), R


# ---------------------------------------------------------------- 自检


def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    cells, _extra = recompute()
    R, L = run_census(cells, _extra["table"])
    chk("C0", all(R.values()),
        "真实数据全绿（红的有 %s）"
        % (",".join(k for k, v in R.items() if not v) or "无"))

    # ---- C1：面板某一格被改 ⇒ 必须红 ------------------------------
    c1 = dict(cells)
    c1["预登记 w k/n"] = "13/14"
    R1, L1 = run_census(c1, _extra["table"])
    chk("C1x", not R1.get("C1"),
        "面板里「预登记 w k/n」被改成 13/14 ⇒ C1 必须红")

    # ---- C2：剂量轴某格被改 ⇒ 必须红 ------------------------------
    c2 = dict(cells)
    c2["剂量轴 w rho（注入比例）"] = "+0.700"
    R2, L2 = run_census(c2, _extra["table"])
    chk("C2x", not R2.get("C2"),
        "剂量轴 rho 被改 ⇒ C2 必须红")

    # ---- C3：倍数列某一格被改 ⇒ 必须红 ----------------------------
    c3 = dict(cells)
    c3["清单行 轨迹级 w 倍数"] = "6.0"
    R3, L3 = run_census(c3, _extra["table"])
    chk("C3x", not R3.get("C3"),
        "倍数列「轨迹级 w」被改 ⇒ C3 必须红")

    # ---- C3y：**k/n 那一支**单独踩到（244.56 ㋁ 的规矩）--------------
    #   ⚠ C3x 只踩了「倍数」那一支 ⇒ k/n 那一支**走不到**
    #   ⇒ 变异台里「把 k/n 的比较焊成恒真」就会**存活** ⇒ 这里补一条
    c3y = dict(cells)
    c3y["清单行 轨迹级 w k/n"] = "12/14"
    R3y, L3y = run_census(c3y, _extra["table"])
    chk("C3y", not R3y.get("C3"),
        "k/n 列「轨迹级 w」被改（其余不变）⇒ C3 必须红")

    # ---- C4：中位 rho 某一格被改 ⇒ 必须红 --------------------------
    c4 = dict(cells)
    c4["传播层 w 中位 rho"] = "+0.400"
    R4, L4 = run_census(c4, _extra["table"])
    chk("C4x", not R4.get("C4"),
        "层内中位 rho 被改 ⇒ C4 必须红")

    # ---- C5：少重算一格 ⇒ 必须红 ----------------------------------
    c5 = dict(cells)
    c5.pop("预登记跨臂 Fisher", None)
    R5, L5 = run_census(c5, _extra["table"])
    chk("C5x", not R5.get("C5"),
        "少重算一格 ⇒ C5 必须红")

    # ---- C6：少印一条留白 ⇒ 必须红 --------------------------------
    old = BLANKS[:]
    try:
        del BLANKS[0]
        R6, L6 = run_census(cells, _extra["table"])
    finally:
        BLANKS[:] = old
    chk("C6x", not R6.get("C6"),
        "少印一条留白 ⇒ C6 必须红")

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="判决面板每一格的来源普查（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        L, rc, R = run()
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print("\n".join(L))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
