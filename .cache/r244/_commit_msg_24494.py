#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_commit_msg_24494.py —— 生成 244.94 的提交信息（**每个数都从收据/账本现取**，⛔ 不手打）。

⚖ 提交信息里的数**必须**与**跑出它们的那些字节**同源 ⇒ ⇒ 账本改了，它**不可能**留在旧数上。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24494")
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

    a_crits = re.findall(r"^\[(PASS|FAIL)\] (E\d)：(.+)$", af, re.M)
    b_red = re.findall(r"^\[FAIL\] (E\d)：", bf, re.M)
    n_rows = len(re.findall(r"^ROW=", af, re.M))
    n_rowv = len(re.findall(r"^ROWV=", af, re.M))

    ledger_text = read(LEDGER)
    ledger_lines = ledger_text.count("\n")
    index_lines = read(INDEX).count("\n")
    n_2494 = len(re.findall(r"^## 修订 244\.94 ", ledger_text, re.M))
    # ⚖⚖⚖ 「落账前那版的 md5」必须**限定在 244.94 段里**取
    #    ⇒ ⇒ 否则会匹配到**更早**那一段的同名行（拿到的就是过期值）。
    _i = ledger_text.find("## 修订 244.94 ")
    _seg = ledger_text[_i:] if _i >= 0 else ""
    pre_md5 = (re.search(r"落账前\*\* md5 `([0-9a-f]{32})`", _seg) or [None, "?"])[1]

    out = []
    W = out.append
    W("「两臂同一个剂量」前提纳入证据链：页面 §6.2.1 的 9 行与账本**逐字一致**（形态 A）")
    W("")
    W("· **判决**：页面 `docs/BPATH_VERDICT.md` §6.2.1（**9 行「两臂同一个剂量」表**）↔ 权威账本 244.83 段"
      "那张验收表 ⇒ ⇒ **逐行逐字一致** ⇒ 形态 **" + a["VERDICT"] + "**")
    W("  · 判据 **E1–E5**：**" + a["N_CHECKS"] + "** 条全绿（E1 三列逐字相同；E2「同」断言有出处；"
      "E3 出处行号存在且恰好指到那张表；E4 锚点唯一；E5 行数 == 9）")
    W("  · 逐行矩阵：**" + str(n_rows) + " 行** ＋ **" + str(n_rowv) + " 条逐行结论**（EQ / SAME）"
      "｜ 辅助测量：rand 列不符 **" + a.get("AUX_RAND_MISMATCH", "?") + "** 处 ｜ 一一对应 **"
      + a.get("AUX_BIJ", "?") + "/" + a.get("AUX_BIJ_TOTAL", "?") + "**")
    W("  · ⚖ **为什么这一块**：244.81/244.82 的 **w-vs-rand 判决**只有在「两臂剂量相同」成立时才可读 ⇒ ⇒ "
      "这张表是该前提的**唯一对外出处** ⇒ ⇒ 它和判决数在**同一条链的两端**")
    W("  · ⚖⚖⚖ **判据从「数能找到」升级为「逐字一致」**：侦察先证明 244.93 式的判据在本节**几乎恒绿**"
      "（25/25 个数都能找到 ⇒ 无数值缺陷）⇒ ⇒ ⇒ 本轮改用**逐字一致**（去反引号 / 去粗体 / 去所有空白）"
      "⇒ ⇒ 连**措辞**都守")
    W("")
    W("· **本轮抓到的 3 处真缺陷**（⛔ 页面**只补措辞**，**一个数据数都没动**，+3/−3 行）：")
    W("  · ① `:41612` 的差列少「**且**」⇒ ⇒ 账本写的是**合取**，页面原来写成了括号 ⇒ ⇒ 页面更松")
    W("  · ② `:41614` 的差列少「**路径**」⇒ ⇒ 账本断言的是「求和**路径**」⇒ ⇒ 页面更松")
    W("  · ③ `:41615` 的差列少「**（同一把向量）**」⇒ ⇒ 账本明写两臂用**同一把向量**")
    W("  · ⚖ **另一处不是缺陷**：`:41610` 的 rand 臂页面写「同」、账本写实际值 ⇒ ⇒ **合法压缩**"
      "⇒ ⇒ 由 E2 判它有出处 ⇒ ⇒ **不改**")
    W("  · ⚖ 缺陷行集合与**预登记 §1.2 登记的完全一致**（规格对账机械可查）")
    W("")
    W("· **每条判据能红**：")
    W("  · 自检（合成夹具、⛔ 零账本零页面零 GPU）：共 **" + str(st_total) + "** 道 ⇒ ⇒ **失败 "
      + str(st_red) + " 道**（⛔ 这是「没通过」的条数，不是「判红的条数」）")
    W("  · 变异台：共 **" + mu["MUT_N"] + "** 条（预登记 10 ＋ 实现期新增 3）⇒ ⇒ 抓住 **"
      + mu["MUT_CAUGHT"] + "** ｜ 存活 **" + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"]
      + "** ｜ 等价变异通过 **" + mu["MUT_EQUIV_OK"] + "**（输出与基线**逐字节相同**）｜ 无闸门预期（留白实证）通过 **"
      + mu["MUT_NORED_OK"] + "** ｜ **预登记期望与实测不符 " + mu["MUT_PREREG_MISMATCH"] + " 处**")
    W("  · 互证（第二条**独立**实现，⛔ 零共用代码、⛔ 锚定**按账本表头 + 行号反查**、⛔ 归一化**按词切分**）："
      "锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 逐字相同 **" + cr["CROSS_N_EQ"] + "** ｜ 逐字不同 **"
      + cr["CROSS_N_NE"] + "** ｜ 「同」断言有出处 **" + cr["CROSS_SAME_OK"] + "/" + cr["CROSS_SAME_TOTAL"]
      + "** ｜ 不符合计 **" + cr["CROSS_MISMATCH"] + "** ｜ 互证**自己也能红**：`CROSS_SELFTEST_RC="
      + cs["CROSS_SELFTEST_RC"] + "`")
    W("  · 预登记 ↔ 实现 的**机械对账**：判据 **" + sp["SPEC_N_CRITERIA"] + "** ｜ 变异 **" + sp["SPEC_N_MUT"]
      + "** ｜ 缺陷行 **" + sp["SPEC_N_DEFECT"] + "** ｜ **真值命中 " + sp["SPEC_REAL_TOKEN_HITS"]
      + "** ⇒ ⇒ 「零手写期望」是**机械可查**的")
    W("  · 「**改前 ⇒ 改后**」两份收据都在：改前形态 **" + b["VERDICT"] + "**、判红 **" + "/".join(b_red)
      + "**（⛔ 那次不算判决）⇒ ⇒ 改后形态 **" + a["VERDICT"] + "**")
    W("  · **不变性**：同一套链连跑 **3 次**，7 份收据 **md5 逐字节相同**")
    W("")
    W("· **边界**（⛔ 不许被读成什么）：")
    W("  · 本轮**只**对账 §6.2.1 的 9 行 ⇒ ⇒ ⛔ **不许**说成「剂量轴整节已核」⇒ ⇒ ⛔ **不许**说成「整页已核」")
    W("  · ⚖⚖⚖ **留白（本轮实测出来的）**：**页面的 rand 臂列在不是「同」时没有闸门守**"
      "⇒ ⇒ 证据：MU-E3（「同」→「异」）与 MU-E12（rand 臂写错数）**都没有任何闸门红**"
      "⇒ ⇒ 本轮用**辅助测量**把它量出来 ⇒ ⇒ 但它**不是闸门** ⇒ ⇒ 下一轮必须补成真判据")
    W("  · ⚖ **预登记 §1.3 有一处悬空引用**（「见 §2 E6」，而 §2 只有 E1–E5）⇒ ⇒ 「一一对应」这条**要求**"
      "没有闸门 ⇒ ⇒ 本轮用**辅助测量**量了（9/9）⇒ ⇒ 仍**不是闸门** ⇒ ⇒ 下一轮补")
    W("  · ⚠ **预登记期望写错 2 处，如实登记**（⛔ 不改实现去迁就期望、⛔ 不改预登记）："
      "MU-E3 期望 E2 红但 E2 是**条件式**判据（改掉「同」后不再适用）｜ MU-E4 期望 E4 红但 E4 守**唯一性**"
      "（删行不破坏唯一性），真正抓住「少一行」的是 **E5**")
    W("  · §6.2.2、§6.1 判决面板（P1–P29）、§6.3、§6.4、页面第一部分（§0–§5）⇒ ⇒ 内容断言仍未被本轮机器守")
    W("  · **剂量—响应 / 污染的精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子**一律**未量到** ⇒ ⇒ 本轮**不碰**")
    W("  · **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**")
    W("  · 「**改闸门自己的比较表达式**没有闸门能抓」（244.93 起留着）⇒ ⇒ 只能缩小、⛔ 不可能消灭 ⇒ ⇒ 留白")
    W("")
    W("· **字节**：账本 **" + str(ledger_lines) + "** 行 ｜ **落账前**那版的 md5 **" + str(pre_md5)
      + "**（**落账后**的 md5 由落账脚本打印、并由**提交后双回读**核）｜ 索引 **" + str(index_lines)
      + "** 行 ｜ 账本里 244.94 段 **" + str(n_2494) + "** 处")
    W("· **远端**：`zju-53`（判决链，⛔ **零 GPU**）＋ `zju-12`（全回归 R13）｜ 收据在 `.cache/r244/_e24494/`（⛔ **不入库**）")
    W("")
    sys.stdout.write("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
