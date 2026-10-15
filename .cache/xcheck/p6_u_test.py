#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 主判决仪器：Mann–Whitney U（双侧，α=0.05）+ 效应量 + 功效披露。

预登记 §P6 原文要求四样，本脚本四样都出：

    1. Mann–Whitney U，双侧，α = 0.05
    2. 两组中位数与 **Hodges–Lehmann** 估计量
    3. 效应量 **Cliff's delta**
    4. ⚠ 若 correct 组轨迹数 < 10，判决一律记「样本不足，不构成结论」

⚠⚠⚴ 本脚本**只做算术，不产生读数**。读数必须来自 `r6_rerun.py` 的全量产物，
⚠⚠⚴ 而那份产物的 `device_validated` 必须为 `true` ——
⚠⚠⚴ 若为 `false`（P9 装置闸没过），本脚本**拒绝出判决**，退出码 4。
⚗⚠⚠ 这是修订 195 那条「闸不接到出口 = 死开关」的延续：
⚗⚠⚠ 仪器自己那一层的门也必须关。

⚠⚠⚴ **功效披露不是可选项**。`p6_readiness.py` 明写：
⚗ 「P6 没给 wrong 设底线，但 n=17 做 U 检验功效极低 ——
⚗  这一格必须在报告里显式披露，不许只报 correct 够格。」
⚗⇒ 本脚本在 wrong 组 < 20 时**强制打印**功效警告，并给出最小可检测位移。

⚠ 统计口径：
    U 用**并列修正**的正态近似（双侧 + 连续性校正）；
    无并列且样本小时同时给**精确检验**（Fisher/MW exact）。
⚠ 有 scipy 时**双实现交叉验证**（本实现 vs scipy.stats.mannwhitneyu），
⚠ 无 scipy 时自动降级为纯 stdlib（远端 easysteer 环境无 scipy）。

用法：
    python3 p6_u_test.py --rows r6_rows.json            # 吃 r6_rerun 全量产物
    python3 p6_u_test.py --a 1 2 3 --b 4 5 6            # 直接给两组数（自检用）

退出码：0 出判决 / 4 拒绝或样本不足 / 2 用法错 / 3 输入自相矛盾
"""

import argparse
import json
import sys
from itertools import combinations
from math import comb, sqrt
from pathlib import Path

ALPHA = 0.05
P6_CORRECT_FLOOR = 10
# ⚠ 功效警示线：wrong 组低于这个数，U 检验功效必然不足（经验值，非推导）
POWER_WARN_N = 20
# ⚠ 精确检验的枚举上限：C(n1+n2, n1) 超过这个数就不枚举（纯 Python 会跑几分钟）
EXACT_MAX_COMB = 2_000_000


def mannwhitney_u(a, b):
    """返回 U_a（a 样本被判大于 b 的配对数），含并列平均秩。"""
    vals = list(a) + list(b)
    n1, n2 = len(a), len(b)
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j + 2) / 2.0          # 1-based 秩的平均
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    r1 = sum(ranks[:n1])
    return r1 - n1 * (n1 + 1) / 2.0


def _tie_groups(vals):
    from collections import Counter
    c = Counter(vals)
    return [v for v, k in c.items() if k > 1]


def u_pvalue_normal(u, n1, n2, vals_all):
    """并列修正 + 连续性校正的双侧正态近似。"""
    n = n1 + n2
    mu = n1 * n2 / 2.0
    nties = _tie_groups(vals_all)
    var = n1 * n2 / 12.0 * ((n + 1) - sum(k ** 3 - k for k in
                                           (sum(1 for v in vals_all if v == t)
                                            for t in nties)) / (n * (n - 1.0)))
    if var <= 0:
        return float("nan")
    z = (abs(u - mu) - 0.5) / sqrt(var)     # 连续性校正
    if z < 0:
        z = 0.0
    # 双侧 p = 2 * (1 - Phi(z))，用 erf 避免依赖 scipy
    import math
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / sqrt(2.0))))


def u_pvalue_exact(u, n1, n2):
    """**双侧**精确 p：所有「不比实测更可能」的结果的概率之和（scipy / R 的定义）。

    ⚠⚠⚴ 修订 202，这件事前后错了**两版**，每版各被一条自检抓到：
    ⚠⚠⚴ v1（原始）：只数单尾 ⇒ 系统性差一个 2 倍。
    ⚠⚠⚴ v2：双侧 = min(1, 2×单尾)。⚠ 这在**完全分离**时**恰好**等于正确值
    ⚠⚠⚴      （两端各 1 个结果，总 2/252），所以自检 T2f「必须等于 2/252」
    ⚠⚠⚴      是**碰巧**绿的 —— 它没有分辨力，抓不住这个 bug。
    ⚠⚠⚴      真正抓到它的是 T3b：n1=n2=4、U=7 时 2×单尾=0.200，
    ⚠⚠⚴      正确值 = 62/70 = 0.886。离散分布下 2×单尾**偏激进**。
    ⚠⚠⚴ v3（本版）：逐点求和，口径 = |U−μ| ≥ |u_obs−μ|。
    ⚠ 本路径只在**无并列**时调用（并列时 U 可为半整数，逐点口径会歧义）。
    """
    n = n1 + n2
    total = comb(n, n1)
    if total > EXACT_MAX_COMB:
        return float("nan")
    mu = n1 * n2 / 2.0
    dev = abs(u - mu)
    cnt = 0
    for idx in combinations(range(1, n + 1), n1):
        s = sum(idx) - n1 * (n1 + 1) // 2
        if abs(s - mu) >= dev - 1e-9:
            cnt += 1
    return cnt / float(total)


def hodges_lehmann(a, b):
    """两样本位置差的 HL 估计量 = 全部 (a_i - b_j) 的中位数。"""
    diffs = sorted(x - y for x in a for y in b)
    n = len(diffs)
    if n == 0:
        return float("nan")
    m = n // 2
    return diffs[m] if n % 2 else (diffs[m - 1] + diffs[m]) / 2.0


def cliffs_delta(a, b):
    """δ = (#(a>b) - #(a<b)) / (n1*n2)。直接数，不经 U 推。"""
    n1, n2 = len(a), len(b)
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / float(n1 * n2)


def median(v):
    s = sorted(v)
    n = len(s)
    if n == 0:
        return float("nan")
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def min_detectable_shift(n1, n2, alpha=ALPHA, power=0.80):
    """粗略的最小可检测位移（正态近似，按两组方差不等的保守公式）。
    ⚠ 这是**量级估计**，不是功效分析的替代品；只用来提醒读者量级。"""
    # 正态分位数（避免依赖 scipy）：二分求 Phi(z)=p
    import math

    def zq(p):
        # 二分求 Phi(z)=p
        lo, hi = -8.0, 8.0
        for _ in range(200):
            mid = (lo + hi) / 2.0
            val = 0.5 * (1.0 + __import__("math").erf(mid / __import__("math").sqrt(2.0)))
            if val < p:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0
    za, zb = zq(1 - alpha / 2.0), zq(power)
    return (za + zb) * sqrt(1.0 / n1 + 1.0 / n2)


def cross_check(a, b, p_norm):
    """有 scipy 就双实现交叉验证；没有就明说没验。"""
    try:
        from scipy.stats import mannwhitneyu
        r = mannwhitneyu(a, b, alternative="two-sided", method="auto")
        return ("scipy U=%.4f p=%.6g" % (r.statistic, r.pvalue),
                abs(r.pvalue - p_norm) < 5e-4 or abs(r.pvalue / max(p_norm, 1e-12) - 1) < 0.02)
    except Exception as e:                        # noqa: BLE001
        return ("⚠ 无 scipy，未交叉验证（%s）" % type(e).__name__, None)


def report(a, b, label_a="correct", label_b="wrong", cross=True):
    n1, n2 = len(a), len(b)
    print("=== P6 主判决：Mann–Whitney U（双侧，α=%.2f）===" % ALPHA)
    print("  %s 组 n=%d  中位数 %+.4f" % (label_a, n1, median(a)))
    print("  %s 组 n=%d  中位数 %+.4f" % (label_b, n2, median(b)))
    if n1 == 0 or n2 == 0:
        print("\n⛔ 有一组为空 —— 无从判决。")
        return 4
    u = mannwhitney_u(a, b)
    allv = list(a) + list(b)
    p = u_pvalue_normal(u, n1, n2, allv)
    print("  U = %.4f   (期望 %.2f)" % (u, n1 * n2 / 2.0))
    if p != p:                      # nan
        print("  p(双侧, 并列修正正态近似) = 无法计算（方差为 0 ⇒ 全部观测值并列）")
        print("  ⚠ 无任何秩信息，本次不构成判决。")
    else:
        print("  p(双侧, 并列修正正态近似) = %.6f" % p)
    if not _tie_groups(allv):
        ncomb = comb(n1 + n2, n1)
        if ncomb <= EXACT_MAX_COMB:
            print("  p(双侧, 精确, 无并列)   = %.6f" % u_pvalue_exact(u, n1, n2))
        else:
            print("  p(双侧, 精确, 无并列)   = 跳过：C(%d,%d)=%d 枚举量超上限 %d"
                  % (n1 + n2, n1, ncomb, EXACT_MAX_COMB))
    hl = hodges_lehmann(a, b)
    cd = cliffs_delta(a, b)
    print("  Hodges–Lehmann 位置差估计 = %+.4f" % hl)
    print("  Cliff's delta             = %+.4f" % cd)
    if cross and p == p:
        msg, ok = cross_check(a, b, p)
        print("  交叉验证：%s%s" % (msg, "" if ok is None else ("  ✅ 一致" if ok else "  ⚠⚠ 不一致")))

    sig = (p == p) and (p < ALPHA)
    print()
    if p != p:
        print("  判决：⛔ **无法判决**（p 不可计算，见上）")
    else:
        print("  判决：%s" % ("**两组分布有显著差异（p<%.2f）**" % ALPHA if sig
                            else "**未达显著（p≥%.2f）**" % ALPHA))

    # ---- 功效披露（强制）----
    print()
    print("  ⚠⚠⚠ **功效披露（P6 原文要求，不许略）**")
    small = [n for n, nm in ((n1, label_a), (n2, label_b)) if n < POWER_WARN_N]
    if small:
        mde = min_detectable_shift(n1, n2)
        print("  ⚠ %s 组 n < %d ⇒ U 检验**功效极低**"
              % (" / ".join("%s(%d)" % (nm, n) for nm, n in
                            zip((label_a, label_b), (n1, n2)) if n < POWER_WARN_N),
                 POWER_WARN_N))
        print("  ⚠ 粗略最小可检测位移（80%% 功效）≈ ±%.4f" % mde)
        print("  ⚗⇒ **「未达显著」几乎不可能是「无差异」的证据** ——")
        print("     在这个样本量下，无差异与微小差异**同样**会给 p≥α。")
    if n1 < P6_CORRECT_FLOOR:
        print("  ⛔ correct 组 n=%d < %d ⇒ 按 P6 原文记「**样本不足，不构成结论**」"
              % (n1, P6_CORRECT_FLOOR))
        print("     ⛔ 不得因 p 小就报显著，⛔ 也不得因 p 大就报「无差异」。")
        return 4
    print("  RESULT p6_u_test  %s  U=%.4f p=%.6g HL=%+.4f cliff=%+.4f"
          % ("SIG" if sig else "NS", u, p, hl, cd))
    return 0


def aggregate_by_traj(rows, field):
    """按 §P6 原文「**对每条轨迹先算一个数**：它在抽到的位置上的均值」聚合。

    ⚠⚠⚴ 修订 202 ⛔ 这是本文件最严重的一处违约，且**打印里写着做了、代码里没做**：
    ⚠⚠⚴ `r6_rerun.py` 的 rows 是**按位置**记的（`MAX_POS_PER_TRAJ = 6`，
    ⚠⚠⚴ 一条轨迹可出最多 6 行）。原实现 `groups[lab].append(v)` 逐行收，
    ⚠⚠⚴ 于是 n = 行数 = 轨迹数 × 每轨迹位置数，**最多虚高 6 倍**，
    ⚠⚠⚴ 而 U 检验据此算的 p 值会假得离谱（样本量越大越显著）。
    ⚠⚠⚴ 预登记 §P6 原文两处都写的是**轨迹数**：
    ⚠⚠⚴   「对每条轨迹先算一个数：……Δlogit(marker 集合) 的**均值**」
    ⚠⚠⚴   「若 correct 组**轨迹数** < 10」
    ⚠⚠⚴ ⇒ 正确实现必须先按 traj 取均值，n = 轨迹数。

    返回 (per_traj, n_rows_used, n_rows_missing_traj)
    其中 per_traj: {traj_id: (label, 该轨迹各位置的均值)}
    """
    per_traj = {}
    n_used = 0
    n_no_traj = 0
    for i, r in enumerate(rows):
        lab = r.get("label")
        v = r.get(field)
        if lab not in ("correct", "wrong") or v is None:
            continue
        tid = r.get("traj")
        if tid is None:
            # ⛔ 不能悄悄当成一条新轨迹 —— 那正好把伪重复装回来。
            n_no_traj += 1
            tid = "@norow#%d" % i
        n_used += 1
        e = per_traj.setdefault(tid, [lab, []])
        e[1].append(float(v))
    out = {k: (v[0], sum(v[1]) / len(v[1])) for k, v in per_traj.items()}
    return out, n_used, n_no_traj


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--rows", default=None,
                    help="r6_rerun.py 的全量产物 json（含 rows 与 device_validated）")
    ap.add_argument("--a", type=float, nargs="+", default=None, help="第一组数值")
    ap.add_argument("--b", type=float, nargs="+", default=None, help="第二组数值")
    ap.add_argument("--field", default=None,
                    help="从 rows 取哪个字段做 Δlogit（默认 mark_w+_1.0）")
    ap.add_argument("--by-position", action="store_true",
                    help="⛔ 诊断用：把每个**位置**当独立观测（伪重复）。"
                         "本档位**不出判决**，恒 EXIT 4。")
    ap.add_argument("--no-cross", action="store_true", help="不做 scipy 交叉验证")
    a = ap.parse_args()

    if a.rows:
        d = json.load(open(a.rows, encoding="utf-8"))
        dv = d.get("device_validated")
        if dv is False:
            print("⛔⛔ **P9 装置闸未过（device_validated=false）**")
            print("   那批读数来自**未验证的装置**，本脚本**拒绝出判决**。")
            print("   ⚠ 这是修订 195 接进出口的那道闸：不接的话这批行会静默流进 U 检验。")
            print("RESULT p6_u_test  BLOCKED  device_validated=false")
            return 4
        if dv is None:
            print("⛔ 产物里没有 device_validated 字段 —— 无法确认装置已验证。")
            print("   ⛔ **缺字段 ≠ 通过**。请先用带该字段的 r6_rerun 重新出产物。")
            return 4
        rows = d.get("rows") or []
        field = a.field or "mark_w+_1.0"

        if a.by_position:
            # 诊断档：明说这是伪重复，且不许出判决。
            g = {"correct": [], "wrong": []}
            for r in rows:
                if r.get("label") in g and r.get(field) is not None:
                    g[r["label"]].append(float(r[field]))
            print("⛔⛔ `--by-position` 是**伪重复口径**：同一条轨迹的多个位置被当成独立观测。")
            print("   MAX_POS_PER_TRAJ = 6 ⇒ n 最多虚高 6 倍，p 值随之假得离谱。")
            print("   下列数字**只作诊断分布用，不构成 §P6 判决**，本档位恒不给出判决。")
            print("   correct n=%d  wrong n=%d  correct 中位数 %+.4f  wrong 中位数 %+.4f"
                  % (len(g["correct"]), len(g["wrong"]),
                     median(g["correct"]) if g["correct"] else float("nan"),
                     median(g["wrong"]) if g["wrong"] else float("nan")))
            print("RESULT p6_u_test  DIAGNOSTIC-ONLY  by_position（无判决）")
            return 4

        per_traj, n_used, n_no_traj = aggregate_by_traj(rows, field)
        n_traj = len(per_traj)
        print("  取数口径（§P6 原文）：字段 `%s`，**先对每条轨迹的各位置取均值**，"
              % field)
        print("                    再拿这些**轨迹级**的数去做 U 检验。")
        print("  ⚠ 行 %d → 轨迹 %d（平均每条 %.2f 个位置）。"
              % (n_used, n_traj, (n_used / n_traj) if n_traj else float("nan")))
        if n_no_traj:
            print("  ⛔ 有 %d 行**没有 traj 字段**，无法归到轨迹上 —— 已按行单独编号。"
                  % n_no_traj)
            print("     ⛔ 这会让「轨迹数」虚高，§P6 的 n<10 底线随之失效 ⇒ 拒绝出判决。")
            print("RESULT p6_u_test  BLOCKED  rows 缺 traj 字段")
            return 4
        if n_traj == 0:
            print("[错误] 产物里没有 usable 的 correct/wrong 读数（字段 %s）" % field)
            return 3
        groups = {"correct": [], "wrong": []}
        for lab, val in per_traj.values():
            groups[lab].append(val)
        return report(groups["correct"], groups["wrong"],
                      cross=not a.no_cross)

    if a.a and a.b:
        return report(a.a, a.b, cross=not a.no_cross)

    print("[错误] 要么给 --rows，要么给 --a 与 --b")
    return 2


if __name__ == "__main__":
    sys.exit(main())
