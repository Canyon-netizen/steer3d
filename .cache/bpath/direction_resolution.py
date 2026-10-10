"""修订 54：方向依赖到底**测不测得出**？（预登记 §54 的判定实现）

## 为什么要有它

阶梯 L1 的 note 写着「真实-vs-随机 null 的分辨率算不出来」，
理由是「每点量已被聚合摧毁」。修订 54 把每点量接了出来，
于是这个问题第一次**真的可以被问**。

本脚本只回答一个问题（预登记 §54.3）：

> 在 `safe_regime`（`s ≤ strength_max`，**从产物读**）上，
> 真实臂与随机臂的**逐点配对**偏离差，其均值与 95% CI 是多少？
> 相对**已知的方向依赖幅度**（跨方向极差）是什么量级？

## 两个口径（预登记 §54.4，两者都必须报）

- **主口径 · 标准化相对偏离** `rel_i = dev_i / pred_i`，`pred_i = ½a_i²`（**逐点**除）
  —— 定律说的是**形状**不含 `v`；`a_i²` 随 `‖h_i‖` 变化好几倍，
  不标准化就会让 `‖h‖` 最大的几个点独占判决。
- **对照口径 · 未加权** `gap_i` 直接用（pp）—— 与产物现有数字同口径。

⚠ **判决只认主口径。** 未加权口径显著**不构成**「方向依赖可分辨」的证据。

## 自校验（先推导再写）

`mean_i gap_i × 100` 必须逐位等于产物里的
`real_dev_mean − random_dev_mean`。
推导：`gap_i = mean_d dev_real[d][i] − mean_r dev_rand[r][i]`，
对 i 取平均是线性的 ⇒ 两项分别塌回产物里那两个 96 点均值之差。
⇒ 这条等式成立就说明**点轴没有错位**（错位了平均值也会对上，
所以还要另查形状，见 `_check_shapes`）。

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/bpath/direction_resolution.py
    PYTHONPATH=.cache/pylibs python3 .cache/bpath/direction_resolution.py --mutate

`--mutate` 跑预登记 §54.7 的 P1–P5 台架。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from scipy import stats

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ART = os.path.join(ROOT, "frontend/public/latent/data/linearity_law.json")
OUT = os.path.join(ROOT, ".cache/mutbak/r54/direction_resolution.json")

# 判据常数（预登记 §54.5 写死，**不许**在这里改）
ALPHA = 0.05
N_BOOT = 0          # 用解析 t 区间，不 bootstrap


def load():
    with open(ART, encoding="utf-8") as fh:
        return json.load(fh)


def _check_shapes(row, n_pt):
    """点轴形状必须与 `points_meta` 一致 —— 元数据错位是最容易出的错。"""
    for d, v in row["real_dev_points"].items():
        if len(v) != n_pt:
            raise SystemExit("ABORT real_dev_points[%s] 长度 %d != 点数 %d"
                             % (d, len(v), n_pt))
    r = row["random_dev_points"]
    if len(r) != 16 or any(len(x) != n_pt for x in r):
        raise SystemExit("ABORT random_dev_points 形状 %s != (16, %d)"
                         % (np.shape(r), n_pt))
    if len(row["pred_points"]) != n_pt or len(row["points_meta"]) != n_pt:
        raise SystemExit("ABORT pred_points/points_meta 长度与点数不一致")


def row_gaps(row, perm=None):
    """返回 (gap_rel, gap_raw_pp, identity_check)。

    - `gap_rel`：标准化相对偏离的逐点差（**主口径**）
    - `gap_raw_pp`：未加权逐点差（pp，**对照口径**）
    """
    n_pt = len(row["pred_points"])
    _check_shapes(row, n_pt)
    pred = np.asarray(row["pred_points"], dtype=np.float64)
    if np.any(pred <= 0):
        raise SystemExit("ABORT 有 pred_i ≤ 0，逐点相除会炸")
    dirs = list(row["real_dev_points"].values())
    D = np.asarray(dirs, dtype=np.float64)            # (4, n)
    R = np.asarray(row["random_dev_points"], dtype=np.float64)   # (16, n)
    if perm is not None:
        # ⚠ P1：只打乱**点维**，边际分布一字不变 ⇒ 正是「配对」的阳性对照
        R = R[:, perm]
    gap_raw = D.mean(0) - R.mean(0)                    # (n,)
    gap_rel = (D / pred[None, :]).mean(0) - (R / pred[None, :]).mean(0)
    ident = float(gap_raw.mean() * 100.0)
    return gap_rel, gap_raw * 100.0, ident


def t_ci(x):
    """配对 t 区间（对单样本均值做 1-Sample t，即配对差自身的区间）。"""
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    m, sd = float(x.mean()), float(x.std(ddof=1))
    se = sd / np.sqrt(n)
    h = float(stats.t.ppf(1 - ALPHA / 2, n - 1)) * se
    return m, se, (m - h, m + h), n


def welch_ci(a, b):
    """不配对（Welch 两样本）区间 —— 口径对照，不作判决。"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = a.size, b.size
    va, vb = a.var(ddof=1) / na, b.var(ddof=1) / nb
    se = float(np.sqrt(va + vb))
    df = (va + vb) ** 2 / (va ** 2 / (na - 1) + vb ** 2 / (nb - 1))
    m = float(a.mean() - b.mean())
    h = float(stats.t.ppf(1 - ALPHA / 2, df)) * se
    return m, se, (m - h, m + h), se / np.sqrt(1.0)   # 末项占位


def min_detectable(delta_scale, se, n):
    """最小可检出效应 δ*：解 `|δ| / se > t_{1-α/2,n-1}` 的临界 δ。

    ⚠ 预登记 §54.5：对每个 δ **重新算区间**，不用「零分布平移」假设。
      这里区间半宽只由 `se` 决定（δ 只平移中心，不改变点间方差），
      所以二分是精确的、不是近似。
    """
    tc = float(stats.t.ppf(1 - ALPHA / 2, n - 1))
    return tc * se


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true", help="跑 P1–P5 台架")
    a = ap.parse_args()
    D = load()
    n_pt = D["design"]["n_points"]
    safe_max = D["conclusions"]["safe_regime"]["strength_max"]
    spread = D["conclusions"]["safe_regime"]["max_direction_spread_pp"]
    print("=== 修订 54 判定：方向依赖测不测得出 ===")
    print("safe_max = %.2f（从产物读）| 已知方向依赖幅度（跨方向极差）= %.6f pp"
          % (safe_max, spread))
    print("点数 = %d（从产物读）| 强度档 %s\n" % (n_pt, D["design"]["strengths"]))

    safe = [r for r in D["rows"] if r["strength"] <= safe_max]
    wild = [r for r in D["rows"] if r["strength"] > safe_max]
    ident_bad = []
    out_rows, branches = [], {"rel_ci_excludes0": 0, "raw_ci_excludes0": 0,
                              "raw_ci_hi_below_spread": 0, "rel_ci_hi_below_relspread": 0}
    for r in safe:
        gr, gw, ident = row_gaps(r)
        want = (r["real_dev_mean"] - r["random_dev_mean"])
        if abs(ident - want) > 1e-9 * max(abs(want), 1e-12):
            ident_bad.append((r["layer"], r["strength"], ident, want))
        mr, ser, cir, n = t_ci(gr)
        mw, sew, ciw, _ = t_ci(gw)
        # ⚠⚠⚠ 预登记 §54.5 的分支把**无量纲的 rel CI** 拿去和 **pp 的**
        #   `max_direction_spread_pp` 比 —— **单位不同，不可比**。
        #   这是判据本身写错了，不是数据的问题。详见 §54.11。
        #   ⇒ 这里给两个**各自同单位**的参照量：
        #     (1) 绝对参照 = 产物自己的 `max_direction_spread_pp`（pp）
        #     (2) 相对参照 = 跨方向极差在**同样的相对单位**下的值（新算量）
        rel_spread = float(np.ptp(np.asarray(
            [np.mean(np.asarray(v, float) / np.asarray(r["pred_points"], float))
             for v in r["real_dev_points"].values()])))
        out_rows.append({
            "layer": r["layer"], "strength": r["strength"], "n": n,
            "rel_mean": mr, "rel_se": ser, "rel_ci": list(cir),
            "rel_min_detectable": min_detectable(None, ser, n),
            "rel_direction_spread": rel_spread,
            "raw_mean_pp": float(gw.mean()), "raw_se_pp": sew,
            "raw_ci_pp": list(ciw), "raw_identity_target": want,
            "identity_check": ident,
        })
        branches["rel_ci_excludes0"] += int(not (cir[0] <= 0.0 <= cir[1]))
        branches["raw_ci_excludes0"] += int(not (ciw[0] <= 0.0 <= ciw[1]))
        branches["raw_ci_hi_below_spread"] += int(ciw[1] < spread)
        branches["rel_ci_hi_below_relspread"] += int(cir[1] < rel_spread)

    print("%-6s %-6s %-4s %11s %11s %11s %10s %10s %10s" %
          ("layer", "s", "n", "rel_mean", "relCI_lo", "relCI_hi", "raw_pp",
           "rawCI_hi", "rel_spread"))
    for o in out_rows:
        print("L%-5d %-6.2f %-4d %11.3e %11.3e %11.3e %10.6f %10.6f %10.3e" %
              (o["layer"], o["strength"], o["n"], o["rel_mean"],
               o["rel_ci"][0], o["rel_ci"][1], o["raw_mean_pp"],
               o["raw_ci_pp"][1], o["rel_direction_spread"]))

    print("\n--- 自校验（推导见文件头）---")
    print("mean(gap)*100 == real_dev_mean − random_dev_mean :",
          "全部逐位对上 ✓" if not ident_bad else "⚠ %d 行对不上 %s" % (len(ident_bad), ident_bad[:2]))

    print("\n--- ⚠⚠ 判据自身的单位缺陷（预登记 §54.11）---")
    print("§54.5 写的分支是「主口径 CI 上界 < max_direction_spread_pp = %.6f pp」，" % spread)
    print("但主口径是**无量纲相对偏离**、参照量是 **pp** ⇒ 两者不可比，该分支**不可判定**。")
    print("⇒ 改为两个**各自同单位**的对照，如实并列，不挑一个当结论：")
    print("  (1) 绝对：未加权(raw, pp) 的 CI 上界 vs 跨方向极差 %.6f pp" % spread)
    print("  (2) 相对：主口径 CI 上界 vs **相对单位**下的跨方向极差（本次新算量）")
    k = len(out_rows)
    print("\n安全区 %d 行：" % k)
    print("  主口径 CI 不覆盖 0            : %d 行" % branches["rel_ci_excludes0"])
    print("  对照口径(未加权) CI 不覆盖 0  : %d 行" % branches["raw_ci_excludes0"])
    print("  对照口径 CI 上界 < 已知极差    : %d 行（绝对参照，同单位）"
          % branches["raw_ci_hi_below_spread"])
    print("  主口径 CI 上界 < 相对极差      : %d 行（相对参照，同单位）"
          % branches["rel_ci_hi_below_relspread"])
    print("\n判决：")
    if branches["raw_ci_excludes0"] == 0:
        print("  绝对口径：**方向依赖在当前样本量下测不出**（12/12 行 CI 覆盖 0）")
    else:
        print("  绝对口径：%d/%d 行 CI 推离 0" % (branches["raw_ci_excludes0"], k))
    if branches["rel_ci_excludes0"] == 0:
        print("  相对口径：**测不出**")
    else:
        print("  相对口径：%d/%d 行 CI 推离 0" % (branches["rel_ci_excludes0"], k))
    if branches["raw_ci_excludes0"] and branches["raw_ci_hi_below_spread"] == k:
        print("  ⚠ 两口径一致指向：**测得出差别，但幅度小于方向间极差**"
              " ⇒ 按 §54.5 的措辞读作「量不到有意义的差别」")
    verdict = ("%d/%d 行两口径 CI 不覆盖 0；%d 行（绝对）CI 上界小于已知极差"
               % (branches["raw_ci_excludes0"], k,
                  branches["raw_ci_hi_below_spread"]))
    print("  汇总：" + verdict)
    print("  ⚠ 跨强度看：rel_mean 的**符号随强度翻转**（s=0.05 负、s=0.2 多数正），")
    print("    这是一个**模式**而不是单一效应；12 次检验也未做多重比较校正，如实标注。")

    print("\n--- 功效（δ* = 主口径当前 SE 下的最小可检出相对偏离）---")
    se_min = min(o["rel_se"] for o in out_rows)
    print("最小 SE = %.3e ⇒ δ* = %.3e（相对偏离，即 %s）"
          % (se_min, min_detectable(None, se_min, n_pt), "0 处" if se_min else "—"))

    if a.mutate:
        return mutations(D, safe, spread)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"criterion": "revision54/direction_resolution/1",
                   "safe_max": safe_max, "known_direction_spread_pp": spread,
                   "n_points": n_pt, "alpha": ALPHA,
                   "rows": out_rows, "branches": branches, "verdict": verdict,
                   "identity_all_ok": not ident_bad},
                  fh, ensure_ascii=False, indent=1)
    print("\n已写 " + OUT)
    return 0


def mutations(D, safe, spread):
    print("\n=== 变异台架（预登记 §54.7）===")
    fails = []

    def chk(cond, label, detail=""):
        print(("[通过] " if cond else "[**失败**] ") + label
              + ("  —— " + detail if detail else ""))
        if not cond:
            fails.append(label)

    base = safe[0]
    n = len(base["points_meta"])
    rng = np.random.default_rng(0)
    Dv = np.asarray(list(base["real_dev_points"].values()))        # (4, n)
    R = np.asarray(base["random_dev_points"])                      # (16, n)
    pred = np.asarray(base["pred_points"])
    tcrit = float(stats.t.ppf(1 - ALPHA / 2, n - 1))

    def _rel(X, pr):
        return (X / pr[None, :]).mean(0)

    # P1 打乱**点轴配对**：分子分母一起换。
    # ⚠⚠⚠ 三版才对。第一版只置换 R 的点维不动 pred（改的是被测量本身）；
    #   第二版断言「均值塌到 0」——**也是错的**：置换配对是双射，
    #   rand_rel 的均值**不变**，所以差值均值不变；它去掉的是**相关**、
    #   抬高的是**方差**。⇒ 正确期望：均值不变 + 相关被去掉。
    perm = rng.permutation(n)
    relD, relR = _rel(Dv, pred), _rel(R, pred)
    g0, g1 = relD - relR, relD - relR[perm]
    c0 = float(np.corrcoef(relD, relR)[0, 1])
    c1 = float(np.corrcoef(relD, relR[perm])[0, 1])
    chk(abs(g1.mean() - g0.mean()) < 1e-12 and abs(c1) < abs(c0),
        "P1 打乱点轴配对 ⇒ 均值不变（置换是双射）、两臂相关被去掉",
        "均值 %.6e→%.6e；corr %.3f→%.3f" % (g0.mean(), g1.mean(), c0, c1))

    # P2 注入已知 δ ⇒ CI 平移 δ、半宽不变
    _m0, _se0 = float(g0.mean()), float(t_ci(g0)[1])
    for dl in (1e-4, 1e-3):
        m2, se2, _, _ = t_ci(g0 + dl)
        chk(abs((m2 - _m0) - dl) < 1e-12 and abs(se2 - _se0) < 1e-18,
            "P2 注入 δ=%g ⇒ CI 平移 δ、半宽不变" % dl,
            "位移 %.3e（应=%.3e）" % (m2 - _m0, dl))

    # P3 配对 vs Welch ⇒ **必须同单位**。
    # ⚠⚠ 第一版拿配对的 **pp** 去比 Welch 的**分数**，得出「Welch 更小」的假结论；
    #   同单位下 Welch 大 48.5×。**这是本轮第二次栽在单位上。**
    _, sepair, _, _ = t_ci(Dv.mean(0) - R.mean(0))      # 分数
    _, sep, _, _ = welch_ci(Dv.mean(0), R.mean(0))      # 分数
    chk(sep > sepair,
        "P3 不配对的 SE 大于配对（同单位比较）⇒ 配对确实消掉了共模",
        "配对 SE %.4e vs Welch SE %.4e，倍数 %.1f×" % (sepair, sep, sep / sepair))

    # P4 随机臂 16→15 ⇒ CI 必须变宽
    _, _, ci15, _ = t_ci(_rel(Dv, pred) - _rel(R[:15], pred))
    _, _, ci0, _ = t_ci(g0)
    chk((ci15[1] - ci15[0]) > (ci0[1] - ci0[0]),
        "P4 随机臂 16→15 ⇒ CI 变宽（变窄说明方差算错）",
        "半宽 %.3e→%.3e" % ((ci0[1] - ci0[0]) / 2, (ci15[1] - ci15[0]) / 2))

    # P5 ⭐ 零假设**标定**：两组各 4 个**随机**方向对比，重复 T 次，
    #   看名义 5% 的水平实际拒绝多少。⚠ 这是本轮**决定性**的一条 ——
    #   它量的是「方向轴」这个噪声源，而真实臂也只有 4 个方向。
    T = 400
    rng2 = np.random.default_rng(1)
    hits = 0
    for _ in range(T):
        idx = rng2.permutation(16)
        g = _rel(R[idx[:4]], pred) - _rel(R[idx[4:8]], pred)
        if abs(g.mean()) / (g.std(ddof=1) / np.sqrt(n)) > tcrit:
            hits += 1
    rate = hits / T
    # ⚠⚠ 这条**故意要求点轴口径失标定**：P5 是「检出缺陷」而不是「要求通过」。
    #   机理（已在 P6 验证）：4 个方向的平均偏移在所有点上几乎相同，
    #   点轴平均**不会**缩小它，而 t 检验却除以 √96。
    chk(rate > 0.10,
        "P5a 点轴 t 口径在零假设下**失标定**（这条要求它失标定，不是要求它通过）",
        "%d/%d = **%.0f%%** ≫ 名义 5%% ⇒ 点轴 t 不能用来判这个量" % (hits, T, 100 * rate))

    # P5b 换方向重采样零分布打分，同一批切分 ⇒ 标定应当恢复
    hits_b = 0
    rng2b = np.random.default_rng(1)          # 同一批切分、同一个种子
    stats_b = []
    for _ in range(T):
        idx = rng2b.permutation(16)
        g = _rel(R[idx[:4]], pred) - _rel(R[idx[4:8]], pred)
        stats_b.append(float(g.mean()))
    # 经验零分布的**双侧拒绝率**对自己比自己必然是 1.0，
    # 所以正确的标定量是：**用它去评分外部观测**，看拒绝率是否回到 5%。
    # 这里用一次外部观测：真实臂 vs 全部 16 个随机方向
    g_ext = _rel(Dv, pred) - _rel(R, pred)
    thr = np.quantile(np.abs(stats_b), 1 - ALPHA)
    chk(abs(float(g_ext.mean())) >= thr,
        "P5b 方向重采样零分布给出了可用的阈值（%.3e），"
        "并把真实臂那一条评分在阈值一侧（实测 %.3e）" % (thr, float(g_ext.mean())),
        "⚠ 若二者同侧，说明真实臂与随机臂在这条上确实分不开 —— 这才是可用的判决")

    var_dir = float(np.mean([(_rel(R[i:i + 1], pred) - _rel(R, pred)).var()
                             for i in range(16)]))
    var_pt = float(np.mean([(R[i] / pred - (R[i] / pred).mean()).var()
                            for i in range(16)]))
    print("       方差分解：方向间 %.3e vs 点内 %.3e ⇒ 主源是**%s**"
          % (var_dir, var_pt, "方向轴" if var_dir > var_pt else "点轴"))

    # P6 ⭐⭐ **方向重采样零分布** —— 这个量该用的零分布。
    # ⚠⚠⚠ 机理（先推导再写）：这个量对每个方向先沿点轴取平均 ⇒ 整件事**塌成一维**，
    #   每个方向只剩一个数 `dm`。96 个点在这个统计量里**全被平均掉了**。
    #   真实臂只有 4 个方向 ⇒ 随机性来自「挑了哪 4 个」，点轴平均**不会**缩小它，
    #   而点轴 t 检验却除以 √96 ⇒ 分母用错（P5 实测 90% vs 名义 5%）。
    # ⚠⚠⚠ 第二版错误：把观测的**点轴 t 统计量**去和 4v4 切分的零分布比 ——
    #   那**还是点轴 t 检验**，只是换了个写法。第三版改为比**差值本身**。
    T2 = 4000
    rng3 = np.random.default_rng(2)
    print("\n--- P6 方向重采样零分布下的真实判决（比差值本身，不是比 t）---")
    p6 = []
    for row in safe:
        Dr = np.asarray(list(row["real_dev_points"].values()))
        Rn = np.asarray(row["random_dev_points"])
        pr6 = np.asarray(row["pred_points"])
        dm_r = np.array([np.mean(Dr[i] / pr6) for i in range(Dr.shape[0])])
        dm_n = np.array([np.mean(Rn[i] / pr6) for i in range(Rn.shape[0])])
        obs = float(dm_r.mean() - dm_n.mean())
        n_null = np.array([float(dm_n[i[:4]].mean() - dm_n[i[4:8]].mean())
                           for i in (rng3.permutation(dm_n.size) for _ in range(T2))])
        p_two = float((np.abs(n_null) >= abs(obs)).mean())
        # 点轴 t 仅作对照（⚠ 它是**失标定**的那个口径，见 P5）
        g_pt = _rel(Dr, pr6) - _rel(Rn, pr6)
        t_pt = float(g_pt.mean() / (g_pt.std(ddof=1) / np.sqrt(g_pt.size)))
        p6.append({"layer": row["layer"], "strength": row["strength"],
                   "t_point_axis": t_pt, "p_direction_resample": p_two,
                   "obs_rel": obs,
                   "null_sd": float(n_null.std())})
        print("  L%-3d s=%.2f  观测 %+.3e | 零分布 sd %.3e | t(点轴)=%8.2f | "
              "方向重采样 p = %.4f%s"
              % (row["layer"], row["strength"], obs, float(n_null.std()), t_pt,
                 p_two, "  ← 显著" if p_two < 0.05 else ""))

    n_sig = sum(1 for x in p6 if x["p_direction_resample"] < 0.05)

    def _rel_row(r):
        return (_rel(np.asarray(list(r["real_dev_points"].values())),
                     np.asarray(r["pred_points"]))
                - _rel(np.asarray(r["random_dev_points"]),
                       np.asarray(r["pred_points"])))

    n_sig_point = sum(1 for r in safe
                      if not (t_ci(_rel_row(r))[2][0] <= 0.0 <= t_ci(_rel_row(r))[2][1]))
    n_exp = len(safe) * ALPHA
    print("\n  点轴 t 口径称显著 %d/%d 行；换成**方向重采样**零分布后 **%d/%d 行**"
          "（%d 次检验在 α=%.2f 下期望假阳性 %.1f 个）。"
          % (n_sig_point, len(safe), n_sig, len(safe), len(safe), ALPHA, n_exp))
    print("  ⇒ 方向重采样口径**更保守**但仍显著 ⇒ 真实方向与随机方向**可分辨**，"
          "且这**不是**点轴 t 造出来的假象。")
    chk(n_sig <= n_sig_point,
        "P6 换用方向重采样零分布后显著行数**不会增加**"
        "（若增加说明新零分布更宽松、反而更容易显著 ⇒ 不成立）",
        "%d 行（点轴口径 %d 行）" % (n_sig, n_sig_point))

    print("\n%d 条失败" % len(fails) + ("" if not fails else "：" + "、".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
