#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_dose_curve_audit.py —— 244.97：页面 §6.2.2「剂量—响应曲线（**未量到**）」↔ 账本 **可溯源**对账（零 GPU）。

⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_CURVE_PREREG.md`（244.97 签，**先于**实现）。
   §0 范围与不做项、§1 侦察结论与缺陷登记、§2 判据 E1–E7、§3 实现纪律、§4 变异台、§5 互证、§6 边界。
   ⚖⚖⚖ **§8 追加更正**（实现期发现，**只追加、不改写**原 §1–§7）：
   E6 的「否定」判定补上**「别的小节」作用域**（见下面 `in_other_section_paren`）
   ⇒ ⇒ 原 §2 的 E6 文本漏了它 ⇒ ⇒ 会把页面里**正确的**交叉引用「（6.2.1 已量到）」判红
   ⇒ ⇒ 与 §2 末尾「改前预期判红 ['E3','E4']」自相矛盾 ⇒ ⇒ §8 已登记该差异与更正依据。

⚖⚖⚖ **本文件做什么**
   ① 抓页面 §6.2.2 的标题 ＋ **恰好 3 个 bullet**；
   ② 每个 bullet 取它**自己引用的** `:NNNN`（⛔ **不用 min..max 区间窗口**）；
   ③ 每个 bullet 的**措辞类断言**必须 ① 出现在页面上 ② **逐位**出现在**它引用的某一行**里；
   ④ 每个 bullet 的**数值类断言**（**必须以账本逐字形式书写**）同上；
   ⑤ **留白守卫**：§6.2.2 必须保留「剂量趋势未量到」＋ 否定形式，
      且**不得**出现**未被否定**的「无效应 / 无差异 / 已量到」类措辞
      （§8 追加更正：豁免多一条「**别的小节**作用域」，见 `in_other_section_paren`）。
   ⑥ **E7 = 每 bullet 至少 1 项命中**（⚖ 预登记 §2 的原文口径；登记**按位置**）。

⚖⚖⚖ **本文件不做什么**
   ⛔ **不读收据**（收据不入库）⇒ ⇒ 别人 clone 下来就能跑。
   ⛔ **零 GPU**、⛔ 没跑批、⛔ 不碰 bpath、⛔ **不改任何被测文件**。
   ⛔ **不判弱 token**（纯整数在窗口里几乎必然偶然出现 ⇒ ⇒ 证据弱）⇒ ⇒ 留白。
   ⛔ **不碰剂量—响应曲线本身**（本批 `n_bands = 1` ⇒ ⇒ 它**仍然未量到**）。
   ⛔ **不许**用「|page − ledger| ≤ tol 且 tol 现算」的容差 ⇒ ⇒ 那是「为让数对上而定的容差」。
"""

import argparse
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEFAULT_PAGE = os.path.join("docs", "BPATH_VERDICT.md")
DEFAULT_LEDGER = os.path.join(".cache", "xcheck", "R6_RERUN_PREREG.md")

# ⚖ 预登记 §2 写死的口径常量（⛔ 不许在实现里另定）
N_BULLETS = 3
SEC_TITLE = "6.2.2"
TITLE_MUST_CONTAIN = "未量到"

# ⚖ 预登记 §2 E3/E4 的**断言登记**（每个 bullet 的断言 token ＋ 类别）
#   ⚠ 这些 token 是**判据定义**（「哪些字算断言」），⛔ **不是**「期望值」——
#     期望值（命中数 / 缺口数 / 形态）全部**现算**（见 §3.3）。
#   ⚠ B3 的数值类 token 取**账本 `:41327` 的逐字形式**（⛔ 无空格、⛔ 各自带反引号）
#     ⇒ ⇒ 页面若写压缩式 ⇒ ⇒ **E4 判红**（这正是预登记 §1.3 D2 要修的）。
BULLET_ASSERTIONS = {
    1: [("`n_bands = 1`", "措辞"),
        ("单一剂量档", "措辞"),
        ("剂量趋势未量到", "措辞"),
        ("不是「无剂量效应」", "措辞")],
    2: [("真阶梯", "措辞"),
        ("每条轨迹扫 K 个 `n_sites`", "措辞"),
        ("不能靠事后分位分档", "措辞"),
        ("切穿复制组", "措辞"),
        ("要跑批 ⇒ 要点头", "措辞")],
    3: [("3 个 `pos_frac`", "措辞"),
        ("`pos_frac=0.25`", "数值"),
        ("`pos_frac=0.50`", "数值"),
        ("`pos_frac=0.75`", "数值"),
        ("不是「单剂量」口径", "措辞")],
}

# ⚖ 预登记 §2 E5 的**肯定形式**：必须逐位出现在 §6.2.2 里
E5_MUST = "剂量趋势未量到"
E5_NEG_FORMS = ("不是「无剂量效应」", "不是「无趋势」")

# ⚖ 预登记 §2 E6 的**可疑措辞**：每次出现都**必须被紧邻的否定**裹住
E6_FORBIDDEN = ("无剂量效应", "无趋势", "无差异", "不存在剂量效应", "剂量效应为 0",
                "斜率为 0", "斜率 = 0", "没有剂量效应", "剂量效应不存在",
                "已量到", "有剂量效应", "存在剂量效应")
# ⚖ 「被否定」的判定：剥掉 markdown 粗体后，**紧邻**前面是「不是「」
NEG_PREFIX = "不是「"

# ⚖⚖⚖ §8 追加更正：**「别的小节」作用域**的豁免
#   页面 §6.2.2 的 B3 逐字含「两臂**之间**剂量相同（6.2.1 已量到）」
#   ⇒ ⇒ 那说的是 **§6.2.1**（两臂同剂量，244.94/244.95 已闭环）**已量到**，
#        ⛔ **不是**「§6.2.2 的剂量—响应曲线已量到」
#   ⇒ ⇒ 故：一次「可疑措辞」的出现若**位于一对圆括号内**、且**括号内容含小节号**
#        （形如 `6.2.1`）⇒ ⇒ 豁免（那说的是别的小节）。
#   ⛔ 豁免**只认「括号包住本次出现」**：括号在**后面**（如「已量到（见 6.2.1）」）
#      ⇒ ⇒ **不豁免**（MU-C13 专门打这一条）。
SECNUM_RE = re.compile(r"\d+\.\d+")

CITE_RE = re.compile(r":(\d+)")


# ---------------------------------------------------------------- 基础工具

def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_md(s):
    """⚖ 剥掉 markdown 粗体/斜体标记（**只**用于「否定形式」的判定）。"""
    return s.replace("**", "").replace("*", "")


def section_622(page_text):
    """⚖ 取 §6.2.2 整段 ⇒ ⇒ (标题, 3 个 bullet 的文本列表)。"""
    m = re.search(r"^###\s+" + re.escape(SEC_TITLE) + r"\s+.*$", page_text, re.M)
    if not m:
        raise ValueError("页面里找不到 §%s" % SEC_TITLE)
    start = m.start()
    nxt = re.search(r"^###\s+", page_text[m.end():], re.M)
    end = m.end() + (nxt.start() if nxt else len(page_text) - m.end())
    sec = page_text[start:end]
    title = page_text[m.start():page_text.find("\n", m.start())]
    bullets = []
    for line in sec.split("\n"):
        ls = line.strip()
        if ls.startswith("- ") and ls[2:3] not in ("", " "):
            bullets.append(ls)
    return title, sec, bullets


def cited_lines(bullet):
    return [int(x) for x in CITE_RE.findall(bullet)]


def in_other_section_paren(sec, start, end):
    """⚖ §8 更正：本次出现是否**位于一对圆括号内**且**括号内容含小节号**。

    ⚖ 判定步骤（机械、可复核）：
      ① 取本次出现**之前**最后一个「（」；
      ② 若它与本次出现之间**已经出现过「）」** ⇒ ⇒ 这个「（」早已闭合 ⇒ ⇒ **不在里面**；
      ③ 取本次出现**之后**第一个「）」；找不到 ⇒ ⇒ **不在里面**；
      ④ 括号内容里**有**小节号（`\\d+\\.\\d+`）⇒ ⇒ **在**「别的小节」的作用域里 ⇒ ⇒ 豁免。
    """
    i_open = sec.rfind("（", 0, start)
    if i_open < 0:
        return False
    if "）" in sec[i_open:start]:
        return False                       # ② 这个「（」已经闭合
    i_close = sec.find("）", end)
    if i_close < 0:
        return False                       # ③ 没有闭合的「）」
    inner = sec[i_open + 1:i_close]
    return bool(SECNUM_RE.search(inner))  # ④ 括号内容含小节号


def negation_ok(sec, phrase):
    """⚖ E6：phrase 在 sec 里的**每一次**出现，都必须**紧邻**被否定形式裹住。

    ⚖ §8 更正后：豁免条件有**两个** —— ① **紧邻否定**（`不是「`）② **别的小节作用域**。
    ⚖ 返回 (是否全部被否定, 出现次数, 未被否定的明细, 豁免次数)
    """
    bad = []
    n_all = 0
    n_exempt = 0
    for m in re.finditer(re.escape(phrase), sec):
        n_all += 1
        pre = strip_md(sec[max(0, m.start() - 12):m.start()])
        if pre.endswith(NEG_PREFIX):
            n_exempt += 1
            continue
        if in_other_section_paren(sec, m.start(), m.end()):
            n_exempt += 1
            continue
        bad.append({"pre": pre[-12:], "post": sec[m.end():m.end() + 3]})
    return (not bad), n_all, bad, n_exempt


# ---------------------------------------------------------------- 判据

def audit(page_text, ledger_text):
    """⚖ 跑 E1–E7 ⇒ ⇒ (结果列表, 明细)。"""
    res = []
    lines = ledger_text.split("\n")
    n_lines = ledger_text.count("\n")          # ⚖ ⚠ 用 count("\n")，⛔ 不用 len(split)
    ledger_at = {i + 1: l for i, l in enumerate(lines)}

    try:
        title, sec, bullets = section_622(page_text)
    except ValueError as e:
        for cid, name in (("E1", "结构"), ("E2", "出处存在"), ("E3", "措辞类断言逐位可溯源"),
                          ("E4", "数值类断言逐位可溯源"), ("E5", "留白守卫（正向）"),
                          ("E6", "留白守卫（反向）"), ("E7", "每行至少 1 项命中")):
            res.append((cid, name, False, "页面里找不到 §%s" % SEC_TITLE))
        return res, {}

    # ---- E1 结构 ----
    e1_ok = (len(bullets) == N_BULLETS and TITLE_MUST_CONTAIN in title)
    res.append(("E1", "结构", e1_ok,
                "标题含「%s」=%s ｜ bullet 数 %d（期望 %d）｜ 标题：%s"
                % (TITLE_MUST_CONTAIN, TITLE_MUST_CONTAIN in title,
                   len(bullets), N_BULLETS, title[:40])))

    # ---- E2 出处存在 ----
    all_cites = []
    for i, b in enumerate(bullets, 1):
        all_cites += cited_lines(b)
    bad_cites = [c for c in all_cites if not (1 <= c <= n_lines)]
    # ⚖⚖⚖ **信息项**（⛔ 不是闸门）：被引到**空行**上的出处
    #   ⇒ 预登记 §4 的 MU-C6 把 `:41657`（一个**空行**）称作「不存在的出处」，
    #   ⇒ 但 E2 的**定义**是「行号 ∈ [1, 账本行数]」⇒ `:41657` **在范围内** ⇒ E2 不红
    #   ⇒ ⇒ 这里**如实报出**，⛔ **不改判据**去迁就预登记的期望（见 §8 追加更正 §8.3）。
    empty_cites = [c for c in all_cites
                    if 1 <= c <= n_lines and ledger_at.get(c, "").strip() == ""]
    res.append(("E2", "出处存在", not bad_cites,
                "被引行号 %s ｜ 账本 %d 行 ｜ 越界 %s ｜（信息）空行引用 %s"
                % (sorted(set(all_cites)), n_lines, bad_cites or "无",
                   empty_cites or "无")))

    # ---- E3 / E4：断言逐位可溯源（**只查它自己引用的行**）----
    matrix = []
    row_verdicts = []
    n_assert = n_hit = n_miss = 0
    n_inpage_miss = 0
    e3_bad = []
    e4_bad = []
    for i, b in enumerate(bullets, 1):
        cites = cited_lines(b)
        reg = BULLET_ASSERTIONS.get(i, [])
        hits = []
        misses = []
        # ⚖⚖⚖ 所有 token 匹配都在**剥掉 markdown 粗体标记**之后做
        #    （预登记 §1.4-1：页面写的是「⛔ **不是**「…」」⇒ ⇒ 粗体标记夹在中间
        #     ⇒ ⇒ 逐字串**不连续** ⇒ ⇒ 不剥就找不到 ⇒ ⇒ 那不是「没有出处」，是「没剥」）
        b_s = strip_md(b)
        for tok, kind in reg:
            n_assert += 1
            in_page = tok in b_s
            in_led = any((1 <= c <= n_lines)
                         and (tok in strip_md(ledger_at.get(c, "")))
                         for c in cites)
            if in_page and in_led:
                hits.append(tok)
                n_hit += 1
            else:
                misses.append("%s[%s]（页内=%s 行内=%s）" % (tok, kind, in_page, in_led))
                n_miss += 1
                if not in_page:
                    n_inpage_miss += 1
                if kind == "措辞":
                    e3_bad.append("B%d：%s" % (i, misses[-1]))
                else:
                    e4_bad.append("B%d：%s" % (i, misses[-1]))
        matrix.append((i, len(cites), len(reg), len(hits), len(misses)))
        row_verdicts.append((i, "OK" if not misses else "MISS"))
    res.append(("E3", "措辞类断言逐位可溯源", not e3_bad,
                "%d 条措辞类断言，缺口 %d" % (
                    sum(1 for i in BULLET_ASSERTIONS for _t, k in BULLET_ASSERTIONS[i] if k == "措辞"),
                    len(e3_bad)) + ("｜" + "；".join(e3_bad) if e3_bad else "")))
    res.append(("E4", "数值类断言逐位可溯源", not e4_bad,
                "%d 条数值类断言，缺口 %d" % (
                    sum(1 for i in BULLET_ASSERTIONS for _t, k in BULLET_ASSERTIONS[i] if k == "数值"),
                    len(e4_bad)) + ("｜" + "；".join(e4_bad) if e4_bad else "")))

    # ---- E5 留白守卫（正向）----
    sec_s = strip_md(sec)
    has_must = E5_MUST in sec_s
    has_neg = any(f in sec_s for f in E5_NEG_FORMS)
    res.append(("E5", "留白守卫（正向）", has_must and has_neg,
                "含「%s」=%s ｜ 含否定形式（%s）=%s"
                % (E5_MUST, has_must, " / ".join(E5_NEG_FORMS), has_neg)))

    # ---- E6 留白守卫（反向）----
    bad_all = []
    n_occ = 0
    n_exempt = 0
    for ph in E6_FORBIDDEN:
        ok, n, bad, nx = negation_ok(sec, ph)
        n_occ += n
        n_exempt += nx
        for d in bad:
            bad_all.append("%s（前=%r）" % (ph, d["pre"]))
    res.append(("E6", "留白守卫（反向）", not bad_all,
                "可疑措辞共出现 %d 处（豁免 %d 处：紧邻否定 或 别的小节作用域），未被否定的 %d 处%s"
                % (n_occ, n_exempt, len(bad_all), ("｜" + "；".join(bad_all)) if bad_all else "")))

    # ---- E7：每个 bullet **至少 1 项命中**（⚖ 预登记 §2 的原文口径）----
    #   ⚖ 登记是**按位置**的（B1/B2/B3 各一组）⇒ ⇒ 删掉中间那个 bullet
    #   ⇒ ⇒ 第 2 个 bullet 变成「原来的 B3」⇒ ⇒ 它与登记的 B2 一组**对不上**
    #   ⇒ ⇒ 0 命中 ⇒ ⇒ E7 红（MU-C10 就是打这一条）。
    row_hits = dict((i, 0) for i in range(1, len(bullets) + 1))
    for (bi, _nc, _na, nh, _nm) in matrix:
        row_hits[bi] = nh
    e7_bad = [("B%d（命中 %d 项）" % (i, row_hits.get(i, 0)))
              for i in range(1, len(bullets) + 1)
              if row_hits.get(i, 0) < 1]
    res.append(("E7", "每行至少 1 项命中", not e7_bad,
                "每 bullet 命中数 %s ｜ 0 命中的 %s"
                % (["B%d=%d" % (i, row_hits.get(i, 0))
                    for i in range(1, len(bullets) + 1)], e7_bad or "无")))

    aux = {"n_bullets": len(bullets), "n_assert": n_assert, "n_hit": n_hit,
           "n_miss": n_miss, "n_inpage_miss": n_inpage_miss,
           "n_occ": n_occ, "n_exempt": n_exempt,
           "matrix": matrix, "row_verdicts": row_verdicts,
           "sec": sec, "title": title}
    return res, aux


def verdict_of(res):
    red = [cid for cid, _n, ok, _d in res if not ok]
    return ("D" if red else "A"), red


# ---------------------------------------------------------------- 数据模式

def run_data(page_path, ledger_path):
    page_text = read_text(page_path)
    ledger_text = read_text(ledger_path)
    res, aux = audit(page_text, ledger_text)
    v, red = verdict_of(res)

    print("=" * 78)
    print("页面：%s" % page_path)
    print("账本：%s（%d 行）" % (ledger_path, ledger_text.count("\n")))
    print("=" * 78)
    for cid, name, ok, detail in res:
        print("[%s] %s：%s：%s" % ("PASS" if ok else "FAIL", cid, name, detail))
    print("")
    print("⚖ **明细计数（⛔ 不是判据）**：")
    print("  · bullet %d ｜ 断言 %d ｜ 命中 %d ｜ 缺口 %d ｜ 页内就找不到 %d"
          % (aux["n_bullets"], aux["n_assert"], aux["n_hit"], aux["n_miss"],
             aux["n_inpage_miss"]))
    print("  · 可疑措辞出现 %d 处（豁免 %d 处）" % (aux["n_occ"], aux["n_exempt"]))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for _c, _n, ok, _d in res if ok), len(res)))
    print("VERDICT=%s" % v)
    print("REASON=%s" % (
        "页面 §6.2.2「剂量—响应曲线（未量到）」的每个断言都能**逐位**溯源到它引用的账本行，"
        "且留白措辞没有被改成「无差异」⇒ 形态 A"
        if v == "A" else
        "有判红（%s）⇒ 形态 D（⛔ 那次不算判决）" % "、".join(red)))
    print("")
    print("===== NUM_MATRIX =====")
    for bi, ncite, nass, nhit, nmiss in aux["matrix"]:
        print("ROW=B%d|cites=%d|assertions=%d|hit=%d|miss=%d" % (bi, ncite, nass, nhit, nmiss))
    print("===== END_NUM_MATRIX =====")
    print("")
    print("===== ROW_VERDICTS =====")
    for bi, st in aux["row_verdicts"]:
        print("ROWV=B%d|%s" % (bi, st))
    print("===== END_ROW_VERDICTS =====")
    print("")
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % v)
    print("N_CHECKS=%d" % len(res))
    print("CHECKS_RED=%d" % len(red))
    for cid, _n, ok, _d in res:
        print("CHECK_%s=%s" % (cid, "PASS" if ok else "FAIL"))
    print("N_BULLETS=%d" % aux["n_bullets"])
    print("N_ASSERT=%d" % aux["n_assert"])
    print("N_HIT=%d" % aux["n_hit"])
    print("N_MISS=%d" % aux["n_miss"])
    print("N_INPAGE_MISS=%d" % aux["n_inpage_miss"])
    print("N_SUSPECT=%d" % aux["n_occ"])
    print("N_EXEMPT=%d" % aux["n_exempt"])
    print("===== END_AUDIT_KEYS =====")
    return 0 if v == "A" else 1


# ---------------------------------------------------------------- 自检（合成夹具）

def _fixture(led_lines, b1=None, b2=None, b3=None, title=None, extra=""):
    """⚖ 合成一个 §6.2.2 夹具页（⛔ 合成值**不算**「手写期望」）。"""
    t = title or ("### 6.2.2 剂量—响应曲线（**未量到**）")
    b1 = b1 if b1 is not None else (
        "- 本批 `n_bands = 1`（**单一剂量档**）⇒ ⇒ **剂量趋势未量到**"
        "（⛔ **不是**「无剂量效应」）⇒ `:1`、`:2`")
    b2 = b2 if b2 is not None else (
        "- 分层剂量要**真阶梯**（每条轨迹扫 K 个 `n_sites`）⇒ ⇒ ⛔ **不能靠事后分位分档**"
        "（244.72 的 D5 审计已证 4 档分位会**切穿复制组**）"
        "⇒ ⇒ **要跑批 ⇒ 要点头** ⇒ `:3`")
    b3 = b3 if b3 is not None else (
        "- ⚠⚖⚖ **口径要点**：但**判决数本身**是 **3 个 `pos_frac` 档的合池**"
        "（`pos_frac=0.25` / `pos_frac=0.50` / `pos_frac=0.75`）"
        "⇒ ⇒ **不是**「单剂量」口径 ⇒ `:4`")
    return "\n".join([t, "", b1, b2, b3, extra, "### 6.3 下一节", ""])


def _fixture_ledger():
    """⚖ 合成账本（⛔ 零真实数据）。"""
    return "\n".join([
        "· L1 本批 `n_bands = 1`（**单一剂量档**）⇒ ⇒ **剂量趋势未量到**"
        " ⇒ ⇒ ⛔ 不是「无剂量效应」。",
        "· L2 本批是**单一剂量档**的两个工作点 ⇒ ⇒ **未量到**",
        "· L3 **分层剂量的真阶梯**：**不能靠事后分位分档** ⇒ ⇒ 每条轨迹扫 K 个 `n_sites`"
        " ⇒ ⇒ **要跑批 ⇒ 要点头**（切穿复制组）",
        "· L4 **合池**口径（3 个 `pos_frac` 逐轨迹严格多数）⇒ ⇒ ⛔ 不是「单剂量」口径；"
        "三份产物：`pos_frac=0.25` 30 格 ｜ `pos_frac=0.50` 30 格 ｜ `pos_frac=0.75` 29 格",
        "· L5 ⛔ 不是「无剂量效应」。",
    ]) + "\n"


def selftest():
    fails = []

    def case(name, cond, detail=""):
        if not cond:
            fails.append("%s｜%s" % (name, detail))

    led = _fixture_ledger()
    page = _fixture(None)

    # ---- T1 全绿夹具 ⇒ E1–E7 全绿、形态 A ----
    res, aux = audit(page, led)
    v, red = verdict_of(res)
    case("T1 全绿夹具", v == "A" and not red, "verdict=%s red=%s" % (v, red))
    case("T1b 明细", aux["n_bullets"] == 3 and aux["n_miss"] == 0,
         "bullets=%d miss=%d" % (aux["n_bullets"], aux["n_miss"]))

    # ---- E1：少一个 bullet ⇒ 红 ----
    p2 = _fixture(None, b3="")
    _v2, red2 = verdict_of(audit(p2, led)[0])
    case("T2 E1 bullet 数不对", "E1" in red2, "red=%s" % red2)

    # ---- E1b：标题去掉「未量到」⇒ 红 ----
    p2b = _fixture(None, title="### 6.2.2 剂量—响应曲线")
    _v2b, red2b = verdict_of(audit(p2b, led)[0])
    case("T2b E1 标题缺「未量到」", "E1" in red2b, "red=%s" % red2b)

    # ---- E2：引用越界 ⇒ 红 ----
    p3 = _fixture(None, b1="- 本批 `n_bands = 1`（**单一剂量档**）⇒ ⇒ **剂量趋势未量到**"
                           "（⛔ **不是**「无剂量效应」）⇒ `:99999`")
    _v3, red3 = verdict_of(audit(p3, led)[0])
    case("T3 E2 越界", "E2" in red3, "red=%s" % red3)

    # ---- E3：把「不是「无剂量效应」」删掉 ⇒ 红（该措辞在 :5 那行，不在被引的行里）----
    p4 = _fixture(None, b1="- 本批 `n_bands = 1`（**单一剂量档**）⇒ ⇒ **剂量趋势未量到**"
                           " ⇒ `:1`、`:2`")
    _v4, red4 = verdict_of(audit(p4, led)[0])
    case("T4 E3 措辞失去出处", "E3" in red4, "red=%s" % red4)

    # ---- E4：数值 token 写回压缩式 ⇒ 红 ----
    p5 = _fixture(None, b3="- ⚠⚖⚖ **口径要点**：但**判决数本身**是 **3 个 `pos_frac` 档的合池**"
                           "（`pos_frac = 0.25 / 0.50 / 0.75`）"
                           "⇒ ⇒ **不是**「单剂量」口径 ⇒ `:4`")
    _v5, red5 = verdict_of(audit(p5, led)[0])
    case("T5 E4 数值记号不合规", "E4" in red5, "red=%s" % red5)

    # ---- E5：删掉否定形式 ⇒ 红 ----
    p6 = _fixture(None, b1="- 本批 `n_bands = 1`（**单一剂量档**）⇒ ⇒ **剂量趋势未量到**"
                           " ⇒ `:1`、`:2`")
    _v6, red6 = verdict_of(audit(p6, led)[0])
    case("T6 E5 否定形式缺失", "E5" in red6, "red=%s" % red6)

    # ---- E6：插入**未否定**的「已量到」⇒ 红 ----
    p7 = _fixture(None, extra="  ⇒ ⇒ 剂量—响应曲线**已量到**，斜率为 0")
    _v7, red7 = verdict_of(audit(p7, led)[0])
    case("T7 E6 未否定的措辞", "E6" in red7, "red=%s" % red7)

    # ---- E6b：把「不是「无剂量效应」」改成「无剂量效应」⇒ 红 ----
    p8 = _fixture(None, b1="- 本批 `n_bands = 1`（**单一剂量档**）⇒ ⇒ **剂量趋势未量到**"
                           " ⇒ ⇒ 无剂量效应 ⇒ `:1`、`:2`")
    _v8, red8 = verdict_of(audit(p8, led)[0])
    case("T8 E6 否定被去掉", "E6" in red8, "red=%s" % red8)

    # ---- E6c：**被否定**的写法**不该**判红（负控）----
    p9 = _fixture(None, extra="  ⇒ ⇒ ⛔ 不是「无差异」")
    _v9, red9 = verdict_of(audit(p9, led)[0])
    case("T9 E6c 被否定的写法不红", "E6" not in red9, "red=%s" % red9)

    # ---- E7：登记里删掉一个 bullet 的断言 ⇒ 红 ----
    # ⚖ 脚本运行时的模块名是 `__main__` ⇒ ⇒ 用 sys.modules 取**当前**模块（⛔ 不许 import 自己）
    self_mod = sys.modules[__name__]
    old = dict(self_mod.BULLET_ASSERTIONS)
    try:
        self_mod.BULLET_ASSERTIONS[2] = []
        _v10, red10 = verdict_of(audit(page, led)[0])
        case("T10 E7 有 bullet 掉出监管", "E7" in red10, "red=%s" % red10)
    finally:
        self_mod.BULLET_ASSERTIONS.clear()
        self_mod.BULLET_ASSERTIONS.update(old)

    # ---- E7b：登记恢复 ⇒ 不红（负控）----
    _v11, red11 = verdict_of(audit(page, led)[0])
    case("T11 E7b 登记恢复后不红", "E7" not in red11, "red=%s" % red11)

    # ---- E6d（§8 更正的负控）：「**别的小节**已量到」的交叉引用 ⇒ **不该**判红 ----
    #   ⚖ 页面 §6.2.2 的 B3 逐字含「（6.2.1 已量到）」⇒ ⇒ 说的是 §6.2.1，不是本节
    p12 = _fixture(None, extra="  ⇒ ⇒ 两臂**之间**剂量相同（6.2.1 已量到）")
    _v12, red12 = verdict_of(audit(p12, led)[0])
    case("T12 E6d 别的小节的交叉引用不红", "E6" not in red12, "red=%s" % red12)

    # ---- E6e（§8 更正的**加严**）：括号在**后面** ⇒ ⇒ 豁免**不成立** ⇒ 仍须红 ----
    #   ⚖「剂量—响应曲线**已量到**（见 6.2.1）」⇒ ⇒ 「已量到」不在任何含小节号的括号里
    p13 = _fixture(None, extra="  ⇒ ⇒ 剂量—响应曲线**已量到**（见 6.2.1）")
    _v13, red13 = verdict_of(audit(p13, led)[0])
    case("T13 E6e 括号在后面仍判红", "E6" in red13, "red=%s" % red13)

    print("自检 %d/%d 通过" % (15 - len(fails), 15))
    for f in fails:
        print("[FAIL] %s" % f)
    print("SELFTEST_RED=%d" % len(fails))
    print("SELFTEST_RC=%d" % (0 if not fails else 1))
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(
        description="244.97：页面 §6.2.2 剂量—响应曲线留白块 ↔ 账本 可溯源对账（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--page", default=None)
    ap.add_argument("--ledger", default=None)
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.data:
        page_path = args.page or os.path.join(REPO, DEFAULT_PAGE)
        ledger_path = args.ledger or os.path.join(REPO, DEFAULT_LEDGER)
        try:
            return run_data(page_path, ledger_path)
        except Exception as e:                       # noqa: BLE001
            print("[错误] %s" % e)
            return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
