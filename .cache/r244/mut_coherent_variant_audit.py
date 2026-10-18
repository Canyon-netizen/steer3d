#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_coherent_variant_audit —— coherent_variant_audit.py 自检的**变异台**。

⚠⚠⚖ 本台架的头号理由（修订 244.41）
  这个工具的输出会**直接改写一条结论的方向**：
  ⚖⚠⚖⚖⚖ 244.40 报「rand 臂 p ∈ [0.0129, 0.4240]」⇒ **稳健、还显著**
  ⚖⚠⚖⚖⚖ 本轮实测：只要「把覆盖率最低那一档去掉」这一个动作
     ⇒ rand 变 11/14、**p = 0.0574** ⇒ **刚好越过 0.05**
  ⚖⚠⚖⚖⚖⇒ 方向上「显著 / 不显著」随**一个平凡动作**翻。
  ⚗⇒ 台架必须能抓住任何让这个读数偏掉的实现错误。

⚖⚠⚖⚖⚖⚖ 本台架**继承 244.40 的两条硬教训**（同族，⛔ 不重犯）
  1. ⚖⚠⚖ **「不许同义反复」的守卫必须是结构性的**：
     判别式 = 「落点在 `selftest()` 里 ⇒ 它改的是判据」，
     ⛔ **不是**「落点行里有没有 `chk(` / `in Lr`」——
     后者**随判据改写而改变形状** ⇒ 守卫静默退化成恒绿。
  2. ⚖⚠⚖ **崩 ≠ 抓到**；变异崩了单列，⛔ 不许冒充「按判据转红」。
  3. ⚖ **变异只改一处代码点**，⛔ 不许改注释/散文。
  4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。
  5. ⚖ 每条变异打印**落点行原文 + 真实路是否变化** ⇒ 有效性当场可核。

⚖⚠⚖⚖⚖⚖⚖⚖ **本台架必须能红**的变异（12 条）
  R1 `flag_of` 把「恰为 0」并进 neg ⇒ C3（第三状态被吃掉）
  R2 `slice_counts` 的 n 把 dropped 也算进去 ⇒ C6/C10（恒等式写错）
  R3 floor 判据 `<` 改成 `<=` ⇒ C10
  R4 floor 恒不删档（drop 恒空）⇒ C10
  R5 median 下标 `m//2` 改成 `m//2+1` ⇒ C5
  R6 未知 mode 悄悄当 full ⇒ C1
  R7 `top_is_not_a_sync_slice` 返回 True ⇒ C7
  R8 `n == 0` 不再打「n=0 未量到」（改印 0/0）⇒ C11
  R9 报告去掉「起点 k 各不相同」⇒ C8
  R10 报告去掉「**也不对齐**」⇒ C8
  R11 ALPHA 字面量改成 0.1 ⇒ C8

跑法：
    python3 mut_coherent_variant_audit.py
    python3 mut_coherent_variant_audit.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "coherent_variant_audit.py")
FORBID = ("chk(", "in Lr")


def find_anchor(src, needle):
    """⚖ 返回 (行号, 该行原文)；⛔ 不唯一 / 落注释 / needle 带缩进 ⇒ 抛。"""
    lines = src.split("\n")
    if "\n" in needle:
        if src.count(needle) != 1:
            raise AssertionError("块 needle 命中 %d 处（要求恰好 1）" % src.count(needle))
        off = src.index(needle)
        if needle.split("\n")[0].lstrip().startswith("#"):
            raise AssertionError("块 needle 首行是**注释**")
        ln = src.count("\n", 0, off) + 1
        return ln, lines[ln - 1]
    if needle[:1].isspace():
        raise AssertionError("单行 needle 不许带前导缩进：%r" % needle[:40])
    hits = [i for i, l in enumerate(lines) if needle in l]
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1）：%r" % (len(hits), needle))
    ln, line = hits[0] + 1, lines[hits[0]]
    if line.lstrip().startswith("#"):
        raise AssertionError("needle 指到第 %d 行，那是**注释**" % ln)
    if needle not in line.lstrip():
        raise AssertionError("needle 只匹配进第 %d 行的前导缩进里" % ln)
    return ln, line


def selftest_span(src):
    """⚖ `selftest()` 在源码里的行号闭区间 —— 「不许同义反复」的结构判别式。"""
    lines = src.split("\n")
    lo = None
    for i, l in enumerate(lines, 1):
        if l.startswith("def selftest("):
            lo = i
            break
    if lo is None:
        raise AssertionError("目标里找不到 def selftest(")
    hi = len(lines)
    for i in range(lo + 1, len(lines) + 1):
        if lines[i - 1].startswith("def ") or lines[i - 1].startswith("if __name__"):
            hi = i - 1
            break
    return lo, hi


def guard_selftest(src):
    """⚖ **守卫自己**的可核自检（244.40 的教训：恒绿护栏要能红）。"""
    lo, hi = selftest_span(src)
    lines = src.split("\n")
    inside = next((l for l in lines[lo:hi] if l.lstrip().startswith("chk(")), None)
    if inside is None:
        return 1, "⚠ selftest 里没有 chk( ⇒ 夹具无从构造"
    probes = [("落在 selftest 内", lines[lo:hi][0].strip()[:24]),
              ("needle 带前导缩进", "    " + inside.strip()[:16]),
              ("只匹配进缩进", inside.strip()[:4] + " ")]
    bad = []
    for tag, needle in probes:
        try:
            apply_mutation(src, needle, "XXX")
            got = "放行"
        except AssertionError:
            got = "拒"
        if got == "放行":
            bad.append("%s（被放行）" % tag)
    return (1 if bad else 0), "守卫自检 %d/3：%s" % (3 - len(bad), "全对" if not bad else bad)


def apply_mutation(src, needle, repl):
    ln, line = find_anchor(src, needle)
    slo, shi = selftest_span(src)
    if slo <= ln <= shi:
        raise AssertionError("落点第 %d 行落在 selftest() 的 [%d,%d] 里 ⇒ "
                             "这是**改判据**（同义反复），⛔ 变异无效" % (ln, slo, shi))
    for bad in FORBID:
        if bad in line:
            raise AssertionError("落点行含 %r ⇒ 这是**改判据**（同义反复），⛔ 变异无效" % bad)
    lines = src.split("\n")
    if "\n" in needle:
        out = src.replace(needle, repl, 1)
    else:
        lines[ln - 1] = line.replace(needle, repl, 1)
        out = "\n".join(lines)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle[:60])
    return out, ln, lines[ln - 1]


def run_selftest(src):
    mod = types.ModuleType("cov_mut")
    mod.__file__ = os.path.abspath(TARGET)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, TARGET, "exec"), mod.__dict__)
            rc = mod.selftest()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    return rc, buf.getvalue()


def run_real(src):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod = types.ModuleType("cov_mut2")
            mod.__file__ = os.path.abspath(TARGET)
            exec(compile(src, TARGET, "exec"), mod.__dict__)
            txt, rc = mod.run()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    return rc, (txt or "")


def _tests(text):
    ok, bad = set(), set()
    for line in text.split("\n"):
        if line.startswith("[PASS]"):
            ok.add(line.split()[1])
        elif line.startswith("[FAIL]"):
            bad.add(line.split()[1])
    return ok, bad


MUTATIONS = [
    # R1 ⛔ 「恰为 0」被并进 neg ⇒ **第三状态被吃掉**
    ("R1", "    if rho < 0:\n        return \"neg\"",
     "    if rho <= 0:\n        return \"neg\"", "C3"),
    # R2 ⛔ n 把 dropped 也算进去 ⇒ 恒等式写错
    ("R2", '"n": pos + neg + zero}',
     '"n": pos + neg + zero + sum(1 for v in per_tid.values() if v[0] is None)}', "C6"),
    # R3 ⛔ floor 判据 `<` 改 `<=` ⇒ 需要一档 cov **恰等于** floor 的边界夹具
    ("R3", "if cov[i] < floor]", "if cov[i] <= floor]", "C10"),
    # R4 floor 恒不删档
    ("R4", "drop = [i for i in range(m) if cov[i] < floor]", "drop = []", "C10"),
    # R5 median 下标写错一档 ⇒ 需要两个得到不同 rho 的夹具
    ("R5", "drop = [m // 2]", "drop = [m // 2 + 1]", "C5"),
    # R6 未知 mode 静静当 full ⇒ 需要「带 floor 也拒绝」才看得见
    ("R6", "if mode not in MODES:", "if False:", "C1"),
    # R7 禁令被拆（`return False` 全文唯一，故用**单行** needle）
    ("R7", "return False", "return True", "C7"),
    # R8 n==0 不再打「n=0 未量到」而印 0/0
    ("R8", 'cells.append("**n=0 未量到**")',
     'cells.append("%d/%d  %.4f" % (c["pos"], c["n"], 1.0))', "C11"),
    # R9 报告抹掉「起点 k 各不相同」（needle 只命中报告那行）
    ("R9", "不是被删的那一档：14 条阶梯的**起点 k 各不相同**",
     "起点 k 一律相同**", "C8"),
    # R10 报告抹掉「**也不对齐**」
    ("R10", "覆盖率带之间**也不对齐**", "覆盖率带之间是对齐的**", "C8"),
    # R11 ALPHA 字面量改成 0.1
    ("R11", "ALPHA = 0.05，字面量", "ALPHA = 0.1，字面量", "C8"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    base = open(args.target, encoding="utf-8").read()

    if args.selftest:
        rc, text = run_selftest(base)
        print(text)
        rc2, _ = run_real(base)
        g_rc, g_msg = guard_selftest(base)
        print("台架基线：自检 rc=%d、真实路 rc=%d、%s ⇒ 守卫 rc=%d" % (rc, rc2, g_msg, g_rc))
        return 0 if (rc == 0 and rc2 == 0 and g_rc == 0) else 1

    rc, text = run_selftest(base)
    ok, bad = _tests(text)
    rc2, base_real = run_real(base)
    g_rc, g_msg = guard_selftest(base)
    print("台架基线：自检 %d 通过 / %d 条 ⇒ rc=%d；真实路 rc=%d；%s"
          % (len(ok), len(ok) + len(bad), rc, rc2, g_msg))
    if rc != 0 or bad or rc2 != 0 or g_rc != 0:
        print("[FAIL] T0 基线就不是全绿 ⇒ 台架无效（自检 rc=%d 失败=%s / 真实路 rc=%d / 守卫 rc=%d）"
              % (rc, ",".join(sorted(bad)), rc2, g_rc))
        return 1

    allok = True
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, ln, new_line = apply_mutation(base, needle, repl)
        except AssertionError as e:
            print("[FAIL] T1.%s 变异串无效：%s" % (name, e))
            allok = False
            continue
        r, t = run_selftest(mut_src)
        _, mbad = _tests(t)
        extra = sorted(mbad - {expect})
        if r == 3:
            print("[FAIL] T2.%s 变异后源码直接崩：%s（⛔ 崩 ≠ 抓到）"
                  % (name, t.split("\n")[0][:88]))
            allok = False
        elif expect not in mbad:
            print("[FAIL] T3.%s 第 %d 行变异 %r 后 %s **仍 PASS** ⛔（实红=%s）"
                  % (name, ln, needle[:40], expect, ",".join(sorted(mbad)) or "无"))
            allok = False
        else:
            print("[PASS] %s 第 %d 行 ⇒ %s 转红%s"
                  % (name, ln, expect, ("（连带 %s）" % ",".join(extra)) if extra else ""))
            print("        ↳ 落点行：%s" % new_line.strip()[:92])
            rr, tt = run_real(mut_src)
            if rr == 3:
                print("        ↳ 真实路：**崩**（%s）⛔ 崩 ≠ 抓到" % tt.split("\n")[0][:70])
            else:
                print("        ↳ 真实路：%s"
                      % ("**与基线不同**（变异确实改了行为）" if tt != base_real
                         else "与基线**逐字相同**（这条只改措辞/判据文案，数字本就不该动）"))

    n = len(MUTATIONS)
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
