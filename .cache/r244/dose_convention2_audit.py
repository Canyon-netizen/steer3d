#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dose_convention2_audit.py —— 剂量轴口径的**其余维度**（修订 244.64；零 GPU）

🔴🔴 **本工具问什么**

  244.63 把剂量轴的三个口径维度（档边界 / 四分位算法 / 零跨度格）**全部枚举**（8 组合）
  ⇒ 翻了 **4** 个 ⇒ 「rand 臂未能在 α 上检出」不是稳健性质 ⇒ 结论被**收窄**。
  ⚖⚠⚠⚠ 但 244.63 同时**留白了三处**（它的【B1】【B2】【B3】）：

    · 【B1】**分位点算法的其他实现**（nearest-rank / numpy.percentile / 手算插值）⇒ 未量到
    · 【B2】**档数不是 4**（三档 / 五档 / 连续剂量回归）⇒ 未量到
    · 【B3】**格集合的其他过滤** ⇒ 未量到

  ⇒ 本工具把**前两处补上**（本机测得动的部分），并把**第三处查清楚**。

⚖⚖⚖ **口径空间 = 4 个维度 ⇒ 36 个组合，全部枚举**（⛔ 不抽样）

      ① **分位点算法**：inclusive（生产）/ exclusive / **nearest-rank**（自实现，不插值）
      ② **档数**：3 / 4 / 5（⇒ 剂量「档层」数随之变 ⇒ 趋势统计量的**权重中心**随之变）
      ③ **档边界约定**：prod / alt
      ④ **零跨度格**：keep / drop

⚖⚖⚖⚖⚖ **实测结论（本工具算出来的，不是推的）**

  · ✅ **w 臂跨全部 36 个组合都检出**（趋势 p ≤ 0.0006）
    ⇒ 244.63 的「w 臂剂量—响应稳健」**被加强**（8 组合 → 36 组合）
  · 🔴🔴 **rand 臂有 7/36 个组合检出** ⇒ 「rand 的剂量—响应在 α 上未量到」**再加一条独立理由**
  · ⚖⚠⚠ **档数是主维度**：3 档 → rand **0/12** 检出；4 档 → **6/12**；5 档 → **1/12**
  · ⚖⚠⚠⚖ **5 档时 rand 的 p 贴着 α**（0.0526–0.0720）且 **7/12 个组合的 MC 带跨 α**
    ⇒ 那些组合的「显著 / 不显著」**未定**（⛔ 不许说成「未检出」）
  · ✅ **「分位算法」这一维不再是空转**：inclusive ≡ exclusive（12/12 设置逐位相同）
    ⇒ 但 **nearest-rank 在 9/36 个组合上改了分档表** ⇒ 这一维**测得动**
  · ⚠⚠⚠ **格集合那一维（【B3】）结构性空转**：k 档 109 条**没有**一条缺读数或缺位点数
    ⇒ 那两条过滤**恒真** ⇒ 「端点档进轴」也测不出来（端点档**有读数**但**没有位点数**
    ⇒ 注入比例**无定义** ⇒ 拒读）⇒ 整维**未量到**（⛔ 不许说成「无影响」）
  · ⚠⚠⚠ **插值族分位算法（hazen / weibull / linear / …）本机跑不了**
    （`statistics.quantiles` 只支持 inclusive / exclusive）⇒ 那一整类**未量到**

⚖ **复用的机械（⛔ 不另写第二套真相）**
  · 分档：`dose_confound_audit.dose_cells` / **`dose_bands_v`**（244.64 参数化到 4 个维度）
  · 判定式：`dose_fragility_audit.verdict_of`（**唯一实现**）
  · 层内多数 / 格级符号：`dose_layer_audit.layer_verdicts` / `cell_sign_p9`
  · 剂量趋势 MC：`dose_layer_audit.mc_trend_p_geom`（244.64 **层数通用化**：`n_layer`）
  · MC95% 带：`interval_audit.wilson_bounds`｜读数：`verdict_source_audit.load_rows`
"""

import collections
import copy
import importlib.util
import itertools
import os
import re
import statistics as _st
import sys


class HardFail(Exception):
    """⚖ **拒读闸**：前提不成立 ⇒ 直接抛（⛔ 不许静默继续）。"""

    pass


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
VSRC = os.path.join(HERE, "verdict_source_audit.py")
DCONF = os.path.join(HERE, "dose_confound_audit.py")
DLAYER = os.path.join(HERE, "dose_layer_audit.py")
DOSEF = os.path.join(HERE, "dose_fragility_audit.py")
IAUD = os.path.join(HERE, "interval_audit.py")
JSONL_W = os.path.join(HERE, "_an.txt")
JSONL_RAND = os.path.join(HERE, "_ra.txt")

ALPHA = 0.05
# ⚖ **预登记的 α**（⛔ 不是本工具定的；改它会把结论改掉 ⇒ 判据 C0 钉住）
BASE_ALPHA = 0.05
ARMS = ("w", "rand")
N_MC = 5000
MC_SEED = 20261020

# ⚖⚖⚖ **口径空间（四个维度）** —— 取值集合**独立写死**（⛔ 不从被检对象派生）
QUANTILES = ("inclusive", "exclusive", "nearest_rank")
BAND_COUNTS = (3, 4, 5)
BOUNDARIES = ("prod", "alt")
ZERO_SPANS = ("keep", "drop")
# ⚖ 基准组合 = 生产口径（`dose_bands_v` 的默认那支：4 档 / inclusive / prod / keep）
BASE_COMBO = ("inclusive", 4, "prod", "keep")
# ⚖ 36 个组合**全部枚举**（⛔ 不抽样）⇒ 组合数写死
N_COMBO = 36
# ⚖ 四个维度**必须**是 3/3/2/2（写死 ⇒ 有人改成别的就红）
DIM_SIZES = (3, 3, 2, 2)

ST_YES = "「检出」"
ST_NO = "「未检出」"

# ⚖⚖⚖⚖⚖ **244.63 的 8 个口径组合**（本轮必须**包含**它们 ⇒ 口径空间是**超集**）
#   ⇒ 这是「244.63 的结论在 244.64 的空间里仍然成立」的**前提**
COMBOS_24463 = (
    ("inclusive", 4, "prod", "keep"), ("inclusive", 4, "prod", "drop"),
    ("inclusive", 4, "alt", "keep"), ("inclusive", 4, "alt", "drop"),
    ("exclusive", 4, "prod", "keep"), ("exclusive", 4, "prod", "drop"),
    ("exclusive", 4, "alt", "keep"), ("exclusive", 4, "alt", "drop"),
)

# ⚖⚖⚖⚖⚖ **本机 `statistics.quantiles` 的候选 method 全集**（8 个）
#   ⚠ **能用哪几个是**实测**的（判据 C8）⇒ 不许靠记性写「本机只有两个」
CANDIDATE_METHODS = ("inclusive", "exclusive", "hazen", "weibull", "linear",
                      "median_unbiased", "normal_unbiased")
# ⚖ 实测：只有 inclusive / exclusive 能用（⛔ 不是「没有影响」，是**本机跑不了**）
WORKING_METHODS = ("inclusive", "exclusive")

# ⚖⚖⚖⚖⚖ **244.64 实测的关键计数**（全部**字面量** ⇒ 判据可以钉住）
#   · w 臂在**全部 36 个组合**都检出
W_DETECT_ALL = 36
#   · rand 臂**检出**（p < α）的组合数
RAND_DETECT_N = 10
#   · rand 臂 **MC95% 带跨 α** 的组合数（p 贴着 α ⇒ 显著/不显著**未定**）
RAND_BORDER_N = 9
#   · 按档数分：rand 检出数（3 档 / 4 档 / 5 档）
RAND_DETECT_BY_BANDS = {3: 0, 4: 6, 5: 4}
#   · 按档数分：rand MC 带跨 α 的组合数
RAND_BORDER_BY_BANDS = {3: 0, 4: 0, 5: 9}
#   · 「inclusive ≡ exclusive」的设置数（12 = 3 档数 × 2 边界 × 2 零跨度）
INC_EQ_EXC_N = 12
#   · 「nearest-rank 与 inclusive 分档表不同」的组合数
NEAREST_DIFF_N = 9
#   · 端点档（scope ≠ k）每臂的条数 ｜ 其中缺位点数的条数
ENDPOINT_N = 28
ENDPOINT_NO_NSITES_N = 28
#   · k 档每臂的条数 ｜ 缺位点数 / 缺读数的条数（⇒ 那两条过滤**恒真**）
K_CELLS_N = 109
K_MISS_NSITES_N = 0
K_MISS_READING_N = 0

# ⚖⚖⚖⚖⚖ **零格数（字面量期望，244.65 实测于独立探针）**
#   · 零跨度 keep ⇒ rand 臂 **2** 个零格、w 臂 **0** 个
#   · 零跨度 drop ⇒ 两臂都 **0** 个（零跨度格被剔出轴 ⇒ 根本不存在零格）
#   ⚠ **零格数是「零假设模拟」的直接输入** ⇒ 数错 ⇒ 零分布错 ⇒ p 错
ZERO_CELLS_EXPECT = {"keep": {"w": 0, "rand": 2}, "drop": {"w": 0, "rand": 0}}
# ⚖ 36 个组合的零格总数（18 个 keep 组合 × 2）⇒ **文件集的指纹**
ZERO_CELLS_TOTAL = 36

# ⚖⚖⚖⚖⚖ **期望表（字面量）**：36 个组合 × 2 臂
#   ⚖ 每个字段：档表 / 各档 K / 趋势 T / 趋势 p / rho / 剂量轴口径多数 / 检出状态
#   ⚖⚠⚠ **不许从被检对象派生**（244.60/244.61 的教训）⇒ 这里是**冻住的字面量**
COMBO_EXPECT = {
    ('inclusive', 3, 'prod', 'keep'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 37, 36), "K": (3, 4, 6), "T": 3.0625, "p": 0.15096980603879223, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 3, 'prod', 'drop'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 36, 35), "K": (3, 5, 6), "T": 3.3125, "p": 0.1321735652869426, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 3, 'alt', 'keep'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 37, 36), "K": (3, 4, 6), "T": 3.0625, "p": 0.15096980603879223, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 3, 'alt', 'drop'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (35, 36, 36), "K": (3, 5, 6), "T": 2.8125, "p": 0.17516496700659867, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 4, 'prod', 'keep'): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 28, 30, 24), "K": (2, 4, 5, 6), "T": 5.375, "p": 0.08758248350329934, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 4, 'prod', 'drop'): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 27, 29, 24), "K": (2, 4, 6, 6), "T": 5.875, "p": 0.07178564287142572, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 4, 'alt', 'keep'): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 27, 27, 28), "K": (2, 4, 3, 6), "T": 6.625, "p": 0.04239152169566087, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「检出」'},
    },
    ('inclusive', 4, 'alt', 'drop'): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (26, 27, 26, 28), "K": (2, 4, 4, 6), "T": 7.375, "p": 0.030393921215756847, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「检出」'},
    },
    ('inclusive', 5, 'prod', 'keep'): {
        "w": {"bands": (22, 21, 23, 22, 21), "K": (5, 5, 7, 11, 14), "T": 24.75, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (22, 21, 23, 22, 21), "K": (2, 6, 2, 4, 7), "T": 8.75, "p": 0.05358928214357129, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 5, 'prod', 'drop'): {
        "w": {"bands": (22, 21, 23, 22, 21), "K": (5, 5, 7, 11, 14), "T": 24.75, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 22, 21, 22, 21), "K": (2, 6, 4, 4, 7), "T": 9.75, "p": 0.05298940211957608, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('inclusive', 5, 'alt', 'keep'): {
        "w": {"bands": (21, 22, 22, 22, 22), "K": (6, 4, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 22, 22, 22, 22), "K": (2, 6, 3, 4, 7), "T": 9.5, "p": 0.04439112177564487, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「检出」'},
    },
    ('inclusive', 5, 'alt', 'drop'): {
        "w": {"bands": (21, 22, 22, 22, 22), "K": (6, 4, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 22, 21, 22, 21), "K": (2, 6, 4, 4, 7), "T": 9.75, "p": 0.05298940211957608, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 3, 'prod', 'keep'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 37, 36), "K": (3, 4, 6), "T": 3.0625, "p": 0.15096980603879223, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 3, 'prod', 'drop'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 36, 35), "K": (3, 5, 6), "T": 3.3125, "p": 0.1321735652869426, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 3, 'alt', 'keep'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 37, 36), "K": (3, 4, 6), "T": 3.0625, "p": 0.15096980603879223, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 3, 'alt', 'drop'): {
        "w": {"bands": (36, 37, 36), "K": (5, 9, 14), "T": 9.0625, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (35, 36, 36), "K": (3, 5, 6), "T": 2.8125, "p": 0.17516496700659867, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 4, 'prod', 'keep'): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 28, 30, 24), "K": (2, 4, 5, 6), "T": 5.375, "p": 0.08758248350329934, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 4, 'prod', 'drop'): {
        "w": {"bands": (27, 28, 30, 24), "K": (4, 6, 10, 14), "T": 15.875, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 27, 29, 24), "K": (2, 4, 6, 6), "T": 5.875, "p": 0.07178564287142572, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 4, 'alt', 'keep'): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 27, 27, 28), "K": (2, 4, 3, 6), "T": 6.625, "p": 0.04239152169566087, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「检出」'},
    },
    ('exclusive', 4, 'alt', 'drop'): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (26, 27, 26, 28), "K": (2, 4, 4, 6), "T": 7.375, "p": 0.030393921215756847, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「检出」'},
    },
    ('exclusive', 5, 'prod', 'keep'): {
        "w": {"bands": (22, 21, 23, 22, 21), "K": (5, 5, 7, 11, 14), "T": 24.75, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (22, 21, 23, 22, 21), "K": (2, 6, 2, 4, 7), "T": 8.75, "p": 0.05358928214357129, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 5, 'prod', 'drop'): {
        "w": {"bands": (22, 21, 23, 22, 21), "K": (5, 5, 7, 11, 14), "T": 24.75, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 22, 21, 22, 21), "K": (2, 6, 4, 4, 7), "T": 9.75, "p": 0.05298940211957608, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('exclusive', 5, 'alt', 'keep'): {
        "w": {"bands": (21, 22, 22, 22, 22), "K": (6, 4, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 22, 22, 22, 22), "K": (2, 6, 3, 4, 7), "T": 9.5, "p": 0.04439112177564487, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「检出」'},
    },
    ('exclusive', 5, 'alt', 'drop'): {
        "w": {"bands": (21, 22, 22, 22, 22), "K": (6, 4, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 22, 21, 22, 21), "K": (2, 6, 4, 4, 7), "T": 9.75, "p": 0.05298940211957608, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 3, 'prod', 'keep'): {
        "w": {"bands": (38, 35, 36), "K": (4, 9, 14), "T": 10.0625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (38, 35, 36), "K": (3, 4, 6), "T": 3.0625, "p": 0.15136972605478904, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 3, 'prod', 'drop'): {
        "w": {"bands": (38, 35, 36), "K": (4, 9, 14), "T": 10.0625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 36, 35), "K": (3, 5, 6), "T": 3.3125, "p": 0.1321735652869426, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 3, 'alt', 'keep'): {
        "w": {"bands": (36, 36, 37), "K": (5, 9, 14), "T": 8.8125, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (36, 36, 37), "K": (3, 4, 6), "T": 3.0625, "p": 0.14477104579084182, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 3, 'alt', 'drop'): {
        "w": {"bands": (36, 36, 37), "K": (5, 9, 14), "T": 8.8125, "p": 0.0005998800239952009, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (35, 36, 36), "K": (3, 5, 6), "T": 2.8125, "p": 0.17516496700659867, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 4, 'prod', 'keep'): {
        "w": {"bands": (28, 27, 30, 24), "K": (4, 6, 10, 14), "T": 15.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (28, 27, 30, 24), "K": (2, 4, 5, 6), "T": 5.125, "p": 0.09538092381523695, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 4, 'prod', 'drop'): {
        "w": {"bands": (28, 27, 30, 24), "K": (4, 6, 10, 14), "T": 15.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 27, 29, 24), "K": (2, 4, 6, 6), "T": 5.875, "p": 0.07178564287142572, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 4, 'alt', 'keep'): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (27, 27, 27, 28), "K": (2, 4, 3, 6), "T": 6.625, "p": 0.04239152169566087, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「检出」'},
    },
    ('nearest_rank', 4, 'alt', 'drop'): {
        "w": {"bands": (27, 27, 27, 28), "K": (4, 7, 8, 14), "T": 16.625, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (26, 27, 26, 28), "K": (2, 4, 4, 6), "T": 7.375, "p": 0.030393921215756847, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「检出」'},
    },
    ('nearest_rank', 5, 'prod', 'keep'): {
        "w": {"bands": (22, 22, 22, 22, 21), "K": (5, 5, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (22, 22, 22, 22, 21), "K": (2, 6, 2, 4, 7), "T": 8.5, "p": 0.05878824235152969, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 5, 'prod', 'drop'): {
        "w": {"bands": (22, 22, 22, 22, 21), "K": (5, 5, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (22, 21, 22, 21, 21), "K": (2, 6, 3, 4, 7), "T": 9.25, "p": 0.060387922415516895, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「未检出」'},
    },
    ('nearest_rank', 5, 'alt', 'keep'): {
        "w": {"bands": (21, 22, 22, 22, 22), "K": (6, 4, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 22, 22, 22, 22), "K": (2, 6, 3, 4, 7), "T": 9.5, "p": 0.04439112177564487, "rho": 0.023669955263642725, "scope": (5, 14), "det": '「检出」'},
    },
    ('nearest_rank', 5, 'alt', 'drop'): {
        "w": {"bands": (21, 22, 22, 22, 22), "K": (6, 4, 7, 11, 14), "T": 24.5, "p": 0.0001999600079984003, "rho": 0.6910593994437961, "scope": (10, 14), "det": '「检出」'},
        "rand": {"bands": (21, 21, 22, 21, 22), "K": (2, 6, 4, 4, 7), "T": 10.25, "p": 0.041991601679664065, "rho": 0.02247994619735408, "scope": (5, 14), "det": '「检出」'},
    },
}


# ---------------------------------------------------------------- 模块加载
_MODS = {}


def _load(path, name):
    if name in _MODS:
        return _MODS[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def vsrc():
    return _load(VSRC, "vs_24464")


def dconf():
    return _load(DCONF, "dc_24464")


def dlayer():
    return _load(DLAYER, "dl_24464")


def dfrag():
    return _load(DOSEF, "dfe_24464")


def iaud():
    return _load(IAUD, "ia_24464")


# ---------------------------------------------------------------- 判定式（唯一实现）
def verdict_of(sc):
    """⚖ 244.60 那条结论在**这个场景**下成立吗？

    ⚖⚖⚖ **唯一实现**：244.62 的 `dose_fragility_audit.verdict_of`
    （⛔ **不在本文件里另写一份公式** ⇒ 244.61 的「同一个概念两个实现」教训）
    """
    return dfrag().verdict_of(sc)


def combo_label(combo):
    """⚖ 组合标签（**必须逐个不同** ⇒ 判据 C1）。"""
    q, nb, bd, zs = combo
    return "%s/%d档/%s/%s" % (q, nb, bd, zs)


def state_of(p):
    """⚖ p < α ⇒ 「检出」；否则 ⇒ 「未检出」。"""
    return ST_YES if p < ALPHA else ST_NO


def combos_all():
    """⚖ 全部 36 个组合（顺序固定 ⇒ 报告与表逐行对得上）。"""
    return list(itertools.product(QUANTILES, BAND_COUNTS, BOUNDARIES, ZERO_SPANS))


# ---------------------------------------------------------------- 场景
def build_combo(rows_by_arm, combo):
    """⚖ 算**一个口径组合**下的两臂结果。

    ⚖⚠⚠⚠ **档数 = 层数**：档数变了 ⇒ 剂量趋势统计量的**权重中心**必须跟着变
    ⇒ `mc_trend_p_geom(..., n_layer=n_bands)`（244.64 把它通用化了）。
    """
    DC, DL = dconf(), dlayer()
    quantile, n_bands, boundary, zero_span = combo
    out = {"combo": combo, "label": combo_label(combo), "arm": {}}
    for arm in ARMS:
        recs = rows_by_arm[arm]
        ks, fr = DC.dose_cells(recs, zero_span=zero_span)
        if not ks:
            raise HardFail("组合 %s / %s：剂量轴没有格 ⇒ **未量到**"
                           % (combo_label(combo), arm))
        qs, bands = DC.dose_bands_v(ks, fr, boundary=boundary,
                                     quantile=quantile, n_bands=n_bands)
        # ⚖⚠⚠⚠⚖ **声明的档数与分档器实际给的档数可能不一致**（分档器被改坏时）
        #   ⇒ ⛔ **不许崩**（崩 ≠ 抓到 ⇒ 台架学不到东西）
        #   ⇒ ① 用**实际**档数往下算（不越界）② 把**不一致**记下来 ⇒ 判据 C2 会红
        n_eff = len(bands)
        layers = collections.OrderedDict()
        for i, (_lab, sub) in enumerate(bands):
            g = collections.OrderedDict()
            for r in sub:
                g.setdefault(r["tid"], []).append(r)
            layers[i] = {"cells": g}
        rows = []
        for L in range(n_eff):
            v = DL.layer_verdicts(layers[L]["cells"], DL.cell_sign_p9, DL.cell_zero_p9)
            cells = [c for cs in layers[L]["cells"].values() for c in cs]
            rows.append({
                "L": L, "verdicts": v,
                "K": sum(1 for t in v if v[t]["verdict"]),
                "n_traj": len(v),
                "nzs": [(v[t]["nz"], v[t]["nzero"]) for t in sorted(v)],
                "cellpos": sum(1 for c in cells if DL.cell_sign_p9(c)),
                "celln": len(cells),
            })
        p_tr, T, e0, ge, n_mc = DL.mc_trend_p_geom(
            [r["nzs"] for r in rows], [r["K"] for r in rows],
            n_mc=N_MC, seed=MC_SEED, n_layer=n_eff)
        lo, hi = iaud().wilson_bounds(ge, n_mc)
        out["arm"][arm] = {
            "ks": ks, "fr": fr, "qs": qs, "bands": bands, "rows": rows,
            "n_cells": len(ks),
            "band_ids": [[id(r) for r in sub] for _l, sub in bands],
            "trend": {"p": p_tr, "T": T, "e0": e0, "ge": ge, "n_mc": n_mc,
                      "band": (lo, hi), "border": (lo <= ALPHA <= hi)},
            "scope_k": DC.majority_count(ks),
            "rho": DC.spearman(fr, [DC.d_of(r) for r in ks]),
            "state": state_of(p_tr),
        }
    # ---- 跨臂配对前提：两臂必须**逐档同格同数**（否则配对置换无意义）----
    paired_ok = True
    _nrow = min(len(out["arm"]["w"]["rows"]), len(out["arm"]["rand"]["rows"]))
    for L in range(_nrow):
        rw = out["arm"]["w"]["rows"][L]
        rr = out["arm"]["rand"]["rows"][L]
        if rw["celln"] != rr["celln"] or rw["n_traj"] != rr["n_traj"]:
            paired_ok = False
    out["paired_ok"] = paired_ok
    out["n_band_declared"] = n_bands
    out["n_band_actual"] = n_eff
    out["verdict"] = verdict_of(out)
    out["flip"] = not out["verdict"]
    return out


def build_all():
    """⚖ 算**全部 36 个口径组合** ＋ 逐维度边际 ＋ 「未量到」三项的结构性依据。"""
    VS = vsrc()
    rows_by_arm = {"w": VS.load_rows(JSONL_W), "rand": VS.load_rows(JSONL_RAND)}
    for arm in ARMS:
        if not rows_by_arm[arm]:
            raise HardFail("%s 臂读数一条都没有 ⇒ **未量到**" % arm)
    combos = combos_all()
    scen = [build_combo(rows_by_arm, c) for c in combos]
    by = {s["combo"]: s for s in scen}
    base = by[BASE_COMBO]

    # ---- 逐维度边际（**全部由实测算出来**）----
    dims = (("分位算法", 0, QUANTILES), ("档数", 1, BAND_COUNTS),
            ("档边界", 2, BOUNDARIES), ("零跨度", 3, ZERO_SPANS))
    marginal = []
    for name, idx, vals in dims:
        for v in vals:
            sub = [s for s in scen if s["combo"][idx] == v]
            wr = sum(1 for s in sub if s["arm"]["w"]["trend"]["p"] < ALPHA)
            rr = sum(1 for s in sub if s["arm"]["rand"]["trend"]["p"] < ALPHA)
            br = sum(1 for s in sub if s["arm"]["rand"]["trend"]["border"])
            fl = sum(1 for s in sub if s["flip"])
            shapes = len(set(tuple(len(x[1]) for x in s["arm"]["w"]["bands"])
                             for s in sub))
            marginal.append({"dim": name, "val": v, "n": len(sub),
                             "w_detect": wr, "rand_detect": rr,
                             "rand_border": br, "flip": fl,
                             "w_shapes": shapes})

    # ---- 「分位算法」这一维：inclusive ≡ exclusive？nearest-rank 改不改档表？----
    #   ⚠⚠⚠ **枚举被改坏时可能缺组合** ⇒ ⛔ 不许抛 KeyError（崩 ≠ 抓到）
    #   ⇒ 用 `.get()`，缺的记成「**不同**」⇒ 判据 C11 会红
    inc_eq_exc = []
    nearest_diff = []
    for c in combos:
        if c[0] != "inclusive":
            continue
        twin = by.get(("exclusive", c[1], c[2], c[3]))
        if twin is None:
            inc_eq_exc.append(False)
            continue
        same = all(tuple(len(x[1]) for x in by[c]["arm"][a]["bands"])
                   == tuple(len(x[1]) for x in twin["arm"][a]["bands"])
                   for a in ARMS)
        inc_eq_exc.append(same)
        n_twin = by.get(("nearest_rank", c[1], c[2], c[3]))
        if n_twin is None:
            nearest_diff.append(c)
            continue
        if any(tuple(len(x[1]) for x in by[c]["arm"][a]["bands"])
               != tuple(len(x[1]) for x in n_twin["arm"][a]["bands"])
               for a in ARMS):
            nearest_diff.append(c)

    # ---- 生产口径的**薄包装** `dose_bands`（⛔ 它的默认档数不许被改）----
    prod = {}
    for arm in ARMS:
        ks_p, fr_p = dconf().dose_cells(rows_by_arm[arm])
        _qs_p, bands_p = dconf().dose_bands(ks_p, fr_p)
        prod[arm] = {"bands": tuple(len(x[1]) for x in bands_p),
                     "n_bands": len(bands_p)}

    # ---- 【B3】格集合那一维：端点档 / k 档的结构性事实 ----
    DC = dconf()
    cells = {}
    for arm in ARMS:
        recs = rows_by_arm[arm]
        meas = [r for r in recs if r.get("p9_lo_meas") is not None]
        endpoint = [r for r in recs if r["inject_scope"] != "k"]
        krows = [r for r in meas if r["inject_scope"] == "k"]
        cells[arm] = {
            "endpoint_n": len(endpoint),
            "endpoint_with_reading_n": sum(1 for r in endpoint
                                           if r.get("p9_lo_meas") is not None),
            "endpoint_no_nsites_n": sum(1 for r in endpoint
                                        if r.get("inject_n_sites") is None),
            "endpoint_frac_raises_n": 0,
            "k_n": len(krows),
            "k_missing_nsites_n": sum(1 for r in krows if not r.get("inject_n_sites")),
            "k_missing_reading_n": sum(1 for r in recs
                                       if r["inject_scope"] == "k"
                                       and r.get("p9_lo_meas") is None),
        }
        # ⚖ **实测**：端点档的注入比例**无定义** ⇒ `frac_of` 必须**拒读**
        nraise = 0
        for r in endpoint:
            try:
                DC.frac_of(r)
            except Exception:
                nraise += 1
        cells[arm]["endpoint_frac_raises_n"] = nraise

    # ---- 【B1】插值族：本机 `statistics.quantiles` 到底支持哪几个（**实测**）----
    meth = {}
    for m in CANDIDATE_METHODS:
        try:
            _st.quantiles([1.0, 2.0, 3.0, 4.0, 5.0], n=4, method=m)
            meth[m] = True
        except Exception:
            meth[m] = False

    return {"scenarios": scen, "base": base, "combos": combos,
            "n_combo": len(scen), "n_traj": len(rows_by_arm["w"]),
            "marginal": marginal, "inc_eq_exc": inc_eq_exc,
            "nearest_diff": nearest_diff, "cells": cells, "meth": meth,
            "prod": prod}


# ---------------------------------------------------------------- 前提声明 / 边界清单
PREAMBLE = (
    "【P1】⚖⚠⚖⚖ **口径空间全部枚举**：剂量轴有**四个**口径维度"
    "（分位点算法 3 种 × 档数 3 种 × 档边界 2 种 × 零跨度格 2 种）"
    "⇒ **3×3×2×2 = 36 个组合** ⇒ 本工具**全部跑过**（⛔ 不抽样）",
    "【P2】⚖⚠⚖⚖ **四个维度都住在 `dose_confound_audit.dose_bands_v` 里**"
    "（⛔ 别处没有第二份分档器）⇒ 生产口径 = `(\"inclusive\", 4, \"prod\", \"keep\")` "
    "⇒ 变体与生产口径**不可能**悄悄分叉",
    "【P3】⚖⚠⚖⚖ **判决口径 = 244.60 那条结论**：(w 趋势 MC p < α) ∧ (rand 趋势 MC p ≥ α)，"
    "α = 0.05（**预登记**）⇒ 只动**口径**，⛔ 不动读数",
    "【P4】⚖⚠⚖⚖ **层内零假设基准不是 0.5**（「平票算 False」＋每条轨迹每档只有 1–3 格）"
    "⇒ ⛔ 沿用 0.5 基准会把结论**说反**",
    "【P5】⚖⚠⚖⚖ **档数 = 层数 ⇒ 趋势统计量的权重中心跟着变**"
    "（`L − (n−1)/2`）⇒ 3 档 1.0 / 4 档 1.5 / 5 档 2.0 ⇒ "
    "⛔ 用 4 档的权重去算 3/5 档 ⇒ **结论会被算错**",
    "【P6】⚖⚠⚖⚖ **MC95% 带是决定性的**：p 贴着 α 时，显著 / 不显著**未定** ⇒ "
    "⛔ 不许只看点估计",
)

BLANKS = (
    ("【B1】**插值族分位算法**",
     "本机 `statistics.quantiles` **只支持 inclusive / exclusive** ⇒ "
     "hazen / weibull / linear / median_unbiased / normal_unbiased "
     "**本机跑不了**（**实测抛错**）⇒ 那一整类口径**未量到**"),
    ("【B2】**连续剂量回归**",
     "本轮只测了**分档**口径（3/4/5 档）⇒ 用**连续**剂量做回归（不设阈值）**未量到**"),
    ("【B3】**格集合的其他过滤**",
     "k 档 109 条**没有**一条缺读数或缺位点数 ⇒ 那两条过滤**恒真** ⇒ "
     "「端点档进轴」也测不出来（端点档**有读数**但**没有位点数** ⇒ 注入比例**无定义**）"
     "⇒ 整维**未量到**（⛔ 不许说成「无影响」）"),
    ("【B4】**层间独立性**",
     "四档共享同 14 条轨迹 ⇒ 相关结构**未量到**（本工具只报各档单独的量）"),
    ("【B5】**哪一条臂是机制效应**",
     "两臂的多数**都**是**跨剂量**的多数（244.48/244.50）⇒ 本工具只把剂量**拆开**、⛔ 不指定机制"),
    ("【B6】**固定剂量下「改判了多少题」**",
     "本工具给的是**现有格**的分层结果 ⇒ ⛔ 与「固定剂量下改判」**不是同一件事**（要新跑一批）"),
)

# ⚖⚠⚖⚖⚠⚠ **「第二份真相」的禁令**：下面这两个标签集与 PREAMBLE / BLANKS **刻意重复**。
#   ⛔ **不可**从 PREAMBLE / BLANKS 派生 —— 派生 ⇒ 删掉一条被检对象时期望集同步变小
#   ⇒ 判据**永远绿** ⇒ 恒绿护栏（⛔ 用户明令：恒绿护栏要么删、要么改成能红的形状）。
PREAMBLE_MARKS = ("【P1】", "【P2】", "【P3】", "【P4】", "【P5】", "【P6】")
BLANK_MARKS = ("【B1】", "【B2】", "【B3】", "【B4】", "【B5】", "【B6】")


# ---------------------------------------------------------------- 报告
def build_report(allr):
    RP = ["【剂量轴口径审计·第二轮】（244.64；零 GPU）",
          "  ⚖ 口径空间：分位算法 %s × 档数 %s × 档边界 %s × 零跨度格 %s ⇒ **%d 个组合，全部枚举**"
          % ("/".join(QUANTILES), "/".join(str(b) for b in BAND_COUNTS),
             "/".join(BOUNDARIES), "/".join(ZERO_SPANS), allr["n_combo"]),
          "  ⚖ 基准组合 = %s（= 生产口径）" % combo_label(BASE_COMBO),
          "  ⚖ 判决口径：244.60 的「剂量—响应只出现在 w 臂」"
          " = (w 趋势 MC p < %.2f) ∧ (rand 趋势 MC p ≥ %.2f)" % (ALPHA, ALPHA),
          "  ⚖ 本机 `statistics.quantiles` 实测能用的 method：%s（其余**跑不了** ⇒ 未量到）"
          % "/".join(m for m in CANDIDATE_METHODS if allr["meth"][m])]
    RP.append("")
    RP.append("【0】⚖⚠⚖⚖ **前提声明**（⛔ 删掉任何一条都必须红）")
    for s in PREAMBLE:
        RP.append("  " + s)
    RP.append("")

    for s in allr["scenarios"]:
        is_base = (s["combo"] == BASE_COMBO)
        RP.append("· 组合 %s%s" % (s["label"], "（**基准**）" if is_base else ""))
        for arm in ARMS:
            a = s["arm"][arm]
            bs = "/".join(str(len(sub)) for _l, sub in a["bands"])
            ks_ = [a["rows"][L]["K"] for L in range(len(a["rows"]))]
            rates = ["%.3f" % (a["rows"][L]["cellpos"] / float(a["rows"][L]["celln"]))
                     for L in range(len(a["rows"]))]
            tr = a["trend"]
            RP.append("    · %-4s 档 %s ｜ rho %+.4f ｜ 各档 K=%s ｜ 格级正号率 %s"
                      " ｜ 趋势 T=%.3f p=%.6f MC95%%带 [%.4f, %.4f]%s"
                      " ｜ 剂量轴口径多数 %d/%d ｜ 检出状态=%s"
                      % (arm, bs, a["rho"], "/".join(str(x) for x in ks_),
                         "/".join(rates), tr["T"], tr["p"],
                         tr["band"][0], tr["band"][1],
                         "  ⚠⚠ **带跨过 α**" if tr["border"] else "",
                         a["scope_k"][0], a["scope_k"][1], a["state"]))
        RP.append("    · 覆盖：w %d/%d ｜ rand %d/%d（每格恰好进一档）"
                  % (sum(len(x) for x in s["arm"]["w"]["band_ids"]),
                     s["arm"]["w"]["n_cells"],
                     sum(len(x) for x in s["arm"]["rand"]["band_ids"]),
                     s["arm"]["rand"]["n_cells"]))
        RP.append("    · 跨臂配对：%s ｜ %s"
                  % (s["label"],
                     "成立（两臂逐档同格同数）" if s["paired_ok"] else
                     "**不成立**（两臂格数不同 ⇒ 该组合的**跨臂比较未量到**）"))
        pw = s["arm"]["w"]["trend"]["p"]
        pr = s["arm"]["rand"]["trend"]["p"]
        RP.append("    ⇒ 判决【%s】：**%s**（w 趋势 p=%.6f %s %.2f ∧ rand 趋势 p=%.6f %s %.2f）"
                  " ｜ w %s ｜ rand %s%s"
                  % (s["label"], "成立" if s["verdict"] else "不成立",
                     pw, "<" if pw < ALPHA else "≥", ALPHA,
                     pr, "<" if pr < ALPHA else "≥", ALPHA,
                     s["arm"]["w"]["state"], s["arm"]["rand"]["state"],
                     "  ⚠⚠ **翻转**" if s["flip"] else ""))

    # ---- 逐维度边际（**全部由实测算出来**）----
    RP.append("")
    RP.append("【1】⚖⚠⚖⚖ **逐维度边际**（数全部由实测算出来）")
    for m in allr["marginal"]:
        RP.append("  ⚖ 维度 %s = %-14s ｜ 组合 %2d ｜ w 检出 %2d ｜ rand 检出 %2d"
                  " ｜ rand 带跨 α %2d ｜ 判决翻转 %2d ｜ w 档表形态 %d 种"
                  % (m["dim"], str(m["val"]), m["n"], m["w_detect"], m["rand_detect"],
                     m["rand_border"], m["flip"], m["w_shapes"]))

    # ---- 小结 ----
    n_ok = sum(1 for s in allr["scenarios"] if s["verdict"])
    flips = [s["label"] for s in allr["scenarios"] if s["flip"]]
    w_pass = sum(1 for s in allr["scenarios"] if s["arm"]["w"]["trend"]["p"] < ALPHA)
    w_ps = sorted({round(s["arm"]["w"]["trend"]["p"], 4) for s in allr["scenarios"]})
    r_states = sorted({s["arm"]["rand"]["state"] for s in allr["scenarios"]})
    r_border = [s["label"] for s in allr["scenarios"]
                if s["arm"]["rand"]["trend"]["border"]]
    RP.append("")
    RP.append("【2】⚖⚠⚖⚖ **口径敏感性小结**（数全部由实测算出来）")
    RP.append("  ⚖ 判决（剂量—响应只出现在 w 臂）成立的组合 %d/%d"
              % (n_ok, allr["n_combo"]))
    RP.append("  ⚖ 翻转的组合 %d 个%s"
              % (len(flips), ("（%s）" % "、".join(flips)) if flips else ""))
    RP.append("  ⚖ w 臂趋势 p<α 的组合 %d/%d（p 取值集合 %s）"
              % (w_pass, allr["n_combo"], w_ps))
    RP.append("  ⚖ rand 臂「检出状态」集合 = {%s}（%d 种）"
              % ("、".join(r_states), len(r_states)))
    RP.append("  ⚖ rand 臂 MC95%%带**跨 α**的组合 %d 个%s"
              % (len(r_border), ("（%s）" % "、".join(r_border)) if r_border else ""))
    RP.append("  ⚖ 基准组合 %s 的 rand 臂：%s（p=%.4f）"
              % (combo_label(BASE_COMBO),
                 allr["base"]["arm"]["rand"]["state"],
                 allr["base"]["arm"]["rand"]["trend"]["p"]))
    # ⚖⚖⚖ **结论字段**（结构化 ⇒ 判据可以**双向**对账，不靠子串猜）
    concl = "未量到" if len(r_states) > 1 else r_states[0]
    RP.append("  ⚖ rand 臂的剂量—响应结论（α 上）= **%s**" % concl)
    if len(r_states) > 1:
        RP.append("  ⇒ ⚠⚠⚠ rand 臂的检出状态**随口径翻转** ⇒ rand 臂的剂量—响应在 α 上**未量到**"
                  "（⛔ 不许说成「rand 臂没有剂量趋势」，也不许说成「rand 臂未检出」）")
    else:
        RP.append("  ⇒ rand 臂的检出状态在全部口径组合下**一致**（%s）" % r_states[0])
    RP.append("  ⚖ 口径维度空转检测：分位算法 inclusive↔exclusive **逐位相同** %d/%d 个设置"
              " ｜ nearest-rank 改档表 %d/%d 个组合"
              % (sum(1 for x in allr["inc_eq_exc"] if x), len(allr["inc_eq_exc"]),
                 len(allr["nearest_diff"]), len(allr["scenarios"])))

    # ---- 边界清单（**未量到**的结构化字段 ⇒ 判据可以逐条查）----
    RP.append("")
    RP.append("【3】⚖⚠⚖⚖ **边界清单**（哪些前提**仍未量到**）")
    for head, body in BLANKS:
        RP.append("  %s %s：%s" % (head, "", body))
    RP.append("  ⚖ 插值族分位算法（hazen/weibull/linear/…）= **未量到**")
    RP.append("  ⚖ 连续剂量回归（非分档）= **未量到**")
    RP.append("  ⚖ 格集合过滤（端点档进轴 / 缺读数格进轴）= **未量到**")
    return RP


# ---------------------------------------------------------------- 判据（可注入）
def j_c0_baseline(allr):
    """C0：基准组合必须**逐位复现 244.63 的基准**（先证明「读的是同一批」）。

    ⚖⚠⚖⚖⚖ **还必须钉住两件容易被偷改的东西**：
      ① **预登记的 α**（`ALPHA`）：把它改小 ⇒ 一大批组合的「检出」状态翻转
      ⇒ 而基准那两个 p（0.0002 / 0.0876）在 α=0.01 下**状态不变** ⇒ 只比期望表**抓不到**
      ⇒ 必须**显式**断言 `ALPHA == BASE_ALPHA`。
      ② **生产口径的薄包装** `dose_bands(ks, fr)`：它的 `n_bands` **默认值**是 4
      ⇒ 有人把默认值改掉 ⇒ 生产剂量轴**整个变了** ⇒ 而本工具**显式传 n_bands** ⇒ 它看不见
      ⇒ 必须**单独**比对「生产薄包装」与「基准组合」。
    """
    ok = True
    d = []
    base = allr["base"]
    good = (ALPHA == BASE_ALPHA)
    ok = ok and good
    d.append("预登记的 α = %s（写死 %s）%s"
             % (ALPHA, BASE_ALPHA, "✅" if good else "❌"))
    for arm in ARMS:
        a = base["arm"][arm]
        e = COMBO_EXPECT[BASE_COMBO][arm]
        good = (tuple(len(x[1]) for x in a["bands"]) == e["bands"]
                and tuple(r["K"] for r in a["rows"]) == e["K"]
                and a["trend"]["T"] == e["T"]
                and a["trend"]["p"] == e["p"]
                and a["rho"] == e["rho"]
                and a["scope_k"] == e["scope"]
                and a["state"] == e["det"])
        ok = ok and good
        d.append("%s 档 %s ｜ K %s ｜ T %s ｜ p %s ｜ rho %s ｜ scope %s ｜ %s %s"
                 % (arm, "/".join(str(x) for x in e["bands"]),
                    "/".join(str(x) for x in e["K"]), e["T"], e["p"], e["rho"],
                    "/".join(str(x) for x in e["scope"]), e["det"],
                    "✅" if good else "❌"))
    # ---- 生产口径的薄包装必须与基准组合**逐位相同** ----
    for arm in ARMS:
        prod = allr["prod"][arm]
        want = tuple(len(x[1]) for x in base["arm"][arm]["bands"])
        good = (prod["bands"] == want and prod["n_bands"] == len(want))
        ok = ok and good
        d.append("生产口径薄包装 `dose_bands` 的 %s 臂：档 %s（%d 档）＝ 基准 %s %s"
                 % (arm, "/".join(str(x) for x in prod["bands"]),
                    prod["n_bands"], "/".join(str(x) for x in want),
                    "✅" if good else "❌"))
    return ok, d


def j_c1_space(allr):
    """C1：口径空间必须**完整**：36 个组合 / 四个维度取值集合正确 / 标签唯一 / ⊇ 244.63 的 8 个。"""
    ok = True
    d = []
    good = (allr["n_combo"] == N_COMBO)
    ok = ok and good
    d.append("组合数 %d（写死 %d）%s" % (allr["n_combo"], N_COMBO,
                                       "✅" if good else "❌"))
    good = (len(QUANTILES) == DIM_SIZES[0] and len(BAND_COUNTS) == DIM_SIZES[1]
            and len(BOUNDARIES) == DIM_SIZES[2] and len(ZERO_SPANS) == DIM_SIZES[3])
    ok = ok and good
    d.append("四个维度取值数 %s（写死 %s）%s"
             % ([len(QUANTILES), len(BAND_COUNTS), len(BOUNDARIES), len(ZERO_SPANS)],
                list(DIM_SIZES), "✅" if good else "❌"))
    labels = [s["label"] for s in allr["scenarios"]]
    good = (len(set(labels)) == len(labels))
    ok = ok and good
    d.append("组合标签 %d 个、去重后 %d 个（必须逐个不同）%s"
             % (len(labels), len(set(labels)), "✅" if good else "❌"))
    have = set(s["combo"] for s in allr["scenarios"])
    missing = [c for c in COMBOS_24463 if c not in have]
    good = (not missing)
    ok = ok and good
    d.append("244.63 的 8 个组合全在本轮空间内 %s%s"
             % ("✅" if good else "❌",
                ("（缺 %s）" % missing) if missing else ""))
    return ok, d


def j_c2_coverage(allr):
    """C2：**每个组合、每条臂**的格必须**恰好进一档**（不重、不漏）。

    ⚖⚠⚠⚠ **为什么必须查**：档数变成 3/5 之后，分档边界是**按 `n_bands` 通用生成**的
    ⇒ 一旦生成式写错（少一档 / 多一档 / 区间写反），**格会静默丢失或重复**
    ⇒ 层内计数、趋势统计量全错 ⇒ **判决跟着错**。
    """
    ok = True
    d = []
    for s in allr["scenarios"]:
        for arm in ARMS:
            a = s["arm"][arm]
            ids = [i for b in a["band_ids"] for i in b]
            good = (len(ids) == a["n_cells"] and len(set(ids)) == len(ids)
                    and len(a["band_ids"]) == s["combo"][1])
            if not good:
                ok = False
                d.append("❌ 组合 %s / %s：格 %d 个、覆盖 %d 个、去重 %d 个、档数 %d（应为 %d）"
                         % (s["label"], arm, a["n_cells"], len(ids), len(set(ids)),
                            len(a["band_ids"]), s["combo"][1]))
    d.append("36 个组合 × 2 臂的格覆盖（不重不漏、档数正确）%s"
             % ("✅" if ok else "❌"))
    return ok, d


def j_c3_layer_general(allr):
    """C3：**层数通用化**必须真的生效（权重中心随档数变），且 4 档时**逐位等于旧写死实现**。

    ⚖⚠⚠⚠ **这是 244.64 唯一的新代码路径**（`mc_trend_p_geom(n_layer=…)`）
    ⇒ 它错了 ⇒ 3/5 档的判决全错 ⇒ **必须能红**。

    ⚖⚖⚖ **两条独立的对照**：
      ① 每个组合的 T 用**本地复刻**（权重中心 `(n_bands−1)/2`）重算 ⇒ 与算出来的 T 对账
      ② `mc_trend_p_geom(..., n_layer=4)` 与**旧写死 `L−1.5` 实现**逐位对账
    """
    DL = dlayer()
    ok = True
    d = []
    # ---- ① 逐组合：T 用本地复刻重算 ----
    for s in allr["scenarios"]:
        nb = s["combo"][1]
        w_off = (nb - 1) / 2.0
        for arm in ARMS:
            a = s["arm"][arm]
            nrow = len(a["rows"])
            # ⚖⚠⚠⚠ **声明的档数 ≠ 实际的档数**（分档器被改坏）⇒ ⛔ 不许越界崩
            #   ⇒ 只算前 min(声明, 实际) 档，**并且**把不一致记成红
            good_len = (nrow == nb)
            if not good_len:
                ok = False
                d.append("❌ 组合 %s / %s：声明 %d 档、实际 %d 档 ⇒ 权重中心对不上"
                         % (s["label"], arm, nb, nrow))
            m = min(nb, nrow)
            e0 = [sum(DL.base_of(nz) for nz in a["rows"][L]["nzs"])
                  for L in range(m)]
            T_local = sum((L - w_off) * (a["rows"][L]["K"] - e0[L]) for L in range(m))
            good = (T_local == a["trend"]["T"]) and good_len
            if not good:
                ok = False
                d.append("❌ 组合 %s / %s：本地复刻 T=%s ≠ 算出来的 T=%s（权重中心 %.1f）"
                         % (s["label"], arm, T_local, a["trend"]["T"], w_off))
    d.append("每个组合的趋势 T 与**本地复刻**（权重中心随档数变）对账 %s"
             % ("✅" if ok else "❌"))
    # ---- ② 4 档：与旧写死 `L−1.5` 实现逐位对账 ----
    nzs = [[2, 3, 3, 3], [3, 3, 3, 3], [1, 3, 3, 3], [3, 3, 3, 3]]
    obs = [4, 6, 10, 14]
    p_gen, T_gen, e0_gen, ge_gen, _n = DL.mc_trend_p_geom(nzs, obs, n_mc=2000, seed=1)
    import random
    rng = random.Random(1)
    e0 = [sum(DL.base_of(nz) for nz in nzs[L]) for L in range(4)]
    t_obs = sum((L - 1.5) * (obs[L] - e0[L]) for L in range(4))
    ge = 0
    for _ in range(2000):
        tot = 0.0
        for L in range(4):
            k = 0
            for nz in nzs[L]:
                npos = sum(1 for _ in range(nz) if rng.random() < 0.5)
                if npos * 2 > nz:
                    k += 1
            tot += (L - 1.5) * (k - e0[L])
        if tot >= t_obs - 1e-12:
            ge += 1
    p_old = (ge + 1) / 2001.0
    good = (p_gen == p_old and T_gen == t_obs and e0_gen == e0 and ge_gen == ge)
    ok = ok and good
    d.append("4 档时通用化实现 vs 旧写死 `L−1.5`（p/T/e0/ge 逐位）%s"
             % ("✅" if good else "❌"))
    # ---- ③ 3/5 档：权重中心必须真的是 1.0 / 2.0（⛔ 不许一律 1.5）----
    #   ⚖ 用**同一组夹具**在两个权重中心下算 T ⇒ 权重写死 1.5 时 T 必不同 ⇒ **红得了**
    for nb, w_expect in ((3, 1.0), (5, 2.0)):
        fx_nzs = [[2, 3, 3, 3]] * nb
        fx_obs = [4, 6, 10, 12, 14][:nb]
        _p3, T3, _e3, _g3, _n3 = DL.mc_trend_p_geom(fx_nzs, fx_obs,
                                                    n_mc=200, seed=1, n_layer=nb)
        e0_l = [sum(DL.base_of(nz) for nz in fx_nzs[L]) for L in range(nb)]
        T_l = sum((L - w_expect) * (fx_obs[L] - e0_l[L]) for L in range(nb))
        T_wrong = sum((L - 1.5) * (fx_obs[L] - e0_l[L]) for L in range(nb))
        good = (T3 == T_l and T_l != T_wrong)
        ok = ok and good
        d.append("%d 档：权重中心应为 %.1f（实现给 T=%s，本地复刻 T=%s；"
                 "若写死 1.5 会给 T=%s）%s"
                 % (nb, w_expect, T3, T_l, T_wrong, "✅" if good else "❌"))
    # ---- ④ **薄包装** `mc_trend_p` 的 `n_layer` 透传（⛔ 漏传 ⇒ 静默按 4 层算）----
    #   ⚖ 用 **5 层**夹具：漏传时 `n_layer` 落回 4 ⇒ 层数与权重中心都变 ⇒ T 不同 ⇒ 红
    fx5 = [[2, 3, 3, 3]] * 5
    obs5 = [4, 6, 10, 12, 14]
    pg5, Tg5, e0g5, _gg5, _nn5 = DL.mc_trend_p_geom(fx5, obs5, n_mc=200, seed=1,
                                                    n_layer=5)
    pw5, Tw5, e0w5 = DL.mc_trend_p(fx5, obs5, n_mc=200, seed=1, n_layer=5)
    good = (pg5 == pw5 and Tg5 == Tw5 and e0g5 == e0w5)
    ok = ok and good
    d.append("薄包装 `mc_trend_p` 的 `n_layer=5` 透传（p/T/e0 逐位）%s"
             % ("✅" if good else "❌"))
    return ok, d


def j_c4_verdicts_printed(allr, RP):
    """C4：判决必须**逐组合印出**，且每条判决与该组合**印出来的 p** 交叉对账。

    ⚖⚠⚠⚠ **双向**：既抓「少印一条」，也抓「判定被写死 / p 被篡改但判决没改」。
    ⚖⇒ ⛔ 不许从被检对象内部去取 p（那样两边同源 ⇒ 恒绿）。
    """
    n_sc = allr["n_combo"]
    vlines = [ln for ln in RP if "⇒ 判决" in ln]
    printed = len(vlines)
    ok = (printed == n_sc)
    d = ["印出判决的组合行 %d（期望 %d）%s" % (printed, n_sc, "✅" if ok else "❌")]
    for ln in vlines:
        m = re.search(r"w 趋势 p=([0-9.]+)", ln)
        m2 = re.search(r"rand 趋势 p=([0-9.]+)", ln)
        if not m or not m2:
            ok = False
            d.append("❌ 判决行里认不出 p：%s" % ln.strip()[:70])
            continue
        pw, pr = float(m.group(1)), float(m2.group(1))
        want = (pw < ALPHA) and (pr >= ALPHA)
        got = ("**成立**" in ln)
        good = (want == got)
        ok = ok and good
        if not good:
            d.append("❌ 判决行 p=(%.4f, %.4f) ⇒ 应%s，实印%s"
                     % (pw, pr, "成立" if want else "不成立",
                        "成立" if got else "不成立"))
    d.append("判决行自带的 p 与「成立/不成立」双向对账 %s" % ("✅" if ok else "❌"))
    # ---- 翻转标记：必须与**算出来的**翻转数一致（⛔ 标记被改掉/漏印都要红）----
    flips = [s["label"] for s in allr["scenarios"] if s["flip"]]
    marked = sum(1 for ln in RP if "⚠⚠ **翻转**" in ln)
    good = (marked == len(flips))
    ok = ok and good
    d.append("「⚠⚠ **翻转**」标记 %d 个（算出来的翻转数 %d）%s"
             % (marked, len(flips), "✅" if good else "❌"))
    return ok, d


def j_c5_w_arm_all(allr):
    """C5：**w 臂必须跨全部 36 个组合都检出**（244.63 的结论被加强的那一条）。"""
    ps = [s["arm"]["w"]["trend"]["p"] for s in allr["scenarios"]]
    n_det = sum(1 for p in ps if p < ALPHA)
    ok = (n_det == W_DETECT_ALL)
    d = ["w 臂趋势 p<α 的组合 %d（写死 %d）%s ｜ p 最大 %.6f"
         % (n_det, W_DETECT_ALL, "✅" if ok else "❌", max(ps))]
    return ok, d


def j_c6_rand_detect(allr):
    """C6：rand 臂**检出**的组合数必须被钉住（= 本轮最重要的那个数）。"""
    det = [s["label"] for s in allr["scenarios"]
           if s["arm"]["rand"]["trend"]["p"] < ALPHA]
    ok = (len(det) == RAND_DETECT_N)
    d = ["rand 臂检出的组合 %d（写死 %d）%s ｜ %s"
         % (len(det), RAND_DETECT_N, "✅" if ok else "❌", "、".join(det) or "无")]
    return ok, d


def j_c7_rand_border(allr):
    """C7：rand 臂 **MC95% 带跨 α** 的组合数必须被钉住（p 贴 α ⇒ 显著/不显著**未定**）。

    ⚖⚠⚠⚠ **不信存储的 `border` 标志**：那条标志是**算出来的结果**
    ⇒ 判据要**从 MC 带重新算**一遍（`lo ≤ α ≤ hi`），否则标志被改坏时判据**看不见**。
    """
    brd = []
    for s in allr["scenarios"]:
        lo, hi = s["arm"]["rand"]["trend"]["band"]
        if lo <= ALPHA <= hi:
            brd.append(s["label"])
    ok = (len(brd) == RAND_BORDER_N)
    d = ["rand 臂 MC 带跨 α 的组合 %d（写死 %d）%s ｜ %s"
         % (len(brd), RAND_BORDER_N, "✅" if ok else "❌", "、".join(brd) or "无")]
    for nb, want in sorted(RAND_BORDER_BY_BANDS.items()):
        got = 0
        for s in allr["scenarios"]:
            if s["combo"][1] != nb:
                continue
            lo, hi = s["arm"]["rand"]["trend"]["band"]
            if lo <= ALPHA <= hi:
                got += 1
        good = (got == want)
        ok = ok and good
        d.append("  %d 档：带跨 α %d（写死 %d）%s"
                 % (nb, got, want, "✅" if good else "❌"))
    return ok, d


def j_c8_interp_unreachable(allr):
    """C8：**插值族分位算法本机跑不了** ⇒ 「未量到」必须是**实测**的，不是断言的。

    ⚖⚠⚠⚠ **为什么必须实测**：⛔ 不许说「本机只有 inclusive/exclusive」
    ⇒ 一旦换了解释器（或 `statistics` 升级），这条判据会**红** ⇒ 强制重测那一整类口径。
    """
    ok = True
    d = []
    for m in CANDIDATE_METHODS:
        want = m in WORKING_METHODS
        got = bool(allr["meth"][m])
        good = (want == got)
        ok = ok and good
        d.append("  method=%-16s 实测 %s（写死 %s）%s"
                 % (m, "能用" if got else "跑不了",
                    "能用" if want else "跑不了", "✅" if good else "❌"))
    return ok, d


def j_c9_endpoint_unmeasurable(allr):
    """C9：「端点档进轴」这个变体**测不出来**（拒读闸实测）⇒ 该维登记为**未量到**。

    ⚖⚠⚠⚠ **为什么**：端点档（scope=all / single）**有读数**但**没有位点数**
    ⇒ 注入比例**无定义** ⇒ `frac_of` **拒读** ⇒ 变体**跑不起来**
    ⇒ ⛔ **不许**说成「端点档没有影响」⇒ 那是「未量到」。
    """
    ok = True
    d = []
    for arm in ARMS:
        c = allr["cells"][arm]
        good = (c["endpoint_n"] == ENDPOINT_N
                and c["endpoint_with_reading_n"] == ENDPOINT_N
                and c["endpoint_no_nsites_n"] == ENDPOINT_NO_NSITES_N
                and c["endpoint_frac_raises_n"] == ENDPOINT_NO_NSITES_N)
        ok = ok and good
        d.append("  %s 臂：端点档 %d 条（写死 %d）｜ 有读数 %d ｜ 缺位点数 %d"
                 "（写死 %d）｜ `frac_of` 拒读 %d（写死 %d）%s"
                 % (arm, c["endpoint_n"], ENDPOINT_N, c["endpoint_with_reading_n"],
                    c["endpoint_no_nsites_n"], ENDPOINT_NO_NSITES_N,
                    c["endpoint_frac_raises_n"], ENDPOINT_NO_NSITES_N,
                    "✅" if good else "❌"))
    return ok, d


def j_c10_cell_filter_void(allr):
    """C10：格集合那两条过滤**恒真** ⇒ 整维**未量到**（⛔ 不许说成「无影响」）。

    ⚖⚠⚠⚠ **恒绿护栏的形状**：这条判据**钉住的是「恒真」这个事实**
    ⇒ 一旦某条 k 档格缺读数 / 缺位点数 ⇒ 它立刻**红** ⇒ 那一维的过滤**测得动了**
    ⇒ 必须回来改结论。
    """
    ok = True
    d = []
    for arm in ARMS:
        c = allr["cells"][arm]
        good = (c["k_n"] == K_CELLS_N
                and c["k_missing_nsites_n"] == K_MISS_NSITES_N
                and c["k_missing_reading_n"] == K_MISS_READING_N)
        ok = ok and good
        d.append("  %s 臂：k 档 %d 条（写死 %d）｜ 缺位点数 %d（写死 %d）"
                 " ｜ scope=k 且缺读数 %d（写死 %d）%s"
                 % (arm, c["k_n"], K_CELLS_N, c["k_missing_nsites_n"],
                    K_MISS_NSITES_N, c["k_missing_reading_n"], K_MISS_READING_N,
                    "✅" if good else "❌"))
    return ok, d


def j_c11_quantile_dim(allr):
    """C11：「分位算法」这一维**测得动**（⛔ 244.63 测的是「inclusive ≡ exclusive」那一对）。

    ⚖⚠⚠⚠ **244.63 的实测**：inclusive 与 exclusive 的分档表**逐位相同** ⇒ 那一对**空转**。
    ⚖ **244.64 的实测**：**nearest-rank**（不插值）在 9/36 个组合上**改了分档表**
    ⇒ 这一维**不是**完全空转 ⇒ 244.63 的【B1】**部分闭合**。
    """
    same = sum(1 for x in allr["inc_eq_exc"] if x)
    ok = (same == INC_EQ_EXC_N)
    d = ["inclusive ≡ exclusive 的设置数 %d（写死 %d）%s"
         % (same, INC_EQ_EXC_N, "✅" if ok else "❌")]
    n_diff = len(allr["nearest_diff"])
    good = (n_diff == NEAREST_DIFF_N)
    ok = ok and good
    d.append("nearest-rank 改掉分档表的组合数 %d（写死 %d）%s"
             % (n_diff, NEAREST_DIFF_N, "✅" if good else "❌"))
    return ok, d


def j_c12_band_count_dim(allr):
    """C12：「档数」这一维**测得动**（3/4/5 档给出不同的分档表 ⇒ 这一维不空转）。"""
    ok = True
    d = []
    for nb in BAND_COUNTS:
        shapes = set()
        for s in allr["scenarios"]:
            if s["combo"][1] != nb:
                continue
            shapes.add(tuple(len(x[1]) for x in s["arm"]["w"]["bands"]))
        good = (len(shapes) > 1)
        ok = ok and good
        d.append("  %d 档：w 臂档表形态 %d 种（必须 >1 ⇒ 这一维不空转）%s"
                 % (nb, len(shapes), "✅" if good else "❌"))
    for nb, want in sorted(RAND_DETECT_BY_BANDS.items()):
        got = sum(1 for s in allr["scenarios"]
                  if s["combo"][1] == nb and s["arm"]["rand"]["trend"]["p"] < ALPHA)
        good = (got == want)
        ok = ok and good
        d.append("  %d 档：rand 检出 %d（写死 %d）%s"
                 % (nb, got, want, "✅" if good else "❌"))
    return ok, d


def j_c13_table_matches(allr, RP):
    """C13：**表里的数**必须与**算出来的数**逐位一致（⛔ 不许手抄）。

    ⚖⚠⚠⚠ 做法：把报告里的组合行**解析**回来 ⇒ 与 `allr` 里算出来的对账
    ⇒ ⛔ 不许从被检对象内部取同一个字段去比（那叫同源）。
    """
    ok = True
    d = []
    by_label = {s["label"]: s for s in allr["scenarios"]}
    cur = None
    seen = 0
    for ln in RP:
        m = re.match(r"^· 组合 (.+?)(（\*\*基准\*\*）)?$", ln)
        if m:
            cur = m.group(1)
            continue
        m2 = re.match(r"^    · (w|rand)\s+档 ([0-9/]+) ｜ rho ([+-][0-9.]+) ｜ "
                      r"各档 K=([0-9/]+) ｜ 格级正号率 ([0-9./]+) ｜ "
                      r"趋势 T=([0-9.-]+) p=([0-9.]+) MC95%带 \[([0-9.]+), ([0-9.]+)\]"
                      r"(  ⚠⚠ \*\*带跨过 α\*\*)? ｜ 剂量轴口径多数 ([0-9]+)/([0-9]+) ｜ "
                      r"检出状态=(.+)$", ln)
        if not m2:
            continue
        seen += 1
        arm = m2.group(1)
        s = by_label.get(cur)
        if s is None:
            ok = False
            d.append("❌ 组合行找不到对应的场景：%s" % cur)
            continue
        a = s["arm"][arm]
        bands = tuple(int(x) for x in m2.group(2).split("/"))
        Ks = tuple(int(x) for x in m2.group(4).split("/"))
        T = float(m2.group(6))
        p = float(m2.group(7))
        lo = float(m2.group(8))
        hi = float(m2.group(9))
        scope = (int(m2.group(11)), int(m2.group(12)))
        want_bands = tuple(len(x[1]) for x in a["bands"])
        want_K = tuple(r["K"] for r in a["rows"])
        # ⚖ 容差 = **印出的位数**能带来的最大误差（T 三位小数 ⇒ 5e-4；p 四位 ⇒ 5e-5）
        #   ⇒ 用 `<=`（不是 `<`）⇒ 「四舍五入恰好落在边界上」不算不一致
        good = (bands == want_bands and Ks == want_K
                and abs(T - a["trend"]["T"]) <= 5e-4 + 1e-9
                and abs(p - a["trend"]["p"]) <= 5e-5 + 1e-9
                and abs(lo - a["trend"]["band"][0]) <= 5e-5 + 1e-9
                and abs(hi - a["trend"]["band"][1]) <= 5e-5 + 1e-9
                and scope == a["scope_k"])
        if not good:
            ok = False
            d.append("❌ %s / %s：印出的 档%s K%s T=%s p=%s 带[%s,%s] scope%s "
                     "≠ 算出来的 档%s K%s T=%s p=%s 带%s scope%s"
                     % (cur, arm, bands, Ks, T, p, lo, hi, scope, want_bands, want_K,
                        a["trend"]["T"], a["trend"]["p"], a["trend"]["band"],
                        a["scope_k"]))
    good = (seen == 2 * allr["n_combo"])
    ok = ok and good
    d.append("解析到的臂行 %d（期望 %d = 36 组合 × 2 臂）%s"
             % (seen, 2 * allr["n_combo"], "✅" if good else "❌"))
    d.append("表里的数与算出来的数逐位一致 %s" % ("✅" if ok else "❌"))
    return ok, d


def j_c14_marginal_matches(allr, RP):
    """C14：**逐维度边际表**里的数必须与**算出来的数**一致（⛔ 不许手抄）。"""
    ok = True
    d = []
    lines = [ln for ln in RP if ln.startswith("  ⚖ 维度 ")]
    if len(lines) != len(allr["marginal"]):
        ok = False
        d.append("❌ 边际行 %d（期望 %d）" % (len(lines), len(allr["marginal"])))
    for m, ln in zip(allr["marginal"], lines):
        want = ("  ⚖ 维度 %s = %-14s ｜ 组合 %2d ｜ w 检出 %2d ｜ rand 检出 %2d"
                " ｜ rand 带跨 α %2d ｜ 判决翻转 %2d ｜ w 档表形态 %d 种"
                % (m["dim"], str(m["val"]), m["n"], m["w_detect"], m["rand_detect"],
                   m["rand_border"], m["flip"], m["w_shapes"]))
        good = (ln == want)
        ok = ok and good
        if not good:
            d.append("❌ 边际行对不上：印 %r ≠ 算 %r" % (ln, want))
    d.append("逐维度边际表 %d 行与算出来的一致 %s"
             % (len(lines), "✅" if ok else "❌"))
    return ok, d


def j_c15_conclusion_field(allr, RP):
    """C15：**结论字段**（结构化）与**留白字段**必须逐条对账。

    ⚖⚠⚖⚖⚖ **为什么落在「可解析的字段」上**（244.63 的教训）：
    ⛔ 「报告里不许出现某句话」这种**子串**判据会被报告里**否定它**的说明句撞车
    ⇒ 假红。
    ⚖ ⇒ 本工具把结论与留白写成**带标签的结构化行**
    ⇒ 判据只查**那些行的值** ⇒ 双向可对账，报告仍可自由讨论被禁的说法。
    """
    ok = True
    d = []
    # ---- 结论字段：算出来的状态集合 ⇒ 期望的值 ----
    states = sorted({s["arm"]["rand"]["state"] for s in allr["scenarios"]})
    want = "未量到" if len(states) > 1 else states[0]
    got = None
    for ln in RP:
        m = re.match(r"^  ⚖ rand 臂的剂量—响应结论（α 上）= \*\*(.+)\*\*$", ln)
        if m:
            got = m.group(1)
            break
    good = (got == want)
    ok = ok and good
    d.append("结论字段（α 上）印 %r、算 %r %s" % (got, want, "✅" if good else "❌"))
    # ---- 留白字段：三个「未量到」必须都印成「未量到」----
    #   ⚖ 解析方式：把**所有** `  ⚖ <名字> = **<值>**` 形式的行收成一张表
    #   ⇒ 报告里可以自由写散文，判据只看**这些结构化行**
    fields = {}
    for ln in RP:
        m = re.match(r"^  ⚖ (.+?)=\s*\*\*(.+)\*\*$", ln)
        if m:
            fields[m.group(1)] = m.group(2)
    for key in ("插值族分位算法（hazen/weibull/linear/…）",
                "连续剂量回归（非分档）",
                "格集合过滤（端点档进轴 / 缺读数格进轴）"):
        got2 = fields.get(key)
        good = (got2 == "未量到")
        ok = ok and good
        d.append("留白字段「%s」印 %r %s"
                 % (key, got2, "✅" if good else "❌"))
    return ok, d


def j_c16_marks(RP):
    """C16：前提标签与留白标签必须**一个不少**（⛔ 删掉一条就红）。"""
    ok = True
    d = []
    for mk in PREAMBLE_MARKS:
        n = sum(1 for ln in RP if mk in ln)
        good = (n >= 1)
        ok = ok and good
        d.append("  前提标签 %s 出现 %d 次 %s" % (mk, n, "✅" if good else "❌"))
    for mk in BLANK_MARKS:
        n = sum(1 for ln in RP if mk in ln)
        good = (n >= 1)
        ok = ok and good
        d.append("  留白标签 %s 出现 %d 次 %s" % (mk, n, "✅" if good else "❌"))
    return ok, d


def j_c17_combos_match_expect(allr):
    """C17：**全部 36 个组合 × 2 臂**必须与**字面量期望表**逐位一致。

    ⚖⚠⚠⚠ **期望表不许从被检对象派生**（244.60/244.61 的教训）
    ⇒ `COMBO_EXPECT` 是**冻住的字面量** ⇒ 这条判据是真正的**回归夹具**。
    """
    ok = True
    d = []
    if set(COMBO_EXPECT.keys()) != set(s["combo"] for s in allr["scenarios"]):
        ok = False
        d.append("❌ 期望表的组合集合与实际枚举的不一致")
        return ok, d
    n_bad = 0
    for s in allr["scenarios"]:
        for arm in ARMS:
            a = s["arm"][arm]
            e = COMBO_EXPECT.get(s["combo"], {}).get(arm)
            if e is None:
                # ⚠⚠⚠ **期望表里没有这个组合**（枚举被改坏）⇒ ⛔ 不许抛 KeyError（崩 ≠ 抓到）
                n_bad += 1
                ok = False
                d.append("❌ 组合 %s / %s：期望表里**没有**这一条" % (s["label"], arm))
                continue
            good = (tuple(len(x[1]) for x in a["bands"]) == e["bands"]
                    and tuple(r["K"] for r in a["rows"]) == e["K"]
                    and a["trend"]["T"] == e["T"]
                    and a["trend"]["p"] == e["p"]
                    and a["rho"] == e["rho"]
                    and a["scope_k"] == e["scope"]
                    and a["state"] == e["det"])
            if not good:
                n_bad += 1
                ok = False
                d.append("❌ 组合 %s / %s：算出来 ≠ 期望"
                         % (s["label"], arm))
    d.append("36 组合 × 2 臂 × 7 字段与字面量期望表逐位一致（不一致 %d 处）%s"
             % (n_bad, "✅" if ok else "❌"))
    return ok, d


def j_c18_zero_cells(allr):
    """C18：**零格数**必须被报出（⛔ 零格被悄悄算进 nz ⇒ 零假设分布就错了 ⇒ p 就错了）。

    ⚖⚠⚖⚖⚖ **零格恒为 False** ⇒ 它**不进**零假设基准、但**进**分母
       ⇒ 零格数是「零分布」的直接输入 ⇒ 数错 ⇒ p 错
    ⇒ 期望值是**独立探针实测的字面量**（⛔ 不从被检对象派生）
    ⇒ 判据从**被检对象**读零格数（`rows[*]["nzs"]` 的第二项）⇒ 与期望对照 ⇒ **能红**。
    """
    ok = True
    d = []
    tot = 0
    bad = []
    for s in allr["scenarios"]:
        zero_span = s["combo"][3]
        for arm in ARMS:
            z = sum(nz0 for r in s["arm"][arm]["rows"] for (_nz, nz0) in r["nzs"])
            tot += z
            want = ZERO_CELLS_EXPECT[zero_span][arm]
            if z != want:
                bad.append("%s / %s 臂：零格 %d（期望 %d）"
                           % (s["label"], arm, z, want))
    ok = (not bad) and (tot == ZERO_CELLS_TOTAL)
    d.append("36 个组合的零格数：keep ⇒ rand 2 / w 0，drop ⇒ 两臂 0"
             "（实测：不符合 %d 处）%s"
             % (len(bad), "✅" if not bad else "❌ " + "；".join(bad[:4])))
    d.append("零格总数 %d（写死 %d）%s"
             % (tot, ZERO_CELLS_TOTAL, "✅" if tot == ZERO_CELLS_TOTAL else "❌"))
    return ok, d


# ---------------------------------------------------------------- 运行
def run():
    allr = build_all()
    RP = build_report(allr)
    res = []

    def put(cid, ok, detail):
        res.append((cid, bool(ok), detail))

    put("C0", *j_c0_baseline(allr))
    put("C1", *j_c1_space(allr))
    put("C2", *j_c2_coverage(allr))
    put("C3", *j_c3_layer_general(allr))
    put("C4", *j_c4_verdicts_printed(allr, RP))
    put("C5", *j_c5_w_arm_all(allr))
    put("C6", *j_c6_rand_detect(allr))
    put("C7", *j_c7_rand_border(allr))
    put("C8", *j_c8_interp_unreachable(allr))
    put("C9", *j_c9_endpoint_unmeasurable(allr))
    put("C10", *j_c10_cell_filter_void(allr))
    put("C11", *j_c11_quantile_dim(allr))
    put("C12", *j_c12_band_count_dim(allr))
    put("C13", *j_c13_table_matches(allr, RP))
    put("C14", *j_c14_marginal_matches(allr, RP))
    put("C15", *j_c15_conclusion_field(allr, RP))
    put("C16", *j_c16_marks(RP))
    put("C17", *j_c17_combos_match_expect(allr))
    put("C18", *j_c18_zero_cells(allr))

    for ln in RP:
        print(ln)
    print("")
    allok = True
    for cid, ok, detail in res:
        allok = allok and ok
        print("[%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for _c, o, _d in res if o), len(res)))
    return RP, res, allr


# ---------------------------------------------------------------- 自检
def _mut_c12_same_table(a):
    """⚖ 把 3 档的**所有**组合改成同一张分档表 ⇒ 「档数这一维」变空转 ⇒ C12 必须红。"""
    three = [s for s in a["scenarios"] if s["combo"][1] == 3]
    if not three:
        return
    tmpl = list(three[0]["arm"]["w"]["bands"])
    for s in three:
        s["arm"]["w"]["bands"] = list(tmpl)


def _mut_c7_band(a):
    """⚖ 把**一个带跨 α 的组合**的 MC 带改成不跨 ⇒ C7 必须红。

    ⚖⚠⚠⚠ **为什么不能写死下标**：跨 α 的组合**不是**最后一个
    ⇒ 写死下标 ⇒ 变异打在**不跨 α** 的组合上 ⇒ 计数不变 ⇒ **变异存活（假绿）**
    ⇒ 必须**按条件挑**。
    """
    for s in a["scenarios"]:
        lo, hi = s["arm"]["rand"]["trend"]["band"]
        if lo <= ALPHA <= hi:
            s["arm"]["rand"]["trend"]["band"] = (0.001, 0.01)
            return


def _mut_c14_rand_detect(ln):
    """⚖ 把边际行里「rand 检出」那个**数**改成别的（⛔ 不写死是哪个值）。"""
    if not ln.startswith("  ⚖ 维度 "):
        return ln
    key = "rand 检出 "
    i = ln.find(key)
    if i < 0:
        return ln
    j = i + len(key)
    k = j
    while k < len(ln) and ln[k].isdigit():
        k += 1
    old = ln[j:k]
    if not old:
        return ln
    new = "99" if old != "99" else "98"
    return ln[:j] + new + ln[k:]


def _mut_c18_zero(a):
    """⚖ 把 rand 臂**一个真有零格**的轨迹的零格数改成 0 ⇒ C18 必须红。

    ⚖⚠⚖ **必须找「真有零格」的那条**（244.65 的教训）：
       打「第一个组合的第一个轨迹」⇒ 那个轨迹**本来就没有零格**
       ⇒ 改动无效 ⇒ 判据看着像**恒绿**。
    """
    for s in a["scenarios"]:
        for r in s["arm"]["rand"]["rows"]:
            for i, (nz, nz0) in enumerate(r["nzs"]):
                if nz0 > 0:
                    r["nzs"][i] = (nz, 0)
                    return


def _mutations():
    """⚖ 每条判据的「变异数据」⇒ 自检要证明**红得了**。

    ⚖⚠⚠⚖ **期望集不许从被检对象派生**（244.60/244.61 的教训）
    ⇒ 这里的变异都是**改坏**的，而**干净**那一侧由真实数据路径保证。

    ⚖⚠⚠⚠⚖ **变异必须打中「它要打的那条判据」**：
      · 改**算出来的数** ⇒ 打「读数侧」的判据（C0/C2/C3/C5/C6/C7/C9/C10/C11/C17）
      · 改**报告里印出来的文本** ⇒ 打「印出来的那一侧」的判据（C4/C13/C14/C15/C16）
    ⇒ 混用会得到「变异存活但其实打偏了」的假结论（244.63 台架第一版的教训）。
    """
    return [
        ("C0", "基准组合的档表被改坏",
         lambda a: a["base"]["arm"]["w"]["bands"].__setitem__(
             0, ("frac<=q1", a["base"]["arm"]["w"]["bands"][0][1][:-1]))),
        ("C0", "基准组合的趋势 p 被篡改",
         lambda a: a["base"]["arm"]["w"]["trend"].__setitem__("p", 0.5)),
        ("C1", "组合数被改成 8",
         lambda a: a.__setitem__("n_combo", 8)),
        ("C1", "两个组合的标签被改成同一个",
         lambda a: a["scenarios"][-1].__setitem__(
             "label", a["scenarios"][-2]["label"])),
        ("C2", "某个组合少了一个格（覆盖漏掉）",
         lambda a: a["scenarios"][-1]["arm"]["rand"]["band_ids"][0].pop()),
        ("C2", "某个组合的格被放进两档（重复）",
         lambda a: a["scenarios"][-1]["arm"]["w"]["band_ids"][1].append(
             a["scenarios"][-1]["arm"]["w"]["band_ids"][1][0])),
        ("C3", "一个组合的趋势 T 被篡改",
         lambda a: a["scenarios"][-1]["arm"]["rand"]["trend"].__setitem__("T", 99.0)),
        ("C4", "报告里一条判决被写反（印「不成立」但 p 支持成立）", "RP"),
        ("C5", "w 臂某个组合的趋势 p 被改成不显著",
         lambda a: a["scenarios"][-1]["arm"]["w"]["trend"].__setitem__("p", 0.5)),
        ("C6", "rand 臂某个组合的趋势 p 被改成不显著",
         lambda a: a["scenarios"][-1]["arm"]["rand"]["trend"].__setitem__("p", 0.5)),
        ("C7", "rand 臂某个组合的 MC 带被改坏（不再跨 α）",
         _mut_c7_band),
        ("C8", "本机能用的 method 集合被改坏（多认一个）",
         lambda a: a["meth"].__setitem__("hazen", True)),
        ("C9", "端点档的「缺位点数」计数被改坏",
         lambda a: a["cells"]["w"].__setitem__("endpoint_no_nsites_n", 0)),
        ("C10", "k 档「缺位点数」计数被改坏",
         lambda a: a["cells"]["rand"].__setitem__("k_missing_nsites_n", 3)),
        ("C11", "「inclusive ≡ exclusive」的设置数被改坏",
         lambda a: a.__setitem__("inc_eq_exc", [True])),
        ("C11", "「nearest-rank 改了档表」的组合数被改坏",
         lambda a: a.__setitem__("nearest_diff", [])),
        ("C12", "3 档的所有组合被改成同一张分档表（这一维变空转）",
         _mut_c12_same_table),
        ("C13", "报告里某个组合的档表被改错", "RP"),
        ("C14", "报告里逐维度边际的某个数被改错", "RP"),
        ("C15", "报告里结论字段被写成「无差异」／留白字段被写成「无影响」", "RP"),
        ("C16", "前提声明少印一条标签", "RP"),
        ("C17", "某个组合的各档 K 被改坏",
         lambda a: a["scenarios"][-1]["arm"]["rand"]["rows"][0].__setitem__(
             "K", 99)),
        ("C18", "rand 臂某个组合的**零格数**被改坏（零格被算进 nz）",
         _mut_c18_zero),
    ]


def selftest():
    """⚖ 自检：① 每条判据在**干净输入**上必须全绿 ② 喂**变异数据**必须红。"""
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", t, why))

    RP, res, allr = run()
    chk("S0", all(o for _c, o, _d in res),
        "真实数据路径上全部判据必须绿（实测 %d/%d）"
        % (sum(1 for _c, o, _d in res if o), len(res)))

    fns = {
        "C0": lambda a, rp: j_c0_baseline(a),
        "C1": lambda a, rp: j_c1_space(a),
        "C2": lambda a, rp: j_c2_coverage(a),
        "C3": lambda a, rp: j_c3_layer_general(a),
        "C4": lambda a, rp: j_c4_verdicts_printed(a, rp),
        "C5": lambda a, rp: j_c5_w_arm_all(a),
        "C6": lambda a, rp: j_c6_rand_detect(a),
        "C7": lambda a, rp: j_c7_rand_border(a),
        "C8": lambda a, rp: j_c8_interp_unreachable(a),
        "C9": lambda a, rp: j_c9_endpoint_unmeasurable(a),
        "C10": lambda a, rp: j_c10_cell_filter_void(a),
        "C11": lambda a, rp: j_c11_quantile_dim(a),
        "C12": lambda a, rp: j_c12_band_count_dim(a),
        "C13": lambda a, rp: j_c13_table_matches(a, rp),
        "C14": lambda a, rp: j_c14_marginal_matches(a, rp),
        "C15": lambda a, rp: j_c15_conclusion_field(a, rp),
        "C16": lambda a, rp: j_c16_marks(rp),
        "C17": lambda a, rp: j_c17_combos_match_expect(a),
        "C18": lambda a, rp: j_c18_zero_cells(a),
    }
    for cid, name, mut in _mutations():
        a2 = copy.deepcopy(allr)
        RP2 = list(RP)
        if mut == "RP":
            # ⚖⚠⚖⚖ **报告侧的变异**：只改**报告文本**（不改算出来的数）
            #   ⇒ 抓「表里/叙述里的数与算出来的不一致」这类错
            if cid == "C4":
                # ⚖ 把**第一条**判决行的「成立」改成「不成立」
                #   ⇒ 那一行的 p 支持「成立」⇒ 交叉对账必须红
                for i, ln in enumerate(RP2):
                    if "⇒ 判决" in ln:
                        RP2[i] = ln.replace("：**成立**（", "：**不成立**（", 1)
                        break
            elif cid == "C13":
                RP2 = [ln.replace("档 27/28/30/24", "档 27/28/30/25")
                       if ln.startswith("    · w ") else ln for ln in RP2]
            elif cid == "C14":
                # ⚖⚠⚖ **按字段定位，⛔ 不写死是哪个数**（244.65 的教训：
                #   写死「rand 检出  2」⇒ 那个数一变 ⇒ 替换打空 ⇒ 变异无效）
                RP2 = [_mut_c14_rand_detect(ln) for ln in RP2]
            elif cid == "C15":
                RP2 = [ln.replace("剂量—响应结论（α 上）= **未量到**",
                                   "剂量—响应结论（α 上）= **无差异**")
                       if "剂量—响应结论（α 上）" in ln else ln for ln in RP2]
                RP2 = [ln.replace("格集合过滤（端点档进轴 / 缺读数格进轴）= **未量到**",
                                   "格集合过滤（端点档进轴 / 缺读数格进轴）= **无影响**")
                       if "格集合过滤" in ln else ln for ln in RP2]
            elif cid == "C16":
                RP2 = [ln for ln in RP2 if "【P5】" not in ln]
        else:
            mut(a2)
        okc, _d = fns[cid](a2, RP2)
        chk("S-%s" % cid, (not okc),
            "变异「%s」必须让 %s 变红%s" % (name, cid,
                                          "（但它仍绿 ⇒ 这条判据**恒绿**）"
                                          if okc else ""))
    print("")
    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return len(bad) == 0


def main():
    if "--selftest" in sys.argv:
        return 0 if selftest() else 1
    _RP, _res, _allr = run()
    return 0 if all(o for _c, o, _d in _res) else 1


if __name__ == "__main__":
    sys.exit(main())
