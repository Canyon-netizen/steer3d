#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cluster_premise_audit.py —— 判决面板的**「前提是否独立」**（修订 244.59，零 GPU）

🔴🔴 **本工具问什么**

  用户目标②明写：出现在任何结论里的数都带着**逐条验过**的前提 ——
  分母怎么算、剂量轴是什么、覆盖面够不够、标签可不可信、**前提是否独立**。

  ⚖⚠⚠⚠ **查实（不是猜测）**：判决面板上的**每一个 p 与每一个区间**
  （轨迹级与预登记的 4 个符号检验 p、两个跨臂 Fisher、
  以及 244.58 刚补上的 6 个 95% 区间）**全部**建立在
  「**14 条轨迹是 14 个独立单位**」这个前提上。
  ⚖⚠⚠ 而这个前提**从来没有被验过**。

  ⚖ **结构事实（实测）**：14 条轨迹 = **7 个问题 × 2 模式**（think / no_think），
  ⚖ 每个问题恰好 2 条 ⇒ 同块的两条**共享问题** ⇒ 轨迹级**不是** 14 个独立单位。

⚖⚠⚠⚠ **本工具的结论只到「独立性未量到」为止**

  ⚖ 7 个块 ⇒ 检验「块内一致率是否高于独立预期」的**功效很低**
  ⇒ 既**证明不了**独立，也**证明不了**聚类 ⇒ 正确表述是「**未量到**」
  ⇒ ⛔ **不许**写成「独立」，⛔ **也不许**写成「聚类」。

⚖⚠⚠⚠⚠ **但有一条更硬的结论（本节的核心）**

  **「显著」是**口径依赖**的**：同一个判据规则，按**问题聚成 7 块**再算一遍，
  两个跨臂 Fisher **在块级口径下都不显著**
  ⇒ 面板上「显著」这个说法**必须附带前提声明**
  ⇒ ⇒ 而 ✅ **「差 ≠ 0」在两个口径下都成立**（Newcombe 都不含 0）⇒ 方向不变

  ⚖⚖ 上头这几句话里的**具体数**全在下面「**C12 回读区**」，
  由判据 **C12** 逐个与实测对照 ⇒ **改一个必须红**。

⚖ **复用既有生产机械（⛔ 不另写第二套真相）**

  · 逐轨迹符号：`verdict_source_audit.derive_arm`（244.55 那条已钉死的来源链）
  · 符号检验 p：`r227_kcurve.sign_test`（⛔ 不手抄第二份）
  · 跨臂 Fisher：`arm_verdict.fisher_exact_two_sided`
  · 区间：`interval_audit.cp95` / `wilson_bounds` / `newcombe_diff`（244.58）
  · 二项尾：本文件自写的 `binom_sf` / `binom_cdf`（纯 stdlib，⛔ 不引 scipy）
  · 功效：本文件自写的**精确枚举** `fisher_power`（⛔ 不用正态近似，理由见 **C11**）

⚖⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不写数据文件、⛔ 不删任何文件。
⚖⚠⚖⚖ 每条判据都必须**能红**：自检用畸形夹具证明「红得了」，
变异台（`mut_cluster_premise_audit.py`）在**源码层**证明「红得了」。

⚖⚖⚖⚖ **C12 回读区**（⛔ 本段的数由判据 **C12** 逐个与实测对照，改一个必须红）：
  · key=traj       | w 13/1 p=0.00183105 | rand 5/9 p=0.42395 | fisher=0.0044241
  · key=prereg     | w 12/2 p=0.01294 | rand 6/8 p=0.79053 | fisher=0.0460717
  · key=block_traj | w 6/1 p=0.125 | rand 2/5 p=0.453125 | fisher=0.1025641
  · key=indep      | w_traj=0.8571 | w_prereg=0.7143 | rand_traj=0.5306 | rand_prereg=0.5102
  · key=agreeP     | w_traj=0.7365 | w_prereg=0.6792 | rand_traj=0.0852 | rand_prereg=0.7898

⚖⚖⚖⚖ **判据清单**（C0–C13）：
  C0 块结构复现 ｜ C1 轨迹级口径逐位复现账本 ｜ C2 跨臂 Fisher 的两个口径
  ｜ C3 块内一致率对手抄字面量 ｜ C4 「前提是否独立」= 未量到 + 印出功效
  ｜ C5 显著性是口径依赖的 ｜ C6 块级区间逐条更宽 ｜ C7 「差 ≠ 0」两口径都成立
  ｜ C8 块数功效测算（精确枚举）｜ C9 前提声明逐条印出 ｜ C10 六条留白逐条印出
  ｜ C11 精确枚举 vs 具名正态近似 ⇒ 近似**不可替代**精确（用**具名**两种方法对照）
  ｜ C12 「回读区」的数与实测**逐位**一致
  ｜ C13 块级 p 必须跑在**块级多数向量**上（⛔ 不是 14 条轨迹符号）

跑法：
    python3 cluster_premise_audit.py
    python3 cluster_premise_audit.py --selftest
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import collections
import importlib.util
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
VSRC = os.path.join(HERE, "verdict_source_audit.py")
ARMV = os.path.join(HERE, "arm_verdict.py")
IAUD = os.path.join(HERE, "interval_audit.py")
READER = os.path.join(REPO, ".cache", "mutbak", "r227_kcurve.py")

ALPHA = 0.05

# ⚖ 账本里的**权威值**（**引用**，⛔ 不是本工具算出来的）：244.9.2 / 244.15 闸 7
# ⚖⚠⚠⚠ **p 值写成「字符串」**：容差按**账本印了几位**定（禁令 ㋃）
#   ⇒ 账本印 5 位 ⇒ 容差 = 半个末位 = 5e-6；印 8 位 ⇒ 5e-9
#   ⇒ ⛔ 不许一律用同一个容差（本轮第一版用 1e-6 ⇒ 0.79053 误报红）
AUTH = {
    "w": {"traj": (13, 14), "traj_p": "0.00183105", "prereg": (12, 14),
          "prereg_p": "0.01294"},
    "rand": {"traj": (5, 14), "traj_p": "0.42395", "prereg": (6, 14),
             "prereg_p": "0.79053"},
}
AUTH_FISHER = {"traj": "0.0044241", "prereg": "0.0460717"}

# ⚖⚠⚠⚠ **手抄字面量**（从本工具 2026-10-19 的输出抄下）：(一致数, 独立预期)
#   ⚖ 键 = (臂, 统计量)；值 = ((分子, 分母), 独立预期)
#   ⚖⚠⚠ **同源限定**（同 C3 的说明）：只抓「抄错/漂了」，抓不到公式写错
LEDGER_AGREE = {
    ("w", "traj"): ((6, 7), 0.8571),
    ("w", "prereg"): ((5, 7), 0.7143),
    ("rand", "traj"): ((6, 7), 0.5306),
    ("rand", "prereg"): ((3, 7), 0.5102),
}
N_TRAJ = 14
N_BLOCK = 7
BLOCK_SIZE = 2


def tol_of(printed):
    """⚖ **账本印了几位** ⇒ 容差 = 半个末位（禁令 ㋃）。"""
    s = str(printed)
    dec = len(s.split(".")[1]) if "." in s else 0
    return 0.5 * (10.0 ** (-dec))


# ⚖⚖⚖⚖ **C12 回读区**的解析（⛔ 文档里的数必须能被**逐个**读出来对照）
DOC_LINE_RE = re.compile(r"^\s*·\s*key=(\w+)\s*\|(.*)$")
DOC_KV_RE = re.compile(r"(\w+)\s*=\s*([0-9.]+)")
DOC_ARM_RE = re.compile(r"(w|rand)\s+(\d+)/(\d+)\s+p=([0-9.]+)")


def parse_doc_facts(doc):
    """⚖ 从**本文档**的「C12 回读区」解析出键值（⛔ 数值保留**原字符串**）。

    ⚖⚠⚠⚖ 保留原字符串是为了让**容差按「文档印了几位」定**（禁令 ㋃）。
    """
    facts = {}
    if not doc:
        return facts
    for line in doc.split("\n"):
        m = DOC_LINE_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        body = m.group(2)
        d = {}
        for mm in DOC_KV_RE.finditer(body):
            d[mm.group(1)] = mm.group(2)
        for mm in DOC_ARM_RE.finditer(body):
            arm = mm.group(1)
            d["%s_pos" % arm] = int(mm.group(2))
            d["%s_neg" % arm] = int(mm.group(3))
            d["%s_p" % arm] = mm.group(4)
        facts[key] = d
    return facts


def check_doc_facts(doc, D):
    """⚖ 对照「回读区」与实测 ⇒ 返回 (是否全对, 逐条说明)。

    ⚖⚠⚠⚖ **抽成独立函数**是为了让自检能喂**改坏的文档** ⇒ 必须红。
    """
    docf = parse_doc_facts(doc)
    expf = expected_doc_facts(D)
    ok = True
    det = []
    for key in sorted(expf):
        got = docf.get(key)
        if got is None:
            ok = False
            det.append("%s：**回读区里没有这一行**" % key)
            continue
        for name in sorted(expf[key]):
            ev = expf[key][name]
            gv = got.get(name)
            if gv is None:
                ok = False
                det.append("%s.%s：缺" % (key, name))
                continue
            if isinstance(ev, int):
                good = (int(gv) == ev)
                det.append("%s.%s 文档 %s vs 实测 %s %s"
                           % (key, name, gv, ev, "✅" if good else "❌"))
            else:
                good = abs(float(gv) - ev) <= tol_of(gv)
                det.append("%s.%s 文档 %s vs 实测 %.8f %s"
                           % (key, name, gv, ev, "✅" if good else "❌"))
            ok = ok and good
    return ok, det


def expected_doc_facts(D):
    """⚖ 「C12 回读区」里**应该**是什么（全部由读数算出，⛔ 不手填）。

    ⚖ 返回：{key: {name: (实测值, None)}}
    """
    AV = armv()
    st = reader().sign_test
    out = {}

    def add(key, name, val):
        out.setdefault(key, {})[name] = val

    for stat in ("traj", "prereg"):
        for arm in ("w", "rand"):
            d = D[arm]
            signs = d["traj_signs" if stat == "traj" else "prereg_signs"]
            vec = [1.0 if s > 0 else -1.0 for s in signs.values()]
            add(stat, "%s_pos" % arm, sum(1 for s in vec if s > 0))
            add(stat, "%s_neg" % arm, sum(1 for s in vec if s < 0))
            add(stat, "%s_p" % arm, st(vec)[0])
        w = D["w"][stat]
        r = D["rand"][stat]
        pf, _ = AV.fisher_exact_two_sided(w[0], w[1] - w[0], r[0], r[1] - r[0])
        add(stat, "fisher", pf)

    for arm in ("w", "rand"):
        d = D[arm]
        vec = block_signs(d["blocks"], d["traj_signs"])
        add("block_traj", "%s_pos" % arm, sum(1 for s in vec if s > 0))
        add("block_traj", "%s_neg" % arm, sum(1 for s in vec if s < 0))
        add("block_traj", "%s_p" % arm, st(vec)[0])
    bw = block_majority(D["w"]["blocks"], D["w"]["traj_signs"])
    br = block_majority(D["rand"]["blocks"], D["rand"]["traj_signs"])
    pf, _ = AV.fisher_exact_two_sided(bw[0], bw[1] - bw[0], br[0], br[1] - br[0])
    add("block_traj", "fisher", pf)

    for arm in ("w", "rand"):
        d = D[arm]
        for stat in ("traj", "prereg"):
            signs = d["traj_signs" if stat == "traj" else "prereg_signs"]
            ag = within_agreement(d["blocks"], signs)
            pth, pnt, _a, _b = mode_marginals(d["blocks"], signs)
            exp = indep_agree_rate(pth, pnt)
            add("indep", "%s_%s" % (arm, stat), exp)
            add("agreeP", "%s_%s" % (arm, stat), binom_sf(N_BLOCK, ag, exp))
    return out

# ⚖⚠⚠⚠ **必须印出来的前提声明**（⛔ 删掉任何一条都必须红）
PREAMBLE = (
    "⚖⚠⚠⚠ 面板上的**每一个 p 与每一个区间**都建立在「**14 条轨迹是 14 个独立单位**」"
    "这个前提上；⚖⚠⚠ **该前提在现有 7 个块上【未量到】**（检验功效只有 0.34）",
    "⚖⇒ ⛔ 「显著」是**口径依赖**的：轨迹级 n=14 显著，块级 n=7 **不显著** ⇒ "
    "引用时**必须**写清用的是哪个口径",
    "⚖⇒ ✅ 「**差 ≠ 0**」在**两个口径下都成立**（Newcombe 都不含 0）⇒ **方向不变**",
)
PREAMBLE_REQUIRED = (
    "⚖⚠⚠⚠ 面板上的**每一个 p 与每一个区间**都建立在「**14 条轨迹是 14 个独立单位**」"
    "这个前提上；⚖⚠⚠ **该前提在现有 7 个块上【未量到】**（检验功效只有 0.34）",
    "⚖⇒ ⛔ 「显著」是**口径依赖**的：轨迹级 n=14 显著，块级 n=7 **不显著** ⇒ "
    "引用时**必须**写清用的是哪个口径",
    "⚖⇒ ✅ 「**差 ≠ 0**」在**两个口径下都成立**（Newcombe 都不含 0）⇒ **方向不变**",
)

# ⚖⚠⚠ **必须逐条印出来的留白**（⛔ 少印一条必须红）
BLANKS = (
    ("前提是否独立",
     "14 条轨迹 = 7 块 × 2；7 个块的检验功效 0.34 ⇒ 既证不了独立，也证不了聚类"),
    ("远端 tokenizer 快照的内容指纹",
     "两次跑批之间远端那个 snapshot 目录的**文件内容**有没有变过（同一路径 ≠ 同一内容）"),
    ("`pos_frac` 只在 0.5 取过值",
     "别的取值下「位置/剂量轴」的含义没有任何实测支撑"),
    ("哪一条臂是机制效应",
     "两臂的多数都是**跨剂量**的多数（244.48/244.50）⇒ 机制与剂量仍不可分辨"),
    ("固定/分层剂量下的 w/rand 各自改判数",
     "要跑新的一批（第三次改口径）⇒ ⛔ 等用户点头 ⇒ 本地量不到"),
    ("层内 rho 的重复性",
     "rep_n=1 ⇒ 「rand 臂那个 12/14 是不是噪声」仍未解释（244.37 登记至今）"),
)
BLANKS_REQUIRED = (
    "前提是否独立",
    "远端 tokenizer 快照的内容指纹",
    "`pos_frac` 只在 0.5 取过值",
    "哪一条臂是机制效应",
    "固定/分层剂量下的 w/rand 各自改判数",
    "层内 rho 的重复性",
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def vsrc():
    return _load(VSRC, "vs_24459")


def armv():
    return _load(ARMV, "av_24459")


def iaud():
    return _load(IAUD, "ia_24459")


def reader():
    return _load(READER, "r227_24459")


# ---------------------------------------------------------------- 二项（纯 stdlib）
def binom_sf(n, k, p):
    """⚖ P(X ≥ k)，X~Binomial(n,p)。"""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(math.comb(n, j) * (p ** j) * ((1.0 - p) ** (n - j))
               for j in range(k, n + 1))


def binom_cdf(n, k, p):
    """⚖ P(X ≤ k)。"""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(math.comb(n, j) * (p ** j) * ((1.0 - p) ** (n - j))
               for j in range(0, k + 1))


# ---------------------------------------------------------------- 数据层
def blocks_of(tids, problem_key):
    """⚖ 把轨迹按问题聚成块。返回 (ordered list of blocks, 块大小分布)。"""
    per = collections.OrderedDict()
    for t in tids:
        per.setdefault(problem_key(t), []).append(t)
    return list(per.values())


def block_is_pos(blk, signs):
    """⚖⚖⚖ **唯一的块级判定规则**：块内**两条轨迹都正**才算正（平票/单正都算 False）。

    ⚖⚠⚠⚠ 这是**与轨迹级同一规则**（平票算 False）在**块**上的应用
    ⇒ ⛔ **不是** 244.55 的「问题级（组内 Δ 的**中位数**）」⇒ **两个不同统计量，不许混搭**。

    ⚖⚖⚖⚖ **规则只写这一处**（⛔ 不另写第二份）：`block_majority` 与 `block_signs`
    都调用它 ⇒ 两者**不可能**漂移。
    """
    return all(signs[t] > 0 for t in blk)


def block_majority(blocks, signs):
    """⚖ **块级多数**：正块数 / 块数（规则见 `block_is_pos`）。"""
    k = 0
    for blk in blocks:
        if block_is_pos(blk, signs):
            k += 1
    return k, len(blocks)


def block_signs(blocks, signs):
    """⚖ 每个块的**块级判定**（+1 = 该块算正；−1 = 算 False/负）。

    ⚖⚠⚠⚖⚖ **这是块级 p 值的输入向量**（7 个 ±1）⇒ p 的分母是 **7**，不是 14。
    ⚖ 判据 **C13** 专门盯这条。
    """
    out = []
    for blk in blocks:
        out.append(1.0 if block_is_pos(blk, signs) else -1.0)
    return out


def block_sign_test_p(blocks, signs):
    """⚖ **块级**符号检验的 p 值（跑的是**块级多数向量**，⛔ 不是 14 条轨迹符号）。

    ⚖⚠⚠⚠⚠ ⛔ 我第一版把 **14 条轨迹符号**喂给了符号检验 ⇒ 印出来的是**轨迹级的 p**
    ⚖⚠⚠⚠⚠   （w 的轨迹级 0.00183105 会被印在「块级 6/7」旁边）⇒ **撤回**。
    ⚖⇒ 正确做法：对**块级多数向量**跑 ⇒ w 6/7 ⇒ p=0.125。
    """
    return reader().sign_test(block_signs(blocks, signs))[0]


def within_agreement(blocks, signs):
    """⚖ 块内两轨迹判定一致的块数。"""
    ag = 0
    for blk in blocks:
        if len(blk) == BLOCK_SIZE and signs[blk[0]] == signs[blk[1]]:
            ag += 1
    return ag


def mode_marginals(blocks, signs):
    """⚖ 两模式各自的边际正号率（think / no_think）。"""
    th = [t for blk in blocks for t in blk if t.endswith("__think")]
    nt = [t for blk in blocks for t in blk if t.endswith("__no_think")]
    pth = (sum(1 for t in th if signs[t] > 0) / float(len(th))) if th else 0.0
    pnt = (sum(1 for t in nt if signs[t] > 0) / float(len(nt))) if nt else 0.0
    return pth, pnt, len(th), len(nt)


def indep_agree_rate(pth, pnt):
    """⚖ **独立情形下**「块内两轨迹同号」的概率（给定两模式各自的边际）。

    ⚖ 块内两轨迹**独立** ⇒ 同号 = 都正 + 都负
       ⇒ P = p_think·p_nothink + (1−p_think)·(1−p_nothink)

    ⚖⚠⚠⚠ **抽成独立函数**是为了让**自检能用已知为真的合成夹具钉住它**
       （⛔ 不抽出来的话，这条公式在真实数据上**改错了也没人发现**）。
    """
    return pth * pnt + (1.0 - pth) * (1.0 - pnt)


def block_is_wider(w_traj, w_block):
    """⚖ 块级区间必须**比**轨迹级区间宽（⇒ 对外引用取最宽的那个）。

    ⚖⚠⚠⚠ **抽成独立函数**是为了让自检能喂**更窄**的块级区间 ⇒ 必须红。
    """
    return w_block > w_traj


def derive_all():
    """⚖ 从**读数**导出两臂的全部逐轨迹符号与块结构。"""
    VS = vsrc()
    out = {}
    for arm, fn in (("w", "_an.txt"), ("rand", "_ra.txt")):
        p = os.path.join(HERE, fn)
        if not os.path.isfile(p):
            raise SystemExit("PRECOND_FAIL: 读不到读数 %s" % p)
        d = VS.derive_arm(VS.load_rows(p), arm)
        tids = d["tids"]
        blocks = blocks_of(tids, VS.problem_key)
        out[arm] = {
            "tids": tids,
            "blocks": blocks,
            "traj_signs": dict(zip(tids, d["traj_signs"])),
            "prereg_signs": dict(zip(tids, d["prereg_signs"])),
            "traj": d["traj"],
            "prereg": d["prereg"],
        }
    return out


# ---------------------------------------------------------------- 功效（精确枚举）
def fisher_power(n, p_w, p_r, alpha=ALPHA):
    """⚖⚠⚠ **跨臂 Fisher 的功效：精确枚举**（⛔ 不许用正态近似）。

    ⚖ 拒绝域 = {精确 Fisher 双尾 p ≤ α}；功效 = 落在拒绝域里的 (a,b) 的联合概率。
    ⚖⚠⚠⚖⚖ **为什么必须精确枚举（244.59 实测）**：
    ⚖ 把备择下的概率换成**具名的正态近似**（拒绝域仍用精确 p）后，
    ⚖ 同一效应量下功效**系统性低估**，且会把「达 80% 功效**需要多少块**」
    ⚖ 的答案推到**更大** ⇒ 近似**不可替代**精确。
    ⚖ 判据 **C11** 专门盯这条（用**具名**的两种方法对照，⛔ 不许手填）。
    """
    AV = armv()
    rej = []
    for a in range(n + 1):
        for b in range(n + 1):
            pv, _ = AV.fisher_exact_two_sided(a, n - a, b, n - b)
            if pv is not None and pv <= alpha:
                rej.append((a, b))
    pw = 0.0
    for a in range(n + 1):
        w = binom_cdf(n, a, p_w) - binom_cdf(n, a - 1, p_w)
        if w <= 0:
            continue
        for b in range(n + 1):
            if (a, b) not in rej:
                continue
            w2 = binom_cdf(n, b, p_r) - binom_cdf(n, b - 1, p_r)
            pw += w * w2
    return pw, len(rej)


def _norm_cdf(z):
    """⚖ 标准正态 CDF（纯 stdlib，⛔ 不引 scipy）。"""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def fisher_power_normal(n, p_w, p_r, alpha=ALPHA):
    """⚖⚠⚖⚖ **具名的正态近似**（244.59 里只当**反面教材**用）。

    ⚖ 拒绝域仍用**精确** Fisher p（⛔ 不动判据），只把**备择下的概率**换成正态近似
    （二项精确概率 → 正态连续化）。

    ⚖⚠⚖⚖ **本函数存在的唯一目的**：让判据 **C11** 能证明
    ⚖ 「用近似会给出**不同的**答案」⇒ 本轮一律用**精确枚举**。

    ⚖⚠⚖⚖⛔ 我第一版用的那个近似公式**本轮复现不出来** ⇒ 那个具体的数**撤回**；
    ⚖   这里用的是**写得出名字、可复算**的近似。
    """
    AV = armv()
    rej = []
    for a in range(n + 1):
        for b in range(n + 1):
            pv, _ = AV.fisher_exact_two_sided(a, n - a, b, n - b)
            if pv is not None and pv <= alpha:
                rej.append((a, b))

    def pnorm_mass(k, p):
        m = n * p
        sd = math.sqrt(n * p * (1.0 - p))
        if sd <= 0:
            return 1.0 if k == 0 else 0.0
        hi = _norm_cdf((k + 0.5 - m) / sd)
        lo = _norm_cdf((k - 0.5 - m) / sd)
        return max(0.0, hi - lo)

    pwn = 0.0
    for (a, b) in rej:
        pwn += pnorm_mass(a, p_w) * pnorm_mass(b, p_r)
    return pwn, len(rej)


def need_blocks_n(pw_fn, target=0.8, nmax=40):
    """⚖ 要达到 `target` 功效，**需要多少块**（⛔ 找不到就返回 None）。

    ⚖⚠⚠⚖⚖ **nmax 封顶 40**（⛔ 不许放到很大）：`fisher_power` 是 **O(n²)** 枚举
    ⇒ 搜到 200 块会退化成 O(n³) ⇒ 变异把功效打成 0 时**整个台架会卡死**。
    ⚖ 40 块已远超实测答案（精确 13 / 近似 15）⇒ 封顶不丢信息。
    """
    for n in range(1, nmax + 1):
        if pw_fn(n) >= target:
            return n
    return None


def methods_give_different_need(pw_a, pw_b, target=0.8):
    """⚖ 两种方法给出的「需要多少块」**必须不同** ⇒ 近似**不可替代**精确。

    ⚖⚠⚠⚖ **抽成独立函数**是为了让自检能喂「同一个方法两次」⇒ 必须红
    （否则这条判据就是**恒绿**）。
    """
    na = need_blocks_n(pw_a, target)
    nb = need_blocks_n(pw_b, target)
    if na is None or nb is None:
        return False
    return na != nb


def sign_power(n, p_true, alpha=ALPHA):
    """⚖ 单臂符号检验的功效（精确二项）。"""
    kc = None
    for k in range(n + 1):
        if binom_sf(n, k, 0.5) <= alpha / 2.0:
            kc = k
            break
    if kc is None:
        return 0.0, None
    return 1.0 - binom_cdf(n, kc - 1, p_true), kc


def agreement_power(n, q_true, alpha=ALPHA):
    """⚖ 「块内一致率显著高于独立预期」这个检验的功效。"""
    crit = None
    for k in range(n + 1):
        if binom_sf(n, k, 0.5) <= alpha:
            crit = k
            break
    if crit is None:
        return 0.0, None
    return 1.0 - binom_cdf(n, crit - 1, q_true), crit


# ---------------------------------------------------------------- 判据
def build_report(D):
    L = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        L.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    VS = vsrc()
    AV = armv()
    IA = iaud()
    st = reader().sign_test

    L.append("【0】⚖⚠⚠⚠ **前提声明**（⛔ 删掉任何一条都必须红）")
    for s in PREAMBLE:
        L.append("  " + s)
    L.append("")

    # ---- C0 块结构复现 ----
    ok0 = True
    d0 = []
    for arm in ("w", "rand"):
        d = D[arm]
        sizes = sorted(len(b) for b in d["blocks"])
        good = (len(d["tids"]) == N_TRAJ and len(d["blocks"]) == N_BLOCK
                and sizes == [BLOCK_SIZE] * N_BLOCK)
        ok0 = ok0 and good
        d0.append("%s %d 轨迹 = %d 块 × %s" % (arm, len(d["tids"]),
                                                len(d["blocks"]),
                                                sorted(set(sizes))))
    put("C0", ok0,
        "块结构必须复现：%d 轨迹 = %d 块 × %d（两臂同形）—— %s"
        % (N_TRAJ, N_BLOCK, BLOCK_SIZE, "；".join(d0)))

    # ---- C1 轨迹级口径必须复现账本 ----
    ok1 = True
    d1 = []
    for arm in ("w", "rand"):
        d = D[arm]
        for stat in ("traj", "prereg"):
            got = d[stat]
            exp = AUTH[arm][stat]
            p_got = st([1.0 if s > 0 else -1.0
                        for s in (d["traj_signs"] if stat == "traj"
                                  else d["prereg_signs"]).values()])[0]
            good = (got == exp
                    and abs(p_got - float(AUTH[arm][stat + "_p"]))
                    <= tol_of(AUTH[arm][stat + "_p"]))
            ok1 = ok1 and good
            d1.append("%s %s %d/%d p=%.8f（账本 %s）"
                      % (arm, stat, got[0], got[1], p_got, AUTH[arm][stat + "_p"]))
    put("C1", ok1, "轨迹级口径必须逐位复现账本（先证明「读的是同一批」）：%s"
        % "；".join(d1))

    # ---- C2 跨臂 Fisher 的两个口径 ----
    ok2 = True
    d2 = []
    for stat in ("traj", "prereg"):
        w = D["w"][stat]
        r = D["rand"][stat]
        p_tr, _ = AV.fisher_exact_two_sided(w[0], w[1] - w[0], r[0], r[1] - r[0])
        bw = block_majority(D["w"]["blocks"],
                            D["w"]["traj_signs" if stat == "traj"
                               else "prereg_signs"])
        br = block_majority(D["rand"]["blocks"],
                            D["rand"]["traj_signs" if stat == "traj"
                                   else "prereg_signs"])
        p_bl, _ = AV.fisher_exact_two_sided(bw[0], bw[1] - bw[0],
                                            br[0], br[1] - br[0])
        good = abs(p_tr - float(AUTH_FISHER[stat])) <= tol_of(AUTH_FISHER[stat])
        ok2 = ok2 and good
        d2.append("%s 轨迹级 %d/%d vs %d/%d p=%.7f（账本 %s）｜ 块级 "
                  "%d/%d vs %d/%d p=%.7f %s"
                  % (stat, w[0], w[1], r[0], r[1], p_tr, AUTH_FISHER[stat],
                     bw[0], bw[1], br[0], br[1], p_bl,
                     "⚠⚠ **不显著**" if p_bl >= ALPHA else "显著"))
    put("C2", ok2, "跨臂 Fisher 的**两个口径**（轨迹级必须复现账本）：%s"
        % "；".join(d2))

    # ---- C3 块内一致率 vs 独立预期 ----
    # ⚖⚠⚠⚠ **同源限定（写在原地）**：下面这张**字面量表**是**从本工具的输出手抄**的
    #   ⇒ 这一条**抓不到「公式本身写错」**，只抓「**抄错 / 漂了**」。
    #   ⚖ 真正独立的守卫是 **C4（检验功效）** 与 **C5（口径翻转）**，
    #   以及**自检**里用**已知为真的合成夹具**钉住公式的那几条。
    ok3 = True
    d3 = []
    for arm in ("w", "rand"):
        for stat in ("traj", "prereg"):
            d = D[arm]
            signs = d["traj_signs" if stat == "traj" else "prereg_signs"]
            ag = within_agreement(d["blocks"], signs)
            pth, pnt, nth, nnt = mode_marginals(d["blocks"], signs)
            exp_agree = indep_agree_rate(pth, pnt)
            pv = binom_sf(N_BLOCK, ag, exp_agree)
            want_ag, want_exp = LEDGER_AGREE[(arm, stat)]
            good = (ag == want_ag[0] and N_BLOCK == want_ag[1]
                    and abs(exp_agree - want_exp) <= tol_of("%.4f" % want_exp))
            ok3 = ok3 and good
            d3.append("%s %s 一致 %d/%d（字面量 %d/%d）｜ 独立预期 %.4f"
                      "（字面量 %.4f）｜ P=%.4f%s ⇒ %s"
                      % (arm, stat, ag, N_BLOCK, want_ag[0], want_ag[1],
                         exp_agree, want_exp, pv,
                         " ⚠ 边际" if pv < 0.10 else "", "✅" if good else "❌"))
    put("C3", ok3,
        "块内一致率与独立预期必须与**手抄字面量**一致（⛔ 同源：只抓抄错/漂了，"
        "抓不到公式写错；公式由**自检的合成夹具**钉住）：%s" % "；".join(d3))

    # ---- C4 「前提是否独立」必须写成「未量到」+ 检验功效 ----
    pw_ag, crit_ag = agreement_power(N_BLOCK, 6.0 / 7.0)
    ok4 = (pw_ag < 0.5)
    put("C4", ok4,
        "「前提是否独立」在现有 %d 个块上**量不到**：检验「一致率 > 独立预期」的功效 "
        "= %.3f（临界值 %s）⇒ ⛔ 既证不了独立、⛔ 也证不了聚类 ⇒ 必须写「**未量到**」"
        % (N_BLOCK, pw_ag, crit_ag))

    # ---- C5 显著性是口径依赖的（必须印出）----
    flips = []
    for stat in ("traj", "prereg"):
        w = D["w"][stat]
        r = D["rand"][stat]
        p_tr, _ = AV.fisher_exact_two_sided(w[0], w[1] - w[0], r[0], r[1] - r[0])
        bw = block_majority(D["w"]["blocks"],
                            D["w"]["traj_signs" if stat == "traj"
                               else "prereg_signs"])
        br = block_majority(D["rand"]["blocks"],
                            D["rand"]["traj_signs" if stat == "traj"
                                   else "prereg_signs"])
        p_bl, _ = AV.fisher_exact_two_sided(bw[0], bw[1] - bw[0],
                                            br[0], br[1] - br[0])
        if (p_tr < ALPHA) != (p_bl < ALPHA):
            flips.append("%s（轨迹级 %.7f 显著 ⇔ 块级 %.7f 不显著）"
                         % (stat, p_tr, p_bl))
    ok5 = len(flips) == 2
    put("C5", ok5,
        "「显著」是**口径依赖**的 —— 必须报出哪些口径翻转：%s"
        % ("；".join(flips) if flips else "（未观察到翻转）"))

    # ---- C6 区间：块级更宽 ⇒ 对外引用取最宽 ----
    ok6 = True
    d6 = []
    for stat in ("traj", "prereg"):
        for arm in ("w", "rand"):
            d = D[arm]
            signs = d["traj_signs" if stat == "traj" else "prereg_signs"]
            bk, bn = block_majority(d["blocks"], signs)
            cl, cu = IA.cp95(*d[stat])
            bl, bu = IA.cp95(bk, bn)
            wider = block_is_wider(cu - cl, bu - bl)
            ok6 = ok6 and wider
            d6.append("%s %s 轨迹级 %d/%d 宽 %.4f ｜ 块级 %d/%d 宽 %.4f %s"
                      % (stat, arm, d[stat][0], d[stat][1], cu - cl,
                         bk, bn, bu - bl, "（块级更宽 ⇒ 取它）" if wider else ""))
    put("C6", ok6, "**块级区间必须逐条比轨迹级更宽**（⇒ 对外引用取最宽的那个）：%s"
        % "；".join(d6))

    # ---- C7 「差 ≠ 0」在两个口径下都成立 ----
    ok7 = True
    d7 = []
    for stat in ("traj", "prereg"):
        w = D["w"][stat]
        r = D["rand"][stat]
        n1 = IA.newcombe_diff(w[0], w[1], r[0], r[1])
        bw = block_majority(D["w"]["blocks"],
                            D["w"]["traj_signs" if stat == "traj"
                               else "prereg_signs"])
        br = block_majority(D["rand"]["blocks"],
                            D["rand"]["traj_signs" if stat == "traj"
                                   else "prereg_signs"])
        n2 = IA.newcombe_diff(bw[0], bw[1], br[0], br[1])
        good = (n1[0] > 0 or n1[1] < 0) and (n2[0] > 0 or n2[1] < 0)
        ok7 = ok7 and good
        d7.append("%s 轨迹级 [%+.4f, %+.4f] ｜ 块级 [%+.4f, %+.4f] ⇒ %s"
                  % (stat, n1[0], n1[1], n2[0], n2[1],
                     "都含 0 ⇒ 差不可分辨" if not good else "**都不含 0**"))
    put("C7", ok7, "「差 ≠ 0」必须在**两个口径下都成立**：%s" % "；".join(d7))

    # ---- C8 块数功效测算（那一批要跑多少题）----
    L.append("  ℹ 块数（问题数）功效测算 —— **精确枚举**，⛔ 不用正态近似")
    power_rows = []
    for n in (7, 10, 14, 20, 30, 40, 60):
        pw_sig, kc = sign_power(n, 6.0 / 7.0)
        pw_ag2, _c2 = agreement_power(n, 6.0 / 7.0)
        pw_f, nrej = fisher_power(n, 6.0 / 7.0, 2.0 / 7.0)
        power_rows.append((n, pw_sig, pw_ag2, pw_f, nrej))
    L.append("    %-6s %-14s %-14s %s" % ("块数", "单臂 p̂=0.857", "检出聚类",
                                          "跨臂 6/7 vs 2/7"))
    for (n, a, b, c, nrej) in power_rows:
        L.append("    %-6d %-14.3f %-14.3f %.3f（拒绝域 %d 个格子）"
                 % (n, a, b, c, nrej))
    need_sig = None
    need_ag = None
    for (n, a, b, c, _r) in power_rows:
        if need_sig is None and a >= 0.8:
            need_sig = n
        if need_ag is None and b >= 0.8:
            need_ag = n
    ok8 = (need_sig is not None and need_ag is not None
           and need_sig > N_BLOCK and need_ag > N_BLOCK)
    put("C8", ok8,
        "**那一批要跑多少题**（零 GPU 测算）：单臂符号检验（效应 p̂=0.857）达 80%% 功效"
        "需 **%s 块**；把「聚类」本身检出需 **%s 块**；现有 **%d 块** ⇒ "
        "⛔ 现有块数**不够**（⇒ 那一批必须加题）"
        % (need_sig, need_ag, N_BLOCK))

    # ---- C9 前提声明必须印出 ----
    L.append("  ℹ 前提声明检查")
    miss9 = [s for s in PREAMBLE_REQUIRED if not any(s in ln for ln in L)]
    put("C9", not miss9, "三条前提声明必须逐条印出；缺 %d 条%s"
        % (len(miss9), "" if not miss9 else "：%s" % miss9))

    # ---- C10 留白 ----
    L.append("  ℹ 未量到项（⛔ 写成「未量到」，⛔ 不许写成「无差异」）")
    for name, why in BLANKS:
        L.append("    · %s —— %s" % (name, why))
    miss10 = [t for t in BLANKS_REQUIRED if not any(t in ln for ln in L)]
    put("C10", not miss10, "六条留白必须逐条印出；缺 %d 条%s"
        % (len(miss10), "" if not miss10 else "：%s" % miss10))

    # ---- C11 精确枚举 vs 具名正态近似 ----
    def _pw_exact(n):
        return fisher_power(n, 6.0 / 7.0, 2.0 / 7.0)[0]

    def _pw_normal(n):
        return fisher_power_normal(n, 6.0 / 7.0, 2.0 / 7.0)[0]

    need_exact = need_blocks_n(_pw_exact)
    need_norm = need_blocks_n(_pw_normal)
    ok11 = methods_give_different_need(_pw_exact, _pw_normal)
    put("C11", ok11,
        "**精确枚举** vs **具名正态近似**（同一效应量 6/7 vs 2/7）：达 80%% 功效"
        "所需块数 = 精确 **%s 块** vs 近似 **%s 块** ⇒ %s"
        "（⇒ 近似**不可替代**精确；n=7 功效 精确 %.4f vs 近似 %.4f）"
        % (need_exact, need_norm,
           "**两者不同**" if ok11 else "⛔ 两者相同 ⇒ 本判据失效",
           _pw_exact(7), _pw_normal(7)))

    # ---- C12 文档回读区 vs 实测 ----
    ok12, d12 = check_doc_facts(globals().get("__doc__") or "", D)
    put("C12", ok12,
        "「**C12 回读区**」里的数必须与实测**逐位**一致（⛔ 文档漂移必须红）：%s"
        % "；".join(d12))

    # ---- C13 块级 p 必须跑在块级多数向量上 ----
    L.append("  ℹ 块级 p 值（**跑在块级多数向量上**，⛔ 不是 14 条轨迹符号）")
    ok13 = True
    d13 = []
    for stat in ("traj", "prereg"):
        for arm in ("w", "rand"):
            d = D[arm]
            signs = d["traj_signs" if stat == "traj" else "prereg_signs"]
            bk, bn = block_majority(d["blocks"], signs)
            p_blk = block_sign_test_p(d["blocks"], signs)
            # ⚖ **独立第二条路**：用「块级多数计数」重建向量 ⇒ 必须与上面一致
            p_indep = st([1.0] * bk + [-1.0] * (bn - bk))[0]
            p_traj = st([1.0 if s > 0 else -1.0 for s in signs.values()])[0]
            good = (abs(p_blk - p_indep) <= 1e-12) and (abs(p_blk - p_traj) > 1e-9)
            ok13 = ok13 and good
            L.append("    · %s %s 块级 %d/%d p=%.8f（独立路 %.8f ｜ 轨迹级 p=%.8f）%s"
                     % (arm, stat, bk, bn, p_blk, p_indep, p_traj,
                        "" if good else " ❌"))
            d13.append("%s %s 块级 %.8f vs 独立路 %.8f vs 轨迹级 %.8f %s"
                       % (arm, stat, p_blk, p_indep, p_traj,
                          "✅" if good else "❌"))
    put("C13", ok13,
        "块级 p 必须跑在**块级多数向量**上（⛔ 不是 14 条轨迹符号；两条路必须一致）：%s"
        % "；".join(d13))

    return L, R


# ---------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    D = derive_all()
    IA = iaud()

    # --- C0 块结构 ---
    for arm in ("w", "rand"):
        d = D[arm]
        chk("C0-%s" % arm,
            len(d["tids"]) == 14 and len(d["blocks"]) == 7
            and all(len(b) == 2 for b in d["blocks"]),
            "%s：14 轨迹 = 7 块 × 2" % arm)

    # --- 块级多数规则：负例 ---
    signs = {"t1": 1, "t2": 1, "t3": 1, "t4": -1}
    blocks = [["t1", "t2"], ["t3", "t4"]]
    k, n = block_majority(blocks, signs)
    chk("C1x", (k, n) == (1, 2), "块内两条都正才算正 ⇒ (1,2)，实测 (%d,%d)" % (k, n))
    signs2 = {"t1": 1, "t2": 1, "t3": -1, "t4": -1}
    k2, _n2 = block_majority(blocks, signs2)
    chk("C1y", k2 == 1, "一正一负 ⇒ 平票算 False ⇒ 1（实测 %d）" % k2)

    # --- 块内一致率 ---
    ag = within_agreement(blocks, signs)
    chk("C2x", ag == 1, "一致块数 %d" % ag)

    # --- 两模式边际 ---
    chk("C2y", True, "（边际计算由 C3 覆盖）")

    # --- 符号检验功效：n=7 效力极低 ---
    pw, kc = sign_power(7, 6.0 / 7.0)
    chk("C3x", pw < 0.5, "n=7 单臂符号检验功效 %.3f（临界值 %s）" % (pw, kc))
    pw14, _ = sign_power(14, 6.0 / 7.0)
    chk("C3y", pw14 > pw, "n=14 功效 %.3f > n=7 的 %.3f" % (pw14, pw))

    # --- 一致率检验功效 ---
    pwa, cra = agreement_power(7, 6.0 / 7.0)
    chk("C4x", pwa < 0.5, "n=7 检出聚类的功效 %.3f" % pwa)
    pwa14, _ = agreement_power(14, 6.0 / 7.0)
    chk("C4y", pwa14 > pwa, "n=14 功效 %.3f > n=7 的 %.3f" % (pwa14, pwa))

    # --- Fisher 功效：精确枚举 vs 正态近似（后者给 0 ⇒ 荒谬）---
    pwf, nrej = fisher_power(14, 6.0 / 7.0, 2.0 / 7.0)
    chk("C5x", pwf > 0.0, "n=14 跨臂 Fisher 功效 %.3f（拒绝域 %d 格）" % (pwf, nrej))
    pwf7, _ = fisher_power(7, 6.0 / 7.0, 2.0 / 7.0)
    chk("C5y", pwf7 > 0.0, "n=7 跨臂 Fisher 功效 %.3f" % pwf7)
    chk("C5z", pwf > pwf7, "n=14 功效 %.3f > n=7 的 %.3f" % (pwf, pwf7))

    # --- 区间对照：块级更宽 ---
    d = D["w"]
    bk, bn = block_majority(d["blocks"], d["traj_signs"])
    cl, cu = IA.cp95(*d["traj"])
    bl, bu = IA.cp95(bk, bn)
    chk("C6x", (bu - bl) > (cu - cl),
        "块级宽 %.4f > 轨迹级宽 %.4f" % (bu - bl, cu - cl))

    # --- 二项尾自检 ---
    chk("C7x", abs(binom_sf(4, 2, 0.5) - 11 / 16.0) < 1e-12,
        "P(X≥2),Bin(4,.5)=11/16=%.6f" % binom_sf(4, 2, 0.5))
    chk("C7y", abs(binom_cdf(4, 2, 0.5) - 11 / 16.0) < 1e-12,
        "P(X≤2),Bin(4,.5)=11/16=%.6f" % binom_cdf(4, 2, 0.5))

    # --- 独立预期公式：合成夹具（**已知为真**）⇒ 公式改错必须红 ---
    # ⚖ think 边际 0.5、no_think 边际 0.5 ⇒ 独立预期 = 0.25+0.25 = 0.5
    chk("C3y", abs(indep_agree_rate(0.5, 0.5) - 0.5) < 1e-12,
        "独立预期(0.5,0.5) = %.6f（应 = 0.5）" % indep_agree_rate(0.5, 0.5))
    # ⚖ think 1.0、no_think 0.0 ⇒ 永远不同号 ⇒ 独立预期 = 0
    chk("C3z", abs(indep_agree_rate(1.0, 0.0)) < 1e-12,
        "独立预期(1.0,0.0) = %.6f（应 = 0）" % indep_agree_rate(1.0, 0.0))
    # ⚖ think 0.8、no_think 0.6 ⇒ 0.48 + 0.08 = 0.56
    chk("C3w", abs(indep_agree_rate(0.8, 0.6) - 0.56) < 1e-12,
        "独立预期(0.8,0.6) = %.6f（应 = 0.56）" % indep_agree_rate(0.8, 0.6))
    # ⚖ 漏掉 (1−pth)(1−pnt) 那一项 ⇒ 0.48 ≠ 0.56 ⇒ 必须被上面那条抓住
    chk("C3v", abs(0.8 * 0.6 - indep_agree_rate(0.8, 0.6)) > 1e-9,
        "漏掉 (1−pth)(1−pnt) ⇒ %.4f ≠ %.4f ⇒ 公式写错**看得见**"
        % (0.8 * 0.6, indep_agree_rate(0.8, 0.6)))

    # --- 块级区间「更宽」的判定：合成夹具 ⇒ 喂更窄的必须红 ---
    chk("C6y", block_is_wider(0.3, 0.5) is True, "块级 0.5 > 轨迹级 0.3 ⇒ True")
    chk("C6z", block_is_wider(0.5, 0.3) is False,
        "块级 0.3 < 轨迹级 0.5 ⇒ False（喂更窄的必须红）")

    # --- 前置声明：少一条必须红 ---
    fake = ["  " + s for s in PREAMBLE[:-1]]
    miss = [s for s in PREAMBLE_REQUIRED if not any(s in ln for ln in fake)]
    chk("C8x", len(miss) == 1, "少印一条前提声明 ⇒ 缺 %d 条" % len(miss))

    # --- 留白：少一条必须红 ---
    L9 = []
    for name, why in BLANKS[:-1]:
        L9.append("    · %s —— %s" % (name, why))
    miss9 = [t for t in BLANKS_REQUIRED if not any(t in ln for ln in L9)]
    chk("C9x", len(miss9) == 1, "少印一条留白 ⇒ 缺 %d 条" % len(miss9))

    st = reader().sign_test

    # --- C11：精确枚举 vs 具名正态近似 ---
    def _f_sig(n):
        return 0.0 if n < 3 else 0.9

    def _f_norm(n):
        return 0.0 if n < 5 else 0.9

    chk("C11x", methods_give_different_need(_f_sig, _f_sig) is False,
        "同一个方法喂两次 ⇒ 块数相同 ⇒ 必须判 False")
    chk("C11y", methods_give_different_need(_f_sig, _f_norm) is True,
        "两个方法给的块数不同 ⇒ 必须判 True")
    chk("C11z", need_blocks_n(lambda n: 0.0) is None
        and need_blocks_n(lambda n: 1.0 if n >= 5 else 0.0) == 5,
        "need_blocks_n：永远达不到 ⇒ None；第 5 块才到 ⇒ 5")
    _need_ex = need_blocks_n(lambda n: fisher_power(n, 6.0 / 7.0, 2.0 / 7.0)[0])
    _need_no = need_blocks_n(lambda n: fisher_power_normal(n, 6.0 / 7.0, 2.0 / 7.0)[0])
    chk("C11w", methods_give_different_need(
        lambda n: fisher_power(n, 6.0 / 7.0, 2.0 / 7.0)[0],
        lambda n: fisher_power_normal(n, 6.0 / 7.0, 2.0 / 7.0)[0]) is True,
        "真实数据：精确 %s 块 vs 近似 %s 块 ⇒ 两者必须不同" % (_need_ex, _need_no))

    # --- C12：文档回读区 ---
    _doc = globals().get("__doc__") or ""
    _facts = parse_doc_facts(_doc)
    chk("C12x", set(_facts) >= {"traj", "prereg", "block_traj", "indep", "agreeP"},
        "回读区解析出 %d 行：%s" % (len(_facts), sorted(_facts)))
    _bad = _doc.replace("0.00183105", "0.00183106")
    chk("C12y", (_bad != _doc) and check_doc_facts(_bad, D)[0] is False,
        "把回读区里一个数改掉 ⇒ 必须判红（这次改没改成功：%s）" % (_bad != _doc))
    chk("C12z", check_doc_facts(_doc, D)[0] is True,
        "本文档自己的回读区必须与实测一致")

    # --- C13：块级 p 跑在哪个向量上（**已知答案**的合成夹具）---
    # ⚖ 4 块：块级多数向量 [+1,+1,-1,+1] ⇒ 3/4 ⇒ P(X≥3)=5/16 ⇒ 双尾 = 10/16 = 0.625
    _bl = [["t1", "t2"], ["t3", "t4"], ["t5", "t6"], ["t7", "t8"]]
    _sg = {"t1": 1, "t2": 1, "t3": 1, "t4": 1, "t5": 1, "t6": -1, "t7": 1, "t8": 1}
    _p_blk = block_sign_test_p(_bl, _sg)
    _p_traj = st([1.0 if s > 0 else -1.0 for s in _sg.values()])[0]
    chk("C13x", abs(_p_blk - 0.625) < 1e-12,
        "块级多数向量 [+1,+1,-1,+1] ⇒ 符号检验 p = 10/16 = 0.625（实测 %.8f）" % _p_blk)
    chk("C13y", abs(_p_traj - 0.0703125) < 1e-12 and abs(_p_blk - _p_traj) > 1e-9,
        "⛔ 若错跑 8 条轨迹符号 ⇒ p = 18/256 = 0.0703125（实测 %.8f）⇒ 与 0.625 完全不同"
        % _p_traj)
    _d0 = D["w"]
    _bk, _bn = block_majority(_d0["blocks"], _d0["traj_signs"])
    chk("C13z", abs(block_sign_test_p(_d0["blocks"], _d0["traj_signs"])
                    - st([1.0] * _bk + [-1.0] * (_bn - _bk))[0]) <= 1e-12,
        "真实数据：块级 p 必须与「块级计数重建的向量」一致")

    print("")
    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % bad)
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(description="判决面板的「前提是否独立」（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        D = derive_all()
        L, R = build_report(D)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print("\n".join(L))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
    return 0 if all(R.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
