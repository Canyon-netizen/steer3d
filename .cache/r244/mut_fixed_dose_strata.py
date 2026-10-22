#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_mutfixed_dose_strata.py —— `fixed_dose_strata.py` 的**变异台**。

⚖⚠⚖⚖⚖⚖ **纪律**（从 244.70–244.71 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活」
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`
   ⑧ ⚖ **必须显式传 `--selftest`** —— ⛔ 不传 ⇒ 目标工具会印「用法」并 rc=2

⚖ **本台架要抓的错**（244.72 这轮自己真犯过 / 差点犯的）：
   ① **把三层当一层**（M1：层数算成 1 ⇒ 「换 pos_frac」被当成单变量）
   ② **把红判据改成恒绿**（M2：作用比例漂移判据改成恒真 ⇒ 2.75 倍的漂移看不见了）
   ③ **把实测数写死/抹掉**（M3：Jaccard 写 0；M9：n_eff 的口径校验关掉）
   ④ **把前提抹掉**（M6：抹掉「未量到」；M8：抹掉「剂量口径歧义」）
   ⑤ **把物理约束关掉**（M5：越界检查改成不触发 ⇒ 探针会崩的格发不出去都不知道）
   ⑥ **把门槛/等价性判掉**（M4：块数算成 0；M7：取数口径差异一律判绿）

⚖⚠⚖⚖ **为什么文件名带下划线**：⛔ 全回归只枚举 `.cache/r244` 下**不以 `_` 开头**的 `.py`
  ⇒ ⇒ 本台架**不进回归执行集** ⇒ ⇒ 不改执行集 md5 清单 ⇒ ⇒ **不触发别的实例重启 4 小时回归**
  ⇒ ⇒ 代价：⛔ **本台架与被测工具都不被全回归覆盖** ⇒ ⇒ 这一层是**留白**，账本里会写明。
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "fixed_dose_strata.py")

FAIL_RE = re.compile(u"^\\[FAIL\\] ([A-Za-z0-9_]+)\uff1a", re.M)
CRASH_RE = re.compile(r"Traceback|\b\w*(?:Error|Exception)\b")
AUX = ("fixed_dose_pool_snapshot.json", "fixed_dose_dispatch_spec_example.json",
       "warm_cells.txt", "dose_confound_audit.py")

# ⚖ (id, 锚点, 替换, 期望变红的那条自检用例, 为什么)
MUTATIONS = [
    ("M1", "n_strata = len(pos_fracs) if t_all_distinct else 1",
     "n_strata = 1", "T2",
     "层数被算成 1 ⇒ 三层被当成一层 ⇒ 「换 pos_frac 是单变量」"),
    ("M2", "DRIFT_SEQ = DRIFT_OP",
     "DRIFT_SEQ = DRIFT_FIXED", "T3",
     "判据评估的规则被换成**旧规则**（n_sites 跨层固定）⇒ ⇒ 「固定剂量」在作用比例这一维上不成立"),
    ("M3", "JACC = max(j_pairs.values()) if j_pairs else 1.0",
     "JACC = 0.0", "T4",
     "层间位点身份被写死成 0 ⇒ 「位点身份不可比」这个实测数没了"),
    ("M4", "n_blk_have = min(n_blk_pool, n_blk_want)",
     "n_blk_have = 0", "T5",
     "块数算成 0 ⇒ 「够不够预登记门槛」这条判据失效"),
    ("M5", "if r[\"n_sites\"] > r[\"seq\"][p]:",
     "if False:", "T6c",
     "物理可达（n_sites 越界）检查被关掉 ⇒ 探针会崩的格发不出去也不知道"),
    ("M6", "premises.append(prem7)",
     "pass  # 变异 M6：抹掉「未量到」", "T7",
     "「剂量档位未量到」被抹掉 ⇒ 未量到的被当成已核过"),
    ("M7", "ok8 = not ladder_mismatch",
     "ok8 = True", "T8b",
     "取数口径的等价性一律判绿 ⇒ 负样（改坏一个阶梯档位）再也抓不住它 ⇒ ⇒ 口径没钉死也没人知道"),
    ("M8", "premises.append(prem_txt)",
     "pass  # 变异 M8：抹掉剂量口径歧义", "T1",
     "剂量口径歧义被抹掉 ⇒ 「固定剂量」那句话是空的却看不出来"),
    ("M9", "if n_eff != P + max(1, int(n_gen * 0.5)):\n            n_eff_cal_ok = False",
     "if False:\n            n_eff_cal_ok = False", "T9",
     "n_eff 的口径校验（n_eff == P + int(0.5 × n_gen)）被关掉 ⇒ 口径漂了也不知道"),
    # ⚖⚖⚖⚖⚖ **M13 是「等价变异」**：替换串**故意等于**锚点 ⇒ ⇒ 文件逐字节不变
    #   ⇒ ⇒ 纪律 ③ 要求它记成「**无效**」（⛔ 不是「存活」）⇒ ⇒ **它就是纪律 ③ 的验收用例**
    ("M13", "ok9 = (worst is not None) and (worst <= tol)",
     "ok9 = (worst is not None) and (worst <= tol)", "T12",
     "【等价变异】替换串等于锚点 ⇒ 文件逐字节不变 ⇒ 必须记成「无效」（⛔ 不是「存活」）"),
    ("M11", "ns = int(round(frac * denom))",
     "ns = int(round(frac * denom * 1.5))", "T12",
     "缩放口径被改坏（密度放大 1.5 倍）⇒ 「固定剂量」在修法下也不成立"),
    ("M12", "if ns == hits[0]:",
     "if ns == hits[0] + 1:", "T13",
     "连续性比较被改坏（拿错的档比）⇒ 「既有 137 格仍可比」这条没验过"),
    ("M10", "cells_per_arm = int(route[\"n_blocks\"]) * tracks_per_block * len(pos_fracs)",
     "cells_per_arm = int(route[\"n_blocks\"]) * tracks_per_block * len(pos_fracs) * len(arms)",
     "T11",
     "格数**多乘了一次臂** ⇒ 每臂 336（真值 168）⇒ 整段成本与规模翻倍"),
    # ⚖⚖⚖⚖⚖ **244.73 新增**：口径钉死 与 操作规则 的两条
    ("M14", "if src == \"ladder\" and constructed_prod != n_sites:",
     "if src == \"ladder\" and constructed != n_sites:", "T8",
     "S8 的基准被换回**旧的 n_eff 口径** ⇒ ⇒ 阶梯与口径对不上（2 条）⇒ ⇒ 口径没钉死"),
    ("M15", "RULE = \"per_layer\"",
     "RULE = \"fixed\"", "T3",
     "规格没声明规则时的**兜底**取错成旧规则（fixed）⇒ ⇒ 判据评估了错的规则 ⇒ ⇒ 「固定剂量」不成立"),
]


def parse_fails(out):
    return FAIL_RE.findall(out or "")


def run_script(script, cwd, timeout=1800, args=()):
    try:
        p = subprocess.run([sys.executable, script] + list(args), cwd=cwd,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def run_selftest(tdir):
    """⚖⚠⚖ **必须显式传 `--selftest`**。"""
    return run_script(os.path.join(tdir, "fixed_dose_strata.py"), tdir,
                      args=("--selftest",))


def _copy_tree(tdir):
    shutil.copy(TARGET, os.path.join(tdir, "fixed_dose_strata.py"))
    for aux in AUX:
        src = os.path.join(HERE, aux)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(tdir, aux))


def _positive_control(tdir):
    """⚖⚖⚖ **阳性对照**：往台架**真正会跑的那个目录**里放一个「必定红」的假目标。"""
    fake = os.path.join(tdir, "fixed_dose_strata.py")
    src = io.open(fake, encoding="utf-8").read()
    bad = src.replace('chk("T9", (not v3["n_eff_cal_ok"]),',
                      'chk("T9", False,')
    if bad == src:
        return False, "阳性对照的落点没找到（夹具变了？）"
    io.open(fake, "w", encoding="utf-8").write(bad)
    rc, out = run_selftest(tdir)
    fails = parse_fails(out)
    if "T9" not in fails:
        return False, ("阳性对照没被抓到（台架自己瞎了？）⇒ 抓到 %r ｜ rc=%s ｜ 输出尾巴：%r"
                       % (fails, rc, (out or "")[-400:]))
    return True, "阳性对照通过（台架能判红）"


def _looks_like_crash(out):
    if "TIMEOUT" in (out or ""):
        return True
    return bool(CRASH_RE.search(out or ""))


def _looks_like_bench_side_error(out):
    o = out or ""
    return ("can't open file" in o) or ("No such file or directory" in o and
                                        "Traceback" not in o)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="fixed_dose_strata.py 的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔，如 M1,M4）")
    a = ap.parse_args()

    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**
    tdir = tempfile.mkdtemp(prefix="mutstrata_")
    try:
        _copy_tree(tdir)
        ok, msg = _positive_control(tdir)
        print("台架阳性对照：%s ⇒ %s" % ("rc=?" if not ok else "过", msg))
        if not ok:
            print("⛔ **台架自己瞎了** ⇒ 本轮结果一律不算数 ⇒ 退出")
            return 2
    finally:
        shutil.rmtree(tdir, ignore_errors=True)

    caught = []
    survived = []
    crashed = []
    invalid = []
    invalid_equiv = []      # ⚖ 等价变异（**示范纪律 ③**）⇒ 不算失败
    invalid_anchor = []    # ⚖ 锚点命中 ≠ 1 ⇒ **变异写错了** ⇒ 算失败

    for mid, anchor, repl, expect, why in muts:
        tdir = tempfile.mkdtemp(prefix="mutstrata_%s_" % mid)
        try:
            tgt = os.path.join(tdir, "fixed_dose_strata.py")
            _copy_tree(tdir)
            src = io.open(tgt, encoding="utf-8").read()
            n = src.count(anchor)
            if n != 1:
                invalid_anchor.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                invalid.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                print("[无效] %s：落点命中 %d 次 ⇒ 这条变异**无效**（不是「存活」）" % (mid, n))
                continue
            new_src = src.replace(anchor, repl)
            # ⚖⚖⚖⚖⚖ **纪律 ③ 的实现**：等价变异（替换后**逐字节相同**）必须记成「无效」
            #   ⇒ ⇒ ⛔ 不是「存活」（⛔ 存活的意思是「改了一处、判据还是绿的」⇒ ⇒ 那更糟）
            #   ⇒ ⇒ ⚠ 244.70–244.72 的几个台架**只把这句写进了 docstring** ⇒ ⇒ 从没实现
            #   ⇒ ⇒ ⇒ 所以「什么都没变」会被报成「存活」⇒ ⇒ ⇒ **这条纪律本来是空的**
            if new_src == src:
                invalid_equiv.append((mid, why, "等价变异（替换后逐字节相同）⇒ 不是「存活」"))
                invalid.append((mid, why, "等价变异（替换后逐字节相同）⇒ 不是「存活」"))
                print("[无效] %s：**等价变异**（替换后逐字节相同）⇒ ⇒ 这条变异**无效**"
                      "（⛔ 不是「存活」）" % mid)
                continue
            io.open(tgt, "w", encoding="utf-8").write(new_src)
            rc, out = run_selftest(tdir)
            fails = parse_fails(out)
            if _looks_like_bench_side_error(out):
                crashed.append((mid, why, "子进程没跑起来"))
                print("[崩 ] %s ⇒ **台架自己的错**（⛔ 不是「抓到」）：%s" % (mid, why))
                continue
            if _looks_like_crash(out):
                crashed.append((mid, why, out.strip()[-200:]))
                print("[崩 ] %s ⇒ **崩了**（⛔ 崩 ≠ 抓到）：%s" % (mid, why))
                continue
            if expect in fails:
                caught.append((mid, why))
                print("[抓到] %s ⇒ %s 变红（%s）" % (mid, expect, why))
            else:
                survived.append((mid, why, fails))
                print("[存活] %s ⇒ 期望 %s 红，实际红了 %r" % (mid, expect, fails))
        finally:
            shutil.rmtree(tdir, ignore_errors=True)

    print("")
    print("变异台：抓住 %d / %d **有效**变异%s"
          % (len(caught), len(muts) - len(invalid),
             ("（另 %d 条**无效**：等价变异 %d ／ 锚点写错 %d）"
              % (len(invalid), len(invalid_equiv), len(invalid_anchor)))
             if invalid else ""))
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived), [s[0] for s in survived]))
        for mid, why, fails in survived:
            print("    %s：%s（实际红了 %r）" % (mid, why, fails))
    if crashed:
        print("⛔ 崩了 %d 条：%s" % (len(crashed), [c[0] for c in crashed]))
        for mid, why, tail in crashed:
            print("    %s：%s（%s）" % (mid, why, tail))
    if invalid:
        print("ℹ 无效 %d 条：%s（⚠ 无效**不算**存活；但必须报出来）" % (len(invalid), [i[0] for i in invalid]))
        for mid, why, msg in invalid:
            print("    %s：%s（%s）" % (mid, why, msg))
    # ⚖⚖⚖⚖⚖ **退出码的口径**：等价变异是**示范纪律 ③**的用例 ⇒ **不算失败**
    #   ⇒ 但「锚点命中 ≠ 1」= 变异写错了 ⇒ **算失败**（⛔ 否则一个错锚点会静默放过）
    if survived or crashed or invalid_anchor:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
