#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""denom_premise_audit.py —— 剂量轴的**分母**建立在哪几条前提上（零 GPU）

🔴🔴 **本工具问什么**

  244.50 把分母换成探针原式 `inj = P + max(1, floor(n_gen*pos_frac)) - 1`，
  并把「`P == len(pid)`」记成**仍未验**。⚖ 那条「未验」的**上游**其实
  在账本 244.7 已经查过：侧车自报 `extra.prompt_tokens` 与独立加载 tokenizer
  重编码 `chat_template_input` 的长度 **60/60 逐位相等**。
  ⚠⚠⚠ **但 244.7 结尾写的是**：「本节只验了侧车的 60 条，也就是 rand 臂的数据
  底座；**w 臂那 137 格的 `P` 仍未经独立复算**。」

  ⚖⚖ 本工具就查这三件事，全部**零 GPU、纯本地**：

    C1  两臂的**格子键**是否逐条相同？⇒ 决定 rand 臂那条验证在**数据底座**上
         能不能覆盖 w 臂。
    C2  那 14 条轨迹的**组成**：是不是 7 题 × {think, no_think} **逐题配对**？
    C3  逐题量 think→no_think 的 `P` 差（账本 244.7.7 记的是**恒 +4**）⇒ 复现它。
    C4  把 `P` 按 4 个方向扰动 ±4（= 那个模板偏移），**剂量结论稳不稳**。
    C5  `P` 在分母里占多大权重（`P / t`），4 个 token 相当于分母的百分之几。

⚖⚠⚠⚠ **本工具答不了、也⛔ 不许假装答了的一条**

  ⚖ **「已验的那 60 条」里到底有没有这 14 条 tid —— 本地量不到。**
     244.7 只把 **60/60 这个数**记进了账本，⛔ **没落那 60 个 tid 的清单**。
  ⚖⇒ 所以「rand 臂验证 ⇒ w 臂也验过」这一步**仍是推断，不是实测**。
  ⚗⇒ **不许**把 C1 的「两臂格子键相同」写成「w 臂的 P 已验过」：
     C1 证明的是**两臂读同一批格子**，不是**那批格子在不在已验集合里**。
     ⇒ 这正是账本 244.5.2 那个「同源当成互证」的同族错，方向相反。
  ⚖⇒ 要真核对，只有两条路：① 落 60 个 tid 的清单进产物再比对；
     ② 远端 `ls` 侧车目录（只加载 tokenizer，⛔ 不占显存）。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不写数据文件、⛔ 不连远端。
⚖⚠⚠⚖ 每条判据都必须**能红**：变异台改的是喂进来的**数据形状**。
"""

import argparse
import io
import json
import math
import os
import statistics as _st
import sys

DEFAULT_FILES = {"w": ".cache/r244/_an.txt", "rand": ".cache/r244/_ra.txt"}
# ⚖ 244.7.7 记的模板偏移：think 与 no_think 的 P 差**恒 +4**
TEMPLATE_OFFSET = 4
# ⚖ 244.7.2 记的已验侧车数（⚠⚠⚠ **只有这个数，没有 tid 清单** ⇒ 见文件头）
LEDGER_SIDECARS = 60
# ⚖ 本批的轨迹组成（实测后写入；由 C2 自己印出来核对）
N_QUESTIONS = 7
SUFFIXES = ("think", "no_think")

# ⚖⚖⚖⚖ **真数据冻结的剂量轴黄金样本**（14 条轨迹 / 109 格，2026-10-19 从
# `.cache/r244/_an.txt` 导出并**逐条手抄成字面量**）。
# ⚖ 只冻结**剂量轴三要素** `P` / `n_gen` / 各档 `n_sites` + 后缀；
# ⚠ **读数 `d` 不冻结**（夹具里用与 frac 单调的合成值）⇒ ⛔ 不复制任何真实读数。
# ⚖ 后缀顺序刻意**按 (题, 后缀) 排序**⇒ 每题的 think/no_think **逐题配对**成立。
GOLD_TRAJ = [
    ('p00', 'no_think', 112, 757, [1, 7, 30, 122, 245, 367, 428]),
    ('p00', 'think', 108, 3309, [1, 6, 27, 110, 440, 881, 1321, 1541]),
    ('p02', 'no_think', 196, 1124, [2, 11, 47, 189, 379, 568, 663]),
    ('p02', 'think', 192, 7938, [4, 16, 65, 260, 1040, 2080, 3120, 3640]),
    ('p03', 'no_think', 139, 2005, [1, 4, 17, 71, 285, 570, 855, 998]),
    ('p03', 'think', 135, 7303, [1, 3, 14, 59, 236, 946, 1893, 2839, 3312]),
    ('p05', 'no_think', 165, 441, [1, 6, 24, 96, 192, 288, 336]),
    ('p05', 'think', 161, 3434, [1, 7, 29, 117, 469, 939, 1408, 1643]),
    ('p07', 'no_think', 203, 4014, [2, 8, 34, 138, 552, 1105, 1657, 1933]),
    ('p07', 'think', 199, 6003, [3, 12, 50, 200, 800, 1600, 2400, 2800]),
    ('p18', 'no_think', 277, 1758, [1, 4, 18, 72, 289, 578, 867, 1011]),
    ('p18', 'think', 273, 10094, [5, 20, 83, 332, 1330, 2660, 3990, 4655]),
    ('p24', 'no_think', 150, 935, [2, 9, 38, 154, 308, 462, 539]),
    ('p24', 'think', 146, 7621, [3, 15, 61, 247, 989, 1978, 2967, 3461]),
]


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 小工具
def load_jsonl(path):
    """⚖ 逐行读 JSON。⚖⚠⚠⚠ 坏行必须**报错**，⛔ 不许静默跳过。"""
    out, bad = [], 0
    for line in io.open(path, encoding="utf-8", errors="replace"):
        t = line.strip()
        if not t.startswith("{"):
            continue
        try:
            out.append(json.loads(t))
        except Exception:
            bad += 1
    if bad:
        raise HardFail("文件 %s 有 %d 行 JSON 解析失败 ⇒ ⛔ 拒读" % (path, bad))
    if not out:
        raise HardFail("文件 %s 一条记录都没有 ⇒ ⛔ 拒读" % path)
    return out


def rank(v):
    """⚖ 平均秩。⚖⚠ 并列**必须**取平均秩，⛔ 不许用顺序名次（会静默错一个值）。"""
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
    if len(xs) != len(ys) or len(xs) < 3:
        raise HardFail("Spearman 需要成对且 n≥3（得到 %d,%d）" % (len(xs), len(ys)))
    rx, ry = rank(xs), rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx)
                    * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def cell_key(r):
    """⚖⚖ 一个格子的**输入身份**：两臂同键 ⇒ 读的是同一批 sidecar + npz。

    ⚖⚠⚠⚠ **为什么不把 `arm` 放进 key**：那正是要证明「两臂只差向量」的那个量，
    ⛔ 放进 key 会让判据恒成立（自己和自己比）。"""
    return (r.get("tid"), r.get("P"), r.get("n_gen"), r.get("pos_frac"),
            r.get("inject_scope"), r.get("inject_n_sites"))


def denom_of(r):
    """⚖ 探针原式（244.50 已钉）：`P + max(1, floor(n_gen*pos_frac)) - 1`。"""
    P, ng, pf = r.get("P"), r.get("n_gen"), r.get("pos_frac")
    if not P or not ng or pf is None:
        raise HardFail("记录 %r 缺 P/n_gen/pos_frac ⇒ 分母**未量到**"
                       % (r.get("tid"),))
    return int(P) + max(1, int(int(ng) * float(pf))) - 1


def d_of(r):
    lo, hi = r.get("p9_lo_meas"), r.get("p9_hi_meas")
    if lo is None or hi is None:
        raise HardFail("记录 %r 缺 p9_lo_meas/p9_hi_meas ⇒ **未量到**"
                       % (r.get("tid"),))
    return float(hi) - float(lo)


def qsplit(recs):
    """⚖ 只用 scope=k 的格切四分位（单/全口径注入的量根本不同）。"""
    ks = [r for r in recs if r.get("inject_scope") == "k" and r.get("inject_n_sites")]
    ns = [float(r["inject_n_sites"]) for r in ks]
    dd = [d_of(r) for r in ks]
    return ks, ns, dd


def bands_of(ns, dd, dens):
    """⚖ 给定分母序列，算出 rho、分位点、档数、各档为正数。"""
    fr = [a / b for a, b in zip(ns, dens)]
    q = _st.quantiles(fr, n=4)
    out = []
    for lo_, hi_ in ((None, q[0]), (q[0], q[1]), (q[1], q[2]), (q[2], None)):
        sel = [(f, d) for f, d in zip(fr, dd)
               if (lo_ is None or f > lo_) and (hi_ is None or f <= hi_)]
        out.append((len(sel), sum(1 for _f, d in sel if d > 0)))
    return spearman(fr, dd), q, out, fr


# --------------------------------------------------------------- 判据
def audit(wpath, rpath):
    L = ["【分母前提审计】w=%s ｜ rand=%s" % (wpath, rpath)]
    W, R = load_jsonl(wpath), load_jsonl(rpath)
    ok = True

    # ---- C1 批次同一性 --------------------------------------------------
    kw = sorted(map(repr, map(cell_key, W)))
    kr = sorted(map(repr, map(cell_key, R)))
    same = (kw == kr)
    L.append("  C1 格子键 (tid,P,n_gen,pos_frac,scope,n_sites) 逐条比较："
             "w %d 格 / rand %d 格 ⇒ %s"
             % (len(kw), len(kr),
                "✅ **完全相同** ⇒ 两臂只差 W 向量，读的是同一批 sidecar+npz"
                if same else "⛔ 有 %d 条不同 ⇒ 两臂**不是**同一批格子" % len(set(kw) ^ set(kr))))
    if same:
        L.append("     ⚖⚠⚠⚠ **这只证明「两臂同底座」，⛔ 不证明「那底座在已验的 60 条里」**")
    ok &= same

    # ---- C2 轨迹组成：逐题配对 ------------------------------------------
    pairs, lone = {}, []
    for r in W:
        tid = r.get("tid") or ""
        parts = tid.split("__")
        q = parts[2] if len(parts) > 2 else tid
        sfx = parts[-1] if parts else ""
        pairs.setdefault(q, set()).add(sfx)
    for q, s in pairs.items():
        if set(SUFFIXES) - s:
            lone.append(q)
    L.append("  C2 轨迹组成：%d 题 × %s ｜ 配对齐全 %s"
             % (len(pairs), list(SUFFIXES),
                "✅" if not lone else "⛔ 这些题缺一臂：" + ",".join(lone)))
    ok &= (not lone)

    # ---- C3 逐题 think→no_think 的 P 差 --------------------------------
    Pby = {}
    for r in W:
        Pby[r.get("tid")] = r.get("P")
    diffs = []
    for q in sorted(pairs):
        a, b = Pby.get("aime__aime25__%s__think" % q), Pby.get("aime__aime25__%s__no_think" % q)
        if a is not None and b is not None:
            diffs.append(b - a)
    uniq = sorted(set(diffs))
    uniform = (len(uniq) == 1 and uniq[0] > 0)
    L.append("  C3 think→no_think 的 P 差：逐题 %d 个值，唯一值 %s ⇒ %s"
             % (len(diffs), uniq,
                "✅ 全为 +%d（账本 244.7.7 记的**恒 +4** 复现）" % TEMPLATE_OFFSET
                if uniq == [TEMPLATE_OFFSET] else
                ("✅ 恒定 +%d（但**不是**账本记的 +%d）" % (uniq[0], TEMPLATE_OFFSET)
                 if uniform else "⛔ 不恒定 ⇒ C4 的扰动幅度要按实测值取")))
    ok &= uniform

    # ---- C4 把这个偏移当不确定度：剂量结论稳不稳 ------------------------
    ks, ns, dd = qsplit(W)
    base_rho, base_q, base_bands, base_fr = bands_of(ns, dd, [denom_of(r) for r in ks])
    off = uniq[0] if uniform else TEMPLATE_OFFSET
    perturbs = {
        "no_think 全 P−%d" % off: [r["P"] - (off if str(r.get("tid", "")).endswith("no_think") else 0)
                                   for r in ks],
        "think 全 P−%d" % off: [r["P"] - (off if str(r.get("tid", "")).endswith("think")
                                          and not str(r.get("tid", "")).endswith("no_think") else 0)
                                for r in ks],
        "全部 P−%d" % off: [r["P"] - off for r in ks],
        "全部 P+%d" % off: [r["P"] + off for r in ks],
    }
    rows, rhos, bandset = [], [], set()
    for lab, Ps in sorted(perturbs.items()):
        dens = [P + max(1, int(int(r["n_gen"]) * float(r["pos_frac"]))) - 1
                for P, r in zip(Ps, ks)]
        rho, q, bands, _fr = bands_of(ns, dd, dens)
        rows.append((lab, rho, q, bands))
        rhos.append(rho)
        bandset.add(tuple(bands))
    L.append("  C4 基准 rho=%+.4f 分位点 %.4f/%.4f/%.4f 档 %s 为正 %s"
             % (base_rho, base_q[0], base_q[1], base_q[2],
                [b[0] for b in base_bands], [b[1] for b in base_bands]))
    for lab, rho, q, bands in rows:
        L.append("     %-16s rho=%+.4f 档 %s 为正 %s" % (lab, rho,
                                                        [b[0] for b in bands],
                                                        [b[1] for b in bands]))
    stable_bands = (len(bandset) == 1)
    L.append("     ⇒ %s" % ("✅ 四个扰动下**分档表完全一致**" if stable_bands else
                            "⚠⚠⚠ 四个扰动下**分档表变了 %d 种** ⇒ **分档表是脆弱量**，"
                            "⛔ 不可当结论引用（只报区间）" % len(bandset)))
    rho_lo, rho_hi = min(rhos + [base_rho]), max(rhos + [base_rho])
    L.append("     ⇒ rho 的区间 = [%+.4f, %+.4f]（跨度 %.4f）⇒ %s"
             % (rho_lo, rho_hi, rho_hi - rho_lo,
                "✅ 符号与量级都稳" if rho_lo > 0.6 else "⛔ 扰动足以翻符号 ⇒ 结论不成立"))
    ok &= (rho_lo > 0.6)

    # ---- C5 P 在分母里的权重 -------------------------------------------
    ts = [max(1, int(int(r["n_gen"]) * float(r["pos_frac"]))) for r in ks]
    dens0 = [denom_of(r) for r in ks]
    ratios = [r["P"] / t for r, t in zip(ks, ts)]
    lo_tok = min(off / d * 100.0 for d in dens0)
    hi_tok = max(off / d * 100.0 for d in dens0)
    L.append("  C5 P/t 比值 %.4f…%.4f（中位 %.4f）｜ %d 个 token 相当于分母的 **%.2f%% … %.2f%%**"
             % (min(ratios), max(ratios), _st.median(ratios), off, lo_tok, hi_tok))

    L.append("")
    L.append("⚖⚖⚖ **本工具答不了的一条**（⛔ 不许当已验）：")
    L.append("  「已验的 %d 条侧车里有没有这 %d 个 tid」—— 244.7 只把 **%d/%d** 这个数"
             % (LEDGER_SIDECARS, len(Pby), LEDGER_SIDECARS, LEDGER_SIDECARS))
    L.append("  记进了账本，**没落 tid 清单** ⇒ 本地量不到。")
    L.append("  ⇒ 244.7 结尾那句「w 臂那 137 格的 P 仍未经独立复算」**本节不撤回**，")
    L.append("    但它的**理由要改**：不是「两臂底座不同」（C1 已证底座相同），")
    L.append("    而是「**没有 key 清单，无法核对那 14 条落在不在已验集合里**」。")
    return L, (0 if ok else 1)


# --------------------------------------------------------------- 自检
def selftest(files=None):
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    chk("C0", abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-12,
        "完全同序 ⇒ rho=%.6f" % spearman([1, 2, 3, 4], [10, 20, 30, 40]))
    # ⚖⚠⚠ 并列必须平均秩：用例必须选「两种名次处理会给出不同 rho」的那一组
    _a, _b = [1, 1, 2, 3], [1, 2, 2, 3]
    chk("C0b", abs(spearman(_a, _b) - 0.8333333333333333) < 1e-12,
        "并列处理不同会改 rho ⇒ %.6f（顺序名次会给 0.838870）" % spearman(_a, _b))

    # ⚖ 合成夹具：两臂**同键**、7 题 × 两后缀、逐题 P 差恒 +4、剂量单调
    def build(arm, break_key=False, break_pair=False, offset=TEMPLATE_OFFSET,
              nm=4):
        rs = []
        ms = [(i + 1) / float(nm + 1) for i in range(nm)]
        for qi in range(N_QUESTIONS):
            q = "p%02d" % (qi * 3)
            for sfx in SUFFIXES:
                tid = "aime__aime25__%s__%s" % (q, sfx)
                P = 100 + 10 * qi + (offset if sfx == "no_think" else 0)
                if break_pair and qi == 3 and sfx == "no_think":
                    P -= offset               # ⇒ 这一题的 P 差变成 0
                ng = 400 + 40 * qi
                for m in ms:
                    den = P + max(1, int(ng * 0.5)) - 1
                    rs.append({"tid": tid, "arm": arm, "P": P, "n_gen": ng,
                               "pos_frac": 0.5, "inject_scope": "k",
                               "inject_n_sites": max(1, int(den * m)),
                               "p9_lo_meas": 0.0, "p9_hi_meas": 0.1 + m})
                rs.append({"tid": tid, "arm": arm, "P": P, "n_gen": ng,
                           "pos_frac": 0.5, "inject_scope": "single",
                           "inject_n_sites": None,
                           "p9_lo_meas": 0.0, "p9_hi_meas": 0.2})
        if break_key:
            rs[0] = dict(rs[0], n_gen=999)      # ⇒ 两臂键不再逐条相同
        return rs

    def distinct_band_count(recs):
        """⚖ 实算：四个扰动下分档表出现了**几种**不同形态（与 audit 用同一套函数）。"""
        ks_, ns_, dd_ = qsplit(recs)
        off_ = TEMPLATE_OFFSET
        variants = [
            [r["P"] for r in ks_],
            [r["P"] - (off_ if str(r.get("tid", "")).endswith("no_think") else 0) for r in ks_],
            [r["P"] - off_ for r in ks_],
            [r["P"] + off_ for r in ks_],
        ]
        seen = set()
        for Ps in variants:
            dens = [P + max(1, int(int(r["n_gen"]) * float(r["pos_frac"]))) - 1
                    for P, r in zip(Ps, ks_)]
            seen.add(tuple(bands_of(ns_, dd_, dens)[2]))
        return len(seen)

    def build_gold(arm="w", offset=TEMPLATE_OFFSET, sign=1.0):
        """⚖⚖ 从**真数据**冻结的剂量轴造夹具（见模块头 `GOLD_TRAJ`）。

        ⚖⚠⚠⚠ **为什么均匀剂量的合成夹具验不了「分档表稳不稳」**：
           第一版搜遍 `nm × jitter` 共 20 组网格，**全部 distinct=1**。
           ⚖ 原因：均匀剂量点下所有格子**同比例**平移 ⇒ **秩不变** ⇒ 分档必不变。
           ⚖ 真数据的 `P/t` 比值跨轨迹 **0.037 … 0.753**（见 C5）⇒ 平移**不均匀**
           ⇒ 分档表才真的会变。
           ⚗⇒ 判别式：**夹具必须落在要验的那个维度上**（同 244.50 的 ㊷），
             而「均匀」本身就是**退化**的一种。"""
        out = []
        for q, sfx, P0, ng, nss in GOLD_TRAJ:
            P = P0 + ((offset - TEMPLATE_OFFSET) if sfx == "no_think" else 0)
            tid = "aime__aime25__%s__%s" % (q, sfx)
            den = P + max(1, int(ng * 0.5)) - 1
            for ns in nss:
                out.append({"tid": tid, "arm": arm, "P": P, "n_gen": ng,
                            "pos_frac": 0.5, "inject_scope": "k",
                            "inject_n_sites": ns,
                            "p9_lo_meas": 0.0,
                            "p9_hi_meas": sign * (0.1 + ns / float(den))})
            out.append({"tid": tid, "arm": arm, "P": P, "n_gen": ng,
                        "pos_frac": 0.5, "inject_scope": "single",
                        "inject_n_sites": None,
                        "p9_lo_meas": 0.0, "p9_hi_meas": 0.2})
        return out

    # ⚖⚠⚠⚠ 黄金样本必须真的**分档表会变**，否则 C9b 是恒绿。
    #   实算不过就**判红**，⛔ 不许悄悄跳过 —— 跳过正是「恒绿」的成因。
    gold = build_gold()
    gold_distinct = distinct_band_count(gold)
    # ⚖⚠⚠ **反向剂量**夹具：干净夹具的 rho 本来就 > 0.6 ⇒ 「⛔ 扰动足以翻符号」
    #   那个分支**永远走不到** ⇒ 把打印选择器焊成 `True` 是**死变异**
    #   （台架 Q3 第一版就是这么活下来的）。⇒ 必须另造一个走得到它的夹具。
    gold_neg = build_gold(sign=-1.0)

    import tempfile

    def dump(rs):
        fd, q_ = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
        io.open(q_, "w", encoding="utf-8").write(
            "\n".join(json.dumps(r) for r in rs) + "\n")
        return q_

    f_w, f_r = dump(build("w")), dump(build("rand"))
    f_bad, f_badpair = dump(build("rand", break_key=True)), dump(build("rand", break_pair=True))

    L, rc = audit(f_w, f_r)
    chk("C1", rc == 0, "干净夹具审计 rc=%d" % rc)
    chk("C1b", any("✅ **完全相同**" in x for x in L), "C1 行必须印出「完全相同」")
    chk("C1c", any("不证明「那底座在已验的 60 条里」" in x for x in L),
        "C1 必须带上「这不证明已验」那句限定（⛔ 漏了就把推断当实测）")
    chk("C2", any("配对齐全 ✅" in x for x in L), "C2 行必须印出配对齐全")
    chk("C3", any("恒 +%d" % TEMPLATE_OFFSET in x for x in L) and "复现" in "\n".join(L),
        "C3 行必须印出恒 +%d 且标为复现账本" % TEMPLATE_OFFSET)
    chk("C4", any("rho 的区间" in x and "✅ 符号与量级都稳" in x for x in L),
        "C4 必须印出 rho 区间与稳健判词")
    # ⚖⚠⚠ C4b 必须是「印出的判词与**实算**一致」，⛔ 不是「出现『分档表』三个字」
    #   —— 只查关键词 ⇒ 一句「分档表完全一致」的谎话照样通过。
    #   ⚖ 判别式：**期望标签断言的是文字，就去改印那一行**（同 244.50 的 P11）。
    #   ⚖⚠ 而且 distinct 要**跨四个扰动**去数，⛔ 不能只数基准那一种。
    cnt = distinct_band_count(build("w"))
    want_stab = "完全一致" if cnt == 1 else ("变了 %d 种" % cnt)
    chk("C4b", any("分档表" in x and want_stab in x for x in L),
        "印出的分档表判词必须是「%s」（实算跨四扰动 distinct=%d）" % (want_stab, cnt))
    chk("C5", any("个 token 相当于分母的" in x for x in L), "C5 必须印出 token 占比")
    # ⚖⚠⚠ C5b：印出的两个百分比必须与**实算**逐位相符，⛔ 不能只查「印没印」
    import re as _re
    _line5 = next((x for x in L if "个 token 相当于分母的" in x), "")
    _mm = _re.search(r"\*\*([0-9.]+)% … ([0-9.]+)%\*\*", _line5)
    _recs5 = build("w")
    _ks5 = [r for r in _recs5
            if r.get("inject_scope") == "k" and r.get("inject_n_sites")]
    _d5 = [denom_of(r) for r in _ks5]
    _lo5 = min(TEMPLATE_OFFSET / d * 100.0 for d in _d5)
    _hi5 = max(TEMPLATE_OFFSET / d * 100.0 for d in _d5)
    chk("C5b", bool(_mm) and abs(float(_mm.group(1)) - _lo5) < 0.01
        and abs(float(_mm.group(2)) - _hi5) < 0.01,
        "印出的 %s…%s 必须等于实算的 %.2f%%…%.2f%%"
        % (_mm.group(1) if _mm else "?", _mm.group(2) if _mm else "?", _lo5, _hi5))

    # ---- C8：C3 必须能分辨「恒定但不是账本记的那个值」-------------------
    #   ⛔ 不许「不管什么数都印『复现』」—— 那是 244.5.2「恒真被当成互证」的同族。
    f7 = dump(build("rand", offset=TEMPLATE_OFFSET + 3))
    L8, _rc8 = audit(f7, f7)
    chk("C8", any("但**不是**账本记的 +%d" % TEMPLATE_OFFSET in x for x in L8)
        and not any("复现" in x for x in L8),
        "偏移改成 +%d 时必须说「不是账本记的 +%d」且⛔ 不许说「复现」"
        % (TEMPLATE_OFFSET + 3, TEMPLATE_OFFSET))

    # ---- 两条判据必须能红（⛔ 不能只有一条方向）-------------------------
    L2, rc2 = audit(f_w, f_bad)
    chk("C6", rc2 != 0 and any("⛔ 有" in x and "不是**同一批格子" in x for x in L2),
        "两臂键不同 ⇒ C1 必须转红（rc=%d）" % rc2)
    # ⚠⚠⚠ 畸变必须放在 **C3 真正读的那一侧**（`audit(wpath, rpath)` 里 C3 读的是
    #   `W`，⛔ 不是 `R`）。第一版把畸变只放在 rand 侧 ⇒ C3 照样绿 ⇒ 用例白写，
    #   而 rc!=0 是被 C1 顶上的 ⇒ **rc 变红不等于我要验的那条红了**。
    L3, rc3 = audit(f_badpair, f_badpair)
    chk("C7", rc3 != 0 and any("不恒定" in x for x in L3),
        "逐题 P 差不恒定 ⇒ C3 必须转红（rc=%d）" % rc3)

    # ---- C9：在一个**分档表真的会变**的夹具上，那条判词必须印「变了 N 种」----
    #   ⚠⚠⚠ 搜不到 ⇒ **判红**（不是跳过）：搜不到说明**这个维度根本没被覆盖**，
    #   那正是「恒绿」的成因。
    chk("C9a", gold_distinct >= 2,
        "黄金样本（真剂量轴 %d 格）实算 distinct=%d ⇒ 必须 ≥2，否则 C9b 恒绿"
        % (sum(len(t[4]) for t in GOLD_TRAJ), gold_distinct))
    tmp = [f_w, f_r, f_bad, f_badpair, f7]
    if gold_distinct >= 2:
        fu = dump(gold)
        tmp.append(fu)
        Lu, _rcu = audit(fu, fu)
        chk("C9b", any("分档表变了 %d 种" % gold_distinct in x for x in Lu),
            "印出的判词必须是「变了 %d 种」" % gold_distinct)
    fn = dump(gold_neg)
    tmp.append(fn)
    Ln2, _rcn = audit(fn, fn)
    chk("C4c", any("⛔ 扰动足以翻符号" in x for x in Ln2),
        "反向剂量夹具上必须印「⛔ 扰动足以翻符号」（这一条才走得到 C4 的另一支）")

    for f in tmp:
        try:
            os.unlink(f)
        except OSError:
            pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="剂量轴分母的前提审计（零 GPU、不连远端）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    for p in DEFAULT_FILES.values():
        if not os.path.exists(p):
            print("⛔ 文件不存在：%s" % p)
            return 1
    L, rc = audit(DEFAULT_FILES["w"], DEFAULT_FILES["rand"])
    print("\n".join(L))
    return rc


if __name__ == "__main__":
    sys.exit(main())
