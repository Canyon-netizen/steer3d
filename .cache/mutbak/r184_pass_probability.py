#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 达标的条件概率表（修订 184 立）。

回答一个问题：
    「跑完的候选一条都没转成 correct」这件事，**能排除多少可能性**？

⚠ 本脚本**不下 P6 结论**（§167：数据没跑完不给结论，当前 24/60）。
⚠ 它只做一件事：把「可能过 / 可能不过」变成一张**条件表 + 一个区间**，
⚠ 让人能看出「还差多少」「6 个样本到底排除了多少」。

口径全部从实测推出，不在别处复刻：
    候选池     19 条  = 旧批 aime25 think 池里 strict == unlabeled 的题
    已测       6 条   （p04 p06 p08 p09 p10 p11），其中 C = 0
    剩余未测   13 条
    锁死 correct 7    = 旧批全部 correct，且修订 181 实测 17/17 无漂移
    P6 底线     10
    => 仍需 >=3 条 correct 来自剩余 13 条，所需转化率 23.1%

⚠ 池子必须限死：AIME25 与 AIME26 的 think 池 pNN 会撞号，
⚠ 用 endswith('__think') 会把两个池混起来（实测踩过：数出 20 而非 19）。
⚠ 本脚本沿用与 r178_uncapped_fate.py 同一套正则。

用法：
    python3 r184_pass_probability.py            # 默认口径
    python3 r184_pass_probability.py --json     # 便于后续引用

退出码：
    0  正常出表
    2  用法错误
"""

import argparse
import re
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD_LABEL = ROOT / ".cache/mutbak/strict_label_b2_full60.json"
TT_RE = re.compile(r"^aime__aime25__p(\d{2})__think$")

P6_CORRECT_FLOOR = 10


def binom_ge(n, k, p):
    """P(X >= k)，X ~ Binom(n, p)。用整数组合数算，避免依赖 scipy。"""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    total = 0.0
    for i in range(k, n + 1):
        total += comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return total


def binom_le(k, n, p):
    return sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
               for i in range(0, k + 1))


def cp_bounds(k, n, alpha=0.05):
    """Clopper-Pearson 区间。只用二分，不需要 scipy。

    ⚠ 修订 184 修正：第一版两个二分方向都反了，把 [0%, 45.9%] 印成
      [45.9%, 0.4%] —— 下界比上界还大，肉眼可见。
      正解：
        下界 = 解 P(X >= k | p) = alpha/2   （binom_ge 关于 p 单调增）
        上界 = 解 P(X <= k | p) = alpha/2   （binom_le 关于 p 单调减）
    """
    lo = 0.0
    if k > 0:
        a, b = 0.0, 1.0
        for _ in range(200):
            mid = (a + b) / 2
            if binom_ge(n, k, mid) > alpha / 2:   # mid 太大，往下走
                b = mid
            else:
                a = mid
        lo = (a + b) / 2

    hi = 1.0
    if k < n:
        a, b = 0.0, 1.0
        for _ in range(200):
            mid = (a + b) / 2
            if binom_le(k, n, mid) > alpha / 2:   # mid 太小，往上走
                a = mid
            else:
                b = mid
        hi = (a + b) / 2

    assert lo <= hi, "Clopper-Pearson 区间倒挂：%r > %r" % (lo, hi)
    return lo, hi


def p_for_prob(n, k, target):
    """解 P(X >= k | p) = target，返回 p。用于找「五成把握」的那个 p。"""
    a, b = 0.0, 1.0
    for _ in range(200):
        mid = (a + b) / 2
        if binom_ge(n, k, mid) < target:
            a = mid
        else:
            b = mid
    return (a + b) / 2


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--n-done", type=int, default=6,
                    help="已测候选条数（默认 6，即修订 184 当时）")
    ap.add_argument("--k-done", type=int, default=0,
                    help="已测候选里转成 correct 的条数（默认 0）")
    ap.add_argument("--new-label", default=None,
                    help="新批标注 json。给了就用它算锁死 correct，"
                         "否则退回旧批（那只在漂移为 0 时对）")
    ap.add_argument("--progress", default=None,
                    help="当前跑批进度，如 '32/60'。不给就不印，避免写死变陈旧")
    a = ap.parse_args()

    if not OLD_LABEL.exists():
        print("[错误] 读不到旧批标注：%s" % OLD_LABEL)
        return 2

    import json
    d = json.load(open(OLD_LABEL, encoding="utf-8"))
    rows = d["rows"] if isinstance(d, dict) and "rows" in d else d
    pool = {}
    for r in rows:
        m = TT_RE.match(str(r["traj"]))
        if m:
            pool[int(m.group(1))] = r["strict"]

    if not pool:
        print("[错误] 旧批里没有匹配 %s 的条目" % TT_RE.pattern)
        return 2

    n_cand = sum(1 for s in pool.values() if s == "unlabeled")

    # ⚠⚠⁴⚠⚴ 修订 189：这一段原来直接 `locked = 旧批 correct 数`。
    #   ⚠⚠⚴⚠⚴ 那只在**漂移恒为 0** 时成立。实测打脸：新批 p18 think
    #   旧批 wrong（8192 触顶答错）-> 新批 correct（10094 未触顶答对），
    #   漂移 1 条 ⇒ 锁死值是 **8** 而不是 7，缺口是 **2** 而不是 3。
    #   ⛔ 拿旧批数当「已经拿到手的东西」，等于把**治疗效果**排除在账外 ——
    #     而抬 cap 恰恰就是治疗。
    #   ⇒ 锁死 = 【新批标签】里、落在【旧批已确立题集】上的 correct 条数。
    newpool = {}
    if a.new_label:
        import json as _j
        _d = _j.load(open(a.new_label, encoding="utf-8"))
        _rows = _d["rows"] if isinstance(_d, dict) and "rows" in _d else _d
        for _r in _rows:
            _m = TT_RE.match(str(_r.get("traj")))
            if _m:
                newpool[int(_m.group(1))] = _r.get("strict")
        established = sorted(p for p, s in pool.items() if s != "unlabeled")
        locked = sum(1 for p in established if newpool.get(p) == "correct")
        drifted = [p for p in established
                   if p in newpool and newpool[p] != pool[p]]
    else:
        established = sorted(p for p, s in pool.items() if s != "unlabeled")
        locked = sum(1 for p in established if newpool.get(p) == "correct")
        drifted = []
    need = max(0, P6_CORRECT_FLOOR - locked)
    n_done, k_done = a.n_done, a.k_done
    if n_done > n_cand:
        print("[错误] --n-done=%d 超过候选池 %d" % (n_done, n_cand))
        return 2
    n_rem = n_cand - n_done

    lo, hi = cp_bounds(k_done, n_done)
    need_rate = need / n_rem if n_rem else float("nan")
    pool_rate = need / n_cand if n_cand else float("nan")

    if a.json:
        print(json.dumps({
            "pool_n": len(pool), "n_cand": n_cand, "locked_correct": locked,
            "need": need, "n_done": n_done, "k_done": k_done,
            "n_rem": n_rem, "need_rate": need_rate, "pool_rate": pool_rate,
            "cp_lo": lo, "cp_hi": hi,
        }, ensure_ascii=False, indent=2))
        return 0

    print("=== P6 达标条件（按 --n-done/--k-done 给的实测）===")
    print("  旧批 aime25 think 池      n = %d" % len(pool))
    print("  候选池（旧批 unlabeled）   n = %d" % n_cand)
    print("  锁死 correct              = %d   （按新批标签 ∩ 旧批已确立题集算）"
          % locked)
    if a.new_label:
        print("  已确立标签被改            = %d 条 %s"
              % (len(drifted), ("→ %s" % ["p%02d" % p for p in drifted])
                 if drifted else "⇒ 锁死值与旧批一致"))
    print("  P6 底线                   = %d" % P6_CORRECT_FLOOR)
    print("  => 仍需 correct           >= %d" % need)
    print("  已测候选 %d 条，其中 C = %d 条" % (n_done, k_done))
    print("  剩余未测候选              = %d 条" % n_rem)
    print()
    print("  剩余所需转化率 = %d/%d = %.1f%%" % (need, n_rem, need_rate * 100))
    print("  全池门槛       = %d/%d = %.1f%%" % (need, n_cand, pool_rate * 100))

    print("\n=== 已测 %d 条里 %d 条转成 correct，能排除多少？===" % (n_done, k_done))
    print("  Clopper-Pearson 95%% 区间：真实转化率 ∈ [%.1f%%, %.1f%%]"
          % (lo * 100, hi * 100))
    print("  ⚠ %d 条样本的上界高到 %.0f%% ——" % (n_done, hi * 100))
    print("  ⚠ **现有数据根本不足以把「真实转化率 > 所需」排除掉。**")
    print("  ⚠ 也就是说：「%d/%d」既不能证明会失败，也不能排除会成功。"
          % (k_done, n_done))

    p_half = p_for_prob(n_rem, need, 0.5)
    # ⚠ 修订 185 修正：grid 去重。原版把 need_rate 与硬编码的 0.30 并列，
    #   两者相等时同一行印两遍；且「五成把握点」用 ±0.005 容差标注，
    #   交点落在两个采样点之间时一个都不会被标上。
    grid = sorted({0.0, 0.05, 0.10, pool_rate, 0.20, need_rate, 0.30, 0.40})
    print("\n=== 条件概率表：若剩余 %d 条的真实转化率是 p，P(补足 %d 条) ==="
          % (n_rem, need))
    print("  %-10s %-14s %s" % ("p", "P(>=%d)" % need, "备注"))
    for p in grid:
        pr = binom_ge(n_rem, need, p)
        marks = []
        if abs(p - pool_rate) < 1e-9:
            marks.append("全池门槛 %.1f%%" % (pool_rate * 100))
        if abs(p - need_rate) < 1e-9:
            marks.append("剩余所需率 %.1f%%" % (need_rate * 100))
        if abs(p - p_half) < 1e-9:
            marks.append("五成把握点")
        print("  %-10.3f %-14.3f%s"
              % (p, pr, ("  <- " + " / ".join(marks)) if marks else ""))

    print("\n  => 剩余真实转化率要高到 %.1f%% 才有**五成**把握补足；"
          % (p_half * 100))
    print("     ⚠ 这个交点 %.1f%% 不一定落在表里任何一行上（表是采样，不是求解）。"
          % (p_half * 100))
    print("     所需率 %.1f%% 对应 P=%.2f。"
          % (need_rate * 100, binom_ge(n_rem, need, need_rate)))
    print("     而目前实测是 %d/%d。" % (k_done, n_done))

    print("\n⚠ 本表不是 P6 结论（§167：数据没跑满不给结论）。")
    if a.progress:
        print("⚠ 跑批进度：%s —— 未跑满，不给 P6 结论。" % a.progress)
    else:
        print("⚠ 跑批进度未随脚本记录，引用本表前请自己核当前进度。")
    print("⚠ 它只回答「还差多少」「现有样本能排除多少」，供决策用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())