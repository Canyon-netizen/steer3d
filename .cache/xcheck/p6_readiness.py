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

# ⚠ P0：旧批次 cap 2048，新批次 cap 8192。⚗ **不混池、不合并判。**
OLD_CAP = 2048
NEW_CAP = 8192

# ⚠ P6 的硬底线。⚗⚠⚴ 改动这里等于改预登记口径 —— ⚗⚠ 须改预登记正文并留痕。
P6_CORRECT_FLOOR = 10

# ⚠⚠⚴⚠⚴ 回归常量：**旧批次 think 必须复现出 4 correct / 2 wrong**。
# ⚠⚠⚴ 这个数写在 §0 正文里，是已确立的事实。⚗⚠ 它必须被**当常量比对**，
# ⚗⚠⚴⚠⚠ **而不是「现算现比」** —— 现算现比等于没有回归基线。
OLD_BATCH_BASELINE = {"think_correct": 4, "think_wrong": 2, "think_n": 24}


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
    if all_caps != [NEW_CAP]:
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
        print("\n⚠⚠⚴ cap=%s 既不是新批次（%d）也不是旧批次（%d）⇒ 批次身份不明。"
              % (all_caps, NEW_CAP, OLD_CAP))
        print("⚠⚠⚴ P0 明写「不混池、不合并判」—— 身份不明的批次不许进 P6。")
        print("RESULT p6_readiness  MISMATCH  cap=%s" % all_caps)
        return 4

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
        print("⚗⚠⚴⚠⚴ ⚠⚠⚴ **但先别急着去取数据** —— 修订 153 实测：")
        print("⚗⚠⚴⚠⚴⚠ ⚠ 新批次**单个 benchmark** 的 correct 只有 6–7 条，")
        print("⚗⚠⚴⚠⚴⚠ ⚗ **按预登记的停止点（前 30 题），再多取也到不了 10。**")
        print("⚗⚠⚴⚠⚴ ⚠⚠⚴ **⇒ 这是设计问题，不是取数问题。**")
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
