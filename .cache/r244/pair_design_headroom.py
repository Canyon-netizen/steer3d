#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pair_design_headroom.py —— 配对设计到底能买到几格余量？（纯算术，零 GPU）

🔴 **这个工具要回答什么**（修订 244.44）
  ⚖⚠⚠⚠ 244.43 已证：**n=14 下账本里每个「显著」判决都只有 1–2 格余量**。
  ⚖⚠⚠⚠⚠⚠⚠⚠⚠ **待批的那个方案叫「配对阶梯」** ⇒ 有一个数字**必须在批之前算**：
  ⚖ 换成配对之后，**判决的分母变成几？余量变成几？**

⚖⚠⚠⚠⚠⚠⚠⚠ **核心结构事实（这决定了全部结论）**
  ⚖ **McNemar 只用「不一致对」**（`b` 与 `c` 两格）⇒ 它的**有效分母是 d = b + c**，
  ⚖ ⛔ **不是**题库大小 N。⚖⚠ 「一致对」（both+/both−）在配对设计里**不携带**差异信息。
  ⚖⚠⚠⇒ **配对必然把分母从 N 缩到 d ≤ N。**

⚖⚠⚠⚠⚖⚠⚖⇒ ⚠⚠⚠⚠⚠⚠ **本节实测的主结论**
  ⚖ **在同一个方向比例下，配对的余量 ≤ 不配对的余量**，且 d 越小越差。
  ⚖ ⇒ ⚠⚠ **配对本身买不到余量。** 它买的是**测量精度**（信号 vs 台阶的比值），
  ⚖ ⛔ 那是**另一件事**，⛔ 不许混进「判决脆不脆」里。

⚖⚠⚠⚠⚖⚠⚖⇒ ⚠⚠ 要 2 格余量，在 n=14 下必须 **≥ 13/14 = 0.929** 一致
  （244.43 已证，本节**独立复核**）。

⚖⚠⚠⚠ **⛔ 本节没回答、也回答不了的**
  ⚖ 「配对**能不能提高一致性**」是**未测量的经验问题** ⇒ 本节给的是**条件结论**，
  ⚖ ⛔ 不是「配对能行」或「配对不行」。

⛔ 本工具：⛔ 不改任何真文件；⛔ 不跑批；⛔ 只做算术（⛔ 不读日志、不读探针输出）。
"""

import argparse
import os
import sys

ALPHA = 0.05
N_ITEMS = 14                      # ⚖ 账本题库的**问题数**，⚠ 字面量
KEEP_FRACS = (0.60, 0.75, 0.90)   # ⚖ 配对后「保留多少不一致对」的扫描点
RATIOS = (0.70, 0.75, 0.80, 0.857, 0.90)
MARGINS = (1, 2)
D_CAP = 200                        # ⚖ `min_d_for` 的搜索上限


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 复用（⛔ 不手抄第二份）
def _load(modname, fname):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读" % path)
    import importlib.util
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


_HA = None


def ha():
    global _HA
    if _HA is None:
        _HA = _load("ha_for_pair", "headroom_audit.py")
    return _HA


def cells_to_alpha(k, n, alpha=ALPHA):
    """⚖ 往**变差**方向走几格才越过 α。⛔ **直接复用** headroom_audit 那一份。"""
    return ha().cells_to_alpha(k, n, alpha)


def sb(pos, n):
    """⚖ 符号检验 p。⛔ 同样复用，⛔ 不在本文件里重写公式。"""
    return ha().sb(pos, n)


def discordant_n(n_items=N_ITEMS, keep=1.0):
    """⚖ 配对之后**留下多少不一致对** d。

    ⚖⚠ `keep` 是「多少比例的对真的不一致」这个**未测量**的经验量
    ⚖ ⇒ ⚖⚠⚠ 本函数只是把那个量**参数化**，⛔ 它**不预测**真实取值。
    ⚖⚠⚠⚠⚠⚠⚠ **守卫**：keep ∉ (0,1] ⇒ 抛，⛔ 不许默默夹到范围里
    ⚖ （默默 clamp 会让「keep=5」看起来合法，而那在现实中不存在）。
    """
    if not 0 < keep <= 1:
        raise HardFail("keep=%r ∉ (0,1] ⇒ ⛔ 拒算（不许悄悄 clamp）" % (keep,))
    if n_items <= 0:
        raise HardFail("n_items=%d ⇒ 无题库，⛔ 拒算" % n_items)
    d = int(round(n_items * keep))
    return max(d, 2)                 # ⚖ d<2 ⇒ McNemar 根本算不出东西 ⇒ 记 2


def pair_margin(d, ratio, alpha=ALPHA):
    """⚖ 配对设计（McNemar）在 d 个不一致对、方向比例 ratio 下的余量。

    ⚖⚠⚠⚠⚠⚠ **关键一步：McNemar 的 p 只由 (b, c) 决定**，
      而 `mcnemar_exact(b, c) = sign_binom(min(b,c), b+c)`
      ⇒ ⚖ **它与「不配对的符号检验」在数学上是同一个函数**，只是分母不同。
    ⚖⚠⚠ ⚖⚠ **所以本函数 ⛔ 不重写 McNemar**，⚗ 而是**把分母换成 d**
      再调同一个 `cells_to_alpha` ⇒ ⛔ 两处实现漂移的可能。
    """
    if d < 2:
        raise HardFail("d=%d ⇒ 不一致对太少，McNemar 无意义，⛔ 拒算" % d)
    if not 0 < ratio <= 1:
        raise HardFail("ratio=%r ∉ (0,1] ⇒ ⛔ 拒算" % (ratio,))
    b = int(round(ratio * d))
    b = min(max(b, 1), d - 1)        # ⚖ 至少留一格可掉（与 headroom 同口径）
    m, ka, pa = cells_to_alpha(b, d, alpha)
    return {"d": d, "b": b, "p": sb(b, d), "margin": m, "k_at": ka, "p_at": pa}


def min_d_for(ratio, margin, alpha=ALPHA, cap=D_CAP):
    """⚖ 要拿到 `margin` 格余量，**不一致对数 d** 至少多大。

    ⚖⚠⚠⚠⚠⚠ **这是条件结论，不是预测**：它说的是「**若**方向比例是 ratio，
    ⚖   **则** d 至少要这么多」；⚖⚠⚠ 而真实 d ⛔ **尚未测量**。
    ⚖⚠⚠⚠⚠⚠⚠ **⛔ 本函数绝不能被读成「d 会达到这么多」** ⇒ 禁令见下。
    """
    if margin < 0:
        raise HardFail("margin=%d 为负 ⇒ ⛔ 拒算" % margin)
    if not 0 < ratio <= 1:
        raise HardFail("min_d_for: ratio=%r ∉ (0,1] ⇒ ⛔ 拒算（**本函数**的守卫）"
                     % (ratio,))
    for d in range(2, cap + 1):
        r = pair_margin(d, ratio, alpha)
        if r["margin"] >= margin:
            return d, r["b"], r["p"]
    raise HardFail("到 d=%d 仍达不到 %d 格余量 ⇒ ⛔ 拒算" % (cap, margin))


def pairing_is_not_more_headroom():
    """⚖⚖ **恒返回 False 的禁令**：⛔ **不许**把「配对」说成「更稳」。

    ⚖⚠⚠⚖⚠⚠⚖ **实测依据**：同一方向比例 0.857 下，分母从 14 缩到 d
      ⇒ 余量 **14→1 格、12→1、10→1、8→0** ⇒ ⚖⚠⚠ **缩分母只会更差**。
    ⚖⚠⚠⚥⚠⚠⚠ **一半的人会说「配对能降方差，所以更稳」** ⇒ ⚖⚠⚠⚠⚠⚠⚠
      **那句话说的是「测量精度」，⛔ 与「判决的格子余量」是两件事。**
      ⚖ 配对阶梯买的是前者（信号 vs 台阶的量级比），⚖ ⛔ **不是**后者。
    ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠
    ⚖⚠⚠ ⚖⚠ 另一面：⚖⚠ **「配对买不到余量」⛔ 也不等于**「配对没用」
    ⚖⚠ ⇒ 它对**测量精度**仍然可能是正解，⛔ 只是**不解决余量**这条。
    """
    return False


def unpaired_margin(k, n=N_ITEMS, alpha=ALPHA):
    """⚖ 不配对的基准（⚖ 账本现状：14 个问题里 12 个正号）。"""
    m, ka, pa = cells_to_alpha(k, n, alpha)
    return {"n": n, "k": k, "p": sb(k, n), "margin": m, "k_at": ka, "p_at": pa}


# --------------------------------------------------------------- 主流程
def run():
    L = []
    L.append("【1】三种候选设计的**有效分母**各是什么（⚖ 这一栏决定了全部结论）")
    L.append("  %-34s %-14s %s" % ("设计", "有效分母", "为什么"))
    L.append("  %-34s %-14s %s" % ("现状：不配对，符号检验", "N = %d" % N_ITEMS,
             "每个问题各贡献 1 格"))
    L.append("  %-34s %-14s %s" % ("配对 + McNemar", "d ≤ %d" % N_ITEMS,
             "⚠ 只用**不一致对**；一致对不携带差异信息"))
    L.append("  %-34s %-14s %s" % ("配对阶梯（相邻档配对）", "N = %d" % N_ITEMS,
             "⚖ 每对都产出一个方向 ⇒ 没有「一致对」可丢"))
    L.append("  ⚖⚠⚠⚖⚖⚖⇒ ⚠⚠⚠⚠⚠ **只有中间那行会把分母变小** ⇒ ⚖⚠⚠⚠ "
             "另外两行分母都是 %d" % N_ITEMS)

    L.append("")
    L.append("【2】**缩分母 ⇒ 余量变差**（同一方向比例 0.857 = 12/14，实测）")
    L.append("  %-10s %-10s %-12s %s" % ("分母 n", "k", "p", "余量"))
    for n in (14, 12, 10, 8, 6, 5, 4):
        k = max(1, min(n - 1, int(round(0.857 * n))))
        r = unpaired_margin(k, n)
        L.append("  %-10s %-10s %-12.5f %s"
                 % ("%d" % n, "%d/%d" % (k, n), r["p"],
                    "**%d 格**" % r["margin"] if r["margin"] else "已越界"))
    L.append("  ⚖⚠⚖⚖⚖⚠⚠⚠⚠⚠⚠ ⇒ ⚠⚠⚠ **分母从 14 缩到 8 ⇒ 余量从 1 格掉到 0 格**")
    L.append("  ⚖⚠⚖⚖⚖⚖⚖⚖ ⚖⚠⚠⚠⚠⚠⇒ ⚠⚠⚠⚠⚠⚠ **配对只会让分母变小或不变**")

    base = unpaired_margin(12, N_ITEMS)
    L.append("")
    L.append("【3】基准：现状 12/%d = %.3f，p=%.5f，**余量 %d 格**"
             % (N_ITEMS, 12.0 / N_ITEMS, base["p"], base["margin"]))
    L.append("  ⚖⚠ 首次越界是 %d/%d（p=%.4f）⇒ 掉一格即越过 α"
             % (base["k_at"], N_ITEMS, base["p_at"]))

    L.append("")
    L.append("【4】⚠ 要 **2 格**余量，**不一致对 d** 至少要多少（⚠⚠ **条件结论**）")
    L.append("  %-14s %-16s %-24s %s" % ("方向比例", "2 格需 d", "占 14 题的", "在本题库可达吗"))
    for r in RATIOS:
        dneed, bneed, _ = min_d_for(r, 2)
        frac = float(dneed) / N_ITEMS
        L.append("  %-14s %-16s %-24s %s"
                 % ("%.3f" % r, "d ≥ %d（b=%d）" % (dneed, bneed),
                    "%.0f%%（d=%d）" % (100 * frac, dneed),
                    "✅ 可达" if dneed <= N_ITEMS else "⛔ **不可达**"))
    L.append("  ⚖⚠⚠⚖⚖⚖⚖⚖⚖⇒ ⚠⚠⚠⚠ **在 0.857 这个比例上 2 格不可达**（需要 d≥15 > 14）")
    L.append("  ⚖⚠⚠ ⚖⚠⚠⚠ 要 2 格只有两条路：⚖ 方向比例推到 **≥ 0.929**，"
             "或 ⚖ 题库 n 加大")
    L.append("     ⚖⚠ n=14 下 13/14 = 0.929 **就是** 2 格（实测 p=%.5f）"
             % sb(13, N_ITEMS))

    L.append("")
    L.append("【5】⛔ 三条必须一起说的禁令")
    L.append("  ⚖⚠⚖ ⚖⚠ **不许**说「配对更稳所以判决更可靠」⇒ 禁令 %s"
             % ("生效" if pairing_is_not_more_headroom() is False else "⛔ 失效"))
    L.append("     ⚖ 配对买的是**测量精度**（信号 vs 台阶的量级比），"
             "⛔ **不是**格子余量")
    L.append("  ⚖⚠⚖⚠⚠⚠ ⚖⚠⚠ 「d≥15」是**条件结论**，⛔ **不是**「d 会到 15」：")
    L.append("     ⚖⚠⚠ 真实 d ⛔ **尚未测量** ⇒ 本节给的是「**若**比例是 r，**则** d 至少多少」")
    L.append("  ⚖⚠⚖⚠⚠⚠⚠⚠⚠⚠ **⛔ 本节没有回答「配对能不能提高一致性」**")
    L.append("     ⚖⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚖ 这是**未测量的经验问题** ⇒ ⛔ 本节既没说「行」也没说「不行」。")
    return "\n".join(L), 0


# --------------------------------------------------------------- 自检
def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # C1 🔴 配对余量的字面量（⛔ 不从被测函数算）
    r6 = pair_margin(6, 0.857)
    r4 = pair_margin(4, 0.857)
    r14 = pair_margin(14, 0.857)
    # ⚖⚠⚠⚠ **ratio=1.0 这个夹具不许省**：`b = round(1.0*d) = d` ⛔ 不是合法 k
    # ⚖⚠⚠⚠ ⇒ ⛔ **没有** `min(..., d-1)` 的话它会变成 d/d，而 d/d 的余量是 1 格
    # ⚖⚠⚠⚠ ⇒ ⚠ 那个夹取一旦被拆，数字就变 ⇒ 判据必须夹到它。
    rfull = pair_margin(4, 1.0)
    chk("C1", r6["margin"] == 0 and r4["margin"] == 0 and r14["margin"] == 1
        and r14["b"] == 12 and rfull["b"] == 3 and rfull["margin"] == 0,
        "比例 0.857：d=14⇒b=%d 余量 **%d 格**；d=6⇒b=%d 余量 %d；d=4⇒b=%d 余量 %d"
        % (r14["b"], r14["margin"], r6["b"], r6["margin"], r4["b"], r4["margin"]))
    chk("C1b", rfull["b"] == 3 and rfull["margin"] == 0,
        "**上界夹取**必须承重：d=4 ratio=1.0 ⇒ b 被夹到 **%d**（⛔ 不是 4），余量 %d 格"
        % (rfull["b"], rfull["margin"]))

    # C2 🔴🔴 端到端：报告里那三行**分母**必须原样出现（⛔ 不许被改口径）
    Lr = run()[0]
    need = ["N = 14", "d ≤ 14", "只有中间那行会把分母变小"]
    miss = [x for x in need if x not in Lr]
    chk("C2", not miss, "报告必须印出三种设计的分母：缺 %s" % miss)

    # C3 🔴 `min_d_for` 的字面量
    #   🔴 ⛔⛔ **判据不许因为被测物抛异常而崩**（244.43 的 H2 同款，本轮 J6/J7 复现）：
    #     台架把 `>= margin` 收紧、或把 `range(2, cap+1)` 写成 `range(2, cap)`，
    #     都会让下面这个 **cap=15 恰等于答案** 的边界夹具**抛** ⇒ ⚠⚠ 整个 selftest 崩掉，
    #     台架只能报「崩」⛔ 而「崩 ≠ 抓到」⇒ ⚠ 恰好丢掉「是哪条判据抓到的」。
    #     ⇒ 这里吃异常、降级成 None，让 C3 **转红而不是崩**。
    #   ⚠⚠⚠ **别把它读成「异常可以无视」**：真抛错时 None ≠ 15 ⇒ C5 照样红。
    def _mdf(*a, **kw):
        try:
            return min_d_for(*a, **kw)
        except HardFail:
            return None
    # ⛔⛔ **先整体接住返回值**，⛔ 不要直接解包
    # ⛔⛔ （`_mdf` 可能返回 None ⟨直接解包会 TypeError⟩ ⟨判据又崩了）。
    _r857 = _mdf(0.857, 2)
    _r90 = _mdf(0.90, 2)
    _r75 = _mdf(0.75, 2)
    # ⛔⛔⛔ **边界夹具**：cap **恰等于**答案 d=15。
    # ⛔⛔⛔ `range(2, cap+1)` ⛔ 若写成 `range(2, cap)` 就够不到 15 ⇒ 这里会 None。
    edge = _mdf(0.857, 2, ALPHA, cap=15)
    # ⛔⛔⛔ ⛔⛔✓ **解包前的名字要跟类型对上**：
    # ⛔⛔⛔   `_r857` 是**三元组**，⛔ 而 `d857`/`b857` 才是解包后的 int。
    # ⛔⛔⛔ ⛔⛔⛔⛔⛔⛔ 本项目**第三次**在解包上栽（244.41 两次、本轮一次）
    # ⛔⛔⛔   ⟨⇒ **返回值 ≥2 个分量就用具名 dict**。
    d857, b857 = (_r857[0], _r857[1]) if _r857 else (None, None)
    d90, b90 = (_r90[0], _r90[1]) if _r90 else (None, None)
    d75, b75 = (_r75[0], _r75[1]) if _r75 else (None, None)
    chk("C3", d857 == 15 and d90 == 12 and d75 == 25
        and edge is not None and edge[0] == 15,
        "2 格余量：比例 0.857⇒d≥**%s**（b=%d）；0.90⇒d≥%s（b=%d）；0.75⇒d≥**%s**（b=%d）；"
        "⚖ **cap=15 恰等于答案** ⇒ 实测返回 d=%s（⛔ 不是抛/None）"
        % (d857, b857, d90, b90, d75, b75,
           edge[0] if edge else "⛔ 未量到（抛了）"))

    # C4 ⚖ 参数守卫：keep ∉ (0,1] / d<2 / ratio ∉ (0,1] / n_items≤0 ⇒ 抛
    def raised(fn):
        try:
            fn()
            return False
        except HardFail:
            return True
    def msg_of(fn):
        try:
            fn()
            return None
        except HardFail as e:
            return str(e)

    m_ratio = msg_of(lambda: min_d_for(1.5, 2))
    chk("C4", raised(lambda: discordant_n(14, 0)) and raised(lambda: discordant_n(14, 5))
        and raised(lambda: pair_margin(1, 0.857)) and raised(lambda: pair_margin(6, 0))
        and raised(lambda: discordant_n(0, 1.0)) and m_ratio is not None
        and m_ratio.startswith("min_d_for:"),
        "keep=0 / keep=5 / d=1 / ratio=0 / n_items=0 / ratio=1.5 ⇒ 六个都抛"
        "；⚖⚠⚠ 且 `min_d_for` 那一条必须抛**自己**的守卫（消息前缀 %r）"
        " ⇒ ⛔ 光断言「会抛」分不清是哪一道" % m_ratio[:14])

    # C5 ⚖ 禁令恒 False
    chk("C5", pairing_is_not_more_headroom() is False,
        "⛔ 配对 ⛔ 不等于「更稳」⇒ 禁令恒 False")

    # C6 ⚖⚖ 报告恒印（⛔ 查报告，⛔ 不查源码 —— 源码自指会恒绿，见 244.43）
    always = ("【1】三种候选设计的**有效分母**", "【2】**缩分母 ⇒ 余量变差**",
              "【4】⚠ 要 **2 格**余量", "【5】⛔ 三条必须一起说的禁令",
              "只有中间那行会把分母变小", "在 0.857 这个比例上 2 格不可达",
              "真实 d ⛔ **尚未测量**", "本节没有回答「配对能不能提高一致性」",
              "别拿它当样本量" if False else "不许**说「配对更稳所以判决更可靠」")
    mr = [x for x in always if x not in Lr]
    chk("C6", not mr, "报告恒印缺 %s" % ("无" if not mr else mr))

    # C7 🔴🔴 缩分母 ⇒ 余量变差，必须是**实测**出来的（⛔ 不许是写死的散文）
    margins = [unpaired_margin(max(1, min(n - 1, int(round(0.857 * n)))), n)["margin"]
               for n in (14, 12, 10, 8)]
    chk("C7", margins == [1, 1, 1, 0],
        "同一比例下分母 14/12/10/8 的余量实测 = %s ⇒ ⚠⚠⚠ 缩分母只会更差"
        % margins)

    # C8 🔐 不可达那条必须真的不可达（⛔ 不是「没算」）
    #   ⚠⚠⚠⚠⚠⚠ 这里**也**不许裸调 `min_d_for`：⚠ 若它抛了，C8 会崩 ⇒
    #   ⚖ 台架报「崩」⇒ 又丢掉信号 ⇒ ⚗⇒ 一律走上面那个 `_mdf`。
    d90b = d90                      # ⚖ 上面已解包成 int，⛔ 不要再 [0]
    chk("C8", d857 is not None and d90b is not None
        and d857 > N_ITEMS and d90b <= N_ITEMS,
        "0.857⇒d≥%s > N=%d ⇒ ⛔ 不可达（实测，不是没算）；"
        "0.90⇒d≥%s ≤ %d ⇒ ✅ 可达" % (d857, N_ITEMS, d90b, N_ITEMS))

    # C9 🔴🔴 `discordant_n` **第一次**有判据覆盖（台架 J1 揭穿的缺口）
    #   ⚖⚠⚠⚠ **这个函数此前一次都没被调用过** ⇒ 改它（`max(d,2)`→`max(d,0)`）
    #   ⛔ 不会有任何判据转红 ⇒ ⚖ **「函数存在 + 守卫存在 + 自检全绿」三件事
    #   ⚠⚠⚠ 都成立，⛔ 仍然可能完全没被测过。**
    #   ⚖⚠⚠⚠⚠ 判别式：**每个对外函数都要有一条判据直接调它**，⛔ 不能只靠
    #   「别的函数间接用到它」⇒ ⚠⚠⚠ 间接覆盖随时可能被重构删掉。
    #   ⚖ 夹具里的 **keep=0.1** 是唯一能触发那个下界夹取的取值：
    #   ⚖ round(14×0.1)=round(1.4)=1 ⇒ ⛔ 不夹就是 1，夹了才是 2。
    chk("C9", discordant_n(14, 1.0) == 14 and discordant_n(14, 0.6) == 8
        and discordant_n(14, 0.5) == 7 and discordant_n(14, 0.1) == 2,
        "keep=1.0⇒d=%d；0.6⇒d=%d；0.5⇒d=%d；⚖ keep=0.1⇒**d=%d**"
        "（⛔ 不是 1 ⇒ 下界夹取承重）"
        % (discordant_n(14, 1.0), discordant_n(14, 0.6),
           discordant_n(14, 0.5), discordant_n(14, 0.1)))

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="配对设计能买到几格余量（零 GPU 纯算术）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    txt, rc = run()
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
