#!/usr/bin/env python3
"""修订 80 §80.4 的 **J1**：同名 Record 表的 key 集合差异 —— **只披露，不判红**。

⚠⚠⚠ 为什么**不是**判红判据（§80.3）：
   取数时发现唯一一对 key 集合不同的 `per_token`（后者多一个 token `80022`），
   在 `BPathPanel.tsx:963-968` 里**不是两张独立表并排**，而是
   **遍历两批 key 的并集**、渲染成一张表两列、缺失侧印 `—`；
   源码 960-962 行的注释还写明「高对齐独有的 80022 原本不渲染」。
   ⇒ **作者早就处理过这个差异**。
   ⚠ 若只看产物数据就判红，会把这段比我设想更好的代码判成**假红** ——
   **假欠账比漏报危险得多。**

⚠⚠⚠ **「是否造成错位取决于渲染方式，而渲染方式不在产物里」**
   （「一张表两列·并集遍历」安全；「两张独立并排的表」才危险）。
   ⇒ 本脚本只负责把差异**摆出来**，判定留给下一条判据（需 AST 级分析）。

⚠⚠⚠ **本脚本自己可能静默失效** ⇒ 两条阳性对照（§80.5）：
   对照 1 同集合 ⇒ 报 0；对照 2 **不同集合 ⇒ 报 1**。
   ⚠ 对照 2 是**唯一**能让「0 对」这个输出有意义的手段 ——
   没有它，「0 对」与「本脚本坏了」在输出上完全一样。

用法：python3 .cache/xcheck/check_record_key_sets.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "frontend/public/latent/data"
CTL = ROOT / ".cache/mutbak/j1ctl"          # ⚠ 对照用的临时产物目录


def is_canonical_numeric(key) -> bool:
    """ECMAScript 的 canonical numeric string：正整数字符串（无前导零、< 2^32-1）。

    ⚠ 只有**这一类** key 会被 `Object.entries` 提前并按数值升序重排；
      其余 key 保持插入顺序。⇒ 这是「JSON 顺序 ≠ 实页顺序」的**精确**触发条件。
    ⚠ §78.4 当初写的是「非数字的 id」，方向反了（承修订 80 §80.1）。
    """
    s = str(key)
    if not (s == "0" or (s and s[0] != "0" and s.isdigit())):
        return False
    return int(s) < 2**32 - 1


def collect(obj, prefix: str, tables: dict[str, list]) -> tuple[int, int]:
    """收所有 dict-of-dict（Record）表：末段名 → [(路径, key 集合)]。

    返回 (表总数, 会被重排的 key 总数)。
    """
    n_tables = 0
    n_canon = 0

    def rec(o: object, p: str) -> None:
        nonlocal n_tables, n_canon
        if isinstance(o, dict):
            if o and all(isinstance(v, dict) for v in o.values()):
                keys = [str(k) for k in o.keys()]
                tables[p.split(".")[-1]].append((p, frozenset(keys)))
                n_tables += 1
                n_canon += sum(1 for k in keys if is_canonical_numeric(k))
            for k, v in o.items():
                rec(v, f"{p}.{k}" if p else k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                rec(v, f"{p}[{i}]")

    rec(obj, prefix)
    return n_tables, n_canon


def scan_dir(data_dir: Path, label: str) -> dict:
    # ⚠⚠⚠⚠ **配对必须限定在「同一个产物文件」内。**
    #   第一版把 tables 跨文件累加，于是 `per_layer`（在 axis_readouts.json 里
    #   是「层号 → 该层的多个单元格」）与 `per_layer`
    #   （在 vector_random_control.json 里是另一个意思）被配成一对，
    #   `cells` 与 `cells`、`gates` 与 `gates` 同理
    #   ⇒ **9 对全是假的**（实测 12 对里至少 9 对属此类）。
    #   ⚠⚠ 「假欠账比漏报危险得多」：读者会去逐个核实这 9 处「缺陷」，
    #   而它们根本不存在。
    #   ⚠ 这条范围限定是**判据措辞的更正**（§80.4 第 2 条原文没写「同一产物内」，
    #   而 §80.2 的形态侦察其实已经限定了）—— 已在预登记 §80.7 披露。
    per_file_tables: dict[str, dict[str, list]] = {}
    n_tables = n_canon = 0
    for f in sorted(data_dir.glob("*.json")):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:                      # ⚠ 崩溃必须与「没数据」可区分
            print(f"⚠⚠ 读不了 {f.name}：{e} ⇒ **这是没读成，不是「没有」**")
            raise SystemExit(2)
        t: dict[str, list] = defaultdict(list)
        ft, fc = collect(obj, "", t)
        n_tables += ft
        n_canon += fc
        per_file_tables[f.name] = t

    n_pairs = same = 0
    diffs = []
    for fname, tables in per_file_tables.items():
        for name, items in sorted(tables.items()):
            if len(items) < 2:
                continue
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    n_pairs += 1
                    a, b = items[i], items[j]
                    if a[1] == b[1]:
                        same += 1
                    else:
                        diffs.append((f"{fname} `{name}`", a[0], b[0],
                                      sorted(a[1] - b[1]), sorted(b[1] - a[1])))

    return {"label": label, "n_files": len(per_file_tables), "n_tables": n_tables,
            "n_canon": n_canon, "n_pairs": n_pairs, "n_same": same,
            "diffs": diffs, "per_file": None}


def selfcheck() -> int:
    """§80.5 的两条阳性对照。⚠ 对照崩了要报「对照没跑」，不是「对照失败」。"""
    print("=== 阳性对照 ===\n")
    if CTL.exists():
        shutil.rmtree(CTL)
    CTL.mkdir(parents=True)

    cases = [
        ("c1", {"a": {"per_id": {"1": {"x": 1}, "2": {"x": 2}}},
                "b": {"per_id": {"2": {"x": 2}, "1": {"x": 1}}}}, 0,
         "同名且 key 集合相同 ⇒ 报 0 对"),
        ("c2", {"a": {"per_id": {"1": {"x": 1}, "2": {"x": 2}}},
                "b": {"per_id": {"2": {"x": 2}, "3": {"x": 3}}}}, 1,
         "⚠ 同名但 key 集合不同 ⇒ 报 **1** 对（证明它能报非零）"),
    ]

    n_ok = 0
    for tag, payload, expect, why in cases:
        # ⚠⚠⚠ **每条对照必须用自己独立的目录。**
        #   第一版两条对照共用一个目录 ⇒ `c1` 的两张 `per_id` 表与 `c2` 的两张
        #   **混在一起**配对，对照 2 实得 3（而不是 1）、配对数 9（而不是 1）。
        #   ⇒ **对照互相污染**，而它自己完全没报错。
        one = CTL / tag
        if one.exists():
            shutil.rmtree(one)
        one.mkdir(parents=True)
        try:
            (one / "case.json").write_text(json.dumps(payload, ensure_ascii=False),
                                           encoding="utf-8")
            r = scan_dir(one, tag)
            got = len(r["diffs"])
        except Exception as e:
            print(f"  ⚠ 对照 {tag} **没跑**（不是「对照失败」）：{e}")
            continue
        ok = (got == expect)
        n_ok += ok
        print(f"  {'✓' if ok else '✗'} 对照 {tag}: 期望 {expect} 实得 {got}"
              f"（配对 {r['n_pairs']}）  —— {why}")

    print(f"\n对照 {n_ok}/{len(cases)}")
    if n_ok != len(cases):
        print("⚠⚠ 对照没过 ⇒ 本脚本不可信，**不发数**")
        return 1
    return 0


def main() -> int:
    if "--selfcheck" in sys.argv:
        return selfcheck()

    print("=== 修订 80 J1：同名 Record 表的 key 集合差异（**披露，不判红**）===\n")
    r = scan_dir(DATA, "frontend/public/latent/data")

    print(f"J1a 扫了 {r['n_files']} 个产物、{r['n_tables']} 张 dict-of-dict 表")
    print(f"J1b 其中 key 为 canonical numeric string（**会被 JS 重排**）："
          f"{r['n_canon']} 个")
    print(f"      ⚠ 重排的**精确**触发条件是「正整数字符串」，不是「非数字」"
          f"（更正 §78.4，承 §80.1）")
    print(f"J1c 末段同名的配对数：{r['n_pairs']}（集合相同 {r['n_same']}）")
    print(f"J1d ⚠ **集合不同**的对：{len(r['diffs'])}\n")

    if r["n_pairs"] == 0:
        print("❌ 配对数为 0 ⇒ **空扫描**，判红（防「没扫到却报漂亮的 0」）")
        return 1

    if not r["diffs"]:
        print("  （当前没有任何同名 Record 表的 key 集合不同）")
    for name, a, b, only_a, only_b in r["diffs"]:
        print(f"  ⚠ `{name}`")
        print(f"      {a}")
        print(f"      {b}")
        print(f"      仅前者有：{only_a[:6]}")
        print(f"      仅后者有：{only_b[:6]}")

    print()
    print("⚠⚠⚠ **以上不是缺陷清单**，是「**待核实的候选**：")
    print("   是否真的错位，取决于**渲染方式** ——")
    print("     ·「一张表两列·并集遍历」⇒ **安全**（行由并集决定，两列同 key）")
    print("     ·「两张独立并排的表」⇒ **危险**（各按自己的集合排）")
    print("   而**渲染方式不在产物里** ⇒ 本脚本判不了，也不该判。")
    print()
    print(f"✅ 披露完成（不判红）。配对数 {r['n_pairs']} ≥ 1 ⇒ 不是空扫描。")
    return 0


if __name__ == "__main__":
    sys.exit(main())