#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flip_robustness.py —— 「R 次重复 launch 能不能回答『k/n 是不是噪声』」（零 GPU）

🔴🔴 **本工具的结论（精确枚举，不是模拟）**

  ⚖⚠⚠⚖⚖⚖⚖ **不能。重复 launch 对「计数」这个检验的证据量是零。**

  符号检验的零假设是「每题一个公平硬币」。R 次 launch 后按**多数符号**
  计数（平票随机破），每题「多数为正」的概率**恒等于 0.5**，
  ⚖ 与 R **完全无关**（R=1/2/3/4/5/7/10/20/41 精确枚举全部 = 0.500000000000）
  ⇒ `X_maj ~ Binomial(n, 0.5)` 对任何 R 都成立
  ⇒ `P(X ≥ 12) = 0.006470`，**两尾 ×2 = 0.012939**
  ⇒ ⛔ 与账本里那个 **0.01294 逐位相同**，而它**本来就是 R=1 的数**
  ⇒ **多跑几轮 launch，这个 p 一个位都不会动。**

⚖⚠⚖⚠⚖ **那我第一版的框架错在哪**（这一条比结论更重要）

  我写的是：估出每题的正向率 `q_i`，再算 `P(X ≥ k | q_i)`。
  🔴🔴 **那是双重计数**：`k` 本身就来自那些 launch，而 `q_i` 也是从
  同一批 launch 估的 ⇒ 条件在一个**已经包含了 k** 的量上
  ⇒ 无论 R 多大、`q_i` 多准，`k` 都「不奇怪」
  ⇒ 该框架**结构上永远给不出证据**。
  ⚖⚠⚠⚠ 自检当场抓到：我第一版对「每题都翻了」的夹具也报了
  「决定为真」（p 上界 3.78e-11）—— ⛔ 那不是判据松，是**问错了**。

⚖⚖ **那么 R 能买到什么？只有两样，都不是「计数」的证据**

  ① **逐题符号稳定性**（诊断量）：哪些题的多数是真的稳住的。
  ② **效应量的信噪比**：`d_i = meas_hi − meas_lo` 的跨 launch 散布 vs
     `|d_i|` 本身 ⇒ 这是**幅度**论证，⛔ 不是**计数**论证。
  ⚖⚠ 探针里**已经有**这个量（`margin_meas`，单位 sigma）⇒
  真正能回答「12/14 是不是噪声」的是**幅度**那条路，⛔ 不是 R 更大的计数。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不读真实数据。
⚖⚠⚠⚖ 每条判据都必须**能红**：变异台改的就是喂给它的数据形状与判据源码。
"""

import argparse
import ast
import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
ALPHA = 0.05


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 组合数学（纯 stdlib）
def binom_pmf(n, k, p):
    if k < 0 or k > n:
        return 0.0
    if p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0 if k == n else 0.0
    lp = (math.lgamma(n + 1.0) - math.lgamma(k + 1.0) - math.lgamma(n - k + 1.0)
          + k * math.log(p) + (n - k) * math.log1p(-p))
    return math.exp(lp) if lp > -745.0 else 0.0


def binom_sf(n, k, p):
    """⚖ P(X ≥ k)，X ~ Binomial(n, p)。⚠ 对数空间求和，
    ⛔ 不许直接 `comb(n,k)*p**k*…` —— n 大时下溢成 0 ⇒ 假 0。"""
    return sum(binom_pmf(n, j, p) for j in range(k, n + 1))


def sign_test_two_sided(k, n, alpha=None):
    """⚖ 两尾符号检验 p（账本口径：两倍单尾）。⚠ 这个式子里**没有 R**。"""
    one = binom_sf(n, max(k, n - k), 0.5)
    return min(1.0, 2.0 * one)


def majority_positive_prob(R):
    """⚖ 精确：在「每题公平硬币」下，R 次 launch 的**多数为正**的概率。

    ⚖⚠ 偶数 R 的平票按**随机破**处理（这是让该概率恒为 0.5 的唯一办法；
    ⛔ 若改成「平票不算正」，概率就会变成 <0.5，p 会随 R 漂 —— 那是**口径**
    问题不是物理问题，所以这里必须写死）。
    """
    half = 0.5 ** R
    if R % 2 == 0:
        ties = math.comb(R, R // 2) * half
        return sum(math.comb(R, j) * half for j in range(R // 2 + 1, R + 1)) + 0.5 * ties
    return sum(math.comb(R, j) * half for j in range(R // 2 + 1, R + 1))


def cp_bounds(x, n, alpha=ALPHA):
    """⚖ Clopper–Pearson 比例的**精确**区间（纯 stdlib：二分 + 精确二项尾）。"""
    if n <= 0:
        return (0.0, 1.0)
    if x <= 0:
        return (0.0, _solve_upper(0, n, alpha))
    if x >= n:
        return (_solve_lower(n, n, alpha), 1.0)
    return (_solve_lower(x, n, alpha), _solve_upper(x, n, alpha))


def _solve_lower(x, n, alpha):
    """⚖ 求 L 使 P_{Bin(n,L)}(X ≥ x) = alpha。⚖⚠ x>0 时该函数对 p **递增**
    ⇒ f(mid)<alpha 表示 p 偏小，**抬 lo**。⚖⚠⚠ 我第一版写反了 ⇒ L 恒为 1。"""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if binom_sf(n, x, mid) < alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _solve_upper(x, n, alpha):
    """⚖ 求 U 使 P_{Bin(n,U)}(X ≤ x) = alpha。⚖⚠ x<n 时该函数对 p **递减**
    ⇒ f(mid)>alpha 表示 p 偏小，**抬 lo**。⚖⚠⚠ 第一版按「递增」写 ⇒ U 恒为 0。"""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if sum(binom_pmf(n, j, mid) for j in range(0, x + 1)) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --------------------------------------------------------------- 数据闸
def normalize(records):
    """⚖ 把 [(name, arm, [d...])] 收成 {arm: [(name, [d...])]}。"""
    arms = {}
    for name, arm, ds in records:
        if not ds:
            raise HardFail("题 %s 没有任何 launch 读数 ⇒ **未量到**，⛔ 不许当 0" % name)
        arms.setdefault(arm, []).append((name, list(ds)))
    for arm, rows in arms.items():
        rs = sorted({len(r[1]) for r in rows})
        if len(rs) > 1:
            raise HardFail("臂 %s 的 launch 数不一致：%s ⇒ ⛔ 不同 R 的题不可并进同一个和"
                           % (arm, rs))
        for nm, ds in rows:
            if any((not isinstance(x, (int, float))) or x != x for x in ds):
                raise HardFail("题 %s 的读数里有 NaN/非数 ⇒ **未量到**" % nm)
    return arms


def majority_sign(ds):
    """⚖ 多数符号，平票按**第一次读数**破（⛔ 不随机 ⇒ 结果可复现）。"""
    pos = sum(1 for d in ds if d > 0)
    neg = sum(1 for d in ds if d < 0)
    if pos == neg:
        return ds[0] > 0
    return pos > neg


# --------------------------------------------------------------- 分析
def analyze_arm(rows, alpha=ALPHA, arm_label=""):
    R = len(rows[0][1])
    n = len(rows)
    maj = [majority_sign(ds) for _, ds in rows]
    k_maj = sum(1 for m in maj if m)
    k_first = sum(1 for _, ds in rows if ds[0] > 0)

    p_two = sign_test_two_sided(k_maj, n)

    # 逐题：翻转次数 + CP 界（**诊断量，不是证据**）
    per = []
    for (nm, ds), m in zip(rows, maj):
        x = sum(1 for d in ds if d > 0)
        lo, up = cp_bounds(x, R, alpha)
        per.append((nm, x, R, lo, up, m))

    return {"arm": arm_label, "R": R, "n": n, "k_maj": k_maj,
            "k_first": k_first, "p_two": p_two, "per": per, "alpha": alpha,
            "maj_prob": majority_positive_prob(R)}


def render(res):
    L = []
    a = res["alpha"]
    L.append("【臂】%s ｜ R=%d ｜ n=%d ｜ 多数计数 k_maj=%d ｜ 第一次读数计数 k_first=%d ｜ α=%.2f"
             % (res["arm"], res["R"], res["n"], res["k_maj"], res["k_first"], a))
    L.append("")
    L.append("【1】⚖⚠⚠⚖ **计数检验的 p 与 R 无关**（这是本节的结论）")
    L.append("  ⚖ 「每题公平硬币」下，多数为正的概率 = %.12f（R=%d）"
             % (res["maj_prob"], res["R"]))
    L.append("  ⚖⇒ X_maj ~ Binomial(%d, 0.5)，**任何 R 都成立**" % res["n"])
    L.append("  ⚖⇒ 两尾符号检验 p = %.6f  ←  ⚠ **式子里没有 R**" % res["p_two"])
    L.append("  ⚖⇒ R=%d 这个 p 与 R=1 的 p **逐位相同** ⇒ 多跑几轮**一个位都不会动**"
             % res["R"])
    L.append("")
    L.append("【2】逐题符号稳定性（⚖ **诊断量，不是证据**）")
    for nm, x, R, lo, up, m in res["per"]:
        tag = "" if 0 < x < R else "  ⚠ 全同 ⇒ 只见到了 %d/%d" % (x, R)
        L.append("  %-10s %d/%d 正  CP[%.3f, %.3f]  多数=%s%s"
                 % (nm, x, R, lo, up, "正" if m else "负", tag))
    L.append("")
    L.append("【3】判定（只有三档）")
    if res["p_two"] < a:
        L.append("  ✅ 计数证据成立：p = %.6f < α = %.2f" % (res["p_two"], a))
        L.append("     ⚖⚠⚠ 这**不是**「翻转解释不了它」——是「在「每题公平硬币」这个"
                 "零假设下，%d/%d 不奇怪的程度只有 %.4f%%」" % (res["k_maj"], res["n"],
                                                        res["p_two"] * 100))
    elif res["p_two"] >= a:
        L.append("  ⚠ **未量到**：p = %.6f ≥ α = %.2f ⇒ ⛔ **不是「无差异」**，是"
                 "「这个零假设下它很普通」" % (res["p_two"], a))
    L.append("")
    L.append("【4】⛔ 本节**没有**回答的")
    L.append("  ⛔ 「12/14 是不是噪声」——⚠ **计数口径答不了，且 R 再大也答不了**")
    L.append("  ⚖⚠ 能答的是**幅度**：`d_i = meas_hi − meas_lo` 的跨 launch 散布 vs")
    L.append("     `|d_i|` 本身（探针里已有 `margin_meas`，单位 sigma）")
    return L


# --------------------------------------------------------------- 自检
def selftest(alpha=ALPHA):
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # C1 二项尾解析可算
    chk("C1", abs(binom_sf(4, 2, 0.5) - 11 / 16.0) < 1e-12,
        "P(X≥2),Bin(4,.5)=11/16=%.6f" % binom_sf(4, 2, 0.5))

    # C2 ⚖⚠⚠ 本节的核心断言：多数为正的概率**与 R 无关**
    ps = [majority_positive_prob(R) for R in (1, 2, 3, 4, 5, 7, 10, 20, 41)]
    chk("C2", max(abs(x - 0.5) for x in ps) < 1e-12,
        "R=%s ⇒ 全部 = %.12f（精确枚举）"
        % ("/".join(map(str, (1, 3, 10, 41))), ps[0]))

    # C3 p 与 R 无关：同一 k、同一 n，不同 R ⇒ p 逐位相同
    a1 = analyze_arm(normalize([("t%02d" % i, "x", [1.0] if i < 12 else [-1.0])
                                for i in range(14)])["x"], alpha, "R=1")
    a3 = analyze_arm(normalize([("t%02d" % i, "x", [1.0, 1.0, -1.0] if i < 12
                                 else [-1.0, -1.0, -1.0])
                                for i in range(14)])["x"], alpha, "R=3")
    chk("C3", a1["p_two"] == a3["p_two"] == sign_test_two_sided(12, 14),
        "R=1 与 R=3 的 p 都 = %.6f" % a1["p_two"])

    # C4 两尾值必须与账本记录的 0.01294 对得上
    chk("C4", abs(sign_test_two_sided(12, 14) - 0.012939) < 5e-6,
        "两尾 p = %.6f（账本记的是 0.01294）" % sign_test_two_sided(12, 14))
    # ⚖⚠⚠⚖ **对称那一支也要测**（244.47 台架当场抓到）：
    #   变异台 N2 把 `max(k, n-k)` 改成 `k` ⇒ 在 k>n/2 时**两支重合**⇒ 死变异。
    #   ⛔ 只测 12/14 ⇒ 那一支**从未被验过** ⇒ 判据看起来是绿的，其实是半盲的。
    chk("C4b", abs(sign_test_two_sided(2, 14) - sign_test_two_sided(12, 14)) < 1e-15,
        "k=2/14 与 k=12/14 必须**完全相等**（对称）：%.6f vs %.6f"
        % (sign_test_two_sided(2, 14), sign_test_two_sided(12, 14)))

    # C5 CP 界：解析解 x=n ⇒ L = alpha^(1/n)
    lo, up = cp_bounds(3, 3)
    chk("C5", up == 1.0 and abs(lo - alpha ** (1.0 / 3.0)) < 1e-9,
        "x=n=3 ⇒ L = α^(1/3) = %.6f" % lo)
    lo0, up0 = cp_bounds(0, 3)
    chk("C6", lo0 == 0.0 and abs(up0 - (1 - alpha ** (1.0 / 3.0))) < 1e-9,
        "x=0,n=3 ⇒ U = 1−α^(1/3) = %.6f" % up0)

    # C7 多数符号的平票口径：可复现、且第一次读数说了算
    chk("C7", majority_sign([1.0, -1.0]) is True
        and majority_sign([-1.0, 1.0]) is False,
        "平票按**第一次读数**破 ⇒ [+,−]=%s 而 [−,+]=%s"
        % (majority_sign([1.0, -1.0]), majority_sign([-1.0, 1.0])))

    # C8 「有翻转」不许改变 p —— 这是本工具第一版框架搞错的地方
    # ⚖⚠⚠⚠ 夹具要**多数仍是正**（[+,+,−]），⛔ 不是 [+,-,-]（那个多数是负，
    #   我第一版就这么写错了一次 ⇒ k_maj 数成 0，还差点以为「翻转把证据打没了」）
    flipped = [("t%02d" % i, "x", ([1.0, 1.0, -1.0] if i < 12 else [-1.0] * 3))
               for i in range(14)]
    a8 = analyze_arm(normalize(flipped)["x"], alpha, "有翻转")
    chk("C8", a8["k_maj"] == 12 and abs(a8["p_two"] - a1["p_two"]) < 1e-15,
        "每题都有翻转 ⇒ k_maj 仍是 %d，p 仍是 %.6f ⇒ 翻转**不改变**计数证据"
        % (a8["k_maj"], a8["p_two"]))

    # C9 输入闸
    for tag, recs, want in (
            ("launch 数不一致", [("a", "x", [1.0, 2.0]), ("b", "x", [1.0])],
             "launch 数不一致"),
            ("空读数", [("a", "x", [])], "未量到"),
            ("NaN", [("a", "x", [float("nan")])], "未量到")):
        try:
            normalize(recs)
            chk("C9-%s" % tag, False, "%s 必须 HardFail" % tag)
        except HardFail as e:
            chk("C9-%s" % tag, want in str(e), "拒读理由含「%s」：%s" % (want, str(e)[:40]))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="R-launch 能不能回答计数问题（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    print("⚠ 本工具⛔ **不读真实数据** —— R-launch 数据还没跑出来。")
    print("⚠ 下面是**精确枚举**与**合成演示**。\n")

    print("【A】核心不变性：多数为正的概率（每题公平硬币下）")
    for R in (1, 2, 3, 4, 5, 7, 10, 20, 41):
        print("  R=%-3d %.12f" % (R, majority_positive_prob(R)))
    print("  ⚖⚠⚠⚖ 全部 = 0.5 ⇒ `X_maj ~ Binomial(n, 0.5)` 对**任何 R**成立")
    print("  ⚖⇒ n=14, k_maj=12 ⇒ 单尾 %.6f ｜ **两尾 ×2 = %.6f**（与 R 无关）"
          % (binom_sf(14, 12, 0.5), sign_test_two_sided(12, 14)))
    print("  ⚖⚠⚠⚠ 这与账本里 0.01294 **逐位相同** ⇒ **它本来就是 R=1 的数**")
    print("  ⚖⇒ **多跑几轮 launch，这个 p 一个位都不会动** ⇒ 该实验买不到新证据")
    print()

    print("【B】合成演示：14 题、观测 12/14、R=3（每题三次全同 = 没测到翻转）")
    recs = [("t%02d" % i, "rand", [1.0] * 3 if i < 12 else [-1.0] * 3)
            for i in range(14)]
    print("\n".join(render(analyze_arm(normalize(recs)["rand"], ALPHA, "rand"))))
    print()

    print("【C】合成演示：同 12/14，但每题**都有翻转**")
    recs2 = [("t%02d" % i, "rand", [1.0, 1.0, -1.0] if i < 12 else [-1.0] * 3)
             for i in range(14)]
    print("\n".join(render(analyze_arm(normalize(recs2)["rand"], ALPHA, "rand"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
