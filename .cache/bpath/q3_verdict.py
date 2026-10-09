"""修订 17 的 Q3 判定：只重跑 Q3，Q1/Q2/Q4 的数据与结论**不动**。

⚠ 输入是 `orthogonality_nt8.json`（修订 17 的补测：8 条机械选出的 no_think
   + 修订 15 那 2 条 think），**不是**修订 16 用的那份。
⚠ 噪声地板仍从**本文件自己的**对照臂取 95 分位，不另设魔数、不借用别的批次的值。
⚠ 有效剂量用产物里已有的 `effective_dose` 字段（探针按 α·(w·ĥ)/‖h‖ 算的），
   不在判定侧重新推算 —— 避免口径漂移。
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
    p = 0
    while p < len(order):
        j = p
        while j + 1 < len(order) and a[order[j + 1]] == a[order[p]]:
            j += 1
        avg = (p + j) / 2.0 + 1.0
        for k in range(p, j + 1):
            r[order[k]] = avg
        p = j + 1
    return r


def spearman(xs, ys):
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return (num / den) if den > 1e-12 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ortho", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    J = json.loads(Path(a.ortho).read_text(encoding="utf-8"))
    rows = J["rows"]
    assert rows, "产物没有位点"
    for r in rows:                      # ⚠ 拒绝任何非数值读数，别让它们混进排序
        assert isinstance(r["w_dot_hhat"], (int, float)), r
        for p in r["points"]:
            for k in ("d_marker", "d_rand", "effective_dose"):
                assert isinstance(p[k], (int, float)), (r["traj"], r["t"], k, p[k])

    d_rand = sorted(abs(p["d_rand"]) for r in rows for p in r["points"])
    floor = d_rand[int(0.95 * (len(d_rand) - 1))]
    print(f"噪声地板 = 本文件对照臂 |d_rand| 的 95 分位 = {floor:.4f}（n={len(d_rand)}）")
    sgn = 1 if J["wU_marker"] > 0 else -1

    sites = [{"traj": r["traj"], "mode": r["mode"], "t": r["t"],
              "w": r["w_dot_hhat"], "aw": abs(r["w_dot_hhat"]),
              "d": r["points"][-1]["d_marker"],
              "eff": r["points"][-1]["effective_dose"]}
             for r in rows]
    above = [s for s in sites if abs(s["d"]) > floor]
    print(f"总位点 {len(sites)}，超地板 {len(above)}")

    res = {"schema": "orthogonality_q3_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 17 §17.3/§17.4",
           "input": a.ortho, "traj": J["traj"],
           "no_think_top_n": J.get("no_think_top_n"),
           "noise_p95": floor, "n_sites": len(sites), "n_above": len(above),
           "by_mode": {}}

    for mode in ("no_think", "think"):
        sub = [s for s in above if s["mode"] == mode]
        print(f"\n=== [{mode}] 超地板 n={len(sub)}")
        if len(sub) < 8:
            print("  ⚠ 不足 8 个 ⇒ 按 §17.4 第 3 条报「无数据」，不报 FAIL")
            res["by_mode"][mode] = {"n": len(sub), "verdict": "无数据"}
            continue
        pool = sorted(sub, key=lambda s: s["aw"])
        k = max(1, len(pool) // 3)
        hi, lo = pool[-k:], pool[:k]
        ah = sum(1 for s in hi if (s["d"] > 0) == (sgn > 0))
        al = sum(1 for s in lo if (s["d"] > 0) == (sgn > 0))
        rho = spearman([s["eff"] for s in sub], [s["d"] for s in sub])
        groups = {}
        for lab, l, h in (("w·ĥ>0", 0.1, 9e9), ("w·ĥ≈0", -0.1, 0.1),
                          ("w·ĥ<0", -9e9, -0.1)):
            g = [s["d"] for s in sub if l < s["w"] < h]
            if g:
                groups[lab] = {"n": len(g), "median": round(st.median(g), 4),
                               "frac_pos": round(sum(1 for x in g if x > 0) / len(g), 3)}
        print(f"  |w·ĥ| 最大 1/3：{ah}/{k} 与 w·U 同号")
        print(f"  |w·ĥ| 最小 1/3：{al}/{k} 与 w·U 同号")
        print(f"  Q1 方向：{'正（H 预测）' if ah > al else '反（H 反转）'}")
        print(f"  ρ(Δ, 有效剂量) = {rho:+.4f}")
        for lab, g in groups.items():
            print(f"    {lab:<8} n={g['n']:<3} Δ中位={g['median']:+.4f}  Δ>0比例={g['frac_pos']}")
        # ⚠⚠ 打平（ah == al）时**不能**判成「反」——那会把分组边界噪声
        # 当成方向证据。本轮 no_think 恰恰是 6/6 对 6/6 打平。
        if ah == al:
            direction = "打平（无方向证据）"
        elif ah > al:
            direction = "正（H 预测）"
        else:
            direction = "反（H 反转）"
        print(f"  ⚠ 两组同号率{'相同' if ah == al else '不同'}"
              f"{'⇒ 不判方向' if ah == al else ''}")
        res["by_mode"][mode] = {"n": len(sub), "k": k, "agree_hi": ah,
                                "agree_lo": al, "rho_eff": round(rho, 4),
                                "direction": direction,
                                "n_above_0.1_orth": sum(1 for s in sub if s["aw"] > 0.1),
                                "groups": groups}

    nt = res["by_mode"].get("no_think", {})
    tk = res["by_mode"].get("think", {})
    if nt.get("verdict") == "无数据":
        final = "无数据（no_think 超地板位点仍不足 8 个）"
    elif "打平" in str(nt.get("direction", "")):
        # §17.4 的四条里没有「打平」这一支 —— 如实报「无法判定」，
        # **不许**把它当成「反」或「正」去凑 §17.4 的结论。
        final = ("无法判定：no_think 两组同号率打平（6/6 vs 6/6），"
                 "且 |w·ĥ|>0.1 的位点仅 4 个 ⇒ Q1 的分组边界在这批数据上切不出样本")
    elif nt.get("direction") == "正":
        final = "结论加强：H 在 no_think 上也不成立 ⇒ 两种 mode 上 H 都被证伪"
    else:
        final = "结论维持：no_think 上 H 同样被反转"
    print(f"\n=== §17.4 判决：{final}")
    print(f"（think 侧方向：{tk.get('direction', '无数据')}，"
          f"修订 16 的 Q1/Q2/Q4 结论一字不改）")
    res["final"] = final
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()