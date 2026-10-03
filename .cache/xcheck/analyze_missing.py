"""轴外的那批可读方向到底是什么？（纯缓存上的线性代数，几秒跑完）

出发点：完备性检验说 4 条命名轴对「字符组成类」观测量只解释 1.6%–20%。
这里回答三个问题：

  Q1 那 4 个字符观测量（digit/op/newline/latex）的 w* 是不是**同一条**方向？
  Q2 10 个非定义式 w* 加 4 条命名轴，一共构成几条互相近正交的方向？
  Q3 如果存在一条主导的「轴外方向」，它能不能通过我用来推翻 caution 的
     **同一套**检验：非循环（语义无关的假观测量给地板）+ 专属（对四条命名轴
     都更低）+ 够不够补上那 0.016–0.20 的缺口？

口径与 completeness.json / verify_s_share.py 相同；w* 从 .cache/xcheck/dir_cache
读，不重载 npz。注意 m = w @ P.T ⇒ m 落在 span(P) 内，所以任意新方向的
逐 token 投影可以直接用缓存的 pred_ 算，不需要原始隐状态。
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path("/Users/zhourui/code/steer3d")
CACHE = ROOT / ".cache/xcheck/dir_cache"
OUT = ROOT / ".cache/xcheck/missing_dirs.json"

man = json.loads((CACHE / "manifest.json").read_text())
P = np.load(CACHE / "P.npy")
Q = np.load(CACHE / "Q.npy")
AXES = np.load(CACHE / "axes.npy")           # (4, 2048) 行=命名轴
AX_NAMES = man["axes"]
DEFINITIONAL = {"entropy", "in_think", "self_check_regex", "step_frac"}
CHAR = ["digit_mass", "op_mass", "newline_mass", "latex_mass"]


def load_ragged(name):
    flat = np.load(CACHE / f"{name}_flat.npy")
    off = np.load(CACHE / f"{name}_off.npy")
    return [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]


def unit_rows(D):
    return D / np.linalg.norm(D, axis=1, keepdims=True)


def med_cos(D1, D2):
    """逐折**配对**算余弦再取中位数 —— 与 cos_per_axis_median 同一口径。

    ⚠️ 第一版写成 `unit_rows(D1) @ unit_rows(D2).T` 再 median，那是 48×48=2304
    个**跨折**值的中位数，不是配对值 —— 连自余弦都会算出 0.9986。
    正确写法是按折逐元素相乘求和：(48, 2048) 逐行点积。
    """
    u1, u2 = unit_rows(D1), unit_rows(D2)
    assert u1.shape == u2.shape, (u1.shape, u2.shape)
    return float(np.median(np.abs((u1 * u2).sum(axis=1))))


D = {t: np.load(CACHE / f"d_{t}.npy") for t in man["targets"]}
nondef = [t for t in man["targets"] if t not in DEFINITIONAL]

# ---------- Q1：四个字符 w* 是不是同一条 ----------
print("=" * 78)
print("Q1  四个字符组成类 w* 的两两余弦（逐折中位 |cos|）")
print("%-14s %s" % ("", "".join("%14s" % c[:12] for c in CHAR)))
cc = {}
for a in CHAR:
    row = []
    for b in CHAR:
        v = med_cos(D[a], D[b])
        cc[f"{a}|{b}"] = v
        row.append(v)
    print("%-14s %s" % (a, "".join("%14.4f" % v for v in row)))

# ---------- Q2：整体结构 ----------
print()
print("=" * 78)
print("Q2  10 个非定义式 w* 的两两 |cos|（只看 ≥0.5 的对）")
pairs = []
for i, a in enumerate(nondef):
    for b in nondef[i + 1:]:
        v = med_cos(D[a], D[b])
        if v >= 0.5:
            pairs.append((v, a, b))
pairs.sort(reverse=True)
for v, a, b in pairs:
    print("   %-16s %-16s %.4f" % (a, b, v))
if not pairs:
    print("   （没有任何一对 ≥0.5）")


def greedy_count(vectors, sep=0.5):
    """从一组向量里贪心取互相 |cos| < sep 的最大子集。"""
    keys = list(vectors)
    chosen = []
    for k in keys:
        if all(abs(vectors[k] @ vectors[c]) < sep for c in chosen):
            chosen.append(k)
    return chosen


# 用每个目标自己的「折中位方向」当代表向量
rep = {t: np.median(unit_rows(D[t]), axis=0) for t in man["targets"]}
rep = {t: v / np.linalg.norm(v) for t, v in rep.items()}
allv = {**{f"axis:{a}": AXES[i] for i, a in enumerate(AX_NAMES)},
        **{f"obs:{t}": rep[t] for t in nondef}}
g_all = greedy_count(allv, 0.5)
g_obs = greedy_count({f"obs:{t}": rep[t] for t in nondef}, 0.5)
print()
print("   10 个非定义式 w* 自己：贪心取 |cos|<0.5 ⇒ %d 条" % len(g_obs))
print("   加上 4 条命名轴后：          ⇒ %d 条" % len(g_all))
print("   明细：", ", ".join(g_all))

# ---------- Q3：主导的轴外方向 ----------
print()
print("=" * 78)
print("Q3  主导的「字符组成」方向 m_surf")
m = np.mean([rep[t] for t in CHAR], axis=0)
m /= np.linalg.norm(m)
print("   m_surf 对四个字符 w*：", "  ".join("%s %.4f" % (t, abs(m @ rep[t])) for t in CHAR))
print("   m_surf 对四个**非**字符 w*：",
      "  ".join("%s %.4f" % (t, abs(m @ rep[t])) for t in nondef if t not in CHAR))
print()
print("   专属检验（cos 越低越好；必须低于它对自己观测量的对齐）：")
for k, i in enumerate(AX_NAMES):
    print("      对命名轴 %-16s %.4f" % (i, abs(m @ AXES[k])))
print("      对 step_frac（位置轴，最强的假对照） %.4f" % abs(m @ rep["step_frac"]))
print("      对 self_check_regex（caution 的定义式）  %.4f" % abs(m @ rep["self_check_regex"]))
print("      对 entropy（confidence 的定义式）        %.4f" % abs(m @ rep["entropy"]))
print()
print("   占 4 条命名轴张成之外的比例：",
      "%.4f" % (np.linalg.norm(m - (m @ Q.T) @ Q)))

# 折中位口径（每个目标自己一个 w*，与前面同一口径），不用代表向量
print()
print("   折中位口径下，四个字符 w* 各自对 4 条命名轴（应都很低 = 不专属于任何命名轴）：")
for t in CHAR:
    row = "  ".join("%s %.4f" % (i[:4], med_cos(D[t], AXES[k:k + 1] * np.ones((48, 1))))
                    for k, i in enumerate(AX_NAMES))
    print("      %-13s %s" % (t, row))

res = {
    "recipe": {"source": str(CACHE), "K": man["K"], "stride": man["stride"],
               "layer": man["layer"], "lambda": {t: man[f"meta_{t}"]["lambda"]
                                                 for t in man["targets"]}},
    "char_pairwise_abs_cos": cc,
    "obs_pairs_ge_0p5": [{"a": a, "b": b, "cos": v} for v, a, b in pairs],
    "greedy_obs_only_sep0p5": g_obs,
    "greedy_with_named_axes_sep0p5": g_all,
    "m_surf": {
        "cos_to_char": {t: float(abs(m @ rep[t])) for t in CHAR},
        "cos_to_other_obs": {t: float(abs(m @ rep[t])) for t in nondef if t not in CHAR},
        "cos_to_named_axes": {i: float(abs(m @ AXES[k])) for k, i in enumerate(AX_NAMES)},
        "cos_to_definition_targets": {
            t: float(abs(m @ rep[t])) for t in DEFINITIONAL if t in rep},
        "fraction_outside_named_span": float(np.linalg.norm(m - (m @ Q.T) @ Q)),
    },
}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print()
print("已写", OUT)
