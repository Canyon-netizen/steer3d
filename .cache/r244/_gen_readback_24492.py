#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_gen_readback_24492.py —— 生成 244.92 的**提交后双回读**事实块（落账之后、提交之前跑）。

⚖ **期望值的出处**：
   · **旧前缀**（追加 244.92 之前的那份账本）⇒ ⇒ **硬编码**（＝ 244.89 那次提交里的那份字节）
     ⇒ ⇒ 「落账没动旧字节」这条**不依赖任何生成物**。
   · **追加之后的整份**（行数 / 字节 / md5 / 围栏数 / 每一修订的行号）⇒ ⇒ 由本脚本**现算**。
   · **修订行号表** ⇒ ⇒ 由本脚本从**追加后的账本**里现扫 ⇒ ⇒ 若有人在生成与提交之间动过账本 ⇒ ⇒ 回读立刻判红。
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
TARGET = os.path.join(REPO, ".cache", "r244", "_post_commit_readback_24492.py")

# ⚖ **旧前缀**（＝ 244.89 那次提交里的那份账本）——⛔ 手写，不许现算
PREFIX_BYTES = 2669016
PREFIX_MD5 = "dca770b663b1187efeeb58841820a0ba"


def md5b(b):
    return hashlib.md5(b).hexdigest()


def main():
    with io.open(LEDGER, "rb") as fh:
        b = fh.read()
    t = b.decode("utf-8")
    lines = t.split("\n")
    fences = sum(1 for l in lines if l.strip().startswith("```"))
    rev_rows = {}
    for i, l in enumerate(lines):
        m = re.match(r"^## 修订 (\d+\.\d+[a-z]?) ", l)
        if m:
            rev_rows.setdefault(m.group(1), []).append(i + 1)
    facts = {
        "PREFIX_BYTES": PREFIX_BYTES,
        "PREFIX_MD5": PREFIX_MD5,
        "FULL_LINES": t.count("\n"),
        "FULL_BYTES": len(b),
        "FULL_MD5": md5b(b),
        "FENCES": fences,
        "REV_ROWS": rev_rows,
    }
    with io.open(TARGET, encoding="utf-8") as fh:
        src = fh.read()
    block = (
        "# ==== BEGIN FACTS（由 _gen_readback_24492.py 写入）====\n"
        "PREFIX_BYTES = %d\n"
        "PREFIX_MD5 = \"%s\"\n"
        "FULL_LINES = %d\n"
        "FULL_BYTES = %d\n"
        "FULL_MD5 = \"%s\"\n"
        "FENCES = %d\n"
        "REV_ROWS = %r\n"
        "# ==== END FACTS ====" % (
            facts["PREFIX_BYTES"], facts["PREFIX_MD5"], facts["FULL_LINES"],
            facts["FULL_BYTES"], facts["FULL_MD5"], facts["FENCES"], facts["REV_ROWS"])
    )
    # ⚖⚖⚖ **先分清「块不存在」与「块已是最新」**（⛔ 两者都会让 `re.sub` 产出同样的文本 ⇒ ⇒ 旧写法会把
    #    「已是最新」误报成「没找到块」⇒ ⇒ 直接把提交卡死）
    if not re.search(r"# ==== BEGIN FACTS.*?# ==== END FACTS ====", src, flags=re.S):
        print("⛔ 没找到 FACTS 块 ⇒ ⇒ 中止")
        return 2
    new = re.sub(r"# ==== BEGIN FACTS.*?# ==== END FACTS ====", block, src, count=1, flags=re.S)
    if new == src:
        print("FACTS 块**已是最新**（逐字节相同）⇒ ⇒ 不重写")
        print("已核对事实块：%d 行 / %d 字节 / md5 %s ｜ 围栏 %d ｜ 修订 %d 条"
              % (facts["FULL_LINES"], facts["FULL_BYTES"], facts["FULL_MD5"],
                 facts["FENCES"], len(facts["REV_ROWS"])))
        print("GEN_RC=0")
        return 0
    with io.open(TARGET, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print("已写入事实块：%d 行 / %d 字节 / md5 %s ｜ 围栏 %d ｜ 修订 %d 条"
          % (facts["FULL_LINES"], facts["FULL_BYTES"], facts["FULL_MD5"],
             facts["FENCES"], len(facts["REV_ROWS"])))
    print("GEN_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
