"""修订 28 的 G1–G4 判定器：**机械实现** §28.3/§28.4，不重新解释判据。

## 与旧判定器的三处**有意不同**（都不是改判据）

1. **噪声地板只取 `rel=1.0` 那一档**（修订 26 F1 的口径修正）。
   ⚠ 只对本批次生效；修订 15–23 的旧判决一律不动。
2. 统计函数（`rank` / `spearman` / `fisher_p`）**从
   `generalization_verdict.py` 导入**，不复制一份 ——
   复制实现就是邀请它漂移（本轮已经在一个手写 Fisher 上栽过：
   它汇总了整个支撑集、恒返回 1.0，是 scipy 把它打回来的）。
3. 样本不足一律报「**无法判定**」，**不报 FAIL**（§28.4 第 6 条 / §17.4 第 3 条）。

## 判据（取数前写死于 §28.3，沿用 §22.2 一字不改）

- G1：`aw` 最大 1/3 的同号率**低于**最小 1/3，且 Fisher `p < 0.01`
- G2：每条超地板 `≥ 8` 的轨迹上方向都为反；允许**至多 1 条**不同向
- G3：`|ρ(Δ, 有效剂量)| ≥ 0.4177`
- G4：`≥ 20%` 的位点随剂量单调降

## 只读

不改任何产物；只读探针产物 + 打印 + 落盘判决。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generalization_verdict import fisher_p, rank, spearman   # noqa: E402

# 取数前定死（§28.3）
P_THRESHOLD = 0.01      # G1 的 Fisher 阈值（沿用 §15/§22）
MIN_PER_TRACK = 8       # G2 的可判门槛（沿用 §17.4 第 3 条）
RHO_OLD = 0.4177        # G3 的对照值（修订 16 think）
MONO_MIN = 0.20         # G4 的阈值（沿用 §22.2）
MAX_DIFF_TRACKS = 1     # G2 允许的不同向轨迹数


def build_sites(rows):
    """只取 rel=1.0 那一档 —— **地板与被判数据必须同档**（修订 26 F1）。"""
    out = []
    for r in rows:
        p = r["points"][-1]
        out.append({"traj": r["traj"], "mode": r["mode"], "t": r["t"],
                    "w": r["w_dot_hhat"], "aw": abs(r["w_dot_hhat"]),
                    "d": p["d_marker"], "dr": p["d_rand"],
                    "eff": p["effective_dose"],
                    "ds": [q["d_marker"] for q in r["points"]]})
    return out


def floor_same_slice(sites):
    """对照臂 |d_rand| 的 95 分位，**只在本批次的同一档上**取。"""
    d = sorted(abs(s["dr"]) for s in sites)
    return d[int(0.95 * (len(d) - 1))], len(d)


def q1(above, sgn):
    pool = sorted(above, key=lambda s: s["aw"])
    k = max(1, len(pool) // 3)
    hi, lo = pool[-k:], pool[:k]
    ah = sum(1 for s in hi if (s["d"] > 0) == (sgn > 0))
    al = sum(1 for s in lo if (s["d"] > 0) == (sgn > 0))
    p = fisher_p(ah, k - ah, al, k - al)
    if ah == al:
        direction = "打平"
    elif ah < al:
        direction = "反"
    else:
        direction = "正"
    return {"hi": ah, "lo": al, "k": k, "fisher_p": p, "direction": direction,
            "pass": bool(ah < al and p < P_THRESHOLD)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-sites", type=int, default=None,
                    help="位点数必须等于此值（预登记 §28.5 写的是 453）")
    a = ap.parse_args()

    J = json.loads(Path(a.probe).read_text(encoding="utf-8"))
    rows = J["rows"]
    if a.expect_sites is not None and len(rows) != a.expect_sites:
        raise SystemExit(f"位点数 {len(rows)} != 预登记的 {a.expect_sites}，拒绝判定")
    if not rows:
        raise SystemExit("产物没有位点")
    for r in rows:
        if not isinstance(r["w_dot_hhat"], (int, float)):
            raise SystemExit(f"w·ĥ 不是数值：{r}")
        for p in r["points"]:
            for k in ("d_marker", "d_rand", "effective_dose"):
                if not isinstance(p[k], (int, float)):
                    raise SystemExit(f"非数值读数：{(r['traj'], r['t'], k, p[k])}")

    sgn = 1 if J["wU_marker"] > 0 else -1
    sites = build_sites(rows)
    floor, n_floor = floor_same_slice(sites)
    above = [s for s in sites if abs(s["d"]) > floor]
    print(f"位点 {len(sites)}，对照臂同档 n={n_floor} ⇒ 噪声地板 = {floor:.4f}")
    print(f"超地板 {len(above)}")

    res = {"schema": "hi_sites_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 28 §28.3/§28.4",
           "input": a.probe, "traj": sorted(J["traj"]),
           "floor_same_slice": floor, "floor_n": n_floor,
           "floor_note": "**只取 rel=1.0 那一档**的对照臂 |d_rand| 95 分位"
                         "（修订 26 F1 的口径修正）；旧批次的地板一律不动",
           "n_sites": len(sites), "n_above": len(above), "by_mode": {}}

    # ---------- G1 ----------
    g1 = q1(above, sgn)
    print(f"\n=== G1：大 1/3 同号 {g1['hi']}/{g1['k']} vs 小 1/3 同号 "
          f"{g1['lo']}/{g1['k']}，Fisher p = {g1['fisher_p']:.4g}")
    print(f"    方向 {g1['direction']} ⇒ {'通过' if g1['pass'] else '不通过'}")
    res["G1"] = g1

    # ---------- G2 ----------
    detail, nbad, njudge, nskip = {}, 0, 0, 0
    for tid in sorted({s["traj"] for s in sites}):
        sub = [s for s in above if s["traj"] == tid]
        if len(sub) < MIN_PER_TRACK:
            detail[tid] = {"n": len(sub), "verdict": "不判"}
            nskip += 1
            continue
        njudge += 1
        pl = sorted(sub, key=lambda s: s["aw"])
        kk = max(1, len(pl) // 3)
        h, l = pl[-kk:], pl[:kk]
        ph = sum(1 for s in h if (s["d"] > 0) == (sgn > 0))
        plo = sum(1 for s in l if (s["d"] > 0) == (sgn > 0))
        rev = ph < plo
        detail[tid] = {"n": len(sub), "hi": ph, "lo": plo, "k": kk,
                       "direction": "反" if rev else ("打平" if ph == plo else "正")}
        nbad += 0 if rev else 1
    print(f"\n=== G2：可判轨迹 {njudge} 条（超地板 ≥{MIN_PER_TRACK}），"
          f"不判 {nskip} 条，不同向 {nbad} 条")
    g2_pass = njudge > 0 and nbad <= MAX_DIFF_TRACKS
    if njudge == 0:
        g2_verdict = "无法判定"
    elif nbad >= 2:
        g2_verdict = "不具轨迹间一致性"
    else:
        g2_verdict = "通过" if g2_pass else "不通过"
    print(f"    ⇒ {g2_verdict}")
    res["G2"] = {"n_judge": njudge, "n_skip": nskip, "n_diff": nbad,
                 "max_allowed": MAX_DIFF_TRACKS, "pass": bool(g2_pass),
                 "verdict": g2_verdict, "per_track": detail}

    # ---------- G3 ----------
    rho = spearman([s["d"] for s in above], [s["eff"] for s in above])
    g3_pass = abs(rho) >= RHO_OLD
    print(f"\n=== G3：ρ(Δ, 有效剂量) = {rho:+.4f}（|ρ| ≥ {RHO_OLD}）"
          f" ⇒ {'通过' if g3_pass else '不通过'}")
    res["G3"] = {"rho_eff": rho, "old": RHO_OLD, "pass": bool(g3_pass)}

    # ---------- G4 ----------
    mono = sum(1 for s in sites
               if len(s["ds"]) >= 2 and all(x > y for x, y in zip(s["ds"], s["ds"][1:])))
    frac = mono / len(sites) if sites else 0.0
    g4_pass = frac >= MONO_MIN
    print(f"\n=== G4：随剂量单调降 {mono}/{len(sites)} = {frac:.2f}"
          f"（≥ {MONO_MIN}）⇒ {'通过' if g4_pass else '不通过'}")
    res["G4"] = {"mono_down": mono, "n": len(sites), "frac": frac,
                 "threshold": MONO_MIN, "pass": bool(g4_pass)}

    # ---------- 汇总（§28.4）----------
    ctrl = sum(1 for s in above if abs(s["dr"]) >= abs(s["d"]))
    res["control_arm"] = {"ctrl_ge": ctrl, "of": len(above)}
    print(f"\n对照组：{ctrl}/{len(above)} 个超地板位点上随机方向动得更多或一样多")
    all_pass = all([g1["pass"], g2_pass, g3_pass, g4_pass])
    res["final"] = "全部通过" if all_pass else "见逐条"
    print(f"最终：{res['final']}")
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()
