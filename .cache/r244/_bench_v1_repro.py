#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_bench_v1_repro.py —— 244.70 **第一版变异台的复现件**（⛔ 不入库 ＋ ⛔ **不是**要跑的东西）

⚖⚠⚖⚖ 本件 = 终版 `mut_fixed_dose_feasible.py` **只差一处**：
   变异循环里 `run_selftest(tdir)` ⇒ `run_selftest(tmp)`
⇒ ⇒ 用来**复现**第一版的现象：「0/20、且『实际红了 []』」
⇒ ⇒ **根因被隔离到这一个改动上** ⇒ 台架去跑的是一个**根本不存在**的文件
⇒ ⇒ 解释器只印一句「can't open file」⇒ rc=2 ⇒ **一条 `[FAIL]` 都没有**
⇒ ⇒ 这就是「**台架自己瞎了**」与「**判据失守**」在输出上分不开的那次实测。
⇒ ⇒ 修法：跑**变异体真正所在的那个目录** ＋ 给台架自己加一条**阳性对照**。
"""

# ⚖⚠ 以下是终版台架的原文（只改了上面那一行）

r"""mut_fixed_dose_feasible.py —— `fixed_dose_feasible.py` 的**变异台**。

⚖⚠⚖⚖⚖⚖ **纪律**：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活」
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的

⚖ 做法（沿用 244.68 的「活体」路）：改源码 ⇒ 跑 `--selftest` ⇒
   ⇒ 期望**指定**的那条自检用例由 PASS 变 FAIL ⇒ 抓住。

⚖⚠⚖⚖⚖⚖ **第一版台架踩的三个坑（本版逐个封掉）**：
   ⛔ **坑 ①（致命）**：变异体写在 `<work>/.cache/r244/` 里，台架却去跑 `<tmp>/`
      ⇒ 那个文件**根本不存在** ⇒ 解释器只报一句「can't open file」⇒ rc=2、
      一条 `[FAIL]` 都没有 ⇒ **20 条变异全被误判「存活」**
      ⇒ ⚖ **「存活」这个结论本身也要能证伪** ⇒ 本版加了**阳性对照**（见 `_positive_control`）：
      往台架**真正会跑的那个目录**里放一个「必定红」的假目标 ⇒
      台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数。
   ⛔ **坑 ②**：解析 `[FAIL]` 行的正则用 `\S+`（贪婪）⇒ 正note里带全角冒号时
      **tid 会被吞进正文** ⇒ 「期望 T1 红」会被判成「实际红了 T1：xxx」
      ⇒ **假存活** ⇒ 本版改成**只收字母数字下划线**的 tid。
   ⛔ **坑 ③**：变异台**自己也**没有任何阳性对照 ⇒ 它瞎了也能输出「20/20」
      ⇒ 本版把「台架能判红」变成**先决条件**（阳性对照不过 ⇒ 直接退出）。
   ⛔ **坑 ④**：**崩**的识别只认 `SyntaxError` / `Traceback` ⇒ **IndentationError** 漏掉
      ⇒ ⇒ 多行表达式被切坏时（最常见的那种崩）⇒「崩」被**误记成「存活」**
      ⇒ ⇒ 本版认**任何** `*Error` / `*Exception` / `Traceback`。
   ⛔ **坑 ⑤**：本版跑出 **17/20**（M8/M18/M19 存活）⇒ ⚠⚠⚖ **这三条不是台架坏，是判据侧有洞**：
      M18/M19 暴露的是 **T7e 根本没锚在前提段上**（F5 的判据行里本来就写着「未量到」）
      ⇒ ⇒ 「前提段被清空/不印」它照样绿 ⇒ ⇒ **那条自检本身就是恒绿的**
      ⇒ ⇒ 修法：把 T7e 锚到**前提段的标题** ＋ **返回的那条前提的内容**上。
      ⇒ ⇒ ⚖ 这正是台架**该干的事**：它抓的不是「判据红」，是「**这条判据根本抓不住东西**」。
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
TARGET = os.path.join(HERE, "fixed_dose_feasible.py")

# ⚖ `[FAIL]` 行的 tid：只允许字母/数字/下划线（⛔ 不用贪婪的 `\S+`）
FAIL_RE = re.compile(u"^\\[FAIL\\] ([A-Za-z0-9_]+)\\uff1a", re.M)

# ⚖ 子进程**崩**了的形状（⛔ 不只认 SyntaxError —— IndentationError 也要认）
CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 落点串, 替换串, 期望红的自检用例, 说明)
MUTATIONS = [
    ("M1", "need = int(m.group(1))", "need = 3",
     "T3", "规模机械算出的门槛被**写死成 3** ⇒ 剂量扫描设计下 12 格门槛失效"),
    ("M2", "ok1 = cpt >= float(need_cells)", "ok1 = True",
     "T2", "F1 恒绿（m≥3 的门槛怎么算都不红）"),
    ("M3", "ok2 = need_traj <= avail_traj", "ok2 = True",
     "T4", "F2 恒绿（轨迹数不够也不红）"),
    ("M4", "ok3 = need_blk <= avail_blk", "ok3 = True",
     "T5", "F3 恒绿（块数不够也不红）"),
    ("M5", "ok4 = need_at_one <= len(pf_avail)", "ok4 = True",
     "T6", "F4 恒绿（同剂量的格造不出来也不红）"),
    ("M6", "ok5 = not unmeasured", "ok5 = True",
     "T7", "F5 恒绿（pos_frac 未测过也不红）"),
    ("M7", "ok6 = not bad_eff", "ok6 = True",
     "T8", "F6 恒绿（n_eff 缺失也不红）"),
    ("M8",
     '    ok7 = (int(pool["n_tid"]) == len(pool["tids"]) == n_bytes_ok\n'
     '           and int(pool["sources"]["generated_dir"]["bytes"]) ==\n'
     '           sum(int(t["bytes"]) for t in pool["tids"]))',
     "    ok7 = True", "T9", "F7 恒绿（池子不自洽也不红）"),
    ("M9", "ok8 = (need_total is not None and need_total <= avail_traj)",
     "ok8 = True", "T10c", "F8 恒绿（**需求本身**超了可得也不红）"),
    ("M10", "can = not blocking_fail", "can = True",
     "T4", "判决恒绿（有阻断项也判「能回答」）"),
    ("M11", "blocking_fail = [f for f in F_BLOCKING if not R2.get(f, False)]",
     "blocking_fail = [f for f in F_BLOCKING if False]",
     "T4", "阻断项被**清空** ⇒ 判决不再看判据"),
    ("M12", "avail_traj = int(pool[\"n_tid\"])", "avail_traj = 10 ** 9",
     "T4", "可得轨迹数被**架空** ⇒ 池子不够也不红"),
    ("M13", "per_tid = float(pool[\"bytes\"][\"per_tid_median\"])",
     "per_tid = 0.0", "T15", "缺口的**字节数**被抹成 0 ⇒ 缺口没被量化"),
    ("M14", "unmeasured = sorted(x for x in pf_used if x not in pf_meas)",
     "unmeasured = []", "T7", "未测过的 pos_frac 被**当成都测过**"),
    ("M15", "if d[\"dose_mode\"] not in (\"fixed\", \"sweep\"):",
     "if False:", "T12", "dose_mode **不校验** ⇒ 非法值也放行"),
    ("M16", "if not isinstance(d[\"pos_fracs\"], list) or not d[\"pos_fracs\"]:",
     "if False:", "T13", "pos_fracs **不校验** ⇒ 空列表也放行"),
    ("M17", "if not isinstance(v, (int, float)) or isinstance(v, bool):",
     "if False:", "T14", "pos_fracs 的元素**不校验** ⇒ 非数字也放行"),
    ("M18", "F_PREMISE = (\"F5\",)", "F_PREMISE = ()",
     "T7e", "前提类判据被**清空** ⇒ 未量到的取值不印出来"),
    ("M19", "if premise_fail:", "if False:",
     "T7e", "前提段**不印** ⇒ 报告里看不到「未量到」"),
    ("M20", "n_layer = bands_per_traj(design)", "n_layer = 4",
     "T1c", "「一条轨迹服务几个档」被**写死成 4** ⇒ 固定剂量下门槛变 12"),
]


def parse_fails(out):
    """⚖ 从子进程输出里取「红了哪些自检用例」（tid 只收字母数字下划线）。"""
    return FAIL_RE.findall(out or "")


def run_script(script, cwd, timeout=1200):
    p = subprocess.run([sys.executable, script, "--selftest"],
                       cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def run_selftest(r244dir):
    return run_script(os.path.join(r244dir, "fixed_dose_feasible.py"), r244dir)


def _positive_control(tdir):
    """⚖⚠⚖⚖ **台架的阳性对照**（本版的关键防线）。

    往台架**真正会跑的那个目录**里放一个「必定红」的假目标 ⇒ 台架必须抓到它。
    ⇒ 抓不到 ⇒ 台架**自己**瞎了（跑错目录 / 正则失效 / 没读 stdout）⇒
    ⇒ 此时任何「变异存活」都**不算数** ⇒ 直接退出。

    ⚖ 假目标的 note **故意带全角冒号** ⇒ 同时验「tid 不会被正文吞掉」。
    """
    probe = os.path.join(tdir, "_bench_probe_target.py")
    io.open(probe, "w", encoding="utf-8").write(
        "# -*- coding: utf-8 -*-\n"
        "import sys\n"
        "print('[FAIL] TZZZ：台架阳性对照：note 里也带全角冒号：x')\n"
        "sys.exit(1)\n")
    try:
        rc, out = run_script(probe, tdir, timeout=120)
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass
    fails = parse_fails(out)
    if rc == 0 or "TZZZ" not in fails:
        print("⛔⛔ 台架**阳性对照失败** ⇒ 台架自己抓不到红（rc=%s，抓到 %s）"
              % (rc, fails))
        print("   ⇒ 下面的「存活」**一律不算数** ⇒ 先修台架")
        print("   ---- 子进程输出（末尾 20 行）----")
        for ln in (out or "").strip().splitlines()[-20:]:
            print("   | %s" % ln)
        return False
    print("台架阳性对照：rc=%s，抓到 %s ⇒ 台架**能**判红 ✅" % (rc, fails))
    return True


def _looks_like_crash(out):
    """⚖ 子进程**崩**了的形状。

    ⚠⚠⚖⚖ **第一版只认 `SyntaxError` / `Traceback`** ⇒ **IndentationError** 被漏掉
    ⇒ ⇒ 多行表达式被切坏时（最常见的那一种崩）⇒ 「崩」被**误记成「存活」**
    ⇒ ⇒ 而「崩」与「存活」必须**分开报**（⚠ 崩 ≠ 抓到）⇒ ⇒ 这里认**任何** `*Error`
    / `*Exception` / `Traceback`。
    """
    return bool(CRASH_RE.search(out or ""))


def _looks_like_bench_side_error(out):
    """⚖ 子进程**没真正跑起来**的样子（⇒ 这是台架自己的错，⛔ 不是「变异存活」）。"""
    return ("can't open file" in out or "No such file or directory" in out
            or "No module named" in out)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="fixed_dose_feasible.py 的变异台")
    ap.add_argument("--only", default=None,
                    help="只跑这几条变异（逗号分隔，如 M1,M13）⇒ 定点重跑用")
    a = ap.parse_args()
    only = None
    if a.only:
        only = set(x.strip() for x in a.only.split(",") if x.strip())

    src0 = io.open(TARGET, encoding="utf-8").read()
    tmp = tempfile.mkdtemp(prefix="mutfeas_")
    caught, invalid, survived, crashed = [], [], [], []
    try:
        # ---- 基线：原版必须**全绿**（⛔ 基线不绿 ⇒ 台架不许跑）
        # ⚖⚠⚖ 临时树必须**按仓的形状**摆：工具的 REPO = HERE/../..
        #   ⇒ ⇒ 工具放在 <work>/.cache/r244/ ⇒ REPO = <work> ⇒ 预登记在
        #   <work>/.cache/xcheck/ ⇒ ⇒ 少了这一层 ⇒ 工具**找不到预登记** ⇒ 基线崩
        work = os.path.join(tmp, "work")
        os.makedirs(os.path.join(work, ".cache"))
        shutil.copytree(HERE, os.path.join(work, ".cache", "r244"),
                        ignore=shutil.ignore_patterns("__pycache__", "._*"))
        for sub in ("xcheck", "mutbak"):
            s = os.path.join(REPO, ".cache", sub)
            if os.path.isdir(s):
                shutil.copytree(s, os.path.join(work, ".cache", sub),
                                ignore=shutil.ignore_patterns("__pycache__", "._*"))
        tdir = os.path.join(work, ".cache", "r244")
        rc, out = run_selftest(tdir)
        print("基线（真实数据）：rc=%s" % rc)
        if rc != 0:
            print(out[-3000:])
            print("⛔ 基线不绿 ⇒ 先修基线，台架不许跑")
            return 2
        print("")

        # ---- ⚖⚠⚖ **阳性对照**：先证明台架**能**判红（⛔ 否则「存活」不算数）
        if not _positive_control(tdir):
            return 3
        print("")

        for mid, needle, repl, expect, why in MUTATIONS:
            if only is not None and mid not in only:
                continue
            n_hit = src0.count(needle)
            if n_hit != 1:
                invalid.append((mid, n_hit, why))
                print("[SKIP] %s 落点串命中 %d 处 ⇒ 变异**无效**（%s）" % (mid, n_hit, why))
                continue
            mut = src0.replace(needle, repl, 1)
            # ⚖ 等价变异检测：切完若**逐字节**没变 ⇒ 那是 no-op ⇒ 记成「无效」
            if mut == src0:
                invalid.append((mid, 0, "等价变异（no-op）：" + why))
                print("[SKIP] %s 切完与原文**逐字节相同** ⇒ 等价变异，**无效**" % mid)
                continue
            mp = os.path.join(tdir, "fixed_dose_feasible.py")
            io.open(mp, "w", encoding="utf-8").write(mut)
            # ⚖⚠⚖⚖⚖ **这里必须跑 `tdir`**（= 变异体**真正所在**的目录）
            #   ⇒ 第一版写成 `tmp` ⇒ 跑的是一个**不存在**的文件 ⇒ 全判「存活」
            try:
                rc, out = run_selftest(tmp)      # ⚖ **复现件**：退回第一版的那一处
            except subprocess.TimeoutExpired:
                crashed.append((mid, why))
                print("[CRASH] %s 崩了（超时）（⚠ 崩 ≠ 抓到）" % mid)
                continue
            if _looks_like_crash(out):
                crashed.append((mid, why))
                print("[CRASH] %s 崩了（语法/异常）（⚠ 崩 ≠ 抓到）" % mid)
                print("         %s" % out.strip().splitlines()[-1][:120])
                continue
            fails = parse_fails(out)
            if rc != 0 and expect in fails:
                caught.append(mid)
                print("[CAUGHT] %s ⇒ %s 红（%s）" % (mid, expect, why))
            elif _looks_like_bench_side_error(out):
                crashed.append((mid, why))
                print("[CRASH] %s **子进程没跑起来**（台架自己的错，⛔ 不是「变异存活」）" % mid)
                print("         %s" % (out.strip().splitlines() or [""])[-1][:160])
            elif rc == 0:
                survived.append((mid, why))
                print("[SURVIVED] %s 期望 %s 红，实际**全绿** ⇒ **变异存活**（%s）"
                      % (mid, expect, why))
            else:
                survived.append((mid, why))
                print("[SURVIVED] %s 期望 %s 红，实际红了 %s（不是期望那条）⇒ **变异存活**"
                      % (mid, expect, fails))
                for ln in (out or "").strip().splitlines()[-8:]:
                    print("         | %s" % ln[:160])
        # ⚖ 还原原版（⛔ 别把变异留在盘上）
        shutil.copyfile(TARGET, os.path.join(tdir, "fixed_dose_feasible.py"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    n_run = len(caught) + len(survived) + len(crashed)
    print("变异台：抓住 %d / %d" % (len(caught), n_run))
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived), [s[0] for s in survived]))
    if invalid:
        print("⚠ 无效变异 %d 条：%s" % (len(invalid), [s[0] for s in invalid]))
    if crashed:
        print("⚠ 崩了 %d 条：%s" % (len(crashed), [c[0] for c in crashed]))
    if only is not None:
        print("（本次只跑了 %s）" % ",".join(sorted(only)))
    return 0 if (len(caught) == n_run and not invalid and not crashed) else 1


if __name__ == "__main__":
    sys.exit(main())
