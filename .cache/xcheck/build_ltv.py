#!/usr/bin/env python3
"""LTV 的**唯一判决权威**。从 probe_ltv.py 的原始落盘字段独立算一遍。

⚠ 本文件不 import 探针，也不复用它的任何中间量。
  探针自己也算了一部分（用于增量落盘），那份**不作为结论** ——
  同源共用会「一处错则处处绿」。

判决规则全部来自 `LTV_PREREG.md`，那是**取数之前**写死的。
结果与门不符就照实报，不换指标、不改门、不挑一个好看的讲。

用法:
  python3 .cache/xcheck/build_ltv.py
  ARTIFACT=.cache/xcheck/ltv.json PUBLIC=... python3 .cache/xcheck/build_ltv.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ART = os.environ.get("ARTIFACT", os.path.join(HERE, "ltv.json"))
PUBLIC = os.environ.get("PUBLIC", os.path.join(
    REPO, "frontend", "public", "latent", "data", "ltv.json"))

# ---- 预登记表 §3 写死的量 ----------------------------------------------------
ALPHA_GRID = [0.05, 0.1, 0.2, 0.35, 0.5, 1.0, 2.0, 4.0]
FIT_ALPHAS = [0.05, 0.1, 0.2]
K_MAX = 8
# G-a：预登记表写的是「≤ 一档强度（α 网格相邻档）」。
#   这里按**字面**实现成「在网格里的下标相差 ≤ 1」，因为那是可判定的形式。
#   ⚠ 预登记表 §3 把它描述成「本网格上约 1.7~2.8 倍」，而本网格的实际相邻档之比是
#     2 / 2 / 1.75 / 1.43 / 2 / 2 / 2 —— **下界 1.43，不是 1.7**。
#     预登记表那句话与它自己定的网格对不上；按上面的「相邻档」字面执行，
#     并把这个不一致印出来，不替它圆。
# -----------------------------------------------------------------------------

# ⚠⚠⚠ 判决切片：G-a0 / G-a / G-b 只在**留出集**上判（预登记表 §43/§84/§100-101）。
#   第一版在**全部 36 个**上下文上判 —— 那是 18 留出 + 18 抽取混在一起，
#   而 G-a 的 claim 与预登记表都写着「在**留出**上下文上」。
#   ⇒ 口径与 claim 不一致，而产物里**没有任何字段披露这一点**：
#     `caveats` 五条一条没提，公开产物的 `split` 还反过来说 `holdout: []`。
#   实测两种口径的差别不是修辞：
#     G-a  全部 36 ⇒ 可判 22 / 0 红；仅留出 18 ⇒ 可判 12 / 0 红（都 pass）
#     G-b  全部 36 ⇒ +1 24／−1 3，p=4.92e-05
#          仅留出 18 ⇒ +1 14／−1 0，p=1.22e-04（更干净）
#          仅抽取 18 ⇒ +1 10／−1 3，p=9.23e-02（**不显著**）
#   ⇒ 混合口径恰好把「抽取集上不显著」这件事藏了起来，而那正是
#     留出划分存在的理由。判决一律按预登记口径走；全量口径作为
#     `variant_all_ctx` 并列发出，但**它不是判决**。
JUDGE_SLICE = "holdout"

def _gb_score(r):
    """G-b 的逐上下文配对打分。**判决与并列口径共用这一份**。

    ⚠ 抽成函数是因为第一版把同一段打分写了两遍（判决一次、并列一次），
      而「同一段数学写两遍」会悄悄不一致 —— 变体与判决对不上时，
      读的人只能看见两个数，不会知道哪个是哪个算出来的。
      ⇒ 单一实现，两处调用。
    """
    n_ctl = len(r["ctl_all"])
    n_ctl_flip = sum(1 for v in r["ctl_all"].values() if v is not None)
    a = r["alpha_star_meas"]
    if a is None and n_ctl_flip == 0:
        return 0, "两边都没改口 ⇒ 无从比较（不记 +1 也不记 −1）"
    if a is None:
        return -1, f"臂没改口，但 {n_ctl_flip}/{n_ctl} 个对照改口了"
    if n_ctl_flip == 0:
        return 1, "臂改口而两个对照都没改口"
    best = min(v for v in r["ctl_all"].values() if v is not None)
    return (1 if a < best else (-1 if a > best else 0)), \
           f"两边都改口：臂 α*={a} vs 对照最早 {best}"


def _gb_sign_p(pos, neg):
    """双侧符号检验的精确 p（n 小，直接数，不用正态近似）。"""
    n_eff = pos + neg
    if n_eff <= 0:
        return 1.0
    k = min(pos, neg)
    return min(1.0, 2 * sum(math.comb(n_eff, i) for i in range(0, k + 1)) / (2 ** n_eff))


def _g_b_variant(rows):
    """同一套打分在**别的切片**上的读数。只作并列信息，不作判决。"""
    pos = neg = zero = 0
    for r in rows:
        s, _w = _gb_score(r)
        pos += s > 0
        neg += s < 0
        zero += s == 0
    return {"n_ctx": len(rows), "n_plus": pos, "n_minus": neg, "n_zero": zero,
            "n_effective": pos + neg, "sign_test_p": _gb_sign_p(pos, neg),
            "note": "并列口径，不是判决；判决切片见 judge_slice"}


# ---------------------------------------------------------------------------
# ① 句子锚定的稀疏分解
#
# ⚠⚠⚠ 这里补的是**一个从未被执行过的方法组件**。
#   预登记表 §1 ① 写的是 v = Σ c_k (r̄(S_k) − r̄(S'_k))，‖c‖₀ ≤ K ≤ 8，
#   并把它列为 LTV 三个组成部分的第一个（「名字可读」）。
#   而 probe_ltv.py 里那一段的实际内容只有：
#       for i, (key, s, sp) in enumerate(SENTENCE_PAIRS):
#           d = resid_at_last(S) - resid_at_last(Sp)
#           rows.append({... "vec": [...] "norm": ...})
#   —— 把 11 条 d_k 算出来倒进产物，**没有 lstsq、没有求 c_k、没有按 |c_k| 选子集**。
#   `K_MAX = 8` 从头到尾只被当作**元数据搬运**（原始层 setting.k_max → 产物 k_max
#   → verify 的 _EXPECT），**从未参与任何选择**。
#   ⇒ 一个「旋钮」被当成参数传了三个文件，但没有任何东西读它。
#     这正是 [[旋钮值 ≠ 生效值]]：设了不等于生效。
#
#   而公开产物与第 8 屏都按「这些句子是这个向量的分解」呈现它 ——
#   一个**从未发生**的分解，被当成事实印在读者面前。
#
#   现在把它真算出来。**判据是过程门**（算过没有、c_k 齐不齐、K_MAX 用上没有），
#   不是「解释率够不够高」那种事后才找得到的阈值门 ——
#   后者正是「未写死却左右判决」，这里不许做。
#   实测出来的解释率原样进 `decomp` 并进 `caveats`，由读者自己判断。
# ---------------------------------------------------------------------------
def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _solve_sym(Amat, bvec):
    """带极小岭项的高斯消元解对称正定方程组（维度 = 轴数，很小）。"""
    n = len(bvec)
    A = [row[:] for row in Amat]
    r = bvec[:]
    for i in range(n):
        piv = max(range(i, n), key=lambda k: abs(A[k][i]))
        if abs(A[piv][i]) < 1e-300:
            raise ValueError("Gram 矩阵奇异：句子轴互相共线，最小二乘无唯一解")
        A[i], A[piv] = A[piv], A[i]
        r[i], r[piv] = r[piv], r[i]
        for k in range(i + 1, n):
            f = A[k][i] / A[i][i]
            for j in range(i, n):
                A[k][j] -= f * A[i][j]
            r[k] -= f * r[i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (r[i] - sum(A[i][j] * x[j] for j in range(i + 1, n))) / A[i][i]
    return x


def _sparse_decomp(sd, lever_vec, k_max):
    """把杠杆 v 在 {d_k} 上做**最小二乘**分解，并按 |c_k| 真的取前 k_max 个。

    ⚠ 最小二乘用的是**全部**轴，不是前 k_max 个 —— 前 k_max 个里的最小二乘
      是另一个（非凸）问题。这里先解全解再按 |c_k| 排序，理由写在这里，
      因为它决定了 `explained_energy` 与 `top_k` 的关系：
      **`explained_energy` 是全解的，`top_k` 是它的截断**，两者不可混读。
    ⚠ 因此当 K_MAX < 轴数时，`top_k` 的重建能量会**低于** `explained_energy`。
      两个数都发出来，别让读者拿 top_k 去核对 explained_energy。
    """
    keys = [r["key"] for r in sd]
    vecs = [r["vec"] for r in sd]
    nv = math.sqrt(_dot(lever_vec, lever_vec))
    if nv <= 0:
        raise ValueError("杠杆向量范数为 0，无法分解")
    m = len(keys)
    gram = [[_dot(vecs[i], vecs[j]) for j in range(m)] for i in range(m)]
    # 岭项只用来在轴几乎共线时稳住数值；相对量级取 Gram 对角的中位数。
    diag = sorted(gram[i][i] for i in range(m))
    ridge = 1e-9 * (diag[m // 2] if m else 1.0)
    for i in range(m):
        gram[i][i] += ridge
    coef = _solve_sym(gram, [_dot(vecs[i], lever_vec) for i in range(m)])

    resid_sq = 0.0
    for j in range(len(lever_vec)):
        rec = sum(coef[i] * vecs[i][j] for i in range(m))
        resid_sq += (rec - lever_vec[j]) ** 2
    resid_ratio = math.sqrt(resid_sq) / nv
    explained = max(0.0, 1.0 - resid_ratio ** 2)

    per_axis = []
    for i, r in enumerate(sd):
        nd = math.sqrt(_dot(vecs[i], vecs[i]))
        cos = (_dot(vecs[i], lever_vec) / (nd * nv)) if nd > 0 else None
        per_axis.append({
            "key": keys[i],
            "cos": cos,
            "cos2": (cos * cos) if cos is not None else None,
            "c": coef[i],
            "norm_d": nd,
            "negative_control": bool(r.get("negative_control")),
        })

    order_by_abs = sorted(range(m), key=lambda i: -abs(coef[i]))
    top = order_by_abs[:max(0, min(k_max, m))]
    # 截断后的重建能量 = ‖Σ_{i∈top} c_i d_i‖² / ‖v‖²
    # ⚠⚠ 第一版这里写成 Σ c_i²‖d_i‖² —— 那是**基向量各自**的能量，
    #   不是重建的能量，而且它不保证 ≤ explained_energy。实测印出 **207.562%**，
    #   一个 >100% 的「被解释的能量」自己就把错处喊出来了。
    #   ⇒ 能量一律按 ‖重建 − 目标‖² / ‖目标‖² 这一个式子算，全解与截断共用，
    #     也保证截断 ≤ 全解（少几个轴只会更差）。
    def _energy(idxs):
        s = 0.0
        for j in range(len(lever_vec)):
            rec = sum(coef[i] * vecs[i][j] for i in idxs)
            s += (rec - lever_vec[j]) ** 2
        return max(0.0, 1.0 - (math.sqrt(s) / nv) ** 2)

    top_explained = _energy(top)

    return {
        "n_axes": m,
        "k_max": k_max,
        "objective": "在全部 d_k 上最小二乘，再按 |c_k| 取前 k_max 个",
        "lever_norm": nv,
        "explained_energy": explained,
        "residual_ratio": resid_ratio,
        "top_k_energy": top_explained,
        "top_k": [keys[i] for i in top],
        "n_negative_control_in_top_k": sum(1 for i in top if sd[i].get("negative_control")),
        "negative_control_keys": [r["key"] for r in sd if r.get("negative_control")],
        "axes": per_axis,
        "note": "explained_energy 是**全解**的能量，top_k 是它的 |c_k| 截断；"
                "K_MAX < 轴数时两者不相等，核对时别混用",
    }


gates, order = {}, []


def put(key, name, claim, verdict, evidence, why_na=None):
    if key in gates:
        raise SystemExit(f"一道门只能 put 一次：{key}")
    g = {"name": name, "claim": claim, "verdict": verdict, "evidence": evidence}
    if why_na:
        g["why_na"] = why_na
    gates[key] = g
    order.append(key)


def log(*a):
    print(*a, flush=True)


def grid_idx(a):
    """α 在网格里的下标；不在网格上（预测值）返回 None。"""
    for i, x in enumerate(ALPHA_GRID):
        if abs(x - a) < 1e-9:
            return i
    return None


def fit_slope(ys, xs):
    """最小二乘斜率与截距（两点以上）。"""
    n = len(xs)
    if n < 2:
        return None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return b, my - b * mx


def sensitivity(ctx):
    """⚠ G-a 的判决依赖「g_v 在哪几档上拟合」—— 而预登记表**没有写死这一项**。

    项目规矩是「判决规则必须取数前写死」。这一项当时没写 ⇒
    它就是一个**未写死却左右判决**的参数。补救不是替它选一个好看的，
    而是**把它变成报告出来的一列**：同一批数据、同一道门、只换拟合窗，
    判决会变成什么，全部印出来。

    为什么主口径取**最小的三档**：窗口越宽，越可能把改口点本身包进去
    ⇒ g_v 是拿答案拟合答案 ⇒ 门变成恒真。所以主口径必须窄。
    而窄窗口的代价正是 pos=391 那种情形：小 α 段 gap 几乎是平的，
    拟合出 g_v ≈ 0，预测「永不改口」，实测却在 α=4 改了口 ——
    这是**真失败**，不是拟合事故（那条曲线的原始形状就在产物里）。
    """
    out = []
    wins = [[0.05, 0.1, 0.2], [0.05, 0.1, 0.2, 0.35], [0.05, 0.1, 0.2, 0.35, 0.5],
            [0.05, 0.1, 0.2, 0.35, 0.5, 1.0], ALPHA_GRID]
    for w in wins:
        hit = circ = both = f = 0
        for c in ctx:
            gap = c["arm_gap"]
            xs = [a for a in w if str(a) in gap]
            ys = [float(gap[str(a)]) for a in xs]
            b, _ = fit_slope(ys, xs)
            m = c["arm_alpha_star"]
            # ⚠⚠ 这里**必须**用与主口径同一套剔除。第一版敏感性函数只剔了
            #   「改口落在窗口内」，没剔「gap 非单调」⇒ 它把主口径已经判 na 的
            #   位置又拿去判了一遍，而那一遍的口径更宽、命中更多 ⇒ 表里
            #   出现「主口径 PASS 而宽窗 FAIL」这种自相矛盾的行。
            #   ⇒ 两处必须共用同一个前置。
            if len(ys) >= 2 and any(ys[i + 1] > ys[i] + 1e-12
                                   for i in range(len(ys) - 1)):
                continue          # 线性外推的前提不成立 ⇒ 与主口径一致地剔除
            if m is not None and m <= max(w):
                circ += 1          # 改口落在窗口内 ⇒ 这档拟合含答案，不可判
                continue
            g = None if b is None else -b
            p = None if (g is None or g <= 0) else float(c["m_p"]) / g
            if p is None:
                if m is None:
                    both += 1
                else:
                    f += 1
                continue
            if m is None:
                if p > ALPHA_GRID[-1]:
                    both += 1
                else:
                    f += 1
                continue
            ip = min(range(len(ALPHA_GRID)), key=lambda i: abs(ALPHA_GRID[i] - p))
            im = grid_idx(m)
            if im is not None and abs(ip - im) <= 1:
                hit += 1
            else:
                f += 1
        out.append({"fit_alphas": w, "n_circular": circ, "n_within_one_notch": hit,
                    "n_both_censored": both, "n_fail": f,
                    # ⚠⚠ **「不可判的多」不是「红得少」。**
                    #   实测：全网格那一行是 8/11 不可判 + 0 红 ⇒ 看着像满分通过，
                    #   实际上它只是**几乎什么都没测**（拟合窗把改口点包进去了，
                    #   g_v 是拿答案拟合答案）。不守这一条，宽窗就会把窄窗发现的
                    #   真失败「洗成」通过 —— 与「全 PASS 的判据等于没有判据」同族。
                    "n_judged": hit + both + f,
                    "verdict": ("degenerate_untested" if (hit + both + f) == 0 or
                                circ > 0.5 * (hit + both + f + circ)
                                else ("pass" if f == 0 else "fail"))})
    return out


# ---- G-c：名字预测效果 --------------------------------------------------------
# 判决规则**逐条**照抄 LTV_PREREG.md 修订 4 ④ / ⑥b / ⑥c + 修订 5，
# 词表与主/负对照键名**不在本文件另写一份**，从 ltv_behavior 取（那是照着
# 预登记实现的唯一一份）。两处各写一份词表，迟早会漂移。
# ⚠ 判决在取数前就已写死；看到读数后不许在这里挑档、改词表、或改哪一条成立。

_ALPHAS_GC = (0.35, 1.0, 4.0)      # 修订 4 ①
_HOLDOUT_N = 3                     # 修订 4 ⑤：3 题 ⇒ 符号检验最小 p=1.0 ⇒ 不报 p


def _g_c_verdict(beh):
    """返回 (verdict, evidence, why_na)。三条子判据逐档算，全部三档成立才算 pass。"""
    import ltv_behavior as LB          # 唯一一份词表/池化实现

    ev = {"alphas": list(_ALPHAS_GC), "primary_key": LB.PRIMARY_KEY,
          "negative_keys": list(LB.NEGATIVE_KEYS),
          "n_holdout": _HOLDOUT_N,
          "n_runs": beh.get("n_runs"),
          "rule": "修订 4 ④G-c.1/.2/.3，在全部三档 α 上都成立才 pass（⑥b）",
          "no_p_value": "3 题配对比较的符号检验最小 p=1.0 ⇒ 不报 p，改判逐题同号（修订 4 ⑤）",
          "per_alpha": {}}

    rows = beh["per_run"]
    pids = beh["pooled_by_problem"].keys()

    # ---- 修订 4 ⑥c / 修订 5：先把不可判格挑出来（先于任何判决）--------------
    undec = []
    for pid in pids:
        for a in _ALPHAS_GC:
            sel = [r for r in rows if r["pid"] == pid and r["alpha"] == a]
            sha = {r["arm"]: r.get("sha1") for r in sel}
            if len(sha) == 3 and len(set(sha.values())) == 1:
                undec.append({"pid": pid, "alpha": a,
                              "why": "三臂生成文本逐字相同 ⇒ 这一格没有分辨力"})
    ev["undecidable_cells"] = undec

    if undec:
        ev["c1_direction"] = "未判（存在不可判格）"
        ev["c2_per_problem"] = "未判（存在不可判格）"
        ev["c3_negative_control"] = "未判（存在不可判格）"
        return "na", ev, (
            f"存在 {len(undec)} 个 (题,α) 格三臂文本逐字相同 ⇒ 该格没有分辨力，"
            f"按修订 5 报 na（不报 pass 也不报 fail）。逐条读数见 evidence.undecidable_cells。"
            f"⚠ 若想「剔掉那题再判」，那是一次口径变更，必须作为修订追加。")

    # ---- 三条子判据逐档算 ---------------------------------------------------
    all_ok, failed_alpha = True, []
    for a in _ALPHAS_GC:
        pa = {arm: (LB.pooled_where(rows, alpha=a, arm=arm) or {}).get(LB.PRIMARY_KEY, 0.0)
              for arm in ("arm", "rand", "zero")}
        d_rand = pa["arm"] - pa["rand"]

        # G-c.1 方向性：arm > rand 且 arm > zero（与 rand 的比较有牙齿）
        c1 = (d_rand > 0) and (pa["arm"] > pa["zero"])

        # G-c.2 逐题同号：每一题 arm-rand 都为正
        per = {pid: ((LB.pooled_where(rows, pid=pid, alpha=a, arm="arm") or {}).get(LB.PRIMARY_KEY, 0.0)
                    - (LB.pooled_where(rows, pid=pid, alpha=a, arm="rand") or {}).get(LB.PRIMARY_KEY, 0.0))
               for pid in pids}
        c2 = all(x > 0 for x in per.values())

        # G-c.3 负对照不吃进来：confident 的 arm-rand 涨幅 > 负对照里最大涨幅
        neg = {nk: (LB.pooled_where(rows, alpha=a, arm="arm") or {}).get(nk, 0.0)
                    - (LB.pooled_where(rows, alpha=a, arm="rand") or {}).get(nk, 0.0)
               for nk in LB.NEGATIVE_KEYS}
        worst = max(neg, key=lambda k: neg[k])
        c3 = d_rand > neg[worst]

        ok = c1 and c2 and c3
        if not ok:
            all_ok = False
            failed_alpha.append(a)
        ev["per_alpha"][str(a)] = {
            "rates": pa, "d_arm_minus_rand": d_rand,
            "c1_direction": bool(c1), "c2_per_problem": bool(c2),
            "per_problem_d": per, "c3_negative_control": bool(c3),
            "negative_deltas": neg, "worst_negative_key": worst,
            "all_three_hold": ok}

    ev["c1_direction"] = all(ev["per_alpha"][str(a)]["c1_direction"] for a in _ALPHAS_GC)
    ev["c2_per_problem"] = all(ev["per_alpha"][str(a)]["c2_per_problem"] for a in _ALPHAS_GC)
    ev["c3_negative_control"] = all(ev["per_alpha"][str(a)]["c3_negative_control"] for a in _ALPHAS_GC)
    ev["failed_alphas"] = failed_alpha
    ev["verdict_rule"] = ("三条子判据在全部三档 α 上都成立 ⇒ pass（⑥b）"
                          "；任一档不成立 ⇒ fail 并指明是哪一档")
    if all_ok:
        return "pass", ev, None
    return "fail", ev, (f"三档里有 {len(failed_alpha)} 档不成立：α={failed_alpha}。"
                        f"⚠ 若想「改成只看 α=1.0」，那是一次口径变更，必须作为修订追加，"
                        f"并同时发出被丢掉的那一档的读数（修订 4 ⑥b）。")


def main():
    if not os.path.exists(ART):
        log(f"原始产物不存在：{ART}；先跑 probe_ltv.py")
        return 2
    d = json.load(open(ART, encoding="utf-8"))
    ctx = d.get("contexts") or []
    if not ctx:
        log("产物里没有 contexts —— 这一轮没取到数，不许判绿")
        return 2
    log(f"原始产物 {ART}")
    log(f"杠杆 {d.get('lever', {}).get('name')}@L{d.get('layer')}　"
        f"α 网格 {d.get('alpha_grid')}　拟合窗 {d.get('fit_alphas')}")
    log(f"上下文 {len(ctx)} 个；留出划分 {d.get('split')}")

    # ---- 判决切片 ------------------------------------------------------
    # ⚠ 留出集为空时**不许判绿**：那正是「在留出上下文上」这个前提不成立，
    #   与 G-c 报 na 是同一件事（G-c 的 why_na 里已经写了同一句话）。
    #   这里选择**停下**而不是报 na，是因为判决切片是**本文件的口径**，
    #   不是被测物的性质 —— 装置自己口径错位应当 exit 2 让你看见。
    _split = d.get("split") or {}
    _ho = list(_split.get("holdout") or [])
    _ex = list(_split.get("extract") or [])
    if JUDGE_SLICE == "holdout":
        if not _ho:
            log("装置故障：预登记表要求在留出集上判（G-a/G-b），"
                "而产物 split.holdout 是空的 ⇒ 前提不成立，不许判绿")
            return 2
        _jctx = [c for c in ctx if c["pid"] in _ho]
        log(f"判决切片 = 留出集 {len(_ho)} 题 / {len(_jctx)} 个上下文"
            f"（全量 {len(ctx)} 个仅作并列信息发出，不作判决）")
    else:
        _jctx = list(ctx)
        log(f"判决切片 = 全量 {len(ctx)} 个上下文")

    # ---- ① 稀疏分解：把它真的算出来 ------------------------------------
    # ⚠ 以前**没有这一步**。K_MAX 被当元数据搬了三个文件却没有任何东西读它，
    #   而产物与页面都按「这些句子是这个向量的分解」呈现它。见 _sparse_decomp 上面的说明。
    _sd = d.get("sentence_diffs") or []
    _lev = (d.get("lever") or {}).get("vec")
    decomp, decomp_err = None, None
    if not _sd:
        decomp_err = "原始产物里没有 sentence_diffs，无法分解"
    elif not _lev:
        decomp_err = "原始产物里没有 lever.vec，无法分解"
    else:
        try:
            decomp = _sparse_decomp(_sd, _lev, K_MAX)
        except Exception as e:          # 装置问题照实报，不吞
            decomp_err = f"{type(e).__name__}: {e}"
    if decomp is None:
        log(f"① 稀疏分解失败：{decomp_err}")
    else:
        log(f"① 稀疏分解（全解）：解释 confidence_up@L{_lev and d.get('lever',{}).get('layer')}"
            f" 的 {decomp['explained_energy']*100:.3f}% 能量，残差比 "
            f"{decomp['residual_ratio']:.4f}")
        log(f"   按 |c_k| 前 {K_MAX} 条：{decomp['top_k']}")
        log(f"   其中负对照 {decomp['n_negative_control_in_top_k']} 条 "
            f"（负对照共 {len(decomp['negative_control_keys'])} 条）")
        log(f"   截断后能量 {decomp['top_k_energy']*100:.3f}%"
            "（≠ 全解能量，K_MAX < 轴数时本来就不该相等）")

    # ---- 构建期自检 ------------------------------------------------------
    problems = []
    if d.get("alpha_grid") != ALPHA_GRID:
        problems.append(f"α 网格与预登记不符：{d.get('alpha_grid')}")
    if d.get("fit_alphas") != FIT_ALPHAS:
        problems.append(f"拟合窗与预登记不符：{d.get('fit_alphas')}")
    idbad = [c for c in ctx if not c.get("identity_top1_ok")]
    if idbad:
        problems.append(f"{len(idbad)} 个上下文恒等自证失败（批量化引入了偏差？）")
    if not d.get("sentence_diffs"):
        problems.append("① 的句子差分缺失")
    # ⚠ 判决切片自身的自检。第一版**没有**这条，于是「split.holdout 是空的」
    #   这个事实一路穿过构建器、穿过 GREEN 18/18 的独立重算、最后落进公开产物，
    #   而 G-a 的 claim 明写着「在留出上下文上」——
    #   一个**自相矛盾且无人披露**的产物被发了出去。
    #   ⇒ 切片是判决的前提，不是配置：前提不成立就在这里报，不许留到判决里。
    _h, _e = set(_ho), set(_ex)
    if not _h:
        problems.append("split.holdout 为空：预登记要求在留出集上判，前提不成立")
    if _h & _e:
        problems.append(f"split.extract 与 split.holdout 重叠 {sorted(_h & _e)}")
    _ctx_pids = {c["pid"] for c in ctx}
    if _h - _ctx_pids:
        problems.append(f"留出题在上下文里一个都没出现：{sorted(_h - _ctx_pids)}")
    # ⚠ ① 的稀疏分解：**过程门**，不是结果门。
    #   判的是「它有没有被真的算过」——算过没有、每个轴有没有 c_k、
    #   K_MAX 有没有被用来选子集。这些是**装置完整性**，不需要事后找阈值。
    #   ⚠ 刻意**不**判「解释率够不够高」：预登记表没有为解释率写过任何门槛，
    #     现在看着 7.807% 再补一个门槛，正是「未写死却左右判决」。
    #     那个数原样发进 `decomp` 与 `caveats`，由读者自己判断它意味着什么。
    if decomp is None:
        problems.append(f"① 的稀疏分解没有算出来：{decomp_err}")
    else:
        _axes = decomp["axes"]
        if len(_axes) != len(_sd):
            problems.append(f"① 分解的轴数 {len(_axes)} != sentence_diffs {len(_sd)}")
        if any(a.get("c") is None for a in _axes):
            problems.append("① 分解有轴没有 c_k（最小二乘没跑完？）")
        if len(decomp["top_k"]) != min(K_MAX, len(_sd)):
            problems.append(
                f"① 分解的 top_k 有 {len(decomp['top_k'])} 条，"
                f"应等于 min(K_MAX={K_MAX}, 轴数 {len(_sd)})")
        # K_MAX 必须真的在**选子集**。上一版 K_MAX 只被搬运，
        # 于是「top_k = 全部轴」也能一路绿灯放行 —— 这里显式判它。
        _by_abs = sorted(_axes, key=lambda a: -abs(a["c"]))
        _want = [a["key"] for a in _by_abs[:min(K_MAX, len(_sd))]]
        if list(decomp["top_k"]) != _want:
            problems.append("① 分解的 top_k 不是按 |c_k| 排的（K_MAX 没被用于选子集）")
    log(f"构建期自检：{len(problems)} 条问题 {problems if problems else ''}")

    # ---- 逐上下文：由 gap(α) 推出 g_v，再预测 α* -------------------------
    rows = []
    for c in ctx:
        m_p = float(c["m_p"])
        gap = c["arm_gap"]
        xs = [a for a in FIT_ALPHAS if str(a) in gap]
        ys = [float(gap[str(a)]) for a in xs]
        b, a0 = fit_slope(ys, xs)
        # 斜率 b = d(gap)/dα。gap 收敛到 0 时改口 ⇒ g_v = −b（正 = 会顶开缺口）
        g_v = None if b is None else -b
        pred = None if (g_v is None or g_v <= 0) else m_p / g_v
        meas = c["arm_alpha_star"]
        ctl = c["ctl_alpha_star"]
        ctl_vals = [v for v in ctl.values() if v is not None]
        ctl_min = min(ctl_vals) if ctl_vals else None
        # 拟合窗**不含**改口，否则「预测」是拿答案推答案
        circular = meas is not None and meas <= max(FIT_ALPHAS)
        rows.append({
            "pid": c["pid"], "pos": c["pos"], "tok": c.get("tok"),
            "m_p": m_p, "g_v": g_v, "gap_at_0": a0,
            "alpha_star_pred": pred, "alpha_star_meas": meas,
            "ctl_alpha_star_min": ctl_min, "ctl_all": ctl,
            "circular_fit_window": circular,
            # 逐上下文的切片归属。页面与判决都读它，不各自再判一次。
            "in_judge_slice": c["pid"] in _ho,
        })
    jrows = [r for r in rows if r["in_judge_slice"]]
    if JUDGE_SLICE == "holdout" and not jrows:
        log("装置故障：留出集里一个上下文都没有 ⇒ 无从判决")
        return 2

    # ---- G-a 可预测 ------------------------------------------------------
    # ⚠ 先剔除**前提不成立**的上下文，否则这道门会红在一个不是缺陷的地方。
    #   前提是什么：小 α 段 gap 必须**单调不增**往 0 走 —— 否则线性外推无意义。
    #   实测确实有这类上下文（gap 先微升再塌，如 pos=391：
    #   0.75425 → 0.75481 → 0.75501，然后到 α≥2 才塌到 −0.47）。
    #   ⇒ 这些位置**报 na**，不报 fail：本仓自己的规矩是
    #     「G2 不过的臂，G3-G6 一律标 na —— 报 fail 是伪造结论」，
    #     这里 G-a 的前提没过，形状完全一样。
    #   同时把它们印出来，因为它们**正是 G-a 会失败的那个机理**，两者必须挂钩。
    def monotone_in_fit(c):
        gap = c["arm_gap"]
        ys = [float(gap[str(a)]) for a in FIT_ALPHAS if str(a) in gap]
        return not any(ys[i + 1] > ys[i] + 1e-12 for i in range(len(ys) - 1))

    nonmono = [c for c in _jctx if not monotone_in_fit(c)]
    nonmono_key = {(c["pid"], c["pos"]) for c in nonmono}
    for r in rows:
        r["gap_monotone_in_fit"] = (r["pid"], r["pos"]) not in nonmono_key
    log(f"\nG-a 前置：拟合窗 {FIT_ALPHAS} 内 gap **非单调**的 {len(nonmono)}/{len(_jctx)}"
        f" 个上下文报 na（线性外推的前提不成立）")
    for c in nonmono[:5]:
        g = c["arm_gap"]
        log(f"     ⊘ {c['pid'][-11:]} pos={c['pos']} "
            f"gap: {[round(float(g[str(a)]), 4) for a in FIT_ALPHAS]}")

    judged = [r for r in jrows
              if not r["circular_fit_window"] and r["gap_monotone_in_fit"]]
    censored_fit = [r for r in jrows if r["circular_fit_window"]]
    dropped_nonmono = [r for r in jrows
                       if not r["gap_monotone_in_fit"] and not r["circular_fit_window"]]
    log(f"   改口落在拟合窗内（预测会变成拿答案推答案）的 {len(censored_fit)} 个"
        f"／前提不成立的 {len(dropped_nonmono)} 个 ⇒ 可判 {len(judged)} 个")

    applic = (len(_jctx) - len(nonmono)) / max(len(_jctx), 1)
    log(f"   ⚠ 适用率 {(len(_jctx)-len(nonmono))}/{len(_jctx)} = {applic:.3f}"
        f"（前提不成立的 {len(nonmono)} 个被剔除 ⇒ G-a 只判 {len(judged)} 个）")
    ok_grid, ok_beyond, fail, npred, nmeas, both_cens = 0, 0, [], 0, 0, 0
    for r in judged:
        p, m = r["alpha_star_pred"], r["alpha_star_meas"]
        if p is None:
            npred += 1                       # g_v ≤ 0：这一档顶不开缺口
            if m is not None:
                fail.append((r, "预测为 None（g_v≤0）但实测改了口"))
            continue
        if m is None:
            nmeas += 1                       # 实测在网格内没改口
            if p <= ALPHA_GRID[-1]:
                fail.append((r, f"预测 α*={p:.3g} ≤ 网格上限但实测未改口（右删失）"))
            else:
                both_cens += 1                # 两边都说「要更大的强度」⇒ 一致
            continue
        ip, im = grid_idx(p), grid_idx(m)
        if ip is None:
            # 预测值不在网格上：与实测所在档比较档距
            near = min(range(len(ALPHA_GRID)),
                       key=lambda i: abs(ALPHA_GRID[i] - p))
            ip = near
        if abs(ip - im) <= 1:
            ok_grid += 1
        else:
            fail.append((r, f"预测 α*={p:.3g}（档 {ip}）与实测 {m}（档 {im}）"
                            f"相差 {abs(ip-im)} 档 > 1"))
    va = ok_grid + both_cens
    log(f"   相邻档内命中 {ok_grid}／两边同判右删失 {both_cens}"
        f"／预测不出（g_v≤0）{npred}／实测右删失 {nmeas}／判红 {len(fail)}")
    for r, why in fail[:6]:
        log(f"     ✗ {r['pid'][-11:]} pos={r['pos']} m_p={r['m_p']:.3f} "
            f"g_v={r['g_v']}：{why}")
    put("G-a0", "定律的适用率",
        "拟合窗内 gap 单调不增（线性外推成立）的上下文必须占多数 —— "
        "前提不成立就把该处剔除，会让 G-a 变好看，那正是「改了坏的一处却让"
        "更宽的检查变绿」",
        "pass" if applic >= 2.0 / 3 else "fail",
        {"n_ctx": len(_jctx), "n_monotone": len(_jctx) - len(nonmono),
         "n_nonmonotone": len(nonmono), "applicability": round(applic, 3),
         "threshold": 2 / 3,
         "judge_slice": JUDGE_SLICE,
         "n_ctx_all": len(ctx),
         "nonmonotone_ctx": [{"pid": c["pid"][-11:], "pos": c["pos"],
                              "gap_fit_window": [round(float(c["arm_gap"][str(a)]), 5)
                                                 for a in FIT_ALPHAS]}
                             for c in nonmono]})

    put("G-a", "阈值可预测",
        "在留出上下文上，由 gap(α) 线性拟合出的 g_v 预测的 α*，"
        "与实测 α* 相差不超过一个网格档",
        "pass" if not fail else "fail",
        {"n_judged": len(judged), "n_excluded_fit_window": len(censored_fit),
         "n_excluded_nonmonotone": len(nonmono),
         "n_within_one_notch": ok_grid, "n_both_censored": both_cens,
         "n_pred_none_gv_le0": npred, "n_meas_censored": nmeas,
         "alpha_grid": ALPHA_GRID, "fit_alphas": FIT_ALPHAS,
         "judge_slice": JUDGE_SLICE,
         "fit_window_sensitivity": sensitivity(_jctx),
         "failures": [{"pid": r["pid"], "pos": r["pos"], "m_p": r["m_p"],
                       "g_v": r["g_v"], "pred": r["alpha_star_pred"],
                       "meas": r["alpha_star_meas"], "why": w}
                      for r, w in fail]})

    # ---- G-b 有牙齿 ------------------------------------------------------
    # 判据：该向量的 α* 必须**显著低于**幅度配平随机对照的 α*。
    #
    # ⚠⚠ 第一版的打分**给错了**两处，都会虚增分数或虚减：
    #   ① 「臂没改口 → −1」。可对照也没改口时，那是**两边都没动**，
    #      谈不上谁更有效 —— 算成扣分是把「没反应」当成「不如别人」。
    #   ② 「两边都改口 → 0」。那恰恰是最该比 α* 的情形，
    #      恰恰比出高下的地方，我却放弃了比较。
    # ⇒ 改成按「谁先动」逐上下文配对：
    #     臂动、对照全不动           → +1
    #     臂动、对照也动             → 比 α*：臂更低 +1／更高 −1／相等 0
    #     臂不动、对照也不动         →  0（两边都没反应，无从比较）
    #     臂不动、对照动了           → −1（随机顶动了而杠杆没顶动）
    #   最后对**非零**的那些做符号检验，报 p 值 ——
    #   「净分 > 0」不是显著性，而预登记表要的是「**显著**低于」。
    detail, pos, neg, zeros = [], 0, 0, 0
    for r in jrows:
        s, why = _gb_score(r)
        pos += s > 0
        neg += s < 0
        zeros += s == 0
        detail.append({"pid": r["pid"], "pos": r["pos"], "m_p": r["m_p"],
                       "arm": r["alpha_star_meas"],
                       "ctl": r["ctl_all"], "score": s, "why": why})
    net = pos - neg
    n_eff = pos + neg
    p_two = _gb_sign_p(pos, neg)
    log(f"\nG-b：配对打分  +1 {pos}／−1 {neg}／0 {zeros}"
        f"（切片 {JUDGE_SLICE}，共 {len(jrows)}）⇒ 净 {net}，有效对比 {n_eff}，"
        f"符号检验 p={p_two:.4g}")
    # 并列口径：同一套规则在**别的切片**上的读数。它们不是判决 ——
    #   预登记表 §43/§84/§100 要求判决只在留出集上做。发出来是为了让
    #   「换成别的口径会怎样」可被核对，而不是藏在提交信息里。
    #   ⚠ 数字**现算**，不许手抄进 caveat：手抄的那一份没有任何东西会对账，
    #     口径一改它就静默过期，而它印在读者面前。
    _var = _g_b_variant(rows)
    _var_ho = _g_b_variant(jrows)
    _var_ex = _g_b_variant([r for r in rows if not r["in_judge_slice"]])
    log(f"   （并列口径 · 全量 {len(rows)} 个：+1 {_var['n_plus']}／−1 {_var['n_minus']}"
        f"／0 {_var['n_zero']}，p={_var['sign_test_p']:.4g} —— 不作判决）")
    log(f"   （并列口径 · 抽取集 {_var_ex['n_ctx']} 个：+1 {_var_ex['n_plus']}"
        f"／−1 {_var_ex['n_minus']}／0 {_var_ex['n_zero']}，"
        f"p={_var_ex['sign_test_p']:.4g} —— 不作判决，但**不显著**，须披露）")
    put("G-b", "阈值表有牙齿",
        "该向量的 α* 显著低于幅度配平随机对照的 α*"
        "（对照与该臂偏离 clean 的范数逐节点相等）",
        "pass" if (net > 0 and p_two < 0.05) else "fail",
        {"net": net, "n_plus": pos, "n_minus": neg, "n_zero": zeros,
         "n_ctx": len(jrows), "n_effective": n_eff, "sign_test_p": p_two,
         "alpha": 0.05, "judge_slice": JUDGE_SLICE,
         "control": "幅度配平随机对照，‖偏离‖ 逐节点相等",
         "variant_all_ctx": _var,
         "detail": detail})

    # ---- G-c 名字预测效果 ----------------------------------------------
    # 判决规则在取数**之前**写死于预登记修订 4 ④/⑥b/⑥c 与修订 5，
    # 逐条实现见 _g_c_verdict()（词表从 ltv_behavior 取，不在此另写一份）。
    _beh_path = os.environ.get("BEHAVIOR", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ltv_behavior.json"))
    _gc_verdict, _gc_ev = None, {}
    if not os.path.exists(_beh_path):
        put("G-c", "名字预测效果",
            "S_k 指向的行为必须出现在注入后的可读输出里，"
            "且在未参与抽取的题上仍成立",
            "na", {"reason": "没有 ltv_behavior.json；先跑 ltv_behavior.py"},
            why_na="行为判定器**没跑**：没有 ltv_behavior.json。"
                   "没跑 ≠ 跑了没过。")
    else:
        _beh = json.load(open(_beh_path, encoding="utf-8"))
        _v, _ev, _why = _g_c_verdict(_beh)
        _gc_verdict, _gc_ev = _v, _ev
        put("G-c", "名字预测效果",
            "S_k 指向的行为必须出现在注入后的可读输出里，"
            "且在未参与抽取的题上仍成立",
            _v, _ev, why_na=_why)

    # ---- 自检门 ----------------------------------------------------------
    # ⚠ claim 里加了「① 稀疏分解真算过」。上一版的 S1 只查「句子差分齐全」
    #   —— 而句子差分**本来就是齐的**，① 那一段从探针到产物到页面
    #   全程都按「已经分解过」呈现，实际只做了 d_k 的计算。
    #   「部件存在」与「部件被执行过」是两件事，S1 原来只查了前者。
    put("S1", "自检：α 网格/拟合窗与预登记一致、每个上下文恒等自证过、"
              "① 句子差分齐全且**稀疏分解真算过**",
        "装置不许带着错的口径去报判决，也不许带着没跑过的部件去报判决",
        "pass" if not problems else "fail",
        {"problems": problems, "n_ctx": len(ctx),
         "n_identity_ok": sum(1 for c in ctx if c.get("identity_top1_ok")),
         "decomp_ran": decomp is not None,
         "decomp_error": decomp_err,
         "explained_energy": (decomp or {}).get("explained_energy"),
         "n_negative_control_in_top_k":
             (decomp or {}).get("n_negative_control_in_top_k")})

    # ---- 输出 ------------------------------------------------------------
    # G-c 的披露词**现算**，不许手抄：口径一改它就静默过期，而它印在读者面前。
    _gc_caveat = None
    if _gc_verdict in ("pass", "fail"):
        _pa = _gc_ev.get("per_alpha") or {}
        _dead, _real = [], []
        for _a, _r in _pa.items():
            _t = _r.get("rates") or {}
            (_dead if all(float(x or 0) == 0 for x in _t.values()) else _real).append(_a)
        _fw = ", ".join(
            f"α={_a} 的待测方向臂 {_r['rates']['arm']:.3f} 反而**低于**同范数随机对照 "
            f"{_r['rates']['rand']:.3f}（Δ={_r['d_arm_minus_rand']:+.3f}）"
            for _a, _r in _pa.items() if _r["d_arm_minus_rand"] < 0)
        _gc_caveat = (
            f"G-c「名字预测效果」判 **{_gc_verdict}**：注入 confidence_up 并未让模型"
            f"说出更多 {(_gc_ev.get('primary_key') or '')} 的话"
            + (f"——{_fw}。" if _fw else "。")
            + (f"⚠ 但 α={', '.join(_dead)} 三臂计数**全是 0**：那一档上该词表一次都"
               f"没命中，Δ=0 是「**量不出来**」，**不是**「测出没有差别」——"
               f"不构成证伪。说「这个名字站不住」的证据是上面那些**方向为负**的档。"
               if _dead else "")
            + "⇒ 「低余弦 + 名字预测不成立」两句合起来，"
            "只能推出**这 11 句话撑不起这个向量**，推不出「模型没有自信这个概念」。"
        )
    sd = d.get("sentence_diffs") or []
    public = {
        "schema": "steer3d.ltv/1",
        "prereg": "LTV_PREREG.md（写于取数之前）",
        "lever": d.get("lever"),
        "alpha_grid": ALPHA_GRID,
        "fit_alphas": FIT_ALPHAS,
        "k_max": K_MAX,
        "split": d.get("split"),
        "judge_slice": JUDGE_SLICE,
        "judge_slice_note":
            "G-a0/G-a/G-b 的判决**只**用留出集上的上下文（预登记表 §43/§84/§100-101）。"
            "全量口径的数字在 G-b 的 variant_all_ctx 里并列给出，它**不是判决**。",
        "registry_names": d.get("registry_names"),
        "sentence_diffs": [
            {"key": r["key"], "S": r["S"], "Sp": r["Sp"], "norm": r["norm"],
             "negative_control": r["negative_control"]} for r in sd],
        "decomp": decomp,
        "decomp_error": decomp_err,
        "contexts": rows,
        "gate_order": order,
        "gates": gates,
        "caveats": [
            # ⚠ 第一条从「存在风险」改成**已发生的实测结果**。
            #   上一版写的是「S_k 是人挑的，存在拟合风险，消不掉」——
            #   那是预登记表 §4 的**预警**。预警之后没有人量过这个风险，
            #   于是产物与第 8 屏都按「句子是这个向量的分解」呈现它。
            #   现在真算了，数字是：见 decomp.explained_energy。
            ("① 句子锚定的稀疏分解**上一轮从未被执行过**：探针只算出了 11 条 d_k，"
             "没有求 c_k、没有按 |c_k| 选子集，K_MAX=8 被当元数据搬了三个文件"
             "却没有任何东西读它。本轮补算后，全解只解释 "
             f"{(decomp or {}).get('explained_energy', 0)*100:.3f}% 的杠杆能量"
             f"（残差比 {(decomp or {}).get('residual_ratio', float('nan')):.4f}）；"
             f"按 |c_k| 取前 {K_MAX} 条里有 "
             f"{(decomp or {}).get('n_negative_control_in_top_k')} 条负对照。"
             "⇒ 预登记表 §1 ①「名字可读」这个组成部分**本轮没有交付**，"
             "caveats 不能只写「存在风险」。")
            if decomp else
            ("① 句子锚定的稀疏分解**从未被执行过**，且本轮补算失败：" + str(decomp_err)
             + " ⇒ 预登记表 §1 ①「名字可读」这个组成部分没有交付。"),
            "S_k 是人挑的（预登记表 §4 已声明），存在拟合风险，消不掉。",
            # ⚠ G-c 判 fail 之后，**产物必须自己说这件事**。
            #   老毛病是「产物不说自己哪里没交付」——第 8 屏印着一个
            #   从未执行过的分解当事实，本轮修掉了；同一个毛病不能搬到 G-c 上。
            #   而且这里有一处**必须说清的区分**：α=1.0 与 4.0 三臂全是 0，
            #   Δ=0 是「那个词表一次都没命中、量不出来」，**不是**「测出没有差别」。
            #   真正说「名字站不住」的证据是 α=0.35 那一档 arm 反而**低于**
            #   同范数随机对照。两者混成一句「没测出效果」就是把量不出来
            #   读成了证伪。
            (_gc_caveat if _gc_verdict else "G-c 未测：本轮没有 ltv_behavior.json"),
            "g_v 只在最小三档上拟合；改口落在拟合窗内的上下文一律不判 G-a。",
            "预登记表 §3 把「一档」写成「约 1.7~2.8 倍」，"
            "而本网格的相邻档之比实为 1.43~2.0 —— 按「相邻档」字面执行。",
            "G-a 剔除了两类上下文并各自写明理由：改口落在拟合窗内"
            "（预测会变成拿答案推答案）与拟合窗内 gap 非单调"
            "（线性外推的前提不成立）。两类都记 na，不记 fail。",
            "G-b 的对照是幅度配平随机对照，‖偏离‖ 逐节点相等，"
            "但随机方向在 2048 维里落在数据流形外，可能过度破坏 ⇒ 右删失被"
            "读成「顶不动」，这个混淆消不掉。",
            # ↓ 以下三条是「判决切片」这件事的披露。第一版一条都没有，
            #   而它恰恰是本轮最该被看见的东西。
            f"判决只在**留出集**上做（预登记表 §43/§84/§100-101），"
            f"当前切片 = {JUDGE_SLICE}（{len(_ho)} 题 / {len(_jctx)} 个上下文）。"
            f"第一版在**全量 {len(ctx)} 个**上下文上判，"
            f"其中约一半来自抽取题 —— 而 G-a 的 claim 与预登记表都写着「留出」。",
            f"按留出口径，G-b 的配对是 +1 {_var_ho['n_plus']}／−1 {_var_ho['n_minus']}"
            f"／0 {_var_ho['n_zero']}，符号检验 p={_var_ho['sign_test_p']:.3g}。"
            f"**同一套规则在抽取集上不显著**（+{_var_ex['n_plus']}／−{_var_ex['n_minus']}，"
            f"p={_var_ex['sign_test_p']:.3g}）—— 这不是缺陷，是「这个方向在抽取题上"
            f"效果更弱」的事实，消不掉，也不该被混合口径盖住。",
            "「留出」在本轮是**弱留出**：S_k 的稀疏分解是按句子做的、"
            "与题无关，所以留出集隔离的是「这些题没参与任何拟合」这一点，"
            "而不是「这些题的 S_k 是在别的题上选的」。预登记表 §100 设想的"
            "是逐题选子集，本轮没有那样做。",
        ],
    }
    os.makedirs(os.path.dirname(PUBLIC), exist_ok=True)
    tmp = PUBLIC + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(public, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PUBLIC)

    log(f"\n{'-'*60}")
    for k in order:
        g = gates[k]
        log(f"  {k:<4} {g['verdict'].upper():<5} {g['name']}")
        if g.get("why_na"):
            log(f"        {g['why_na'][:110]}…")
    cnt = {v: sum(1 for k in order if gates[k]["verdict"] == v)
           for v in ("pass", "fail", "na")}
    log(f"  三态计数 {cnt}")
    log(f"  已写出 {PUBLIC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())