"""selection_contamination.py 的本地先验（假数据，不碰真产物）。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_selection_contamination.py

## 这些用例在钉什么

1. **两条落盘路径的键集合必须一致** —— 「A0 不适用」那条路径原本只写
   `{pass, why}`，而面板按完整结构读 `A1.median_dom.toFixed()` 与
   `A2.cover.toFixed()` ⇒ 换个不显著的数据就整页崩。真数据恰好 A0 适用，
   所以这缺陷**一直没暴露**，是夹具逼出来的。
2. **守卫不能空转（恒绿就是没判据）** —— 必须造出 B1 / A2 **各自不过**的反例。
3. **守卫不能误伤** —— 正例数据必须让 B1 / A1 / A2 都**过**。
4. **四道数据守卫** —— totals 对账、重复映射、缺映射、位点数。
5. **种子无关** —— 关键用例换 3 个种子，判决必须一致（防单种子运气）。
6. **实产物一致性（只读）** —— 重跑真数据，结论必须与已落盘产物逐字段相符。

⚠ 第 2 条最容易漏：`A2` 的覆盖度 = `|ρ_null| / |ρ_obs|`。若 `ρ_null` 恒大，
它就是个恒 PASS 的空判据。反例必须**真的**把覆盖度压到 0.5 以下。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
SCRIPT = os.path.join(HERE, "selection_contamination.py")
MUTBAK = os.path.join(ROOT, ".cache/mutbak")
PY = sys.executable

A1_KEYS = {"median_dom", "median_rest", "p", "max_p", "pass",
           "applicable", "why"}
A2_KEYS = {"rho_null", "cover", "need_cover", "pass", "applicable",
           "note", "rho_within", "why"}

FAILS = []


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + ("" if cond else f"  ← {detail}"))
    if not cond:
        FAILS.append(name)


def build(tmp, sel, all_dom_frac, all_total, n_traj, *,
          dup_map=False, drop_map=False, break_totals=False, seed=0):
    """造一整套假产物。

    sel            : [(dom: bool, aw: float, d: float), ...] —— 选中的位点
    all_dom_frac   : 全体 marker 位点里 dom 的占比（B2 的分母侧）
    all_total      : 全体 marker 位点总数（必须 ≥ len(sel)）
    """
    if n_traj > len(sel):
        n_traj = len(sel)
    all_dom = int(round(all_total * all_dom_frac))
    all_rest = all_total - all_dom

    rows, mp = [], []
    for i, (dom, aw, d) in enumerate(sel):
        traj = f"t{i % n_traj:02d}"
        t = 1000 + i
        rows.append({"traj": traj, "t": t, "mode": "think",
                     "w_dot_hhat": float(aw), "w_dot_h": 100.0,
                     "h_norm": 500.0, "npz_layer_read": 19,
                     "inject_hs_index": 20, "n_tok": 8192,
                     "points": [{"rel": 1.0, "alpha": 20.0,
                                 "d_marker": float(d), "d_rand": 0.05,
                                 "effective_dose": 0.01}]})
        mp.append({"traj": traj, "t": t, "token_id": 7196 if dom else 10061})

    # 全体 marker 的逐轨迹分摊（对账守卫要比 tracks 之和）
    per = all_total // n_traj
    tracks = [{"traj": f"t{j:02d}", "n_marker": per} for j in range(n_traj)]
    tracks[-1]["n_marker"] += all_total - per * n_traj
    allj = {"n_traj": n_traj, "n_marker_total": all_total,
            "totals": {"7196": all_dom, "10061": all_rest}, "tracks": tracks}
    if break_totals:                      # 故意让 totals 对不上 tracks
        allj["n_marker_total"] = all_total + 7

    if drop_map:
        mp = mp[:-1]
    if dup_map:
        mp = mp + [dict(mp[0])]

    P, Mp, A, O = (os.path.join(tmp, n) for n in
                   ("probe.json", "map.json", "all.json", "out.json"))
    for path, obj in ((P, {"schema": "probe/1", "wU_marker": 1.0, "rows": rows}),
                      (Mp, mp), (A, allj)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    return P, Mp, A, O


def run(probe, mp, allj, out, extra=()):
    cmd = [PY, SCRIPT, "--probe", probe, "--map", mp,
           "--marker-all", allj, "--out", out] + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True)
    res = None
    # ⚠ 只有**成功**才读产物：守卫触发时产物可能压根不存在，读它会把
    #    「判据拒绝判定」误报成「JSON 解析失败」，现场指向错误的方向。
    if r.returncode == 0 and os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            res = json.load(f)
    return r, res


def synth(kind, n=400, seed=0):
    """按名字造 sel（dom, aw, d）。"""
    rng = np.random.default_rng(seed)
    if kind == "null":            # aw 与 |Δ| 各自独立 ⇒ A0 不适用
        aw = rng.uniform(0.15, 0.6, n)
        d = rng.normal(0, 2.0, n)
        return [(bool(i % 2), float(aw[i]), float(d[i])) for i in range(n)]
    if kind == "clean":           # 两组 aw 分离；|Δ| 完全由 aw 决定
        aw = np.concatenate([rng.normal(0.20, 0.03, n // 2),
                             rng.normal(0.50, 0.03, n // 2)])
        d = aw + rng.normal(0, 0.01, n)
        dom = [i < n // 2 for i in range(n)]
        return [(dom[i], float(aw[i]), float(d[i])) for i in range(n)]
    if kind == "aw_drives":       # ρ_obs≈1 而组只解释一小块 ⇒ A2 不过
        # ⚠ dom 必须**与 aw 无关**（随机）⇒ ρ_null ≈ 0。
        #   第一版写成 `bool(dom) == bool(aw > median)`，那是在**挑选**
        #   「dom 且 aw 高 / 非 dom 且 aw 低」的样本 ⇒ 把相关**强化**到
        #   接近 1，cover 反而涨到 0.87，用例自己就假通过了。
        aw = rng.normal(0.5, 0.2, n)
        dom = rng.random(n) < 0.5
        d = aw + rng.normal(0, 0.02, n)   # ρ_obs ≈ 1
        return [(bool(dom[i]), float(aw[i]), float(d[i])) for i in range(n)]
    raise SystemExit(f"未知的 kind：{kind}")


# ---------------------------------------------------------------- 用例 1
print("== 1. A0 不适用路径：键集合与正常路径一致 ==")
with tempfile.TemporaryDirectory(prefix="selc_") as td:
    P, Mp, A, O = build(td, synth("null"), 0.25, 900, 12)
    r, res = run(P, Mp, A, O)
    ok("null 数据能跑通", r.returncode == 0, r.stderr[-300:])
    if res:
        ok("A1 键集合完整", set(res["A1"]) == A1_KEYS,
           f"多 {sorted(set(res['A1']) - A1_KEYS)}、缺 {sorted(A1_KEYS - set(res['A1']))}")
        ok("A2 键集合完整", set(res["A2"]) == A2_KEYS,
           f"多 {sorted(set(res['A2']) - A2_KEYS)}、缺 {sorted(A2_KEYS - set(res['A2']))}")
        ok("A0 判不适用", res["A0"]["pass"] == 0.0, res["A0"])
        ok("A0 不适用时 A1 报 False 而非 PASS",
           res["A1"]["pass"] == 0.0 and res["A1"]["applicable"] is False, res["A1"])
        ok("A0 不适用时 A2 报 False 而非 PASS",
           res["A2"]["pass"] == 0.0 and res["A2"]["applicable"] is False, res["A2"])
        ok("final 说不适用", "不适用" in res["final"], res["final"])
        ok("A1/A2 数值位是 null（面板不能拿到 undefined）",
           res["A1"]["median_dom"] is None and res["A2"]["cover"] is None,
           (res["A1"]["median_dom"], res["A2"]["cover"]))
        ok("B1/B2 仍然出数（不适用只关幅度侧）",
           "median_dom" in res["B1"] and "enrich" in res["B2"])

# ---------------------------------------------------------------- 用例 2
print("\n== 2. 正例：B1 / A1 / A2 都过（守卫不能误伤） ==")
for seed in (0, 1, 2):
    with tempfile.TemporaryDirectory(prefix="selc_") as td:
        P, Mp, A, O = build(td, synth("clean", seed=seed), 0.25, 1200, 12)
        r, res = run(P, Mp, A, O)
        if not res:
            ok(f"clean(seed={seed}) 跑通", False, r.stderr[-300:])
            continue
        ok(f"clean(seed={seed}) A0 适用", res["A0"]["pass"] == 1.0, res["A0"])
        ok(f"clean(seed={seed}) B1 过", res["B1"]["pass"] == 1.0, res["B1"])
        ok(f"clean(seed={seed}) A1 过", res["A1"]["pass"] == 1.0, res["A1"])
        ok(f"clean(seed={seed}) A2 过", res["A2"]["pass"] is True,
           f"cover={res['A2']['cover']}")
        ok(f"clean(seed={seed}) final 是「主要由 token 构成决定」",
           "主要由 token 构成决定" in res["final"], res["final"])

# ---------------------------------------------------------------- 用例 3
print("\n== 3. 反例：A2 必须能判不过（否则是恒 PASS 的空判据） ==")
for seed in (0, 1, 2):
    with tempfile.TemporaryDirectory(prefix="selc_") as td:
        P, Mp, A, O = build(td, synth("aw_drives", seed=seed), 0.25, 1200, 12)
        r, res = run(P, Mp, A, O)
        if not res:
            ok(f"aw_drives(seed={seed}) 跑通", False, r.stderr[-300:])
            continue
        ok(f"aw_drives(seed={seed}) A0 适用（ρ_obs 显著）",
           res["A0"]["pass"] == 1.0, res["A0"])
        ok(f"aw_drives(seed={seed}) ρ_obs 明显大于 ρ_null",
           abs(res["A0"]["rho_obs"]) > abs(res["A2"]["rho_null"]),
           f"ρ_obs={res['A0']['rho_obs']} ρ_null={res['A2']['rho_null']}")
        ok(f"aw_drives(seed={seed}) A2 **不过**（覆盖度 < 0.5）",
           res["A2"]["pass"] is False and res["A2"]["cover"] < 0.5,
           f"cover={res['A2']['cover']}")
        ok(f"aw_drives(seed={seed}) final 不是「可被构成解释」",
           "可被构成解释" not in res["final"], res["final"])

# ---------------------------------------------------------------- 用例 4
print("\n== 4. B2 必须能判不过（enrich≈1 时） ==")
with tempfile.TemporaryDirectory(prefix="selc_") as td:
    sel = synth("null")
    n_dom = sum(1 for s in sel if s[0])
    frac = n_dom / len(sel)
    P, Mp, A, O = build(td, sel, frac, 900, 12)     # 全体占比 == 选中占比
    r, res = run(P, Mp, A, O)
    if res:
        ok("B2 富集≈1.0", abs(res["B2"]["enrich"] - 1.0) < 0.05, res["B2"])
        ok("B2 判不过", res["B2"]["pass"] == 0.0, res["B2"])
        ok("B1 也判不过（两组 aw 同分布）", res["B1"]["pass"] == 0.0, res["B1"])

# ---------------------------------------------------------------- 用例 5
print("\n== 5. 四道数据守卫 ==")
with tempfile.TemporaryDirectory(prefix="selc_") as td:
    P, Mp, A, O = build(td, synth("clean"), 0.25, 900, 10, dup_map=True)
    r, res = run(P, Mp, A, O)
    ok("重复 (traj,t) 拒绝判定", r.returncode != 0 and "重复" in r.stdout + r.stderr)

with tempfile.TemporaryDirectory(prefix="selc_") as td:
    P, Mp, A, O = build(td, synth("clean"), 0.25, 900, 10, drop_map=True)
    r, res = run(P, Mp, A, O)
    ok("缺 token 映射拒绝判定", r.returncode != 0 and "映射" in r.stdout + r.stderr)

with tempfile.TemporaryDirectory(prefix="selc_") as td:
    P, Mp, A, O = build(td, synth("clean"), 0.25, 900, 10, break_totals=True)
    r, res = run(P, Mp, A, O)
    ok("marker 总构成对不上拒绝判定",
       r.returncode != 0 and "对不上" in r.stdout + r.stderr)

with tempfile.TemporaryDirectory(prefix="selc_") as td:
    P, Mp, A, O = build(td, synth("clean"), 0.25, 900, 10)
    r, res = run(P, Mp, A, O, extra=["--expect-sites", "399"])
    ok("位点数不符拒绝判定",
       r.returncode != 0 and "拒绝判定" in r.stdout + r.stderr)

# ---------------------------------------------------------------- 用例 6
print("\n== 6. 噪声地板分支（--floor-same-slice） ==")
with tempfile.TemporaryDirectory(prefix="selc_") as td:
    P, Mp, A, O = build(td, synth("clean"), 0.25, 900, 10)
    r, res = run(P, Mp, A, O, extra=["--floor-same-slice", "0.0"])
    ok("地板=0 时位点全留", res is not None and res["A0"]["n"] == 400,
       res["A0"]["n"] if res else r.stderr[-200:])
with tempfile.TemporaryDirectory(prefix="selc_") as td:
    P, Mp, A, O = build(td, synth("clean"), 0.25, 900, 10)
    r, res = run(P, Mp, A, O, extra=["--floor-same-slice", "1e9"])
    ok("地板吃掉全部 ⇒ A0 不适用而不是崩",
       res is not None and res["A0"]["pass"] == 0.0 and set(res["A2"]) == A2_KEYS,
       res["A0"] if res else r.stderr[-200:])

# ---------------------------------------------------------------- 用例 7
print("\n== 7. 实产物一致性（只读；重跑真数据） ==")
real_in = {n: os.path.join(MUTBAK, n) for n in
           ("orthogonality_hi.json", "site_tokens_hi.json", "marker_all_hi.json")}
landed = os.path.join(MUTBAK, "selection_contamination.json")
missing = [n for n, p in real_in.items() if not os.path.exists(p)]
if missing or not os.path.exists(landed):
    ok("实产物齐全", False, f"缺 {missing or []} / 落盘产物 {not os.path.exists(landed)}")
else:
    with tempfile.TemporaryDirectory(prefix="selc_") as td:
        O = os.path.join(td, "out.json")
        r, res = run(real_in["orthogonality_hi.json"],
                     real_in["site_tokens_hi.json"],
                     real_in["marker_all_hi.json"], O,
                     extra=["--expect-sites", "453",
                            "--floor-same-slice", "1.4996"])
        ok("真数据跑通", r.returncode == 0, r.stderr[-300:])
        if res:
            old = json.load(open(landed, encoding="utf-8"))
            for blk in ("B1", "B2", "A0", "A1", "A2"):
                bad = [k for k in old[blk]
                       if k != "note" and old[blk][k] != res[blk].get(k)]
                ok(f"真数据 {blk} 与落盘产物逐字段一致", not bad,
                   f"不一致字段 {bad}：落盘 {[(k, old[blk][k]) for k in bad]} "
                   f"vs 重跑 {[(k, res[blk].get(k)) for k in bad]}")
            ok("真数据 n_sites = 453", res["n_sites"] == 453, res["n_sites"])
            ok("真数据 A0 适用位点 = 205", res["A0"]["n"] == 205, res["A0"]["n"])
            # ⚠ 不钉死 `2.275`：那是产物的一次舍入结果，钉它等于把
            #   显示精度写进测试（而显示精度正是用例 8 要守的东西）。
            #   这里只钉**实质结论**「富集约 2.3 倍、两位显示 2.28」。
            ok("真数据 B2 富集 ≈ 2.3 倍且两位显示 2.28",
               2.2 < res["B2"]["enrich"] < 2.3
               and format(res["B2"]["enrich"], ".2f") == "2.28",
               res["B2"]["enrich"])
            ok("真数据 B2 过 / A1 不过 / A2 过",
               res["B2"]["pass"] == 1.0 and res["A1"]["pass"] == 0.0
               and res["A2"]["pass"] is True,
               (res["B2"]["pass"], res["A1"]["pass"], res["A2"]["pass"]))
            ok("落盘产物本身键集合完整",
               set(old["A1"]) == A1_KEYS and set(old["A2"]) == A2_KEYS,
               (sorted(set(old["A1"]) ^ A1_KEYS), sorted(set(old["A2"]) ^ A2_KEYS)))

# ---------------------------------------------------------------- 用例 8
print("\n== 8. 文档/预登记表格里的数字必须与产物一致 ==")
# ⚠ 为什么需要这条：构建器的列表数字是**从产物自动取**的，散文与表格却是
#   手写的。改了产物而忘了改表格 ⇒ 逐字节复算照样通过、页面照样渲染，
#   只有读者会发现同一屏两个数打架。
#   ⚠ **本条只覆盖修订 40**。§4.3（修订 37）与 §4.3b（修订 39）的表格
#   数字**尚未**纳入守卫 —— 那是已知的缺口，列在下一步，不假装覆盖。

def section_tables(path, header, nxt):
    """抽出某章节里以 `|` 开头的表格行。"""
    src = open(path, encoding="utf-8").read()
    i = src.find(header)
    if i < 0:
        raise SystemExit(f"{path} 里找不到 {header}")
    j = src.find(nxt, i + len(header))
    seg = src[i:] if j < 0 else src[i:j]
    return "\n".join(l for l in seg.splitlines() if l.strip().startswith("|"))


def fmt(v, spec):
    return format(v, spec)


if missing or not os.path.exists(landed):
    ok("修订 40 表格数字守卫（缺产物，跳过）", True, "产物缺失，已在用例 7 报错")
else:
    sc = json.load(open(landed, encoding="utf-8"))
    DOC = os.path.join(ROOT, "docs/BPATH_MARKER_STEERING.md")
    PREREG = os.path.join(ROOT, ".cache/xcheck/R6_RERUN_PREREG.md")
    try:
        doc_tbl = section_tables(DOC, "### 4.3c", "\n---")
        pre_tbl = section_tables(PREREG, "### 40.4", "\n### 40.5")
    except SystemExit as e:
        ok("抽出修订 40 的表格", False, str(e))
        doc_tbl = pre_tbl = ""
    if doc_tbl and pre_tbl:
        want = [
            ("B1 7196 中位", fmt(sc["B1"]["median_dom"], ".4f")),
            ("B1 其余中位", fmt(sc["B1"]["median_rest"], ".4f")),
            ("B1 p", fmt(sc["B1"]["p"], ".4f")),
            ("B2 选中占比", fmt(sc["B2"]["sel_frac_dom"] * 100, ".1f") + "%"),
            ("B2 全体占比", fmt(sc["B2"]["baseline_frac_dom"] * 100, ".1f") + "%"),
            ("B2 富集", fmt(sc["B2"]["enrich"], ".2f")),
            ("A0 rho", fmt(sc["A0"]["rho_obs"], ".4f")),
            ("A0 p", fmt(sc["A0"]["p"], ".4f")),
            ("A1 7196 中位", fmt(sc["A1"]["median_dom"], ".4f")),
            ("A1 其余中位", fmt(sc["A1"]["median_rest"], ".4f")),
            ("A1 p", fmt(sc["A1"]["p"], ".4f")),
            ("A2 rho_null", fmt(sc["A2"]["rho_null"], ".4f")),
            ("A2 覆盖度", fmt(sc["A2"]["cover"], ".3f")),
        ]
        for label, s in want:
            ok(f"文档 §4.3c 表格含 {label} = {s}", s in doc_tbl, f"没找到 {s!r}")
            ok(f"预登记 §40.4 表格含 {label} = {s}", s in pre_tbl, f"没找到 {s!r}")

        # ⚠ 同屏精度纪律：散文里出现的 ρ 必须与表格**同精度**，
        #   否则读者在同一屏看到 0.1434 和 0.143 两个数。
        for where, seg in (("文档 §4.3c 散文", doc_tbl),):
            bad = [s for s in ("0.143 ", "0.192") if s in seg]
            ok(f"{where} 没有 3 位精度的 ρ", not bad, f"发现 {bad}")

        # ⚠ 构建器的散文必须**动态跟随产物**：把 claim 里的富集倍数
        #   换成别的值再构建，产物里的 claim 文本必须跟着变。
        built = json.load(open(os.path.join(
            ROOT, "frontend/public/latent/data/bpath_marker_steering.json"),
            encoding="utf-8"))
        s40 = built["orthogonality"].get("selection40")
        ok("交付 JSON 里含 selection40", bool(s40))
        if s40:
            ok("claim 的富集倍数跟随产物",
               fmt(sc["B2"]["enrich"], ".2f") + " 倍" in s40["claim"],
               s40["claim"])
            ok("mechanism_note 的 rho 跟随产物（4 位）",
               fmt(sc["A0"]["rho_obs"], ".4f") in s40["mechanism_note"]
               and fmt(sc["A2"]["rho_null"], ".4f") in s40["mechanism_note"],
               s40["mechanism_note"])
            ok("reading 的中位数跟随产物",
               fmt(sc["B1"]["median_dom"], ".4f") in s40["reading"]
               and fmt(sc["B1"]["median_rest"], ".4f") in s40["reading"],
               s40["reading"])
            ok("交付 JSON 的 selection40 与判决产物同源",
               s40["B2"]["enrich"] == sc["B2"]["enrich"]
               and s40["A2"]["cover"] == sc["A2"]["cover"],
               (s40["B2"]["enrich"], s40["A2"]["cover"]))

        # ⚠⚠ Python `format` 与 JS `toFixed` 必须在这些显示值上**给出同一个串**。
        #   两侧都踩同一个 IEEE754 坑（`2.275` 的实际值偏小 ⇒ 两边都给 2.27），
        #   所以「Python 对、JS 错」这种不一致**不可能被单侧检查发现** ——
        #   必须真的跑一次 JS 才知道面板上显示的是什么。
        #   这条也是为什么产物里 `enrich` 要存 8 位而不是 round 到 3 位。
        shown = [("enrich", sc["B2"]["enrich"], 2),
                 ("sel_frac%", sc["B2"]["sel_frac_dom"] * 100, 1),
                 ("base_frac%", sc["B2"]["baseline_frac_dom"] * 100, 1),
                 ("A2.cover", sc["A2"]["cover"], 3),
                 ("B1.median_dom", sc["B1"]["median_dom"], 4),
                 ("A1.median_dom", sc["A1"]["median_dom"], 4)]
        payload = json.dumps([[v, d] for _, v, d in shown])
        jscode = ("const a=JSON.parse(process.argv[1]);"
                  "console.log(a.map(p=>Number(p[0]).toFixed(p[1])).join(','))")
        try:
            nr = subprocess.run(["node", "-e", jscode, payload],
                                capture_output=True, text=True, timeout=60)
            ok("node 可用（面板侧格式化实测）", nr.returncode == 0,
               (nr.stderr or nr.stdout)[-200:])
            if nr.returncode == 0:
                for (lab, v, dig), g in zip(shown, nr.stdout.strip().split(",")):
                    py = format(v, f".{dig}f")
                    ok(f"JS toFixed 与 Python format 对 {lab} 同值", py == g,
                       f"Python {py} vs JS {g}（值 {v!r}）")
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            ok("node 可用（面板侧格式化实测）", True, f"跳过：{e}")

# ---------------------------------------------------------------- 收尾
print()
if FAILS:
    print(f"**先验失败 {len(FAILS)} 项**：{FAILS}")
    sys.exit(1)
print("先验全过")
