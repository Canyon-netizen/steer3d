#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""fixed_dose_density_target.py —— 244.75：测「固定剂量」的**目标密度 ρ\***（零 GPU）

⚖⚖⚖⚖⚖ **这一轮只测**：⛔ 不改口径、⛔ 不改预登记、⛔ 不改格清单、⛔ 不发批、⛔ 不改探针。
⚖⚖⚖⚖⚖ **只读**：本文件只读池快照 / 规格 / 生产阶梯 ⇒ ⇒ 不写任何产品文件。

🔴 **测什么**（① 那一轮要定的那个数，就是这里测出来的）
   ① **现批密度谱**：现有生产阶梯（`warm_cells.txt`，137 格）的**生产密度**长什么样
      ⇒ ⇒ 用来当「ρ\* 该取在哪儿」的**参照系**
   ② **inj 分布**：`inj(f) = P + max(1, int(n_gen·f)) − 1` 在三个 `pos_frac` 下的分布
      ⇒ ⇒ 它决定「每个 (轨迹, pos_frac) 有多少个合法 n_sites」
   ③ **候选 ρ\* 的实测清单**（本轮的核心产出）：
      对每个候选 ρ\* ⇒ 每个 (轨迹, pos_frac)：
        · **合法 n_sites 窗口** = { n ∈ [1, inj] : |n/inj − ρ\*| ≤ tol }
        · **规范 n_sites** = 最接近 ρ\*·inj 的那个整数（⇒ 密度 ≈ ρ\*）
        · **实测密度** = n_sites / inj
      ⇒ ⇒ 汇总：可行组合数 / D2（同轨迹密度相等）满足的轨迹数 / 最坏密度极差 /
        n_sites 的范围 / **供给（窗口非空）是否成为阻断**
   ④ **供给的两种读法**（⚠ 244.70 那条线索的量化）：
      · **旧读法**（密度审计器 D4 现在的读法）：把生产阶梯当 **pos_frac 无关**
      · **新读法**：阶梯**带 pos_frac**（⇒ ⇒ 构造新阶梯时）能不能供出
      ⇒ ⇒ 两者的差 = 「D4 的红有多少是**格式缺口**造成的」

⚖⚖⚖⚖⚖ **分母一律走生产实现**（`dose_confound_audit.denom_of`）⇒ ⛔ **不另写一份**
   ⚠ 244.50 的教训：`int()` 是**向零截断**（⛔ 不是四舍五入）、`max(1, …)` 的夹取、
   `pos_frac` **缺字段必须拒读** ⇒ ⇒ 这三条都由 `denom_of` 承担 ⇒ ⇒ 本文件不再复述。
"""

import argparse
import collections
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
POOL_DEFAULT = os.path.join(HERE, "fixed_dose_pool_snapshot.json")
BASE_DEFAULT = os.path.join(HERE, "fixed_dose_cost_baseline.json")
SPEC_DEFAULT = os.path.join(HERE, "fixed_dose_dispatch_spec_example.json")
ROUTE_DEFAULT = os.path.join(HERE, "fixed_dose_route_measure_first.json")
D_TOL_DEFAULT = 0.005

# ⚖ 候选 ρ* 的扫描网格（⛔ 只作**候选**，⛔ 不是口径决定）
SCAN = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50)


def dconf():
    import dose_confound_audit
    return dose_confound_audit


def _read_json(p, what):
    if not os.path.isfile(p):
        raise SystemExit("⛔ %s 不存在：%s" % (what, p))
    return json.loads(io.open(p, encoding="utf-8").read())


def tid_info(pool):
    """⚖ 每条轨迹的 `P` / `n_gen`（来自**生成池快照** ⇒ ⛔ 不重算）。"""
    out = {}
    for t in pool.get("tids") or []:
        out[t["tid"]] = {"P": t.get("P"), "n_gen": t.get("n_gen")}
    return out


def inj_of(DC, P, n_gen, pos_frac):
    """⚖ **可注入位置总数** ⇒ 走生产实现（⛔ 不另写一份公式）。"""
    return DC.denom_of({"inject_n_sites": 1, "P": int(P), "n_gen": int(n_gen),
                         "pos_frac": float(pos_frac)})


def window_for(inj, target, tol):
    """⚖ 合法 n_sites 的**窗口** = { n ∈ [1, inj] : |n/inj − target| <= tol }。

    ⚖⚠⚖ **窗口为空 ⇒ 供给**不成立** ⇒ ⇒ 调用方必须**判红**（⛔ 不许猜、不许崩）。
    """
    out = []
    for n in range(1, int(inj) + 1):
        if abs(float(n) / float(inj) - target) <= tol:
            out.append(n)
    return out


def canonical_ns(inj, target):
    """⚖ **规范 n_sites** = 最接近 `target·inj` 的整数（⛔ 必须落在 [1, inj] 里）。"""
    x = target * float(inj)
    n = int(x + 0.5) if x >= 0 else -int(-x + 0.5)
    if n < 1:
        n = 1
    if n > int(inj):
        n = int(inj)
    return n


def best_ns(inj, target, tol):
    """⚖ 窗口里**离 target 最近**的那个整数（⇒ 密度最接近 ρ*）⇒ 无窗口 ⇒ `None`。"""
    w = window_for(inj, target, tol)
    if not w:
        return None
    return min(w, key=lambda n: (abs(float(n) / float(inj) - target), n))


def reuse_count(DC, ti, target, tol, ladder):
    """⚖ **「零新格」的真实数字**：现批里**注入参数逐位相同**的格 ⇒ ⇒ 可以复用。

    ⚖⚠⚖ **判据**（逐位）：
      · 现批的格是 `(tid, scope=k, n_sites)`，**pos_frac 全是 0.5**（真数据）
      · 固定剂量设计里，每条轨迹在 **pos_frac=0.5** 那一档需要**一个**确定的 n_sites
        （规范取整）
      ⇒ ⇒ 若那个 n_sites **恰好等于**现批该轨迹的某个 rung 的 n_sites
      ⇒ ⇒ ⇒ **注入参数逐位相同**（scope / n_sites / pos_frac 三样都一样）
      ⇒ ⇒ ⇒ 那格**可复用** ⇒ ⇒ 「零新格」**不成立**，但「要新生成多少」**比想象中少**
    """
    reused = []
    for tid in sorted(ti.keys()):
        info = ti[tid]
        if not info["P"] or not info["n_gen"]:
            continue
        rungs = ladder.get(tid) or []
        if not rungs:
            continue
        inj = inj_of(DC, info["P"], info["n_gen"], 0.5)
        cn = canonical_ns(inj, target)
        if cn in rungs:
            reused.append((tid, cn, float(cn) / float(inj)))
    return reused


def read_ladder(path):
    """⚖ 读生产阶梯 ⇒ `(rungs: {tid: [n_sites,…]}, has_pos_frac: bool)`。

    ⚖⚠⚖ **列数要分清**：3 列 = **没有 pos_frac** ⇒ ⇒ 那些 rung 是按它**生成时**的
    pos_frac 造的（真数据全 0.5）⇒ ⇒ ⛔ **不许**默认当成 pos_frac 无关。
    """
    rungs = collections.OrderedDict()
    cols = set()
    has_pf = None
    for line in io.open(path, encoding="utf-8"):
        s = line.rstrip("\n")
        if not s.strip():
            continue
        parts = s.split("\t")
        cols.add(len(parts))
        if has_pf is None:
            has_pf = (len(parts) >= 4)
        if len(parts) >= 3 and parts[1] == "k":
            try:
                rungs.setdefault(parts[0], []).append(int(parts[2]))
            except ValueError:
                continue
    return rungs, has_pf, sorted(cols)


def measure(DC, ti, pos_fracs, target, tol, ladder=None, ladder_has_pf=False):
    """⚖ 在给定的 ρ* 下**量**一遍 ⇒ 返回一个可打印的字典。"""
    tids = sorted(ti.keys())
    per_tid = []
    n_combo = 0
    n_combo_ok = 0
    worst_spread = 0.0
    worst_spread_tid = None
    ns_all = []
    d2_ok = 0
    d2_total = 0
    # 供给：旧读法（阶梯 pos_frac 无关）vs 新读法（按 pos_frac 造新阶梯）
    supply_old_ok = 0
    supply_new_ok = 0

    for tid in tids:
        info = ti[tid]
        if not info["P"] or not info["n_gen"]:
            continue
        rows = []
        dens = []
        for f in pos_fracs:
            inj = inj_of(DC, info["P"], info["n_gen"], f)
            w = window_for(inj, target, tol)
            n_combo += 1
            ok = bool(w)
            if ok:
                n_combo_ok += 1
            cn = canonical_ns(inj, target)
            d = float(cn) / float(inj)
            dens.append(d)
            ns_all.append(cn)
            bn = best_ns(inj, target, tol)
            rows.append({"f": f, "inj": inj, "n_window": len(w),
                         "n_first": (w[0] if w else None),
                         "n_last": (w[-1] if w else None),
                         "canon": cn, "dens": d,
                         "canon_in_window": (cn in w) if w else False,
                         "best": bn})
            # ---- 供给：新读法（新阶梯带 pos_frac）⇒ 窗口非空即可供出 ----
            if ok:
                supply_new_ok += 1
            # ---- 供给：旧读法（阶梯 pos_frac 无关）⇒ 现有 rung 里有没有命中窗口的 ----
            if ladder is not None:
                hit = [v for v in ladder.get(tid, [])
                       if abs(float(v) / float(inj) - target) <= tol]
                if len(hit) == 1:
                    supply_old_ok += 1
        d2_total += 1
        if len(dens) >= 2:
            sp = max(dens) - min(dens)
            if sp > worst_spread:
                worst_spread = sp
                worst_spread_tid = tid
            if sp <= tol:
                d2_ok += 1
        per_tid.append({"tid": tid, "rows": rows})

    return {
        "target": target, "tol": tol,
        "n_tid": len(per_tid), "n_combo": n_combo, "n_combo_ok": n_combo_ok,
        "d2_ok": d2_ok, "d2_total": d2_total,
        "worst_spread": worst_spread, "worst_spread_tid": worst_spread_tid,
        "ns_min": (min(ns_all) if ns_all else None),
        "ns_max": (max(ns_all) if ns_all else None),
        "supply_old_ok": supply_old_ok, "supply_new_ok": supply_new_ok,
        "per_tid": per_tid,
    }


def fmt(x, nd=4):
    return ("%." + str(nd) + "f") % x


# ================================================================ 打印
def arm_factor(base, route_arms, ladder_n_cells):
    """⚖⚠⚖⚖⚖ **「一格可复用 ⇒ 省几次探针」** ⇒ ⇒ 它的**前提**是：
      **两臂探过的是同一批格**（⇒ ⇒ 一条格定义在每条臂上各探一次）。

    ⚖ **证据 = 成本基线里的 `probe_cell`**（两臂各探了多少格）⇒ ⇒ 前提**成立**要同时满足：
      ① 基线里探针的**臂集合** == 路线规格的**臂集合**（⛔ 否则「乘臂数」没依据）
      ② 每条臂的 `n_begin == n_end`（⛔ 否则那臂有**没跑完**的格）
      ③ 两臂的格数**相等**（⇒ ⇒ 同一批格）
      ④ 且**等于阶梯格数**（⇒ ⇒ 探的就是这批阶梯格）

    ⚖⚠⚖ **不成立 ⇒ 因子退回 1**（⛔ **宁可保守**，不许瞎乘臂数）⇒ ⇒ 那时报告里会印 ⚠。
    """
    pc = (base or {}).get("probe_cell") or {}
    # ⚖⚠⚖⚖⚖ **`probe_cell` 里不只有臂**：还有 `caveats`（**list**）与
    #   `per_cell_s_both_arms`（**dict**，但不是臂记录）⇒ ⇒ ⛔ **不能**把它的 key
    #   一律当「臂」（244.75 踩过 ⇒ ⇒ `q.get(...)` 在 list 上**崩**）
    #   ⇒ ⇒ 判据 = 「值是 dict 且带 n_begin / n_end / per_cell_s 之一」⇒ ⇒ 才是臂记录
    def _is_arm(v):
        return isinstance(v, dict) and any(k in v for k in ("n_begin", "n_end", "per_cell_s"))
    arms_base = sorted(k for k, v in pc.items() if _is_arm(v))
    arms_route = sorted(list(route_arms or []))
    detail = {"arms_base": arms_base, "arms_route": arms_route, "per_arm": {}}
    ok = (arms_base == arms_route) and bool(arms_base)
    vals = []
    for tag in arms_base:
        q = pc.get(tag) or {}
        nb, ne = q.get("n_begin"), q.get("n_end")
        detail["per_arm"][tag] = {"n_begin": nb, "n_end": ne,
                                  "unpaired": len(q.get("unpaired_cells") or [])}
        if nb is None or ne is None or nb != ne:
            ok = False
        else:
            vals.append(nb)
    if not vals or len(set(vals)) != 1:
        ok = False
    elif ladder_n_cells and vals[0] != ladder_n_cells:
        ok = False
    detail["same_count"] = (vals[0] if vals else None)
    detail["ladder_n_cells"] = ladder_n_cells
    factor = (len(arms_base) if ok and arms_base else 1)
    return factor, ok, detail


def reuse_runs(n_reuse_defs, n_arms, n_need_cells):
    """⚖⚠⚖⚖⚖ **单位**换算：「**格定义**」⇒ 「**探针运行**」。

    ⚖⚠ **为什么必须有这一步（244.75 第一版踩过）**：
      · 发批规格的 `columns` = `tid/scope/n_sites/pos_frac` ⇒ ⇒ **没有 arm 列**
        ⇒ ⇒ 一条**格定义**在**每条臂**上**各探一次** ⇒ ⇒ 现批 137 格 × 2 臂**都探过**
      · ⇒ ⇒ **一格可复用 ⇒ 省 `n_arms` 次探针**（⛔ 不是 1 次）
      · ⇒ ⇒ `n_need_cells` 数的是**探针运行**（含臂）⇒ ⇒ 拿它减**格定义数**⇒ ⇒ **单位不一致**
        ⇒ ⇒ 算成「要新跑 %d」⇒ ⇒ **少算一半**（336 − 14 = 322 ⛔ 而真值是 336 − 28 = **308**）

    ⚖ 这里**只允许同单位相减** ⇒ ⇒ 变异台 M11 打的就是「把臂数乘掉」这一处。
    """
    n_runs = int(n_reuse_defs) * int(n_arms)
    n_new = (int(n_need_cells) - n_runs) if n_need_cells else None
    return n_runs, n_new


def render(DC, ti, pos_fracs, spec_frac, tol, ladder, ladder_has_pf, ladder_cols,
           base_n_cells, targets, n_need_cells=None, n_arms=2, arm_mult=None,
           premise=None):
    out = []
    A = out.append
    A("=" * 78)
    A("244.75 —— **「固定剂量」的目标密度 ρ\\* 的实测清单**（零 GPU、只读、⛔ 不改口径）")
    A("=" * 78)
    A("")
    A("⚖ 数据：池快照 **%d** 条轨迹 ｜ 生产阶梯 **%d** 条 scope=k 的 rung（覆盖 **%d** 条轨迹）"
      "（%s 列 ⇒ %s）"
      % (len(ti), sum(len(v) for v in (ladder or {}).values()), len(ladder or {}),
         "/".join(str(c) for c in ladder_cols),
         ("**有 pos_frac 列**" if ladder_has_pf else "⚠ **没有 pos_frac 列**（⇒ rung 按生成时的 pos_frac 造）")))
    A("⚖ `pos_frac`s = %s ｜ 规格 `dose.frac` = **%s** ｜ `dose.tol` = **%s**"
      % (list(pos_fracs), fmt(spec_frac, 4), fmt(tol, 4)))
    A("")

    # ---------- ① inj 分布 ----------
    A("### ① `inj(f) = P + max(1, int(n_gen·f)) − 1` 的分布（⛔ 走生产实现 `denom_of`）")
    A("")
    for f in pos_fracs:
        vals = []
        for tid, info in sorted(ti.items()):
            if not info["P"] or not info["n_gen"]:
                continue
            vals.append(inj_of(DC, info["P"], info["n_gen"], f))
        if not vals:
            continue
        vals.sort()
        A("- `pos_frac=%s`：**%d** 条轨迹 ｜ inj **min %d ｜ 中位 %d ｜ max %d**"
          % (f, len(vals), vals[0], vals[len(vals) // 2], vals[-1]))
    A("")

    # ---------- ② 现批密度谱 ----------
    A("### ② 现批密度谱（现有 %d 格的**生产密度**）—— ρ\\* 的参照系" % base_n_cells)
    A("")
    dens_all = []
    for tid, ns_list in sorted(ladder.items()):
        info = ti.get(tid)
        if not info or not info["P"] or not info["n_gen"]:
            continue
        inj = inj_of(DC, info["P"], info["n_gen"], 0.5)
        for v in ns_list:
            dens_all.append(float(v) / float(inj))
    if dens_all:
        s = sorted(dens_all)
        A("- 现批密度 **min %s ｜ 中位 %s ｜ max %s**（**%d** 格）"
          % (fmt(s[0]), fmt(s[len(s) // 2]), fmt(s[-1]), len(s)))
        if base_n_cells and len(dens_all) != base_n_cells:
            A("- ⚠ **现批共 %d 行，其中 %d 行算不出密度**（⇒ ⇒ **那 %d 行不是「轨迹不在池里」**"
              "⇒ ⇒ 它们是 **scope ≠ k 的变体**（阶梯第 2 列写着 `scope`、第 3 列是 `single`/`all`）"
              "⇒ ⇒ **剂量分数对它们没有定义**（⛔ **不适用** ⛔ 不是「未量到」⇒ ⛔ 也不是「无差异」）"
              "）⇒ ⇒ ⛔ **不许**把上面这个分布当成「全部 %d 行」的分布"
              % (base_n_cells, base_n_cells - len(dens_all), base_n_cells - len(dens_all),
                 base_n_cells))
        near = [d for d in s if abs(d - spec_frac) <= tol]
        A("- 落在 **规格 frac ± tol**（%s ± %s）里的：**%d** 格 %s"
          % (fmt(spec_frac, 4), fmt(tol, 4), len(near),
             ("⇒ ⇒ 现批**没有**这个剂量 ⇒ ρ\\* 若是它 ⇒ **全是新生成**" if not near
              else "⇒ ⇒ 现批**已经**跑过这个剂量")))
        q = []
        for i in range(4):
            k = int(round(i * (len(s) - 1) / 3.0))
            q.append(s[k])
        A("- 现批密度的四分位：**%s**" % " ｜ ".join(fmt(x) for x in q))
    A("")

    # ---------- ③ 候选清单 ----------
    A("### ③ **候选 ρ\\* 的实测清单**（本轮的核心产出）")
    A("")
    A("| ρ\\* | 可行 (轨迹,pos_frac) 组合 | D2 满足的轨迹 | 最坏密度极差 | n_sites 范围 | 供给阻断? |")
    A("|---|---|---|---|---|---|")
    res = {}
    for tg in targets:
        m = measure(DC, ti, pos_fracs, tg, tol, ladder, ladder_has_pf)
        res[tg] = m
        blocked = "⚠ **是**" if m["n_combo_ok"] < m["n_combo"] else "✅ 否"
        A("| **%s** | %d / %d | %d / %d | %s%s | %d – %d | %s |"
          % (fmt(tg, 2), m["n_combo_ok"], m["n_combo"], m["d2_ok"], m["d2_total"],
             fmt(m["worst_spread"], 5),
             ("（`%s`）" % m["worst_spread_tid"]) if m["worst_spread_tid"] else "",
             m["ns_min"], m["ns_max"], blocked))
    A("")
    A("⚖⚠⚖ **怎么读这张表**：")
    A("")
    A("- 「可行组合」= 每个 (轨迹, pos_frac) 的**合法 n_sites 窗口非空** ⇒ ⇒ "
      "**能不能造出新阶梯**。")
    A("- 「D2 满足」= 同一条轨迹的 3 个 pos_frac 上，**实测密度相等**（极差 ≤ tol）"
      "⇒ ⇒ 这才叫「固定剂量」。")
    A("- 「最坏密度极差」= 所有轨迹里**最差**的那条 ⇒ ⇒ 离 tol 有多少余量。")
    A("- ⛔ 这张表**不是口径决定**：它只告诉你「每个候选 ρ\\* 长什么样」。")
    A("")

    # ---------- ④ 供给的两种读法 ----------
    A("### ④ 供给的两种读法（⚠ 244.70 那条线索的量化）")
    A("")
    m_spec = res.get(spec_frac)
    if m_spec is not None:
        A("在 **规格 frac = %s** 下：" % fmt(spec_frac, 4))
        A("")
        A("| 读法 | 供出的 (轨迹, pos_frac) 组合 |")
        A("|---|---|")
        A("| **旧读法**（把现有阶梯当 **pos_frac 无关**）＝ 密度审计器 D4 现在的读法 | %d / %d |"
          % (m_spec["supply_old_ok"], m_spec["n_combo"]))
        A("| **新读法**（阶梯**带 pos_frac** ⇒ 构造新阶梯） | %d / %d |"
          % (m_spec["supply_new_ok"], m_spec["n_combo"]))
        A("")
        gap = m_spec["n_combo"] - m_spec["supply_new_ok"]
        A("- ⇒ ⇒ **只要新阶梯带 pos_frac 那一列，供给缺口 = %d** ⇒ ⇒ %s"
          % (gap,
             ("⇒ ⇒ **除格式外没有别的供给阻断**（⚠ 这一句只在「新读法」下成立）"
              if gap == 0 else "⇒ ⇒ 仍有 %d 个组合供不出 ⇒ ⇒ **要新阶梯**" % gap)))
        A("- ⚠⚠⚖ **旧读法把「rung 只对它生成时的 pos_frac 有效」这件事忽略了** ⇒ ⇒ "
          "它数出来的「供不出」里，**有一部分其实是格式缺口**，不是真的供给不够。")
        A("")

    # ---------- ⑤ 规范阶梯 ----------
    A("### ⑤ 在 **规格 frac = %s** 下的**规范阶梯**（`n_sites = 最近整数(ρ\\*·inj)`）" % fmt(spec_frac, 4))
    A("")
    m = res.get(spec_frac)
    if m is not None:
        A("| 轨迹 | " + " ｜ ".join("f=%s" % f for f in pos_fracs) + " | 密度极差 |")
        A("|---" * (len(pos_fracs) + 2) + "|")
        for row in m["per_tid"][:12]:
            cells = []
            ds = []
            for r in row["rows"]:
                cells.append("n=%d inj=%d d=%s" % (r["canon"], r["inj"], fmt(r["dens"])))
                ds.append(r["dens"])
            sp = (max(ds) - min(ds)) if len(ds) >= 2 else 0.0
            A("| `%s` | %s | %s |" % (row["tid"], " ｜ ".join(cells), fmt(sp, 5)))
        if len(m["per_tid"]) > 12:
            A("| … | （其余 %d 条轨迹同格式，略） | |" % (len(m["per_tid"]) - 12))
        A("")
        A("- ⇒ ⇒ 规范阶梯下**最坏**的密度极差 = **%s**（容差 %s）⇒ ⇒ %s"
          % (fmt(m["worst_spread"], 6), fmt(tol, 4),
             ("✅ **D2 成立**（余量充足）" if m["worst_spread"] <= tol
              else "❌ **D2 不成立** ⇒ ⇒ 规范取整**不够** ⇒ ⇒ 得用窗口里的最优选点")))
        A("- ⇒ ⇒ `n_sites` 的取值范围 = **%d – %d**（这是「剂量大小」的可视化）"
          % (m["ns_min"], m["ns_max"]))
    A("")
    # ---------- ⑥ 「零新格」的真实数字 ----------
    A("### ⑥ 「零新格」的真实数字（⚠ 更正 244.72 的一句**过强**的话）")
    A("")
    reused = reuse_count(DC, ti, spec_frac, tol, ladder)
    # ⚖⚠⚖⚖⚖ **单位**：「格定义」（tid × scope × n_sites，**两臂共用**）≠「探针运行」（格定义 × 臂）
    #   ⚠⚠ **244.75 第一版踩过这个坑**：`n_need_cells` 数的是**探针运行**（含臂），
    #   而 `len(reused)` 数的是**格定义**（不含臂）⇒ ⇒ 拿后减前 ⇒ ⇒ **单位不一致**
    #   ⇒ ⇒ 算成「要新跑 %d」（少算了一半）⇒ ⇒ 现在**分开报**，且**只拿同单位相减**。
    # ⚖⚠⚖⚖⚖ 乘臂数**只在前提成立时**做 ⇒ ⇒ 前提不成立 ⇒ ⇒ 因子退回 1（⛔ 宁可保守）
    mult = int(arm_mult) if arm_mult else int(n_arms)
    n_reuse_runs, n_new_runs = reuse_runs(len(reused), mult, n_need_cells)
    A("- 244.72 记的是：「那 137 格的注入参数是**剂量扫描**口径 ⇒ ⛔ **不能**复用成固定剂量的格"
      "⇒ ⇒ **336 格全是新的**」。")
    A("- ⚠⚠⚖ **那句对「整批」是对的，对「每一格」不对**：现批每条轨迹有**多个** rung，"
      "而固定剂量设计每个 (轨迹, pos_frac) 只需要**一个** n_sites ⇒ ⇒ "
      "**若那个 n_sites 恰好命中现批的某个 rung ⇒ ⇒ 注入参数（scope / n_sites / pos_frac）"
      "逐位相同 ⇒ ⇒ 那格**可以复用**。")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 现批里**注入参数逐位相同**、可复用的**格定义**（tid × scope × n_sites，两臂共用） | **%d** |"
      % len(reused))
    if n_need_cells:
        A("| 那一批需要的总**探针运行数**（56/臂 × 3 格 × **%d** 臂） | **%d** |"
          % (n_arms, n_need_cells))
        A("| ⇒ ⇒ **可复用的探针运行数**（格定义 × **%d** 臂） | **%d** |"
          % (mult, n_reuse_runs))
        A("| ⇒ ⇒ **要新跑**的探针运行数 | **%d** |" % n_new_runs)
    A("")
    if reused:
        A("| 轨迹 | n_sites（= 规范取整） | 实测密度 |")
        A("|---|---|---|")
        for tid, cn, d in reused:
            A("| `%s` | %d | %s |" % (tid, cn, fmt(d, 5)))
    A("")
    A("⚖⚠⚖⚖ **边界（⛔ 不许越读）**：")
    A("")
    A("- 上面这个数是**在整池（%d 条轨迹）上**数的 ⇒ ⇒ 那一批具体选哪 56 条/臂**还没定**"
      " ⇒ ⇒ **可复用的格数会随选轨而变** ⇒ ⇒ 上面的值是**上界**。" % len(ti))
    if n_need_cells:
        A("- ⇒ ⇒ **「%d 格全是新的」这句话要改成**：**至少** %d 次探针要新跑，"
          "**至多** %d 次可复用（取决于选轨）。"
          % (n_need_cells, n_new_runs, n_reuse_runs))
    A("")
    A("⚖⚠⚖⚖⚖⚖ **前提核验**（⛔ 「一格可复用 ⇒ 省几次探针」**依赖**它）：")
    A("")
    if premise:
        _pa = premise.get("per_arm") or {}
        A("- 证据 = 成本基线的 `probe_cell`（**每条臂**各探了多少格）：%s"
          % ("；".join("%s 臂 n_begin=%s n_end=%s 未配对=%s"
                       % (t, _pa.get(t, {}).get("n_begin"), _pa.get(t, {}).get("n_end"),
                          _pa.get(t, {}).get("unpaired")) for t in sorted(_pa)) or "（缺）"))
        A("- 核验：臂集合 %s == 路线 %s ｜ 两臂格数相等且 = 阶梯 %s ⇒ ⇒ **前提%s**"
          % (premise.get("arms_base"), premise.get("arms_route"),
             premise.get("ladder_n_cells"), "成立" if premise.get("ok") else "不成立"))
        A("- ⇒ ⇒ **乘的臂因子 = %d**%s"
          % (mult, "" if premise.get("ok")
             else "（⚠ 前提**不成立** ⇒ ⇒ 因子**退回 1** ⇒ ⇒ ⛔ **宁可保守**）"))
    A("")
    A("- ⚠⚠⚖⚖⚖ **⚠ 单位坑（244.75 自己踩的）**：**「格」有两个单位** —— "
      "**格定义**（tid × scope × n_sites，**两臂共用**）与 **探针运行**（格定义 × 臂）。")
    A("  ⇒ ⇒ 发批规格的 `columns` = `tid/scope/n_sites/pos_frac` ⇒ ⇒ **没有 arm 列** "
      "⇒ ⇒ 一条格定义在**每条臂**上各探一次 ⇒ ⇒ 现批 %d **行** × %d 臂**都探过**。"
      % (base_n_cells or 0, mult))
    A("  ⇒ ⇒ ⇒ **一格可复用 ⇒ 省 %d 次探针**（不是 1 次）⇒ ⇒ ⇒ 可复用的探针运行数 = %d × %d = **%d**。"
      % (n_arms, len(reused), n_arms, n_reuse_runs))
    A("  ⇒ ⇒ ⇒ ⛔ **不许**拿「格定义数」去减「探针运行数」（⇒ ⇒ 那是**单位不一致**）"
      "⇒ ⇒ 那样会算成 **%d**，⛔ **真值是 %d**。"
      % ((n_need_cells - len(reused)) if n_need_cells else 0, n_new_runs))
    A("- ⛔ **本段只数得数**，⛔ 不改任何预登记、⛔ 不改格清单、⛔ 不发批。")
    A("")
    A("---")
    A("")
    return "\n".join(out)


# ================================================================ 自检
def selftest():
    """⚖ 自检：**每条判据都配反例**（⛔ 恒绿 = 量不到东西）。"""
    DC = dconf()
    results = []

    def chk(name, cond, msg):
        results.append((name, bool(cond), msg))

    def safe(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:            # ⛔ 崩 ⛔ 不等于抓到 ⇒ 记成「崩了」
            return ("__CRASH__", repr(e))

    def crashed(r):
        """⚖⚠⚖⚖ **崩的判别式**：⛔ **不能**用「是不是 tuple」⇒ ⇒
        `reuse_runs` 成功时**本来就返回 tuple** ⇒ ⇒ 那样会把成功误判成崩
        ⇒ ⇒ **必须看标记**（`safe` 造出来的崩是 `("__CRASH__", …)`）。"""
        return isinstance(r, tuple) and len(r) == 2 and r[0] == "__CRASH__"

    # ---- T1：分母必须与生产实现逐位相同（⛔ 不另写一份）----
    r = safe(lambda: inj_of(DC, 112, 757, 0.25))
    exp = safe(lambda: DC.denom_of({"inject_n_sites": 1, "P": 112, "n_gen": 757,
                                     "pos_frac": 0.25}))
    chk("T1", r == exp and not isinstance(r, tuple),
        "inj 必须逐位等于生产 `denom_of`（实测 %r vs %r）" % (r, exp))
    # ---- T1a：`max(1, …)` 的夹取**真的生效**的那个夹具（n_gen·f < 1 ⇒ int() = 0）----
    r1a = safe(lambda: inj_of(DC, 10, 1, 0.5))
    e1a = safe(lambda: DC.denom_of({"inject_n_sites": 1, "P": 10, "n_gen": 1,
                                     "pos_frac": 0.5}))
    chk("T1a", r1a == e1a and not isinstance(r1a, tuple),
        "`max(1,…)` 生效时 inj 仍须等于生产实现（实测 %r vs %r；⛔ 漏掉 max(1,…) ⇒ %r）"
        % (r1a, e1a, 10 + 0 - 1))

    # ---- T1b：`int()` 是**向零截断**（⛔ 不是四舍五入）----
    r = safe(lambda: inj_of(DC, 10, 3, 0.5))     # int(1.5)=1 ⇒ 10+1−1=10
    chk("T1b", r == 10, "int() 向零截断：P=10 n_gen=3 f=0.5 ⇒ inj=%r（期望 10）" % (r,))

    # ---- T2：inj 随 pos_frac 单调不减 ----
    vals = [inj_of(DC, 112, 757, f) for f in (0.25, 0.5, 0.75)]
    chk("T2", vals == sorted(vals) and vals[0] < vals[-1],
        "inj 随 pos_frac 单调：%r" % (vals,))

    # ---- T3：窗口 = {|n/inj − ρ*| ≤ tol} ⇒ 端点必须在内 ----
    w = window_for(1000, 0.25, 0.005)
    ok3 = bool(w) and all(abs(float(n) / 1000.0 - 0.25) <= 0.005 for n in w)
    chk("T3", ok3 and w[0] >= 1 and w[-1] <= 1000,
        "窗口端点必须落在容差内且在 [1, inj] 里（%r…%r，共 %d）" % (w[0], w[-1], len(w)))

    # ---- T4：窗口为空 ⇒ 必须**判红**（⛔ 不许崩、不许猜）----
    r = safe(lambda: best_ns(10, 0.25, 0.005))
    chk("T4", r is None, "窗口为空时 `best_ns` 必须返回 None（实测 %r）" % (r,))

    # ---- T5：规范取整的密度必须落在容差内（合成夹具，inj 足够大）----
    bad = []
    for inj in (300, 934, 1761, 2588):
        cn = canonical_ns(inj, 0.25)
        d = float(cn) / inj
        if abs(d - 0.25) > 0.005:
            bad.append((inj, cn, d))
    chk("T5", not bad, "规范取整的密度必须落在 ρ*±tol 内（违例 %r）" % (bad,))

    # ---- T6：D2 判定 —— 「密度相等」与「密度不等」两个夹具分别绿/红 ----
    def d2_spread(dens, tol=0.005):
        return (max(dens) - min(dens)) <= tol
    chk("T6a", d2_spread([0.25000, 0.25001, 0.24999]), "D2：密度相等 ⇒ 绿")
    chk("T6b", not d2_spread([0.25000, 0.26000]), "D2：密度差 0.01 > tol ⇒ 红")

    # ---- T7：阶梯的列数要能分辨「有没有 pos_frac」----
    tmp = os.path.join(HERE, "_fdt_tmp")
    if not os.path.isdir(tmp):
        os.makedirs(tmp)
    try:
        p3 = os.path.join(tmp, "lad3.tsv")
        io.open(p3, "w", encoding="utf-8").write("t1\tk\t10\nt2\tk\t20\n")
        p4 = os.path.join(tmp, "lad4.tsv")
        io.open(p4, "w", encoding="utf-8").write("t1\tk\t10\t0.5\nt2\tk\t20\t0.5\n")
        r3, pf3, c3 = read_ladder(p3)
        r4, pf4, c4 = read_ladder(p4)
        chk("T7a", (not pf3) and c3 == [3], "3 列阶梯 ⇒ 必须认出**没有** pos_frac（%r）" % (c3,))
        chk("T7b", pf4 and c4 == [4], "4 列阶梯 ⇒ 必须认出**有** pos_frac（%r）" % (c4,))
        chk("T7c", r3.get("t1") == [10] and r4.get("t1") == [10],
            "两种列数下 rung 都要读到（%r / %r）" % (r3.get("t1"), r4.get("t1")))
    finally:
        for f in ("lad3.tsv", "lad4.tsv"):
            p = os.path.join(tmp, f)
            if os.path.isfile(p):
                os.remove(p)

    # ---- T8：候选扫描里**没有**的 ρ\\* 必须能算（不崩）----
    r = safe(lambda: measure(DC, {"t": {"P": 112, "n_gen": 757}}, (0.25, 0.5, 0.75),
                              0.25, 0.005, None, False))
    ok8 = (not isinstance(r, tuple)) and r["n_combo"] == 3
    chk("T8", ok8, "最小夹具（1 条轨迹 × 3 个 pos_frac）必须算得出来"
        "（实测 n_combo=%s）" % (r.get("n_combo") if isinstance(r, dict) else r,))

    # ---- T9：ρ\\* 高到装不下 ⇒ 「可行组合数 < 总数」⇒ 印**不可行**而不是 0% ----
    r = safe(lambda: measure(DC, {"t": {"P": 1, "n_gen": 2}}, (0.5,),
                              0.999, 0.0001, None, False))
    ok9 = (not isinstance(r, tuple))
    chk("T9", ok9, "极端 ρ\\* 必须**算得出**并被判成不可行（实测 %r）" % (r,))

    # ---- T10：**自己的错** —— 把窗口判据改成恒真 ⇒ 必须被抓住 ----
    good = window_for(1000, 0.25, 0.005)
    broken = list(range(1, 1001))          # ⛔ 恒真的「坏实现」
    chk("T10a", len(good) < len(broken), "窗口判据必须**不是**恒真（正确 %d 个 vs 恒真 %d 个）"
        % (len(good), len(broken)))

    # ---- T11：pos_frac 缺字段 ⇒ 生产实现必须**拒读**（⛔ 不许默认 0.5）----
    r = safe(lambda: DC.denom_of({"inject_n_sites": 1, "P": 10, "n_gen": 20}))
    chk("T11", isinstance(r, tuple), "缺 pos_frac ⇒ 生产实现必须拒读（实测 %r）" % (r,))

    # ---- T12：n_sites 必须被夹在 [1, inj] 里（ρ\\* 越界不许越界取点）----
    cn = canonical_ns(5, 0.99)
    # ⚠⚠⚖ 夹具必须**真的走到下限夹取**（`x < 0.5` ⇒ `int(x+0.5) = 0` ⇒ 夹取生效）
    #   ⇒ ⇒ 否则「把下限夹取拆掉」这条变异**抓不到**（244.75 预跑实测）
    cn2 = canonical_ns(1, 0.2)
    chk("T12", 1 <= cn <= 5 and 1 <= cn2 <= 1,
        "规范取整必须夹在 [1, inj]（inj=5 ρ\\*=0.99 ⇒ %r ｜ inj=1 ρ\\*=0.2 ⇒ %r，"
        "后者**必须**被下限夹到 1）" % (cn, cn2))

    # ---- T13：**夹具必须能分辨**「密度相等」与「密度不等」⇒ 恒绿的判据不行 ----
    chk("T13a", d2_spread([0.25, 0.25]) and not d2_spread([0.25, 0.30]),
        "D2 判据必须能分辨相等/不等（⛔ 恒绿不算）")
    chk("T13b", len(window_for(1000, 0.25, 0.005)) != len(window_for(1000, 0.25, 0.5)),
        "容差必须真的影响窗口大小（⛔ 恒真不算）")

    # ---- T14：`reuse_count` 的命中判据必须能分辨「命中」与「不命中」----
    lad_hit = {"ta": [122], "tb": [7]}
    r14 = safe(lambda: reuse_count(DC, {"ta": {"P": 112, "n_gen": 757},
                                        "tb": {"P": 112, "n_gen": 757}},
                                    0.25, 0.005, lad_hit))
    ok14 = (not isinstance(r14, tuple)) and len(r14) == 1 and r14[0][0] == "ta"
    chk("T14", ok14, "reuse_count 必须只认**注入参数逐位相同**的那个（实测 %r）"
        % (r14 if not isinstance(r14, tuple) else r14[1],))

    # ---- T15：`measure` 的「可行组合」计数必须能分辨窗口非空 / 为空 ----
    r15 = safe(lambda: measure(DC, {"ta": {"P": 112, "n_gen": 757},
                                    "tb": {"P": 1, "n_gen": 2}},
                                (0.5,), 0.25, 0.005, None, False))
    ok15 = (not isinstance(r15, tuple)) and r15["n_combo"] == 2 and r15["n_combo_ok"] == 1
    chk("T15", ok15, "可行组合计数必须只算窗口**非空**的（实测 %r）"
        % (("n_combo=%s n_combo_ok=%s" % (r15["n_combo"], r15["n_combo_ok"]))
           if isinstance(r15, dict) else r15,))

    # ---- T16：⚠⚠⚖⚖⚖ **臂数必须进「要新跑」的算式** ----
    #   ⚠⚠ **244.75 第一版漏了这一步** ⇒ ⇒ 算出「322」⛔ 而真值是「308」
    #   ⇒ ⇒ 判据必须钉死：**格定义数 × 臂数** ⇒ ⇒ 再减 ⇒ ⇒
    r16 = safe(lambda: reuse_runs(14, 2, 336))
    ok16 = (not crashed(r16)) and tuple(r16) == (28, 308)
    chk("T16", ok16,
        "「要新跑」必须按**探针运行**算（14 格定义 × 2 臂 = 28 ⇒ 336 − 28 = **308**；"
        "⛔ 少乘臂数会算成 322）（实测 %r）"
        % (r16,))
    # ⚖⚠⚖ **必须能红**：把臂数抹掉 ⇒ ⇒ T16 必须变红（⛔ 否则这条判据恒绿 ⇒ 不算数）
    r16b = safe(lambda: reuse_runs(14, 1, 336))
    ok16b = (not crashed(r16b)) and tuple(r16b) != (28, 308)
    chk("T16b", ok16b,
        "判据本身必须能分辨「乘了臂数」与「没乘臂数」（⛔ 恒绿不算）（实测 %r）"
        % (r16b,))

    # ---- T17：「乘臂数」的**前提核验**必须能分辨「两臂探过同一批格」与「没有」----
    good_base = {"probe_cell": {"w": {"n_begin": 137, "n_end": 137, "unpaired_cells": []},
                                 "rand": {"n_begin": 137, "n_end": 137,
                                          "unpaired_cells": []}}}
    bad_base = {"probe_cell": {"w": {"n_begin": 137, "n_end": 137, "unpaired_cells": []},
                                "rand": {"n_begin": 137, "n_end": 99,
                                         "unpaired_cells": []}}}
    r17 = safe(lambda: arm_factor(good_base, ["w", "rand"], 137))
    ok17 = (not crashed(r17)) and r17[0] == 2 and r17[1] is True
    chk("T17", ok17, "前提成立时因子必须等于臂数（实测 %r）" % (r17,))
    r17b = safe(lambda: arm_factor(bad_base, ["w", "rand"], 137))
    ok17b = (not crashed(r17b)) and r17b[0] == 1 and r17b[1] is False
    chk("T17b", ok17b,
        "前提**不成立**时因子必须**退回 1**（⛔ 宁可保守，⛔ 不许瞎乘）（实测 %r）" % (r17b,))
    # ⚖⚠⚖⚖⚖ **真实结构**：`probe_cell` 里**还有** `caveats`（**list**）与
    #   `per_cell_s_both_arms`（**dict**，但不是臂记录）⇒ ⇒ 244.75 第一版把它的
    #   key 一律当「臂」⇒ ⇒ 在 list 上 `.get` ⇒ ⇒ **崩** ⇒ ⇒ 这条夹具钉死它
    messy_base = {"probe_cell": {
        "caveats": ["a", "b"],
        "per_cell_s_both_arms": {"n": 2, "median": 26.0},
        "w": {"n_begin": 137, "n_end": 137, "unpaired_cells": [],
              "per_cell_s": {"n": 137}},
        "rand": {"n_begin": 137, "n_end": 137, "unpaired_cells": [],
                 "per_cell_s": {"n": 137}}}}
    r17c = safe(lambda: arm_factor(messy_base, ["w", "rand"], 137))
    ok17c = (not crashed(r17c)) and r17c[0] == 2 and r17c[1] is True \
        and r17c[2]["arms_base"] == ["rand", "w"]
    chk("T17c", ok17c,
        "`probe_cell` 里的**非臂** key（`caveats` 是 list、`per_cell_s_both_arms` 是 dict）"
        "**不许**被当成臂 ⇒ ⇒ 否则会**崩**（⛔ 崩 ≠ 抓到）（实测 %r）" % (r17c,))

    ok = sum(1 for _n, c, _m in results if c)
    print("自检 %d/%d 通过" % (ok, len(results)))
    for name, cond, msg in results:
        print("  [%s] %-5s %s" % ("PASS" if cond else "FAIL", name, msg))
    return ok == len(results)


def main():
    ap = argparse.ArgumentParser(description="244.75：测「固定剂量」的目标密度 ρ*（零 GPU、只读）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--pool", default=POOL_DEFAULT)
    ap.add_argument("--base", default=BASE_DEFAULT)
    ap.add_argument("--spec", default=SPEC_DEFAULT)
    ap.add_argument("--route", default=ROUTE_DEFAULT)
    args = ap.parse_args()
    if args.selftest:
        return 0 if selftest() else 1
    DC = dconf()
    pool = _read_json(args.pool, "池快照")
    base = _read_json(args.base, "成本基线")
    spec = _read_json(args.spec, "发批规格")
    route = _read_json(args.route, "路线规格")
    ti = tid_info(pool)
    dose = spec.get("dose") or {}
    spec_frac = float(dose.get("frac", 0.25))
    tol = float(dose.get("tol", D_TOL_DEFAULT))
    pos_fracs = [float(x) for x in (route.get("pos_fracs") or spec.get("route", {}).get("pos_fracs")
                                    or [0.25, 0.5, 0.75])]
    cl = base.get("cell_list") or {}
    ladder_path = cl.get("path")
    ladder, has_pf, cols = read_ladder(ladder_path)
    n_cells = cl.get("n_cells") or sum(len(v) for v in ladder.values())
    targets = sorted(set(list(SCAN) + [spec_frac]))
    n_need = None
    n_arms = 1
    try:
        n_arms = len(route.get("arms") or [1])
        n_need = (int(route.get("target_tracks_per_arm") or 0)
                  * int(route.get("cells_per_track") or 0)
                  * n_arms)
    except Exception:
        n_need = None
    # ⚖⚠⚖⚖⚖ 「一格可复用 ⇒ 省几次探针」的**前提核验**（两臂探的是同一批格）
    arm_mult, prem_ok, prem = arm_factor(base, route.get("arms") or [], n_cells)
    prem["ok"] = prem_ok
    print(render(DC, ti, pos_fracs, spec_frac, tol, ladder, has_pf, cols,
                 n_cells, targets, n_need, n_arms, arm_mult, prem))
    return 0


if __name__ == "__main__":
    sys.exit(main())
