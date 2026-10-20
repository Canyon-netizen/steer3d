#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""⚖⚖⚖⚖⚖ 244.66 固定剂量 / 分层剂量批次的**分析管线**（⛔ **不跑批**；替身跑通）。

⚖⚠⚠⚠⚠⚠ **本文件不产生「固定剂量那一批」的判决** ——
   那一批**还没跑**（要 GPU + 用户点头）⇒ **未量到**。
   本文件做的是：把「固定剂量下 w 臂与 rand 臂**各改判多少题**、**差多少 pp**、
   **p 值与区间**各是多少」这条**分析管线**写出来，并用**现有两批**当**替身**跑通。
   ⇒ 替身数字 ⛔ **不许**被引用成那一批的判决（判据 F11 专门盯这条标注）。

⚖⚠⚠⚠⚠⚠ **口径（α / 档数 / 档边界 / 分位点 / 零跨度 / 多数规则 / 检验 / 区间）
   ⛔ 一个都不在本文件里写死** ⇒ 全部从
   `.cache/xcheck/R6_FIXED_DOSE_PREREG.md` 的**机器可读块**读（K1–K13，2026-10-20 签）
   ⇒ **口径只可能被改一处**（预登记）⇒ 改那里 ⇒ 输出立刻变。
   ⚖ 判据 **F2** 会**活体**证明这一点（改预登记文件 ⇒ 输出立刻变）。

⚖⚖⚖ **复用既有生产机械**（⛔ 不另写第二套真相）：
   · 剂量轴格集合 / 分档器：`dose_confound_audit.dose_cells` / `dose_bands_v`
   · 层内多数 + 零格：`dose_layer_audit.layer_verdicts`（**`zero_fn` 必传**）
   · 配对置换：`dose_layer_audit.paired_perm_geom`（244.66 加了 MC 计数 `ge`/`n_perm`）
   · 精确 Fisher：`arm_verdict.fisher_exact_two_sided`（⛔ 不用正态近似）
   · 区间：`interval_audit.wilson_bounds` / `newcombe_diff`
   · 块级规则：`cluster_premise_audit.blocks_of` / `block_is_pos`
   · 规模：`dose_layer_audit.size_requirements`（`fisher_power` 注入
     `cluster_premise_audit.fisher_power` ＝ **精确枚举**）

⚖⚖⚖⚖⚖ **244.66 的三条纪律（从 244.60–244.65 的教训里继承）**：
   ① **口径只写一处**（预登记）⇒ F2 活体验；
   ② **每条判据都能红** ⇒ F1–F12 全部有「改坏就红」的反例（见 `selftest`）；
   ③ **恒绿护栏删掉** ⇒ 本文件**没有**「恒真的检查」：每条判据都挂在一个
      **可观测、会变**的量上（档数 / 轨迹集 / 区间端点 / p 值 / 文本标记）。
"""
import argparse
import collections
import importlib.util
import inspect
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_FIXED_DOSE_PREREG.md")
JSONL_W = os.path.join(HERE, "_an.txt")
JSONL_RAND = os.path.join(HERE, "_ra.txt")

ARMS = ("w", "rand")

# ⚖⚖⚖ **分析参数**（⛔ 不是口径）：置换次数与种子。
#   ⚖ 与 `dose_layer_audit.paired_perm_geom` 的默认值**必须一致** ⇒
#   ⚖⚠ 「两处各写一份」的经典坑 ⇒ 本文件**断言**它们一致（F8a）⇒ 改一处必红。
N_PERM = 20000
MC_SEED = 20261020

# ⚖⚖⚖ 预登记机器可读块**必须**有的键（⛔ 独立字面量 ⇒ ⛔ 不从被检对象派生）
PREREG_KEYS = (
    "alpha", "n_bands", "boundary", "quantile", "zero_span",
    "majority_rule", "report_alt_majority", "layer_base", "cross_arm_test",
    "fisher_method", "interval_ratio", "interval_diff", "mc_band",
    "blocks_needed_sign_test", "blocks_needed_cluster",
    "blocks_needed_fisher_exact", "sign_date",
)

# ⚖⚖⚖ 预登记的 **K 清单**编号（⛔ 独立字面量 ⇒ 少一条必须红）
PREREG_K_IDS = tuple("K%d" % i for i in range(1, 14))

# ⚖⚖⚖ 留白清单（**未量到**）——⛔ 独立字面量 ⇒ 少印一条必须红
BLANK_MARKS = tuple("【B%d】" % i for i in range(1, 9))
BLANKS = (
    ("【B1】**固定剂量那一批本身**",
     "那一批**还没跑**（GPU + 用户点头）⇒ 「固定剂量下 w/rand 各改判多少题、"
     "差多少 pp、p 值与区间」⇒ **未量到**（本文件只交**管线**）"),
    ("【B2】**「哪一条臂是机制效应」**", "未量到"),
    ("【B3】**前提独立性**",
     "14 条轨迹 = 7 块 × 2 ⇒ 块级口径只是**另一种口径**⇒ 独立性本身**未量到**"),
    ("【B4】**层间独立性**", "各档共享同一批轨迹 ⇒ 相关结构**未量到**"),
    ("【B5】**插值族分位算法**（hazen / weibull / linear…）",
     "本机 `statistics.quantiles` 只有 inclusive/exclusive ⇒ 未量到"),
    ("【B6】**连续剂量回归**（不设阈值）", "未量到"),
    ("【B7】**远端 tokenizer 快照的内容指纹** / **`pos_frac` 只在 0.5 取过值**",
     "未量到"),
    ("【B8】**替身与那一批的差别**",
     "替身是**跨剂量混在一起**的现有两批 ⇒ 替身里「剂量」与「机制」**仍不可分辨**"
     "⇒ 替身数字**不许**当固定剂量的结论"),
)

# ⚖⚖⚖ 判据清单（⛔ 独立字面量 ⇒ 少一条判据必须红）
CRITERION_IDS = tuple("F%d" % i for i in range(1, 13))

# ⚖⚖⚖ 「这是替身、不是那一批的判决」的标记（⛔ 独立字面量）
STANDIN_MARK = "【替身】"

# ⚖ 244.50 的生产剂量轴（**账本登记值**）—— 判据 F3 用它证明「读的是同一批数据」
AXIS_QUANTILES = (0.015, 0.250, 0.750)
AXIS_BAND_SIZE = (27, 28, 30, 24)
AXIS_RHO = 0.6911
AXIS_RHO_RAND = 0.0237

# ⚖ 已知答案夹具（⛔ **独立推导**，不是从被检实现反推）
#   表 [[1,9],[11,3]]：边际 r1=10 / r2=14 / c1=12 / n=24
#   「概率 ≤ 观测概率」的表是 x ∈ {0,1,9,10}（x = 第一行第一列的格数）
#   权重 C(10,x)·C(14,12−x) = 91, 3640, 3640, 91 ⇒ 和 = 7462
#   分母 C(24,12) = 2704156 ⇒ 精确值 7462/2704156
#   ⚖ 交叉核对：R 的 `fisher.test(matrix(c(1,9,11,3),2))` 双尾 p-value = 0.002759
#   ⇒ 同一个数（正态近似会给 ≈ 0.0126 ⇒ **抓得住「误用近似」**）
FISHER_FIXTURE = ((1, 9, 11, 3), 7462.0 / 2704156.0)

# ⚖ 244.60 登记的**逐层规模**（正态近似，条/臂）——判据 F10 拿它当**独立**对照
LEDGER_LAYER_SIZES = {0: 130, 1: 177, 2: 31, 3: 14}


class HardFail(Exception):
    """⚖ 前提不满足 ⇒ **不出判决**（⛔ 不许降级、不许静默兜底）。"""


# ---------------------------------------------------------------- 模块加载
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


def dlayer():
    return _load(os.path.join(HERE, "dose_layer_audit.py"), "dl_24466")


def dconf():
    return dlayer().dconf()


def vsrc():
    return dlayer().vsrc()


def armv():
    return dlayer().armv()


def iaud():
    return dlayer().iaud()


def cpre():
    return dlayer().cpre()


# ---------------------------------------------------------------- 预登记
def read_prereg(path=PREREG):
    """⚖⚖⚖ 从预登记的**机器可读块**读口径（⛔ **不在代码里写死**）。

    ⚖ 块格式：` ```prereg ` 围栏里的 `key = value` 行。
    ⚖⚠⚠⚠ **缺键 ⇒ HardFail**（⛔ 不许用默认值兜底 ⇒ 那会让「口径被改」看不见）。
    """
    if not os.path.isfile(path):
        raise HardFail("预登记文件不存在：%s" % path)
    text = io.open(path, encoding="utf-8").read()
    m = re.search(r"```prereg\r?\n(.*?)```", text, re.S)
    if not m:
        raise HardFail("预登记里找不到 ```prereg 机器可读块：%s" % path)
    raw = {}
    for ln in m.group(1).splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            raise HardFail("预登记机器块里有一行没有 '=': %r" % s)
        k, v = s.split("=", 1)
        raw[k.strip()] = v.strip()
    missing = [k for k in PREREG_KEYS if k not in raw]
    if missing:
        raise HardFail("预登记机器块缺键：%s（⛔ 不许用默认值兜底）"
                       % ", ".join(missing))
    return raw


def prereg_k_rows(path=PREREG):
    """⚖ 预登记里那张 **K 清单表**的行（`K1`…`K13`）—— 判据 F1 用它查「清单齐全」。"""
    if not os.path.isfile(path):
        raise HardFail("预登记文件不存在：%s" % path)
    out = []
    for ln in io.open(path, encoding="utf-8").read().splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and re.match(r"^K\d+$", cells[0]):
            out.append(cells)
    return out


def _as_num(raw, key, cast):
    """⚖⚠⚖⚖ 预登记的值**格式不对** ⇒ **HardFail**（⛔ 不许崩成 ValueError）。

    ⚖ **244.68 补**：原来 `float(raw["alpha"])` 在值为空/非数时会**抛 ValueError**
    ⇒ 读同一份预登记的**预检器**会带着 traceback **崩掉**
    ⇒ ⛔ **「崩」不是「抓到」** ⇒ 改成**干净的 HardFail**（⇒ 明确「前提不满足」）。
    ⚖ 良构路径的取值**完全不变**（只多了一层 except ⇒ 逐位相同）。
    """
    v = (raw or {}).get(key)
    try:
        return cast(v)
    except (TypeError, ValueError):
        raise HardFail("预登记 %s=%r 不是%s" % (key, v, cast.__name__))


class Cfg(object):
    """⚖ **生效口径**（全部来自预登记）—— ⛔ 本类里没有一句「写死」的取值。"""

    def __init__(self, raw):
        self.raw = dict(raw)
        self.alpha = _as_num(raw, "alpha", float)
        self.n_bands = _as_num(raw, "n_bands", int)
        self.boundary = raw["boundary"]
        self.quantile = raw["quantile"]
        self.zero_span = raw["zero_span"]
        self.majority_rule = raw["majority_rule"]
        self.report_alt_majority = raw["report_alt_majority"]
        self.layer_base = raw["layer_base"]
        self.cross_arm_test = raw["cross_arm_test"]
        self.fisher_method = raw["fisher_method"]
        self.interval_ratio = raw["interval_ratio"]
        self.interval_diff = raw["interval_diff"]
        self.mc_band = raw["mc_band"]
        self.blocks_needed_sign_test = _as_num(raw, "blocks_needed_sign_test", int)
        self.blocks_needed_cluster = _as_num(raw, "blocks_needed_cluster", int)
        self.blocks_needed_fisher_exact = _as_num(raw, "blocks_needed_fisher_exact", int)
        self.sign_date = raw["sign_date"]
        self._check_contract()

    def _check_contract(self):
        """⚖ 口径**取值**必须落在机械支持的范围里；口径**种类**必须本管线实现过。
        ⚖⚠⚠ 种类不匹配 ⇒ **HardFail**（⛔ 绝不静默降级成「别的做法」）。"""
        DC = dconf()
        if self.boundary not in DC.BOUNDARY_CONVENTIONS:
            raise HardFail("预登记 boundary=%r 不在 %s 里" % (self.boundary,
                                                             list(DC.BOUNDARY_CONVENTIONS)))
        if self.quantile not in DC.QUANTILE_METHODS_EXT:
            raise HardFail("预登记 quantile=%r 不在 %s 里"
                           % (self.quantile, list(DC.QUANTILE_METHODS_EXT)))
        if self.zero_span not in DC.ZERO_SPAN_POLICIES:
            raise HardFail("预登记 zero_span=%r 不在 %s 里"
                           % (self.zero_span, list(DC.ZERO_SPAN_POLICIES)))
        if self.n_bands not in DC.N_BANDS_CHOICES:
            raise HardFail("预登记 n_bands=%r 不在 %s 里"
                           % (self.n_bands, list(DC.N_BANDS_CHOICES)))
        need = {
            "majority_rule": "nT_gt_nF_zero_counts_as_False",
            "report_alt_majority": "required",
            "layer_base": "exact_binomial",
            "cross_arm_test": "paired_permutation",
            "fisher_method": "exact_enumeration",
            "interval_ratio": "wilson95",
            "interval_diff": "newcombe95",
            "mc_band": "required",
        }
        for k, v in need.items():
            if getattr(self, k) != v:
                raise HardFail("预登记 %s=%r，本管线只实现了 %r（⛔ 不许静默降级）"
                               % (k, getattr(self, k), v))

    def as_lines(self):
        """⚖ 生效口径的**可读清单**（报告与账本共用 ⇒ 两处不可能漂）。"""
        return [
            ("alpha", "%.6g" % self.alpha),
            ("n_bands", "%d" % self.n_bands),
            ("boundary", self.boundary),
            ("quantile", self.quantile),
            ("zero_span", self.zero_span),
            ("majority_rule", self.majority_rule),
            ("report_alt_majority", self.report_alt_majority),
            ("layer_base", self.layer_base),
            ("cross_arm_test", self.cross_arm_test),
            ("fisher_method", self.fisher_method),
            ("interval_ratio", self.interval_ratio),
            ("interval_diff", self.interval_diff),
            ("mc_band", self.mc_band),
            ("blocks_needed_sign_test", "%d" % self.blocks_needed_sign_test),
            ("blocks_needed_cluster", "%d" % self.blocks_needed_cluster),
            ("blocks_needed_fisher_exact", "%d" % self.blocks_needed_fisher_exact),
            ("sign_date", self.sign_date),
        ]


# ---------------------------------------------------------------- 小工具
def mc_band_p(ge, n_perm):
    """⚖⚖⚖ MC95% 不确定带：从 MC 计数 `(ge, n_perm)` 到 **p 尺度**的**精确**变换。

    ⚖ 零假设模拟的 p = `(ge+1)/(n_perm+1)` ⇒ p 的 MC 误差来自 `ge` 的误差
    ⇒ ① `wilson_bounds(ge, n_perm)` 给 `ge/n_perm` 的 95% 带
    ⇒ ② **单调变换** `x ↦ (x·n_perm+1)/(n_perm+1)` ⇒ 得到 p 尺度的带。
    ⚖⚠⚠ **与 244.64/244.65 的约定的差别**：那两处把 `wilson_bounds(ge, n_mc)`
    **直接**当 p 的带（那把 p 当成 `ge/n_mc` ⇒ 忽略了 +1 修正）
    ⇒ 两者相差 ≤ `1/(n_perm+1)`（本轮 ≈ 5.0e-5）
    ⇒ ⚖ 报告里把**最大差**印出来 ⇒ 不是两个真相，是一个更准 + 一个更粗。
    """
    lo, hi = iaud().wilson_bounds(ge, n_perm)
    d = n_perm + 1.0
    return ((lo * n_perm + 1.0) / d, (hi * n_perm + 1.0) / d)


def p_symbol(p, alpha):
    """⚖⚠⚠ **比较符号按真值算**（244.65 的教训：四位小数会印出「p=0.0500 ≥ 0.05」
    而真值在 α 下方 ⇒ 报告自相矛盾）。"""
    return "<" if p < alpha else "≥"


def fmt_p(p):
    """⚖ p 一律 **6 位小数**（K11）—— ⛔ 不用字符串截断（`"0.087782…"[:6]` 会印成 0.0877）。"""
    return "%.6f" % p


def fmt_pct(x, d=2):
    return ("%." + str(d) + "f") % (100.0 * x)


# ---------------------------------------------------------------- 数据层
def build_all(cfg, rows_by_arm=None):
    """⚖ 从**读数**算出逐档的：两臂改判数、差 pp、p 值、区间、块级、改判矩阵。"""
    VS, DC, DL = vsrc(), dconf(), dlayer()
    if rows_by_arm is None:
        rows_by_arm = {"w": VS.load_rows(JSONL_W), "rand": VS.load_rows(JSONL_RAND)}
    for arm in ARMS:
        if not rows_by_arm.get(arm):
            raise HardFail("%s 臂读数一条都没有 ⇒ **未量到**" % arm)
    out = {"cfg": cfg, "arm": {}, "axis": {}, "cross": [], "rows": {}}
    for arm in ARMS:
        recs = rows_by_arm[arm]
        ks, fr = DC.dose_cells(recs, zero_span=cfg.zero_span)
        if not ks:
            raise HardFail("%s 臂剂量轴没有格 ⇒ **未量到**" % arm)
        qs, bands = DC.dose_bands_v(ks, fr, boundary=cfg.boundary,
                                    quantile=cfg.quantile, n_bands=cfg.n_bands)
        rows = []
        for i, (lab, sub) in enumerate(bands):
            cells_by_tid = collections.OrderedDict()
            for r in sub:
                cells_by_tid.setdefault(r["tid"], []).append(r)
            cells = [c for cs in cells_by_tid.values() for c in cs]
            v_main = DL.layer_verdicts(cells_by_tid, DL.cell_sign_p9, DL.cell_zero_p9)
            v_alt = VS.p9delta_per_tid(cells)
            k_main = sum(1 for t in v_main if v_main[t]["verdict"])
            k_alt = sum(1 for t in v_alt if v_alt[t]["verdict"])
            # ⚖⚖⚖ 零格数取自**生产机械** `layer_verdicts`（`zero_fn` 必传）
            #   ⇒ ⛔ 不许自己另数一遍（那会让 `zero_fn` 变成**死参数** ⇒ 变异台抓不到）
            nzero = sum(v_main[t]["nzero"] for t in v_main)
            cellpos = sum(1 for c in cells if DL.cell_sign_p9(c))
            rows.append({
                "L": i, "label": lab, "n_cells": len(sub), "n_traj": len(v_main),
                "k": k_main, "n": len(v_main),
                "ratio": (float(k_main) / len(v_main)) if v_main else 0.0,
                "k_alt": k_alt, "n_alt": len(v_alt),
                "ratio_alt": (float(k_alt) / len(v_alt)) if v_alt else 0.0,
                "nzero": nzero, "cellpos": cellpos,
                "v_main": v_main, "v_alt": v_alt,
                "cells_by_tid": cells_by_tid,
            })
        out["arm"][arm] = {"ks": ks, "fr": fr, "qs": qs, "bands": bands, "rows": rows}
        out["axis"][arm] = {"qs": list(qs), "sizes": [len(b[1]) for b in bands],
                            "rho": DC.spearman(fr, [DC.d_of(r) for r in ks]),
                            "n_cells": len(ks)}
    # ⚖ 逐档的注入比例范围（供报告印「这一档是哪个剂量区间」）
    for arm in ARMS:
        a = out["arm"][arm]
        frac_by_id = dict((id(r), f) for r, f in zip(a["ks"], a["fr"]))
        for i, (_lab, sub) in enumerate(a["bands"]):
            frs = [frac_by_id[id(r)] for r in sub]
            a["rows"][i]["frac_lo"] = min(frs) if frs else None
            a["rows"][i]["frac_hi"] = max(frs) if frs else None
    # ---- 跨臂逐档 ----
    CP = cpre()
    w_rows = out["arm"]["w"]["rows"]
    r_rows = out["arm"]["rand"]["rows"]
    n_band = min(len(w_rows), len(r_rows))
    all_tids = sorted(set(r["tid"] for r in rows_by_arm["w"]))
    blocks = CP.blocks_of(all_tids, VS.problem_key)
    out["blocks"] = blocks
    for L in range(n_band):
        vw, vr = w_rows[L]["v_main"], r_rows[L]["v_main"]
        tids_w, tids_r = sorted(vw), sorted(vr)
        paired = (tids_w == tids_r)
        same_m = (all(vw[t]["m"] == vr[t]["m"] for t in tids_w)
                  if paired else False)
        diffs = [(1 if vw[t]["verdict"] else 0) - (1 if vr[t]["verdict"] else 0)
                 for t in tids_w] if paired else []
        p_perm, obs, ge, n_perm = (DL.paired_perm_geom(diffs, N_PERM, MC_SEED)
                                   if paired else (1.0, 0, 0, N_PERM))
        band_lo, band_hi = mc_band_p(ge, n_perm)
        kw, nw = w_rows[L]["k"], w_rows[L]["n"]
        kr, nr = r_rows[L]["k"], r_rows[L]["n"]
        pf, _po = armv().fisher_exact_two_sided(kw, nw - kw, kr, nr - kr)
        wlw, wuw = iaud().wilson_bounds(kw, nw)
        wlr, wur = iaud().wilson_bounds(kr, nr)
        nc = iaud().newcombe_diff(kw, nw, kr, nr)
        naive = iaud().naive_diff(kw, nw, kr, nr)
        mat = {"TT": 0, "TF": 0, "FT": 0, "FF": 0}
        for t in tids_w:
            a = 1 if vw[t]["verdict"] else 0
            b = 1 if vr[t]["verdict"] else 0
            mat["%s%s" % ("T" if a else "F", "T" if b else "F")] += 1
        # ---- 块级（K13）----
        sw = {t: (1 if vw[t]["verdict"] else -1) for t in tids_w}
        sr = {t: (1 if vr[t]["verdict"] else -1) for t in tids_r}
        bw = _block_verdicts(blocks, sw, set(tids_w))
        br = _block_verdicts(blocks, sr, set(tids_r))
        nb_ok = sum(1 for x in bw if x[1] is not None)
        bkw = sum(1 for x in bw if x[1] is True)
        bkr = sum(1 for x in br if x[1] is True)
        pbf = None
        if nb_ok:
            pbf, _ = armv().fisher_exact_two_sided(bkw, nb_ok - bkw, bkr, nb_ok - bkr)
        bdiffs = [(1 if (x[1] is True) else 0) - (1 if (y[1] is True) else 0)
                  for x, y in zip(bw, br) if x[1] is not None and y[1] is not None]
        bperm = (DL.paired_perm_geom(bdiffs, N_PERM, MC_SEED)[0] if bdiffs else 1.0)
        bnc = iaud().newcombe_diff(bkw, nb_ok, bkr, nb_ok) if nb_ok else (0.0, 0.0)
        out["cross"].append({
            "L": L, "label": w_rows[L]["label"],
            "paired": paired, "same_m": same_m,
            "kw": kw, "nw": nw, "kr": kr, "nr": nr,
            "pw": float(kw) / nw if nw else 0.0,
            "pr": float(kr) / nr if nr else 0.0,
            "diff_pp": 100.0 * ((float(kw) / nw if nw else 0.0)
                                - (float(kr) / nr if nr else 0.0)),
            "wilson_w": (wlw, wuw), "wilson_r": (wlr, wur),
            "newcombe": nc, "naive": naive,
            "fisher": pf, "p_perm": p_perm, "obs": obs, "ge": ge, "n_perm": n_perm,
            "band": (band_lo, band_hi),
            "border": (band_lo <= cfg.alpha <= band_hi),
            "matrix": mat, "diffs": diffs,
            "bkw": bkw, "bkr": bkr, "nb": nb_ok, "n_blocks": len(blocks),
            "block_fisher": pbf, "block_perm": bperm, "block_newcombe": bnc,
            "block_evaluable": nb_ok,
        })
    # ---- 功效预算（**规划量**，⛔ 不是判决）----
    layer_rows = [{"L": c["L"], "pw": c["pw"], "pr": c["pr"]} for c in out["cross"]]
    cells_per_traj = (float(out["axis"]["w"]["n_cells"])
                      / float(len(out["arm"]["w"]["rows"][0]["v_main"])))
    lines, size = dlayer().size_requirements(
        layer_rows, cells_per_traj, fisher_power=cpre().fisher_power,
        n_layer=cfg.n_bands)
    out["budget"] = {"lines": lines, "size": size, "cells_per_traj": cells_per_traj,
                     "n_blocks": len(blocks),
                     "n_traj_per_arm": len(out["arm"]["w"]["rows"][0]["v_main"])}
    return out


def _block_verdicts(blocks, signs, traj_set):
    """⚖ 逐块的块级判定 —— ⛔ 规则**只写一处**：`cluster_premise_audit.block_is_pos`。

    ⚖⚠⚠ 块内某条轨迹在**这一档**没有格 ⇒ 该块在这一档**不可评**
    ⇒ 记 `None`（**未量到**）⇒ ⛔ 不许当成 False 混进分母。
    """
    out = []
    for blk in blocks:
        if not all(t in traj_set for t in blk):
            out.append((blk, None))
            continue
        out.append((blk, cpre().block_is_pos(blk, signs)))
    return out


# ---------------------------------------------------------------- 报告
def build_report(A, cfg, prereg_raw, k_rows):
    """⚖ 出报告 + 判据（`F1`…`F12`）。返回 `(文本行, {判据号: bool})`。"""
    RP = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        RP.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    DL = dlayer()
    axis = A["axis"]
    cross = A["cross"]

    # ---- 【0】替身声明 ----
    RP.append("【0】%s⚖⚠⚠⚠⚖⚠ **本节不是「固定剂量那一批」的判决**" % STANDIN_MARK)
    RP.append("  · 那一批**还没跑**（要 GPU + 用户点头）⇒ **未量到**"
              "（见【B1】）")
    RP.append("  · 下面所有数字是**替身**：用**现有两批**（w / rand，"
              "**跨剂量混在一起**）跑通**同一条管线**")
    RP.append("  · 替身数字 ⛔ **不许**被引用成「固定剂量下改判多少题」"
              "（⛔ 剂量与机制在替身上**仍不可分辨**⇒【B8】）")
    RP.append("")

    # ---- 【1】生效口径 ----
    RP.append("【1】⚖ 生效口径（**全部来自预登记的机器可读块**；"
              "⛔ 本文件里没有写死任何一个）")
    for k, v in cfg.as_lines():
        RP.append("  · %s = %s" % (k, v))
    RP.append("  ℹ 预登记的 **K 清单**（原文，共 %d 条）：%s"
              % (len(k_rows), " / ".join(r[0] for r in k_rows)))
    RP.append("")

    # ---- 【2】逐档结果 ----
    RP.append("【2】⚖ 替身运行：逐档（=逐剂量区间）的两臂结果")
    for c in cross:
        a = A["arm"]["w"]["rows"][c["L"]]
        lo = a["frac_lo"]
        hi = a["frac_hi"]
        RP.append("  · 档 %d（%s%s）：w **%d/%d** = %.4f"
                  "（Wilson95 [%.4f, %.4f]）｜ rand **%d/%d** = %.4f"
                  "（Wilson95 [%.4f, %.4f]）"
                  % (c["L"], c["label"],
                     ("，注入比例 %.4f–%.4f" % (lo, hi)) if lo is not None else "",
                     c["kw"], c["nw"], c["pw"], c["wilson_w"][0], c["wilson_w"][1],
                     c["kr"], c["nr"], c["pr"], c["wilson_r"][0], c["wilson_r"][1]))
        RP.append("      · 差 **%+.2fpp**（Newcombe95 [%+.2f, %+.2f] pp）"
                  " ⇒ %s"
                  % (c["diff_pp"], 100.0 * c["newcombe"][0], 100.0 * c["newcombe"][1],
                     "**区间不含 0**" if (c["newcombe"][0] > 0 or c["newcombe"][1] < 0)
                     else "⚠⚠ **区间含 0 ⇒ 该档未量到**"))
        RP.append("      · 配对置换（K8，**结论口径**）p = %s %s α=%.6g"
                  "（MC95%% 带 [%.6f, %.6f]）⇒ %s"
                  " ｜ 精确 Fisher（K9，⛔ **只印不判**）p = %s"
                  % (fmt_p(c["p_perm"]), p_symbol(c["p_perm"], cfg.alpha), cfg.alpha,
                     c["band"][0], c["band"][1],
                     ("**未定**（带跨 α ⇒ 显著/不显著都没定）" if c["border"]
                      else ("**检出**" if c["p_perm"] < cfg.alpha else "**未检出**")),
                     fmt_p(c["fisher"]) if c["fisher"] is not None else "（不可评）"))
        m = c["matrix"]
        RP.append("      · 改判矩阵（%d 条配对轨迹）：两臂都改判 %d ｜ "
                  "**只 w 改判 %d** ｜ **只 rand 改判 %d** ｜ 都不改判 %d"
                  % (c["nw"], m["TT"], m["TF"], m["FT"], m["FF"]))
        RP.append("      · 块级（K13，%d 块中 %d 块可评）：w %d/%d ｜ rand %d/%d"
                  " ｜ Fisher p = %s（⛔ 分母是**块数** %d，⛔ 不是轨迹数 %d）"
                  " ｜ 配对置换 p = %s"
                  % (c["n_blocks"], c["nb"], c["bkw"], c["nb"], c["bkr"], c["nb"],
                     fmt_p(c["block_fisher"]) if c["block_fisher"] is not None
                     else "（不可评）",
                     c["nb"], c["nw"], fmt_p(c["block_perm"])))
        alt_w = A["arm"]["w"]["rows"][c["L"]]
        alt_r = A["arm"]["rand"]["rows"][c["L"]]
        same = (alt_w["k_alt"] == c["kw"] and alt_r["k_alt"] == c["kr"])
        RP.append("      · 另一条多数规则（K6b，零格**剔出**分母）：w %d/%d ｜ rand %d/%d"
                  " ⇒ %s（该档零格：w %d 个、rand %d 个）"
                  % (alt_w["k_alt"], alt_w["n_alt"], alt_r["k_alt"], alt_r["n_alt"],
                     "与主口径**相同**" if same else "⚠⚠ **与主口径不等**（load-bearing）",
                     alt_w["nzero"], alt_r["nzero"]))
    RP.append("")

    # ---- 【3】改判矩阵汇总 ----
    RP.append("【3】⚖ 改判矩阵汇总（逐档 2×2；⛔ **不是**判决，只是「差在哪」的结构）")
    for c in cross:
        m = c["matrix"]
        RP.append("  · 档 %d：TT %d ｜ TF %d ｜ FT %d ｜ FF %d"
                  % (c["L"], m["TT"], m["TF"], m["FT"], m["FF"]))
    RP.append("")

    # ---- 【4】功效预算表 ----
    RP.append("【4】⚖ 功效预算表（**规划量**，⛔ **不是判决**）")
    for ln in A["budget"]["lines"]:
        RP.append(ln)
    RP.append("    · 块级规模前提（**来自预登记**，244.59）：符号检验需 **%d 块** ｜"
              " 检出聚类需 **%d 块** ｜ 跨臂 Fisher（精确）需 **%d 块**"
              % (cfg.blocks_needed_sign_test, cfg.blocks_needed_cluster,
                 cfg.blocks_needed_fisher_exact))
    RP.append("    · **现有 %d 块**（%d 条轨迹/臂）⇒ 距预登记要求差 **%d/%d/%d 块**"
              " ⇒ ⚠⚠ **现有规模不够**（这是**规划量**，⛔ 不是判决）"
              % (A["budget"]["n_blocks"], A["budget"]["n_traj_per_arm"],
                 max(0, cfg.blocks_needed_sign_test - A["budget"]["n_blocks"]),
                 max(0, cfg.blocks_needed_cluster - A["budget"]["n_blocks"]),
                 max(0, cfg.blocks_needed_fisher_exact - A["budget"]["n_blocks"])))
    RP.append("")

    # ---- 【5】留白（**必须排在判据之前** ⇒ 判据 F11 数得到标记）----
    RP.append("【5】⚖ 留白（**未量到** ⇒ ⛔ 不许说成「无差异」）")
    for head, body in BLANKS:
        RP.append("  %s %s：%s" % (head, "", body))
    RP.append("")

    # ---- 判据 ----
    RP.append("【6】⚖ 判据（每条都**能红**；反例见 `selftest`）")

    # F1 预登记机器块 + K 清单齐全
    ok1 = True
    miss_k = [k for k in PREREG_K_IDS if k not in [r[0] for r in k_rows]]
    miss_raw = [k for k in PREREG_KEYS if k not in (prereg_raw or {})]
    ok1 = (not miss_k) and (not miss_raw)
    put("F1", ok1,
        "预登记必须**机器块 17 键齐全**且 **K 清单 K1–K13 齐全**"
        "（缺键 ⇒ 口径会被静默兜底 ⇒ 必须红）：缺机器键 %s ｜ 缺 K %s"
        % (miss_raw or "无", miss_k or "无"))

    # F2 口径确实来自预登记（生效口径 == 文件；且文件被改 ⇒ 输出必须变）
    ok2 = True
    d2 = []
    for k, v in cfg.as_lines():
        rv = (prereg_raw or {}).get(k)
        if k in ("alpha",):
            same = (rv is not None and abs(float(rv) - float(v)) < 1e-12)
        elif k in ("n_bands", "blocks_needed_sign_test", "blocks_needed_cluster",
                   "blocks_needed_fisher_exact"):
            same = (rv is not None and int(rv) == int(v))
        else:
            same = (rv is not None and str(rv) == str(v))
        ok2 = ok2 and same
        if not same:
            d2.append("%s: 生效 %r vs 预登记 %r" % (k, v, rv))
    put("F2", ok2,
        "**生效口径必须逐项等于预登记文件**（⛔ 不许代码里写死）：%s"
        % ("；".join(d2) if d2 else "17 项逐项一致"))

    # F3 剂量轴逐位复现 244.50（证明读的是同一批数据 + 同一套分档器）
    ok3 = True
    d3 = []
    for arm in ARMS:
        ax = axis[arm]
        want_q = AXIS_QUANTILES
        want_s = AXIS_BAND_SIZE
        want_r = AXIS_RHO if arm == "w" else AXIS_RHO_RAND
        gq = (len(ax["qs"]) == len(want_q)
              and all(abs(a - b) <= 5e-4 for a, b in zip(ax["qs"], want_q)))
        gs = (tuple(ax["sizes"]) == tuple(want_s))
        gr = (abs(ax["rho"] - want_r) <= 5e-4)
        ok3 = ok3 and gq and gs and gr
        d3.append("%s 分位点 %s%s ｜ 档 %s%s ｜ rho %+.4f（期望 %+.4f）%s"
                  % (arm, "/".join("%.3f" % q for q in ax["qs"]),
                     "✅" if gq else "❌",
                     "/".join(str(x) for x in ax["sizes"]), "✅" if gs else "❌",
                     ax["rho"], want_r, "✅" if gr else "❌"))
    n_decl = cfg.n_bands
    n_act = len(A["arm"]["w"]["rows"])
    ok3 = ok3 and (n_decl == n_act)
    d3.append("声明档数 %d vs 实际 %d %s" % (n_decl, n_act,
                                            "✅" if n_decl == n_act else "❌"))
    put("F3", ok3, "剂量轴必须**逐位复现 244.50**（先证明「读的是同一批」）：%s"
        % "；".join(d3))

    # F4 跨臂配对前提：同一剂量档、同一批轨迹、逐条格数相同
    ok4 = all(c["paired"] and c["same_m"] for c in cross) and len(cross) > 0
    d4 = ["档 %d：配对 %s ｜ 逐条格数相同 %s"
          % (c["L"], "✅" if c["paired"] else "❌",
             "✅" if c["same_m"] else "❌") for c in cross]
    put("F4", ok4,
        "**「固定剂量」的前提**：两臂在**同一档**必须是**同一批轨迹、逐条格数相同**"
        "（否则跨臂比较无意义 ⇒ 必须红）：%s" % "；".join(d4))

    # F5 两条多数规则并报（K6 / K6b）
    ok5 = True
    d5 = []
    n_alt_marks = DL._count_mark(RP, "另一条多数规则")
    ok5 = ok5 and (n_alt_marks == len(cross))
    d5.append("印了 %d/%d 档" % (n_alt_marks, len(cross)))
    # ⚖⚠⚠⚠⚖ **判据侧独立重算**（⛔ 不可从被检对象自身派生 ⇒ 否则恒绿）：
    #   ① K6b 的计数 = 「逐轨迹 `d>0` 的格数 > `d<0` 的格数」（用生产 `d_of` 重算）
    #   ② 零格数 = 「逐格 `d == 0`」（用生产 `d_of` 重算）
    #   ⇒ 这两条都**不**经过 `p9delta_per_tid` / `layer_verdicts` ⇒ 抓得住「K6b 取自被检对象」
    DC = dconf()
    for arm in ARMS:
        a = A["arm"][arm]
        for row in a["rows"]:
            cells = [c for cs in row["cells_by_tid"].values() for c in cs]
            nz_re = 0
            per_tid = collections.OrderedDict()
            for c in cells:
                d = DC.d_of(c)
                if d == 0.0:
                    nz_re += 1
                else:
                    e = per_tid.setdefault(c["tid"], [0, 0])
                    if d > 0:
                        e[0] += 1
                    else:
                        e[1] += 1
            alt_re = sum(1 for _t, (p, n) in per_tid.items() if p > n)
            same_alt = (alt_re == row["k_alt"]) and (len(per_tid) == row["n_alt"])
            same_nz = (nz_re == row["nzero"])
            ok5 = ok5 and same_alt and same_nz
            if not (same_alt and same_nz):
                d5.append("%s 档 %d：K6b 印 %s（重算 %d）%s ｜ 零格印 %d（重算 %d）%s"
                          % (arm, row["L"], row["k_alt"], alt_re,
                             "✅" if same_alt else "❌", row["nzero"], nz_re,
                             "✅" if same_nz else "❌"))
    differ = [c["L"] for c in cross
              if (A["arm"]["w"]["rows"][c["L"]]["k_alt"] != c["kw"]
                  or A["arm"]["rand"]["rows"][c["L"]]["k_alt"] != c["kr"])]
    RP.append("    ℹ 两条多数规则**不等**的档：%s"
              % (differ if differ else "无（本批两臂在四档上恰好一致）"))
    put("F5", ok5,
        "**两条多数规则必须同时报出**（K6 主口径 + K6b 零格剔出分母）"
        "⇒ 每一档都要有「另一条多数规则」这一行（少印一条必须红）"
        "⇒ 且 K6b 的计数与零格数必须能由**生产 `d_of` 独立重算**出来：%s"
        % ("；".join(d5) if d5 else "逐档重算一致"))

    # F6 区间方法：比例用 Wilson95、差用 Newcombe95（⛔ 不是两个 CI 相减）
    ok6 = True
    d6 = []
    for c in cross:
        nd = iaud().newcombe_diff(c["kw"], c["nw"], c["kr"], c["nr"])
        nv = iaud().naive_diff(c["kw"], c["nw"], c["kr"], c["nr"])
        same_new = abs(nd[0] - c["newcombe"][0]) < 1e-12 and abs(nd[1] - c["newcombe"][1]) < 1e-12
        diff_naive = (abs(nd[0] - nv[0]) > 1e-9 or abs(nd[1] - nv[1]) > 1e-9)
        wl = iaud().wilson_bounds(c["kw"], c["nw"])
        cp = iaud().cp95(c["kw"], c["nw"])
        diff_cp = (abs(wl[0] - cp[0]) > 1e-9 or abs(wl[1] - cp[1]) > 1e-9)
        # ⚖⚖⚖ 印出的比例区间必须**就是** Wilson95（⛔ 不能是 CP95）
        same_w = (abs(wl[0] - c["wilson_w"][0]) < 1e-12
                  and abs(wl[1] - c["wilson_w"][1]) < 1e-12)
        ok6 = ok6 and same_new and diff_naive and diff_cp and same_w
        d6.append("档 %d：Newcombe %s ｜ 与「CI 相减」不同 %s ｜ Wilson≠CP %s"
                  " ｜ 印出的比例区间=Wilson95 %s"
                  % (c["L"], "✅" if same_new else "❌",
                     "✅" if diff_naive else "❌", "✅" if diff_cp else "❌",
                     "✅" if same_w else "❌"))
    put("F6", ok6,
        "区间必须**比例=Wilson95、差=Newcombe95**（⛔ 不许两个 CI 相减）"
        "⇒ 报告里的差区间必须与 `newcombe_diff` 逐位相同、且**必须**与错误的"
        "「CI 相减」**不同**、Wilson 必须与 CP95 **不同**：%s" % "；".join(d6))

    # F7 精确 Fisher（⛔ 不是正态近似）：已知答案夹具 + 报告里的 p 可由 (k,n) 复算
    ok7 = True
    d7 = []
    tab, want = FISHER_FIXTURE
    got, _ = armv().fisher_exact_two_sided(*tab)
    same_fix = abs(got - want) < 1e-12
    ok7 = ok7 and same_fix
    d7.append("已知答案夹具 %s ⇒ p=%.12f（期望 %.12f，R `fisher.test` 双尾）%s"
              % (list(tab), got, want, "✅" if same_fix else "❌"))
    for c in cross:
        pv, _ = armv().fisher_exact_two_sided(c["kw"], c["nw"] - c["kw"],
                                               c["kr"], c["nr"] - c["kr"])
        same = (pv is not None and c["fisher"] is not None
                and abs(pv - c["fisher"]) < 1e-12)
        ok7 = ok7 and same
        if not same:
            d7.append("档 %d 的 Fisher p 复算不一致 ❌" % c["L"])
    put("F7", ok7,
        "跨臂 Fisher 必须**精确枚举**（⛔ 不用正态近似）⇒ 已知答案夹具 + "
        "报告里的每个 p 必须能由印出的 (k, n) **复算**出来：%s" % "；".join(d7))

    # F8 配对置换 + MC 带
    ok8 = True
    d8 = []
    sig = inspect.signature(dlayer().paired_perm_geom).parameters
    same_def = (sig["n_perm"].default == N_PERM and sig["seed"].default == MC_SEED)
    ok8 = ok8 and same_def
    d8.append("置换参数与机械默认值一致 %s（本文件 N_PERM=%d / MC_SEED=%d）"
              % ("✅" if same_def else "❌", N_PERM, MC_SEED))
    for c in cross:
        # ⚖⚖⚖ **判据侧独立重算 MC 带**（⛔ 不调本文件自己的 `mc_band_p`，
        #   否则「带算错」时判据与被检对象一起错 ⇒ **恒绿**）
        #   ⇒ 用外部机械 `interval_audit.wilson_bounds` + 文档里的单调变换
        _wl, _wh = iaud().wilson_bounds(c["ge"], c["n_perm"])
        _dd = c["n_perm"] + 1.0
        lo = (_wl * c["n_perm"] + 1.0) / _dd
        hi = (_wh * c["n_perm"] + 1.0) / _dd
        same_b = (abs(lo - c["band"][0]) < 1e-12 and abs(hi - c["band"][1]) < 1e-12)
        brack = (c["band"][0] - 1e-12) <= c["p_perm"] <= (c["band"][1] + 1e-12)
        bord = (c["band"][0] <= cfg.alpha <= c["band"][1])
        # ⚖⚠⚠ **比较符号按真值**（244.65 的坑：印出「p=0.0500 ≥ 0.05」而真值在下方）
        want = "p = %s %s α=%.6g" % ("%.6f" % c["p_perm"],
                                     "<" if c["p_perm"] < cfg.alpha else "≥",
                                     cfg.alpha)
        sym_ok = any(want in ln for ln in RP)
        ok8 = ok8 and same_b and brack and (bord == c["border"]) and sym_ok
        d8.append("档 %d：带可复算 %s ｜ 带包住 p %s ｜ 跨 α 标志一致 %s ｜ 符号正确 %s"
                  % (c["L"], "✅" if same_b else "❌", "✅" if brack else "❌",
                     "✅" if bord == c["border"] else "❌",
                     "✅" if sym_ok else "❌"))
    # 已知答案：全零差 ⇒ p 必须 1.0
    p0, obs0, ge0, n0 = dlayer().paired_perm_geom([0] * 14, N_PERM, MC_SEED)
    null_ok = (abs(p0 - 1.0) < 1e-12 and obs0 == 0)
    ok8 = ok8 and null_ok
    d8.append("已知答案（14 条全零差）⇒ p=%.12f（期望 1.0）%s"
              % (p0, "✅" if null_ok else "❌"))
    put("F8", ok8,
        "配对置换 + **MC 不确定带**（K11）必须可复算、带必须包住 p、"
        "「带跨 α」必须**从带重算**（⛔ 不许读一个现成的标志）：%s" % "；".join(d8))

    # F9 块级口径并报（K13）：分母是块数，不是轨迹数
    ok9 = True
    d9 = []
    n_blk_marks = DL._count_mark(RP, "块级（K13，")
    for c in cross:
        good = (c["nb"] == c["n_blocks"]) and (c["nb"] != c["nw"] or c["nw"] == c["nb"])
        ok9 = ok9 and good
        d9.append("档 %d：块分母 %d（轨迹 %d）%s"
                  % (c["L"], c["nb"], c["nw"], "✅" if good else "❌"))
    ok9 = ok9 and (n_blk_marks == len(cross))
    d9.append("印出块级行 %d/%d 档" % (n_blk_marks, len(cross)))
    # ⚖⚖⚖ **判据侧用「生产机械」重算块级计数**（`blocks_of` + `block_is_pos`）
    #   ⇒ 抓「块级规则被换掉 / 块被拆错」，⛔ 不从被检对象自身派生
    CP, VS = cpre(), vsrc()
    all_tids = sorted(A["arm"]["w"]["rows"][0]["v_main"])
    prod_blocks = CP.blocks_of(all_tids, VS.problem_key)
    for c in cross:
        for arm, field in (("w", "bkw"), ("rand", "bkr")):
            row = A["arm"][arm]["rows"][c["L"]]
            v = row["v_main"]
            signs = dict((t, (1 if v[t]["verdict"] else -1)) for t in v)
            ks = 0
            nb = 0
            for blk in prod_blocks:
                if not all(t in signs for t in blk):
                    continue
                nb += 1
                if CP.block_is_pos(blk, signs):
                    ks += 1
            same = (ks == c[field]) and (nb == c["nb"])
            ok9 = ok9 and same
            if not same:
                d9.append("档 %d %s：块级印 %d/%d，生产机械重算 %d/%d ❌"
                          % (c["L"], arm, c[field], c["nb"], ks, nb))
    put("F9", ok9,
        "**块级口径必须同时报**（K13：前提独立性未量到 ⇒ 块级与轨迹级并报）"
        "⇒ 分母必须是**块数**（⛔ 不是轨迹数）"
        "⇒ 且块级计数必须与**生产机械** `block_is_pos` 重算一致：%s"
        % "；".join(d9))

    # F12 改判矩阵必须完备，且与两臂计数对账
    ok12 = True
    d12 = []
    for c in cross:
        m = c["matrix"]
        tot = m["TT"] + m["TF"] + m["FT"] + m["FF"]
        good = (tot == c["nw"]) and (m["TT"] + m["TF"] == c["kw"]) \
            and (m["TT"] + m["FT"] == c["kr"])
        ok12 = ok12 and good
        d12.append("档 %d：合计 %d（应 %d）｜ TT+TF=%d（应 w %d）｜ TT+FT=%d（应 rand %d）%s"
                   % (c["L"], tot, c["nw"], m["TT"] + m["TF"], c["kw"],
                      m["TT"] + m["FT"], c["kr"], "✅" if good else "❌"))
    put("F12", ok12,
        "**改判矩阵必须完备**（TT+TF+FT+FF = 配对轨迹数）"
        "⇒ 且 TT+TF 必须等于 w 的改判数、TT+FT 必须等于 rand 的改判数：%s"
        % "；".join(d12))

    # F10 功效预算表
    ok10 = True
    d10 = []
    for k in ("blocks_needed_sign_test", "blocks_needed_cluster",
              "blocks_needed_fisher_exact"):
        v = getattr(cfg, k)
        good = (v > 0) and (A["budget"]["n_blocks"] < v)
        ok10 = ok10 and good
        d10.append("%s=%d（现有 %d 块 ⇒ 不足 %s）"
                   % (k, v, A["budget"]["n_blocks"],
                      "✅" if good else "❌"))
    ok10 = ok10 and (len(A["budget"]["lines"]) > 0) and (len(A["budget"]["size"]) > 0)
    d10.append("预算行 %d 条、逐层规模 %d 条"
               % (len(A["budget"]["lines"]), len(A["budget"]["size"])))
    # ⚖⚖⚖ 预算表必须**真的印在报告里**（⛔ 只在数据里存在不算数）
    n_size_marks = DL._count_mark(RP, "正态近似规模")
    ok10 = ok10 and (n_size_marks == len(cross))
    d10.append("印出逐档规模行 %d/%d 档" % (n_size_marks, len(cross)))
    # ⚖⚖⚖ **与 244.60 登记的逐层规模对照**（独立来源 ⇒ 能抓「预算表算错」）
    for L, want in sorted(LEDGER_LAYER_SIZES.items()):
        got = A["budget"]["size"].get(L, {}).get("approx")
        same = (got is not None and int(got) == int(want))
        ok10 = ok10 and same
        d10.append("档 %d 规模 %s/臂 vs 244.60 登记 %d/臂 %s"
                   % (L, got, want, "✅" if same else "❌"))
    put("F10", ok10,
        "**功效预算表**必须给出「那一批要多少题/块」（**规划量**，⛔ 不是判决），"
        "且逐档规模必须与 **244.60 登记值**一致：%s" % "；".join(d10))

    # F11 替身标注 + 留白清单齐全
    ok11 = True
    d11 = []
    n_standin = DL._count_mark(RP, STANDIN_MARK)
    ok11 = ok11 and (n_standin >= 1)
    d11.append("替身标记出现 %d 次" % n_standin)
    for mark in BLANK_MARKS:
        n = DL._count_mark(RP, mark)
        ok11 = ok11 and (n >= 1)
        d11.append("%s×%d" % (mark, n))
    put("F11", ok11,
        "**替身标注 + 留白清单**必须齐全（⛔ 没量到的要**留白**，"
        "⛔ 不许说成「无差异」）：%s" % " ".join(d11))

    # ---- 【6】留白（**未量到** ⇒ ⛔ 不许说成「无差异」）——
    RP.append("")
    return RP, R


# ---------------------------------------------------------------- 自检
def selftest():
    """⚖ 自检：**已知答案夹具** + **每条判据的红化验证**（⛔ 判据不许恒绿）。"""
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # ---- 已知答案夹具 ----
    tab, want = FISHER_FIXTURE
    got, _ = armv().fisher_exact_two_sided(*tab)
    chk("T1", abs(got - want) < 1e-12,
        "精确 Fisher 已知答案 %s ⇒ %.12f（期望 %.12f）" % (list(tab), got, want))
    p0, obs0, _ge, _n = dlayer().paired_perm_geom([0] * 14, N_PERM, MC_SEED)
    chk("T2", abs(p0 - 1.0) < 1e-12 and obs0 == 0,
        "配对置换已知答案（14 条全零差）⇒ p=%.12f（期望 1.0）" % p0)
    lo, hi = mc_band_p(0, N_PERM)
    # ⚖ 已知答案：`ge = 0` ⇒ p 的**下端恰是** `1/(n_perm+1)`（p = (ge+1)/(n_perm+1)
    #   ⇒ 最小的可能 p）⇒ ⛔ 不是 0（那是「把 p 当 ge/n_perm」那个粗口径的答案）
    # ⚖ 上端：Wilson 上端(0/n) ≈ z²/n = 3.8415/20000 = 1.92e-4
    #   ⇒ p 上端 = (1.92e-4·20000 + 1)/20001 = 4.84/20001 ≈ 2.42e-4
    chk("T3", abs(lo - 1.0 / (N_PERM + 1.0)) < 1e-15 and 2.0e-4 < hi < 3.0e-4,
        "MC 带变换：ge=0 ⇒ p 带 [%.8f, %.8f]"
        "（下端 = 1/(n+1) = %.8f，上端 ≈ 2.42e-4）" % (lo, hi, 1.0 / (N_PERM + 1.0)))
    w = iaud().wilson_bounds(12, 14)
    chk("T4", abs(w[0] - 0.6005862050302965) < 1e-12,
        "Wilson 已知答案（12/14）⇒ [%.12f, %.12f]" % w)
    nc = iaud().newcombe_diff(12, 14, 6, 14)
    nv = iaud().naive_diff(12, 14, 6, 14)
    chk("T5", abs(nc[0] - 0.0734623890946891) < 1e-12 and abs(nc[1] - 0.6666546381180075) < 1e-12,
        "Newcombe 已知答案（12/14 vs 6/14）⇒ [%.12f, %.12f]" % nc)
    chk("T6", abs(nc[0] - nv[0]) > 1e-6,
        "Newcombe 与「CI 相减」**不同**（%.12f vs %.12f）⇒ F6 的负向对照有效"
        % (nc[0], nv[0]))
    sig = inspect.signature(dlayer().paired_perm_geom).parameters
    chk("T7", sig["n_perm"].default == N_PERM and sig["seed"].default == MC_SEED,
        "置换参数与机械默认值一致（⛔ 两处各写一份必红）")

    # ---- 预登记读取 ----
    raw = read_prereg(PREREG)
    chk("T8", all(k in raw for k in PREREG_KEYS),
        "预登记机器块 %d 键齐全" % len(PREREG_KEYS))
    krows = prereg_k_rows(PREREG)
    chk("T9", [r[0] for r in krows] == list(PREREG_K_IDS),
        "预登记 K 清单 = %s" % " ".join(r[0] for r in krows))
    try:
        read_prereg(os.path.join(HERE, "_no_such_prereg.md"))
        chk("T10", False, "缺预登记文件必须 HardFail（⛔ 不许兜底）")
    except HardFail:
        chk("T10", True, "缺预登记文件 ⇒ HardFail ✅")
    # T16：机器块**缺键** ⇒ 必须 HardFail（⛔ 不许用默认值兜底）
    tmp_dir0 = os.path.join(HERE, "_fd_selftest_tmp")
    if not os.path.isdir(tmp_dir0):
        os.makedirs(tmp_dir0)
    try:
        src0 = io.open(PREREG, encoding="utf-8").read()
        pk = os.path.join(tmp_dir0, "prereg_nokey.md")
        io.open(pk, "w", encoding="utf-8").write(
            src0.replace("alpha = 0.05\n", ""))
        try:
            read_prereg(pk)
            chk("T16", False, "机器块缺 `alpha` 必须 HardFail（⛔ 不许兜底）")
        except HardFail:
            chk("T16", True, "机器块缺 `alpha` ⇒ HardFail ✅")
        finally:
            if os.path.isfile(pk):
                os.remove(pk)
    finally:
        if os.path.isdir(tmp_dir0):
            try:
                os.rmdir(tmp_dir0)
            except OSError:
                pass

    cfg = Cfg(raw)
    rows_by_arm = {"w": vsrc().load_rows(JSONL_W),
                   "rand": vsrc().load_rows(JSONL_RAND)}
    A = build_all(cfg, rows_by_arm)
    RP, R = build_report(A, cfg, raw, krows)
    chk("T11", all(R.values()),
        "基准运行：判据全绿（%d/%d）" % (sum(1 for v in R.values() if v), len(R)))
    chk("T12", set(R.keys()) == set(CRITERION_IDS),
        "判据编号齐全：%s" % " ".join(sorted(R.keys(), key=lambda x: int(x[1:]))))

    # ---- **每条判据的红化验证**（⛔ 恒绿的判据在这里会露馅）----
    import copy

    def rerun(a_obj, c_obj, r_obj, k_obj):
        return build_report(a_obj, c_obj, r_obj, k_obj)[1]

    # F1：机器块缺键 ⇒ 红
    r_bad = dict(raw)
    r_bad.pop("alpha")
    R1 = rerun(A, cfg, r_bad, krows)
    chk("M1", (not R1["F1"]), "F1：机器块缺 `alpha` ⇒ 必须红")
    k_bad = [r for r in krows if r[0] != "K7"]
    R2 = rerun(A, cfg, raw, k_bad)
    chk("M2", (not R2["F1"]), "F1：K 清单缺 K7 ⇒ 必须红")

    # F2：生效口径与预登记不符 ⇒ 红
    cfg_bad = copy.deepcopy(cfg)
    cfg_bad.n_bands = 3
    R3 = rerun(A, cfg_bad, raw, krows)
    chk("M3", (not R3["F2"]), "F2：生效档数 3 vs 预登记 4 ⇒ 必须红")

    # F3：剂量轴被改坏 ⇒ 红
    A_bad = copy.deepcopy(A)
    A_bad["axis"]["w"]["sizes"] = [1, 2, 3, 4]
    R4 = rerun(A_bad, cfg, raw, krows)
    chk("M4", (not R4["F3"]), "F3：档表被改坏 ⇒ 必须红")

    # F4：跨臂配对前提被破坏 ⇒ 红
    A_bad = copy.deepcopy(A)
    A_bad["cross"][0]["paired"] = False
    R5 = rerun(A_bad, cfg, raw, krows)
    chk("M5", (not R5["F4"]), "F4：配对前提被破坏 ⇒ 必须红")

    # F5：K6b 的计数被改坏 ⇒ 红
    A_bad = copy.deepcopy(A)
    A_bad["arm"]["w"]["rows"][0]["k_alt"] = 999
    R6 = rerun(A_bad, cfg, raw, krows)
    chk("M6", (not R6["F5"]), "F5：K6b 的计数被改坏 ⇒ 必须红")

    # F6：差区间被换成「CI 相减」⇒ 红
    A_bad = copy.deepcopy(A)
    A_bad["cross"][0]["newcombe"] = A_bad["cross"][0]["naive"]
    R7 = rerun(A_bad, cfg, raw, krows)
    chk("M7", (not R7["F6"]), "F6：差区间被换成「CI 相减」⇒ 必须红")

    # F7：Fisher p 被换成别的数 ⇒ 红
    A_bad = copy.deepcopy(A)
    A_bad["cross"][0]["fisher"] = 0.0126
    R8 = rerun(A_bad, cfg, raw, krows)
    chk("M8", (not R8["F7"]), "F7：Fisher p 被改 ⇒ 必须红")

    # F8：MC 带被改坏 ⇒ 红
    A_bad = copy.deepcopy(A)
    A_bad["cross"][0]["band"] = (0.0, 0.0)
    R9 = rerun(A_bad, cfg, raw, krows)
    chk("M9", (not R9["F8"]), "F8：MC 带被改坏 ⇒ 必须红")

    # F9：块分母被换成轨迹数 ⇒ 红
    A_bad = copy.deepcopy(A)
    for c in A_bad["cross"]:
        c["nb"] = c["nw"]
    R10 = rerun(A_bad, cfg, raw, krows)
    chk("M10", (not R10["F9"]), "F9：块分母被换成轨迹数 ⇒ 必须红")

    # F10：预算表被删 ⇒ 红
    A_bad = copy.deepcopy(A)
    A_bad["budget"]["lines"] = []
    A_bad["budget"]["size"] = {}
    R11 = rerun(A_bad, cfg, raw, krows)
    chk("M11", (not R11["F10"]), "F10：功效预算表被删 ⇒ 必须红")

    # F11：留白被删 ⇒ 红
    global BLANKS
    saved = BLANKS
    BLANKS = saved[:4]
    try:
        R12 = rerun(A, cfg, raw, krows)
        chk("M12", (not R12["F11"]), "F11：留白被删 ⇒ 必须红")
    finally:
        BLANKS = saved

    # F12：改判矩阵被写死 ⇒ 红
    A_bad = copy.deepcopy(A)
    for c in A_bad["cross"]:
        c["matrix"] = {"TT": 0, "TF": 0, "FT": 0, "FF": 0}
    R13 = rerun(A_bad, cfg, raw, krows)
    chk("M13", (not R13["F12"]), "F12：改判矩阵被写死 ⇒ 必须红")

    # F9：块级规则被换（用生产机械重算 ⇒ 必须红）
    A_bad = copy.deepcopy(A)
    A_bad["cross"][0]["bkw"] = A_bad["cross"][0]["bkw"] + 1
    R14 = rerun(A_bad, cfg, raw, krows)
    chk("M14", (not R14["F9"]), "F9：块级计数被改 ⇒ 必须红")

    # ---- 口径**活体**变异：改预登记 ⇒ 输出必须变（F2 的活体验）----
    tmp_dir = os.path.join(HERE, "_fd_selftest_tmp")
    if not os.path.isdir(tmp_dir):
        os.makedirs(tmp_dir)
    try:
        src = io.open(PREREG, encoding="utf-8").read()
        p3 = os.path.join(tmp_dir, "prereg_3bands.md")
        io.open(p3, "w", encoding="utf-8").write(
            src.replace("n_bands = 4", "n_bands = 3"))
        raw3 = read_prereg(p3)
        cfg3 = Cfg(raw3)
        A3 = build_all(cfg3, rows_by_arm)
        chk("T13", len(A3["arm"]["w"]["rows"]) == 3,
            "**活体变异**：预登记改成 3 档 ⇒ 实际档数 %d（期望 3）"
            % len(A3["arm"]["w"]["rows"]))
        pz = os.path.join(tmp_dir, "prereg_drop.md")
        io.open(pz, "w", encoding="utf-8").write(
            src.replace("zero_span = keep", "zero_span = drop"))
        rawz = read_prereg(pz)
        cfgz = Cfg(rawz)
        Az = build_all(cfgz, rows_by_arm)
        # ⚖⚠⚠ **只有 rand 臂的 k 格里有零格**（w 臂 0 个）⇒ 「drop」只动 rand 臂
        #   ⇒ 判据必须盯**那个**臂，否则会拿一个「本来就没零格」的臂当证据
        nz_keep_w = A["axis"]["w"]["n_cells"]
        nz_drop_w = Az["axis"]["w"]["n_cells"]
        nz_keep_r = A["axis"]["rand"]["n_cells"]
        nz_drop_r = Az["axis"]["rand"]["n_cells"]
        chk("T14", (nz_drop_r < nz_keep_r) and (nz_drop_w == nz_keep_w),
            "**活体变异**：预登记改成 zero_span=drop ⇒ rand 臂格数 %d → %d（必须变）"
            " ｜ w 臂 %d → %d（w 臂**没有**零格 ⇒ 不变才对）"
            % (nz_keep_r, nz_drop_r, nz_keep_w, nz_drop_w))
        pa = os.path.join(tmp_dir, "prereg_alpha.md")
        io.open(pa, "w", encoding="utf-8").write(
            src.replace("alpha = 0.05", "alpha = 0.01"))
        cfga = Cfg(read_prereg(pa))
        chk("T15", abs(cfga.alpha - 0.01) < 1e-12,
            "**活体变异**：预登记 α 改成 0.01 ⇒ 生效 α = %.6g" % cfga.alpha)
    finally:
        for f in ("prereg_3bands.md", "prereg_drop.md", "prereg_alpha.md"):
            p = os.path.join(tmp_dir, f)
            if os.path.isfile(p):
                os.remove(p)
        if os.path.isdir(tmp_dir):
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass

    print("")
    print("自检：%d 通过 / %d 失败" % (len(ok), len(bad)))
    if bad:
        print("失败项：%s" % " ".join(bad))
    return (not bad)


def main():
    ap = argparse.ArgumentParser(description="固定剂量 / 分层剂量批次的分析管线（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--prereg", default=PREREG)
    args = ap.parse_args()
    if args.selftest:
        return 0 if selftest() else 1
    try:
        raw = read_prereg(args.prereg)
        krows = prereg_k_rows(args.prereg)
        cfg = Cfg(raw)
        A = build_all(cfg)
        RP, R = build_report(A, cfg, raw, krows)
    except HardFail as e:
        print("PRECOND_FAIL: %s" % e, file=sys.stderr)
        return 2
    print("\n".join(RP))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
    return 0 if all(R.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
