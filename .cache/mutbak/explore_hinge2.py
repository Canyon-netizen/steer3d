#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探索 2（仍不是判据）：「动摇标记」到底对不对应**错误**。

上一步的探索说明模型在这批 CoT 里会写 `Wait, no.` / `let me check again`
这类话，而且很多。但**说得多不等于用得上**。判据必须是「模型在**这里**
动摇了」，所以必须先验一件事：

  这些标记出现的时刻，模型是不是真的在改主意？

用**可证的外部信号**代替人工判断：把标记按轨迹分成「出现过」和
「没出现过」，看它们跟最终答案对错（`is_correct`）有没有关系。
但这只能验到轨迹级，验不到位置级。

位置级的真信号是**回头引用的比例**：模型说 `Wait, no.` 之后，
下一句是不是在**复述/纠正前文**（即引用前文出现过的 token），
还是**往前推进**（引入新内容）。前者是「改主意」，后者是「补充」。

⚠ 这仍是探索。它只回答「这条路值不值得写判据」，不下判决。
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")

# 先粗切一类，看看够不够用
MARK = re.compile(
    r"(Wait,\s*no\.?|Let me check again\.|Let me think again\.|Wait, let me check|"
    r"But let me check again\.|Hmm\.|Let me check\.|But let me think again\.|"
    r"Wait, maybe I misread|maybe I miscalculated|But maybe I made a mistake|"
    r"I made a mistake|let me verify|Let me re-examine|reconsider)",
    re.IGNORECASE)

WORD = re.compile(r"[A-Za-z]{3,}")


def main() -> int:
    files = sorted(glob.glob(os.path.join(NPZ_DIR, "*__think.json")))
    has = []
    back = 0
    fwd = 0
    rows = []
    for f in files:
        t = os.path.basename(f)[:-5]
        o = json.load(open(f, encoding="utf-8"))
        text = o["generated_text"]
        hits = list(MARK.finditer(text))
        has.append(bool(hits))
        nb = nf = 0
        for m in hits:
            # 标记后 200 字符里的词，有多少在前文出现过
            before = set(w.lower() for w in WORD.findall(text[:m.start()]))
            after = set(w.lower() for w in WORD.findall(text[m.end():m.end() + 220]))
            if not after:
                continue
            ov = len(before & after) / len(after)
            if ov >= 0.5:
                nb += 1
            else:
                nf += 1
        back += nb
        fwd += nf
        rows.append((t[5:9], o["is_correct"], len(hits), nb, nf))
        print(f"{t[5:9]}  correct={str(o['is_correct']):5s} 标记={len(hits):3d}  "
              f"回头={nb:3d} 往前={nf:3d}")

    nc_has = sum(1 for _, c, h, _, _ in rows if c and h)
    nc_non = sum(1 for _, c, h, _, _ in rows if c and not h)
    nw_has = sum(1 for _, c, h, _, _ in rows if not c and h)
    nw_non = sum(1 for _, c, h, _, _ in rows if not c and not h)
    print(f"\n=== 轨迹级：标记 × 最终答案对错 ===")
    print(f"  答案对：有标记 {nc_has}  无标记 {nc_non}")
    print(f"  答案错：有标记 {nw_has}  无标记 {nw_non}")
    tot_b, tot_f = back, fwd
    print(f"\n=== 位置级：标记后的词有多少在前文出现过 ===")
    print(f"  回头（改主意）{tot_b}   往前（补充新内容）{tot_f}   "
          f"回头占比 {tot_b/(tot_b+tot_f)*100:.1f}%")
    print("\n⚠ 「回头占比高」只说明模型在复述前文，**不能**单独证明它在改主意。")
    print("  复述也可能只是重新推导。要下判决需要另一个独立信号。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())