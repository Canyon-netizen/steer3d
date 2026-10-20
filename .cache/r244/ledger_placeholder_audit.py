#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_placeholder_audit.py —— 账本里有没有**没被替换的占位符**（零 GPU，修订 244.63）

🔴🔴 **本工具问什么**

  244.63 要往账本追加一段，追加脚本的**终检**报「回填后仍有未替换的占位符：`@WPALL@`」。
  ⇒ 顺着查下去发现：**占位符不是 244.63 引进的，是 244.62 引进的** ——
  244.62 那段在账本里**留着 14 处裸占位符**（8 个不同的标记），本该是数字的地方**是空的**。

  根因（244.62 的追加脚本）：
    ① 替换表里有**链式占位符**：`"@NS5@": "@NS@"`（变体 → canonical 的**裸 token**）；
    ② 替换是**单趟**、按 dict 插入序 ⇒ canonical 占位符**先**被换成真值，
       变体占位符**后**被换成 canonical 的**裸 token** ⇒ 那几处最终写进账本的就是 `@NS@` 原文；
    ③ 244.62 的脚本**替换后没有残留检查** ⇒ 没人发现。

⚖⚖⚖⚖ **本工具的立场**

  · 账本是**唯一权威历史** ⇒ 它里面**必须**没有「本该是数字的空位」。
  · ⛔ **按纪律不回头改账本历史** ⇒ 244.62 那 14 处**保留在原处**，改成
    **登记在案 + 应填值由程序化重算钉住 + 本工具长期盯着不许再长新的**。
  · ⚖ **登记表必须独立写死**（`HOLE_LINES` / `HOLE_VALUES` 都是**字面量**）
    ⇒ ⛔ 不许「现扫现登记」：那会让 C1/C2/C3 变成恒绿。
  · ⚖ **应填值的尺子住在产品之外**：用 `dose_fragility_audit`（244.62 用的同一套机械）
    **现算**一遍 ⇒ 登记值与现算值不符 ⇒ 红。

⚖ **扫描规则（两处例外，理由写在这里）**

  · 行内代码段（`` `...` ``）里的 `@X@` **不算**残留 ⇒ 账本可以**引用**标记名。
  · ⛔ **但代码段里的标记也必须全部已登记**（C5）⇒ 「藏在代码段里的新洞」照样红。
  · ⛔ **`****`（双重加粗）这一类不设护栏**：实测正文里 80 处命中里 79 处是
    「`**`代码`**`」被剥掉代码段后两个粗体标记贴到一起造成的**假阳性**
    ⇒ 登记 80 个例外就不是护栏 ⇒ 只在账本里作事实登记（244.62 段 38328 行那处真残留）。

⚖⚠⚖⚖⚖ 每条判据都必须**能红**：判据全部抽成**可注入的函数**（`j_cN_*`），
   ⇒ 自检与变异台才能「喂变异数据看它红」（⛔ 判据内联 ⇒ 自检恒绿、什么都没验到）。

跑法：
    python3 ledger_placeholder_audit.py
    python3 ledger_placeholder_audit.py --selftest
    python3 ledger_placeholder_audit.py --ledger <副本路径>     # 变异台用
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
LEDGER_REL = os.path.join(".cache", "xcheck", "R6_RERUN_PREREG.md")

# ⚖ 账本里「占位符」的形态：`@` + 大写字母/数字/下划线 + `@`（244.62/244.63 的替换表约定）
TOKEN_RE = re.compile(r"@[A-Z][A-Z0-9_]*@")

# ================================================================ 登记表（⚖ **字面量**）
# ⚖ 每一行 = (行号, 该行的标记集合, 该行的**原文**)
# ⚖⚠⚖⚖ **244.65 改的**：第三元素从「**去掉所有标记后**的归一化原文」改成「**原文**」
#   ⇒ 因为 244.65 更正了零假设 ⇒ 244.62 段那几行是**历史数值**（不许被改）
#   ⇒ 原来只看归一化文本 ⇒ **值被改是看不见的** ⇒ 现在原文逐字比 ⇒ 值被改也红
# ⚖ 同一行的多个标记**共享同一份**原文 ⇒ 上下文漂移（哪怕标记没动）也会红。
HOLE_LINES = [
    (38289, ("@NS@",),
     '### 【1】⚖ 扰动族：**4 个变体 ＋ 基准 = @NS@ 个场景**（244.51 那个族，逐条复用）'),
    (38301, ("@NORMSAME@",),
     '  ⇒ `denom_premise_audit` 的输出**@NORMSAME@**（`_dpa_before_24462.txt` vs `_dpa_after_24462.txt`）'),
    (38307, ("@NS@",),
     '### 【3】🔴🔴 逐场景的实测结果（全部 @NS@ 个场景）'),
    (38339, ("@NS@", "@NFLIP@"),
     '  ⚖ **实测**：@NS@ 个场景里**翻了 @NFLIP@ 个**（**全部 P+4**）'),
    (38340, ("@RPMIN@",),
     '  ⇒ 该场景里 rand 臂的趋势 p = **@RPMIN@ < 0.05** ⇒ rand 臂**也**检出了剂量趋势'),
    (38343, ("@NS@", "@WPALL@"),
     '  · ✅ **w 臂的剂量—响应是稳健的**：全部 @NS@ 个场景里 w 的趋势 p = **@WPALL@**（带 [0.0000, 0.0008]）'),
    (38344, ("@SKW@", "@SKR@"),
     '  · ✅ **剂量轴口径的多数是稳的**：w **@SKW@**、rand **@SKR@** 在全部场景**完全不变**'),
    (38345, ("@RPMIN@", "@RPMID@"),
     '  · 🔴 **「rand 臂平坦」站不住**：rand 的趋势 p 在 **@RPMIN@ … @RPMID@** 之间'),
    (38348, ("@WPALL@",),
     '  ⚖⇒ 改后的措辞：**「w 臂的剂量—响应稳健（全部扰动场景 p=@WPALL@）；rand 臂的剂量趋势'),
    (38356, ("@RPMIN@",),
     '  ⇒ ⇒ 那些场景的显著性**本来就未定** ⇒ 只印 p = @RPMIN@ 会让人以为「rand 臂也显著了」，'),
]

# ⚖ 每个标记**该填什么** —— 全部**字面量**
# ⚖⚠⚖⚖⚖ **244.65 更正**：这几个是**当前**的真值（零假设更正后现算出来的）
#   ⇒ C4 拿它们跟**现算**对 ⇒ **过期检测保住了**
#   ⇒ 而 244.62 段里的**历史**数值由 C3（原文逐字比）**冻住** ⇒ 两边都在
HOLE_VALUES = {
    "@NFLIP@": "2",
    "@NORMSAME@": "逐行相同",
    "@NS@": "5",
    "@RPMID@": "0.0876",
    "@RPMIN@": "0.0490",
    "@SKR@": "5/14",
    "@SKW@": "10/14",
    "@WPALL@": "0.0002",
}

# ⚖ 哪些标记的应填值**可以程序化重算**（尺子 = `dose_fragility_audit`，⛔ 不住在被测对象里）
RECOMPUTE_KEYS = {
    "@NS@": "NS",
    "@NFLIP@": "NFLIP",
    "@RPMIN@": "RPMIN",
    "@RPMID@": "RPMID",
    "@WPALL@": "WPALL",
    "@SKW@": "SKW",
    "@SKR@": "SKR",
}
# ⚖ 哪些标记的应填值是**文字**（⛔ 它的出处是 244.62 那次归一前后的输出对比，
#   那两个 .txt 不入库 ⇒ 只能核「值本身」，核不了「对比过程」⇒ 如实登记）
TEXT_VALUES = {"@NORMSAME@": "逐行相同"}

HOLE_MARKS = sorted(HOLE_VALUES)
N_HOLE_LINES = len(HOLE_LINES)
N_HOLE_SITES = sum(len(m) for _l, m, _n in HOLE_LINES)

# ⚖ 另一类残留：**双重加粗**（`****`）—— 244.62 脚本把「**不成立**」又套进一层粗体造成的
# ⚖ 登记规则：**原始行里**就写着 4+ 连续星号、且**不在行内代码段里**（⇒ 「`**`代码`**`」
#   剥掉后两个粗体标记贴到一起那种**假阳性**天然被排除，实测 80 处命中只剩这 1 行）
BOLD_LINES = [
    (38328, "      ⇒ 判决：«»不成立«»　⚠⚠ **翻转**"),
]
N_BOLD_LINES = len(BOLD_LINES)


# ================================================================ 扫描
def _code_mask(text):
    """⚖ 逐行标记「这行是不是代码」：**配对围栏之间**的行 ⇒ 整行算代码。

    ⚠⚠⚠ **实测踩过的坑**：账本里围栏标记 **761 个（奇数）** ⇒ 简单的「遇 ``` 就取反」
    ⇒ 从那个**未配对**的围栏起整段**反相** ⇒ 后面 4710 行**散文**被当成代码
    ⇒ 洞全被吞掉（实测：prose 扫出 0 处）。
    ⇒ 这里改成**按对配**：(F1,F2]、(F3,F4] … 算代码；
      **末尾没配上的那个围栏，其后的内容按散文处理**（保守：宁可多报也不漏报）。
    """
    lines = text.split("\n")
    fence = [i for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    mask = [False] * len(lines)
    for a, b in zip(fence[0::2], fence[1::2]):
        for i in range(a + 1, b + 1):
            mask[i] = True
    return mask


def prose_of(line, is_code):
    """⚖ 取出该行的「散文部分」：代码行 ⇒ 空；否则去掉行内代码段（`` `...` ``）。"""
    if is_code:
        return ""
    return re.sub(r"`[^`]*`", "", line)


def scan(text):
    """⚖ 扫出两样东西（都带行号，1 起）：

    · `prose`：散文里的占位符 ⇒ 真正该被回填却没回填的**洞**
    · `allm`：**整本**账本（含代码段）出现过的标记集合 ⇒ 防「洞藏在代码段里」
    """
    mask = _code_mask(text)
    prose = []
    allm = set()
    for i, (raw, is_code) in enumerate(zip(text.split("\n"), mask), 1):
        for m in TOKEN_RE.findall(raw):
            allm.add(m)
        for m in TOKEN_RE.findall(prose_of(raw, is_code)):
            prose.append((m, i))
    return prose, allm


def scan_bold_naive(text):
    """⚖ **朴素规则**（剥掉行内代码段后再找 4+ 连续星号）的命中数。

    ⚖⚠⚖⚖ **只用于报告假阳性的规模，⛔ 不作判据**：
      朴素规则会把「`**`代码`**`」剥完之后**两个粗体标记贴到一起**当成一处残留
      ⇒ 账本里它命中几十处，真残留只有一处
      ⇒ 登记几十个例外就不是护栏 ⇒ 判据 C8 用的是精确规则（`scan_bold`）。
    """
    n = 0
    for raw, is_code in zip(text.split("\n"), _code_mask(text)):
        if is_code:
            continue
        n += len(BOLD_RE.findall(prose_of(raw, False)))
    return n


def normalize_line(line, marks):
    """⚖ 归一化：把该行所有标记换成 `«»`（⇒ 与标记无关的原文指纹）。"""
    out = line
    for m in sorted(set(marks), key=len, reverse=True):
        out = out.replace(m, "«»")
    return out


BOLD_RE = re.compile(r"\*{4,}")


def scan_bold(text):
    """⚖ 找出**正文**里字面写着 4 个以上连续星号的行（= 双重加粗残留）。

    ⚖⚠⚖⚖ **规则必须精确，否则全是假阳性**：
      朴素规则（剥掉行内代码段后找 `****`）在账本里命中 **80 处**，
      其中 **79 处**是「`**`代码`**`」剥掉代码段后**两个粗体标记贴到一起**造出来的
      ⇒ 登记几十个例外就不是护栏。
    ⚖ 本规则只看**原始行**：`**` 与 `**` 挨着的**两段代码**之间，原始行里并没有连续的星号
    ⇒ 那种假阳性天然被排除；只有**原始行里就写着** `****`（且不在代码段内）才算。
    """
    out = []
    for i, (raw, is_code) in enumerate(zip(text.split("\n"), _code_mask(text)), 1):
        if is_code:
            continue
        spans = [m.span() for m in re.finditer(r"`[^`]*`", raw)]
        for m in BOLD_RE.finditer(raw):
            s, e = m.span()
            if any(s < b and a < e for a, b in spans):
                continue          # 在代码段里 ⇒ 是「词表 token 值」那类，**不算**
            out.append((m.group(0), i))
    return out


# ================================================================ 判据（⚖ 全部可注入）
def j_c0_readable(text):
    """C0：账本可读、无坏字、含 244.62 段标题。"""
    if not text:
        return False, "账本是空的"
    if "�" in text:
        return False, "账本含 U+FFFD 坏字"
    if "## 修订 244.62 —— " not in text:
        return False, "账本里找不到 244.62 段标题"
    return True, "账本可读（%d 行，U+FFFD=0，含 244.62 段）" % text.count("\n")


def j_c1_no_unregistered(prose, reg_lines):
    """C1：散文里的占位符**必须全部登记**（未登记 ⇒ 新洞 ⇒ 红）。"""
    known = set()
    for _ln, marks, _n in reg_lines:
        known.update(marks)
    bad = sorted(set(m for m, _l in prose) - known)
    if bad:
        return False, "未登记的占位符：%s（⛔ 新洞）" % bad
    return True, "散文里的占位符全部在登记内（%d 处 / %d 个标记）" % (
        len(prose), len(known))


def j_c2_sites_present(prose, reg_lines):
    """C2：登记的洞**仍在原位**（行号 + 该行的标记集合都一致）⇒ 洞被修好或漂移 ⇒ 红。"""
    byline = {}
    for m, ln in prose:
        byline.setdefault(ln, []).append(m)
    bad = []
    for ln, marks, _n in reg_lines:
        got = tuple(sorted(byline.get(ln, [])))
        if got != tuple(sorted(marks)):
            bad.append("行 %d 期望 %s 实得 %s" % (ln, sorted(marks), list(got)))
    if bad:
        return False, "登记的洞不在原位：%s" % bad
    return True, "登记的 %d 行 / %d 处洞全部仍在原位" % (len(reg_lines), N_HOLE_SITES)


def j_c3_line_fingerprint(text, reg_lines):
    """C3：登记行的**原文**逐字相同 ⇒ 历史被改（**上下文**或**值**）⇒ 红。

    ⚖⚠⚖⚖⚖ **244.65 改的**：原来比的是**归一化原文**（把标记换成 «»）
    ⇒ 标记**旁边的值**被改是**看不见**的 ⇒ 而 244.62 段那几行正是**历史数值**
    ⇒ 现在登记的是**原文**（含当时的值）⇒ 值被改也会红
    ⇒ 且 244.65 更正后，**当前**的真值由 C4 单独钉（登记的应填值 vs 现算）⇒ 两边都在。
    """
    lines = text.split("\n")
    bad = []
    for ln, marks, raw in reg_lines:
        if ln > len(lines):
            bad.append("行 %d 不存在" % ln)
            continue
        got = lines[ln - 1]
        if got != raw:
            bad.append("行 %d 原文已变" % ln)
    if bad:
        return False, "登记行的原文漂移：%s" % bad
    return True, "登记的 %d 行原文逐字未变" % len(reg_lines)


def j_c4_values_recomputed(reg_values, recomputed):
    """C4：登记的**应填值** == 程序化**现算**值（尺子 = `dose_fragility_audit`）。"""
    bad = []
    for mark, key in sorted(RECOMPUTE_KEYS.items()):
        if mark not in reg_values:
            bad.append("%s 没登记应填值" % mark)
            continue
        if key not in recomputed:
            bad.append("%s 的重算源 %s 缺" % (mark, key))
            continue
        if reg_values[mark] != recomputed[key]:
            bad.append("%s 登记 %r ≠ 现算 %r" % (mark, reg_values[mark], recomputed[key]))
    for mark, want in sorted(TEXT_VALUES.items()):
        if reg_values.get(mark) != want:
            bad.append("%s 登记 %r ≠ 应为 %r" % (mark, reg_values.get(mark), want))
    if bad:
        return False, "应填值对不上：%s" % bad
    return True, "%d 个应填值与现算逐条一致（+ %d 个文字值）" % (
        len(RECOMPUTE_KEYS), len(TEXT_VALUES))


def j_c5_mark_set(allm, reg_values):
    """C5：**整本**账本（含代码段）出现过的标记集合 == 登记的标记集合。

    ⇒ 「新洞藏在代码段里」也红（⛔ 不许用反引号把新洞藏起来）。
    """
    got = sorted(allm)
    want = sorted(reg_values)
    if got != want:
        return False, "全账本标记集合 %s ≠ 登记 %s" % (got, want)
    return True, "全账本（含代码段）标记集合 == 登记集合（%d 个）" % len(want)


def j_c6_counts(prose, reg_lines):
    """C6：散文残留**总数** == 登记处数 ⇒ 防漏扫 / 防「只查了一部分」。"""
    got, want = len(prose), sum(len(m) for _l, m, _n in reg_lines)
    if got != want:
        return False, "散文残留 %d 处 ≠ 登记 %d 处" % (got, want)
    return True, "散文残留 %d 处 == 登记 %d 处" % (got, want)


def j_c7_every_mark_checkable(reg_values):
    """C7：登记表里**每个**标记都要有核验途径（重算源 或 显式文字白名单）。

    ⇒ ⛔ 不许登记一个「编出来的数」——没有核验途径的标记 ⇒ 红。
    """
    cover = set(RECOMPUTE_KEYS) | set(TEXT_VALUES)
    miss = sorted(set(reg_values) - cover)
    extra = sorted(cover - set(reg_values))
    if miss or extra:
        return False, "覆盖不全：无核验途径 %s ／ 有途径但没登记 %s" % (miss, extra)
    return True, "%d 个标记全部有核验途径（%d 个可重算 + %d 个文字）" % (
        len(reg_values), len(RECOMPUTE_KEYS), len(TEXT_VALUES))


def j_c8_bold_residual(text):
    """C8：正文里字面 `****`（双重加粗残留）的**行数** == 登记数，且就是登记的那一行。

    ⇒ 新长出一处 ⇒ 红；登记的那处被修好/漂移 ⇒ 也红（要更新登记表）。
    """
    lines = text.split("\n")
    got = {}
    for _m, ln in scan_bold(text):
        got.setdefault(ln, 0)
        got[ln] += 1
    if len(got) != N_BOLD_LINES:
        return False, "正文里字面 `****` 的行数 %d ≠ 登记 %d（%s）" % (
            len(got), N_BOLD_LINES, sorted(got))
    for ln, norm in BOLD_LINES:
        if ln > len(lines):
            return False, "登记的粗体残留行 %d 不存在" % ln
        if normalize_line(lines[ln - 1], ["****"]) != norm:
            return False, "登记的粗体残留行 %d 原文已变" % ln
    return True, "字面 `****` 的行数 == 登记 %d 行（%s）" % (
        N_BOLD_LINES, ",".join(str(l) for l, _n in BOLD_LINES))


# ================================================================ 重算（⚖ 尺子住在产品之外）
def recompute_values():
    """⚖ 现算 244.62 那 8 个标记的应填值（复用 244.62 用的同一套机械）。

    ⛔ **不住在被测对象里** —— 尺子 = `dose_fragility_audit`（扰动族 + 层内统计）。
    """
    sys.path.insert(0, HERE)
    import dose_fragility_audit as DFA  # noqa: E402
    import contextlib
    import io as _io
    _buf = _io.StringIO()
    with contextlib.redirect_stdout(_buf):
        _rp, _res, allr = DFA.run()   # ⚖ DFA.run() 自己会打报告 ⇒ 收进缓冲区，别污染本工具输出
    sc = allr["scenarios"]
    w_ps = sorted(set(round(s["arm"]["w"]["trend"]["p"], 6) for s in sc))
    r_ps = sorted(set(round(s["arm"]["rand"]["trend"]["p"], 6) for s in sc))
    sk_w = sorted(set(tuple(s["arm"]["w"]["scope_k"]) for s in sc))
    sk_r = sorted(set(tuple(s["arm"]["rand"]["scope_k"]) for s in sc))
    return {
        "NS": str(len(sc)),
        "NFLIP": str(sum(1 for s in sc if s["flip"])),
        "RPMIN": "%.4f" % min(r_ps),
        "RPMID": "%.4f" % max(r_ps),
        "WPALL": "、".join("%.4f" % p for p in w_ps),
        "SKW": "、".join("%d/%d" % t for t in sk_w),
        "SKR": "、".join("%d/%d" % t for t in sk_r),
    }


# ================================================================ 跑
def evaluate(text, reg_lines, reg_values, recomputed):
    """⚖ 一次判定：把 8 条判据都跑一遍 ⇒ 返回 [(cid, ok, detail)]。"""
    prose, allm = scan(text)
    res = []

    def put(cid, ok, detail):
        res.append((cid, bool(ok), detail))

    put("C0", *j_c0_readable(text))
    put("C1", *j_c1_no_unregistered(prose, reg_lines))
    put("C2", *j_c2_sites_present(prose, reg_lines))
    put("C3", *j_c3_line_fingerprint(text, reg_lines))
    put("C4", *j_c4_values_recomputed(reg_values, recomputed))
    put("C5", *j_c5_mark_set(allm, reg_values))
    put("C6", *j_c6_counts(prose, reg_lines))
    put("C7", *j_c7_every_mark_checkable(reg_values))
    put("C8", *j_c8_bold_residual(text))
    return res


def read_ledger(path):
    if not os.path.isabs(path):
        path = os.path.join(REPO, path)
    if not os.path.exists(path):
        raise SystemExit("PRECOND_FAIL: 账本不存在：%s" % path)
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def run(ledger=None):
    path = ledger or LEDGER_REL
    text = read_ledger(path)
    recomputed = recompute_values()
    prose, allm = scan(text)
    res = evaluate(text, HOLE_LINES, HOLE_VALUES, recomputed)

    print("=" * 78)
    print("账本：%s（%d 行）" % (path, text.count("\n")))
    print("=" * 78)
    print("登记在案的洞（244.62 段留下的**未回填占位符**）：")
    for ln, marks, _norm in HOLE_LINES:
        print("  行 %-6d %-28s 应填 %s"
              % (ln, "、".join(marks),
                 "、".join(HOLE_VALUES.get(m, "?") for m in marks)))
    print("  ⇒ %d 行 / %d 处 / %d 个标记" % (N_HOLE_LINES, N_HOLE_SITES, len(HOLE_MARKS)))
    print("")
    print("现算出来的应填值（尺子 = dose_fragility_audit）：")
    for k in sorted(recomputed):
        print("  %-8s = %s" % (k, recomputed[k]))
    print("")
    allok = True
    for cid, ok, detail in res:
        allok = allok and ok
        print("[%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for _c, o, _d in res if o), len(res)))
    return res, allok


# ================================================================ 自检
def _mut_text(text, lineno, new):
    """⚖ 把第 lineno 行换成 new（1 起）。"""
    ls = text.split("\n")
    ls[lineno - 1] = new
    return "\n".join(ls)


def selftest(ledger=None):
    """⚖ 自检：① 真实账本上全绿 ② 每条判据在**针对性变异**下必须红。"""
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", t, why))

    path = ledger or LEDGER_REL
    text = read_ledger(path)
    recomputed = recompute_values()
    base = evaluate(text, HOLE_LINES, HOLE_VALUES, recomputed)
    chk("S0", all(o for _c, o, _d in base),
        "真实账本上全部判据必须绿（实测 %d/%d）"
        % (sum(1 for _c, o, _d in base if o), len(base)))

    def one(cid, txt=None, lines=None, vals=None, rec=None):
        """⚖ 只喂一个变异 ⇒ 目标判据必须红（其余判据红不红**不管**）。"""
        t2 = text if txt is None else txt
        l2 = HOLE_LINES if lines is None else lines
        v2 = HOLE_VALUES if vals is None else vals
        r2 = recomputed if rec is None else rec
        try:
            got = evaluate(t2, l2, v2, r2)
        except Exception as e:
            chk("S-%s" % cid, False, "判据在变异数据上**崩了**（%s）⇒ 算红" % e)
            return
        d = dict((c, o) for c, o, _x in got)
        chk("S-%s" % cid, (not d.get(cid, True)),
            "变异后 %s 必须红（实测 %s）" % (cid, "红" if not d.get(cid, True) else "**仍绿**"))

    # C0：把 244.62 段标题删掉
    one("C0", txt=text.replace("## 修订 244.62 —— ", "## 修订 X —— ", 1))
    # C1：在正文里塞一个没登记的新洞
    one("C1", txt=text + "\n⚠ 这是个没被回填的洞 @ZZZ@ 还在\n")
    # C2：把登记的行号挪一行
    bad_lines = [(HOLE_LINES[0][0] + 1, HOLE_LINES[0][1], HOLE_LINES[0][2])] + HOLE_LINES[1:]
    one("C2", lines=bad_lines)
    # C3：把登记行的归一化原文改一个字
    n0 = HOLE_LINES[0][2]
    bad_lines = [(HOLE_LINES[0][0], HOLE_LINES[0][1], n0.replace("变体", "变数"))] + HOLE_LINES[1:]
    one("C3", lines=bad_lines)
    # C4：把登记的应填值改错
    bad_vals = dict(HOLE_VALUES)
    bad_vals["@NS@"] = "6"
    one("C4", vals=bad_vals)
    # C4：把**现算**值改错（证明 C4 不是拿登记表自己当尺子）
    bad_rec = dict(recomputed)
    bad_rec["NS"] = "6"
    one("C4", rec=bad_rec)
    # C5：登记里多一个账本上没有的标记（反向：登记本身在编）
    bad_vals = dict(HOLE_VALUES)
    bad_vals["@FOO@"] = "1"
    one("C5", vals=bad_vals)
    # C6：把登记行数改少一处（总数对不上）
    one("C6", lines=HOLE_LINES[:-1])
    # C7：登记一个没有核验途径的标记
    bad_vals = dict(HOLE_VALUES)
    bad_vals["@BAR@"] = "1"
    one("C7", vals=bad_vals)
    # C8：正文里新长出一处字面 `****` ⇒ 粗体残留的登记数对不上
    one("C8", txt=text + "\n⚖ 判决：****成立****\n")

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="账本占位符审计（零 GPU、不连远端）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--ledger", default=None)
    a = ap.parse_args()
    try:
        if a.selftest:
            return selftest(a.ledger)
        res, allok = run(a.ledger)
        return 0 if allok else 1
    except SystemExit as e:
        print("%s" % e)
        return 2
    except Exception as e:
        print("PRECOND_FAIL: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
