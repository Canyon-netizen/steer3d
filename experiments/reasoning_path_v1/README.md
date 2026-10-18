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
