#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r111_index_coverage.py —— 修订 111-B

目的：待办里挂了很久的一条 —— 「`index.html` 独立站全部条目」从没被判过。
  原因记在预登记里是「DOM/screenshot 不可用」，但修订 101 已经证明
  **实点通道受阻时可以自带 headless Chrome 走 CDP**。⇒ 这条现在能做。

⚠⚠ 本脚本量的是**独立站自己的覆盖**，不是重复母判据：
   母判据扫的是 Next.js 面板（40899 字符可见文案 / 20 个面板）。
   独立站是另一个站点（20172 字符 / 页面高 12542px），两者覆盖面不可互相代替。

## 取数口径（写死，改口径要单独立修订）

分诊依据是**源码里它到底 fetch 了哪些产物**，不是「页面上能不能找到字面」：

  NOT_FETCHED  源码没有 fetch 这个产物 ⇒ 它的值**可证**不上屏（除非硬编码在 HTML 里）
               ⇒ 这是**证明**，比「找不到字面」强一档
  ON_SCREEN    取用了，且值原样出现在整页可见文案里 ⇒ **可证已上屏**
  ABSENT       取用了，但任何形态都找不到 ⇒ **不可证上屏**（可能变形后上屏）
  UNDECIDABLE  取用了，只撞上无区分度的短值 ⇒ 说明不了任何事

## ⚠⚠ 仪器陷阱（已踩，记在这里）

第一版用 `fetch\\(\\s*[\"'\\`]([^\"'\\`]+)` 提取取用清单，得出的结论是
「独立站只取 models.json、34 个产物一个都不取」。
⚠ 而文件里有 **21 处 `fetch(`** —— 主流写法是 `dataBase()+\"x.json\"`，
**拼接式路径根本匹配不上那条字面量正则**。
⚠ 若不核 `grep -c \"fetch(\"`，这个「干净利落的 0」会被直接发布。
⇒ 提取必须覆盖拼接式；本脚本用 `(?:dataBase\\(\\)|base)\\s*\\+\\s*[\"']([^\"']+)[\"']`，
  并**把两种口径的差（1 vs 17）一并印出来**当自证。

## 三个闸门（缺一不可）

G-cal  重新实现的分诊函数必须**逐条重现**修订 107 在 Next.js 面板上的已发布分层
       （ON_SCREEN 30 / ABSENT 22 / UNDECIDABLE 22）。对不上就是仪器没校准，
       后面所有数字都作废。
G-pos  阳性对照取自**源码**（独立来源，不循环）：13 个 h1/h2 字面标题必须全在可见文案里。
G-neg  阴性对照：未取用产物的值**必须**找不到。找得到就是「NOT_FETCHED=证明」这条
       前提错了，整张分诊表作废。
"""
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend/public/latent/index.html"
VIS_IDX = ROOT / ".cache/mutbak/r111_visible_index.txt"
VIS_NEXT = ROOT / ".cache/mutbak/r107_visible_all.txt"
OUT106 = ROOT / ".cache/mutbak/r106_out.txt"
DATA = ROOT / "frontend/public/latent/data"

sys.path.insert(0, str(ROOT / ".cache/xcheck"))


def die(m):
    print("[闸门失败] " + m)
    sys.exit(2)


# ---------- 源码解析：取用清单 ----------
h = SRC.read_text(encoding="utf-8")
n_fetch = len(re.findall(r"fetch\(", h))
naive = {u.split("/")[-1] for u in re.findall(r"""fetch\(\s*["'`]([^"'`]+)["'`]""", h)}
naive = {x for x in naive if x.endswith(".json")}
real = set(re.findall(r"""(?:dataBase\(\)|base)\s*\+\s*["']([^"']+)["']""", h))
real = {x.split("/")[-1] for x in real if x.endswith(".json")}
if 'fetch("models.json")' in h:
    real.add("models.json")
real = {x for x in real if x and x != ".json"}

arts = sorted(p.name for p in DATA.glob("*.json"))
fetched = sorted(a for a in arts if a in real)
unfetched = sorted(a for a in arts if a not in real)

print("[自证] 源码里 fetch( 出现 %d 处" % n_fetch)
print("[自证] 字面量口径认出 %d 个 json：%s" % (len(naive), sorted(naive)))
print("[自证] 拼接口径认出 %d 个 json" % len(real))
print("[自证] ⚠ 两口径差 %d 个 —— 这就是第一版会发错的地方"
      % len(real - naive))
if n_fetch != 21:
    die("fetch( 出现 %d 处 ≠ 21 ⇒ 源码变了，取用清单口径要重核" % n_fetch)
if len(fetched) != 15:
    die("取用 %d 个产物 ≠ 15（%s）⇒ 口径变了" % (len(fetched), fetched))
print("[自证] 取用 %d 个 / 未取 %d 个（未取=%s）"
      % (len(fetched), len(unfetched), unfetched))

# ---------- 可见文案 ----------
if not VIS_IDX.exists():
    die("独立站可见文案不存在：" + str(VIS_IDX))
t_idx = io.open(VIS_IDX, encoding="utf-8").read()
if len(t_idx) < 15000:
    die("独立站文案过短（%d 字符）" % len(t_idx))
print("[自证] 独立站可见文案 %d 字符" % len(t_idx))


# ---------- 分诊函数（与 r107_value_onscreen.py 同实现，须过 G-cal）----------
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
    # ⚠ 修订 106 的清单里路径带 `public/latent/` 前缀，r107 里有这层处理，
    #   我第一版抄漏了 ⇒ FileNotFoundError 直接崩。口径照旧，不改。
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


def distinctive(v):
    if isinstance(v, str):
        return len(v.strip()) >= 8
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if f == int(f) and abs(f) < 100:
        return False
    return len(repr(f)) >= 4 or abs(f) >= 1000


def tier_of(fname, field, text):
    vals = artifact_fields(fname).get(field)
    if vals is None:
        return None, 0, "字段名在产物里找不到"
    strong = [v for v in vals if distinctive(v)]
    if any(any(x in text for x in variants(v)) for v in strong):
        return "ON_SCREEN", len(vals), ""
    if any(any(x in text for x in variants(v)) for v in vals):
        return "UNDECIDABLE", len(vals), ""
    return "ABSENT", len(vals), ""


# ---------- 取 74 个盲区字段 ----------
if not OUT106.exists():
    die("修订 106 的探针输出不存在：" + str(OUT106))
sec = io.open(OUT106, encoding="utf-8").read().split("=== 全部盲区字段 ===")[-1]
pairs = []
for line in sec.split("\n"):
    m = re.match(r"\s+(\S+\.json)\s+(\S+)\s+(TYPE_DECL|COMMENT)\s*$", line)
    if m:
        pairs.append((m.group(1), m.group(2)))
if len(pairs) != 74:
    die("盲区清单解析到 %d 条 ≠ 74" % len(pairs))
print("[自证] 74 个盲区字段解析成功")

# ================= G-cal：必须在 Next.js 面板上重现修订 107 的已发布分层 =================
if not VIS_NEXT.exists():
    die("Next.js 面板文案不存在，无法校准：" + str(VIS_NEXT))
t_next = io.open(VIS_NEXT, encoding="utf-8").read()
cal = {}
for fn, fld in pairs:
    tg, _k, _m = tier_of(fn, fld, t_next)
    cal[(fn, fld)] = tg
n_on = sum(1 for v in cal.values() if v == "ON_SCREEN")
n_ab = sum(1 for v in cal.values() if v == "ABSENT")
n_un = sum(1 for v in cal.values() if v == "UNDECIDABLE")
n_broken = sum(1 for v in cal.values() if v is None)
print()
print("[G-cal] 在 Next.js 面板文案上：本实现得 ON_SCREEN %d / ABSENT %d / UNDECIDABLE %d / 口径不成立 %d"
      % (n_on, n_ab, n_un, n_broken))
if (n_on, n_ab, n_un) != (30, 22, 22):
    die("G-cal 失败：修订 107 已发布的是 30/22/22，本实现对不上 ⇒ 仪器未校准，"
        "本脚本后续所有数字作废")
print("[G-cal ✓] 逐条重现修订 107 的 30/22/22 ⇒ 本仪器已校准")

# ================= G-pos：阳性对照取自源码 =================
heads = re.findall(r"<h[1-4][^>]*>([^<]{4,80})</h[1-4]>", h)
missing = [x.strip() for x in heads if x.strip() not in t_idx]
print()
print("[G-pos] 源码硬写标题 %d 个，其中 %d 个不在可见文案里%s"
      % (len(heads), len(missing), ("：%s" % missing[:3]) if missing else ""))
if len(heads) < 10 or missing:
    die("G-pos 失败：阳性对照不成立 ⇒ 这份文案不是这页渲染出来的")

# ================= 独立站分诊 =================
rows = []
for fn, fld in pairs:
    if fn not in real:
        rows.append((fn, fld, "NOT_FETCHED", 0, "源码未 fetch 该产物"))
        continue
    tg, k, msg = tier_of(fn, fld, t_idx)
    rows.append((fn, fld, tg or "BROKEN", k, msg))

# ================= G-neg：未取用产物的值必须找不到 =================
neg_rows = [r for r in rows if r[2] == "NOT_FETCHED"]
leaked = []
for fn, fld, _t, _k, _m in neg_rows:
    for v in artifact_fields(fn).get(fld, []):
        if not distinctive(v):
            continue
        if any(x in t_idx for x in variants(v)):
            leaked.append((fn, fld))
            break
print()
print("[G-neg] 未取用产物里被判 NOT_FETCHED 的 %d 个字段，"
      "其中值**泄漏**到独立站的 %d 个%s"
      % (len(neg_rows), len(leaked), ("：%s" % leaked[:5]) if leaked else ""))
if leaked:
    die("G-neg 失败：NOT_FETCHED ≠ 证明（值确实出现在页面上）⇒ 分诊表作废")
print("[G-neg ✓] 无泄漏 ⇒ 「源码未 fetch ⇒ 值可证不上屏」这条前提成立")

# ---------- 报告 ----------
cnt = {}
for r in rows:
    cnt[r[2]] = cnt.get(r[2], 0) + 1
print()
print("=== 独立站对 74 个同形字段的分诊 ===")
for k in ("ON_SCREEN", "UNDECIDABLE", "ABSENT", "NOT_FETCHED", "BROKEN"):
    if cnt.get(k):
        print("  %-12s %2d 个" % (k, cnt[k]))
print()
print("=== ON_SCREEN：独立站确实把值印给了读者 ===")
for r in rows:
    if r[2] == "ON_SCREEN":
        print("  %-42s %-30s %d 个叶子" % (r[0], r[1], r[3]))
print()
print("=== ABSENT / UNDECIDABLE / BROKEN：取用了但值没到读者眼前（需逐条判读）===")
for r in rows:
    if r[2] in ("ABSENT", "UNDECIDABLE", "BROKEN"):
        print("  %-42s %-30s %2d 个叶子  %s" % (r[0], r[1], r[3], r[2]))
print()
print("=== 字段来自哪些未取用产物（这些值独立站可证上没有）===")
byu = {}
for fn, fld, t, _k, _m in rows:
    if t == "NOT_FETCHED":
        byu.setdefault(fn, []).append(fld)
for fn, flds in sorted(byu.items(), key=lambda kv: -len(kv[1])):
    print("  %-42s %2d 个" % (fn, len(flds)))
print()
print("⚠ 口径提醒：")
print("  · NOT_FETCHED 是**证明**（源码不取 ⇒ 上不了），ABSENT 是**不可证**（可能变形后上屏）")
print("  · 独立站与 Next.js 面板是**两个站点**，两边的覆盖不可互相代替")
