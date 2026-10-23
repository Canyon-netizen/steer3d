#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_fixed_dose_pooled_verdict_audit.py —— `fixed_dose_pooled_verdict_audit.py`
的**变异台**（244.80，里程碑 **M3** 的 G0-4）。

⚖⚠⚖⚖⚖ **纪律**（从 244.70–244.78 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活」
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条判据该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`
   ⑧ ⚖ 变异可以落在**三个**目标上：分析器本体、**口径真源**（预登记）、
      **依赖模块**（`dose_layer_audit.py`）⇒ ⇒ 「依赖坏了测不到」这件事本身要能红

⚖⚖⚖⚖⚖ **本台架要抓的错**（V-P1…V-P19 每一条都必须证明**能红**）：
   ① 多数规则被改成 `>=`（平票算 True）⇒ ⇒ V-P4
   ② 零格被剔出分母（主口径）⇒ ⇒ V-P4 / V-P5
   ③ 缺读数被当成 0（`d_of` 被绕开）⇒ ⇒ V-P3
   ④ 格集合的条件被拆掉（密度 / scope / 读数 / n_sites）⇒ ⇒ V-P2
   ⑤ 零假设基准被写死 0.5 ⇒ ⇒ V-P6
   ⑥ 零格也抽币（模拟退回旧写法）⇒ ⇒ V-P7
   ⑦ Wilson 被换成别的区间 ⇒ ⇒ V-P11
   ⑧ Fisher 被换成正态近似 ⇒ ⇒ V-P12
   ⑨ 面板印的数与返回的不一致 ⇒ ⇒ V-P16
   ⑩ 异质性 / 三组 `pos_frac` / 块级分母 / 前提清单 / 边界清单 / 问题级那一行
      被删或被改 ⇒ ⇒ V-P9 / V-P10 / V-P13 / V-P14 / V-P15 / V-P17
   ⑪ 口径真源（预登记）被改 ⇒ ⇒ V-P1
   ⑫ 旧批口径被改（`panel_all` 偷偷加 scope 过滤）⇒ ⇒ V-P18
   ⑬ 面板**不印**格数结构（`m` 分布 / `(n_nz,n_zero)` 分布 / 基准分布）
      ⇒ ⇒ V-P19（预登记 V3/V4 明写「必须打印」）
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = "fixed_dose_pooled_verdict_audit.py"
XCHECK = os.path.join(REPO, ".cache", "xcheck")
PREREG_NAME = "R6_FIXED_DOSE_POOLED_VERDICT_PREREG.md"
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")

CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 目标文件（相对 .cache/r244 或 .cache/xcheck）, 落点串, 替换串,
#    期望红的判据, 说明)
MUTATIONS = [
    ("P1", TARGET, '"verdict": (pos * 2 > m),', '"verdict": (pos * 2 >= m),',
     "V-P4",
     "⚖⚖⚖ **多数规则被改成 `>=`**（平票算 True）⇒ ⇒ V-P4 必须红"),
    ("P2", TARGET, '"verdict": (pos * 2 > m),', '"verdict": (pos * 2 > (m - zero)),',
     "V-P5",
     "⚖⚖⚖ **零格被剔出分母**（主口径）⇒ ⇒ V-P5（多数 ≡ 中位数符号）必须红"
     "（⇒ V-P4 也会红，那是同根）"),
    ("P3", TARGET, "d = dconf().d_of(c)              # ⛔ 缺 p9_* ⇒ HardFail（V-P3）",
     "d = float(c.get('p9_hi_meas') or 0.0) - float(c.get('p9_lo_meas') or 0.0)",
     "V-P3",
     "⚖⚖⚖ **缺读数被当成 0**（绕开 `d_of`）⇒ ⇒ V-P3 必须红"),
    ("P4", TARGET, 'if mode == "fixed_dose" and "density" not in drop:',
     'if False and mode == "fixed_dose" and "density" not in drop:',
     "V-P2",
     "⚖⚖⚖ **密度条件被拆掉** ⇒ ⇒ V-P2（条件 load-bearing）必须红"),
    ("P5", TARGET,
     'if "scope" not in drop and rec.get("scope") != spec["scope"]:',
     'if False and "scope" not in drop and rec.get("scope") != spec["scope"]:',
     "V-P2",
     "⚖⚖⚖ **scope 条件被拆掉** ⇒ ⇒ V-P2 必须红"),
    ("P6", TARGET,
     'if "reading" not in drop and not rec.get("measured"):',
     'if False and "reading" not in drop and not rec.get("measured"):',
     "V-P2",
     "⚖⚖⚖ **「读数在」条件被拆掉** ⇒ ⇒ V-P2 必须红"),
    ("P7", TARGET,
     'if "nsites" not in drop and not rec.get("inject_n_sites"):',
     'if False and "nsites" not in drop and not rec.get("inject_n_sites"):',
     "V-P2",
     "⚖⚖⚖ **n_sites 条件被拆掉** ⇒ ⇒ V-P2 必须红"),
    ("P8", TARGET,
     "mean = sum(p for _t, p in per) / float(len(per)) if per else float(\"nan\")",
     "mean = 0.5",
     "V-P6",
     "⚖⚖⚖ **零假设基准被写死 0.5** ⇒ ⇒ V-P6 必须红"),
    ("P9", "dose_layer_audit.py",
     "if track_is_positive(draws, n_nz, n_zero):",
     "if sum(1 for d in draws if d > 0.5) * 2 > len(draws):",
     "V-P7",
     "⚖⚖⚖ **零格也抽币**（模拟退回旧写法）⇒ ⇒ V-P7 必须红"),
    ("P10", TARGET,
     "def wilson(x, n):\n    return iaud().wilson_bounds(x, n)",
     "def wilson(x, n):\n    p = x / float(n)\n    return (max(0.0, p - 1.96 * math.sqrt(p * (1 - p) / n)),\n            min(1.0, p + 1.96 * math.sqrt(p * (1 - p) / n)))",
     "V-P11",
     "⚖⚖⚖ **Wilson 被换成 Wald 区间** ⇒ ⇒ V-P11（与独立实现对账）必须红"),
    ("P11", TARGET,
     "    p, _obs = armv().fisher_exact_two_sided(a, b, c, d)\n    return p",
     "    n = a + b + c + d\n    p1 = (a + b) / float(n) if n else 0.0\n    p2 = (a + c) / float(n) if n else 0.0\n    se = math.sqrt(max(1e-12, p1 * (1 - p1) + p2 * (1 - p2)) / n)\n    z = (p1 - p2) / se\n    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))",
     "V-P12",
     "⚖⚖⚖ **Fisher 被换成正态近似** ⇒ ⇒ V-P12（与独立穷举对账）必须红"),
    ("P12", TARGET,
     'A("  %-4s 改判 **%d/%d** ｜ 区间 %s ｜ 零假设基准（逐轨迹平均）%.4f"\n'
     '          % (arm, a["pos"], a["n_traj"], fmt_ci(a["ci"][0], a["ci"][1]),\n'
     '             a["base_mean"]))',
     'A("  %-4s 改判 **%d/%d** ｜ 区间 %s ｜ 零假设基准（逐轨迹平均）%.4f"\n'
     '          % (arm, a["pos"] + 1, a["n_traj"], fmt_ci(a["ci"][0], a["ci"][1]),\n'
     '             a["base_mean"]))',
     "V-P16",
     "⚖⚖⚖ **面板印的数与返回的不一致**（多印 1）⇒ ⇒ V-P16 必须红"),
    ("P13", TARGET,
     'A("       ├ 异质性（前提，⛔ 不是判决）：三格全一致 %d ｜ 2:1 分歧 %d ｜ 分歧率 %s"\n'
     '          % (a["disagree"]["all_same"], a["disagree"]["split_2to1"],\n'
     '             ("%.4f" % a["disagree"]["rate"]) if a["disagree"]["n"] else "未量到"))',
     'A("       ├ （异质性那行被删了）")',
     "V-P9",
     "⚖⚖⚖ **异质性那行被删** ⇒ ⇒ V-P9（必须**印在面板上**）必须红"),
    ("P14", TARGET,
     'for key, g in (c.get("groups") or {}).items():',
     'for key, g in list((c.get("groups") or {}).items())[:2]:',
     "V-P10",
     "⚖⚖⚖ **三组 `pos_frac` 只印两组** ⇒ ⇒ V-P10 必须红"),
    ("P15", TARGET, '"n_blocks": len(bw), "w_pos": pb, "rand_pos": pr,',
     '"n_blocks": len(bw) * 2, "w_pos": pb, "rand_pos": pr,',
     "V-P13",
     "⚖⚖⚖ **块级分母被改成块数的两倍** ⇒ ⇒ V-P13 必须红"),
    ("P16", TARGET,
     'A("  **不适用**：问题级 Δ 需要 `scope = all` 的格，本批**没有** ⇒ ⇒ "\n'
     '      "⛔ 不是「未量到」，⛔ 不是「无差异」")',
     'A("  FAIL：问题级 0/0")',
     "V-P17",
     "⚖⚖⚖ **「不适用」被渲染成 FAIL** ⇒ ⇒ V-P17 必须红"),
    ("P17", TARGET,
     '    "**`pos_frac = 0.25 / 0.75` 未量到** ⇒ ⇒ 合池会把「`pos_frac` 本身有没有效应」藏起来",',
     '',
     "V-P15",
     "⚖⚖⚖ **边界清单少一条** ⇒ ⇒ V-P15（编号独立字面量）必须红"),
    ("P18", TARGET,
     '    ("【P4】", "**剂量趋势未量到**：合池（`n_bands = 1`）没有剂量轴 ⇒ ⇒ ⛔ **不是「无趋势」**"),',
     '',
     "V-P14",
     "⚖⚖⚖ **前提清单少一条** ⇒ ⇒ V-P14（编号独立字面量）必须红"),
    ("P19", "xcheck/" + PREREG_NAME,
     "sign_source_primary = d_gt_0",
     "sign_source_primary = d_ge_0",
     "V-P1",
     "⚖⚖⚖ **口径真源（预登记）被改** ⇒ ⇒ V-P1（13 键逐字相符）必须红"),
    ("P20", TARGET, 'if mode in ("fixed_dose", "scope_k"):',
     'if mode in ("fixed_dose", "scope_k", "panel_all"):',
     "V-P18",
     "⚖⚖⚖ **旧批 `panel_all` 口径偷偷加了 scope 过滤** ⇒ ⇒ V-P18（12/14 复现）必须红"),
    ("P21", TARGET,
     '每轨迹有效格 m 分布 = %s ｜ ',
     '有效格数分布 = %s ｜ ',
     "V-P19",
     "⚖⚖⚖ **面板不再印 `m` 分布那个标记** ⇒ ⇒ V-P19（预登记 V3/V4 要求「必须打印」）必须红"),
]


def _link_tree(work):
    """⚖ 把 `.cache/r244` 与 `.cache/xcheck` **符号链接**进工作树
    ⇒ 改的确实是被检文件，而**别的**文件仍是原件。"""
    r244dir = os.path.join(work, ".cache", "r244")
    os.makedirs(r244dir)
    for name in sorted(os.listdir(HERE)):
        if name.endswith((".py", ".json", ".sh")):
            os.symlink(os.path.join(HERE, name), os.path.join(r244dir, name))
    xc = os.path.join(work, ".cache", "xcheck")
    os.makedirs(xc)
    for name in sorted(os.listdir(XCHECK)):
        if name.endswith(".md"):
            os.symlink(os.path.join(XCHECK, name), os.path.join(xc, name))
    mb = os.path.join(work, ".cache", "mutbak")
    os.makedirs(mb)
    src = os.path.join(REPO, ".cache", "mutbak", "r227_kcurve.py")
    if os.path.isfile(src):
        os.symlink(src, os.path.join(mb, "r227_kcurve.py"))
    return r244dir, xc


def _materialize(path, text):
    """⚖ 把被检文件**真的**放进工作树（⛔ 覆盖那个符号链接）⇒ 改的就是它。"""
    if os.path.islink(path) or os.path.exists(path):
        os.remove(path)
    io.open(path, "w", encoding="utf-8").write(text)
    return path


def _target_path(work, rel):
    if rel.startswith("xcheck/"):
        return os.path.join(work, ".cache", "xcheck", rel[len("xcheck/"):])
    return os.path.join(work, ".cache", "r244", rel)


def run_criteria(workdir):
    """⚖ 跑被检工具的 `--criteria` ⇒ 返回 `(rc, 判据 dict, 原始输出)`。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = os.path.join(workdir, ".cache", "r244", TARGET)
    cmd = [sys.executable, p, "--criteria",
           "--old-w-log", os.path.join(BPATH, "r244_warm_w.log"),
           "--old-w-status", os.path.join(BPATH, "r244_warm_w_status.txt"),
           "--old-r-log", os.path.join(BPATH, "r244_warm_rand.log"),
           "--old-r-status", os.path.join(BPATH, "r244_warm_rand_status.txt")]
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                           timeout=2400, env=env)
        out = r.stdout + r.stderr
        crit = {}
        try:
            crit = json.loads(r.stdout)
        except Exception:
            crit = None
        return r.returncode, crit, out
    except subprocess.TimeoutExpired:
        return -9, None, "TIMEOUT"


def _red(crit):
    if not crit:
        return []
    return sorted([k for k, v in crit.items() if not v.get("ok")])


def _looks_like_crash(out):
    if "TIMEOUT" in (out or ""):
        return True
    return bool(CRASH_RE.search(out or ""))


def _looks_like_bench_side_error(out):
    o = out or ""
    return ("can't open file" in o) or ("No such file or directory" in o and
                                        "Traceback" not in o)


def _positive_control(workdir):
    """⚖⚖⚖ **阳性对照** ⇒ 抓不到 ⇒ **台架自己瞎了** ⇒ 下面的「存活」一律不算数。"""
    path = os.path.join(workdir, ".cache", "r244", TARGET)
    src = io.open(path, encoding="utf-8").read()
    bad = src.replace('"verdict": (pos * 2 > m),', '"verdict": (pos * 2 >= m),')
    if bad == src:
        return False, "阳性对照的落点没找到（夹具变了？）"
    _materialize(path, bad)
    rc, crit, out = run_criteria(workdir)
    red = _red(crit)
    if "V-P4" not in red:
        return False, ("阳性对照没被抓到（台架自己瞎了？）⇒ 红了 %r ｜ rc=%s ｜ 输出尾巴：%r"
                       % (red, rc, (out or "")[-400:]))
    return True, "阳性对照通过（台架能判红）"


def main():
    import argparse
    ap = argparse.ArgumentParser(description="合池判决层分析器的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔）")
    a = ap.parse_args()
    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**
    work = tempfile.mkdtemp(prefix="mutpooled_")
    try:
        _link_tree(work)
        ok, msg = _positive_control(work)
        print("台架阳性对照：%s ⇒ %s" % ("过" if ok else "不过", msg))
        if not ok:
            print("⛔ **台架自己瞎了** ⇒ 本轮结果一律不算数 ⇒ 退出")
            return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    caught, survived, crashed, invalid_anchor, invalid_equiv = [], [], [], [], []
    for mid, rel, anchor, repl, expect, why in muts:
        work = tempfile.mkdtemp(prefix="mutpooled_%s_" % mid)
        try:
            _link_tree(work)
            path = _target_path(work, rel)
            src = io.open(path, encoding="utf-8").read()
            n = src.count(anchor)
            if n != 1:
                invalid_anchor.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                print("[无效] %s：落点命中 %d 次 ⇒ 这条变异**无效**（不是「存活」）" % (mid, n))
                continue
            mutated = src.replace(anchor, repl)
            if mutated == src:
                invalid_equiv.append((mid, why, "替换后文件逐字节相同 ⇒ 等价变异 ⇒ 无效"))
                print("[无效] %s：替换后文件**逐字节不变** ⇒ 等价变异 ⇒ 记「无效」" % mid)
                continue
            _materialize(path, mutated)
            rc, crit, out = run_criteria(work)
            if _looks_like_bench_side_error(out):
                crashed.append((mid, why, "子进程没跑起来"))
                print("[崩 ] %s ⇒ **台架自己的错**（⛔ 不是「抓到」）：%s" % (mid, why))
                continue
            if _looks_like_crash(out):
                crashed.append((mid, why, out.strip()[-300:]))
                print("[崩 ] %s ⇒ **崩了**（⛔ 崩 ≠ 抓到）：%s" % (mid, why))
                continue
            red = _red(crit)
            if expect in red:
                caught.append((mid, why, red))
                print("[抓到] %s ⇒ %s 变红（同时红了：%s）" % (mid, expect, "、".join(red)))
            else:
                survived.append((mid, why, red))
                print("[存活] %s ⇒ 期望 %s 红，实际红了 %r" % (mid, expect, red))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    print("")
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived), [s[0] for s in survived]))
        for mid, why, red in survived:
            print("    %s：%s（实际红了 %r）" % (mid, why, red))
    if crashed:
        print("⚠ 崩了 %d 条：%s" % (len(crashed), [c[0] for c in crashed]))
        for mid, why, tail in crashed:
            print("    %s：%s ⇒ %s" % (mid, why, tail))
    if invalid_anchor:
        print("⚠ 无效变异 %d 条（锚点命中 ≠ 1）：%s"
              % (len(invalid_anchor), [i[0] for i in invalid_anchor]))
        for mid, why, tail in invalid_anchor:
            print("    %s：%s ⇒ %s" % (mid, why, tail))
    if invalid_equiv:
        print("⚖ 等价变异 %d 条（替换后**逐字节不变** ⇒ 记「无效」⇒ ⛔ **不是**「存活」）：%s"
              % (len(invalid_equiv), [i[0] for i in invalid_equiv]))
    _applied = len(muts) - len(invalid_equiv) - len(invalid_anchor)
    print("变异台：抓住 %d / %d（等价变异 %d 条 ⇒ 记「无效」⇒ 不计入分母）"
          % (len(caught), _applied, len(invalid_equiv)))
    return 0 if (not survived and not crashed and not invalid_anchor) else 1


if __name__ == "__main__":
    sys.exit(main())
