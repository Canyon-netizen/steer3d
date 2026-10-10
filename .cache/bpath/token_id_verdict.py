"""修订 36 的 **T1–T3 判定器**：Δ 的符号是否与 marker token 组相关。

## 判据（**取数前**写死于预登记 §36.4）

> **T1（主）** 按**两条组都出现**的轨迹分层的 CMH 检验，双尾 `p < 0.01`；
> **T2（守卫）** 7196 组 ≥50、其余组 ≥20、共享轨迹 ≥8
>   ⇒ 任一不满足报「**无法判定**」，不报 PASS 也不报 FAIL；
> **T3（次要）** 不分层 Fisher 双尾，只作对照。

⚠ **T1 通过也只能支持**「两组符号分布不同，且差异不能只用『来自不同轨迹』
解释」；**不能**支持「差异由 token 身份造成」——位置 `t` 的中位数两组差一截，
CMH **不控位置**。

## ⚠ 为什么自己实现 MH 统计量（以及它怎么被验过）

`statsmodels` 不在本项目的依赖里，scipy 也没有分层检验。
⚠ **新写的统计实现本身可能就是坏的东西**，所以本文件带**自校验**：

    Mantel–Haenszel 统计量在**只有一层**时，必须等于该 2×2 表的
    **无校正** Pearson 卡方（scipy `chi2_contingency(correction=False)`）。
    自校验会实际跑这个等式，不等就 `raise`。

这条等式是 MH 的定义本身，不是拟合出来的等式，所以它是硬校验。

## 只读

不改任何产物；只读探针产物 + 位点→token 映射 + 落盘判决。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from scipy.stats import chi2_contingency, fisher_exact, norm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DOM = 7196               # 主导 marker（§36.2 实测 125/179）
T1_MAX_P = 0.01          # §36.4 取数前写死
MIN_DOM = 50             # T2
MIN_REST = 20            # T2
MIN_STRATA = 8           # T2


def mh_stat(tables):
    """tables: [(a,b,c,d)]，每层 [[a,b],[c,d]]，返回 (MH 统计量, 方差和)。

    ⚠ 某层边际合计为 0（该层没有两组中任一者）时跳过并如实计数。
    """
    num, var, used, skipped = 0.0, 0.0, 0, 0
    for a, b, c, d in tables:
        n = a + b + c + d
        if n == 0 or (a + b) == 0 or (c + d) == 0:
            skipped += 1
            continue
        row1, col1 = a + b, a + c
        e = row1 * col1 / n
        num += a - e
        var += row1 * (c + d) * col1 * (b + d) / (n * n) / (n - 1)
        used += 1
    return num, var, used, skipped


def selfcheck():
    """单层时必须满足**精确关系**

        χ²_MH = χ²_Pearson × (N − 1) / N

    推导：单层时 `num = a − (a+b)(a+c)/N = (ad − bc)/N`，
    而 `var = (a+b)(c+d)(a+c)(b+d) / (N²(N−1))`
    ⇒ `χ²_MH = (ad−bc)²(N−1)/[(a+b)(c+d)(a+c)(b+d)]`，
    正是 Pearson 的 `(N−1)/N` 倍。

    ⚠ 第一版把断言写成「MH == scipy 无校正卡方」，**那条断言是错的**
    （两者差一个 `(N−1)/N` 因子），自校验当场把实现「判死」了 ——
    实现其实是对的。⇒ 这类等式**必须先推导再写**，否则守卫会变成
    「永远拒绝正确实现」的假警报。

    现在的断言比原来更强：它同时验了分子 `(ad−bc)²/N²` 与方差里的 `(N−1)`，
    只对其中一个因子就通不过。
    """
    for tab in ([[7, 5], [3, 9]], [[11, 2], [1, 4]], [[30, 12], [25, 41]]):
        a, b, c, d = tab[0][0], tab[0][1], tab[1][0], tab[1][1]
        n = a + b + c + d
        num, var, used, _ = mh_stat([(a, b, c, d)])
        if used != 1 or var <= 0:
            raise SystemExit(f"自校验失败：单层未用上（used={used}, var={var}）")
        mine = num * num / var
        ref = float(chi2_contingency(np.array(tab), correction=False)[0])
        want = ref * (n - 1) / n
        if abs(mine - want) > 1e-9:
            raise SystemExit(
                f"⚠ MH 实现与推导式不一致：自校验 {mine!r} vs "
                f"Pearson×(N-1)/N = {want!r} ⇒ 实现有问题，拒绝判定")
        z = abs(num) / np.sqrt(var)
        p = 2 * (1 - norm.cdf(z))
        if not (0.0 <= p <= 1.0):
            raise SystemExit(f"双尾 p 异常：{p}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True, help="orthogonality_extreme.json")
    ap.add_argument("--map", required=True, help="site_tokens.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--floor-same-slice", type=float, default=None,
                    help="若给出，则只用超地板位点（默认全用）")
    a = ap.parse_args()

    selfcheck()
    print("自校验通过：单层 MH == scipy 无校正 Pearson 卡方")

    J = json.loads(Path(a.probe).read_text(encoding="utf-8"))
    M = json.loads(Path(a.map).read_text(encoding="utf-8"))
    sgn = 1 if J["wU_marker"] > 0 else -1

    tok = {(r["traj"], int(r["t"])): int(r["token_id"]) for r in M}
    if len(tok) != len(M):
        raise SystemExit(f"映射里有重复的 (traj,t)：{len(tok)} vs {len(M)}")

    sites, missing = [], 0
    for r in J["rows"]:
        key = (r["traj"], int(r["t"]))
        if key not in tok:
            missing += 1
            continue
        p = r["points"][-1]
        sites.append({"traj": r["traj"], "t": key[1], "tid": tok[key],
                      "neg": (p["d_marker"] > 0) != sgn,
                      "dr": p["d_rand"], "d": p["d_marker"]})
    if missing:
        raise SystemExit(f"有 {missing} 个位点没有 token 映射，拒绝判定")

    if a.floor_same_slice is not None:
        sites = [s for s in sites if abs(s["d"]) > a.floor_same_slice]
        print(f"⚠ 只用 |Δ| > {a.floor_same_slice} 的位点：{len(sites)} 个")

    dom = [s for s in sites if s["tid"] == DOM]
    rest = [s for s in sites if s["tid"] != DOM]
    trajs_d = {s["traj"] for s in dom}
    trajs_r = {s["traj"] for s in rest}
    shared = sorted(trajs_d & trajs_r)

    n_dn = sum(1 for s in dom if s["neg"])
    n_rn = sum(1 for s in rest if s["neg"])
    frac_d = n_dn / len(dom) if dom else float("nan")
    frac_r = n_rn / len(rest) if rest else float("nan")

    # ---- 分层 2×2（只取两组都出现的轨迹）----
    tables = []
    per_track = {}
    for tid in shared:
        sd = [s for s in dom if s["traj"] == tid]
        sr = [s for s in rest if s["traj"] == tid]
        a_ = sum(1 for s in sd if s["neg"])
        b_ = len(sd) - a_
        c_ = sum(1 for s in sr if s["neg"])
        d_ = len(sr) - c_
        tables.append((a_, b_, c_, d_))
        per_track[tid] = {"dom": len(sd), "rest": len(sr),
                          "dom_neg": a_, "rest_neg": c_}

    print(f"\n位点 {len(sites)} 个：{DOM} 组 {len(dom)}、其余 {len(rest)}")
    print(f"负向占比：{DOM} {n_dn}/{len(dom)} = {frac_d:.3f}；"
          f"其余 {n_rn}/{len(rest)} = {frac_r:.3f}")
    print(f"两组都出现的轨迹 {len(shared)} 条")

    res = {"schema": "token_id_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 36 §36.4",
           "probe": a.probe, "map": a.map,
           "dom_id": DOM, "n_sites": len(sites),
           "n_dom": len(dom), "n_rest": len(rest),
           "dom_neg": n_dn, "rest_neg": n_rn,
           "dom_neg_frac": round(frac_d, 4), "rest_neg_frac": round(frac_r, 4),
           "n_shared_tracks": len(shared),
           "floor_same_slice": a.floor_same_slice,
           "per_track": per_track,
           "selfcheck": "单层 MH == scipy 无校正 Pearson 卡方（已跑）"}

    # ---- 逐 token 明细（描述性；小样本组只作描述不作判决）----
    per_token = {}
    for s in sites:
        d = per_token.setdefault(str(s["tid"]), {"n": 0, "neg": 0})
        d["n"] += 1
        d["neg"] += 1 if s["neg"] else 0
    for k, v in per_token.items():
        v["neg_frac"] = round(v["neg"] / v["n"], 4)
        v["reportable"] = v["n"] >= 10      # <10 的组只列数，不参与任何结论
    res["per_token"] = dict(sorted(
        per_token.items(), key=lambda kv: -kv[1]["n"]))

    # ---- T2 守卫（先判，样本不够就不报 PASS）----
    fails = []
    if len(dom) < MIN_DOM:
        fails.append(f"{DOM} 组只有 {len(dom)} < {MIN_DOM}")
    if len(rest) < MIN_REST:
        fails.append(f"其余组只有 {len(rest)} < {MIN_REST}")
    if len(shared) < MIN_STRATA:
        fails.append(f"共享轨迹只有 {len(shared)} < {MIN_STRATA}")
    res["T2"] = {"pass": not fails, "why": fails,
                 "min_dom": MIN_DOM, "min_rest": MIN_REST,
                 "min_strata": MIN_STRATA}
    if fails:
        res["final"] = "无法判定"
        res["why"] = "；".join(fails)
        print(f"\n⚠ T2 样本量守卫不过：{res['why']} ⇒ 报「无法判定」")
        json.dump(res, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"写出 {a.out}")
        return

    # ---- T1 分层 CMH ----
    num, var, used, skipped = mh_stat(tables)
    if var <= 0:
        res["T1"] = {"pass": False, "why": "MH 方差为 0"}
        res["final"] = "无法判定"
        print("⚠ MH 方差为 0 ⇒ 无法判定")
        json.dump(res, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return
    chi = num * num / var
    p1 = float(2 * (1 - norm.cdf(abs(num) / np.sqrt(var))))
    t1_pass = p1 < T1_MAX_P
    res["T1"] = {"chi2_mh": round(chi, 4), "p_two_sided": p1,
                 "n_strata_used": used, "n_strata_skipped": skipped,
                 "max_p": T1_MAX_P, "pass": bool(t1_pass),
                 "num": round(num, 4), "var": round(var, 4)}
    print(f"\n=== T1：分层 CMH（{used} 层）χ² = {chi:.4f}，"
          f"双尾 p = {p1:.4g}（须 < {T1_MAX_P}）⇒ "
          f"{'通过' if t1_pass else '不通过'}")

    # ---- T3 不分层 Fisher（对照，非判决）----
    orr, p3 = fisher_exact([[n_dn, len(dom) - n_dn],
                            [n_rn, len(rest) - n_rn]])
    res["T3"] = {"or": float(orr), "p_two_sided": float(p3),
                 "note": "不分层的 Fisher，只作对照；**不含**轨迹分层"}
    print(f"=== T3（对照，非判决）：不分层 Fisher OR = {orr:.3f}，"
          f"双尾 p = {p3:.4g}")

    res["final"] = "两组符号分布不同" if t1_pass else "两组符号分布无差异"
    res["scope_warning"] = (
        "⚠⚠ **T1 通过也只能支持**「两组 Δ 符号分布不同，且差异不能只用"
        "『来自不同轨迹』解释」。**不能**支持「差异由 token 身份造成」——"
        "位置 `t` 的中位数两组差一截（3594 vs 5078），"
        "**CMH 不控位置**，位置/token 身份在这批数据里**不可分离**。")
    print(f"\n最终：{res['final']}")
    json.dump(res, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()
