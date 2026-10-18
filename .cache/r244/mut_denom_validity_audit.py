#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_denom_validity_audit —— denom_validity_audit.py 自检的**变异台**。

⚠⚠⚠ 本台架的头号理由（修订 244.38）
  这个工具的作用是**质疑一把尺**：`margin_meas = |ΔP9| / resid_std`。
  ⚖⚠⚠ 而它的输出会被读成「归一化削弱梯度 ⇒ 原梯度是噪声」——
  ⛔ 那是一条**会顺着往下推的**结论，所以它的失效方向特别危险：
  ① K1 的判定被拆 ⇒ 「与臂无关」被无条件印出 ⇒ 尺的合法性被凭空认了
  ② K2 的「未量到」被印成「不是噪声底」⇒ ⛔ 把**没量到**读成**否定结论**
     ⚖⚠⚠ 这正是 244.37 刚犯的同一个坑（同一天！）
  ③ Mann-Whitney 的零分布枚举错 ⇒ p 系统性偏大 ⇒ 「未检出」被印成「没差异」
  ④ 探针里 `resid_std` 的定义若被人改了，本工具整篇前提失效 ⇒ C5 守着

变异台设计纪律（同族）：
1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
2. ⚖ needle 必须唯一（单行或**整块**）、落在代码行。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。
5. ⚖⚠ **崩 ≠ 抓到**：崩掉的变异单列。

跑法：
    python3 mut_denom_validity_audit.py
    python3 mut_denom_validity_audit.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "denom_validity_audit.py")


def find_anchor(src, needle):
    """⚖ needle 可以是多行块：整块唯一即可，取块首行算行号。"""
    if "\n" in needle:
        if src.count(needle) != 1:
            raise AssertionError("块 needle 命中 %d 处（要求恰好 1）"
                                 % src.count(needle))
        off = src.index(needle)
        first = needle.split("\n")[0]
        if first.lstrip().startswith("#"):
            raise AssertionError("块 needle 首行是**注释**")
        return src.count("\n", 0, off) + 1
    hits = [(i, l) for i, l in enumerate(src.split("\n"), 1)
            if needle in l]
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1）：%r" % (len(hits), needle))
    lineno, line = hits[0]
    if line.lstrip().startswith("#"):
        raise AssertionError("needle 指到第 %d 行，那是**注释**" % lineno)
    pos = line.find(needle)
    stripped = line.lstrip()
    if pos < (len(line) - len(stripped)):
        raise AssertionError("needle 落在第 %d 行的前导缩进里 ⇒ 去掉 needle 的前导空格"
                             % lineno)
    return lineno


def apply_mutation(src, needle, repl):
    lineno = find_anchor(src, needle)
    out = src.replace(needle, repl, 1)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle[:60])
    return out, lineno


def run_selftest(src):
    mod = types.ModuleType("denom_mut")
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
            mod = types.ModuleType("denom_mut2")
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
    # N1 ⚠⚠⚖ K1 判定被拆 ⇒ 「与臂无关」被无条件印出 ⇒ 尺的合法性被凭空认了
    ("N1", 'if same == 0 else', 'if True else', "T6"),

    # N2 ⚠⚠⚖⚖ K2 的「未量到」被印成「不是噪声底」
    #   ⇒ 这一句是 244.37 刚犯过的同一个坑；这里直接让它恒为「检出」。
    ("N2", "        det = pv < ALPHA\n", "        det = True\n", "T7"),

    # N3 ⚠⚠ Mann-Whitney 零分布回到「全部 2^n 个子集」（不固定两组样本量）
    #   ⇒ p 系统性偏大 ⇒ 3v3 从 0.1000 变 0.4375
    ("N3", "for pick in itertools.combinations(range(n), n1):",
     "for pick in itertools.product((0, 1), repeat=n):", "C1"),

    # ⚠⚠⚖⚖ **N4 已作废并删除**：它打的是 `mann_whitney_exact` 里那句
    #   `if n == 0 or len(a) == 0 or len(b) == 0: return 1.0`。
    #   ⚖⚠⚖⚖ 变异台当场证明那条守卫**可证冗余**：删掉它，空组仍然返回 1.0
    #   （`combinations(range(2), 0)` 只有一个空组合 ⇒ 命中 ⇒ 1.0）
    #   ⇒ 它**永远生效不到** ⇒ 是一条**恒绿护栏** ⛔ 不是「判据太松」。
    # ⚗⇒ 按纪律「恒绿护栏要么删、要么写成能红的形状」⇒ **已删**，
    #   删的理由写在源码原地。⚖⚠ 这里记一笔，是为了不让下一个人以为
    #   「所有守卫都有变异盯着」。

    # N5 ⚠⚠⚖ 禁令被拆 ⇒ 「未量到 ⇒ 不是噪声底」又被写回去
    # ⚖⚠⚠⚠ 第一版这条改的是**默认参数** `alpha=ALPHA -> 0.0`，
    #   而那个函数**从不读它的参数**（恒返回 False）⇒ **变异可证无效**，
    #   台架报「仍 PASS」时我差点当成「判据太松」⇒ 真因在变异本身。
    ("N5", "    return False\n\n\n# --------------------------------------------------------------- 主流程",
     "    return True\n\n\n# --------------------------------------------------------------- 主流程",
     "C6"),

    # N6 ⚠⚠ C5：探针里 `resid_std` 的定义检查被拆
    #   ⛔ 那条守卫若失效，将来有人把它改成别的定义，本工具整篇前提悄悄失效。
    ("N6", 'okdef = (\'"resid_std": float(resid.std(ddof=1))\' in src',
     'okdef = (\'"resid_std": float(0.0)\' in src', "C5"),

    # N7 K3 的曲率阈值放到 0 ⇒ 「超过阈值的占比」永远是 0/全部
    ("N7", "CURVE_HI = 1.2", "CURVE_HI = 0.0", "T6"),

    # N8 ⚖⚠ `lin_ratio` 缺失时**静默当 0** ⇒ K3 会把「没量到」印成「曲率很小」
    ("N8", "        except (TypeError, ValueError):\n            miss += 1\n            continue",
     "        except (TypeError, ValueError):\n            got[(c[\"tid\"], round(cov, 9))] = 0.0\n            continue",
     "T8"),
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
        print("[FAIL] T0 基线就不是全绿 ⇒ 台架无效，先修工具（自检 rc=%d 失败=%s / 真实路 rc=%d）"
              % (rc, ",".join(sorted(bad)), rc2))
        return 1

    allok, crashed = True, []
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
                  "（真因通常在**用例没覆盖那个维度**）" % (name, ln, needle[:60], expect))
            allok = False
        else:
            print("[PASS] %s 第 %d 行变异 %r ⇒ %s 转红"
                  % (name, ln, needle[:60], expect))
            crashed.append(name) if False else None

    n = len(MUTATIONS)
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
