#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_doc_dose_curve_audit.py —— 变异台（244.97）：预登记 §4 + §8.3 的 **14 条**变异必须**每条都被判过**。

⚖⚖⚖ **本轮验证的是「页面 §6.2.2 的留白块 ⇔ 账本可溯源」这条链**：
   · **E3 / E4**：每个断言必须**逐位**出现在**它自己引用的那一行**里（⛔ 不许跨行借用）；
   · **E5 / E6**：**留白守卫**（正向：必须写「未量到」；反向：⛔ 不许把「未量到」写成「无差异/已量到」）；
   · **E1 / E2 / E7**：结构、出处存在、每行至少 1 项命中。
   ⇒ ⇒ 本台的核心是 **MU-C1..MU-C14**，其中 **MU-C6** 是本轮**如实登记的 1 处不符**（预登记 §8.2）。

⚖⚖⚖ **期望闸门一律手写**（⛔ **不从实现派生** ⇒ ⇒ 否则「两边一起变」⇒ ⇒ 恒绿）。
⚖ 每条变异有**三个落点**：① **页面层** ② **账本层** ③ **等价层**。
⚖ **等价变异**（`mode="equiv"`）⇒ ⇒ 判定结果必须与**基线逐字节相同**。
⚖ **崩的条数必须是 0**；**存活（没被抓住）的条数必须是 0**。

⚖⚖⚖ **纪律**：预登记写的「期望红闸门」与**实测**不符时 ⇒ ⇒ **如实登记**（打印 + 计数）
   ⇒ ⇒ ⛔ **不改实现去迁就期望**、⛔ **不改预登记**。

⚖ **用法**（远端）：
   MUT_TARGET=… MUT_WORK=… MUT_LEDGER=… MUT_PAGE=… python3 mut_doc_dose_curve_audit.py
"""

import io
import os
import subprocess
import sys

TARGET = os.environ.get("MUT_TARGET", ".cache/r244/doc_dose_curve_audit.py")
WORK = os.environ.get("MUT_WORK", "/dev/shm/_mut24497")
LEDGER = os.environ.get("MUT_LEDGER", ".cache/xcheck/R6_RERUN_PREREG.md")
PAGE = os.environ.get("MUT_PAGE", ".cache/r244/_page_24497.md")
PY = os.environ.get("MUT_PY", sys.executable)

CHECKS = ("E1", "E2", "E3", "E4", "E5", "E6", "E7")

# ⚖⚖⚖ **页面行的定位锚**（按行首前缀 ⇒ ⇒ 精确落在它该落的那一行）
P_B1 = "- 本批 `n_bands = 1`"
P_B2 = "- 分层剂量要**真阶梯**"
P_B3 = "- ⚠⚖⚖ **口径要点**"
P_TITLE = "### 6.2.2 "


def _mut_line(text, prefix, fn):
    """⚖ 精确定位**一行**（行首前缀）⇒ ⇒ 只改这一行 ⇒ ⇒ 负控不连坐。"""
    out = []
    hit = 0
    for l in text.split("\n"):
        if l.startswith(prefix):
            out.append(fn(l))
            hit += 1
        else:
            out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 前缀 %r 命中 %d 行（期望恰好 1 行）⇒ 中止" % (prefix, hit))
    return "\n".join(out)


def _del_line(text, prefix):
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


def _insert_after(text, prefix, new_line):
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


# ================================================================ 变异表
# ⚖⚖⚖ `expect` = (mode, gate, prereg_gate)
#    mode: "gate"（期望那些闸门红）｜ "equiv"（期望与基线逐字节相同）
#    gate: **我手写**的期望红闸门（元组；全部要红）
#    prereg_gate: **预登记 §4 / §8.3 写的**期望红闸门（元组；全部要红 ⇒ 否则记「不符」）
MUTATIONS = [
    ("MU-C1", "B1 删掉 `:41513`（D1 补的出处又没了）", "page",
     lambda t: _mut_line(t, P_B1, lambda l: l.replace("、`:41513`", "", 1)),
     "gate", ("E3",), ("E3",)),
    ("MU-C2", "B3 删掉 `:41327`（D2 补的出处又没了）", "page",
     lambda t: _mut_line(t, P_B3, lambda l: l.replace("、`:41327`", "", 1)),
     "gate", ("E4",), ("E4",)),
    ("MU-C3", "B3 把三个 token 写回**压缩式**", "page",
     lambda t: _mut_line(t, P_B3,
                         lambda l: l.replace("（`pos_frac=0.25` / `pos_frac=0.50` / `pos_frac=0.75`）",
                                             "（`pos_frac = 0.25 / 0.50 / 0.75`）", 1)),
     "gate", ("E4",), ("E4",)),
    ("MU-C4", "B1 把「不是「无剂量效应」」改成「无剂量效应」（**去掉否定**）", "page",
     lambda t: _mut_line(t, P_B1,
                         lambda l: l.replace("（⛔ **不是**「无剂量效应」）", "（⛔ 无剂量效应）", 1)),
     "gate", ("E5", "E6"), ("E5", "E6")),
    ("MU-C5", "B1 把「剂量趋势未量到」改成「剂量趋势已量到」", "page",
     lambda t: _mut_line(t, P_B1,
                         lambda l: l.replace("**剂量趋势未量到**", "**剂量趋势已量到**", 1)),
     "gate", ("E3", "E6"), ("E3", "E6")),
    ("MU-C6", "B2 把 `:41656` 改成 `:41657`（**空行**，⛔ 不越界）", "page",
     lambda t: _mut_line(t, P_B2, lambda l: l.replace("`:41656`", "`:41657`", 1)),
     "gate", ("E3",), ("E2",)),
    ("MU-C7", "B3 把「3 个 `pos_frac`」改成「4 个 `pos_frac`」", "page",
     lambda t: _mut_line(t, P_B3,
                         lambda l: l.replace("**3 个 `pos_frac` 档的合池**",
                                             "**4 个 `pos_frac` 档的合池**", 1)),
     "gate", ("E3",), ("E3",)),
    ("MU-C8", "在 §6.2.2 里插一句「剂量—响应曲线**已量到**，斜率为 0」", "page",
     lambda t: _insert_after(t, P_B3, "  ⇒ ⇒ 剂量—响应曲线**已量到**，斜率为 0"),
     "gate", ("E6",), ("E6",)),
    ("MU-C9", "把 §6.2.2 的标题去掉「未量到」", "page",
     lambda t: _mut_line(t, P_TITLE,
                         lambda l: l.replace("剂量—响应曲线（**未量到**）", "剂量—响应曲线", 1)),
     "gate", ("E1",), ("E1",)),
    ("MU-C10", "删掉中间那个 bullet（B2）", "page",
     lambda t: _del_line(t, P_B2),
     "gate", ("E1", "E7"), ("E1", "E7")),
    ("MU-C11", "B2 把 `:41656` 改成 `:99999`（**真越界**）", "page",
     lambda t: _mut_line(t, P_B2, lambda l: l.replace("`:41656`", "`:99999`", 1)),
     "gate", ("E2",), ("E2",)),
    ("MU-C12", "**等价**：改 B2 里「244.72 的 D5 审计已证」这个**不参与任何判据**的补充说明", "page",
     lambda t: _mut_line(t, P_B2,
                         lambda l: l.replace("244.72 的 D5 审计已证", "244.72 的 D5 审计证明", 1)),
     "equiv", (), ()),
    ("MU-C13", "在 §6.2.2 里插一句「剂量—响应曲线**已量到**（见 6.2.1）」（括号在**后面**）", "page",
     lambda t: _insert_after(t, P_B3, "  ⇒ ⇒ 剂量—响应曲线**已量到**（见 6.2.1）"),
     "gate", ("E6",), ("E6",)),
    ("MU-C14", "**账本层**：把账本 `:41656` 里的「切穿复制组」改坏", "ledger",
     lambda t: _mut_ledger(t, "**分层剂量的真阶梯**", "切穿复制组", "穿透复制组"),
     "gate", ("E3",), ("E3",)),
]


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def parse_keys(out):
    """⚖ 解析 AUDIT_KEYS 段 ⇒ ⇒ {CHECK_E1: PASS/FAIL, …} ＋ VERDICT ＋ N_*。"""
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

    # ---- 基线：未变异的页面必须**全绿**，否则整个变异台没有意义 ----
    base_page = os.path.join(WORK, "baseline.md")
    write_text(base_page, page_text)
    rc, out = run_checker(base_page, LEDGER)
    base_keys = parse_keys(out)
    out_base = body(out)
    base_red = sorted(c for c in CHECKS if base_keys.get("CHECK_" + c) == "FAIL")
    print("[基线] rc=%d VERDICT=%s 红闸门=%s ｜ bullet=%s ｜ 断言=%s ｜ 命中=%s ｜ 缺口=%s"
          % (rc, base_keys.get("VERDICT"), base_red,
             base_keys.get("N_BULLETS"), base_keys.get("N_ASSERT"),
             base_keys.get("N_HIT"), base_keys.get("N_MISS")))
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
    mismatch = []
    data_judged = 0
    ledger_judged = 0

    for mid, desc, where, fn, mode, gate, prereg_gate in MUTATIONS:
        print("")
        print("---- %s：%s（落点 %s）----" % (mid, desc, where))
        print("     手写期望：mode=%s ｜ 期望红闸门=%s ｜ 预登记写的=%s"
              % (mode, list(gate),
                 list(prereg_gate) if prereg_gate else "（等价）"))
        if mode == "equiv":
            try:
                eq_page = fn(page_text)
            except SystemExit as e:
                print("⛔ 变异本身构造失败：%s" % e)
                crashed.append(mid)
                continue
            p = os.path.join(WORK, "mut_%s.md" % mid)
            write_text(p, eq_page)
            rc, out = run_checker(p, LEDGER)
            if rc == 2 or "PRECOND_FAIL" in out or "Traceback" in out:
                print("[CRASH] 被检实现崩了（rc=%d）⇒ ⇒ 不算「抓到」" % rc)
                crashed.append(mid)
                continue
            if body(out) == out_base:
                equivalent_ok += 1
                print("[PASS] 等价变异：输出与基线**逐字节相同**")
            else:
                equivalent_bad.append(mid)
                print("[FAIL] 等价变异：输出与基线**不同** ⇒ ⇒ 判定被无关改动影响")
            continue

        if where == "page":
            data_judged += 1
            try:
                bad_page = fn(page_text)
            except SystemExit as e:
                print("⛔ 变异本身构造失败：%s" % e)
                crashed.append(mid)
                continue
            p = os.path.join(WORK, "mut_%s.md" % mid)
            write_text(p, bad_page)
            cmd_page, cmd_ledger = p, LEDGER
        else:
            ledger_judged += 1
            try:
                bad_ledger = fn(ledger_text)
            except SystemExit as e:
                print("⛔ 变异本身构造失败：%s" % e)
                crashed.append(mid)
                continue
            p = os.path.join(WORK, "mut_%s_ledger.md" % mid)
            write_text(p, bad_ledger)
            cmd_page, cmd_ledger = PAGE, p

        rc, out = run_checker(cmd_page, cmd_ledger)
        if rc == 2 or "PRECOND_FAIL" in out or "Traceback" in out:
            print("[CRASH] 被检实现崩了（rc=%d）⇒ ⇒ 不算「抓到」" % rc)
            crashed.append(mid)
            continue
        keys = parse_keys(out)
        red = sorted(c for c in CHECKS if keys.get("CHECK_" + c) == "FAIL")
        miss_gates = [g for g in gate if g not in red]
        if miss_gates:
            survivors.append(mid)
            print("[FAIL] 期望红闸门 %s **没红**（实际红闸门 %s）" % (list(gate), red))
            continue
        caught += 1
        extra = [c for c in red if c not in gate]
        print("[PASS] 期望红闸门 %s **已红**（实际红闸门 %s%s）"
              % (list(gate), red, "；额外红闸门（连坐）：%s" % extra if extra else ""))
        miss_prereg = [g for g in prereg_gate if g not in red]
        if miss_prereg:
            mismatch.append("%s：预登记期望红闸门 %s，实际红闸门 %s"
                            % (mid, list(prereg_gate), red))

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
    print("MUT_PREREG_MISMATCH=%d" % len(mismatch))
    print("MUT_DATA_JUDGED=%d" % data_judged)
    print("MUT_LEDGER_JUDGED=%d" % ledger_judged)
    print("MUT_RC=%d" % (0 if (not survivors and not crashed and not equivalent_bad) else 1))
    print("===== END_AUDIT_KEYS =====")
    return 0 if (not survivors and not crashed and not equivalent_bad) else 1


if __name__ == "__main__":
    sys.exit(main())
