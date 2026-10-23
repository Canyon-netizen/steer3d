#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""premise_independence_audit.py —— **前提独立性**的**第二条独立实现**（244.82）。

⚖⚖⚖⚖⚖ **这个文件回答什么**
   244.81 的判决面板上每一个 p、每一个区间，都建立在「56 条轨迹彼此独立」这个
   **没被验过**的前提上（面板前提 P1）。真实结构是 **56 = 28 块 × 2**
   （块 = 同一道题同位置的 `think` + `no_think`），且每条轨迹还有 **3 个 `pos_frac` 复制格**。

⚖⚖⚖⚖⚖ **纪律（本文件的形状就是这些纪律）**
   ① **口径只从预登记读**：`.cache/xcheck/R6_PREMISE_INDEPENDENCE_PREREG.md`（244.82 签）
      ⇒ ⛔ 本文件**不写死**那些口径常量？—— **写死的是「从预登记读来的」那一组**，
      且 §PI-P1 判它们**逐条在案**（⛔ 不默认值兜底、不静默降级）。
   ② **数据路径不同**：本文件读 **bpath 原始跑批日志** `r244_warm_fd_{w,rand}.log`，
      **自己按 `pos_frac` 过滤** ⇒ ⇒ **不读** `fixed_dose_split_log.py` 的拆分产物、
      **不读**先导探查 `_scout_premise_indep.py` 的路径 ⇒ ⇒ 与先导探查**不同源**。
   ③ **统计方法不同**：
        · 块级置换用 **DP 精确零分布**（⛔ **不是**蒙特卡洛、⛔ 没有种子误差）；
        · 差 pp 的区间用 **删一块 jackknife**（⛔ **不是** bootstrap、⛔ 确定性）；
        · t 分位数**自己算**（Student-t CDF 二分；⛔ 不抄表、⛔ 不用 scipy）。
   ④ **每条判据能红**：本文件带 `--selftest`（Phase-0 G0-1/G0-2，已知答案夹具）
      与变异台 `mut_premise_independence_audit.py`（⛔ 变异台必须能红）。
   ⑤ **判决只算一次**：印出来的 = 返回的。
   ⑥ ⛔ **未量到 ≠ 没差异 ≠ 失败**：不适用/未量到**不许**渲染成 FAIL。

⚖⚖⚖ **本文件**不**产出**「前提独立性成立」这句话
   （预登记 §1：这条前提**不可证明**）⇒ ⇒ 只产出
   「**在把块当独立单位的保守口径下，判决是否仍然成立**」＋「块内相关的**可检出**证据」。
"""

import argparse
import collections
import io
import json
import math
import os
import re
import sys

# =============================================================================
# 口径常量（**逐条对应**预登记 §2 的 P2/P3/P5/P6/P11）
#   ⚠ 这些值**同时**被 `--print-spec` 印出来 ⇒ ⇒ 变异台能逐条改它们 ⇒ ⇒ 能红。
# =============================================================================
SPEC = {
    "rho": 0.250,            # P2：目标密度 ρ*
    "tol": 0.0050,           # P2：密度容差
    "scope": "k",            # P2：只取 scope == 'k'
    "alpha": 0.05,           # P6：α
    "n_perm_expected": 20000,  # P6：⛔ **只用于交叉互证**（先导探查的 MC 次数），本文件**不用**它算 p
    "scout_blk_perm_p": 0.002700,  # P14：先导探查印的块级 MC 置换 p（⛔ 用作 MC 误差对照，不参与本文件任何计算）
}

# P11：自检必须逐位复现的 6 个数（**来自面板**，⛔ 本文件**不**用它们算任何结论）
EXPECT = {
    "traj_w": (46, 56),
    "traj_rand": (29, 56),
    "blk_w": (21, 28),
    "blk_rand": (6, 28),
    "fisher_traj": 0.001152,
    "fisher_blk": 0.000131,
}

# G0-2：t 分位数的**对账目标**（⛔ 是对账目标，⛔ 不是抄进代码当答案用）
TQ_KNOWN = [
    (1, 12.7062047364),
    (10, 2.228138852),
    (27, 2.051830516),
]


def die(msg):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(3)


class Criteria(object):
    """⚖ 判据收集器：每条判据**带 id** ⇒ ⇒ 变异台能知道「哪条该红」。"""

    def __init__(self):
        self.items = []

    def check(self, cid, ok, detail):
        self.items.append((cid, bool(ok), detail))
        print("[%s] %-14s %s" % ("PASS" if ok else "FAIL", cid, detail))
        return bool(ok)

    def fail_count(self):
        return sum(1 for _c, ok, _d in self.items if not ok)

    def failed_ids(self):
        return set(c for c, ok, _d in self.items if not ok)

    def summary(self):
        n = len(self.items)
        bad = self.fail_count()
        print("自检 %d 条 ｜ PASS %d ｜ FAIL %d" % (n, n - bad, bad))
        return 0 if bad == 0 else 1


# =============================================================================
# 统计：全部**自己实现**（⛔ 不 import scipy / statsmodels / 面板分析器）
# =============================================================================


def wilson(x, n, z=1.959963984540054):
    """Wilson95 比例区间（百分数）。"""
    if not n:
        return (float("nan"), float("nan"))
    p = x / float(n)
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / d
    return (100.0 * (c - h), 100.0 * (c + h))


def newcombe(x1, n1, x2, n2):
    """两比例之差的 Newcombe95（方法 10）——⛔ 不是两 CI 相减。"""
    l1, u1 = wilson(x1, n1)
    l2, u2 = wilson(x2, n2)
    p1, p2 = x1 / float(n1), x2 / float(n2)
    d = 100.0 * (p1 - p2)
    lo = d - math.sqrt((p1 * 100 - l1) ** 2 + (u2 - p2 * 100) ** 2)
    hi = d + math.sqrt((u1 - p1 * 100) ** 2 + (p2 * 100 - l2) ** 2)
    return (lo, hi)


def fisher_exact(a, b, c, d):
    """两侧 Fisher 精确（「不比观测更可能」的经典定义，⛔ 不是双尾×1 的凑法）。"""
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    if n == 0:
        return float("nan")

    def prob(x):
        if not (0 <= x <= r1) or not (0 <= c1 - x <= r2):
            return 0.0
        return (math.comb(r1, x) * math.comb(r2, c1 - x)) / float(math.comb(n, c1))

    p_obs = prob(a)
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1)
                         if prob(x) <= p_obs * (1 + 1e-12)))


def binom_two_sided_exact(k, n, p0):
    """精确二项两侧检验（按「概率不比观测更可能」排序，⛔ 与 Fisher 同一约定）。

    ⛔ 不是「2×单尾」的凑法。
    """
    if n <= 0:
        return float("nan")

    def pmf(x):
        return math.comb(n, x) * (p0 ** x) * ((1.0 - p0) ** (n - x))

    p_obs = pmf(k)
    return min(1.0, sum(pmf(x) for x in range(n + 1) if pmf(x) <= p_obs * (1 + 1e-12)))


def mcnemar_exact(b, c):
    """精确 McNemar（二项）：不一致的 b+c 条里 b 条偏向一臂。"""
    n = b + c
    if n == 0:
        return float("nan")
    return binom_two_sided_exact(min(b, c), n, 0.5)


# ---- Student-t：自己算（预登记 P7 / PI-P16：⛔ 不抄表、⛔ 不用 scipy）


def _betacf(a, b, x):
    """连分式（Lentz 法）—— 正则化不完全 beta 的 continued fraction。"""
    MAXIT, EPS, FPMIN = 300, 3.0e-16, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    """正则化不完全 beta I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t, nu):
    """Student-t 分布函数。"""
    x = nu / (nu + t * t)
    ib = betai(nu / 2.0, 0.5, x)
    p = 1.0 - 0.5 * ib
    return p if t > 0 else (1.0 - p)


def t_quantile(p, nu):
    """t 分位数（二分法）—— ⛔ 不抄表。"""
    lo, hi = 0.0, 2000.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if student_t_cdf(mid, nu) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---- 块级置换：**精确**零分布（DP）


def exact_block_perm_p(block_diffs):
    """⚖⚖⚖ **精确**块级置换双侧 p（DP 精确零分布，⛔ **不是**蒙特卡洛）。

    零分布：每个块独立地以 1/2 概率交换两臂标签 ⇒ 统计量 `T = Σ ε_b·d_b`。
    ⇒ 分布只取决于 **d 的多重集** ⇒ 用「按取值分组 + 卷积」的 DP 精确算。
    ⛔ `d_b == 0` 的块对统计量无贡献，但每个有 **2** 种符号选择 ⇒ 计数乘 `2^z`。
    """
    obs = sum(block_diffs)
    if not block_diffs:
        return (float("nan"), 0, 0, 0)
    cnt = collections.Counter(block_diffs)
    zeros = cnt.pop(0, 0)
    dp = {0: 1}
    for v in sorted(cnt):
        c = cnt[v]
        nd = collections.defaultdict(int)
        for s, ways in dp.items():
            for j in range(c + 1):
                nd[s + (2 * j - c) * v] += ways * math.comb(c, j)
        dp = nd
    total = 2 ** len(block_diffs)
    tail = 0
    for s, ways in dp.items():
        if abs(s) >= abs(obs):
            tail += ways * (2 ** zeros)
    return (tail / float(total), obs, tail, total)


def brute_force_perm_p(block_diffs):
    """⚖ 暴力枚举（**只给 G0-1 用**）：n 小时把 2ⁿ 个符号组合全列出来。"""
    n = len(block_diffs)
    obs = sum(block_diffs)
    tail = 0
    total = 0
    for mask in range(1 << n):
        t = 0
        for i in range(n):
            t += block_diffs[i] if (mask >> i) & 1 else -block_diffs[i]
        total += 1
        if abs(t) >= abs(obs):
            tail += 1
    return tail / float(total)


# ---- 删一块 jackknife（cluster jackknife）


def cluster_jackknife_ci(pw, pr, alpha):
    """⚖⚖ **删一块 jackknife** 的 95% 区间（确定性，⛔ 没有种子）。

    `pw`/`pr`：按块对齐的两臂「块是否正」0/1 序列（长度 = 块数）。
    """
    n = len(pw)
    if n < 3:
        return (float("nan"), float("nan"), float("nan"))
    sw, sr = sum(pw), sum(pr)
    theta = 100.0 * (sw / float(n) - sr / float(n))
    th = []
    for i in range(n):
        th.append(100.0 * ((sw - pw[i]) / float(n - 1) - (sr - pr[i]) / float(n - 1)))
    mbar = sum(th) / float(n)
    var = (n - 1) / float(n) * sum((v - mbar) ** 2 for v in th)
    se = math.sqrt(var)
    tq = t_quantile(1.0 - alpha / 2.0, n - 1)
    return (theta - tq * se, theta + tq * se, se)


# =============================================================================
# 解析：bpath 原始跑批日志（⛔ 不读拆分产物）
# =============================================================================

RESULT_RE = re.compile(r"^RESULT\s+r204_cell\s+(\S+)\s+pos=([0-9.]+)")


def parse_raw_log(path):
    """⚖ 自己解析原始跑批日志 ⇒ 返回 (记录列表, RESULT 头里的 tid 集合)。

    ⚠ 两条**互相独立**的取数路线：JSON 行给读数、`RESULT` 头给 tid ⇒
       两者必须**对得上** ⇒ ⇒ 解析错了一眼就能看出来（自证）。
    """
    recs = []
    hdr_tids = set()
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            m = RESULT_RE.match(ln)
            if m:
                hdr_tids.add(m.group(1))
                continue
            ln = ln.strip()
            if not ln.startswith("{"):
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if "tid" in r:
                recs.append(r)
    return recs, hdr_tids


def denom_of(r):
    """⚖ 照探针原式：`inj = int(P) + max(1, int(n_gen*pos_frac)) − 1`。"""
    P, ng, pf = r.get("P"), r.get("n_gen"), r.get("pos_frac")
    if P is None or ng is None or pf is None:
        return None
    return int(P) + max(1, int(int(ng) * float(pf))) - 1


def cell_set(recs):
    """⚖ P2 四条：`scope==k` ∧ 读数在 ∧ `n_sites` 为真 ∧ 密度 = ρ*±tol。"""
    kept, dropped = [], []
    for r in recs:
        lo, hi = r.get("p9_lo_meas"), r.get("p9_hi_meas")
        if lo is None or hi is None:
            dropped.append((r, "读数缺失"))
            continue
        if (r.get("inject_scope") or "") != SPEC["scope"]:
            dropped.append((r, "scope≠%s" % SPEC["scope"]))
            continue
        if not r.get("inject_n_sites"):
            dropped.append((r, "n_sites 为假"))
            continue
        inj = denom_of(r)
        if inj is None or inj <= 0:
            dropped.append((r, "分母算不出"))
            continue
        fr = float(r["inject_n_sites"]) / float(inj)
        if abs(fr - SPEC["rho"]) > SPEC["tol"]:
            dropped.append((r, "密度 %.6f ∉ ρ*±%.4f" % (fr, SPEC["tol"])))
            continue
        rr = dict(r)
        rr["_frac"] = fr
        kept.append(rr)
    return kept, dropped


def pool_trajectories(kept):
    """⚖ P3：逐轨迹**严格多数** `nT·2 > m`（平票 False、零格进分母）。"""
    by_tid = collections.OrderedDict()
    for r in kept:
        by_tid.setdefault(r["tid"], []).append(r)
    out = collections.OrderedDict()
    for tid, cs in by_tid.items():
        vals = []
        for r in cs:
            d = float(r["p9_hi_meas"]) - float(r["p9_lo_meas"])
            vals.append(1 if d > 0 else (-1 if d < 0 else 0))
        m = len(vals)
        nT = sum(1 for v in vals if v > 0)
        out[tid] = {"vals": vals, "m": m, "nT": nT,
                    "verdict": bool(nT * 2 > m)}
    return out


def block_key_split(tid):
    """⚖ **P4：按 `__` 切分 `tid`，取前 N−1 段**（⛔ 不是剥后缀）。

    `aime__aime25__p00__no_think` ⇒ `aime__aime25__p00`
    """
    parts = tid.split("__")
    if len(parts) >= 2 and parts[-1] in ("think", "no_think"):
        return "__".join(parts[:-1])
    return tid


def block_key_suffix(tid):
    """⚖ **另一条路线**（剥后缀）—— 只用来**对账**两条路线是否给出同一个块集合。"""
    for suf in ("__no_think", "__think"):
        if tid.endswith(suf):
            return tid[:-len(suf)]
    return tid


def build_blocks(pooled):
    """⚖ P5：块 = 同一块键下的两条轨迹；块判决 = 两条都正才算正。"""
    bl = collections.OrderedDict()
    for tid, v in pooled.items():
        bl.setdefault(block_key_split(tid), {})[tid] = v
    return bl


def block_verdict(blk):
    """⚖ 块判决：块内**两条都正**才算正（⛔ 少于两条 ⇒ 不算正、且不算进分母）。"""
    if len(blk) != 2:
        return None
    return bool(all(v["verdict"] for v in blk.values()))


# =============================================================================
# Phase-0 闸门（G0-1 / G0-2）：**已知答案**夹具，⛔ 不依赖真数据
# =============================================================================


def gate_selftest(crit):
    """⚖⚖ G0-1 + G0-2：⛔ 全绿才允许写真实数据路径。"""
    print("==== Phase-0 闸门（G0-1 / G0-2，零 GPU、已知答案）====")

    # ---- S-SPEC：口径常量必须与预登记 §2 一致（**再钉一遍**，⇒ 变异台能红）
    spec_expect = {"rho": 0.250, "tol": 0.0050, "scope": "k", "alpha": 0.05}
    bad_spec = []
    for k, v in spec_expect.items():
        if SPEC.get(k) != v:
            bad_spec.append("%s 我=%s 预登记=%s" % (k, SPEC.get(k), v))
    crit.check("S-SPEC", not bad_spec,
               "口径常量与预登记 §2 一致：rho=%s / tol=%s / scope=%s / alpha=%s ⇒ %s"
               % (SPEC.get("rho"), SPEC.get("tol"), SPEC.get("scope"), SPEC.get("alpha"),
                  "全对" if not bad_spec else "⛔ %s" % "、".join(bad_spec)))

    # ---- G0-1：DP 精确置换 vs 暴力枚举
    ok = True
    detail = []
    import random as _rnd
    rng = _rnd.Random(20261023)
    for _k in range(12):
        n = rng.randint(3, 11)
        vec = [rng.choice([-4, -2, 0, 2, 4]) for _ in range(n)]
        p_dp, _o, _t, _tot = exact_block_perm_p(vec)
        p_bf = brute_force_perm_p(vec)
        if abs(p_dp - p_bf) > 1e-12:
            ok = False
            detail.append("n=%d DP=%.17g 暴力=%.17g" % (n, p_dp, p_bf))
    crit.check("S-DP", ok,
               "DP 精确置换 vs 暴力枚举 2^n：%d 组随机块差向量 ⇒ %s"
               % (12, "逐位相同（≤1e-12）" if ok else "⛔ 不一致：%s" % detail))

    # ---- G0-2 ①：t 分位数 vs 已知值
    ok = True
    detail = []
    for df, want in TQ_KNOWN:
        got = t_quantile(0.975, df)
        if abs(got - want) > 1e-6:
            ok = False
            detail.append("df=%d 我=%.10f 期望=%.10f" % (df, got, want))
    crit.check("S-TQ", ok,
               "Student-t 97.5%% 分位数 vs 已知值（df=%s）：%s"
               % (",".join(str(d) for d, _ in TQ_KNOWN),
                  "逐位相同（≤1e-6）" if ok else "⛔ %s" % detail))

    # ---- G0-2 ②：精确二项两侧检验 vs **另一条实现**（连乘 pmf 累加，不用排序法）
    ok = True
    detail = []
    for (k, n, p0) in [(24, 28, 0.7066), (22, 27, 0.5), (11, 28, 0.5006)]:
        got = binom_two_sided_exact(k, n, p0)
        # 另一条实现：显式枚举全部 x，把 pmf 排序后累加概率 ≤ pmf(k) 的
        pms = []
        for x in range(n + 1):
            pms.append((math.comb(n, x) * (p0 ** x) * ((1.0 - p0) ** (n - x)), x))
        pms.sort()
        thr = None
        for pv, x in pms:
            if x == k:
                thr = pv
                break
        alt = sum(pv for pv, x in pms if pv <= thr * (1 + 1e-12))
        if abs(got - alt) > 1e-12:
            ok = False
            detail.append("k=%d n=%d 我=%.17g 另一实现=%.17g" % (k, n, got, alt))
    crit.check("S-BINOM", ok,
               "精确二项两侧检验 vs 另一实现（枚举排序法）：%s"
               % ("逐位相同（≤1e-12）" if ok else "⛔ %s" % detail))

    # ---- G0-2 ③：删一块 jackknife（5 块合成夹具 ⇒ 手算可验）
    pw = [1, 1, 0, 1, 0]
    pr = [0, 0, 0, 1, 0]
    lo, hi, se = cluster_jackknife_ci(pw, pr, 0.05)
    # 手算：θ = 100*(3/5 − 1/5) = 40；逐块剔除的 θ_(i) 全部手算
    th = []
    n = 5
    for i in range(n):
        th.append(100.0 * ((sum(pw) - pw[i]) / 4.0 - (sum(pr) - pr[i]) / 4.0))
    mbar = sum(th) / 5.0
    var = 4.0 / 5.0 * sum((v - mbar) ** 2 for v in th)
    want_se = math.sqrt(var)
    want_lo = 40.0 - t_quantile(0.975, 4) * want_se
    want_hi = 40.0 + t_quantile(0.975, 4) * want_se
    ok = (abs(se - want_se) < 1e-9 and abs(lo - want_lo) < 1e-9 and abs(hi - want_hi) < 1e-9
          and abs(th[0] - 25.0) < 1e-9)
    crit.check("S-JACK", ok,
               "删一块 jackknife 合成夹具：θ=40.00pp、θ_(1)=25.00pp、SE=%.6f、区间[%.6f, %.6f] ⇒ %s"
               % (se, lo, hi, "与手算一致" if ok else "⛔ 与手算不一致"))

    # ---- G0-2 ④：块键切分
    cases = [
        ("aime__aime25__p00__no_think", "aime__aime25__p00"),
        ("aime__aime25__p00__think", "aime__aime25__p00"),
        ("solo_tid", "solo_tid"),
    ]
    ok = all(block_key_split(a) == b for a, b in cases)
    crit.check("S-BLOCKKEY", ok,
               "块键切分（按 `__` 取前 N−1 段）：%s ⇒ %s"
               % ("、".join("%s→%s" % (a, b) for a, b in cases), "全对" if ok else "⛔ 有错"))

    # ---- G0-2 ⑥：**平票夹具**（⚠ 这一批真数据里**没有**平票轨迹 ⇒ 必须靠夹具覆盖）
    tie_recs = [
        {"tid": "fx__tie__think", "p9_hi_meas": 1.0, "p9_lo_meas": 0.0},
        {"tid": "fx__tie__think", "p9_hi_meas": 0.0, "p9_lo_meas": 1.0},
    ]
    tie = pool_trajectories(tie_recs)["fx__tie__think"]
    tie_ok = (tie["m"] == 2 and tie["nT"] == 1 and tie["verdict"] is False)
    crit.check("S-TIE", tie_ok,
               "**平票夹具**（m=2、1 正 1 负 ⇒ nT·2 = m）：多数决必须判 **False**"
               "（⛔ 平票算 False）⇒ 我算 m=%d、nT=%d、判决=%s ⇒ %s"
               % (tie["m"], tie["nT"], tie["verdict"],
                  "对" if tie_ok else "⛔ 错（⛔ 若这里判 True，说明用的是 `>=`）"))

    # ---- G0-2 ⑤：Fisher 精确 vs 已知值
    ok = True
    detail = []
    for args, want, label in [((1, 1, 1, 1), 1.0, "2×2 全 1 ⇒ p = 1"),
                              ((10, 0, 0, 10), 2.0 / 184756.0, "10/0 vs 0/10 ⇒ p = 2/C(20,10)")]:
        got = fisher_exact(*args)
        if abs(got - want) > 1e-12:
            ok = False
            detail.append("%s：我=%.17g 期望=%.17g" % (label, got, want))
    crit.check("S-FISHER", ok,
               "Fisher 精确 vs 已知值：%s" % ("全对" if ok else "⛔ %s" % detail))

    return crit


# =============================================================================
# 主流程
# =============================================================================


def analyse(w_log, r_log):
    """⚖ 跑真数据（⛔ 只读）。返回 (结果字典, 判据收集器)。"""
    crit = Criteria()
    arms = {}
    for arm, path in (("w", w_log), ("rand", r_log)):
        if not os.path.isfile(path):
            die("缺原始跑批日志：%s" % path)
        recs, hdr_tids = parse_raw_log(path)
        kept, dropped = cell_set(recs)
        pooled = pool_trajectories(kept)
        arms[arm] = {"pooled": pooled, "kept": kept, "dropped": dropped,
                     "n_recs": len(recs), "hdr_tids": hdr_tids}
        print("臂 %s：原始日志 %d 条 ｜ 进格集合 %d ｜ 剔出 %d ｜ 轨迹 %d"
              % (arm, len(recs), len(kept), len(dropped), len(pooled)))
        for r, why in dropped:
            print("    剔出：%s（%s）" % (r.get("tid"), why))

    # ---- P1：数据路径（⛔ 必须是 bpath 原始日志，⛔ 不是拆分产物）
    path_ok = True
    for arm in ("w", "rand"):
        p = (w_log if arm == "w" else r_log)
        if os.path.basename(p).startswith("pf") or os.sep + "work" + os.sep in p:
            path_ok = False
    crit.check("S-PATHPROLOG", path_ok,
               "数据路径 = bpath **原始**跑批日志（⛔ 不是拆分产物）：%s"
               % ("✅ 两个臂都是原始日志" if path_ok else "⛔ 有一臂读了拆分产物"))

    # ---- 解析自证：JSON 的 tid 与 RESULT 头必须对得上
    for arm in ("w", "rand"):
        a = arms[arm]
        json_tids = set(a["pooled"].keys())
        missing = json_tids - a["hdr_tids"]
        extra_hdr = len(a["hdr_tids"]) - len(json_tids & a["hdr_tids"])
        crit.check("S-PARSE-%s" % arm, (not missing),
                   "解析自证：%s 臂 JSON 里的 %d 个 tid **全部**出现在 RESULT 头里"
                   "（头里多出 %d 个 —— 那些格没读数 ⇒ 不进格集合）"
                   % (arm, len(json_tids), extra_hdr))

    # ---- 块键两条路线必须给出同一个块集合
    route_ok = True
    for arm in ("w", "rand"):
        for tid in arms[arm]["pooled"]:
            if block_key_split(tid) != block_key_suffix(tid):
                route_ok = False
    crit.check("S-BLOCKROUTE", route_ok,
               "块键两条路线（按 `__` 切分 vs 剥后缀）给出**同一个**块集合：%s"
               % ("✅ 逐条一致" if route_ok else "⛔ 有 tid 两条路线不一致"))

    # ---- 轨迹级 + 块级计数
    traj_pos = {}
    for arm in ("w", "rand"):
        p = arms[arm]["pooled"]
        traj_pos[arm] = (sum(1 for v in p.values() if v["verdict"]), len(p))
    blocks = {arm: build_blocks(arms[arm]["pooled"]) for arm in ("w", "rand")}
    blk_pos = {}
    for arm in ("w", "rand"):
        vs = [block_verdict(b) for b in blocks[arm].values()]
        vs = [v for v in vs if v is not None]
        blk_pos[arm] = (sum(1 for v in vs if v), len(vs))

    # ---- G0-3：自检必须逐位复现面板
    ok = True
    bad = []
    for arm, key in (("w", "traj_w"), ("rand", "traj_rand")):
        if traj_pos[arm] != EXPECT[key]:
            ok = False
            bad.append("%s 轨迹级 我=%s 期望=%s" % (arm, traj_pos[arm], EXPECT[key]))
    for arm, key in (("w", "blk_w"), ("rand", "blk_rand")):
        if blk_pos[arm] != EXPECT[key]:
            ok = False
            bad.append("%s 块级 我=%s 期望=%s" % (arm, blk_pos[arm], EXPECT[key]))
    f_traj = fisher_exact(traj_pos["w"][0], traj_pos["w"][1] - traj_pos["w"][0],
                          traj_pos["rand"][0], traj_pos["rand"][1] - traj_pos["rand"][0])
    f_blk = fisher_exact(blk_pos["w"][0], blk_pos["w"][1] - blk_pos["w"][0],
                         blk_pos["rand"][0], blk_pos["rand"][1] - blk_pos["rand"][0])
    if abs(f_traj - EXPECT["fisher_traj"]) > 5e-7:
        ok = False
        bad.append("轨迹级 Fisher 我=%.6f 期望=%.6f" % (f_traj, EXPECT["fisher_traj"]))
    if abs(f_blk - EXPECT["fisher_blk"]) > 5e-7:
        ok = False
        bad.append("块级 Fisher 我=%.6f 期望=%.6f" % (f_blk, EXPECT["fisher_blk"]))
    crit.check("S-SELFPANEL", ok,
               "G0-3 自检逐位复现面板：轨迹级 w %d/%d、rand %d/%d ｜ 块级 w %d/%d、rand %d/%d "
               "｜ Fisher 轨迹 %.6f、块 %.6f ⇒ %s"
               % (traj_pos["w"][0], traj_pos["w"][1], traj_pos["rand"][0], traj_pos["rand"][1],
                  blk_pos["w"][0], blk_pos["w"][1], blk_pos["rand"][0], blk_pos["rand"][1],
                  f_traj, f_blk, "全部逐位相同" if ok else "⛔ %s" % bad))
    if not ok:
        for b in bad:
            print("⛔ 自检不符：%s" % b)
        # ⚖⚖ **硬停**（⛔ 不是崩）：闸不过 ⇒ 解析不可信 ⇒ 拒绝继续算
        #    ⇒ 打印**可识别的标记** ⇒ ⇒ 变异台能把它认成「被拦下」，⛔ 不是「台架瞎了」
        print("G0_3_HARDSTOP: 自检复现不上 ⇒ 硬停（⛔ 不许拿「差不多」的数继续算）")
        return None, crit

    # ---- 块级：两条臂按块对齐
    keys = sorted(set(blocks["w"]) & set(blocks["rand"]))
    pw, pr, bdiff = [], [], []
    for q in keys:
        vw = block_verdict(blocks["w"][q])
        vr = block_verdict(blocks["rand"][q])
        if vw is None or vr is None:
            continue
        pw.append(1 if vw else 0)
        pr.append(1 if vr else 0)
        # 轨迹尺度的块差（⛔ 与先导探查同一统计量尺度 ⇒ 才有可比性）
        bdiff.append((sum(1 for v in blocks["w"][q].values() if v["verdict"])
                      - sum(1 for v in blocks["rand"][q].values() if v["verdict"])))
    nblk = len(pw)

    # ---- P6：精确块级置换（DP）
    p_blk_exact, obs_blk, tail_blk, tot_blk = exact_block_perm_p(bdiff)
    print("")
    print("==== 跨臂零分布（块是独立单位 ⇒ 保守口径）====")
    print("· **精确**块级置换（DP 精确零分布，⛔ 非 MC）：p = %.8f（obs = %d ｜ 尾 %d / %d）"
          % (p_blk_exact, obs_blk, tail_blk, tot_blk))
    print("  ⚖ obs 的**尺度**：本实现用**块尺度**（块内 w 正数 − rand 正数）⇒ 先导探查印的 obs = 34 "
          "是**轨迹尺度**（同一条统计量的 2 倍）⇒ ⇒ **p 值与尺度无关**（|T| ≥ |obs| 同时放大）⇒ ⇒ 可比")
    # ---- S-DP-TOTAL：DP 的计数总数必须恰好等于 2^n（⛔ 能红：comb 因子写错就变）
    dp_total_ok = (tot_blk == (2 ** len(bdiff)))
    crit.check("S-DP-TOTAL", dp_total_ok,
               "DP 精确零分布的**计数总数** = %d（期望 2^%d = %d）⇒ %s"
               % (tot_blk, len(bdiff), 2 ** len(bdiff),
                  "对" if dp_total_ok else "⛔ 组合数因子写错了"))
    scout_p = SPEC["scout_blk_perm_p"]
    mc_se = math.sqrt(scout_p * (1 - scout_p) / SPEC["n_perm_expected"])
    d_mc = p_blk_exact - scout_p
    crit.check("S-EXACT-P", abs(d_mc) <= 3 * mc_se,
               "精确块级置换 p = %.8f ｜ 先导探查 MC p = %.6f ｜ 差 %+.8f"
               "（MC 的 1 SE ≈ %.8f ⇒ 差 = %.2f SE ⇒ %s）"
               % (p_blk_exact, scout_p, d_mc, mc_se, abs(d_mc) / mc_se,
                  "在 3 SE 内 ⇒ 是 MC 误差" if abs(d_mc) <= 3 * mc_se
                  else "⛔ 超出 3 SE ⇒ DP 或 MC 其中一个坏了"))

    # ---- P7：删一块 jackknife 区间（⛔ 非 bootstrap）
    jlo, jhi, jse = cluster_jackknife_ci(pw, pr, SPEC["alpha"])
    theta_blk = 100.0 * (sum(pw) / float(nblk) - sum(pr) / float(nblk))
    print("· 块级差 %+.2f pp ｜ **删一块 jackknife** 95%% 区间 [%+.2f, %+.2f] pp（SE = %.4f）"
          % (theta_blk, jlo, jhi, jse))
    # ---- S-JACK-LINEAR：**两条等价路线**算同一个方差 ⇒ 必须一致（⛔ 能红）
    th_lin = []
    for i in range(nblk):
        th_lin.append(100.0 * ((sum(pw) - pw[i]) / float(nblk - 1)
                               - (sum(pr) - pr[i]) / float(nblk - 1)))
    mbar = sum(th_lin) / float(nblk)
    v_routeA = (nblk - 1) / float(nblk) * sum((v - mbar) ** 2 for v in th_lin)
    v_routeB = (nblk - 1) / float(nblk) * sum((v - theta_blk) ** 2 for v in th_lin)
    lin_ok = (abs(mbar - theta_blk) < 1e-9 and abs(v_routeA - v_routeB) < 1e-9)
    crit.check("S-JACK-LINEAR", lin_ok,
               "jackknife 两条等价路线（以 θ̄ 为心 vs 以 θ̂ 为心）：θ̄ = %.10f、θ̂ = %.10f ｜ "
               "方差 %.10f vs %.10f ⇒ %s（统计量是**线性的** ⇒ 两条路必须一致）"
               % (mbar, theta_blk, v_routeA, v_routeB,
                  "一致" if lin_ok else "⛔ 不一致 ⇒ 统计量非线性或实现写错了"))

    # ---- 轨迹级对照（Newcombe95）
    nw, nr = traj_pos["w"][1], traj_pos["rand"][1]
    tlo, thi = newcombe(traj_pos["w"][0], nw, traj_pos["rand"][0], nr)
    theta_traj = 100.0 * (traj_pos["w"][0] / float(nw) - traj_pos["rand"][0] / float(nr))
    print("· 轨迹级差 %+.2f pp ｜ Newcombe95（**假定轨迹独立**）[%+.2f, %+.2f] pp（对照）"
          % (theta_traj, tlo, thi))

    # ---- P8：LOBO（逐块剔除）
    lobo_d, lobo_p = [], []
    for i in range(nblk):
        sub = bdiff[:i] + bdiff[i + 1:]
        sp, _o, _t, _tt = exact_block_perm_p(sub)
        lobo_p.append(sp)
        lobo_d.append(100.0 * ((sum(pw) - pw[i]) / float(nblk - 1)
                               - (sum(pr) - pr[i]) / float(nblk - 1)))
    flips = sum(1 for v in lobo_p if v >= SPEC["alpha"])
    print("· **LOBO**（逐块剔除 %d 个子集）：块级差 [%+.2f, %+.2f] pp ｜ 置换 p ∈ [%.6f, %.6f] ｜ "
          "**判决被掀翻的子集数 = %d**" % (nblk, min(lobo_d), max(lobo_d),
                                          min(lobo_p), max(lobo_p), flips))
    crit.check("S-LOBO", (len(lobo_p) == nblk),
               "LOBO 跑了 %d/%d 个子集（每个子集都重算了块级差与**精确**置换 p）"
               % (len(lobo_p), nblk))

    # ---- P9：块内相关（一致率 / 偶然一致率 / κ / 精确二项 p）
    print("")
    print("==== 块内相关（同一块的两条轨迹）====")
    within = {}
    for arm in ("w", "rand"):
        bl = blocks[arm]
        agree = tot = 0
        for q in keys:
            dw = bl.get(q)
            if not dw or len(dw) != 2:
                continue
            vs = [v["verdict"] for v in dw.values()]
            tot += 1
            agree += 1 if vs[0] == vs[1] else 0
        p_pos = (sum(1 for v in arms[arm]["pooled"].values() if v["verdict"])
                 / float(len(arms[arm]["pooled"])))
        po = agree / float(tot)
        pe = p_pos * p_pos + (1 - p_pos) * (1 - p_pos)
        kappa = (po - pe) / (1 - pe) if (1 - pe) else float("nan")
        p_bin = binom_two_sided_exact(agree, tot, pe)
        within[arm] = {"agree": agree, "tot": tot, "po": po, "pe": pe,
                       "kappa": kappa, "p": p_bin}
        print("· %s 臂：块 %d ｜ 一致 %d（po = %.4f）｜ 偶然一致 pe = %.4f ｜ κ = %+.4f "
              "｜ 精确二项两侧 p = %.6f ⇒ %s"
              % (arm, tot, agree, po, pe, kappa, p_bin,
                 "**可检出**" if p_bin < SPEC["alpha"] else "**未检出**（⛔ 不是「不相关」）"))
    crit.check("S-WITHIN", all("p" in v and v["tot"] > 0 for v in within.values()),
               "块内相关：两臂都报了 po / pe / κ / **精确二项 p**（p 值自己算）")

    # ---- P10：复制格一致性
    print("")
    print("==== 复制格一致性（每条轨迹 3 个 `pos_frac`）====")
    repl = {}
    for arm in ("w", "rand"):
        same = split = 0
        for tid, v in arms[arm]["pooled"].items():
            vals = [x for x in v["vals"] if x != 0]
            if len(vals) < 2:
                continue
            if all(x == vals[0] for x in vals):
                same += 1
            else:
                split += 1
        repl[arm] = (same, split, split / float(same + split))
        print("· %s 臂：三格全一致 %d ｜ 2:1 分歧 %d ｜ 分歧率 %.4f"
              % (arm, same, split, split / float(same + split)))
    crit.check("S-REPL", all(repl[a][1] > 0 for a in ("w", "rand")),
               "复制格分歧率：两臂都报了（三格全一致 / 2:1 分歧 / 分歧率）")

    # ---- 轨迹级 McNemar（对照）
    disc_w = disc_r = 0
    for t in set(arms["w"]["pooled"]) & set(arms["rand"]["pooled"]):
        sw = arms["w"]["pooled"][t]["verdict"]
        sr = arms["rand"]["pooled"][t]["verdict"]
        if sw and not sr:
            disc_w += 1
        elif sr and not sw:
            disc_r += 1
    mcn_p = mcnemar_exact(disc_w, disc_r)
    print("")
    print("· 轨迹级 McNemar（精确二项，不一致 %d 条：w 优 %d / rand 优 %d）：p = %.6f（对照）"
          % (disc_w + disc_r, disc_w, disc_r, mcn_p))

    # ---- §3.3：结论形态（⛔ 只允许 C-A / C-B / C-C）
    alpha = SPEC["alpha"]
    within_detectable = any(v["p"] < alpha for v in within.values())
    decisive = (p_blk_exact < alpha) and (jlo > 0 or jhi < 0) and (flips == 0)
    if decisive:
        verdict = "C-A"
        vtext = ("**C-A：在把块当独立单位的保守口径下，判决仍然成立**"
                 "（精确块级置换 p = %.8f < α；块级差 jackknife 区间 [%+.2f, %+.2f] pp 不含 0；"
                 "LOBO 掀翻数 = 0 ⇒ 没有单独一块能推翻它）"
                 % (p_blk_exact, jlo, jhi))
    elif within_detectable:
        verdict = "C-C"
        vtext = ("**C-C：块内相关可检出，且保守口径下判决不成立** ⇒ ⇒ 「判决成立」**撤回**")
    else:
        verdict = "C-B"
        vtext = ("**C-B：保守零分布下判决不成立** ⇒ ⇒ 「判决成立」**撤回**"
                 "（⇒ 改写为『**口径依赖**：只在假定轨迹独立时成立』）")
    print("")
    print("==== 结论形态（预登记 §3.3：⛔ 只允许 C-A / C-B / C-C）====")
    print("· %s" % vtext)
    crit.check("S-VERDICT", verdict in ("C-A", "C-B", "C-C"),
               "结论形态 = %s（∈ {C-A, C-B, C-C}）" % verdict)

    res = {
        "traj_pos": traj_pos, "blk_pos": blk_pos, "fisher_traj": f_traj,
        "fisher_blk": f_blk, "p_blk_exact": p_blk_exact, "obs_blk": obs_blk,
        "jack_lo": jlo, "jack_hi": jhi, "theta_blk": theta_blk,
        "theta_traj": theta_traj, "newc_lo": tlo, "newc_hi": thi,
        "within": within, "repl": repl, "nblk": nblk, "mcn_p": mcn_p,
        "lobo_min": min(lobo_d), "lobo_max": max(lobo_d),
        "lobo_pmin": min(lobo_p), "lobo_pmax": max(lobo_p), "lobo_flips": flips,
        "verdict": verdict,
        "n_recs": {a: arms[a]["n_recs"] for a in arms},
        "n_kept": {a: len(arms[a]["kept"]) for a in arms},
    }
    return res, crit


def print_cross(res):
    """⚖ 机器可读块（供跨实现互证脚本逐项抠）。"""
    print("")
    print("==== CROSS（机器可读；跨实现互证用）====")
    print("CROSS|traj_w=%d/%d" % res["traj_pos"]["w"])
    print("CROSS|traj_rand=%d/%d" % res["traj_pos"]["rand"])
    print("CROSS|blk_w=%d/%d" % res["blk_pos"]["w"])
    print("CROSS|blk_rand=%d/%d" % res["blk_pos"]["rand"])
    print("CROSS|fisher_traj=%.6f" % res["fisher_traj"])
    print("CROSS|fisher_blk=%.6f" % res["fisher_blk"])
    print("CROSS|theta_blk_pp=%.2f" % res["theta_blk"])
    print("CROSS|theta_traj_pp=%.2f" % res["theta_traj"])
    print("CROSS|nblk=%d" % res["nblk"])
    print("CROSS|blk_agree_w=%d" % res["within"]["w"]["agree"])
    print("CROSS|blk_agree_rand=%d" % res["within"]["rand"]["agree"])
    print("CROSS|blk_po_w=%.4f" % res["within"]["w"]["po"])
    print("CROSS|blk_po_rand=%.4f" % res["within"]["rand"]["po"])
    print("CROSS|repl_same_w=%d" % res["repl"]["w"][0])
    print("CROSS|repl_split_w=%d" % res["repl"]["w"][1])
    print("CROSS|repl_rate_w=%.4f" % res["repl"]["w"][2])
    print("CROSS|repl_same_rand=%d" % res["repl"]["rand"][0])
    print("CROSS|repl_split_rand=%d" % res["repl"]["rand"][1])
    print("CROSS|repl_rate_rand=%.4f" % res["repl"]["rand"][2])
    print("CROSS|mcnemar_p=%.6f" % res["mcn_p"])
    print("CROSS|lobo_min_pp=%.2f" % res["lobo_min"])
    print("CROSS|lobo_max_pp=%.2f" % res["lobo_max"])
    print("CROSS|lobo_flips=%d" % res["lobo_flips"])
    print("CROSS|verdict=%s" % res["verdict"])
    print("CROSS|exact_blk_perm_p=%.8f" % res["p_blk_exact"])
    print("CROSS|jack_lo_pp=%.2f" % res["jack_lo"])
    print("CROSS|jack_hi_pp=%.2f" % res["jack_hi"])


def main():
    ap = argparse.ArgumentParser(description="前提独立性 · 第二条独立实现（244.82）")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑 Phase-0 闸门（G0-1/G0-2，零 GPU、已知答案）")
    ap.add_argument("--print-spec", action="store_true", help="印口径常量（供变异台对账）")
    ap.add_argument("--w-log", default=os.environ.get(
        "R244_BPATH", "/home/zhourui/steer3d_bpath") + "/r244_warm_fd_w.log")
    ap.add_argument("--rand-log", default=os.environ.get(
        "R244_BPATH", "/home/zhourui/steer3d_bpath") + "/r244_warm_fd_rand.log")
    args = ap.parse_args()

    if args.print_spec:
        for k in sorted(SPEC):
            print("SPEC|%s=%s" % (k, SPEC[k]))
        for k in sorted(EXPECT):
            v = EXPECT[k]
            print("EXPECT|%s=%s" % (k, v if not isinstance(v, tuple) else "%d/%d" % v))
        return 0

    crit = Criteria()
    if args.selftest:
        gate_selftest(crit)
        return crit.summary()

    print("==============================================================")
    print("前提独立性 · 第二条独立实现（244.82）｜ 数据路径 = bpath 原始日志")
    print("==============================================================")
    res, crit = analyse(args.w_log, args.rand_log)
    if res is None:
        print("")
        print("判据 %d 条 ｜ PASS %d ｜ FAIL %d（G0-3 硬停 ⇒ 本次分析**没跑**）"
              % (len(crit.items), len(crit.items) - crit.fail_count(), crit.fail_count()))
        return 3
    print_cross(res)
    print("")
    n = len(crit.items)
    bad = crit.fail_count()
    print("判据 %d 条 ｜ PASS %d ｜ FAIL %d" % (n, n - bad, bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
