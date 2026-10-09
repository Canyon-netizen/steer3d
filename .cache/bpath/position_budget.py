"""新批次：按模式统计「可用于 R-6 取样的位置数」，并与标签交叉。

## 为什么问这个

think 模式存在**选择效应**：截顶轨迹很难打标签，而能打标签的子集偏向答对。
⚠ 下面这句话是 **n=11 时的旧判断，已被 50 题实测推翻**（见预登记修订 5）：

    「按 30 题外推，think 只有约 14 correct / 2 wrong，wrong 组不足以做秩和检验。」

n=50 实测：think **12 correct / 8 wrong**，两项都过 P6 门槛；
反倒是 no_think 的 correct 只有 5，卡在 10 之下。
原因是 R-27 的散文抽取让截顶轨迹也能打标签（n=50 时触顶轨迹 23% 有标签），
而这个比例随 n 上升——**n=11 时的外推不足以支撑「不足以」的断言**。

no_think 相反：几乎 100% 有标签，但模型在 AIME 上直接答对的太少
（correct 10.2%），correct 组始终凑不满。

## 判决规则（取数前写死）

  Q1 按 P5（每条最多 6 个位置、按十等分位取）算，两种模式各能凑出多少**位置**
  Q2 按 P6 算，两种模式各能凑出多少**轨迹**（correct / wrong）
  Q3 分组秩和检验至少需要 wrong 组 >= 8 条轨迹，否则本轮 R-6
     在该模式上判「样本不足，不构成结论」
  Q4 Q1/Q2 都不达标的模式，本轮直接标「该模式不可用」，不做降级凑合
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from pathlib import Path

MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
MAX_POS_PER_TRAJ = 6
MIN_CORRECT = 10          # 与 P6 / r6_verdict.py 同源
MIN_WRONG = 8             # 与 P6 / r6_verdict.py 同源
MIN_CORRECT_TRAJ = 10      # 与 P6 / r6_verdict.py 同源
TARGET = 60                # 预登记修订 3/4 的停止点（数据天花板）


def sample_markers(marker_idx, n_tok):
    """按 P5：按 token 十等分位各取一个，每条最多 MAX_POS_PER_TRAJ 个。"""
    if not marker_idx:
        return []
    buckets = {}
    for g in marker_idx:
        b = min(9, int(g / max(n_tok, 1) * 10))
        buckets.setdefault(b, []).append(g)
    out = []
    for b in sorted(buckets)[:MAX_POS_PER_TRAJ]:
        out.append(buckets[b][0])
    return out


def main(root, labels_path):
    lab = {r["traj"]: r for r in json.load(open(labels_path, encoding="utf-8"))["rows"]}
    rows = []
    for f in sorted(glob.glob(f"{root}/*.json")):
        j = json.load(open(f, encoding="utf-8"))
        tid = j["trajectory_id"]
        n_tok = j["n_generated_tokens"]
        mk = [i for i, t in enumerate(j.get("tokens") or [])
              if t["token_id"] in MARKER_IDS]
        sampled = sample_markers(mk, n_tok)
        rows.append({
            "traj": tid, "mode": j["config"]["mode"], "n_tok": n_tok,
            "truncated": n_tok >= j["config"]["max_new_tokens"],
            "n_markers": len(mk), "n_sampled": len(sampled),
            "label": lab.get(tid, {}).get("strict", "?"),
        })

    print(f"{'traj':40s} {'mode':9s} {'tok':>5s} {'触顶':>5s} {'marker':>7s} "
          f"{'抽样位':>6s} {'严格标签':>9s}")
    for r in rows:
        print(f"{r['traj']:40s} {r['mode']:9s} {r['n_tok']:5d} "
              f"{str(r['truncated']):>5s} {r['n_markers']:7d} {r['n_sampled']:6d} "
              f"{r['label']:>9s}")

    print("\n" + "=" * 78)
    print(f"{'模式':10s} {'轨迹':>4s} {'可抽样位置':>10s} {'correct':>8s} {'wrong':>6s} "
          f"{'unlab':>6s} {'wrong轨迹':>9s} {'>=8?':>5s}")
    print("=" * 78)
    agg = {}
    for mode in ("think", "no_think"):
        rs = [r for r in rows if r["mode"] == mode]
        if not rs:
            continue
        pos = sum(r["n_sampled"] for r in rs)
        c = [r for r in rs if r["label"] == "correct"]
        w = [r for r in rs if r["label"] == "wrong"]
        u = [r for r in rs if r["label"] == "unlabeled"]
        ok = len(w) >= MIN_WRONG
        agg[mode] = {"n_traj": len(rs), "positions": pos, "correct": len(c),
                     "wrong": len(w), "unlabeled": len(u), "enough": ok}
        print(f"{mode:10s} {len(rs):4d} {pos:10d} {len(c):8d} {len(w):6d} "
              f"{len(u):6d} {len(w):9d} {'是' if ok else '否':>5s}")

    print("\n" + "=" * 78)
    print(f"Q1/Q2/Q3 判决（按当前比例外推到 TARGET={TARGET} 题，"
          f"即预登记修订 3/4 的停止点）")
    print("=" * 78)
    for mode, a in agg.items():
        scale = TARGET / max(a["n_traj"], 1)
        wt = a["wrong"] * scale
        ct = a["correct"] * scale
        v3 = a["enough"]
        print(f"  {mode:10s} 当前 n={a['n_traj']} 外推 {TARGET} 题 -> "
              f"correct≈{ct:.0f} wrong≈{wt:.0f}  "
              f"Q3(wrong>=8) {'PASS' if v3 else 'FAIL（外推也只 %.0f）' % wt}")
        print(f"             P6(correct>=10 与 wrong>=8 同时) "
              f"{'PASS' if ct >= MIN_CORRECT and wt >= MIN_WRONG else 'FAIL'}")

    usable = [m for m, a in agg.items() if a["enough"]]
    print()
    if usable:
        print("=> wrong 组够 8 条轨迹的模式:", ", ".join(usable))
        for m in usable:
            a = agg[m]
            ct = a["correct"] * TARGET / max(a["n_traj"], 1)
            wt = a["wrong"] * TARGET / max(a["n_traj"], 1)
            ok = ct >= MIN_CORRECT and wt >= MIN_WRONG
            print(f"   {m}：外推 correct≈{ct:.0f} / wrong≈{wt:.0f}"
                  f"  ⇒ P6 {'可出判决' if ok else '样本不足'}")
    else:
        print("=> **两种模式的 wrong 组都不足 8 条轨迹**。")
        print("   本轮 R-6 在两个模式上都判「样本不足，不构成结论」——")
        print("   按 P6/P3 不得降级凑合，也不得改门槛。")

    out = Path(".cache/mutbak/bpath_position_budget.json")
    json.dump({"rows": rows, "agg": agg,
               "rules": {"max_pos_per_traj": MAX_POS_PER_TRAJ,
                         "min_wrong_traj": MIN_WRONG}},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])