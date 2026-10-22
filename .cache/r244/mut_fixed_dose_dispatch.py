#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_fixed_dose_dispatch.py —— `fixed_dose_dispatch.py` 的**变异台**。

⚖⚠⚖⚖⚖⚖ **纪律**（从 244.70 / 244.71 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活」
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`

⚖⚠⚖⚖ **本台架的工作目录怎么搭**（244.71 这一轮新踩的坑）：
   被检工具会**顺带 import 同目录的既有机械**（`fixed_dose_feasible` → `fixed_dose_preflight`
   → `fixed_dose_audit` → `dose_layer_audit` → … → `.cache/mutbak/r227_kcurve.py`）
   ⇒ ⇒ 只复制被检文件**不够** ⇒ ⇒ 那样会「崩」⇒ ⇒ 而「崩」≠「抓到」⇒ ⇒ **假红**。
   ⇒ ⇒ 正确做法：搭一棵**符号链接树**（`.cache/r244`、`.cache/mutbak`、`.cache/xcheck`）
   ⇒ ⇒ 只把**被改的那一个文件**真的复制进去 ⇒ ⇒ 其余全部指向原件 ⇒ ⇒ 快且完整。

⚖ **本台架要抓的三类错**：
   ① **判据被改成恒真**（G1–G11 任一条）⇒ ⇒ 「核清单」变成「盖印章」
   ② **前提被抹掉**（G12 的「未量到」那条）⇒ ⇒ 未量到的轴被当成已测过
   ③ **判决方向搞反**（G12 被塞进阻断集 ⇒ 「未量到」被当成「失败」）
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
TARGET = os.path.join(HERE, "fixed_dose_dispatch.py")

# ⚖ `[FAIL]` 行的用例号：只允许字母/数字/下划线（⛔ 不用贪婪的 `\S+`）
FAIL_RE = re.compile(u"^\\[FAIL\\] ([A-Za-z0-9_]+)\uff1a", re.M)

# ⚖ 子进程**崩**了的形状（⛔ 任何 `*Error` / `*Exception` / Traceback 都算）
CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 落点串, 替换串, 期望红的自检用例, 说明)
MUTATIONS = [
    ("M1", 'ok1 = bool(head) and len(head) >= 4 and head[3].strip() == "pos_frac"',
     "ok1 = True", "T2",
     "G1（有 pos_frac 列）被改成恒真 ⇒ 没有 pos_frac 列也不红"),
    ("M2", "ok2 = (not bad_cols) and bool(crows)", "ok2 = True", "T3",
     "G2（每行列数）被改成恒真 ⇒ 列数不对也不红"),
    ("M3", "ok3 = (not mixed) and bool(by_tid)", "ok3 = True", "T4",
     "G3（同轨迹内剂量一致）被改成恒真 ⇒ 剂量混了也不红"),
    ("M4", "ok4b = not not_on_ladder", "ok4b = True", "T5",
     "G4b（n_sites 在自己阶梯上）被改成恒真 ⇒ 剂量档非法也不红"),
    ("M5", "ok4c = (not no_hit) and (not multi_hit)", "ok4c = True", "T5b",
     "G4c（剂量分数命中唯一一档）被改成恒真 ⇒ 档位歧义也不红"),
    ("M6", "ok4d = not wrong_rung", "ok4d = True", "T5c",
     "G4d（清单写的 n_sites 就是那一档）被改成恒真 ⇒ 写错档位也不红"),
    ("M7", "ok5 = (not bad_m) and bool(by_tid)", "ok5 = True", "T7",
     "G5（每条轨迹的格数）被改成恒真 ⇒ 少一格也不红"),
    ("M8", "ok6 = not dup", "ok6 = True", "T8",
     "G6（pos_frac 互不相同）被改成恒真 ⇒ 重复的格也不红"),
    ("M9", "ok7 = len(shapes) <= 1", "ok7 = True", "T9",
     "G7（各轨迹同形）被改成恒真 ⇒ 形状不齐也不红"),
    ("M10", "ok8 = (not bad_num) and not extra", "ok8 = True", "T10",
     "G8（pos_frac ⊆ 规格）被改成恒真 ⇒ 规格外的取值也不红"),
    ("M11", "ok9a = len(tids) == want", "ok9a = True", "T11",
     "G9a（轨迹数）被改成恒真 ⇒ 轨迹不够也不红"),
    ("M12", "ok9b = (k_think == k_ntk) and len(k_think) == n_blocks and not other",
     "ok9b = True", "T19",
     "G9b（think/no_think 成对）被改成恒真 ⇒ 不成对也不红"),
    ("M13", "ok10 = cpt >= need_cells", "ok10 = True", "T12",
     "G10（m≥3 门槛）被改成恒真 ⇒ 格数不够也不红"),
    ("M14", "ok11 = len(good) == per_arm", "ok11 = True", "T13",
     "G11（每臂格数）被改成恒真 ⇒ 总格数不对也不红"),
    ("M15", "    if not ok12:\n        premises.append(",
     "    if False:\n        premises.append(", "T14",
     "G12 的「未量到」前提被抹掉 ⇒ 未量到的轴被当成已测过"),
    ("M16", 'G_BLOCKING = ("G1", "G2", "G3", "G4a", "G4b", "G4c", "G4d", "G5", "G6",\n'
     '              "G7", "G8", "G9a", "G9b", "G10", "G11")',
     'G_BLOCKING = ("G1", "G2", "G3", "G4a", "G4b", "G4c", "G4d", "G5", "G6",\n'
     '              "G7", "G8", "G9a", "G9b", "G10", "G11", "G12")', "T14b",
     "G12 被塞进阻断集 ⇒ 「未量到」被当成「失败」（⇒ 判决方向搞反）"),
    ("M17", "ok4a = not bad_scope", "ok4a = True", "T22",
     "G4a（scope 与规格一致）被改成恒真 ⇒ scope 不符也不红"),
    ("M18", 'out.append("    " + "\\t".join(COLUMNS))   # ⚖⚠⚖ 这行是「模板表头」⇒ 台架 M18 盯着它',
     'out.append("    " + "\\t".join(COLUMNS[:3]))', "T16",
     "模板表头被改成 3 列 ⇒ 印出来的「该长什么样」是错的（⇒ 判据仍绿 ⇒ ⛔ 靠 T16 抓）"),
    ("M19", 'put_diag("**剂量分数的实测跨度**（⛔ **诊断**，⛔ 不参与判决）："',
     '_skip = ("**剂量分数的实测跨度**（⛔ **诊断**，⛔ 不参与判决）："', "T23",
     "诊断行被抹掉 ⇒ 「印出实测跨度」这句话就成了**说谎**（⇒ 靠 T23/T23b 抓）"),
]


def parse_fails(out):
    return FAIL_RE.findall(out or "")


def _link_tree(root):
    """⚖ 搭一棵**符号链接树**（`.cache/r244`、`.cache/mutbak`、`.cache/xcheck`）。
    ⚖⚠⚖ 只把 `skip` 里的文件**真的复制**（其余全部是指向原件的符号链接）
    ⇒ ⇒ 树是完整的（被检工具的 import 链能走通）⇒ ⇒ 又快。"""
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
            if os.path.isdir(src):
                continue
            try:
                os.symlink(src, os.path.join(d, name))
            except OSError:
                shutil.copy2(src, os.path.join(d, name))
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
    """⚖⚠⚖ **必须显式传 `--selftest`** ⇒ ⛔ 不传 ⇒ 工具会印「用法」并 rc=2
    ⇒ ⇒ 阳性对照就会读到「一条 `[FAIL]` 都没有」⇒ ⇒ **台架自己瞎了却报「瞎了」**。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r244dir = os.path.join(workdir, ".cache", "r244")
    try:
        p = subprocess.run([sys.executable, os.path.join(r244dir, "fixed_dose_dispatch.py"),
                            "--selftest"],
                           cwd=workdir, capture_output=True, text=True,
                           timeout=2400, env=env)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def _positive_control(workdir):
    """⚖⚖⚖ **阳性对照**：往台架**真正会跑的那个目录**里放一个「必定红」的假目标。
    ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ **台架自己瞎了** ⇒ 下面的「存活」一律不算数 ⇒ 退出。"""
    r244dir = os.path.join(workdir, ".cache", "r244")
    src = io.open(os.path.join(r244dir, "fixed_dose_dispatch.py"), encoding="utf-8").read()
    bad = src.replace('chk("T1", v["can"],', 'chk("T1", False,')
    if bad == src:
        return False, "阳性对照的落点没找到（夹具变了？）"
    _materialize(r244dir, "fixed_dose_dispatch.py", bad)
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
    ap = argparse.ArgumentParser(description="fixed_dose_dispatch.py 的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔，如 M1,M4）")
    a = ap.parse_args()

    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**（⛔ 不过 ⇒ 下面的「存活」不算数 ⇒ 直接退出）
    work = tempfile.mkdtemp(prefix="mutdisp_")
    try:
        r244dir = _link_tree(work)
        _materialize(r244dir, "fixed_dose_dispatch.py")
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
    invalid = []

    for mid, anchor, repl, expect, why in muts:
        work = tempfile.mkdtemp(prefix="mutdisp_%s_" % mid)
        try:
            r244dir = _link_tree(work)
            src = io.open(TARGET, encoding="utf-8").read()
            n = src.count(anchor)
            if n != 1:
                invalid.append((mid, why, "落点命中 %d 次（必须恰好 1 次）" % n))
                print("[无效] %s：落点命中 %d 次 ⇒ 这条变异**无效**（不是「存活」）" % (mid, n))
                continue
            _materialize(r244dir, "fixed_dose_dispatch.py", src.replace(anchor, repl))
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
        for mid, why, tail in invalid:
            print("    %s：%s ⇒ %s" % (mid, why, tail))
    return 0 if (not survived and not crashed and not invalid) else 1


if __name__ == "__main__":
    sys.exit(main())
