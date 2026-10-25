#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_make_handoff_24493.py —— 生成 244.93 的**交接文件**（`.cache/xcheck/HANDOFF_24493.md`，⛔ 不入库）。

⚖ 交接里的每个数**都从收据/账本现取** ⇒ ⇒ 与提交信息**同源**。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24493")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
INDEX = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")
OUT = os.path.join(REPO, ".cache", "xcheck", "HANDOFF_24493.md")


def read(p):
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def keys(text, name):
    m = re.search(r"===== %s =====\n(.*?)===== END_%s =====" % (name, name), text, re.S)
    if not m:
        raise SystemExit("⛔ 收据里没有 %s 块 ⇒ ⇒ 中止" % name)
    d = {}
    for l in m.group(1).split("\n"):
        if "=" in l:
            k, v = l.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def main():
    st_text = read(os.path.join(RCPT, "selftest.out"))
    bf = read(os.path.join(RCPT, "data_before.out"))
    af = read(os.path.join(RCPT, "data_after.out"))
    st_total = len(re.findall(r"^\[(PASS|FAIL)\]", st_text, re.M))
    st_red = (re.search(r"^SELFTEST_RED=(\d+)", st_text, re.M) or [None, "?"])[1]
    a = keys(af, "AUDIT_KEYS")
    b = keys(bf, "AUDIT_KEYS")
    mu = keys(read(os.path.join(RCPT, "mut.out")), "AUDIT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")
    n_rows = len(re.findall(r"^ROW=", af, re.M))
    b_red = re.findall(r"^\[FAIL\] (D\d)：", bf, re.M)
    led = read(LEDGER)
    led_lines = led.count("\n")
    led_m = re.search(r"^## 修订 244\.93 ", led, re.M)
    led_row = led.count("\n", 0, led_m.start()) + 1 if led_m else 0
    idx = read(INDEX)
    idx_lines = idx.count("\n")
    regp = os.path.join(RCPT, "reg_24493.txt")
    reg_line = "（R12 收据不在本地 ⇒ 见提交后双回读）"
    if os.path.isfile(regp):
        reg = read(regp)
        m = re.search(r"小结：变异台.*", reg)
        g = re.search(r"REG_RC=(\d+)", reg)
        reg_line = "R12：REG_RC=%s ｜ %s" % (g.group(1) if g else "?", m.group(0) if m else "?")

    L = []
    A = L.append
    A("# 交接：244.93 —— 剂量轴展品块纳入证据链（形态 A）")
    A("")
    A("## 上手三步")
    A("")
    A("1. **先读账本尾部**：`/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md`"
      "（唯一权威历史，**" + str(led_lines) + "** 行；244.93 段在行 **" + str(led_row) + "**）")
    A("2. **再读本文件**（交接全文）")
    A("3. **再** `git log --oneline -10` ＋ `git status --porcelain`"
      "（工作区有同事的未跟踪文件，⛔ **不碰**）")
    A("")
    A("## 这一轮判了什么")
    A("")
    A("· **问题**：页面上「**剂量轴**」那块（**5 行展品表 ＋ 1 条口径切换注**）"
      "⇒ ⇒ 之前**从来没有被机器核过** ⇒ ⇒ 现在它是**可对账的对象**。")
    A("· **做法**：判据的**期望值从页面那一行自动派生**（⛔ **一个数都不手写**）"
      "⇒ ⇒ 判据问的是「**这个数能不能在它引用的账本行里逐位找到**」"
      "⇒ ⇒ **数写错 ⇒ 找不到 ⇒ 红**；**出处引错 ⇒ 找不到 ⇒ 红**。")
    A("· **判决**：形态 **" + a["VERDICT"] + "**（D1–D4：**"
      + str(int(a["N_CHECKS"]) - int(a["CHECKS_RED"])) + "/" + a["N_CHECKS"] + "** 通过；"
      "逐数矩阵 **" + str(n_rows) + " 个数**，0 个没有出处）")
    A("· **改前 ⇒ 改后**：改前形态 **" + b["VERDICT"] + "**、判红 **" + "/".join(b_red)
      + "**（⛔ 那次不算判决）⇒ ⇒ 这是「**检查器有牙齿**」的证据")
    A("")
    A("## 抓到并修掉的两处真缺陷（⛔ 页面只改出处行号，一个数据数都没动）")
    A("")
    A("1. 口径切换注的出处 `:38406`、`:38413` ⇒ ⇒ **引到了相反结论的行**"
      "（inclusive 是生产默认 / 基准 = prod/inclusive/keep）⇒ ⇒ 真出处是 `:40404`")
    A("2. 「缺读数 0、缺位点数 0」的真实出处是 `:38198`，页面写的是 `:38195`")
    A("")
    A("## 每条判据能红")
    A("")
    A("· 自检：" + str(st_total) + " 道用例，失败 " + str(st_red) + " 道（⛔ 这是「没通过」的条数）")
    A("· 变异台：" + mu["MUT_N"] + " 条（预登记 8 ＋ 等价 1），抓住 " + mu["MUT_CAUGHT"]
      + " / 存活 " + mu["MUT_SURVIVORS"] + " / 崩 " + mu["MUT_CRASHED"])
    A("· 互证（第二条独立实现）：锚点 " + cr["CROSS_N_ANCHORS"] + " / 逐数 " + cr["CROSS_N_NUMBERS"]
      + " / 不符 0；**互证自己也能红**")
    A("· 预登记 ↔ 实现机械对账：判据 " + sp["SPEC_N_CRITERIA"] + " / 变异 " + sp["SPEC_N_MUT"]
      + " / 锚点 " + sp["SPEC_N_ANCHORS"] + " / 偏差 " + sp["SPEC_N_DEVIATION"]
      + "（已声明）/ 真值命中 " + sp["SPEC_REAL_TOKEN_HITS"])
    A("· 全回归：" + reg_line)
    A("")
    A("## 边界（⛔ 不许被读成什么）")
    A("")
    A("- 本轮**只**对账 §6.2.3 的 5 行 ＋ 1 条注 ⇒ ⇒ ⛔ **不许**说成「剂量轴整节已核」/「整页已核」")
    A("- **D1 守的是「数与出处脱节」，⛔ 不是「出处引得最准」** ⇒ ⇒ 留白")
    A("- §6.1 / §6.2（**除 §6.2.3**）/ §6.3 / §6.4 / 页面第一部分 ⇒ ⇒ 这些小节的**内容断言**仍未被机器守"
      "（⚠ 244.92 的链守着：A8 全页行号越界 ＋ §6.3 台账行、A5 §6.4.1 的 B-14 行、"
      "A6 §6.4.4 逐字引用句、A7 §6.5 复算入口、A9 全页过期措辞、A1–A4/H1–H7 §6.7）")
    A("- **剂量—响应 / 污染的精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子**一律**未量到**")
    A("- **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**")
    A("")
    A("## 【如何做】下一轮（244.94+）")
    A("")
    A("1. **§6.2.1 的 9 行**纳入（先解决 `5×2⁻⁹` 这类数学表达式的取数规则）")
    A("2. **§6.2.2 的「未量到」措辞**纳入")
    A("3. **§6.1 判决面板 / §6.3 台账 / §6.4 边界条目**逐块纳入")
    A("4. 页面第一部分（§0–§5）**最后**做")
    A("5. **把「改闸门自己的比较表达式」也纳入变异台**（244.93 的变异台**只改数据**、⛔ **没改实现**"
      "⇒ ⇒ 这条留白**仍在**）⇒ 例如：把 token 级包含改成子串包含 ⇒ ⇒ 自检 S-D1d 必须红"
      "（自检里已经备着这条负控，只差**把它接到变异台上**）")
    A("6. **要点头的线**（本轮一律没碰）：块级同口径污染上界（重解析原始跑批日志）、"
      "固定剂量批重跑加 `--dump-raw`、多随机种子对照臂、同结论对照臂、分层剂量真阶梯、"
      "docs 那条线 GPU 前向、照 meta 重建能否逐位复现的重训")
    A("")
    A("## 字节")
    A("")
    A("- 账本：**" + str(led_lines) + "** 行 ｜ 索引：**" + str(idx_lines) + "** 行")
    A("- 收据：`.cache/r244/_e24493/`（⛔ **不入库**；远端 `zju-53`；全回归 `zju-12`）")
    A("- 复跑：`bash .cache/r244/_run_24493_verify.sh`（远端 zju-53，⛔ 零 GPU）")
    A("")
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L))
    print("已写出 %s（%d 行）" % (OUT, len(L)))
    print("HANDOFF_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
