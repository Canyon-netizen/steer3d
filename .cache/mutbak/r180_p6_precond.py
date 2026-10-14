#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 判决前置闸 —— 在跑 p6_readiness.py 之前先过这个。

修订 180 立这条闸的原因（实测，非推断）：

  在 18/60 条（think n=9）的部分数据上，p6_readiness.py 照样出判决：
      RESULT p6_readiness  UNDERPOWERED  think correct=5 < 10
      EXIT=3
  并印出下面这段话：
      缺的是轨迹本身（带 hidden states 的 npz），不是口径、不是算力。
      新批次单个 benchmark 的 correct 只有 6-7 条，
      按预登记的停止点（前 30 题），再多取也到不了 10。
      => 这是设计问题，不是取数问题。

  逐条对账：
    * 「6-7 条」出自 cap 全 8192 的批次（strict_label_b2_full60.json，120 行），
      是旧批的实测值，被原样搬到 cap 32768 的新批上；
    * 「再多取也到不了 10」在 18/60 时是**假话** —— 30 题里有 21 题还没开始生成；
    * 「这是设计问题，不是取数问题」把「还没跑完」误诊成「设计上就不够」。

  三条都足以让人提前收工、砍掉正在跑的这一轮。

本闸不修改 p6_readiness.py，也不改任何阈值 —— 它只做一件事：
**数据没齐就不许跑那支仪器。**

用法：
    python3 r180_p6_precond.py <label.json> <expect_cap> <expect_rows>
退出码：
    0  批次完整 -> 允许跑 p6_readiness.py
    4  批次不完整 -> 拒绝，且印出「为什么这条判决现在不成立」
    2  用法/文件错误
"""

import json
import sys
from collections import Counter
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INCOMPLETE = 4


def load_rows(path):
    d = json.load(open(path, encoding="utf-8"))
    return d["rows"] if isinstance(d, dict) and "rows" in d else d


def prob_mode(traj):
    """'aime__aime25__p07__think' -> (7, 'think')；不匹配返回 (None, None)。

    ⚠ 修订 180 修正：题目名按 '__' 切是 **4 段**（aime / aime25 / p07 / think），
    不是 3 段。第一版按 3 段写，结果 18 条合法数据全被误报「形状不可解析」——
    恒红且红错理由：真因是行数不足，却印成格式问题。
    """
    parts = str(traj).rsplit("__", 2)
    if len(parts) != 3:
        return None, None
    _, pid, mode = parts
    if not pid.startswith("p") or not pid[1:].isdigit():
        return None, None
    return int(pid[1:]), mode


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return EXIT_USAGE

    label_path = Path(sys.argv[1]).resolve()
    expect_cap = int(sys.argv[2])
    expect_rows = int(sys.argv[3])

    if not label_path.exists():
        print("[错误] 读不到标注文件：%s" % label_path)
        return EXIT_USAGE

    rows = load_rows(label_path)
    probs = expect_rows // 2

    checks = []

    caps = Counter(r.get("cap") for r in rows)
    caps_ok = len(caps) == 1 and list(caps)[0] == expect_cap
    checks.append(("cap 全等且 = %d" % expect_cap, caps_ok,
                   "cap 分布 %s" % dict(caps)))

    n_ok = len(rows) == expect_rows
    checks.append(("行数 = %d" % expect_rows, n_ok,
                   "实际 %d（缺 %d）" % (len(rows), expect_rows - len(rows))))

    ids = [r.get("traj") for r in rows]
    dup = [t for t, c in Counter(ids).items() if c > 1]
    checks.append(("traj 无重复", not dup, "重复 %d 个：%s" % (len(dup), dup)))

    parsed = [prob_mode(t) for t in ids]
    unparsed = [t for t, p in zip(ids, parsed) if p[0] is None]
    checks.append(("traj 形状可解析", not unparsed, "不合规 %d 个：%s"
                   % (len(unparsed), unparsed[:5])))

    got = {(p, m) for p, m in parsed if p is not None}
    missing = [(p, m) for p in range(probs) for m in ("think", "no_think")
               if (p, m) not in got]
    checks.append(("题号 0..%d 两臂齐全" % (probs - 1), not missing,
                   "缺 %d 条：%s" % (len(missing), missing[:6])))

    print("=== P6 判决前置闸：%s ===" % label_path.name)
    print("    期望 cap=%d  行数=%d" % (expect_cap, expect_rows))
    for name, ok, detail in checks:
        print("  [%s] %s —— %s" % ("✅" if ok else "❌", name, detail))

    if all(ok for _, ok, _ in checks):
        print("\n✅ 批次完整 —— 现在跑 p6_readiness.py，它的判决才成立。")
        print("RESULT p6_precond  OK")
        return EXIT_OK

    print("\n" + "=" * 68)
    print("⛔ 批次不完整 —— **不要跑 p6_readiness.py**。")
    print("=" * 68)
    print("它会把「还没跑完」判成「设计上就不够」，并印：")
    print("    「按前 30 题，再多取也到不了 10」")
    print("    「=> 这是设计问题，不是取数问题」")
    print("⚠ 那两句在未跑满时都是**假话** —— 它会把还在跑的这一轮劝停。")
    print("\n现在该做的是等生成跑满再量；权威口径看 r178_uncapped_fate.py，")
    print("它会分开印「已测 / 未测」，不会把未测混进分母。")
    print("RESULT p6_precond  INCOMPLETE  ——  判决不许出")
    return EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())