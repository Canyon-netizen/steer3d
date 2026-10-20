#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_fixed_dose_preflight —— `fixed_dose_preflight.py` 的**变异台**（修订 244.68）

⚠⚠⚖ **本台架问什么**

  244.68 交的是**发批前预检器**：给它「计划中的那一批」的设计描述 ⇒ 它必须回答
  「**这一批能不能**回答目标里「①」那条（固定剂量下 w/rand 各改判多少题、
  差多少 pp、p 值与区间）」。
  它的价值全在**判据能红**：口径被写死、规模被低估、块级门槛被忽略、rand 臂的档
  被漏查、留白被删、「未量到」被说成零 ⇒ 必须**立刻红**。

  ⇒ 台架必须保证：那些判据（D1–D7 ＋ P1–P10）**每一条**都**抓得住**对应的写错。

⚖⚠⚖⚖⚖ **台架怎么跑（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真实设计路全绿 **且** 自检全绿。
  2. 每条变异**只改一处代码点**；⛔ 不改注释/散文。
  3. 每条变异**必须先证明自己有效**：落点串**确实被替换**（命中恰好 1 处）。
  4. **崩 ≠ 抓到**：被测代码抛异常单列（`[CRASH]`），⛔ 不算抓到。
  5. **两条路都查**（真实设计路 ＋ 自检路）。
  6. ⚖⚠⚖⚖ **顺序要紧**：先判「什么都没变」⇒ 那是**无效**变异（no-op），
     **不是**「存活」⇒ 否则会把等价变异记成「判据抓不住」（**冤枉判据**）。
  7. ⚖⚠ **「A 等于 B」型判据在「A、B 都写死」时是恒绿的**
     ⇒ 每条「写死型」变异都必须由**自检里的活体检查**抓住
     （M1–M4 改预登记/改期望比例 ⇒ 印出来的数必须变），
     ⛔ 不能只靠「A == B」那种比较。

⚖⚠⚖⚖⚖⚖ **必须能红**的变异（18 条）

  M1  D1 的 n_bands 口径比较被短路            ⇒ T7
  M2  D1 的 boundary 口径比较被短路          ⇒ T7b
  M3  块级门槛被写死 20（不再从预登记读）      ⇒ M2（活体）
  M4  逐档需求被写死 130                     ⇒ M4（活体）
  M5  m≥3 的门槛被写死 12                    ⇒ M3（活体）
  M6  rand 空档检查被放宽（0 也算数）          ⇒ T5
  M7  两臂配对检查被短路                     ⇒ T6
  M8  档数检查被短路                         ⇒ T8
  M9  块级比较被放宽（1 块也算够）            ⇒ T2
  M10 规模重算里的比例被写死（需求不再随设计变）⇒ P3
  M11 缺口清单少列一条                       ⇒ P6
  M12 留白段被删                             ⇒ P7
  M13 规模机械的 min_n 被改小（需求被低估）     ⇒ P9
  M14 重算时比例被偏移（印出的数与外部重算不符）⇒ P8
  M15 判决逻辑被短路（永远「能回答」）         ⇒ T2
  M16 【0】的「未量到」声明被删               ⇒ T1c
  M17 禁词表被清空（「未量到」可以说成零了）     ⇒ T10
  M18 P1 的「多出来的键」检查被短路           ⇒ T9c
  M19 CLI 只捕 `fda().HardFail` ⇒ 崩成 traceback ⇒ T9e

跑法：
    python3 mut_fixed_dose_preflight.py
    python3 mut_fixed_dose_preflight.py --selftest
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
TARGET = os.path.join(HERE, "fixed_dose_preflight.py")

# ⚖ 真实设计路用的**合格设计**（⛔ 与工具里的夹具同源 ⇒ 不引入第二套数字）
GOOD_DESIGN = {
    "design_id": "bench_good",
    "n_blocks": 24,
    "tracks_per_arm": 200,
    "cells_per_track": 12,
    "tracks_per_band": {"w": [200, 200, 200, 200],
                        "rand": [200, 200, 200, 200]},
    "expected_proportions": {
        "w": [4.0 / 14, 6.0 / 14, 10.0 / 14, 14.0 / 14],
        "rand": [2.0 / 14, 4.0 / 14, 5.0 / 14, 6.0 / 14]},
    "convention": {"n_bands": 4, "boundary": "prod", "quantile": "inclusive",
                   "zero_span": "keep"},
}

# ⚖ (编号, 落点旧串, 落点新串, 期望红的判据/自检 token, 它踩的是哪一支)
MUTATIONS = [
    ("M1",
     "            same = (want is not None and got is not None and int(want) == int(got))",
     "            same = True",
     "T7", "D1 的 n_bands 口径比较被**短路**（⇒ 口径不一致也绿）"),
    ("M2",
     "            same = (want is not None and got is not None and str(want) == str(got))",
     "            same = True",
     "T7b", "D1 的 boundary 口径比较被**短路**"),
    ("M3",
     "    need_blocks = max(cfg.blocks_needed_sign_test, cfg.blocks_needed_cluster,\n"
     "                      cfg.blocks_needed_fisher_exact)",
     "    need_blocks = 20",
     "M2", "块级门槛被**写死 20**（不再从预登记读 ⇒ 预登记改了也没人知道）"),
    ("M4",
     "        req = _req_of(sz[\"size\"].get(b))",
     "        req = 130",
     "M4", "逐档需求被**写死 130**（⛔ 那是档 0 的值 ⇒ 别的档全被低估）"),
    ("M5",
     "            need_cells = int(m.group(1))",
     "            need_cells = 12",
     "M3", "m≥3 的门槛被**写死 12**（不再从规模机械的输出读）"),
    ("M6",
     "        good = (have is not None and have > 0)",
     "        good = (have is not None)",
     "T5", "rand 空档检查被**放宽**（0 条也算「有档」）"),
    ("M7",
     "    same = (len(dw) == len(dr) and all(dw[i] == dr[i] for i in range(len(dw))))",
     "    same = True",
     "T6", "两臂配对检查被**短路**（⇒ 跨臂比较可能不成立也绿）"),
    ("M8",
     "    ok7 = (len(dw) == n_bands and len(dr) == n_bands\n"
     "           and len(ep.get(\"w\", [])) == n_bands and len(ep.get(\"rand\", [])) == n_bands)",
     "    ok7 = True",
     "T8", "档数与预登记一致的检查被**短路**"),
    ("M9",
     "    ok2 = n_blocks >= need_blocks",
     "    ok2 = n_blocks >= 1",
     "T2", "块级比较被**放宽**（1 块也算够）"),
    ("M10",
     "        rows.append({\"L\": b, \"pw\": pw, \"pr\": pr})",
     "        rows.append({\"L\": b, \"pw\": 0.5, \"pr\": 0.5})",
     "P3", "规模重算里的**比例被写死**（⇒ 需求不再随设计变 ⇒ 「重算」是假的）"),
    ("M11",
     "        gaps.append(\"块级规模不足：%d 块 < 门槛 %d 块（差 %d）\"\n"
     "                    % (n_blocks, need_blocks, need_blocks - n_blocks))",
     "        pass",
     "T2b", "缺口清单**少列一条**（⇒ 有一条缺口被藏起来）"),
    ("M12",
     "    RP.append(\"【6】⚖ 留白（**未量到** ⇒ ⛔ 不许说成「无差异」）\")\n",
     "",
     "P7", "**留白段被删**（⇒ 未量到的被悄悄说成了别的）"),
    ("M13",
     "    lines, size = dlayer().size_requirements(\n"
     "        rows, cpt, fisher_power=cpre().fisher_power, n_layer=n_bands)",
     "    lines, size = dlayer().size_requirements(\n"
     "        rows, cpt, fisher_power=cpre().fisher_power, n_layer=n_bands, min_n=1)",
     "P9", "规模机械的 `min_n` 被**改小**（⇒ 需求被低估 ⇒ 与 244.60 登记值对不上）"),
    ("M14",
     "        pw = float(design[\"expected_proportions\"][\"w\"][b])",
     "        pw = float(design[\"expected_proportions\"][\"w\"][b]) + 0.05",
     "P8", "重算时**比例被偏移**（⇒ 印出的需求与外部重算对不上）"),
    ("M15",
     "    can = all(R[c] for c in D_IDS)\n    RP.append(\"【5】",
     "    can = True\n    RP.append(\"【5】",
     "T2", "判决逻辑被**短路**（永远「能回答」）"),
    ("M16",
     "    RP.append(\"  · ⛔ 本工具**不产出**「固定剂量下各改判多少题 / 差多少 pp / p 值 / 区间」\"\n"
     "              \"⇒ 那一批**还没跑** ⇒ **未量到**（⛔ **不是**「无差异」）\")",
     "    RP.append(\"  · 本工具只回答「能不能」\")",
     "T1c", "【0】的「**未量到**」声明被删（⇒ 未量到被说得像已量到）"),
    ("M17",
     "BANNED_WORDS = (\"无差异\", \"无效应\", \"没有差异\", \"不影响\")",
     "BANNED_WORDS = ()",
     "T10", "**禁词表被清空**（⇒ 未量到可以被说成零）"),
    ("M18",
     "    extra_raw = sorted(k for k in (prereg_raw or {}) if k not in fda().PREREG_KEYS)",
     "    extra_raw = []",
     "T9c", "P1 的「**多出来的键**」检查被短路（⇒ 多写的口径被静默忽略）"),
    ("M19",
     "    except (HardFail, fda().HardFail) as e:",
     "    except fda().HardFail as e:",
     "T9e", "CLI 只捕 `fda().HardFail` ⇒ 设计描述缺文件/畸形时**崩成 traceback**"
     "（⛔ 「崩」不是「抓到」）"),
]


def _load(path, src=None):
    mod = types.ModuleType("pfp_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_design(mod):
    """⚖ 真实设计路：跑完整的「读预登记 → 重算规模 → 出报告 + 判据」。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _RP, R, _can = mod.run_preflight(mod._bench_design())
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
        if "[FAIL]" in line:
            # ⚖⚠⚖⚖⚠ **token 必须只取到全角冒号之前**
            #   （自检印的是「  [FAIL] T7：设计声明 5 档 ≠ …」⇒ `\S+` 会把
            #    「T7：设计声明」整段当成 token ⇒ 期望的「T7」**永远匹配不上**
            #    ⇒ 13 条明明被抓到却被记成「存活」⇒ **台架自己的 bug**）
            m = re.match(r"\s*\[FAIL\]\s+([^\s：:]+)", line)
            if m:
                fails.add(m.group(1))
    return fails, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    src = io.open(args.target, encoding="utf-8").read()

    # ⚖ 把合格设计塞进模块命名空间（工具本身不依赖它 ⇒ ⛔ 不改被检对象）
    base = _load(args.target, src)
    base._bench_design = lambda: dict(GOOD_DESIGN)

    R0, err0 = run_design(base)
    if err0:
        print("⛔ 基线崩了：%s" % err0)
        return 1
    red0 = set(c for c, v in R0.items() if not v)
    sf0, serr0 = run_selftest_fails(base)
    print("基线（真实设计路）：%d/%d 通过%s"
          % (sum(1 for v in R0.values() if v), len(R0),
             ("（红：%s）" % ",".join(sorted(red0))) if red0 else ""))
    print("基线（自检）：失败集合 %s" % (",".join(sorted(sf0)) or "空"))
    if red0 or sf0 or serr0:
        print("⛔ 基线不绿 ⇒ 先修基线，台架不许跑（%s%s）"
              % (err0 or "", ",".join(sorted(sf0))))
        return 1

    caught, survived, invalid, crashed = [], [], [], []
    for mid, old, new, want, why in MUTATIONS:
        n_hit = src.count(old)
        if n_hit != 1:
            invalid.append((mid, "落点串命中 %d 处（必须恰好 1 处）" % n_hit))
            print("[SKIP] %s 落点串命中 %d 处 ⇒ 变异**无效**（%s）" % (mid, n_hit, why))
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
        mod._bench_design = lambda: dict(GOOD_DESIGN)
        R, err = run_design(mod)
        sf, serr = run_selftest_fails(mod)
        if err or serr:
            crashed.append((mid, err or serr))
            print("[CRASH] %s 崩了：%s（⚠ 崩 ≠ 抓到）" % (mid, err or serr))
            continue
        red = set(c for c, v in R.items() if not v)
        by = []
        if want in red:
            by.append("真实设计路")
        if want in sf:
            by.append("自检路（活体变异/畸形夹具）")
        # ⚖⚠⚖⚖⚖ **顺序要紧**：先判「什么都没变」⇒ 那是**无效**变异（no-op），
        #   **不是**「存活」⇒ 否则台架会把「等价变异」记成「判据抓不住」（冤枉判据）
        if not red and not sf:
            invalid.append((mid, "真实路与自检都没变 ⇒ 变异**无效**（等价变异）"))
            print("[SKIP] %s 真实路与自检均未变化 ⇒ 变异**无效**（等价变异）" % mid)
            continue
        if not by:
            survived.append((mid, want, "真实路红=%s；自检失败=%s"
                             % (",".join(sorted(red)) or "无",
                                ",".join(sorted(sf)) or "无")))
            print("[SURVIVED] %s 期望 %s 红，实际 真实路=%s 自检=%s ⇒ **变异存活**"
                  % (mid, want, ",".join(sorted(red)) or "无",
                     ",".join(sorted(sf)) or "无"))
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
