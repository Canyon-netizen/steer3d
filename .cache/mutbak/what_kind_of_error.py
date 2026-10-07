#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查一件事：这 24 条轨迹的错误**到底是什么类型的错误**。

背景：Phase-0 用「算式两边对不上」找错，找到 14 条，逐条人工读后发现
**14/14 全是抽取器假阳性**（audit_14_wrong.py）。于是问题变成：
这些轨迹里**有没有**真能定位的算术错？

本脚本不判决，只把「最终答案错」但「抽取器零判错」的轨迹的收尾部分
原样摊开，让人看清错在哪一步。是算错了，还是推理方向错了、读错题了、
还是根本没写完。

输出分两类：
  A 类：有判错（哪怕是假阳性）—— 已被 audit 覆盖
  B 类：零判错但答案错 —— **从未被任何自动判据看过**
"""
from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
CLAIMS = os.path.join(ROOT, ".cache", "xcheck", "p0_claims.json")


def main() -> int:
    d = json.load(open(CLAIMS, encoding="utf-8"))
    nwrong = {}
    nclaim = {}
    for r in d["rows"]:
        nclaim[r["trajectory_id"]] = len(r["claims"])
        nwrong[r["trajectory_id"]] = sum(1 for c in r["claims"] if not c["ok"])

    files = sorted(glob.glob(os.path.join(NPZ_DIR, "*__think.json")))
    bclass = []
    for f in files:
        t = os.path.basename(f)[:-5]
        o = json.load(open(f, encoding="utf-8"))
        if o["is_correct"]:
            continue
        if nwrong.get(t, 0) == 0:
            bclass.append((t, o))

    print(f"最终答案错的轨迹共 {sum(1 for f in files if not json.load(open(f, encoding='utf-8'))['is_correct'])} 条")
    print(f"其中抽取器**零判错**的：{len(bclass)} 条 —— 这些错误从未被任何自动判据看过\n")
    for t, o in bclass:
        text = o["generated_text"]
        tail = text[-420:].replace("\n", " ⏎ ")
        print(f"=== {t[5:9]}  答案 {o['generated_answer']} / 真值 {o['ground_truth']}"
              f"  claims={nclaim.get(t, 0)} ===")
        print(f"    收尾 …{tail}…\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())