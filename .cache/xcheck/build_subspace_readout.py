"""把 §4.8 / §4.8.3 / §4.8.6 的结果压成页面数据 readable_subspace.json。

三份产物都是本轮自己跑出来的，��里只做搬运与排版，不重新计算：
  .cache/xcheck/missing_dirs.json        12 维下界、4 条方向两两余弦、贪心明细
  .cache/xcheck/specificity_matrix.json  M[A][B] 专属性矩阵 + 打乱地板
  .cache/xcheck/token_locality.json      Δ=0/1/20/100 的重新拟合读出

判据要读的是**页面印出来的数字**与这份文件一致，所以字段名要稳定。
"""
import json
import warnings
from pathlib import Path

import numpy as np

# 本机 numpy 2.0 的 matmul 会发 divide-by-zero / overflow / invalid 假告警
# （FAILED_OBS_FORENSICS §10 已验证与 float64 逐位相同，数据无 inf/nan）
warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
X = ROOT / ".cache/xcheck"
CACHE = X / "dir_cache"
DST = ROOT / "frontend/public/latent/data/readable_subspace.json"

miss = json.loads((X / "missing_dirs.json").read_text())
spec = json.loads((X / "specificity_matrix.json").read_text())
loc = json.loads((X / "token_locality.json").read_text())
comp = json.loads((ROOT / ".cache/completeness/completeness.json").read_text())

CHAR = ["digit_mass", "op_mass", "newline_mass", "latex_mass"]
LABEL = {
    "digit_mass": "数字",
    "op_mass": "运算符",
    "newline_mass": "换行",
    "latex_mass": "排版结构",
}
MEANING = "top-64 候选质量落在该类 token 上的占比"
AX_NAME = {"confidence": "confidence", "caution": "caution",
           "creativity": "creativity", "reasoning_deep": "reasoning_deep"}

# 每条方向对 4 条命名轴的余弦（analyze_missing.py 当时只打印了，没落盘）
P = np.load(CACHE / "P.npy")
AXES = np.load(CACHE / "axes.npy")
axes_k = {}
for k, n in enumerate(AX_NAME):
    v = P.T @ AXES[k]
    axes_k[n] = v / np.linalg.norm(v)


def cos_to_named(key):
    u = np.load(CACHE / f"w_{key}.npy")
    u = u / np.linalg.norm(u, axis=1, keepdims=True)
    return {n: round(float(np.median(np.abs(u @ axes_k[n]))), 4) for n in AX_NAME}


M = spec["specificity_matrix"]
F = spec["fake_floor_char4x4"]
null20 = comp["direction_search"]["delta20"]["per_target"]

rows = []
for t in CHAR:
    d = loc["results"][t]
    row = {b: v for b, v in M[t].items() if b != t}
    worst = max(row, key=lambda k: abs(row[k]))
    n20 = null20[t]["null_p99_random"] if t in null20 else None
    rows.append({
        "key": t,
        "label": LABEL[t],
        "meaning": MEANING,
        "diagnostic": {
            "diagonal": round(M[t][t], 4),
            "floor": round(F[t][t], 4),
            "offdiag_worst": round(abs(row[worst]), 4),
            "offdiag_worst_cell": worst,      # 存原始 key，中文标签交给面板映射，保持数据可对账
            "offdiag_worst_label": LABEL.get(worst, worst),
            "margin_over_offdiag": round(M[t][t] / abs(row[worst]), 2) if row[worst] else None,
            "cos_to_named_axes": cos_to_named(t),
            "max_cos_to_named": round(max(cos_to_named(t).values()), 4),
        },
        "delta": {d_: round(d[f"delta{d_}"]["rho"], 4) for d_ in loc["deltas"]},
        "delta20_null_p99": round(n20, 4) if n20 is not None else None,
        "delta20_over_null": round(d["delta20"]["rho"] / n20, 2) if n20 else None,
        "decay_x20": round(d["delta0"]["rho"] / abs(d["delta20"]["rho"]), 1)
        if abs(d["delta20"]["rho"]) > 1e-6 else None,
    })

# 命名轴那一行（confidence / caution 的读出），作为「同一把尺子」上的已发布对照
named = []
for t, axname in [("top1_prob_renorm", "confidence 的读出"),
                  ("backtrack_topk", "caution 的读出")]:
    d = loc["results"][t]
    named.append({
        "key": t, "axis": axname,
        "delta": {d_: round(d[f"delta{d_}"]["rho"], 4) for d_ in loc["deltas"]},
        "decay_x20": round(d["delta0"]["rho"] / abs(d["delta20"]["rho"]), 1),
    })

ctrl = loc["results"]["step_frac"]
PAY = {
    "schema": "steering3d.readable_subspace/1",
    "question": "4 条命名轴之外，残差流里还剩多少解释得了行为的方向？",
    "convention": {
        "layer": 14, "k_pca": miss["recipe"]["K"], "stride": miss["recipe"]["stride"],
        "search_space": "每个观测量在 L14 上用留一轨迹岭回归拟合最优线性读出 w*，"
                        "再在 2048 维原空间里量它与其它观测量 w* 的余弦",
        "floor": "把目标在轨迹内随机打乱（保留边缘分布、破坏逐步对应），"
                 "同一个 w* 还能预测多少 —— 这就是这套判据的噪声水平",
        "note": "全部数字来自本项目自己的脚本，见 .cache/xcheck/。页面只负责显示。",
    },
    "headline": {
        "readable_directions_lower_bound": len(miss["greedy_with_named_axes_sep0p5"]),
        "named_axes": 4,
        "greedy_obs_only": len(miss["greedy_obs_only_sep0p5"]),
        "separation_threshold": 0.5,
        "caution_absorbed": "axis:caution 没有被贪心选中 —— cos(confidence, caution)=0.5537 "
                            "已超过 0.5 门槛，在贪心里被 confidence 吃掉。",
    },
    "surface_directions": rows,
    "named_axis_readouts": named,
    "control": {
        "key": "step_frac", "label": "轨迹位置（装置阳性对照）",
        "delta": {d_: round(ctrl[f"delta{d_}"]["rho"], 4) for d_ in loc["deltas"]},
        "decay_x20": round(ctrl["delta0"]["rho"] / abs(ctrl["delta20"]["rho"]), 1),
        "note": "它在 Δ=100 仍有 0.7087、几乎不衰减 ⇒ 装置有能力测出持续方向，"
                "而它测出的是位置轴。所以下面六条「塌了」不是因为装置测不出。",
    },
    "char_pairwise_abs_cos": {k: round(v, 4) for k, v in miss["char_pairwise_abs_cos"].items()},
    "char_pairwise_note": "两两余弦（逐折配对中位 |cos|）。数字↔换行 0.0195 是"
                          "「缺口不是一条轴」这个结论的唯一依据。",
    "verdict": (
        "缺口不是一条「表面形式」轴，是 4 条互相近乎正交的轴"
        "（digit_mass ↔ newline_mass 只有 0.0195）。"
        "这 4 条全部通过了「非循环（远高于打乱地板）」与"
        "「专属（对 4 条命名轴 cos ≤ 0.258）」两条判据，"
        "并且全部是 token 局部的（Δ=20 塌 6.4×–42.1×，而位置轴对照不塌）。"
    ),
    "not_claimed": (
        "以上全是**可读性**（哪个方向能线性预测哪个观测量），"
        "不是**因果性**（沿它注入会不会改变行为）。后者要占 GPU 做干预实验，"
        "本轮未做 —— 所以不能说「所以解释向量理论就是这 12 条」。"
    ),
}
DST.write_text(json.dumps(PAY, ensure_ascii=False, indent=1))
print("已写", DST)
print("  可读方向下界 :", PAY["headline"]["readable_directions_lower_bound"],
      "（命名轴 4 条）")
for r in rows:
    print("  %-13s 对角 %.4f  地板 %+.4f  非对角最大 %.4f（%s）  Δ=20 %.4f（%s×）" % (
        r["label"], r["diagnostic"]["diagonal"], r["diagnostic"]["floor"],
        r["diagnostic"]["offdiag_worst"], r["diagnostic"]["offdiag_worst_cell"],
        r["delta"][20], r["decay_x20"]))
print("  对照 step_frac :", PAY["control"]["delta"])
