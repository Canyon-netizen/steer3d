#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""244.96 索引期望值探针（**一次性**）。

⚠ 目的：R15 驱动里的 `EXPECT_INDEX_MD5` / `EXPECT_INDEX_LINES` 必须**手写期望值**，
  ⛔ 不能留占位符（留了就不成闸门），也不能在跑的时候现算（现算 ⇒ 恒绿）。

⚖ 本探针的做法：**不复制生成器的逻辑**，而是 import 原生成器、只覆盖它的
  两个路径常量（PREREG / OUT），⇒ 算出来的 md5 与落账后真跑
  `python3 .cache/mutbak/r100_build_index.py` 的输出**逐字节同源**。

⚠ 输入是**落账前的干跑副本**（`_ledger_24496_dry.md`），
  它与真落账后的账本**逐字节相同**（md5 `912f7d6f34aa8b78d4483d7a539ae2b2`）。

⚖⚖⚖ **诚实声明**：与 244.95 不同，244.96 的**真索引是在落账后重建的**，
  R15 驱动里手写的 `EXPECT_INDEX_MD5` 取的就是那份重建结果。
  ⇒ ⇒ 本探针的作用**不是**「预先算出期望值」，而是**独立复核**：
  「从干跑副本重建出来的索引」与「从真账本重建出来的索引」**逐字节相同**
  ⇒ ⇒ ⇒ 期望值**不是**重建过程里某个偶发因素（比如时间戳／顺序）造成的。
"""
import importlib.util
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / ".cache/mutbak/r100_build_index.py"
DRY = ROOT / ".cache/r244/_ledger_24496_dry.md"
OUT = ROOT / ".cache/mutbak/_index_24496_probe.md"

if not GEN.exists():
    print("[错误] 找不到生成器 %s" % GEN)
    sys.exit(2)
if not DRY.exists():
    print("[错误] 找不到干跑账本 %s" % DRY)
    sys.exit(2)

spec = importlib.util.spec_from_file_location("r100_build_index", GEN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# ⚖ 只覆盖输入/输出路径，逻辑一行没改
mod.PREREG = DRY
mod.OUT = OUT

mod.main()

b = OUT.read_bytes()
print("")
print("=== 244.96 索引期望值（独立复核）===")
print("index_md5=%s" % hashlib.md5(b).hexdigest())
print("index_lines=%d" % (b.count(b"\n")))
print("index_bytes=%d" % len(b))
