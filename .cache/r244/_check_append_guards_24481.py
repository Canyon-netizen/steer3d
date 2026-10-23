#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⛔ 临时检查器（用完即删）：验「即将追加的两段正文」不会把读账本的护栏弄红。

⚖ 复用被测工具**自己的**扫描函数（`ledger_placeholder_audit.scan` / `scan_bold`）
   ⇒ ⛔ 不另写一套规则（两处不一致本身就是一类错）。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import ledger_placeholder_audit as LPA  # noqa: E402

LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")


def read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def main():
    base = read(LEDGER)
    secs = {}
    for n in ("24480", "24481"):
        sc = os.path.join(HERE, "_append_%s.py" % n)
        sys.argv = [sc, "--dry"]
        import subprocess
        out = subprocess.run([sys.executable, sc, "--dry"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        txt = out.stdout.decode("utf-8")
        i = txt.find("## 修订 ")
        j = txt.rfind("（--dry")
        assert i > 0 and j > i, "⛔ %s 的 dry 输出形状变了" % n
        secs[n] = txt[i:j]
    for n, s in secs.items():
        print("== %s：%d 字符 / %d 行" % (n, len(s), s.count("\n")))

    # ① 占位符：追加后**整本**账本的标记集合必须与登记集合一致
    after = base + secs["24480"] + secs["24481"]
    prose, allm = LPA.scan(after)
    base_prose, base_allm = LPA.scan(base)
    new_allm = sorted(allm - base_allm)
    print("① 新出现的标记：%s" % (new_allm or "无"))
    new_prose = [p for p in prose if p not in base_prose]
    print("① 新出现的正文占位符：%s" % (new_prose or "无"))

    # ② 正文里字面 `****`：追加后行数必须与登记数一致
    b_bold = dict()
    for _m, ln in LPA.scan_bold(base):
        b_bold.setdefault(ln, 0)
        b_bold[ln] += 1
    a_bold = dict()
    for _m, ln in LPA.scan_bold(after):
        a_bold.setdefault(ln, 0)
        a_bold[ln] += 1
    new_bold = sorted(set(a_bold) - set(b_bold))
    print("② 新长出的 `****` 行：%s" % (new_bold or "无"))
    print("② 登记数 N_BOLD_LINES=%d ｜ 落账前命中行=%d ｜ 落账后命中行=%d"
          % (LPA.N_BOLD_LINES, len(b_bold), len(a_bold)))

    # ③ 登记行号必须仍然指向同一行（只追加 ⇒ 旧行号不动）
    #    ⚖ 比较方式照抄 C3 的真实判法：**原文**逐字比（⛔ 不是归一化版 —— 244.65 改过）
    lines = after.split("\n")
    drift = []
    for ln, marks, raw in LPA.HOLE_LINES:
        if ln > len(lines):
            drift.append((ln, "行不存在"))
            continue
        if lines[ln - 1] != raw:
            drift.append((ln, "原文已变"))
    print("③ 登记行漂移：%s" % (drift or "无"))

    bad = bool(new_allm) or bool(new_prose) or bool(new_bold) or bool(drift)
    print("⇒ %s" % ("🔴 有风险" if bad else "✅ 追加后护栏不受影响（标记/粗体/登记行 三项都没动）"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
