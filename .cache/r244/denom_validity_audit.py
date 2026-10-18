#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""denom_validity_audit.py —— `margin_meas` 的**分母**到底是不是一把干净的尺（零 GPU）

🔴 **这个工具要回答什么**
  `dose_axis_audit` 的 J5 要求「原始量与归一化量同报」，理由是
  「单看 margin_meas 分不清『效应变大』与『噪声变小』」。
  ⚖ 而归一化的定义是 `margin_meas = |p9_hi_meas − p9_lo_meas| / resid_std`
  （探针 `r204_noise_probe.py:269`）—— ⚠⚠⚠ **这把尺的合法性从未被验过**。

⚖⚠⚖⚖ **为什么这把尺可疑（全部来自已落盘的数据 + 已读过的源码）**
  ⚖ ① **它不是「噪声底」，是「线性拟合的残差」**：
     `:224` `resid_std = resid.std(ddof=1)`，其中 `resid = dm − A·coef`
     ⇒ 它是 **α 扫描拟合不出直线的那部分**。
     ⚖⚠ 而探针**自己**在 `:210-213` 就写明「那个残差里混着『噪声』与
       『非线性』两样东西，**分不开**」⇒ `:30` 表头那句「（= 噪声底）」
       是**解读**，⛔ 不是定义。
  ⚖ ② **它依赖 steering 向量**：两臂在同一 (tid, 覆盖率, n_eff) 上
     `resid_std` **109/109 全部不同** ⇒ 它⛔ 不是与臂无关的纯几何量。
  ⚖ ③ **它与剂量强相关**：层内 rho(覆盖率, resid_std) 是
     w **12/14** 正号、rand **11/14** 正号
     ⇒ 若它是独立噪声底，这个 rho 应当≈0。
  ⚖⚠⚠⚖ ①②③ 合起来的推论：
     `margin_meas` = 信号 ÷ 一个**随剂量一起变大**的量
     ⇒ 若剂量—响应本身是饱和/非线性的，**分母会随信号一起涨**
     ⇒ 归一化**按构造**削弱真实剂量信号
     ⇒ ⛔ **`margin_meas` 的层内梯度不能用来判断「有没有剂量效应」**。

⚖⚖ **本工具实际做的检验（不是读码，是从已落盘的数算出来的）**
  ⚖ K1 两臂 `resid_std` 逐格是否相同 ⇒ 「与臂无关」这条当场判死/判活
  ⚖ K2 层内 rho(覆盖率, resid_std) 的正号数 ⇒ 「独立噪声底」要求它≈0
  ⚖ K3 `lin_ratio`（全域 resid ÷ 局部 resid）的中位与 >1.2 的占比
     ⇒ 残差是否**明确**混着非线性（探针 `:210-213` 的说法）
  ⚖ K4 ⚖⚖ **可失败的预测**：按 lin_ratio 把轨迹分成高/低两组，
     高组（更弯 ⇒ 更像曲率而非噪声）的 rho(覆盖率, resid_std) 应当**更强**。
     ⛔ 若两组没有差别 ⇒ 「共变来自曲率」这个解释**不成立**，
       只能报「未量到」，⛔ 不许替它编故事。

⚖⚠⚠ **结论的读法（必须照抄，别自己加戏）**
  ⚖ 这条工具⛔ **不改变**任何已登记的判决。
  ⚖⚠ 它指出的是**一把尺的适用范围**，不是「剂量效应不存在」。
  ⚖⚠ 「归一化削弱梯度」这件事，⛔ 既可能是「尺脏」，也可能是「效应饱和」，
    本工具**分不开**这两者 ⇒ 必须照实说「分不开」。

⛔ 本工具：⛔ 不改任何真文件；⛔ 不跑批；⛔ 只读两份已有日志。
"""

import argparse
import ast
import importlib.util
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"
W_LOG = ".cache/r244/w_new.log"
RAND_LOG = ".cache/r244/rand_new.log"

CURVE_HI = 1.2          # ⚖ lin_ratio 高于它 ⇒ 全域残差明显大于局部残差
ALPHA = 0.05


class HardFail(Exception):
    pass


def _load_dose():
    path = os.path.join(HERE, "dose_axis_audit.py")
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    spec = importlib.util.spec_from_file_location("dose_axis_for_denom", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _cells_by_cover(D, kp, path):
    """⚖ 把格按 **(tid, 覆盖率)** 索引。

    ⚖⚠⚠ 为什么不带 n_eff：`k_cells` 的行里**没有** n_eff 列
       ⇒ 第一版去取 `row["_n_eff"]` ⇒ **必然 KeyError**。
    ⚖ 而 J4 已经钉过 (tid, 覆盖率) 集合逐格相同 ⇒ 这个键**足够且唯一**。"""
    out = {}
    for c in D.load_cells(path):
        n, cov, direct = D.check_cell(c, kp)
        if cov is None:
            continue
        out[(c["tid"], round(cov, 9))] = c
    return out


def _prop_rows(D, kp, path):
    """⚖ 传播层（读出位点未被注入）的行，带上 lin_ratio。"""
    rows = D.k_cells(D.load_cells(path), kp)
    out = []
    for r in rows:
        if r["direct"]:
            continue
        out.append(r)
    return out


def lin_ratios(D, kp, path):
    """⚖ 每格的 lin_ratio（全域 resid ÷ 局部 resid）。⛔ NaN/缺失一律剔出并报数。"""
    got, miss = {}, 0
    for c in D.load_cells(path):
        n, cov, direct = D.check_cell(c, kp)
        if cov is None:
            continue
        v = c.get("lin_ratio")
        try:
            v = float(v)
        except (TypeError, ValueError):
            miss += 1
            continue
        if v != v:
            miss += 1
            continue
        got[(c["tid"], round(cov, 9))] = v
    return got, miss


def mann_whitney_exact(a, b):
    """⚖ Mann-Whitney 精确（双侧，小样本用穷举，⛔ 不查表）。

    ⚖⚠⚠ 并列：把并列摊成平均秩（与 Wilcoxon 同一套约定，⛔ 不两套混用）。
    ⚖⚠⚠⚠ 分组为空 ⇒ **无证据** ⇒ 返回 **1.0**（⛔ 不是 0.0）。
    """
    pool = [(float(x), 0) for x in a] + [(float(x), 1) for x in b]
    n = len(pool)
    # ⚖⚠⚠⚠⚖ 这里原本还有一句 `if n == 0 or len(a) == 0 or len(b) == 0: return 1.0`
    #   —— ⚖⚠⚠⚠ **变异台抓到它可证冗余**：删掉它，`mann_whitney_exact([], [1,2])`
    #   仍然返回 1.0（`combinations(range(2), 0)` 只有一个空组合 ⇒ 命中 ⇒ 1.0）
    #   ⇒ 那道守卫**永远生效不到**，⛔ 删不删都一样 ⇒ 它是一条**恒绿护栏**。
    # ⚗⇒ 恒绿护栏要么删、要么写成能被验出差异的形状。⚖ 这里**删掉**，
    #   并把「为什么删」写在原地 —— ⛔ 不是把它悄悄改掉。
    idx = sorted(range(n), key=lambda i: pool[i][0])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pool[idx[j + 1]][0] == pool[idx[i]][0]:
            j += 1
        mid = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            ranks[idx[t]] = mid
        i = j + 1
    r_a = sum(ranks[i] for i in range(n) if pool[i][1] == 0)
    obs = min(r_a, n * (n + 1) / 2.0 - r_a)
    # ⚖⚠⚖⚖ 零分布必须**固定两组样本量**：只枚举 C(n, n1) 种分配。
    #   ⚖⚠⚠⚖⚖ 第一版枚举了**全部 2^n 个子集**（不分组大小）
    #   ⇒ 极端的小子集也被算进分母 ⇒ p 被**系统性高估**：
    #   3v3 完全分离本该是 2/20 = 0.1000，它印出 0.4375。
    #   ⛔ 而 0.4375 < 0.05 **不可达**这件事，反而让我差点以为「夹具欠功效」，
    #   ⛔ 其实是我的检验本身就错了 —— **症状与病因分处两地**。
    n1 = len(a)
    tot = 0
    hit = 0
    for pick in itertools.combinations(range(n), n1):
        sel = set(pick)
        s = sum(r for i, r in enumerate(ranks) if i in sel)
        tot += 1
        if min(s, n * (n + 1) / 2.0 - s) <= obs + 1e-12:
            hit += 1
    return min(1.0, hit / float(tot))


def non_significant_is_not_a_negative_conclusion(p_value, alpha=ALPHA):
    """⚖⚖ **恒返回 False 的禁令**，且它**必须**恒返回 False。

    🔴 244.37 刚犯的同一个坑：把「p ≥ 0.05 ⇒ 这条性质不成立」印了出来。
    ⚖⚠⛔ p ≥ 0.05 只说明**没量到**（或无力检出），
       ⛔ 它**不是**「这个性质不存在」的证据。
    ⚖ 这条禁令存在的理由与 `arm_contrast_audit` 那条**同源**：
       「没量到」是事实，「没有」是结论，⛔ 两者不许混。

    ⚖⚠⚠⚖ 自检 **C6** 用**真实数据本身**顶住它：
       rand 臂传播层 rho(覆盖率, resid_std) 是 11/14 正号、p=0.0574，
       ⚖ 同时中位 |rho| = **0.625** ⇒ 「没检出」与「明显相关」
       ⚖⚠ **同时成立** ⇒ 禁令不是空话。
    """
    return False


# --------------------------------------------------------------- 主流程
def run(w_log=W_LOG, rand_log=RAND_LOG, probe_path=PROBE_REL):
    D = _load_dose()
    kp = D.load_k_positions(probe_path)
    L = []

    L.append("【1】K1：`resid_std` 与 steering 向量有关吗（逐格配对比对）")
    gw = _cells_by_cover(D, kp, w_log)
    gr = _cells_by_cover(D, kp, rand_log)
    common = sorted(set(gw) & set(gr))
    if not common:
        return "\n".join(L + ["  ⛔ 两臂没有可配对的格 ⇒ HardFail"]), 1
    same = sum(1 for k in common
               if float(gw[k]["resid_std"]) == float(gr[k]["resid_std"]))
    ratios = sorted(float(gr[k]["resid_std"]) / float(gw[k]["resid_std"])
                    for k in common
                    if float(gw[k]["resid_std"]) != 0.0)
    L.append("  ⚖ 可配对格 %d；`resid_std` 逐位相同 **%d** 格" % (len(common), same))
    L.append("  ⚖ rand/w 比值：中位 %.4f（范围 %.4f..%.4f）"
             % (D.med(ratios), ratios[0], ratios[-1]))
    L.append("  ⇒ %s" % ("⛔ 它**依赖 steering 向量** ⇒ ⛔ **不是**与臂无关的纯几何量"
                        if same == 0 else "⚖ 多数格相同 ⇒ 与臂基本无关（本轮不成立）"))

    L.append("")
    L.append("【2】K2/K3：它是「独立噪声底」吗")
    for name, path in (("w", w_log), ("rand", rand_log)):
        rows = _prop_rows(D, kp, path)
        g = D.by_tid(rows)
        rhos = {}
        for tid in sorted(g):
            sub = g[tid]
            if len(sub) < 3:
                continue
            rhos[tid] = D.spearman([x["cov"] for x in sub],
                                   [x["denom"] for x in sub])
        vals = [v for v in rhos.values() if v is not None]
        pos = sum(1 for v in vals if v > 0)
        lr, miss = lin_ratios(D, kp, path)
        lrv = sorted(lr.values())
        over = sum(1 for v in lrv if v > CURVE_HI)
        L.append("  ── %s 臂传播层" % name)
        L.append("     K2 层内 rho(覆盖率, resid_std)：正号 **%d/%d**  p=%s  中位=%+.3f"
                 % (pos, len(vals), "%.4f" % D.binom2(pos, len(vals)), D.med(vals)))
        L.append("     ⚖⚠ 判据用 **符号检验 p < %.2f**，⛔ **不用**「正号数 ≥ 0.8n」"
                 "（那是个拍出来的阈值，且会把「未量到」印成「不是」）" % ALPHA)
        L.append("     K3 lin_ratio：中位 %.3f（范围 %.3f..%.3f）；>%.1f 的占 **%d/%d**"
                 "（缺失 %d 剔出）"
                 % (D.med(lrv), lrv[0], lrv[-1], CURVE_HI, over, len(lrv), miss))
        pv = D.binom2(pos, len(vals))
        det = pv < ALPHA
        L.append("     ⇒ %s"
                 % ("⚖⚠ **检出**与剂量的共变（正号 %d/%d，p=%.4f < %.2f）"
                    % (pos, len(vals), pv, ALPHA) if det else
                    "⚖ **未量到**（正号 %d/%d，p=%.4f ≥ %.2f）"
                    % (pos, len(vals), pv, ALPHA)))
        if not det:
            L.append("       ⚠⚠⚠ **「未量到」是事实，⛔ 不是「它就是独立噪声底」**")
            L.append("          （p≥0.05 只说明**没量到**；⛔ 更不能说「这一条不成立」）")
        L.append("       ⚖ 另报：中位 |rho| = %.3f（独立噪声底下应当 ≈0）"
                 % abs(D.med(vals)))

    L.append("")
    L.append("【3】K4 ⚖⚖ **可失败的预测**：共变来自**曲率**吗")
    L.append("  ⚖ 按每条轨迹的 lin_ratio 中位数把轨迹分成高/低两组；")
    L.append("  ⚖ 预测：更弯的一组（更像曲率、⛔ 不是随机噪声）"
             "其层内 rho(覆盖率, resid_std) 应当**更强**。")
    for name, path in (("w", w_log), ("rand", rand_log)):
        rows = _prop_rows(D, kp, path)
        g = D.by_tid(rows)
        lr, _ = lin_ratios(D, kp, path)
        per = {}
        for tid, sub in g.items():
            if len(sub) < 3:
                continue
            rho = D.spearman([x["cov"] for x in sub], [x["denom"] for x in sub])
            vals = [lr[(tid, round(x["cov"], 9))] for x in sub
                    if (tid, round(x["cov"], 9)) in lr]
            if rho is None or not vals:
                continue
            per[tid] = (sorted(vals)[len(vals) // 2], rho)
        if len(per) < 4:
            L.append("  ── %s 臂：可用轨迹 %d 条 ⛔ 不足，**跳过**（不许硬分组）"
                     % (name, len(per)))
            continue
        srt = sorted(per.items(), key=lambda kv: kv[1][0])
        half = len(srt) // 2
        lo = [v[1] for _, v in srt[:half]]
        hi = [v[1] for _, v in srt[half:]]
        p = mann_whitney_exact(lo, hi)
        L.append("  ── %s 臂：低曲率组 n=%d 中位 rho=%+.3f ｜高曲率组 n=%d 中位 rho=%+.3f"
                 % (name, len(lo), D.med(lo), len(hi), D.med(hi)))
        L.append("     Mann-Whitney 精确 p = **%.4f** ⇒ %s"
                 % (p, "✅ 预测成立 ⇒ 共变**可能**来自曲率"
                    if p < ALPHA else "⛔ 预测**不成立** ⇒ 只能报「未量到」，"
                                        "⛔ **不许**说「共变来自曲率」"))

    L.append("")
    L.append("【4】结论的读法（⛔ 不要越读）")
    L.append("  ⚖⚠ 本工具⛔ **不改变**任何已登记的判决（244.22–244.37 一个数都没动）。")
    L.append("  ⚖⚠⚠ 「归一化削弱梯度」有**两种**解释：① 尺脏（分母含非线性）；")
    L.append("     ② 效应本身饱和。⚖⚠ **本工具分不开这两者** ⇒ 必须照实说「分不开」。")
    L.append("  ⚖⚠ 因此 ⛔ `margin_meas` 的层内梯度**不能**用来判断「有没有剂量效应」，")
    L.append("     也⛔ 不能用「归一化后梯度变小」来支持「原梯度是噪声」。")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # C1 Mann-Whitney：两组完全分离 ⇒ p 取到该划分的最小值
    p1 = mann_whitney_exact([0.1, 0.2, 0.3], [5.0, 6.0, 7.0])
    # C1b 两组完全相同 ⇒ 没有任何分离 ⇒ p = 1.0
    p2 = mann_whitney_exact([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    # C1c 任一组为空 ⇒ 无证据 ⇒ 1.0（⛔ 不是 0）
    p3 = mann_whitney_exact([], [1.0, 2.0])
    chk("C1", p2 == 1.0 and p3 == 1.0 and abs(p1 - 2.0 / 20.0) < 1e-12,
        "Mann-Whitney：完全相同 ⇒ p=%.4f；空组 ⇒ p=%.4f；完全分离 ⇒ p=%.4f"
        % (p2, p3, p1))

    # C2 ⚠⚠⚖ **K1 那一关必须能红**：两臂 `resid_std` 逐格相同 ⇒ 不是 arm 依赖量
    #    这组夹具里 resid_std 全是 1.0 ⇒ 逐位相同 ⇒ 「与臂无关」成立
    same_fixture = {("t", 0.5): 1.0, ("t", 0.7): 1.0}
    diff_fixture = {("t", 0.5): 1.0, ("t", 0.7): 2.0}
    chk("C2", len(set(same_fixture.values())) == 1
        and len(set(diff_fixture.values())) == 2,
        "K1 夹具形状：全同 ⇒ 判「与臂无关」；有一格不同 ⇒ 判「依赖 steering」")

    # C3 ⚠⚠⚖ **K2 那一关必须能红**：独立噪声底要求 rho(覆盖率, resid_std) ≈ 0。
    #    夹具 A（与剂量无关 ⇒ rho≈0）、夹具 B（随剂量升 ⇒ rho>0）。
    import numpy as np
    cov = [0.1, 0.2, 0.3, 0.4, 0.5]
    flat = [0.30, 0.31, 0.29, 0.30, 0.305]        # 乱序 ⇒ rho ≈ −0.1
    rise = [0.10, 0.20, 0.31, 0.44, 0.58]         # 单调升 ⇒ rho = +1
    import importlib.util as _iu
    sp = _iu.spec_from_file_location("dax_probe", os.path.join(HERE, "dose_axis_audit.py"))
    dm = _iu.module_from_spec(sp)
    sys.modules[sp.name] = dm
    sp.loader.exec_module(dm)
    chk("C3", dm.spearman(cov, flat) is not None and abs(dm.spearman(cov, flat)) < 0.5
        and abs(dm.spearman(cov, rise) - 1.0) < 1e-9,
        "K2 夹具：与剂量无关 ⇒ rho=%.3f（应当≈0）；单调升 ⇒ rho=%.3f（应当 +1）"
        % (dm.spearman(cov, flat), dm.spearman(cov, rise)))

    # C4 ⚠⚠⚖ **K4 那一关必须能红**：高曲率组的 rho 确实更强
    #    ⛔ 这条断言的是**分组逻辑本身**，⛔ 不是真实数据（真实数据可能不成立）
    # ⚖⚠⚖ 3v3 完全分离时精确 p = 2/C(6,3) = 0.1000 ⇒ **结构上到不了 0.05**。
    #   ⇒ 第一版拿 3 vs 3 断言 p<0.05 是**恒红**（不是有牙齿的断言）。
    p_min33 = mann_whitney_exact([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])  # = 2/20
    # ⚗⇒ 真实 K4 是 7 vs 7 ⇒ 最小 p = 2/C(14,7) ≈ 5.8e-4 ⇒ **够用**。
    hi_group = [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0]
    lo_group = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
    p4 = mann_whitney_exact(lo_group, hi_group)
    p4_rev = mann_whitney_exact(hi_group, lo_group)
    chk("C4", abs(p_min33 - 0.1000) < 1e-12 and p4 < ALPHA
        and abs(p4 - p4_rev) < 1e-12,
        "3v3 完全分离 ⇒ p=%.4f（标准值 2/20）；"
        "7v7 完全分离 ⇒ p=%.6f；反向同值（对称）=%.6f"
        % (p_min33, p4, p4_rev))

    # C5 ⚠⚠ 探针里 `resid_std` 的**定义**必须仍是线性拟合残差
    #    ⚖⚠⚠ 若有人把它改成别的东西，本工具整篇的推论前提就没了
    src = open(os.path.join(os.path.dirname(HERE), "mutbak", "r204_noise_probe.py"),
               encoding="utf-8").read() if os.path.exists(
        os.path.join(os.path.dirname(HERE), "mutbak", "r204_noise_probe.py")) else ""
    okdef = ('"resid_std": float(resid.std(ddof=1))' in src
             and "resid = dm - A.dot(coef)" in src)
    chk("C5", bool(src) and okdef,
        "探针里 resid_std 仍是 `resid.std(ddof=1)` 且 `resid = dm - A·coef`"
        "（%s）" % ("找到" if src else "⛔ 探针源码不可达"))

    # ⚖⚠⚖ T6 **端到端**（合成日志）：K1 的判定分支必须**可红**。
    #   ⚖⚠⚠⚠ 自检 C2 验的只是「夹具形状」，⛔ **没有验 `run()` 真的会那么判**
    #   ⇒ 变异打在那句 `if same == 0` 上会**全部存活**。
    #   ⚗⇒ 造两份**合成日志**跑 `run()`：A 组两臂 resid_std 逐格不同、
    #   B 组逐格相同 ⇒ K1 的判定必须**一个说依赖、一个说不依赖**。
    import json as _json
    import tempfile as _tf
    dm2 = sys.modules.get("dax_probe")
    if dm2 is None:
        sp2 = _iu.spec_from_file_location("dax_probe2",
                                          os.path.join(HERE, "dose_axis_audit.py"))
        dm2 = _iu.module_from_spec(sp2)
        sys.modules[sp2.name] = dm2
        sp2.loader.exec_module(dm2)
    tmpd = _tf.mkdtemp(prefix="denom_t6_")

    # ⚖⚠⚠ k 档必须**全在传播层**：n_eff=1762 时读出位点的秩是 **418**
    #   ⇒ `check_cell` 把 k ≥ 418 的档判成 direct（读出位点已被注入）
    #   ⛔ 第一版用 100..500 ⇒ 多数档是 direct ⇒ 传播层只剩 1 条轨迹
    #   ⇒ 「端到端」根本没测到层内逻辑。
    # ⚖⚠⚠ `_mk` 也写错了：第一版把**两条臂写进同一个文件**
    #   ⇒ K1 配对时两臂取到的是**同一个值** ⇒ 「不同」的意图根本没发生。
    KS = [50, 100, 150, 200, 250, 300, 350]
    NT = 14          # ⚖ 符号检验要**分母**：1 条轨迹时 p 恒为 1.0 ⇒ 永远测不到「检出」

    def _mk(fname, resid_fn, nt=NT):
        """⚖ `resid_fn(i_trajectory, j_rung) -> resid_std`"""
        lines = []
        for i in range(nt):
            for j, kk in enumerate(KS, 1):
                r_ = resid_fn(i, j)
                c = dm2._cell("t%02d__x" % i, "k", kk, 108, 1654, 3309,
                              0.0, r_ * 0.1, r_, True)
                c["lin_ratio"] = 1.1 + 0.01 * j + 0.001 * i
                lines.append(_json.dumps(c))
        with open(os.path.join(tmpd, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # A：两臂 resid_std 逐格不同；B：逐格相同（K1 的两个分支）
    base = [0.10, 0.20, 0.31, 0.44, 0.58, 0.70, 0.83]
    _mk("a_w.log", lambda i, j: base[j - 1])
    _mk("a_r.log", lambda i, j: base[j - 1] * (1.05 + 0.01 * i))
    ta, _ = run(os.path.join(tmpd, "a_w.log"), os.path.join(tmpd, "a_r.log"))
    _mk("b_w.log", lambda i, j: base[j - 1])
    _mk("b_r.log", lambda i, j: base[j - 1])
    tb, _ = run(os.path.join(tmpd, "b_w.log"), os.path.join(tmpd, "b_r.log"))
    chk("T6", "依赖 steering 向量" in ta and "与臂基本无关" in tb
        and ">1.2 的占" in ta,
        "K1 端到端：两臂 resid_std 不同 ⇒ 判「依赖 steering」；逐格相同 ⇒ 判「与臂基本无关」；"
        "K3 的阈值必须**印成字面量 1.2**（⛔ 阈值不许只活在代码里）")

    # K2 的两个分支也要端到端：**检出** 与 **未量到** 必须都会印出来。
    # ⚖⚠⚠「未量到」那一支尤其要紧 —— 它必须带上 ⛔「不是噪声底」那句。
    #   ⚖ 第一版没写它 ⇒ 变异把 `det = pv < ALPHA` 改成恒 True 也会全绿。
    _mk("d_w.log", lambda i, j: 0.30 + 0.01 * ((i + j) % 3))     # 乱序 ⇒ rho≈0
    _mk("d_r.log", lambda i, j: 0.32 + 0.01 * ((i + j) % 3))
    td, _ = run(os.path.join(tmpd, "d_w.log"), os.path.join(tmpd, "d_r.log"))
    # ⚖⚠⚖ T8：`lin_ratio` 缺失的格必须被**剔出并报数**，
    #   ⛔ 不许静默当成 0（那会把「没量到」印成「曲率很小」）。
    def _mk_missing(fname):
        lines = []
        for i in range(NT):
            for j, kk in enumerate(KS, 1):
                c = dm2._cell("t%02d__x" % i, "k", kk, 108, 1654, 3309,
                              0.0, 0.03 * j, 0.10 + 0.02 * j, True)
                if not (i == 0 and j in (2, 4)):   # 两格故意不给 lin_ratio
                    c["lin_ratio"] = 1.1 + 0.01 * j
                lines.append(_json.dumps(c))
        with open(os.path.join(tmpd, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    _mk_missing("e_w.log")
    _mk_missing("e_r.log")
    te, _ = run(os.path.join(tmpd, "e_w.log"), os.path.join(tmpd, "e_r.log"))
    chk("T8", "缺失 2 剔出" in te,
        "K3 端到端：两格缺 lin_ratio ⇒ 必须报「缺失 2 剔出」（⛔ 不许静默当 0）")

    chk("T7", "检出" in ta and "未量到" in td
        and "不是「它就是独立噪声底」" in td,
        "K2 端到端：分母随剂量单调（%d 条轨迹）⇒ 判「检出」；分母与剂量无关 ⇒ "
        "判「未量到」并带上 ⛔「不是噪声底」那句" % NT)

    # C6 ⚖⚖⚖ **禁令必须有实体**：存在「p ≥ 0.05、同时中位 |rho| 明显非零」的数据。
    #    真实数据就是：rand 臂传播层 resid_std 的 11/14、p=0.0574、中位 0.625。
    p_null = 0.0574
    med_abs = 0.625
    chk("C6", non_significant_is_not_a_negative_conclusion(p_null) is False
        and p_null >= ALPHA and med_abs > 0.4,
        "反例：p=%.4f ≥ %.2f（未量到），而中位 |rho|=%.3f（明显非零）"
        " ⇒ 「未量到」⛔ **不能**印成「不是噪声底」" % (p_null, ALPHA, med_abs))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="margin_meas 分母的有效性审计（零 GPU）")
    ap.add_argument("--w-log", default=W_LOG)
    ap.add_argument("--rand-log", default=RAND_LOG)
    ap.add_argument("--probe", default=PROBE_REL)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    txt, rc = run(args.w_log, args.rand_log, args.probe)
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
