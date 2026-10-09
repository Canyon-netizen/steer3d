"""量两个数：类均值差向量的真实长度，以及它与 ||h|| 的比。

## 为什么必须先量这个

注入尺度现在是 `alpha = rel * class_gap`，而 `class_gap` 是
**类均值差在 w 方向上的投影**（`|W|=1` 时 `class_gap = W·Δ̄`，Δ̄ = 类均值差）。

投影长度 **不等于** Δ̄ 的长度：Δ̄ 里垂直于 w 的分量对 class_gap 完全不可见。
若 ||Δ̄|| 远大于 class_gap，那么 `alpha = rel * class_gap` 就是**系统性偏小**的剂量
——不是「剂量不够大所以量不到」，而是**尺度取错了**。

## 为什么不能靠「调到能过为止」

预登记明令「不因 p 值大小改口」。剂量尺度必须**先定死规则**再跑。
本脚本只负责提供制定规则所需的**量**，不负责判定通过与否。

## 输出
  gap_proj  = class_gap（w 方向投影，隐状态单位）
  gap_norm  = ||Δ̄||        （类均值差向量的真实长度）
  cos       = W·Δ̄ / ||Δ̄||（探针方向与类均值差的对齐度）
  h_norm    = ||h|| 中位数（隐状态自然尺度）
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import numpy as np

MARKER_IDS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
LAYER = 20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz-dir", required=True)
    ap.add_argument("--sidecar-dir", required=True)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    pos_by, P_by, T_by = {}, {}, {}
    for f in sorted(Path(a.sidecar_dir).glob("*.json")):
        j = json.load(open(f, encoding="utf-8"))
        if j["config"]["mode"] != "think":
            continue
        mk = [i for i, t in enumerate(j.get("tokens") or [])
              if t["token_id"] in MARKER_IDS]
        if len(mk) < 3:
            continue
        tid = j["trajectory_id"]
        pos_by[tid] = mk
        P_by[tid] = (j.get("extra") or {}).get("prompt_tokens")
        T_by[tid] = j["n_generated_tokens"]
        if len(pos_by) >= a.limit:
            break

    rng = np.random.default_rng(42)
    pos_all, neg_all, hnorm, off = [], [], [], []
    per_traj = {}
    for tid in sorted(pos_by):
        z = np.load(Path(a.npz_dir) / f"{tid}.npz")
        H = z["hidden_states"][:, LAYER, :].astype(np.float32)
        z.close()
        P, T, mk = P_by[tid], T_by[tid], pos_by[tid]
        # 坐标系核对：npz 全序列长度应当等于 P_actual + T，
        # 而 extra.prompt_tokens 是 add_special_tokens=False 的分词数，
        # 两者可能差几个特殊 token。修订 3 的 C4 验过 22/22，这里再打一次。
        P_actual = H.shape[0] - T
        off.append((tid, P, P_actual, H.shape[0]))
        P = P_actual          # 用 npz 自己给出的 P，不信侧车
        if P < 0:
            continue
        pos_idx = [P + t - 1 for t in mk if 0 <= P + t - 1 < H.shape[0]]
        cand = np.setdiff1d(np.arange(T), np.array(mk, dtype=int))
        neg_idx = [P + int(cand[np.argmin(np.abs(cand - t))]) - 1 for t in mk] \
            if len(cand) else []
        neg_idx = [i for i in neg_idx if 0 <= i < H.shape[0]]
        if not pos_idx or not neg_idx:
            continue
        pos_all.append(H[pos_idx])
        neg_all.append(H[neg_idx])
        hnorm.extend(np.linalg.norm(H, axis=-1).tolist()[::7])
        per_traj[tid] = {"n_pos": len(pos_idx), "n_neg": len(neg_idx)}
        del H

    print(f"[坐标系] 侧车 extra.prompt_tokens vs npz 实际 P（共 {len(off)} 条）")
    diffs = [b - a for _, a, b, _ in off]
    print(f"  差值 中位 {st.median(diffs):.0f}  范围 {min(diffs)}~{max(diffs)}"
          f"  非零 {sum(1 for d in diffs if d)}/{len(diffs)}")
    if not pos_all:
        print("没有可用轨迹")
        return
    Pm = np.concatenate(pos_all, 0)
    Nm = np.concatenate(neg_all, 0)
    dbar = Pm.mean(0) - Nm.mean(0)
    gap_norm = float(np.linalg.norm(dbar))
    h_med = float(st.median(hnorm))
    print(f"[人口] think 轨迹 {len(per_traj)}，正例 {len(Pm)}，负例 {len(Nm)}")
    print(f"  ||h|| (layer{LAYER}) 中位 {h_med:.1f}")
    print(f"  ||Δ̄|| = {gap_norm:.2f}   （类均值差向量的真实长度）")
    print(f"  ||Δ̄|| / ||h|| = {gap_norm / h_med:.3f}")
    print(f"  正类自身离散度（std 的均方） {float(np.linalg.norm(Pm.std(0))):.2f}")
    print(f"  负类自身离散度             {float(np.linalg.norm(Nm.std(0))):.2f}")

    res = {"n_traj": len(per_traj), "n_pos": len(Pm), "n_neg": len(Nm),
           "layer": LAYER, "gap_norm": gap_norm, "h_norm_median": h_med,
           "P_offset_median": st.median(diffs), "P_offset_range": [min(diffs), max(diffs)],
           "ratio": gap_norm / h_med,
           "pos_spread": float(np.linalg.norm(Pm.std(0))),
           "neg_spread": float(np.linalg.norm(Nm.std(0)))}
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
    print("\n写出", a.out)


if __name__ == "__main__":
    main()