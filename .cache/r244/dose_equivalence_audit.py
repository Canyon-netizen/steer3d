#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""dose_equivalence_audit.py —— **剂量等值性**核查（244.83）。

⚖⚖⚖⚖⚖ **这个文件回答什么**
   244.81/244.82 的判决面板（w 臂 vs rand 臂、轨迹级差 +30.36pp、块级差 +53.57pp）
   **全部**建立在一句**从未被实测过**的话上：

       「w 臂与 rand 臂是**同一个剂量**下的比较。」

   此前这句话只有**跑批脚本里的一行注释**作依据 ⇒ ⇒ 注释不是测量。
   本文件把它**逐项实测**：向量范数、α 网格、判决读数 α、位点数、位点集合、
   逐格字段、静态命令行、逐格注入总范数 —— 共 **11 条硬判据**（预登记 §3.1）。

⚖⚖⚖⚖⚖ **纪律（本文件的形状就是这些纪律）**
   ① **口径只从预登记读**：`.cache/xcheck/R6_DOSE_EQUIVALENCE_PREREG.md`（244.83 签）
      ⇒ ⇒ 本文件**不写死**那些口径常量？—— **写死的是「从预登记读来的」那一组**，
      且 §3.1 判它们**逐条在案**（⛔ 不默认值兜底、不静默降级）。
   ② **两条独立证据流**：
        · **S1 静态**：bpath 的 `r244_warm_sweep.sh`（跑批器）＋ `r241_probe.py`（探针）
          ⇒ ⇒ 剂量规格**从源码逐字读出**，⛔ 不抄日志里的印字当答案；
        · **S2 动态**：bpath 两臂原始日志的逐格字段 ＋ `w_p2a.npy` 的实际范数
          ⇒ ⇒ **不看任何判决读数**（本轮只管剂量这一侧）。
   ③ ⛔ **每条硬判据都必须有「跨来源」那一半**：只比「两臂相等」的判据在结构上
      **可能恒绿**（两臂跑的是**同一份模板** ⇒ 相同是必然的）⇒ ⇒ 本文件对每条
      硬判据都额外要求「**与源码/日志/文件里的另一处来源对账**」⇒ ⇒ 那才是能红的部分。
   ④ **每条判据能红**：`--selftest`（G0-1 合成夹具，零 bpath、零 GPU）
      ＋ 变异台 `mut_dose_equivalence_audit.py`（⛔ 变异台必须能红）。
   ⑤ **判决只算一次**：印出来的 = 返回的。
   ⑥ ⛔ **未量到 ≠ 没差异 ≠ 失败**：w 臂缺的那一格 ⇒ 报「未量到」，⛔ 不当 0、不当失败。

⚖⚖⚖ **本文件**不**产出**「w 有效、rand 无效」这类**机制**结论
   （预登记 §4：那要等「同结论对照臂」，244.84+）⇒ ⇒ 本轮只管**剂量**这一侧。
"""

import argparse
import io
import json
import math
import os
import re
import sys

import numpy as np

# =============================================================================
# 口径常量（**逐条对应**预登记 §2 / §3.1）
#   ⚠ 这些值**同时**被 `--print-spec` 印出来 ⇒ ⇒ 变异台能逐条改它们 ⇒ ⇒ 能红。
# =============================================================================
SPEC = {
    "norm_rel_tol": 1e-6,          # Q3：注入前（float64）范数相对差上限
    "bf16_rel_bound": 1e-2,        # Q3′：注入后（bfloat16）范数相对差上限 ＝ 5 × 2^-9
    "model_dtype": "bfloat16",     # Q3″：模型 dtype（必须与探针源码一致）
    "k_seed": 0,                   # Q7：位点选择的种子（探针里写死 0）
    "inj_rel_tol": 1e-6,           # Q10：逐格注入总范数相对差上限
    "inj_direct_cells": 20,        # Q10：直接求和路径的抽样格数
    "cos_ref_seeds": 2000,         # Q11：余弦参考分布规模 K
    "cos_sd_rel_tol": 0.05,        # Q11：参考分布 sd 与理论值 1/√d 的相对差上限
    "w_npy_md5": "d8e6a066d55a6e5196ff706bd59bcedb",
    "runner_md5": "5d9cdffeafdbf5fe83195db183ee17a3",
    "probe_md5": "61f5b6919306299c164af1bb9cf79c0a",
    "cells_md5": "b3de113e028720b3d0ee92f7cd0b9e99",
    "w_log_md5": "3f910a1c600a81d5a909834db81e35e7",
    "rand_log_md5": "5f4b928a3ebc25e3ee65171b2ac3a6e9",
}

# =============================================================================
# 字段划分（预登记 §0.5 更正 ② / Q8）
#   S  = 剂量结构字段：**两臂必须逐位相同**
#   R  = 读数字段：**允许不同**（方向不同 ⇒ slope / p9_* / … 必然不同）
#   D  = 退化字段：repeat=1 ⇒ **与注入向量无关** ⇒ 不可能两臂不同（登记理由）
#   「arm」是**唯一被允许取值不同**的结构字段，单独列出。
#   ⚖ 这三张清单**互斥且完备**覆盖日志里出现的 49 个字段（实测核对，见 DQ-FIELDS-PART）。
# =============================================================================
STRUCT_FIELDS = (
    "P", "gap", "inject_n_sites", "inject_nested", "inject_scope",
    "n_gen", "n_steps", "pos_frac", "rep_n_hi", "rep_n_lo", "t", "tid",
)
ARM_FIELD = "arm"
READOUT_FIELDS = (
    "b_ctl", "b_mark", "ctl_min_adj_diff", "ctl_n_distinct", "dm_max", "dm_min",
    "fit_err_hi", "fit_err_hi_sigma", "fit_err_lo", "lin_ratio", "margin_meas",
    "marker_raw_hi", "marker_raw_lo", "min_adj_diff", "n_distinct",
    "p9_hi", "p9_hi_meas", "p9_lo", "p9_lo_meas", "p9_margin_se",
    "p9_se_hi", "p9_se_lo", "p9_up_mono", "rep_mean_hi", "rep_mean_lo",
    "resid_std", "resid_std_local", "slope", "slope_local", "up_mono_meas",
)
# ⚖ 退化字段：**定义上**与注入向量无关（repeat=1 ⇒ 标准差无定义(null) / 散布恒 0 / 恒精确）
DEGENERATE_FIELDS = (
    "rep_exact_hi", "rep_exact_lo", "rep_spread_hi", "rep_spread_lo",
    "rep_std_hi", "rep_std_lo",
)

# ⚖ 判决读数 α 的两个系数（探针源码：`("lo", 0.5 * a.gap), ("hi", 1.0 * a.gap)`）
READOUT_COEF = (0.5, 1.0)

# ⚖ Q12：残余混淆（**必须逐条在案**，⛔ 漏一条 ⇒ 红）
REMIX = (
    ("①", "rand 臂的 α 是**绝对**注入量；`gap` 是 **w 的属性**（rand 方向无类间隙）"
          "⇒ 判决读数用**绝对 α**，故两臂读数剂量相同，但**语义不同**必须写明"),
    ("②", "w 是**训练所得**的方向、rand 是**各向同性**方向 ⇒ 「rand 臂差」"
          "**不等于**「只有 w 有效」"),
    ("③", "**单种子**：rand 臂只用了**一个**方向（种子 0）⇒ 「随机」的覆盖面**未量到**"),
    ("④", "**未正交化**：`cos(w, rand) ≠ 0`（实测见下）⇒ rand 臂里含 w 成分的"
          "**影响未量到**"),
)
# ⚖ 每条残余混淆**必须包含的关键词**（⛔ 少了 ⇒ 红 ⇒ ⇒ 变异台能删掉一条来验）
REMIX_REQUIRED = (
    ("①", "绝对"), ("②", "各向同性"), ("③", "单种子"), ("④", "未正交化"),
)

# =============================================================================
# 探针源码里必须逐字存在的**事实**（Q2 / DQ-SRC）
#   ⛔ 写死这些常量就等于「抄答案」⇒ ⇒ 这里要的是**源码里真的有这行**。
# =============================================================================
SRC_MUST_CONTAIN = (
    ("rand_normalize", "W = (W / np.linalg.norm(W)) * float(np.linalg.norm(_W0))"),
    ("rand_draw", "W = _g.standard_normal(_W0.shape).astype(np.float64)"),
    ("k_positions_rng", "_rng = _np.random.default_rng(int(seed))"),
    ("k_positions_perm", "return sorted(int(x) for x in _rng.permutation(n)[:k])"),
    ("alpha_grid", "alphas = np.linspace(-a.alpha_max, a.alpha_max, a.n_steps)"),
    ("inject_dtype", "torch.as_tensor(vec, dtype=h.dtype"),
    ("readout_alpha", '("lo", 0.5 * a.gap), ("hi", 1.0 * a.gap)'),
)

BEGIN_RE = re.compile(
    r"^### BEGIN (\S+) \[(\d+)/(\d+)\] n_eff=(\d+) --inject-scope (\S+) --inject-n-sites (\d+)")
END_RE = re.compile(r"^### END\s+\[(\d+)/(\d+)\] (\S+) rc=(-?\d+)")
MOD_RE = re.compile(r"\[臂\] 用固定种子随机方向（mod=([0-9.]+)，与 w 同模长）")


def die(msg):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(3)


class Criteria(object):
    """⚖ 判据收集器：每条判据**带 id** ⇒ ⇒ 变异台能知道「哪条该红」。"""

    def __init__(self):
        self.items = []

    def check(self, cid, ok, detail):
        self.items.append((cid, bool(ok), detail))
        print("[%s] %-16s %s" % ("PASS" if ok else "FAIL", cid, detail))
        return bool(ok)

    def fail_count(self):
        return sum(1 for _c, ok, _d in self.items if not ok)

    def failed_ids(self):
        return set(c for c, ok, _d in self.items if not ok)

    def summary(self):
        n = len(self.items)
        bad = self.fail_count()
        print("判据 %d 条 ｜ PASS %d ｜ FAIL %d" % (n, n - bad, bad))
        return 0 if bad == 0 else 1


class _Ov(object):
    """⚖ 临时替换模块级常量（**只**自检用；⛔ 不影响真数据路径）。"""

    def __init__(self, **kw):
        self.kw = kw
        self.old = {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = globals()[k]
            globals()[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            globals()[k] = v


# =============================================================================
# 基础：读文件 / md5 / 数值
# =============================================================================


def read_text(path):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def md5_of(path):
    import hashlib
    h = hashlib.md5()
    with io.open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def linspace(start, stop, num):
    """⚖ 与 `numpy.linspace` 同序同精度（先 `step*i` 再 `+ start`，末点强制取 stop）。"""
    if num <= 0:
        return []
    if num == 1:
        return [float(start)]
    div = num - 1
    step = (float(stop) - float(start)) / float(div)
    y = [float(start) + step * i for i in range(num)]
    y[-1] = float(stop)
    return y


def to_bf16(x):
    """⚖ 把 float32 数组**舍入**到 bfloat16（round-to-nearest-even），再回到 float32。

    ⚠ 为什么要自己实现：注入发生时的 dtype 是 **bfloat16**（探针第 379 行
    `torch_dtype=torch.bfloat16`）⇒ ⇒ 「注入后的范数」只能在 **bf16 量化精度**上谈。
    ⛔ 不 import torch ⇒ ⇒ 本审计**零 GPU 栈依赖**（bf16 舍入规则＝保留高 16 位
    的就地 RNE，与 torch 的 `to(torch.bfloat16)` 一致，由 `_cross_check_24483.py`
    现场对账）。
    """
    a = np.ascontiguousarray(np.asarray(x, dtype=np.float32))
    bits = a.view(np.uint32).copy()
    lsb = (bits >> np.uint32(16)) & np.uint32(1)
    bits = (bits + np.uint32(0x7FFF) + lsb) & np.uint32(0xFFFF0000)
    return bits.view(np.float32)


def rand_direction(w0, seed):
    """⚖ **探针里的 rand 规则**（逐字对应 `r241_probe.py` 第 405–406 行）：

         W = _g.standard_normal(_W0.shape).astype(np.float64)
         W = (W / np.linalg.norm(W)) * float(np.linalg.norm(_W0))

    ⚠⚠⚠⚠ **缩放因子的精度口径 —— 这是 244.83 抓到的一个真 bug**：
       `_W0` 是 **float32** 数组 ⇒ ⇒ `np.linalg.norm(_W0)` 走 **float32** 累加
       （BLAS `sdot`）⇒ ⇒ 返回值是 **float32**（本批 = **1.0** 精确）
       ⇒ ⇒ 缩放因子 = **float32 范数**。
       ⛔ 若误用 float64 范数（0.99999999935713）⇒ ⇒ 与探针**实际行为**差 6.4e-10
       ⇒ ⇒ 判决数会错（虽然仍 < 1e-6 上限、形态不变）⇒ ⇒ **数要更正，不是"差不多就行"**。

    ⚠ `w0` 必须是**原始 float32 数组**（⛔ 不是 float64 转换后的）。
    """
    g = np.random.default_rng(int(seed))
    w = g.standard_normal(w0.shape).astype(np.float64)
    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0))
    return w


def k_positions(n, k, seed):
    """⚖ **探针里的位点规则**（第 126–133 行，nested=True 分支）：
         default_rng(seed).permutation(n)[:k] ⇒ 排序
    """
    g = np.random.default_rng(int(seed))
    perm = g.permutation(int(n))
    return sorted(int(x) for x in perm[:int(k)])


def inject_total_formula(alpha_max, vnorm, k):
    """⚖ 注入扰动总范数（**公式路径**）：k 个位点各加 `α·v` ⇒ ‖Σ‖ = |α|·‖v‖·√k。"""
    return float(alpha_max) * float(vnorm) * math.sqrt(float(k))


def inject_total_direct(alpha_max, v, k):
    """⚖ 注入扰动总范数（**直接路径**）：把 k 份 `α·v` 当作**注入场**
       （每个位点各一份）⇒ 取整场的 **L2 范数** = √(Σ_j ‖α·v‖²) = |α|·‖v‖·√k。

    ⚖ 为什么是 L2 而不是「向量和的范数」：k 份是**同一个**向量，
       它们的**和**是 k·v（范数 k·‖v‖），那不是「往残差流里加了多少量」；
       残差流上真正被改动的是**整场** ⇒ ⇒ 该看整场的 L2 范数。
    ⚖ 为什么要两条路径：一条写错（例如漏掉 √k、或误用 k）时，另一条会**对不上**
       ⇒ ⇒ 这就是「跨来源」那一半 ⇒ ⇒ 判据能红。
    """
    nv = float(np.dot(v, v))
    sq = 0.0
    a2 = float(alpha_max) ** 2
    for _ in range(int(k)):
        sq += a2 * nv
    return math.sqrt(sq)


# =============================================================================
# 解析：日志 / 跑批器 / 探针 / cells
# =============================================================================


def parse_log(path):
    """⚖ 解析跑批日志 ⇒ PINNED / NMAP / 逐格（BEGIN + JSON + END）。"""
    txt = read_text(path)
    pinned, nmap_lines, cells_line = {}, [], None
    cells, order = {}, []
    cur = None
    mods = []
    for ln in txt.split("\n"):
        if ln.startswith("PINNED "):
            for tok in ln[7:].split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    pinned[k] = v
        elif ln.startswith("CELLS "):
            cells_line = ln
        elif ln.startswith("NMAP "):
            nmap_lines.append(ln)
        elif ln.startswith("### BEGIN "):
            m = BEGIN_RE.match(ln)
            if not m:
                continue
            cur = {"tid": m.group(1), "idx": int(m.group(2)), "total": int(m.group(3)),
                   "n_eff": int(m.group(4)), "scope": m.group(5), "n_sites": int(m.group(6)),
                   "json": None, "end_rc": None}
        elif ln.lstrip().startswith("{"):
            try:
                d = json.loads(ln.strip())
            except Exception:
                continue
            if not (isinstance(d, dict) and "tid" in d and "pos_frac" in d):
                continue
            if cur is not None:
                cur["json"] = d
                key = (d.get("tid"), d.get("pos_frac"))
                cells[key] = cur
                order.append(key)
        elif ln.startswith("### END"):
            m = END_RE.match(ln)
            if m and cur is not None:
                cur["end_rc"] = int(m.group(4))
        m2 = MOD_RE.search(ln)
        if m2:
            mods.append(float(m2.group(1)))
    return {"path": path, "pinned": pinned, "nmap": nmap_lines, "cells_line": cells_line,
            "cells": cells, "order": order, "mods": mods, "text": txt}


def parse_cells_tsv(path):
    """⚖ 读格清单（4 列：tid / scope / n_sites / pos_frac，带表头）。"""
    out = {}
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        lines = [x.rstrip("\n") for x in fh]
    hdr = lines[0].split("\t")
    if hdr != ["tid", "scope", "n_sites", "pos_frac"]:
        raise ValueError("cells 表头不对：%r" % (hdr,))
    for ln in lines[1:]:
        if not ln.strip():
            continue
        tid, scope, ns, pf = ln.split("\t")
        out[(tid, float(pf))] = {"scope": scope, "n_sites": int(ns), "pos_frac": float(pf)}
    return out


def parse_runner(path):
    """⚖ 从跑批器源码抠出 `$C` 命令行模板与 `$B`。"""
    txt = read_text(path)
    m = re.search(r'^C="(.*)"\s*$', txt, re.M)
    if not m:
        raise ValueError("跑批器里找不到 C=... 命令行模板")
    mb = re.search(r"^B=(\S+)", txt, re.M)
    return {"c_tpl": m.group(1), "B": mb.group(1) if mb else "", "text": txt}


def subst_cmd(c_tpl, B, W_PATH, GPU, ARM):
    s = c_tpl.replace("$B", B).replace("$W_PATH", W_PATH)
    s = s.replace("$GPU_UUID", GPU).replace("$ARM", ARM)
    return s.split()


def flags_of(tokens):
    """⚖ 命令行 ⇒ {flag: value}；无值开关（布尔）记成 ""。"""
    out = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                out[t] = tokens[i + 1]
                i += 2
            else:
                out[t] = ""
                i += 1
        else:
            i += 1
    return out


def src_readout_coef(text):
    """⚖ 从探针源码里读出判决读数 α 的两个系数（跨来源那一半）。"""
    m = re.search(r'\("lo",\s*([0-9.]+)\s*\*\s*a\.gap\),\s*\("hi",\s*([0-9.]+)\s*\*\s*a\.gap\)',
                  text)
    if not m:
        return None
    return (float(m.group(1)), float(m.group(2)))


def src_k_seed(text):
    """⚖ 从探针源码里读出 `_k_positions` 的默认种子（跨来源那一半）。"""
    m = re.search(r"def _k_positions\(.*?seed\s*=\s*(\d+)", text, re.S)
    return int(m.group(1)) if m else None


# =============================================================================
# 上下文
# =============================================================================


class Ctx(object):
    def __init__(self, w_log, rand_log, runner, probe, w_npy, cells):
        self.w = parse_log(w_log)
        self.r = parse_log(rand_log)
        self.runner = parse_runner(runner)
        self.probe_text = read_text(probe)
        self.probe_md5 = md5_of(probe)
        self.w0 = np.load(w_npy)
        self.cells = parse_cells_tsv(cells)
        self.paths = {"w_log": w_log, "rand_log": rand_log, "runner": runner,
                      "probe": probe, "w_npy": w_npy, "cells": cells}


def arm_cmd(ctx, arm):
    """⚖ 某臂的**实际命令行**（从跑批器模板 ＋ 该臂的 PINNED 行代入）。"""
    lg = ctx.w if arm == "w" else ctx.r
    p = lg["pinned"]
    return subst_cmd(ctx.runner["c_tpl"], ctx.runner["B"], p.get("W_PATH", ""),
                     p.get("GPU", ""), p.get("ARM", arm))


# =============================================================================
# 判决
# =============================================================================


def evaluate(ctx, spec, cr):
    """⚖ 跑全部判据 ⇒ 返回 (verdict, results)。"""
    res = {}

    # ---- 0) G0-3 前置：六件产物都在且可读 ------------------------------
    need = ["w_log", "rand_log", "runner", "probe", "w_npy", "cells"]
    miss = [k for k in need if not os.path.exists(ctx.paths[k])]
    if miss:
        print("G0_3_HARDSTOP: 缺产物：%s" % ",".join(miss))
        return "D-C", {"hardstop": miss}

    # ---- DQ-ARTEFACT：产物 md5 对账 -------------------------------------
    #   ⚖ 前四件的期望值来自**账本登记**（244.78/244.79/31065 段）⇒ ⇒ **独立来源**；
    #   ⚖ 后两件（两臂日志）**此前从未被登记过** ⇒ ⇒ 本轮**首次登记** ⇒ ⇒ 从下一轮起才成为独立来源。
    md5s = dict((k, md5_of(ctx.paths[k])) for k in
                ("w_log", "rand_log", "runner", "probe", "w_npy", "cells"))
    pin_ledger = (("runner", "runner_md5"), ("probe", "probe_md5"),
                  ("w_npy", "w_npy_md5"), ("cells", "cells_md5"))
    pin_new = (("w_log", "w_log_md5"), ("rand_log", "rand_log_md5"))
    bad = [(k, md5s[k], spec[sk]) for k, sk in pin_ledger + pin_new if md5s[k] != spec[sk]]
    cr.check("DQ-ARTEFACT", not bad,
             "产物 md5 逐位对上：账本登记的 %d 件（%s）｜ 本轮首次登记的 %d 件（%s）｜ 不符 %d 件%s"
             % (len(pin_ledger), "、".join(k for k, _ in pin_ledger),
                len(pin_new), "、".join(k for k, _ in pin_new),
                len(bad), ("：%s" % bad) if bad else ""))
    res["artifact_md5"] = md5s

    # ---- DQ-DTYPE：模型 dtype 与注入 dtype（跨来源：源码 + 登记值）------
    mdt = re.search(r"torch_dtype=torch\.(\w+)", ctx.probe_text)
    model_dt = mdt.group(1) if mdt else None
    inj_dt = "torch.as_tensor(vec, dtype=h.dtype" in ctx.probe_text
    ok = (model_dt is not None and inj_dt and model_dt == spec["model_dtype"])
    cr.check("DQ-DTYPE", ok,
             "模型 dtype=%s（源码读出）｜ 注入 dtype 取 h.dtype=%s ｜ 登记值=%s ⇒ %s"
             % (model_dt, model_dt if inj_dt else "⛔未找到", spec["model_dtype"],
                "一致" if ok else "⛔不一致"))
    res["model_dtype"] = model_dt

    # ---- DQ-SRC：探针源码里的七条事实 + 位点规则不依赖臂 -----------------
    miss_src = [k for k, s in SRC_MUST_CONTAIN if s not in ctx.probe_text]
    mk = re.search(r"def _k_positions\(.*?\n(?=\ndef )", ctx.probe_text, re.S)
    kp_body = mk.group(0) if mk else ""
    arm_dep = ("arm" in kp_body) if kp_body else True
    ok = (not miss_src) and (not arm_dep)
    cr.check("DQ-SRC", ok,
             "探针源码七条事实缺 %d 条%s｜ 位点规则是否依赖臂：%s"
             % (len(miss_src), ("（%s）" % ",".join(miss_src)) if miss_src else "",
                "⛔是" if arm_dep else "否"))
    res["src_missing"] = miss_src

    # ---- DQ-NORM：注入前（float64）范数等值 -----------------------------
    w0 = ctx.w0
    w64 = w0.astype(np.float64)
    w_norm = float(np.linalg.norm(w64))
    r_vec = rand_direction(w0, spec["k_seed"])
    r_norm = float(np.linalg.norm(r_vec))
    rel = abs(r_norm - w_norm) / max(w_norm, 1e-300)
    ok = rel <= spec["norm_rel_tol"]
    # ⚖ 探针用的缩放因子 = `float(np.linalg.norm(_W0))`，而 `_W0` 是 **float32**
    #    ⇒ numpy 走 float32 累加 ⇒ 返回 float32（本批 = 1.0 精确）
    scale_f32 = float(np.linalg.norm(w0))
    cr.check("DQ-NORM", ok,
             "注入前范数（float64 口径）：w=%.17g ｜ rand(seed=%d)=%.17g ｜ 相对差=%.3e（上限 %.1e）"
             "｜ 探针缩放因子 float(np.linalg.norm(float32 W))=%.17g"
             % (w_norm, spec["k_seed"], r_norm, rel, spec["norm_rel_tol"], scale_f32))
    res["w_norm"] = w_norm
    res["r_norm"] = r_norm
    res["scale_f32"] = scale_f32

    # ---- DQ-NORM16：注入后（bfloat16）范数等值 --------------------------
    w_b = to_bf16(w0.astype(np.float32)).astype(np.float64)
    r_b = to_bf16(r_vec.astype(np.float32)).astype(np.float64)
    wn_b, rn_b = float(np.linalg.norm(w_b)), float(np.linalg.norm(r_b))
    rel16 = abs(rn_b - wn_b) / max(wn_b, 1e-300)
    ok = rel16 <= spec["bf16_rel_bound"]
    cr.check("DQ-NORM16", ok,
             "注入后（bfloat16）范数：w=%.10f ｜ rand=%.10f ｜ 相对差=%.3e（上限 %.1e ＝ 5×2^-9）"
             % (wn_b, rn_b, rel16, spec["bf16_rel_bound"]))
    res["w_norm_bf16"] = wn_b
    res["r_norm_bf16"] = rn_b
    res["rel_bf16"] = rel16

    # ---- 两臂命令行 ------------------------------------------------------
    cw, crd = arm_cmd(ctx, "w"), arm_cmd(ctx, "rand")
    fw, fr = flags_of(cw), flags_of(crd)

    # ---- DQ-CMD：静态命令行只差 gpu-uuid / arm（--w 必须相同）-----------
    allowed = ("--gpu-uuid", "--arm")
    diffs = []
    for f in sorted(set(fw) | set(fr)):
        if f in allowed:
            continue
        if fw.get(f) != fr.get(f):
            diffs.append((f, fw.get(f), fr.get(f)))
    w_same = fw.get("--w") == fr.get("--w")
    ok = (not diffs) and w_same
    cr.check("DQ-CMD", ok,
             "命令行扣掉 %s 后两臂差异 %d 处%s｜ `--w` 两臂%s（%s）"
             % ("/".join(allowed), len(diffs),
                ("：%s" % diffs) if diffs else "", "相同" if w_same else "⛔不同",
                fw.get("--w")))
    res["cmd_diffs"] = diffs

    # ---- DQ-ALPHA：α 网格两臂相同 **且** 与源码构造式一致 ---------------
    amax = fw.get("--alpha-max")
    nst = fw.get("--n-steps")
    grid_w = linspace(-float(amax), float(amax), int(nst)) if amax and nst else []
    grid_r = linspace(-float(fr.get("--alpha-max")), float(fr.get("--alpha-max")),
                      int(fr.get("--n-steps"))) if fr.get("--alpha-max") and fr.get("--n-steps") else []
    same_grid = bool(grid_w) and grid_w == grid_r
    # 跨来源：网格首/末点必须 == ∓alpha_max（源码：`linspace(-alpha_max, alpha_max, n_steps)`）
    src_ok = bool(grid_w) and grid_w[0] == -float(amax) and grid_w[-1] == float(amax) \
        and len(grid_w) == int(nst)
    # 跨来源：点数必须与日志 JSON 的 n_steps 一致
    json_nsteps = set()
    for c in list(ctx.w["cells"].values()) + list(ctx.r["cells"].values()):
        if c["json"] and "n_steps" in c["json"]:
            json_nsteps.add(c["json"]["n_steps"])
    nsteps_ok = (len(json_nsteps) == 1 and nst is not None
                 and int(nst) == list(json_nsteps)[0])
    ok = same_grid and src_ok and nsteps_ok
    cr.check("DQ-ALPHA", ok,
             "α 网格：w=linspace(%s,%s,%s) ｜ rand=linspace(%s,%s,%s) ｜ 逐位%s ｜ "
             "首末点与源码构造式%s ｜ 点数与日志 JSON 的 n_steps（%s）%s"
             % (grid_w[0] if grid_w else "?", grid_w[-1] if grid_w else "?",
                len(grid_w) if grid_w else 0,
                grid_r[0] if grid_r else "?", grid_r[-1] if grid_r else "?",
                len(grid_r) if grid_r else 0,
                "相同" if same_grid else "⛔不同",
                "一致" if src_ok else "⛔不一致", sorted(json_nsteps),
                "一致" if nsteps_ok else "⛔不一致"))
    res["alpha_max"] = float(amax) if amax else None
    res["n_steps"] = int(nst) if nst else None

    # ---- DQ-GAP：判决读数剂量（命令行 + 探针源码系数 + 日志 JSON 三源）----
    gap_c = fw.get("--gap")
    gap_r = fr.get("--gap")
    gap_w = float(gap_c) if gap_c else None
    gap_rr = float(gap_r) if gap_r else None
    ro_w = sorted([READOUT_COEF[0] * gap_w, READOUT_COEF[1] * gap_w]) if gap_w is not None else []
    ro_r = sorted([READOUT_COEF[0] * gap_rr, READOUT_COEF[1] * gap_rr]) if gap_rr is not None else []
    src_coef = src_readout_coef(ctx.probe_text)
    coef_ok = (src_coef is not None
               and abs(src_coef[0] - READOUT_COEF[0]) <= 1e-12
               and abs(src_coef[1] - READOUT_COEF[1]) <= 1e-12)
    json_gaps = set()
    for c in list(ctx.w["cells"].values()) + list(ctx.r["cells"].values()):
        if c["json"] and "gap" in c["json"]:
            json_gaps.add(c["json"]["gap"])
    three_src = (gap_w is not None and gap_w == gap_rr and ro_w == ro_r
                 and len(json_gaps) == 1 and abs(list(json_gaps)[0] - gap_w) <= 1e-12
                 and coef_ok)
    cr.check("DQ-GAP", three_src,
             "判决读数 α：w=%s ｜ rand=%s ｜ 命令行 gap %s/%s ｜ 探针源码系数 %s ｜ 日志 JSON gap=%s ⇒ %s"
             % (ro_w, ro_r, gap_c, gap_r, src_coef, sorted(json_gaps),
                "三源一致" if three_src else "⛔不一致"))
    res["gap"] = gap_w
    res["readout_alphas"] = ro_w
    res["src_coef"] = src_coef

    # ---- DQ-NSITES：位点数四源相同 --------------------------------------
    common = sorted(k for k in ctx.w["cells"] if k in ctx.r["cells"])
    ns_bad = []
    for k in common:
        cw_ = ctx.w["cells"][k]
        cr_ = ctx.r["cells"][k]
        a, b = cw_["n_sites"], cr_["n_sites"]
        c = cw_["json"].get("inject_n_sites")
        d = cr_["json"].get("inject_n_sites")
        row = ctx.cells.get(k)
        e = row["n_sites"] if row else None
        f = row["scope"] if row else None
        if not (a == b == c == d == e):
            ns_bad.append((k, a, b, c, d, e))
        if f is not None and f != cw_["scope"]:
            ns_bad.append((k, "scope", cw_["scope"], f))
    ok = (len(common) > 0) and (not ns_bad)
    cr.check("DQ-NSITES", ok,
             "逐格位点数/口径：BEGIN行 / JSON / cells 文件 / 两臂 **四源**一致 ｜ 比较格数 %d ｜ 不一致 %d 格%s"
             % (len(common), len(ns_bad), ("：%s" % ns_bad[:3]) if ns_bad else ""))
    res["n_common"] = len(common)
    res["nsites_bad"] = ns_bad

    # ---- DQ-KPOS：位点种子与源码一致 + 逐格位点集合两臂相同 -------------
    src_seed = src_k_seed(ctx.probe_text)
    seed_ok = (src_seed is not None and src_seed == spec["k_seed"])
    kp_bad, neff_bad = [], []
    for k in common:
        jw = ctx.w["cells"][k]["json"]
        jr = ctx.r["cells"][k]["json"]
        nw = int(jw["P"]) + int(jw["t"])
        nr = int(jr["P"]) + int(jr["t"])
        kw = ctx.w["cells"][k]["n_sites"]
        kr = ctx.r["cells"][k]["n_sites"]
        if k_positions(nw, kw, spec["k_seed"]) != k_positions(nr, kr, spec["k_seed"]):
            kp_bad.append(k)
        if nw != ctx.w["cells"][k]["n_eff"]:
            neff_bad.append((k, ctx.w["cells"][k]["n_eff"], nw))
    ok = seed_ok and (not kp_bad) and (not neff_bad) and len(common) > 0
    cr.check("DQ-KPOS", ok,
             "位点种子：实现用 %s ｜ 源码 `def _k_positions(..., seed=%s)` ⇒ %s ｜ "
             "逐格位点集合两臂%s ｜ n_eff 与 P+t 不符 %d 格"
             % (spec["k_seed"], src_seed, "一致" if seed_ok else "⛔不一致",
                "相同" if not kp_bad else "⛔不同", len(neff_bad)))
    res["kpos_bad"] = kp_bad
    res["src_seed"] = src_seed

    # ---- DQ-FIELDS：字段划分（预登记 §0.5 更正 ②）----------------------
    all_keys = set()
    for c in list(ctx.w["cells"].values()) + list(ctx.r["cells"].values()):
        if c["json"]:
            all_keys |= set(c["json"].keys())
    declared = set(STRUCT_FIELDS) | set(READOUT_FIELDS) | set(DEGENERATE_FIELDS) | {ARM_FIELD}
    missing = sorted(all_keys - declared)
    extra = sorted(declared - all_keys)
    complete = (not missing) and (not extra)
    cr.check("DQ-FIELDS-PART", complete,
             "字段划分完备：实测 %d 个 ｜ 声明 %d 个 ｜ 未声明 %d 个%s ｜ 声明了但实测没有 %d 个%s"
             % (len(all_keys), len(declared), len(missing),
                ("：%s" % missing) if missing else "", len(extra),
                ("：%s" % extra) if extra else ""))

    s_bad, compared = [], 0
    for k in common:
        jw = ctx.w["cells"][k]["json"]
        jr = ctx.r["cells"][k]["json"]
        for f in STRUCT_FIELDS:
            compared += 1
            if jw.get(f) != jr.get(f):
                s_bad.append((k, f, jw.get(f), jr.get(f)))
    cr.check("DQ-FIELDS-EQ", (not s_bad) and compared == len(common) * len(STRUCT_FIELDS),
             "S 内 %d 个结构字段逐格比较：实际比较 %d 次（应 %d）｜ 两臂不一致 %d 处%s"
             % (len(STRUCT_FIELDS), compared, len(common) * len(STRUCT_FIELDS),
                len(s_bad), ("：%s" % s_bad[:3]) if s_bad else ""))

    D = set()
    for k in common:
        jw = ctx.w["cells"][k]["json"]
        jr = ctx.r["cells"][k]["json"]
        for f in all_keys:
            if f == ARM_FIELD:
                continue
            if jw.get(f) != jr.get(f):
                D.add(f)
    # ⚖ 「第三处」：既不在 S、又不在读数/退化清单里的字段 ⇒ ⇒ 分类漏了 ⇒ 红
    third = sorted(f for f in all_keys
                   if f != ARM_FIELD and f not in STRUCT_FIELDS
                   and f not in READOUT_FIELDS and f not in DEGENERATE_FIELDS)
    # ⚖ 声明为读数、但**从不不同**、又不在退化清单 ⇒ ⇒ 它其实不是读数 ⇒ 红
    never = sorted(f for f in (set(READOUT_FIELDS) | set(DEGENERATE_FIELDS)) - D
                   if f not in DEGENERATE_FIELDS)
    degenerate_ok = True
    for f in DEGENERATE_FIELDS:
        vals = set()
        for k in common:
            vals.add(repr(ctx.w["cells"][k]["json"].get(f)))
            vals.add(repr(ctx.r["cells"][k]["json"].get(f)))
        if len(vals) != 1:
            degenerate_ok = False
    arm_ok = (bool(common)
              and ctx.w["cells"][common[0]]["json"].get(ARM_FIELD) == "w"
              and ctx.r["cells"][common[0]]["json"].get(ARM_FIELD) == "rand")
    cr.check("DQ-FIELDS-CLS", (not third) and (not never) and degenerate_ok and arm_ok,
             "实测差异字段 D（除 arm）共 %d 个 ｜ **落进第三处**（不在 S / 读数 / 退化）的字段：%d 个%s ｜ "
             "声明为读数但**从不不同**且不在退化清单：%d 个%s ｜ 退化字段是否全恒定：%s ｜ 两臂 arm 字段：%s"
             % (len(D), len(third), ("：%s" % third) if third else "",
                len(never), ("：%s" % never) if never else "",
                "是" if degenerate_ok else "⛔否", "w/rand 正确" if arm_ok else "⛔不对"))
    res["diff_fields"] = sorted(D)
    res["unexplained"] = never
    res["third_place"] = third

    # ---- DQ-INJECT：逐格注入总范数（两臂 + 公式/直接两条路径互证）--------
    amax_v = res.get("alpha_max") or 0.0
    inj_bad = []
    for k in common:
        kw = ctx.w["cells"][k]["n_sites"]
        kr = ctx.r["cells"][k]["n_sites"]
        iw = inject_total_formula(amax_v, w_norm, kw)
        ir = inject_total_formula(amax_v, r_norm, kr)
        if abs(iw - ir) > spec["inj_rel_tol"] * max(iw, 1e-300):
            inj_bad.append((k, iw, ir))
    # 跨路径：抽 N 格，用「真的把 k 份 α·v 加起来」对账
    path_bad = []
    for k in common[:int(spec["inj_direct_cells"])]:
        kw = ctx.w["cells"][k]["n_sites"]
        f_ = inject_total_formula(amax_v, w_norm, kw)
        d_ = inject_total_direct(amax_v, w64, kw)
        if abs(f_ - d_) > 1e-9 * max(abs(d_), 1e-300):
            path_bad.append((k, f_, d_))
    ok = (not inj_bad) and (not path_bad) and len(common) > 0
    cr.check("DQ-INJECT", ok,
             "逐格注入扰动总范数 = alpha_max(%s) × ∥v∥ × √k ｜ 两臂相对差超限的格 %d ｜ "
             "公式路径 vs 直接求和路径不一致 %d 格%s"
             % (amax_v, len(inj_bad), len(path_bad),
                ("：%s" % path_bad[:2]) if path_bad else ""))

    # ---- 未量到的格（⛔ 不当 0、不当失败）--------------------------------
    only_w = sorted(set(ctx.w["cells"]) - set(ctx.r["cells"]))
    only_r = sorted(set(ctx.r["cells"]) - set(ctx.w["cells"]))
    res["only_w"] = only_w
    res["only_r"] = only_r
    print("未量到：w 臂独有 %d 格%s ｜ rand 臂独有 %d 格%s ｜ 比较格数 %d（w 总 %d / rand 总 %d）"
          % (len(only_w), ("：%s" % only_w[:3]) if only_w else "",
             len(only_r), ("：%s" % only_r[:3]) if only_r else "",
             len(common), len(ctx.w["cells"]), len(ctx.r["cells"])))

    # ---- DQ-COS：余弦被量到 ---------------------------------------------
    cos0 = float(np.dot(w64.ravel(), r_vec.ravel()) / (w_norm * r_norm))
    ref = []
    d_ = int(w0.shape[0])
    for k in range(1, int(spec["cos_ref_seeds"]) + 1):
        g = np.random.default_rng(k)
        rr = g.standard_normal(w0.shape).astype(np.float64)
        rr = rr / np.linalg.norm(rr)
        ref.append(float(np.dot(w64.ravel(), rr.ravel()) / w_norm))
    mean = sum(ref) / len(ref)
    var = sum((x - mean) ** 2 for x in ref) / (len(ref) - 1)
    sd = math.sqrt(var)
    z = (cos0 - mean) / sd if sd > 0 else float("nan")
    rank = sum(1 for x in ref if x < cos0) / float(len(ref))
    theo = 1.0 / math.sqrt(float(d_))
    sd_rel = abs(sd - theo) / theo
    mods = sorted(set(ctx.r["mods"]))
    mod_ok = bool(mods) and abs(mods[0] - r_norm) <= 5e-4
    cos_ok = (len(ref) == int(spec["cos_ref_seeds"])) and mod_ok and (sd_rel <= spec["cos_sd_rel_tol"])
    cr.check("DQ-COS", cos_ok,
             "cos(w, rand_seed%d)=%.6f ｜ 参考分布 K=%d ｜ 经验秩=%.5f ｜ z=%.3f ｜ "
             "参考 sd=%.6f vs 理论 1/√%d=%.6f（相对差 %.3f）｜ 探针日志印的 mod=%s vs 重算 %.4f ⇒ %s"
             % (spec["k_seed"], cos0, len(ref), rank, z, sd, d_, theo, sd_rel,
                mods[0] if mods else "⛔无", r_norm, "跨来源一致" if mod_ok else "⛔不一致"))
    res["cos0"] = cos0
    res["cos_rank"] = rank
    res["cos_z"] = z
    res["cos_sd"] = sd
    res["cos_theo_sd"] = theo

    # ---- DQ-REMIX：残余混淆逐条在案 -------------------------------------
    remix_text = "\n".join("%s %s" % (t, x) for t, x in REMIX)
    miss_remix = [(t, kw) for t, kw in REMIX_REQUIRED if kw not in remix_text]
    cr.check("DQ-REMIX", not miss_remix,
             "残余混淆 %d 条 ｜ 必含关键词缺 %d 条%s"
             % (len(REMIX), len(miss_remix),
                ("：%s" % miss_remix) if miss_remix else ""))
    res["remix_text"] = remix_text

    # ---- DQ-VERDICT ------------------------------------------------------
    hard = ["DQ-ARTEFACT", "DQ-DTYPE", "DQ-SRC", "DQ-NORM", "DQ-NORM16", "DQ-ALPHA", "DQ-GAP",
            "DQ-NSITES", "DQ-KPOS", "DQ-FIELDS-PART", "DQ-FIELDS-EQ", "DQ-FIELDS-CLS",
            "DQ-CMD", "DQ-INJECT"]
    failed = cr.failed_ids()
    hard_failed = [h for h in hard if h in failed]
    verdict = "D-B" if hard_failed else "D-A"
    cr.check("DQ-VERDICT", verdict in ("D-A", "D-B", "D-C"),
             "判决形态 = %s（硬判据 %d 条，红 %d 条：%s）"
             % (verdict, len(hard), len(hard_failed), hard_failed))
    res["hard"] = hard
    res["hard_failed"] = hard_failed
    res["verdict"] = verdict
    return verdict, res


# =============================================================================
# 自检（G0-1：合成夹具，零 bpath、零 GPU）
# =============================================================================

FAKE_PROBE = '''#!/usr/bin/env python3
import numpy as np
import torch

MODEL = "fake"
# ⚖ 与真实探针同形的一行（`from_pretrained(MODEL, torch_dtype=torch.bfloat16)`）⇒ ⇒ DQ-DTYPE 能读到
_MODEL_KW = dict(torch_dtype=torch.bfloat16)


def _k_positions(n, k, seed=0, nested=False):
    import numpy as _np
    n, k = int(n), int(k)
    _rng = _np.random.default_rng(int(seed))
    if nested:
        return sorted(int(x) for x in _rng.permutation(n)[:k])
    return sorted(_rng.choice(n, size=k, replace=False).tolist())


def inject_at(h, v, alpha, scope, inj, n_sites=None, nested=False):
    h = h.clone() if hasattr(h, "clone") else h.copy()
    if scope == "k":
        pos = _k_positions(h.shape[1], n_sites, nested=nested)
        out = h.copy() if hasattr(h, "copy") else h.clone()
        for j in pos:
            out[:, j, :] = out[:, j, :] + alpha * v
        return out
    return h


def run(a):
    model = torch.nn.Linear(4, 4)
    model = model.to(torch.bfloat16)
    _W0 = np.load(a.w)
    W = _W0
    if a.arm == "rand":
        _g = np.random.default_rng(0)
        W = _g.standard_normal(_W0.shape).astype(np.float64)
        W = (W / np.linalg.norm(W)) * float(np.linalg.norm(_W0))
        print("[臂] 用固定种子随机方向（mod=%.4f，与 w 同模长）"
              % float(np.linalg.norm(W)), flush=True)
    alphas = np.linspace(-a.alpha_max, a.alpha_max, a.n_steps)
    v = torch.as_tensor(vec, dtype=h.dtype, device=h.device)
    for _lab, _al in (("lo", 0.5 * a.gap), ("hi", 1.0 * a.gap)):
        pass
    return alphas


model = torch.nn.Linear(4, 4)
model = model.to(torch.bfloat16)
'''


FAKE_RUNNER = '''#!/bin/bash
set -u
B=/home/zhourui/steer3d_bpath
GPU_UUID=${1:?usage}
CELLS=${2:?usage}
NMAP=${3:?usage}
EXPECT_CELLS=${4:-137}
TAG=${5:-}
ARM=${6:-w}
POS_FRAC_DEFAULT=${7:-0.5}
W_PATH=${8:-/tmp/w_p2a.npy}
C="--cell --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w $W_PATH --gap 113.47440338134766 --n-steps 60 --alpha-max 120 --band 60 --gpu-uuid $GPU_UUID --arm $ARM --inject-nested"
'''

FAKE_STRUCT = {
    "P": 112, "gap": 113.47440338134766, "inject_n_sites": 75, "inject_nested": True,
    "inject_scope": "k", "n_gen": 757, "n_steps": 60, "pos_frac": 0.25,
    "rep_n_hi": 1, "rep_n_lo": 1, "t": 189, "tid": "aime__aime25__p00__no_think",
}
FAKE_READOUT = {
    "b_ctl": 7.28125, "b_mark": -0.34281498193740845, "ctl_min_adj_diff": 0.03125,
    "ctl_n_distinct": 21, "dm_max": 0.38810935243964195, "dm_min": -0.19684386253356934,
    "fit_err_hi": -0.04793282904959731, "fit_err_hi_sigma": -0.6542642811538603,
    "fit_err_lo": 0.0469611808223674, "lin_ratio": 1.296268759613757,
    "margin_meas": 2.6148983260804486, "marker_raw_hi": -0.09853832423686981,
    "marker_raw_lo": -0.2901114821434021, "min_adj_diff": 0.00023090839385986328,
    "n_distinct": 60, "p9_hi": 0.19634382865094133, "p9_hi_meas": 0.24427665770053864,
    "p9_lo": 0.09966468061637375, "p9_lo_meas": 0.05270349979400635,
    "p9_margin_se": 1.2817943096109226, "p9_se_hi": 0.07542485351172583,
    "p9_se_lo": 0.0742618979841681, "p9_up_mono": True,
    "rep_mean_hi": 0.24427665770053864, "rep_mean_lo": 0.05270349979400635,
    "resid_std": 0.07326218231730913, "resid_std_local": 0.05651774122762838,
    "slope": 0.0017039816056077927, "slope_local": 0.001125069290142635,
    "up_mono_meas": True,
}
FAKE_DEGEN = {"rep_exact_hi": True, "rep_exact_lo": True, "rep_spread_hi": 0.0,
              "rep_spread_lo": 0.0, "rep_std_hi": None, "rep_std_lo": None}


def fake_json(arm, st):
    d = dict(st)
    d.update(FAKE_READOUT)
    d.update(FAKE_DEGEN)
    d["arm"] = arm
    # ⛔ 读数字段必须**两臂不同**（否则 DQ-FIELDS-CLS 会把它们当成结构字段）
    for f in ("slope", "resid_std", "p9_lo_meas", "p9_hi_meas", "up_mono_meas",
              "b_mark", "rep_mean_lo", "rep_mean_hi", "n_distinct", "dm_min",
              "b_ctl", "dm_max", "lin_ratio", "p9_lo", "p9_hi", "resid_std_local",
              "slope_local", "margin_meas", "marker_raw_hi", "marker_raw_lo",
              "min_adj_diff", "p9_se_lo", "p9_se_hi", "p9_margin_se",
              "fit_err_lo", "fit_err_hi", "fit_err_hi_sigma", "ctl_min_adj_diff",
              "ctl_n_distinct", "p9_up_mono"):
        if d.get(f) is not None:
            d[f] = d[f] * (1.0 if arm == "w" else -1.0)
    return d


def write_fake_log(path, arm, n_cells=3, gpu="GPU-fake"):
    lines = []
    lines.append("PINNED GPU=%s  CELLS=/home/zhourui/steer3d_bpath/warm_cells_fixed_dose.tsv  "
                 "NMAP=/home/zhourui/steer3d_bpath/n_eff_map  POS_FRAC_DEFAULT=0.5  "
                 "EXPECT_CELLS=%d  TAG=_fd_%s  ARM=%s  "
                 "W_PATH=/home/zhourui/steer3d_bpath/w_p2a.npy  11:17:36" % (gpu, n_cells, arm, arm))
    lines.append("CELLS header=header4  header_nf=4  data_rows=%d  11:17:36" % n_cells)
    lines.append("NMAP rows=180 md5=3b9b4cdb9f3d3300b7bf30ce268d2846  11:17:36")
    for i in range(n_cells):
        pf = (0.25, 0.5, 0.75)[i % 3]
        tid = "aime__aime25__p00__no_think"
        st = dict(FAKE_STRUCT)
        st["pos_frac"] = pf
        st["t"] = int(757 * pf)
        st["inject_n_sites"] = 75 + i
        st["tid"] = tid
        d = fake_json(arm, st)
        n = int(d["P"]) + int(d["t"])
        lines.append("### BEGIN %s [%d/%d] n_eff=%d --inject-scope %s --inject-n-sites %d  11:17:37"
                     % (tid, i + 1, n_cells, n, d["inject_scope"], d["inject_n_sites"]))
        if arm == "rand":
            lines.append("[臂] 用固定种子随机方向（mod=1.0000，与 w 同模长）")
        lines.append("RESULT r204_cell  %s pos=%.2f" % (tid, pf))
        lines.append(json.dumps(d, sort_keys=True))
        lines.append("### END   [%d/%d] %s rc=0  11:21:50" % (i + 1, n_cells, tid))
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def build_fake(tmpdir, n_cells=3):
    """⚖ 造一套**自洽**的合成产物（w 臂与 rand 臂各一份）。"""
    paths = {"w_log": os.path.join(tmpdir, "w.log"),
             "rand_log": os.path.join(tmpdir, "rand.log"),
             "runner": os.path.join(tmpdir, "runner.sh"),
             "probe": os.path.join(tmpdir, "probe.py"),
             "w_npy": os.path.join(tmpdir, "w_p2a.npy"),
             "cells": os.path.join(tmpdir, "cells.tsv")}
    write_fake_log(paths["w_log"], "w", n_cells)
    write_fake_log(paths["rand_log"], "rand", n_cells)
    with io.open(paths["runner"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(FAKE_RUNNER)
    with io.open(paths["probe"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(FAKE_PROBE)
    rng = np.random.default_rng(7)
    v = rng.standard_normal(64).astype(np.float64)
    v = (v / np.linalg.norm(v)).astype(np.float32)
    np.save(paths["w_npy"], v)
    with io.open(paths["cells"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write("tid\tscope\tn_sites\tpos_frac\n")
        for i in range(n_cells):
            pf = (0.25, 0.5, 0.75)[i % 3]
            fh.write("aime__aime25__p00__no_think\tk\t%d\t%.2f\n" % (75 + i, pf))
    return paths


def selftest():
    """⚖ G0-1：合成夹具 ⇒ ① 全绿 ② 逐个注入缺陷 ⇒ 对应判据必须红。"""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="_de_selftest_")
    try:
        paths = build_fake(tmp)
        # ⚖ 夹具不是真产物 ⇒ 它的 md5 **必须**换成夹具自己的 ⇒ ⇒ 否则 DQ-ARTEFACT 会恒红
        spec_fake = dict(SPEC)
        for _k, _sk in (("w_log", "w_log_md5"), ("rand_log", "rand_log_md5"),
                        ("runner", "runner_md5"), ("probe", "probe_md5"),
                        ("w_npy", "w_npy_md5"), ("cells", "cells_md5")):
            spec_fake[_sk] = md5_of(paths[_k])
        cr = Criteria()
        # ⚖⚖⚖ 夹具的 md5 覆盖放在**最外层** ⇒ ⇒ 缺陷注入的 `_Ov(SPEC=...)` 嵌套在**里面**
        #    ⇒ ⇒ **内层赢** ⇒ ⇒ 缺陷改的正是**同一个** SPEC ⇒ ⇒ 才抓得到
        #    ⇒ ⇒ 且**不再**按副本重算 md5（重算会把「登记值被改」这条缺陷中和掉）
        with _Ov(SPEC=spec_fake):
            v, _res = evaluate(Ctx(**paths), SPEC, cr)
            print("")
            print("自检①（无缺陷）：判决形态 = %s ｜ 判据 %d 条 ｜ FAIL %d 条"
                  % (v, len(cr.items), cr.fail_count()))
            if cr.fail_count() != 0:
                print("⛔ 自检① 不过 ⇒ 有恒红的判据 ⇒ 硬停")
                return 1

            defects = [
                ("范数不等（rand 不归一）", "DQ-NORM", _ov_rand_notnorm),
                ("α 网格构造错（起点不是 -alpha_max）", "DQ-ALPHA", _ov_grid_wrong),
                ("判决读数系数错（0.5/1.0 → 0.25/2.0）", "DQ-GAP", _ov_coef_wrong),
                ("位点数不等（w 臂一格被改）", "DQ-NSITES", _patch_nsites),
                ("位点种子错（0 → 1）", "DQ-KPOS", _ov_seed_wrong),
                ("字段划分漏项（拿掉 pos_frac）", "DQ-FIELDS-CLS", _ov_struct_drop),
                ("命令行多一个不同（rand 臂换另一把向量）", "DQ-CMD", _patch_band),
                ("注入总范数公式漏 √k", "DQ-INJECT", _ov_inj_formula),
                ("dtype 不符（源码写 float32）", "DQ-DTYPE", _patch_dtype),
                ("源码事实缺一条（linspace 那行）", "DQ-SRC", _patch_src_linspace),
                ("跨来源 mod 对不上（印 1.5）", "DQ-COS", _patch_mod),
                ("残余混淆漏一条", "DQ-REMIX", _ov_remix_drop),
                ("产物 md5 对不上（登记值被改）", "DQ-ARTEFACT", _ov_artifact_md5),
            ]
            bad = []
            for desc, want, patch in defects:
                d2 = tempfile.mkdtemp(prefix="_de_def_")
                try:
                    p2 = {}
                    for k in paths:
                        dst = os.path.join(d2, os.path.basename(paths[k]))
                        shutil.copyfile(paths[k], dst)
                        p2[k] = dst
                    with patch(p2):
                        cr2 = Criteria()
                        evaluate(Ctx(**p2), SPEC, cr2)
                    red = cr2.failed_ids()
                    if want in red:
                        print("  [红] %-34s ⇒ %s 红（同时红了：%s）"
                              % (desc, want, ",".join(sorted(red))))
                    else:
                        print("  [❌] %-34s ⇒ **%s 没红**（红的是：%s）⇒ 判据没牙齿"
                              % (desc, want, ",".join(sorted(red))))
                        bad.append((desc, want))
                finally:
                    shutil.rmtree(d2, ignore_errors=True)
        print("")
        print("自检②（注入缺陷 %d 个）：抓到 %d ｜ 没抓到 %d"
              % (len(defects), len(defects) - len(bad), len(bad)))
        for desc, want in bad:
            print("  [没抓到] %s ⇒ 期望 %s 红" % (desc, want))
        return 0 if not bad else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- 自检用的缺陷注入（每个只改**一处**）-------------------------------


class _NullOv(object):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _ov_rand_notnorm(p):
    def bad(w0, seed):
        g = np.random.default_rng(int(seed))
        return g.standard_normal(w0.shape).astype(np.float64)
    return _Ov(rand_direction=bad)


def _ov_grid_wrong(p):
    orig = linspace
    def bad(start, stop, num):
        return orig(0.0, stop, num)
    return _Ov(linspace=bad)


def _ov_coef_wrong(p):
    return _Ov(READOUT_COEF=(0.25, 2.0))


def _ov_seed_wrong(p):
    sp = dict(SPEC)
    sp["k_seed"] = 1
    return _Ov(SPEC=sp)


def _ov_struct_drop(p):
    return _Ov(STRUCT_FIELDS=tuple(f for f in STRUCT_FIELDS if f != "pos_frac"))


def _ov_inj_formula(p):
    def bad(alpha_max, vnorm, k):
        return float(alpha_max) * float(vnorm) * float(k)
    return _Ov(inject_total_formula=bad)


def _ov_remix_drop(p):
    return _Ov(REMIX=REMIX[:3])


def _ov_artifact_md5(p):
    """⚖ 改**登记的**向量 md5 ⇒ ⇒ 产物与登记对不上 ⇒ ⇒ DQ-ARTEFACT 必须红。"""
    sp = dict(SPEC)
    sp["w_npy_md5"] = "0" * 32
    return _Ov(SPEC=sp)


def _patch_nsites(p):
    """⚖ w 臂日志里改一格的 inject_n_sites ⇒ ⇒ 四源不再一致。"""
    with io.open(p["w_log"], encoding="utf-8") as fh:
        t = fh.read()
    t = t.replace('"inject_n_sites": 76', '"inject_n_sites": 77', 1)
    t = t.replace("--inject-n-sites 76", "--inject-n-sites 77", 1)
    with io.open(p["w_log"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(t)
    return _NullOv()


def _patch_band(p):
    """⚖ **rand 臂的 `--w` 指向另一把向量** ⇒ ⇒ 两臂命令行出现第二处不同
       ⇒ ⇒ 这正是「两臂只差一个变量」会被破掉的真实场景 ⇒ ⇒ DQ-CMD 必须红。"""
    with io.open(p["rand_log"], encoding="utf-8") as fh:
        t = fh.read()
    t = t.replace("W_PATH=/home/zhourui/steer3d_bpath/w_p2a.npy",
                  "W_PATH=/home/zhourui/steer3d_bpath/w_other.npy")
    with io.open(p["rand_log"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(t)
    return _NullOv()


def _patch_dtype(p):
    with io.open(p["probe"], encoding="utf-8") as fh:
        t = fh.read()
    t = t.replace("torch.bfloat16", "torch.float32")
    with io.open(p["probe"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(t)
    return _NullOv()


def _patch_src_linspace(p):
    with io.open(p["probe"], encoding="utf-8") as fh:
        t = fh.read()
    t = t.replace("alphas = np.linspace(-a.alpha_max, a.alpha_max, a.n_steps)",
                  "alphas = np.arange(a.n_steps)")
    with io.open(p["probe"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(t)
    return _NullOv()


def _patch_mod(p):
    """⚖ rand 臂日志里探针印的 mod 改成别的数 ⇒ ⇒ 跨来源对不上。"""
    with io.open(p["rand_log"], encoding="utf-8") as fh:
        t = fh.read()
    t = t.replace("mod=1.0000", "mod=1.5000")
    with io.open(p["rand_log"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(t)
    return _NullOv()


# =============================================================================
# 主流程
# =============================================================================


def print_spec():
    for k in sorted(SPEC):
        print("SPEC %s = %r" % (k, SPEC[k]))
    print("SPEC struct_fields = %r" % (STRUCT_FIELDS,))
    print("SPEC readout_fields = %r" % (READOUT_FIELDS,))
    print("SPEC degenerate_fields = %r" % (DEGENERATE_FIELDS,))
    print("SPEC readout_coef = %r" % (READOUT_COEF,))
    print("SPEC remix_required = %r" % (REMIX_REQUIRED,))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--print-spec", action="store_true")
    ap.add_argument("--bpath", default=os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath"))
    ap.add_argument("--w-log", default=None)
    ap.add_argument("--rand-log", default=None)
    ap.add_argument("--runner", default=None)
    ap.add_argument("--probe", default=None)
    ap.add_argument("--w-npy", default=None)
    ap.add_argument("--cells", default=None)
    args = ap.parse_args()

    if args.print_spec:
        print_spec()
        return 0

    if args.selftest:
        return selftest()

    b = args.bpath
    paths = {
        "w_log": args.w_log or os.path.join(b, "r244_warm_fd_w.log"),
        "rand_log": args.rand_log or os.path.join(b, "r244_warm_fd_rand.log"),
        "runner": args.runner or os.path.join(b, "r244_warm_sweep.sh"),
        "probe": args.probe or os.path.join(b, "r241_probe.py"),
        "w_npy": args.w_npy or os.path.join(b, "w_p2a.npy"),
        "cells": args.cells or os.path.join(b, "warm_cells_fixed_dose.tsv"),
    }
    print("=== 剂量等值性核查（244.83）｜ bpath=%s ===" % b)
    print("产物 md5：w_log=%s ｜ rand_log=%s ｜ runner=%s ｜ probe=%s ｜ w_npy=%s ｜ cells=%s"
          % tuple(md5_of(paths[k]) for k in
                  ("w_log", "rand_log", "runner", "probe", "w_npy", "cells")))
    cr = Criteria()
    verdict, res = evaluate(Ctx(**paths), SPEC, cr)
    print("")
    print("—— 残余混淆（Q12，**必须逐条在案**）——")
    print(res.get("remix_text", ""))
    print("")
    print("VERDICT=%s" % verdict)
    print("判据汇总：%d 条 ｜ PASS %d ｜ FAIL %d"
          % (len(cr.items), len(cr.items) - cr.fail_count(), cr.fail_count()))
    return 0 if cr.fail_count() == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
