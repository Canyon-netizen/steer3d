# Reasoning Path & Vector Intervention

> 一句话：把 full baseline hidden-state route 和 anchor 注入后的局部轨迹放在同一张 PCA 图里，
> 看“向量把路线推到哪里”，以及“推得远”是否等于“推得准”。

页面：/reasoning-path.html
数据：experiments/reasoning_path_v1/reasoning_path.json
图：experiments/reasoning_path_v1/reasoning_path.png
生成器：backend/examples/build_reasoning_path.py
远端采集：backend/examples/collect_reasoning_path.py

## 这次做了什么

1. 6 条 AIME 轨迹，选 marker 前一个 token 作为 anchor；
2. 在远端空卡上跑 5 个 arm：baseline / w / mean_g / sparse_g / random；
3. 在 anchor 注入一次（dose 0.1 × input norm），teacher-forced 继续同一段 token；
4. 记录 layer 21（以及 20/27）的 hidden states 和窗口内 behavior；
5. 用本地 npz 的完整 baseline hidden states 拟合 PCA，投影 full route + steered window；
6. 画箭头：同一 token 位置 baseline→steered 的位移；
7. 汇总 anchor Δlogp、mean arrow norm、mean ΔH。

## 结果

全局（6 sources 平均）：

| arm | anchor Δlogp | mean arrow norm | mean ΔH |
|---|---:|---:|---:|
| w | +0.083 | 0.380 | -0.0007 |
| mean_g | +0.319 | 0.217 | -0.0066 |
| sparse_g | +0.293 | 0.176 | -0.0056 |
| random | -0.006 | 0.099 | -0.0001 |

两个直接结论：

- **mean_g / sparse_g 在 anchor 上更有效**（+0.32 / +0.29），而 w 只有 +0.08；
- **w 的几何位移最大（0.38）**，但目标效果最小——说明“把 state 推得远”不等于“把行为推向目标”。

PCA 前三个方向只解释 6.3% / 3.5% / 2.9% 的方差，所以 3D 图是局部可视化，
不能把 3D 距离当成完整流形距离。

## 页面怎么读

- 左侧 3D：每个 source 的完整 baseline route（灰色），窗口 baseline（白）和 +mean_g（黄），
  黄色箭头 = 同一 token 位置的 baseline→steered 位移；
- 右侧曲线：窗口内 Δ next-token logp（相对 baseline），anchor 虚线是 marker 前的位置；
- 底部表：每个 source 的 anchor Δlogp / mean arrow / mean ΔH；
- 选择 source/arm 可切换；自动旋转只是看几何，不改变数据。

## 能说 / 不能说

能说：

- 在同一段推理上，向量注入会在后续 token 产生可测的 hidden-state 位移；
- mean_g/sparse_g 比 w 更“对靶”，w 的位移更大但效果更弱；
- 可以用 full route + local arrows 展示“路线被推到哪里”。

不能说：

- 箭头是因果路径；它只是 hidden-state 位移；
- teacher-forced 窗口等于自由生成；
- 3D PCA 是完整流形；
- 单层/单 dose/6 source 的结论可外推。

## 下一步

1. 对 top 位移位置做 head/OV attribution，回答“是哪条通路把路线推走”；
2. 多 dose / 多 anchor，看位移是否可预测 Δlogp；
3. 用 independent split 验证“箭头方向 → 行为”的映射；
4. 接 state-dependent guidance，比较固定向量 vs 流形切向控制。

## Head / OV & MLP attribution（2026-10-18 补）

对 6 个 source 的 anchor 做单点 head/OV + MLP attribution：

| arm (layer 20) | mean MLP ΔDLA | mean sum head ΔDLA |
|---|---:|---:|
| w | +0.96 | +0.25 |
| mean_g | **+31.06** | +0.56 |
| sparse_g | +19.04 | +0.54 |
| random | -0.86 | +0.09 |

结论：

- 在这个 marker 设置下，vector 的直接 logit 效应主要落在 MLP write；
- attention head 的直接 ΔDLA 小一个数量级以上；
- 因此不能简单套用“steering 主要走 OV circuit”的结论——至少对 marker logp，
  block-20/21 的 MLP 是更大的直接通道；
- 这是单点 DLA，不是完整 edge graph；head 的间接/多层贡献仍需 path patching。

图：reasoning_path_heads.png
