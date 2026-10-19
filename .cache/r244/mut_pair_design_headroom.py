#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_pair_design_headroom.py —— pair_design_headroom.py 自检的**变异台**。

⚠⚠⚖ 本台架的头号理由（修订 244.44）
  本节的产出是一条**否定性结论**：⛔ **配对本身买不到格子余量**。
  ⚖⚠⚖⚖⚖⇒ 台架必须能保证这条否定**不是分母算错造成的**：
     ⚖ 若 `discordant_n` / `pair_margin` / `min_d_for` 里有一个把 d 或 b 算错，
     ⚖ 「缩分母 ⇒ 余量变差」这个单调性就会被悄悄推翻。

⚖⚠⚖⚖⚖⚖⚖⚖ **继承 244.40–244.43 的硬约束（同族，⛔ 不重犯）**
  1. ⚖ 「不许同义反复」的守卫是**结构性**的：「落点在 `selftest()` 里」，
     ⛔ **不是**「行里有没有 `chk(` / `in Lr」——后者随判据改写而失效。
  2. ⚖⚠ **崩 ≠ 抓到**。
  3. ⚖ 变异只改一处代码点；⛔ 不改注释/散文。
  4. ⚖ 每条变异打印**落点行原文 + 真实路是否变化**。
  5. ⚖⚠ 变异必须**先证明自己有效**。
  6. ⚖⚠⚠⚠⚠⚠ **⛔ 不许在源码里搜字面量当判据**（244.43 的教训：那必然自指 ⇒ 恒绿）。
     ⚖ 本台的判据**只查报告产物 `Lr`**，⛔ 没有「查源码」那一半。
  7. ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠ **needle 是本项目最常出错的东西**
     （244.43 一轮里手打错 4 次：⚠ 个数、中文、缩进、前导空格；244.44 改用生成器
     又被「重复代码块覆盖结果」坑了一次）。
     ⚗⇒ 本文件每条 needle 都**逐条从真实源核对过唯一命中**（见下），
     且 `find_anchor` 在每次运行时**再断言一次** ⇒ needle 写错台架会当场报。
     ⚖⚠⚠⚠ 两处 needle 在源码里**出现多次**，⛔ 必须用**块 needle**（带上下文）：
        · `if not 0 < ratio <= 1:` 出现在 `pair_margin` 与 `min_d_for` ⇒ J4 取后者
        · `return False` 出现在禁令函数与 `discordant_n` 的 except ⇒ J9 取前者

⚖⚠⚖⚖⚖⚖⚖⚖⚖ **必须能红**的变异（9 条）
  J1  `discordant_n` 的下界夹取 `max(d,2)` → `max(d,0)` ⇒ C9
      ⚖⚠ 第一版把它期望成 C4，被台架当场判 FAIL ⇒ **台架期望标签本身也会写错**。
      ⚖ 真因：C4 只查**六道守卫会不会抛**，而 `max(d,2)` 是**夹取**不是守卫 ⇒
      ⚖ 拆掉它 C4 理应不动 ⇒ 抓到它的是 C9（`discordant_n` 的**直接**判据）。
  J2  `keep` 守卫被拆 ⇒ C4
  J3  `pair_margin` 的 `d<2` 守卫被拆 ⇒ C4
  J4  `min_d_for` 的 `ratio` 守卫被拆（块 needle）⇒ C4
  J5  `b` 的上界夹取被拆 ⇒ C1
  J6  `min_d_for` 阈值收紧一格 ⇒ C3
  J7  扫描区间少一格 ⇒ C3
  J8  题库大小 `N_ITEMS` 14 → 13（端到端）⇒ C2
  J9  「配对 ⛔ 不等于更稳」禁令被拆（块 needle）⇒ C5

跑法：
    python3 mut_pair_design_headroom.py
    python3 mut_pair_design_headroom.py --selftest
退出码：0 = 全部被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "pair_design_headroom.py")
FORBID = ("chk(", "in Lr")


def find_anchor(src, needle):
    """⚖ 定位 needle 所在的唯一一处，并拒绝「落在 selftest 里 / 指到注释」。"""
    lines = src.split("\n")
    if "\n" in needle:
        if src.count(needle) != 1:
            raise AssertionError("块 needle 命中 %d 处（要求恰好 1）" % src.count(needle))
        off = src.index(needle)
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
    """⚖⚖ 结构守卫自检：三条探针必须**全被拒**（⛔ 放行即守卫失效）。"""
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
        out = src.replace(needle, repl, 1)          # ⚖ 块 needle：整块替换
    else:
        lines[ln - 1] = line.replace(needle, repl, 1)
        out = "\n".join(lines)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle[:60])
    return out, ln, lines[ln - 1]


def _materialize(src, tag):
    """⚖⚠⚖⚖ 把**变异后的源码**落成真文件，让 `open(__file__)` 读到的就是它。
    ⚖⚠⚠⚠ 必须落**同目录**：目标用 `dirname(abspath(__file__))` 去找 headroom_audit.py。
    """
    path = os.path.join(HERE, "_mut_tmp_%s.py" % tag)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return path


def run_selftest(src, tag="base"):
    tmp = _materialize(src, tag)
    mod = types.ModuleType("pair_mut")
    mod.__file__ = tmp
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, tmp, "exec"), mod.__dict__)
            rc = mod.selftest()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    finally:
        os.remove(tmp)
    return rc, buf.getvalue()


def run_real(src, tag="base"):
    tmp = _materialize(src, tag + "_real")
    mod = types.ModuleType("pair_mut2")
    mod.__file__ = tmp
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, tmp, "exec"), mod.__dict__)
            txt, rc = mod.run()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    finally:
        os.remove(tmp)
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
    # J1 discordant_n 的下界夹取（⚠ 期望 C9 不是 C4：夹取≠守卫，C4 只查守卫）
    ("J1", "return max(d, 2)", "return max(d, 0)", "C9"),
    # J2 keep 守卫被拆
    ("J2", "if not 0 < keep <= 1:", "if False:", "C4"),
    # J3 pair_margin 的 d<2 守卫被拆
    ("J3", "if d < 2:", "if False:", "C4"),
    # J4 min_d_for 的 ratio 守卫被拆（块 needle：同一串在 pair_margin 里也有一份）
    ("J4",
     "    if margin < 0:\n"
     "        raise HardFail(\"margin=%d 为负 ⇒ ⛔ 拒算\" % margin)\n"
     "    if not 0 < ratio <= 1:",
     "    if margin < 0:\n"
     "        raise HardFail(\"margin=%d 为负 ⇒ ⛔ 拒算\" % margin)\n"
     "    if False:", "C4"),
    # J5 b 的上界夹取被拆
    ("J5", "b = min(max(b, 1), d - 1)", "b = max(b, 1)", "C1"),
    # J6 min_d_for 阈值收紧一格
    ("J6", 'if r["margin"] >= margin:', 'if r["margin"] >= margin + 1:', "C3"),
    # J7 扫描区间少一格
    ("J7", "for d in range(2, cap + 1):", "for d in range(2, cap):", "C3"),
    # J8 题库大小被改（端到端）
    ("J8", "N_ITEMS = 14", "N_ITEMS = 13", "C2"),
    # J9 禁令被拆（块 needle：return False 在 discordant_n 的 except 里也有一份）
    ("J9", "    return False\n\n\ndef unpaired_margin(",
     "    return True\n\n\ndef unpaired_margin(", "C5"),
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
        r, t = run_selftest(mut_src, name)
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
            rr, tt = run_real(mut_src, name)
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
