#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""headroom_audit.py —— 账本里那些「显著」的判决，离 α=0.05 到底有**几格**（零 GPU）

🔴 **这个工具要回答什么**（修订 244.43）
  ⚖⚠⚖⚠ 244.41 实测：**删掉覆盖率最低那一档**，rand 臂的 p 从 **0.0129** 掉到
     **0.0574**，差**一位**就越过 α。
  ⚖⚠⚖⚖⚖⚖⚖⚖⚠ **那一位是那一档的特例吗？—— 不是。**
  ⚖⚖⚖ n=14 的二项符号检验**逐格**读：
        k=10/14 p=0.1796（不显著）｜**11/14 p=0.0574（不显著）**
        **12/14 p=0.0129（显著）**｜13/14 p=0.00183｜14/14 p=0.00012
  ⚖⚖⚖⚖⚖⚖⇒ ⚠⚠⚠ **12/14 只买 1 格余量**；⚠ 要 **2 格**余量，n=14 下
     必须强到 **13/14 = 0.929** ⇒ ⇒ **这个题库（14 个问题）上，
     任何比例型符号判决都只能有 1 格余量**。
  ⚗⇒ 244.41 不是「发现了一个脆的地方」，⚖⚠⚠⚠⚠ 而是**「脆」是 n=14 的通性**。

⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ **所以这个工具给的是「余量」不是判决**
  ⚖「离 α 有 m 格」= 往**变差**方向走 m 格才会越过 α
  ⚖⚠⚠⚠ **一格 = 数倍 p**（12/14 ⇒ 0.0129 → 0.0574 = **4.4 倍**）
  ⚖⚠⚠⚠⚠⇒ 报余量是为了让读者**按格子读**判决，⛔ 而不是换一个判决

⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖⚖ **两条必须一起说的禁令**
  ⚖ **余量小 ⛔ 不等于**「判决无效」⇒ ⚖ 它只说「**一格之差**」
  ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ **rep_n≥2 解决不了这个问题**：rep_n 量的是**格内噪声**，
     ⛔ 它**不改变 k/n** ⇒ ⇒ **余量只由 n 与效应量决定**

⛔ 本工具：⛔ 不改任何真文件；⛔ 不跑批；⛔ 只做算术（不读日志）。
"""

import argparse
import os
import sys

ALPHA = 0.05
# ⚖ 边界可证冗余的**扫描范围**（C2a 与报告【1】共用同一个常量）
SCAN_HI = 60
#   每条形如 (名字, k, n, 层级) —— 层级只用于分组，⛔ 不参与任何计算。
VERDICTS = [
    ("轨迹级 w", 13, 14, "轨迹级"),
    # ⚖⚠⚠⚠⚖⚠ **修订 244.55 更正**：这里**原来**写的是 `(5, 9)` ——
    #   ⚖ 那个 `9` 是账本 244.9.2 里「**5 正 / 9 负**」的**负数**，
    #   ⚖⚠ 被当成了**样本量** ⇒ `sign_binom(5, 9)` = **1.0**
    #   ⇒ 244.43 的表印出「轨迹级 rand 5/9 p=**1.00000**」❌
    #   ⚖ 权威（244.9.2）：5 正 / 9 负 ⇒ 样本量 **14** ⇒ p = **0.42395** ✅
    #   ⚖⚠ **对结论的影响：零**（余量仍「已越界」、显著判决仍 4 个、
    #   ⚖   余量仍 2/1/1/1、「一格 = 4.4–8.0 倍 p」区间不变）⇒ **判决一个数都没动**。
    #   ⚖ 独立守卫：`.cache/r244/verdict_source_audit.py` 的 C8（从读数重算后对账）。
    ("轨迹级 rand", 5, 14, "轨迹级"),
    ("问题级 w", 7, 7, "问题级"),
    ("问题级 rand", 2, 7, "问题级"),
    ("预登记主统计量 w", 12, 14, "预登记主"),
    ("预登记主统计量 rand", 6, 14, "预登记主"),
    ("传播层 w（244.37）", 9, 14, "事后·层内"),
    ("传播层 rand（244.37）", 12, 14, "事后·层内"),
    ("传播层 w 直接层", 6, 7, "事后·层内"),
    ("传播层 rand 直接层", 5, 7, "事后·层内"),
]
EFFECTS = (0.75, 0.857)
MARGINS = (1, 2, 3)


class HardFail(Exception):
    pass


def _load(modname, fname):
    """⚖⚠⚖⚠ **⛔ 不手抄第二份 `sign_binom`** —— 复用 `arm_contrast_audit` 那个。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    import importlib.util
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


_SB = None


_SB_MEMO = {}
_SB_MEMO_CAP = 400000


def _sign_binom_cached(pos, n):
    """⛔⛔⛔⛔⛔⛔ **two-level cache**:
      1) exec that module **once** (still **reused**, ⛔ not a 2nd implementation)
      2) ⛔⛔ **value memo** -- `sign_binom` is pure arithmetic, so memo ⛔ **changes no number**

    ⛔⛔⛔⛔ ⛔ **round-2 defect found by mutation bench**:
      ⛔ 1st version only cached the module load. ⛔ mutation H2
      ⛔   (`m += 1` removed) makes `min_n_for` spin the **whole cap**,
      ⛔   and `sign_binom` is O(n) per call => O(n**3) total.
      ⛔   ⛔ **measured**: cap=200 -> 0.21s, cap=400 -> 5.01s.
      ⛔   ⛔ bench calls `min_n_for` 9x => **~an hour for one mutation**.
      ⛔ ✓=> the value memo collapses those repeats (pure fn, same numbers)
      ⛔   and `min_n_for`'s cap is now **400** (see its docstring for the reasoning).
    """
    global _SB
    key = (pos, n)
    hit = _SB_MEMO.get(key)
    if hit is not None:
        return hit
    if _SB is None:
        _SB = _load("arm_for_headroom", "arm_contrast_audit.py").sign_binom
    if len(_SB_MEMO) >= _SB_MEMO_CAP:
        _SB_MEMO.clear()            # ⛔ bounded; ⛔ never silently wrong
    _SB_MEMO[key] = _SB(pos, n)
    return _SB_MEMO[key]


def sb(pos, n):
    """⛖ 符号检验 p（双侧）。⛔ n ≤ 0 ⇒ 抛，⛔ 不许当 1.0。"""
    if n <= 0:
        raise HardFail("n=%d ⇒ 无分母，⛔ 拒算（不许当 p=1.0）" % n)
    return _sign_binom_cached(pos, n)


def cells_to_alpha(k, n, alpha=ALPHA):
    """⚖ 往**变差**方向走几格才越过 α。返回 `(m, k_at, p_at)`。

    ⚖⚠⚖⚖⚖⚖⚖⚖ **边界用 `<`：语义上 p ≥ α 就已经算越界** ⇒ 「还没越」
       的判据必须是 `p < alpha`。
    ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ **⛔⚠ 但在 α=0.05 下它是可证冗余的**：
       ⚖ `sign_binom` 的取值**永远是 S/2^(n−1)**（S 为整数；封顶的 1.0 也
         是这个形状）⇒ ⚖ p = 0.05 需要 2^(n−1)·0.05 = 2^(n−1)/20 为整数，
         而 **5 ∤ 2^(n−1)** ⇒ ⚖ ⛔ p **永远不等于** 0.05
       ⚖⇒ ⚠ `<` 与 `<=` **逐位等价** ⇒ ⚠⚠ **`<`→`<=` 是死变异**（台架 H1 已删）
    ⚖⚠⚖ `alpha_hits` 把这件事**钉成可核事实**（C2a），⛔ 而不是留成散文。
    ⚖⚠⚖⚖⚖⚖⚖ ⚖⚠⚠⚠ **第一版的理由是错的（此处已更正）**：我当时写
       「用 `<=` 会让 `cells(11,14)` 算成 1」⇒ ⚖ 实测 11/14 的 p=0.05737
       **本来就 > α** ⇒ ⚖ `<` 与 `<=` **都**给 **0** ⇒ ⛔「差一格」不存在，
       ⚖⚠⚠ 那是我**把话写圆了**（症状：我要一个能红的变异，理由是编的）。
    ⚖⚠ C2 真正守的是另一件事：**p ≥ α ⇒ 余量必须算 0**，⛔ 不许印成「还有一格」。
    """
    if not 0 <= k <= n:
        raise HardFail("k=%d 不在 [0,%d] ⇒ ⛔ 拒算" % (k, n))
    m, j = 0, k
    while j >= 0 and sb(j, n) < alpha:
        j -= 1
        m += 1
    return m, max(j, 0), (sb(max(j, 0), n) if j >= 0 else 1.0)


def alpha_hits(lo_n, hi_n, alpha=ALPHA):
    """⚖ 扫 n∈[lo_n,hi_n]、k∈[0,n]，数一数有几家 p **恰等于** alpha。

    ⚖⚠⚖⚖⚖⚖⚖⚖⚖⚠⚠⚠ **为什么要这个函数**：`<` vs `<=` 那条边界守卫在 α=0.05
      下**可证冗余**（见 `cells_to_alpha` 的 docstring）⇒ ⚠ 光靠散文说「永不
      相等」是不合格的，⚗⇒ **把它算出来**，报告与自检都印那个**实测数**。
    ⚖⚠⚖⚖ ⚖⚠⚠⚠⚠⚠⚠ **⛔ 这个扫描器不许空洞**：一个恒返回 0 的实现能让
      「命中 0 个」永远绿 ⇒ ⚗⇒ 必须同时有一个**能命中**的 α 来钉住它。
    ⚖ 返回 **具名 dict**（⛔ 不是裸元组）：解包顺序本轮已栽过一次，不给它机会。
    """
    if hi_n < lo_n:
        raise HardFail("hi_n=%d < lo_n=%d ⇒ 空区间，⛔ 拒算" % (hi_n, lo_n))
    pairs, hits = 0, []
    for n in range(lo_n, hi_n + 1):
        for k in range(0, n + 1):
            pairs += 1
            if sb(k, n) == alpha:
                hits.append((k, n))
    return {"n_pairs": pairs, "n_hits": len(hits), "pairs": hits}


def one_cell_ratio(k, n):
    """⚖ 掉**一格**会把 p 放大多少倍。`None` ⇒ 本来就不可算/无意义。

    ⚖⚠⚠⚠⚖⚖⚖⚖ **⛔ 绝不返回 1.0 冒充「不变」**：k=0 时掉一格不存在
    ⚖⚠⚠⚠⚖⚖⚖⚠ ⇒ 返回 None（未量到），⛔ 不是 1.0
    """
    if k <= 0:
        return None
    p0 = sb(k, n)
    p1 = sb(k - 1, n)
    if p0 is None or p1 is None:
        return None
    return p1 / p0 if p0 > 0 else None


def min_n_for(effect, margin, alpha=ALPHA, cap=400):
    """⚖ 要拿到 `margin` 格余量，n 至少多大（效应比例固定）。

    ⚖⚠⚠⚠⚖⚖⚖⚖⚖ **这是**事后**算的功效数字，⛔ 不是预登记所需样本量**：
       ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ 它假设**效应比例恰好等于观测值**；
       ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ ⚖ 若真效应更小，所需 n **更大**（0.75 那行就是证据）。
    ⚗⇒ 报它是为了说明「**当前设计差多少**」，⛔ 不是「这样就够」了。
    ⛔⛔⛔⛔⛔⛔⛔⛔ **why cap = 400 (changed by measurement, not by taste)**:
    ⛔ round 1 wrote `cap=2000`. ⛔⛔ mutation H2 (`m += 1` removed)
    ⛔   => `m` is always 0 => the loop spins the **whole cap**;
    ⛔   and `sign_binom` is O(n) per call => **O(n**3)** total.
    ⛔   ⛔ **measured**, one `min_n_for(0.857, 2)` under H2:
    ⛔     cap=200 -> **0.21s** | cap=400 -> **5.01s** | cap=2000 -> minutes
    ⛔⛔ bench C5 calls it 3x and the report 6x => ⛔⛔ **one mutation took ~an hour**;
    ⛔⛔ the whole bench looked **hung**.
    ⛔ ✓=> **400**: ⛔⛔ the **largest real answer** over
    ⛔   `EFFECTS`×`MARGINS` is only **n=25** => 400 still leaves
    ⛔   **16x** headroom while cost drops to seconds.
    ⛔⛔ **do not flip this the other way**: ⛔ never cut cap to ~26
    ⛔⛔ just to run fast -- that makes the "real effect smaller, needs
    ⛔⛔ bigger n" branch **unreachable**, and `HardFail` is that branch's
    ⛔⛔ only visible signal.
    """
    for n in range(5, cap + 1):
        k = int(round(effect * n))
        k = min(max(k, 1), n - 1)               # 至少留一格可掉
        if cells_to_alpha(k, n, alpha)[0] >= margin:
            return n, k, sb(k, n)
    raise HardFail("到 n=%d 仍达不到 %d 格余量 ⇒ ⛔ 拒算" % (cap, margin))


def headroom_is_not_a_verdict():
    """⚖⚖ **恒返回 False 的禁令**，且它**必须**恒返回 False。

    🔴 244.43 实测：账本里 4 个被当作「显著」的判决，余量全是 **1–2 格**。
       ⚖⚠⚖⚖⚖ 一半的人会顺手写成「这些判决**站不住**/应当撤回」。
    ⚖⚠⚖⚖⚖⚖⚖ 那**方向正好相反**：
       ⚖ **余量小** = 「**离阈值只有一格**」⇒ 行动含义是「**报告时必须带上这一格**」
       ⚖ **判决无效** = 「这个结论不成立」⇒ ⛔ 余量**完全不支持**这个说法
    ⚖⚠⚖⚖⚖⚖⚖ ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠
    ⚖⚠⚖⚖⚖⚖⚖ ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠
    ⚖ 同一件事的另一面：⛔ 余量小也**不**许被引用成「所以 rand 那 12/14 是噪声」
       —— 那是 244.37–244.42 反复登记的三条禁令之一（p ≥ 0.05 / 未量到 / 稳）。
    """
    return False


# --------------------------------------------------------------- 主流程
def run():
    L = []
    L.append("【1】账本里每一个**计数型**判决的格数余量（p 与 α 都是**同一个**符号检验）")
    L.append("  ⚖ α = %.2f；⚖⚠ 余量 = 往**变差**方向走几格才越过 α" % ALPHA)
    L.append("  ⚖⚠⚠⚠⚖⚠ 期望值与账本**逐字一致**，⛔ 本工具不改任何数")
    L.append("")
    L.append("  %-22s %-8s %-11s %-9s %-22s %s"
             % ("判决", "k/n", "p", "余量", "首次越界", "一格 = 几倍 p"))
    nsig, margins, sig_margins = 0, [], []
    for tag, k, n, _tier in VERDICTS:
        p = sb(k, n)
        m, ka, pa = cells_to_alpha(k, n)
        ratio = one_cell_ratio(k, n)
        sig = p < ALPHA
        nsig += 1 if sig else 0
        margins.append(m)
        if sig:
            sig_margins.append((tag, m))
        L.append("  %-22s %-8s %-11.5f %-9s %-22s %s"
                 % (tag, "%d/%d" % (k, n), p,
                    "**%d 格**" % m if sig else "已越界",
                    ("%d/%d p=%.4f" % (ka, n, pa)) if sig else "—",
                    ("%.1f 倍" % ratio) if ratio else "—"))
    L.append("")
    L.append("  ⚖⚠⚠⚠⚖⚠⇒ 被当作「显著」的判决共 **%d** 个" % nsig)
    # ⚖⚠⚖⚖⚖⚖⚖⚖⚖ 第一版我写 `margins[:nsig]` ⇒ **把已越界的 0 格也混进来了**
    #   ⇒ 印成「2 格、0 格、1 格、0 格」⛔ 而**显著**的那四个是 2/1/1/1
    #   ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠ ⚖⚠ **症状**看着像「有的显著只有 0 格余量」，
    #   ⚖⚠⚠⚠⚠⚠⚖⚠⚠⚠ ⚖⚠⚠⚠⚠ **病因**是「收集时没按显著性过滤」
    L.append("     ⚖⚠⚠ 它们的余量（**只列显著的**）：**%s**"
             % ("、".join("%s %d 格" % (t, m) for t, m in sig_margins) if nsig else "（无）"))
    L.append("     ⚖⚠⚠⚠ **无一例外 ≤ %d 格** ⇒ ⚖ **一格扰动就能翻面**"
             % max([m for _t, m in sig_margins]) if nsig else "")
    scan = alpha_hits(1, SCAN_HI)
    L.append("  ⚖ 边界守卫**可证冗余**（α=%.2f 下 p 永不恰等于 α）："
             "扫 n=1..%d 的 %d 个 (k,n) 对"
             % (ALPHA, SCAN_HI, scan["n_pairs"]))
    L.append("     ⇒ p **恰等于** α 的有 **%d** 个 ⇒ %s"
             % (scan["n_hits"],
                "`<` 与 `<=` **逐位等价** ⇒ ⛔ 别拿它当变异（死变异，台架已删）"
                if scan["n_hits"] == 0 else
                "**存在恰相等的 (k,n)** ⇒ 边界守卫**承重**，不许删"))

    L.append("")
    L.append("【2】n=14 逐格读（⚖ 这是**通性**，不是某一档的特性）")
    L.append("  %-10s %-9s %-11s %s" % ("k/n", "比例", "p", "余量"))
    for k in range(10, 15):
        p = sb(k, 14)
        L.append("  %-10s %-9.3f %-11.5f %s"
                 % ("%d/14" % k, k / 14.0, p,
                    "**%d 格**" % cells_to_alpha(k, 14)[0] if p < ALPHA else "已越界"))
    L.append("  ⚖⚠⚠⚠⚖⚠⇒ **12/14 只买 1 格**；⚖⚠ 要 **2 格**余量，n=14 下")
    L.append("     必须强到 **13/14 = 0.929** ⇒ ⚖⚠⚠⚠⚠ **这个题库只有 14 个问题**")
    L.append("     ⚖⚠⚠⚠⚠⚠ ⇒ ⚖⚠⚠ **任何比例型符号判决在这里最多 2 格余量**")

    L.append("")
    L.append("【3】要多少 n / 多强的效应才够（⚠⚠ **事后**算的，⛔ 不是预登记样本量）")
    L.append("  %-26s %-10s %-10s %-10s" % ("效应比例", "要 1 格余量", "要 2 格", "要 3 格"))
    for eff in EFFECTS:
        cellsrow = []
        for m in MARGINS:
            try:
                n, k, p = min_n_for(eff, m)
                cellsrow.append("n≥%d" % n)
            except HardFail:
                # ⚖⚠⚠⚠ **报告不许因为算不出来就崩** —— 台架 H2（`m` 恒 0）
                #   会让 `min_n_for` 转满 cap 后 `raise` ⇒ ⚠⚠ 整个 `run()`
                #   崩掉 ⇒ 台架报「崩」⛔ 而「崩 ≠ 抓到」，信号就没了。
                # ⚖ ⇒ 这里印「**未量到**」：⚖ 「没量到」是**事实**，⛔ 不是「无解」
                cellsrow.append("**未量到**")
        L.append("  %-26s %-10s %-10s %-10s"
                 % ("%.3f%s" % (eff, "（= 12/14）" if abs(eff - 0.857) < 1e-9
                                else "（更弱）"), cellsrow[0], cellsrow[1], cellsrow[2]))
    L.append("  ⚖⚠⚠⚠⚠⚠ ⇒ 效应**弱一截**（0.857→0.75）所需 n **涨得很快**")
    L.append("     ⚖ cap=400；⚖ `EFFECTS`×`MARGINS` 的**最大真答案是 n=25**（余量 16 倍）")
    L.append("     ⇒ ⚖⚠⚠ 事后拿观测效应去算的功效**必然乐观** ⇒ ⛔ 别拿它当样本量")

    L.append("")
    L.append("【4】⛔ 三条必须一起说的禁令")
    L.append("  ⚖⚠⚖ 余量小 ⛔ **不等于**「判决无效」⇒ 禁令 %s"
             % ("生效" if headroom_is_not_a_verdict() is False else "⛔ 失效"))
    L.append("     ⚖ 它只说「**离阈值只有一格**」⇒ 行动含义是「**报告必须带上这一格**」")
    L.append("  ⚖⚠⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠ **rep_n≥2 解决不了本节的问题**")
    L.append("     ⚖ rep_n 量的是**格内噪声**，⛔ 它**不改变 k/n**")
    L.append("     ⚖⚠⚠⇒ 余量只由 **n** 与**效应量**决定 ⇒ ⚠ 要加余量只能改**设计**")
    L.append("  ⚖⚠⚖⚠⚠⚠⛔ 余量小也**不**许被引用成「所以那个 12/14 是噪声」")
    L.append("     ⚖⚠⚠⚠⚠⚠⚖ 那是 244.37–244.42 连续登记的三条禁令（p ≥ 0.05 /")
    L.append("     未量到 / 稳 ⛔ 不等于 不是噪声）；**rep_n ≥ 2 仍然必需**")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # C1 🔴 逐格读的字面量（⛔ 不从被测函数算）
    chk("C1", cells_to_alpha(12, 14)[0] == 1 and cells_to_alpha(13, 14)[0] == 2
        and cells_to_alpha(14, 14)[0] == 3 and cells_to_alpha(11, 14)[0] == 0,
        "n=14：12/14⇒%d 格、13/14⇒%d、14/14⇒%d、**11/14⇒%d（已越界）**"
        % (cells_to_alpha(12, 14)[0], cells_to_alpha(13, 14)[0],
           cells_to_alpha(14, 14)[0], cells_to_alpha(11, 14)[0]))

    # C2 🔴 **已越界的那一格**：p ≥ α ⇒ 余量必须算 **0**，⛔ 不许印成「还有一格」
    #   ⚖⚠⚖⚖⚖⚖ ⚖⚠ **⛔ 它不是在守 `<` vs `<=`**（那在 α=0.05 下可证冗余，见
    #   `cells_to_alpha` 的 docstring + C2a）⇒ ⚖⚠ 我第一版**把理由写错了**，
    #   ⚖⚠⚠ 而错因是「我需要一个能红的变异」⇒ 修法是**承认它冗余并删掉那条变异**。
    p11 = sb(11, 14)
    chk("C2", p11 >= ALPHA and cells_to_alpha(11, 14)[0] == 0,
        "11/14 的 p=%.5f ≥ α=%.2f ⇒ 余量必须是 **0**（实测 %d）"
        % (p11, ALPHA, cells_to_alpha(11, 14)[0]))

    # C2a 🔴🔴 「p 永不恰等于 α」**钉成可核事实** + 扫描器**不许空洞**
    #   ⚖⚠⚖⚖⚖⚖ ⚖⚠ **两个方向都要能红**，否则这条只是恒绿的散文：
    #     ① n=1..60 的 1890 个 (k,n) 对里，p **恰等于** 0.05 的 = **0** 个
    #     ② ⛔ 恒返回 0 的扫描器会让 ① 永远绿 ⇒ ⚖ 用 **p 恰等于 1.0** 的
    #        个数 > 0 把它钉住（1.0 可达 ⇒ 证明扫描器真在扫）
    sc = alpha_hits(1, SCAN_HI)
    hit10 = alpha_hits(1, SCAN_HI, 1.0)["n_hits"]
    chk("C2a", sc["n_pairs"] == 1890 and sc["n_hits"] == 0 and hit10 > 0,
        "n=1..%d 共 %d 个 (k,n) 对 ⇒ p 恰等于 α=0.05 的 **%d** 个（⇒ `<`/`<=` "
        "可证冗余）；⚠ 扫描器**非空洞**：p 恰等于 1.0 的有 %d 个"
        % (SCAN_HI, sc["n_pairs"], sc["n_hits"], hit10))

    # C3 🔴 一格 = 多少倍 p（字面量 4.4 倍）
    r = one_cell_ratio(12, 14)
    chk("C3", abs(r - 4.4347) < 1e-3 and one_cell_ratio(0, 14) is None,
        "12/14 掉一格：%.4f → %.4f = **%.2f 倍**；k=0 ⇒ %s（⛔ 不是 1.0）"
        % (sb(12, 14), sb(11, 14), r, one_cell_ratio(0, 14)))

    # C4 ⚖ 参数守卫：k 越界 / n=0 ⇒ 抛，⛔ 不许当 p=1.0
    def raised(fn):
        try:
            fn()
            return False
        except HardFail:
            return True
    chk("C4", raised(lambda: sb(1, 0)) and raised(lambda: cells_to_alpha(15, 14))
        and raised(lambda: cells_to_alpha(-1, 14))
        and raised(lambda: alpha_hits(10, 5)),
        "n=0 ⇒ 抛；k>n ⇒ 抛；k<0 ⇒ 抛；空区间 ⇒ 抛（四次都抛）")

    # C5 🔴 `min_n_for` 的字面量：效应 0.857 要 2 格余量 ⇒ n ≥ 15
    # 🔴 ⛔⛔ **判据不许因为被测物抛异常而崩**：
    #   ⚖ 台架 H2（`m += 1` 被拆 ⇒ m 恒 0）会让 `min_n_for` 转满
    #   cap 后 `raise HardFail` ⇒ ⚠⚠ 自检**整个崩掉**，台架报
    #   「崩」⚠⚠ 而「崩 ≠ 抓到」⇒ ⚠ 恰好丢掉「哪条判据抓到的」这个信号。
    #   ✓⇒ 这里**吃掉异常**、把结果降级成 None，让 C5 **转红而不是崩**。
    #   ⚠⚠⚠⚠⚠⚠ ⚠⚠ **这不许被读成「异常可以无视」**：
    #   `min_n_for` 真实抛错时 C5 会红（None ≠ 15）⇒ ⚠ 异常照样被抓，只是
    #   ✓ 换了个报告方式。
    def _mnf(eff, m):
        try:
            return min_n_for(eff, m)
        except HardFail:
            return None

    r2, r1, r2w = _mnf(0.857, 2), _mnf(0.857, 1), _mnf(0.75, 2)
    n2 = r2[0] if r2 else None
    k2 = r2[1] if r2 else None
    p2 = r2[2] if r2 else None
    n1 = r1[0] if r1 else None
    n2w = r2w[0] if r2w else None
    chk("C5", n2 == 15 and n1 == 9 and n2w == 25,
        "效应 0.857：1 格⇒n≥%s、2 格⇒**n≥%s**（k=%s, p=%s）；"
        "效应 0.75：2 格⇒n≥**%s**" % (n1, n2, k2, p2, n2w))

    # C6 ⚖ 禁令恒 False
    chk("C6", headroom_is_not_a_verdict() is False,
        "余量小 ⛔ 不等于「判决无效」⇒ 禁令恒 False")

    # C7 ⚖⚖ 报告字面量：**恒印**的那些必须真的印在报告里
    Lr = run()[0]
    always = ("【1】账本里每一个**计数型**判决", "【2】n=14 逐格读",
              "【3】要多少 n", "【4】⛔ 三条必须一起说的禁令",
              "无一例外 ≤ 2 格", "12/14 只买 1 格", "只列显著的",
              "p **恰等于** α 的有 **0** 个",
              "禁令 生效",            # ⚠⚠ 替掉被删掉那半条：见下面的理由
              )
    # 🔴⛔⛔ **本条原有两半，其中「查源码」那半已被删除** —— 理由写原地：
    #   ⚖ 它形如 `x = ("某段源码字面量", ...)`；`ms = [x for x in ... if x not in src]`。
    #   ⚖⚠⚠⚠ **而 `x` 自己就在 `src` 里**（它就写在下一行）⇒ `x not in src`
    #   **恒为假** ⇒ 这半条判据**在任何源码状态下都绿** ⇒ **原理上无法变红**。
    #   ⚖⚠⚠⚠ 这不是「needle 选得不好」：⚖ **任何**在源码里搜字面量的写法都逃不掉
    #   这条（把字面量挪到别处也还是「判据自己满足判据」）。
    #   ⚖⚠⚠⚠ 现场证据（台架 H9）：我第一版取 `... is False else`、第二版取
    #   「含引号的全文」⇒ ⚠ 两次都因为**同一段字面量在别处还有副本**而存活；
    #   ⚠ 而第三次看清了：**副本就是判据自己** ⇒ 再怎么取都白搭。
    #   ✓ 改成**正向**断言：报告必须印出 `禁令 生效` ⇒ 变异把条件写反时它变成
    #   「⛔ 失效」⇒ C7 转红。⚖ 正向断言查的是**被测产物**，⛔ 不自指。
    mr = [x for x in always if x not in Lr]
    chk("C7", not mr,
        "报告恒印缺 %s（⛔「查源码」那半已删：它恒绿，理由见上方）"
        % ("无" if not mr else mr))

    # C8 🔴🔴 端到端：判决清单必须**逐字**复现账本的值（⛔ 不许被工具改掉）
    # 🔐🔐 **端到端：判决清单必须**逐行**复现账本的值**（⛔ 不许从 VERDICTS 算）
    #   ⚖⚖⚖ **本条第一版太弱，台架 H10 当场拆穿**：它只查 4 个值
    #   （13/14 / 6/14 / 7/7 / 12/14）⇒ ⚠⚠ 把「预登记主统计量 w」的 k 从 12 改成 11，
    #   ⚖ 那个 12/14 由**别的行**提供 ⇒ C8 仍绿 ⛔ 而 C9 红了。
    #   ⚠⚠⚠⚠⚠⚠ ⚠⚠ 「核心里抽查 4 个」≠「清单逐字复现」
    #   ⇒ ✓ 现在**十行全列**，且每个 k/n 都是**字面量**。
    # ⚠⚠⚠⚠⚠ **修订 244.55 登记的限定（写在原地，⛔ 别删）**：
    #   ⚖ 本条的期望清单 `want8` 与被检的 `VERDICTS` 是**同一个手抄来源**
    #   ⇒ ⚠⚠⚠ **它原理上抓不到「两边一起抄错」**（244.55 实测：两处**同时**写成
    #   ⚖   `(5, 9)`，C8 全绿 ⇒ 直到 244.55 才发现「轨迹级 rand p=1.00000」）
    #   ⇒ **真正的独立守卫**在 `.cache/r244/verdict_source_audit.py` 的 **C8**：
    #   ⚖   它从**读数重算**那 6 行，再与本表**逐行对账** ⇒ 两端不同源。
    #   ⚖ 本条**保留**（它守的是「报告没印出那十行」这一件不同的事），
    #   ⚖   但**不许**把它当成「抄错抓得到」的证据。
    want8 = [("轨迹级 w", 13, 14),
              # ⚖⚠⚠⚠ **修订 244.55 更正**：这里**原来**写的是 `(5, 9)`
              #   ⇒ 那是把「5 正 / 9 负」的**负数**当成**样本量**
              #   ⇒ 与上面 VERDICTS 的误印**同源**（同一个手抄错误）
              ("轨迹级 rand", 5, 14),
              ("问题级 w", 7, 7),
              ("问题级 rand", 2, 7),
              ("预登记主统计量 w", 12, 14),
              ("预登记主统计量 rand", 6, 14),
              ("传播层 w（244.37）", 9, 14),
              ("传播层 rand（244.37）", 12, 14),
              ("传播层 w 直接层", 6, 7),
              ("传播层 rand 直接层", 5, 7)]
    miss8 = ["%s %d/%d" % (t, k, n) for t, k, n in want8
             if ("%-22s %-8s" % (t, "%d/%d" % (k, n))) not in Lr]
    chk("C8", not miss8 and Lr.count("轨迹级 rand") == 1,
        "判决清单**十行**必须逐字复现账本：缺 %s；轨迹级 rand 出现 %d 次（⛔ 恰好 1）"
        % (miss8, Lr.count("轨迹级 rand")))

    # C9 🔐🔐 **「显著判决的余量」必须只含显著的那些（字面量）
    #   ⛔⛔ 第一版我写 `margins[:nsig]` ⇒ **把已越界的 0 格也混进来**
    #   ⇒ 印成「2 格、0 格、1 格、0 格」⇒ ⚠ **病毒是「没按显著性过滤」**
    #   ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠ ⚖⚠ **另一个自己写的坑**：我给每个片段都加了 `**`，
    #   ⚖ ⚠ 报告里 `**` 只在**整行首尾**，中间用 `、` 相连 ⇒ 拼一起来就**对不上**
    need9 = ("轨迹级 w 2 格", "问题级 w 1 格",
             "预登记主统计量 w 1 格", "传播层 rand（244.37） 1 格")
    chk("C9", all(x in Lr for x in need9) and "轨迹级 rand 0 格" not in Lr,
        "「只列显著的」那行必须是 2/1/1/1（逐片段字面量），⛔ 不许混入已越界的 0 格")
    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="判决的格数余量（零 GPU 纯算术）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    txt, rc = run()
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
