#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⛔⛔ **已弃用 —— 不要运行，也不要引用它的输出。** ⛔⛔

弃用理由见预登记 `.cache/xcheck/R6_RERUN_PREREG.md` §94.5。
保留它只为记录一次失败：**自动分类器两个方向都判错了**。
正确版本是 `r94_render_blindspot2.py`。

⚠⚠ 本脚本唯一的实际危害：它的**最终结论碰巧与正确版一致**
（「通用 key 渲染解释 0 条」），而它的**中间推理全是错的**
⇒ 谁要是只看结论不看这段横幅，就会以为那条路径已经被自动核实过了。

—————————————————————————————————————————————
以下为原始（错误的）实现，原样保留供对照。

修订 94：核实「通用 key 迭代 ⇒ Y2 字段名判据失明」这条到底成立多少。

⚠⚠ 本脚本的存在是因为我在修订 90.4 **说过头了**：
那里写「宿主里出现通用 key 迭代写法的文件 11 个，其中这 3 个产物的 4 个宿主
有 2 个 ⇒ 判据结构性失明」。
⚠ 那是用「源码里出现过 Object.keys 这个**字符串**」当代理，
  而**计数 / 取值 / 排序**根本不构成失明 ——
  只有「把 key 当**可见文案**渲染出来」才构成。
⇒ 本脚本先分清这三类，再查那 64 条候选里**有没有一条**真能被它解释。

本脚本是诊断探针，不判红绿。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
IDX = FE / "public/latent/index.html"

# 修订 90 反事实测出的三个被排除产物 + 它们在 §90.4 的 64 条候选
TARGETS = ["linearity_law.json", "logit_lens.json", "path_readout.json"]

# 母判据 :226 逐字照抄
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


def field_name(path: str) -> str:
    n = path.rsplit(".", 1)[-1] if "." in path else path
    if "[" in n:
        h = n.partition("[")[0]
        n = h if h else n
    return n


def name_pattern(name: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


def hosts_of(names):
    out = {}
    for p in sorted(FE.glob("components/*.tsx")):
        out[p] = p.read_text(encoding="utf-8")
    if IDX.exists():
        out[IDX] = IDX.read_text(encoding="utf-8")
    return {p: s for p, s in out.items() if any(n in s for n in names)}


def classify_sites(src: str, path_name: str):
    """把三种 `Object.keys/entries/values` 用法分开。

    ⚠ 这是本轮的核心修正：**出现字符串 ≠ 渲染 key**。
      count   —— 只数个数 / 取首元素 / 排序      ⇒ 不构成失明
      render  —— key 进了输出模板（${…} / 文本节点）⇒ **才是失明**
      other   —— 其余（.map 出的值里不含 key 等）   ⇒ 待人工看
    """
    lines = src.split("\n")
    out = []
    for i, ln in enumerate(lines, 1):
        if not re.search(r"Object\.(keys|entries|values)\s*\(", ln):
            continue
        # 取往后 12 行当上下文
        ctx = "\n".join(lines[i - 1: i + 12])
        m = re.search(r"Object\.(keys|entries|values)\s*\(\s*([A-Za-z_$][\w$.\[\]'\"]*)", ln)
        arg = m.group(2) if m else "?"
        kind = "other"
        # 计数：紧跟 .length / 取 [0] / 只进 reduce|filter|sort
        if re.search(r"Object\.(keys|entries|values)\s*\([^)]*\)\s*\.length", ln) or \
           re.search(r"Object\.keys\s*\([^)]*\)\s*\[\s*0\s*\]", ln):
            kind = "count"
        # 渲染：局部变量名出现在模板插值里
        elif re.search(r"\$\{[^}]*\b" + re.escape(arg.split(".")[-1].split("[")[0]) + r"\b", ctx):
            kind = "render"
        out.append((i, kind, arg, ln.strip()[:96]))
    return out


def main():
    hs = hosts_of(TARGETS)
    print("=" * 78)
    print("修订 94 · 「通用 key 迭代 ⇒ 判据失明」到底成立多少（修正 90.4）")
    print("=" * 78)

    n_render = 0
    for p, s in hs.items():
        sites = classify_sites(s, p.name)
        c = sum(1 for _i, k, _a, _l in sites if k == "count")
        r = sum(1 for _i, k, _a, _l in sites if k == "render")
        o = len(sites) - c - r
        n_render += r
        print(f"\n── {p.name}（{len(sites)} 处 Object.* 用法）")
        print(f"   计数/取值 {c}  ·  **渲染 key** {r}  ·  待看 {o}")
        for ln, kind, arg, text in sites:
            mark = {"count": "·", "render": "★", "other": "?"}[kind]
            print(f"   {mark} :{ln:<5} [{kind:<6}] {arg:<22} {text}")
    print(f"\n[汇总] 四个宿主里**真把 key 渲染成可见文案**的站点共 {n_render} 处")

    # ── 这 n_render 处渲染的对象里，有没有那 64 条候选 ──────────────
    print("\n" + "=" * 78)
    print("这 64 条候选里，有没有一条**真的**落在这类渲染面上")
    print("=" * 78)
    rows = []
    for nm in TARGETS:
        f = FE / "public/latent/data" / nm
        if not f.exists():
            print(f"[错误] 产物不存在 {f}")
            sys.exit(2)
        data = json.loads(f.read_text(encoding="utf-8"))
        acc = walk(data)
        n, n_str = len(acc), sum(1 for _p, v in acc if isinstance(v, str))
        excl = n >= 2000 and (n_str / n if n else 0) < 0.01
        names = {}
        for pth, _v in acc:
            fn = field_name(pth)
            if fn and fn not in names:
                names[fn] = pth
        owner_paths = [q for q, s2 in hs.items() if nm in s2]
        unrendered = [fn for fn in sorted(names)
                      if not any(name_pattern(fn).search(hs[q]) for q in owner_paths)]
        rows.append((nm, len(unrendered), unrendered, [q.name for q in owner_paths]))
        print(f"\n  {nm}：候选 {len(unrendered)} 条 / 宿主 {', '.join(q.name for q in owner_paths)}")

    # 逐个候选：它在产物里的路径落不落在「可能被通用渲染的对象」里
    # ⚠ 判定用**保守代理**：候选字段名的**父路径**里若出现
    #   by_direction / pa / verdict / selection 这几个被渲染对象的键，
    #   才算「可能被通用渲染解释」。其余一律算**解释不了**。
    RENDERED_OBJ_KEYS = {"by_direction", "pa", "verdict", "by_verdict"}
    total = sum(r[1] for r in rows)
    explained, not_explained = [], []
    for nm, n_unr, unr, owners in rows:
        f = FE / "public/latent/data" / nm
        data = json.loads(f.read_text(encoding="utf-8"))
        acc = walk(data)
        first = {}
        for pth, _v in acc:
            fn = field_name(pth)
            if fn and fn not in first:
                first[fn] = pth
        for fn in unr:
            pth = first[fn]
            segs = set(re.findall(r"[A-Za-z_$][\w$]*", pth))
            (explained if segs & RENDERED_OBJ_KEYS else not_explained).append((nm, fn, pth))

    print(f"\n[结论] 64 条候选里：")
    print(f"  能被「通用 key 渲染」解释的   {len(explained)} 条")
    print(f"  **解释不了**的                {len(not_explained)} 条")
    if explained:
        print("\n  可解释的（逐条）：")
        for nm, fn, pth in explained:
            print(f"    {nm:<22} {fn:<28} {pth[:70]}")
    print(f"\n⚠ 判定口径：候选的**父路径**里出现被渲染对象的键"
          f"（{', '.join(sorted(RENDERED_OBJ_KEYS))}）才算「可解释」。")
    print(f"  这是**保守代理**，不是证明 —— 它只说明「这条路通不通」，")
    print(f"  不说明「那条字段真的被渲染了」。")


if __name__ == "__main__":
    main()