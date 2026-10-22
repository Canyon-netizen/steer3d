#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_fixed_dose_density_target.py —— `fixed_dose_density_target.py` 的**变异台**（244.75）。

⚖⚠⚖⚖⚖ **纪律**（从 244.70–244.74 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活」
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`

⚖⚖⚖⚖⚖ **本台架要抓的几类错**（244.75 的重点）：
   ① ⚠⚠⚖⚖ **窗口判据被改成恒真/恒假** ⇒ ⇒ 「能不能造出新阶梯」这个判据瞎掉
      ⇒ ⇒ 244.75 的核心结论（每个候选 ρ\\* 都可行）会变成**假话**
   ② ⚠⚠⚖⚖ **inj 不走生产实现**（漏 `max(1,…)`）⇒ ⇒ 与生产口径**分叉** ⇒ ⇒ 测量到的
      「密度相等」是**假的**
   ③ ⚠⚠⚖⚖ **D2 判据（极差 ≤ tol）被改成恒真** ⇒ ⇒ 「固定剂量」的定义被架空
   ④ ⚠⚠⚖ **「零新格」的复用判据被改坏** ⇒ ⇒ 244.75 那条更正（322 而非 336）会说错
   ⑤ **夹取 / 列数判定 / 空窗口处理**被改坏 ⇒ ⇒ 边界情形出错或**猜数**
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TOOL = "fixed_dose_density_target.py"

# ⚖ `[FAIL]` 行的用例号：只允许字母/数字/下划线（⛔ 不用贪婪的 `\S+`）
#   ⚠⚠⚠ **行首允许空白**（244.75 实测踩过）：被检工具的自检是
#     `print("  [%s] %-5s %s" % ...)` ⇒ ⇒ **`[FAIL]` 前面有 2 个空格**
#     ⇒ ⇒ 正则若要求 `^\[FAIL\]` ⇒ ⇒ **一条红都认不出来** ⇒ ⇒ 台架**全瞎**
#     ⇒ ⇒ 幸而**阳性对照**先过把它抓住了（⛔ 否则这轮会报「全部存活」而我信了）
FAIL_RE = re.compile(u"^\\s*\\[FAIL\\]\\s+([A-Za-z0-9_]+)[\\s\uff1a]", re.M)

# ⚖ 子进程**崩**了的形状（⛔ 任何 `*Error` / `*Exception` / Traceback 都算）
CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 落点串, 替换串, 期望红的自检用例, 说明)
MUTATIONS = [
    ("M1",
     "        if abs(float(n) / float(inj) - target) <= tol:",
     "        if True:  # 变异：窗口判据被改成恒真",
     "T3",
     "⚠⚠⚖⚖ **合法 n_sites 的窗口判据被改成恒真** ⇒ ⇒ 「这个 (轨迹, pos_frac) 有没有合法 "
     "n_sites」这个问题**瞎掉** ⇒ ⇒ 244.75 的核心结论（每个候选 ρ\\* 都可行）会变成**假话** "
     "⇒ ⇒ T3 必须红"),
    ("M2",
     "    if n < 1:\n        n = 1",
     "    if n < 1:\n        n = 0  # 变异：下限夹取被拆",
     "T12",
     "⚠⚠⚖ **规范取整的下限夹取被拆** ⇒ ⇒ 极端情形下 `n_sites = 0`（⇒ 注入 0 个位置）"
     "⇒ ⇒ T12 必须红"),
    ("M3",
     '    return DC.denom_of({"inject_n_sites": 1, "P": int(P), "n_gen": int(n_gen),\n'
     '                         "pos_frac": float(pos_frac)})',
     "    return int(P) + int(int(n_gen) * float(pos_frac)) - 1  # 变异：漏掉 max(1, …)",
     "T1a",
     "⚠⚠⚖⚖⚖ **inj 不走生产实现**（漏了 `max(1, …)` 的夹取）⇒ ⇒ 与生产口径**分叉** ⇒ ⇒ "
     "测出来的「密度相等 / 不等」是**假的** ⇒ ⇒ T1a 必须红"),
    ("M4",
     "            has_pf = (len(parts) >= 4)",
     "            has_pf = (len(parts) >= 3)  # 变异：pos_frac 列判定被放宽",
     "T7a",
     "⚠⚠⚖ **阶梯的「有没有 pos_frac 列」判定被放宽** ⇒ ⇒ 3 列的阶梯会被当成 4 列 ⇒ ⇒ "
     "「rung 只对它生成时的 pos_frac 有效」这条**丢了** ⇒ ⇒ **T7a** 必须红"
     "（⚠ 244.75 预跑实测：这条变异破的是 T7a（「3 列 ⇒ 必须认出**没有** pos_frac」），"
     "⛔ 我第一版把期望写成了 T7b ⇒ ⇒ 台架报「存活」⇒ ⇒ **期望写错**也要改，不是变异的问题）"),
    ("M5",
     "        return (max(dens) - min(dens)) <= tol",
     "        return True  # 变异：D2 判据被改成恒真",
     "T6b",
     "⚠⚠⚖⚖⚖ **D2 判据（同轨迹密度相等）被改成恒真** ⇒ ⇒ 「固定剂量」的定义被架空 ⇒ ⇒ "
     "任何密度组合都会被说成「固定剂量」⇒ ⇒ T6b 必须红"),
    ("M6",
     "    w = window_for(inj, target, tol)\n    if not w:\n        return None",
     "    w = window_for(inj, target, tol)\n    if not w:\n        return 1  # 变异：空窗口时猜一个数",
     "T4",
     "⚠⚠⚖ **空窗口时返回了一个猜的数**（⛔ 不许猜）⇒ ⇒ 供给不成立的情形会被说成成立 "
     "⇒ ⇒ T4 必须红"),
    ("M7",
     "            ok = bool(w)\n            if ok:\n                n_combo_ok += 1",
     "            if True:  # 变异：可行组合计数恒真\n                n_combo_ok += 1",
     "T15",
     "⚠⚠⚖ **「可行组合」计数被改成恒真** ⇒ ⇒ 「每个 (轨迹, pos_frac) 都可行」变成**假话** "
     "⇒ ⇒ T15 必须红"),
    ("M8",
     "        if cn in rungs:",
     "        if True:  # 变异：复用判据恒真",
     "T14",
     "⚠⚠⚖ **「零新格」的复用判据被改成恒真** ⇒ ⇒ 每条轨迹都会被说成「可复用」⇒ ⇒ "
     "244.75 那条更正（**308** 而非 336）会说错 ⇒ ⇒ T14 必须红"),
    ("M9",
     "        rungs = ladder.get(tid) or []\n        if not rungs:\n            continue\n"
     '        inj = inj_of(DC, info["P"], info["n_gen"], 0.5)',
     "        rungs = ladder.get(tid) or []\n        if not rungs:\n            continue\n"
     '        inj = inj_of(DC, info["P"], info["n_gen"], 0.25)  # 变异：用错 pos_frac',
     "T14",
     "⚠⚠⚖ **复用时用错了 `pos_frac`**（0.25 而不是现批实际的 0.5）⇒ ⇒ 算出来的 "
     "n_sites 不是现批那一档 ⇒ ⇒ 「注入参数逐位相同」这个前提**破了** ⇒ ⇒ T14 必须红"),
    ("M10",
     "    if not w:\n        return None",
     "    if not w:\n        return None",
     "T4",
     "⚖ **等价变异验收用例**：替换串 **==** 落点串 ⇒ 文件**逐字节不变** ⇒ ⇒ 必须记成"
     "「**无效**」（⛔ **不是**「存活」）⇒ ⇒ 纪律 ③ 不是 docstring"),
    ("M11",
     "    n_runs = int(n_reuse_defs) * int(n_arms)",
     "    n_runs = int(n_reuse_defs)  # 变异：抹掉臂数",
     "T16",
     "⚠⚠⚖⚖⚖ **单位不一致**：「可复用」数的是**格定义**（两臂共用），而「要跑的」数的是"
     "**探针运行**（含臂）⇒ ⇒ 抹掉臂数 ⇒ ⇒ **只算了一次** ⇒ ⇒ 「要新跑」被算成 **322** "
     "⛔ 而真值是 **308** ⇒ ⇒ T16 必须红"),
    ("M12",
     "    factor = (len(arms_base) if ok and arms_base else 1)",
     "    factor = (len(arms_base) if arms_base else 1)  # 变异：不看前提就乘臂数",
     "T17b",
     "⚠⚠⚖⚖⚖ **前提不成立也照样乘臂数**：「两臂探过的是同一批格」没核实 ⇒ ⇒ 就把因子乘上去 "
     "⇒ ⇒ **省下的探针数是猜的** ⇒ ⇒ 因子必须**退回 1** ⇒ ⇒ T17b 必须红"),
]


def parse_fails(out):
    return FAIL_RE.findall(out or "")


def _link_tree(root):
    """⚖ 搭一棵**符号链接树**（`.cache/r244`、`.cache/mutbak`、`.cache/xcheck`）。

    ⚖⚠⚖ 被检工具会 **import 同目录的既有机械**（`dose_confound_audit`）⇒ ⇒ 只复制被检
       文件**不够** ⇒ ⇒ 那样会「崩」⇒ ⇒ 而「崩」≠「抓到」⇒ ⇒ **假红** ⇒ ⇒ 搭符号链接树。
    """
    r244 = os.path.join(root, ".cache", "r244")
    os.makedirs(r244)
    for name in sorted(os.listdir(HERE)):
        src = os.path.join(HERE, name)
        dst = os.path.join(r244, name)
        if os.path.isdir(src):
            continue
        try:
            os.symlink(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    for sub in ("mutbak", "xcheck"):
        s = os.path.join(REPO, ".cache", sub)
        d = os.path.join(root, ".cache", sub)
        if not os.path.isdir(s):
            continue
        os.makedirs(d)
        for name in sorted(os.listdir(s)):
            src = os.path.join(s, name)
            dst = os.path.join(d, name)
            if os.path.isdir(src):
                continue
            try:
                os.symlink(src, dst)
            except OSError:
                shutil.copy2(src, dst)
    return r244


def _materialize(r244dir, target_name, text=None):
    """⚖ 把被改文件**真的**放进工作树（⛔ 覆盖那个符号链接）⇒ 改的就是它。"""
    p = os.path.join(r244dir, target_name)
    if os.path.islink(p) or os.path.exists(p):
        os.remove(p)
    src = os.path.join(HERE, target_name)
    if text is None:
        shutil.copy2(src, p)
    else:
        io.open(p, "w", encoding="utf-8").write(text)
    return p


def run_selftest(workdir):
    """⚖⚠⚖ **必须显式传 `--selftest`** ⇒ ⛔ 不传 ⇒ 工具会印「用法」并 rc=2。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r244dir = os.path.join(workdir, ".cache", "r244")
    try:
        p = subprocess.run([sys.executable, os.path.join(r244dir, TOOL),
                            "--selftest"],
                           cwd=workdir, capture_output=True, text=True,
                           timeout=2400, env=env)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def _positive_control(workdir):
    """⚖⚖⚖ **阳性对照** ⇒ 抓不到 ⇒ **台架自己瞎了** ⇒ 下面的「存活」一律不算数。"""
    r244dir = os.path.join(workdir, ".cache", "r244")
    p = os.path.join(r244dir, TOOL)
    src = io.open(p, encoding="utf-8").read()
    bad = src.replace('chk("T1", r == exp and', 'chk("T1", False and')
    if bad == src:
        return False, "阳性对照的落点没找到（夹具变了？）"
    _materialize(r244dir, TOOL, bad)
    rc, out = run_selftest(workdir)
    fails = parse_fails(out)
    if "T1" not in fails:
        return False, ("阳性对照没被抓到（台架自己瞎了？）⇒ 抓到 %r ｜ rc=%s ｜ 输出尾巴：%r"
                       % (fails, rc, (out or "")[-400:]))
    return True, "阳性对照通过（台架能判红）"


def _looks_like_crash(out):
    if "TIMEOUT" in (out or ""):
        return True
    return bool(CRASH_RE.search(out or ""))


def _looks_like_bench_side_error(out):
    """⚖ 子进程**根本没跑起来**（⛔ 不是「变异存活」）。"""
    o = out or ""
    return ("can't open file" in o) or ("No such file or directory" in o and
                                        "Traceback" not in o)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="fixed_dose_density_target.py 的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔，如 M1,M4）")
    a = ap.parse_args()

    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**（⛔ 不过 ⇒ 下面的「存活」不算数 ⇒ 直接退出）
    work = tempfile.mkdtemp(prefix="mutfdt_")
    try:
        r244dir = _link_tree(work)
        _materialize(r244dir, TOOL)
        ok, msg = _positive_control(work)
        print("台架阳性对照：%s ⇒ %s" % ("过" if ok else "rc=?", msg))
        if not ok:
            print("⛔ **台架自己瞎了** ⇒ 本轮结果一律不算数 ⇒ 退出")
            return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    caught = []
    survived = []
    crashed = []
    invalid_anchor = []
    invalid_equiv = []

    # ---- ① 之二：**基线必须先跑一遍**，且**必须全绿** ----
    #   ⚖⚠⚖⚖⚖ **为什么必须加这道（244.75 踩过）**：原来只查「期望那条在变异后红了」
    #   ⇒ ⇒ ⛔ **没查「它在基线里本来是不是绿的」** ⇒ ⇒ 若基线那条本来就是红的
    #   ⇒ ⇒ ⇒ 「变红」是**空话**（红→红）⇒ ⇒ ⇒ 「抓到」是**假的**
    #   ⇒ ⇒ ⇒ 所以现在：**基线有红 ⇒ 台架自己瞎了 ⇒ 退出**（⛔ 不许报「抓到」）
    base_fails = set()
    work = tempfile.mkdtemp(prefix="mutfdt_base_")
    try:
        r244dir = _link_tree(work)
        _materialize(r244dir, TOOL)
        rc, out = run_selftest(work)
        base_fails = set(parse_fails(out))
        print("台架基线：自检红 %d 条 %s" % (len(base_fails), sorted(base_fails)))
        if base_fails:
            print("⛔ **基线就有红项** ⇒ ⇒ 「变红」这个说法**不成立**"
                  "（⛔ 期望必须钉在**基线绿**的那条上）⇒ ⇒ 台架自己瞎了 ⇒ 退出")
            return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for mid, anchor, repl, expect, why in muts:
        work = tempfile.mkdtemp(prefix="mutfdt_%s_" % mid)
        try:
            r244dir = _link_tree(work)
            src = io.open(os.path.join(HERE, TOOL), encoding="utf-8").read()
            n = src.count(anchor)
            if n != 1:
                invalid_anchor.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                print("[无效] %s：落点命中 %d 次 ⇒ 这条变异**无效**（不是「存活」）" % (mid, n))
                continue
            mutated = src.replace(anchor, repl)
            # ⚖⚖⚖ **纪律 ③**：等价变异 = 替换后文件**逐字节不变**
            #   ⇒ ⇒ 必须记成「**无效**」（⛔ **不是**「存活」）⇒ ⇒ 等价变异**不算失败**
            if mutated == src:
                invalid_equiv.append((mid, why, "替换后文件逐字节相同 ⇒ 等价变异 ⇒ 无效"))
                print("[无效] %s：替换后文件**逐字节不变** ⇒ 这条是**等价变异** ⇒ 记「无效」"
                      "（⛔ 不是「存活」）" % mid)
                continue
            _materialize(r244dir, TOOL, mutated)
            rc, out = run_selftest(work)
            fails = parse_fails(out)
            if _looks_like_bench_side_error(out):
                crashed.append((mid, why, "子进程没跑起来"))
                print("[崩 ] %s ⇒ **台架自己的错**（⛔ 不是「抓到」）：%s" % (mid, why))
                continue
            if _looks_like_crash(out):
                crashed.append((mid, why, out.strip()[-300:]))
                print("[崩 ] %s ⇒ **崩了**（⛔ 崩 ≠ 抓到）：%s" % (mid, why))
                continue
            if expect in fails:
                caught.append((mid, why))
                print("[抓到] %s ⇒ %s 变红（%s）" % (mid, expect, why))
            else:
                survived.append((mid, why, fails))
                print("[存活] %s ⇒ 期望 %s 红，实际红了 %r" % (mid, expect, fails))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    print("")
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived), [s[0] for s in survived]))
        for mid, why, fails in survived:
            print("   · %s：期望红的那条**没红**（实际红了 %r）⇒ %s" % (mid, fails, why))
    if crashed:
        print("⛔ 崩 %d 条：%s（⛔ 崩 ≠ 抓到）" % (len(crashed), [c[0] for c in crashed]))
        for mid, why, tail in crashed:
            print("   · %s：%s ⇒ %s" % (mid, tail, why))
    if invalid_anchor:
        print("⛔ 落点无效 %d 条：%s" % (len(invalid_anchor),
                                        [c[0] for c in invalid_anchor]))
        for mid, why, tail in invalid_anchor:
            print("   · %s：%s ⇒ %s" % (mid, tail, why))
    if invalid_equiv:
        print("⚖ 等价变异 %d 条：%s（记「无效」⇒ ⛔ **不计入分母**、**不算失败**）"
              % (len(invalid_equiv), [c[0] for c in invalid_equiv]))
    print("")
    print("变异终检：抓住 %d / %d（等价变异 %d 条 ⇒ 记「无效」⇒ 不计入分母）"
          % (len(caught), len(muts) - len(invalid_equiv), len(invalid_equiv)))
    return 0 if (not survived and not crashed and not invalid_anchor) else 1


if __name__ == "__main__":
    sys.exit(main())
