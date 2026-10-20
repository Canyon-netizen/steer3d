#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_dose_fragility_audit —— `dose_fragility_audit.py` 的**变异台**（修订 244.62）

⚠⚠⚖ **本台架问什么**

  244.62 问的是：**剂量轴的脆性会不会动摇 244.60 的「剂量—响应只出现在 w 臂」**
  ⇒ 实测：**会**（5 个场景里翻了 1 个，且 rand 臂的 p 在 2 个场景里**带跨过 α**）
  ⇒ 台架必须保证：244.62 的那 12 条判据**每一条**都**抓得住**对应的实现写错。

⚖⚠⚖⚖ **本轮最要紧的三个错**（台架要能抓住）：

  ① **扰动没真的改 P**（`shift_records` 写成恒等）⇒ 四个场景全等于基准
     ⇒ 「脆性」变成**空转**⇒ C2 必须红（否则 C2 是恒绿护栏）。
  ② **判决被写死成恒真** ⇒ 打印的 p（0.0488）与「成立」自相矛盾 ⇒ C4 必须红。
  ③ **扰动幅度改小**（4 → 3）⇒ 分档表与 rho 不再复现 244.51 ⇒ C12 必须红。

⚖⚠⚖⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实数据全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到；
     **切坏语法的变异判「无效」**，⛔ 也不许算抓到。
  5. **两条路都查**（真实数据路 + 自检的畸形夹具路）

⚖⚠⚖⚖⚖⚖ **必须能红**的变异（12 条）

  M1  扰动没真的改 P（`shift_records` 写成恒等）⇒ C2
  M2  少算一个扰动场景 ⇒ C1
  M3  rand 臂用了 w 臂的格 ⇒ C0
  M4  判决被写死成恒真 ⇒ C4
  M5  预登记的 α 被改小 ⇒ C0
  M6  层内基准被换成 0.5 ⇒ C3
  M7  「**翻转**」这个**标记**被改掉 ⇒ C5
  M8  「MC95%带」这个**标记**被改掉 ⇒ C10
  M9  「剂量轴口径多数」这个**标记**被改掉 ⇒ C8
  M10 p_exact 被写死成 0 ⇒ C9
  M11 扰动幅度 4 → 3 ⇒ C12
  M12 少印一个场景 ⇒ C4

跑法：
    python3 mut_dose_fragility_audit.py
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
TARGET = os.path.join(HERE, "dose_fragility_audit.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     "    return [dict(r, P=p) for r, p in zip(recs, Ps)]",
     "    return [dict(r, P=r[\"P\"]) for r, p in zip(recs, Ps)]",
     "C2", "扰动没真的改 `P` ⇒ 四个场景全等于基准 ⇒ 脆性空转"),
    ("M2",
     "    for i, (lab, Ps_w) in enumerate(variants_w):",
     "    for i, (lab, Ps_w) in enumerate(variants_w[:3]):",
     "C1", "少算一个扰动场景（4 ⇒ 3）"),
    ("M3",
     "    for arm in ARMS:\n        shifted = shifted_by_arm[arm]",
     "    for arm in ARMS:\n        shifted = shifted_by_arm[\"w\"]",
     "C0", "rand 臂用了 w 臂的格 ⇒ 各层计数与基准不符"),
    ("M4",
     "    return (pw < ALPHA) and (pr >= ALPHA)",
     "    return True",
     "C4", "判决被写死成恒真（打印的 p=0.0488 与「成立」自相矛盾）"),
    ("M5",
     "ALPHA = 0.05\n# ⚖ **预登记的 α**",
     "ALPHA = 0.01\n# ⚖ **预登记的 α**",
     "C0", "预登记的 α 被改小（0.05 → 0.01）"),
    ("M6",
     '            bases = [DL.majority_base_p(nz) for nz in row["nzs"]]',
     '            bases = [0.5 for nz in row["nzs"]]',
     "C3", "层内基准被换成 0.5（⛔ 244.60 的核心陷阱）"),
    ("M7",
     '"  ⚠⚠ **翻转**" if sc["flip"] else ""',
     '"  ⚠⚠ ✗✗" if sc["flip"] else ""',
     "C5", "「**翻转**」这个**标记**被改掉 ⇒ 「必须印出」型判据红"),
    ("M8",
     "MC95%%带 [%.4f, %.4f]%s",
     "MCband [%.4f, %.4f]%s",
     "C10", "「MC95%带」这个**标记**被改掉 ⇒ 不确定带没被印出"),
    ("M9",
     '" ｜ 剂量轴口径多数 %d/%d"',
     '" ｜ 轴口径多数 %d/%d"',
     "C8", "「剂量轴口径多数」这个**标记**被改掉"),
    ("M10",
     'p_exact = RD.sign_test([float(d) for d in nz])[0] if nz else None',
     'p_exact = 0.0 if nz else None',
     "C9", "配对置换 p 的对照（精确符号检验）被写死成 0"),
    ("M11",
     "OFF = 4\n",
     "OFF = 3\n",
     "C11", "扰动幅度 4 → 3 ⇒ 不再复现 244.51 的分档表与 rho"),
    ("M12",
     '    for sc in allr["scenarios"]:\n        RP.append("· 场景 %s" % sc["label"])',
     '    for sc in allr["scenarios"][:4]:\n        RP.append("· 场景 %s" % sc["label"])',
     "C4", "少印一个场景 ⇒ 判决行数对不上"),
]


def _load(path, src=None):
    mod = types.ModuleType("dfa_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod):
    """⚖ 真实数据路：返回 {判据号: 是否通过}。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _RP, res, _allr = mod.run()
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return {c: o for c, o, _d in res}, None


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
    # ⚖⚠⚖⚖⚖ **期望标签必须存在**（244.62 自己踩过）：
    #   我把判据 **C12 改名成 C11** 之后，期望标签还写着 "C12"
    #   ⇒ 那个期望**指向了不存在的判据** ⇒ 变异明明让 C11 红了，台架却报「存活」
    #   ⇒ **回归抓住的**（全回归里它是红的）⇒ 现在加一条守卫：
    #   **期望标签不在基线的判据集合里 ⇒ 判「无效」**（⛔ 不许报「存活」）
    known = set(R0.keys())
    for mid, old, new, want, why in MUTATIONS:
        if want not in known:
            invalid.append((mid, "期望标签 %s 不在基线判据集合里（%s）⇒ 标签过期"
                            % (want, ",".join(sorted(known)))))
            print("[SKIP] %s 期望标签 %s **不存在** ⇒ 期望**过期**（⛔ 不许报存活）"
                  % (mid, want))
            continue
        if src.count(old) != 1:
            invalid.append((mid, "落点串命中 %d 处（必须恰好 1 处）" % src.count(old)))
            print("[SKIP] %s 落点串命中 %d 处 ⇒ 变异**无效**（%s）"
                  % (mid, src.count(old), why))
            continue
        msrc = src.replace(old, new, 1)
        # ⚖⚠⚖⚠ **变异必须先证明自己有效**：切完后源码**还要能解析**
        #   （切坏语法 ⇒ 模块加载即崩 ⇒ 这不是「抓到」，是变异**无效**）
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
