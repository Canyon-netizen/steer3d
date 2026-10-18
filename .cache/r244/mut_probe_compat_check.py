#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_probe_compat_check —— probe_compat_check.py 的**变异台**。

⚠⚠⚠ 本台架的头号理由（修订 244.36）
  这个工具的输出是一句「**候选探针改动向后兼容**」。⛔ 而这句话会被
  当成「可以改真探针了」的依据 ⇒ 一旦它**假绿**，代价就是三处判据被静默改写。
  ⚖⚠ 本工具 244.36 那一版已经**当场假绿过一次**，三处都是同一类病：

  ① 假绿：J7 写的是 `callable(fn)` ⇒ **包装器**方案照过不误
     （函数对象确实存在），⚖⚠ 而抽出来**一调就 NameError**
     ⇒ 判据只验了「抽得出」，没验「抽出来能用」。
  ② 覆盖缺口：J1 网格只跑 `nested=False`，⚖⚠ 而补丁改的恰恰是
     `nested=True` 那条 return ⇒ **被改的那条路从未被验**。
  ③ 判据被自己遮住：J9「把模块重指到打过补丁的探针」若只改**模块全局**，
     `def f(p=PROBE)` 的默认值在**定义时**就绑定了 ⇒ 改不动
     ⇒ J9 会**静默地继续读真探针** ⇒ **恒绿**。
  ⚗⇒ 恒绿的 J9 比没有 J9 **更危险**：它会让「三个自检都过」在
     根本没验过补丁的情况下被印出来。⇒ 必须有 C9 当场证明陷阱真实存在。

变异台设计纪律（同 mut_pair_ladder_preflight）：
1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
2. ⚖ needle 必须唯一、落在代码行、⛔ 不得指进前导缩进。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。
5. ⚖⚠ **崩 ≠ 抓到**：崩掉的变异单列出来，不许冒充「按判据转红」。

跑法：
    python3 mut_probe_compat_check.py
    python3 mut_probe_compat_check.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或台架自身基线不绿。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "probe_compat_check.py")
PROBE = os.path.abspath(os.path.join(HERE, "..", "mutbak", "r204_noise_probe.py"))


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
    """⚖ needle/repl 可以是 str，也可以是**等长**的 list（多点联合变异）。"""
    needles = [needle] if isinstance(needle, str) else list(needle)
    repls = [repl] if isinstance(repl, str) else list(repl)
    if len(needles) != len(repls):
        raise AssertionError("needle 与 repl 数量不等")
    out, lines = src, []
    for nd, rp in zip(needles, repls):
        lineno, line = find_code_line(out, nd)
        new_line = line.replace(nd, rp, 1)
        out = out.replace(line, new_line)
        lines.append(lineno)
    if out == src:
        raise AssertionError("变异没有真的改到文件（needle=%r）" % (needles,))
    return out, lines[0] if len(lines) == 1 else lines


def _load(src):
    mod = types.ModuleType("compat_mut")
    mod.__file__ = os.path.abspath(TARGET)
    exec(compile(src, TARGET, "exec"), mod.__dict__)
    return mod


def run_selftest(src):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = _load(src).selftest()
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    return rc, buf.getvalue()


def run_real(src):
    """⚖ 跑真实数据那条路。⇒ (rc, text)；rc==3 表示**崩**，不算干净的红。

    ⚖⚠ text 取 `run()` 的**返回值**，⛔ 不是 stdout
       —— `run()` 是返回文本、不打印，取 stdout 会拿到**空串**，
       ⛔ 而空串会让「哪一段红了」这个问题**无处可查**。
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            txt, rc = _load(src).run(PROBE)
    except Exception as e:
        return 3, "%s: %s\n%s" % (type(e).__name__, e, buf.getvalue())
    return rc, (txt or "") + "\n" + buf.getvalue()


def red_lines(text):
    """⚖ 报告里带 ⛔ 的行 —— 它们是「按判据转红」的落点。"""
    return [ln.strip() for ln in text.split("\n") if "⛔" in ln]


def _tests(text):
    ok, bad = set(), set()
    for line in text.split("\n"):
        if line.startswith("[PASS]"):
            ok.add(line.split()[1])
        elif line.startswith("[FAIL]"):
            bad.add(line.split()[1])
    return ok, bad


# (名字, kind, needle, repl, expect)
#   kind="st"  ⇒ 期望被该自检编号抓住
#   kind="run" ⇒ 期望真实数据那条路 rc≠0
MUTATIONS = [
    # Q1 ⚠⚠ J1 **忽略 nested** ⇒ 只比 `nested=False` 那一路
    #   症状：补丁改的是 `nested=True` 的 return，而判据压根没看它
    #   ⇒ 被改的地方**从未被验**，判据却全绿。
    ("Q1", "st", "a(n, k, nested=nested)", "a(n, k)", "C2"),

    # Q2 J3 放宽「恰好差一个」⇒ 差 0 个也放过
    #   症状：报告印「两档只差一个位点」，而实际可能一个都没换。
    ("Q2", "st",
     "return sb != sf and len(sb) == k and len(sf) == k and len(sb ^ sf) == 2",
     "return sb != sf and len(sb) == k and len(sf) == k and len(sb ^ sf) >= 0",
     "C3"),

    # Q3 ⚠⚠ J4 退回比**数值最大**（244.36 已修的那一条）⇒ C5 必红
    ("Q3", "st", "worst = max(sb, key=lambda j: ranks[j])", "worst = max(sb)", "C5"),

    # Q4 ⚠⚠⚖ **头号**：J7 恒返回 True ⇒ 包装器方案照过不误
    #   症状：抽出来的函数一调就 NameError，报告却印「✅ 抽取契约」。
    ("Q4", "st",
     "if len(out) != k or len(set(int(x) for x in out)) != k:",
     "if False:", "C6b"),

    # Q5 ⚠⚠⚖ rebind **不改 __defaults__** ⇒ C9 必红
    #   症状：J9 静默继续读**真探针** ⇒ 「三个自检都过」变成恒绿。
    ("Q5", "st",
     "nd = tuple(new_path if (isinstance(x, str) and x in olds) else x for x in d)",
     "nd = d", "C9"),

    # Q6 J6 守卫失效（非嵌套 + force 不再报错）⇒ 真实路 rc≠0
    #   症状：`force` 在非嵌套路径上**静默失效**，跑批照跑，
    #         而格表里记的是「我以为强制了这个位点」。
    ("Q6", "run", "if force is not None and not nested:", "if False:", None),

    # Q7 force 整体变成空操作 ⇒ 真实路 rc≠0（J3：两档一个位点都没差）
    ("Q7", "run", "if int(force) not in pos:", "if False:", None),

    # Q8 ⚠⚠⚖⚖ **本轮的头条变异**：把默认路径那一行**改写**掉
    #   （即 244.36 那个「行为完全等价」的版本）
    #   症状：J1/J2/J3/J8 **照样全绿**（行为确实等价），
    #         ⛔ 但 `ladder_position_audit` 的自检 **A4** 报红 ——
    #         它的夹具按**这一行的字面文本**做变异，str.replace 静默变空操作。
    #   ⚖⇒ 这条变异证明：**行为级兼容 ≠ 文本级兼容**，
    #         而「J1/J2/J3 全过」与「J9 里 A4 仍绿」必须**同时**成立。
    # ⚖⚠⚠⚠ 这条变异**自己栽了两次**，都是「变异必须先证明自己有效」：
    #   ① 第一版只删掉 `if force is None` 短路、没补 `force is not None`
    #      ⇒ 默认路径 `int(None)` **崩**（台架拒绝把崩冒充抓到，报 WARN）；
    #   ② 第二版把 `_perm = _rng.permutation(n)` 写成**两遍**
    #      ⇒ RNG 前进、第二次抽取不同 ⇒ **J1 正确地红了**
    #      ⛔ 而 J1 红并不是这条变异想证明的那件事。
    #   ⚗⇒ 第三版才既等价又无那一行：第二遍改名成 `_dummy`（仍消耗 RNG，
    #     但没人读它）⇒ `_perm` 保持第一次抽取、`pos` 重算同值。
    # ⚖⚠ 应用顺序：**倒着来**。`apply_mutation` 是逐条就地替换，
    #   若先插 `_perm = ...` 那行，needle「`_perm = _rng.permutation(n)`」
    #   就会变成**命中 2 行** ⇒ 台架自己先报错（这正是它的纪律在起作用）。
    #   ③ 第三版忘了把 `force is not None` 一起搬过来
    #      ⇒ 默认路径 `int(None)` **又崩**（台架仍报 WARN，不冒充抓到）。
    #   ⚗⇒ 四处都搬齐之后，它才是**行为等价**的那一版，
    #     而它的红**只能**来自 A4 的 `assert bad != seg`。
    ("Q8", "run",
     ["\"        if int(force) not in pos:\\n\"",
      "\"        _perm = _rng.permutation(n)\\n\"",
      "\"        if force is None:\\n\"",
      "\"            return sorted(int(x) for x in _rng.permutation(n)[:k])\\n\""],
     ["\"        if force is not None and int(force) not in pos:\\n\"",
      "\"        _dummy = _rng.permutation(n)\\n\"",
      "\"        _perm = _rng.permutation(n)\\n\"",
      "\"        pos = sorted(int(x) for x in _perm[:k])\\n\""],
     None),

    # Q9 C1 锚点计数守卫被拆 ⇒ C8 必红
    #   症状：探针形态变了（锚点出现 2 处）也照样打补丁 ⇒ 打到错的地方。
    ("Q9", "st", "if c != 1:", "if False:", "C8"),

    # Q10 J6 只认 ValueError；改成 KeyError ⇒ 真实路 rc≠0
    #   症状：守卫还在，但报错类型不对 ⇒ 排障时被误导成「别的问题」。
    ("Q10", "run", "raise ValueError(\\n", "raise KeyError(\\n", None),

    # Q11 换掉的是**秩第 0 个**而不是秩最大的 ⇒ 真实路 rc≠0（J4）
    #   症状：配对两档仍然只差一个位点（J3 照样绿），
    #         ⛔ 但换掉的是**任意**那个 ⇒ S ⊂ S' 的构造依据变了，
    #           「嵌套阶梯 + 只差一个」这两条性质不再同时成立。
    ("Q11", "run", "int(_perm[k - 1])", "int(_perm[0])", None),
]

# ⚖⚠⚠ 工具里 `make_patched` 那句 `if patched == src: raise HardFail` **没有变异**。
#   原因：三个替换都**按构造**改变文本（SIG_NEW≠SIG_OLD、插入 FORCE_GUARD 非空），
#   ⇒ 那道护栏**原理上不可达** ⇒ 打多少变异它都不会红。
#   ⚗⇒ 承重不明的护栏要么删、要么写成能红的形状。这条留着是当**双保险**，
#     ⛔ 但它**不在**变异台覆盖范围内 —— 写在这里是为了不让下一个人
#     误以为「全部判据都有变异盯着」。


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
        print(text2)
        print("台架基线：自检 rc=%d、真实路 rc=%d" % (rc, rc2))
        return 0 if (rc == 0 and rc2 == 0) else 1

    rc, text = run_selftest(base)
    ok, bad = _tests(text)
    rc2, _ = run_real(base)
    print("台架基线：自检 %d 通过 / %d 条 ⇒ rc=%d；真实路 rc=%d"
          % (len(ok), len(ok) + len(bad), rc, rc2))
    if rc != 0 or bad or rc2 != 0:
        print("[FAIL] T0 基线就不是全绿 ⇒ 台架无效，先修工具"
              "（自检 rc=%d 失败=%s / 真实路 rc=%d）"
              % (rc, ",".join(sorted(bad)), rc2))
        return 1

    allok, crashed = True, []
    for name, kind, needle, repl, expect in MUTATIONS:
        try:
            mut_src, ln = apply_mutation(base, needle, repl)
        except AssertionError as e:
            print("[FAIL] T1.%s 变异串无法定位：%s" % (name, e))
            allok = False
            continue
        if kind == "st":
            r, t = run_selftest(mut_src)
            _, mbad = _tests(t)
            if r == 3:
                print("[FAIL] T2.%s 变异后源码直接崩：%s（⛔ 崩 ≠ 抓到）"
                      % (name, t.split("\n")[0][:88]))
                allok = False
            elif expect not in mbad:
                print("[FAIL] T3.%s 第 %s 行变异 %r 后 %s **仍 PASS** ⛔"
                      "（真因通常在**用例没覆盖那个维度**，不在判据松紧）"
                      % (name, ln, needle if isinstance(needle, str) else "<多点>", expect))
                allok = False
            else:
                print("[PASS] %s 第 %s 行变异 %r ⇒ %s 转红"
                      % (name, ln, needle if isinstance(needle, str) else "<多点>", expect))
        else:
            r, t = run_real(mut_src)
            if r == 3:
                print("[WARN] T4.%s 变异后**崩**（%s）⇒ 被抓住但**不是干净的按判据变红**"
                      % (name, t.split("\n")[0][:60]))
                crashed.append(name)
                continue
            if r == 0:
                print("[FAIL] T4.%s 变异 %r 后真实路**仍 rc=0** ⛔（判据没咬住）"
                      % (name, needle if isinstance(needle, str) else "<多点>"))
                allok = False
            else:
                reds = red_lines(t)
                print("[PASS] %s 第 %s 行变异 %r ⇒ 真实路按判据转红（rc=%d）"
                      % (name, ln, needle if isinstance(needle, str) else "<多点>", r))
                for rl in reds[:2]:
                    print("        ↳ 落点：%s" % rl[:104])

    n = len(MUTATIONS)
    if crashed:
        print("⚖⚠ 其中 %d 条是**崩**（%s）：被抓住，但⛔ 不是按判据变红"
              % (len(crashed), ",".join(crashed)))
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
