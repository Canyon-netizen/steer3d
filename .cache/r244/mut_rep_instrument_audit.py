#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_rep_instrument_audit —— `rep_instrument_audit.py` 的变异台（修订 244.46）

⚠⚠⚠⚖⚠⚠⚠⚖ **这个台架的特殊性**：别的台架变异的是**工具源码**，
  本台架变异的是**被审计的探针源码**。

  ⚖ 为什么必须这样：审计工具的判据是「探针长这样 ⇒ R 轮逐位相同」。
  ⛔ 如果只变异工具源码，我验的是「工具自己会不会报错」，
  ⛔ **验不到「探针真的变脏时判据会不会红」** —— 而那才是它存在的理由。
⚗⇒ 每条变异都往真探针里**注入一种真实的污染源**（用循环变量、
  在外层 for 体内改自由变量、引入 RNG、去掉 .eval()、让 inj 在首次调用后变、
  去掉 subprocess），⛔ 一条都不许是「只改措辞/判据文案」。

⚖⚠⚠ 变异纪律（同本项目其它台架）：
  1. 只改**代码行**；⛔ 不许改注释/散文。
  2. needle 必须**唯一命中、落在代码行、不在前导缩进里**。
  3. ⛔ 不许事后调变异调到绿为止。
  4. **崩 ≠ 抓到**：崩掉的单列 WARN。
  5. ⛔ 期望标签必须是**具体那一条判据**，⛔ 不许写「工具红」了事。

跑法：
    python3 mut_rep_instrument_audit.py
退出码：0 = 全部变异都被指定的那条判据抓住；1 = 有变异存活，或台架基线不绿。
"""

import argparse
import ast
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "rep_instrument_audit.py")
PROBE = os.path.abspath(os.path.join(HERE, "..", "mutbak", "r204_noise_probe.py"))


# --------------------------------------------------------------- needle
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
                "needle 指到第 %d 行第 %d 列，落在前导缩进里 ⇒ 请去掉前导空格" % (i, pos))
        hits.append((i, line))
    if len(hits) != 1:
        raise AssertionError("needle 命中 %d 行（要求恰好 1）：%r" % (len(hits), needle))
    return hits[0]


def apply_block(src, old, new):
    """⚖⚠⚖ **块 needle 必须走 `src.replace` 整块替换** ⛔ 不许走单行查找 ——
    `find_code_line` 是**逐行**找的，多行串必然 0 命中（244.46 第一版栽在这）。
    ⚖⚠⚠⚖ 后置断言照旧：旧块必须**消失**、新块必须**出现**（244.45 教训）。
    """
    n = src.count(old)
    if n != 1:
        raise AssertionError("块 needle 命中 %d 处（要求恰好 1）" % n)
    out = src.replace(old, new, 1)
    if out == src:
        raise AssertionError("块替换没有产生任何变化")
    assert new in out, "新块没进去"
    if old not in new:              # 插入型变异：新块合法地含回旧块（M7 就是）
        assert old not in out, "旧块仍在 ⇒ 替换没落地"
    return out, src[:src.index(old)].count("\n") + 1


def apply_mutation(src, needle, repl):
    """⚖ needle/repl 可以是 str，也可以是**等长**的 list（多点联合变异）。"""
    if isinstance(needle, str) and "\n" in needle:
        return apply_block(src, needle, repl)
    ns = [needle] if isinstance(needle, str) else list(needle)
    rs = [repl] if isinstance(repl, str) else list(repl)
    if len(ns) != len(rs):
        raise AssertionError("needle 与 repl 数量不等")
    out, lines = src, []
    for nd, rp in zip(ns, rs):
        lineno, line = find_code_line(out, nd)
        out = out.replace(line, line.replace(nd, rp, 1))
        lines.append(lineno)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % (ns,))
    # ⚖⚠⚠⚖ 后置断言：每个旧串必须**真的消失**。
    #   244.45 栽过 `.replace("(tmp)", …)` 在 `mod.__dict__, tmp` 上是**空操作**
    #   而「原串命中 1 处」的断言照样通过 ⇒ 静默失效。
    for nd, rp in zip(ns, rs):
        # ⚖⚠⚠⚖ 「旧串必须消失」有一个**例外**（244.46 第二版）：
        #   **插入型**变异的新串合法地把旧串原样含回来
        #   （M2 = `rep[_lab] = vals` → `b_mark = …\n  rep[_lab] = vals`）。
        #   ⇒ 那种情况只查「新串在不在」；否则才查「旧串消失」。
        assert rp in out, "新串没进去：%r" % rp[:48]
        if nd not in rp:
            assert nd not in out, "替换没落地（旧串仍在）：%r" % nd
    return out, (lines[0] if len(lines) == 1 else lines)


# --------------------------------------------------------------- 载入
def _load(path):
    mod = types.ModuleType("ria_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(io.open(path, encoding="utf-8").read(), path, "exec"), mod.__dict__)
    return mod


def run_audit(mod, src, label):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            lines, rc = mod.audit(src, label)
    except Exception as e:
        return 3, ["%s: %s" % (type(e).__name__, e)], ""
    return rc, lines, buf.getvalue()


def verdict_line(lines, tag):
    for ln in lines:
        s = ln.strip()
        if s.startswith(tag) and s[len(tag):len(tag) + 1] in (" ", "b"):
            return s
    return ""


# --------------------------------------------------------------- 变异表
#  (名字, needle, repl, 期望标签)
#  期望标签：
#    "R1"/"R2"/"R3"/"R4"/"R4b"/"R5" ⇒ 那一行必须出现 ⛔ 且整体 rc≠0
#    "REFUSE:子串"                      ⇒ 必须 HardFail 成干净的红（rc=1）并带上子串
MUTATIONS = [
    # M1 ⛔ 循环体**用**循环变量 ⇒ 每次迭代输入都不同 ⇒ 「R 轮逐位相同」失效
    ("M1", "for _ in range(max(1, a.repeat))]",
     "for _al in range(max(1, a.repeat))]", "R1"),

    # M2 ⛔ 在外层 for 的**体内**改掉自由变量 b_mark（只在推导式之后）
    #    ⇒ 第 2 次外层迭代看到的 b_mark 与第 1 次不同 ⇒ 跨剂量比较被污染
    ("M2", "rep[_lab] = vals",
     "b_mark = b_mark + 0.0\n        rep[_lab] = vals", "R2"),

    # M3 ⛔ 循环体里真的调 torch RNG ⇒ R 轮**必然**不同
    ("M3", "vals = [lse_t(forward(W, _al)[mk]) - b_mark",
     "vals = [torch.rand(1)[0] + lse_t(forward(W, _al)[mk]) - b_mark", "R4"),

    # M4 ⛔ 去掉 .eval() ⇒ dropout 在跑 ⇒ 重复不再是自我重复
    ("M4", ".cuda().eval()", ".cuda()", "R4b"),

    # M5 ⛔ `inj` 在首次 forward 调用**之后**被重新赋值
    #    ⇒ 第二次调用开始读到不同的注入位置 ⇒ 判据必须拦
    ("M5", "base = forward(W, 0.0)",
     "base = forward(W, 0.0)\n    inj = inj + 0", "R3"),

    # M6 ⛔ batch 不再用 subprocess ⇒ 「零改动量跨进程噪声」那条不成立
    ("M6", "p = subprocess.run(cmd, capture_output=True, text=True)",
     "p = _inline(cmd)", "R5"),

    # M7 ⛔ 出现**两个**读 a.repeat 的推导式 ⇒ 必须拒读，⛔ 不许取第一个凑合
    ("M7",
     "            vals = [lse_t(forward(W, _al)[mk]) - b_mark\n"
     "                    for _ in range(max(1, a.repeat))]",
     "            vals = [lse_t(forward(W, _al)[mk]) - b_mark\n"
     "                    for _ in range(max(1, a.repeat))]\n"
     "            vals2 = [lse_t(forward(W, _al)[mk]) - b_mark\n"
     "                    for _ in range(max(1, a.repeat))]",
     "REFUSE:2 个候选"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    args = ap.parse_args()

    probe_src = io.open(PROBE, encoding="utf-8").read()
    mod = _load(args.target)

    # ---- 基线：必须自检 0 错 + 真探针审计全绿 ------------------------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        st_rc = mod.selftest(PROBE)
    st_txt = buf.getvalue()
    base_rc, base_lines, _ = run_audit(mod, probe_src, "真探针")
    n_pass = st_txt.count("[PASS]"); n_fail = st_txt.count("[FAIL]")
    print("台架基线：自检 %d 通过 / %d 条 ⇒ rc=%d；真探针审计 rc=%d"
          % (n_pass, n_pass + n_fail, st_rc, base_rc))
    if st_rc != 0 or n_fail or base_rc != 0:
        print("[FAIL] T0 基线就不是全绿 ⇒ 台架无效，先修工具（自检 rc=%d 失败=%d / "
              "真探针 rc=%d）" % (st_rc, n_fail, base_rc))
        return 1

    allok, crashed = True, []
    for name, needle, repl, expect in MUTATIONS:
        try:
            mut_src, ln = apply_mutation(probe_src, needle, repl)
            ast.parse(mut_src)              # ⛔ 变异不许把源码写坏
        except (AssertionError, SyntaxError) as e:
            print("[FAIL] T1.%s 变异串无法定位或写坏了源码：%s" % (name, e))
            allok = False
            continue

        rc, lines, _ = run_audit(mod, mut_src, "%s 变异" % name)

        if rc == 3:
            print("[WARN] T2.%s 变异后工具**崩** ⇒ 被抓住但**不是干净的按判据变红**"
                  % name)
            crashed.append(name)
            continue

        if expect.startswith("REFUSE:"):
            sub = expect.split(":", 1)[1]
            got = "\n".join(lines)
            if rc == 1 and sub in got:
                print("[PASS] %s 第 %s 行 ⇒ 拒读（%s）"
                      % (name, ln, next((x.strip() for x in lines
                                         if sub in x), "—")[:88]))
            else:
                print("[FAIL] T3.%s 第 %s 行 ⇒ 期望拒读「%s」，实得 rc=%d%s"
                      % (name, ln, sub, rc,
                         "" if rc == 0 else " / " + got.strip()[:70]))
                allok = False
            continue

        vl = verdict_line(lines, expect)
        if "⛔" in vl and rc != 0:
            print("[PASS] %s 第 %s 行 ⇒ %s 转红（rc=%d）" % (name, ln, expect, rc))
            print("        ↳ %s" % vl[:112])
        else:
            print("[FAIL] T4.%s 第 %s 行 ⇒ %s **没有转红** ⛔（该判据量不到这种污染）"
                  % (name, ln, expect))
            print("        ↳ 实得：%s" % (vl[:112] or "（没这一行）"))
            allok = False

    n = len(MUTATIONS)
    if crashed:
        print("⚖⚠ 其中 %d 条是**崩**（%s）：被抓住，但⛔ 不是按判据变红"
              % (len(crashed), ",".join(crashed)))
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
