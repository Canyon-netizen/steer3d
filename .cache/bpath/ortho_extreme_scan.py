"""修订 30 §30.3：极对齐位的**静态扫描 + 选材**（纯静态、不跑模型、不用 GPU）。

## 它做什么

对**尚未在高对齐批次里测过**的轨迹，逐条算全部 marker 位点的 `w·ĥ`，
取该轨迹 `|w·ĥ|` **最高十分位**作为「极对齐位点」，写成显式清单。

⚠ 极对齐带是**逐轨迹的十分位**，不是一个全局阈值 ——
不同轨迹的 `|w·ĥ|` 分布差很多，用全局阈值会把短轨迹/长轨迹混着比。
所以清单必须带**逐位点的 `|w·ĥ|`**，让探针能逐条对账。

## 选材为什么仍然无偏

它读的是 `gen_b2/aime/*.json` + `*.npz` —— **里面没有任何 `Δ`**。
选材只依赖预测量 `w·ĥ` ⇒ 在结构上不可能偏向效应的大小或方向。

## 为什么排除已测的 30 条

高对齐批次（修订 28/29）已经把那 30 条的**全部** `w·ĥ>0.1` 位点测过了，
其中就包含它们的极对齐位点。重测既浪费算力、也让「独立」失去意义。

## 只读

不改任何产物；只写一份选材清单。
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os

import numpy as np

MK = {13824, 14190, 6771, 10061, 7196, 88190, 80022}
NPZ = 19
DECILE = 0.10
ROOT = "/home/zhourui/steer3d_bpath"

EXPECT_POOL = 28          # 58 − 修订 28/29 已测的 30 条


def pick_top_decile(pairs, decile=DECILE):
    """pairs: [(t, w)] -> 取 |w| 最高 decile 的位点（并列时取 |w| 更大的）。

    ⚠ 返回值**保序**（按 t 升序），让清单可逐条比对、diff 稳定。
    """
    if not pairs:
        return []
    k = max(1, int(len(pairs) * decile))     # 与 §30.3 的「最高十分位」一致
    order = sorted(pairs, key=lambda p: (-abs(p[1]), p[0]))
    top = order[:k]
    return sorted(top, key=lambda p: p[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--already", required=True,
                    help="hi_sites_pick.json：已测过的轨迹（要排除）")
    ap.add_argument("--frac-scan", required=True,
                    help="ortho_frac_full.json：58 条扫描池")
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-pool", type=int, default=EXPECT_POOL)
    a = ap.parse_args()

    measured = {t["traj"] for t in
                json.load(open(a.already, encoding="utf-8"))["tracks"]}
    pool58 = {r["traj"] for r in
              json.load(open(a.frac_scan, encoding="utf-8"))}
    todo = sorted(pool58 - measured)
    if len(todo) != a.expect_pool:
        raise SystemExit(f"待测轨迹应为 {a.expect_pool} 条，实际 {len(todo)}")

    W = np.load(os.path.join(a.root, "w_L19_m0.npy")).astype(np.float32)
    W = W / (float(np.linalg.norm(W)) + 1e-12)

    rows, total, n_judge = [], 0, 0
    for tid in todo:
        side = os.path.join(a.root, "gen_b2/aime", f"{tid}.json")
        j = json.load(open(side, encoding="utf-8"))
        if (j.get("config") or {}).get("mode") != "think":
            raise SystemExit(f"{tid} 不是 think 轨迹，池子算错了")
        ts = [i for i, t in enumerate(j.get("tokens") or [])
              if t.get("token_id") in MK]
        if not ts:
            continue
        z = np.load(os.path.join(a.root, "gen_b2/aime", f"{tid}.npz"))
        hs = np.asarray(z["hidden_states"])
        z.close()
        pairs = []
        for i in ts:
            h = hs[i - 1, NPZ, :].astype(np.float64)
            pairs.append((i, float(W @ (h / np.linalg.norm(h)))))
        del hs
        top = pick_top_decile(pairs)
        if not top:
            continue
        rows.append({"traj": tid, "n_sites": len(ts),
                     "sites": [{"t": t, "w": round(w, 6),
                                "aw": round(abs(w), 6)} for t, w in top]})
        total += len(top)
        n_judge += 1 if len(top) >= 8 else 0
        print(f"  {tid:<30} marker {len(ts):<4} → 极对齐 {len(top):<3} "
              f"|w·ĥ| 最小 {min(abs(w) for _, w in top):.4f}", flush=True)

    rows.sort(key=lambda r: -len(r["sites"]))
    out = {"schema": "extreme_pick/1",
           "prereg": "R6_RERUN_PREREG.md 修订 30 §30.3",
           "rule": ("逐轨迹取 |w·ĥ| 最高 10% 的 marker 位点；"
                    "并列时取 |w·ĥ| 更大的；选材只依赖预测量，不依赖 Δ"),
           "decile": DECILE,
           "excluded_already_measured": sorted(measured),
           "n_tracks": len(rows), "n_sites": total,
           "n_tracks_ge8": n_judge,
           "tracks": rows}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{len(rows)} 条轨迹、合计 {total} 个极对齐位点；"
          f"其中位点数 ≥8（E2 可判）的轨迹 {n_judge} 条")
    print(f"前向估计 = {total}×3×2 + {len(rows)} = {6*total+len(rows)}")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()
