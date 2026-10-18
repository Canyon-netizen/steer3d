#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_arm_contrast_audit —— arm_contrast_audit.py 自检的**变异台**。

⚠⚠⚠ 本台架的头号理由（修订 244.37）
  这个工具的输出会**改写一条已经进了账本的 🔴**：
  「rand 臂传播层方向性剂量梯度比 w 臂强 ⇒ 负控比处理臂强」。
  ⚖⚠ 而那条结论原来的依据是**比较两个 p 值的大小**。
  ⚖⚠⚠ 所以本工具的失效方向**特别危险**：
  ① **判据把「不一致对」与「一致对」搞混** ⇒ McNemar p 从 0.6875 变成 0.0156
     ⇒ 把「无证据」印成「**差异显著**」⇒ ⛔ 凭空造出一个结论。
     ⚖⚠⚠ 而作者本人**真的**先犯过一次（第一版就是拿 both+/both− 当 b、c）。
  ② 判据恒返回 True ⇒ 「两臂有差异」被无条件印出。
  ③ 单臂 p 的双侧倍数少乘 2 ⇒ 报告里那两个被**反复引用**的数直接错一半。

变异台设计纪律（同 mut_probe_compat_check）：
1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
2. ⚖ needle 必须唯一、落在代码行、⛔ 不得指进前导缩进。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。
5. ⚖⚠ **崩 ≠ 抓到**：崩掉的变异单列，不许冒充「按判据转红」。

跑法：
    python3 mut_arm_contrast_audit.py
    python3 mut_arm_contrast_audit.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "arm_contrast_audit.py")


def find_code_line(src, needle):
    """⚖ needle 可以是**多行块**：只要整块在文件里**唯一**即可，
       并用块的首行算出行号。
    ⚖⚠⚠ 为什么需要块定位：`if n == 0:` 这类守卫在同一个文件里有**两处同文**
      （`mcnemar_exact` 与 `wilcoxon_exact` 各一处），
      ⛔ 单行 needle 分不开 ⇒ 台架会报「无法定位」而那不是变异的问题。
    ⚖⚠⚠ 块定位**不放宽**「必须是代码行」这条纪律：
      块首行仍要通过下面的注释/前导缩进检查。
    """
    if "\n" in needle:
        if src.count(needle) != 1:
            raise AssertionError("块 needle 命中 %d 处（要求恰好 1）：%r"
                                 % (src.count(needle), needle[:40]))
        off = src.index(needle)
        first = needle.split("\n")[0]
        lineno = src.count("\n", 0, off) + 1
        if first.lstrip().startswith("#"):
            raise AssertionError("块 needle 首行（第 %d 行）是**注释**" % lineno)
        return lineno, first
    return _check_code_line(*_scan_line(src, needle), needle)


def _scan_line(src, needle):
    hits = []
    for i, line in enumerate(src.split("\n"), 1):
        if line.find(needle) >= 0:
            hits.append((i, line))
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1 行）：%r"
                             % (len(hits), needle))
    return hits[0]


def _check_code_line(lineno, line, needle):
    pos = line.find(needle.split("\n")[0])
    stripped = line.lstrip()
    if stripped.startswith("#"):
        raise AssertionError("needle 指到第 %d 行，那一行是**注释**"
                             "（变异的是散文，不是代码）" % lineno)
    if pos >= 0 and pos < (len(line) - len(stripped)):
        raise AssertionError(
            "needle 指到第 %d 行第 %d 列，落在前导缩进里（前导空白占 %d 列）"
            "⇒ 请去掉 needle 的前导空格" % (lineno, pos, len(line) - len(stripped)))
    return lineno, line


def apply_mutation(src, needle, repl):
    """⚖ 定位由 `find_code_line` 负责（单行 or 多行块），
       替换一律按**整块**做：`src.replace(needle, repl, 1)`。
    ⚖⚠ 第一版这里仍按「单行」替换 ⇒ 块 needle 定位成功但**替换落空**
       ⇒ 台架报「变异没有真的改到文件」，而那不是变异本身的问题。
    """
    lineno, _line = find_code_line(src, needle)
    out = src.replace(needle, repl, 1)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % needle[:60])
    return out, lineno


def run_selftest(src):
    mod = types.ModuleType("contrast_mut")
    mod.__file__ = os.path.abspath(TARGET)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = _exec(src).selftest()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    return rc, buf.getvalue()


def _exec(src):
    mod = types.ModuleType("contrast_mut")
    mod.__file__ = os.path.abspath(TARGET)
    exec(compile(src, TARGET, "exec"), mod.__dict__)
    return mod


def run_real(src):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            txt, rc = _exec(src).run()
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
    # R1 ⚠⚠⚖⚖ **头号**：McNemar 拿**一致对**当不一致对
    #   ⇒ 真实数据上 p 从 0.6875 变成 0.2891 ⇒ 把「无证据」印成「接近显著」
    #   ⚖⚠⚠ 这正是作者第一版**真的**犯的那个错（账本 244.37 有记）。
    ("R1", "if a > 0 > c)", "if a > 0 and c > 0)", "C1"),

    # R1b 反过来：另一格也换成一致对 ⇒ 不一致对变空 ⇒ 永远 p=1.0
    #   ⇒ 「两臂有差异」被**永久掩盖**（另一种方向的假绿）。
    #   ⚖⚠⚠ C1 的夹具是专门挑的：两臂 6 条同为正、2 条 w−/rand+，
    #   ⛔ 一致对与不一致对的计数**不同**（6/0 vs 0/2）⇒ 两种算法给出不同的 p。
    ("R1b", "if a < 0 < c)", "if a < 0 and c < 0)", "C1"),

    # R2 零个不一致对时必须给 p=1.0（⛔ 不是 0.0）
    #   ⇒ 症状：「两臂**一条都没反号**」被印成「差异极显著」。
    ("R2", "    n = b + c\n    if n == 0:\n        return 1.0",
     "    n = b + c\n    if n == 0:\n        return 0.0", "C2"),

    # R3 双侧少乘 2 ⇒ p 缩小一半
    #   ⚖⚠⚠ 真实数据上 0.6875 ⇒ 0.3438，结论方向不变 ⇒ **症状最隐蔽的一条**
    ("R3", "return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n)",
     "return min(1.0, 1.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n)",
     "C1"),

    # R3b k 用 max 而非 min ⇒ 参考分布跟着最不平衡的那一格走
    ("R3b", "k = min(b, c)", "k = max(b, c)", "C1"),

    # R4 Wilcoxon 零差不剔 ⇒ n 虚高、p 变小 ⇒ 把「没量到」算成「有证据」
    ("R4", "nz = [float(d) for d in deltas if float(d) != 0.0]",
     "nz = [float(d) for d in deltas]", "C3"),

    # R4b Wilcoxon 全零时也返回 0.0 ⇒ 「一个非零差都没有」被当成极显著
    ("R4b", "    if n == 0:\n        return 1.0, n",
     "    if n == 0:\n        return 0.0, n", "C3"),

    # R5 ⚠⚠ 并列取**严格小于**排名 ⇒ 秩被压扁 ⇒ p 从 0.625 变 0.375
    #   ⚖⚠⚠ 这是本工具里最容易写错、而 C3（无并列）测不出来的那一步
    #   ⇒ 由 C3b（专门带并列的夹具）承重。
    ("R5", "mid = (i + j) / 2.0 + 1.0", "mid = float(i + 1)", "C3b"),

    # R6 单臂符号检验少乘 2 ⇒ 报告里那两个被反复引用的 p 直接错一半
    ("R6", "    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(0, min(pos, n - pos) + 1))\n               / 2.0 ** n)",
     "    return min(1.0, 1.0 * sum(math.comb(n, i) for i in range(0, min(pos, n - pos) + 1))\n               / 2.0 ** n)",
     "C9"),

    # R7 禁令被拆 ⇒ 「两个 p 值差得远」又被当成差异证据
    ("R7", "return False", "return True", "C4"),

    # R8 ⚠⚠⚖ unwrap 解包错了 ⇒ C8（夹具与生产形状对齐那道）失去牙齿
    #   ⚖⚠⚠ 第一版写的是「把形状检查改成 `if False:`」⇒ 那样会**崩**，
    #   ⛔ 而崩 ≠ 抓到 ⇒ 换成「解包不解」：自检能红、真实路另外会炸。
    ("R8", "out[t] = v[0]", "out[t] = v[1]", "C8"),

    # R9 轨迹集合不等时不再 HardFail，改为静默继续 ⇒ 「先交后算」
    #   ⇒ 不配对的轨迹被悄悄丢掉，而报告照样印结论。
    ("R9", "if tids_w != tids_r:", "if False:", "C6"),

    # R10 未量到的 rho 不再剔出分母（把 None 当 0.0 参与）
    ("R10", "    both = {t: (pw[t], pr[t]) for t in sorted(tids_w)\n            if pw[t] is not None and pr[t] is not None}",
     "    both = {t: (0.0 if pw[t] is None else pw[t], 0.0 if pr[t] is None else pr[t])\n            for t in sorted(tids_w)}", "C5"),
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
        rc2, text2 = run_real(base)
        print(text2[-900:])
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
                  "（真因通常在**用例没覆盖那个维度**）" % (name, ln, needle, expect))
            allok = False
        else:
            print("[PASS] %s 第 %d 行变异 %r ⇒ %s 转红" % (name, ln, needle, expect))
            rr, tt = run_real(mut_src)
            if rr != 3 and "McNemar 精确" in tt:
                for ln2 in tt.split("\n"):
                    if "McNemar 精确" in ln2 or "无可检出差异" in ln2:
                        print("        ↳ 真实路：%s" % ln2.strip()[:96])
                        break

    n = len(MUTATIONS)
    if crashed:
        print("⚖⚠ 其中 %d 条是**崩**（%s）：被抓住，但⛔ 不是按判据变红"
              % (len(crashed), ",".join(crashed)))
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
