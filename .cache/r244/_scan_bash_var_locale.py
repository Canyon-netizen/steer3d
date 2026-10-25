#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ 扫 shell 脚本里「**裸** `$VAR` 紧跟非 ASCII 字符」的写法。

⚖⚖⚖ **为什么要扫**：某些 locale（例如本机的 `LC_CTYPE=C.UTF-8`）下，bash 会把全角标点的
首字节当成**标识符字符** ⇒ ⇒ `$MSG（…` 被解析成变量 `MSG…` ⇒ ⇒ `set -u` 立刻报
`unbound variable` ⇒ ⇒ 提交链当场断（**`bash -n` 查不出来**，只在运行期炸）。

⚖ 修法：写成 `${MSG}`（显式闭合变量名）。
⚖ ⛔ **注释行不算**（bash 不解析注释里的内容）。
"""

import io
import re
import sys

PAT = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")


def scan(path):
    lines = io.open(path, encoding="utf-8").read().split("\n")
    hits = []
    for i, l in enumerate(lines, 1):
        s = l.lstrip()
        if s.startswith("#"):
            continue
        for m in PAT.finditer(l):
            e = m.end()
            if e < len(l) and ord(l[e]) >= 0x80:
                hits.append((i, m.group(0), l))
                break
    return hits


def main():
    bad_total = 0
    for p in sys.argv[1:]:
        hits = scan(p)
        if hits:
            bad_total += len(hits)
            for i, v, l in hits:
                print("⛔ %s:%d  裸 $%s 紧跟非 ASCII" % (p, i, v))
                print("     %s" % l)
    if bad_total == 0:
        print("✅ 全部通过：代码行里没有「裸 $VAR 紧跟非 ASCII」的写法")
    print("BAD_TOTAL=%d" % bad_total)
    return 1 if bad_total else 0


if __name__ == "__main__":
    sys.exit(main())
