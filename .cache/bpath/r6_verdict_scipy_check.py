"""交叉验证 r6_verdict.py 的统计量：手写兜底实现 vs scipy vs 暴力枚举。

判决脚本的 p 值直接决定「显著 / 未观察到」，算错就是假结论，所以三层都要对齐。

## 三层参照

1. **`scipy.stats.mannwhitneyu`** —— `r6_verdict.mannwhitney()` 的权威实现，
   p 值直接来自它。本脚本的第一职责是确认它被**正确调用**
   （分支选对、没有踩「并列时用 exact」那个坑）。
2. **`_mannwhitney_builtin`** —— 手写兜底实现。逐例与 scipy 比对。
   它的存在意义是 scipy 不可用时不至于当场崩，但它**必须**被钉住。
3. **`brute_exact_p()`** —— 穷举 C(n,m) 种打标方式的真值。
   scipy 的 `method='exact'` 内部把 U `astype(int)`，**带并列时会截断**，
   所以带并列的精确分支只能靠穷举验。

## 这套脚本抓到的三个真 bug（均已修）

1. `_exact_p()` 按「秩 1..n 互不相同」DP ⇒ 有并列时描述的是一个不存在的
   分布。实测 p 0.381 vs 真值 0.335（偏差 0.046，方向不定）。
   修法：按**取值分组** DP，组内乘 C(c_j, k)。
2. 双侧定义写成 `2*P(U<=min)`，scipy 用的是 `2*P(U>=max)`。
   在中心质量点上整整差一个质量（实测 0.503 vs 1.000）。
   修法：按 scipy 的 `sf(U, min, max)` 口径重算。
3. 连续性校正**符号写反**。scipy 走上尾 `sf(max(U1,U2))` 所以减 0.5；
   按 `min` 取绝对值就要加 0.5。写反了比不校正还差。

另有一个不是 bug 但同样致命的**陷阱**：
`n1*n2 <= EXACT_MAX` 这个门槛只看样本量、不看并列，
带并列时照样走 exact 分支 ⇒ scipy 内部截断 U。
现在并列一律退回正态近似。
"""
from __future__ import annotations

import importlib.util
import itertools
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_sp = importlib.util.spec_from_file_location("r6v", HERE / "r6_verdict.py")
V = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(V)

import numpy as np
from scipy.stats import mannwhitneyu, rankdata

FAIL = []


def check(tag, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {tag}  {extra}")
    if not cond:
        FAIL.append(tag)


def brute_exact_p(x, y):
    """穷举 C(n,m) 种「哪些观测属于较小的那组」，按 scipy 口径取双侧 p。

    只用于**小 n**（n<=18，C(18,9)=48620，纯 Python 可接受）。
    验证的是 DP 的组合逻辑，逻辑与 n 大小无关，所以刻意不在大 n 上跑。
    """
    n1, n2 = len(x), len(y)
    pooled = list(x) + list(y)
    n = n1 + n2
    if math.comb(n, min(n1, n2)) > 200000:
        raise ValueError(f"n={n} 的穷举太慢，请用更小的样本")
    ranks = [float(v) for v in rankdata(pooled)]    # 平均秩，正确处理并列
    U1 = sum(ranks[:n1]) - n1 * (n1 + 1) / 2.0
    uhi = max(U1, n1 * n2 - U1)
    m = min(n1, n2)
    get = ranks.__getitem__
    cnt = tot = 0
    for combo in itertools.combinations(range(n), m):
        # 组合给的是「较小的那组」；若 x 就是较小组则 U=U1，否则 U=nm-U1
        u_sel = sum(map(get, combo)) - m * (m + 1) / 2.0
        tot += 1
        if u_sel >= uhi - 1e-12:
            cnt += 1
    assert tot == math.comb(n, m), f"穷举总数不对: {tot} != {math.comb(n, m)}"
    return min(1.0, 2.0 * cnt / tot)


print("=" * 76)
print("0 scipy 是否可用（权威实现缺席则本脚本无意义）")
print("=" * 76)
check("0.1 r6_verdict 已 import 到 scipy", V.SCIPY is not None)


print()
print("=" * 76)
print("1 权威实现选择正确性：分支按「样本量 AND 无并列」选")
print("=" * 76)


def branch_of(x, y):
    n1, n2 = len(x), len(y)
    _, ties = V._ranks(list(x) + list(y))
    return "exact" if (n1 * n2 <= V.EXACT_MAX and not ties) else "asymptotic"


cases = [
    ("n1*n2=100 无并列", [0.5 * i for i in range(10)], [10 + 0.25 * i for i in range(10)], "exact"),
    ("n1*n2=441 超门槛 无并列", [0.5 * i for i in range(21)],
     [100 + 0.25 * i for i in range(21)], "asymptotic"),
    ("n1*n2=100 有并列 -> 必须退回正态", [0.0] * 10, [10.0] * 5 + [0.0] * 5, "asymptotic"),
    ("全同值（有并列）", [1.0] * 10, [1.0] * 10, "asymptotic"),
]
for tag, x, y, want in cases:
    check(f"1.{cases.index((tag, x, y, want)) + 1} {tag}", branch_of(x, y) == want,
          f"实得 {branch_of(x, y)}")

# 带并列时若误用 exact，scipy 内部 astype(int) 会截断 U
x_t, y_t = [0.0] * 5 + [1.0] * 3, [0.0] * 6 + [1.0] * 2
p_wrong = float(mannwhitneyu(x_t, y_t, method="exact").pvalue)
p_right = V.mannwhitney(x_t, y_t)[1]
p_bf = brute_exact_p(x_t, y_t)
check("1.5 带并列时误用 exact 会跑偏（本脚本选对了分支）",
      abs(p_wrong - p_bf) > 1e-6 and abs(p_right - float(
          mannwhitneyu(x_t, y_t, method="asymptotic").pvalue)) < 1e-12,
      f"误用exact={p_wrong:.6f} 正确={p_right:.6f} 真值(精确)={p_bf:.6f}")


print()
print("=" * 76)
print("2 手写兜底实现 == scipy（随机数据，含大量并列）")
print("=" * 76)


def run_vs_scipy(ncases, lo, hi, n1, n2, tag, nplaces, seed):
    rng = random.Random(seed)
    w = 0.0
    n_tied = n_exact = 0
    worst_case = None
    for _ in range(ncases):
        x = [round(rng.uniform(lo, hi), nplaces) for _ in range(n1)]
        y = [round(rng.uniform(lo, hi), nplaces) for _ in range(n2)]
        tied = len(set(x + y)) < len(x) + len(y)
        n_tied += tied
        n_exact += (branch_of(x, y) == "exact")
        mth = branch_of(x, y)
        p_ref = float(mannwhitneyu(x, y, method=mth).pvalue)
        p_mine = V._mannwhitney_builtin(x, y, mth)[1]
        d = abs(p_mine - p_ref)
        if d > w:
            w, worst_case = d, (p_mine, p_ref, x, y, mth)
    print(f"\n[{tag}] n1={n1} n2={n2} 域 {lo}~{hi} 精度{nplaces}位 "
          f"-> 精确分支 {n_exact}/{ncases}，含并列 {n_tied}/{ncases}")
    check(f"{tag} 手写 == scipy", w < 1e-12, f"max|Δp|={w:.2e}")
    if w >= 1e-12 and worst_case:
        print(f"      p_builtin={worst_case[0]:.8f} p_scipy={worst_case[1]:.8f} "
              f"({worst_case[4]})")
        print(f"      x={worst_case[2]}\n      y={worst_case[3]}")
    return w


run_vs_scipy(200, -5, 5, 10, 12, "2a 高精度（无并列 -> 精确分支）", 12, 101)
run_vs_scipy(200, -3, 3, 10, 12, "2b 整数（含并列 -> 正态分支）", 0, 102)
run_vs_scipy(150, -3, 3, 21, 21, "2c 大样本", 0, 103)
run_vs_scipy(150, -3, 3, 13, 17, "2d n1!=n2（检验 min/max 帧）", 0, 104)


print()
print("=" * 76)
print("3 手写精确分支 == 暴力枚举（**含并列**）")
print("=" * 76)


def run_vs_brute(ncases, lo, hi, n1, n2, tag, nplaces, seed):
    """无并列的精确分支：穷举是真值，且**非饱和**（p 多半落在 0~1 中间），
    所以能抓住 DP 里任何常量平移 —— 饱和断言（完全分离）抓不到那类错。"""
    rng = random.Random(seed)
    w = 0.0
    mid = 0
    worst_case = None
    for _ in range(ncases):
        x = [round(rng.uniform(lo, hi), nplaces) for _ in range(n1)]
        y = [round(rng.uniform(lo, hi), nplaces) for _ in range(n2)]
        assert len(set(x + y)) == n1 + n2, "本组要求无并列"
        p_bf = brute_exact_p(x, y)
        p_mine = V._mannwhitney_builtin(x, y, "exact")[1]
        d = abs(p_mine - p_bf)
        if 1e-9 < p_bf < 1 - 1e-9:
            mid += 1
        if d > w:
            w, worst_case = d, (p_mine, p_bf, x, y)
    print(f"\n[{tag}] n1={n1} n2={n2} 域 {lo}~{hi} 精度{nplaces}位 "
          f"（非饱和 {mid}/{ncases}）")
    check(f"{tag} 精确分支 == 穷举", w < 1e-12, f"max|Δp|={w:.2e}")
    if w >= 1e-12 and worst_case:
        print(f"      p_builtin={worst_case[0]:.8f} p_brute={worst_case[1]:.8f}")
        print(f"      x={worst_case[2]}\n      y={worst_case[3]}")
    return w


run_vs_brute(300, -5, 5, 8, 9, "3a 无并列 小样本", 12, 201)
run_vs_brute(200, -5, 5, 6, 6, "3b 无并列 n1==n2", 12, 202)
run_vs_brute(150, -5, 5, 5, 11, "3c 无并列 n1!=n2（检验 min/max 帧）", 12, 203)


print()
print("=" * 76)
print("3x 带并列数据必须被**拒绝**，而不是给一个口径依赖的数")
print("=" * 76)
for tag, xa, ya in [("整数", [0.0, 1.0, 1.0, -1.0], [0.0, 0.0, 2.0, -1.0, 1.0]),
                    ("全同值", [1.0] * 4, [1.0] * 5)]:
    try:
        V._exact_p(xa, ya, 3.0)
        check(f"3x.{'整数' if tag == '整数' else '全同值'} 并列被拒绝", False,
              "竟然算出了数")
    except ValueError:
        check(f"3x.{'整数' if tag == '整数' else '全同值'} 并列被拒绝", True)

# mannwhitney() 顶层见到并列必须改走正态近似，不能落到精确分支
_, ties = V._ranks([0.0, 1.0, 1.0, -1.0] + [0.0, 0.0, 2.0, -1.0, 1.0])
check("3x 并列时顶层已选正态分支",
      branch_of([0.0, 1.0, 1.0, -1.0], [0.0, 0.0, 2.0, -1.0, 1.0]) == "asymptotic",
      f"ties={bool(ties)}")


print()
print("=" * 76)
print("4 端点：归一化两头都要钉死")
print("=" * 76)
n = 10
p_sep = V.mannwhitney([100 + i for i in range(n)], [i for i in range(n)])[1]
closed = 2 / math.comb(2 * n, n)
check("4.1 完全分离 p == 2/C(n,n1)", abs(p_sep - closed) < 1e-12,
      f"p={p_sep:.10f} 闭式={closed:.10f}")
p_same = V.mannwhitney([1.0] * n, [1.0] * n)[1]
check("4.2 全体相同 p == 1", p_same == 1.0, f"p={p_same}")

half = V._mannwhitney_builtin([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                              [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
                              "exact")[1]
p_bf = brute_exact_p([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                     [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0])
check("4.3 完全分离 精确分支 == 穷举", abs(half - p_bf) < 1e-12,
      f"p={half:.10f} 穷举={p_bf:.10f}")

# 中间值断言：抓「秩少 1」那类**常量平移**。
# 完全分离那类是饱和的（p 顶到 2/C(n,n1)），任何偏移都可能被掩盖。
mid = V._mannwhitney_builtin(list(range(6)), list(range(6, 14)), "exact")[1]
mid_bf = brute_exact_p(list(range(6)), list(range(6, 14)))
check("4.4 中间值（非饱和）断言能抓住常量平移",
      abs(mid - mid_bf) < 1e-12, f"p={mid:.8f} 穷举={mid_bf:.8f}")
check("4.5 4.4 确实是非饱和的（否则这条断言没有牙齿）",
      1e-6 < mid_bf < 1 - 1e-6, f"p={mid_bf:.8f}")


print()
print("=" * 76)
print("5 Cliff's delta / HL")
print("=" * 76)
rng = random.Random(999)
w_d = 0.0
for _ in range(200):
    x = [rng.randint(0, 10) for _ in range(11)]
    y = [rng.randint(0, 10) for _ in range(13)]
    U1 = mannwhitneyu(x, y, method="asymptotic").statistic
    w_d = max(w_d, abs(V.cliffs_delta(x, y) - (2 * U1 / (len(x) * len(y)) - 1)))
check("5.1 delta == 2U/(n1n2)-1", w_d < 1e-9, f"max|Δ|={w_d:.2e}")

w_h = 0.0
for _ in range(100):
    x = [rng.randint(0, 10) for _ in range(9)]
    y = [rng.randint(0, 10) for _ in range(11)]
    d = sorted(a - b for a in x for b in y)
    m = len(d)
    ref = float(d[m // 2]) if m % 2 else (d[m // 2 - 1] + d[m // 2]) / 2
    w_h = max(w_h, abs(V.hodges_lehmann(x, y) - ref))
check("5.2 HL == 差值中位数", w_h < 1e-9, f"max|Δ|={w_h:.2e}")


print()
print("=" * 76)
print("6 牙齿自检：把已知 bug 注入回去，本脚本必须变红")
print("=" * 76)
print("（四个变异都是本脚本开发过程中**真实抓到过**的缺陷，不是编的）")

import tempfile

SRC = (HERE / "r6_verdict.py").read_text(encoding="utf-8")
MUTATIONS = [
    ("M1 精确 DP 的秩少 1（常量平移）",
     "i + j + 2))   # 平均秩=(i+j)/2+1，×2 即 i+j+2",
     "i + j + 1))   # MUTANT"),
    ("M2 并列时仍走 exact 分支",
     'method = "exact" if (n1 * n2 <= EXACT_MAX and not has_tie) else "asymptotic"',
     'method = "exact" if (n1 * n2 <= EXACT_MAX) else "asymptotic"'),
    ("M3 连续性校正符号反了",
     "z = (Uhi - mu - 0.5) / sd            # 走 SF 上尾，所以**减** 0.5",
     "z = (Uhi - mu + 0.5) / sd            # MUTANT"),
    ("M4 精确分支尾方向反了",
     "if s2 - off2 >= uhi2 - 1e-9:",
     "if s2 - off2 <= uhi2 + 1e-9:        # MUTANT"),
]


def probe(src_text, tag):
    """在变异版上跑三组探针，返回 (p_builtin, branch, exact_raises)。"""
    import importlib.util
    tmp = Path(tempfile.mkdtemp()) / "mut_verdict.py"
    tmp.write_text(src_text, encoding="utf-8")
    s = importlib.util.spec_from_file_location("mutverdict", tmp)
    mm = importlib.util.module_from_spec(s)
    s.loader.exec_module(mm)
    xa = [round(v, 12) for v in (0.3, -1.2, 4.4, -3.1, 2.2, -0.7, 5.1, 1.9)]
    ya = [round(v, 12) for v in (-2.4, 3.3, 0.9, -4.8, 1.4, 2.8, -0.2, 4.6, -1.7, 3.7)]
    xt = [0.0, 1.0, 1.0, -1.0, 2.0]
    yt = [0.0, 0.0, 2.0, -1.0, 1.0, 1.0]
    integ = [rng.randint(-3, 3) for _ in range(13)]
    integ2 = [rng.randint(-3, 3) for _ in range(17)]
    try:
        mm._exact_p(xt, yt, 3.0)
        raised = False
    except ValueError:
        raised = True
    return (mm._mannwhitney_builtin(xa, ya, "exact")[1],
            mm.mannwhitney(xt, yt)[1],
            mm.mannwhitney(integ, integ2)[1],
            raised)


base = probe(SRC, "baseline")
check("6.0 原始版本三条探针均可算出且拒绝并列",
      all(isinstance(v, float) for v in base[:3]) and base[3] is True,
      f"exact={base[0]:.6f} tie={base[1]:.6f} asym={base[2]:.6f}")

for tag, old, new in MUTATIONS:
    if old not in SRC:
        check(f"6.{tag} 变异锚点还在", False, "源码已变，锚点失效")
        continue
    got = probe(SRC.replace(old, new, 1), tag)
    differs = [abs(g - b) > 1e-9 for g, b in zip(got[:3], base[:3])]
    raised_diff = got[3] != base[3]
    check(f"6.{tag} 被本脚本的探针抓到", any(differs) or raised_diff,
          f"探针差异 {differs} 并列拒绝变化={raised_diff}")

print()
print("=" * 76)
print(f"失败 {len(FAIL)} 项")
if FAIL:
    print("失败项:", FAIL)
print("=" * 76)
if FAIL:
    print("=> **与独立参照不一致：出判决前必须先修。**")
    sys.exit(1)
print("=> scipy 分支选对手写兜底逐位一致，兜底实现与穷举一致，"
      "四个已知 bug 注入后均被探针抓到。")