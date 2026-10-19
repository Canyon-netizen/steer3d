#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_flip_robustness —— `flip_robustness.py` 的变异台（修订 244.47）

⚖⚠⚖ 变异设计的三条硬规矩（244.43–244.46 累计踩出来的）：
  1. needle **唯一命中、落在代码行、不在前导缩进里**；
  2. **块 needle 走 `src.replace` 整块替换**（单行查找对多行串必然 0 命中）；
  3. ⚖⚠⚠⚖ 替换后必须断言**旧串真的消失**（若新串合法含回旧串则例外），
     并且 `ast.parse` 变异后的源码 —— ⛔ 变异不许把工具写坏。

跑法：python3 mut_flip_robustness.py
退出码：0 = 全部变异都被指定的那条自检抓住；1 = 有变异存活或基线不绿。
"""

import argparse
import ast
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "flip_robustness.py")


def find_code_line(src, needle):
    hits = []
    for i, line in enumerate(src.split("\n"), 1):
        pos = line.find(needle)
        if pos < 0:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            raise AssertionError("needle 指到第 %d 行第 %d 列，那一行是**注释**" % (i, pos))
        if pos < (len(line) - len(stripped)):
            raise AssertionError("needle 指到第 %d 行第 %d 列，落在前导缩进里" % (i, pos))
        hits.append((i, line))
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1）：%r" % (len(hits), needle))
    return hits[0]


def apply_block(src, old, new):
    n = src.count(old)
    if n != 1:
        raise AssertionError("块 needle 命中 %d 处（要求恰好 1）" % n)
    out = src.replace(old, new, 1)
    if out == src:
        raise AssertionError("块替换没有产生任何变化")
    assert new in out, "新块没进去"
    if old not in new:
        assert old not in out, "旧块仍在 ⇒ 替换没落地"
    return out, src[:src.index(old)].count("\n") + 1


def apply_mutation(src, needle, repl):
    if "\n" in needle:
        return apply_block(src, needle, repl)
    lineno, line = find_code_line(src, needle)
    out = src.replace(line, line.replace(needle, repl, 1))
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle)
    assert repl in out, "新串没进去：%r" % repl
    if needle not in repl:
        assert needle not in out, "替换没落地（旧串仍在）：%r" % needle
    return out, lineno


MUTATIONS = [
    # N1 两尾改成单尾 ⇒ C4 必须红（账本口径是 0.01294）
    ("N1", "return min(1.0, 2.0 * one)", "return min(1.0, one)", "C4"),

    # N2 两尾的另一半取错：只用 k，不再看 n−k ⇒ C4 必须红
    #   ⚖⚠ 这一条是「对称性写错」的典型：k>n/2 时另一半必须用 n−k
    ("N2", "one = binom_sf(n, max(k, n - k), 0.5)",
     "one = binom_sf(n, k, 0.5)", "C4b"),

    # N3 平票改成「一律算正」⇒ C7 必须红（可复现性 + 口径）
    ("N3", "return ds[0] > 0", "return True", "C7"),

    # N4 CP 下界的二分方向写反 ⇒ C5 必须红（L 会恒为 1）
    ("N4", "if binom_sf(n, x, mid) < alpha:", "if binom_sf(n, x, mid) > alpha:", "C5"),

    # N5 CP 上界的二分方向写反 ⇒ C6 必须红（U 会恒为 0）
    ("N5", "if sum(binom_pmf(n, j, mid) for j in range(0, x + 1)) > alpha:",
     "if sum(binom_pmf(n, j, mid) for j in range(0, x + 1)) < alpha:", "C6"),

    # N6 binom_sf 求和区间写反 ⇒ C1 必须红
    ("N6", "return sum(binom_pmf(n, j, p) for j in range(k, n + 1))",
     "return sum(binom_pmf(n, j, p) for j in range(0, k))", "C1"),

    # N7 空读数闸被拆 ⇒ C9-空读数 必须红（不许当 0）
    ("N7", "if not ds:", "if False:", "C9-空读数"),

    # N8 launch 数一致性闸被拆 ⇒ C9-launch 数不一致 必须红
    ("N8", "if len(rs) > 1:", "if False:", "C9-launch 数不一致"),

    # N9 偶数 R 的平票按「全算正」破 ⇒ C2 必须红（多数概率不再是 0.5）
    ("N9", "return sum(math.comb(R, j) * half for j in range(R // 2 + 1, R + 1)) + 0.5 * ties",
     "return sum(math.comb(R, j) * half for j in range(R // 2 + 1, R + 1)) + ties", "C2"),
]


def _load(path, src=None):
    mod = types.ModuleType("fr_mut")
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
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    txt = buf.getvalue()
    return rc, "%s自检 %d/%d 通过" % (txt, txt.count("[PASS]"),
                                     txt.count("[PASS]") + txt.count("[FAIL]"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    args = ap.parse_args()

    base = io.open(args.target, encoding="utf-8").read()
    mod = _load(args.target)
    rc0, t0 = run_selftest(mod)
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
        m2 = _load(args.target, mut_src)
        rc, txt = run_selftest(m2)
        if rc == 3:
            print("[FAIL] T2.%s 变异后工具**崩**（%s）⇒ ⛔ 崩 ≠ 按判据变红"
                  % (name, txt.split("\n")[0][:70]))
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
