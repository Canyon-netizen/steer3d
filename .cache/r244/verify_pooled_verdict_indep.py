#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_pooled_verdict_indep.py —— 固定剂量「合池判决层」判决的**独立重算器**。

⚖⚖⚖ **为什么要有这个工具（244.81）**

  244.81 的判决面板是**分析器自己算自己印**的（`fixed_dose_pooled_verdict_audit.py`）
  ⇒ ⇒ 「印出来的数」与「返回的数」一致（V-P16）只保证**自洽**，
  ⛔ **不保证算对** ⇒ ⇒ 需要**第二条独立实现**把面板上的每个数**重算一遍**。

⚖⚖⚖ **独立性的三条硬规矩（⛔ 破一条，这条判据就作废）**

  ① ⛔ **不 import 那个分析器**、⛔ 不 import 权威读数器（`r227_kcurve.py`）、
     ⛔ 不 import 拆分器（`fixed_dose_split_log.py`）⇒ ⇒ **数据路径也不共用**：
     本工具**自己解析原始跑批日志**（`r244_warm_fd_{w,rand}.log`），
     ⛔ 不读拆分产物 ⇒ ⇒ 连「拆分器有没有改格」这条也一起独立验掉。
  ② ⛔ **统计量自己实现**：Wilson / Newcombe / Fisher / 置换检验
     ⇒ ⇒ **不调用** `interval_audit` / `arm_verdict` / `dose_layer_audit`
     ⇒ ⇒ 同口径（口径是预登记写死的）但**不同实现** ⇒ ⇒ 两端不同源。
  ③ ⚖ **置换检验用二项精确**（`Binom(k,0.5)` 直算）⇒ ⇒ 分析器那边是
     Monte Carlo（`n_perm=20000`）⇒ ⇒ 我这边**不是同一个随机数** ⇒ ⇒
     两条路给出**同一个 p** 才算对上；差得远就是有一边错了。

⚖⚖⚖ **判决只算一次**

  本工具**不产生第二个判决数**：它把**面板上的字**抠出来，
  与**自己重算的数**逐条比 ⇒ ⇒ 输出的是「对/不对」，⛔ 不是另一份面板。

⛔ 本工具：⛔ 不跑批、⛔ 不改分析器、⛔ 不改预登记、⛔ 不写 bpath。
"""

import argparse
import io
import json
import math
import os
import re
import sys
from collections import OrderedDict

# ---------------------------------------------------------------- 口径（照预登记）
RHO = 0.250          # ρ*（固定剂量目标密度）
TOL = 0.0050         # 密度容差
Z95 = 1.959963984540054
PFS = (0.25, 0.50, 0.75)


# ---------------------------------------------------------------- 统计（⛔ 自己实现）
def wilson(x, n, z=Z95):
    """⛔ 自己实现的 Wilson score 区间（⛔ 不调 `interval_audit.wilson_bounds`）。"""
    if n <= 0:
        return (0.0, 1.0)
    ph = x / float(n)
    z2 = z * z
    den = 1.0 + z2 / n
    c = (ph + z2 / (2.0 * n)) / den
    h = (z / den) * math.sqrt(ph * (1.0 - ph) / n + z2 / (4.0 * n * n))
    return (max(0.0, c - h), min(1.0, c + h))


def newcombe(x1, n1, x2, n2, z=Z95):
    """⛔ 自己实现的 Newcombe 分数法之差（**方法 10**）。"""
    p1 = x1 / float(n1)
    p2 = x2 / float(n2)
    l1, u1 = wilson(x1, n1, z)
    l2, u2 = wilson(x2, n2, z)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (max(-1.0, lo), min(1.0, hi))


def fisher_two_sided(a, b, c, d):
    """⛔ 自己实现的 Fisher 精确（两尾 = 「不比观测表更可能」的表全求和）。"""
    n = a + b + c + d
    if n == 0:
        return None
    r1, r2, c1 = a + b, c + d, a + c
    denom = float(math.comb(n, c1))

    def prob(x):
        return (math.comb(r1, x) * math.comb(r2, c1 - x)) / denom

    p_obs = prob(a)
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    p = 0.0
    for x in range(lo, hi + 1):
        px = prob(x)
        if px <= p_obs * (1 + 1e-12):
            p += px
    return min(1.0, p)


def paired_perm_exact(diffs):
    """⚖ **配对置换（精确）**：⛔ 不用 Monte Carlo ⇒ ⇒ 走二项分布直算。

    ⚖ 零假设 = 两臂标签**逐轨迹可交换** ⇒ ⇒ 每个「不一致的轨迹」可独立翻转。
    `diffs` = `sign_w − sign_r` ∈ {0, +2, −2} ⇒ ⇒
      · `k` = 不一致轨迹数 ⇒ 每个贡献 ±2（各 1/2）；
      · 于是 `T/2 = 2·Binom(k, 1/2) − k`；
      · 两尾 p = `P(Binom ≥ 上阈值) + P(Binom ≤ 下阈值)`。
    """
    nz = [d for d in diffs if d != 0]
    k = len(nz)
    if k == 0:
        return 1.0, 0.0, 0
    obs = abs(sum(nz)) / 2.0          # |T| / 2
    hi_thr = math.ceil((k + obs) / 2.0 - 1e-12)
    lo_thr = math.floor((k - obs) / 2.0 + 1e-12)

    def pmf(j):
        return math.comb(k, j) * (0.5 ** k)

    p = 0.0
    if hi_thr <= k:
        p += sum(pmf(j) for j in range(hi_thr, k + 1))
    if lo_thr >= 0:
        p += sum(pmf(j) for j in range(0, lo_thr + 1))
    return min(1.0, p), sum(nz) / 2.0, k


def majority_base_p2(n_nz, n_zero=0):
    """⛔ 自己实现的「层内多数为真」零假设基准（零格恒 False ⇒ 不进基准、进分母）。"""
    if n_nz <= 0:
        return 0.5
    tot = n_nz + n_zero
    return sum(math.comb(n_nz, j) * (0.5 ** n_nz)
               for j in range(n_nz + 1) if j * 2 > tot)


# ---------------------------------------------------------------- 解析（⛔ 自己解析原始日志）
BEGIN_RE = re.compile(r"^### BEGIN (\S+) \[(\d+)/(\d+)\] n_eff=(\d+) "
                      r"--inject-scope (\S+) --inject-n-sites (\d+)")
END_RE = re.compile(r"^### END\s+\[(\d+)/(\d+)\] (\S+) rc=(-?\d+)")


def parse_log(path):
    """⚖ 自己解析**原始跑批日志** ⇒ ⇒ 返回格子列表。

    ⛔ **不用**权威读数器、⛔ **不用**拆分器 ⇒ ⇒ 连数据路径都是独立的。
    """
    with io.open(path, encoding="utf-8", errors="replace", newline="") as fh:
        text = fh.read()
    cells, cur = [], None
    for line in text.split("\n"):
        if line.startswith("### BEGIN"):
            m = BEGIN_RE.match(line)
            if not m:
                raise SystemExit("⛔ BEGIN 行解析失败：%r" % line)
            cur = {"tid": m.group(1), "idx": int(m.group(2)), "n_tot": int(m.group(3)),
                   "n_eff": int(m.group(4)), "scope_begin": m.group(5),
                   "n_sites_begin": int(m.group(6)), "rc": None, "reading": None}
            cells.append(cur)
        elif line.startswith("### END"):
            m = END_RE.match(line)
            if not m:
                raise SystemExit("⛔ END 行解析失败：%r" % line)
            if cur is None:
                raise SystemExit("⛔ END 行没有配对的 BEGIN：%r" % line)
            cur["rc"] = int(m.group(4))
            cur["end_tid"] = m.group(3)
        elif line.startswith("{"):
            obj = json.loads(line)
            if cur is None:
                raise SystemExit("⛔ 读数 JSON 没有配对的 BEGIN：%r" % line[:80])
            if cur["reading"] is None:
                cur["reading"] = obj
    return cells


def cell_set(cells, rho=RHO, tol=TOL):
    """⚖ 格集合（V3 四条）：`scope==k` ∧ 读数在 ∧ `n_sites` 为真 ∧ 密度相等。"""
    kept, dropped = [], []
    for c in cells:
        r = c["reading"]
        if r is None:
            dropped.append((c, "读数缺失（未量到）"))
            continue
        scope = r.get("inject_scope") or c["scope_begin"]
        if scope != "k":
            dropped.append((c, "scope≠k"))
            continue
        ns = r.get("inject_n_sites")
        if not ns:
            dropped.append((c, "inject_n_sites 为假"))
            continue
        P, ng, pf = r.get("P"), r.get("n_gen"), r.get("pos_frac")
        if not P or not ng or pf is None:
            dropped.append((c, "缺 P/n_gen/pos_frac"))
            continue
        if r.get("p9_lo_meas") is None or r.get("p9_hi_meas") is None:
            dropped.append((c, "缺 p9_*（未量到）"))
            continue
        inj = int(P) + max(1, int(int(ng) * float(pf))) - 1
        frac = float(ns) / float(inj)
        if abs(frac - rho) > tol:
            dropped.append((c, "密度 %.6f ∉ ρ*±%.4f" % (frac, tol)))
            continue
        c2 = dict(c)
        c2["d"] = float(r["p9_hi_meas"]) - float(r["p9_lo_meas"])
        c2["up"] = r.get("up_mono_meas")
        c2["pf"] = float(pf)
        c2["frac"] = frac
        c2["inj"] = inj
        kept.append(c2)
    return kept, dropped


def problem_key(tid):
    return re.sub(r"__(?:no_)?think$", "", tid) or tid


# ---------------------------------------------------------------- 合池（⛔ 自己实现）
def pool_by_tid(kept):
    g = OrderedDict()
    for r in kept:
        g.setdefault(r["tid"], []).append(r)
    out = OrderedDict()
    for tid, cs in g.items():
        pos = neg = zero = 0
        vals = []
        for c in cs:
            d = c["d"]
            vals.append(d)
            if d > 0:
                pos += 1
            elif d < 0:
                neg += 1
            else:
                zero += 1
        m = len(vals)
        out[tid] = {"pos": pos, "neg": neg, "zero": zero, "m": m,
                    "nz": m - zero, "vals": vals,
                    "verdict": (pos * 2 > m),          # 主口径：平票 False、零格进分母
                    "verdict_alt": (pos > neg)}        # V8：零格剔出分母
    return out


def pool_by_tid_up(kept):
    """⚖ 辅口径（`up_mono_meas`）：⛔ 缺该字段的格**剔出**（不是当 False）。"""
    g = OrderedDict()
    for r in kept:
        g.setdefault(r["tid"], []).append(r)
    out = OrderedDict()
    for tid, cs in g.items():
        pos = neg = 0
        n = 0
        for c in cs:
            v = c["up"]
            if v is None:
                continue
            n += 1
            if v:
                pos += 1
            else:
                neg += 1
        out[tid] = {"pos": pos, "neg": neg, "m": n, "verdict": (pos * 2 > n)}
    return out


def disagreement(pooled):
    all_same = split = 0
    for tid, v in pooled.items():
        signs = [1 if x > 0 else (-1 if x < 0 else 0) for x in v["vals"]]
        nz = [s for s in signs if s != 0]
        if len(nz) < 2:
            continue
        if all(s == nz[0] for s in nz):
            all_same += 1
        else:
            split += 1
    n = all_same + split
    return {"all_same": all_same, "split": split, "n": n,
            "rate": (split / float(n)) if n else float("nan")}


def block_pos(pooled, tids):
    """⚖ V9：块 = think + no_think；块内两条轨迹**都正**才算正。"""
    per = OrderedDict()
    for t in tids:
        per.setdefault(problem_key(t), []).append(1 if pooled[t]["verdict"] else -1)
    out = []
    for q, vs in per.items():
        out.append((q, len(vs), all(v > 0 for v in vs)))
    return out


# ---------------------------------------------------------------- 面板解析
def _arm_block(txt, arm):
    """⚖ 取某个臂的那一段（从它的「改判」行到下一个臂的「改判」行之前）。"""
    lines = txt.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^  %s\s+改判" % arm, ln):
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^  (w|rand)\s+改判", lines[i]):
            end = i
            break
    return "\n".join(lines[start:end])


def _parse_dist(s):
    """⚖ 面板上的分布串 → dict。⚠ 键里的 `,` **不带空格** ⇒ 按 `, ` 切分是安全的。"""
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        raise ValueError("分布串形状不对：%r" % s)
    body = s[1:-1].strip()
    out = OrderedDict()
    if not body:
        return out
    for item in body.split(", "):
        if "×" not in item:
            raise ValueError("分布项形状不对：%r" % item)
        k, n = item.rsplit("×", 1)
        out[k] = int(n)
    return out


def parse_panel(path):
    with io.open(path, encoding="utf-8") as fh:
        txt = fh.read()
    p = {"raw": txt}

    for arm in ("w", "rand"):
        blk = _arm_block(txt, arm)
        if not blk:
            continue
        m = re.search(r"改判 \*\*(\d+)/(\d+)\*\* ｜ 区间 \[([-+0-9.]+), ([-+0-9.]+)\] pp ｜ "
                      r"零假设基准（逐轨迹平均）([0-9.]+)", blk)
        if m:
            p["arm_" + arm] = {"pos": int(m.group(1)), "n": int(m.group(2)),
                               "ci": (float(m.group(3)), float(m.group(4))),
                               "base": float(m.group(5))}
        m = re.search(r"辅口径（`up_mono_meas`）改判 (\d+)/(\d+) ｜ 零格剔出分母那条 (\d+)/(\d+)", blk)
        if m:
            p["aux_" + arm] = {"pos_up": int(m.group(1)), "n_up": int(m.group(2)),
                               "pos_alt": int(m.group(3)), "n_alt": int(m.group(4))}
        m = re.search(r"与主口径\*\*逐条一致\*\*的轨迹：(\d+)/(\d+)", blk)
        if m:
            p["agree_" + arm] = (int(m.group(1)), int(m.group(2)))
        m = re.search(r"三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)", blk)
        if m:
            p["het_" + arm] = {"all_same": int(m.group(1)), "split": int(m.group(2)),
                               "rate": float(m.group(3))}
        m = re.search(r"格集合：进 (\d+) 格 ｜ 剔出 (\d+) 格", blk)
        if m:
            p["set_" + arm] = {"kept": int(m.group(1)), "dropped": int(m.group(2))}
        m = re.search(r"每轨迹有效格 m 分布 = (\{[^}]*\})", blk)
        if m:
            p["mdist_" + arm] = _parse_dist(m.group(1))
        m = re.search(r"\(n_nz,n_zero\) 分布 = (\{[^}]*\})", blk)
        if m:
            p["nzdist_" + arm] = _parse_dist(m.group(1))
        m = re.search(r"基准分布（V4）：(\{[^}]*\})", blk)
        if m:
            p["basedist_" + arm] = _parse_dist(m.group(1))
        m = re.search(r"零格合计 (\d+)", blk)
        if m:
            p["zerocells_" + arm] = int(m.group(1))

    m = re.search(r"^  差 \*\*([-+0-9.]+) pp\*\* ｜ 差区间 \[([-+0-9.]+), ([-+0-9.]+)\] pp ｜ "
                  r"跨臂 Fisher（精确枚举）p = ([0-9.]+) ｜ 配对置换 p = ([0-9.]+)$", txt, re.M)
    if m:
        p["cross"] = {"diff_pp": float(m.group(1)),
                      "ci": (float(m.group(2)), float(m.group(3))),
                      "fisher_p": float(m.group(4)),
                      "perm_p": float(m.group(5))}
    m = re.search(r"^  配对置换 \*\*MC95% 不确定带\*\* = \[([0-9.]+), ([0-9.]+)\]"
                  r"（ge=(\d+) / n_perm=(\d+)", txt, re.M)
    if m:
        p["band"] = ((float(m.group(1)), float(m.group(2))),
                     int(m.group(3)), int(m.group(4)))

    m = re.search(r"^-------------------- 块级.*?\n^  w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 "
                  r"([-+0-9.]+) pp ｜ 差区间 \[([-+0-9.]+), ([-+0-9.]+)\] pp ｜ Fisher p = ([0-9.]+)$",
                  txt, re.M | re.S)
    if m:
        p["block"] = {"w_pos": int(m.group(1)), "w_n": int(m.group(2)),
                      "r_pos": int(m.group(3)), "r_n": int(m.group(4)),
                      "diff_pp": float(m.group(5)),
                      "ci": (float(m.group(6)), float(m.group(7))),
                      "fisher_p": float(m.group(8))}

    for pf in PFS:
        key = "%.2f" % pf
        m = re.search(r"^  pos_frac=%s\s+w (\d+)/(\d+) ｜ rand (\d+)/(\d+) ｜ 差 ([-+0-9.]+) pp ｜ "
                      r"差区间 \[([-+0-9.]+), ([-+0-9.]+)\] pp ｜ Fisher p = ([0-9.]+)$" % key,
                      txt, re.M)
        if m:
            p["grp_" + key] = {"w_pos": int(m.group(1)), "w_n": int(m.group(2)),
                               "r_pos": int(m.group(3)), "r_n": int(m.group(4)),
                               "diff_pp": float(m.group(5)),
                               "ci": (float(m.group(6)), float(m.group(7))),
                               "fisher_p": float(m.group(8))}
    return p


# ---------------------------------------------------------------- 比对
class Checker(object):
    def __init__(self):
        self.rows = []

    def add(self, cid, label, mine, theirs, tol=None, exact=True):
        if theirs is None:
            ok = False
        elif exact:
            ok = (mine == theirs)
        else:
            ok = abs(float(mine) - float(theirs)) <= (tol if tol is not None else 0.0)
        self.rows.append({"id": cid, "label": label, "mine": mine, "theirs": theirs, "ok": ok})
        return ok

    def add_range(self, cid, label, mine, theirs, tol=0.005):
        if theirs is None:
            ok = False
        else:
            ok = (abs(float(mine[0]) - float(theirs[0])) <= tol
                  and abs(float(mine[1]) - float(theirs[1])) <= tol)
        self.rows.append({"id": cid, "label": label, "mine": list(mine), "theirs": theirs, "ok": ok})
        return ok

    def add_dict(self, cid, label, mine, theirs):
        """⚖ 分布比对：键集合与计数都要逐条相同（⛔ 不能只看总数）。

        ⚖⚠ **键的写法必须与面板一致**：tuple 键写成 `(2,0)`（⛔ 逗号后**不加空格**）
        ⇒ ⇒ 否则「我的 `(3, 0)`」与「面板的 `(3,0)`」会被判成不同 ⇒ ⇒ 假红。
        """
        def norm(k):
            if isinstance(k, tuple):
                return "(" + ",".join(str(x) for x in k) + ")"
            return str(k)

        if theirs is None:
            ok = False
        else:
            mk = dict((norm(k), v) for k, v in mine.items())
            ok = (mk == dict((norm(k), v) for k, v in theirs.items()))
        self.rows.append({"id": cid, "label": label, "mine": dict(mine), "theirs": theirs, "ok": ok})
        return ok


def _dist(vals):
    d = OrderedDict()
    for v in vals:
        d[v] = d.get(v, 0) + 1
    return d


def _dist_str(vals):
    d = _dist(vals)
    return "{" + ", ".join("%s×%d" % (k, d[k]) for k in d) + "}"


def _base_dist_str(vals):
    d = _dist([round(v, 6) for v in vals])
    return "{" + ", ".join("%s×%d" % (k, d[k]) for k in d) + "}"


# ---------------------------------------------------------------- 自检（已知答案）
def selftest():
    """⚖ **已知答案夹具**：⛔ 不依赖真数据 ⇒ ⇒ 可以进回归执行集。

    ⚖ 每条都是**手写的期望值**（⛔ 不从被检对象派生 ⇒ ⇒ 不是自证）。
    """
    checks = []

    def add(cid, label, ok, detail=""):
        checks.append((cid, label, bool(ok), detail))

    # 1) Wilson 已知答案
    lo, hi = wilson(0, 10)
    add("S-Wilson-0", "Wilson(0,10) = [0, 0.277532]",
        abs(lo) < 1e-12 and abs(hi - 0.2775328) < 1e-6, "[%.7f, %.7f]" % (lo, hi))
    lo, hi = wilson(5, 10)
    add("S-Wilson-5", "Wilson(5,10) = [0.236593, 0.763407]",
        abs(lo - 0.2365931) < 1e-6 and abs(hi - 0.7634069) < 1e-6, "[%.7f, %.7f]" % (lo, hi))

    # 2) Newcombe 方法 10（已知答案：两比例相同时区间含 0）
    lo, hi = newcombe(5, 10, 5, 10)
    add("S-Newcombe-same", "Newcombe(5/10, 5/10) 含 0",
        lo < 0 < hi, "[%.7f, %.7f]" % (lo, hi))

    # 3) Fisher 精确已知答案
    p = fisher_two_sided(3, 1, 1, 3)
    add("S-Fisher-1", "Fisher(3,1,1,3) = 0.4857142857",
        abs(p - 0.4857142857142857) < 1e-12, "%.12f" % p)
    p = fisher_two_sided(46, 10, 29, 27)
    add("S-Fisher-2", "Fisher(46,10,29,27) = 0.0011522251934",
        abs(p - 0.0011522251934061715) < 1e-12, "%.12f" % p)

    # 4) 零假设基准（V4/V5 的口径）
    add("S-Base-3", "base(3,0) = 0.5", abs(majority_base_p2(3, 0) - 0.5) < 1e-12)
    add("S-Base-2", "base(2,0) = 0.25", abs(majority_base_p2(2, 0) - 0.25) < 1e-12)
    add("S-Base-11", "base(1,1) = 0（阈值含零格 ⇒ 只认 2 正 ⇒ 抽不到）",
        abs(majority_base_p2(1, 1)) < 1e-12)
    add("S-Base-00", "base(0,0) = 0.5（n_nz≤0 的约定）",
        abs(majority_base_p2(0, 0) - 0.5) < 1e-12)

    # 5) 多数规则（主口径：平票 False、零格进分母）
    p4 = pool_by_tid([{"tid": "t", "d": 0.1, "up": True},
                      {"tid": "t", "d": 0.0, "up": True}])
    add("S-Major-1pos1zero", "1 正 1 零 ⇒ False（零格进分母）",
        p4["t"]["verdict"] is False and p4["t"]["m"] == 2 and p4["t"]["zero"] == 1)
    p4 = pool_by_tid([{"tid": "t", "d": 0.1, "up": True},
                      {"tid": "t", "d": -0.1, "up": False}])
    add("S-Major-tie", "1 正 1 负 ⇒ False（平票算 False）", p4["t"]["verdict"] is False)
    p4 = pool_by_tid([{"tid": "t", "d": 0.1, "up": True},
                      {"tid": "t", "d": 0.2, "up": True},
                      {"tid": "t", "d": 0.0, "up": True}])
    add("S-Major-2pos1zero", "2 正 1 零 ⇒ True（零格进分母）",
        p4["t"]["verdict"] is True and p4["t"]["m"] == 3)
    p4 = pool_by_tid([{"tid": "t", "d": 0.1, "up": True},
                      {"tid": "t", "d": 0.0, "up": True}])
    add("S-Major-alt", "1 正 1 零 ⇒ V8（零格剔出分母）判 True",
        p4["t"]["verdict_alt"] is True)

    # 6) 配对置换（精确）已知答案：4 个不一致轨迹全在 w 一侧 ⇒ p = 2/16 = 0.125
    #    ⚖ 观测统计量 `T/2` = sum(diffs)/2 = 8/2 = **4**（⛔ 不是 2）
    p, obs, k = paired_perm_exact([2, 2, 2, 2])
    add("S-Perm-4", "置换：4 个不一致全在 w ⇒ p = 0.125（k=4, T/2=+4）",
        abs(p - 0.125) < 1e-12 and k == 4 and obs == 4.0, "p=%.6f k=%d T/2=%g" % (p, k, obs))
    p, obs, k = paired_perm_exact([0, 0, 0])
    add("S-Perm-0", "置换：没有不一致轨迹 ⇒ p = 1", abs(p - 1.0) < 1e-12)

    # 7) 解析器：合成日志 ⇒ 一格有读数、一格没有
    #    ⚖ 有读数那格的 `inject_n_sites` 必须让密度**落在 ρ*±tol 内**：
    #    P=10, n_gen=100, pos_frac=0.5 ⇒ inj = 10 + 50 − 1 = 59
    #    ⇒ ⇒ n_sites=15 ⇒ 密度 15/59 = 0.254237 ∈ [0.245, 0.255] ✓
    #    （⛔ 若取 5 ⇒ 密度 0.0847 ⇒ 会被**密度条件**剔掉 ⇒ 夹具就验不到「缺读数」那条）
    mini = (
        "### BEGIN x__think [1/2] n_eff=1 --inject-scope k --inject-n-sites 15  00:00:00\n"
        "{\"tid\": \"x__think\", \"pos_frac\": 0.5, \"P\": 10, \"n_gen\": 100, "
        "\"inject_scope\": \"k\", \"inject_n_sites\": 15, \"p9_lo_meas\": 0.1, "
        "\"p9_hi_meas\": 0.2, \"up_mono_meas\": true}\n"
        "### END   [1/2] x__think rc=0  00:00:01\n"
        "### BEGIN y__think [2/2] n_eff=1 --inject-scope k --inject-n-sites 15  00:00:01\n"
        "### END   [2/2] y__think rc=1  00:00:02\n")
    cs = None
    tmp = None
    try:
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix="_indep_mini_log_", suffix=".txt")
        with io.open(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(mini)
        cs = parse_log(tmp)
    finally:
        if tmp and os.path.isfile(tmp):
            os.remove(tmp)
    add("S-Parse-cells", "合成日志解析出 2 格", len(cs) == 2, "%d 格" % len(cs))
    add("S-Parse-read", "第 1 格有读数、第 2 格没有",
        cs[0]["reading"] is not None and cs[1]["reading"] is None)
    kept, dropped = cell_set(cs)
    add("S-CellSet", "缺读数的那格被剔出格集合（⛔ 不当 0）",
        len(kept) == 1 and len(dropped) == 1, "kept=%d dropped=%d" % (len(kept), len(dropped)))

    # 8) 分布串解析（面板格式 ↔ 解析器）
    d = _parse_dist("{2×1, 3×55}")
    add("S-Dist-parse", "分布串 `{2×1, 3×55}` 解析成 2 个键",
        d == {"2": 1, "3": 55}, str(dict(d)))

    bad = [c for c in checks if not c[2]]
    for cid, label, ok, detail in checks:
        print("[%s] %-16s %s%s" % ("OK  " if ok else "FAIL", cid, label,
                                   ("  ⇒ %s" % detail) if detail else ""))
    print("自检 %d 条 ｜ PASS %d ｜ FAIL %d" % (len(checks), len(checks) - len(bad), len(bad)))
    return 0 if not bad else 1


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="⛔ 只跑已知答案夹具（不依赖真数据）")
    ap.add_argument("--w-log")
    ap.add_argument("--rand-log")
    ap.add_argument("--panel")
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not (a.w_log and a.rand_log and a.panel):
        raise SystemExit("⛔ 缺 --w-log / --rand-log / --panel（或用 --selftest）")

    # ---- ① 自己解析原始日志
    raw = {"w": parse_log(a.w_log), "rand": parse_log(a.rand_log)}

    # ---- ② 格集合
    kept, dropped = {}, {}
    for arm in ("w", "rand"):
        kept[arm], dropped[arm] = cell_set(raw[arm])

    # ---- ③ 合池
    pooled = {arm: pool_by_tid(kept[arm]) for arm in ("w", "rand")}
    pooled_up = {arm: pool_by_tid_up(kept[arm]) for arm in ("w", "rand")}

    tids = sorted(set(pooled["w"]) & set(pooled["rand"]))
    signs_w = [1 if pooled["w"][t]["verdict"] else -1 for t in tids]
    signs_r = [1 if pooled["rand"][t]["verdict"] else -1 for t in tids]

    arm_res = {}
    for arm in ("w", "rand"):
        P = pooled[arm]
        pos = sum(1 for v in P.values() if v["verdict"])
        n = len(P)
        ci = wilson(pos, n)
        bases = [majority_base_p2(v["nz"], v["zero"]) for v in P.values()]
        base_mean = sum(bases) / float(len(bases)) if bases else float("nan")
        het = disagreement(P)
        pos_up = sum(1 for v in pooled_up[arm].values() if v["verdict"])
        n_up = len(pooled_up[arm])
        pos_alt = sum(1 for v in P.values() if v["verdict_alt"])
        agree = sum(1 for t in P
                    if P[t]["verdict"] == pooled_up[arm].get(t, {}).get("verdict"))
        arm_res[arm] = {"pos": pos, "n": n, "ci": ci, "base_mean": base_mean,
                        "bases": bases, "het": het, "pos_up": pos_up, "n_up": n_up,
                        "pos_alt": pos_alt, "agree": agree,
                        "kept": len(kept[arm]), "dropped": len(dropped[arm]),
                        "m_dist": _dist([v["m"] for v in P.values()]),
                        "nz_dist": _dist([(v["nz"], v["zero"]) for v in P.values()]),
                        "base_dist": _dist([round(b, 6) for b in bases]),
                        "zero_cells": sum(v["zero"] for v in P.values())}

    # ---- ④ 跨臂
    diffs = [a1 - b1 for a1, b1 in zip(signs_w, signs_r)]
    perm_p, perm_obs, k_disc = paired_perm_exact(diffs)
    fisher_p = fisher_two_sided(arm_res["w"]["pos"], arm_res["w"]["n"] - arm_res["w"]["pos"],
                                 arm_res["rand"]["pos"], arm_res["rand"]["n"] - arm_res["rand"]["pos"])
    diff_pp = 100.0 * (arm_res["w"]["pos"] / float(arm_res["w"]["n"])
                       - arm_res["rand"]["pos"] / float(arm_res["rand"]["n"]))
    diff_ci = newcombe(arm_res["w"]["pos"], arm_res["w"]["n"],
                       arm_res["rand"]["pos"], arm_res["rand"]["n"])

    bw = block_pos(pooled["w"], tids)
    br = block_pos(pooled["rand"], tids)
    pb = sum(1 for _q, _n, p in bw if p)
    pr = sum(1 for _q, _n, p in br if p)
    blk = {"w_pos": pb, "w_n": len(bw), "r_pos": pr, "r_n": len(br),
           "diff_pp": 100.0 * (pb / float(len(bw)) - pr / float(len(br))),
           "ci": newcombe(pb, len(bw), pr, len(br)),
           "fisher_p": fisher_two_sided(pb, len(bw) - pb, pr, len(br) - pr)}

    grp = {}
    for pf in PFS:
        key = "%.2f" % pf
        g = {}
        for arm in ("w", "rand"):
            sub = [c for c in kept[arm] if abs(c["pf"] - pf) < 1e-9]
            g[arm] = {"pos": sum(1 for c in sub if c["d"] > 0), "n": len(sub)}
        g["diff_pp"] = 100.0 * (g["w"]["pos"] / float(g["w"]["n"])
                                - g["rand"]["pos"] / float(g["rand"]["n"]))
        g["ci"] = newcombe(g["w"]["pos"], g["w"]["n"], g["rand"]["pos"], g["rand"]["n"])
        g["fisher_p"] = fisher_two_sided(g["w"]["pos"], g["w"]["n"] - g["w"]["pos"],
                                         g["rand"]["pos"], g["rand"]["n"] - g["rand"]["pos"])
        grp[key] = g

    # ---- ⑤ 面板比对
    P = parse_panel(a.panel)
    C = Checker()

    for arm in ("w", "rand"):
        r = arm_res[arm]
        ps = P.get("set_" + arm) or {}
        C.add("I-%s-cells" % arm, "%s 臂格子总数（自己解析的 BEGIN 数）" % arm,
              len(raw[arm]), 168)
        C.add("I-%s-kept" % arm, "%s 臂进格集合的格数" % arm, r["kept"], ps.get("kept"))
        C.add("I-%s-drop" % arm, "%s 臂剔出格集合的格数" % arm, r["dropped"], ps.get("dropped"))
        pa = P.get("arm_" + arm) or {}
        C.add("T-%s-pos" % arm, "%s 臂改判数" % arm, "%d/%d" % (r["pos"], r["n"]),
              "%s/%s" % (pa.get("pos"), pa.get("n")))
        if pa.get("ci"):
            C.add_range("T-%s-ci" % arm, "%s 臂 Wilson95 区间(pp)" % arm,
                        [r["ci"][0] * 100.0, r["ci"][1] * 100.0], pa.get("ci"))
        if pa.get("base") is not None:
            C.add("T-%s-base" % arm, "%s 臂零假设基准（逐轨迹平均）" % arm,
                  r["base_mean"], pa.get("base"), tol=0.00005, exact=False)
        au = P.get("aux_" + arm) or {}
        C.add("T-%s-up" % arm, "%s 臂辅口径(up_mono_meas)改判数" % arm,
              "%d/%d" % (r["pos_up"], r["n_up"]),
              "%s/%s" % (au.get("pos_up"), au.get("n_up")))
        C.add("T-%s-alt" % arm, "%s 臂零格剔出分母那条" % arm,
              "%d/%d" % (r["pos_alt"], r["n"]),
              "%s/%s" % (au.get("pos_alt"), au.get("n_alt")))
        ag = P.get("agree_" + arm)
        C.add("T-%s-agree" % arm, "%s 臂主/辅口径逐条一致数" % arm,
              "%d/%d" % (r["agree"], r["n"]),
              "%s/%s" % (ag[0], ag[1]) if ag else None)
        h = P.get("het_" + arm) or {}
        C.add("T-%s-het" % arm, "%s 臂异质性（全一致/2:1分歧/率）" % arm,
              "%d/%d/%.4f" % (r["het"]["all_same"], r["het"]["split"], r["het"]["rate"]),
              "%s/%s/%s" % (h.get("all_same"), h.get("split"), h.get("rate")))
        # ⚖ V3/V4 要求印在面板上的三项（244.81 补）
        C.add_dict("T-%s-mdist" % arm, "%s 臂每轨迹有效格 m 分布（V3）" % arm,
                   r["m_dist"], P.get("mdist_" + arm))
        C.add_dict("T-%s-nzdist" % arm, "%s 臂 (n_nz,n_zero) 分布（V3）" % arm,
                   r["nz_dist"], P.get("nzdist_" + arm))
        C.add_dict("T-%s-basedist" % arm, "%s 臂基准分布（V4）" % arm,
                   r["base_dist"], P.get("basedist_" + arm))
        C.add("T-%s-zerocells" % arm, "%s 臂零格合计" % arm,
              r["zero_cells"], P.get("zerocells_" + arm))

    cr = P.get("cross") or {}
    C.add("X-diff", "两臂差 pp", diff_pp, cr.get("diff_pp"), tol=0.005, exact=False)
    if cr.get("ci"):
        C.add_range("X-diffci", "两臂差 Newcombe95 区间(pp)",
                    [diff_ci[0] * 100.0, diff_ci[1] * 100.0], cr.get("ci"))
    C.add("X-fisher", "跨臂 Fisher 精确 p（面板印 6 位小数 ⇒ 容差 1e-6）",
          fisher_p, cr.get("fisher_p"), tol=1e-6, exact=False)
    band = P.get("band")
    if band:
        blo, bhi = band[0]
        ok = (blo - 1e-12) <= perm_p <= (bhi + 1e-12)
        C.rows.append({"id": "X-perm", "label": "配对置换 p（我的二项精确）落在面板 MC 带内",
                       "mine": perm_p, "theirs": [blo, bhi], "ok": ok})
    else:
        C.rows.append({"id": "X-perm", "label": "配对置换 p（我的二项精确）落在面板 MC 带内",
                       "mine": perm_p, "theirs": None, "ok": False})

    bk = P.get("block") or {}
    C.add("B-pos", "块级 w/rand 改判数", "%d/%d ｜ %d/%d" % (blk["w_pos"], blk["w_n"],
                                                            blk["r_pos"], blk["r_n"]),
          "%s/%s ｜ %s/%s" % (bk.get("w_pos"), bk.get("w_n"),
                             bk.get("r_pos"), bk.get("r_n")))
    C.add("B-diff", "块级差 pp", blk["diff_pp"], bk.get("diff_pp"), tol=0.005, exact=False)
    if bk.get("ci"):
        C.add_range("B-diffci", "块级差 Newcombe95 区间(pp)",
                    [blk["ci"][0] * 100.0, blk["ci"][1] * 100.0], bk.get("ci"))
    C.add("B-fisher", "块级 Fisher 精确 p（面板印 6 位小数 ⇒ 容差 1e-6）",
          blk["fisher_p"], bk.get("fisher_p"), tol=1e-6, exact=False)

    for pf in PFS:
        key = "%.2f" % pf
        g = grp[key]
        pg = P.get("grp_" + key) or {}
        C.add("G-%s-pos" % key, "pos_frac=%s 的 w/rand 改判数" % key,
              "%d/%d ｜ %d/%d" % (g["w"]["pos"], g["w"]["n"], g["rand"]["pos"], g["rand"]["n"]),
              "%s/%s ｜ %s/%s" % (pg.get("w_pos"), pg.get("w_n"),
                                 pg.get("r_pos"), pg.get("r_n")))
        C.add("G-%s-diff" % key, "pos_frac=%s 的差 pp" % key, g["diff_pp"], pg.get("diff_pp"),
              tol=0.005, exact=False)
        if pg.get("ci"):
            C.add_range("G-%s-ci" % key, "pos_frac=%s 的差区间(pp)" % key,
                        [g["ci"][0] * 100.0, g["ci"][1] * 100.0], pg.get("ci"))
        C.add("G-%s-fisher" % key, "pos_frac=%s 的 Fisher 精确 p" % key, g["fisher_p"],
              pg.get("fisher_p"), tol=1e-6, exact=False)

    # ---- ⑥ 印出
    out = []
    A = out.append
    A("=== 固定剂量合池判决：**独立重算器**（⛔ 不 import 分析器/读数器/拆分器） ===")
    A("面板：%s" % a.panel)
    A("原始日志：%s ｜ %s" % (a.w_log, a.rand_log))
    A("")
    A("---- 我自己算出来的口径结构（⚠ 面板**也**印这个 ⇒ 两边应当一致）----")
    for arm in ("w", "rand"):
        r = arm_res[arm]
        A("  %-4s 轨迹 %d ｜ m 分布 = %s ｜ (n_nz,n_zero) 分布 = %s ｜ 零格合计 %d"
          % (arm, r["n"], _dist_str([v["m"] for v in pooled[arm].values()]),
             _dist_str([(v["nz"], v["zero"]) for v in pooled[arm].values()]),
             r["zero_cells"]))
        A("       基准分布 = %s ｜ 逐轨迹平均 = %.6f"
          % (_base_dist_str(r["bases"]), r["base_mean"]))
    A("  置换：不一致轨迹 k = %d ｜ 观测 T/2 = %+g ｜ 我的二项精确 p = %.6f"
      % (k_disc, perm_obs, perm_p))
    A("")
    A("---- 逐条比对 ----")
    for r in C.rows:
        A("[%s] %-14s %s ｜ 我的 = %s ｜ 面板 = %s"
          % ("OK  " if r["ok"] else "FAIL", r["id"], r["label"], r["mine"], r["theirs"]))
    bad = [r for r in C.rows if not r["ok"]]
    A("")
    A("判据 %d 条 ｜ PASS %d ｜ FAIL %d" % (len(C.rows), len(C.rows) - len(bad), len(bad)))
    txt = "\n".join(out)
    if a.out:
        with io.open(a.out, "w", encoding="utf-8", newline="") as fh:
            fh.write(txt + "\n")
    print(txt)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
