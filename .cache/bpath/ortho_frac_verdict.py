"""修订 24 · M1 / M2 / M3 判定器（**机械实现**，不重新解释判据）。

## 它做什么

读 `ortho_frac_full.json`（58 条未测 think 轨迹**全量** marker 位点的
`w·ĥ > 0.1` 占比），按 **预登记 §24.1 取数前写死的**三条判据给出 PASS/FAIL，
并在 M3 的「再更正」分支下输出 §24.2 **预先写好的**措辞原文。

## 为什么不重新解释判据

§24.1 的三条判据在取数前已落盘并提交（`c5bb376` 之后单独一笔修订 24 提交）。
本脚本因此**只做算术**，不做任何判断：

- M1：`median(frac_58) >= 0.05`
- M2：`p01_think`（0.1577）排在 58 条中的名次 `<= 3`
- M3：M1 过 ⇒ 修订 23 的更正**必须再更正一次**（措辞取自 §24.2 原文）；
  M1 不过 ⇒ 修订 23 的更正**维持**。

⚠ 三处**不许**在本脚本里出现：改 `0.05`、改 `0.1` 的正交边界、
改「前 3 条」。它们若需要改，必须单独立修订。

## 中位数定义（预登记未指明，此处显式钉死并两个都报）

58 是偶数。本脚本把**判据用的中位**定为 numpy 的标准中位数
（= 中间两值的平均），同时打印扫描脚本里用的上中位数
（`fr[n//2]`），并断言两者判定的 PASS/FAIL 一致后才出结论。
若两者判定不同，脚本会**拒绝出结论**而不是挑一个。

## 只读

不改任何产物、不改预登记原文；§24.2 的措辞是从预登记**读出来**的，
不重打一遍，避免两处漂移。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

PREREG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "xcheck", "R6_RERUN_PREREG.md")

N_EXPECT = 58           # 预登记 §24.1 写死的轨迹数
M1_MIN_MEDIAN = 0.05    # 预登记 §24.1
M2_MAX_RANK = 3         # 预登记 §24.1「前 3 条」
P01_FRAC = 0.1577       # 预登记 §24.0/§24.1 写下的**字面值**，判据按它执行
P01_HI, P01_N = 21, 133 # p01_think 全量的实测计数（修订 16，两份产物独立一致）
P01_FRAC_TRUE = P01_HI / P01_N   # = 0.157894736...


def read_sec242(prereg_path: str) -> str:
    """从预登记 §24.2 摘出预先写好的更正措辞（blockquote）。

    找不到就抛错 —— 宁可崩，也不能用一份「大概是这个意思」的措辞。
    """
    lines = open(prereg_path, encoding="utf-8").read().splitlines()
    try:
        i0 = next(i for i, l in enumerate(lines)
                  if l.startswith("## 24.2"))
    except StopIteration:
        raise SystemExit("预登记里找不到 §24.2，拒绝出结论")
    quote = [l[2:] for l in lines[i0 + 1:] if l.startswith("> ")]
    if not quote:
        raise SystemExit("§24.2 里没有 blockquote 措辞，拒绝出结论")
    return "\n".join(quote).strip()


def verdict(rows, prereg_path):
    if len(rows) != N_EXPECT:
        raise SystemExit(
            f"轨迹数 {len(rows)} != 预登记要求的 {N_EXPECT}，拒绝出结论")

    fr = [r["frac"] for r in rows]
    med_std = statistics.median(fr)                 # 偶数 -> 中间两值平均
    med_up = sorted(fr)[len(fr) // 2]               # 扫描脚本用的上中位数
    m1_std = med_std >= M1_MIN_MEDIAN
    m1_up = med_up >= M1_MIN_MEDIAN

    rank = 1 + sum(1 for v in fr if v > P01_FRAC)   # 名次：严格大于 p01 的条数 + 1
    m2 = rank <= M2_MAX_RANK

    # 敏感性：判据里写的 P01_FRAC 字面值（0.1577）与实测 21/133（0.157895…）
    # 在小数第 4 位不一致。**判据按字面值执行**，这里只回答
    # 「若换成实测值，名次会不会翻」——不改判据，只暴露它的脆弱性。
    rank_true = 1 + sum(1 for v in fr if v > P01_FRAC_TRUE)
    if (rank_true <= M2_MAX_RANK) != m2:
        raise SystemExit(
            f"p01 判据常量转写错误会改变 M2 结论"
            f"（字面值名次 {rank} vs 实测值名次 {rank_true}），"
            f"必须单独立修订后才出结论")

    if m1_std != m1_up:
        raise SystemExit(
            f"两种中位数定义给出相反判定（{med_std:.4f} vs {med_up:.4f}），"
            f"拒绝挑一个出结论")

    out = {
        "prereg_section": "§24.1",
        "n_tracks": len(rows),
        "n_sites_total": sum(r["n_sites"] for r in rows),
        "n_hi_total": sum(r["n_hi"] for r in rows),
        "median_std": med_std,
        "median_upper_mid": med_up,
        "min": min(fr), "max": max(fr),
        "mean": sum(fr) / len(fr),
        "p01_frac": P01_FRAC,
        "p01_rank": rank,
        "p01_frac_true_from_counts": P01_FRAC_TRUE,
        "p01_rank_under_true_value": rank_true,
        "p01_percentile_rank_over_n": 100.0 * rank / len(rows),
        "M1": {"rule": f"median(frac over {N_EXPECT}) >= {M1_MIN_MEDIAN}",
               "value": med_std, "pass": bool(m1_std)},
        "M2": {"rule": f"p01({P01_FRAC}) 排名 <= {M2_MAX_RANK}",
               "rank": rank, "above_p01": rank - 1,
               "rank_under_true_value": rank_true,
               "verdict_invariant": ((rank_true <= M2_MAX_RANK) == m2),
               "pass": bool(m2)},
        "M3": {"rule": "M1 过 => 修订23 的更正必须再更正一次；不过 => 维持",
               "action": ("revise_rev23_again" if m1_std else "keep_rev23"),
               "new_wording_sec242": read_sec242(prereg_path) if m1_std else None},
        "table": sorted(
            [{"rank": i + 1, "traj": r["traj"], "n_hi": r["n_hi"],
              "n_sites": r["n_sites"], "frac": r["frac"]}
             for i, r in enumerate(sorted(rows, key=lambda r: -r["frac"]))],
            key=lambda r: r["rank"]),
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--prereg", default=PREREG)
    a = ap.parse_args()

    rows = json.load(open(a.input, encoding="utf-8"))
    v = verdict(rows, a.prereg)

    print(f"轨迹 {v['n_tracks']} 条，位点 {v['n_sites_total']} 个，"
          f"高对齐 {v['n_hi_total']} 个 = {v['n_hi_total']/v['n_sites_total']:.4f}")
    print(f"逐条占比：中位(std) {v['median_std']:.4f}  "
          f"上中位 {v['median_upper_mid']:.4f}  "
          f"均值 {v['mean']:.4f}  [{v['min']:.4f}, {v['max']:.4f}]")
    print(f"p01 = {v['p01_frac']} 排名 {v['p01_rank']}/{v['n_tracks']} "
          f"(高于它的 {v['M2']['above_p01']} 条)")
    print(f"M1 median >= {M1_MIN_MEDIAN} : {'PASS' if v['M1']['pass'] else 'FAIL'}"
          f"   ({v['M1']['value']:.4f})")
    print(f"M2 p01 rank <= {M2_MAX_RANK} : {'PASS' if v['M2']['pass'] else 'FAIL'}")
    print(f"M3 -> {v['M3']['action']}")
    print("\n前 8 条：" + "  ".join(
        f"{r['traj'].split('__')[1]}:{r['frac']:.3f}"
        for r in v["table"][:8]))
    if v["M3"]["new_wording_sec242"]:
        print("\n--- §24.2 预先写好的措辞 ---")
        print(v["M3"]["new_wording_sec242"])

    if a.out:
        json.dump(v, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n写出 {a.out}")
    else:
        print("\n（未指定 --out，只打印不落盘）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())