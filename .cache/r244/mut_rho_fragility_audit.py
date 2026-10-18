#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_rho_fragility_audit —— rho_fragility_audit.py 自检的**变异台**。

⚠⚠⚠ 本台架的头号理由（修订 244.39）
  这个工具量的是「12/14 正号稳不稳」，而它的输出会直接改写一条
  **已被撤回过一次**的账本结论的**方向**：
  ⚖ 实测 w 臂 **8/13** 条的符号删一档就翻，rand 臂只有 **3/13**。
  ⚖⚠⚠ 而配对 McNemar 给出 discordant **5 vs 0**、p=**0.0625** ——
  **差一格**就到 0.05。⇒ 这是一条**贴边**的读数，判据稍松就会被印成结论。
  ⚖⚠⚠⚖ 它的失效方向：
  ① jackknife 的翻转判定被拆 ⇒ 「全稳」被无条件印出
  ② 「零 rho」的分支被拆 ⇒ 无方向的轨迹被当成「非常稳」
  ③ 阈值 `DEGENERATE_ND` 改了 ⛔ 报告里也不印 ⇒ 退化路径被静默放过
  ④ 禁令被拆 ⇒ 「未量到」又被印成「没有差别」

变异台设计纪律（同族）：
1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
2. ⚖ needle 唯一（单行或**整块**）、落在代码行。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。
5. ⚖⚠ **崩 ≠ 抓到**。

跑法：
    python3 mut_rho_fragility_audit.py
    python3 mut_rho_fragility_audit.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "rho_fragility_audit.py")


def find_anchor(src, needle):
    if "\n" in needle:
        if src.count(needle) != 1:
            raise AssertionError("块 needle 命中 %d 处（要求恰好 1）"
                                 % src.count(needle))
        off = src.index(needle)
        first = needle.split("\n")[0]
        if first.lstrip().startswith("#"):
            raise AssertionError("块 needle 首行是**注释**")
        return src.count("\n", 0, off) + 1
    hits = [(i, l) for i, l in enumerate(src.split("\n"), 1) if needle in l]
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1）：%r" % (len(hits), needle))
    lineno, line = hits[0]
    if line.lstrip().startswith("#"):
        raise AssertionError("needle 指到第 %d 行，那是**注释**" % lineno)
    pos, stripped = line.find(needle), line.lstrip()
    if pos < (len(line) - len(stripped)):
        raise AssertionError("needle 落在第 %d 行的前导缩进里" % lineno)
    return lineno


def apply_mutation(src, needle, repl):
    lineno = find_anchor(src, needle)
    out = src.replace(needle, repl, 1)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle[:60])
    return out, lineno


def run_selftest(src):
    mod = types.ModuleType("frag_mut")
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
            mod = types.ModuleType("frag_mut2")
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
    # P1 ⚠⚠⚖⚖ 翻转判定被拆 ⇒ 「全稳」被无条件印出
    #   ⚖⚠⚠ 真数据上会把 w 臂 8/13 脆弱印成 0/13 ⇒ **方向直接反了**
    ("P1", "if r2 is not None and (r2 > 0) != (full > 0):",
     "if False:", "C2"),

    # ⚠⚠⚖⚖ **P2 已作废并删除**：它打的是 `jackknife` 里那道 `n < min_rungs` 守卫。
    #   ⚖⚠⚖⚖ 变异台当场证明它**被 `spearman` 自己的 n>=3 前置完全遮住**
    #   （2 档时 spearman 返回 None ⇒ 删不删都一样）⇒ **恒绿护栏**。
    # ⚗⇒ 已删，并把「为什么删」写在源码原地。
    #   `MIN_RUNGS` **保留**：报告层仍用它把短档标成「未量到」，由 C3 钉住。

    # P3 ⚠⚠⚖⚖ 第一版 P3 打的是 `n < min_rungs` 那道守卫
    #   ⚖⚠⚠⚖ 它已随 P2 一起**删除**（被 spearman 的 n>=3 前置完全遮住）
    #   ⇒ 变异串定位不到，⛔ 那不是变异的问题，是**守卫已经不在了**。
    # ⚗⇒ 换成一条仍然承重的：spearman 返回 None 之后，jackknife 必须原样透出
    #   ⇒ 被拆的话「未量到」会被当成 0.0 参与后续统计。
    ("P3", "    if full is None:\n        return None, None, None",
     "    if full is None:\n        return 0.0, 0, None", "C3"),

    # P4 ⚠⚠⚖ **零 rho 分支被拆** ⇒ 无方向的轨迹被当成「非常稳」
    #   ⚖⚠⚠ 真数据上 w 臂有 1 条 rho 恰为 0.000 ⇒ 它会变成「稳」
    ("P4", "    if full == 0.0:\n        return 0.0, None,",
     "    if False:\n        return 0.0, None,", "C4"),

    # P5 ⚠⚠⚖ 「删最高档」改成「删最低档」⇒ 剂量叙事压的那一档**没被删到**
    ("P5", "top = spearman_fn(list(cov[:-1]), list(y[:-1]))",
     "top = spearman_fn(list(cov[1:]), list(y[1:]))", "C8"),

    # P6 退化阈值改了（⛔ 报告里不印 ⇒ 看不见）
    ("P6", "DEGENERATE_ND = 2", "DEGENERATE_ND = 99", "C7"),

    # P7 ⚖⚠⚖ 禁令被拆 ⇒ 「未量到」又被印成「没有差别」
    ("P7", "    return False\n", "    return True\n", "C6"),

    # ⚠⚠⚖⚖ **P8 已作废并删除**：它把 McNemar 的复用源换成另一个模块
    #   ⇒ 变体直接 `AttributeError` **崩** ⛔ 而崩 ≠ 抓到
    #   ⇒ 那条是「真问题但按纪律不能算被抓到」。换成一条干净可红的。
    # P8 组间 Fisher 的双侧倍数少乘 2 ⇒ 对照数从 0.58105 变成 0.29052
    #   ⚖⚠⚠ 症状隐蔽：它只是「对照」那一行，而对照最容易被当参考
    ("P8", "return min(1.0, 2.0 * sum(math.comb(n, i)",
     "return min(1.0, 1.0 * sum(math.comb(n, i)", "C7"),
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
        print("台架基线：自检 rc=%d、真实路 rc=%d" % (rc, rc2))
        return 0 if (rc == 0 and rc2 == 0) else 1

    rc, text = run_selftest(base)
    ok, bad = _tests(text)
    rc2, _ = run_real(base)
    print("台架基线：自检 %d 通过 / %d 条 ⇒ rc=%d；真实路 rc=%d"
          % (len(ok), len(ok) + len(bad), rc, rc2))
    if rc != 0 or bad or rc2 != 0:
        print("[FAIL] T0 基线就不是全绿 ⇒ 台架无效（自检 rc=%d 失败=%s / 真实路 rc=%d）"
              % (rc, ",".join(sorted(bad)), rc2))
        return 1

    allok = True
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, ln = apply_mutation(base, needle, repl)
        except AssertionError as e:
            print("[FAIL] T1.%s 变异串无法定位：%s" % (name, e))
            allok = False
            continue
        r, t = run_selftest(mut_src)
        _, mbad = _tests(t)
        if r == 3:
            print("[FAIL] T2.%s 变异后源码直接崩：%s（⛔ 崩 ≠ 抓到）"
                  % (name, t.split("\n")[0][:88]))
            allok = False
        elif expect not in mbad:
            print("[FAIL] T3.%s 第 %d 行变异 %r 后 %s **仍 PASS** ⛔"
                  % (name, ln, needle[:56], expect))
            allok = False
        else:
            print("[PASS] %s 第 %d 行变异 %r ⇒ %s 转红" % (name, ln, needle[:56], expect))
            rr, tt = run_real(mut_src)
            if rr != 3 and "McNemar" in tt:
                for l2 in tt.split("\n"):
                    if "McNemar" in l2:
                        print("        ↳ 真实路：%s" % l2.strip()[:92])
                        break

    n = len(MUTATIONS)
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
