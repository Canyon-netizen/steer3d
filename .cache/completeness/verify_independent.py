#!/usr/bin/env python3
"""独立复核：不 import completeness.py 的任何东西，重写一遍最吃重的那几个数。

跑法（仓库根目录）：

    python3 .cache/completeness/verify_independent.py

复核 4 件事（结论报告里承重的）：

  V1  4 条命名轴张成的 S 的条件数与线性无关性
  V2  Δ=0 上 `step_frac` 的 S 解释份额应 ≈ 0.997（**阳性对照**：
      step_frac 是 reasoning_deep 的定义分组，S 真的覆盖它 ⇒ 同一把尺子必须报出接近 1）
  V3  Δ=0 上 `op_mass` / `newline_mass` / `latex_mass` 的 S 解释份额应 ≈ 0.02
      （同一把尺子读出接近 0 ⇒ 这三条轴一点也没覆盖它们）
  V4  `confidence`→`top1_prob_renorm` cos 应 ≈ 0.412、`caution`→`backtrack_topk`
      cos 应 ≈ 0.308、`step_frac`→`reasoning_deep` cos 应 ≈ 0.628

V2 与 V3 合起来才是「这把尺子可信」的根据：同一段代码在覆盖时给 0.997、
在不覆盖时给 0.016。若复核不出这个对比，前面所有数字都作废。

判据：与 completeness.json 对应键的偏差 ≤ 1e-6（本机同 dtype、同 BLAS，应逐位相同）。
"""
import json
import re
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
VEC = ROOT / "backend/examples/output/steering_vectors"
SRC = ROOT / ".cache/completeness/completeness.json"

LAYER, STRIDE, K, LAM = 14, 2, 256, 1e-2
AX = ["confidence_up", "caution", "creativity", "reasoning_deep"]
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)


def load():
    H, tgt = [], {k: [] for k in
                  ("op_mass", "newline_mass", "latex_mass", "step_frac", "top1_prob_renorm",
                   "backtrack_topk")}
    import csv
    for f in sorted(NPZ.glob("*.npz")):
        d = np.load(f, mmap_mode="r")
        side = json.loads(f.with_suffix(".json").read_text())
        am = np.asarray(d["attention_mask"]).ravel()
        keep = np.nonzero(am == 1)[0][::STRIDE]
        H.append(np.asarray(np.asarray(d["hidden_states"][:, LAYER, :])[keep], np.float64))
        toks = side["tokens"]
        n = len(toks)
        tgt["step_frac"].append(np.arange(n)[::STRIDE] / max((n - 1) // STRIDE, 1))
        tgt["op_mass"].append(_col(f, "op_mass"))
        tgt["newline_mass"].append(_col(f, "newline_mass"))
        tgt["latex_mass"].append(_col(f, "latex_mass"))
        tgt["top1_prob_renorm"].append(_col(f, "top1_prob_renorm"))
        tgt["backtrack_topk"].append(_col(f, "backtrack_topk"))
    return H, tgt


_COL_CACHE = {}


def _col(f, name):
    """从 obs_series.npz 取列（stride=1），再按同一步长抽步。"""
    key = "obs_series"
    if key not in _COL_CACHE:
        z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
        names = [str(x) for x in z["names"]]
        per = [[] for _ in z["traj_T"]]
        for i, t in enumerate(z["traj_id"]):
            per[t].append(z["obs"][i])
        _COL_CACHE[key] = ({n: [np.array(p)[:, j] for p in per]
                            for j, n in enumerate(names)})
    files = sorted(NPZ.glob("*.npz"))
    i = files.index(f)
    return _COL_CACHE[key][name][i][::STRIDE]


def loo_fit(Xs, Ys, lam_rel):
    xm = np.mean([x.mean(0) for x in Xs], 0)
    ym = np.mean([y.mean(0) for y in Ys], 0)
    Gs = [(x - xm).T @ (x - xm) for x in Xs]
    Bs = [(x - xm).T @ (y - ym) for x, y in zip(Xs, Ys)]
    G, B = sum(Gs), sum(Bs)
    ws, pf, tg = [], [], []
    for i in range(len(Xs)):
        Gi, Bi = G - Gs[i], B - Bs[i]
        w = np.linalg.solve(Gi + lam_rel * np.trace(Gi) / Gi.shape[0] * np.eye(len(Gi)), Bi)[:, 0]
        ws.append(w)
        pf.append((Xs[i] - xm) @ w)
        tg.append(Ys[i] - ym)
    p, t = np.concatenate(pf), np.concatenate(tg)
    rho = float(((p - p.mean()) * (t - t.mean())).mean() / (p.std() * t.std()))
    return np.array(ws), rho, p, t


def main():
    ref = json.loads(SRC.read_text())
    out = {"purpose": "独立复核，不 import completeness.py", "checks": {}}
    H, tgt = load()
    n_traj = len(H)

    # PCA（与被复核脚本同一口径：逐轨迹均值的均值做中心，trace 归一）
    xm = np.mean([h.mean(0) for h in H], 0)
    C = np.zeros((2048, 2048))
    for h in H:
        hc = h - xm
        C += hc.T @ hc
    C /= np.trace(C)
    ev, evec = np.linalg.eigh(C)
    P = evec[:, np.argsort(ev)[::-1][:K]]

    axes = []
    for a in AX:
        v = np.load(VEC / f"{a}.npy").astype(np.float64).ravel()
        axes.append(v / np.linalg.norm(v))
    S = np.array(axes)
    sv = np.linalg.svd(S, compute_uv=False)

    # ---- V1
    out["checks"]["V1_condition_number_of_S"] = {
        "recomputed_cond_S": float(sv[0] / sv[-1]),
        "json_cond_S": ref["named_span_S"]["condition_number_S"],
        "json_singular_values": ref["named_span_S"]["singular_values"],
        "recomputed_singular_values": sv.tolist(),
    }

    Xp = [(h - xm) @ P for h in H]
    A = [h @ S.T - xm @ S.T for h in H]          # 每条命名轴的逐轨迹中心化投影

    def gram(rows):
        Q = np.zeros_like(rows)
        for j in range(len(rows)):
            v = rows[j].copy()
            for i in range(j):
                v -= (Q[i] @ v) * Q[i]
            Q[j] = v / np.linalg.norm(v)
        return Q

    Q = gram(S)

    def analyse(name):
        Ys = [(v - v.mean())[:, None] for v in tgt[name]]
        Xs = [Xp[i] for i in range(n_traj)]
        ws, rho_full, PF, TR = loo_fit(Xs, Ys, LAM)
        Df = ws @ P.T
        coef = Df @ Q.T
        PR = np.concatenate([Xp[i] @ ws[i] - A[i] @ coef[i] for i in range(n_traj)])
        rho_res = float(((PR - PR.mean()) * (TR - TR.mean())).mean() / (PR.std() * TR.std()))
        wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
        cos = {a.replace("_up", "").replace("_deep", "_deep"): float(np.median(np.abs(wn @ S[j])))
               for j, a in enumerate(AX)}
        return {"rho_full": rho_full, "rho_res": rho_res,
                "S_share": 1 - rho_res ** 2 / rho_full ** 2 if rho_full else None,
                "cos_to_axes": cos}

    # ---- V2 / V3
    for nm, tag in [("step_frac", "V2_positive_control"),
                    ("op_mass", "V3_not_covered"),
                    ("newline_mass", "V3_not_covered"),
                    ("latex_mass", "V3_not_covered")]:
        r = analyse(nm)
        out["checks"][f"{tag}:{nm}"] = {
            "recomputed": r,
            "json_rho_full": ref["readout"][f"{nm}|delta0"]["oof_pearson_full"],
            "json_rho_res": ref["readout"][f"{nm}|delta0"]["oof_pearson_residual_outside_S"],
            "json_S_share": ref["readout"][f"{nm}|delta0"]["pearson2_share_explained_by_S"],
        }

    # ---- V4 装置复现
    out["checks"]["V4_cos"] = {}
    for nm, axis_name, key in [("top1_prob_renorm", "confidence_up", "confidence"),
                               ("backtrack_topk", "caution", "caution"),
                               ("step_frac", "reasoning_deep", "reasoning_deep")]:
        r = analyse(nm)
        out["checks"]["V4_cos"][f"{nm}->{axis_name}"] = {
            "recomputed_cos": r["cos_to_axes"][axis_name],
            "json_cos": ref["apparatus_repro"]["rows"][key]["observed_cos"]
            if key in ref["apparatus_repro"]["rows"] else
            ref["apparatus_repro"]["step_frac_ruler"]["delta0"]["observed_cos"],
        }

    # ---- 汇总判据
    worst = 0.0
    for k, v in out["checks"].items():
        if k == "V1_condition_number_of_S":
            worst = max(worst, abs(v["recomputed_cond_S"] - v["json_cond_S"]))
        elif isinstance(v, dict) and "recomputed" in v:
            for a, b in [("rho_full", "json_rho_full"), ("rho_res", "json_rho_res")]:
                worst = max(worst, abs(v["recomputed"][a] - v[b]))
        elif isinstance(v, dict) and "recomputed_cos" in v:
            worst = max(worst, abs(v["recomputed_cos"] - v["json_cos"]))
    out["max_abs_deviation_vs_json"] = worst
    out["tolerance"] = 1e-6
    out["pass"] = bool(worst <= 1e-6)
    pos = out["checks"]["V2_positive_control:step_frac"]["recomputed"]["S_share"]
    neg = [out["checks"][f"V3_not_covered:{n}"]["recomputed"]["S_share"]
           for n in ("op_mass", "newline_mass", "latex_mass")]
    out["ruler_discrimination"] = {
        "S_share_when_S_covers_the_direction_step_frac": pos,
        "S_share_when_S_does_not_cover": neg,
        "separation_ratio": float(pos / max(neg)),
        "verdict": ("同一把尺子：覆盖时给 %.3f、不覆盖时给 %.3f（相差 %.0f 倍）"
                    "⇒ 尺子本身有分辨力" % (pos, max(neg), pos / max(neg))),
    }
    (ROOT / ".cache/completeness/verify_independent.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print(f"max |Δ| vs completeness.json = {worst:.3e}  pass={out['pass']}")
    print(out["ruler_discrimination"]["verdict"])
    print("  step_frac S_share =", round(pos, 4),
          " op/newline/latex S_share =", [round(x, 4) for x in neg])
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
