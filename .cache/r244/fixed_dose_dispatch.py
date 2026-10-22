#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixed_dose_dispatch.py —— **发批清单模板**（格清单加 pos_frac 列）＋ **清单校验器**（零 GPU、零写操作）。

⚖⚖⚖⚖⚖ **244.71 的第二半**：244.71 的第一半（`fixed_dose_cost.py`）把两条路线各要花多少**量**出来了
   ⇒ ⇒ 两条路线**共同的阻断**是 **C6：格清单没有 pos_frac 列** ⇒ ⇒ 本工具把 C6 **落地**：
   ① `--emit-template` ⇒ **印出**发批清单该长什么样（**4 列**：tid / scope / n_sites / pos_frac）
      ＋ **要填什么**的规格（哪些轨迹 × 哪些 pos_frac × 哪个剂量分数 × 期望多少格）
   ② `--check` ⇒ 校验**填好的**清单（⛔ 不发批、⛔ 不写任何数据文件）

⚖⚠⚖⚖⚖⚖ **本工具⛔ 不做**的四件事（都不许偷做）：
   ① **不改探针**、**不改格清单格式**（那是**生成侧**改动 ⇒ 要用户点头）⇒ 本工具**只印格式**
   ② **不发批**（⛔ GPU ⇒ 要用户点头）⇒ 本工具⛔ **不启动任何探针**
   ③ **不替用户决定剂量** ⇒ 剂量是**输入**（`--dose-frac` / `--dose-tol`）⇒ ⇒ 本工具只**核**它
   ④ **不改账本里的任何数** ⇒ 本工具⛔ **不产生判决**（它判的是「清单对不对」，不是「效果好不好」）

⚖⚖⚖ **复用既有机械**（⛔ 不另写第二套真相）：
   · 路线规格 ＋ 成本（C1–C8）⇒ **调用** `fixed_dose_cost.evaluate`
   · m≥3 的门槛 ⇒ **调用** `fixed_dose_feasible.need_cells_from_mechanic`（⛔ 不写「3 × 档数」）
   · 生成池、`n_eff`、`pos_frac` 已测性 ⇒ **调用** `fixed_dose_feasible.read_pool`
   · 既有格清单（**阶梯**的真身）⇒ 从**成本基线**里记的路径读（带 md5 ⇒ 可核）

⚖⚠⚖⚖⚖⚖ **三条必须说清的口径**（**本工具自己也不许含糊**）：
   ① `pos_frac` ⛔ **不是位置**（244.26 已证：它是**有效前缀比例** `t = max(1, int(n_gen·pos_frac))`）
      ⇒ ⇒ 固定剂量下**唯一**能变的轴就是它 ⇒ ⇒ **格清单必须多这一列** ⇒ ⇒ 这就是 C6。
      ⇒ ⇒ ⚠⚠⚖⚖⚖ **244.72 更正**：这一段里「pos_frac **不承载剂量**」那句话**不成立** ⇒ ⇒
        `pos_frac` 改的是**可注入位置数** `inj = P + max(1,int(n_gen·pos_frac)) − 1`
        ⇒ ⇒ 而**生产剂量分数 = n_sites / inj** ⇒ ⇒ **同样 n_sites、不同 pos_frac ⇒ 剂量不同**
        ⇒ ⇒ ⇒ 「固定剂量」的真含义是**密度相等** ⇒ ⇒ 判据是 **G13** ⇒ ⇒
        ⇒ ⇒ **n_sites 必须随 pos_frac 等比变**（⛔ 不是「三条轨迹的 n_sites 相同」）。
   ② ⚠⚠⚖ **剂量必须用「分数」声明，不能用「档位序号」** —— **实测**（244.71 新查）：
      既有 `k` 阶梯是**每条轨迹自己的 n_eff 分位阶梯**（实测 14 条轨迹：档位落在
      0.0008 / 0.0036 / 0.0155 / 0.0623 / 0.25 / 0.50 / 0.75 / 0.875 附近），
      而**阶梯长度不同**（7 / 8 / 9 档）⇒ ⇒ **同一个档位序号在不同轨迹上是不同的分数**
      ⇒ ⇒ 且 ⛔ **格清单的 k 行不是按档位排序的**（实测 `p03__think`：3,14,59,236,946,1893,**1**,2839,3312
      ⇒ 那个 **1** 夹在 1893 与 2839 之间）⇒ ⇒ **序号根本不是可靠的剂量口径**
      ⇒ ⇒ ⇒ 唯一稳的口径是**分数** `n_sites / n_eff` ⇒ ⇒ 本工具按分数核。
   ③ ⚠⚠ **只有 14 条轨迹有阶梯**（`warm_cells.txt` 覆盖 14 条 / 137 行）⇒ ⇒ 其余轨迹的
      阶梯**尚未生成** ⇒ ⇒ 它们的剂量**未量到** ⇒ ⇒ 进前提清单，⛔ **不许**当成「核过了」。

⚖ 用法：
   `fixed_dose_dispatch.py --emit-template --route <json> --dose-scope k --dose-frac <f> --dose-tol <t>`
       [--spec-out <json>]
   `fixed_dose_dispatch.py --check <filled.tsv> --spec <json>`
   `fixed_dose_dispatch.py --selftest`
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
POOL_DEFAULT = os.path.join(HERE, "fixed_dose_pool_snapshot.json")
BASE_DEFAULT = os.path.join(HERE, "fixed_dose_cost_baseline.json")

# ⚖ 判据号（G4 拆成 a–d、G9 拆成 a/b ⇒ 因为它们问的是**不同的几件事**）
G_IDS = ("G1", "G2", "G3", "G4a", "G4b", "G4c", "G4d", "G5", "G6", "G7",
         "G8", "G9a", "G9b", "G10", "G11", "G12", "G13")
# ⚖⚠⚖ **G12 是「前提类」**（pos_frac 未测过）⇒ ⛔ **不进阻断集**
#   ⇒ 否则「未量到」会被当成「失败」⇒ ⇒ 与 F5 / C7 同一条纪律
# ⚖⚠⚖⚖ **G3 从阻断集里移出（244.72）** ⇒ 因为它问的是「**注入参数**（scope/n_sites）
#   是否一致」⇒ ⛔ **那不等于「剂量固定」** ⇒ ⇒ 「剂量固定」的判据是 **G13**
#   （同一条轨迹的**复制格密度**相等 ⇒ **生产剂量口径** ⇒ ⛔ 复用
#   `fixed_dose_density_audit.density_of` ⇒ ⇒ 与**分析管线**逐位同源）
G_BLOCKING = ("G1", "G2", "G4a", "G4b", "G4c", "G4d", "G5", "G6",
              "G7", "G8", "G9a", "G9b", "G10", "G11", "G13")

# ⚖ 新格清单的**列**（⛔ 现状是 3 列 ⇒ 少的那一列就是 pos_frac ⇒ 这就是 C6）
COLUMNS = ("tid", "scope", "n_sites", "pos_frac")

_MODS = {}


def _load(name):
    """⚖ 延迟 import（同目录的既有机械）⇒ ⛔ 不在 import 期就炸。"""
    if name not in _MODS:
        import importlib
        _MODS[name] = importlib.import_module(name)
    return _MODS[name]


def fdc():
    return _load("fixed_dose_cost")


def dlayer():
    return _load("dose_layer_audit")


def fdf():
    return _load("fixed_dose_feasible")


class HardFail(Exception):
    """⚖ 本工具自己的 HardFail（⚠ 与别的工具的同名类**不是同一个类型**）。"""


# ---------------------------------------------------------------- 读输入
def _read_json(path, what):
    if not os.path.isfile(path):
        raise HardFail("%s不存在：%s" % (what, path))
    try:
        return json.loads(io.open(path, encoding="utf-8").read())
    except ValueError as e:
        raise HardFail("%s不是合法 JSON：%s（%s）" % (what, path, e))


def read_route(path):
    """⚖ 读路线规格（⛔ 复用 `fixed_dose_cost` 的键集与策略取值 ⇒ ⛔ 不另立一套）。"""
    r = _read_json(path, "路线规格")
    C = fdc()
    for k in C.ROUTE_KEYS:
        if k not in r:
            raise HardFail("路线规格缺字段 %s（⛔ 不许用默认值兜底）" % k)
    if r["strategy"] not in ("expand_pool", "measure_first"):
        raise HardFail("路线规格 strategy 认不出来：%r" % (r["strategy"],))
    if not isinstance(r["pos_fracs"], list) or not r["pos_fracs"]:
        raise HardFail("路线规格 pos_fracs 必须是非空列表")
    return r


def read_route_obj(r):
    """⚖ 校验内嵌的路线对象（与 `read_route` 同一套规则 ⇒ ⛔ 两处不会漂）。"""
    C = fdc()
    for k in C.ROUTE_KEYS:
        if k not in r:
            raise HardFail("内嵌路线缺字段 %s" % k)
    if r["strategy"] not in ("expand_pool", "measure_first"):
        raise HardFail("内嵌路线 strategy 认不出来：%r" % (r["strategy"],))
    return r


def _valid_dose(d):
    """⚖ 剂量的两个键：**分数** 与 **容差**（⛔ 两者都必须给 ⇒ 不许默认值兜底）。"""
    for k in ("scope", "frac", "tol"):
        if k not in d:
            raise HardFail("发批规格 dose 缺键 %s（⛔ 不许默认值兜底）" % k)
    for k in ("frac", "tol"):
        v = d[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise HardFail("发批规格 dose.%s 必须是数字：%r" % (k, v))
    if not (0.0 < float(d["frac"]) < 1.0):
        raise HardFail("发批规格 dose.frac 必须在 (0,1) 之间（它是 n_sites/n_eff）：%r" % d["frac"])
    if not (0.0 < float(d["tol"]) < 1.0):
        raise HardFail("发批规格 dose.tol 必须在 (0,1) 之间：%r" % d["tol"])
    return d


def read_spec(path):
    """⚖ 读**发批规格**（= 路线 ＋ 剂量口径）⇒ 缺键 ⇒ HardFail（⛔ 不许默认值兜底）。"""
    s = _read_json(path, "发批规格")
    for k in ("spec_id", "route", "dose", "arms"):
        if k not in s:
            raise HardFail("发批规格缺键 %s（⛔ 不许用默认值兜底）" % k)
    _valid_dose(s["dose"])
    if not isinstance(s["arms"], list) or not s["arms"]:
        raise HardFail("发批规格 arms 必须是非空列表")
    read_route_obj(s["route"])
    return s


def read_cells(path, expect_header=True):
    """⚖ 读一份格清单（TSV）⇒ 返回 `(表头, 行列表)`。
    ⚖⚠⚖ **行必须逐字存**（⛔ 不预先 strip 列里的空白 ⇒ 免得把「多了一列空格」吞掉）。"""
    if not os.path.isfile(path):
        raise HardFail("格清单不存在：%s" % path)
    raw = io.open(path, encoding="utf-8").read()
    if "\ufffd" in raw:
        raise HardFail("格清单里有坏字：%s" % path)
    lines = [ln for ln in raw.split("\n") if ln.strip() != ""]
    if not lines:
        raise HardFail("格清单是空的：%s" % path)
    if expect_header:
        head = lines[0].split("\t")
        body = lines[1:]
    else:
        head = None
        body = lines
    rows = []
    for i, ln in enumerate(body, 2):
        rows.append({"lineno": i, "raw": ln, "cols": ln.split("\t")})
    return head, rows


def ladder_map(base):
    """⚖ 既有格清单 ⇒ 每条轨迹的 **k 阶梯**（真身，⛔ 不重算阶梯）。
    ⚖⚠⚖⚖⚖ **阶梯的「档位序号」不可靠**（实测 `p03__think` 的 k 行不是排序的）⇒ ⇒
    ⇒ 本函数只给「**有哪些 n_sites**」⇒ ⇒ **档位的可比口径是分数**（见 `frac_ladder`）。"""
    p = base["cell_list"]["path"]
    head, rows = read_cells(p, expect_header=False)
    lad = {}
    for r in rows:
        if len(r["cols"]) < 3:
            continue
        tid, kind, val = r["cols"][0], r["cols"][1], r["cols"][2]
        if kind != "k":
            continue
        lad.setdefault(tid, []).append(val)
    return lad


def neff_map(pool):
    """⚖ 每条轨迹的 `n_eff`（来自**生成池快照** ⇒ ⛔ 不重算）。"""
    return dict((t["tid"], t["n_eff"]) for t in pool["tids"])


def frac_ladder(lad, neff, tid):
    """⚖ 某条轨迹的阶梯 ⇒ `[(n_sites, 分数)]`（分数 = n_sites / n_eff）。
    ⚖⚠⚖ **n_eff 未知 ⇒ 返回 None** ⇒ ⇒ 那条轨迹的剂量**未量到**（⛔ 不许当「核过了」）。"""
    n = neff.get(tid)
    if not n:
        return None
    out = []
    for v in lad.get(tid, []):
        try:
            out.append((v, float(v) / float(n)))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------- 模板
def build_spec(route, dose_scope, dose_frac, dose_tol, arms=None):
    """⚖ 造**发批规格**（路线 ＋ 剂量口径 ＋ 臂）⇒ 这就是「要填什么」的那一份。"""
    arms = list(arms or route["arms"])
    return {
        "spec_id": "发批规格（%s）" % route["route_id"],
        "route": route,
        "dose": {"scope": dose_scope, "frac": float(dose_frac), "tol": float(dose_tol),
                 "meaning": "**每个 (轨迹, pos_frac) 取「生产密度 n_sites / (P + max(1,int(n_gen·pos_frac))−1) "
                 "落在 frac ± tol 内」的那一档**⇒ ⚠⚠⚖ **244.72 更正**：244.71 这一版写的是 "
                 "`n_sites/n_eff` ⇒ ⛔ **那不是生产剂量口径** ⇒ ⇒ 详见账本 244.72 段"
                            "⇒ ⛔ **不是**「档位序号」⇒ ⇒ **不是**同一个绝对 n_sites"},
        "arms": arms,
        "columns": list(COLUMNS),
        "premises": list(route.get("premises", [])),
    }


def render_template(spec, route, base, pool):
    """⚖ 印**模板**：表头 ＋ **形状示例行** ＋ 「要填什么」的规格。
    ⚖⚠⚖ **示例行是示例**（⛔ 不是要发出去的清单 ⇒ 印的时候必须写清楚）。"""
    out = []
    out.append("=" * 78)
    out.append("【发批清单模板】⚖⚖⚖ 固定剂量那一批的格清单**该长什么样**（244.71，零 GPU）")
    out.append("=" * 78)
    out.append("  ⚖ 规格：`%s`" % spec["spec_id"])
    out.append("  ⚖ 路线：`%s`（策略 `%s`）" % (route["route_id"], route["strategy"]))
    out.append("  ⚖ 剂量口径：scope = `%s` ｜ **生产密度** **%.4f ± %.4f**"
               "（= n_sites / (P + max(1,int(n_gen·pos_frac))−1)）"
               % (spec["dose"]["scope"], float(spec["dose"]["frac"]), float(spec["dose"]["tol"])))
    out.append("  ⚖ 臂：%s ｜ 每条轨迹 %d 格 ｜ 块数 %d"
               % (",".join(spec["arms"]), int(route["cells_per_track"]),
                  int(route["n_blocks"])))
    out.append("")
    out.append("  ⚖⚖⚖⚖⚖ **新格式：4 列**（⛔ 现状是 **3 列** ⇒ 少的就是 `pos_frac` ⇒ 这就是 **C6**）：")
    out.append("")
    out.append("    " + "\t".join(COLUMNS))   # ⚖⚠⚖ 这行是「模板表头」⇒ 台架 M18 盯着它
    out.append("")
    out.append("  ⚖ **形状示例行**（⛔ **示例** ⇒ ⛔ **不是**要发出去的清单）：")
    lad = ladder_map(base)
    neff = neff_map(pool)
    ex_tid, ex_val = None, "（阶梯待生成）"
    for t in sorted(lad):
        fl = frac_ladder(lad, neff, t)
        if not fl:
            continue
        hits = [(v, f) for (v, f) in fl
                if abs(f - float(spec["dose"]["frac"])) <= float(spec["dose"]["tol"])]
        if len(hits) == 1:
            ex_tid, ex_val = t, hits[0][0]
            break
    for pf in route["pos_fracs"]:
        out.append("    " + "\t".join([ex_tid or "<tid>", spec["dose"]["scope"],
                                       str(ex_val), str(pf)]))
    out.append("")
    out.append("  ⚖ **要填什么**（生成侧填完 ⇒ 用 `--check` 核 ⇒ 核过了才谈发不发）：")
    out.append("    · 轨迹：**%d** 条（%d 块 × 2 个臂型）"
               % (int(route["n_blocks"]) * 2, int(route["n_blocks"])))
    out.append("    · 每条轨迹 **%d** 格 ⇒ pos_frac 取 **%s**"
               % (int(route["cells_per_track"]), ",".join(str(x) for x in route["pos_fracs"])))
    out.append("    · 每条轨迹的 **scope 相同**；⚠⚠⚖ **剂量（生产密度）相同 ⇒ n_sites 随 inj 变**")
    out.append("      ⇒ ⇒ ⛔ **244.71 那句「n_sites 全部相同 ＝ 剂量被钉死」是错的** ⇒ ⇒ 见账本 244.72 段")
    out.append("      ⇒ n_sites = **每个 (轨迹, pos_frac) 各自**、"
               "**生产密度落在 %.4f ± %.4f** 的那一档"
               % (float(spec["dose"]["frac"]), float(spec["dose"]["tol"])))
    out.append("      ⇒ ⇒ ⚠⚠⚖⚖⚖ **244.72 实测：现有阶梯供不出**（它是**在 pos_frac=0.5 下生成**的）"
               "⇒ ⇒ ⇒ **要在 0.25 / 0.75 下命中同一密度 ⇒ 需要另一个 n_sites**")
    out.append("      ⇒ ⇒ ⇒ ⇒ ⇒ 那一部分**不在现有阶梯上** ⇒ ⇒ ⇒ **要新阶梯**（⇒ 生成侧 ⇒ ⛔ 要点头）")
    out.append("      ⇒ ⇒ ⇒ ⇒ ⇒ 量法：`.cache/r244/fixed_dose_density_audit.py --supply --route <json>`")
    out.append("    · ⇒ **每臂**的格数 = %d × %d × %d = **%d**"
               % (int(route["n_blocks"]), 2, int(route["cells_per_track"]),
                  int(route["n_blocks"]) * 2 * int(route["cells_per_track"])))
    out.append("    · ⇒ **两臂**（%s）合计 **%d** 格"
               % (",".join(spec["arms"]),
                  int(route["n_blocks"]) * 2 * int(route["cells_per_track"]) * len(spec["arms"])))
    out.append("")
    out.append("  ⚖⚠⚖⚖⚖⚖ **四条必须一起说清的前提**（⛔ 不是免责声明，是**口径**）：")
    out.append("    ① `pos_frac` ⛔ **不是位置** ⇒ 它是**有效前缀比例** `t = max(1, int(n_gen·pos_frac))`")
    out.append("       ⇒ ⇒ 固定剂量下**唯一**能变的轴就是它 ⇒ ⇒ **格清单必须多这一列**")
    out.append("       ⇒ ⇒ ⚠⚠⚖⚖⚖ **244.72 更正**：「pos_frac **不承载剂量**」**不成立** ⇒ ⇒ "
               "它改**可注入位置数** ⇒ ⇒ **生产剂量 = n_sites / inj** ⇒ ⇒ ⇒ "
               "**密度相等**才叫固定剂量 ⇒ ⇒ **n_sites 必须随 pos_frac 等比变**")
    out.append("    ② ⚠⚠⚖ **剂量用「分数」不用「档位序号」** —— 实测：阶梯是**每条轨迹自己的 n_eff 分位**")
    out.append("       ⇒ 阶梯长度不同（7 / 8 / 9 档）⇒ **同一序号在不同轨迹上是不同的分数**")
    out.append("       ⇒ ⇒ 且 ⛔ **格清单的 k 行不是排序的**（实测 `p03__think` 的 **1** 夹在 1893 与 2839 之间）")
    out.append("       ⇒ ⇒ ⇒ 唯一稳的口径是**分数**（⚠⚠⚖ **244.72：那个分数要按**生产密度**算，"
               "⛔ **不是** `n_sites/n_eff`** ⇒ ⇒ 因为分母依赖 pos_frac）")
    out.append("    ③ ⚠⚠ **只有 14 条轨迹有阶梯**（`warm_cells.txt` 覆盖 14 条 / 137 行）")
    out.append("       ⇒ ⇒ 其余轨迹的阶梯**尚未生成** ⇒ ⇒ 它们的剂量**未量到** ⇒ 进前提清单")
    out.append("    ④ ⛔ **本工具不发批**：它只**印格式** ＋ **核清单** ⇒ ⇒ 改格清单格式 / 改探针 / 发批")
    out.append("       ⇒ ⇒ **都要用户点头**")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- 校验
def check_cells(spec, cells_path, pool, base):
    """⚖ 核一份**填好的**格清单 ⇒ 返回 `(判据行, 判决字典)`。
    ⚖⚖⚖ **判决只算一次**（印出来的与返回的必须一致 ⇒ 报告那一层算完返回）。"""
    R = {}
    rows = []
    gaps = []
    premises = []
    notes = []          # ⚖⚠⚖ **非阻断**但**必须印出来**的结论（244.72 加）
                        #   ⇒ 否则「判据红了但理由不印」⇒ 印出来的与返回的不一致

    def put(gid, ok, detail):
        R[gid] = bool(ok)
        rows.append("  [%s] %-5s %s" % ("PASS" if ok else "FAIL", gid, detail))

    def put_premise(gid, ok, detail):
        """⚖⚠⚖⚖⚖ **前提类**判据 ⇒ ⛔ **不许**印成 `FAIL`
        ⇒ ⇒ 否则「**未量到**」会被读成「**失败**」⇒ ⇒ 而同一屏下面就写着「可以发」
        ⇒ ⇒ ⇒ 那正是 244.62 定的纪律：**未量到 ≠ 没差异 ≠ 失败**。"""
        R[gid] = bool(ok)
        rows.append("  [前提] %-5s %s" % (gid, detail))

    def put_diag(detail):
        """⚖ **诊断行**（⛔ **不是判据** ⇒ ⛔ 不参与判决）⇒ ⇒ 只供人看。
        ⚖⚠⚖ ⚠ **印出来了才算数**（244.71 的教训：注释里说「印出」而代码没印 ⇒ 那是**说谎**）。"""
        rows.append("  [诊断] %-5s %s" % ("", detail))

    route = spec["route"]
    scope_want = str(spec["dose"]["scope"])
    target = float(spec["dose"]["frac"])
    tol = float(spec["dose"]["tol"])
    cpt = int(route["cells_per_track"])
    n_blocks = int(route["n_blocks"])
    pf_route = [float(x) for x in route["pos_fracs"]]

    head, crows = read_cells(cells_path)

    # ---------- G1 有没有 pos_frac 列
    ok1 = bool(head) and len(head) >= 4 and head[3].strip() == "pos_frac"
    put("G1", ok1,
        "**格清单有 pos_frac 列吗**：表头 %s ⇒ %s"
        % (head if head else "（无表头）",
           "✅ 有（第 4 列）" if ok1 else
           "❌ ⇒ **C6 的落地形态**：缺 pos_frac 列 ⇒ 固定剂量下多格**造不出来**"
           "（⇒ 要改生成侧的格清单格式 ⇒ ⛔ 要用户点头）"))
    if not ok1:
        gaps.append("格清单缺 pos_frac 列 ⇒ 固定剂量下多格造不出来（⇒ 生成侧改动 ⇒ 要点头）")

    # ---------- G2 每行列数
    bad_cols = [r["lineno"] for r in crows if len(r["cols"]) != 4]
    ok2 = (not bad_cols) and bool(crows)
    put("G2", ok2,
        "**每行列数**：%d 行里列数 ≠ 4 的有 **%d** 行 %s"
        % (len(crows), len(bad_cols), "✅" if ok2 else "❌（行号 %s）" % bad_cols[:5]))
    if not ok2:
        gaps.append("格清单有 %d 行列数不对（应 4 列）" % len(bad_cols))

    # ---------- 解析（列数不对的行 ⛔ 不参与后面的判据，避免连锁假红）
    good = [r for r in crows if len(r["cols"]) == 4]
    by_tid = {}
    for r in good:
        tid, sc, ns, pf = r["cols"][0], r["cols"][1], r["cols"][2], r["cols"][3]
        by_tid.setdefault(tid, []).append({"scope": sc, "n_sites": ns, "pos_frac": pf,
                                           "lineno": r["lineno"]})

    # ---------- G3 同一条轨迹内**注入参数**必须一致
    # ⚠⚠⚖⚖⚖ **244.72 更正**：这一条问的是「**注入参数**（scope / n_sites）一致」，
    #   ⛔ **它不等于「剂量固定」** ⇒ ⇒ 244.71 把这两件事当成一件 ⇒ ⇒ 错。
    #   ⇒ ⇒ 「剂量固定」的真判据是 **G13**（**生产密度**口径下的复制格密度相等）
    #   ⇒ ⇒ G3 因此**降级为非阻断**（它的结论仍要印出来 ⇒ 走 `notes` 通道）
    mixed = []
    for tid, cells in sorted(by_tid.items()):
        doses = set((c["scope"], c["n_sites"]) for c in cells)
        if len(doses) != 1:
            mixed.append(tid)
    ok3 = (not mixed) and bool(by_tid)
    put("G3", ok3,
        "**同一条轨迹内注入参数（scope / n_sites）一致**：%d 条轨迹里**不一致**的 **%d** 条 %s"
        "（⚠⚠⚖ **这不等于「剂量固定」** ⇒ 「剂量固定」看 **G13**）"
        % (len(by_tid), len(mixed), "✅" if ok3 else "❌（%s）" % mixed[:3]))
    if not ok3:
        notes.append("%d 条轨迹内部的**注入参数**不一致 ⇒ ⇒ 注意：「剂量固定」要求的是"
                     "**密度相等**（⇒ 看 **G13**），⛔ 不是「n_sites 相同」" % len(mixed))

    # ---------- G13 同一条轨迹的**复制格密度相等**（**这才是「固定剂量」**）
    # ⚖⚖⚖ 密度走**生产口径**（`n_sites / (P + max(1,int(n_gen·pos_frac))−1)`）
    #   ⇒ ⛔ **不另写一份** ⇒ 直接调 `fixed_dose_density_audit.density_of`
    #   ⇒ ⇒ 与**分析管线**（`dose_confound_audit.frac_of`）**逐位同源**
    # ⚠⚠⚖⚖⚖ **244.72 的起因**：244.71 的校验器用 `n_sites / n_eff` 判「剂量固定」
    #   ⇒ 而生产口径的**分母依赖 pos_frac** ⇒ ⇒ 两套定义只在 pos_frac=0.5 时相等
    #   ⇒ ⇒ 而既有 137 条真记录**全是 0.5** ⇒ ⇒ 这条断层在真数据上**测不出来**
    dens_mixed = []
    dens_n = 0
    dens_tids = sorted(by_tid)
    # ⚠⚠⚖⚖⚖ **244.72 更正（另一条线的复核查出来的）**：这一段原来读的是 `POOL_DEFAULT`
    #   ⇒ ⇒ **形参 `pool` 被完全忽略** ⇒ ⇒ 传**别的**池子时 G13 仍拿**默认池**算密度
    #   ⇒ ⇒ 属于「**用错来源 ⇒ 数看起来正常、其实不是那一批**」的族 ⇒ ⇒ **改用形参**
    #   ⇒ ⇒ 形参池里缺 P / n_gen ⇒ ⇒ **算不出** ⇒ ⇒ 印「未量到」
    #   ⇒ ⇒ （⛔ **不许**回退到默认池 ⇒ 那就是「偷偷换了一批」）
    _pool_ti = {}
    try:
        for _t in pool["tids"]:
            _pool_ti[_t["tid"]] = (_t.get("P"), _t.get("n_gen"))
    except Exception:
        _pool_ti = {}
    for tid in dens_tids:
        cells = by_tid[tid]
        info = _pool_ti.get(tid)
        if not info or not info[0] or not info[1]:
            continue
        vals = []
        for c in cells:
            try:
                vals.append(_load("fixed_dose_density_audit").density_of(
                    int(c["n_sites"]), int(info[0]), int(info[1]), float(c["pos_frac"])))
            except Exception:
                vals = []
                break
        if len(vals) < 2:
            continue
        dens_n += 1
        if (max(vals) - min(vals)) > tol:
            dens_mixed.append((tid, max(vals) - min(vals)))
    if dens_n == 0:
        put_premise("G13", False,
                    "**同一条轨迹的复制格密度相等**（⇒ **这才是「固定剂量」**）："
                    "⚠⚠ **算不出**（**形参 pool** 里缺 P / n_gen）⇒ ⇒ 这些轨迹的剂量"
                    "**未量到** ⇒ ⇒ ⛔ **本条没核**（⛔ 不是「没差异」）")
        premises.append("**形参 pool** 里缺 P / n_gen ⇒ ⇒ **G13 没法核** ⇒ ⇒ "
                        "那一批的「固定剂量」在**密度口径**下**未量到**")
    else:
        ok13 = not dens_mixed
        put("G13", ok13,
            "**同一条轨迹的复制格密度相等**（⇒ **这才是「固定剂量」**，生产口径）："
            "%d 条轨迹里密度**不一致**的 **%d** 条 %s（容差 %.4f）"
            % (dens_n, len(dens_mixed), "✅" if ok13 else "❌（%s）"
               % [(t, "%.4f" % s) for t, s in dens_mixed[:3]], tol))
        if not ok13:
            gaps.append("%d 条轨迹的复制格**密度不等** ⇒ ⇒ 那一批**不是固定剂量**"
                        "（⇒ 剂量与 pos_frac 混在一起 ⇒ ⇒ 与 244.48/244.50/244.51 "
                        "查到的那个跨剂量多数**同一类**）" % len(dens_mixed))

    lad = ladder_map(base)
    neff = neff_map(pool)

    # ---------- G4a scope 与规格一致
    bad_scope = [t for t, cs in by_tid.items()
                 if any(c["scope"] != scope_want for c in cs)]
    ok4a = not bad_scope
    put("G4a", ok4a,
        "**scope 与规格一致**：规格写的是 `%s`；清单里有 **%d** 条轨迹的 scope 不是它 %s"
        % (scope_want, len(bad_scope), "✅" if ok4a else "❌（%s）" % bad_scope[:3]))
    if not ok4a:
        gaps.append("%d 条轨迹的 scope 与规格不符" % len(bad_scope))

    # ---------- G4b n_sites 必须在自己阶梯上
    not_on_ladder = []
    unknown_ladder = []
    for tid, cells in sorted(by_tid.items()):
        ns = cells[0]["n_sites"]
        L = lad.get(tid)
        if not L:
            unknown_ladder.append(tid)
            continue
        if ns not in L:
            not_on_ladder.append(tid)
    ok4b = not not_on_ladder
    put("G4b", ok4b,
        "**n_sites 在它自己的阶梯上**：阶梯已知的轨迹里，n_sites **不在阶梯上**的 **%d** 条 %s"
        % (len(not_on_ladder), "✅" if ok4b else "❌（%s）" % not_on_ladder[:3]))
    if not ok4b:
        gaps.append("%d 条轨迹的 n_sites 不在它自己的 k 阶梯上" % len(not_on_ladder))

    # ---------- G4c 每条轨迹必须**恰好命中一个**分数落在 frac ± tol 的档位
    no_hit = []
    multi_hit = []
    picked = {}
    for tid, cells in sorted(by_tid.items()):
        fl = frac_ladder(lad, neff, tid)
        if fl is None:
            unknown_ladder.append(tid)
            continue
        hits = [(v, f) for (v, f) in fl if abs(f - target) <= tol]
        if len(hits) == 0:
            no_hit.append(tid)
        elif len(hits) > 1:
            multi_hit.append(tid)
        else:
            picked[tid] = hits[0]
    ok4c = (not no_hit) and (not multi_hit)
    put("G4c", ok4c,
        "**剂量分数在 frac ± tol 内恰好命中一档**：阶梯已知的 %d 条轨迹里，"
        "**命中 0 档**的 **%d** 条、**命中多档**的 **%d** 条 %s"
        % (len(picked) + len(no_hit) + len(multi_hit), len(no_hit), len(multi_hit),
           "✅" if ok4c else "❌（命中 0：%s；命中多：%s）"
           % (no_hit[:2], multi_hit[:2])))
    if not ok4c:
        gaps.append("%d 条轨迹在 frac ± tol 内命中 0 档、%d 条命中多档 ⇒ 剂量口径有歧义"
                    % (len(no_hit), len(multi_hit)))

    # ---------- G4d 清单写的 n_sites 必须就是那一档
    wrong_rung = [t for t, (v, f) in picked.items()
                  if by_tid[t][0]["n_sites"] != v]
    ok4d = not wrong_rung
    put("G4d", ok4d,
        "**清单里的 n_sites 就是那一档**：写错的轨迹 **%d** 条 %s"
        % (len(wrong_rung), "✅" if ok4d else "❌（%s）" % wrong_rung[:3]))
    if not ok4d:
        gaps.append("%d 条轨迹的 n_sites 不是 frac ± tol 命中的那一档" % len(wrong_rung))

    # ⚖⚠⚖⚖ **「各轨迹的剂量分数一致」** ⛔ **不做成判据** ——
    #   它被 **G4c + G4d** **蕴含**（每条轨迹的分数都落在 frac ± tol 内 ⇒ 跨度 ≤ 2·tol）
    #   ⇒ ⇒ 做成判据就是**恒绿**（244.62 的教训：恒绿不是绿，是量不到东西）
    #   ⇒ ⇒ 降级成**诊断**：印出实测跨度 ⇒ 供人看，不参与判决。
    fr_vals = [f for (v, f) in picked.values()]
    spread = (max(fr_vals) - min(fr_vals)) if fr_vals else 0.0
    listed_fr = []
    for tid, cells in sorted(by_tid.items()):
        n = neff.get(tid)
        if n:
            try:
                listed_fr.append(float(cells[0]["n_sites"]) / float(n))
            except ValueError:
                pass
    listed_spread = (max(listed_fr) - min(listed_fr)) if listed_fr else 0.0
    put_diag("**剂量分数的实测跨度**（⛔ **诊断**，⛔ 不参与判决）："
             "命中档位的分数跨度 **%.6f**；清单里实际写的 n_sites 换算出的分数跨度 "
             "**%.6f**（容差 %.6f）" % (spread, listed_spread, tol))
    if unknown_ladder:
        premises.append("**%d 条轨迹的 k 阶梯尚未生成**（%s…）⇒ ⇒ 它们的剂量**未量到**"
                        "⇒ ⇒ 本工具**没核**到它们 ⇒ ⛔ 不许当成「核过了」"
                        % (len(set(unknown_ladder)), ", ".join(sorted(set(unknown_ladder))[:2])))

    # ---------- G5 每条轨迹的格数
    bad_m = [t for t, cs in by_tid.items() if len(cs) != cpt]
    ok5 = (not bad_m) and bool(by_tid)
    put("G5", ok5,
        "**每条轨迹的格数 = %d**：格数不对的轨迹 **%d** 条 %s"
        % (cpt, len(bad_m), "✅" if ok5 else "❌（%s）" % bad_m[:3]))
    if not ok5:
        gaps.append("%d 条轨迹的格数不等于 %d" % (len(bad_m), cpt))

    # ---------- G6 同一条轨迹内 pos_frac 互不相同
    dup = []
    for tid, cells in sorted(by_tid.items()):
        pfs = [c["pos_frac"] for c in cells]
        if len(set(pfs)) != len(pfs):
            dup.append(tid)
    ok6 = not dup
    put("G6", ok6,
        "**同一条轨迹内 pos_frac 互不相同**（否则那几格是同一格）：重复的轨迹 **%d** 条 %s"
        % (len(dup), "✅" if ok6 else "❌（%s）" % dup[:3]))
    if not ok6:
        gaps.append("%d 条轨迹里有重复的 pos_frac ⇒ 那是重复的格" % len(dup))

    # ---------- G7 各轨迹的 pos_frac 集合必须相同（同形）
    shapes = set(frozenset(c["pos_frac"] for c in cells) for cells in by_tid.values())
    ok7 = len(shapes) <= 1
    put("G7", ok7,
        "**各轨迹的 pos_frac 集合相同**（同形 ⇒ 跨轨迹可配对）：形状 **%d** 种 %s"
        % (len(shapes), "✅" if ok7 else "❌（%s）" % sorted(
            [sorted(s) for s in shapes])[:3]))
    if not ok7:
        gaps.append("各轨迹的 pos_frac 形状有 %d 种 ⇒ 不能跨轨迹配对" % len(shapes))

    # ---------- G8 pos_frac 取值 ⊆ 路线规格
    used = set()
    for cells in by_tid.values():
        for c in cells:
            used.add(c["pos_frac"])
    try:
        used_f = set(float(x) for x in used)
    except ValueError:
        used_f = set()
        bad_num = True
    else:
        bad_num = False
    extra = sorted(used_f - set(pf_route)) if not bad_num else []
    ok8 = (not bad_num) and not extra
    put("G8", ok8,
        "**pos_frac 取值 ⊆ 路线规格**：清单用了 %s；规格允许 %s %s"
        % (sorted(used_f) if not bad_num else sorted(used),
           pf_route, "✅" if ok8 else "❌（多出 %s）" % extra))
    if not ok8:
        gaps.append("清单里有规格之外的 pos_frac 取值：%s" % extra)

    # ---------- G9 轨迹数 + think/no_think 成对
    tids = sorted(by_tid)
    # ⚖⚠⚖⚖ **成对要按「同一条题目」比**（⛔ 不是按整串 tid 比 ——
    #   `...__p00__think` 与 `...__p00__no_think` 是**不同的串** ⇒ 按整串比**恒不等** ⇒ ⇒ 恒红）
    def _key(t):
        if t.endswith("__think"):
            return t[:-len("__think")]
        if t.endswith("__no_think"):
            return t[:-len("__no_think")]
        return None
    think = set(t for t in tids if t.endswith("__think"))
    ntk = set(t for t in tids if t.endswith("__no_think"))
    other = [t for t in tids if _key(t) is None]
    k_think = set(_key(t) for t in think)
    k_ntk = set(_key(t) for t in ntk)
    want = n_blocks * 2
    ok9a = len(tids) == want
    put("G9a", ok9a,
        "**轨迹数 = %d**（%d 块 × 2）：清单里 **%d** 条 %s"
        % (want, n_blocks, len(tids), "✅" if ok9a else "❌（差 %d 条）" % (want - len(tids))))
    if not ok9a:
        gaps.append("轨迹数 %d ≠ %d" % (len(tids), want))
    ok9b = (k_think == k_ntk) and len(k_think) == n_blocks and not other
    put("G9b", ok9b,
        "**think / no_think 成对**（按同一条题目配对）：think **%d** 条 ／ no_think **%d** 条"
        "（题目 %d vs %d）%s"
        % (len(think), len(ntk), len(k_think), len(k_ntk),
           "✅" if ok9b else "❌（臂型无法识别的 %d 条）" % len(other)))
    if not ok9b:
        gaps.append("think/no_think 不成对（题目 %d vs %d；臂型无法识别 %d 条）"
                    % (len(k_think), len(k_ntk), len(other)))

    # ---------- G10 m≥3 的门槛（⛔ 复用 244.70 那条路 ⇒ 不写「3 × 档数」）
    need_cells, n_layer, sz_lines, _size = _need_cells(route)
    ok10 = cpt >= need_cells
    put("G10", ok10,
        "**m≥3 的门槛**（⛔ 由规模机械算出）：一条轨迹服务 %d 个档 ⇒ 门槛 **%d 格**；"
        "清单给 %d 格 %s" % (n_layer, need_cells, cpt, "✅" if ok10 else "❌（差 %d 格）"
                             % (need_cells - cpt)))
    if not ok10:
        gaps.append("每条轨迹 %d 格 < 门槛 %d 格（m≥3 ⇒ 平票不出现）" % (cpt, need_cells))

    # ---------- G11 每臂总格数
    per_arm = n_blocks * 2 * cpt
    ok11 = len(good) == per_arm
    put("G11", ok11,
        "**每臂的格数 = %d**（%d 块 × 2 × %d 格）：清单里 **%d** 格 %s"
        % (per_arm, n_blocks, cpt, len(good), "✅" if ok11 else "❌（差 %d 格）"
           % (per_arm - len(good))))
    if not ok11:
        gaps.append("每臂格数 %d ≠ %d" % (len(good), per_arm))

    # ---------- G12 pos_frac 轴的已测性（前提，⛔ 不判失败）
    pf_meas = [float(x) for x in pool["pos_frac"]["measured"]]
    unmeasured = sorted(x for x in pf_route if x not in pf_meas)
    ok12 = not unmeasured
    put_premise("G12", ok12,
        "**pos_frac 轴的已测性**（⚠ **前提类** ⇒ ⛔ **不判失败**）：这一批要用 pos_frac %s；"
        "**已测过**的只有 %s ⇒ %s"
        % (pf_route, pf_meas,
           "✅ 全是已测取值" if ok12 else "⚠⚠ **未量到**：%s（已测取值里没有）" % unmeasured))
    if not ok12:
        premises.append("pos_frac 取值 %s **未量到**（已测过的只有 %s）⇒ "
                        "**这一批同时是这条轴的首次测量** ⇒ 它的结论**不能**被说成「已验证过这条轴」"
                        % (unmeasured, pf_meas))
    for p in spec.get("premises", []):
        premises.append(str(p))

    blocking = [g for g in G_BLOCKING if not R.get(g, False)]
    can = not blocking
    return rows, {
        "R": R, "rows": rows, "gaps": gaps, "premises": premises,
        "notes": notes,
        "can": can, "blocking": blocking,
        "n_tid": len(tids), "n_rows": len(crows), "n_good": len(good),
        "per_arm_cells": per_arm, "need_cells": need_cells, "n_layer": n_layer,
        "unknown_ladder": sorted(set(unknown_ladder)), "picked": picked,
        "frac_spread": spread, "listed_frac_spread": listed_spread,
    }


_NEED_CELLS_CACHE = {}


def _need_cells(route, prereg_path=None):
    """⚖ m≥3 的门槛 ⇒ **复用 244.70 那条路**（⛔ 本文件不写「3 × 档数」这个公式）。
    ⚖⚠⚖ 走的正是 `fixed_dose_feasible.need_cells_from_mechanic`
      ⇒ ⇒ 与 244.70 的 **F1** **同一份公式** ⇒ ⇒ 两处不会漂。
    ⚖ 逐档比例取**预登记里登记的那一组**（`REGISTERED_PROPS`）⇒ ⇒ 印出来的规模行
      与账本 244.66 登记的 130/177/31/14 **一致** ⇒ ⇒ ⛔ 不在这里另编比例。
    ⚖⚠ **结果缓存**（纯函数 ⇒ 缓存不改变任何输出）⇒ 避免每次核清单都重跑一遍精确枚举。"""
    ck = (int(route["cells_per_track"]), prereg_path or "")
    if ck in _NEED_CELLS_CACHE:
        return _NEED_CELLS_CACHE[ck]
    F = fdf()
    P = F.pre()
    prereg_path = prereg_path or F.PREREG
    Fd = P.fda()          # ⚖ `fixed_dose_audit`（⛔ 口径的运行时真相源）
    cfg = Fd.Cfg(Fd.read_prereg(prereg_path))
    design = {
        "dose_mode": "fixed",
        "cells_per_track": float(route["cells_per_track"]),
        "expected_proportions": P.REGISTERED_PROPS,
    }
    rows = F._rows_from(design, cfg)
    need, n_layer, lines, size = F.need_cells_from_mechanic(design, rows, cfg)
    _NEED_CELLS_CACHE[ck] = (need, n_layer, lines, size)
    return need, n_layer, lines, size


def build_demo(spec, pool, base):
    """⚖ 造一份**能核的**演示清单：只用**阶梯已知**的那些轨迹
    ⇒ ⇒ 它的块数 = **阶梯已知的对数**（⛔ 不是路线要的块数 ⇒ ⇒ 必须写清楚）
    ⇒ ⇒ 用途：在**真件**上跑通「印清单 ⇒ 核清单」的**绿路径**（⛔ 不是那一批的清单）。

    ⚠⚠⚖⚖⚖ **244.72 更正**：这份演示清单用的是「同一轨迹三个 pos_frac **共用同一 n_sites**」
    ⇒ ⇒ 在**生产密度口径**下它的复制格**密度不等** ⇒ ⇒ **G13 必红** ⇒ ⇒
    ⇒ ⇒ 它现在**只演示「格式与配对」** ⇒ ⇒ ⛔ **不是一份可以发的清单**。"""
    lad = ladder_map(base)
    neff = neff_map(pool)
    target = float(spec["dose"]["frac"])
    tol = float(spec["dose"]["tol"])
    pairs = [p for p in _pairs_from_ladder(lad)
             if all(_pick_rung(lad, neff, t, target, tol) for t in p)]
    route = dict(spec["route"])
    route["n_blocks"] = len(pairs)
    route["target_tracks_per_arm"] = len(pairs) * 2
    route["route_id"] = "%s（演示：只用阶梯已知的 %d 对）" % (spec["route"]["route_id"], len(pairs))
    spec2 = dict(spec)
    spec2["route"] = route
    spec2["spec_id"] = "%s（演示）" % spec["spec_id"]
    lines = ["\t".join(COLUMNS)]
    for pair in pairs:
        for t in pair:
            v, f = _pick_rung(lad, neff, t, target, tol)
            for pf in spec["route"]["pos_fracs"]:
                lines.append("\t".join([t, spec["dose"]["scope"], v, str(pf)]))
    return spec2, "\n".join(lines) + "\n", len(pairs)


def render_check(spec, verdict, cells_path):
    out = []
    out.append("=" * 78)
    out.append("【发批清单校验】⚖⚖⚖ 这份清单能不能发（244.71，零 GPU）")
    out.append("=" * 78)
    out.append("  ⚖ 清单：`%s`（%d 行）" % (cells_path, verdict["n_rows"]))
    out.append("  ⚖ 规格：`%s`" % spec["spec_id"])
    out.append("")
    for ln in verdict["rows"]:
        out.append(ln)
    out.append("")
    if verdict["can"]:
        out.append("  ✅ **这份清单可以发**（阻断类判据全绿）")
        out.append("     ⇒ ⛔ 但**本工具不发批** ⇒ ⛔ 发不发 / 跑不跑 ⇒ **要用户点头**")
    else:
        out.append("  🔴 **这份清单不能发** —— 阻断 %d 条：" % len(verdict["blocking"]))
        for i, g in enumerate(verdict["gaps"], 1):
            out.append("    %d) %s" % (i, g))
    if verdict.get("notes"):
        out.append("")
        out.append("  ⚠⚠⚖ **提示（⛔ 不阻断，但必须看）**：")
        for i, n in enumerate(verdict["notes"], 1):
            out.append("    %d) %s" % (i, n))
    if verdict["premises"]:
        out.append("")
        out.append("  ⚠⚠⚠ **前提（未量到）** —— ⛔ **不许**说成「已验证」：")
        for i, p in enumerate(verdict["premises"], 1):
            out.append("    %d) %s" % (i, p))
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- 自检
def _mk(tmp, name, text):
    p = os.path.join(tmp, name)
    io.open(p, "w", encoding="utf-8").write(text)
    return p


def _pairs_from_ladder(lad):
    """⚖ 从**真阶梯**里取出成对的 (think, no_think) 轨迹 ⇒ ⛔ 不手打 tid。
    ⚖ 配对规则：同一条题目（`...__pNN__<臂型>`）的两个臂型。"""
    tids = sorted(lad)
    pmap = {}
    for t in tids:
        if t.endswith("__think"):
            pmap.setdefault(t[:-len("__think")], {})["think"] = t
        elif t.endswith("__no_think"):
            pmap.setdefault(t[:-len("__no_think")], {})["no_think"] = t
    pairs = []
    for k in sorted(pmap):
        if "think" in pmap[k] and "no_think" in pmap[k]:
            pairs.append((pmap[k]["think"], pmap[k]["no_think"]))
    return pairs


def _pick_rung(lad, neff, tid, target, tol):
    """⚖ 按**分数**挑档（⛔ 不按序号 ⇒ 实测序号不可靠）。"""
    fl = frac_ladder(lad, neff, tid)
    if not fl:
        return None
    hits = [(v, f) for (v, f) in fl if abs(f - target) <= tol]
    return hits[0] if len(hits) == 1 else None


def _good_cells_text(route, pool, base, scope="k", target=0.25, tol=0.005,
                     n_pairs=4, cpt=3, pfs=(0.25, 0.5, 0.75)):
    """⚖ 造一份**干净**的格清单（⛔ 用的都是**真阶梯**上按**分数**挑中的档位
    ⇒ ⇒ 走的是与真件同一条路 ⇒ ⇒ 不会因为「夹具自己造不出合法剂量」而假红）。"""
    lad = ladder_map(base)
    neff = neff_map(pool)
    pairs = _pairs_from_ladder(lad)
    lines = ["\t".join(COLUMNS)]
    used = 0
    for i in range(len(pairs)):
        t_think, t_nt = pairs[i]
        r_think = _pick_rung(lad, neff, t_think, target, tol)
        r_nt = _pick_rung(lad, neff, t_nt, target, tol)
        if r_think is None or r_nt is None:
            continue
        used += 1
        if used > n_pairs:
            break
        for tid, (v, f) in ((t_think, r_think), (t_nt, r_nt)):
            for pf in pfs:
                lines.append("\t".join([tid, scope, v, str(pf)]))
    assert used >= n_pairs, "真阶梯里按分数挑不出 %d 对轨迹（只挑到 %d 对）" % (n_pairs, used)
    return "\n".join(lines) + "\n"


def _base(base_path=BASE_DEFAULT):
    return _read_json(base_path, "成本基线")


def selftest(pool_path=POOL_DEFAULT, base_path=BASE_DEFAULT):
    """⚖⚠⚖ **每条判据都要有红化反例**（⛔ 恒绿的判据不许留）。"""
    import tempfile
    import shutil
    pool = fdf().read_pool(pool_path)
    base = _base(base_path)
    ok, bad = [], []

    def chk(name, cond, msg):
        (ok if cond else bad).append(name)
        if not cond:
            print("[FAIL] %s：%s" % (name, msg))

    TARGET_F = 0.25
    TOL = 0.005
    route = {
        "route_id": "selftest", "strategy": "measure_first",
        "target_tracks_per_arm": 8, "n_blocks": 4, "cells_per_track": 3,
        "pos_fracs": [0.25, 0.5, 0.75], "arms": ["w", "rand"],
    }
    tmp = tempfile.mkdtemp(prefix="fddisp_")
    try:
        spec = build_spec(route, "k", TARGET_F, TOL)
        # ---- 基线：一份**干净**的清单 ⇒ 全绿
        txt = _good_cells_text(route, pool, base, target=TARGET_F, tol=TOL,
                               n_pairs=4, cpt=3)
        p = _mk(tmp, "good.tsv", txt)
        rows, v = check_cells(spec, p, pool, base)
        # ⚠⚠⚖⚖⚖ **244.72 更正**：244.71 把这份清单当「干净清单 ⇒ 全绿」⇒
        #   但它用的是「同一条轨迹三个 pos_frac **共用同一个 n_sites**」的形状
        #   ⇒ ⇒ 在**生产密度口径**下它的复制格**密度不等** ⇒ ⇒ **G13 必红**
        #   ⇒ ⇒ 「全绿」那句话是**基于错口径**的 ⇒ ⇒ 这里改成诚实版本。
        chk("T1", v["blocking"] == ["G13"],
            "基线清单（244.71 形状）⇒ 阻断**恰好**只有 G13（实际 %s）" % v["blocking"])
        chk("T1b", all(v["R"][g] for g in G_BLOCKING if g != "G13"),
            "基线清单的**其余**阻断类判据应全绿")
        chk("T1c", "G13" in G_BLOCKING,
            "G13 必须在阻断集里 ⇒ 「固定剂量」这条要参与判决")
        # ---- T24 / T24b：**G13** 的红化反例（台架 M20 / M21 盯着这两条）
        chk("T24", (not v["R"]["G13"]),
            "ladder 形状（三个 pos_frac **共用同一个 n_sites**）⇒ 复制格**密度不等** ⇒ "
            "G13 必须红（⛔ 这正是 244.72 的发现）")
        chk("T24b", (not v["R"]["G13"]) and (not v["can"]),
            "G13 红 ⇒ 判决必须是「**不能发**」（⇒ G13 若被踢出阻断集，这里要红）")

        # ---- T25：**G13 必须用形参 `pool`**（244.72 更正后新增）
        #   ⚠⚠⚖⚖⚖ 另一条线的复核查出来：G13 原来读 `POOL_DEFAULT` ⇒ **忽略形参 pool**
        #   ⇒ ⇒ 「用错来源 ⇒ 数看起来正常、其实不是那一批」的族
        #   ⇒ ⇒ 这里造一个**缺 P / n_gen** 的池子 ⇒ G13 必须**算不出** ⇒ 印「未量到」
        #   ⇒ ⇒ （若 G13 偷偷回退到默认池 ⇒ 它照样能算出数 ⇒ 这里红）
        pool_nopn = {"tids": [dict(t, P=None, n_gen=None) for t in pool["tids"]],
                     "pos_frac": pool.get("pos_frac", {})}
        _r, v25 = check_cells(spec, p, pool_nopn, base)
        #   ⚠⚠⚖⚖⚖ **认专属标记，不认泛泛的「未量到」**（第一次写成 `any("未量到" in t ...)`
        #   ⇒ ⇒ 被**别的**前提（G12 的「未量到轴」）蒙混过去 ⇒ ⇒ 台架 M22 **存活**
        #   ⇒ ⇒ ⇒ 判据必须能分辨「**G13 这一条**算不出」与「别的前提算不出」
        chk("T25", (not v25["R"]["G13"]) and any("缺 P / n_gen" in t for t in v25["premises"]),
            "G13 必须读**形参 pool**（池里缺 P/n_gen ⇒ 必须印「G13 没法核 ⇒ 未量到」"
            "⇒ ⛔ 不许回退到默认池）")

        # ---- G1：没有 pos_frac 列 ⇒ 红
        p2 = _mk(tmp, "nopf.tsv", "\n".join(
            ["\t".join(COLUMNS[:3])] + [ln for ln in txt.split("\n")[1:]]) + "\n")
        _r, v2 = check_cells(spec, p2, pool, base)
        chk("T2", (not v2["R"]["G1"]) and (not v2["can"]),
            "没有 pos_frac 列 ⇒ G1 必须红且判「不能发」")

        # ---- G2：列数不对 ⇒ 红
        p3 = _mk(tmp, "badcols.tsv", txt.replace("\t0.25", "\t0.25\tX"))
        _r, v3 = check_cells(spec, p3, pool, base)
        chk("T3", (not v3["R"]["G2"]) and (not v3["can"]), "列数不对 ⇒ G2 必须红")

        # ---- G3：同一条轨迹内剂量不一致 ⇒ 红
        lines = txt.split("\n")
        lines[1] = lines[1].replace("\tk\t", "\tkX\t")
        p4 = _mk(tmp, "mixed.tsv", "\n".join(lines))
        _r, v4 = check_cells(spec, p4, pool, base)
        chk("T4", (not v4["R"]["G3"]) and ("G3" not in G_BLOCKING),
            "同轨迹内**注入参数**不一致 ⇒ G3 必须红（且 ⛔ 它**不参与**阻断）")

        # ---- G4b：n_sites 不在阶梯上 ⇒ 红（⛔ **只换值**，⛔ 不许多出一列 ⇒ 否则测的是 G2）
        out5 = []
        for ln in txt.split("\n"):
            c = ln.split("\t")
            if len(c) == 4 and c[1] == "k":
                c[2] = "999999"
                ln = "\t".join(c)
            out5.append(ln)
        p5 = _mk(tmp, "offladder.tsv", "\n".join(out5))
        _r, v5 = check_cells(spec, p5, pool, base)
        chk("T5", (not v5["R"]["G4b"]) and (not v5["can"]),
            "n_sites 不在阶梯上 ⇒ G4b 必须红（阻断：%s）" % v5["blocking"])

        # ---- G4c：**命中多档** ⇒ 红（把容差放大到覆盖两档 ⇒ 目标档位**歧义**）
        #   ⚠⚠⚖ 判据必须**只踩它那一支** ⇒ ⇒ G4b（仍在阶梯上）绿、G4d（没有唯一命中）绿
        spec_loose = build_spec(route, "k", 0.5, 0.26)
        _r, v5b = check_cells(spec_loose, p, pool, base)
        chk("T5b", (not v5b["R"]["G4c"]) and v5b["R"]["G4b"] and v5b["R"]["G4d"],
            "容差放大到覆盖多档 ⇒ G4c 必须红，而 G4b / G4d 仍绿（阻断：%s）" % v5b["blocking"])

        # ---- G4d：清单写的 n_sites **不是**命中的那一档 ⇒ 红
        #   ⇒ 换成**阶梯上另一个分数很远**的档 ⇒ 仍在阶梯上（G4b 绿）、
        #   ⇒ 而阶梯里 frac±tol 仍**只命中一档**（G4c 绿）⇒ ⇒ 只踩 G4d 那一支
        lad = ladder_map(base)
        neff = neff_map(pool)
        pairs = _pairs_from_ladder(lad)
        t0 = pairs[0][0]
        fl = frac_ladder(lad, neff, t0)
        alt = None
        for (_v, _f) in fl:
            if abs(_f - TARGET_F) > 0.1:
                alt = _v
                break
        if alt is not None:
            out5c = []
            for ln in txt.split("\n"):
                c = ln.split("\t")
                if len(c) == 4 and c[0] == t0:
                    c[2] = alt
                    ln = "\t".join(c)
                out5c.append(ln)
            p5c = _mk(tmp, "d.tsv", "\n".join(out5c))
            _r, v5c = check_cells(spec, p5c, pool, base)
            chk("T5c", (not v5c["R"]["G4d"]) and v5c["R"]["G4b"] and v5c["R"]["G4c"],
                "清单写的 n_sites 不是命中的那一档 ⇒ G4d 必须红，而 G4b / G4c 仍绿"
                "（阻断：%s）" % v5c["blocking"])

        # ---- G5：格数不对 ⇒ 红（⛔ 真的**删掉一行**）
        _lines7 = [ln for ln in txt.split("\n") if ln.strip() != ""]
        p7 = _mk(tmp, "m.tsv", "\n".join(_lines7[:-1]) + "\n")
        _r, v7 = check_cells(spec, p7, pool, base)
        chk("T7", (not v7["R"]["G5"]) and (not v7["can"]),
            "少一格 ⇒ G5 必须红（阻断：%s）" % v7["blocking"])

        # ---- G6：pos_frac 重复 ⇒ 红
        out8 = []
        seen = set()
        for ln in txt.split("\n"):
            if ln.endswith("\t0.75") and not seen:
                ln = ln.replace("\t0.75", "\t0.25")
                seen.add(1)
            out8.append(ln)
        p8 = _mk(tmp, "dup.tsv", "\n".join(out8))
        _r, v8 = check_cells(spec, p8, pool, base)
        chk("T8", (not v8["R"]["G6"]) and (not v8["can"]), "pos_frac 重复 ⇒ G6 必须红")

        # ---- G7：各轨迹形状不同 ⇒ 红
        out9 = []
        first = True
        for ln in txt.split("\n"):
            if first and ln.endswith("\t0.75"):
                ln = ln.replace("\t0.75", "\t0.9")
                first = False
            out9.append(ln)
        p9 = _mk(tmp, "shape.tsv", "\n".join(out9))
        _r, v9 = check_cells(spec, p9, pool, base)
        chk("T9", (not v9["R"]["G7"]) and (not v9["can"]), "形状不一致 ⇒ G7 必须红")

        # ---- G8：规格外的 pos_frac ⇒ 红
        p10 = _mk(tmp, "extra.tsv", txt.replace("\t0.75", "\t0.9"))
        _r, v10 = check_cells(spec, p10, pool, base)
        chk("T10", (not v10["R"]["G8"]) and (not v10["can"]), "规格外的 pos_frac ⇒ G8 必须红")

        # ---- G9：轨迹数不对 ⇒ 红
        p11 = _mk(tmp, "few.tsv", "\n".join(txt.split("\n")[:5]) + "\n")
        _r, v11 = check_cells(spec, p11, pool, base)
        chk("T11", (not v11["R"]["G9a"]) and (not v11["can"]), "轨迹数不对 ⇒ G9a 必须红")

        # ---- G10：格数不足 m≥3 ⇒ 红
        route2 = dict(route, cells_per_track=2, n_blocks=4)
        spec2 = build_spec(route2, "k", TARGET_F, TOL)
        p12 = _mk(tmp, "m2.tsv", _good_cells_text(route2, pool, base, target=TARGET_F,
                                                  tol=TOL, n_pairs=4, cpt=2))
        _r, v12 = check_cells(spec2, p12, pool, base)
        chk("T12", (not v12["R"]["G10"]) and (not v12["can"]),
            "每条 2 格 < 门槛 3 ⇒ G10 必须红")

        # ---- G11：总格数不对 ⇒ 红
        out13 = []
        for i, ln in enumerate(txt.split("\n")):
            if i == 3:
                continue
            out13.append(ln)
        p13 = _mk(tmp, "cells.tsv", "\n".join(out13))
        _r, v13 = check_cells(spec, p13, pool, base)
        chk("T13", (not v13["R"]["G11"]) and (not v13["can"]), "总格数不对 ⇒ G11 必须红")

        # ---- G12：pos_frac 未测过 ⇒ **前提**，⛔ 不判失败
        _r, v14 = check_cells(spec, p, pool, base)
        chk("T14", (not v14["R"]["G12"]) and len(v14["premises"]) >= 1,
            "G12 红必须进前提清单")
        chk("T14b", ("G12" not in G_BLOCKING) and (not v14["R"]["G12"]),
            "G12 是**前提类** ⇒ ⛔ 不在阻断集里 ⇒ ⛔ 不许**单独因为它**判「不能发」")
        chk("T14c", "G12" not in G_BLOCKING, "G12 ⛔ 不许进阻断集")

        # ---- T21：G12 那一行**不许**印成 FAIL（⇒ 未量到 ≠ 失败）
        _rows14 = "\n".join(v14["rows"])
        chk("T21", "[FAIL] G12" not in _rows14,
            "前提类判据 G12 不许印成 FAIL（⇒ 未量到 ≠ 失败）")
        chk("T21b", "[前提] G12" in _rows14, "G12 那一行应该印成 [前提]")

        # ---- T23：**诊断行必须真的印出来**（⛔ 注释里说「印出」而代码没印 ⇒ 那是**说谎**）
        _rows14b = "\n".join(v14["rows"])
        chk("T23", "[诊断]" in _rows14b, "诊断行（剂量分数的实测跨度）必须印出来")
        chk("T23b", "实测跨度" in _rows14b, "诊断行必须写明它印的是什么")

        # ---- T19：**只有 G9b 红**的夹具（纪律：一条判据拆两支 ⇒ 两支各要一条夹具）
        out19 = ["\t".join(COLUMNS)]
        for i in range(3):
            for _t in pairs[i]:
                _rung = _pick_rung(lad, neff, _t, TARGET_F, TOL)
                for _pf in (0.25, 0.5, 0.75):
                    out19.append("\t".join([_t, "k", _rung[0], str(_pf)]))
        for _t in (pairs[3][0], pairs[4][0]):
            _rung = _pick_rung(lad, neff, _t, TARGET_F, TOL)
            for _pf in (0.25, 0.5, 0.75):
                out19.append("\t".join([_t, "k", _rung[0], str(_pf)]))
        p19 = _mk(tmp, "pair.tsv", "\n".join(out19) + "\n")
        _r, v19 = check_cells(spec, p19, pool, base)
        chk("T19", (not v19["R"]["G9b"]) and v19["R"]["G9a"],
            "只有 G9b 红 ⇒ G9b 必须红且 G9a 必须绿（阻断：%s）" % v19["blocking"])

        # ---- T20：**真件**上的绿路径（演示清单 ⇒ 必须全绿）
        #   ⚖ 这就是「每条判据配一个『干净输入必须全绿』的合成夹具」的落点
        spec20, cells20, np20 = build_demo(spec, pool, base)
        p20 = _mk(tmp, "demo.tsv", cells20)
        _r, v20 = check_cells(spec20, p20, pool, base)
        # ⚠⚠⚖⚖⚖ **244.72 更正**：演示清单用的是「三个 pos_frac **共用同一 n_sites**」的
        #   形状 ⇒ ⇒ 在**生产密度口径**下它**不是固定剂量** ⇒ ⇒ **G13 必红**
        #   ⇒ ⇒ 244.71 那句「演示清单必须全绿」是基于**错口径**的 ⇒ ⇒ 诚实改写。
        chk("T20", (v20["blocking"] == ["G13"])
            and all(v20["R"][g] for g in G_BLOCKING if g != "G13"),
            "真件上的演示清单 ⇒ 阻断**恰好**只有 G13（实际 %s）" % v20["blocking"])
        chk("T20b", np20 >= 1, "演示必须至少挑到 1 对轨迹（得 %d）" % np20)

        # ---- T15：**印出来的**判决必须与返回的一致（⚖ 判决只算一次）
        txt15 = render_check(spec, v, p)
        chk("T15", ("这份清单可以发" in txt15) == v["can"],
            "报告里的判决与返回的判决必须一致")
        chk("T15b", ("前提（未量到）" in txt15) == bool(v["premises"]),
            "前提段的有无必须与返回一致")

        # ---- G4a：scope 与规格不符 ⇒ 红（⛔ **只改一条轨迹的全部格**
        #   ⇒ 那条轨迹内部仍自洽 ⇒ ⇒ G3 仍绿 ⇒ ⇒ 只踩 G4a 那一支）
        out4a = []
        t_first = sorted(set(ln.split("\t")[0] for ln in txt.split("\n")
                             if len(ln.split("\t")) == 4))[0]
        for ln in txt.split("\n"):
            c = ln.split("\t")
            if len(c) == 4 and c[0] == t_first:
                c[1] = "kX"
                ln = "\t".join(c)
            out4a.append(ln)
        p4a = _mk(tmp, "scope.tsv", "\n".join(out4a))
        _r, v4a = check_cells(spec, p4a, pool, base)
        chk("T22", (not v4a["R"]["G4a"]) and v4a["R"]["G3"],
            "scope 与规格不符 ⇒ G4a 必须红，而 G3 仍绿（阻断：%s）" % v4a["blocking"])

        # ---- T16：模板必须**印出** 4 列 ＋ 写明「示例」
        t16 = render_template(spec, route, base, pool)
        chk("T16", "\t".join(COLUMNS) in t16 and "示例" in t16,
            "模板必须印出 4 列表头 ＋ 标明示例行")

        # ---- T17：坏输入 ⇒ **干净**的 HardFail（⛔ 不是 traceback）
        try:
            read_spec(_mk(tmp, "badspec.json", json.dumps({"spec_id": "x"})))
            chk("T17", False, "缺键的规格必须抛 HardFail")
        except HardFail:
            chk("T17", True, "")
        except Exception as e:
            chk("T17", False, "缺键的规格抛的是 %r" % type(e))
        try:
            read_spec(_mk(tmp, "badrung.json",
                          json.dumps({"spec_id": "x", "route": route,
                                      "dose": {"scope": "k", "frac": 0.25},
                                      "arms": ["w"]})))
            chk("T18", False, "dose 缺 tol 必须抛 HardFail")
        except HardFail:
            chk("T18", True, "")
        except Exception as e:
            chk("T18", False, "dose 缺 tol 抛的是 %r" % type(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


# ---------------------------------------------------------------- CLI
def main():
    import argparse
    ap = argparse.ArgumentParser(description="发批清单模板 ＋ 清单校验器（244.71，零 GPU）")
    ap.add_argument("--emit-template", action="store_true")
    ap.add_argument("--emit-demo", action="store_true",
                    help="造一份**能核的**演示清单（只用阶梯已知的轨迹）⇒ 跑通绿路径")
    ap.add_argument("--check", default=None, help="填好的格清单（TSV）")
    ap.add_argument("--route", default=None)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--spec-out", default=None)
    ap.add_argument("--cells-out", default=None)
    ap.add_argument("--dose-scope", default=None)
    ap.add_argument("--dose-frac", default=None)
    ap.add_argument("--dose-tol", default=None)
    ap.add_argument("--pool", default=POOL_DEFAULT)
    ap.add_argument("--baseline", default=BASE_DEFAULT)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    try:
        if a.selftest:
            return selftest(a.pool, a.baseline)
        pool = fdf().read_pool(a.pool)
        base = _base(a.baseline)
        if a.emit_template:
            if not a.route:
                raise HardFail("--emit-template 需要 --route")
            if not a.dose_scope or a.dose_frac is None or a.dose_tol is None:
                raise HardFail("--emit-template 需要 --dose-scope / --dose-frac / --dose-tol"
                               "（⛔ 不许默认值兜底 ⇒ 剂量口径是**规格**的一部分）")
            route = read_route(a.route)
            spec = build_spec(route, a.dose_scope, float(a.dose_frac), float(a.dose_tol))
            print(render_template(spec, route, base, pool))
            if a.spec_out:
                io.open(a.spec_out, "w", encoding="utf-8").write(
                    json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
                print("  ⚖ 规格已写出：`%s`" % a.spec_out)
            return 0
        if a.emit_demo:
            if not a.spec:
                raise HardFail("--emit-demo 需要 --spec")
            spec = read_spec(a.spec)
            spec2, cells_txt, npairs = build_demo(spec, pool, base)
            if a.cells_out:
                io.open(a.cells_out, "w", encoding="utf-8").write(cells_txt)
                print("  ⚖ 演示清单已写出：`%s`（%d 行 / %d 对轨迹）"
                      % (a.cells_out, cells_txt.count("\n") - 1, npairs))
            if a.spec_out:
                io.open(a.spec_out, "w", encoding="utf-8").write(
                    json.dumps(spec2, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
                print("  ⚖ 演示规格已写出：`%s`" % a.spec_out)
            print("  ⚠⚠⚠ **这是演示**（⛔ 不是那一批的清单）⇒ 它只用**阶梯已知**的 %d 对轨迹"
                  " ⇒ ⇒ 完整清单要等**生成侧**产出（⇒ 要用户点头）" % npairs)
            return 0
        if a.check:
            if not a.spec:
                raise HardFail("--check 需要 --spec（⛔ 清单必须对着**规格**核）")
            spec = read_spec(a.spec)
            rows, v = check_cells(spec, a.check, pool, base)
            print(render_check(spec, v, a.check))
            return 0 if v["can"] else 1
        print("用法：--emit-template --route <json> --dose-scope k --dose-frac <f> --dose-tol <t> "
              "｜ --check <tsv> --spec <json> ｜ --selftest", file=sys.stderr)
        return 2
    except (HardFail, fdc().HardFail if hasattr(fdc(), "HardFail") else HardFail) as e:
        print("PRECOND_FAIL: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
