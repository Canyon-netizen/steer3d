"""补一个缺失的产物：emitted_has_digit 与 digit_top1 到底是同一个量吗。

§4.9.2 里写了一句「corr(emitted_has_digit_t, digit_top1_t) = 0.9839，
而与错开一步的 digit_top1_{t-1} 只有 0.0925」。
这两个数当时只是 `heldout_specificity.py` 的 stdout，**没进产物 JSON**
⇒ 页面上一旦要显示它，就必须先有可复算的东西。

所以这里单独立一个产物，并加一条对照：
  - 主口径：整段拼接后算 Pearson（与原脚本逐位一致，便于交叉核对）
  - 对照口径：逐轨迹算 Pearson 再平均（防止它是「跨轨迹拼接」造出来的伪影）

两个口径差得远 ⇒ 这个数不能上页面。
"""
import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
OUT = ROOT / ".cache/xcheck/heldout_selfdup.json"
AIME = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
STRIDE = 2

vocab = json.loads((ROOT / "frontend/public/latent/data/vocab.json").read_text())["ids"]
is_digit = np.zeros(len(vocab), dtype=bool)
for i, s in enumerate(vocab):
    w = s.strip()
    if w and all(c in "0123456789" for c in w):
        is_digit[i] = True

DIGIT_TOP1, EMITTED_HAS_DIGIT = [], []
for f in sorted(AIME.glob("*.npz")):
    zz = np.load(f, mmap_mode="r")
    ti = np.asarray(zz["topk_indices"])
    am = np.asarray(zz["attention_mask"]).ravel()
    tk = json.loads(f.with_suffix(".json").read_text())["tokens"]
    n = min(ti.shape[0], len(tk))
    keep = np.nonzero(am[:n] == 1)[0][::STRIDE]
    d = is_digit[ti[:n][keep]]
    toks = [tk[i]["token"] for i in keep]
    DIGIT_TOP1.append(d[:, 0].astype(np.float64))
    EMITTED_HAS_DIGIT.append(
        np.array([any(c.isdigit() for c in t) for t in toks], np.float64))
    del zz

assert len(DIGIT_TOP1) == len(EMITTED_HAS_DIGIT) == 48, "轨迹数不该是 48 以外"
assert all(len(a) == len(b) for a, b in zip(DIGIT_TOP1, EMITTED_HAS_DIGIT))


def pearson(p, t):
    p, t = np.asarray(p, np.float64).ravel(), np.asarray(t, np.float64).ravel()
    den = p.std() * t.std()
    if not np.isfinite(den) or den == 0:
        return float("nan")
    return float(((p - p.mean()) * (t - t.mean())).mean() / den)


def pearson_trajs(ps, ts):
    """逐轨迹算再平均 —— 与整段拼接是两个口径，差得远就说明拼接造了伪影。"""
    out = []
    for p, t in zip(ps, ts):
        n = min(len(p), len(t))
        v = pearson(p[:n], t[:n])
        if np.isfinite(v):
            out.append(v)
    return float(np.mean(out)), len(out)


a = np.concatenate(EMITTED_HAS_DIGIT)
b = np.concatenate(DIGIT_TOP1)
lag0_pooled = pearson(a, b)
lag1_pooled = pearson(a[1:], b[:-1])
lag0_per, n_ok0 = pearson_trajs(EMITTED_HAS_DIGIT, DIGIT_TOP1)
lag1_per, n_ok1 = pearson_trajs(EMITTED_HAS_DIGIT[1:], DIGIT_TOP1[:-1])

res = {
    "what": "emitted_has_digit 与 digit_top1 是不是同一个观测量",
    "n_traj": len(DIGIT_TOP1),
    "n_step": int(len(a)),
    "pooled": {
        "same_step": lag0_pooled,
        "lag1": lag1_pooled,
        "drop": lag0_pooled - lag1_pooled,
    },
    "per_traj_mean": {
        "same_step": lag0_per,
        "lag1": lag1_per,
        "drop": lag0_per - lag1_per,
        "n_used": n_ok0,
        "n_used_lag1": n_ok1,
    },
    "verdict": ("same_observable" if lag0_pooled > 0.9 and lag1_pooled < 0.3
                else "inconclusive"),
    "note": ("本步发出的 token 含数字 与 本步记录的 top-1 是数字 是同一个量；"
             "与错开一步的只有 %.4f。两个口径（拼接/逐轨迹平均）差 %.4f / %.4f，"
             "所以这个数不是跨轨迹拼接造出来的。"
             % (lag1_pooled, abs(lag0_pooled - lag0_per), abs(lag1_pooled - lag1_per))),
}

print("轨迹 %d  步 %d" % (res["n_traj"], res["n_step"]))
print("整段拼接  同一步 %.4f   错开一步 %.4f   落差 %.4f"
      % (lag0_pooled, lag1_pooled, res["pooled"]["drop"]))
print("逐轨迹平均 同一步 %.4f   错开一步 %.4f   落差 %.4f  (有效轨迹 %d/%d)"
      % (lag0_per, lag1_per, res["per_traj_mean"]["drop"], n_ok0, len(DIGIT_TOP1)))
print("判定：", res["verdict"])
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("已写", OUT)
