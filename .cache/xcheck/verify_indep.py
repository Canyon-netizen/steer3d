"""独立复算 #2：严格照 compute_steering_vectors.py 的逐轨迹语义。

上一版我按**全局**百分位算，n_pos=18930、cos=0.9729，与线上向量对不上。
读了源码第 175-190 行后发现百分位是**逐轨迹**的（np.percentile(gen_e, 30)），
且 len(gen_h) < 20 的轨迹要跳过。这才是线上向量的真实定义。

本脚本验三件事，全部只从 48 个 npz 重算，不用子智能体的中间文件：
  1. 样本数是否等于 steering_vectors.json 里的 n_positive / n_negative
  2. cos(线上 .npy, 我重算的 L14) 是否 ≈ 1
  3. cos(v_L13, v_L14)
第 1、2 条不过，第 3 条就没有意义。
"""
import glob
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
NPZ = sorted(glob.glob(str(ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime/*.npz")))
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE,
)
L13, L14 = 13, 14


def cos(a, b):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


trajs, s13, s14, any_flag = [], 0.0, 0.0, False
for p in NPZ:
    d = np.load(p, allow_pickle=True)
    hs = d["hidden_states"]
    meta = json.loads(Path(p).with_suffix(".json").read_text())
    toks = meta.get("tokens", [])
    if len(toks) != hs.shape[0]:
        continue
    n_p = int(meta.get("n_prompt_tokens", 0) or 0)
    flags = [bool(t.get("is_self_check", False)) for t in toks]
    if any(flags):
        any_flag = True
    trajs.append(
        {
            "hidden": np.asarray(hs[:, L14, :], dtype=np.float32),
            "entropy": np.array([t["entropy"] for t in toks], dtype=np.float32),
            "is_self_check": flags,
            "token_text": [t["token"] for t in toks],
            "n_prompt": n_p,
        }
    )
    g13 = np.asarray(hs[:, L13, :], dtype=np.float32)[n_p:]
    s13 += float(np.linalg.norm(g13, axis=1).sum())
    s14 += float(np.linalg.norm(np.asarray(hs[:, L14, :], np.float32)[n_p:], axis=1).sum())

# 全局回退（load_trajectories 第 107-110 行）：整批标志全 False 才按文本重算
if not any_flag:
    for t in trajs:
        t["is_self_check"] = [bool(SELF_CHECK_RE.search(s)) for s in t["token_text"]]

n_steps = sum(len(t["hidden"]) - t["n_prompt"] for t in trajs)


def pool_confidence(trajs, layer_key="hidden"):
    lo, hi = [], []
    for t in trajs:
        h, e, n_p = t[layer_key], t["entropy"], t["n_prompt"]
        gen_h, gen_e = h[n_p:], e[n_p:]
        if len(gen_h) < 20:
            continue
        q1, q3 = np.percentile(gen_e, 30), np.percentile(gen_e, 75)
        lo.append(gen_h[gen_e <= q1])
        hi.append(gen_h[gen_e >= q3])
    return np.concatenate(lo), np.concatenate(hi)


def pool_self_check(trajs):
    sc, reg = [], []
    for t in trajs:
        h, flags, n_p = t["hidden"], t["is_self_check"], t["n_prompt"]
        for i, f in enumerate(flags):
            if i < n_p:
                continue
            (sc if f else reg).append(h[i])
    return (np.stack(sc), np.stack(reg)) if len(sc) >= 20 and len(reg) >= 100 else (None, None)


def dom(pos, neg):
    v = pos.mean(0) - neg.mean(0)
    return v / np.linalg.norm(v)


meta = json.loads(
    (ROOT / "backend/examples/output/steering_vectors/steering_vectors.json").read_text()
)
print("=" * 72)
print("载入 %d 条轨迹 / 生成步合计 %d" % (len(trajs), n_steps))
m13, m14 = s13 / n_steps, s14 / n_steps
print("mean‖h‖  L13=%.6f  L14=%.6f  R=%.6f" % (m13, m14, m14 / m13))
print("  对照：子智能体 139.377/164.421/1.1797；我上一版 138.043/163.193/1.1822")

vdir = ROOT / "backend/examples/output/steering_vectors"
rows = []
for name, builder in [("confidence_up", "conf"), ("caution", "sc")]:
    lo, hi = pool_confidence(trajs) if builder == "conf" else pool_self_check(trajs)
    v14 = dom(lo, hi)
    pub = np.load(vdir / f"{name}.npy").astype(np.float64).ravel()
    pub = pub / np.linalg.norm(pub)
    m = meta[name]
    rows.append(
        (name, len(lo), m["n_positive"], len(hi), m["n_negative"], cos(pub, v14))
    )
    print()
    print("2) %s" % name)
    print("   n_positive  重算 %6d  线上记 %6d  %s" % (len(lo), m["n_positive"],
          "OK" if len(lo) == m["n_positive"] else "不一致"))
    print("   n_negative  重算 %6d  线上记 %6d  %s" % (len(hi), m["n_negative"],
          "OK" if len(hi) == m["n_negative"] else "不一致"))
    print("   cos(线上 .npy, 我的 L14) = %.12f" % cos(pub, v14))
    globals()["v14_" + name] = v14

# L13 重算
t13 = []
for p, t in zip(NPZ, trajs):
    d = np.load(p, allow_pickle=True)
    t13.append(np.asarray(d["hidden_states"][:, L13, :], dtype=np.float32))
for i, t in enumerate(t13):
    pass
# 需要逐轨迹对齐：重新按同样顺序载入 L13
L13s = []
for p in NPZ:
    d = np.load(p, allow_pickle=True)
    hs = d["hidden_states"]
    meta_s = json.loads(Path(p).with_suffix(".json").read_text())
    toks = meta_s.get("tokens", [])
    if len(toks) != hs.shape[0]:
        continue
    L13s.append(np.asarray(hs[:, L13, :], dtype=np.float32))
assert len(L13s) == len(trajs)
trajs13 = [dict(t, hidden=h) for t, h in zip(trajs, L13s)]

lo, hi = pool_confidence(trajs13)
v13_conf = dom(lo, hi)
lo, hi = pool_self_check(trajs13)
v13_caut = dom(lo, hi)

print()
print("3) 跨一层的向量余弦 cos(v_L13, v_L14)")
print("   confidence_up = %.10f" % cos(v13_conf, v14_confidence_up))
print("   caution       = %.10f" % cos(v13_caut, v14_caution))
print("   子智能体报 0.9551222208 / 0.9420589099")
print("=" * 72)
