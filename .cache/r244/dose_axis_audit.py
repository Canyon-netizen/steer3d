#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dose_axis_audit.py —— 审计「剂量—响应」阶梯的剂量轴本身（修订 244.31）

🔴 **为什么要有这个工具**
  244.29 发现阶梯真结构是 `{n_eff//1024, //256, //64, //16, //4, //2, ×3//4, ×7//8}`；
  244.30 把预登记统计量按档型切开后发现：**真正的剂量阶梯单独看 Fisher p=0.7036**，
  显著性全部由尾段档（3/4、7/8）与端点档（single/all）承载。
  ⇒ 引出一个**结构性**问题（不是调参问题）：
      「剂量—响应」这套设计，**是否真的在测剂量？**

⚖⚠⚠ 本工具要拆的两条轴
  * **剂量轴**：覆盖率 `cov = k / n_eff`
  * **机制轴**：注入位点集里**有没有读出位点 `n_eff-1`**（`r204_noise_probe.py:431`
    的 forward 返回 `o.logits[0, -1]`）
    ⇒ 含 ⇒ marker logsumexp 被**直接**扰动；不含 ⇒ 经残差流**传播**。
  ⚖ 244.27 已登记「k 档之间混着两种机制」，但**没量过两者共线到什么程度**。
  ⚗⇒ 本工具把「共线性」本身变成一条**按构造能红**的判据（J6）。

⚖⚠⚠⚖ 本轮作者在这件事上踩过的两个坑，已写成判据（不是写成注释）
  ⚖⚠ 坑一：`kp(n, n, nested=True)` 命中探针里的 `if k == n: return list(range(n))`
        这个**恒等捷径**。用它去找「读出位点在排列里的秩」，会**恒定**得到
        秩 = n-1、阈值覆盖 ≈ 1.0 —— 数字单调、量级合理、**看不出任何毛病**，
        而它是捷径造的，不是数据。⇒ J1（k 必须 < n_eff）+ J2（反证件）。
  ⚖⚠⚠ 坑二：按 `10**9` 把 `single`/`all` 排到 k 档末尾来造「档序」。
        ⛔ 每条轨迹的 k 档数是 **7/8/9 三种**（`n_eff < 1024` 的档被丢、
        `p03__think` 多一个人工补档），⇒ 「档序」会把 k 档与端点**混进同一列**，
        印出 14/10/1 这种**不可能**的每列格数。⚠ 本工具的作者第一版就是这么错的，
        而总数 137 当时看着完全正常 —— 抓住它的是**k 档总数 112 ≠ 109**。
        ⇒ J4 用「k 档集合两臂逐格相同 + 总数与落盘格表一致」把它钉死。

⛔ 本工具**零 GPU**，只用已落盘的读数 JSON + 探针源码（AST 抽取位点函数）。

⚖ 独立单位：轨迹（14 条）。⛔ 格与格**不独立**（同轨迹共用 prompt/问题/生成轨迹），
   故一切轨迹级统计都用 n=14 做符号检验，⛔ 不用 137 格。
"""

import argparse
import ast
import collections
import json
import math
import os
import sys

# ⚖ 探针源码的**兜底**相对路径。⛔ 本模块**不读自己的源码**（`__file__`）：
#   变异台把源码 exec 进内存模块，那儿没有 `__file__`。
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"

RESP_HI = "p9_hi_meas"
RESP_LO = "p9_lo_meas"
RESP_NORM = "margin_meas"
RESP_DENOM = "resid_std"
UP = "up_mono_meas"


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 统计
def binom2(k, n):
    """⚖ 双尾二项检验。⛔ 返回值必须在 [0,1] —— 这条断言是判据 J8。

    ⚖⚠⚠⚠ 修订 244.31：作者第一版写成 `2*min(1.0,p)`，于是 **k=n 时印出 p=2**
    （p 的上界是 1，2 是**不可能**的值）。抓住它的不是「2 看着奇怪」，
    而是**上界**这个事实。⇒ 正确式是 `min(1.0, 2*单尾)`，截断是**必需**的；
    ⛔ 但**把截断改成 `1.0`**（244.23 的变异）必须仍被抓 ⇒ 自检 T6 钉它。
    """
    if n <= 0:
        raise HardFail("binom2：n=%r 不是正数 ⇒ 「没量到」，⛔ 不许当 p=1" % (n,))
    if not (0 <= k <= n):
        raise HardFail("binom2：k=%r 越界（0<=k<=%d）" % (k, n))
    lo = sum(math.comb(n, i) for i in range(0, k + 1)) / 2.0 ** n
    hi = sum(math.comb(n, i) for i in range(k, n + 1)) / 2.0 ** n
    p = min(1.0, 2.0 * min(lo, hi))
    if not (0.0 <= p <= 1.0):
        raise HardFail("binom2 印出不可能的 p=%r（上界 1）" % (p,))
    return p


def rankdata(v):
    """平均秩（并列取均值）。⛔ 空序列直接 HardFail，不许返回 0 让人当「无相关」。"""
    n = len(v)
    if n < 2:
        raise HardFail("rankdata：长度 %d < 2 ⇒ 相关系数**未量到**" % n)
    order = sorted(range(n), key=lambda i: v[i])
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for q in range(i, j + 1):
            r[order[q]] = avg
        i = j + 1
    return r


def spearman(x, y):
    if len(x) != len(y):
        raise HardFail("spearman：长度不等 %d vs %d" % (len(x), len(y)))
    rx, ry = rankdata(x), rankdata(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0.0 or dy == 0.0:
        return None            # ⛔ 零方差 ⇒ 「未量到」，⛔ 不许当 0.0
    return num / (dx * dy)


def sign_fisher(pos, n):
    """pos 个正号 / n 个单位的双尾检验。⛔ n==0 ⇒ 未量到 ⇒ 报 None，⛔ 不许当 p=1。"""
    if n <= 0:
        return None
    return binom2(pos, n)


def med(v):
    """⚖ **中位**，偶数长度取**两中位的平均**（标准约定）。

    ⚖⚠⚠⚖ 修订 244.31：作者第一版写成 `s[len(s)//2]` —— 那是**上中位**，
    而 `statistics.median` 取**两中位平均**。而带内每条轨迹**正好 2 格**
    ⇒ 两种约定给出 4.23× 与 5.54×，**差 25%**，两个数都「看着合理」。
    ⚗⇒ 中位口径本身是**约定**不是规格 ⇒ ① 用标准式；
      ② 报告里注明是约定；③ 自检 T1c 钉住（`med([1,3])` 必须 2.0 而非 3.0），
      ⛔ 不然改这一行会静默改掉所有中位数。
    ⛔ 空序列返回 None（「未量到」），⛔ 不许当 0.0。
    """
    s = sorted(v)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


# --------------------------------------------------------------- 位点（⛔ 不手抄）
def load_k_positions(probe_path=PROBE_REL, name="_k_positions"):
    """⚖ 从**真实源码**抽出函数并 exec —— ⛔ 不手抄（手抄就是第二份实现）。

    ⛔ 三道**按构造能红**的前置，任一不成立即 HardFail：
      ① 定义存在；② 探针里**至少有一处真的调用它**（否则审计的不是仪器走的那条路）；
      ③ 调用点传 `nested=`，且 `seed` 默认值是 0（仪器不传 seed ⇒ 必须同一个）。
    """
    if not os.path.exists(probe_path):
        raise HardFail("找不到探针源码 %s ⇒ ⛔ 拒用（不许拿夹具冒充真实仪器）"
                       % probe_path)
    src = open(probe_path, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            fn = node
            break
    if fn is None:
        raise HardFail("探针源码里找不到 %s（文件 %s）" % (name, probe_path))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) == name]
    if not calls:
        raise HardFail("探针里**没有任何地方调用** %s ⇒ 审计的不是仪器走的那条路，⛔ 拒用"
                       % name)
    if not any(kw.arg == "nested" for c in calls for kw in c.keywords):
        raise HardFail("%s 的调用点没有传 `nested=` ⇒ 仪器可能用非嵌套位点，⛔ 拒用" % name)
    seg = ast.get_source_segment(src, fn)
    ns = {}
    exec(compile("import numpy as _np\n" + seg, probe_path, "exec"), ns)
    import inspect
    sig = inspect.signature(ns[name])
    if sig.parameters["seed"].default != 0:
        raise HardFail("%s 的 seed 默认值是 %r，不是 0 ⇒ 本审计算的是另一组位点，⛔ 拒用"
                       % (name, sig.parameters["seed"].default))
    return ns[name]


def shortcut_check(kpos, nsamples=64):
    """⚖⚠⚠ **J2 反证件**：证明「排列 ≠ 恒等」，否则不许报告秩/阈值。

    ⚖⚠⚠⚠ 坑一的正面处理：探针里 `if k == n: return list(range(n))` 是**恒等捷径**。
      若有人用 `kpos(n, n)` 去读排列，就会**恒定**得到「末位就是读出位点」。
    ⚗⇒ 反过来先证明 `kpos(n, n)` 确实是恒等（捷径存在），
       **且** `sorted(default_rng(0).permutation(n))` 一般**不是**它。
      两件事都成立，才允许在报告里谈「读出位点的秩」。
    """
    import numpy as np
    ident = short = diff = 0
    for n in range(7, 7 + nsamples):
        if list(kpos(n, n, nested=True)) == list(range(n)):
            ident += 1
        perm = np.random.default_rng(0).permutation(n).tolist()
        # ⚖⚠⚠⚠ 这里**必须比未排序的排列**。作者第一版写的是
        #    `sorted(permutation(n)) != list(range(n))` —— 而 `sorted(排列)`
        #    对**任意**排列都等于 `range(n)` ⇒ 那条反证件**可证恒绿**，
        #    永远给 diff>0，反过来把「捷径造出的秩」放行了。
        #    这正是修订 244.26 记的「恒绿检查台架原理上抓不到」那一类，
        #    在这里由作者本人重演一次。
        if perm != list(range(n)):
            diff += 1
    if ident == 0:
        raise HardFail("反证件失败：kpos(n,n) 都不是恒等 ⇒ 本工具对捷径的假设已失效，"
                       "⛔ 拒读（捷径若真不存在，秩的读法要重新论证）")
    if diff == 0:
        raise HardFail("反证件失败：default_rng(0).permutation(n) **恒等于** range(n) "
                       "⇒ 「秩」这个读数没有信息量，⛔ 拒读")
    return ident, diff


# --------------------------------------------------------------- 读数
def load_cells(path):
    """从读数日志里取 `{"tid"` 开头的行。⛔ 少于两档直接 HardFail。"""
    cells = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith('{"tid"'):
                cells.append(json.loads(line))
    if len(cells) < 2:
        raise HardFail("%s 里只读到 %d 格 ⇒ **未量到**，⛔ 不许当「无差异」"
                       % (path, len(cells)))
    return cells


def n_eff_of(c):
    """⚖ n_eff = P + t —— 生产者 `r204_noise_probe.py:393` 的切片是 `(pid+gen)[:P+t]`，
    且 P9 的 meas 走**整条 forward**（`use_cache=False`，:423）⇒ hook 里
    `h.shape[1] == P + t`。⛔ 用侧车的 `P`，⛔ 不用 `len(pid)`（244.26 已实测 60/60 相等）。"""
    return int(c["P"]) + int(c["t"])


def raw_response(c):
    """⚖ 响应 = 两个**实测**工作剂量上的读数之差的绝对值
    （`p9_lo_meas` / `p9_hi_meas`，对应 α=0.5·gap 与 α=1.0·gap，`:266` 附近）。
    ⚖⚠ 刻意用**原始**量而不是 `margin_meas`：后者除了分子还除以 `resid_std`
       ⇒ 单看它分不清「效应变大」与「噪声变小」。J5 要求两者同报。"""
    return abs(float(c[RESP_HI]) - float(c[RESP_LO]))


def check_cell(c, kpos):
    """⚖ **J1**：k 档必须 `k < n_eff`，否则位点集走过 `k==n` 恒等捷径。
    ⚖⚠ **J3**：`t == max(1, int(n_gen*pos_frac))` 且 `1 <= t <= n_gen`。
    返回 (n_eff, cov, direct)。任一不成立即 HardFail —— ⛔ 不许降级继续算。"""
    n = n_eff_of(c)
    ng = int(c["n_gen"])
    t = int(c["t"])
    pf = float(c["pos_frac"])
    if t != max(1, int(ng * pf)):
        raise HardFail("格 %s：t=%d != max(1,int(%d*%r))=%d ⇒ 覆盖率分母不是仪器口径"
                       % (c["tid"], t, ng, pf, max(1, int(ng * pf))))
    if not (1 <= t <= ng):
        raise HardFail("格 %s：t=%d 越界（1<=t<=n_gen=%d）" % (c["tid"], t, ng))
    if c["inject_scope"] != "k":
        return n, None, True   # all / single：见 J2 下的说明
    k = int(c["inject_n_sites"])
    if k <= 0:
        raise HardFail("格 %s：k=%d 不是正数" % (c["tid"], k))
    if k >= n:
        raise HardFail(
            "格 %s：k=%d >= n_eff=%d ⇒ `_k_positions` 会走 `if k==n: return range(n)` "
            "**恒等捷径** ⇒ 机制判定失效。⛔ 拒读（这不是小瑕疵：它恒定地给出"
            "「读出位点必在集内」）" % (c["tid"], k, n))
    pos = set(int(x) for x in kpos(n, k, nested=True))
    return n, k / float(n), (n - 1) in pos


# --------------------------------------------------------------- 分析
def k_cells(cells, kpos):
    """只取 k 档（dose ladder），⛔ 端点档（all/single）**不进**剂量轴分析：
    它们的覆盖率恒 = 1.0，不是剂量水平，而是**两种机制的端点**。"""
    out = []
    for c in cells:
        n, cov, direct = check_cell(c, kpos)
        if cov is None:
            continue
        out.append({"tid": c["tid"], "cov": cov, "direct": direct,
                    "raw": raw_response(c), "norm": float(c[RESP_NORM]),
                    "denom": float(c[RESP_DENOM]), "up": bool(c[UP])})
    return out


def by_tid(rows):
    g = collections.defaultdict(list)
    for r in rows:
        g[r["tid"]].append(r)
    return g


def traj_rhos(g):
    """逐轨迹 rho(cov, X)，X ∈ {原始响应, margin_meas, resid_std, 直接扰动}。
    ⛔ rho 为 None（零方差）⇒ 该轨迹「未量到」，⛔ 从分母里剔掉而不是当 0。"""
    res = {}
    for tid in sorted(g):
        rows = g[tid]
        cov = [r["cov"] for r in rows]
        direct = [1.0 if r["direct"] else 0.0 for r in rows]
        e = {"raw": spearman(cov, [r["raw"] for r in rows]),
             "norm": spearman(cov, [r["norm"] for r in rows]),
             "denom": spearman(cov, [r["denom"] for r in rows]),
             "direct": spearman(cov, direct)}
        e["rungs"] = len(rows)
        res[tid] = e
    return res


def pos_test(vals):
    """对一组可空的 rho 做符号检验。⛔ 分母 = **量到的**个数（剔 None）。"""
    ok = [v for v in vals if v is not None]
    n = len(ok)
    if n == 0:
        return 0, 0, None
    pos = sum(1 for v in ok if v > 0.0)
    return pos, n, sign_fisher(pos, n)


def band_compare(cells, kpos, lo=0.20, hi=0.60):
    """⚖ **J7** 匹配覆盖率带内比两种机制，**轨迹级**。

    ⚖⚠⚠ 为什么必须是轨迹级：格数不等于样本量（同轨迹的格共用问题/prompt/轨迹）。
    ⚖ 落在带里**只有一种机制**的轨迹才是可用的配对单位；两样都有的轨迹
    在带内做配对会同时用到两条格，本工具分开报。
    """
    rows = []
    for c in cells:
        n, cov, direct = check_cell(c, kpos)
        if cov is None or not (lo <= cov <= hi):
            continue
        rows.append({"tid": c["tid"], "cov": cov, "direct": direct,
                     "raw": raw_response(c), "up": bool(c[UP])})
    g = by_tid(rows)
    only_p, only_d = [], []
    for tid in sorted(g):
        rr = g[tid]
        if any(r["direct"] for r in rr) and any(not r["direct"] for r in rr):
            continue                       # 带内混合 ⇒ 归入 mixed，另行报
        (only_d if rr[0]["direct"] else only_p).append(
            (tid, med([r["raw"] for r in rr]), med([1.0 if r["up"] else 0.0
                                                   for r in rr])))
    mp = med([v for _, v, _ in only_p]) if only_p else None
    md = med([v for _, v, _ in only_d]) if only_d else None
    ratio = (md / mp) if (mp not in (None, 0.0) and md is not None) else None
    return {"n_prop": len(only_p), "n_direct": len(only_d),
            "n_mixed": sum(1 for tid in g if len({r["direct"] for r in g[tid]}) > 1),
            "med_prop": mp, "med_direct": md, "ratio": ratio,
            "up_prop": med([u for _, _, u in only_p]) if only_p else None,
            "up_direct": med([u for _, _, u in only_d]) if only_d else None,
            "lo": lo, "hi": hi}


def ladder_same(cells_a, cells_b, kpos):
    """⚖ **J4**：两臂的 (tid, 覆盖率) 阶梯必须逐格相同，否则剂量轴不可比 ⇒ HardFail。

    ⚖⚠⚠⚠ 比的是 **(tid, 覆盖率) 集合**，⛔ 不是「档序号」。
      理由（坑二）：每条轨迹的 k 档数是 **7/8/9 三种**（`n_eff < 1024` 的档被丢、
      `p03__think` 多一个人工补档），按档序号排名会把 k 档与端点**混进同一列**。
    ⚖⚠⚠ T4 必须**调用本函数**并看它报不报；
      ⛔ 只在自检里比夹具的两份 key 是不是不等 —— 那是**恒绿检查**
      （夹具不等是构造出来的，与判据无关）。作者第一版就是这么写的。
    """
    ka = sorted((r["tid"], round(r["cov"], 9)) for r in k_cells(cells_a, kpos))
    kb = sorted((r["tid"], round(r["cov"], 9)) for r in k_cells(cells_b, kpos))
    if ka != kb:
        only_a = sorted(set(ka) - set(kb))
        only_b = sorted(set(kb) - set(ka))
        raise HardFail(
            "【J4】两臂的 (tid, 覆盖率) 阶梯**不一致** ⇒ 剂量轴不可比，⛔ 拒读。"
            "只在 A：%d 条，只在 B：%d 条" % (len(only_a), len(only_b)))
    return len(ka)


def j5_verdict(m_raw, m_norm, m_denom):
    """⚖ **J5**：梯度会不会只是「分母变小」造出来的？

    ⚗ 判别式：归一化量 = 原始量 ÷ resid_std。⇒ 若 `resid_std` 随覆盖率**上升**，
    归一化会把梯度**压小** ⇒ 梯度是真的变大；反之归一化量上的梯度强于原始量
    ⇒ ⚠ 梯度**可能部分来自分母**，⛔ 不许把 `margin_meas` 的梯度当「效应变大」。
    ⛔ 任一为 None（零方差）⇒ 返回 "未量到"，⛔ 不许当「梯度是真的」。
    """
    if m_raw is None or m_norm is None or m_denom is None:
        return "未量到"
    return "压小" if m_raw > m_norm else "可疑"


def j6_collinear(pos_d, n_d, pos_r, n_r):
    """⚖ **J6**：机制轴是否与剂量轴共线 ⇒ 剂量与机制不可分离。

    ⛔ 两条**都**满符号才判共线；单边满符号**不**判。
    ⚖⚠ 双向都要钉：恒返回 True 会让「不可分离」变成一句永远成立的话。
    """
    if not n_d or not n_r:
        return None
    return (pos_d >= n_d) and (pos_r >= n_r)


def j7_smalln(n_direct, n_prop):
    """⚖ **J7**：n < 10 ⇒ 这个倍数**不可做显著性判断**。
    ⚖⚠ 双向都要钉：恒返回 True 会把每个读数都打上「无力检出」的标签。
    """
    if n_direct <= 0 or n_prop <= 0:
        return None
    return min(n_direct, n_prop) < 10


def report(cells_w, cells_r, kpos, lo=0.20, hi=0.60, cells_a=None, cells_b=None):
    """出报告。cells_a/cells_b 若给出，则额外做 J4（两臂阶梯逐格一致）。"""
    L = []
    ident, diff = shortcut_check(kpos)
    L.append("【0】前置与反证件（J1/J2/J3）")
    L.append("  ✓ `_k_positions(n,n)` 恒等于 range(n) 的样本：%d/%d ⇒ 捷径确实存在"
             % (ident, ident + diff))
    L.append("  ✓ default_rng(0).permutation(n) **不是** range(n) 的样本：%d ⇒ "
             "「秩」这个读法有信息量" % diff)

    rw, rr_ = k_cells(cells_w, kpos), k_cells(cells_r, kpos)
    L.append("  ✓ k 档格数：w=%d rand=%d（端点档 all/single 各 %d 格已剔出剂量轴）"
             % (len(rw), len(rr_), len(cells_w) - len(rw)))

    # ⚖ J4 默认就要比**两臂**（w vs rand）—— 这是「剂量轴可比」的必要条件。
    # ⚖⚠⚠ 若两臂档数不同（曾实测 7/8/9 三种），「按档序排名」就会把 k 档与端点混列，
    #    所以比的是 **(tid, 覆盖率) 集合**，⛔ 不是「档序号」。
    if cells_a is not None and cells_b is not None:
        n_same = ladder_same(cells_a, cells_b, kpos)
        L.append("  ✓ J4：两臂 (tid, 覆盖率) 阶梯**逐格相同**（%d 档）⇒ 剂量轴可比"
                 % n_same)

    L.append("")
    L.append("【1】剂量—响应梯度是否存在（轨迹级 Spearman，n=独立轨迹数）")
    L.append("  ⚖ 响应 = |p9_hi_meas − p9_lo_meas|（**原始**量，⛔ 不用 margin_meas）")
    L.append("  ⚖⚠ margin_meas 的分母 resid_std **同列印出**：")
    L.append("     若 resid_std 也随覆盖率同向上升 ⇒ 归一化**压低**了梯度，")
    L.append("     ⇒ 梯度**不是**「噪声变小」造出来的（J5）。")
    res = {}
    for name, rows in (("w", rw), ("rand", rr_)):
        g = by_tid(rows)
        r = traj_rhos(g)
        res[name] = r
        L.append("  ── %s 臂（%d 条轨迹，k 档/轨迹 中位 %d）"
                 % (name, len(r), med([v["rungs"] for v in r.values()])))
        for key, label in (("raw", "rho(覆盖率, 原始响应)"),
                           ("denom", "rho(覆盖率, resid_std 分母)"),
                           ("norm", "rho(覆盖率, margin_meas)"),
                           ("direct", "rho(覆盖率, 直接扰动)")):
            vals = [r[t][key] for t in sorted(r)]
            pos, n, p = pos_test(vals)
            got = [v for v in vals if v is not None]
            L.append("     %-24s 正号 %2d/%-2d  p=%s  中位 rho=%s"
                     % (label, pos, n,
                        ("%.3g" % p) if p is not None else "**未量到**",
                        ("%+.3f" % med(got)) if got else "**未量到**"))
        # ⚖ **J5 判定**：梯度会不会只是「分母变小」造出来的？—— 从数据算，不写死。
        mr = med([v for v in [r[t]["raw"] for t in sorted(r)] if v is not None])
        mn = med([v for v in [r[t]["norm"] for t in sorted(r)] if v is not None])
        md_ = med([v for v in [r[t]["denom"] for t in sorted(r)] if v is not None])
        if mr is None or mn is None or md_ is None:
            L.append("     J5：**未量到**（某一列零方差）⇒ ⛔ 不许谈归一化混淆")
        else:
            verdict = j5_verdict(mr, mn, md_)
            L.append("     J5：原始 rho(%+.3f) vs 归一化 rho(%+.3f)，分母 rho=%+.3f ⇒ %s"
                     % (mr, mn, md_, verdict))
            if verdict == "压小":
                L.append("         ⇒ 噪声（resid_std）随覆盖率**变大**，归一化把梯度"
                         "**压小**了 ⇒ 梯度**不是**「噪声变小」造出来的")
            else:
                L.append("         ⇒ ⚠⚠ 归一化量上的梯度**强于**原始量 ⇒ 梯度可能"
                         "**部分来自分母**，⛔ 不许把 margin_meas 的梯度当效应变大")

    L.append("")
    L.append("【2】剂量轴与机制轴**是否共线**（J6）")
    for name in ("w", "rand"):
        r = res[name]
        pr, n, p = pos_test([r[t]["direct"] for t in sorted(r)])
        qr, n2, p2 = pos_test([r[t]["raw"] for t in sorted(r)])
        col = j6_collinear(pr, n, qr, n2)
        if col is None:
            L.append("  ⚠ %s 臂：机制轴或响应轴**未量到** ⇒ ⛔ 不许说「可分离」"
                     "也不许说「不可分离」" % name)
        elif col:
            L.append("  ⚠⚠ %s 臂：覆盖率↔**机制**（%d/%d 正号, p=%s）与"
                     "覆盖率↔**响应**（%d/%d 正号, p=%s）**同时强正**"
                     % (name, pr, n, ("%.3g" % p) if p else "?", qr, n2,
                        ("%.3g" % p2) if p2 else "?"))
            L.append("       ⇒ 剂量与机制在这套阶梯里**不可分离**：")
            L.append("       ⛔ 任何「响应随剂量升高」的读数，都同时是"
                     "「离读出位点更近」的读数。")
        else:
            L.append("  ✓ %s 臂：机制轴未与剂量轴**同时**满符号（机制 %d/%d，响应 %d/%d）"
                     " ⇒ 未见共线" % (name, pr, n, qr, n2))
    same = True
    for t in sorted(set(res["w"]) & set(res["rand"])):
        a_, b_ = res["w"][t]["direct"], res["rand"][t]["direct"]
        if a_ is None or b_ is None or abs(a_ - b_) > 1e-12:
            same = False
            break
    L.append("  ⚖ 两条臂的直接扰动 rho **逐轨迹应完全相同**（它是阶梯几何的性质，"
             "与臂无关）⇒ 实测相同=%s" % same)

    L.append("")
    L.append("【3】**匹配覆盖率**带 [%.2f, %.2f] 内：直接 vs 传播（J7）"
             % (lo, hi))
    for name, cells in (("w", cells_w), ("rand", cells_r)):
        bc = band_compare(cells, kpos, lo, hi)
        if bc["ratio"] is None:
            L.append("  ── %s 臂：**未量到**（带内 仅直接=%d / 仅传播=%d，"
                     "⛔ 分母为 0 不许印「无差异」）"
                     % (name, bc["n_direct"], bc["n_prop"]))
            continue
        L.append("  ── %s 臂：轨迹级 仅直接 n=%d、仅传播 n=%d、带内混合 %d 条（混合者不参与）"
                 % (name, bc["n_direct"], bc["n_prop"], bc["n_mixed"]))
        L.append("     原始响应中位数：直接 %.6f vs 传播 %.6f ⇒ **倍数 %.2f**"
                 % (bc["med_direct"], bc["med_prop"], bc["ratio"]))
        if bc["up_direct"] is not None:
            L.append("     通过率中位数：直接 %.2f vs 传播 %.2f"
                     % (bc["up_direct"], bc["up_prop"]))
        nmin = min(bc["n_direct"], bc["n_prop"])
        small = j7_smalln(bc["n_direct"], bc["n_prop"])
        if small is None:
            L.append("     ⚠⚠ 有一侧 n=0 ⇒ 该倍数是**未量到**，⛔ 不许印成「无差异」")
        elif small:
            L.append("     ⚠⚠ n=%d < 10 ⇒ 这个倍数**不可做显著性判断**："
                     "「未量到」不是「没有」，也不是「已确证」。" % nmin)
    L.append("  ⚖⚠⚠ 这个倍数若显著大于 1 ⇒ 机制效应 ≫ 层内剂量效应，")
    L.append("     ⇒ 「剂量—响应」曲线上占主导的斜率来自**是否触及读出位点**。")

    L.append("")
    L.append("【4】本工具**依赖**、但**没有**自己验的（⛔ 不许说成端到端）")
    L.append("  ⚖ J1/J2 验的是**位点集**；生产者是整条 forward（`use_cache=False`, :423）")
    L.append("     ⇒ hook 里 `h.shape[1] == P + t` 属**代码阅读**，非本工具实测。")
    L.append("  ⚖ `all` / `single` 两档按**读码**判为直接（`:150` 广播全体；")
    L.append("     `:176` `j = min(inj, h.shape[1]-1)` 且 `inj = ids.shape[1]-1`, :394）")
    L.append("     ⇒ 它们必含读出位点；⚠ 这是**按源码推断**，本工具未在 GPU 上验。")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def _stub_kpos(n, k, seed=0, nested=False):
    """⚖ **夹具**：忠实复制探针里 `_k_positions` 的行为，⛔ 含 `k==n` 恒等捷径。
    ⚖⚠⚠ 这个捷径就是坑一的成因 —— 夹具必须**带上它**，
    否则 T1 的反证件会假绿（验的是另一个函数）。"""
    import numpy as np
    n, k = int(n), int(k)
    if k == n:
        return list(range(n))          # ⚖⚠⚠ 探针里的恒等捷径，原样保留
    if k == 0:
        return []
    if nested:
        return sorted(int(x) for x in np.random.default_rng(int(seed)).permutation(n)[:k])
    return sorted(np.random.default_rng(int(seed)).choice(n, size=k,
                                                          replace=False).tolist())


def _cell(tid, scope, k, P, t, n_gen, m_lo, m_hi, resid, up, pf=0.5):
    c = {"tid": tid, "inject_scope": scope, "inject_n_sites": k, "P": P, "t": t,
         "n_gen": n_gen, "pos_frac": pf, RESP_HI: m_hi, RESP_LO: m_lo,
         RESP_NORM: abs(m_hi - m_lo) / resid if resid > 0 else float("inf"),
         RESP_DENOM: resid, UP: up}
    return c


def selftest(probe_path=None):
    ok, bad = [], []
    kpos = _stub_kpos
    real_note = ""

    def chk(tid_, cond, why=""):
        (ok if cond else bad).append(tid_)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (tid_, why))

    # T1 反证件：捷径存在 + 排列≠恒等（坑一的正面处理）
    try:
        ident, diff = shortcut_check(kpos)
        chk("T1", ident > 0 and diff > 0,
            "反证件：恒等样本 %d、非恒等样本 %d" % (ident, diff))
    except HardFail as e:
        chk("T1", False, "shortcut_check 抛 HardFail: %s" % e)

    # T1b ⚠ 破坏夹具：把「排列≠恒等」的检查废掉 ⇒ shortcut_check 必须抛
    #    （恒绿检查只能靠「用破坏条件的夹具看它报不报」抓住）
    import numpy as _np
    real_perm = _np.random.default_rng

    class _DegenerateRng:
        def __init__(self, seed=0):
            pass

        def permutation(self, n):
            return _np.arange(n)          # ⚖ 故意让排列 == range(n)

        def choice(self, n, size=None, replace=False):
            return _np.arange(size or n)

    try:
        _np.random.default_rng = lambda seed=0: _DegenerateRng(seed)
        try:
            shortcut_check(kpos)
            chk("T1b", False, "排列恒等于 range(n) 时 shortcut_check 竟没抛 ⇒ J2 是恒绿")
        except HardFail:
            chk("T1b", True, "排列恒等于 range(n) 时 shortcut_check 正确拒读")
        except Exception as e:
            chk("T1b", False, "抛的是 %s 而非 HardFail" % type(e).__name__)
    finally:
        _np.random.default_rng = real_perm

    # T1c ⚖ 中位口径：偶数长度必须取两中位平均（⛔ 不是上中位）
    #     这条不是装饰：上中位 vs 平均让带内倍数从 4.23 变成 5.54（差 25%）。
    chk("T1c", med([1.0, 3.0]) == 2.0 and med([1.0, 2.0, 3.0]) == 2.0
        and med([3.0, 1.0]) == 2.0 and med([]) is None,
        "med 偶数取平均、奇数取中位、空=>None")

    # T2 J1 能红：k >= n_eff 的格必须 HardFail（恒等捷径 ⇒ 机制判定失效）
    bad_cell = _cell("t1", "k", 64, 10, 54, 108, 0.0, 1.0, 0.05, True)
    try:
        check_cell(bad_cell, kpos)
        chk("T2", False, "k=64>=n_eff=64 竟过了 ⇒ J1 是恒绿")
    except HardFail:
        chk("T2", True, "k>=n_eff 的格被 J1 拒读")

    # T2b J1 的正常侧：k = n_eff-1 必须过（防止判据过严）
    good_cell = _cell("t1", "k", 63, 10, 54, 108, 0.0, 1.0, 0.05, True)
    try:
        n, cov, direct = check_cell(good_cell, kpos)
        chk("T2b", cov is not None and n == 64, "k=n_eff-1 正常通过（cov=%.4f）" % cov)
    except HardFail as e:
        chk("T2b", False, "J1 过严：k=n_eff-1 被拒（%s）" % e)

    # T3 J3 能红：t 与 max(1,int(n_gen*pos_frac)) 不符必须 HardFail
    broken = _cell("t1", "k", 8, 10, 30, 108, 0.0, 1.0, 0.05, True)
    try:
        check_cell(broken, kpos)
        chk("T3", False, "t=30 != max(1,int(108*0.5))=54 竟过了 ⇒ J3 是恒绿")
    except HardFail:
        chk("T3", True, "t 与 n_gen*pos_frac 不符被 J3 拒读")

    # T4 **J4 能红**：两臂阶梯不一致必须让 ladder_same 抛
    # ⚖⚠⚠⛔ 作者第一版在自检里写的是「两份夹具的 key 本来就不等」——
    #   那是**恒绿检查**（夹具不等是构造出来的，与判据无关）。
    #   正确形态：**调用判据**并看它报不报。
    P4, T4_, NG4 = 10, 54, 108
    a = [_cell("s0", "k", 4, P4, T4_, NG4, 0.0, 1.0, 0.05, True),
         _cell("s1", "k", 8, P4, T4_, NG4, 0.0, 1.0, 0.05, True)]
    b = [_cell("s0", "k", 4, P4, T4_, NG4, 0.0, 1.0, 0.05, True),
         _cell("s1", "k", 7, P4, T4_, NG4, 0.0, 1.0, 0.05, True)]
    try:
        ladder_same(a, b, kpos)
        chk("T4", False, "阶梯不一致却没抛 ⇒ J4 是恒绿")
    except HardFail:
        chk("T4", True, "阶梯不一致被 J4 拒读")
    # T4b 正常侧：完全相同的两臂必须通过（防判据过严）
    try:
        n4 = ladder_same(a, a, kpos)
        chk("T4b", n4 == 2, "相同阶梯通过（%d 档）" % n4)
    except HardFail as e:
        chk("T4b", False, "J4 过严：相同阶梯被拒（%s）" % e)

    # T10 **J5 双向**：梯度真变大 ⇒ 压小；归一化更强 ⇒ 可疑
    chk("T10", j5_verdict(0.76, 0.67, 0.86) == "压小"
        and j5_verdict(0.60, 0.90, -0.80) == "可疑"
        and j5_verdict(None, 0.9, 0.8) == "未量到",
        "J5 两向：原始>归一化⇒压小；归一化>原始⇒可疑；None⇒未量到")

    # T11 **J6 双向**：两条都满符号⇒共线；单边满⇒不判；分母 0⇒None
    chk("T11", j6_collinear(14, 14, 14, 14) is True
        and j6_collinear(14, 14, 7, 14) is False
        and j6_collinear(5, 14, 14, 14) is False
        and j6_collinear(0, 0, 14, 14) is None,
        "J6 两向：双满⇒共线；单边满⇒不判；分母 0⇒未量到")

    # T12 **J7 双向**：n<10⇒要喊；n>=10⇒不许喊；一侧 0⇒未量到
    # ⚖⚠ 第一版这里写 `j7_smalln(12, 9) is False` ⇒ 当场报红。
    #   查下去是**测试的期望值算错了**（min(12,9)=9，仍 < 10 ⇒ 该喊），
    #   ⛔ 不是判据错 —— 「小的那个」才是分母，不是求和。
    chk("T12", j7_smalln(3, 7) is True and j7_smalln(12, 9) is True
        and j7_smalln(12, 12) is False and j7_smalln(0, 7) is None,
        "J7 两向：n=3 与 n=min 9⇒要喊；n=12/12⇒不喊；一侧 0⇒未量到")

    # T5 binom2 边界：k=n 必须给 p<=1（坑：曾印出 p=2）
    chk("T5", 0.0 <= binom2(14, 14) <= 1.0, "binom2(14,14)=%.3g 在 [0,1]"
        % binom2(14, 14))

    # T5c ⚖⚠ **精确值**断言 —— 没有这条，`p = 1.0` 的变异**存活**：
    #     T5 只查 p∈[0,1]（1.0 也在范围内 ✓ 过），
    #     T6 只查对称处恰为 1.0（硬编码 1.0 也满足 ✓ 过）。
    # ⚗⇒ **范围断言是弱守卫**：任何落在范围内的常数都能过它。
    exact = 2.0 / 2.0 ** 14
    got = binom2(14, 14)
    chk("T5c", abs(got - exact) < 1e-15 and abs(binom2(0, 14) - exact) < 1e-15,
        "binom2(14,14)=binom2(0,14)=%.10g（应恰为 2/2^14）" % got)

    # T5b binom2 越界必须 HardFail（k>n 不许静默）
    try:
        binom2(15, 14)
        chk("T5b", False, "binom2(15,14) 竟没抛 ⇒ J8 是恒绿")
    except HardFail:
        chk("T5b", True, "binom2 的 k>n 越界被拒")

    # T6 ⛔ 不能把 min(1.0,·) 换成 1.0（244.23 的变异，本轮重演）
    #     判别方式：k=n/2 对称处，双尾必须**等于 1.0**（截断生效），
    #     而非被某个别的常数决定
    # ⚖⚠⚠ 这里的 except 不是装饰：去掉截断会让 binom2 **抛** HardFail
    #   （范围断言先抓到）⇒ 若不接住，整轮自检以崩收场，
    #   而台架把「崩」判成「台架坏了」而不是「这条判据咬住了」。
    #   ⚗⇒ 要的是**干净的按判据变红**，不是崩。
    try:
        sym = binom2(7, 14)
        chk("T6", abs(sym - 1.0) < 1e-12,
            "binom2(7,14)=%.6f（对称处截断后恰为 1.0）" % sym)
    except HardFail as e:
        chk("T6", False, "binom2(7,14) 抛 HardFail ⇒ 截断没生效：%s" % e)

    # T7 J7：n<10 必须给出「不可做显著性判断」；n>=10 不许常喊
    # ⚖⚠⚠ 夹具怎么造：机制（是否含读出位点）**只由 (n_eff, k) 决定**，
    #   而覆盖率约等于 0.31 ⇒ 若所有夹具共用同一个 n_eff，它们会**全部同机制**
    #   ⇒ 一个空组 ⇒ T7 会假绿（分母为 0 时 ratio=None，看起来"对了"）。
    # ⚗⇒ 必须扫**不同的 n_eff**（覆盖率不变）才能同时造出两种机制。
    need_d, need_p, cells = [], [], []
    NG = 108
    t = max(1, int(NG * 0.5))
    for neff in range(64, 4000):
        k = max(1, int(round(0.3125 * neff)))
        if k >= neff or (neff - t) < 1:
            continue
        c = _cell("probe%d" % neff, "k", k, neff - t, t, NG, 0.0, 0.0, 0.05, True)
        try:
            _, cov, direct = check_cell(c, kpos)
        except HardFail:
            continue
        if not (0.20 <= cov <= 0.60):
            continue
        if direct and len(need_d) < 3:
            need_d.append(neff)
        elif not direct and len(need_p) < 7:
            need_p.append(neff)
        if len(need_d) == 3 and len(need_p) == 7:
            break
    for i, neff in enumerate(need_d):          # 直接档给大响应
        cells.append(_cell("d%d" % i, "k", max(1, int(round(0.3125 * neff))),
                           neff - t, t, NG, 0.0, 0.30, 0.05, True))
    for i, neff in enumerate(need_p):          # 传播档给小响应
        cells.append(_cell("p%d" % i, "k", max(1, int(round(0.3125 * neff))),
                           neff - t, t, NG, 0.0, 0.06, 0.05, False))
    bc = band_compare(cells, kpos)
    small = min(bc["n_direct"], bc["n_prop"]) < 10
    ratio_ok = bc["ratio"] is not None and bc["ratio"] > 4.0
    chk("T7", small and ratio_ok and bc["n_mixed"] == 0,
        "带内 仅直接 n=%d / 仅传播 n=%d / 混合 %d、倍数 %.2f ⇒ 必须标为不可做显著性判断"
        % (bc["n_direct"], bc["n_prop"], bc["n_mixed"], bc["ratio"] or float("nan")))

    # T7b 分母为 0 时不许印「无差异」
    only_p = [_cell("p%d" % i, "k", 20, P4, T4_, NG4, 0.0, 0.06, 0.05, False)
              for i in range(4)]
    bc0 = band_compare(only_p, kpos)
    chk("T7b", bc0["ratio"] is None and bc0["n_direct"] == 0,
        "带内无直接档 ⇒ ratio=None（**未量到**），⛔ 不许当 1.0")

    # T8 零方差 ⇒ None（未量到），⛔ 不许当 0.0
    flat = [_cell("f0", "k", 4, P4, T4_, NG4, 0.1, 0.1, 0.05, True),
            _cell("f0", "k", 8, P4, T4_, NG4, 0.1, 0.1, 0.05, True)]
    g = by_tid(k_cells(flat, kpos))
    rr = traj_rhos(g)["f0"]
    chk("T8", rr["raw"] is None and rr["denom"] is None,
        "响应零方差 ⇒ rho=None（**未量到**），⛔ 不许当 0.0")

    # T9 ⚖ 若探针源码可达，用**真函数**再跑一遍 J1/J2（夹具≠真实仪器）
    if probe_path and os.path.exists(probe_path):
        try:
            real = load_k_positions(probe_path)
            ident, diff = shortcut_check(real)
            n, cov, d = check_cell(good_cell, real)
            chk("T9", ident > 0 and diff > 0 and cov is not None,
                "真 _k_positions：恒等 %d、非恒等 %d、k=n-1 的 cov=%.4f"
                % (ident, diff, cov))
        except HardFail as e:
            chk("T9", False, "真函数上 J1/J2 抛 HardFail: %s" % e)
        except Exception as e:
            chk("T9", False, "真函数上抛 %s: %s" % (type(e).__name__, e))
    else:
        real_note = "  ⚠ T9 未运行（探针源码不可达：%r）⇒ 只验了夹具\n" % (
            probe_path or PROBE_REL,)
        print(real_note, end="")

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


# --------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(
        description="审计「剂量—响应」阶梯的剂量轴（零 GPU）")
    ap.add_argument("--w-log", default=None, help="w 臂读数日志")
    ap.add_argument("--rand-log", default=None, help="rand 臂读数日志")
    ap.add_argument("--arm2-log", default=None,
                    help="可选：第二个臂的日志，用于 J4 阶梯一致性")
    ap.add_argument("--probe", default=PROBE_REL, help="探针源码路径")
    ap.add_argument("--lo", type=float, default=0.20, help="匹配带下界")
    ap.add_argument("--hi", type=float, default=0.60, help="匹配带上界")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest(args.probe)

    # ⚖ 「没给日志」不许退化成「没差异」⇒ 显式 HardFail，不静默当空。
    if not args.w_log or not args.rand_log:
        raise HardFail("必须同时给 --w-log 与 --rand-log（⛔ 少一臂 ⇒ 无法比，"
                       "不许把「没量到」当「无差异」）")
    kpos = load_k_positions(args.probe)
    cw = load_cells(args.w_log)
    cr = load_cells(args.rand_log)
    ca = load_cells(args.arm2_log) if args.arm2_log else cw
    cb = cr
    txt, rc = report(cw, cr, kpos, args.lo, args.hi, ca, cb)
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
