#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_dose_axis_audit —— dose_axis_audit.py 自检的**变异台**。

⚠⚠⚠ 本台架的头号理由（修订 244.31）
  作者在这一轮里**自己连写了两条恒绿检查**，都被本台架要抓的东西盯着：

  ⚖⚠⚠ 恒绿一：`shortcut_check` 里那条反证件写成
        `sorted(permutation(n)) != list(range(n))` ——
        而 `sorted(排列)` 对**任意**排列都等于 `range(n)`
        ⇒ 那条判据**可证恒绿**，永远给 diff>0，
        ⚖ 反而把「恒等捷径造出的秩」放行了。
        ⚗ 抓住它的不是「它太松」，是**它可证恒真**：排列的排序必然是 range(n)。

  ⚖⚠⚠ 恒绿二：自检 T4 第一版写的是「两份夹具的 key 本来就不等」——
        夹具不等是**构造出来的**，与判据无关 ⇒ 恒绿。
        ⚗ 唯一能抓住它的办法是**让自检调用判据**并看它报不报（现在的形态）。

  ⚖⚠⚠ 弱守卫一：T5 只断言 `0 <= p <= 1`。⛔ 任何落在范围内的**常数**
        （比如 244.23 那条 `p = 1.0` 的变异）都能过它 ⇒ 弱守卫等于没有。
        ⚗ 补了 T5c 的**精确值**断言才咬得住。

⚖⇒ H1–H11 每条都让**指定判据**由 PASS 变 FAIL；H6/H7 两向都咬
   （恒 True 与恒 False 同样是缺陷 ——「判据没独立承重」和「判据恒绿」等价）。

变异台设计纪律（同 mut_ladder_position_audit）：
1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
2. ⚖ needle 必须唯一、落在代码行、⛔ 不得指进前导缩进。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。

跑法：
    python3 mut_dose_axis_audit.py
    python3 mut_dose_axis_audit.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或台架自身自检失败。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "dose_axis_audit.py")
PROBE = os.path.join(os.path.dirname(HERE), "mutbak", "r204_noise_probe.py")


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
    mod = types.ModuleType("dose_mut")
    mod.__file__ = os.path.abspath(TARGET)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, TARGET, "exec"), mod.__dict__)
            # ⚖ selftest 必须拿到**真探针**路径，否则 T9 只验夹具。
            rc = mod.selftest(PROBE)
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
    # H1 J1：把「k 必须 < n_eff」放宽到 k > n_eff+1
    # ⚖⚠ 症状：k == n_eff 的格走过 `return list(range(n))` 恒等捷径 ⇒
    #   该格**恒定**被判成「直接扰动」，机制配比被凭空抬高。
    ("H1", "if k >= n:", "if k > n + 1:", "T2"),

    # H2 J2：把反证件改回「排序后再比」——**可证恒绿**的那一版
    # ⚖⚠⚠ 症状：diff 恒 > 0 ⇒ 反证件永远放行「秩」，而秩可能来自捷径。
    ("H2", "if perm != list(range(n)):", "if sorted(perm) != list(range(n)):", "T1"),

    # H3 J3：去掉 t 与 pos_frac 的运行时恒等 ⇒ T3 必红
    ("H3", "if t != max(1, int(ng * pf)):", "if False:", "T3"),

    # H4 J4：两臂阶梯不一致时不再拒读 ⇒ T4 必红
    # ⚖⚠ 症状：两臂档数不同（实测 7/8/9 三种）仍照读 ⇒ 剂量轴根本不可比。
    ("H4", "if ka != kb:", "if False:", "T4"),

    # H5 J5：J5 恒返回「压小」⇒ T10 必红
    # ⚖⚠ 症状：报告永远说「梯度不是噪声变小造出来的」，哪怕它就是。
    ("H5", 'return "压小" if m_raw > m_norm else "可疑"', 'return "压小"', "T10"),

    # H6 J6：只查机制轴那条，丢掉「两条同时满符号」⇒ T11 必红
    # ⚖⚠ 症状：只要机制轴满符号就喊「不可分离」，而响应轴可能完全没梯度。
    ("H6", "return (pos_d >= n_d) and (pos_r >= n_r)", "return (pos_d >= n_d)", "T11"),

    # H7 J7：恒返回 True ⇒ T12 必红（**每个**读数都被打上「无力检出」）
    ("H7", "return min(n_direct, n_prop) < 10", "return True", "T12"),

    # H7b J7 反向：恒返回 False ⇒ T12 必红（把 n=3 的警告消音）
    # ⚖⚠⚠ 这就是 244.30 那条「先把判据调松让仪器安静」的最小形态。
    ("H7b", "return min(n_direct, n_prop) < 10", "return False", "T12"),

    # H8 binom2 去掉截断 ⇒ T6 必红（对称处印出 1.209 > 1）
    ("H8", "p = min(1.0, 2.0 * min(lo, hi))", "p = 2.0 * min(lo, hi)", "T6"),

    # H8b binom2 把截断换成常数 1.0（244.23 那条变异）⇒ T5c 必红
    # ⚖⚠⚠ 症状：**范围断言抓不住它**（1.0 也在 [0,1] 内），
    #   必须靠 T5c 的精确值断言 —— 这就是「弱守卫」的代价。
    ("H8b", "p = min(1.0, 2.0 * min(lo, hi))", "p = 1.0", "T5c"),

    # H9 中位：偶数长度改回「取上中位」⇒ T1c 必红
    # ⚖⚠ 症状：带内倍数从 5.54 变成 4.23（**差 25%**），两个数都看着合理。
    ("H9", "return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])",
     "return s[n // 2]", "T1c"),

    # H10 并列取「序号」而不是平均秩 ⇒ T8 必红
    # ⚖⚠ 症状：全并列的一列被当成**有**方差 ⇒ 零方差不再报「未量到」，
    #   spearman 照样给出一个数 —— **「量不到」被读成了「量到了 0」**。
    # ⚖⚠⚠ 第一版写成 `i + 1.0` —— `i` 在内层循环里**不变** ⇒ 两个并列位
    #   仍然拿到同一个值 ⇒ 零方差照样成立 ⇒ **变异无效却看着像在变异**。
    #   ⚗⇒ 变异本身也会「可证无效」：改完必须确认它真的改变了行为。
    ("H10", "r[order[q]] = avg", "r[order[q]] = avg + 0.5 * q", "T8"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--probe", default=PROBE)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    base = open(args.target, encoding="utf-8").read()

    if args.selftest:
        rc, text = run_selftest(base)
        print(text)
        print("台架自身自检 rc=%d" % rc)
        return 0 if rc == 0 else 1

    # 台架先证明自己有效：原版必须全绿
    rc, text = run_selftest(base)
    ok, bad = _tests(text)
    print("台架基线：自检 %d 通过 / %d 条判据 ⇒ rc=%d"
          % (len(ok), len(ok) + len(bad), rc))
    if rc != 0 or bad:
        print("[FAIL] T0 基线就不是全绿 ⇒ 台架无效，先修工具（rc=%d 失败=%s）"
              % (rc, ",".join(sorted(bad))))
        return 1

    allok = True
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, ln = apply_mutation(base, needle, repl)
        except AssertionError as e:
            print("[FAIL] T1.%s 变异串无法定位：%s" % (name, e))
            allok = False
            continue
        rc, text = run_selftest(mut_src)
        _, mbad = _tests(text)
        if rc == 3:
            print("[FAIL] T2.%s 变异后源码直接崩：%s"
                  % (name, text.split("\n")[0][:90]))
            allok = False
        elif expect not in mbad:
            print("[FAIL] T3.%s 第 %d 行变异 %r 后 %s **仍 PASS** ⛔（台架看不见它；"
                  "真因通常不是判据没牙，而是这条判据**没独立承重**）"
                  % (name, ln, needle, expect))
            allok = False
        else:
            print("[PASS] %s 第 %d 行变异 %r ⇒ %s 转红"
                  % (name, ln, needle, expect))

    n = len(MUTATIONS)
    print("变异终检：%d/%d 全部被抓住" % (n if allok else n - 1, n)
          if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
