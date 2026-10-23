#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **提交后双回读**（账本 ＋ 索引）：**断言式**，每条都能红。

核对七件事（⛔ 任何一条不过 ⇒ 退出码非 0 ⇒ 提交链判红）：
  A. **旧前缀逐字节不变**：账本前 2508858 字节的 md5 必须仍等于追加前的
     `c43fce0384192e572515c68503ac5ff7`（⇒ ⇒ 「账本只追加」这条前提**被验过**，不是口头说的）
  B. 账本总量：41521 行 / 2540773 字节 / md5 `30045599a8666d6bc5b2e4d65fe0e178`
  C. 围栏数仍是 761（追加正文不许带进新围栏）
  D. 标题「## 修订 244.80」恰好 1 条且在行 41249；「## 修订 244.81」恰好 1 条且在行 41382
  E. 索引里这两条修订各命中 1 条
  F. **工作区与 HEAD 逐位一致**（账本、索引各一次）
  G. HEAD 这次提交**只带**白名单里的那些路径（⛔ 不能卷进同事的改动）

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

# 追加前的账本（前缀必须逐字节不变）
PREFIX_BYTES = 2508858
PREFIX_MD5 = "c43fce0384192e572515c68503ac5ff7"
# 追加后的账本
FULL_LINES = 41521
FULL_BYTES = 2540773
FULL_MD5 = "30045599a8666d6bc5b2e4d65fe0e178"
FENCES = 761
REV_ROWS = {"244.80": 41249, "244.81": 41382}

WHITELIST = [
    ".cache/r244/probe_compat_check.py",
    ".cache/r244/fixed_dose_pooled_verdict_audit.py",
    ".cache/r244/mut_fixed_dose_pooled_verdict_audit.py",
    ".cache/r244/verify_pooled_verdict_indep.py",
    ".cache/r244/mut_verify_pooled_verdict_indep.py",
    ".cache/r244/_scout_premise_indep.py",
    ".cache/r244/_verify_launcher_bytes_24481.py",
    ".cache/r244/_run_pooled_verdict_24481.sh",
    ".cache/r244/_run_24481_verify.sh",
    ".cache/r244/_run_24481_reg_shm.sh",
    ".cache/r244/_run_24481b_reg_shm.sh",
    ".cache/r244/_land_24480_24481.sh",
    ".cache/r244/_run_r2_24481.sh",
    ".cache/r244/_verify_landing_24481.py",
    ".cache/r244/_check_append_guards_24481.py",
    ".cache/r244/_chain_r2_after_landing.sh",
    ".cache/r244/_fetch_r2_receipt.sh",
    ".cache/r244/_append_24481.py",
    ".cache/r244/_commit_msg_24481.py",
    ".cache/r244/_make_handoff_24481.py",
    ".cache/r244/_post_commit_readback_24481.py",
    ".cache/r244/_commit_24481.sh",
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
    """跑一遍全部断言；返回 (ok, 逐条结果)"""
    res = []
    ok = True

    def chk(name, cond, detail):
        nonlocal ok
        res.append((name, bool(cond), detail))
        if not cond:
            ok = False

    # A. 旧前缀逐字节不变
    pre = ledger_bytes[:PREFIX_BYTES]
    chk("A 旧前缀逐字节不变", len(pre) == PREFIX_BYTES and _md5(pre) == PREFIX_MD5,
        "前 %d 字节 md5 = %s（期望 %s）" % (PREFIX_BYTES, _md5(pre) if len(pre) == PREFIX_BYTES else "(不足)",
                                        PREFIX_MD5))
    # B. 总量
    t = ledger_bytes.decode("utf-8")
    nlines = t.count("\n")
    chk("B 账本总量", nlines == FULL_LINES and len(ledger_bytes) == FULL_BYTES
        and _md5(ledger_bytes) == FULL_MD5,
        "%d 行 / %d 字节 / md5 %s（期望 %d / %d / %s）"
        % (nlines, len(ledger_bytes), _md5(ledger_bytes), FULL_LINES, FULL_BYTES, FULL_MD5))
    # C. 围栏数
    fences = sum(1 for l in t.split("\n") if l.strip().startswith("```"))
    chk("C 围栏数不变", fences == FENCES, "%d（期望 %d）" % (fences, FENCES))
    # D. 两个标题各 1 条且行号正确
    lines = t.split("\n")
    for rev, row in REV_ROWS.items():
        idx = [i + 1 for i, l in enumerate(lines) if l.startswith("## 修订 %s " % rev)]
        chk("D 标题「## 修订 %s」" % rev, idx == [row],
            "%d 条，行号 %s（期望 1 条 @ %d）" % (len(idx), idx, row))
    # E. 索引命中
    for rev in REV_ROWS:
        hit = [l for l in index_text.split("\n") if ("修订 %s" % rev) in l]
        chk("E 索引命中「修订 %s」" % rev, len(hit) == 1, "%d 条（期望 1）" % len(hit))
    print("──── %s ────" % tag)
    for name, good, detail in res:
        print("  %s %-28s %s" % ("✅" if good else "⛔", name, detail))
    return ok, res


def main():
    # ---- G. HEAD 这次提交只带白名单里的路径
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

    # ---- F. 工作区 vs HEAD 逐位一致
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

    # ---- 自证：截短一份（⛔ 切在换行处，别切坏 UTF-8）⇒ 必须判红
    cut = ledger_bytes.rfind(b"\n", 0, PREFIX_BYTES - 10)
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
