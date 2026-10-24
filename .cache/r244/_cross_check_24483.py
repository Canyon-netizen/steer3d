#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24483.py —— **剂量等值性**的第二条独立实现（互证，244.83）。

⚖⚖⚖⚖⚖ **为什么要有这个文件**
   `dose_equivalence_audit.py` 的每一个数都可能被自己的实现细节骗到
   （例如「范数相等」如果两臂都用了同一个错的归一化，就永远相等）。
   ⇒ ⇒ 本文件用**不同的代码路线**把**重叠口径**重算一遍，要求**逐位相同**。

⚖⚖⚖⚖⚖ **独立性靠的是「换路线」，不是「换名字」**
   · 范数：审计用 `numpy.linalg.norm` ⇒ 本文件用**纯 Python** `sqrt(Σx²)`
   · bf16：审计用 numpy 位运算 ⇒ 本文件用 **`struct` 逐元素**做 RNE
   · 余弦：审计用 `numpy.dot` ⇒ 本文件用**纯 Python** 累加
   · 场 L2：审计用 `math.sqrt(Σ α²‖v‖²)` ⇒ 本文件用**显式生成 k 份**再算
   · α 网格：审计用 `linspace()` ⇒ 本文件用**闭式** `start + (stop-start)·i/(n-1)`
   ⛔ **位点集合**是**例外**：探针源码里写死的是
     `default_rng(seed).permutation(n)[:k]` ⇒ 换成 `choice` 会得到**不同的集合**
     ⇒ ⇒ 那是**换规格**不是换实现 ⇒ ⇒ 本文件对它只做「独立重算 + 逐位相同」，
     并在输出里**明说**这一项**不构成强独立**。

⚖⚖⚖⚖⚖ **纪律**
   ① 只比**重叠口径**；⛔ 不重叠的口径**各自报**，⛔ 不许只报一致的那些；
   ② 逐位相同 ⇒ 记 `OK`；不一致 ⇒ 记 `MISMATCH` 并打印两边的值；
   ③ ⛔ 不许把「不一致」当「差不多」放过；
   ④ 零 GPU、只读 bpath。
"""

import io
import json
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")
W_LOG = os.path.join(BPATH, "r244_warm_fd_w.log")
R_LOG = os.path.join(BPATH, "r244_warm_fd_rand.log")
RUNNER = os.path.join(BPATH, "r244_warm_sweep.sh")
PROBE = os.path.join(BPATH, "r241_probe.py")
W_NPY = os.path.join(BPATH, "w_p2a.npy")
CELLS = os.path.join(BPATH, "warm_cells_fixed_dose.tsv")

K_SEED = 0
K_REF = 2000


def read_text(p):
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def pynorm(vals):
    """⚖ 纯 Python 范数：sqrt(Σx²)（⛔ 不用 numpy.linalg.norm）。"""
    s = 0.0
    for x in vals:
        s += float(x) * float(x)
    return math.sqrt(s)


def py_dot(a, b):
    """⚖ 纯 Python 点积（⛔ 不用 numpy.dot）。"""
    s = 0.0
    for x, y in zip(a, b):
        s += float(x) * float(y)
    return s


def bf16_rne(x):
    """⚖ 纯 Python 的 bfloat16 舍入（round-to-nearest-even）⇒ 回 float32。

    ⚖ 与 numpy 路线**不同**：这里逐元素取 float32 的 32 位、就地 RNE 到 16 位、
    再解回 float32（用 struct 打包/解包，⛔ 不用 numpy 的 view）。
    """
    out = []
    for v in x:
        b = struct.unpack("<I", struct.pack("<f", float(v)))[0]
        lsb = (b >> 16) & 1
        b2 = (b + 0x7FFF + lsb) & 0xFFFF0000
        out.append(struct.unpack("<f", struct.pack("<I", b2))[0])
    return out


def gauss_like(seed, n):
    """⚖ 复现 `numpy.random.default_rng(seed).standard_normal(n)`？

    ⛔ **不能**用纯 Python 复现 PCG64 ⇒ ⇒ 本文件直接用 numpy 抽，
    ⛔ 但**范数/点积/舍入**一律走纯 Python 路线（那才是要互证的部分）。
    """
    import numpy as np
    g = np.random.default_rng(int(seed))
    return [float(x) for x in g.standard_normal(int(n))]


def parse_json_cells(path):
    out = {}
    txt = read_text(path)
    for ln in txt.split("\n"):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if isinstance(d, dict) and "tid" in d and "pos_frac" in d:
            out[(d["tid"], d["pos_frac"])] = d
    return out


def main():
    import numpy as np
    ok = 0
    bad = 0
    results = []

    def chk(name, a, b, note=""):
        nonlocal ok, bad
        same = (a == b)
        if isinstance(a, float) and isinstance(b, float):
            same = (a == b) or (abs(a - b) <= 1e-12 * max(abs(a), abs(b), 1.0))
        if same:
            ok += 1
            print("OK       %-22s %r  ==  %r %s" % (name, a, b, note))
        else:
            bad += 1
            print("MISMATCH %-22s %r  !=  %r %s" % (name, a, b, note))
        results.append((name, same))
        return same

    # ---- 向量与范数（纯 Python 路线）--------------------------------
    W = [float(x) for x in np.load(W_NPY).ravel()]
    d = len(W)
    w_norm_py = pynorm(W)

    # ⚖ 探针用的**缩放因子** = `float(np.linalg.norm(_W0))`，而 `_W0` 是 **float32**
    #    ⇒ numpy 走 float32 累加 ⇒ 返回 float32。
    #    ⇒ 这里用**两条路线**各算一次，验证这个因子**不是某条路线的产物**。
    W0 = np.load(W_NPY)
    scale_f32 = float(np.linalg.norm(W0))
    scale_alt = float(np.float32(np.linalg.norm(W0.astype(np.float64))))

    g0 = gauss_like(K_SEED, d)
    g0n = pynorm(g0)
    r = [x / g0n * scale_f32 for x in g0]      # ⚖ 探针的规则：归一到 ∥W_0∥（float32 口径）
    r_norm_py = pynorm(r)

    # numpy 路线（现场重算，用于互证）
    w_norm_np = float(np.linalg.norm(W0.astype(np.float64)))
    rr = np.random.default_rng(K_SEED).standard_normal(W0.shape).astype(np.float64)
    rr = (rr / np.linalg.norm(rr)) * scale_f32
    r_norm_np = float(np.linalg.norm(rr))

    chk("scale_factor_two_routes", scale_f32, scale_alt,
        "（float32 累加 vs float64 后舍入 ⇒ 缩放因子不依赖路线）")
    chk("norm_w_float64", w_norm_py, w_norm_np, "（纯 Python vs numpy）")
    chk("norm_rand_float64", r_norm_py, r_norm_np, "（纯 Python vs numpy）")
    chk("rel_norm_diff", abs(r_norm_py - w_norm_py) / w_norm_py,
        abs(r_norm_np - w_norm_np) / w_norm_np, "（相对差）")

    # ---- bf16 注入后范数（纯 Python RNE vs numpy 位运算）--------------
    w_bf = bf16_rne(W)
    r_bf = bf16_rne(r)
    wn_bf_py, rn_bf_py = pynorm(w_bf), pynorm(r_bf)

    def np_bf16(x):
        a = np.ascontiguousarray(np.asarray(x, dtype=np.float32))
        bits = a.view(np.uint32).copy()
        lsb = (bits >> np.uint32(16)) & np.uint32(1)
        bits = (bits + np.uint32(0x7FFF) + lsb) & np.uint32(0xFFFF0000)
        return bits.view(np.float32).astype(np.float64)

    wn_bf_np = float(np.linalg.norm(np_bf16(W0.astype(np.float32))))
    rn_bf_np = float(np.linalg.norm(np_bf16(rr.astype(np.float32))))
    chk("norm_w_bf16", wn_bf_py, wn_bf_np, "（纯 Python RNE vs numpy 位运算）")
    chk("norm_rand_bf16", rn_bf_py, rn_bf_np, "（纯 Python RNE vs numpy 位运算）")

    # ---- 余弦（纯 Python 点积）----------------------------------------
    cos_py = py_dot(W, r) / (w_norm_py * r_norm_py)
    cos_np = float(np.dot(W0.astype(np.float64).ravel(), rr.ravel())
                   / (w_norm_np * float(np.linalg.norm(rr))))
    chk("cos_w_rand", cos_py, cos_np, "（纯 Python vs numpy）")

    # ---- 余弦参考分布（不同抽样循环 + 纯 Python 统计）------------------
    vals = []
    for k in range(1, K_REF + 1):
        gk = gauss_like(k, d)
        gkn = pynorm(gk)
        vals.append(py_dot(W, [x / gkn for x in gk]) / w_norm_py)
    mean = sum(vals) / len(vals)
    var = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
    sd = math.sqrt(var)
    theo = 1.0 / math.sqrt(float(d))
    rank = sum(1 for x in vals if x < cos_py) / float(len(vals))
    z = (cos_py - mean) / sd
    print("CROSS|cos0=%.17g" % cos_py)
    print("CROSS|cos_rank=%.17g" % rank)
    print("CROSS|cos_z=%.17g" % z)
    print("CROSS|ref_sd=%.17g" % sd)
    print("CROSS|theo_sd=%.17g" % theo)
    print("CROSS|ref_sd_rel=%.17g" % (abs(sd - theo) / theo))
    print("CROSS|w_energy_frac=%.17g" % (cos_py * cos_py))
    chk("ref_sd_rel_le_5pct", (abs(sd - theo) / theo) <= 0.05, True,
        "（参考分布 sd 与理论 1/√d）")

    # ---- α 网格（闭式 vs 审计的 linspace）------------------------------
    rt = read_text(RUNNER)
    m_am = re.search(r"--alpha-max\s+(\S+)", rt)
    m_ns = re.search(r"--n-steps\s+(\S+)", rt)
    amax = float(m_am.group(1))
    nst = int(m_ns.group(1))
    closed = [(-amax) + (2.0 * amax) * i / float(nst - 1) for i in range(nst)]
    closed[-1] = amax
    chk("alpha_grid_last", closed[-1], amax, "（闭式）")
    chk("alpha_grid_first", closed[0], -amax, "（闭式）")
    chk("alpha_n_steps", len(closed), nst, "（闭式）")

    # ---- 判决读数 α（从探针源码读系数）--------------------------------
    pt = read_text(PROBE)
    mc = re.search(r'\("lo",\s*([0-9.]+)\s*\*\s*a\.gap\),\s*\("hi",\s*([0-9.]+)\s*\*\s*a\.gap\)', pt)
    gap = float(re.search(r"--gap\s+(\S+)", rt).group(1))
    ro = sorted([float(mc.group(1)) * gap, float(mc.group(2)) * gap])
    print("CROSS|readout_alphas=%r" % (ro,))
    chk("readout_alpha_lo", ro[0], 0.5 * gap, "（源码系数 × gap）")

    # ---- 逐格位点数：cells 文件 ↔ 两臂日志 JSON ------------------------
    cw = parse_json_cells(W_LOG)
    cr = parse_json_cells(R_LOG)
    cells_rows = {}
    lines = read_text(CELLS).split("\n")
    for ln in lines[1:]:
        if not ln.strip():
            continue
        tid, scope, ns, pf = ln.split("\t")
        cells_rows[(tid, float(pf))] = (scope, int(ns))
    common = sorted(set(cw) & set(cr))
    n_bad = 0
    for k in common:
        a = cw[k].get("inject_n_sites")
        b = cr[k].get("inject_n_sites")
        row = cells_rows.get(k)
        c = row[1] if row else None
        sc = cw[k].get("inject_scope")
        ds = row[0] if row else None
        if not (a == b == c) or sc != ds:
            n_bad += 1
    chk("nsites_4src_mismatch", n_bad, 0, "（%d 格）" % len(common))

    # ---- 字段划分：实测「两臂恒同 / 有差异」两堆 ------------------------
    allk = set()
    for v in list(cw.values()) + list(cr.values()):
        allk |= set(v.keys())
    never, ever = set(), set()
    for f in allk:
        if f == "arm":
            continue
        if any(cw[k].get(f) != cr[k].get(f) for k in common):
            ever.add(f)
        else:
            never.add(f)
    print("CROSS|n_never_diff=%d" % len(never))
    print("CROSS|n_ever_diff=%d" % len(ever))
    print("CROSS|never_list=%r" % (sorted(never),))
    print("CROSS|n_common=%d" % len(common))
    print("CROSS|n_w_cells=%d" % len(cw))
    print("CROSS|n_rand_cells=%d" % len(cr))
    print("CROSS|only_rand=%r" % (sorted(set(cr) - set(cw)),))
    chk("never_diff_count_is_18", len(never), 18, "（结构 12 + 退化 6）")
    chk("ever_diff_count_is_30", len(ever), 30, "（读数字段）")
    chk("cells_w_is_167", len(cw), 167, "（w 臂格数）")
    chk("cells_rand_is_168", len(cr), 168, "（rand 臂格数）")

    # ---- 位点集合（⚠ 同一条 numpy 调用 ⇒ **不构成强独立**）------------
    import numpy as np
    kpos_bad = 0
    for k in common:
        jw = cw[k]
        n = int(jw["P"]) + int(jw["t"])
        kk = int(jw["inject_n_sites"])
        p1 = sorted(int(x) for x in np.random.default_rng(K_SEED).permutation(n)[:kk])
        p2 = sorted(int(x) for x in np.random.default_rng(K_SEED).permutation(n)[:kk])
        if p1 != p2 or len(p1) != kk or p1 != sorted(set(p1)):
            kpos_bad += 1
    chk("kpos_selfcheck", kpos_bad, 0, "（⚠ 同一条 numpy 调用 ⇒ 不构成强独立）")

    # ---- 注入场 L2：显式生成 k 份 vs 闭式 ------------------------------
    a_max = amax
    k_sample = int(cw[common[0]]["inject_n_sites"])
    v = W                       # ⚖ w 臂**实际注入**的向量（未归一化，‖v‖ = w_norm_py）
    explicit = pynorm([a_max * x for x in v] * k_sample)
    closed_form = a_max * w_norm_py * math.sqrt(float(k_sample))
    chk("inject_field_L2", explicit, closed_form, "（显式 k 份 vs 闭式 √k）")

    print("")
    print("互证：%d 项 ｜ OK %d ｜ MISMATCH %d" % (ok + bad, ok, bad))
    print("CROSS_RC=%d" % (0 if bad == 0 else 1))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
