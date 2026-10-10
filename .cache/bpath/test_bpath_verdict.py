"""BPATH_VERDICT.md 与交付 JSON 的逐项核对（修订 43）。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_bpath_verdict.py

## 这些用例在钉什么

1. **总体判决的每个数字都能追到产物的一个字段**（§1.1 / §1.2 / §1.3）。
2. **阶梯表逐格 == 交付 JSON 的 `ladder_mapping`**（预登记 §43.1 的 L-1）。
3. **L-1：被后续修订改变了读法的表述，理由必须一起改** ——
   提到「已被推翻」就必须在同一条 note 里说明理由也变了。
4. **L-2：阶梯不得把「不可判定」印成「有证据反对」** ——
   任何 `evidence_against_*` 状态一律红。

⚠ 第 3、4 条的来源：L7 曾标成 `evidence_against_naive_reading`，
而它自己的 note 写的是「不能外推」⇒ **状态标签在断言一件没测的事**。
光读 note 是发现不了的，必须查**状态字段**。
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
DOC = os.path.join(ROOT, "docs/BPATH_VERDICT.md")
BUILT = os.path.join(ROOT, "frontend/public/latent/data/"
                            "bpath_marker_steering.json")

FAILS = []


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + ("" if cond else f"  ← {detail}"))
    if not cond:
        FAILS.append(name)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def rows(seg):
    out = []
    for line in seg.splitlines():
        s = line.strip()
        if not s.startswith("|") or not s.endswith("|"):
            continue
        cells = [c.strip() for c in s[1:-1].split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        out.append(cells)
    return out


# ---------------------------------------------------------------- 判据
def verify(doc, d):
    bad = []

    def need(cond, name):
        if not cond:
            bad.append(name)

    t = d["orthogonality"]["token_id37"]
    s = d["orthogonality"]["selection40"]
    ps = t["position_strat"]
    be, bh = t["batches"][0], t["batches"][1]

    # ---- §1.1 符号维度 ----
    for b, tag in ((be, "E"), (bh, "高对齐")):
        # ⚠ 交付 JSON 里 `dom_neg` / `rest_neg` **已经是**构建器拼好的
        #   `k/n` 字符串，不是整数 ⇒ 别再拼一次（会得到 121/125/125）。
        need(b["dom_neg"] in doc,
             f"判决 §1.1 {tag} 批 7196 计数 = {b['dom_neg']}")
        need(b["rest_neg"] in doc,
             f"判决 §1.1 {tag} 批 其余计数 = {b['rest_neg']}")
        need(format(b["dom_neg_frac"], ".3f") in doc,
             f"判决 §1.1 {tag} 批 7196 比率 = {format(b['dom_neg_frac'], '.3f')}")
        need(format(b["rest_neg_frac"], ".3f") in doc,
             f"判决 §1.1 {tag} 批 其余比率 = {format(b['rest_neg_frac'], '.3f')}")
        need(format(b["chi2_mh"], ".2f") in doc,
             f"判决 §1.1 {tag} 批 CMH = {format(b['chi2_mh'], '.2f')}")
    need(f"{format(s['A0']['rho_obs'], '.4f')}" in doc,
         f"判决 §1.2 ρ_obs = {format(s['A0']['rho_obs'], '.4f')}")
    need(format(s["A0"]["p"], ".4f") in doc,
         f"判决 §1.2 A0 p = {format(s['A0']['p'], '.4f')}")
    need(f"n = {s['A0']['n']}" in doc, f"判决 §1.2 A0 n = {s['A0']['n']}")
    need(format(s["A1"]["p"], ".4f") in doc,
         f"判决 §1.2 A1 p = {format(s['A1']['p'], '.4f')}")
    need(f"{format(s['A2']['rho_null'], '.4f')}" in doc,
         f"判决 §1.2 ρ_null = {format(s['A2']['rho_null'], '.4f')}")
    need(format(s["A2"]["cover"], ".3f") in doc,
         f"判决 §1.2 覆盖度 = {format(s['A2']['cover'], '.3f')}")

    # ---- §1.3 筛选富集 ----
    need(format(s["B2"]["sel_frac_dom"] * 100, ".1f") in doc,
         f"判决 §1.3 选中占比 = {format(s['B2']['sel_frac_dom'] * 100, '.1f')}")
    need(format(s["B2"]["baseline_frac_dom"] * 100, ".1f") in doc,
         f"判决 §1.3 全体占比 = {format(s['B2']['baseline_frac_dom'] * 100, '.1f')}")
    need(f"富集 {format(s['B2']['enrich'], '.2f')}×" in doc,
         f"判决 §1.3 富集 = {format(s['B2']['enrich'], '.2f')}×")
    need(format(s["B2"]["p"], ".1e") in doc,
         f"判决 §1.3 Fisher p = {format(s['B2']['p'], '.1e')}")

    # ---- §3 位置共线 ----
    need(format(ps["chi2_mh"], ".2f") in doc,
         f"判决 §3 位置分层 CMH = {format(ps['chi2_mh'], '.2f')}")
    need(f"{ps['n_strata_used']} 层" in doc,
         f"判决 §3 层数 = {ps['n_strata_used']}")

    # ---- §0 / §2.1 静态读数与 P9 ----
    r = d["readability_static"]
    need(format(r["freq_weighted"], "+.5f") in doc,
         f"判决 §0 频次加权 = {format(r['freq_weighted'], '+.5f')}")
    need(f"{r['n_ids_positive']}/{r['n_ids']} 个 marker id" in doc,
         f"判决 §0 正号 id = {r['n_ids_positive']}/{r['n_ids']}")
    p9 = d["p9_device_benchmark"]
    need(f"P9 {p9['n_pass']}/{p9['n']} 通过" in doc,
         f"判决 §2 P9 = {p9['n_pass']}/{p9['n']}")

    # ---- L-1 / L-2：阶梯表逐格一致 ----
    doc_ladder = {}
    for c in rows(doc):
        m = re.fullmatch(r"\*\*(L[0-7])\*\*", c[0])
        if m and len(c) >= 4:
            doc_ladder[m.group(1)] = c[2].strip("`").strip()
    json_ladder = {r["level"]: r["bpath_state"] for r in d["ladder_mapping"]}
    need(set(doc_ladder) == set(json_ladder),
         f"判决阶梯表的级 == 交付 JSON（文档 {sorted(doc_ladder)} "
         f"vs JSON {sorted(json_ladder)}）")
    for lv, st in json_ladder.items():
        need(doc_ladder.get(lv) == st,
             f"判决阶梯表 {lv} = {st!r}（文档 {doc_ladder.get(lv)!r}）")

    for r_ in d["ladder_mapping"]:
        st, note = r_["bpath_state"], r_["note"]
        # L-2：不得把「不可判定」印成「有证据反对」
        need(not st.startswith("evidence_against"),
             f"阶梯 {r_['level']} 状态不是 evidence_against_*（实际 {st!r}）")
        # L-1：提到旧判决就必须连理由一起改
        if "已被推翻" in note:
            need("理由变了" in note,
                 f"阶梯 {r_['level']} 的 note 提到「已被推翻」就同时改了理由")
        # L-1：`here` 必须带具体数字，不能是一句没有数的断言
        need(bool(re.search(r"\d", r_["here"])),
             f"阶梯 {r_['level']} 的 here 带具体数字")
    return bad


# ---------------------------------------------------------------- 主流程
print("== 1. 读产物与判决文档 ==")
doc = read(DOC)
d = json.loads(read(BUILT))
ok("判决文档存在且 0 坏字",
   os.path.exists(DOC) and doc.count("\ufffd") == 0)
ok("交付 JSON 带 ladder_mapping", bool(d.get("ladder_mapping")))
ok("L7 状态已是 not_adjudicable",
   [r for r in d["ladder_mapping"] if r["level"] == "L7"][0]["bpath_state"]
   == "not_adjudicable")

print("\n== 2. 真数据必须全过 ==")
bad = verify(doc, d)
ok(f"真数据 {len(bad)} 条判据全过", not bad, str(bad[:6]))

print("\n== 3. 变异自证 ==")
MUTS = [
    ("§1.1 的 7196 计数改了", "dom_neg"),
    ("§1.1 的 CMH 改了", "chi2"),
    ("§1.2 的 ρ_obs 改了", "rho_obs"),
    ("§1.2 的 A1 p 改了", "a1p"),
    ("§1.2 的覆盖度改了", "cover"),
    ("§1.3 的富集倍数改了", "enrich"),
    ("§1.3 的 Fisher p 改了", "b2p"),
    ("§3 的位置 χ² 改了", "ps_chi2"),
    ("P9 的通过数改了", "p9"),
    ("阶梯 L7 状态退回 evidence_against", "l7_state"),
    ("阶梯 L2 的 note 只留判决不留理由", "l2_reason"),
    ("阶梯某一行的 here 没有数字了", "no_num"),
]


def mutate(kind):
    e = copy.deepcopy(d)
    t = e["orthogonality"]["token_id37"]
    if kind == "dom_neg":
        # ⚠ 该字段是**字符串**，变异也得是字符串（写成整数会崩在 `in` 上，
        #   而崩掉 ≠ 变红 ⇒ 那样这条变异是假的）
        t["batches"][0]["dom_neg"] = "120/125"
    elif kind == "chi2":
        t["batches"][0]["chi2_mh"] = 60.0
    elif kind == "rho_obs":
        e["orthogonality"]["selection40"]["A0"]["rho_obs"] = 0.30
    elif kind == "a1p":
        e["orthogonality"]["selection40"]["A1"]["p"] = 0.001
    elif kind == "cover":
        e["orthogonality"]["selection40"]["A2"]["cover"] = 0.900
    elif kind == "enrich":
        e["orthogonality"]["selection40"]["B2"]["enrich"] = 1.10
    elif kind == "b2p":
        e["orthogonality"]["selection40"]["B2"]["p"] = 1.0e-10
    elif kind == "ps_chi2":
        t["position_strat"]["chi2_mh"] = 4.35
    elif kind == "p9":
        e["p9_device_benchmark"]["n_pass"] = 3
    elif kind == "l7_state":
        for r_ in e["ladder_mapping"]:
            if r_["level"] == "L7":
                r_["bpath_state"] = "evidence_against_naive_reading"
    elif kind == "l2_reason":
        for r_ in e["ladder_mapping"]:
            if r_["level"] == "L2":
                r_["note"] = "修订 29：「对齐度反向」已被推翻。"
    elif kind == "no_num":
        for r_ in e["ladder_mapping"]:
            if r_["level"] == "L5":
                r_["here"] = "没有"
    return e


for name, kind in MUTS:
    got = verify(doc, mutate(kind))
    ok(f"变异「{name}」能让守卫变红", bool(got),
       "verify 仍然全绿 ⇒ 这条判据没有牙齿")

print("\n== 4. 反向变异：改文档也必须红 ==")
# ⚠ 反引号在 bash 里是命令替换 ⇒ 传给本文件的字面量里**不能**直接写反引号，
#   否则替换串会变成空的（表现为「变异没生效」）。用 chr(96) 拼出来。
BT = chr(96)
for name, old, new in [
    ("L7 那一格的状态改了", BT + "not_adjudicable" + BT,
     BT + "evidence_against" + BT),
    ("富集倍数改了", "富集 2.28×", "富集 1.28×"),
    ("L5 那一格的状态改了", BT + "missing" + BT, BT + "done" + BT),
]:
    # ⚠ 判「变异已生效」要问的是**替换有没有真的改变文本**，
    #   不能问「新串在文档里不存在」—— 新串可能在别处合法出现
    #   （本次 `done` 就是 L2 的合法状态），那样这条守卫会恒假。
    ok(f"文档变异「{name}」已生效",
       old in doc and doc.replace(old, new, 1) != doc,
       "文档里找不到待替换的原文，或替换后文本没变 ⇒ 这条测不到东西")
    got = verify(doc.replace(old, new, 1), d)
    ok(f"文档变异「{name}」能让守卫变红", bool(got),
       "verify 仍然全绿 ⇒ 这条判据没有牙齿")

print()
if FAILS:
    print(f"**先验失败 {len(FAILS)} 项**：{FAILS}")
    sys.exit(1)
print("先验全过")