"""R-6 的 P6/P7/P8 判决：correct vs wrong 的效应方向是否不同。

输入是 `r6_rerun.py` 的输出。判决规则全部来自 `.cache/xcheck/R6_RERUN_PREREG.md`
的 P6/P7/P8 与 Q3，**本文件不另设任何阈值**。

## 口径（P7）

- **口径 A（主）**：仅 marker 位置
- **口径 B**：全部抽样位置
两个口径都报；主口径是事先写死的，不允许事后换成对自己有利的那个。

## 统计量（P6）

- 每个读数先在**位置内**算 Δ，再对轨迹取均值（绝对 Δlogprob 跨位置不可比）
- Mann–Whitney U，双侧，α=0.05；并列值做 tie 校正
- 同时报 Cliff's delta 与 Hodges–Lehmann 估计量
- **correct 组 < 10 条轨迹，或 wrong 组 < 8 条轨迹 ⇒ 一律判
  「样本不足，不构成结论」**，不得因 p 值大小改口

## 特异性（P8）

`|Δmark| / |Δthe|`。若 < 0.5，结论里必须写上「不能说专门影响标记词」。
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

ALPHA = 0.05          # P6
MIN_CORRECT = 10      # P6
MIN_WRONG = 8         # Q3
SPEC_FLOOR = 0.5      # P8
# n1*n2 小于此值且**无并列**时走精确置换分布；正态近似在小样本下反保守
# （见 mannwhitney 注释）。有并列时一律退回 tie 校正的正态近似。
EXACT_MAX = 400

try:                                       # scipy 是权威实现，缺了要喊出来
    from scipy.stats import mannwhitneyu as SCIPY
    from scipy.stats import wilcoxon as WILCOXON
    from scipy.stats import kruskal as KRUSKAL
except Exception:                          # pragma: no cover
    SCIPY = WILCOXON = KRUSKAL = None
    print("⚠ 未找到 scipy —— 退回手写兜底实现。"
          "判决前必须先跑 r6_verdict_scipy_check.py 确认两者一致。")


# ---------------------------------------------------------------- 统计量
def _ranks(a):
    """平均秩（并列取均值），返回 (ranks, tie_groups)"""
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    i = 0
    ties = []
    while i < len(order):
        j = i
        while j + 1 < len(order) and a[order[j + 1]] == a[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        if j > i:
            ties.append(j - i + 1)
        i = j + 1
    return r, ties


def mannwhitney(x, y):
    """双侧 U + p。

    **权威实现是 scipy**（`scipy.stats.mannwhitneyu`）；本文件里的手写版
    `_mannwhitney_builtin` 只在 scipy 不可用时兜底，且必须被
    `r6_verdict_scipy_check.py` 逐例比对通过。

    ## 为什么不能只写个「差不多」的 p

    小样本下正态近似反保守：n1=n2=5 完全分离时近似给 p≈0.009，
    而精确置换分布的真值是 2/C(10,5)=0.00794。P6 的门槛恰好落在
    n≈10-18，正落在近似的危险区，所以按 P6 取数前写死的规则分支：

    - **无并列**且 `n1*n2 <= EXACT_MAX` ⇒ 精确置换分布
    - **其余情形（含任何并列）** ⇒ tie 校正 + 连续性校正的正态近似

    并列时**不许**用 scipy 的 `method='exact'`：它内部把 U `astype(int)`，
    带并列时会把 U 截断，算出来的是一个不存在的分布的尾概率。

    ## 两个手写时踩过的坑（留给兜底实现）

    1. 精确分支按「秩 1..n 互不相同」DP，在有并列时描述的是一个
       不存在的分布（实测偏差 0.046）。必须按**取值分组**DP。
    2. 连续性校正的**符号**取决于用上尾还是下尾。scipy 走
       `sf(max(U1,U2))` ⇒ 减 0.5；若按 `min` 取绝对值 ⇒ 必须**加** 0.5。
       写反了会比不加还差。
    """
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan"), float("nan")
    x, y = list(x), list(y)
    r, ties = _ranks(x + y)
    has_tie = bool(ties)
    method = "exact" if (n1 * n2 <= EXACT_MAX and not has_tie) else "asymptotic"

    U1 = sum(r[:n1]) - n1 * (n1 + 1) / 2.0
    U = min(U1, n1 * n2 - U1)          # 统一返回 min(U1,U2)，与用没用 scipy 无关

    if SCIPY is not None:
        p = float(SCIPY(x, y, alternative="two-sided", method=method).pvalue)
        z = float("nan")
        if method == "asymptotic":
            n = n1 + n2
            mu = n1 * n2 / 2.0
            tie_corr = sum(t ** 3 - t for t in ties)
            s = math.sqrt(n1 * n2 / 12.0 * ((n + 1) - tie_corr / (n * (n - 1.0))))
            Uhi = max(U1, n1 * n2 - U1)
            z = (Uhi - mu - 0.5) / s if s > 0 else 0.0
        return U, p, z
    return _mannwhitney_builtin(x, y, method)


def _mannwhitney_builtin(x, y, method):
    """不依赖 scipy 的兜底实现，约定与 scipy 逐位一致。"""
    n1, n2 = len(x), len(y)
    r, ties = _ranks(x + y)
    R1 = sum(r[:n1])
    U1 = R1 - n1 * (n1 + 1) / 2.0
    U2 = n1 * n2 - U1
    Uhi = max(U1, U2)
    Ulo = min(U1, U2)

    if method == "exact":
        return Ulo, _exact_p(x, y, Uhi), float("nan")

    n = n1 + n2
    mu = n1 * n2 / 2.0
    tie_corr = sum(t ** 3 - t for t in ties)
    sd = math.sqrt(n1 * n2 / 12.0 * ((n + 1) - tie_corr / (n * (n - 1.0))))
    if sd <= 0:
        return Ulo, 1.0, 0.0
    z = (Uhi - mu - 0.5) / sd            # 走 SF 上尾，所以**减** 0.5
    p = min(1.0, 2.0 * (0.5 * (1.0 - math.erf(z / math.sqrt(2)))))
    return Ulo, p, z


def _exact_p(x, y, Uhi):
    """Mann–Whitney U 的精确双侧 p，**并列值正确处理**，约定同 scipy。

    scipy 的双侧定义是 `2 * P(U >= max(U1, U2))`，且它的分布永远按
    **(min(n1,n2), max(n1,n2))** 这一组大小构造（`_MWU.sf(U, min, max)`）。
    带上这两点才能与 scipy 逐位对上。

    **本函数只接受无并列数据。** 并列时「精确双侧 p」没有公认口径：
    scipy 的 `sf()` 内部靠分布对称性把 `P(U>=k)` 换成 `cdf(mn-k)`，
    而带并列的置换分布**并不对称**（例：全同值样本真实 `P(U>=uhi)=0`，
    scipy 的对称捷径却给 1.0）。带并列时正态近似才是标准做法，
    所以 `mannwhitney()` 见到并列就改走近似分支；这里再挡一道，
    宁可报错也不给一个依赖口径约定的数。

    按「取值分组」DP：排序后第 j 个取值组有 c_j 个观测、平均秩 r_j
    （秩只取决于合并后的全体值）。状态 (i, s) = (已分给选择组的个数,
    秩和)，第 j 组选 k 个进选择组 ⇒ (i+k, s+k·r_j)，乘 C(c_j, k)。
    总数 Σ∏C(c_j,k_j) = C(n, m)，与「从 n 个里均匀选 m 个」一致。

    秩可能带 .5，故全程把秩乘 2 用整数运算，避免浮点键爆炸。
    """
    n1, n2 = len(x), len(y)
    m = min(n1, n2)
    pooled = list(x) + list(y)
    n = len(pooled)
    vals = sorted(pooled)
    if len(set(vals)) != n:
        raise ValueError(
            "_exact_p() 只接受无并列数据；带并列请走正态近似。"
            "（并列时精确双侧 p 无公认口径，见 docstring）")
    groups = []                       # (组大小, 平均秩×2)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[j + 1] == vals[i]:
            j += 1
        groups.append((j - i + 1, i + j + 2))   # 平均秩=(i+j)/2+1，×2 即 i+j+2
        i = j + 1

    cur = {(0, 0): 1}                  # (已选个数, 秩和×2) -> 计数
    for c, r2 in groups:
        nxt = defaultdict(int)
        for (i_, s2), w in cur.items():
            for k in range(0, min(c, m - i_) + 1):
                nxt[(i_ + k, s2 + k * r2)] += w * comb(c, k)
        cur = nxt

    off2 = m * (m + 1)                 # m(m+1)/2，×2
    uhi2 = 2.0 * Uhi
    tail = 0
    total = 0
    for (i_, s2), w in cur.items():
        if i_ != m:
            continue
        total += w
        if s2 - off2 >= uhi2 - 1e-9:
            tail += w
    if total == 0:
        return float("nan")
    return min(1.0, 2.0 * tail / total)


def cliffs_delta(x, y):
    if not x or not y:
        return float("nan")
    gt = sum(1 for a in x for b in y if a > b)
    lt = sum(1 for a in x for b in y if a < b)
    return (gt - lt) / (len(x) * len(y))


def hodges_lehmann(x, y):
    diffs = [a - b for a in x for b in y]
    return statistics.median(diffs) if diffs else float("nan")


def sign_frac(x):
    return (sum(1 for v in x if v > 0) / len(x)) if x else float("nan")


# ---------------------------------------------------------------- 次级分析 S
# 预登记修订 4 的 S1–S3。**次级**：不替代 P6，P6 判「样本不足」时结论照写。
# 设计动机：P6 死在「标签供给」上，而标签只是分组变量、不是机制本身。
S_ALPHA = 0.05
S_BONF = 2                 # 两个模式 => Bonferroni 校正到 0.025


def _paired_dose(trajs, hi_f, lo_f):
    """取同一条轨迹上 hi/lo 两个剂量的配对差，返回 (差值列表, 标签列表)。"""
    out = []
    for t in trajs:
        hi = t["traj_d"].get(hi_f)
        lo = t["traj_d"].get(lo_f)
        if hi is None or lo is None:
            continue
        out.append((hi - lo, t.get("label", "unknown")))
    return out


def s1_dose_monotonic(trajs, mode, hi_f="mark_w+_1.0", lo_f="mark_w+_0.5"):
    """S1 剂量单调性（不用标签）：剂量翻倍时 marker 集合 Δ 是否更大。

    Wilcoxon signed-rank 双侧；再要求中位差 > 0（方向与 w 训练方向一致，
    见 P9 符号基准）。两模式 Bonferroni。
    """
    pairs = _paired_dose(trajs, hi_f, lo_f)
    diffs = [d for d, _ in pairs]
    res = {"mode": mode, "n_paired": len(diffs), "field_hi": hi_f, "field_lo": lo_f}
    if len(diffs) < 5:
        res["verdict"] = "**样本不足，不构成结论**（配对数 %d < 5）" % len(diffs)
        return res
    med = statistics.median(diffs)
    res["median_diff"] = round(med, 5)
    res["mean_diff"] = round(statistics.mean(diffs), 5)
    res["pos_frac"] = round(sign_frac(diffs), 3)
    if all(abs(d) < 1e-12 for d in diffs):
        # scipy 的 wilcox 在「差值全为 0」时直接抛 ValueError。
        # 这不是异常场景——「剂量完全没有效应」就会走到这里，
        # 所以必须显式判成「未观察到」，不能让判决脚本崩掉。
        res["p"] = 1.0
        res["alpha_bonf"] = round(S_ALPHA / S_BONF, 4)
        res["verdict"] = ("**未观察到**剂量单调效应（全部 %d 条配对差为 0）。"
                          "这等于「本装置在两个剂量上给出同样的读数」，"
                          "与「有剂量反应」是同一件事的两面，报告时必须写明。"
                          % len(diffs))
        return res
    if WILCOXON is not None:
        p = float(WILCOXON(diffs, zero_method="wilcox",
                           alternative="two-sided").pvalue)
    else:
        # 无 scipy 时退回符号检验（保守）：忽略幅度，只数正负
        k = sum(1 for d in diffs if d > 0)
        n = sum(1 for d in diffs if d != 0)
        p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i)
                                                 for i in range(0, min(k, n - k) + 1))
                                  / 2 ** n)
        res["fallback"] = "sign-test（无 scipy）"
    res["p"] = round(p, 6)
    res["alpha_bonf"] = round(S_ALPHA / S_BONF, 4)
    if p < S_ALPHA / S_BONF and med > 0:
        res["verdict"] = ("剂量翻倍时 marker 集合 Δ 显著增大且方向为正"
                          "（p=%.4g < %.4g，中位差 %.4g）" % (p, S_ALPHA / S_BONF, med))
    elif p < S_ALPHA / S_BONF:
        res["verdict"] = ("统计显著但**方向为负**（中位差 %.4g）："
                          "剂量越大效应越小，与 P9 符号基准方向相反，"
                          "先查装置。" % med)
    else:
        res["verdict"] = ("**未观察到**剂量单调效应（p=%.4g >= %.4g）。"
                          "这不等于「无效应」，只等于本样本量下测不出。"
                          % (p, S_ALPHA / S_BONF))
    return res


def s2_three_group(trajs, mode, field):
    """S2 三组 Kruskal–Wallis：correct / wrong / unlabeled 一起比。

    P6 之所以卡死，是因为 unlabeled 被丢掉了。S2 把它留作独立组，
    于是最大的一批样本重新进入检验。
    """
    g = {"correct": [], "wrong": [], "unlabeled": []}
    for t in trajs:
        v = t["traj_d"].get(field)
        if v is None:
            continue
        lab = t.get("label", "unlabeled")
        g[lab if lab in g else "unlabeled"].append(v)
    res = {"mode": mode, "field": field,
           "n": {k: len(v) for k, v in g.items()},
           "median": {k: (round(statistics.median(v), 4) if v else None)
                      for k, v in g.items()}}
    alive = [v for v in g.values() if v]
    if len(alive) < 2:
        res["verdict"] = "**样本不足，不构成结论**（可用组 < 2）"
        return res
    if KRUSKAL is not None:
        res["H"] = round(float(KRUSKAL(*alive).statistic), 4)
        res["p"] = round(float(KRUSKAL(*alive).pvalue), 6)
    else:
        res["verdict"] = "**无法检验**：无 scipy，Kruskal–Wallis 不可用"
        return res
    sig = res["p"] < S_ALPHA / S_BONF
    res["alpha_bonf"] = round(S_ALPHA / S_BONF, 4)
    res["verdict"] = (
        "三组存在差异（p=%.4g < %.4g）。**这不等于 correct 与 wrong 不同**——"
        "差异可能来自 correct vs unlabeled。必须看下面的两两比较。"
        % (res["p"], S_ALPHA / S_BONF) if sig else
        "**未观察到**三组差异（p=%.4g >= %.4g）；这不等于「无差异」。"
        % (res["p"], S_ALPHA / S_BONF))
    # 两两比较（Mann–Whitney，与 P6 同一套统计量与分支规则）
    pairs = {}
    for a in ("correct", "wrong", "unlabeled"):
        for b in ("correct", "wrong", "unlabeled"):
            if a >= b:
                continue
            if not (g[a] and g[b]):
                continue
            _, p, _ = mannwhitney(g[a], g[b])
            pairs[f"{a}_vs_{b}"] = {
                "p": round(p, 6),
                "cliffs_delta": round(cliffs_delta(g[a], g[b]), 3),
                "sig": p < S_ALPHA / S_BONF,
            }
    res["pairwise"] = pairs
    return res


def s3_specificity(trajs, mode):
    """S3 特异性（P8）：与标签无关，所以 n 用全部轨迹而非仅有标签的。"""
    num = [abs(t["traj_d"].get("mark_w+_1.0", 0.0)) for t in trajs]
    den = [abs(t["traj_d"].get("the_w+_1.0", 0.0)) for t in trajs]
    pr = [(a, b) for a, b in zip(num, den) if b > 1e-9]
    if not pr:
        return {"mode": mode, "n": 0,
                "verdict": "**无法计算**：所有轨迹的 Δthe 都是 0"}
    r = [a / b for a, b in pr]
    out = {"mode": mode, "n": len(r),
           "median": round(statistics.median(r), 3),
           "min": round(min(r), 3), "max": round(max(r), 3),
           "n_labeled": sum(1 for t in trajs if t.get("label") != "unknown")}
    out["below_floor"] = out["median"] < SPEC_FLOOR
    out["verdict"] = ("中位特异性 %.3f < %.1f ⇒ **不能说专门影响标记词**"
                      % (out["median"], SPEC_FLOOR) if out["below_floor"]
                      else "中位特异性 %.3f >= %.1f" % (out["median"], SPEC_FLOOR))
    return out


# ---------------------------------------------------------------- 主判决
def verdict_for(rows, field, calib_name):
    """对某个读数字段逐模式出判决。"""
    out = {}
    for mode in ("think", "no_think"):
        rs = [r for r in rows
          if r["mode"] == mode and r["traj_d"].get(field) is not None]
        c = [r["traj_d"][field] for r in rs if r["label"] == "correct"]
        w = [r["traj_d"][field] for r in rs if r["label"] == "wrong"]
        entry = {
            "n_traj_labeled": len(rs),
            "correct_n": len(c), "wrong_n": len(w),
            "correct_med": round(statistics.median(c), 4) if c else None,
            "wrong_med": round(statistics.median(w), 4) if w else None,
            "correct_posfrac": round(sign_frac(c), 3) if c else None,
            "wrong_posfrac": round(sign_frac(w), 3) if w else None,
        }
        enough = len(c) >= MIN_CORRECT and len(w) >= MIN_WRONG
        entry["enough"] = enough
        if enough:
            U, p, z = mannwhitney(c, w)
            entry.update({
                "U": U, "p": round(p, 5), "z": round(z, 3),
                "cliffs_delta": round(cliffs_delta(c, w), 3),
                "hodges_lehmann": round(hodges_lehmann(c, w), 4),
            })
            if p < ALPHA:
                entry["verdict"] = ("两组效应显著不同（p<%.2f）" % ALPHA)
            else:
                entry["verdict"] = ("**未观察到**两组效应不同（p=%.3f >= %.2f）；"
                                    "这不等于「无差异」，只等于本样本量下测不出。" % (p, ALPHA))
        else:
            why = []
            if len(c) < MIN_CORRECT:
                why.append(f"correct 组 {len(c)} < {MIN_CORRECT}")
            if len(w) < MIN_WRONG:
                why.append(f"wrong 组 {len(w)} < {MIN_WRONG}")
            entry["verdict"] = ("**样本不足，不构成结论**（" + "；".join(why) +
                                "）。按 P6 不得因 p 值大小改口。")
        out[mode] = entry
    return out


def main(inp, out):
    d = json.load(open(inp, encoding="utf-8"))
    rows = d["rows"]
    if not d.get("pos_ok"):
        print("⚠ P9 装置符号基准未通过 —— 按预登记**不得**继续做分组判决。")
        print("  先修装置。")
        json.dump({"blocked_by_P9": True}, open(out, "w"), ensure_ascii=False, indent=1)
        return 2

    # 每条轨迹对每个读数字段取均值（先位置内、再轨迹内）
    agg = {}
    for r in rows:
        k = r["traj"]
        agg.setdefault(k, {"traj": k, "mode": r["mode"], "label": r["label"],
                           "traj_d": {}, "n_pos": 0})
        agg[k]["n_pos"] += 1
        for kk, vv in r.items():
            if kk.startswith(("mark_", "the_", "tok_")) and isinstance(vv, (int, float)):
                agg[k]["traj_d"].setdefault(kk, []).append(vv)
    trajs = []
    for k, v in agg.items():
        v["traj_d"] = {kk: statistics.mean(vv) for kk, vv in v["traj_d"].items()}
        trajs.append(v)

    print("=" * 78)
    print(f"轨迹池 {len(trajs)} 条；"
          f"{ {m: sum(1 for t in trajs if t['mode']==m) for m in ('think','no_think')} }")
    print("=" * 78)

    # 主读数按预登记：w+@1.0 的 marker 集合效应
    fields = [("mark_w+_1.0", "口径A 主读数：+w@rel1.0 对 marker 集合"),
              ("mark_w-_1.0", "+w@rel1.0 的反向对照：-w"),
              ("mark_rand_1.0", "+w@rel1.0 的随机方向对照"),
              ("tok_w+_1.0", "该位置实际写下的标记词的 Δlogit"),
              ("mark_w+_0.5", "低剂量 w+@rel0.5"),
              ("mark_w-_0.5", "低剂量 w-@rel0.5")]

    verdicts = {}
    for f, name in fields:
        if f not in (trajs[0]["traj_d"] if trajs else {}):
            continue
        v = verdict_for(trajs, f, name)
        verdicts[f] = {"name": name, "per_mode": v}
        print(f"\n--- {name} ---")
        for mode, e in v.items():
            print(f"  [{mode}] correct {e['correct_n']} (中位 {e['correct_med']}, "
                  f"正号占比 {e['correct_posfrac']}) | "
                  f"wrong {e['wrong_n']} (中位 {e['wrong_med']}, "
                  f"正号占比 {e['wrong_posfrac']})")
            print(f"          {e['verdict']}")

    # 特异性 P8
    spec = {}
    for mode in ("think", "no_think"):
        rs = [t for t in trajs if t["mode"] == mode]
        if not rs:
            continue
        num = [abs(t["traj_d"].get("mark_w+_1.0", 0.0)) for t in rs]
        den = [abs(t["traj_d"].get("the_w+_1.0", 0.0)) for t in rs]
        pairs = [(a, b) for a, b in zip(num, den) if b > 1e-9]
        if pairs:
            r = [a / b for a, b in pairs]
            sp = {"n": len(pairs), "median": round(statistics.median(r), 3),
                  "min": round(min(r), 3), "max": round(max(r), 3)}
            sp["below_floor"] = sp["median"] < SPEC_FLOOR
            spec[mode] = sp
            print(f"\n[P8 特异性 |Δmark|/|Δthe|] {mode}: n={sp['n']} "
                  f"中位={sp['median']} (min {sp['min']}, max {sp['max']})"
                  f"  {'**低于 0.5 -> 不能说专门影响标记词**' if sp['below_floor'] else ''}")

    # ---------------------------------------------------------------- 次级 S
    # 预登记修订 4。**次级**，不替代 P6；P6 判「样本不足」时结论照写。
    secondary = {}
    for mode in ("think", "no_think"):
        rs = [t for t in trajs if t["mode"] == mode]
        if not rs:
            continue
        print(f"\n===== 次级分析 {mode}（n={len(rs)}，修订 4 预登记） =====")
        s1 = s1_dose_monotonic(rs, mode)
        secondary.setdefault(mode, {})["S1_dose_monotonic"] = s1
        print(f"  [S1 剂量单调性] 配对 {s1['n_paired']}  "
              f"中位差 {s1.get('median_diff')}  p={s1.get('p')}")
        print(f"       {s1['verdict']}")

        s2s = {}
        for f in ("mark_w+_1.0", "tok_w+_1.0"):
            if not rs or f not in rs[0]["traj_d"]:
                continue
            e = s2_three_group(rs, mode, f)
            s2s[f] = e
            print(f"  [S2 三组 KW] {f}  n={e['n']}  H={e.get('H')} p={e.get('p')}")
            print(f"       {e['verdict']}")
            for k, v in (e.get("pairwise") or {}).items():
                print(f"         {k}: p={v['p']} delta={v['cliffs_delta']} "
                      f"{'显著' if v['sig'] else '未达显著'}")
        secondary.setdefault(mode, {})["S2_three_group"] = s2s

        s3 = s3_specificity(rs, mode)
        secondary[mode]["S3_specificity"] = s3
        print(f"  [S3 特异性] n={s3['n']}（全部轨迹，与标签无关）"
              f"  中位={s3.get('median')} min={s3.get('min')} max={s3.get('max')}")
        print(f"       {s3['verdict']}")

    print()
    print("=" * 78)
    print("提醒：S1–S3 是**次级**分析，不替代 P6。")
    print("     若 P6 判「样本不足」，结论必须照写，不得用 S 的结果改口。")
    print("=" * 78)

    res = {"input": inp, "pos_ok": d["pos_ok"], "class_gap": d.get("class_gap"),
           "rel_ladder": d.get("rel_ladder"), "n_traj": len(trajs),
           "verdicts": verdicts, "specificity": spec, "secondary": secondary,
           "rules": {"alpha": ALPHA, "min_correct": MIN_CORRECT,
                     "min_wrong": MIN_WRONG, "spec_floor": SPEC_FLOOR,
                     "secondary_alpha": S_ALPHA,
                     "secondary_bonferroni": S_BONF}}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))