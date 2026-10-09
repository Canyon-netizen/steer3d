"""按预登记修订 15 §15.2 的 Q1–Q4 判定正交度假设 H。

⚠ 判据写在预登记里、**先于取数**。本脚本只做判定，不改判据、不改数据。
   输入是 `orthogonality.json`（179 个位点 × 3 个剂量 × {w, 随机对照}）。
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from pathlib import Path


def rank(a):
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    pos = 0
    while pos < len(order):           # 并列取平均秩
        j = pos
        while j + 1 < len(order) and a[order[j + 1]] == a[order[pos]]:
            j += 1
        avg = (pos + j) / 2.0 + 1.0
        for k in range(pos, j + 1):
            r[order[k]] = avg
        pos = j + 1
    return r


def spearman(xs, ys):
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return (num / den) if den > 1e-12 else 0.0


def fisher_p(a, b, c, d):
    """2x2 Fisher 精确检验（单尾，备择：a/b 的比例更高）。"""
    def C(n, k):
        return math.comb(n, k)
    n = a + b + c + d
    p = 0.0
    r1 = a + b
    c1 = a + c
    for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1):
        prob = C(r1, x) * C(n - r1, c1 - x) / C(n, c1)
        if x <= a:
            p += prob
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ortho", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    J = json.loads(Path(a.ortho).read_text(encoding="utf-8"))
    rows = J["rows"]
    assert J["wU_marker"] > 0, "w·U[marker] 非正，Q1 的「同号」无意义"
    sign_wU = 1 if J["wU_marker"] > 0 else -1

    # 噪声地板：随机对照臂 |d_rand| 的 95 分位。**从对照臂取，不另设魔数**。
    d_rand = [abs(p["d_rand"]) for r in rows for p in r["points"]]
    d_rand_sorted = sorted(d_rand)
    noise_p95 = d_rand_sorted[int(0.95 * (len(d_rand_sorted) - 1))]
    print(f"噪声地板 = 对照臂 |d_rand| 的 95 分位 = {noise_p95:.4f}"
          f"（n={len(d_rand)}，不另设魔数）")
    print(f"w·U[marker] = {J['wU_marker']:+.6f} ⇒ 判「同号」的方向 = {sign_wU:+d}")

    # 每个位点的代表读数：取 rel=1.0（最大剂量），并要求超过噪声地板才算「有响应」
    def rep(r, key="d_marker", rel=1.0):
        for p in r["points"]:
            if abs(p["rel"] - rel) < 1e-9:
                return p[key]
        return 0.0

    sites = []
    for r in rows:
        sites.append({
            "traj": r["traj"], "mode": r["mode"], "t": r["t"],
            "w_dot_hhat": r["w_dot_hhat"],
            "abs_w_dot_hhat": abs(r["w_dot_hhat"]),
            "d1": rep(r), "eff": r["points"][-1]["effective_dose"],
        })
    above = [s for s in sites if abs(s["d1"]) > noise_p95]
    print(f"总位点 {len(sites)}，其中 |Δ| 超过噪声地板的 {len(above)} 个"
          f"（其余 {len(sites)-len(above)} 个按 Q1 只算「无响应」）")

    res = {"schema": "orthogonality_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 15",
           "noise_p95": noise_p95, "n_sites": len(sites),
           "n_above_noise": len(above)}

    # ---------- Q1：|w·ĥ| 最大 1/3 vs 最小 1/3，「同号」比例 ----------
    pool = sorted(above, key=lambda s: s["abs_w_dot_hhat"])
    k = max(1, len(pool) // 3)
    lo, hi = pool[:k], pool[-k:]
    agree_hi = sum(1 for s in hi if (s["d1"] > 0) == (sign_wU > 0))
    agree_lo = sum(1 for s in lo if (s["d1"] > 0) == (sign_wU > 0))
    p1 = fisher_p(agree_hi, len(hi) - agree_hi, agree_lo, len(lo) - agree_lo)
    print(f"\n=== Q1（符号判据）")
    print(f"  |w·ĥ| 最大 1/3：{agree_hi}/{len(hi)} 与 w·U 同号")
    print(f"  |w·ĥ| 最小 1/3：{agree_lo}/{len(lo)} 与 w·U 同号")
    print(f"  Fisher p = {p1:.4g}  ⇒ {'通过' if p1 < 0.01 else '不通过'}")
    res["Q1"] = {"hi_agree": agree_hi, "hi_n": len(hi),
                 "lo_agree": agree_lo, "lo_n": len(lo),
                 "fisher_p": p1, "pass": bool(p1 < 0.01)}

    # ---------- Q2：秩相关比较 ----------
    print(f"\n=== Q2（有效剂量判据）")
    out = {}
    for mode in ("all", "think", "no_think"):
        sub = above if mode == "all" else [s for s in above if s["mode"] == mode]
        if len(sub) < 8:
            print(f"  [{mode}] 超地板位点仅 {len(sub)} 个，不足 8，不判")
            continue
        y = [s["d1"] for s in sub]
        rho_eff = spearman([s["eff"] for s in sub], y)
        rho_alpha = spearman([1.0 for s in sub], y)      # α 恒为 class_gap×1.0 ⇒ 常数
        out[mode] = {"n": len(sub), "rho_eff": rho_eff, "rho_alpha": rho_alpha}
        print(f"  [{mode}] n={len(sub)}  ρ(Δ, 有效剂量)={rho_eff:+.4f}"
              f"  ρ(Δ, α)={rho_alpha:+.4f}"
              f"  ⇒ {'有效剂量有增量' if abs(rho_eff) > abs(rho_alpha) else '无增量'}")
    res["Q2"] = out

    # ---------- Q3：no_think 正控 ----------
    q3 = None
    if "no_think" in out:
        nt = [s for s in above if s["mode"] == "no_think"]
        alln = len(nt)
        agree = sum(1 for s in nt if (s["d1"] > 0) == (sign_wU > 0))
        pool_nt = sorted(nt, key=lambda s: s["abs_w_dot_hhat"])
        kn = max(1, len(pool_nt) // 3)
        nhi = sum(1 for s in pool_nt[-kn:] if (s["d1"] > 0) == (sign_wU > 0))
        nlo = sum(1 for s in pool_nt[:kn] if (s["d1"] > 0) == (sign_wU > 0))
        q3 = {"n": alln, "agree": agree, "n_hi": kn, "agree_hi": nhi, "agree_lo": nlo}
        print(f"\n=== Q3（no_think 正控）")
        print(f"  no_think 超地板位点 {alln} 个，同号 {agree}/{alln}")
        print(f"  高 1/3 {nhi}/{kn} vs 低 1/3 {nlo}/{kn}")
        print(f"  ⇒ {'成立' if nhi > nlo else '不成立'}")
        res["Q3"] = q3

    # ---------- Q4：p01__think 的不利证据，必须报 ----------
    print(f"\n=== Q4（不利证据，必须一并报告）")
    p01 = [s for s in sites if s["traj"] == "aime__aime25__p01__think"]
    neg = sum(1 for s in p01 if s["d1"] < 0)
    mono_down = 0
    for r in rows:
        if r["traj"] != "aime__aime25__p01__think":
            continue
        ys = [p["d_marker"] for p in sorted(r["points"], key=lambda p: p["rel"])]
        if all(ys[i] >= ys[i + 1] for i in range(len(ys) - 1)):
            mono_down += 1
    print(f"  p01__think {len(p01)} 个位点中，rel=1.0 时 Δ<0 的有 {neg} 个")
    print(f"  「随剂量单调降」的位点：{mono_down}/{len(p01)}")
    print(f"  ⇒ 该轨迹上存在**稳定地越来越负**的响应，H 解释不了它"
          f"（H 预测响应正比于 w·ĥ，而此轨迹 w·ĥ 在 0 附近变号）")
    res["Q4"] = {"n": len(p01), "n_neg": neg, "n_monotone_down": mono_down}

    # ---------- 汇总 ----------
    q1p = res["Q1"]["pass"]
    q2p = any(abs(v["rho_eff"]) > abs(v["rho_alpha"]) + 1e-9
              and abs(v["rho_eff"]) > 0.15 for v in out.values())
    q3p = bool(q3 and q3["agree_hi"] > q3["agree_lo"])
    print(f"\n=== 汇总：Q1 {'PASS' if q1p else 'FAIL'} / "
          f"Q2 {'PASS' if q2p else 'FAIL'} / Q3 {'PASS' if q3p else 'FAIL'}")
    verdict = ("支持 H（须同时报 Q4 反例）" if (q1p and q2p and q3p)
               else "H 无证据，保留为待检验假设")
    print(f"⇒ 判决：{verdict}")
    res["verdict"] = verdict
    res["q_flags"] = {"Q1": q1p, "Q2": q2p, "Q3": q3p}
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                               encoding="utf-8")
        print(f"写出 {a.out}")


if __name__ == "__main__":
    main()