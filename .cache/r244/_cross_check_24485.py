#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24485.py —— 244.85「类级结论的留一稳健性」的**第二条独立实现**。

⚖⚖⚖⚖⚖ **为什么要有第二条实现**
   244.83 的教训：同一个口径，两条实现路线，**当场抓到过一个真 bug**
   （rand 向量的缩放因子必须是 float32 口径）⇒ ⇒ 「写对了一遍」不算数
   ⇒ ⇒ 本文件走**纯 Python 路线**（点积 / 范数 / 均值 / 方差 / 秩全部自己实现），
   与被检实现的 **numpy 路线**互证。
   ⚖⚖⚖ 244.85 的量更大：**16 个子集**（n = 6/5/4/3/1）全部独立重算。

⚖⚖⚖⚖⚖ **分界（哪些必须同源、哪些必须独立）**
   · **随机抽样源**（`default_rng(s).standard_normal(d)`）：⚠ **必须同源**
     ⇒ ⇒ 否则两条路线抽的不是同一批「零分布」，根本无从互证。
   · **算术路径**（点积、范数、均值、样本方差、秩、比较）：⚠ **必须独立**
     ⇒ ⇒ 本文件用 `sum(map(mul, ...))` 与 `math.fsum` 等**另一套**实现。
   · **判决映射**（§3.1）：⚠ **必须独立** ⇒ ⇒ 本文件用**另一套写法**（显式 if/elif 链）
     ⇒ ⇒ 被检实现用**规则表** ⇒ ⇒ 两边不许共享代码。

⚖⚖⚖⚖⚖ **纪律**
   · ⛔ 本文件**不改**被检实现、⛔ 不改预登记、⛔ 不改 bpath
   · ⛔ 期望值**从账本读**（⛔ 不写死）
   · ⚖ 互证只输出 `CROSS|key=value` 与一行小结；比对方由本文件自己做（读 de.out）

⚖⚖⚖⚖⚖ **本文件**必须能**自己判红** ⇒ ⇒ 下面每一条比对面都写死了判据
"""

import json
import math
import os
import re
import struct
import sys
from operator import mul

import numpy as np

LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")
DE_OUT = os.environ.get("R244_DE_OUT", "")

MEMBERS = ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_p2a", "w_old"]
DOSE_W = "w_p2a"
D = 2048
K = 2000
REF_SINGLE_LO = 1
REF_CLASS_LO = 100001
RAND_SEED = 0
Z_THRESHOLD = 2.0
CROSS_REL_TOL = 1e-12


def ulp_diff(a, b):
    """⚖ 两个 double 之间的 **ULP 距离**（⛔ 有限值）。

    ⚖⚖⚖ **为什么本文件要单独算它**：
    「相对差 ≤ 1e-12」这条容差**看不见 1 ULP 的差别**（1 ULP ≈ 1.3e-16 相对）
    ⇒ ⇒ 「差 0」与「差 3 个 ULP」在容差口径下**长得一模一样**
    ⇒ ⇒ 跨路线的差值**必须单独存、单独印**，⛔ 不能只说「在容差内」。
    """
    def key(x):
        u = struct.unpack("<Q", struct.pack("<d", float(x)))[0]
        return (~u + 1) & 0xFFFFFFFFFFFFFFFF if (u >> 63) else (u | 0x8000000000000000)
    return abs(key(a) - key(b))

# ⚖ 子集族（**独立再写一遍**：⛔ 不 import 被检实现 ⇒ ⇒ 真的是第二条实现）
FAMILY = {
    "FULL": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_p2a", "w_old"],
    "LOO-m0": ["w_L19_m1", "w_real", "w_t1", "w_p2a", "w_old"],
    "LOO-m1": ["w_L19_m0", "w_real", "w_t1", "w_p2a", "w_old"],
    "LOO-real": ["w_L19_m0", "w_L19_m1", "w_t1", "w_p2a", "w_old"],
    "LOO-t1": ["w_L19_m0", "w_L19_m1", "w_real", "w_p2a", "w_old"],
    "LOO-p2a": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_old"],
    "LOO-old": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_p2a"],
    "STRAT-A": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1"],
    "CLU-A": ["w_L19_m1", "w_t1", "w_p2a"],
    "CLU-B": ["w_L19_m0", "w_real", "w_old"],
    "SINGLE-m0": ["w_L19_m0"],
    "SINGLE-m1": ["w_L19_m1"],
    "SINGLE-real": ["w_real"],
    "SINGLE-t1": ["w_t1"],
    "SINGLE-p2a": ["w_p2a"],
    "SINGLE-old": ["w_old"],
}
DECISION = ["FULL", "LOO-m0", "LOO-m1", "LOO-real", "LOO-t1", "LOO-p2a", "LOO-old"]
DOSE_KEY = "LOO-p2a"


def die(msg):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(3)


def read_text(p):
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


# =============================================================================
# ⚖ 纯 Python 算术路线（⛔ 不用 numpy 的 dot / norm / mean / var）
# =============================================================================
def pdot(a, b):
    """⚖ 纯 Python 点积（`sum(map(mul, ...))`）⇒ 与 numpy 的 BLAS 路径**不同实现**。"""
    return sum(map(mul, a, b))


def pnorm(a):
    """⚖ 纯 Python 范数（`math.sqrt(sum(x*x))`）⇒ 与 numpy 的 `linalg.norm` **不同实现**。"""
    return math.sqrt(sum(x * x for x in a))


def pmean(v):
    return math.fsum(v) / len(v)


def pvar_sample(v):
    """⚖ 样本方差（ddof=1）⇒ 与 244.83/244.84 的写法同口径。"""
    m = pmean(v)
    return math.fsum((x - m) ** 2 for x in v) / (len(v) - 1)


def prand_raw(seed, shape):
    """⚖ **随机抽样源与被检实现同源**（numpy 的 PCG64）—— ⚠ 这一处**必须**同源。"""
    g = np.random.default_rng(int(seed))
    return g.standard_normal(shape).astype(np.float64)


def unit_py(v):
    n = pnorm(v)
    return [x / n for x in v]


def cos_py(u, v):
    """⚖ 244.83/244.84 的余弦口径：`dot(u, v) / ‖u‖`（**v 由调用方保证已归一化**）。"""
    return pdot(u, v) / pnorm(u)


def rand_direction_py(w0, seed):
    """⚖ 探针规则（`r241_probe.py` 的 rand 那一支）——⚠ **缩放因子必须是 float32 口径**。"""
    g = np.random.default_rng(int(seed))
    w = g.standard_normal(w0.shape).astype(np.float64)
    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0))
    return [float(x) for x in w]


def subset_stats_py(unit_vecs, r0, refs):
    """⚖ **纯 Python** 的子集统计量（与被检实现同口径、异实现）。"""
    n = len(unit_vecs)
    m = [0.0] * len(unit_vecs[0])
    for v in unit_vecs:
        for i in range(len(m)):
            m[i] += v[i]
    m = [x / n for x in m]
    mnorm = pnorm(m)
    mc = [x / mnorm for x in m]

    def one(r):
        t = sum(cos_py(v, r) for v in unit_vecs) / n
        u = abs(cos_py(mc, r))
        return t, u

    T_obs, _u = one(r0)
    Ts, Us = [], []
    for rr in refs:
        t, u = one(rr)
        Ts.append(t)
        Us.append(u)
    mT = pmean(Ts)
    sT = pvar_sample(Ts) ** 0.5
    mU = pmean(Us)
    sU = pvar_sample(Us) ** 0.5
    z_T = (T_obs - mT) / sT
    rank_T = sum(1 for x in Ts if x < T_obs) / float(len(Ts))
    theo_T = mnorm / math.sqrt(float(len(unit_vecs[0])))
    sd_rel_T = abs(sT - theo_T) / theo_T
    zs = [(x - mT) / sT for x in Ts]
    fpr = sum(1 for z in zs if z >= Z_THRESHOLD) / float(len(Ts))
    return {"n": n, "T_obs": T_obs, "z_T": z_T, "rank_T": rank_T,
            "sd": sT, "theo": theo_T, "sdrel": sd_rel_T, "fpr": fpr}


def verdict_py(shapes, hard_ok, disc_ok, full_expected):
    """⚖ **独立写法**的判决映射（被检实现用**规则表**）⇒ ⇒ 两边不许共享代码。"""
    if not hard_ok:
        return "FAIL"
    if not disc_ok:
        return "F-E"
    if shapes.get("FULL") != full_expected:
        return "FAIL"
    if shapes.get(DOSE_KEY) == "E-A":
        return "F-B"
    for k in DECISION:
        if k in ("FULL", DOSE_KEY):
            continue
        if shapes.get(k) == "E-A":
            return "F-C"
    return "F-A"


# =============================================================================
def ledger_expectations(ledger_path):
    text = read_text(ledger_path)

    def section(num):
        m = re.search(r"^## 修订 %s\b" % re.escape(num), text, re.M)
        if not m:
            return None
        m2 = re.search(r"^## 修订 ", text[m.end():], re.M)
        return text[m.start():(m.end() + m2.start()) if m2 else len(text)]

    sec = section("244.84")
    if sec is None:
        die("账本里没有「## 修订 244.84」段 ⇒ ⇒ 拒绝兜底")

    def line_with(kw):
        for ln in sec.splitlines():
            if kw in ln:
                return ln
        die("账本 244.84 段里找不到含「%s」的行 ⇒ ⇒ 拒绝兜底" % kw)

    def one(pat, what, s):
        m = re.search(pat, s)
        if not m:
            die("账本 244.84 段里读不到「%s」⇒ ⇒ 拒绝兜底" % what)
        return m.group(1)

    exp = {}
    exp["T"] = float(one(r"\*\*([-+0-9.eE]+)\*\*", "类级 T", line_with("**类级主统计量**")))
    exp["z"] = float(one(r"\*\*([-+0-9.eE]+)\*\*", "类级 z_T",
                          line_with("**z_T**（对参考种子分布）")))
    ln = line_with("经验秩 / 参考 sd")
    mm = re.search(r"\|\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*\|", ln)
    if not mm:
        die("账本 244.84 段里读不到「秩 / sd / 理论 sd」⇒ ⇒ 拒绝兜底")
    exp["rank"] = float(mm.group(1))
    exp["sd"] = float(mm.group(2))
    exp["theo"] = float(mm.group(3))
    exp["fpr"] = float(one(r"\*\*([-+0-9.eE]+)\*\*", "FPR",
                            line_with("经验假阳性率")))
    exp["verdict"] = one(r"判决形态\s*(E-[ABC])", "判决形态", sec)
    return exp


def parse_de_out(path):
    """⚖ 解析被检实现的真数据输出（`SUBSET|...` 行 + `VERDICT=` + 判据状态）。"""
    if not path or not os.path.isfile(path):
        die("找不到被检实现的真数据输出：%s" % path)
    text = read_text(path)
    subs = {}
    for m in re.finditer(
            r"^SUBSET\|([^|]+)\|n=(\d+)\|T=([-+0-9.eE]+)\|z=([-+0-9.eE]+)\|"
            r"rank=([-+0-9.eE]+)\|sd=([-+0-9.eE]+)\|theo=([-+0-9.eE]+)\|"
            r"sdrel=([-+0-9.eE]+)\|fpr=([-+0-9.eE]+)\|shape=(\S+)$", text, re.M):
        subs[m.group(1)] = {
            "n": int(m.group(2)), "T_obs": float(m.group(3)), "z_T": float(m.group(4)),
            "rank_T": float(m.group(5)), "sd": float(m.group(6)), "theo": float(m.group(7)),
            "sdrel": float(m.group(8)), "fpr": float(m.group(9)), "shape": m.group(10),
        }
    mv = re.search(r"^VERDICT=(\S+)$", text, re.M)
    verdict = mv.group(1) if mv else None
    crit = {}
    for m in re.finditer(r"^\[(PASS|FAIL)\]\s+(\S+)", text, re.M):
        crit[m.group(2)] = (m.group(1) == "PASS")
    return subs, verdict, crit


def main():
    if not os.path.isdir(BPATH):
        die("bpath 不存在：%s" % BPATH)
    exp = ledger_expectations(LEDGER)

    # ---- 向量（numpy 读盘 ⇒ 字节一致；算术走纯 Python）----
    vecs = {}
    for nm in MEMBERS:
        arr = np.load(os.path.join(BPATH, nm + ".npy"))
        if arr.shape != (D,):
            die("%s 的 shape 不是 (%d,)" % (nm, D))
        vecs[nm] = unit_py([float(x) for x in arr])

    # ---- rand 臂方向（探针规则，float32 缩放口径）----
    w0 = np.load(os.path.join(BPATH, DOSE_W + ".npy"))
    r0 = rand_direction_py(w0, RAND_SEED)

    # ---- 参考方向（**随机源同源**、归一化走纯 Python）----
    refs = []
    for s in range(REF_CLASS_LO, REF_CLASS_LO + K):
        rr = prand_raw(s, (D,))
        n = pnorm(rr)
        refs.append([float(x) / n for x in rr])
    sys.stderr.write("互证：参考方向 %d 个已生成\n" % len(refs))

    # ---- 逐子集重算 ----
    mine = {}
    shapes = {}
    for name in sorted(FAMILY):
        uvs = [vecs[nm] for nm in FAMILY[name]]
        st = subset_stats_py(uvs, r0, refs)
        st["shape"] = "E-B" if st["z_T"] >= Z_THRESHOLD else "E-A"
        mine[name] = st
        shapes[name] = st["shape"]
        print("XSUBSET|%s|n=%d|T=%+.17g|z=%+.17g|rank=%.17g|sd=%.17g|theo=%.17g|"
              "sdrel=%.17g|fpr=%.17g|shape=%s"
              % (name, st["n"], st["T_obs"], st["z_T"], st["rank_T"], st["sd"],
                 st["theo"], st["sdrel"], st["fpr"], shapes[name]), flush=True)

    # ---- 与被检实现逐项比 ----
    theirs, their_verdict, crit = parse_de_out(DE_OUT)
    ok_count = 0
    bad = []

    def rel(a, b):
        return abs(a - b) / abs(b) if b != 0 else float("inf")

    if sorted(theirs.keys()) != sorted(mine.keys()):
        die("子集名单不一致 ⇒ ⇒ 口径对不上 ⇒ ⇒ 中止（被检 %s ／ 本文件 %s）"
            % (sorted(theirs.keys()), sorted(mine.keys())))

    for name in sorted(mine):
        for key in ("T_obs", "z_T", "rank_T", "sd", "theo", "sdrel", "fpr"):
            d = rel(mine[name][key], theirs[name][key])
            if d <= CROSS_REL_TOL:
                ok_count += 1
            else:
                bad.append("%s.%s 相对差 %.3g > %.0g（纯 Python %.17g ／ numpy %.17g）"
                           % (name, key, d, CROSS_REL_TOL, mine[name][key], theirs[name][key]))
        if mine[name]["shape"] != theirs[name]["shape"]:
            bad.append("%s.shape 不一致（%s ／ %s）"
                       % (name, mine[name]["shape"], theirs[name]["shape"]))
        else:
            ok_count += 1

    # ---- 与账本对账（FULL 的类级量）----
    full = mine["FULL"]
    for key, want in (("T_obs", exp["T"]), ("z_T", exp["z"]), ("rank_T", exp["rank"]),
                      ("sd", exp["sd"]), ("theo", exp["theo"]), ("fpr", exp["fpr"])):
        d = rel(full[key], want)
        if d <= CROSS_REL_TOL:
            ok_count += 1
        else:
            bad.append("FULL.%s 与账本 244.84 的登记相对差 %.3g > %.0g（实测 %.17g ／ 账本 %.17g）"
                       % (key, d, CROSS_REL_TOL, full[key], want))

    # ---- 判决形态（**独立写法**重算）----
    h9 = crit.get("H9-DISC", True)
    hard_ok = all(v for k, v in crit.items() if k != "H9-DISC")
    my_verdict = verdict_py(shapes, hard_ok, h9, exp["verdict"])
    if my_verdict == their_verdict:
        ok_count += 1
    else:
        bad.append("判决形态不一致（纯 Python 独立映射 %s ／ 被检 %s）" % (my_verdict, their_verdict))

    # ---- 判决形态的**分支可达性**（本文件独立确认五个形态都可能被产出）----
    reach = []
    base = dict((k, "E-B") for k in FAMILY)
    reach.append(verdict_py(base, True, True, "E-B"))
    c = dict(base)
    c[DOSE_KEY] = "E-A"
    reach.append(verdict_py(c, True, True, "E-B"))
    c = dict(base)
    c["LOO-t1"] = "E-A"
    reach.append(verdict_py(c, True, True, "E-B"))
    reach.append(verdict_py(base, True, False, "E-B"))
    reach.append(verdict_py(base, False, True, "E-B"))
    if sorted(set(reach)) == sorted(["F-A", "F-B", "F-C", "F-E", "FAIL"]):
        ok_count += 1
    else:
        bad.append("判决形态分支可达性不足：%s" % sorted(set(reach)))

    # ---- 跨路线差值（**单独存**：差值本身必须落账，⛔ 不能只说「在容差内」）----
    # ⚖⚖⚖ **为什么必须单独存**：上面的逐项比只回答「在不在 1e-12 容差内」
    #   ⇒ ⇒ 「差 0」与「差 3 个 ULP」在容差口径下**长得一模一样**
    #   ⇒ ⇒ 「本轮与账本 244.84 逐位相同」这句话**能不能说**，取决于差值本身
    #   ⇒ ⇒ 所以这里把 **ULP 距离**逐项算出来、单独印、单独落账。
    def _rel(a, b):
        return abs(a - b) / abs(b) if b != 0 else float("inf")

    max_rel = -1.0
    max_rel_where = ""
    max_ulp = -1
    max_ulp_where = ""
    n_ident = 0
    n_total = 0
    for name in sorted(mine):
        for key in ("T_obs", "z_T", "rank_T", "sd", "theo", "sdrel", "fpr"):
            a, b = mine[name][key], theirs[name][key]
            n_total += 1
            if a == b:
                n_ident += 1
            d = _rel(a, b)
            if d > max_rel:
                max_rel, max_rel_where = d, "%s.%s" % (name, key)
            u = ulp_diff(a, b)
            if u > max_ulp:
                max_ulp, max_ulp_where = u, "%s.%s" % (name, key)
    print("CROSSROUTE|SUMMARY|max_rel=%.6g|at=%s|max_ulp=%d|ulp_at=%s|identical=%d/%d|bound=%.0g"
          % (max_rel, max_rel_where, max_ulp, max_ulp_where, n_ident, n_total, CROSS_REL_TOL))

    # ---- FULL 的两个头条量：纯 Python 路线 vs numpy 路线 ----
    for key, lbl in (("T_obs", "类级 T"), ("z_T", "类级 z_T")):
        a, b = mine["FULL"][key], theirs["FULL"][key]
        print("CROSSROUTE|FULL|%s|py=%.17g|np=%.17g|rel=%.6g|ulp=%d|identical=%s"
              % (lbl, a, b, _rel(a, b), ulp_diff(a, b), "yes" if a == b else "no"))

    # ---- FULL 的 6 项：numpy 路线 vs **账本 244.84 主表**（同一条路线 ⇒ 应当**逐位**）----
    for key, want, lbl in (("T_obs", exp["T"], "类级 T"), ("z_T", exp["z"], "类级 z_T"),
                           ("rank_T", exp["rank"], "类级秩"), ("sd", exp["sd"], "类级参考 sd"),
                           ("theo", exp["theo"], "类级理论 sd"), ("fpr", exp["fpr"], "类级 FPR")):
        a = theirs["FULL"][key]
        print("CROSSROUTE|LEDGER|%s|np=%.17g|ledger=%.17g|rel=%.6g|ulp=%d|identical=%s"
              % (lbl, a, want, _rel(a, want), ulp_diff(a, want), "yes" if a == want else "no"))

    for b in bad:
        print("CROSS|MISMATCH|%s" % b)
    print("CROSS|items_ok=%d" % ok_count)
    print("CROSS|mismatches=%d" % len(bad))
    print("CROSS|verdict=%s" % my_verdict)
    print("CROSS|subsets=%d" % len(mine))
    if bad:
        print("CROSS_RC=1")
        return 1
    print("CROSS_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
