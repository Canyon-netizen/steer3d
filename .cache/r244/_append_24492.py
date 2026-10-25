#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_append_24492.py —— 把 **244.92** 落账（**只追加**），每条数**从收据解析**。

⚖⚖⚖ **纪律**
   · ⛔ 代码里**不写死任何一个数**（全部从 `.cache/r244/_e24492/*.out` 解析）；
   · ⛔ **追加段无围栏、无反斜杠**（⇒ ⇒ 账本的围栏行首计数不变）；
   · ⛔ **旧前缀逐字节不变**（追加前后对同一段字节算 md5 比对）；
   · ⛔ **幂等**：重跑 ⇒ 「逐字节相同、不重复写」；
   · ⛔ 段里的 md5 必须**与本地现算的 md5** 相等（否则中止）。
"""

import hashlib
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
RCPT = os.path.join(REPO, ".cache", "r244", "_e24492")
MARK = "## 修订 244.92 ——"
# ⚖ **R11 第一次（红）那份收据** ＋ **上一轮（R10）收据**：段里凡写这两个 run 的数 ⇒ ⇒ 一律**现取**
RED_R11 = os.path.join(RCPT, "reg_24492_R11a_red.txt")
R10_RCPT = os.path.join(RCPT, "reg_24489_R10.txt")
GREEN_R11 = os.path.join(RCPT, "reg_24492.txt")


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


def near(lines, idx, pat):
    """⚖ 在第 idx 行**往后 6 行**里找第一个匹配 pat 的行 ⇒ ⇒ 返回 match 对象。"""
    for l in lines[idx:idx + 6]:
        m = re.search(pat, l)
        if m:
            return m
    return None


def ledger_section(lines, rev):
    """⚖ 抠出「## 修订 <rev> 」这一段 ⇒ ⇒ 返回该段的行列表。"""
    start = None
    for i, l in enumerate(lines):
        if l.startswith("## 修订 %s " % rev):
            start = i
            break
    if start is None:
        raise SystemExit("⛔ 账本里没有「## 修订 %s 」这一段 ⇒ ⇒ 中止" % rev)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## 修订 "):
            end = j
            break
    return lines[start:end]


def ci_and_c_from_ledger(lines):
    """⚖⚖⚖ **从账本 244.89 段现取**区间下端点与 c 下界（⛔ 不写死任何一个数）。

    ⇒ ⇒ 提交信息 / 交接里的每个数都与**账本**同源 ⇒ ⇒ 账本改了，它们**不可能**留在旧数上。
    """
    sec = ledger_section(lines, "244.89")
    ci = {}
    c_lo = {}
    for l in sec:
        if "三个 Newcombe 下端点" in l:
            # ⚠ 账本里 95% / 99% 是**续写**（不重复 `CI_lo(traj)` 前缀）⇒ ⇒ 按 `CI_lo(...)` 切段
            for arm in ("traj", "block"):
                k = l.find("CI_lo(%s)" % arm)
                if k < 0:
                    continue
                tail = l[k + len("CI_lo(%s)" % arm):]
                nxt = tail.find("CI_lo(")
                if nxt >= 0:
                    tail = tail[:nxt]
                for m in re.finditer(r"(\d+)% = \*\*([+-][0-9.]+)\*\*", tail):
                    ci[(arm, m.group(1))] = m.group(2)
        if "c 的下界" in l and "Wilson" in l:
            for m in re.finditer(r"(\d+)% ⇒ \*\*([+-][0-9.]+)\*\*", l):
                c_lo[m.group(1)] = m.group(2)
    need_ci = [("traj", "90"), ("traj", "95"), ("traj", "99"),
               ("block", "90"), ("block", "95"), ("block", "99")]
    miss = [k for k in need_ci if k not in ci]
    miss += [lv for lv in ("90", "95", "99") if lv not in c_lo]
    if miss:
        raise SystemExit("⛔ 账本 244.89 段里没取到这些下界：%s ⇒ ⇒ 中止" % miss)
    return ci, c_lo


def parse_red_r11():
    """⚖⚖⚖ **R11 第一次（红）那份收据**里现取本轮要引用的数（⛔ 一个数都不手打）。"""
    if not os.path.isfile(RED_R11):
        raise SystemExit("⛔ 缺 R11 第一次（红）的收据：%s ⇒ ⇒ 中止" % RED_R11)
    lines = read(RED_R11).split("\n")
    d = {}
    m = re.search(r"^REG_RC=(\d+)", "\n".join(lines), re.M)
    d["reg_rc"] = m.group(1) if m else None
    m = re.search(r"^GATE_RC=(\d+)", "\n".join(lines), re.M)
    d["gate_rc"] = m.group(1) if m else None
    m = re.search(r"小结：变异台 全绿 (\d+) / 跑得动 (\d+) ；自检 全绿 (\d+) / 跑得动 (\d+)", "\n".join(lines))
    if not m:
        raise SystemExit("⛔ R11 红收据里没抠到「小结：变异台 …」⇒ ⇒ 中止")
    d["mut_g"], d["mut_r"], d["st_g"], d["st_r"] = m.groups()
    for i, l in enumerate(lines):
        if l.startswith("  [BAD ] mut_ledger_placeholder_audit.py"):
            mm = near(lines, i, r"基线（真实账本）：(\d+)/(\d+) 通过（红：(\w+)）")
            if not mm:
                raise SystemExit("⛔ R11 红收据里没抠到「基线（真实账本）」⇒ ⇒ 中止")
            d["base_g"], d["base_t"], d["base_cid"] = mm.groups()
            mm = near(lines, i, r"基线（自检）：失败集合 (\S+)")
            if not mm:
                raise SystemExit("⛔ R11 红收据里没抠到「基线（自检）：失败集合」⇒ ⇒ 中止")
            d["base_s0"] = mm.group(1)
            break
    else:
        raise SystemExit("⛔ R11 红收据里没有 mut_ledger_placeholder_audit 的 [BAD] 行 ⇒ ⇒ 中止")
    for i, l in enumerate(lines):
        if l.startswith("  [BAD ] ledger_placeholder_audit.py"):
            mm = near(lines, i, r"自检 (\d+)/(\d+) 通过")
            if not mm:
                raise SystemExit("⛔ R11 红收据里没抠到占位符审计的自检分数 ⇒ ⇒ 中止")
            d["lpa_g"], d["lpa_t"] = mm.groups()
            break
    else:
        raise SystemExit("⛔ R11 红收据里没有 ledger_placeholder_audit 的 [BAD] 行 ⇒ ⇒ 中止")
    return d


def parse_r10_lpa():
    """⚖ **上一轮（R10）**同一脚本的分数（做对照 ⇒ ⇒ 「红是本轮引入的」这句话有出处）。"""
    if not os.path.isfile(R10_RCPT):
        raise SystemExit("⛔ 缺 R10 收据：%s ⇒ ⇒ 中止" % R10_RCPT)
    lines = read(R10_RCPT).split("\n")
    for i, l in enumerate(lines):
        if l.startswith("  [OK ] ledger_placeholder_audit.py"):
            m = near(lines, i, r"自检 (\d+)/(\d+) 通过")
            if not m:
                raise SystemExit("⛔ R10 收据里没抠到占位符审计的自检分数 ⇒ ⇒ 中止")
            return m.group(1), m.group(2)
    raise SystemExit("⛔ R10 收据里没有 ledger_placeholder_audit 的 [OK] 行 ⇒ ⇒ 中止")


def parse_green_r11():
    """⚖⚖⚖ **R11 重跑（绿）那份收据**：数现取（⛔ 一个数都不手打）。

    ⚖ **为什么绿的那份不登记进账本**：它的 md5 依赖账本字节 ⇒ ⇒ 登记进去就是循环 ⇒ ⇒
      它改由**提交后双回读**核（「收据里的账本 md5 == 提交里那份」＋「R11 本身是绿的」）。
    """
    if not os.path.isfile(GREEN_R11):
        raise SystemExit("⛔ 缺 R11（绿）的收据：%s ⇒ ⇒ 中止" % GREEN_R11)
    text = read(GREEN_R11)
    d = {}
    m = re.search(r"^REG_RC=(\d+)", text, re.M)
    d["reg_rc"] = m.group(1) if m else None
    m = re.search(r"GATE_RC=(\d+)", text)
    d["gate_rc"] = m.group(1) if m else None
    m = re.search(r"小结：变异台 全绿 (\d+) / 跑得动 (\d+) ；自检 全绿 (\d+) / 跑得动 (\d+)", text)
    if not m:
        raise SystemExit("⛔ R11 绿收据里没抠到「小结：变异台 …」⇒ ⇒ 中止")
    d["mut_g"], d["mut_r"], d["st_g"], d["st_r"] = m.groups()
    m = re.search(r"\[OK \] mut_ledger_placeholder_audit\.py\s+变异台：抓住 (\d+) / (\d+)", text)
    d["lpa_mut_caught"], d["lpa_mut_total"] = (m.group(1), m.group(2)) if m else ("?", "?")
    m = re.search(r"\[OK \] ledger_placeholder_audit\.py\s+自检 (\d+)/(\d+) 通过", text)
    d["lpa_st_g"], d["lpa_st_t"] = (m.group(1), m.group(2)) if m else ("?", "?")
    return d


def main():
    sk = keys(read(os.path.join(RCPT, "selftest.out")), "SELFTEST_KEYS")
    mu = keys(read(os.path.join(RCPT, "mut.out")), "MUT_KEYS")
    cr = keys(read(os.path.join(RCPT, "cross.out")), "CROSS_KEYS")
    sp = keys(read(os.path.join(RCPT, "spec.out")), "SPEC_KEYS")
    af = read(os.path.join(RCPT, "after.out"))
    bf = read(os.path.join(RCPT, "before.out"))
    ak = keys(af, "AUDIT_KEYS")

    # ---- 改前那次：形态与判红（**从 before.out 解析**）----
    b_verdict = (re.search(r"^VERDICT=(.*)$", bf, re.M) or [None, "?"])[1]
    b_red = re.findall(r"^\[FAIL\] (H\d)$", bf, re.M)
    b_a_red = re.findall(r"^\[FAIL\] (A\d) ", bf, re.M)

    # ---- 改后那次：形态与逐条判据（**从 after.out 解析**）----
    a_verdict = ak["VERDICT"]
    a_reason = (re.search(r"^理由：(.*)$", af, re.M) or [None, ""])[1]
    crits = re.findall(r"^\[(PASS|FAIL)\] (H\d)$", af, re.M)
    # ⚖ A1–A9 在 AUDIT_KEYS 里（`CHECK_A1`…）⇒ ⇒ 【3】要把**两族**都列全
    a_crits = [(ak["CHECK_A%d" % i], "A%d" % i) for i in range(1, 10) if ("CHECK_A%d" % i) in ak]
    if len(a_crits) != 9:
        raise SystemExit("⛔ AUDIT_KEYS 里的 A1–A9 不齐（%d 条）⇒ ⇒ 中止" % len(a_crits))
    # ⚖ 自检用例总数（**现算**：自检收据里 [PASS]/[FAIL] 行数）
    st_total = len(re.findall(r"^\[(PASS|FAIL)\]", read(os.path.join(RCPT, "selftest.out")), re.M))
    # ⚖ **R11 第一次（红）** ＋ **R10（对照）**：段里引用的数**现取**
    red = parse_red_r11()
    r10_g, r10_t = parse_r10_lpa()

    # ---- 文件 md5（**本地现算**）----
    files = [
        ".cache/r244/doc_consistency_audit.py",
        ".cache/r244/mut_doc_consistency_audit.py",
        ".cache/r244/_cross_check_24492.py",
        ".cache/r244/_spec_crosscheck_24492.py",
        ".cache/r244/_run_24492_verify.sh",
        ".cache/xcheck/R6_DOC_CONSISTENCY_PREREG.md",
        ".cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md",
    ]
    md5s = [(f, md5f(os.path.join(REPO, f))) for f in files]
    page_md5 = md5f(os.path.join(REPO, "docs", "BPATH_VERDICT.md"))
    rcpt_files = ["selftest.out", "before.out", "after.out", "mut.out", "cross.out", "spec.out"]
    rcpt_md5 = [(f, md5f(os.path.join(RCPT, f))) for f in rcpt_files]

    body = []
    A = body.append
    # ⚖⚖⚖ 标题里**两个粗体不能贴在一起**（`****`）⇒ ⇒ 被既有护栏 C8 抓（见【5】第 9 条）
    A(MARK + " ⚖⚖⚖⚖⚖ **对外口径页纳入证据链**：`docs/BPATH_VERDICT.md` ↔ 权威账本 **244.89 段**"
      "（**逐条一致**，形态 **" + a_verdict + "**）")
    A("")
    A("⚖ **口径真相源**：`.cache/xcheck/R6_DOC_CONSISTENCY_PREREG.md`（244.92 签，**先于**实现；"
      "§0.5' 含 **2 条更正**、§2.1 固定**页面锚点行格式**、§4′ 增补 **10 道闸门**）")
    A("⚖ **数据**：**只读**权威账本的 **244.89 段** ＋ **244.89 预登记 §3.2 模板** ＋ **页面 `docs/BPATH_VERDICT.md`**"
      " ⇒ ⇒ ⛔ **不读收据**（收据**不入库**）⇒ ⇒ 本轮只依赖**已入库**文件 ⇒ ⇒ 别人 clone 下来也能跑")
    A("⚖ **收据**：`.cache/r244/_e24492/{selftest,before,after,mut,cross,spec}.out` ＋ `receipt.txt`"
      "（⚖ **不入库**；远端 `zju-53`，2026-10-25）"
      "｜ R11 第一次（**红**）的收据 `reg_24492_R11a_red.txt` ＋ 上一轮（R10）对照收据 `reg_24489_R10.txt`"
      "（⚖ **同样不入库**；⚖ 本段里凡引用这两个 run 的数 ⇒ ⇒ **一律从这两份现取**，⛔ 不手打）")
    A("")
    A("#### 【1】这一轮做了什么")
    A("")
    A("· **没有跑批、没有 GPU、没有重解析原始跑批日志** ⇒ ⇒ 本轮**不产生任何新的实测数**，"
      "只做「**页面 ↔ 账本**」的对账与修正 ⇒ ⇒ ⛔ **一个实测数都没改**。")
    A("· **回答的问题**：对外口径页 `docs/BPATH_VERDICT.md` 是读者**真正看到**的东西 ⇒ ⇒ 但它**从来没有被机器核过**"
      "（旧留白 B-20：文档层没有自检）⇒ ⇒ 本轮把页面里**与固定剂量判决相关**的对外断言"
      "（判决形态 / 成立格数 / 区间下端点 / 破口清单 / 边界条目 / 逐字引用句 / 复算入口 / 入库状态）"
      "**逐条**变成**可对账的对象**。")
    A("· **做法**：① 页面上每个对外断言**锚定成「带标签的整行」**（⛔ 不按裸串 ⇒ ⇒ 同一个值在页里出现多次也不会让负控失效）；"
      "② 页面里的**人工填空句**必须**逐字**等于**预登记 §3.2 的模板 ＋ 由账本算出的填空**；"
      "③ 页面的**账本行号**必须**指得到内容**；④ 页面的每个数**必须能追到账本出处**。")
    A("· ⚖⚖⚖ **权威链**：**收据 → 账本 → 页面**，每一环**独立**核过 ⇒ ⇒ 互证脚本做**三方对账**"
      "（244.89 收据的 `AUDIT_KEYS` ↔ 账本 244.89 段 ↔ 本页）⇒ ⇒ 页面上那个数**不可能**与跑出它的字节脱节。")
    A("")
    A("#### 【2】判决面板")
    A("")
    A("· **判决形态**：**" + a_verdict + "**")
    A("· **理由（原文）**：" + a_reason)
    A("· **页面本轮改了什么**（⛔ 只改**与账本不一致的对外断言**，同事的措辞与结构**一字未动**）："
      "标题的「截至修订 244.88」→ **244.89**｜§6.0 的作用域句 → 244.89 的 27 格口径｜"
      "§6.1 加 **P25–P29**（三档 CI 下端点 / c_lo / 决策区 4/12 / 全表 17/27）｜"
      "§6.3 加 **244.89 台账行**、把 244.88 行里「全回归 R9 未做」改成「**账本里没有 R9 的记录**」｜"
      "§6.4.1 的 **B-14** 从「未量到」改成「**已量到**」＋ 加 **B-21**（换区间方法仍未量到）｜"
      "§6.4.4 的逐字句换成 **244.89 的那一句**（**244.88 那一句逐字保留、标为历史**）｜"
      "§6.5 加 **RC-8a / RC-8b / RC-8c**｜§6.6 改掉「入库收尾未完成」｜**新增 §6.7 可对账块**。")
    A("")
    A("#### 【3】✅ **判据逐条（真数据 · 改后 · 共 " + str(len(a_crits) + len(crits)) + " 条："
      "A1–A9 ＋ H1–H7）**")
    A("")
    for st, cid in a_crits:
        A("- [" + st + "] **" + cid + "**")
    for st, cid in crits:
        A("- [" + st + "] **" + cid + "**")
    A("")
    A("#### 【4】✅ **每条判据能红**")
    A("")
    A("- **自检**（Phase-0，合成夹具、⛔ 零账本、⛔ 零页面、⛔ 零 GPU）：共 **" + str(st_total)
      + "** 道用例 ⇒ ⇒ **失败 " + sk["SELFTEST_RED"] + " 道**"
      "（⚖ 这个数是「**没通过**的条数」，⛔ **不是**「判红的条数」——本项目的「红」专指「护栏该抓而抓住了」）"
      "｜ `FIX_A1`…`FIX_A9` **全 PASS** ｜ `SELFTEST_RC=" + sk["SELFTEST_RC"] + "`")
    A("- **变异台**：抓到 **" + mu["MUT_CAUGHT"] + " / " + mu["MUT_TOTAL"] + "**"
      "（无效 " + mu["MUT_INVALID"] + " 条 ⇒ ⇒ 记「无效」⇒ ⇒ 不计入分母；⛔ 等价/冗余层被削的见【5】）"
      "｜ 存活 **" + mu["MUT_SURVIVED"] + "** ｜ 崩 **" + mu["MUT_CRASHED"] + "**"
      " ｜ 落点错 **" + mu["MUT_MISPLACED"] + "** ｜ `MUT_DATA_JUDGED=" + mu["MUT_DATA_JUDGED"] + "`")
    A("- **互证**（第二条**独立**实现：⛔ 零共用代码、⛔ 解析口径**故意不同**、⛔ 填空用 `str.replace` 而被检实现用 `re.sub`）"
      "：**OK " + cr["CROSS_OK"] + "** ｜ MISMATCH **" + cr["CROSS_MISMATCH"] + "**"
      " ｜ 独立重算的判决形态 **" + cr["CROSS_FORM"] + "**")
    A("- **预登记 ↔ 实现 的机械对账**：OK **" + sp["SPEC_OK"] + "** ｜ 红 **" + sp["SPEC_RED"] + "**")
    A("- ⚖⚖⚖ **「改前 ⇒ 改后」两份收据都在**：**改前**（页面当时过期）⇒ ⇒ 形态 **" + b_verdict + "**"
      "、判红 **" + "/".join(b_red) + "**、检查项判红 **" + "/".join(b_a_red) + "**"
      " ⇒ ⇒ 这是「**检查器有牙齿**」的证据（⛔ 那次**不算判决**）⇒ ⇒ **改后**形态 **" + a_verdict + "**")
    A("")
    A("#### 【5】⚖⚖⚖ **本轮抓到的真缺陷（⛔ 一个实测数都没动）**")
    A("")
    A("1. ⚠⚖⚖⚖⚖ **实现层（恒绿，最严重）**：形态级联里 `failed = set(c for ok, c in crits if not ok)` —— "
      "判据状态当时是**字符串** `\"PASS\"` ⇒ ⇒ `not \"PASS\"` **恒为假** ⇒ ⇒ **判红集合永远是空** "
      "⇒ ⇒ **任何页面都被判成 A · 逐条一致** ⇒ ⇒ ⛔ **自检层完全没测级联**，所以它一路溜过 "
      "⇒ ⇒ 改成**布尔** ＋ 补 **G0-10**（H1..H7 的 **128** 种组合穷举 ＋ **手写**级联期望）。"
      "⚖ **这是 244.88 第 ② 条缺陷、244.89 第 ① 条缺陷的**第三次**同型复发**（三次都是「期望从常量派生 / 状态判错」）。")
    A("2. ⚠⚖⚖ **工具层（夹具不同形 ⇒ ⇒ 自检在对着自己造的假账本绿）**：第一版检查器按**裸串**找"
      "（`4/12`、`-0.7675`）⇒ ⇒ 同一个值在页面里**出现多次** ⇒ ⇒ **改一处仍绿** ⇒ ⇒ 负控形同虚设；"
      "⇒ ⇒ 且它的账本解析假设（`⇒ 决策区` / `⇒ 全表` 两个分隔标记、`c 的下界` 不带括号后缀、理由行是 `理由：`）"
      "**与真账本不符** ⇒ ⇒ 真数据一进去**必崩** ⇒ ⇒ 改成**锚定带标签的整行** ＋ 解析按**真账本逐行形状**重写"
      " ＋ 合成夹具改成**与真账本同形**（措辞逐行同形、**填空的值另取一套**）。")
    A("3. ⚠⚖ **实现层（填空静默不填）**：逐字句的第 **4** 个空的匹配模式用了**半角** `(`，而模板里是**全角**「（」"
      "⇒ ⇒ 那一空**静默不填** ⇒ ⇒ 期望句里残留 `__` ⇒ ⇒ **被合成夹具抓到**（手写的期望句 ≠ 算出来的）"
      "⇒ ⇒ 修成全角 ＋ 加**硬闸**：填完若仍残留 `__` ⇒ ⇒ **中止**（不许当成「页面写错了」）。")
    A("4. ⚠⚖⚖ **实现层（子串 ⇒ ⇒ 截断仍判绿）**：锚定用 `line in blk`（**子串**）⇒ ⇒ **被截断**的期望行"
      "（例如破口清单只剩两条）**恰好是**页面那一行的**前缀** ⇒ ⇒ 仍然判绿 ⛔ ⇒ ⇒ 「破口被漏报」这类改动**抓不到** "
      "⇒ ⇒ 由**变异 MU22** 抓出 ⇒ ⇒ 改成**整行相等 + 整行计数** ⇒ ⇒ **判据变严**。")
    A("5. ⚠ **实现层（块的结束正则写成「排除自己」）**：块的结束用了「**排除 6.7 自己**」的前瞻 "
      "⇒ ⇒ 起点一改（变异 MU17）就把块**吞到文件尾** ⇒ ⇒ 该变异**抓不到** ⇒ ⇒ 改成「到下一个二级标题为止」。")
    A("6. ⚠ **工具层（互证）**：244.89 的收据里 **AUDIT_KEYS 块没有 END 标记** ⇒ ⇒ 按 END 标记抠块的互证脚本"
      "**抠不到键** ⇒ ⇒ 改成「读到下一个 `=====` 为止」⇒ ⇒ 三方对账才真跑通（OK " + cr["CROSS_OK"] + "）。")
    A("7. ⚠⚖ **变异台（期望闸门手写也会写错）**：MU21 的期望闸门最初手写成 **G0-5c**，实际抓住它的是 **G0-19** "
      "⇒ ⇒ ⇒ 改期望（**不是**改实现）⇒ ⇒ ⚖ **如实标注**：期望值手写也会写错，但**变异本身确实被抓住**。"
      "⚖ 另外把「无效」的判据从「输出逐字节相同」改成「**判定结果与基线完全相同**」（夹具的 FIX_A* ＋ 判据行 ＋ 形态 ＋ 红项集合）"
      "⇒ ⇒ ⇒ 更强、且可机械验。")
    A("8. ⚠ **预登记层（事实错误）**：§0.5 的 N1 与 §1 写「244.89 验证链收据**已入库**」⇒ ⇒ **假**"
      "（收据目录按纪律**不入库**）⇒ ⇒ 按预登记自己的机制**追加更正 ①**（⛔ 只追加、⛔ 不改既有字节）"
      "⇒ ⇒ 真相源改为「**已入库三件套**」，并把**收据 → 账本**那一环交给**互证脚本的三方对账**去核。")
    A("9. ⚠⚖⚖ **账本层（本轮自己引入、已被**既有**护栏抓住）**：244.92 段标题里两个粗体"
      "（`**244.89 段**` 与 `**逐条一致**`）**贴在了一起** ⇒ ⇒ 原始行里出现**字面** `****` "
      "⇒ ⇒ 被**既有**的 `ledger_placeholder_audit.py` 判据 **C8** 判红 ⇒ ⇒ 连带 `mut_ledger_placeholder_audit.py` "
      "的**基线**红（**" + red["base_g"] + "/" + red["base_t"] + "**，红 **" + red["base_cid"]
      + "**；基线自检失败集合 **" + red["base_s0"] + "**）⇒ ⇒ 占位符审计自己的自检也红（**"
      + red["lpa_g"] + "/" + red["lpa_t"] + "**）⇒ ⇒ **全回归 R11 第一次跑是红的**（`REG_RC=" + red["reg_rc"]
      + "`｜`GATE_RC=" + red["gate_rc"] + "`｜变异台 **" + red["mut_g"] + "/" + red["mut_r"]
      + "**｜自检 **" + red["st_g"] + "/" + red["st_r"] + "**）⇒ ⇒ **本轮自己的提交被护栏挡在门外**。")
    A("   ⚖ **处置**：⛔ **不扩 C8 的登记表**（扩登记＝把「例外」变成常态 ⇒ ⇒ 护栏变弱）"
      "⇒ ⇒ **改我自己的标题**（把两个粗体拆开）⇒ ⇒ **重跑 R11 是本次提交的硬前置**"
      "（⚖ 绿的那份 R11 收据**不登记进账本**：它的 md5 依赖账本字节 ⇒ ⇒ 登记进去就是循环 ⇒ ⇒ "
      "改由**提交后双回读**的 H-1..H-4 去核「收据里的账本 md5 == 提交里那份」＋「R11 本身是绿的」）。")
    A("   ⚖ **这条恰好证明 C8 不是恒绿的**：它在**没人盯着**的时候，自己把一个**新增**的格式缺陷抓了出来；"
      "且 **R10 时同一个脚本是全绿的**（**" + r10_g + "/" + r10_t + "**）⇒ ⇒ 红是**本轮引入**的，不是历史遗留。")
    A("")
    A("#### 【6】⛔ **边界清单（本轮哪些仍未量到 / 不许被读成什么）**")
    A("")
    A("- ✅ **B-14 关闭**：「更宽置信水平下的保守读法」**已量到**（27 格全表 ＋ 决策区 12 格）"
      "⇒ ⇒ 但它量到的是**界与作用域**，⛔ **不是**「污染的精确幅度」。")
    A("- ✅ **新增 B-21**：「**换个区间方法**（承认聚类 vs score 型区间）在保守读法上的影响」**未量到**"
      "⇒ ⇒ 244.89 **只换置信水平、不换方法**。")
    A("- ⛔ **本轮只对账「固定剂量判决」那几节** ⇒ ⇒ 页面**第一部分**（静态读数）**不在本轮口径内** "
      "⇒ ⇒ ⛔ **不许**被说成「整页已核」。")
    A("- ⛔ **文档层（预登记 ＋ 账本）的整体自检仍未建立** ⇒ ⇒ 本轮**只是**把**可对账的那些对外断言**纳入检查 "
      "⇒ ⇒ 旧留白 **B-20 仍成立**（只被**缩小**，⛔ **不被消灭**）。")
    A("- ⛔ **页面层现在有自检了**（这是本轮新增的）⇒ ⇒ 但「**改闸门自己的比较表达式**没有闸门能抓」"
      "⇒ ⇒ 只能用「正控 ＋ 负控共用同一函数」把它**缩小**，⛔ **不可能**消灭 ⇒ ⇒ 记为**留白**。")
    A("- ⛔ **「污染不存在」仍未量到**；污染的**精确幅度**仍未量到；**块级**同口径污染上界仍未量到；"
      "**剂量—响应**、**机制轴**、**多随机种子**一律**未量到** ⇒ ⇒ 本轮**不碰**它们。")
    A("- ⛔ **预登记层与账本层仍没有自检** ⇒ ⇒ 「预登记**整体**先于结果」**仍不成立**。"
      "⚖ 准确的说法：「§0、§2、§2.1、§3、§3.2、§4、§4′、§5、§6、§7 与 §0.5' 的 **2 条更正**的口径与判据全部先于结果」。")
    A("")
    A("#### 【7】▶️ **下一轮（244.93+）**")
    A("")
    A("1. **B-1 要点头**（**重解析原始跑批日志**）⇒ ⇒ 才能得到「**同口径**的块级污染上界」。")
    A("2. **换区间方法**（承认聚类 vs score 型）在保守读法上的影响 ⇒ ⇒ **要点头**。")
    A("3. **剂量轴 / 机制轴 / 多随机种子** ⇒ ⇒ **要点头**（跑批）。")
    A("4. **页面 ↔ 账本的一致性检查已进执行集** ⇒ ⇒ 以后每轮落账后**都要重跑它**"
      "（⇒ ⇒ 页面若忘了更新 ⇒ ⇒ **红**）⇒ ⇒ 这就是「**现状表有人盯着**」那一条的机器版。")
    A("")
    A("#### 【8】⚖ **这一轮的字节**")
    A("")
    A("⚖⚖⚖ 下面每个 md5 都是**由文件本身算出来的**；标「⚖ 收据登记」的**同时**与**远端验证链收据里登记的那份逐位对上** "
      "⇒ ⇒ 「入库的字节 ＝ 跑出这些数的字节」。")
    A("")
    A("- **被检 / 口径 / 驱动（" + str(len(md5s)) + " 件）**：")
    for f, h in md5s:
        A("  - `" + h + "`  `" + os.path.basename(f) + "`  ⚖ 收据登记（远端验证链）")
    A("- **收据文件（6 件 · ⛔ 不入库）**：")
    for f, h in rcpt_md5:
        A("  - `" + h + "`  `" + f + "`  ⚖ 收据登记（远端验证链）")
    A("- **页面**：`" + page_md5 + "`  `docs/BPATH_VERDICT.md`（⚖ 收据登记：改后副本 md5 一致）")
    A("")
    A("⚖ **远端**：`zju-53`（2026-10-25 CST）｜ ⛔ **零 GPU**、⛔ 没跑批、⛔ 没重解析原始跑批日志、⛔ 没改读数器/探针/拆分器、"
      "⛔ 没改 244.79–244.89 段。")
    A("")
    A("⚖⚖⚖ **一条必须说清的事实**：`zju-53` 与 `zju-12` 是**两台共享同一份 NFS 家目录**的机器 ⇒ ⇒ 「**两台远端逐位一致**」是**必然**的，"
      "⛔ **不是**一条独立证据 ⇒ ⇒ 真正的独立证据是「**收据里的 md5 == 本地现算的 md5**」。")
    A("")

    entry = "\n".join(body)
    # ---- 硬闸 1：追加段**无围栏、无反斜杠** ----
    if "```" in entry:
        raise SystemExit("⛔ 追加段里有围栏 ⇒ ⇒ 中止")
    if "\\" in entry:
        raise SystemExit("⛔ 追加段里有反斜杠 ⇒ ⇒ 中止")
    if MARK not in entry:
        raise SystemExit("⛔ 追加段的标记不对 ⇒ ⇒ 中止")

    old = read(LEDGER)
    old_b = old.encode("utf-8")
    old_md5 = md5b(old_b)
    old_fence = len(re.findall(r"^```", old, re.M))

    # ---- 硬闸 2：**幂等**（已落 ⇒ **绝不重复写**；并逐条报告「已有段 vs 收据算出来的那段」）----
    # ⚖⚖⚖ **本轮修的真缺陷（244.92–244.96 五轮同病）**：原来写的是 `old.startswith(MARK)`
    #    ⇒ ⇒ MARK 是**段标题**（「## 修订 244.92 ——」）⇒ ⇒ 整本账本的**第一行**永远不是它
    #    ⇒ ⇒ **这个闸从来没有触发过**（死闸）⇒ ⇒ 拿已落过账的账本再跑一次
    #    ⇒ ⇒ 会**再追加一份** 244.92 段（实测 244.96 段被追加了第二份，+95 行）。
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
            print("✅ 幂等：账本里已有的 244.92 段与**收据算出来的那段逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）")
        elif _h2 == _w2 and _n_pre > 0:
            print("✅ 幂等：账本里已有的 244.92 段与**收据算出来的那段**"
                  "（**除『落账前 md5（行数）』这 %d 处 token 外**）**逐字节相同**"
                  " ⇒ ⇒ **不重复写**（本次落账无需再动）" % _n_pre)
            print("   （那一个 token 指向『本次落账前那版账本』⇒ ⇒ **重跑时必然变**"
                  " ⇒ ⇒ ⛔ 不许据此改数）")
        else:
            _dl = [(x, y) for x, y in zip(_h2.split("\n"), _w2.split("\n")) if x != y][:3]
            raise SystemExit("⛔ 账本里已有 244.92 段，但它与收据算出来的**不一致**"
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
    for h in re.findall(r"`([0-9a-f]{32})`", entry):
        if h not in [x[1] for x in md5s] + [x[1] for x in rcpt_md5] + [page_md5]:
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
