#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dose_confound_audit.py —— 那个 k/n 符号判决是不是**被剂量轴混淆**了（零 GPU）

🔴🔴 **本工具问什么**
  账本的判决是「逐轨迹取 `up_mono_meas` **多数**」。可 244.47 说：
  **R 再大也不改变那个 p**，且能答问题的是**幅度**口径。
  ⚖⚠⚠⚠ 但在走幅度之前必须先问一件更基本的事：
  **那些「格」之间到底是不是同一个东西？**

⚖⚠⚖⚖⚖ **实测结论（本工具算出来的，不是推的）**

  那 137 格里 —— `inject_scope=k` 的 109 格是**注入位点数扫描**，
  位点数从 **1 一直到 4655**；外加 `scope=single` 14 格与 `scope=all` 14 格。
  ⚖⚠⚠⚠ **它们⛔ 不是同一条件下的重复测量，而是不同剂量。**

  ⇒ 逐轨迹的「多数为真」= **跨不同剂量的多数**
  ⇒ **符号翻转与剂量效应在 w 臂上完全混淆** ⇒ ⛔ 在固定剂量之前，
     「12/14 是不是噪声」**原理上不可分辨**。

⚖⚠ **w 臂上剂量效应是实测到的（注入比例轴，Spearman +0.691）**：

      比例分档          格数   d 中位     为正
      最低四分位        27    -0.0000    11/27   ← 接近抛硬币
      次低              28    +0.0026    16/28
      次高              30    +0.1250    23/30
      最高              24    +0.8684    24/24   ← 全正

  ⚖⇒ 那个 12/14 的**大部分来自高注入比例那几档**；最低档 11/27 与抛硬币无异。
⚖ **rand 臂没有剂量趋势**（Spearman +0.024）⇒ 它的 6/14 **不是**剂量驱动的。

⚠⚠⚖⚖⚖ **修订 244.50：更正 244.49 自己的分母（同一个位置栽了第二次）**

  ⚖ 244.49 用 `P + n_gen − 1` 当分母。探针 `.cache/mutbak/r204_noise_probe.py:406-410`
     的**原式**是：

         P   = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)
         n   = len(gen)
         t   = max(1, int(n * a.pos_frac))          ← ⛔ 不是 n
         ids = torch.tensor([(pid + gen)[: P + t]])
         inj = ids.shape[1] - 1

  ⚖⚠⚠⚠ 两臂 137 条记录的 `pos_frac` **全为 0.5** ⇒ `t = n_gen/2`
     ⇒ 244.49 的分母**大了 1.58…1.96 倍**（⚠⚠ **逐轨迹不等**，见下）。
     ⇒ 更正后：分母范围 **384 … 5319（13.9 倍）**，比例范围 **0.0003 … 0.8758**。

  ⚖⚠⚠⚠⚖⚠⚠ **⚠ 我自己先写错了一条，现更正**：244.50 动手前我以为
     「分母差个常数 0.5 ⇒ 秩不变 ⇒ rho 与分档表都不动」⇒ **错**。

     ⚖ 旧分母 `P+n_gen−1` ⛔ **不是** 新分母 `P+⌊n·pf⌋−1` 的常数倍：
        `(P+n_gen−1)/(P+n_gen/2−1)` **有 14 个不同取值，落在 1.5755 … 1.9649**
        （随该轨迹的 P/n_gen 比变化）⇒ **秩会变** ⇒ rho 与分档**都变**。

     ⚖ **并排实测（同一批 109 格；旧式已逐位复现账本 244.49）**：

        旧式 P+n_gen−1    rho=+0.685  分位点 0.008/0.127/0.382  档 27/28/27/27  正 11/16/20/27
        新式 P+⌊n·pf⌋−1   rho=+0.691  分位点 0.015/0.250/0.750  档 27/28/30/24  正 11/16/23/24

     ⚖⚖ **真正不变的只有两样**：① 109 格里**为正的总格数 = 74**（同一批格重新分组）；
        ② 定性结论（w 臂单调、最低档 ≈ 抛硬币、最高档全正）。
     ⚖ **变的**：rho（+0.685→+0.691）、分位点、**分档表本身**（27/28/27/27 → 27/28/30/24）。

  ⚖⚠ 244.48 栽的是「拿**个数**当剂量轴」；244.49 栽的是「分母算错一整个因子」。
     ⚗ 同一条**剂量轴**上栽两次 ⇒ 剂量轴的每一个常数都**必须照探针原式抄**，
       ⛔ 不许按公式「推」。⇒ 新增禁令 **㊶**（见文件末尾）。

⚠⚠⚠ **本节的限制（写在这里以免被当成全绿）**
  · ⚠⚠⚠ **分母 `inj` 仍不在记录里**。本工具按上面那条**原式**重算，
    它成立的前提有两条：① `P == len(pid)`；② `pos_frac ≤ 1`（否则
    `(pid+gen)[:P+t]` 会被 `len(pid)+n` 截断，分母变成 `len(pid)+n−1`）。
    ⚖ **C2c 把第 ② 条量出来**（`pos_frac` 取值集合 + 是否可能截断）。
    ⚖⚠ 第 ① 条**记录里验不到**（`P` 优先取 `extra.prompt_tokens`，
    取不到才回退 `len(pid)`）⇒ 列入「没验的」。
  · 只用了每臂**一个**结果文件；跨文件一致性由「多数计数必须复现账本的
    12/14 / 6/14」这条判据把关。
  · `inject_scope` 的三类（single / k / all）**混在一起**参与多数，
    ⛔ 而它们注入的量根本不同。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不写数据文件。
⚖⚠⚠⚖ 每条判据都必须**能红**：变异台改的是喂进来的**数据形状**。

⚖⚠⚖⚖⚖ **新增禁令 ㊶（244.50 的元教训，写在这里防止再犯）**

  ⚖ **「更正一个常数」⛔ 不等于「乘一个常数」。**
  ⚗⇒ 判别式：**并排把更正前后两个版本都算一遍**，逐项写清
     「真的不变 / 真的变了」。⛔ **不许靠「同一批格重新分组 ⇒ 不变」的直觉断言。**
  ⚖ 反例就在本文件：`P+n_gen−1` 与 `P+⌊n·pf⌋−1` 的比值**逐轨迹不同**
     ⇒ 秩变了 ⇒ **rho 和分档表都变了**；只有「总为正格数 74」与定性结论不变。
  ⚖⚠ 推论：**凡是要写进账本的「不受影响」，必须先实测过** ——
     它是最容易整段作废、而写起来最像已验证的那种断言。
"""

import argparse
import ast
import io
import json
import math
import os
import statistics as _st
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
# ⚖ 两个**已入库**的结果文件（.cache/ 被 ignore ⇒ 只作默认，不入库）
DEFAULT_FILES = {"w": ".cache/r244/_an.txt", "rand": ".cache/r244/_ra.txt"}
# ⚖⚠ 账本 244.43 记的计数：**判据必须复现它**，否则说明读的不是那一批
LEDGER_COUNT = {"w": 12, "rand": 6}
N_TRAJ = 14


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 小工具
def load_jsonl(path):
    """⚖ 逐行读 JSON。⚖⚠⚠⚠ 缺失/坏行必须**报错**，⛔ 不许静默跳过 ——
    静默跳过会让「读到了 137 条」看起来像「全部都在」。"""
    out, bad = [], 0
    for i, line in enumerate(io.open(path, encoding="utf-8", errors="replace"), 1):
        t = line.strip()
        if not t.startswith("{"):
            continue
        try:
            out.append(json.loads(t))
        except Exception:
            bad += 1
    if bad:
        raise HardFail("文件 %s 有 %d 行 JSON 解析失败 ⇒ ⛔ 拒读（不许跳过后当全量）"
                       % (path, bad))
    if not out:
        raise HardFail("文件 %s 一条记录都没有 ⇒ ⛔ 拒读" % path)
    return out


def rank(v):
    s = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[s[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    """⚖ Spearman 秩相关。⚖⚠⚠⚠ **必须逐条秩**（并列取平均秩），
    ⛔ 不许用 numpy 的默认名次（并列会给不同名次 ⇒ 静默错一个值）。"""
    if len(xs) != len(ys) or len(xs) < 3:
        raise HardFail("Spearman 需要成对且 n≥3（得到 %d,%d）" % (len(xs), len(ys)))
    rx, ry = rank(xs), rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx)
                    * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def d_of(rec):
    """⚖ 一格的 lo→hi 实测差。⚖⚠⚠⚠ 缺 `p9_lo_meas` 必须**拒读**，
    ⛔ 不许当成 0（那是「没量到」被渲染成 0 的老坑）。"""
    lo, hi = rec.get("p9_lo_meas"), rec.get("p9_hi_meas")
    if lo is None or hi is None:
        raise HardFail("记录 %r 缺 p9_lo_meas/p9_hi_meas ⇒ **未量到**，⛔ 不许当 0"
                       % (rec.get("tid"),))
    return float(hi) - float(lo)


def denom_of(rec):
    """⚖⚖⚖ 一格的**可注入位置总数** `inj`，**照探针原式抄**。

    ⚖ 探针 `.cache/mutbak/r204_noise_probe.py:406-410`：

        P   = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)
        n   = len(gen)
        t   = max(1, int(n * a.pos_frac))
        ids = torch.tensor([(pid + gen)[: P + t]], ...)
        inj = ids.shape[1] - 1

    ⚖⚠⚠⚠⚖⚠ **修订 244.50**：244.49 写的是 `P + n_gen − 1`，**整整大了一倍**。
       ⛔ ⛔ **`pos_frac` 必须实取**：`t = max(1, int(n_gen * pos_frac))`，
       而两臂 137 条记录的 `pos_frac` **全为 0.5** ⇒ `t = n_gen/2`。
       ⚖⚠ **硬编 0.5 是不许的**：真数据恰好全 0.5 ⇒ 硬编在真数据上
       **与正确式逐位相同** ⇒ 那个变异在真数据上**恒绿**（变异台 P7 抓不到），
       只有 `pos_frac` **变化的合成夹具**才抓得到（自检 C6）。

    ⚖⚠ 三个细节都是判据的一部分，缺一个数就会错：
       ① `int()` 是**向零截断**，⛔ 不是四舍五入（自检 C6 专门钉这一条）；
       ② `max(1, …)` 的夹取在 `n_gen*pos_frac < 1` 时**生效**（自检 C6）；
       ③ `pos_frac` **缺字段必须拒读** —— 静默默认 0.5 是最坏的一种
          （真数据上无异、换一批数据就静默错）⇒ 变异台 P10 钉这一条。
    """
    P, ng, pf = rec.get("P"), rec.get("n_gen"), rec.get("pos_frac")
    if not P or not ng or pf is None:
        raise HardFail("记录 %r 缺 P/n_gen/pos_frac ⇒ 剂量**比例**算不出来 ⇒ **未量到**"
                       % (rec.get("tid"),))
    return int(P) + max(1, int(int(ng) * float(pf))) - 1


def pf_of(rec):
    """⚖ 一格的 `pos_frac`。⚖⚠⚠⚠ 缺它必须**拒读**，⛔ 不许默认 0.5 ——
    真数据恰好全 0.5 ⇒ 默认值在真数据上**看不出错**，换一批就静默错一倍。"""
    pf = rec.get("pos_frac")
    if pf is None:
        raise HardFail("记录 %r 缺 pos_frac ⇒ **未量到**" % (rec.get("tid"),))
    return float(pf)


def frac_of(rec):
    """⚖ 一格的注入**比例** = n_sites / 可注入位置总数。"""
    ns = rec.get("inject_n_sites")
    if ns is None:
        raise HardFail("记录 %r 没有 inject_n_sites ⇒ **未量到**" % (rec.get("tid"),))
    return float(ns) / float(denom_of(rec))


def majority_count(recs):
    """⚖ 账本口径：逐轨迹取 `d > 0` 的多数（平票算 False ⇒ 不算真）。"""
    g = {}
    for r in recs:
        g.setdefault(r.get("tid"), []).append(d_of(r) > 0)
    return sum(1 for v in g.values() if sum(v) * 2 > len(v)), len(g)


# --------------------------------------------------------------- 判据
def audit(arm, path):
    L = ["【臂】%s ｜ 文件 %s" % (arm, path)]
    recs = load_jsonl(path)
    meas = [r for r in recs if r.get("p9_lo_meas") is not None]
    L.append("  ⚖ 记录 %d 条 ｜ 有实测读数的 %d 条" % (len(recs), len(meas)))

    ok = True
    # C1 必须复现账本的逐轨迹多数计数
    k, n_traj = majority_count(recs)
    want = LEDGER_COUNT.get(arm)
    good = (want is not None and k == want and n_traj == N_TRAJ)
    L.append("  C1 逐轨迹「多数为真」= %d/%d（账本记 %s）⇒ %s"
             % (k, n_traj, want, "✅ 复现" if good else "⛔ 没复现 ⇒ 读的不是那一批"))
    ok &= good

    # C2 格的构成：必须是**混合剂量**，否则「混淆」这条判据恒红
    ks = [r for r in meas if r["inject_scope"] == "k" and r.get("inject_n_sites")]
    scopes = {}
    for r in meas:
        scopes[r["inject_scope"]] = scopes.get(r["inject_scope"], 0) + 1
    L.append("  C2 inject_scope 分布 %s ｜ scope=k 里位点数 %d..%d（%d 格）"
             % (scopes, min(r["inject_n_sites"] for r in ks),
                max(r["inject_n_sites"] for r in ks), len(ks)))
    mixed = (len(scopes) > 1 and len({r["inject_n_sites"] for r in ks}) > 1)
    L.append("     ⇒ %s" % ("✅ 剂量与 scope 都是混合的 ⇒ 跨格多数**不是**同条件多数"
                             if mixed else "⛔ 剂量是齐的 ⇒ 这批不能支持「混淆」这条结论"))
    ok &= mixed

    # ⚖⚠⚠⚖ 剂量轴必须是**比例**：分母跨轨迹差多少倍
    # ⚖⚠⚠⚖⚖⚠ 244.50：**分母公式已更正**为探针原式
    #   `P + max(1, int(n_gen*pos_frac)) − 1`（244.49 写的 `P + n_gen − 1` 大了一倍）
    dens = [denom_of(r) for r in ks]
    ratio = max(dens) / min(dens)
    L.append("  C2b 可注入位置总数 inj = P+floor(n_gen×pos_frac)−1 = %d … %d（**%.1f 倍**）"
             % (min(dens), max(dens), ratio))
    L.append("      ⇒ %s" % ("✅ 跨轨迹差很多 ⇒ **原始位点数不可比**，剂量轴必须用比例"
                              if ratio > 2 else "⚠ 分母差异 <2 倍 ⇒ 原始个数近似可比"))
    ok &= (ratio > 2)

    # ⚖⚠⚠⚖⚖ 244.50 新增：**pos_frac 的取值集合必须印出来**
    #   理由：分母错一整个常数因子（244.49 的 2×）时，**秩相关与分档表都不动**
    #   ⇒ 所有"看起来很稳"的量对分母**完全无感** ⇒ 只能靠把**取值集合本身**
    #   印出来 + 用**变化的 pos_frac** 合成夹具钉住公式。
    pfs = sorted({pf_of(r) for r in meas})
    pf_disp = ("%s" % pfs) if len(pfs) <= 6 else ("%s …(%d 个)" % (pfs[:6], len(pfs)))
    L.append("  C2c pos_frac 取值集合 = %s（全部 %d 条实测记录）"
             % (pf_disp, len(meas)))
    # ⚖ 分母公式成立的前提：`(pid+gen)[:P+t]` 不被 `len(pid)+n` 截断 ⇔ t ≤ n ⇔ pf ≤ 1
    over = [p for p in pfs if p > 1.0]
    nonpos = [p for p in pfs if p <= 0.0]
    L.append("      ⇒ %s" % ("✅ 全在 (0,1] ⇒ 不截断，inj 公式精确成立"
                             if not over and not nonpos else
                             "⛔ 有 pf>1（会被 len(pid)+n 截断，分母变 len(pid)+n−1，"
                             "**未量到**）或 pf<=0 ⇒ 补下 %s" % (over + nonpos)))
    ok &= (not over and not nonpos)

    # ⚖⚠⚠⚖ 244.50 新增：**扫描合法性对账**
    #   探针 `_k_positions(n,k)` 在 `k > n` 时**抛 ValueError**（⛔ 不是夹取），
    #   而 `n = h.shape[1]` = 整条 prefix = `ids.shape[1]` = inj+1
    #   ⇒ 越界的格子**根本不会留下记录** ⇒ 这条判据是**对账**，不是修 bug。
    badk = [(r.get("tid"), r["inject_n_sites"], denom_of(r)) for r in ks
            if float(r["inject_n_sites"]) > denom_of(r) + 1]
    L.append("  C2d 扫描合法性：n_sites ≤ ids.shape[1](=inj+1) ⇒ 越界 %d/%d 格"
             % (len(badk), len(ks)))
    if badk:
        L.append("      ⛔ %s ⇒ 探针本该抛错却留了记录 ⇒ **判据与探针不一致**"
                 % (badk[:3],))
    ok &= (not badk)

    # C3 剂量相关性：**两个轴都印**，差别必须看得见
    ns = [float(r["inject_n_sites"]) for r in ks]
    fr = [frac_of(r) for r in ks]
    dd = [d_of(r) for r in ks]
    rho_raw = spearman(ns, dd)
    rho = spearman(fr, dd)
    L.append("  C3 d 与剂量 的 Spearman：原始个数 %+.3f ｜ ✅**注入比例** %+.3f（%d 格）"
             % (rho_raw, rho, len(ks)))
    L.append("     ⚖ 结论用**比例**那一列；原始个数那列跨轨迹不可比（见 C2b）")
    L.append("     ⚖ 注入比例范围 %.4f … %.4f" % (min(fr), max(fr)))

    # C4 分档表（四档都必须印出来，且中位数单调与否要**报出来**）
    qs_ = _st.quantiles(fr, n=4)
    bands = [("frac<=q1", [r for r, f2 in zip(ks, fr) if f2 <= qs_[0]]),
             ("q1..q2", [r for r, f2 in zip(ks, fr) if qs_[0] < f2 <= qs_[1]]),
             ("q2..q3", [r for r, f2 in zip(ks, fr) if qs_[1] < f2 <= qs_[2]]),
             ("frac>q3", [r for r, f2 in zip(ks, fr) if f2 > qs_[2]])]
    L.append("  C4 按**注入比例**四分位分档（分位点 %.3f / %.3f / %.3f）"
             % tuple(qs_))
    meds = []
    for lab, sub in bands:
        if not sub:
            L.append("     %-11s 0 格" % lab)
            continue
        v = [d_of(r) for r in sub]
        meds.append(_st.median(v))
        L.append("     %-11s %3d 格  d 中位 %+.4f  为正 %2d/%d"
                 % (lab, len(v), meds[-1], sum(1 for x in v if x > 0), len(v)))
    mono = all(meds[i] <= meds[i + 1] for i in range(len(meds) - 1))
    L.append("     ⇒ 各档中位%s单调递增 ⇒ %s"
             % ("" if mono else "**不**", "✅ 剂量效应实测存在" if mono
                else "⚠ 不单调 ⇒ 该臂看不出剂量效应（≠「剂量不存在」）"))

    # C5 结论
    L.append("")
    if good and mixed and abs(rho) > 0.3:
        L.append("  ⚖⚠⚠⚖ **结论**：逐轨迹的「多数」是**跨不同注入位点数**的多数")
        L.append("     ⇒ 符号翻转与剂量效应**混淆** ⇒ ⛔ 在固定/分层剂量之前，")
        L.append("     「%d/%d 是不是噪声」**原理上不可分辨**" % (k, n_traj))
    else:
        L.append("  ⚠ 本臂**不支持**「剂量混淆」这条结论（复现=%s，混合=%s，rho=%+.3f）"
                 % (good, mixed, rho))
    L.append("")
    L.append("【⛔】本工具没验的（244.50 更新）：")
    L.append("  · `P == len(pid)` —— 探针 `P` 优先取 `extra.prompt_tokens`，"
             "取不到才回退 `len(pid)`，而记录里**只有 P** ⇒ 若两者不等，")
    L.append("    真分母是 `min(P+t, len(pid)+n) − 1`，本工具算的会**偏大**。")
    L.append("  · `p9_*_meas` 只来自 prefill 路径（已按 `:477-481` 核对），"
             "但 `scope=k` 在**增量解码**（`h.shape[1]==1`）下的行为本工具⛔ 没验。")
    L.append("  · single/all 与 k 三类的**跨类**可比性、逐文件一致性（只读了一个文件）。")
    return L, (0 if ok else 1)


# --------------------------------------------------------------- 自检
def selftest(files=None):
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # 合成数据：构造一个**必然**复现 12/14 且剂量单调的批
    # ⚖⚠⚠⚖⚖⚠ 244.50：**pos_frac 必须逐格变化**
    #   真数据 137 条的 pos_frac **全为 0.5** ⇒ 任何把它硬编成 0.5 的变异
    #   在真数据上**逐位相同 ⇒ 恒绿** ⇒ 只有"pos_frac 变化"的合成夹具
    #   才抓得到那个错（这是「夹具必须覆盖真数据退化维度」的一个实例）。
    PF_TRI = (0.25, 0.5, 0.75)
    # ⚖ ns 取成 denom 的**比例** ⇒ 恒 ≤ inj ⇒ C2d 合法性恒绿（合法夹具）
    #   而剂量跨度仍从 0.1% 到 90% ⇒ 「剂量混合」与秩相关判据都还有分辨力
    MS = (0.001, 0.01, 0.1, 0.4, 0.9)
    syn = []
    for tid in range(N_TRAJ):
        pos_majority = tid < 12
        ng = 200 + 50 * tid
        for j, m in enumerate(MS):
            pf = PF_TRI[(tid + j) % 3]
            den = 100 + max(1, int(ng * pf)) - 1
            ns = max(1, int(den * m))
            sgn = 1.0 if pos_majority else -1.0
            syn.append({"tid": "t%02d" % tid, "inject_scope": "k",
                        "inject_n_sites": ns, "pos_frac": pf,
                        "P": 100, "n_gen": ng,
                        "p9_lo_meas": 0.0, "p9_hi_meas": sgn * (0.1 + m)})
        # ⚖⚠⚠⚠ 必须同时有 scope=single / all ⇒ 否则 C2「剂量混合」判据**恒红**
        #   （合成夹具少一维 ⇒ 判据看起来红，其实是夹具不全）
        for sc in ("single", "all"):
            syn.append({"tid": "t%02d" % tid, "inject_scope": sc,
                        "inject_n_sites": None, "pos_frac": 0.5,
                        "P": 100, "n_gen": ng,
                        "p9_lo_meas": 0.0,
                        "p9_hi_meas": 0.5 if pos_majority else -0.5})
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    io.open(p, "w", encoding="utf-8").write(
        "\n".join(json.dumps(r) for r in syn) + "\n")

    # C0 Spearman：构造已知秩相关
    chk("C0", abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-12,
        "完全同序 ⇒ rho=%.6f" % spearman([1, 2, 3, 4], [10, 20, 30, 40]))
    chk("C0b", abs(spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-12,
        "完全逆序 ⇒ rho=%.6f" % spearman([1, 2, 3, 4], [40, 30, 20, 10]))
    # ⚖⚠⚠ 并列必须取**平均秩**（numpy 默认会给出不同名次 ⇒ 静默错一个值）
    # ⚖⚠⚠⚠ 这一条第一版写成 `spearman([1,1,2],[5,5,9]) == 1.0`
    #   ⇒ **两种名次都给 1.0** ⇒ 用例**区分不了** ⇒ 台架 P6 存活。
    #   ⚖⚠⚠⚠ 用例必须选「并列处理不同 ⇒ rho 不同」的那一组。
    _a, _b = [1, 1, 2, 3], [1, 2, 2, 3]
    chk("C0c", abs(spearman(_a, _b) - 0.8333333333333333) < 1e-12,
        "并列处理不同会改 rho ⇒ rho=%.6f（平均秩 0.833333 / 顺序名次 0.838870）"
        % spearman(_a, _b))

    # C1 多数口径：平票算 False
    rows = [{"tid": "a", "p9_lo_meas": 0.0, "p9_hi_meas": 1.0},
            {"tid": "a", "p9_lo_meas": 0.0, "p9_hi_meas": -1.0},
            {"tid": "b", "p9_lo_meas": 0.0, "p9_hi_meas": 1.0}]
    chk("C0d", True, "夹具 P/n_gen/**pos_frac** 已带（244.50 起 pos_frac 必填）")
    chk("C1", majority_count(rows) == (1, 2), "平票不算真 ⇒ %s" % (majority_count(rows),))

    # C2 缺读数必须拒读
    # ⚖⚠⚠⚠ 这里必须接 **Exception** 再断言类型，⛔ 不能只接 HardFail ——
    #   否则把守卫拆掉之后 `float(None)` 抛 TypeError ⇒ 直接逃出 selftest
    #   ⇒ 台架按「崩」记 ⇒ 而**崩 ⛔ 不等于按判据转红**（变异 P3 当场撞到）。
    try:
        d_of({"tid": "z", "p9_lo_meas": None, "p9_hi_meas": 1.0})
        chk("C2", False, "缺 p9_lo_meas 却**没有**拒读")
    except HardFail as e:
        chk("C2", "未量到" in str(e), "拒读理由是「未量到」：%s" % str(e)[:40])
    except Exception as e:
        chk("C2", False, "拒读时抛的是 %s 而不是 HardFail ⇒ 崩 ⛔ 不算按判据转红"
            % type(e).__name__)

    # C3 坏 JSON 必须拒读，不许静默跳过
    badp = p + ".bad"
    io.open(badp, "w", encoding="utf-8").write('{"tid":"a","p9_lo_meas":0,'
                                               '"p9_hi_meas":1}\n{oops\n')
    try:
        load_jsonl(badp)
        chk("C3", False, "有坏行却**没有**拒读")
    except HardFail as e:
        chk("C3", "解析失败" in str(e), "拒读理由正确：%s" % str(e)[:40])
    except Exception as e:
        chk("C3", False, "拒读时抛的是 %s 而不是 HardFail" % type(e).__name__)

    # C4 合成批上跑一遍：多数必须复现 12/14
    L, rc = audit("w", p)
    chk("C4", rc == 0, "合成批审计 rc=%d" % rc)
    chk("C5", any("= 12/14（账本记 12）⇒ ✅ 复现" in x for x in L),
        "C1 行必须印出复现成功")

    # ⚖⚠⚠⚖⚖⚠ C6：**分母公式逐条钉死**（244.50 的正主）
    #   244.49 栽的正是「分母按公式推、不照探针原式抄」⇒ 这里把原式的
    #   ① `int()` 向零截断 ② `max(1,…)` 夹取 ③ `pos_frac` 实取，
    #   全部做成**手算的字面量期望**。
    #   ⚖⚠ 期望值⛔ 不许由被测函数自己算出来 —— 那就是自反比较（恒绿）。
    cases = [(100, 200, 0.25, 149),     # t = int(200*0.25) = 50
             (100, 200, 0.75, 249),     # t = 150
             (100, 1, 0.25, 100),       # int(0.25)=0 ⇒ max(1,0)=1 ⇒ 夹取生效
             (100, 203, 0.5, 200)]      # int(101.5)=101；round(101.5)=102 ⇒ 钉截断
    got = [denom_of({"tid": "x", "P": P, "n_gen": ng, "pos_frac": pf})
           for (P, ng, pf, _w) in cases]
    want = [w for (_P, _ng, _pf, w) in cases]
    chk("C6", got == want, "inj 逐条＝%s（期望 %s）" % (got, want))

    # C7 缺 pos_frac 必须**拒读** —— ⛔ 静默默认 0.5 是最坏的一种错：
    #   真数据恰好全 0.5 ⇒ 默认值**看不出错**，换一批数据就静默错一倍
    try:
        denom_of({"tid": "x", "P": 100, "n_gen": 200})
        chk("C7", False, "缺 pos_frac 却**没有**拒读")
    except HardFail as e:
        chk("C7", "未量到" in str(e), "拒读理由是「未量到」：%s" % str(e)[:40])
    except Exception as e:
        chk("C7", False, "拒读时抛的是 %s 而不是 HardFail ⇒ 崩 ⛔ 不算按判据转红"
            % type(e).__name__)

    # ⚖⚠⚠⚖ C8：**两条新判据必须能红**（C2c 截断 / C2d 越界）
    #   ⚖⚠ 断言的是**那两行的文字**，⛔ 不是 rc —— 最小批本来就过不了
    #     C1（轨迹数不足 14），用 rc 断言会让其它判据的红冒充覆盖。
    def _mini(pf_bad=False, ns_bad=False):
        rs = []
        for i in range(3):
            r = {"tid": "m%d" % (i % 2), "inject_scope": "k",
                 "inject_n_sites": 10 * (i + 1), "pos_frac": 0.5,
                 "P": 100, "n_gen": 400,
                 "p9_lo_meas": 0.0, "p9_hi_meas": 0.1 * (i + 1)}
            if i == 0 and pf_bad:
                r["pos_frac"] = 2.0          # ⇒ 会被 len(pid)+n 截断 ⇒ 分母变
            if i == 2 and ns_bad:
                r["inject_n_sites"] = 999999  # ⇒ 超过 inj+1，探针本该抛错
            rs.append(r)
        for i in range(2):
            rs.append({"tid": "m%d" % i, "inject_scope": "single",
                       "inject_n_sites": None, "pos_frac": 0.5,
                       "P": 100, "n_gen": 400,
                       "p9_lo_meas": 0.0, "p9_hi_meas": 0.2})
        return rs

    def _dump(rs):
        fd, q = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
        io.open(q, "w", encoding="utf-8").write(
            "\n".join(json.dumps(r) for r in rs) + "\n")
        return q

    extras = [_dump(_mini()), _dump(_mini(pf_bad=True)), _dump(_mini(ns_bad=True))]
    Lc, _ = audit("w", extras[0])
    Lp, _ = audit("w", extras[1])
    Ln, _ = audit("w", extras[2])
    chk("C8a", any("✅ 全在 (0,1]" in x for x in Lc) and any("越界 0/" in x for x in Lc),
        "干净夹具 ⇒ C2c/C2d 都绿")
    chk("C8b", any("⛔ 有 pf>1" in x for x in Lp), "pos_frac=2.0 ⇒ C2c 转红")
    chk("C8c", any("越界 1/" in x for x in Ln), "n_sites 超 inj+1 ⇒ C2d 转红")

    for f in (p, badp) + tuple(extras):
        try:
            os.unlink(f)
        except OSError:
            pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="符号判决的剂量混淆审计（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--arm", choices=sorted(DEFAULT_FILES), default=None)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    arms = [args.arm] if args.arm else sorted(DEFAULT_FILES)
    rc = 0
    for arm in arms:
        path = DEFAULT_FILES[arm]
        if not os.path.exists(path):
            print("【臂】%s ｜ ⛔ 文件不存在：%s" % (arm, path))
            rc = 1
            continue
        L, r = audit(arm, path)
        print("\n".join(L)); print()
        rc |= r
    return rc


if __name__ == "__main__":
    sys.exit(main())
