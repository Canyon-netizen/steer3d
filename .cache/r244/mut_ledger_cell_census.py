#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_ledger_cell_census —— `ledger_cell_census.py` 的**变异台**（修订 244.57）

⚠⚠⚖ **本台架问什么**

  244.57 把**要展示给用户的 63 个格**逐格独立重算了一遍。
  ⚖⚠⚖⚖⚖⇒ 台架必须保证：这 6 条判据**每一条**都**抓得住**对应的实现写错。
  ⚖ 尤其 244.55 在**同一批格**上逮到一处抄错的整数 ⇒ 这类表**必须有独立重算**。

⚖⚠⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据 6/6 通过 **且** 自检 7/7 通过。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**、**真实路真的变了**。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）⇒
     「拆掉某条检查 / 放宽某个容差」类变异在**干净真实数据**上是看不见的，
     只有畸形夹具能抓到它（244.55 踩过，244.56 再确认）。

⚖⚠⚖⚖ **必须能红**的变异（6 条）
  M1  逐格比较的「数值一致」那一支被焊成恒真 ⇒ C1（自检路）
  M2  剂量轴 rho 的**比较容差**被放到无穷 ⇒ C2（自检路）
  M3  倍数列的**比较容差**被放到无穷 ⇒ C3（自检路）
  M4  k/n 那一支的「不一致」判定被焊成恒假 ⇒ C3（自检路）
  M5  「每一格都有独立重算」的缺格检查被焊成恒假 ⇒ C5（自检路）
  M6  五条未量到项少印一条 ⇒ C6（真实数据路）

跑法：
    python3 mut_ledger_cell_census.py
    python3 mut_ledger_cell_census.py --selftest
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
TARGET = os.path.join(HERE, "ledger_cell_census.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     "        elif _num_eq(got, led, tol):\n            continue",
     "        elif True:\n            continue",
     "C1", "逐格比较的「**数值一致**」那一支（焊成恒真）"),
    ("M2",
     '    bad2 = audit(cells, LEDGER_DOSE, {"剂量轴 w rho（注入比例）": 5e-4,',
     '    bad2 = audit(cells, LEDGER_DOSE, {"剂量轴 w rho（注入比例）": 5e9,',
     "C2", "剂量轴 rho 的**比较容差**那一支（放到无穷）"),
    ("M3",
     '                              ("倍数", LEDGER_RATIO.get(name), 0.05)):',
     '                              ("倍数", LEDGER_RATIO.get(name), 5e9)):',
     "C3", "倍数列的**比较容差**那一支（放到无穷）"),
    ("M4",
     "            elif suf == \"k/n\":\n                if got != exp:\n                    bad3.append((key, exp, got))",
     "            elif suf == \"k/n\":\n                if False:\n                    bad3.append((key, exp, got))",
     "C3", "k/n 那一支的「**不一致**」判定（焊成恒假）"),
    ("M5",
     "    missing = [n for n in have if n not in cells]",
     "    missing = []",
     "C5", "「每一格都有独立重算」的**缺格检查**（焊成恒假）"),
    ("M6",
     '    ("层内 rho 的重复性",\n'
     '     "rep_n=1 ⇒ 「rand 臂那个 12/14 是不是噪声」**仍未解释**（244.37）"),\n',
     "",
     "C6", "「未量到」五条里的**一条**（少印一条）"),
]


def _load(path, src=None):
    mod = types.ModuleType("lcc_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _L, _rc, R = mod.run()
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return R, None


def run_selftest_fails(mod):
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
            fails.add(line.split()[1])
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
        sf_cids = set(re.match(r"([A-Z]\d+)", x).group(1)
                      for x in sf if re.match(r"([A-Z]\d+)", x))
        by = []
        if want in red:
            by.append("真实数据路")
        if want in sf_cids:
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
