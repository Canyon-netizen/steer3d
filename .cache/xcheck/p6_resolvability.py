#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 观测量**可分辨性**闸（修订 198 立）。

回答一个预登记没问的问题：
    「就算 correct 组够 10 条，P6 要测的那个**量本身**测得出来吗？」

⚠⚠ 为什么要单独一道闸：预登记 P6 只写了
    「correct 组轨迹数 < 10 ⇒ 记『样本不足，不构成结论』」
    —— 它防的是**样本量**不足，**没有防「观测量低于仪器分辨率」**。
    ⚗⇒ 两个组都够 10 条，但真实差值比一个 ulp 还小时，
    ⚗   Mann–Whitney U 是在**拿噪声和噪声比**，p 值不可解释。

⚠ 口径全部来自实测，不在本脚本复刻任何模型计算：
    dot_marker_mean  取自 `w_unembed_align.py` 的产物
    class_gap        取自 `w*.npy.json`
    衰减 ~40×        取自预登记 §11.3 / §11.4（`α·(w·U)` 被下游 block 衰减）
    bf16 ulp         bf16 = 1 符号 + 8 指数 + **7 尾数** ⇒ ulp(v) = 2^⌊log₂v⌋ × 2⁻⁷

⚠⚠ **本闸只能把「可跑」变成「不可跑」，不能反过来**（沿用修订 8 的收紧纪律）。
⚠⚠ 预登记的**任何**口径（剂量阶梯、注入层、训练位置）本脚本一个字都不改。

⚠⚠ **`--logit-mag` 是必填，不给默认值** ——
⚠⚠ 分辨率取决于 logit 落在哪个 2 的幂区间，不同桶答案可能翻转。
⚠⚠ 偷偷给个默认值 = 偷偷替读数定口径，正是本项目反复栽的那类错。

用法：
    python3 p6_resolvability.py --w-unembed wu.json --w-meta w.json \
        --name new_p2a --logit-mag 40.0

退出码：
    0  可分辨 ⇒ 允许进入 P6 全量
    3  低于分辨率 ⇒ ⛔ 拒绝，并报出「该换哪一层口径」（只提示，不实施）
    2  用法/输入错误
"""

import argparse
import json
import sys
from math import floor, log2
from pathlib import Path

# 预登记 §11.3 / §11.4 实测：`α·(w·U)` 在 L=20 被下游 block 衰减约 40×。
# ⚠ 这是**实测值**，不是推导值。本脚本只做算术，不重新测。
ATTENUATION_L20 = 40.0

# 自检用的两份实测夹具（数值见修订 197 §197.2，均可由 w_unembed_align.py 复算）
FIXTURES = {
    "armB": {"dot_marker_mean": 0.18019922077655792, "class_gap": 231.978},
    "new_p2a": {"dot_marker_mean": 0.043172, "class_gap": 113.474},
}


def bf16_ulp(mag):
    """bf16 在量级 `mag` 处的最小可分辨步长。

    bf16 = 1 符号 + 8 指数 + 7 尾数位 ⇒ 对 v ∈ [2^k, 2^(k+1))，
    ulp = 2^k × 2^-7 = 2^(k-7)。
      v=8   (k=3) ⇒ 0.0625
      v=40  (k=5) ⇒ 0.25      ← 修订 7 记的 ±0.25 就是这一桶
      v=100 (k=6) ⇒ 0.5
    """
    if mag <= 0:
        raise ValueError("logit 量级必须为正，收到 %r" % (mag,))
    return 2.0 ** (floor(log2(mag)) - 7)


def assess(dot_marker_mean, class_gap, logit_mag=None, floor=None,
           rel_max=1.0, attenuation=ATTENUATION_L20):
    """返回判决字典。纯算术，可离线验。

    ⚠⚠ 修订 200 修正：**地板优先用实测的 `--floor`，`--logit-mag` 只是推导它的一种办法。**
    ⚠⚠ 原版把地板写死成 `bf16_ulp(logit_mag)`，而实测证明那**推不对**：
    ⚠⚠   logit 量级 ~3.094 ⇒ bf16 ulp 0.015625
    ⚠⚠   norm 输出量级 ~144–150 ⇒ bf16 ulp 1.0
    ⚠⚠   而 34 个实测读数的公共步长是 **0.125** —— 三者**互不相等**。
    ⚗⇒ 真正决定判决的是**读数实际能分辨多细**，那是个**实测量**，
    ⚗   不是任何单个张量的 dtype 网格推出来的数。
    """
    if floor is None:
        if logit_mag is None:
            raise ValueError("floor 与 logit_mag 至少要给一个")
        floor = bf16_ulp(logit_mag)
    alpha = rel_max * class_gap
    d_calib = alpha * dot_marker_mean           # 校准点的一阶效应（精确）
    d_l20 = d_calib / attenuation              # L=20 的应得残差（衰减后）
    ratio = d_l20 / floor
    return {
        "alpha": alpha,
        "d_calib": d_calib,
        "d_l20": d_l20,
        "floor": floor,
        "logit_mag": logit_mag,
        "ratio_to_floor": ratio,
        # ⛔ 用 >= 而不是 >：恰在一个 ulp 上算「勉强可分辨」，边界归可跑，
        # ⛔ 这样本闸只会拒掉「明确不可分辨」的，不会拒掉边界情形。
        "resolvable": d_l20 >= floor,
    }


def load_dot(wu_path, name):
    d = json.load(open(wu_path, encoding="utf-8"))
    rows = d.get("rows", d)
    if name not in rows:
        raise KeyError("w-unembed 产物里没有 %r，现有：%s" % (name, sorted(rows)))
    return float(rows[name]["dot_marker_mean"])


def load_gap(meta_path):
    d = json.load(open(meta_path, encoding="utf-8"))
    return float(d["class_gap"])


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--w-unembed", required=True,
                    help="w_unembed_align.py 的产物 json（取 dot_marker_mean）")
    ap.add_argument("--w-meta", required=True, help="w*.npy.json（取 class_gap）")
    ap.add_argument("--name", required=True, help="产物里这条 w 的名字")
    ap.add_argument("--logit-mag", type=float, default=None,
                    help="注入点实测 |logit| 量级；用它**推导**地板 "
                         "（bf16_ulp）。⚠ 实测证明推导值对不上读数量子，"
                         "所以能直接给 --floor 就给 --floor")
    ap.add_argument("--floor", type=float, default=None,
                    help="**直接**给分辨率地板。优先于 --logit-mag —— "
                         "34 个实测读数的公共步长是 0.125，与任何 dtype 推导值都不同")
    ap.add_argument("--floor-source", default=None,
                    help="地板的**出处**，必填。例：empirical-gcd-of-34-readings。"
                         "⚠ 不写出处 = 数字没有来源，正是本项目反复栽的那类错")
    ap.add_argument("--rel-max", type=float, default=1.0,
                    help="P3 剂量阶梯的最大档，默认 1.0（预登记写死的，不得调）")
    ap.add_argument("--attenuation", type=float, default=ATTENUATION_L20,
                    help="L=20 衰减倍数，默认 %.1f（§11.3 实测）" % ATTENUATION_L20)
    a = ap.parse_args()

    try:
        dot = load_dot(a.w_unembed, a.name)
        gap = load_gap(a.w_meta)
    except (OSError, KeyError, ValueError) as e:
        print("[错误] 读输入失败：%s" % e)
        return 2

    if a.floor is not None and a.logit_mag is not None:
        print("[错误] --floor 与 --logit-mag 给了**两个**地板来源 —— "
              "这正是「口径含糊」的形态，只给一个。")
        return 2
    if a.floor is None and a.logit_mag is None:
        print("[错误] 地板必须给一个：--floor（实测，推荐）或 --logit-mag（推导）。")
        return 2
    if not a.floor_source:
        print("[错误] --floor-source 必填：地板这个数**从哪来**必须写下来。")
        return 2

    r = assess(dot, gap, a.logit_mag, a.floor, a.rel_max, a.attenuation)

    print("=== P6 观测量可分辨性（%s）===" % a.name)
    print("  w·U[marker] 均值        = %+.6f" % dot)
    print("  class_gap               = %.3f" % gap)
    print("  rel_max（P3 写死）      = %.1f" % a.rel_max)
    print("  α = rel × class_gap     = %.3f" % r["alpha"])
    print("  校准点一阶效应 α·(w·U)  = %+.4f      （该点恒等式**精确**）" % r["d_calib"])
    print("  ÷ 衰减 %.1f（§11.3 实测） = %+.4f      （L=20 的应得残差）"
          % (a.attenuation, r["d_l20"]))
    if r["logit_mag"] is not None:
        print("  注入点 |logit| 量级      = %.4f（由它推导地板）" % r["logit_mag"])
        print("    ⇒ bf16_ulp = 2^⌊log₂v⌋·2⁻⁷ = %.6f" % bf16_ulp(r["logit_mag"]))
    else:
        print("  地板 **直接实测给定**（不经推导）")
    print("  ★ 地板 floor              = %.6f" % r["floor"])
    print("    出处：%s" % a.floor_source)
    print("  残差 / 分辨率            = %.3f" % r["ratio_to_floor"])
    print()

    if r["resolvable"]:
        print("  ✅ **可分辨**（残差 ≥ 一个 ulp）⇒ 允许进入 P6 全量。")
        print("     ⚠ 但这**只说明测得出来**，不说明有效应；")
        print("     ⚠ 有没有效应仍要由 Mann–Whitney U 自己回答。")
        print("RESULT p6_resolvability  RESOLVABLE  ratio=%.3f" % r["ratio_to_floor"])
        return 0

    print("  ⛔⛔ **低于仪器分辨率**（残差 < 一个 ulp）")
    print("     ⇒ 即便 correct 组够 10 条，Mann–Whitney U 也在**拿噪声和噪声比**：")
    print("     ⇒ 分不出两组**不是因为没效应，是因为量不出来**。")
    print("     ⇒ p 值不可解释，**不得**报「显著」也不得报「无差异」。")
    print()
    print("  ⚠ 这是**预登记没防的缺口**：P6 只写了 correct<10 ⇒「样本不足」，")
    print("  ⚠ 没有防「观测量本身低于分辨率」。两条是不同的「不成立」。")
    print()
    print("  ⚠ 把它抬出分辨率需要动**预登记口径**，本闸只报不实施。可选项见修订 197 §197.4：")
    print("     A 读数点改到校准点 L=-1   B 换 pos_offset=0 重训")
    print("     C 提高剂量（⛔ 禁止）     D 承认不可测，原样记「不构成结论」")
    print("     ⚗⚠ B 与 C 都属于「把信号调大以便测到」，与「调到绿为止」只差一层皮。")
    print()
    print("RESULT p6_resolvability  BELOW_FLOOR  ratio=%.3f" % r["ratio_to_floor"])
    return 3


if __name__ == "__main__":
    sys.exit(main())
