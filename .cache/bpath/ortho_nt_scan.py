"""no_think 侧的极对齐选材扫描（**静态、纯 numpy，不用 GPU**）。

## 为什么要做

§33.6 在 think 的 E 批次里看到一个**事后**形状：`|w·ĥ|` 最高一档的 Δ 中位
转正（+1.500），而下面三档都是负的（≈ −1.5 ~ −1.75）。那是**事后切片**，
不能当结论。要检验它必须有**新数据**，而 think 池已经用尽：

    think 池 58 = 修订 28 的 30 + 修订 32 E 批次的 26 + 剩 2
    而剩下的 2 条（aime25_p03/p05）**恰好是被绝对边界剔掉的那两条**
    —— 它们的最高十分位全部 `|w·ĥ| ≤ 0.1`，对这个问题是结构性不可用的。

⇒ 还能拿到新数据的只剩 no_think 侧（远端 60 条，已测 10 条）。

⚠ **mode 不同就是另一个总体。** 本扫描只回答
「在 no_think 上能不能采到足够的极对齐位点」，
**不能**把 think 上的结论直接外推过来（§28.2 的作用域纪律）。

## 选材为什么不可能偏向结果

选材只用**预测量** `w·ĥ`：marker 位点集 → 取 `|w·ĥ|` 最高十分位 → 过绝对边界。
输入里**一个 Δ 都没有**，所以结构上不可能偏向任何方向的结果。

## 与 think 侧同口径

- 绝对边界 `|w·ĥ| > 0.10`（修订 32）——**先取十分位、再过边界**，顺序不能反；
- `NPZ_LAYER = 19`，`h = hs[i-1, 19, :]`（坐标系三条事实，见 `r6_rerun.py`）；
- marker 集合 `MARKER_IDS` 七个 id，与探针一致。

## 守卫

⚠ 显式 `raise`，不用 `assert` —— `python -O` 会关掉 `assert`。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MARKER_IDS = (13824, 14190, 6771, 10061, 7196, 88190, 80022)
MK = set(MARKER_IDS)
NPZ = 19
DECILE = 0.10
ORTH_MIN = 0.10          # 与 ortho_extreme_scan.ORTH_MIN 同值
ROOT = "/home/zhourui/steer3d_bpath"


def pick_top_decile(pairs, decile=DECILE, orth_min=ORTH_MIN):
    """pairs: [(t, w)] -> 最高十分位 **且** |w| > orth_min；返回值按 t 升序。

    ⚠ 顺序不能反：先过边界会改变十分位的分母。
    """
    if not pairs:
        return []
    k = max(1, int(len(pairs) * decile))
    order = sorted(pairs, key=lambda p: (-abs(p[1]), p[0]))
    top = [p for p in order[:k] if abs(p[1]) > orth_min]
    return sorted(top, key=lambda p: p[0])


def scan_one(root, tid, W):
    """返回**键集合恒定**的记录。

    ⚠ 第一版有两处 `return`，键集合不一致（一条有 `n_hi`/`aw_max`，
       另一条没有）⇒ 调用方按第一条的键打印，第二条直接 KeyError。
       这类「同一个函数多条返回路径」的 bug 一条路径不会暴露，
       另一条必然炸。⇒ 这里**只有一条 return**，空情形也走它。
    """
    side = os.path.join(root, "gen_b2/aime", f"{tid}.json")
    j = json.load(open(side, encoding="utf-8"))
    mode = (j.get("config") or {}).get("mode")
    ts = [i for i, t in enumerate(j.get("tokens") or [])
          if t.get("token_id") in MK]

    n_hi, aw_max, top, note = 0, None, [], ""
    if not ts:
        note = "没有 marker 位点"
    else:
        # ⚠ 整块读一次，再在 numpy 侧切片（NpzFile.__getitem__ 每次重解压整个数组）
        z = np.load(os.path.join(root, "gen_b2/aime", f"{tid}.npz"))
        hs = np.asarray(z["hidden_states"])
        z.close()
        if hs.ndim != 3:
            raise SystemExit(f"{tid}: hidden_states 维度 {hs.shape} != 3")
        if hs.shape[1] != 28:
            raise SystemExit(f"{tid}: 层数 {hs.shape[1]} != 28")
        pairs = []
        for i in ts:
            if i - 1 < 0:
                continue                    # t=0 没有前一位，注入下标不成立
            h = hs[i - 1, NPZ, :].astype(np.float64)
            pairs.append((i, float(W @ (h / np.linalg.norm(h)))))
        del hs
        top = pick_top_decile(pairs)
        aw_all = [abs(w) for _, w in pairs]
        n_hi = sum(1 for a in aw_all if a > ORTH_MIN)
        aw_max = round(max(aw_all), 6) if aw_all else None
        if not top and aw_all:
            note = (f"最高十分位里没有一个位点过 |w·ĥ| > {ORTH_MIN}"
                    f"（该轨迹 aw 最大 {max(aw_all):.4f}）")
        elif not aw_all:
            note = "没有可算的位点（marker 全在 t=0）"

    return {"traj": tid, "mode": mode, "n_sites": len(ts), "n_hi": n_hi,
            "aw_max": aw_max, "note": note,
            "sites": [{"t": t, "w": round(w, 6), "aw": round(abs(w), 6)}
                      for t, w in top]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--mode", default="no_think",
                    choices=["no_think", "think"])
    ap.add_argument("--exclude", default=None,
                    help="已测轨迹清单（JSON 数组）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0,
                    help="只扫前 N 条（试点用，0=全扫）")
    ap.add_argument("--expect-pool", type=int, default=None)
    a = ap.parse_args()

    excl = set()
    if a.exclude:
        excl = set(json.load(open(a.exclude, encoding="utf-8")))

    allt = sorted(os.path.basename(p)[:-5] for p in
                  glob.glob(os.path.join(a.root, "gen_b2/aime",
                                          f"*__{a.mode}.json")))
    todo = [t for t in allt if t not in excl]
    if a.expect_pool is not None and len(todo) != a.expect_pool:
        raise SystemExit(f"待测轨迹应为 {a.expect_pool} 条，实际 {len(todo)}")
    if a.limit:
        todo = todo[:a.limit]
        print(f"⚠ 试点模式：只扫前 {len(todo)} 条（--limit {a.limit}）")

    W = np.load(os.path.join(a.root, "w_L19_m0.npy")).astype(np.float32)
    W = W / (float(np.linalg.norm(W)) + 1e-12)

    rows, total, n_judge, n_drop = [], 0, 0, 0
    for tid in todo:
        r = scan_one(a.root, tid, W)
        if r["mode"] != a.mode:
            raise SystemExit(f"{tid} 的 mode 是 {r['mode']}，池子算错了")
        if not r["sites"]:
            n_drop += 1
            # ⚠ 用 r.get 而不是 r["note"] —— scan_one 一定给 note，
            #    但这里若再写错键就会 KeyError 崩在**打印**上，
            #    把「这条轨迹没被选中」变成「整个扫描失败」。
            print(f"  {tid:<32} marker {r['n_sites']:<4} hi {r['n_hi']:<4}"
                  f" → 0（{r.get('note', '未说明原因')}）", flush=True)
            continue
        rows.append(r)
        total += len(r["sites"])
        n_judge += 1 if len(r["sites"]) >= 8 else 0
        print(f"  {tid:<32} marker {r['n_sites']:<4} hi {r['n_hi']:<4} "
              f"→ 极对齐 {len(r['sites']):<3} aw_max {r['aw_max']:.4f}",
              flush=True)

    rows.sort(key=lambda r: (-len(r["sites"]), r["traj"]))
    out = {"schema": "nt_pick/1",
           "prereg": "R6_RERUN_PREREG.md 修订 34（no_think 侧的可行性清点）",
           "rule": ("逐轨迹取 |w·ĥ| 最高 10% 的 marker 位点（名额 k 由该轨迹 "
                    "marker 总数决定，**不受**绝对边界影响）**且** |w·ĥ| > 0.10；"
                    "先取十分位再过边界。选材只依赖预测量，不依赖 Δ"),
           "mode": a.mode,
           "decile": DECILE, "orth_min": ORTH_MIN,
           "excluded_already_measured": sorted(excl),
           "n_candidates": len(todo),
           "n_tracks": len(rows), "n_sites": total,
           "n_tracks_ge8": n_judge, "n_tracks_dropped": n_drop,
           "tracks": rows}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    print(f"\n候选 {len(todo)} 条 ⇒ 有极对齐位点的 {len(rows)} 条、"
          f"合计 {total} 个位点；≥8 位点的 {n_judge} 条；"
          f"过完边界归零的 {n_drop} 条")
    print(f"前向估计 = {total}×3×2 + {len(rows)} = {6 * total + len(rows)}")
    print(f"写出 {a.out}")


if __name__ == "__main__":
    main()