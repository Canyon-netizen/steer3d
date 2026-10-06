#!/usr/bin/env python3
"""独立重算层：验证「行为阈值随决胜间距单调」这条机制断言。

为什么要有这一层
----------------
探针 `probe_live_inject.py` 自己会印「单调，断言成立」。但那**声称**强于它的
判据：判据读的正是探针自己算出来的 `per_step_threshold_bracket` 和
`mechanism_monotonic`。如果探针的取下界逻辑写错了，两边会**一起错**，照样全绿
—— 这就是「判据与产品共用一份手抄」。

所以这里**不复用探针的任何中间结果**：只读最底层的 `scans[].rows[]`
（每格 = 每强度 × 每步的 top1 token / 决胜间距 / 是否翻盘），
从这些原始行**重新**判定「这一步在哪些强度翻过」，再重建区间、重新查单调性。
两边不一致就报红。

用法: python3 .cache/xcheck/verify_threshold_law.py [probe_live_inject.json]
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    REPO, ".cache", "probe_live_inject.json")

checks = []


def rec(name, ok, detail):
    checks.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}\n       {detail}")


def main():
    if not os.path.exists(PATH):
        rec("X0 探针产物在（没有它就无从验起）", False, f"缺文件 {PATH}")
        return 1
    d = json.load(open(PATH, encoding="utf-8"))
    scans = d.get("scans") or []
    rec("X0 探针产物在且含扫描数据", bool(scans),
        f"{PATH}  scans={len(scans)}  steps={d.get('steps')}")

    if not scans:
        return 1
    grid = sorted(s["mult"] for s in scans)
    steps = d["steps"]

    # ── 独立重建：从 rows 里重算「每步在哪些强度翻过」 ──────────────
    rebuilt = {}
    for i in range(steps):
        flips_at = None
        for s in scans:
            r = s["rows"][i]
            if r["token_ctrl"] != r["token_inj"]:
                flips_at = s["mult"]
                break
        rebuilt[i] = flips_at

    # 与探针自己印的逐��区间对账
    probe_claim = {p["step"]: p.get("flips_at") for p in
                   d.get("per_step_threshold_bracket", [])}
    mism = {i: (rebuilt[i], probe_claim.get(i)) for i in rebuilt
            if rebuilt[i] != probe_claim.get(i)}
    rec("E1 独立重算的「每步首次翻盘强度」与探针自印的一致",
        not mism,
        f"重算={ {i: rebuilt[i] for i in rebuilt} }"
        + ("" if not mism else f"  不一致={mism}"))

    # ── 独立重建单调性 ────────────────────────────────────────────
    # 下界：翻盘格的上一次采样点；若该步在最低档就翻，下界记 0（无下界）。
    lows, margins = {}, {}
    for i in range(steps):
        m = rebuilt[i]
        if m is None:
            lows[i] = grid[-1]        # 到上限仍不翻 ⇒ 只知 >grid[-1]
        else:
            k = grid.index(m)
            lows[i] = grid[k - 1] if k > 0 else 0.0
        margins[i] = scans[0]["rows"][i]["margin_ctrl"]
    order = sorted(margins, key=lambda s: margins[s])
    viol = [(a, b) for a, b in zip(order, order[1:])
            if lows[b] < lows[a] - 1e-12]
    rec("E2 独立重算：阈值下界随决胜间距单调不减（机制断言）",
        not viol,
        "  ".join(f"步{s}:间距{margins[s]:.2f}→下界{lows[s]:.3f}" for s in order)
        + ("" if not viol else f"   反例={viol}"))

    # ── 独立重算翻盘总数 ───────────────────────────────────────────
    n_flip = sum(1 for i in range(steps) if rebuilt[i] is not None)
    any_rows = [r for s in scans for r in s["rows"]]
    tot_flip = sum(1 for r in any_rows if r["flipped"])
    rec("E3 「有翻盘的步数」与「翻盘格子总数」两个数互相对得上",
        n_flip <= tot_flip <= n_flip * len(grid),
        f"有翻盘的步数={n_flip}  翻盘格子总数={tot_flip}  档数={len(grid)}"
        f"  （后者应在前者与 前者×档数 之间）")

    # ── 效应的「剂量」必须真的随强度单调增强 ───────────────────────
    # 若 max|Δlogit| 不随强度涨，那「剂量-反应」就是假的。
    dl = [(s["mult"], max(r["max_abs_dlogit"] for r in s["rows"])) for s in scans]
    inc = all(dl[i][1] <= dl[i + 1][1] + 1e-6 for i in range(len(dl) - 1))
    rec("E4 剂量-反应前提：最大 |Δlogit| 随注入强度单调不减", inc,
        "  ".join(f"{m}×→{v:.3f}" for m, v in dl))

    # ── hook 确实生效过（否则整套都是空转）─────────────────────────
    rec("E5 注入确实改变了 logit（否则是装置故障不是结论）",
        all(max(r["max_abs_dlogit"] for r in s["rows"]) > 1e-6 for s in scans),
        f"各档最大Δlogit="
        f"{[round(max(r['max_abs_dlogit'] for r in s['rows']), 4) for s in scans]}")

    # ══════════════════════════════════════════════════════════════
    # 产物层：网站读的那份 JSON 必须与原始扫描对得上，且**自洽**
    # ══════════════════════════════════════════════════════════════
    ART = os.environ.get("ARTIFACT") or os.path.join(
        REPO, "frontend", "public", "latent", "data",
        "intervention_threshold_law.json")
    if not os.path.exists(ART):
        rec("F1 产物文件在", False, f"缺 {ART}（先跑 build_threshold_law.py）")
        return 1
    art = json.load(open(ART, encoding="utf-8"))
    rec("F1 产物文件在且含机制与剂量-反应两节",
        bool(art.get("mechanism")) and bool(art.get("dose_response")),
        f"{ART}  档数={len(art.get('dose_response') or [])}")

    # F2 产物的逐档 Δlogit 必须等于从原始行重算的
    a_dl = {round(x["mult"], 6): x["max_abs_dlogit"] for x in art["dose_response"]}
    r_dl = {round(s["mult"], 6): round(max(r["max_abs_dlogit"] for r in s["rows"]), 4)
            for s in scans}
    diff = {k: (r_dl[k], a_dl.get(k)) for k in r_dl
            if a_dl.get(k) is None or abs(a_dl[k] - r_dl[k]) > 1e-3}
    rec("F2 产物的逐档 |Δlogit| == 从原始行重算的值（产物没手抄/没漂移）",
        not diff, f"重算={r_dl}" + ("" if not diff else f"   不符={diff}"))

    # F3 产物的逐步区间必须等于独立重建的
    a_ps = {p["step"]: p for p in art.get("per_step", [])}
    f3 = []
    for i in range(steps):
        m = rebuilt[i]
        want_hi = m
        if m is None:
            want_bracket, want_lo = "right_censored", grid[-1]
        else:
            k = grid.index(m)
            want_lo = grid[k - 1] if k > 0 else 0.0
            want_bracket = "bracketed" if want_lo > 0 else "left_censored"
        got = a_ps.get(i, {})
        if (got.get("bracket") != want_bracket
                or (got.get("threshold_hi") or None) != want_hi
                or abs(float(got.get("threshold_lo", -1)) - want_lo) > 1e-9):
            f3.append((i, want_bracket, want_lo, want_hi, got.get("bracket"),
                       got.get("threshold_lo"), got.get("threshold_hi")))
    rec("F3 产物的逐步阈值区间 == 独立重建的", not f3,
        f"逐步= {[(i, rebuilt[i]) for i in rebuilt]}"
        + ("" if not f3 else f"   不符={f3}"))

    # F4 产物**自洽**：verdict 必须与它自己记的 evidence 推出的一致
    # 这条专防「JSON 里 stable=true、日志里写不稳」那类自相矛盾：
    # 读者（人或脚本）只看 stable=true 就会以为这是通则。
    g = art.get("generality")
    if not g:
        rec("F4 产物自洽：通用性一节的结论与它的证据一致", True,
            "通用性一节缺失（没跑 probe_threshold_law.py），无可判")
    else:
        ev = g.get("evidence", {})
        implied = ev.get("gate_A_ratio_within_limit") and ev.get("gate_B_all_bracketed")
        want = "candidate_law" if implied else "not_general"
        rec("F4 产物自洽：verdict 与 evidence 推出的结论一致（不许 stable=true 而 verdict 说不稳）",
            g.get("verdict") == want,
            f"verdict={g.get('verdict')}  门A={ev.get('gate_A_ratio_within_limit')} "
            f"门B={ev.get('gate_B_all_bracketed')}  ⇒ 应为 {want}  "
            f"未夹住={ev.get('n_unbracketed_pairs')}/{ev.get('n_pairs')}")

    # F5 若判决是 not_general，页面上必须能读到**否定**的理由，不许只印成立那半
    if g and g.get("verdict") == "not_general":
        reason = g.get("verdict_reason") or ""
        rec("F5 判否时必须带可读的否定理由（不许只留下肯定的那一半）",
            len(reason) > 20 and ("不翻" in reason or "未夹" in reason or "没测到" in reason),
            f"理由长度={len(reason)}  摘要={reason[:70]}…")
    else:
        rec("F5 判否时必须带可读的否定理由", True, "本轮不适用（verdict 非 not_general）")

    # F6 产物里的「与回放相反」那条对照必须是真的有判据在管
    rec("F6 产物声明的「回放不改 token」有指定判据在管",
        "D13" in json.dumps(art.get("contrast_with_replay", {})),
        f"contrast_with_replay.checked_by="
        f"{(art.get('contrast_with_replay') or {}).get('checked_by')}")

    p = sum(1 for _, ok, _ in checks if ok)
    print(f"\n=== {p}/{len(checks)} passed ===")
    return 0 if p == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
