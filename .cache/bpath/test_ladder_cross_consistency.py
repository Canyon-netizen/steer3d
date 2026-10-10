"""两份阶梯产物的**跨产物一致性**核对（修订 44，判据 X-2）。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_ladder_cross_consistency.py

## 为什么要单独一套

`EvidenceLadderPanel` 与 `BPathPanel` 在 `/` 这一页上**前后相邻**，
渲染两份产物：`evidence_ladder.json`（原数据集）与
`bpath_marker_steering.json`（B 路 / R-6）。

同屏的两份产物，**每一份单独读都通顺**，但合起来会撞上矛盾：

* L6 —— 主阶梯「**缺**随机臂」，B 路「**有**随机臂」，两边都 `partial`；
* L7 —— 主阶梯「一次都没测（缺位置轴对照）」，B 路「做了位置轴对照，
  但位置与 token 共线 ⇒ 不可判定」；
* L2 —— 主阶梯给「14 条」，B 路给 `w·U`，两个**不同**的读数顶同一格。

⚠ 这类矛盾比「一份产物内部自相矛盾」更隐蔽：单读任一份都发现不了。
⇒ 判据 X-1 要求**每一级都注明证据基底**；本文件把它钉住。

## 这些用例在钉什么

1. 两份产物的状态都在**各自的封闭词表**内；
2. **两份都描述的每一级**，两边 note 都必须带批次限定词
   （主阶梯「原数据集」／B 路「B 路」）；
3. 一边引用另一边的说法时，**必须同时给出自己这批的说法**；
4. 同一级的两个状态在「**能不能声称**」这一位上必须一致
   —— `missing` 与 `done` 打架是硬错。
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
MAIN = os.path.join(ROOT, "frontend/public/latent/data/evidence_ladder.json")
BPATH = os.path.join(ROOT, "frontend/public/latent/data/"
                            "bpath_marker_steering.json")

MAIN_STATES = {"done", "partial", "missing"}
BPATH_STATES = {"done", "partial", "missing", "not_adjudicable"}
MAIN_BATCH = "原数据集"
BPATH_BATCH = "B 路"


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + ("" if cond else f"  ← {detail}"))
    if not cond:
        FAILS.append(name)


def verify(main, bpath):
    bad = []

    def need(cond, name):
        if not cond:
            bad.append(name)

    M = {r["level"]: r for r in main["ladder"]}
    B = {r["level"]: r for r in bpath["ladder_mapping"]}
    both = sorted(set(M) & set(B))
    need(len(both) >= 4,
         f"两份产物描述的级数 ≥ 4（实际 {both}）")

    for lv in both:
        m, b = M[lv], B[lv]
        # ---- 1. 封闭词表 ----
        need(m["state"] in MAIN_STATES,
             f"主阶梯 {lv} 状态在词表内（实际 {m['state']!r}）")
        need(b["bpath_state"] in BPATH_STATES,
             f"B 路 {lv} 状态在词表内（实际 {b['bpath_state']!r}）")
        # ---- 2. 批次限定词（X-1）----
        need(MAIN_BATCH in m.get("note", "") or MAIN_BATCH in m.get("here", ""),
             f"主阶梯 {lv} 注明了证据基底是「{MAIN_BATCH}」")
        need(BPATH_BATCH in b.get("note", "") or BPATH_BATCH in b.get("here", ""),
             f"B 路 {lv} 注明了证据基底是「{BPATH_BATCH}」")
        # ---- 4. 「能不能声称」必须一致 ----
        claimable = {"done", "partial"}
        need((m["state"] in claimable) == (b["bpath_state"] in claimable),
             f"{lv} 两边的「能不能声称」一致"
             f"（主 {m['state']!r} vs B 路 {b['bpath_state']!r}）")

    # ---- 3. 引用对方时必须同时给出自己这批的说法 ----
    for lv in both:
        mn, bn = M[lv].get("note", ""), B[lv].get("note", "")
        if "B 路" in mn:
            need(MAIN_BATCH in mn,
                 f"主阶梯 {lv} 引用 B 路时同时说了自己这批是「{MAIN_BATCH}」")
        if "主阶梯" in bn:
            need(BPATH_BATCH in bn,
                 f"B 路 {lv} 引用主阶梯时同时说了自己这批是「{BPATH_BATCH}」")
    return bad


FAILS = []

print("== 1. 读两份产物 ==")
main = json.loads(open(MAIN, encoding="utf-8").read())
bpath = json.loads(open(BPATH, encoding="utf-8").read())
ok("两份产物都在", os.path.exists(MAIN) and os.path.exists(BPATH))
ok("主阶梯自带 6 条跨产物自检标记",
   main.get("selfcheck_passed") is True)

print("\n== 2. 真数据必须全过 ==")
bad = verify(main, bpath)
ok(f"真数据 {len(bad)} 条判据全过", not bad, str(bad[:6]))

print("\n== 3. 变异自证 ==")
MUTS = [
    ("主阶梯 L6 去掉批次限定", "main_batch"),
    ("B 路 L7 去掉批次限定", "bpath_batch"),
    ("B 路 L7 改成 done（与主阶梯的 missing 打架）", "claim_disagree"),
    ("主阶梯 L7 改成 done（B 路是不可判定）", "claim_disagree2"),
    ("主阶梯 L6 状态塞进非法值", "bad_state"),
    ("B 路 L6 塞进 evidence_against_*", "bad_state2"),
    ("B 路 L6 引用主阶梯却不说自己这批", "no_own"),
    ("主阶梯 L2 去掉批次限定", "main_batch2"),
]


def mutate(kind):
    m, b = copy.deepcopy(main), copy.deepcopy(bpath)
    M = {r["level"]: r for r in m["ladder"]}
    B = {r["level"]: r for r in b["ladder_mapping"]}
    if kind == "main_batch":
        M["L6"]["note"] = M["L6"]["note"].replace("（**原数据集**）", "")
    elif kind == "bpath_batch":
        # ⚠ 第一版只 replace 了第一处，而 note 后半句还有「对 B 路这一批」⇒
        #   判据照样通过，变异是**假的**。必须去掉**全部**出现。
        B["L7"]["note"] = B["L7"]["note"].replace(BPATH_BATCH, "那批")
        B["L7"]["note"] = B["L7"]["note"].replace("R-6", "另一条线")
    elif kind == "claim_disagree":
        B["L7"]["bpath_state"] = "done"
    elif kind == "claim_disagree2":
        M["L7"]["state"] = "done"
    elif kind == "bad_state":
        M["L6"]["state"] = "ok_mostly"
    elif kind == "bad_state2":
        B["L6"]["bpath_state"] = "evidence_against_naive_reading"
    elif kind == "no_own":
        # ⚠ 保留「主阶梯」三个字，但**不给**自己这批的限定词。
        B["L6"]["note"] = "主阶梯那边说 L6 缺随机臂。"
    elif kind == "main_batch2":
        M["L2"]["note"] = M["L2"]["note"].replace("（**原数据集**）", "")
    return m, b


for name, kind in MUTS:
    m, b = mutate(kind)
    got = verify(m, b)
    ok(f"变异「{name}」能让守卫变红", bool(got),
       "verify 仍然全绿 ⇒ 这条判据没有牙齿")

print()
if FAILS:
    print(f"**先验失败 {len(FAILS)} 项**：{FAILS}")
    sys.exit(1)
print("先验全过")