#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r111_variant_gate.py —— 修订 111-C

## 要修的病

`r107_value_onscreen.py`（修订 107，本仓沿用至今）的分诊是：

    strong = [v for v in vals if distinctive(v)]      # ← 对**原值**判区分度
    hit    = any(x in text for x in variants(v))       # ← 却拿**变体**去撞文本

⚠⚴ `variants()` 会生成 `%.0f` / `rstrip('0')` 这些形态，它们**会摧毁区分度**：

    值 55.4  →  distinctive(55.4) = True（repr '55.4' 有 4 字符）
             →  variants 含 '55'
             →  '55' 在 318 KB 的 index.html 源码里到处都是 ⇒ 判「已上屏」

⚠ 这正是预登记里早写过的那条（判值上没上屏时短值不是证据），
   但**当年只把门槛加在原值上，没加在变体上** ⇒ 门槛被 `%.0f` 绕过去了。

## 修法

把区分度判定**下沉到变体**：只有**自身**够有区分度的形态才配当证据。
形态级门槛：长度 ≥ 4 且不是 `-?\d{1,3}` 这种小整数（字符串仍 ≥ 8）。

## ⚠ 本脚本只做一件事：对同一批样本**并排**跑新旧两把尺子，把差值打出来。
   不改 r107（已发布），不改 r111_index_coverage.py（闸门仍红）。
   先把「修完会动多少数」量出来，再决定要不要立修订。
"""
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"


def die(m):
    print("[自证失败] " + m)
    sys.exit(2)


def leaves(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from leaves(v, (p + "." + str(k)) if p else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from leaves(v, "%s[%d]" % (p, i))
    elif o is not None and not (isinstance(o, str) and o == ""):
        yield p, o


CACHE = {}


def artifact_fields(fname):
    if fname in CACHE:
        return CACHE[fname]
    p = ROOT / "frontend" / fname if fname.startswith("public/") else DATA / fname
    if not p.exists():
        die("产物不存在：" + str(p))
    idx = {}
    for lp, v in leaves(json.loads(p.read_text(encoding="utf-8"))):
        nm = lp.rsplit(".", 1)[-1] if "." in lp else lp
        nm = nm.partition("[")[0] or nm
        idx.setdefault(nm, []).append(v)
    CACHE[fname] = idx
    return idx


# ---------------- 旧尺子（原值判区分度）----------------
def distinctive_old(v):
    if isinstance(v, str):
        return len(v.strip()) >= 8
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if f == int(f) and abs(f) < 100:
        return False
    return len(repr(f)) >= 4 or abs(f) >= 1000


def variants(v):
    out = set()
    if isinstance(v, str):
        s = v.strip()
        if len(s) >= 2:
            out.add(s)
        return out
    try:
        f = float(v)
    except (TypeError, ValueError):
        return out
    for nd in (0, 1, 2, 3, 4, 5, 6):
        out.add(("%%.%df" % nd) % f)
        out.add(("%.*f" % (nd, f)).rstrip("0").rstrip(".") if nd else str(int(f)))
    out.add(str(int(f)) if f == int(f) else "")
    for nd in (0, 1, 2):
        out.add(("%%.%df" % nd) % (f * 100))
    return {x for x in out if x and len(x) >= 2}


# ---------------- 新尺子：只做一件事 ----------------
# ⚠⚠ 第一版把「对原值判区分度」整个换成「对变体判区分度」，结果是
#    ON_SCREEN 30 → **38**（变多！）—— 因为值级门槛挡掉的 v（如整数 55、1.5）
#    它的补零形态 '55.0' / '1.50' 在变体级门槛下反而**放行了**。
#    ⇒ 那不是修复，是换了一把更松的尺子，且**同时动用了两个变量**。
#
# ⚠ 正确做法：候选集仍由**旧尺子**提出（保持「哪些值有资格当证据」不变），
#   只在这批候选里**剔除自身不具区分度的形态**。
#   ⇒ 任何差值都只能归因于「剔掉了弱变体」这一个变量。
SMALL_INT = re.compile(r"^-?\d{1,3}$")


def variant_is_strong(x):
    if len(x) < 4:
        return False
    return not SMALL_INT.match(x)


def tier(fn, fld, text, new):
    vals = artifact_fields(fn).get(fld)
    if vals is None:
        return None
    if new:
        cands = [x for v in vals if distinctive_old(v)
                 for x in variants(v) if variant_is_strong(x)]
    else:
        cands = [x for v in vals if distinctive_old(v) for x in variants(v)]
    if any(c in text for c in cands):
        return "ON_SCREEN"
    if any(x in text for v in vals for x in variants(v)):
        return "UNDECIDABLE"
    return "ABSENT"


# ---------------- 样本 ----------------
sec = io.open(ROOT / ".cache/mutbak/r106_out.txt", encoding="utf-8").read()
pairs = [(m.group(1), m.group(2)) for m in
         (re.match(r"\s+(\S+\.json)\s+(\S+)\s+(TYPE_DECL|COMMENT)\s*$", l)
          for l in sec.split("=== 全部盲区字段 ===")[-1].split("\n")) if m]
if len(pairs) != 74:
    die("盲区清单 %d 条 ≠ 74" % len(pairs))

CORPORA = [
    ("Next.js 面板（修订 107 的语料，40899 字符）",
     ROOT / ".cache/mutbak/r107_visible_all.txt"),
    ("独立站 index.html（修订 111 新语料，20170 字符）",
     ROOT / ".cache/mutbak/r111_visible_index.txt"),
]

# 阳性/阴性对照（同一套机制，两份语料各自独立）
PROBE_POS = ("public/latent/data/readable_subspace.json", "digit_mass|newline_mass")
PROBE_NEG = ("public/latent/data/readable_subspace.json", "bound_caveat")

print("样本：%d 个同形字段；两套语料各跑一遍新旧两把尺子\n" % len(pairs))
for label, path in CORPORA:
    if not path.exists():
        die("语料缺失：" + str(path))
    text = io.open(path, encoding="utf-8").read()
    print("=" * 96)
    print("语料：%s（%d 字符）" % (label, len(text)))
    print("=" * 96)
    for new in (False, True):
        res = {}
        for fn, fld in pairs:
            res[(fn, fld)] = tier(fn, fld, text, new)
        n_on = sum(1 for v in res.values() if v == "ON_SCREEN")
        n_ab = sum(1 for v in res.values() if v == "ABSENT")
        n_un = sum(1 for v in res.values() if v == "UNDECIDABLE")
        tag = "新尺子（旧候选集里剔掉弱变体）" if new else "旧尺子（原值级门槛，= 修订 107）"
        print("  %-34s ON_SCREEN %2d / ABSENT %2d / UNDECIDABLE %2d"
              % (tag, n_on, n_ab, n_un))
        pos = res.get(PROBE_POS)
        neg = res.get(PROBE_NEG)
        print("     阳性对照 0.0195 → %-12s %s"
              % (pos, "✓" if pos == "ON_SCREEN" else "✗ 仪器认不出已上屏的东西"))
        print("     阴性对照 bound_caveat → %-6s %s"
              % (neg, "✓" if neg == "ABSENT" else "✗ 判定虚松"))
    # 差值逐条
    diffs = []
    for fn, fld in pairs:
        o = tier(fn, fld, text, False)
        n = tier(fn, fld, text, True)
        if o != n:
            diffs.append((fn, fld, o, n))
    print("  ⚠ 新旧不一致 %d 条：" % len(diffs))
    for fn, fld, o, n in diffs:
        print("     %-42s %-28s %s → %s" % (fn.split("/")[-1], fld, o, n))
    print()

print("⚠ 读法：候选集由旧尺子提出，新尺子只在候选集里剔掉**自身不具区分度**的形态。")
print("⚠ ⇒ 候选集只减不增 ⇒ ON_SCREEN 只会变少、ABSENT 只会变多，任何差值都可归因。")
print("⚠ 「ON_SCREEN→ABSENT/UNDECIDABLE」= 修订 107 当年**用弱证据判的已上屏**。")
