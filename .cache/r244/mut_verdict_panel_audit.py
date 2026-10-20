#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_verdict_panel_audit —— `verdict_panel_audit.py` 的**变异台**（修订 244.61）

⚠⚠⚖ **本台架问什么**

  244.61 把「判决面板」做成**终版**（63 格 + 剂量轴 + 分层 + 区间 + 口径 + 边界清单），
  每格都带口径与前提 ⇒ 读者能一眼看出「显著」的前提。

  ⇒ 台架必须保证：那 11 条判据**每一条**都**抓得住**对应的实现写错。

⚖⚠⚖⚖ **本轮最要紧的四个错**（台架要能抓住）：

  ① **格集合被改了**（剂量轴的定义 ⇒ 面板的每一格都建在它上面）
  ② **分层数被改了**（244.60 的结论被悄悄改掉）
  ③ **口径没配上**（⇒ 读者看不出这个数是哪一条统计量）
  ④ **边界清单少一条 / 多一条**（⛔ 少印要红、多印也要红 ⇒ 双向）

⚖⚠⚖⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）
  6. ⚖ 自检路的 id 用**完整 token**（`C4x` 与 `C4` 分得开）

⚖⚠⚖⚖⚖ **必须能红**的变异（16 条）

  M1  剂量轴分位点字面量改一个数          ⇒ C1（真实数据路）
  M2  剂量轴格数字面量改一个数            ⇒ C1（真实数据路）
  M3  剂量轴四档字面量改一个数            ⇒ C1（真实数据路）
  M4  244.60 分层表的一格改掉             ⇒ C4（真实数据路）
  M5  244.60 剂量趋势的字面量改掉         ⇒ C4（真实数据路）
  M6  前提声明少印一条                    ⇒ C6（真实数据路）
  M7  边界清单的**期望集**少一条          ⇒ C7（真实数据路）⚠ 期望集被改 ⇒ 靠**双向**那一半抓
  M8  边界清单的**期望集**多一条          ⇒ C7（真实数据路）⚠ 靠**少印**那一半抓
  M9  口径匹配「轨迹级」被改坏            ⇒ C5（真实数据路）
  M10 口径匹配「剂量轴」被改坏            ⇒ C5（真实数据路）
  M11 少印一行格集合条件                  ⇒ C8（真实数据路）
  M12 C9 的块级行数阈值 2 → 3            ⇒ C9（真实数据路）
  M13 C10 的区间条数阈值 6 → 7            ⇒ C10（真实数据路）
  M14 C2 的集合比较 `==` → `!=`          ⇒ C2（真实数据路）
  M15 C5 的「未配口径」判据反写           ⇒ C5（真实数据路）
  M16 面板的一格被篡改                    ⇒ C0（真实数据路）

⚖⚠⚖⚖⚖⚖ **台架当场抓到的「我以为它能红、其实红不了」**（记下来免得再犯）

  ⚖⚠⚠⚠⚠ **变量遮蔽把 C8 变成「近乎恒绿护栏」**（自检先抓到的，⛔ 不是台架）：
     `j_c8_rules` 第一版写成
     `[r for r in RULE if not any(tag(i, r) in ln for i, r in enumerate(RULE, 1) for ln in lines)]`
     ⇒ 内层的 `r` **遮蔽**了外层的 `r` ⇒ 实际检查的是「三条里**任意一条**在不在」
     ⇒ **少印一条照样绿** ⇒ 修法：内层换变量名、逐条独立查。
     ⚖ 判别式：**同一个表达式里两层循环用同一个变量名 ⇒ 先查一遍再改**。
  ⚖⚠⚠ **「阈值类」判据的匹配串要够窄**（自检先抓到的）：
     C9 原本用 `"块级（" in ln` ⇒ **口径图例**那一行也被算进去 ⇒ 阈值只要
     1 行真块级 + 1 行图例就过 ⇒ **判据偏弱** ⇒ 改成 `"· 块级（"`（带项目符号）。

跑法：
    python3 mut_verdict_panel_audit.py
    python3 mut_verdict_panel_audit.py --selftest
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
TARGET = os.path.join(HERE, "verdict_panel_audit.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     "AXIS_QUANTILES = (0.015, 0.250, 0.750)",
     "AXIS_QUANTILES = (0.016, 0.250, 0.750)",
     "C1", "剂量轴分位点的**字面量**被改（0.015 → 0.016）"),
    ("M2",
     "DOSE_CELL_COUNT = 109",
     "DOSE_CELL_COUNT = 110",
     "C1", "剂量轴格数的**字面量**被改（109 → 110）"),
    ("M3",
     "AXIS_BAND_SIZE = (27, 28, 30, 24)",
     "AXIS_BAND_SIZE = (27, 28, 30, 25)",
     "C1", "剂量轴四档的**字面量**被改"),
    ("M4",
     "    (0, 4, 2, 0.6218, 0.407, 0.407, 0.3036),",
     "    (0, 5, 2, 0.6218, 0.407, 0.407, 0.3036),",
     "C4", "244.60 分层表的**一格**被改（层 0 的 w 条数 4 → 5）"),
    ("M5",
     'TREND_24460 = {"w": (15.875, 0.0002), "rand": (5.375, 0.0878)}',
     'TREND_24460 = {"w": (15.875, 0.0010), "rand": (5.375, 0.0878)}',
     "C4", "244.60 剂量趋势的**字面量**被改"),
    ("M6",
     '    ("【P4】⚖⚠⚠⚠ **生产里并存两条多数规则**（`majority_count` 零**进**分母 vs "\n'
     '     "`p9delta_per_tid` 零**不计**）⇒ rand 臂层 2 **5/14 vs 6/14** ⇒ 引用必须写清哪条"),\n',
     "",
     "C6", "前提声明里**一条**（少印一条 ⇒ 独立标签【P4】消失）"),
    ("M7",
     '    "前提是否独立",\n',
     "",
     "C7", "边界清单的**期望集**少一条 ⇒ 印出的那条变成「多印」⇒ **双向**那一半抓"),
    ("M8",
     '    "层间独立性",\n',
     '    "层间独立性",\n    "一条我瞎编的空白",\n',
     "C7", "边界清单的**期望集**多一条 ⇒ 我列的那条变成「少印」"),
    ("M9",
     '    if "轨迹级" in cell_name:',
     '    if "轨迹级X" in cell_name:',
     "C5", "口径匹配「轨迹级」被改坏 ⇒ 那几格落进 else ⇒ **未配口径**"),
    ("M10",
     '    if cell_name.startswith("剂量轴"):',
     '    if cell_name.startswith("剂量軸"):',
     "C5", "口径匹配「剂量轴」被改坏"),
    ("M11",
     '        RP.append("      〔格集合条件 %d〕%s" % (i, rule))',
     '        pass',
     "C8", "「格集合条件」那一行被删 ⇒ 少印一条 ⇒ C8 必须红"),
    ("M12",
     "            and n_block_rows >= 2)",
     "            and n_block_rows >= 3)",
     "C9", "C9 的块级行数阈值被放宽（2 → 3）⇒ 实际只有 2 行 ⇒ 必须红"),
    ("M13",
     "    return n_iv >= 6 and n_diff >= 3",
     "    return n_iv >= 7 and n_diff >= 3",
     "C10", "C10 的区间条数阈值被放宽（6 → 7）"),
    ("M14",
     "    return set(id(r) for r in impl_cells) == set(id(r) for r in rule_cells)",
     "    return set(id(r) for r in impl_cells) != set(id(r) for r in rule_cells)",
     "C2", "C2 的集合比较被反写（`==` → `!=`）"),
    ("M15",
     "    return [n for n in cells if caliber_of(n) is None]",
     "    return [n for n in cells if caliber_of(n) is not None]",
     "C5", "C5 的「未配口径」判据被反写"),
    ("M16",
     "    cells, extra = C.recompute()",
     '    cells, extra = C.recompute()\n    cells["预登记 w k/n"] = "13/14"',
     "C0", "面板的**一格**被篡改 ⇒ 244.57 的逐格对账必须红"),
]


def _load(path, src=None):
    mod = types.ModuleType("vpa_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod):
    """⚖ 真实数据路：返回 (红了的判据集合, 错误信息, 判据总条数)。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _RP, R, _B = mod.build()
    except Exception as e:
        return set(), "%s: %s" % (type(e).__name__, e), 0
    return set(c for c, v in R.items() if not v), None, len(R)


def run_selftest_fails(mod):
    """⚖ 自检路：返回失败的**完整 token** 集合。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.selftest()
    except Exception as e:
        return set(), "%s: %s" % (type(e).__name__, e)
    fails = set()
    for line in buf.getvalue().split("\n"):
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
    red0, err0, n0 = run_audit(base)
    if err0:
        print("⛔ 基线崩了：%s" % err0)
        return 1
    sf0, serr0 = run_selftest_fails(base)
    print("基线（真实数据）：%d 条判据，红的有 %s"
          % (n0, ",".join(sorted(red0)) or "无"))
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
        # ⚖⚠⚖⚠ **变异必须先证明自己有效**：切完后源码**还要能解析**
        try:
            mod = _load(args.target, msrc)
        except SyntaxError as e:
            invalid.append((mid, "切完后语法错（%s）⇒ 变异**无效**" % e))
            print("[SKIP] %s 切完后语法错 ⇒ 变异**无效**（%s）" % (mid, e))
            continue
        red, err, _n = run_audit(mod)
        sf, serr = run_selftest_fails(mod)
        if err or serr:
            crashed.append((mid, err or serr))
            print("[CRASH] %s 崩了：%s（⚠ 崩 ≠ 抓到）" % (mid, err or serr))
            continue
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
