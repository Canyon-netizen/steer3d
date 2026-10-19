#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_p_identity_audit —— `p_identity_audit.py` 的变异台（修订 244.54）

⚖ 纪律（同本项目其它台架）：
  1. needle **唯一命中、落在代码行、不在前导缩进里**；
  2. 替换后必须断言**旧串真的消失**（新串含回旧串时除外），并 `ast.parse`。

⚖⚠⚖⚖ 本台架针对的是 244.54 的**两类失效方向**：
  · **恒绿型**（判据被焊成恒真 ⇒ 真有错也报不出来）
  · **恒红型 / 取错型**（作用域解析被拆掉 ⇒ 干净夹具就红）

⚖⚠⚖⚖ **期望标签必须指向「走得到那一支」的夹具**（本项目已栽 6 次死变异）：
  · P12/P13 拆的是 D5 的**两条不同分支** ⇒ 必须各有一条夹具**单独**踩到那一支
    （D5x 只踩「t 不可重算」，D5y 只踩「t > n」）
  · P10 拆的是「记录 P 逐条相等」⇒ D3x 那条夹具必须**只有**这一支红

跑法：python3 mut_p_identity_audit.py
"""

import argparse
import ast
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "p_identity_audit.py")


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
    # P1 MODEL 比较被焊成恒真 ⇒ S1x（MODEL 不同那份夹具）必红
    ("P1", "same_model = (len(set(models.values())) == 1 and None not in models.values())",
     "same_model = True", "S1x"),

    # P2 tokenizer 加载的比较被放宽（>= 1）⇒ S2x 必红
    ("P2", "len({tuple(v or ()) for v in loads.values()}) == 1",
     "len({tuple(v or ()) for v in loads.values()}) >= 1", "S2x"),

    # P3 flag 比较被焊成恒真 ⇒ S3x 必红
    ("P3", "same_flag = (len(set(flags.values())) == 1 and None not in flags.values())",
     "same_flag = True", "S3x"),

    # P4 字段比较被焊成恒真 ⇒ S4x 必红
    ("P4", "same_field = (len(set(flds.values())) == 1 and None not in flds.values())",
     "same_field = True", "S4x"),

    # P5 P 的「len(pid) 回退支」检查被焊成恒真 ⇒ S5x 必红
    ("P5", 'has_fallback = "len(pid)" in p_txt', "has_fallback = True", "S5x"),

    # P6 截断形状检查被焊成恒真 ⇒ S6x 必红
    ("P6", 'cut_ok = bool(re.search(r"\\[:\\s*P\\s*\\+\\s*t\\s*\\]", ids_txt))',
     "cut_ok = True", "S6x"),

    # P7 ⚠⚠⚠ 作用域解析被拆掉（退回全树）⇒ 干净夹具就会拿到同名干扰项
    #    `n = alphas.size` ⇒ **C0（干净夹具）转红**
    #    ⇒ 这条变异的价值在于：它证明「按作用域取值」这条**真的在判据里**
    ("P7", 'n_exprs = assigns_in(scopes["probe"], "n")',
     'n_exprs = assigns_in(trees["probe"], "n")', "C0"),

    # P8 戳一致性被焊成恒真 ⇒ D1x 必红
    ("P8", 'mark("D1", len(vals) == 1 and len(stamps) >= 2,',
     'mark("D1", True,', "D1x"),

    # P9 按 md5 选权威 map 的那一步被改（选中兄弟）⇒ 干净夹具就红 ⇒ C0
    ("P9", "auth = [p for p in cands if md5_of(p) == want_md5]",
     "auth = [p for p in cands if md5_of(p) != want_md5]", "C0"),

    # P10 记录 P 的逐条相等检查被拆掉 ⇒ D3x 必红
    ("P10", 'if str(M[t][iP]) != str(r.get("P")):', "if False:", "D3x"),

    # P11 P 分布的逐项比较被焊成恒真 ⇒ D4x 必红
    ("P11", "same = (d[k] == LEDGER_P_DIST[k])", "same = True", "D4x"),

    # P12 ⚠⚖ D5 的「t 不可重算」那一支被拆掉（只留 t>n）⇒ D5x 必红
    #     （D5y 那条夹具只踩 t>n ⇒ 两条分支**各有一条夹具单独踩到**）
    ("P12", "d5_ok = (not bad_t and not bad_nt and not over)",
     "d5_ok = (not over)", "D5x"),

    # P13 D5 的「t > n」那一支被拆掉 ⇒ D5y 必红
    ("P13", "if t > n_npz:", "if False:", "D5y"),

    # P14 n_eff == P+t 的检查被拆掉 ⇒ D7x 必红
    ("P14", "if int(r[iE]) != int(r[iP]) + int(r[iT])]",
     "if False]", "D7x"),

    # P15 POS_FRAC 的对照被焊成恒真 ⇒ D6x 必红
    ("P15", "mark(\"D6\", pfs == {LEDGER_POS_FRAC},",
     "mark(\"D6\", True,", "D6x"),

    # P16 「恒等式，⛔ 不需要实测」这个限定被抹掉 ⇒ C1 必红
    #     ⇒ 少了它，读者会把「源码同形」误读成「实测过」
    ("P16", "⇒ 取自**同一份输入**时**必然相等**（恒等式，⛔ 不需要实测）。",
     "⇒ 取自**同一份输入**时**必然相等**（恒等式）。", "C1"),

    # P17 残留前提 R4 那条被删掉 ⇒ C2 必红
    ("P17", "L.append(\"    R4 `sidecar_prompt_tokens.tsv` 的**来源未查**（仓库里找不到生产者）\")",
     "L.append(\"    (略)\")", "C2"),
]


def _load(path, src=None):
    mod = types.ModuleType("pia_mut")
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
