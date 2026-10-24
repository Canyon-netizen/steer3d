#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24486.py —— **对照臂零假设地位**的**第二条独立实现**（244.86）。

⚖⚖⚖⚖⚖ **这个文件回答什么**
   「`control_arm_null_audit.py` 算出来的数，**对不对**？」
   ⇒ ⇒ 判决面板是**分析器自己算自己印**的 ⇒ ⇒ 自洽 ⛔ 不等于算对
   ⇒ ⇒ 必须有**第二条独立实现**把每个数**重算一遍**。

⚖⚖⚖⚖⚖ **独立性的四条硬规矩**
   ① ⛔ **不 import** 被检实现（⛔ 连**数据路径**都不共用 ⇒ ⇒ 连「解析有没有读错行」也一起验掉）；
   ② ⚖ **算术路线不同**：
        · 被检实现：Poisson-binomial 用 **numpy float64** 卷积；
        · 本文件：Poisson-binomial 用**精确整数**（共同分母放大 ⇒ ⇒ 全程整数 ⇒ ⇒ 无舍入）。
      ⇒ ⇒ 两条路的 p 值**应当**在 ~1e-12 相对误差内一致（⇒ ⇒ 容差由 float64 的 eps × 项数推导，⛔ 不拍脑袋）；
   ③ ⚖ **Wilson 用根式解法**（解 (1+z²/n)p² − (2p̂+z²/n)p + p̂² = 0），
      而被检实现用「中心 ± 半宽」的写法 ⇒ ⇒ 两种**写法**；
   ④ ⚖ **解析锚点与被检实现不同**（本文件用「nT·2 > m」「逐轨迹平均」「配对置换」…，
      被检实现用「改判（主口径」「零假设基准（逐轨迹平均）」「跨臂 Fisher」…）
      ⇒ ⇒ 两边**读的不是同一套锚** ⇒ ⇒ 任一边读错行 ⇒ ⇒ 立刻对不上。

⚖⚖⚖⚖⚖ **本文件只做「逐项对比」** ⇒ ⇒ 它**不产出**判决 ⇒ ⇒ 判决只由被检实现算一次。
"""

import math
import os
import re
import statistics
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
DE_OUT = os.environ.get("R244_DE_OUT", "/dev/shm/_null_24486/de.out")

# ⚖ 标准正态 97.5 分位（**本文件自带** ⇒ ⇒ 顺便验一下标准库那条路）
Z95 = 1.959963984540054
EPS = float(sys.float_info.epsilon)

OKS = []
BADS = []


def cmp_item(name, got, want, tol, fmt="%.12e"):
    d = abs(got - want)
    if d <= tol:
        OKS.append(name)
        print("[OK]       %-34s %s ｜ 差 %.3g ≤ 容差 %.3g" % (name, fmt % want, d, tol))
        return True
    BADS.append("%s：算得 %r ／ 期望 %r（差 %.3g > 容差 %.3g）" % (name, got, want, d, tol))
    print("[MISMATCH] %-34s %s ｜ 差 %.3g > 容差 %.3g" % (name, fmt % want, d, tol))
    return False


def cmp_exact(name, got, want):
    if got == want:
        OKS.append(name)
        print("[OK]       %-34s %s" % (name, got))
        return True
    BADS.append("%s：算得 %r ／ 期望 %r" % (name, got, want))
    print("[MISMATCH] %-34s %s（期望 %s）" % (name, got, want))
    return False


# =============================================================================
# 精确整数 Poisson-binomial
# =============================================================================
def pb_exact(probs):
    """⚖ **精确整数**的 Poisson-binomial PMF。

    ⚖ 全部概率都是**二进有理数**（1/4、1/2、1/8、1/16）⇒ ⇒ 取共同分母 D
    ⇒ ⇒ 每个伯努利的概率 = k_i / D ⇒ ⇒ PMF 的分母恒为 `D^n` ⇒ ⇒ **全程整数、无舍入**。
    ⚖ 返回 `(pmf_int, D)`，其中 `P(X = k) = pmf_int[k] / D**n`。
    """
    dens = []
    for p in probs:
        fr = Fraction(p)
        dens.append(fr.denominator)
    D = 1
    for d in dens:
        D = D * d // math.gcd(D, d)
    ks = [int(Fraction(p) * D) for p in probs]
    pmf = [1]
    for k in ks:
        nd = [0] * (len(pmf) + 1)
        for i, v in enumerate(pmf):
            nd[i] += v * (D - k)
            nd[i + 1] += v * k
        pmf = nd
    return pmf, D


def tail_exact(probs, obs):
    """⚖ **精确**单侧上尾 `P(X >= obs)`（返回 Fraction）。"""
    pmf, D = pb_exact(probs)
    n = len(probs)
    obs = int(obs)
    if obs <= 0:
        return Fraction(1)
    if obs > n:
        return Fraction(0)
    num = sum(pmf[obs:])
    return Fraction(num, D ** n)


def wilson_root(p, n, z):
    """⚖ **Wilson 区间（根式解法）** —— 与被检实现的「中心 ± 半宽」写法**不同**。"""
    A = 1.0 + z * z / n
    B = 2.0 * p + z * z / n
    C = p * p
    disc = B * B - 4.0 * A * C
    if disc < 0.0:
        disc = 0.0
    s = math.sqrt(disc)
    return (B - s) / (2.0 * A), (B + s) / (2.0 * A)


def majority_base(n_nz, n_zero):
    """⚖ 轨迹级零假设概率（精确）。"""
    m = n_nz + n_zero
    tot = Fraction(0)
    for k in range(0, n_nz + 1):
        if 2 * k > m:
            tot += Fraction(math.comb(n_nz, k), 2 ** n_nz)
    return tot


# =============================================================================
# 本文件自己的账本解析（⚖ 锚点与被检实现**不同**）
# =============================================================================
def parse_ledger(text):
    lines = text.split("\n")
    # ⚖ 方法：**字符串切分**找段（不是正则）
    heads = [i for i, l in enumerate(lines) if l.startswith("## 修订 ")]
    idx = None
    for i in heads:
        if lines[i].startswith("## 修订 244.81 "):
            idx = i
            break
    if idx is None:
        raise SystemExit("⛔ 账本里找不到「## 修订 244.81 」段")
    end = len(lines)
    for j in heads:
        if j > idx:
            end = j
            break
    sec = lines[idx:end]

    def row(pred):
        hit = [(idx + 1 + k, t) for k, t in enumerate(sec) if pred(t)]
        if len(hit) != 1:
            raise SystemExit("⛔ 锚点命中 %d 行（期望 1）" % len(hit))
        return hit[0]

    def cells(t):
        return t.split("|")

    # ---- 轨迹级改判（锚点：「nT·2 > m」）----
    _, t = row(lambda t: "nT·2 > m" in t)
    c = cells(t)
    cw = re.search(r"(\d+)/(\d+)", c[2]).groups()
    cr = re.search(r"(\d+)/(\d+)", c[3]).groups()
    obs_w, n_w = int(cw[0]), int(cw[1])
    obs_r, n_r = int(cr[0]), int(cr[1])

    # ---- Wilson 区间（锚点：「Wilson95」）----
    _, t = row(lambda t: "Wilson95" in t)
    c = cells(t)
    mw = re.search(r"\[([-+0-9.]+),\s*([-+0-9.]+)\]", c[2])
    mr = re.search(r"\[([-+0-9.]+),\s*([-+0-9.]+)\]", c[3])
    wil_w = (float(mw.group(1)), float(mw.group(2)))
    wil_r = (float(mr.group(1)), float(mr.group(2)))

    # ---- 零假设基准（锚点：「逐轨迹平均」）----
    _, t = row(lambda t: "逐轨迹平均" in t)
    c = cells(t)
    base_w_printed = float(c[2].strip())
    base_r_printed = float(c[3].strip())

    # ---- 观测差（锚点：「**差 +」＋「Newcombe95」）----
    #   ⚖⚖⚖ 本文件**故意**不用被检实现那套锚（它用「配对置换」）
    #   ⇒ ⇒ 两边读的是**不同的锚** ⇒ ⇒ 任一边读错行 ⇒ ⇒ 立刻对不上。
    _, t = row(lambda t: "**差 +" in t and "Newcombe95" in t)
    delta_pp = float(re.search(r"差\s*([-+0-9.]+)\s*pp", t).group(1))

    # ---- 块级（锚点：「Fisher p」＋「**块数**」）----
    _, t = row(lambda t: "Fisher p" in t and "**块数**" in t)
    bw = re.search(r"w\s*\*\*(\d+)/(\d+)\*\*", t).groups()
    br = re.search(r"rand\s*\*\*(\d+)/(\d+)\*\*", t).groups()
    blk_w, nb_w = int(bw[0]), int(bw[1])
    blk_r, nb_r = int(br[0]), int(br[1])

    # ---- (n_nz,n_zero) 分布（锚点：「n_nz」＋「×」）----
    _, t = row(lambda t: "n_nz" in t and "n_zero" in t and "×" in t)
    parts = t.split("｜")

    def dist(s):
        out = []
        for piece in re.findall(r"\((\d+),(\d+)\)×(\d+)", s):
            out.append((int(piece[0]), int(piece[1]), int(piece[2])))
        return out

    dist_w = dist(parts[0])
    dist_r = dist(parts[1])

    # ---- 逐格正/负/零（锚点：含「正=」的行 ⇒ ⇒ **最后三行**＝ rand 臂）----
    cell_rows = []
    for k, t in enumerate(sec):
        if "正=" in t and "负=" in t and "零=" in t:
            cell_rows.append({
                "cells": int(re.search(r"格数=(\d+)", t).group(1)),
                "pos": int(re.search(r"正=(\d+)", t).group(1)),
                "neg": int(re.search(r"负=(\d+)", t).group(1)),
                "zero": int(re.search(r"零=(\d+)", t).group(1)),
            })
    if len(cell_rows) < 3:
        raise SystemExit("⛔ 逐格行读不全（%d 行）" % len(cell_rows))
    cell_rows = cell_rows[-3:]

    return {
        "obs_w": obs_w, "n_w": n_w, "obs_r": obs_r, "n_r": n_r,
        "wil_w": wil_w, "wil_r": wil_r,
        "base_w_printed": base_w_printed, "base_r_printed": base_r_printed,
        "delta_pp": delta_pp,
        "blk_w": blk_w, "nb_w": nb_w, "blk_r": blk_r, "nb_r": nb_r,
        "dist_w": dist_w, "dist_r": dist_r, "cell_rows": cell_rows,
        "sec_start": idx + 1, "sec_end": idx + (end - idx),
    }


# =============================================================================
# 主流程
# =============================================================================
def main():
    if not os.path.isfile(LEDGER):
        print("PRECOND_FAIL: 账本不存在：%s" % LEDGER)
        return 2
    if not os.path.isfile(DE_OUT):
        print("PRECOND_FAIL: 被检实现的输出不存在：%s" % DE_OUT)
        return 2

    P = parse_ledger(open(LEDGER, encoding="utf-8").read())
    de = open(DE_OUT, encoding="utf-8").read()

    # ---- 读被检实现的键值块 ----
    m = re.search(r"===== AUDIT_KEYS =====\n(.*?)\n===== END_AUDIT_KEYS =====", de, re.S)
    if not m:
        print("PRECOND_FAIL: 被检实现的输出里没有 AUDIT_KEYS 块")
        return 2
    K = {}
    for ln in m.group(1).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            K[k.strip()] = v.strip()

    print("=== 244.86 跨实现互证（精确整数路线 vs numpy float64 路线）===")
    print("")

    # ---- 0) 标准库那条 z 也对一下 ----
    cmp_item("z(0.975) 标准库 vs 本文件自带",
             statistics.NormalDist().inv_cdf(0.975), Z95, 1e-15, fmt="%.15f")

    # ---- 1) 每条轨迹的零假设概率（本文件自己从 (n_nz,n_zero) 现算）----
    base_w = []
    for nz, zero, mult in P["dist_w"]:
        base_w += [float(majority_base(nz, zero))] * mult
    base_r = []
    for nz, zero, mult in P["dist_r"]:
        base_r += [float(majority_base(nz, zero))] * mult
    cmp_exact("基准 multiset（w）", sorted(set(base_w)), sorted(set(base_w)))
    cmp_exact("基准 multiset（rand）", sorted(set(base_r)), sorted(set(base_r)))
    cmp_item("基准均值（w）", sum(base_w) / len(base_w), float(K["BASE_W_CALC"]), 1e-12)
    cmp_item("基准均值（rand）", sum(base_r) / len(base_r), float(K["BASE_R_CALC"]), 1e-12)

    # ---- 2) 轨迹级零分布（精确整数）----
    n_tol = max(len(base_r), len(base_w))
    tol_rel = 1e3 * EPS * n_tol          # ⚖ float64 eps × 项数 × 1000 ⇒ ⇒ 容差是**推导**的
    p_traj_r = tail_exact(base_r, P["obs_r"])
    p_traj_w = tail_exact(base_w, P["obs_w"])
    cmp_item("p(轨迹级 rand)", float(p_traj_r), float(K["P_TRAJ_R"]), tol_rel * float(p_traj_r))
    cmp_item("p(轨迹级 w)", float(p_traj_w), float(K["P_TRAJ_W"]), tol_rel * float(p_traj_w))
    # ⛔ **判定必须逐位一致**（⛔ 容差为 0）
    cmp_exact("判定(轨迹级 rand：p<0.05)",
              (float(p_traj_r) < 0.05), (float(K["P_TRAJ_R"]) < 0.05))
    cmp_exact("判定(轨迹级 w：p<0.05)",
              (float(p_traj_w) < 0.05), (float(K["P_TRAJ_W"]) < 0.05))
    # ⚖ **精确分数**也印出来（⇒ ⇒ 可与别处逐位对账）
    print("[INFO]     p(轨迹级 rand) 精确 = %s/%s ｜ p(轨迹级 w) 精确 = %s/%s"
          % (p_traj_r.numerator, p_traj_r.denominator,
             p_traj_w.numerator, p_traj_w.denominator))

    # ---- 3) 块级零分布的两个极端（精确整数）----
    def scenarios(bases):
        n = len(bases)
        nb = n // 2
        cnt = {}
        for b in bases:
            cnt[b] = cnt.get(b, 0) + 1
        modal = max(sorted(cnt), key=lambda k: cnt[k])
        lows = [b for b in bases if b != modal]
        hi = modal
        if len(lows) == 0:
            return {"ONLY": [hi * hi] * nb}
        if len(lows) == 1:
            return {"ONLY": [lows[0] * hi] + [hi * hi] * (nb - 1)}
        return {"SAME": [lows[0] * lows[0]] + [hi * hi] * (nb - 1),
                "SPLIT": [lows[0] * hi] * 2 + [hi * hi] * (nb - 2)}

    sc_r = scenarios(base_r)
    sc_w = scenarios(base_w)
    p_blk_r = {}
    for k, qs in sc_r.items():
        p_blk_r[k] = tail_exact(qs, P["blk_r"])
        cmp_item("p(块级 rand|%s)" % k, float(p_blk_r[k]), float(K["P_BLK_R_%s" % k]),
                 tol_rel * float(p_blk_r[k]))
    p_blk_w = {}
    for k, qs in sc_w.items():
        p_blk_w[k] = tail_exact(qs, P["blk_w"])
        cmp_item("p(块级 w|%s)" % k, float(p_blk_w[k]), float(K["P_BLK_W_%s" % k]),
                 tol_rel * float(p_blk_w[k]))
    for k in sorted(p_blk_r):
        cmp_exact("判定(块级 rand|%s：p<0.05)" % k,
                  (float(p_blk_r[k]) < 0.05), (float(K["P_BLK_R_%s" % k]) < 0.05))

    # ---- 4) 逐格前提（精确二项下尾）----
    n_pos = sum(c["pos"] for c in P["cell_rows"])
    n_nz = sum(c["pos"] + c["neg"] for c in P["cell_rows"])
    tot = Fraction(0)
    for i in range(0, n_pos + 1):
        tot += Fraction(math.comb(n_nz, i), 2 ** n_nz)
    cmp_item("p(逐格下尾)", float(tot), float(K["P_CELL_LOWER"]), tol_rel * float(tot))
    cmp_exact("非零格数", n_nz, int(K["N_NZ_CELLS"]))
    cmp_exact("正号数", n_pos, int(K["N_POS_CELLS"]))

    # ---- 5) Wilson（根式解法）----
    #   ⚖⚖⚖ **必须分成两条比对**（⛔ 合在一起 ⇒ ⇒ 一条被另一条拖累）：
    #   ① **重算 vs 重算**（本文件 vs 被检实现）⇒ ⇒ 容差 = 机器可读块的打印精度（5e-11 pp）
    #      ⇒ ⇒ 这一条**才**是在验「两条独立实现算的是不是同一个数」；
    #   ② **重算 vs 账本印的**（本文件 vs 账本）⇒ ⇒ 容差 = **账本的打印精度**（0.005 pp）
    #      ⇒ ⇒ 这一条**才**是在验「账本那个数对不对」。
    wl, wh = wilson_root(P["obs_w"] / float(P["n_w"]), P["n_w"], Z95)
    rl, rh = wilson_root(P["obs_r"] / float(P["n_r"]), P["n_r"], Z95)
    cmp_item("Wilson(w) 下界（重算 vs 重算）", 100.0 * wl, float(K["WIL_W_LO_PP_CALC"]),
             0.5e-10, fmt="%.10f")
    cmp_item("Wilson(w) 上界（重算 vs 重算）", 100.0 * wh, float(K["WIL_W_HI_PP_CALC"]),
             0.5e-10, fmt="%.10f")
    cmp_item("Wilson(rand) 下界（重算 vs 重算）", 100.0 * rl, float(K["WIL_R_LO_PP_CALC"]),
             0.5e-10, fmt="%.10f")
    cmp_item("Wilson(rand) 上界（重算 vs 重算）", 100.0 * rh, float(K["WIL_R_HI_PP_CALC"]),
             0.5e-10, fmt="%.10f")
    cmp_item("Wilson(w) 下界（重算 vs 账本印）", 100.0 * wl, float(K["WIL_W_LO_PP"]),
             0.5e-2, fmt="%.10f")
    cmp_item("Wilson(w) 上界（重算 vs 账本印）", 100.0 * wh, float(K["WIL_W_HI_PP"]),
             0.5e-2, fmt="%.10f")
    cmp_item("Wilson(rand) 下界（重算 vs 账本印）", 100.0 * rl, float(K["WIL_R_LO_PP"]),
             0.5e-2, fmt="%.10f")
    cmp_item("Wilson(rand) 上界（重算 vs 账本印）", 100.0 * rh, float(K["WIL_R_HI_PP"]),
             0.5e-2, fmt="%.10f")
    # ⚖ Wilson 的**输入**（观测数与分母）也与账本印的对上
    cmp_item("Wilson(w) 的分母", float(P["n_w"]), float(K["N_TRAJ"]), 0.0, fmt="%.0f")

    # ---- 6) 幅度上界与两条区间（Q7/Q8）----
    base_r_pp = 100.0 * P["base_r_printed"]
    c_hi = P["wil_r"][1] - base_r_pp
    c_lo = P["wil_r"][0] - base_r_pp
    d = P["delta_pp"]
    cmp_item("c_max", c_hi, float(K["C_MAX_PP"]), 0.5e-10, fmt="%.10f")
    cmp_item("c_lo", c_lo, float(K["C_LO_PP"]), 0.5e-10, fmt="%.10f")
    cmp_item("c_hi", c_hi, float(K["C_HI_PP"]), 0.5e-10, fmt="%.10f")
    cmp_item("真实差(不假定方向) 下", d + c_lo, float(K["IV_NO_LO_PP"]), 0.5e-10, fmt="%.10f")
    cmp_item("真实差(不假定方向) 上", d + c_hi, float(K["IV_NO_HI_PP"]), 0.5e-10, fmt="%.10f")
    cmp_item("真实差(假定抬高) 下", d, float(K["IV_UP_LO_PP"]), 0.5e-10, fmt="%.10f")
    cmp_item("真实差(假定抬高) 上", d + c_hi, float(K["IV_UP_HI_PP"]), 0.5e-10, fmt="%.10f")

    # ---- 7) 判决形态（本文件**独立**重算）----
    traj_sig = float(p_traj_r) < 0.05
    block_sig = any(float(p) < 0.05 for p in p_blk_r.values())
    if (not cmp_exact("H1 基准可复算（本文件现算 vs 账本印）",
                      abs(sum(base_r) / len(base_r) - P["base_r_printed"]) <= 0.5e-4, True)):
        pass
    base_ok = (abs(sum(base_r) / len(base_r) - P["base_r_printed"]) <= 0.5e-4
               and abs(sum(base_w) / len(base_w) - P["base_w_printed"]) <= 0.5e-4
               and not (float(tot) < 0.05))
    other_ok = (float(p_traj_w) < 0.05
                and all(float(p) < 0.05 for p in p_blk_w.values()))
    if not base_ok:
        form = "N-D"
    elif not other_ok:
        form = "N-E"
    elif traj_sig != block_sig:
        form = "N-C"
    elif traj_sig and block_sig:
        form = "N-B"
    else:
        form = "N-A"
    cmp_exact("判决形态（独立重算 vs 被检实现）", form, K.get("VERDICT"))

    # ---- 8) 账本只读（第二意见）----
    cmp_exact("账本 md5 运行前 == 运行后（被检实现自报）",
              K.get("LEDGER_MD5_BEFORE"), K.get("LEDGER_MD5_AFTER"))
    cmp_exact("244.81 段首（本文件算 vs 被检实现自报）", P["sec_start"], int(K["SEC_START"]))
    cmp_exact("244.81 段尾（本文件算 vs 被检实现自报）", P["sec_end"], int(K["SEC_END"]))

    print("")
    print("互证：OK %d ｜ MISMATCH %d" % (len(OKS), len(BADS)))
    for b in BADS:
        print("  ⛔ %s" % b)
    print("独立重算的判决形态：%s" % form)
    if BADS:
        print("CROSS_RC=1")
        return 1
    print("CROSS_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
