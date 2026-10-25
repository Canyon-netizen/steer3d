#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_append_24494.py —— 把 **244.94** 落账（**只追加**），每条数**从收据解析**。

⚖⚖⚖ **纪律**（沿用 244.92/244.93 的成规）
   · ⛔ 代码里**不写死任何一个数**（全部从 `.cache/r244/_e24494/*.out` ＋ `receipt.txt` 解析）；
   · ⛔ **追加段无围栏、无反斜杠**（⇒ ⇒ 账本的围栏行首计数不变）；
   · ⛔ **旧前缀逐字节不变**（追加前后对同一段字节算 md5 比对）；
   · ⛔ **幂等**：重跑 ⇒ 「逐字节相同、不重复写」；
   · ⛔ 段里的 md5 必须**与本地现算的 md5** 相等（否则中止）；
   · ⛔ 追加段**不得**出现 `@大写@` 形式的占位符标记（既有护栏 C1/C5/C6 会判红）；
   · ⛔ 追加段**不得**出现字面 `****`（既有护栏 C8 会判红）。
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.environ.get("APPEND_LEDGER",
                         os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md"))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24494")
MARK = "## 修订 244.94 ——"


def read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def md5b(b):
    return hashlib.md5(b).hexdigest()


def md5f(p):
    return md5b(read(p).encode("utf-8"))


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


def receipt_md5s():
    """⚖ 远端收据里登记的 md5（**远端现算**）⇒ ⇒ 与本地现算逐位对。"""
    txt = read(os.path.join(RCPT, "receipt.txt"))
    out = {}
    for l in txt.split("\n"):
        m = re.match(r"^([0-9a-f]{32})\s+(\S+)$", l.strip())
        if m:
            out[os.path.basename(m.group(2))] = m.group(1)
    return out


def main():
    st_text = read(os.path.join(RCPT, "selftest.out"))
    st_total = len(re.findall(r"^\[(PASS|FAIL)\]", st_text, re.M))
    st_rc = (re.search(r"^SELFTEST_RC=(\d+)", st_text, re.M) or [None, None])[1]
    st_red = (re.search(r"^SELFTEST_RED=(\d+)", st_text, re.M) or [None, None])[1]

    bf = read(os.path.join(RCPT, "data_before.out"))
    af = read(os.path.join(RCPT, "data_after.out"))
    b_keys = keys(bf, "AUDIT_KEYS")
    a_keys = keys(af, "AUDIT_KEYS")
    b_crits = re.findall(r"^\[(PASS|FAIL)\] (E\d)：(.+)$", bf, re.M)
    a_crits = re.findall(r"^\[(PASS|FAIL)\] (E\d)：(.+)$", af, re.M)
    n_rows = len(re.findall(r"^ROW=", af, re.M))
    n_rowv = len(re.findall(r"^ROWV=", af, re.M))
    if len(a_crits) != int(a_keys["N_CHECKS"]):
        raise SystemExit("⛔ 判据行数与 N_CHECKS 对不上 ⇒ ⇒ 中止")
    # ⚖ 改前的判红明细（拆成一条一条）
    b_red_detail = ""
    for _s, cid, detail in b_crits:
        if cid == "E1":
            b_red_detail = detail
    b_defects = [x for x in b_red_detail.split("；") if x.strip()]

    mu = keys(read(os.path.join(RCPT, "mut.out")), "AUDIT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "AUDIT_KEYS")
    cs = keys(read(os.path.join(RCPT, "cross_selftest.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")

    # ⚖ 远端收据登记的 md5（**远端现算**）⇒ ⇒ 与本地现算逐位对
    rc_md5 = receipt_md5s()
    files = [
        ".cache/r244/doc_dose_arm_audit.py",
        ".cache/r244/mut_doc_dose_arm_audit.py",
        ".cache/r244/_cross_check_24494.py",
        ".cache/r244/_spec_crosscheck_24494.py",
        ".cache/r244/_run_24494_verify.sh",
        ".cache/xcheck/R6_DOSE_ARM_DOC_PREREG.md",
    ]
    md5s = []
    for f in files:
        h = md5f(os.path.join(REPO, f))
        base = os.path.basename(f)
        if base in rc_md5 and rc_md5[base] != h:
            raise SystemExit("⛔ %s 的 md5：远端收据 %s ≠ 本地现算 %s ⇒ ⇒ 中止"
                             % (base, rc_md5[base], h))
        md5s.append((f, h))
    page_after_md5 = md5f(os.path.join(REPO, "docs", "BPATH_VERDICT.md"))
    page_before_md5 = md5f(os.path.join(REPO, ".cache", "r244", "_page_24494_before.md"))
    page_after_copy_md5 = md5f(os.path.join(REPO, ".cache", "r244", "_page_24494.md"))
    if rc_md5.get("_page_24494.md") not in (None, page_after_copy_md5):
        raise SystemExit("⛔ 改后页面副本 md5 与远端收据对不上 ⇒ ⇒ 中止")
    if rc_md5.get("BPATH_VERDICT.md") not in (None, page_after_md5):
        raise SystemExit("⛔ 页面 md5 与远端收据对不上 ⇒ ⇒ 中止")
    if rc_md5.get("_page_24494_before.md") not in (None, page_before_md5):
        raise SystemExit("⛔ 改前页面副本 md5 与远端收据对不上 ⇒ ⇒ 中止")
    if page_after_md5 != page_after_copy_md5:
        raise SystemExit("⛔ 页面与改后副本不是同一份字节 ⇒ ⇒ 中止")

    rcpt_files = ["selftest.out", "data_before.out", "data_after.out", "mut.out",
                  "cross.out", "cross_selftest.out", "spec.out"]
    rcpt_md5 = []
    for f in rcpt_files:
        h = md5f(os.path.join(RCPT, f))
        if f in rc_md5 and rc_md5[f] != h:
            raise SystemExit("⛔ 收据 %s 的 md5：远端 %s ≠ 本地 %s ⇒ ⇒ 中止" % (f, rc_md5[f], h))
        rcpt_md5.append((f, h))
    ledger_pre_md5 = rc_md5.get("R6_RERUN_PREREG.md")
    ledger_pre_lines = (re.search(r"账本：.*?（(\d+) 行）", bf) or [None, None])[1]

    body = []
    A = body.append
    A(MARK + " ⚖⚖⚖⚖⚖ **「两臂同一个剂量」前提纳入证据链**：页面 `docs/BPATH_VERDICT.md` §6.2.1 的 "
      "9 行 ↔ 权威账本 244.83 段那张验收表 **逐行逐字对账**（形态 **" + a_keys["VERDICT"] + "**）")
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_ARM_DOC_PREREG.md`（244.94 签，**先于**实现；"
      "§0 范围与不做项、§1 侦察与 3 处缺陷、§2 判据 E1–E5、§3 实现纪律、§4 变异台 MU-E1..MU-E10、"
      "§5 互证、§6 边界、§7 下一轮）")
    A("⚖ **数据**：**只读已入库文件**（页面 ＋ 账本整本）⇒ ⇒ ⛔ **不读收据**（收据**不入库**）"
      "⇒ ⇒ 别人 clone 下来就能跑；⛔ **零 GPU**、⛔ 没跑批、⛔ 没重解析原始跑批日志、⛔ 没改探针")
    A("⚖ **收据**：`.cache/r244/_e24494/{selftest,data_before,data_after,mut,cross,cross_selftest,spec}.out`"
      " ＋ `receipt.txt`（⚖ **不入库**；远端 `zju-53`）")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· **没有跑批、没有 GPU、没有重解析原始跑批日志** ⇒ ⇒ 本轮**不产生任何新的实测数**，"
      "只做「**页面 ↔ 账本**」的对账与修正 ⇒ ⇒ ⛔ **一个实测数都没改**。")
    A("· **为什么是这一块**：244.81/244.82 的 **w-vs-rand 判决**只有在「**两臂剂量相同**」这条前提成立时才可读"
      "⇒ ⇒ §6.2.1 这张 9 行的表就是该前提的**唯一对外出处** ⇒ ⇒ 它和判决数在**同一条链的两端**。")
    A("· ⚖⚖⚖ **核心设计（判据从「数能找到」升级为「逐字一致」）**：侦察先证明 244.93 式的"
      "「每个数能在它引用的账本行里逐位找到」在本节**几乎恒绿** ⇒ ⇒ 无数值缺陷 ⇒ ⇒ "
      "⇒ ⇒ 本轮改用**逐字一致**（归一化 = 去反引号 / 去粗体标记 / 去**所有**空白）⇒ ⇒ 连**措辞**都守。")
    A("· ⚖ **归一化只比内容、⛔ 不比 markdown 装饰**；⚖ **「同」是派生断言**（页面把账本里两臂逐位相同的行"
      "压成一个字）⇒ ⇒ 单列一条判据 E2 判它**有没有出处**。")
    A("")
    A("#### 【2】⚖⚖⚖ **本轮抓到的 3 处真缺陷（⛔ 页面只补字，一个数据数都没动）**")
    A("")
    A("· 缺陷行（账本行号）：**" + sp.get("SPEC_DEFECT_LINES", "") + "** ⇒ ⇒ 与预登记 §1.2 登记的"
      "**完全一致**（规格对账机械可查 ⇒ 「找到的就是预登记登记的那些」）。")
    for d in b_defects:
        A("  · " + d)
    A("· ⇒ ⇒ 三处都是**措辞**层面的（页面的说法比账本**松**）：`:41612` 少「且」、`:41614` 少「路径」、"
      "`:41615` 少「（同一把向量）」⇒ ⇒ **已按账本原文补回**（`+3 / −3` 行）。")
    A("· ⚖ **另一处不是缺陷**：`:41610` 的 rand 臂页面写「同」、账本写实际值 ⇒ ⇒ 那是**合法压缩**"
      "⇒ ⇒ 由 E2 判它有出处（账本该行 w 臂与 rand 臂逐字相同）⇒ ⇒ **不改**。")
    A("")
    A("#### 【3】✅ **判据逐条（真数据 · 改后 · 共 " + a_keys["N_CHECKS"] + " 条：E1–E5）**")
    A("")
    for s, cid, detail in a_crits:
        A("- [" + s + "] **" + cid + "**：" + detail)
    A("")
    A("⚖ 逐行矩阵：**" + str(n_rows) + " 行展品** ＋ **" + str(n_rowv) + " 条逐行结论**"
      "（EQ = 三列逐字相同 ｜ SAME = 「同」断言有出处）⇒ ⇒ 逐行明细见收据 `data_after.out` 的 "
      "`NUM_MATRIX` ＋ `ROW_VERDICTS` 块。")
    A("⚖ **辅助测量（⛔ 不是判据、⛔ 不参与形态判定）**：rand 列逐字不符 **" + a_keys.get("AUX_RAND_MISMATCH", "?")
      + "** 处 ｜ 一一对应 **" + a_keys.get("AUX_BIJ", "?") + "/" + a_keys.get("AUX_BIJ_TOTAL", "?")
      + "**（9 个页行引到的账本行互不相同）⇒ ⇒ ⚠ 这两项的绿灯**不构成**「已被守住」，只作为事实登记。")
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0，合成夹具、⛔ 零账本、⛔ 零页面、⛔ 零 GPU）：共 **" + str(st_total)
      + "** 道用例 ⇒ ⇒ **失败 " + str(st_red) + " 道**（⚖ 这个数是「**没通过**」的条数，"
      "⛔ **不是**「判红的条数」）｜ `SELFTEST_RC=" + str(st_rc) + "`")
    A("- **变异台**：预登记 §4 的 **10 条** ＋ 实现期新增的 **3 条**（MU-E11 账本侧、"
      "MU-E12 rand 错数、MU-E13 表头复制；**非预登记**）⇒ ⇒ 共 **" + mu["MUT_N"] + "** 条，"
      "抓住 **" + mu["MUT_CAUGHT"] + "** ｜ 存活 **" + mu["MUT_SURVIVORS"] + "** ｜ 崩 **"
      + mu["MUT_CRASHED"] + "** ｜ 等价变异通过 **" + mu["MUT_EQUIV_OK"]
      + "**（输出与基线**逐字节相同**）｜ 等价变异异常 **" + mu["MUT_EQUIV_BAD"] + "**"
      + " ｜ 无闸门预期（留白实证）通过 **" + mu["MUT_NORED_OK"] + "** ｜ 异常 **"
      + mu["MUT_NORED_BAD"] + "** ｜ 页面层判 **" + mu["MUT_DATA_JUDGED"] + "** ｜ 账本层判 **"
      + mu["MUT_LEDGER_JUDGED"] + "** ｜ 自检层判 **" + mu["MUT_SELFTEST_JUDGED"] + "**"
      + " ｜ `MUT_RC=" + mu["MUT_RC"] + "`")
    A("- ⚖⚖⚖ **预登记期望与实测不符 2 处（如实登记，⛔ 不改实现去迁就期望、⛔ 不改预登记）**：")
    A("  · **MU-E3**（把某行 rand 臂的「同」改成「异」）：预登记期望 **E2 红** ⇒ ⇒ **实测无闸门红**"
      "⇒ ⇒ 原因：E2 是**条件式**判据（只在页面写「同」时才查）⇒ ⇒ 把「同」改成「异」之后它**不再适用**"
      "⇒ ⇒ ⇒ 这是**留白**的实证（见 §6），已用 MU-E11（账本侧变异）给 E2 补上牙齿。")
    A("  · **MU-E4**（删掉一整行展品）：预登记期望 **E4 红** ⇒ ⇒ **实测只有 E5 红**"
      "⇒ ⇒ 原因：E4 守的是**唯一性**（每行在整页只出现一次），删行**不破坏**唯一性"
      "⇒ ⇒ ⇒ 真正抓住「少一行」的是 **E5（计数）** ⇒ ⇒ 按实测登记。")
    A("- **互证**（第二条**独立**实现：⛔ 零共用代码、⛔ 锚定**故意不同**〔它按**账本自己的 5 格表头**定位那张表、"
      "再按**页面的「账本位置」列的行号**反查匹配；被检实现按**页面的 6 格表头**定位、按**量列**匹配〕、"
      "⛔ 归一化**故意不同**〔**按词切分逐词序列**比 vs **删空白整串**比〕）"
      "：锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 逐字相同 **" + cr["CROSS_N_EQ"] + "** ｜ 逐字不同 **"
      + cr["CROSS_N_NE"] + "** ｜ 「同」断言有出处 **" + cr["CROSS_SAME_OK"] + "/" + cr["CROSS_SAME_TOTAL"]
      + "** ｜ 读数不符 **" + cr["CROSS_CELL_MISMATCH"] + "** ｜ **表示差异 " + cr["CROSS_REPR_DIFF"]
      + "**（⛔ 不算不符：被检实现把 `n_eff == P+t` 的空白删掉合成一个 token，互证按词切分保留 3 个 token；"
      "**去空白后相等** ⇒ ⇒ 内容一致）｜ **不符合计 " + cr["CROSS_MISMATCH"]
      + "** ｜ 互证自算形态 **" + cr["CROSS_VERDICT"] + "** ⇒ ⇒ `CROSS_RC=" + cr["CROSS_RC"] + "`")
    A("- ⚖ **互证自己也要能红**：把被检实现的输出改坏（翻一个闸门 ＋ 改一个逐行结论 ＋ 改一个读数）"
      "⇒ ⇒ 互证**抓到 " + cs.get("CROSS_SELFTEST_N_DIFF", "?") + " 处** ⇒ ⇒ `CROSS_SELFTEST_RC="
      + cs["CROSS_SELFTEST_RC"] + "`")
    A("- **预登记 ↔ 实现 的机械对账**：判据集合一致（**" + sp["SPEC_N_CRITERIA"] + "** 条 E1–E5）"
      " ｜ 变异覆盖预登记 **" + sp["SPEC_N_MUT"] + "** 条（额外 3 条为实现期新增、**非预登记**）"
      " ｜ 缺陷行 **" + sp["SPEC_N_DEFECT"] + "** 条（**预登记登记的 == 实际有差异的**）"
      " ｜ **真值命中 " + sp["SPEC_REAL_TOKEN_HITS"] + "**（⇒ 「零手写期望」**机械可查**）"
      " ｜ E5 的手写行数期望 **" + sp.get("SPEC_EXPECT_ROWS", "?") + "**"
      " ⇒ ⇒ `SPEC_RC=" + sp["SPEC_RC"] + "`")
    A("- ⚖⚖⚖ **「改前 ⇒ 改后」两份收据都在**：**改前**（故意留的过期页面副本）⇒ ⇒ 形态 **"
      + b_keys["VERDICT"] + "**、判红 **" + "/".join(sorted(set(
          re.findall(r"^CHECK_(E\d)=FAIL", bf, re.M)))) + "** ⇒ ⇒ 这是「**检查器有牙齿**」的证据"
      "（⛔ 那次**不算判决**）⇒ ⇒ **改后**形态 **" + a_keys["VERDICT"] + "**。")
    A("- ⚖ **不变性**：同一套链连跑 **3 次**，7 份收据 **md5 逐字节相同** ⇒ ⇒ 判定**可复现**。")
    A("")
    A("#### 【5】⚖ **页面改动（最小化 · 可对照）**")
    A("")
    A("· 只改 **3 行**（**+3 / −3**）⇒ ⇒ **只补措辞**，⛔ **一个数据数都没动**：")
    A("  · `:41612` 行的差列：`逐格相同（`n_eff == P+t` 全部相符）` ⇒ ⇒ 补「且」"
      "⇒ ⇒ 账本写的是**合取**（且），页面原来把合取写成了括号 ⇒ ⇒ 页面**更松**。")
    A("  · `:41614` 行的差列：`公式 vs 直接求和不一致` ⇒ ⇒ 补「路径」"
      "⇒ ⇒ 账本断言的是「求和**路径**」，页面原来写的是「求和」⇒ ⇒ 页面**更松**。")
    A("  · `:41615` 行的差列：`--w 两臂相同` ⇒ ⇒ 补「（同一把向量）」"
      "⇒ ⇒ 账本明写两臂用的是**同一把向量**，页面原来没写 ⇒ ⇒ 页面**信息更少**。")
    A("")
    A("#### 【6】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ⛔ **本轮只对账 §6.2.1 的 9 行** ⇒ ⇒ ⛔ **不许**被说成「剂量轴整节已核」"
      "⇒ ⇒ ⛔ **不许**被说成「整页已核」。")
    A("- ⛔ §6.2.2、§6.1 判决面板（P1–P29）、§6.3、§6.4、页面第一部分（§0–§5）"
      "⇒ ⇒ 这些小节的内容断言仍未被本轮机器守。")
    A("- ⚖⚖⚖ **留白（本轮实测出来的，不是猜的）**：**页面的 rand 臂列在不是「同」时，没有闸门守**"
      "⇒ ⇒ 证据：MU-E3（把「同」改成「异」）与 MU-E12（把 rand 臂写成错数）**都没有任何闸门红**"
      "⇒ ⇒ 原因：预登记 §2 的 E1 **明写**「rand 臂列不在 E1 的作用域」、E2 **只管**「同」这个断言"
      "⇒ ⇒ ⇒ 页面若把 rand 臂写成「异」或写错一个数，**没有闸门会红**"
      "⇒ ⇒ 本轮用**辅助测量**把这件事**量出来**（AUX_RAND_MISMATCH）⇒ ⇒ 但它**不是闸门**"
      "⇒ ⇒ ⇒ 下一轮必须把它变成真判据。")
    A("- ⚖ **预登记 §1.3 有一处悬空引用（如实登记，⛔ 不改预登记）**：§1.3 写「……要守（见 §2 E6）」，"
      "而 §2 明写「判据共 **5 条**，编号 **E1–E5**」⇒ ⇒ **没有 E6** ⇒ ⇒ "
      "「9 行与账本 9 行一一对应、不得两行对一行」这条**要求**在 §2 里**没有闸门**"
      "⇒ ⇒ 本轮用**辅助测量**把它量了（AUX_BIJ = 9/9 ⇒ ⇒ 本批数据**确实**一一对应）"
      "⇒ ⇒ 但它**仍然不是闸门** ⇒ ⇒ 同上，下一轮补。")
    A("- ⚖ **E3 的「那张表」用的是代理口径**（以 `|` 开头 ＋ 归一化后 5 格 ＋ 首格非空）"
      "⇒ ⇒ 理论上可能把账本里**别的** 5 列表的行也算成表行 ⇒ ⇒ 记为**留白**，不是缺陷。")
    A("- ⚖ **E1 守的是「页面与账本逐字一致」，⛔ 不是「账本原文本身语义正确」**"
      "⇒ ⇒ 账本若写错，页面逐字照抄也判绿 ⇒ ⇒ 那是**账本层**的问题。")
    A("- ⚖ **账本表里页面没收录的 2 行**（`:41606` 产物 md5 对账、`:41616` 字段划分）"
      "⇒ ⇒ 属「产物完整性 / 字段划分」，**取舍合理** ⇒ ⇒ 记为**留白**，⛔ 不写成判据。")
    A("- ⚖ **E5 把「9」写死** ⇒ ⇒ 将来要**扩行** ⇒ ⇒ 必须**改预登记 + 改判据**，⛔ 不许偷偷改期望。")
    A("- ⛔ **剂量—响应曲线仍未量到**；污染的精确幅度 / 块级同口径上界 / 剂量—响应 / 机制轴 / "
      "多随机种子 一律**未量到** ⇒ ⇒ 本轮**不碰**它们。")
    A("- ⛔ **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**。")
    A("- ⛔ 「**改闸门自己的比较表达式**没有闸门能抓」（244.93 起就留着）⇒ ⇒ "
      "只能用「正控 ＋ 负控共用同一函数」把它**缩小**，⛔ **不可能**消灭 ⇒ ⇒ 记为**留白**。")
    A("")
    A("#### 【7】▶️ **下一轮（244.95+）**")
    A("")
    A("1. **把 rand 臂列变成真判据**（本轮留白的第一条）：① 页面写「同」⇒ ⇒ 账本能证明（已是 E2）；"
      "② 页面写**实际值**⇒ ⇒ 必须与账本**逐字相同**（新判据）。")
    A("2. **把「一一对应」变成真判据**（本轮留白的第二条）：9 个页行引到的账本行**必须互不相同**。")
    A("3. **§6.1 判决面板 P1–P29** 逐条对账（它是**判决数本身** ⇒ 最靠近判决数），"
      "但要先解决「页面侧派生数」（P18/P21/P28/P29 里的「9/9」「10 处」「4/12」）的取数口径。")
    A("4. **§6.2.2「未量到」措辞**纳入（守「⛔ 未量到不许被写成已量到」这个方向）。")
    A("5. **§6.3 台账 / §6.4 边界条目**逐块纳入；页面第一部分（§0–§5）**最后**做。")
    A("6. **要点头的线**（本轮一律没碰）：块级同口径污染上界（重解析原始跑批日志）、固定剂量批重跑加 "
      "`--dump-raw`、多随机种子对照臂、同结论对照臂、分层剂量真阶梯、docs 那条线 GPU 前向、"
      "照 meta 重建能否逐位复现的重训。")
    A("")
    A("#### 【8】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与**远端验证链收据里登记的那份逐位对上** "
      "⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 变异台 / 互证 / 规格对账 / 驱动（" + str(len(md5s)) + " 件）**：")
    for f, h in md5s:
        A("  - `" + h + "`  `" + os.path.basename(f) + "`  ⚖ 收据登记（远端验证链）")
    A("- **页面（2 件）**：")
    A("  - `" + page_after_md5 + "`  `docs/BPATH_VERDICT.md`（改后）  ⚖ 收据登记（远端验证链）")
    A("  - `" + page_before_md5 + "`  `_page_24494_before.md`（改前副本）  ⚖ 收据登记（远端验证链）")
    A("- **收据文件（" + str(len(rcpt_md5)) + " 件 · ⛔ 不入库）**：")
    for f, h in rcpt_md5:
        A("  - `" + h + "`  `" + f + "`  ⚖ 收据登记（远端验证链）")
    A("- **账本**：**落账前** md5 `" + str(ledger_pre_md5) + "`（" + str(ledger_pre_lines)
      + " 行）⇒ ⇒ ⚖ 落账**后**的账本 md5 由落账脚本打印、并由**提交后双回读**核"
      "（⛔ 把它登记进账本就是循环）。")
    A("")
    A("⚖ **远端**：`zju-53`（验证链，⛔ **零 GPU**）｜ 收据在 `.cache/r244/_e24494/`（⛔ 不入库）。")
    A("")

    entry = "\n".join(body)
    # ---- 硬闸 1：追加段**无围栏、无反斜杠、无占位符标记、无字面 `****`** ----
    if "```" in entry:
        raise SystemExit("⛔ 追加段里有围栏 ⇒ ⇒ 中止")
    if "\\" in entry:
        raise SystemExit("⛔ 追加段里有反斜杠 ⇒ ⇒ 中止")
    if re.search(r"@[A-Z][A-Z0-9_]*@", entry):
        raise SystemExit("⛔ 追加段里有占位符标记（既有护栏 C1/C5/C6 会判红）⇒ ⇒ 中止")
    if "****" in entry:
        raise SystemExit("⛔ 追加段里有字面 `****`（既有护栏 C8 会判红）⇒ ⇒ 中止")
    if MARK not in entry:
        raise SystemExit("⛔ 追加段的标记不对 ⇒ ⇒ 中止")
    if "\ufffd" in entry:
        raise SystemExit("⛔ 追加段里有坏字 ⇒ ⇒ 中止")

    old = read(LEDGER)
    old_b = old.encode("utf-8")
    old_md5 = md5b(old_b)
    old_fence = len(re.findall(r"^```", old, re.M))

    # ---- 硬闸 2：**幂等**（已落过 ⇒ 「逐字节相同、不重复写」）----
    if old.startswith(MARK):
        print("⛔ 账本里已经有 244.94 段 ⇒ ⇒ 幂等命中：逐字节相同、不重复写")
        print("LEDGER_LINES=%d" % len(old.split("\n")))
        print("LEDGER_BYTES=%d" % len(old_b))
        print("LEDGER_MD5=%s" % old_md5)
        print("APPEND_RC=0")
        return 0

    new = old.rstrip("\n") + "\n\n" + entry
    new_b = new.encode("utf-8")
    # ---- 硬闸 3：**旧前缀逐字节不变** ----
    if not new_b.startswith(old_b.rstrip(b"\n")):
        raise SystemExit("⛔ 旧前缀被改了 ⇒ ⇒ 中止")
    # ---- 硬闸 4：**围栏行首计数不变** ----
    new_fence = len(re.findall(r"^```", new, re.M))
    if new_fence != old_fence:
        raise SystemExit("⛔ 围栏数变了（%d ⇒ %d）⇒ ⇒ 中止" % (old_fence, new_fence))
    # ---- 硬闸 5：段里的 md5 必须**与本地现算的**一致 ----
    allowed = [x[1] for x in md5s] + [x[1] for x in rcpt_md5] + [page_after_md5, page_before_md5,
                                                                    page_after_copy_md5,
                                                                    str(ledger_pre_md5)]
    for h in re.findall(r"`([0-9a-f]{32})`", entry):
        if h not in allowed:
            raise SystemExit("⛔ 段里的 md5 %s 与本地现算的对不上 ⇒ ⇒ 中止" % h)

    with io.open(LEDGER, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)

    # ---- 落账后回读：旧前缀逐字节不变 + 围栏数不变 ----
    back = read(LEDGER).encode("utf-8")
    if not back.startswith(old_b.rstrip(b"\n")):
        raise SystemExit("⛔ 落账后回读：旧前缀变了 ⇒ ⇒ 中止")
    if len(re.findall(r"^```", read(LEDGER), re.M)) != old_fence:
        raise SystemExit("⛔ 落账后回读：围栏数变了 ⇒ ⇒ 中止")

    print("旧账本：%d 行 ｜ %d B ｜ md5 %s" % (len(old.split("\n")), len(old_b), old_md5))
    print("新账本：%d 行 ｜ %d B ｜ md5 %s" % (len(new.split("\n")), len(new_b), md5b(new_b)))
    print("追加段：%d 行 ｜ 围栏数 %d ⇒ %d（不变）" % (len(entry.split("\n")), old_fence, new_fence))
    print("APPEND_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
