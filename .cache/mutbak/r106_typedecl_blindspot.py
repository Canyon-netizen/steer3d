#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r106_typedecl_blindspot.py —— 修订 106

母判据 `check_render_coverage_sitewide.py:180-183` 的判红条件是：

    if any(name_pattern(nm).search(hs[o]) for o in owners):
        continue          # 字段名在宿主源码里出现 ⇒ 算「已渲染」

⚠ 这是一条**按字段名匹配源码**的**代理**指标（脚本 docstring :17-20 自己声明了）。
⚠ 而 **TypeScript 类型声明**也会让名字出现：

    SubspacePanel.tsx:74    bound_caveat: string;

⇒ 该字段被判为「已渲染」⇒ 永远不进台账。
⚠ 而修订 103.4 已实测：`bound_caveat` 在全部 .tsx 里**只出现这 1 次**，
   面板那段下界前提是手写 JSX ⇒ **它从不上屏**。

⚗ ⇒ 「新增未渲染 0 个」是一个**否定性断言**，而它建立在「字段名出现过 = 渲染了」
   这个代理上 ⇒ **类型声明是它的盲区**。

本脚本量：全站有多少字段落进这个盲区。

三条纪律：
  1) **不重新实现口径** —— 直接 import 母判据（它有 __main__ 守卫）
  2) **阳性对照** —— 必须能把已知的 `bound_caveat` 抓出来，否则本探针没有测量能力
  3) 拿不到阳性对照 ⇒ exit 2，绝不输出「0 个」
"""
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOM = ROOT / ".cache/xcheck/check_render_coverage_sitewide.py"
FE = ROOT / "frontend"

spec = importlib.util.spec_from_file_location("mom", MOM)
mom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mom)          # 有 __main__ 守卫，import 不会跑 main()


def strip_comments(s):
    """剥 TS/JS 注释，**但保持行结构与每行长度不变**。

    ⚠⚠ 第一版用全局剥注释再按**字符偏移**映射回原文 ——
    剥注释会改变长度和行号 ⇒ 偏移全部错位 ⇒
    `vector_roles.json` 的 median/rho/status/pass 全被误判成 COMMENT。
    ⚠ 而**阳性对照照样通过**（判据是「全 ∈ {TYPE_DECL, COMMENT}」，
    此时一切都是 COMMENT ⇒ 必然命中）⇒ **能被平凡满足的对照不是对照**。
    ⇒ 改成**逐行剥、行结构与行内长度都保持**，偏移才对得上。
    """
    lines = s.split("\n")
    out = []
    in_block = False
    for line in lines:
        buf = []
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if in_block:
                if c == "*" and i + 1 < n and line[i + 1] == "/":
                    in_block = False
                    buf.append("  ")      # 同行同列，两字符
                    i += 2
                else:
                    buf.append(" ")      # 同行同列
                    i += 1
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "/":
                buf.append("  ")          # 同行同列
                i += 2
                while i < n:
                    buf.append(" "); i += 1
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "*":
                in_block = True
                buf.append("  "); i += 2
                continue
            if c in "`\"'":
                q = c; buf.append(c); i += 1
                while i < n and line[i] != q:
                    if line[i] == "\\":
                        buf.append(line[i]); i += 1
                    if i < n:
                        buf.append(line[i]); i += 1
                if i < n:
                    buf.append(line[i]); i += 1
                continue
            buf.append(c); i += 1
        # 只要求**行数一致**，不要求行内长度一致 ——
        # 后者更难保证，而后面改成按行号定位，根本不需要长度对齐。
        out.append("".join(buf))
    return "\n".join(out)


def strip_ok(s):
    """自证：逐行剥之后行数必须与原文一致（按行号定位的前提）。"""
    return len(s.split("\n")) == len(strip_comments(s).split("\n"))


TYPE_DECL = re.compile(
    r"^\s*([A-Za-z_$][\w$]*)\??\s*:\s*[A-Za-z_$][\w$<>|\[\]{},\s.]*;?\s*$")


def classify_line(raw_line, stripped_line, name):
    """把「某一行里出现了 name」这一次命中归类。

    ⚠ 按**行号**定位，不按字符偏移 —— 剥注释会改变长度，
      用偏移映射必然错位（第一版就是这么把 median/rho 全判成 COMMENT 的）。
    """
    if name not in raw_line:
        return "SKIP"                       # 理论上不会走到
    if name not in stripped_line:
        return "COMMENT"                    # 剥掉注释后这行就没有它了 ⇒ 只活在注释里
    if TYPE_DECL.match(stripped_line.strip()):
        return "TYPE_DECL"
    return "REAL"


hs = mom.hosts()
bad = [h.name for h, s in hs.items() if not strip_ok(s)]
if bad:
    print("[自证失败] 逐行剥之后行结构变了：%s" % bad)
    sys.exit(2)
hs_stripped = {h: strip_comments(s) for h, s in hs.items()}
print("[自证] %d 个宿主剥注释前后行数一致 ⇒ 可按行号定位"
      % len(hs))

# ---------- 校准：先复现母判据自己的口径 ----------
rep = mom.scan()
print("[校准] 母判据 scan() 复现：%d 个产物 / %d 个叶子 / %d 个排除"
      % (rep["n_artifacts_checked"], rep["n_leaves_total"], len(rep["excluded"])))
ledger = json.load(io.open(MOM.with_suffix("").with_name(
    "check_render_coverage_sitewide.debt.json"), encoding="utf-8"))
debt_names = set(d["field"] for d in ledger["debt"])
n_debt = sum(len(a["unrendered"]) for a in rep["artifacts"])
print("[校准] 本次算出的未渲染字段数 %d；台账条数 %d" % (n_debt, len(ledger["debt"])))

blind = []
stat = {"REAL": 0, "TYPE_DECL": 0, "COMMENT": 0}
for f in mom.artifacts():
    rel = str(f.relative_to(FE))
    if not f.exists():
        continue
    owners = [h for h, s in hs.items() if f.name in s]
    data = json.loads(f.read_text(encoding="utf-8"))
    acc = []
    list(mom.leaves(data, acc=acc))
    if len(acc) >= mom.EXCL_MIN_LEAVES:
        n_str = sum(1 for _, v in acc if isinstance(v, str))
        if acc and n_str / len(acc) < mom.EXCL_MAX_STR_RATIO:
            continue                      # 排除表内的产物本项无判据
    names = {}
    for p, _v in acc:
        nm = mom.field_name(p)
        if nm and nm not in names:
            names[nm] = p
    for nm, first in names.items():
        if nm in debt_names:
            continue                      # 已在台账里，不算盲区
        kinds = []
        for o in owners:
            rawl = hs[o].split("\n")
            strl = hs_stripped[o].split("\n")
            pat = mom.name_pattern(nm)
            for i, line in enumerate(rawl):
                if pat.search(line):
                    k = classify_line(line, strl[i] if i < len(strl) else "", nm)
                    if k != "SKIP":
                        kinds.append(k)
        if not kinds:
            continue                      # 这才该进台账（母判据已归入）
        for k in kinds:
            stat[k] += 1
        if all(k in ("TYPE_DECL", "COMMENT") for k in kinds):
            blind.append({"artifact": rel, "field": nm, "first": first,
                          "kinds": sorted(set(kinds)), "n_hits": len(kinds)})

print()
print("[统计] 字段名在宿主里出现的全部次数，按出现形态分：")
for k, v in stat.items():
    print("   %-10s %d 次" % (k, v))
print()
print("⇒ 只靠「类型声明/注释」出现 ⇒ 被母判据算作已渲染、实际不上屏：")
print("   **%d 个字段**（分布在 %d 个产物）"
      % (len(blind), len(set(b["artifact"] for b in blind))))

# ---------- 负对照：已知真上屏的字段必须被判成 REAL ----------
# ⚠ 只设阳性对照不够：第一版正因为「一切都被判成 COMMENT」而让阳性对照
#   **平凡通过**。负对照防的正是这个 —— 它要求仪器**能报出不是盲区的东西**。
NEG = "readable_directions_lower_bound"      # :158/:173 直接印成「至少 14 条」
neg_kinds = []
for o in hs:
    if "readable_subspace.json" not in hs[o]:
        continue
    rawl = hs[o].split("\n")
    strl = hs_stripped[o].split("\n")
    pat = mom.name_pattern(NEG)
    for i, line in enumerate(rawl):
        if pat.search(line):
            neg_kinds.append(classify_line(line, strl[i] if i < len(strl) else "", NEG))
print()
print("[负对照] %s 在归属宿主里的出现形态：%s" % (NEG, neg_kinds))
if "REAL" not in neg_kinds:
    print("[自证失败] 负对照失败：一个确定真上屏的字段没被判成 REAL")
    print("           ⇒ 仪器把所有东西都判成了盲区形态，%d 这个数字是假的" % len(blind))
    sys.exit(2)
print("[负对照 ✓] 有 REAL 出现 ⇒ 仪器不是退化的（%d 次命中中 %d 次 REAL）"
      % (len(neg_kinds), neg_kinds.count("REAL")))

# ---------- 阳性对照：必须能抓到已知的 bound_caveat ----------
hits = [b for b in blind if b["field"] == "bound_caveat"]
if not hits:
    print("[自证失败] 阳性对照失败：没抓到已知的 bound_caveat")
    print("           ⇒ 本探针没有测量能力，%d 这个数字不可信" % len(blind))
    sys.exit(2)
print("[阳性对照 ✓] bound_caveat 被抓到了：")
for h in hits:
    print("   %s :: %s  出现形态=%s 命中 %d 次"
          % (h["artifact"], h["field"], "/".join(h["kinds"]), h["n_hits"]))

print()
print("=== 全部盲区字段 ===")
for b in sorted(blind, key=lambda x: (x["artifact"], x["field"])):
    print("  %-44s %-34s %s" % (b["artifact"], b["field"], "/".join(b["kinds"])))