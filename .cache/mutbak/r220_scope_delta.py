#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r220_scope_delta —— 两份 `r6_rerun.py --smoke` 产物的**口径差**对账。

## 这条在量什么

修订 218 查明 P6 读数源一直用「单点注入 + 纯 prefill」，与流水线的
「全位置广播 + 增量解码」不是同一个量。修订 219 给 `r6_rerun.py` 加了
`--inject-scope {single,all}`（默认 `single` 不变），于是现在**同一台装置**
可以按两种口径各跑一次。

⛔ 本脚本量的是「**P6 自己的仪器**上两种口径差多少」，
⚠ **不是**修订 209/210 那个数 —— 那是在探针 `r204_noise_probe.py` 上量的。
⚠⚠⛔ 两者不可互相替代：探针的量 ≠ 仪器的量（口径、步数、读数点都不同）。

## ⚠⚠⁴ 报数纪律（照抄，不许省）

1. ⚠⚠⁴ 「一致」这句话**不携带覆盖面** ⇒ 必须同报**在哪些格、哪些读数点上验的**，
   以及 ⛔ **没验的范围**（本脚本只比 `--smoke` 的 P9 bench，不含全量 `rows`）。
2. ⚠⚠ **分母为 0 时不许印「一致」** —— 那不是「一致」，是「没量到」。
3. ⚠⚠ 只报 |Δ| 对方向性主张**无分辨力** ⇒ 必须同报**符号构成** + 符号检验。
4. ⚠⚠ 「A 相对 B 涨了 N%」必须说清分子分母各自怎么取；本脚本因此同时给
   「中位数之比」与「逐格比值的中位数」，并给出**逐格方向**。
5. ⚠⚠⛔ **一次对照只改一个变量** ⇒ 先检查两份产物**除口径外**是否逐字段相同；
   不同就**拒绝**把差归给口径。

跑法：
    python3 r220_scope_delta.py --a before.json --b after.json \
        [--label-a 改之前] [--label-b 改之后]
退出码：0 = 读完了；1 = 读不了（文件缺失/非 json/无 bench）。
⚠⚠ 退出码**不表示**「两个口径差多少」——那是一个数，不是一个判决。
"""

import argparse
import json
import math
import sys

# ⚠ 纯出处的字段：**不是**读数，比较时必须排除。
# ⚠⚠⁴ 修订 221：`smoke_traj` / `smoke_traj_arg` 也进这里 ——
# ⚠⚠⁴ 它们决定**覆盖面**（比了几条轨迹），不是读数本身。
# ⚖ 但覆盖面差异**不许被静默**：compare_bench 的 only_in_a/only_in_b 会
# ⚖ 把格数不同这件事报出来，且报告【1】会印比较点数。
PROVENANCE_KEYS = ("inject_scope", "pos_ok", "device_validated",
                   "smoke_traj", "smoke_traj_arg")

# ⚠⚠⚠⚠ 修订 239：**`dose_source` 从 PROVENANCE_KEYS 里拿出来了**。
# ⚖ 它记的**不是出处，是「用的是哪个方向向量」**：
# ⚖   `w_meta`（从 meta 文件读的 w）／`retrained`（现重训）／
# ⚖⚠ **`FALLBACK_375`（向量没拿到时的硬编码兜底）**
# ⚖⚠⚠ 把它当「允许不同的出处字段」⇒ ⛔ **拿 w_meta 的一批去比 FALLBACK_375
# ⚖ 的一批，「一次只改一个变量」会判 PASS，⚖ 而那是**两个完全不同的方向向量**。
# ⚖ ⚗ 而 `report` 从头到尾**没印过 dose_source** ⇒ ⚖ 报告上一个字的提示都没有。
# ⚖⇒ 现在它必须**两边相同**；不同 ⇒ 「不是一次对照」。
# ⛔ 「出处不同」**从不**是「可以忽略的差别」。
DOSE_KEY = "dose_source"

# ⚠⚠⚠⚠ 修订 239.1：**三态，不是 bool。**
# ⚖⚠ 原来只有「相同 / 不同」两种。⚖ 但两边**都没记**时 `da == db` 成立
# ⚖ ⇒ 旧写法判成「同向量」⇒ 照样签发「一次对照 ⇒ 差可以归给口径」。
# ⚖ ⚗ 而**没法确认两臂用的是同一个向量**时，口径差**根本不可归因** ——
# ⚖ 「不知道」比「不同」还弱，⛔ 不能和「一样」共用一个说法。
DOSE_STATE_UNKNOWN = "unknown"
DOSE_STATE_SAME = "same"
DOSE_STATE_DIFFERENT = "different"

DOSE_STATE_NOTE = {
    DOSE_STATE_SAME: "",
    DOSE_STATE_DIFFERENT: "   ⛔⛔ **两边不是同一个方向向量**",
    DOSE_STATE_UNKNOWN: "   ⚠⚠ **未记录 ⇒ 无法确认是同一个方向向量**",
}

# ⚖⚠⚴ 修订 239.1：**守卫的措辞与报告头的措辞必须同源**。
# ⚖ 两处各写一句话，迟早写岔 ⇒ 出现「报告头说不一样、单变量守卫却放行」。
# ⚖⇒ 一张表按状态索引，⛔ 不许在别处另起一份措辞。
DOSE_STATE_REASON = {
    DOSE_STATE_DIFFERENT:
        "⛔⛔ **方向向量来源不同**（{k}：A={a!r} / B={b!r}）⇒ "
        "**不是一次对照**，差不能归给口径",
    DOSE_STATE_UNKNOWN:
        "⛔⛔ **{k} 未记录**（A={a!r} / B={b!r}）⇒ ⛔ 无法确认两边用的是"
        "**同一个方向向量**，差不能归给口径",
}


def dose_state(da, db):
    """`dose_source` 的三态。

    ⚖⚠⁴ 为什么不是 bool：⛔ 「没量到」是事实，「无差异」是结论，
    ⚖ 合成一个布尔值就等于把前者印成后者。
    """
    if da is None or db is None:
        return DOSE_STATE_UNKNOWN
    return DOSE_STATE_SAME if da == db else DOSE_STATE_DIFFERENT


def _sign_test(n_pos, n_neg):
    """符号检验。返回 (z, p)：`z` 是方向统计量，`p` 是**精确**双尾二项。

    ⚠⚠⁴ `p` **不用**正态近似 `erfc(|z|/√2)`。
    ⚖ 2026-10-17 实测：n=4 全同向时正态近似给 **p=0.0455**，
    ⚖ 而精确值是 **2/2⁴ = 0.125** —— ⚠⚠ 那个值**比理论下界还小**，
    ⚖ 等于报出了一个 n=4 下**不可能达到**的显著水平。
    ⚖⇒ 小样本符号检验必须用精确二项；任何时候 `p >= 2/2^n` 都应成立。
    ⚖ 分母为 0 返回 (None, None)。

    ⚗ `z` 仍然照报，但 ⚠ 它**不是** p 的计算依据（小 n 时不可用）。
    """
    n = n_pos + n_neg
    if n == 0:
        return None, None
    z = (n_pos - n_neg) / math.sqrt(n)
    k = min(n_pos, n_neg)
    obs = math.comb(n, k)
    probs = [math.comb(n, j) for j in range(n + 1)]
    p = sum(c for c in probs if c <= obs) / float(2 ** n)
    return z, p


def _cells(bench):
    """把 {tid: {"w+@0.5": v, ...}} 摊平成 [(tid, key, float), ...]。

    ⚠ **逐格摊平**：比较的单位是「一格上的一个读数」，
    ⚗ 不是「一条轨迹的一个和」—— 后者会把正负抵消掉。
    """
    out = []
    for tid in sorted(bench or {}):
        row = bench[tid] or {}
        for key in sorted(row):
            try:
                out.append((tid, key, float(row[key])))
            except (TypeError, ValueError):
                out.append((tid, key, None))
    return out


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def compare_bench(a_bench, b_bench, tol=0.0):
    """逐格比较两个 bench。返回 dict。

    ⚠ `tol=0.0` = 判**逐位相同**。这里不设默认容差：
    ⚗ 「差不多」不是「一样」，把容差留给调用方显式声明。
    """
    A = {(t, k): v for t, k, v in _cells(a_bench)}
    B = {(t, k): v for t, k, v in _cells(b_bench)}
    only_a = sorted(set(A) - set(B))
    only_b = sorted(set(B) - set(A))
    common = sorted(set(A) & set(B))

    n_exact = n_cmp = n_skip = 0
    deltas, pos, neg, zero = [], 0, 0, 0
    per_arm = {}
    for key in common:
        va, vb = A[key], B[key]
        if va is None or vb is None:          # ⛔ 有非数值格：不算「相同」也不造数
            n_skip += 1
            continue
        n_cmp += 1
        d = vb - va
        if abs(d) <= tol:
            n_exact += 1
            zero += 1
            deltas.append(0.0)
            continue
        deltas.append(d)
        if d > 0:
            pos += 1
        else:
            neg += 1
        arm = key[1].split("@")[0]
        per_arm.setdefault(arm, []).append(d)

    z, p = _sign_test(pos, neg)
    mag = [abs(d) for d in deltas]
    # ⚠ 「A 相对 B」的两个不同取法，**必须都报**（读的人无从判断你要的是哪个）
    med_a = _median([A[k] for k in common if A[k] is not None and B[k] is not None])
    med_b = _median([B[k] for k in common if A[k] is not None and B[k] is not None])
    ratio_of_medians = (med_b / med_a) if (med_a not in (None, 0.0)
                                           and med_b is not None) else None
    per_cell = [(B[k] / A[k]) for k in common
                if A[k] not in (None, 0.0) and B[k] is not None]
    # ⚠⚠⁴ **比值什么时候没有意义**：这里的读数本身是**差值**（logit 差），
    # ⚠⚠⁴ 中心就在 0 附近。若两边的水平（中位）比它们自己的抖动（|Δ| 量级）还小，
    # ⚖ 「A 相对 B 涨了 N%」就是拿两个接近 0 的数相除 —— 数字能算，但它不代表任何东西。
    # ⛔⇒ 必须**明说**，而不是把一个不稳的数印出来让人误用。
    abs_max = max(mag) if mag else None
    level_is_above_noise = (
        med_a is not None and med_b is not None and abs_max is not None
        and abs(med_a) > abs_max and abs(med_b) > abs_max)

    return {
        # ---- 覆盖面（不报这个，下面所有「一致」都无从检验）----
        "n_bench_rows": len(set(t for t, _ in common)),
        "n_common": len(common),
        "n_compared": n_cmp,          # ⛔ 真正的分母
        "n_skipped": n_skip,
        "only_in_a": only_a,
        "only_in_b": only_b,
        # ---- 逐位相同 ----
        "n_exact": n_exact,
        "frac_exact": (n_exact / n_cmp) if n_cmp else None,
        # ---- 幅度 ----
        "abs_med": _median(mag),
        "abs_max": max(mag) if mag else None,
        "abs_min": max(mag) if mag else None,
        # ---- ⛔ 方向：只报 |Δ| 时看不出「整体偏低」和「随机抖」的区别 ----
        "n_pos": pos, "n_neg": neg, "n_zero": zero,
        "sign_z": z, "sign_p": p,
        # ---- 「涨了 N%」的两种取法 ----
        "median_a": med_a, "median_b": med_b,
        "ratio_of_medians": ratio_of_medians,
        "median_of_per_cell_ratio": _median(per_cell),
        "level_is_above_noise": level_is_above_noise,
        "per_arm": {k: {"n": len(v), "med": _median([abs(x) for x in v]),
                        "max": max(abs(x) for x in v),
                        "n_pos": sum(1 for x in v if x > 0),
                        "n_neg": sum(1 for x in v if x < 0)}
                    for k, v in sorted(per_arm.items())},
    }


def compare_verdicts(a_v, b_v):
    """P9 判决的翻转。**判决翻转比幅度更能说明口径不是无关项。**"""
    A = {t: bool((a_v or {}).get(t, {}).get("ok")) for t in (a_v or {})}
    B = {t: bool((b_v or {}).get(t, {}).get("ok")) for t in (b_v or {})}
    flip = sorted(t for t in set(A) & set(B) if A[t] != B[t])
    return {"n": len(set(A) & set(B)),
            "n_ok_a": sum(1 for t in set(A) & set(B) if A[t]),
            "n_ok_b": sum(1 for t in set(A) & set(B) if B[t]),
            "flipped": flip, "n_flipped": len(flip)}


def check_single_variable(a, b):
    """⛔ 除口径外必须逐字段相同，否则差**不能**归给口径。"""
    reasons = []
    # ⚠⚠⚠⚠ 方向向量来源**必须一致** —— 它不是「出处」，是「治疗本身」。
    # ⛔ 两边来源不同 ⇒ ⛔ **不是一次对照**，⛔ 差**不能**归给口径。
    da, db = a.get(DOSE_KEY), b.get(DOSE_KEY)
    dst = dose_state(da, db)
    # ⚠⚠⚠⚠ **「没记」不等于「一样」**（修订 239.1 实测出来的）。
    # ⚖⚖ 两边都没记时 `da == db` 成立 ⇒ 只判 `da != db` 会判成「同向量」，
    # ⚖ 而单变量守卫照样签发「✅ 只有口径不同 ⇒ 差可以归给口径」。
    # ⚖⚗ 实测：`reasons == []`、`single_variable_ok == True`、判决照常往下走。
    # ⚖⇒ 「没法确认」时**拒绝归因**，⛔ 不是降级成一句脚注。
    # ⚖ 单个条件（非 if/elif）—— ⛔ 否则 F4 变异把 `if` 改成 `if False`
    # ⚖ 时 `elif` 那一支**仍然会跑**，变异体就变成半复原的。
    if dst != DOSE_STATE_SAME:
        reasons.append(DOSE_STATE_REASON[dst].format(k=DOSE_KEY, a=da, b=db))
    for k in sorted(set(a) | set(b)):
        if k in PROVENANCE_KEYS:
            continue
        if k not in a:
            reasons.append("B 有 A 没有的字段 %r" % k)
        elif k not in b:
            reasons.append("A 有 B 没有的字段 %r" % k)
        elif k in ("bench", "bench_v"):
            continue                      # 这两个由 compare_* 单独比
        elif a[k] != b[k]:
            reasons.append("字段 %r 两边不同" % k)
    return (len(reasons) == 0), reasons


def analyze(pa, pb, label_a="A", label_b="B"):
    """顶层：把上面几件事收成一份可直接读的判决。"""
    bench = compare_bench(pa.get("bench"), pb.get("bench"))
    verd = compare_verdicts(pa.get("bench_v"), pb.get("bench_v"))
    single_ok, reasons = check_single_variable(pa, pb)
    # ⚖ 三态算一次，报告头与守卫共用同一个判据（⛔ 不许两处各判一次）
    dst = dose_state(pa.get(DOSE_KEY), pb.get(DOSE_KEY))

    # ⛔ 分母为 0 **不许**报「一致」
    if bench["n_compared"] == 0:
        verdict = "没量到（比较点 0 个）—— 不是「一致」"
    elif bench["n_skipped"]:
        verdict = "有 %d 格非数值被跳过" % bench["n_skipped"]
    elif bench["n_exact"] == bench["n_compared"]:
        verdict = "逐位相同 %d/%d" % (bench["n_exact"], bench["n_compared"])
    else:
        verdict = "不逐位相同 %d/%d 恰为 0" % (bench["n_exact"], bench["n_compared"])

    return {
        "label_a": label_a, "label_b": label_b,
        "scope_a": pa.get("inject_scope", "（未记录）"),
        "scope_b": pb.get("inject_scope", "（未记录）"),
        # ⚠⚠⚠ 方向向量来源必须**印在报告头上**（修订 239）
        "dose_a": pa.get(DOSE_KEY, "（未记录）"),
        "dose_b": pb.get(DOSE_KEY, "（未记录）"),
        "dose_state": dst,
        # ⚖⚠ `dose_same` 只在**真的确认相同**时为 True —— 「没记」不是「一样」
        "dose_same": dst == DOSE_STATE_SAME,
        "bench": bench, "verdicts": verd,
        "single_variable_ok": single_ok, "single_variable_reasons": reasons,
        "verdict": verdict,
        "coverage_note": ("覆盖面 = --smoke 的 P9 bench（%d 条轨迹 × 读数点）；"
                          "⛔ 不含全量 rows、不含 P6 的 U 检验、不含生成文本"
                          % bench["n_bench_rows"]),
    }


def _fmt(v, spec="%.6f"):
    return "None" if v is None else (spec % v)


def _dose_head(a, r):
    """报告头里那一行 `dose_source`。⚖⚠ 三态分别说。

    ⚠ 抽成独立一行是为了让 F4 变异能**只**动这一处（⛔ 锚点落在
    ⚖ NAME token 上，不落在 STRING 或前导空白上）。
    """
    a("  %s：A = %s ｜ B = %s%s"
      % (DOSE_KEY, r["dose_a"], r["dose_b"], DOSE_STATE_NOTE[r["dose_state"]]))


def report(r):
    L = []
    a = L.append
    a("=" * 78)
    a("口径差对账：%s  →  %s" % (r["label_a"], r["label_b"]))
    a("  inject_scope：A = %s ｜ B = %s" % (r["scope_a"], r["scope_b"]))
    # ⚠⚠⚠ 方向向量来源 —— 以前**一个字都没印**，⚖ 而它是治疗本身
    _dose_head(a, r)
    a("=" * 78)

    a("")
    a("【0】一次对照只改一个变量？")
    if r["single_variable_ok"]:
        a("  ✅ 除口径外逐字段相同 ⇒ 下面的差可以归给口径")
    else:
        a("  ⛔⛔ 不止一个变量变了，下面的差**不能**归给口径：")
        for x in r["single_variable_reasons"]:
            a("      - %s" % x)

    b = r["bench"]
    a("")
    a("【1】覆盖面（不报这个，「一致」无从检验）")
    a("  比较点 %d 个（%d 条轨迹）｜ 跳过 %d ｜ 只在 A %d ｜ 只在 B %d"
      % (b["n_compared"], b["n_bench_rows"], b["n_skipped"],
         len(b["only_in_a"]), len(b["only_in_b"])))
    a("  %s" % r["coverage_note"])

    a("")
    a("【2】逐位相同")
    a("  %s" % r["verdict"])

    a("")
    a("【3】幅度（只报 |Δ| 看不出方向，见下一节）")
    a("  |Δ| min %s ｜ 中位 %s ｜ max %s"
      % (_fmt(b["abs_min"]), _fmt(b["abs_med"]), _fmt(b["abs_max"])))

    a("")
    a("【4】⛔ 方向：符号构成")
    a("  正 %d ｜ 负 %d ｜ 恰为 0 %d" % (b["n_pos"], b["n_neg"], b["n_zero"]))
    if b["sign_z"] is None:
        a("  符号检验：**无非零差异** ⇒ 无方向可言")
    else:
        a("  符号检验 z = %+.4f，双尾 p = %.3g" % (b["sign_z"], b["sign_p"]))
    for arm, s in b["per_arm"].items():
        a("    %-6s n=%-3d |Δ| 中位 %-12s max %-12s 正 %d / 负 %d"
          % (arm, s["n"], _fmt(s["med"]), _fmt(s["max"]), s["n_pos"], s["n_neg"]))

    a("")
    a("【5】「相对变化」的两种取法（读的人无从判断你要哪个，所以都给）")
    a("  A 中位 %s ｜ B 中位 %s" % (_fmt(b["median_a"]), _fmt(b["median_b"])))
    if not b["level_is_above_noise"]:
        a("  ⛔⛔ **本批的比值没有意义，别引用**：")
        a("      读数本身是**差值**，中心落在 0 附近；而两边的水平（中位 %s / %s）"
          % (_fmt(b["median_a"]), _fmt(b["median_b"])))
        a("      比它们自己的 |Δ| 量级（max %s）还小 ⇒ 拿接近 0 的数相除，"
          % _fmt(b["abs_max"]))
        a("      算得出数，但那个数不代表任何东西。")
        a("      ⇒ 本批该读的是**【3】幅度**与**【4】符号构成**。")
    else:
        a("  中位数之比       = %s" % _fmt(b["ratio_of_medians"]))
        a("  逐格比值的中位数 = %s" % _fmt(b["median_of_per_cell_ratio"]))
        a("  ⚠⚠ 两者是**不同的量**；若 B 侧右偏，中位数之比会把方向讲反。")

    v = r["verdicts"]
    a("")
    a("【6】P9 判决翻转（幅度之外的独立证据）")
    a("  A 通过 %d/%d ｜ B 通过 %d/%d ｜ 翻转 %d 条"
      % (v["n_ok_a"], v["n"], v["n_ok_b"], v["n"], v["n_flipped"]))
    for t in v["flipped"]:
        a("    - %s" % t)

    a("")
    a("判决：%s" % r["verdict"])
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    try:
        pa = json.load(open(args.a, encoding="utf-8"))
        pb = json.load(open(args.b, encoding="utf-8"))
    except Exception as exc:                              # noqa: BLE001
        print("⛔ 读不了产物：%r" % (exc,), flush=True)
        return 1
    if not isinstance(pa.get("bench"), dict) or not isinstance(pb.get("bench"), dict):
        print("⛔ 产物里没有 bench —— 这不是 r6_rerun.py --smoke 的产物", flush=True)
        return 1

    r = analyze(pa, pb, args.label_a, args.label_b)
    print(report(r), flush=True)
    if args.out:
        json.dump(r, open(args.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\n[落盘] %s" % args.out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
