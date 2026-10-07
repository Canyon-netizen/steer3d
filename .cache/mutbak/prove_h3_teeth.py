#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证 H-3 新增的 6 条真实语料对照**有牙齿**。

⚠ 光看 `hinge_points.py --selfcheck` 变红**不能**证明牙齿 —— 变红也可能
  是我把 FAILMODE 加进去、于是「判据恒红」。必须反向验：
  **老实现（打补丁前的那版规则）在这 6 条上确实会误抓**，新实现不会。

做法：把老规则的 `_B`（含 `but maybe I` / `maybe my`）与老 `EXCLUDE`
（锚在 `^` 上）原样搬进来，在同一批句子上跑，报老版误抓了几条。
只搬规则，不碰真实实现。
"""
from __future__ import annotations

import re
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
import hinge_points as HP  # noqa: E402

# ---- 老实现（B 类通配 + EXCLUDE 只锚句首）----
_OLD_B = [r"maybe I miscalculated", r"maybe I misread the problem",
          r"maybe I made a mistake", r"I made a mistake",
          r"may have made a mistake", r"my assumption is wrong",
          r"my reasoning is wrong", r"but maybe I", r"maybe my"]
OLD_MARK_B = re.compile("|".join(_OLD_B), re.IGNORECASE)
OLD_EXCLUDE = re.compile(
    r"^\s*(?:but\s+|so\s+|and\s+|also\s+)?"
    r"(?:wait\s*,?\s*)?(?:the\s+problem\s+says|it\s+says|the\s+question\s+says)"
    r"|^\s*(?:alternatively\s*,?\s*)?maybe\s+(?:we|i)\s+can\b"
    r"|^\s*let\s+me\s+try\b", re.IGNORECASE)


def old_find(text: str):
    out = []
    for m in HP._SENT.finditer(text):
        sent = m.group(0)
        cls = "A" if HP.MARK_A.search(sent) else (
            "B" if OLD_MARK_B.search(sent) else None)
        if cls is None or OLD_EXCLUDE.search(sent):
            continue
        if not HP.HEAD_OK.search(sent[:12]):
            continue
        out.append((cls, " ".join(sent.split())[:70]))
    return out


def main() -> int:
    fails = []
    print("=== 6 条真实假阳性原句：老实现 vs 新实现 ===")
    for s in HP.FAILMODE[5:]:
        o = old_find(s)
        n = HP.find_hinges(s)
        flag_o = "误抓" if o else "未抓"
        flag_n = "误抓" if n else "未抓"
        print(f"\n  老 {flag_o} / 新 {flag_n}")
        print(f"    {s[:78]}")
        if not o:
            fails.append(f"老实现竟然没误抓（牙齿不存在）：{s[:50]}")
        if n:
            fails.append(f"新实现仍误抓：{s[:50]}")
    if fails:
        print("\n=== 牙齿检查 FAIL ===")
        for f in fails:
            print("  ! " + f)
        return 1
    print(f"\n✓ 6 条全部：老实现误抓 {len(HP.FAILMODE)-5} 条、新实现 0 条")
    print("  ⇒ 这 6 条**有牙齿**：它们能区分老实现与新实现，不是恒红恒绿。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())