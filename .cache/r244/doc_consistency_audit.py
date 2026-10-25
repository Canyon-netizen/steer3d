#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_consistency_audit.py —— 把**对外口径页** `docs/BPATH_VERDICT.md` 纳入证据链（244.92）。

⚖⚖⚖⚖⚖ **本轮是什么**（244.92）
   ① 把页面上「与固定剂量判决相关」的对外断言**逐条**与**权威账本 244.89 段**对账；
   ② 页面里**人工填空的句子**（先验固定句）必须**逐字**等于**预登记 §3.2 的模板 ＋ 由账本算出的填空**；
   ③ 页面里的**复算入口**必须**在案**（命令实跑由**验证链**留收据）；
   ④ 页面引用的**账本行号**必须**指得到内容**。

⚖⚖⚖ **真相源只有一个**：**账本**（`.cache/xcheck/R6_RERUN_PREREG.md` 的「## 修订 244.89 」段）
   ＋ **预登记**（`.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md` 的 §3.2 模板）。
   ⇒ ⇒ **不读收据**（收据**不入库**）⇒ ⇒ 本脚本只依赖**已入库**的文件 ⇒ ⇒ 别人 clone 下来也能跑。

⚖⚖⚖ **纪律**
   · ⛔ 代码里**不写死任何一个数**（含容差：容差由**账本自己的打印精度**推导）；
   · ⛔ **期望值一律从权威来源解析**，⛔ 不从被检对象（页面）派生 ⇒ ⇒ 否则「两边一起变」⇒ ⇒ 恒绿；
   · ⛔ **检查项锚定「带标签的整行」**（⛔ **不按裸串**）⇒ ⇒ 同一个值在页面里出现多次，也不会让负控失效；
   · ⛔ **每条检查项必须能红**（G0-2 逐项负控 ＋ G0-3 隔离 ＋ 运行时的「改坏一页必须红」自证）；
   · ⛔ **未量到 ≠ 无差异**：本脚本**只**判「页面与账本是否逐条一致」，
     ⛔ **不**替页面断言任何「污染不存在」之类的话。

⚖ **用法**：
   python3 doc_consistency_audit.py --selftest
   python3 doc_consistency_audit.py --data [--page P] [--ledger L] [--prereg P]
"""

import argparse
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEFAULT_PAGE = os.path.join(REPO, "docs", "BPATH_VERDICT.md")
DEFAULT_LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
DEFAULT_PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_CONFIDENCE_LEVEL_PREREG.md")

REV = "244.89"
# ⚖⚖⚖ **硬失败集合手写**（⛔ 不从任何模块常量派生 ⇒ ⇒ 否则变异会两边一起变 ⇒ ⇒ 恒绿）
HARD_FAIL_IDS = ("H1", "H2")
CRIT_IDS = ("H1", "H2", "H3", "H4", "H5", "H6", "H7")
CHECK_IDS = ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9")

# ⚖⚖⚖ **模板逐字副本**（⛔ 只给**合成夹具**用 ⇒ ⇒ 自检零外部依赖）
#    ⚠ 它与 `.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md` §3.2 的那一行必须**逐字相同**
#    ⇒ ⇒ 由**对账脚本**（`_spec_crosscheck_24492.py`）机械核对 ⇒ ⇒ 不靠人眼。
FIXTURE_TEMPLATE = (
    "> 「『污染解释不了观测差』这条结论的成立范围是：**污染只可能抬高 rand 臂**的读法"
    "（在 CI 水平 __ 上，下界 +__ pp，跨水平 __/3 成立）；"
    "在**点估计**口径下成立（__/__ 口径成立，最紧 +__ pp）；"
    "在**把抽样噪声与污染幅度同时按最保守方向**的读法下，它**只在部分水平/基准组合成立**"
    "（**决策区**（联合置信 ≥ 90%）内 __/__ 格成立、全表 __/27 格成立；违例：__）。」"
)

# ⚖⚖⚖ **手写的期望串**（⛔ **不从被检对象派生** ⇒ ⇒ 夹具与被检实现**互为对照**）
FIXTURE_QUOTE = (
    "> 「『污染解释不了观测差』这条结论的成立范围是：**污染只可能抬高 rand 臂**的读法"
    "（在 CI 水平 99 上，下界 7.333333 pp，跨水平 3/3 成立）；"
    "在**点估计**口径下成立（9/9 口径成立，最紧 15.1111 pp）；"
    "在**把抽样噪声与污染幅度同时按最保守方向**的读法下，它**只在部分水平/基准组合成立**"
    "（**决策区**（联合置信 ≥ 90%）内 4/12 格成立、全表 17/27 格成立；违例："
    "CI95/污染99/main(-0.7675, 联合 94%), CI95/污染99/zero_as_half(-1.6604, 联合 94%), "
    "CI99/污染90/main(-0.6861, 联合 89%), CI99/污染90/zero_as_half(-1.5790, 联合 89%), "
    "CI99/污染95/main(-2.6518, 联合 94%), CI99/污染95/zero_as_half(-3.5447, 联合 94%), "
    "CI99/污染95/zero_as_zero(-1.7589, 联合 94%), CI99/污染99/main(-6.3298, 联合 98%), "
    "CI99/污染99/zero_as_half(-7.2226, 联合 98%), CI99/污染99/zero_as_zero(-5.4369, 联合 98%)"
    "）。」"
)

FIXTURE_DEC_BREAKS = (
    "CI95/污染99/main(-0.7675, 联合 94%), CI95/污染99/zero_as_half(-1.6604, 联合 94%), "
    "CI99/污染95/main(-2.6518, 联合 94%), CI99/污染95/zero_as_half(-3.5447, 联合 94%), "
    "CI99/污染95/zero_as_zero(-1.7589, 联合 94%), CI99/污染99/main(-6.3298, 联合 98%), "
    "CI99/污染99/zero_as_half(-7.2226, 联合 98%), CI99/污染99/zero_as_zero(-5.4369, 联合 98%)"
)

FIXTURE_DEC_BREAKS_ALL = (
    "CI95/污染99/main(-0.7675, 联合 94%), CI95/污染99/zero_as_half(-1.6604, 联合 94%), "
    "CI99/污染90/main(-0.6861, 联合 89%), CI99/污染90/zero_as_half(-1.5790, 联合 89%), "
    "CI99/污染95/main(-2.6518, 联合 94%), CI99/污染95/zero_as_half(-3.5447, 联合 94%), "
    "CI99/污染95/zero_as_zero(-1.7589, 联合 94%), CI99/污染99/main(-6.3298, 联合 98%), "
    "CI99/污染99/zero_as_half(-7.2226, 联合 98%), CI99/污染99/zero_as_zero(-5.4369, 联合 98%)"
)

NUM_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?")
ITEM_RE = re.compile(r"CI[0-9]+/污染[0-9]+/[A-Za-z_]+\([^)]*\)")


# =============================================================================
# 读文件 / 解析
# =============================================================================
def read_text(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def ledger_lines(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read().split("\n")


def section_of(lines, rev):
    """⚖ 抠出「## 修订 <rev> 」这一段（**行号 1-based**）⇒ ⇒ 返回 (起, 止, 正文)。"""
    start = None
    for i, l in enumerate(lines):
        if l.startswith("## 修订 %s " % rev):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## 修订 "):
            end = j
            break
    return start + 1, end, "\n".join(lines[start:end])


def standalone_numbers(text):
    """⚖ 取「**独立成词**」的数（⛔ 紧邻字母/下划线/点的数字**不算数** ⇒ ⇒ 文件名里的 24492 不参与）。"""
    out = []
    for m in NUM_RE.finditer(text):
        s, e = m.start(), m.end()
        before = text[s - 1] if s > 0 else ""
        after = text[e] if e < len(text) else ""
        if before and (before.isalnum() or before in "_."):
            continue
        if after and (after.isalnum() or after in "_."):
            continue
        out.append(m.group(0))
    return out


def _after(text, start_pat, stop_pats, what):
    m = re.search(start_pat, text, re.M)
    if not m:
        raise SystemExit("⛔ 账本 %s 段里核不到「%s」的起始标记（%s）" % (REV, what, start_pat))
    tail = text[m.end():]
    cut = len(tail)
    for sp in stop_pats:
        j = tail.find(sp)
        if j != -1 and j < cut:
            cut = j
    return tail[:cut]


def parse_source(ledger_path, prereg_path):
    """⚖⚖⚖ **权威来源**：从**账本 244.89 段** ＋ **预登记 §3.2** 解析出全部期望值。"""
    lines = ledger_lines(ledger_path)
    sec = section_of(lines, REV)
    if sec is None:
        raise SystemExit("⛔ 账本里没有「## 修订 %s 」这一段 ⇒ ⇒ 中止" % REV)
    lo, hi, text = sec
    src = {"sec_lo": lo, "sec_hi": hi, "sec_text": text, "ledger_lines": len(lines)}
    src["line_at"] = {}
    for i, l in enumerate(lines[lo - 1:hi]):
        src["line_at"][lo + i] = l

    def need(pat, what):
        m = re.search(pat, text, re.M)
        if not m:
            raise SystemExit("⛔ 账本 %s 段里核不到「%s」（模式 %s）" % (REV, what, pat))
        return m

    # ---- 判决形态 / 四个计数 ----
    src["verdict"] = need(r"· \*\*判决形态\*\*：\*\*(.+?)\*\*", "判决形态").group(1)
    src["n_dec"] = int(need(r"\*\*主表 = 决策区\*\*.*?\*\*(\d+) 格\*\*", "决策区格数").group(1))
    src["n_dec_hold"] = int(need(r"\*\*主表 = 决策区\*\*.*?其中 \*\*(\d+) 格成立\*\*", "决策区成立数").group(1))
    src["n_cells"] = int(need(r"\*\*副表 = 全 (\d+) 格\*\*", "全表格数").group(1))
    src["n_all_hold"] = int(need(r"\*\*副表 = 全 \d+ 格\*\*（\*\*完整作用域\*\*）：\*\*(\d+) 格成立\*\*", "全表成立数").group(1))
    src["n_all_breaks"] = int(need(r"\*\*副表 = 全 \d+ 格\*\*（\*\*完整作用域\*\*）：\*\*\d+ 格成立\*\* ｜ 破口 (\d+) 个", "全表破口数").group(1))

    # ---- 三个 Newcombe 下端点 ＋ 三个 c 下界 ----
    m = need(r"CI_lo\(traj\) 90% = \*\*([+-][0-9.]+)\*\* ｜ 95% = \*\*([+-][0-9.]+)\*\* ｜ 99% = \*\*([+-][0-9.]+)\*\*", "CI_lo(traj)")
    src["ci_traj"] = {90: m.group(1), 95: m.group(2), 99: m.group(3)}
    m = need(r"CI_lo\(block\) 90% = \*\*([+-][0-9.]+)\*\* ｜ 95% = \*\*([+-][0-9.]+)\*\* ｜ 99% = \*\*([+-][0-9.]+)\*\*", "CI_lo(block)")
    src["ci_blk"] = {90: m.group(1), 95: m.group(2), 99: m.group(3)}
    m = need(r"c 的下界[^*]*\*\*：90% ⇒ \*\*([+-][0-9.]+)\*\* ｜ 95% ⇒ \*\*([+-][0-9.]+)\*\* ｜ 99% ⇒ \*\*([+-][0-9.]+)\*\*", "c 下界")
    src["c_lo"] = {90: m.group(1), 95: m.group(2), 99: m.group(3)}

    # ---- 理由行（点估计 / 跨水平 / 全表破口清单）----
    reason = need(r"^· \*\*理由（原文）\*\*：(.*)$", "理由").group(1)
    src["reason"] = reason
    m = re.search(r"在\*\*点估计\*\*口径下成立（(\d+)/(\d+)，最紧 ([+-][0-9.]+) pp）", reason)
    if not m:
        raise SystemExit("⛔ 理由里核不到「点估计口径」的三个数 ⇒ ⇒ 中止")
    src["pt_ok"], src["pt_n"], src["pt_min"] = m.group(1), m.group(2), m.group(3)
    m = re.search(r"在\*\*污染只抬高\*\*的读法下成立（跨水平 (\d+)/(\d+)，最紧 ([+-][0-9.]+) pp）", reason)
    if not m:
        raise SystemExit("⛔ 理由里核不到「跨水平」的三个数 ⇒ ⇒ 中止")
    src["sr_ok"], src["sr_n"], src["sr_min"] = m.group(1), m.group(2), m.group(3)
    m = re.search(r"破口：([^）]+)$", reason)
    if not m:
        raise SystemExit("⛔ 理由里核不到「破口：…」全表清单 ⇒ ⇒ 中止")
    src["viol_all"] = m.group(1).strip()

    # ---- 决策区破口清单（H5 判据行，**逐字**）----
    h5 = re.search(r"^- \[[A-Z]+\] \*\*H5\*\*.*$", text, re.M)
    if not h5:
        raise SystemExit("⛔ 账本段里核不到 H5 判据行 ⇒ ⇒ 中止")
    m = re.search(r"\*\*违例\*\*：(.+)$", h5.group(0))
    if not m:
        raise SystemExit("⛔ H5 判据行里核不到「**违例**：…」决策区清单 ⇒ ⇒ 中止")
    src["viol_dec"] = m.group(1).strip()

    # ---- 主表 / 副表（逐格，用于**自洽核对**）----
    main_blk = _after(text, r"· \*\*主表 = 决策区\*\*", ("· **副表 = 全",), "主表")
    all_blk = _after(text, r"· \*\*副表 = 全", ("· **单源读法",), "副表")
    src["main_cells"] = _cells(main_blk)
    src["all_cells"] = _cells(all_blk)
    src["n_dec_breaks"] = len([c for c in src["main_cells"] if not c["ok"]])
    src["n_dec_cells"] = len(src["main_cells"])
    src["n_all_cells"] = len(src["all_cells"])
    src["n_dec_items"] = len(ITEM_RE.findall(src["viol_dec"]))
    src["n_all_items"] = len(ITEM_RE.findall(src["viol_all"]))

    # ---- 预登记 §3.2 的**先验固定句**模板 ----
    pre = read_text(prereg_path)
    m = re.search(r"^> 「『污染解释不了观测差』.*$", pre, re.M)
    if not m:
        raise SystemExit("⛔ 预登记里核不到 §3.2 的先验固定句模板 ⇒ ⇒ 中止")
    src["template"] = m.group(0)
    return src


def _cells(block):
    """⚖ 解析作用域表的一行：`| CI | 污染 | 基准 | 界 | 联合 | … |`"""
    out = []
    for ln in block.split("\n"):
        m = re.match(r"^\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*(\S+)\s*\|\s*\*\*([+-][0-9.]+)\*\*\s*\|\s*(\d+)%\s*\|(.*)$", ln)
        if not m:
            continue
        tail = m.group(6)
        out.append({"ci": float(m.group(1)), "c": float(m.group(2)), "var": m.group(3),
                    "bound": m.group(4), "conf": int(m.group(5)),
                    "ok": "不成立" not in tail})
    return out


# =============================================================================
# 页面解析
# =============================================================================
def parse_page(page_text):
    """⚖ 从页面里抠出：244.89 块、B-xx 行、RC-xx 行、台账行、逐字引用句、账本行号引用。"""
    p = {}
    m = re.search(r"^## 6\.7 .*$", page_text, re.M)
    p["block67"] = ""
    if m:
        tail = page_text[m.start():]
        # ⚖ 块到**下一个 `## ` 标题**为止（⛔ 不许用「排除自己」的前瞻 ⇒ ⇒ 起点一改就把块吞到文件尾）
        nxt = re.search(r"^## ", tail[1:], re.M)
        p["block67"] = tail[:nxt.start() + 1] if nxt else tail
    p["b_rows"] = dict((m.group(1), m.group(0)) for m in re.finditer(r"^\| \*\*(B-\d+)\*\* \|.*$", page_text, re.M))
    p["rc_rows"] = dict((m.group(1), m.group(0)) for m in re.finditer(r"^\| \*\*(RC-\d+[a-z]?)\*\* \|.*$", page_text, re.M))
    p["ledger_rows"] = dict((m.group(1), m.group(0)) for m in re.finditer(r"^\| \*\*(244\.\d+)\*\* \|.*$", page_text, re.M))
    m = re.search(r"^> 「『污染解释不了观测差』.*$", page_text, re.M)
    p["quote"] = m.group(0) if m else ""
    p["cites"] = [int(x) for x in re.findall(r":(\d{4,6})", page_text)]
    p["text"] = page_text
    return p


# =============================================================================
# 期望值（**先验固定句 ＋ 由账本算出的填空**；**页面锚点整行**）
# =============================================================================
def expected_sentence(src):
    """⚖⚖⚖ 用**预登记的模板**逐字填空 ⇒ ⇒ 页面必须**逐字**等于它 ⇒ ⇒ 页面不许改措辞。"""
    t = src["template"]
    fills = [
        (r"在 CI 水平 __ 上", "在 CI 水平 99 上"),
        (r"下界 \+__ pp", "下界 " + src["ci_traj"][99].lstrip("+") + " pp"),
        (r"跨水平 __/3 成立", "跨水平 " + src["sr_ok"] + "/" + src["sr_n"] + " 成立"),
        (r"（__/__ 口径成立", "（" + src["pt_ok"] + "/" + src["pt_n"] + " 口径成立"),
        (r"最紧 \+__ pp", "最紧 " + src["pt_min"].lstrip("+") + " pp"),
        (r"）内 __/__ 格成立", "）内 " + str(src["n_dec_hold"]) + "/" + str(src["n_dec"]) + " 格成立"),
        (r"全表 __/27 格成立", "全表 " + str(src["n_all_hold"]) + "/" + str(src["n_cells"]) + " 格成立"),
        (r"违例：__）。", "违例：" + src["viol_all"] + "）。"),
    ]
    out = t
    for pat, rep in fills:
        out = re.sub(pat, rep.replace("\\", "\\\\"), out, count=1)
    # ⚖⚖⚖ **填空必须真的填上**：⛔ 半角/全角括号写错 ⇒ ⇒ 该空**静默不填** ⇒ ⇒ 期望句里残留「__」
    #    ⇒ ⇒ 这一条**必须**报出来（⛔ 不许当成「页面写错了」⇒ ⇒ 那是工具自己坏了）
    if "__" in out:
        raise SystemExit("⛔ 填空后模板里仍有未填的空「__」⇒ ⇒ 模板与填空模式不匹配 ⇒ ⇒ 中止")
    return out


def expected_lines(src):
    """⚖⚖⚖ **页面锚点整行**（预登记 §2.1）⇒ ⇒ 一行只归属一个检查项 ⇒ ⇒ 负控不许连坐。"""
    return {
        "L_verdict": "· **判决形态**：**" + src["verdict"] + "**",
        "L_counts": "· **保守读法**：决策区 **" + str(src["n_dec_hold"]) + "/" + str(src["n_dec"]) +
                    "** 成立，全表 **" + str(src["n_all_hold"]) + "/" + str(src["n_cells"]) + "** 成立",
        "L_allbrk": "· **全表破口**：**" + str(src["n_all_breaks"]) + " 处**",
        "L_decbrk": "· **决策区破口（" + str(src["n_dec_breaks"]) + " 格）**：" + src["viol_dec"],
        "L_ci_traj": "· **CI_lo(traj)**：90% = **" + src["ci_traj"][90] + "** ｜ 95% = **" + src["ci_traj"][95] + "** ｜ 99% = **" + src["ci_traj"][99] + "**",
        "L_ci_blk": "· **CI_lo(block)**：90% = **" + src["ci_blk"][90] + "** ｜ 95% = **" + src["ci_blk"][95] + "** ｜ 99% = **" + src["ci_blk"][99] + "**",
        "L_c_lo": "· **c 的下界**：90% ⇒ **" + src["c_lo"][90] + "** ｜ 95% ⇒ **" + src["c_lo"][95] + "** ｜ 99% ⇒ **" + src["c_lo"][99] + "**",
    }


# =============================================================================
# 检查项 A1..A9（**每条都要能红**）
# =============================================================================
def _chk(name, ok, detail):
    return {"id": name, "ok": bool(ok), "detail": detail}


def _anchor(page_text, blk, line):
    """⚖ 锚定「带标签的整行」：必须是 §6.7 块里的**一整行**（⛔ **不是子串**），
    且**全页只出现一次**（⛔ 按**整行**计数）。

    ⚖⚖⚖ **为什么必须比「整行」而不是「子串」**（244.92 的真缺陷，被变异 MU22 抓到）：
    若用 `line in blk`（子串），那么**被截断**的期望行（例如破口清单只剩两条）
    **恰好是**页面那一行的**前缀** ⇒ ⇒ 仍然判绿 ⛔ ⇒ ⇒ 「破口被漏报」这类改动**抓不到**。
    ⇒ ⇒ 这里一律按**整行**（`split("\\n")` 后的元素）比较与计数。
    """
    blk_lines = blk.split("\n")
    page_lines = page_text.split("\n")
    return (blk_lines.count(line) == 1) and (page_lines.count(line) == 1)


def run_checks(page_text, src):
    p = parse_page(page_text)
    res = []
    blk = p["block67"]
    el = expected_lines(src)

    # ---- A1：判决形态 ----
    res.append(_chk("A1", _anchor(page_text, blk, el["L_verdict"]),
                    "§6.7 块里必须有且只有一行「· **判决形态**：**" + src["verdict"] + "**」"
                    "（页面上：" + ("✅ 有" if el["L_verdict"] in blk else "⛔ 没有") +
                    "；全页出现 " + str(page_text.count(el["L_verdict"])) + " 次）"))

    # ---- A2：成立格数（决策区 __/__ 与全表 __/__）----
    res.append(_chk("A2", _anchor(page_text, blk, el["L_counts"]),
                    "§6.7 块里必须有且只有一行「" + el["L_counts"] + "」"
                    "（页面上：" + ("✅ 有" if el["L_counts"] in blk else "⛔ 没有") +
                    "；全页出现 " + str(page_text.count(el["L_counts"])) + " 次）"))

    # ---- A3：三个 CI 下端点 ＋ 三个 c 下界 ----
    miss3 = [k for k in ("L_ci_traj", "L_ci_blk", "L_c_lo") if not _anchor(page_text, blk, el[k])]
    res.append(_chk("A3", not miss3,
                    "缺：%s" % ("、".join(miss3) if miss3 else "无")))

    # ---- A4：破口清单（决策区逐格 ＋ 全表破口数）----
    miss4 = [k for k in ("L_allbrk", "L_decbrk") if not _anchor(page_text, blk, el[k])]
    res.append(_chk("A4", not miss4,
                    "缺：%s（页面必须逐字写全表破口数与决策区逐格清单）" % ("、".join(miss4) if miss4 else "无")))

    # ---- A5：边界清单里「更宽置信水平下的保守读法」必须**已量到**且**指向 244.89 段** ----
    row = p["b_rows"].get("B-14", "")
    cites5 = [int(x) for x in re.findall(r":(\d{4,6})", row)]
    ok5 = bool(row) and ("未量到" not in row) and ("已量到" in row or "✅" in row)
    ok5b = bool(cites5) and all(src["sec_lo"] <= c <= src["sec_hi"] for c in cites5)
    res.append(_chk("A5", ok5 and ok5b,
                    "B-14 行：%s ｜ 其账本行号 %s 落在 244.89 段 [%d, %d]：%s"
                    % ("✅ 已量到" if ok5 else "⛔ 仍写着未量到/缺", cites5 or "无",
                       src["sec_lo"], src["sec_hi"], "✅" if ok5b else "⛔ 没有")))

    # ---- A6：逐字引用句 ----
    exp = expected_sentence(src)
    ok6 = (p["quote"] == exp) and (exp in page_text)
    res.append(_chk("A6", ok6,
                    "页面的引用句" + ("**逐字等于**" if ok6 else "**不等于**") +
                    "预登记 §3.2 模板 ＋ 账本填空的期望句；期望句＝" + exp))

    # ---- A7：复算入口（RC-8a/8b/8c 必须在案，且必须**是可跑的命令**）----
    need_rc = ("RC-8a", "RC-8b", "RC-8c")
    miss7 = [r for r in need_rc if r not in p["rc_rows"]]
    ok7b = all(("python3" in p["rc_rows"].get(r, "") and ".py" in p["rc_rows"].get(r, ""))
               for r in need_rc)
    res.append(_chk("A7", not miss7 and ok7b,
                    "缺：%s ｜ 每条都是可跑命令（python3 + .py）：%s"
                    % (miss7 or "无", "✅" if ok7b else "⛔")))

    # ---- A8：账本行号引用必须指得到内容；244.89 的行号必须落在 244.89 段内 ----
    n_lines = src["ledger_lines"]
    bad = [c for c in p["cites"] if c < 1 or c > n_lines]
    off = []
    ok8b = False
    if p["ledger_rows"].get(REV):
        cites8 = [int(x) for x in re.findall(r":(\d{4,6})", p["ledger_rows"][REV])]
        off = [c for c in cites8 if not (src["sec_lo"] <= c <= src["sec_hi"])]
        hit = [c for c in cites8 if c in src["line_at"] and src["verdict"] in src["line_at"][c]]
        ok8b = (not off) and bool(hit)
    res.append(_chk("A8", (not bad) and ok8b,
                    "越界行号：%s ｜ 244.89 台账行：%s"
                    % (bad or "无", ("✅ 指向段内且指得到内容" if ok8b else "⛔ 段外行号 %s 或指不到内容" % (off or "无")))))

    # ---- A9：不得残留「入库收尾未完成」这类**过期状态**（措辞按页面原话）----
    stale_marks = ("入库收尾未完成", "入库待收尾", "待收尾")
    stale = [m for m in stale_marks if m in page_text]
    ok9 = (not stale) and (REV in page_text)
    res.append(_chk("A9", ok9,
                    "残留过期状态措辞：%s ｜ 页面提到 %s：%s"
                    % (stale or "无", REV, "✅" if REV in page_text else "⛔ 没有")))

    return res, p


def h5_bit_equal(page_text, src):
    """⚖ **H5**：页面的 7 个锚点行 ＋ 逐字引用句 ⇒ ⇒ **逐位**等于**由账本算出的期望**。"""
    el = expected_lines(src)
    exp = expected_sentence(src)
    blk_lines = parse_page(page_text)["block67"].split("\n")
    page_lines = page_text.split("\n")
    miss = []
    for k in sorted(el.keys()):
        if page_lines.count(el[k]) != 1:
            miss.append("%s（整行出现 %d 次）" % (k, page_lines.count(el[k])))
        elif blk_lines.count(el[k]) != 1:
            miss.append("%s（不在 §6.7 块里）" % k)
    if page_lines.count(exp) < 1:
        miss.append("逐字引用句（页面 0 次）")
    return (not miss), miss


def self_consistency(src):
    """⚖ **H2**：账本 244.89 段里的关键数**互相自洽**（账本自己的表 vs 账本自己的清单）。

    ⚖ 这条**必须在自检里也能红**（⛔ 否则「改坏账本解析」这类变异**没人抓**）。
    """
    return (
        src["n_dec"] == src["n_dec_cells"] and
        src["n_cells"] == src["n_all_cells"] and
        src["n_dec_hold"] == len([c for c in src["main_cells"] if c["ok"]]) and
        src["n_all_hold"] == len([c for c in src["all_cells"] if c["ok"]]) and
        src["n_all_hold"] + src["n_all_breaks"] == src["n_cells"] and
        src["n_dec_breaks"] == src["n_dec"] - src["n_dec_hold"] and
        src["n_dec_items"] == src["n_dec_breaks"] and
        src["n_all_items"] == src["n_all_breaks"]
    )


def h7_no_unsourced_numbers(page_text, src):
    """⚖ **H7**：§6.7 块里**每一个数**都必须能在账本 244.89 段里**逐位**找到 ⇒ ⇒ 「无出处数」= 红。

    ⚖⚖⚖ **块缺失 ⇒ ⇒ 判红**（⛔ 不许「真空绿」：块都没有 ⇒ ⇒ 无从核 ⇒ ⇒ 不许绿）。
    """
    blk = parse_page(page_text)["block67"]
    body = []
    for ln in blk.split("\n"):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        body.append(s)
    if not body:
        return False, ["§6.7 块缺失或为空 ⇒ ⇒ 无从核「无出处数」"]
    txt = "\n".join(body)
    ledger_nums = set(standalone_numbers(src["sec_text"]))
    bad = []
    for tok in standalone_numbers(txt):
        if tok not in ledger_nums:
            bad.append(tok)
    return (not bad), bad


def h6_selfproof(page_text, src):
    """⚖⚖ **H6**：把页面**人为改坏一处** ⇒ ⇒ 同一套检查**必须红** ⇒ ⇒ 证明它不是恒绿的。"""
    el = expected_lines(src)
    bad_line = el["L_counts"].replace("**" + str(src["n_dec_hold"]) + "/" + str(src["n_dec"]) + "**",
                                      "**" + str(src["n_dec_hold"] + 1) + "/" + str(src["n_dec"]) + "**", 1)
    tampered = page_text.replace(el["L_counts"], bad_line, 1)
    if tampered == page_text:
        return False, "改坏的落点没找到 ⇒ ⇒ 自证形同虚设"
    res, _p = run_checks(tampered, src)
    red = [r["id"] for r in res if not r["ok"]]
    return (bool(red)), ("改坏后判红：" + (", ".join(red) if red else "⛔ 没有一条红 ⇒ 它是恒绿的"))


# =============================================================================
# 判决（形态级联：互斥且穷尽）
# =============================================================================
def verdict_from(crits):
    """⚖ 形态级联：**硬失败集合手写**（⛔ 不从模块常量派生）。

    ⚖⚖⚖ **判据状态必须是布尔**：⛔ 用字符串 `"PASS"` 的话，`not "PASS"` 恒为假
    ⇒ ⇒ **判红集合永远是空** ⇒ ⇒ **任何页面都被判成 A**（恒绿）⇒ ⇒ 244.92 第一版就栽在这里。
    """
    failed = set(c for ok, c in crits if not ok)
    if failed & set(HARD_FAIL_IDS):
        return "E", failed
    if "H6" in failed:
        return "D", failed
    if "H5" in failed or "H7" in failed:
        return "C", failed
    if failed & {"H3", "H4"}:
        return "B", failed
    return "A", failed


# =============================================================================
# Phase-0 自检（**合成夹具**：⛔ 零账本、⛔ 零页面、⛔ 零 GPU）
# =============================================================================
def fixture_source():
    """⚖ 造一份**合成的**权威来源（⛔ 不读真账本）⇒ ⇒ 自检零外部依赖。

    ⚖ 网格与真数据**同形**（决策区 12 格：4 成立 ＋ 8 破口；全表 27 格：17 成立 ＋ 10 破口）
    ⇒ ⇒ 负控才有东西可破坏 ⇒ ⇒ 夹具**不许**是「全绿的一页」。
    ⚖ **措辞结构**与真账本**逐行同形**（⛔ 解析器必须经得起真账本的形状）。
    """
    grid = {
        (0.90, 0.90): [("main", 7.7326, True), ("zero_as_half", 6.8397, True), ("zero_as_zero", 8.6255, True)],
        (0.90, 0.95): [("main", 5.7669, True), ("zero_as_half", 4.8741, True), ("zero_as_zero", 6.6598, True)],
        (0.90, 0.99): [("main", 2.0890, True), ("zero_as_half", 1.1961, True), ("zero_as_zero", 2.9818, True)],
        (0.95, 0.90): [("main", 4.8761, True), ("zero_as_half", 3.9832, True), ("zero_as_zero", 5.7689, True)],
        (0.95, 0.95): [("main", 2.9104, True), ("zero_as_half", 2.0176, True), ("zero_as_zero", 3.8033, True)],
        (0.95, 0.99): [("main", -0.7675, False), ("zero_as_half", -1.6604, False), ("zero_as_zero", 0.1253, True)],
        (0.99, 0.90): [("main", -0.6861, False), ("zero_as_half", -1.5790, False), ("zero_as_zero", 0.2067, True)],
        (0.99, 0.95): [("main", -2.6518, False), ("zero_as_half", -3.5447, False), ("zero_as_zero", -1.7589, False)],
        (0.99, 0.99): [("main", -6.3298, False), ("zero_as_half", -7.2226, False), ("zero_as_zero", -5.4369, False)],
    }
    decision = {(0.95, 0.95), (0.95, 0.99), (0.99, 0.95), (0.99, 0.99)}
    main, allr = [], []
    for (ci, c), rows in sorted(grid.items()):
        conf = int(round(ci * 100)) + int(round(c * 100)) - 100
        for var, b, ok in rows:
            mark = "✅ 成立" if ok else "⛔ **不成立**"
            if (ci, c) in decision:
                main.append("| %.2f | %.2f | %s | **%+.4f** | %d%% | %s |" % (ci, c, var, b, conf, mark))
                allr.append("| %.2f | %.2f | %s | **%+.4f** | %d%% | 是 | %s |" % (ci, c, var, b, conf, mark))
            else:
                allr.append("| %.2f | %.2f | %s | **%+.4f** | %d%% | — | %s |" % (ci, c, var, b, conf, mark))
    main = "\n".join(main)
    allr = "\n".join(allr)
    sec = (
        "## 修订 244.89 —— 合成夹具（形态 **B'**）\n\n"
        "· **判决形态**：**B'**\n\n"
        "· **理由（原文）**：保守读法在 10/27 格有破口（**决策区内 8 个**）⇒ ⇒ **结论要收紧**：「污染解释不了观测差」"
        "在**污染只抬高**的读法下成立（跨水平 3/3，最紧 +7.3333 pp），在**点估计**口径下成立"
        "（9/9，最紧 +15.1111 pp）；在**抽样噪声与污染幅度同时最保守**的读法下**只在部分水平/基准组合成立**"
        "（决策区 4/12 格成立）。破口：" + FIXTURE_DEC_BREAKS_ALL + "\n\n"
        "· **主表 = 决策区**（联合置信 ≥ 90%；**12 格**，其中 **4 格成立**）：\n\n"
        + main + "\n\n"
        "· **副表 = 全 27 格**（**完整作用域**）：**17 格成立** ｜ 破口 10 个\n\n"
        + allr + "\n\n"
        "· ⚖ **三个 Newcombe 下端点**：CI_lo(traj) 90% = **+15.111111** ｜ 95% = **+13.222222** ｜ 99% = **+7.333333**；"
        "CI_lo(block) 90% = **+32.444444** ｜ 95% = **+27.555555** ｜ 99% = **+19.666666**\n\n"
        "· ⚖ **c 的下界（Wilson；随水平变宽）**：90% ⇒ **-8.777777** ｜ 95% ⇒ **-10.888888** ｜ 99% ⇒ **-13.999999**（main 基准）\n\n"
        "- [FAIL] **H5** 保守读法·决策区（联合 ≥ 90%·运算③） — 决策区 12 格（联合 ≥ 90%）｜ 4 成立 ｜ **违例**：" + FIXTURE_DEC_BREAKS + "\n"
    )
    src = {"sec_lo": 42259, "sec_hi": 42419, "sec_text": sec, "ledger_lines": 42419,
           "verdict": "B'", "n_dec": 12, "n_dec_hold": 4, "n_cells": 27, "n_all_hold": 17,
           "n_all_breaks": 10,
           "ci_traj": {90: "+15.111111", 95: "+13.222222", 99: "+7.333333"},
           "ci_blk": {90: "+32.444444", 95: "+27.555555", 99: "+19.666666"},
           "c_lo": {90: "-8.777777", 95: "-10.888888", 99: "-13.999999"},
           "pt_ok": "9", "pt_n": "9", "pt_min": "+15.1111",
           "sr_ok": "3", "sr_n": "3", "sr_min": "+7.3333",
           "viol_dec": FIXTURE_DEC_BREAKS,
           "viol_all": FIXTURE_DEC_BREAKS_ALL,
           "template": FIXTURE_TEMPLATE}
    src["main_cells"] = _cells(main)
    src["all_cells"] = _cells(allr)
    src["n_dec_breaks"] = len([c for c in src["main_cells"] if not c["ok"]])
    src["n_dec_cells"] = len(src["main_cells"])
    src["n_all_cells"] = len(src["all_cells"])
    src["n_dec_items"] = len(ITEM_RE.findall(src["viol_dec"]))
    src["n_all_items"] = len(ITEM_RE.findall(src["viol_all"]))
    src["line_at"] = {42259: "## 修订 244.89 —— 合成夹具（形态 **B'**）",
                      42419: "· ⚖ **c 的下界（Wilson；随水平变宽）**：90% ⇒ **-8.777777**"}
    return src


def fixture_page(src):
    """⚖ 造一份**合成的**「页面」：照本页要用的**锚点**写 ⇒ ⇒ 自检零外部依赖。

    ⚖⚖⚖ 这里的 7 行与引用句**全部手写**（⛔ **不调用** `expected_lines` / `expected_sentence`）
    ⇒ ⇒ 否则「改期望值」的变异会**两边一起变** ⇒ ⇒ 恒绿。
    """
    lines = []
    lines.append("# 合成页面")
    lines.append("| **B-14** | 更宽置信水平下的保守读法 | ✅ 已量到 | `:42300` |")
    lines.append("| **RC-8a** | `python3 .cache/r244/confidence_level_audit.py --data` | 读数 | ✅ |")
    lines.append("| **RC-8b** | `python3 .cache/r244/_cross_check_24492.py` | 读数 | ✅ |")
    lines.append("| **RC-8c** | `python3 .cache/r244/doc_consistency_audit.py --data` | 读数 | ✅ |")
    lines.append("| **244.89** | **B'** | … | `:42259` |")
    lines.append("")
    lines.append("## 6.7 合成可对账块")
    lines.append("")
    lines.append("· **判决形态**：**B'**")
    lines.append("· **保守读法**：决策区 **4/12** 成立，全表 **17/27** 成立")
    lines.append("· **全表破口**：**10 处**")
    lines.append("· **决策区破口（8 格）**：" + FIXTURE_DEC_BREAKS)
    lines.append("· **CI_lo(traj)**：90% = **+15.111111** ｜ 95% = **+13.222222** ｜ 99% = **+7.333333**")
    lines.append("· **CI_lo(block)**：90% = **+32.444444** ｜ 95% = **+27.555555** ｜ 99% = **+19.666666**")
    lines.append("· **c 的下界**：90% ⇒ **-8.777777** ｜ 95% ⇒ **-10.888888** ｜ 99% ⇒ **-13.999999**")
    lines.append("")
    lines.append(FIXTURE_QUOTE)
    return "\n".join(lines) + "\n"


def selftest():
    """⚖ Phase-0：合成夹具、⛔ 零账本、⛔ 零页面、⛔ 零 GPU。"""
    src = fixture_source()
    page = fixture_page(src)
    res, _p = run_checks(page, src)
    out = []
    g_ok = True

    def rec(gid, ok, detail):
        nonlocal g_ok
        out.append("[%s] %s %s" % ("PASS" if ok else "FAIL", gid, detail))
        if not ok:
            g_ok = False

    # G0-1：正控（合成页面全绿）
    reds = [r["id"] for r in res if not r["ok"]]
    rec("G0-1", not reds, "合成页面 ⇒ 判红：%s（期望 0）" % (reds or "无"))

    # G0-2：逐项负控（每个检查项各有一个只破坏它的负控）
    neg = {
        "A1": lambda t: t.replace("· **判决形态**：**B'**", "· **判决形态**：**A'**", 1),
        "A2": lambda t: t.replace("· **保守读法**：决策区 **4/12** 成立，全表 **17/27** 成立",
                                  "· **保守读法**：决策区 **5/12** 成立，全表 **17/27** 成立", 1),
        "A3": lambda t: t.replace("**+7.333333**", "**+7.333334**", 1),
        "A4": lambda t: t.replace("-0.7675", "-0.7674", 1),
        "A5": lambda t: t.replace("✅ 已量到", "⛔ 未量到", 1),
        "A6": lambda t: t.replace("污染只可能抬高 rand 臂", "污染可能抬高 rand 臂", 1),
        "A7": lambda t: t.replace("| **RC-8b** |", "| **RC-9b** |", 1),
        "A8": lambda t: t.replace("`:42259`", "`:42000`", 1),
        "A9": lambda t: t + "\n（244.89 的入库待收尾）\n",
    }
    for cid, mut in neg.items():
        t2 = mut(page)
        if t2 == page:
            rec("G0-2/%s" % cid, False, "负控的落点没找到 ⇒ ⇒ 负控形同虚设")
            continue
        r2, _ = run_checks(t2, src)
        red2 = [r["id"] for r in r2 if not r["ok"]]
        rec("G0-2/%s" % cid, cid in red2, "破坏 %s ⇒ 判红：%s（必须含 %s）" % (cid, red2 or "⛔ 没有", cid))

    # G0-3：隔离性（每个负控只红它自己）
    for cid, mut in neg.items():
        t2 = mut(page)
        r2, _ = run_checks(t2, src)
        red2 = set(r["id"] for r in r2 if not r["ok"])
        rec("G0-3/%s" % cid, red2 <= {cid}, "破坏 %s ⇒ 判红集合：%s（不许连坐）" % (cid, sorted(red2)))

    # G0-4：护栏**调用点**（从真正的对账路径喂坏页面）
    t2 = neg["A1"](page)
    r2, _ = run_checks(t2, src)
    rec("G0-4", any(r["id"] == "A1" and not r["ok"] for r in r2), "从真正的对账路径喂坏页面 ⇒ A1 必须红")

    # G0-5：「无出处数」检查
    ok7, bad7 = h7_no_unsourced_numbers(page, src)
    rec("G0-5", ok7, "合成页面里追不到出处的数：%s" % (bad7 or "无"))
    t3 = page.replace("**+7.333333**", "**+7.333334**", 1)
    ok7b, bad7b = h7_no_unsourced_numbers(t3, src)
    rec("G0-5b", not ok7b, "改一个数 ⇒ 必须被判「无出处」：%s" % (bad7b or "⛔ 没抓到"))

    # G0-5c：「逐位相等」（H5）
    ok5, miss5 = h5_bit_equal(page, src)
    rec("G0-5c", ok5, "锚点行逐位相等：%s" % (miss5 or "全部对上"))

    # G0-6：逐字引用句（改一个字必须红）
    exp = expected_sentence(src)
    t4 = page.replace(exp, exp.replace("污染只可能抬高", "污染可能抬高", 1), 1)
    r4, _ = run_checks(t4, src)
    rec("G0-6", any(r["id"] == "A6" and not r["ok"] for r in r4), "逐字引用句改一个字 ⇒ A6 必须红")

    # G0-7：行号 ↔ 内容（把 244.89 台账行的行号挪到段外必须红）
    t5 = page.replace("`:42259`", "`:42000`", 1)
    r5, _ = run_checks(t5, src)
    rec("G0-7", any(r["id"] == "A8" and not r["ok"] for r in r5), "行号挪走 ⇒ A8 必须红")

    # G0-8：幂等（同一输入跑两遍 ⇒ 逐字节相同）
    src2 = fixture_source()
    page2 = fixture_page(src2)
    r6, _ = run_checks(page2, src2)
    o2 = "\n".join("%s %s" % ("PASS" if r["ok"] else "FAIL", r["id"]) for r in r6)
    rec("G0-8", len(o2) > 0 and o2 == "\n".join("%s %s" % ("PASS" if r["ok"] else "FAIL", r["id"]) for r in res),
        "两次解析的检查项集合一致：%s" % ("✅" if o2 else "⛔"))

    # G0-9：「过期状态描述」
    t6 = page + "\n（244.89 的入库待收尾）\n"
    r7, _ = run_checks(t6, src)
    rec("G0-9", any(r["id"] == "A9" and not r["ok"] for r in r7), "写回「入库待收尾」⇒ A9 必须红")

    # G0-10：形态级联穷举（对 H1..H7 的布尔组合**穷举** ⇒ ⇒ 形态唯一、不落空、5 形态全覆盖）
    #          ⚖⚖⚖ 这条闸门是被 244.92 的**真缺陷**逼出来的：级联里「判红集合永远是空」
    #          （`not "PASS"` 恒假）⇒ ⇒ **任何页面都被判成 A** ⇒ ⇒ 而**自检层完全没测级联**。
    def expect_form(f1, f2, f3, f4, f5, f6, f7):
        """⚖ **手写**的级联（⛔ **不从实现派生** ⇒ ⇒ 改实现必被抓）"""
        if (not f1) or (not f2):
            return "E"
        if not f6:
            return "D"
        if (not f5) or (not f7):
            return "C"
        if (not f3) or (not f4):
            return "B"
        return "A"

    seen = {}
    bad10 = []
    for mask in range(128):
        flags = [bool(mask & (1 << i)) for i in range(7)]
        got, _failed = verdict_from([(flags[i], "H%d" % (i + 1)) for i in range(7)])
        want = expect_form(*flags)
        if got != want:
            bad10.append("H1..H7=%s ⇒ 得 %s（手写级联说 %s）" % (flags, got, want))
        seen[got] = seen.get(got, 0) + 1
    miss10 = [f for f in ("E", "D", "C", "B", "A") if seen.get(f, 0) == 0]
    rec("G0-10", (not bad10) and (not miss10),
        "形态级联穷举 128 种组合：%s ｜ 5 形态覆盖缺口：%s"
        % (bad10[:3] or "全部与手写级联一致", miss10 or "无"))

    # G0-11：**重复落点**必须红（⇒ 「全页只出现一次」这条真的在守）
    #          ⚖ 重复行要插在 §6.7 块的**外面** ⇒ ⇒ 否则块内计数也能抓到 ⇒ ⇒ 测不到「页级唯一」那条
    dup = page.replace("## 6.7 合成可对账块",
                       "· **保守读法**：决策区 **4/12** 成立，全表 **17/27** 成立\n\n## 6.7 合成可对账块", 1)
    r11, _ = run_checks(dup, src)
    rec("G0-11", any(r["id"] == "A2" and not r["ok"] for r in r11),
        "把 L_counts 行**在块外**复制一份 ⇒ A2 必须红（否则「全页只出现一次」没人守）")

    # G0-12：**逐行 tamper**（7 个锚点行 ⇒ 每行都必须让**它归属的**检查项红，且不许连坐）
    line_tampers = [
        ("· **判决形态**：**B'**", "· **判决形态**：**A'**", "A1"),
        ("· **保守读法**：决策区 **4/12** 成立，全表 **17/27** 成立",
         "· **保守读法**：决策区 **5/12** 成立，全表 **17/27** 成立", "A2"),
        ("· **CI_lo(traj)**：90% = **+15.111111** ｜ 95% = **+13.222222** ｜ 99% = **+7.333333**",
         "· **CI_lo(traj)**：90% = **+15.111112** ｜ 95% = **+13.222222** ｜ 99% = **+7.333333**", "A3"),
        ("· **CI_lo(block)**：90% = **+32.444444** ｜ 95% = **+27.555555** ｜ 99% = **+19.666666**",
         "· **CI_lo(block)**：90% = **+32.444445** ｜ 95% = **+27.555555** ｜ 99% = **+19.666666**", "A3"),
        ("· **c 的下界**：90% ⇒ **-8.777777** ｜ 95% ⇒ **-10.888888** ｜ 99% ⇒ **-13.999999**",
         "· **c 的下界**：90% ⇒ **-8.777778** ｜ 95% ⇒ **-10.888888** ｜ 99% ⇒ **-13.999999**", "A3"),
        ("· **全表破口**：**10 处**", "· **全表破口**：**11 处**", "A4"),
        ("· **决策区破口（8 格）**：" + FIXTURE_DEC_BREAKS,
         "· **决策区破口（8 格）**：" + FIXTURE_DEC_BREAKS.replace("-0.7675", "-0.7674"), "A4"),
    ]
    bad12 = []
    for old, new, owner in line_tampers:
        t = page.replace(old, new, 1)
        if t == page:
            bad12.append("落点没找到：" + old[:24])
            continue
        rr, _ = run_checks(t, src)
        reds = set(r["id"] for r in rr if not r["ok"])
        if reds != {owner}:
            bad12.append("%s ⇒ 判红 %s（应恰为 %s）" % (old[:20], sorted(reds), owner))
    rec("G0-12", not bad12, "7 个锚点行逐行 tamper：%s" % (bad12 or "每行都恰好只红它自己的检查项"))

    # G0-13：**B-14 的行号**必须受「落在 244.89 段内」这条守
    t13 = page.replace("`:42300`", "`:42000`", 1)
    r13, _ = run_checks(t13, src)
    reds13 = set(r["id"] for r in r13 if not r["ok"])
    rec("G0-13", reds13 == {"A5"},
        "把 B-14 的行号挪到 244.89 段外 ⇒ 判红 %s（应恰为 A5）" % sorted(reds13))

    # G0-14：三个过期措辞**逐个**写回 ⇒ A9 必须红
    bad14 = []
    for mark in ("入库收尾未完成", "入库待收尾", "待收尾"):
        t = page + "\n（" + mark + "）\n"
        rr, _ = run_checks(t, src)
        if not any(r["id"] == "A9" and not r["ok"] for r in rr):
            bad14.append(mark)
    rec("G0-14", not bad14, "三个过期措辞逐个写回 ⇒ A9 必须红：%s" % (bad14 or "全部红"))

    # G0-15：**文件名里的数字不算数**（正控 ⇒ ⇒ 「独立成词」这条规则真的在生效）
    t15 = page + "\n· 复算入口：`python3 .cache/r244/_cross_check_24492.py`\n"
    ok15, bad15 = h7_no_unsourced_numbers(t15, src)
    rec("G0-15", ok15, "文件名里的数字（r244 / 24492）**不算数**：%s" % (bad15 or "✅ 未被判无出处"))

    # G0-16：账本**自洽核对**必须能红（否则「改坏账本解析」这类变异没人抓）
    #          ⚖ 落点选 `n_all_items`（**只有一条子句**查它 ⇒ ⇒ 变异台能精确地打掉那一条）
    src16 = fixture_source()
    src16["n_all_items"] = 99
    rec("G0-16", not self_consistency(src16), "改坏账本的破口清单条数 ⇒ H2 自洽核对必须红")

    # G0-17：§6.7 块**缺失** ⇒ H7 必须红（⛔ 不许「真空绿」）
    t17 = page.replace("## 6.7 合成可对账块\n", "", 1)
    ok17, bad17 = h7_no_unsourced_numbers(t17, src)
    rec("G0-17", (not ok17) and ("§6.7" in (bad17[0] if bad17 else "")),
        "删掉 §6.7 标题 ⇒ H7 必须红（不许真空绿）：%s" % (bad17 or "⛔ 没抓到"))

    # G0-18：**第一条**引用句必须逐字等于期望句（⛔ 不许「后面藏一句对的」）
    t18 = "> 「『污染解释不了观测差』这句是**假的**」。\n" + page
    r18, _ = run_checks(t18, src)
    rec("G0-18", any(r["id"] == "A6" and not r["ok"] for r in r18),
        "在页面前面插一句错的引用句 ⇒ A6 必须红")

    # G0-19：**H5 必须能红**（⛔ 「逐位相等」这条不许是恒绿的）
    t19 = page + "\n· **保守读法**：决策区 **4/12** 成立，全表 **17/27** 成立\n"
    ok19, miss19 = h5_bit_equal(t19, src)
    rec("G0-19", not ok19, "复制一行 ⇒ H5 必须红（不许恒绿）：%s" % (miss19 or "⛔ 没抓到"))

    # ⚖⚖⚖ **H6 的运行期自证**：把页面改坏一处 ⇒ ⇒ 同一套检查必须红
    ok6, why6 = h6_selfproof(page, src)
    rec("H6-自证", ok6, why6)

    n_fail = sum(1 for l in out if l.startswith("[FAIL]"))
    for l in out:
        print(l)
    print("自检：%d 道 ｜ FAIL %d 道" % (len(out), n_fail))
    print("")
    print("===== SELFTEST_KEYS =====")
    print("SELFTEST_RED=%d" % n_fail)
    for r in res:
        print("FIX_%s=%s" % (r["id"], "PASS" if r["ok"] else "FAIL"))
    print("SELFTEST_RC=%d" % (0 if g_ok else 1))
    print("===== END_SELFTEST_KEYS =====")
    return 0 if g_ok else 1


# =============================================================================
# 真数据
# =============================================================================
def data(page_path, ledger_path, prereg_path):
    if not os.path.exists(page_path):
        print("[FAIL] H1 页面文件不存在：%s" % page_path)
        print("VERDICT=E")
        print("DATA_RC=2")
        return 2
    page = read_text(page_path)
    if not page.strip():
        print("[FAIL] H1 页面文件为空：%s" % page_path)
        print("VERDICT=E")
        print("DATA_RC=2")
        return 2
    try:
        src = parse_source(ledger_path, prereg_path)
    except SystemExit as e:
        print("[FAIL] H2 权威来源不可读或不自洽：%s" % e)
        print("VERDICT=E")
        print("DATA_RC=2")
        return 2

    res, p = run_checks(page, src)
    ok5, miss5 = h5_bit_equal(page, src)
    ok7, bad7 = h7_no_unsourced_numbers(page, src)
    ok6, why6 = h6_selfproof(page, src)

    # ---- H2：关键数**互相自洽**（账本自己的表 vs 账本自己的清单）----
    self_ok = self_consistency(src)

    crits = []
    crits.append((True, "H1"))
    crits.append((self_ok, "H2"))
    h3 = all(r["ok"] for r in res if r["id"] in ("A1", "A2", "A3", "A4"))
    h4 = all(r["ok"] for r in res if r["id"] in ("A5", "A6", "A7", "A8", "A9"))
    crits.append((h3, "H3"))
    crits.append((h4, "H4"))
    crits.append((ok5, "H5"))
    crits.append((ok6, "H6"))
    crits.append((ok7, "H7"))

    print("──── 检查项 ────")
    for r in res:
        print("[%s] %s %s" % ("PASS" if r["ok"] else "FAIL", r["id"], r["detail"]))
    if not ok5:
        print("[FAIL] H5 锚点行未逐位相等：%s" % (miss5 or "无"))
    if not ok7:
        print("[FAIL] H7 无出处数：%s" % (bad7[:12] or "无"))
    if not ok6:
        print("[FAIL] H6 自证失败：%s" % why6)
    print("")
    print("──── 判据 ────")
    for st, cid in crits:
        print("[%s] %s" % ("PASS" if st else "FAIL", cid))
    form, failed = verdict_from(crits)
    print("")
    print("VERDICT=%s" % form)
    print("理由：%s" % ("页面与账本**逐条一致**" if form == "A"
                        else "页面与账本**不一致**（判红：%s）" % sorted(failed)))
    print("")
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % form)
    print("SRC_VERDICT=%s" % src["verdict"])
    print("N_DEC=%d" % src["n_dec"])
    print("N_DEC_HOLD=%d" % src["n_dec_hold"])
    print("N_CELLS=%d" % src["n_cells"])
    print("N_ALL_HOLD=%d" % src["n_all_hold"])
    print("N_ALL_BREAKS=%d" % src["n_all_breaks"])
    print("N_DEC_BREAKS=%d" % src["n_dec_breaks"])
    print("SEC_LO=%d" % src["sec_lo"])
    print("SEC_HI=%d" % src["sec_hi"])
    print("CHECKS_RED=%d" % len([r for r in res if not r["ok"]]))
    for r in res:
        print("CHECK_%s=%s" % (r["id"], "PASS" if r["ok"] else "FAIL"))
    print("===== END_AUDIT_KEYS =====")
    print("DATA_RC=%d" % (0 if form == "A" else 1))
    return 0 if form == "A" else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--page", default=DEFAULT_PAGE)
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--prereg", default=DEFAULT_PREREG)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.data:
        return data(a.page, a.ledger, a.prereg)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
