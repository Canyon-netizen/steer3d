"""J2 的诊断版：不猜「是哪个公式错了」，把四种组合都试一遍，看哪个复现存储的 logits。

J2 原本假设 `logit = RMSNorm(last_hidden) @ (lm_head.weight * norm.weight)`，
实测中位误差 156、最大 339 —— 口径明显不对。
但**层扫描真正需要的是「在 norm 之后、lm_head 之前注入时，下游是恒等映射」这件事**，
不依赖我事先写对解析式。所以先把这个口径钉出来。

组合：
  A  RMSNorm(h) @ (lm_head * norm)      原始假设
  B  RMSNorm(h) @ lm_head               归一化但不乘 γ
  C  h @ (lm_head * norm)               乘 γ 但不归一化
  D  h @ lm_head                        都不做
另外单独验：E  `lm_head.weight` 与 `embed_tokens.weight` 是否逐位相同
（Qwen3-1.7B 是 tied 的，若两者相同则 B/D 才是对的，γ 已被折进权重）。
"""
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open

npz_path = Path(sys.argv[1])
model_dir = Path(sys.argv[2])
N_T = int(sys.argv[3]) if len(sys.argv) > 3 else 6

with np.load(npz_path) as z:
    last = z["last_hidden"]
    gen = z["token_ids"]
    topk_i = z["topk_indices"]
    topk_l = z["topk_logits"]
T = last.shape[0]
print(f"npz T={T}  last_hidden {last.shape} {last.dtype}  "
      f"||last|| 中位 {np.median(np.linalg.norm(last.astype(np.float64), axis=1)):.3f}")

lm_w = nm_w = emb_w = None
src = {}
for c in sorted(model_dir.glob("*.safetensors")):
    with safe_open(str(c), framework="pt") as f:
        for k in list(f.keys()):
            if k.endswith("lm_head.weight"):
                lm_w = f.get_tensor(k).to(torch.float32).numpy(); src["lm_head"] = c.name
            elif k.endswith("model.norm.weight"):
                nm_w = f.get_tensor(k).to(torch.float32).numpy(); src["norm"] = c.name
            elif k.endswith("embed_tokens.weight"):
                emb_w = f.get_tensor(k).to(torch.float32).numpy(); src["embed"] = c.name
print(f"权重来源: {src}")
print(f"lm_head {None if lm_w is None else lm_w.shape}  "
      f"norm {None if nm_w is None else nm_w.shape}  "
      f"embed {None if emb_w is None else emb_w.shape}")

if lm_w is not None and emb_w is not None:
    same = np.array_equal(lm_w, emb_w)
    md = float(np.abs(lm_w.astype(np.float64) - emb_w.astype(np.float64)).max())
    print(f"E  lm_head 与 embed_tokens 逐位相同 = {same}   最大绝对差 = {md:.6g}")

eps = 1e-6
W_eff = lm_w.astype(np.float64) * nm_w.astype(np.float64)[None, :]   # (V, 2048)
combs = {
    "A RMSNorm(h)@(lm*nm)": lambda x, ids: (W_eff[ids] @ x),
    "B RMSNorm(h)@lm":      lambda x, ids: (lm_w.astype(np.float64)[ids] @ (x / np.sqrt((x ** 2).mean() + eps))),
    "C h@(lm*nm)":          lambda x, ids: (W_eff[ids] @ x),
    "D h@lm":               lambda x, ids: (lm_w.astype(np.float64)[ids] @ x),
}
# A 与 C 只差一个归一化因子，单列才能区分
combs["A RMSNorm(h)@(lm*nm)"] = lambda x, ids: (
    (lm_w.astype(np.float64) * nm_w.astype(np.float64)[None, :])[ids]
    @ ((x / np.sqrt((x ** 2).mean() + eps)) * nm_w.astype(np.float64)))
res = {k: [] for k in combs}
for t in range(0, T, max(1, T // N_T)):
    x = last[t].astype(np.float64)
    ids = topk_i[t]
    for k, fn in combs.items():
        res[k].append(np.abs(fn(x, ids) - topk_l[t].astype(np.float64)))

print(f"\n{'组合':26s} {'最大误差':>12s} {'中位':>12s} {'90分位':>12s}")
best = None
for k, v in combs.items():
    e = np.concatenate(res[k])
    print(f"{k:26s} {e.max():12.4f} {np.median(e):12.4f} {np.percentile(e,90):12.4f}")
    if best is None or np.median(e) < best[1]:
        best = (k, np.median(e))

t0 = 0
x = last[t0].astype(np.float64)
print(f"\n样例 t={t0}：存储 top1 = {topk_l[t0][0]:.4f}（真实 token {gen[t0]}）")
for k, fn in combs.items():
    print(f"  {k:26s} 重建 top1 = {float(fn(x, topk_i[t0])[0]):12.4f}")

print(f"\n⇒ 误差最小的组合是 **{best[0]}**（中位 {best[1]:.4f}）")
if best[1] < 0.5:
    print("⇒ 口径对上了。层扫描的解析预测 `Δlogit = α·(w·W_eff)` 可以用。")
else:
    print("⇒ **四个组合全不对**。可能 topk_logits 不是这条前向的（生成用 vLLM、"
          "hidden 用 HF 两次前向），或者 norm 口径另有约定。")
    print("  层扫描仍可跑：L=-1 的**实测**值本身就是校准点，不依赖解析式。")
