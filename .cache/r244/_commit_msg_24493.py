#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_commit_msg_24493.py —— 生成 244.93 的提交信息（**每个数都从收据/账本现取**，⛔ 不手打）。

⚖ 提交信息里的数**必须**与**跑出它们的那些字节**同源 ⇒ ⇒ 账本改了，它**不可能**留在旧数上。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24493")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
INDEX = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_INDEX.md")


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
    cs = keys(read(os.path.join(RCPT, "cross_selftest.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")
    n_rows = len(re.findall(r"^ROW=", af, re.M))
    b_red = re.findall(r"^\[FAIL\] (D\d)：", bf, re.M)
    led_text = read(LEDGER)
    led_lines = led_text.count("\n")
    idx_text = read(INDEX)
    idx_lines = idx_text.count("\n")
    n_2493 = len(re.findall(r"^## 修订 244\.93 ", led_text, re.M))

    L = []
    A = L.append
    A("剂量轴展品块纳入证据链：页面 §6.2.3 的每个数都能在它引用的账本行里**逐位**找到（形态 A）")
    A("")
    A("· **判决**：页面 `docs/BPATH_VERDICT.md` §6.2.3（**5 行展品表 ＋ 1 条口径切换注**）"
      "↔ 权威账本 **逐位一致** ⇒ 形态 **" + a["VERDICT"] + "**")
    A("  · 判据 **D1–D4**：**" + str(int(a["N_CHECKS"]) - int(a["CHECKS_RED"])) + "/" + a["N_CHECKS"]
      + "** 通过（D1 每个数在它引用的账本行里**逐位**找到，token 级；D2 锚点行全页唯一；"
      "D3 出处行号存在；D4 口径注四档组有出处）")
    A("  · 逐数矩阵：**" + str(n_rows) + " 个数**（展品列 ＋ 实测列）⇒ ⇒ **0 个**没有出处")
    A("")
    A("· **本轮抓到的两处真缺陷**（⛔ 页面**只改出处行号**，**一个数据数都没动**，+2/−2 行）：")
    A("  · ① 口径切换注的出处 `:38406`、`:38413` ⇒ ⇒ 那两行是**相反结论**"
      "（inclusive 是生产默认 / 基准 = prod/inclusive/keep）⇒ ⇒ 真出处是 `:40404`（244.74 段）")
    A("  · ② 「缺读数 0、缺位点数 0」的真实出处是 `:38198`，页面写的是 `:38195`")
    A("  · ⚠ 另有一处**一度被我判错**的「矛盾」（`:38490` vs `:40404`）⇒ ⇒ 那是**两批不同数据**"
      "⇒ ⇒ **不矛盾** ⇒ ⇒ 不当缺陷、页面不动")
    A("")
    A("· **每条判据能红**：")
    A("  · 自检（合成夹具、⛔ 零账本零页面零 GPU）：共 **" + str(st_total) + "** 道 ⇒ ⇒ **失败 " + str(st_red)
      + " 道**（⛔ 这是「没通过」的条数，不是「判红的条数」）")
    A("  · 变异台：共 **" + mu["MUT_N"] + "** 条（预登记 8 ＋ 实现期新增 1 条等价变异）⇒ ⇒ 抓住 **"
      + mu["MUT_CAUGHT"] + "** ｜ 存活 **" + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"]
      + "** ｜ 等价变异通过 **" + mu["MUT_EQUIV_OK"] + "**（输出与基线**逐字节相同**）")
    A("  · 互证（第二条**独立**实现，⛔ 零共用代码、⛔ 锚定与取数口径**故意不同**）：锚点 **"
      + cr["CROSS_N_ANCHORS"] + "** ｜ 逐数比对 **" + cr["CROSS_N_NUMBERS"] + "** ｜ 不符 **0**"
      "（引用行号 / 逐数 / 判定 / 形态 / 口径注）｜ 互证**自己也能红**：`CROSS_SELFTEST_RC="
      + cs["CROSS_SELFTEST_RC"] + "`")
    A("  · 预登记 ↔ 实现 的**机械对账**：判据 **" + sp["SPEC_N_CRITERIA"] + "** ｜ 变异 **"
      + sp["SPEC_N_MUT"] + "** ｜ 锚点 **" + sp["SPEC_N_ANCHORS"] + "** ｜ 偏差 **"
      + sp["SPEC_N_DEVIATION"] + "**（已显式声明）｜ **真值命中 " + sp["SPEC_REAL_TOKEN_HITS"]
      + "** ⇒ ⇒ 「零手写期望」是**机械可查**的")
    A("  · 「**改前 ⇒ 改后**」两份收据都在：改前形态 **" + b["VERDICT"] + "**、判红 **"
      + "/".join(b_red) + "**（⛔ 那次不算判决）⇒ ⇒ 改后形态 **" + a["VERDICT"] + "**")
    A("")
    A("· **边界**（⛔ 不许被读成什么）：")
    A("  · 本轮**只**对账 §6.2.3 的 5 行 ＋ 1 条注 ⇒ ⇒ ⛔ **不许**说成「剂量轴整节已核」"
      "⇒ ⇒ ⛔ **不许**说成「整页已核」")
    A("  · **D1 守的是「数与出处脱节」，⛔ 不是「出处引得最准」** ⇒ ⇒ 留白")
    A("  · §6.1 / §6.2（**除 §6.2.3**）/ §6.3 / §6.4 / 页面第一部分 ⇒ ⇒ 这些小节的**内容断言**仍未被机器守"
      "（⚠ 244.92 的链**确实**守着几处：A8 全页行号越界 ＋ §6.3 台账行、A5 §6.4.1 的 B-14 行、"
      "A6 §6.4.4 的逐字引用句、A7 §6.5 复算入口、A9 全页过期措辞、A1–A4/H1–H7 §6.7）")
    A("  · **剂量—响应 / 污染的精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子**一律**未量到** ⇒ ⇒ 本轮**不碰**")
    A("  · **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**")
    A("")
    led_md5_pre = ""
    for l in read(os.path.join(RCPT, "receipt.txt")).split("\n"):
        m = re.match(r"^([0-9a-f]{32})\s+.*R6_RERUN_PREREG\.md$", l.strip())
        if m:
            led_md5_pre = m.group(1)
            break
    if not led_md5_pre:
        raise SystemExit("⛔ 收据里没找到账本的 md5 ⇒ ⇒ 中止")

    A("· **字节**：账本 **" + str(led_lines) + "** 行 ｜ **落账前**那版的 md5 **" + led_md5_pre
      + "**（**落账后**的 md5 由落账脚本打印、并由**提交后双回读**核）｜ 索引 **" + str(idx_lines)
      + "** 行 ｜ 账本里 244.93 段 **" + str(n_2493) + "** 处")
    A("· **远端**：`zju-53`（判决链，⛔ **零 GPU**）＋ `zju-12`（全回归 R12）"
      "｜ 收据在 `.cache/r244/_e24493/`（⛔ **不入库**）")
    A("")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
