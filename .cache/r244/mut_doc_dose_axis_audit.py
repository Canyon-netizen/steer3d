#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_doc_dose_axis_audit.py —— 变异台（244.93）：预登记 §4 的 8 条变异必须**每条都被抓住**。

⚖⚖⚖ **期望闸门一律手写**（⛔ **不从实现派生** ⇒ ⇒ 否则「两边一起变」⇒ ⇒ 恒绿）。
⚖ 每条变异有**两个落点**：
   ① **真数据层**（真页面副本 ＋ 真账本）⇒ ⇒ 期望某个**检查项**变红（`expect_check`）；
   ② **自检层**（合成夹具）⇒ ⇒ 期望**自检整体红**（`expect_selftest_red`）。
⚖ **无效（等价）变异**：`expect_check is None` ⇒ ⇒ 判定结果必须与**基线逐字节相同**。
⛔ **崩的条数必须是 0**（变异**不得**让被检实现自己崩；崩了不算「抓到」）。
⛔ **存活（没被抓住）的条数必须是 0**。

⚖ **用法**（远端）：
   MUT_TARGET=… MUT_WORK=… MUT_LEDGER=… MUT_PAGE=… python3 mut_doc_dose_axis_audit.py
"""

import io
import os
import re
import subprocess
import sys

TARGET = os.environ.get("MUT_TARGET", ".cache/r244/doc_dose_axis_audit.py")
WORK = os.environ.get("MUT_WORK", "/dev/shm/_mut24493")
LEDGER = os.environ.get("MUT_LEDGER", ".cache/xcheck/R6_RERUN_PREREG.md")
PAGE = os.environ.get("MUT_PAGE", ".cache/r244/_page_24493.md")
PY = os.environ.get("MUT_PY", sys.executable)

CHECKS = ("D1", "D2", "D3", "D4")

# ⚖⚖⚖ **变异表**（id, 描述, 落点, 变异函数, 期望变红的检查项, 期望变红的自检用例）
#    ⚖ `expect_check` / `expect_selftest_red` **全部手写**（⛔ 不从实现派生）。
#    ⚖ 落点 "data" ⇒ 改**页面副本**；落点 "selftest" ⇒ 改**夹具**（源码里的 FIX_LEDGER）。

ROW_RHO = "| rho（剂量—响应相关）"
ROW_QUANT = "| 注入比例轴的**分位点**"
ROW_FRAGILE = "| **脆性**：**±4 token** 扰动族"
ROW_OUT = "　出处："


def _mut_row(text, prefix, fn, contains=None):
    """⚖ 精确定位**一行**（按行首前缀 ＋ 可选「还要含某串」）⇒ ⇒ 只改这一行 ⇒ ⇒ 负控不连坐。

    ⚖⚖⚖ **为什么要 contains**：页面里**多处**都有「　出处：」行（每节一个）⇒ ⇒ 光靠前缀不唯一
    ⇒ ⇒ 必须再加一个「还要含某串」的约束 ⇒ ⇒ 否则变异会**改错行**（244.93 第一版 MU-D5 就栽在这）。
    """
    out = []
    hit = 0
    for l in text.split("\n"):
        if l.startswith(prefix) and (contains is None or contains in l):
            out.append(fn(l))
            hit += 1
        else:
            out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 前缀 %s（还要含 %r）命中 %d 行（期望恰好 1 行）⇒ 中止"
                         % (prefix, contains, hit))
    return "\n".join(out)


def m_d1(text):
    """MU-D1：把 rho 行里的数改错（+0.691 → +0.692）⇒ ⇒ D1 必须红。"""
    return _mut_row(text, ROW_RHO, lambda l: l.replace("+0.691", "+0.692", 1))


def m_d2(text):
    """MU-D2：把分位点行的出处改成**不含该数**的行 ⇒ ⇒ D1 必须红。"""
    return _mut_row(text, ROW_QUANT,
                    lambda l: l.replace("`:37545`、`:37988`、`:40281`",
                                        "`:38406`、`:38413`", 1))


def m_d3(text):
    """MU-D3：删掉一整行展品 ⇒ ⇒ D2 必须红（锚定不到）。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        if l.startswith(ROW_FRAGILE):
            hit += 1
            continue
        out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 脆性行命中 %d 行（期望 1 行）⇒ 中止" % hit)
    return "\n".join(out)


def m_d4(text):
    """MU-D4：把一行展品**复制**一份 ⇒ ⇒ D2 必须红（不再唯一）。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        out.append(l)
        if l.startswith(ROW_FRAGILE):
            out.append(l)
            hit += 1
    if hit != 1:
        raise SystemExit("⛔ 脆性行命中 %d 行（期望 1 行）⇒ 中止" % hit)
    return "\n".join(out)


def m_d5(text):
    """MU-D5：把口径切换注的出处改成不含 28/27/30/24 的行 ⇒ ⇒ D4 必须红。"""
    return _mut_row(text, ROW_OUT, lambda l: l.replace("`:40404`", "`:38406`", 1),
                    contains="HANDOFF_24478")


def m_d6(text):
    """MU-D6：把口径切换注里的 28/27/30/24 改成 29/27/30/24 ⇒ ⇒ D4 必须红。"""
    return _mut_row(text, "⚖⚖⚖ **口径切换",
                    lambda l: l.replace("**28/27/30/24**", "**29/27/30/24**", 1))


def m_d7(text):
    """MU-D7：引用一个**不存在**的账本行号（> 总行数）⇒ ⇒ D3 必须红。"""
    return _mut_row(text, ROW_FRAGILE,
                    lambda l: l.replace("`:40281`", "`:40281`、`:99999`", 1))


def m_e1(text):
    """MU-E1（**等价变异**，非预登记）：把**复算列**的 `RC-7` 改成 `RC-8`
    ⇒ ⇒ 该列不在任何判据的作用域里 ⇒ ⇒ 判定结果必须与**基线逐字节相同**。"""
    return _mut_row(text, ROW_QUANT, lambda l: l.replace("| RC-7 |", "| RC-8 |", 1))


MUTATIONS = [
    ("MU-D1", "rho 行的数改错（+0.691 → +0.692）", "data", m_d1, "D1", None),
    ("MU-D2", "分位点行的出处换成不含该数的行", "data", m_d2, "D1", None),
    ("MU-D3", "删掉一整行展品", "data", m_d3, "D2", None),
    ("MU-D4", "复制一行展品", "data", m_d4, "D2", None),
    ("MU-D5", "口径切换注的出处换成不含该四档组的行", "data", m_d5, "D4", None),
    ("MU-D6", "口径切换注的四档组改错", "data", m_d6, "D4", None),
    ("MU-D7", "引用不存在的账本行号", "data", m_d7, "D3", None),
    ("MU-E1", "**等价变异**：改复算列（不在作用域内）", "data", m_e1, None, None),
    ("MU-D8", "夹具账本行改成与真账本**不同形**", "selftest", None, None, "S0"),
]

# ⚖ MU-D8：**改夹具**（源码里的 FIX_LEDGER）⇒ ⇒ 把四档组的分隔符从 "/" 改成空格
#    ⇒ ⇒ 那种形状**真账本里不会出现** ⇒ ⇒ 正控 S0 必须红 ⇒ ⇒ 「自检必红」。
MU_D8_OLD = "inclusive 会是 **24/23/22/21**"
MU_D8_NEW = "inclusive 会是 **24 23 22 21**"


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def parse_keys(out):
    """⚖ 解析 AUDIT_KEYS 段 ⇒ ⇒ {CHECK_D1: PASS/FAIL, …} ＋ VERDICT。"""
    keys = {}
    in_block = False
    for l in out.split("\n"):
        if l.strip() == "===== AUDIT_KEYS =====":
            in_block = True
            continue
        if l.strip() == "===== END_AUDIT_KEYS =====":
            in_block = False
            continue
        if in_block and "=" in l:
            k, v = l.split("=", 1)
            keys[k.strip()] = v.strip()
    return keys


def run_checker(page_path, ledger_path):
    """⚖ 跑被检实现（**走真实 CLI 路径**）⇒ ⇒ 返回 (rc, stdout)。"""
    cmd = [PY, TARGET, "--data", "--page", page_path, "--ledger", ledger_path]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.read().decode("utf-8", "replace")
    p.wait()
    return p.returncode, out


def run_selftest(script_path):
    cmd = [PY, script_path, "--selftest"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.read().decode("utf-8", "replace")
    p.wait()
    return p.returncode, out


def body(out):
    """⚖ 去掉**头部路径行**后的输出正文（⇒ ⇒ 比等价时**不把路径差异**当成判定差异）。"""
    keep = []
    for l in out.split("\n"):
        s = l.strip()
        if s.startswith("页面：") or s.startswith("账本："):
            continue
        keep.append(l)
    return "\n".join(keep)


def main():
    if not os.path.isdir(WORK):
        os.makedirs(WORK)
    page_text = read_text(PAGE)
    src_text = read_text(TARGET)

    # ---- 基线：未变异的页面必须**全绿**，否则整个变异台没有意义 ----
    base_page = os.path.join(WORK, "baseline.md")
    write_text(base_page, page_text)
    rc, out = run_checker(base_page, LEDGER)
    base_keys = parse_keys(out)
    out_base = body(out)
    base_red = sorted(c for c in CHECKS if base_keys.get("CHECK_" + c) == "FAIL")
    print("[基线] rc=%d VERDICT=%s 红闸门=%s" % (rc, base_keys.get("VERDICT"), base_red))
    if rc != 0 or base_red:
        print("⛔ 基线不是全绿 ⇒ ⇒ 变异台**无效** ⇒ 中止")
        print("===== AUDIT_KEYS =====")
        print("MUT_RC=2")
        print("===== END_AUDIT_KEYS =====")
        return 2

    caught = 0
    survivors = []
    crashed = []
    equivalent_ok = 0
    equivalent_bad = []
    data_judged = 0
    selftest_judged = 0

    for mid, desc, where, fn, expect_check, expect_gate in MUTATIONS:
        print("")
        print("---- %s：%s（落点 %s）----" % (mid, desc, where))
        if where == "data":
            data_judged += 1
            try:
                bad_page = fn(page_text)
            except SystemExit as e:
                print("⛔ 变异本身构造失败：%s" % e)
                crashed.append(mid)
                continue
            p = os.path.join(WORK, "mut_%s.md" % mid)
            write_text(p, bad_page)
            rc, out = run_checker(p, LEDGER)
            if rc == 2 or "PRECOND_FAIL" in out or "Traceback" in out:
                print("[CRASH] 被检实现崩了（rc=%d）⇒ ⇒ 不算「抓到」" % rc)
                crashed.append(mid)
                continue
            keys = parse_keys(out)
            red = sorted(c for c in CHECKS if keys.get("CHECK_" + c) == "FAIL")
            if expect_check is None:
                # ⚖ **等价变异**：必须与基线**逐字节**相同
                if body(out) == out_base:
                    equivalent_ok += 1
                    print("[PASS] 等价变异：输出与基线**逐字节相同**（红闸门 %s）" % red)
                else:
                    equivalent_bad.append(mid)
                    print("[FAIL] 等价变异：输出与基线**不同** ⇒ ⇒ 判定被无关改动影响")
                continue
            if expect_check in red:
                caught += 1
                extra = [c for c in red if c != expect_check]
                print("[PASS] 期望红闸门 %s **已红**（实际红闸门 %s%s）"
                      % (expect_check, red,
                         "；额外红闸门（连坐）：%s" % extra if extra else ""))
            else:
                survivors.append(mid)
                print("[FAIL] 期望红闸门 %s **没红**（实际红闸门 %s）" % (expect_check, red))
        else:
            selftest_judged += 1
            if MU_D8_OLD not in src_text:
                print("⛔ 源码里找不到 MU-D8 的锚点串 %r ⇒ 中止" % MU_D8_OLD)
                crashed.append(mid)
                continue
            bad_src = src_text.replace(MU_D8_OLD, MU_D8_NEW, 1)
            p = os.path.join(WORK, "mut_%s.py" % mid)
            write_text(p, bad_src)
            rc, out = run_selftest(p)
            failed = [l for l in out.split("\n") if l.startswith("[FAIL]")]
            if rc == 0:
                print("[FAIL] 夹具改成不同形后**自检仍全绿** ⇒ ⇒ 夹具与真账本「同形」这件事**没被守住**")
                survivors.append(mid)
            else:
                caught += 1
                gate_hit = any(expect_gate in l for l in failed) if expect_gate else bool(failed)
                print("[PASS] 自检**变红**（rc=%d）｜ 期望红用例 %s 命中=%s"
                      % (rc, expect_gate, gate_hit))
                if not gate_hit:
                    print("⚠ 实际红用例：%s" % [l[:60] for l in failed])

    print("")
    print("=" * 70)
    print("变异 %d 条 ｜ 抓住 %d ｜ 存活 %d ｜ 崩 %d ｜ 等价变异通过 %d ｜ 等价变异异常 %d"
          % (len(MUTATIONS), caught, len(survivors), len(crashed),
             equivalent_ok, len(equivalent_bad)))
    if survivors:
        print("存活（没被抓住）：%s" % survivors)
    if crashed:
        print("崩：%s" % crashed)
    if equivalent_bad:
        print("等价变异异常：%s" % equivalent_bad)
    print("")
    print("===== AUDIT_KEYS =====")
    print("MUT_N=%d" % len(MUTATIONS))
    print("MUT_CAUGHT=%d" % caught)
    print("MUT_SURVIVORS=%d" % len(survivors))
    print("MUT_CRASHED=%d" % len(crashed))
    print("MUT_EQUIV_OK=%d" % equivalent_ok)
    print("MUT_EQUIV_BAD=%d" % len(equivalent_bad))
    print("MUT_DATA_JUDGED=%d" % data_judged)
    print("MUT_SELFTEST_JUDGED=%d" % selftest_judged)
    print("MUT_RC=%d" % (0 if (not survivors and not crashed and not equivalent_bad) else 1))
    print("===== END_AUDIT_KEYS =====")
    return 0 if (not survivors and not crashed and not equivalent_bad) else 1


if __name__ == "__main__":
    sys.exit(main())
