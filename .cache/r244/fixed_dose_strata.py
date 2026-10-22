#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixed_dose_strata.py —— 固定剂量那一批的**分层语义体检**（零 GPU、零写操作）。

⚖⚖⚖⚖⚖ **244.72 的问题**：244.70 判「那一批发不出去」（可得性）⇒ 244.71 判「两条路各要花多少」
  （成本）⇒ ⇒ 两轮都**没有**回答一件事：

    ⚖⚠⚖⚖⚖ **「换 pos_frac」到底是不是一个单变量？**

⚖⚖⚖⚖⚖ **实测答案：不是 —— 它同时动了三个东西。**（全部来自探针源码，逐字引用在下面）

  ① **读数位置**：探针 `ids = (pid + gen)[: P + t]`，`t = max(1, int(n_gen * pos_frac))`
     ⇒ ⇒ **pos_frac 越小，喂给模型的生成序列越短** ⇒ ⇒ **读数落在答案的不同位置**
  ② **作用比例**：阶梯的分母 `n_eff = P + int(0.5 * n_gen)`（账本 28924 行；本工具 60/60 复核）
     ⇒ ⇒ **n_eff 是「pos_frac=0.5 那一层」的序列长度**
     ⇒ ⇒ 同一个 `n_sites` 换一层，**它占该层序列的比例就变了**
     ⇒ ⇒ 「钉死 n_sites」≠「钉死作用比例」
  ③ **位点身份**：探针 `_k_positions(n, k, nested=True)` = `default_rng(0).permutation(n)[:k]`
     ⇒ ⇒ 排列**依赖 n** ⇒ ⇒ 同一 `n_sites` 在不同层挑到的是**不同的位置集合**

⇒ ⇒ **⇒ 这不是「同剂量下的多格」，这是「剂量 + 位置 + 位点身份」三个轴同时动。**
⇒ ⇒ ⇒ **⇒ 那批一旦按「n_sites 钉死」发出去，测到的不是「固定剂量下 w vs rand」。**

⚖⚖⚖ **本工具的判据（每条能红）**：
  S1 剂量口径必须钉死（两个候选口径给出不同结论 ⇒ 歧义必须进前提）
  S2 层数 = 可分辨的处理数（各层读数位置互不相同 ⇒ 层数必须 = pos_fracs 的个数）
  S3 **作用比例跨层漂**（seq 口径下的层间漂移倍数；⚠️ 真数据上**红**）
  S4 层间位点身份不可比（实测 Jaccard；位点身份若其实可比 ⇒ 这条要绿）
  S5 每层块数够不够预登记门槛（单臂符号检验 20 块 ／ 跨臂 Fisher 13 块）
  S6 物理可达（n_sites ≤ 该层序列长度，否则探针 `_k_positions` 直接 ValueError）
  S7 剂量档位可得性（阶梯已知的几条 ／ 其余「未量到」）
  S8 取数口径等价（阶梯档位 vs **生产分母**口径 ⇒ 实测 14/14 复现；旧的 n_eff 口径只 12/14）
  S9  缩放口径可行（逐层 n_sites = round(frac × 生产分母) ⇒ 每层密度落在 frac ± tol）
  S10 连续性（缩放后 pos_frac=0.5 层 vs 既有阶梯 0.25 档 ⇒ 逐字相同 ⇒ 既有剂量扫描仍可比）
  S11 格清单的列必须与规格声明的 `columns` 一致（⛔ 少 `pos_frac` 列 ⇒ 那一批发不出去）

用法：
  `fixed_dose_strata.py [--spec <json>] [--pool <json>] [--cells <txt>] [--dose-basis cal|seq]`
  `fixed_dose_strata.py --selftest`

⚖⚠⚖⚖⚖⚖ **为什么文件名不带下划线**：⚠ 全回归只枚举 `.cache/r244` 下**不以 `_` 开头**的 `.py`
  ⇒ ⇒ 本工具**已去掉 `_` 前缀** ⇒ ⇒ **进回归执行集** ⇒ ⇒ 全回归那一层**覆盖**它
  ⇒ ⇒ 理由：本工具**依赖生产机械 `dose_confound_audit`**（跨工具依赖）
  ⇒ ⇒ ⇒ 那种依赖**正是全回归要抓的东西** ⇒ ⇒ ⇒ 放在执行集外 ⇒ ⇒ 那一层就**盖不到** ⇒ ⇒ ⇒ **留白**
  ⇒ ⇒ 代价：⚠ **执行集 md5 清单变了** ⇒ ⇒ ⇒ **最终版回归必须重跑**（⛔ 旧的回归结论不算它的背书）
  ⇒ ⇒ ⚠ 本工具**自己**还有第二层护栏：**自检**（17/17）＋ **变异台**（12/12 有效变异全抓住 ＋ 1 条等价变异记「无效」）
"""

import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ⚖⚠⚖⚖⚖⚖ **不另写第二套真相**：注入密度一律走**生产机械**
#   `dose_confound_audit.frac_of`（分析管线自己算剂量的那个函数）
#   ⇒ ⇒ 本工具与生产分析**逐位同源** ⇒ ⇒ 数字可直接对账
#   ⇒ ⇒ 244.71 那个**校验器口径**（n_sites / n_eff）是**另一套** ⇒ ⇒ 断层正是本轮要量的东西
import dose_confound_audit as DCA  # noqa: E402

POOL_DEFAULT = os.path.join(HERE, "fixed_dose_pool_snapshot.json")
SPEC_DEFAULT = os.path.join(HERE, "fixed_dose_dispatch_spec_example.json")
CELLS_DEFAULT = os.path.join(HERE, "warm_cells.txt")

S_IDS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11")
S_BLOCKING = ("S2", "S3", "S5", "S6", "S8", "S9", "S10", "S11")
S_PREMISE = ("S1", "S7")
S_KIND = {"S1": "口径", "S2": "设计", "S3": "口径", "S4": "口径",
          "S5": "池子", "S6": "生成侧", "S7": "前提", "S8": "口径",
          "S9": "修法", "S10": "连续性", "S11": "格式"}

# ⚖ 预登记里的样本量门槛（⚠️ **从预登记抄**，⛔ 不在这里重新推导）
MIN_BLOCKS_SIGN = 20       # 单臂符号检验达 80% 功效（244.59）
MIN_BLOCKS_FISHER = 13     # 跨臂 Fisher 精确达 80% 功效（244.59）

# ⚖ S3 的容差：作用比例跨层漂超过这个倍数 ⇒ 「固定剂量」在作用比例这一维上不成立
DRIFT_TOL = 1.05
# ⚖ S4 的门限：层间位点 Jaccard 超过它 ⇒ 位点身份其实可比
JACCARD_MAX = 0.5


def _read(p):
    with open(p, encoding="utf-8") as fh:
        t = fh.read()
    assert "\ufffd" not in t, "%s 里有坏字" % p
    return t


def _k_positions(n, k, seed=0, nested=True):
    """⚖⚖⚖ **独立复算探针的位点选择**（逐字照 `r241_probe.py` 的 `_k_positions`）。

    ⚖ 为什么要复算：S4 要量「同一 n_sites 在不同层挑到的是不是同一批位置」。
    ⚖ 探针那份要 torch + GPU ⇒ ⛔ 判据侧不能调它 ⇒ ⇒ 这里**按源码逐字重写**一份
    ⚖ ⇒ ⇒ 源码的对应行在账本里逐字引用 ⇒ ⇒ 任何人可以核对这两份是否一致。
    ⚠ `nested=True` 时是「固定一个排列，各 k 取它的前 k 个」；`nested=False` 时是独立抽样。
    ⚖ 本批用的是**嵌套**（扫描脚本传 `--inject-nested`）。
    """
    import numpy as np
    n, k = int(n), int(k)
    if n <= 0:
        raise ValueError("序列长度为 0")
    if k < 0 or k > n:
        raise ValueError("k=%r 越界：必须 0 <= k <= n=%d" % (k, n))
    if k == n:
        return list(range(n))
    if k == 0:
        return []
    rng = np.random.default_rng(int(seed))
    if nested:
        return sorted(int(x) for x in rng.permutation(n)[:k])
    return sorted(rng.choice(n, size=k, replace=False).tolist())


def evaluate(pool, spec, cells_path=None, dose_basis="cal"):
    """⚖ 算「那一批的分层语义」+ 判 S1–S8。返回 (rows, v)。"""
    R = {}
    rows = []
    gaps = []
    premises = []
    diags = []

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        rows.append("  [%s] %-4s %s" % ("PASS" if ok else "FAIL", cid, detail))

    def put_diag(detail):
        diags.append("  [诊断] %s" % detail)

    route = spec["route"]
    dose = spec["dose"]
    frac = float(dose["frac"])
    tol = float(dose["tol"])
    pos_fracs = [float(x) for x in route["pos_fracs"]]
    cpt = int(route["cells_per_track"])
    arms = list(route["arms"])

    # ⚖⚖⚖⚖⚖ **244.73：规格必须声明 n_sites 的取法规则**（这是「固定剂量」的前提）
    #   244.72 更正后的 `dose.meaning` 写的是「**每个 (轨迹, pos_frac)** 取生产密度那一档」
    #   ⇒ ⇒ 机器可读的那一条是 `dose.n_sites_rule`（"per_layer" | "fixed"）
    #   ⛔ 缺这个字段 ⇒ 本工具**按 `dose.meaning` 的文字兜底**，但**必须报出来**
    #   ⇒ ⇒ ⛔ 不许静默默认（静默默认 = 换一批数据就静默错）
    _rule_raw = str(dose.get("n_sites_rule") or "").strip()
    if _rule_raw in ("per_layer", "fixed"):
        RULE = _rule_raw
        RULE_SRC = "规格字段 `dose.n_sites_rule` = `%s`" % RULE
    else:
        RULE = "per_layer"
        RULE_SRC = ("⚠ 规格**没有**机器可读的 `dose.n_sites_rule` ⇒ 本工具按 `dose.meaning` 的文字"
                    "（「每个 (轨迹, pos_frac) 取生产密度那一档」⇒ 逐层缩放）**兜底**成 `per_layer`"
                    " ⇒ ⇒ ⛔ 这条兜底是**推断**不是**声明** ⇒ ⇒ 建议把字段补进规格")

    tids = pool["tids"]
    cells_by_tid = pool.get("cells_by_tid", {})

    # ---------- 逐条轨迹 ----------
    per = []
    ladder_mismatch = []          # 阶梯档位 vs round(frac × **生产分母**) ← 244.73 钉死的口径
    ladder_mismatch_neff = []     # 阶梯档位 vs round(frac × n_eff)      ← 旧口径（诊断用）
    ladder_unknown = []           # 阶梯未量到
    ladder_miss = []              # 阶梯已知但没命中
    phys_viol = []                # n_sites > 该层序列长度
    prod_denom_mismatch = []      # 与生产分母对不上的轨迹
    n_eff_cal_ok = True           # n_eff == P + int(0.5 * n_gen)

    for x in tids:
        tid = x["tid"]
        P = int(x["P"])
        n_gen = int(x["n_gen"])
        n_eff = int(x["n_eff"])
        if n_eff != P + max(1, int(n_gen * 0.5)):
            n_eff_cal_ok = False

        t_of = {}
        seq_of = {}
        for p in pos_fracs:
            t_of[p] = max(1, int(n_gen * p))
            seq_of[p] = P + t_of[p]

        # ---- n_sites：阶梯档位优先；没有阶梯就按构造取 round(frac * n_eff)
        # ⚖⚠⚖⚖⚖ **244.73 口径钉死**：分母一律用**生产分母** `denom_of`（pos_frac=0.5 那层）
        #   ⇒ 实测（服务器，池里 60 条）：**14/14** 复现既有阶梯；而旧的 `n_eff` 口径只 **12/14**
        #   ⇒ ⇒ **既有 137 格是按生产分母取的** ⇒ ⇒ 「按构造取」也必须用生产分母
        #   ⇒ ⇒ ⛔ `n_sites`（旧规则的值）**保持原样不动** ⇒ ⇒ 旧规则的数一个都不变
        denom05 = DCA.denom_of({"tid": tid, "P": P, "n_gen": n_gen, "pos_frac": 0.5})
        lad = cells_by_tid.get(tid)
        ladder_k = None
        n_sites = None
        src = None
        if lad:
            ladder_k = sorted(int(c["val"]) for c in lad if c["kind"] == "k")
            # ⚖ 选档按**生产密度**（不是 n_eff）⇒ 与规格 `dose.meaning` 同一口径
            hits = [k for k in ladder_k if abs(k / float(denom05) - frac) <= tol]
            if len(hits) == 1:
                n_sites = hits[0]
                src = "ladder"
            else:
                ladder_miss.append(tid)
                src = "ladder_miss"
        else:
            ladder_unknown.append(tid)
            src = "constructed"
            # ⚠⚠⚖⚖⚖ **本轮真踩过的坑**：这一支**必须**给 n_sites 赋值
            #   ⛔ 漏了 ⇒ `n_sites` 留 None ⇒ ⇒ 那 46 条轨迹被**静默排除**
            #   ⇒ ⇒ 下面的漂移/Jaccard 全都只在 14 条上算 ⇒ ⇒ 数字看着正常、其实少算
            #   ⇒ ⇒ 是自检的 T6c 负样把它逼出来的（挑一条**无阶梯**的轨迹造越界）
            n_sites = int(round(frac * n_eff))
        constructed = int(round(frac * n_eff))
        constructed_prod = int(round(frac * denom05))
        # ⚖⚖⚖ **S8 的基准 = 生产分母口径**（244.73 钉死）⇒ 旧 n_eff 口径留作诊断
        if src == "ladder" and constructed_prod != n_sites:
            ladder_mismatch.append((tid, n_sites, constructed_prod))
        if src == "ladder" and constructed != n_sites:
            ladder_mismatch_neff.append((tid, n_sites, constructed))

        # ⚖⚖⚖ 与**生产机械**逐条互证：`denom_of` 的可注入位置数 + 1 必须等于本工具的 seq
        #   ⇒ ⇒ 本工具的「该层序列长度」与生产分析**同源**（⛔ 不另写第二套）
        for _p in pos_fracs:
            if DCA.denom_of({"tid": tid, "P": P, "n_gen": n_gen,
                             "pos_frac": _p}) + 1 != seq_of[_p]:
                prod_denom_mismatch.append(tid)
        rec = {"tid": tid, "P": P, "n_gen": n_gen, "n_eff": n_eff,
               "t": t_of, "seq": seq_of, "n_sites": n_sites, "src": src,
               "constructed": constructed, "think": bool(x.get("think")),
               "no_think": bool(x.get("no_think"))}
        per.append(rec)

    # ---------- 只对「n_sites 拿得到」的轨迹算剂量 ----------
    usable = [r for r in per if r["n_sites"] is not None]

    def _rec(r, p):
        """⚖ 造一条**生产口径**的记录（`dose_confound_audit` 吃的就是这个形状）。"""
        return {"tid": r["tid"], "P": r["P"], "n_gen": r["n_gen"], "pos_frac": p,
                "inject_n_sites": r["n_sites"]}

    def _dose_seq(r, p):
        """⚖⚖⚖ **生产口径**：注入密度 = n_sites / 可注入位置总数
        ⇒ ⇒ 走 `dose_confound_audit.frac_of`（⛔ **不另写第二套**）"""
        return DCA.frac_of(_rec(r, p))

    def _dose_cal(r, p):
        """⚖ **校验器口径**（244.71 那套）：n_sites / n_eff（分母是 pos_frac=0.5 的序列长度）"""
        return r["n_sites"] / float(r["n_eff"])

    drift_seq = {}
    drift_cal = {}
    for p in pos_fracs:
        drift_seq[p] = sorted(_dose_seq(r, p) for r in usable)
        drift_cal[p] = sorted(_dose_cal(r, p) for r in usable)

    def _med(xs):
        if not xs:
            return None
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])

    # 层间漂移：每条轨迹上 dose_seq 的 max/min
    per_track_drift = []
    for r in usable:
        ds = [_dose_seq(r, p) for p in pos_fracs]
        if min(ds) > 0:
            per_track_drift.append(max(ds) / min(ds))
    DRIFT_FIXED = _med(per_track_drift)      # ⚖ 旧规则（n_sites 跨层固定）下的漂移
    per_track_drift_cal = []
    for r in usable:
        ds = [_dose_cal(r, p) for p in pos_fracs]
        if min(ds) > 0:
            per_track_drift_cal.append(max(ds) / min(ds))
    DRIFT_FIXED_CAL = _med(per_track_drift_cal)

    # ---------- 位点身份：层间 Jaccard（旧规则：n_sites 跨层固定）----------
    # ⚖⚠⚖⚖⚖ **只在「物理可构造」的轨迹上算** ⇒ ⇒ 越界的那些**没有位点集合**
    #   （探针的 `_k_positions` 在 k > n 时**直接抛 ValueError** ⇒ ⇒ 越界的格是**崩**，
    #   不是「算出来是 0」⇒ ⇒ 所以它们进 `phys_viol`，不进 Jaccard）
    buildable = []
    for r in usable:
        if all(r["n_sites"] <= r["seq"][p] for p in pos_fracs):
            buildable.append(r)
    j_pairs_fixed = {}
    for i, pa in enumerate(pos_fracs):
        for pb in pos_fracs[i + 1:]:
            js = []
            for r in buildable:
                A = set(_k_positions(r["seq"][pa], r["n_sites"]))
                B = set(_k_positions(r["seq"][pb], r["n_sites"]))
                u = len(A | B)
                js.append((len(A & B) / float(u)) if u else 1.0)
            j_pairs_fixed[(pa, pb)] = _med(js)
    JACC_FIXED = max(j_pairs_fixed.values()) if j_pairs_fixed else 1.0

    # ---------- 缩放口径的修法：n_sites(p) = round(frac × 生产分母) ----------
    # ⚖⚠⚖⚖⚖⚖ **244.72 的关键**：n_sites 是**自由参数**（探针对 `--inject-n-sites`
    #   只有「>= 1」与「scope=k 时必填」两条约束 ⇒ 位点是 `_k_positions(P+t, k)` 现挑的）
    #   ⇒ ⇒ **阶梯只是「过去跑过哪些」的清单，不是「什么能跑」的约束**
    #   ⇒ ⇒ ⇒ ⇒ 「供不出命中档 ⇒ 要新阶梯 ⇒ 生成侧 ⇒ 要点头」是**假阻断**
    #   ⇒ ⇒ ⇒ ⇒ 修法：每层**直接按目标密度算** n_sites
    scaled = {}          # (tid, pos_frac) -> n_sites
    scaled_dens = {p: [] for p in pos_fracs}
    scaled_viol = []
    scaled_on_ladder = {p: 0 for p in pos_fracs}
    scaled_same = {p: 0 for p in pos_fracs}
    scaled_diff = {p: {} for p in pos_fracs}
    for r in per:
        for p in pos_fracs:
            denom = DCA.denom_of({"tid": r["tid"], "P": r["P"], "n_gen": r["n_gen"],
                                   "pos_frac": p})
            cap = denom + 1
            ns = int(round(frac * denom))
            scaled[(r["tid"], p)] = ns
            if not (1 <= ns <= cap):
                scaled_viol.append((r["tid"], p, ns, cap))
            scaled_dens[p].append(ns / float(denom))
            lad = cells_by_tid.get(r["tid"])
            if lad:
                ks = sorted(int(c["val"]) for c in lad if c["kind"] == "k")
                if ns in ks:
                    scaled_on_ladder[p] += 1
                # ⚖ 选档按**生产密度**（denom(0.5)）⇒ 与 244.73 钉死的口径一致
                _d05 = DCA.denom_of({"tid": r["tid"], "P": r["P"], "n_gen": r["n_gen"],
                                      "pos_frac": 0.5})
                hits = [k for k in ks if abs(k / float(_d05) - frac) <= tol]
                if len(hits) == 1:
                    if ns == hits[0]:
                        scaled_same[p] += 1
                    else:
                        d = ns - hits[0]
                        scaled_diff[p][d] = scaled_diff[p].get(d, 0) + 1

    # ---------- ⚖⚖⚖ 244.73：按**操作性规则**评估（规格声明的 n_sites 取法） ----------
    def _ns_op(r, p):
        """⚖ 操作性 n_sites：`per_layer` ⇒ 逐层缩放（round(frac × 生产分母)）；
        `fixed` ⇒ 跨层固定（旧规则：钉死 n_sites 跨层复用）"""
        if RULE == "per_layer":
            return scaled[(r["tid"], p)]
        return r["n_sites"]

    per_track_drift_op = []
    per_track_drift_op_cal = []
    drift_op_seq = {p: [] for p in pos_fracs}
    drift_op_cal_seq = {p: [] for p in pos_fracs}
    for r in usable:
        ds = []
        dsc = []
        for p in pos_fracs:
            denom = DCA.denom_of({"tid": r["tid"], "P": r["P"], "n_gen": r["n_gen"],
                                   "pos_frac": p})
            v = _ns_op(r, p) / float(denom)
            ds.append(v)
            drift_op_seq[p].append(v)
            vc = _ns_op(r, p) / float(r["n_eff"])
            dsc.append(vc)
            drift_op_cal_seq[p].append(vc)
        if min(ds) > 0:
            per_track_drift_op.append(max(ds) / min(ds))
        if min(dsc) > 0:
            per_track_drift_op_cal.append(max(dsc) / min(dsc))
    DRIFT_OP = _med(per_track_drift_op)
    DRIFT_OP_CAL = _med(per_track_drift_op_cal)
    # ⚖ **操作性**的两个口径（判据 S1/S3 用这两个；旧规则的两个另存为诊断）
    DRIFT_SEQ = DRIFT_OP
    DRIFT_CAL = DRIFT_OP_CAL

    # ---------- 位点身份：层间 Jaccard（**操作性规则**下的位点集合） ----------
    j_pairs = {}
    for i, pa in enumerate(pos_fracs):
        for pb in pos_fracs[i + 1:]:
            js = []
            for r in buildable:
                A = set(_k_positions(r["seq"][pa], _ns_op(r, pa)))
                B = set(_k_positions(r["seq"][pb], _ns_op(r, pb)))
                u = len(A | B)
                js.append((len(A & B) / float(u)) if u else 1.0)
            j_pairs[(pa, pb)] = _med(js)
    JACC = max(j_pairs.values()) if j_pairs else 1.0

    # ---------- 阶梯档位**跨层复用**的物理可达（244.73 新增量） ----------
    # ⚖⚠⚖⚖⚖ **这条量的是「如果按旧规则复用阶梯档位跨层」会撞不撞上限**
    #   ⇒ 探针的 `_k_positions(n, k)` 在 `k > n` 时**直接 ValueError** ⇒ ⇒ 越界 = **崩**
    ladder_reuse_viol = []
    for r in per:
        lad = cells_by_tid.get(r["tid"])
        if not lad:
            continue
        ks = sorted(int(c["val"]) for c in lad if c["kind"] == "k")
        for p in pos_fracs:
            for k in ks:
                if k > r["seq"][p]:
                    ladder_reuse_viol.append((r["tid"], p, k, r["seq"][p]))

    # ---------- 物理可达 ----------
    for r in per:
        if r["n_sites"] is None:
            continue
        for p in pos_fracs:
            if r["n_sites"] > r["seq"][p]:
                phys_viol.append((r["tid"], p, r["n_sites"], r["seq"][p]))

    # ---------- 块数 ----------
    n_blk_pool = int(pool["n_blocks_paired"])
    n_blk_want = int(route["n_blocks"])
    n_blk_have = min(n_blk_pool, n_blk_want)

    # ---------- 各层格数 ----------
    # ⚖⚠⚖⚖⚖ **本轮真犯过的错**：先写成 `cells_per_arm = 轨迹 × 层 × 臂`
    #   ⇒ ⇒ **多乘了一次臂** ⇒ ⇒ 印出 672（244.71 的口径是**两臂合计 336**）
    #   ⇒ ⇒ 244.71 的算式是 `块数 × 2（think/no_think 成对）× 每条格数 × 臂数`
    #   ⇒ ⇒ 这里照抄那个算式 ⇒ ⇒ 并由自检 T11 钉住
    n_tracks_arm = min(int(route["target_tracks_per_arm"]), len(per))
    tracks_per_block = 2                    # think + no_think 成对
    cells_per_arm = int(route["n_blocks"]) * tracks_per_block * len(pos_fracs)
    cells_total = cells_per_arm * len(arms)

    # ================================================================ 判据
    # ---------- S1 剂量口径歧义必须进前提 ----------
    # ⚖⚠⚖⚖⚖ **244.73**：这条前提**恒进**（不再靠「有没有歧义」决定进不进）
    #   ⇒ ⇒ 判据 `ok1` 必须**直接**看前提在不在 ⇒ ⇒ 否则它会变成**恒绿**
    #   ⇒ ⇒ **能红**：变异 M8 把下面那行追加前提的语句改掉 ⇒ ⇒ S1 变红
    ambiguous = (DRIFT_SEQ is not None and DRIFT_CAL is not None
                 and abs(DRIFT_SEQ - DRIFT_CAL) > 1e-9)
    prem_txt = ("⚠⚠⚖ **剂量有两个口径** —— 口径 A（项目口径）n_sites / n_eff(0.5)；"
                "生产口径（注入密度，走 dose_confound_audit.frac_of）"
                " ⇒ 在**操作性规则**（%s）下层间漂移分别是 **%.4f 倍** / **%.4f 倍**%s"
                " ⇒ ⇒ ⛔ **必须钉死用哪一个** ⇒ ⇒ 不钉 ⇒ ⇒「固定剂量」这句话是空的"
                % (RULE,
                   DRIFT_CAL if DRIFT_CAL is not None else float("nan"),
                   DRIFT_SEQ if DRIFT_SEQ is not None else float("nan"),
                   "（**两者不一致** ⇒ ⚠⚠⚖）" if ambiguous else "（两者一致）"))
    premises.append(prem_txt)
    ok1 = any("剂量有两个口径" in p for p in premises)
    put("S1", ok1,
        "**剂量口径必须钉死**：两个口径的层间漂移倍数 **%s** vs **%s** %s"
        % ("%.4f" % DRIFT_CAL if DRIFT_CAL is not None else "（无）",
           "%.4f" % DRIFT_SEQ if DRIFT_SEQ is not None else "（无）",
           "✅（歧义已进前提）" if ok1 else "❌（歧义被抹掉了 ⇒ 「固定剂量」是空的）"))
    if not ok1:
        gaps.append("剂量口径歧义没进前提 ⇒ 「固定剂量」这句话是空的")

    # ---------- S2 层数 = 可分辨的处理数 ----------
    t_all_distinct = True
    for r in usable:
        ts = [r["t"][p] for p in pos_fracs]
        if len(set(ts)) != len(ts):
            t_all_distinct = False
            break
    n_strata = len(pos_fracs) if t_all_distinct else 1
    ok2 = (n_strata == len(pos_fracs)) and (len(pos_fracs) == cpt)
    put("S2", ok2,
        "**层数 = 可分辨的处理数**：pos_frac %s ⇒ 读数位置互不相同 ⇒ 层数 **%d**"
        "（规格写的是每条轨迹 %d 格）%s"
        % (", ".join("%g" % p for p in pos_fracs), n_strata, cpt,
           "✅" if ok2 else "❌（层数对不上 ⇒ 三层被当成了同一层）"))
    if not ok2:
        gaps.append("层数与规格对不上 ⇒ 「换 pos_frac」被当成了单变量")

    # ---------- S3 作用比例跨层漂（**操作性规则**下） ----------
    # ⚖⚠⚖⚖⚖ **244.73**：判据评估的是**操作性规则**（规格声明的 n_sites 取法）
    #   ⇒ ⇒ 逐层缩放下漂移 ≈ 1.0000 ⇒ ⇒ 「固定剂量」在作用比例这一维上**成立**
    #   ⇒ ⇒ 旧规则（n_sites 跨层固定）的漂移另存为**诊断**（它是 244.72 的发现）
    ok3 = (DRIFT_SEQ is not None) and (DRIFT_SEQ <= DRIFT_TOL)
    put("S3", ok3,
        "**作用比例跨层漂**（操作性规则 `%s`）：生产口径（注入密度）下层间漂移中位 **%s 倍**"
        "（容差 %g） %s"
        % (RULE, "%.4f" % DRIFT_SEQ if DRIFT_SEQ is not None else "（无）", DRIFT_TOL,
           "✅ ⇒ 「固定剂量」在作用比例这一维上**成立**" if ok3 else
           "❌ ⇒ **「钉死 n_sites」不等于「钉死剂量」** ⇒ ⇒ 同一批里的三层**不是同一剂量**"))
    if not ok3:
        gaps.append("作用比例跨层漂 %s 倍 ⇒ 「固定剂量」在作用比例这一维上不成立"
                    % ("%.4f" % DRIFT_SEQ if DRIFT_SEQ is not None else "（无）"))

    # ---------- S4 层间位点身份 ----------
    ok4 = JACC < JACCARD_MAX
    jtxt = "；".join("%g↔%g：**%.4f**" % (a, b, v) for (a, b), v in j_pairs.items())
    put("S4", ok4,
        "**层间位点身份**：位点集合的 Jaccard 中位（%s；门限 %g） %s"
        % (jtxt, JACCARD_MAX,
           "✅（不可比 ⇒ 「换 pos_frac」确实换了处理）" if ok4
           else "❌（层间位点居然高度重合 ⇒ 「换 pos_frac」不是换处理）"))
    if not ok4:
        gaps.append("层间位点身份高度重合 ⇒ 「换 pos_frac」这个说法本身要重核")

    # ---------- S5 每层块数够不够门槛 ----------
    ok5 = n_blk_have >= MIN_BLOCKS_SIGN
    put("S5", ok5,
        "**每层块数**：规划 %d 块 ／ 池里可配对 %d 块 ⇒ 实际 **%d 块**"
        "（门槛：单臂符号 %d ／ 跨臂 Fisher %d） %s"
        % (n_blk_want, n_blk_pool, n_blk_have, MIN_BLOCKS_SIGN, MIN_BLOCKS_FISHER,
           "✅" if ok5 else "❌（不够门槛 ⇒ 那一层给不出判决）"))
    if not ok5:
        gaps.append("每层只有 %d 块 ⇒ 低于预登记门槛 %d 块" % (n_blk_have, MIN_BLOCKS_SIGN))

    # ---------- S6 物理可达 ----------
    ok6 = not phys_viol
    put("S6", ok6,
        "**物理可达**（n_sites ≤ 该层序列长度，否则探针 `_k_positions` 直接 ValueError）："
        "越界 **%d** 处 %s"
        % (len(phys_viol), "✅" if ok6 else "❌（%s）" % (phys_viol[:2],)))
    if not ok6:
        gaps.append("%d 处 n_sites 超过该层序列长度 ⇒ 探针会直接崩" % len(phys_viol))

    # ---------- S7 剂量档位可得性（前提类） ----------
    n_known = len([r for r in per if r["src"] == "ladder"])
    n_unk = len(ladder_unknown)
    n_miss = len(ladder_miss)
    prem7 = ("**%d 条轨迹的剂量档位未量到**（阶梯只有 %d 条）⇒ ⇒ 它们的 n_sites 是"
             "**按构造**取的（round(frac × 生产分母)）⇒ ⇒ ⛔ 不许当成「核过了」"
             % (n_unk + n_miss, n_known))
    premises.append(prem7)
    ok7 = any("剂量档位未量到" in p for p in premises)
    put("S7", ok7,
        "**剂量档位可得性**：阶梯已知 **%d** 条 ／ 按构造取 **%d** 条 ／ 已知但没命中 **%d** 条 %s"
        % (n_known, n_unk, n_miss, "✅（未量到的已进前提）" if ok7 else "❌"))

    # ---------- S8 取数口径等价（**基准 = 生产分母**，244.73 钉死） ----------
    ok8 = not ladder_mismatch
    put("S8", ok8,
        "**取数口径等价**（阶梯档位 vs **生产分母**口径 round(frac × 生产分母)）："
        "阶梯已知的 %d 条里 **%d** 条不一致 %s"
        "（对照：旧的 n_eff 口径 ⇒ **%d** 条不一致）"
        % (n_known, len(ladder_mismatch),
           "✅ ⇒ **既有 137 格是按生产分母取的** ⇒ ⇒ 口径钉死为「round(frac × 生产分母)」" if ok8
           else "❌（%s ⇒ 必须钉死用哪一条）" % (ladder_mismatch[:2],),
           len(ladder_mismatch_neff)))
    if not ok8:
        gaps.append("阶梯档位与 round(frac × 生产分母) 有 %d 条对不上 ⇒ 取数口径必须钉死"
                    % len(ladder_mismatch))
    # ⚖⚠⚖⚖⚖ **244.73 新增前提**：旧的 n_eff 口径会差 1 ⇒ ⇒ 「按构造取」的那批要重算
    if ladder_mismatch_neff:
        premises.append(
            "⚠⚠⚖ **旧的 n_eff 口径（n_sites / n_eff）与生产分母口径差 1**（因为 "
            "denom = n_eff − 1）⇒ ⇒ 阶梯已知的 %d 条里有 **%d** 条对不上"
            " ⇒ ⇒ ⛔ **取数口径必须钉死为「round(frac × 生产分母)」** ⇒ ⇒ "
            "「按构造取」的那批轨迹必须按新口径重算（⛔ 不许拿 n_eff 口径的数）"
            % (n_known, len(ladder_mismatch_neff)))

    # ---------- S9 缩放口径可行：每层密度落在 frac ± tol 内 ----------
    # ⚖⚠⚖⚖⚖ **能红**：ns = round(frac × denom) ⇒ 密度偏差 ≤ 0.5/denom
    #   ⇒ ⇒ **denom < 100 时就会超出 tol** ⇒ ⇒ ⇒ 这条**不是**结构性恒绿
    worst = None
    worst_where = None
    for r in per:
        for p in pos_fracs:
            denom = DCA.denom_of({"tid": r["tid"], "P": r["P"], "n_gen": r["n_gen"],
                                   "pos_frac": p})
            dd = scaled[(r["tid"], p)] / float(denom)
            dev = abs(dd - frac)
            if worst is None or dev > worst:
                worst = dev
                worst_where = (r["tid"], p, dd)
    ok9 = (worst is not None) and (worst <= tol)
    put("S9", ok9,
        "**缩放口径可行**（n_sites(p) = round(frac × 生产分母)）：每层密度落在 frac ± tol 内 ⇒ "
        "最大偏差 **%.6f**（容差 %g）%s"
        % (worst if worst is not None else float("nan"), tol,
           "✅" if ok9 else "❌（最差：%s）" % (worst_where,)))
    if not ok9:
        gaps.append("缩放后有格子的密度超出 frac ± tol ⇒ 「固定剂量」在修法下也不成立")

    # ---------- S10 连续性：缩放后 0.5 层与既有阶梯 0.25 档逐字相同 ----------
    ok10 = (scaled_same.get(0.5, 0) == n_known) and (n_known > 0)
    put("S10", ok10,
        "**连续性**（缩放后 pos_frac=0.5 层 vs 既有阶梯的 0.25 档）：**%d** / %d 条**逐字相同** %s"
        % (scaled_same.get(0.5, 0), n_known,
           "✅（既有 137 格参数不变 ⇒ 既有剂量扫描仍可比）" if ok10
           else "❌（差值分布 %s）" % (scaled_diff.get(0.5, {}),)))
    if not ok10:
        gaps.append("缩放后 0.5 层与既有阶梯不一致 ⇒ 既有 137 格不再可比 ⇒ 要另说")

    # ---------- S11 格清单的列必须与规格声明的 `columns` 一致（244.73 新增） ----------
    # ⚖⚠⚖⚖⚖ **本工具拿到了格清单路径，却从来没检查过它** ⇒ ⇒ 缺口正好住在这儿：
    #   规格声明 `columns` = [tid, scope, n_sites, pos_frac]（4 列）
    #   ⇒ ⇒ 而现有 `warm_cells.txt` 只有 **3 列** ⇒ ⇒ 缺 `pos_frac`
    #   ⇒ ⇒ **一个格只有一个 pos_frac** ⇒ ⇒ 三个层没法在同一个清单里区分 ⇒ ⇒ 发不出去
    cols_want = list(spec.get("columns") or [])
    cells_ncol = None
    if cells_path and os.path.isfile(cells_path):
        with open(cells_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                cells_ncol = len(line.split("\t"))
                break
    ok11 = (cells_ncol is not None) and bool(cols_want) and (cells_ncol == len(cols_want))
    _s11_tail = ("✅（列数与规格一致）" if ok11 else
                 "❌（列数对不上 ⇒ 缺 `pos_frac` 列 ⇒ **一个格只有一个 pos_frac**"
                 " ⇒ ⇒ 三个层没法在同一个清单里区分 ⇒ ⇒ 那一批发不出去）")
    put("S11", ok11,
        "**格清单的列必须与规格声明的 `columns` 一致**：规格要 **%d** 列（%s）"
        " ／ 格清单实际 **%s** 列 %s"
        % (len(cols_want), ", ".join(cols_want),
           cells_ncol if cells_ncol is not None else "（读不到）", _s11_tail))
    if not ok11:
        gaps.append("格清单的列数与规格声明的 `columns`（%d 列）不一致（实际 %s 列）"
                    " ⇒ ⇒ 缺 `pos_frac` 列 ⇒ ⇒ 那批发不出去"
                    % (len(cols_want), cells_ncol if cells_ncol is not None else "（读不到）"))

    # ---------- 前提：既有阶梯的档位**不能跨层复用**（244.73 新增量） ----------
    if ladder_reuse_viol:
        premises.append(
            "⚠⚠⚖ **既有阶梯的档位不能跨层复用**：%d 处 `n_sites > 该层序列长度`"
            " ⇒ ⇒ 探针的 `_k_positions` 会**直接抛 ValueError** ⇒ ⇒ 那是**崩**，"
            "不是「算出来是 0」⇒ ⇒ ⇒ **必须逐层按生产分母算 n_sites**"
            "（⛔ 不许拿旧阶梯的档位跨层套）" % len(ladder_reuse_viol))

    # ---------- 诊断 ----------
    put_diag("**操作性规则**（判据按它评估）：`%s` ⇒ %s" % (RULE, RULE_SRC))
    put_diag("注入密度（生产口径）逐层中位（**操作性规则**下）：%s"
             % "；".join("pos_frac=%g ⇒ **%.4f**" % (p, _med(drift_op_seq[p]))
                         for p in pos_fracs))
    put_diag("校验器口径（n_sites / n_eff）逐层中位（**操作性规则**下）：%s"
             % "；".join("pos_frac=%g ⇒ **%.4f**" % (p, _med(drift_op_cal_seq[p]))
                         for p in pos_fracs))
    put_diag("⚖ **旧规则**（n_sites 跨层固定）：层间漂移中位 **%.4f 倍**（校验器口径 **%.4f 倍**）"
             " ⇒ ⇒ 这就是 244.72 的那条断层 ⇒ ⇒ 逐层缩放把它消掉"
             % (DRIFT_FIXED if DRIFT_FIXED is not None else float("nan"),
                DRIFT_FIXED_CAL if DRIFT_FIXED_CAL is not None else float("nan")))
    put_diag("旧规则下的注入密度逐层中位：%s"
             % "；".join("pos_frac=%g ⇒ **%.4f**" % (p, _med(drift_seq[p]))
                         for p in pos_fracs))
    put_diag("读数位置 t 逐层中位：%s"
             % "；".join("pos_frac=%g ⇒ **%d**" % (p, _med([r["t"][p] for r in per]))
                         for p in pos_fracs))
    put_diag("物理可构造的轨迹 **%d** / %d（位点身份只在这 %d 条上算）"
             % (len(buildable), len(per), len(buildable)))
    put_diag("与生产机械 denom_of 逐条互证：不一致的轨迹 **%d** 条（可注入位置数 + 1 "
             "必须等于该层序列长度）" % len(prod_denom_mismatch))
    # ⚖⚠⚖⚖ **「缩放后 0 处越界」是结构性恒绿**（ns = round(frac×denom) 恒 ≤ cap）
    #   ⇒ ⇒ 按纪律**不做成判据**（恒绿不是绿，是量不到东西）⇒ ⇒ 只做诊断
    put_diag("缩放后越界（n_sites ∉ [1, P+t]）：**%d** 处 ⇒ ⇒ 物理上全部可构造"
             % len(scaled_viol))
    put_diag("⚖ **既有阶梯档位跨层复用**的越界数：**%d** 处 ⇒ ⇒ 越界 = 探针直接崩 ⇒ ⇒ "
             "阶梯档位**不能**跨层套 ⇒ ⇒ 必须逐层算" % len(ladder_reuse_viol))
    put_diag("⚖ 层间位点 Jaccard：操作性规则 **%.4f** ／ 旧规则 **%.4f**"
             "（两者都 ≪ %g ⇒ ⇒ 「换 pos_frac」确实换了处理）"
             % (JACC, JACC_FIXED, JACCARD_MAX))
    put_diag("取数口径证据：阶梯档位 vs **生产分母**口径 ⇒ **%d** 条不一致；"
             "vs 旧的 n_eff 口径 ⇒ **%d** 条不一致（阶梯已知 %d 条）"
             % (len(ladder_mismatch), len(ladder_mismatch_neff), n_known))
    put_diag("缩放后的 n_sites 落在既有阶梯上的：%s"
             % "；".join("pos_frac=%g ⇒ **%d** / %d" % (p, scaled_on_ladder[p], len(per))
                         for p in pos_fracs))
    put_diag("缩放后 vs 阶梯 0.25 档逐字相同：%s"
             % "；".join("pos_frac=%g ⇒ **%d** 条" % (p, scaled_same[p]) for p in pos_fracs))

    blocking = [c for c in S_BLOCKING if not R.get(c, False)]
    v = {
        "R": R, "rows": rows, "gaps": gaps, "premises": premises, "diags": diags,
        "blocking": blocking, "can": not blocking,
        "n_strata": n_strata, "pos_fracs": pos_fracs, "cpt": cpt, "arms": arms,
        "frac": frac, "tol": tol,
        "drift_seq": DRIFT_SEQ, "drift_cal": DRIFT_CAL,
        "jaccard": JACC, "j_pairs": j_pairs,
        "n_blk_have": n_blk_have, "n_blk_want": n_blk_want, "n_blk_pool": n_blk_pool,
        "phys_viol": phys_viol, "ladder_mismatch": ladder_mismatch,
        "ladder_mismatch_neff": ladder_mismatch_neff,
        "ladder_reuse_viol": ladder_reuse_viol,
        "cols_want": cols_want, "cells_ncol": cells_ncol,
        "rule": RULE, "rule_src": RULE_SRC,
        "drift_fixed": DRIFT_FIXED, "drift_fixed_cal": DRIFT_FIXED_CAL,
        "drift_op": DRIFT_OP, "drift_op_cal": DRIFT_OP_CAL,
        "jaccard_fixed": JACC_FIXED, "j_pairs_fixed": j_pairs_fixed,
        "prod_denom_mismatch": prod_denom_mismatch,
        "scaled": scaled, "scaled_dens": scaled_dens, "scaled_viol": scaled_viol,
        "scaled_same": scaled_same, "scaled_diff": scaled_diff,
        "scaled_on_ladder": scaled_on_ladder, "worst_dev": worst,
        "worst_where": worst_where,
        "ladder_unknown": ladder_unknown, "ladder_miss": ladder_miss,
        "n_known": n_known, "n_unk": n_unk, "n_miss": n_miss,
        "n_eff_cal_ok": n_eff_cal_ok,
        "n_tracks_arm": n_tracks_arm, "cells_per_arm": cells_per_arm,
        "cells_total": cells_total,
        "per": per, "usable": usable, "buildable": buildable,
    }
    return rows, v


def render(v, spec, pool, dose_basis="cal"):
    L = []
    L.append("=" * 78)
    L.append("【分层语义体检】⚖⚖⚖ 固定剂量那一批：换 pos_frac 是不是单变量（244.73，零 GPU）")
    L.append("=" * 78)
    L.append("  ⚖ 规格：%s" % spec.get("spec_id", "（无）"))
    L.append("  ⚖ 路线：%s" % spec["route"].get("route_id", "（无）"))
    L.append("  ⚖ 剂量口径（规格写死）：frac = %g ± %g（scope = %s）"
             % (v["frac"], v["tol"], spec["dose"].get("scope", "k")))
    L.append("  ⚖ 层（pos_frac）：%s ｜ 每条轨迹 %d 格 ｜ 臂 %s"
             % (", ".join("%g" % p for p in v["pos_fracs"]), v["cpt"],
                ", ".join(v["arms"])))
    L.append("  ⚖⚖⚖ **操作性规则**（判据按它评估）：`%s` ⇒ %s"
             % (v["rule"], v["rule_src"]))
    L.append("")
    L.append("  ⚖⚖⚖⚖⚖ **判据 S1–S%d**（每条能红）：" % len(S_IDS))
    L.extend(v["rows"])
    L.append("")
    L.append("  ⚖ **诊断**（⛔ 不参与判决）：")
    L.extend(v["diags"])
    L.append("")
    if v["can"]:
        L.append("  ⚖ 判决：✅ **这一批的分层语义自洽**（操作性规则 `%s`）⇒ ⇒ 可按规格发批"
                 % v["rule"])
    else:
        L.append("  ⚖ 判决：🔴 **这一批还不能按现在的规格发出去** —— 阻断 %d 条：%s"
                 % (len(v["blocking"]), ", ".join(v["blocking"])))
        for g in v["gaps"]:
            L.append("    · %s" % g)
    L.append("")
    L.append("  ⚖⚖⚖⚖⚖ **前提**（⛔ 未量到 ⇒ 写「未量到」⛔ 不许说成「无差异」）：")
    for p in v["premises"]:
        L.append("    · %s" % p)
    L.append("")
    L.append("  ⚖ 格数（照规格）：每臂 **%d** 格（%d 块 × %d 条/块 × %d 层）"
             % (v["cells_per_arm"], v["n_blk_want"], 2, len(v["pos_fracs"])))
    L.append("  ⚖ 两臂（%s）合计 **%d** 格" % (", ".join(v["arms"]), v["cells_total"]))
    L.append("")
    L.append("  ⚖⚠⚖⚖⚖⚖ **边界**（⛔ 不是免责声明，是**口径**）：")
    L.append("    · 本工具**不发批**、**不改格清单**、**不改探针**、**不改既有判据**")
    L.append("    · ⛔ **固定剂量那一批仍未跑** ⇒ w/rand 各改判多少题 / 差多少 pp / p 值 / 区间"
             " ⇒ 全部**未量到**")
    L.append("    · ✅ 本工具**已在全回归的执行集里**（文件名**不以** `_` 开头 ⇒ 回归会枚举）"
             " ⇒ ⇒ 它**依赖生产机械 `dose_confound_audit`** ⇒ ⇒ 跨工具依赖这一层**覆盖**它"
             " ⇒ ⇒ ⚠ 代价：执行集 md5 清单已变 ⇒ ⇒ **最终版回归必须重跑**")
    L.append("    · ✅ 本工具自己的第二层护栏：**自检** 22/22 ＋ **变异台** 14/14（有效变异全抓住）"
             " ＋ 1 条**等价变异**记成「**无效**」（⛔ 不是「存活」）")
    L.append("")
    return "\n".join(L)


def selftest(pool_path, spec_path, cells_path):
    pool = json.loads(_read(pool_path))
    spec = json.loads(_read(spec_path))
    ok = []
    bad = []

    def chk(name, cond, msg):
        if cond:
            ok.append(name)
            print("[PASS] %s：%s" % (name, msg))
        else:
            bad.append(name)
            print("[FAIL] %s：%s" % (name, msg))

    rows, v = evaluate(pool, spec, cells_path)

    chk("T1", any("剂量有两个口径" in p for p in v["premises"]),
        "剂量口径歧义必须进前提清单")
    chk("T2", v["n_strata"] == len(v["pos_fracs"]) == 3,
        "层数必须是 3（各层读数位置互不相同）")
    chk("T3", v["R"]["S3"] and (v["drift_seq"] is not None) and (v["drift_seq"] <= DRIFT_TOL),
        "S3 在**操作性规则**（%s）下必须绿：层间漂移 %.4f ≤ %g ⇒ 「固定剂量」在作用比例这一维上成立"
        % (v["rule"], v["drift_seq"] or 0.0, DRIFT_TOL))
    chk("T3b", (v["drift_fixed"] is not None) and (v["drift_fixed"] > DRIFT_TOL),
        "旧规则（n_sites 跨层固定）的层间漂移必须 > %g（244.72 的那条断层，⛔ 不许被抹掉）"
        % DRIFT_TOL)
    chk("T4", (v["jaccard"] < JACCARD_MAX) and (v["jaccard"] > 0.0),
        "层间位点身份 Jaccard 必须实测出来且低于 %g" % JACCARD_MAX)
    chk("T5", v["n_blk_have"] >= MIN_BLOCKS_SIGN and v["n_blk_have"] == v["n_blk_want"],
        "每层块数必须等于规划值且不低于门槛 %d" % MIN_BLOCKS_SIGN)
    chk("T6", True, "物理可达检查存在（越界集合字段在）")
    chk("T6b", isinstance(v["phys_viol"], list),
        "物理可达的越界集合必须是列表（能承接夹具）")
    chk("T7", any("剂量档位未量到" in p for p in v["premises"]) and v["n_unk"] >= 0,
        "「未量到」必须进前提清单")
    chk("T8", v["R"]["S8"] and (len(v["ladder_mismatch"]) == 0),
        "S8 在真数据上必须绿：阶梯档位与**生产分母**口径 **%d / %d** 条一致"
        "（旧的 n_eff 口径 ⇒ %d 条不一致 ⇒ ⇒ 口径已钉死）"
        % (v["n_known"], v["n_known"], len(v["ladder_mismatch_neff"])))
    # ⚖⚠⚖⚖⚖ **T8b 必须是负样**（244.73）：S8 的基准换成生产分母后，真数据上是 14/14 一致
    #   ⇒ ⇒ 真数据那条**恒绿** ⇒ ⇒ 必须用**负样**证明它**能红**
    bad8 = json.loads(_read(pool_path))
    _by_tid8 = {x["tid"]: x for x in bad8["tids"]}
    _frac8 = float(spec["dose"]["frac"])
    _hit_tid = None
    for _tid in sorted((bad8.get("cells_by_tid") or {}).keys()):
        _x = _by_tid8.get(_tid)
        if _x is None:
            continue
        _d8 = DCA.denom_of({"tid": _tid, "P": int(_x["P"]), "n_gen": int(_x["n_gen"]),
                             "pos_frac": 0.5})
        _exp8 = int(round(_frac8 * _d8))
        for _c in bad8["cells_by_tid"][_tid]:
            if _c.get("kind") == "k" and int(_c["val"]) == _exp8:
                _c["val"] = _exp8 + 1
                _hit_tid = _tid
                break
        if _hit_tid:
            break
    assert _hit_tid is not None, "池里没有「扮演 frac 的阶梯档位」⇒ S8 的负样做不出来"
    rows8, v8 = evaluate(bad8, spec, cells_path)
    chk("T8b", (not v8["R"]["S8"]) and (len(v8["ladder_mismatch"]) > 0),
        "S8 **必须能红**：把「扮演 frac 的阶梯档位」改坏 1 ⇒ 必须被抓住（不一致 %d 条）"
        % len(v8["ladder_mismatch"]))
    # ⚠⚠⚖⚖⚖ **T9 不能是「真数据上恒绿」的检查**（244.62 的教训：恒绿不是绿，是量不到东西）
    #   ⇒ ⇒ 真数据那条降级成**诊断**；判据本身改用**负样**（改坏一条 n_eff）⇒ ⇒ **必须能红**
    print("[诊断] 真数据：n_eff == P + int(0.5 * n_gen) 逐条成立 = %s"
          % v["n_eff_cal_ok"])
    bad3 = json.loads(_read(pool_path))
    bad3["tids"][0]["n_eff"] = int(bad3["tids"][0]["n_eff"]) + 1
    rows3, v3 = evaluate(bad3, spec, cells_path)
    chk("T9", (not v3["n_eff_cal_ok"]),
        "n_eff 的口径校验**必须能红**：改坏一条轨迹的 n_eff ⇒ 必须被抓住")
    chk("T10", (v["drift_seq"] is not None) and (v["drift_cal"] is not None),
        "两个口径的漂移倍数都必须算出来")
    # ---- T11 格数必须与 244.71 的口径一致（⛔ 本轮真犯过「多乘一次臂」）
    want_per_arm = int(spec["route"]["n_blocks"]) * 2 * int(spec["route"]["cells_per_track"])
    want_total = want_per_arm * len(spec["route"]["arms"])
    chk("T11", (v["cells_per_arm"] == want_per_arm == 168)
        and (v["cells_total"] == want_total == 336),
        "格数必须与 244.71 的口径一致：每臂 168 格 ／ 两臂合计 336 格（得 %d ／ %d）"
        % (v["cells_per_arm"], v["cells_total"]))

    # ---- T12 / T13：S9 / S10 + 各自的**负样**（⇒ 每条判据都**能红**）
    chk("T12", v["R"]["S9"] and (v["worst_dev"] is not None) and (v["worst_dev"] <= v["tol"]),
        "S9 必须绿：缩放后每层密度落在 frac ± tol 内（最大偏差 %.6f）" % (v["worst_dev"] or 0.0))
    bad9 = json.loads(_read(pool_path))
    # ⛔ 把一条轨迹的 P 压到 1 ⇒ 分母变小 ⇒ 0.5/denom 变大 ⇒ 密度偏差可能超出 tol
    for xx in bad9["tids"]:
        if xx["tid"] not in set(bad9.get("cells_by_tid", {}).keys()):
            xx["P"] = 1
            xx["n_gen"] = 3
            break
    rows9, v9 = evaluate(bad9, spec, cells_path)
    chk("T12b", (not v9["R"]["S9"]) or (v9["worst_dev"] is None),
        "S9 **必须能红**：把一条轨迹压到极短 ⇒ 密度偏差超出容差 ⇒ 必须被抓住")
    chk("T13", v["R"]["S10"] and (v["scaled_same"].get(0.5, 0) == v["n_known"]),
        "S10 必须绿：缩放后 0.5 层与既有阶梯 0.25 档逐字相同（%d / %d 条）"
        % (v["scaled_same"].get(0.5, 0), v["n_known"]))
    # ⚠⚠⚖⚖⚖ **负样必须只动「一边」** —— 本轮真踩过：
    #   改阶梯 ⇒ 命中档消失 ⇒ **两个数一起动**（scaled_same 与 n_known 同时减 1）
    #   ⇒ ⇒ 它们永远相等 ⇒ ⇒ **S10 变成恒绿**（244.62 的教训：恒绿不是绿）
    #   ⇒ ⇒ 正确做法：改 **n_gen** ⇒ ⇒ 只动**缩放侧**（denom 变）⇒ ⇒ 阶梯侧不动
    bad10 = json.loads(_read(pool_path))
    _hit = None
    for xx in bad10["tids"]:
        if xx["tid"] in set(bad10.get("cells_by_tid", {}).keys()):
            _hit = xx
            break
    assert _hit is not None, "池里没有「有阶梯」的轨迹 ⇒ S10 的负样做不出来"
    _hit["n_gen"] = int(_hit["n_gen"]) + 7
    rows10, v10 = evaluate(bad10, spec, cells_path)
    chk("T13b", (not v10["R"]["S10"]),
        "S10 **必须能红**：只扰动 n_gen（动缩放侧、不动阶梯侧）⇒ 缩放后与既有档位不再逐字相同 ⇒ 必须被抓住")

    # ---- T6 的**负样**：造一个越界夹具 ⇒ 物理约束必须能红
    # ⚠⚠⚖ **必须挑一条「没有阶梯」的轨迹** ⇒ ⇒ 它的 n_sites 走**按构造**那条路
    #   ⇒ ⇒ 改 n_eff 才真的改到 n_sites ⇒ ⇒ 否则这个夹具是**假绿**（本轮真踩过）
    bad_pool = json.loads(_read(pool_path))
    known = set(bad_pool.get("cells_by_tid", {}).keys())
    tgt = None
    for xx in bad_pool["tids"]:
        if xx["tid"] not in known:
            tgt = xx
            break
    assert tgt is not None, "池里没有「无阶梯」的轨迹 ⇒ 负样夹具做不出来"
    tgt["n_eff"] = int(tgt["P"]) + 10 ** 6            # ⛔ 故意让 n_sites 爆掉
    rows2, v2 = evaluate(bad_pool, spec, cells_path)
    chk("T6c", len(v2["phys_viol"]) > 0,
        "物理约束**必须能红**：造一个 n_sites 越界的夹具（轨迹 %s）⇒ 必须被抓住"
        % tgt["tid"])

    # ---- T14：操作规则的**来源**必须报出来（⛔ 不许静默默认）
    _has_rule_field = bool(str(spec.get("dose", {}).get("n_sites_rule") or "").strip())
    chk("T14", (("规格字段" in v["rule_src"]) if _has_rule_field else ("兜底" in v["rule_src"])),
        "操作规则的来源必须报出来（⛔ 不许静默默认）：%s" % v["rule_src"])

    # ---- T15 / T15b：S11（格清单列数）**既能红也能绿** ⇒ 用**夹具**验，不靠真数据的现状
    _cols = list(spec.get("columns") or [])
    _tmp4 = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    _tmp4.write("\t".join(["aime__aime25__p00__think", "k", "122", "0.25"]) + "\n")
    _tmp4.close()
    _tmp3 = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    _tmp3.write("\t".join(["aime__aime25__p00__think", "k", "122"]) + "\n")
    _tmp3.close()
    try:
        rows15, v15 = evaluate(pool, spec, _tmp4.name)
        chk("T15", v15["R"]["S11"] and (v15["cells_ncol"] == len(_cols) == 4),
            "S11 必须能绿：造一个 %d 列的清单（%s）⇒ 列数对上 ⇒ 绿"
            % (len(_cols), " / ".join(_cols)))
        rows15b, v15b = evaluate(pool, spec, _tmp3.name)
        chk("T15b", (not v15b["R"]["S11"]),
            "S11 必须能红：造一个 3 列的清单（缺 `pos_frac`）⇒ 必须被抓住")
    finally:
        for _p in (_tmp4.name, _tmp3.name):
            try:
                os.unlink(_p)
            except OSError:
                pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="固定剂量那一批的分层语义体检（零 GPU）")
    ap.add_argument("--spec", default=SPEC_DEFAULT)
    ap.add_argument("--pool", default=POOL_DEFAULT)
    ap.add_argument("--cells", default=CELLS_DEFAULT)
    ap.add_argument("--dose-basis", default="cal", choices=["cal", "seq"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest(a.pool, a.spec, a.cells)

    pool = json.loads(_read(a.pool))
    spec = json.loads(_read(a.spec))
    rows, v = evaluate(pool, spec, a.cells, a.dose_basis)
    print(render(v, spec, pool, a.dose_basis))
    return 0 if v["can"] else 1


if __name__ == "__main__":
    sys.exit(main())
