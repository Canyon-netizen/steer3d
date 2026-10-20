#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dose_convention_audit.py —— 剂量轴的**口径**不确定性会不会动摇 244.62 的结论（零 GPU，修订 244.63）

🔴🔴 **本工具问什么**

  244.62 刚把 244.60 的「剂量—响应只出现在 w 臂」**撤回并更正**成：
  「**w 臂的剂量—响应稳健**（全部扰动场景 p=0.0002）；**rand 臂的剂量趋势在 α 边界附近，
  检出与否随扰动翻转** ⇒ 只能说 rand 臂未能在 α 上检出剂量趋势」。

  ⚖⚠⚠⚠ **但那个扰动族只动了一个维度：分母 `P` 的 ±4 token 平移。**
  ⚖⚠⚠⚠⚖ **剂量轴的「口径」本身从来没被扰动过** —— 而口径有三个维度：

    ① **档边界约定**：生产 `f<=q1` / `q1<f<=q2` / `q2<f<=q3` / `f>q3`
                    变体 `f<q1`  / `q1<=f<q2` / `q2<=f<q3` / `f>=q3`
    ② **四分位算法**：`statistics.quantiles(fr, n=4)` 的 `inclusive`（生产默认）vs `exclusive`
    ③ **零跨度格**（`d == 0`）进不进剂量轴

  ⇒ 2 × 2 × 2 = **8 个组合**，本工具**全部枚举**（⛔ 不抽样）。

⚖⚖⚖ **本工具的立场（先说结论的形状，数字全部由实测算出来再印）**

  · 判决口径 = 244.60 那条结论：**(w 趋势 MC p < α) ∧ (rand 趋势 MC p ≥ α)**
  · 244.62 的更正措辞 = **rand 臂「未能在 α 上检出」是**基准口径下**的陈述**
    ⇒ 若换一个**口径**就检出 ⇒ 那句话**不是稳健性质** ⇒ 必须**再收窄**。

⚖ **复用的机械（⛔ 不另写第二套真相）**
  · 剂量轴（格集合 / 分档）：`dose_confound_audit.dose_cells` / **`dose_bands_v`**
    （244.63 参数化后的**唯一实现**；生产口径 = `dose_bands_v(ks, fr, "prod", "inclusive")`
    ⇒ 变体与生产口径**不可能**悄悄分叉）
  · 244.60 那条结论的判定式：`dose_fragility_audit.verdict_of`（**唯一实现**；本文件只转发）
  · 层内零假设基准：`dose_layer_audit.majority_base_p`（⛔ **不是 0.5**）
  · 层内多数：`dose_layer_audit.layer_verdicts` / `cell_sign_p9`
  · 剂量趋势 MC：`dose_layer_audit.mc_trend_p_geom`（**尊重每条轨迹的 nz 与平票规则**）
  · 跨臂配对置换：`dose_layer_audit.paired_perm_p`
  · 精确符号检验：`r227_kcurve.sign_test`（⛔ 不手抄第二份）
  · 区间：`interval_audit.wilson_bounds`（MC 带）/ `cp95`
  · 面板口径多数：`dose_confound_audit.majority_count`

⚖⚠⚖⚖ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不连远端、⛔ 不写/删任何数据文件。
⚖⚠⚖⚖⚖ 每条判据都必须**能红**：判据全部抽成**可注入的函数**（`j_cN_*`），
   ⇒ 自检才能「喂变异数据看它红」（⛔ 判据内联 ⇒ 自检恒绿、什么都没验到）。

跑法：
    python3 dose_convention_audit.py
    python3 dose_convention_audit.py --selftest
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import collections
import copy
import importlib.util
import itertools
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
VSRC = os.path.join(HERE, "verdict_source_audit.py")
DCONF = os.path.join(HERE, "dose_confound_audit.py")
DLAYER = os.path.join(HERE, "dose_layer_audit.py")
DOSEF = os.path.join(HERE, "dose_fragility_audit.py")
IAUD = os.path.join(HERE, "interval_audit.py")
READER = os.path.join(REPO, ".cache", "mutbak", "r227_kcurve.py")
JSONL_W = os.path.join(HERE, "_an.txt")
JSONL_RAND = os.path.join(HERE, "_ra.txt")

ALPHA = 0.05
# ⚖ **预登记的 α**（⛔ 不是本工具定的；改它会把结论改掉 ⇒ 判据 C0 钉住）
BASE_ALPHA = 0.05
N_LAYER = 4
ARMS = ("w", "rand")
N_MC = 5000
MC_SEED = 20261020

# ⚖⚖⚖ **口径空间（三个维度，各 2 种取值）** —— 取值集合**独立写死**
BOUNDARIES = ("prod", "alt")
QUANTILES = ("inclusive", "exclusive")
ZERO_SPANS = ("keep", "drop")
# ⚖ 基准组合 = 生产口径（`dose_bands_v` 的默认那支）
BASE_COMBO = ("prod", "inclusive", "keep")
# ⚖ 8 个组合**全部枚举**（⛔ 不抽样）⇒ 组合数写死
N_COMBO = 8
# ⚖ 三个维度**必须**是各 2 种（写死 ⇒ 有人改成 3 种就红）
DIM_SIZES = (2, 2, 2)

# ⚖⚖⚖ **独立写死的期望表**（244.63 的一次性探查脚本 `_explore_24463.py` 实测）
#   ⚖ 那份探查**自带分档器**（⛔ 不调 `dose_bands_v`）⇒ 与本工具是**两份独立实现**
#   ⚖ ⇒ 两者一致才有意义；不一致 ⇒ 有一份写错了 ⇒ 判据 C11 红。
#   ⚖⚠ **确定量**（分档表 / 各层 K / T）容差紧；**MC 点估计**（p）容差宽
#     （p = (ge+1)/(n_mc+1) 有蒙特卡洛误差 ⇒ 不该拿它卡到小数点后四位）。
COMBO_EXPECT = {
    ("prod", "inclusive", "keep"): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (27, 28, 30, 24), "K": (2, 4, 5, 6), "T": 5.375,
                 "p": 0.0878, "rho": 0.0237, "scope": (5, 14), "det": "「未检出」"},
    },
    ("prod", "inclusive", "drop"): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (27, 27, 29, 24), "K": (2, 4, 6, 6), "T": 5.875,
                 "p": 0.0718, "rho": 0.0225, "scope": (5, 14), "det": "「未检出」"},
    },
    ("prod", "exclusive", "keep"): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (27, 28, 30, 24), "K": (2, 4, 5, 6), "T": 5.375,
                 "p": 0.0878, "rho": 0.0237, "scope": (5, 14), "det": "「未检出」"},
    },
    ("prod", "exclusive", "drop"): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (27, 27, 29, 24), "K": (2, 4, 6, 6), "T": 5.875,
                 "p": 0.0718, "rho": 0.0225, "scope": (5, 14), "det": "「未检出」"},
    },
    ("alt", "inclusive", "keep"): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (27, 27, 27, 28), "K": (2, 4, 3, 6), "T": 6.625,
                 "p": 0.0418, "rho": 0.0237, "scope": (5, 14), "det": "「检出」"},
    },
    ("alt", "inclusive", "drop"): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (26, 27, 26, 28), "K": (2, 4, 4, 6), "T": 7.375,
                 "p": 0.0304, "rho": 0.0225, "scope": (5, 14), "det": "「检出」"},
    },
    ("alt", "exclusive", "keep"): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (27, 27, 27, 28), "K": (2, 4, 3, 6), "T": 6.625,
                 "p": 0.0418, "rho": 0.0237, "scope": (5, 14), "det": "「检出」"},
    },
    ("alt", "exclusive", "drop"): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625,
              "p": 0.0002, "rho": 0.6911, "scope": (10, 14), "det": "「检出」"},
        "rand": {"bands": (26, 27, 26, 28), "K": (2, 4, 4, 6), "T": 7.375,
                 "p": 0.0304, "rho": 0.0225, "scope": (5, 14), "det": "「检出」"},
    },
}

# ⚖ 容差（**确定量**紧、**MC 点估计**宽）
TOL_T = 5e-3
TOL_P = 5e-3
TOL_RHO = 3e-4

# ⚖⚖⚖ **244.60 的权威值**（⛔ **不是本工具算出来的**；期望集要**独立写死**）
#   244.61 的教训：期望集不许从被检对象派生 ⇒ 这里全是字面量。
BASE_BAND_SIZE = (27, 28, 30, 24)
BASE_LAYER_K = {"w": (4, 6, 10, 14), "rand": (2, 4, 5, 6)}
BASE_TREND_T = {"w": 15.875, "rand": 5.375}
BASE_TREND_P = {"w": 0.0002, "rand": 0.0878}
BASE_SCOPE_K = {"w": (10, 14), "rand": (5, 14)}
# ⚖ 244.60 的结论（w p<α ∧ rand p≥α）在**基准口径**下**成立**
BASE_VERDICT = True
# ⚖ 244.60 的独立事实：层内基准确实塌到 **0.25**（⛔ 不是 0.5）
MIN_LAYER_BASE = 0.25
# ⚖ 244.63 的独立实测：两臂各有 **5 个格正好落在分位点上**
#   ⇒ 「档边界换约定」**不是空转**（⛔ 若这个数是 0 ⇒ 那个维度空转）
BASE_CELLS_ON_CUT = 5
# ⚖⚖⚖ 244.63 的独立实测：「零跨度格不进轴」**破坏跨臂配对**
#   （w 臂 0 个零跨度格、rand 臂 2 个 ⇒ drop 后 rand 少 2 个格 ⇒ 两臂不同格）
#   ⇒ 配对**不成立**的组合数 ≥ 这个下界（⛔ 否则「配对前提」那条判据是空的）
MIN_UNPAIRED = 2
# ⚖⚖⚖ 244.63 的独立实测：**「四分位算法」这一维在本批数据上完全空转**
#   （inclusive 与 exclusive 的分档表**逐位相同**）⇒ 至少有 MIN_IDLE_DIM 个维度
#   **完全空转**（⛔ 否则「维度空转检测」那条判据是空的 ⇒ 恒绿护栏）
MIN_IDLE_DIM = 1

# ⚖⚖⚖⚖⚖ **「第二份真相」的禁令**：下面这两个标签集与 PREAMBLE / BLANKS **刻意重复**。
#   ⛔ **不可**从 PREAMBLE / BLANKS 派生 —— 244.60 的变异台**当场抓到**：
#   派生 ⇒ 删掉一条被检对象时期望集同步变小 ⇒ 判据**永远绿** ⇒ 恒绿护栏。
PREAMBLE_MARKS = ("【P1】", "【P2】", "【P3】", "【P4】", "【P5】")
BLANK_MARKS = ("【B1】", "【B2】", "【B3】", "【B4】", "【B5】", "【B6】")

# ⚖ 检出状态的**两个互不包含的词**（⛔ 用直角引号包住，
#   否则「未检出」里含「检出」⇒ 字符串匹配分不开 ⇒ 判据恒绿）
ST_YES = "「检出」"
ST_NO = "「未检出」"

_MODS = {}


class HardFail(Exception):
    pass


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
    return _load(VSRC, "vs_24463")


def dconf():
    return _load(DCONF, "dc_24463")


def dlayer():
    return _load(DLAYER, "dl_24463")


def dfrag():
    return _load(DOSEF, "dfe_24463")


def iaud():
    return _load(IAUD, "ia_24463")


def reader():
    return _load(READER, "r227_24463")


# ---------------------------------------------------------------- 判定式（唯一实现）
def verdict_of(sc):
    """⚖ 244.60 那条结论在**这个场景**下成立吗？

    ⚖⚖⚖ **唯一实现**：244.62 的 `dose_fragility_audit.verdict_of`
    （⛔ **不在本文件里另写一份公式** ⇒ 244.61 的「同一个概念两个实现」教训）
    ⚖ 判据 C4 另有**独立**的一份判定式（从**印出来的 p** 重算）⇒ 交叉对账。
    """
    return dfrag().verdict_of(sc)


def combo_label(combo):
    return "%s/%s/%s" % combo


def state_of(p):
    """⚖ p < α ⇒ 「检出」；否则 ⇒ 「未检出」。"""
    return ST_YES if p < ALPHA else ST_NO


# ---------------------------------------------------------------- 场景
def build_combo(rows_by_arm, combo):
    """⚖ 算**一个口径组合**下的两臂结果。"""
    DC, DL = dconf(), dlayer()
    boundary, quantile, zero_span = combo
    out = {"combo": combo, "label": combo_label(combo), "arm": {}}
    for arm in ARMS:
        recs = rows_by_arm[arm]
        ks, fr = DC.dose_cells(recs, zero_span=zero_span)
        if not ks:
            raise HardFail("组合 %s / %s：剂量轴没有格 ⇒ **未量到**"
                           % (combo_label(combo), arm))
        qs, bands = DC.dose_bands_v(ks, fr, boundary=boundary, quantile=quantile)
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
                "L": L, "verdicts": v,
                "K": sum(1 for t in v if v[t]["verdict"]),
                "n_traj": len(v),
                "nzs": [v[t]["nz"] for t in sorted(v)],
                "cellpos": sum(1 for c in cells if DL.cell_sign_p9(c)),
                "celln": len(cells),
            })
        p_tr, T, e0, ge, n_mc = DL.mc_trend_p_geom(
            [r["nzs"] for r in rows], [r["K"] for r in rows],
            n_mc=N_MC, seed=MC_SEED)
        lo, hi = iaud().wilson_bounds(ge, n_mc)
        out["arm"][arm] = {
            "ks": ks, "fr": fr, "qs": qs, "bands": bands, "rows": rows,
            "trend": {"p": p_tr, "T": T, "e0": e0, "ge": ge, "n_mc": n_mc,
                      "band": (lo, hi), "border": (lo <= ALPHA <= hi)},
            "scope_k": DC.majority_count(ks),
            "rho": DC.spearman(fr, [DC.d_of(r) for r in ks]),
            "state": state_of(p_tr),
        }
    # ---- 跨臂：逐层配对置换 + 精确符号检验（244.60 的 C5 教训）----
    RD = reader()
    for L in range(N_LAYER):
        vw = out["arm"]["w"]["rows"][L]["verdicts"]
        vr = out["arm"]["rand"]["rows"][L]["verdicts"]
        diffs = [(1 if vw[t]["verdict"] else 0) - (1 if vr[t]["verdict"] else 0)
                 for t in sorted(vw)]
        pperm, obs = DL.paired_perm_p(diffs)
        nz = [d for d in diffs if d != 0]
        p_exact = RD.sign_test([float(d) for d in nz])[0] if nz else None
        out.setdefault("layers", []).append(
            {"L": L, "diffs": diffs, "pperm": pperm, "obs": obs,
             "p_exact": p_exact,
             "kw": out["arm"]["w"]["rows"][L]["K"],
             "kr": out["arm"]["rand"]["rows"][L]["K"]})
    # ---- 跨臂配对前提：两臂必须**逐层同格同数**（否则配对置换无意义）----
    # ⚖⚠⚖⚖ **244.63 实测发现**：「零跨度格不进轴」这个口径**会破坏配对** ——
    #   w 臂零跨度格 **0 个**、rand 臂 **2 个** ⇒ drop 之后 rand 少了 2 个格
    #   ⇒ 两臂**不再同格** ⇒ 跨臂配对置换的前提**不成立** ⇒ 该组合的跨臂比较**未量到**。
    paired_ok = True
    for L in range(N_LAYER):
        rw = out["arm"]["w"]["rows"][L]
        rr = out["arm"]["rand"]["rows"][L]
        if (rw["celln"] != rr["celln"] or rw["n_traj"] != rr["n_traj"]):
            paired_ok = False
    out["paired_ok"] = paired_ok
    # ---- 层内基准（每层每臂）：⛔ 不是 0.5 ----
    for arm in ARMS:
        for row in out["arm"][arm]["rows"]:
            bases = [DL.majority_base_p(nz) for nz in row["nzs"]]
            row["bases"] = bases
            row["avg_base"] = (sum(bases) / len(bases)) if bases else None
    out["verdict"] = verdict_of(out)
    out["flip"] = not out["verdict"]
    return out


def build_all():
    """⚖ 算**全部 8 个组合**（⛔ 全部枚举，不抽样）＋ 基准。"""
    VS = vsrc()
    rows_by_arm = {"w": VS.load_rows(JSONL_W), "rand": VS.load_rows(JSONL_RAND)}
    for arm in ARMS:
        if not rows_by_arm[arm]:
            raise HardFail("%s 臂读数一条都没有 ⇒ **未量到**" % arm)
    combos = list(itertools.product(BOUNDARIES, QUANTILES, ZERO_SPANS))
    scen = [build_combo(rows_by_arm, c) for c in combos]
    base = [s for s in scen if s["combo"] == BASE_COMBO][0]
    # ---- 空转检测：**逐臂**（⚠ 只看一条臂会把「另一臂变了」判成空转）----
    for s in scen:
        for arm in ARMS:
            s.setdefault("idle", {})[arm] = (
                tuple(len(sub) for _l, sub in s["arm"][arm]["bands"])
                == tuple(len(sub) for _l, sub in base["arm"][arm]["bands"]))
        s["idle_all"] = all(s["idle"][a] for a in ARMS)
    # ---- 切点上的格数（决定「边界换约定」是不是空转）----
    cut = {}
    zero_span_cells = {}
    for arm in ARMS:
        DC = dconf()
        ks, fr = DC.dose_cells(rows_by_arm[arm])
        import statistics as _st
        qs = _st.quantiles(fr, n=4)
        cut[arm] = sum(1 for f in fr if f in (qs[0], qs[1], qs[2]))
        # ⚖⚖⚖ **零跨度格数**（`d == 0`）—— 解释「drop 维度」在两臂上表现不同的原因
        zero_span_cells[arm] = sum(1 for r in ks if DC.d_of(r) == 0.0)
    # ---- ⚖⚖⚖ 三个口径维度里，哪些在**本批数据上**是**空转**的 ----
    #   （翻这一维 ⇒ 分档表会不会变？⇒ 这一维的口径不确定性**测不测得到**）
    by = {s["combo"]: s for s in scen}
    dim_idle = []
    for idx, name, a, b in ((0, "档边界", "prod", "alt"),
                            (1, "四分位算法", "inclusive", "exclusive"),
                            (2, "零跨度格", "keep", "drop")):
        combo = list(BASE_COMBO)
        combo[idx] = b
        s = by.get(tuple(combo))
        if s is None:
            dim_idle.append({"name": name, "flip": "%s→%s" % (a, b),
                             "w": None, "rand": None})
            continue
        bw = tuple(len(x) for _l, x in s["arm"]["w"]["bands"])
        br = tuple(len(x) for _l, x in base["arm"]["w"]["bands"])
        rw = tuple(len(x) for _l, x in s["arm"]["rand"]["bands"])
        rr = tuple(len(x) for _l, x in base["arm"]["rand"]["bands"])
        dim_idle.append({"name": name, "flip": "%s→%s" % (a, b),
                         "w": (bw != br), "rand": (rw != rr)})
    return {"scenarios": scen, "base": base, "combos": combos,
            "n_combo": len(scen), "n_traj": len(rows_by_arm["w"]),
            "cut": cut, "dim_idle": dim_idle, "zero_span_cells": zero_span_cells}


# ---------------------------------------------------------------- 报告
PREAMBLE = (
    "【P1】⚖⚠⚖⚖ **口径空间全部枚举**：剂量轴有三个口径维度（档边界约定 / 四分位算法 / "
    "零跨度格进不进轴），每个 2 种取值 ⇒ **2×2×2 = 8 个组合** ⇒ 本工具**全部跑过**（⛔ 不抽样）",
    "【P2】⚖⚠⚖⚖ **三个维度都住在 `dose_confound_audit.dose_bands_v` / `dose_cells` 里**"
    "（⛔ 别处没有第二份分档器）⇒ 生产口径 = `(\"prod\", \"inclusive\", \"keep\")` "
    "⇒ 变体与生产口径**不可能**悄悄分叉",
    "【P3】⚖⚠⚖⚖ **判决口径 = 244.60 那条结论**：(w 趋势 MC p < α) ∧ (rand 趋势 MC p ≥ α)，"
    "α = 0.05（**预登记**）⇒ 只动**口径**，⛔ 不动读数",
    "【P4】⚖⚠⚖⚖ **层内零假设基准不是 0.5**（「平票算 False」＋每条轨迹每层只有 1–3 格）"
    "⇒ 各层基准不同 ⇒ 层间比较必须用各自的基准",
    "【P5】⚖⚠⚖⚖ **MC p 只是点估计**（`p = (ge+1)/(n_mc+1)`）⇒ 每个组合每臂都印 **MC95% 带**"
    "⇒ p 贴着 α 时，「显著/不显著」**本来就未定**",
)

BLANKS = (
    ("【B1】**分位点算法的其他实现**",
     "本轮只测了 `statistics.quantiles` 的 inclusive / exclusive 两支 ⇒ "
     "**nearest-rank / numpy.percentile / 手算插值**等**未量到**"),
    ("【B2】**档数不是 4**", "三档 / 五档 / 连续剂量回归**未量到**"),
    ("【B3】**格集合的其他过滤**",
     "按**位点数**（而非比例）分档、或换掉「scope=k ∧ 有读数 ∧ 有位点数」这三条条件 ⇒ **未量到**"),
    ("【B4】**臂外口径**", "面板口径（scope=all / single）**不参与**分档 ⇒ 那条轴的口径**未量到**"),
    ("【B5】**哪一条臂是机制效应**",
     "本轮只拆**口径**、⛔ 不指定机制 ⇒ 机制归属**仍未量到**"),
    ("【B6】**零跨度格（d==0）的语义**",
     "它是「**没变化**」还是「**没量到**」⇒ **未量到** ⇒ 本轮只把它当**口径维度**处理"),
)


def build_report(allr):
    RP = ["【剂量轴口径审计】（244.63；零 GPU）",
          "  ⚖ 口径空间：档边界 %s × 四分位算法 %s × 零跨度格 %s ⇒ **%d 个组合，全部枚举**"
          % ("/".join(BOUNDARIES), "/".join(QUANTILES), "/".join(ZERO_SPANS),
             allr["n_combo"]),
          "  ⚖ 基准组合 = %s（= 生产口径）" % combo_label(BASE_COMBO),
          "  ⚖ 判决口径：244.60 的「剂量—响应只出现在 w 臂」"
          " = (w 趋势 MC p < %.2f) ∧ (rand 趋势 MC p ≥ %.2f)" % (ALPHA, ALPHA),
          "  ⚖ 切点上的格数：w %d ｜ rand %d（⇒ 「档边界换约定」**不是空转**的前提）"
          % (allr["cut"]["w"], allr["cut"]["rand"]),
          "  ⚖ 零跨度格（`d == 0`）数：w %d ｜ rand %d"
          "（⇒ 「零跨度格不进轴」这一维在 **w 臂上不动**、在 **rand 臂上动**）"
          % (allr["zero_span_cells"]["w"], allr["zero_span_cells"]["rand"])]
    RP.append("")
    RP.append("【0】⚖⚠⚖⚖ **前提声明**（⛔ 删掉任何一条都必须红）")
    for s in PREAMBLE:
        RP.append("  " + s)
    RP.append("")

    for s in allr["scenarios"]:
        is_base = (s["combo"] == BASE_COMBO)
        RP.append("· 组合 %s%s" % (s["label"], "（**基准**）" if is_base else ""))
        for arm in ARMS:
            a = s["arm"][arm]
            bs = "/".join(str(len(sub)) for _l, sub in a["bands"])
            ks_ = [a["rows"][L]["K"] for L in range(N_LAYER)]
            rates = ["%.3f" % (a["rows"][L]["cellpos"] / float(a["rows"][L]["celln"]))
                     for L in range(N_LAYER)]
            tr = a["trend"]
            RP.append("    · %-4s 档 %s ｜ rho %+.4f ｜ 各层 K=%s ｜ 格级正号率 %s"
                      " ｜ 趋势 T=%.3f p=%.4f MC95%%带 [%.4f, %.4f]%s"
                      " ｜ 剂量轴口径多数 %d/%d ｜ 检出状态=%s"
                      % (arm, bs, a["rho"], "/".join(str(x) for x in ks_),
                         "/".join(rates), tr["T"], tr["p"],
                         tr["band"][0], tr["band"][1],
                         "  ⚠⚠ **带跨过 α**" if tr["border"] else "",
                         a["scope_k"][0], a["scope_k"][1], a["state"]))
        RP.append("    · 空转：%s ｜ w=%s rand=%s ｜ 完全空转=%s"
                  % (s["label"],
                     "是" if s["idle"]["w"] else "否",
                     "是" if s["idle"]["rand"] else "否",
                     "是" if s["idle_all"] else "否"))
        RP.append("    · 跨臂配对：%s ｜ %s"
                  % (s["label"],
                     "成立（两臂逐层同格同数）" if s["paired_ok"] else
                     "**不成立**（两臂格数不同 ⇒ 该组合的**跨臂比较未量到**）"))
        pw = s["arm"]["w"]["trend"]["p"]
        pr = s["arm"]["rand"]["trend"]["p"]
        RP.append("    ⇒ 判决【%s】：**%s**（w 趋势 p=%.4f < %.2f ∧ rand 趋势 p=%.4f ≥ %.2f）"
                  " ｜ w %s ｜ rand %s%s"
                  % (s["label"], "成立" if s["verdict"] else "不成立",
                     pw, ALPHA, pr, ALPHA,
                     s["arm"]["w"]["state"], s["arm"]["rand"]["state"],
                     "  ⚠⚠ **翻转**" if s["flip"] else ""))

    # ---- 小结（**全部由实测算出来**）----
    n_ok = sum(1 for s in allr["scenarios"] if s["verdict"])
    flips = [s["label"] for s in allr["scenarios"] if s["flip"]]
    w_pass = sum(1 for s in allr["scenarios"] if s["arm"]["w"]["trend"]["p"] < ALPHA)
    w_ps = sorted({round(s["arm"]["w"]["trend"]["p"], 4) for s in allr["scenarios"]})
    r_states = sorted({s["arm"]["rand"]["state"] for s in allr["scenarios"]})
    base_rand_state = allr["base"]["arm"]["rand"]["state"]
    RP.append("")
    RP.append("【2】⚖⚠⚖⚖ **口径敏感性小结**（数全部由实测算出来）")
    RP.append("  ⚖ 判决（剂量—响应只出现在 w 臂）成立的组合 %d/%d"
              % (n_ok, allr["n_combo"]))
    RP.append("  ⚖ 翻转的组合 %d 个%s"
              % (len(flips), ("（%s）" % "、".join(flips)) if flips else ""))
    RP.append("  ⚖ w 臂趋势 p<α 的组合 %d/%d（p 取值集合 %s）"
              % (w_pass, allr["n_combo"], w_ps))
    RP.append("  ⚖ rand 臂「检出状态」集合 = {%s}（%d 种）"
              % ("、".join(r_states), len(r_states)))
    RP.append("  ⚖ 基准组合 %s 的 rand 臂：%s（p=%.4f）"
              % (combo_label(BASE_COMBO), base_rand_state,
                 allr["base"]["arm"]["rand"]["trend"]["p"]))
    # ⚖⚖⚖ **结论字段**（结构化 ⇒ 判据可以**双向**对账，不靠子串猜）
    concl = "未量到" if len(r_states) > 1 else r_states[0]
    RP.append("  ⚖ rand 臂的剂量—响应结论（α 上）= **%s**" % concl)
    if len(r_states) > 1:
        RP.append("  ⇒ ⚠⚠⚠ rand 臂的检出状态**随口径翻转** ⇒ rand 臂的剂量—响应在 α 上**未量到**"
                  "（⛔ 不许说成「rand 臂没有剂量趋势」，也不许说成「rand 臂未检出」）")
    else:
        RP.append("  ⇒ rand 臂的检出状态在全部口径组合下**一致**（%s）" % r_states[0])
    idle_all = [s["label"] for s in allr["scenarios"]
                if s["idle_all"] and s["combo"] != BASE_COMBO]
    RP.append("  ⚖ 完全空转的组合（分档表与基准逐位相同，除基准外）%d 个%s"
              % (len(idle_all), ("（%s）" % "、".join(idle_all)) if idle_all else ""))
    # ---- ⚖⚖⚖ 三个口径维度里，哪些在**本批数据上**空转（⇒ 那一维**测不测得到**）----
    _parts = []
    for _d in allr["dim_idle"]:
        if _d["w"] is None:
            _parts.append("%s(%s) **该组合不在枚举里**" % (_d["name"], _d["flip"]))
        else:
            _parts.append("%s(%s) w=%s rand=%s"
                          % (_d["name"], _d["flip"],
                             "变" if _d["w"] else "**不变**",
                             "变" if _d["rand"] else "**不变**"))
    RP.append("  ⚖ 口径维度空转检测：%s" % " ｜ ".join(_parts))
    _full_idle = [d["name"] for d in allr["dim_idle"]
                  if d["w"] is not None and not d["w"] and not d["rand"]]
    RP.append("  ⚖ **完全空转**的维度（翻它两臂分档表都不变 ⇒ 那一维的口径不确定性**测不到**）"
              "：%s" % ("、".join(_full_idle) if _full_idle else "无"))

    RP.append("")
    RP.append("【3】⚖⚠⚖⚖ **边界清单**（哪些前提**仍未量到**）")
    for head, body in BLANKS:
        RP.append("  %s %s：%s" % (head, "", body))
    return RP


# ---------------------------------------------------------------- 判据（可注入）
def j_c0_baseline(base):
    """C0：基准组合必须**逐位复现 244.60**（⛔ 不许悄悄换口径）。"""
    ok, d = True, []
    for arm in ARMS:
        a = base["arm"][arm]
        bs = tuple(len(sub) for _l, sub in a["bands"])
        good = (bs == BASE_BAND_SIZE)
        ok &= good
        d.append("%s 档数 %s（期望 %s）%s" % (arm, list(bs), list(BASE_BAND_SIZE),
                                             "✅" if good else "❌"))
        ks = tuple(a["rows"][L]["K"] for L in range(N_LAYER))
        good = (ks == BASE_LAYER_K[arm])
        ok &= good
        d.append("%s 各层 K %s（期望 %s）%s" % (arm, list(ks), list(BASE_LAYER_K[arm]),
                                               "✅" if good else "❌"))
        T = a["trend"]["T"]
        good = abs(T - BASE_TREND_T[arm]) < TOL_T
        ok &= good
        d.append("%s 趋势 T=%.3f（期望 %.3f）%s" % (arm, T, BASE_TREND_T[arm],
                                                   "✅" if good else "❌"))
        p = a["trend"]["p"]
        good = abs(p - BASE_TREND_P[arm]) < TOL_P
        ok &= good
        d.append("%s 趋势 p=%.4f（期望 %.4f）%s" % (arm, p, BASE_TREND_P[arm],
                                                   "✅" if good else "❌"))
        sk = tuple(a["scope_k"])
        good = (sk == BASE_SCOPE_K[arm])
        ok &= good
        d.append("%s 剂量轴口径多数 %d/%d（期望 %d/%d）%s"
                 % (arm, sk[0], sk[1], BASE_SCOPE_K[arm][0], BASE_SCOPE_K[arm][1],
                    "✅" if good else "❌"))
    good = (base["verdict"] == BASE_VERDICT)
    ok &= good
    d.append("基准组合的判决 %s（期望 %s）%s"
             % ("成立" if base["verdict"] else "**不成立**",
                "成立" if BASE_VERDICT else "不成立", "✅" if good else "❌"))
    good = (ALPHA == BASE_ALPHA)
    ok &= good
    d.append("判决的 α = %.4f（预登记 %s，⛔ 不许改）%s"
             % (ALPHA, BASE_ALPHA, "✅" if good else "❌"))
    return ok, d


def j_c1_space(allr):
    """C1：口径空间必须**恰好 8 个组合**、标签唯一、三维度取值集合写死。"""
    ok = (allr["n_combo"] == N_COMBO)
    d = ["枚举出的组合数 %d（期望 %d = %d 个维度各 2 种）%s"
         % (allr["n_combo"], N_COMBO, len(DIM_SIZES),
            "✅" if ok else "❌")]
    labels = [s["label"] for s in allr["scenarios"]]
    good = (len(set(labels)) == len(labels))
    ok &= good
    d.append("组合标签 %d 个、去重后 %d 个（必须逐个不同）%s"
             % (len(labels), len(set(labels)), "✅" if good else "❌"))
    good = (tuple(sorted(BOUNDARIES)) == ("alt", "prod")
            and tuple(sorted(QUANTILES)) == ("exclusive", "inclusive")
            and tuple(sorted(ZERO_SPANS)) == ("drop", "keep"))
    ok &= good
    d.append("三个维度的取值集合 %s / %s / %s %s"
             % (list(BOUNDARIES), list(QUANTILES), list(ZERO_SPANS),
                "✅" if good else "❌"))
    good = (len(DIM_SIZES) == 3 and all(x == 2 for x in DIM_SIZES))
    ok &= good
    d.append("维度数 %d、每维取值数 %s %s"
             % (len(DIM_SIZES), list(DIM_SIZES), "✅" if good else "❌"))
    good = any(s["combo"] == BASE_COMBO for s in allr["scenarios"])
    ok &= good
    d.append("基准组合 %s 在枚举结果里：%s" % (combo_label(BASE_COMBO),
                                              "✅" if good else "❌"))
    return ok, d


def j_c2_not_idle(allr, RP):
    """C2：口径变体**不是空转**（⛔ 否则「口径敏感性」是空的 ⇒ 恒绿护栏），
    且**空转的组合必须被逐个标出**（⚠ 只看一条臂 ⇒ 会把「另一臂变了」判成空转）。"""
    ok, d = True, []
    moved = [s["label"] for s in allr["scenarios"]
             if not (s["idle"]["w"] and s["idle"]["rand"])]
    good = len(moved) >= 1
    ok &= good
    d.append("分档表真的动过的组合 %d 个（%s）%s"
             % (len(moved), "、".join(moved) if moved else "无",
                "✅" if good else "❌（⇒ 口径敏感性是空的 ⇒ 这条会是恒绿护栏）"))
    # ---- 切点上的格数：>0 ⇒ 「边界换约定」不是空转 ----
    for arm in ARMS:
        good = allr["cut"][arm] == BASE_CELLS_ON_CUT
        ok &= good
        d.append("%s 臂落在分位点上的格 %d（期望 %d ⇒ 「档边界换约定」不是空转）%s"
                 % (arm, allr["cut"][arm], BASE_CELLS_ON_CUT,
                    "✅" if good else "❌"))
    # ---- 逐组合的空转标记必须被印出且与实算一致 ----
    lines = [ln for ln in RP if "空转：" in ln]
    good = (len(lines) == allr["n_combo"])
    ok &= good
    d.append("印出「空转：」的行 %d（期望 %d）%s"
             % (len(lines), allr["n_combo"], "✅" if good else "❌"))
    for s in allr["scenarios"]:
        hit = [ln for ln in lines if s["label"] in ln]
        if not hit:
            ok = False
            d.append("❌ 组合 %s 没有印出空转标记" % s["label"])
            continue
        ln = hit[0]
        mw = re.search(r"w=(是|否)", ln)
        mr = re.search(r"rand=(是|否)", ln)
        ma = re.search(r"完全空转=(是|否)", ln)
        if not (mw and mr and ma):
            ok = False
            d.append("❌ 组合 %s 的空转行认不出标记：%s" % (s["label"], ln.strip()[:70]))
            continue
        want = (("是" if s["idle"]["w"] else "否"),
                ("是" if s["idle"]["rand"] else "否"),
                ("是" if s["idle_all"] else "否"))
        got = (mw.group(1), mr.group(1), ma.group(1))
        good = (want == got)
        ok &= good
        d.append("组合 %s 的空转标记 w/rand/全 %s（期望 %s）%s"
                 % (s["label"], got, want, "✅" if good else "❌"))
    # ---- 三个口径维度的空转检测必须被印出且与实算一致 ----
    dl = [ln for ln in RP if "口径维度空转检测" in ln]
    good = (len(dl) == 1)
    ok &= good
    d.append("印出「口径维度空转检测」的行 %d（期望 1）%s"
             % (len(dl), "✅" if good else "❌"))
    full_expect = []
    if dl:
        parts = [p.strip() for p in dl[0].split("：", 1)[1].split("｜")]
        got_dim = {}
        for p in parts:
            m = re.match(r"^(.+?)\((.+?)\) w=(\*\*不变\*\*|变) rand=(\*\*不变\*\*|变)$", p)
            if not m:
                ok = False
                d.append("❌ 维度行认不出：%s" % p[:60])
                continue
            got_dim[m.group(1)] = (m.group(3) == "变", m.group(4) == "变")
        for dd in allr["dim_idle"]:
            if dd["w"] is None:
                continue
            good = (got_dim.get(dd["name"]) == (dd["w"], dd["rand"]))
            ok &= good
            d.append("维度 %s 的空转标记 w/rand %s（期望 %s）%s"
                     % (dd["name"], got_dim.get(dd["name"]),
                        (dd["w"], dd["rand"]), "✅" if good else "❌"))
            if not dd["w"] and not dd["rand"]:
                full_expect.append(dd["name"])
    # ---- 「完全空转的维度」那一行也必须与实算一致 ----
    fl = [ln for ln in RP if "完全空转**的维度" in ln]
    good = (len(fl) == 1)
    ok &= good
    d.append("印出「完全空转**的维度」的行 %d（期望 1）%s"
             % (len(fl), "✅" if good else "❌"))
    if fl:
        got_full = fl[0].split("：", 1)[1].strip()
        want_full = "、".join(full_expect) if full_expect else "无"
        good = (got_full == want_full)
        ok &= good
        d.append("完全空转的维度印出「%s」（期望「%s」）%s"
                 % (got_full, want_full, "✅" if good else "❌"))
    # ---- 至少一个维度必须**完全空转**（⛔ 否则这条判据是空的 ⇒ 恒绿护栏）----
    good = (len(full_expect) >= MIN_IDLE_DIM)
    ok &= good
    d.append("**完全空转**的维度 %d 个（%s）｜ 期望 ≥ %d %s"
             % (len(full_expect), "、".join(full_expect) if full_expect else "无",
                MIN_IDLE_DIM,
                "✅" if good else "❌（⇒ 这条判据是空的 ⇒ 恒绿护栏）"))
    return ok, d


def j_c3_layer_base(allr):
    """C3：层内零假设基准必须**逐条**与 `majority_base_p` 一致，**且**确实塌到 < 0.5。"""
    DL = dlayer()
    ok, d = True, []
    worst = None
    for s in allr["scenarios"]:
        for arm in ARMS:
            for row in s["arm"][arm]["rows"]:
                want = [DL.majority_base_p(nz) for nz in row["nzs"]]
                good = (row["bases"] == want)
                ok &= good
                if not good:
                    d.append("❌ 组合 %s / %s / 层 %d：基准序列与现算不一致"
                             % (s["label"], arm, row["L"]))
                if row["avg_base"] is not None:
                    worst = (row["avg_base"] if worst is None
                             else min(worst, row["avg_base"]))
    good = (worst is not None) and (worst <= MIN_LAYER_BASE + 1e-12)
    ok &= good
    d.append("全部组合里最小的层内平均基准 %.4f（期望 ≤ %.2f，⛔ 不是 0.5）%s"
             % (worst if worst is not None else float("nan"), MIN_LAYER_BASE,
                "✅" if good else "❌"))
    return ok, d


def j_c4_verdicts_printed(allr, RP):
    """C4：判决必须**逐组合印出**，且每条判决与该组合**印出来的 p** 交叉对账。

    ⚖⚠⚠⚠ **双向**：既抓「少印一条」，也抓「判定被写死 / p 被篡改但判决没改」。
    ⚖⚠⚠⚠ **判决行自带 p** ⇒ 交叉对账是**自足**的
    ⚖ ⇒ ⛔ 不许从被检对象内部去取 p（那样两边同源 ⇒ 恒绿）。
    """
    n_sc = allr["n_combo"]
    vlines = [ln for ln in RP if "⇒ 判决" in ln]
    printed = len(vlines)
    ok = (printed == n_sc)
    d = ["印出判决的组合行 %d（期望 %d）%s" % (printed, n_sc, "✅" if ok else "❌")]
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


def j_c5_flip_count(allr, RP):
    """C5：翻转数必须被**报出**，且与逐组合判决**交叉对账**（算出来的 == 数出来的）。"""
    flips = [s["label"] for s in allr["scenarios"] if s["flip"]]
    marked = sum(1 for ln in RP if "⚠⚠ **翻转**" in ln)
    ok = (marked == len(flips))
    d = ["算出的翻转数 %d（场景：%s）｜ 报告里标出的 %d 行 %s"
         % (len(flips), ("、".join(flips) if flips else "无"), marked,
            "✅" if ok else "❌")]
    return ok, d


def j_c6_mc_calibration():
    """C6：MC 趋势 p 的零分布**双向校准**（244.60 的 C4z 教训）。

    ⚖⚠⚠⚠ **单边判据对「零分布塌掉/反号」是瞎的** ⇒ 必须正反两测。
    ⚖⚠⚠⚠⚖ **口径澄清（244.62 自己踩的坑，别记反）**：
    这个 MC 检验是**单边**的（`p = P(T_sim ≥ T_obs)`）⇒
      · 「零分布**塌掉**」（T_sim ≡ 0）⇒ 零假设夹具上 p = **1.0** ⇒ 红
      · 「零分布**反号**」（T_sim ≡ 负）⇒ 零假设夹具上 p ≈ **0** ⇒ 红
      ⇒ **一条「零假设夹具 p ≈ 0.5」就同时抓住这两种坏掉**
    ⚠ 而「**观测**本身反号」（T_obs < 0）⇒ p ≈ **1** ⇒ 那是**单边检验的正确语义**
      ⇒ ⛔ **不许**把它当成「坏掉」。
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


def j_c7_denominators(allr, RP):
    """C7：跨臂**配对前提** —— 两臂必须**逐层同格同数**；不成立的组合**必须被标出**。

    ⚖⚠⚖⚖ **244.63 的实测发现**：「零跨度格不进轴」这个口径**会破坏配对** ——
    w 臂零跨度格 **0 个**、rand 臂 **2 个** ⇒ drop 之后 rand 少 2 个格
    ⇒ 那几个组合**两臂不再同格** ⇒ 跨臂配对置换的前提**不成立**
    ⇒ 该组合的跨臂比较**未量到** ⇒ 报告**必须**标出来（不许静默算一个没意义的数）。

    ⚖⚠⚖ **判据形状**：既查「配对成立的组合，分母必须逐条相同」，
       也查「不配对的组合必须被标成『未量到』」⇒ **双向**都能红。
    """
    ok, d = True, []
    unpaired = [s["label"] for s in allr["scenarios"] if not s["paired_ok"]]
    # ---- 独立重算配对（⛔ **不许只信**被检对象存下来的 `paired_ok`）----
    for s in allr["scenarios"]:
        recomputed = True
        for L in range(N_LAYER):
            rw = s["arm"]["w"]["rows"][L]
            rr = s["arm"]["rand"]["rows"][L]
            if (rw["celln"] != rr["celln"] or rw["n_traj"] != rr["n_traj"]
                    or rw["n_traj"] != len(rw["nzs"])):
                recomputed = False
        good = (recomputed == s["paired_ok"])
        ok &= good
        d.append("组合 %s 的配对标记（存「%s」）vs 独立重算「%s」%s"
                 % (s["label"], "成立" if s["paired_ok"] else "不成立",
                    "成立" if recomputed else "不成立", "✅" if good else "❌"))
    lines = [ln for ln in RP if "跨臂配对：" in ln]
    good = (len(lines) == allr["n_combo"])
    ok &= good
    d.append("印出「跨臂配对：」的行 %d（期望 %d）%s"
             % (len(lines), allr["n_combo"], "✅" if good else "❌"))
    for s in allr["scenarios"]:
        hit = [ln for ln in lines if s["label"] in ln]
        if not hit:
            ok = False
            d.append("❌ 组合 %s 没有印出配对标记" % s["label"])
            continue
        ln = hit[0]
        if s["paired_ok"]:
            good = ("不成立" not in ln) and ("未量到" not in ln)
            ok &= good
            d.append("组合 %s 配对成立 ⇒ 标记须为「成立」且**不许**出现「未量到」%s"
                     % (s["label"], "✅" if good else "❌"))
        else:
            good = ("**不成立**" in ln) and ("未量到" in ln)
            ok &= good
            d.append("组合 %s 配对**不成立** ⇒ 标记须含「不成立」与「未量到」%s"
                     % (s["label"], "✅" if good else "❌"))
    # ---- 不配对的组合必须**至少**有 MIN_UNPAIRED 个（⛔ 否则这条判据是空的）----
    good = (len(unpaired) >= MIN_UNPAIRED)
    ok &= good
    d.append("配对不成立的组合 %d 个（%s）｜ 期望 ≥ %d %s"
             % (len(unpaired), "、".join(unpaired) if unpaired else "无",
                MIN_UNPAIRED,
                "✅" if good else "❌（⇒ 这条判据是空的 ⇒ 恒绿护栏）"))
    return ok, d


def j_c8_scope_k_printed(allr, RP):
    """C8：剂量轴口径的多数必须**每个组合每臂都印出**（⛔ 只印基准 ⇒ 读者无法复核）。"""
    n_sc = allr["n_combo"]
    printed = sum(1 for ln in RP if "剂量轴口径多数" in ln)
    ok = (printed == n_sc * 2)
    d = ["印出「剂量轴口径多数」的行 %d（期望 %d = %d 组合 × 2 臂）%s"
         % (printed, n_sc * 2, n_sc, "✅" if ok else "❌")]
    return ok, d


def j_c9_pperm_matches_exact(allr):
    """C9：逐层**配对置换 p** 必须与**精确符号检验**一致（⛔ 置换台自己错了也要红）。"""
    ok, d = True, []
    for s in allr["scenarios"]:
        for row in s.get("layers", []):
            if row["p_exact"] is None:
                continue
            good = abs(row["pperm"] - row["p_exact"]) <= 0.005
            ok &= good
            if not good:
                d.append("❌ 组合 %s / 层 %d：配对置换 %.4f vs 精确 %.6f"
                         % (s["label"], row["L"], row["pperm"], row["p_exact"]))
    d.append("每个组合每层的配对置换 p 与精确符号检验一致（⛔ 置换台自己错了也要红）%s"
             % ("✅" if ok else "❌"))
    return ok, d


def j_c10_mc_band_printed(allr, RP):
    """C10：每个组合每臂的 **MC 不确定带**必须印出（⛔ 只印点估计 ⇒ 边界看不出来）。

    ⚖⚠⚠⚠ **这是本轮最要紧的一条**：rand 臂的 p 落在 α 附近
    ⇒ 只印 p 会让人以为「rand 臂检出/未检出」是确定的，
       而它的带**可能跨过** α ⇒ 那个组合的显著性**本来就未定**。
    """
    n_sc = allr["n_combo"]
    lines = [ln for ln in RP if "MC95%带" in ln]
    printed = len(lines)
    ok = (printed == n_sc * 2)
    d = ["印出「MC95%%带」的行 %d（期望 %d = %d 组合 × 2 臂）%s"
         % (printed, n_sc * 2, n_sc, "✅" if ok else "❌")]
    n_border = 0
    for s in allr["scenarios"]:
        for arm in ARMS:
            lo, hi = s["arm"][arm]["trend"]["band"]
            if not (hi > lo):
                ok = False
                d.append("❌ 组合 %s / %s：带宽度为 0 ⇒ **未量到**" % (s["label"], arm))
            if s["arm"][arm]["trend"]["border"]:
                n_border += 1
    d.append("带跨过 α（%.2f）的组合×臂数 %d%s"
             % (ALPHA, n_border, "（⇒ 那些组合的显著性**未定**）" if n_border else ""))
    ok = ok and (printed == n_sc * 2)
    return ok, d


def j_c11_combos_match_expect(allr):
    """C11：8 个组合的**分档表 / 各层 K / T / p / rho / 口径多数**必须**逐位复现**期望表。

    ⚖⚖⚖ **这是唯一的「绝对值」检查**：非基准组合的数没有别的来源
    ⇒ 期望集**独立写死**（抄 244.63 那份**独立探查**的实测表）⇒ 实现写错 ⇒ 红。
    """
    ok, d = True, []
    for s in allr["scenarios"]:
        exp = COMBO_EXPECT.get(s["combo"])
        if exp is None:
            ok = False
            d.append("❌ 组合 %s 不在期望表里（标签被改过？）" % s["label"])
            continue
        for arm in ARMS:
            e = exp[arm]
            a = s["arm"][arm]
            got_bands = tuple(len(sub) for _l, sub in a["bands"])
            good = (got_bands == e["bands"])
            ok &= good
            d.append("组合 %s / %s 档表 %s（期望 %s）%s"
                     % (s["label"], arm, list(got_bands), list(e["bands"]),
                        "✅" if good else "❌"))
            got_K = tuple(a["rows"][L]["K"] for L in range(N_LAYER))
            good = (got_K == e["K"])
            ok &= good
            d.append("组合 %s / %s 各层 K %s（期望 %s）%s"
                     % (s["label"], arm, list(got_K), list(e["K"]),
                        "✅" if good else "❌"))
            good = abs(a["trend"]["T"] - e["T"]) < TOL_T
            ok &= good
            d.append("组合 %s / %s 趋势 T=%.3f（期望 %.3f）%s"
                     % (s["label"], arm, a["trend"]["T"], e["T"],
                        "✅" if good else "❌"))
            good = abs(a["trend"]["p"] - e["p"]) < TOL_P
            ok &= good
            d.append("组合 %s / %s 趋势 p=%.4f（期望 %.4f）%s"
                     % (s["label"], arm, a["trend"]["p"], e["p"],
                        "✅" if good else "❌"))
            good = abs(a["rho"] - e["rho"]) < TOL_RHO
            ok &= good
            d.append("组合 %s / %s rho %+.4f（期望 %+.4f）%s"
                     % (s["label"], arm, a["rho"], e["rho"], "✅" if good else "❌"))
            good = (tuple(a["scope_k"]) == e["scope"])
            ok &= good
            d.append("组合 %s / %s 剂量轴口径多数 %d/%d（期望 %d/%d）%s"
                     % (s["label"], arm, a["scope_k"][0], a["scope_k"][1],
                        e["scope"][0], e["scope"][1], "✅" if good else "❌"))
            # ⚖⚖⚖ **检出状态词也要写死**：否则改坏 `state_of` 报告**仍然自洽**
            #   ⇒ 判据**恒绿**（244.63 的变异台 M14 抓到的就是这个洞）
            good = (a["state"] == e["det"])
            ok &= good
            d.append("组合 %s / %s 检出状态 %s（期望 %s）%s"
                     % (s["label"], arm, a["state"], e["det"],
                        "✅" if good else "❌"))
    d.append("8 个组合的**分档表 / K / T / p / rho / 口径多数**逐位复现独立写死的期望表%s"
             % ("✅" if ok else "❌"))
    return ok, d


def j_c12_w_arm_all_combos(allr, RP):
    """C12：「w 臂跨**全部**口径组合 p<α」这个小结必须印出，且**与实算一致**。

    ⚖⚠⚠ **双向**：印出的组合数必须等于实算的组合数（⛔ 写死一个数 ⇒ 恒绿护栏）。
    """
    w_pass = sum(1 for s in allr["scenarios"]
                 if s["arm"]["w"]["trend"]["p"] < ALPHA)
    lines = [ln for ln in RP if "w 臂趋势 p<α 的组合" in ln]
    ok = (len(lines) == 1)
    d = ["印出「w 臂趋势 p<α 的组合」的行 %d（期望 1）%s"
         % (len(lines), "✅" if ok else "❌")]
    if lines:
        m = re.search(r"w 臂趋势 p<α 的组合 (\d+)/(\d+)", lines[0])
        if not m:
            ok = False
            d.append("❌ 小结行里认不出组合数：%s" % lines[0].strip()[:70])
        else:
            got = (int(m.group(1)), int(m.group(2)))
            good = (got == (w_pass, allr["n_combo"]))
            ok &= good
            d.append("小结印出 w 臂通过 %d/%d（实算 %d/%d）%s"
                     % (got[0], got[1], w_pass, allr["n_combo"],
                        "✅" if good else "❌"))
    return ok, d


def j_c13_rand_state_wording(allr, RP):
    """C13：rand 臂的**结论字段**必须与**实算的检出状态集合**一致（双向）。

    ⚖⚠⚖⚖ **这是本轮的核心判据**：
      · 若各组合的检出状态**不止一种** ⇒ 结论字段**必须**是「未量到」
        （⛔ 不许说成「rand 臂没有剂量趋势」，⛔ 也不许说成「rand 臂未检出」）
      · 若只有一种 ⇒ 结论字段**必须**是那个状态

    ⚖⚠⚖⚖⚖ **为什么用「结构化结论字段」而不是子串禁词**（244.63 自己踩的坑）：
      我第一版用「报告里不许出现 `rand 臂无剂量趋势`」这条子串检查
      ⇒ 报告里那句**否定**（`⛔ 既不能说「rand 臂无剂量趋势」`）**撞车** ⇒ **假红**。
    ⇒ 禁词检查必须落在**一个可解析的字段**上（⇒ 双向可红，且不会撞否定句）。
    """
    states = sorted({s["arm"]["rand"]["state"] for s in allr["scenarios"]})
    want = "未量到" if len(states) > 1 else states[0]
    # ⚖ 每条臂线都必须印出自己的检出状态词（⛔ 少印一条 ⇒ 读者无法复核）
    sl = [ln for ln in RP if "检出状态=" in ln]
    good = (len(sl) == allr["n_combo"] * 2)
    ok = good
    d = ["印出「检出状态=」的行 %d（期望 %d = %d 组合 × 2 臂）%s"
         % (len(sl), allr["n_combo"] * 2, allr["n_combo"],
            "✅" if good else "❌")]
    lines = [ln for ln in RP if "rand 臂的剂量—响应结论" in ln]
    good = (len(lines) == 1)
    ok = ok and good
    d.append("印出「rand 臂的剂量—响应结论」的行 %d（期望 1）%s"
             % (len(lines), "✅" if good else "❌"))
    if lines:
        m = re.search(r"结论（α 上）= \*\*(.+?)\*\*", lines[0])
        if not m:
            ok = False
            d.append("❌ 结论行里认不出结论词：%s" % lines[0].strip()[:70])
        else:
            got = m.group(1)
            good = (got == want)
            ok &= good
            d.append("结论词印出「%s」（期望「%s」｜ 实算状态集合 %s）%s"
                     % (got, want, states, "✅" if good else "❌"))
            for bad_word in ("无差异", "无剂量趋势", "没有差异", "不存在"):
                if bad_word in got:
                    ok = False
                    d.append("❌ 结论词含禁止的说法「%s」" % bad_word)
    # ---- 状态集合那一行也必须与实算一致 ----
    slines = [ln for ln in RP if "rand 臂「检出状态」集合" in ln]
    good = (len(slines) == 1)
    ok &= good
    d.append("印出「rand 臂「检出状态」集合」的行 %d（期望 1）%s"
             % (len(slines), "✅" if good else "❌"))
    if slines:
        m = re.search(r"集合 = \{([^}]*)\}（(\d+) 种）", slines[0])
        if not m:
            ok = False
            d.append("❌ 小结行里认不出状态集合：%s" % slines[0].strip()[:70])
        else:
            got = [x.strip() for x in m.group(1).split("、") if x.strip()]
            n_got = int(m.group(2))
            good = (got == states) and (n_got == len(states))
            ok &= good
            d.append("小结印出状态集合 %s（%d 种）｜ 实算 %s（%d 种）%s"
                     % (got, n_got, states, len(states), "✅" if good else "❌"))
    if len(states) > 1:
        good = any("未量到" in ln for ln in RP)
        ok &= good
        d.append("状态不止一种 ⇒ 报告**必须**写「未量到」%s" % ("✅" if good else "❌"))
    else:
        good = any(states[0] in ln for ln in RP)
        ok &= good
        d.append("状态只有一种 ⇒ 报告**必须**写 %s %s"
                 % (states[0], "✅" if good else "❌"))
    return ok, d


def j_c14_wording_guard(allr, RP):
    """C14：措辞护栏 —— ⛔ 报告不许出现「无差异」；基准组合的 rand 状态词必须印出。"""
    ok = True
    d = []
    bad = [ln for ln in RP if "无差异" in ln]
    good = (not bad)
    ok &= good
    d.append("⛔ 报告里出现「无差异」的行 %d（必须 0）%s"
             % (len(bad), "✅" if good else "❌"))
    base_state = allr["base"]["arm"]["rand"]["state"]
    good = any(base_state in ln for ln in RP)
    ok &= good
    d.append("基准组合的 rand 状态词 %s 必须被印出 %s"
             % (base_state, "✅" if good else "❌"))
    good = any("未量到" in ln for ln in RP)
    ok &= good
    d.append("报告必须出现「未量到」%s" % ("✅" if good else "❌"))
    return ok, d


def j_c15_labels_printed(RP):
    """C15：前提声明与边界清单的**标签**必须一个不少（⛔ 少一条就红）。

    ⚖⚠⚖ 期望集**独立写死**（`PREAMBLE_MARKS` / `BLANK_MARKS`）
    ⇒ ⛔ 不许从 PREAMBLE / BLANKS 派生（派生 ⇒ 恒绿护栏，244.60 的变异台抓到过）。
    """
    ok = True
    d = []
    for mk in PREAMBLE_MARKS:
        good = any(mk in ln for ln in RP)
        ok &= good
        d.append("前提标签 %s %s" % (mk, "✅" if good else "❌"))
    for mk in BLANK_MARKS:
        good = any(mk in ln for ln in RP)
        ok &= good
        d.append("边界标签 %s %s" % (mk, "✅" if good else "❌"))
    return ok, d


# ---------------------------------------------------------------- 主流程
def run():
    allr = build_all()
    RP = build_report(allr)
    res = []

    def put(cid, ok, detail):
        res.append((cid, bool(ok), detail))

    put("C0", *j_c0_baseline(allr["base"]))
    put("C1", *j_c1_space(allr))
    put("C2", *j_c2_not_idle(allr, RP))
    put("C3", *j_c3_layer_base(allr))
    put("C4", *j_c4_verdicts_printed(allr, RP))
    put("C5", *j_c5_flip_count(allr, RP))
    put("C6", *j_c6_mc_calibration())
    put("C7", *j_c7_denominators(allr, RP))
    put("C8", *j_c8_scope_k_printed(allr, RP))
    put("C9", *j_c9_pperm_matches_exact(allr))
    put("C10", *j_c10_mc_band_printed(allr, RP))
    put("C11", *j_c11_combos_match_expect(allr))
    put("C12", *j_c12_w_arm_all_combos(allr, RP))
    put("C13", *j_c13_rand_state_wording(allr, RP))
    put("C14", *j_c14_wording_guard(allr, RP))
    put("C15", *j_c15_labels_printed(RP))

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

    ⚖⚠⚠⚠ **期望集不许从被检对象派生**（244.60/244.61 的教训）
    ⇒ 这里的变异都是**改坏**的，而**干净**那一侧由真实数据路径保证。
    """
    return [
        ("C0", "基准的档数表被改坏",
         lambda a: a["base"]["arm"]["w"]["bands"].__setitem__(
             0, ("frac<=q1", a["base"]["arm"]["w"]["bands"][0][1][:-1]))),
        ("C0", "基准的趋势 p 被篡改",
         lambda a: a["base"]["arm"]["w"]["trend"].__setitem__("p", 0.5)),
        ("C1", "组合数被改成 4",
         lambda a: a.__setitem__("n_combo", 4)),
        ("C1", "一个组合的标签被改成另一个",
         lambda a: a["scenarios"][-1].__setitem__(
             "label", a["scenarios"][-2]["label"])),
        ("C2", "所有组合都被标成空转",
         lambda a: [s.__setitem__("idle", {k: True for k in s["idle"]})
                    for s in a["scenarios"]]),
        ("C3", "层内基准被改成 0.5",
         lambda a: [row.__setitem__("bases", [0.5] * len(row["bases"]))
                    for s in a["scenarios"] for arm in ("w", "rand")
                    for row in s["arm"][arm]["rows"]]),
        ("C4", "报告里少印一个组合的判决", "RP"),
        ("C5", "翻转标记的行数与算出来的不一致",
         lambda a: a["scenarios"][0].__setitem__("flip", not a["scenarios"][0]["flip"])),
        ("C6", "MC 校准用的零分布被换成恒真的 p", "CAL"),
        ("C7", "某一层两臂的格数被改坏（配对标记没跟着改）",
         lambda a: a["scenarios"][0]["arm"]["rand"]["rows"][0].__setitem__(
             "celln", a["scenarios"][0]["arm"]["rand"]["rows"][0]["celln"] + 1)),
        ("C7", "不配对的组合被标成「配对成立」",
         lambda a: a["scenarios"][1].__setitem__("paired_ok", True)),
        ("C7", "报告里配对标记被改错", "RP"),
        ("C8", "报告里少印一条剂量轴口径多数", "RP"),
        ("C9", "配对置换 p 被篡改",
         lambda a: a["scenarios"][-1]["layers"][0].__setitem__("pperm", 0.999)),
        ("C10", "报告里少印一条 MC95%带", "RP"),
        ("C11", "某个组合的档表被改坏",
         lambda a: a["scenarios"][-1]["arm"]["rand"]["bands"].__setitem__(
             0, ("frac<q1", a["scenarios"][-1]["arm"]["rand"]["bands"][0][1][:-1]))),
        ("C12", "小结里 w 臂的通过组合数被写错", "RP"),
        ("C13", "小结里 rand 臂的状态集合被写错", "RP"),
        ("C14", "报告里出现了「无差异」", "RP"),
        ("C15", "前提声明少印一条标签", "RP"),
    ]


def selftest():
    """⚖ 自检：① 每条判据在**干净输入**上必须全绿 ② 喂**变异数据**必须红。"""
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", t, why))

    RP, res, allr = run()
    chk("S0", all(o for _c, o, _d in res),
        "真实数据路径上全部判据必须绿（实测 %d/%d）"
        % (sum(1 for _c, o, _d in res if o), len(res)))

    fns = {
        "C0": lambda a, rp: j_c0_baseline(a["base"]),
        "C1": lambda a, rp: j_c1_space(a),
        "C2": lambda a, rp: j_c2_not_idle(a, rp),
        "C3": lambda a, rp: j_c3_layer_base(a),
        "C4": lambda a, rp: j_c4_verdicts_printed(a, rp),
        "C5": lambda a, rp: j_c5_flip_count(a, rp),
        "C6": lambda a, rp: j_c6_mc_calibration(),
        "C7": lambda a, rp: j_c7_denominators(a, rp),
        "C8": lambda a, rp: j_c8_scope_k_printed(a, rp),
        "C9": lambda a, rp: j_c9_pperm_matches_exact(a),
        "C10": lambda a, rp: j_c10_mc_band_printed(a, rp),
        "C11": lambda a, rp: j_c11_combos_match_expect(a),
        "C12": lambda a, rp: j_c12_w_arm_all_combos(a, rp),
        "C13": lambda a, rp: j_c13_rand_state_wording(a, rp),
        "C14": lambda a, rp: j_c14_wording_guard(a, rp),
        "C15": lambda a, rp: j_c15_labels_printed(rp),
    }
    for cid, name, mut in _mutations():
        a2 = copy.deepcopy(allr)
        RP2 = list(RP)
        if mut == "RP":
            if cid == "C4":
                RP2 = [ln for ln in RP if a2["scenarios"][-1]["label"] not in ln]
            elif cid == "C8":
                RP2 = [ln for ln in RP if "剂量轴口径多数" not in ln]
            elif cid == "C10":
                RP2 = [ln for ln in RP if "MC95%带" not in ln]
            elif cid == "C12":
                RP2 = [ln.replace("w 臂趋势 p<α 的组合 %d/%d"
                                  % (sum(1 for s in allr["scenarios"]
                                         if s["arm"]["w"]["trend"]["p"] < ALPHA),
                                     allr["n_combo"]),
                                  "w 臂趋势 p<α 的组合 1/%d" % allr["n_combo"])
                       for ln in RP]
            elif cid == "C13":
                RP2 = [ln.replace("结论（α 上）= **未量到**",
                                  "结论（α 上）= **无差异**") for ln in RP]
            elif cid == "C14":
                RP2 = RP + ["  ⚠ 两臂无差异"]
            elif cid == "C15":
                RP2 = [ln for ln in RP if "【P3】" not in ln]
            elif cid == "C7":
                RP2 = [ln.replace(
                    "**不成立**（两臂格数不同 ⇒ 该组合的**跨臂比较未量到**）",
                    "成立（两臂逐层同格同数）") for ln in RP]
        elif mut == "CAL":
            okc, _dc = j_c6_mc_calibration()
            chk("S-%s" % cid, okc, "MC 零分布双向校准：%s" % "✅" if okc else "❌")
            continue
        else:
            mut(a2)
        try:
            got, _d = fns[cid](a2, RP2)
        except Exception as e:      # ⚖ 判据不许崩 ⇒ 崩了算「红」
            chk("S-%s" % cid, False, "判据在变异数据上**崩了**（%s）⇒ 算红" % e)
            continue
        chk("S-%s" % cid, (not got),
            "变异「%s」后 %s 必须红（实测 %s）" % (name, cid, "红" if not got else "**仍绿**"))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="剂量轴口径审计（零 GPU、不连远端）")
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
