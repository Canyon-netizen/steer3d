#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arm_contrast_audit.py —— 「两臂层内梯度有没有差异」的**配对**判据（零 GPU）

🔴 **这个工具要回答什么**
  244.30 起账本里挂着一条 🔴：
    「rand 臂传播层出现方向性剂量梯度（**12/14** 正号，p=0.0129，中位 +0.568），
      而 w 臂没有（9/14，p=0.424）⇒ **负控比处理臂更强**」
  ⚖⚠⚠⚖ 那个结论的来源是**比较两个 p 值的大小**（0.0129 小 vs 0.424 大）。
  ⛔ **两个 p 值的大小差异不是两臂差异的证据** —— 它只是两个独立的
     「各自 vs 零假设」的结论。把它们摆在一起看大小，等于
     「A 组显著、B 组不显著 ⇒ A 组效应更大」，⛔ 这条推理形式上就不成立。
  ⚗⇒ 正确做法：两臂跑的是**同一批轨迹**（同一 (tid, 覆盖率) 阶梯，
     `dose_axis_audit.ladder_same` 的 J4 已经钉过）⇒ 这是**配对**设计，
     ⇒ 差异要用**配对**检验问，不能用两个独立符号检验摆在一起比。

⚖⚖ **本工具算三个量，各有各的适用面**
  ⚖ **McNemar 精确（只用不一致对）**：问「符号**模式**是否不同」。
     ⛔ **只看不一致对**（一正一负的那些）——
     一致对（都正 / 都负）在配对设计里**不携带**差异信息。
     ⚠⚠⚠ 作者第一版把**一致对**（both+/both−）当成 b、c 代进去，
        在真实数据上给出 p=0.0156 —— ⚖⚠ 那是**假的显著**。
        ⛔ 正确的 discordant 是 2 vs 4 ⇒ p=0.6875。自检 **C1** 用一个
        能区分两种算法的夹具把这个坑钉死。
  ⚖ **Wilcoxon 符号秩精确**：问「rho 的**幅度**是否不同」。
     ⚖⚠ 它对**分布对称**有假设，n 小的时候比 McNemar 更容易吃到极端值。
  ⚖ **两个独立符号检验的 p**：⛔ **只作为「各自 vs 零」的读数印出**，
     ⛔ **永远不参与**「两臂有差异」这个判断。

⚖⚠⚠ **这条工具产出的任何数字都是事后分析**
  ⛔ 它⛔ **不替换**预登记统计量（w 12/14=0.8571 / rand 6/14=0.4286 /
  Fisher 0.0460717），⛔ 也不改任何判决。⚗⇒ 报告里必须显著标注这一点。

⛔ 本工具：⛔ 不改任何真文件；⛔ 不跑批；⛔ 只读两份已有日志。
⚖⚠ 报告里所有数**从数据算出来**再印，⛔ 不写死。
"""

import argparse
import ast
import itertools
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"

# ⚖ 两臂的日志（⛔ 默认值是**相对仓库根**的路径，跑的时候要在根目录）
W_LOG = ".cache/r244/w_new.log"
RAND_LOG = ".cache/r244/rand_new.log"

ALPHA = 0.05


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 检验
def mcnemar_exact(b, c):
    """⚖ **McNemar 精确**（双侧）：b、c 是**不一致对**的两格。

    ⚖⚠⚠⚠⛔ **b、c 必须是不一致对**，不是一致对（both+/both−）。
      一致对在配对设计里**不携带**差异信息。
      ⚖⚠ 第一版把 both+/both− 传进来 ⇒ 真实数据上给出 p=0.0156 的
         **假显著**（正确值 0.6875）。自检 C1 用能区分两种算法的夹具钉死。
    ⚖⚠ discordant 总数为 0 ⇒ **没有证据** ⇒ 返回 **1.0**，
      ⛔ 绝不能返回 0.0（「一个不一致对都没有」被当成「差异极显著」）。
    """
    b, c = int(b), int(c)
    if b < 0 or c < 0:
        raise HardFail("不一致对计数不能为负：b=%d c=%d" % (b, c))
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n)


def wilcoxon_exact(deltas):
    """⚖ **Wilcoxon 符号秩精确**（双侧），并列取中秩。

    ⚖⚠⚠ **零差必须剔出分母**并单独报数：
       保留它会让 n 虚高、p 变小 ⇒ 把「没量到」算成「有证据」。
    ⚖⚠⚠⚠ 零差**全部**剔光 ⇒ 无可检验的差 ⇒ 返回 **1.0**（⛔ 不是 0.0）。
    """
    nz = [float(d) for d in deltas if float(d) != 0.0]
    n = len(nz)
    if n == 0:
        return 1.0, n
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nz[order[j + 1]]) == abs(nz[order[i]]):
            j += 1
        mid = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            ranks[order[t]] = mid
        i = j + 1
    total = n * (n + 1) / 2.0
    w_pos = sum(r for r, d in zip(ranks, nz) if d > 0)
    obs = min(w_pos, total - w_pos)
    hit = 0
    for bits in itertools.product((0, 1), repeat=n):
        s = sum(r for r, b in zip(ranks, bits) if b)
        if min(s, total - s) <= obs + 1e-12:
            hit += 1
    return min(1.0, hit / float(2 ** n)), n


def sign_binom(pos, n):
    """⚖ 单臂符号检验（复算用，⛔ 不参与「两臂有差异」的判断）。"""
    if n <= 0:
        return None
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(0, min(pos, n - pos) + 1))
               / 2.0 ** n)


def pval_gap_is_not_evidence(p_a, p_b):
    """⚖⚖ **恒返回 False 的判决闸**，且它**必须**恒返回 False。

    🔴 这个函数存在的唯一目的：把「两个 p 值大小不同 ⇒ 两臂有差异」
       这条**推理形式本身**钉成**不可用**。
    ⚖ 它⛔ 不做任何统计判断，只是一条被代码化的**推理禁令**：
       ⛔ 报告里**永远**不许由 `p_a` 与 `p_b` 的大小推出差异结论。
    ⚖⚠⚠⚠ 恒 False 在这里**不是缺陷** —— 它不是判据，是**禁令**；
       ⛔ 判据（McNemar / Wilcoxon）才是要能红的那些。
       ⚖ 自检 **C4** 会证明「真的存在一组数据，两个 p 值差得很远
       而配对检验不显著」⇒ 禁令不是空话。
    """
    return False


# --------------------------------------------------------------- 取数
def _load_dose_axis():
    import importlib.util
    path = os.path.join(HERE, "dose_axis_audit.py")
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    spec = importlib.util.spec_from_file_location("dose_axis_for_contrast", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def unwrap(m, tag):
    """⚖ `dose_axis_audit.within_mech` 返回的是 `{tid: (rho, 档数)}` —— **元组**。

    ⚖⚠⚖⚖ 第一版自检的夹具直接传裸 float，于是**夹具与生产形状不同**：
       自检 7/7 全绿，⛔ 而真实数据一进去就 `TypeError` 崩掉。
       ⛔ 夹具必须走**和生产同一段代码**，否则自检验的是另一个对象。
    ⚗⇒ 显式解包，并**拒收**任何别的形状。
    """
    out = {}
    for t, v in m.items():
        if not (isinstance(v, tuple) and len(v) == 2):
            raise HardFail("%s 的 %s 形状不是 (rho, 档数)：%r ⇒ ⛔ 拒读"
                           % (tag, t, v))
        out[t] = v[0]
    return out


def contrast(pw_raw, pr_raw, tag_w="w 臂", tag_r="rand 臂"):
    """⚖ **核心对比**：入参是 `{tid: (rho, 档数)}`（`within_mech` 的原始返回）。

    返回字典，含 discordant 计数、McNemar、Wilcoxon、两臂各自符号检验。
    ⚖⚠⚠ **rho 为 None（零方差 ⇒ 未量到）必须剔出配对分母并报出条数**，
       ⛔ 不能当 0.0 参与 —— 那是「没量到」被当成「测得是 0」。

    ⚖⚠⚖⚖ **解包放在这里，⛔ 不放在调用方** ——
       第一版解包在 `run()`、自检夹具直接喂裸 float
       ⇒ 夹具与生产走**两条不同的代码路径** ⇒ 自检 7/7 全绿，
         ⛔ 而真实数据一进去就 `TypeError` 崩。
       ⚗⇒ 夹具必须**原样**喂生产形状，让判据自己解包。
    """
    pw = unwrap(pw_raw, tag_w)
    pr = unwrap(pr_raw, tag_r)
    tids_w = set(pw)
    tids_r = set(pr)
    if tids_w != tids_r:
        only_w = sorted(tids_w - tids_r)
        only_r = sorted(tids_r - tids_w)
        raise HardFail(
            "两臂轨迹集合不一致 ⇒ **不是配对**，⛔ 拒读"
            "（只在 w：%d，只在 rand：%d）" % (len(only_w), len(only_r)))

    both = {t: (pw[t], pr[t]) for t in sorted(tids_w)
            if pw[t] is not None and pr[t] is not None}
    dropped = sorted(t for t in sorted(tids_w)
                     if pw[t] is None or pr[t] is None)

    b = sum(1 for a, c in both.values() if a > 0 > c)      # w+ / rand−
    c = sum(1 for a, c in both.values() if a < 0 < c)      # w− / rand+
    conc_pp = sum(1 for a, c in both.values() if a > 0 and c > 0)
    conc_mm = sum(1 for a, c in both.values() if a < 0 and c < 0)

    deltas = [c - a for a, c in both.values()]
    w_p, n_nz = wilcoxon_exact(deltas)

    n = len(both)
    return {
        "n_paired": n,
        "dropped": dropped,
        "w_pos": sum(1 for a, c in both.values() if a > 0),
        "w_neg": sum(1 for a, c in both.values() if a < 0),
        "r_pos": sum(1 for a, c in both.values() if c > 0),
        "r_neg": sum(1 for a, c in both.values() if c < 0),
        "w_zero": sum(1 for a, c in both.values() if a == 0),
        "conc_pp": conc_pp, "conc_mm": conc_mm,
        "discordant_wpos_rneg": b, "discordant_wneg_rpos": c,
        "mcnemar_p": mcnemar_exact(b, c),
        "wilcoxon_p": w_p, "wilcoxon_n_nonzero": n_nz,
        "w_sign_p": sign_binom(sum(1 for a, c in both.values() if a > 0), n),
        "r_sign_p": sign_binom(sum(1 for a, c in both.values() if c > 0), n),
        "per_tid": both,
    }


def _f(x):
    return "—" if x is None else ("%.4f" % x)


# --------------------------------------------------------------- 主流程
def run(w_log=W_LOG, rand_log=RAND_LOG, probe_path=PROBE_REL):
    D = _load_dose_axis()
    kp = D.load_k_positions(probe_path)
    cw = D.load_cells(w_log)
    cr = D.load_cells(rand_log)
    rw = D.k_cells(cw, kp)
    rr = D.k_cells(cr, kp)

    L = []
    L.append("【1】配对前提：两臂必须是**同一批轨迹**")
    tw = sorted({r["tid"] for r in rw})
    tr = sorted({r["tid"] for r in rr})
    L.append("  ⚖ w 臂 %d 条 / rand 臂 %d 条；轨迹集合%s"
             % (len(tw), len(tr),
                "**完全一致** ✅" if tw == tr else "⛔ 不一致 ⇒ 拒读"))
    if tw != tr:
        L.append("  ⛔ HardFail：不是配对设计，下面的配对检验**不适用**")
        return "\n".join(L), 1

    L.append("")
    L.append("【2】两臂的层内梯度：三个量，分别回答不同的问题")
    for tag, want in (("传播层", False), ("直接层", True)):
        pw = D.within_mech(rw, want)
        pr = D.within_mech(rr, want)
        L.append("")
        L.append("  ── %s（%s）" % (tag, "只读出位点未被注入的档" if not want
                                     else "读出位点已被注入的档"))
        try:
            s = contrast(pw, pr, "w 臂 / %s" % tag, "rand 臂 / %s" % tag)
        except HardFail as e:
            L.append("     ⛔ %s" % e)
            return "\n".join(L), 1
        L.append("     配对 n=%d%s"
                 % (s["n_paired"],
                    ("；剔掉未量到 %d 条（%s）"
                     % (len(s["dropped"]), ", ".join(s["dropped"][:4])))
                    if s["dropped"] else "；无未量到的轨迹"))
        L.append("     符号计数：w +%d/−%d（0: %d）｜ rand +%d/−%d"
                 % (s["w_pos"], s["w_neg"], s["w_zero"], s["r_pos"], s["r_neg"]))
        L.append("     一致对 both+=%d both−=%d ｜ **不一致对** w+/rand−=%d, w−/rand+=%d"
                 % (s["conc_pp"], s["conc_mm"],
                    s["discordant_wpos_rneg"], s["discordant_wneg_rpos"]))
        L.append("     ⚖ McNemar 精确（**只用不一致对**）p = %s"
                 % _f(s["mcnemar_p"]))
        L.append("     ⚖ Wilcoxon 符号秩精确（rho 幅度，非零差 %d）p = %s"
                 % (s["wilcoxon_n_nonzero"], _f(s["wilcoxon_p"])))
        L.append("     ⚖⚠ 各臂自己 vs 零：w p=%s、rand p=%s —— ⛔ 这两个数"
                 "**只回答「各自 vs 零」**，⛔ 不回答「两臂有差异」"
                 % (_f(s["w_sign_p"]), _f(s["r_sign_p"])))

        gap = (s["r_sign_p"] is not None and s["w_sign_p"] is not None
               and abs(s["r_sign_p"] - s["w_sign_p"]) > 0.05)
        verdict_sign = s["mcnemar_p"] < ALPHA
        verdict_mag = s["wilcoxon_p"] < ALPHA
        if gap and not verdict_sign:
            L.append("     ⚖⚠⚠ **两个 p 值差了 %.3f，而配对检验不显著** ⇒ 这正是"
                     % abs(s["r_sign_p"] - s["w_sign_p"]))
            L.append("        「A 显著 B 不显著 ⇒ A 更大」那个**推理陷阱**的实例。")
        if verdict_sign:
            L.append("     ⚖ 结论：符号**模式**两臂有差异（McNemar p<0.05）")
        else:
            L.append("     ⚖ 结论：符号**模式**两臂**无可检出差异**（McNemar p=%s ≥ 0.05）"
                     % _f(s["mcnemar_p"]))
        if verdict_mag:
            L.append("     ⚖⚠⚠ 结论（**事后**）：rho **幅度**两臂有差异"
                     "（Wilcoxon p=%s < 0.05）" % _f(s["wilcoxon_p"]))
        else:
            L.append("     ⚖⚠ 结论（**事后**）：rho 幅度两臂**无可检出差异**"
                     "（Wilcoxon p=%s ≥ 0.05）" % _f(s["wilcoxon_p"]))

    L.append("")
    L.append("【3】判决（只针对「两臂层内梯度有没有差异」这一问）")
    L.append("  ⚖⚠ 本工具⛔ **没有**回答「rand 臂那个 12/14 是不是噪声」")
    L.append("     —— rep_n=1、层内读数 ~1σ ⇒ 那一条**仍然未解释**。")
    L.append("  ⚖⚠⚠ 本工具全部数字都是**事后分析**，⛔ 不替换预登记统计量、")
    L.append("     ⛔ 不改任何判决。")
    L.append("  ⚖ 禁令（代码化的推理规则）：%s"
             % ("两个 p 值的大小差异**永远不构成**两臂有差异的证据"
                if pval_gap_is_not_evidence(None, None) is False
                else "⛔ 失效"))
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def M(d):
        """⚖ 夹具必须用**生产形状** `(rho, 档数)`，⛔ 不得用裸 float ——
        ⚖⚠⚖ 那正是第一版自检 7/7 全绿而真实数据一进去就崩的原因。"""
        return {k: (v, 3) for k, v in d.items()}

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # ⚖⚠⚖⚖ C1 **头号**：McNemar 必须**只用不一致对**。
    #    这组数据是**特意挑**的，让两种算法给出**不同**的 p：
    #      两臂 6 条同为正（一致对 both+=6）、2 条 w−/rand+（不一致对 c=2）
    #      正确（0, 2，n=2）⇒ 2·C(2,0)/2^2 = 0.5000
    #      错误（拿一致对 6, 0，n=6）⇒ 2·C(6,0)/2^6 = 0.0313
    #    ⚖⚠⚠⚠ 若两组计数**相同**（第一版就是这样），两种算法给出同一个 p
    #      ⛔ 那一关就测不出任何东西 —— 变异 R1 / R1b 都会**存活**。
    pw1 = {"t%d" % i: 1.0 for i in range(6)}
    pw1["t6"] = -1.0
    pw1["t7"] = -1.0
    pr1 = {"t%d" % i: 1.0 for i in range(8)}
    s1 = contrast(M(pw1), M(pr1))
    wrong = mcnemar_exact(s1["conc_pp"], s1["conc_mm"])
    chk("C1", s1["discordant_wpos_rneg"] == 0 and s1["discordant_wneg_rpos"] == 2
        and s1["conc_pp"] == 6 and s1["conc_mm"] == 0
        and abs(s1["mcnemar_p"] - 0.5) < 1e-12 and abs(wrong - 0.03125) < 1e-12,
        "McNemar 只用不一致对 ⇒ p=%.4f；误用一致对会给出 p=%.4f"
        "（两值不同 ⇒ R1 与 R1b 都能被这一关抓住）"
        % (s1["mcnemar_p"], wrong))

    # C2 discordant=0 ⇒ p=1.0，⛔ 不是 0.0（「没不一致对」≠「差异极显著」）
    same = {"t%d" % i: (1.0 if i % 2 else -1.0) for i in range(6)}
    s2 = contrast(M(same), M(same))
    chk("C2", s2["discordant_wpos_rneg"] == 0 and s2["discordant_wneg_rpos"] == 0
        and s2["mcnemar_p"] == 1.0,
        "两臂逐条相同 ⇒ 不一致对 0 ⇒ p=%.4f（⛔ 不得为 0）" % s2["mcnemar_p"])

    # C3 Wilcoxon：全同向 ⇒ p 取到该 n 的**最小值**；全零 ⇒ p=1.0
    w_all, n1 = wilcoxon_exact([1.0, 2.0, 3.0, 4.0])
    w_zero, n2 = wilcoxon_exact([0.0, 0.0, 0.0])
    chk("C3", abs(w_all - 2.0 / 16.0) < 1e-12 and w_zero == 1.0 and n1 == 4 and n2 == 0,
        "全同向 p=%.4f（最小值 2/2^4）；全零 ⇒ p=%.4f 且剔出 %d 个"
        % (w_all, w_zero, n2))

    # C4 ⚖⚖ **禁令必须被真实反例顶住**，⛔ 不是空话：
    #    13 条配对轨迹，w 9 正 / rand 12 正 —— 两个单臂 p 差 0.26，
    #    而配对的 McNemar 只有 3 个不一致对 ⇒ p=0.25，**不显著**。
    #    ⚖ 这正是「A 显著 B 不显著 ⇒ A 更大」的实例，也是 244.30 那条 🔴 的病根。
    pw4 = {"t%d" % i: 1.0 for i in range(9)}
    for i in (9, 10, 11, 12):
        pw4["t%d" % i] = -1.0
    pr4 = {"t%d" % i: 1.0 for i in range(12)}
    pr4["t12"] = -1.0
    s4 = contrast(M(pw4), M(pr4))
    gap = abs(s4["r_sign_p"] - s4["w_sign_p"])
    chk("C4", s4["n_paired"] == 13 and gap > 0.05 and s4["mcnemar_p"] >= ALPHA
        and pval_gap_is_not_evidence(s4["w_sign_p"], s4["r_sign_p"]) is False,
        "反例：n=%d、w p=%.4f vs rand p=%.4f（差 %.4f），McNemar p=%.4f 仍不显著"
        " ⇒ 禁令有实体"
        % (s4["n_paired"], s4["w_sign_p"], s4["r_sign_p"], gap, s4["mcnemar_p"]))

    # C5 未量到（rho=None）必须剔出分母并报出，⛔ 不当 0.0
    pw5 = {"a": 1.0, "b": -1.0, "c": None, "d": 0.5}
    pr5 = {"a": 1.0, "b": -1.0, "c": 1.0, "d": 0.5}
    s5 = contrast(M(pw5), M(pr5))
    chk("C5", s5["n_paired"] == 3 and s5["dropped"] == ["c"]
        and s5["discordant_wneg_rpos"] == 0,
        "有一条 rho=None ⇒ 配对 n=%d、剔出 %s（⛔ 不当 0.0）"
        % (s5["n_paired"], s5["dropped"]))

    # C6 轨迹集合不一致 ⇒ HardFail（⛔ 不许悄悄取交集）
    raised = False
    try:
        contrast(M({"a": 1.0}), M({"a": 1.0, "b": -1.0}))
    except HardFail:
        raised = True
    chk("C6", raised, "两臂轨迹集合不等 ⇒ 必须 HardFail（不许先交后算）")

    # C7 mcnemar_exact 参数为负 ⇒ HardFail（防止把计数写反）
    raised = False
    try:
        mcnemar_exact(-1, 2)
    except HardFail:
        raised = True
    chk("C7", raised, "不一致对计数为负 ⇒ 必须 HardFail")

    # C8 ⚖⚠⚖ `unwrap` 必须**拒收**裸 float —— 这条守卫的由来就是
    #    「夹具和生产形状不同 ⇒ 自检全绿、真实数据崩」。
    raised = False
    try:
        unwrap({"a": 1.0}, "夹具")
    except HardFail:
        raised = True
    ok_shape = unwrap({"a": (1.0, 5)}, "夹具") == {"a": 1.0}
    chk("C8", raised and ok_shape,
        "裸 float 必须被 unwrap 拒收；生产形状 (rho, 档数) 解包正确=%s" % ok_shape)

    # C3b ⚠⚠ **并列（中秩）**必须有独立用例：C3 的 [1,2,3,4] 无并列，
    #   ⇒ 中秩与「严格小于排名」给出**同一个** p ⇒ 那条实现错了也测不出来。
    #   [1,1,-2,3]：中秩 {1.5,1.5,3,4} ⇒ p=10/16=0.625；
    #   严格小于排名 {1,1,3,4} ⇒ p=6/16=0.375。⛔ 两值不同才测得到。
    w_tie, n_tie = wilcoxon_exact([1.0, 1.0, -2.0, 3.0])
    chk("C3b", n_tie == 4 and abs(w_tie - 10.0 / 16.0) < 1e-12,
        "并列中秩 ⇒ p=%.4f（应 0.6250；若实现退回严格小于排名会得 0.3750）"
        % w_tie)

    # C9 单臂符号检验的双侧倍数必须正确（⛔ 少乘 2 ⇒ p 缩小一半，
    #   而报告里那两个 p 正是本工具要**克制使用**的数，印错会误导人）
    s9 = sign_binom(12, 13)
    chk("C9", abs(s9 - 28.0 / 8192.0) < 1e-15,
        "sign_binom(12,13)=%.6f（应 %.6f）" % (s9, 28.0 / 8192.0))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="两臂层内梯度的配对对比（零 GPU）")
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
