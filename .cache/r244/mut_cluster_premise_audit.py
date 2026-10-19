#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_cluster_premise_audit —— `cluster_premise_audit.py` 的**变异台**（修订 244.59）

⚠⚠⚖ **本台架问什么**

  244.59 验的是判决面板的**「前提是否独立」**——
  ⚖ 14 条轨迹 = 7 块 × 2 ⇒ 面板上**每一个 p 与每一个区间**都建立在
  「14 个独立单位」这个**从未验过**的前提上。
  ⇒ 台架必须保证：那 11 条判据**每一条**都**抓得住**对应的实现写错。

⚖⚠⚖⚖ **本轮最要紧的两个错**（台架要能抓住）：

  ① **块级口径的「多数」规则**（块内两条**都正**才算正）
     ⇒ 改错它 ⇒ 「显著性是否口径依赖」的结论会**整个翻转**
  ② **跨臂 Fisher 的功效**：⛔ **不许用正态近似** ⇒ 必须**精确枚举**
     ⇒ 判据 **C11**：用具名的「精确枚举」与「正态近似」两种方法对照，
       两者给出的「需要多少块」**必须不同** ⇒ 近似**不可替代**精确
     ⇒ 变异台专门盯这条（M10）

⚖⚠⚖⚖⚖ **本轮新抓到的第三个错（我自己写进账本前的）**：

  ③ **块级 p 值算错了对象**：我第一版把 **14 条轨迹符号**喂给了符号检验
     ⇒ 印出来的是**轨迹级的 p**（w 的 0.00183105 会被印在「块级 6/7」旁边）
     ⇒ 判据 **C13** 专门盯这条（M11）

⚖⚠⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）
  6. ⚖ 自检路的 id 用**完整 token**（`C4x` 与 `C4` 分得开）

⚖⚠⚖⚖ **必须能红**的变异（12 条）
  M1  块级「两条都正」改成「任意一条正」⇒ C7（真实数据路）
  M2  块内「一致」的判定反号（改成「不一致」）⇒ C3（真实数据路）
  M3  跨臂 Fisher 换成「双尾 ×2」（⛔ 精确 p 不用）⇒ C2（真实数据路）
  M4  「独立预期」公式漏掉 (1−pth)(1−pnt) ⇒ C3v（自检路，合成夹具）
  M5  跨臂 Fisher 的功效被换成占位（⛔ 精确枚举没了）⇒ C5x（自检路）
  M6  块级区间「更宽」的判定被焊成恒真 ⇒ C6z（自检路）
  M7  「一致率检验」的临界值判定放宽 ⇒ C4（真实数据路）
  M8  少印一条前提声明 ⇒ C9（真实数据路）
  M9  少印一条留白 ⇒ C10（真实数据路）
  M10 正态近似被换成「直接调精确枚举」⇒ 两种方法不再有别 ⇒ C11（真实数据路）
  M11 块级 p 被改成跑 **14 条轨迹符号**（= 我自己写进账本前的那版 bug）⇒ C13
  M12 文档「C12 回读区」里的一个数被改 ⇒ C12（真实数据路）

⚖⚠⚖⚖⚠ **台架当场抓到的三个「我以为它能红、其实红不了」**（记下来免得再犯）

  ⚖ **M2 的第一版是条死变异**：把「两条都正」改成「块内多数为正」——
     而块内**只有 2 格** ⇒ 「多数为正（平票算 False）」**恰好等价于**「两条都正」
     ⇒ 变异**完全没生效** ⇒ 台架报「存活」，实为**无效**。
     ⚖⚠⚠ **判别式**：块级是 2 格时，「多数」只有一种解释 ⇒ 改「多数」的写法是**死变异**。
  ⚖ **期望标签要按「实际能红的判据」指**，⛔ 不按自己以为的：
     第一版我把 M1 期望成 C5（「显著性是否口径依赖」），实测红的是 **C3/C6/C7**。
  ⚖ **判据本身太软 ⇒ 变异存活**：第一版的 C3 只印数、C6 断言的是一条
     **数学定理**（「一致 ⊇ 全正」⇒ 恒真 ⇒ 恒绿）⇒ 变异抓不到。
     ⇒ 修法：C3 改成**对手抄字面量**（244.57 的形状），
     C6 抽成**可注入**的函数 `block_is_wider` ⇒ 自检喂更窄的必须红。

跑法：
    python3 mut_cluster_premise_audit.py
    python3 mut_cluster_premise_audit.py --selftest
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
TARGET = os.path.join(HERE, "cluster_premise_audit.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     "    return all(signs[t] > 0 for t in blk)",
     "    return any(signs[t] > 0 for t in blk)",
     "C7", "块级「两条都正」被改成「任意一条正」"),
    ("M2",
     "        if len(blk) == BLOCK_SIZE and signs[blk[0]] == signs[blk[1]]:",
     "        if len(blk) == BLOCK_SIZE and signs[blk[0]] != signs[blk[1]]:",
     "C3", "块内「一致」的判定被反号（改成「不一致」）"),
    ("M3",
     "    ok2 = True\n"
     "    d2 = []\n"
     "    for stat in (\"traj\", \"prereg\"):\n"
     "        w = D[\"w\"][stat]\n"
     "        r = D[\"rand\"][stat]\n"
     "        p_tr, _ = AV.fisher_exact_two_sided(w[0], w[1] - w[0], r[0], r[1] - r[0])",
     "    ok2 = True\n"
     "    d2 = []\n"
     "    for stat in (\"traj\", \"prereg\"):\n"
     "        w = D[\"w\"][stat]\n"
     "        r = D[\"rand\"][stat]\n"
     "        p_tr = min(1.0, 2 * binom_sf(w[1] + r[1], max(w[0], r[0]), 0.5))",
     "C2", "跨臂 Fisher 的**精确 p**被换成「双尾 ×2 的二项近似」"),
    ("M4",
     "    return pth * pnt + (1.0 - pth) * (1.0 - pnt)",
     "    return pth * pnt",
     "C3v", "「独立预期」漏掉了 (1−pth)(1−pnt) ⇒ 公式写错"),
    ("M5",
     "    pw = 0.0\n    for a in range(n + 1):",
     "    pw = 0.0\n    for a in range(0):",
     "C5x", "跨臂 Fisher 的**精确枚举功效**被换成占位"),
    ("M6",
     "    return w_block > w_traj",
     "    return True",
     "C6z", "块级区间「更宽」的判定被焊成恒真"),
    ("M7",
     "        if binom_sf(n, k, 0.5) <= alpha:\n            crit = k\n            break\n"
     "    if crit is None:\n        return 0.0, None\n"
     "    return 1.0 - binom_cdf(n, crit - 1, q_true), crit",
     "        if binom_sf(n, k, 0.5) <= 1.0:\n            crit = k\n            break\n"
     "    if crit is None:\n        return 0.0, None\n"
     "    return 1.0 - binom_cdf(n, crit - 1, q_true), crit",
     "C4", "「一致率检验」的临界值判定被放宽到 1.0 ⇒ 功效虚高"),
    ("M8",
     "PREAMBLE = (\n"
     '    "⚖⚠⚠⚠ 面板上的**每一个 p 与每一个区间**都建立在「**14 条轨迹是 14 个独立单位**」"\n'
     '    "这个前提上；⚖⚠⚠ **该前提在现有 7 个块上【未量到】**（检验功效只有 0.34）",\n'
     '    "⚖⇒ ⛔ 「显著」是**口径依赖**的：轨迹级 n=14 显著，块级 n=7 **不显著** ⇒ "\n'
     '    "引用时**必须**写清用的是哪个口径",\n'
     '    "⚖⇒ ✅ 「**差 ≠ 0**」在**两个口径下都成立**（Newcombe 都不含 0）⇒ **方向不变**",\n'
     ")",
     "PREAMBLE = (\n"
     '    "⚖⚠⚠⚠ 面板上的**每一个 p 与每一个区间**都建立在「**14 条轨迹是 14 个独立单位**」"\n'
     '    "这个前提上；⚖⚠⚠ **该前提在现有 7 个块上【未量到】**（检验功效只有 0.34）",\n'
     '    "⚖⇒ ⛔ 「显著」是**口径依赖**的：轨迹级 n=14 显著，块级 n=7 **不显著** ⇒ "\n'
     '    "引用时**必须**写清用的是哪个口径",\n'
     ")",
     "C9", "前提声明里**一条**（少印一条）"),
    ("M9",
     '    ("层内 rho 的重复性",\n'
     '     "rep_n=1 ⇒ 「rand 臂那个 12/14 是不是噪声」仍未解释（244.37 登记至今）"),\n',
     "",
     "C10", "「未量到」六条里的**一条**（少印一条）"),
    ("M10",
     "    return pwn, len(rej)",
     "    return fisher_power(n, p_w, p_r, alpha)[0], len(rej)",
     "C11", "正态近似被换成「直接调精确枚举」⇒ 两种方法不再有别"),
    ("M11",
     "    return reader().sign_test(block_signs(blocks, signs))[0]",
     "    return reader().sign_test([1.0 if s > 0 else -1.0 for s in signs.values()])[0]",
     "C13", "块级 p 被改成跑 14 条轨迹符号（= 我自己写进账本前的那版 bug）"),
    ("M12",
     "  · key=traj       | w 13/1 p=0.00183105 | rand 5/9 p=0.42395 | fisher=0.0044241",
     "  · key=traj       | w 13/1 p=0.00183106 | rand 5/9 p=0.42395 | fisher=0.0044241",
     "C12", "文档「C12 回读区」里的一个数被改（文档漂移）"),
]


def _load(path, src=None):
    mod = types.ModuleType("cpa_mut")
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
            D = mod.derive_all()
            _L, R = mod.build_report(D)
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
