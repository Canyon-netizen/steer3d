"""只读核对 P9 基准轨迹的选取，不加载模型、不占 GPU。

要回答三个问题（都关系到 P9 到底在测什么）：
  1. smoke_tids 选中的是哪 3 条？是 think 还是 no_think？
  2. 它们是否落在 train_tids 里（即 P9 基准是不是**样本内**的）？
  3. labels 文件对这 3 条覆盖了没有？

算不到、答不上来就明说，不猜。
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SC = Path("/home/zhourui/steer3d_bpath/gen_b2/aime")
LAB = sys.argv[1] if len(sys.argv) > 1 else "/home/zhourui/steer3d_bpath/labels_full60.json"

# 常量**从被测代码里 import**，不复制一份。
# 我第一版凭印象写了 MARKER_IDS=[151645,151644]，真值是 7 个
# [13824,14190,6771,10061,7196,88190,80022] —— 照抄的那份会把 marker 全数漏掉，
# 于是「有 marker 的前 3 条」选出来的东西根本不是 P9 真正用的那 3 条。
spec = importlib.util.spec_from_file_location("r6run", HERE / "r6_rerun.py")
R6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R6)
MARKER_IDS = R6.MARKER_IDS
print(f"MARKER_IDS（从 r6_rerun.py 读入）= {MARKER_IDS}")
print(f"LAYER={R6.LAYER}  REL_LADDER={R6.REL_LADDER}  CONTROL_ID={R6.CONTROL_ID}")
print()

lab = {r["traj"]: r for r in json.load(open(LAB, encoding="utf-8"))["rows"]}

metas = {}
for f in sorted(SC.glob("*.json")):
    j = json.load(open(f, encoding="utf-8"))
    tid = j["trajectory_id"]
    markers = [i for i, t in enumerate(j.get("tokens") or [])
               if t["token_id"] in MARKER_IDS]
    metas[tid] = {
        "mode": j["config"]["mode"],
        "n_markers": len(markers),
        "label": lab[tid]["strict"] if tid in lab else "MISSING",
    }

train_tids = {t for t, v in metas.items()
              if v["mode"] == "think" and v["n_markers"] >= 3}
smoke_tids = [t for t in sorted(metas) if metas[t]["n_markers"]][:3]

print(f"轨迹总数 {len(metas)}   train_tids（think 且 >=3 marker）{len(train_tids)} 条")
print(f"标签覆盖：{sum(1 for v in metas.values() if v['label']!='MISSING')}/{len(metas)}")
print()
print("排序后前 6 条（冒烟基准就是取前 3 条有 marker 的）：")
for t in sorted(metas)[:6]:
    v = metas[t]
    print(f"  {t:44s} {v['mode']:9s} markers={v['n_markers']:3d} "
          f"label={v['label']:9s} in_train={t in train_tids}")
print()
print("P9 基准 smoke_tids：")
inside = 0
for t in smoke_tids:
    v = metas[t]
    ins = t in train_tids
    inside += ins
    print(f"  {t:44s} {v['mode']:9s} markers={v['n_markers']:3d} "
          f"label={v['label']:9s} in_train={ins}")
print()
print(f"结论：{inside}/3 条落在 train_tids 内 ⇒ "
      f"{'P9 基准是**样本内**的' if inside else 'P9 基准**不在**训练集内'}")
print(f"      其中 think {sum(1 for t in smoke_tids if metas[t]['mode']=='think')} 条，"
      f"no_think {sum(1 for t in smoke_tids if metas[t]['mode']=='no_think')} 条")
