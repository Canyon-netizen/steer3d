"""统计未测 think 轨迹**全量** marker 位点里 `w·ĥ > 0.1` 的占比。

## 它要回答的问题（修订 23 的混淆检查）

修订 23 用「10 条轨迹 × 每条 8 个等距位点」做独立复核，判 G1 不过
（`|ρ|` 0.4177 → 0.1327）。但新批次的高对齐位点占比只有 **2.5%**，
而 p01_think（全量）是 **15.8%**，差 6 倍。

⇒ 两种解释在数据上无法区分：
  (1) p01_think 的效应量远高于典型轨迹；
  (2) **等距分位取 8 个点几乎采不到高对齐位点**，G1 是在
      没有高对齐样本的数据上做的。

本脚本用**纯静态**计算（不解模型、不用 GPU）统计全量占比，
以区分 (1) 与 (2)。

## 只读，不改任何数据

⚠ 坐标系：读 npz 第 `NPZ_LAYER=19` 层（= 注入点 block 20 的输入）。
⚠ `NpzFile.__getitem__` 每次都重新解压整个数组 ⇒ **取一次**再在 numpy 侧切片。
"""
import glob
import json
import os

import numpy as np

MK = {13824, 14190, 6771, 10061, 7196, 88190, 80022}
NPZ = 19
ROOT = "/home/zhourui/steer3d_bpath"
SKIP = {"aime__aime25__p00__think", "aime__aime25__p01__think"}

W = np.load(os.path.join(ROOT, "w_L19_m0.npy")).astype(np.float32)
W = W / (float(np.linalg.norm(W)) + 1e-12)

rows = []
for f in sorted(glob.glob(os.path.join(ROOT, "gen_b2/aime", "*.json"))):
    try:
        j = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    if (j.get("config") or {}).get("mode") != "think":
        continue
    tid = j["trajectory_id"]
    if tid in SKIP:
        continue
    ts = [i for i, t in enumerate(j.get("tokens") or [])
          if t.get("token_id") in MK]
    if not ts:
        continue
    z = np.load(os.path.join(ROOT, "gen_b2/aime", f"{tid}.npz"))
    hs = np.asarray(z["hidden_states"])
    z.close()
    vals = []
    for i in ts:
        h = hs[i - 1, NPZ, :].astype(np.float64)
        vals.append(float(W @ (h / np.linalg.norm(h))))
    del hs
    n_hi = sum(1 for v in vals if v > 0.1)
    rows.append({"traj": tid, "n_tok": j.get("n_generated_tokens"),
                 "n_sites": len(ts), "n_hi": n_hi,
                 "frac": n_hi / len(ts)})
    print(f"  {tid:<32} {n_hi:>3}/{len(ts):<3} = {n_hi/len(ts):.4f}", flush=True)

rows.sort(key=lambda r: -r["frac"])
out = os.path.join(ROOT, "ortho_frac_full.json")
json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n轨迹 {len(rows)} 条，位点 {sum(r['n_sites'] for r in rows)} 个")
fr = sorted(r["frac"] for r in rows)
print(f"高对齐占比：中位 {fr[len(fr)//2]:.4f}，最大 {fr[-1]:.4f}")
tot_hi = sum(r["n_hi"] for r in rows)
tot_sites = sum(r["n_sites"] for r in rows)
print(f"合计高对齐位点 {tot_hi}/{tot_sites} = {tot_hi/tot_sites:.4f}")
print(f"（对照：p01_think = 21/133 = {21/133:.6f}；预登记 §24.1 把它写成 0.1577，"
      f"是四舍五入误差，见修订 25）")
print(f"写出 {out}")