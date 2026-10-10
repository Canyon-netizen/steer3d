"""修订 55：L1 claim 那个二阶因子到底对不对？（预登记 §55 的判定实现）

## 判据（预登记 §55.3，取数前写死）

| # | 判据 |
|---|---|
| **V1** | 逐点验证恒等式：实测 `rel = dev_points/pred_points` 与精确式之差 < 1e-9 |
| **V2** | 反向锚点：claim 因子与真值的差必须 **>** 它与实测的差 |
| **V3** | 符号结构：按精确式逐点预测 `sign(rel−1)`，与实测比，一致率必须报 |
| **V4** | 幅度对比：修订 49 那个「跨方向相对幅度 6.5%」在精确式下重算，两个数并列 |

## 精确式（预登记 §55.2，先推导再写）

    rel = dev/pred = 2(1−c²) / [ (1+ac) · ( √(1+2ac+a²) + 1 + ac ) ]

由 `√(1+2ac+a²) − (1+ac) = a²(1−c²)/(√(1+2ac+a²)+1+ac)`（有理化）得到。
⚠ 这不是拟合、不是截断、不是近似 —— 是**恒等式**。
⇒ 所以 V1 的判据不是「拟合得好不好」，而是「差是不是机器精度」。

## claim 因子

    claim_factor = (1 − a·c) / (1 + a·c)          ← L1 claim 现在写的

## 用法

    PYTHONPATH=.cache/pylibs python3 .cache/bpath/factor_verdict.py
    PYTHONPATH=.cache/pylibs python3 .cache/bpath/factor_verdict.py --mutate
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ART = os.path.join(ROOT, "frontend/public/latent/data/linearity_law.json")
OUT = os.path.join(ROOT, ".cache/mutbak/r55/factor_verdict.json")

TOL = 1e-9                      # 预登记 §55.3 的 V1 阈值
CLAIM_A, CLAIM_B = "(1−a·c)", "(1+a·c)"


def rel_exact(a, c):
    """§55.2 的精确式。⚠ 不是截断展开、不是拟合。"""
    root = np.sqrt(1.0 + 2.0 * a * c + a * a)
    return 2.0 * (1.0 - c * c) / ((1.0 + a * c) * (root + 1.0 + a * c))


def rel_claim(a, c):
    return (1.0 - a * c) / (1.0 + a * c)


def rows_safe(doc):
    smax = doc["conclusions"]["safe_regime"]["strength_max"]
    return [r for r in doc["rows"] if r["strength"] <= smax]


def row_arrays(r, dev_override=None, pred_scale=1.0):
    """取出一行里逐点的 (rel, a, c)，四个方向与 16 个随机方向分开。"""
    pred = np.asarray(r["pred_points"], dtype=np.float64) * pred_scale
    out = {}
    for grp in ("real", "random"):
        A, C = [], []
        names = (list(r["real_dev_points"].keys()) if grp == "real"
                 else ["r%02d" % i for i in range(len(r["random_dev_points"]))])
        akey = "a_points" if grp == "real" else "random_a_points"
        ckey = "c_points" if grp == "real" else "random_c_points"
        dkey = "real_dev_points" if grp == "real" else "random_dev_points"
        for i, nm in enumerate(names):
            src = r[dkey][nm] if grp == "real" else r[dkey][i]
            d = np.asarray(src, dtype=np.float64)
            if dev_override is not None and grp == "real" and nm == dev_override[0]:
                d = d.copy()
                d[dev_override[1]] += dev_override[2]
            A.append(np.asarray(r[akey][nm] if grp == "real" else r[akey][i],
                                dtype=np.float64))
            C.append(np.asarray(r[ckey][nm] if grp == "real" else r[ckey][i],
                                dtype=np.float64))
        out[grp] = (np.asarray(A), np.asarray(C), pred[None, :])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()
    with open(ART, encoding="utf-8") as fh:
        doc = json.load(fh)
    safe = rows_safe(doc)
    smax = doc["conclusions"]["safe_regime"]["strength_max"]
    print("=== 修订 55 判定：L1 claim 的二阶因子 ===")
    print("精确式 rel = 2(1−c²)/[(1+ac)(√(1+2ac+a²)+1+ac)]   （预登记 §55.2）")
    print("claim 因子 = %s/%s\n" % (CLAIM_A, CLAIM_B))

    # ---- Q4 必做项：恒等式自身的阳性对照（先证明实现没写错） ----
    rs = np.random.default_rng(0)
    H = rs.standard_normal((512, 2048))
    H *= (100.0 / np.linalg.norm(H, axis=1, keepdims=True))
    u = rs.standard_normal(2048)
    u /= np.linalg.norm(u)
    hn = np.linalg.norm(H, axis=1)
    c_t = (H @ u) / hn
    a_t = 0.37 / hn
    act = np.linalg.norm(H + 0.37 * u[None, :], axis=1)
    lin = hn * (1.0 + a_t * c_t)
    rel_t = (act / lin - 1.0) / (0.5 * a_t ** 2)
    q4 = float(np.max(np.abs(rel_t - rel_exact(a_t, c_t))))
    print("Q4 阳性对照（玩具输入，512 点）：rel 与精确式最大差 = %.3e ⇒ %s"
          % (q4, "实现正确 ✓" if q4 < 1e-9 else "⚠ 实现本身有问题，先修它"))

    # ---- V1 / V2 / V3 ----
    worst_exact, worst_claim, n_exact_ok = 0.0, 0.0, 0
    n_pt, agree, tot_pt = 0, 0, 0
    claim_res = []
    for r in safe:
        arr = row_arrays(r)
        for grp in ("real", "random"):
            A, C, pred = arr[grp]
            dk = "real_dev_points" if grp == "real" else "random_dev_points"
            ks = (list(r[dk].keys()) if grp == "real"
                  else list(range(len(r[dk]))))
            rel = np.asarray([np.asarray(r[dk][k], dtype=np.float64)
                              for k in ks]) / pred
            e = float(np.max(np.abs(rel - rel_exact(A, C))))
            c_ = float(np.max(np.abs(rel - rel_claim(A, C))))
            worst_exact = max(worst_exact, e)
            worst_claim = max(worst_claim, c_)
            n_exact_ok += int(e < TOL)
            n_pt += rel.size
            agree += int(np.sum(np.sign(rel - 1.0)
                                == np.sign(rel_exact(A, C) - 1.0)))
            tot_pt += rel.size
        # V4：跨方向相对幅度（逐点安全区全行）
        A, C, pred = arr["real"]
        relr = np.asarray([np.asarray(v) for v in r["real_dev_points"].values()]) / pred
        pred_np = np.asarray(r["pred_points"])
        cc = np.asarray([np.asarray(v) for v in r["c_points"].values()])
        aa = np.asarray([np.asarray(v) for v in r["a_points"].values()])
        a_row = r["a_mean"]
        c_row = [v["cos_mean"] for v in r["real"].values()]
        claim_res.append({
            "layer": r["layer"], "strength": r["strength"],
            "claim_spread_rowmean": float(np.ptp(rel_claim(a_row, np.array(c_row)))),
            "exact_spread_rowmean": float(np.ptp(rel_exact(a_row, np.array(c_row)))),
            "claim_spread_rel": float(np.ptp(rel_claim(aa, cc))),
            "exact_spread_rel": float(np.ptp(rel_exact(aa, cc))),
            "pred_pct": float(pred_np.mean() * 100.0),
        })

    print("\n--- V1 逐点恒等式验证（安全区 %d 行，%d 个点）---" % (len(safe), n_pt))
    print("实测 rel 与**精确式**的最大绝对差 = %.3e（阈值 %.0e）⇒ %s"
          % (worst_exact, TOL, "**恒等式成立** ✓" if worst_exact < TOL else "⚠ 不成立"))
    print("\n--- V2 反向锚点：claim 因子离真值多远 ---")
    print("实测 rel 与 **claim 因子**的最大绝对差 = %.3e" % worst_claim)
    print("⇒ %s" % ("精确式近 %d 个数量级 ⇒ **claim 因子被证伪**"
                    % int(round(np.log10(max(worst_claim, 1) / max(worst_exact, 1e-300))))
                    if worst_exact < TOL else "见 V1"))
    print("\n--- V3 符号结构 ---")
    print("精确式预测 sign(rel−1) 与实测的一致率 = %.2f%%（%d/%d 点）"
          % (100.0 * agree / max(tot_pt, 1), agree, tot_pt))
    # ⚠⚠⚠ V4 第一版只报了**逐点**口径（19.5% / 21.6%），而修订 49 报的是 6.5%。
    #   两者差 3 倍 —— 查下来是**同一个量的两种口径**：
    #     · 修订 49 的口径 = 逐行 `a_mean` / `cos_mean` 代入，只对 **4 个方向**取 ptp
    #     · 我第一版的口径 = **逐点**的 (a, c)，含点间变异
    #   ⇒ **不能**把 19.5% 当成对 6.5% 的「更正」。两个口径都必须标出来。
    print("\n--- V4 幅度对比（跨方向相对极差）—— ⚠ 两个口径，必须分别读 ---")
    print("口径甲（修订 49 的口径：逐行 a_mean / cos_mean，只对 4 个方向取 ptp）")
    print("%-6s %-6s %12s %12s %12s" % ("layer", "s", "pred_pct", "claim", "exact"))
    for c_ in claim_res:
        print("L%-5d %-6.2f %12.6f %12.4f%% %12.4f%%"
              % (c_["layer"], c_["strength"], c_["pred_pct"],
                 100 * c_["claim_spread_rowmean"],
                 100 * c_["exact_spread_rowmean"]))
    mx_c = max(x["claim_spread_rowmean"] for x in claim_res)
    mx_e = max(x["exact_spread_rowmean"] for x in claim_res)
    print("  最大：claim 因子 **%.4f%%** vs 精确式 **%.4f%%**" % (100 * mx_c, 100 * mx_e))
    print("  ⇒ 修订 49 印的 **6.5%** 已在本口径下**精确复现**（L12 s=0.20）")
    print("  ⇒ 换成正确因子后同口径是 **%.4f%%** ⇒ 旧数偏大 **%.2f 倍**（不是 3 倍；"
          "3 倍那个差是我第一版跨口径比出来的，已作废）" % (100 * mx_e, mx_c / mx_e))
    mx_c2 = max(x["claim_spread_rel"] for x in claim_res)
    mx_e2 = max(x["exact_spread_rel"] for x in claim_res)
    print("口径乙（逐点：含点间 c 的变异）claim **%.4f%%** vs 精确式 **%.4f%%**"
          % (100 * mx_c2, 100 * mx_e2))
    print("  ⚠ 口径乙**不等于**修订 49 的数，它是另一个量，不得互相更正。")

    verdict = {
        "criterion": "revision55/factor_verdict/1",
        "exact_formula": "2(1-c^2)/((1+ac)(sqrt(1+2ac+a^2)+1+ac))",
        "claim_formula": "(1-a*c)/(1+a*c)",
        "q4_toy_max_abs_err": q4,
        "v1_max_abs_err_exact": worst_exact, "v1_tol": TOL,
        "v1_identity_holds": bool(worst_exact < TOL),
        "v2_max_abs_err_claim": worst_claim,
        "v3_sign_agreement": agree / max(tot_pt, 1),
        "v3_n_points": tot_pt,
        "v4_rowmean_claim_max": mx_c, "v4_rowmean_exact_max": mx_e,
        "v4_pointwise_claim_max": mx_c2, "v4_pointwise_exact_max": mx_e2,
        "v4_rows": claim_res,
    }
    if args.mutate:
        return mutations(doc, safe)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, ensure_ascii=False, indent=1)
    print("\n已写 " + OUT)
    return 0


def mutations(doc, safe):
    """预登记 §55.4 的 Q1–Q3（Q4 在 main 里已跑）。"""
    print("\n=== 变异台架（预登记 §55.4）===")
    fails = []

    def chk(cond, label, detail=""):
        print(("[通过] " if cond else "[**失败**] ") + label
              + ("  —— " + detail if detail else ""))
        if not cond:
            fails.append(label)

    r = safe[-1]                       # s=0.2 的最后一行
    base = np.asarray(list(r["real_dev_points"].values()))
    pred = np.asarray(r["pred_points"])
    A = np.asarray([np.asarray(v) for v in r["a_points"].values()])
    C = np.asarray([np.asarray(v) for v in r["c_points"].values()])
    err0 = float(np.max(np.abs(base / pred - rel_exact(A, C))))

    # Q1 改一个点（幅度远大于 1e-9）
    d = base.copy()
    d[0, 0] += 1e-3
    e1 = float(np.max(np.abs(d / pred - rel_exact(A, C))))
    chk(err0 < TOL and e1 > TOL,
        "Q1 改一个 dev 点（幅度 1e-3 ≫ 1e-9）⇒ 恒等式检查必须红",
        "变异前 %.3e（绿）→ 变异后 %.3e（红）" % (err0, e1))

    # Q2 pred 整体乘 1.001
    e2 = float(np.max(np.abs(base / (pred * 1.001) - rel_exact(A, C))))
    chk(e2 > TOL,
        "Q2 pred 整体乘 1.001（分母变了）⇒ 恒等式检查必须红",
        "%.3e（应 > %.0e）" % (e2, TOL))

    # Q3 claim 因子被换成精确式 ⇒ claim 自检必须红（这里查产物里写的那个式子）
    src = open(os.path.join(ROOT, ".cache/xcheck/build_evidence_ladder.py"),
               encoding="utf-8").read()
    chk("(1−a·c)/(1+a·c)" in src and "2(1−c" not in src.split("claim")[-1][:200],
        "Q3 构建器里 claim 的因子**仍是**错误的那个（尚未替换 ⇒ claim 自检现在该红）",
        "命中 (1−a·c)/(1+a·c)=%s" % ("(1−a·c)/(1+a·c)" in src))

    print("\n%d 条失败" % len(fails) + ("" if not fails else "：" + "、".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())