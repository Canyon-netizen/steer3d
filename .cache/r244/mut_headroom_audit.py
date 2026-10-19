#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_headroom_audit —— headroom_audit.py 自检的**变异台**。

⚠⚠⚖ 本台架的头号理由（修订 244.43）
  本节的产出是**一组格子**：账本里每个被当作「显著」的判决离 α=0.05 有几格。
  ⚖⚠⚖⚖⚖⇒ 台架必须能保证这组格子**不是余量算法写错造成的**：
     ⚖ 若 `cells_to_alpha` 多算/少算一格，m=1 与 m=2 会整个翻掉。

⚖⚠⚖⚖⚖⚖ **本轮在台架自己身上拆掉两条恒绿**（244.43）
  ① ⚖⚠⚖⚖⚖⚖ **死变异 H1**：`<` → `<=` 在 α=0.05 下**不可达**
     （⚖ `sign_binom` 的取值永远是 S/2^(n−1)，而 **5 ∤ 2^(n−1)** ⇒ p 永不 = 0.05）
     ⇒ ⚠⚠ 我第一版给它编的理由（「`<=` 会让 11/14 算成 1 格」）**是错的**：
     ⚖ 11/14 的 p=0.05737 本来就 > α ⇒ `<` 与 `<=` **都给 0**。
     ⚗⇒ 处理：**删掉这条变异**，⛔ 而不是留着一条永远抓不到人的死条目充数。
  ② ⚖⚠⚖⚖⚖⚖ **C7 的 `branches` 那一半恒绿**：它 `open(__file__)` 读源码，
     ⚖ 而台架当时给的 `__file__` 是**磁盘上那个未被变异的文件** ⇒
     ⚖⚠⚠⚠ 任何只改**源码分支**的变异都**永远抓不到**。
     ⚗⇒ 处理：`_materialize()` 把变异后的源码**落成同目录真文件**再 exec。

⚖⚠⚖⚖⚖⚖⚖⚖⚖ 继承 244.40–244.42 的硬约束（同族，⛔ 不重犯）
  1. ⚖ 「不许同义反复」的守卫是**结构性**的：「落点在 `selftest()` 里」
     ⛔ **不是**「行里有没有 `chk(` / `in Lr」——后者随判据改写而失效。
  2. ⚖⚠ **崩 ≠ 抓到**。
  3. ⚖ 变异只改一处代码点；⛔ 不改注释/散文。
  4. ⚖ 每条变异打印**落点行原文 + 真实路是否变化**。
  5. ⚖⚠ 变异必须**先证明自己有效**（落点行真的改了、真实路真的变了）。

⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖ **必须能红**的变异（14 条）
  H1  余量**多算**一格（`m` → `m+1`）⇒ C1（替掉那条死变异）
  H2  余量**少走**一格（`m += 1` 被拆）⇒ C1
  H3  `one_cell_ratio` 的 None 被写成 1.0 ⇒ C3
  H4  `sb` 的 n≤0 守卫被拆 ⇒ C4
  H5  `cells_to_alpha` 的 k 越界守卫被拆 ⇒ C4
  H6  `min_n_for` 的 `>= margin` 改成 `>= margin + 1` ⇒ C5
  H7  「余量小 ⛔ 不等于判决无效」禁令被拆 ⇒ C6
  H8  报告抹掉「**12/14 只买 1 格**」⇒ C7（恒印那一半）
  H9  源码分支 `is False` 被抹 ⇒ C7（branches 那一半，**靠 _materialize 才红得了**）
  H10 判决清单的 k 被篡改（12 → 11）⇒ C8
  H11 「只列显著的」的过滤器 `if sig` 被改成恒真 ⇒ C9
  H12 扫描器 `== alpha` 写成 `>= alpha` ⇒ C2a
  H13 扫描器恒 0（`if False`）⇒ C2a（⛔ 只有「能命中 1.0」那半抓得到）
  H14 `alpha_hits` 的空区间守卫被拆 ⇒ C4

⚖⚠⚖⚖⚖⚖ ⚖⚠ **H12 与 H13 是一对**，缺一不可：
  ⚖ 只做 H12（`>=`）⇒ 扫描器仍非空洞，但 ① 会红；
  ⚖ 只做 H13（恒 0）⇒ ⚖⚠ **只有**「p 恰等于 1.0 的个数 > 0」那半能抓到它
  ⚖ ⇒ ⛔ 若 C2a 只断言「命中 0 个」，H13 就是条变异能存活的判据。

跑法：
    python3 mut_headroom_audit.py
    python3 mut_headroom_audit.py --selftest
退出码：0 = 全部被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "headroom_audit.py")
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


def _materialize(src, tag):
    """⚖⚠⚖⚖⚖⚖ 把**变异后的源码**落成真文件，让 `open(__file__)` 读到的就是它。

    ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚠⚠⚠⚠ **本轮拆掉的恒绿之二**：
    ⚖ 原来 `mod.__file__ = TARGET` = **磁盘上未被变异的那个文件**
    ⚖ ⇒ ⚖⚠ C7 的 `branches` 那一半（`x not in src`，`src` 来自 `open(__file__)`）
    ⚖⚠⚠⚠ **读的是原始文件** ⇒ ⛔ 任何只改**源码分支**的变异都**永远抓不到**
    ⚖ ⚖⚠ 症状：H9 这类变异会报「仍 PASS」，而人很容易归咎成「变异无效」
    ⚖⚠⚖⚖ ⇒ ⚖⚠ **「仍 PASS」的第四种形态**：判据读的不是被测物（第四种形态：
    ⚖⚠⚠ 台架装置本身量错了对象 ⇒ 与前三类「夹具遮蔽/只验等价/只验会抛」不同源）。
    ⚖⚠⚖⚖⚖⚖⚖ ⚖⚠ **必须落同目录**：`sb()` 用 `dirname(abspath(__file__))`
    ⚖   去找 `arm_contrast_audit.py`，换个目录就 ⛔ 直接抛。
    """
    path = os.path.join(HERE, "_mut_tmp_%s.py" % tag)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return path


def run_selftest(src, tag="base"):
    """⚖ 变异后的源码**落盘**再 exec ⇒ `open(__file__)` 读到的是它。"""
    tmp = _materialize(src, tag)
    mod = types.ModuleType("head_mut")
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
    mod = types.ModuleType("head_mut2")
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
    # H1 🔐🔐 余量**多算**一格 —— ⚠⚠ **替掉原来那条死变异**（`<`→`<=`）
    #   ⚖ 死因：α=0.05 下 p 永不恰等于 α（5 ∤ 2^(n−1)）⇒ `<`/`<=` 逐位等价
    ("H1", "return m, max(j, 0),", "return m + 1, max(j, 0),", "C1"),
    # H2 余量**少走**一格（`m += 1` 被拆 ⇒ m 恒 0）
    ("H2", "        j -= 1\n        m += 1", "        j -= 1", "C1"),
    # H3 None 被写成 1.0（⛔ 冒充「一格不变」）
    ("H3", "    if k <= 0:\n        return None", "    if k <= 0:\n        return 1.0", "C3"),
    # H4 n≤0 守卫被拆
    ("H4", "    if n <= 0:\n        raise HardFail", "    if False:\n        raise HardFail", "C4"),
    # H5 k 越界守卫被拆
    ("H5", "    if not 0 <= k <= n:\n        raise HardFail",
     "    if False:\n        raise HardFail", "C4"),
    # H6 阈值收紧一格 ⇒ 最小 n 变大（⚠ 换成 `>= margin+1`，⛔ 不换成 cap：
    #   cap 会让 C5 **抛异常** ⇒ 台架报「崩」⛔ 而「崩 ≠ 抓到」）
    ("H6", "if cells_to_alpha(k, n, alpha)[0] >= margin:",
     "if cells_to_alpha(k, n, alpha)[0] >= margin + 1:", "C5"),
    # H7 禁令被拆
    ("H7", "    return False\n\n\n# --------------------------------------------------------------- 主流程",
     "    return True\n\n\n# --------------------------------------------------------------- 主流程", "C6"),
    # H8 报告抹掉「12/14 只买 1 格」（C7 的 `always` 恒印那一半）
    ("H8", 'L.append("  ⚖⚠⚠⚠⚖⚠⇒ **12/14 只买 1 格',
     'L.append("  ⚖⚠⚠⚠⚖⚠⇒ **11/14 只买 1 格', "C7"),
    # H9 🔴 源码分支 `is False` 被抹（C7 的 `branches` 那一半）
    #   ⚖⚠⚠⚠ 这条**在 `_materialize` 之前是抓不到的**（恒绿的判据）⇒ 它的价值
    #   ⚖⚠⚠ 就是当那半条恒绿的**反证**：修好之后它必须转红
    # H9 🔴 三元条件**写反** ⇒ 报告从「禁令 生效」变成「⛔ 失效」⇒ C7
    #   ⚖⚠⚠⚠ 旧版 H9 打的是「把源码里某段字面量抹掉」，⛔ **那条判据原理上恒绿**：
    #   ⚖ `x = ("字面量", ...)` 里 `x` 自己就在源码里 ⇒ `x not in src` 恒为假
    #   ⇒ ⚠⚠ 怎么取字面量都白搭 ⇒ 该判据已在 headroom_audit.py 里**删除**（理由写原地）
    #   ⇒ ⚖⚠ 这里换成**正路**：断言报告**必须**印「禁令 生效」⇒ 写反就红
    ("H9", '"生效" if headroom_is_not_a_verdict() is False else',
     '"⛔ 失效" if headroom_is_not_a_verdict() is False else', "C7"),
    # H10 判决清单的 k 被篡改（12 → 11）⇒ C8
    ("H10", '("预登记主统计量 w", 12, 14, "预登记主"),',
     '("预登记主统计量 w", 11, 14, "预登记主"),', "C8"),
    # H11 「只列显著的」的过滤器 `if sig` 改成恒真 ⇒ 已越界的 0 格混进来 ⇒ C9
    ("H11", 'if sig:',
     'if True:', "C9"),
    ("H12", "if sb(k, n) == alpha:", "if sb(k, n) >= alpha:", "C2a"),
    # H13 🔴 扫描器恒 0（`if False`）⇒ C2a
    #   ⚖⚠⚠⚠ **只有「p 恰等于 1.0 的个数 > 0」那半抓得到它**
    #   ⇒ ⛔ 若 C2a 只断言「命中 0 个」，这条就会存活
    ("H13", "if sb(k, n) == alpha:", "if False:", "C2a"),
    # H14 空区间守卫被拆 ⇒ C4
    ("H14", "    if hi_n < lo_n:\n        raise HardFail",
     "    if False:\n        raise HardFail", "C4"),
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
