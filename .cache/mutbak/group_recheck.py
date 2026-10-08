#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""38 案例分组结果的复核：那个「其他」桶到底是什么。

## 触发

R-5 的 A 组（按标记词类型）跑出五组：

    Hmm +0.192   Let +1.062   Wait +0.142   maybe +0.247   **其他 +4.699**

「其他」= 该位置实际写的 token **不以** wait/let/hmm/mayb 开头，
共 8 个位置 / 7 条轨迹，Δ 是其余各组的 4 倍。

⚠ 而 R-5 判的是「各组是否**同号**」——五组确实全正，PASS。
   但「同号」这条判据**看不见权重失衡**：一个 21% 的大桶
   贡献了远超其余的幅度，却和它们一起被平均成一个 PASS。

⇒ 本脚本只做一件事：把那 8 个位置的 token 与 Δ 全部印出来，
   人工看它们**是不是真的算动摇标记词**。
   如果不是，R-5 的 PASS 就建立在一个装错东西的桶上。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, ".cache", "mutbak", "causal_rel44.json")
NOISE = 4.339e-05
K1, K0 = "w|rel+1.00", "w|rel+0.00"


def stem(txt):
    t = txt.strip().lower()
    for k, name in (("wait", "Wait"), ("let", "Let"), ("hmm", "Hmm"),
                    ("mayb", "maybe")):
        if t.startswith(k[:3]):
            return name
    return "其他"


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["rows"]
    print(f"案例 {len(rows)} 个，轨迹 {d.get('n_traj')}，"
          f"类间间距 {d['class_gap']:.1f}，噪声底 {NOISE:.2e}\n")

    by_traj = {}
    for r in rows:
        by_traj.setdefault(r["traj"], []).append(
            r["d"][K1]["mark"] - r["d"][K0]["mark"])

    print("=== 全部位置：token 与 Δmarker(α_rel=1) ===")
    print(f"  {'分组':>6s}  {'Δ':>9s}  token（逐个）")
    for r in rows:
        s = stem(r["marker_text"])
        dl = r["d"][K1]["mark"] - r["d"][K0]["mark"]
        flag = "  ← 其他" if s == "其他" else ""
        print(f"  {s:>6s}  {dl:+9.4f}  {r['marker_text']!r:14s} "
              f"{r['traj'][:34]:34s} t={r['t']}{flag}")

    print("\n=== 「其他」桶的 8 个位置单独看 ===")
    oth = [r for r in rows if stem(r["marker_text"]) == "其他"]
    print(f"  位置 {len(oth)} 个 / 轨迹 {len(set(r['traj'] for r in oth))} 条")
    in_marker = sum(1 for r in oth if r["marker_id"] in d["marker_ids"])
    print(f"  其中 token 落在 **marker 集合（7 个 id）** 里的：{in_marker}/{len(oth)}")
    print(f"  它们的 Δmarker 平均：{sum(r['d'][K1]['mark'] - r['d'][K0]['mark'] for r in oth) / len(oth):+.4f}")

    print("\n=== 剔除「其他」桶后，R-5 还成立吗 ===")
    keep = [r for r in rows if stem(r["marker_text"]) != "其他"]
    groups = {}
    for r in keep:
        groups.setdefault(stem(r["marker_text"]), []).append(
            r["d"][K1]["mark"] - r["d"][K0]["mark"])
    means = {}
    for g, v in sorted(groups.items()):
        # 按轨迹聚合
        byt = {}
        for r in keep:
            if stem(r["marker_text"]) == g:
                byt.setdefault(r["traj"], []).append(
                    r["d"][K1]["mark"] - r["d"][K0]["mark"])
        means[g] = float(sum(sum(x) / len(x) for x in byt.values()) / len(byt))
        print(f"    {g:6s} 轨迹 {len(byt):2d} 条 / 位置 {len(v):2d} 个  "
              f"Δ {means[g]:+.4f}")
    allpos = [x for x in means.values() if abs(x) > NOISE]
    print(f"\n  剔除后仍全同号：{'是 ✅' if (allpos and (all(v > 0 for v in allpos) or all(v < 0 for v in allpos))) else '否 ❌'}")
    print(f"  ⚠ 但「其他」桶占 {len(oth)}/{len(rows)} = "
          f"{len(oth) / len(rows):.0%} 的位置，剔除它等于改样本。")
    print(f"    原 R-5 的 PASS 是**连它一起**的同号判断，两条都要留档。")


if __name__ == "__main__":
    raise SystemExit(main())