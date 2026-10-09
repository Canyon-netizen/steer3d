"""修订 28 的**选材**：从 48 条未测轨迹里挑出 453 个高对齐位点。

## 它必须做到的三件事（取数前写死在预登记 §28.1）

1. **轨迹**：按 `trajectory_id` **字典序取前 30 条**。
   ⚠ **不按 `frac` / `n_hi` 排序** —— 那是按预测量挑，等于挑结果。
2. **位点**：每条内取**全部** `w·ĥ > 0.1` 的 marker 位点，不上限、不抽样。
3. ⚠⚠ **选材只依赖预测量 `w·ĥ`，从不依赖结果量 `Δ`。**
   本脚本**读不到任何 Δ**（输入只有 `ortho_frac_full.json`），
   所以它在结构上就不可能偏向效应的大小或方向。

## 为什么单独一个文件

「选材」是这套设计里唯一**能悄悄偏向结论**的环节
（手动挑、或按结果排序挑，都能让 G1 变绿）。
把它写成可审、可单测的纯函数，比写进探针里靠自觉可靠。

## 纯 Python ⇒ 本地假数据先验，不上远端

远端跑一次要加载模型（几分钟），而选材崩在**任何前向之前**毫无意义。
`test_pick_hi_sites.py` 在本地 5 秒验完。

## 只读

不改任何产物。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# 取数前定死（预登记 §28.1 / §28.5）
N_TRACKS = 30
ORTH_THRESHOLD = 0.1          # w·ĥ > 0.1，与修订 24/27 同一个正交边界
EXPECT_POOL = 48              # 58 − 修订 22 用过的 10 条
EXPECT_SITES = 453            # 字典序前 30 条的 n_hi 之和
# 修订 22 用过的 10 条轨迹（p02–p11），必须排除，否则「独立」不成立
USED_IN_REV22 = {f"aime__aime25__p{i:02d}__think" for i in range(2, 12)}


def pick(rows):
    """rows: [{traj, n_hi, n_sites, frac}] -> (chosen_tracks, totals)

    ⚠ 只用 `traj` 与 `n_hi`；**`frac` 一列刻意不参与任何排序**。
    """
    if len(rows) != 58:
        raise SystemExit(f"轨迹池应为 58 条，实际 {len(rows)}，拒绝选材")
    # ⚠ 输入池**本来就含**修订 22 用过的那 10 条（它们已被静态扫过、
    # 但要在选材这一步被排除掉）。要断言的是「恰好排除掉 10 条」，
    # 而不是「池里没有它们」—— 后者会让真数据直接被拒。
    n_used = sum(1 for r in rows if r["traj"] in USED_IN_REV22)
    if n_used != len(USED_IN_REV22):
        raise SystemExit(
            f"输入池里应有 {len(USED_IN_REV22)} 条修订 22 用过的轨迹，"
            f"实际 {n_used} 条，拒绝选材")
    rest = sorted((r for r in rows if r["traj"] not in USED_IN_REV22),
                  key=lambda r: r["traj"])          # ← 字典序，无信息
    if len(rest) != EXPECT_POOL:
        raise SystemExit(f"排除修订22 后应为 {EXPECT_POOL} 条，实际 {len(rest)}")
    chosen = rest[:N_TRACKS]
    sites = sum(r["n_hi"] for r in chosen)
    # 用显式 raise 而不是 `assert` —— **`assert` 会被 `python -O` 整个关掉**，
    # 守卫不能建在一个能被静默关掉的语句上。
    for r in chosen:
        if not (0 <= r["n_hi"] <= r["n_sites"]):
            raise SystemExit(
                f"{r['traj']} 的 n_hi({r['n_hi']}) 与 n_sites({r['n_sites']}) "
                f"不自洽，拒绝选材")
    if sites != EXPECT_SITES:
        raise SystemExit(
            f"位点数 {sites} != 预登记 §28.5 写的 {EXPECT_SITES}，拒绝选材")
    return chosen, sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frac-scan", required=True,
                    help="ortho_frac_full.json（58 条，纯静态，不含任何 Δ）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = json.load(open(a.frac_scan, encoding="utf-8"))
    chosen, sites = pick(rows)
    out = {"schema": "pick_hi_sites/1",
           "prereg": "R6_RERUN_PREREG.md 修订 28 §28.1",
           "rule": ("字典序取前 %d 条未测轨迹；每条取全部 w·ĥ>%.1f 的 marker 位点；"
                    "不按 frac/n_hi 排序；选材只依赖预测量，不依赖 Δ"
                    % (N_TRACKS, ORTH_THRESHOLD)),
           "excluded_rev22": sorted(USED_IN_REV22),
           "n_tracks": len(chosen),
           "n_sites": sites,
           "n_zero_contrib": sum(1 for r in chosen if r["n_hi"] == 0),
           "n_tracks_ge8": sum(1 for r in chosen if r["n_hi"] >= 8),
           "tracks": [{"traj": r["traj"], "n_hi": r["n_hi"],
                       "n_sites": r["n_sites"], "frac": r["frac"]}
                      for r in chosen]}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"选中 {len(chosen)} 条轨迹，合计 {sites} 个 w·ĥ>{ORTH_THRESHOLD} 位点")
    print(f"其中 n_hi=0 的轨迹 {out['n_zero_contrib']} 条、"
          f"n_hi>=8 的轨迹 {out['n_tracks_ge8']} 条")
    print(f"前向数估计 = {sites}×3×2 + {len(chosen)} = {6*sites+len(chosen)}")
    print("\n字典序前 30 条（完整表，供事后核对没有按结果挑过）：")
    for i, r in enumerate(chosen, 1):
        print(f"  {i:>2} {r['traj']:<30} n_hi={r['n_hi']:<4} n_sites={r['n_sites']}")
    print(f"\n写出 {a.out}")


if __name__ == "__main__":
    main()