#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_two_experiment_check —— two_experiment_check.py 自检的**变异台**。

## 这条在量什么

`two_experiment_check.py --selftest` 报 9/9。⚠⚠ 那**只证明「没报错」**，
⛔ 不证明「能红」—— 一套恒绿的检查和一个真正有牙的检查，在输出上长得一模一样。

⚖ 244.25 实测时，这套自检当场抓到本工具自己的两个 bug：
⚖ ① 文案里两个占位符只给了一个参数（TypeError）；
⚖ ② 把 **137 写死**在文案里，于是 6 格的夹具会印「137/137 全不同」。
⚖⇒ 自检必须包含「报告不许印不可能的数」这类判据，才抓得到第②条。

## ⚠⚠⁴ 变异台设计纪律

1. ⚠⚠⁴ **变异必须只改一处代码点**，⛔ 不许顺手改注释/散文。
2. ⚖ **定位按代码行**：needle 必须唯一、必须落在代码行（不是 `#` 注释）、
   ⛔ 且不得指进前导缩进（那会让「改到哪一行」变成猜测）。
3. ⛔ **不许事后调变异调到绿为止**。
4. ⚖ 变异在**内存里**做（`exec` 一份改过的源码），⛔ 不落临时文件、不动原件。

跑法：
    python3 mut_two_experiment_check.py            # 变异台
    python3 mut_two_experiment_check.py --selftest # 台架自身自检
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或台架自身自检失败。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "two_experiment_check.py")


def find_code_line(src, needle):
    """定位唯一一行**代码行**含 needle。⚖ 三条硬要求，见文件头纪律。"""
    hits = []
    for i, line in enumerate(src.split("\n"), 1):
        pos = line.find(needle)
        if pos < 0:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            raise AssertionError(
                "needle 指到第 %d 行第 %d 列，那一行是**注释**"
                "（变异的是散文，不是代码）" % (i, pos))
        if pos < (len(line) - len(stripped)):
            raise AssertionError(
                "needle 指到第 %d 行第 %d 列，落在前导缩进里（前导空白占 %d 列）"
                "⇒ 请去掉 needle 的前导空格" % (i, pos, len(line) - len(stripped)))
        hits.append((i, line))
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1 行）：%r"
                             % (len(hits), needle))
    return hits[0]


def apply_mutation(src, needle, repl):
    lineno, line = find_code_line(src, needle)
    if needle not in line:
        raise AssertionError("needle 不在这行里（needle=%r）" % needle)
    new_line = line.replace(needle, repl, 1)
    out = src.replace(line, new_line)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle)
    return out, lineno


def run_selftest(src):
    mod = types.ModuleType("tec_mut")
    mod.__file__ = os.path.abspath(TARGET)   # ⚖ 让 open(__file__) 类判据仍成立
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, TARGET, "exec"), mod.__dict__)
            rc = mod.selftest()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    return rc, buf.getvalue()


def failed_tests(text):
    """抽出 FAIL 的自检编号。⚠ 编号是 `T1`..`Tn`（纯数字），用 isalnum 兼容带字母的。"""
    out = set()
    for line in text.split("\n"):
        if line.startswith("[FAIL]"):
            tok = line.split()[1] if len(line.split()) > 1 else ""
            if tok and tok[0] == "T" and tok[1:].isalnum():
                out.add(tok)
    return out


def passed_tests(text):
    out = set()
    for line in text.split("\n"):
        if line.startswith("[PASS]"):
            tok = line.split()[1] if len(line.split()) > 1 else ""
            if tok and tok[0] == "T" and tok[1:].isalnum():
                out.add(tok)
    return out


MUTATIONS = [
    # G1 去掉剥 arm —— 本工具存在的**头号理由**就没了
    # ⚠⚠⚠ 症状：只改臂名、读数一动没动，也会被判成「两个不同的实验」。
    # ⚖ 而这是判据的措辞与它实际比的东西不对齐：它声称比的是读数，
    # ⚖ 实际比的是「读数 + 臂名」。
    ("G1", 'r.pop("arm", None)', 'pass  # 变异：不再剥 arm', "T3"),
    # G2 剥 arm 后载荷相同也不硬失败
    ("G2", "if ma == mb:", "if False:", "T2"),
    # G3 承重字段全同也不硬失败 ⇒ 由 T9 抓（载荷 md5 那边已被 T2 遮蔽）
    ("G3", "if lb == 0:", "if False:", "T9"),
    # G4 格数不等不拒读 ⇒ 会静默取短的当分母
    ("G4", "if len(cb) != n:", "if False:", "T4"),
    # G5 tid 错位不拒读 ⇒ 错位一格把上一格读成这一格
    ("G5", 'if a.get("tid") != b.get("tid"):', "if False:", "T5"),
    # G6 MUST_MATCH 不拒读 ⇒ 「不是单变量对照」这道闸形同虚设
    # ⚖⚠ needle 用 `if bad:` 而不是那句比较 —— 比较在 field_diff_counts 里
    # ⚖ 也有一份，会命中两行（台架会报「定位失败」，那**不等于**判据没牙）。
    ("G6", "if bad:", "if False:", "T6"),
    # G7 不变清单分桶失效 ⇒ 不在清单里的字段被悄悄放过
    # ⚠⚠ 症状：报告永远说「✅ 无按设计应变却没变的字段」，
    # ⚖ 而一个陌生的 0/N 全同字段本该逼人写理由。
    ("G7", "if k not in INVARIANT_BY_DESIGN and k not in MUST_MATCH]",
     "if False]", "T8"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--selftest", action="store_true",
                    help="台架自身自检（用坏变异证明本台架会红）")
    args = ap.parse_args()

    if args.selftest:
        ok = True
        base = open(args.target, encoding="utf-8").read()
        for name, needle, repl, expect in MUTATIONS:
            try:
                mut_src, ln = apply_mutation(base, needle, repl)
            except AssertionError as e:
                print("[FAIL] T1.%s 变异串无法定位：%s" % (name, e))
                ok = False
                continue
            rc, text = run_selftest(mut_src)
            red = failed_tests(text)
            if rc == 3:
                print("[FAIL] T2.%s 变异后源码直接崩：%s" % (name, text.split("\n")[0]))
                ok = False
            elif expect not in red:
                print("[FAIL] T3.%s 变异 %r 后 %s **仍 PASS** ⛔（台架看不见）"
                      % (name, needle, expect))
                ok = False
            else:
                print("[PASS] T5.%s 变异确实改到了第%d行，且 %s 由 PASS 变 FAIL"
                      % (name, ln, expect))
        print("mut_two_experiment_check --selftest: %s"
              % ("全部通过" if ok else "有失败"))
        return 0 if ok else 1

    base = open(args.target, encoding="utf-8").read()
    rc0, text0 = run_selftest(base)
    n0 = len(passed_tests(text0)) + len(failed_tests(text0))
    print("=" * 74)
    print("变异台：目标 %s" % os.path.basename(args.target))
    print("基线自检：%d/%d%s" % (len(passed_tests(text0)), n0,
                                 "（基线就不绿，先修判据再谈变异）"
                                 if rc0 != 0 else ""))
    print("=" * 74)
    if rc0 != 0:
        print("⛔ 基线就不全绿 —— 变异结果没有意义，先修判据。")
        return 1
    base_pass = passed_tests(text0)
    print("基线判据：%s\n" % ",".join(sorted(base_pass)))

    survived = []
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, lineno = apply_mutation(base, needle, repl)
        except AssertionError as e:
            print("[台架坏了] %s 定位失败：%s" % (name, e))
            survived.append(name + "(定位失败)")
            continue
        rc, text = run_selftest(mut_src)
        red = failed_tests(text)
        if expect in red:
            print("[抓住了] %-3s 第%-4d行  %-40s ⇒ %s 由 PASS 变 FAIL ✅"
                  % (name, lineno, needle[:40], expect))
        else:
            print("[存活!!] %-3s 第%-4d行  %-40s ⇒ %s **仍是 PASS** ⛔"
                  % (name, lineno, needle[:40], expect))
            survived.append("%s→%s" % (name, expect))

    print("\n" + "=" * 74)
    if survived:
        print("⛔ 有 %d 个变异存活：%s" % (len(survived), "、".join(survived)))
        print("   ⇒ 这些判据是**恒绿的装饰品**，要么修判据，要么换能改变被观测量的变异。")
        return 1
    print("✅ %d 个变异全部被抓住（每条都让**指定的**那条判据由 PASS 变 FAIL）"
          % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
