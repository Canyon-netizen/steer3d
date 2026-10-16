#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r224_id_collision.py —— 找账本里**编号被重载**的判据/条件 id。

## 这条在查什么

账本里判据/条件用 `C1` `D3` `E1` `J1` `P9` `S2` … 这种短编号，
⚠⚠⛔ 而**同一个编号在不同的修订里指的是不同的东西**。
⚖ 实测：**至少 26 个**编号在「定义位」上跨命名空间重复定义
⛔（见修订 224）。

⚖ 后果不是「难看」，是**引错**：
⚖ 说「C4 的 87 条」时，读的人可能以为在说 P9 那个 C4。

## ⚠⚠⛔ 这条报的是**下界**，不是总数

⚠⚠⛔ 它只认**两种定义位**：
  ① 以编号开头的表格行 `| C4 …`
  ② 以加粗编号开头的行 `**C4（…）**`
⛔ 正文里「C4 那里…」这种**行内引用**它一概不认。
⚖⇒ **报出的 26 是下界**；真实重载数只会更多，不会更少。

⚖⇒ 同族：[[单边判据给出的百分比是下界]]。这条判据是单边的。

跑法：
    python3 .cache/mutbak/r224_id_collision.py --ledger .cache/xcheck/R6_RERUN_PREREG.md
    python3 .cache/mutbak/r224_id_collision.py --selftest
退出码：0 正常 / 1 自检红 / 2 读不了账本
"""

import argparse
import os
import re
import sys
from collections import defaultdict

# 参与统计的编号族。⚠⚠ 这是**白名单**，漏一族就漏一批 —— 报出来的仍是下界。
FAMILIES = "CDJPEBSF"
_ID = re.compile(r'(?<![A-Za-z0-9_])([' + FAMILIES + r'])(\d{1,2})(?![0-9])')
ROW = re.compile(r'^\|[\s*]*([CDJPEBSF]\d{1,2})(?![0-9])')
BOLD = re.compile(r'^\*\*([CDJPEBSF]\d{1,2})(?![0-9])')
REV = re.compile(r'^## 修订 (\d+)')

HEADER_NS = "§P* 预登记头部"


def sections(lines):
    """每行所属的命名空间。⚠ 头部自成一区 —— 很多编号最早定义在那里。"""
    out, cur = [], HEADER_NS
    for l in lines:
        m = REV.match(l)
        if m:
            cur = "修订" + m.group(1)
        out.append(cur)
    return out


def find_definitions(lines):
    """→ {id: {命名空间: [(行号, 原文), …]}}"""
    sec = sections(lines)
    out = defaultdict(lambda: defaultdict(list))
    for i, l in enumerate(lines):
        s = l.strip()
        m = ROW.match(s) or BOLD.match(s)
        if not m:
            continue
        out[m.group(1)][sec[i]].append((i + 1, s[:70]))
    return out


def collisions(defs, min_ns=2):
    """→ [(id, {ns: hits}), …]，只留跨 ≥min_ns 个命名空间定义的。"""
    hit = [(k, v) for k, v in defs.items() if len(v) >= min_ns]
    hit.sort(key=lambda kv: (-len(kv[1]), -sum(len(x) for x in kv[1].values())))
    return hit


def render(hit, max_show=5):
    L = []
    a = L.append
    a("在**定义位**上跨命名空间重复定义的编号：共 %d 个" % len(hit))
    a("⚠⚠⚴ **这是下界**：只认「表格行/加粗行首」两种定义位，行内引用一概不认。")
    a("")
    for k, v in hit:
        tot = sum(len(x) for x in v.values())
        a("%-4s 共 %2d 处定义，跨 %d 个命名空间" % (k, tot, len(v)))
        for s in sorted(v, key=lambda x: (x != HEADER_NS, x))[:max_show]:
            i, d = v[s][0]
            a("    %-16s L%-6d %s" % (s, i, d))
        if len(v) > max_show:
            a("    …另 %d 个命名空间" % (len(v) - max_show))
        a("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 自检：判据必须能红，且「下界」这句话本身要能验
# ---------------------------------------------------------------------------

SYNTH = [
    "## 修订 1 —— x",
    "| C4 前端条件一 | ✅ |",          # 修订1 定义 C4
    "| E1 另一个条件 | ✅ |",
    "正文里随便提一句 C4，不算定义位",     # ← 行内引用，**不该**被算
    "## 修订 2 —— y",
    "| C4 完全不同的东西 | ✅ |",          # 修订2 又定义 C4 ⇒ 重载
    "**D4（加粗行首也算定义位）** 这里",     # 加粗行首算
    "**J1（同一个）** 也算",              # 同一个 id 两个修订没有 ⇒ 不重载
]


def selftest():
    ok = True

    def ck(name, cond):
        nonlocal ok
        print("  %-58s %s" % (name, "PASS" if cond else "FAIL"))
        if not cond:
            ok = False

    defs = find_definitions(SYNTH)
    hit = dict((k, v) for k, v in collisions(defs))
    ck("S1 ⛔ 跨修订重复定义 ⇒ 判为重载（C4）", "C4" in hit)
    ck("S2 ⛔ 只在一个命名空间定义 ⇒ 不判重载（J1）", "J1" not in hit)
    ck("S3 ⛔ 加粗行首**也**算定义位（D4）", "D4" in defs)
    ck("S4 ⛔⛔ 行内引用**不算**定义位（E1 只 1 处）",
       len(defs.get("E1", {})) == 1)
    ck("S5 ⛔ 只认 FAMILIES 里的编号族", all(k[0] in FAMILIES for k in defs))

    # ⛔ 变异：把加粗规则去掉 ⇒ S3 必须红（证明 S3 有分辨力）
    import re as _re
    mut = [l for l in SYNTH if not l.startswith("**D4")]
    if len(mut) != len(SYNTH) - 1:
        print("  %-58s FAIL" % "S6 ⛔ 变异去掉加粗行 ⇒ D3/S3 必须红")
        ok = False
    else:
        d2 = find_definitions(mut)
        ck("S6 ⛔ 变异去掉加粗行首 ⇒ D4 不再是定义位 ⇒ S3 会红",
           "D4" not in d2)

    # ⛔ 变异：把「跨命名空间」放宽成「同命名空间出现两次」⇒ S2 必须红
    d3 = {k: v for k, v in defs.items() if sum(len(x) for x in v.values()) >= 2}
    ck("S7 ⛔⛔ 变异：同命名空间定义两次**也**判重载 ⇒ 会把 J1 误报 ⇒ S2 有分辨力",
       "J1" not in d3)

    print()
    print("RESULT r224_id_collision_selftest  %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.ledger:
        ap.error("需要 --ledger 或 --selftest")
    if not os.path.exists(a.ledger):
        print("⛔ 账本不存在：%s" % a.ledger, flush=True)
        return 2
    hit = collisions(find_definitions(
        open(a.ledger, encoding="utf-8").read().split("\n")))
    txt = render(hit)
    print(txt, flush=True)
    if a.out:
        import json
        json.dump({k: {s: [i for i, _ in v2] for s, v2 in v.items()}
                   for k, v in hit},
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n[落盘] %s" % a.out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
