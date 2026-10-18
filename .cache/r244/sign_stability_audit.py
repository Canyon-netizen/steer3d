#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sign_stability_audit.py —— 「12/14 正号」这个**计数**对方法有多敏感（零 GPU）

🔴 **这个工具要回答什么**
  244.39 测到：w 臂 **8/13** 条的层内 rho 符号删掉一档就翻，rand 臂 **3/13**。
  ⚖⚠⚖⚖ 但那只是「哪条轨迹不稳」。更要紧的是它对**整体那个计数**的后果：
  244.31 的第三条腿、244.37 的「12/14 vs 9/14」、244.39 的稳健性对比，
  ⚖⚠⚠⚠ **全都建立在「正号数」这一个数上**。
  ⚗⇒ 如果那个数在方法稍微一变时就大幅移动，
     ⇒ **「12/14 正号、p=0.0129」根本不是一个稳健的量**。

⚖⚖ **做法：正号数的「最坏情形界」**
  ⚖ 对每条轨迹，把**完整版 + 全部留一变体**的 rho 符号都收起来：
     · 全为正 ⇒ 这条**只可能**贡献正号
     · 全为负 ⇒ 只可能贡献负号
     · 两者都有 ⇒ **两可**（符号是偶然的）
  ⚖ 于是正号数落在 **[只可能负 … 只可能正或两可]** 之间，
     ⚖ 并把它换算成 p 的区间一并印出。

⚖⚠⚠⚠⚖ **这个区间是「最坏情形界」，⛔ 绝对不是置信区间**
  ⚖ 它假设「每条轨迹**同时**取到对整体结论最不利的方向」。
  ⚖⇒ 它是一个**下界**（偏保守），⛔ 不含任何概率模型。
  ⚖⚠⚠⚠ 而它照样有用：区间**宽到覆盖另一臂**时，
     ⇒ 说明**这个量分辨不了两臂**，⚗⇒ 必须连同区间一起印，⛔ 不许单引。

🔴🔴 **修订 244.40 的头号教训：双侧符号检验的 p 关于 k 是「V 形」，⛔ 不单调**
  ⚖ `sign_binom(k,n) = 2·Σ_{i≤min(k, n−k)} C(n,i)/2ⁿ` ⇒ 关于 k **先降后升**，
     **最小值在两端、最大值在 k=n/2**。
  ⚖⚠⚠⚠ 第一版把 p 的区间写成 `[sign_binom(hi), sign_binom(lo)]`，
     ⛔ 那**默认了单调**。w 臂的界 [4,13] **横跨 k=7** ⇒
     ⚖ 端点公式印出 `[0.0018, 0.1796]`，
     ⚖⚠⚠⚠ 而真实最坏在 **k=7 ⇒ p = 1.0000**（恰好落在零假设中心）
     ⚖⇒ **印出来的最坏情形把 w 臂美化了 5.6 倍**，⛔ 而且方向最坏：
        它让 w 臂看起来「方法变一下也还行」。
  ⚗⇒ 修法：`p_span` **逐个 k 扫描** [lo,hi] 取 (min, max) 并报出最坏 k；
     并用 **C8** 钉住「端点公式与扫描结果必须不同」。

⚖⚠⚠ **两条必须照抄的禁令**
  ⚖ ① 区间重叠 ⛔ **不等于**「两者相同」——
     它等于「**这个量不可用**」。⛔ 不许印成「没有差别」。
  ⚖ ② 「稳」⛔ 不等于「不是噪声」；「不稳健」⛔ 也不等于「是噪声」。
     rep_n=1 的那个问题，本工具⛔ **回答不了**。

⛔ 本工具：⛔ 不改任何真文件；⛔ 不跑批；⛔ 只读两份已有日志。
"""

import argparse
import importlib.util
import itertools
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"
W_LOG = ".cache/r244/w_new.log"
RAND_LOG = ".cache/r244/rand_new.log"
ALPHA = 0.05


class HardFail(Exception):
    pass


def _load(modname, fname):
    path = os.path.join(HERE, fname)
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def sign_binom(pos, n):
    """⚖ 复用 `arm_contrast_audit.sign_binom` —— ⛔ 不手抄一份。"""
    return _load("arm_for_sign", "arm_contrast_audit.py").sign_binom(pos, n)


def tau(x, y):
    """⚖ Kendall tau-b —— 用**秩的**定义，不走 Spearman 的中秩那一套。"""
    n = len(x)
    if n < 2:
        return None
    con = dis = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = x[i] - x[j], y[i] - y[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif (dx > 0) == (dy > 0):
                con += 1
            else:
                dis += 1
    den = math.sqrt((con + dis + tx) * (con + dis + ty))
    return (con - dis) / den if den > 0 else None


# --------------------------------------------------------------- 变体符号
def variant_signs(cov, y, spearman_fn, min_variants=2):
    """⚖ 收齐「完整版 + 全部留一变体」的符号。

    ⚖⚠⚠ 至少要 `min_variants` 个可算的 rho 才谈得上「稳定」；
       少于它 ⇒ **未量到**，⛔ 不许报成「只可能正」。
    ⚖⚠⚠ 返回 (只可能正, 只可能负, 两可, 变体数)
    """
    vs = []
    full = spearman_fn(list(cov), list(y))
    if full is not None:
        vs.append(full)
    for j in range(len(cov)):
        r = spearman_fn([v for i, v in enumerate(cov) if i != j],
                        [v for i, v in enumerate(y) if i != j])
        if r is not None:
            vs.append(r)
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ **返回值必须四者互不相同。**
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ 第一版用 `None` **同时**表示「变体不足（未量到）」与
    #   「两可」，而 `run()` 把 `None` 一律当成「未量到」剔出
    #   ⇒ **9 条两可轨迹被当成未量到丢掉**，只剩 5 条稳定的
    #   ⇒ 区间塌成 [4,4] vs [9,9] ⇒ 印出「区间**不重叠**、可分辨」
    #   ⛔ 而真实区间是 [4,13] 覆盖 [9,12] ⇒ **结论整个反了**。
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖ ⚖ 这是本轮**最贵的一个 bug**：它把「不可分辨」
    #   印成了「可分辨」，而方向恰好相反。
    # ⚗⇒ 修法：⛔ **不许用同一个哨兵表示两种状态**。
    #   `None` = 未量到；`True` = 恒正；`False` = 恒负；`"either"` = 两可。
    if len(vs) < min_variants:
        return None                      # 未量到
    has_p = any(v > 0 for v in vs)
    has_n = any(v < 0 for v in vs)
    if has_p and has_n:
        return "either"                  # 两可 ⛔ 与「未量到」**必须**分开
    if has_p:
        return True                      # 恒正
    return False                         # 恒负（含全为 0：没有方向）


def bounds(flags):
    """⚖ 由三分类算出正号数的**最坏情形界**。
    ⚖⚠⚖⚖⚖⚖⚖ **下界到底是哪个数？我第一版写反了，而且自检把它钉住了。**

    ⚖ 计数 = Σ「这条轨迹在当前变体下是否为正」：
      · 只可能正 ⇒ **恒**贡献 1
      · 只可能负 ⇒ **恒**贡献 0
      · 两可       ⇒ 贡献 0 或 1
    ⚗⇒ 最坏情形 = **两可全部取负** ⇒ **lo = 只可能正**（⛔ 不是「只可能负」！）
    ⚗⇒ 最好情形 = 两可全部取正 ⇒ **hi = 只可能正 + 两可**

    ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖ **我第一版把 lo 写成「只可能负」** ⇒
      ① 区间被**凭空拉宽**（rand 真值 [9,12] 会被印成 [2,12]）
      ② 更糟的是 **C2 与 C4 按错误的期望写** ⇒ **自检在给 bug 背书**
         ⚖⚠⚠⚠ 「自检全绿」与「实现错了」**同时成立**。
    ⚗⇒ 修法：先按**定义**把计数写出来再写代码；
      自检的期望串必须**独立于实现**推导（这里是「两可全取负」这句定义）。
    """
    only_p = sum(1 for f in flags if f is True)
    only_n = sum(1 for f in flags if f is False)
    either = sum(1 for f in flags if f == "either")          # ⛔ 不是 f is None
    n = len(flags)
    return {"n": n, "only_pos": only_p, "only_neg": only_n,
            "either": either, "lo": only_p, "hi": only_p + either}


def _pv(p):
    """⚖ p 值取 None 时才算「没算出来」⇒ 印 1.0。

    ⚖⚠⚠⚖⚖⚖⚖ **⛔⛔ 第一版写的是 `sign_binom(...) or 1.0`。**
    ⚖⚠⚠⚖⚖ `or` 是**真值**判断，不是「是不是 None」判断
       ⇒ p **恰好为 0.0** 时（`2/2ⁿ` 在 n 大时下溢；或被夹到 0），
       `0.0 or 1.0` ⇒ **印成 1.0** ⇒ 「最坏情形 p」被印成「毫无证据」的反面。
    ⚖⚠⚠⚖⚖⚖ 这与「不许用同一个哨兵表示两种状态」同族：**必须**显式判 None。
    """
    return 1.0 if p is None else p


def p_span(lo, hi, n, sign_fn=None):
    """⚖ 正号数落在 [lo,hi] 时，**双侧符号检验 p** 能取到的全部值。

    ⚖⚠⚠⚠⚖⚖⚖⚖⚖ **为什么必须逐个 k 扫，而不是端点公式**
    ⚖ `sign_binom` 是**双侧**的（`min(k, n−k)`）⇒ 关于 k 是 **V 形**：
       k=1 与 k=n−1 **同值**（都是 2·(1+n)/2ⁿ），k=n/2 处**最大**。
    ⚖⚠⚠⚠⚖⇒ `[sign(hi), sign(lo)]` 只看**两端**，⛔ 会把「最坏在中间」整段漏掉。
       ⚖⚠⚠⚠⚖⚖⚖ 本例实测：w 臂 [4,13] 端点给 `[0.0018, 0.1796]`，
          扫描给 **`[0.0018, 1.0000]`**（最坏在 k=7）⇒ 差 **5.6 倍**。
    ⚗⇒ 返回 (p_min, p_max) 与**各自对应的 k**，报告里必须把 k 印出来
       —— 否则读者只会看到两个数，⛔ 不知道最坏情形是「方法一变就归零」。

    ⚖⚠⚠ 区间 [lo,hi] 是整数闭区间；⛔ 不许传反（lo > hi）。
    """
    if sign_fn is None:
        sign_fn = sign_binom
    if n <= 0 or lo > hi:
        raise HardFail("p_span：n=%d、lo=%d、hi=%d ⇒ 参数不合法" % (n, lo, hi))
    vals = [(sign_fn(k, n), k) for k in range(lo, hi + 1)]
    p_min, k_min = min(vals, key=lambda t: t[0])
    p_max, k_max = max(vals, key=lambda t: t[0])
    return {"p_min": _pv(p_min), "k_at_pmin": k_min,
            "p_max": _pv(p_max), "k_at_pmax": k_max, "n": n}


def parse_counts(txt):
    """⚖ 把**报告文本**里的分类计数解回来 —— `run()` 层判据的唯一入口。

    ⚖⚠⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ **为什么要从文本里解，而不是让 selftest 直接摸内部变量？**
    ⚖ 因为**函数级**夹具看不见报告层：
      ⚖⚠⚖⚖⚖⚖ 第一版的 C1..C7 **全是函数级** ⇒ 「两可被并进未量到、
        区间塌成 [4,4] vs [9,9] ⇒ 印出可分辨」那个真 bug，
        ⚖⚠⚠⚖⚖⚖⚖⚖⚖ **七条自检一起绿**，⛔ 而报告印的是错的。
    ⚗⇒ 哨兵复用、计数塌缩这类 bug，⛔ 只能由**读报告**的判据抓住。
    ⛔ 解析失败必须抛 HardFail（⛔ 不许悄悄少解一条）——
      少解一条会让「两臂」循环只看一条臂，恒绿。
    """
    out, cur = [], None
    for ln in txt.split("\n"):
        if "臂（传播层，n=" in ln:
            # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ **只吃连续数字**，⛔ 不许 split("）") / split(";")
            # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ 第一版用 `split("）")[0]` ⇒ 平时全绿，
            #   ⚖⚠⚖⚖⚖⚖⚖⚖⛔ 而一旦真 bug（哨兵复用）发作，报告变成
            #   「n=5；未量到 9 条剔出」⇒ `int()` **当场崩** ⇒ 台架报「崩 ≠ 抓到」
            #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖ ⇒ 等于**在最该抓的那条变异上失去牙齿**。
            # ⚗⇒ 教训同族：「解析器只在病发时才跑的那条分支」⛔ 必须先写成稳的。
            head, num = ln.split("n=")[1], ""
            for ch in head:
                if not ch.isdigit():
                    break
                num += ch
            if not num:
                raise HardFail("臂计数行里读不出 n：%r" % ln)
            cur = {"n": int(num),
                   "dropped": int(ln.split("未量到 ")[1].split(" ")[0])
                   if "未量到 " in ln else 0}
            out.append(cur)
        elif cur is not None and "只可能正" in ln:
            seg = ln.split("**")
            if len(seg) < 6:
                raise HardFail("分类计数行解析不了：%r" % ln)
            cur["only_pos"], cur["only_neg"] = int(seg[1]), int(seg[3])
            cur["either"] = int(seg[5].split()[-1])
        elif cur is not None and "正号数的界 = **[" in ln:
            lo, hi = ln.split("**[")[1].split("]**")[0].split(",")
            cur["lo"], cur["hi"] = int(lo), int(hi)
        elif cur is not None and "p 的区间 = **[" in ln:
            lo, hi = ln.split("**[")[1].split("]**")[0].split(",")
            cur["p_min"], cur["p_max"] = float(lo), float(hi)
    if len(out) != 2:
        raise HardFail("报告里解析到 %d 条臂的计数（应恰好 2）⇒ ⛔ 判据会恒绿"
                        % len(out))
    for c in out:
        for k in ("only_pos", "only_neg", "either", "lo", "hi", "p_min", "p_max"):
            if k not in c:
                raise HardFail("臂的计数缺字段 %s ⇒ ⛔ 拒读（报告格式变了？）" % k)
    return out


def overlap_is_not_equality(a, b):
    """⚖⚖ **恒返回 False 的禁令**，且它**必须**恒返回 False。

    🔴 244.37 与 244.38 连续两次踩「p≥0.05 ⇒ 不成立」那一条的反面。
    ⚖⚠⚠⚖ 本工具会印出「w 区间 [4,13] **完全覆盖** rand 区间 [9,12]」。
    ⚖⚠⚠⛔ 那**不是**「两臂没有差别」的证据，
       ⚖⚠⚠⚠ 它是「**这个量分辨不了两臂**」的证据 ——
       后者的行动含义是「**别再用它**」，前者是「**可以下结论了**」。
    ⚖⚠⚠⛔ 完全相反 ⇒ 必须禁止。
    """
    return False


# --------------------------------------------------------------- 主流程
def run(w_log=W_LOG, rand_log=RAND_LOG, probe_path=PROBE_REL):
    D = _load("dose_for_sign", "dose_axis_audit.py")
    kp = D.load_k_positions(probe_path)
    L = []

    L.append("【1】正号数的**最坏情形界**（完整版 + 全部留一变体）")
    L.append("  ⚖⚠⚠⚠ 这是**最坏情形界**，⛔ **绝对不是置信区间**")
    L.append("     （它假设每条轨迹**同时**取到最不利方向；⛔ 不含概率模型）")
    res = {}
    for name, path in (("w", w_log), ("rand", rand_log)):
        rows = D.k_cells(D.load_cells(path), kp)
        g = D.by_tid([r for r in rows if not r["direct"]])
        flags, dropped = [], []
        for tid in sorted(g):
            sub = sorted(g[tid], key=lambda r: r["cov"])
            f = variant_signs([r["cov"] for r in sub],
                              [r["raw"] for r in sub], D.spearman)
            if f is None:
                dropped.append(tid)
            else:
                flags.append(f)
        b = bounds(flags)
        obs = sum(1 for t in sorted(g)
                  if t not in dropped
                  and D.spearman([r["cov"] for r in sorted(g[t], key=lambda x: x["cov"])],
                                 [r["raw"] for r in sorted(g[t], key=lambda x: x["cov"])]) > 0)
        res[name] = b
        sp = p_span(b["lo"], b["hi"], b["n"])
        obs_p = _pv(sign_binom(obs, b["n"]))
        naive_hi = _pv(sign_binom(b["hi"], b["n"]))
        naive_lo = _pv(sign_binom(b["lo"], b["n"]))
        res[name + "_span"] = sp
        L.append("")
        L.append("  ── %s 臂（传播层，n=%d%s）"
                 % (name, b["n"],
                    "；未量到 %d 条剔出" % len(dropped) if dropped else ""))
        L.append("     只可能正 **%d** ｜只可能负 **%d** ｜**两可 %d**"
                 % (b["only_pos"], b["only_neg"], b["either"]))
        L.append("     实测正号（只用完整版 rho）= **%d**" % obs)
        L.append("     ⇒ 正号数的界 = **[%d, %d]**" % (b["lo"], b["hi"]))
        # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ **p 区间必须逐 k 扫**（`p_span`），⛔ 不用端点公式：
        #   双侧 p 关于 k 是 **V 形** ⇒ 端点公式会把「最坏在中间」整段漏掉。
        #   ⚖⚠⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ w 臂界 [4,13] 横跨 k=7 ⇒ 端点公式印 [0.0018,0.1796]，
        #   真实最坏 **1.0000**（k=7）⇒ 差 5.6 倍，⛔ 而且**恰好美化 w 臂**。
        # ⚖⚠⚖⚖⚖⚖ 第一版这两行还**各印一次 p 区间**（一个带实测、一个不带），
        #   ⛔ 同一屏出现两个「区间」⇒ 读者必然挑错那个 ⇒ 已合并成一行。
        L.append("     ⇒ p 的区间 = **[%.4f, %.4f]**（最坏 p=%.4f 出现在 k=%d；"
                 "实测 p = %.4f）"
                 % (sp["p_min"], sp["p_max"], sp["p_max"], sp["k_at_pmax"], obs_p))
        L.append("     ⚖⚠⚠ 双侧符号检验的 p 关于 k 是 **V 形**（k 与 n−k 同值）"
                 "⇒ ⛔ 端点公式只给 [%.4f, %.4f]，" % (naive_hi, naive_lo))
        if abs(naive_lo - sp["p_max"]) > 1e-9:
            L.append("        而逐 k 扫描的**最坏**是 %.4f（k=%d）⇒ "
                     "⚠⚠⚠ **端点公式把最坏情形说轻了**"
                     % (sp["p_max"], sp["k_at_pmax"]))
        else:
            L.append("        本臂的界**没有**横跨 k=n/2 ⇒ 两种算法一致")

    L.append("")
    L.append("【2】两臂的区间可分辨吗")
    a, b = res["w"], res["rand"]
    ov = not (a["hi"] < b["lo"] or b["hi"] < a["lo"])
    L.append("  ⚖ w 臂 [%d, %d] ｜rand 臂 [%d, %d]"
             % (a["lo"], a["hi"], b["lo"], b["hi"]))
    if ov:
        L.append("  ⇒ ⚠⚠⚠ **两个区间重叠**（甚至 w 的界完全覆盖 rand 的）")
        L.append("     ⇒ 「正号数」这个量**分辨不了两臂**")
        L.append("     ⚖⚠⚠⛔ 这⛔ **不是**「两臂没有差别」的证据；")
        L.append("        它是「**别再用这个量下结论**」的证据。")
    else:
        L.append("  ⇒ 区间不重叠（⚖ 本轮不成立，如实报）")
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖ p 的区间也**必须**一起看：计数区间不重叠但 p 区间重叠，
    #   ⚖ 说明「显著」这个说法本身就随方法漂 ⇒ 结论同样不能用。
    pw, pr = res["w_span"], res["rand_span"]
    pov = not (pw["p_max"] < pr["p_min"] or pr["p_max"] < pw["p_min"])
    L.append("  ⚖ p 的区间：w **[%.4f, %.4f]** ｜rand **[%.4f, %.4f]**%s"
             % (pw["p_min"], pw["p_max"], pr["p_min"], pr["p_max"],
                "  ⇒ ⚠⚠⚠ **p 的区间也重叠**" if pov else "  ⇒ p 区间不重叠"))
    if pov:
        L.append("     ⇒ 连「p<0.05」这个说法都**随方法漂** ⇒ 结论不能只靠 p")

    L.append("")
    L.append("【3】读法（⛔ 不要越读）")
    L.append("  ⚖ ⚠ 区间重叠 ⛔ 不等于「两者相同」⇒ 禁令 %s"
             % ("生效" if overlap_is_not_equality(a, b) is False else "⛔ 失效"))
    L.append("  ⚖ ⚠ 「稳」⛔ 不等于「不是噪声」；「不稳健」⛔ 也不等于「是噪声」。")
    L.append("     rep_n=1 的那个问题，本工具⛔ **回答不了**。")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    D = _load("dose_for_sign_st", "dose_axis_audit.py")
    spm = D.spearman

    # C1 稳健轨迹 ⇒ 界退化为它自己
    v = variant_signs([0.1, 0.2, 0.3, 0.4], [1.0, 2.0, 3.0, 4.0], spm)
    b1 = bounds([v])
    # ⚖⚠⚖⚖⚖⚖ 稳健正 ⇒ **恒**贡献正号 ⇒ 界退化成 [1,1]
    #   ⚖⚠⚠⚖⚖⚠⚖⚖ 我第一版这里期望 [0,1] —— 那是按**错误实现**写的
    #   ⇒ 三条自检（C1/C2/C4）里有**三条**在给同一个 bug 背书，
    #   ⚖⚠⚠⚠ 而台架当时报「自检 6/7 通过」，看上去只差一条。
    chk("C1", v is True and b1["lo"] == 1 and b1["hi"] == 1,
        "干净单调 ⇒ 只可能正；界=[%d,%d]（应 [1,1]：恒正**恒**贡献 1）"
        % (b1["lo"], b1["hi"]))

    # C2 ⚖⚠⚖⚖⚖⚖ 期望**按定义**推：两可全取负 ⇒ 正号数 = 恒正的两条 = **2**；
    #   两可全取正 ⇒ **3**。⛔ 不是「只可能负」的 1。
    # ⚖⚠⚖⚖⚖⚖⚖⚖ 夹具是**暴力搜**出来的真实序列（244.39 的教训：⛔ 不许凭印象写）
    yv = [25.0, 27.0, 3.0, 17.0, 33.0]
    xv = [0.1, 0.2, 0.3, 0.4, 0.5]
    tw = variant_signs(xv, yv, spm)
    b2 = bounds([True, True, False, tw])
    chk("C2", b2["either"] == 1 and b2["lo"] == 2 and b2["hi"] == 3,
        "两可夹具（rho=%+.3f）：界=[%d,%d]"
        "（下界=恒正条数 **2**；⛔ 写成「只可能负」的 1 就是 bug）"
        % (spm(xv, yv), b2["lo"], b2["hi"]))

    # C3 ⚠⚠⚖⚖ 另一种错法：上界漏掉「两可」⇒ **假不显著**
    #    纯人工构造（⛔ 不是搜的）：三条全为「两可」
    b3 = bounds(["either", "either", "either"])
    chk("C3", b3["lo"] == 0 and b3["hi"] == 3 and b3["only_neg"] == 0,
        "三条全两可 ⇒ lo=**0**（⛔ 不许算成 3）、hi=**3**（⛔ 不许漏）")

    # C4 ⚖⚠⚖⚖⚖⚖⚖⚖ 三条**全恒负** ⇒ 正号数恒为 **0** ⇒ 界 [0, 0]
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚠ 我第一版在这里期望 [3,3] —— 那个期望**本身也是错的**
    #   ⇒ 第一版 C4 是「按错误实现写的断言」⇒ 它当时**通过了**，而实现是错的。
    b4 = bounds([False, False, False])
    chk("C4", b4["lo"] == 0 and b4["hi"] == 0 and b4["only_neg"] == 3,
        "三条全恒负 ⇒ 界=[%d,%d]（应 [0,0]：恒负的**永远不**贡献正号）"
        % (b4["lo"], b4["hi"]))

    # C5 ⚠⚠⚖ 变体数不足 ⇒ **未量到**（None），⛔ 不许报成「只可能正」，
    #   ⛔ 也⛔ **不许**与「两可」（"either"）共用同一个哨兵 ——
    #   ⚖⚠⚖⚖⚖⚖⚖ 那正是把 9 条两可当成未量到剔掉、结论整个反过来的那个 bug。
    v5 = variant_signs([0.1, 0.2], [1.0, 9.0], spm)
    chk("C5", v5 is None, "2 档 ⇒ 变体不足 ⇒ 未量到（实测 %s）" % v5)

    # C6 ⚠⚠⚖ 禁令必须有实体：本工具真的会印出「区间重叠」
    a5 = bounds([True, False, "either", "either"])
    b6 = bounds([True, True, "either", "either"])
    ov = not (a5["hi"] < b6["lo"] or b6["hi"] < a5["lo"])
    chk("C6", ov and overlap_is_not_equality(a5, b6) is False,
        "反例：w 界=[%d,%d]、rand 界=[%d,%d] ⇒ 重叠，但禁令要求"
        "⛔ **不许**印成「两者相同」" % (a5["lo"], a5["hi"], b6["lo"], b6["hi"]))

    # C7 ⚖⚠⚖ 报告必须**印成字面量**：⛔ 阈值/措辞不许只活在代码里
    #   ⚖⚠⚖⚖⚖⚖ 加严到 V 形那句与 p 区间那句。
    #   🔴🔴🔴 **⛔ 不许查「条件分支里才出现的那句」**（如「p 的区间也重叠」）：
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖ 那让 C7 变成**数据依赖**判据 ——
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖ 数据一换（区间不再重叠）它就**假红**，
    #   ⚖⚠⚖⚥⚠⚠⚠⚠ 而基线（恰好重叠）看不出来 ⇒ 又是一个「看着绿、其实脆」的自检。
    # ⚗⇒ 拆成两半：**恒印**的字面量查报告；**分支**字面量查源码。
    Lr = run()[0]
    src_here = open(os.path.abspath(__file__), encoding="utf-8").read()
    always = ("最坏情形界", "不是置信区间", "正号数的界 = **[", "p 的区间 = **[",
              "V 形", "最坏 p=", "p 的区间：w")
    branches = ("p 的区间也重叠", "p 区间不重叠",
                "端点公式把最坏情形说轻了", "没有**横跨 k=n/2")
    miss_r = [x for x in always if x not in Lr]
    miss_s = [x for x in branches if x not in src_here]
    chk("C7", not miss_r and not miss_s,
        "报告恒印字面量缺 %s；源码分支字面量缺 %s"
        % ("无" if not miss_r else miss_r, "无" if not miss_s else miss_s))

    # C8 🔴🔴 **本轮头号教训**：端点公式 ≠ p 的区间（双侧 p 是 V 形）
    #   ⚖⚠⚠⚖⚖ 夹具就是 **w 臂的真实界** [4,13]、n=14（⛔ 不编数字）
    #   ⚖ 端点公式：[sign(13), sign(4)] = [0.0018, 0.1796]
    #   ⚖ 逐 k 扫 ：min 0.0018（k=13）｜**max 1.0000（k=7）** ← 期望值是**字面量**
    s8 = p_span(4, 13, 14)
    e8_hi = _pv(sign_binom(13, 14))
    e8_lo = _pv(sign_binom(4, 14))
    chk("C8", abs(s8["p_min"] - 0.0018) < 1e-4 and s8["p_max"] == 1.0
        and s8["k_at_pmax"] == 7 and e8_hi < 0.002 and abs(e8_lo - 0.1796) < 1e-4
        and abs(e8_lo - s8["p_max"]) > 0.5,
        "w 臂真界[4,13]/n=14：扫描 ⇒ [%.4f, %.4f]（最坏 k=%d）；"
        "端点公式 ⇒ [%.4f, %.4f] ⇒ 两者差 %.1f 倍，⛔ 端点公式把最坏说轻了"
        % (s8["p_min"], s8["p_max"], s8["k_at_pmax"], e8_hi, e8_lo,
           s8["p_max"] / max(e8_lo, 1e-12)))

    # C9 ⚖⚠⚖ `_pv` 必须只把 **None** 当「没算出来」⇒ ⛔ 不许用 `or`
    #   ⚖⚠⚖⚖⚖⚖ 第一版写 `sign_binom(...) or 1.0`：p 恰为 **0.0** 时
    #   ⇒ `0.0 or 1.0` ⇒ 印成 1.0 ⇒ 「最坏 p」被印反。
    chk("C9", _pv(0.0) == 0.0 and _pv(None) == 1.0 and _pv(0.5) == 0.5,
        "falsy 陷阱：_pv(0.0)=%.1f（⛔ 不是 1.0）、_pv(None)=%.1f、_pv(0.5)=%.1f"
        % (_pv(0.0), _pv(None), _pv(0.5)))

    # C10 ⚖⚠⚖⚖⚖⚖ **V 形这件事本身**必须是可核事实，⛔ 不是我的口头主张
    #    （夹具走**生产**那个 `sign_binom`，⛔ 不塞替身）
    v_lo = _pv(sign_binom(1, 14))
    v_hi = _pv(sign_binom(13, 14))
    v_mid = _pv(sign_binom(7, 14))
    chk("C10", abs(v_lo - v_hi) < 1e-12 and v_mid == 1.0 and v_hi < v_mid,
        "sign_binom(1,14)=%.4f == sign_binom(13,14)=%.4f；"
        "sign_binom(7,14)=%.4f ⇒ 确认 **V 形**（两端同值、中间最大）"
        % (v_lo, v_hi, v_mid))

    # C11 🔴⚖⚖ **`run()` 层**判据：C1..C10 全是函数级夹具，⛔ 看不见报告层
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ 哨兵复用（Q1 那种）只有这一层能抓住：
    #   ⚖⚠⚖⚖⚖⚖ 第一版 C1..C7 七条一起绿，⛔ 而报告印的是「可分辨」。
    #   ① 三类 + 未量到 == n ② hi−lo == 两可 ③ p 在 [0,1] 且不倒挂
    #   ④ **两可 ≥ 1** —— ⛔ 这一条是**数据相关**的证人（本轮真两可 9/3），
    #      ⛔ 数据换了可能失效；⚗ 有意的：哨兵复用会让它**变 0**。
    cs = parse_counts(Lr)
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ **恒等式要用 `bounds` 的定义，不是「总数」**
    # ⚖ `bounds` 的 n = **len(flags)**（已剔掉未量到）⇒ n **不含** dropped。
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚠⚠ 第一版我写成「三类 + dropped == n」，
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚠⚠ 那条**恒错**（漏了 dropped 多算一遍）
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚠⚠ ⇒ 只要真 bug 让「有轨迹被剔出」，C11 就红
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚠⚠ ⇒ 它会是**假警报**，而基线（无 dropped）看不出来。
    acct = all(c["only_pos"] + c["only_neg"] + c["either"] == c["n"]
               and c["hi"] - c["lo"] == c["either"]
               and 0.0 <= c["p_min"] <= c["p_max"] <= 1.0 for c in cs)
    either_nz = max(c["either"] for c in cs) >= 1
    chk("C11", acct and either_nz,
        "报告层对账：%s；两可最大 %d 条（⛔ 变 0 就是哨兵复用）"
        % ("｜".join("n=%d=%d+%d+%d, 界[%d,%d], p[%.4f,%.4f], 未量到%d"
                     % (c["n"], c["only_pos"], c["only_neg"], c["either"],
                        c["lo"], c["hi"], c["p_min"], c["p_max"], c["dropped"])
                     for c in cs),
           max(c["either"] for c in cs)))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="正号数对方法的敏感区间（零 GPU）")
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
