#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dose_layer_audit.py —— 判决面板的**剂量分层**（修订 244.60，零 GPU）

🔴🔴 **本工具问什么**

  244.48/244.50 已证：面板上那个多数（w **12/14** vs rand **6/14**）是
  **跨不同剂量**的多数 ⇒ 固定/分层剂量之前，「噪声」与「剂量」**不可分辨**。

  ⚖ 本工具**就地分层**：用 244.50 的**注入比例剂量轴**把 14 条轨迹的格切成
  **4 个剂量层**，在**每层内部**重新数「多少条轨迹为真」，给出
  **w / rand 各自多少条、差多少 pp、p 值、区间**。

⚖⚠⚠⚠⚠ **本工具钉住的那个陷阱（最要紧的一条）**

  **层内的零假设基准不是 0.5。**
  ⚖ 因为「平票算 False」，而每条轨迹在每层只有 **1–3 格**：
     · 1 格 ⇒ 基准 0.5
     · **2 格 ⇒ 基准 0.25**（两条**都**正才算正）
     · 3 格 ⇒ 基准 0.5
  ⚖⚠⚠ 实测各层平均基准 **0.3036 / 0.2500 / 0.3571 / 0.3214**（⛔ **不是 0.5**）
  ⇒ ⚠⚠ **沿用 0.5 基准会把结论说反**（层 2 的 w 臂：正确基准 p=0.0070（显著）
     vs 0.5 基准 p=0.1796（不显著））⇒ 判据 **C3/C4** 专门盯这条。

⚖⚠⚠⚠ **跨臂比较用的是「配对置换检验」**，不是生产的 Fisher：
  生产 Fisher 假设「每条轨迹为真的概率 = 0.5」⇒ **在层内这个前提是错的**
  ⇒ 本工具**两个都印**（生产 Fisher 保留 ⛔ 不许删），但**结论用配对置换**：
  它把「两臂标签逐轨迹交换」当作零假设 ⇒ **自动吸收** m 分布的不对称。

⚖ **复用既有生产机械（⛔ 不另写第二套真相）**

  · 剂量轴（分位点/四档）：`dose_confound_audit.dose_cells` / **`dose_bands`**
    （244.60 把 244.50 内联的档边界抽成**唯一实现**，⛔ 别处不许另写）
  · 逐轨迹符号：`verdict_source_audit.derive_arm` / `p9delta_per_tid`（244.55）
  · 面板口径的多数：`dose_confound_audit.majority_count`（244.50）
  · 符号检验 p：`r227_kcurve.sign_test`（⛔ 不手抄第二份）
  · 跨臂 Fisher：`arm_verdict.fisher_exact_two_sided`（生产）
  · 区间：`interval_audit.cp95` / `wilson_bounds` / `newcombe_diff`（244.58）
  · 功效：`cluster_premise_audit.fisher_power`（244.59，**精确枚举**）

⚖⚠⚠⚖ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不连远端、⛔ 不写/删任何数据文件。
⚖⚠⚖⚖ 每条判据都必须**能红**：自检用畸形夹具证明「红得了」，
变异台（`mut_dose_layer_audit.py`）在**源码层**证明「红得了」。

跑法：
    python3 dose_layer_audit.py
    python3 dose_layer_audit.py --selftest
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import collections
import importlib.util
import io
import itertools
import json
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
VSRC = os.path.join(HERE, "verdict_source_audit.py")
DCONF = os.path.join(HERE, "dose_confound_audit.py")
ARMV = os.path.join(HERE, "arm_verdict.py")
IAUD = os.path.join(HERE, "interval_audit.py")
CPRE = os.path.join(HERE, "cluster_premise_audit.py")
READER = os.path.join(REPO, ".cache", "mutbak", "r227_kcurve.py")
JSONL_W = os.path.join(HERE, "_an.txt")
JSONL_RAND = os.path.join(HERE, "_ra.txt")

ALPHA = 0.05
N_LAYER = 4

# ⚖ **账本里的权威值**（引用，⛔ 不是本工具算出来的）：244.50 的剂量轴
AXIS_QUANTILES = (0.015, 0.250, 0.750)
AXIS_BAND_SIZE = (27, 28, 30, 24)
AXIS_RHO = 0.6911
# ⚖⚠⚠ **rand 臂的 rho 是另一个数**（244.50：rand 臂没有剂量趋势，+0.024）
#   ⇒ ⛔ 不许把 w 臂的 0.6911 套到 rand 臂上（那是一条**与数据无关的假红**）
AXIS_RHO_RAND = 0.024
AXIS_POS = (11, 16, 23, 24)
# ⚖ 面板口径的多数（244.50 的 C1 / 244.55 的 C1）⇒ 证明「读的是同一批」
PANEL_MAJORITY = {"w": (12, 14), "rand": (6, 14)}

_MODS = {}


def _count_mark(RP, mark):
    """⚖ 报告里有几行含这个标记（用于「必须印出」型判据 ⇒ ⛔ 少印一条必须红）。"""
    return sum(1 for ln in RP if mark in ln)


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
    return _load(VSRC, "vs_24460")


def dconf():
    return _load(DCONF, "dc_24460")


def armv():
    return _load(ARMV, "av_24460")


def iaud():
    return _load(IAUD, "ia_24460")


def cpre():
    return _load(CPRE, "cp_24460")


def reader():
    return _load(READER, "r227_24460")


# ---------------------------------------------------------------- 层内零假设
def majority_base_p(nz):
    """⚖⚖⚖ **层内「多数为真」在零假设下的概率**。

    ⚖ 规则 `nT > nF` ⇒ **平票算 False** ⇒ 零假设下
       `nT ~ Bin(nz, 0.5)`、`nF = nz − nT` ⇒ 正号的概率 = P(nT > nz/2)。

    ⚖⚠⚠⚠⚠ **nz = 2 ⇒ 0.25（⛔ 不是 0.5）** ⇒ 各层基准不同
       ⇒ ⛔ **不许**拿 0.5 当层内基准（那会把结论说反）。
    ⚖ 抽成独立函数是为了让自检能用**已知答案**的夹具钉住它。
    """
    if nz <= 0:
        return 0.5
    return sum(math.comb(nz, j) * 0.5 ** nz
               for j in range(nz // 2 + 1, nz + 1))


def poisson_binomial_pmf(ps):
    """⚖ Poisson-binomial 的 PMF（DP；纯 stdlib，⛔ 不引 scipy）。"""
    dist = [1.0]
    for p in ps:
        nd = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            nd[i] += v * (1.0 - p)
            nd[i + 1] += v * p
        dist = nd
    return dist


def pb_two_sided(ps, k):
    """⚖ PB 的双尾 p —— **与生产 `sign_test` 同约定**（概率 ≤ 观测概率的全算进来）。"""
    dist = poisson_binomial_pmf(ps)
    if k < 0 or k >= len(dist):
        return 1.0
    obs = dist[k]
    return sum(v for v in dist if v <= obs + 1e-12)


def pb_pmf_by_enumeration(nzs):
    """⚖⚖⚖ PB PMF 的**直接枚举**版（**独立机械**；⛔ 不用 DP 的结果）。

    ⚖ 每条轨迹的 `nz` 个格子各有两种符号 ⇒ 全部 `2^Σnz` 种分配逐一数。
    ⚖ ⚠⚠ **只适合小规模**（`Σnz` ≤ ~20）⇒ 判据用它复核 DP 的一小段真数据。
    """
    total = 0
    counts = collections.Counter()
    for bits in itertools.product((0, 1), repeat=int(sum(nzs))):
        i = 0
        k = 0
        for nz in nzs:
            npos = sum(bits[i:i + nz])
            i += nz
            if npos * 2 > nz:
                k += 1
        counts[k] += 1
        total += 1
    return [counts.get(i, 0) / float(total) for i in range(len(nzs) + 1)]


def paired_perm_p(diffs, n_perm=20000, seed=20261020):
    """⚖⚖⚖ **配对置换检验**（跨臂比较用）。

    ⚖ 零假设 = 「两臂的标签逐轨迹**可交换**」⇒ 逐轨迹随机交换两臂的判定
    ⇒ 统计量 = 两臂「为真条数」之差 ⇒ p = P(|T| ≥ |T_obs|)。

    ⚖⚠⚠ **为什么不用生产的 Fisher**：Fisher 假设「每条轨迹为真的概率 = 0.5」
    ⇒ 在层内这个前提**是错的**（基准是 0.25–0.5，且各层不同）
    ⇒ 本工具**两个都印**，但**结论用配对置换**。
    """
    obs = sum(diffs)
    if not diffs:
        return 1.0, 0
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_perm):
        t = 0
        for d in diffs:
            t += d if rng.random() < 0.5 else -d
        if abs(t) >= abs(obs):
            ge += 1
    return (ge + 1) / (n_perm + 1.0), obs


def mc_trend_p_geom(nzs_by_layer, obs_counts, n_mc=5000, seed=20261020):
    """⚖⚖⚖ **剂量趋势检验**（MC 零假设）—— **多返回 MC 的计数**（`ge` / `n_mc`）。

    ⚖ 统计量 `T = Σ_L (L − 1.5) · (K_L − E0_L)`：`K_L` = 该层为真的条数，
    `E0_L` = 该层在零假设下的**期望条数**（`Σ_t base_p(nz_t)`）。
    ⚖ 零假设 = 「**每格公平硬币**」⇒ MC 模拟（**尊重每条轨迹的 nz 与平票规则**）
    ⇒ p = P(T_sim ≥ T_obs)。

    ⚖⚠⚠⚠ **为什么不能用 0.5 基准**：各层的 m 分布不同 ⇒ 基准不同
    ⇒ 「层间比大小」这个原始统计量**被 m 混淆** ⇒ 必须用**各自的基准**。

    ⚖⚠⚠⚠⚖ **为什么多返回 `ge` / `n_mc`（244.62 加的）**：
    `p = (ge+1)/(n_mc+1)` 只是**点估计**，MC 本身有**蒙特卡洛误差**
    ⇒ 244.62 要报「p 的不确定带」（当 p 贴着 α 时，这个带是**决定性的**）
    ⇒ **一个实现**：`mc_trend_p` 是本函数的薄包装 ⇒ ⛔ 不许另写第二份 MC。
    """
    e0 = [sum(majority_base_p(nz) for nz in nzs_by_layer[L]) for L in range(N_LAYER)]
    t_obs = sum((L - 1.5) * (obs_counts[L] - e0[L]) for L in range(N_LAYER))
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_mc):
        tot = 0.0
        for L in range(N_LAYER):
            k = 0
            for nz in nzs_by_layer[L]:
                npos = sum(1 for _ in range(nz) if rng.random() < 0.5)
                if npos * 2 > nz:
                    k += 1
            tot += (L - 1.5) * (k - e0[L])
        if tot >= t_obs - 1e-12:
            ge += 1
    return (ge + 1) / (n_mc + 1.0), t_obs, e0, ge, n_mc


def mc_trend_p(nzs_by_layer, obs_counts, n_mc=5000, seed=20261020):
    """⚖⚖⚖ **剂量趋势检验**（MC 零假设）。

    ⚖ 统计量与零假设见 `mc_trend_p_geom`（**唯一实现**）⇒ 本函数是它的**薄包装**
    （返回 `(p, T, e0)`，⛔ 不带 MC 计数 ⇒ 244.60/244.61 的调用点**逐位不变**）。
    """
    p, t_obs, e0, _ge, _n = mc_trend_p_geom(nzs_by_layer, obs_counts, n_mc, seed)
    return p, t_obs, e0


# ---------------------------------------------------------------- 数据层
def cell_sign_p9(r):
    """⚖ 244.48 的口径：格级 `d = p9_hi_meas − p9_lo_meas > 0`。"""
    return dconf().d_of(r) > 0


def cell_sign_pre(r):
    """⚖ 预登记口径：格级 `up_mono_meas`。"""
    return r.get("up_mono_meas") is True


def layer_verdicts(cells_by_tid, sign_fn):
    """⚖ 逐轨迹在层内的多数（`nT > nF` ⇒ **平票算 False**）。

    ⚖ 返回 {tid: {pos, neg, nz, m, verdict}}；`nz` = **非零**格数
    （`d == 0` 的格既不算正也不算负 ⇒ 只进分母不进基准）。
    """
    out = {}
    for tid, cs in cells_by_tid.items():
        nT = sum(1 for c in cs if sign_fn(c))
        nF = sum(1 for c in cs if not sign_fn(c))
        out[tid] = {"pos": nT, "neg": nF, "nz": nT + nF, "m": len(cs),
                    "verdict": nT > nF}
    return out


def build_all():
    """⚖ 从**读数**导出：剂量轴、每层的格、每层的逐轨迹判定。"""
    VS = vsrc()
    DC = dconf()
    rows = {"w": VS.load_rows(JSONL_W), "rand": VS.load_rows(JSONL_RAND)}
    out = {"rows": rows, "arm": {}}
    for arm, rs in rows.items():
        ks, fr = DC.dose_cells(rs)
        qs, bands = DC.dose_bands(ks, fr)
        frac_by_id = {id(r): f for r, f in zip(ks, fr)}
        layers = collections.OrderedDict()
        layer_fracs = collections.OrderedDict()
        for i, (_lab, sub) in enumerate(bands):
            g = collections.OrderedDict()
            gf = collections.OrderedDict()
            for r in sub:
                g.setdefault(r["tid"], []).append(r)
                gf.setdefault(r["tid"], []).append(frac_by_id[id(r)])
            layers[i] = {"cells": g, "fracs": gf}
            for tid, vs in gf.items():
                layer_fracs.setdefault(tid, []).extend(vs)
        out["arm"][arm] = {"ks": ks, "fr": fr, "qs": qs, "bands": bands,
                           "layers": layers, "layer_fracs": layer_fracs,
                           "rho": DC.spearman(fr, [DC.d_of(r) for r in ks]),
                           "panel": DC.majority_count(rs),
                           "scope_k": DC.majority_count(ks)}
    return out


# ---------------------------------------------------------------- 判据
PREAMBLE = (
    "【P1】⚖⚠⚠⚠ **层内的零假设基准不是 0.5** —— 「平票算 False」＋每条轨迹每层只有 1–3 格"
    " ⇒ 2 格的层基准塌到 **0.25** ⇒ ⛔ 沿用 0.5 基准会把结论**说反**",
    "【P2】⚖⚠⚠⚠ **跨臂比较用「配对置换检验」**（零假设＝两臂标签逐轨迹可交换）"
    " ⇒ **自动吸收**各层 m 分布的不对称；生产 Fisher 也印，但**不许**拿它当层内结论",
    "【P3】⚖⚠⚠⚠ **层间不是独立的**（同一批 14 条轨迹、同一批格）⇒ 四层**不许**当四个独立检验",
    "【P4】⚖⇒ ✅ 「**差 ≠ 0**」在**每一层**都要单独看（区间可能含 0 ⇒ 那层就**未量到**）",
)

BLANKS = (
    ("【B1】**剂量层的机制含义**",
     "四层只是**注入比例**的四分位 ⇒ 机制是否随之改变，⛔ 本地量不到"),
    ("【B2】**层间独立性**",
     "四层共享同 14 条轨迹 ⇒ 相关结构**未量到**（本工具只报各层单独的量）"),
    ("【B3】**层内的重复性**",
     "rep_n=1 ⇒ 层内读数 ~1σ ⇒ 「rand 臂层内少数为真是不是噪声」**仍未解释**"),
    ("【B4】**`pos_frac` 只在 0.5 取过值**",
     "别的取值下「位置轴」的含义**没有**任何实测支撑"),
    ("【B5】**纯剂量轴**（剂量与机制完全正交的那一轴）",
     "本节只是**把现有格按剂量切开** ⇒ 机制与剂量**仍不可分辨**"),
    ("【B6】**哪一条臂是机制效应**",
     "两臂的多数**都**是**跨剂量**的多数（244.48/244.50）⇒ 本节只把剂量**拆开**、⛔ 不指定机制"),
    ("【B7】**固定剂量下「改判了多少题」**",
     "本节给的是**现有格**的分层结果 ⇒ ⛔ 与「固定剂量下改判」**不是同一件事**（要新跑一批）"),
)

# ⚖⚠⚖⚖⚠⚠ **「第二份真相」**：下面这两个列表与 PREAMBLE / BLANKS **刻意重复**。
#   ⛔ **不可**从 PREAMBLE / BLANKS 派生 —— 244.60 的变异台**当场抓到**：
#   派生（`PREAMBLE_REQUIRED = tuple(PREAMBLE)`）⇒ **删掉一条被检对象时
#   期望集同步变小** ⇒ 判据**永远绿** ⇒ 恒绿护栏
#   （⛔ 用户明令：恒绿护栏要么删、要么改成能红的形状）。
#   ⚖ 判据只查**短标签**（【P1】…【B7】）⇒ 散文可以随便改，标签一个都不能少。
PREAMBLE_MARKS = ("【P1】", "【P2】", "【P3】", "【P4】")
BLANK_MARKS = ("【B1】", "【B2】", "【B3】", "【B4】", "【B5】", "【B6】", "【B7】")


def build_report(A):
    RP = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        RP.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    IA = iaud()
    AV = armv()
    st = reader().sign_test
    w = A["arm"]["w"]
    ra = A["arm"]["rand"]

    RP.append("【0】⚖⚠⚠⚠ **前提声明**（⛔ 删掉任何一条都必须红）")
    for s in PREAMBLE:
        RP.append("  " + s)
    RP.append("")

    # ---- C0 剂量轴逐位复现 244.50 ----
    ok0 = True
    d0 = []
    for arm in ("w", "rand"):
        a = A["arm"][arm]
        want_rho = AXIS_RHO if arm == "w" else AXIS_RHO_RAND
        good = (tuple(round(q, 3) for q in a["qs"]) == AXIS_QUANTILES
                and tuple(len(b[1]) for b in a["bands"]) == AXIS_BAND_SIZE
                and abs(a["rho"] - want_rho) <= 5e-4)
        ok0 = ok0 and good
        d0.append("%s 分位点 %s ｜ 档 %s ｜ rho %+.4f（账本 %+.4f）"
                  % (arm, "/".join("%.3f" % q for q in a["qs"]),
                     "/".join(str(len(b[1])) for b in a["bands"]), a["rho"], want_rho))
    pos0 = tuple(sum(1 for r in w["bands"][i][1] if dconf().d_of(r) > 0)
                 for i in range(N_LAYER))
    ok0 = ok0 and (pos0 == AXIS_POS)
    d0.append("w 各档为正 %s（账本 %s）"
              % ("/".join(str(x) for x in pos0), "/".join(str(x) for x in AXIS_POS)))
    put("C0", ok0, "剂量轴必须**逐位复现 244.50**（先证明「读的是同一批」）：%s"
        % "；".join(d0))

    # ---- C1 面板口径复现 + 两臂同格 ----
    ok1 = True
    d1 = []
    for arm in ("w", "rand"):
        a = A["arm"][arm]
        good = (a["panel"] == PANEL_MAJORITY[arm])
        ok1 = ok1 and good
        d1.append("%s 面板口径（全部格）%d/%d（账本 %d/%d）"
                  % (arm, a["panel"][0], a["panel"][1],
                     PANEL_MAJORITY[arm][0], PANEL_MAJORITY[arm][1]))
    tids = sorted(A["arm"]["w"]["layers"][0]["cells"])
    same = True
    for L in range(N_LAYER):
        gw = A["arm"]["w"]["layers"][L]["cells"]
        gr = A["arm"]["rand"]["layers"][L]["cells"]
        if sorted(gw) != sorted(gr):
            same = False
        for t in gw:
            if len(gw[t]) != len(gr.get(t, [])):
                same = False
    ok1 = ok1 and same and (len(tids) == 14)
    d1.append("两臂每层轨迹集合与**每条轨迹的格数**逐条相同：%s（轨迹 %d 条）"
              % (same, len(tids)))
    put("C1", ok1, "面板口径必须复现账本 **且** 两臂必须**同格同数**（配对的前提）：%s"
        % "；".join(d1))

    # ---- C2 每层的计数 / 差 pp / 区间 ----
    RP.append("  ℹ 每层的 w / rand（主口径 = 244.48 的 `d = p9_hi − p9_lo > 0` 多数）")
    layer_rows = []
    ok2 = True
    for L in range(N_LAYER):
        vw = layer_verdicts(A["arm"]["w"]["layers"][L]["cells"], cell_sign_p9)
        vr = layer_verdicts(A["arm"]["rand"]["layers"][L]["cells"], cell_sign_p9)
        kw = sum(1 for t in vw if vw[t]["verdict"])
        kr = sum(1 for t in vr if vr[t]["verdict"])
        nw, nr = len(vw), len(vr)
        pw = float(kw) / nw
        pr = float(kr) / nr
        clw, cuw = IA.cp95(kw, nw)
        clr, cur = IA.cp95(kr, nr)
        wlw, wuw = IA.wilson_bounds(kw, nw)
        wlr, wur = IA.wilson_bounds(kr, nr)
        nd = IA.newcombe_diff(kw, nw, kr, nr)
        pf, _ = AV.fisher_exact_two_sided(kw, nw - kw, kr, nr - kr)
        diffs = [(1 if vw[t]["verdict"] else 0) - (1 if vr[t]["verdict"] else 0)
                 for t in sorted(vw)]
        pperm, obs = paired_perm_p(diffs)
        # ⚖⚖⚖ **格级正号率**（⛔ **不受**「平票算 False」影响 ⇒ 它是**最干净**的剂量—响应量）
        gpw = sum(1 for c in A["arm"]["w"]["layers"][L]["cells"].values()
                  for x in c if cell_sign_p9(x))
        gpn = sum(len(c) for c in A["arm"]["w"]["layers"][L]["cells"].values())
        gpr = sum(1 for c in A["arm"]["rand"]["layers"][L]["cells"].values()
                  for x in c if cell_sign_p9(x))
        layer_rows.append({"L": L, "vw": vw, "vr": vr, "kw": kw, "kr": kr,
                           "nw": nw, "nr": nr, "pw": pw, "pr": pr,
                           "cpw": (clw, cuw), "cpr": (clr, cur),
                           "wilsw": (wlw, wuw), "wilsr": (wlr, wur),
                           "newc": nd, "fisher": pf, "pperm": pperm,
                           "obs": obs, "diffs": diffs,
                           "cellpos": (gpw, gpn, gpr),
                           "cellrate": (gpw / float(gpn), gpr / float(gpn))})
        RP.append("    · 层 %d：w %d/%d（%.3f，CP95 [%s, %s]，W95 [%s, %s]）"
                 " ｜ rand %d/%d（%.3f，CP95 [%s, %s]）"
                 " ｜ 差 %+.1fpp（Newcombe [%+.4f, %+.4f]）"
                 " ｜ 配对置换 p=%.4f ｜ 生产 Fisher %.4f"
                 % (L, kw, nw, pw, IA.fmt(clw), IA.fmt(cuw), IA.fmt(wlw), IA.fmt(wuw),
                    kr, nr, pr, IA.fmt(clr), IA.fmt(cur),
                    100.0 * (pw - pr), nd[0], nd[1], pperm, pf))
        RP.append("      · 格级正号率（⛔ **不受平票规则影响**）：w %d/%d=%.3f"
                 " ｜ rand %d/%d=%.3f"
                 % (gpw, gpn, gpw / float(gpn), gpr, gpn, gpr / float(gpn)))
        good = (nd[0] > 0 or nd[1] < 0)
        RP.append("      ⇒ 差区间%s" % ("**不含 0**" if good else "**含 0 ⇒ 该层未量到**"))
    # ⚖⚖⚖ C2 的**能红**内容：每层的计数必须与**生产机械** `dose_confound_audit.majority_count`
    #   逐层一致（⛔ 不许只印数；两支实现不一致 ⇒ 必须红）
    #   ⚖⚠⚠ **并且必须报出「两条多数规则」的差别**（244.60 的新发现）：
    #   · 面板口径（`majority_count`）：`d>0` 的格数 **×2 > 总格数**（零**进**分母）
    #   · 轨迹级符号检验口径（`p9delta_per_tid`）：`pos > neg`（零**不计**）
    #   ⇒ rand 臂有 `d == 0` 的格 ⇒ 两者**不等**（6/14 vs 5）⇒ 必须报出来
    ok2 = True
    d2 = []
    VS = vsrc()
    for L in range(N_LAYER):
        for arm in ("w", "rand"):
            cells = [c for cs in A["arm"][arm]["layers"][L]["cells"].values()
                     for c in cs]
            prod_k, prod_n = dconf().majority_count(cells)
            mine = layer_verdicts(A["arm"][arm]["layers"][L]["cells"], cell_sign_p9)
            mk = sum(1 for t in mine if mine[t]["verdict"])
            same = (prod_k == mk and prod_n == len(mine))
            ok2 = ok2 and same
            d2.append("层 %d %s：生产机械 %d/%d vs 本工具 %d/%d %s"
                      % (L, arm, prod_k, prod_n, mk, len(mine),
                         "✅" if same else "❌"))
    RP.append("  ℹ ⚠⚠ **两条多数规则**在 rand 臂**不等**（244.60 新发现）：")
    for L in range(N_LAYER):
        row = None
        for r_ in layer_rows:
            if r_["L"] == L:
                row = r_
        cells = [c for cs in A["arm"]["rand"]["layers"][L]["cells"].values()
                 for c in cs]
        prod = VS.p9delta_per_tid(cells)
        k_alt = sum(1 for t in prod if prod[t]["verdict"])
        nzeros = sum(1 for c in cells if dconf().d_of(c) == 0.0)
        RP.append("    · 层 %d：面板口径（零进分母）%d/14 ｜ 符号检验口径（零不计）%d/14"
                  " ｜ 该层 `d==0` 的格 %d 个%s"
                  % (L, row["kr"], k_alt, nzeros,
                     "  ⚠⚠ **不等**" if k_alt != row["kr"] else ""))
    put("C2", ok2 and (_count_mark(RP, "两条多数规则") >= 1),
        "每层的计数必须与**生产机械** `majority_count` 逐层一致"
        "（⛔ 不许只印数），且**两条多数规则**的差别必须报出：%s" % "；".join(d2))

    # ---- C3 层内零假设基准：必须 ≠ 0.5，且 PB 的 PMF 必须与直接枚举逐位一致 ----
    ok3 = True
    d3 = []
    for row in layer_rows:
        L_ = row["L"]
        vw = row["vw"]
        nzs = [vw[t]["nz"] for t in sorted(vw)]
        bases = [majority_base_p(nz) for nz in nzs]
        avg = sum(bases) / len(bases)
        row["avg_base"] = avg
        row["bases"] = bases
        row["nzs"] = nzs
        differs = abs(avg - 0.5) > 1e-9
        ok3 = ok3 and differs
        d3.append("层 %d 平均基准 %.4f%s"
                  % (L_, avg, "" if differs else "（⛔ 竟等于 0.5 ⇒ 判据失效）"))
    # ⚖ PB 的 PMF 必须与**直接枚举**逐位一致（用一小段真数据：层 1 的前 4 条轨迹）
    v1 = layer_rows[1]["nzs"][:4]
    pmf_dp = poisson_binomial_pmf([majority_base_p(nz) for nz in v1])
    pmf_en = pb_pmf_by_enumeration(v1)
    same = all(abs(a - b) <= 1e-12 for a, b in zip(pmf_dp, pmf_en))
    ok3 = ok3 and same
    d3.append("PB 的 DP 与**直接枚举**逐位一致：%s（nz=%s）" % (same, v1))
    put("C3", ok3, "层内零假设基准必须**按实际非零格数算**（⛔ 不是 0.5），"
        "且 PB 的 PMF 必须与**直接枚举**逐位一致：%s" % "；".join(d3))

    # ---- C4 「用 0.5 基准会翻转结论」必须被报出 ----
    flips = []
    ok4 = True
    d4 = []
    for row in layer_rows:
        vw = row["vw"]
        bases = row["bases"]
        p_ok = pb_two_sided(bases, row["kw"])
        p_05 = st([1.0] * row["kw"] + [-1.0] * (row["nw"] - row["kw"]))[0]
        row["p_correct"] = p_ok
        row["p_05"] = p_05
        flip = (p_ok < ALPHA) != (p_05 < ALPHA)
        if flip:
            flips.append("层 %d（正确 %.4f ⇔ 0.5 基准 %.4f）"
                         % (row["L"], p_ok, p_05))
        d4.append("层 %d：w p 正确基准 %.6f vs 0.5 基准 %.6f%s"
                  % (row["L"], p_ok, p_05, "  ⚠⚠ **翻转**" if flip else ""))
        RP.append("    · " + d4[-1])
    # ⚖⚠⚖⚖ **「必须印出」型**：翻转不但要**算出来**，还要**印出来**
    #   （⛔ 只报「翻转 N 处」而不印逐层对照 ⇒ 读者无法复核 ⇒ 判据也抓不到「不印」）
    ok4 = len(flips) >= 1 and (_count_mark(RP, "**翻转**") >= 1)
    put("C4", ok4, "「用 0.5 基准会翻转结论」必须被**报出**（实测翻转 %d 处，"
        "且逐层对照必须印出 %d 行）：%s"
        % (len(flips), _count_mark(RP, "**翻转**"),
           "；".join(flips) if flips else "（未观察到翻转）"))

    # ---- C5 剂量趋势（w / rand 各自）----
    trend = {}
    for arm in ("w", "rand"):
        counts = []
        nzs_by_layer = []
        for L in range(N_LAYER):
            v = layer_verdicts(A["arm"][arm]["layers"][L]["cells"], cell_sign_p9)
            counts.append(sum(1 for t in v if v[t]["verdict"]))
            nzs_by_layer.append([v[t]["nz"] for t in sorted(v)])
        p_tr, t_obs, e0 = mc_trend_p(nzs_by_layer, counts)
        trend[arm] = {"p": p_tr, "T": t_obs, "e0": e0, "counts": counts}
        RP.append("    · %-4s 剂量趋势：各层 K=%s ｜ 各层零假设期望 E0=%s"
                 " ｜ T=%.3f ｜ MC p=%.4f"
                 % (arm, counts, [round(x, 2) for x in e0], t_obs, p_tr))
    ok_perm = True
    d_perm = []
    for row in layer_rows:
        nz = [d for d in row["diffs"] if d != 0]
        if not nz:
            continue
        p_exact = st([float(d) for d in nz])[0]
        good = abs(row["pperm"] - p_exact) <= 0.005
        ok_perm = ok_perm and good
        d_perm.append("层 %d：配对置换 %.4f vs 精确符号检验 %.6f %s"
                      % (row["L"], row["pperm"], p_exact, "✅" if good else "❌"))
    put("C5", (_count_mark(RP, "剂量趋势") >= 2) and ok_perm,
        "剂量趋势（w / rand **各一条**）必须印出（实测 %d 条），"
        "且**配对置换 p 必须与精确符号检验一致**（⛔ 置换台自己错了也要红）：%s"
        % (_count_mark(RP, "剂量趋势"), "；".join(d_perm)))

    # ---- C6 层内多数 vs 全量多数的不一致数 + 面板 12/14 vs scope=k ----
    d6 = []
    ok6 = True
    for arm in ("w", "rand"):
        a = A["arm"][arm]
        gk = collections.OrderedDict()
        for r in a["ks"]:
            gk.setdefault(r["tid"], []).append(r)
        vk = layer_verdicts(gk, cell_sign_p9)
        flips_n = []
        for L in range(N_LAYER):
            v = layer_verdicts(a["layers"][L]["cells"], cell_sign_p9)
            n = sum(1 for t in v if t in vk and v[t]["verdict"] != vk[t]["verdict"])
            flips_n.append((L, n, len(v)))
        d6.append("%s：面板口径（全部格）%d/%d ｜ 剂量轴口径（scope=k）%d/%d"
                  " ｜ 各层与全量不一致数 %s"
                  % (arm, a["panel"][0], a["panel"][1],
                     a["scope_k"][0], a["scope_k"][1],
                     "/".join("%d" % f[1] for f in flips_n)))
        RP.append("    · " + d6[-1])
        if a["panel"] != a["scope_k"]:
            allg = collections.OrderedDict()
            for r in A["rows"][arm]:
                if r.get("p9_lo_meas") is not None:
                    allg.setdefault(r["tid"], []).append(r)
            vfull = layer_verdicts(allg, cell_sign_p9)
            fl = sorted(t for t in vk if vk[t]["verdict"] != vfull[t]["verdict"])
            d6.append("   ⇒ ⚠⚠ 两口径**差 %d 条**（端点格 all/single 不在剂量轴上）：%s"
                      % (abs(a["panel"][0] - a["scope_k"][0]), fl[:4]))
    # ⚖ 备选口径 b：轨迹按「自己的中位剂量」归层 ⇒ 若几乎全落一层 ⇒ **退化**
    med_by_tid = collections.OrderedDict()
    for tid, vs in A["arm"]["w"]["layer_fracs"].items():
        # ⚖⚠⚠ **中位数用标准口径**（偶数个时取两中位的平均）⇒ ⛔ 不许用
        #   「上中位」那套（我第一版用了 ⇒ 结论从「退化」翻成「可用」）
        med_by_tid[tid] = statistics.median(vs)
    cnt = collections.Counter()
    qs_w = A["arm"]["w"]["qs"]
    for tid, med in med_by_tid.items():
        if med <= qs_w[0]:
            cnt[0] += 1
        elif med <= qs_w[1]:
            cnt[1] += 1
        elif med <= qs_w[2]:
            cnt[2] += 1
        else:
            cnt[3] += 1
    RP.append("    · 备选口径 b（轨迹按**自己的中位剂量**归层）：%s"
             % dict(sorted(cnt.items())))
    RP.append("      ⇒ %s" % ("⚠⚠ **退化**（几乎全落一层）⇒ 该口径**不可用**"
                          if max(cnt.values()) >= 12 else "可用"))
    ok6 = (_count_mark(RP, "不一致数") >= 2) and bool(cnt)
    put("C6", ok6, "层内多数与全量多数的**不一致数**（w / rand 各一条）必须印出，"
        "且备选口径 b 的退化情况必须报出（⚠ 那是**关于世界**的事实 ⇒ 只要求**如实印出**）")

    # ---- C7 跑批规模 ----
    RP.append("  ℹ 跑批规模（每层每臂要多少条轨迹 / 每条轨迹每层要多少格）")
    size = {}
    for row in layer_rows:
        p1, p0 = max(row["pw"], row["pr"]), min(row["pw"], row["pr"])
        delta = abs(p1 - p0)
        if delta <= 0:
            size[row["L"]] = {"need": None, "note": "两臂比例相同 ⇒ 所需条数 ∞"}
            RP.append("    · 层 %d：两臂比例相同 ⇒ 所需条数 **∞**" % row["L"])
            continue
        z975, z80 = 1.959963984540054, 0.8416212335729143
        pbar = (p1 + p0) / 2.0
        n_approx = max(14, int(math.ceil(
            2.0 * (z975 + z80) ** 2 * pbar * (1.0 - pbar) / (delta ** 2))))
        # ⚖⚠⚠⚠ **精确枚举的成本是 O(n³)**（`fisher_power` 是 n² 次 Fisher、每次 O(n)）
        #   ⇒ 复核**封顶 n ≤ 64**（⛔ 244.59 的教训：搜索上界会毁掉台架）
        n_chk = None
        note = ">64/臂（精确枚举 O(n³) ⇒ 本轮**不**复核）"
        if n_approx <= 64:
            for n in range(n_approx, 65, 2):
                if cpre().fisher_power(n, p1, p0)[0] >= 0.8:
                    n_chk = n
                    break
            note = "%s/臂" % n_chk
        size[row["L"]] = {"need": n_chk, "approx": n_approx}
        RP.append("    · 层 %d：w %.3f vs rand %.3f（差 %.1fpp）｜ 正态近似规模 %d/臂"
                 " ｜ **精确枚举复核 %s**（现有 14）"
                 % (row["L"], row["pw"], row["pr"], 100 * delta, n_approx, note))
    cells_per_traj = len(w["ks"]) / float(len(tids))
    need_cells = 3 * N_LAYER
    RP.append("    · 每条轨迹平均 k 档 %.2f ⇒ 要让每层 m≥3（平票不出现）需 ≥%d 档"
             " ⇒ 阶梯要扫到现在的 **%.2f 倍**"
             % (cells_per_traj, need_cells, need_cells / cells_per_traj))
    put("C7", (_count_mark(RP, "精确枚举复核") >= 1)
        and (_count_mark(RP, "正态近似规模") >= 1)
        and (_count_mark(RP, "m≥3") >= 1),
        "跑批规模的三块内容（**正态近似规模** / **精确枚举复核** / 每轨迹每层 **m≥3**）"
        "必须印出（⚠ 规模是**规划量**，⛔ 不是判决）")

    # ---- C8 前提声明 / C9 留白 ----
    # ⚖⚠⚖⚖⚠ **期望集与被检对象不同源**（244.60 的台架抓到：派生 ⇒ 恒绿 ⇒ 抓不到变异）
    #   ⇒ 这里查的是**独立写死的短标签**（【P1】…【B7】），⛔ 不从 PREAMBLE / BLANKS 派生
    RP.append("  ℹ 前提声明检查")
    miss8 = [s for s in PREAMBLE_MARKS if not any(s in ln for ln in RP)]
    put("C8", not miss8, "四条前提声明必须逐条印出（按**独立标签**查，"
        "⛔ 期望集**不**从被检对象派生）；缺 %d 条%s"
        % (len(miss8), "" if not miss8 else "：%s" % miss8))

    RP.append("  ℹ 未量到项（⛔ 写成「未量到」，⛔ 不许写成「无差异」）")
    for name, why in BLANKS:
        RP.append("    · %s —— %s" % (name, why))
    miss9 = [t for t in BLANK_MARKS if not any(t in ln for ln in RP)]
    put("C9", not miss9, "七条留白必须逐条印出（按**独立标签**查）；缺 %d 条%s"
        % (len(miss9), "" if not miss9 else "：%s" % miss9))

    return RP, R, layer_rows, trend


def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # ---- 层内基准：已知答案 ----
    chk("C0x", abs(majority_base_p(1) - 0.5) < 1e-12,
        "nz=1 ⇒ 基准 0.5（实测 %.6f）" % majority_base_p(1))
    chk("C0y", abs(majority_base_p(2) - 0.25) < 1e-12,
        "⛔ nz=2 ⇒ 基准 **0.25**（实测 %.6f）" % majority_base_p(2))
    chk("C0z", abs(majority_base_p(3) - 0.5) < 1e-12,
        "nz=3 ⇒ 基准 0.5（实测 %.6f）" % majority_base_p(3))
    chk("C0w", abs(majority_base_p(4) - 0.3125) < 1e-12,
        "nz=4 ⇒ 基准 0.3125（实测 %.6f）" % majority_base_p(4))
    chk("C0v", majority_base_p(2) != 0.5,
        "⚖⚠ **2 格的基准 ≠ 0.5** ⇒ 这就是「用 0.5 会说反」的根源")

    # ---- PB 的 DP vs 直接枚举（已知答案的小规模）----
    for nzs in ([2, 2], [1, 2, 3], [2, 2, 1]):
        dp = poisson_binomial_pmf([majority_base_p(nz) for nz in nzs])
        en = pb_pmf_by_enumeration(nzs)
        chk("C1x-%s" % ("".join(str(x) for x in nzs)),
            all(abs(a - b) <= 1e-12 for a, b in zip(dp, en)),
            "PB DP vs 枚举（nz=%s）逐位一致" % nzs)

    # ---- PB 双尾 p：与「枚举版」在同一约定下逐位一致 ----
    nzs = [2, 2, 1]
    ps = [majority_base_p(nz) for nz in nzs]
    dist = poisson_binomial_pmf(ps)
    tot = 0.0
    for bits in itertools.product((0, 1), repeat=int(sum(nzs))):
        i = 0
        k = 0
        for nz in nzs:
            npos = sum(bits[i:i + nz])
            i += nz
            if npos * 2 > nz:
                k += 1
        tot += 1.0
    obs = dist[1]
    p_enum = sum(dist[i] for i in range(len(dist)) if dist[i] <= obs + 1e-12)
    chk("C1y", abs(pb_two_sided(ps, 1) - p_enum) <= 1e-12,
        "PB 双尾 p：DP %.8f vs 枚举 %.8f" % (pb_two_sided(ps, 1), p_enum))

    # ---- 层内多数规则：平票算 False ----
    cs = [{"up": True}, {"up": False}, {"up": True}, {"up": True}]
    v = layer_verdicts({"t1": cs}, lambda r: r["up"])
    chk("C2x", v["t1"]["verdict"] is True and v["t1"]["nz"] == 4,
        "3 正 1 负 ⇒ 为真（实测 %s）" % v["t1"]["verdict"])
    cs2 = [{"up": True}, {"up": False}]
    v2 = layer_verdicts({"t1": cs2}, lambda r: r["up"])
    chk("C2y", v2["t1"]["verdict"] is False,
        "⛔ 1 正 1 负 ⇒ **平票算 False**（实测 %s）" % v2["t1"]["verdict"])

    # ---- 配对置换检验：零差异 ⇒ p 大；完全一致 ⇒ p 小 ----
    p0, obs0 = paired_perm_p([0, 0, 0, 0], n_perm=2000)
    chk("C3x", p0 > 0.5 and obs0 == 0,
        "四对全同号 ⇒ 差 0，p=%.4f" % p0)
    p1, obs1 = paired_perm_p([1, 1, 1, 1], n_perm=2000)
    # ⚖⚖⚖ **已知答案**：4 对全不一致 ⇒ T 只可能取 ±4 ⇒ 精确双尾 p = 2/16 = **0.125**
    #   （⛔ 我第一版写「p < 0.1」⇒ 那是**期望写错了**，不是实现错）
    chk("C3y", abs(p1 - 0.125) < 0.02 and obs1 == 4,
        "四对全不一致 ⇒ 差 4，精确 p=0.125（实测 %.4f）" % p1)

    # ---- 剂量趋势：完全单调 ⇒ MC p 小 ----
    nzs_flat = [[2] * 14 for _ in range(4)]
    p_mono, T, e0 = mc_trend_p(nzs_flat, [4, 6, 10, 14], n_mc=2000)
    chk("C4x", p_mono < 0.1, "单调递增的层计数 ⇒ MC p=%.4f" % p_mono)
    p_flat, T2, _ = mc_trend_p(nzs_flat, [7, 7, 7, 7], n_mc=2000)
    chk("C4y", p_flat > 0.1, "各层相同 ⇒ MC p=%.4f" % p_flat)
    # ⚖⚠⚖⚖⚠ **零分布校准**（244.60 的变异台**当场抓到**的一个真洞）：
    #   C4x / C4y 都是**单边**的 ⇒ 零分布**塌掉**时（每格必正 ⇒ T_sim 恒为 0）
    #   C4x 只会**更小**（p=0.0005）、C4y 只会**更大**（p=1.0）⇒ **两条照样绿**
    #   ⇒ 必须补一条**双边**的**校准**判据：
    #   零假设夹具（各层计数相同 ⇒ t_obs=0）⇒ p 必须 ≈ 0.5
    #   （实测 0.534；略高于 0.5 是因为「恰好等于 0」也算 ≥ 0 ⇒ 平局概率 ~0.07
    #     ⇒ +0.035；8 个 seed 实测落在 0.525–0.539 ⇒ 带宽 [0.35, 0.65] 极宽裕）
    #   ⇒ 零分布塌掉 ⇒ p=1.0 ⇒ **红**；零分布反号 ⇒ p≈0 ⇒ **红**。
    chk("C4z", 0.35 <= p_flat <= 0.65,
        "⛔ 零分布**校准**：零假设夹具（t_obs=0）⇒ p 必须≈0.5（实测 %.4f）" % p_flat)

    # ---- 真实数据：C0/C1 必须复现 ----
    A = build_all()
    w = A["arm"]["w"]
    chk("C5x", tuple(round(q, 3) for q in w["qs"]) == AXIS_QUANTILES,
        "真实数据：剂量轴分位点 %s"
        % ("/".join("%.3f" % q for q in w["qs"])))
    chk("C5y", w["panel"] == PANEL_MAJORITY["w"],
        "真实数据：面板口径 %d/%d" % (w["panel"][0], w["panel"][1]))
    v1 = layer_verdicts(w["layers"][1]["cells"], cell_sign_p9)
    bases = [majority_base_p(v1[t]["nz"]) for t in sorted(v1)]
    chk("C5z", abs(sum(bases) / len(bases) - 0.25) < 1e-12,
        "真实数据：层 1 的平均基准 %.6f（应是 0.25：14 条全是 2 格）"
        % (sum(bases) / len(bases)))

    print("")
    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % bad)
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(description="判决面板的剂量分层（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        A = build_all()
        RP, R, _rows, _trend = build_report(A)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print("\n".join(RP))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
    return 0 if all(R.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
