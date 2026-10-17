#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_ladder_position_audit —— ladder_position_audit.py 自检的**变异台**。

⚠⚠⚠ 本台架存在的头号理由：修订 244.26 里，A3 **当场抓到工具自己的一道恒绿检查**
⚖（「抽出的源码逐字在文件里」—— `seg` 本就从 `src` 抽出，**按构造恒真**）。
⚖ 而恒绿检查是**台架抓不到的**（台架原理上量不了「一条永远为真的断言」）。
⚗⇒ 唯一能抓住它的办法，是**自检里放一条「该断言必须能红」的用例**，
⚖ 也就是 A3 现在的样子：拿一个**故意破坏条件**的夹具去看它报不报。

⚖ 于是本台架逐条咬「那些能红的检查」：H1–H6 每条都让指定判据由 PASS 变 FAIL。

变异台设计纪律（同 mut_two_experiment_check）：
1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
2. ⚖ needle 必须唯一、落在代码行、⛔ 不得指进前导缩进。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。

跑法：
    python3 mut_ladder_position_audit.py
    python3 mut_ladder_position_audit.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或台架自身自检失败。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "ladder_position_audit.py")


def find_code_line(src, needle):
    hits = []
    for i, line in enumerate(src.split("\n"), 1):
        pos = line.find(needle)
        if pos < 0:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            raise AssertionError("needle 指到第 %d 行第 %d 列，那一行是**注释**"
                                 "（变异的是散文，不是代码）" % (i, pos))
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
    mod = types.ModuleType("lpa_mut")
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
    # H1 去掉「探针里从不调用 ⇒ 拒用」⇒ A3 必红
    ("H1", "if not calls:", "if False:", "A3"),
    # H2 去掉 seed 默认值检查 ⇒ A5 必红
    # ⚠⚠ 症状：审计按 seed=0 算位点，而仪器用 seed=1 ⇒ **审计的是另一组位点**，
    # ⚖ 报告看上去完全正常。
    ("H2", 'if sig.parameters["seed"].default != 0:',
     "if False:", "A5"),
    # H3 去掉「调用点必须传 nested=」⇒ A6 必红
    ("H3", 'if not any(kw.arg == "nested" for c in calls for kw in c.keywords):',
     "if False:", "A6"),
    # H4 去掉「挑出的位数必须等于 k」自证 ⇒ A4 必红
    # ⚖⚠ 症状：位数与 k 不符时**继续算**，prompt 占比的分母就换了口径。
    ("H4", "if len(pos) != k:", "if False:", "A4"),
    # H5 去掉 t / n_eff 的运行时恒等 ⇒ A2 必红
    ("H5", "if t != max(1, int(ng * pos_frac)):", "if False:", "A2"),
    # H6 把 Bonferroni 门槛放回 0.05 ⇒ A7 必红
    # ⚖⚠ 真实数据里已有 1 档二项 p=0.0354 ⇒ 门槛一松，工具就改口报
    # ⚖ 「⛔ 偏离均匀采样」⇒ **门槛松紧会改变结论**，不是口味问题。
    ("H6", "bonf = 0.05 / n_tests", "bonf = 0.05", "A7"),
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
        print("mut_ladder_position_audit --selftest: %s"
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
            print("[抓住了] %-3s 第%-4d行  %-44s ⇒ %s 由 PASS 变 FAIL ✅"
                  % (name, lineno, needle[:44], expect))
        else:
            print("[存活!!] %-3s 第%-4d行  %-44s ⇒ %s **仍是 PASS** ⛔"
                  % (name, lineno, needle[:44], expect))
            survived.append("%s→%s" % (name, expect))

    print("\n" + "=" * 74)
    if survived:
        print("⛔ 有 %d 个变异存活：%s" % (len(survived), "、".join(survived)))
        return 1
    print("✅ %d 个变异全部被抓住" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
