#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 94（重做）：Y2「通用 key 渲染 ⇒ 判据失明」的真实波及范围。

⚠⚠ 上一版探针（r94_render_blindspot.py）**两个方向都判错**，已弃用：
  把 `Object.entries(verdict).map(([k,n]) => …`（真渲染 `:611 {k} ×{n}`）
  判成 other，把 `Object.values(…).reduce(…)`（只求和不渲染）判成 render。
  ⚠ 根因与本项目探针前两次同型：**找错了变量** ——
     该看迭代绑定变量（`k` / `a`），不是对象名（`verdict` / `AS.by_direction`）。

⇒ 本版不写正则分类器（4 个宿主里候选站点只有 3 个，肉眼读比自动可靠），
  改为：先**人工钉死**哪 3 处是真渲染，再从**数据里取真实键集**，
  最后与 64 条候选求交。

诊断探针，不判红绿。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"

# ── 人工钉死的三处真渲染（每处都读过源码，见下表的行号证据）──────────
# 1) InterventionOutcomePanel.tsx:601-612
#      {Object.entries(verdict).map(([k, n]) => ( … {k} ×{n} … data-verdict={k}
#    verdict = ans.selection?.by_verdict ?? {}          (:496)
#    ⇒ 渲染的是 by_verdict 的**键**
# 2) index.html:3118-3127
#      Object.keys(AS.by_direction).map(k => ({dir: k, …}))
#      → `${esc(LABEL[a.dir] || a.dir)} 的答案`
#    AS = C.answer_shift_free_run                        (:3093)
#    ⇒ 渲染的是 by_direction 的**键**
# 3) index.html:3972-3981
#      const pa = e.per_alpha || {}; const ks = Object.keys(pa);
#      → `α=${a} Δ=…`（a 就是键）
#    ⇒ 渲染的是 per_alpha 的**键**
RENDER_OBJ = [
    ("by_verdict",   "InterventionOutcomePanel.tsx:601（verdict = ans.selection.by_verdict，:496）"),
    ("by_direction", "index.html:3118（AS = C.answer_shift_free_run，:3093）"),
    ("per_alpha",    "index.html:3972（e.per_alpha）"),
]

TARGETS = ["linearity_law.json", "logit_lens.json", "path_readout.json"]
MD_EMPHASIS = re.compile(r"\*\*[^*\s][^*]*\*\*")


def walk(o, p="", acc=None):
    if acc is None:
        acc = []
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, f"{p}.{k}" if p else str(k), acc)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{p}[{i}]", acc)
    elif o is not None and not (isinstance(o, str) and o == ""):
        acc.append((p, o))
    return acc


def field_name(path):
    n = path.rsplit(".", 1)[-1] if "." in path else path
    if "[" in n:
        h = n.partition("[")[0]
        n = h if h else n
    return n


def np(name):
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


def collect_key_sets():
    """从**所有**交付产物里，把三处渲染对象的真实键集取出来。"""
    out = {}
    for f in sorted((FE / "public/latent/data").glob("*.json")) + [FE / "public/latent/models.json"]:
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        for obj_name, _src in RENDER_OBJ:
            hits = []
            def scan(o, path=""):
                if isinstance(o, dict):
                    if obj_name in o and isinstance(o[obj_name], dict):
                        hits.extend(o[obj_name].keys())
                    for k, v in o.items():
                        scan(v, f"{path}.{k}" if path else str(k))
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        scan(v, f"{path}[{i}]")
            scan(data)
            if hits:
                out.setdefault(obj_name, set()).update(map(str, hits))
    return out


def main():
    print("=" * 78)
    print("修订 94（重做）·「通用 key 渲染 ⇒ 判据失明」的真实波及范围")
    print("=" * 78)
    print("\n[前提] 四个宿主里**真正把 key 当可见文案渲染**的站点，人工钉死 3 处：")
    for name, src in RENDER_OBJ:
        print(f"   · {name:<14} {src}")
    print("⚠ 上一版探针用「源码出现过 Object.keys 字符串」当代理，判错了两个方向，已弃用。")

    ks = collect_key_sets()
    print(f"\n[键集] 从交付产物里取到的三处渲染对象的真实键：")
    for name, _src in RENDER_OBJ:
        keys = sorted(ks.get(name, []))
        print(f"   {name:<14} {len(keys)} 个键：{keys[:10]}{' …' if len(keys) > 10 else ''}")
    union = set().union(*ks.values()) if ks else set()
    print(f"   三处键的并集 {len(union)} 个 ⇒ **封闭词表**，不是「任意 key」")

    # 64 条候选
    hosts = {}
    for p in sorted(FE.glob("components/*.tsx")):
        hosts[p] = p.read_text(encoding="utf-8")
    idx = FE / "public/latent/index.html"
    if idx.exists():
        hosts[idx] = idx.read_text(encoding="utf-8")

    cands = []
    for nm in TARGETS:
        f = FE / "public/latent/data" / nm
        data = json.loads(f.read_text(encoding="utf-8"))
        acc = walk(data)
        names = {}
        for pth, _v in acc:
            fn = field_name(pth)
            if fn and fn not in names:
                names[fn] = pth
        owners = [q for q, s in hosts.items() if nm in s]
        for fn in sorted(names):
            if not any(np(fn).search(hosts[q]) for q in owners):
                cands.append((nm, fn, names[fn]))

    print(f"\n[候选] 三个被排除产物的「Y2 会报未渲染」字段共 {len(cands)} 条")
    hit = [c for c in cands if c[1] in union]
    print(f"[交集] 其中键落在三处渲染词表里的：**{len(hit)} 条**")
    for nm, fn, pth in hit:
        print(f"   {nm:<22} {fn:<26} {pth[:60]}")

    print(f"\n[结论]")
    if not hit:
        print("   0 条 ⇒ 「通用 key 渲染」这条失明路径**解释不了任何一条候选**。")
        print("   ⇒ 修订 90.4 写的「2/4 宿主含通用 key 迭代 ⇒ 判据结构性失明」**说过头了**：")
        print("     真渲染站点只有 3 处，且渲染的都是**封闭词表**的键，")
        print("     而 64 条候选的字段名与这三张表**零交集**。")
    else:
        print(f"   {len(hit)} 条可能被通用渲染解释 ⇒ 需逐条人工判读。")
    print("\n⚠ 这**不等于**「那 64 条都真的没上屏」——")
    print("  「键不在渲染词表里」只说明「不是被这三处渲染的」，")
    print("  仍可能有别的渲染路径（动态 key 拼接、把整块 JSON.stringify 上屏等）。")
    print("  ⇒ 定论仍然要实点页面，而实点通道不可用。")

    if not ks:
        print("\n[错误] 三处渲染对象的键集一个都没在交付产物里找到 ⇒ 探针失效，不发数")
        sys.exit(2)
    print(f"\n[够测性] 取到的键集非空（{len(union)} 个）—— 探针至少量到了东西。")


if __name__ == "__main__":
    main()