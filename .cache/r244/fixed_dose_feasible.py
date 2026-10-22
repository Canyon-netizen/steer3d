#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixed_dose_feasible.py —— **那一批能不能跑出来**的体检（零 GPU、纯本地读文件）。

⚖⚠⚖⚖⚖⚖ **为什么要有这个工具**（244.68 留下的洞）：
   244.68 的预检器查的是「**设计声明**的规模 vs 功效需求」⇒ 它**不查**那些轨迹
   在现实里**存不存在** ⇒ ⇒ 一个只查声明的守门人，对「声明与现实不符」是**恒绿的**
   （⚠ 这正是 244.68 自己抓到的 P1「恒绿」那一族）。

   ⚖ 本工具加的那一维叫「**可得性**」：拿**真件派生的生成池快照**
   （`fixed_dose_pool_snapshot.json`）去核对设计 ⇒ 判「这一批**能不能被造出来**」。

⚖⚠⚖⚖⚖⚖ **三条硬纪律**：
   ① **复用既有机械**（⛔ 不另写第二套真相）：
      · 口径与设计检查（D1–D3/D5–D7）⇒ **直接调用** `fixed_dose_preflight.run_preflight`
      · m≥3 的门槛 ⇒ **调用** `dose_layer_audit.size_requirements`（把「一条轨迹服务几个档」
        作为它的 `n_layer` 传进去）⇒ ⛔ **本文件里不写「3 × 档数」这个公式**
   ② **判决只算一次**（印出来的与返回的必须一致 ⇒ 由报告那一层算完返回）
   ③ **每条判据都能红** ⇒ 自检里每条都有**红化反例**；⛔ 恒绿的判据不许留

⚖⚠⚖⚖⚖⚖ **一个必须说清的口径更正**（⛔ 只追加，不改 244.68 的源码）：
   244.68 的 **D4**（每条轨迹至少 12 格）来自 `size_requirements` 的
   `need_cells = 3 × n_layer`，而它传的 `n_layer` = **档数（4）**
   ⇒ ⇒ 那是「**剂量扫描**」设计下的门槛（4 个档 × 每档 m≥3 ⇒ 12 格）。
   ⚖⚠⚠⚖ 而「**固定剂量**」设计里，一条轨迹**只服务一个档** ⇒ 它的 m 就是它自己的格数
   ⇒ ⇒ 门槛应是 **3 格**，**不是 12** ⇒ ⇒ 用 244.68 的 D4 去判固定剂量设计会**假红**
   ⇒ ⇒ 本工具用 **F1**（按设计算门槛）并在报告里**显式**说明这处差别。

⚖ 用法：
   `fixed_dose_feasible.py --design <json> [--pool <json>] [--prereg <md>]`
   `fixed_dose_feasible.py --emit-design-template` / `--emit-pool-template`
   `fixed_dose_feasible.py --selftest`
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_FIXED_DOSE_PREREG.md")
POOL_DEFAULT = os.path.join(HERE, "fixed_dose_pool_snapshot.json")

_MODS = {}


def _load(path, name):
    """⚖ 延迟 import（同目录的既有机械）⇒ ⛔ 不在 import 期就炸。"""
    if name not in _MODS:
        import importlib
        _MODS[name] = importlib.import_module(name)
    return _MODS[name]


def pre():
    return _load("fixed_dose_preflight", "fixed_dose_preflight")


def dlayer():
    return _load("dose_layer_audit", "dose_layer_audit")


def cpre():
    return _load("cluster_premise_audit", "cluster_premise_audit")


class HardFail(Exception):
    """⚖ 本工具自己的 HardFail（⚠ 与 `fixed_dose_audit.HardFail` **不是同一个类型**）。"""


# ⚖ 设计描述 = 244.68 的键 **＋** 两键（⛔ 不许改 244.68 的键集 ⇒ 复用它的校验）
EXTRA_DESIGN_KEYS = ("dose_mode", "pos_fracs")
DESIGN_KEYS = pre().DESIGN_KEYS + EXTRA_DESIGN_KEYS

F_IDS = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")
# ⚖ 哪条判据属于「设计类」、哪条属于「池子类」⇒ ⇒ 缺口分两类 ⇒ **动作不同**
F_BLOCKING = ("F1", "F2", "F3", "F4", "F6", "F7", "F8")
F_PREMISE = ("F5",)
F_KIND = {"F1": "设计", "F2": "池子", "F3": "池子", "F4": "设计",
          "F5": "前提", "F6": "池子", "F7": "池子", "F8": "池子"}


def read_design(path):
    """⚖ 读设计描述（⛔ 复用 244.68 的校验 ⇒ 键集只多两键，其余一模一样）。
    ⚖⚠⚖ **两种同名 `HardFail` 不是同一个类型**（244.68 踩过）⇒ 这里把
    预检器抛的那种**翻译**成本工具的（⇒ 调用方只需要捕一种）。"""
    try:
        d = pre().read_design(path)      # ⛔ 它会检查 244.68 的键 ⇒ 缺键 ⇒ 它抛 HardFail
    except pre().HardFail as e:
        raise HardFail(str(e))
    miss = [k for k in EXTRA_DESIGN_KEYS if k not in d]
    if miss:
        raise HardFail("设计描述缺键：%s（⛔ 不许用默认值兜底）" % ", ".join(miss))
    if d["dose_mode"] not in ("fixed", "sweep"):
        raise HardFail("设计描述 'dose_mode' 只能是 'fixed'（固定剂量）或 'sweep'（剂量扫描），"
                       "得到 %r" % (d["dose_mode"],))
    if not isinstance(d["pos_fracs"], list) or not d["pos_fracs"]:
        raise HardFail("设计描述 'pos_fracs' 必须是非空列表（同一剂量下同一条轨迹的格靠它变）")
    for v in d["pos_fracs"]:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise HardFail("设计描述 'pos_fracs' 的元素必须是数字：%r" % (v,))
    return d


def read_pool(path):
    """⚖ 读生成池快照（⛔ 缺键 ⇒ HardFail；⛔ 不许默认值兜底）。"""
    if not os.path.isfile(path):
        raise HardFail("生成池快照不存在：%s" % path)
    try:
        p = json.loads(io.open(path, encoding="utf-8").read())
    except ValueError as e:
        raise HardFail("生成池快照不是合法 JSON：%s（%s）" % (path, e))
    need = ("n_tid", "n_blocks_paired", "tids", "pos_frac", "bytes", "sources")
    miss = [k for k in need if k not in p]
    if miss:
        raise HardFail("生成池快照缺键：%s" % ", ".join(miss))
    if not isinstance(p["tids"], list) or not p["tids"]:
        raise HardFail("生成池快照 'tids' 必须是非空列表")
    for t in p["tids"]:
        for k in ("tid", "n_eff", "bytes"):
            if k not in t:
                raise HardFail("生成池快照的某条 tid 缺键 %r（tid=%r）" % (k, t.get("tid")))
    pf = p["pos_frac"]
    for k in ("measured", "available"):
        if k not in pf or not isinstance(pf[k], list):
            raise HardFail("生成池快照 'pos_frac' 缺键或类型不对：%r" % (k,))
    return p


def design_template():
    """⚖ 起步模板（⛔ 里面的数是**占位**，⛔ 不是建议规模）。"""
    t = pre().design_template()
    t["dose_mode"] = "fixed"
    t["pos_fracs"] = [0.25, 0.5, 0.75]
    return t


# ---------------------------------------------------------------- 门槛（复用机械）
def bands_per_traj(design):
    """⚖ **一条轨迹服务几个档** ⇒ ⇒ 决定 m≥3 的门槛。
    ⚖⚠⚖ 档数本身**不写死**：扫档的那个数从规模机械那里取（`N_LAYER`）。"""
    if design["dose_mode"] == "fixed":
        return 1
    return int(dlayer().N_LAYER)


def _rows_from(design, cfg):
    """⚖ 把 `expected_proportions` 摊成规模机械要的 `{L, pw, pr}` 行。
    ⚖⚠⚖ 这**不是公式**，只是摊平；⇒ 而**一致性**由下面那次 `assert` 盯着
    （⇒ 与 244.68 的那一段投影**逐条一致**，两处不会漂）。"""
    rows = []
    for b in range(int(cfg.n_bands)):
        try:
            pw = float(design["expected_proportions"]["w"][b])
            pr = float(design["expected_proportions"]["rand"][b])
        except (IndexError, TypeError, ValueError):
            raise HardFail("设计描述的 expected_proportions 少于 %d 档" % int(cfg.n_bands))
        rows.append({"L": b, "pw": pw, "pr": pr})
    return rows


def need_cells_from_mechanic(design, rows, cfg):
    """⚖⚠⚖⚖ **m≥3 的门槛从规模机械的输出行里解析**（⛔ 本文件不重写公式）。
    ⇒ 做法：把「一条轨迹服务几个档」作为 `n_layer` 传进 `size_requirements`
    ⇒ 它自己会算出 `need_cells` 并印出来 ⇒ ⇒ **同一份公式、两种设计**。"""
    n_layer = bands_per_traj(design)
    lines, size = dlayer().size_requirements(
        rows, float(design["cells_per_track"]),
        fisher_power=cpre().fisher_power, n_layer=n_layer)
    need = None
    for ln in lines:
        m = re.search(r"需\s*≥(\d+)\s*档", ln)
        if m:
            need = int(m.group(1))
    assert need is not None, "规模机械的输出行里没解析出 need_cells ⇒ 口径变了"
    return need, n_layer, lines, size


# ---------------------------------------------------------------- 主报告
def build_report(design, pool, prereg_path=PREREG):
    """⚖ **只算一次**：算完返回 ⇒ 印出来的与返回的**必然一致**。
    ⇒ 返回 `(报告行, {判据号: bool}, 判决字典)`。"""
    P = pre()
    F = P.fda()
    raw = F.read_prereg(prereg_path)
    cfg = F.Cfg(raw)
    k_rows = F.prereg_k_rows(prereg_path)

    # ⚖ **复用** 244.68 的预检器（D1–D3/D5–D7 ＋ P1–P10）
    RP, R, _can = P.run_preflight(design, prereg_path=prereg_path)
    sz = P.recompute_size(design, cfg)

    # ⚖⚠⚖ **本工具摊的行**与 **244.68 摊的行**必须**逐条一致**（⇒ 两处不会漂）
    rows = _rows_from(design, cfg)
    _l0, size0 = dlayer().size_requirements(
        rows, float(design["cells_per_track"]),
        fisher_power=cpre().fisher_power, n_layer=int(cfg.n_bands))
    assert size0 == sz["size"], "本工具的摊行与 244.68 的不一致 ⇒ 两处漂了"

    R2 = {}
    lines = []
    gaps = []
    premises = []

    def put(fid, ok, detail):
        R2[fid] = bool(ok)
        lines.append("  [%s] %-4s %s" % ("PASS" if ok else "FAIL", fid, detail))

    # ---------- F1 口径相容：m≥3 的门槛**按设计**算（⛔ 不重写公式）
    need_cells, n_layer, sz_lines, size = need_cells_from_mechanic(design, rows, cfg)
    cpt = float(design["cells_per_track"])
    ok1 = cpt >= float(need_cells)
    put("F1", ok1,
        "**m≥3 的门槛按设计算**：「一条轨迹服务 %d 个档」⇒ 门槛 **%d 格**；设计给 %g 格 %s"
        % (n_layer, need_cells, cpt, "✅" if ok1 else "❌（差 %g 格）" % (need_cells - cpt)))
    if not ok1:
        gaps.append("设计口径：每条轨迹 %g 格 < 门槛 %d 格（m≥3 ⇒ 平票不出现）"
                    % (cpt, need_cells))

    # ---------- F2 轨迹数可得
    need_w = sum(int(x) for x in design["tracks_per_band"]["w"])
    need_r = sum(int(x) for x in design["tracks_per_band"]["rand"])
    need_traj = max(need_w, need_r)
    avail_traj = int(pool["n_tid"])
    ok2 = need_traj <= avail_traj
    put("F2", ok2,
        "**轨迹数可得**：这一批每臂要 **%d** 条（w %d / rand %d）；生成池里**有** **%d** 条 %s"
        % (need_traj, need_w, need_r, avail_traj, "✅" if ok2 else "❌（缺 %d 条）"
           % (need_traj - avail_traj)))
    gap_bytes = 0
    if not ok2:
        per = float(pool["bytes"]["per_tid_median"])
        gap_bytes = int(round((need_traj - avail_traj) * per))
        gaps.append("池子不够：每臂要 %d 条轨迹，池里只有 %d 条 ⇒ **缺 %d 条**"
                    "（按池内每条中位 %.2f GB ⇒ 约 **%.0f GB** 生成物）"
                    % (need_traj, avail_traj, need_traj - avail_traj,
                       per / 1e9, gap_bytes / 1e9))

    # ---------- F3 块数可得
    need_blk = int(design["n_blocks"])
    avail_blk = int(pool["n_blocks_paired"])
    ok3 = need_blk <= avail_blk
    put("F3", ok3,
        "**块数可得**：这一批要 **%d** 块；池里 think/no_think **可配对**的块 **%d** %s"
        % (need_blk, avail_blk, "✅" if ok3 else "❌（缺 %d 块）" % (need_blk - avail_blk)))
    if not ok3:
        gaps.append("池子不够：要 %d 块，可配对块只有 %d ⇒ **缺 %d 块**"
                    % (need_blk, avail_blk, need_blk - avail_blk))

    # ---------- F4 同剂量多格**可构造**
    pf_avail = [float(x) for x in pool["pos_frac"]["available"]]
    if design["dose_mode"] == "fixed":
        need_at_one = cpt
        ok4 = need_at_one <= len(pf_avail)
        put("F4", ok4,
            "**同一剂量下的多格可构造**：固定剂量 ⇒ 一条轨迹的 %g 格**全在同一个剂量** ⇒ "
            "现有批的**剂量轴是 n_sites（k 阶梯）**、scope 是**口径开关**（量的是不同的东西）⇒ "
            "两者在固定剂量下都被钉死 ⇒ ⇒ 只剩 **pos_frac** 这条轴；可用的 pos_frac **%d** 个 %s"
            % (need_at_one, len(pf_avail), "✅" if ok4 else "❌（不够 %g 个）"
               % (need_at_one - len(pf_avail))))
        if not ok4:
            gaps.append("设计口径：同一剂量下要 %g 格，但可用的 pos_frac 只有 %d 个 ⇒ 造不出来"
                        % (need_at_one, len(pf_avail)))
    else:
        put("F4", True,
            "**同一剂量下的多格可构造**：剂量扫描设计 ⇒ **不适用**（每个 (tid, n_sites) 只有一格 ⇒ "
            "m 靠**跨剂量**堆 ⇒ ⚠ 那正是 244.65「零格」的来源）")

    # ---------- F5 pos_frac 轴：**已测过没有**（红 ⇒ 进前提清单，⛔ 不是失败）
    pf_meas = [float(x) for x in pool["pos_frac"]["measured"]]
    pf_used = [float(x) for x in design["pos_fracs"]]
    unmeasured = sorted(x for x in pf_used if x not in pf_meas)
    ok5 = not unmeasured
    put("F5", ok5,
        "**pos_frac 轴的已测性**：这一批要用 pos_frac %s；**已测过**的只有 %s ⇒ %s"
        % (pf_used, pf_meas,
           "✅ 全是已测取值" if ok5 else "⚠⚠ **未量到**：%s（已测取值里没有）" % unmeasured))
    if not ok5:
        premises.append("pos_frac 取值 %s **未量到**（已测过的只有 %s）⇒ "
                        "**这一批同时是这条轴的首次测量** ⇒ 它的结论**不能**被说成「已验证过这条轴」"
                        % (unmeasured, pf_meas))

    # ---------- F6 n_eff 逐条可查
    bad_eff = [t["tid"] for t in pool["tids"] if not (isinstance(t.get("n_eff"), (int, float))
                                                      and t["n_eff"] > 0)]
    ok6 = not bad_eff
    put("F6", ok6,
        "**n_eff 逐条可查**：池里 %d 条轨迹，n_eff 缺失或非正的 %d 条 %s"
        % (len(pool["tids"]), len(bad_eff), "✅" if ok6 else "❌（%s）" % bad_eff[:3]))
    if not ok6:
        gaps.append("池子自相矛盾：%d 条轨迹的 n_eff 不可用" % len(bad_eff))

    # ---------- F7 池子自洽
    n_bytes_ok = sum(1 for t in pool["tids"] if float(t.get("bytes", 0)) > 0)
    ok7 = (int(pool["n_tid"]) == len(pool["tids"]) == n_bytes_ok
           and int(pool["sources"]["generated_dir"]["bytes"]) ==
           sum(int(t["bytes"]) for t in pool["tids"]))
    put("F7", ok7,
        "**池子自洽**：n_tid %d / tids %d / 有生成物的 %d 条 / 字节合计自洽 %s"
        % (int(pool["n_tid"]), len(pool["tids"]), n_bytes_ok,
           "✅" if ok7 else "❌（快照与逐条清单对不上）"))
    if not ok7:
        gaps.append("生成池快照自相矛盾（n_tid / tids / 字节合计对不上）⇒ 快照过期或被改过")

    # ---------- F8：**需求本身**就超过可得吗（⛔ 需求从规模机械取，⛔ 不写死）
    #   ⚠⚠⚠ 这条才是**决定性**的：F2 只查「**声明** ≤ 可得」⇒ 一个「刚好够」的声明
    #   就能骗过它 ⇒ ⇒ 必须另查「**需求** ≤ 可得」⇒ ⇒ 若需求本身就超了 ⇒
    #   ⇒ **这一批在今天的池子上根本发不出去**（⇒ 无论怎么设计都不行）。
    req = [P._req_of(size.get(L)) for L in range(len(size))]
    req = [int(x) for x in req if x is not None]
    need_total = sum(req) if len(req) == len(size) else None
    ok8 = (need_total is not None and need_total <= avail_traj)
    per_tid = float(pool["bytes"]["per_tid_median"])
    # ⚖⚠⚖ **只算一次**：F8 的缺口字节数在这里算好 ⇒ 印出来的与返回的**必然一致**
    gap_bytes_req = 0
    if need_total is not None and need_total > avail_traj:
        gap_bytes_req = int(round((need_total - avail_traj) * per_tid))
    if need_total is None:
        put("F8", False, "**需求本身**是否超过可得：逐档需求算不出来 ⇒ 判红")
        gaps.append("逐档需求算不出来 ⇒ 无法判断这一批发不发得出去")
    else:
        put("F8", ok8,
            "**需求本身**是否超过可得：功效预算要求 **%d** 条/臂（逐档 %s）；"
            "池里**总共**只有 **%d** 条 ⇒ %s"
            % (need_total, "/".join(str(x) for x in req), avail_traj,
               "✅ 需求可满足" if ok8 else "❌（**连需求本身**都差 %d 条）"
               % (need_total - avail_traj)))
        if not ok8:
            gaps.append("池子不够：**连需求本身**都超过可得（需求 %d 条/臂 vs 可得 %d 条）"
                        "⇒ **这一批在今天的池子上发不出去** ⇒ 缺 **%d** 条轨迹"
                        "（按池内每条中位 %.2f GB ⇒ 约 **%.0f GB** 生成物）"
                        % (need_total, avail_traj, need_total - avail_traj,
                           per_tid / 1e9, gap_bytes_req / 1e9))
    need_total_req = need_total
    blocking_fail = [f for f in F_BLOCKING if not R2.get(f, False)]
    premise_fail = [f for f in F_PREMISE if not R2.get(f, False)]
    can = not blocking_fail
    kind = None
    if not can:
        kinds = set(F_KIND[f] for f in blocking_fail)
        kind = "池子" if kinds == {"池子"} else ("设计" if kinds == {"设计"} else "两者")

    RP2 = []
    RP2.append("")
    RP2.append("=" * 78)
    RP2.append("【A】⚖⚖ **可得性体检**（244.70）——「这一批**能不能**跑出来」")
    RP2.append("=" * 78)
    RP2.append("  ⚖ 生成池快照：`%s`（%d 条轨迹 / 可配对块 %d / 生成物 %.1f GB）"
               % (pool.get("snapshot_id", "?"), int(pool["n_tid"]),
                  int(pool["n_blocks_paired"]),
                  float(pool["sources"]["generated_dir"]["bytes"]) / 1e9))
    RP2.append("  ⚖ 设计：dose_mode = %s ｜ 一条轨迹服务 %d 个档 ｜ 每条 %g 格 ｜ pos_frac %s"
               % (design["dose_mode"], n_layer, cpt, pf_used))
    RP2.append("")
    RP2.append("  ⚖⚖ 244.68 预检器的设计检查（**复用**，⛔ 不重写）：")
    for ln in RP:
        if ln.strip().startswith("[") or ln.strip().startswith("判据"):
            RP2.append("    " + ln)
    RP2.append("")
    RP2.append("  ⚖⚖⚖ 本工具的判据（每条**能红**）：")
    for ln in lines:
        RP2.append(ln)
    RP2.append("")
    RP2.append("  ⚖⚠⚠⚠ **244.68 的 D4 与本工具 F1 的差别**（口径更正，⛔ 不改 244.68 源码）：")
    RP2.append("    D4 用的是「一条轨迹服务 **4** 个档」⇒ 门槛 **12 格**（那是**剂量扫描**设计的数）")
    RP2.append("    ⇒ 固定剂量设计下一条轨迹**只服务 %d 个档** ⇒ 门槛 **%d 格** ⇒ 本工具按 F1 判"
               % (n_layer, need_cells))
    RP2.append("    ⇒ ⛔ 用 244.68 的 D4 去判**固定剂量**设计会**假红**（⇒ 见账本 244.70 的更正段）")
    RP2.append("")
    RP2.append("=" * 78)
    RP2.append("【B】⚖⚖⚖ **判决**")
    RP2.append("=" * 78)
    if can:
        RP2.append("  ✅ **能回答**（设计层面 ＋ **可得性层面**都过）")
        RP2.append("     ⇒ 这一批**跑得出来**，且跑完**能**给出：固定剂量下 w / rand "
                   "**各改判多少题**、**差多少 pp**、**p 值**与**区间**")
        RP2.append("     ⇒ ⛔ 具体数**未量到**（这一批还没跑）")
    else:
        RP2.append("  🔴 **不能回答** —— 缺口 %d 条（%s类）：" % (len(gaps), kind or "—"))
        for i, g in enumerate(gaps, 1):
            RP2.append("    %d) %s" % (i, g))
    if premise_fail:
        RP2.append("")
        RP2.append("  ⚠⚠⚠ **前提（未量到）** —— ⛔ **不许**说成「已验证」：")
        for i, p in enumerate(premises, 1):
            RP2.append("    %d) %s" % (i, p))
    if can:
        RP2.append("")
        RP2.append("  ⚠⚠ **前提（规划假设，⛔ 不是事实）**：")
        RP2.append("    · 逐档正号率 `expected_proportions` 是**规划假设** ⇒ 逐档需求 **%s** 是"
                   "**规划量**（⛔ 不是判决）⇒ 若真实效应**更小** ⇒ 需求**更大** ⇒ 而可得只有 %d 条"
                   "⇒ ⇒ 这一批的「能回答」**只**在**假设成立**时成立"
                   % ("/".join(str(x) for x in req) if req else "?", avail_traj))
    RP2.append("")
    RP2.append("  ⚖ 判据：%d/%d 通过（其中 **%d 条**判据红在**前提**上，不判「不能回答」）"
               % (sum(1 for v in R2.values() if v), len(R2), len(premise_fail)))
    RP2.append("")

    verdict = {
        "can_answer": can,
        "blocking_fail": blocking_fail,
        "premise_fail": premise_fail,
        "gaps": gaps,
        "premises": premises,
        "kind": kind,
        "need_traj": need_traj,
        "need_total_req": need_total_req,
        "req_per_band": req,
        "avail_traj": avail_traj,
        "gap_bytes": gap_bytes,
        "gap_bytes_req": gap_bytes_req,
        "need_cells": need_cells,
        "n_layer": n_layer,
        "n_blocks_needed": need_blk,
        "n_blocks_avail": avail_blk,
    }
    return RP2, R2, verdict


def run_feasible(design, pool, prereg_path=PREREG):
    """⚖ 跑一遍 ⇒ `(文本行, {判据号: bool}, 判决字典)`。"""
    RP, R, V = build_report(design, pool, prereg_path=prereg_path)
    return RP, R, V


# ---------------------------------------------------------------- 自检
def _mk_design(d, tmpdir, name="d.json"):
    import tempfile
    p = os.path.join(tmpdir, name)
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
    return p


def _pool(over=None):
    p = read_pool(POOL_DEFAULT)
    if over:
        p = dict(p)
        p.update(over)
    return p


def _design(over=None):
    d = {
        "design_id": "自检用设计",
        "n_blocks": 4,
        "tracks_per_arm": 4,
        "cells_per_track": 3,
        "tracks_per_band": {"w": [1, 1, 1, 1], "rand": [1, 1, 1, 1]},
        "expected_proportions": {"w": [0.29, 0.29, 0.29, 0.29],
                                 "rand": [0.14, 0.14, 0.14, 0.14]},
        "convention": {"n_bands": 4, "boundary": "prod",
                       "quantile": "inclusive", "zero_span": "keep"},
        "dose_mode": "fixed",
        "pos_fracs": [0.25, 0.5, 0.75],
    }
    if over:
        d.update(over)
    return d


def selftest():
    """⚖⚠⚖ **每条判据都要有红化反例**（⛔ 恒绿的判据不许留）。"""
    import tempfile
    ok_all = True
    n = [0]

    def chk(tid, cond, note):
        n[0] += 1
        nonlocal ok_all
        if not cond:
            ok_all = False
            print("[FAIL] %s：%s" % (tid, note))

    pool = _pool()
    tmp = tempfile.mkdtemp(prefix="fdfeas_")
    try:
        # ---- 基线：**用满现成池**的设计 ⇒ 能回答
        #   ⚠⚠⚠ 注意：基线必须是「**需求本身**能被池子满足」的设计 ⇒ 否则 F8 必红
        #   ⇒ ⇒ 「设计得刚好」**不够** ⇒ 还得「池子够得着需求」（这正是 F8 的意义）
        d = _design({"n_blocks": 28, "tracks_per_arm": 56, "cells_per_track": 3,
                     "tracks_per_band": {"w": [14, 14, 14, 14], "rand": [14, 14, 14, 14]},
                     "expected_proportions": {"w": [0.90, 0.90, 0.90, 0.90],
                                              "rand": [0.10, 0.10, 0.10, 0.10]}})
        RP, R, V = run_feasible(d, pool)
        chk("T1", V["can_answer"], "用满现成池的设计应判「能回答」（红项：%s）"
            % V["blocking_fail"])
        chk("T1b", all(R[f] for f in F_BLOCKING), "基线设计的阻断类判据应全绿")
        chk("T1c", V["need_cells"] == 3,
            "固定剂量下 m≥3 门槛应为 3 格（得 %r）" % V["need_cells"])
        chk("T1d", V["need_total_req"] is not None and V["need_total_req"] <= int(pool["n_tid"]),
            "基线设计的逐档需求之和必须 ≤ 可得轨迹数（得 %r）" % V.get("need_total_req"))

        # ---- F1：固定剂量下门槛是 3（⛔ 不是 12）
        d2 = dict(d, cells_per_track=2)
        _RP2, R2, V2 = run_feasible(d2, pool)
        chk("T2", (not R2["F1"]) and (not V2["can_answer"]),
            "每条轨迹 2 格 < 门槛 3 ⇒ F1 必须红")

        # ---- F1b：剂量扫描设计下门槛是 12（**同一份公式** ⇒ 两种设计都验）
        d3 = _design({"dose_mode": "sweep", "cells_per_track": 12})
        _RP3, R3, V3 = run_feasible(d3, pool)
        chk("T3", V3["need_cells"] == 12,
            "剂量扫描下门槛应为 12 格（得 %r）" % V3["need_cells"])
        chk("T3b", R3["F1"], "12 格 ⇒ F1 应绿")
        d3b = _design({"dose_mode": "sweep", "cells_per_track": 3})
        _RP3b, R3b, _V3b = run_feasible(d3b, pool)
        chk("T3c", (not R3b["F1"]), "剂量扫描下 3 格 ⇒ F1 必须红")

        # ---- F2：轨迹数不够
        d4 = dict(d, tracks_per_band={"w": [100, 100, 100, 100],
                                   "rand": [100, 100, 100, 100]},
                  tracks_per_arm=400)
        _RP4, R4, V4 = run_feasible(d4, pool)
        chk("T4", (not R4["F2"]) and (not V4["can_answer"]),
            "要 400 条/臂、池里 60 条 ⇒ F2 必须红且判「不能回答」")
        chk("T4b", V4["kind"] == "池子", "缺口应判为「池子类」（得 %r）" % V4["kind"])
        chk("T4c", V4["gap_bytes"] > 0, "缺口必须被量化成字节数")

        # ---- F3：块数不够
        d5 = dict(d, n_blocks=999)
        _RP5, R5, V5 = run_feasible(d5, pool)
        chk("T5", (not R5["F3"]) and (not V5["can_answer"]),
            "要 999 块、可配对 30 块 ⇒ F3 必须红")

        # ---- F4：同剂量多格造不出来
        d6 = dict(d, cells_per_track=9, pos_fracs=[0.25, 0.5, 0.75, 0.9, 0.8, 0.7,
                                              0.6, 0.55, 0.45])
        _RP6, R6, _V6 = run_feasible(d6, pool)
        chk("T6", (not R6["F4"]), "同剂量要 9 格、可用 pos_frac 只有 3 个 ⇒ F4 必须红")

        # ---- F5：pos_frac 未测过 ⇒ 红**但不**判「不能回答」（⇒ 进前提清单）
        d7 = dict(d, pos_fracs=[0.25, 0.5, 0.75])
        _RP7, R7, V7 = run_feasible(d7, pool)
        chk("T7", (not R7["F5"]), "用了未测过的 pos_frac ⇒ F5 必须红")
        chk("T7b", V7["can_answer"], "F5 红是**前提**不是失败 ⇒ 不该判「不能回答」")
        chk("T7c", len(V7["premises"]) == 1, "未量到的取值必须进前提清单")
        d7b = dict(d, pos_fracs=[0.5])
        _RP7b, R7b, V7b = run_feasible(d7b, pool)
        chk("T7d", R7b["F5"] and not V7b["premises"],
            "只用已测过的 pos_frac ⇒ F5 绿、无前提")
        # ---- T7e：**印出来的**前提必须与返回的一致（⛔ 印了 ≠ 判了）
        #   ⚖⚠⚖⚖ 这一条必须**锚在前提段上**（⛔ 不能只查「报告里有没有那三个字」）
        #   ⇒ 因为 F5 的**判据行里**本来就写着「未量到」⇒ ⇒ 只查那三个字 ⇒
        #   ⇒ 「前提类判据被清空」与「前提段不印」这两条变异**照样绿** ⇒ ⇒ **恒绿**
        #   ⇒ ⇒ 所以这里查两件事：**前提段的标题在** ＋ **返回的那条前提的内容在**
        txt7 = "\n".join(_RP7)
        chk("T7e", ("前提（未量到）" in txt7)
            and len(V7["premises"]) >= 1
            and V7["premises"][0][:20] in txt7,
            "报告里必须印出「未量到」的**前提段**，且印出来的内容与返回的前提一致")
        chk("T7f", (("能回答" in txt7) == V7["can_answer"]),
            "报告里的判决与返回的判决必须一致")

        # ---- F6：n_eff 缺失 ⇒ 红
        bad_pool = json.loads(json.dumps(pool))
        bad_pool["tids"][0]["n_eff"] = 0
        _RP8, R8, _V8 = run_feasible(_design(), bad_pool)
        chk("T8", (not R8["F6"]), "某条 tid 的 n_eff=0 ⇒ F6 必须红")

        # ---- F7：池子不自洽 ⇒ 红
        bad_pool2 = json.loads(json.dumps(pool))
        bad_pool2["n_tid"] = 999
        _RP9, R9, _V9 = run_feasible(_design(), bad_pool2)
        chk("T9", (not R9["F7"]), "n_tid 与 tids 对不上 ⇒ F7 必须红")

        # ---- T10：判决**只算一次** ⇒ 印出来的与返回的一致
        d10 = dict(d, tracks_per_band={"w": [100, 100, 100, 100],
                                   "rand": [100, 100, 100, 100]})
        RP10, R10, V10 = run_feasible(d10, pool)
        txt = "\n".join(RP10)
        chk("T10", ("不能回答" in txt) == (not V10["can_answer"]),
            "报告里的判决与返回的判决必须一致")
        chk("T10b", ("缺 %d 条" % (400 - int(pool["n_tid"]))) in txt,
            "缺口清单必须印出确切的缺多少条")

        # ---- T10c：F8 —— **需求本身**超过可得 ⇒ 必须红（这一条才是决定性的）
        d10c = _design({"tracks_per_band": {"w": [200, 200, 200, 200],
                                             "rand": [200, 200, 200, 200]},
                        "tracks_per_arm": 800})
        _RP10c, R10c, V10c = run_feasible(d10c, pool)
        chk("T10c", (not R10c["F8"]),
            "功效预算的需求（%s 条/臂）超过可得 %d 条 ⇒ F8 必须红"
            % (V10c.get("need_total_req"), int(pool["n_tid"])))
        chk("T10d", V10c["need_total_req"] is not None
            and V10c["need_total_req"] > int(pool["n_tid"]),
            "F8 必须真的算出需求（得 %r）" % V10c.get("need_total_req"))
        chk("T10e", any("发不出去" in g for g in V10c["gaps"]),
            "F8 红时缺口清单必须说「发不出去」")

        # ---- T15：F8 的缺口**字节数**必须被量化，且与 (需求-可得)×每条中位 **独立复算**一致
        #   ⚖⚠⚖ 这一条是变异 **M13** 的落点（⛔ 字节数被抹成 0 ⇒ 缺口就**没被量化**）
        exp15 = int(round((V10c["need_total_req"] - int(pool["n_tid"]))
                          * float(pool["bytes"]["per_tid_median"])))
        chk("T15", V10c["gap_bytes_req"] == exp15 and V10c["gap_bytes_req"] > 0,
            "F8 红时的缺口字节数必须被量化，且与独立复算一致（得 %r，期望 %r）"
            % (V10c.get("gap_bytes_req"), exp15))

        # ---- T10f：**全绿**设计 ⇒ 判「能回答」（⇒ 证明这套判据不是恒红）
        d10f = dict(d)
        _RP10f, R10f, V10f = run_feasible(d10f, pool)
        chk("T10f", V10f["can_answer"],
            "用满现成池的设计应判「能回答」（红项：%s）" % V10f["blocking_fail"])
        chk("T10g", V10f["need_total_req"] is not None,
            "全绿设计也必须报出需求")

        # ---- T11：坏输入 ⇒ **干净**的 HardFail（⛔ 不是 traceback）
        try:
            read_design(_mk_design({"design_id": "x"}, tmp, "bad1.json"))
            chk("T11", False, "缺键的设计描述必须抛 HardFail")
        except HardFail:
            chk("T11", True, "")
        except Exception as e:
            chk("T11", False, "缺键的设计描述抛的是 %r，不是 HardFail" % type(e))
        try:
            read_design(_mk_design(dict(_design(), dose_mode="bogus"), tmp, "bad2.json"))
            chk("T12", False, "dose_mode 非法必须抛 HardFail")
        except HardFail:
            chk("T12", True, "")
        except Exception as e:
            chk("T12", False, "dose_mode 非法抛的是 %r，不是 HardFail" % type(e))
        try:
            read_design(_mk_design(dict(_design(), pos_fracs=[]), tmp, "bad3.json"))
            chk("T13", False, "pos_fracs 为空必须抛 HardFail")
        except HardFail:
            chk("T13", True, "")
        except Exception as e:
            chk("T13", False, "pos_fracs 为空抛的是 %r，不是 HardFail" % type(e))
        try:
            read_design(_mk_design(dict(_design(), pos_fracs=["x"]), tmp, "bad4.json"))
            chk("T14", False, "pos_fracs 含非数字必须抛 HardFail")
        except HardFail:
            chk("T14", True, "")
        except Exception as e:
            chk("T14", False, "pos_fracs 含非数字抛的是 %r，不是 HardFail" % type(e))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("自检：%d 通过 / %d 失败" % (n[0] if ok_all else 0, 0 if ok_all else 1))
    return 0 if ok_all else 1


def main():
    import argparse
    ap = argparse.ArgumentParser(description="固定剂量那一批的「可得性体检」（零 GPU）")
    ap.add_argument("--design", default=None)
    ap.add_argument("--pool", default=POOL_DEFAULT)
    ap.add_argument("--prereg", default=PREREG)
    ap.add_argument("--emit-design-template", action="store_true")
    ap.add_argument("--emit-pool-template", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    try:
        if a.selftest:
            return selftest()
        if a.emit_design_template:
            print(json.dumps(design_template(), ensure_ascii=False, indent=1))
            return 0
        if a.emit_pool_template:
            print(json.dumps({"snapshot_id": "把这一份的来源写清",
                              "n_tid": 0, "n_blocks_paired": 0,
                              "tids": [], "bytes": {"per_tid_median": 0},
                              "pos_frac": {"measured": [], "available": []},
                              "sources": {"generated_dir": {"bytes": 0}}},
                             ensure_ascii=False, indent=1))
            return 0
        if not a.design:
            print("用法：--design <json>（或 --selftest / --emit-design-template）",
                  file=sys.stderr)
            return 2
        design = read_design(a.design)
        pool = read_pool(a.pool)
        RP, R, V = run_feasible(design, pool, prereg_path=a.prereg)
        print("\n".join(RP))
        return 0 if V["can_answer"] else 1
    except (HardFail, pre().HardFail) as e:
        # ⚖⚠⚖ **两种同名 HardFail 都不是一个类型** ⇒ 两个都捕 ⇒ 干净返回 2（⛔ 不是 traceback）
        print("PRECOND_FAIL: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
