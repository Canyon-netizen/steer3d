#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_denom_premise_audit —— `denom_premise_audit.py` 的变异台（修订 244.51，7 条）

⚖ 纪律（同本项目其它台架）：
  1. needle **唯一命中、落在代码行、不在前导缩进里**；
  2. 替换后必须断言**旧串真的消失**（新串含回旧串时除外），并 `ast.parse`；
  3. ⛔ 期望标签必须是**具体那一条自检**。

⚖⚠⚠⚖ 244.51 的两条台架纪律：
  · **期望标签读的是哪一处，就改它读的那一处**。C4/C9b 断言的是**印出来那行**
    ⇒ 变异改的是**打印选择器**，⛔ 不是 `ok &= …`（改 `ok` 只动 rc、不动文字
    ⇒ 期望标签照样过 ⇒ **变异存活**，244.50 的 P11 已经栽过）。
  · **夹具必须落在要验的那个维度上**。均匀剂量的合成夹具上分档表恒稳
    ⇒ 「脆弱」那条判词恒为假 ⇒ Q4 在它上面是死变异
    ⇒ 自检 C9 用**真数据冻结的黄金剂量轴**（109 格）来钉它。

跑法：python3 mut_denom_premise_audit.py
"""

import argparse
import ast
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "denom_premise_audit.py")


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
    # Q1 批次同一性恒判「相同」⇒ 两臂键不同的夹具上 C6 必红
    ("Q1", "same = (kw == kr)", "same = True", "C6"),

    # Q2 C3 的「差值是否恒定」被焊成恒真 ⇒ 差不恒定的夹具上 C7 必红
    ("Q2", "uniform = (len(uniq) == 1 and uniq[0] > 0)", "uniform = True", "C7"),

    # ⚖ Q3 期望标签断言的是**印出来那行** ⇒ 改**打印选择器**，⛔ 不改 ok
    # ⚠⚠⚠ 第一版把期望标成 **C4** ⇒ 死变异活下来了：C4 跑在**干净夹具**上，
    #   而那里的 rho 本来就 > 0.6 ⇒ 那支判词**恒为真** ⇒ 焊成 True 看不出来。
    #   ⚖⇒ 期望标签必须指向**走得到那一支**的夹具（C4c 的反向剂量夹具）。
    ("Q3", '"✅ 符号与量级都稳" if rho_lo > 0.6 else', '"✅ 符号与量级都稳" if True else', "C4c"),

    # ⚖⚠ Q4 同上：分档表脆弱那条判词。C9 用**真剂量轴黄金样本**（distinct=2）
    #   ⇒ 把它焊成「完全一致」必被 C9b 抓住。
    #   ⚠ 在**均匀剂量**的合成夹具上这条是**死变异**（恒稳 ⇒ 恒绿）。
    ("Q4", '"✅ 四个扰动下**分档表完全一致**" if stable_bands else',
     '"✅ 四个扰动下**分档表完全一致**" if True else', "C9b"),

    # Q5 「复现账本的 +4」被焊成恒真 ⇒ 偏移改成 +7 的夹具上 C8 必红
    ("Q5", "if uniq == [TEMPLATE_OFFSET] else", "if True else", "C8"),

    # ⚖⚠⚠ Q6 **本工具最重要的一条守卫**：C1 后面那句
    #   「⛔ 这只证明两臂同底座、不证明底座在已验集合里」。
    #   把它换成一句「已验 ✅」⇒ 把**推断**印成**实测** ⇒ C1c 必红。
    ("Q6", "**这只证明「两臂同底座」，⛔ 不证明「那底座在已验的 60 条里」**",
     "**这 14 条已在已验集合内，P 已验 ✅**", "C1c"),

    # Q7 C5 的百分比被写死 ⇒ C5b（印出的数必须与实算一致）必红
    ("Q7", "lo_tok = min(off / d * 100.0 for d in dens0)", "lo_tok = 99.0", "C5b"),
]


def _load(path, src=None):
    mod = types.ModuleType("dpa_mut")
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
