#!/usr/bin/env python3
"""S3 — item 4：注入点在 L13，所以标称 s 在注入点的真实相对幅度是多少。

## 怎么跑

    cd /Users/zhourui/code/steer3d
    python3 .cache/layerside2/s1_cache_facts.py   # 产出 hidden_L{12..15}.npy
    python3 .cache/layerside2/s3_injection_amp.py  # 本脚本

产物：s3_injection_amp.json

## 口径（全部来自实测 ‖h‖，不用推测）

在线路径的两条事实（代码证据，见 s3 输出的 code_evidence）：
  1. `SteeringRegistry.scaled()` (backend/core/steering.py:218) 返回
     `v * (strength * layer_rms(layer))` —— 幅度按**被请求的层号** L=14 定标。
  2. `register_forward_pre_hook(block 14)` 扰动的是 block 14 的**输入**，
     也就是 `hidden_states[:,13]`。

于是 ‖δ‖ = s · mean‖h_L14‖，但它落在范数为 mean‖h_L13‖ 的状态上：

    注入点相对幅度  a = s · mean‖h_L14‖ / mean‖h_L13‖ = s · R
    「L14 处的 s=0.2 等价于 L13 处的 s=?」= 0.2 · R

## 两个 mean‖h‖ 来源，都要报

在线实际读的是 `layer_profiles.json` 的 `mean_norm`（20010 个 token 的
子采样），全量重算（本脚本，69155 步）差 0.05%。结论不依赖选哪个，
但引用时必须说明是哪一个，所以两套都算。

## 几何代价的定义要说清

文档 §2 给 `a = s·rms(L)/‖h‖`，代价 ≈ ½a²。逐 token 的 a 不同
（‖h‖ 有分布），所以「实测代价」应是对每个 token 各自算 a 再平均 ½a²：
    E[½a²] = ½ s² M² E[1/‖h‖²]，  M = mean‖h‖
Jensen 不等式说明它 **≥** ½s² —— 这正是文档 L20 表里 s=0.20 记 2.236%
而不是 2.00% 的原因。本脚本用实测 ‖h‖ 分布把 E[1/‖h‖²] 算出来，
于是 L13 与 L14 的代价都能用同一条公式给出。
"""
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path("/Users/zhourui/code/steer3d")
OUT = Path(__file__).resolve().parent
PROFILES = ROOT / "backend/examples/output/layer_profiles.json"
S_NOMINAL = 0.2


def main():
    t0 = time.time()
    idx = json.loads((OUT / "traj_index.json").read_text())
    norms = {}
    for L in (13, 14):
        H = np.load(OUT / f"hidden_L{L}.npy", mmap_mode="r")
        alln = np.empty(idx["total_rows"], dtype=np.float64)
        for e in idx["traj"]:
            h = np.asarray(H[e["start"]:e["stop"]], dtype=np.float64)
            alln[e["start"]:e["stop"]] = np.sqrt((h * h).sum(axis=1))
        inv2 = 1.0 / (alln * alln)
        hsum = np.zeros(H.shape[1], dtype=np.float64)
        for e in idx["traj"]:
            hsum += np.asarray(H[e["start"]:e["stop"]], dtype=np.float64).sum(axis=0)
        norms[L] = {
            "n_steps": int(alln.size),
            "mean_L2norm": float(alln.mean()),
            "std_L2norm": float(alln.std()),
            "mean_of_L2norm_squared": float((alln ** 2).mean()),
            "mean_of_inverse_L2norm_squared": float(inv2.mean()),
            # 文档 §2.1 说 layer_rms「实际是均值的 L2 范数」——实测是 mean(‖h‖)，
            # 不是 ‖mean(h)‖。两个都算出来，报告里可引用。
            "L2norm_of_mean": float(np.linalg.norm(hsum / alln.size)),
            "min": float(alln.min()), "max": float(alln.max()),
            "p05": float(np.percentile(alln, 5)),
            "p50": float(np.percentile(alln, 50)),
            "p95": float(np.percentile(alln, 95)),
        }
        del alln, inv2, H

    prof = {e["layer"]: e for e in json.loads(PROFILES.read_text())["layers"]}
    res = {
        "schema": "layerside2.s3_injection_amp/1",
        "s_nominal": S_NOMINAL,
        "code_evidence": {
            "scaled": "backend/core/steering.py:218  v * (strength * layer_rms(layer))"
                       " —— 幅度按被请求的层号 L=14 定标",
            "hook": "backend/core/activation.py:44-50 / model_runner.py:277-283 / "
                    "run_intervention.py:176-183 均为 block.register_forward_pre_hook(L)，"
                    "扰动 block L 的输入 = hidden_states[:, L-1]",
            "consequence": "‖δ‖ = s · mean‖h_L14‖，但落在范数 mean‖h_L13‖ 的状态上",
        },
        "norms_full_69155_steps": norms,
        "layer_profiles_json_mean_norm": {
            "L13": prof[13]["mean_norm"], "L14": prof[14]["mean_norm"],
            "n_tokens": prof[13]["n_tokens"],
            "note": "在线实际读取的定标值（20010 token 子采样）",
        },
    }

    M13 = norms[13]["mean_L2norm"]
    M14 = norms[14]["mean_L2norm"]
    P13 = prof[13]["mean_norm"]
    P14 = prof[14]["mean_norm"]
    E13 = norms[13]["mean_of_inverse_L2norm_squared"]
    E14 = norms[14]["mean_of_inverse_L2norm_squared"]

    variants = {}
    for tag, m13, m14 in (("full_recompute_69155", M13, M14),
                          ("layer_profiles_json_20010", P13, P14)):
        R = m14 / m13
        a_inject = S_NOMINAL * R
        # 同一绝对 ‖δ‖ 下，L13 要用多大的标称 s
        s_equiv = S_NOMINAL * R
        # 逐 token 平均的几何代价 E[½a²]（a 用各自层的 E[1/‖h‖²]）
        cost_inject = 0.5 * S_NOMINAL ** 2 * m14 ** 2 * E13
        cost_nominal_L14 = 0.5 * S_NOMINAL ** 2 * m14 ** 2 * E14
        cost_plain_analytic = 0.5 * S_NOMINAL ** 2
        variants[tag] = {
            "mean_norm_L13": m13, "mean_norm_L14": m14,
            "R_ratio_L14_over_L13": R,
            "injected_delta_norm_at_s_nominal": S_NOMINAL * m14,
            "relative_amplitude_at_injection_point": a_inject,
            "s_equivalent_at_L13_for_same_delta": s_equiv,
            "geometric_cost_half_a2_nominal_s_plain": cost_plain_analytic,
            "geometric_cost_per_token_avg_at_injection_point": cost_inject,
            "geometric_cost_per_token_avg_at_L14": cost_nominal_L14,
            "cost_inflation_vs_plain": cost_inject / cost_plain_analytic,
        }
    res["variants"] = variants

    res["headline"] = {
        "R_using_layer_profiles_json": variants[
            "layer_profiles_json_20010"]["R_ratio_L14_over_L13"],
        "R_full_recompute": variants["full_recompute_69155"]["R_ratio_L14_over_L13"],
        "relative_amplitude_at_injection_point_at_s_0.2": variants[
            "layer_profiles_json_20010"]["relative_amplitude_at_injection_point"],
        "s_equivalent_at_L13": variants[
            "layer_profiles_json_20010"]["s_equivalent_at_L13_for_same_delta"],
        "geometric_cost_at_injection_point_frac": variants[
            "layer_profiles_json_20010"][
                "geometric_cost_per_token_avg_at_injection_point"],
        "geometric_cost_at_injection_point_pct": 100 * variants[
            "layer_profiles_json_20010"][
                "geometric_cost_per_token_avg_at_injection_point"],
        "doc_L20_s0.20_analytic_frac": 0.02236,
        "doc_L20_s0.20_4_named_dirs_frac": 0.02240,
        "doc_claim_being_checked": "标称 s=0.2 实为相对幅度 0.236，几何代价 2.78%"
                                   "（而非文档写的 2.24%）",
    }
    res["elapsed_sec"] = round(time.time() - t0, 1)
    (OUT / "s3_injection_amp.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res["headline"], ensure_ascii=False, indent=1))
    print(json.dumps(variants, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
