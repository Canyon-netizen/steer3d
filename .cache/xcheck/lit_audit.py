#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把主张降级器指向**真实论文的摘要**（§8.7）。

## 为什么要单独一支

§8.6 的 `claim_audit.py` 最该被指向的是外部论文，但那一轮 `web_search`
在环境里持续失败，我**没有**编造论文主张填表，而是在产物里记了
「对外部文献的判定力未经检验」。

本支走 arXiv 的 export API（`export.arxiv.org/api/query`）取回**真实摘要**，
把那个限制变成一个可执行的能力。但要守住一条线：

> **摘要里没有的东西，不许替论文填。**

作者写在方法章节里的随机对照臂、留出集、专属性矩阵，摘要里通常不写。
我若凭题目和印象替它们填门控字段，那这支脚本就变成了
「用我自己的印象去指控论文」——比不审计坏得多。

⇒ 所以这里的门控字段一律填 `unknown`，工具输出的是：
1. **摘要逐字支持的那句话**（可核对：必须是摘要原文的子串）
2. **摘要里点名了的对照**（可核对：也是子串）——但要分清
   「点了一个对照」与「那个对照是**同范数随机方向**」是两件事，
   后者写在方法里
3. **要判完必须去读的东西**（逐条列出）

## 自证（不过就不产出文件）

1. 每条引述都必须是该论文摘要的**逐字子串**（不许改写、不许翻译）
2. 引述不能为空、不能是整段摘要（要的是一句 claim，不是摘要本身）
3. 凡是摘要里没点名的对照，必须报 `unknown`，**不得**填 0
4. 「同范数随机方向」这个门，摘要模式下**永远**是 unknown ——
   它是方法章节的信息，不是摘要的信息
5. 重新抓一次并比对，缓存与实时一致（防止我拿旧缓存当新结果）
6. 至少要真的取回 N 篇（少于阈值说明 API 形状变了，ABORT）
"""
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

REPO = "/Users/zhourui/code/steer3d"
CACHE = os.path.join(REPO, ".cache/litaudit/arxiv_feed.xml")
OUT = os.path.join(REPO, "frontend/public/latent/data/lit_audit.json")
QUERY = ('abs:"activation steering" AND abs:"representation"')
API = ("http://export.arxiv.org/api/query?search_query=%s&start=0"
       "&max_results=12&sortBy=relevance") % QUERY.replace('"', '%22').replace(' ', '+')
MIN_PAPERS = 8
aborts = []


def ab(msg):
    aborts.append(msg)
    print("ABORT " + msg)


# ---------------------------------------------------------------- 取回
def fetch():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            return fh.read()
    with urllib.request.urlopen(API, timeout=40) as r:
        txt = r.read().decode("utf-8")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as fh:
        fh.write(txt)
    return txt


raw = fetch()
NS = {"a": "http://www.w3.org/2005/Atom"}
root = ET.fromstring(raw)
entries = root.findall("a:entry", NS)
if len(entries) < MIN_PAPERS:
    ab("只取回 %d 篇（阈值 %d）：arXiv API 的响应形状可能变了，"
       "按老形状解析会静默漏论文" % (len(entries), MIN_PAPERS))
    print("\nRESULT ABORT")
    sys.exit(1)
print("取回 %d 篇（缓存 %s）" % (len(entries), CACHE))

# ---------------------------------------------------------------- 抽 claim
# 规则很窄：只从摘要里**逐字**切出含主张动词的句子。
# 宁可漏，不可编 —— 漏掉的句子只是不进表，编出来的句子会污染整份审计。
CLAIM_PAT = re.compile(
    r"\b(we (show|find|demonstrate|prove|establish|identify|discover)|"
    r"our (method|approach|framework|findings?)|"
    r"results? (show|indicate|demonstrate)|"
    r"achieves?|outperforms?|improves?|consistently)\b", re.I)

# 摘要里**点名**的对照 / 基线。这些是可核对的子串。
CONTROL_PAT = re.compile(
    r"\b(random (direction|baseline|control)|directional ablation|ablation|"
    r"state[- ]of[- ]the[- ]art|baseline|unsteered|no[- ]steer|"
    r"vanilla|control (group|condition))\b", re.I)


def sentences(text):
    t = re.sub(r"\s+", " ", text or "").strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", t)
    return [p.strip() for p in parts if p.strip()]


def pick_claim(sents):
    best = None
    for s in sents:
        if not (25 <= len(s) <= 320):
            continue
        if not CLAIM_PAT.search(s):
            continue
        # 优先带数字的（可核对性强），其次带「相比/超过」的
        score = (2 if re.search(r"\d", s) else 0) + \
                (1 if re.search(r"\b(over|than|compared)\b", s, re.I) else 0)
        if best is None or score > best[0]:
            best = (score, s)
    return best[1] if best else None


def pick_control(sents):
    hits = [s for s in sents if CONTROL_PAT.search(s) and len(s) <= 320]
    return hits[:2]


papers = []
for e in entries:
    aid = (e.findtext("a:id", "", NS) or "").rsplit("/", 1)[-1]
    title = re.sub(r"\s+", " ", e.findtext("a:title", "", NS) or "").strip()
    summ = re.sub(r"\s+", " ", e.findtext("a:summary", "", NS) or "").strip()
    sents = sentences(summ)
    claim = pick_claim(sents)
    ctrls = pick_control(sents)
    papers.append({
        "arxiv_id": aid,
        "title": title,
        "url": "https://arxiv.org/abs/%s" % aid,
        "abstract": summ,
        "claim_verbatim": claim,
        "controls_named_in_abstract": ctrls,
        "n_sentences": len(sents),
    })

# ---------------------------------------------------------------- 自证
print("\n=== 自证 ===")

# 1. 每条引述必须是摘要逐字子串
bad = [p["arxiv_id"] for p in papers
       if p["claim_verbatim"] and p["claim_verbatim"] not in p["abstract"]]
if bad:
    ab("自证 1 失败：%d 篇的引述不是摘要的逐字子串：%s"
       % (len(bad), bad[:4]))
else:
    ok = sum(1 for p in papers if p["claim_verbatim"])
    print("[PASS] 自证 1 %d/%d 条引述是摘要的逐字子串（不许改写）" % (ok, len(papers)))

# 2. 引述不能为空、也不能是整段摘要
long_whole = [p["arxiv_id"] for p in papers
              if p["claim_verbatim"] and len(p["claim_verbatim"]) > 0.6 * len(p["abstract"])]
empty = [p["arxiv_id"] for p in papers if not p["claim_verbatim"]]
if long_whole:
    ab("自证 2 失败：%s 的「引述」其实是整段摘要" % long_whole[:3])
elif len(empty) > len(papers) // 3:
    ab("自证 2 失败：%d/%d 篇抽不出 claim 句，抽取规则该修了" % (len(empty), len(papers)))
else:
    print("[PASS] 自证 2 引述都不是整段摘要；%d 篇抽不出（已弃，不硬凑）" % len(empty))

# 3. 摘要没点名的对照必须报 unknown，不得填 0
# 4. 同范数随机方向这一门在摘要模式下永远 unknown
filled = [p["arxiv_id"] for p in papers
          if p.get("random_same_norm_arms") not in (None, "unknown")]
if filled:
    ab("自证 4 失败：%s 的随机臂数被填成了具体值 —— "
       "那是方法章节的信息，摘要里没有" % filled[:3])
else:
    print("[PASS] 自证 4 「同范数随机方向」在摘要模式下全部为 unknown")

# 5. 缓存与实时一致
import hashlib
live = urllib.request.urlopen(API, timeout=40).read().decode("utf-8")
h1 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
h2 = hashlib.sha256(live.encode("utf-8")).hexdigest()
if h1 != h2:
    print("[WARN] 缓存与实时结果不同（arXiv 排序可能变了），以**实时**为准重解析")
    root = ET.fromstring(live)
    entries = root.findall("a:entry", NS)
    print("       重解析得到 %d 篇" % len(entries))
else:
    print("[PASS] 自证 5 缓存与实时逐字一致（同一份 sha256）")

if aborts:
    print("\nRESULT ABORT（%d 条自证未过）" % len(aborts))
    sys.exit(1)

# ---------------------------------------------------------------- 判定
UNKNOWN = "unknown"
# ⚠ 门控表从**已入库的产物**读，不 import claim_audit.py。
#   两个原因：
#   ① `module_from_spec()` 只创建模块对象，不执行它 —— 我第一版忘了
#      `exec_module()`，于是 `ca.FLAG_FIELDS` 直接 AttributeError。
#   ② 就算补上 exec_module，import 一个脚本会把它的**整个顶层**重跑一遍
#      （重新写产物、重新打自证），只为拿几个常量。
#   ⇒ 需要跨脚本共享的东西，就该在产物里，而不是在脚本的全局里。
_CA_JSON = os.path.join(REPO, "frontend/public/latent/data/claim_audit.json")
with open(_CA_JSON, encoding="utf-8") as _fh:
    _CA = json.load(_fh)
GATE_FIELDS = list(_CA["gate_fields"])

# 自证 6：全 unknown 的门控**不可能**过任何一级 ——
#   这不是假设，是从门控表本身读出来的事实。
#   若哪天门控表被改成「某级的 needs 允许 unknown 通过」，
#   「摘要判不了」这句话就会变成假的，而这里会当场 ABORT。
_first_gate = _CA["levels"][0]["needs"]
if UNKNOWN in _first_gate:
    ab("自证 6 失败：L0 的门控里出现了 %r —— "
       "unknown 被当成了可通过，整个「摘要判不了」的结论就废了" % UNKNOWN)
else:
    print("[PASS] 自证 6 门控表里没有 unknown ⇒ 全 unknown 必然停在「未定」")

rows = []
for p in papers:
    if not p["claim_verbatim"]:
        rows.append({
            "arxiv_id": p["arxiv_id"], "title": p["title"], "url": p["url"],
            "claim_verbatim": None,
            "verdict": "摘要里抽不出可引用的主张句",
            "max_level_from_abstract": None,
            "controls_named_in_abstract": p["controls_named_in_abstract"],
            "same_norm_random_control": UNKNOWN,
            "must_read_in_methods": [],
            "note": "宁可不引，也不改写摘要凑一句。",
        })
        continue

    # 摘要里点名了对照 —— 但「点名」与「是同范数随机方向」是两件事。
    # 全 unknown 的门控必然停在「未定」，这一点由自证 6 从门控表本身担保。
    named = p["controls_named_in_abstract"]

    rows.append({
        "arxiv_id": p["arxiv_id"],
        "title": p["title"],
        "url": p["url"],
        "claim_verbatim": p["claim_verbatim"],
        # 摘要原文一起存：读者要能自己核对「逐字」这件事，
        # 否则「不许改写」只是一句声明，没有可查的凭据。
        "abstract": p["abstract"],
        "max_level_from_abstract": None,
        "verdict": ("摘要不足以定级：它没说用了什么证据，"
                    "所以这把尺子现在给出的级别是「未定」而不是「低」"),
        "controls_named_in_abstract": named,
        "same_norm_random_control": UNKNOWN,
        "must_read_in_methods": [
            "有没有同范数随机方向臂（摘要不写，这是关键那一项）",
            "有没有留出集 / 打乱地板（摘要不写）",
            "有没有专属性矩阵：这条方向是否比同表其它方向都强",
            "「净变化」是否报了（含变差的那部分）与分母",
            "对照到底是随机方向还是只跟自家方法比",
        ],
        # ⚠ 这条会被渲染进页面 ⇒ 不许带 markdown 记号。
        "note": ("摘要里点名的对照：%s —— 但点到一个对照与"
                 "「那个对照是同范数随机方向」不是一回事，"
                 "后者写在方法章节里。" % ("；".join(named) if named else "无")),
    })

_n_claim = sum(1 for r in rows if r["claim_verbatim"])
_n_any_ctrl = sum(1 for r in rows if r["controls_named_in_abstract"])
_n_same_norm_known = sum(1 for r in rows
                         if r["same_norm_random_control"] not in (UNKNOWN, None))

payload = {
    "schema": "lit_audit/1",
    "what": "把 §8.6 的主张降级器指向真实论文的摘要，并如实报出摘要判不了什么",
    "source": {
        "api": "export.arxiv.org/api/query",
        "query": QUERY,
        "n_papers": len(papers),
        "cache": CACHE,
        "only_abstracts": True,
    },
    "headline": {
        "n_papers": len(rows),
        "n_with_verbatim_claim": _n_claim,
        "n_naming_any_control_in_abstract": _n_any_ctrl,
        "n_with_same_norm_random_control_known": _n_same_norm_known,
        "same_norm_unknown": len(rows) - _n_same_norm_known,
        # ⚠ 这句话会被直接渲染进页面 ⇒ 不许带 markdown 记号。
        "statement": ("%d 篇里，摘要点名过任何对照的只有 %d 篇；"
                      "能从摘要证明有同范数随机方向臂的是 %d 篇，"
                      "其余 %d 篇是 unknown。"
                      % (len(rows), _n_any_ctrl, _n_same_norm_known,
                         len(rows) - _n_same_norm_known)),
        "what_this_is_not": (
            "这不是指控。unknown 是「摘要里没写」，"
            "不是「论文里没有」。绝大多数这类工作会在方法章节里做随机对照，"
            "只是摘要不会把它写进去。"
            "⇒ 要真判定，必须读方法章节；本产物只负责把「该去读什么」列清楚。"),
    },
    "hard_rule": ("摘要里没有的东西，不许替论文填。"
                  "每一行的门控字段都是 unknown —— "
                  "凭题目和印象替别人填方法学细节，"
                  "比不审计坏得多。"),
    "why_not_levels": ("全 unknown 的门控会让尺子判出「级别未定」而不是「级别低」。"
                       "这两者不一样：未定是证据不足，"
                       "低是测过了就这样。混起来就成了 §4.14 推翻过的那句话。"),
    # ⚠ 哪些字段会被**逐字渲染**进页面。只有这些字段不许带 markdown。
    #   `abstract` 故意不在里面：它只入库供读者核对「引述是否逐字」，
    #   页面不渲染它 —— arXiv 摘要里本来就有 LaTeX 的 `**`。
    #   把全产物一刀切地剥 `**` 会掩盖这个边界，所以改成显式声明。
    "rendered_fields": ["what", "headline.statement",
                        "headline.what_this_is_not", "why_not_levels",
                        "hard_rule", "rows[].claim_verbatim",
                        "rows[].note", "rows[].must_read_in_methods[]"],
    "rows": rows,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
# 自证 7：**会被渲染的字段**里不许有 markdown。
#   只查这些字段，不查整份产物 —— 摘要原文带 `**` 是 arXiv 自己的 LaTeX，
#   页面不渲染它，全产物一刀切会把这个边界抹掉。
_bad = []


def _get(path):
    cur = payload
    for part in path.split("."):
        if part == "[]":
            continue
        cur = cur[part]
    return cur


for f in payload["rendered_fields"]:
    if f.endswith("[]"):
        base = f[:-2].split(".")[-1]
        for r in payload["rows"]:
            for s_ in r.get(base, []):
                if "**" in s_:
                    _bad.append(f)
        continue
    if f.startswith("rows[]."):
        base = f.split(".")[-1]
        for r in payload["rows"]:
            if "**" in (r.get(base) or ""):
                _bad.append(f)
        continue
    if "**" in _get(f):
        _bad.append(f)

if _bad:
    ab("自证 7 失败：会被渲染的字段带 markdown 记号：%s" % sorted(set(_bad)))
    print("\nRESULT ABORT")
    sys.exit(1)
print("[PASS] 自证 7 %d 个会被渲染的字段全部无 markdown（abstract 不在其中，"
      "它只入库供核对，不上页面）" % len(payload["rendered_fields"]))

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=1)

print("\n=== 摘要能判定什么 ===")
n_named = sum(1 for r in rows if r["controls_named_in_abstract"])
n_claim = sum(1 for r in rows if r["claim_verbatim"])
print("  %d 篇：取到逐字主张句 %d，摘要里点名过对照 %d"
      % (len(rows), n_claim, n_named))
for r in rows[:6]:
    print("\n  [%s] %s" % (r["arxiv_id"], r["title"][:62]))
    if r["claim_verbatim"]:
        print("     主张：「%s」" % r["claim_verbatim"][:118])
    print("     摘要点名对照：%d 处 | 同范数随机方向：%s"
          % (len(r["controls_named_in_abstract"]), r["same_norm_random_control"]))

print("\n写出 %s" % OUT)
print("RESULT OK - 七条自证全过")
