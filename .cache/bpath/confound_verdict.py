"""按预登记修订 21 的 C1–C4 检验「位置/轨迹能否解释对齐度」。

⚠ 判据在预登记里**先于取数**写死；本脚本只判定，不改判据、不改数据。
⚠ 全部用已有产物做**重分析**，不跑前向。
⚠ 分组阈值沿用修订 16 原值（`1/3` 分位、`0.1` 正交边界），一律不改。
"""
from __future__ import annotations

import argparse
import json
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


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return (num / den) if den > 1e-12 else 0.0


def resid(y, xs):
    """把 y 对 xs 做一元线性回归，返回残差。"""
    mx, my = st.mean(xs), st.mean(y)
    den = sum((a - mx) ** 2 for a in xs)
    b = (sum((a - mx) * (b - my) for a, b in zip(xs, y)) / den) if den > 1e-12 else 0.0
    return [yy - (my + b * (xx - mx)) for xx, yy in zip(xs, y)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ortho", required=True)
    ap.add_argument("--floor", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    J = json.loads(Path(a.ortho).read_text(encoding="utf-8"))
    rows = [r for r in J["rows"] if r["mode"] == "think"
            and abs(r["points"][-1]["d_marker"]) > a.floor]
    # ⚠ 同批 think 只有两条轨迹，位点极不均衡 —— 这是本修订要检验的东西本身
    trajs = sorted({r["traj"] for r in rows})
    print(f"think 超地板位点 {len(rows)} 个，来自 {len(trajs)} 条轨迹：")
    for tid in trajs:
        n = sum(1 for r in rows if r["traj"] == tid)
        print(f"   {tid:<32} {n} 个")

    w = [r["w_dot_hhat"] for r in rows]
    t = [float(r["t"]) for r in rows]
    d = [r["points"][-1]["d_marker"] for r in rows]
    res = {"schema": "confound_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 21",
           "n": len(rows), "traj": trajs, "by_mode": {}}

    # ---------- C1：w·ĥ 与位置 t 的纠缠 ----------
    rho_wt = spearman(w, t)
    c1 = abs(rho_wt) < 0.30
    print(f"\n=== C1（位置混杂）ρ(w·ĥ, t) = {rho_wt:+.4f}，"
          f"|ρ| = {abs(rho_wt):.4f} ⇒ {'通过' if c1 else '不通过'}")
    res["C1"] = {"rho_w_t": round(rho_wt, 4), "pass": bool(c1)}

    # ---------- C2：逐轨迹内部的方向 ----------
    print("\n=== C2（逐轨迹方向）")
    c2_detail = {}
    c2 = True
    for tid in trajs:
        sub = [r for r in rows if r["traj"] == tid]
        if len(sub) < 8:
            print(f"   {tid:<32} n={len(sub):<3} 不足 8 ⇒ 不判（沿用修订 17 的处置）")
            c2_detail[tid] = {"n": len(sub), "verdict": "不判"}
            c2 = False          # ⚠ 不能算「都过」：有一条是「不判」而非「过」
            continue
        pool = sorted(sub, key=lambda r: abs(r["w_dot_hhat"]))
        k = max(1, len(pool) // 3)
        hi, lo = pool[-k:], pool[:k]
        sgn = 1 if J["wU_marker"] > 0 else -1
        ah = sum(1 for r in hi if (r["points"][-1]["d_marker"] > 0) == (sgn > 0))
        al = sum(1 for r in lo if (r["points"][-1]["d_marker"] > 0) == (sgn > 0))
        direction = "正" if ah > al else ("反" if ah < al else "打平")
        ok = direction == "反"
        c2 = c2 and ok
        print(f"   {tid:<32} n={len(sub):<3} 大1/3 {ah}/{k} vs 小1/3 {al}/{k} "
              f"⇒ {direction} {'✓' if ok else '✗'}")
        c2_detail[tid] = {"n": len(sub), "k": k, "hi": ah, "lo": al,
                          "direction": direction, "ok": ok}
    res["C2"] = {"detail": c2_detail, "pass": bool(c2)}

    # ---------- C3：增量解释力 ----------
    print("\n=== C3（增量解释力）")
    # 轨迹内分位（0..1），用来吸收「轨迹身份」这个维度
    within = []
    for tid in trajs:
        ts = sorted(float(r["t"]) for r in rows if r["traj"] == tid)
        idx = {v: i for i, v in enumerate(ts)}
        for r in rows:
            if r["traj"] == tid:
                within.append(idx[float(r["t"])] / max(1, len(ts) - 1))
    rho_w = spearman(w, d)
    rho_t = spearman(t, d)
    rho_wi = spearman(within, d)
    c3 = abs(rho_w) >= max(abs(rho_t), abs(rho_wi))
    print(f"   |ρ(Δ, w·ĥ)| = {abs(rho_w):.4f}")
    print(f"   |ρ(Δ, t)|   = {abs(rho_t):.4f}")
    print(f"   |ρ(Δ, 轨迹内分位)| = {abs(rho_wi):.4f}")
    print(f"   ⇒ 对齐度{'不劣于' if c3 else '**劣于**'}位置/轨迹 ⇒ "
          f"{'通过' if c3 else '不通过'}")
    res["C3"] = {"rho_w": round(rho_w, 4), "rho_t": round(rho_t, 4),
                 "rho_within": round(rho_wi, 4), "pass": bool(c3)}

    # ---------- C4：剔除位置后，对齐度的残余信号 ----------
    print("\n=== C4（残差判据，最关键）")
    # 先从 w·ĥ 里剔除 t 与轨迹内分位（各自一元回归后取残差），再看它与 Δ 的相关
    w1 = resid(w, t)
    w2 = resid(w1, within)
    rho_res = pearson(w2, d)
    c4 = rho_res < 0 and abs(rho_res) >= 0.20
    print(f"   ρ(w·ĥ | 已剔除 t 与轨迹内分位, Δ) = {rho_res:+.4f}")
    print(f"   ⇒ {'通过（残余信号仍为负且够强）' if c4 else '不通过'}")
    res["C4"] = {"rho_residual": round(rho_res, 4), "pass": bool(c4)}

    # ---------- 汇总 ----------
    if not res["C1"]["pass"]:
        final = ("C1 不过：w·ĥ 与位置显著纠缠 ⇒ 修订 16 的「按对齐度分组」"
                 "前提失效，按 §21.4 做披露式更正")
    elif not c2:
        final = "C1 过、C2 不过：结论只在部分轨迹上成立，不得写成全局性质"
    elif not c4:
        final = "C3 过但 C4 不过：对齐度的信号可被位置完全解释 ⇒ 撤回机制归属"
    else:
        final = "C1–C4 都过：修订 16 的结论维持，且已排除位置与轨迹的混杂"
    print(f"\n=== §21.2 判决：{final}")
    print("⚠ 这是**同一批数据的重分析**，不是独立验证（§21.3）")
    res["final"] = final
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()