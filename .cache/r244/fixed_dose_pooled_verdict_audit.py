#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""固定剂量「合池判决层」分析器（244.80，里程碑 **M3**）。

⚖⚖⚖ **它是谁**
   预登记 `.cache/xcheck/R6_FIXED_DOSE_POOLED_VERDICT_PREREG.md`（**V1–V12** ＋
   判据 **V-P1…V-P18**）指定的**唯一**判决层实现 ⇒ ⇒ **口径只从预登记/规格读**
   （⛔ 代码里不写死、⛔ 不默认值兜底）⇒ ⇒ 统计机械（多数规则 / 零假设 / 区间 /
   精确 Fisher / 配对置换）**一律复用既有模块**，⛔ 不另写一份
   （244.61 的教训：同一个概念两个实现 ⇒ 两套口径悄悄分叉）。

⚖ **数据流**（每一跳都有真源）
   跑批日志（一趟，3 个 `pos_frac` 混在一起）
     └─ 拆分器 `fixed_dose_split_log.py`（按 `pos_frac` 拆三份 ⇒ 读数器读得动）
          └─ 权威读数器 `r227_kcurve.py`（⛔ **一个字都不改** ⇒ 既有收据全部有效）
               └─ **本文件**（合池 ⇒ 判决面板）

⛔ **本文件不做**：⛔ 不改读数器、⛔ 不改探针、⛔ 不跑批、⛔ 不改任何预登记、
   ⛔ 不「顺手」把旧批的数重算一遍（⛔ 旧批交叉对照只作**判据 V-P18** 的锚点）。

⚖⚖⚖ **三条容易踩的坑（本文件显式处理）**
   ① **「未量到」不是 0、不是「不适用」、也不是「无差异」**：
      读数整块缺失 ⇒ **剔出格集合**（V3）并计入「未量到格」；
      读数在但 `p9_lo_meas/p9_hi_meas` 缺 ⇒ **HardFail**（V-P3）；
      口径不适用（例：问题级需要 `scope=all` 的格）⇒ 印「**不适用**」并写明**为什么**。
   ② **零假设基准不是恒等于 0.5**（V4）：逐轨迹算 `majority_base_p2(nz, n_zero)` 再平均。
   ③ **不许把两个 CI 相减**（V11）：差区间一律 Newcombe95。
"""

import argparse
import collections
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
MUTBAK = os.path.join(REPO, ".cache", "mutbak")

PREREG_POOLED = os.path.join(REPO, ".cache", "xcheck",
                              "R6_FIXED_DOSE_POOLED_VERDICT_PREREG.md")
PREREG_VARIANT = os.path.join(REPO, ".cache", "xcheck",
                               "R6_FIXED_DOSE_VARIANT_PREREG.md")
SPEC_DISPATCH = os.path.join(HERE, "fixed_dose_dispatch_spec_example.json")
SPEC_ROUTE = os.path.join(HERE, "fixed_dose_route_measure_first.json")
SPLITTER = os.path.join(HERE, "fixed_dose_split_log.py")
READER_MD5 = "1e31c78ed8f88a61099d2b7fd89665d5"
# ⚖ 读数器的**候选路径**（⛔ 靠 md5 认它，⛔ 不靠路径认它）
READER_CANDIDATES = [
    os.path.join(MUTBAK, "r227_kcurve.py"),
    os.path.join(HERE, "_k23_reader_r227_kcurve.py"),
]

# ⚖⚖⚖ **期望集是独立字面量**（⛔ 不许从被检对象派生 ⇒ 不许「读出来再比读出来」）
EXPECT_POOLED = {
    "sign_source_primary": "d_gt_0",
    "sign_source_secondary": "up_mono_meas",
    "pool_rule": "strict_majority_ties_false",
    "cell_set": "scope_k_reading_present_nsites_true_density_equal",
    "null_base": "per_traj_majority_base_p2_then_mean",
    "null_sim_rule": "zero_cell_never_coin_threshold_npos2_gt_nnz_nzero",
    "heterogeneity": "split_pos_frac_groups_plus_disagreement_rate",
    "alt_majority": "report_required",
    "block_level": "report_required",
    "cross_arm": "paired_permutation_and_exact_fisher",
    "interval": "wilson95_ratio_newcombe95_diff",
    "alpha": "0.05",
    "sign_date": "2026-10-23",
}
EXPECT_VARIANT = {
    "alpha": "0.05",
    "n_bands": "1",
    "boundary": "prod",
    "quantile": "inclusive",
    "zero_span": "keep",
    "majority_rule": "nT_gt_nF_zero_counts_as_False",
    "report_alt_majority": "required",
    "layer_base": "exact_binomial",
    "cross_arm_test": "paired_permutation",
    "fisher_method": "exact_enumeration",
    "interval_ratio": "wilson95",
    "interval_diff": "newcombe95",
    "mc_band": "required",
    "blocks_needed_sign_test": "20",
    "blocks_needed_cluster": "14",
    "blocks_needed_fisher_exact": "13",
    "sign_date": "2026-10-23",
}

# ⚖ **前提清单**（V-P14：必须逐条印出；⛔ 少印一条必须红）
PREMISES = [
    ("【P1】", "**前提独立性未量到**：56 条轨迹 = 28 块 × 2；块内还有 3 个复制格"
               "⇒ ⇒ 面板上每一个 p 与每一个区间都建立在这个**没被验过**的前提上"),
    ("【P2】", "**`pos_frac = 0.25 / 0.75` 从没被测过**（旧批只有 0.5）⇒ ⇒ "
               "那两组的任何行为**未量到**；合池组**不能**替它们说话"),
    ("【P3】", "**三复制格的实现间一致性（分歧率）是前提，不是判决**（V6）"),
    ("【P4】", "**剂量趋势未量到**：合池（`n_bands = 1`）没有剂量轴 ⇒ ⇒ ⛔ **不是「无趋势」**"),
    ("【P5】", "**问题级不适用**：问题级 Δ 需要 `scope = all` 的格，本批**没有** ⇒ ⇒ "
               "印「不适用」并写明原因，⛔ **不是「未量到」**，⛔ **不是「无差异」**"),
]
# ⚖ **边界清单**（V-P15：**双向**对上 ⇒ 少印红、多印也红）
BOUNDARIES = [
    "固定剂量下 w/rand **各改判多少题、差多少 pp、p 值与区间** ⇒ 本面板给的是"
    "**合池（3 个 `pos_frac` 多数）**口径，⛔ 不是「单剂量」口径",
    "**零格**（`d == 0`）**进分母、不进基准**（V4/V5）⇒ ⇒ 基准**不是**恒等于 0.5",
    "**零格剔出分母**那一条多数规则（V8）**必须同时看** ⇒ 两条**不等**时以主口径为准并标出",
    "**区间**：比例 Wilson95；两臂之差 Newcombe95（⛔ **不是**两个 CI 相减）",
    "**跨臂 Fisher 是精确枚举**（⛔ 不是正态近似）",
    "**块级分母是块数**（⛔ 不是轨迹数）",
    "**前提独立性未量到** ⇒ ⇒ 「显著」是**口径依赖**的",
    "**`pos_frac = 0.25 / 0.75` 未量到** ⇒ ⇒ 合池会把「`pos_frac` 本身有没有效应」藏起来",
    "**剂量趋势未量到**（合池无剂量轴）",
    "**旧批与本批的样本可比性未量到**",
    "**「照 meta 重建能否逐位复现」仍未量到**（重训命令已定位，账本 244.79 段【10】）",
]

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


def dla():
    """⚖ 复用 `dose_layer_audit` 的模块加载器（⛔ 不另写一份机械）。"""
    return _load(os.path.join(HERE, "dose_layer_audit.py"), "dla_24480")


def dconf():
    return dla().dconf()


def armv():
    return dla().armv()


def iaud():
    return dla().iaud()


def vsrc():
    return dla().vsrc()


def fda():
    """⚖ `fixed_dose_audit`（`mc_band_p` / `fmt_p` 的**唯一实现**）。"""
    return _load(os.path.join(HERE, "fixed_dose_audit.py"), "fda_24480")


def reader():
    """⚖⚖⚖ **权威读数器**（⛔ **逐位校验 md5** ⇒ 换了一份字节就不认）。

    ⚠ 候选路径覆盖两种目录布局：本机 `.cache/mutbak/r227_kcurve.py`、
      服务器 `.cache/r244/_k23_reader_r227_kcurve.py`（⛔ **不靠路径认它**，
      靠**字节**认它 ⇒ ⇒ 换路径不换口径）。
    """
    for p in READER_CANDIDATES:
        if os.path.isfile(p) and _md5(p) == READER_MD5:
            return _load(p, "r227_24480")
    raise HardFail("找不到 md5 == %s 的权威读数器（候选：%s）"
                   % (READER_MD5, READER_CANDIDATES))


def splitter():
    return _load(SPLITTER, "split_24480")


class HardFail(Exception):
    pass


def _read(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _md5(path):
    return hashlib.md5(io.open(path, "rb").read()).hexdigest()


# ---------------------------------------------------------------- 口径


def read_prereg_block(path):
    """⚖ 读预登记里的**机器可读块**（```prereg 围栏内）⇒ {键: 字符串}。"""
    txt = _read(path)
    m = re.search(r"```prereg\n(.*?)\n```", txt, re.S)
    if not m:
        raise HardFail("预登记 %s 里没有 ```prereg 机器可读块" % path)
    out = {}
    for ln in m.group(1).split("\n"):
        if "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def check_prereg(path, expect, label):
    """⚖⚖⚖ **V-P1**：键集**恰好**相等、取值**逐字**相等（⛔ 多一个键也红）。"""
    got = read_prereg_block(path)
    miss = sorted(set(expect) - set(got))
    extra = sorted(set(got) - set(expect))
    if miss or extra:
        raise HardFail("%s 键集不符：缺 %s ｜ 多 %s" % (label, miss, extra))
    for k, v in expect.items():
        if got[k] != v:
            raise HardFail("%s 键 %r 取值不符：%r ≠ 期望 %r" % (label, k, got[k], v))
    return got


def load_spec():
    """⚖ ρ\\* / tol / scope / pos_frac 三档：**只从规格 JSON 读**（⛔ 不写死）。"""
    d = json.loads(_read(SPEC_DISPATCH))
    r = json.loads(_read(SPEC_ROUTE))
    dose = d["dose"]
    return {
        "rho": float(dose["frac"]),
        "tol": float(dose["tol"]),
        "scope": dose["scope"],
        "pos_fracs": [float(x) for x in r["pos_fracs"]],
        "arms": list(r["arms"]),
        "n_tracks": int(r["target_tracks_per_arm"]),
        "n_blocks": int(r["n_blocks"]),
        "cells_per_track": int(r["cells_per_track"]),
        "md5_dispatch": _md5(SPEC_DISPATCH),
        "md5_route": _md5(SPEC_ROUTE),
    }


# ---------------------------------------------------------------- 格集合


def build_records(cells):
    """⚖ 读数器的 cell ⇒ 记录。⚠ **读数整块缺** ⇔ 「未量到」标记（⛔ 不当 0）。"""
    out = []
    for c in cells:
        r = c.get("reading")
        if r is None:
            out.append({"tid": c.get("tid"), "measured": False, "idx": c.get("idx"),
                        "scope": c.get("scope"), "pos_frac": None,
                        "inject_n_sites": None})
            continue
        rec = dict(r)
        rec["tid"] = c.get("tid")
        rec["measured"] = True
        rec["idx"] = c.get("idx")
        rec["scope"] = r.get("inject_scope") or c.get("scope")
        rec["inject_n_sites"] = r.get("inject_n_sites")
        rec["pos_frac"] = r.get("pos_frac")
        out.append(rec)
    return out


def cell_set(recs, spec, mode, drop=()):
    """⚖⚖⚖ **V3 / V-P2**：格集合。

    `mode`：
      · `fixed_dose` ⇒ V3 的**四条**（`scope==k` ∧ 读数在 ∧ `n_sites` 为真 ∧ 密度相等）
      · `scope_k`    ⇒ 前三条（**旧批交叉对照**用；旧批是剂量扫描，密度本就不等）
      · `panel_all`  ⇒ 只要读数在（**旧批面板口径**用）

    ⚖ `drop` = **逐条摘掉某个条件**（只给判据 V-P2 用：验证每条条件**都 load-bearing**，
      ⛔ 一条「摘掉也不改结果」的条件就是**恒绿护栏** ⇒ 必须红）。
    """
    kept, dropped = [], []
    for rec in recs:
        if "reading" not in drop and not rec.get("measured"):
            dropped.append((rec, "未量到（读数缺失 ⇒ 剔出格集合）"))
            continue
        if mode in ("fixed_dose", "scope_k"):
            if "scope" not in drop and rec.get("scope") != spec["scope"]:
                dropped.append((rec, "scope≠%s" % spec["scope"]))
                continue
            if "nsites" not in drop and not rec.get("inject_n_sites"):
                dropped.append((rec, "inject_n_sites 为假"))
                continue
        if mode == "fixed_dose" and "density" not in drop:
            try:
                inj = dconf().denom_of(rec)
            except Exception as e:                      # 密度算不出 ⇒ 未量到
                dropped.append((rec, "密度算不出（%s）" % e))
                continue
            fr = float(rec["inject_n_sites"]) / float(inj)
            if abs(fr - spec["rho"]) > spec["tol"]:
                dropped.append((rec, "密度 %.6f ∉ ρ*±%.4f" % (fr, spec["tol"])))
                continue
            rec["_frac"] = fr
            rec["_inj"] = inj
        kept.append(rec)
    return kept, dropped


# ---------------------------------------------------------------- 合池


def pool(cells_by_tid, sign):
    """⚖⚖⚖ **V2 / V1 / V8**：逐轨迹合池。

    `sign` = `d`（主口径，`d = p9_hi_meas − p9_lo_meas`）或 `up_mono`（辅口径）。

    ⚖ **主口径**：多数 = `nT·2 > m`（**平票算 False**、**零格进分母**）
    ⚖ **辅口径（V8）**：多数 = `pos > neg`（**零格剔出分母**）
    """
    out = {}
    for tid, cs in cells_by_tid.items():
        pos = neg = zero = 0
        vals = []
        for c in cs:
            if sign == "d":
                d = dconf().d_of(c)              # ⛔ 缺 p9_* ⇒ HardFail（V-P3）
                vals.append(d)
                if d > 0:
                    pos += 1
                elif d < 0:
                    neg += 1
                else:
                    zero += 1
            else:
                v = c.get("up_mono_meas")
                if v is None:
                    continue                      # 次口径未量到 ⇒ 剔出该格
                vals.append(1.0 if v else -1.0)
                if v:
                    pos += 1
                else:
                    neg += 1
        m = len(vals)
        out[tid] = {
            "pos": pos, "neg": neg, "zero": zero, "m": m, "nz": m - zero,
            "verdict": (pos * 2 > m),             # V2：平票 False、零格进分母
            "verdict_alt": (pos > neg),          # V8：零格剔出分母
            "vals": vals,
            "n_pf": len(set(c.get("pos_frac") for c in cs)),
            "pfs": sorted(set(c.get("pos_frac") for c in cs)),
        }
    return out


def group_by_tid(recs):
    g = collections.OrderedDict()
    for r in recs:
        g.setdefault(r["tid"], []).append(r)
    return g


def null_base(pooled, sign):
    """⚖⚖⚖ **V4**：逐轨迹 `majority_base_p2(nz, n_zero)` 再**等权平均**。"""
    per = []
    for tid, v in pooled.items():
        zero = v["zero"] if sign == "d" else 0
        nz = v["m"] - zero
        per.append((tid, dla().majority_base_p2(nz, zero)))
    mean = sum(p for _t, p in per) / float(len(per)) if per else float("nan")
    return per, mean


def disagreement(pooled):
    """⚖⚖ **V6**：三复制格的**一致性**（全一致 / 2:1 分歧）⇒ 分歧率。"""
    all_same = split = 0
    for tid, v in pooled.items():
        signs = [1 if x > 0 else (-1 if x < 0 else 0) for x in v["vals"]]
        if len(signs) < 2:
            continue
        nz = [s for s in signs if s != 0]
        if len(nz) < 2:
            continue
        if all(s == nz[0] for s in nz):
            all_same += 1
        else:
            split += 1
    n = all_same + split
    return {"all_same": all_same, "split_2to1": split, "n": n,
            "rate": (split / float(n)) if n else float("nan")}


# ---------------------------------------------------------------- 统计


def wilson(x, n):
    return iaud().wilson_bounds(x, n)


def newcombe(x1, n1, x2, n2):
    return iaud().newcombe_diff(x1, n1, x2, n2)


def fisher(a, b, c, d):
    p, _obs = armv().fisher_exact_two_sided(a, b, c, d)
    return p


def sign_test_p(signs):
    """⚖ 逐轨迹符号检验（reader 的 `sign_test`，⛔ 不另写）。"""
    return reader().sign_test([float(s) for s in signs])[0]


def paired_perm(diffs):
    """⚖⚖⚖ **配对置换**（唯一实现 = `dose_layer_audit.paired_perm_geom`）⇒
    返回 `(p, obs, ge, n_perm)` ⇒ **MC 不确定带**要 `ge/n_perm`（V12）。"""
    if not diffs:
        return 1.0, 0, 0, 0
    return dla().paired_perm_geom(diffs)


def mc_band(ge, n_perm):
    """⚖ **MC95% 不确定带**（唯一实现 = `fixed_dose_audit.mc_band_p`）⇒
    p 贴近 α 时**必须**报它（V12 / K11）。"""
    if not n_perm:
        return None, None
    return fda().mc_band_p(ge, n_perm)


def block_table(pooled, signs):
    """⚖⚖ **V9**：块 = `think` + `no_think` 两条轨迹；**块内两条都正才算正**。"""
    per = collections.OrderedDict()
    for tid, s in signs.items():
        per.setdefault(vsrc().problem_key(tid), {})[tid] = s
    out = []
    for q, d in per.items():
        out.append((q, len(d), all(v > 0 for v in d.values()),
                    all(v > 0 for v in d.values()) if len(d) == 2 else None))
    return out


def arm_counts(pooled, key="verdict"):
    pos = sum(1 for v in pooled.values() if v[key])
    return pos, len(pooled)


def diff_pp(x1, n1, x2, n2):
    if not n1 or not n2:
        return float("nan")
    return 100.0 * (x1 / float(n1) - x2 / float(n2))


def fmt_p(p):
    """⚖⚖ **V12**：p **印 6 位小数**（244.65：四位小数会把 0.049990 印成 0.0500）。"""
    if p is None:
        return "未量到"
    return "%.6f" % p


def fmt_ci(lo, hi, scale=100.0):
    if lo is None or hi is None or (isinstance(lo, float) and math.isnan(lo)):
        return "未量到"
    return "[%+.2f, %+.2f] pp" % (lo * scale, hi * scale)


def fmt_dist(counter):
    """⚖ 分布打印：`{2×1, 3×55}`。

    ⚖⚠ **键可能是 int 也可能是 tuple** ⇒ ⇒ 排序必须用 `str` 当键
    （⛔ 直接 `sorted(counter)` 会在两种键混在一起时**抛 TypeError**）。
    ⚖⚠⚖ **tuple 键一律写成 `(2,0)`（⛔ 逗号后**不加空格**）** ⇒ ⇒
    于是**分隔符 `, ` 不会出现在键内部** ⇒ ⇒ 外部脚本可以**无歧义**地切分
    （⛔ 若写成 `(2, 0)`，外部按 `, ` 切分会把一个键切成两半 ⇒ ⇒ 静默错）。
    """
    if not counter:
        return "{}"
    parts = []
    for k in sorted(counter, key=lambda z: str(z)):
        if isinstance(k, tuple):
            ks = "(" + ",".join(str(x) for x in k) + ")"
        else:
            ks = str(k)
        parts.append("%s×%d" % (ks, counter[k]))
    return "{" + ", ".join(parts) + "}"


# ---------------------------------------------------------------- 判决


def analyze(arms, spec, source_md5):
    """⚖⚖⚖ **判决只算一次**（V-P16）：返回的 dict 与印出来的面板**逐字一致**。

    `arms` = {"w": recs, "rand": recs}（记录列表）
    """
    res = {"source_md5": source_md5, "spec": spec, "arms": {}}
    for arm, recs in arms.items():
        kept, dropped = cell_set(recs, spec, "fixed_dose")
        by_tid = group_by_tid(kept)
        pooled = pool(by_tid, "d")
        pooled_up = pool(by_tid, "up_mono")
        base_per, base_mean = null_base(pooled, "d")
        pos, n = arm_counts(pooled)
        pos_alt, _n_alt = arm_counts(pooled, "verdict_alt")
        pos_up, n_up = arm_counts(pooled_up)
        ci = wilson(pos, n)
        disagree = disagreement(pooled)
        # ⚖ V1：两条正号源**逐条**比对
        agree = sum(1 for t in pooled
                    if pooled[t]["verdict"] == pooled_up.get(t, {}).get("verdict"))
        # ⚖ V7：分 `pos_frac` 三组
        groups = {}
        for pf in spec["pos_fracs"]:
            sub = [c for c in kept if c.get("pos_frac") is not None
                   and abs(float(c["pos_frac"]) - pf) < 1e-9]
            p2 = 0
            for c in sub:
                if dconf().d_of(c) > 0:
                    p2 += 1
            groups["%.2f" % pf] = {"pos": p2, "n": len(sub)}
        res["arms"][arm] = {
            "kept": len(kept), "dropped": len(dropped), "n_traj": n,
            "pos": pos, "pos_alt": pos_alt, "pos_up": pos_up, "n_up": n_up,
            "ci": ci, "base_mean": base_mean, "base_per": base_per,
            "disagree": disagree, "agree_with_secondary": agree,
            "groups": groups, "pooled": pooled, "pooled_up": pooled_up,
            "drop_reasons": collections.Counter(r for _rec, r in dropped),
            # ⚖⚖⚖ **244.81 补**：预登记 V3/V4 明写「**必须打印**每条轨迹的 `m` 分布」
            #   与「**必须打印** `(n_nz, n_zero)` 分布与基准分布」⇒ ⇒
            #   **原面板两样都没印** ⇒ ⇒ 「零格进分母」（B2）与「这一格没读数」
            #   （w 臂 1 条轨迹只有 2 个有效格）在判决面上**不可见** ⇒ ⇒ 补上。
            "m_dist": collections.Counter(v["m"] for v in pooled.values()),
            "nz_dist": collections.Counter((v["nz"], v["zero"]) for v in pooled.values()),
            "base_dist": collections.Counter(round(b, 6) for _t, b in base_per),
            "zero_cells": sum(v["zero"] for v in pooled.values()),
        }
    # ---- 跨臂（V10）
    w, r = res["arms"].get("w"), res["arms"].get("rand")
    cross = {}
    if w and r:
        tids = sorted(set(w["pooled"]) & set(r["pooled"]))
        signs_w = [1 if w["pooled"][t]["verdict"] else -1 for t in tids]
        signs_r = [1 if r["pooled"][t]["verdict"] else -1 for t in tids]
        diffs = [a - b for a, b in zip(signs_w, signs_r)]
        pp, pobs, ge, n_perm = paired_perm(diffs)
        blo, bhi = mc_band(ge, n_perm)
        cross = {
            "n_paired": len(tids),
            "fisher_p": fisher(w["pos"], w["n_traj"] - w["pos"],
                               r["pos"], r["n_traj"] - r["pos"]),
            "paired_perm_p": pp, "paired_perm_obs": pobs,
            "paired_perm_ge": ge, "paired_perm_n_perm": n_perm,
            "paired_perm_band": (blo, bhi),
            "diff_pp": diff_pp(w["pos"], w["n_traj"], r["pos"], r["n_traj"]),
            "diff_ci": newcombe(w["pos"], w["n_traj"], r["pos"], r["n_traj"]),
            "sign_w_p": sign_test_p(signs_w), "sign_r_p": sign_test_p(signs_r),
        }
        # ⚖ V9 块级
        bw = block_table(w["pooled"], {t: (1 if w["pooled"][t]["verdict"] else -1)
                                       for t in tids})
        br = block_table(r["pooled"], {t: (1 if r["pooled"][t]["verdict"] else -1)
                                       for t in tids})
        pb = sum(1 for _q, _n, pos, _two in bw if pos)
        pr = sum(1 for _q, _n, pos, _two in br if pos)
        cross["block"] = {
            "n_blocks": len(bw), "w_pos": pb, "rand_pos": pr,
            "w_ci": wilson(pb, len(bw)), "rand_ci": wilson(pr, len(br)),
            "diff_pp": diff_pp(pb, len(bw), pr, len(br)),
            "diff_ci": newcombe(pb, len(bw), pr, len(br)),
            "fisher_p": fisher(pb, len(bw) - pb, pr, len(br) - pr),
            "incomplete_blocks": sum(1 for _q, n2, _p, two in bw if two is False),
        }
        # ⚖ V7 三组各自的差 pp / p / 区间
        gp = {}
        for key in w["groups"]:
            gw, gr = w["groups"][key], r["groups"][key]
            gp[key] = {
                "w": gw, "rand": gr,
                "diff_pp": diff_pp(gw["pos"], gw["n"], gr["pos"], gr["n"]),
                "diff_ci": newcombe(gw["pos"], gw["n"], gr["pos"], gr["n"]),
                "fisher_p": fisher(gw["pos"], gw["n"] - gw["pos"],
                                   gr["pos"], gr["n"] - gr["pos"]),
            }
        cross["groups"] = gp
    res["cross"] = cross
    return res


def render(res):
    """⚖ 判决面板（印出来的每一行都能在返回的 dict 里找到对应值 ⇒ V-P16）。"""
    L = []
    spec = res["spec"]
    A = L.append
    A("=" * 78)
    if res.get("partial"):
        A("⚠⚠⚠⚠⚠ **部分读数** —— 状态文件**没有** `ALLDONE`，**或**格数没齐 ⇒ ⇒ 这一轮**还在跑**")
        sh = res.get("short") or {}
        for arm, (got, exp) in sorted(sh.items()):
            A("⚠⚠⚠⚠⚠ · 臂 `%s`：读到 **%d** 格，应有 **%d** 格" % (arm, got, exp))
        A("⚠⚠⚠⚠⚠ ⇒ ⇒ **本面板的数不是判决** ⇒ ⇒ 固定剂量下的判决数**未量到**"
          "（⛔ 不许把这里的数抄成结论）")
        A("=" * 78)
    A("固定剂量「合池判决层」判决面板（口径：预登记 %s 的 V1–V12）" % "R6_FIXED_DOSE_POOLED_VERDICT_PREREG")
    A("=" * 78)
    A("【口径来源】ρ* = %.3f ｜ tol = %.4f ｜ scope = %s ｜ pos_frac 三档 = %s"
      % (spec["rho"], spec["tol"], spec["scope"],
         " / ".join("%.2f" % x for x in spec["pos_fracs"])))
    A("【字节】预登记 md5 = %s ｜ 变体预登记 md5 = %s ｜ 规格 md5 = %s / %s"
      % (res["source_md5"]["prereg"], res["source_md5"]["variant"],
         spec["md5_dispatch"], spec["md5_route"]))
    A("【读数器】md5 = %s（⛔ 一个字都不改）" % res["source_md5"]["reader"])
    A("")
    A("-------------------- 轨迹级（合池：3 个 `pos_frac` 逐轨迹严格多数）--------------------")
    for arm in ("w", "rand"):
        a = res["arms"].get(arm)
        if not a:
            A("  %-4s ⇒ 未量到" % arm)
            continue
        A("  %-4s 改判 **%d/%d** ｜ 区间 %s ｜ 零假设基准（逐轨迹平均）%.4f"
          % (arm, a["pos"], a["n_traj"], fmt_ci(a["ci"][0], a["ci"][1]),
             a["base_mean"]))
        A("       ├ 辅口径（`up_mono_meas`）改判 %d/%d ｜ 零格剔出分母那条 %d/%d"
          % (a["pos_up"], a["n_up"], a["pos_alt"], a["n_traj"]))
        # ⚖⚖⚖ 244.81 补印：预登记 V3/V4 要求印 `m` 分布与 `(n_nz,n_zero)` 分布 + 基准分布
        A("       ├ 格数结构（V3/V4 明写「必须打印」）：每轨迹有效格 m 分布 = %s ｜ "
          "(n_nz,n_zero) 分布 = %s ｜ 零格合计 %d"
          % (fmt_dist(a["m_dist"]), fmt_dist(a["nz_dist"]), a["zero_cells"]))
        A("       ├ 基准分布（V4）：%s" % fmt_dist(a["base_dist"]))
        A("       ├ 与主口径**逐条一致**的轨迹：%d/%d" % (a["agree_with_secondary"], a["n_traj"]))
        A("       ├ 异质性（前提，⛔ 不是判决）：三格全一致 %d ｜ 2:1 分歧 %d ｜ 分歧率 %s"
          % (a["disagree"]["all_same"], a["disagree"]["split_2to1"],
             ("%.4f" % a["disagree"]["rate"]) if a["disagree"]["n"] else "未量到"))
        A("       └ 格集合：进 %d 格 ｜ 剔出 %d 格" % (a["kept"], a["dropped"]))
    c = res.get("cross") or {}
    if c:
        band = c.get("paired_perm_band") or (None, None)
        A("  差 **%+.2f pp** ｜ 差区间 %s ｜ 跨臂 Fisher（精确枚举）p = %s ｜ 配对置换 p = %s"
          % (c["diff_pp"], fmt_ci(c["diff_ci"][0], c["diff_ci"][1]),
             fmt_p(c["fisher_p"]), fmt_p(c["paired_perm_p"])))
        A("  配对置换 **MC95%% 不确定带** = [%.6f, %.6f]（ge=%d / n_perm=%d ⇒ ⛔ p 贴近 α 时以这条为准）"
          % (band[0], band[1], c.get("paired_perm_ge"), c.get("paired_perm_n_perm")))
    A("")
    A("-------------------- 块级（块 = think + no_think；块内两条都正才算正）--------------------")
    b = (c.get("block") or {})
    if b:
        A("  w %d/%d ｜ rand %d/%d ｜ 差 %+.2f pp ｜ 差区间 %s ｜ Fisher p = %s"
          % (b["w_pos"], b["n_blocks"], b["rand_pos"], b["n_blocks"],
             b["diff_pp"], fmt_ci(b["diff_ci"][0], b["diff_ci"][1]), fmt_p(b["fisher_p"])))
    else:
        A("  未量到")
    A("")
    A("-------------------- 分 `pos_frac` 三组（V7：合池组为主，三组分列）--------------------")
    for key, g in (c.get("groups") or {}).items():
        A("  pos_frac=%-5s w %d/%d ｜ rand %d/%d ｜ 差 %+.2f pp ｜ 差区间 %s ｜ Fisher p = %s"
          % (key, g["w"]["pos"], g["w"]["n"], g["rand"]["pos"], g["rand"]["n"],
             g["diff_pp"], fmt_ci(g["diff_ci"][0], g["diff_ci"][1]), fmt_p(g["fisher_p"])))
    A("")
    A("-------------------- 问题级（V-P5 前提）--------------------")
    A("  **不适用**：问题级 Δ 需要 `scope = all` 的格，本批**没有** ⇒ ⇒ "
      "⛔ 不是「未量到」，⛔ 不是「无差异」")
    A("")
    A("-------------------- 前提清单（V-P14：逐条印出）--------------------")
    for tag, txt in PREMISES:
        A("  %s %s" % (tag, txt))
    A("")
    A("-------------------- 边界清单（V-P15）--------------------")
    for i, b2 in enumerate(BOUNDARIES, 1):
        A("  B%-2d %s" % (i, b2))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- 判据自检


def synth(n_tracks=6, pfs=(0.25, 0.5, 0.75), rho=0.25, mode="all_pos"):
    """⚖ **合成夹具**（G0-2 同族）：3 `pos_frac` × n 轨迹 × 2 臂。"""
    out = {"w": [], "rand": []}
    for ti in range(n_tracks):
        tid = "aime__aime25__p%02d__%s" % (ti, "think" if ti % 2 == 0 else "no_think")
        for pf in pfs:
            P, ng = 100, 1000
            t = max(1, int(ng * pf))
            inj = P + t - 1
            ns = int(round(rho * inj))
            for arm in ("w", "rand"):
                if mode == "all_pos":
                    lo, hi = 0.10, 0.20
                elif mode == "half":
                    lo, hi = (0.10, 0.20) if ti % 2 == 0 else (0.20, 0.10)
                else:  # zeros
                    lo = hi = 0.15
                rec = {"tid": tid, "measured": True, "idx": len(out[arm]) + 1,
                       "scope": "k", "inject_n_sites": ns, "pos_frac": pf,
                       "P": P, "n_gen": ng,
                       "p9_lo_meas": lo, "p9_hi_meas": hi,
                       "up_mono_meas": hi >= lo}
                out[arm].append(rec)
    return out


def _readings_of(recs):
    return [r for r in recs if r.get("measured")]


def check_all(ctx):
    """⚖⚖⚖ **V-P1…V-P18**：每条返回 `(ok, detail)`（⛔ 期望集不许从被检对象派生）。"""
    res = {}

    def add(cid, ok, detail):
        res[cid] = {"ok": bool(ok), "detail": detail}

    spec = ctx["spec"]
    # --- V-P1 口径只从预登记读
    try:
        check_prereg(ctx["prereg"], EXPECT_POOLED, "合池预登记")
        check_prereg(ctx["variant"], EXPECT_VARIANT, "变体预登记")
        add("V-P1", True, "13 键 + 17 键逐字相符")
    except Exception as e:
        add("V-P1", False, str(e))
        return res

    # --- V-P2 格集合四条：每条**要么** load-bearing，**要么**被别的条件蕴含
    #     （⚖ 「被蕴含」≠ 恒绿护栏：它在**另一个口径**下仍是活的 ⇒ 两个口径合起来验）
    good = synth(n_tracks=2)["w"]
    # ⚖ 夹具：**每条条件各造一个违规格**（不造 ⇒ 那条条件就没人验）
    viol = []
    v_scope = dict(good[0]); v_scope["scope"] = "all"; viol.append(v_scope)
    v_read = dict(good[0]); v_read["measured"] = False; viol.append(v_read)
    v_ns = dict(good[0]); v_ns["inject_n_sites"] = 0; viol.append(v_ns)
    v_den = dict(good[0]); v_den["inject_n_sites"] = 7; viol.append(v_den)
    fx = good + viol

    def _only_excluded(cond, mode):
        """⚖ 只被 `cond` 挡掉的格（别的条件都放行）⇒ 有 ⇒ 这条条件 load-bearing。"""
        hit = []
        for rec in fx:
            k_all, _ = cell_set([rec], spec, mode, drop=())
            k_wo, _ = cell_set([rec], spec, mode, drop=(cond,))
            if not k_all and k_wo:
                hit.append(rec)
        return hit

    dead, implied = [], []
    for cond in ("scope", "reading", "nsites", "density"):
        live = [m for m in ("fixed_dose", "scope_k")
                if _only_excluded(cond, m)]
        if not live:
            dead.append(cond)
        elif "fixed_dose" not in live:
            implied.append(cond)
    add("V-P2", not dead,
        "四条条件在两个口径合起来都 load-bearing%s"
        % ("" if not implied else
           "；⚠ 在**固定剂量口径**下 %s 被别的条件**蕴含**（⇒ 该口径下冗余，⛔ 但口径真源是预登记，"
           "⇒ **只记账不改口径**）" % "、".join(implied))
        if not dead else "恒绿护栏：%s 在任何口径下都不 load-bearing" % dead)

    # --- V-P3 缺读数 ⇒ HardFail（⛔ 不当 0）
    # ⚖⚖⚖ **判据要测「本工具的代码路径」** ⇒ ⇒ 不能只测依赖的 `d_of`
    #   （⛔ 只测依赖 ⇒ 绕过 `d_of` 的变异**抓不到** ⇒ 那就是恒绿护栏）
    bad_cell = {"tid": "x", "measured": True, "scope": "k", "inject_n_sites": 1,
                "pos_frac": 0.5, "P": 100, "n_gen": 1000,
                "p9_hi_meas": 0.2}                  # ⛔ 缺 p9_lo_meas
    try:
        pool({"x": [bad_cell]}, "d")
        add("V-P3", False, "缺 p9_lo_meas 的格**竟然没抛** ⇒ 不当 0 这条守不住")
    except Exception:
        add("V-P3", True, "缺 p9_lo_meas ⇒ `pool()` HardFail（⛔ 不当 0）")

    # --- V-P4 多数 = nT·2 > m（平票 False、零格进分母）
    # ⚖ 零格 = `p9_hi_meas == p9_lo_meas`（⛔ 不是「hi 比 lo 小」）
    p4 = pool({"t": [_mk(0.1, 0.2), _mk(0.1, 0.1)]}, "d")["t"]      # 1 正 1 零 ⇒ False
    p4b = pool({"t": [_mk(0.1, 0.2), _mk(0.2, 0.3), _mk(0.1, 0.1)]}, "d")["t"]
    p4c = pool({"t": [_mk(0.1, 0.2), _mk(0.2, 0.1)]}, "d")["t"]  # 1 正 1 负 ⇒ 平票 False
    p4d = pool({"t": [_mk(0.1, 0.2), _mk(0.1, 0.1)]}, "d")["t"]
    sub4 = [
        ("1正1零⇒False", p4["verdict"] is False),
        ("1正1零 m=2", p4["m"] == 2),
        ("1正1零 zero=1", p4["zero"] == 1),
        ("2正1零⇒True", p4b["verdict"] is True),
        ("2正1零 zero=1", p4b["zero"] == 1),
        ("2正1零 pos=2", p4b["pos"] == 2),
        ("1正1负⇒False", p4c["verdict"] is False),
        ("1正1负 zero=0", p4c["zero"] == 0),
        ("V8 零格剔分母⇒True", p4d["verdict_alt"] is True),
    ]
    bad4 = [n for n, o in sub4 if not o]
    add("V-P4", not bad4,
        "平票 False、零格进分母；V8 零格剔出分母时同夹具判正（两条不等）"
        + ("" if not bad4 else " ⇒ ⇒ 红：%s" % bad4))

    # --- V-P5 多数 ≡ 中位数符号（3 值夹具，8 种符号组合）
    ok5 = True
    for signs in itertools_product3():
        vals = [1.0 * s for s in signs]
        maj = pool({"t": [_mkd(v) for v in vals]}, "d")["t"]["verdict"]
        med = (sorted(vals)[1] > 0)
        ok5 &= (maj == med)
    add("V-P5", ok5, "3 值夹具上多数 ≡ 中位数符号")

    # --- V-P6 基准逐轨迹算再平均（⛔ 非硬写 0.5）
    pooled_mix = pool({"a": [_mk(0.1, 0.2)] * 3,
                       "b": [_mk(0.1, 0.2), _mk(0.0, 0.0), _mk(-0.2, -0.1)]}, "d")
    _per, mean = null_base(pooled_mix, "d")
    ok6 = abs(mean - 0.375) < 1e-9
    add("V-P6", ok6, "基准均值 = %.6f（期望 0.375 ⇒ 逐轨迹算）" % mean)

    # --- V-P7 检验用模拟规则（零格不抽币、阈值含零格）
    rate = dla().sim_null_positive_rate(2, 1, n_mc=4000)
    ok7 = abs(rate - 0.25) < 0.03
    add("V-P7", ok7, "sim_null(2,1) = %.4f（期望 ≈0.25 ⇒ 旧写法会给 0.5）" % rate)

    # --- V-P8/V-P9/V-P10/V-P13：面板**必须真的印出**（⛔ 只查返回 dict 不够 ⇒ 印漏了测不到）
    fx2 = synth(n_tracks=4, mode="half")
    an = analyze(fx2, spec, ctx["source_md5"])
    a_w = an["arms"]["w"]
    txt2 = render(an)
    ok8 = ("pos" in a_w and "pos_alt" in a_w and "pos_up" in a_w) and \
        ("零格剔出分母那条" in txt2) and ("up_mono_meas" in txt2)
    add("V-P8", ok8, "两条多数规则 + 辅口径**都在面板上印出**")
    ok9 = ("disagree" in a_w and "rate" in a_w["disagree"]) and \
        ("三格全一致" in txt2) and ("2:1 分歧" in txt2)
    add("V-P9", ok9, "异质性（分歧计数 + 分歧率）**印在面板上**（标记唯一 ⇒ 删行必红）")
    ok10 = (len(an["cross"].get("groups") or {}) == len(spec["pos_fracs"])) and \
        all(re.search(r"pos_frac=%-5s" % k, txt2) for k in an["cross"]["groups"])
    add("V-P10", ok10, "三组 pos_frac **都印在面板上**")
    # --- V-P19（244.81 补）格数结构必须印在面板上（预登记 V3/V4 明写「必须打印」）
    #   ⚖⚖ **为什么补这条**：244.81 第一版面板**没印** `m` 分布与 `(n_nz,n_zero)` 分布
    #   ⇒ ⇒ 「零格进分母」（B2）与「某条轨迹少一个有效格」在判决面上**看不见**
    #   ⇒ ⇒ 读者无法从面板判断分母到底怎么来的 ⇒ ⇒ 这条判据钉住它。
    ok19 = ("m_dist" in a_w and "nz_dist" in a_w and "base_dist" in a_w
            and "每轨迹有效格 m 分布" in txt2 and "(n_nz,n_zero) 分布" in txt2
            and "基准分布" in txt2 and "零格合计" in txt2)
    add("V-P19", ok19,
        "m 分布 / (n_nz,n_zero) 分布 / 基准分布 / 零格合计 **都印在面板上**"
        "（预登记 V3/V4 要求）")
    blk = an["cross"].get("block") or {}
    # ⚖ 块数**独立**数一遍（⛔ 不从被检对象取）
    exp_blocks = len(set(vsrc().problem_key(t) for t in a_w["pooled"]))
    ok13 = ("n_blocks" in blk and blk.get("n_blocks") == exp_blocks and exp_blocks > 0)
    add("V-P13", ok13, "块级分母 = 块数（独立数出 %d，报告 %s）"
        % (exp_blocks, blk.get("n_blocks")))

    # --- V-P11 区间：Wilson + Newcombe（⛔ 不许两 CI 相减）
    ok11a = True
    for x, n in ((3, 10), (0, 14), (14, 14), (6, 14), (1, 56)):
        tl, tu = wilson(x, n)
        il, iu = _wilson_indep(x, n)
        ok11a &= abs(tl - il) < 1e-12 and abs(tu - iu) < 1e-12
    nl, nu = newcombe(3, 10, 1, 10)
    naive = iaud().naive_diff(3, 10, 1, 10)
    ok11b = abs((nl - naive[0])) > 1e-6
    add("V-P11", ok11a and ok11b,
        "Wilson 与**独立实现**逐位相同（5 组）；Newcombe ≠ 两 CI 相减（%.6f vs %.6f）"
        % (nl, naive[0]))

    # --- V-P12 Fisher 精确枚举（与独立穷举对账）
    ok12 = abs(fisher(3, 7, 1, 9) - _fisher_bruteforce(3, 7, 1, 9)) < 1e-12
    add("V-P12", ok12, "Fisher 与独立穷举逐位相同")

    # --- V-P14 前提清单逐条印出（⚖ 期望的**编号**是独立字面量 ⇒ 少印/多印都红）
    EXPECT_PREMISE_TAGS = ["【P%d】" % i for i in range(1, 6)]
    txt = render(an)
    miss_p = [t for t in EXPECT_PREMISE_TAGS if t not in txt]
    add("V-P14", not miss_p, "前提 %d 条全在面板上（期望编号独立字面量）" % len(EXPECT_PREMISE_TAGS)
        if not miss_p else "少印 %s" % miss_p)

    # --- V-P15 边界清单**双向**对上（⚖ 期望的**编号**是独立字面量 ⇒ 少印/多印都红）
    EXPECT_BOUNDARY_IDS = ["B%d" % i for i in range(1, 12)]
    got_ids = set(re.findall(r"(?<![A-Za-z0-9])(B\d{1,2})(?![0-9])", txt))
    miss_b = [b for b in EXPECT_BOUNDARY_IDS if b not in got_ids]
    extra_b = sorted(got_ids - set(EXPECT_BOUNDARY_IDS))
    add("V-P15", not miss_b and not extra_b,
        "边界 %d 条双向对上（期望编号独立字面量）" % len(EXPECT_BOUNDARY_IDS)
        if (not miss_b and not extra_b) else "少印 %s ｜ 多印 %s" % (miss_b, extra_b))

    # --- V-P16 判决只算一次（印出来的 == 返回的）
    ok16 = True
    for arm in ("w", "rand"):
        a = an["arms"][arm]
        pat = re.compile(r"^  %-4s 改判 \*\*(\d+)/(\d+)\*\*" % arm, re.M)
        m = pat.search(txt)
        ok16 &= bool(m) and int(m.group(1)) == a["pos"] and int(m.group(2)) == a["n_traj"]
    add("V-P16", ok16, "面板上印的改判数 == 返回的数")

    # --- V-P17 未量到不许渲染成 FAIL
    ok17 = ("未量到" in txt) and ("FAIL" not in txt)
    add("V-P17", ok17, "未量到渲染成「未量到」而不是 FAIL")

    # --- V-P18 旧批交叉对照
    old = ctx.get("old")
    if not old:
        add("V-P18", False,
            "旧批日志**不在**（`R244_BPATH` 下找不到 r244_warm_{w,rand}.log）⇒ ⇒ "
            "**未量到**（⛔ 恒绿护栏：不许因为「跑不了」就当通过）")
    else:
        try:
            ok18, d18 = _old_cross_check(old, spec)
            add("V-P18", ok18, d18)
        except Exception as e:
            add("V-P18", False, "旧批交叉对照跑不起来：%s" % e)
    return res


def _wilson_indep(x, n, z=1.959963984540054):
    """⚖ **独立实现**的 Wilson 分数区间（⛔ 判据要不自指 ⇒ 这里**故意不调**生产函数）。"""
    if n <= 0:
        return (0.0, 1.0)
    ph = x / float(n)
    z2 = z * z
    den = 1.0 + z2 / n
    c = (ph + z2 / (2.0 * n)) / den
    h = (z / den) * math.sqrt(ph * (1.0 - ph) / n + z2 / (4.0 * n * n))
    return (max(0.0, c - h), min(1.0, c + h))


def _mk(lo, hi):
    return {"tid": "t", "measured": True, "scope": "k", "inject_n_sites": 1,
            "pos_frac": 0.5, "P": 100, "n_gen": 1000,
            "p9_lo_meas": lo, "p9_hi_meas": hi, "up_mono_meas": hi >= lo}


def _mkd(v):
    return _mk(0.0, v) if v != 0 else _mk(0.0, 0.0)


def itertools_product3():
    """⚖ 3 个符号的全部 3³ 组合（-1/0/+1）。"""
    out = []
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            for c in (-1, 0, 1):
                out.append((a, b, c))
    return out


def _fisher_bruteforce(a, b, c, d):
    """⚖ **独立穷举**实现（⛔ 不复用被检对象的算法 ⇒ 判据不自指）。"""
    from math import comb
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    if n == 0:
        return float("nan")
    lo, hi = max(0, c1 - r2), min(r1, c1)

    def prob(x):
        return (comb(r1, x) * comb(r2, c1 - x)) / float(comb(n, c1))
    p_obs = prob(a)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1)
                         if prob(x) <= p_obs * (1 + 1e-12)))


def _old_cross_check(old, spec):
    """⚖⚖⚖ **V-P18**：旧批交叉对照（全部格 12/14、6/14；scope=k 10/14）。

    ⚠ 旧批是**剂量扫描**（密度本就不等）⇒ ⇒ 这里用 `panel_all` / `scope_k`
       两个**历史口径**，⛔ **不**套固定剂量的密度条件。
    """
    out = {}
    for arm in ("w", "rand"):
        recs = old[arm]
        for mode, want in (("panel_all", old["expect_all"][arm]),
                           ("scope_k", old["expect_scope_k"].get(arm))):
            if want is None:
                continue
            kept, _ = cell_set(recs, spec, mode)
            pooled = pool(group_by_tid(kept), "d")
            pos, n = arm_counts(pooled)
            out[(arm, mode)] = (pos, n, want)
    bad = []
    for k, (pos, n, want) in out.items():
        if (pos, n) != want:
            bad.append("%s %s 实测 %d/%d ≠ 登记 %s" % (k[0], k[1], pos, n, want))
    detail = "旧批交叉对照：%s" % (" ｜ ".join(
        "%s %s = %d/%d（登记 %s）" % (k[0], k[1], v[0], v[1], v[2])
        for k, v in sorted(out.items())))
    return (not bad), detail + ("" if not bad else " ⇒ ⇒ 红：%s" % bad)


# ---------------------------------------------------------------- 跑真实数据


def read_arm_records(log, status, expect_cells=None, allow_partial=False):
    """⚖ 用**权威读数器**读一份日志 ⇒ 记录列表（⛔ 不自己解析 BEGIN）。

    ⚖⚖⚖ **没有 `ALLDONE` ⇒ 这一轮可能还没跑完** ⇒ ⇒ 默认 **HardFail**（不出判决）；
       只有显式 `--allow-partial` 才放行 ⇒ ⇒ 且放行时面板**必须**打上
       「部分读数，不是判决」的横幅（⛔ 防止半批数据被当成判决数）。
    """
    rc = reader()
    with io.open(log, encoding="utf-8", errors="replace") as fh:
        log_text = fh.read()
    with io.open(status, encoding="utf-8", errors="replace") as fh:
        st_text = fh.read()
    blocks = rc.parse_blocks(log_text)
    rows, alldone = rc.parse_status(st_text)
    if alldone is None and not allow_partial:
        raise HardFail("%s 无 ALLDONE ⇒ 这一轮**可能还没跑完** ⇒ 不出判决" % status)
    cells = rc.join(blocks, rows)
    if expect_cells is not None and len(cells) != expect_cells:
        raise HardFail("%s 读出 %d 格 ≠ 期望 %d" % (log, len(cells), expect_cells))
    recs = build_records(cells)
    for r in recs:
        r["_partial"] = (alldone is None)
    return recs


def source_md5():
    return {"prereg": _md5(PREREG_POOLED), "variant": _md5(PREREG_VARIANT),
            "reader": _md5(os.path.join(HERE, "..", "mutbak", "r227_kcurve.py"))
            if os.path.isfile(os.path.join(HERE, "..", "mutbak", "r227_kcurve.py"))
            else READER_MD5,
            "splitter": _md5(SPLITTER)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--criteria", action="store_true",
                    help="只输出判据 JSON（给变异台用）")
    ap.add_argument("--arms", help="JSON：{\"w\":[{\"log\":..,\"status\":..},..],"
                                   "\"rand\":[..]}")
    ap.add_argument("--expect-cells", type=int, default=None)
    ap.add_argument("--allow-partial", action="store_true",
                    help="⛔ 只作**管线自检**用：允许没有 ALLDONE 的部分读数"
                         "⇒ ⇒ 面板会打上「不是判决」的横幅")
    ap.add_argument("--old-w-log"); ap.add_argument("--old-w-status")
    ap.add_argument("--old-r-log"); ap.add_argument("--old-r-status")
    ap.add_argument("--out")
    a = ap.parse_args()

    spec = load_spec()
    smd5 = source_md5()

    if a.criteria:
        ctx = _ctx(spec, smd5, a)
        res = check_all(ctx)
        print(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True))
        return 0 if all(v["ok"] for v in res.values()) else 1

    if a.selftest:
        ctx = _ctx(spec, smd5, a)
        res = check_all(ctx)
        bad = 0
        for cid in sorted(res, key=lambda s: int(re.search(r"V-P(\d+)", s).group(1))):
            v = res[cid]
            print("[%s] %-6s %s" % ("OK  " if v["ok"] else "FAIL", cid, v["detail"]))
            bad += 0 if v["ok"] else 1
        print("---- 判据 %d 条 ｜ PASS %d ｜ FAIL %d"
              % (len(res), len(res) - bad, bad))
        return 0 if bad == 0 else 1

    if not a.arms:
        ap.error("需要 --arms（JSON）或 --selftest")
    arms_spec = json.loads(a.arms)
    recs = {}
    for arm, lst in arms_spec.items():
        rr = []
        for item in lst:
            rr.extend(read_arm_records(item["log"], item["status"], a.expect_cells,
                                       allow_partial=a.allow_partial))
        recs[arm] = rr
    an = analyze(recs, spec, smd5)
    # ⚖⚖⚖ **部分数据不许长得像判决**（⛔ 光看 `ALLDONE` 不够 ——
    #   拆分出来的 status **带着** `ALLDONE` ⇒ 半批数据也会「看起来跑完了」
    #   ⇒ ⇒ 判据用**格数**：每臂必须齐 `n_tracks × cells_per_track` 格）
    exp_cells = spec["n_tracks"] * spec["cells_per_track"]
    short = {arm: (len(rs), exp_cells) for arm, rs in recs.items() if len(rs) != exp_cells}
    partial = bool(short) or any(r.get("_partial") for rs in recs.values() for r in rs)
    an["partial"] = partial
    an["short"] = short
    txt = render(an)
    print(txt)
    if a.out:
        with io.open(a.out, "w", encoding="utf-8") as fh:
            fh.write(txt)
    return 0


def _ctx(spec, smd5, a):
    """⚖ 判据自检的上下文：口径 ＋ 旧批。

    ⚖⚖⚖ **旧批路径要有默认值**（`R244_BPATH` 环境变量，默认
    `/home/zhourui/steer3d_bpath`）⇒ ⇒ **回归 harness 只用 `--selftest` 调用时
    也能跑**（⛔ 否则 V-P18 会因为「拿不到旧批」而崩 ⇒ ⇒ 回归里那条工具直接红）。
    ⚠ 旧批日志**不在** ⇒ ⇒ V-P18 判**红**（⛔ 恒绿护栏 ⇒ 不许跳过装作通过）。
    """
    bp = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")
    ow = a.old_w_log or os.path.join(bp, "r244_warm_w.log")
    ows = a.old_w_status or os.path.join(bp, "r244_warm_w_status.txt")
    orl = a.old_r_log or os.path.join(bp, "r244_warm_rand.log")
    ors = a.old_r_status or os.path.join(bp, "r244_warm_rand_status.txt")
    old = None
    if all(os.path.isfile(p) for p in (ow, ows, orl, ors)):
        old = {
            "w": read_arm_records(ow, ows),
            "rand": read_arm_records(orl, ors),
            # ⚖ **独立字面量**（⛔ 期望集不许从被检对象派生）
            "expect_all": {"w": (12, 14), "rand": (6, 14)},
            "expect_scope_k": {"w": (10, 14), "rand": (5, 14)},
        }
    return {"spec": spec, "source_md5": smd5, "prereg": PREREG_POOLED,
            "variant": PREREG_VARIANT, "old": old}


if __name__ == "__main__":
    sys.exit(main())
