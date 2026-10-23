#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_fixed_dose_cells.py —— `fixed_dose_cells.py` 的**变异台**（244.76）。

⚖⚠⚖⚖⚖ **纪律**（从 244.70–244.75 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活**
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`

⚖⚖⚖⚖⚖ **本台架要抓的六类错**（244.76 的重点）：
   ① **选轨规则**被换成别的（⛔ 事后可挑 ⇒ 样本被动手）⇒ ⇒ 字典序那条必须能分辨
   ② ⚠⚠⚖ **分母不依赖 pos_frac** ⇒ ⇒ 244.72 查出的那道**断层**被焊回去
   ③ **规范取整的夹取**被拆掉 ⇒ ⇒ n_sites 越界
   ④ ⚠⚠⚖⚖ **少乘臂数**（336 − 14 = 322 那个老坑）⇒ ⇒ 「要新跑多少」算错
   ⑤ **表头被去掉** ⇒ ⇒ 【9.3】那条「静默吞第一格」又测不到
   ⑥ **口径一致性判据 / 格数闸 / ρ\* 被改成恒真或写死** ⇒ ⇒ 判据变成盖印章
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
TARGET = os.path.join(HERE, "fixed_dose_cells.py")

# ⚖ `[FAIL]` 行的用例号：只允许字母/数字/下划线（⛔ 不用贪婪的 `\S+`）
FAIL_RE = re.compile(u"^\\[FAIL\\] ([A-Za-z0-9_]+)\uff1a", re.M)

# ⚖ 子进程**崩**了的形状（⛔ 任何 `*Error` / `*Exception` / Traceback 都算）
CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 落点串, 替换串, 期望红的自检用例, 说明)
MUTATIONS = [
    ("N1", "    return ordered[:n_tracks]", "    return ordered[-n_tracks:]", "T4",
     "⚖⚖⚖ **选轨规则被换**（取字典序**最后** N 条 ⇒ 事后可挑 ⇒ 样本被动手）⇒ ⇒ "
     "T4（字典序前 N 条）必须红"),
    ("N2", "    if n < 1:\n        n = 1", "    if n < 1:\n        n = 0", "T2",
     "⚖⚖ **下限夹取被拆掉** ⇒ n_sites 可能取到 0 ⇒ ⇒ T2 必须红"),
    ("N3", '    return DC.denom_of({"inject_n_sites": 1, "P": int(P), "n_gen": int(n_gen),\n'
     '                         "pos_frac": float(pos_frac)})',
     '    return DC.denom_of({"inject_n_sites": 1, "P": int(P), "n_gen": int(n_gen),\n'
     '                         "pos_frac": 0.5})', "T1d",
     "⚠⚠⚖⚖⚖ **分母被改成不依赖 pos_frac** ⇒ ⇒ 244.72 查出的那道**断层**被焊回去 ⇒ ⇒ "
     "T1d 必须红（inj 必须随 pos_frac 变）"),
    ("N4", '    return DC.frac_of({"inject_n_sites": int(n_sites), "P": int(P),\n'
     '                        "n_gen": int(n_gen), "pos_frac": float(pos_frac)})',
     "    return float(n_sites) / float(int(n_gen) * 0.5)", "T3",
     "⚠⚠⚖ **密度不再走生产机械 `frac_of`** ⇒ ⇒ 与分析管线**分叉** ⇒ ⇒ T3 必须红"),
    ("N5", "    reuse_runs = len(reuse_tids) * n_arms", "    reuse_runs = len(reuse_tids)",
     "T12",
     "⚠⚠⚖⚖⚖ **少乘臂数**（336 − 14 = **322** 那个老坑）⇒ ⇒ 「要新跑多少」算错 ⇒ ⇒ "
     "T12（复用/新跑次数逐位对账）必须红"),
    ("N6", '    lines = ["\\t".join(spec["columns"])]', "    lines = []", "T9",
     "⚖⚖⚖ **表头被去掉** ⇒ ⇒ 【9.3】那条「静默吞掉第一格」又变成**测不到** ⇒ ⇒ T9 必须红"),
    ("N7", "    put(\"C1\", not diffs,", "    put(\"C1\", True,", "T6",
     "⚖⚖⚖ **规格/路线一致性判据被改成恒真** ⇒ ⇒ 「两处各写一份」漂了也看不出来 ⇒ ⇒ "
     "T6（漂了必须红）必须红"),
    ("N8", "            cn = canonical_ns(inj, target)\n            d = density_of(",
     "            cn = canonical_ns(inj, 0.25)\n            d = density_of(", "T11",
     "⚖⚖⚖ **ρ\\* 被写死**（⛔ 规格里的 `dose.frac` 就不起作用了）⇒ ⇒ T11（改 ρ\\* 必须改数）必须红"),
    ("N9", "    ok7 = (len(cells) == want_tracks == want_blocks)", "    ok7 = True", "T8b",
     "⚖⚖⚖ **格数闸被改成恒真** ⇒ ⇒ 「格子少了一个」也看不出来 ⇒ ⇒ T8b 必须红"),
    ("N10", "            cn = canonical_ns(inj, target)\n            d = density_of(",
     "            cn = canonical_ns(inj, target) + (5 if pf == route[\"pos_fracs\"][0] else 0)\n"
     "            d = density_of(", "T7",
     "⚖⚖⚖ **某一个 `pos_frac` 的 n_sites 被整体 +5** ⇒ ⇒ 那一档的密度偏离 ρ\\* ⇒ ⇒ "
     "基线不再全绿 ⇒ ⇒ T7（基线必须全绿）必须抓到"),
    ("N11", "    probe_runs = len(cells) * n_arms", "    probe_runs = len(cells) * n_arms",
     "T12",
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
    """⚖ 把被检文件**真的**放进工作树（⛔ 覆盖那个符号链接）⇒ 改的就是它。"""
    p = os.path.join(r244dir, target_name)
    if os.path.islink(p) or os.path.exists(p):
        os.remove(p)
    if text is None:
        shutil.copy2(TARGET, p)
    else:
        io.open(p, "w", encoding="utf-8").write(text)
    return p


def run_selftest(workdir):
    """⚖⚠⚖ **必须显式传 `--selftest`** ⇒ ⛔ 不传 ⇒ 工具会印「用法」并 rc=2。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r244dir = os.path.join(workdir, ".cache", "r244")
    try:
        p = subprocess.run([sys.executable, os.path.join(r244dir, "fixed_dose_cells.py"),
                            "--selftest"],
                           cwd=workdir, capture_output=True, text=True,
                           timeout=2400, env=env)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def _positive_control(workdir):
    """⚖⚖⚖ **阳性对照** ⇒ 抓不到 ⇒ **台架自己瞎了** ⇒ 下面的「存活」一律不算数。"""
    r244dir = os.path.join(workdir, ".cache", "r244")
    src = io.open(os.path.join(r244dir, "fixed_dose_cells.py"), encoding="utf-8").read()
    bad = src.replace('chk("T4", sel == tids[:56]', 'chk("T4", False')
    if bad == src:
        return False, "阳性对照的落点没找到（夹具变了？）"
    _materialize(r244dir, "fixed_dose_cells.py", bad)
    rc, out = run_selftest(workdir)
    fails = parse_fails(out)
    if "T4" not in fails:
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
    ap = argparse.ArgumentParser(description="fixed_dose_cells.py 的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔，如 N1,N4）")
    a = ap.parse_args()

    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**（⛔ 不过 ⇒ 下面的「存活」不算数 ⇒ 直接退出）
    work = tempfile.mkdtemp(prefix="mutcells_")
    try:
        r244dir = _link_tree(work)
        _materialize(r244dir, "fixed_dose_cells.py")
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

    for mid, anchor, repl, expect, why in muts:
        work = tempfile.mkdtemp(prefix="mutcells_%s_" % mid)
        try:
            r244dir = _link_tree(work)
            src = io.open(TARGET, encoding="utf-8").read()
            n = src.count(anchor)
            if n != 1:
                invalid_anchor.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                print("[无效] %s：落点命中 %d 次 ⇒ 这条变异**无效**（不是「存活」）" % (mid, n))
                continue
            mutated = src.replace(anchor, repl)
            # ⚖⚖⚖ **纪律 ③**：等价变异 = 替换后文件**逐字节不变** ⇒ 必须记成「**无效**」
            if mutated == src:
                invalid_equiv.append((mid, why, "替换后文件逐字节相同 ⇒ 等价变异 ⇒ 无效"))
                print("[无效] %s：替换后文件**逐字节不变** ⇒ 这条是**等价变异** ⇒ 记「无效」"
                      "（⛔ 不是「存活」）" % mid)
                continue
            _materialize(r244dir, "fixed_dose_cells.py", mutated)
            rc, out = run_selftest(workdir=work)
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
