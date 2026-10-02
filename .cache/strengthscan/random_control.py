#!/usr/bin/env python3
"""随机方向对照的分布，而不是单点。

`scan_v2.py` 只跑了一个随机方向，于是「真实 0.571 vs 随机 0.037」
是**一个样本对一个样本**。子智能体的复算报告已经指出
vector_roles 那批数据犯过同一类错：用 16 个随机方向里的最大值
当地板，而「打败 16 个」的零假设通过率恰是 6.25%。

所以这里跑 200 个固定 seed 的随机方向，报告真实方向在分布里的分位，
而不是"比一个随机值大多少"。

同时验一个更硬的问题：**置信向量真的特殊，还是因为它更长/更对齐？**
**两对**方向是同一向量的反向（confidence_up/down、reasoning_deep/shallow，
注册表里标了 derived_from），它们在 subspace_frac 上应该完全相同 ——
如果不等，说明我的计算有 bug。

注意是**两对**不是三对。早先这里写的是"三个方向是同一向量的反向"，
页面上也跟着写成了 "three opposite pairs"，而注册表里 derived_from
只有两条；caution 与 creativity 并不是反向的（实测 cos = +0.342862）。
6 个标签实际对应 4 条独立向量。
"""
import json
import os
import sys

import numpy as np

REPO = "/Users/zhourui/code/steer3d"
sys.path.insert(0, REPO)

from backend.core.replay_runner import NpzReplayRunner  # noqa: E402
from backend.core.steering import get_registry  # noqa: E402

LAYERS = [12, 14, 16, 20, 24]
N_RANDOM = 200
SEED = 20261003
N_TRAJ = 4
N_STEPS = 10
TOPK = 3


def main():
    runner = NpzReplayRunner()
    reg = get_registry()
    names = list(reg.names)

    # One basis per layer, from a fixed sample.
    basis = {}
    top3_var = {}
    for L in LAYERS:
        X = []
        for r in runner.records[:3]:
            z = np.load(r["npz"], mmap_mode="r")
            st = [int(round(x)) for x in np.linspace(z["hidden_states"].shape[0] * 0.35,
                                                      z["hidden_states"].shape[0] - 1, 24)]
            X.append(np.asarray(z["hidden_states"][st, L, :], dtype=np.float32))
        X = np.concatenate(X, 0)
        Xc = X - X.mean(0)
        # 奇异值平方和 = 总方差，所以前 k 个成分解释的比例可以直接算出来。
        # 页面上"这个 3 维子空间只占 19% 方差"这句话必须能对回这里的数。
        sv = np.linalg.svd(Xc, compute_uv=False)
        var = sv ** 2
        top3_var[L] = float(var[:TOPK].sum() / var.sum())
        _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
        basis[L] = Vt[:TOPK]
    print("top-%d 方差占比: %s" % (
        TOPK, "  ".join("L%d=%.4f" % (L, top3_var[L]) for L in LAYERS)), file=sys.stderr)

    def subspace_frac(v, L):
        return float(np.linalg.norm(basis[L] @ v) / np.linalg.norm(v))

    # --- the two opposite pairs must agree --------------------------
    # 注意只有**两对**，不是三对：caution 与 creativity 并不是反向的
    # （实测 cos = +0.34）。页面上"三对"的说法就是这么来的。
    print("=== 反向向量对的自洽性（同向量取反，subspace_frac 应完全相同）", file=sys.stderr)
    pairs = [("confidence_up", "confidence_down"), ("reasoning_deep", "reasoning_shallow")]
    flip_check = []
    for a, b in pairs:
        rows = []
        for L in LAYERS:
            fa = subspace_frac(np.asarray(reg.scaled(a, 0.2, L), dtype=np.float64), L)
            fb = subspace_frac(np.asarray(reg.scaled(b, 0.2, L), dtype=np.float64), L)
            flag = "OK " if abs(fa - fb) < 1e-9 else "MISMATCH"
            rows.append({"layer": L, "a": a, "b": b, "frac_a": fa, "frac_b": fb,
                         "abs_diff": abs(fa - fb), "ok": flag.strip() == "OK"})
            print("  %-20s L%-3d %.6f vs %.6f  %s" % (f"{a}/{b}", L, fa, fb, flag),
                  file=sys.stderr)
        flip_check.append({"pair": [a, b], "rows": rows,
                           "max_abs_diff": max(r["abs_diff"] for r in rows),
                           "all_equal": all(r["ok"] for r in rows)})
    # 未成对的两个也记下来，免得读者以为 6 个标签 = 3 对
    # 注意：reg.scaled() 返回的是**带该层 RMS 标度**的向量（实测点积量级 ~370），
    # 算余弦必须先归一化，否则得到的是范数平方而不是余弦。
    unpaired = {}
    for a, b in [("caution", "creativity")]:
        va = np.asarray(reg.scaled(a, 0.2, 14), dtype=np.float64)
        vb = np.asarray(reg.scaled(b, 0.2, 14), dtype=np.float64)
        c = float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))
        unpaired[a + "_vs_" + b] = {"cosine": c, "is_flip": abs(c + 1.0) < 1e-9}
        assert abs(c) <= 1.0 + 1e-9, "cosine out of range: %r" % c
        print("  %s vs %s: cos=%+.6f  (成反向? %s)" % (a, b, c, unpaired[a + "_vs_" + b]["is_flip"]),
              file=sys.stderr)

    # --- real vs a population of random directions -----------------
    rs = np.random.default_rng(SEED)
    rand = rs.standard_normal((N_RANDOM, 2048))
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)

    out = {"schema": "steer3d.strength_random_control/1",
           "n_random": N_RANDOM, "seed": SEED, "topk": TOPK,
           "layers": LAYERS, "per_layer": {},
           "top3_variance_frac": {str(L): top3_var[L] for L in LAYERS},
           "sign_flip_pairs": flip_check,
           "unpaired_cosine": unpaired}

    for L in LAYERS:
        rnd = np.array([subspace_frac(rand[i], L) for i in range(N_RANDOM)])
        real = {n: subspace_frac(np.asarray(reg.scaled(n, 0.2, L), dtype=np.float64), L)
                for n in names}
        thr_max = float(rnd.max())          # the bar the earlier artifact used
        p_gt = {n: float((rnd > v).mean()) for n, v in real.items()}
        out["per_layer"][str(L)] = {
            "random_mean": float(rnd.mean()), "random_std": float(rnd.std()),
            "random_min": float(rnd.min()), "random_max": float(rnd.max()),
            "random_p95": float(np.percentile(rnd, 95)),
            "bar_beating_all_200": thr_max,
            "family_wise_rate_if_bar_is_200_max": 1.0 / N_RANDOM,
            "real": real,
            "empirical_p_gt_random": p_gt,
            "best_real": float(max(real.values())),
            "best_over_random_max": float(max(real.values()) / thr_max),
        }
        print("\nL%-3d random over %d: mean=%.4f std=%.4f max=%.4f  (1/200=%.4f)"
              % (L, N_RANDOM, rnd.mean(), rnd.std(), rnd.max(), 1.0 / N_RANDOM),
              file=sys.stderr)
        for n in sorted(real, key=lambda k: -real[k]):
            print("    %-20s %.4f   P(random > this) = %.4f" % (n, real[n], p_gt[n]),
                  file=sys.stderr)

    path = os.path.join(REPO, ".cache/strengthscan/random_control.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("\nwrote " + path, file=sys.stderr)


if __name__ == "__main__":
    main()
