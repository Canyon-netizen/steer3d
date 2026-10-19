#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_nmap_coverage_audit —— `nmap_coverage_audit.py` 的变异台（修订 244.53，7 条）

⚖ 纪律（同本项目其它台架）：
  1. needle **唯一命中、落在代码行、不在前导缩进里**；
  2. 替换后必须断言**旧串真的消失**（新串含回旧串时除外），并 `ast.parse`。

⚖⚠⚖⚖ 本台的主线：**「戳」是这份审计的地基**。
  · N2 把「恰好一份与戳相符」焊成恒真 ⇒ 权威文件认错也看不出来；
  · N7 把「兄弟文件」那行判词删掉 ⇒ 用错文件（同名不同戳）就没人提醒；
  · N1 把「两臂戳一致」焊成恒真 ⇒ 两臂用不同 map 也不报。

跑法：python3 mut_nmap_coverage_audit.py
"""

import argparse
import ast
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "nmap_coverage_audit.py")


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
    # N1 两臂戳一致判词被焊成恒真 ⇒ 戳不一致时 C9 必红
    ("N1", '"✅ 全部**逐位一致** ⇒ 两臂用的是同一份 map" if len(all_st) == 1',
     '"✅ 全部**逐位一致** ⇒ 两臂用的是同一份 map" if True', "C9"),

    # N2 权威唯一判词被焊成恒真 ⇒ C2 必红
    # ⚖ N2 改成「按 md5 选权威文件」的那一步被改 ⇒ 选中了**兄弟**（P 全 +1）
    #   ⇒ 分布与 P 立刻对不上 ⇒ 干净夹具的 rc 必须变红 ⇒ C1。
    #   ⚠ 第一版把「恰好一份与戳相符」判词焊成恒真 ⇒ **死变异**（干净夹具上那支恒为真）。
    ("N2", 'auth = [p for p in cands if md5_of(p) == want_md5]',
     'auth = [p for p in cands if md5_of(p) != want_md5]', "C1"),

    # N3 「未命中」那半句被删 ⇒ 覆盖不全时 C8 必红
    ("N3", '"" if not miss else "　⛔ 未命中：%s" % (miss,)', '""', "C8"),

    # N4 P 不等的检查被拆掉 ⇒ C11 必红
    ("N4", "if str(M[t][i_p]) != str(Pm.get(t))]", "if False]", "C11"),

    # N5 分布逐项比较被焊成恒真 ⇒ C5 必红
    # ⚖ N5 期望标签改成 C13（分布**不符**的那份夹具）⇒ 那一支才走得到
    ("N5", "same = (d[k] == LEDGER_P_DIST[k])", "same = True", "C13"),

    # N6 逐格 n_eff 的比较被焊成恒真 ⇒ C10 必红
    ("N6", "if ne == ne_map and ne == P_ + t_:", "if True:", "C10"),

    # N7「兄弟文件」那行判词被删 ⇒ 用错文件没人提醒 ⇒ C2b 必红
    ("N7", '"⚠ **兄弟**：md5 与戳不同，⛔ 不是权威"', '"⚠ (略)"', "C2b"),
]


def _load(path, src=None):
    mod = types.ModuleType("nca_mut")
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
