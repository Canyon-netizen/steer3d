"""新批次：按模式统计「可用于 R-6 取样的位置数」，并与标签交叉。

## 为什么问这个

think 模式出现了严重的**选择效应**：截顶的那 55% 全部 unlabeled，
而有标签的 45% 里 83% 是对的 ⇒ 「能打标签的子集」系统性偏向答对。
按 30 题外推，think 只有约 14 correct / **2 wrong**，wrong 组不足以做秩和检验。

no_think 相反：100% 有标签，correct 2 / wrong 9，是个可用的对照，
但 marker 数量少。到底哪条路能走，要看**每条轨迹有多少个可取样位置**。

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
MIN_WRONG_TRAJ = 8


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
        ok = len(w) >= MIN_WRONG_TRAJ
        agg[mode] = {"n_traj": len(rs), "positions": pos, "correct": len(c),
                     "wrong": len(w), "unlabeled": len(u), "enough": ok}
        print(f"{mode:10s} {len(rs):4d} {pos:10d} {len(c):8d} {len(w):6d} "
              f"{len(u):6d} {len(w):9d} {'是' if ok else '否':>5s}")

    print("\n" + "=" * 78)
    print("Q1/Q2/Q3 判决（按当前 22 条的**比例**外推到 30 题 = 每模式 30 条）")
    print("=" * 78)
    for mode, a in agg.items():
        scale = 30 / max(a["n_traj"], 1)
        w30 = a["wrong"] * scale
        c30 = a["correct"] * scale
        v3 = a["enough"]
        print(f"  {mode:10s} 外推 30 题 -> correct≈{c30:.0f} wrong≈{w30:.0f}  "
              f"Q3(wrong>=8) {'PASS' if v3 else 'FAIL（外推也只 %.0f）' % w30}")

    usable = [m for m, a in agg.items() if a["enough"]]
    print()
    if usable:
        print("=> 可用模式:", ", ".join(usable))
        for m in usable:
            print(f"   {m}：外推 correct≈{agg[m]['correct']*30/agg[m]['n_traj']:.0f} / "
                  f"wrong≈{agg[m]['wrong']*30/agg[m]['n_traj']:.0f}")
    else:
        print("=> **两种模式的 wrong 组都不足 8 条轨迹**。")
        print("   本轮 R-6 在两个模式上都判「样本不足，不构成结论」——")
        print("   按 P6/P3 不得降级凑合，也不得改门槛。")

    out = Path(".cache/mutbak/bpath_position_budget.json")
    json.dump({"rows": rows, "agg": agg,
               "rules": {"max_pos_per_traj": MAX_POS_PER_TRAJ,
                         "min_wrong_traj": MIN_WRONG_TRAJ}},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])