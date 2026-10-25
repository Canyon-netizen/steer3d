#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_doc_dose_arm_rand_audit.py —— 变异台（244.95）：预登记 §4 的 **9 条**变异必须**每条都被判过**。

⚖⚖⚖ **本轮验证的是「244.94 的两条留白 ⇒ 变成了真闸门」**：
   · **E6**（rand 臂列逐字一致）与 **E7**（一一对应）是 244.94 的**辅助测量**升格成的**真判据**；
   ⇒ ⇒ 本台的核心是 **MU-F1 / MU-F2 / MU-F3 / MU-F4**（它们分别打 E6/E6/E6/E7）
   ⇒ ⇒ 其中 **MU-F2 正是 244.94 的 MU-E3**（那时**没有任何闸门红**）⇒ ⇒ 现在**必须有牙齿**。

⚖⚖⚖ **期望闸门一律手写**（⛔ **不从实现派生** ⇒ ⇒ 否则「两边一起变」⇒ ⇒ 恒绿）。
⚖ 每条变异有**三个落点**：① **页面层** ② **账本层** ③ **自检层**。
⚖ **等价变异**（`mode="equiv"`）⇒ ⇒ 判定结果必须与**基线逐字节相同**。
⚖ **无闸门变异**（`mode="nored"`）⇒ ⇒ 期望**没有任何闸门变红**。
⚖ **崩的条数必须是 0**；**存活（没被抓住）的条数必须是 0**。

⚖⚖⚖ **纪律**：预登记写的「期望红闸门」与**实测**不符时 ⇒ ⇒ **如实登记**（打印 + 计数）
   ⇒ ⇒ ⛔ **不改实现去迁就期望**、⛔ **不改预登记**。

⚖ **用法**（远端）：
   MUT_TARGET=… MUT_WORK=… MUT_LEDGER=… MUT_PAGE=… python3 mut_doc_dose_arm_rand_audit.py
"""

import io
import os
import re
import subprocess
import sys

TARGET = os.environ.get("MUT_TARGET", ".cache/r244/doc_dose_arm_rand_audit.py")
WORK = os.environ.get("MUT_WORK", "/dev/shm/_mut24495")
LEDGER = os.environ.get("MUT_LEDGER", ".cache/xcheck/R6_RERUN_PREREG.md")
PAGE = os.environ.get("MUT_PAGE", ".cache/r244/_page_24494.md")
PY = os.environ.get("MUT_PY", sys.executable)

CHECKS = ("E1", "E2", "E3", "E4", "E5", "E6", "E7")

# ⚖⚖⚖ **页面行的定位锚**（按行首前缀 ⇒ ⇒ 精确落在它该落的那一行）
ROW_NORM = "| 注入前范数（float64 口径）"
ROW_L2 = "| 逐格注入场 L2（"
ROW_ALPHA = "| α 网格"
ROW_READ = "| 判决读数 α"
ROW_STATIC = "| 静态命令行"
HDR_621 = "| 量 | w 臂 | rand 臂 | 差 / 判据 | 账本位置 | 复算 |"
HDR_623 = "| 展品 | 实测 | 账本位置 | 复算 |"


def _mut_row(text, prefix, fn, contains=None):
    """⚖ 精确定位**一行**（行首前缀 ＋ 可选「还要含某串」）⇒ ⇒ 只改这一行 ⇒ ⇒ 负控不连坐。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        if l.startswith(prefix) and (contains is None or contains in l):
            out.append(fn(l))
            hit += 1
        else:
            out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 前缀 %r（还要含 %r）命中 %d 行（期望恰好 1 行）⇒ 中止"
                         % (prefix, contains, hit))
    return "\n".join(out)


def _del_row(text, prefix):
    """⚖ 删掉**一整行**（按行首前缀）⇒ ⇒ 命中必须恰好 1 行。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        if l.startswith(prefix):
            hit += 1
            continue
        out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 前缀 %r 命中 %d 行（期望恰好 1 行）⇒ 中止" % (prefix, hit))
    return "\n".join(out)


def _dup_row(text, prefix):
    """⚖ 把**一行复制**一份（紧跟原行）⇒ ⇒ 命中必须恰好 1 行。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        out.append(l)
        if l.startswith(prefix):
            out.append(l)
            hit += 1
    if hit != 1:
        raise SystemExit("⛔ 前缀 %r 命中 %d 行（期望恰好 1 行）⇒ 中止" % (prefix, hit))
    return "\n".join(out)


def _insert_after_row(text, prefix, new_line):
    """⚖ 在**某一行之后**插入一行（不改动别处）⇒ ⇒ 命中必须恰好 1 行。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        out.append(l)
        if l.startswith(prefix):
            out.append(new_line)
            hit += 1
    if hit != 1:
        raise SystemExit("⛔ 前缀 %r 命中 %d 行（期望恰好 1 行）⇒ 中止" % (prefix, hit))
    return "\n".join(out)


# ================================================================ 变异表
# ⚖⚖⚖ `expect` = (mode, gate, prereg_gate, aux_min)
#    mode: "gate"（期望该闸门红）｜ "equiv"（期望与基线逐字节相同）｜ "nored"（期望无闸门红）
#    gate: 期望红的闸门（mode="gate" 时）；None 表示不指定
#    prereg_gate: **预登记 §4 写的**期望红闸门（None = 预登记写的是「等价」）
#    aux_min: 期望辅助测量至少量到多少（mode="nored" 时用）
MUTATIONS = [
    ("MU-F1", "把页面 rand 臂的**实际值**改错一位（:41607 那行）", "page",
     lambda t: _mut_row(t, ROW_NORM, lambda l: l.replace("0.99999999999999989", "0.99999999999999988", 1)),
     ("gate", "E6", "E6", 0)),
    ("MU-F2", "把页面 rand 臂的「同」改成「异」（= 244.94 的 MU-E3 同款）", "page",
     lambda t: _mut_row(t, ROW_ALPHA, lambda l: l.replace("| 同 |", "| 异 |", 1)),
     ("gate", "E6", "E6", 0)),
    ("MU-F3", "**账本侧**：把账本该行 rand 臂的**实际值**改错一位", "ledger",
     lambda t: _mut_ledger(t, "| 注入前范数（float64 口径） |", "0.99999999999999989", "0.99999999999999988"),
     ("gate", "E6", "E6", 0)),
    ("MU-F4", "把两个页行的出处改成**同一行**", "page",
     lambda t: _mut_row(t, ROW_STATIC, lambda l: l.replace("`:41615`", "`:41614`", 1)),
     ("gate", "E7", "E7", 0)),
    ("MU-F5", "把某行的出处改成**表外**的一行", "page",
     lambda t: _mut_row(t, ROW_L2, lambda l: l.replace("`:41614`", "`:41602`", 1)),
     ("gate", "E3", "E3", 0)),
    ("MU-F6", "把某行 w 臂的数改错", "page",
     lambda t: _mut_row(t, ROW_NORM, lambda l: l.replace("6.429e-10", "6.429e-11", 1)),
     ("gate", "E1", "E1", 0)),
    ("MU-F7", "把某页行的 rand 臂从「同」改成**账本里的实际值**（**合法**方向）", "page",
     lambda t: _mut_row(t, ROW_READ,
                        lambda l: l.replace("| 同 |", "| `[56.73720169067383, 113.47440338134766]` |", 1)),
     ("nored", None, None, 0)),
    ("MU-F8", "改「复算」列（RC-6 → RC-7）——该列不在任何判据的作用域内", "page",
     lambda t: _mut_row(t, ROW_ALPHA, lambda l: l.replace("| RC-6 |", "| RC-7 |", 1)),
     ("equiv", None, None, 0)),
    ("MU-F9", "**夹具层**：把夹具的 rand 值改坏", "selftest", None,
     ("selftest", None, None, 0)),
]


def _mut_ledger(text, marker, old, new):
    """⚖ 账本侧变异：在**含 `marker` 的那一行**里把 `old` 换成 `new`（⛔ 行号不许变 ⇒ ⛔ 不许增删行）。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        if (marker in l) and (old in l):
            out.append(l.replace(old, new, 1))
            hit += 1
        else:
            out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 账本里含 %r 且含 %r 的行命中 %d 行（期望恰好 1 行）⇒ 中止"
                         % (marker, old, hit))
    return "\n".join(out)


# ⚖ MU-F9（自检层）：把**夹具账本**第 4 行的 **rand 值**改错一位
#    ⇒ ⇒ 夹具的 rand 与夹具页面的 rand 不再一致 ⇒ ⇒ **E6 必须红** ⇒ ⇒ 正控 S0 必须红
#    ⇒ ⇒ 「夹具的 rand 与真账本同形」这件事被守住。
#    ⚖⚖⚖ `replace(…, 1)` 命中的是**源码里第一处**（= 夹具账本那一行，⛔ 不是夹具页面那一行）
#    ⇒ ⇒ 负控**精确**落在「账本侧」。
MU_F9_OLD = "0.22222222222222222"
MU_F9_NEW = "0.22222222222222223"


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def parse_keys(out):
    """⚖ 解析 AUDIT_KEYS 段 ⇒ ⇒ {CHECK_E1: PASS/FAIL, …} ＋ VERDICT ＋ AUX_*。"""
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
    ledger_text = read_text(LEDGER)
    src_text = read_text(TARGET)

    # ---- 基线：未变异的页面必须**全绿**，否则整个变异台没有意义 ----
    base_page = os.path.join(WORK, "baseline.md")
    write_text(base_page, page_text)
    rc, out = run_checker(base_page, LEDGER)
    base_keys = parse_keys(out)
    out_base = body(out)
    base_red = sorted(c for c in CHECKS if base_keys.get("CHECK_" + c) == "FAIL")
    print("[基线] rc=%d VERDICT=%s 红闸门=%s ｜ AUX_RAND_MISMATCH=%s ｜ AUX_BIJ=%s/%s"
          % (rc, base_keys.get("VERDICT"), base_red,
             base_keys.get("AUX_RAND_MISMATCH"), base_keys.get("AUX_BIJ"),
             base_keys.get("AUX_BIJ_TOTAL")))
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
    nored_ok = 0
    nored_bad = []
    mismatch = []
    data_judged = 0
    ledger_judged = 0
    selftest_judged = 0

    for mid, desc, where, fn, expect in MUTATIONS:
        mode, gate, prereg_gate, aux_min = expect
        print("")
        print("---- %s：%s（落点 %s）----" % (mid, desc, where))
        print("     手写期望：mode=%s ｜ 期望红闸门=%s ｜ 预登记写的=%s"
              % (mode, gate,
                 prereg_gate if prereg_gate
                 else ("（等价）" if mode == "equiv"
                       else ("（不该红）" if mode == "nored" else "（无）"))))
        if where in ("page", "ledger"):
            if where == "page":
                data_judged += 1
            else:
                ledger_judged += 1
            try:
                if where == "page":
                    bad_page = fn(page_text)
                    p = os.path.join(WORK, "mut_%s.md" % mid)
                    write_text(p, bad_page)
                    cmd_page, cmd_ledger = p, LEDGER
                else:
                    bad_ledger = fn(ledger_text)
                    p = os.path.join(WORK, "mut_%s_ledger.md" % mid)
                    write_text(p, bad_ledger)
                    cmd_page, cmd_ledger = PAGE, p
            except SystemExit as e:
                print("⛔ 变异本身构造失败：%s" % e)
                crashed.append(mid)
                continue
            rc, out = run_checker(cmd_page, cmd_ledger)
            if rc == 2 or "PRECOND_FAIL" in out or "Traceback" in out:
                print("[CRASH] 被检实现崩了（rc=%d）⇒ ⇒ 不算「抓到」" % rc)
                crashed.append(mid)
                continue
            keys = parse_keys(out)
            red = sorted(c for c in CHECKS if keys.get("CHECK_" + c) == "FAIL")
            aux_rand = int(keys.get("AUX_RAND_MISMATCH", "0") or 0)
            if mode == "equiv":
                if body(out) == out_base:
                    equivalent_ok += 1
                    print("[PASS] 等价变异：输出与基线**逐字节相同**（红闸门 %s）" % red)
                else:
                    equivalent_bad.append(mid)
                    print("[FAIL] 等价变异：输出与基线**不同** ⇒ ⇒ 判定被无关改动影响")
                continue
            if mode == "nored":
                if red:
                    nored_bad.append(mid)
                    print("[FAIL] 期望**无闸门红**，实际红了 %s ⇒ ⇒ 这条不是「留白实证」" % red)
                    continue
                if aux_rand < aux_min:
                    nored_bad.append(mid)
                    print("[FAIL] 期望辅助测量至少量到 %d，实际 AUX_RAND_MISMATCH=%d"
                          % (aux_min, aux_rand))
                    continue
                nored_ok += 1
                if aux_min:
                    print("[PASS] **无闸门红** ＋ 辅助测量量到 %d 处 rand 列不符 ⇒ ⇒ 「留白」被**量到**了"
                          % aux_rand)
                else:
                    print("[PASS] **无闸门红**（且**预期**没有 rand 列不符：aux=%d）⇒ ⇒ 合法方向，闸门**没有误判**"
                          % aux_rand)
                if prereg_gate:
                    mismatch.append("%s：预登记期望红闸门 %s，实测**无闸门红**（E2 是**条件式**判据："
                                    "只在页面写「同」时才查）" % (mid, prereg_gate))
                continue
            # ---- mode == "gate" ----
            if gate and gate in red:
                caught += 1
                extra = [c for c in red if c != gate]
                print("[PASS] 期望红闸门 %s **已红**（实际红闸门 %s%s）"
                      % (gate, red, "；额外红闸门（连坐）：%s" % extra if extra else ""))
                if prereg_gate and prereg_gate not in red:
                    mismatch.append("%s：预登记期望红闸门 %s，实际红闸门 %s" % (mid, prereg_gate, red))
            else:
                survivors.append(mid)
                print("[FAIL] 期望红闸门 %s **没红**（实际红闸门 %s）" % (gate, red))
        else:
            selftest_judged += 1
            if MU_F9_OLD not in src_text:
                print("⛔ 源码里找不到 MU-F9 的锚点串 ⇒ 中止")
                crashed.append(mid)
                continue
            bad_src = src_text.replace(MU_F9_OLD, MU_F9_NEW, 1)
            p = os.path.join(WORK, "mut_%s.py" % mid)
            write_text(p, bad_src)
            rc, out = run_selftest(p)
            failed = [l for l in out.split("\n") if l.startswith("[FAIL]")]
            if rc == 0:
                print("[FAIL] 夹具改成不同形后**自检仍全绿** ⇒ ⇒ 夹具与真账本「同形」这件事**没被守住**")
                survivors.append(mid)
            else:
                caught += 1
                gate_hit = any("S0 " in l for l in failed)
                print("[PASS] 自检**变红**（rc=%d）｜ 正控 S0 命中=%s ｜ 实际红用例 %s"
                      % (rc, gate_hit, [l[:46] for l in failed]))
                if not gate_hit:
                    print("⚠ 正控 S0 **没**在红用例里 ⇒ ⇒ 如实登记")

    print("")
    print("=" * 70)
    print("变异 %d 条 ｜ 抓住 %d ｜ 存活 %d ｜ 崩 %d ｜ 等价变异通过 %d ｜ 等价变异异常 %d"
          % (len(MUTATIONS), caught, len(survivors), len(crashed),
             equivalent_ok, len(equivalent_bad)))
    print("无闸门预期（留白实证）通过 %d ｜ 异常 %d" % (nored_ok, len(nored_bad)))
    if survivors:
        print("存活（没被抓住）：%s" % survivors)
    if crashed:
        print("崩：%s" % crashed)
    if equivalent_bad:
        print("等价变异异常：%s" % equivalent_bad)
    if nored_bad:
        print("无闸门预期异常：%s" % nored_bad)
    if mismatch:
        print("⚖⚖⚖ **预登记期望与实测不符（如实登记，⛔ 不改实现去迁就期望）**：")
        for m in mismatch:
            print("  · %s" % m)
    print("")
    print("===== AUDIT_KEYS =====")
    print("MUT_N=%d" % len(MUTATIONS))
    print("MUT_CAUGHT=%d" % caught)
    print("MUT_SURVIVORS=%d" % len(survivors))
    print("MUT_CRASHED=%d" % len(crashed))
    print("MUT_EQUIV_OK=%d" % equivalent_ok)
    print("MUT_EQUIV_BAD=%d" % len(equivalent_bad))
    print("MUT_NORED_OK=%d" % nored_ok)
    print("MUT_NORED_BAD=%d" % len(nored_bad))
    print("MUT_PREREG_MISMATCH=%d" % len(mismatch))
    print("MUT_DATA_JUDGED=%d" % data_judged)
    print("MUT_LEDGER_JUDGED=%d" % ledger_judged)
    print("MUT_SELFTEST_JUDGED=%d" % selftest_judged)
    print("MUT_RC=%d" % (0 if (not survivors and not crashed and not equivalent_bad
                              and not nored_bad) else 1))
    print("===== END_AUDIT_KEYS =====")
    return 0 if (not survivors and not crashed and not equivalent_bad and not nored_bad) else 1


if __name__ == "__main__":
    sys.exit(main())
