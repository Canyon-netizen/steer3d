#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r107_value_onscreen.py —— 修订 107

修订 106 量到 74 个字段的「已渲染」判定是靠类型声明/注释撑起来的，
但**真实盲区大小未知**。本脚本用**整页真实可见文案**去核这 74 个字段的**值**
有没有真的印给读者看。

⚠⚠ 口径必须写清楚，否则会得出反向的错误结论：
   值**原样出现** ⇒ 可证已上屏（强证据）
   值**原样不出现** ⇒ **不可证**未上屏 —— 它可能变形后上屏
                      （取整、成百分比、换单位、只印其中的差值）
   ⇒ 所以「原样缺席」集合是**未上屏真值的上界**，不是下界。

两个对照（缺一不可）：
   阳性：digit_mass|newline_mass 的值 0.0195 **必须**被找到
         （§101 实测它在页面上；找不到就是这台仪器坏了）
   阴性：bound_caveat 的值**必须**找不到
         （修订 106 三条路径已证它确定不上屏；找到了就是判定太松）
"""
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT106 = ROOT / ".cache/mutbak/r106_out.txt"
VIS = ROOT / ".cache/mutbak/r107_visible_all.txt"
DATA = ROOT / "frontend/public/latent/data"

def die(m):
    print("[自证失败] " + m)
    sys.exit(2)

# ---------- 自证 1：可见文案必须真的拿到了数据 ----------
if not VIS.exists():
    die("整页文案文件不存在：" + str(VIS))
text = io.open(VIS, encoding="utf-8").read()
if len(text) < 3000:
    die("整页文案过短（%d 字符）" % len(text))
print("[自证] 整页可见文案 %d 字符" % len(text))
# 页面上的已知数必须在里面 —— 否则读到的是空壳
for probe in ["0.8588", "至少 14 条", "0.5537", "0.7087"]:
    if probe not in text:
        die("可见文案里找不到已知的 %r ⇒ 这份文本不是渲染出来的页面" % probe)
print("[自证] 4 个已知页面数（0.8588 / 至少 14 条 / 0.5537 / 0.7087）全部在文案内")

# ---------- 取 74 个字段（来源：修订 106 的探针输出，断言条数） ----------
src = io.open(OUT106, encoding="utf-8").read()
sec = src.split("=== 全部盲区字段 ===")[-1]
pairs = []
for line in sec.split("\n"):
    m = re.match(r"\s+(\S+\.json)\s+(\S+)\s+(TYPE_DECL|COMMENT)\s*$", line)
    if m:
        pairs.append((m.group(1), m.group(2)))
if len(pairs) != 74:
    die("从修订 106 输出里解析到 %d 条，预期 74 ⇒ 清单口径变了" % len(pairs))
print("[自证] 修订 106 的盲区清单 74 条解析成功")

# ---------- 产物取值 ----------
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

def variants(v):
    """一个值可能被印出来的所有形态。"""
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
    # 百分比 / 折叠差值等常见变形
    for nd in (0, 1, 2):
        out.add(("%%.%df" % nd) % (f * 100))
    return {x for x in out if x and len(x) >= 2}

def distinctive(v):
    """这个值够不够「有区分度」，够不够资格当上屏的证据。

    ⚠⚠ 第一版没有这一层，于是短值制造了大量**假阳性**：
    `bpath_marker_steering.json :: 20` 在 40899 字里撞上「20 个候选」
    ⇒ 被判成「已上屏」—— 与那个字段毫无关系。
    ⇒ 门槛：字符串 ≥ 8 字；数字的最短形态 ≥ 4 字符**且**不是常见整数。
    """
    if isinstance(v, str):
        return len(v.strip()) >= 8
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if f == int(f) and abs(f) < 100:        # 0/1/2/3/4/20… 在长文本里必然撞上
        return False
    return len(repr(f)) >= 4 or abs(f) >= 1000


rows = []
for fname, field in pairs:
    idx = artifact_fields(fname)
    vals = idx.get(field)
    if vals is None:
        rows.append((fname, field, None, None, "字段名在产物里找不到（口径不符）"))
        continue
    strong = [v for v in vals if distinctive(v)]
    hit_strong = any(any(x in text for x in variants(v)) for v in strong)
    hit_any = any(any(x in text for x in variants(v)) for v in vals)
    if hit_strong:
        tier = "ON_SCREEN"
    elif hit_any:
        tier = "UNDECIDABLE"      # 只撞上无区分度的短值 ⇒ 说明不了任何事
    else:
        tier = "ABSENT"
    rows.append((fname, field, len(vals), tier, ""))

# ---------- 两个对照 ----------
pos = [r for r in rows if r[1] == "digit_mass|newline_mass"]
neg = [r for r in rows if r[1] == "bound_caveat"]
print()
if not pos or pos[0][3] != "ON_SCREEN":
    die("阳性对照失败：0.0195 应判为上屏 ⇒ 本仪器判不出已上屏的东西")
print("[阳性对照 ✓] 0.0195 判为 ON_SCREEN ⇒ 仪器能认出已上屏的东西")
if not neg or neg[0][3] != "ABSENT":
    die("阴性对照失败：bound_caveat 应判为 ABSENT ⇒ 判定虚松")
print("[阴性对照 ✓] bound_caveat 判为 ABSENT ⇒ 判定不虚松")

onscreen = [r for r in rows if r[3] == "ON_SCREEN"]
absent = [r for r in rows if r[3] == "ABSENT"]
undec = [r for r in rows if r[3] == "UNDECIDABLE"]
broken = [r for r in rows if r[3] is None]

print()
print("=== 结果（74 个同形字段，三分）===")
print("  ON_SCREEN（有区分度的值出现在文案里 ⇒ **可证已上屏**）: %d" % len(onscreen))
print("  ABSENT（任何形态都找不到 ⇒ **不可证上屏**）            : %d" % len(absent))
print("  UNDECIDABLE（只撞上无区分度的短值 ⇒ 说明不了任何事）    : %d" % len(undec))
print("  口径不成立                                              : %d" % len(broken))
print()
print("⚠ ABSENT 是**未上屏真值的上界**（值可能变形后上屏）；")
print("⚠ UNDECIDABLE 那一批**不是证据**，只能靠逐条判读定性。")
print()
print("=== ON_SCREEN：名字不出现，但有区分度的值到了读者眼前 ===")
for f, n, k, _t, _m in sorted(onscreen):
    print("  %-44s %s" % (f, n))
print()
print("=== ABSENT：任何形态都找不到（需逐条判读）===")
for f, n, k, _t, _m in sorted(absent):
    print("  %-44s %-32s %d 个叶子" % (f, n, k))
print()
print("=== UNDECIDABLE：只撞上短值，不可判定 ===")
for f, n, k, _t, _m in sorted(undec):
    print("  %-44s %-32s %d 个叶子" % (f, n, k))