"""修订 30 §30.3 的 **E1–E3 判定器**：机械实现，不重新解释判据。

## 判据（取数前写死于预登记 §30.3.1）

> **E1（方向）** 极对齐位点上「Δ 与 `w·U` 同号」的比例 **< 25%**，
> 且 `fisher_exact` 双尾 **p < 0.05**；
> **E2（逐轨迹）** 每条极对齐位点 `≥ 8` 的轨迹上，**负向位点占 ≥ 75%**；
> 至多 **1** 条例外；
> **E3（对照）** 极对齐位点上的 `|Δrand| ≥ |Δmarker|` 比例
> **不高于**其余位点；
> 达不到样本量 ⇒ 报「**无法判定**」，**不报 PASS 也不报 FAIL**。

⚠ 三条都是**带方向/带比例**的判据，不能只问「有没有差异」。

## 与 G1–G4 判定器的差别

本判据处理的是**极对齐带**，地板仍按修订 28 §28.3 的口径修正
**只取 `rel=1.0` 那一档**。极对齐位点**全部**参与判定
（它们本来就过了 `w·ĥ>0` 的入选线），但仍要过**噪声地板** ——
否则「负向」可能只是「在噪声里」。

## 只读

不改任何产物；只读探针产物 + 打印 + 落盘判决。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generalization_verdict import fisher_p, spearman   # noqa: E402

# 取数前定死（§30.3.1）
E1_MAX_AGREE = 0.25       # 同号率上限
E1_MAX_P = 0.05           # Fisher 双尾上限
E2_MIN_PER_TRACK = 8      # 可判门槛
E2_MIN_NEG = 0.75         # 轨迹内负向占比下限
E2_MAX_EXC = 1            # 允许的例外轨迹数
E3_MAX_CTRL = 0.05        # ctrl_ge 比例上限（= 地板隐含的名义率）
E3_NOISY_RATIO = 1.5      # 极对齐带 |Δrand| p95 相对全体的容许倍数
MIN_TOTAL = 20            # 总体样本量下限，低于它报「无法判定」


def sign_agree(d, sgn):
    return (d > 0) == sgn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--all-sites", default=None,
                    help="orthogonality_hi.json：算 E3 的「其余位点」基准用")
    ap.add_argument("--expect-sites", type=int, default=None)
    a = ap.parse_args()

    J = json.loads(Path(a.probe).read_text(encoding="utf-8"))
    rows = J["rows"]
    if not rows:
        raise SystemExit("产物没有位点")
    if a.expect_sites is not None and len(rows) != a.expect_sites:
        raise SystemExit(f"位点数 {len(rows)} != 预期 {a.expect_sites}，拒绝判定")
    sgn = 1 if J["wU_marker"] > 0 else -1

    sites = []
    for r in rows:
        p = r["points"][-1]
        for k in ("d_marker", "d_rand"):
            if not isinstance(p[k], (int, float)):
                raise SystemExit(f"非数值读数：{(r['traj'], r['t'], k, p[k])}")
        sites.append({"traj": r["traj"], "t": r["t"],
                      "aw": abs(r["w_dot_hhat"]),
                      "d": p["d_marker"], "dr": p["d_rand"]})

    # 噪声地板：同档口径（§28.3）
    d = sorted(abs(s["dr"]) for s in sites)
    floor = d[int(0.95 * (len(d) - 1))]
    above = [s for s in sites if abs(s["d"]) > floor]
    n_neg = sum(1 for s in above if not sign_agree(s["d"], sgn))
    agree = len(above) - n_neg
    print(f"极对齐位点 {len(sites)} 个（同档地板 {floor:.4f}），"
          f"超地板 {len(above)} 个")

    res = {"schema": "extreme_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 30 §30.3",
           "input": a.probe, "n_sites": len(sites),
           "floor_same_slice": floor, "n_above": len(above),
           "n_traj": len({s['traj'] for s in sites})}

    # ---- 样本量守卫：达不到就报「无法判定」，不报 FAIL ----
    if len(above) < MIN_TOTAL:
        res["final"] = "无法判定"
        res["why"] = f"超地板位点只有 {len(above)} 个 < {MIN_TOTAL}"
        print(f"⚠ {res['why']} ⇒ 不报 PASS 也不报 FAIL")
        json.dump(res, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return

    # ---- E1 ----
    # ⚠ §30.3 的「Fisher 双尾 p < 0.05」必须先说清**和谁比**，否则不可实现。
    #    这里定为：极对齐位点的同号率 vs 「无方向性」的零假设（同号率 50%）。
    #    Fisher 的第二行取 [n//2, n - n//2] ⇒ 精确二项检验。
    from scipy.stats import fisher_exact      # 判据写的是**双尾**
    half_a, half_b = len(above) // 2, len(above) - len(above) // 2
    orr, p2 = fisher_exact([[agree, n_neg], [half_a, half_b]])
    e1_frac = agree / len(above)
    e1_pass = (e1_frac < E1_MAX_AGREE) and (p2 < E1_MAX_P)
    print(f"\n=== E1：同号率 {agree}/{len(above)} = {e1_frac:.3f}"
          f"（须 < {E1_MAX_AGREE}），vs 无方向性零假设的双尾 Fisher "
          f"p = {p2:.4g}（须 < {E1_MAX_P}）⇒ {'通过' if e1_pass else '不通过'}")
    res["E1"] = {"agree": agree, "n": len(above), "frac": round(e1_frac, 4),
                 "fisher_two_sided_p": p2, "or": orr, "pass": bool(e1_pass),
                 "note": "第二行取 [n//2, n-n//2] ⇒ 精确二项检验（零假设=无方向性）"}

    # ---- E2 ----
    per, n_judge, n_pass, detail = {}, 0, 0, {}
    for tid in sorted({s["traj"] for s in sites}):
        sub = [s for s in above if s["traj"] == tid]
        if len(sub) < E2_MIN_PER_TRACK:
            detail[tid] = {"n": len(sub), "verdict": "不判"}
            continue
        n_judge += 1
        neg = sum(1 for s in sub if not sign_agree(s["d"], sgn))
        frac = neg / len(sub)
        ok = frac >= E2_MIN_NEG
        n_pass += 1 if ok else 0
        detail[tid] = {"n": len(sub), "neg": neg, "neg_frac": round(frac, 3),
                       "verdict": "通过" if ok else "例外"}
    if n_judge == 0:
        e2_verdict, e2_pass = "无法判定", False
    elif n_judge <= E2_MAX_EXC + 1:
        # ---- 修订 33 §33.7：样本量守卫，让判据「有牙齿」----
        # ⚠ 「例外数 ≤k」形式的判据，在 n_judge ≤ k+1 时**恒过**：
        #    最多 k+1 条轨迹 ⇒ 例外数最多 k+1 ⇒ 永远 ≤k。
        #    也就是说 n_judge=1 时，哪怕唯一那条轨迹 100% 正向，照样 PASS
        #    ⇒ 那是「测了但没测到」，比失败更糟，必须报「无法判定」。
        e2_pass = False
        e2_verdict = "无法判定"
        print(f"\n⚠⚠ E2 样本量守卫：可判轨迹只有 {n_judge} 条，"
              f"而允许的例外数是 {E2_MAX_EXC} 条 ⇒ 例外数最多 "
              f"{n_judge} ≤ {E2_MAX_EXC + 1}，本判据对**任何**数据都返回 PASS"
              f"（无牙齿）⇒ 判「无法判定」，不报 PASS")
    else:
        e2_pass = (n_judge - n_pass) <= E2_MAX_EXC
        e2_verdict = "通过" if e2_pass else "不具轨迹间一致性"
    print(f"\n=== E2：可判轨迹 {n_judge} 条，不判 {len(detail) - n_judge} 条，"
          f"负向占比 ≥{E2_MIN_NEG} 的 {n_pass} 条，例外 "
          f"{n_judge - n_pass} 条（须 ≤{E2_MAX_EXC}）⇒ {e2_verdict}")
    res["E2"] = {"n_judge": n_judge, "n_pass": n_pass, "n_skip": len(detail) - n_judge,
                 "max_exc": E2_MAX_EXC, "pass": bool(e2_pass),
                 "verdict": e2_verdict, "per_track": detail,
                 "teeth_ok": bool(n_judge > E2_MAX_EXC + 1),
                 "teeth_note": "修订 33 §33.7：n_judge ≤ max_exc+1 时本判据恒过，"
                               "必须判「无法判定」；teeth_ok=False 即该状态"}

    # ---- E3 ----
    # ---- E3′（修订 31 §31.2：改成有牙齿的版本）----
    # ⚠ 原写法「不高于其余位点」**几乎恒过**：地板本身就是对照臂 |Δrand| 的
    #    p95 ⇒ 至少 95% 的位点 |d_rand| ≤ 地板 < |d_marker|。
    #    现在查两件事：
    #      (a) ctrl_ge 比例 ≤ 5%（紧贴名义率，查有没有异常位点）
    #      (b) **极对齐带的 |Δrand| 95 分位 ≤ 全体的 1.5 倍**
    #          —— 这一条才真的问「极对齐带是不是比别处更吵」。
    ctrl_here = sum(1 for s in above if abs(s["dr"]) >= abs(s["d"]))
    frac_here = ctrl_here / len(above)
    d_here = sorted(abs(s["dr"]) for s in above)
    p95_here = d_here[int(0.95 * (len(d_here) - 1))]
    base = None
    if a.all_sites:
        A = json.loads(Path(a.all_sites).read_text(encoding="utf-8"))
        da = sorted(abs(r["points"][-1]["d_rand"]) for r in A["rows"])
        p95_all = da[int(0.95 * (len(da) - 1))]
        fl = da[int(0.95 * (len(da) - 1))]
        rest = [r for r in A["rows"] if abs(r["points"][-1]["d_marker"]) > fl]
        base = {"floor": fl, "n_above": len(rest), "p95_rand": p95_all,
                "ctrl_ge": sum(1 for r in rest
                               if abs(r["points"][-1]["d_rand"])
                               >= abs(r["points"][-1]["d_marker"])),
                "frac": 0.0}
        base["frac"] = base["ctrl_ge"] / len(rest) if rest else 0.0
    a_ok = frac_here <= E3_MAX_CTRL
    b_ok = (base is None) or (p95_here <= base["p95_rand"] * E3_NOISY_RATIO)
    e3_pass = bool(a_ok and b_ok)
    print(f"\n=== E3′：ctrl_ge {ctrl_here}/{len(above)} = {frac_here:.3f}"
          f"（须 ≤{E3_MAX_CTRL}）⇒ {'过' if a_ok else '不过'}")
    print(f"    极对齐带 |Δrand| 的 p95 = {p95_here:.4f}"
          + (f"，全体基准 {base['p95_rand']:.4f}"
             f"（须 ≤ 其 {E3_NOISY_RATIO} 倍）" if base else "（无基准）")
          + f" ⇒ {'过' if b_ok else '不过'}")
    res["E3"] = {"ctrl_ge": ctrl_here, "n": len(above),
                 "frac": round(frac_here, 4),
                 "p95_rand_here": p95_here,
                 "p95_rand_baseline": base["p95_rand"] if base else None,
                 "noisy_ratio_ok": bool(b_ok),
                 "a_ok": bool(a_ok), "pass": e3_pass,
                 "note": "修订 31 §31.2：原写法几乎恒过（地板即对照臂 p95），已换成 (a)ctrl_ge≤5% + (b)极对齐带 p95 不高于全体 1.5 倍"}

    ok = all([e1_pass, e2_pass, e3_pass])
    res["final"] = "全部通过" if ok else "见逐条"
    print(f"\n最终：{res['final']}")
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()
