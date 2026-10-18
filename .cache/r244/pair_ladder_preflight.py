#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pair_ladder_preflight.py —— 「只差一个位点」的配对阶梯，**零 GPU 可行性预检**

🔴 **为什么要有这个工具**
  244.31–244.33 把 🔴 问题走到这里：
    · 「剂量—响应」曲线的形状主要由**机制切换**决定（层内无可检出剂量梯度）；
    · 那个切换处的台阶**新增了 372 个位点**，读出位点只占 1 个
      ⇒ 把 11.84× 归因给读出位点是**推断**，不是测量。
  ⚖⇒ 要判 J9（`added <= 1` 才允许读成纯机制），需要一个**两档只差一个位点**的阶梯。
  ⚗⇒ 本工具在**发批之前**把那个阶梯算出来并自证它满足判据。

⚖⚠ **设计（同 k 配对，不是「多加一个位点」）**
  S   = `_k_positions(n_eff, k_base, seed=0, nested=True)` 且**不含**读出位点
  S'  = S ∪ {n_eff − 1}
  ⚖⇒ 两档的 **k 只差 1**，覆盖率只差 **1/n_eff**（实测中位 0.00057）
     ⛔ 对比：现有阶梯的机制台阶 Δcov = 0.2498 ⇒ 配对方案小约 **440 倍**
     ⚗⇒ 这才是「剂量几乎不变、只有机制变」的那一档对照。

⚖⚠⚠⚠ 本工具**不**假设探针现在能这么做
  ⚖ `inject_scope` 实测只有 `["single", "all", "k"]`（`:777`），且 `_k_positions`
     **没有任何排除位点的能力**（全仓 grep 无 exclude/force/skip）。
  ⚖ ⇒ **跑批前必须先改探针**（新增一个能「强制排除/强制包含指定位点」的口径）。
  ⚗⇒ 本工具只负责证明「这个设计**成立**」，⛔ 不负责假装它已经能跑。

⚖⚠⚠ 边界情况必须报出来，不能藏
  ⚖ `k_base` 会被「读出位点在排列里的秩」夹住：秩小 ⇒ `k_base` 被压小
     ⇒ 该轨迹的配对覆盖率远低于别的轨迹。
  ⚖ 实测 14 条里有 **2 条**（秩 140 / 193）被夹到 cov≈0.063 / 0.167。
  ⚗⇒ 判据 K5 强制把条数印出来。

⚖ 独立单位：轨迹（14 条）。⛔ 格不独立。
⚖ 本工具零 GPU：只读已落盘的读数日志 + 探针源码。
"""

import argparse
import ast
import collections
import json
import os
import sys

RESP_HI = "p9_hi_meas"
RESP_LO = "p9_lo_meas"
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"

# ⚖ 现有阶梯机制台阶的 Δcov（244.33 实测：新增位点中位 372 ⇒ Δcov 中位 0.2498）。
# ⚖⚠⚠⚠ 这个数是**外部实测值**，⛔ 不许当常数写进判据 —— 判据只比
#     「配对 Δcov 与阶梯 Δcov 的比值」，⛔ 不比绝对值。
# ⚖⚠ 若把它写进 `if d_pair < LADDER_DCOV` 这种判据 ⇒ 改一下它结论就变
#     ⇒ 那是「门槛松紧改变结论」的配方（244.26 的 H6 已记过）。
LADDER_DCOV = 0.2498

# ⚖ 配对 Δcov 的上限：**剂量混淆必须可忽略**才允许把对照读成「只有机制变」。
# ⚖⚠ 这是**设计要求**，不是实测值；⛔ 但它同时被 T5 的精确值断言钉住。
PAIR_DCOV_MAX = 0.01

TARGET_COV = 0.25          # ⚖ 配对的**目标**覆盖率（任意取的中位档，实测可行）
CLAMP_COV = 0.20           # ⚖ 低于它 ⇒ k_base 被秩夹住了（判据 K5）


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 位点
def load_k_positions(probe_path=PROBE_REL, name="_k_positions"):
    """⚖ 从**真实源码**抽出并 exec —— ⛔ 不手抄（手抄就是第二份实现）。"""
    if not os.path.exists(probe_path):
        raise HardFail("找不到探针源码 %s ⇒ ⛔ 拒读" % probe_path)
    src = open(probe_path, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            fn = node
            break
    if fn is None:
        raise HardFail("探针源码里找不到 %s" % name)
    ns = {}
    exec(compile("import numpy as _np\n"
                 + ast.get_source_segment(src, fn), probe_path, "exec"), ns)
    # ⚖⚠⚠ 第一版这里写的是 `if fn.args.defaults: raise HardFail` ——
    #   ⛔ **那条守卫本身是错的**：`_k_positions(n, k, seed=0, nested=False)`
    #   本来就有 **2** 个默认值 ⇒ 它对**当前这份真实源码**也报红。
    #   ⚖⇒ 守卫必须写成「**期望**的默认值形态」，⛔ 不是「没有默认值」。
    import inspect
    sig = inspect.signature(ns[name])
    if sig.parameters["seed"].default != 0:
        raise HardFail("%s 的 seed 默认值是 %r，不是 0 ⇒ 本工具算的是另一组位点，"
                       "⛔ 拒读" % (name, sig.parameters["seed"].default))
    return ns[name]


def readout_rank(n, kpos):
    """⚖ 读出位点 `n−1` 在 `default_rng(0).permutation(n)` 里的秩。

    ⚖⚠⚠⛔ **必须走未排序的排列**：`sorted(排列)` 对任意排列都等于 `range(n)`
       （244.31 记的恒绿检查）。此处取的是 `perm[n−1] == n−1` 的**下标**，
       是真正携带信息的那个量。
    """
    import numpy as np
    perm = np.random.default_rng(0).permutation(n).tolist()
    if perm == list(range(n)):                    # ⚖ 反证件：排列不能是恒等
        raise HardFail("default_rng(0).permutation(%d) 恒等于 range(n) ⇒ "
                       "「秩」没有信息量，⛔ 拒读" % n)
    hits = [i for i, v in enumerate(perm) if v == n - 1]
    if len(hits) != 1:
        raise HardFail("排列里 %d-1 出现 %d 次 ⇒ 不是排列" % (n, len(hits)))
    return hits[0]


def pair_sets(n, kpos, target_cov=TARGET_COV):
    """⚖ 返回 (S, S', k_base, rank)。

    ⚖⚖⚖ 修订 244.34 的结构性修正：**守卫必须互不遮住**。
      ⚖⚠⚠ 第一版有三道守卫（K1「秩≥1」、K2「S 不含读出位点」、K3「S⊂S' 且恰好差 1」）。
      ⚖⚠⚠ 台架报出 K1/K2 的变异**全部存活** —— 原因是它们**被 K3 吞掉**：
      ⚖   若读出位点已在 S 里，则 `Sp = S` ⇒ `Sp − S = ∅`
      ⚖   ⇒ K3 的「恰好差 1 个」必然触发 ⇒ K1/K2 永远不会独自决定结果。
      ⚖⚗⇒ 两支守卫被同一支遮住 ⇒ 判据**没独立承重**（台架报「存活」的又一形态）。
      ⚖⇒ 修法：⛔ **删掉 K1/K2，只留 K3 这一道真守卫**，但让 K3 的
        **报错文案**区分病因（秩=0 / 位点集已含读出位点 / 位点数对不上）。
        ⚖⚠ 文案是**行为**（可被诊断依赖），本就用 T2/T7 两条夹具分别咬住。
    """
    rank = readout_rank(n, kpos)
    k_base = int(n * target_cov)
    # ⚖⚠ 夹到 rank：保证 `perm[:k]` 的**下标**取不到 rank，
    #   即集合**元素**里取不到读出位点。⛔ 少了这一步：小秩轨迹上
    #   `perm[:k]` 会**包含**读出位点 ⇒ 两档重合（K3 会抓到，但那时
    #   「k_base 差多少」这个信息已经丢了 ⇒ 报错指错病因）。
    k_base = min(k_base, rank)
    if k_base < 1:
        # ⚖ 秩=0 ⇒ 排列首位就是读出位点 ⇒ 任何非空 `perm[:k]` 都含它
        #   ⇒ 该 n 上配对**不存在**（夹到 k=0 会得到空集，那不是一档）。
        raise HardFail("n=%d：读出位点在排列里的秩=0 ⇒ 该 n 上**配对不可行**"
                       "（⛔ 夹到 k=0 会得到空集）" % n)
    if k_base >= n - 1:
        raise HardFail("n=%d：k_base=%d 已到 n−2 ⇒ 集合大到塞不下对照"
                       % (n, k_base))
    S = set(int(x) for x in kpos(n, k_base, nested=True))
    if len(S) != k_base:
        raise HardFail("n=%d：位点数 %d ≠ k_base %d ⇒ 分母口径变了，⛔ 拒读"
                       % (n, len(S), k_base))
    Sp = S | {n - 1}
    # ⚖⚠⚠ 244.34：**只有这一道守卫**。
    # ⚖⚠ 第一版把「S 已含读出位点」单列成一条 raise ⇒ ⛔ 它**遮住**了下面这条
    #   （含读出位点时 `Sp − S = ∅`，两条都会触发）⇒ K3 的变异存活。
    # ⚗⇒ 两种病因**共用一个出口**，文案负责区分 —— 这是可诊断性，不是第二条守卫。
    if not S < Sp or len(Sp - S) != 1:
        cause = ("位点集**已含**读出位点（多半是 k_base 没夹到 rank=%d）" % rank
                 if (n - 1) in S else "两档之差不为 1")
        raise HardFail("n=%d：%s ⇒ 构不成「只差一个位点」的配对，⛔ 拒读" % (n, cause))
    return S, Sp, k_base, rank


# --------------------------------------------------------------- 判据
def k4_pair_dcov_ok(d_pair):
    """⚖ **K4**：配对 Δcov 必须小到「剂量变化可忽略」。"""
    if d_pair is None or d_pair <= 0.0:
        return False
    return d_pair <= PAIR_DCOV_MAX


def k5_clamped(cov_s):
    """⚖ **K5**：该轨迹的配对覆盖率是否被读出位点的秩夹住了。⛔ 不许藏。"""
    return cov_s < CLAMP_COV


# --------------------------------------------------------------- 主流程
def read_neff(path):
    """⚖ 从已落盘读数里取每条轨迹的 `n_eff = P + t`（⛔ 不用 `len(pid)`）。"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith('{"tid"'):
                c = json.loads(line)
                ne = int(c["P"]) + int(c["t"])
                prev = out.get(c["tid"])
                if prev is not None and prev != ne:
                    raise HardFail("轨迹 %s 的 n_eff 在格间不一致：%d vs %d ⇒ "
                                   "⛔ 拒读" % (c["tid"], prev, ne))
                out[c["tid"]] = ne
    if not out:
        raise HardFail("%s 里没读到任何格 ⇒ **未量到**，⛔ 不许当「不可行」" % path)
    return out


def med(v):
    s = sorted(v)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def run(w_log, probe_path=PROBE_REL, target_cov=TARGET_COV, ladder_dcov=LADDER_DCOV,
        arms=("w", "rand")):
    kpos = load_k_positions(probe_path)
    neff = read_neff(w_log)
    L = []
    L.append("【1】逐轨迹的配对（两档只差读出位点这一个）")
    L.append("  ⚖ S = perm[:k_base]（**不含**读出位点）；S' = S ∪ {n_eff−1}")
    L.append("  %-26s %-7s %-7s %-9s %-9s %-9s %s"
             % ("轨迹", "n_eff", "k_base", "读出位点秩", "cov(S)", "cov(S')", "夹住?"))
    dcs, covs, clamped = [], [], []
    for tid in sorted(neff):
        n = neff[tid]
        S, Sp, k_base, rank = pair_sets(n, kpos, target_cov)
        cov_s, cov_sp = k_base / float(n), (k_base + 1) / float(n)
        d = cov_sp - cov_s
        dcs.append(d)
        covs.append(cov_s)
        cl = k5_clamped(cov_s)
        if cl:
            clamped.append(tid)
        L.append("  %-26s %-7d %-7d %-9d %-9.4f %-9.4f %s"
                 % (tid[-16:], n, k_base, rank, cov_s, cov_sp,
                    "⚠ 是" if cl else "否"))
    dp = med(dcs)
    L.append("")
    L.append("【2】K4：配对的 Δcov vs 现有阶梯台阶的 Δcov（**都要算出来再比**）")
    L.append("  ⚖ 配对 Δcov = 1/n_eff：中位 **%.5f**（范围 %.5f..%.5f）"
             % (dp, min(dcs), max(dcs)))
    L.append("  ⚖ 阶梯台阶 Δcov = %.4f（244.33 实测：新增位点中位 372）" % ladder_dcov)
    if dp is None or ladder_dcov <= 0:
        L.append("  K4：**未量到** ⇒ ⛔ 不许说「剂量变化可忽略」")
        ratio = None
    else:
        ratio = ladder_dcov / dp
        ok = k4_pair_dcov_ok(dp)
        L.append("  ⇒ 配对方案的剂量变化比阶梯台阶**小 %.0f 倍**" % ratio)
        L.append("  K4：%s" % ("✅ 通过（Δcov ≤ %.4f）" % PAIR_DCOV_MAX if ok else
                              "⚠⚠ **不通过**：Δcov > %.4f ⇒ 剂量变化不可忽略，"
                              "⛔ 这组对照不能读成「只有机制变」" % PAIR_DCOV_MAX))
    L.append("")
    L.append("【3】K5：被读出位点的秩夹住的轨迹（⛔ 不许藏）")
    L.append("  ⚖ 目标覆盖率 %.2f；低于 %.2f 视为被夹住" % (TARGET_COV, CLAMP_COV))
    L.append("  ⇒ **%d / %d 条**被夹住%s"
             % (len(clamped), len(neff),
                ("：" + "、".join(t[-14:] for t in clamped)) if clamped else ""))
    if clamped:
        L.append("  ⚠⚠ 这些轨迹的配对**剂量**与别的轨迹不同 ⇒ 跨轨迹比 Δraw 是"
                 "⛔ 不许的；只用**轨迹内**配对差。")
    L.append("")
    L.append("【4】格数与前置（⛔ 本工具**没有**跑批）")
    cells = 2 * len(neff) * len(arms)
    L.append("  ⚖ 需要 **%d 格** = %d 轨迹 × 2 档 × %d 臂"
             % (cells, len(neff), len(arms)))
    L.append("  ⚖⚠⚠⛔ **前置未满足**：探针的 `inject_scope` 实测只有 "
             "`[\"single\", \"all\", \"k\"]`（`:777`），")
    L.append("     且 `_k_positions` **没有**排除/强制包含指定位点的能力")
    L.append("     ⇒ ⛔ 现在**跑不出**这个对照，必须先改探针。")
    L.append("  ⚖ 顺带：`--repeat R` **已存在**（`:773`，默认 1）"
             "⇒ `rep_n≥2` 不用写新代码；")
    L.append("     ⛔ 但重复值**只作诊断**，判据仍取 `meas[0]`（`:456`）"
             "⇒ 预登记必须写明「重复不入统计量」。")
    return "\n".join(L), 0, {"d_pair_med": dp, "ratio": ratio,
                             "clamped": clamped, "cells": cells,
                             "n_traj": len(neff)}


# --------------------------------------------------------------- 自检
def _stub_kpos(n, k, seed=0, nested=False):
    """⚖ 夹具：忠实复制探针的 `_k_positions`（含 `k==n` 恒等捷径）。"""
    import numpy as np
    n, k = int(n), int(k)
    if k == n:
        return list(range(n))
    if k == 0:
        return []
    if nested:
        return sorted(int(x) for x in np.random.default_rng(int(seed)).permutation(n)[:k])
    return sorted(np.random.default_rng(int(seed)).choice(n, size=k,
                                                          replace=False).tolist())


def try_pair(n, kpos, tc=TARGET_COV):
    """⚖ 调 `pair_sets`，并把 `HardFail` 变成**干净的红**返回，不让它带崩自检。

    ⚖⚠⚠⚖ 244.34 的第三条教训：**台架把「崩」记成「台架坏了」**。
      ⇒ 每一条会调到 `pair_sets` 的断言都必须走它，否则某个变异
      造成的「抛」会被记成台架故障，而**不是**「该判据咬住了」。
    ⚗⇒ 要的是**干净的按判据变红**。
    """
    try:
        return pair_sets(n, kpos, tc), None
    except HardFail as e:
        return None, str(e)


def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # T1 读出位点秩：⛔ 不许走 sorted（244.31 的恒绿检查）
    # ⚖⚠⚠ 这里必须 try/except：变异 P7（把排列**排序**后再找秩）会触发
    #   「反证件 ⇒ HardFail」⇒ ⛔ 不接住的话整轮自检**崩**，
    #   台架把「崩」记成「台架坏了」而不是「P7 咬住了」。⚗ 要**干净的变红**。
    try:
        r = readout_rank(1000, _stub_kpos)
        chk("T1", isinstance(r, int) and 1 <= r < 1000,
            "readout_rank(1000)=%r（须在 [1,999]，⛔ 不许是 0 或 999）" % r)
    except HardFail as e:
        chk("T1", False, "readout_rank 抛 HardFail（反证件或秩异常）：%s" % str(e)[:40])

    # T2 秩=0 ⇒ 该 n 上配对不可行，必须 HardFail，且**文案要说清病因**
    # ⚖⚠⚠ 第一版调的是 `readout_rank` —— ⛔ **调错了层**：守卫在 `pair_sets` 里，
    #   `readout_rank` 只是**报**秩。⚗⇒ 守卫在哪一层，测试就调那一层。
    import numpy as np
    real_rng = np.random.default_rng

    class _FirstIsLast:
        def __init__(self, seed=0):
            pass

        def permutation(self, n):
            # ⚖⚠ 必须返回 **ndarray**：真 `default_rng().permutation(n)` 返回的是
            #   ndarray，⛔ 夹具返回 list 会让被测函数在 `.tolist()` 上炸
            #   ⇒ 台架把「崩」记成「台架坏了」，而不是「夹具写错」。
            # ⚖⚠⚠ 第一版写 `arange(1, n+1)` ⇒ 值 n−1 落在下标 **n−2**，秩根本不是 0
            #   ⇒ T2 报红。⚗ 要让秩=0，排列必须**以 n−1 开头**：[n−1, 0, 1, …, n−2]。
            return np.concatenate([np.array([n - 1]), np.arange(n - 1)])

        def choice(self, n, size=None, replace=False):
            return np.arange(size or n)

    try:
        np.random.default_rng = lambda seed=0: _FirstIsLast(seed)
        _res, err2 = try_pair(500, _stub_kpos)
        chk("T2", err2 is not None and "配对不可行" in err2,
            "秩=0 ⇒ 拒读且**文案说清病因**（含「配对不可行」）%s"
            % ("" if err2 is None else "：%s" % err2[:30]))
    finally:
        np.random.default_rng = real_rng

    # T3 正常配对：n=4000 与**小秩** n=2210（真实秩=140）都必须成立
    # ⚖⚠⚠ 第一版这里**同时**调了 n=2210（小秩）⇒ 变异 P1（去掉夹住）会让它
    #   直接抛 ⇒ 崩。⚗⇒ 小秩那一条归 **T9**（已 try/except）单独承重。
    res, err = try_pair(4000, _stub_kpos)
    if err is not None:
        chk("T3", False, "n=4000 的正常配对竟被拒读：%s" % err[:40])
    else:
        S, Sp, kb, rank = res
        chk("T3", (4000 - 1) not in S and S < Sp and len(Sp - S) == 1
            and len(S) == kb,
            "pair_sets(4000)：|S|=%d、S'−S=%d 个位点、S⊂S'、读出位点∉S"
            % (len(S), len(Sp - S)))

    # T9 ⚖ `k_base` 必须**被秩夹住**：n=2210 的秩是 140，
    #    ⛔ 不夹的话 k_base 会取 int(2210*0.25)=552 ⇒ 集合**含**读出位点。
    #    ⚗⇒ 但那种情况下 T3 会抛 HardFail ⇒ 测的是「抛不抛」，
    #       ⛔ 测不到「夹到了 140」这个**具体行为** ⇒ 需要独立断言 k_base == 秩。
    # ⚖⚠⚠ 必须 try/except：变异 P1（去掉夹住）会让 n=2210 直接抛 HardFail
    #   ⇒ ⛔ 不接住就是**崩**，而台架记的是「台架坏了」。
    res9, err9 = try_pair(2210, _stub_kpos)
    if err9 is not None:
        chk("T9", False, "n=2210 被拒读 ⇒ **夹住**失效：%s" % err9[:44])
    else:
        _S9, _Sp9, kb2, rank2 = res9
        chk("T9", kb2 == rank2 and kb2 == 140,
            "n=2210：k_base=%d 必须夹到秩=%d（⛔ 不是 int(n*0.25)=552）"
            % (kb2, rank2))

    # T4 K4 双向：Δcov 太大必须不通过；刚好在门槛内必须通过
    chk("T4", k4_pair_dcov_ok(1.0 / 4000.0) is True
        and k4_pair_dcov_ok(0.25) is False and k4_pair_dcov_ok(0.0) is False
        and k4_pair_dcov_ok(None) is False,
        "K4：1/4000⇒通过；0.25⇒不通过；0 / None ⇒ 不通过")

    # T5 ⚖⚠⚠⚖ 必须用**字面量**，⛔ 不得引用 `PAIR_DCOV_MAX` 自己。
    # ⚖⚠ 第一版写 `k4_pair_dcov_ok(PAIR_DCOV_MAX) is True` 与
    #   `k4_pair_dcov_ok(PAIR_DCOV_MAX*1.000001) is False`
    #   ⚖⚠⚠ **对任何阈值都成立** ⇒ 它验的是**行为形状**，⛔ 验不出阈值**被改了**
    #   ⇒ 变异 `PAIR_DCOV_MAX 0.01 → 0.5` **存活**。
    # ⚗⇒ 断言一个常数的**值**，就必须写死那个值 ⇒ 同
    #   「范围断言是弱守卫」：能过它的常数太多了。
    chk("T5", k4_pair_dcov_ok(0.01) is True
        and k4_pair_dcov_ok(0.02) is False,
        "K4 阈值**值**：Δcov=0.01⇒通过（⛔ 0.01 是设计要求）；0.02⇒不通过")

    # T6 K5 双向：被夹住要报；没被夹住不许报
    chk("T6", k5_clamped(0.063) is True and k5_clamped(0.167) is True
        and k5_clamped(0.2498) is False and k5_clamped(0.25) is False,
        "K5：0.063 / 0.167⇒夹住；0.2498 / 0.25⇒没夹住")

    # T7 K3 能红：把 `perm[:k]` 换成含读出位点的集合 ⇒ 必须 HardFail
    def _kpos_bad(n, k, seed=0, nested=False):
        """⚖ 夹具：**替换**掉最后一个位点为读出位点（模拟「k_base 没夹到秩」）。

        ⚖⚠⚠⚖ 第一版用的是 `set(...) | {n-1}`（**并集**）⇒ 位数变成 k+1
          ⇒ 被「位数自证」那条守卫**抢先**触发 ⇒ T7 在替**别人**承重，
          ⛔ 而 K3（唯一承重的那道）被完全遮住 ⇒ 它的变异存活。
        ⚗⇒ 破坏「恰好差一个位点」这条不变量的夹具，必须**只破坏这一条**。
        """
        s = list(_stub_kpos(n, k, seed, nested))
        s[-1] = n - 1
        return sorted(set(s))
    _res, err7 = try_pair(4000, _kpos_bad)
    chk("T7", err7 is not None and "已含" in err7,
        "S 含读出位点 ⇒ 拒读且文案点明病因%s"
        % ("" if err7 is None else "（已含…）" if "已含" in err7 else "（⛔ 文案没说病因）"))

    # T10 ⚖ 位点数自证：位点集**位数对不上** k_base ⇒ 必须拒读
    #     ⚖⚠ 第一版没有这条 ⇒ 把「位数自证」换成恒假时**完全不可见**
    #   ⚖⚠ 因为在**正常**夹具上位数永远等于 k_base ⇒ 守卫的正确路径是恒不触发，
    #   ⇒ 只有一条**故意破坏**的夹具才能咬住它。
    def _kpos_short(n, k, seed=0, nested=False):
        """⚖ 夹具：只给 k−1 个位点（模拟「位数与 k 不符」）"""
        return _stub_kpos(n, k, seed, nested)[:max(0, k - 1)]
    _res, err10 = try_pair(4000, _kpos_short)
    chk("T10", err10 is not None and "位点数" in err10,
        "位数比 k_base 少 1 ⇒ 拒读%s"
        % ("" if err10 is None else "：%s" % err10[:34]))

    # T11 ⚖ `seed` 默认值守卫：探针若用 seed=1，本工具算的是**另一组位点**
    #     ⚖⚠ 第一版完全没有这条 ⇒ 变异 `seed != 0` 检查被拆时**完全不可见**。
    # ⚖⚠⚠ 这条要一个**真的探针文件**：夹具版 kpos 不经过 AST 抽取。
    #   ⚗⇒ 自检写临时文件是可以的（判据**不读自己的源码**，读的是另一份夹具）。
    import tempfile
    _probe_src = ("def _k_positions(n, k, seed=%d, nested=False):\n"
                  "    import numpy as _np\n"
                  "    n, k = int(n), int(k)\n"
                  "    if k == n:\n"
                  "        return list(range(n))\n"
                  "    if k == 0:\n"
                  "        return []\n"
                  "    return sorted(int(x) for x in "
                  "_np.random.default_rng(int(seed)).permutation(n)[:k])\n")
    _fd, _path = tempfile.mkstemp(suffix="_probe.py")
    try:
        with os.fdopen(_fd, "w", encoding="utf-8") as _f:
            _f.write(_probe_src % 1)          # ⚖ seed 默认值故意给 **1**
        try:
            load_k_positions(_path)
            chk("T11", False, "探针 seed 默认值=1 却过了 ⇒ 守卫被拆或读的是另一组位点")
        except HardFail as e:
            chk("T11", "seed" in str(e), "seed 默认值非 0 被拒读：%s" % str(e)[:38])
        # T11b 正常侧：seed=0 必须通过（防守卫过严）
        with open(_path, "w", encoding="utf-8") as _f:
            _f.write(_probe_src % 0)
        try:
            fn = load_k_positions(_path)
            chk("T11b", callable(fn) and fn(100, 5) is not None,
                "seed 默认值=0 正常通过")
        except HardFail as e:
            chk("T11b", False, "守卫过严：seed=0 被拒（%s）" % str(e)[:34])
    finally:
        try:
            os.unlink(_path)
        except OSError:
            pass

    # T8 med 口径：偶数取两中位平均（⛔ 不是上中位，244.31 的 H9）
    chk("T8", med([1.0, 3.0]) == 2.0 and med([1.0, 2.0, 3.0]) == 2.0
        and med([]) is None, "med 偶数取平均、空⇒None")

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="配对阶梯的零 GPU 可行性预检")
    ap.add_argument("--w-log", default=None, help="w 臂读数日志（取 n_eff）")
    ap.add_argument("--probe", default=PROBE_REL)
    ap.add_argument("--target-cov", type=float, default=TARGET_COV)
    ap.add_argument("--ladder-dcov", type=float, default=LADDER_DCOV)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.w_log:
        raise HardFail("必须给 --w-log（⛔ 少一份 ⇒ 「未量到」，⛔ 不许当「不可行」）")
    txt, rc, _ = run(args.w_log, args.probe, args.target_cov, args.ladder_dcov)
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
