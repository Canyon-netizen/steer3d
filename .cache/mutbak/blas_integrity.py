#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境完整性检验：numpy's matmul 在这台机器上会报**伪** FPE，
需要判定它是「只报警不报错」还是「真的算错」。

## 为什么必须查

`numpy 2.0.2` 在本机对**内维 k ≥ 240** 的 matmul 一律报
`divide by zero encountered in matmul`（同一次调用里还同时报
overflow / underflow / invalid），但结果矩阵**逐元素有限**。

`(4,4) @ (4,4)` 不报；`randn(240,2048).T @ randn(240)` 报。
⇒ 触发条件是矩阵规模，不是数据。

**这不是小事**：PROBE 的 `A = H'WH + λI`、`c = (A)⁻¹ H'Wy`、
以及据此得到的 **AUROC 0.993** 全部走这条路径。
若 BLAS 真的算错，那 0.993 是假信号，本轮（乃至 PROBE 那轮）全部作废。

## 怎么判定

用**分块**复算绕开被怀疑的 kernel：把 k 维切成一列一列累加
（k=1 的乘加不可能触发大 kernel），得到独立参考值，逐元素比对。

- 分块与整体一致 ⇒ 警告是噪声，**数字可信**，只须记一条环境注记
- 分块与整体不一致 ⇒ **数字不可信**，PROBE 与 CAUSAL 的全部读数作废

## 输出

`.cache/mutbak/blas_integrity.json`
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, ".cache", "mutbak", "blas_integrity.json")


def matmul_ref(A, B, block=1):
    """按 k 维分块累加的参考实现。block=1 时每次是纯外积累加，
    不经过被怀疑的 GEMM kernel。"""
    k = A.shape[1]
    out = np.zeros((A.shape[0], B.shape[1]), dtype=np.float64)
    for s in range(0, k, block):
        e = min(k, s + block)
        out += A[:, s:e] @ B[s:e, :]
    return out


def compare(name, A, B, block, rel_tol=1e-9):
    full = A @ B
    ref = matmul_ref(A, B, block)
    fin = bool(np.isfinite(full).all())
    d = np.abs(full - ref)
    scale = max(1e-12, float(np.abs(ref).max()))
    md = float(d.max())
    rel = md / scale
    nbad = int((d > rel_tol * scale).sum())
    return {"name": name, "shape": [int(x) for x in np.array(A @ B).shape],
            "k": int(A.shape[1]), "block": block,
            "full_finite": fin, "max_abs_diff": md, "max_rel_diff": rel,
            "n_elems_over_tol": nbad,
            "verdict": "AGREE" if (fin and rel < rel_tol) else "DISAGREE"}


def main() -> int:
    print(f"numpy {np.__version__}  线程环境变量："
          f"OMP={os.environ.get('OMP_NUM_THREADS', '<unset>')} "
          f"OPENBLAS={os.environ.get('OPENBLAS_NUM_THREADS', '<unset>')}")
    rng = np.random.default_rng(20261008)
    rows = []

    # 1) 纯随机的中等矩阵 —— 不掺任何项目数据
    for k in (8, 64, 240, 512):
        A = rng.normal(size=(2048, k))
        B = rng.normal(size=(k, 512))
        rows.append(compare(f"随机 {A.shape} @ {B.shape}", A, B, 1))

    # 2) 项目里真实的那个矩阵形状（标准化后的 H'WH）
    X = rng.normal(size=(240, 2048)).astype(np.float32).astype(np.float64)
    mu = X.mean(0, keepdims=True)
    sd = X.std(0)
    Hn = (X - mu) / sd
    sgn = rng.choice([-1.0, 1.0], size=240)
    wgt = np.full(240, 0.5 / 120.0)
    rows.append(compare("H'·(H·w) 2048x240 @ 240x240", Hn.T, Hn * (wgt * sgn)[:, None], 1))
    rows.append(compare("H'·H 2048x240 @ 240x2048", Hn.T, Hn, 1))

    # 3) 求解 + 实际探针读数：整条链端到端比对
    lam = 1e4
    A_full = Hn.T @ (Hn * (wgt * sgn)[:, None]) + lam * np.eye(2048)
    b_full = Hn.T @ (wgt * sgn)
    A_ref = matmul_ref(Hn.T, Hn * (wgt * sgn)[:, None], 1) + lam * np.eye(2048)
    b_ref = matmul_ref(Hn.T, (wgt * sgn)[:, None], 1)[:, 0]
    c_full = np.linalg.solve(A_full, b_full)
    c_ref = np.linalg.solve(A_ref, b_ref)
    cos = float(c_full @ c_ref / (np.linalg.norm(c_full) * np.linalg.norm(c_ref)))
    s_full = (Hn - 0) @ c_full
    s_ref = Hn @ c_ref
    # 用合成标签算一遍 AUROC，看端到端结论是否一致
    def auc(scores, y):
        o = np.argsort(scores)
        r = np.empty(len(scores), float)
        r[o] = np.arange(1, len(scores) + 1)
        n1, n0 = int((y > 0).sum()), int((y == 0).sum())
        return float((r[y > 0].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

    y = np.array([1] * 120 + [0] * 120)
    a_full, a_ref = auc(s_full, y), auc(s_ref, y)
    print("\n=== 端到端（标准化 → 加权 Gram → 求解 → 打分 → AUROC）===")
    print(f"  系数向量余弦相似度      {cos:.12f}")
    print(f"  系数最大绝对差          {np.abs(c_full - c_ref).max():.3e}")
    print(f"  AUROC 整体路径          {a_full:.12f}")
    print(f"  AUROC 分块路径          {a_ref:.12f}")
    print(f"  AUROC 差                {abs(a_full - a_ref):.3e}")

    print("\n=== 逐矩阵比对（分块 k=1 为参考）===")
    for r in rows:
        flag = "✅" if r["verdict"] == "AGREE" else "❌"
        print(f"  {flag} {r['name']:34s} k={r['k']:4d} "
              f"有限={r['full_finite']} 最大相对差 {r['max_rel_diff']:.3e} "
              f"超差元素 {r['n_elems_over_tol']}")

    all_ok = all(r["verdict"] == "AGREE" for r in rows)
    end_ok = (cos > 1 - 1e-12) and abs(a_full - a_ref) < 1e-12
    print(f"\n  逐矩阵：{'全部一致' if all_ok else '存在不一致'}"
          f"    端到端：{'一致' if end_ok else '不一致'}")

    if all_ok and end_ok:
        print("\n  ⇒ 结论：这些 FPE 警告是**误报**。BLAS 在本机报了")
        print("    divide-by-zero / overflow，**但结果与分块参考逐元素一致**，")
        print("    端到端的 AUROC 也完全相同。")
        print("    ⇒ 数字可信。⚠ 但任何用 `-W error` 跑的项目脚本都会在这些")
        print("      调用上**假死**，这是环境缺陷，不是数据缺陷。")
    else:
        print("\n  ⇒ 结论：**BLAS 在本机算错了**。")
        print("    ⚠⚠ PROBE 的 AUROC 0.993 与 CAUSAL 的全部读数**作废**，")
        print("      必须换机器或换 BLAS 实现后重算。")

    json.dump({"numpy": np.__version__,
               "rows": rows,
               "coef_cos": cos,
               "auc_full": a_full, "auc_block": a_ref,
               "clean": bool(all_ok and end_ok)},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}")
    return 0 if (all_ok and end_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
