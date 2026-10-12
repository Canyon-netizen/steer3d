#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 94 续：Y2 的 513 条台账里，有多少条能被「JSON.stringify 兜底渲染」解释。

诊断探针，不判红绿。

⚠ 背景：index.html 的 `evOneLine(g)`（:3950-3982）按 `g.name` 分派，
  命不中任何 case 时走 `default: return JSON.stringify(e).slice(0, 90)`
  —— 也就是**把整个 evidence 对象原样转成文本上屏**，
  里面每个字段名都不出现在源码里。
  ⇒ 对这条路径，Y2 的「字段名必须在宿主源码里出现」**结构性失明**。

⚠ 本脚本要量的只有一件事：**有多少条台账条目，其字段名落在某个 gate 的
  evidence 对象里**（因而可能被这条兜底路径渲染）。
⚠ 它**不能**判定「那条真的被渲染了」——
  还取决于 (a) 该 gate 的 name 是否真落进 default 分支、
  (b) 该字段是否在 JSON.stringify 的前 90 个字符内。
  ⇒ 输出只能叫「**可被解释的候选**」，不能叫「假阳性」。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
IDX = FE / "public/latent/index.html"
DEBT = ROOT / ".cache/xcheck/check_render_coverage_sitewide.debt.json"

# evOneLine 的 case 分支里**显式写过**的 gate 名 —— 命中这些的不走 default
EXPLICIT_GATES = {
    "恒等自证", "幅度配平自证", "与录制数据一致", "反事实存在",
    "存在方向性层", "内容窗可定位", "描述-因果重叠", "对照不等价", "名字预测效果",
}


def field_name(path):
    n = path.rsplit(".", 1)[-1] if "." in path else path
    if "[" in n:
        h = n.partition("[")[0]
        n = h if h else n
    return n


def find_gates(obj, path="", out=None):
    """找出所有形如 {…gate…, evidence: {…}} 的对象。"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        if "evidence" in obj and isinstance(obj["evidence"], dict):
            out.append((path, obj))
        for k, v in obj.items():
            find_gates(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_gates(v, f"{path}[{i}]", out)
    return out


def main():
    src = IDX.read_text(encoding="utf-8")
    if "JSON.stringify(e).slice(0, 90)" not in src.replace("JSON.stringify(e).slice(0,90)", "JSON.stringify(e).slice(0, 90)") \
       and "JSON.stringify(e).slice(0,90)" not in src:
        print("[错误] 兜底渲染那行没找到 ⇒ 探针的前提不成立，不发数")
        sys.exit(2)

    data_dir = FE / "public/latent/data"
    ltv = json.loads((data_dir / "ltv.json").read_text(encoding="utf-8"))
    gates = find_gates(ltv)
    print("=" * 78)
    print("修订 94（续）· 513 条台账里有多少能被「JSON.stringify 兜底渲染」解释")
    print("=" * 78)
    print(f"\n[扫描] ltv.json 里带 evidence 对象的 gate 共 {len(gates)} 个")
    if not gates:
        print("[错误] 一个 gate 都没扫到 ⇒ 探针失效")
        sys.exit(2)

    ev_keys = {}          # 字段名 -> 出现在哪些 gate 的 evidence 里
    default_hits = 0
    for gpath, g in gates:
        name = g.get("name", "")
        if name in EXPLICIT_GATES:
            continue
        default_hits += 1
        for k in g["evidence"]:
            ev_keys.setdefault(k, []).append((gpath, name))

    print(f"[分派] 其中 name 未被 case 显式列出 ⇒ 走 default 兜底的有 {default_hits} 个")
    print(f"[字段] 这些 gate 的 evidence 里共出现 {len(ev_keys)} 个不同字段名")

    debt = json.loads(DEBT.read_text(encoding="utf-8"))
    ents = debt["debt"]
    in_scope = [e for e in ents if not e["artifact"].startswith("z5::")]

    explained, not_exp = [], []
    for e in in_scope:
        (explained if e["field"] in ev_keys else not_exp).append(e)

    print(f"\n[台账] 在册非 z5 条目 {len(in_scope)} 条")
    print(f"  字段名落在兜底渲染的 evidence 键里   {len(explained)} 条"
          f"（{len(explained)/len(in_scope)*100:.1f}%）")
    print(f"  **与该路径无关**                    {len(not_exp)} 条")

    if explained:
        print("\n[可被解释的候选 · 逐条]")
        for e in explained:
            gs = ev_keys[e["field"]]
            nm = gs[0][1] or "(无名)"
            mark = "" if nm not in EXPLICIT_GATES else "  ← ⚠ 该 gate 其实走的是 case 分支"
            print(f"   {Path(e['artifact']).name:<24} {e['field']:<26} gate「{nm}」{mark}")

    print(f"\n[结论·能说什么]")
    if not explained:
        print("   0 条 ⇒ 这条兜底路径**不解释**任何台账条目；513 条不因它失真。")
    else:
        print(f"   {len(explained)} 条是**可被解释的候选**，⚠ 不是「假阳性」：")
        print("   还差两道条件才能定论 —")
        print("     ① 该字段名是否真落在 default 分支的 JSON.stringify 输出**前 90 字符**内")
        print("     ② 该字段的值是否**非空**（空值 JSON.stringify 后只有 key 名）")
        print("   ⇒ 两道都需要实点页面才能核，而实点通道不可用。")
    print(f"\n⚠ 但这**只覆盖** ltv.json 的 gate。index.html 之外还有")
    print(f"   InterventionOutcomePanel.tsx:601 的 by_verdict（键 {sorted({'right->wrong','wrong->right','wrong->wrong'})}）")
    print(f"   与 :3118 的 by_direction（键 confidence_up / confidence_down）——")
    print(f"   修订 94 正文已逐条核过，与本产物无关。")


if __name__ == "__main__":
    main()