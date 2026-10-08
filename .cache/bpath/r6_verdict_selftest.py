"""r6_verdict.py 的自检：统计量对不对 + 两条「不该给结论」的分支拦不拦得住。

判决脚本是产出最终答案的那一环，全绿但算错就等于没判决。
本脚本用**已知答案的构造数据**逐项验，并故意触发两条保护分支。

## 判决规则（取数前写死）

  S1 Cliff's delta：x 全大于 y => +1；全小于 => -1；完全相同 => 0
     且**重叠样本必须落在 (0,1)**（防「delta 恒为 1」的实现照样全绿）
  S2 Mann–Whitney：同分布 => p 不显著；完全分离 => p 恰等于闭式解 2/C(n1+n2,n1)
     小样本走精确分支（返回 z=nan），大样本走正态近似（z 有限）——两条分支都要被钉住
  S3 Hodges–Lehmann：x=[1,2], y=[0,1] 的全部差值中位数 = 1
  S4 correct 组不足 10 条 => 判决串必须含「样本不足」
  S5 wrong 组不足 8 条 => 同上
  S6 P9 未通过 => 脚本必须拒绝出判决（返回码 2），而不是照常算
  S7 **全 PASS 的判决脚本等于没有判决**：至少要有一条构造数据让某条判红
"""
from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r6v", HERE / "r6_verdict.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)

FAILS = []
TOTAL = 0


def chk(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {extra}")
    if not cond:
        FAILS.append(name)


print("=" * 74)
print("S1-S3 统计量")
print("=" * 74)
chk("S1a delta 完全分离 x>y", V.cliffs_delta([10, 11, 12], [1, 2, 3]) == 1.0)
chk("S1b delta 完全分离 x<y", V.cliffs_delta([1, 2, 3], [10, 11, 12]) == -1.0)
chk("S1c delta 完全相同", V.cliffs_delta([5, 5, 5], [5, 5, 5]) == 0.0)

U, p, z = V.mannwhitney([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
chk("S2a 同分布 p 大", p > 0.5, f"p={p:.3f}")

# n1=n2=5 且完全分离：精确分布只有 252 种排列，双侧命中 2 种
# => p = 2/C(10,5) = 0.007937，**不是** 1e-3 量级。
# 这里验的是闭式解，不是「p 小」——p 小是真的，但小到哪是另一件事。
U, p, z = V.mannwhitney([100, 101, 102, 103, 104], [1, 2, 3, 4, 5])
closed = 2 / math.comb(10, 5)
chk("S2b 完全分离 p 等于闭式解 2/C(10,5)",
    abs(p - closed) < 1e-9, f"p={p:.8f} 闭式={closed:.8f}")
chk("S2c 精确分支不返回 z（不是 z=0，也不是 nan 混进判决）",
    math.isnan(z), f"z={z!r}")

# 另一条分支也要被钉住：n1*n2 > EXACT_MAX 时才走正态近似，那时必须有有限 z。
# z 走 SF 上尾所以恒为正（Uhi >= mu），这里用 |z| 断言，不写死符号。
big_c = list(range(100, 100 + 30))
big_w = list(range(0, 30))
U, p, z = V.mannwhitney(big_c, big_w)
chk("S2d 大样本走正态近似：z 有限且显著",
    math.isfinite(z) and abs(z) > 3 and p < 1e-6, f"z={z:.2f} p={p:.2e}")

# 并列时顶层必须改走正态近似：scipy 的 exact 内部把 U astype(int)，
# 带并列会把 U 截断，算出来的是一个不存在的分布的尾概率。
p_tie = V.mannwhitney([0.0, 0.0, 0.0, 0.0, 0.0] + [2.0] * 5,
                      [0.0] * 6 + [1.0] * 4)[1]
p_asym = float(V.SCIPY([0.0, 0.0, 0.0, 0.0, 0.0] + [2.0] * 5,
                       [0.0] * 6 + [1.0] * 4, alternative="two-sided",
                       method="asymptotic").pvalue)
chk("S2e 并列数据走正态近似而非 exact",
    math.isfinite(p_tie) and abs(p_tie - p_asym) < 1e-12,
    f"p={p_tie:.6f}")

hl = V.hodges_lehmann([1, 2], [0, 1])
chk("S3 HL 估计量", hl == 1.0, f"HL={hl}")


def mk_rows(n_correct, n_wrong, cv, wv, mode="no_think"):
    rows = []
    for i in range(n_correct):
        rows.append({"traj": f"c{i}", "mode": mode, "label": "correct",
                     **{f"mark_w+_1.0": cv + i, f"the_w+_1.0": 0.1}})
    for i in range(n_wrong):
        rows.append({"traj": f"w{i}", "mode": mode, "label": "wrong",
                     **{f"mark_w+_1.0": wv + i, f"the_w+_1.0": 0.1}})
    return rows


print()
print("=" * 74)
print("S4-S5 保护分支")
print("=" * 74)
tmp = Path(tempfile.mkdtemp())

# correct 够、wrong 不够
d = {"pos_ok": True, "rows": mk_rows(12, 5, 1.0, 1.0), "rel_ladder": [1.0],
     "class_gap": 300.0}
json.dump(d, open(tmp / "a.json", "w"))
subprocess.run([sys.executable, str(HERE / "r6_verdict.py"), str(tmp / "a.json"),
                str(tmp / "a.out.json")], capture_output=True)
res = json.load(open(tmp / "a.out.json", encoding="utf-8"))
e = res["verdicts"]["mark_w+_1.0"]["per_mode"]["no_think"]
chk("S4 correct 够 / wrong 不够 -> 样本不足",
    "样本不足" in e["verdict"] and e["wrong_n"] == 5, e["verdict"][:60])

# correct 不够
d = {"pos_ok": True, "rows": mk_rows(6, 20, 1.0, 1.0), "rel_ladder": [1.0],
     "class_gap": 300.0}
json.dump(d, open(tmp / "b.json", "w"))
subprocess.run([sys.executable, str(HERE / "r6_verdict.py"), str(tmp / "b.json"),
                str(tmp / "b.out.json")], capture_output=True)
res = json.load(open(tmp / "b.out.json", encoding="utf-8"))
e = res["verdicts"]["mark_w+_1.0"]["per_mode"]["no_think"]
chk("S5 correct 不够 -> 样本不足", "样本不足" in e["verdict"], e["verdict"][:60])

print()
print("=" * 74)
print("S6 P9 未通过必须拒绝出判决")
print("=" * 74)
json.dump({"pos_ok": False, "rows": mk_rows(20, 20, 5.0, 1.0)},
          open(tmp / "c.json", "w"))
r = subprocess.run([sys.executable, str(HERE / "r6_verdict.py"), str(tmp / "c.json"),
                    str(tmp / "c.out.json")], capture_output=True, text=True)
res = json.load(open(tmp / "c.out.json", encoding="utf-8"))
chk("S6 返回码 2 且标记 blocked",
    r.returncode == 2 and res.get("blocked_by_P9") is True,
    f"rc={r.returncode}")
chk("S6 且没有产出任何判决", "verdicts" not in res)

print()
print("=" * 74)
print("S7 反向样本必须被判出「显著不同」（证明判据不是恒绿）")
print("=" * 74)
# 全分离：correct=[20..31] > wrong=[0.1..11.1]，delta 必须是 +1.000
d = {"pos_ok": True, "rows": mk_rows(12, 12, 20.0, 0.1), "rel_ladder": [1.0],
     "class_gap": 300.0}
json.dump(d, open(tmp / "d.json", "w"))
subprocess.run([sys.executable, str(HERE / "r6_verdict.py"), str(tmp / "d.json"),
                str(tmp / "d.out.json")], capture_output=True)
res = json.load(open(tmp / "d.out.json", encoding="utf-8"))
e = res["verdicts"]["mark_w+_1.0"]["per_mode"]["no_think"]
chk("S7a 强分离样本判显著不同", "显著不同" in e["verdict"], e["verdict"][:50])
chk("S7b p 值很小", e.get("p", 1) < 0.05, f"p={e.get('p')}")
chk("S7c Cliff's delta = +1（全分离）", e.get("cliffs_delta") == 1.0,
    f"delta={e.get('cliffs_delta')}")

# **重叠**样本：correct=[5..16] 与 wrong=[0.1..11.1] 有交集，
# delta 必须落在 (0,1) 之间。这一条是防「delta 恒为 1」的牙齿：
# 只测全分离的话，一个写死 return 1.0 的实现也能全绿。
d = {"pos_ok": True, "rows": mk_rows(12, 12, 5.0, 0.1), "rel_ladder": [1.0],
     "class_gap": 300.0}
json.dump(d, open(tmp / "d2.json", "w"))
subprocess.run([sys.executable, str(HERE / "r6_verdict.py"), str(tmp / "d2.json"),
                str(tmp / "d2.out.json")], capture_output=True)
res = json.load(open(tmp / "d2.out.json", encoding="utf-8"))
e = res["verdicts"]["mark_w+_1.0"]["per_mode"]["no_think"]
dl = e.get("cliffs_delta", -1)
chk("S7e 重叠样本 delta 严格落在 (0,1)",
    0.0 < dl < 1.0, f"delta={dl} p={e.get('p')}")

# 同分布样本必须判「未观察到」，而不是误报显著
d = {"pos_ok": True, "rows": mk_rows(12, 12, 1.0, 1.0), "rel_ladder": [1.0],
     "class_gap": 300.0}
json.dump(d, open(tmp / "e.json", "w"))
subprocess.run([sys.executable, str(HERE / "r6_verdict.py"), str(tmp / "e.json"),
                str(tmp / "e.out.json")], capture_output=True)
res = json.load(open(tmp / "e.out.json", encoding="utf-8"))
e = res["verdicts"]["mark_w+_1.0"]["per_mode"]["no_think"]
chk("S7d 同分布样本不误报显著", "未观察到" in e["verdict"], e["verdict"][:50])

print()
print("=" * 74)
print("S8 次级分析 S1–S3（修订 4）：既能判红也不能恒绿")
print("=" * 74)


def mk_traj(name, mode, label, d10, d05=None, the=0.1):
    return {"traj": name, "mode": mode, "label": label,
            "traj_d": {"mark_w+_1.0": d10,
                       **({"mark_w+_0.5": d05} if d05 is not None else {}),
                       "the_w+_1.0": the}}


# S1 剂量单调：剂量翻倍效应变大 => 应判「显著增大且方向为正」
up = [mk_traj(f"u{i}", "no_think", "correct", 2.0 + 0.1 * i, 0.5 + 0.01 * i)
      for i in range(12)]
r = V.s1_dose_monotonic(up, "no_think")
chk("S8a 剂量单调为正 -> 判显著增大", "显著增大" in r["verdict"],
    f"p={r.get('p')} med={r.get('median_diff')}")

# S1 反向：剂量翻倍效应变小 => **不得**判「显著增大」
down = [mk_traj(f"d{i}", "no_think", "correct", 0.5 + 0.01 * i, 2.0 + 0.1 * i)
        for i in range(12)]
r = V.s1_dose_monotonic(down, "no_think")
chk("S8b 剂量单调为负 -> 不得判显著增大",
    "显著增大" not in r["verdict"], r["verdict"][:56])

# S1 恒绿防护：完全无差的两组必须判「未观察到」
flat = [mk_traj(f"f{i}", "no_think", "correct", 1.0, 1.0) for i in range(12)]
r = V.s1_dose_monotonic(flat, "no_think")
chk("S8c 无剂量效应 -> 判未观察到", "未观察到" in r["verdict"],
    f"p={r.get('p')}")

# S1 样本不足：配对数 < 5 必须拒绝
r = V.s1_dose_monotonic(up[:3], "no_think")
chk("S8d 配对数不足 -> 样本不足", "样本不足" in r["verdict"])

# S2 三组：correct/wrong/unlabeled 有差异时应判显著，且必须给出两两比较
three = ([mk_traj(f"c{i}", "no_think", "correct", 5.0 + i) for i in range(9)]
         + [mk_traj(f"w{i}", "no_think", "wrong", 0.1 + 0.1 * i) for i in range(9)]
         + [mk_traj(f"u{i}", "no_think", "unlabeled", 2.5 + 0.1 * i)
            for i in range(9)])
r = V.s2_three_group(three, "no_think", "mark_w+_1.0")
chk("S8e S2 三组有差异 -> 判显著且带两两比较",
    "三组存在差异" in r["verdict"] and len(r.get("pairwise") or {}) == 3,
    f"p={r.get('p')} 组数={r['n']}")

# S2 反向：三组同分布 -> 不得误报
same = ([mk_traj(f"c{i}", "no_think", "correct", 1.0 + 0.1 * i) for i in range(9)]
        + [mk_traj(f"w{i}", "no_think", "wrong", 1.0 + 0.1 * i) for i in range(9)]
        + [mk_traj(f"u{i}", "no_think", "unlabeled", 1.0 + 0.1 * i)
           for i in range(9)])
r = V.s2_three_group(same, "no_think", "mark_w+_1.0")
chk("S8f S2 三组同分布 -> 不误报", "未观察到" in r["verdict"], f"p={r.get('p')}")

# S3：unlabeled 也必须进 n（这正是 S3 与 P8 的区别）
withu = up + [mk_traj(f"z{i}", "no_think", "unlabeled", 3.0, 1.0)
              for i in range(8)]
r = V.s3_specificity(withu, "no_think")
chk("S8g S3 把 unlabeled 也计入 n", r["n"] == len(withu),
    f"n={r['n']}/{len(withu)}")

print()
print("=" * 74)
print(f"总计 {TOTAL} 项，失败 {len(FAILS)}")
if FAILS:
    print("失败项:", FAILS)
print("=" * 74)
print("=> " + ("判决脚本可用。" if not FAILS else "**判决脚本有问题，先修再出结论。**"))
sys.exit(0 if not FAILS else 1)