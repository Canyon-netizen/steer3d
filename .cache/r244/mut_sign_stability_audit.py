#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_sign_stability_audit —— sign_stability_audit.py 自检的**变异台**。

⚠⚠⚖ 本台架的头号理由（修订 244.40）
  这个工具的输出会**直接改写一条结论的方向**。
  ⚖⚠⚖⚖⚖ 第一版它用 `None` **同时**表示「未量到」与「两可」，
  而 `run()` 把 `None` 一律当「未量到」剔出
  ⇒ 9 条**两可**轨迹被丢掉，区间塌成 [4,4] vs [9,9]
  ⇒ 印出「区间**不重叠**、可分辨」
  ⛔ 而真值是 [4,13] **覆盖** [9,12] ⇒ **结论整个反了，且方向恰好相反**。
  ⚗⇒ 台架必须能抓住这一类：**哨兵复用**。

⚖⚠⚖⚖⚖⚖ 本台架**头号教训之二：变异不许是「同义反复」**
  ⚖ 第一版 Q7 写的是 needle = `"不是置信区间"` ——
  ⚖⚠⚖⚖⚖⚖⚖ 那命中的是 **selftest 自己那行断言的字面量**（`"不是置信区间" in Lr`），
  ⚖⚠⚖⚖⚖⚖⛔ 而**不是**报告里那句文案。
  ⚖⇒ 于是「把报告措辞改掉」这个变异，其实改的是**判据自己**
  ⚖⇒ 它当然转红，⚖⚠⚖ 但转红的原因是**同义反复**，⛔ 什么也没证明。
  ⚗⇒ 修法：**全局守卫** `FORBID`（下）——
     变异落点那条**行**里不许出现 `chk(` 或 `in Lr`
  ⇒ 从此「改判据」与「改被测物」在机器层面**分得开**。

⚖⚠⚖⚖⚖⚖ 本台架**必须能红**的变异
  Q1 两可被并进「未量到」（真 bug 复现）⇒ C2 **与 C11**（run() 层）转红
  Q2 下界算成「只可能负」⇒ 区间被**凭空拉宽** ⇒ C2 转红
  Q3 上界漏掉「两可」⇒ **假不显著** ⇒ C3 转红
  Q4 变体不足不再报未量到 ⇒ C5 转红
  Q5 恒正/恒负判反 ⇒ C1 转红
  Q6 禁令被拆 ⇒ C6 转红
  Q7 **报告**文案从「不是置信区间」改成「可作参考区间」⇒ C7 转红
  Q8 `p_span` 只扫端点（= 退回端点公式，V 形漏检）⇒ C8 转红
  Q9 `_pv` 写成 `p or 1.0`（falsy 陷阱）⇒ C9 转红
  Q10 报告把「V 形」说成「W 形」⇒ C7 转红

⚖⚠⚖⚖⚖⚖⚖⚠⚖ 变异台设计纪律（同族）：
  1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
  2. ⚖ needle 唯一；单行 needle **不许带前导缩进**（判据在 `stripped` 里找）。
  3. ⛔ 不许事后调变异调到绿为止。
  4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。
  5. ⚖⚠ **崩 ≠ 抓到**。
  6. 🔴 **落点行不许含 `chk(` 或 `in Lr`** ⇒ 杜绝「改判据冒充改被测物」。
  7. ⚖ 打印落点行原文 + 真实路是否变化 ⇒ 变异**有效性**当场可核。

跑法：
    python3 mut_sign_stability_audit.py
    python3 mut_sign_stability_audit.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "sign_stability_audit.py")

# ⚖⚠⚖⚖⚖⚖⚖ 落点行里出现这些 ⇒ 变异改的是**判据自己**，⛔ 同义反复
FORBID = ("chk(", "in Lr")


def selftest_span(src):
    """⚖ 返回 `selftest()` 在源码里的行号闭区间 `[lo, hi]`。

    ⚖⚠⚖⚖⚖⚖⚖⚠⚠⚠ **这是「不许同义反复」唯一有牙齿的判别式。**
    ⚖⚠⚖⚖⚖⚖⚖⚠⚠⚠ 第一版守卫只查落点行里有没有 `chk(` / `in Lr` 字面量，
    ⚖⚠⚖⚖⚖⚖⚖⚥⚠⚠⚠⚠ 而 C7 一旦**改写**，断言就从
    ⚠⚠  `"不是置信区间" in Lr and ...`  变成元组 `always = (..., "不是置信区间", ...)`
    ⚖⚠⚥⇒ 两个字面量都不在那一行 ⇒ **守卫静默失效**，第一版 Q7 那条同义反复又活了
    ⚖⚠⚥⇒ 实测：守卫写成 FORBID 时，它对那条 needle **不拦**。
    ⚗⇒ 判别式必须是**结构**的：「落点在 `selftest` 里 ⇒ 它改的是判据」，
      ⛔ 而不是「落点行里有没有某个字面量」。
    """
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
    """⚖ **守卫自己**的可核自检：它必须能拒掉该拒的、放行该放的。

    ⚖⚠⚖⚠⚖⚖⚠⚖⚠⚠ 「恒绿护栏要么删、要么写成能红的形状」——
    ⚖⚠⚖⚠⚖⚖⚠⚖⚠⚠ 本函数就是那个「能红的形状」：
    ⚖⚠⚖⚠⚖⚖⚠⚖⚠⚠ 三条反例夹具（落在 selftest 内 / 带前导缩进 / 只匹配进缩进）
    ⚖⚠⚥⛔ 任一条**没被拒**，本函数就红 ⇒ 守卫退化成恒绿时**当场暴露**。
    """
    lo, hi = selftest_span(src)
    lines = src.split("\n")
    inside = next((l for l in lines[lo:hi] if l.lstrip().startswith("chk(")), None)
    if inside is None:
        return 1, "⚠ selftest 里没有 chk( ⇒ 夹具无从构造"
    probes = [
        ("落在 selftest 内的 needle（第一版 Q7 那条同义反复）",
         lines[lo:hi][0].strip()[:24], True),
        ("单行 needle 带前导缩进", "    " + inside.strip()[:16], True),
        ("只匹配进前导缩进", inside.strip()[:4] + " ", True),
    ]
    bad = []
    for tag, needle, want_reject in probes:
        try:
            apply_mutation(src, needle, "XXX")
            got = "放行"
        except AssertionError:
            got = "拒"
        if (got == "拒") != want_reject:
            bad.append("%s（%s）" % (tag, got))
    return (1 if bad else 0), "守卫自检 %d/3：%s" % (3 - len(bad), "全对" if not bad else bad)


def find_anchor(src, needle):
    """⚖ 返回 (行号, 该行原文)；⛔ 命中不唯一 / 落注释 / needle 带缩进 ⇒ 抛。

    ⚖⚠⚖⚖⚖⚖ **第一版的缩进判据是错的。**
    ⚖⚠⚖⚖⚖⚖ 第一版 needle 自带 8 个空格，而判据是
      「`pos < len(line) - len(line.lstrip())` ⇒ 落在前导缩进里 ⇒ 拒」
      ⇒ 而 needle **本来就该**以缩进开头 ⇒ 第一版**误杀了自己的 Q1**。
    ⚖⚠⚖⚖⚖⚖⚖⚠⚖ 真判据是「**去掉缩进后**还能不能找到」：
      找到 ⇒ needle 指的是代码内容；找不到 ⇒ 它只匹配进了缩进里 ⇒ 拒。
    ⚗⇒ 因此规定：**单行 needle 一律不带前导缩进**（块 needle 允许带）。
    """
    lines = src.split("\n")
    if "\n" in needle:
        if src.count(needle) != 1:
            raise AssertionError("块 needle 命中 %d 处（要求恰好 1）" % src.count(needle))
        off = src.index(needle)
        first = needle.split("\n")[0]
        if first.lstrip().startswith("#"):
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


def apply_mutation(src, needle, repl):
    """⚖ 单行 needle ⇒ **只在那唯一一行里**做子串替换（⛔ 不全局 replace）。

    ⚖⚠⚖⚖⚖⚖⚖ 为何不 `src.replace(needle, repl, 1)`：
    ⚖⚠⚖⚖⚖⚖⚖ 那是**全文第一个**匹配 —— 若同样的片段先出现在别处，
    ⚖⚠⚖⚖⚖⚖⚖ 就会改错行，而 `find_anchor` 已经算好了行号 ⇒ 白算。
    ⛔ 块 needle 仍走全局 replace（块本身已验证唯一）。
    """
    ln, line = find_anchor(src, needle)
    slo, shi = selftest_span(src)
    if slo <= ln <= shi:
        raise AssertionError("落点第 %d 行落在 selftest() 的 [%d,%d] 里 ⇒ "
                             "这是**改判据**（同义反复），⛔ 变异无效" % (ln, slo, shi))
    for bad in FORBID:
        if bad in line:
            raise AssertionError("落点行含 %r ⇒ 这是**改判据**（同义反复），⛔ 变异无效"
                                % bad)
    lines = src.split("\n")
    if "\n" in needle:
        out = src.replace(needle, repl, 1)
        new_line = repl.split("\n")[needle.split("\n").index(
            next(l for l in needle.split("\n") if l.strip()))]
    else:
        lines[ln - 1] = line.replace(needle, repl, 1)
        out = "\n".join(lines)
        new_line = lines[ln - 1]
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle[:60])
    return out, ln, new_line


def run_selftest(src):
    mod = types.ModuleType("sign_mut")
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
            mod = types.ModuleType("sign_mut2")
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
    # Q1 🔴🔴 **真 bug 复现**：两可被并进「未量到」⇒ 区间塌缩
    #   ⚖⚠⚖⚖⚖⚖⚖⚖ 期望红的是 **C2 与 C11**，⛔ 不是 C3：
    #   ⚖ C3 直接喂 `bounds(["either",...])` 字面量 ⇒ 根本不经 `variant_signs`
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖ ⚠ 第一版把它标成「C3 转红」⇒ 那条变异当时**其实抓不到任何东西**。
    #   ⚖ C2 走 `variant_signs`（两可夹具）⇒ 会红；
    #   ⚖ C11 读**报告**（两可条数 → 0）⇒ 也会红（这才是真 bug 的形状）。
    ("Q1", 'return "either"',
     'return None                       # BUG: 两可并进未量到', "C11"),

    # Q2 ⚠⚠⚖⚖ 下界算成「只可能负」⇒ 区间被**凭空拉宽**（我第一版就是这么写的）
    ("Q2", '"either": either, "lo": only_p, "hi": only_p + either}',
     '"either": either, "lo": only_n, "hi": only_p + either}', "C2"),

    # Q3 ⚠⚠⚖⚖ 上界漏掉「两可」⇒ **假不显著**
    ("Q3", '"either": either, "lo": only_p, "hi": only_p + either}',
     '"either": either, "lo": only_p, "hi": only_p}', "C3"),

    # Q4 ⚖⚠⚖ 变体不足不再报未量到 ⇒ 2 档轨迹被当成「恒负」
    ("Q4", "if len(vs) < min_variants:", "if len(vs) < 0:", "C5"),

    # Q5 ⚖⚠⚖ 恒正/恒负判反（块：跨两行 ⇒ ⛔ 单行改会留下悬空 body）
    ("Q5", "    if has_p:\n        return True                      # 恒正",
     "    if has_p:\n        return False                     # 恒正", "C1"),

    # Q6 ⚖⚠⚖ 禁令被拆 ⇒ 「区间重叠」又被印成「两者相同」
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚠⚠ 块 needle 必须锚在**下一段真代码**之前：
    #   ⚖ 第一版写 `...return False\n\n\ndef bounds(flags):` ⇒ 命中 0 处，
    #   ⚖ 因为 `bounds` 在**上面**、`overlap_is_not_equality` 后面接的是**注释横幅**。
    ("Q6", "    return False\n\n\n", "    return True\n\n\n", "C6"),

    # Q7 ⚖⚠⚖ 报告**文案**从「不是置信区间」改成「可作参考区间」
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚠⚠ needle 必须落在**报告那行**（第 267 行附近），
    #   ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⛔ 第一版 needle=`"不是置信区间"` 命中的是 **C7 断言自己的字面量**
    #   ⚖⇒ 那条变异是**同义反复**，转红什么也没证明（FORBID 守卫现已拦下它）。
    ("Q7", '，⛔ **绝对不是置信区间**"', '，⛔ **可作参考区间**"', "C7"),

    # Q8 🔴🔴 `p_span` 只扫端点 ⇒ 退回端点公式 ⇒ V 形的最坏情形漏掉
    ("Q8", "for k in range(lo, hi + 1)]", "for k in (lo, hi)]", "C8"),

    # Q9 🔴🔴 `_pv` 写成 `p or 1.0` ⇒ falsy 陷阱（p=0.0 被印成 1.0）
    ("Q9", "return 1.0 if p is None else p", "return p or 1.0", "C9"),

    # Q10 ⚖⚠⚖ 报告把「V 形」说成「W 形」⇒ 那条解释被悄悄改掉
    ("Q10", "是 **V 形**（k 与 n−k 同值）", "是 **W 形**（k 与 n−k 同值）", "C7"),
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
        print("台架基线：自检 rc=%d、真实路 rc=%d、%s ⇒ 守卫 rc=%d"
              % (rc, rc2, g_msg, g_rc))
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
                  % (name, ln, expect,
                     ("（连带 %s）" % ",".join(extra)) if extra else ""))
            print("        ↳ 落点行：%s" % new_line.strip()[:92])
            rr, tt = run_real(mut_src)
            if rr == 3:
                print("        ↳ 真实路：**崩**（%s）⛔ 崩 ≠ 抓到" % tt.split("\n")[0][:70])
            else:
                print("        ↳ 真实路：%s"
                      % ("**与基线不同**（变异确实改了行为）" if tt != base_real
                         else "与基线**逐字相同**（这条只改措辞/禁令，数字本就不该动）"))
                for key in ("p 的区间 = **", "p 的区间也重叠", "区间重叠"):
                    for l2 in tt.split("\n"):
                        if key in l2:
                            print("        ↳ %s" % l2.strip()[:92])
                            break

    n = len(MUTATIONS)
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
