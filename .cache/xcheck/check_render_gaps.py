#!/usr/bin/env python3
"""修订 74 §74.1 的 W8：把 C 类按块分组，每组配一个**独立于 AST 仪器**的 grep 事实。

⚠⚠ 为什么必须有一台独立的仪器：§73 那台是 AST（解析别名、循环、回调作用域），
   它「测不到」的那 794 条里，可能混着**真的从没被触达**的块。
   只用 AST 一个来源，我无法区分「仪器瞎了」与「代码真的没写」。
   ⇒ 本脚本的块名出现次数用**朴素 grep 计数**，与 AST **互不引用**。

⚠ W8d：报了分组**不等于**这些字段「该上屏」。该上屏与否是设计问题，要人定。
⚠ 本脚本不对任何一组给出「应当渲染」的建议。

用法：python3 .cache/xcheck/check_render_gaps.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PANEL = {
    "bpath_marker_steering.json": "frontend/components/BPathPanel.tsx",
    "heldout_readability.json": "frontend/components/HeldoutPanel.tsx",
    "evidence_ladder.json": "frontend/components/EvidenceLadderPanel.tsx",
}


def load_tiers():
    spec = importlib.util.spec_from_file_location(
        "tiers", HERE / "check_render_tiers.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def grep_count(src: str, name: str) -> int:
    """⚠ **朴素**计数：逐行统计 `name` 作为独立词出现的行数。

    这里刻意**不用**任何解析 —— 它的价值就在于「笨」：
    一台笨仪器与一台聪明仪器互相印证，才谈得上交叉核对。
    """
    pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
    return sum(1 for line in src.splitlines() if pat.search(line))


def block_of(path: str) -> str:
    """顶层块名，**必须剥掉下标**。

    ⚠⚠ 第一版直接用 `path.split(".")[0]`，于是 `built_from[0]` … `built_from[9]`
      各自成组，`answerable[0]` 也成组。
      更糟的是拿 `answerable[0]` 这个**字面串**去 grep 宿主源码 ——
      源码写的是 `d.answerable.map(…)`，**永远搜不到 `answerable[0]`**
      ⇒ 它被报成「⚑ 可证未触达」，而 AST 仪器明明白白列着 `d/answerable` 这个
      循环站点。
      ⇒ 假欠账比漏报危险得多。块名一律剥下标后再 grep。
    """
    top = path.split(".")[0]
    return re.sub(r"\[\d+\]$", "", top)


def main() -> int:
    print("=== 修订 74 W8：C 类按块分组 + 独立 grep 事实 ===\n")
    tiers = load_tiers()
    rows = tiers.classify()
    crows = [r for r in rows if r["tier"] == "C"]

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in crows:
        groups[(r["artifact"], block_of(r["path"]))].append(r)

    srcs = {k: (ROOT / v).read_text(encoding="utf-8") for k, v in PANEL.items()}

    # ⚠⚠ W8f 要**双向**核对，不只是「grep 说有、AST 说无」那一个方向。
    #   反方向同样要抓：grep 报 0 行、而 AST 那边有该块的访问/循环 ⇒
    #   **grep 的检索词错了**（第一版就栽在这：拿 `answerable[0]` 去搜源码）。
    #   假欠账比漏报危险得多。
    ast = tiers.run_instrument()["panels"]
    ast_blocks: dict[str, set[str]] = {}
    for pname, blob in ast.items():
        names: set[str] = set()
        for _r, b in blob.items():
            for key in ("accesses", "loops"):
                for a in b[key]:
                    segs = a.split("/")
                    if segs[0] in ("d", "j", "x"):
                        segs = segs[1:]
                    if segs:
                        names.add(segs[0])
        ast_blocks[pname] = names

    print(f"C 弱覆盖共 {len(crows)} 条，分成 {len(groups)} 个 (产物, 顶层块) 组。\n")
    print("W8a 分组　　　　　　　条数　占C　W8b grep 行数  W8f AST 侧  判定")
    print("─" * 84)

    provable: list[tuple[str, str, int]] = []
    inconclusive: list[tuple[str, str, int]] = []
    type_decl: list[tuple[str, str, int]] = []
    conflict: list[str] = []
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    for (art, top), items in ordered:
        n = len(items)
        g = grep_count(srcs[art], top)
        in_ast = top in ast_blocks.get(Path(PANEL[art]).name, set())
        if g == 0 and in_ast:
            # ⚠ 两台仪器打架 ⇒ 只能报冲突，不能报「可证」
            tag = "⚠⚠ 冲突：grep 0 行但 AST 有该块 ⇒ 检索词有问题，**不下结论**"
            conflict.append(f"{art} / {top}: grep={g} 行，AST 有该块，{n} 条")
        elif g == 0:
            provable.append((art, top, n))
            tag = "⚑ 可证未触达（grep 0 行且 AST 无该块）"
        elif not in_ast:
            # ⚠ grep 命中了，AST 却说这个块**没被取值过** ——
            #   那 1 行几乎总在**类型声明**里（`suites` 就是这么被误判的）
            #   或是个偶然同名的普通词（`what` / `schema`）。
            type_decl.append((art, top, n))
            tag = "⚠⚠ grep 命中但 AST 无取值 ⇒ 几乎全在**类型声明**里"
        else:
            inconclusive.append((art, top, n))
            tag = "✓ 块确被取值过，只是这批字段没用到"
        print(f"{art[:22]:<22} {top:<20} {n:>4} {100*n/len(crows):5.1f}%   "
              f"{g:>5} 行   {'有' if in_ast else '无':^4}    {tag}")

    tot_p = sum(n for _, _, n in provable)
    tot_i = sum(n for _, _, n in inconclusive)
    tot_t = sum(n for _, _, n in type_decl)
    print("\n" + "=" * 84)
    print(f"W8c **可证未触达**（grep 0 行 **且** AST 无该块）："
          f"{len(provable)} 组 / {tot_p} 条 = C 的 {100*tot_p/len(crows):.1f}%")
    print("   这批是**可证的欠账**：不是仪器看不见，是源码里真的没有这个名字。")
    print(f"\n 块确被取值过、只是这批字段没用到：{len(inconclusive)} 组 / {tot_i} 条 "
          f"= C 的 {100*tot_i/len(crows):.1f}%")
    print(f"\n ⚠ grep 命中但 AST 判**无取值**（几乎全在类型声明里）："
          f"{len(type_decl)} 组 / {tot_t} 条 = C 的 {100*tot_t/len(crows):.1f}%")
    for art, top, n in type_decl:
        print(f"     · {art} / {top}（{n} 条）")
    if conflict:
        print(f"\n⚠⚠ **两台仪器冲突 {len(conflict)} 组，本组不下结论**：")
        for c in conflict:
            print(f"   · {c}")

    print("\n⚠⚠ W8d：以上分组**不是**「该上屏」的判断。")
    print("   「哪些该上屏」是设计问题，需要人定 —— 本脚本不提出建议。")
    print("\n⚠ W8e：C 不许塞进 Y2 台账或豁免表。")
    print("   但 W8c 那一批（grep 0 行）性质不同，是**可证的**，")
    print("   允许单独进入一张明确标注「可证未触达」的清单，与 unclassified 分开。")
    return 0


if __name__ == "__main__":
    sys.exit(main())