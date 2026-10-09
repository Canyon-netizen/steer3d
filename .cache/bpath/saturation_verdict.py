"""按预登记修订 19 §19.2 的 S1–S4 判定「天花板效应」解释。

⚠ 判据在预登记里**先于取数**写死；本脚本只判定，不改判据、不改数据。
⚠ 两个输入必须**逐位点对齐**：基线来自 `baseline.json`（无注入前向），
   Δ 来自 `orthogonality_nt8.json`（注入前向）。位点按 `(traj, t)` 配对，
   **不重新挑位点**（修订 19 §19.5）。
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
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--ortho", required=True)
    ap.add_argument("--floor", type=float, required=True,
                    help="噪声地板，沿用 orthogonality_nt8.json 的判定值")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    B = json.loads(Path(a.baseline).read_text(encoding="utf-8"))
    O = json.loads(Path(a.ortho).read_text(encoding="utf-8"))
    base = {(r["traj"], r["t"]): r for r in B["rows"]}

    rows = []
    for r in O["rows"]:
        b = base[(r["traj"], r["t"])]
        for k in ("base_marker_lse", "base_real_logit"):
            assert isinstance(b[k], (int, float)), (r["traj"], r["t"], k)
        rows.append({
            "traj": r["traj"], "mode": r["mode"], "t": r["t"],
            "w_dot_hhat": r["w_dot_hhat"],
            "d": r["points"][-1]["d_marker"],
            "base_lse": b["base_marker_lse"],
            "real_is_top1": b["real_is_top1"],
        })
    above = [r for r in rows if abs(r["d"]) > a.floor]
    print(f"总位点 {len(rows)}，超地板 {len(above)}（地板 {a.floor}，沿用正交度批次的值）")

    res = {"schema": "saturation_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 19",
           "n_sites": len(rows), "n_above": len(above),
           "floor": a.floor, "by_mode": {}}

    s1p = s2p = s3p = None
    for mode in ("think", "no_think"):
        sub = [r for r in above if r["mode"] == mode]
        print(f"\n=== [{mode}] 超地板 n={len(sub)}")
        if len(sub) < 8:
            print("  ⚠ 不足 8 ⇒ 按 S4 报「不判」，**不报 FAIL**（沿用修订 17 §17.4 第 3 条）")
            res["by_mode"][mode] = {"n": len(sub), "verdict": "不判"}
            continue
        y = [r["d"] for r in sub]
        rho_base = spearman([r["base_lse"] for r in sub], y)     # S1
        rho_w = spearman([r["w_dot_hhat"] for r in sub], y)     # S3 (i)
        s1 = rho_base < -0.15
        pool = sorted(sub, key=lambda r: r["base_lse"])
        k = max(1, len(pool) // 3)
        hi, lo = pool[-k:], pool[:k]
        nh = sum(1 for r in hi if r["d"] < 0)
        nl = sum(1 for r in lo if r["d"] < 0)
        p2 = fisher_p(nh, k - nh, nl, k - nl)
        s2 = p2 < 0.01 and nh > nl
        print(f"  S1 ρ(Δ, 基线 lse) = {rho_base:+.4f}  ⇒ "
              f"{'通过（显著负）' if s1 else '不通过'}")
        print(f"  S2 基线最高1/3 负 {nh}/{k} vs 最低1/3 负 {nl}/{k}，"
              f"Fisher p = {p2:.4g} ⇒ {'通过' if s2 else '不通过'}")
        print(f"  S3 |ρ(基线)| = {abs(rho_base):.4f}  vs  "
              f"|ρ(w·ĥ)| = {abs(rho_w):.4f}  ⇒ "
              f"{'基线不劣于对齐度' if abs(rho_base) >= abs(rho_w) else '对齐度更强'}")
        s3 = abs(rho_base) >= abs(rho_w)
        # 附带的描述性量：真实 token 是不是 top1（天花板效应的直观对应）
        top1 = sum(1 for r in sub if r["real_is_top1"]) / len(sub)
        hi_top1 = sum(1 for r in hi if r["real_is_top1"]) / len(hi)
        lo_top1 = sum(1 for r in lo if r["real_is_top1"]) / len(lo)
        print(f"     （描述性）真实 token 是 top1 的比例：全 {top1:.2f} / "
              f"基线高组 {hi_top1:.2f} / 低组 {lo_top1:.2f}")
        res["by_mode"][mode] = {
            "n": len(sub), "rho_base": round(rho_base, 4),
            "rho_w": round(rho_w, 4), "S1": bool(s1), "S2": bool(s2),
            "S3": bool(s3), "neg_hi": nh, "neg_lo": nl, "k": k,
            "fisher_p": p2, "top1_all": round(top1, 3),
            "top1_hi": round(hi_top1, 3), "top1_lo": round(lo_top1, 3)}
        if mode == "think":
            s1p, s2p, s3p = s1, s2, s3

    if s1p is None:
        final = "不判（think 超地板位点不足 8 个）"
    elif s1p and s2p and s3p:
        final = ("天花板效应：修订 16 的「反转」应重新解释为**基线饱和的代理**，"
                 "而非方向反了；按修订 19 §19.4 做披露式更正（收窄归因，数字不改）")
    elif not (s1p and s2p):
        final = "饱和解释无证据：修订 16 的结论维持（仍只报现象，不报机制）"
    else:
        final = "基线解释力不优于对齐度：两个解释并列，不宣称任何一个被取代"
    print(f"\n=== §19.3 判决：{final}")
    print("（修订 13–18 的判据、数据与结论一字未改）")
    res["final"] = final
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()