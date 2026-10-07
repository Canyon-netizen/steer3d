#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探索性扫描：**不是判据**，只用来归纳语义类别。

⚠ 这个脚本的输出**不进任何判决**。它存在的唯一目的是：在把词表**定死**
  之前，让我看清 1.7B 模型在这批 CoT 里动摇时到底会写哪几种话。
  看清之后写 `.cache/xcheck/HINGE_PREREG.md` 定死类别与阈值，
  之后规则一个字都不许改。

⚠ 因此这里刻意用**极宽**的关键词抓取（wait / hmm / maybe ...），
  再由人归纳类别，而不是先猜类别再去凑。
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")

# 极宽的探针词：只求召回，不求精
PROBES = [
    r"wait\b", r"\bhmm\b", r"\bactually\b", r"\bmaybe\b", r"\bbut wait\b",
    r"\blet me (?:re|check|verify|reconsider|recalculate|re-examine|recompute)\w*",
    r"\bhold on\b", r"\bconfus\w+", r"\bwrong\b", r"\bmistake\b",
    r"\bcorrect me\b", r"\bshould be\b", r"\bdoesn'?t (?:match|make sense)\b",
    r"\bi made\b", r"\blet me (?:try|double)\b", r"\bagain\b",
]
RX = re.compile("|".join(PROBES), re.IGNORECASE)


def sentences(text: str):
    for m in re.finditer(r"[^.!?\n]+[.!?]", text):
        yield m.start(), m.end(), m.group(0)


def main() -> int:
    files = sorted(glob.glob(os.path.join(NPZ_DIR, "*__think.json")))
    per_traj = Counter()
    print("=== 命中的整句（按探针分组，去重）===")
    buckets = {}
    for f in files:
        t = os.path.basename(f)[:-5]
        o = json.load(open(f, encoding="utf-8"))
        text = o["generated_text"]
        for s, e, sent in sentences(text):
            for p in PROBES:
                if re.search(p, sent, re.IGNORECASE):
                    key = re.sub(r"\s+", " ", sent.strip())[:110]
                    buckets.setdefault(key, []).append(t[5:9])
                    per_traj[t[5:9]] += 1
                    break
    for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        tag = ",".join(sorted(set(v))[:6])
        print(f"[{len(v):3d}] {tag:34s} {k}")
    print(f"\n共 {len(buckets)} 种不同句子")
    print(f"\n=== 每条轨迹的命中次数 ===")
    for tid, n in sorted(per_traj.items()):
        print(f"  {tid}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())