#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探索 3（仍不是判据）：上一版「回头占比 95.8%」很可能是**度量自带的**。

质疑：上一版量的不是「模型回头改自己」，而是「标记后面 220 字符里有多少
**词**在前文出现过」。但 `Let me check.` 这类标记**结构上就紧跟在刚写完的
一段后面**——模型刚写完第 k 句，说 `Let me check`，然后复述第 k 句——
复述前文几乎是**必然**的，95.8% 里可能没有任何信息。

空转检验（两个）：
  A. **随机对照**：在**任意**位置（比如随机位置的同长度窗口）量同样的
     「回头率」。如果随机位置也给 95%，那这个量压根不测任何东西。
  B. **标记位置 vs 非标记位置**：如果「回头」在标记处并不比别处高，
     那标记本身没带来任何信息。

只有标记处的回头率**显著高于**随机位置，这个量才有资格当判据。
"""
from __future__ import annotations

import glob
import json
import os
import random
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")

MARK = re.compile(
    r"(Wait,\s*no\.?|Let me check again\.|Let me think again\.|Wait, let me check|"
    r"But let me check again\.|Hmm\.|Let me check\.|But let me think again\.|"
    r"Wait, maybe I misread|maybe I miscalculated|But maybe I made a mistake|"
    r"I made a mistake|let me verify|Let me re-examine|reconsider)",
    re.IGNORECASE)
WORD = re.compile(r"[A-Za-z]{3,}")
random.seed(20261007)


def back_ratio(text: str, pos: int, span: int = 220) -> float:
    before = set(w.lower() for w in WORD.findall(text[:pos]))
    after = set(w.lower() for w in WORD.findall(text[pos:pos + span]))
    if not after:
        return -1.0
    return len(before & after) / len(after)


def main() -> int:
    files = sorted(glob.glob(os.path.join(NPZ_DIR, "*__think.json")))
    at_mark, at_rand = [], []
    for f in files:
        o = json.load(open(f, encoding="utf-8"))
        text = o["generated_text"]
        for m in MARK.finditer(text):
            r = back_ratio(text, m.end())
            if r >= 0:
                at_mark.append(r)
        # 随机对照：同一条轨迹里随机取位置
        for _ in range(len(MARK.findall(text)) or 5):
            p = random.randrange(0, max(1, len(text) - 300))
            r = back_ratio(text, p)
            if r >= 0:
                at_rand.append(r)

    def stat(v, name):
        v = sorted(v)
        n = len(v)
        mean = sum(v) / n
        med = v[n // 2]
        return f"{name}: n={n} 均值={mean*100:.1f}% 中位={med*100:.1f}%"

    print("=== 回头率：标记处 vs 随机处 ===")
    print("  " + stat(at_mark, "标记处"))
    print("  " + stat(at_rand, "随机处"))
    diff = (sum(at_mark) / len(at_mark) - sum(at_rand) / len(at_rand)) * 100
    print(f"\n  差值 = {diff:+.1f} 个百分点")
    if diff < 3:
        print("\n⚠ 差值很小 ⇒ 「回头」这个量**不区分**标记处与随机处。")
        print("  上一版那个 95.8% 是度量自带的（标记结构上紧跟刚写完的内容），")
        print("  **不能**当判据用。")
    else:
        print("\n✓ 差值明显 ⇒ 标记处确实比别处更常回头，可以进一步写判据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())