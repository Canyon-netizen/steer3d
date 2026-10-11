#!/usr/bin/env python3
"""修订 73 §73.1 的 W7：用 TypeScript AST 仪器给渲染覆盖分三级。

⚠⚠ 本脚本**不判红未渲染**，它只把 Y1 判为「已覆盖」的叶子分三级并全部报出。
   C 级的含义是「**本仪器测不到**」，**不是**「没渲染」——
   仪器不认识跨文件 import 的辅助渲染函数、运行时拼路径、
   把整个对象作为单个 prop 丢给子组件（见预登记 §73.1 W7c）。

⚠ 仪器：`ts_access_paths.js`（TypeScript 5.5.3 AST），自带 5 条已知答案
   作为阳性对照；任一条不成立 ⇒ 仪器不可信 ⇒ **本脚本不发数**。

用法：python3 .cache/xcheck/check_render_tiers.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INSTRUMENT = HERE / "ts_access_paths.js"
Y1 = HERE / "check_render_coverage.py"

PAIRS = [
    ("frontend/public/latent/data/bpath_marker_steering.json",
     "frontend/components/BPathPanel.tsx"),
    ("frontend/public/latent/data/heldout_readability.json",
     "frontend/components/HeldoutPanel.tsx"),
    ("frontend/public/latent/data/evidence_ladder.json",
     "frontend/components/EvidenceLadderPanel.tsx"),
]

DIGIT = re.compile(r"^\d+$")


def load_y1():
    spec = importlib.util.spec_from_file_location("y1", Y1)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def norm(path: str) -> tuple[str, ...]:
    """`a.rows[0].c` → ('a','rows','*','c')；`a.per_id.7196.c` → ('a','per_id','*','c')。

    ⚠⚠ 带下标的段必须**同时**吐出容器名**和**一个 `*`。
      第一版只把 `[0]` 删掉留下 `rows`，于是产物侧得到 `('…','rows','level')`，
      而面板侧的循环访问是 `('…','rows','*','level')` ⇒ **永远对不上**。
      B 级因此只得了 15 条（明显偏小），是 C 样本把它暴露出来的。
    """
    out = []
    for seg in path.split("."):
        if seg.startswith("["):
            out.append("*")
            continue
        m = re.search(r"\[\d+\]$", seg)
        name = seg[: m.start()] if m else seg
        if not name:
            continue
        if DIGIT.match(name):
            out.append("*")
        else:
            out.append(name)
            if m:
                out.append("*")
    return tuple(out)


def run_instrument():
    p = subprocess.run(["node", str(INSTRUMENT)], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"⚠⚠ 仪器自检未通过 ⇒ 不发数\n{p.stderr.strip()}")
    return json.loads(p.stdout)


def classify() -> list[dict]:
    """跑仪器 + Y1，把**每个被 Y1 判为「已覆盖」**的叶子分级。

    返回 [{artifact, panel, path, name, tier}]，tier ∈ {'A','B','C'}。
    仪器自检不通过时直接 SystemExit —— 不发数。
    """
    data = run_instrument()
    known = data["known_answers"]
    if sum(1 for k in known if k["ok"]) != len(known):
        raise SystemExit("仪器自检未通过 ⇒ 不发任何分级数字")

    y1 = load_y1()
    panels = data["panels"]
    rows: list[dict] = []
    for art_rel, panel_rel in PAIRS:
        art = json.loads((ROOT / art_rel).read_text(encoding="utf-8"))
        src = (ROOT / panel_rel).read_text(encoding="utf-8")
        pname = Path(panel_rel).name
        info = panels.get(pname, {})
        acc_all: set[tuple[str, ...]] = set()
        loop_all: set[tuple[str, ...]] = set()
        for _root, blob in info.items():
            for a in blob["accesses"]:
                segs = a.split("/")
                if segs[0] in ("d", "j", "x"):
                    segs = segs[1:]
                acc_all.add(tuple(s for s in segs if s))
            for l in blob["loops"]:
                segs = l.split("/")
                if segs[0] in ("d", "j", "x"):
                    segs = segs[1:]
                loop_all.add(tuple(s for s in segs if s))

        for lpath, lname, val in y1.leaves(art):
            if not y1.name_pattern(lname).search(src):
                continue                       # Y1 已判「未渲染」，不在本分级范围
            segs = norm(lpath)
            if segs in acc_all:
                hit = next((l for l in loop_all
                            if len(l) < len(segs) and segs[:len(l)] == l), None)
                tier = "B" if hit is not None else "A"
            else:
                tier = "C"
            rows.append({"artifact": Path(art_rel).name, "panel": pname,
                         "path": lpath, "name": lname, "tier": tier})
    return rows


def main() -> int:
    print("=== 修订 73 W7：渲染覆盖三级判定（AST 仪器，非正则）===\n")
    rows = classify()
    tot = len(rows)
    cnt = {t: sum(1 for r in rows if r["tier"] == t) for t in "ABC"}
    A, B, C = cnt["A"], cnt["B"], cnt["C"]

    data = run_instrument()
    for k in data["known_answers"]:
        c = k["check"]
        what = c.get("must_access") or c.get("must_NOT_access") or c.get("must_loop")
        print(f"   [{'ok' if k['ok'] else '✗'}] {what}   （{c['why']}）")

    print(f"\nY1 判为「已覆盖」的叶子：{tot}")
    print(f"  A 强（完整路径逐字出现）      {A:5d}  {100*A/tot:5.1f}%")
    print(f"  B 循环（祖先容器被迭代）      {B:5d}  {100*B/tot:5.1f}%")
    print(f"  C 弱（只有字段名命中）        {C:5d}  {100*C/tot:5.1f}%")

    print("\n⚠⚠ C 的口径：C = 「**本仪器测不到**」，**不是**「没渲染」。")
    print("   仪器不认识：跨文件 import 的辅助渲染函数、运行时拼路径、")
    print("   把整个对象作为单个 prop 丢给子组件。")
    print("   「`{...spread}` 0 处 / 数据对象解构 0 处」是**本次实测**，不是保证。")

    print("\nB 样本（前 6 条）:")
    for r in [r for r in rows if r["tier"] == "B"][:6]:
        print(f"   · {r['artifact']}: {r['path']}")

    # ⚠⚠ W7f：别名展开**只可能**让 A 变大。
    #   若 A 小于「不做别名展开时父形态逐字命中」的数，说明这台仪器
    #   比一次朴素字符串搜索还弱 ⇒ 判红。
    #   ⚠ 抽 classify() 时第一版把这一段弄丢了 —— 那是**已提交的判据**，
    #   静默删掉它就等于让判据自己变弱。补回来。
    y1 = load_y1()
    raw_parent_hit = 0
    for art_rel, panel_rel in PAIRS:
        art = json.loads((ROOT / art_rel).read_text(encoding="utf-8"))
        src = (ROOT / panel_rel).read_text(encoding="utf-8")
        for lpath, lname, _v in y1.leaves(art):
            if not y1.name_pattern(lname).search(src):
                continue
            pseg = lpath.rsplit(".", 2)
            praw = ".".join(pseg[-2:]) if len(pseg) >= 2 else lpath
            if y1.name_pattern(praw).search(src):
                raw_parent_hit += 1
    ok_f = A >= raw_parent_hit
    print(f"\nW7f 一致性方向检查：A({A}) {'≥' if ok_f else '<'} "
          f"朴素父形态命中({raw_parent_hit})"
          f"　{'✓ 别名展开只可能让 A 变大' if ok_f else '✗ 仪器比朴素字符串搜索还弱'}")
    return 0 if ok_f else 1


if __name__ == "__main__":
    sys.exit(main())