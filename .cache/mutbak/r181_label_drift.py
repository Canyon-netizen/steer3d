#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""旧批 vs 新批的标签漂移检查（修订 181 立）。

回答且只回答一个问题：
    新批（cap 32768）与旧批（cap 8192）在**同一批题、同一臂**上，
    旧批已经确立的标签（correct / wrong）有没有被重跑扰动？

为什么这是 P6 的前置项：
    P6 要比的是两批的 correct 数之差。若重跑本身会把 correct 翻成 wrong，
    这个差就同时混着「抬 cap 的效果」与「重跑的扰动」，两件事分不开就不能归因。
    §167 管的是「不许提前下结论」，本脚本管的是「数据到齐之后那个结论能不能这么读」。

判定口径（写死在此，不从别处复刻）：
    漂移 = 旧批 strict ∈ {correct, wrong} 且 新批 strict ≠ 旧批 strict
    必须为 0。unlabeled -> X 不算漂移（它本来就是未确立的），
    但要单列出来，因为那正是「不再截断」发生的地方。

用法：
    python3 r181_label_drift.py <old_label.json> <new_label.json>
退出码：
    0  无漂移
    4  有漂移
    2  用法/文件错误
"""

import json
import sys
from collections import Counter
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DRIFT = 4

ESTABLISHED = ("correct", "wrong")


def load_rows(path):
    d = json.load(open(path, encoding="utf-8"))
    return d["rows"] if isinstance(d, dict) and "rows" in d else d


def arm_of(traj):
    return str(traj).rsplit("__", 1)[-1] if "__" in str(traj) else "?"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return EXIT_USAGE

    old_p, new_p = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    for p in (old_p, new_p):
        if not p.exists():
            print("[错误] 读不到标注文件：%s" % p)
            return EXIT_USAGE

    old = {r["traj"]: r for r in load_rows(old_p)}
    new = {r["traj"]: r for r in load_rows(new_p)}
    common = sorted(set(old) & set(new))

    print("=== 标签漂移检查 ===")
    print("  旧批 = %s（cap 分布 %s）"
          % (old_p.name, dict(Counter(r.get("cap") for r in old.values()))))
    print("  新批 = %s（cap 分布 %s）"
          % (new_p.name, dict(Counter(r.get("cap") for r in new.values()))))
    print("  同题同臂可比 = %d 条" % len(common))
    if not common:
        print("[错误] 两批没有可比的同题同臂条目 —— 先查输入")
        return EXIT_USAGE

    matrix = Counter((old[t]["strict"], new[t]["strict"]) for t in common)
    print("\n--- 旧标签 -> 新标签 转移矩阵 ---")
    for (o, n), c in sorted(matrix.items()):
        print("  %-10s -> %-10s %3d" % (o, n, c))

    lock = [t for t in common if old[t]["strict"] in ESTABLISHED]
    print("\n--- 已确立标签（分母限定在旧批 correct/wrong）---")
    print("  合计 n=%d" % len(lock))
    drifts = []
    for m in ("think", "no_think"):
        sub = [t for t in lock if arm_of(t) == m]
        bad = [t for t in sub if old[t]["strict"] != new[t]["strict"]]
        drifts += bad
        detail = Counter((old[t]["strict"], new[t]["strict"]) for t in sub)
        print("  %-9s n=%2d  一致 %2d  不一致 %d  %s"
              % (m, len(sub), len(sub) - len(bad), len(bad), dict(detail)))

    unl = [t for t in common if old[t]["strict"] == "unlabeled"]
    print("\n--- 旧批 unlabeled 的 %d 条（不算漂移，单列）---" % len(unl))
    for t in unl:
        o, n = old[t], new[t]
        print("  %-30s ntok %-6s -> %-6s  trunc %-5s -> %-5s  -> %s"
              % (t, o.get("n_tok"), n.get("n_tok"),
                 o.get("truncated"), n.get("truncated"), n["strict"]))

    print()
    if drifts:
        print("⛔ 有漂移 %d 条 —— 两批 correct 数之差不能直接归因于抬 cap。" % len(drifts))
        for t in drifts:
            print("   %s: %s -> %s" % (t, old[t]["strict"], new[t]["strict"]))
        print("RESULT label_drift  DRIFT  n=%d" % len(drifts))
        return EXIT_DRIFT

    print("✅ 已确立标签 %d/%d 全部保持，无漂移。" % (len(lock), len(lock)))
    print("⚠ 适用范围：只覆盖当前两批**共同存在**的那些题。")
    print("⚠ 新批尚未生成完时，本结果只是已生成那一段的，不得当作全池结论。")
    print("RESULT label_drift  OK  n_locked=%d" % len(lock))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())