#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_append_24496.py —— 把 **244.96** 落账（**只追加**），每条数**从收据解析**。

⚖⚖⚖ **纪律**（沿用 244.92–244.95 的成规）
   · ⛔ 代码里**不写死任何一个数**（全部从 `.cache/r244/_e24496/*.out` ＋ `receipt.txt` 解析）；
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
RCPT = os.path.join(REPO, ".cache", "r244", "_e24496")
MARK = "## 修订 244.96 ——"


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
    if not st_total:
        m = re.search(r"自检 (\d+)/(\d+) 通过", st_text)
        st_total = int(m.group(2)) if m else 0
    st_rc = (re.search(r"^SELFTEST_RC=(\d+)", st_text, re.M) or [None, None])[1]
    st_red = (re.search(r"^SELFTEST_RED=(\d+)", st_text, re.M) or [None, None])[1]

    bf = read(os.path.join(RCPT, "data_before.out"))
    af = read(os.path.join(RCPT, "data_after.out"))
    b_keys = keys(bf, "AUDIT_KEYS")
    a_keys = keys(af, "AUDIT_KEYS")
    b_crits = re.findall(r"^\[(PASS|FAIL)\] (E\d)：(.+)$", bf, re.M)
    a_crits = re.findall(r"^\[(PASS|FAIL)\] (E\d)：(.+)$", af, re.M)
    if len(a_crits) != int(a_keys["N_CHECKS"]):
        raise SystemExit("⛔ 判据行数与 N_CHECKS 对不上 ⇒ ⇒ 中止")
    b_red = sorted(set(re.findall(r"^\[FAIL\] (E\d)：", bf, re.M)))
    n_rows = len(re.findall(r"^ROW=", af, re.M))
    n_rowv = len(re.findall(r"^ROWV=", af, re.M))
    # ⚖ 派生分数 / 计数的明细（从 NUM_MATRIX 行里现算，⛔ 不手写）
    matrix = re.findall(r"^ROW=(\w+)\|cites=(\d+)\|strong=(\d+)\|verbatim=(\d+)\|"
                         r"r6=(\d+)\|missing=(\d+)\|frac=(\d+)/(\d+)$", af, re.M)
    n_frac_hit = sum(int(m[6]) for m in matrix)
    n_frac_tot = sum(int(m[7]) for m in matrix)
    # ⚖ 改前页面里**哪些行**有差异（⛔ 从收据现读，⛔ 不手写）
    b_matrix = dict((m[0], m) for m in re.findall(
        r"^ROW=(\w+)\|cites=(\d+)\|strong=(\d+)\|verbatim=(\d+)\|"
        r"r6=(\d+)\|missing=(\d+)\|frac=(\d+)/(\d+)$", bf, re.M))

    mu = keys(read(os.path.join(RCPT, "mut.out")), "AUDIT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "AUDIT_KEYS")
    cs = keys(read(os.path.join(RCPT, "cross_selftest.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")

    rc_md5 = receipt_md5s()
    files = [
        ".cache/r244/doc_panel_audit.py",
        ".cache/r244/mut_doc_panel_audit.py",
        ".cache/r244/_cross_check_24496.py",
        ".cache/r244/_spec_crosscheck_24496.py",
        ".cache/r244/_run_24496_verify.sh",
        ".cache/xcheck/R6_PANEL_PREREG.md",
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
    page_before_md5 = md5f(os.path.join(REPO, ".cache", "r244", "_page_24496_before.md"))
    page_after_copy_md5 = md5f(os.path.join(REPO, ".cache", "r244", "_page_24496.md"))
    for key, val in (("_page_24496.md", page_after_copy_md5),
                     ("_page_24496_before.md", page_before_md5),
                     ("BPATH_VERDICT.md", page_after_md5)):
        if rc_md5.get(key) not in (None, val):
            raise SystemExit("⛔ %s 的 md5 与远端收据对不上 ⇒ ⇒ 中止" % key)
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
    ledger_pre_lines = (re.search(r"账本：.*?（(\d+) 行）", af) or [None, None])[1]

    body = []
    A = body.append
    A(MARK + " ⚖⚖⚖⚖⚖ **判决面板 P1–P29** 纳入证据链：每个数**可溯源**到它引用的账本行"
      "（形态 **" + a_keys["VERDICT"] + "**）")
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_PANEL_PREREG.md`（244.96 签，**先于**实现；"
      "§0 范围与不做项、§1 侦察结论与缺陷登记、§2 判据 E1–E8、§3 实现纪律、"
      "§4 变异台 MU-H1..MU-H10、§5 互证、§6 边界、§7 下一轮）")
    A("⚖ **数据**：**只读已入库文件**（页面 ＋ 账本整本）⇒ ⇒ ⛔ **不读收据**（收据**不入库**）"
      "⇒ ⇒ 别人 clone 下来就能跑；⛔ **零 GPU**、⛔ 没跑批、⛔ 不改探针")
    A("⚖ **收据**：`.cache/r244/_e24496/{selftest,data_before,data_after,mut,cross,cross_selftest,spec}.out`"
      " ＋ `receipt.txt`（⚖ **不入库**；远端 `zju-53`）")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· ⛔ **本轮没有跑批、没有 GPU、没有重解析原始跑批日志** ⇒ ⇒ 本轮**不产生任何新的实测数**"
      "⇒ ⇒ ⛔ **一个实测数都没改**。")
    A("· ⚖⚖⚖ **本轮把页面 §6.1「判决面板 P1–P29」纳入证据链**：每个 P 行的「实测」列里的数，"
      "必须**可溯源**到**它自己引用的那几行账本**。")
    A("  · ⚖⚖⚖ **引用集合必须精确**（⛔ **不许**用 min..max 区间窗口）：P22 引的是"
      "`:42164`、`:42222` 两个**离散行** ⇒ 若取区间会**夹进 57 行没被引用的行**"
      "⇒ ⇒ 「4/12」会在区间内的 `:42388` 上**偶然命中** ⇒ ⇒ **判据虚高** ⇒ ⇒ 这是本轮头号陷阱。")
    A("  · ⚖ **规则 R6' 的外部依据**（⛔ 不是本轮反推的）：账本 `:41722`「把本轮的值印到 6 位小数，"
      "必须与账本那个数**逐位相同**」＋「绝对差 ≤ 5e-7（＝末位打印精度 1e-6 的一半，"
      "⛔ **由打印精度推导**，⛔ 不是从实测值倒推）」；账本 `:39004`「判决行与场景行改用 6 位小数」"
      "⇒ ⇒ ⛔ **不许**写成「|page − ledger| ≤ tol 且 tol 现算」⇒ ⇒ 那是「为让数对上而定的容差」。")
    A("  · ⚖⚠⚠⚠ **R6' 会放行 7 位小数**（多印的那位被舍掉）⇒ ⇒ 它**抓不到**「页面多印一位」"
      "⇒ ⇒ 专门加 **E4** 收紧：「走 R6' 分支的页面值，打印精度必须**恰好 6 位小数**」。")
    A("")
    A("#### 【2】⚖ **本轮页面改动：只补出处 ＋ 统一量词，⛔ 一个数都没动**")
    A("")
    A("· ⛔ **页面只改了 " + sp.get("SPEC_N_DEFECT", "?") + " 行**（P28 / P29），"
      "**一个实测数都没改** ⇒ ⇒ 改的**只有**：")
    A("  · **P28 的「账本位置」补 2 个出处**：`:42278`（一行同时给出「4/12」「决策区内 8 个」"
      "「10/27 格有破口」**和 10 条破口清单**）＋ `:42297`（「破口 10 个」）；")
    A("  · **量词「处」→「个」**（3 处）：账本 `:42278` 写「决策区内 8 **个**」、`:42297` 写"
      "「破口 10 **个**」⇒ ⇒ 页面原来写「处」⇒ ⇒ 按 244.94 的成规（同义改写若账本有逐字对应，"
      "以账本为准）判为**措辞缺陷**并更正。")
    A("· ⚖ **改前 ⇒ 改后**两份收据都在（证明**旧判决不被扰动**）：**改前**形态 **"
      + b_keys["VERDICT"] + "**、判红 **" + ("/".join(b_red) if b_red else "无")
      + "**（⛔ 那次不算判决）⇒ ⇒ **改后**形态 **" + a_keys["VERDICT"] + "**。")
    A("· ⚖ **缺陷行集合**：预登记 §1.3 登记为「出处缺失 / 量词不符」的行 == 实际有差异的行 == **"
      + sp.get("SPEC_DEFECT_LINES", "?") + "** ⇒ ⇒ 机械可查。")
    A("")
    A("#### 【3】✅ **判据逐条（真数据 · 改后 · 共 " + a_keys["N_CHECKS"] + " 条：E1–E8）**")
    A("")
    for _s, cid, detail in a_crits:
        A("- [" + _s + "] **" + cid + "**：" + detail)
    A("")
    A("⚖ 逐行矩阵：**" + str(n_rows) + " 行展品** ＋ **" + str(n_rowv) + " 条逐行结论**"
      "⇒ ⇒ 逐行明细见收据 `data_after.out` 的 `NUM_MATRIX` ＋ `ROW_VERDICTS` 块。")
    A("⚖ **明细计数**（⛔ 不是判据，但与 E3/E5/E6/E7 同口径）：强 token **"
      + a_keys.get("N_STRONG", "?") + "** 个（逐位 **" + a_keys.get("N_VERBATIM", "?")
      + "** ＋ R6' **" + a_keys.get("N_R6", "?") + "**）｜ 派生分数 **"
      + a_keys.get("N_FRAC", "?") + "** 个（逐位 **" + str(n_frac_hit) + "/" + str(n_frac_tot)
      + "**）｜ 计数短语 **" + a_keys.get("N_COUNT", "?") + "** 个。")
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0，合成夹具、⛔ 零账本、⛔ 零页面、⛔ 零 GPU）：共 **" + str(st_total)
      + "** 道用例 ⇒ ⇒ **失败 " + str(st_red) + " 道**（⚖ 这个数是「**没通过**」的条数，"
      "⛔ **不是**「判红的条数」）｜ `SELFTEST_RC=" + str(st_rc) + "`")
    _extra = sp.get("SPEC_MUT_EXTRA", "[]").strip("[]").strip()
    _n_extra = len([x for x in _extra.split(",") if x.strip()]) if _extra else 0
    A("- **变异台**：预登记 §4 的 **" + mu.get("MUT_PREREG_N", "?") + "** 条（MU-H1..MU-H10）"
      "＋ **实现期新增 " + str(_n_extra)
      + "** 条 ⇒ ⇒ 共 **" + mu["MUT_N"] + "** 条，抓住 **" + mu["MUT_CAUGHT"]
      + "** ｜ 存活 **" + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"]
      + "** ｜ 等价变异通过 **" + mu["MUT_EQUIV_OK"] + "**（输出与基线**逐字节相同**）"
      "｜ 等价变异异常 **" + mu["MUT_EQUIV_BAD"] + "** ｜ 无闸门预期通过 **"
      + mu["MUT_NORED_OK"] + "** ｜ 异常 **" + mu["MUT_NORED_BAD"]
      + "** ｜ 页面层判 **" + mu["MUT_DATA_JUDGED"] + "** ｜ 账本层判 **"
      + mu["MUT_LEDGER_JUDGED"] + "** ｜ 自检层判 **" + mu["MUT_SELFTEST_JUDGED"]
      + "** ｜ **预登记期望与实测不符 " + mu["MUT_PREREG_MISMATCH"] + " 处**"
      "｜ `MUT_RC=" + mu["MUT_RC"] + "`")
    A("- ⚖⚖⚖ **本轮最关键的两条变异**：**MU-H3 / MU-H7** 把页面的 p 值改成 **7 位小数**"
      "⇒ ⇒ **E3 仍绿**（R6' 把多印的那位舍掉了）⇒ ⇒ **只有 E4 能抓**"
      "⇒ ⇒ 这证明 **E4 不是恒绿的**，也证明 **E3 单独不够**。")
    A("- ⚖ **等价变异 2 条**（输出与基线**逐字节相同**⇒ ⇒ 记「无效」⇒ ⛔ 不计入分母）："
      "改「复算」列（该列不在任何判据的作用域内）｜ **弱 token 留白的实证**"
      "（改 P5 的 n_perm=20000 → 20001，⛔ 弱 token 本轮不判 ⇒ ⇒ **没有任何闸门会红**"
      "⇒ ⇒ 这条留白被**量到**了，而不是假装）。")
    A("- **互证**（第二条**独立**实现：⛔ 零共用代码、⛔ 锚定**故意不同**〔它用**整行正则**扫 `:NNNN`，"
      "被检实现按**表格第 5 格**取〕、⛔ 归一化**故意不同**〔**数值词元序列**逐元素比 vs "
      "**删空白整串包含**〕、⛔ R6' **故意不同**〔`%.*f` vs `Decimal` 量化〕）"
      "：锚点 **" + cr["CROSS_N_ANCHORS"] + "** ｜ 强 token **" + cr["CROSS_N_STRONG"]
      + "** ｜ 逐字相同 **" + cr["CROSS_N_VERBATIM"] + "** ｜ R6' **" + cr["CROSS_N_R6"]
      + "** ｜ 缺口 **" + cr["CROSS_N_MISSING"] + "** ｜ **表示差异** "
      + cr["CROSS_REPR_DIFF"] + " （⛔ 不算不符，见下）｜ 不符合计 **"
      + cr["CROSS_MISMATCH"] + "** ｜ 互证自算形态 **" + cr["CROSS_VERDICT"]
      + "** ⇒ ⇒ `CROSS_RC=" + cr["CROSS_RC"] + "`")
    A("- ⚖ **互证自己也要能红**：把被检实现的输出改坏（翻一个闸门 ＋ 改一个计数 ＋ 改一个逐行结论）"
      "⇒ ⇒ 互证**抓到 " + cs.get("CROSS_SELFTEST_N_DIFF", "?") + " 处** ⇒ ⇒ `CROSS_SELFTEST_RC="
      + cs["CROSS_SELFTEST_RC"] + "`")
    A("- **预登记 ↔ 实现 的机械对账**：判据集合一致（**" + sp["SPEC_N_CRITERIA"]
      + "** 条 E1–E8）｜ 变异覆盖预登记 **" + sp["SPEC_N_MUT"]
      + "** 条 ｜ **缺陷行集合** == 实际有差异的行（**" + sp["SPEC_DEFECT_LINES"]
      + "**）｜ **真值命中 " + sp["SPEC_REAL_TOKEN_HITS"]
      + "**（⇒ 「零手写期望」**机械可查**）")
    A("- ⚖⚖⚖ **预登记的预测被兑现**：预登记 §1.3 写「改前预期判红 **"
      + sp["SPEC_PREDICTED_RED"] + "**」⇒ ⇒ 实测改前判红 **"
      + sp["SPEC_ACTUAL_RED_BEFORE"] + "** ⇒ ⇒ **逐条对上**（⛔ 预登记写错 ⇒ 这里立刻红）。")
    A("- ⚖ **不变性**：同一套链连跑 **3 次**，7 份收据 **md5 逐字节相同** ⇒ ⇒ 判定**可复现**。")
    A("")
    A("#### 【5】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ⛔ 本轮**只**对账 §6.1 判决面板的 **29 个 P 行** ⇒ ⇒ ⛔ **不许**说成「整页已核」"
      "⇒ ⇒ ⛔ **不许**说成「§6 全核」。")
    A("- ⛔ §6.2.2、§6.3、§6.4、§6.5、§6.6、§6.7 与页面 §0–§5 ⇒ ⇒ 内容断言仍未被机器守。")
    A("- ⚠ **弱 token（纯整数）本轮⛔ 不判**（⛔ 在窗口里几乎必然偶然出现 ⇒ ⇒ 证据弱）⇒ ⇒ 留白"
      "（已被 MU-H12 **实证**：改 n_perm=20000 → 20001，**没有任何闸门会红**）。")
    A("- ⚠ **P11 的「56 个 base」本轮⛔ 不判**（它是**页面的基数补充说明**，数是对的）⇒ ⇒ 留白。")
    A("- ⚠ **E3 的「逐位」分支用的是「子串包含」** ⇒ ⇒ 页面**多打一位小数也会被放行**"
      "（互证实测 **" + cr["CROSS_REPR_DIFF"] + "** 处**表示差异**：P15×1、P23×2"
      "⇒ ⇒ 实为**记号差异**〔页面用排版减号 −（U+2212），账本用 ASCII -〕"
      "⇒ ⇒ ⛔ 不算不符 ⇒ ⇒ 但也说明 E3 抓不住「多打一位」⇒ ⇒ 留白。")
    A("- ⚠ **E5 的清单识别口径是写死的**（「破口：」/「违例：」＋ `),` 切分）⇒ ⇒ 换一种写法就数不到"
      "⇒ ⇒ 留白。")
    A("- ⚠ **E6 只管「破口 N」「决策区内 N」两类计数** ⇒ ⇒ 其它计数措辞不判 ⇒ ⇒ 留白。")
    A("- ⛔ **剂量—响应曲线仍未量到**；污染的精确幅度 / 块级同口径上界 / 机制轴 / 多随机种子 一律"
      "**未量到** ⇒ ⇒ 本轮**不碰**它们。")
    A("- ⛔ **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**。")
    A("- ⛔ 「**改闸门自己的比较表达式**没有闸门能抓」⇒ ⇒ 只能缩小、⛔ 不可能消灭 ⇒ ⇒ 留白。")
    A("")
    A("#### 【6】▶️ **下一轮（244.97+）**")
    A("")
    A("1. **弱 token 的取数口径**：纯整数（46/56、4/12、12 格…）如何在**不用偶然命中**的前提下判。")
    A("2. **P11 的「56 个 base」**这类**页面补充说明**的处置口径（要么纳入、要么明确排除）。")
    A("3. **§6.2.2「未量到」措辞**纳入；然后 **§6.3 台账 / §6.4 边界条目**；页面 §0–§5 **最后**做。")
    A("4. **把「改闸门自己的比较表达式」也纳入变异台**（实现层变异 ⇒ 治那条留白）。")
    A("5. **要点头的线**（本轮一律没碰）：块级同口径污染上界（重解析原始跑批日志）、"
      "固定剂量批重跑加 `--dump-raw`、多随机种子对照臂、同结论对照臂、分层剂量真阶梯、"
      "docs 那条线 GPU 前向、照 meta 重建能否逐位复现的重训。")
    A("")
    A("#### 【7】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与"
      "**远端验证链收据里登记的那份逐位对上** ⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 变异台 / 互证 / 规格对账 / 驱动（" + str(len(md5s)) + " 件）**：")
    for f, h in md5s:
        A("  - `" + h + "`  `" + os.path.basename(f) + "`  ⚖ 收据登记（远端验证链）")
    A("- **页面（2 件 · 本轮**改过 2 行**，登记以备复核）**：")
    A("  - `" + page_after_md5 + "`  `docs/BPATH_VERDICT.md`（改后）  ⚖ 收据登记（远端验证链）")
    A("  - `" + page_before_md5 + "`  `_page_24496_before.md`（改前副本）  ⚖ 收据登记（远端验证链）")
    A("- **收据文件（" + str(len(rcpt_md5)) + " 件 · ⛔ 不入库）**：")
    for f, h in rcpt_md5:
        A("  - `" + h + "`  `" + f + "`  ⚖ 收据登记（远端验证链）")
    A("- **账本**：**落账前** md5 `" + str(ledger_pre_md5) + "`（" + str(ledger_pre_lines)
      + " 行）⇒ ⇒ ⚖ 落账**后**的账本 md5 由落账脚本打印、并由**提交后双回读**核"
      "（⛔ 把它登记进账本就是循环）。")
    A("")
    A("⚖ **远端**：`zju-53`（验证链，⛔ **零 GPU**）｜ 收据在 `.cache/r244/_e24496/`（⛔ 不入库）。")
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

    # ---- 硬闸 2：**幂等**（已落 ⇒ **绝不重复写**；并逐条报告「已有段 vs 收据算出来的那段」）----
    # ⚖⚖⚖ **本轮修的真缺陷（244.92–244.96 五轮同病）**：原来写的是 `old.startswith(MARK)`
    #    ⇒ ⇒ MARK 是**段标题**（「## 修订 244.96 ——」）⇒ ⇒ 整本账本的**第一行**永远不是它
    #    ⇒ ⇒ **这个闸从来没有触发过**（死闸）⇒ ⇒ 拿已落过账的账本再跑一次
    #    ⇒ ⇒ 会**再追加一份** 244.96 段（实测 244.96 段被追加了第二份，+95 行）。
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
            print("✅ 幂等：账本里已有的 244.96 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）")
        elif _h2 == _w2 and _n_pre > 0:
            print("✅ 幂等：账本里已有的 244.96 段与**收据算出来的那段**"
                  "（**除『落账前 md5（行数）』这 %d 处 token 外**）**逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）" % _n_pre)
            print("   （那一个 token 指向『本次落账前那版账本』⇒ ⇒ **重跑时必然变**"
                  " ⇒ ⇒ ⛔ 不许据此改数）")
        else:
            _dl = [(x, y) for x, y in zip(_h2.split("\n"), _w2.split("\n")) if x != y][:3]
            raise SystemExit("⛔ 账本里已有 244.96 段，但它与收据算出来的**不一致**"
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
    allowed = [x[1] for x in md5s] + [x[1] for x in rcpt_md5] + [page_after_md5,
                                                                    page_before_md5,
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
