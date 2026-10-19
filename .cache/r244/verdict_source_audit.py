#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verdict_source_audit.py —— 判决数的**来源链**与**分子**（修订 244.55，零 GPU）

🔴🔴 **本工具问什么**

  账本里最硬的那几个数（w 12/14、rand 6/14、w 13/1、rand 5/9、Fisher 0.0044241）
  一直被**当作已知**引用。244.52 又查出「结果文件里的 `arm` 标签是坏的」，
  于是那条「12/14 与 6/14 能被 `_wn.txt` / `_rn2.txt` 复现」的**复现链本身**
  需要被钉死。⇒ 本工具只做这一件事：**把每个判决数的来源链与分子摊开**。

⚖⚠⚠⚠ **本工具发现的第一个东西（不是本工具发明的，是账本里两处并排放着的）**

  账本里有**两个不同的轨迹级统计量**，它们**不是同一个数**：

    · **预登记主统计量**（244.14.5 / 244.15 闸 7）：
      逐轨迹 `up_mono_meas` **多数为真**，判据 `nT > nF` ⇒ **平局算 False**
      ⇒ w **12/14** = 0.8571、rand **6/14** = 0.4286、差 +42.9pp、Fisher 0.0460717
    · **轨迹级符号检验**（244.9.2，`arm_verdict.py`）：
      逐轨迹 Δ = `p9_lo_meas`(all 档) − `p9_lo_meas`(k_hi 档) 的**符号**
      ⇒ w **13/1** p=0.00183105、rand **5/9** p=0.42395、Fisher 0.0044241

  ⚠⚠⚠ **w 臂的 12 与 13 差的那一条，被本工具定位到唯一一条轨迹**：
    `aime__aime25__p00__think` —— 它的 `up_mono_meas` 是 **5/5（平局）**
    ⇒ 预登记口径（平局算 False）判它**假**；轨迹级口径判它**真**（Δ=+0.181673）
    ⇒ ⛔ 两个数**不是抄错**，是**两条不同的规则**。

⚖⚠⚠⚠ **第二个发现（真·误印，在 244.43 的表里）**

  `.cache/r244/headroom_audit.py` 的判决清单里有一行：

      ("轨迹级 rand", 5, 9, "轨迹级")      ← ⛔ **9 是「5 正 / 9 负」里的负数**

  ⇒ 它被当成**样本量**用 ⇒ `sign_binom(5, 9)` = **1.0** ⇒ 244.43 的表印出
  「轨迹级 rand 5/9 p=**1.00000**」。⚖ 而权威值（244.9.2）是
  **5 正 / 9 负、样本量 14、p=0.42395** ⇒ 正确写法是 `("轨迹级 rand", 5, 14, …)`。

  ⚖ **对结论的影响：零**（余量仍「已越界」、显著判决仍 4 个、余量仍 2/1/1/1、
  「一格 = 4.4–8.0 倍 p」区间不变）⇒ 但**表里那个 p 是错的**，必须撤回并更正。

  ⚖⚠⚠⚠ **第三件事：为什么这道错没被抓住** ——
  `headroom_audit.py` 的自检 C8 拿 `want8`（**同样手抄的**那一份）与报告比
  ⇒ **判据的两端来自同一个可变来源** ⇒ 那道守卫**原理上抓不到抄错**。
  ⛔ 本工具的 C8/C10 就是来补这个洞的：**独立重算** vs **那份手抄表**。

⚖⚠⚠⚠ **本工具不复用 reader 的 `analyze()`**（它需要本地**没有**的状态文件）
  ⇒ 改为**从读数重算**，并用**账本 244.9.2 的权威值**当等价性守卫：
  算不出那四个数 ⇒ 本工具的推导就与 reader 不等价 ⇒ **判红**。
  ⚖ 复用 `r227_kcurve.sign_test`（符号检验）与 `arm_verdict.fisher_exact_two_sided`
  （Fisher）—— ⛔ **不手抄第二份**（「两个解析器就是两套真相」）。

⚖⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不写数据文件、⛔ 不删任何文件。
⚖⚠⚖⚖ 每条判据都必须**能红**：自检用畸形夹具证明「红得了」，
  变异台（`mut_verdict_source_audit.py`）在**源码层**证明「红得了」。

跑法：
    python3 verdict_source_audit.py
    python3 verdict_source_audit.py --selftest
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import ast
import collections
import hashlib
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, "..", "mutbak", "r227_kcurve.py")
ARM_VERDICT = os.path.join(HERE, "arm_verdict.py")
HEADROOM = os.path.join(HERE, "headroom_audit.py")

# ⚖ 本轮判决实际引用的两批文件（标签正确的）与两批**标签坏了**的
USED = {"w": "_an.txt", "rand": "_ra.txt"}
USED_BAD = {"w": "_wn.txt", "rand": "_rn2.txt"}

# ⚖⚠⚠ 账本 244.9.2 的**权威值**（**引用**，⛔ 不是本工具算出来的）：
#   轨迹级 w 13/1 p=0.00183105 ｜ rand 5/9 p=0.42395 ｜ Fisher 0.0044241
#   问题级 w 7/0 p=0.015625 ｜ rand 2/5 p=0.453125 ｜ Fisher 0.020979
# ⚖ 预登记主统计量（244.14.5 / 244.15 闸 7 / 244.23）：
#   w 12/14 p=0.01294 ｜ rand 6/14 p=0.79053 ｜ 差 +42.9pp ｜ Fisher 0.0460717
AUTH = {
    "w": {
        "prereg": (12, 14), "prereg_p": 0.01294,
        "traj": (13, 14), "traj_p": 0.00183105,
        "prob": (7, 7), "prob_p": 0.015625,
        # ⚖⚠⚠ **净差 +1 ⛔ 不等于「只差一条」**：逐轨迹不同向的**实际 3 条**
        #   （p00__think 平局、p03__think 5/6、p18__no_think）
        "n_differ": 3, "net_diff": 1,
    },
    "rand": {
        "prereg": (6, 14), "prereg_p": 0.79053,
        "traj": (5, 14), "traj_p": 0.42395,
        "prob": (2, 7), "prob_p": 0.453125,
    },
}
AUTH_FISHER = {"traj": 0.0044241, "prob": 0.020979}

# ⚖⚠⚠ 244.43 表里「轨迹级 rand」那一行的**误印**（**撤回并更正**，⛔ 不是改数凑好看）
#   表里写 (5, 9) ⇒ 把「5 正 / 9 负」里的**负数**当成了**样本量**
#   权威（244.9.2）：5 正 / 9 负 ⇒ 样本量 **14** ⇒ p = 0.42395
CORRECTIONS = {"轨迹级 rand": (5, 14)}

# ⚖⚠⚠ **账本里仍「未量到」的三项**（⛔ 不许写成「无差异」）
BLANKS = (
    ("远端 tokenizer 快照的内容指纹",
     "两次跑批之间远端那个 snapshot 目录的**文件内容**有没有变过 —— 同一路径 ≠ 同一内容"),
    ("`pos_frac` 只在 0.5 取过值",
     "别的取值下「位置/剂量轴」的含义**没有**任何实测支撑"),
    ("哪一条臂是机制效应",
     "w 臂的 12/14 与 rand 臂的 6/14 **都**是跨剂量的多数（244.48/244.50）⇒ 机制未分离"),
)
# ⚖⚠⚠ **必须印出来的三项**（与上面那份内容**分开** ⇒ 判据的两端不同源）
#   ⚖ 理由：若「要求」与「内容」是同一份列表 ⇒ 删掉一条就**一起消失** ⇒ 恒绿。
BLANKS_REQUIRED = ("远端 tokenizer 快照的内容指纹",
                   "`pos_frac` 只在 0.5 取过值",
                   "哪一条臂是机制效应")

_MODS = {}


def _load(path, name):
    if not os.path.isfile(path):
        raise SystemExit("PRECOND_FAIL: 找不到 %s" % path)
    if name in _MODS:
        return _MODS[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def reader():
    return _load(READER, "r227_kcurve")


def arm_verdict():
    return _load(ARM_VERDICT, "arm_verdict")


def headroom():
    return _load(HEADROOM, "headroom_audit")


# ---------------------------------------------------------------- 读数层


def load_rows(path):
    """⚖ 只收以 `{` 开头的行（`_an.txt` 是**原始驱动日志**，`_ra.txt` 是**纯 JSONL**）"""
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("{"):
                rows.append(json.loads(s))
    return rows


def group_tids(rows):
    per = collections.OrderedDict()
    for r in rows:
        per.setdefault(r["tid"], []).append(r)
    return per


def problem_key(tid):
    """⚖ 与 reader 的 `analyze()` **同口径**：剥掉 `__think` / `__no_think`"""
    import re
    return re.sub(r"__(?:no_)?think$", "", tid) or tid


def n_eff_of(cs):
    """⚖ 样本量取该轨迹**第一个**有 P/t 的格的 `P + t`
    ⚖（reader 的回退口径；244.53/244.54 已证 BEGIN 的 n_eff == P + t）"""
    for c in cs:
        if c.get("P") is not None and c.get("t") is not None:
            return int(c["P"]) + int(c["t"])
    return None


def delta_per_tid(rows):
    """⚖⚠ 逐轨迹 Δ = `p9_lo_meas`(all 档) − `p9_lo_meas`(k_hi 档)
    ⚖   k_hi = **最大的、满足 `2*k <= n_eff` 的 k 档**（与 reader 同一套整数口径）
    ⚖   ⚠ `k_hi` ⛔ **绝不**取 `ladder[-1]`（244.229 的静默坑）"""
    out = {}
    for tid, cs in group_tids(rows).items():
        alls = [c for c in cs if c.get("inject_scope") == "all"]
        lad = [c for c in cs if c.get("inject_scope") == "k"]
        if not alls or not lad:
            out[tid] = None
            continue
        n_eff = n_eff_of(cs)
        below = [c for c in lad
                 if n_eff is not None and 2 * int(c["inject_n_sites"]) <= n_eff]
        if not below:
            out[tid] = None
            continue
        below.sort(key=lambda c: int(c["inject_n_sites"]))
        out[tid] = alls[-1]["p9_lo_meas"] - below[-1]["p9_lo_meas"]
    return out


def prereg_per_tid(rows):
    """⚖ 预登记主统计量（244.14.5 / 244.15 闸 7）：逐轨迹 `up_mono_meas` 多数为真
    ⚖   判据 `nT > nF` ⇒ **平局算 False**（⚠ 约定不是规格，须同报）"""
    out = {}
    for tid, cs in group_tids(rows).items():
        nT = sum(1 for c in cs if c.get("up_mono_meas") is True)
        nF = sum(1 for c in cs if c.get("up_mono_meas") is False)
        miss = sum(1 for c in cs if c.get("up_mono_meas") is None)
        out[tid] = {"n_true": nT, "n_false": nF, "missing": miss,
                    "verdict": nT > nF, "tie": nT == nF}
    return out


def p9delta_per_tid(rows):
    """⚖ 244.48 的口径：逐轨迹 `d = p9_hi_meas − p9_lo_meas > 0` 的多数"""
    out = {}
    for tid, cs in group_tids(rows).items():
        p = n = z = 0
        for c in cs:
            d = c["p9_hi_meas"] - c["p9_lo_meas"]
            if d > 0:
                p += 1
            elif d < 0:
                n += 1
            else:
                z += 1
        out[tid] = {"pos": p, "neg": n, "zero": z,
                    "verdict": p > n, "tie": p == n}
    return out


def problem_deltas(deltas):
    """⚖ 问题级：按问题分组，取组内**逐轨迹 Δ 的中位数**（reader 同口径）"""
    buckets = collections.OrderedDict()
    for tid, d in deltas.items():
        if d is None:
            continue
        buckets.setdefault(problem_key(tid), []).append(d)
    return collections.OrderedDict(
        (p, reader()._median(v)) for p, v in buckets.items())


def sign_of(d):
    if d is None:
        return 0
    return 1 if d > 0 else (-1 if d < 0 else 0)


def counts_from_signs(signs):
    pos = sum(1 for s in signs if s > 0)
    neg = sum(1 for s in signs if s < 0)
    return pos, neg, pos + neg


def fingerprint(rows):
    """⚖ 内容指纹：把 `arm` 字段**排除**后逐条 sha1（244.52 的口径）"""
    hs = []
    for r in rows:
        d = {k: v for k, v in r.items() if k != "arm"}
        hs.append(hashlib.sha1(
            json.dumps(d, sort_keys=True, ensure_ascii=False)
            .encode("utf-8")).hexdigest())
    return hs


# ---------------------------------------------------------------- 判决层


def derive_arm(rows, arm):
    """⚖ 从一批读数里导出该臂的三个判决 + 逐轨迹明细"""
    dl = delta_per_tid(rows)
    pg = prereg_per_tid(rows)
    pd_ = p9delta_per_tid(rows)
    tids = list(group_tids(rows).keys())
    traj_signs = [sign_of(dl.get(t)) for t in tids]
    prob_d = problem_deltas(dl)
    prob_signs = [sign_of(v) for v in prob_d.values()]
    prereg_signs = [1 if pg[t]["verdict"] else -1 for t in tids]
    st = reader().sign_test
    return {
        "arm": arm,
        "tids": tids,
        "n_cells": len(rows),
        "prereg_signs": prereg_signs,
        "prereg": (sum(1 for s in prereg_signs if s > 0), len(prereg_signs)),
        "prereg_p": st([1.0 if s > 0 else -1.0 for s in prereg_signs])[0],
        "traj_signs": traj_signs,
        "traj": (sum(1 for s in traj_signs if s > 0), len(traj_signs)),
        "traj_p": st([float(s) for s in traj_signs])[0],
        "prob_signs": prob_signs,
        "prob": (sum(1 for s in prob_signs if s > 0), len(prob_signs)),
        "prob_p": st([float(s) for s in prob_signs])[0],
        "delta": dl,
        "prereg_per_tid": pg,
        "p9delta_per_tid": pd_,
        "n_eff_first": n_eff_of(rows),
    }


def fisher(w_pos, w_neg, r_pos, r_neg):
    p, _ = arm_verdict().fisher_exact_two_sided(w_pos, w_neg, r_pos, r_neg)
    return p


# ---------------------------------------------------------------- 判据


def _close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def check_data(dw, dr, files, used, bad, expect):
    """⚖ 数据级判据（C1–C7、C11）。返回 (results, lines)"""
    L = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        L.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    # ---- C1 预登记主统计量的来源链 --------------------------------
    ok1 = True
    d1 = []
    for arm, d in (("w", dw), ("rand", dr)):
        exp = expect[arm]["prereg"]
        got = d["prereg"]
        ok1 = ok1 and (got == exp)
        d1.append("%s %d/%d（期望 %d/%d）" % (arm, got[0], got[1], exp[0], exp[1]))
    put("C1", ok1,
        "预登记主统计量（`up_mono_meas` 多数，平局算 False）：%s" % "；".join(d1))

    # ---- C2 轨迹级符号检验的来源链 --------------------------------
    ok2 = True
    d2 = []
    for arm, d in (("w", dw), ("rand", dr)):
        exp = expect[arm]["traj"]
        got = d["traj"]
        ok2 = ok2 and (got == exp)
        d2.append("%s %d/%d（期望 %d/%d）" % (arm, got[0], got[1], exp[0], exp[1]))
    # ⚖⚠⚠ 逐轨迹**符号向量**（期望给了就逐条比 —— 夹具靠它抓「取错 k_hi」）
    for arm, d in (("w", dw), ("rand", dr)):
        expv = expect[arm].get("traj_signs")
        if expv is not None:
            ok2 = ok2 and (d["traj_signs"] == expv)
    put("C2", ok2,
        "轨迹级符号检验（`p9_lo_meas`(all − k_hi)）：%s；逐轨迹符号向量%s"
        % ("；".join(d2), "已逐条核对" if expect["w"].get("traj_signs") else "未给期望"))

    # ---- C3 问题级 -------------------------------------------------
    ok3 = True
    d3 = []
    for arm, d in (("w", dw), ("rand", dr)):
        exp = expect[arm]["prob"]
        got = d["prob"]
        ok3 = ok3 and (got == exp)
        d3.append("%s %d/%d（期望 %d/%d）" % (arm, got[0], got[1], exp[0], exp[1]))
    put("C3", ok3, "问题级（剥 `__think`/`__no_think` 分组，取 Δ 中位数）：%s"
        % "；".join(d3))

    # ---- C4 跨臂 Fisher -------------------------------------------
    fw = fisher(dw["traj"][0], dw["traj"][1] - dw["traj"][0],
                dr["traj"][0], dr["traj"][1] - dr["traj"][0])
    fp = fisher(dw["prob"][0], dw["prob"][1] - dw["prob"][0],
                dr["prob"][0], dr["prob"][1] - dr["prob"][0])
    ok4 = _close(fw, expect["fisher_traj"], 1e-6) and _close(fp, expect["fisher_prob"], 1e-6)
    put("C4", ok4,
        "跨臂 Fisher 双尾：轨迹级 %.7g（期望 %.7g）、问题级 %.7g（期望 %.7g）"
        % (fw, expect["fisher_traj"], fp, expect["fisher_prob"]))

    # ---- C5 分子定位：12 与 13 的**逐轨迹**关系 ---------------------
    # ⚠⚠⚠ **净差 +1 ⛔ 不等于「只差一条」** —— 本工具第一版就是这么写的，
    #   ⚠⚠⚠ **被它自己的判据当场推翻**：逐轨迹不同向的**实际有 3 条**
    #   （2 条「轨迹级真 / 预登记假」+ 1 条「预登记真 / 轨迹级假」）。
    #   ⇒ 两个数**不是同一条规则的两个版本**，⛔ **不可互相替代**。
    pw = dw["prereg_per_tid"]
    diff_tids = [t for t in dw["tids"]
                 if pw[t]["verdict"] != (dw["traj_signs"][dw["tids"].index(t)] > 0)]
    tie_tids = [t for t in dw["tids"] if pw[t]["tie"]]
    net = dw["traj"][0] - dw["prereg"][0]
    exp = expect["w"]
    ok5 = (len(diff_tids) == exp.get("n_differ", len(diff_tids))
           and net == exp.get("net_diff", net)
           and len(tie_tids) == 1 and tie_tids[0] in diff_tids)
    put("C5", ok5,
        "w 臂「预登记 %d」与「轨迹级 %d」：**净差 %+d**，但**逐轨迹不同向的有 %d 条**"
        "（%s）；平局轨迹 %d 条（%s）⇒ **净差 +1 ⛔ 不等于「只差一条」**"
        % (dw["prereg"][0], dw["traj"][0], net, len(diff_tids),
           "、".join(diff_tids) or "无", len(tie_tids),
           "、".join(tie_tids) or "无"))

    # ---- C6 预登记口径 vs 244.48 口径的逐格关系 --------------------
    n_same = n_diff = 0
    diff_notzero = []
    for arm, d in (("w", dw), ("rand", dr)):
        rows = files[used[arm]]
        pg = d["prereg_per_tid"]
        for c in rows:
            a = c.get("up_mono_meas") is True
            b = (c["p9_hi_meas"] - c["p9_lo_meas"]) > 0
            if a == b:
                n_same += 1
            else:
                n_diff += 1
                if not (c["p9_hi_meas"] == c["p9_lo_meas"]):
                    diff_notzero.append((arm, c["tid"], c["inject_scope"],
                                         c["inject_n_sites"]))
    ok6 = (len(diff_notzero) == 0)
    put("C6", ok6,
        "逐格 `up_mono_meas` 与 `(p9_hi > p9_lo)`：相同 %d 格、不同 %d 格；"
        "不同的格里**非零跨度**的有 %d 条 ⇒ 例外格必须**全是零跨度格**"
        % (n_same, n_diff, len(diff_notzero)))

    # ---- C7 坏标签文件的复现链（244.52 登记的待办）------------------
    ok7 = True
    d7 = []
    for arm in ("w", "rand"):
        good = files[used[arm]]
        b = files.get(bad.get(arm))
        if b is None:
            ok7 = False
            d7.append("%s 臂：坏标签文件**不在本地** ⇒ 未量到" % arm)
            continue
        same_fp = (fingerprint(good) == fingerprint(b))
        labs = sorted(set(str(r.get("arm", "<缺失>")) for r in b))
        lab_bad = (labs != [arm])
        d_good = derive_arm(good, arm)
        d_bad = derive_arm(b, arm)
        same_nums = (d_good["prereg"] == d_bad["prereg"]
                     and d_good["traj"] == d_bad["traj"])
        ok7 = ok7 and same_fp and lab_bad and same_nums
        d7.append("%s 臂：坏标签文件 arm=%s、内容指纹%s、判决数%s"
                  % (arm, "/".join(labs), "逐条相同" if same_fp else "不同",
                     "相同" if same_nums else "不同"))
    put("C7", ok7,
        "坏标签文件（`_wn.txt`/`_rn2.txt`）与权威对**给出同一个判决数**、"
        "且标签确实是坏的 ⇒ 复现链**不依赖 arm 标签**；%s" % "；".join(d7))

    # ---- C11 留白 --------------------------------------------------
    L_blank = ["  · %s —— **未量到**（%s）" % (t, why) for t, why in BLANKS]
    L.extend(L_blank)
    missing_blanks = [t for t in BLANKS_REQUIRED
                      if not any(("· %s ——" % t) in x for x in L)]
    put("C11", not missing_blanks,
        "三条未量到项必须逐条印出（⛔ 不许写成「无差异」）；缺 %s"
        % ("无" if not missing_blanks else "、".join(missing_blanks)))

    return R, L


def extract_verdicts(path):
    """⚖ 用 **AST** 从 `headroom_audit.py` 里结构化取出 `VERDICTS`
    ⚖ （⛔ 不正则、⛔ 不手抄第二份）"""
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "VERDICTS":
                    out = []
                    for el in node.value.elts:
                        name = el.elts[0].value
                        k = el.elts[1].value
                        n = el.elts[2].value
                        tier = el.elts[3].value
                        out.append((name, k, n, tier))
                    return out
    raise SystemExit("PRECOND_FAIL: %s 里没有 VERDICTS" % path)


def extract_want8(path):
    """⚖ 取出 `headroom_audit.py` 自检 C8 的 `want8` 期望清单"""
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "want8":
                    out = []
                    for el in node.value.elts:
                        out.append((el.elts[0].value, el.elts[1].value,
                                    el.elts[2].value))
                    return out
    return None


def check_table(headroom_path, dw, dr):
    """⚖ 表级判据（C8–C10）。返回 (results, lines)"""
    L = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        L.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    vs = extract_verdicts(headroom_path)
    derived = {
        "轨迹级 w": (dw["traj"][0], dw["traj"][1]),
        "轨迹级 rand": (dr["traj"][0], dr["traj"][1]),
        "问题级 w": (dw["prob"][0], dw["prob"][1]),
        "问题级 rand": (dr["prob"][0], dr["prob"][1]),
        "预登记主统计量 w": (dw["prereg"][0], dw["prereg"][1]),
        "预登记主统计量 rand": (dr["prereg"][0], dr["prereg"][1]),
    }
    mism = []
    for name, k, n, _tier in vs:
        if name in derived:
            gk, gn = derived[name]
            if (k, n) != (gk, gn):
                mism.append((name, (k, n), (gk, gn)))
    L.append("  ℹ 判决清单十行对账（**6 行可从读数重算**；另 4 行是层内 rho 正号，"
             "**本工具⛔ 不重算**）")
    for name, k, n, tier in vs:
        if name in derived:
            gk, gn = derived[name]
            mark = "✅" if (k, n) == (gk, gn) else "⛔⛔⛔ 不一致"
            L.append("      %-22s 表里 %d/%d ｜ 重算 %d/%d  %s"
                     % (name, k, n, gk, gn, mark))
        else:
            # ⚖⚠⚠ 修订 244.56：**别在这里印「未量到」** ——
            #   ⚖ 那 4 行在 244.56 里**已经被独立重算过**（`layer_row_audit.py`）
            #   ⇒ 印「未量到」会变成**过期的断言**。
            #   ⚖⚠ 而「本工具⛔ 不重算」是**关于本工具作用域**的真话 ⇒ 印它。
            L.append("      %-22s 表里 %d/%d ｜ **本工具⛔ 不重算**（层内 rho 正号，"
                     "来源 244.32）" % (name, k, n))
    put("C8", not mism,
        "判决清单里**可重算的 6 行**必须与重算值逐位相等；不一致 %d 行%s"
        % (len(mism),
           ("：" + "；".join("%s 表里 %d/%d vs 重算 %d/%d"
                             % (n, a[0], a[1], b[0], b[1]) for n, a, b in mism))
           if mism else ""))

    # ---- C9 更正不碰判决 -------------------------------------------
    hr = headroom()
    fixed = []
    for name, k, n, tier in vs:
        if name in CORRECTIONS:
            k, n = CORRECTIONS[name]
        fixed.append((name, k, n, tier))
    sig = []
    margins = []
    for name, k, n, tier in fixed:
        p = hr.sb(k, n)
        m, _ka, _pa = hr.cells_to_alpha(k, n)
        if p < hr.ALPHA:
            sig.append((name, m))
        margins.append((name, m, p))
    want_sig = [("轨迹级 w", 2), ("问题级 w", 1),
                ("预登记主统计量 w", 1), ("传播层 rand（244.37）", 1)]
    row = [m for m in margins if m[0] == "轨迹级 rand"]
    p_fixed = row[0][2] if row else None
    ok9 = (len(sig) == 4 and sig == want_sig
           and row and row[0][1] == 0
           and _close(p_fixed, 0.42395, 1e-5))
    put("C9", ok9,
        "更正「轨迹级 rand」那一行为 5/14 后：p=%.5f（权威 0.42395）、余量仍「已越界」、"
        "显著判决仍 %d 个且余量仍 %s ⇒ **判决一个数都没动**"
        % (p_fixed if p_fixed is not None else float("nan"),
           len(sig), "/".join(str(m) for _n, m in sig)))

    # ---- C10 headroom 自检 C8 的同源性（恒绿登记）-------------------
    want8 = extract_want8(headroom_path)
    if want8 is None:
        put("C10", False, "headroom_audit.py 里**找不到** `want8` ⇒ 无法判定同源性")
    else:
        vmap = dict((n, (k, n2)) for n, k, n2, _t in vs)
        same = 0
        diff = []
        for name, k, n in want8:
            if vmap.get(name) == (k, n):
                same += 1
            else:
                diff.append(name)
        ok10 = (len(want8) == len(vs) == 10)
        if diff:
            put("C10", ok10,
                "`want8` 与 `VERDICTS` 有 **%d 行不同源**（%s）⇒ 那道守卫现在**抓得到**"
                "那几行；总行数 %d/%d" % (len(diff), "、".join(diff), len(want8), len(vs)))
        else:
            put("C10", ok10,
                "headroom 自检 C8 的 `want8`（%d 行）与 `VERDICTS`（%d 行）**逐行同源**"
                " ⇒ 那道守卫**原理上抓不到抄错**（恒绿）⇒ 真正的守卫是本工具的 C8"
                % (len(want8), len(vs)))
    return R, L


# ---------------------------------------------------------------- 主流程


def build_report(files, used, bad, expect, headroom_path=HEADROOM):
    dw = derive_arm(files[used["w"]], "w")
    dr = derive_arm(files[used["rand"]], "rand")
    L = []
    L.append("【1】判决数的**来源链**（每条：哪批文件 / 哪个字段 / 哪条规则 / 什么平局口径）")
    L.append("  ⚖ 批次：w = `%s`（arm='w'）｜ rand = `%s`（arm='rand'）"
             % (used["w"], used["rand"]))
    L.append("")
    L.append("  A · **预登记主统计量**（244.14.5 / 244.15 闸 7）")
    L.append("      字段 `up_mono_meas`；规则 = 逐轨迹**多数为真**；判据 `nT > nF`")
    L.append("      ⇒ **平局算 False**（⚠ 约定不是规格，须同报）")
    for arm, d in (("w", dw), ("rand", dr)):
        ties = [t for t in d["tids"] if d["prereg_per_tid"][t]["tie"]]
        L.append("      %-4s ⇒ **%d/%d** = %.4f，p=%.5f；平局轨迹 %d 条%s"
                 % (arm, d["prereg"][0], d["prereg"][1],
                    d["prereg"][0] / float(d["prereg"][1]), d["prereg_p"],
                    len(ties), ("（" + "、".join(ties) + "）") if ties else ""))
    L.append("")
    L.append("  B · **轨迹级符号检验**（244.9.2，`arm_verdict.py`）")
    L.append("      字段 `p9_lo_meas`；规则 = 逐轨迹 Δ = all 档 − k_hi 档")
    L.append("      k_hi = 最大的、满足 `2*k <= n_eff` 的 k 档（⛔ 绝不取 `ladder[-1]`）")
    for arm, d in (("w", dw), ("rand", dr)):
        L.append("      %-4s ⇒ 正 %d / 负 %d（n=%d），p=%.8f"
                 % (arm, d["traj"][0], d["traj"][1] - d["traj"][0],
                    d["traj"][1], d["traj_p"]))
    L.append("")
    L.append("  C · **问题级符号检验**")
    L.append("      分组 = 剥掉 `__think`/`__no_think`；量 = 组内逐轨迹 Δ 的**中位数**")
    for arm, d in (("w", dw), ("rand", dr)):
        L.append("      %-4s ⇒ 正 %d / 负 %d（n=%d），p=%.8f"
                 % (arm, d["prob"][0], d["prob"][1] - d["prob"][0],
                    d["prob"][1], d["prob_p"]))
    L.append("")
    L.append("  D · **跨臂 Fisher**（精确双尾）")
    L.append("      轨迹级 p=%.7g ｜ 问题级 p=%.7g"
             % (fisher(dw["traj"][0], dw["traj"][1] - dw["traj"][0],
                       dr["traj"][0], dr["traj"][1] - dr["traj"][0]),
                fisher(dw["prob"][0], dw["prob"][1] - dw["prob"][0],
                       dr["prob"][0], dr["prob"][1] - dr["prob"][0])))
    L.append("")
    L.append("【2】**分子**逐条定位（w 臂：预登记 %d 与轨迹级 %d 的关系）"
             % (dw["prereg"][0], dw["traj"][0]))
    L.append("  %-38s %-10s %-10s %-12s %-10s %s" %
             ("tid", "up_mono T/F", "预登记", "Δ（轨迹级）", "轨迹级", "两条口径"))
    diff_tids = []
    for i, t in enumerate(dw["tids"]):
        pg = dw["prereg_per_tid"][t]
        dlt = dw["delta"].get(t)
        pv = pg["verdict"]
        tv = dw["traj_signs"][i] > 0
        same = (pv == tv)
        if not same:
            diff_tids.append(t)
        L.append("  %-38s %-10s %-10s %-12s %-10s %s"
                 % (t, "%d/%d%s" % (pg["n_true"], pg["n_false"],
                                    "(平)" if pg["tie"] else ""),
                    "真" if pv else "假",
                    ("%+.6f" % dlt) if dlt is not None else "未量到",
                    "真" if tv else "假",
                    "一致" if same else "⛔ 不同向"))
    L.append("")
    L.append("  ⚖⚠⚠⚠ **净差 %+d**（%d − %d），但**逐轨迹不同向的有 %d 条**：%s"
             % (dw["traj"][0] - dw["prereg"][0], dw["traj"][0],
                dw["prereg"][0], len(diff_tids), "、".join(diff_tids) or "无"))
    L.append("  ⚖⚠⚠⚠ ⇒ ⛔ **净差 +1 不等于「只差一条」** ⇒ 预登记 12/14 与轨迹级 13/1"
             " **不是同一条规则的两个版本**，⛔ **不可互相替代**，⛔ 引用时必须**同报口径**。")
    L.append("")
    L.append("【3】**留白**（⛔ 没量到的写成「未量到」，⛔ 不许写成「无差异」）")
    for t, why in BLANKS:
        L.append("  · %s —— **未量到**（%s）" % (t, why))
    L.append("")
    L.append("【4】判决清单**对账** + **恒绿登记**")
    R1, L1 = check_table(headroom_path, dw, dr)
    L.extend(L1)
    L.append("")
    L.append("【5】判据")
    R2, L2 = check_data(dw, dr, files, used, bad, expect)
    L.extend(L2)
    R = collections.OrderedDict()
    R.update(R2)
    R.update(R1)
    return L, R


def run(rdir=HERE, used=None, bad=None, expect=None, headroom_path=HEADROOM):
    used = used or USED
    bad = bad or USED_BAD
    expect = expect or {"w": AUTH["w"], "rand": AUTH["rand"],
                         "fisher_traj": AUTH_FISHER["traj"],
                         "fisher_prob": AUTH_FISHER["prob"]}
    files = {}
    for name in list(used.values()) + list(bad.values()):
        p = os.path.join(rdir, name)
        if os.path.isfile(p):
            files[name] = load_rows(p)
    missing = [n for n in list(used.values()) if n not in files]
    if missing:
        raise SystemExit("PRECOND_FAIL: 读不到 %s" % missing)
    L, R = build_report(files, used, bad, expect, headroom_path)
    bad_cids = [c for c, v in R.items() if not v]
    return L, (0 if not bad_cids else 1), R


# ---------------------------------------------------------------- 自检夹具

# ⚖ 合成夹具的**逐轨迹目标**（与权威数一致，但**数值是合成的**）
#   (tid, n_true, n_false, n_zero, Δ)
FX_W = [
    ("p00__think", 5, 5, 0, 0.30),
    ("p00__no_think", 7, 2, 0, 0.30),
    ("p03__think", 5, 6, 0, 0.20),
    ("p03__no_think", 7, 3, 0, 0.20),
    ("p02__think", 9, 1, 0, 0.40),
    ("p02__no_think", 6, 3, 0, 0.20),
    ("p05__think", 6, 4, 0, 0.20),
    ("p05__no_think", 5, 4, 0, 0.30),
    ("p07__think", 8, 2, 0, 0.10),
    ("p07__no_think", 10, 0, 0, 0.20),
    ("p18__think", 8, 2, 0, -0.10),
    ("p18__no_think", 9, 1, 0, 0.50),
    ("p24__think", 7, 3, 0, 0.30),
    ("p24__no_think", 9, 0, 0, 0.20),
]
FX_RAND = [
    ("p00__think", 6, 4, 0, -0.30),
    ("p00__no_think", 4, 5, 0, -0.30),
    ("p03__think", 3, 8, 0, -0.40),
    ("p03__no_think", 2, 8, 0, -0.20),
    ("p02__think", 8, 2, 0, 0.20),
    ("p02__no_think", 6, 3, 0, 0.20),
    ("p05__think", 7, 3, 0, 0.30),
    ("p05__no_think", 1, 8, 0, 0.10),
    ("p07__think", 4, 6, 0, -0.30),
    ("p07__no_think", 6, 4, 0, -0.20),
    ("p18__think", 1, 9, 0, -0.40),
    ("p18__no_think", 8, 2, 0, -0.30),
    ("p24__think", 4, 6, 2, -0.50),
    ("p24__no_think", 1, 8, 0, 0.10),
]

# ⚖ k 阶梯：最后一个恒 > n_eff/2 ⇒ `2*k <= n_eff` 这个过滤器**恒承重**
FX_KS = [1, 2, 4, 8, 16, 32, 64, 100, 150, 160, 170, 180, 190, 200]


def fx_rows(spec, arm):
    """⚖ 合成一批读数。⚖⚠ **形状必须与生产一样脏**：
      · 有 `all` / `single` / `k` 三种 scope（`up_mono_meas` 逐格都算票）
      · 阶梯里**有** `2*k > n_eff` 的档（过滤器承重）
      · **非 k_hi 档的 `p9_lo_meas` 一律取大值** ⇒ 取错 k_hi 就会**翻符号**
      · 有**零跨度格**（`p9_hi == p9_lo`）⇒ 两条口径在格级真的不一样
    """
    rows = []
    for i, (tid, n_true, n_false, n_zero, delta) in enumerate(spec):
        total = n_true + n_false
        n_eff = 200 + 7 * i
        P = n_eff - 50
        t = 50
        n_ladder = total - 2
        ks = FX_KS[:max(0, n_ladder - 1)] + [260]
        cells = [("all", None), ("single", None)]
        for k in ks:
            cells.append(("k", k))
        # ⚖ 谁是真票：前 n_true 格为真；其中**最后 n_zero 格是零跨度**
        for j, (scope, k) in enumerate(cells):
            is_true = j < n_true
            is_zero = is_true and (j >= n_true - n_zero)
            if scope == "all":
                lo = delta
            elif scope == "single":
                lo = 0.25
            else:
                lo = 0.0 if 2 * k <= n_eff else (5.0 + 0.01 * j)
            if is_zero:
                hi = lo
            elif is_true:
                hi = lo + 0.01
            else:
                hi = lo - 0.01
            r = {"tid": tid, "arm": arm, "inject_scope": scope,
                 "inject_n_sites": k if k is not None else 0,
                 "P": P, "t": t, "pos_frac": 0.5, "n_steps": 60, "gap": 100.0,
                 "n_gen": 2 * t, "p9_lo_meas": lo, "p9_hi_meas": hi,
                 "up_mono_meas": is_true}
            rows.append(r)
    return rows


def fx_expect():
    """⚖ 夹具的期望值 = **从夹具规格推出来**的（⛔ 不是抄生产数据）"""
    ex = {}
    for arm, spec in (("w", FX_W), ("rand", FX_RAND)):
        prereg = sum(1 for _t, nt, nf, _z, _d in spec if nt > nf)
        prereg_tie = sum(1 for _t, nt, nf, _z, _d in spec if nt == nf)
        traj_pos = sum(1 for _t, _nt, _nf, _z, d in spec if d > 0)
        # 问题级：同 problem 的两条 Δ 取中位数（n=2 ⇒ 均值）
        byprob = collections.OrderedDict()
        for t, _nt, _nf, _z, d in spec:
            byprob.setdefault(problem_key(t), []).append(d)
        prob_pos = sum(1 for v in byprob.values() if reader()._median(v) > 0)
        ex[arm] = {
            "prereg": (prereg, len(spec)),
            "traj": (traj_pos, len(spec)),
            "prob": (prob_pos, len(byprob)),
            "traj_signs": [1 if d > 0 else -1 for _t, _a, _b, _c, d in spec],
        }
        # ⚖ 逐轨迹不同向的条数与净差（⛔ 从**规格**推出来，不是抄生产数据）
        n_diff = 0
        for (t, nt, nf, _z, d) in spec:
            prereg_true = nt > nf
            traj_true = d > 0
            if prereg_true != traj_true:
                n_diff += 1
        ex[arm]["n_differ"] = n_diff
        ex[arm]["net_diff"] = traj_pos - prereg
        ex[arm]["_tie"] = prereg_tie
    return ex


def _write_fixture(d, name, rows, arm_label=None):
    p = os.path.join(d, name)
    with io.open(p, "w", encoding="utf-8") as f:
        for r in rows:
            if arm_label is not None:
                r = dict(r)
                r["arm"] = arm_label
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return p


def fx_dir(d, bad_content_differs=False):
    """⚖ 造四个文件：`_an.txt`/`_ra.txt`（标签对）与 `_wn.txt`/`_rn2.txt`（标签坏）"""
    w = fx_rows(FX_W, "w")
    r = fx_rows(FX_RAND, "rand")
    _write_fixture(d, "_an.txt", w)
    _write_fixture(d, "_ra.txt", r)
    if bad_content_differs:
        # ⚖ 坏标签文件的内容**真的不同** ⇒ 「选错文件」查得出来
        w2 = fx_rows(FX_W, "w")
        w2[0]["p9_lo_meas"] += 3.0
        _write_fixture(d, "_wn.txt", w2, arm_label="X")
        r2 = fx_rows(FX_RAND, "rand")
        r2[0]["p9_lo_meas"] += 3.0
        _write_fixture(d, "_rn2.txt", r2, arm_label="X")
    else:
        _write_fixture(d, "_wn.txt", w, arm_label="X")
        _write_fixture(d, "_rn2.txt", r, arm_label="X")
    return d


def selftest():
    import tempfile
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    d = tempfile.mkdtemp()
    fx_dir(d)
    ex = fx_expect()
    ex["fisher_traj"] = AUTH_FISHER["traj"]
    ex["fisher_prob"] = AUTH_FISHER["prob"]
    # ⚖ 夹具的 Fisher p 与生产的**不同** ⇒ 期望必须按夹具重算
    dw = derive_arm(fx_rows(FX_W, "w"), "w")
    dr = derive_arm(fx_rows(FX_RAND, "rand"), "rand")
    ex["fisher_traj"] = fisher(dw["traj"][0], dw["traj"][1] - dw["traj"][0],
                               dr["traj"][0], dr["traj"][1] - dr["traj"][0])
    ex["fisher_prob"] = fisher(dw["prob"][0], dw["prob"][1] - dw["prob"][0],
                               dr["prob"][0], dr["prob"][1] - dr["prob"][0])
    L, rc, R = run(rdir=d, expect=ex)
    chk("C0", rc == 0, "干净夹具 rc=%d（红的有 %s）"
        % (rc, ",".join(k for k, v in R.items() if not v) or "无"))

    # ---- C1：平局口径被改成「平局算 True」⇒ 预登记分子变大 ⇒ 必须红 ----
    d1 = tempfile.mkdtemp()
    fx_dir(d1)
    ex1 = dict(ex)
    ex1["w"] = dict(ex["w"])
    ex1["w"]["prereg"] = (ex["w"]["prereg"][0] + 1, ex["w"]["prereg"][1])
    L1, rc1, R1 = run(rdir=d1, expect=ex1)
    chk("C1x", not R1.get("C1"),
        "把预登记的期望分子 +1（模拟「平局算 True」）⇒ C1 必须红（rc=%d）" % rc1)

    # ---- C2：期望的轨迹级符号向量被改 ⇒ 必须红 --------------------
    d2 = tempfile.mkdtemp()
    fx_dir(d2)
    ex2 = dict(ex)
    ex2["w"] = dict(ex["w"])
    ex2["w"]["traj_signs"] = list(ex["w"]["traj_signs"])
    ex2["w"]["traj_signs"][0] = -ex2["w"]["traj_signs"][0]
    L2, rc2, R2 = run(rdir=d2, expect=ex2)
    chk("C2x", not R2.get("C2"),
        "轨迹级逐轨迹符号向量被改一位 ⇒ C2 必须红（rc=%d）" % rc2)

    # ---- C3：问题级期望被改 ⇒ 必须红 ------------------------------
    d3 = tempfile.mkdtemp()
    fx_dir(d3)
    ex3 = dict(ex)
    ex3["w"] = dict(ex["w"])
    ex3["w"]["prob"] = (ex["w"]["prob"][0] + 1, ex["w"]["prob"][1])
    L3, rc3, R3 = run(rdir=d3, expect=ex3)
    chk("C3x", not R3.get("C3"),
        "问题级期望被改 ⇒ C3 必须红（rc=%d）" % rc3)

    # ---- C4：跨臂 Fisher 期望被改 ⇒ 必须红 ------------------------
    d4 = tempfile.mkdtemp()
    fx_dir(d4)
    ex4 = dict(ex)
    ex4["fisher_traj"] = ex["fisher_traj"] + 0.01
    L4, rc4, R4 = run(rdir=d4, expect=ex4)
    chk("C4x", not R4.get("C4"),
        "Fisher 期望被改 ⇒ C4 必须红（rc=%d）" % rc4)

    # ---- C5：把 p05__no_think 的 up_mono 票从 5/4 改成 4/5 ⇒
    #   预登记分子 12→11 ⇒ **净差 +1 变成 +2**、不同向条数 3→4
    #   ⇒ C5 必须红（⚠ Δ 没动 ⇒ C2 仍绿 ⇒ 这条夹具**只**动口径不动剂量）
    d5 = tempfile.mkdtemp()
    fx_dir(d5)
    w5 = fx_rows(FX_W, "w")
    # ⚖ 把 p05__no_think 的一格从「真」翻成「假」（5/4 → 4/5）
    #   ⇒ 预登记分子 12→11 ⇒ **净差 +1 变成 +2**、不同向条数 3→4
    #   ⚖ 同时把 p9_hi 一起翻 ⇒ 两条口径在**格级**仍一致 ⇒ C6 仍绿
    #   ⚖ 只动 up_mono、**不动 p9_lo_meas** ⇒ Δ 不变 ⇒ C2 仍绿
    for r in w5:
        if (r["tid"] == "p05__no_think" and r["up_mono_meas"] is True
                and r["p9_hi_meas"] != r["p9_lo_meas"]):
            r["up_mono_meas"] = False
            r["p9_hi_meas"] = r["p9_lo_meas"] - 0.01
            break
    _write_fixture(d5, "_an.txt", w5)
    _write_fixture(d5, "_wn.txt", w5, arm_label="X")
    L5, rc5, R5 = run(rdir=d5, expect=ex)
    chk("C5x", not R5.get("C5"),
        "预登记分子被改（净差 +1→+2）⇒ C5 必须红（rc=%d）" % rc5)

    # ---- C6：例外格出现在**非零跨度**格上 ⇒ C6 必须红 --------------
    d6 = tempfile.mkdtemp()
    fx_dir(d6)
    r6 = fx_rows(FX_RAND, "rand")
    # ⚖ 把一个「假」格（up_mono=False、p9_hi < p9_lo）改成 **p9_hi > p9_lo**
    #   ⇒ 格级出现「up_mono 与 p9delta 不一致」，而那格**不是零跨度** ⇒ C6 必须红
    for r in r6:
        if (r["tid"] == "p24__think" and r["up_mono_meas"] is False
                and r["p9_hi_meas"] < r["p9_lo_meas"]):
            r["p9_hi_meas"] = r["p9_lo_meas"] + 0.02
            break
    _write_fixture(d6, "_ra.txt", r6)
    _write_fixture(d6, "_rn2.txt", r6, arm_label="X")
    L6, rc6, R6 = run(rdir=d6, expect=ex)
    chk("C6x", not R6.get("C6"),
        "例外格落在非零跨度格上 ⇒ C6 必须红（rc=%d）" % rc6)

    # ---- C7：坏标签文件内容**真的不同** ⇒ C7 必须红 ----------------
    d7 = tempfile.mkdtemp()
    fx_dir(d7, bad_content_differs=True)
    L7, rc7, R7 = run(rdir=d7, expect=ex)
    chk("C7x", not R7.get("C7"),
        "坏标签文件内容不同 ⇒ C7 必须红（rc=%d）" % rc7)

    # ---- C8/C9/C10：表级判据用**变异过的 headroom_audit 副本** -----
    d8 = tempfile.mkdtemp()
    fx_dir(d8)
    hr_src = io.open(HEADROOM, encoding="utf-8").read()
    # ⚖ 副本 1：把「轨迹级 rand」那行改成 (5, 9) ⇒ C8 必须红
    hr_bad = hr_src.replace('("轨迹级 rand", 5, 14, "轨迹级"),',
                             '("轨迹级 rand", 5, 9, "轨迹级"),')
    p8 = os.path.join(d8, "headroom_bad.py")
    io.open(p8, "w", encoding="utf-8").write(hr_bad)
    L8, rc8, R8 = run(rdir=d8, expect=ex, headroom_path=p8)
    chk("C8x", not R8.get("C8"),
        "判决清单的「轨迹级 rand」被改回 (5,9) ⇒ C8 必须红（rc=%d）" % rc8)
    # ⚖ 副本 2：把 want8 改掉 ⇒ C10 的「同源」判定必须变
    hr_bad2 = hr_src.replace('("轨迹级 rand", 5, 14),',
                              '("轨迹级 rand", 5, 9),')
    p8b = os.path.join(d8, "headroom_bad2.py")
    io.open(p8b, "w", encoding="utf-8").write(hr_bad2)
    L8b, rc8b, R8b = run(rdir=d8, expect=ex, headroom_path=p8b)
    chk("C10x", not R8b.get("C10") or any("不同源" in x for x in L8b),
        "`want8` 与 `VERDICTS` 不同源 ⇒ C10 的判词必须变（rc=%d）" % rc8b)

    for dd in (d, d1, d2, d3, d4, d5, d6, d7, d8):
        try:
            for fn in os.listdir(dd):
                os.unlink(os.path.join(dd, fn))
            os.rmdir(dd)
        except OSError:
            pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="判决数的来源链与分子（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        L, rc, R = run()
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print("\n".join(L))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
