# Steering Design Guide

> **一句话**：把已有的 hidden-state 读数、原生单元阻断/恢复、logit lens 产物合成一页
> **可执行的设计指南**：哪一层承载效应、哪一层抵消、该选什么方向/剂量/层，以及
> **哪些结论还没有测**。

页面：/steering-design
数据：experiments/steering_design_v1/steering_design.json
生成器：backend/examples/build_steering_design.py
分析模块：backend/core/steering_design.py

## 这个指南回答什么

它不回答“模型在想什么”，也不重跑模型。它把四类已有证据放在同一张设计桌上：

1. **读出（readout）**：w·U 对 7 个 marker id 的静态点积、logit lens 的逐层 p(final token)。
2. **因果（causal）**：+v / -v 三档剂量、四种措辞条件下的正确性读数。
3. **层策略（layer）**：block 20-27 的组级 block / restore 效应。
4. **单元策略（unit）**：选中的 256 个原生单元（每层 32 个）及其选择分数。

## 符号约定（读表之前必须知道）

    block   = score(+v) - score(+v 中把该组单元恢复为 baseline)
    restore = score(baseline 中把该组单元替换为 +v) - score(baseline)
    compensation = (block + restore) / 2
    support      = -compensation

- support > 0：该层单元与 +v 的**净效应同向**（当前净效应为负）。
- support < 0：该层单元在**抵消**净效应，是“移除/反转”优先测试的对象。
- 判 supporting / compensating 要求 block 与 restore **同号**且均值超过 0.02 地板；
  否则记 weak。地板是设计选择，不是统计显著性门槛。

## 当前结论（2026-10-17 产物）

- 7/7 marker id 的 w·U 为正（freq-weighted +0.18424），但 +v 对正确性的主剂量效应是
  **-0.06641**；读出与因果是**两个不同的目标**。
- block 20 的单元与负净效应同向（support +0.04750，逐题同号 5/6）；block 25 的单元
  在抵消它（compensation +0.08588，逐题同号 6/6）。block 21/24 同向抵消但幅度更小；
  block 24 也是 6/6，是 block 25 之外第二个逐题稳定的抵消层。
- -v 在三档剂量都为正（+0.01768 / +0.10387 / +0.30337）；+v 在正确性上方向是错的。
- 措辞会改变符号：correct×neutral +0.10610，correct×self-check -0.25971。
- 最终 token 的 logit-lens p_final 在 layer 0 为 0.00019，layer 18 为 0.12629，
  layer 27 为 0.93604：**答案信息在后期层才线性可解码**。
- **hidden-state readout atlas（30 条轨迹 / 384 个 marker）**：best layer 21，
  raw cos AUC **0.1991**、oriented **0.8009**、orientation **-1**，24/24 条轨迹为负向；
  norm control 0.5632，残差化 raw 0.1927。⇒ **marker 位置的 cos(h,w) 更低**，
  w·h 不是正向 marker 读出；静态 w·U 不能外推到状态投影。
- **per-marker 符号分裂**：7196（n=105）在 layer 17 正向（raw cos AUC 0.7305），
  其余 marker 为负（6771 0.1453@27、10061 0.1620@21、14190 0.3690@19、13824 0.0725@27）；
  88190/80022 n<10 不可判。⇒ set-level AUC 掩盖了符号分裂；不能用一个全局符号/层
  服务全部 marker。
- **construction probe（6 sites / 3 markers）**：block-20 局部梯度 g 在全部 6 个 site
  上提高 f = log p(marker)，是三个 marker 的最佳候选（均值 +0.0159 / +0.3643 / +0.3419）；
  w 对 7196 平均为负、对 10061/6771 明显弱于 g；w+g ≈ g。⇒ 用 g 作为构造基线，
  但它是局部白盒方向，不是语义向量。
- **held-out transfer（2 calib + 2 held-out / marker）**：用 calibration 平均梯度构造的方向
  在 held-out site 上仍提高 f：7196 +0.6514（w +0.1026）、10061 +0.4363（w +0.0192）、
  6771 +0.1958（w +0.1314）；sparse 10% 保留 78-100%。cross：7196 方向对其它 marker 为负
  （-0.457 / -5.711），10061/6771 方向对其它 marker 为正。⇒ **per-marker 方向可迁移，
  但不能用一个方向服务所有 marker**。
- **alpha / side-effect sweep（6 held-out sites）**：在 mean KL <= 0.1 内，有用窗口是
  7196 sparse g@0.02（+0.2639, KL 0.0734）、10061 mean g@0.02（+0.2005, KL 0.0851）、
  6771 w@0.1（+0.1314, KL 0.0850）。dose 0.05 下 mean g 的 Δlogp 最大但 KL 也大
  （7196 +0.563/KL 0.672），sparse g 同 dose KL 更低（+0.476/KL 0.366），w 最安全但更弱。
  ⇒ **按 KL 预算选 direction/dose，不要只看 Δlogp**。
- **compiled recipe**：每个 marker 已编译一个可复现的 .npy 候选方向（7196 sparse g@0.02、
  10061 mean g@0.02、6771 w@0.1），并在 held-out site 上验证。⇒ 这是设计的**起点**，
  不是生产级向量；verification 复用 transfer/sweep 的 held-out site，不是第三个独立 split。

## 怎么用

1. 先在页面上确认 target：marker 读出还是 correctness？两者不可混用。
2. 看 Layer Strategy：红色层不要用 +v 原方向当正控制；绿色层是“移除/反转抵消单元”
   的第一批候选。表里的“逐题同号”给出 block/restore 在 6 道留出题里与本层均值同号的
   题数；出现 x/6 就说明该层有反向案例。
3. 看 Dose：如果目标是 correctness，当前 +v 的符号是反的；-v 三档都为正。
4. 看 Readout：marker 全正只说明“可读”，不说明“可控”；唯一的读出轴（confidence）
   是 tautological，不能当专属方向。
5. 看 Units：这张表是**响应排序**，不是因果排序；单单元因果尚未测。
6. 看 Hidden-state readout：set-level w·h 在 layer 21 与 marker **反相关**；
   但 per-marker 是分裂的（7196 正向，其余负向）。先选目标 marker，再谈层/符号。
   完整热图与 per-marker 表见 /readout-atlas 与 docs/READOUT_ATLAS.md。
7. 看 Construction：g = ∇_h log p(marker) 是当前唯一在全部 site 上提高 f 的候选；
   但它依赖前缀/层/剂量，不能当通用配方。见 /steering-construction。
8. 看 Held-out transfer：mean g 能迁移到没参与构造的 site；先选 marker，再用该 marker 的
   calibration 平均梯度，sparse 10% 是可解释变体。cross 矩阵告诉你方向是否 marker-specific。
9. 看 Alpha/side-effect：按 KL 预算选 direction/dose；mean g 效果大但代价大，sparse g 更省，
   w 最安全但更弱。见 /steering-sweep。
10. 看 Compiled recipe：每个 marker 有 .npy + dose + file sha；换前缀/层/模型后必须重新验证。
    见 /steering-recipe。
11. 看 Recommendations：每条都带 evidence 与 confidence；high priority 不等于显著。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_readout_atlas.py
    .cache/venv_steer/bin/python backend/examples/probe_steering_construction.py
    .cache/venv_steer/bin/python backend/examples/build_steering_transfer.py
    .cache/venv_steer/bin/python backend/examples/build_steering_sweep.py
    .cache/venv_steer/bin/python backend/examples/compile_steering_recipe.py
    python3 backend/examples/build_steering_design.py

输出：

- experiments/readout_atlas_v1/readout_atlas.json / .png
- experiments/steering_construction_v1/steering_construction.json / .png
- experiments/steering_transfer_v1/steering_transfer.json / .png
- experiments/steering_sweep_v1/steering_sweep.json / .png
- experiments/steering_recipe_v1/steering_recipe.json + vectors/*.npy
- frontend/public/latent/data/readout_atlas.json（页面读取；被 .gitignore 忽略）
- experiments/steering_design_v1/steering_design.json（入库）
- experiments/steering_design_v1/README.md（自动生成）
- experiments/steering_design_v1/steering_design.png（2x2 静态图：层策略 / 剂量 / logit lens / marker 读出）
- frontend/public/latent/data/steering_design.json（页面读取；被 .gitignore 忽略）

测试：

    python3 -m pytest backend/tests/test_readout_atlas.py backend/tests/test_steering_construction.py backend/tests/test_steering_gradient.py backend/tests/test_steering_sweep.py backend/tests/test_steering_recipe.py backend/tests/test_steering_design.py -q

## 这个指南**不**做什么

- 不重跑模型；所有数字来自现有产物，并记录 sha256。
- 不把组级 block/restore 说成单单元机制。
- 不把 measured 当成“统计显著”；它只表示“这个数存在于源产物”。
- 不给最终构造配方：per-unit causal alignment、control direction、token-composition
  matched control、第二模型/第二向量、closed-loop controller 都列在 unmeasured。

## 下一步（把指南变成构造器）

1. 给每个单元算一阶因果对齐：s_i = grad_h(f) · d_i，c_i = s_i * (grad_h(a_i) · v)。
2. 用四象限（响应 vs 因果贡献）把“载体 / 补偿者 / 沉默贡献者”分开。
3. 修复向量：v' = normalize(v - lambda * sum_{compensators} alpha_i * grad_h(a_i))。
4. 在留出题上与 v / CAA / random / gradient steering 对比，预登记成功判据。
5. 把结果写回本页：新增 “Repair” 与 “Assemble” 两个 panel。

## 相关文档

- [READOUT_ATLAS.md](READOUT_ATLAS.md)：hidden-state 读出 atlas（30 条轨迹 / 384 个 marker）
- [STEERING_CONSTRUCTION.md](STEERING_CONSTRUCTION.md)：局部梯度构造 probe（6 sites / 3 markers）
- [STEERING_TRANSFER.md](STEERING_TRANSFER.md)：held-out 迁移（2 calib + 2 held-out / marker）
- [STEERING_SWEEP.md](STEERING_SWEEP.md)：alpha / side-effect sweep（dose 0.02-0.5）
- [STEERING_RECIPE.md](STEERING_RECIPE.md)：compiled recipe + .npy 文件
- [STEERING_WORKBENCH.md](STEERING_WORKBENCH.md)：自包含 HTML 总工作台
- 页面：/readout-atlas、/steering-construction、/steering-transfer、/steering-sweep、/steering-recipe、/steering-design、/steering-workbench.html
