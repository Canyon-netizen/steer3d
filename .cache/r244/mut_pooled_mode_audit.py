#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_pooled_mode_audit.py —— `pooled_mode_audit.py` 的**变异台**（244.74）。

⚖⚠⚖⚖⚖ **纪律**（从 244.70 / 244.71 / 244.72 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活」
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`

⚖⚖⚖⚖⚖ **本台架要抓的五类错**（244.74 的重点）：
   ① **合池分支被拆/被改坏**（M1/M2/M3）⇒ ⇒ 「固定剂量」算不出判决数
   ② ⚠⚠⚖⚖⚖ **档数白名单里没有 1**（M4）⇒ ⇒ 预登记写 `n_bands = 1` 时管线直接拒读
   ③ ⚠⚠⚖⚖⚖ **趋势守卫被拆**（M5/M9）⇒ ⇒ 1 档时跑出 p = 1.0
      ⇒ ⇒ **「没测」被渲染成「无差异」**（本台架最要紧的一条）
   ④ **生产口径被改坏**（M6）⇒ ⇒ 「生产路径逐位不变」这条护栏瞎了
   ⑤ **合池下的口径校验 / 轴标注 / 规模措辞被改坏**（M7/M8/M10/M11）

⚖⚠⚖⚖⚖⚖⚖⚖⚖ **本台架与 244.72 那两个的差别**：变异**落在不同文件**上
   （`dose_confound_audit` / `dose_layer_audit` / `fixed_dose_audit`）
   ⇒ ⇒ 台架必须**按文件**把被改的那一份真的放进工作树（⛔ 其余全部指向原件）。

⚖⚠⚖⚖⚖⚖⚖⚖⚖ **工作目录怎么搭**（244.71 的教训）：被检工具会**顺带 import 同目录的既有机械**
   ⇒ ⇒ 只复制被检文件**不够** ⇒ ⇒ 那样会「崩」⇒ ⇒ 而「崩」≠「抓到」⇒ ⇒ **假红**
   ⇒ ⇒ 正确做法：搭一棵**符号链接树**（`.cache/r244`、`.cache/mutbak`、`.cache/xcheck`）
   ⇒ ⇒ 只把**被改的那一个文件**真的复制进去 ⇒ ⇒ 其余全部指向原件 ⇒ ⇒ 快且完整。
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
TOOL = "pooled_mode_audit.py"

# ⚖ `[FAIL]` 行的用例号：只允许字母/数字/下划线（⛔ 不用贪婪的 `\S+`）
#   ⚠ 本工具的自检打印 `[FAIL] T2 消息`（**半角空格**）⇒ ⇒ 这里两种分隔符都收
FAIL_RE = re.compile(u"^\\[FAIL\\] ([A-Za-z0-9_]+)[\\s\uff1a]", re.M)

# ⚖ 子进程**崩**了的形状（⛔ 任何 `*Error` / `*Exception` / Traceback 都算）
CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 目标文件, 落点串, 替换串, 期望红的自检用例, 说明)
MUTATIONS = [
    ("M1", "dose_confound_audit.py",
     "    if n_bands == 1:",
     "    if False:  # 变异：合池分支被跳过",
     "T2",
     "⚠⚠⚖ **合池分支被跳过** ⇒ ⇒ `statistics.quantiles(n=1)` 返回**空表** ⇒ `qs[0]` 越界 "
     "⇒ ⇒ 合池模式**不可用** ⇒ ⇒ T2 必须红"),
    ("M2", "dose_confound_audit.py",
     '        return [], [("pooled(合池)", list(ks))]',
     "        return [], []",
     "T2",
     "合池分支返回**空档** ⇒ ⇒ 合池模式下**一档都没有** ⇒ ⇒ T2 必须红"),
    ("M3", "dose_confound_audit.py",
     '        return [], [("pooled(合池)", list(ks))]',
     '        return [], [("pooled(合池)", list(ks)[:-1])]',
     "T3",
     "⚠⚠⚖ **合池档漏掉一格** ⇒ ⇒ 判决的**分母被悄悄改小** ⇒ ⇒ T3 必须红（守恒破了）"),
    ("M4", "dose_confound_audit.py",
     "N_BANDS_CHOICES = (1, 3, 4, 5)",
     "N_BANDS_CHOICES = (3, 4, 5)",
     "T7",
     "⚠⚠⚖⚖⚖ **档数白名单里没有 1** ⇒ ⇒ 预登记写 `n_bands = 1` 时管线**直接拒读** ⇒ ⇒ "
     "T7 必须红"),
    ("M5", "dose_layer_audit.py",
     "    if n_layer < 2:",
     "    if False:  # 变异：趋势守卫被拆",
     "T4",
     "⚠⚠⚖⚖⚖ **趋势守卫被拆** ⇒ ⇒ 1 档时 `trend_weights(1) = [0]` ⇒ 统计量恒 0 ⇒ "
     "**p = 1.0** ⇒ ⇒ 「没测」被渲染成「无差异」⇒ ⇒ T4 必须红"),
    ("M6", "dose_confound_audit.py",
     'bands = [("frac<=q1", [r for r, f2 in zip(ks, fr) if f2 <= qs[0]])]',
     'bands = [("frac<q1", [r for r, f2 in zip(ks, fr) if f2 <= qs[0]])]',
     "T1",
     "⚠⚠⚖ **生产口径的档名被改** ⇒ ⇒ 「生产路径逐位不变」这条护栏瞎了 ⇒ ⇒ T1 必须红"),
    ("M7", "dose_confound_audit.py",
     "    if quantile not in QUANTILE_METHODS_EXT:",
     "    if False:  # 变异：口径取值的前置校验被拆",
     "T6",
     "⚠⚠⚖ **合池下的坏口径取值被静默接受**（合池根本不参与分位 ⇒ 校验一拆就漏）⇒ ⇒ "
     "T6 必须红"),
    ("M8", "fixed_dose_audit.py",
     '                            "rho": None if _pooled else _rho,',
     '                            "rho": _rho,',
     "T9",
     "⚠⚠⚖⚖⚖ **合池下的 rho 不标「未量到」** ⇒ ⇒ 印出来的数会被读成「剂量无关联」⇒ ⇒ "
     "T9 必须红"),
    ("M9", "dose_layer_audit.py",
     '"剂量趋势**未量到**（⛔ 不是 p=1.0，也不是「无差异」）"',
     '"剂量趋势**没趋势**（⛔ 不是 p=1.0，也不是「无差异」）"',
     "T4",
     "⚠⚠⚖⚖⚖ **守卫的理由词被换掉**（「未量到」→「没趋势」）⇒ ⇒ 「未量到」与「无差异」"
     "在**措辞**上分不开了 ⇒ ⇒ T4 必须红"),
    ("M10", "dose_layer_audit.py",
     "    if n_layer == 1:",
     "    if False:  # 变异：合池措辞被拆",
     "T12",
     "⚠⚠⚖ **合池下还印 4 档的措辞**（「阶梯要扫到现在的 N 倍」）⇒ ⇒ 把「不需要扫阶梯」"
     "渲染成「要扫 N 倍」⇒ ⇒ T12 必须红"),
    ("M11", "dose_confound_audit.py",
     "    if n_bands < 1:",
     "    if n_bands < 0:",
     "T5",
     "⚠⚠⚖ `n_bands = 0` 的闸被放宽 ⇒ ⇒ 抛的**不是** `HardFail`（是 `StatisticsError`）⇒ ⇒ "
     "崩 ⛔ 不算按判据转红 ⇒ ⇒ T5 必须红"),
    ("M12", "dose_confound_audit.py",
     '        return [], [("pooled(合池)", list(ks))]',
     '        return [], [("pooled(合池)", list(ks))]',
     "T2",
     "⚖ **等价变异验收用例**：替换串 **==** 落点串 ⇒ 文件**逐字节不变** ⇒ ⇒ 必须记成"
     "「**无效**」（⛔ **不是**「存活」）⇒ ⇒ 纪律 ③ 不是 docstring"),
]


def parse_fails(out):
    return FAIL_RE.findall(out or "")


def _link_tree(root):
    """⚖ 搭一棵**符号链接树**（`.cache/r244`、`.cache/mutbak`、`.cache/xcheck`）。"""
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
    bad = src.replace('chk("T1", ok1 and', 'chk("T1", False and')
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
    ap = argparse.ArgumentParser(description="pooled_mode_audit.py 的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔，如 M1,M4）")
    a = ap.parse_args()

    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**（⛔ 不过 ⇒ 下面的「存活」不算数 ⇒ 直接退出）
    work = tempfile.mkdtemp(prefix="mutpool_")
    try:
        r244dir = _link_tree(work)
        _materialize(r244dir, TOOL)
        ok, msg = _positive_control(work)
        print("台架阳性对照：%s ⇒ %s" % ("rc=?" if not ok else "过", msg))
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

    for mid, fname, anchor, repl, expect, why in muts:
        work = tempfile.mkdtemp(prefix="mutpool_%s_" % mid)
        try:
            r244dir = _link_tree(work)
            src = io.open(os.path.join(HERE, fname), encoding="utf-8").read()
            n = src.count(anchor)
            if n != 1:
                invalid_anchor.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                print("[无效] %s：落点命中 %d 次 ⇒ 这条变异**无效**（不是「存活」）" % (mid, n))
                continue
            mutated = src.replace(anchor, repl)
            # ⚖⚖⚖ **纪律 ③（244.72 补实现）**：等价变异 = 替换后文件**逐字节不变**
            #   ⇒ ⇒ 必须记成「**无效**」（⛔ **不是**「存活」）⇒ ⇒ 否则纪律 ③ 只是 docstring
            #   ⇒ ⇒ （⛔ 等价变异**不算失败** —— 它是示范用例；「锚点命中 ≠ 1」才算失败）
            if mutated == src:
                invalid_equiv.append((mid, why, "替换后文件逐字节相同 ⇒ 等价变异 ⇒ 无效"))
                print("[无效] %s：替换后文件**逐字节不变** ⇒ 这条是**等价变异** ⇒ 记「无效」"
                      "（⛔ 不是「存活」）" % mid)
                continue
            _materialize(r244dir, fname, mutated)
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
            print("    %s：%s（实际红了 %r）" % (mid, why, fails))
    if crashed:
        print("⚠ 崩了 %d 条：%s" % (len(crashed), [c[0] for c in crashed]))
        for mid, why, tail in crashed:
            print("    %s：%s ⇒ %s" % (mid, why, tail))
    if invalid_anchor:
        print("⚠ 无效变异 %d 条（锚点命中 ≠ 1）：%s" % (len(invalid_anchor), [i[0] for i in invalid_anchor]))
        for mid, why, tail in invalid_anchor:
            print("    %s：%s ⇒ %s" % (mid, why, tail))
    if invalid_equiv:
        print("⚖ 等价变异 %d 条（替换后**逐字节不变** ⇒ 记「无效」⇒ ⛔ **不是**「存活」）：%s"
              % (len(invalid_equiv), [i[0] for i in invalid_equiv]))
        for mid, why, tail in invalid_equiv:
            print("    %s：%s ⇒ %s" % (mid, why, tail))
    # ⚖ 分母 = **真正落上去**的变异数（等价变异与落点失效都**不计入**）
    _applied = len(muts) - len(invalid_equiv) - len(invalid_anchor)
    print("变异台：抓住 %d / %d（等价变异 %d 条 ⇒ 记「无效」⇒ 不计入分母）"
          % (len(caught), _applied, len(invalid_equiv)))
    return 0 if (not survived and not crashed and not invalid_anchor) else 1


if __name__ == "__main__":
    sys.exit(main())
