#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mut_fixed_dose_density_audit.py —— `fixed_dose_density_audit.py` 的**变异台**。

⚖⚠⚖⚖⚖ **纪律**（从 244.70 / 244.71 的台架继承，一条都不许放松）：
   ① 每条变异只改**一处**源码（⛔ 改多处 ⇒ 抓到了也不知道是哪一处抓的）
   ② 每条变异必须**恰好命中 1 处**（⛔ 命中 0 或 >1 ⇒ 这条变异**无效** ⇒ 必须报出来）
   ③ 「什么都没变」（等价变异）必须记成**无效**，⛔ **不是**「存活**
   ④ ⛔ **「崩」≠「抓到」** ⇒ 崩了要单独报（⇒ 崩的条数必须压到 **0**）
   ⑤ 判据的**期望集不许从被检对象派生** ⇒ 期望的「哪条自检用例该红」是**手写**的
   ⑥ ⚖ **阳性对照**先过：往台架**真正会跑的那个目录**里放一个「必定红」的假目标
      ⇒ 台架必须抓到它 ⇒ 抓不到 ⇒ 台架**自己**瞎了 ⇒ 下面的「存活」一律不算数 ⇒ 直接退出
   ⑦ ⛔ 崩溃识别认**任何** `*Error` / `*Exception` / `Traceback`

⚖⚖⚖⚖⚖ **本台架要抓的四类错**（244.72 的重点）：
   ① **判据被改成恒真**（D1–D5 任一条）⇒ ⇒ 「核清单」变成「盖印章」
   ② ⚠⚠⚖⚖⚖ **密度定义被换成 `n_eff` 那一支**（M9）⇒ ⇒ ⇒ **244.72 查出的那条
      「校验器口径 vs 生产口径」的断层被焊回去** ⇒ ⇒ 判据必须抓得到
      （⛔ 这条是本台架**最要紧**的一条：它守的正是本轮的核心发现）
   ③ **供给判据被改成恒真**（D4）⇒ ⇒ 现有阶梯供不出也会说「供得出」
   ④ **前提被抹掉 / 诊断行被抹掉**（D7 / D6）⇒ ⇒ 「未量到」被当成已测过、
      「印出实测离散」这句话变成**说谎**

⚖⚠⚖⚖⚖⚖ **工作目录怎么搭**（244.71 的教训）：被检工具会**顺带 import 同目录的既有机械**
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
TARGET = os.path.join(HERE, "fixed_dose_density_audit.py")

# ⚖ `[FAIL]` 行的用例号：只允许字母/数字/下划线（⛔ 不用贪婪的 `\S+`）
FAIL_RE = re.compile(u"^\\[FAIL\\] ([A-Za-z0-9_]+)\uff1a", re.M)

# ⚖ 子进程**崩**了的形状（⛔ 任何 `*Error` / `*Exception` / Traceback 都算）
CRASH_RE = re.compile(
    r"^(Traceback \(most recent call last\)|\w*(?:Error|Exception)\b)", re.M)

# ⚖ (编号, 落点串, 替换串, 期望红的自检用例, 说明)
MUTATIONS = [
    ("M1", "ok2 = (not mixed) and bool(by_tid)", "ok2 = True", "T2",
     "D2（复制格密度相等）被改成恒真 ⇒ 密度混了也不红"),
    ("M2", "ok3 = bool(dens) and not off", "ok3 = True", "T3",
     "D3（每格密度落 frac±tol）被改成恒真 ⇒ 剂量没钉死也不红"),
    ("M3", "ok4 = (not supply_miss) and bool(supply_miss is not None)",
     "ok4 = True", "T4c",
     "D4（供给）被改成恒真 ⇒ 现有阶梯供不出也会说「供得出」"),
    ("M4", "ok5 = not split_tids", "ok5 = True", "T5",
     "D5（分析断层：复制格被拆档）被改成恒真 ⇒ 拆开了也不红"),
    ("M5", "ok1 = not uniq_missing", "ok1 = True", "T8",
     "D1（密度算不写得出来）被改成恒真 ⇒ 池外的轨迹也不红"),
    ("M6", "    if not ok7:\n        premises.append(",
     "    if False:\n        premises.append(", "T7c",
     "D7 的「未量到」前提被抹掉 ⇒ 未量到的轴被当成已测过"),
    ("M7", 'put_diag("**两套「剂量分数」定义的档内离散**',
     '_skip = ("**两套「剂量分数」定义的档内离散**', "T6",
     "诊断行被抹掉 ⇒ 「印出实测离散」这句话就成了**说谎**"),
    ("M8", "        if sp > tol:", "        if sp > 1e9:", "T2",
     "D2 的容差被放宽到无穷 ⇒ 密度再乱也不红"),
    ("M9", "    return DC.frac_of(rec)",
     "    return float(n_sites) / float(P + max(1, int(int(n_gen) * 0.5)) - 1)", "T9",
     "⚠⚠⚖⚖⚖ **密度定义被换成「分母不依赖 pos_frac」那一支**（= 校验器那一支的效果）"
     "⇒ ⇒ 244.72 查出的「校验器口径 vs 生产口径」的断层被**焊回去** ⇒ ⇒ 判据必须抓得到"),
    ("M10", "    ok8 = pooled_ok", "    ok8 = False", "T9c",
     "⚖⚠⚖ 244.74：**D8 被改成恒假** ⇒ ⇒ 「这一批在当前管线下算不出判决数」这句话"
     "**无中生有** ⇒ ⇒ T9c 必须红"
     "（⚠ 原来这条是「改成恒真」⇒ 244.74 起 D8 的**正确极性就是绿** ⇒ 那个变异"
     "与正确行为**语义等价** ⇒ 抓不到 ⇒ ⇒ 换成「恒假」这一支）"),
    ("M10b", '                        quantile=conv["quantile"], n_bands=1)',
     '                        quantile=conv["quantile"], n_bands=0)', "T9c",
     "⚠⚠⚖ 244.74：**D8 的探测被改坏**（探 n_bands=0 而不是 1 ⇒ 必抛 ⇒ 合池模式"
     "被判成「没有」）⇒ ⇒ D8 转红 ⇒ ⇒ T9c 必须红"
     "（⚠ 244.76：落点随「口径去写死」改过 ⇒ 边界/分位改成取预登记 ⇒ 断言同步更新）"),
    ("M11", "            if len(hits) != 1:\n                miss.append((tid, pf, len(hits)))",
     "            if False:  # 变异：让供给审计永远不报 miss\n                miss.append((tid, pf, len(hits)))", "T4b",
     "⚠⚠⚖⚖⚖ **供给审计的 miss 列表被改成永远为空** ⇒ ⇒ 「供不出」这件事**测不到** ⇒ ⇒ "
     "T4b（负样：加一个供不出的 pos_frac ⇒ 必须多报 miss）必须抓到 ⇒ ⇒ "
     "（原 T4b 是恒真重言式 ⇒ 恒绿 ⇒ 量不到东西 ⇒ 244.72 改成负样）"),
    ("M12", "            if len(hits) != 1:\n                miss.append((tid, pf, len(hits)))",
     "            if len(hits) != 1:\n                miss.append((tid, pf, len(hits)))", "T4b",
     "⚖ **等价变异验收用例**：替换串 **==** 落点串 ⇒ 文件**逐字节不变** ⇒ ⇒ 必须记成"
     "「**无效**」（⛔ **不是**「存活」）⇒ ⇒ 纪律 ③ 不是 docstring"),
    # ---- 244.76 新增：三条都是「**口径去写死**」这一层的护栏 ----
    ("M13", 'n_bands=int(conv["n_bands"]))',
     'n_bands=4)', "T13a",
     "⚖⚖⚖⚖⚖ 244.76：**D5 的档数被写死回 4**（⛔ 原来就是写死的 ⇒ ⇒ 244.76 刚把它"
     "改成读预登记 ⇒ ⇒ 这条变异把它**焊回去**）⇒ ⇒ 变体预登记（合池）下 D5 必红 ⇒ ⇒ "
     "T13a 必须抓到 ⇒ ⇒ 证明「口径真的来自预登记」"),
    ("M14", "    ok9 = (head_cols == expect_cols)",
     "    ok9 = True", "T11",
     "⚖⚖⚖⚖⚖ 244.76：**D9（表头判据）被改成恒真** ⇒ ⇒ 无表头的清单也会说「表头对」⇒ ⇒ "
     "【9.3】那条「静默吞掉第一格」又变成**测不到** ⇒ ⇒ T11 必须抓到"),
    ("M15", "        raw = F.read_prereg(p)\n        cfg = F.Cfg(raw)",
     "        return {\"n_bands\": 4, \"boundary\": \"prod\", \"quantile\": \"inclusive\",\n"
     "                \"zero_span\": \"keep\", \"prereg\": p}", "T13a",
     "⚖⚖⚖⚖⚖ 244.76：**读预登记那一层被换成写死的字典** ⇒ ⇒ 「口径只写一处」被破坏 ⇒ ⇒ "
     "变体预登记读不到 ⇒ ⇒ T13a 必须抓到（⛔ 兜底 ⇒ 口径被改就看不见了）"),
    ("M16", '    if target is None or tol is None:\n'
     '        raise HardFail("供给审计必须显式给出目标密度与容差（⛔ 不许默认值兜底 ⇒ "\n'
     '                       "剂量口径的真源是**规格**的 `dose.frac` / `dose.tol`）")',
     "    if target is None or tol is None:\n        target, tol = 0.25, 0.005", "T15",
     "⚖⚖⚖ 244.76：**供给审计的「不许兜底」被拆掉** ⇒ ⇒ 剂量口径又变成代码里写死的第二处 ⇒ ⇒ "
     "T15 必须抓到"),
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
        p = subprocess.run([sys.executable, os.path.join(r244dir, "fixed_dose_density_audit.py"),
                            "--selftest"],
                           cwd=workdir, capture_output=True, text=True,
                           timeout=2400, env=env)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"


def _positive_control(workdir):
    """⚖⚖⚖ **阳性对照** ⇒ 抓不到 ⇒ **台架自己瞎了** ⇒ 下面的「存活」一律不算数。"""
    r244dir = os.path.join(workdir, ".cache", "r244")
    src = io.open(os.path.join(r244dir, "fixed_dose_density_audit.py"), encoding="utf-8").read()
    bad = src.replace('chk("T1", v["n_tid"] >= 1,', 'chk("T1", False,')
    if bad == src:
        return False, "阳性对照的落点没找到（夹具变了？）"
    _materialize(r244dir, "fixed_dose_density_audit.py", bad)
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
    ap = argparse.ArgumentParser(description="fixed_dose_density_audit.py 的变异台")
    ap.add_argument("--only", default=None, help="只跑这几条变异（逗号分隔，如 M1,M4）")
    a = ap.parse_args()

    sel = set(a.only.split(",")) if a.only else None
    muts = [m for m in MUTATIONS if (sel is None or m[0] in sel)]

    # ---- ① 阳性对照**先过**（⛔ 不过 ⇒ 下面的「存活」不算数 ⇒ 直接退出）
    work = tempfile.mkdtemp(prefix="mutden_")
    try:
        r244dir = _link_tree(work)
        _materialize(r244dir, "fixed_dose_density_audit.py")
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
        work = tempfile.mkdtemp(prefix="mutden_%s_" % mid)
        try:
            r244dir = _link_tree(work)
            src = io.open(TARGET, encoding="utf-8").read()
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
            _materialize(r244dir, "fixed_dose_density_audit.py", mutated)
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
