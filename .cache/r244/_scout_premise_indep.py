#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""⚖⚖⚖ **244.82 的前瞻探查：前提独立性**（⛔ **这是探查，不是判决**；⛔ 不进执行集 —— 文件名以 `_` 开头）

⚖⚖⚖ **为什么做这件事**：
   244.81 判决面板上的每一个 p 与每一个区间，都建立在「**56 条轨迹彼此独立**」这个
   **没被验过**的前提上（面板前提 P1）。而真实结构是
   **56 条轨迹 = 28 块 × 2**（块 = 同一道题的 `think` + `no_think`），
   且块内每条轨迹还有 **3 个 `pos_frac` 复制格**。
   ⇒ ⇒ 若块内两条轨迹相关，**逐轨迹**的置换零分布**偏窄** ⇒ ⇒ p 会**偏小**。

⚖ **本探查问的问题**：
   「把零分布改成『**块是独立单位**」（块内整体交换两臂标签），判决还站得住吗？」

⚖⚖⚖ **纪律**：
   ① **自检**：本脚本独立解析原始日志、独立算格集合与合池 ⇒ ⇒ 必须**逐条复现**面板的
      46/56、29/56、21/28、6/28 ⇒ ⇒ 否则**硬停**（复现不上 ⇒ 说明我的解析错了，
      ⛔ 不许拿一个「差不多」的数继续算）。
   ② **零 GPU、只读**：只读拆分产物，⛔ 不碰 bpath、⛔ 不写任何地方。
   ③ **本探查的结论不进账本**：它是 244.82 的**先导** ⇒ ⇒ 正式那一轮必须另有
      **第二条独立实现** ＋ **变异台**（⛔ 不能只有这一份）。
"""

import collections
import io
import json
import math
import os
import random
import re
import sys

WORK = os.environ.get("SCOUT_WORK", "/dev/shm/_pooled_24481/work")
PANEL = os.environ.get("SCOUT_PANEL", "/dev/shm/_pooled_24481/verdict_panel.txt")
RHO = 0.250
TOL = 0.0050
SCOPE = "k"
N_PERM = 20000
SEED = 20261020
BOOT = 20000
BOOT_SEED = 20261021

# ⚖ 面板上的数（**用来自检**，⛔ 不是用来算的）
EXPECT = {
    "w_traj": (46, 56), "rand_traj": (29, 56),
    "w_blk": (21, 28), "rand_blk": (6, 28),
}


def die(msg):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(3)


# ---------------------------------------------------------------- 解析


def parse_logs(arm):
    """⚖ 自己解析拆分日志：每格一行 JSON（紧跟在 `RESULT r204_cell` 之后）。"""
    recs = []
    for pf in ("025", "050", "075"):
        p = os.path.join(WORK, arm, "pf%s.log" % pf)
        if not os.path.isfile(p):
            die("缺拆分日志：%s" % p)
        with io.open(p, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln.startswith("{"):
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if "tid" not in r:
                    continue
                recs.append(r)
    return recs


def denom_of(r):
    """⚖ 照探针原式：`inj = P + max(1, int(n_gen*pos_frac)) − 1`。"""
    P = r.get("P")
    ng = r.get("n_gen")
    pf = r.get("pos_frac")
    if P is None or ng is None or pf is None:
        return None
    t = max(1, int(int(ng) * float(pf)))
    return int(P) + t - 1


def cell_set(recs):
    """⚖ V3 的四条：`scope==k` ∧ 读数在 ∧ `n_sites` 为真 ∧ 密度 = ρ*±tol。"""
    kept, dropped = [], []
    for r in recs:
        lo, hi = r.get("p9_lo_meas"), r.get("p9_hi_meas")
        if lo is None or hi is None:
            dropped.append((r, "读数缺失"))
            continue
        if (r.get("inject_scope") or "") != SCOPE:
            dropped.append((r, "scope≠k"))
            continue
        if not r.get("inject_n_sites"):
            dropped.append((r, "n_sites 为假"))
            continue
        inj = denom_of(r)
        if inj is None or inj <= 0:
            dropped.append((r, "分母算不出"))
            continue
        fr = float(r["inject_n_sites"]) / float(inj)
        if abs(fr - RHO) > TOL:
            dropped.append((r, "密度 %.6f ∉ ρ*±%.4f" % (fr, TOL)))
            continue
        r = dict(r)
        r["_frac"] = fr
        kept.append(r)
    return kept, dropped


def pool(kept):
    """⚖ 逐轨迹合池：3 个 `pos_frac` 格的**严格多数**（`nT·2 > m`；平票 False；零格进分母）。"""
    by_tid = collections.OrderedDict()
    for r in kept:
        by_tid.setdefault(r["tid"], []).append(r)
    out = {}
    for tid, cs in by_tid.items():
        vals = []
        for r in cs:
            d = float(r["p9_hi_meas"]) - float(r["p9_lo_meas"])
            vals.append(1 if d > 0 else (-1 if d < 0 else 0))
        m = len(vals)
        nT = sum(1 for v in vals if v > 0)
        out[tid] = {"vals": vals, "m": m, "nT": nT,
                    "verdict": (nT * 2 > m), "d_sum": sum(vals)}
    return out


def block_key(tid):
    """⚖ 块键 = 去掉末尾的 `__think` / `__no_think`。"""
    for suf in ("__no_think", "__think"):
        if tid.endswith(suf):
            return tid[: -len(suf)]
    return tid


def wilson(x, n):
    if not n:
        return (float("nan"), float("nan"))
    z = 1.959963984540054
    p = x / float(n)
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / d
    return (100.0 * (c - h), 100.0 * (c + h))


def newcombe(x1, n1, x2, n2):
    """⚖ 两比例之差的 Newcombe95（方法 10）。"""
    l1, u1 = wilson(x1, n1)
    l2, u2 = wilson(x2, n2)
    p1, p2 = x1 / float(n1), x2 / float(n2)
    d = 100.0 * (p1 - p2)
    lo = d - math.sqrt((p1 * 100 - l1) ** 2 + (u2 - p2 * 100) ** 2)
    hi = d + math.sqrt((u1 - p1 * 100) ** 2 + (p2 * 100 - l2) ** 2)
    return (lo, hi)


def fisher_exact(a, b, c, d):
    """⚖ 两侧 Fisher 精确（**「不比观测更可能」的经典定义**，⛔ 自己实现，不 import）。

    ⚖ 与 `arm_verdict.fisher_exact_two_sided` 同一约定：
       固定边际 ⇒ `prob(x) = C(r1,x)·C(r2,c1−x)/C(n,c1)` ⇒ 把所有
       `prob(x) ≤ prob(obs)` 的表加起来（⛔ **不是**「双尾×1」的凑法）。
    """
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    if n == 0:
        return float("nan")
    def prob(x):
        if not (0 <= x <= r1) or not (0 <= c1 - x <= r2):
            return 0.0
        return (math.comb(r1, x) * math.comb(r2, c1 - x)) / float(math.comb(n, c1))
    p_obs = prob(a)
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1)
                         if prob(x) <= p_obs * (1 + 1e-12)))


def mcnemar_exact(b, c):
    """⚖⚖ **精确 McNemar（二项）**：不一致的 `b+c` 条里，`b` 条偏向一臂。

    ⚖ 双侧 p = `P(X ≤ min(b,c)) + P(X ≥ max(b,c))`（X ~ Binom(b+c, 0.5)）
      —— ⛔ **不是**「2×单尾」的凑法（那在 n 小的时候会高估证据）。
    """
    n = b + c
    if n == 0:
        return float("nan")
    def pmf(k):
        return math.comb(n, k) / float(2 ** n)
    lo = min(b, c)
    hi = max(b, c)
    p = sum(pmf(k) for k in range(0, lo + 1)) + sum(pmf(k) for k in range(hi, n + 1))
    return min(1.0, p)


# ---------------------------------------------------------------- 统计


def paired_perm_traj(diffs, n_perm=N_PERM, seed=SEED):
    """⚖ **逐轨迹**置换（= 面板上那个：假定 56 条轨迹彼此独立）。"""
    obs = sum(diffs)
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_perm):
        t = 0
        for d in diffs:
            t += d if rng.random() < 0.5 else -d
        if abs(t) >= abs(obs):
            ge += 1
    return (ge + 1) / (n_perm + 1.0), obs, ge, n_perm


def paired_perm_block(block_diffs, n_perm=N_PERM, seed=SEED):
    """⚖⚖⚖ **块级**置换（**块是独立单位** ⇒ 块内两臂整体交换）。

    ⇒ 这就是「前提独立性**不成立**时**应该**用的零分布」。
    """
    obs = sum(block_diffs)
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_perm):
        t = 0
        for d in block_diffs:
            t += d if rng.random() < 0.5 else -d
        if abs(t) >= abs(obs):
            ge += 1
    return (ge + 1) / (n_perm + 1.0), obs, ge, n_perm


def cluster_boot_diff(pw, pr, nboot=BOOT, seed=BOOT_SEED):
    """⚖ **按块重采样**的 bootstrap ⇒ 差 pp 的「聚类稳健」区间。

    `pw` / `pr`：按块对齐的两臂「块是否正」序列（长度 = 块数）。
    """
    n = len(pw)
    rng = random.Random(seed)
    vals = []
    for _ in range(nboot):
        idx = [rng.randrange(n) for _ in range(n)]
        a = sum(pw[i] for i in idx)
        b = sum(pr[i] for i in idx)
        vals.append(100.0 * (a / float(n) - b / float(n)))
    vals.sort()
    lo = vals[int(0.025 * (len(vals) - 1))]
    hi = vals[int(0.975 * (len(vals) - 1))]
    return (lo, hi)


# ---------------------------------------------------------------- 主流程


def main():
    arms = {}
    for arm in ("w", "rand"):
        recs = parse_logs(arm)
        kept, dropped = cell_set(recs)
        pooled = pool(kept)
        arms[arm] = {"pooled": pooled, "kept": len(kept), "dropped": dropped}
        print("臂 %s：解析 %d 格 ｜ 进格集合 %d ｜ 剔出 %d ｜ 轨迹 %d"
              % (arm, len(recs), len(kept), len(dropped), len(pooled)))
        for r, why in dropped:
            print("    剔出：%s（%s）" % (r.get("tid"), why))

    # ---- ① 自检（**复现不上 ⇒ 硬停**）
    bad = []
    for arm in ("w", "rand"):
        p = arms[arm]["pooled"]
        pos = sum(1 for v in p.values() if v["verdict"])
        key = "%s_traj" % arm
        if (pos, len(p)) != EXPECT[key]:
            bad.append("%s 轨迹级 我=%d/%d 面板=%s" % (arm, pos, len(p), EXPECT[key]))
    # 块级
    blocks = collections.OrderedDict()
    for arm in ("w", "rand"):
        bl = collections.OrderedDict()
        for tid, v in arms[arm]["pooled"].items():
            bl.setdefault(block_key(tid), {})[tid] = v["verdict"]
        blocks[arm] = bl
    for arm in ("w", "rand"):
        bl = blocks[arm]
        pos = sum(1 for q, d in bl.items() if len(d) == 2 and all(d.values()))
        key = "%s_blk" % arm
        if (pos, len(bl)) != EXPECT[key]:
            bad.append("%s 块级 我=%d/%d 面板=%s" % (arm, pos, len(bl), EXPECT[key]))
    # ⚖⚖ **Fisher 也自检**（⛔ 自己实现的统计量必须与面板逐位相同）
    f_traj = fisher_exact(EXPECT["w_traj"][0], EXPECT["w_traj"][1] - EXPECT["w_traj"][0],
                          EXPECT["rand_traj"][0], EXPECT["rand_traj"][1] - EXPECT["rand_traj"][0])
    f_blk = fisher_exact(EXPECT["w_blk"][0], EXPECT["w_blk"][1] - EXPECT["w_blk"][0],
                         EXPECT["rand_blk"][0], EXPECT["rand_blk"][1] - EXPECT["rand_blk"][0])
    if abs(f_traj - 0.001152) > 5e-7:
        bad.append("轨迹级 Fisher 我=%.6f 面板=0.001152" % f_traj)
    if abs(f_blk - 0.000131) > 5e-7:
        bad.append("块级 Fisher 我=%.6f 面板=0.000131" % f_blk)
    if bad:
        for b in bad:
            print("⛔ 自检不符：%s" % b)
        die("自检不符 ⇒ 我的解析不可信 ⇒ 硬停（⛔ 不许拿「差不多」的数继续算）")
    print("✅ 自检通过：轨迹级 w 46/56、rand 29/56 ｜ 块级 w 21/28、rand 6/28"
          " ｜ 轨迹级 Fisher %.6f、块级 Fisher %.6f（与面板逐位相同）" % (f_traj, f_blk))

    # ---- ② 块内相关（前提独立性第一层）
    print("")
    print("==== ② 块内相关（同一块的两条轨迹）====")
    agree = tot = 0
    discord_w = discord_r = 0
    for q in blocks["w"]:
        d = blocks["w"][q]
        if len(d) != 2:
            continue
        dr = blocks["rand"].get(q, {})
        if len(dr) != 2:
            continue
        vs = list(d.values())
        vr = list(dr.values())
        tot += 1
        agree += 1 if vs[0] == vs[1] else 0
        if vs[0] != vs[1]:
            discord_w += 1
        if vr[0] != vr[1]:
            discord_r += 1
    print("· 块数 %d ｜ w 臂块内两条**判决一致** %d（%.4f）｜ rand 臂块内不一致 %d ｜ w 臂块内不一致 %d"
          % (tot, agree, agree / float(tot), discord_r, discord_w))
    # φ 系数（块内两条的符号相关）
    a = b = c2 = d2 = 0
    for q in blocks["w"]:
        dw = blocks["w"][q]
        dr = blocks["rand"].get(q, {})
        if len(dw) != 2 or len(dr) != 2:
            continue
        for tid in dw:
            sw = dw[tid]
            sr = dr[tid]
            if sw and sr:
                a += 1
            elif sw and not sr:
                b += 1
            elif (not sw) and sr:
                c2 += 1
            else:
                d2 += 1
    n = a + b + c2 + d2
    den = math.sqrt(float((a + b) * (c2 + d2) * (a + c2) * (b + d2)))
    phi = ((a * d2 - b * c2) / den) if den else float("nan")
    print("· w×rand 的 2×2（逐轨迹）：w正&rand正 %d ｜ w正&rand负 %d ｜ w负&rand正 %d ｜ w负&rand负 %d"
          " ｜ φ = %.4f（n=%d）" % (a, b, c2, d2, phi, n))
    # McNemar（逐轨迹的配对）
    disc = b + c2
    mcn_p = mcnemar_exact(b, c2)
    print("· McNemar（逐轨迹配对，不一致 %d 条：w优 %d / rand优 %d）⇒ 精确二项两侧 p = %.6f"
          % (disc, b, c2, mcn_p))

    # ---- ③ 跨臂零分布：逐轨迹 vs 块级
    print("")
    print("==== ③ 跨臂零分布：逐轨迹（面板上那个） vs 块级（前提不成立时该用的）====")
    tids = sorted(set(arms["w"]["pooled"]) & set(arms["rand"]["pooled"]))
    diffs = []
    for t in tids:
        sw = 1 if arms["w"]["pooled"][t]["verdict"] else -1
        sr = 1 if arms["rand"]["pooled"][t]["verdict"] else -1
        diffs.append(sw - sr)
    p_traj, obs_traj, ge_traj, n_traj = paired_perm_traj(diffs)
    print("· **逐轨迹**置换：p = %.6f（obs = %d ｜ ge=%d/%d）← 面板印的是 0.001750"
          % (p_traj, obs_traj, ge_traj, n_traj))

    blk_of = collections.OrderedDict()
    for t in tids:
        blk_of.setdefault(block_key(t), []).append(diffs[tids.index(t)])
    blk_diffs = [sum(v) for _q, v in blk_of.items()]
    p_blk, obs_blk, ge_blk, n_blk = paired_perm_block(blk_diffs)
    print("· **块级**置换（块内整体交换两臂标签）：p = %.6f（obs = %d ｜ ge=%d/%d）"
          % (p_blk, obs_blk, ge_blk, n_blk))
    print("  ⇒ ⇒ **比值**：块级 p ÷ 逐轨迹 p = %.2f×" % (p_blk / p_traj if p_traj else float("nan")))
    print("  ⇒ ⇒ 结论：%s"
          % ("**判决在块级零分布下依然站得住**（p 仍远小于 0.05）"
             if p_blk < 0.05 else "🔴 **判决在块级零分布下不成立**（p ≥ 0.05）⇒ ⇒ 口径依赖"))

    # ---- ④ 区间：口径对比
    print("")
    print("==== ④ 差 pp 的区间：Newcombe95（把轨迹当独立） vs 按块 bootstrap（承认聚类）====")
    pw = [1 if (len(blocks["w"][q]) == 2 and all(blocks["w"][q].values())) else 0
          for q in blocks["w"]]
    pr = [1 if (len(blocks["rand"][q]) == 2 and all(blocks["rand"][q].values())) else 0
          for q in blocks["rand"]]
    lo, hi = cluster_boot_diff(pw, pr)
    print("· **块级**差 %+.2f pp ｜ 按块 bootstrap 95%% 区间 [%+.2f, %+.2f] pp"
          % (100.0 * (sum(pw) / float(len(pw)) - sum(pr) / float(len(pr))), lo, hi))
    wp = sum(1 for v in arms["w"]["pooled"].values() if v["verdict"])
    rp = sum(1 for v in arms["rand"]["pooled"].values() if v["verdict"])
    nw, nr = len(arms["w"]["pooled"]), len(arms["rand"]["pooled"])
    ncl, nch = newcombe(wp, nw, rp, nr)
    print("· **轨迹级**差 %+.2f pp ｜ Newcombe95（假定轨迹独立）[%+.2f, %+.2f] pp"
          % (100.0 * (wp / float(nw) - rp / float(nr)), ncl, nch))
    print("  ⇒ ⇒ 若按块聚合：块级 w %d/%d ｜ rand %d/%d ｜ Fisher 两侧 p = %.6f"
          % (sum(pw), len(pw), sum(pr), len(pr),
             fisher_exact(sum(pw), len(pw) - sum(pw), sum(pr), len(pr) - sum(pr))))

    # ---- ⑤ 复制格一致性（前提独立性的第二层：块内还有 3 个复制格）
    print("")
    print("==== ⑤ 复制格一致性（块内 3 个 `pos_frac`）====")
    for arm in ("w", "rand"):
        same = split = 0
        for tid, v in arms[arm]["pooled"].items():
            vals = [x for x in v["vals"] if x != 0]
            if len(vals) < 2:
                continue
            if all(x == vals[0] for x in vals):
                same += 1
            else:
                split += 1
        print("· %s 臂：三格全一致 %d ｜ 2:1 分歧 %d ｜ 分歧率 %.4f（面板同）"
              % (arm, same, split, split / float(same + split)))

    print("")
    print("⚖ **这是探查**：上面的数**没进账本** ⇒ ⇒ 244.82 那一轮必须另有"
          "**第二条独立实现** ＋ **变异台**（能红）⇒ ⇒ 本探查只用来定方向。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
