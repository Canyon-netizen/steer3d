"""决定性一步：这 4 条「轴外方向」是真的，还是我构造的观测量的副产品？

Q1/Q2/Q3 已经给出：四个字符组成类 w* 彼此近乎正交（0.02–0.46），
所以缺口**不是**一条轴，是 4 条。这一支做两件决定性的事：

  1. **专属性矩阵** M[A][B] = 用 A 的留一折权重去预测观测量 B 的样本外 Pearson。
     判据：对角线必须显著大于非对角线。如果 w*(digit_mass) 同样能预测
     newline_mass，那这 4 条就不是 4 条而是一条。
  2. **地板**：语义无关的假观测量（把 B 在轨迹内随机打乱，保留边缘分布）
     能被 w*(A) 预测到什么程度。判据：对角线必须显著高于这个地板。

     这一条是必须的 —— 上一轮我用「非循环 + 专属」推翻了 caution 的归属，
     同一套检验必须用在这批新方向上，否则就是双标。
"""
import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
CACHE = ROOT / ".cache/xcheck/dir_cache"
OUT = ROOT / ".cache/xcheck/specificity_matrix.json"
SEED = 20261003

man = json.loads((CACHE / "manifest.json").read_text())
AXES = np.load(CACHE / "axes.npy")
AX_NAMES = man["axes"]
DEFINITIONAL = {"entropy", "in_think", "self_check_regex", "step_frac"}
CHAR = ["digit_mass", "op_mass", "newline_mass", "latex_mass"]
NONDEF = [t for t in man["targets"] if t not in DEFINITIONAL]


def load_ragged(name):
    flat = np.load(CACHE / f"{name}_flat.npy")
    off = np.load(CACHE / f"{name}_off.npy")
    return [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]


Xp = load_ragged("Xp0")
W = {t: np.load(CACHE / f"w_{t}.npy") for t in man["targets"]}
KEEP = {t: man[f"meta_{t}"]["keep"] for t in man["targets"]}

# ---- 目标：10 个非定义式 + 4 个定义式/尺子 ----
z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
names = [str(x) for x in z["names"]]
obs = z["obs"].astype(np.float64)
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]
usable = {names[j]: [p[::2, j] for p in series] for j in range(len(names))}

import re
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)
side = [json.loads(p.with_suffix(".json").read_text())["tokens"]
        for p in sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))]
control = {
    "entropy": [np.array([t["entropy"] for t in tk], np.float64)[::2] for tk in side],
    "in_think": [np.array([bool(t["is_in_think_block"]) for t in tk], np.float64)[::2]
                 for tk in side],
    "self_check_regex": [np.array([bool(SELF_CHECK_RE.search(t["token"] or "")) for t in tk],
                                  np.float64)[::2] for tk in side],
    "step_frac": [np.arange(len(tk), dtype=np.float64)[::2] /
                  max((len(tk) - 1) // 2, 1) for tk in side],
}
TARGET = {**usable, **control}


def centered(v):
    return v - v.mean()


def oof(weights_src, target_name, fake=None):
    """用 weights_src 那一格的留一折权重，预测 target_name（逐轨迹去均值）。
    fake 非 None 时用假观测量代替目标。"""
    src = TARGET[target_name] if fake is None else fake
    keep = KEEP[weights_src]
    preds, tgts = [], []
    for k, i in enumerate(keep):
        y = src[i][: len(Xp[i])]
        if len(y) == 0:
            continue
        preds.append(Xp[i] @ W[weights_src][k])
        tgts.append(centered(y))
    p, t = np.concatenate(preds), np.concatenate(tgts)
    den = p.std() * t.std()
    if den == 0 or not np.isfinite(den):
        return float("nan")
    return float(((p - p.mean()) * (t - t.mean())).mean() / den)


rng = np.random.default_rng(SEED)
FAKE = {}
for t in NONDEF:
    FAKE[t] = []
    for v in TARGET[t]:
        f = v.copy()
        rng.shuffle(f)          # 轨迹内打乱：破坏逐步对应，保留边缘分布
        FAKE[t].append(f)

rows = list(NONDEF)
print("专属性矩阵 M[用谁的 w*][预测谁]  —— 样本外 Pearson，Δ=0，轨迹内去均值")
print()
hdr = "%-15s" % "w* \\ 目标" + "".join("%12s" % t[:10] for t in rows)
print(hdr)
print("-" * len(hdr))
M = {}
for a in rows:
    vals = {b: oof(a, b) for b in rows}
    M[a] = vals
    best = max(vals, key=lambda k: vals[k])
    mark = " ←" if best != a else " ←对角"
    print("%-15s" % a + "".join("%12.4f" % vals[b] for b in rows) + mark)

print()
print("地板（轨迹内打乱目标后，同一个 w* 还能预测多少）")
print("%-15s" % "w* \\ 目标" + "".join("%12s" % t[:10] for t in CHAR))
F = {}
for a in CHAR:
    F[a] = {b: oof(a, b, fake=FAKE[b]) for b in CHAR}
    print("%-15s" % a + "".join("%12.4f" % F[a][b] for b in CHAR))

print()
print("四个字符方向的「对角 vs 地板」倍数，以及它对 4 条命名轴的余弦：")
P = np.load(CACHE / "P.npy")
axes_k = {}
for k, name in enumerate(AX_NAMES):
    v = P.T @ AXES[k]
    axes_k[name] = v / np.linalg.norm(v)
char_axis = {}
for t in CHAR:
    diag, fl = M[t][t], F[t][t]
    u = W[t] / np.linalg.norm(W[t], axis=1, keepdims=True)
    char_axis[t] = {n: float(np.median(np.abs(u @ axes_k[n]))) for n in AX_NAMES}
    off = max(abs(v) for b, v in M[t].items() if b != t)
    print("   %-13s 对角 %.4f  地板 %.4f（%5.0f×）  非对角最大 %.4f（%4.1f× 余量）  命名轴 %s" % (
        t, diag, fl, diag / fl if fl else float("nan"), off, diag / off if off else float("nan"),
        "  ".join("%s %.3f" % (n[:4], c) for n, c in char_axis[t].items())))

# 阳性对照：这套判据必须能测出位置轴，否则上面整张表都只是噪声
rev_ramp = [-v for v in TARGET["step_frac"]]
print()
print("阳性对照（装置必须能测出位置轴）：")
print("   step_frac 用 step_frac 的 w* 预测        = %.4f" % oof("step_frac", "step_frac"))
print("   1 − step_frac（语义相反的斜坡，同一个 w*） = %.4f" % oof("step_frac", "step_frac", fake=rev_ramp))

OUT.write_text(json.dumps({
    "seed": SEED, "note": "M[A][B]: 用 A 的留一折权重预测 B，Δ=0，轨迹内去均值",
    "specificity_matrix": M, "fake_floor_char4x4": F,
    "char_summary": {t: {"diagonal": M[t][t], "floor": F[t][t],
                          "ratio": (M[t][t] / F[t][t]) if F[t][t] else None}
                     for t in CHAR},
}, ensure_ascii=False, indent=1))
print()
print("已写", OUT)
