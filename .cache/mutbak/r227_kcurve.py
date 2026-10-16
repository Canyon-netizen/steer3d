#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r227_kcurve —— k 曲线的**逐块配对**读数器（修订 227）。

## 这条在量什么

修订 225/226 用 `--inject-scope k --inject-n-sites K` 做「位点数 k」的手术刀，
问的是**基线漂移是不是位点数堆出来的**。两轮都停在「未确立」，但两次的 k 阶梯
踩了同一个坑（修订 226）：**按整条序列长度排 k，而仪器吃的是前缀**
`n_eff = P + int(pos_frac*gen)` ⇒ 3/18 格越界崩了。
修订 227 先量后排（阶梯按 n_eff 排），覆盖面从 1 个问题扩到 **2 个问题**。

⚠⚠⛔ 本脚本只**读**。它不碰模型、不重算任何读数、不改任何格子。

## ⚠⚠⁴ 报数纪律（照抄，不许省）

1. ⛔ **崩的格不是 0**。没有读数的格子单独计数、单独列出，⛔ **不进**任何
   求和 / 中位 / 符号检验的分母。「没量到」是事实，「无差异」是结论。
2. ⚖ 有读数的格子**自己报出** `inject_scope` / `inject_n_sites` / `P` / `t`
   ⇒ **k 不靠位置配对取**。位置配对只用来做**交叉校验**（状态文件与日志逐格对得上）。
3. ⚠ 校验不过一律 **exit 2 硬失败**，⛔ 不许「尽力而为地读一部分」。
   ⚖ 分母对不齐时**读一半比读错强这句话是错的** —— 错位一格就会把
   k=2048 的值读成 single 的值（修订 226 的事故）。
4. ⚠⚠ 报趋势/反向/拐点之前，先与**同曲线相邻档抖动**比一次：
   差值 ≪ 抖动 ⇒ 只能写「噪声主导」，⛔ 不能写成机制。
5. ⚠⚠ 轨迹数 ≠ 独立问题数（`think` / `no_think` 同属一个问题）
   ⇒ 符号检验在**问题级**也报一遍，并给双尾下界 `2/2^n`。
6. ⚠⚠ `n_eff` 与 JSON 自报的 `P + t` 必须相等 —— 这是「阶梯排对了」的唯一
   运行时证据，⛔ 不许靠我记忆里的 n_eff。

跑法：
    python3 r227_kcurve.py --log r227_sweep.log --status r227_status.txt
    python3 r227_kcurve.py --selftest
退出码：0 = 读完了；2 = 校验不过（拒绝读）；3 = 文件读不了。
"""

import argparse
import json
import math
import re
import sys

BEGIN_RE = re.compile(
    r"^###\s+BEGIN\s+(?P<tid>\S+)(?P<rest>.*?)\s\s+(?P<time>\d\d:\d\d:\d\d)\s*$")
N_EFF_RE = re.compile(r"n_eff=(\d+)")
RC_RE = re.compile(r"\brc=(-?\d+)")
K_RE = re.compile(r"\bk=(\d+)")
SCOPES = ("single", "all")

# ⚠ JSON 读数行必须同时含这两个键才算「读到了」：
# ⚖ `tid` 防误认，`p9_lo_meas` 才是被量的那个数（`p9_lo` 是拟合值，不是实测）。
READ_MARKERS = ('"tid"', '"p9_lo_meas"')

EXC_RE = re.compile(r"^(\w*(?:Error|Exception|Interrupt|Exit))\b", re.M)


class HardFail(Exception):
    """校验不过。⛔ 一律硬失败，不降级成「尽力而为地读一部分」。"""


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def sign_test(deltas):
    """**精确**双尾符号检验。返回 (p, n_pos, n_neg, n_tie, p_lower_bound, z)。

    ⚠⚠⁴ 这里**不许用正态近似** `erfc(|z|/√2)`。
    ⚖ 2026-10-17 实测：n=4 全同向时正态近似给 **p=0.0455**，
    ⚖ 而精确值是 **2/2⁴ = 0.125** —— ⚠⚠ 那个近似值**比理论下界还小**，
    ⚖ 也就是说它报出了一个**在 n=4 下不可能达到**的显著水平。
    ⚖⇒ 小样本符号检验必须用精确二项，任何时候 p ≥ 2/2^n 都应成立；
    ⚖ 若报出的 p 小于下界，那不是统计结论，是伪影。

    ⚖ p_lower_bound = 2/2^n 是 n 个全同向时**最小可能**的 p。
    ⚖ 它 > 0.05 ⇒ 这套设计**结构上没有能力**在 0.05 上给结论。
    """
    pos = sum(1 for d in deltas if d > 0)
    neg = sum(1 for d in deltas if d < 0)
    tie = sum(1 for d in deltas if d == 0)
    n = pos + neg
    if n == 0:
        return None, pos, neg, tie, None, None
    k = min(pos, neg)
    # ⚖ 精确双尾：把所有「不比观测到的更可能」的结果都算进去
    obs = math.comb(n, k)
    probs = [math.comb(n, j) for j in range(n + 1)]
    p = sum(c for c in probs if c <= obs) / float(2 ** n)
    lb = 2.0 ** (1 - n)
    z = (pos - neg) / math.sqrt(n)
    return p, pos, neg, tie, lb, z


# ---------------------------------------------------------------- 解析


def parse_blocks(text):
    """按 `### BEGIN` 把日志切成块。⚠ 返回的块数必须与状态文件行数对得上。"""
    blocks = []
    cur = None
    for line in text.split("\n"):
        m = BEGIN_RE.match(line)
        if m:
            if cur is not None:
                blocks.append(cur)
            ne = N_EFF_RE.search(m.group("rest"))
            cur = {"tid": m.group("tid"),
                   "n_eff": int(ne.group(1)) if ne else None,
                   "time": m.group("time"),
                   "lines": []}
        elif cur is not None:
            cur["lines"].append(line)
    if cur is not None:
        blocks.append(cur)
    return blocks


def parse_status(text):
    """状态文件 → (rows, alldone)。`ALLDONE` 行不算一格。"""
    rows = []
    alldone = None
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("ALLDONE"):
            alldone = s.split()[-1]
            continue
        rc = RC_RE.search(s)
        if rc is None:
            raise HardFail("状态行读不出 rc：%r" % s)
        k = K_RE.search(s)
        scope = None
        for sc in SCOPES:
            if re.search(r"(?:^|\s)%s(?:\s|$)" % sc, s):
                scope = sc
                break
        rows.append({"tid": s.split()[0],
                     "k": int(k.group(1)) if k else None,
                     "scope": scope if scope else ("k" if k else None),
                     "rc": int(rc.group(1)),
                     "raw": s})
    return rows, alldone


def _extract_reading(lines):
    """块里若有读数就取出来。⚖ 返回 (reading|None, err)。

    ⛔ 没有读数时返回 None —— ⛔ 绝不用 0 顶替（修订 226 的教训）。
    """
    found = []
    for ln in lines:
        t = ln.strip()
        if not t.startswith("{") or not all(mk in t for mk in READ_MARKERS):
            continue
        try:
            found.append(json.loads(t))
        except ValueError:
            continue
    if len(found) == 1:
        return found[0], None
    if len(found) > 1:
        raise HardFail("一块里有 %d 条读数 JSON —— 我不知道该信哪条，停下" % len(found))
    m = EXC_RE.search("\n".join(lines))
    return None, (m.group(1) if m else "无读数（无 JSON，且没抓到异常名）")


def join(blocks, rows):
    """逐块配对 + 交叉校验。⚠⚠ 校验不过一律抛 HardFail。"""
    if len(blocks) != len(rows):
        raise HardFail(
            "块数 %d ≠ 状态行数 %d —— 日志和状态文件不是同一轮，"
            "位置配对会错位，拒绝读" % (len(blocks), len(rows)))

    cells = []
    seen = {}
    for i, (b, r) in enumerate(zip(blocks, rows)):
        if b["tid"] != r["tid"]:
            raise HardFail("第 %d 格 tid 对不上：日志 %r vs 状态 %r（错位一格会把"
                           "上一格的 k 读成这一格的）" % (i + 1, b["tid"], r["tid"]))
        reading, err = _extract_reading(b["lines"])
        c = {"idx": i + 1, "tid": b["tid"], "n_eff": b["n_eff"], "time": b["time"],
             "rc": r["rc"], "scope": None, "k": None, "reading": reading, "err": err,
             "n_eff_src": ("BEGIN" if b["n_eff"] is not None else "未量到")}

        if reading is not None:
            c["scope"] = reading.get("inject_scope")
            if c["scope"] == "k":
                c["k"] = int(reading["inject_n_sites"])
            # ⚖ 交叉校验：状态文件说的 k 必须是读数自报的那个 k。
            # ⚖ 这一步是「位置配对只用来校验、不用来取数」的实现处。
            if r["scope"] in SCOPES and c["scope"] != r["scope"]:
                raise HardFail("第 %d 格口径不符：状态 %r vs 读数 %r"
                               % (i + 1, r["scope"], c["scope"]))
            if r["scope"] == "k" and c["k"] != r["k"]:
                raise HardFail("第 %d 格 k 不符：状态 %r vs 读数 %r"
                               % (i + 1, r["k"], c["k"]))
            # ⚠⚠ n_eff 必须等于读数自报的 P + t（仪器吃前缀，这是唯一运行时证据）
            # ⚖ BEGIN 行里没写 n_eff 时（r226 的格式就是这样）**回退**到读数自报的 P+t，
            # ⚖ 但必须标明来源 —— 回退来的 n_eff 不能冒充「BEGIN 与 P+t 互相印证过」。
            pt = reading.get("P")
            tt = reading.get("t")
            if pt is not None and tt is not None:
                pt_sum = int(pt) + int(tt)
                if b["n_eff"] is None:
                    c["n_eff"] = pt_sum
                    c["n_eff_src"] = "读数P+t（未与 BEGIN 互证）"
                else:
                    c["n_eff_src"] = "BEGIN（已与 P+t 互证）"
                    if b["n_eff"] != pt_sum:
                        raise HardFail(
                            "第 %d 格 n_eff=%d ≠ P+t=%d+%d=%d —— 阶梯排错了"
                            % (i + 1, b["n_eff"], pt, tt, pt_sum))
            else:
                c["n_eff_src"] = "未量到（读数里没有 P/t）"
        elif r["rc"] == 0:
            raise HardFail("第 %d 格 rc=0 却没读到 JSON —— 状态与日志矛盾，拒绝读"
                           % (i + 1))
        # ⚠⚠⁴ **重复档检测**。这一条是 2026-10-17 修订 232 才补上的，
        # ⚖ 因为那一轮改用「**追加进同一份日志**」的驱动形态（只跑新增档，
        # ⚖ 而不重跑已入库的 31 格）。
        # ⚖⚠ 那个形态有个新风险：**驱动被误跑两次 ⇒ 同一个 (tid, 口径, k) 出现两次**。
        # ⚖ 而上面的交叉校验两次都过得去（状态与读数确实一致）⇒
        # ⚖ 重复档会**静默混进曲线**，既虚增「抖动地板」又让该档被算两次。
        # ⚖⚠ 分母、显著性、单调性都会被它污染，而输出上看不出任何异常。
        if reading is not None:
            key = (c["tid"], c["scope"], c["k"])
            if key in seen:
                raise HardFail(
                    "第 %d 格与第 %d 格**重复**：tid=%s 口径=%s k=%s"
                    "⇒ 同一档被跑了两遍（驱动被误跑两次？）。"
                    "⚠ 重复档会虚增抖动地板并让该档被算两次，⛔ 拒绝读。"
                    % (i + 1, seen[key], c["tid"], c["scope"], c["k"]))
            seen[key] = i + 1
        cells.append(c)
    return cells


# ---------------------------------------------------------------- 分析


def analyze(cells, verbose=True):
    ok = [c for c in cells if c["reading"] is not None]
    bad = [c for c in cells if c["reading"] is None]

    arms = sorted(set(c["reading"]["arm"] for c in ok if "arm" in c["reading"]))
    nested = sorted(set(c["reading"].get("inject_nested") for c in ok))
    if len(arms) > 1:
        raise HardFail("曲线里混了多个臂 %s ⇒ 不能连成一条曲线" % arms)
    if len(nested) > 1:
        raise HardFail("曲线里混了嵌套设置 %s ⇒ 不能连成一条曲线" % nested)

    # ---- 按 tid 分组
    tids = []
    for c in cells:
        if c["tid"] not in tids:
            tids.append(c["tid"])

    per = {}
    for t in tids:
        cs = [c for c in cells if c["tid"] == t]
        ladder = sorted([c for c in cs if c["scope"] == "k" and c["reading"]],
                        key=lambda c: c["k"])
        ends = {c["scope"]: c for c in cs if c["scope"] in SCOPES and c["reading"]}
        ncrash = sum(1 for c in cs if c["reading"] is None)
        n_eff = next((c["n_eff"] for c in cs if c["n_eff"] is not None), None)
        # ⚖ n_eff 的来源必须同报：互证过 ≠ 回退来的
        n_eff_src = next((c.get("n_eff_src") for c in cs
                          if c["n_eff"] is not None), "未量到")

        row = {"tid": t, "n_eff": n_eff, "n_eff_src": n_eff_src,
               "n_cells": len(cs), "n_crash": ncrash,
               "ladder": ladder, "single": ends.get("single"), "all": ends.get("all")}

        # ⚖ 三个尺子：
        #   jitter     = 相邻档 lo 之差的**最大**绝对值  ← 判决尺（极值）
        #   jitter_med = 相邻档 lo 之差的**中位数**      ← 稳健尺（跨轮次可比）
        #   span       = 阶梯内 lo 的极差（max − min）  ← 参考尺
        # ⚠ 修订 226 账本里的 0.3460 是**极差**，不是相邻档差。
        # ⚠⚠⚠ 修订 232 查出一条**必须写在这里**的坑：**`jitter` 是极值统计量，
        # ⚖ 档位越多它只会越大** ⇒ 多测两档就会让「噪声主导」更容易成立。
        # ⚖ 本轮实测：多测两档后 p03__think 的 jitter 从 0.1300 涨到 0.3343
        # ⚖ ⇒ ⛔ **跨轮次的判决不可比**；要跨轮次比，请用 `jitter_med`。
        los = [c["reading"]["p9_lo_meas"] for c in ladder]
        diffs = [abs(los[i + 1] - los[i]) for i in range(len(los) - 1)]
        row["jitter"] = max(diffs) if diffs else None
        row["jitter_med"] = _median(diffs) if diffs else None
        row["span"] = (max(los) - min(los)) if los else None
        row["k_lo"] = ladder[0]["k"] if ladder else None
        row["k_hi"] = ladder[-1]["k"] if ladder else None

        a = ends.get("all")
        s = ends.get("single")
        row["drift_single_all"] = (a["reading"]["p9_lo_meas"]
                                   - s["reading"]["p9_lo_meas"]) if (a and s) else None
        if a and ladder:
            row["drift_khi_all"] = (a["reading"]["p9_lo_meas"]
                                    - ladder[-1]["reading"]["p9_lo_meas"])
        else:
            row["drift_khi_all"] = None
        # ⚖⚖ 位置身份效应：`single` 就是「1 个位点、位置=prefix 最后一位」
        # ⚖ （inject_at 的 inj = ids.shape[1]-1），而 `k=1` 是「1 个位点、
        # ⚖ 位置=种子 0 置换里的那个」⇒ **两者位点数相同，只有位置身份不同**。
        # ⚖⇒ `single − k=1` 直接量出位置身份的效应，⛔ 不需要另跑一档。
        # ⚠ 阶梯里若没有 k=1 那一档（如 p03__think 从 k=3 起），就是「未量到」。
        one = next((c for c in ladder if c["k"] == 1), None)
        row["k_one"] = one
        lo_s = s["reading"]["p9_lo_meas"] if s else None
        lo_1 = one["reading"]["p9_lo_meas"] if one else None
        row["drift_single_k1"] = (lo_s - lo_1) if (lo_s is not None and lo_1 is not None) else None
        # ⚖⚖ 尾段（≥50% + `all`）逐档。修订 229 §229.5 记的是
        # ⚖ 「50%–100% 之间**只有两个点**，中间是空的」；修订 232 补了 3/4、7/8
        # ⚖ ⇒ 这一段变成四点 ⇒ ⛔「最后一步是不是真的只有一步」现在可判了。
        pts = []
        if n_eff:
            for c in ladder:
                # ⚖ 阈值按**整数**判 `k*2 >= n_eff`，⛔ 不用百分比浮点。
                # ⚖⚠ 2026-10-17 更正我自己一次**误判**：我曾把
                # ⚖ `p03__no_think` 的 k=570 被排除当成「差 0.04% 的缺陷」，
                # ⚗ 其实是 `n_eff=1141` 的一半是 **570.5**，`2×570=1140 < 1141`
                # ⚗ ⇒ k=570 **确实在半数以下**，⛔ 排除是对的，不是 bug。
                # ⚖ 整数比与百分比判据等价，但少一层浮点面，值得保留。
                if c["k"] * 2 >= n_eff:
                    pts.append((100.0 * c["k"] / n_eff, "k=%d" % c["k"],
                                c["reading"]["p9_lo_meas"]))
        if a:
            pts.append((100.0, "all", a["reading"]["p9_lo_meas"]))
        pts.sort(key=lambda x: x[0])
        row["tail"] = pts
        # ⚖ 尾段里逐档差**超过抖动地板**的次数 ⇒ 0 就是「整段都落在噪声内」
        # ⚖ 两个尺子各数一遍：max 是极值（随档位变多而变大），med 才是稳健的那个
        jx, jm = row.get("jitter"), row.get("jitter_med")
        row["tail_jitter_exceed"] = (
            sum(1 for j in range(1, len(pts)) if jx is not None
                and abs(pts[j][2] - pts[j - 1][2]) > jx),
            sum(1 for j in range(1, len(pts)) if jm is not None
                and abs(pts[j][2] - pts[j - 1][2]) > jm))
        per[t] = row

    # ---- 判决：差值 vs 抖动
    for t, r in per.items():
        r["verdict_khi"] = _verdict(r["drift_khi_all"], r["jitter"])
        r["verdict_single"] = _verdict(r["drift_single_all"], r["jitter"])
        r["verdict_posid"] = _verdict(r["drift_single_k1"], r["jitter"])
        # ⚖ 稳健尺的同一批判决（跨轮次可比用这一组）
        r["verdict_khi_med"] = _verdict(r["drift_khi_all"], r["jitter_med"])
        r["verdict_single_med"] = _verdict(r["drift_single_all"], r["jitter_med"])
        r["verdict_posid_med"] = _verdict(r["drift_single_k1"], r["jitter_med"])

    # ---- 分层符号检验：轨迹级 vs 问题级
    tr = [per[t]["drift_khi_all"] for t in tids if per[t]["drift_khi_all"] is not None]
    prob = {}
    for t in tids:
        p = re.sub(r"__(?:no_)?think$", "", t) or t
        d = per[t]["drift_khi_all"]
        if d is None:
            continue
        prob.setdefault(p, []).append(d)
    pd_ = [_median(v) for v in prob.values()]

    # ---- 位置身份：single − k=1（位点数相同，只有位置不同）
    pid = [per[t]["drift_single_k1"] for t in tids
           if per[t]["drift_single_k1"] is not None]
    pid_prob = {}
    for t in tids:
        p = re.sub(r"__(?:no_)?think$", "", t) or t
        d = per[t]["drift_single_k1"]
        if d is not None:
            pid_prob.setdefault(p, []).append(d)
    pid_pd = [_median(v) for v in pid_prob.values()]

    return {"arm": arms[0] if arms else None,
            "nested": nested[0] if nested else None,
            "n_cells": len(cells), "n_ok": len(ok), "n_bad": len(bad),
            "bad": bad, "tids": tids, "per": per,
            "traj": sign_test(tr), "prob": sign_test(pd_),
            "pid_traj": sign_test(pid), "pid_prob": sign_test(pid_pd),
            "n_pid": len(pid),
            "n_problems": len(prob)}


def _verdict(diff, jitter):
    """⚠⚠⁴ 差值 ≪ 抖动 ⇒ 只能写「噪声主导」。"""
    if diff is None:
        return "未量到（缺比较所需的格子）"
    if jitter is None or jitter == 0.0:
        return "未量到（阶梯只有 1 档，没有抖动可比）"
    if abs(diff) < jitter:
        return "噪声主导（|Δ|=%.4f < 同曲线抖动 %.4f）" % (abs(diff), jitter)
    return "超过抖动（|Δ|=%.4f ≥ 抖动 %.4f）" % (abs(diff), jitter)


# ---------------------------------------------------------------- 报告


def report(r, verbose=True):
    L = []
    L.append("=" * 78)
    L.append("r227 k 曲线读数器    臂=%s  嵌套=%s" % (r["arm"], r["nested"]))
    L.append("=" * 78)

    # 【0】分母与缺口 —— 崩的格单独报，绝不当 0
    L.append("\n【0】覆盖面：共 %d 格 —— 有读数 %d，⛔ 无读数 %d"
             % (r["n_cells"], r["n_ok"], r["n_bad"]))
    if r["n_bad"]:
        L.append("    ⛔ 以下格子**没有读数**，不进任何分母（不是 0）：")
        for c in r["bad"]:
            L.append("      #%-3d %-28s k/口径=%s rc=%d  %s"
                     % (c["idx"], c["tid"],
                        c["k"] if c["scope"] == "k" else (c["scope"] or "?"),
                        c["rc"], c["err"]))
    else:
        L.append("    ✅ 无崩格")

    # 【1】逐条曲线
    L.append("\n【1】逐轨迹 k 曲线（n_eff = P + t，仪器吃前缀）")
    for t in r["tids"]:
        p = r["per"][t]
        L.append("\n  ── %s   n_eff=%s（来源：%s）   格数=%d（崩 %d）"
                 % (t, p["n_eff"], p["n_eff_src"], p["n_cells"], p["n_crash"]))
        L.append("     %-10s %-12s %-12s %-10s" % ("口径/k", "k/n_eff", "lo", "hi"))
        for c in p["ladder"]:
            rr = c["reading"]
            frac = 100.0 * c["k"] / p["n_eff"] if (p["n_eff"] and c["k"]) else float("nan")
            L.append("     k=%-7d %5.1f%%       %+.4f      %+.4f"
                     % (c["k"], frac, rr["p9_lo_meas"], rr["p9_hi_meas"]))
        for sc in SCOPES:
            c = p[sc]
            if c is None:
                L.append("     %-10s ⛔ 未量到" % sc)
            else:
                rr = c["reading"]
                frac = (100.0 if sc == "all" else
                        (100.0 * c["reading"]["t"] / p["n_eff"] if p["n_eff"] else float("nan")))
                L.append("     %-10s %5.1f%%       %+.4f      %+.4f"
                         % (sc, frac, rr["p9_lo_meas"], rr["p9_hi_meas"]))

    # 【2】两个**不同的问题**，必须分开读
    L.append("\n【2】两个不同的问题（⚠⚠ 别把它们当同一条曲线上的两点看）")
    L.append("    ⚠⚠ `single` 注入的是 prefix 的**最后一位**（inj = n_eff−1），")
    L.append("    ⚖ 而 `k=1` 挑的是种子 0 置换里的某个位置 ⇒ **位点身份不同**。")
    L.append("    ⚗ 所以 `single→all` 那列是**口径差**（修订 219–221 那个问题），")
    L.append("    ⚗ ⛔ **不是**剂量曲线上的一点。剂量问题只看 `k_hi→all`。")
    L.append("     %-28s %-15s %-15s %-10s %-10s %-10s"
             % ("tid", "k_hi→all(剂量)", "single→all(口径)",
                "相邻档差max", "相邻档差med", "极差"))
    for t in r["tids"]:
        p = r["per"][t]
        d1 = p["drift_single_all"]
        d2 = p["drift_khi_all"]
        L.append("     %-28s %-15s %-15s %-10s %-10s %-10s"
                 % (t,
                    "%+.4f" % d2 if d2 is not None else "未量到",
                    "%+.4f" % d1 if d1 is not None else "未量到",
                    "%.4f" % p["jitter"] if p["jitter"] is not None else "未量到",
                    "%.4f" % p["jitter_med"] if p["jitter_med"] is not None else "未量到",
                    "%.4f" % p["span"] if p["span"] is not None else "未量到"))
    L.append("    ⚠⚠⚠ **`相邻档差max` 是极值统计量，档位越多它只会越大** ⇒")
    L.append("       多测两档就会让「噪声主导」更容易成立。⚖ 本轮实测 p03__think 的")
    L.append("       max 从 0.1300 涨到 0.3343 ⇒ ⛔ **跨轮次的判决不可比**。")
    L.append("       ⚖ 要跨轮次比，请看 `相邻档差med`（中位数，对档位数不敏感）。")
    L.append("")
    for t in r["tids"]:
        p = r["per"][t]
        L.append("     %-28s k_hi(剂量)  max尺: %s" % (t, p["verdict_khi"]))
        L.append("     %-28s             med尺: %s" % (t, p["verdict_khi_med"]))
        L.append("     %-28s single(口径) max尺: %s" % (t, p["verdict_single"]))
        L.append("     %-28s             med尺: %s" % (t, p["verdict_single_med"]))

    # 【3】分层符号检验（**精确**二项，⛔ 不用正态近似）
    L.append("\n【3】符号检验（k_hi→all 的漂移，剂量问题）—— ⚠ 轨迹 ≠ 独立问题")
    L.append("    ⚖ **精确**双尾二项符号检验。⛔ 小 n 时正态近似会给出**比理论下界还小**")
    L.append("       的 p（n=4 全同向：近似 0.0455 vs 精确 0.125）⇒ 那是伪影不是结论。")
    for name, st, n, label in (("轨迹级", r["traj"], len(r["tids"]), "轨迹"),
                               ("问题级", r["prob"], r["n_problems"], "问题")):
        p_, pos, neg, tie, lb, z = st
        if p_ is None:
            L.append("     %s：⛔ 无漂移读数，没法检验（不是「无差异」）" % name)
            continue
        L.append("     %s n=%-3d 正%2d/负%2d/零%2d  p=%.4g（精确）"
                 % (name, pos + neg, pos, neg, tie, p_))
        L.append("            功效下界 2/2^n = %.3g%s"
                 % (lb, "   ⚠⚠ > 0.05 ⇒ 这套设计结构上到不了 0.05"
                    if lb > 0.05 else ""))
        if p_ < lb:
            L.append("            ⛔⛔ p < 下界 —— 内部矛盾，检验本身坏了")
    L.append("     ⚖ %d 条轨迹只来自 %d 个问题（think / no_think 同属一个问题）"
             % (len(r["tids"]), r["n_problems"]))

    # 【4】位置身份：single − k=1（**位点数相同，只有位置不同**）
    L.append("\n【4】位置身份效应 = `single` − `k=1`")
    L.append("    ⚖ 两者都是**只注入 1 个位点**；`single` 的位置是 prefix 最后一位，")
    L.append("    ⚖ `k=1` 的位置是种子 0 置换里的那个 ⇒ **位点数恒同，只有身份不同**。")
    L.append("    ⚗ 所以这个差**不需要**另跑一档，它已经在数据里了。")
    L.append("     %-28s %-12s %-12s %-10s" % ("tid", "single−k=1", "max尺", "med尺"))
    for t in r["tids"]:
        p = r["per"][t]
        d = p["drift_single_k1"]
        one = p.get("k_one")
        if d is None:
            why = "缺 k=1 档（阶梯最小 k=%s）" % (one["k"] if one else "无")
            L.append("     %-28s %-12s %-12s %s" % (t, "未量到", "—", why))
            continue
        L.append("     %-28s %-12s %-12s %-10s"
                 % (t, "%+.4f" % d, p["verdict_posid"], p["verdict_posid_med"]))
    L.append("")
    for name, st in (("轨迹级", r["pid_traj"]), ("问题级", r["pid_prob"])):
        p_, pos, neg, tie, lb, z = st
        if p_ is None:
            L.append("     位置身份 %s：⛔ 没有可比的格子（不是「无差异」）" % name)
            continue
        L.append("     位置身份 %s n=%-3d 正%2d/负%2d/零%2d  p=%.4g（精确）  下界 %.3g%s"
                 % (name, pos + neg, pos, neg, tie, p_, lb,
                    "   ⚠⚠ > 0.05" if lb > 0.05 else ""))
    L.append("     ⚖ 有 %d/%d 条轨迹能算这个差（⛔ 其余是「未量到」，不是 0）"
             % (r["n_pid"], len(r["tids"])))

    # 【5】尾段细分（≥50% + all）—— 回答「50%→100% 是不是真的只有一步」
    L.append("\n【5】尾段细分（覆盖率 ≥50% 的档 + `all`）")
    L.append("    ⚖ 修订 229 记的是「50%–100% 之间只有两个点，中间是空的」；")
    L.append("    ⚖ 补了 3/4、7/8 之后这一段才有四档 ⇒ 逐步的差才可判。")
    for t in r["tids"]:
        p = r["per"][t]
        tail = p.get("tail") or []
        if len(tail) < 2:
            L.append("\n  ── %s   ⛔ 尾段只有 %d 个点，没法分步（不是「无差异」）"
                     % (t, len(tail)))
            continue
        j = p["jitter"]
        jm = p["jitter_med"]
        L.append("\n  ── %s   尾段 %d 档，max尺 %s / med尺 %s"
                 % (t, len(tail),
                    ("%.4f" % j) if j is not None else "未量到",
                    ("%.4f" % jm) if jm is not None else "未量到"))
        L.append("     %-10s %-9s %-11s %-20s" % ("档", "覆盖", "lo", "与上一档之差"))
        for idx, (frac, lab, lo) in enumerate(tail):
            if idx == 0:
                d = "—"
            else:
                delta = lo - tail[idx - 1][2]
                mk = ""
                if j is not None:
                    mk += "⛔超max" if abs(delta) > j else "max内"
                if jm is not None:
                    mk += " ⛔超med" if abs(delta) > jm else " med内"
                d = "%+.4f  %s" % (delta, mk)
            L.append("     %-10s %5.1f%%   %+.4f      %s" % (lab, frac, lo, d))
        ex_max, ex_med = p["tail_jitter_exceed"]
        L.append("     ⇒ 逐档差超过地板的次数：max尺 %d 次%s"
                 % (ex_max, "（整段落在噪声内）" if ex_max == 0 else ""))
        L.append("       ⚖ med尺 %d 次%s"
                 % (ex_med, "（整段落在噪声内）" if ex_med == 0 else ""))
    return "\n".join(L)

# ---------------------------------------------------------------- 自检


# ⚖ 合成数据的形状是**故意**设计的，不是随手写的：
# ⚖ 阶梯相邻档大幅振荡，且**最大步与中位步不相等**（0.40 vs 0.36），
# ⚖ 这样「判决尺=max」与「稳健尺=med」两套判决能被**区分开**测。
LADDER_LO = [0.00, 0.40, 0.05, 0.42]
SINGLE_LO = 0.30
ALL_LO = 0.20


def _synthetic(mutate=None, ks=None):
    """造一份格式真实的合成日志 + 状态文件（每块自带 P + t = n_eff）。"""
    cells = [("aime__aime25__p00__think", 1762, ["1", "6", "27", "110"]),
             ("aime__aime25__p00__no_think", 490, ["1", "7", "30", "122"])]
    if ks is not None:
        cells = [(t, n, list(ks)) for t, n, _ in cells]
    log = []
    st = []
    i = 0
    for tid, n_eff, klist in cells:
        for j, k in enumerate(klist):
            i += 1
            log.append("### BEGIN %s n_eff=%d  00:%02d:%02d" % (tid, n_eff, 0, i))
            log.append('{"tid": "%s", "p9_lo_meas": %.6f, "p9_hi_meas": -0.01, '
                       '"inject_scope": "k", "inject_n_sites": %s, '
                       '"inject_nested": true, "arm": "rand", "P": 108, "t": %d}'
                       % (tid, LADDER_LO[j % len(LADDER_LO)], k, n_eff - 108))
            st.append("%s k=%s rc=0" % (tid, k))
        for sc, lo in (("single", SINGLE_LO), ("all", ALL_LO)):
            i += 1
            log.append("### BEGIN %s %s n_eff=%d  00:%02d:%02d" % (tid, sc, n_eff, 0, i))
            log.append('{"tid": "%s", "p9_lo_meas": %.6f, "p9_hi_meas": -0.01, '
                       '"inject_scope": "%s", "inject_nested": true, "arm": "rand", '
                       '"P": 108, "t": %d}' % (tid, lo, sc, n_eff - 108))
            st.append("%s %s rc=0" % (tid, sc))
    if mutate:
        log, st = mutate(log, st)
    return "\n".join(log) + "\n", "\n".join(st) + "\n"


def _read_pair(log_text, st_text):
    return join(parse_blocks(log_text), parse_status(st_text)[0])


def selftest():
    T = []

    def ck(name, fn):
        try:
            fn()
            T.append((name, "PASS", ""))
        except AssertionError as e:
            T.append((name, "FAIL", str(e) or "断言失败"))
        except Exception as e:
            T.append((name, "FAIL", "%s: %s" % (type(e).__name__, e)))

    # K1 绿：格式真实的一轮全部读出
    def k1():
        lg, st = _synthetic()
        cs = _read_pair(lg, st)
        assert len(cs) == 12, len(cs)
        assert all(c["reading"] is not None for c in cs)
        r = analyze(cs)
        assert r["n_ok"] == 12 and r["n_bad"] == 0, (r["n_ok"], r["n_bad"])
        assert r["n_problems"] == 1, r["n_problems"]
    ck("K1 绿：12 格全读出，崩格 0，问题数 1", k1)

    # K2 红：删掉一格读数 ⇒ 必须报「无读数」且绝不当 0；后续 k 不得错位
    def k2():
        def mut(log, st):
            out = []
            for ln in log:
                if ln.strip().startswith('{"tid"') and '"inject_n_sites": 6' in ln:
                    out.append("Traceback (most recent call last):")
                    out.append("ValueError: k 越界")
                    continue
                out.append(ln)
            # 同步把该格 rc 改成 1
            st = [s.replace("think k=6 rc=0", "think k=6 rc=1") for s in st]
            return out, st
        lg, st = _synthetic(mutate=mut)
        cs = _read_pair(lg, st)
        r = analyze(cs)
        assert r["n_bad"] == 1, r["n_bad"]
        assert r["n_ok"] == 11, r["n_ok"]
        # ⛔ 崩格不得有读数、不得被填成 0
        bad = r["bad"][0]
        assert bad["reading"] is None, "崩格被填了读数"
        assert bad["err"] and "ValueError" in bad["err"], bad["err"]
        # ⚖ 关键：崩格之后的每格 k 必须还是它自己的 k（防错位一格）
        after = [c["k"] for c in cs if c["idx"] > bad["idx"] and c["scope"] == "k"]
        assert after == [27, 110, 1, 7, 30, 122], after
        # ⛔ 崩格不进任何分母
        assert all(c["reading"] is not None for c in cs if c["idx"] > bad["idx"])
    ck("K2 红：删一格读数 ⇒ 报 1 格无读数，且后续 6 档 k 全部不错位", k2)

    # K3 红：状态行数少于块数 ⇒ 硬失败（不许读一半）
    def k3():
        lg, st = _synthetic()
        try:
            _read_pair(lg, "\n".join(st.strip().split("\n")[:-1]) + "\n")
            raise AssertionError("应当硬失败却读成功了")
        except HardFail as e:
            assert "不是同一轮" in str(e), str(e)
    ck("K3 红：状态少一行 ⇒ 硬失败而非读一半", k3)

    # K4 红：某一格状态里的 tid 被改坏 ⇒ 硬失败（防错位一格）
    def k4():
        lg, st = _synthetic()
        st = st.replace("aime__aime25__p00__think k=27", "aime__aime25__p00__WRONG k=27")
        try:
            _read_pair(lg, st)
            raise AssertionError("应当硬失败却读成功了")
        except HardFail as e:
            assert "tid 对不上" in str(e), str(e)
    ck("K4 红：状态 tid 改坏 ⇒ 硬失败", k4)

    # K5 红：状态里的 k 与读数自报的 k 不符 ⇒ 硬失败
    def k5():
        lg, st = _synthetic()
        st = st.replace("aime__aime25__p00__no_think k=30", "aime__aime25__p00__no_think k=31")
        try:
            _read_pair(lg, st)
            raise AssertionError("应当硬失败却读成功了")
        except HardFail as e:
            assert "k 不符" in str(e), str(e)
    ck("K5 红：状态 k ≠ 读数自报 k ⇒ 硬失败", k5)

    # K6 红：n_eff ≠ P + t（阶梯排错的唯一运行时证据）⇒ 硬失败
    def k6():
        lg, st = _synthetic()
        # 把 no_think 那组的 n_eff 从 490 改成整条序列长度 757
        lg = lg.replace("aime__aime25__p00__no_think n_eff=490",
                        "aime__aime25__p00__no_think n_eff=757")
        try:
            _read_pair(lg, st)
            raise AssertionError("应当硬失败却读成功了")
        except HardFail as e:
            assert "阶梯排错了" in str(e), str(e)
    ck("K6 红：n_eff ≠ P+t ⇒ 硬失败（正是修订 226 的错）", k6)

    # K7 红：一块里两条读数 ⇒ 硬失败（不许挑一条）
    def k7():
        def mut(log, st):
            out = []
            for ln in log:
                out.append(ln)
                if ln.strip().startswith('{"tid"') and '"inject_n_sites": 27' in ln:
                    out.append(ln)
            return out, st
        lg, st = _synthetic(mutate=mut)
        try:
            _read_pair(lg, st)
            raise AssertionError("应当硬失败却读成功了")
        except HardFail as e:
            assert "2 条读数" in str(e), str(e)
    ck("K7 红：一块两条读数 ⇒ 硬失败", k7)

    # K8 红：rc=0 却没有读数（状态与日志矛盾）⇒ 硬失败
    def k8():
        def mut(log, st):
            out = [ln for ln in log
                   if not (ln.strip().startswith('{"tid"')
                           and '"inject_n_sites": 6' in ln)]
            return out, st
        lg, st = _synthetic(mutate=mut)
        try:
            _read_pair(lg, st)
            raise AssertionError("应当硬失败却读成功了")
        except HardFail as e:
            assert "rc=0 却没读到" in str(e), str(e)
    ck("K8 红：rc=0 却无读数 ⇒ 硬失败", k8)

    # K9 绿：差值 ≪ 抖动 ⇒ 判决必须写「噪声主导」
    def k9():
        lg, st = _synthetic()
        cs = _read_pair(lg, st)
        r = analyze(cs)
        seen = 0
        for t in r["tids"]:
            p = r["per"][t]
            assert abs(p["drift_khi_all"]) < p["jitter"], \
                "夹具形状不对：漂移 %.4f 应小于抖动 %.4f" % (
                    abs(p["drift_khi_all"]), p["jitter"])
            assert "噪声主导" in p["verdict_khi"], p["verdict_khi"]
            assert "噪声主导" in p["verdict_single"], p["verdict_single"]
            seen += 1
        assert seen == 2, seen
    ck("K9 绿：差值 ≪ 抖动 ⇒ 判决印「噪声主导」（2 条轨迹都验到）", k9)

    # K10 绿：精确双尾符号检验 —— 全同向时 p **等于**功效下界
    def k10():
        for n in (4, 5, 8, 13):
            p, pos, neg, tie, lb, z = sign_test([1.0] * n)
            assert (pos, neg, tie) == (n, 0, 0), (n, pos, neg, tie)
            assert abs(lb - 2.0 ** (1 - n)) < 1e-15, (n, lb)
            assert abs(p - lb) < 1e-15, \
                "n=%d 全同向时精确 p 应等于下界 %r，实得 %r" % (n, lb, p)
            assert p >= lb, (n, p, lb)
        p5 = sign_test([1.0] * 5)[0]
        assert p5 > 0.05, "n=5 时 p=%.4f > 0.05，必须触发「结构上到不了」" % p5
        p_e, pos_e, neg_e, tie_e, lb_e, z_e = sign_test([])
        assert p_e is None and lb_e is None, (p_e, lb_e)
    ck("K10 绿：精确符号检验（全同向 p ≡ 下界 2/2^n，n=4..13）", k10)

    # K11 绿：只有 1 档阶梯 ⇒ 抖动不可比，必须写「未量到」而不是 0
    def k11():
        lg, st = _synthetic(ks=["1"])
        cs = _read_pair(lg, st)
        r = analyze(cs)
        for t in r["tids"]:
            assert r["per"][t]["jitter"] is None, r["per"][t]["jitter"]
            assert "未量到" in r["per"][t]["verdict_khi"], r["per"][t]["verdict_khi"]
    ck("K11 绿：单档阶梯 ⇒ 抖动不可比，报「未量到」", k11)

    # K12 红：曲线里混了不同臂 ⇒ 拒绝连成一条曲线
    def k12():
        lgt, st = _synthetic()
        lgt = lgt.replace('"arm": "rand"', '"arm": "w"', 1)
        cs = _read_pair(lgt, st)
        try:
            analyze(cs)
            raise AssertionError("应当拒绝却连了")
        except HardFail as e:
            assert "混了多个臂" in str(e), str(e)
    ck("K12 红：混臂 ⇒ 拒绝连成一条曲线", k12)

    # K13 绿：BEGIN 行没有 n_eff（r226 的格式）⇒ 从读数 P+t 回退，且标明未互证
    def k13():
        lg, st = _synthetic()
        lg = re.sub(r"\s*n_eff=\d+", "", lg)   # r226 的真实格式：整个 token 都没有
        assert "n_eff" not in lg.split("\n")[0], lg.split("\n")[0]
        cs = _read_pair(lg, st)
        r = analyze(cs)
        for t in r["tids"]:
            p = r["per"][t]
            assert p["n_eff"] in (1762, 490), p["n_eff"]
            assert "未与 BEGIN 互证" in p["n_eff_src"], p["n_eff_src"]
        # ⚖ 回退后 k/n_eff 必须真的算得出来（不再全是 nan）
        out = report(r)
        assert "nan%" not in out, "回退之后 k/n_eff 仍是 nan，说明没真用上 P+t"
        assert "24.9%" in out, "no_think 末档 122/490 应印 24.9%"
    ck("K13 绿：BEGIN 无 n_eff ⇒ 从 P+t 回退并标明未互证", k13)

    # K14 红：正态近似给 n=4 一个**比理论下界还小**的 p —— 那不是统计，是伪影
    # ⚠⚠ 这条是 2026-10-17 真机读数时撞出来的：读数器印了 p=0.0455，
    # ⚖ 却在同一屏印下界 2/2⁴=0.125 —— p 不可能低于下界，输出自相矛盾。
    def k14():
        p, pos, neg, tie, lb, z = sign_test([1.0] * 4)
        assert abs(p - 0.125) < 1e-12, \
            "n=4 全同向的精确 p 应为 0.125，实得 %r" % p
        # ⚖ 把正态近似也算出来，记住它有多离谱（这就是本条存在的理由）
        approx = math.erfc(abs((0 - 4) / math.sqrt(4)) / math.sqrt(2.0))
        assert abs(approx - 0.0455) < 1e-3, approx
        assert approx < lb, \
            "本条的前提是「正态近似低于下界」；若哪天不成立了请重写本条"
        # ⚖ 报告里绝不许出现 p < 下界（那是内部矛盾的信号）
        r = analyze(_read_pair(*_synthetic()))
        out = report(r)
        assert "内部矛盾" not in out, "报告自称内部矛盾"
        for line in out.split("\n"):
            if "（精确）" in line:
                m = re.search(r"p=([0-9.eE+-]+)", line)
                assert m, line
                val = float(m.group(1))
                assert 0.0 < val <= 1.0, line
    ck("K14 红：n=4 精确 p=0.125；正态近似的 0.0455 是伪影", k14)

    # K15 绿：位置身份差 = single − k=1；阶梯里没有 k=1 档时必须报「未量到」
    def k15():
        lg, st = _synthetic()
        r = analyze(_read_pair(lg, st))
        for t in r["tids"]:
            p = r["per"][t]
            assert p["k_one"] is not None, t
            assert p["drift_single_k1"] is not None, t
            # ⚖ 夹具：SINGLE_LO 减去第一档 LADDER_LO[0]
            assert abs(p["drift_single_k1"] - (SINGLE_LO - LADDER_LO[0])) < 1e-9, \
                p["drift_single_k1"]
        assert "【4】位置身份效应" in report(r)
        # ⚖ 阶梯最小档不是 1（如 p03__think 从 k=3 起）⇒ **未量到**，⛔ 不是 0
        lg2, st2 = _synthetic(ks=["6"])
        r2 = analyze(_read_pair(lg2, st2))
        for t in r2["tids"]:
            assert r2["per"][t]["k_one"] is None, t
            assert r2["per"][t]["drift_single_k1"] is None, \
                "没有 k=1 档却算出了位置身份差"
            assert "未量到" in r2["per"][t]["verdict_posid"], \
                r2["per"][t]["verdict_posid"]
        assert r2["n_pid"] == 0, r2["n_pid"]
        out2 = report(r2)
        assert "缺 k=1 档" in out2, out2[-700:]
    ck("K15 绿：位置身份差 = single−k=1；无 k=1 档 ⇒ 报「未量到」不是 0", k15)

    # K16 红：**重复档**必须硬失败 —— 这是「追加进同一份日志」驱动形态的专属风险
    def k16():
        def mut(log, st):
            # ⚖ `mutate` 收到的是**行列表**，⛔ 不是字符串（见 `_synthetic`）
            return list(log) + log[:2], list(st) + [st[0]]
        lg, st = _synthetic(mutate=mut)
        try:
            _read_pair(lg, st)
            raise AssertionError("应当硬失败却读成功了 —— 重复档被静默读进来了")
        except HardFail as e:
            assert "重复" in str(e), str(e)
            assert "虚增抖动地板" in str(e), str(e)
    ck("K16 红：同一档跑两遍 ⇒ 硬失败（否则虚增抖动地板、该档被算两次）", k16)

    # K17 绿：尾段（≥50% + all）逐档展开；尾段不足 2 点 ⇒ 「未量到」不是 0
    def k17():
        lg, st = _synthetic()
        r = analyze(_read_pair(lg, st))
        out = report(r)
        assert "【5】尾段细分" in out
        for t in r["tids"]:
            tail = r["per"][t]["tail"]
            # ⚖ 夹具里 max k = 110，而 n_eff=1762 ⇒ 110/1762 = 6.2% < 50%
            # ⚖ ⇒ k 档一档都不进尾段，只有 `all` ⇒ ⛔ 不足 2 点
            assert len(tail) == 1, (t, tail)
            assert "没法分步" in report(r) and t in report(r)
        # ⚖ 再造一份**尾段够长**的：把阶梯拉到覆盖 ≥50%
        lg2, st2 = _synthetic(ks=["1100", "1400", "1700"])
        r2 = analyze(_read_pair(lg2, st2))
        assert len(r2["per"][r2["tids"][0]]["tail"]) == 4, \
            r2["per"][r2["tids"][0]]["tail"]      # 3 个 k 档 + all
        o2 = report(r2)
        assert "逐档差超过地板的次数" in o2
    ck("K17 绿：尾段逐档展开；尾段不足 2 点 ⇒ 报「没法分步」不是 0", k17)

    # K18 绿：稳健尺 `jitter_med` 必须是**中位数**，且 max ≥ med
    # ⚠⚠ 这条是修订 232 加的：`jitter`（max）是极值统计量，档位越多只会越大
    # ⚖ ⇒ 跨轮次比较必须用 med，而 med 若不小心写成了 max，整套稳健尺就白设。
    def k18():
        lg, st = _synthetic()
        r = analyze(_read_pair(lg, st))
        for t in r["tids"]:
            p = r["per"][t]
            los = [LADDER_LO[i % len(LADDER_LO)]
                   for i in range(len(p["ladder"]))]
            diffs = sorted(abs(los[i + 1] - los[i]) for i in range(len(los) - 1))
            exp_med = diffs[len(diffs) // 2] if len(diffs) % 2 else \
                0.5 * (diffs[len(diffs) // 2 - 1] + diffs[len(diffs) // 2])
            assert abs(p["jitter_med"] - exp_med) < 1e-12, \
                "%s jitter_med=%r 应为中位数 %r" % (t, p["jitter_med"], exp_med)
            assert abs(p["jitter"] - max(diffs)) < 1e-12, (t, p["jitter"])
            assert p["jitter"] >= p["jitter_med"], \
                "max %r 必须 ≥ med %r" % (p["jitter"], p["jitter_med"])
            # ⚖ 夹具刻意让两者不相等 ⇒ 否则「med 其实是 max」测不出来
            assert p["jitter"] > p["jitter_med"], \
                "夹具形状不对：max %r 与 med %r 相等，测不出区别" % (
                    p["jitter"], p["jitter_med"])
    ck("K18 绿：稳健尺是**中位数**不是 max（且 max ≥ med、两者不相等）", k18)

    npass = sum(1 for _, s, _ in T if s == "PASS")
    for name, st_, msg in T:
        print("[%s] %s%s" % (st_, name, ("  ← " + msg) if msg else ""))
    print("r227_kcurve --selftest: %d/%d" % (npass, len(T)))
    return 0 if npass == len(T) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="扫描日志（含 ### BEGIN 分块）")
    ap.add_argument("--status", help="状态文件（每格一行 + ALLDONE）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.log or not a.status:
        ap.error("需要 --log 与 --status（或 --selftest）")

    try:
        with open(a.log) as f:
            log_text = f.read()
        with open(a.status) as f:
            st_text = f.read()
    except IOError as e:
        print("读不了文件：%s" % e, file=sys.stderr)
        return 3

    blocks = parse_blocks(log_text)
    rows, alldone = parse_status(st_text)
    try:
        if alldone is None:
            print("⚠⚠ 状态文件没有 ALLDONE —— 这一轮**可能还在跑**，"
                  "读数是部分的", file=sys.stderr)
        cells = join(blocks, rows)
        r = analyze(cells)
    except HardFail as e:
        print("⛔ 校验不过，拒绝读：%s" % e, file=sys.stderr)
        return 2

    print(report(r))
    if alldone:
        print("\n✅ 状态文件末尾有 ALLEDONE（实为 ALLDONE %s）—— 这一轮跑完了" % alldone)
    else:
        print("\n⚠ 没有 ALLDONE —— 以上是部分读数")
    return 0


if __name__ == "__main__":
    sys.exit(main())
