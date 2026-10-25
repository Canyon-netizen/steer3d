#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **生成 244.89 双回读的期望值**（落账之后、提交之前跑一次）。

⚖ **它做什么**：
   ① 核对账本**追加 244.89 之前**的那段字节 ⇒ **必须**等于 244.88 那次提交里的那份
      （硬编码：%d 字节 / md5 %s）⇒ ⇒ 「落账没动旧字节」是**独立**核对的，不是自说自话；
   ② 把追加之后的**整份**账本的 行数/字节/md5、围栏数、每条「## 修订 N」的行号
      **写进** `_post_commit_readback_24489.py` 的 FACTS 块 ⇒ ⇒ 提交后再回读时逐条对账。
"""

import hashlib
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
TARGET = os.path.join(HERE, "_post_commit_readback_24489.py")

# 244.88 那次提交里的那份账本（**硬编码** ⇒ 独立核对）
PREFIX_BYTES = 2643525
PREFIX_MD5 = "17557c5a4c9cc423d275def382d43b4f"


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
    rev_rows = {}
    for i, l in enumerate(lines):
        m = re.match(r"^## 修订 (\d+\.\d+) ", l)
        if m:
            rev_rows.setdefault(m.group(1), []).append(i + 1)
    if "244.89" not in rev_rows:
        print("⛔ 账本里没有「## 修订 244.89」这一段 ⇒ 先落账")
        return 3
    if len(rev_rows["244.89"]) != 1:
        print("⛔ 账本里有 %d 段「## 修订 244.89」⇒ ⇒ 停下" % len(rev_rows["244.89"]))
        return 3
    print("✅ 244.89 段：行 %s" % rev_rows["244.89"])

    facts = "\n".join([
        "# ==== BEGIN FACTS（由 _gen_readback_24489.py 写入）====",
        "PREFIX_BYTES = %d" % PREFIX_BYTES,
        'PREFIX_MD5 = "%s"' % PREFIX_MD5,
        "FULL_LINES = %d" % full_lines,
        "FULL_BYTES = %d" % full_bytes,
        'FULL_MD5 = "%s"' % full_md5,
        "FENCES = %d" % fences,
        "REV_ROWS = %r" % (rev_rows,),
        "# ==== END FACTS ====",
    ])

    src = io.open(TARGET, encoding="utf-8").read()
    new, n = re.subn(r"# ==== BEGIN FACTS.*?# ==== END FACTS ====", facts, src, flags=re.S)
    if n != 1:
        print("⛔ FACTS 块替换了 %d 处（期望 1）" % n)
        return 3
    with io.open(TARGET, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print("✅ 已写入 %s" % TARGET)
    print("   整份账本：%d 行 / %d 字节 / md5 %s ｜ 围栏 %d ｜ 修订条目 %d"
          % (full_lines, full_bytes, full_md5, fences, len(rev_rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
