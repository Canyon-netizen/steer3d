#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""fixed_dose_cells.py —— 244.76：**生成**「固定剂量」那一批的 4 列格清单（零 GPU、只读输入）

⚖⚖⚖⚖⚖ **这一轮只生成清单**：⛔ 不跑批、⛔ 不改探针、⛔ 不发批、⛔ 不改生产脚本。
⚖⚖⚖⚖⚖ **只读**：本文件只读**池快照** / **规格** / **路线** ⇒ ⇒ 不写任何产品文件
   （除非显式给 `--out` ⇒ 那只写**清单**本身）。

🔴 **为什么必须有这个工具**（244.72 的缺口）：
   现有那份生产阶梯 `warm_cells.txt`（137 行 / 3 列）是**一次性**从上一轮的 status 文件
   **机器解析**出来的 ⇒ ⇒ 固定剂量批**不能沿用这条路**（⛔ 它的 n_sites 是「阶梯上独立的一档」
   ⇒ ⇒ 同一个 n_sites 跨 `pos_frac` ⇒ **剂量差 2.77 倍** ⇒ ⇒ 那正是 244.72 查出的**断层**）
   ⇒ ⇒ 固定剂量的清单必须**从池快照 + ρ\* 现算**。

⚖⚖⚖⚖⚖ **输出格式（格式的**第二个**维度也不许忘）**：
   `tid` / `scope` / `n_sites` / `pos_frac` **4 列 ＋ 一行表头**
   ⇒ ⇒ 分析侧（`read_cells`）**要**表头；生产跑批脚本**不要**表头（它把每行都当一格）
   ⇒ ⇒ **runner 必须显式跳/验表头**（⛔ 否则会去探一格假格 `tid/scope/n_sites`）

⚖⚖⚖⚖⚖ **口径各归其位（⛔ 不许代码里写死）**：
   · **目标密度 ρ\* / 容差 tol / 注入 scope** ⇒ **规格** `dose.frac` / `dose.tol` / `dose.scope`
   · **pos_frac 三档 / 规模（56 条/臂、28 块、3 格/条）** ⇒ **路线** `pos_fracs` / …
   · **档数 / 档边界 / 分位点算法 / 零跨度** ⇒ **预登记**（分析口径，本工具不用）
   · **选轨规则** ⇒ 变体预登记 §6（S1–S4）：**按 `tid` 字典序取前 N 条**（中性、确定性）
   · **分母（inj）** ⇒ **生产实现** `dose_confound_audit.denom_of`（⛔ 不另写一份公式）
"""

import argparse
import collections
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

POOL_DEFAULT = os.path.join(HERE, "fixed_dose_pool_snapshot.json")
SPEC_DEFAULT = os.path.join(HERE, "fixed_dose_dispatch_spec_example.json")
ROUTE_DEFAULT = os.path.join(HERE, "fixed_dose_route_measure_first.json")

# ⚖⚖⚖ 清单的**列**（⛔ 独立字面量 ⇒ 期望集不许从被检对象派生）
CELLS_COLUMNS = ("tid", "scope", "n_sites", "pos_frac")

# ⚖⚖⚖ **路线里属于「口径」的那几个键**（规格里内嵌了一份副本 ⇒ 两处必须逐字一致）
ROUTE_CONVENTION_KEYS = ("pos_fracs", "n_blocks", "cells_per_track",
                         "target_tracks_per_arm", "arms")

# ⚖⚖⚖ 一个**块** = `think` + `no_think` **两条**轨迹（变体预登记 §6 的 S1）
#   ⇒ 块数 × 2 = 轨迹数 ⇒ ⇒ 这条是**结构性事实**，⛔ 不是口径取值
TRACKS_PER_BLOCK = 2

# ⚖⚖⚖ 244.75 **登记值**（独立字面量 ⇒ 用来对账「复用数 / 要新跑多少次」）
#   · 现有批探过 **14 条轨迹**（7 块 × 2）
#   · 两臂都探过 ⇒ 复用 **28 次探针**
#   · 固定剂量这一批 = 168 格 × 2 臂 = **336 次探针** ⇒ ⇒ 要新跑 **308 次**
REUSE_TRACKS_REGISTERED = 14
REUSE_RUNS_REGISTERED = 28
PROBE_RUNS_REGISTERED = 336
NEW_RUNS_REGISTERED = 308
# ⚖ 变体预登记 §7 登记的格数（56 轨迹 × 3 个 `pos_frac`）
CELLS_REGISTERED = 168


class HardFail(Exception):
    pass


def dconf():
    import dose_confound_audit
    return dose_confound_audit


def fdf():
    import fixed_dose_feasible
    return fixed_dose_feasible


def _read_json(path, what):
    if not os.path.isfile(path):
        raise HardFail("⛔ %s 不存在：%s" % (what, path))
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 读输入
def read_spec(path):
    """⚖ **规格** = ρ\* / tol / scope / 列声明 的真源（⛔ 不许代码里写死）。"""
    sp = _read_json(path, "发批规格")
    dose = sp.get("dose") or {}
    for k in ("frac", "tol", "scope"):
        if dose.get(k) is None:
            raise HardFail("⛔ 规格缺 `dose.%s`（⛔ 不许默认值兜底）" % k)
    return {
        "spec_id": sp.get("spec_id", "（未命名）"),
        "frac": float(dose["frac"]),
        "tol": float(dose["tol"]),
        "scope": str(dose["scope"]),
        "columns": [str(c) for c in (sp.get("columns") or CELLS_COLUMNS)],
        "route_embedded": sp.get("route") or {},
    }


def read_route(path):
    """⚖ **路线** = pos_frac 三档 / 规模 的真源。"""
    rt = _read_json(path, "路线规格")
    for k in ("pos_fracs", "cells_per_track", "target_tracks_per_arm"):
        if rt.get(k) is None:
            raise HardFail("⛔ 路线缺 `%s`（⛔ 不许默认值兜底）" % k)
    return {
        "route_id": rt.get("route_id", "（未命名）"),
        "pos_fracs": [float(x) for x in rt["pos_fracs"]],
        "cells_per_track": int(rt["cells_per_track"]),
        "target_tracks_per_arm": int(rt["target_tracks_per_arm"]),
        "n_blocks": int(rt.get("n_blocks") or 0),
        "arms": list(rt.get("arms") or []),
    }


def check_route_consistency(spec, route):
    """⚖⚖⚖ **规格里内嵌的 route 副本**必须与**路线文件**逐字一致（口径键）。

    ⚖⚠⚖ 那是「**两处各写一份**」的经典坑（规格内嵌一份、路线文件一份）
    ⇒ ⇒ 两处漂了 ⇒ 发出去的批次与算出来的批次**不是同一批** ⇒ ⇒ 必须**判红**。
    ⛔ 只比**口径键**；`premises` 是散文，不参与。
    """
    emb = spec.get("route_embedded") or {}
    diffs = []
    for k in ROUTE_CONVENTION_KEYS:
        if k not in emb:
            diffs.append("%s：规格内嵌里**没有**" % k)
            continue
        a, b = emb[k], (route.get(k) if k in route else None)
        if k == "pos_fracs":
            a = [float(x) for x in a]
            b = [float(x) for x in (b or [])]
        elif k in ("n_blocks", "cells_per_track", "target_tracks_per_arm"):
            a, b = int(a), int(b)
        elif k == "arms":
            a, b = list(a), list(b)
        if a != b:
            diffs.append("%s：规格 **%r** vs 路线 **%r**" % (k, a, b))
    return diffs


# ---------------------------------------------------------------- 选轨
def select_tracks(tids, n_tracks):
    """⚖⚖⚖ **选轨规则**（变体预登记 §6 的 S1–S3）：按 `tid` **字典序**取前 N 条。

    ⚖⚖⚖ **为什么是字典序**：⛔ 不用 `n_eff`、不用字节数、不用任何**与结果相关**的量
       ⇒ ⇒ 中性 ⇒ ⇒ 事后不可挑。
    ⚖⚖ **已知的后果**（不是理由）：已探过的 7 个块**恰好**全落在前 28 块里
       ⇒ ⇒ 复用 14 条轨迹 ⇒ ⇒ 336 − 28 = **308** 次要新跑（与 244.75 登记值**逐位一致**）。
       ⚠ 但「复用最多」**没量过** ⇒ ⇒ ⛔ **不许**把它当理由。
    """
    ordered = sorted(tids)
    if n_tracks > len(ordered):
        raise HardFail("⛔ 要 %d 条轨迹，池子里只有 %d 条 ⇒ 供给不成立（⛔ 不许截断）"
                       % (n_tracks, len(ordered)))
    return ordered[:n_tracks]


# ---------------------------------------------------------------- 剂量
def inj_of(DC, P, n_gen, pos_frac):
    """⚖ **可注入位置总数** ⇒ 走**生产实现** `denom_of`（⛔ 不另写一份公式）。"""
    return DC.denom_of({"inject_n_sites": 1, "P": int(P), "n_gen": int(n_gen),
                         "pos_frac": float(pos_frac)})


def canonical_ns(inj, target):
    """⚖ **规范 n_sites** = 最接近 `target·inj` 的整数（⛔ 必须夹在 `[1, inj]` 里）。"""
    x = target * float(inj)
    n = int(x + 0.5) if x >= 0 else -int(-x + 0.5)
    if n < 1:
        n = 1
    if n > int(inj):
        n = int(inj)
    return n


def density_of(DC, n_sites, P, n_gen, pos_frac):
    """⚖ **生产剂量分数** ⇒ 走**生产机械** `frac_of`（⛔ 不另写一份）。"""
    return DC.frac_of({"inject_n_sites": int(n_sites), "P": int(P),
                        "n_gen": int(n_gen), "pos_frac": float(pos_frac)})


# ---------------------------------------------------------------- 复用
def existing_rungs(pool):
    """⚖ 现有批**真跑过**的那些 k 档（来自**池快照**的 `cells_by_tid` ⇒ ⛔ 不重算阶梯）。"""
    out = {}
    for tid, cells in (pool.get("cells_by_tid") or {}).items():
        vals = []
        for c in cells or []:
            if (c.get("kind") or "") == "k":
                try:
                    vals.append(int(c.get("val")))
                except (TypeError, ValueError):
                    continue
        if vals:
            out[tid] = vals
    return out


def reuse_tracks(DC, ti, rungs, tracks, pos_fracs, target, pf_measured):
    """⚖⚖⚖ **哪些格可以复用**（244.75 的判据，逐位）：格的身份 =
    **(轨迹, pos_frac, scope, n_sites)** 四样都一样 ⇒ ⇒ 那格**探过了**。

    ⚖ 现有批的 `pos_frac` **只有 0.5 被测过**（池快照 `pos_frac.measured`）⇒ ⇒
    ⇒ **只有那一个 `pos_frac` 的格**可能复用 ⇒ ⇒ 其余两档**必须新跑**。
    ⚠⚠ **不许**在没测过的 `pos_frac` 上认复用（⛔ 那等于假设「那个组合探过了」）。
    ⚖ 复用的**探针次数** = 轨迹数 × **臂数**（两臂都探过）。
    """
    reuse = []
    for tid in tracks:
        info = ti.get(tid)
        if not info or not info.get("P") or not info.get("n_gen"):
            continue
        lad = rungs.get(tid) or []
        if not lad:
            continue
        for pf in pos_fracs:
            if pf not in pf_measured:
                continue
            inj = inj_of(DC, info["P"], info["n_gen"], pf)
            cn = canonical_ns(inj, target)
            if cn in lad:
                reuse.append((tid, pf, cn))
    return reuse


# ---------------------------------------------------------------- 主生成
def build_cells(pool, spec, route):
    """⚖⚖⚖ **生成清单** ⇒ 返回 `(判据行, 判决字典)`（判决只算一次 ⇒ 印出来的与返回的一致）。"""
    DC = dconf()
    ti = {}
    for t in pool.get("tids") or []:
        ti[t["tid"]] = {"P": t.get("P"), "n_gen": t.get("n_gen"),
                        "n_eff": t.get("n_eff")}
    rows = []
    R = {}

    def put(gid, ok, detail):
        R[gid] = bool(ok)
        rows.append("  [%s] %-5s %s" % ("PASS" if ok else "FAIL", gid, detail))

    # ---- C1 规格内嵌的 route 副本 vs 路线文件
    diffs = check_route_consistency(spec, route)
    put("C1", not diffs,
        "**规格内嵌的 route 与路线文件逐字一致**（⛔ 两处各写一份 ⇒ 会漂）：%s"
        % ("✅ 一致" if not diffs else "❌ %s" % diffs))

    # ---- C2 规格声明的列 vs 本工具的列
    ok2 = list(spec["columns"]) == list(CELLS_COLUMNS)
    put("C2", ok2,
        "**列声明一致**（规格 `columns` vs 本工具）：规格 **%s** ｜ 工具 **%s** %s"
        % (spec["columns"], list(CELLS_COLUMNS), "✅" if ok2 else "❌"))

    # ---- C3 每条轨迹的复制格数 = pos_frac 数
    ok3 = (route["cells_per_track"] == len(route["pos_fracs"]))
    put("C3", ok3,
        "**每条轨迹的复制格数 = `pos_frac` 数**（规格自洽）：cells_per_track **%d** vs "
        "pos_fracs **%d** %s"
        % (route["cells_per_track"], len(route["pos_fracs"]), "✅" if ok3 else "❌"))

    # ---- C4 选轨
    all_tids = sorted(ti.keys())
    tracks = select_tracks(all_tids, route["target_tracks_per_arm"])
    expect_prefix = all_tids[:route["target_tracks_per_arm"]]
    ok4 = (tracks == expect_prefix)
    put("C4", ok4,
        "**选轨 = `tid` 字典序前 %d 条**（变体预登记 §6 的 S1–S3）：实得 **%d** 条 %s"
        % (route["target_tracks_per_arm"], len(tracks), "✅" if ok4 else "❌"))

    # ---- C5 逐格算剂量（供给：每个 (轨迹, pos_frac) 都要落在 ρ*±tol 内）
    target, tol = spec["frac"], spec["tol"]
    cells = []
    bad = []
    spread = []
    dens_all = []
    for tid in tracks:
        info = ti.get(tid)
        if not info or not info.get("P") or not info.get("n_gen"):
            bad.append((tid, "-", "-", "缺 P / n_gen"))
            continue
        row_dens = []
        for pf in route["pos_fracs"]:
            inj = inj_of(DC, info["P"], info["n_gen"], pf)
            cn = canonical_ns(inj, target)
            d = density_of(DC, cn, info["P"], info["n_gen"], pf)
            row_dens.append(d)
            dens_all.append(d)
            if abs(d - target) > tol:
                bad.append((tid, pf, cn, d))
            cells.append({"tid": tid, "scope": spec["scope"], "n_sites": cn,
                          "pos_frac": pf, "inj": inj, "density": d})
        spread.append((tid, max(row_dens) - min(row_dens)))
    ok5 = (not bad) and bool(cells)
    put("C5", ok5,
        "**每格密度落在 ρ*±tol 内**（ρ*=%.4f tol=%.4f）：%d 格里**不落**的 **%d** 格 %s"
        % (target, tol, len(cells), len(bad), "✅" if ok5 else "❌（%s）" % bad[:3]))

    # ---- C6 同一条轨迹的复制格**密度相等**（这才是「固定剂量」）
    worst = max(spread, key=lambda x: x[1]) if spread else ("—", 0.0)
    ok6 = bool(spread) and worst[1] <= tol
    put("C6", ok6,
        "**同一条轨迹的复制格密度相等**（⇒ 这才是「固定剂量」）：最坏极差 **%.6f**（%s）"
        "（容差 %.4f）%s" % (worst[1], worst[0], tol, "✅" if ok6 else "❌"))

    # ---- C7 格数闸（**两条独立算法**必须给出同一个数 ⇒ ⛔ 恒绿护栏要能红）
    want_tracks = route["target_tracks_per_arm"] * len(route["pos_fracs"])
    want_blocks = route["n_blocks"] * TRACKS_PER_BLOCK * route["cells_per_track"]
    ok7 = (len(cells) == want_tracks == want_blocks)
    put("C7", ok7,
        "**格数闸**（两条独立算法必须给出同一个数）：轨迹数 %d × pos_frac %d = **%d** ｜ "
        "块数 %d × %d 条/块 × cells_per_track %d = **%d** ｜ 实得 **%d** %s"
        % (route["target_tracks_per_arm"], len(route["pos_fracs"]), want_tracks,
           route["n_blocks"], TRACKS_PER_BLOCK, route["cells_per_track"], want_blocks,
           len(cells), "✅" if ok7 else "❌"))

    # ---- C8 每条轨迹的复制格数
    per = collections.Counter(c["tid"] for c in cells)
    bad_per = sorted(t for t, n in per.items() if n != len(route["pos_fracs"]))
    ok8 = (not bad_per) and (len(per) == len(tracks))
    put("C8", ok8,
        "**每条轨迹恰好 %d 个复制格**：%d 条轨迹里**数不对**的 **%d** 条 %s"
        % (len(route["pos_fracs"]), len(per), len(bad_per),
           "✅" if ok8 else "❌（%s）" % bad_per[:3]))

    # ---- C9 复用数 / 要新跑多少次（对账 244.75 的登记值）
    rungs = existing_rungs(pool)
    pf_measured = [float(x) for x in ((pool.get("pos_frac") or {}).get("measured") or [])]
    reuse = reuse_tracks(DC, ti, rungs, tracks, route["pos_fracs"], target, pf_measured)
    reuse_tids = sorted(set(t for t, _pf, _n in reuse))
    n_arms = len(route["arms"]) or 1
    probe_runs = len(cells) * n_arms
    reuse_runs = len(reuse_tids) * n_arms
    new_runs = probe_runs - reuse_runs
    ok9 = (len(reuse_tids) == REUSE_TRACKS_REGISTERED and
           reuse_runs == REUSE_RUNS_REGISTERED and
           probe_runs == PROBE_RUNS_REGISTERED and
           new_runs == NEW_RUNS_REGISTERED)
    put("C9", ok9,
        "**复用数与 244.75 登记值逐位对账**：可复用 **%d** 条轨迹（登记 %d）／**%d** 次探针"
        "（登记 %d）／总 **%d** 次（登记 %d）／**要新跑 %d** 次（登记 %d）%s"
        % (len(reuse_tids), REUSE_TRACKS_REGISTERED, reuse_runs, REUSE_RUNS_REGISTERED,
           probe_runs, PROBE_RUNS_REGISTERED, new_runs, NEW_RUNS_REGISTERED,
           "✅" if ok9 else "❌"))

    # ---- C10 臂数必须来自路线（⛔ 不许写死 2）
    ok10 = (n_arms == len(route["arms"]) and n_arms >= 1)
    put("C10", ok10,
        "**臂数来自路线**（⛔ 不许写死）：**%d** 臂 %s" % (n_arms, "✅" if ok10 else "❌"))

    # ---- 判决
    blocking = [g for g in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10")
                if not R.get(g, False)]
    can = not blocking
    v = {"R": R, "rows": rows, "can": can, "blocking": blocking, "cells": cells,
         "tracks": tracks, "reuse": reuse, "reuse_tids": reuse_tids,
         "probe_runs": probe_runs, "reuse_runs": reuse_runs, "new_runs": new_runs,
         "dens_min": (min(dens_all) if dens_all else None),
         "dens_max": (max(dens_all) if dens_all else None),
         "worst_spread": (worst[1] if spread else None),
         "n_arms": n_arms}
    return rows, v


def render(spec, route, v, out_path):
    out = []
    out.append("=" * 78)
    out.append("【固定剂量格清单生成】⚖⚖⚖ 机器产出 4 列清单（244.76，零 GPU）")
    out.append("=" * 78)
    out.append("  ⚖ 规格：`%s`（ρ*=%.4f tol=%.4f scope=%s）"
               % (spec["spec_id"], spec["frac"], spec["tol"], spec["scope"]))
    out.append("  ⚖ 路线：`%s`（%d 条/臂 × %d 个 pos_frac %s ｜ %d 臂）"
               % (route["route_id"], route["target_tracks_per_arm"],
                  len(route["pos_fracs"]), route["pos_fracs"], v["n_arms"]))
    out.append("  ⚖ 清单：%s（**%d** 格 / **%d** 条轨迹）"
               % (out_path or "（未写出）", len(v["cells"]), len(v["tracks"])))
    out.append("  ⚖ 密度：min **%.6f** ｜ max **%.6f** ｜ 同轨迹最坏极差 **%.6f**"
               % (v["dens_min"], v["dens_max"], v["worst_spread"]))
    out.append("  ⚖ 探针：总 **%d** 次（%d 格 × %d 臂）｜ 可复用 **%d** 次"
               "（%d 条轨迹）｜ **要新跑 %d** 次"
               % (v["probe_runs"], len(v["cells"]), v["n_arms"], v["reuse_runs"],
                  len(v["reuse_tids"]), v["new_runs"]))
    out.append("")
    for ln in v["rows"]:
        out.append(ln)
    out.append("")
    if v["can"]:
        out.append("  ✅ **清单可以生成**（判据全绿）")
    else:
        out.append("  🔴 **清单不能生成**（阻断：%s）" % ", ".join(v["blocking"]))
    out.append("  ⛔ **本工具不发批** ⇒ ⇒ 发不发 / 跑不跑 ⇒ **要用户点头**")
    out.append("  ⚠⚠⚖ **格式契约**：4 列 ＋ **一行表头** ⇒ ⇒ 生产跑批脚本**必须显式跳/验表头**"
               "（⛔ 否则会去探一格假格 `tid/scope/n_sites`）")
    out.append("")
    return "\n".join(out)


def cells_text(spec, v):
    """⚖⚖⚖ **清单正文**：**表头 ＋ 数据行**（按 `(tid, pos_frac)` 升序 ⇒ ⇒ 可复现）。"""
    lines = ["\t".join(spec["columns"])]
    for c in sorted(v["cells"], key=lambda x: (x["tid"], x["pos_frac"])):
        lines.append("\t".join([c["tid"], c["scope"], str(c["n_sites"]),
                                str(c["pos_frac"])]))
    return "\n".join(lines) + "\n"


# ================================================================ 自检
def selftest(pool_path=POOL_DEFAULT, spec_path=SPEC_DEFAULT, route_path=ROUTE_DEFAULT):
    """⚖⚠⚖ **每条判据都要有红化反例**（⛔ 恒绿的判据不许留）。"""
    import tempfile
    import shutil
    DC = dconf()
    pool = fdf().read_pool(pool_path)
    spec = read_spec(spec_path)
    route = read_route(route_path)
    ok, bad = [], []

    def chk(name, cond, msg):
        (ok if cond else bad).append(name)
        if not cond:
            print("[FAIL] %s：%s" % (name, msg))

    # ---- C1：inj 必须逐位等于生产 `denom_of`
    r = inj_of(DC, 112, 757, 0.25)
    exp = DC.denom_of({"inject_n_sites": 1, "P": 112, "n_gen": 757, "pos_frac": 0.25})
    chk("T1", r == exp, "inj 必须逐位等于生产 `denom_of`（实测 %r vs %r）" % (r, exp))

    # ---- T1b：`int()` 是**向零截断**（⛔ 不是四舍五入）
    chk("T1b", inj_of(DC, 10, 3, 0.5) == 10,
        "int() 向零截断：P=10 n_gen=3 f=0.5 ⇒ inj=%r（期望 10）"
        % (inj_of(DC, 10, 3, 0.5),))

    # ---- T1c：`max(1, …)` 的夹取**真的生效**
    r1c = inj_of(DC, 10, 1, 0.5)
    e1c = DC.denom_of({"inject_n_sites": 1, "P": 10, "n_gen": 1, "pos_frac": 0.5})
    chk("T1c", r1c == e1c, "`max(1,…)` 生效时 inj 仍须等于生产实现（实测 %r vs %r）"
        % (r1c, e1c))

    # ---- T1d：分母**必须依赖 pos_frac**（⛔ 否则「固定剂量」那套全废）
    d25 = inj_of(DC, 112, 757, 0.25)
    d75 = inj_of(DC, 112, 757, 0.75)
    chk("T1d", d25 != d75,
        "inj 必须随 pos_frac 变（0.25 ⇒ %r ｜ 0.75 ⇒ %r）⇒ 否则 244.72 那道**断层**又回来了"
        % (d25, d75))

    # ---- T2：规范取整必须夹在 [1, inj]
    chk("T2", 1 <= canonical_ns(5, 0.99) <= 5 and canonical_ns(1, 0.2) == 1,
        "规范取整必须夹在 [1, inj]（inj=5 ρ*=0.99 ⇒ %r ｜ inj=1 ρ*=0.2 ⇒ %r，"
        "后者**必须**被下限夹到 1）" % (canonical_ns(5, 0.99), canonical_ns(1, 0.2)))

    # ---- T3：密度必须走生产机械 `frac_of`
    d = density_of(DC, 1698, 112, 757, 0.5)
    e = DC.frac_of({"inject_n_sites": 1698, "P": 112, "n_gen": 757, "pos_frac": 0.5})
    chk("T3", d == e, "密度必须逐位等于生产 `frac_of`（实测 %r vs %r）" % (d, e))

    # ---- T4：选轨规则 = 字典序前 N 条（**独立期望**：不是从被检对象派生）
    tids = sorted(t["tid"] for t in pool["tids"])
    sel = select_tracks(tids, 56)
    chk("T4", sel == tids[:56] and len(sel) == 56,
        "选轨必须是**字典序前 56 条**（实得 %d 条，首条 %r）" % (len(sel), sel[0] if sel else None))

    # ---- T5：供给不成立（ρ* 离谱）⇒ 必须**判红**，不许崩、不许猜
    tmp = tempfile.mkdtemp(prefix="fdcells_")
    try:
        bad_spec = dict(spec, frac=0.999, tol=0.0001)
        _rows, vbad = build_cells(pool, bad_spec, route)
        chk("T5", (not vbad["can"]) and (not vbad["R"]["C5"]),
            "ρ* 离谱（0.999）⇒ C5 必须红且清单**不能生成**（实际 C5=%s can=%s）"
            % (vbad["R"]["C5"], vbad["can"]))

        # ---- T6：规格内嵌的 route 副本漂了 ⇒ C1 必须红
        drift_spec = dict(spec)
        drift_spec["route_embedded"] = dict(spec["route_embedded"],
                                             pos_fracs=[0.25, 0.5])
        _rows, vdrift = build_cells(pool, drift_spec, route)
        chk("T6", (not vdrift["R"]["C1"]),
            "规格内嵌的 route 与路线文件不一致 ⇒ C1 必须红（实际 C1=%s）" % vdrift["R"]["C1"],)

        # ---- T7：**基线必须全绿**（⛔ 否则「能红」的说法不算数）
        _rows, v = build_cells(pool, spec, route)
        chk("T7", v["can"],
            "基线必须全绿（实际阻断 %s）" % (v["blocking"],))

        # ---- T8：**格数必须是预登记的那个数**（独立字面量 ⇒ ⛔ 不是从被检对象派生）
        chk("T8", len(v["cells"]) == CELLS_REGISTERED,
            "这一批的格数必须是 **%d**（变体预登记 §7 登记值；实得 %d）"
            % (CELLS_REGISTERED, len(v["cells"])))

        # ---- T8b：格数闸必须**能红**（两条算法不一致 ⇒ 红）
        bad_route = dict(route, n_blocks=route["n_blocks"] - 1)
        _rows, vbad7 = build_cells(pool, spec, bad_route)
        chk("T8b", (not vbad7["R"]["C7"]) and ("C7" in vbad7["blocking"]),
            "路线里的块数少一块 ⇒ 格数闸（两条算法不一致）必须红（实际 C7=%s）"
            % (vbad7["R"]["C7"],))

        # ---- T9：**表头**必须存在且列名 == 规格声明（⛔ 格式的第二个维度）
        txt = cells_text(spec, v)
        first = txt.split("\n")[0]
        chk("T9", first == "\t".join(spec["columns"]),
            "清单第一行必须是**表头**且列名 == 规格 `columns`（实测 %r）" % (first,))

        # ---- T10：**改口径不许改数**（【9.4】）：只改**文本** ⇒ 输出**逐位相同**
        text_spec = dict(spec, spec_id=spec["spec_id"] + "（只改了文本）")
        _rows, vt = build_cells(pool, text_spec, route)
        chk("T10", cells_text(text_spec, vt) == txt,
            "只改文本（`spec_id`）⇒ 清单必须**逐位相同**（⇒ 「改口径不许改数」的第一版）")

        # ---- T11：⚖⚖ **改口径必须改数**（反例 ⇒ 证明上面那条不是恒绿）
        other_spec = dict(spec, frac=0.30)
        _rows, vo = build_cells(pool, other_spec, route)
        chk("T11", cells_text(other_spec, vo) != txt,
            "ρ* 改成 0.30 ⇒ 清单必须**变**（⇒ T10 那条不是恒绿）")

        # ---- T12：复用数必须与 244.75 的登记值**逐位一致**（独立字面量）
        chk("T12", (len(v["reuse_tids"]) == REUSE_TRACKS_REGISTERED and
                     v["reuse_runs"] == REUSE_RUNS_REGISTERED and
                     v["probe_runs"] == PROBE_RUNS_REGISTERED and
                     v["new_runs"] == NEW_RUNS_REGISTERED),
            "复用/新跑次数必须与 244.75 登记值逐位一致（实得 %d/%d/%d/%d，登记 %d/%d/%d/%d）"
            % (len(v["reuse_tids"]), v["reuse_runs"], v["probe_runs"], v["new_runs"],
               REUSE_TRACKS_REGISTERED, REUSE_RUNS_REGISTERED,
               PROBE_RUNS_REGISTERED, NEW_RUNS_REGISTERED))

        # ---- T13：⚖⚖ **「少乘臂数」那个经典错**必须被分辨出来
        #      少乘臂数 ⇒ 336 − 14 = **322**（244.75 的老坑）｜ 正确 ⇒ 336 − 28 = **308**
        naive = v["probe_runs"] - len(v["reuse_tids"])
        chk("T13", (v["new_runs"] == NEW_RUNS_REGISTERED) and (naive != NEW_RUNS_REGISTERED),
            "「少乘臂数」的值（%d）必须与正确值（%d）**不同** ⇒ 判据能分辨（实际新跑 %d）"
            % (naive, NEW_RUNS_REGISTERED, v["new_runs"]))

        # ---- T14：⚖⚖ **同一条轨迹的复制格密度必须相等**（D2 的同款判据）
        spreads = []
        by = collections.defaultdict(list)
        for c in v["cells"]:
            by[c["tid"]].append(c["density"])
        for tid, ds in by.items():
            spreads.append(max(ds) - min(ds))
        chk("T14", spreads and max(spreads) <= spec["tol"],
            "同轨迹复制格密度必须相等（最坏极差 %.6f，容差 %.4f）"
            % (max(spreads) if spreads else -1, spec["tol"]))

        # ---- T15：⚖⚖ 清单**必须自洽**：每行的 `n_sites` 与 `pos_frac` 重算出来的密度一致
        mism = 0
        for c in v["cells"]:
            info = [t for t in pool["tids"] if t["tid"] == c["tid"]][0]
            dd = density_of(DC, c["n_sites"], info["P"], info["n_gen"], c["pos_frac"])
            if abs(dd - c["density"]) > 1e-12:
                mism += 1
        chk("T15", mism == 0,
            "清单里每一行的密度必须能**重算**出来（不符 %d 行）" % mism)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("自检 %d 通过 / %d 失败" % (len(ok), len(bad)))
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(description="244.76：生成「固定剂量」的 4 列格清单（零 GPU）")
    ap.add_argument("--out", default=None, help="清单写到哪儿（⛔ 不给就不写）")
    ap.add_argument("--pool", default=POOL_DEFAULT)
    ap.add_argument("--spec", default=SPEC_DEFAULT)
    ap.add_argument("--route", default=ROUTE_DEFAULT)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    try:
        if a.selftest:
            return selftest(a.pool, a.spec, a.route)
        pool = fdf().read_pool(a.pool)
        spec = read_spec(a.spec)
        route = read_route(a.route)
        _rows, v = build_cells(pool, spec, route)
        txt = cells_text(spec, v)
        if a.out:
            with io.open(a.out, "w", encoding="utf-8") as fh:
                fh.write(txt)
        print(render(spec, route, v, a.out))
        return 0 if v["can"] else 1
    except HardFail as e:
        print("⛔ %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
