#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_dose_layer_audit —— `dose_layer_audit.py` 的**变异台**（修订 244.60）

⚠⚠⚖ **本台架问什么**

  244.60 把面板上的多数**按剂量层拆开**，并钉住一个陷阱：
  **层内的零假设基准不是 0.5**（平票算 False + 每层每轨迹只有 1–3 格
  ⇒ 2 格的层基准塌到 **0.25**）⇒ 沿用 0.5 基准会把结论**说反**。

  ⇒ 台架必须保证：那 10 条判据**每一条**都**抓得住**对应的实现写错。

⚖⚠⚖⚖ **本轮最要紧的三个错**（台架要能抓住）：

  ① **层内基准算错**（把 0.25 当 0.5）⇒ 显著性结论翻转
  ② **平票规则写反**（`nT > nF` 写成 `>=`）⇒ 与生产机械不一致
  ③ **块级 p / 置换 p 算错对象**（244.59 的同族坑）⇒ 印出别的层的数

⚖⚠⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）
  6. ⚖ 自检路的 id 用**完整 token**（`C4x` 与 `C4` 分得开）

⚖⚠⚖⚖⚖ **必须能红**的变异（14 条）
  M1  层内基准公式（`nz//2+1` → `nz//2`）⇒ C0y（自检路）
  M2  平票规则（`nT > nF` → `>=`）⇒ C2（真实数据路）
  M3  PB 的 DP 两个分支互换 ⇒ C3（真实数据路）
  M4  配对置换**不换臂**（`else -d` → `else d`）⇒ C5（真实数据路）
  M5  MC 零假设改成「每格必正」⇒ C4z（自检路）
  M6  格级符号 `> 0` → `>= 0` ⇒ C2（真实数据路）
  M7  剂量轴字面量改一个数 ⇒ C0（真实数据路）
  M8  少印一条前提声明 ⇒ C8（真实数据路）
  M9  少印一条留白 ⇒ C9（真实数据路）
  M10 少印 rand 的剂量趋势行 ⇒ C5（真实数据路）
  M11 少印「不一致数」行 ⇒ C6（真实数据路）
  M12 「正态近似规模」这个标记被改掉 ⇒ C7（真实数据路）
  M13 少印「两条多数规则」的报告 ⇒ C2（真实数据路）
  M14 少印「**翻转**」这个**标记** ⇒ C4（真实数据路）

⚖⚠⚖⚖⚠ **台架当场抓到的「我以为它能红、其实红不了」**（记下来免得再犯）

  ⚖ **M1 的第一版期望写错了**：我以为改基准公式会让 C3 红（实测 C3 仍绿，
     因为 C3 抓的是「基准 ≠ 0.5」与「DP vs 枚举」两件事，都不受影响）
     ⇒ 实际红的是**自检的 C0y**（已知答案 nz=2 ⇒ 0.25）
     ⇒ ⚖ 判别式：**期望标签要按「实际能红的判据」指**，⛔ 不按自己以为的。

  ⚖⚠⚖⚠ **M5 的第一版期望也写错了（更狠）**：我以为「MC 零分布塌掉」会让 C4x 红
     （C4x 抓的是「单调 ⇒ p 小」）⇒ **实测 C4x 照样绿** ——
     因为零分布塌掉后 p 只会**更小**（0.0005），**更符合**「单调 ⇒ p 小」！
     ⇒ 根因：**C4x / C4y 都是单边的** ⇒ 任何让 p 变小的破坏它们都看不见
     ⇒ 修法：**补一条双边的「零分布校准」判据 C4z**
     （零假设夹具 t_obs=0 ⇒ p 必须≈0.5；实测 0.534，8 个 seed 落在 0.525–0.539）
     ⇒ ⚖ 判别式：**单边判据对「分布塌掉 / 分布反号」是瞎的**，
        零假设类判据必须**双向**校准。

  ⚖⚠⚖⚖⚠⚠ **M8 抓到的不是一个「期望写错」，是一个「恒绿护栏」**：
     M8 少印一条前提声明 ⇒ C8 **本该**红 ⇒ 实测**照样绿** ⇒ 查下去发现
     C8 的期望集是 `PREAMBLE_REQUIRED = tuple(PREAMBLE)` ——
     **从被检对象本身派生** ⇒ 删掉一条被检对象时**期望集同步变小**
     ⇒ 判据**永远绿** ⇒ 抓到任何变异都红不了。
     ⚖⚠⚠⚠ **判别式（通用）**：
       **「必须印出 N 条」型判据的期望集，绝不可从被检对象派生**
       ⇒ 要么写死**独立标签**（本轮改成 【P1】…【B7】），
       要么让判据检查**计数**而不是**内容成员资格**。
     C9 同病（`BLANKS_REQUIRED = tuple(x[0] for x in BLANKS)`）⇒ 一并改。
     ⇒ ⛔ 这正是用户明令要禁的形状：「恒绿护栏要么删、要么改成能红的形状」。

跑法：
    python3 mut_dose_layer_audit.py
    python3 mut_dose_layer_audit.py --selftest
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
TARGET = os.path.join(HERE, "dose_layer_audit.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     "    return sum(math.comb(nz, j) * 0.5 ** nz\n"
     "               for j in range(nz // 2 + 1, nz + 1))",
     "    return sum(math.comb(nz, j) * 0.5 ** nz\n"
     "               for j in range(nz // 2, nz + 1))",
     "C0y", "层内基准公式（2 格的基准被从 0.25 改成 0.75）"),
    ("M2",
     "                    \"m\": len(cs), \"verdict\": nT > nF}",
     "                    \"m\": len(cs), \"verdict\": nT >= nF}",
     "C2", "平票规则（`nT > nF` 改成 `>=` ⇒ 与生产机械不一致）"),
    ("M3",
     "            nd[i] += v * (1.0 - p)\n            nd[i + 1] += v * p",
     "            nd[i] += v * p\n            nd[i + 1] += v * (1.0 - p)",
     "C3", "Poisson-binomial 的 DP 两个分支互换"),
    ("M4",
     "            t += d if rng.random() < 0.5 else -d",
     "            t += d",
     "C5", "配对置换**不换臂**（统计量恒为观测值）"),
    ("M5",
     "    npos = sum(1 for _r in draws[:n_nz] if _r < 0.5)",
     "    npos = n_nz",
     "C4z", "MC 零假设改成「每格必正」⇒ 零分布塌掉 ⇒ 校准判据红"),
    ("M6",
     "    return dconf().d_of(r) > 0",
     "    return dconf().d_of(r) >= 0",
     "C2", "格级符号 `> 0` 改成 `>= 0`（零格被算成正）"),
    ("M7",
     "AXIS_QUANTILES = (0.015, 0.250, 0.750)",
     "AXIS_QUANTILES = (0.016, 0.250, 0.750)",
     "C0", "剂量轴的**字面量**被改（分位点 0.015 → 0.016）"),
    ("M8",
     '    "【P4】⚖⇒ ✅ 「**差 ≠ 0**」在**每一层**都要单独看（区间可能含 0 ⇒ 那层就**未量到**）",\n',
     "",
     "C8", "前提声明里**一条**（少印一条 ⇒ 独立标签【P4】消失）"),
    ("M9",
     '    ("【B3】**层内的重复性**",\n'
     '     "rep_n=1 ⇒ 层内读数 ~1σ ⇒ 「rand 臂层内少数为真是不是噪声」**仍未解释**"),\n',
     "",
     "C9", "「未量到」七条里的**一条**（少印一条 ⇒ 独立标签【B3】消失）"),
    ("M10",
     '    for arm in ("w", "rand"):\n        counts = []',
     '    for arm in ("w",):\n        counts = []',
     "C5", "只印 w 臂的剂量趋势（少印一条）"),
    ("M11",
     '        RP.append("    · " + d6[-1])\n',
     "",
     "C6", "「不一致数」那一行被删"),
    ("M12",
     '（差 %.1fpp）｜ 正态近似规模 %d/臂',
     '（差 %.1fpp）｜ 规模 %d/臂',
     "C7", "「正态近似规模」这个**标记**被改掉"),
    ("M13",
     '    RP.append("  ℹ ⚠⚠ **两条多数规则**在 rand 臂**不等**（244.60 新发现）：")\n',
     "",
     "C2", "「两条多数规则」的报告被删"),
    ("M14",
     '"  ⚠⚠ **翻转**" if flip else ""',
     '"  ⚠⚠ ✗✗" if flip else ""',
     "C4", "「**翻转**」这个**标记**被改掉 ⇒ 「必须印出」型判据红"),
    ("M15",
     "    return sum(math.comb(n_nz, j) * 0.5 ** n_nz\n"
     "               for j in range(n_nz + 1) if j * 2 > tot)",
     "    return majority_base_p(n_nz + n_zero)",
     "C10", "零假设基准**退回旧写法**（零格也当一次公平抛硬币）"),
    ("M16",
     "    npos = sum(1 for _r in draws[:n_nz] if _r < 0.5)\n"
     "    return npos * 2 > n_nz + n_zero",
     "    npos = sum(1 for _r in draws if _r < 0.5)\n"
     "    return npos * 2 > n_nz + n_zero",
     "C11", "零假设**模拟规则退回旧写法**（零格也抽公平硬币 ⇒ 零分布变宽）"),
    ("M17",
     "    w_off = (n_layer - 1) / 2.0",
     "    w_off = 0.0",
     "C12", "层间权重改成**不对称** ⇒ 「解析基准在比较中抵消」的恒等破掉"),
]




def _load(path, src=None):
    mod = types.ModuleType("dla_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod):
    """⚖ 真实数据路。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            A = mod.build_all()
            _RP, R, _rows, _trend = mod.build_report(A)
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return R, None


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
        # ⚖⚠⚖⚠ **变异必须先证明自己有效**：切完后源码**还要能解析**
        #   （切坏语法 ⇒ 模块加载即崩 ⇒ 这不是「抓到」，是变异**无效**）
        #   ⛔ 崩 ≠ 抓到：加载失败**不许**算进 caught。
        try:
            mod = _load(args.target, msrc)
        except SyntaxError as e:
            invalid.append((mid, "切完后语法错（%s）⇒ 变异**无效**" % e))
            print("[SKIP] %s 切完后语法错 ⇒ 变异**无效**（%s）" % (mid, e))
            continue
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
