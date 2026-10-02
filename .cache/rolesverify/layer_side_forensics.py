#!/usr/bin/env python3
"""量化一个自查出来的口径错位：向量在哪一层提取、在线注入又作用在哪一层。

## 三个已核实的事实

1. `hidden_states[:,27]` 与 `last_hidden` **逐位相同**（max|diff| = 0.0），
   且范数 L0→L26 单调升到 3081.25、L27 突降到 126.79（比值 0.0411）。
   ⇒ `hidden_states[:, L]` 是**第 L 个 block 的输出**，
     「进入第 L 个 block 的残差」这个说法**错了一位**。

2. `compute_steering_vectors.py:89` 取 `hs[:, layer, :]`（默认 `--layer 14`）
   ⇒ 向量取自 `hidden_states[:,14]` = block 14 的输出 = **block 15 的输入**。

3. `model_runner._install_add_hook` / `activation.install_residual_add_hook`
   都是 `block.register_forward_pre_hook`，作用在 block `layer_idx` 的**输入**
   ⇒ 注入改的是 `hidden_states[:, layer_idx − 1]`。

**合起来：注入层号 14 实际扰动 `hidden_states[:,13]`，而向量取自
`hidden_states[:,14]`。相差一个 block，且注入比提取早一块。**

## 为什么这不只是措辞

注入量是 `a = unit_v · s · rms(L)`（绝对量，与方向无关）。
离线强度扫描扰动的就是 `hidden_states[:,L]`，所以 `‖h‖ = rms(L)`，
相对幅度恰为 `s`，定律退化成 `Δ ≈ ½s²` —— 自洽。

在线路径扰动 `hidden_states[:,L−1]`，`‖h‖ = rms(L−1)`，于是真实相对幅度是

    s · rms(L) / rms(L−1)   ≠   s

本脚本量三样东西，全部自己复算：
  A. 同一分组（熵 p30/p75）在 L13 与 L14 上重算的 contrast 方向之间的 cos
     —— 决定「差一块」是纯标量问题还是方向也变了
  B. 两个重算方向与磁盘上 `confidence_up.npy` 的 cos
     —— 确认磁盘上的向量确实是 L14 那一版
  C. `rms(13)`、`rms(14)` 与真实相对幅度比 `rms(14)/rms(13)`
"""
import glob
import json
from pathlib import Path

import numpy as np

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ = sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))
VEC = ROOT / "backend/examples/output/steering_vectors/confidence_up.npy"
OUT = ROOT / ".cache/rolesverify/layer_side_forensics.json"
LAYERS = [13, 14]
_ERR = dict(all="ignore")


def unit(x):
    x = np.asarray(x, np.float64)
    return x / np.linalg.norm(x)


def main():
    res = {
        "schema": "steer3d.layer_side_forensics/1",
        "claim": "hidden_states[:,L] 是第 L 个 block 的输出，不是进入 block L 的残差",
        "layers_compared": LAYERS,
    }

    # ---- 事实 1：层语义 ------------------------------------------------
    d0 = np.load(NPZ[0])
    hs0 = d0["hidden_states"]
    lh0 = d0["last_hidden"]
    a = hs0[:, 27, :].astype(np.float64)
    b = lh0.astype(np.float64)
    norms = [float(np.linalg.norm(hs0[:, L, :].astype(np.float64), axis=1).mean())
             for L in range(28)]
    res["layer_semantics_evidence"] = {
        "max_abs_diff_hs27_vs_last_hidden": float(np.abs(a - b).max()),
        "bitwise_identical": bool(np.array_equal(a, b)),
        "mean_norm_by_layer": {str(L): norms[L] for L in [0, 12, 13, 14, 15, 26, 27]},
        "norm_drop_26_to_27_ratio": norms[27] / norms[26],
        "verdict": "L27 == 最后一个 block 经最终 RMSNorm 后的状态 ⇒ 下标 L = 第 L 个 block 的输出",
    }

    # ---- 事实 2/3：提取层与注入侧 ---------------------------------------
    res["code_evidence"] = {
        "vector_extraction": "compute_steering_vectors.py:89  gen_hidden = hs[:, layer, :]  (--layer 14)",
        "injection": "model_runner._install_add_hook / activation.install_residual_add_hook "
                     "= block.register_forward_pre_hook(layer_idx) ⇒ 改的是 block layer_idx 的输入 "
                     "= hidden_states[:, layer_idx-1]",
        "mismatch": "向量取自 hidden_states[:,14]（block 14 输出），注入 layer_idx=14 改的是 "
                    "hidden_states[:,13]（block 13 输出）。相差一块，注入比提取早一块。",
    }

    # ---- A/B/C：重算 contrast 方向 ---------------------------------------
    # 分组口径逐字对齐 steering_vectors.json：low-entropy p30 vs high-entropy p75
    pos_acc = {L: np.zeros(2048, np.float64) for L in LAYERS}
    neg_acc = {L: np.zeros(2048, np.float64) for L in LAYERS}
    n_pos = {L: 0 for L in LAYERS}
    n_neg = {L: 0 for L in LAYERS}
    norm_acc = {L: 0.0 for L in LAYERS}
    norm_n = {L: 0 for L in LAYERS}
    ent_all = []

    for f in NPZ:
        z = np.load(f)
        side = json.loads(f.with_suffix(".json").read_text())
        toks = side["tokens"]
        T = len(toks)
        ent = np.asarray([t["entropy"] for t in toks], np.float64)
        ent_all.append(ent)
        hs = z["hidden_states"]
        lo, hi = np.percentile(ent, [30, 75])
        mpos = ent <= lo
        mneg = ent >= hi
        for L in LAYERS:
            h = np.asarray(hs[:, L, :], np.float64)
            pos_acc[L] += h[mpos].sum(axis=0)
            n_pos[L] += int(mpos.sum())
            neg_acc[L] += h[mneg].sum(axis=0)
            n_neg[L] += int(mneg.sum())
            norm_acc[L] += float(np.linalg.norm(h, axis=1).sum())
            norm_n[L] += T

    dirs = {}
    for L in LAYERS:
        dirs[L] = unit(pos_acc[L] / n_pos[L] - neg_acc[L] / n_neg[L])

    stored = unit(np.load(VEC).astype(np.float64).ravel())
    rms = {L: norm_acc[L] / norm_n[L] for L in LAYERS}

    res["recompute"] = {
        "grouping": "entropy p30 (low) vs p75 (high)，与 steering_vectors.json 的 "
                    "positive_group/negative_group 同口径",
        "n_positive": n_pos[14], "n_negative": n_neg[14],
        "n_trajectories": len(NPZ),
        "mean_hidden_norm": {str(L): rms[L] for L in LAYERS},
        "cos_recomputed_L13_vs_L14": float(dirs[13] @ dirs[14]),
        "cos_stored_vs_recomputed": {str(L): float(stored @ dirs[L]) for L in LAYERS},
        "norm_ratio_14_over_13": rms[14] / rms[13],
    }

    r = res["recompute"]
    s = 0.1
    a_off = s * rms[14]
    res["consequences"] = {
        "offline_scan": {
            "perturbed_state": "hidden_states[:,L]",
            "relative_amplitude": s,
            "law": "Δ ≈ ½·s²，自洽",
        },
        "live_path": {
            "perturbed_state": "hidden_states[:,L-1]",
            "relative_amplitude": s * rms[14] / rms[13],
            "value_at_s_0.1": s * rms[14] / rms[13],
            "amplification_vs_offline": rms[14] / rms[13],
        },
        "injected_vector_norm_at_s_0.1": a_off,
        "direction_error": {
            "cos_L13_L14": r["cos_recomputed_L13_vs_L14"],
            "cos_stored_vs_L14": r["cos_stored_vs_recomputed"]["14"],
            "cos_stored_vs_L13": r["cos_stored_vs_recomputed"]["13"],
            "reading": (
                "若 cos(L13,L14) 接近 1，则差一块主要是标量问题（在线幅度偏大）；"
                "若明显小于 1，则连方向也不一样，在线注入的东西不是被表征过的那个方向"
            ),
        },
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res["recompute"], ensure_ascii=False, indent=1))
    print(json.dumps(res["consequences"], ensure_ascii=False, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
