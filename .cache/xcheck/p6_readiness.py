"""P6 开机自检 —— 回答一个问题：**这份数据能不能跑出预登记的主判决？**

⚠ 为什么需要这个文件
──────────────────
R-6 预登记 §0 把整个项目的意义写死了：旧批次 think 严格标签下只有
**4 correct / 2 wrong**，样本太薄；本轮只回答「样本量够时效应方向是否不同」。
⚠⚠⁴ 而 §1 P6 有一条**硬底线**：

    若 correct 组轨迹数 < 10，判决一律记「**样本不足，不构成结论**」，
    **不得**因为 p 值小就报显著，也**不得**因为 p 值大就报「无差异」。

⚠⚠⚴⚠⚠ 所以「手上这份数据够不够 P6」是个**可以机械判定**的问题，
⚗⚠ 而它此前从来没有被**当成一道闸**跑过 —— ⚗⚠⚠⚠ 每轮都是先算 p 值，
⚗⚠⚴⚠⚠⚠ 回头才发现自己连 10 条都没有。**顺序错了。**

⚠⚠⚴ 本脚本**只读数据、不碰 GPU、不算 p 值**：它判的是「够不够资格算 p 值」。

## 复用而不重写

⚠⚠⚴⚠⚴ 标签规则由 `strict_label.py` 的 `label()` 提供（R-27，写死在取数前）。
⚗⚠⚠⚴⚠⚠ **本脚本 import 它，不复刻它** —— ⚗⚠ 复刻一份就是「仪器跑了别的东西」：
⚗⚠⚴⚠ **两个标签器算出不同的 correct/wrong，而我不会知道自己用了哪一个。**

## 五种状态分开记（不许合并）

| 状态 | 含义 |
|---|---|
| ⚗ **崩** | 目录/文件/JSON 不对，判据本身跑不起来 |
| ⚗ **不匹配** | 批次不符合预登记声明（cap 不是 8192 ⇒ 不是 P0 指定的新批次） |
| ⚠ **样本不足** | 批次对，但 correct < 10 ⇒ 按 P6 记「不构成结论」 |
| ✅ **够格** | 可以跑 P6；**本脚本仍不代跑** |
| ⚠ **旧批次** | cap 2048 的那批，§0 的 4/2 就是它 —— 只作回归对照 |

用法：  python3 .cache/xcheck/p6_readiness.py [--traj DIR] [--label JSON]
退出码：0 = 够格；3 = 样本不足；4 = 批次不匹配；5 = 崩
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".cache/mutbak"))
import strict_label                                  # noqa: E402  (R-27 标签规则，唯一来源)

# ⚠ P0：旧批次 cap 2048；⚠⚠ 新批次有两个**已知** cap。⚗ **不混池、不合并判。**
#
# ⚠⚠⁴⚠ 修订 166：32768 轮要进 P6，⚗⚠ **而 8192 不能被顶掉** ——
# ⚗⚠⚴⚠⚴ **把 NEW_CAP 直接改成 32768 是错的**：那会让已有的 cap 8192 批次
# ⚗⚠⚴（gen_b2 / strict_label_b2_full60）反过来变成「身份不明」，⚗⚠ **那是倒退。**
# ⚗⚠⇒ 正解：认一个【已知新批次 cap 集合】，⚗⚠ **而混池继续拒**。
OLD_CAP = 2048
KNOWN_NEW_CAPS = (8192, 32768)

# ⚠ P6 的硬底线。⚗⚠⚴ 改动这里等于改预登记口径 —— ⚗⚠ 须改预登记正文并留痕。
P6_CORRECT_FLOOR = 10

# ⚠⚠⚴⚠⚴ 回归常量：**旧批次 think 必须复现出 4 correct / 2 wrong**。
# ⚠⚠⚴ 这个数写在 §0 正文里，是已确立的事实。⚗⚠ 它必须被**当常量比对**，
# ⚗⚠⚴⚠⚠ **而不是「现算现比」** —— 现算现比等于没有回归基线。
OLD_BATCH_BASELINE = {"think_correct": 4, "think_wrong": 2, "think_n": 24}

# ⚠⚠⁴⚠⁴ 完整性守卫（修订 187 新增）。
# ⚗⚠⚠ 停止规则是「前 30 题」，所以**每个 benchmark 的 think 臂**都该有 30 条。
# ⚗⚠⚠⚴ 守卫的判据写成 `!= 期望规模`，不是 `< 阈值`：
# ⚗⚠⚠⚴⚴ 多于期望同样是数据不对（混批/重复），不能只挡「不足」那一种。
EXPECTED_THINK_N_PER_BENCH = 30
EXIT_INCOMPLETE = 6          # ⚠ 与 UNDERPOWERED(3) 区分开：那是「够了但不够格」，这是「还没跑完」

# ⚠⚠⁴⚠⁴ 历史实测值（修订 187 起**必须条件化**后才能印）。
# ⚗⚠⚠ 这两个数出自 **cap 8192** 批次（`strict_label_b2_full60.json`，
# ⚗⚠⚠ 实测 cap 分布 {8192: 120}），账本 `R6_RERUN_PREREG.md:20949` 记
# ⚗⚠⚠ 「实测（严格口径 R-27）：aime25 7、aime26 6」。
# ⚗⚠⚴⚴⚴ 它**只在 cap==8192 时成立**。cap 32768 批次上印它，是把上一批的答案
# ⚗⚠⚴⚴⚴ 写死成这一批的性质 —— 而「6–7 会不会变」正是 cap 32768 这一轮要检验的事。
CAP8192_MEASURED_ON = 8192
CAP8192_PER_BENCH_CORRECT = {"aime25": 7, "aime26": 6}


BENCH_RE = re.compile(r"^aime__([A-Za-z0-9]+)__")

def bench_of(traj):
    """从轨迹 id 取出 benchmark 名。

    ⚠⚠⚴⚠⚴⚠⚠ 修订 153：**合并两个 benchmark 会把「够不够格」整个翻过来** ——
    ⚗⚠ 实测 think 口径 aime25 correct=7 / aime26 correct=6，
    ⚗⚠⚴ **两个都够不到 P6 的 10**，⚗⚠⚴⚠⚠⚠ **而合并池是 13 ⇒ 看着够格。**
    ⚗⚠⚴⚠ **预登记 §停止规则明写「按题号停、不按标签停」，
    ⚗⚠⚴⚠⚠ ⚠ 而那 60 条其实是 aime25(30) + aime26(30) 两个池。**
    ⚗⚠⚴ ⇒ **判决必须按单个 benchmark 判，合并池不许用来过关。**
    """
    m = BENCH_RE.match(traj or "")
    return m.group(1) if m else "?"


def per_bench(rows, mode):
    out = {}
    for r in rows:
        if r.get("mode") != mode:
            continue
        b = bench_of(r.get("traj"))
        out.setdefault(b, []).append(r)
    return out


def per_mode(rows):
    out = {}
    for m in ("think", "no_think"):
        rs = [r for r in rows if r.get("mode") == m]
        if not rs:
            continue
        c = Counter(r["strict"] for r in rs)
        out[m] = {"n": len(rs), "correct": c["correct"], "wrong": c["wrong"],
                  "unlabeled": c["unlabeled"],
                  "truncated": sum(bool(r.get("truncated")) for r in rs),
                  "ghost": sum(bool(r.get("ghost")) for r in rs),
                  "caps": sorted({r.get("cap") for r in rs if r.get("cap") is not None})}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", default=None, help="轨迹 json 所在目录")
    ap.add_argument("--label", default=None, help="strict_label 产出的 json（可选，给了就优先用它）")
    a = ap.parse_args()

    # ---- 取行：优先用已存的标签产物，否则现算 ----
    if a.label:
        p = Path(a.label)
        if not p.exists():
            print("RESULT p6_readiness  CRASH  标签文件不存在：%s" % p)
            return 5
        blob = json.loads(p.read_text(encoding="utf-8"))
        rows = blob.get("rows") or []
        src = "标签产物 %s" % p.name
    elif a.traj:
        paths = sorted(glob.glob(os.path.join(a.traj, "*.json")))
        if not paths:
            print("RESULT p6_readiness  CRASH  目录里没有轨迹 json：%s" % a.traj)
            return 5
        rows = [strict_label.label(x) for x in paths]
        src = "现算 %d 条 @ %s" % (len(rows), a.traj)
    else:
        # 默认：本机那个声明 cap 8192 的新批次
        d = ROOT / "datasets/aime_qwen3_1p7b_32k_fp32/aime"
        paths = sorted(glob.glob(os.path.join(str(d), "*.json")))
        if not paths:
            print("RESULT p6_readiness  CRASH  默认批次目录里没有轨迹 json：%s" % d)
            return 5
        rows = [strict_label.label(x) for x in paths]
        src = "现算 %d 条 @ %s" % (len(rows), d.name)

    print("=== P6 开机自检 ===")
    print("数据来源：%s" % src)
    print("标签规则：strict_label.label()（R-27，唯一来源，本脚本不复刻）")
    # ⚠⚠⁴⚠⁴ 印出**实际加载的**标签器路径 —— ⚗⚠⁴ 同名文件可以有好几份
    # ⚗⚠⁴（本机 .cache/mutbak/ 下就有 strict_label_16k.json / _b2_partial.json 等），
    # ⚗⚠ 而「读的是不是我以为的那一份」只能靠打印路径自证，不能靠推断。
    print("  ⚠ 实际加载：%s" % getattr(strict_label, "__file__", "（未知）"))

    stats = per_mode(rows)
    if "think" not in stats:
        print("⚠ 没有 think 模式的轨迹 —— P6 判的是 think 轨迹。")
        print("RESULT p6_readiness  CRASH  无 think 轨迹")
        return 5

    for m, s in stats.items():
        print("[%s] %-9s n=%3d  correct=%3d  wrong=%3d  unlabeled=%3d  "
              "触顶=%3d  幻觉=%2d  cap=%s"
              % (m, m, s["n"], s["correct"], s["wrong"], s["unlabeled"],
                 s["truncated"], s["ghost"], s["caps"]))

    th = stats["think"]
    all_caps = sorted({c for s in stats.values() for c in s["caps"]})



    # ---- 状态 1：批次是否符合 P0 声明 ----
    # ⚠⚠⁴⚠⚴ 修订 166：判据是「**批次内 cap 全等** 且 落在**已知新批次集合**里」。
    # ⚗⚠⚴ **不是「cap 等于某一个数」** —— 放宽成集合最容易顺手把「混池」也放宽，
    # ⚗⚠⚴⚠⚴⚴ 而混池正是 P0 明写要防的（8192 与 32768 混在一起 = 两个不同实验）。
    if len(all_caps) != 1 or all_caps[0] not in KNOWN_NEW_CAPS:
        # ⚠⚠⚴ 旧批次**内部 cap 是混的**：实测 48 条里 8 条声明 1024、40 条声明 2048。
        # ⚗⚠⚴⚠⚠ §0 正文把它统称为「cap 2048」—— **那不精确，但不构成混池**
        # ⚗⚠⚴（混池的风险是旧批与新批混，而这里**每一条都 ≤ 2048**）。
        # ⚠⇒ 认「旧批次」按 **全部 cap ≤ 2048**，不按「恰好等于 2048」。
        # ⚗⚠ **判据若写成恰好相等，会把一个真批次误判成「身份不明」** ——
        # ⚗⚠⚠⚠⚠⚠ 而**误判成身份不明**会让人以为数据有问题，去做没必要的排查。
        if all_caps and max(all_caps) <= OLD_CAP:
            print("\n⚠ 这是**旧批次**（全部 cap ≤ %d）—— §0 说的 4/2 就是它。" % OLD_CAP)
            print("⚠⚠⚴⚠⚴ 注意：实测 cap 分布 = %s，⚗⚠ **§0 把它统称为「cap 2048」并不精确**"
                  "（8 条声明 1024、40 条声明 2048）。⚗⚠⚠⚠⚠⚠⚠ **但它不构成混池** ——"
                  % all_caps)
            print("⚗⚠⚴ 每一条都 ≤ %d，而 P0 要防的是旧批与**新批**混。" % OLD_CAP)
            ok = (th["correct"] == OLD_BATCH_BASELINE["think_correct"]
                  and th["wrong"] == OLD_BATCH_BASELINE["think_wrong"]
                  and th["n"] == OLD_BATCH_BASELINE["think_n"])
            print("[%s] 回归对照：think 应为 %d/%d（n=%d），实得 %d/%d（n=%d）"
                  % ("PASS" if ok else "FAIL",
                     OLD_BATCH_BASELINE["think_correct"], OLD_BATCH_BASELINE["think_wrong"],
                     OLD_BATCH_BASELINE["think_n"], th["correct"], th["wrong"], th["n"]))
            print("\nRESULT p6_readiness  OLD_BATCH  §0 的 4/2 %s复现"
                  % ("已" if ok else "**未**"))
            return 0 if ok else 3
        print("\n⚠⚠⚴ cap=%s 既不是已知新批次（%s）也不是旧批次（全部 ≤ %d）⇒ 批次身份不明。"
              % (all_caps, " / ".join(str(c) for c in KNOWN_NEW_CAPS), OLD_CAP))
        print("⚠⚠⚴ P0 明写「不混池、不合并判」—— 身份不明的批次不许进 P6。")
        print("RESULT p6_readiness  MISMATCH  cap=%s" % all_caps)
        return 4

    # ---- ⚠⚠⁴⚠⁴ 完整性守卫（修订 187 新增）----
    # ⚠⚠⚴⚠⚴ **这一段原先不存在。** 实测（修订 180.3）在 18/60 的部分数据上，
    # ⚠⚠⚴⚠⚴ 本脚本照样出判决 `UNDERPOWERED / EXIT=3`，并印
    # ⚠⚠⚴⚠⚴   「按前 30 题，再多取也到不了 10」／「这是设计问题，不是取数问题」
    # ⚠⚠⚴⚠⚴ 而当时 30 题里有 21 题**还没开始生成** ——
    # ⚠⚠⚴⚠⚴ 那两句都是假话，且足以让人提前收工、砍掉正在跑的这一轮。
    #
    # ⚠ 为什么退出码要用 6 而不是复用 3：
    #   3 (UNDERPOWERED) = 「跑够了，但 correct 数不够格」
    #   6 (INCOMPLETE)   = 「还没跑完，判决这件事本身还不存在」
    # ⚠ 两者混用同一个码，事后从日志里分不出「结论成立」和「数据没到」。
    _bchk = per_bench(rows, "think")
    _bad = {b: len(v) for b, v in sorted(_bchk.items())
            if len(v) != EXPECTED_THINK_N_PER_BENCH}
    if _bad:
        print("\n" + "!" * 68)
        print("⛔ **批次未跑满 —— 本次不出判决。**")
        print("!" * 68)
        print("  停止规则要求每个 benchmark 的 think 臂各 %d 条，实得："
              % EXPECTED_THINK_N_PER_BENCH)
        for _b, _n in _bad.items():
            print("    %-10s %3d / %d" % (_b, _n, EXPECTED_THINK_N_PER_BENCH))
        print("\n⚠⚠⚴ **在未跑满的数据上，本脚本算出的任何 correct 数都不是这个批次的性质，")
        print("⚠⚠⚴   它只是「目前跑到哪」的快照。**")
        print("⚠⚠⚴ 特别是：**不许**据它说「再多取也到不了 N」或「这是设计问题，不是取数问题」")
        print("⚠⚠⚴ —— 未跑满时这两句必然是假话（还没取的部分当然可能改变总数）。")
        print("\n  权威进度/归宿口径看 r178_uncapped_fate.py（它分开印「已测 / 未测」），")
        print("  跑批前的前置闸看 r180_p6_precond.py，批量编排看 r182_verdict_pipeline.py。")
        print("\nRESULT p6_readiness  INCOMPLETE  think n=%s（期望每个 benchmark %d）⇒ 判决不存在"
              % ({b: len(v) for b, v in sorted(_bchk.items())},
                 EXPECTED_THINK_N_PER_BENCH))
        return EXIT_INCOMPLETE

    # ---- ⚠⚠⚴⚠⚴ 按 benchmark 拆开：合并池会把结论翻过来 ----
    bench = per_bench(rows, "think")
    if len(bench) > 1:
        print("\n--- 按 benchmark 拆开（⚠⚠⚴ **判决必须按单个 benchmark 判**）---")
        per = {}
        for b in sorted(bench):
            c = Counter(r["strict"] for r in bench[b])
            per[b] = c["correct"]
            print("  %-10s n=%3d  correct=%3d  wrong=%3d  unlabeled=%3d  %s"
                  % (b, len(bench[b]), c["correct"], c["wrong"], c["unlabeled"],
                     "✅ 过 P6 底线" if c["correct"] >= P6_CORRECT_FLOOR
                     else "⚠ 够不到 P6 底线"))
        pooled = per.get(max(per, key=per.get), 0)
        print("  %-10s n=%3d  correct=%3d  ← **合并池**" % ("合并", th["n"], th["correct"]))
        if max(per.values()) < P6_CORRECT_FLOOR <= th["correct"]:
            print("\n⚠⚠⚴⚠⚴⚠⚠⚠⚠ **合并池才够格**（%d ≥ %d），⚗⚠⚠⚠⚠ 而每个 benchmark 都够不到："
                  % (th["correct"], P6_CORRECT_FLOOR))
            print("⚗⚠⚴⚠⚠⚠⚠⚠ %s" % {b: v for b, v in per.items()})
            print("⚗⚠⚴⚠⚠⚠ ⚗⚠ **这正是预登记停止规则要防的那件事**"
                  "（「按题号停、不按标签停」，不让跑到多少 correct 反过来决定取多少题）。")
            print("\nRESULT p6_readiness  POOL_ONLY  仅合并池达标 %d；单池 %s ⇒ **不许用合并池判 P6**"
                  % (th["correct"], sorted(per.items())))
            return 3

    # ---- 状态 2：P6 的 correct 底线 ----
    print("\n--- P6 底线核对 ---")
    print("  P6 原文：correct 组轨迹数 < %d ⇒ 记「**样本不足，不构成结论**」" % P6_CORRECT_FLOOR)
    print("  实得 think correct = %d" % th["correct"])
    if th["correct"] < P6_CORRECT_FLOOR:
        print("\n⚠⚠⚴ **样本不足。** ⚗⚠ 按 P6，这一格必须记「不构成结论」——")
        print("⚗⚠⚴⚠⚠ **既不能因为 p 值小就报显著，也不能因为 p 值大就报「无差异」。**")
        print("⚗⚠⚠⚠⚠⚠ ⚠ 缺的是**轨迹本身**（带 hidden states 的 npz），不是口径、不是算力。")
        # ⚠⚠⁴⚠⁴ 修订 187：这段原先**无条件印**，把 cap 8192 批次的实测值
        # ⚠⚠⁴⚠⁴ 当成了「新批次」的通性。出处：R6_RERUN_PREREG.md:20949，
        # ⚠⚠⁴⚠⁴ 而那批产物 strict_label_b2_full60.json 实测 cap 分布 {8192: 120}。
        # ⚠⚠⁴⚠⁴ 「6–7 会不会变」正是 cap 32768 这一轮要检验的事，
        # ⚠⚠⁴⚠⁴ 印一个上一批的答案，正是把要检验的东西先写死了。
        # ⚠⇒ 只有当**当前批次就是实测那一批**时才印，并且连条件一起印。
        if all_caps and all_caps[0] == CAP8192_MEASURED_ON:
            print("⚗⚠⚴⚠⚴ ⚠⚠⚴ **这条只对 cap %d 成立**（修订 153 在该批次实测）："
                  % CAP8192_MEASURED_ON)
            print("⚗⚠⚴⚠⚴⚠ ⚠ 单个 benchmark 的 correct 实测 %s"
                  % CAP8192_PER_BENCH_CORRECT)
            print("⚗⚠⚴⚠⚴⚠ ⚗ **按预登记的停止点（前 30 题），再多取也到不了 %d。**"
                  % P6_CORRECT_FLOOR)
            print("⚗⚠⚴⚠⚴ ⚠⚠⚴ **⇒ 对 cap %d 这一批，这是设计问题，不是取数问题。**"
                  % CAP8192_MEASURED_ON)
        else:
            print("⚗⚠⚴⚠⚴ ⚠⚠⚴ ⚠ **本批次 cap = %s，不是实测那批（cap %d）。**"
                  % (all_caps, CAP8192_MEASURED_ON))
            print("⚗⚠⚴⚠◦⚠⚠ ⚗⚠⚠⚴ **因此这里不印任何历史 correct 数。**")
            print("⚗⚠⚴⚠◦⚠◦ ⚗⚠⚠⚠⚴ 历史值 %s 出自 cap %d 批次，对本批**不成立**；"
                  % (CAP8192_PER_BENCH_CORRECT, CAP8192_MEASURED_ON))
            print("⚗⚠⚴⚠◦⚠◦ ⚗⚠⚠⚴⚴ 拿它外推本批，等于把「本轮要检验的量」先写死成已知。")
            print("⚗⚠⚴⚠◦⚠◦ ⚗⚠⚠⚴ ⚠ 本批 correct 够不够 %d，以上面这一批实测数为准：%d。"
                  % (P6_CORRECT_FLOOR, th["correct"]))
        print("\nRESULT p6_readiness  UNDERPOWERED  think correct=%d < %d ⇒ 「样本不足，不构成结论」"
              % (th["correct"], P6_CORRECT_FLOOR))
        return 3

    print("\n✅ correct 组已达 P6 底线（%d ≥ %d）。" % (th["correct"], P6_CORRECT_FLOOR))
    print("⚠⚠⚴ **本脚本不代跑 P6** —— 它只判「够不够资格算 p 值」。")
    print("⚠⚠⚴⚠⚠ 且 wrong 组只有 %d 条：⚗ **P6 没给 wrong 设底线，但 n=%d 做 U 检验"
          % (th["wrong"], th["wrong"]))
    print("⚗⚠⚴⚠⚴ 功效极低** —— ⚗⚠⚠ 这一格必须在报告里显式披露，不许只报 correct 够格。")
    print("\nRESULT p6_readiness  ELIGIBLE  think correct=%d wrong=%d" % (th["correct"], th["wrong"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
