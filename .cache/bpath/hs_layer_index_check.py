"""钉死一件事：npz 里的第 k 层到底对应 HF 的 hs[k] 还是 hs[k+1]。

## 为什么必须钉

`collect_qwen3_aime.py:198-203` 的代码是

    for li in range(1, len(hs)):
        v = hs[li][0, -1, :]
        layer_vecs.append(v32)

即 npz 的第 `k` 层 = `hs[k+1]` = **block k 的输出** = **block k+1 的输入**。

而注入是 `blk = model.model.layers[LAYER]` 上的 forward **pre**-hook
（`r6_rerun.py:212,222`），动的是 **block LAYER 的输入** = `hs[LAYER]`
= **npz 第 LAYER-1 层**。

`load_xy` 取的是 `z["hidden_states"][:, LAYER, :]` = **npz 第 LAYER 层**。

⇒ 若上述代码为真，`w` 是在**注入点下一层**的激活上训的。
这与修订 7 修掉的「一个 token」是同一族错误，只是错在**层**这个轴上。

## 两条判据（都不加载 1.7B 模型，只切片读 safetensors）

**J1（逐位相等，最硬）**：`last_hidden` 就是最后一层残差 `hs[28]`。
若它与 `hidden_states[:, 27]` 逐位相同 ⇒ npz 第 27 层 = hs[28]
⇒ 映射 `npz[k] = hs[k+1]` 成立。
（npz 存的是 float16，逐位相等是可直接判的，没有数值容差问题。）

**J2（重建 logit，独立验证）**：生成是贪心的，真实 token 必在 top-64 里。
对每个 t，取 `topk_indices[t][0]` 与 `topk_logits[t][0]`，验

    topk_logits[t][0] == RMSNorm(last_hidden[t]) @ (lm_head.weight * norm.weight)[gen[t]]

这同时验了后面注入层扫描要用的 `W_eff = lm_head.weight * norm.weight`。
再用全部 64 个 top-k 误差做统计，报最大误差。
"""
import sys
import zipfile
from pathlib import Path

import numpy as np

npz_path = Path(sys.argv[1])
model_dir = Path(sys.argv[2])
T_PROBE = int(sys.argv[3]) if len(sys.argv) > 3 else 8   # 抽多少个 token 验


def read_header(fh):
    """numpy 2.x 删了 format._read_array_header，只能按版本分派。"""
    ver = np.lib.format.read_magic(fh)
    rd = {  (1, 0): np.lib.format.read_array_header_1_0,
           (2, 0): np.lib.format.read_array_header_2_0}[tuple(ver)]
    shape, _, dtype = rd(fh)
    return shape, dtype


print(f"npz: {npz_path.name}")
with zipfile.ZipFile(npz_path) as zf:
    keys = [k[:-4] if k.endswith(".npy") else k for k in zf.namelist()]
    print("条目:", keys)
    for raw in zf.namelist():
        with zf.open(raw) as fh:
            shape, dtype = read_header(fh)
        print(f"  {raw:26s} shape={shape} dtype={dtype}")

with np.load(npz_path) as z:
    hs = z["hidden_states"]          # (T, 28, D) float16
    last = z["last_hidden"]          # (T, D)
    gen = z["token_ids"]
    topk_i = z["topk_indices"]       # (T, 64)
    topk_l = z["topk_logits"]        # (T, 64)
T, L, D = hs.shape
print(f"\nhidden_states (T={T}, L={L}, D={D})  —— L={L}，"
      f"Qwen3-1.7B 有 28 个 block，HF 的 hidden_states 长度应为 29")

# ---------------- J1：last_hidden 逐位等于第几层 ----------------
print("\n" + "=" * 70)
print("J1  last_hidden 与 hidden_states 各层的逐位相等情况")
print("=" * 70)
hits = []
for k in range(L):
    same = np.array_equal(last, hs[:, k, :])
    if same:
        hits.append(k)
    md = float(np.abs(last.astype(np.float64) - hs[:, k, :].astype(np.float64)).max())
    print(f"  层 {k:2d}: 逐位相同={str(same):5s}  最大绝对差={md:.6g}")
if hits:
    print(f"\n⇒ **npz 第 {hits} 层 == last_hidden == hs[{hits[0]+1}]**")
    print("⇒ 映射 `npz[k] = hs[k+1]`（丢弃了 embedding 那层）**成立**")
else:
    print("\n⇒ last_hidden 与任何一层都不逐位相同。")
    print("   可能它存的是最后一层 **之前** 的值，或经过了额外处理 —— "
          "**不要**据此改 load_xy，先查采集端。")

# ---------------- J2：用 top-64 重建 logit ----------------
print("\n" + "=" * 70)
print("J2  RMSNorm(last_hidden) @ (lm_head * norm.weight) 与 topk_logits 对不对得上")
print("=" * 70)
from safetensors import safe_open
import torch

lm_w = nm_w = None
for c in sorted(model_dir.glob("*.safetensors")):
    # 必须用 framework="pt"：numpy 后端读不了 bfloat16（TypeError）
    with safe_open(str(c), framework="pt") as f:
        for k in list(f.keys()):
            if k.endswith("lm_head.weight"):
                lm_w = f.get_tensor(k).to(torch.float32).numpy()
            elif k.endswith("model.norm.weight"):
                nm_w = f.get_tensor(k).to(torch.float32).numpy()
    if lm_w is not None and nm_w is not None:
        print(f"  在 {c.name} 里找到 lm_head.weight {lm_w.shape} 与 model.norm.weight {nm_w.shape}")
        break
if lm_w is None or nm_w is None:
    print("**没找到权重**（可能是 tied embedding，只有 embed_tokens 没有 lm_head）")
    sys.exit(2)

W_eff = (lm_w.astype(np.float64) * nm_w.astype(np.float64)[None, :])  # (V, D)
eps = 1e-6
errs = []
for t in range(0, T, max(1, T // T_PROBE)):
    x = last[t].astype(np.float64)
    x = x / np.sqrt((x ** 2).mean() + eps) * nm_w.astype(np.float64)
    pred = W_eff[topk_i[t]] @ x            # (64,2048)@(2048,) -> (64,)
    errs.append(np.abs(pred - topk_l[t].astype(np.float64)))
errs = np.concatenate(errs)
print(f"  抽 {len(errs)} 个 (token, logit) 对："
      f"最大误差 {errs.max():.4f}  中位 {np.median(errs):.4f}  90分位 {np.percentile(errs,90):.4f}")
t0 = 0
x = last[t0].astype(np.float64)
x = x / np.sqrt((x ** 2).mean() + eps) * nm_w.astype(np.float64)
print(f"  样例 t={t0}：存储 {topk_l[t0][0]:.4f}  重建 "
      f"{float(x @ W_eff[topk_i[t0][0]]):.4f}   真实 token {gen[t0]} 在 top1? "
      f"{bool(topk_i[t0][0] == gen[t0])}")
if errs.max() < 0.5:
    print("⇒ J2 通过：`W_eff = lm_head.weight * norm.weight` 与 RMSNorm 口径正确，"
          "注入层扫描里的一阶预测公式可用。")
else:
    print("⇒ J2 不通过：口径还没对上，**先修这里**，注入层扫描的预测值不可信。")
