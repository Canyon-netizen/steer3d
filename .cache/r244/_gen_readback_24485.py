#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.85 双回读的期望值**（落账之后、提交之前跑一次）。

⚖ **它做什么**：
   ① 核对账本**追加 244.85 之前**的那段字节 ⇒ **必须**等于 244.84 那次提交里的那份
      （硬编码：%d 字节 / md5 %s）⇒ ⇒ 「落账没动旧字节」是**独立**核对的，不是自说自话；
   ② 把追加之后的**整份**账本的 行数/字节/md5、围栏数、每条「## 修订 N」的行号
      **写进** `_post_commit_readback_24485.py` 的 FACTS 块 ⇒ ⇒ 提交后再回读时逐条对账。
"""

import hashlib
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
TARGET = os.path.join(HERE, "_post_commit_readback_24485.py")

# 244.84 那次提交里的那份账本（**硬编码** ⇒ 独立核对）
PREFIX_BYTES = 2572096
PREFIX_MD5 = "a83d97136e326bcf913e1174c0c0600b"


def _md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    with io.open(LEDGER, "rb") as fh:
        data = fh.read()
    text = data.decode("utf-8")

    # ① 旧前缀核对
    pre = data[:PREFIX_BYTES]
    if len(pre) != PREFIX_BYTES or _md5(pre) != PREFIX_MD5:
        print("⛔ 旧前缀对不上：%d 字节 / md5 %s（期望 %d / %s）"
              % (len(pre), _md5(pre) if len(pre) == PREFIX_BYTES else "(不足)",
                 PREFIX_BYTES, PREFIX_MD5))
        return 3
    print("✅ 旧前缀逐字节不变：%d 字节 / md5 %s" % (PREFIX_BYTES, PREFIX_MD5))

    # ② 整份账本的事实
    full_lines = text.count("\n")
    full_bytes = len(data)
    full_md5 = _md5(data)
    fences = sum(1 for l in text.split("\n") if l.strip().startswith("```"))
    lines = text.split("\n")
    # ⚖⚖⚖ 同一修订号**可能有多段**（追加段：第二机旁证 / 补记 ⇒ 按设计复用同一个修订号）
    #   ⇒ ⇒ 这里必须登记**全部**行号（⛔ 只留最后一条 ⇒ ⇒ 回读的「恰好 1 段」断言必红 ⇒ ⇒ 自相矛盾）
    rev_rows = {}
    for i, l in enumerate(lines):
        m = re.match(r"^## 修订 (\d+\.\d+) ", l)
        if m:
            rev_rows.setdefault(m.group(1), []).append(i + 1)
    if "244.85" not in rev_rows:
        print("⛔ 账本里没有「## 修订 244.85」这一段 ⇒ 先落账")
        return 3
    print("✅ 整份账本：%d 行 / %d 字节 / md5 %s ｜ 围栏 %d" % (full_lines, full_bytes, full_md5, fences))
    for k in sorted(rev_rows):
        print("   修订 %s @ %s" % (k, rev_rows[k]))

    # ③ 写进 FACTS 块
    with io.open(TARGET, encoding="utf-8", newline="") as fh:
        src = fh.read()
    block = (
        "# ==== BEGIN FACTS（由 _gen_readback_24485.py 写入）====\n"
        "PREFIX_BYTES = %d\n"
        "PREFIX_MD5 = \"%s\"\n"
        "FULL_LINES = %d\n"
        "FULL_BYTES = %d\n"
        "FULL_MD5 = \"%s\"\n"
        "FENCES = %d\n"
        "REV_ROWS = %r\n"
        "# ==== END FACTS ====" % (PREFIX_BYTES, PREFIX_MD5, full_lines, full_bytes,
                                 full_md5, fences, rev_rows))
    m = re.search(r"# ==== BEGIN FACTS.*?# ==== END FACTS ====", src, re.S)
    if not m:
        print("⛔ %s 里找不到 FACTS 块" % TARGET)
        return 3
    src = src[:m.start()] + block + src[m.end():]
    with io.open(TARGET, "w", encoding="utf-8", newline="") as fh:
        fh.write(src)
    print("✅ 已写入 FACTS：%s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
