#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_mechanism_strat —— mechanism_strat.py 自检的**变异台**。

⚠⚠⚠ 本台架的头号理由：修订 244.28 里，**第一版的判定太松** ——
只判「方向一致 ⇒ 通过」，而实测方向确实一致（+64.3pp vs +14.3pp）
却幅度差 4.5 倍、两层 p 差 1210 倍。
⚖⚠ **「太松」的判据比「太严」更危险**：它让一个只对一半成立的结论带着 ✅ 通过。
⚗⇒ M6 就是为它准备的：拿实测那组数，要求「必须喊出必须同报分层」。

变异台设计纪律（同 mut_two_experiment_check / mut_ladder_position_audit）：
1. ⚠⚠⁴ 变异只改一处代码点，⛔ 不许改注释/散文。
2. ⚖ needle 必须唯一、落在代码行、⛔ 不得指进前导缩进。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在内存里 exec，⛔ 不落临时文件、不动原件。

跑法：
    python3 mut_mechanism_strat.py
    python3 mut_mechanism_strat.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或台架自身自检失败。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "mechanism_strat.py")


def find_code_line(src, needle):
    hits = []
    for i, line in enumerate(src.split("\n"), 1):
        pos = line.find(needle)
        if pos < 0:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            raise AssertionError("needle 指到第 %d 行第 %d 列，那一行是**注释**"
                                 % (i, pos))
        if pos < (len(line) - len(stripped)):
            raise AssertionError(
                "needle 指到第 %d 行第 %d 列，落在前导缩进里（前导空白占 %d 列）"
                "⇒ 请去掉 needle 的前导空格" % (i, pos, len(line) - len(stripped)))
        hits.append((i, line))
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1 行）：%r" % (len(hits), needle))
    return hits[0]


def apply_mutation(src, needle, repl):
    lineno, line = find_code_line(src, needle)
    new_line = line.replace(needle, repl, 1)
    out = src.replace(line, new_line)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle)
    return out, lineno


def run_selftest(src):
    mod = types.ModuleType("ms_mut")
    mod.__file__ = os.path.abspath(TARGET)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, TARGET, "exec"), mod.__dict__)
            rc = mod.selftest()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    return rc, buf.getvalue()


def _tests(text):
    ok, bad = set(), set()
    for line in text.split("\n"):
        if line.startswith("[PASS]"):
            ok.add(line.split()[1])
        elif line.startswith("[FAIL]"):
            bad.add(line.split()[1])
    return ok, bad


MUTATIONS = [
    # N1 把幅度门槛放到天上 ⇒ 「必须同报分层」永不喊
    # ⚖⚠⚠ 症状：实测 +64.3pp vs +14.3pp（差 4.5 倍）、p 差 1210 倍，
    # ⚖   报告却印「✅ 幅度也在同一量级 ⇒ 主判决不是单层机制的产物」。
    # ⚖⚠ 它指向 **M8**（只靠幅度差的那条），⛔ 不是 M6 ——
    # ⚖   M6 验的是「幅度或 p 任一」，废掉任一支它照样 PASS（第一轮就存活了）。
    ("N1", "and max(abs(d1), abs(d2)) / min(abs(d1), abs(d2)) >= 3.0)",
     "and max(abs(d1), abs(d2)) / min(abs(d1), abs(d2)) >= 1e9)", "M8"),
    # N2 方向判据恒真 ⇒ 两层方向相反也放过
    ("N2", "same = (d1 > 0) == (d2 > 0)", "same = True", "M5"),
    # N3 「多数为真」改成 `>=` ⇒ 平局被算成 True
    # ⚖⚠⚠ 口径约定是 `nT > nF`（**平局算 False**），改了就换了统计量。
    ("N3", "return nt, nf, (nt > nf), len(vals)", "return nt, nf, (nt >= nf), len(vals)", "M1"),
    # N4 读数为 None 的格也进分母 ⇒ 「未量到」被当成 False
    ("N4", "if r[\"up\"] is not None]", "]", "M2"),
    # N5 把 Fisher 的 p 直接返回 1.0 ⇒ M3 红
    # ⚖⚠⚠ needle 用 `return min(1.0, p)` 而**不是** `if n == 0:` ——
    # ⚖   后者在 `sign_test_exact` 里也有一份，会命中两行（定位失败）。
    # ⚖⚗ 而第一版 N5 只废掉空表守卫，M3 那时只查了空表 ⇒ **变异存活**。
    # ⚖   ⇒ M3 补了**独立暴力实现**作参照，才真正承重。
    ("N5", "return min(1.0, p)", "return 1.0  # 变异：p 恒为 1", "M3"),
    # N6 p 值比门槛放到天上 ⇒ 只靠 p 判据时永不喊（指向 **M9**，同理）
    ("N6", "and max(p1, p2) / min(p1, p2) >= 100.0)",
     "and max(p1, p2) / min(p1, p2) >= 1e99)", "M9"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    base = open(args.target, encoding="utf-8").read()

    if args.selftest:
        ok = True
        for name, needle, repl, expect in MUTATIONS:
            try:
                mut_src, ln = apply_mutation(base, needle, repl)
            except AssertionError as e:
                print("[FAIL] T1.%s 变异串无法定位：%s" % (name, e))
                ok = False
                continue
            rc, text = run_selftest(mut_src)
            _, bad = _tests(text)
            if rc == 3:
                print("[FAIL] T2.%s 变异后源码直接崩：%s" % (name, text.split("\n")[0]))
                ok = False
            elif expect not in bad:
                print("[FAIL] T3.%s 变异 %r 后 %s **仍 PASS** ⛔（台架看不见）"
                      % (name, needle, expect))
                ok = False
            else:
                print("[PASS] T5.%s 变异改到第%d行，且 %s 由 PASS 变 FAIL" % (name, ln, expect))
        print("mut_mechanism_strat --selftest: %s"
              % ("全部通过" if ok else "有失败"))
        return 0 if ok else 1

    rc0, text0 = run_selftest(base)
    good, bad = _tests(text0)
    print("=" * 74)
    print("变异台：目标 %s" % os.path.basename(args.target))
    print("基线自检：%d/%d%s" % (len(good), len(good) + len(bad),
                                 "（基线就不绿，先修判据再谈变异）" if rc0 != 0 else ""))
    print("=" * 74)
    if rc0 != 0:
        print("⛔ 基线就不全绿 —— 变异结果没有意义，先修判据。")
        return 1
    print("基线判据：%s\n" % ",".join(sorted(good)))

    survived = []
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, lineno = apply_mutation(base, needle, repl)
        except AssertionError as e:
            print("[台架坏了] %s 定位失败：%s" % (name, e))
            survived.append(name + "(定位失败)")
            continue
        rc, text = run_selftest(mut_src)
        _, red = _tests(text)
        if expect in red:
            print("[抓住了] %-3s 第%-4d行  %-46s ⇒ %s 由 PASS 变 FAIL ✅"
                  % (name, lineno, needle[:46], expect))
        else:
            print("[存活!!] %-3s 第%-4d行  %-46s ⇒ %s **仍是 PASS** ⛔"
                  % (name, lineno, needle[:46], expect))
            survived.append("%s→%s" % (name, expect))

    print("\n" + "=" * 74)
    if survived:
        print("⛔ 有 %d 个变异存活：%s" % (len(survived), "、".join(survived)))
        return 1
    print("✅ %d 个变异全部被抓住" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
