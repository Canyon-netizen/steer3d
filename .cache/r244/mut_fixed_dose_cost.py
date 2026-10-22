#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_fixed_dose_cost.py —— `fixed_dose_cost.py` 的**变异台**。

⚖⚠⚖⚖⚖⚖ **纪律**（从 244.70 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活」
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`
      （⛔ 只认 SyntaxError 会把 IndentationError 记成「存活」）

⚖ 做法：改源码 ⇒ 跑 `--selftest` ⇒ 期望**指定**的那条自检用例由 PASS 变 FAIL ⇒ 抓住。

⚖ **本台架要抓的三类错**（都是 244.71 自己真犯过 / 差点犯的）：
   ① **成本口径被低估**（M4 用每条中位代替每对均值 ⇒ 低估 2.08 倍；
      M5 用中位代替均值 ⇒ 低估 2 倍；M9 乘数错 ⇒ 整段少算一半）
   ② **判决逻辑被写死**（M1/M2/M3/M6 把判据改成恒真；M8 把总成本改成 0）
   ③ **判决方向搞反**（M7 把「未量到」的前提抹掉；M10 把「要补的量」当成阻断；
      M11 把缺口类别混成「两者」；M12 把格子数算少一半）
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
TARGET = os.path.join(HERE, "fixed_dose_cost.py")

# ⚖ `[FAIL]` 行的用例号：只允许字母/数字/下划线（⛔ 不用贪婪的 `\S+`）
FAIL_RE = re.compile(u"^\\[FAIL\\] ([A-Za-z0-9_]+)\uff1a", re.M)

# ⚖ 子进程**崩**了的形状（⛔ 任何 `*Error` / `*Exception` / Traceback 都算）
CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 落点串, 替换串, 期望红的自检用例, 说明)
MUTATIONS = [
    ("M1", "ok1 = tgt <= n_tid_pool", "ok1 = True",
     "T1", "C1（轨迹数可得）被改成恒真 ⇒ 池子不够也不红"),
    ("M2", "ok2 = nblk <= n_blk_pool", "ok2 = True",
     "T2", "C2（块数可得）被改成恒真 ⇒ 块数不够也不红"),
    ("M3", "ok3 = cpt <= len(pf_avail)", "ok3 = True",
     "T3", "C3（同剂量多格可构造）被改成恒真"),
    ("M4", "bytes_gen = need_pairs * per_pair_bytes",
     "bytes_gen = need_pairs * per_tid_median * 2",
     "T4", "边际生成成本改用「每条中位 × 2」⇒ **低估 2.08 倍**"
           "（这正是 244.70 那个 202 GB 的根因）"),
    ("M5", "probe_mean_s = half * (w_t_mean + w_n_mean + r_t_mean + r_n_mean)",
     "probe_mean_s = half * (w_t_med + w_n_med + r_t_med + r_n_med)",
     "T5", "墙钟改用**中位**⇒ 长尾分布下**低估 2 倍**"),
    ("M6", "ok6 = (cpt <= 1) or has_pf", "ok6 = True",
     "T6", "C6（格清单格式）被改成恒真 ⇒ 缺 pos_frac 列也不红"),
    ("M7", "    if not ok7:\n        premises.append(",
     "    if False:\n        premises.append(",
     "T7b", "「未量到」那条前提被抹掉 ⇒ 未量到的轴被当成已测过"),
    ("M8", "total_mean_s = gen_mean_s + probe_mean_s",
     "total_mean_s = 0",
     "T8", "总成本被写成 0 ⇒ 「贵」与「便宜」都判不出来"),
    ("M9", "half = per_arm_cells // 2", "half = per_arm_cells // 4",
     "T11", "格数乘数错 ⇒ 整段**少算一半**（本轮真犯过）"),
    ("M10", "if not R.get(c, False) and c not in (\"C1\", \"C2\")",
     "if not R.get(c, False)",
     "T13", "「扩池」的 C1/C2 被算成阻断 ⇒ 扩池路线**永远判红**"),
    ("M11", "\"生成侧\" if ks == {\"生成侧\"} else \"两者\"",
     "\"两者\"",
     "T14", "缺口类别混成「两者」⇒ 动作不同的事被当成同一件"),
    ("M12", "n_cells_total = int(route[\"n_blocks\"]) * 2 * cpt * len(arms)",
     "n_cells_total = int(route[\"n_blocks\"]) * 2 * cpt * len(arms) // 2",
     "T10", "格子数算少一半 ⇒ 成本少算一半"),
]


def parse_fails(out):
    return FAIL_RE.findall(out or "")


def run_script(script, cwd, timeout=1200, args=()):
    try:
        p = subprocess.run([sys.executable, script] + list(args), cwd=cwd,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def run_selftest(r244dir):
    """⚖⚠⚖ **必须显式传 `--selftest`** —— ⛔ 不传 ⇒ 目标工具会印「用法」并 rc=2
    ⇒ ⇒ 阳性对照就会读到「一条 `[FAIL]` 都没有」⇒ ⇒ **台架自己瞎了却报「瞎了」**
    ⇒ ⇒ 这一条是本轮真踩的坑（244.70 的目标工具默认就自检，本轮的不是）"""
    return run_script(os.path.join(r244dir, "fixed_dose_cost.py"), r244dir,
                      args=("--selftest",))


def _positive_control(tdir):
    """⚖⚖⚖ **阳性对照**：往台架**真正会跑的那个目录**里放一个「必定红」的假目标。

    ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ **台架自己瞎了** ⇒ 下面的「存活」一律不算数 ⇒ 退出。
    """
    fake = os.path.join(tdir, "fixed_dose_cost.py")
    src = io.open(fake, encoding="utf-8").read()
    # ⚖ 把 selftest 的第一条检查改成**必定红**（不改判定逻辑，只改夹具）
    bad = src.replace('chk("T1", (not v["R"]["C1"]) and (not v["can"]),',
                      'chk("T1", False,')
    if bad == src:
        return False, "阳性对照的落点没找到（夹具变了？）"
    io.open(fake, "w", encoding="utf-8").write(bad)
    rc, out = run_selftest(tdir)
    fails = parse_fails(out)
    if "T1" not in fails:
        # ⚖⚖⚖ **失败时必须带证据**（⛔ 光说「台架自己瞎了」等于没说）
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
    ap = argparse.ArgumentParser(description="fixed_dose_cost.py 的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔，如 M1,M4）")
    a = ap.parse_args()

    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**（⛔ 不过 ⇒ 下面的「存活」不算数 ⇒ 直接退出）
    tdir = tempfile.mkdtemp(prefix="mutcost_")
    try:
        shutil.copy(TARGET, os.path.join(tdir, "fixed_dose_cost.py"))
        for aux in ("fixed_dose_pool_snapshot.json", "fixed_dose_cost_baseline.json",
                    "fixed_dose_route_expand_pool.json", "fixed_dose_route_measure_first.json"):
            src = os.path.join(HERE, aux)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(tdir, aux))
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

    for mid, anchor, repl, expect, why in muts:
        tdir = tempfile.mkdtemp(prefix="mutcost_%s_" % mid)
        try:
            tgt = os.path.join(tdir, "fixed_dose_cost.py")
            shutil.copy(TARGET, tgt)
            for aux in ("fixed_dose_pool_snapshot.json", "fixed_dose_cost_baseline.json",
                        "fixed_dose_route_expand_pool.json",
                        "fixed_dose_route_measure_first.json"):
                src = os.path.join(HERE, aux)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(tdir, aux))
            src = io.open(tgt, encoding="utf-8").read()
            n = src.count(anchor)
            if n != 1:
                invalid.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                print("[无效] %s：落点命中 %d 次 ⇒ 这条变异**无效**（不是「存活」）" % (mid, n))
                continue
            io.open(tgt, "w", encoding="utf-8").write(src.replace(anchor, repl))
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
    print("变异台：抓住 %d / %d" % (len(caught), len(muts)))
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived), [s[0] for s in survived]))
        for mid, why, fails in survived:
            print("    %s：%s（实际红了 %r）" % (mid, why, fails))
    if crashed:
        print("⚠ 崩了 %d 条：%s" % (len(crashed), [c[0] for c in crashed]))
        for mid, why, tail in crashed:
            print("    %s：%s ⇒ %s" % (mid, why, tail))
    if invalid:
        print("⚠ 无效变异 %d 条：%s" % (len(invalid), [i[0] for i in invalid]))
    return 0 if (not survived and not crashed and not invalid) else 1


if __name__ == "__main__":
    sys.exit(main())
