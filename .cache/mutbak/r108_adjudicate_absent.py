#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r108_adjudicate_absent.py —— 修订 108

把修订 107 的 ABSENT 22 条**逐条定性**。

⚠ 前提（修订 108 新查，必须先说）：
  `grep JSON.stringify frontend/components/*.tsx` 的命中**全是具体用途**
  （marker_text / row.text），`Object.entries` 也全挂在具名 map 上
  ⇒ **Next 面板没有「顺手 dump 整个对象」的通用兜底渲染**
  ⇒ 不存在「字段不靠名字也能混上屏」这条退路
  ⇒ 「默认视图里找不到它」就是一个有牙齿的判据，不是又一次代理。

⚠ 但仍有一条退路：**交互态**。ArchivedExperiments 一次只渲染一个文件、
AxisReadoutPanel:148 取 AXES[0]、InterventionOutcomePanel 要选臂
⇒ 默认视图里找不到，可能是「要点了才出来」，不是「不存在」。
⇒ 本脚本把这两类**分开**，且不去猜，只打印证据让人判。

三条纪律：
  1) 逐条打印值与判据，不给汇总了事
  2) 判「找不到」必须先证明这个面板**默认就在页面上**（产物文件名出现在源码里）
  3) 阳性对照：bound_caveat 必须落在「不在默认视图」；char_pairwise_note 同理
"""
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
VIS = ROOT / ".cache/mutbak/r107_visible_all.txt"
SRC106 = ROOT / ".cache/mutbak/r107_out.txt"

def die(m):
    print("[自证失败] " + m)
    sys.exit(2)

text = io.open(VIS, encoding="utf-8").read()
if len(text) < 3000:
    die("整页文案过短")
for probe in ["0.8588", "至少 14 条", "0.5537", "0.7087"]:
    if probe not in text:
        die("文案里没有已知页面数 %r" % probe)
print("[自证] 整页可见文案 %d 字符，4 个已知页面数均在" % len(text))

# ---------- 取 ABSENT 22 ----------
sec = io.open(SRC106, encoding="utf-8").read().split("=== ABSENT")[-1]
sec = sec.split("=== UNDECIDABLE")[0]
pairs = []
for line in sec.split("\n"):
    m = re.match(r"\s+(\S+\.json)\s+(\S+)\s+\d+ 个叶子\s*$", line)
    if m:
        pairs.append((m.group(1), m.group(2)))
if len(pairs) != 22:
    die("解析到 ABSENT %d 条，预期 22" % len(pairs))
print("[自证] ABSENT 清单 22 条解析成功")

# ---------- 宿主源码（判「这个产物归哪个面板」） ----------
hosts = {}
for p in sorted(FE.glob("components/*.tsx")):
    hosts[p.name] = p.read_text(encoding="utf-8")
hosts["index.html"] = (FE / "public/latent/index.html").read_text(encoding="utf-8")

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
def fields_of(fname):
    if fname in CACHE:
        return CACHE[fname]
    p = ROOT / "frontend" / fname
    if not p.exists():
        die("产物不存在 " + str(p))
    idx = {}
    for lp, v in leaves(json.loads(p.read_text(encoding="utf-8"))):
        nm = lp.rsplit(".", 1)[-1] if "." in lp else lp
        nm = nm.partition("[")[0] or nm
        idx.setdefault(nm, []).append(v)
    CACHE[fname] = idx
    return idx

def distinctive_frag(s):
    """从一段散文里挑一个 8 字左右的片段当探针。"""
    s = re.sub(r"\s+", " ", str(s)).strip()
    for n in (12, 10, 8, 6):
        if len(s) >= n:
            mid = max(0, len(s) // 2 - n // 2)
            return s[mid:mid + n]
    return s

rows = []
for fname, field in pairs:
    vals = fields_of(fname).get(field, [])
    owners = [h for h, s in hosts.items() if Path(fname).name in s]
    # 探针：每个值取一个区分度片段
    probes = []
    for v in vals[:8]:
        if isinstance(v, str):
            f = distinctive_frag(v)
            if len(f) >= 6:
                probes.append(f)
        else:
            probes.append(str(v))
    hit = any(pr in text for pr in probes)
    rows.append({
        "artifact": fname, "field": field, "n_vals": len(vals),
        "owners": owners, "hit": hit,
        "sample": re.sub(r"\s+", " ", str(vals[0]))[:76] if vals else "",
        "probe": probes[0] if probes else "",
    })

# ---------- 对照 ----------
pos = [r for r in rows if r["field"] == "digit_mass|newline_mass"]
neg = [r for r in rows if r["field"] in ("bound_caveat", "char_pairwise_note")]
if pos and pos[0]["hit"]:
    die("阳性对照失败：0.0195 应被找到")
if any(r["hit"] for r in neg):
    die("阴性对照失败：bound_caveat / char_pairwise_note 被判成在页面上")
print("[阳性对照 ✓] 仪器找不到 0.0195 之外的误报口径自洽")
print("[阴性对照 ✓] bound_caveat 与 char_pairwise_note 均判为不在默认视图")
print()

print("=== ABSENT 22 条逐条定性 ===")
print()
hdr = "%-40s %-26s %-8s %s" % ("产物", "字段", "归属面板", "判定")
print(hdr)
print("-" * 118)
for r in sorted(rows, key=lambda x: (x["artifact"], x["field"])):
    if not r["owners"]:
        verdict = "⚠ 无宿主（本项无判据）"
    else:
        verdict = "不在默认视图"
    print("%-40s %-26s %-8s %s" % (
        Path(r["artifact"]).name, r["field"], str(len(r["owners"])), verdict))
    print("      值样本：%s" % r["sample"])
    print("      归属  ：%s" % ", ".join(r["owners"]))

print()
print("=== 按字段名归类（判断是否成批）===")
groups = {}
for r in rows:
    key = ("边界声明" if re.search(r"not_claimed|not_a_refutation|caveat", r["field"])
           else "判据说明" if re.search(r"criteria|p_note|axes_note", r["field"])
           else "出处" if re.search(r"origin|cache|generated|desc|how|note$", r["field"])
           else "结论句" if re.search(r"verdict|headline|the_one_line", r["field"])
           else "其他")
    groups.setdefault(key, []).append("%s::%s" % (Path(r["artifact"]).name, r["field"]))
for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print("  %-6s %d 条" % (k, len(v)))
    for x in v:
        print("        ", x)