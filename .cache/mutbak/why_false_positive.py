#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化 Phase-0 那 14 条判错的**成因结构**，以及判对那 99 条的同口径基线。

⚠ 为什么要量这个：如果 14 条判错可以被几条机械规则解释（裸数字当表达式、
  等号前面其实有个 sqrt/floor/逻辑函数、等号前面是条件句），
  那它们就不是「模型算错了」的证据，而是**抽取器的解析能力不足**。
  反过来，如果判对那 99 条里有大量同样的形态却没被判错，
  说明这些形态本身不决定判红判绿，得另找原因。

不判决，只数形态。
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
CLAIMS = os.path.join(ROOT, ".cache", "xcheck", "p0_claims.json")

FNS = ("sqrt", "floor", "log", "φ", "cbrt")


def is_bare_num(lhs: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", lhs))


def fn_before(text: str, start: int, w: int = 25):
    ctx = text[max(0, start - w):start]
    hit = [f for f in FNS if f in ctx]
    return hit


def sup_after(text: str, end: int) -> bool:
    """等号左边紧跟着平方/立方记号 —— 说明 lhs 少了指数。"""
    return end < len(text) and text[end:end + 1] in "²³^"


def cond_before(text: str, start: int, w: int = 20) -> bool:
    ctx = text[max(0, start - w):start].lower()
    return ("if " in ctx) or ("let " in ctx) or ("such that" in ctx) \
        or ("suppose" in ctx) or ("=" in ctx)


def main() -> int:
    d = json.load(open(CLAIMS, encoding="utf-8"))
    allc = [(r["trajectory_id"], c) for r in d["rows"] for c in r["claims"]]
    cache = {}

    def get(t):
        if t not in cache:
            cache[t] = json.load(
                open(os.path.join(NPZ_DIR, t + ".json"), encoding="utf-8")
            )["generated_text"]
        return cache[t]

    stats = {"wrong": {}, "ok": {}}
    for k in stats:
        stats[k] = dict(total=0, bare=0, fn=0, sup=0, cond=0, flagged=0)

    detail = []
    for t, c in allc:
        text = get(t)
        k = "ok" if c["ok"] else "wrong"
        s = stats[k]
        bare = is_bare_num(c["lhs"])
        fn = fn_before(text, c["start"])
        sup = sup_after(text, c["end"])
        cond = cond_before(text, c["start"])
        s["total"] += 1
        s["bare"] += bare
        s["fn"] += bool(fn)
        s["sup"] += sup
        s["cond"] += cond
        if not c["ok"]:
            detail.append((t, c["tok"], c["lhs"], bare, fn, sup, cond))

    print(f"claim 总数 {len(allc)}\n")
    hdr = f"{'形态':<22}{'判错 14':>10}{'判对 99':>10}"
    print(hdr)
    print("-" * len(hdr.encode('utf-8').decode('utf-8')))
    for label, key in [("lhs 是裸数字", "bare"),
                       ("等号前有 sqrt/floor/φ", "fn"),
                       ("lhs 后紧跟 ²/³/^", "sup"),
                       ("等号前是条件/设元句", "cond")]:
        w, o = stats["wrong"], stats["ok"]
        print(f"{label:<22}{w[key]:>6}/{w['total']:<4}{o[key]:>7}/{o['total']:<4}")

    print("\n=== 14 条判错逐条的形态 ===")
    for t, tok, lhs, bare, fn, sup, cond in detail:
        tags = []
        if bare:
            tags.append("裸数字")
        if fn:
            tags.append("前有" + "/".join(fn))
        if sup:
            tags.append("后有指数")
        if cond:
            tags.append("条件句")
        print(f"  tok{tok:<6d} lhs={lhs!r:<14} {' + '.join(tags) or '（以上都不是）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())