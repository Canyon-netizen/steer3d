#!/usr/bin/env python3
"""分叉那一步到底发生了什么：定向贬低 incumbent，还是全局重加权？

为什么问这个
------------
已有机制量给出：6/6 题的净间距都**变宽**，而 4/6 题原赢家的分数**下降**。
「赢家被削弱」有两种完全不同的读法，指向完全不同的解释：

  A. **定向贬低**：只有 incumbent 被压下去，其余候选基本不动
     ⇒ 向量在做一个「把这个词从候选里拿掉」的动作。
  B. **全局重加权**：一大片词同向移动，incumbent 只是在幅度上 unlucky
     ⇒ 向量是旋转/重加权表征，incumbent 掉分只是副作用。

这两种解释对「怎么用它」的建议完全相反：A 说可以拿它做候选抑制，
B 说它根本没有指向性。所以必须分开。

判据
----
对 6 道题的分叉步 k，把两臂的 top-8 按 **id** 对齐（不是按排名），
逐个算 Δ = g_s − g_c，然后看：
  · Δ 的符号分布（有多少词掉、多少词涨）
  · incumbent 的 Δ 在全体里的**分位**（它是不是最特殊的那几个之一）
  · 若「全局同向」成立，则 Δ 应**中位数远离 0**（同向堆积）
  · 若「定向」成立，则 Δ 应**以 0 为中心散开**，而 incumbent 在负尾

判决规则在取数前写死：
  定向贬低 ⇔ incumbent 的 Δ 落在最低的四分位 **且** Δ 的中位数 |·| 小于全体极差的一半
  否则记为「无法区分」，不硬套二选一

用法: python3 .cache/xcheck/analyse_divergence_shape.py
"""
import json
import os
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(REPO, "frontend", "public", "latent", "data",
                    "path_readout.json")
log = lambda *a: print(*a, flush=True)


def main():
    d = json.load(open(PATH, encoding="utf-8"))
    probs = d["problems"]
    log(f"题数 = {len(probs)}   分叉步取各题的 k\n")

    rows = []
    for pid, p in probs.items():
        k = p["k"]
        st = next(s for s in p["steps"] if s["t"] == k)
        cm = {i: g for i, g in zip(st["c"]["ids"], st["c"]["g"])}
        sm = {i: g for i, g in zip(st["s"]["ids"], st["s"]["g"])}
        shared = sorted(set(cm) & set(sm))
        if len(shared) < 4:
            log(f"  {pid}: 共享候选只有 {len(shared)} 个，不够判形状")
            continue
        deltas = [sm[i] - cm[i] for i in shared]
        inc_id = st["c"]["ids"][0]           # 对照臂的 top-1 = incumbent
        inc_d = sm[inc_id] - cm[inc_id] if inc_id in shared else None
        rows.append({
            "pid": pid, "k": k, "n_shared": len(shared),
            "inc_id": inc_id,
            "inc_delta": inc_d,
            "deltas": deltas,
            "same_top1": st.get("same_top1"),
        })

    if not rows:
        log("装置故障：没有一道题有足够的共享候选，无从判形状")
        return 2

    # 判决规则：取数前定死
    inc_deltas = [r["inc_delta"] for r in rows if r["inc_delta"] is not None]
    all_d = [x for r in rows for x in r["deltas"]]
    span = max(all_d) - min(all_d)
    med_abs = statistics.median(abs(x) for x in all_d)
    # incumbent 在每题内部的分位（0=最小 Δ，也就是被压得最狠）
    pct = []
    for r in rows:
        if r["inc_delta"] is None:
            continue
        below = sum(1 for x in r["deltas"] if x < r["inc_delta"])
        pct.append(below / max(1, len(r["deltas"]) - 1))
    median_pct = statistics.median(pct)

    targeted = (median_pct <= 0.34) and (med_abs < span / 2)

    log("逐题：incumbent(对照 top-1) 的 Δ，以及它在本题候选里的分位")
    log("  %-14s %4s %8s %12s %10s" % ("题", "k", "inc_Δ", "inc_分位", "共享候选"))
    for r, q in zip(rows, pct):
        log("  %-14s %4s %8.3f %12.2f %10d"
            % (r["pid"][:14], r["k"], r["inc_delta"], q, r["n_shared"]))

    log("")
    log(f"incumbent Δ 的中位数 = {statistics.median(inc_deltas):.3f}"
        f"   （负 = 原赢家被压低）")
    log(f"全部候选 Δ 的中位绝对值 = {med_abs:.3f}   全体极差 = {span:.3f}"
        f"   比值 = {med_abs/span:.2f}")
    log(f"incumbent 分位的中位数 = {median_pct:.2f}"
        f"   （0 = 每题里被压得最狠的那个；1 = 最轻）")

    # ── 决定性对照：Δ 与「原本分数」相关吗？ ────────────────────
    # 这一条决定解释的走向：
    #   · 若 Δ 随原本分数系统性下降 ⇒ 不是针对 incumbent，
    #     而是**分布被压陡**（高的压更低、低的不动）——
    #     而「压陡」正好能解释为什么 6/6 的净间距都变宽。
    #   · 若不相关 ⇒ 才是真对 incumbent 的定向贬低。
    # 两种读法对「这个向量该怎么用」的含义完全不同，所以必须分开报。
    xs, ys = [], []
    for r in rows:
        st = next(s for s in probs[r["pid"]]["steps"] if s["t"] == r["k"])
        cm = {i: g for i, g in zip(st["c"]["ids"], st["c"]["g"])}
        sm = {i: g for i, g in zip(st["s"]["ids"], st["s"]["g"])}
        for i in set(cm) & set(sm):
            xs.append(cm[i])
            ys.append(sm[i] - cm[i])

    def spearman(a, b):
        def rank(v):
            order = sorted(range(len(v)), key=lambda i: v[i])
            rk = [0.0] * len(v)
            for pos, i in enumerate(order):
                rk[i] = pos + 1
            return rk
        ra, rb = rank(a), rank(b)
        n = len(a)
        ma, mb = sum(ra) / n, sum(rb) / n
        num = sum((ra[i]-ma)*(rb[i]-mb) for i in range(n))
        da = sum((ra[i]-ma)**2 for i in range(n)) ** 0.5
        db = sum((rb[i]-mb)**2 for i in range(n)) ** 0.5
        return (num / (da*db)) if da and db else float("nan")

    rho = spearman(xs, ys)
    # Spearman 的粗略零假设门槛：|ρ| > 2/√n 之外不当作有信号。
    thr = 2 / (len(xs) ** 0.5) if xs else float("inf")
    steep = (rho < -thr) if rho == rho else False
    log("")
    log(f"对照：Δ 与「原本分数」的 Spearman ρ = {rho:.3f}"
        f"（n={len(xs)}，粗零假设门槛 |ρ|>{thr:.2f}）")
    if steep:
        log("  ⇒ 原本分数越高的词，Δ 越负 ⇒ 这是**把分布压陡**，"
            "不是只针对 incumbent。")
        log("     而压陡正好解释了 6/6 的净间距都变宽：赢家被压、"
            "challenger 相对被抬。")
    elif rho == rho and rho > thr:
        log("  ⇒ 原本分数越高的词，Δ 越**正** ⇒ 分布被压平，"
            "这会**缩小**间距，与 gap_widened 6/6 为正矛盾。")
    else:
        log("  ⇒ 没有可判的相关（|ρ| 在粗门槛内）⇒ "
            "本数据分不清压陡与定向。")
    log("  ⚠ 样本提醒：每题只有 5~8 个共享候选，"
        "分位数 0.25 与 0.5 只差**一个**候选的宽度。"
        "上面这条是提示，不是定论。")
    log("")
    if targeted:
        log("RESULT 定向贬低：incumbent 系统性地落在负尾，且整体位移以 0 为中心散开")
        log("        ⇒ 不是全局同向推力，是对这个 incumbent 的定向削弱。")
        log("        实践含义：这种向量的用法是**抑制某个候选**，"
            "不是「推高另一种答案」。")
    else:
        log("RESULT 无法区分定向与全局：incumbent 的分位没有系统性落在负尾，"
            "或整体位移是同向堆积的")
        log("        ⇒ 不硬套二选一。当前数据支持的最强陈述仍然只是："
            "分数被改了，赢家有时被削弱。")

    out = os.path.join(REPO, ".cache", "divergence_shape.json")
    json.dump({"rows": [{kk: vv for kk, vv in r.items() if kk != "deltas"}
                        for r in rows],
               "inc_delta_median": statistics.median(inc_deltas),
               "median_abs_delta": med_abs, "span": span,
               "inc_pct_median": median_pct,
               "verdict": "targeted" if targeted else "undetermined",
               "steepness_rho": rho, "steepness_threshold": thr,
               "distribution_steepened": bool(steep)},
              open(out, "w"), ensure_ascii=False, indent=2)
    log(f"（明细已写 {out}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
