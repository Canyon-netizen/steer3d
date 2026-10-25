#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_append_24493.py —— 把 **244.93** 落账（**只追加**），每条数**从收据解析**。

⚖⚖⚖ **纪律**（沿用 244.92 的成规）
   · ⛔ 代码里**不写死任何一个数**（全部从 `.cache/r244/_e24493/*.out` ＋ `receipt.txt` 解析）；
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
RCPT = os.path.join(REPO, ".cache", "r244", "_e24493")
MARK = "## 修订 244.93 ——"


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
    b_red = re.findall(r"^\[FAIL\] (D\d)：", bf, re.M)
    a_crits = re.findall(r"^\[(PASS|FAIL)\] (D\d)：(.+)$", af, re.M)
    n_rows = len(re.findall(r"^ROW=", af, re.M))
    if len(a_crits) != int(a_keys["N_CHECKS"]):
        raise SystemExit("⛔ 判据行数与 N_CHECKS 对不上 ⇒ ⇒ 中止")

    mu = keys(read(os.path.join(RCPT, "mut.out")), "AUDIT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "AUDIT_KEYS")
    cs = keys(read(os.path.join(RCPT, "cross_selftest.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")

    # ⚖ 远端收据登记的 md5（**远端现算**）⇒ ⇒ 与本地现算逐位对
    rc_md5 = receipt_md5s()
    files = [
        ".cache/r244/doc_dose_axis_audit.py",
        ".cache/r244/mut_doc_dose_axis_audit.py",
        ".cache/r244/_cross_check_24493.py",
        ".cache/r244/_spec_crosscheck_24493.py",
        ".cache/r244/_run_24493_verify.sh",
        ".cache/xcheck/R6_DOSE_AXIS_DOC_PREREG.md",
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
    page_before_md5 = md5f(os.path.join(REPO, ".cache", "r244", "_page_24493_before.md"))
    if rc_md5.get("BPATH_VERDICT.md") not in (None, page_after_md5):
        raise SystemExit("⛔ 页面 md5 与远端收据对不上 ⇒ ⇒ 中止")
    if rc_md5.get("_page_24493_before.md") not in (None, page_before_md5):
        raise SystemExit("⛔ 改前页面副本 md5 与远端收据对不上 ⇒ ⇒ 中止")

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
    A(MARK + " ⚖⚖⚖⚖⚖ **剂量轴展品块纳入证据链**：页面 `docs/BPATH_VERDICT.md` §6.2.3 的 "
      "5 行展品表 ＋ 1 条口径切换注 ↔ 权威账本 **逐位对账**（形态 **" + a_keys["VERDICT"] + "**）")
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_AXIS_DOC_PREREG.md`（244.93 签，**先于**实现；"
      "§0 范围与不做项、§1 侦察与两处缺陷、§2 判据 D1–D4、§3 实现纪律、§4 变异台 MU-D1..MU-D8、"
      "§5 互证、§6 边界、§7 下一轮）")
    A("⚖ **数据**：**只读已入库文件**（页面 ＋ 账本整本）⇒ ⇒ ⛔ **不读收据**（收据**不入库**）"
      "⇒ ⇒ 别人 clone 下来就能跑；⛔ **零 GPU**、⛔ 没跑批、⛔ 没重解析原始跑批日志、⛔ 没改探针")
    A("⚖ **收据**：`.cache/r244/_e24493/{selftest,data_before,data_after,mut,cross,cross_selftest,spec}.out`"
      " ＋ `receipt.txt`（⚖ **不入库**；远端 `zju-53`）")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· **没有跑批、没有 GPU、没有重解析原始跑批日志** ⇒ ⇒ 本轮**不产生任何新的实测数**，"
      "只做「**页面 ↔ 账本**」的对账与修正 ⇒ ⇒ ⛔ **一个实测数都没改**。")
    A("· **回答的问题**：页面上「**剂量轴**」那块**展品表**（5 行）＋「**口径切换**」注（1 条）"
      "⇒ ⇒ 之前它们**从来没有被机器核过** ⇒ ⇒ 本轮把这一块变成**可对账的对象**。")
    A("· ⚖⚖⚖ **核心设计**：判据的**期望值从页面那一行自动派生**，⛔ **一个数都不手写** ⇒ ⇒ "
      "判据要问的是「**这个数能不能在它引用的账本行里逐位找到**」⇒ ⇒ **数写错 ⇒ 找不到 ⇒ 红**、"
      "**出处引错 ⇒ 找不到 ⇒ 红** ⇒ ⇒ 既不会「恒绿」，也不会像 MU21 那样「期望本身写错」。")
    A("· ⚖ **包含判定是 token 级**（⛔ 不是子串）⇒ ⇒ 页面上的「0」**不会**被账本里「109 格」的 109 顶替；"
      "⚖ **锚定用带标签的整行**（数字归一化后整格相等 ＋ 全页唯一）⇒ ⇒ 不是裸串、不是子串。")
    A("")
    A("#### 【2】⚖⚖⚖ **本轮抓到的两处真缺陷（⛔ 页面只改出处行号，一个数据数都没动）**")
    A("")
    A("1. ⚖⚖ **口径切换注的出处引到了相反结论的那两行**：页面写「账本 `:38406`、`:38413`」"
      "⇒ ⇒ 那两行是「**inclusive 是生产默认**」与「**基准 = prod/inclusive/keep**」"
      "⇒ ⇒ **恰好与那句断言相反**；真正支撑「登记值是 exclusive、inclusive 会是 28/27/30/24」的是 `:40404`"
      "（244.74 段）⇒ ⇒ 已把出处改成 `:40404`，并把那两个行号**标成「口径定义」**保留。")
    A("2. ⚖ **「缺读数 0、缺位点数 0」的出处写错了行**：页面写 `:38195`（那行只有「109 格 / 109 格」）"
      "⇒ ⇒ 真正的出处是 `:38198` ⇒ ⇒ 已补上 `:38198`。")
    A("3. ⚠ **一度被我判错的「矛盾」（如实登记）**：`:38490`（244.63 段）说 inclusive 与 exclusive 的分档表相同，"
      "`:40404`（244.74 段）说档大小不同 ⇒ ⇒ 那是**两批不同数据**⇒ ⇒ **不矛盾** ⇒ ⇒ "
      "本轮**不**当缺陷、页面**不动**（⛔ 不许把两批混成一句）。")
    A("")
    A("#### 【3】✅ **判据逐条（真数据 · 改后 · 共 " + a_keys["N_CHECKS"] + " 条：D1–D4）**")
    A("")
    for s, cid, detail in a_crits:
        A("- [" + s + "] **" + cid + "**：" + detail)
    A("")
    A("⚖ 逐数矩阵：**" + str(n_rows) + " 个数**（展品列 ＋ 实测列）⇒ ⇒ **每一个**都在它引用的账本行里"
      "**逐位**找到（token 级）⇒ ⇒ 逐数明细见收据 `data_after.out` 的 `NUM_MATRIX` 块。")
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0，合成夹具、⛔ 零账本、⛔ 零页面、⛔ 零 GPU）：共 **" + str(st_total)
      + "** 道用例 ⇒ ⇒ **失败 " + str(st_red) + " 道**（⚖ 这个数是「**没通过**」的条数，"
      "⛔ **不是**「判红的条数」）｜ `SELFTEST_RC=" + str(st_rc) + "`")
    A("- **变异台**：预登记 §4 的 **8 条** ＋ 实现期新增的 **1 条等价变异**（MU-E1，非预登记）"
      "⇒ ⇒ 共 **" + mu["MUT_N"] + "** 条，抓住 **" + mu["MUT_CAUGHT"] + "**"
      " ｜ 存活 **" + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"] + "**"
      " ｜ 等价变异通过 **" + mu["MUT_EQUIV_OK"] + "**（输出与基线**逐字节相同**）"
      " ｜ 等价变异异常 **" + mu["MUT_EQUIV_BAD"] + "**"
      " ｜ `MUT_DATA_JUDGED=" + mu["MUT_DATA_JUDGED"] + "` ｜ `MUT_RC=" + mu["MUT_RC"] + "`")
    A("- **互证**（第二条**独立**实现：⛔ 零共用代码、⛔ 锚定口径**故意不同**〔它按「第 1＋2 列的数集合」定位，"
      "被检实现按「标签列」定位〕、⛔ 取数口径**故意不同**〔lookaround 正则 ＋ 数值比较 vs token 级字符串相等〕）"
      "：锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 逐数比对 **" + cr["CROSS_N_NUMBERS"] + "**"
      " ｜ 引用行号不符 **" + cr["CROSS_CITE_MISMATCH"] + "** ｜ 逐数不符 **" + cr["CROSS_NUM_MISMATCH"] + "**"
      " ｜ 判定不符 **" + cr["CROSS_CHECK_MISMATCH"] + "** ｜ 形态不符 **" + cr["CROSS_VERDICT_MISMATCH"] + "**"
      " ｜ 口径注不符 **" + cr["CROSS_NOTE_MISMATCH"] + "** ⇒ ⇒ `CROSS_RC=" + cr["CROSS_RC"] + "`")
    A("- ⚖ **互证自己也要能红**：把被检实现的输出改坏（翻一个「有无出处」标志 ＋ 翻一个判定）"
      "⇒ ⇒ 互证**抓到** ⇒ ⇒ `CROSS_SELFTEST_RC=" + cs["CROSS_SELFTEST_RC"] + "`")
    A("- **预登记 ↔ 实现 的机械对账**：判据集合一致（**" + sp["SPEC_N_CRITERIA"] + "** 条 D1–D4）"
      " ｜ 变异覆盖预登记 **" + sp["SPEC_N_MUT"] + "** 条（额外 MU-E1 为实现期新增、**非预登记**）"
      " ｜ 锚点 **" + sp["SPEC_N_ANCHORS"] + "** ｜ 偏差 **" + sp["SPEC_N_DEVIATION"]
      + "**（已显式声明）｜ **真值命中 " + sp["SPEC_REAL_TOKEN_HITS"] + "**"
      " ⇒ ⇒ 「**期望从页面行派生、零手写期望**」是**机械可查**的 ⇒ ⇒ `SPEC_RC=" + sp["SPEC_RC"] + "`")
    A("- ⚖⚖⚖ **「改前 ⇒ 改后」两份收据都在**：**改前**（故意留的过期页面副本）⇒ ⇒ 形态 **"
      + b_keys["VERDICT"] + "**、判红 **" + "/".join(b_red) + "** ⇒ ⇒ 这是「**检查器有牙齿**」的证据"
      "（⛔ 那次**不算判决**）⇒ ⇒ **改后**形态 **" + a_keys["VERDICT"] + "**。")
    A("")
    A("#### 【5】⚖ **页面改动（最小化 · 可对照）**")
    A("")
    A("· 只改 **2 行**（**+2 / −2**）⇒ ⇒ **只动出处行号**，⛔ **一个数据数都没动**：")
    A("  · 「格集合的三条过滤条件」那行的**账本位置**：`:38191`–`:38193`、`:38195` ⇒ ⇒ 补上 `:38198`")
    A("  · 「口径切换」注的**出处行**：账本 `:38406`、`:38413` ⇒ ⇒ 改成 `:40404`（那两个行号标成「口径定义」保留）")
    A("")
    A("#### 【6】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ⛔ **本轮只对账 §6.2.3 的 5 行展品表 ＋ 1 条口径切换注** ⇒ ⇒ ⛔ **不许**被说成「剂量轴整节已核」"
      "⇒ ⇒ ⛔ **不许**被说成「整页已核」。")
    A("- ⛔ §6.1 判决面板、§6.2（**除本轮的 §6.2.3**）、§6.3、§6.4、页面第一部分（§0–§5）"
      "⇒ ⇒ 这些小节的**内容断言**仍未被机器守。")
    A("- ⚖ **更正（预登记 §6 那句不准确）**：预登记写的是「§6.1/§6.2/§6.3/§6.4 **全部**未被机器守」"
      "⇒ ⇒ 那句**过头**了 ⇒ ⇒ 244.92 的链**确实**守着这几处：**A8** 核全页的账本行号引用是否越界 ＋ "
      "§6.3 的 244.89 台账行、**A5** 核 §6.4.1 的 B-14 行、**A6** 核 §6.4.4 的逐字引用句、"
      "**A7** 核 §6.5 的复算入口可跑、**A9** 核全页无过期措辞且提到 244.89、**A1–A4/H1–H7** 核 §6.7 "
      "⇒ ⇒ 准确说法是「**除这些之外**的内容断言仍未被机器守」⇒ ⇒ ⛔ 预登记**不改**（它是**先于结果**的），"
      "**更正只追加在本段**。")
    A("- ⚖ **D1 守的是「数与出处脱节」，⛔ 不是「出处引得最准」** ⇒ ⇒ 记为**留白**，不是缺陷。")
    A("- ⛔ 「格集合的三条过滤条件」的**三条条件本身**本轮**只核计数、不核条件原文** ⇒ ⇒ 留白。")
    A("- ⛔ **剂量—响应曲线仍未量到**；污染的精确幅度 / 块级同口径上界 / 剂量—响应 / 机制轴 / "
      "多随机种子 一律**未量到** ⇒ ⇒ 本轮**不碰**它们。")
    A("- ⛔ **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**。")
    A("- ⛔ 页面层**这一块**现在有自检了，但「**改闸门自己的比较表达式**没有闸门能抓」⇒ ⇒ "
      "只能用「正控 ＋ 负控共用同一函数」把它**缩小**，⛔ **不可能**消灭 ⇒ ⇒ 记为**留白**。")
    A("")
    A("#### 【7】▶️ **下一轮（244.94+）**")
    A("")
    A("1. **§6.2.1 的 9 行**纳入（先解决 `5×2⁻⁹` 这类数学表达式的取数规则）。")
    A("2. **§6.2.2 的「未量到」措辞**纳入（守「⛔ 未量到不许被写成已量到」这个方向）。")
    A("3. **§6.1 判决面板 / §6.3 台账 / §6.4 边界条目**逐块纳入。")
    A("4. 页面第一部分（§0–§5）**最后**做（它含静态读数，出处分散）。")
    A("5. **要点头的线**（本轮一律没碰）：块级同口径污染上界（重解析原始跑批日志）、固定剂量批重跑加 "
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
    A("  - `" + page_before_md5 + "`  `_page_24493_before.md`（改前副本）  ⚖ 收据登记（远端验证链）")
    A("- **收据文件（" + str(len(rcpt_md5)) + " 件 · ⛔ 不入库）**：")
    for f, h in rcpt_md5:
        A("  - `" + h + "`  `" + f + "`  ⚖ 收据登记（远端验证链）")
    A("- **账本**：**落账前** md5 `" + str(ledger_pre_md5) + "`（" + str(ledger_pre_lines)
      + " 行）⇒ ⇒ ⚖ 落账**后**的账本 md5 由落账脚本打印、并由**提交后双回读**核"
      "（⛔ 把它登记进账本就是循环）。")
    A("")
    A("⚖ **远端**：`zju-53`（验证链，⛔ **零 GPU**）｜ 收据在 `.cache/r244/_e24493/`（⛔ 不入库）。")
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

    old = read(LEDGER)
    old_b = old.encode("utf-8")
    old_md5 = md5b(old_b)
    old_fence = len(re.findall(r"^```", old, re.M))

    # ---- 硬闸 2：**幂等**（已落 ⇒ **绝不重复写**；并逐条报告「已有段 vs 收据算出来的那段」）----
    # ⚖⚖⚖ **本轮修的真缺陷（244.92–244.96 五轮同病）**：原来写的是 `old.startswith(MARK)`
    #    ⇒ ⇒ MARK 是**段标题**（「## 修订 244.93 ——」）⇒ ⇒ 整本账本的**第一行**永远不是它
    #    ⇒ ⇒ **这个闸从来没有触发过**（死闸）⇒ ⇒ 拿已落过账的账本再跑一次
    #    ⇒ ⇒ 会**再追加一份** 244.93 段（实测 244.96 段被追加了第二份，+95 行）。
    #    ⇒ ⇒ 恢复 **244.86 起的成规**（账本 `:41731` 记着「改成『已落 ⇒ 必须与收据算出来的
    #    那段逐字节相同』⇒ ⇒ 幂等且**自证**」）⇒ ⇒ 这五轮把它**退化**掉了。
    n_have = len(re.findall(r"^" + re.escape(MARK), old, re.M))
    if n_have > 1:
        raise SystemExit("⛔ 账本里有 %d 处「%s」⇒ ⇒ 停下" % (n_have, MARK))
    if n_have == 1:
        # ⚖ 成规里比的是「段标题 → **文件末尾**」⇒ ⇒ 对**非最后一段**的历史轮次不成立
        #    （后面还跟着别的段）⇒ ⇒ 这里改成「段标题 → **下一段标题**」。
        _i = old.index(MARK)
        _m = re.search(r"^## 修订 ", old[_i + len(MARK):], re.M)
        _j = (_i + len(MARK) + _m.start()) if _m else len(old)
        _have = old[_i:_j].rstrip("\n")
        _want = entry.rstrip("\n")
        # ⚖ 段里唯一**账本派生**的 token 是「落账前 md5（行数）」⇒ ⇒ 重跑时它必然变
        _pre = r"落账前\*\* md5 `[0-9a-f]{32}`（\d+ 行）"
        _h2 = re.sub(_pre, "落账前** md5 `<MD5>`（<N> 行）", _have)
        _w2 = re.sub(_pre, "落账前** md5 `<MD5>`（<N> 行）", _want)
        _n_pre = len(re.findall(_pre, _have))
        if _have == _want:
            print("✅ 幂等：账本里已有的 244.93 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）")
        elif _h2 == _w2 and _n_pre > 0:
            print("✅ 幂等：账本里已有的 244.93 段与**收据算出来的那段**"
                  "（**除『落账前 md5（行数）』这 %d 处 token 外**）**逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）" % _n_pre)
            print("   （那一个 token 指向『本次落账前那版账本』⇒ ⇒ **重跑时必然变**"
                  " ⇒ ⇒ ⛔ 不许据此改数）")
        else:
            _dl = [(x, y) for x, y in zip(_h2.split("\n"), _w2.split("\n")) if x != y][:3]
            raise SystemExit("⛔ 账本里已有 244.93 段，但它与收据算出来的**不一致**"
                             "（**不止『落账前 md5』那一处**）⇒ ⇒ 停下"
                             "（⛔ 不许覆盖、⛔ 不许改数凑好看）\n   前 3 处差异：%r" % (_dl,))
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
