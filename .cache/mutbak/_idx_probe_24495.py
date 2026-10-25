#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""244.95 索引期望值探针（**一次性**，用完即删）。

⚠ 目的：R14 驱动里的 `__INDEX_MD5__` / `__INDEX_LINES__` 必须**手写期望值**，
  ⛔ 不能留占位符（留了就不成闸门），也不能在跑的时候现算（现算 ⇒ 恒绿）。

⚖ 本探针的做法：**不复制生成器的逻辑**，而是 import 原生成器、只覆盖它的
  两个路径常量（PREREG / OUT），⇒ 算出来的 md5 与落账后真跑
  `python3 .cache/mutbak/r100_build_index.py` 的输出**逐字节同源**。

⚠ 输入是**落账前的干跑副本**（`_ledger_24495_dry.md`），
  它与真落账后的账本逐字节相同（md5 已在落账前核过）。
"""
import importlib.util
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / ".cache/mutbak/r100_build_index.py"
DRY = ROOT / ".cache/r244/_ledger_24495_dry.md"
OUT = ROOT / ".cache/mutbak/_index_24495_probe.md"

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
print("=== 244.95 索引期望值（可回填进 R14 驱动）===")
print("index_md5=%s" % hashlib.md5(b).hexdigest())
print("index_lines=%d" % (b.count(b"\n")))
print("index_bytes=%d" % len(b))
