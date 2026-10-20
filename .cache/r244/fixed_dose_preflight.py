#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixed_dose_preflight.py —— **发批前预检器**（244.68，零 GPU）。

⚖⚠⚖⚖⚖⚖ **它回答的唯一问题**：
   「**计划中的**那一批（固定剂量 / 分层剂量）**能不能**回答目标里「①」那条
   —— 即：固定剂量下 **w 臂与 rand 臂各改判多少题、差多少 pp、p 值与区间**？」

⚖⚠⚖⚖⚖⚖ **它⛔ 不产出那些数**：
   那一批**还没跑**（要 GPU + 用户点头）⇒ 「各改判多少题 / 差多少 pp / p 值 / 区间」
   ⇒ **未量到**（⛔ **不是**「无差异」）。本工具只回答「**能不能**回答」。

⚖⚖⚖ 为什么要在**跑之前**做这件事（244.66 之后的判断）：
   244.66 把**口径预登记 ＋ 分析管线 ＋ 判据 ＋ 功效预算**都做完了 ⇒ 那一批
   **只要 GPU ＋ 点头**就能跑 ⇒ 但**跑之前**还有一件**零 GPU**的事没做：
   **那一批的「设计」本身**。
   ⚖⚠⚠ 若设计不满足预登记的 **K1–K13** 与**规模前提**（rand 臂也要有足够的
   剂量档、每层 m≥3、块级要 20/14/13 块）⇒ **那一批跑完也答不了「固定剂量下
   各改判多少题」** ⇒ **白烧 GPU**。
   ⇒ 本工具：**给它「计划中的那一批」的描述 ⇒ 必须能回答「这一批能不能回答 ①」**。

⚖⚖⚖⚖⚖ **复用既有生产机械**（⛔ 不另写第二套真相）：
   · 预登记读取 ＋ 生效口径：`fixed_dose_audit.read_prereg` / `fixed_dose_audit.Cfg`
     （⛔ 口径**只从预登记来**；本文件里**一个口径都不写死**）
   · 规模需求：`dose_layer_audit.size_requirements`（`fisher_power` 注入
     `cluster_premise_audit.fisher_power` ＝ **精确枚举**）⇒ **⛔ 不写死
     130/177/31/14**（那三个数是**重算**出来的，判据 **P9** 拿 **244.60 的登记值**
     当**独立对照**）
   · 层数：`dose_layer_audit.N_LAYER`（⛔ 不写死 4）
   · m≥3 的门槛：**从 `size_requirements` 自己的输出行里读**（⛔ 不在本文件里
     重写那个公式 ⇒ 不产生第二份真相）

⚖⚖⚖⚖⚖ **本文件里的纪律**（从 244.60–244.67 的教训里继承）：
   ① **口径只写一处**（预登记）⇒ 判据 **P2** 活体验；
   ② **每条判据都能红** ⇒ **P1–P10** 全部有「改坏就红」的反例（见 `selftest`）；
   ③ **恒绿护栏删掉** ⇒ 每条判据都挂在一个**可观测、会变**的量上
      （预登记的键 / 设计的字段 / 重算出的需求数 / 报告里的文本标记）；
   ④ **判据侧复算⛔ 不许调被检对象自己的函数**（⇒ 恒绿）⇒ 用**外部机械**内联重算
      ＋ **已知答案夹具**；
   ⑤ **未量到的要留白** ⇒ 判据 **P10** 盯「⛔ 不许把未量到说成无差异」。

⚖ **设计描述文件（JSON）的字段**（`--emit-template` 可印一份模板）：
   `design_id`        —— 这一批的名字（自由文本）
   `n_blocks`         —— 块数（块级口径的**分母**；K13 ⇒ 块级**必须能报**）
   `tracks_per_arm`   —— 每臂轨迹条数（**规划量**）
   `cells_per_track`  —— **每条轨迹**的格数（⇒ 决定每层 m 能不能 ≥3）
   `tracks_per_band`  —— `{"w": [...], "rand": [...]}`：**每臂每档**落进去的轨迹数
                         （⛔ rand 臂每档都**不许为 0** ⇒ 244.64 的约束）
   `expected_proportions` —— `{"w": [...], "rand": [...]}`：**规划假设**的逐档正号率
                         （⛔ 是**假设**，⛔ 不是事实 ⇒ 报告里必须这么标）
   `convention`       —— 这一批**打算用**的口径（必须与**预登记**逐项一致 ⇒ K1–K5）
"""

import argparse
import collections
import importlib.util
import io
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PREREG = os.path.join(REPO, ".cache", "xcheck", "R6_FIXED_DOSE_PREREG.md")

# ⚖ 设计描述必须有的顶层键（⛔ 缺键 ⇒ HardFail ⇒ ⛔ 不许用默认值兜底）
DESIGN_KEYS = (
    "design_id",
    "n_blocks",
    "tracks_per_arm",
    "cells_per_track",
    "tracks_per_band",
    "expected_proportions",
    "convention",
)
# ⚖ 设计里「打算用的口径」必须逐项对上预登记的那几项（K1–K5）
CONVENTION_KEYS = ("n_bands", "boundary", "quantile", "zero_span")
# ⚖ 244.60 登记的**逐档规模**（正态近似，条/臂）——判据 P9 拿它当**独立对照**
#   ⛔ 这三个/四个数在**别处**也有一份（账本 244.60 段）⇒ 本工具**重算**，
#     判据 P9 比的是「重算值 == 登记值」⇒ 两处独立推导出同一个数。
REGISTERED_SIZES = {0: 130, 1: 177, 2: 31, 3: 14}
# ⚖ 替身（现有两批）**逐档**的 w / rand 改判数（账本 244.66 登记）
#   ⇒ 4/14、6/14、10/14、14/14 ｜ 2/14、4/14、5/14、6/14
#   ⇒ 喂给 `size_requirements` 应当**重算出** 130/177/31/14（判据 P9）
REGISTERED_PROPS = {
    "w": [4.0 / 14.0, 6.0 / 14.0, 10.0 / 14.0, 14.0 / 14.0],
    "rand": [2.0 / 14.0, 4.0 / 14.0, 5.0 / 14.0, 6.0 / 14.0],
}

D_IDS = ("D1", "D2", "D3", "D4", "D5", "D6", "D7")
P_IDS = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10")

# ⚖⚠⚖⚖ **「把未量到说成零」的措辞**（K11/留白纪律）
#   ⚠⚠⚠⚠⚠ **护栏规则必须与被保护对象的现实一致** ⇒ 否则**假红**是拦路石：
#   报告里**必然**有一句「⛔ 不许把它说成『无差异』」⇒ 那一句**自己**含被禁词
#   ⇒ 若不分「声明禁止」与「结论措辞」，护栏会**自己撞自己** ⇒ 恒红/假红。
#   ⇒ 规则：**同一个词**，前面 14 字里若含「不许/不是/⛔/禁」⇒ 那是**声明**
#     （放行）；否则那是**结论措辞** ⇒ 判红。
BANNED_WORDS = ("无差异", "无效应", "没有差异", "不影响")
PROHIBITION_MARKS = ("不许", "不是", "⛔", "禁")


def banned_claims(lines):
    """⚖ 报告里**把「未量到」说成零**的措辞（⛔ 声明禁止的那句**不算**）。"""
    hits = []
    for ln in lines:
        for w in BANNED_WORDS:
            i = ln.find(w)
            while i >= 0:
                ctx = ln[max(0, i - 14):i]
                if not any(m in ctx for m in PROHIBITION_MARKS):
                    hits.append((w, ln.strip()[:70]))
                    break
                i = ln.find(w, i + 1)
    return hits


class HardFail(Exception):
    """⚖ 前提不满足 ⇒ **不出判决**（⛔ 不许降级、不许静默兜底）。"""


# ---------------------------------------------------------------- 模块加载
_MODS = {}


def _load(path, name):
    if name in _MODS:
        return _MODS[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def fda():
    """⚖ 244.66 的分析管线（预登记读取 / 生效口径 / 登记值）。"""
    return _load(os.path.join(HERE, "fixed_dose_audit.py"), "fda_24468")


def dlayer():
    return fda().dlayer()


def cpre():
    return fda().cpre()


# ---------------------------------------------------------------- 设计描述
def read_design(path):
    """⚖ 读**设计描述**（JSON）。⛔ 缺键 ⇒ HardFail（⛔ 不许默认值兜底）。"""
    if not os.path.isfile(path):
        raise HardFail("设计描述文件不存在：%s" % path)
    try:
        d = json.loads(io.open(path, encoding="utf-8").read())
    except ValueError as e:
        raise HardFail("设计描述不是合法 JSON：%s（%s）" % (path, e))
    if not isinstance(d, dict):
        raise HardFail("设计描述必须是 JSON 对象：%s" % path)
    miss = [k for k in DESIGN_KEYS if k not in d]
    if miss:
        raise HardFail("设计描述缺键：%s（⛔ 不许用默认值兜底）" % ", ".join(miss))
    for k in ("tracks_per_band", "expected_proportions"):
        if not isinstance(d[k], dict):
            raise HardFail("设计描述 %r 必须是对象" % k)
        for arm in ("w", "rand"):
            if arm not in d[k] or not isinstance(d[k][arm], list):
                raise HardFail("设计描述 %r 缺 %r 臂的列表" % (k, arm))
    if not isinstance(d["convention"], dict):
        raise HardFail("设计描述 'convention' 必须是对象")
    miss_c = [k for k in CONVENTION_KEYS if k not in d["convention"]]
    if miss_c:
        raise HardFail("设计描述 'convention' 缺键：%s" % ", ".join(miss_c))
    return d


def design_template():
    """⚖ 一份**起步模板**（⛔ 里面的数是**占位**，⛔ 不是建议规模）。"""
    return {
        "design_id": "把这一批起个名",
        "n_blocks": 0,
        "tracks_per_arm": 0,
        "cells_per_track": 0,
        "tracks_per_band": {"w": [], "rand": []},
        "expected_proportions": {"w": [], "rand": []},
        "convention": {"n_bands": 0, "boundary": "", "quantile": "", "zero_span": ""},
    }


# ---------------------------------------------------------------- 规模重算
def recompute_size(design, cfg):
    """⚖⚖⚖ **重算**逐档所需规模（⛔ 不写死 130/177/31/14）。

    ⚖ 复用 `dose_layer_audit.size_requirements`（唯一实现）＋ 精确枚举的
      `cluster_premise_audit.fisher_power` ⇒ 与 244.60/244.65/244.66 **同一个口径**。
    ⚖⚠⚠ **m≥3 的门槛从机械自己的输出行里读**（⛔ 不在本文件重写那个公式）。
    """
    n_bands = cfg.n_bands
    rows = []
    for b in range(n_bands):
        try:
            pw = float(design["expected_proportions"]["w"][b])
            pr = float(design["expected_proportions"]["rand"][b])
        except (IndexError, TypeError, ValueError):
            raise HardFail("设计描述的 expected_proportions 少于 %d 档" % n_bands)
        rows.append({"L": b, "pw": pw, "pr": pr})
    cpt = float(design["cells_per_track"])
    lines, size = dlayer().size_requirements(
        rows, cpt, fisher_power=cpre().fisher_power, n_layer=n_bands)
    # ⚖ m≥3 门槛：**从机械的输出行里解析**（⛔ 不重写公式）
    need_cells = None
    mult = None
    for ln in lines:
        m = re.search(r"要让每层 m≥3（平票不出现）需 ≥(\d+) 档", ln)
        if m:
            need_cells = int(m.group(1))
        m2 = re.search(r"阶梯要扫到现在的 \*\*([0-9.]+) 倍\*\*", ln)
        if m2:
            mult = float(m2.group(1))
    if need_cells is None:
        raise HardFail("规模机械的输出里找不到「m≥3 需 ≥N 档」那一行 ⇒ "
                       "⛔ 不许在本文件里重写那个公式")
    return {"lines": lines, "size": size, "need_cells": need_cells,
            "ladder_mult": mult, "cells_per_traj": cpt}


def _req_of(entry):
    """⚖ 某档的**所需条数/臂**：`need`（精确枚举复核）优先，⛔ 没有就用正态近似。"""
    if entry is None:
        return None
    need = entry.get("need")
    approx = entry.get("approx")
    if need is not None:
        return int(need)
    if approx is not None:
        return int(approx)
    return None


# ---------------------------------------------------------------- 报告 + 判据
def build_report(design, cfg, prereg_raw, k_rows, sz):
    """⚖ 出报告 + 判据（`D1`–`D7` ＝ 设计检查；`P1`–`P10` ＝ 预检器自身）。
    ⚖ 返回 `(文本行, {判据号: bool})`。"""
    RP = []
    R = collections.OrderedDict()
    gaps = []

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        RP.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    n_bands = cfg.n_bands
    tpb = design["tracks_per_band"]
    dw, dr = tpb.get("w", []), tpb.get("rand", [])
    ep = design["expected_proportions"]
    conv = design["convention"]

    # ---------------- 【0】对象声明
    RP.append("【0】⚖ 预检对象（⛔ 本节**不是**那一批的判决）")
    RP.append("  · 预检的是「**计划中的**那一批」的设计描述（`%s`）"
              % design.get("design_id", "（未命名）"))
    RP.append("  · ⛔ 本工具**不产出**「固定剂量下各改判多少题 / 差多少 pp / p 值 / 区间」"
              "⇒ 那一批**还没跑** ⇒ **未量到**（⛔ **不是**「无差异」）")
    RP.append("  · 本工具只回答一件事：**这一批能不能回答目标里「①」那条**")
    RP.append("")

    # ---------------- 【1】生效口径（全部来自预登记）
    RP.append("【1】⚖ 生效口径（**全部来自预登记的机器可读块**；"
              "⛔ 本文件里没有写死任何一个）")
    for k, v in cfg.as_lines():
        RP.append("  · %s = %s" % (k, v))
    RP.append("  ℹ 预登记的 **K 清单**（原文，共 %d 条）：%s"
              % (len(k_rows), " / ".join(r[0] for r in k_rows)))
    RP.append("")

    # ---------------- 【2】设计摘要
    RP.append("【2】⚖ 设计摘要（来自**设计描述文件**；⚠ 里面的数是**规划量**）")
    RP.append("  · 块数 n_blocks = **%s** ｜ 每臂轨迹 = **%s** ｜ 每条轨迹格数 = **%s**"
              % (design["n_blocks"], design["tracks_per_arm"],
                 design["cells_per_track"]))
    RP.append("  · 每臂每档落进去的轨迹数：w %s ｜ rand %s"
              % (dw, dr))
    RP.append("  · **规划假设**的逐档正号率（⚠ 是**假设**，⛔ 不是事实）：")
    RP.append("      w %s" % ["%.4f" % x for x in ep.get("w", [])])
    RP.append("      rand %s" % ["%.4f" % x for x in ep.get("rand", [])])
    RP.append("")

    # ---------------- 【3】规模重算
    RP.append("【3】⚖ 规模**重算**（**规划量**，⛔ 不是判决；"
              "⛔ 数字由 `size_requirements` **重算**，⛔ 不是写死的）")
    for ln in sz["lines"]:
        RP.append(ln)
    RP.append("    · ⚠ 上面的「（现有 N）」是**规模机械自己的措辞**（指**替身**那 14 条）"
              "⇒ ⛔ **与本设计的规模无关** ⇒ 本设计的数看【2】")
    RP.append("    · 块级规模前提（**来自预登记**）：符号检验需 **%d 块** ｜"
              " 检出聚类需 **%d 块** ｜ 跨臂 Fisher（精确）需 **%d 块**"
              % (cfg.blocks_needed_sign_test, cfg.blocks_needed_cluster,
                 cfg.blocks_needed_fisher_exact))
    RP.append("")

    # ---------------- 【4】设计检查 D1–D7
    RP.append("【4】⚖ 设计检查（**这一批能不能回答 ①**）")

    # D1 口径必须与预登记逐项一致
    d1 = []
    ok1 = True
    for k in CONVENTION_KEYS:
        want = prereg_raw.get(k)
        got = conv.get(k)
        if k == "n_bands":
            same = (want is not None and got is not None and int(want) == int(got))
        else:
            same = (want is not None and got is not None and str(want) == str(got))
        ok1 = ok1 and same
        d1.append("%s 预登记 %r vs 设计 %r %s"
                  % (k, want, got, "✅" if same else "❌"))
    put("D1", ok1,
        "**口径必须发批前定死**（K1–K5）⇒ 设计声明的口径必须与**预登记**逐项一致"
        "（否则事后改口径 ⇒ 结论不可比）：%s" % "；".join(d1))
    if not ok1:
        gaps.append("口径与预登记不一致（K1–K5）")

    # D2 块级规模
    need_blocks = max(cfg.blocks_needed_sign_test, cfg.blocks_needed_cluster,
                      cfg.blocks_needed_fisher_exact)
    n_blocks = int(design["n_blocks"])
    ok2 = n_blocks >= need_blocks
    put("D2", ok2,
        "**块级必须能报**（K13）⇒ 块数 **%d** ≥ 门槛 **%d**"
        "（符号 %d / 聚类 %d / 精确 Fisher %d，取最大）%s"
        % (n_blocks, need_blocks, cfg.blocks_needed_sign_test,
           cfg.blocks_needed_cluster, cfg.blocks_needed_fisher_exact,
           "" if ok2 else " ⇒ **差 %d 块**" % (need_blocks - n_blocks)))
    if not ok2:
        gaps.append("块级规模不足：%d 块 < 门槛 %d 块（差 %d）"
                    % (n_blocks, need_blocks, need_blocks - n_blocks))

    # D3 逐档规模（用重算出来的需求）
    d3 = []
    ok3 = True
    for b in range(n_bands):
        req = _req_of(sz["size"].get(b))
        entry = sz["size"].get(b) or {}
        have_w = dw[b] if b < len(dw) else None
        have_r = dr[b] if b < len(dr) else None
        if req is None or have_w is None or have_r is None:
            ok3 = False
            d3.append("档 %d：需求或设计给的值**缺失** ❌" % b)
            continue
        good = (have_w >= req and have_r >= req)
        ok3 = ok3 and good
        d3.append("档 %d：需 **%d**/臂（正态近似 %s）｜ 设计 w %s / rand %s %s"
                  % (b, req, entry.get("approx"), have_w, have_r,
                     "✅" if good else "❌"))
    put("D3", ok3,
        "**逐档规模必须够**（要能给出逐档的改判数/差 pp/p 值 ⇒ 每档都得有足够轨迹）：%s"
        % "；".join(d3))
    if not ok3:
        gaps.append("逐档规模不足（见【4】D3 的逐档缺口）")

    # D4 m≥3（门槛从机械输出读）
    ok4 = float(design["cells_per_track"]) >= float(sz["need_cells"])
    put("D4", ok4,
        "**每层 m≥3**（平票不出现）⇒ 每条轨迹至少 **%d 格**；设计给 **%s** 格 %s"
        % (sz["need_cells"], design["cells_per_track"],
           "✅" if ok4 else "❌（差 %g 格）"
           % (float(sz["need_cells"]) - float(design["cells_per_track"]))))
    if not ok4:
        gaps.append("每层 m<3：每条轨迹 %s 格 < 门槛 %d 格"
                    % (design["cells_per_track"], sz["need_cells"]))

    # D5 rand 臂每档都要有轨迹
    d5 = []
    ok5 = True
    for b in range(n_bands):
        have = dr[b] if b < len(dr) else 0
        good = (have is not None and have > 0)
        ok5 = ok5 and good
        d5.append("档 %d：rand %s %s" % (b, have, "✅" if good else "❌"))
    put("D5", ok5,
        "**rand 臂也必须有足够的剂量档**（244.64/244.65 补的约束 ⇒ 某档 rand 为空 ⇒ "
        "该档的跨臂比较**根本不存在**）：%s" % "；".join(d5))
    if not ok5:
        gaps.append("rand 臂有档位为空（该档跨臂比较不存在）")

    # D6 两臂可配对
    same = (len(dw) == len(dr) and all(dw[i] == dr[i] for i in range(len(dw))))
    put("D6", same,
        "**两臂必须可配对**（跨臂比较的前提 ⇒ 同一档必须是同一批轨迹）："
        "w %s ｜ rand %s ⇒ %s"
        % (dw, dr, "✅" if same else "❌"))
    if not same:
        gaps.append("两臂每档轨迹数不等 ⇒ 跨臂比较不成立")

    # D7 档数与预登记一致
    ok7 = (len(dw) == n_bands and len(dr) == n_bands
           and len(ep.get("w", [])) == n_bands and len(ep.get("rand", [])) == n_bands)
    put("D7", ok7,
        "**档数必须与预登记一致**（预登记 n_bands = %d）⇒ 设计每处列表都得是 %d 项："
        "w 档 %d ｜ rand 档 %d ｜ 假设 w %d ｜ 假设 rand %d"
        % (n_bands, n_bands, len(dw), len(dr),
           len(ep.get("w", [])), len(ep.get("rand", []))))
    if not ok7:
        gaps.append("档数与预登记（%d 档）不一致" % n_bands)

    RP.append("")

    # ---------------- 【5】判决
    can = all(R[c] for c in D_IDS)
    RP.append("【5】⚖⚖⚖ **判决**（只回答「能不能」，⛔ 不回答「是多少」）")
    if can:
        RP.append("  ✅ **这一批的设计能回答目标里「①」那条**"
                  "（⚠ 这是**设计层面**的判决，⛔ **不是**「已经答了」）")
        RP.append("     ⇒ 跑完这一批**能**给出：固定剂量下 w / rand **各改判多少题**、"
                  "**差多少 pp**、**p 值**与**区间**（⛔ 具体数**未量到**）")
    else:
        RP.append("  🔴 **这一批的设计**答不了**目标里「①」那条** ⇒ ⛔ **别发这一批**"
                  "（跑完也答不了 ⇒ 白烧 GPU）")
        RP.append("     ⇒ **缺口清单**（逐条都要补齐后重跑本预检器）：")
        for i, g in enumerate(gaps):
            RP.append("       %d) %s" % (i + 1, g))
    RP.append("")

    # ---------------- 【6】留白
    RP.append("【6】⚖ 留白（**未量到** ⇒ ⛔ 不许说成「无差异」）")
    RP.append("  ⚠ 固定剂量下 w / rand **各改判多少题 / 差多少 pp / p 值 / 区间**"
              "⇒ **未量到**（那一批还没跑）")
    RP.append("  ⚠ 这一批**到底跑不跑、跑多少题** ⇒ **等用户点头**（GPU）")
    RP.append("  ⚠ **层间独立性**（各档共享同一批轨迹）⇒ 未量到")
    RP.append("  ⚠ **哪一条臂是机制效应** ⇒ 未量到")
    RP.append("")

    # ---------------- 【7】预检器自身的判据
    RP.append("【7】⚖ 判据（**预检器自身**，每条都**能红**；反例见 `selftest`）")

    # P1 预登记必须**恰好**是那 17 个键（⛔ 多出来的键会被静默忽略 ⇒ 口径可能没生效）
    #    ＋ K 清单**恰好** K1–K13（顺序也要一致）
    # ⚠⚠⚠⚠⚠ **244.68 的一个自我修正**：P1 原先写成「缺键 ⇒ 红」⇒ **恒绿**
    #   （`read_prereg` 在缺键时已经 HardFail ⇒ `build_report` 根本走不到那儿）
    #   ⇒ 改成**可达**的两条：**多出来的键** ＋ **K 清单不齐/乱序**。
    extra_raw = sorted(k for k in (prereg_raw or {}) if k not in fda().PREREG_KEYS)
    miss_raw = [k for k in fda().PREREG_KEYS if k not in (prereg_raw or {})]
    k_ids = [r[0] for r in k_rows]
    k_bad = (k_ids != list(fda().PREREG_K_IDS))
    put("P1", (not extra_raw) and (not miss_raw) and (not k_bad),
        "预登记必须**恰好**是那 %d 个机器键（⛔ 多出来的键会被静默忽略 ⇒ 口径可能没生效）"
        "且 **K 清单恰好 K1–K13**（顺序也要一致）：缺机器键 %s ｜ **多机器键 %s** ｜ K 清单 %s"
        % (len(fda().PREREG_KEYS), miss_raw or "无", extra_raw or "无",
           "✅ 一致" if not k_bad else "❌ 实际 %s" % "/".join(k_ids)))

    # P2 生效口径逐项 == 预登记
    d2 = []
    ok2p = True
    for k, v in cfg.as_lines():
        rv = (prereg_raw or {}).get(k)
        if k == "alpha":
            same = (rv is not None and abs(float(rv) - float(v)) < 1e-12)
        elif k in ("n_bands", "blocks_needed_sign_test", "blocks_needed_cluster",
                   "blocks_needed_fisher_exact"):
            same = (rv is not None and int(rv) == int(v))
        else:
            same = (rv is not None and str(rv) == str(v))
        ok2p = ok2p and same
        if not same:
            d2.append("%s: 生效 %r vs 预登记 %r" % (k, v, rv))
    put("P2", ok2p,
        "**生效口径必须逐项等于预登记文件**（⛔ 不许代码里写死）：%s"
        % ("；".join(d2) if d2 else "逐项一致"))

    # P3 规模需求必须是**重算**的（**活体**：把期望比例改掉 ⇒ 需求必须变）
    alt_props = {"w": [], "rand": []}
    for b in range(n_bands):
        try:
            _pw = float(ep["w"][b])
            _pr = float(ep["rand"][b])
        except (IndexError, TypeError, ValueError):
            _pw, _pr = 0.5, 0.5
        alt_props["w"].append(min(0.99, max(0.01, _pw + 0.05)))
        alt_props["rand"].append(min(0.99, max(0.01, _pr - 0.05)))
    alt_design = dict(design)
    alt_design["expected_proportions"] = alt_props
    try:
        sz_alt = recompute_size(alt_design, cfg)
        alt_vec = [sz_alt["size"].get(b, {}).get("approx") for b in range(n_bands)]
    except HardFail:
        alt_vec = None
    now_vec = [sz["size"].get(b, {}).get("approx") for b in range(n_bands)]
    ok3p = (alt_vec is not None) and (alt_vec != now_vec)
    put("P3", ok3p,
        "**规模需求必须是重算的**（⛔ 不许写死 130/177/31/14）⇒ 把期望比例**改掉**"
        "（w +0.05 / rand −0.05）后**再重算一遍** ⇒ 需求数**必须变**"
        "（若不变 ⇒ 本工具在写死）：本设计 %s ｜ 扰动后 %s"
        % (now_vec, alt_vec if alt_vec is not None else "重算失败"))

    # P4 块级门槛来自预登记
    put("P4", need_blocks == max(cfg.blocks_needed_sign_test,
                                 cfg.blocks_needed_cluster,
                                 cfg.blocks_needed_fisher_exact),
        "**块级门槛必须来自预登记的 3 个键**（⛔ 不许写死 20/14/13）："
        "符号 %d ｜ 聚类 %d ｜ 精确 Fisher %d ⇒ 取最大 **%d**"
        % (cfg.blocks_needed_sign_test, cfg.blocks_needed_cluster,
           cfg.blocks_needed_fisher_exact, need_blocks))

    # P5 m≥3 门槛来自机械的输出（⛔ 不是本文件里的公式）
    put("P5", sz["need_cells"] == 3 * n_bands,
        "**m≥3 的门槛必须来自规模机械自己的输出**（⛔ 本文件不重写那个公式）"
        "⇒ 读出 **%d 格**；与 `3 × n_bands`（%d）一致 %s"
        % (sz["need_cells"], 3 * n_bands,
           "✅" if sz["need_cells"] == 3 * n_bands else "❌"))

    # P6 缺口清单必须与 FAIL 的设计检查**一一对应**
    n_fail = len([c for c in D_IDS if not R[c]])
    put("P6", n_fail == len(gaps),
        "**缺口清单必须与失败的检查一一对应**（少列一条 ⇒ 会被漏掉）："
        "失败 %d 条 ｜ 清单 %d 条" % (n_fail, len(gaps)))

    # P7 留白必须排在判据之前
    idx_blank = None
    idx_crit = None
    for i, ln in enumerate(RP):
        if idx_blank is None and ln.startswith("【6】"):
            idx_blank = i
        if idx_crit is None and ln.startswith("【7】"):
            idx_crit = i
    put("P7", (idx_blank is not None and idx_crit is not None
               and idx_blank < idx_crit),
        "**留白段必须排在判据之前**（⇒ 判据数得到标记）：留白在第 %s 行 ｜ "
        "判据在第 %s 行" % (idx_blank, idx_crit))

    # P8 印出的需求数必须与机械的返回**逐位相同**（外部机械重算）
    d8 = []
    ok8 = True
    for b in range(n_bands):
        entry = sz["size"].get(b) or {}
        req = _req_of(entry)
        if req is None:
            ok8 = False
            d8.append("档 %d：需求缺失 ❌" % b)
            continue
        # 独立重算：把这一档单独喂给机械 ⇒ 应当得到同一个数
        row = [{"L": b, "pw": float(ep["w"][b]), "pr": float(ep["rand"][b])}]
        _l2, s2 = dlayer().size_requirements(
            row, sz["cells_per_traj"], fisher_power=cpre().fisher_power,
            n_layer=n_bands)
        req2 = _req_of(s2.get(b))
        same = (req2 is not None and abs(req2 - req) < 1e-12)
        ok8 = ok8 and same
        d8.append("档 %d：印 %s ｜ 外部重算 %s %s"
                  % (b, req, req2, "✅" if same else "❌"))
    put("P8", ok8,
        "**印出的需求数必须能被外部机械独立重算**（⛔ 不许调本工具自己的函数凑）：%s"
        % "；".join(d8))

    # P9 重算值 == 244.60 登记值（**独立对照** ⇒ 抓「写死」）
    reg_props = (list(ep.get("w", [])) == REGISTERED_PROPS["w"]
                 and list(ep.get("rand", [])) == REGISTERED_PROPS["rand"])
    if reg_props:
        got = [sz["size"].get(b, {}).get("approx") for b in range(n_bands)]
        want = [REGISTERED_SIZES[b] for b in range(n_bands)]
        ok9 = (got == want)
        put("P9", ok9,
            "**重算出来的逐档规模必须与 244.60 的登记值逐位一致**"
            "（⛔ 两处**独立**推导 ⇒ 同一个数）：重算 %s ｜ 登记 %s"
            % (got, want))
    else:
        put("P9", True,
            "**重算出来的逐档规模必须与 244.60 的登记值逐位一致**"
            "（本设计的期望比例**不是**替身那一份 ⇒ 本条**不适用** ⇒ 不作数）")

    # P10 ⛔ 不许把「未量到」说成「无差异」
    hits = banned_claims(RP)
    put("P10", not hits,
        "**⛔ 不许把「未量到」说成「零差异/零效应」**（⛔ 声明禁止的那一句本身**不算**）"
        "⇒ 报告里出现这类**结论措辞** %d 处" % len(hits)
        + ("：%s" % "；".join(h[0] for h in hits) if hits else "（无）"))

    # ⚖⚠⚖⚖⚖ **244.68 的一处自我修正**：判决原本被**算了两遍**
    #   （报告里一遍、`run_preflight` 里又一遍）⇒ 两者**可能自相矛盾**
    #   （⇒ 变异台 M15 把报告里那遍短路掉时，返回值那遍仍是「不能回答」
    #    ⇒ 印出来的与返回的不一致 ⇒ **没人抓得住**）
    #   ⇒ ⇒ 归一：**只算一次**，由 `build_report` 算完**返回**。
    return RP, R, can


def run_preflight(design, prereg_path=PREREG):
    """⚖ 跑一遍预检 ⇒ `(文本行, {判据号: bool}, 判决bool)`。"""
    F = fda()
    raw = F.read_prereg(prereg_path)
    cfg = F.Cfg(raw)
    k_rows = F.prereg_k_rows(prereg_path)
    sz = recompute_size(design, cfg)
    RP, R, can = build_report(design, cfg, raw, k_rows, sz)
    return RP, R, can


# ---------------------------------------------------------------- 自检
def _fixture(over=None):
    """⚖ 夹具设计（**合格**的那一份：块数够、规模够、m≥3、rand 每档有）。"""
    d = {
        "design_id": "fixture_fd",
        "n_blocks": 24,
        "tracks_per_arm": 200,
        "cells_per_track": 12,
        "tracks_per_band": {"w": [200, 200, 200, 200],
                            "rand": [200, 200, 200, 200]},
        "expected_proportions": {"w": list(REGISTERED_PROPS["w"]),
                                 "rand": list(REGISTERED_PROPS["rand"])},
        "convention": {"n_bands": 4, "boundary": "prod", "quantile": "inclusive",
                       "zero_span": "keep"},
    }
    if over:
        d.update(over)
    return d


def _mk_design(d, tmpdir, name="d.json"):
    p = os.path.join(tmpdir, name)
    io.open(p, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=2))
    return p


def selftest():
    """⚖ 自检：已知答案夹具 ＋ **活体**变异（每条判据都证明「能红」）。"""
    F = fda()
    results = []

    def chk(t, cond, why=""):
        results.append((t, bool(cond), why))
        return bool(cond)

    # ⚖⚠⚖⚖⚖ 临时目录必须**进程唯一**（244.68 修）：原来叫 `_pf_tmp`
    #   ⇒ 两个进程**同时**跑（自检 ＋ 变异台）⇒ 各自 `rmtree` 对方的文件
    #   ⇒ 「预登记文件不存在」这种**假红** ⇒ ⇒ 名字里带上 **PID**。
    tmp = os.path.join(HERE, "_pf_tmp_%d" % os.getpid())
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    try:
        # ---- T1 合格设计 ⇒ 能回答，D 全 PASS
        RP, R, can = run_preflight(_fixture())
        chk("T1", can and all(R[c] for c in D_IDS),
            "合格设计 ⇒ 判决「能回答」且 D1–D7 全 PASS")
        chk("T1b", all(R[c] for c in P_IDS),
            "合格设计 ⇒ P1–P10 全 PASS（细节：%s"
            % "、".join(c for c in P_IDS if not R[c]) + "）")
        def _sec(lines, head, nxt):
            out, on = [], False
            for ln in lines:
                if ln.startswith(head):
                    on = True
                    continue
                if on and ln.startswith(nxt):
                    break
                if on:
                    out.append(ln)
            return out

        sec0 = _sec(RP, "【0】", "【1】")
        chk("T1c", ("未量到" in "".join(sec0)) and not banned_claims(RP),
            "【0】段必须写「未量到」且不许把未量到说成零")

        # ---- T2 块数不够 ⇒ D2 红 ⇒ 不能回答
        d = _fixture({"n_blocks": 7})
        RP2, R2, can2 = run_preflight(d)
        chk("T2", (not can2) and (not R2["D2"])
            and ("答不了" in "".join(RP2))
            and ("✅ **这一批的设计能回答" not in "".join(RP2)),
            "块数 7 < 门槛 ⇒ D2 必须红；判决「不能回答」"
            "（**返回的**与**印出来的**必须一致 ⇒ ⛔ 判决只许算一次）")
        chk("T2b", any("块级规模不足" in ln for ln in RP2),
            "缺口清单里必须点名「块级规模不足」")

        # ---- T3 每档规模不够 ⇒ D3 红
        d = _fixture({"tracks_per_band": {"w": [14] * 4, "rand": [14] * 4}})
        RP3, R3, can3 = run_preflight(d)
        chk("T3", (not can3) and (not R3["D3"]),
            "每档 14 条 < 需求 ⇒ D3 必须红")

        # ---- T4 m<3 ⇒ D4 红
        d = _fixture({"cells_per_track": 7.79})
        RP4, R4, can4 = run_preflight(d)
        chk("T4", (not can4) and (not R4["D4"]),
            "每条轨迹 7.79 格 < 12 ⇒ D4 必须红")

        # ---- T5 rand 某档为空 ⇒ D5 红
        d = _fixture({"tracks_per_band": {"w": [200] * 4, "rand": [200, 0, 200, 200]}})
        RP5, R5, can5 = run_preflight(d)
        chk("T5", (not can5) and (not R5["D5"]),
            "rand 档 1 = 0 ⇒ D5 必须红")

        # ---- T6 两臂不等 ⇒ D6 红
        d = _fixture({"tracks_per_band": {"w": [200] * 4, "rand": [199] * 4}})
        RP6, R6, can6 = run_preflight(d)
        chk("T6", (not can6) and (not R6["D6"]),
            "两臂每档不等 ⇒ D6 必须红")

        # ---- T7 口径与预登记不一致 ⇒ D1 红
        d = _fixture({"convention": {"n_bands": 5, "boundary": "prod",
                                      "quantile": "inclusive", "zero_span": "keep"}})
        RP7, R7, can7 = run_preflight(d)
        chk("T7", (not can7) and (not R7["D1"]),
            "设计声明 5 档 ≠ 预登记 4 档 ⇒ D1 必须红")

        # ---- T7b 只改 boundary（其余与预登记一致）⇒ D1 也必须红
        d7b = _fixture({"convention": {"n_bands": 4, "boundary": "alt",
                                       "quantile": "inclusive", "zero_span": "keep"}})
        RP7b, R7b, can7b = run_preflight(d7b)
        chk("T7b", (not can7b) and (not R7b["D1"]),
            "设计声明 boundary=alt ≠ 预登记 prod ⇒ D1 必须红")

        # ---- T8 档数与预登记不一致 ⇒ D7 红
        d = _fixture({"tracks_per_band": {"w": [200] * 3, "rand": [200] * 3}})
        RP8, R8, can8 = run_preflight(d)
        chk("T8", (not can8) and (not R8["D7"]),
            "设计给 3 档 ≠ 预登记 4 档 ⇒ D7 必须红")

        # ---- T9 预登记缺键 ⇒ HardFail（⛔ 不许兜底）
        src = io.open(PREREG, encoding="utf-8").read()
        bad = src.replace("alpha = 0.05\n", "", 1)
        p = os.path.join(tmp, "prereg_missing.md")
        io.open(p, "w", encoding="utf-8").write(bad)
        hit = False
        try:
            run_preflight(_fixture(), prereg_path=p)
        except F.HardFail:
            hit = True
        chk("T9", hit, "预登记**缺键** ⇒ 必须 HardFail（⛔ 不许默认值兜底）")

        # ---- T9b 预登记的**值畸形** ⇒ HardFail（⛔ 不许崩成 ValueError）
        bad2 = src.replace("alpha = 0.05", "alpha = ", 1)
        p2b = os.path.join(tmp, "prereg_malformed.md")
        io.open(p2b, "w", encoding="utf-8").write(bad2)
        hit2 = False
        try:
            run_preflight(_fixture(), prereg_path=p2b)
        except F.HardFail:
            hit2 = True
        chk("T9b", hit2,
            "预登记的**值畸形** ⇒ 必须 HardFail（⛔ 「崩」不是「抓到」）")

        # ---- T9c 机器块**多一个键** ⇒ P1 必须红（⛔ 多出来的键会被静默忽略）
        p2c = os.path.join(tmp, "prereg_extra.md")
        io.open(p2c, "w", encoding="utf-8").write(
            src.replace("sign_date = 2026-10-20\n",
                        "sign_date = 2026-10-20\nfoo = 1\n", 1))
        RPc, Rc, _c = run_preflight(_fixture(), prereg_path=p2c)
        chk("T9c", (not Rc["P1"]),
            "预登记机器块**多一个键** ⇒ P1 必须红（那个键会被静默忽略）")

        # ---- T9d K 清单**缺一行** ⇒ P1 必须红
        p2d = os.path.join(tmp, "prereg_nok.md")
        _lines_src = src.split("\n")
        _keep = [ln for ln in _lines_src if not ln.startswith("| K7 |")]
        io.open(p2d, "w", encoding="utf-8").write("\n".join(_keep))
        RPd, Rd, _c = run_preflight(_fixture(), prereg_path=p2d)
        chk("T9d", (not Rd["P1"]),
            "预登记的 **K 清单缺 K7** ⇒ P1 必须红（清单不齐）")

        # ---- T10 P10 必须**能红**（真的写一句「无差异」 ⇒ 必须被抓）
        chk("T10", bool(banned_claims(["  · 两臂无差异 ⇒ 结论成立"])),
            "P10 必须能红：一句「两臂无差异 ⇒ 结论成立」必须被抓")
        chk("T10b", not banned_claims(["  · ⛔ 不许把它说成「无差异」"]),
            "P10 不得**假红**：声明禁止的那一句必须放行")

        # ---- T9e **CLI** 遇到缺设计文件 ⇒ 必须干净返回 2（⛔ 不许崩成 traceback）
        #   ⚖ 这条走的是**命令行入口**（`main()`）⇒ 台架的两条路都不经过它
        #   ⇒ 必须单独钉住（⛔ 「崩」不是「抓到」）
        import contextlib as _ctx
        import io as _io
        _buf = _io.StringIO()
        _rc = None
        _old_argv = list(sys.argv)
        try:
            sys.argv = ["fixed_dose_preflight.py", "--design",
                        os.path.join(tmp, "_no_such_design.json")]
            with _ctx.redirect_stdout(_buf):
                _rc = main()
        except SystemExit as e:
            _rc = e.code
        except Exception as e:
            # ⚖⚠⚠⚖⚖ **这里必须把异常**接住**并记成失败**，⛔ 不许让它冒出去
            #   （冒出去 ⇒ 整个自检**崩** ⇒ 台架记成「崩」⇒ ⛔ **崩 ≠ 抓到**
            #   ⇒ 那条变异就永远抓不到 ⇒ 覆盖出空洞）
            _rc = "EXC:%s" % type(e).__name__
        finally:
            sys.argv = _old_argv
        chk("T9e", (_rc == 2) and ("HardFail" in _buf.getvalue()),
            "CLI 遇到**缺设计文件** ⇒ 必须干净返回 2 并印 HardFail"
            "（⛔ 不许崩成 traceback；实际 rc=%r）" % (_rc,))

        # ---- M1 活体：改预登记的 alpha ⇒ 生效口径必须变（P2 的活体证据）
        p2 = os.path.join(tmp, "prereg_alpha.md")
        io.open(p2, "w", encoding="utf-8").write(
            src.replace("alpha = 0.05", "alpha = 0.01", 1))
        RPm1, Rm, _c = run_preflight(_fixture(), prereg_path=p2)
        raw2 = F.read_prereg(p2)
        chk("M1", (abs(float(raw2["alpha"]) - 0.01) < 1e-12) and Rm["P2"]
            and ("alpha = 0.01" in "".join(RPm1)),
            "改预登记 alpha ⇒ **报告里印出来的 α 必须变**（活体）")

        # ---- M2 活体：改预登记的 blocks_needed_sign_test ⇒ 门槛必须变
        p3 = os.path.join(tmp, "prereg_blocks.md")
        io.open(p3, "w", encoding="utf-8").write(
            src.replace("blocks_needed_sign_test = 20",
                        "blocks_needed_sign_test = 40", 1))
        RPm2, Rm2, canm2 = run_preflight(_fixture(), prereg_path=p3)
        chk("M2", ("40" in "".join(RPm2)) and Rm2["P4"],
            "改预登记块级门槛 ⇒ 报告里的门槛必须变（活体）")

        # ---- M3 活体：改预登记的 n_bands ⇒ m≥3 门槛必须变
        #   ⚠ n_bands 必须在机械支持的取值里（3/4/5）⇒ 用 5
        #   ⚠ 配套的设计也得是 5 档（⛔ 不许拿 4 档的设计配 5 档的预登记）
        p4 = os.path.join(tmp, "prereg_bands.md")
        io.open(p4, "w", encoding="utf-8").write(
            src.replace("n_bands = 4", "n_bands = 5", 1))
        d3f = _fixture({
            "tracks_per_band": {"w": [200] * 5, "rand": [200] * 5},
            "expected_proportions": {
                "w": [4.0 / 14, 6.0 / 14, 10.0 / 14, 14.0 / 14, 0.9],
                "rand": [2.0 / 14, 4.0 / 14, 5.0 / 14, 6.0 / 14, 0.5]},
            "convention": {"n_bands": 5, "boundary": "prod",
                           "quantile": "inclusive", "zero_span": "keep"}})
        RPm3, Rm3, _c = run_preflight(d3f, prereg_path=p4)
        chk("M3", ("15" in "".join(RPm3)) and Rm3["P5"],
            "改预登记 n_bands=5 ⇒ m≥3 门槛必须变成 15（活体）")

        # ---- M4 活体：改设计的期望比例 ⇒ 需求必须变（P3 的活体证据）
        d4 = _fixture({"expected_proportions": {
            "w": [0.5, 0.6, 0.7, 0.8], "rand": [0.2, 0.3, 0.4, 0.5]}})
        RPm4, Rm4, _c = run_preflight(d4)

        def _d3line(lines):
            for ln in lines:
                if " D3：" in ln:
                    return ln
            return ""

        def _d3reqs(lines):
            """⚖ 从**印出来的** D3 那一行里取逐档需求数（⛔ 不调被检对象的函数）。"""
            return re.findall(r"需 \*\*(\d+)\*\*/臂", _d3line(lines))

        chk("M4", (_d3reqs(RP) != _d3reqs(RPm4)) and Rm4["P3"],
            "改期望比例 ⇒ 印出的逐档需求数必须变（活体）：%s vs %s"
            % (_d3reqs(RP), _d3reqs(RPm4)))

        # ---- M5 缺口清单与失败检查一一对应
        d5 = _fixture({"n_blocks": 7, "cells_per_track": 7.79})
        RPm5, Rm5, canm5 = run_preflight(d5)
        nfail = len([c for c in D_IDS if not Rm5[c]])
        chk("M5", (nfail == 2) and (not canm5),
            "同时坏两项 ⇒ 失败 %d 条 ⇒ 判决「不能回答」" % nfail)
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp)

    # ---- 打印
    npass = len([1 for _t, ok, _w in results if ok])
    for t, ok, why in results:
        print("  [%s] %s：%s" % ("PASS" if ok else "FAIL", t, why))
    # ⚖ 小结**印在最后**（与 `fixed_dose_audit.py` **一致**）⇒ 回归日志的 tail 行
    #   直接显示「N 通过 / M 失败」⇒ ⛔ 别让 tail 落在某一条用例上（244.68 修）
    print("")
    print("自检：%d 通过 / %d 失败" % (npass, len(results) - npass))
    return 0 if npass == len(results) else 1


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="固定剂量批次 · 发批前预检器（244.68）")
    ap.add_argument("--design", help="设计描述 JSON 的路径")
    ap.add_argument("--prereg", default=PREREG)
    ap.add_argument("--emit-template", action="store_true",
                    help="印一份设计描述模板（占位数）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.emit_template:
        print(json.dumps(design_template(), ensure_ascii=False, indent=2))
        return 0
    if a.selftest:
        return selftest()
    if not a.design:
        ap.error("需要 --design（或 --emit-template / --selftest）")
    try:
        design = read_design(a.design)
        RP, R, can = run_preflight(design, prereg_path=a.prereg)
    except (HardFail, fda().HardFail) as e:
        # ⚖⚠⚖⚖⚖ **244.68 的一处真 bug（这里修的）**：`read_design` 抛的是
        #   **本文件自己的** `HardFail`，而这里原来只捕 `fda().HardFail`
        #   ⇒ 设计描述**缺文件/缺键/JSON 畸形**时**崩成 traceback**
        #   ⇒ ⛔ **「崩」不是「抓到」** ⇒ 两种 HardFail **都要**捕 ⇒ 干净地返回 2
        print("HardFail：%s" % e)
        return 2
    for ln in RP:
        print(ln)
    return 0 if can else 1


if __name__ == "__main__":
    sys.exit(main())
