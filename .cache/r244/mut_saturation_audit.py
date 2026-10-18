#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_saturation_audit —— saturation_audit.py 自检的**变异台**。

⚠⚠⚖ 本台架的头号理由（修订 244.42）
  本轮最重要的产出是**一条否证**：「饱和 ⇒ |rho| 小 ⇒ 符号脆」被自己的预测证伪
  （rand r=−0.078 / w r=**+0.533**，方向相反）。
  ⚖⚠⚖⚖⚖⇒ 台架必须能保证这条否证**不是实现错误造成的**：
     ⚖ 若 `pearson_r` 或 `census` 有偏，任何「假说被证伪」的结论都会被推翻。

⚖⚠⚖⚖⚖⚖ 继承 244.40/244.41 的硬约束（同族，⛔ 不重犯）
  1. ⚖ 「不许同义反复」的守卫是**结构性**的：「落点在 `selftest()` 里」
     ⛔ **不是**「行里有没有 `chk(` / `in Lr」——后者随判据改写而失效。
  2. ⚖⚠ **崩 ≠ 抓到**。
  3. ⚖ 变异只改一处代码点；⛔ 不改注释/散文。
  4. ⚖ 每条变异打印**落点行原文 + 真实路是否变化**。

⚖⚠⚖⚖⚖⚖⚖⚖ **必须能红**的变异（10 条）
  S1 floor 判据 `<=` 改 `<` ⇒ C2（边界点看不见）
  S2 ceil 判据 `>=` 改 `>` ⇒ C2
  S3 floor/ceil 合成一个布尔 ⇒ C1（第三态被吃掉）
  S4 `census` 的 mid 算错 ⇒ C3（恒等式）
  S5 `pearson_r` 零方差返回 0.0 而不是 None ⇒ C4
  S6 `pearson_r` 分母少乘一项 ⇒ C4
  S7 `usable_rungs` 把不足 3 档也算「可算」⇒ C5
  S8 禁令被拆 ⇒ C6
  S9 报告抹掉「假说被自己的预测证伪」⇒ C7
  S10 敏感性区间被改成写死的「不敏感」⇒ C9

跑法：
    python3 mut_saturation_audit.py
    python3 mut_saturation_audit.py --selftest
退出码：0 = 全部被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "saturation_audit.py")
FORBID = ("chk(", "in Lr")


def find_anchor(src, needle):
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
    mod = types.ModuleType("sat_mut")
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
            mod = types.ModuleType("sat_mut2")
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
    ("S1", "if raw <= floor:", "if raw < floor:", "C2"),
    ("S2", "if raw >= ceil:", "if raw > ceil:", "C2"),
    ("S3", 'if raw <= floor:\n        return "floor"', "if raw <= floor:\n        return True", "C1"),
    ("S4", '"mid": len(raws) - f - c,', '"mid": len(raws) - f - c - 1,', "C3"),
    ("S5", "return None                            # ⛔ 零方差 ⇒ 未量到，不是 0",
     "return 0.0                              # BUG: 零方差印 0.0", "C4"),
    ("S6", "return sxy / (sxx ** 0.5 * syy ** 0.5)", "return sxy / syy", "C4"),
    ("S7", "n_ok = sum(1 for v in out.values() if v[0] >= 3)",
     "n_ok = sum(1 for v in out.values() if v[0] >= 1)", "C5"),
    ("S8", "    return False\n\n\n# --------------------------------------------------------------- 主流程",
     "    return True\n\n\n# --------------------------------------------------------------- 主流程", "C6"),
    ("S9", '⇒ ⇒ **假说被自己的预测证伪** ⇒ ⚖⚠⚠⚠⚠ 只能报',
     '⇒ ⇒ **假说得到支持** ⇒ ⚖⚠⚠⚠⚠ 只能报', "C7"),
    ("S10", "**具体数字是阈值敏感的**", "**结论对阈值不敏感**", "C9"),
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
