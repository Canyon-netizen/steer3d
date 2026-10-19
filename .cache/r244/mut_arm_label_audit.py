#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_arm_label_audit —— `arm_label_audit.py` 的变异台（修订 244.52，6 条）

⚖ 纪律（同本项目其它台架）：
  1. needle **唯一命中、落在代码行、不在前导缩进里**；
  2. 替换后必须断言**旧串真的消失**（新串含回旧串时除外），并 `ast.parse`。

⚖⚠⚠⚖ 本台最要紧的一条是 **M4**：
  指纹**排除 `arm` 字段**是整份审计的地基 —— 不排除，同一批测量会被拆成两个「臂」，
  而自检 C9（只差 arm 字段 ⇒ 必须并成 1 簇）是唯一钉住它的用例。

跑法：python3 mut_arm_label_audit.py
"""

import argparse
import ast
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "arm_label_audit.py")


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
    # M1 C2 的「恰好两簇」判词被焊成永远成立 ⇒ 干净夹具上 C2 必红
    ("M1", 'if two else', 'if True else', "C11"),

    # ⚖ M2 跨簇标签检测被拆掉 ⇒ X 横跨两簇时 C6/C7 必红
    ("M2", "if len(s) > 1}", "if False}", "C6"),

    # M3 引用文件的标签核对被焊成永远「正确」⇒ C8 必红
    ("M3", "good = (labs == [arm])", "good = True", "C8"),

    # ⚖⚠⚠⚖ M4 **本台最要紧的一条**：指纹不再排除 `arm`
    #   ⇒ 只差 arm 字段的两份文件被拆成两簇 ⇒ C9 必红。
    ("M4", 'd = {k: v for k, v in rec.items() if k != "arm"}', "d = dict(rec)", "C9"),

    # M5 「无横跨」那句判词被删 ⇒ C3 必红
    ("M5", '"     ⇒ ✅ 没有标签横跨两簇"', '"     ⇒ (略)"', "C3"),

    # M6 C5 的「两种口径一致」判词被焊成永远成立 ⇒ C5 必红
    ("M6", "if agree else", "if True else", "C7"),
]


def _load(path, src=None):
    mod = types.ModuleType("ala_mut")
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
