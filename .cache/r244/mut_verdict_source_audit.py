#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_verdict_source_audit —— `verdict_source_audit.py` 自检的**变异台**（修订 244.55）

⚠⚠⚖ **本台架问什么**

  244.55 的判决数来源链有 **11 条判据**（C1–C11）。
  ⚖⚠⚖⚖⚖⇒ 台架必须能保证：这 11 条**每一条**都**抓得住**对应的实现写错。
  ⚖ 尤其：244.55 实测发现 `headroom_audit.py` 的自检 C8 与被检的 `VERDICTS`
  **同源** ⇒ 那道守卫**原理上抓不到抄错** ⇒ **本台架是那道缺口的替代品**。

⚖⚠⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码跑真实数据 ⇒ 11/11 通过。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：
     · 落点串**确实被替换**（否则报「无效变异」）
     · **真实路真的变了**（红了的判据集合与基线不同）
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`__crash__`），⛔ 不算抓到。
  5. 报「仍 PASS」必须区分：
     · 判据读的不是被测物 / 用例没覆盖那个维度 / 变异无效（真实路未变）
     ⇒ 这三种**分别**报出来，⛔ 不许笼统说「没抓到」。

⚖⚠⚖⚖ **期望标签必须指向「我要改的那支，在这个夹具上走得到吗」**
  （已栽 7 次的坑，见账本 244.43/244.52）⇒ 每条变异都写明**它踩的是哪一支**。

⚖⚠⚠⚖ **必须能红**的变异（12 条）
  M1  预登记的平局口径 `nT > nF` → `nT >= nF`（平局算 True）⇒ C1
  M2  k_hi 过滤器 `2*k <= n_eff` → `k <= n_eff`（取错档）⇒ C2
  M3  问题分组键（剥 `__think`/`__no_think`）被拆 ⇒ C3
  M4  跨臂 Fisher 的表构造**行列错位** ⇒ C4
  M5  「两条口径不同向」的集合算反（`!=` → `==`）⇒ C5
  M6  C6 的「例外格必须全是零跨度格」被焊成恒真 ⇒ C6
  M7  内容指纹**不再排除 `arm`** ⇒ C7
  M8  判决清单对账的「不一致」判定被焊成恒假 ⇒ C8
  M9  「轨迹级 rand」那一行的**更正被撤掉** ⇒ C9
  M10 `want8` 只取前 5 行 ⇒ C10
  M11 三条未量到项**少印一条** ⇒ C11
  M12 预登记的负号票数 `nF` 被算成 0 ⇒ C1

跑法：
    python3 mut_verdict_source_audit.py
    python3 mut_verdict_source_audit.py --selftest
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
TARGET = os.path.join(HERE, "verdict_source_audit.py")

# ⚖ (编号, 落点旧串, 落点新串, 期望红的那条判据, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     '"verdict": nT > nF, "tie": nT == nF}',
     '"verdict": nT >= nF, "tie": nT == nF}',
     "C1", "预登记口径的**平局那一支**（`nT > nF` ⇒ `nT >= nF`）"),
    ("M2",
     "if n_eff is not None and 2 * int(c[\"inject_n_sites\"]) <= n_eff]",
     "if n_eff is not None and int(c[\"inject_n_sites\"]) <= n_eff]",
     "C2", "k_hi 的**覆盖率过滤那一支**（`2*k <= n_eff` ⇒ `k <= n_eff`）"),
    ("M3",
     'return re.sub(r"__(?:no_)?think$", "", tid) or tid',
     'return tid',
     "C3", "问题级**分组键**（剥后缀那一支）"),
    ("M4",
     "    fw = fisher(dw[\"traj\"][0], dw[\"traj\"][1] - dw[\"traj\"][0],\n"
     "                dr[\"traj\"][0], dr[\"traj\"][1] - dr[\"traj\"][0])",
     "    fw = fisher(dw[\"traj\"][0], dw[\"traj\"][1],\n"
     "                dr[\"traj\"][0], dr[\"traj\"][1])",
     "C4", "跨臂 Fisher 的**表构造**（负号数被写成**总数**）"),
    ("M5",
     "if pw[t][\"verdict\"] != (dw[\"traj_signs\"][dw[\"tids\"].index(t)] > 0)]",
     "if pw[t][\"verdict\"] == (dw[\"traj_signs\"][dw[\"tids\"].index(t)] > 0)]",
     "C5", "「两条口径**不同向**的集合」那一支"),
    ("M6",
     "    ok6 = (len(diff_notzero) == 0)",
     "    ok6 = True",
     "C6", "「例外格必须**全是零跨度格**」那一支（焊成恒真）"),
    ("M7",
     'd = {k: v for k, v in r.items() if k != "arm"}',
     'd = dict(r)',
     "C7", "内容指纹**排除 `arm` 字段**那一支"),
    ("M8",
     "            if (k, n) != (gk, gn):\n"
     "                mism.append((name, (k, n), (gk, gn)))",
     "            if False:\n"
     "                mism.append((name, (k, n), (gk, gn)))",
     "C8", "判决清单对账的「**不一致**」那一支（焊成恒假）"),
    ("M9",
     'CORRECTIONS = {"轨迹级 rand": (5, 14)}',
     'CORRECTIONS = {"轨迹级 rand": (5, 9)}',
     "C9", "「轨迹级 rand」那一行的**更正**（被撤掉）"),
    ("M10",
     "                        out.append((el.elts[0].value, el.elts[1].value,\n"
     "                                    el.elts[2].value))\n"
     "                    return out",
     "                        out.append((el.elts[0].value, el.elts[1].value,\n"
     "                                    el.elts[2].value))\n"
     "                    return out[:5]",
     "C10", "`want8` 的**行数**（只取前 5 行）"),
    ("M11",
     '    ("哪一条臂是机制效应",\n'
     '     "w 臂的 12/14 与 rand 臂的 6/14 **都**是跨剂量的多数（244.48/244.50）⇒ 机制未分离"),\n',
     "",
     "C11", "「未量到」三条里的**一条**（少印一条）"),
    ("M12",
     'nF = sum(1 for c in cs if c.get("up_mono_meas") is False)',
     'nF = 0',
     "C1", "预登记口径的**负号票数**那一支"),
]


def _load(path, src=None):
    mod = types.ModuleType("vsa_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod):
    """⚖ 跑**真实数据**上的审计。返回 (R, err)：
    R = {判据: bool}；err = 崩了的异常文本（None = 没崩）"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _L, _rc, R = mod.run()
    except Exception as e:  # ⚠ 崩了单列，⛔ 不算「抓到」
        return None, "%s: %s" % (type(e).__name__, e)
    return R, None


def run_selftest_fails(mod):
    """⚖ 跑**自检**（含畸形夹具）。返回 (失败判据集合, 崩了文本)"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = mod.selftest()
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

    # ---- 基线必须绿（真实数据 + 自检，两条都要绿）-------------------
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
        # ⚖⚠⚠ **两条路都要查**：
        #   ① 真实数据路：期望那条判据是否转红
        #   ② **自检路**（含畸形夹具）：「拆掉某条检查」这类变异
        #      ⛔ 在**干净真实数据**上是看不见的 ⇒ 只有畸形夹具能抓到它
        R, err = run_audit(mod)
        sf, serr = run_selftest_fails(mod)
        if err or serr:
            crashed.append((mid, err or serr))
            print("[CRASH] %s 崩了：%s（⚠ 崩 ≠ 抓到）" % (mid, err or serr))
            continue
        red = set(c for c, v in R.items() if not v)
        # ⚖ 自检里的失败 id 形如 `C6x` ⇒ 去掉尾部的 `x` 即是它守的那条判据
        # ⚖ 自检里的失败 id 形如 `C1x` ⇒ 取**判据号前缀**
        #   （⛔ 不用 rstrip("x")：那种写法对 `C3y` **不成立** ⇒ 244.56 踩过）
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
