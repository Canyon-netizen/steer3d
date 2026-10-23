#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""fixed_dose_density_audit.py —— 「固定剂量」在**生产剂量口径**下**到底成不成立**（零 GPU）。

⚖⚖⚖⚖⚖ **为什么要有这个工具**（244.72 的起因，⚠ **一句话**）：
   244.71 的发批清单校验器按 **`n_sites / n_eff`** 判「剂量固定」，
   而**分析管线**（`dose_confound_audit.frac_of`）按
   **`n_sites / (P + max(1, int(n_gen·pos_frac)) − 1)`**（= **注入密度**）算剂量分数
   ⇒ ⇒ 两套定义**只在 `pos_frac = 0.5` 时相等**
   ⇒ ⇒ 而既有 137 条真记录的 `pos_frac` **全为 0.5** ⇒ ⇒ **这条断层在真数据上测不出来**
   ⇒ ⇒ 在「固定 n_sites、3 个 pos_frac 复制格」的那一批上 ⇒
        校验器口径的档内极差 = **1.0000 倍**（⇒ 「是固定剂量」）
        生产口径的档内极差   = **2.86 倍**  （⇒ ⛔ **不是固定剂量**）
   ⇒ ⇒ ⇒ **244.71 的校验器会把一个「剂量扫描」当成「固定剂量」放行**

⚖⚖⚖ **本工具的口径**：⛔ **不另写第二套密度定义** ⇒ 密度一律走
   `dose_confound_audit.frac_of`（**生产机械**）⇒ ⇒ 判据与**分析管线**逐位同源。

⚖⚖⚖ **判据 D1–D7**（每条**能红** ⇒ 自检里逐条配红化反例）：
   D1  每格的**生产剂量分数**算得出来吗？（P/n_gen 缺 ⇒ 该轨迹剂量**未量到** ⇒ 前提类）
   D2  同一条轨迹的**复制格密度相等**吗？⇒ **这才是「固定剂量」**（阻断）
   D3  每格的密度落在规格的 `frac ± tol` 内吗？（阻断）
   D4  **供给**：现有阶梯能否在每个 (轨迹, pos_frac) 下供出命中档？（阻断）
   D5  **分析断层**：分析管线的分档器会不会把复制格**拆到不同档** ⇒ 档内 m？（阻断）
   D6  两套口径的差（⛔ **诊断**，⛔ 不参与判决）
   D7  pos_frac 轴**已测过**吗？（前提类 ⇒ ⛔ 不判失败）

⚖⛔ **本工具不发批、不改格清单格式、不改探针、不产生任何判决数**
   ⇒ 它只回答「**这一批的设计在生产口径下成不成立**」。

⚖ 用法：
   `fixed_dose_density_audit.py --audit --cells <tsv> --spec <json>`
   `fixed_dose_density_audit.py --supply --route <json>`
   `fixed_dose_density_audit.py --selftest`
"""

import io
import os
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

POOL_DEFAULT = os.path.join(HERE, "fixed_dose_pool_snapshot.json")
CELLS_COLUMNS = ("tid", "scope", "n_sites", "pos_frac")
D_TOL_DEFAULT = 0.005
# ⚖⚖⚖ 244.76：**生效口径的默认来源 = 老预登记**（⇒ 老口径下数值**逐位不变**）
#   ⇒ 变体预登记（合池 `n_bands = 1`）走 `--prereg` 指过去 ⇒ ⇒ **两条口径并存、互不覆盖**
PREREG_DEFAULT = os.path.join(REPO, ".cache", "xcheck", "R6_FIXED_DOSE_PREREG.md")
# ⚖ 244.76：**变体**预登记（合池 `n_bands = 1`，244.76 新签）⇒ 与老预登记**并存**
PREREG_VARIANT = os.path.join(REPO, ".cache", "xcheck", "R6_FIXED_DOSE_VARIANT_PREREG.md")


class HardFail(Exception):
    pass


def _load(name):
    p = os.path.join(HERE, name)
    assert os.path.isfile(p), "缺文件：%s" % name
    return io.open(p, encoding="utf-8").read()


def dconf():
    import dose_confound_audit
    return dose_confound_audit


def dlayer():
    import dose_layer_audit
    return dose_layer_audit


def fdf():
    import fixed_dose_feasible
    return fixed_dose_feasible


def fda():
    import fixed_dose_audit
    return fixed_dose_audit


def read_convention(prereg_path=None):
    """⚖⚖⚖ 读**生效口径**（档数 / 档边界 / 分位点算法 / 零跨度）⇒ **只从预登记的机器块读**。

    ⚖⚖⚖⚖⚖ **244.76**：这个工具原来把四个口径**写死**在代码里
       （`dose_cells(zero_span="keep")` ＋ `dose_bands_v(boundary="prod",
       quantile="inclusive", n_bands=4)`）⇒ ⇒ 违反 244.66 的宪法
       「口径**只写一处**：分析脚本从机器可读块读，⛔ **代码里一个口径都不写死**」
       ⇒ ⇒ **它是四个工具里唯一的例外**（preflight / feasible / audit 都读预登记）
       ⇒ ⇒ 现在改成**从预登记读** ⇒ ⇒ **老预登记写的正是那四个值 ⇒ 数值逐位不变**
       ⇒ ⇒ ⇒ 「改口径不许改数」这条判据的第一版就在这里（见 T12）。

    ⛔ **不许兜底**：预登记缺键 / 取值非法 ⇒ `Cfg` 直接 HardFail
       （⛔ 默认值兜底 ⇒ 「口径被改」就看不见了 ⇒ 那是宪法明令禁止的）。
    """
    p = prereg_path or PREREG_DEFAULT
    F = fda()
    # ⚖⚠⚖⚖⚖ 244.76：**两个模块各有各的 `HardFail`** ⇒ `fixed_dose_audit.read_prereg`
    #   抛的是**它那个**类 ⇒ ⇒ 若不转成本模块的类 ⇒ ⇒ 异常会**逃出去**
    #   ⇒ ⇒ 自检会**崩**、变异台会把每一条都记成「崩」（⛔ 崩 ≠ 抓到）⇒ ⇒ 这里必须转。
    try:
        raw = F.read_prereg(p)
        cfg = F.Cfg(raw)
    except F.HardFail as e:
        raise HardFail("读预登记失败（%s）：%s" % (p, e))
    return {"n_bands": int(cfg.n_bands), "boundary": cfg.boundary,
            "quantile": cfg.quantile, "zero_span": cfg.zero_span, "prereg": p}


def _read_json(path, what):
    try:
        return __import__("json").load(io.open(path, encoding="utf-8"))
    except Exception as e:
        raise HardFail("读不了 %s（%r）：%s" % (what, path, e))


def read_cells(path):
    """⚖ 读**四列**格清单 ⇒ `(表头, 行)`。⛔ 列数不对的行也返回（由判据去判）。"""
    rows = []
    head = None
    for i, line in enumerate(io.open(path, encoding="utf-8"), 1):
        s = line.rstrip("\n")
        if not s.strip():
            continue
        cols = s.split("\t")
        if head is None:
            head = [c.strip() for c in cols]
            continue
        rows.append({"lineno": i, "cols": cols})
    return head, rows


def tid_info(pool):
    """⚖ 每条轨迹的 `P` / `n_gen` / `n_eff`（来自**生成池快照** ⇒ ⛔ 不重算）。"""
    out = {}
    for t in pool["tids"]:
        out[t["tid"]] = {"P": t.get("P"), "n_gen": t.get("n_gen"),
                         "n_eff": t.get("n_eff")}
    return out


def density_of(n_sites, P, n_gen, pos_frac):
    """⚖⚖⚖ **生产剂量分数（注入密度）** ⇒ **复用生产机械** `frac_of`（⛔ 不另写一份）。

    ⚖ 为什么要走 `frac_of` 而不是自己算：分析管线算剂量分数走的就是它
    ⇒ ⇒ 本工具与**分析管线**逐位同源 ⇒ ⇒ 判据不会与分析口径分叉。"""
    DC = dconf()
    rec = {"inject_n_sites": int(n_sites), "P": int(P), "n_gen": int(n_gen),
           "pos_frac": float(pos_frac)}
    return DC.frac_of(rec)


def ladder_rungs(base):
    """⚖ 既有格清单 ⇒ 每条轨迹的 k 阶梯（**真身**，⛔ 不重算阶梯）。"""
    p = base["cell_list"]["path"]
    lad = collections.OrderedDict()
    if not os.path.isfile(p):
        return lad
    for line in io.open(p, encoding="utf-8"):
        s = line.strip()
        if not s:
            continue
        parts = s.split("\t")
        if len(parts) >= 3 and parts[1] == "k":
            try:
                lad.setdefault(parts[0], []).append(int(parts[2]))
            except ValueError:
                continue
    return lad


def parse_spec(path):
    sp = _read_json(path, "发批规格")
    dose = sp.get("dose") or {}
    return {
        "spec_id": sp.get("spec_id", "（未命名）"),
        "route": sp.get("route") or {},
        # ⚖ 244.76：**表头是格式的第二个维度** ⇒ 判据 D9 要拿规格声明的列名来比
        "columns": [str(c) for c in (sp.get("columns") or CELLS_COLUMNS)],
        "scope": str(dose.get("scope", "k")),
        "frac": float(dose.get("frac", 0.25)),
        "tol": float(dose.get("tol", D_TOL_DEFAULT)),
        "pos_fracs": [float(x) for x in (sp.get("route") or {}).get("pos_fracs", [])],
        "n_blocks": int((sp.get("route") or {}).get("n_blocks", 0)),
        "cells_per_track": int((sp.get("route") or {}).get("cells_per_track", 0)),
    }


# ================================================================ 主审计
def audit_cells(spec, cells_path, pool, base, conv=None):
    """⚖ 在**生产剂量口径**下核一份格清单 ⇒ 返回 `(判据行, 判决字典)`。
    ⚖⚖⚖ **判决只算一次**（印出来的与返回的一致 ⇒ 报告层算完再返回）。

    ⚖⚖⚖ 244.76：`conv` = **生效口径**（从预登记读）⇒ ⛔ 代码里不再写死任何口径取值。
    """
    DC = dconf()
    conv = conv or read_convention()
    R = {}
    rows = []
    gaps = []
    premises = []

    def put(gid, ok, detail):
        R[gid] = bool(ok)
        rows.append("  [%s] %-5s %s" % ("PASS" if ok else "FAIL", gid, detail))

    def put_premise(gid, ok, detail):
        R[gid] = bool(ok)
        rows.append("  [前提] %-5s %s" % (gid, detail))

    def put_diag(detail):
        rows.append("  [诊断] %-5s %s" % ("", detail))

    ti = tid_info(pool)
    target = float(spec["frac"])
    tol = float(spec["tol"])

    head, crows = read_cells(cells_path)
    good = [r for r in crows if len(r["cols"]) == 4]
    by_tid = collections.OrderedDict()
    for r in good:
        tid, sc, ns, pf = r["cols"][0], r["cols"][1], r["cols"][2], r["cols"][3]
        by_tid.setdefault(tid, []).append({"scope": sc, "n_sites": ns,
                                           "pos_frac": pf, "lineno": r["lineno"]})

    # ---------- D1 每格的密度算得出来吗
    missing_info = []
    dens = {}
    for tid, cells in by_tid.items():
        info = ti.get(tid)
        if not info or not info["P"] or not info["n_gen"]:
            missing_info.append(tid)
            continue
        for c in cells:
            try:
                dens[(tid, c["lineno"])] = density_of(
                    int(c["n_sites"]), info["P"], info["n_gen"], float(c["pos_frac"]))
            except (ValueError, TypeError, HardFail):
                missing_info.append(tid)
    uniq_missing = sorted(set(missing_info))
    ok1 = not uniq_missing
    put("D1", ok1,
        "**每格的生产剂量分数算得出来吗**（要 P / n_gen）：%d 条轨迹里**算不出**的 **%d** 条 %s"
        % (len(by_tid), len(uniq_missing), "✅" if ok1 else "❌（%s）" % uniq_missing[:3]))
    if not ok1:
        premises.append("%d 条轨迹缺 P / n_gen ⇒ 它们的剂量**未量到** ⇒ 本工具**没核**到它们"
                        % len(uniq_missing))

    # ---------- D2 同轨迹复制格的密度相等（**这才是「固定剂量」**）
    mixed = []
    spreads = []
    for tid, cells in sorted(by_tid.items()):
        vals = []
        for c in cells:
            v = dens.get((tid, c["lineno"]))
            if v is not None:
                vals.append(v)
        if len(vals) < 2:
            continue
        sp = max(vals) - min(vals)
        spreads.append(sp)
        if sp > tol:
            mixed.append((tid, sp))
    ok2 = (not mixed) and bool(by_tid)
    put("D2", ok2,
        "**同一条轨迹的复制格密度相等**（⇒ **这才是「固定剂量」**）：%d 条轨迹里密度**不一致**的 "
        "**%d** 条 %s（容差 %.4f）"
        % (len(by_tid), len(mixed), "✅" if ok2 else "❌（%s）"
           % [(t, "%.4f" % s) for t, s in mixed[:3]], tol))
    if not ok2:
        gaps.append("%d 条轨迹的复制格**密度不等** ⇒ 那一批**不是固定剂量**（⇒ 剂量与 pos_frac 混淆）"
                    % len(mixed))

    # ---------- D3 每格密度落在 frac ± tol
    off = []
    for (tid, ln), v in sorted(dens.items()):
        if abs(v - target) > tol:
            off.append((tid, ln, v))
    ok3 = bool(dens) and not off
    put("D3", ok3,
        "**每格密度落在 frac ± tol 内**（frac=%.4f tol=%.4f）：%d 格里**不落**的 **%d** 格 %s"
        % (target, tol, len(dens), len(off), "✅" if ok3 else "❌（%s）"
           % [(t, "%.4f" % v) for t, _l, v in off[:3]]))
    if not ok3:
        gaps.append("%d 格的密度不落在 frac ± tol 内 ⇒ 剂量口径没钉死" % len(off))

    # ---------- D4 供给：现有阶梯能否供出每个 (轨迹, pos_frac) 的命中档
    lad = ladder_rungs(base)
    supply_miss = []
    supply_tot = 0
    for tid, cells in sorted(by_tid.items()):
        info = ti.get(tid)
        if not info or not info["P"] or not info["n_gen"]:
            continue
        for c in cells:
            supply_tot += 1
            den = None
            try:
                den = DC.denom_of({"inject_n_sites": int(c["n_sites"]), "P": int(info["P"]),
                                   "n_gen": int(info["n_gen"]),
                                   "pos_frac": float(c["pos_frac"])})
            except Exception:
                den = None
            if den is None:
                supply_miss.append((tid, c["pos_frac"], "算不出分母"))
                continue
            hits = [v for v in lad.get(tid, [])
                    if abs(v / float(den) - target) <= tol]
            if len(hits) != 1:
                supply_miss.append((tid, c["pos_frac"], "命中 %d 档" % len(hits)))
    ok4 = (not supply_miss) and bool(supply_miss is not None)
    put("D4", ok4,
        "**供给**：现有 k 阶梯能否在每个 (轨迹, pos_frac) 下供出**恰好一档**命中 frac±tol："
        "%d 个组合里**供不出**的 **%d** 个 %s"
        % (supply_tot, len(supply_miss), "✅" if ok4 else "❌（%s）"
           % [(t, p, w) for t, p, w in supply_miss[:3]]))
    if not ok4:
        gaps.append("现有阶梯在 %d / %d 个 (轨迹, pos_frac) 组合下**供不出**命中档 ⇒ "
                    "⇒ 那一份格清单**造不出来**（⇒ 要新阶梯 ⇒ 生成侧 ⇒ 要点头）"
                    % (len(supply_miss), supply_tot))

    # ---------- D5 分析断层：分档器会不会把复制格拆到不同档
    split_tids = []
    ms = collections.Counter()
    if dens and not uniq_missing:
        recs = []
        for tid, cells in sorted(by_tid.items()):
            info = ti[tid]
            for c in cells:
                recs.append({"tid": tid, "inject_scope": c["scope"],
                             "inject_n_sites": int(c["n_sites"]),
                             "P": int(info["P"]), "n_gen": int(info["n_gen"]),
                             "pos_frac": float(c["pos_frac"]),
                             "p9_lo_meas": 0.1, "p9_hi_meas": 0.2})
        try:
            # ⚖⚖⚖ 244.76：四个口径**全部来自预登记**（⛔ 原来这里是四个写死的字面量
            #   ⇒ ⇒ 违反 244.66 宪法「代码里一个口径都不写死」）
            ks, fr = DC.dose_cells(recs, zero_span=conv["zero_span"])
            _qs, bands = DC.dose_bands_v(ks, fr, boundary=conv["boundary"],
                                          quantile=conv["quantile"],
                                          n_bands=int(conv["n_bands"]))
            band_of = collections.defaultdict(set)
            for i, (_lab, sub) in enumerate(bands):
                for r in sub:
                    band_of[r["tid"]].add(i)
                cb = collections.OrderedDict()
                for r in sub:
                    cb.setdefault(r["tid"], []).append(r)
                for t2, cs2 in cb.items():
                    ms[len(cs2)] += 1
            split_tids = [t for t, s in band_of.items() if len(s) > 1]
            detail = ("分析管线的 **%d 档**（口径来自预登记）把复制格**拆开**的轨迹 **%d / %d** 条；"
                      "档内 m 分布 **%s**（设计意图 m=%d）"
                      % (int(conv["n_bands"]), len(split_tids), len(band_of), dict(ms),
                         int(spec.get("cells_per_track") or 3)))
            ok5 = not split_tids
        except Exception as e:
            ok5 = False
            detail = "分析管线的分档器**跑不了**（%r）⇒ ⇒ 这一批的分析**未量到**" % (e,)
    else:
        ok5 = False
        detail = "有轨迹缺 P / n_gen ⇒ 分母算不出 ⇒ 分档**未量到**"
    put("D5", ok5, "**分析断层**（分析管线自己的分档器）：" + detail)
    if not ok5:
        gaps.append("复制格会被分析管线的剂量分档**拆到不同档** ⇒ 档内 m 不成立 ⇒ "
                    "「固定剂量」的读数在分析口径下**带着 pos_frac 混淆**")

    # ---------- D8：当前分析管线**有没有合池模式**？
    #    ⚖⚖⚖ 为什么必须单独判：「固定剂量」⇒ **剂量轴没有离散度可分** ⇒
    #    4 个分位切点会**切穿复制组**（见 D5）⇒ ⇒ 唯一正确的分析口径是**合池**（1 档）
    #    ⚖⚠⚖⚖ **244.74 更新**：244.72 时 `dose_bands_v` **拒绝 `n_bands < 2`**
    #    ⇒ ⇒ D8 当时是**红**的（「当前管线没有合池模式」⇒ 「跑完也算不出判决数」）
    #    ⇒ ⇒ **244.74 把 `n_bands = 1` 那一支补进管线** ⇒ ⇒ **D8 现在应当转绿**
    pooled_ok = False
    pooled_why = ""
    try:
        #   ⚖⚖⚖ 244.76：`n_bands = 1` 是**被探的那项能力**（⛔ **不是**口径取值）
        #   ⇒ ⇒ 档边界 / 分位点算法一律取**预登记**的（⛔ 代码里不再写死）
        DC.dose_bands_v([{"tid": "x"}], [0.25], boundary=conv["boundary"],
                        quantile=conv["quantile"], n_bands=1)
        pooled_ok = True
        pooled_why = "分档器**接受** n_bands=1 ⇒ 合池模式**可用**"
    except Exception as e:
        pooled_why = ("分档器**拒绝** n_bands=1（%s）⇒ ⇒ 当前管线**没有合池模式** ⇒ ⇒ "
                      "「固定剂量」这一批在**当前管线**下**算不出判决数**"
                      % (str(e).strip().split("\n")[0][:120]))
    ok8 = pooled_ok
    put("D8", ok8, "**当前分析管线有没有合池模式**（固定剂量必须合池）：" + pooled_why)
    if not ok8:
        gaps.append("当前分析管线**没有合池模式**（`dose_bands_v` 拒绝 n_bands=1）⇒ ⇒ "
                    "「固定剂量」这一批**在当前管线下算不出判决数** ⇒ ⇒ 要么改管线，"
                    "要么那一批**别跑**")

    # ---------- D9：**表头**（格式的**第二个**维度，不止列数）—— 必须存在且与规格一致
    #    ⚖⚖⚖⚖⚖ 244.76 新增：原来 `read_cells` **无条件吃第一行** ⇒ ⇒ 喂**无表头**的文件
    #    ⇒ ⇒ 第一格被**静默吞掉** ⇒ ⇒ **没有任何判据会报** ⇒ ⇒ 典型的「静默数据丢失」
    #    （与本项目「崩 ≠ 抓到」「恒绿护栏要能红」同类）
    #    ⇒ ⇒ 现在有一条**能红**的判据盯着它：**表头缺失 / 列名不符 ⇒ 红**。
    #    ⚖⚖ **244.75 登记的数不受影响**：`fixed_dose_density_target.py` 的 `read_ladder`
    #    （行 131–153）**不吃表头** ⇒ ⇒ 14/28/308 逐条成立 ✅
    expect_cols = [str(c).strip() for c in (spec.get("columns") or CELLS_COLUMNS)]
    head_cols = [str(c).strip() for c in (head or [])]
    ok9 = (head_cols == expect_cols)
    put("D9", ok9,
        "**表头存在且列名与规格 `columns` 一致**（格式的**第二个**维度，不止列数）："
        "表头 **%s** vs 规格 **%s** %s"
        % (head_cols, expect_cols, "✅" if ok9 else "❌（分析侧会**静默吞掉第一格**）"))
    if not ok9:
        gaps.append("格清单的**表头**与规格 `columns` 不一致（或**根本没有表头**）⇒ ⇒ "
                    "分析侧 `read_cells` 会**静默吞掉第一格**（⛔ 静默数据丢失）⇒ ⇒ "
                    "要么补上表头，要么 ⛔ **不许跑这一批**")

    # ---------- D6 两套口径的差（⛔ 诊断，⛔ 不参与判决）
    neff_spread = 0.0
    neff_ratio = 1.0
    for tid, cells in sorted(by_tid.items()):
        info = ti.get(tid)
        if not info or not info["n_eff"]:
            continue
        vals = []
        for c in cells:
            try:
                vals.append(float(c["n_sites"]) / float(info["n_eff"]))
            except (ValueError, TypeError):
                pass
        if len(vals) >= 2:
            neff_spread = max(neff_spread, max(vals) - min(vals))
            if min(vals) > 0:
                neff_ratio = max(neff_ratio, max(vals) / min(vals))
    ana_spread = max(spreads) if spreads else 0.0
    ana_ratio = 1.0
    for tid, cells in sorted(by_tid.items()):
        vals = [dens[(tid, c["lineno"])] for c in cells if (tid, c["lineno"]) in dens]
        if len(vals) >= 2 and min(vals) > 0:
            ana_ratio = max(ana_ratio, max(vals) / min(vals))
    put_diag("**两套「剂量分数」定义的档内离散**：校验器口径（n_sites / n_eff）极差 **%.4f**"
             "（max/min = **%.4f 倍**）；生产口径（n_sites / denom_of(pos_frac)）"
             "极差 **%.4f**（max/min = **%.4f 倍**）（⛔ **诊断**，⛔ 不参与判决）"
             % (neff_spread, neff_ratio, ana_spread, ana_ratio))

    # ---------- D7 pos_frac 轴的已测性（前提类）
    pf_meas = [float(x) for x in pool["pos_frac"]["measured"]]
    unmeasured = sorted(set(x for x in spec.get("pos_fracs", []) if x not in pf_meas))
    ok7 = not unmeasured
    put_premise("D7", ok7,
                "**pos_frac 轴的已测性**（⚠ **前提类** ⇒ ⛔ **不判失败**）：这一批要用 pos_frac %s；"
                "**已测过**的只有 %s ⇒ %s"
                % (spec.get("pos_fracs", []), pf_meas,
                   "✅ 全是已测取值" if ok7 else "⚠⚠ **未量到**：%s" % unmeasured))
    if not ok7:
        premises.append("pos_frac 取值 %s **未量到**（已测过的只有 %s）⇒ "
                        "**这一批同时是这条轴的首次测量**" % (unmeasured, pf_meas))

    # ⚖⚖⚖ 244.76：阻断集 **加了 D9**（表头/列名）⇒ ⇒ 244.74 登记的「阻断集 = {D2,D3,D4,D5}」
    #   ⇒ ⇒ **244.76 起 = {D2,D3,D4,D5,D9}**（⚠ 这是**新增一条判据**带来的事实变化，
    #   ⇒ ⇒ 不是把红改成绿 ⇒ ⇒ 老口径下 D1–D8 的**判决数字逐位不变**）
    blocking = [g for g in ("D2", "D3", "D4", "D5", "D8", "D9") if not R.get(g, False)]
    can = not blocking
    return rows, {
        "R": R, "rows": rows, "gaps": gaps, "premises": premises,
        "can": can, "blocking": blocking, "conv": conv,
        "n_tid": len(by_tid), "n_cells": len(good),
        "dens": dens, "supply_miss": supply_miss, "supply_tot": supply_tot,
        "ana_spread": ana_spread, "neff_spread": neff_spread,
        "split_tids": split_tids, "m_hist": dict(ms),
        "head": head,
    }


def render_audit(spec, v, cells_path):
    out = []
    out.append("=" * 78)
    out.append("【密度口径审计】⚖⚖⚖ 「固定剂量」在**生产剂量口径**下成不成立（244.72，零 GPU）")
    out.append("=" * 78)
    out.append("  ⚖ 规格：`%s`" % spec["spec_id"])
    out.append("  ⚖ 清单：`%s`（%d 行 / %d 条轨迹）" % (cells_path, v["n_cells"], v["n_tid"]))
    out.append("  ⚖ 密度口径：**n_sites / (P + max(1, int(n_gen·pos_frac)) − 1)**"
               "（⛔ **复用** `dose_confound_audit.frac_of` ⇒ 与**分析管线**逐位同源）")
    # ⚖⚖⚖ 244.76：**生效口径必须印出来**（从预登记读 ⇒ 数字与口径**一起**可核对）
    cv = v.get("conv") or {}
    out.append("  ⚖ **生效分析口径**（来自预登记 `%s` ⇒ ⛔ 代码里不写死）："
               "档数 **%s** ｜ 档边界 **%s** ｜ 分位点算法 **%s** ｜ 零跨度 **%s**"
               % (cv.get("prereg", "（未指定）"), cv.get("n_bands"),
                  cv.get("boundary"), cv.get("quantile"), cv.get("zero_span")))
    out.append("")
    for ln in v["rows"]:
        out.append(ln)
    out.append("")
    if v["can"]:
        out.append("  ✅ **这一批在生产剂量口径下成立**（阻断类判据全绿）")
    else:
        out.append("  🔴 **这一批在生产剂量口径下不成立**（阻断：%s）" % ", ".join(v["blocking"]))
    out.append("  ⛔ **本工具不发批** ⇒ ⇒ 发不发 / 跑不跑 ⇒ **要用户点头**")
    if v["gaps"]:
        out.append("")
        out.append("  ⚠⚠⚖ **缺口**：")
        for g in v["gaps"]:
            out.append("    · " + g)
    if v["premises"]:
        out.append("")
        out.append("  ⚠⚠⚖ **前提（未量到）** —— ⛔ **不许**说成「已验证」：")
        for i, p in enumerate(v["premises"], 1):
            out.append("    %d) %s" % (i, p))
    out.append("")
    return "\n".join(out)


# ================================================================ 供给审计
def audit_supply(route, pool, base, target=None, tol=None):
    """⚖ **供给审计**：现有 k 阶梯（pos_frac=0.5 下生成的）能不能在每个
    (轨迹, pos_frac) 下供出「生产密度 = target」的那一档。

    ⚠⚠⚖⚖⚖ **244.76**：原来 `target=0.25` / `tol=0.005` 是**函数默认值**
       ⇒ ⇒ 那是**第二处**写着剂量口径（真源在**规格**的 `dose.frac` / `dose.tol`）
       ⇒ ⇒ 违反「口径只写一处」⇒ ⇒ 现在**不许兜底**：不给就 HardFail。

    ⚖⚠⚖ **为什么必须查这条**：阶梯是**在 pos_frac=0.5 下生成**的 ⇒
    同一个 n_sites 在 0.25 / 0.75 下**密度不同** ⇒ ⇒ 要在别的 pos_frac 下
    命中同一密度 ⇒ **需要另一个 n_sites** ⇒ ⇒ 那个 n_sites **在不在阶梯上**，
    本地量得到 ⇒ ⇒ **量不到就别假设它在**。"""
    if target is None or tol is None:
        raise HardFail("供给审计必须显式给出目标密度与容差（⛔ 不许默认值兜底 ⇒ "
                       "剂量口径的真源是**规格**的 `dose.frac` / `dose.tol`）")
    DC = dconf()
    ti = tid_info(pool)
    lad = ladder_rungs(base)
    pfs = [float(x) for x in route.get("pos_fracs", [])]
    out = []
    miss = []
    tot = 0
    for tid in sorted(lad):
        info = ti.get(tid)
        if not info or not info["P"] or not info["n_gen"]:
            continue
        for pf in pfs:
            tot += 1
            den = DC.denom_of({"inject_n_sites": 1, "P": int(info["P"]),
                               "n_gen": int(info["n_gen"]), "pos_frac": pf})
            hits = [v for v in lad[tid] if abs(v / float(den) - target) <= tol]
            if len(hits) != 1:
                miss.append((tid, pf, len(hits)))
    out.append("=" * 78)
    out.append("【供给审计】⚖⚖⚖ 现有阶梯供不供得出「生产密度固定」的那一批（244.72，零 GPU）")
    out.append("=" * 78)
    out.append("  ⚖ 目标密度 **%.4f ± %.4f**（生产口径）｜ pos_frac %s"
               % (target, tol, pfs))
    out.append("  ⚖ 阶梯：%d 条轨迹 / %d 档（**在 pos_frac=0.5 下生成** ⇒ ⛔ 别的 pos_frac 下"
               "同一 n_sites 的**密度不同**）" % (len(lad), sum(len(v) for v in lad.values())))
    out.append("")
    out.append("  ⚖⚖⚖ **供不出恰好一档的 (轨迹, pos_frac) 组合：%d / %d**" % (len(miss), tot))
    for tid, pf, n in miss[:12]:
        out.append("    · %-34s pos_frac=%.2f ⇒ 命中 %d 档" % (tid, pf, n))
    if len(miss) > 12:
        out.append("    · …（其余 %d 个略）" % (len(miss) - 12))
    out.append("")
    if miss:
        out.append("  🔴 **供给断层**：现有阶梯**供不出** ⇒ ⇒ 那一批的格清单**造不出来**")
        out.append("     ⇒ ⇒ 要**新阶梯**（在 0.25 / 0.75 下各生成一次）⇒ ⇒ **生成侧** ⇒ ⛔ 要用户点头")
    else:
        out.append("  ✅ 现有阶梯供得出")
    out.append("")
    return "\n".join(out), {"miss": miss, "tot": tot, "n_ladder_tid": len(lad)}


# ================================================================ 自检
def _mk(tmp, name, text):
    p = os.path.join(tmp, name)
    io.open(p, "w", encoding="utf-8").write(text)
    return p


def _fake_cells_ladder(pool, base, target=0.25, tol=D_TOL_DEFAULT):
    """⚖ 造一份**当前世界形状**的清单：用**真阶梯**上那一档 n_sites，
    **三个 pos_frac 共用同一个 n_sites** ⇒ ⇒ 正是 244.71 模板印的那个形状。

    ⚖⚠⚖ 它**故意**不满足密度口径（D2/D3 会红）⇒ ⇒ 它的用处是当**反例**。

    ⚖⚖⚖ 244.76 **回补默认值**的因（⛔ 不是「口径写死」）：
       `pooled_mode_audit.py`（**244.74 入库的另一个工具**）在两处调用
       `_fake_cells_fixed(pool, base)` ⇒ ⇒ 我一度把 `target`/`tol` 改成**必填**
       ⇒ ⇒ **那个工具直接崩**（`TypeError`）⇒ ⇒ **本轮引入的红**
       ⇒ ⇒ 所以默认值**必须留着**。
       ⚖⚖⚖ 而这两个值是**夹具的测试输入**（⛔ **不是分析口径**）：
       ⇒ ⇒ 分析口径（档数/边界/分位/零跨度）**只从预登记读**（见 `read_convention`）
       ⇒ ⇒ 发批口径（ρ*/tol）**只从规格读**（见 `parse_spec`）⇒ ⇒ 这里的 0.25/0.005
       只是**夹具**，⛔ 不参与任何判决。"""
    ti = tid_info(pool)
    lad = ladder_rungs(base)
    DC = dconf()
    lines = ["\t".join(CELLS_COLUMNS)]
    for tid in sorted(lad):
        info = ti.get(tid)
        if not info or not info["P"] or not info["n_gen"]:
            continue
        den = DC.denom_of({"inject_n_sites": 1, "P": int(info["P"]),
                           "n_gen": int(info["n_gen"]), "pos_frac": 0.5})
        hits = [v for v in lad[tid] if abs(v / float(den) - target) <= tol]
        if len(hits) != 1:
            continue
        for pf in (0.25, 0.5, 0.75):
            lines.append("\t".join([tid, "k", str(hits[0]), str(pf)]))
    return "\n".join(lines) + "\n"


def _fake_cells_fixed(pool, base, target=0.25, tol=D_TOL_DEFAULT):
    """⚖ 造一份**密度真的固定**的清单（**正向夹具**）：每个 pos_frac 的 n_sites
    按**它自己的分母**缩放 ⇒ ⇒ 三个复制格的**密度相等** ⇒ ⇒ 这才是「固定剂量」。

    ⚖⚠⚖ 这份清单的 n_sites **不在现有阶梯上** ⇒ ⇒ D4（供给）仍红
    ⇒ ⇒ **这正是本轮要量出来的东西**：密度口径下**需要新阶梯**。

    ⚖⚖⚖ 244.76：默认值**必须留着**（`pooled_mode_audit.py` 在两处用两参调用它
    ⇒ ⇒ 改成必填 ⇒ ⇒ 那个工具崩 ⇒ ⇒ 本轮引入的红）⇒ ⇒ 详见
    `_fake_cells_ladder` 的同一段说明。"""
    ti = tid_info(pool)
    lad = ladder_rungs(base)
    DC = dconf()
    lines = ["\t".join(CELLS_COLUMNS)]
    for tid in sorted(lad):
        info = ti.get(tid)
        if not info or not info["P"] or not info["n_gen"]:
            continue
        ns = {}
        for pf in (0.25, 0.5, 0.75):
            den = DC.denom_of({"inject_n_sites": 1, "P": int(info["P"]),
                               "n_gen": int(info["n_gen"]), "pos_frac": pf})
            ns[pf] = max(1, int(round(target * den)))
        for pf in (0.25, 0.5, 0.75):
            lines.append("\t".join([tid, "k", str(ns[pf]), str(pf)]))
    return "\n".join(lines) + "\n"


def selftest(pool_path=POOL_DEFAULT, base_path=None):
    """⚖⚠⚖ **每条判据都要有红化反例**（⛔ 恒绿的判据不许留）。"""
    import tempfile
    import shutil
    pool = fdf().read_pool(pool_path)
    if base_path is None:
        base_path = os.path.join(HERE, "fixed_dose_cost_baseline.json")
    base = _read_json(base_path, "成本基线")
    ok, bad = [], []

    def chk(name, cond, msg):
        (ok if cond else bad).append(name)
        if not cond:
            print("[FAIL] %s：%s" % (name, msg))

    route = {"route_id": "selftest", "strategy": "measure_first",
             "n_blocks": 2, "cells_per_track": 3, "pos_fracs": [0.25, 0.5, 0.75],
             "arms": ["w", "rand"]}
    spec = {"spec_id": "selftest", "route": route, "scope": "k",
            "frac": 0.25, "tol": D_TOL_DEFAULT,
            # ⚖ 244.76：**表头是格式的第二个维度** ⇒ 判据 D9 要拿它来比
            "columns": list(CELLS_COLUMNS),
            "pos_fracs": [0.25, 0.5, 0.75], "n_blocks": 2, "cells_per_track": 3}
    tmp = tempfile.mkdtemp(prefix="fdden_")
    try:
        txt = _fake_cells_ladder(pool, base, spec["frac"], spec["tol"])
        p = _mk(tmp, "cells.tsv", txt)
        _rows, v = audit_cells(spec, p, pool, base)
        chk("T1", v["n_tid"] >= 1, "夹具自己造不出格（n_tid=%d）" % v["n_tid"])
        chk("T1b", v["R"]["D1"], "D1 应绿（P/n_gen 齐）")

        # ---- D2：把某条轨迹的复制格改成**密度不等** ⇒ 必须红
        lines = txt.split("\n")
        for i, ln in enumerate(lines):
            if ln.startswith("aime") and ln.endswith("0.25"):
                parts = ln.split("\t")
                parts[2] = str(int(parts[2]) * 2)      # ⇒ n_sites 变 ⇒ 密度变
                lines[i] = "\t".join(parts)
                break
        p2 = _mk(tmp, "mixed.tsv", "\n".join(lines))
        _r, v2 = audit_cells(spec, p2, pool, base)
        chk("T2", (not v2["R"]["D2"]) and (not v2["can"]),
            "复制格密度不等 ⇒ D2 必须红且判「不成立」")

        # ---- D3：把某格的 n_sites 改到 frac±tol 之外 ⇒ D3 必须红
        lines3 = txt.split("\n")
        for i, ln in enumerate(lines3):
            if ln.startswith("aime") and ln.endswith("0.5"):
                parts = ln.split("\t")
                parts[2] = str(int(parts[2]) // 2)
                lines3[i] = "\t".join(parts)
                break
        p3 = _mk(tmp, "off.tsv", "\n".join(lines3))
        _r, v3 = audit_cells(spec, p3, pool, base)
        chk("T3", (not v3["R"]["D3"]) and (not v3["can"]),
            "某格密度不落 frac±tol ⇒ D3 必须红")

        # ---- D4：供给断层（⛔ 用**真阶梯**量 ⇒ ⛔ 不许用手造的数）
        _txt, sv = audit_supply(route, pool, base, spec["frac"], spec["tol"])
        chk("T4", isinstance(sv["miss"], list) and sv["tot"] > 0,
            "供给审计没跑起来")
        # ---- T4b：供给审计的**负样**（⚠⚠⚖ 244.72 更正：原来那条是**恒真重言式**）
        #   ⚠⚠⚖ 原式 `(len(miss)>0) == (tot-len(miss)!=tot)` ⇒ 右边 ⇔ `miss != 0`
        #   ⇒ ⇒ **和左边是同一个命题** ⇒ ⇒ 恒真 ⇒ ⇒ 恒绿 ⇒ ⇒ 恒绿不是绿，是**量不到东西**
        #   ⇒ ⇒ 改成**负样**：给路线加一个阶梯供不出的 pos_frac（0.125）
        #   ⇒ ⇒ 供给审计**必须**多报出 miss ⇒ ⇒ 「miss 永远空着」这类改动会被抓住
        route2 = dict(route, pos_fracs=list(route["pos_fracs"]) + [0.125])
        _txt2, sv2 = audit_supply(route2, pool, base, spec["frac"], spec["tol"])
        chk("T4b", (sv2["tot"] > sv["tot"]) and (len(sv2["miss"]) > len(sv["miss"])),
            "给路线加一个供不出的 pos_frac（0.125）⇒ 供给审计必须多报 miss"
            "（tot %d→%d，miss %d→%d）" % (sv["tot"], sv2["tot"],
                                          len(sv["miss"]), len(sv2["miss"])))
        chk("T4c", (not v["R"]["D4"]) == (len(v["supply_miss"]) > 0),
            "D4 的判决必须与「供不出的组合数」一致（D4 被改成恒真时要被抓到）")

        # ---- D5：分档器拆开复制格 ⇒ D5 必须红（**用真阶梯 + 真密度**）
        _r5, v5 = audit_cells(spec, p, pool, base)
        chk("T5", (not v5["R"]["D5"]) == (len(v5["split_tids"]) > 0),
            "D5 的判决与「拆分轨迹数」不一致")

        # ---- D6：诊断行必须**印出来**（⛔ 印不出来就等于没说）
        chk("T6", any("[诊断]" in ln for ln in v["rows"]),
            "两套口径的差必须印成诊断行")

        # ---- D7：前提类 ⇒ ⛔ 不许印成 FAIL
        chk("T7", any("[前提]" in ln for ln in v["rows"]),
            "D7 必须印成 [前提]（⛔ 不是 FAIL）")
        chk("T7b", not any(ln.startswith("  [FAIL] D7") for ln in v["rows"]),
            "D7 ⛔ 不许印成 [FAIL]")
        chk("T7c", any("pos_frac" in p and "未量到" in p for p in v["premises"]),
            "前提清单里必须写明 pos_frac 未量到（⇒ 前提被抹掉时要被抓到）")

        # ---- D1：清单里有一条**不在池子**的轨迹 ⇒ 它的剂量**未量到** ⇒ D1 必须红
        ghost = txt.rstrip("\n") + "\nghost__tid\tk\t100\t0.5\n"
        p8 = _mk(tmp, "ghost.tsv", ghost)
        _r, v8 = audit_cells(spec, p8, pool, base)
        chk("T8", (not v8["R"]["D1"]),
            "清单里有池子外的轨迹 ⇒ D1 必须红（它的剂量**未量到**）")

        # ---- T9（⚖⚖⚖ **正向夹具**）：密度**真的固定**的那份清单 ⇒ D2/D3/D5 必须**全绿**
        #      ⇒ ⇒ 证明这三条判据**不是恒红** ⇒ ⇒ 也证明「换成 n_eff 那一支」会被抓住
        txt9 = _fake_cells_fixed(pool, base, spec["frac"], spec["tol"])
        p9 = _mk(tmp, "fixed.tsv", txt9)
        _r9, v9 = audit_cells(spec, p9, pool, base)
        chk("T9", v9["R"]["D2"] and v9["R"]["D3"],
            "密度真的固定的那份清单 ⇒ D2/D3 必须**绿**（证明这两条不是恒红；实际 D2=%s D3=%s）"
            % (v9["R"]["D2"], v9["R"]["D3"]))
        # ⚖⚠⚖⚖⚖ 244.74：**极性翻转**（**事实变了**，⛔ 不是把红改成绿来好看）
        #   · 244.72 记的是「当前管线**没有合池模式**」（`dose_bands_v` 拒绝 `n_bands < 2`）
        #   · 244.74 把 `n_bands = 1`（合池）那一支**补进管线** ⇒ ⇒ **D8 转绿**
        #   · ⇒ D5 仍红（4 档会切穿复制组 ⇒ 固定剂量**必须**走合池）
        chk("T9c", (not v9["R"]["D5"]) and (v9["R"]["D8"]),
            "⚖⚖⚖ 密度真的固定 ⇒ 剂量轴**没有离散度可分** ⇒ 当前管线的 4 档会**切穿复制组**"
            "（D5 必须红）⇒ 且 **244.74 起当前管线已有合池模式**（D8 必须**绿**）⇒ ⇒ "
            "「固定剂量」这一批在**当前管线**下**算得出判决数**了（合池口径）"
            "（实际 D5=%s D8=%s）" % (v9["R"]["D5"], v9["R"]["D8"]))
        chk("T9b", not v9["R"]["D4"],
            "密度固定的那份清单的 n_sites **不在现有阶梯上** ⇒ D4（供给）**必须**仍红"
            "（⇒ 这正是本轮要量出来的东西：需要新阶梯）")

        # ---- T10：**表头存在** ⇒ D9 必须绿（正向夹具）⇒ ⇒ 证明 D9 不是恒红
        chk("T10", v["R"]["D9"] and ("D9" not in v["blocking"]),
            "带表头的夹具 ⇒ D9 必须**绿**且**不阻断**（实际 D9=%s 阻断=%s）"
            % (v["R"]["D9"], v["blocking"]))

        # ---- T11：**表头缺失** ⇒ D9 必须红（⛔ 这正是【9.3】那条「静默吞第一格」的护栏）
        #      ⇒ 原来 `read_cells` 无条件吃第一行 ⇒ ⇒ 喂无表头文件 ⇒ **第一格被静默吞掉**
        #      ⇒ ⇒ 没有任何判据会报 ⇒ ⇒ 现在必须**报出来**
        no_head = "\n".join([ln for ln in txt.split("\n") if not ln.startswith("tid\t")])
        p11 = _mk(tmp, "nohead.tsv", no_head)
        _r11, v11 = audit_cells(spec, p11, pool, base)
        chk("T11", (not v11["R"]["D9"]) and ("D9" in v11["blocking"]),
            "喂**无表头**的清单 ⇒ D9 必须红且阻断（原来会**静默吞掉第一格**而无任何判据报）"
            "（实际 D9=%s 阻断=%s）" % (v11["R"]["D9"], v11["blocking"]))

        # ---- T12：**表头列名不符** ⇒ D9 必须红（⛔ 格式的第二个维度）
        bad_head = "\n".join(["tid\tscope\tn_sites\tPOS_FRAC"] + txt.split("\n")[1:])
        p12 = _mk(tmp, "badhead.tsv", bad_head)
        _r12, v12 = audit_cells(spec, p12, pool, base)
        chk("T12", (not v12["R"]["D9"]),
            "表头列名与规格 `columns` 不一致 ⇒ D9 必须红（实际 D9=%s）" % (v12["R"]["D9"],))

        # ---- T13：⚖⚖⚖ **口径去写死的活体验**：D5 必须**跟着预登记走**
        #      ⇒ 老预登记（n_bands = 4）⇒ D5 **红**（4 档切穿复制组）
        #      ⇒ 变体预登记（n_bands = 1 合池）⇒ D5 **绿**（合池不切）
        #      ⇒ ⇒ 证明 D5 **不再**由代码里的字面量决定（⛔ 否则这条判据恒绿 ⇒ 不算数）
        conv_var = read_convention(PREREG_VARIANT)
        _r13, v13 = audit_cells(spec, p9, pool, base, conv_var)
        chk("T13a", (conv_var["n_bands"] == 1) and v13["R"]["D5"],
            "变体预登记（合池 n_bands=1）⇒ D5 必须**绿**（合池不会切穿复制组）"
            "（实际 n_bands=%s D5=%s）" % (conv_var["n_bands"], v13["R"]["D5"]))
        chk("T13b", (not v9["R"]["D5"]),
            "老预登记（n_bands=4）⇒ D5 必须**仍红**（⇒ ⇒ **老口径下数字逐位不变**）"
            "（实际 D5=%s）" % (v9["R"]["D5"],))

        # ---- T14：⛔ 缺预登记 ⇒ HardFail（⛔ 不许用默认值兜底）
        try:
            read_convention(os.path.join(HERE, "_no_such_prereg_24476.md"))
            chk("T14", False, "缺预登记文件必须 HardFail（⛔ 不许兜底）")
        except HardFail:
            chk("T14", True, "缺预登记文件必须 HardFail（⛔ 不许兜底）")

        # ---- T15：⛔ 供给审计**不许**默认值兜底（剂量口径的真源是**规格**）
        try:
            audit_supply(route, pool, base)
            chk("T15", False, "供给审计不给目标密度/容差 ⇒ 必须 HardFail（⛔ 不许兜底）")
        except HardFail:
            chk("T15", True, "供给审计不给目标密度/容差 ⇒ 必须 HardFail（⛔ 不许兜底）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("自检 %d 通过 / %d 失败" % (len(ok), len(bad)))
    return 0 if not bad else 1


def main():
    import argparse
    ap = argparse.ArgumentParser(description="「固定剂量」的生产剂量口径审计（244.72，零 GPU）")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--supply", action="store_true")
    ap.add_argument("--cells", default=None)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--route", default=None)
    ap.add_argument("--pool", default=POOL_DEFAULT)
    ap.add_argument("--baseline", default=os.path.join(HERE, "fixed_dose_cost_baseline.json"))
    # ⚖⚖⚖ 244.76：**生效分析口径从预登记读**（⛔ 原来写死在代码里）
    #   ⇒ 变体预登记（合池 `n_bands = 1`）⇒ `--prereg …/R6_FIXED_DOSE_VARIANT_PREREG.md`
    ap.add_argument("--prereg", default=PREREG_DEFAULT)
    # ⚖⚖⚖ 244.76：剂量口径（ρ* / tol）**真源 = 规格** ⇒ ⛔ 不给默认值兜底
    ap.add_argument("--dose-frac", type=float, default=None)
    ap.add_argument("--dose-tol", type=float, default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    try:
        if a.selftest:
            return selftest(a.pool, a.baseline)
        pool = fdf().read_pool(a.pool)
        base = _read_json(a.baseline, "成本基线")
        if a.supply:
            if not a.spec:
                raise HardFail("--supply 需要 --spec（剂量口径 ρ*/tol **只写在规格里** ⇒ "
                               "⛔ 不许代码里兜底）")
            spec = parse_spec(a.spec)
            route = _read_json(a.route, "路线") if a.route else {}
            frac = a.dose_frac if a.dose_frac is not None else spec["frac"]
            tol = a.dose_tol if a.dose_tol is not None else spec["tol"]
            txt, _sv = audit_supply(route, pool, base, frac, tol)
            print(txt)
            return 0
        if a.audit:
            if not a.cells or not a.spec:
                raise HardFail("--audit 需要 --cells 与 --spec")
            spec = parse_spec(a.spec)
            rows, v = audit_cells(spec, a.cells, pool, base, read_convention(a.prereg))
            print(render_audit(spec, v, a.cells))
            return 0 if v["can"] else 1
        print("用法：--audit --cells <tsv> --spec <json> ｜ --supply --route <json> ｜ --selftest",
              file=sys.stderr)
        return 2
    except HardFail as e:
        print("⛔ %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
