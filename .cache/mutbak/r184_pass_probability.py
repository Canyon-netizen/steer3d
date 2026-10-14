#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 达标的条件概率表（修订 184 立）。

回答一个问题：
    「跑完的候选一条都没转成 correct」这件事，**能排除多少可能性**？

⚠ 本脚本**不下 P6 完整结论**（§167：数据没跑完不给完整结论）。
⚠ 它只做一件事：把「可能过 / 可能不过」变成一张**条件表 + 一个区间**，
⚠ 让人能看出「还差多少」「已测样本到底排除了多少」。

⚠⚠⚠ 修订 193 修正：**correct 有两路贡献，原版只数了其中一路。**
    路1 锁死 locked = 【旧批已确立题集 ∩ 新批标签】里 correct 的条数
    路2 落袋 banked = 【旧批候选】里、在新批**已经转成 correct** 的条数（C 类）
    => 到手 = locked + banked，缺口 need = max(0, 底线 - 到手)
    ⚠⚠⚠ 原版 `need = 底线 - locked`，等于把「**已经拿到手的 C**」
    ⚠⚠⚠ 当成「还没拿到」⇒ 在 C 已落袋 2 条时仍印「仍需 >= 2」——
    ⚠⚠⚠ **与已达成底线的事实直接矛盾**，且方向是虚报困难。

    ⚗ 下面这段是**修订 184 当时的历史快照**，不是本批性质，别当现状引用：
        候选池 19 · 已测 6 · C=0 · 锁死 7 · 缺口 3 · 所需转化率 23.1%
    ⚗ 其中「锁死 7」在修订 189 已被实测打脸（漂移 1 条 ⇒ 真值 8）。

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
    ap.add_argument("--n-done", type=int, default=None,
                    help="已测候选条数。给了以它为准；不给且给了 "
                         "--new-label 时自动从标注数出来（防手填变记忆）")
    ap.add_argument("--k-done", type=int, default=None,
                    help="已测候选里转成 correct 的条数（落袋 C）。同上，默认自动数")
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
        locked = 0
        drifted = []

    # ⚠⚠⁴ 修订 193：候选里**已经转成 correct** 的那些是「已经拿到手」的，
    #   原版没数它们 ⇒ 缺口被虚报。两条路必须都数。
    candidates = sorted(p for p, s in pool.items() if s == "unlabeled")
    measured_c = sorted(p for p in candidates if p in newpool)
    banked = sorted(p for p in measured_c if newpool[p] == "correct")

    # ⚗ n_done / k_done 默认从标注文件数出来，不接受「记忆里的数」。
    #   显式传参优先（复现历史口径 / 反向证伪时用）。
    n_done = len(measured_c) if a.n_done is None else a.n_done
    k_done = len(banked) if a.k_done is None else a.k_done

    if n_done > n_cand:
        print("[错误] --n-done=%d 超过候选池 %d" % (n_done, n_cand))
        return 2
    if k_done > n_done:
        print("[错误] --k-done=%d 超过 --n-done=%d" % (k_done, n_done))
        return 2
    if a.new_label and a.n_done is None and a.k_done is None and n_done == 0:
        print("[错误] --new-label 里一条候选都没匹配上；"
              "确认该文件含 aime25 think 标签")
        return 2

    inhand = locked + k_done
    need = max(0, P6_CORRECT_FLOOR - inhand)
    n_rem = n_cand - n_done
    rem_unmeasured = sorted(p for p in candidates if p not in newpool)

    lo, hi = cp_bounds(k_done, n_done)
    need_rate = need / n_rem if n_rem else float("nan")
    pool_rate = need / n_cand if n_cand else float("nan")

    if a.json:
        print(json.dumps({
            "pool_n": len(pool), "n_cand": n_cand, "locked_correct": locked,
            "banked_correct": k_done, "banked_p": ["p%02d" % p for p in banked],
            "inhand_correct": inhand, "floor_reached": need == 0,
            "need": need, "n_done": n_done, "k_done": k_done,
            "rem_unmeasured": ["p%02d" % p for p in rem_unmeasured],
            "n_rem": n_rem, "need_rate": need_rate, "pool_rate": pool_rate,
            "cp_lo": lo, "cp_hi": hi,
        }, ensure_ascii=False, indent=2))
        return 0

    print("=== P6 达标条件（correct 分两路贡献）===")
    print("  旧批 aime25 think 池      n = %d" % len(pool))
    print("  候选池（旧批 unlabeled）   n = %d" % n_cand)
    print("  锁死 correct              = %d   （按新批标签 ∩ 旧批已确立题集算）"
          % locked)
    if a.new_label:
        print("  已确立标签被改            = %d 条 %s"
              % (len(drifted), ("→ %s" % ["p%02d" % p for p in drifted])
                 if drifted else "⇒ 锁死值与旧批一致"))
    # ⚠ 显式传参与「从标注数出来」不一致时必须把两个数都说出来，
    #   否则 `= 0 → [p20,p23]` 这种自相矛盾的行会被读成事实。
    _blist = ["p%02d" % p for p in banked]
    if banked and k_done == len(banked):
        _btail = "→ %s" % _blist
    elif banked:
        _btail = "⚗ 标注里数出 %d 条 → %s" % (len(banked), _blist)
    else:
        _btail = ""
    print("  落袋 correct（C 类已转）  = %d   %s" % (k_done, _btail))
    print("  ------------------------------")
    print("  ★ 到手 correct            = %d   = 锁死 %d + 落袋 %d"
          % (inhand, locked, k_done))
    print("  P6 底线                   = %d" % P6_CORRECT_FLOOR)
    print("  => 仍需 correct           >= %d" % need)
    print("  已测候选 %d 条，其中 C = %d 条" % (n_done, k_done))
    print("  剩余未测候选              = %d 条 %s"
          % (n_rem, ["p%02d" % p for p in rem_unmeasured] or ""))
    print()

    if need == 0:
        print("  ★★ **P6 底线已达成**（到手 %d ≥ 底线 %d），且此结论是**单调下界**。"
              % (inhand, P6_CORRECT_FLOOR))
        print("     ⚠ 它不是 §167 禁的「完整批结论」：剩余 %d 条**全是候选**，"
              % n_rem)
        print("       它们只可能增加 correct、不会减少 ⇒ 计数**单调不减**，")
        print("       越过后不会再落回。这条不依赖未跑完的 %d 条。" % n_rem)
        print("     ⚠ 完整 P6 判决仍须等 60/60 跑满，由 r182_verdict_pipeline 出。")
        print("     ⚠ 缺口为 0 ⇒ 下面这张条件概率表恒为 1.000，**没有信息量**，")
        print("       故不打印（省得把一张空表读成「条件已算过」）。")
        print()
        print("  === 已测段转化率（供判断剩余段的先验，非 P6 判决）===")
        print("  实测 %d/%d = %.1f%%   Clopper-Pearson 95%% 区间 [%.1f%%, %.1f%%]"
              % (k_done, n_done, (k_done / n_done * 100) if n_done else float("nan"),
                 lo * 100, hi * 100))
        print()
    else:
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

    print("\n⚠ 本表不是 P6 完整结论（§167：数据没跑完不给完整结论）。")
    if need == 0:
        print("⚠ 例外：上面那条「底线已达成」是**单调下界**，不受 §167 限制 ——")
        print("⚠ 它只依赖「已到手 %d 条」这个已发生的事实，不依赖未跑完的部分。" % inhand)
    if a.progress:
        print("⚠ 跑批进度：%s —— 未跑满，不给 P6 完整结论。" % a.progress)
    else:
        print("⚠ 跑批进度未随脚本记录，引用本表前请自己核当前进度。")
    print("⚠ 它只回答「还差多少」「现有样本能排除多少」，供决策用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())