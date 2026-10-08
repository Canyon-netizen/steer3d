"""从远端日志统计主跑进度与产出质量。

判决规则（取数前写死）：
  S1 速率：实际 s/条 vs pilot 外推（think 246 + no_think 46 = 292 s/条）。
     偏离 > 2x 判红 —— 预登记里写明要报出来。
  S2 截顶率：think 触顶比例。若 > 50%，说明 cap 8192 对这批题多数仍不够。
  S3 正确率：日志里的 ✓/✗。这是**旧标签**口径，只用于速率与规模的粗判，
     真实标签要用 strict_label.py 的 R-27 规则重算。
  S4 外推：按当前速率与正确率，外推全量后 correct 组有多少条轨迹。
     这是 P6「correct 组 < 10 条即样本不足」的预判依据。
"""
from __future__ import annotations

import re
import statistics
import sys
from collections import Counter

PAT = re.compile(
    r"\[(\d+)/(\d+)\]\s+(think|no_think)\s+(\S+)\s+…\s+([✓✗])\s+(\d+)\s+tok\s+ans=(\S*)"
)


def main(path, cap):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = PAT.search(line.replace("\r", "\n"))
            if m:
                rows.append({
                    "i": int(m.group(1)), "n_tot": int(m.group(2)),
                    "mode": m.group(3), "pid": m.group(4),
                    "ok": m.group(5) == "✓", "tok": int(m.group(6)), "ans": m.group(7),
                })
    n = len(rows)
    print(f"解析到 {n} 条轨迹（日志里 {PAT.pattern[:20]}…）")

    th = [r for r in rows if r["mode"] == "think"]
    nt = [r for r in rows if r["mode"] == "no_think"]
    for name, rs in (("think", th), ("no_think", nt)):
        if not rs:
            continue
        trunc = sum(1 for r in rs if r["tok"] >= cap)
        ok = sum(r["ok"] for r in rs)
        print(f"  {name:9s} n={len(rs):3d}  触顶={trunc:3d} ({trunc/len(rs)*100:3.0f}%)  "
              f"旧标签答对={ok:2d} ({ok/len(rs)*100:3.0f}%)  "
              f"tok 中位={statistics.median([r['tok'] for r in rs]):.0f} max={max(r['tok'] for r in rs)}")

    print("\n负数答案（越界标签，脏读数）:",
          [f"{r['pid']}/{r['mode']}={r['ans']}" for r in rows if r['ans'].startswith('-')])

    # S1 速率：需要两个时间戳，用条数 + 外推的完成时间不可靠。
    # 这里只报条数与按 pilot 速率的对比，等拿到 elapsed 再算。
    tot_expected = rows[0]["n_tot"] if rows else 0 * 2
    print(f"\n目标条数 {tot_expected}，已完成 {n}（{n/tot_expected*100:.0f}%）")
    return rows


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8192)