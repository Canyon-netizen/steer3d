#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_interval_audit —— `interval_audit.py` 的**变异台**（修订 244.58）

⚠⚠⚖ **本台架问什么**

  244.58 给判决面板的 6 个比例**补上了统计置信区间**（CP95 + Wilson95 + Newcombe 差区间）。
  ⚖⚠⚖⚖⚖⇒ 台架必须保证：那 11 条判据**每一条**都**抓得住**对应的实现写错。

⚖⚠⚖⚖ **本轮最要紧的一个错**：`cp_bounds` 解的是「**每端 α**」（覆盖率 1−2α），
  要 95% 必须传 **α/2** ⇒ 传错 ⇒ 区间变宽 1 个档 ⇒ **C1（定义式）** 与
  **C4（覆盖率）** 都必须红。⇒ 这是 M1。

⚖⚠⚖⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）⇒
     「把检查焊成恒真 / 放宽阈值」这类变异在**干净真实数据**上是看不见的，
     只有畸形夹具能抓到它（244.55 踩过，244.56/244.57 再确认）。
  6. ⚖ 自检路的 id 用**完整 token**（`C4x` 与 `C4` 分得开）
     ⇒ 244.56 的教训：`rstrip("x")` 对 `C3y` 不成立 ⇒ 一律用正则取。

⚖⚠⚖⚖ **必须能红**的变异（10 条）
  M1  CP 用 α 而不是 α/2 ⇒ C1（真实数据路 + 自检路）
  M2  Wilson 的 z 默认值改成 90% 的 1.645 ⇒ C1（真实数据路）
  M3  Wilson 上下界写反 ⇒ C1（真实数据路）
  M4  Newcombe 差区间换成「两 CI 相减」⇒ C6（真实数据路）
  M5  C4 的覆盖率阈值放宽到 0.90 ⇒ C4x（自检路）
  M6  少印一条「未量到」⇒ C9（真实数据路）
  M7  少印一条前置声明 ⇒ C7（真实数据路）
  M8  z95 常量写错（1.95996… → 1.96）⇒ C0（真实数据路）
  M9  把「Wilson ⊆ CP」的判定焊成恒真 ⇒ C3x（自检路）
  M10 把「定义式」的判定焊成恒真 ⇒ C1x（自检路）

跑法：
    python3 mut_interval_audit.py
    python3 mut_interval_audit.py --selftest
退出码：0 = 全部被抓住；1 = 有变异存活 / 基线不绿。
"""

import argparse
import contextlib
import io
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "interval_audit.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     "    return flip().cp_bounds(x, n, alpha / 2.0)",
     "    return flip().cp_bounds(x, n, alpha)",
     "C1", "CP 用了 **α** 而不是 **α/2**（⇒ 那是 90% 区间，不是 95%）"),
    ("M2",
     "def wilson_bounds(x, n, z=Z95):",
     "def wilson_bounds(x, n, z=1.645):",
     "C1", "Wilson 的 z 默认值换成 90% 的 1.645"),
    ("M3",
     "    return (max(0.0, c - h), min(1.0, c + h))",
     "    return (min(1.0, c + h), max(0.0, c - h))",
     "C1", "Wilson 上下界写反"),
    ("M4",
     "    return (max(-1.0, lo), min(1.0, hi))",
     "    return (l1 - u2, u1 - l2)",
     "C6", "Newcombe 差区间被换成「两 CI 相减」"),
    ("M5",
     "COV_CP_FLOOR = 0.95      #",
     "COV_CP_FLOOR = 0.90      #",
     "C4x", "C4 的覆盖率阈值被放宽到 0.90"),
    ("M6",
     '    ("层内 rho 的重复性",\n'
     '     "rep_n=1 ⇒ rand 臂那个 12/14 是不是噪声仍未解释（244.37 登记至今）"),\n',
     "",
     "C9", "「未量到」六条里的**一条**（少印一条）"),
    ("M7",
     'PREAMBLE = (\n'
     '    "⚖⚠⚠⚠ **这些区间是「计数口径」的边际**（244.48/244.50：两臂的多数都是**跨剂量**的多数）",\n'
     '    "⚖⇒ ⛔ **不代表**「固定剂量下改判了多少题」的区间 ⇒ 那一格仍写「**未量到**」",\n'
     '    "⚖⇒ ⛔ 本节**没有**回答「12/14 是不是噪声」（244.47 已证计数口径答不了）",\n'
     ')\n',
     'PREAMBLE = (\n'
     '    "⚖⚠⚠⚠ **这些区间是「计数口径」的边际**（244.48/244.50：两臂的多数都是**跨剂量**的多数）",\n'
     '    "⚖⇒ ⛔ **不代表**「固定剂量下改判了多少题」的区间 ⇒ 那一格仍写「**未量到**」",\n'
     ')\n',
     "C7", "前置声明里**一条**（少印一条）"),
    ("M8",
     "Z95 = 1.959963984540054",
     "Z95 = 1.96",
     "C0", "z95 常量写错（Φ(1.96) ≠ 0.975）"),
    ("M9",
     "    ok = (wl[0] >= cp[0] - 1e-12 and wl[1] <= cp[1] + 1e-12)",
     "    ok = True",
     "C3x", "「Wilson ⊆ CP」的判定被焊成恒真"),
    ("M10",
     "    ok = ok and okw and wl[0] <= wl[1]",
     "    ok = True",
     "C1x", "「端点满足定义式」的判定被焊成恒真"),
]


def _load(path, src=None):
    mod = types.ModuleType("ia_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod):
    """⚖ 真实数据路：跑 `run(verify=False)`，返回 (判据表, 错误)"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _L, R = mod.run(verify=False)
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return R, None


def run_selftest_fails(mod):
    """⚖ 自检路：跑 `selftest()`，返回 (失败的完整 token 集合, 错误)"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.selftest()
    except Exception as e:
        return set(), "%s: %s" % (type(e).__name__, e)
    txt = buf.getvalue()
    fails = set()
    for line in txt.split("\n"):
        if line.startswith("[FAIL]"):
            m = re.match(r"\[FAIL\]\s+(\S+)", line)
            if m:
                fails.add(m.group(1))
    return fails, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    src = io.open(args.target, encoding="utf-8").read()

    base = _load(args.target, src)
    R0, err0 = run_audit(base)
    if err0:
        print("⛔ 基线崩了：%s" % err0)
        return 1
    red0 = set(c for c, v in R0.items() if not v)
    sf0, serr0 = run_selftest_fails(base)
    print("基线（真实数据）：%d/%d 通过%s"
          % (sum(1 for v in R0.values() if v), len(R0),
             ("（红：%s）" % ",".join(sorted(red0))) if red0 else ""))
    print("基线（自检）：失败集合 %s" % (",".join(sorted(sf0)) or "空"))
    if red0 or sf0 or serr0:
        print("⛔ 基线不绿 ⇒ 先修基线，台架不许跑（%s%s）"
              % (err0 or "", ",".join(sorted(sf0))))
        return 1

    caught, survived, invalid, crashed = [], [], [], []
    for mid, old, new, want, why in MUTATIONS:
        if src.count(old) != 1:
            invalid.append((mid, "落点串命中 %d 处（必须恰好 1 处）" % src.count(old)))
            print("[SKIP] %s 落点串命中 %d 处 ⇒ 变异**无效**（%s）"
                  % (mid, src.count(old), why))
            continue
        msrc = src.replace(old, new, 1)
        mod = _load(args.target, msrc)
        R, err = run_audit(mod)
        sf, serr = run_selftest_fails(mod)
        if err or serr:
            crashed.append((mid, err or serr))
            print("[CRASH] %s 崩了：%s（⚠ 崩 ≠ 抓到）" % (mid, err or serr))
            continue
        red = set(c for c, v in R.items() if not v)
        by = []
        if want in red:
            by.append("真实数据路")
        if want in sf:
            by.append("自检路（畸形夹具）")
        if not by:
            survived.append((mid, want, "真实路红=%s；自检失败=%s"
                             % (",".join(sorted(red)) or "无",
                                ",".join(sorted(sf)) or "无")))
            print("[SURVIVED] %s 期望 %s 红，实际 真实路=%s 自检=%s ⇒ **变异存活**"
                  % (mid, want, ",".join(sorted(red)) or "无",
                     ",".join(sorted(sf)) or "无"))
            continue
        if not red and not sf:
            invalid.append((mid, "真实路与自检都没变 ⇒ 变异**无效**"))
            print("[SKIP] %s 真实路与自检均未变化 ⇒ 变异**无效**" % mid)
            continue
        caught.append(mid)
        print("[CAUGHT] %s ⇒ %s 红（%s；经 %s）"
              % (mid, want, why, "、".join(by)))

    print("")
    print("变异台：抓住 %d / %d" % (len(caught), len(MUTATIONS)))
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived),
                                "；".join("%s（期望 %s）" % (m, w) for m, w, _ in survived)))
    if invalid:
        print("⚠ 无效变异 %d 条：%s" % (len(invalid),
                                   "；".join("%s（%s）" % (m, why) for m, why in invalid)))
    if crashed:
        print("⚠ 崩了 %d 条：%s" % (len(crashed),
                                "；".join("%s（%s）" % (m, e) for m, e in crashed)))
    if survived:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
