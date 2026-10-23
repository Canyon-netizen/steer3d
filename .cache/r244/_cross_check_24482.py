#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24482.py —— **两条独立实现**在重叠口径上的逐位互证（244.82）。

⚖⚖⚖ **为什么要有这条**
   244.81 轮的「先导探查」（`_scout_premise_indep.py`）与 244.82 轮的
   **第二条独立实现**（`premise_independence_audit.py`）是**两个不同的程序**：
     · **数据路径不同**：先导读 `fixed_dose_split_log.py` 的**拆分产物**（`/dev/shm/.../work/*/pf*.log`）；
       本实现读 **bpath 原始跑批日志**并**自己按 `pos_frac` 过滤**。
     · **块键路线不同**：先导**剥后缀**；本实现**按 `__` 切分取前 N−1 段**。
     · **置换算法不同**：先导用 **蒙特卡洛**（20000 次，有种子）；本实现用 **DP 精确零分布**。
     · **区间算法不同**：先导用**按块 bootstrap**（有种子）；本实现用**删一块 jackknife**（确定性）。
     · **p 值口径不同**：先导的块级 p 与本实现的块级 p **不是**同一个数（MC vs 精确）
       ⇒ ⇒ 它们的差**就是 MC 误差**（预登记 §3.1）⇒ ⇒ 必须**在 MC 误差量级内**，⛔ 不是「逐位相同」。

⚖⚖⚖ **互证三类**
   ① **逐位相同**（同一口径、同一机械）：轨迹级/块级改判数、Fisher p、块内一致数、
      复制格一致/分歧计数与分歧率、两臂差 pp、McNemar p ⇒ ⇒ **任一不等 ⇒ 红**。
   ② **区间重叠**（不同机械、同一被估量）：先导 bootstrap 区间 vs 本实现 jackknife 区间
      ⇒ ⇒ 必须**重叠**且**都远离 0** ⇒ ⇒ ⛔ 不要求端点逐位相同（那才叫瞎比）。
   ③ **MC 误差量级**（不同机械、同一零分布）：先导 MC p vs 本实现精确 p
      ⇒ ⇒ 差必须 **≤ 3 个 MC 标准误**（预登记 §3.1）。

⛔ **本脚本不改任何东西**，只读两份输出、逐项比对、打印判据。
"""

import io
import math
import os
import re
import sys

# ③：先导的 MC 次数（用于算标准误）
SCOUT_N_PERM = 20000
MC_Z = 3.0


def _read(p):
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _grab(txt, pat, what):
    m = re.search(pat, txt)
    if not m:
        raise SystemExit("⛔ 抠不到「%s」" % what)
    return m


def parse_scout(txt):
    """⚖ 抠先导探查的数（⛔ 逐条抠，⛔ 不手抄）。"""
    d = {}
    m = _grab(txt, r"自检通过：轨迹级 w (\d+)/(\d+)、rand (\d+)/(\d+) ｜ "
                  r"块级 w (\d+)/(\d+)、rand (\d+)/(\d+) ｜ "
                  r"轨迹级 Fisher ([0-9.]+)、块级 Fisher ([0-9.]+)", "先导自检行")
    d["traj_w"] = "%s/%s" % (m.group(1), m.group(2))
    d["traj_rand"] = "%s/%s" % (m.group(3), m.group(4))
    d["blk_w"] = "%s/%s" % (m.group(5), m.group(6))
    d["blk_rand"] = "%s/%s" % (m.group(7), m.group(8))
    d["fisher_traj"] = m.group(9)
    d["fisher_blk"] = m.group(10)

    m = _grab(txt, r"块数 (\d+) ｜ w 臂块内两条\*\*判决一致\*\* (\d+)（([0-9.]+)）｜ "
                  r"rand 臂块内不一致 (\d+) ｜ w 臂块内不一致 (\d+)", "先导块内相关行")
    d["nblk"] = m.group(1)
    d["blk_agree_w"] = m.group(2)
    d["blk_po_w"] = m.group(3)
    d["blk_disagree_rand"] = m.group(4)
    d["blk_agree_rand"] = str(int(m.group(1)) - int(m.group(4)))
    d["blk_disagree_w"] = m.group(5)

    m = _grab(txt, r"\*\*块级\*\*置换（块内整体交换两臂标签）：p = ([0-9.]+)", "先导块级置换")
    d["mc_blk_perm_p"] = m.group(1)
    m = _grab(txt, r"\*\*逐轨迹\*\*置换：p = ([0-9.]+)", "先导逐轨迹置换")
    d["mc_traj_perm_p"] = m.group(1)

    m = _grab(txt, r"\*\*块级\*\*差 ([-+0-9.]+) pp ｜ 按块 bootstrap 95% 区间 "
                  r"\[([-+0-9.]+), ([-+0-9.]+)\] pp", "先导块级区间")
    d["theta_blk"] = m.group(1)
    d["boot_lo"], d["boot_hi"] = m.group(2), m.group(3)
    m = _grab(txt, r"\*\*轨迹级\*\*差 ([-+0-9.]+) pp ｜ Newcombe95（假定轨迹独立）"
                  r"\[([-+0-9.]+), ([-+0-9.]+)\] pp", "先导轨迹级区间")
    d["theta_traj"] = m.group(1)
    d["newc_lo"], d["newc_hi"] = m.group(2), m.group(3)

    for arm, tag in (("w", "w"), ("rand", "rand")):
        m = _grab(txt, r"%s 臂：三格全一致 (\d+) ｜ 2:1 分歧 (\d+) ｜ 分歧率 ([0-9.]+)" % tag,
                  "先导复制格行（%s）" % arm)
        d["repl_same_%s" % arm] = m.group(1)
        d["repl_split_%s" % arm] = m.group(2)
        d["repl_rate_%s" % arm] = m.group(3)

    m = _grab(txt, r"McNemar（逐轨迹配对，不一致 (\d+) 条：w优 (\d+) / rand优 (\d+)）⇒ "
                  r"精确二项两侧 p = ([0-9.]+)", "先导 McNemar 行")
    d["mcn_disc"] = m.group(1)
    d["mcn_w"] = m.group(2)
    d["mcn_rand"] = m.group(3)
    d["mcnemar_p"] = m.group(4)
    return d


def parse_cross(txt):
    """⚖ 抠本实现印的 CROSS 块。"""
    d = {}
    for ln in txt.split("\n"):
        if not ln.startswith("CROSS|"):
            continue
        k, _sep, v = ln[len("CROSS|"):].partition("=")
        d[k] = v
    if not d:
        raise SystemExit("⛔ 本实现的输出里没有 CROSS 块")
    return d


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法：_cross_check_24482.py <先导探查输出> <本实现输出>")
    scout_p, mine_p = sys.argv[1], sys.argv[2]
    for p in (scout_p, mine_p):
        if not os.path.isfile(p):
            raise SystemExit("⛔ 缺文件：%s" % p)
    s = parse_scout(_read(scout_p))
    m = parse_cross(_read(mine_p))

    fails = []

    def chk(name, ok, detail):
        print("[%s] %-18s %s" % ("PASS" if ok else "FAIL", name, detail))
        if not ok:
            fails.append(name)

    print("==== ① 逐位相同（同一口径、同一机械）====")
    # ⚖ 键名映射：本实现的 CROSS 块用了 `_pp` 后缀；数值一律按 **浮点** 比
    #   （先导印的是 `+53.57`、本实现印的是 `53.57` ⇒ ⛔ 符号格式不同但值相同）
    KEYMAP = {
        "theta_blk": "theta_blk_pp",
        "theta_traj": "theta_traj_pp",
    }
    exact_pairs = [
        ("traj_w", "轨迹级 w 改判"), ("traj_rand", "轨迹级 rand 改判"),
        ("blk_w", "块级 w 改判"), ("blk_rand", "块级 rand 改判"),
        ("fisher_traj", "轨迹级 Fisher p"), ("fisher_blk", "块级 Fisher p"),
        ("blk_agree_w", "w 臂块内一致数"), ("blk_agree_rand", "rand 臂块内一致数"),
        ("repl_same_w", "w 臂复制格全一致"), ("repl_split_w", "w 臂复制格分歧"),
        ("repl_rate_w", "w 臂分歧率"), ("repl_same_rand", "rand 臂复制格全一致"),
        ("repl_split_rand", "rand 臂复制格分歧"), ("repl_rate_rand", "rand 臂分歧率"),
        ("theta_blk", "块级差 pp"), ("theta_traj", "轨迹级差 pp"),
        ("mcnemar_p", "McNemar 精确二项 p"), ("nblk", "块数"),
    ]

    def _same(a, b):
        if a == b:
            return True
        try:
            return abs(float(a) - float(b)) < 5e-7
        except (TypeError, ValueError):
            return False

    for key, label in exact_pairs:
        sv = s.get(key, "(缺)")
        mv = m.get(KEYMAP.get(key, key), "(缺)")
        ok = _same(sv, mv)
        chk("X-%s" % key, ok, "%s：先导 `%s` vs 本实现 `%s`" % (label, sv, mv))

    print("")
    print("==== ② 区间（不同机械、同一被估量 ⇒ 必须重叠且都远离 0）====")
    b_lo, b_hi = float(s["boot_lo"]), float(s["boot_hi"])
    j_lo, j_hi = float(m["jack_lo_pp"]), float(m["jack_hi_pp"])
    ov = min(b_hi, j_hi) - max(b_lo, j_lo)
    ok = (ov > 0) and (b_lo > 0 or b_hi < 0) and (j_lo > 0 or j_hi < 0)
    chk("X-INTERVAL", ok,
        "先导 bootstrap [%+.2f, %+.2f] vs 本实现 jackknife [%+.2f, %+.2f] ⇒ 重叠宽度 %.2f pp ｜ "
        "两者都远离 0：%s" % (b_lo, b_hi, j_lo, j_hi, ov,
                             "是" if (b_lo > 0 or b_hi < 0) and (j_lo > 0 or j_hi < 0) else "否"))

    print("")
    print("==== ③ MC vs 精确（同一零分布 ⇒ 差必须是 MC 误差量级）====")
    mc = float(s["mc_blk_perm_p"])
    ex = float(m["exact_blk_perm_p"])
    se = math.sqrt(mc * (1 - mc) / SCOUT_N_PERM)
    d = ex - mc
    ok = abs(d) <= MC_Z * se
    chk("X-MCERROR", ok,
        "先导 MC p = %.6f（n=%d）vs 本实现**精确** p = %.8f ｜ 差 %+.8f ｜ MC 的 1 SE = %.8f "
        "⇒ 差 = %.2f SE ⇒ %s"
        % (mc, SCOUT_N_PERM, ex, d, se, abs(d) / se,
           "在 %g SE 内 ⇒ 就是 MC 误差" % MC_Z if ok else "⛔ 超出 %g SE ⇒ 要查" % MC_Z))

    print("")
    n = len(exact_pairs) + 2
    print("互证判据 %d 条 ｜ PASS %d ｜ FAIL %d" % (n, n - len(fails), len(fails)))
    if fails:
        print("⛔ 红的判据：%s" % "、".join(fails))
        return 1
    print("✅ **两条独立实现在重叠口径上互证通过**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
