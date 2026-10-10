"""位置分层 CMH（预登记 §37.3）—— **产物化**。

⚠ 这是**补充分析，不是预登记判决**。§36.4 已预先声明
「位置/token 身份不可分离」，故按位置分层是为了**查混淆项**，
不是为了给位置/token 谁的结论。本脚本**不输出任何 pass/fail**。

## 为什么以前没有这个产物

§37.3 的表格（`45/46 = 0.978` …、`χ² = 144.86`）与构建器里的
`position_check` 字符串**都只以手写散文存在**，没有任何产物兜底。
改了 `orthogonality_extreme.json` 而忘了改散文，逐字节复算照样通过。
修订 42 把它们接到产物上，并让 `test_docs_token_tables.py` 逐项核对。

## ⚠ 三分位切点的定义会改答案（修订 42 §42.4）

本项目用**秩三分位** `sorted_t[n//3]` 与 `sorted_t[2n//3]`，
得切点 `2934 / 5110`。若改用 `np.percentile(t, 100/3)` 得 `2938.3 / 5105.7`，
中间层的「其余」变成 **13** 而不是 **14** ⇒ §37.3 表里 `2/14 = 0.143`
会变成 `2/13 = 0.154`。

⚠ 两个数只差 0.01，但**格子数变了** —— 按格子数查表的守卫会指向不同的东西。
⇒ 本脚本**必须**把 `cutpoint_def` 写进产物，并且**同时**算出另一种切法
的结果放进 `cutpoint_sensitivity`，让这个脆弱性在产物里可见。

## ⚠ `num` 不是 χ²（修订 42 §42.3）

分层 CMH 是 `[Σ(a−E)]² / ΣV`，**分子必须平方**。本脚本直接调
`token_id_verdict.mh_stat()` —— 修订 42 已把它加固为**在函数内部算好 χ²
再返回**，所以这里拿到的第一个数就是统计量，不会再取错。

## 只读

不改任何既有产物；只读探针产物 + 位点→token 映射 + 落盘。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_id_verdict import mh_stat, selfcheck  # noqa: E402

DOM = 7196               # 主导 marker（§36.2 实测 125/179）
CUTPOINT_DEF = "rank_third"   # sorted_t[n//3] 与 sorted_t[2n//3]


def rank_third(ts):
    """秩三分位切点：`sorted_t[n//3]` 与 `sorted_t[2n//3]`。"""
    s = sorted(ts)
    n = len(s)
    if n < 3:
        raise SystemExit(f"位点只有 {n} 个，三分位没有意义，拒绝出数")
    return s[n // 3], s[2 * n // 3]


def pct_third(ts):
    """另一种切法（`np.percentile`），只写进 `cutpoint_sensitivity`。"""
    return float(np.percentile(ts, 100 / 3)), float(np.percentile(ts, 200 / 3))


def stratify(sites, lo, hi):
    """按 `[t ≤ lo] / [lo < t ≤ hi] / [t > hi]` 分三层并数格子。

    ⚠ 返回的三层**键集合完全一致**（即便某层为空），这样调用方
      不必担心某条路径少一个键。
    """
    bounds = [("low", -float("inf"), lo),
              ("mid", lo, hi),
              ("high", hi, float("inf"))]
    out = []
    for label, a, b in bounds:
        g = [s for s in sites if a < s["t"] <= b]
        d = [s for s in g if s["tid"] == DOM]
        r = [s for s in g if s["tid"] != DOM]
        dn = sum(1 for s in d if s["neg"])
        rn = sum(1 for s in r if s["neg"])
        out.append({
            "label": label,
            "n_sites": len(g),
            "dom_n": len(d), "dom_neg": dn,
            "dom_pos": len(d) - dn,
            "rest_n": len(r), "rest_neg": rn,
            "rest_pos": len(r) - rn,
            "dom_neg_frac": (dn / len(d)) if d else None,
            "rest_neg_frac": (rn / len(r)) if r else None,
        })
    return out


def cell_stats(strata):
    """把三层格子交给 `mh_stat` ⇒ 返回 (χ², p, 层数, 跳过数)。"""
    tables = [(s["dom_neg"], s["dom_pos"], s["rest_neg"], s["rest_pos"])
              for s in strata]
    chi2, num, var, used, skipped = mh_stat(tables)
    if var <= 0:
        raise SystemExit("位置分层方差为 0（某层没有两组中任一者），拒绝出数")
    p = float(2 * (1 - norm.cdf(abs(num) / np.sqrt(var))))
    return chi2, p, used, skipped


def build(probe_path, map_path):
    selfcheck()          # MH 实现自校验（单层 == Pearson×(N−1)/N）
    J = json.loads(Path(probe_path).read_text(encoding="utf-8"))
    M = json.loads(Path(map_path).read_text(encoding="utf-8"))
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
                      "neg": (p["d_marker"] > 0) != sgn})
    if missing:
        raise SystemExit(f"有 {missing} 个位点没有 token 映射，拒绝出数")

    lo, hi = rank_third([s["t"] for s in sites])
    strata = stratify(sites, lo, hi)
    chi2, p, used, skipped = cell_stats(strata)

    # ⚠ 另一种切法：只为了把脆弱性写进产物，**不作判决**。
    a_lo, a_hi = pct_third([s["t"] for s in sites])
    alt = stratify(sites, a_lo, a_hi)

    res = {
        "schema": "pos_strat/1",
        "prereg": "R6_RERUN_PREREG.md 修订 37 §37.3（**补充分析，非预登记判决**）",
        "role": "补充分析：查位置这个混淆项，**不输出 pass/fail**",
        "probe": probe_path,
        "map": map_path,
        "dom_id": DOM,
        "n_sites": len(sites),
        "cutpoint_def": CUTPOINT_DEF,
        "cutpoints": [lo, hi],
        "strata": strata,
        "chi2_mh": round(chi2, 4),
        "p_two_sided": p,
        "n_strata_used": used,
        "n_strata_skipped": skipped,
        "cutpoint_sensitivity": {
            "why": ("切点定义会改格子数：秩三分位得中间层「其余」14，"
                    "np.percentile 得 13 ⇒ 表里 2/14 变 2/13。"
                    "守卫只认 cutpoint_def，不接受其他切法。"),
            "other_def": "np.percentile",
            "other_cutpoints": [a_lo, a_hi],
            "other_strata": alt,
        },
        "scope_warning": (
            "⚠ 位置与 token 在这批语料里共线，本分析**只能**说"
            "「差异在每个位置层里都还在」，**不能**说"
            "「差异由 token 身份造成」"),
        "selfcheck": "mh_stat 的单层自校验已在本进程跑过",
    }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    res = build(a.probe, a.map)

    # ⚠ 守卫全部跑完、结果构好，**才**落盘（修订 40 的教训：
    #   `open()` 先于校验会留下空文件，把病因推到几百行外）。
    for s in res["strata"]:
        if s["dom_n"] == 0 or s["rest_n"] == 0:
            raise SystemExit(
                f"层 {s['label']} 缺组（dom={s['dom_n']}, rest={s['rest_n']}）"
                f"⇒ CMH 无意义，拒绝落盘")
    Path(a.out).write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"自校验通过；位点 {res['n_sites']} 个，"
          f"切点（{res['cutpoint_def']}）= {res['cutpoints']}")
    for s in res["strata"]:
        print(f"  {s['label']:4s} 7196 {s['dom_neg']}/{s['dom_n']} = "
              f"{s['dom_neg_frac']:.3f}   其余 {s['rest_neg']}/{s['rest_n']} = "
              f"{s['rest_neg_frac']:.3f}")
    print(f"位置分层 CMH：χ² = {res['chi2_mh']:.4f}，双尾 p = "
          f"{res['p_two_sided']:.4g}（{res['n_strata_used']} 层）")
    print(f"⚠ 补充分析，**不出判决**。写出 {a.out}")


if __name__ == "__main__":
    main()