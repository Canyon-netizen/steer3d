#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_pair_ladder_preflight —— pair_ladder_preflight.py 自检的**变异台**。

⚠⚠⚠ 本台架的头号理由（修订 244.34）
  这个预检工具的作用是「在发批前证明那个配对设计成立」。
  ⚖⚠⚠ 而它的失效方向是**最坏的那种**：
  ⚖ ① 守卫写得太松 ⇒ 放行一个**实际上不成立**的位点对
     ⇒ 报告说「只差一个位点、剂量变化可忽略」，⛔ 而跑批要花 GPU；
  ⚖ ② 守卫写得太紧/形状假设错 ⇒ 对**当前这份真实源码**也报红
     ⇒ ⚖ 第一版就栽在这：`if fn.args.defaults: raise HardFail`
        ⛔ 而 `_k_positions(n, k, seed=0, nested=False)` 本来就有 2 个默认值
        ⇒ 那条守卫对真实数据也是红的。
     ⚗⇒ **守卫必须写成「期望的形态」，⛔ 不是「没有某种形态」**。
  ⚖ ③ 测试**调错层** ⇒ 测的是别人的行为
     ⇒ 第一版 T2 调 `readout_rank`，而 K1 的守卫在 `pair_sets` 里。

变异台设计纪律（同 mut_dose_axis_audit）：
1. ⚠⚠⁴ **变异只改一处代码点**，⛔ 不许改注释/散文。
2. ⚖ needle 必须唯一、落在代码行、⛔ 不得指进前导缩进。
3. ⛔ 不许事后调变异调到绿为止。
4. ⚖ 变异在**内存里** exec，⛔ 不落临时文件、不动原件。

跑法：
    python3 mut_pair_ladder_preflight.py
    python3 mut_pair_ladder_preflight.py --selftest
退出码：0 = 全部变异都被抓住；1 = 有变异存活，或台架自身自检失败。
"""

import argparse
import contextlib
import io
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "pair_ladder_preflight.py")


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
    mod = types.ModuleType("pair_mut")
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
    # P1 **夹住**失效：k_base 不再夹到 rank ⇒ T9 必红
    # ⚖⚠⚠⚖ 244.34 的核心修正：第一版的三道守卫（秩≥1 / S 不含读出位点 /
    #   S⊂S' 且恰好差 1）**互相遮住** —— 若读出位点已在 S 里则 Sp=S
    #   ⇒ K3 必然触发 ⇒ K1/K2 的变异**全部存活**。
    #   ⚖⚠ 而「夹住」本身有独立后果：小秩轨迹（n=2210 秩=140）上
    #   ⛔ 不夹就会取 k_base=552 ⇒ 集合含读出位点 ⇒ 覆盖率报错。
    ("P1", "k_base = min(k_base, rank)", "k_base = k_base", "T9"),
    # P2 K3：不再要求「恰好差一个位点」⇒ T7 必红
    # ⚖⚠⚖ 症状：报告印「两档只差一个位点」，而实际差 372 个
    #   ⇒ 整个预检结论失效，且 ⛔ 没有告警。
    ("P2", "if not S < Sp or len(Sp - S) != 1:", "if False:", "T7"),
    ("P2b", "if (n - 1) in S", "if False", "T7"),

    # P3 秩=0 的不可行判定**报错文案**被改掉 ⇒ T2 必红
    # ⚖⚠⚠⚖ 这条断言的是**文案**不是「抛不抛」—— 那是刻意的：
    #   秩=0 时「抛」这件事由 K3（Sp−S 必须为 1）也会触发，
    #   ⚖⚠ 所以「抛」**不能**归因给这条判定 ⇒ 它没有独立承重。
    #   ⚗⇒ 它的独立价值是**可诊断性**：报错必须说清「这个 n 上配对不存在」，
    #     否则排障时会误以为是别处坏了。⚗⇒ 文案是行为，可以被断言。
    ("P3", "**配对不可行**", "不可行", "T2"),

    # P4 K4：门槛放宽 ⇒ T5 必红
    # ⚖⚠⚠ 症状：Δcov 门槛一松，「剂量变化可忽略」这句话就变成假的
    #   ⇒ 这是 244.26 的 H6（门槛松紧改变结论）同一个配方。
    ("P4", "PAIR_DCOV_MAX = 0.01", "PAIR_DCOV_MAX = 0.5", "T5"),
    ("P4b", "PAIR_DCOV_MAX = 0.01", "PAIR_DCOV_MAX = 0.005", "T5"),

    # P5 K4：判定恒返回 True ⇒ T4 必红（反向不许误放行）
    ("P5", "return d_pair <= PAIR_DCOV_MAX", "return True", "T4"),

    # P6 K5：不再报告被夹住的轨迹 ⇒ T6 必红
    # ⚖⚠⚠ 症状：**14 条里有 2 条**的配对剂量与其余不同，这个事实从报告里消失
    #   ⇒ 读者会以为 14 条剂量一致 ⇒ 跨轨迹聚合就变成合法的了。
    ("P6", "return cov_s < CLAMP_COV", "return False", "T6"),

    # P6b K5 反向：恒返回 True ⇒ T6 必红（把「没被夹住」也误喊）
    ("P6b", "return cov_s < CLAMP_COV", "return True", "T6"),

    # P7 readout_rank：把未排序的排列**排序后再找** ⇒ T1 必红
    # ⚖⚠⚖⚖ 这是 244.31 那条**可证恒绿**检查的翻版：
    #   `sorted(排列)` 对任意排列都等于 `range(n)` ⇒ 秩恒为 n−1
    #   ⇒ `k_base` 恒被夹到 n−1 ⇒ 配对覆盖率恒 ≈ 1 ⇒ 全表错，且看不出来。
    # ⚖⚠ 本工具里的**反证件**（perm == range(n) ⇒ HardFail）先把这条拦住，
    #   所以症状是**崩**而不是「静默错」⇒ 本变异抓的是「反证件在岗」。
    ("P7", "perm = np.random.default_rng(0).permutation(n).tolist()",
     "perm = sorted(np.random.default_rng(0).permutation(n).tolist())", "T1"),

    # P8 load_k_positions：不再核 seed 默认值 ⇒ T9 必红
    # ⚖⚠ 症状：仪器用 seed=1 而本工具按 seed=0 算位点 ⇒ **审计的是另一组位点**，
    #   而报告完全正常（244.26 记的同一类病）。⚗⇒ T9 的 `kb2 == rank2`
    #   依赖真实秩 140，seed 变了就不等 ⇒ 咬得住。
    ("P8", 'if sig.parameters["seed"].default != 0:', "if False:", "T11"),

    # P9 位点数自证被拆 ⇒ T3 必红
    # ⚖⚠ 症状：位点数与 k_base 不符时**继续算** ⇒ 覆盖率的分母换了口径，
    #   而报告看不出任何异常。
    ("P9", "if len(S) != k_base:", "if False:", "T10"),

    # P10 **K6**：判定恒返回 True ⇒ T12 必红（过期常量不再拒读）
    # ⚖⚠⚖⚖ 这是 244.34.1 的守卫：抄来的 `LADDER_DCOV` 会**静默过期**，
    #   而过期会让「小 N 倍」这句结论**无声地**失真，报告看上去完全正常。
    # ⚖⚠ 症状：现场算出 0.24982、抄来的是 0.08（明显过期），
    #   工具却照样通过 ⇒ 一条基于过期前提的结论被放行。
    ("P10", "return abs(declared - computed) / computed <= tol", "return True", "T12"),

    # P10b K6 反向：恒返回 False ⇒ T12 必红（一切都被判过期）
    ("P10b", "return abs(declared - computed) / computed <= tol", "return False", "T12"),

    # P11 K6：容差放到 10 倍（等于没有核对）⇒ T12 必红
    # ⚖⚠⚠ 症状：任何抄来的值都算「一致」⇒ K6 变成一句废话。
    ("P11", "def k6_fresh(computed, declared, tol=0.05):",
     "def k6_fresh(computed, declared, tol=5.0):", "T12"),

    # P12 `run()`：把**现场算的值**换回抄来的常量 ⇒ T12 必红
    # ⚖⚠⚖⚖ 症状与 P10 同类，但更隐蔽：代码看着在核对，
    #   实际比的是「常量 vs 常量」⇒ 现场计算成了**死代码**。
    #   ⚗⇒ 判据必须钉住「比的是现场值」这件事本身 ⇒ 由**端到端**的 T13 承重
    #   （喂一份故意过期的核对值，要求报告判它过期）。
    ("P12", "measured = ladder_step_dcov(w_log, probe_path)",
     "measured = ladder_dcov", "T13"),
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
        print("台架自身自检 rc=%d" % rc)
        return 0 if rc == 0 else 1

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
                  "真因通常不在判据，而在**用例没覆盖那个维度**）"
                  % (name, ln, needle, expect))
            allok = False
        else:
            print("[PASS] %s 第 %d 行变异 %r ⇒ %s 转红"
                  % (name, ln, needle, expect))

    n = len(MUTATIONS)
    print("变异终检：%d/%d 全部被抓住" % (n, n) if allok else "变异终检：有变异存活")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
