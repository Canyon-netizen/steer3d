#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **提交后双回读**（账本 ＋ 索引）：**断言式**，每条都能红（244.82）。

核对七件事（⛔ 任何一条不过 ⇒ 退出码非 0 ⇒ 提交链判红）：
  A. **旧前缀逐字节不变**：账本前 2540773 字节的 md5 必须仍等于追加 244.82 之前的
     `30045599a8666d6bc5b2e4d65fe0e178`（⇒ ⇒ 「账本只追加」这条前提**被验过**，不是口头说的）
  B. 账本总量：41589 行 / 2548316 字节 / md5 `9c7158c17095b3ca3ceaf7f22b1d12a7`
  C. 围栏数仍是 761（追加正文不许带进新围栏）
  D. 标题「## 修订 244.80」@41249、「## 修订 244.81」@41382、「## 修订 244.82」@41522，各恰好 1 条
  E. 索引里这三条修订各命中 1 条
  F. **工作区与 HEAD 逐位一致**（账本、索引各一次）
  G. HEAD 这次提交**只带**白名单里的那些路径（⛔ 不能卷进同事的改动）
  H. **R3 收据里的账本 md5 == 本次提交里那份**（⇒ ⇒ 「R3 验的就是本次提交里那份字节」）

自证（能红）：把账本**截短**一份喂进同一套断言 ⇒ 必须判红。
"""

import hashlib
import io
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = ".cache/xcheck/R6_RERUN_PREREG.md"
INDEX = ".cache/xcheck/R6_RERUN_INDEX.md"

# 追加 244.82 之前的账本（前缀必须逐字节不变）
PREFIX_BYTES = 2540773
PREFIX_MD5 = "30045599a8666d6bc5b2e4d65fe0e178"
# 追加 244.82 之后的账本
FULL_LINES = 41589
FULL_BYTES = 2548316
FULL_MD5 = "9c7158c17095b3ca3ceaf7f22b1d12a7"
FENCES = 761
REV_ROWS = {"244.80": 41249, "244.81": 41382, "244.82": 41522}

WHITELIST = [
    ".cache/r244/premise_independence_audit.py",
    ".cache/r244/mut_premise_independence_audit.py",
    ".cache/r244/_cross_check_24482.py",
    ".cache/r244/_run_24482_verify.sh",
    ".cache/r244/_run_24482_reg_shm.sh",
    ".cache/r244/_fetch_r3_receipt.sh",
    ".cache/r244/_append_24482.py",
    ".cache/r244/_commit_msg_24482.py",
    ".cache/r244/_make_handoff_24482.py",
    ".cache/r244/_post_commit_readback_24482.py",
    ".cache/r244/_commit_24482.sh",
    ".cache/xcheck/R6_PREMISE_INDEPENDENCE_PREREG.md",
    LEDGER,
    INDEX,
]


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _read_bytes(rel):
    with io.open(os.path.join(REPO, rel), "rb") as fh:
        return fh.read()


def _git(*a):
    p = subprocess.Popen(["git"] + list(a), cwd=REPO, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        return None
    return out


def _assertions(ledger_bytes, index_text, tag):
    res = []
    ok = True

    def chk(name, cond, detail):
        nonlocal ok
        res.append((name, bool(cond), detail))
        if not cond:
            ok = False

    pre = ledger_bytes[:PREFIX_BYTES]
    chk("A 旧前缀逐字节不变", len(pre) == PREFIX_BYTES and _md5(pre) == PREFIX_MD5,
        "前 %d 字节 md5 = %s（期望 %s）"
        % (PREFIX_BYTES, _md5(pre) if len(pre) == PREFIX_BYTES else "(不足)", PREFIX_MD5))
    t = ledger_bytes.decode("utf-8")
    nlines = t.count("\n")
    chk("B 账本总量", nlines == FULL_LINES and len(ledger_bytes) == FULL_BYTES
        and _md5(ledger_bytes) == FULL_MD5,
        "%d 行 / %d 字节 / md5 %s（期望 %d / %d / %s）"
        % (nlines, len(ledger_bytes), _md5(ledger_bytes), FULL_LINES, FULL_BYTES, FULL_MD5))
    fences = sum(1 for l in t.split("\n") if l.strip().startswith("```"))
    chk("C 围栏数不变", fences == FENCES, "%d（期望 %d）" % (fences, FENCES))
    lines = t.split("\n")
    for rev, row in REV_ROWS.items():
        idx = [i + 1 for i, l in enumerate(lines) if l.startswith("## 修订 %s " % rev)]
        chk("D 标题「## 修订 %s」" % rev, idx == [row],
            "%d 条，行号 %s（期望 1 条 @ %d）" % (len(idx), idx, row))
    for rev in REV_ROWS:
        hit = [l for l in index_text.split("\n") if ("修订 %s" % rev) in l]
        chk("E 索引命中「修订 %s」" % rev, len(hit) == 1, "%d 条（期望 1）" % len(hit))
    print("──── %s ────" % tag)
    for name, good, detail in res:
        print("  %s %-28s %s" % ("✅" if good else "⛔", name, detail))
    return ok, res


def main():
    names = _git("show", "--name-only", "--pretty=format:", "HEAD")
    got = sorted([n for n in (names or b"").decode("utf-8").split("\n") if n.strip()])
    want = sorted(WHITELIST)
    extra = [n for n in got if n not in want]
    missing = [n for n in want if n not in got]
    g_ok = (not extra) and (not missing)
    print("──── G 这次提交只带白名单路径 ────")
    print("  %s 提交带了 %d 个路径（期望 %d）｜ 清单外 %s ｜ 清单内漏掉 %s"
          % ("✅" if g_ok else "⛔", len(got), len(want), extra or "无", missing or "无"))
    if not g_ok:
        return 1

    f_ok = True
    print("──── F 工作区 vs HEAD 逐位一致 ────")
    for rel in (LEDGER, INDEX):
        a = _read_bytes(rel)
        b = _git("show", "HEAD:%s" % rel)
        if b is None:
            print("  ⛔ %s ｜ HEAD 里读不到" % rel)
            f_ok = False
            continue
        same = (_md5(a) == _md5(b))
        if not same:
            f_ok = False
        print("  %s %s ｜ 工作区 md5 = %s ｜ HEAD md5 = %s"
              % ("✅" if same else "⛔", rel, _md5(a), _md5(b)))
    if not f_ok:
        return 1

    ledger_bytes = _read_bytes(LEDGER)
    index_text = _read_bytes(INDEX).decode("utf-8")
    ok, _res = _assertions(ledger_bytes, index_text, "A–E 账本 / 索引断言")
    if not ok:
        return 1

    cut = ledger_bytes.rfind(b"\n", 0, PREFIX_BYTES - 10)

    # ---- H：R3 收据里的账本 md5 == 本次提交里那份（⇒ 「R3 验的就是提交里那份字节」）
    regp = os.path.join(REPO, ".cache", "r244", "_e24482", "reg_24482.txt")
    if os.path.isfile(regp):
        reg = io.open(regp, encoding="utf-8", errors="replace").read()
        m = re.search(r"ledger_lines=(\d+)\s+ledger_md5=(\w+)", reg)
        h_ok = bool(m) and (m.group(2) == _md5(ledger_bytes)) and (int(m.group(1)) == FULL_LINES)
        print("──── H R3 收据的账本 md5 == 本次提交里那份 ────")
        print("  %s R3 收据：%s 行 / md5 %s ｜ 提交里那份：%s 行 / md5 %s"
              % ("✅" if h_ok else "⛔",
                 m.group(1) if m else "(缺)", m.group(2) if m else "(缺)",
                 FULL_LINES, _md5(ledger_bytes)))
        if not h_ok:
            return 1
    else:
        print("──── H R3 收据的账本 md5 == 本次提交里那份 ────")
        print("  ⛔ 缺 R3 收据：%s ⇒ ⇒ 这条没验到" % regp)
        return 1

    short = ledger_bytes[:cut] if cut > 0 else ledger_bytes[:PREFIX_BYTES - 10]
    ok2, res2 = _assertions(short, index_text, "自证：截短账本（必须判红）")
    bad = [n for n, good, _d in res2 if not good]
    print("  %s 自证：截短后有 %d 条判红（%s）⇒ ⇒ 这套断言**能红**"
          % ("✅" if (not ok2 and bad) else "⛔", len(bad), "、".join(bad[:3])))
    if ok2 or not bad:
        print("⛔ 自证失败：这套断言在账本被截短时居然全绿 ⇒ 它是恒绿的，不能用")
        return 1

    print()
    print("✅ 提交后双回读全过（账本 ＋ 索引 ＋ 提交清单）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
