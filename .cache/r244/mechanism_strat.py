#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mechanism_strat —— 预登记主统计量按「机制」分层的**敏感性分析**（零 GPU）

## 这条在量什么

⚖ 修订 244.27.2 查出：阶梯的读出在**最后一个位置**，而注入位点由种子 0
⚖ 的置换均匀挑出 ⇒ 某些档**直接**扰动读出位置、某些只经**传播**。
⚖ ⇒ 「剂量—响应曲线」上的不同点**不是同一个机制的两个剂量**。

⚖⚠⚠⚠ **本脚本是事后（post-hoc）敏感性分析。**
⚖ ⛔ 它**不**替换预登记主统计量（244.14.5 / 244.15），
⚖ ⛔ 也**不**产出新的「结论」—— 它的唯一作用是回答一个问题：
⚖⚖ **主判决是不是只在某一层机制上成立？**
⚖ 若两层给出的判决不一致 ⇒ 主判决对该机制敏感，必须同报。

## 分层怎么定的

| 层 | 哪些档 |
|---|---|
| **直接** | `single`（注入位点按构造就是读出位置）、`all`（每处都注入）、以及位点集合**含** `n_eff-1` 的 `k` 档 |
| **传播** | 位点集合**不含** `n_eff-1` 的 `k` 档 |

⚖ 位点用 **AST 从真实探针源码抽取**的 `_k_positions` 算
⚖（与 `ladder_position_audit.py` 同一函数、同一路径、同一 seed=0），
⚖ ⛔ 不重实现、不手抄。

## 口径（与预登记一致，不许换）

⚖ 逐轨迹 = 该轨迹该层内 `up_mono_meas` 的**多数为真**，判据 `nT > nF`
⚖ ⇒ **平局算 False**（⚠ 这是约定不是规格，须同报）。
⚖ 跨臂 = 两臂通过率的 Fisher 精确双尾。

跑法：
    python3 mechanism_strat.py --reader … --w-log … --rand-log …
    python3 mechanism_strat.py --selftest
退出码：0 = 两层都算出来了；1 = 前置条件失败或某层算不出。
"""

import argparse
import importlib.util
import os
import sys
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, "..", "mutbak", "r227_kcurve.py")
AUDIT = os.path.join(HERE, "ladder_position_audit.py")
DEFAULT_CELLS = os.path.join(HERE, "warm_cells.txt")
DEFAULT_MAP = os.path.join(HERE, "n_eff_map.tsv")
DEFAULT_PROBE = os.path.join(HERE, "..", "mutbak", "r204_noise_probe.py")


class PrecondFail(Exception):
    pass


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fisher_two_sided(a, b, c, d):
    n = a + b + c + d
    if n == 0:
        return None
    r1, r2, c1 = a + b, c + d, a + c
    lo, hi = max(0, c1 - r2), min(r1, c1)
    probs = lambda x: (comb(r1, x) * comb(r2, c1 - x)) / float(comb(n, c1))
    p_obs = probs(a)
    p = sum(probs(x) for x in range(lo, hi + 1) if probs(x) <= p_obs * (1 + 1e-12))
    return min(1.0, p)


def sign_test_exact(k, n):
    """H0: P(正)=0.5 的精确双尾。⚠ n==0 ⇒ 返回 None（「未量到」，不是 1）。"""
    if n == 0:
        return None
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) * 2.0 / float(2 ** n)
    return min(1.0, tail)


def read_arm(rc, log, status, expect_cells, label):
    log_text = open(log, encoding="utf-8", errors="replace").read()
    st_text = open(status, encoding="utf-8", errors="replace").read()
    blocks = rc.parse_blocks(log_text)
    rows, alldone = rc.parse_status(st_text)
    if alldone is None:
        raise PrecondFail("%s 无 ALLDONE ⇒ 该轮可能没跑完" % status)
    if expect_cells is not None and len(blocks) != expect_cells:
        raise PrecondFail("%s 有 %d 块，期望 %d" % (log, len(blocks), expect_cells))
    cells = rc.join(blocks, rows)          # ⚖ 走读数器**同一条** join，不重实现
    arms = sorted({c["reading"].get("arm") for c in cells if c["reading"]})
    if len(arms) != 1:
        raise PrecondFail("%s 臂名混了 %r" % (log, arms))
    print("[%s] arm=%s  cells=%d" % (label, arms[0], len(cells)))
    return cells, arms[0]


def rung_kind(tid, scope, k, nmap):
    """⚖ 这个格属于哪一**档型**。

    ⚖⚠⚠⚠ 修订 244.29 查出的**混淆**：两层的档型分布**极不对称**
    ⚖   （实测：传播层 **100%** 是公式档；直接层 42% `single/all` + 42% 尾段档
    ⚖   + 15% 公式档）⇒ **「层」与「档型」完全混淆**。
    ⚖⚗ 所以「直接层效应更强」完全可以平凡地解释成
    ⚖   「尾段步进点与全注入本来就是更强的扰动」，⛔ 不需要机制叙事。
    ⚖⇒ 因此必须**再按档型去混淆**（只看公式档）才谈机制。
    """
    if scope in ("single", "all"):
        return "scope"
    ne = int(nmap[tid]["n_eff"])
    if k == ne * 3 // 4 or k == ne * 7 // 8:
        return "tail"          # r235 为「尾段逐档展开」加的步进点，⛔ 不是剂量档
    if k <= ne // 2:
        return "formula"
    return "other"


def stratify(rc, cells, nmap, kp):
    """逐格定层。⛔ `single`/`all` 按构造必是「直接」，不靠猜。"""
    out = []
    for c in cells:
        r = c["reading"]
        if r is None:
            continue
        sc = c["scope"]
        if sc == "single" or sc == "all":
            layer = "direct"
        elif sc == "k":
            tid, k = c["tid"], c["k"]
            if tid not in nmap:
                raise PrecondFail("%s 不在 n_eff_map 里 ⇒ 未量到" % tid)
            ne = int(nmap[tid]["n_eff"])
            pos = kp(ne, k, 0, True)
            if len(pos) != k:
                raise PrecondFail("%s k=%d 位点数 %d ≠ k" % (tid, k, len(pos)))
            layer = "direct" if (ne - 1) in pos else "prop"
        else:
            raise PrecondFail("口径 %r 未量到 ⇒ 拒绝猜它属于哪一层" % sc)
        out.append({"tid": c["tid"], "layer": layer,
                    "kind": rung_kind(c["tid"], sc, c["k"], nmap),
                    "up": r.get("up_mono_meas"), "scope": sc, "k": c["k"]})
    return out


def majority(rows):
    """⇒ (n_true, n_false, 是否多数为真)。⚖ 判据 `nT > nF` ⇒ **平局算 False**。"""
    vals = [bool(r["up"]) for r in rows if r["up"] is not None]
    nt, nf = sum(vals), len(vals) - sum(vals)
    return nt, nf, (nt > nf), len(vals)


def verdict_lines(d1, d2, p1, p2, n1=None, n2=None):
    """机制分层的判定。⇒ (lines, rc)。⚖ rc==1 ⇒ 方向相反，⛔ 必须停。

    ⚖⚠⚠ 修订 244.28：**幅度也要比**，⛔ 不能只看方向。
    ⚖⚗ 第一版只判「方向一致 ⇒ 通过」，那与「放宽判据让它变绿」同族：
    ⚖   实测方向确实一致（+64.3pp vs +14.3pp），但幅度差 4.5 倍、
    ⚖   两层 Fisher p 差 3 个数量级（0.00058 vs 0.70）⇒ 那个判定**太松了**。
    ⚖⚠ 「太松」的判据比「太严」更危险：它让一个只对一半成立的结论
    ⚖   带着 ✅ 通过。
    ⚖⚠⚠ 修订 244.29：加 `n1/n2`。**小 n 层的「无差异」是无力检出，不是「没有」**
    ⚖   （口径 B 的直接层实测只有 n=7，Fisher p=0.46）。
    """
    L = []
    L.append("  直接层两臂差 = %+.1f pp；传播层两臂差 = %+.1f pp"
             % (100 * d1, 100 * d2))
    same = (d1 > 0) == (d2 > 0)
    if not same:
        L.append("  ⛔⛔ 两层的**方向相反** ⇒ 主判决**对机制分层敏感**！")
        L.append("     ⇒ 引用 w vs rand 的通过率差时，⛔ 必须同报这个分层结果。")
        return L, 1
    if abs(d1) > 0 and abs(d2) > 0:
        L.append("  幅度比（较大层 / 较小层）= %.2f 倍"
                 % (max(abs(d1), abs(d2)) / min(abs(d1), abs(d2))))
    if p1 is not None and p2 is not None and min(p1, p2) > 0:
        L.append("  两层 Fisher p 之比 = %.3g 倍" % (max(p1, p2) / min(p1, p2)))
    big_amp = (abs(d1) > 0 and abs(d2) > 0
               and max(abs(d1), abs(d2)) / min(abs(d1), abs(d2)) >= 3.0)
    big_p = (p1 is not None and p2 is not None and min(p1, p2) > 0
             and max(p1, p2) / min(p1, p2) >= 100.0)
    L.append("  ✅ 两层的**方向**一致（都是 %s 侧更高）" % ("w" if d1 > 0 else "rand"))
    if big_amp or big_p:
        L.append("  ⚠⚠⚠ **但幅度差一个量级**（≥3 倍且/或两层 p 差 ≥100 倍）⇒")
        L.append("     ⇒ **效应几乎全部由其中一层承载**。引用通过率差时")
        L.append("     ⛔ **必须同报分层**，⛔ 不许只报合计那个数。")
        L.append("     ⚖ 弱的那一层（p 大）单独看**没有可检出的差异**；")
        L.append("        ⛔ 但那⛔ 不等于「那层没有效应」—— 该层每轨迹的格数更少，")
        L.append("        「多数为真」的噪声更大。**未量到 ≠ 无效应。**")
    else:
        L.append("  ⚖ 幅度也在同一量级 ⇒ 主判决不是单层机制的产物")
    ns = [x for x in (n1, n2) if x is not None]
    if ns and min(ns) < 10:
        L.append("  ⚠⚠⚠ **最小的那层只有 n=%d 条轨迹**（%s）⇒ "
                 % (min(ns), "、".join(str(x) for x in ns)))
        L.append("     ⛔ 小 n 层的「无差异」是**无力检出**，⛔ **不是**「那层没有效应」。")
        L.append("     ⇒ 上面那句「不是单层机制的产物」同样只在一个很弱的意义上成立。")
    L.append("  ⚖⚠ 再强调：⛔ 本脚本是事后分析，⛔ 不得用来替换预登记主统计量，")
    L.append("     也⛔ 不得只报对自己有利的那一层。")
    return L, 0


def tally(rows, layer, kinds=None):
    """⇒ (n_true, n_false, n_traj)。⚖ 判据 `nT > nF` ⇒ 平局算 False。"""
    sel = [r for r in rows if r["layer"] == layer
           and (kinds is None or r["kind"] in kinds)]
    nt = nf = n = 0
    for t in sorted({r["tid"] for r in sel}):
        sub = [r for r in sel if r["tid"] == t]
        a, b, m, cnt = majority(sub)
        if cnt == 0:
            continue
        nt += 1 if m else 0
        nf += 0 if m else 1
        n += 1
    return nt, nf, n


def run(rc, kp, w_log, w_st, r_log, r_st, expect_cells, nmap):
    w_cells, w_arm = read_arm(rc, w_log, w_st, expect_cells, "w")
    r_cells, r_arm = read_arm(rc, r_log, r_st, expect_cells, "rand")
    ws = stratify(rc, w_cells, nmap, kp)
    rs = stratify(rc, r_cells, nmap, kp)
    L = []
    L.append("=" * 74)
    L.append("按机制分层的敏感性分析（⛔ 事后，不替换预登记主统计量）")
    L.append("=" * 74)
    L.append("  口径：逐轨迹 = 该层内 `up_mono_meas` 多数为真，判据 nT > nF ⇒ 平局算 False")
    L.append("  分层：single/all 与含读出位置的 k 档 = **直接**；其余 k 档 = **传播**")

    # ⚖⚠⚠⚠ 修订 244.29：**层与档型完全混淆**，必须先把组成印出来。
    L.append("\n【混淆检查】两层的**档型**组成（⚠ 这一段决定下面的数能不能归因给机制）")
    comp = {}
    for layer in ("direct", "prop"):
        for kind in ("scope", "tail", "formula", "other"):
            comp[(layer, kind)] = sum(1 for r in ws + rs
                                       if r["layer"] == layer and r["kind"] == kind)
    for layer in ("direct", "prop"):
        tot = sum(v for (l, _), v in comp.items() if l == layer) or 1
        L.append("  %-4s 共 %d 格：" % ("直接" if layer == "direct" else "传播", tot))
        for kind, lab in (("scope", "single/all"), ("tail", "尾段档 3/4,7/8"),
                          ("formula", "公式档 ≤1/2"), ("other", "其它")):
            v = comp[(layer, kind)]
            L.append("      %-16s %3d  (%.1f%%)" % (lab, v, 100.0 * v / tot))
    L.append("  ⚖⚠⚠ **传播层几乎 100% 是公式档；直接层大半是尾段步进点与全注入**")
    L.append("     ⇒ 「层」与「档型」**混淆** ⇒ 「直接层效应更强」可以平凡地解释成")
    L.append("     「尾段步进点/全注入本来就是更强的扰动」，⛔ **不必诉诸机制**。")
    L.append("     ⇒ 所以下面给**两个口径**：全部档 / 只公式档（去混淆）。")

    def block(title, kinds):
        L.append("\n【%s】" % title)
        res = {}
        for label, rows in (("w", ws), ("rand", rs)):
            res[label] = {}
            for layer in ("direct", "prop"):
                nt, nf, n = tally(rows, layer, kinds)
                res[label][layer] = {"nt": nt, "nf": nf, "n": n,
                                     "rate": (nt / n) if n else None}
        for layer in ("direct", "prop"):
            a, b = res["w"][layer], res["rand"][layer]
            L.append("  ── %s 层" % ("直接" if layer == "direct" else "传播"))
            if a["n"] == 0 or b["n"] == 0:
                L.append("     ⛔ 未量到：有一臂在该层没有轨迹（n=0）⇒ 不许读成「无差异」")
                continue
            L.append("     w    %d/%d = %.4f" % (a["nt"], a["n"], a["rate"]))
            L.append("     rand %d/%d = %.4f" % (b["nt"], b["n"], b["rate"]))
            L.append("     差 = %+.1f 个百分点" % (100 * (a["rate"] - b["rate"])))
            p = fisher_two_sided(a["nt"], a["nf"], b["nt"], b["nf"])
            L.append("     Fisher 双尾 p=%s" % ("未量到" if p is None else "%.6g" % p))
        return res

    per_all = block("口径 A：全部档（**与档型混淆**）", None)
    per_fmt = block("口径 B：只公式档（**已按档型去混淆** ⛔ 这才是谈机制的干净口径）",
                    {"formula"})
    per_tail = block("口径 C：只尾段档（3/4、7/8 —— r235 为「尾段逐档展开」加的**步进点**，"
                     "⛔ **不是**剂量档）", {"tail"})
    per_scope = block("口径 D：只 single/all（**端点**，⛔ 同样不是剂量档）", {"scope"})
    per = per_fmt
    L.append("\n  ⚖⚠ 判定用**口径 B**（去混淆）；A/C/D 只作对照，⛔ 不得单独引用。")
    L.append("  ⚖⚠⚠ **只有口径 D** 与 244.23 的轨迹级 Δ 符号检验**计数相同**"
             "（13/1 vs 5/9、p=0.0044241）")
    L.append("     ⚠⚠ 而那**不是恒等** —— 逐轨迹比对：single/all 多数 vs `drift_khi_all` 符号，")
    L.append("     w 一致 **12/14**、rand 一致 **8/14** ⇒ 二者**重叠但不同**。")
    L.append("     ⇒ ⛔ 把口径 D 的 p 当作 Δ 检验的**独立佐证**就是**重复计数**。")
    L.append("     ⚖⚠⚠ 口径 C（尾段档）与 244.23 的 Δ 检验**不是**同一件事："
             "它是 %d/%d vs %d/%d、p=%.6g。"
             % (per_tail["w"]["direct"]["nt"], per_tail["w"]["direct"]["n"],
                per_tail["rand"]["direct"]["nt"], per_tail["rand"]["direct"]["n"],
                fisher_two_sided(per_tail["w"]["direct"]["nt"],
                                 per_tail["w"]["direct"]["nf"],
                                 per_tail["rand"]["direct"]["nt"],
                                 per_tail["rand"]["direct"]["nf"]) or float("nan")))
    L.append("     ⚖ 而且尾段档的**传播层 n=0**（它们必然直接扰动读出位置）⇒ **未量到**。")
    if per["w"]["direct"]["n"] == 0 or per["w"]["prop"]["n"] == 0 or \
            per["rand"]["direct"]["n"] == 0 or per["rand"]["prop"]["n"] == 0:
        L.append("\n【判定】主判决对机制分层是否敏感")
        L.append("  ⚠ 去混淆口径里有一层没有轨迹（n=0）⇒ **未量到**")
        L.append("     ⛔ 不许说「一致」也⛔ 不许说「不一致」")
        return "\n".join(L), 1
    d1 = per["w"]["direct"]["rate"] - per["rand"]["direct"]["rate"]
    d2 = per["w"]["prop"]["rate"] - per["rand"]["prop"]["rate"]
    p1 = fisher_two_sided(per["w"]["direct"]["nt"], per["w"]["direct"]["nf"],
                          per["rand"]["direct"]["nt"], per["rand"]["direct"]["nf"])
    p2 = fisher_two_sided(per["w"]["prop"]["nt"], per["w"]["prop"]["nf"],
                          per["rand"]["prop"]["nt"], per["rand"]["prop"]["nf"])
    L.append("\n【判定】主判决对机制分层是否敏感（口径 B）")
    lines, vrc = verdict_lines(d1, d2, p1, p2,
                                per["w"]["direct"]["n"], per["w"]["prop"]["n"])
    L.extend(lines)
    return "\n".join(L), vrc


def _fmtp(p):
    return "未量到" if p is None else "%.6g" % p


def selftest():
    T = []

    def ck(name, fn):
        try:
            fn()
            T.append((name, "PASS", ""))
        except AssertionError as e:
            T.append((name, "FAIL", str(e) or "断言失败"))
        except Exception as e:
            T.append((name, "FAIL", "%s: %s" % (type(e).__name__, e)))

    # M1 绿：平局算 False（口径约定，不是规格）
    def m1():
        rows = [{"up": True}, {"up": False}]
        assert majority(rows) == (1, 1, False, 2), majority(rows)
        rows2 = [{"up": True}, {"up": True}, {"up": False}]
        assert majority(rows2) == (2, 1, True, 3), majority(rows2)
    ck("M1 绿：平局算 False（nT > nF）；空层不进分母", m1)

    # M2 红：空层 ⇒ 未量到，不是 0
    def m2():
        nt, nf, ok, n = majority([{"up": None}, {"up": None}])
        assert n == 0, n
    ck("M2 红：读数为 None 的格不进分母（n=0 是「未量到」，不是 0）", m2)

    # M3 绿：Fisher 与**独立暴力实现**逐条吻合（空表返回 None）
    # ⚖⚠ 必须有参照实现，否则「把 p 直接返回 1.0」这种变异**抓不到**
    # ⚖   （台架第一轮就报了 N5「存活」，因为当时的 M3 只查了空表）。
    def m3():
        from fractions import Fraction

        def brute(a, b, c, d):
            n = a + b + c + d
            r1, r2, c1 = a + b, c + d, a + c
            lo, hi = max(0, c1 - r2), min(r1, c1)
            pr = lambda x: (Fraction(comb(r1, x) * comb(r2, c1 - x),
                                     comb(n, c1)))
            p_obs = pr(a)
            return min(1.0, sum(pr(x) for x in range(lo, hi + 1)
                                 if pr(x) <= p_obs))
        for tab in ((10, 3, 1, 11), (14, 0, 9, 5), (5, 9, 5, 9), (1, 1, 1, 1)):
            got = fisher_two_sided(*tab)
            exp = brute(*tab)
            assert got is not None and abs(got - exp) < 1e-9, (tab, got, exp)
        assert fisher_two_sided(0, 0, 0, 0) is None, "空表必须返回 None（未量到）"
    ck("M3 绿：Fisher 与独立暴力实现吻合；空表返回 None", m3)

    # M4 绿：精确符号检验的边界
    def m4():
        assert abs(sign_test_exact(14, 14) - 2 / 16384.0) < 1e-12, sign_test_exact(14, 14)
        assert abs(sign_test_exact(7, 14) - 1.0) < 1e-12, sign_test_exact(7, 14)
        assert sign_test_exact(0, 0) is None
    ck("M4 绿：精确符号检验 全同=2/2^n、7:14=1.0、n=0 未量到", m4)

    # M5 红：方向相反 ⇒ 必须 rc=1（这是唯一能让流水线停的那一种）
    def m5():
        lines, rc = verdict_lines(0.10, -0.05, 0.01, 0.5, 14, 14)
        assert rc == 1, rc
        assert any("方向相反" in x for x in lines), lines
    ck("M5 红：两层方向相反 ⇒ rc=1 且点名「方向相反」", m5)

    # M6 绿：方向一致但幅度差 4.5 倍 / p 差 1210 倍 ⇒ **必须喊出来**
    # ⚖⚠ 这就是实测那组数（+64.3pp vs +14.3pp、p 0.00058 vs 0.70）。
    # ⚖⚗ 第一版判定只说「方向一致 ⇒ 通过」，本条会把它抓出来。
    def m6():
        lines, rc = verdict_lines(0.643, 0.143, 0.00058, 0.704, 14, 14)
        assert rc == 0, rc
        assert any("幅度差一个量级" in x for x in lines), lines
        assert any("必须同报分层" in x for x in lines), lines
    ck("M6 绿：方向一致但幅度差一个量级 ⇒ 必须喊出「必须同报分层」", m6)

    # M7 绿：方向一致且幅度同量级 ⇒ 不许乱喊
    def m7():
        lines, rc = verdict_lines(0.30, 0.28, 0.04, 0.06, 14, 14)
        assert rc == 0, rc
        assert not any("幅度差一个量级" in x for x in lines), lines
        assert any("同一量级" in x for x in lines), lines
    ck("M7 绿：幅度同量级 ⇒ 不许误喊「必须同报分层」（否则就是噪声）", m7)

    # M8 绿：**只**靠幅度差（p 两层相等）也必须喊
    # ⚖⚠⚠ 这条是修台架第一轮报出的「N1/N6 存活」：原来 M6 只验
    # ⚖   `big_amp OR big_p` 那个**或** ⇒ 单独废掉任一支仍然 PASS
    # ⚖   ⇒ 两个分支**各自都没被独立承重**。⇒ 必须各钉一条。
    def m8():
        lines, rc = verdict_lines(0.643, 0.143, 0.05, 0.05, 14, 14)   # p 相等 ⇒ 只可能靠幅度
        assert rc == 0, rc
        assert any("幅度差一个量级" in x for x in lines), lines
    ck("M8 绿：只有幅度差（两层 p 相等）⇒ 仍必须喊「必须同报分层」", m8)

    # M9 绿：**只**靠 p 差（幅度同量级）也必须喊
    def m9():
        lines, rc = verdict_lines(0.30, 0.29, 0.00058, 0.704, 14, 14)
        assert rc == 0, rc
        assert any("幅度差一个量级" in x for x in lines), lines
    ck("M9 绿：只有 p 差（幅度同量级）⇒ 仍必须喊「必须同报分层」", m9)

    npass = sum(1 for _, s, _ in T if s == "PASS")
    for name, s, msg in T:
        print("[%s] %s%s" % (s, name, ("  ← " + msg) if msg else ""))
    print("mechanism_strat --selftest: %d/%d" % (npass, len(T)))
    return 0 if npass == len(T) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", default=READER)
    ap.add_argument("--w-log")
    ap.add_argument("--w-status")
    ap.add_argument("--rand-log")
    ap.add_argument("--rand-status")
    ap.add_argument("--map", dest="map_path", default=DEFAULT_MAP)
    ap.add_argument("--expect-cells", type=int, default=137)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    need = (args.w_log, args.w_status, args.rand_log, args.rand_status)
    if not all(need):
        ap.error("需要 --w-log/--w-status/--rand-log/--rand-status，或 --selftest")
    rc = _load(args.reader, "r227_kcurve")
    aud = _load(AUDIT, "ladder_position_audit")
    kp, _ = aud.load_k_positions(DEFAULT_PROBE)
    nmap = aud.read_map(args.map_path)
    try:
        txt, rc_ = run(rc, kp, args.w_log, args.w_status, args.rand_log,
                       args.rand_status, args.expect_cells, nmap)
        print(txt)
        return rc_
    except PrecondFail as e:
        print("⛔ PRECOND_FAIL: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
