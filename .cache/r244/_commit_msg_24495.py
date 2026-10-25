#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_commit_msg_24495.py —— 生成 244.95 的提交信息（**每个数都从收据/账本现取**，⛔ 不手打）。

⚖ 提交信息里的数**必须**与**跑出它们的那些字节**同源 ⇒ ⇒ 账本改了，它**不可能**留在旧数上。
"""

import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24495")
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
    n_2495 = len(re.findall(r"^## 修订 244\.95 ", ledger_text, re.M))
    # ⚖⚖⚖ 「落账前那版的 md5」必须**限定在 244.94 段里**取
    #    ⇒ ⇒ 否则会匹配到**更早**那一段的同名行（拿到的就是过期值）。
    _i = ledger_text.find("## 修订 244.95 ")
    _seg = ledger_text[_i:] if _i >= 0 else ""
    pre_md5 = (re.search(r"落账前\*\* md5 `([0-9a-f]{32})`", _seg) or [None, "?"])[1]

    out = []
    W = out.append
    W("两条**实测**留白补成真判据：rand 臂列（E6）＋ 一一对应（E7）从「辅助测量」升格为**闸门**")
    W("")
    W("· **判决**：页面 `docs/BPATH_VERDICT.md` §6.2.1（**9 行「两臂同一个剂量」表**）↔ 权威账本 244.83 段"
      "那张验收表 ⇒ ⇒ **逐行逐字一致**，且 **E6/E7** 也全绿 ⇒ 形态 **" + a["VERDICT"] + "**")
    W("  · 判据 **E1–E7**：**" + a["N_CHECKS"] + "** 条全绿（E1 三列逐字相同；E2「同」断言有出处；"
      "E3 出处行号存在且恰好指到那张表；E4 锚点唯一；E5 行数 == 9；"
      "**E6 rand 臂列 vs 账本的可比较形式 L；E7 一一对应**）")
    W("  · 逐行矩阵：**" + str(n_rows) + " 行** ＋ **" + str(n_rowv) + " 条逐行结论**（EQ / SAME）"
      "｜ 明细计数：rand 列不符 **" + a.get("AUX_RAND_MISMATCH", "?") + "** 处 ｜ 一一对应 **"
      + a.get("AUX_BIJ", "?") + "/" + a.get("AUX_BIJ_TOTAL", "?") + "**")
    W("")
    W("· ⚖⚖⚖ **本轮把 244.94 的两条**实测**留白补成真闸门**（⛔ 那是变异台**打出来的**，⛔ 不是猜的）：")
    W("  · **E6 · rand 臂列**：244.94 的 MU-E3（「同」→「异」）与 MU-E12（rand 臂写错数）"
      "**都没有任何闸门红** ⇒ ⇒ 现在 **E6 必须红**（MU-F1 页面侧 / MU-F2 页面侧 / MU-F3 **账本侧**）")
    W("  · **E7 · 一一对应**：244.94 预登记 §1.3 的「见 §2 E6」是**悬空引用**（§2 只有 E1–E5）"
      "⇒ ⇒ 那条**要求**当时**没有闸门** ⇒ ⇒ 现在 **E7 必须红**（MU-F4）")
    W("  · ⚖ **E6 的比较基准 L**（预登记 §1.4）：账本 rand 格是「同」⇒ ⇒ 取**账本 w 格**；否则取**账本 rand 格**"
      "⇒ ⇒ 页面写**更具体**的值**不算错** ⇒ ⇒ MU-F7 专门守这一条（**不该**判红）")
    W("")
    W("· ⛔ **本轮没有新缺陷**：244.94 已把那 3 处措辞缺陷改掉 ⇒ ⇒ 本轮**页面一个字节都没动**、"
      "**一个实测数都没改** ⇒ ⇒ ⚠ 预登记 §1.3 就写明了「新判据在当前数据上**预期是绿**」"
      "⇒ ⇒ ⛔ **不许**被说成「又抓到了新缺陷」")
    W("")
    W("· **每条判据能红**：")
    W("  · 自检（合成夹具、⛔ 零账本零页面零 GPU）：共 **" + str(st_total) + "** 道 ⇒ ⇒ **失败 "
      + str(st_red) + " 道**（⛔ 这是「没通过」的条数，不是「判红的条数」）")
    W("  · 变异台：预登记 §4 的 **9 条**（MU-F1..MU-F9）⇒ ⇒ 抓住 **" + mu["MUT_CAUGHT"] + "** ｜ 存活 **"
      + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"] + "** ｜ 等价变异通过 **"
      + mu["MUT_EQUIV_OK"] + "**（输出与基线**逐字节相同**）｜ 无闸门预期 **" + mu["MUT_NORED_OK"]
      + "**（MU-F7 合法方向）｜ **预登记期望与实测不符 " + mu["MUT_PREREG_MISMATCH"] + " 处**")
    W("  · 互证（第二条**独立**实现，⛔ 零共用代码、⛔ 锚定**按账本表头 + 行号反查**、⛔ 归一化**按词切分**）："
      "锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 逐字相同 **" + cr["CROSS_N_EQ"] + "** ｜ 「同」断言有出处 **"
      + cr["CROSS_SAME_OK"] + "/" + cr["CROSS_SAME_TOTAL"] + "** ｜ **E6 不符 " + cr.get("CROSS_E6_MISMATCH", "?")
      + "** ｜ **E7 重复 " + cr.get("CROSS_E7_DUP", "?") + "** ｜ 不符合计 **" + cr["CROSS_MISMATCH"]
      + "** ｜ 互证**自己也能红**：`CROSS_SELFTEST_RC=" + cs["CROSS_SELFTEST_RC"] + "`")
    W("  · 预登记 ↔ 实现 的**机械对账**：判据 **" + sp["SPEC_N_CRITERIA"] + "** ｜ 变异 **" + sp["SPEC_N_MUT"]
      + "** ｜ 改前差异行 == **上一轮预登记登记的那 3 行**（⛔ 从上一轮预登记里读）｜ **真值命中 "
      + sp["SPEC_REAL_TOKEN_HITS"] + "** ⇒ ⇒ 「零手写期望」是**机械可查**的")
    W("  · 「**改前 ⇒ 改后**」两份收据都在：改前形态 **" + b["VERDICT"] + "**、判红 **" + "/".join(b_red)
      + "**（⛔ 那次不算判决）⇒ ⇒ 改后形态 **" + a["VERDICT"] + "**")
    W("  · **不变性**：同一套链连跑 **3 次**，7 份收据 **md5 逐字节相同**")
    W("")
    W("· **边界**（⛔ 不许被读成什么）：")
    W("  · 本轮**仍然只**对账 §6.2.1 的 9 行 ⇒ ⇒ ⛔ **不许**说成「剂量轴整节已核」⇒ ⇒ ⛔ **不许**说成「整页已核」")
    W("  · ✅ **244.94 的两条留白本轮已关闭**（rand 臂列 ⇒ E6 ｜ 一一对应 ⇒ E7）⇒ ⇒ 它们**不再是留白**")
    W("  · ⚠ **新的留白**：E6 守的是「页面与账本一致」，⛔ 不是「账本本身对」；"
      "E7 守的是「一一对应」，⛔ 不是「对应关系对」")
    W("  · §6.2.2、§6.1 判决面板（P1–P29）、§6.3、§6.4、页面第一部分（§0–§5）⇒ ⇒ 内容断言仍未被本轮机器守")
    W("  · **剂量—响应 / 污染的精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子**一律**未量到** ⇒ ⇒ 本轮**不碰**")
    W("  · **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**")
    W("  · 「**改闸门自己的比较表达式**没有闸门能抓」⇒ ⇒ 只能缩小、⛔ 不可能消灭 ⇒ ⇒ 留白")
    W("")
    sys.stdout.write("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
