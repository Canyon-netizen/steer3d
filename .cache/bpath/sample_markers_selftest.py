"""sample_markers 取样器的自检：位置必须铺满整条轨迹。

## 为什么这是硬要求

原实现取「前 6 个非空分位」，在 10 个分位全非空时**只覆盖前 60%**，
且报告里看不出任何异常。think 模式 96% 的轨迹中招，而 think 恰是
唯一能过 P6 的模式 ⇒ 结论会变成「轨迹前 60% 上如何如何」却写成通用结论。

这类「不报错、不崩、只是系统性偏掉」的缺陷，全绿自检抓不到，
所以这里钉的是**性质**（覆盖跨度），不是具体数字。

## 判据（取数前写死）

  T1 10 个分位全非空时，取样点必须同时落在前半（分位<5）与后半（分位>=5）
  T2 取样点数不超过 MAX_POS_PER_TRAJ，且不重复
  T3 非空分位数 <= 6 时，**全都要被取到**（不因为上限而丢分位）
  T4 桶内取中位而非第一个
  T5 退化输入：空 marker / 单点 / 全部落在同一分位，都不许崩
  T6 牙齿自检：旧实现（原「前 6 个非空分位」）必须被 T1 判红
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
_sp = importlib.util.spec_from_file_location("r6r", HERE / "r6_rerun.py")
R = importlib.util.module_from_spec(_sp)
# 只取纯函数，不 import torch/transformers
_src = (HERE / "r6_rerun.py").read_text(encoding="utf-8")
_ns = {"defaultdict": defaultdict, "MAX_POS_PER_TRAJ": 6}
exec(compile(_src[_src.index("def sample_markers"):_src.index("# ------"
      "---------------------------------------------------------- 训练方向")],
             "<sampler>", "exec"), _ns)
new = _ns["sample_markers"]

FAILS = []
TOTAL = 0


def chk(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {extra}")
    if not cond:
        FAILS.append(name)


def old_impl(marker_idx, n_tok, MAX=6):
    """原实现（保留在测试里做对照）。"""
    if not marker_idx:
        return []
    b = defaultdict(list)
    for g in marker_idx:
        b[min(9, int(g / max(n_tok, 1) * 10))].append(g)
    out = []
    for k in sorted(b)[:MAX]:
        out.append(b[k][0])
    return sorted(out)


def decile(g, n_tok):
    return min(9, int(g / max(n_tok, 1) * 10))


print("=" * 74)
print("T1 取样点必须铺满前后半（10 分位全非空）")
print("=" * 74)
N = 10000
full = list(range(50, 9950, 50))          # 10 个分位各 10 个点
picked = new(full, N)
ds = [decile(g, N) for g in picked]
chk("T1a 10 分位全非空时取到 6 个位置", len(picked) == 6, f"取到 {len(picked)}")
chk("T1b 前半（分位<5）与后半（分位>=5）都有点",
    any(d < 5 for d in ds) and any(d >= 5 for d in ds), f"分位={ds}")
chk("T1c 最靠后的分位被取到", max(ds) >= 8, f"最大分位={max(ds)}")

print()
print("=" * 74)
print("T2 上限与去重")
print("=" * 74)
dense = list(range(10, N, 3))              # 每分位大量点
p2 = new(dense, N)
chk("T2a 不超过 6 个位置", len(p2) <= 6, f"取到 {len(p2)}")
chk("T2b 无重复", len(set(p2)) == len(p2))
chk("T2c 取到的都在 marker 集合里", set(p2) <= set(dense))
chk("T2d 返回值有序", p2 == sorted(p2))

print()
print("=" * 74)
print("T3 非空分位 <= 6 时全都要取到")
print("=" * 74)
few = [500, 1500, 2500, 3500, 4500, 5500]   # 分位 0..5 各 1 个
p3 = new(few, N)
chk("T3a 6 个非空分位全部取到", len(p3) == 6, f"取到 {len(p3)}")
two = [100, 9500]
p3b = new(two, N)
chk("T3b 只有 2 个非空分位时取到 2 个", len(p3b) == 2, f"取到 {len(p3b)}")
chk("T3c 取的是这两个分位本身",
    {decile(g, N) for g in p3b} == {0, 9}, f"分位={[decile(g, N) for g in p3b]}")

print()
print("=" * 74)
print("T4 桶内取中位而非第一个")
print("=" * 74)
one_bucket = list(range(100, 1000, 10))     # 全在分位 0
p4 = new(one_bucket, N)
chk("T4a 单分位只取 1 个点", len(p4) == 1, f"取到 {len(p4)}")
chk("T4b 取的是桶内中位", p4[0] == sorted(one_bucket)[len(one_bucket) // 2],
    f"取了 {p4[0]}，中位 {sorted(one_bucket)[len(one_bucket) // 2]}")

print()
print("=" * 74)
print("T5 退化输入不许崩")
print("=" * 74)
for tag, mk, n in [("空 marker", [], N),
                   ("单个 marker", [5000], N),
                   ("全在同一分位", [100, 200, 300], N),
                   ("n_tok=0", [100, 5000], 0),
                   ("越界位置", [99999, 5], N)]:
    try:
        r = new(mk, n)
        chk(f"T5 {tag}", isinstance(r, list), f"-> {r}")
    except Exception as e:
        chk(f"T5 {tag}", False, f"抛异常 {type(e).__name__}: {e}")

print()
print("=" * 74)
print("T6 牙齿自检：旧实现必须被 T1 判红")
print("=" * 74)
old_p = old_impl(full, N)
old_ds = [decile(g, N) for g in old_p]
# 旧实现的缺陷是「够到后半但够不到尾部」：它取到分位 5，
# 所以只查「有没有后半点」是抓不住它的 —— 必须查 T1c 的尾部覆盖。
old_reaches_tail = max(old_ds) >= 8
chk("T6a 旧实现够不到最后一个非空分位（说明 T1c 有牙齿）",
    old_reaches_tail is False, f"旧实现分位={old_ds} 最大={max(old_ds)}")
chk("T6b 旧实现确实漏掉了尾部", max(old_ds) < 8, f"旧最大分位={max(old_ds)}")
chk("T6c 新旧实现结果不同（否则这次修改没生效）", old_p != new(full, N),
    f"旧={old_p[:3]}... 新={sorted(new(full, N))[:3]}...")
# 反向：新实现必须够到尾部，且这正是 T1c 的内容
chk("T6d 新实现够到最后一个非空分位", max(decile(g, N) for g in new(full, N)) >= 8)

print()
print("=" * 74)
print(f"总计 {TOTAL} 项，失败 {len(FAILS)}")
if FAILS:
    print("失败项:", FAILS)
print("=" * 74)
print("=> " + ("取样器合格。" if not FAILS else "**取样器有偏倚，先修再开跑。**"))
sys.exit(0 if not FAILS else 1)