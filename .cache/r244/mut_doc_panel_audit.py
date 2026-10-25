#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_doc_panel_audit.py —— 244.96 的**变异台**：每条判据**必须能红**。

⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_PANEL_PREREG.md` §4（MU-H1..MU-H10 ＋ 期望红闸门）。
   ⛔ **期望值一律手写在本文件里**（⛔ 不从被检对象/上一轮输出里推导）
   ⇒ ⇒ 否则「期望」会跟着「实现」一起变 ⇒ ⇒ 恒绿 ⇒ ⇒ 没有闸门能抓。

⚖ **三类期望**（沿用 244.94/244.95 的成规）：
   · **gate**：某闸门**必须红**（可多闸门：预登记写了几个就都得红）；
   · **equiv**：输出与基线**逐字节相同**（等价变异 ⇒ 记「无效」⇒ ⛔ 不计入分母）
     ⚖ **equiv 同时是「留白被量到」的证据**：改动落在**弱 token**上 ⇒ ⇒
        没有任何判据会红 ⇒ ⇒ 输出逐字节相同 ⇒ ⇒ 弱 token 那条留白被**实证**；
   · **selftest**：改**检查器夹具** ⇒ ⇒ 检查器的 `--selftest` **必须红**
     ⇒ ⇒ 证明自检不是恒绿的。

⚖⚖⚖ **预登记期望 vs 实测**：两条都记；**不一致就如实计数**（MUT_PREREG_MISMATCH），
   ⛔ **不改实现去迁就期望**、⛔ **不改预登记**。

⚖ **零 GPU**、⛔ 不跑批、⛔ **不改任何被测文件**（只在 /dev/shm 的副本上变异）。
"""

import io
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.environ.get("MUT_TARGET", ".cache/r244/doc_panel_audit.py")
WORK = os.environ.get("MUT_WORK", "/dev/shm/_mut24496")
LEDGER = os.environ.get("MUT_LEDGER", ".cache/xcheck/R6_RERUN_PREREG.md")
PAGE = os.environ.get("MUT_PAGE", ".cache/r244/_page_24496.md")
PY = os.environ.get("MUT_PY", sys.executable)

# ================================================================ 变异表
# ⚖⚖⚖ `expect` = (mode, gates, prereg_gates, aux_min)
#    mode: "gate"｜"equiv"｜"selftest"
#    gates: **期望红的闸门**（mode="gate"；多个 ⇒ 都得红）
#    prereg_gates: **预登记 §4 写的**期望红闸门（None = 预登记没写这条）
# ⚖⚖⚖ MU-H1..MU-H10 的 prereg_gates **逐条照抄预登记 §4**，⛔ 不许自己改。
MUTATIONS = [
    ("MU-H1", "页面 P2 的 +30.36 改成 +30.37（改一位）", "page",
     lambda t: _mut_row(t, "P2", lambda l: l.replace("+30.36", "+30.37", 1)),
     ("gate", ("E3",), ("E3",), 0)),
    ("MU-H2", "页面 P11 的 p 值 0.394094 改成 0.394095（末位 +1）", "page",
     lambda t: _mut_row(t, "P11", lambda l: l.replace("0.394094", "0.394095", 1)),
     ("gate", ("E3",), ("E3",), 0)),
    ("MU-H3", "页面 P11 的 p 值改成 **7 位小数** 0.3940944"
              "（⇒ E3 仍绿、**只有 E4 能抓** ⇒ 这正是 E4 存在的理由）", "page",
     lambda t: _mut_row(t, "P11", lambda l: l.replace("0.394094", "0.3940944", 1)),
     ("gate", ("E4",), ("E4",), 0)),
    ("MU-H4", "页面 P28 的「破口 10 个」改成「破口 11 个」", "page",
     lambda t: _mut_row(t, "P28", lambda l: l.replace("破口 10 个", "破口 11 个", 1)),
     ("gate", ("E5", "E6"), ("E5", "E6"), 0)),
    ("MU-H5", "页面 P28 的引用**删掉** `:42278`", "page",
     lambda t: _mut_row(t, "P28", lambda l: l.replace("`:42278`、", "", 1)),
     ("gate", ("E5", "E6"), ("E5", "E6"), 0)),
    ("MU-H6", "页面 P29 的量词「个」改回「处」", "page",
     lambda t: _mut_row(t, "P29", lambda l: l.replace("破口 10 个", "破口 10 处", 1)),
     ("gate", ("E6",), ("E6",), 0)),
    ("MU-H7", "页面 P12 的 p 值改成 **7 位小数** 0.7098421（⇒ 只有 E4 能抓）", "page",
     lambda t: _mut_row(t, "P12", lambda l: l.replace("0.709842", "0.7098421", 1)),
     ("gate", ("E4",), ("E4",), 0)),
    ("MU-H8", "页面**删掉一行** P（P29）", "page",
     lambda t: _mut_drop_row(t, "P29"),
     ("gate", ("E1",), ("E1",), 0)),
    ("MU-H9", "页面 P2 的引用改成越界的 `:99999`", "page",
     lambda t: _mut_row(t, "P2", lambda l: l.replace("`:41404`", "`:99999`", 1)),
     ("gate", ("E2",), ("E2",), 0)),
    ("MU-H10", "页面 P28 的派生分数 4/12 改成 5/12", "page",
     lambda t: _mut_row(t, "P28", lambda l: l.replace("4/12", "5/12", 1)),
     ("gate", ("E7",), ("E7",), 0)),
    # ---- 实现期新增（**预登记 §4 里没有** ⇒ prereg_gates=None ⇒ 如实登记）----
    ("MU-H11", "**等价**：改「复算」列 RC-8a → RC-8b（该列不在任何判据的作用域内）", "page",
     lambda t: _mut_row(t, "P1", lambda l: l.replace("| RC-8a |", "| RC-8b |", 1)),
     ("equiv", None, None, 0)),
    ("MU-H12", "**弱 token 留白的实证**：改 P5 的 n_perm=20000 → 20001"
               "（弱 token 本轮⛔ 不判 ⇒ ⇒ 没有任何闸门会红 ⇒ 输出应**逐字节相同**）", "page",
     lambda t: _mut_row(t, "P5", lambda l: l.replace("n_perm=20000", "n_perm=20001", 1)),
     ("equiv", None, None, 0)),
    ("MU-H13", "**自检层**：把检查器夹具里的值改坏 ⇒ ⇒ 检查器 `--selftest` 必须红",
     "selftest", None, ("selftest", None, None, 0)),
]


def _mut_row(text, pid, fn):
    """⚖ 只改**那一行**（⛔ 不许增删行 ⇒ ⛔ 不许改行号 ⇒ ⇒ 账本引用仍指同一行）。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        if l.startswith("| **%s** |" % pid):
            out.append(fn(l))
            hit += 1
        else:
            out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 页面里 **%s** 命中 %d 行（期望恰好 1 行）⇒ 中止" % (pid, hit))
    return "\n".join(out)


def _mut_drop_row(text, pid):
    out = []
    hit = 0
    for l in text.split("\n"):
        if l.startswith("| **%s** |" % pid):
            hit += 1
            continue
        out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 页面里 **%s** 命中 %d 行（期望恰好 1 行）⇒ 中止" % (pid, hit))
    return "\n".join(out)


# ⚖ MU-H13（自检层）：改**检查器源码里夹具账本**的那一行
#    ⇒ ⇒ 夹具的数与夹具页面的数不再一致 ⇒ ⇒ 某条判据必须红 ⇒ ⇒ 自检必须红
#    ⚖⚖⚖ `replace(…, 1)` 命中的是**源码里第一处**（= 夹具账本那一行，⛔ 不是夹具页面那一行）
#    ⚖⚖⚖ 挑的是 **L1 的基线值**：29 行夹具全引 `:1` 且 token 是 `0.5`
#    ⇒ ⇒ 把它改成 0.600000 ⇒ ⇒ 「0.5」不再逐位出现 ⇒ ⇒ **全绿夹具 T1 必须红**
MU_H13_OLD = "L1 有 **0.500000** 的数"
MU_H13_NEW = "L1 有 **0.600000** 的数"


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def parse_keys(out):
    """⚖ 解析 AUDIT_KEYS 段 ⇒ ⇒ {CHECK_E1: PASS/FAIL, …} ＋ VERDICT ＋ 计数。"""
    keys = {}
    in_block = False
    for l in out.split("\n"):
        s = l.strip()
        if s == "===== AUDIT_KEYS =====":
            in_block = True
            continue
        if s == "===== END_AUDIT_KEYS =====":
            in_block = False
            continue
        if in_block and "=" in l:
            k, v = l.split("=", 1)
            keys[k.strip()] = v.strip()
    return keys


def run_checker(page_path, ledger_path, target=None):
    cmd = [PY, target or TARGET, "--data", "--page", page_path, "--ledger", ledger_path]
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
    """⚖ 去掉**头部路径行**后的输出正文（⇒ ⇒ 等价时不把路径差异当判定差异）。"""
    keep = []
    for l in out.split("\n"):
        s = l.strip()
        if s.startswith("页面：") or s.startswith("账本："):
            continue
        keep.append(l)
    return "\n".join(keep)


def main():
    if not os.path.isdir(WORK):
        os.makedirs(WORK, exist_ok=True)
    page_text = read_text(os.path.join(REPO, PAGE))
    ledger_text = read_text(os.path.join(REPO, LEDGER))

    base_page = os.path.join(WORK, "base_page.md")
    base_led = os.path.join(WORK, "base_ledger.md")
    write_text(base_page, page_text)
    write_text(base_led, ledger_text)

    rc0, out0 = run_checker(base_page, base_led)
    k0 = parse_keys(out0)
    print("基线：rc=%d ｜ VERDICT=%s ｜ CHECKS_RED=%s"
          % (rc0, k0.get("VERDICT"), k0.get("CHECKS_RED")))
    if k0.get("VERDICT") != "A":
        print("⛔ 基线**不是绿**（改后页面应形态 A）⇒ ⇒ 变异台没有可用的基线 ⇒ 中止")
        print("===== AUDIT_KEYS =====")
        print("MUT_RC=2")
        print("===== END_AUDIT_KEYS =====")
        return 2
    base_body = body(out0)

    caught = []
    survivors = []
    crashed = []
    equivalent_ok = []
    equivalent_bad = []
    nored_ok = []
    nored_bad = []
    mismatch = []
    data_judged = 0
    ledger_judged = 0
    selftest_judged = 0

    for mid, desc, target, fn, expect in MUTATIONS:
        mode, gates, prereg_gates, aux_min = expect
        tag = "[%s] %-7s %s" % (mid, mode, desc)

        # ---- 自检层 ----
        if mode == "selftest":
            src = read_text(os.path.join(REPO, TARGET))
            if MU_H13_OLD not in src:
                print("⛔ %s：源码里找不到夹具串 %r ⇒ 中止" % (mid, MU_H13_OLD))
                crashed.append(mid)
                continue
            tgt = os.path.join(WORK, "mut_target_%s.py" % mid)
            write_text(tgt, src.replace(MU_H13_OLD, MU_H13_NEW, 1))
            rc, sout = run_selftest(tgt)
            selftest_judged += 1
            if rc != 0:
                caught.append(mid)
                print("  ✅ %s ⇒ 自检红（rc=%d）⇒ 判据有牙齿" % (tag, rc))
            else:
                survivors.append(mid)
                print("  ⛔ %s ⇒ 自检**仍绿** ⇒ 它抓不住夹具被改坏" % tag)
            continue

        # ---- 页面 / 账本层 ----
        mp = os.path.join(WORK, "mut_%s_page.md" % mid)
        ml = os.path.join(WORK, "mut_%s_ledger.md" % mid)
        if target == "page":
            write_text(mp, fn(page_text))
            write_text(ml, ledger_text)
            data_judged += 1
        else:
            write_text(mp, page_text)
            write_text(ml, fn(ledger_text))
            ledger_judged += 1

        try:
            rc, out = run_checker(mp, ml)
        except Exception as e:                       # noqa: BLE001
            print("  ⛔ %s ⇒ 跑挂了：%s" % (tag, e))
            crashed.append(mid)
            continue

        if rc not in (0, 1):
            crashed.append(mid)
            print("  ⛔ %s ⇒ 返回码异常 rc=%d" % (tag, rc))
            continue

        keys = parse_keys(out)
        red = sorted([c for c in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")
                      if keys.get("CHECK_%s" % c) == "FAIL"])

        if mode == "gate":
            want = tuple(gates)
            ok = all(g in red for g in want)
            if ok:
                caught.append(mid)
                print("  ✅ %s ⇒ 判红 %s（期望含 %s）" % (tag, red, list(want)))
            else:
                survivors.append(mid)
                print("  ⛔ %s ⇒ **没**判红 %s（期望含 %s）⇒ ⇒ 这条判据抓不住它"
                      % (tag, red, list(want)))
            if prereg_gates is not None and tuple(sorted(prereg_gates)) != tuple(sorted(want)):
                mismatch.append(mid)
                print("      ⚠ 预登记期望 %s ≠ 台里写的 %s" % (list(prereg_gates), list(want)))
        elif mode == "equiv":
            same = (body(out) == base_body)
            if same:
                equivalent_ok.append(mid)
                print("  ✅ %s ⇒ 输出与基线**逐字节相同**（等价变异 ⇒ 记「无效」）" % tag)
            else:
                equivalent_bad.append(mid)
                print("  ⛔ %s ⇒ 输出**变了** ⇒ 它**不是**等价变异" % tag)
        elif mode == "nored":
            if not red:
                nored_ok.append(mid)
                print("  ✅ %s ⇒ 无闸门红（留白实证）" % tag)
            else:
                nored_bad.append(mid)
                print("  ⛔ %s ⇒ 竟然判红了 %s ⇒ 期望写错" % (tag, red))

    print("")
    print("===== AUDIT_KEYS =====")
    print("MUT_N=%d" % len(MUTATIONS))
    print("MUT_CAUGHT=%d" % len(caught))
    print("MUT_SURVIVORS=%d" % len(survivors))
    print("MUT_CRASHED=%d" % len(crashed))
    print("MUT_EQUIV_OK=%d" % len(equivalent_ok))
    print("MUT_EQUIV_BAD=%d" % len(equivalent_bad))
    print("MUT_NORED_OK=%d" % len(nored_ok))
    print("MUT_NORED_BAD=%d" % len(nored_bad))
    print("MUT_PREREG_MISMATCH=%d" % len(mismatch))
    print("MUT_DATA_JUDGED=%d" % data_judged)
    print("MUT_LEDGER_JUDGED=%d" % ledger_judged)
    print("MUT_SELFTEST_JUDGED=%d" % selftest_judged)
    print("MUT_PREREG_N=%d" % sum(1 for _m, _d, _t, _f, e in MUTATIONS if e[2] is not None))
    print("MUT_RC=%d" % (0 if (not survivors and not crashed and not equivalent_bad
                              and not nored_bad and not mismatch) else 1))
    print("===== END_AUDIT_KEYS =====")
    return 0 if (not survivors and not crashed and not equivalent_bad
                 and not nored_bad and not mismatch) else 1


if __name__ == "__main__":
    sys.exit(main())
