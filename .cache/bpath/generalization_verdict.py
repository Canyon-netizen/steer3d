"""按预登记修订 22 §22.2 的 G1–G4 判定「反转」能否推广到独立轨迹。

⚠ 判据在预登记里**先于取数**写死；本脚本只判定，不改判据、不改数据。
⚠ 分组阈值沿用修订 16 原值（`1/3` 分位、`0.1` 正交边界），一律不改。
⚠ 噪声地板从**本批次自己的**对照臂取 95 分位（§22.1「其余设置全部沿用」）。
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from pathlib import Path

OLD_RHO = 0.4177          # 修订 16 的 |ρ(Δ, 有效剂量)|，G3 的比较基准


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


def fisher_p(a, b, c, d):
    def C(n, k):
        return math.comb(n, k)
    n = a + b + c + d
    r1, c1 = a + b, a + c
    p = 0.0
    for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1):
        pr = C(r1, x) * C(n - r1, c1 - x) / C(n, c1)
        if x <= a:
            p += pr
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    J = json.loads(Path(a.fresh).read_text(encoding="utf-8"))
    rows = J["rows"]
    for r in rows:
        assert r["mode"] == "think", "本批次应只有 think 轨迹"
        assert isinstance(r["w_dot_hhat"], (int, float)), r

    d_rand = sorted(abs(p["d_rand"]) for r in rows for p in r["points"])
    floor = d_rand[int(0.95 * (len(d_rand) - 1))]
    print(f"噪声地板 = 本批次对照臂 |d_rand| 的 95 分位 = {floor:.4f}（n={len(d_rand)}）")
    sgn = 1 if J["wU_marker"] > 0 else -1

    above = [{"traj": r["traj"], "t": r["t"], "w": r["w_dot_hhat"],
              "aw": abs(r["w_dot_hhat"]), "d": r["points"][-1]["d_marker"],
              "eff": r["points"][-1]["effective_dose"],
              "pts": sorted(r["points"], key=lambda p: p["rel"])}
             for r in rows if abs(r["points"][-1]["d_marker"]) > floor]
    print(f"总位点 {len(rows)}，超地板 {len(above)}")

    res = {"schema": "generalization_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 22",
           "traj": J["traj"], "excluded": J["think_already_excluded"],
           "noise_p95": floor, "n_sites": len(rows), "n_above": len(above)}

    # ---------- G1 ----------
    pool = sorted(above, key=lambda s: s["aw"])
    k = max(1, len(pool) // 3)
    hi, lo = pool[-k:], pool[:k]
    ah = sum(1 for s in hi if (s["d"] > 0) == (sgn > 0))
    al = sum(1 for s in lo if (s["d"] > 0) == (sgn > 0))
    p1 = fisher_p(ah, k - ah, al, k - al)
    g1 = (ah < al) and p1 < 0.01
    print(f"\n=== G1（推广判据）")
    print(f"  大 1/3 同号 {ah}/{k} vs 小 1/3 同号 {al}/{k}，Fisher p = {p1:.4g}")
    print(f"  方向 {'反（仍成立）' if ah < al else ('正（不再成立）' if ah > al else '打平')}"
          f" ⇒ {'通过' if g1 else '不通过'}")
    res["G1"] = {"hi": ah, "lo": al, "k": k, "fisher_p": p1, "pass": bool(g1)}

    # ---------- G2 ----------
    print(f"\n=== G2（逐轨迹一致性）")
    detail, nbad, nskip = {}, 0, 0
    for tid in J["traj"]:
        sub = [s for s in above if s["traj"] == tid]
        if len(sub) < 8:
            print(f"   {tid:<32} 超地板 {len(sub):>2} 个，<8 ⇒ 不判")
            detail[tid] = {"n": len(sub), "verdict": "不判"}
            nskip += 1
            continue
        pl = sorted(sub, key=lambda s: s["aw"])
        kk = max(1, len(pl) // 3)
        h, l = pl[-kk:], pl[:kk]
        ph = sum(1 for s in h if (s["d"] > 0) == (sgn > 0))
        plo = sum(1 for s in l if (s["d"] > 0) == (sgn > 0))
        direc = "反" if ph < plo else ("正" if ph > plo else "打平")
        if direc != "反":
            nbad += 1
        print(f"   {tid:<32} n={len(sub):>2}  大1/3 {ph}/{kk} vs 小1/3 {plo}/{kk} ⇒ {direc}")
        detail[tid] = {"n": len(sub), "hi": ph, "lo": plo, "direction": direc}
    g2 = nbad <= 1
    print(f"   ⇒ 不同向 {nbad} 条，允许至多 1 条 ⇒ {'通过' if g2 else '不通过'}"
          f"（另有 {nskip} 条不判）")
    res["G2"] = {"detail": detail, "n_opposite": nbad, "n_skip": nskip,
                 "pass": bool(g2)}

    # ---------- G3 ----------
    rho = spearman([s["eff"] for s in above], [s["d"] for s in above])
    g3 = abs(rho) >= OLD_RHO
    print(f"\n=== G3（强度）|ρ(Δ, 有效剂量)| = {abs(rho):.4f} "
          f"vs 旧批次 {OLD_RHO} ⇒ {'通过' if g3 else '不通过'}")
    res["G3"] = {"rho": round(rho, 4), "old": OLD_RHO, "pass": bool(g3)}

    # ---------- G4 ----------
    mono_down = 0
    for r in rows:
        ys = [p["d_marker"] for p in
              sorted(r["points"], key=lambda p: p["rel"])]
        if all(ys[i] >= ys[i + 1] for i in range(len(ys) - 1)):
            mono_down += 1
    frac = mono_down / len(rows)
    g4 = frac >= 0.20
    print(f"\n=== G4（Q4 复现）随剂量单调降的位点 {mono_down}/{len(rows)} "
          f"= {frac:.2f}（阈值 0.20）⇒ {'复现' if g4 else '不复现'}")
    res["G4"] = {"mono_down": mono_down, "n": len(rows), "frac": round(frac, 3),
                 "pass": bool(g4)}

    # ---------- 判决 ----------
    if g1 and g2 and g3:
        final = ("G1、G2、G3 都过：「对齐度反向」在一批 10 条独立 think 轨迹上可复现 "
                 "⇒ 修订 21 §21.9 的限定**解除**")
    elif not g1:
        final = ("G1 不过：按 §22.5 做披露式更正 ——「对齐度反向」是 "
                 "p01_think 的局部性质，不具推广性（只改适用范围，不改数字）")
    elif not g2:
        final = "G2 不过：报「不具轨迹间一致性」，措辞改为「多数轨迹反向、少数不同向」"
    elif not g3:
        final = "G3 不过：报「强度不可推广」，只保留方向结论、不保留幅度"
    else:
        final = "待定"
    g4note = ("G4 通过：旧批次的 Q4 不利证据在新批次复现"
              if g4 else
              "**G4 不复现**：旧批次的 Q4（p01_think 56/133 单调降）"
              "是**该轨迹的特例**，如实披露，不改旧数据")
    print(f"\n=== §22.3 判决：{final}")
    print(f"=== {g4note}")
    res["final"] = final
    res["g4_note"] = g4note
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()