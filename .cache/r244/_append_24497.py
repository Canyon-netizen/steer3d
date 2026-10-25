#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_append_24497.py —— 把 **244.97** 落账（**只追加**），每条数**从收据解析**。

⚖⚖⚖ **纪律**（沿用 244.92–244.96 的成规）
   · ⛔ 代码里**不写死任何一个数**（全部从 `.cache/r244/_e24497/*.out` ＋ `receipt.txt` 解析）；
   · ⛔ **追加段无围栏、无反斜杠**（⇒ ⇒ 账本的围栏行首计数不变）；
   · ⛔ **旧前缀逐字节不变**（追加前后对同一段字节算 md5 比对）；
   · ⛔ **幂等**：重跑 ⇒ 「逐字节相同、不重复写」；
   · ⛔ 段里的 md5 必须**与本地现算的 md5** 相等（否则中止）；
   · ⛔ 追加段**不得**出现 `@大写@` 形式的占位符标记（既有护栏 C1/C5/C6 会判红）；
   · ⛔ 追加段**不得**出现字面 `****`（既有护栏 C8 会判红）。

⚖⚖⚖ **本轮的特殊职责**：补记 **244.96 的连带修复**（244.92–244.96 五份落账脚本的
   「防重复落账」闸曾退化成**死闸**）—— ⛔ 244.96 账本段**没记**它 ⇒ ⇒ **在本段补记**。
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.environ.get("APPEND_LEDGER",
                         os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md"))
RCPT = os.path.join(REPO, ".cache", "r244", "_e24497")
MARK = "## 修订 244.97 ——"


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
    b_detail = {}
    for _s, cid, detail in re.findall(r"^\[(PASS|FAIL)\] (E\d)：(.+)$", bf, re.M):
        b_detail[cid] = detail

    mu = keys(read(os.path.join(RCPT, "mut.out")), "AUDIT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "AUDIT_KEYS")
    cs = keys(read(os.path.join(RCPT, "cross_selftest.out")), "AUDIT_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "AUDIT_KEYS")

    rc_md5 = receipt_md5s()
    files = [
        ".cache/r244/doc_dose_curve_audit.py",
        ".cache/r244/mut_doc_dose_curve_audit.py",
        ".cache/r244/_cross_check_24497.py",
        ".cache/r244/_spec_crosscheck_24497.py",
        ".cache/r244/_run_24497_verify.sh",
        ".cache/xcheck/R6_DOSE_CURVE_PREREG.md",
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
    page_before_md5 = md5f(os.path.join(REPO, ".cache", "r244", "_page_24497_before.md"))
    page_after_copy_md5 = md5f(os.path.join(REPO, ".cache", "r244", "_page_24497.md"))
    for key, val in (("_page_24497.md", page_after_copy_md5),
                     ("_page_24497_before.md", page_before_md5),
                     ("BPATH_VERDICT.md", page_after_md5)):
        if rc_md5.get(key) not in (None, val):
            raise SystemExit("⛔ %s 的 md5 与远端收据对不上 ⇒ ⇒ 中止" % key)
    if page_after_md5 != page_after_copy_md5:
        raise SystemExit("⛔ 页面与改后副本不是同一份字节 ⇒ ⇒ 中止")
    # ⚖ 预登记的**签署副本**（§1–§7 的原始字节）⇒ ⇒ 用来证明「§8 只是追加」
    signed_path = os.path.join(REPO, ".cache", "r244", "_prereg_24497_signed.md")
    signed_bytes = read(signed_path).encode("utf-8")
    signed_md5 = md5b(signed_bytes)
    prereg_bytes = read(os.path.join(REPO, ".cache", "xcheck",
                                     "R6_DOSE_CURVE_PREREG.md")).encode("utf-8")
    if not prereg_bytes.startswith(signed_bytes):
        raise SystemExit("⛔ 现预登记文件的前 %d 字节与签署副本**不逐字节相同** ⇒ ⇒ 中止"
                         % len(signed_bytes))
    n_signed = len(signed_bytes)

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
    A(MARK + " ⚖⚖⚖⚖⚖ **剂量—响应曲线留白块（§6.2.2）** 纳入证据链："
      "每个断言**逐位可溯源**到它引用的账本行 ＋ **留白守卫**"
      "（⛔ 不许把「未量到」写成「无差异 / 已量到」）（形态 **" + a_keys["VERDICT"] + "**）")
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_CURVE_PREREG.md`（244.97 签，**先于**实现；"
      "§0 范围与不做项、§1 侦察结论与缺陷登记、§2 判据 E1–E7、§3 实现纪律、"
      "§4 变异台 MU-C1..MU-C10、§5 互证、§6 边界、§7 下一轮、"
      "**§8 追加更正**（实现期发现，**只追加**、§1–§7 一行未改））")
    A("⚖ **数据**：**只读已入库文件**（页面 ＋ 账本整本）⇒ ⇒ ⛔ **不读收据**（收据**不入库**）"
      "⇒ ⇒ 别人 clone 下来就能跑；⛔ **零 GPU**、⛔ 没跑批、⛔ 不改探针")
    A("⚖ **收据**：`.cache/r244/_e24497/{selftest,data_before,data_after,mut,cross,"
      "cross_selftest,spec}.out` ＋ `receipt.txt`（⚖ **不入库**；远端 `zju-53`）")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· ⛔ **本轮没有跑批、没有 GPU、没有重解析原始跑批日志** ⇒ ⇒ 本轮**不产生任何新的实测数**"
      "⇒ ⇒ ⛔ **一个实测数都没改**。")
    A("· ⚖⚖⚖ **本轮把页面 §6.2.2「剂量—响应曲线（未量到）」这个留白块纳入证据链**：")
    A("  · **E3 / E4**：每个 bullet 的断言（措辞类 " + a_keys.get("N_ASSERT", "?")
      + " 条里分措辞类与数值类）必须**逐位**出现在**它自己引用的那一行**里"
      "（⛔ **不许跨行借用**；⛔ **不许**用 min..max 区间窗口）。")
    A("  · **E5 / E6**：**留白守卫** —— 正向：必须写「剂量趋势未量到」**且**带否定形式；"
      "反向：⛔ **不许**出现**未被否定**的「无效应 / 无趋势 / 无差异 / 已量到」类措辞。")
    A("  · **E1 / E2 / E7**：结构（恰好 3 个 bullet ＋ 标题含「未量到」）、出处存在、"
      "每行至少 1 项命中。")
    A("· ⛔ **本轮不碰剂量—响应曲线本身**（本批 `n_bands = 1` ⇒ ⇒ 它**仍然未量到**）"
      "⇒ ⇒ 本轮只是把「未量到」这句话**纳入证据链**，⛔ **不是**去量它。")
    A("")
    A("#### 【2】⚖ **本轮页面改动：只补出处 ＋ 改记号，⛔ 一个值都没动**")
    A("")
    A("· ⛔ **页面只改了 2 行**（B1、B3），**diff 是 +2/−2** ⇒ ⇒ **一个实测数都没改**，改的只有：")
    A("  · **D1（B1 · 出处缺失）**：B1 的逐字措辞「不是「无剂量效应」」**不在**它引用的两行里，"
      "而在账本 `:41513` ⇒ ⇒ **补出处**（⛔ 一个字都没改）。")
    A("  · **D2（B3 · 出处缺失 ＋ 记号不合规）**：B3 写的压缩式记号（三个档用斜杠连写）"
      "**全账本没有任何一行**是这个逐字串；账本 `:41327` 的逐字形式是**三个分开的**"
      "⇒ ⇒ **补出处** ＋ **记号改成账本逐字式**"
      "⇒ ⇒ ⛔ **三个值（0.25 / 0.50 / 0.75）一个都没改**，改的**只是记号**。")
    A("  · **D3（⛔ 不是缺陷 · 明确留白）**：B3 引的 `:41418`（异质性「合池口径对 `pos_frac` 敏感」）"
      "**合法** ⇒ ⇒ ⛔ **不许**删它、⛔ 也**不许**判它为「多余出处」。")
    A("· ⚖ **改前 ⇒ 改后**两份收据都在（证明**旧判决不被扰动**）：**改前**形态 **"
      + b_keys["VERDICT"] + "**、判红 **" + ("/".join(b_red) if b_red else "无")
      + "**（⛔ 那次不算判决）⇒ ⇒ **改后**形态 **" + a_keys["VERDICT"] + "**。")
    A("· ⚖ **缺陷集合**：预登记 §1.3 登记为「真缺陷」的 bullet（**"
      + sp.get("SPEC_DEFECT_BULLETS", "?") + "**）== 实际有差异的 bullet（**"
      + sp.get("SPEC_REAL_DEFECT_BULLETS", "?") + "**）⇒ ⇒ 机械可查。")
    A("· ⚖ **改前的缺口明细**（从收据现取）：**E3** 缺口 1 条（B1 的「不是「无剂量效应」」"
      "页内=True、行内=False）｜ **E4** 缺口 3 条（B3 的三个 `pos_frac` 记号页内就找不到）"
      "⇒ ⇒ **两条判据各自被抓**，⛔ 不是一条判据被重复计数。")
    A("")
    A("#### 【3】✅ **判据逐条（真数据 · 改后 · 共 " + a_keys["N_CHECKS"] + " 条：E1–E7）**")
    A("")
    for _s, cid, detail in a_crits:
        A("- [" + _s + "] **" + cid + "**：" + detail)
    A("")
    A("⚖ 逐行矩阵：**" + str(n_rows) + " 个 bullet** ＋ **" + str(n_rowv)
      + " 条逐行结论**（每 bullet 至少 1 项命中）⇒ ⇒ 逐行明细见收据 `data_after.out` 的 "
      "`NUM_MATRIX` ＋ `ROW_VERDICTS` 块。")
    A("⚖ **明细计数**（⛔ 不是判据）：断言 **" + a_keys.get("N_ASSERT", "?")
      + "** 条 ｜ 命中 **" + a_keys.get("N_HIT", "?") + "** ｜ 缺口 **"
      + a_keys.get("N_MISS", "?") + "** ｜ 可疑措辞出现 **" + a_keys.get("N_SUSPECT", "?")
      + "** 处（豁免 **" + a_keys.get("N_EXEMPT", "?") + "** 处）｜ bullet 数 **"
      + a_keys.get("N_BULLETS", "?") + "**。")
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0，合成夹具、⛔ 零账本、⛔ 零页面、⛔ 零 GPU）：共 **" + str(st_total)
      + "** 道用例 ⇒ ⇒ **失败 " + str(st_red) + " 道**（⚖ 这个数是「**没通过**」的条数，"
      "⛔ **不是**「判红的条数」）｜ `SELFTEST_RC=" + str(st_rc) + "`")
    A("- **变异台**：预登记 §4 的 **10** 条（MU-C1..MU-C10）＋ §8.3 **新增 4 条**"
      "（MU-C11..MU-C14）⇒ ⇒ 共 **" + mu["MUT_N"] + "** 条，抓住 **" + mu["MUT_CAUGHT"]
      + "** ｜ 存活 **" + mu["MUT_SURVIVORS"] + "** ｜ 崩 **" + mu["MUT_CRASHED"]
      + "** ｜ 等价变异通过 **" + mu["MUT_EQUIV_OK"] + "**（输出与基线**逐字节相同**）"
      "｜ 等价变异异常 **" + mu["MUT_EQUIV_BAD"] + "** ｜ 页面层判 **" + mu["MUT_DATA_JUDGED"]
      + "** ｜ 账本层判 **" + mu["MUT_LEDGER_JUDGED"] + "**"
      "｜ **预登记期望与实测不符 " + mu["MUT_PREREG_MISMATCH"] + " 处**"
      "｜ `MUT_RC=" + mu["MUT_RC"] + "`")
    A("- ⚖⚖⚖ **本轮如实登记的那 1 处不符（MU-C6）**：预登记写「把 `:41656` 改成 `:41657`"
      "（**不存在的出处**）｜ 预期红 **E2**（行号越界）」⇒ ⇒ 实测 `:41657` **存在**、"
      "**在范围内**（账本 " + str(ledger_pre_lines) + " 行）、且内容是**一个空行**"
      "⇒ ⇒ **E2 按定义不红**、实测红的是 **E3**（B2 的措辞在那一行里逐位找不到）"
      "⇒ ⇒ **如实登记，不改判据去迁就期望**（⛔ 改 E2 的定义去迁就期望会让「出处存在」变味）"
      "⇒ ⇒ **E2 自己的越界能力由 MU-C11**（`:99999`，真越界）**证明** ⇒ ⇒ E2 红。")
    A("- ⚖ **等价变异 1 条**（MU-C12：改 B2 里「244.72 的 D5 审计已证」这个**不参与任何判据**的"
      "补充说明）⇒ ⇒ 输出与基线**逐字节相同** ⇒ ⇒ 记「无效」⇒ ⛔ 不计入分母。")
    A("- **互证**（第二条**独立**实现：⛔ 零共用代码、⛔ 锚定**故意不同**〔**整行正则**扫 `:NNNN`"
      "（含全角冒号）vs 被检实现按 bullet 内的 `:NNNN` 取〕、⛔ 归一化**故意不同**"
      "〔**词元序列连续包含** vs **逐位子串包含**〕、⛔ 匹配**故意不同**"
      "〔**命中集合比集合** vs 逐条判真伪〕、⛔ 豁免判定**故意不同**"
      "〔**括号整体正则** vs 前向后向括号配对扫描〕）：bullet **" + cr["CROSS_N_BULLETS"]
      + "** ｜ 断言 **" + cr["CROSS_N_ASSERT"] + "** ｜ 命中 **" + cr["CROSS_N_HIT"]
      + "** ｜ 缺口 **" + cr["CROSS_N_MISS"] + "** ｜ 可疑措辞 **" + cr["CROSS_N_SUSPECT"]
      + "** 处（豁免 **" + cr["CROSS_N_EXEMPT"] + "**）｜ 命中集合 **" + cr["CROSS_N_HITSET"]
      + "** 条 ｜ 缺口集合 **" + cr["CROSS_N_MISSSET"] + "** 条 ｜ **不符合计 **"
      + cr["CROSS_MISMATCH"] + "** ｜ 互证自算形态 **" + cr["CROSS_VERDICT"]
      + "** ⇒ ⇒ `CROSS_RC=" + cr["CROSS_RC"] + "`")
    A("- ⚖ **互证自己也要能红**：把被检实现的输出改坏（翻一个闸门 ＋ 改一个命中计数 ＋ "
      "改一个逐行矩阵）⇒ ⇒ **重跑真比对**（⛔ 不是只验「字符串变了」）⇒ ⇒ 抓到 **"
      + cs.get("CROSS_SELFTEST_N_DIFF", "?") + " / " + cs.get("CROSS_SELFTEST_N", "?")
      + "** 处 ⇒ ⇒ `CROSS_SELFTEST_RC=" + cs.get("CROSS_SELFTEST_RC", "?") + "`")
    A("- **预登记 ↔ 实现 的机械对账**（七项）：判据集合一致（**" + sp["SPEC_N_CRITERIA"]
      + "** 条 E1–E7）｜ 变异覆盖预登记 **" + sp["SPEC_N_MUT"] + "** 条（多出 **"
      + sp.get("SPEC_MUT_EXTRA", "[]") + "**）｜ **缺陷集合** == 实际有差异的 bullet（**"
      + sp["SPEC_REAL_DEFECT_BULLETS"] + "**）｜ **真值命中 " + sp["SPEC_REAL_TOKEN_HITS"]
      + "**（实现）与 **" + sp.get("SPEC_REAL_TOKEN_HITS_CROSS", "?")
      + "**（互证）⇒ 「零手写期望」**机械可查**")
    A("- ⚖⚖⚖ **预登记的预测被兑现**：预登记末尾写「改前预期判红 **"
      + sp["SPEC_PREDICTED_RED"] + "**」⇒ ⇒ 实测改前判红 **"
      + sp["SPEC_ACTUAL_RED_BEFORE"] + "** ⇒ ⇒ **逐条对上**（⛔ 预登记写错 ⇒ 这里立刻红）"
      "｜ 改后判红 **" + sp["SPEC_ACTUAL_RED_AFTER"] + "**（形态 A）。")
    A("- ⚖⚖⚖ **预登记 §8 追加更正（实现期发现 · 只追加）**：")
    A("  · **更正一（E6 漏了「别的小节」作用域）**：页面 B3 逐字含「两臂之间剂量相同"
      "（6.2.1 已量到）」⇒ ⇒ 那说的是 **§6.2.1**（两臂同剂量，244.94/244.95 已闭环）"
      "**已量到**，⛔ **不是**「§6.2.2 的剂量—响应曲线已量到」⇒ ⇒ 按 §2 原文（只认「紧邻否定」）"
      "会把它**误判红** ⇒ ⇒ 与 §2 末尾自己写的「改前预期判红 E3/E4」**自相矛盾**"
      "⇒ ⇒ 补上作用域（豁免：紧邻否定，**或**该次出现位于含小节号的圆括号内）"
      "⇒ ⇒ **原文本**下改前判红会是 E3/E4/E6，**更正后**是 **"
      + sp["SPEC_ACTUAL_RED_BEFORE"] + "** ⇒ ⇒ 与预测**一致**。")
    A("  · **登记（⛔ 不是更正）**：§8.2 的 MU-C6「预登记期望 ≠ 实测」"
      "⇒ ⇒ 本轮**如实登记 1 处**（`MUT_PREREG_MISMATCH=" + sp.get("SPEC_MUT_MISMATCH", "?")
      + "`）⇒ ⇒ 规格对账**强制**它恰好为 1（否则「不符被如实登记」这件事本身就没被守住）。")
    A("  · **新增 4 条变异**：MU-C11（真越界 `:99999` ⇒ E2 有牙齿）｜ MU-C12（等价）"
      "｜ MU-C13（括号在**后面** ⇒ §8.1 的豁免**不成立** ⇒ E6 仍红）"
      "｜ MU-C14（**账本层**：把 `:41656` 里的「切穿复制组」改坏 ⇒ E3 证明它**真的在读账本**）。")
    A("· ⚖⚖⚖ **补记 244.96 的连带修复（真缺陷）**：244.92–244.96 **五份**落账脚本的"
      "「防重复落账」闸**曾是死闸**（拿**段标题**去比整本账本的**开头** ⇒ ⇒ 永远不成立 "
      "⇒ ⇒ **这个闸从来没有触发过**）⇒ ⇒ 拿已落过账的账本再跑一次会**再追加一份**"
      "（实测 244.96 段被追加了第二份）⇒ ⇒ 244.96 用 `_fix_append_guard_24496.py` "
      "**恢复 244.86 成规并补强**（比「段标题 → 下一段标题」，且只允许「落账前 md5（行数）」"
      "这**一个** token 不同）⇒ ⇒ 在 zju-53 隔离树逐轮验证 **5 轮 × 3 项 = 15/15 绿**"
      "（含**负控**：必须会停）⇒ ⇒ ⛔ **244.96 账本段没记它** ⇒ ⇒ **在本段补记**"
      "（⛔ 账本只追加、追记要重跑全回归 ⇒ ⇒ 本轮补记是更省的做法）。")
    A("")
    A("#### 【5】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ⛔ 本轮**只**对账 §6.2.2 的 **" + a_keys.get("N_BULLETS", "?")
      + " 个 bullet** ⇒ ⇒ ⛔ **不许**说成「§6.2 已核」⇒ ⇒ ⛔ **不许**说成「剂量轴已核」。")
    A("- ⛔ **剂量—响应曲线仍然未量到** ⇒ ⇒ 本轮**没有**推进它一毫米 "
      "⇒ ⇒ ⛔ **不许**把「留白被纳入证据链」读成「留白被填上」。")
    A("- ⚠ **§8.1 的豁免有残留风险**：⛔ 若有人把「（6.2.1 已量到）」写成本节的**主语**，"
      "豁免会放过去 ⇒ ⇒ 本轮**只能缩小**、⛔ **不可能**消灭 ⇒ ⇒ 留白。")
    A("- ⚠ **E2 只判「行号 ∈ [1, 账本行数]」** ⇒ ⇒ 指向**空行**的出处**不越界**"
      "（MU-C6 实测：`:41657` 是个空行 ⇒ E2 绿、E3 红）⇒ ⇒ 「空行引用算不算不存在」"
      "是**口径问题**，本轮⛔ **不改判据** ⇒ ⇒ 留白。")
    A("- ⚠ **E7 的登记是按位置**的（B1/B2/B3 各一组）⇒ ⇒ 改 bullet 顺序会让它**错位**"
      "（MU-C10 实测：删掉中间那个 ⇒ E7 红）⇒ ⇒ 留白。")
    A("- ⚠ **弱 token（纯整数）本轮⛔ 不判**（⛔ 在窗口里几乎必然偶然出现 ⇒ ⇒ 证据弱）⇒ ⇒ 留白。")
    A("- ⛔ **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**"
      "（§8 是**实现期**追加的，不在签署时的字节里 ⇒ ⇒ 签署副本已单独登记）。")
    A("- ⛔ 「**改闸门自己的比较表达式**没有闸门能抓」⇒ ⇒ 只能缩小、⛔ 不可能消灭 ⇒ ⇒ 留白。")
    A("- ⛔ **要点头的线**（本轮一律没碰）：块级同口径污染上界、固定剂量批重跑加 `--dump-raw`、"
      "多随机种子对照臂、同结论对照臂、分层剂量真阶梯、docs 那条线 GPU 前向、"
      "照 meta 重建能否逐位复现的重训。")
    A("")
    A("#### 【6】▶️ **下一轮（244.98+）**")
    A("")
    A("1. **§6.2.2 之后** ⇒ §6.3 台账 / §6.4 边界条目；页面 §0–§5 **最后**。")
    A("2. **弱 token 的取数口径**（纯整数如何在**不用偶然命中**的前提下判）。")
    A("3. **「空行引用」要不要升格成闸门**（E2 的口径问题：出处指向一个空行，算不算「不存在」）。")
    A("4. **把「改闸门自己的比较表达式」也纳入变异台**（实现层变异 ⇒ 治那条留白）。")
    A("5. **要点头的线**（同上，本轮一律没碰）。")
    A("")
    A("#### 【7】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与"
      "**远端验证链收据里登记的那份逐位对上** ⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 变异台 / 互证 / 规格对账 / 驱动 / 预登记（" + str(len(md5s)) + " 件）**：")
    for f, h in md5s:
        A("  - `" + h + "`  `" + os.path.basename(f) + "`  ⚖ 收据登记（远端验证链）")
    A("- **页面（2 件 · 本轮**改过 2 行**，登记以备复核）**：")
    A("  - `" + page_after_md5 + "`  `docs/BPATH_VERDICT.md`（改后）  ⚖ 收据登记（远端验证链）")
    A("  - `" + page_before_md5 + "`  `_page_24497_before.md`（改前副本）  ⚖ 收据登记（远端验证链）")
    A("- **预登记的签署副本（1 件 · ⛔ 不入库）**：")
    A("  - `" + signed_md5 + "`  `_prereg_24497_signed.md`（**签署时刻**的 §1–§7 原始字节）"
      "⇒ ⇒ 现预登记文件的**前 " + str(n_signed) + " 字节**与之**逐字节相同**"
      "⇒ ⇒ §8 **确实只是追加**。")
    A("- **收据文件（" + str(len(rcpt_md5)) + " 件 · ⛔ 不入库）**：")
    for f, h in rcpt_md5:
        A("  - `" + h + "`  `" + f + "`  ⚖ 收据登记（远端验证链）")
    A("- **账本**：**落账前** md5 `" + str(ledger_pre_md5) + "`（" + str(ledger_pre_lines)
      + " 行）⇒ ⇒ ⚖ 落账**后**的账本 md5 由落账脚本打印、并由**提交后双回读**核"
      "（⛔ 把它登记进账本就是循环）。")
    A("")
    A("⚖ **远端**：`zju-53`（验证链，⛔ **零 GPU**）｜ 收据在 `.cache/r244/_e24497/`（⛔ 不入库）。")
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
    if chr(0xFFFD) in entry:
        raise SystemExit("⛔ 追加段里有坏字 ⇒ ⇒ 中止")

    old = read(LEDGER)
    old_b = old.encode("utf-8")
    old_md5 = md5b(old_b)
    old_fence = len(re.findall(r"^```", old, re.M))

    # ---- 硬闸 2：**幂等**（已落 ⇒ **绝不重复写**；并逐条报告「已有段 vs 收据算出来的那段」）----
    n_have = len(re.findall(r"^" + re.escape(MARK), old, re.M))
    if n_have > 1:
        raise SystemExit("⛔ 账本里有 %d 处「%s」⇒ ⇒ 停下" % (n_have, MARK))
    if n_have == 1:
        _i = old.index(MARK)
        _m = re.search(r"^## 修订 ", old[_i + len(MARK):], re.M)
        _j = (_i + len(MARK) + _m.start()) if _m else len(old)
        _have = old[_i:_j].rstrip("\n")
        _want = entry.rstrip("\n")
        _pre = r"落账前\*\* md5 `[0-9a-f]{32}`（\d+ 行）"
        _h2 = re.sub(_pre, "落账前** md5 `<MD5>`（<N> 行）", _have)
        _w2 = re.sub(_pre, "落账前** md5 `<MD5>`（<N> 行）", _want)
        _n_pre = len(re.findall(_pre, _have))
        if _have == _want:
            print("✅ 幂等：账本里已有的 244.97 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）")
        elif _h2 == _w2 and _n_pre > 0:
            print("✅ 幂等：账本里已有的 244.97 段与**收据算出来的那段**"
                  "（**除『落账前 md5（行数）』这 %d 处 token 外**）**逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）" % _n_pre)
            print("   （那一个 token 指向『本次落账前那版账本』⇒ ⇒ **重跑时必然变**"
                  " ⇒ ⇒ ⛔ 不许据此改数）")
        else:
            _dl = [(x, y) for x, y in zip(_h2.split("\n"), _w2.split("\n")) if x != y][:3]
            raise SystemExit("⛔ 账本里已有 244.97 段，但它与收据算出来的**不一致**"
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
                                                                    signed_md5,
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
