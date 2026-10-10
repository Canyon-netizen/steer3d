"""修订 38 的 **M1–M3 判定器**：「对齐度反复」是不是两 token 群体的混合。

## 判据（**取数前**写死于预登记 §38.3）

> **M1（混合存在）** token 构成在四个 `|w·ĥ|` 分位之间**不同**：
>     4×2 齐性 χ²，双尾 `p < 0.01`；
> **M2（组内无形状）** 每个 token 组内，同号率在四分位之间的**极差 ≤ 0.15**；
> **M3（整体 > 组内）** `整体极差 − max(两组内部的极差) ≥ 0.10`。
>
> **M1 ∧ M2 ∧ M3 全成立** ⇒ 支持「倒 U 主要来自混合」；
> **任一不成立** ⇒ **不支持**，并报出是哪一条。

- 主口径：**超地板位点**（与修订 29/33 同口径）；次要：全部位点；
- 样本量守卫：每组每档 **≥ 20** ⇒ 否则「**无法判定**」。

⚠ **M2 用极差而不是 p 值**：`p ≥ 0.05` 的非拒绝很弱；
极差是等价性口径（TOST 式），直接回答「形状有多大」。

## ⚠ 这不是新的判决，是已有数据的**分层再分析**

不跑任何前向；只把 `orthogonality_hi.json` 与 `site_tokens_hi.json`
**按 token 重新分层**再算形状。已发布的判决一个字都不改。

## 只读

不改任何产物；只读产物 + 落盘判决。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from scipy.stats import chi2_contingency

DOM = 7196                    # 修订 37 的主导 marker
M1_MAX_P = 0.01               # §38.3
M2_MAX_RANGE = 0.15           # §38.3
M3_MIN_GAIN = 0.10            # §38.3
MIN_PER_CELL = 20             # §38.3 样本量守卫


def quartile_profile(rows, key):
    """按 `key` 升序切四等份，返回每档的同号率（None = 该档为空）。"""
    k = sorted(rows, key=lambda r: r[key])
    n = len(k)
    out = []
    for i in range(4):
        sub = k[i * n // 4:(i + 1) * n // 4]
        if not sub:
            out.append((0, None))
            continue
        out.append((len(sub),
                    sum(1 for r in sub if r["agree"]) / len(sub)))
    return out


def rng(profile):
    vals = [v for _, v in profile if v is not None]
    return (max(vals) - min(vals)) if len(vals) >= 2 else None


def analyse(rows, key="aw", label=""):
    """返回该口径下的 M1–M3 全部读数与判定。"""
    overall = quartile_profile(rows, key)
    dom = [r for r in rows if r["dom"]]
    rest = [r for r in rows if not r["dom"]]
    p_dom = quartile_profile(dom, key)
    p_rest = quartile_profile(rest, key)

    # ---- 样本量守卫 ----
    cells = ([c for c, _ in p_dom] + [c for c, _ in p_rest])
    guard_fail = []
    if min(cells) < MIN_PER_CELL:
        guard_fail.append(
            f"某组某档只有 {min(cells)} 个位点 < {MIN_PER_CELL}")

    # ---- M1 混合存在（4×2 齐性）----
    # ⚠ 分档计数必须与 quartile_profile **用同一套切法**（先按 key 升序，
    #    再 `i*n//4` 切片）。早先这里先写了一个「用 rows[i::4]」的版本，
    #    紧接着被下面的正确版本覆盖 —— 死代码，且一旦有人把覆盖删掉就会
    #    得到**与主表不一致**的构成表。⇒ 只保留一处。
    k = sorted(rows, key=lambda r: r[key])
    n = len(k)
    tab = np.array([[sum(1 for r in k[i * n // 4:(i + 1) * n // 4] if r["dom"]),
                     sum(1 for r in k[i * n // 4:(i + 1) * n // 4]
                         if not r["dom"])] for i in range(4)])
    if tab.min() == 0 or tab.sum() == 0:
        m1_p, m1_chi = None, None
        m1_pass = False
    else:
        m1_chi, m1_p, _, _ = chi2_contingency(tab, correction=False)
        m1_pass = bool(m1_p < M1_MAX_P)

    r_dom, r_rest = rng(p_dom), rng(p_rest)
    m2_pass = bool(r_dom is not None and r_rest is not None
                   and r_dom <= M2_MAX_RANGE and r_rest <= M2_MAX_RANGE)
    r_all = rng(overall)
    inner = max([x for x in (r_dom, r_rest) if x is not None], default=None)
    gain = (r_all - inner) if (r_all is not None and inner is not None) else None
    m3_pass = bool(gain is not None and gain >= M3_MIN_GAIN)

    if guard_fail:
        final = "无法判定"
    elif m1_pass and m2_pass and m3_pass:
        final = "支持：倒 U 主要来自混合"
    else:
        bad = [k2 for k2, v in (("M1", m1_pass), ("M2", m2_pass),
                                ("M3", m3_pass)) if not v]
        final = "不支持（未成立：" + "、".join(bad) + "）"

    return {
        "caliber": label, "n_sites": len(rows),
        "n_dom": len(dom), "n_rest": len(rest),
        "overall": {"rates": [v for _, v in overall],
                    "n": [c for c, _ in overall], "range": r_all},
        "dom": {"rates": [v for _, v in p_dom],
                "n": [c for c, _ in p_dom], "range": r_dom},
        "rest": {"rates": [v for _, v in p_rest],
                 "n": [c for c, _ in p_rest], "range": r_rest},
        "M1": {"chi2": None if m1_chi is None else round(float(m1_chi), 4),
               "p": None if m1_p is None else float(m1_p),
               "max_p": M1_MAX_P, "pass": m1_pass,
               "composition": tab.tolist()},
        "M2": {"max_range": M2_MAX_RANGE, "dom_range": r_dom,
               "rest_range": r_rest, "pass": m2_pass},
        "M3": {"min_gain": M3_MIN_GAIN, "overall_range": r_all,
               "inner_range": inner, "gain": gain, "pass": m3_pass},
        "guard_fail": guard_fail, "final": final,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-sites", type=int, default=None)
    a = ap.parse_args()

    J = json.loads(Path(a.probe).read_text(encoding="utf-8"))
    M = json.loads(Path(a.map).read_text(encoding="utf-8"))
    sgn = 1 if J["wU_marker"] > 0 else -1
    tok = {(r["traj"], int(r["t"])): int(r["token_id"]) for r in M}
    if len(tok) != len(M):
        raise SystemExit(f"映射里有重复的 (traj,t)：{len(tok)} vs {len(M)}")

    rows = []
    for r in J["rows"]:
        key = (r["traj"], int(r["t"]))
        if key not in tok:
            raise SystemExit(f"{key} 没有 token 映射，拒绝判定")
        p = r["points"][-1]
        rows.append({"traj": r["traj"], "t": key[1], "aw": abs(r["w_dot_hhat"]),
                     "dom": tok[key] == DOM,
                     "agree": (p["d_marker"] > 0) == sgn,
                     "d": p["d_marker"], "dr": p["d_rand"]})
    if a.expect_sites is not None and len(rows) != a.expect_sites:
        raise SystemExit(f"位点数 {len(rows)} != 预期 {a.expect_sites}，拒绝判定")

    # 主口径：超地板（与修订 29/33 同口径）；次要：全部
    floor = sorted(abs(r["dr"]) for r in rows)[int(0.95 * (len(rows) - 1))]
    above = [r for r in rows if abs(r["d"]) > floor]
    print(f"地板 {floor:.4f}；全部 {len(rows)}，超地板 {len(above)}")

    prim = analyse(above, "aw", "超地板（主口径）")
    sec = analyse(rows, "aw", "全部（次要口径）")

    def show(res, name):
        print(f"\n=== {name}（n={res['n_sites']}）")
        o, d, s = res["overall"], res["dom"], res["rest"]
        print("  整体同号率：", [None if v is None else round(v, 3)
                              for v in o["rates"]],
              f"极差 {o['range']:.3f}" if o["range"] is not None else "")
        print("  7196 组   ：", [None if v is None else round(v, 3)
                              for v in d["rates"]],
              f"极差 {d['range']:.3f}" if d["range"] is not None else "")
        print("  其余组    ：", [None if v is None else round(v, 3)
                              for v in s["rates"]],
              f"极差 {s['range']:.3f}" if s["range"] is not None else "")
        m = res["M1"]
        print(f"  M1 混合存在：χ² = {m['chi2']}，p = {m['p']} "
              f"（须 < {M1_MAX_P}）⇒ {'过' if m['pass'] else '不过'}")
        print(f"  M2 组内无形状：极差 {d['range']} / {s['range']}"
              f"（须 ≤ {M2_MAX_RANGE}）⇒ {'过' if res['M2']['pass'] else '不过'}")
        g = res["M3"]["gain"]
        print(f"  M3 整体>组内：{o['range']} − {res['M3']['inner_range']} = "
              f"{None if g is None else round(g, 3)}（须 ≥ {M3_MIN_GAIN}）"
              f" ⇒ {'过' if res['M3']['pass'] else '不过'}")
        if res["guard_fail"]:
            print(f"  ⚠ 守卫：{res['guard_fail']}")
        print(f"  判定：{res['final']}")

    show(prim, "主口径")
    show(sec, "次要口径")

    out = {"schema": "mixture_verdict/1",
           "prereg": "R6_RERUN_PREREG.md 修订 38 §38.3",
           "probe": a.probe, "map": a.map, "dom_id": DOM,
           "floor_same_slice": floor,
           "primary": prim, "secondary": sec,
           "final": prim["final"],
           "note": ("⚠ 这是已有数据的**分层再分析**，不跑任何前向；"
                    "已发布判决一个字不改")}
    json.dump(out, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n写出 {a.out}")


if __name__ == "__main__":
    main()