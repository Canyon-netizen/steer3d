"""预检：扫描脚本 `ortho_frac_scan.py` 到底会吐出几条？

## 为什么在跑之前查

扫描对「这条轨迹没有 marker 位点」的轨迹是 `continue` 静默跳过的。
判定器 `ortho_frac_verdict.py` 在条数 != 58 时**按设计拒绝出结论**
（用例 4 已先验）。

⇒ 若有轨迹被静默丢掉，58 条的判据（中位数）就建立在**少一条的样本**上，
而这条差异在跑完之前**看不出来**。

本脚本只读**小 JSON**（sidecar），不解 npz、不跑模型、不用 GPU，
对磁盘的压力可忽略。

## 它要报的三件事

1. think 轨迹总数（应为 60）；
2. 其中 SKIP 掉 2 条后剩多少（应为 58）；
3. 每条的 marker 位点数 —— 特别标出**位点数为 0**的轨迹（会被静默丢掉）。
"""
import glob
import json
import os

MK = {13824, 14190, 6771, 10061, 7196, 88190, 80022}
ROOT = "/home/zhourui/steer3d_bpath"
SKIP = {"aime__aime25__p00__think", "aime__aime25__p01__think"}

think, dropped, bad_json = [], [], []
for f in sorted(glob.glob(os.path.join(ROOT, "gen_b2/aime", "*.json"))):
    try:
        j = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        bad_json.append((f, repr(e)))
        continue
    if (j.get("config") or {}).get("mode") != "think":
        continue
    tid = j["trajectory_id"]
    k = sum(1 for t in (j.get("tokens") or []) if t.get("token_id") in MK)
    think.append((tid, k))

kept = [(t, k) for t, k in think if t not in SKIP]
zero = [(t, k) for t, k in kept if k == 0]

print(f"think 轨迹（读到的 sidecar）      : {len(think)}")
print(f"SKIP 掉的                        : {len(think) - len(kept)}  {sorted(SKIP)}")
print(f"扫描脚本实际会处理                : {len(kept)}  （判据要求 58）")
print(f"其中 marker 位点数为 0（会被丢掉）: {len(zero)}  {[t for t, _ in zero]}")
if bad_json:
    print(f"⚠ 读不出来的 sidecar {len(bad_json)} 个：{bad_json[:3]}")
ks = sorted(k for _, k in kept if k > 0)
if ks:
    print(f"位点数 min/中位/max              : {ks[0]}/{ks[len(ks)//2]}/{ks[-1]}")
    print(f"位点总数                        : {sum(ks)}")
print("\n判定：", "OK，条数够，判据可执行" if len(kept) == 58 and not zero
      else "**条数对不上 58 ⇒ 判定器会拒绝出结论**")