# Reasoning Path v1

目标：把「模型自己的推理路线」和「施加向量后路线怎么移动」放在同一个可视化里。

- 数据：6 条 AIME 轨迹 × 73 个窗口 token × 5 个 arm（baseline / w / mean_g / sparse_g / random）
- 模型：Qwen3-1.7B，远端 node1011 空卡，float32，eager
- 注入层：20；查看层：21；dose：0.1 × anchor input norm
- teacher-forced continuation：注入后仍用同一段 token，不做自由生成
- 完整 baseline route：本地 npz 的 layer-21 hidden states，PCA 到 3D

## 文件

- sources.json：6 个 source 的 prompt/token ids
- remote_l21/reasoning_path.json：远端 capture 的元数据/behavior
- remote_l21/reasoning_path_states.npz：6×5×3 层 hidden states（48MB，未入库）
- reasoning_path.json：PCA 坐标、箭头、behavior、summary（入库）
- reasoning_path.png：3D route + vector effect + across-source bars
- reasoning_path_behaviour.png：window 内 Δlogp
- reasoning_path.html：自包含交互页（静态图 fallback）
- frontend/public/reasoning-path.html：网页副本

## 关键读数

全局（6 sources 平均）：

| arm | anchor Δlogp | mean arrow norm | mean ΔH |
|---|---:|---:|---:|
| w | +0.083 | 0.380 | -0.0007 |
| mean_g | +0.319 | 0.217 | -0.0066 |
| sparse_g | +0.293 | 0.176 | -0.0056 |
| random | -0.006 | 0.099 | -0.0001 |

⇒ **几何位移大 ≠ 目标效果好**：w 把 hidden state 推得更远，但 anchor Δlogp 只有 mean_g 的约 1/4；
mean_g 的位移更小但更“对靶”。

PCA 前三个方向解释方差约 6.3% / 3.5% / 2.9%——3D 只是投影，不是完整流形。

## 边界

- 单层（21）、单 dose、6 source；teacher-forced，不是自由生成。
- 箭头是同一 token 位置的 hidden-state 位移，不是因果路径。
- 只在 anchor 注入一次；不是 per-token controller。
- 还没有 head/OV attribution；下一轮接。

## 复现

远端采集（空卡）：

    cd /data/home/zhourui/reasoning_path_20261018
    /data/home/zhourui/miniconda3/envs/easysteer/bin/python collect_reasoning_path.py       --sources sources.json --model /data/model/Qwen3-1.7B --vectors vectors       --out results_l21 --layers 20,21,27 --inject-layer 20 --dose 0.1 --gpu 2

本地构建：

    python3 backend/examples/build_reasoning_path.py

测试：

    python3 -m pytest backend/tests/test_reasoning_path.py -q

## Head / OV & MLP attribution at anchor

Remote capture results_attr/vector_attribution.json（单点、layer 20/21）：

| arm (layer 20) | mean MLP ΔDLA | mean sum head ΔDLA |
|---|---:|---:|
| w | +0.96 | +0.25 |
| mean_g | +31.06 | +0.56 |
| sparse_g | +19.04 | +0.54 |
| random | -0.86 | +0.09 |

⇒ 在这个 marker 设置下，anchor 处 vector 的直接 logit 效应主要来自 MLP write，
attention head 的直接 DLA 变化小一个数量级以上。注意：这是 layer 20/21 单点 DLA，
不是完整 edge graph，也不代表其它层/位置没有 head 贡献。

Top heads（mean_g, layer 20）：head 6 (+0.160), 5 (+0.111), 12 (+0.108), 9 (+0.102)。
Layer 21 top：head 0 (+0.146), 14 (+0.076), 10 (+0.075), 11 (+0.071)。

新增文件：reasoning_path_heads.png。

## Causal patching（2026-10-18 补）

对 mean_g / w 在 anchor 做组件 patching（6 sources 平均）：

| component | mean_g sufficiency | mean_g necessity | w sufficiency |
|---|---:|---:|---:|
| mlp20 | 0.788 | 0.970 | 0.100 |
| mlp21 | 0.648 | 0.982 | -0.026 |
| mlp_both | **0.868** | 0.945 | -0.087 |
| heads20 (top4) | 0.052 | 1.000 | 0.012 |
| heads21 (top4) | 0.074 | 1.000 | 0.018 |
| heads_both | 0.123 | 1.000 | 0.034 |

解释：

- **sufficiency**：把 steered 的 MLP20+21 write patch 回 baseline，能恢复约 87% 的 mean_g Δlogp；
  heads 只有约 12% → MLP write 是充分通道，heads 不是。
- **necessity** 接近 1：把 baseline 单个组件 patch 进 steered，效果几乎不消失 → 下游可补偿，
  效应是分布式/冗余的，不是单点开关。
- w 的 MLP sufficiency 接近 0 → w 的效果不是由 MLP write 传递，和它弱且非对靶一致。

新增文件：reasoning_path_causal.png。
