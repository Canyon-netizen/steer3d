#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""落账后的**回读核对**（⛔ 不改任何文件，只读并打印）。

核对四件事：
  ① 账本行数 / 字节 / md5
  ② 围栏数（追加前 761 ⇒ 追加后必须仍是 761）
  ③ 新增标题「## 修订 244.80 / 244.81」各出现几次、行号在哪
  ④ 索引里能不能查到这两条修订
"""
import hashlib
import io
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
L = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
I = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")


def main():
    t = io.open(L, encoding="utf-8", newline="").read()
    lines = t.split("\n")
    print("账本：%d 行 ｜ %d 字节 ｜ md5 %s"
          % (t.count("\n"), len(t.encode("utf-8")),
             hashlib.md5(t.encode("utf-8")).hexdigest()))
    fences = sum(1 for l in lines if l.strip().startswith("```"))
    print("围栏数：%d（追加前是 761 ⇒ 必须不变）" % fences)
    for rev in ("244.80", "244.81"):
        idx = [i + 1 for i, l in enumerate(lines) if l.startswith("## 修订 %s " % rev)]
        print("标题「## 修订 %s」：%d 条 ｜ 行号 %s" % (rev, len(idx), idx))
        for i in idx:
            print("   行 %d：%s" % (i, lines[i - 1][:76]))
    it = io.open(I, encoding="utf-8", newline="").read()
    for rev in ("244.80", "244.81"):
        hit = [l.strip() for l in it.split("\n") if ("修订 %s" % rev) in l]
        print("索引里「修订 %s」：%d 条" % (rev, len(hit)))
        for h in hit:
            print("   %s" % h[:110])
    return 0


if __name__ == "__main__":
    sys.exit(main())
