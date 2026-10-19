#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_dose_confound_audit —— `dose_confound_audit.py` 的变异台（修订 244.48）

⚖ 纪律（同本项目其它台架）：
  1. needle **唯一命中、落在代码行、不在前导缩进里**；
  2. 替换后必须断言**旧串真的消失**（新串含回旧串时除外），并 `ast.parse`；
  3. ⛔ 期望标签必须是**具体那一条自检**。

跑法：python3 mut_dose_confound_audit.py
"""

import argparse
import ast
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "dose_confound_audit.py")


def find_code_line(src, needle):
    hits = []
    for i, line in enumerate(src.split("\n"), 1):
        pos = line.find(needle)
        if pos < 0:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            raise AssertionError("needle 落在第 %d 行的**注释**上" % i)
        if pos < (len(line) - len(stripped)):
            raise AssertionError("needle 落在第 %d 行的前导缩进里" % i)
        hits.append((i, line))
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1）：%r" % (len(hits), needle))
    return hits[0]


def apply_mutation(src, needle, repl):
    lineno, line = find_code_line(src, needle)
    out = src.replace(line, line.replace(needle, repl, 1))
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle)
    assert repl in out, "新串没进去：%r" % repl
    if needle not in repl:
        assert needle not in out, "替换没落地（旧串仍在）：%r" % needle
    return out, lineno


MUTATIONS = [
    # P1 账本基准被改 ⇒ C1（必须复现 12/14 / 6/14）必红
    ("P1", 'LEDGER_COUNT = {"w": 12, "rand": 6}',
     'LEDGER_COUNT = {"w": 11, "rand": 6}', "C4"),

    # P2 平票口径改成「算真」⇒ C1（平票不算真）必红
    ("P2", "if sum(v) * 2 > len(v))", "if sum(v) * 2 >= len(v))", "C1"),

    # P3 缺读数闸被拆 ⇒ C2（缺 p9_lo_meas 必须拒读）必红
    ("P3", "if lo is None or hi is None:", "if False:", "C2"),

    # P4 坏行闸被拆 ⇒ C3（有坏 JSON 必须拒读）必红
    ("P4", "if bad:", "if False:", "C3"),

    # P5 「剂量混合」判据被写成恒假 ⇒ C2 必红
    ("P5", "mixed = (len(scopes) > 1 and len({r[\"inject_n_sites\"] for r in ks}) > 1)",
     "mixed = False", "C4"),

    # P6 并列秩取「第一个」而不是平均 ⇒ C0c 必红（并列必须平均秩）
    ("P6", "avg = (i + j) / 2.0 + 1", "avg = i + 1.0", "C0c"),
]


def _load(path, src=None):
    mod = types.ModuleType("dca_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_selftest(mod):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = mod.selftest()
    except Exception as e:
        return 3, "%s: %s" % (type(e).__name__, e)
    txt = buf.getvalue()
    return rc, "%s自检 %d/%d" % (txt, txt.count("[PASS]"),
                                txt.count("[PASS]") + txt.count("[FAIL]"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    args = ap.parse_args()

    base = io.open(args.target, encoding="utf-8").read()
    rc0, t0 = run_selftest(_load(args.target))
    print("台架基线：rc=%d ｜ %s" % (rc0, t0.strip().split("\n")[-1]))
    if rc0 != 0:
        print("[FAIL] T0 基线不绿 ⇒ 台架无效，先修工具")
        return 1

    allok = True
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, ln = apply_mutation(base, needle, repl)
            ast.parse(mut_src)
        except (AssertionError, SyntaxError) as e:
            print("[FAIL] T1.%s 变异串无法定位或写坏了源码：%s" % (name, e))
            allok = False
            continue
        rc, txt = run_selftest(_load(args.target, mut_src))
        if rc == 3:
            print("[FAIL] T2.%s 变异后工具**崩**（%s）⇒ ⛔ 崩 ≠ 按判据变红"
                  % (name, txt[:70]))
            allok = False
            continue
        line = next((l.strip() for l in txt.split("\n")
                     if l.startswith("[FAIL] %s " % expect)), None)
        if line:
            print("[PASS] %s 第 %s 行 ⇒ %s 转红" % (name, ln, expect))
            print("        ↳ %s" % line[:112])
        else:
            print("[FAIL] T3.%s 第 %s 行 ⇒ %s **没有转红** ⛔" % (name, ln, expect))
            allok = False

    n = len(MUTATIONS)
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
