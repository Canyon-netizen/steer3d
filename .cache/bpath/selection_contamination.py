"""修订 40 的 **B1/B2 + A0–A2 判定器**：筛选是否在挑 token？幅度是否被污染？

## 判据（**取数前**写死于预登记 §40.2）

> **B1** 7196 与其余的 `|w·ĥ|` 分布**不同**：Mann–Whitney 双尾 `p < 0.01`；
> **B2** 「高对齐位点」内 7196 的占比**高于**其在**全体 marker 位点**内的占比：
>     Fisher 双尾 `p < 0.01`；
> **A0（前提）** `ρ_obs = Spearman(|w·ĥ|, |Δ|)` 须显著非零（`p < 0.05`），
>     否则报「**不适用**」；
> **A1** 7196 与其余的 `|Δ|` 分布不同：Mann–Whitney 双尾 `p < 0.01`；
> **A2** 把 `|Δ|` 换成**所在 token 组的中位 `|Δ|`**（⇒ 只保留 token 信息、
>     去掉 `aw` 信息），重算 `ρ_null = Spearman(|w·ĥ|, 组中位数)`。
>     **判决**：`|ρ_null| ≥ 0.5 × |ρ_obs|` ⇒ 支持「ρ **主要**由 token 构成决定」。

⚠ **A2 用「替换成组中位数」而不是置换标签**：置换会连
`token → |Δ|` 这条**正是要保留**的关系一起打掉；替换组中位数只去掉
`aw → |Δ|` 的部分 ⇒ 零假设恰好是「幅度里只有 token，没有 aw」。

## 只读

不改任何产物；只读探针 + 映射 + marker 总构成 + 落盘判决。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from scipy.stats import fisher_exact, mannwhitneyu, spearmanr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DOM = 7196
B_MAX_P = 0.01             # B1 / B2
A0_MAX_P = 0.05            # A0 前提
A_MAX_P = 0.01             # A1
A2_COVER = 0.5             # A2 的 0.5 因子
MIN_N_RHO = 8              # 算 ρ 的最小位点数（层内 ρ 也用这个门槛）

# ⚠⚠ **两条落盘路径的键集合必须完全一致**。
# 「A0 不适用」那条路径原本只写 `{pass, why}`，而面板与构建器都按
# 完整结构读 `A1.median_dom` / `A2.cover` ⇒ 换个不显著的数据就整页崩。
# 真数据恰好 A0 适用，所以这缺陷一直没暴露 —— 靠先验夹具逼出来。
A1_KEYS = {"median_dom", "median_rest", "p", "max_p", "pass",
           "applicable", "why"}
A2_KEYS = {"rho_null", "cover", "need_cover", "pass", "applicable",
           "note", "rho_within", "why"}
WHY_NA = "A0 不适用（ρ_obs 不显著，没有可污染的东西）"


def check_keys(res):
    """结构性守卫：落盘前核对键集合，缺一个就 raise（不用 assert，`-O` 会关掉）。"""
    for name, keys in (("A1", A1_KEYS), ("A2", A2_KEYS)):
        got = set(res[name])
        if got != keys:
            raise SystemExit(
                f"{name} 的键集合不对：多 {sorted(got - keys)}、"
                f"缺 {sorted(keys - got)} ⇒ 面板会读到 undefined")
    return res


def dump(res, out):
    """⚠ 两道落盘前守卫，且**校验全部完成之后才碰文件**。

    第一版是 `open(out, "w")` 之后再校验 ⇒ 守卫触发时留下一个**空文件**，
    下游读它得到 `Expecting value: line 1 column 1`，报错现场指向 JSON 解析，
    真正的病因（键集合不对）在几百行之外。
    ⇒ 先 `json.dumps` 成字符串，成功了再一次性写。

    `allow_nan=False` 是第二道：`json.dump` 默认把 inf 写成裸 `Infinity`，
    那是**非法 JSON**，浏览器 `JSON.parse` 会直接抛。
    """
    bad = []

    def scan(o, p="$"):
        if isinstance(o, dict):
            for k, v in o.items():
                scan(v, f"{p}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                scan(v, f"{p}[{i}]")
        elif isinstance(o, float) and not math.isfinite(o):
            bad.append(p)

    scan(res)
    if bad:
        raise SystemExit(f"产物里有非有限数（nan/inf）于 {sorted(set(bad))}"
                         f" ⇒ 拒绝落盘（写出去浏览器 JSON.parse 会抛）")
    text = json.dumps(check_keys(res), ensure_ascii=False, indent=1,
                      allow_nan=False)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--marker-all", required=True,
                    help="count_marker_tokens.py 的输出（B2 的分母）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-sites", type=int, default=None)
    ap.add_argument("--floor-same-slice", type=float, default=None)
    a = ap.parse_args()

    J = json.loads(Path(a.probe).read_text(encoding="utf-8"))
    M = json.loads(Path(a.map).read_text(encoding="utf-8"))
    ALL = json.loads(Path(a.marker_all).read_text(encoding="utf-8"))
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
        rows.append({"traj": r["traj"], "t": key[1],
                     "aw": abs(r["w_dot_hhat"]),
                     "dom": tok[key] == DOM,
                     "d": p["d_marker"], "dr": p["d_rand"]})
    if a.expect_sites is not None and len(rows) != a.expect_sites:
        raise SystemExit(f"位点数 {len(rows)} != 预期 {a.expect_sites}，拒绝判定")

    # ⚠ 分母对账：逐轨迹 marker 数之和必须等于 totals 之和
    tot_sum = sum(v for v in ALL["totals"].values())
    trk_sum = sum(t["n_marker"] for t in ALL["tracks"])
    if tot_sum != trk_sum or tot_sum != ALL["n_marker_total"]:
        raise SystemExit(
            f"marker 总构成对不上：totals={tot_sum} 逐轨迹={trk_sum} "
            f"声明={ALL['n_marker_total']} ⇒ 拒绝判定")

    n_dom = sum(1 for r in rows if r["dom"])
    n_rest = len(rows) - n_dom
    all_dom = ALL["totals"].get(str(DOM), 0)
    all_rest = tot_sum - all_dom

    res = {"schema": "selection_contamination/1",
           "prereg": "R6_RERUN_PREREG.md 修订 40 §40.2",
           "probe": a.probe, "map": a.map, "marker_all": a.marker_all,
           "dom_id": DOM, "n_sites": len(rows),
           "floor_same_slice": a.floor_same_slice,
           "marker_all_total": tot_sum}

    # ---- B1 |w·ĥ| 分布是否不同 ----
    aw_d = [r["aw"] for r in rows if r["dom"]]
    aw_r = [r["aw"] for r in rows if not r["dom"]]
    u1, p_b1 = mannwhitneyu(aw_d, aw_r, alternative="two-sided")
    b1 = float(p_b1 < B_MAX_P)
    res["B1"] = {"median_dom": float(np.median(aw_d)),
                 "median_rest": float(np.median(aw_r)),
                 "p": float(p_b1), "max_p": B_MAX_P, "pass": b1}
    print(f"=== B1：|w·ĥ| 中位 {np.median(aw_d):.4f} vs {np.median(aw_r):.4f}，"
          f"Mann-Whitney 双尾 p = {p_b1:.4g}（须 < {B_MAX_P}）⇒ "
          f"{'过' if b1 else '不过'}")

    # ---- B2 高对齐位点里 7196 是否富集 ----
    orr, p_b2 = fisher_exact([[n_dom, n_rest], [all_dom, all_rest]])
    sel = n_dom / len(rows)
    base = all_dom / tot_sum
    b2 = float(p_b2 < B_MAX_P)
    # ⚠⚠ **enrich 必须存 8 位，不能 round 到 3 位**。
    #   真值 2.275087175513367 —— round(...,3) 得到 `2.275`，而 `2.275`
    #   的 IEEE754 表示是 2.27499999999999991118… ⇒ 下游任何两位格式化
    #   （Python `format` 与 JS `toFixed` **都**如此）都给 **2.27**，
    #   而文档按十进制字面量四舍五入写的是 **2.28**。
    #   ⇒ 同一个数在页面和文档里会显示成两个不同的值，且没有任何守卫发现。
    #   存 8 位后两侧都稳定给 2.28；「文档数字 == 产物格式化值」由
    #   test_selection_contamination.py 用例 8 钉住。
    res["B2"] = {"sel_frac_dom": round(sel, 8), "baseline_frac_dom": round(base, 8),
                 "enrich": round(sel / base, 8) if base else None,
                 "or": float(orr), "p": float(p_b2),
                 "max_p": B_MAX_P, "pass": b2,
                 "note": ("分母 = 这 %d 条轨迹里**全部** marker 位点"
                          "（count_marker_tokens.py，只读 sidecar）"
                          % ALL["n_traj"])}
    print(f"=== B2：选中里 7196 占 {sel:.1%}，全体 marker 里占 {base:.1%}"
          f"（富集 {sel / base:.2f}×），Fisher 双尾 p = {p_b2:.4g}"
          f"（须 < {B_MAX_P}）⇒ {'过' if b2 else '不过'}")

    # ---- 幅度部分 ----
    use = rows
    if a.floor_same_slice is not None:
        use = [r for r in rows if abs(r["d"]) > a.floor_same_slice]
        print(f"⚠ 只用 |Δ| > {a.floor_same_slice} 的位点：{len(use)} 个")
    aw = np.array([r["aw"] for r in use], dtype=float)
    ad = np.array([abs(r["d"]) for r in use], dtype=float)
    # ⚠ 地板可能把**全部**位点吃掉（`use` 为空）⇒ `spearmanr` 返回 nan。
    #    样本不足按纪律报「**不适用**」，不是 PASS，也不是崩在
    #    「产物里有非有限数」上 —— 那会让下游读到一个空文件。
    if len(use) < MIN_N_RHO:
        a0 = 0.0
        res["A0"] = {"rho_obs": None, "p": None, "max_p": A0_MAX_P,
                     "pass": 0.0, "n": len(use),
                     "why": f"|Δ| 超地板的位点只有 {len(use)} 个 < {MIN_N_RHO}"}
        print(f"⚠ A0（前提）：超地板位点只有 {len(use)} 个 < {MIN_N_RHO}"
              f" ⇒ 不适用")
    else:
        rho_obs, p_obs = spearmanr(aw, ad)
        a0 = float(math.isfinite(rho_obs) and math.isfinite(p_obs)
                   and p_obs < A0_MAX_P)
        res["A0"] = {"rho_obs": float(rho_obs), "p": float(p_obs),
                     "max_p": A0_MAX_P, "pass": a0, "n": len(use),
                     "why": None}
        print(f"=== A0（前提）：ρ_obs = Spearman(|w·ĥ|, |Δ|) = {rho_obs:+.4f}"
              f"，p = {p_obs:.4g}（须 < {A0_MAX_P}）⇒ "
              f"{'适用' if a0 else '不适用'}")

    if not a0:
        # 键集合与下面正常路径**逐个相同**（值用 None 占位）
        res["A1"] = {"median_dom": None, "median_rest": None, "p": None,
                     "max_p": A_MAX_P, "pass": False, "applicable": False,
                     "why": WHY_NA}
        res["A2"] = {"rho_null": None, "cover": None, "need_cover": A2_COVER,
                     "pass": False, "applicable": False, "rho_within": {},
                     "note": WHY_NA, "why": res["A0"].get("why") or WHY_NA}
        res["final"] = "幅度维度：不适用（ρ_obs 不显著，没有可污染的东西）"
        print(f"⚠ {res['final']}")
        dump(res, a.out)
        print(f"写出 {a.out}")
        return

    # A1 |Δ| 分布是否不同
    d_d = [abs(r["d"]) for r in use if r["dom"]]
    d_r = [abs(r["d"]) for r in use if not r["dom"]]
    u2, p_a1 = mannwhitneyu(d_d, d_r, alternative="two-sided")
    a1 = float(p_a1 < A_MAX_P)
    res["A1"] = {"median_dom": float(np.median(d_d)),
                 "median_rest": float(np.median(d_r)),
                 "p": float(p_a1), "max_p": A_MAX_P, "pass": a1,
                 "applicable": True, "why": None}
    print(f"=== A1：|Δ| 中位 {np.median(d_d):.4f} vs {np.median(d_r):.4f}，"
          f"p = {p_a1:.4g}（须 < {A_MAX_P}）⇒ {'过' if a1 else '不过'}")

    # A2 用「组中位数」替换 |Δ|，只保留 token 信息
    med_dom, med_rest = float(np.median(d_d)), float(np.median(d_r))
    sub = np.array([med_dom if r["dom"] else med_rest for r in use])
    rho_null, _ = spearmanr(aw, sub)
    # ⚠ ρ_obs→0 时 cover 会爆成 inf ⇒ **判「无法判定」而不是 PASS**。
    #    （正常路径里 A0 已经要求 ρ_obs 显著，但守卫不依赖那条推理。）
    cover = (abs(rho_null) / abs(rho_obs)
             if rho_obs != 0 and math.isfinite(rho_obs) else float("inf"))
    cover_ok = math.isfinite(cover)
    a2 = bool(cover_ok and cover >= A2_COVER)
    res["A2"] = {"rho_null": float(rho_null),
                 # ⚠ 不可判定时写 None 而不是 inf —— `inf` 会被 json.dump
                 #    写成裸 `Infinity`（非法 JSON），浏览器 JSON.parse 会抛。
                 "cover": round(cover, 4) if cover_ok else None,
                 "need_cover": A2_COVER, "pass": a2, "applicable": cover_ok,
                 "note": ("把 |Δ| 换成所在 token 组的中位 |Δ| ⇒ 只保留 token "
                          "信息、去掉 aw 信息；覆盖度 = |ρ_null| / |ρ_obs|"
                          + ("" if cover_ok else "；⚠ ρ_obs 退化 ⇒ 无法判定")),
                 "why": None}
    # 层内 ρ（**只报，不判决**）
    within = {}
    for lab, sel in (("dom", [r for r in use if r["dom"]]),
                     ("rest", [r for r in use if not r["dom"]])):
        if len(sel) >= 8:
            rr, pp = spearmanr([r["aw"] for r in sel],
                               [abs(r["d"]) for r in sel])
            within[lab] = {"rho": float(rr), "p": float(pp), "n": len(sel)}
    res["A2"]["rho_within"] = within
    print(f"=== A2：ρ_null = {rho_null:+.4f}，覆盖度 = |ρ_null|/|ρ_obs| ="
          f" {cover:.3f}（须 ≥ {A2_COVER}）⇒ {'过' if a2 else '不过'}")
    print(f"    （层内 ρ 只报不判：{within}）")

    if a1 and a2:
        res["final"] = "幅度维度的 ρ 主要由 token 构成决定"
    elif a2:
        res["final"] = "幅度 ρ 可被构成解释（但组间 |Δ| 分布差异未达阈值）"
    else:
        res["final"] = "幅度 ρ 不能仅由构成解释"
    print(f"\n最终：{res['final']}")
    dump(res, a.out)
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()