#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixed_dose_cost.py —— **两条路线各要花多少**（零 GPU，零写操作）。

⚖⚖⚖⚖⚖ **244.71 的问题**：244.70 判掉「照今天的生成池，那一批发不出去」⇒ ⇒ 下一步是
  「**扩池**」与「**先量后算**」两条路，**各要花多少** ⇒ ⇒ 而「花多少」必须**量出来**，
  ⛔ 不能是形容词。

⚖ **本工具的输入**（都是**真件**，不是估计）：
  · `.cache/r244/fixed_dose_pool_snapshot.json`  —— 生成池快照（60 条 / 30 对 / 86.1 GB）
  · `.cache/r244/fixed_dose_cost_baseline.json`  —— **成本基线**（从既有日志与 mtime 量出来的
    探针单格墙钟、生成单条墙钟、每对字节数；带源 md5）
  · 一份**路线** JSON（`--emit-route-template` 可打印模板）

⚖ **两条路线**：
  · `expand_pool`（扩池）：先补生成池到够，再跑 ⇒ 多付**生成**的钱
  · `measure_first`（先量后算）：用现成池跑**单剂量**小批 ⇒ 零新生成，先拿到**实测**效应量

⚖⚠⚖⚖⚖⚖ **本工具防两个「低估成本」的坑**（这两个坑都是 244.71 实测时真踩到的）：
  ① **边际生成成本必须按「对」算**：生成池是 **think/no_think 成对**的 ⇒ 扩池是**成对**加
     ⇒ 边际成本 = **每对均值**（2.86 GB）⇒ ⛔ **不是**「每条中位 × 2」（0.69 × 2 = 1.38 GB）
     ⇒ ⇒ 244.70 用后者 ⇒ **低估了 2.08 倍**（202 GB vs 420 GB）⇒ 本工具把这条做成判据 **C4**。
  ② **墙钟必须用均值**：单格墙钟的分布**长尾**（中位 25 s，均值 54 s，max 541 s）⇒
     ⇒ 用中位算总墙钟会**低估 2 倍**⇒ ⇒ 本工具把这条做成判据 **C5**（中位只作**下界**印出）。

⚖ **判决**：两条路线**都**算总墙钟 ＋ 总字节 ⇒ 打印**比值** ⇒ ⚠ 但「先量后算」更便宜
  **不等于**它更对 ⇒ 它拿到的是**更小**的样本 ⇒ 结论**更弱** ⇒ ⇒ 两条前提都要印。

用法：
  `fixed_dose_cost.py --route <json> [--pool <json>] [--baseline <json>]`
  `fixed_dose_cost.py --emit-route-template`
  `fixed_dose_cost.py --selftest`
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
POOL_DEFAULT = os.path.join(HERE, "fixed_dose_pool_snapshot.json")
BASE_DEFAULT = os.path.join(HERE, "fixed_dose_cost_baseline.json")

C_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
C_BLOCKING = ("C1", "C2", "C3", "C6")
C_PREMISE = ("C7",)
C_KIND = {"C1": "池子", "C2": "池子", "C3": "设计", "C4": "口径",
          "C5": "口径", "C6": "生成侧", "C7": "前提", "C8": "口径"}

ROUTE_KEYS = ("route_id", "strategy", "target_tracks_per_arm", "n_blocks",
              "cells_per_track", "pos_fracs", "arms")
# ⚖ 路线规格**可以**带 `premises`（这一步的**前提**，做成**数据** ⇒ ⛔ 不写在代码里
#   ⇒ 换一条路线时前提跟着换 ⇒ ⇒ 打印出来才不会被漏掉）
ROUTE_OPT = ("premises",)


def _read(p):
    with open(p, encoding="utf-8") as fh:
        t = fh.read()
    assert "\ufffd" not in t, "%s 里有坏字" % p
    return t


def _stat(s):
    """⚖ 一个 stats 字典 ⇒ (中位, 均值, max, n)。"""
    return s["median"], s["mean"], s["max"], s["n"]


def evaluate(route, pool, base):
    """⚖ 算一条路线的成本 + 判 C1–C8。返回 (rows, verdict_dict)。"""
    R = {}
    rows = []
    gaps = []
    premises = []

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        rows.append("  [%s] %-4s %s" % ("PASS" if ok else "FAIL", cid, detail))

    # ---- 输入自洽（⛔ 基线快照自带 caveats ⇒ 这里只查它有没有那些字段）
    for k in ("probe_cell", "gen_track", "cell_list", "sources"):
        assert k in base, "成本基线缺 %s" % k

    n_tid_pool = int(pool["n_tid"])
    n_blk_pool = int(pool["n_blocks_paired"])
    per_pair_bytes = float(base["gen_track"]["bytes_per_pair_mean"])
    n_pairs_pool = int(base["gen_track"]["n_pairs"])

    # ===== C1 轨迹数可得 =====
    tgt = int(route["target_tracks_per_arm"])
    ok1 = tgt <= n_tid_pool
    put("C1", ok1,
        "**目标轨迹数可得**：这一批每臂要 **%d** 条；池里**实有** **%d** 条 %s"
        % (tgt, n_tid_pool, "✅" if ok1 else "❌（缺 %d 条）" % (tgt - n_tid_pool)))
    if not ok1:
        gaps.append("池子不够：每臂要 %d 条轨迹，池里只有 %d 条 ⇒ 缺 %d 条" %
                    (tgt, n_tid_pool, tgt - n_tid_pool))

    # ===== C2 块数可得 =====
    nblk = int(route["n_blocks"])
    ok2 = nblk <= n_blk_pool
    put("C2", ok2,
        "**块数可得**：这一批要 **%d** 块；池里 think/no_think **可配对**的块 **%d** %s"
        % (nblk, n_blk_pool, "✅" if ok2 else "❌（缺 %d 块）" % (nblk - n_blk_pool)))
    if not ok2:
        gaps.append("池子不够：要 %d 块，可配对块只有 %d ⇒ 缺 %d 块" %
                    (nblk, n_blk_pool, nblk - n_blk_pool))

    # ===== C3 多格可构造（固定剂量 ⇒ 只剩 pos_frac 这条轴）=====
    pf_avail = [float(x) for x in pool["pos_frac"]["available"]]
    cpt = int(route["cells_per_track"])
    ok3 = cpt <= len(pf_avail)
    put("C3", ok3,
        "**同剂量下的多格可构造**：每条轨迹 %d 格**全在同一个剂量** ⇒ 只剩 **pos_frac** 这条轴；"
        "可用的 pos_frac **%d** 个 %s" % (cpt, len(pf_avail),
                                           "✅" if ok3 else "❌（不够 %d 个）" % (cpt - len(pf_avail))))
    if not ok3:
        gaps.append("设计口径：同一剂量下要 %d 格，但可用的 pos_frac 只有 %d 个 ⇒ 造不出来"
                    % (cpt, len(pf_avail)))

    # ===== C4 边际生成成本必须按「对」算 =====
    #   ⚖⚖⚖ 这一条是 244.71 的**核心防错**：⛔ 绝不许用「每条中位 × 2」
    per_tid_median = float(pool["bytes"]["per_tid_median"])
    naive = 2 * per_tid_median
    need_pairs = max(0, (tgt - n_tid_pool + 1) // 2) if tgt > n_tid_pool else 0
    if route["strategy"] == "expand_pool":
        bytes_gen = need_pairs * per_pair_bytes
        ok4 = bytes_gen >= need_pairs * per_tid_median
        put("C4", ok4,
            "**边际生成成本按「对」算**：要补 **%d 对**（think+no_think）⇒ 每对均值 **%.2f GB**"
            " ⇒ 合计 **%.0f GB**；⛔ 若错用「每条中位 %.2f × 2 = %.2f GB」⇒ 只会算成 **%.0f GB**"
            " ⇒ ⇒ **低估 %.2f 倍** %s"
            % (need_pairs, per_pair_bytes / 1e9, bytes_gen / 1e9, per_tid_median / 1e9,
               naive / 1e9, need_pairs * naive / 1e9,
               (bytes_gen / (need_pairs * naive)) if need_pairs else 1.0,
               "✅" if ok4 else "❌"))
        if not ok4:
            gaps.append("边际生成成本口径错了（用了每条中位而不是每对均值）⇒ 成本被低估")
    else:
        bytes_gen = 0
        put("C4", True,
            "**边际生成成本按「对」算**：本路线**零新生成** ⇒ 生成物成本 **0 GB** "
            "（⚖ 但「先量后算」的代价在**别处**：见 C6 与判决里的前提）✅")

    # ===== C5 墙钟口径：均值（期望），中位只作下界 =====
    arms = list(route["arms"])
    n_cells_total = int(route["n_blocks"]) * 2 * cpt * len(arms)   # 块×2(think/no_think)×格×臂
    w_med, w_mean, w_max, _ = _stat(base["probe_cell"]["w"]["per_cell_s"])
    r_med, r_mean, r_max, _ = _stat(base["probe_cell"]["rand"]["per_cell_s"])
    # ⚖ think / no_think 各占一半的块 ⇒ 每臂的格里 think 与 no_think 各半
    # ⚖⚖⚖⚖ **格子数算错会整段少算一半** ⇒ 这里的乘数是「**每臂**的格数的一半」
    #   ⇒ 四个臂×臂型的项**各乘一次**（⛔ 不是把两臂的均值先平均再乘一次）
    per_arm_cells = n_cells_total // len(arms)
    half = per_arm_cells // 2
    cells_think = half          # 每臂的 think 格数
    cells_nt = per_arm_cells - half
    def _arm_mean(tag, arm):
        s = base["probe_cell"][tag]["per_cell_s_by_arm"].get(arm)
        assert s and s.get("n"), "%s 臂的 %s 分组没有样本" % (tag, arm)
        return s["median"], s["mean"]
    w_t_med, w_t_mean = _arm_mean("w", "think")
    w_n_med, w_n_mean = _arm_mean("w", "no_think")
    r_t_med, r_t_mean = _arm_mean("rand", "think")
    r_n_med, r_n_mean = _arm_mean("rand", "no_think")
    probe_mean_s = half * (w_t_mean + w_n_mean + r_t_mean + r_n_mean)
    probe_med_s = half * (w_t_med + w_n_med + r_t_med + r_n_med)
    ok5 = probe_mean_s >= probe_med_s
    put("C5", ok5,
        "**墙钟用均值**（单格分布**长尾**：中位 %.0f s vs 均值 %.0f s vs max %.0f s）⇒ "
        "本批 **%d 格** ⇒ 期望 **%.0f s（%.2f GPU 小时）**；中位口径只作**下界** **%.0f s（%.2f h）** %s"
        % (w_med, w_mean, w_max, n_cells_total, probe_mean_s, probe_mean_s / 3600.0,
           probe_med_s, probe_med_s / 3600.0, "✅" if ok5 else "❌"))

    # ===== C6 格清单格式：固定剂量 + 多 pos_frac ⇒ 必须有 pos_frac 列 =====
    cl = base["cell_list"]
    has_pf = bool(cl.get("has_pos_frac_column"))
    ok6 = (cpt <= 1) or has_pf
    put("C6", ok6,
        "**格清单格式够不够**：每条轨迹 %d 格 ⇒ 固定剂量下**必须**靠 pos_frac 区分 ⇒ "
        "⇒ 格清单**必须**有 pos_frac 列；现状 **%d 列**（%s）%s"
        % (cpt, cl["n_columns"][0] if cl["n_columns"] else -1, cl.get("columns", "?"),
           "✅" if ok6 else "❌ ⇒ **要改生成侧**（格清单格式）⇒ ⛔ 那是**生成侧改动** ⇒ 要用户点头"))
    if not ok6:
        gaps.append("格清单格式缺 pos_frac 列 ⇒ 固定剂量下多格**造不出来**"
                    "（⇒ 要改生成侧的格清单格式 ⇒ 要用户点头）")

    # ===== C7 未量到的 pos_frac ⇒ 前提（⛔ 不判失败）=====
    pf_meas = [float(x) for x in pool["pos_frac"]["measured"]]
    pf_used = [float(x) for x in route["pos_fracs"]]
    unmeasured = sorted(x for x in pf_used if x not in pf_meas)
    ok7 = not unmeasured
    put("C7", ok7,
        "**pos_frac 轴的已测性**：这一批要用 pos_frac %s；**已测过**的只有 %s ⇒ %s"
        % (pf_used, pf_meas,
           "✅ 全是已测取值" if ok7 else "⚠⚠ **未量到**：%s（已测取值里没有）" % unmeasured))
    if not ok7:
        premises.append("pos_frac 取值 %s **未量到**（已测过的只有 %s）⇒ "
                        "**这一批同时是这条轴的首次测量** ⇒ 它的结论**不能**被说成「已验证过这条轴」"
                        % (unmeasured, pf_meas))
    # ⚖ 路线规格里带来的前提（**数据**）⇒ 追加在自动生成的那些之后
    for _p in route.get("premises", []):
        premises.append(str(_p))

    # ===== C8 路线排序可核：两头的墙钟都要算出来 =====
    gen_mean_s = 0.0
    gen_med_s = 0.0
    if route["strategy"] == "expand_pool":
        g_think = base["gen_track"]["per_interval_s_by_arm"]["think"]
        g_nt = base["gen_track"]["per_interval_s_by_arm"]["no_think"]
        gen_mean_s = need_pairs * (g_think["mean"] + g_nt["mean"])
        gen_med_s = need_pairs * (g_think["median"] + g_nt["median"])
    total_mean_s = gen_mean_s + probe_mean_s
    total_med_s = gen_med_s + probe_med_s
    ok8 = total_mean_s > 0
    put("C8", ok8,
        "**总成本可核**：生成 **%.0f s（%.2f GPU 小时）** ＋ 探针 **%.0f s（%.2f h）** "
        "⇒ **合计 %.0f s（%.2f GPU 小时）**；中位口径下界 **%.0f s（%.2f h）** %s"
        % (gen_mean_s, gen_mean_s / 3600.0, probe_mean_s, probe_mean_s / 3600.0,
           total_mean_s, total_mean_s / 3600.0, total_med_s, total_med_s / 3600.0,
           "✅" if ok8 else "❌"))

    # ⚖⚖⚖ **判决必须与策略相关**：
    #   · `measure_first`：C1/C2 红 ⇒ **真的发不出去**（池子就这么多）
    #   · `expand_pool`  ：C1/C2 红 ⇒ 那是「**要补的量**」（**这条路线就是去补它的**）
    #     ⇒ ⛔ 绝不能把它算成「阻断」⇒ ⛔ 否则「扩池」这条路线会**永远判红**
    #        （而它本该判「补完之后发得出去，代价是 X」）
    pool_fill = [c for c in ("C1", "C2") if not R.get(c, False)]
    if route["strategy"] == "expand_pool":
        blocking = [c for c in C_BLOCKING
                    if not R.get(c, False) and c not in ("C1", "C2")]
    else:
        blocking = [c for c in C_BLOCKING if not R.get(c, False)]
    prem = [c for c in C_PREMISE if not R.get(c, False)]
    can = not blocking
    kind = None
    if blocking:
        ks = set(C_KIND[c] for c in blocking)
        kind = "池子" if ks == {"池子"} else (
            "设计" if ks == {"设计"} else (
                "生成侧" if ks == {"生成侧"} else "两者"))
    return rows, {
        "R": R, "rows": rows, "gaps": gaps, "premises": premises, "can": can, "kind": kind,
        "blocking": blocking, "pool_fill": pool_fill,
        "n_cells_total": n_cells_total, "cells_think": cells_think, "cells_nt": cells_nt,
        "bytes_gen": bytes_gen, "need_pairs": need_pairs,
        "probe_mean_s": probe_mean_s, "probe_med_s": probe_med_s,
        "gen_mean_s": gen_mean_s, "gen_med_s": gen_med_s,
        "total_mean_s": total_mean_s, "total_med_s": total_med_s,
        "per_pair_bytes": per_pair_bytes, "per_tid_median": per_tid_median,
        "naive_bytes": need_pairs * naive,
    }


def render(route, pool, base, verdict, title=None):
    out = []
    out.append("=" * 78)
    out.append("【%s】⚖⚖ 路线成本（244.71，零 GPU）—— 路线 `%s`（%s）"
               % (title or "路线", route["route_id"], route["strategy"]))
    out.append("=" * 78)
    out.append("  ⚖ 目标：每臂 %d 条 / %d 块 / 每条 %d 格 / 臂 %s"
               % (int(route["target_tracks_per_arm"]), int(route["n_blocks"]),
                  int(route["cells_per_track"]), ",".join(route["arms"])))
    out.append("  ⚖ 成本基线：探针单格 w 均 %.1f s ｜ rand 均 %.1f s ｜ 生成每对均 %.2f GB"
               % (base["probe_cell"]["w"]["per_cell_s"]["mean"],
                  base["probe_cell"]["rand"]["per_cell_s"]["mean"],
                  verdict["per_pair_bytes"] / 1e9))
    out.append("")
    out.extend(verdict["rows"])
    out.append("")
    if verdict["pool_fill"]:
        out.append("  ⚖ **要补的量**（本路线就是去补它的 ⇒ 代价已算在下面）：")
        for i, g in enumerate(verdict["gaps"], 1):
            if g.startswith("池子不够"):
                out.append("    · %s" % g)
    rest = [g for g in verdict["gaps"] if not g.startswith("池子不够")]
    if verdict["can"]:
        if verdict["pool_fill"]:
            out.append("  ✅ **补完池子之后这条路发得出去**（阻断类判据全绿；"
                       "⚠ 但「补」本身要花钱 ⇒ 见下面的成本）")
        else:
            out.append("  ✅ **这条路在今天的池子上发得出去**（阻断类判据全绿）")
    else:
        out.append("  🔴 **这条路发不出去** —— 阻断 %d 条（%s类）："
                   % (len(rest), verdict["kind"] or "两者"))
        for i, g in enumerate(rest, 1):
            out.append("    %d) %s" % (i, g))
        for i, g in enumerate(verdict["gaps"], 1):
            if g.startswith("池子不够"):
                out.append("    · %s" % g)
    if verdict["premises"]:
        out.append("")
        out.append("  ⚠⚠⚠ **前提（未量到）** —— ⛔ **不许**说成「已验证」：")
        for i, p in enumerate(verdict["premises"], 1):
            out.append("    %d) %s" % (i, p))
    out.append("")
    out.append("  ⚖ 成本：生成物 **%.0f GB** ｜ 生成墙钟 **%.2f GPU 小时** ｜ "
               "探针 **%d 格 / %.2f GPU 小时** ｜ **合计 %.2f GPU 小时**"
               % (verdict["bytes_gen"] / 1e9, verdict["gen_mean_s"] / 3600.0,
                  verdict["n_cells_total"], verdict["probe_mean_s"] / 3600.0,
                  verdict["total_mean_s"] / 3600.0))
    out.append("  ⚖ （中位口径的下界：生成 %.2f h ＋ 探针 %.2f h ＝ **%.2f GPU 小时**）"
               % (verdict["gen_med_s"] / 3600.0, verdict["probe_med_s"] / 3600.0,
                  verdict["total_med_s"] / 3600.0))
    out.append("")
    return "\n".join(out)


ROUTE_TEMPLATE = {
    "route_id": "（例：expand_pool_354）",
    "strategy": "expand_pool",
    "target_tracks_per_arm": 354,
    "n_blocks": 177,
    "cells_per_track": 3,
    "pos_fracs": [0.25, 0.5, 0.75],
    "arms": ["w", "rand"],
}


def compare(route_a, route_b, pool, base):
    """⚖⚖ **两条路线放一起比**（这才是 244.71 要交的那张表）。"""
    rows_a, va = evaluate(route_a, pool, base)
    rows_b, vb = evaluate(route_b, pool, base)
    out = []
    out.append("=" * 78)
    out.append("【对比】⚖⚖⚖ 两条路线的成本（244.71，零 GPU）")
    out.append("=" * 78)
    out.append("  ⚖ 成本基线：探针单格 w 均 %.1f s ｜ rand 均 %.1f s ｜ 生成每对均 %.2f GB"
               % (base["probe_cell"]["w"]["per_cell_s"]["mean"],
                  base["probe_cell"]["rand"]["per_cell_s"]["mean"],
                  va["per_pair_bytes"] / 1e9))
    out.append("")
    hdr = ("  %-34s | %-22s | %-22s" % ("", route_a["route_id"], route_b["route_id"]))
    out.append(hdr)
    out.append("  " + "-" * (len(hdr) - 2))

    def line(k, a, b):
        out.append("  %-34s | %-22s | %-22s" % (k, a, b))
    line("策略", route_a["strategy"], route_b["strategy"])
    line("每臂目标条数", str(route_a["target_tracks_per_arm"]),
         str(route_b["target_tracks_per_arm"]))
    line("块数", str(route_a["n_blocks"]), str(route_b["n_blocks"]))
    line("每条格数", str(route_a["cells_per_track"]), str(route_b["cells_per_track"]))
    line("要跑的格数", str(va["n_cells_total"]), str(vb["n_cells_total"]))
    line("**新增生成物**", "%.0f GB" % (va["bytes_gen"] / 1e9),
         "%.0f GB" % (vb["bytes_gen"] / 1e9))
    line("**新增生成墙钟**", "%.2f GPU h" % (va["gen_mean_s"] / 3600.0),
         "%.2f GPU h" % (vb["gen_mean_s"] / 3600.0))
    line("**探针墙钟**", "%.2f GPU h" % (va["probe_mean_s"] / 3600.0),
         "%.2f GPU h" % (vb["probe_mean_s"] / 3600.0))
    line("**合计 GPU 小时**", "**%.2f**" % (va["total_mean_s"] / 3600.0),
         "**%.2f**" % (vb["total_mean_s"] / 3600.0))
    line("（中位口径下界）", "%.2f GPU h" % (va["total_med_s"] / 3600.0),
         "%.2f GPU h" % (vb["total_med_s"] / 3600.0))
    line("阻断类判据", ("全绿" if va["can"] else "红 %s" % va["blocking"]),
         ("全绿" if vb["can"] else "红 %s" % vb["blocking"]))
    line("**能拿到的结论**",
         ("判决可下（需求 %d/臂 ≤ 可得）" % int(route_a["target_tracks_per_arm"]))
         if va["can"] else "发不出去",
         ("判决可下（需求 %d/臂 ≤ 可得）" % int(route_b["target_tracks_per_arm"]))
         if vb["can"] else "发不出去")
    out.append("")
    if va["total_mean_s"] > 0 and vb["total_mean_s"] > 0:
        ratio = va["total_mean_s"] / vb["total_mean_s"]
        cheaper = route_b["route_id"] if ratio > 1 else route_a["route_id"]
        out.append("  ⚖⚖⚖ **便宜的那条**：`%s`（**%.2f×**）"
                   % (cheaper, max(ratio, 1.0 / ratio)))
    out.append("  ⚠⚠⚖ **便宜 ≠ 更对** —— 两条路线的前提**不一样**，⛔ 不许只比钱：")
    if va["n_cells_total"] != vb["n_cells_total"]:
        out.append("    · ⚖⚠ **样本量差 %d 倍**（%d 格 vs %d 格）⇒ **样本小的那条给的是更弱的结论**"
                   " ⇒ ⇒ 「便宜」那条买到的**不是**同一种结论"
                   % (max(va["n_cells_total"], vb["n_cells_total"])
                      // max(1, min(va["n_cells_total"], vb["n_cells_total"])),
                      va["n_cells_total"], vb["n_cells_total"]))
    for tag, v in ((route_a["route_id"], va), (route_b["route_id"], vb)):
        if v["premises"]:
            for p in v["premises"]:
                out.append("    · `%s` ⇒ %s" % (tag, p))
        else:
            out.append("    · `%s` ⇒ （无前提）" % tag)
    out.append("  ⚖⚠⚖ **共同的阻断**（两条路线**都**要解决）：")
    common = []
    for cid in C_BLOCKING:
        if not va["R"].get(cid, False) and not vb["R"].get(cid, False):
            common.append("%s（%s）" % (cid, C_KIND[cid]))
    if common:
        for c in common:
            out.append("    · %s" % c)
    else:
        out.append("    · （无）")
    out.append("")
    return "\n".join(out), va, vb


def main():
    import argparse
    ap = argparse.ArgumentParser(description="两条路线的成本对比（244.71，零 GPU）")
    ap.add_argument("--route", default=None)
    ap.add_argument("--compare", nargs=2, default=None, metavar=("ROUTE_A", "ROUTE_B"))
    ap.add_argument("--pool", default=POOL_DEFAULT)
    ap.add_argument("--baseline", default=BASE_DEFAULT)
    ap.add_argument("--emit-route-template", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.emit_route_template:
        print(json.dumps(ROUTE_TEMPLATE, ensure_ascii=False, indent=2))
        return 0
    if a.selftest:
        return selftest(a.pool, a.baseline)
    if a.compare:
        ra = json.loads(_read(a.compare[0]))
        rb = json.loads(_read(a.compare[1]))
        for r in (ra, rb):
            for k in ROUTE_KEYS:
                assert k in r, "路线缺字段 %s" % k
            assert r["strategy"] in ("expand_pool", "measure_first"), "strategy 认不出来"
        pool = json.loads(_read(a.pool))
        base = json.loads(_read(a.baseline))
        txt, va, vb = compare(ra, rb, pool, base)
        print(txt)
        return 0
    if not a.route:
        print("用法：--route <json>（或 --compare A B / --selftest / --emit-route-template）")
        return 2

    route = json.loads(_read(a.route))
    for k in ROUTE_KEYS:
        assert k in route, "路线缺字段 %s" % k
    assert route["strategy"] in ("expand_pool", "measure_first"), "strategy 认不出来"
    pool = json.loads(_read(a.pool))
    base = json.loads(_read(a.baseline))
    rows, v = evaluate(route, pool, base)
    print(render(route, pool, base, v))
    return 0 if v["can"] else 1


# ================================================================ 自检
def _base_route(**kw):
    r = dict(ROUTE_TEMPLATE)
    r["route_id"] = "selftest"
    r.update(kw)
    return r


def selftest(pool_path, base_path):
    pool = json.loads(_read(pool_path))
    base = json.loads(_read(base_path))
    ok, bad = [], []

    def chk(name, cond, msg):
        # ⚖⚖⚖ **行首就是 `[FAIL]`**（⛔ 不许有前导空格）—— 变异台的 `FAIL_RE`
        #   锚在**行首**（`^\[FAIL\] `）⇒ 加缩进 ⇒ 台架会**读不到** ⇒ 「全漏」与「全抓住」
        #   **长得一样** ⇒ ⇒ 这个格式也是**阳性对照**能抓出来的
        (ok if cond else bad).append(name)
        if not cond:
            print("[FAIL] %s：%s" % (name, msg))

    # ---- C1 轨迹数不够
    r = _base_route(target_tracks_per_arm=400, n_blocks=200)
    rows, v = evaluate(r, pool, base)
    chk("T1", (not v["R"]["C1"]) and (not v["can"]),
        "要 400 条/臂、池里 60 条 ⇒ C1 必须红且判「发不出去」")
    chk("T1b", any("缺 340 条" in g for g in v["gaps"]),
        "缺口清单必须写明缺多少条（得 %r）" % v["gaps"])

    # ---- C2 块数不够
    r = _base_route(target_tracks_per_arm=56, n_blocks=999)
    rows, v = evaluate(r, pool, base)
    chk("T2", (not v["R"]["C2"]) and (not v["can"]), "要 999 块 ⇒ C2 必须红")

    # ---- C3 多格造不出来
    r = _base_route(target_tracks_per_arm=56, n_blocks=28, cells_per_track=9)
    rows, v = evaluate(r, pool, base)
    chk("T3", (not v["R"]["C3"]) and (not v["can"]),
        "每条 9 格 > 3 个 pos_frac ⇒ C3 必须红")

    # ---- C4 边际成本按「对」：改 pool 的 per_tid_median 不得改变扩池成本
    r = _base_route(strategy="expand_pool", target_tracks_per_arm=354, n_blocks=177)
    rows, v = evaluate(r, pool, base)
    bytes_a = v["bytes_gen"]
    pool2 = json.loads(_read(pool_path))
    pool2["bytes"]["per_tid_median"] = 1          # ⚖ 故意改掉每条中位
    rows, v2 = evaluate(r, pool2, base)
    chk("T4", abs(v2["bytes_gen"] - bytes_a) < 1,
        "扩池的生成物成本**不许**随「每条中位」变（那正是 244.70 低估 2.08 倍的根因）"
        "（得 %r vs %r）" % (bytes_a, v2["bytes_gen"]))
    chk("T4b", v2["R"]["C4"],
        "改了每条中位之后 C4 仍必须绿（成本仍按每对算）")

    # ---- C5 墙钟用均值：中位口径只会更小
    r = _base_route(strategy="measure_first", target_tracks_per_arm=56, n_blocks=28)
    rows, v = evaluate(r, pool, base)
    chk("T5", v["probe_mean_s"] > v["probe_med_s"],
        "均值口径必须 > 中位口径（长尾分布 ⇒ 用中位会低估）（得 %.0f vs %.0f）"
        % (v["probe_mean_s"], v["probe_med_s"]))
    chk("T5b", v["R"]["C5"], "C5 必须绿（口径对）")

    # ---- C6 格清单格式：现状没有 pos_frac ⇒ 固定剂量多格 ⇒ 必须红
    r = _base_route(strategy="measure_first", target_tracks_per_arm=56, n_blocks=28,
                    cells_per_track=3)
    rows, v = evaluate(r, pool, base)
    chk("T6", (not v["R"]["C6"]) and (not v["can"]),
        "现状格清单 3 列（无 pos_frac）⇒ 固定剂量下每条 3 格 ⇒ C6 必须红")
    chk("T6b", any("pos_frac" in g for g in v["gaps"]),
        "缺口清单必须点名 pos_frac 列（得 %r）" % v["gaps"])
    # ⛔ 断言现状真的是 3 列（⛔ 不许哪天悄悄变了还继续红）
    chk("T6c", base["cell_list"]["n_columns"] == [3],
        "成本基线里格清单应当是 3 列（得 %r）" % base["cell_list"]["n_columns"])

    # ---- C7 未量到的 pos_frac ⇒ 进前提，⛔ 不判失败
    r = _base_route(strategy="measure_first", target_tracks_per_arm=56, n_blocks=28,
                    pos_fracs=[0.25, 0.5, 0.75])
    rows, v = evaluate(r, pool, base)
    chk("T7", (not v["R"]["C7"]) and len(v["premises"]) >= 1,
        "C7 红 ⇒ 必须进前提清单（得 %d 条前提）" % len(v["premises"]))
    chk("T7b", any("未量到" in p for p in v["premises"]),
        "前提清单必须写「未量到」（得 %r）" % v["premises"])
    chk("T7c", "C7" not in C_BLOCKING,
        "C7 是**前提类**判据 ⇒ ⛔ 不许进阻断类（否则「未量到」会被当成「失败」）")

    # ---- C8 总成本可算
    chk("T8", v["total_mean_s"] > 0 and v["R"]["C8"], "C8 必须绿且总墙钟 > 0")

    # ---- T10 格子数必须等于 块×2(think/no_think)×每条格数×臂数
    r = _base_route(strategy="measure_first", target_tracks_per_arm=56, n_blocks=28,
                    cells_per_track=3)
    rows, v = evaluate(r, pool, base)
    want = 28 * 2 * 3 * 2
    chk("T10", v["n_cells_total"] == want,
        "格子数必须是 %d（得 %d）" % (want, v["n_cells_total"]))

    # ---- T11 独立复算：每格平均墙钟必须落在**实测**的每格均值区间内
    #   ⚖⚖⚖ 这一条会抓住「乘数错 ⇒ 整段少算一半」那类错（本轮真犯过）
    means = []
    for tag in ("w", "rand"):
        for arm, st in base["probe_cell"][tag]["per_cell_s_by_arm"].items():
            if st.get("n"):
                means.append(st["mean"])
    lo, hi = min(means), max(means)
    per_cell = v["probe_mean_s"] / float(v["n_cells_total"])
    chk("T11", lo <= per_cell <= hi,
        "每格平均墙钟 %.1f s 必须落在实测区间 [%.1f, %.1f] 内（⇒ 乘数没算错）"
        % (per_cell, lo, hi))
    # ⛔ 再钉一条：每格平均墙钟必须 ≥ **各臂型中位**的最小值（防止拿中位当均值）
    meds = []
    for tag in ("w", "rand"):
        for arm, st in base["probe_cell"][tag]["per_cell_s_by_arm"].items():
            if st.get("n"):
                meds.append(st["median"])
    chk("T12", per_cell >= min(meds),
        "每格平均墙钟 %.1f s 不得低于任何臂型的中位（%.1f s）⇒ ⛔ 不许用中位冒充均值"
        % (per_cell, min(meds)))

    # ---- T13 「扩池」路线：C1/C2 红是**它要做的事** ⇒ ⛔ 不许判成「发不出去」
    r = _base_route(strategy="expand_pool", target_tracks_per_arm=354, n_blocks=177)
    rows, v = evaluate(r, pool, base)
    chk("T13", (not v["R"]["C1"]) and (not v["R"]["C2"])
        and "C1" not in v["blocking"] and "C2" not in v["blocking"]
        and v["pool_fill"] == ["C1", "C2"],
        "扩池路线：C1/C2 必须红（那是**要补的量**）但**不许**进阻断集"
        "（得 blocking=%s pool_fill=%s）" % (v["blocking"], v["pool_fill"]))
    chk("T13b", any("要补的量" in x for x in render(r, pool, base, v).split("\n")),
        "扩池路线的判决里必须出现「**要补的量**」⇒ ⛔ 不能把补池说成「缺口」")

    # ---- T14 缺口类别：只红 C6（生成侧）⇒ 类别必须印「生成侧」而不是「两者」
    r = _base_route(strategy="measure_first", target_tracks_per_arm=56, n_blocks=28)
    rows, v = evaluate(r, pool, base)
    chk("T14", v["kind"] == "生成侧",
        "只红 C6 时缺口类别必须是「生成侧」（得 %r）" % v["kind"])

    # ---- 基线自洽：字节基线与池快照必须逐位对上
    gb = float(base["gen_track"]["bytes_total"])
    pb = float(pool["sources"]["generated_dir"]["bytes"])
    chk("T9", abs(gb - pb) / max(1.0, pb) < 0.01,
        "成本基线的字节合计必须与池快照对上（得 %r vs %r）" % (gb, pb))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
