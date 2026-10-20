#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verdict_panel_audit.py —— **判决面板终版**（修订 244.61，零 GPU）

⚖⚠⚠⚠⚠ 本工具**只做一件事**：把用户点名要看的那张「判决面板」**一次印全**，
  并且**每一格都带着它的口径与前提**。

⚖⚠⚠⚠⚠ **为什么现在做这一节**
  · 面板到现在还是 244.57 时代的 **63 格** ⇒ 它**没有**剂量分层、
    **没有** 244.59 的口径声明、**没有** 244.60 的层内基准说明、
    **没有** 244.58 的区间 ⇒ 读者从面板上**看不出**「显著」的前提。
  · 244.60 把「多数」按剂量层拆开后，**面板那个 12/14 的覆盖面**才变成一个
    **可查的问题**（面板口径 12/14 vs 剂量轴口径 10/14）。

⚖⚠⚠⚠⚠ **复用既有生产机械（⛔ 不另写第二套真相）**
  · 面板 63 格  ⇐ `ledger_cell_census.recompute()` + `.run_census()`（244.57）
  · 剂量轴      ⇐ `dose_confound_audit.dose_cells` / `dose_bands`（244.50 / 244.60）
  · 剂量分层    ⇐ `dose_layer_audit.build_all()` / `build_report()`（244.60）
  · 区间        ⇐ `interval_audit.derive_panel()` / `compute_all()` / `build_report()`（244.58）
  · 块级        ⇐ `cluster_premise_audit.block_majority` / `block_sign_test_p`（244.59）
  · 对账逻辑    ⇐ `census.audit()`（⛔ 不自己再写一遍逐格比较）

⚖⚠⚠⚠⚖ **本工具自己的纪律（244.60 的教训）**
  ① **期望集独立写死** ⛔ 不从被检对象派生（244.60 的 C8/C9 就是这么变成恒绿护栏的）
  ② **判据抽成可注入的函数** ⇐ 自检才能「喂变异数据看它红」
     （244.56 踩过：判据内联 ⇒ 自检只能验「没变红」⇒ 恒绿）
  ③ 边界清单的判据**双向**（少印要红、**多印也要红**）
  ④ 每条判据**必须能红** ⇒ 配变异台 `mut_verdict_panel_audit.py`
"""

import collections
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

_MODS = {}


def _load(fname, name):
    if name in _MODS:
        return _MODS[name]
    import importlib.util
    path = os.path.join(HERE, fname)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def census():
    return _load("ledger_cell_census.py", "lcc_24461")


def dla():
    return _load("dose_layer_audit.py", "dla_24461")


def dca():
    return _load("dose_confound_audit.py", "dca_24461")


def cpa():
    return _load("cluster_premise_audit.py", "cpa_24461")


def iaud():
    return _load("interval_audit.py", "ia_24461")


# ================================================================= 独立写死的期望集
# ⚖⚠⚠⚠⚠ **全部是「账本印的值」的独立字面量**（⛔ 不从被检对象派生）
#   ⇒ 期望集与被检对象**不同源** ⇒ 少一条 / 改一个数 ⇒ 必须红

# ---- 剂量轴（244.50 印的）
AXIS_QUANTILES = (0.015, 0.250, 0.750)
AXIS_BAND_SIZE = (27, 28, 30, 24)
AXIS_RHO = 0.691
DOSE_CELL_COUNT = 109

# ---- 剂量轴的**格集合定义**（244.61 新增：244.60 之前它是**隐式**的）
#   ⚖ 写成**三条独立的过滤条件字面量**（⛔ 不调 `dose_cells` 来生成期望集）
DOSE_CELL_RULE = (
    "inject_scope == 'k'",
    "p9_lo_meas is not None（有实测读数）",
    "inject_n_sites 为真（有位点数）",
)

# ---- 244.60 印的四层分层数（逐位）
LAYER_TABLE_24460 = (
    # (层, w 条数, rand 条数, 配对置换 p, 格级正号率 w, 格级正号率 rand, 层内基准)
    (0, 4, 2, 0.6218, 0.407, 0.407, 0.3036),
    (1, 6, 4, 0.7231, 0.571, 0.429, 0.2500),
    (2, 10, 5, 0.1230, 0.767, 0.400, 0.3571),
    (3, 14, 6, 0.0081, 1.000, 0.500, 0.3214),
)
TREND_24460 = {"w": (15.875, 0.0002), "rand": (5.375, 0.0878)}

# ---- 五个口径（244.55 教训：账本里有**两个不同的轨迹级统计量** ⇒ 必须标清）
CAL_TRAJ = "轨迹级符号检验（`p9_lo_meas`）"
CAL_PROB = "问题级（组内 Δ 的中位数）"
CAL_PREREG = "预登记主统计量（`up_mono_meas`，平局算 False）"
CAL_BLOCK = "块级（244.59：块内两条都正才算正）"
CAL_DOSE = "剂量轴口径（244.60：轨迹级 × 剂量层，scope=k）"
CAL_LAYER = "层内/传播层（244.32 / 244.37）"
CALIBERS = (CAL_TRAJ, CAL_PROB, CAL_PREREG, CAL_BLOCK, CAL_DOSE, CAL_LAYER)

# ---- 前提声明（独立短标签，⛔ 不从被检对象派生）
PREMISE_TAGS = ("【P1】", "【P2】", "【P3】", "【P4】")
PREMISES = (
    ("【P1】⚖⚠⚠⚠ **前提是否独立 = 未量到**（14 条轨迹 = 7 块 × 2，7 块 ⇒ 检验功效 0.340）"
     " ⇒ 面板上每一个 p 与每一个区间都带着这个**未量到**的前提"),
    ("【P2】⚖⚠⚠⚠ **层内的零假设基准不是 0.5**（平票算 False ⇒ 基准 = P(nT > nz/2)；"
     "nz=2 ⇒ 0.25）⇒ 沿用 0.5 会把**层 2** 的结论说反（0.0070 vs 0.1796）"),
    ("【P3】⚖⚠⚠⚠ **面板口径（全部格）w 12/14 ≠ 剂量轴口径（scope=k）w 10/14**"
     " ⇒ 差在**端点格**（`all` / `single`）不在剂量轴上 ⇒「固定剂量」版本是 **10/14**"),
    ("【P4】⚖⚠⚠⚠ **生产里并存两条多数规则**（`majority_count` 零**进**分母 vs "
     "`p9delta_per_tid` 零**不计**）⇒ rand 臂层 2 **5/14 vs 6/14** ⇒ 引用必须写清哪条"),
)

# ---- 边界清单的**键**（244.61 独立写死，⛔ 不从 census/dla/cpa 派生）
#   ⚖⚠⚠⚠ 三处清单的条目名各不相同（244.60 那 7 条带【B*】标签与 ** 粗体）
#   ⇒ 用**剥掉标签与粗体**的「键」做对齐 ⇒ 键表**独立写死**在本工具里
#   ⇒ 判据**双向**：我列的必须印出（少印 ⇒ 红）**且**印出的必须在我列的里
#     （三处新增一条空白 ⇒ 也红 ⇒ ⛔ 不许悄悄多出一条「未量到」）
BLANK_KEYS_24461 = (
    "远端 tokenizer 快照的内容指纹",
    "`pos_frac` 只在 0.5 取过值",
    "哪一条臂是机制效应",
    "固定/分层剂量下的 w/rand 各自改判数",
    "层内 rho 的重复性",
    "前提是否独立",
    "剂量层的机制含义",
    "层间独立性",
    "层内的重复性",
    "纯剂量轴（剂量与机制完全正交的那一轴）",
    "固定剂量下「改判了多少题」",
)


def blank_key(name):
    """⚖ 剥掉标签与粗体标记 ⇒ 边界清单的**键**。"""
    return re.sub(r"【[PB]\d+】|\*\*", "", name).strip()


def caliber_of(cell_name):
    """⚖ 这一格属于**哪一条统计量**（口径）。

    ⚖⚠⚠⚠ **匹配不上就返回 None**（⛔ 不许落到 else 兜底）——
      新增/改名一格而忘了配口径 ⇒ 判据 C5 必须红。
    """
    if cell_name.startswith("剂量轴"):
        return CAL_DOSE
    if "轨迹级" in cell_name:
        return CAL_TRAJ
    if "问题级" in cell_name:
        return CAL_PROB
    if "预登记" in cell_name:
        return CAL_PREREG
    if "块级" in cell_name:
        return CAL_BLOCK
    if ("传播层" in cell_name or "台阶" in cell_name
            or "中位 rho" in cell_name):
        return CAL_LAYER
    return None


# ================================================================= 判据（**可注入**）
# ⚖⚠⚠⚠⚠ 每条都是**吃参数、返回 bool**的函数 ⇒ 自检可以**喂变异数据**看它红
#   （244.56 踩过：判据内联在报告里 ⇒ 自检只能验「没变红」⇒ **恒绿**）


def j_c1_axis(qs, bands, rho, n_cells):
    """⚖ C1：剂量轴必须**逐位复现 244.50**。"""
    return (tuple(round(q, 3) for q in qs) == AXIS_QUANTILES
            and tuple(bands) == AXIS_BAND_SIZE
            and abs(rho - AXIS_RHO) <= 5e-4
            and n_cells == DOSE_CELL_COUNT)


def j_c2_cellset(impl_cells, rule_cells):
    """⚖ C2：剂量轴的**格集合**必须**逐条**等于独立写死的三条条件。

    ⚖ 两端**不同源**：一边是 `dose_cells` 的实现输出，
      一边是本工具**自己写的**过滤规则 ⇒ 有牙。
    """
    return set(id(r) for r in impl_cells) == set(id(r) for r in rule_cells)


def j_c3_measured(all_k):
    """⚖ C3：「**所有** k 格都有实测读数与位点数」必须成立。

    ⚖ 这是「各处过滤条件当前等价**不是巧合**」的**唯一**理由 ⇒ 必须被验。
    """
    return (len(all_k) == DOSE_CELL_COUNT
            and not [r for r in all_k if r.get("p9_lo_meas") is None]
            and not [r for r in all_k if not r.get("inject_n_sites")])


def j_c4_layers(layer_rows, trend):
    """⚖ C4：四层分层数与**剂量趋势**必须与 244.60 **逐位一致**。"""
    bad = []
    for (L_, kw, kr, pp, cw, cr, base), row in zip(LAYER_TABLE_24460, layer_rows):
        gpw, gpn, gpr = row["cellpos"]
        if (L_ != row["L"] or kw != row["kw"] or kr != row["kr"]
                or abs(pp - row["pperm"]) > 5e-5
                or abs(cw - gpw / float(gpn)) > 5e-4
                or abs(cr - gpr / float(gpn)) > 5e-4
                or abs(base - row["avg_base"]) > 5e-5):
            bad.append("层 %d" % row["L"])
    tw, pr = TREND_24460["w"], TREND_24460["rand"]
    if abs(tw[0] - trend["w"]["T"]) > 5e-4 or abs(tw[1] - trend["w"]["p"]) > 5e-5:
        bad.append("w 剂量趋势")
    if abs(pr[0] - trend["rand"]["T"]) > 5e-4 or abs(pr[1] - trend["rand"]["p"]) > 5e-5:
        bad.append("rand 剂量趋势")
    return (not bad), bad


def j_c5_caliber(cells):
    """⚖ C5：**每一格**都必须配到口径。返回未配口径的格名列表（空 = 绿）。"""
    return [n for n in cells if caliber_of(n) is None]


def j_c6_premise(lines):
    """⚖ C6：四条前提声明必须逐条印出。返回缺的标签。"""
    return [t for t in PREMISE_TAGS if not any(t in ln for ln in lines)]


def j_c7_blanks(printed_keys):
    """⚖ C7：边界清单**双向**对上。返回 (少印, 多印)。"""
    miss = [k for k in BLANK_KEYS_24461 if k not in printed_keys]
    extra = [k for k in printed_keys if k not in BLANK_KEYS_24461]
    return miss, extra


def j_c8_rules(lines):
    """⚖ C8：「剂量轴的格集合」的三条过滤条件必须**逐条**印出。

    ⚖⚠⚠⚠⚠ **第一版这里有「变量遮蔽」**：内层 `for i, r in enumerate(...)` 把外层的
      `r` **遮蔽**了 ⇒ 实际检查的是「三条里**任意一条**在不在」⇒
      **近乎恒绿护栏**（少印一条照样绿）⇒ 是自检当场抓出来的。
      ⇒ 修法：内层用**另一个变量名**，逐条独立查。
    """
    out = []
    for i, rule in enumerate(DOSE_CELL_RULE, 1):
        tag = "〔格集合条件 %d〕%s" % (i, rule)
        if not any(tag in ln for ln in lines):
            out.append(rule)
    return out


def j_c9_caliber_rows(lines):
    """⚖ C9：口径对照表必须印出面板口径、剂量轴口径与**两个统计量各自的块级**。

    ⚖⚠⚠⚠⚠ 匹配串必须是 `"· 块级（"`（**带项目符号**）——
      只匹配 `"块级（"` 会把**口径图例**那一行也算进去
      ⇒ 阈值只要 1 行真块级 + 1 行图例就够 ⇒ **判据偏弱**（244.61 自检当场发现）。
    """
    n_block_rows = sum(1 for ln in lines if "· 块级（" in ln)
    return (any(("面板口径" in ln) for ln in lines)
            and any(("剂量轴口径" in ln) for ln in lines)
            and n_block_rows >= 2)


def j_c10_intervals(lines):
    """⚖ C10：6 个比例的 95% 区间与 3 条差区间必须印出。"""
    n_iv = sum(1 for ln in lines if "CP95 [" in ln)
    n_diff = sum(1 for ln in lines if "Newcombe [" in ln)
    return n_iv >= 6 and n_diff >= 3


# ================================================================= 主流程
def build():
    """⚖ 组装面板。返回 (RP, R, blocks)。"""
    C = census()
    D = dla()
    DC = dca()
    CPA = cpa()
    IA = iaud()

    RP = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        RP.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    # ---- 复用 244.57 的 63 格普查 ----
    cells, extra = C.recompute()
    R_c, _L_c = C.run_census(cells, extra["table"])

    # ---- 复用 244.60 的剂量分层 ----
    A = D.build_all()
    _rp_dla, _R_dla, layer_rows, trend = D.build_report(A)

    # ---- 剂量轴（唯一实现）----
    ks, fr = DC.dose_cells(A["rows"]["w"])
    qs, bands = DC.dose_bands(ks, fr)
    band_sizes = tuple(len(b[1]) for b in bands)
    rho = DC.spearman(fr, [DC.d_of(r) for r in ks])

    # ---- 区间（复用 244.58）----
    icells, _iout = IA.derive_panel()
    ires = IA.compute_all(icells)
    _L_ia, R_ia = IA.build_report(icells, ires)

    RP.append("【0】⚖⚠⚠⚠ **前提声明**（⛔ 删掉任何一条都必须红）")
    for s in PREMISES:
        RP.append("  " + s)
    RP.append("")

    # ================================================================ 板块一：判决面板
    RP.append("【1】🔴 **判决面板**（%d 格 ｜ 每一格都带**口径**）" % len(cells))
    RP.append("  ⚖ 全部来自 `ledger_cell_census.recompute()` 的**独立重算**"
              "（244.57：63/63 逐位全对 ⇒ 面板再没有一个「只有手抄」的格）")
    RP.append("  ⚖ 口径图例（⚠ **块级口径在 63 格里没有格子** —— 它是 244.59 新增的第四个统计量）：")
    for c in CALIBERS:
        RP.append("      %s" % c)
    RP.append("")

    panel_rows = []
    for name in sorted(cells):
        panel_rows.append((name, cells[name], caliber_of(name)))
    RP.append("  ℹ 面板逐格（格名 ｜ 独立重算值 ｜ **口径**）")
    for name, val, cal in panel_rows:
        RP.append("      %-26s %-16s ｜ %s"
                  % (name, val, cal if cal else "⛔ **未配口径**"))
    RP.append("")

    # ================================================================ 板块二：剂量轴
    RP.append("【2】📐 **剂量轴**（注入比例轴，244.50）")
    RP.append("  ⚖ 分位点 %s ｜ 四档格数 %s ｜ w rho %+.4f ｜ 剂量轴格数 %d"
              % ("/".join("%.3f" % q for q in qs),
                 "/".join(str(b) for b in band_sizes), rho, len(ks)))
    RP.append("  ⚖⚠⚠⚠ **格集合的定义**（244.61 新增：244.60 之前它是**隐式**的）"
              " ⇒ 这三条**一起**才构成「剂量轴的格」：")
    for i, rule in enumerate(DOSE_CELL_RULE, 1):
        RP.append("      〔格集合条件 %d〕%s" % (i, rule))
    RP.append("")

    # ================================================================ 板块三：剂量分层
    RP.append("【3】📊 **剂量分层**（244.60：轨迹级 × 剂量层）")
    RP.append("  ℹ 层 ｜ w ｜ rand ｜ 配对置换 p ｜ 格级正号率 w/rand ｜ 层内基准")
    for row in layer_rows:
        gpw, gpn, gpr = row["cellpos"]
        RP.append("      层 %d ｜ %d/%d ｜ %d/%d ｜ %.4f ｜ %.3f / %.3f ｜ %.4f"
                  % (row["L"], row["kw"], row["nw"], row["kr"], row["nr"],
                     row["pperm"], gpw / float(gpn), gpr / float(gpn),
                     row["avg_base"]))
    RP.append("  ⚖ 剂量趋势（各自层基准 + MC 零假设）："
              "w T=%.3f p=%.4f ｜ rand T=%.3f p=%.4f"
              % (trend["w"]["T"], trend["w"]["p"], trend["rand"]["T"],
                 trend["rand"]["p"]))
    RP.append("")

    # ================================================================ 板块四：口径对照
    #   ⚖⚠⚠⚠⚠ **块级必须标明是「哪个统计量的块级」**（244.59 的教训：
    #   账本里有**两个不同的轨迹级统计量** ⇒ 单说「块级 6/7」这句话**不完整**）
    DCPA = CPA.derive_all()

    def _block(arm, stat):
        d = DCPA[arm]
        signs = d["traj_signs" if stat == "traj" else "prereg_signs"]
        bk, bn = CPA.block_majority(d["blocks"], signs)
        p = CPA.block_sign_test_p(d["blocks"], signs)
        return bk, bn, p

    RP.append("【4】🔀 **口径对照**（同一个「多数」在不同口径下的数）")
    RP.append("  ⚖⚠⚠⚠ **块级必须标明是「哪个统计量的块级」**（244.59 的教训："
              "「块级 6/7」这句话本身**不完整**）")
    RP.append("      · %-30s w %-7s rand %-7s（%s）"
              % ("面板口径（全部格，含端点格）",
                 "%d/%d" % (A["arm"]["w"]["panel"][0], A["arm"]["w"]["panel"][1]),
                 "%d/%d" % (A["arm"]["rand"]["panel"][0], A["arm"]["rand"]["panel"][1]),
                 "244.57 普查的 63 格之一"))
    RP.append("      · %-30s w %-7s rand %-7s（%s）"
              % ("剂量轴口径（scope=k，244.60）",
                 "%d/%d" % (A["arm"]["w"]["scope_k"][0], A["arm"]["w"]["scope_k"][1]),
                 "%d/%d" % (A["arm"]["rand"]["scope_k"][0], A["arm"]["rand"]["scope_k"][1]),
                 "「固定剂量」那个版本"))
    for stat, slabel in (("traj", "轨迹级符号检验"), ("prereg", "预登记主统计量")):
        bkw, bnw, pw = _block("w", stat)
        bkr, bnr, prr = _block("rand", stat)
        RP.append("      · %-30s w %-7s rand %-7s（%s 的块级 p=%s / %s）"
                  % ("块级（%s）" % slabel, "%d/%d" % (bkw, bnw),
                     "%d/%d" % (bkr, bnr), slabel, "%.6f" % pw, "%.6f" % prr))
    RP.append("")

    # ================================================================ 板块五：区间
    RP.append("【5】📐 **统计区间**（95%；CP = Clopper–Pearson 精确，W = Wilson 分数）")
    RP.append("  ⚖ 全部走 `interval_audit`（244.58；每个区间都由**定义式 / 覆盖率实测 / 暴力搜**验过）")
    for key, c in icells.items():
        r = ires[key]
        RP.append("      · %-14s %d/%d  p̂=%.4f ｜ CP95 [%s, %s] ｜ W95 [%s, %s]"
                  % (c["label"], c["k"], c["n"], r["phat"],
                     IA.fmt(r["cp"][0]), IA.fmt(r["cp"][1]),
                     IA.fmt(r["wilson"][0]), IA.fmt(r["wilson"][1])))
    for dkey, _dlabel, _stat in IA.DIFFS:
        d = ires[dkey]
        RP.append("      · %-14s w %d/%d − rand %d/%d ｜ 差 %s pp"
                  " ｜ Newcombe [%s, %s]（⛔ 不许用两个 CI 相减）"
                  % (d["label"], d["w"][0], d["w"][1], d["rand"][0], d["rand"][1],
                     "%.1f" % (100.0 * d["phat_diff"]),
                     IA.fmt(d["newcombe"][0]), IA.fmt(d["newcombe"][1])))
    RP.append("  ⚖⚠⚠⚠⚠ **这些区间是「计数口径」的边际**（244.48/244.50：两臂的多数都是**跨剂量**的多数）")
    RP.append("     ⇒ ⛔ **不代表**「固定剂量下改判了多少题」的区间 ⇒ 那一格仍写「**未量到**」")
    RP.append("")

    # ================================================================ 板块六：边界清单
    RP.append("【6】⚠️ **边界清单**（未量到 ⇒ ⛔ 不许写成「无差异」）")
    merged = collections.OrderedDict()
    for src, pairs in (("244.57", C.BLANKS), ("244.59", CPA.BLANKS),
                       ("244.60", D.BLANKS)):
        for name, why in pairs:
            k = blank_key(name)
            if k in merged:
                merged[k]["srcs"].append(src)
            else:
                merged[k] = {"raw": name, "why": why, "srcs": [src]}
    for _k, v in merged.items():
        RP.append("      · %s —— **未量到**（%s）｜ %s"
                  % (v["raw"], v["why"], "/".join(v["srcs"])))
    printed_keys = set(merged)
    RP.append("")

    # ================================================================ 判据
    put("C0", all(R_c.values()),
        "面板 %d 格的**逐格**对账必须全绿（复用 244.57 的 6 条判据：%s）"
        % (len(cells), "、".join("census:%s%s" % (k, "" if v else "❌")
                                 for k, v in R_c.items())))

    put("C1", j_c1_axis(qs, band_sizes, rho, len(ks)),
        "剂量轴必须**逐位复现 244.50**（分位点 %s ｜ 四档 %s ｜ rho %+.3f ｜ %d 格）"
        % ("/".join("%.3f" % q for q in AXIS_QUANTILES),
           "/".join(str(b) for b in AXIS_BAND_SIZE), AXIS_RHO, DOSE_CELL_COUNT))

    rule_cells = [r for r in A["rows"]["w"]
                  if r.get("inject_scope") == "k"
                  and r.get("p9_lo_meas") is not None
                  and r.get("inject_n_sites")]
    ok2 = j_c2_cellset(ks, rule_cells)
    put("C2", ok2,
        "剂量轴的**格集合**必须**逐条**等于独立写死的三条条件（%d 条）；"
        "实现给 %d 条、独立规则给 %d 条；差 %d 条%s"
        % (len(rule_cells), len(ks), len(rule_cells),
           len(set(id(r) for r in ks) ^ set(id(r) for r in rule_cells)),
           "" if ok2 else "：集合不同 ⇒ 剂量轴的定义被改了"))

    all_k = [r for r in A["rows"]["w"] if r.get("inject_scope") == "k"]
    no_meas = [r for r in all_k if r.get("p9_lo_meas") is None]
    no_site = [r for r in all_k if not r.get("inject_n_sites")]
    put("C3", j_c3_measured(all_k),
        "「**所有** k 格都有实测读数与位点数」必须成立（k 格 %d 条；缺读数 %d 条；"
        "缺位点数 %d 条）⇒ 这是各处过滤条件当前等价的**理由**"
        % (len(all_k), len(no_meas), len(no_site)))

    ok4, bad4 = j_c4_layers(layer_rows, trend)
    put("C4", ok4,
        "四层分层数与**剂量趋势**必须与 244.60 **逐位一致**；不一致：%s"
        % ("、".join(bad4) if bad4 else "无"))

    n_nocal = j_c5_caliber(cells)
    put("C5", not n_nocal,
        "**每一格**都必须配到口径（%d 格；未配 %d 格%s）"
        % (len(cells), len(n_nocal),
           ("：" + "、".join(n_nocal[:6])) if n_nocal else ""))

    miss6 = j_c6_premise(RP)
    put("C6", not miss6,
        "四条前提声明必须逐条印出（按**独立标签**查，⛔ 期望集不从被检对象派生）；"
        "缺 %d 条%s" % (len(miss6), "" if not miss6 else "：%s" % miss6))

    miss7, extra7 = j_c7_blanks(printed_keys)
    put("C7", not miss7 and not extra7,
        "边界清单必须**双向**对上：我**独立写死**的 %d 条 vs 印出的 %d 条；"
        "少印 %d 条、多印 %d 条%s"
        % (len(BLANK_KEYS_24461), len(printed_keys), len(miss7), len(extra7),
           ("：" + "、".join((miss7 + extra7)[:4])) if (miss7 or extra7) else ""))

    miss8 = j_c8_rules(RP)
    put("C8", not miss8,
        "「剂量轴的格集合」的三条过滤条件必须**逐条**印出（⛔ 它是**隐式**的，"
        "隐式 ⇒ 改一处没人知道）；缺 %d 条%s"
        % (len(miss8), "" if not miss8 else "：%s" % miss8))

    put("C9", j_c9_caliber_rows(RP),
        "口径对照表必须同时印出**面板口径**、**剂量轴口径**"
        "（⇒「固定剂量」那个版本是 10/14，⛔ 不是 12/14）"
        "**与两个统计量各自的块级**（实测 %d 行 ⇒ 「块级 6/7」这句话**不完整**）"
        % sum(1 for ln in RP if "· 块级（" in ln))

    n_iv = sum(1 for ln in RP if "CP95 [" in ln)
    n_diff = sum(1 for ln in RP if "Newcombe [" in ln)
    put("C10", all(R_ia.values()) and j_c10_intervals(RP),
        "6 个比例的 95%% 区间（实测 %d 条）与 3 条差区间（实测 %d 条）必须印出，"
        "且 244.58 的判据全绿（%s）"
        % (n_iv, n_diff,
           "、".join("iv:%s%s" % (k, "" if v else "❌") for k, v in R_ia.items())))

    return RP, R, {"cells": cells, "R_census": R_c, "layer_rows": layer_rows,
                   "trend": trend, "qs": qs, "bands": band_sizes, "rho": rho,
                   "ks": ks, "blank_keys": printed_keys, "R_iv": R_ia,
                   "rule_cells": rule_cells, "all_k": all_k,
                   "blank_items": merged}


# ================================================================= 自检
def selftest():
    """⚖ 每条判据**正反两测**：干净输入必须绿、变异输入必须红。

    ⚖⚠⚠⚠⚠ **必须真的注入变异**（244.60 踩过：自检只在**未变异**数据上重算判据
      ⇒ 判据恒为真 ⇒ 自检**恒红**，什么都没验到）
    """
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    RP, R, B = build()
    chk("C0", all(R.values()),
        "真实数据全绿（红的有 %s）"
        % (",".join(k for k, v in R.items() if not v) or "无"))

    # ---- C1：剂量轴被改 ⇒ 必须红 ----
    chk("C1x", j_c1_axis(B["qs"], B["bands"], B["rho"], len(B["ks"]))
        and not j_c1_axis((0.016,) + tuple(B["qs"][1:]), B["bands"], B["rho"],
                          len(B["ks"])),
        "剂量轴分位点被改 ⇒ C1 必须红")

    # ---- C2：格集合多一格 ⇒ 必须红 ----
    extra = B["ks"] + [object()]
    chk("C2x", j_c2_cellset(B["ks"], B["rule_cells"])
        and not j_c2_cellset(extra, B["rule_cells"]),
        "剂量轴格集合多一格 ⇒ C2 必须红")

    # ---- C3：数据事实被破坏 ⇒ 必须红 ----
    broken = list(B["all_k"])
    chk("C3x", j_c3_measured(B["all_k"])
        and not j_c3_measured(broken[:-1]),
        "少一格 k ⇒ C3 必须红")

    # ---- C4：分层数被改 ⇒ 必须红 ----
    rows = [dict(r) for r in B["layer_rows"]]
    rows[0] = dict(rows[0])
    rows[0]["cellpos"] = (99, rows[0]["cellpos"][1], rows[0]["cellpos"][2])
    ok4, _b = j_c4_layers(rows, B["trend"])
    chk("C4x", j_c4_layers(B["layer_rows"], B["trend"])[0] and not ok4,
        "某一层的格级正号率被改 ⇒ C4 必须红")

    # ---- C5：有一格没配口径 ⇒ 必须红 ----
    chk("C5x", j_c5_caliber(B["cells"]) == []
        and j_c5_caliber({"一个全新的格名": "x"}) == ["一个全新的格名"],
        "没配口径的格名必须被 C5 抓住（⛔ 不许落 else 兜底）")

    # ---- C6：少印一条前提声明 ⇒ 必须红 ----
    short = [ln for ln in RP if "【P4】" not in ln]
    chk("C6x", not j_c6_premise(RP) and j_c6_premise(short),
        "少印一条前提声明 ⇒ C6 必须红")

    # ---- C7：少印 / 多印一条边界清单 ⇒ 必须红（**双向**）----
    miss, extra7 = j_c7_blanks(B["blank_keys"])
    short_keys = set(B["blank_keys"]) - {BLANK_KEYS_24461[0]}
    more_keys = set(B["blank_keys"]) | {"一条我没写进独立清单的空白"}
    chk("C7x", not miss and not extra7
        and j_c7_blanks(short_keys)[0] and not j_c7_blanks(short_keys)[1],
        "少印一条边界清单 ⇒ C7 必须红")
    chk("C7y", j_c7_blanks(more_keys)[1],
        "多印一条边界清单 ⇒ C7 也必须红（⛔ 不许悄悄多一条「未量到」）")

    # ---- C8：少印一条格集合条件 ⇒ 必须红 ----
    short8 = [ln for ln in RP if "〔格集合条件 3〕" not in ln]
    chk("C8x", not j_c8_rules(RP) and j_c8_rules(short8),
        "少印一条格集合条件 ⇒ C8 必须红")

    # ---- C9：少印一行块级口径 ⇒ 必须红 ----
    short9 = [ln for ln in RP if "块级（" not in ln]
    chk("C9x", j_c9_caliber_rows(RP) and not j_c9_caliber_rows(short9),
        "少印一行块级口径 ⇒ C9 必须红")

    # ---- C10：少印一条区间 ⇒ 必须红 ----
    short10 = [ln for ln in RP if "CP95 [" not in ln]
    chk("C10x", j_c10_intervals(RP) and not j_c10_intervals(short10),
        "少印一条区间 ⇒ C10 必须红")

    print("")
    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % bad)
    return 0 if not bad else 1


def main():
    import argparse
    ap = argparse.ArgumentParser(description="判决面板终版（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        RP, R, _B = build()
        for ln in RP:
            print(ln)
        print("")
        print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
        return 0 if all(R.values()) else 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("⛔ 崩了：%s: %s" % (type(e).__name__, e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
