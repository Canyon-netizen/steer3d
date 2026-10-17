# Compiled Steering Recipe

> **一句话**：每个 marker 一个可复现的候选方向——readout atlas 选层，calibration 梯度均值
> 构造方向，alpha/side-effect sweep 选 KL 预算内的 dose，在 held-out site 上验证，
> 并保存为 .npy。它是**可复现的起点**，不是生产级 steering vector。

页面：/steering-recipe
数据：experiments/steering_recipe_v1/steering_recipe.json
向量：experiments/steering_recipe_v1/vectors/*.npy
生成器：backend/examples/compile_steering_recipe.py
装配函数：backend/core/steering_recipe.py

## Recipe 表

| marker | readout layer / AUC | direction | dose | expected Δlogp / KL | verified Δlogp / KL | file |
|---|---|---:|---:|---:|---:|---|
| 7196 | 17 / 0.7305 | sparse g | 0.02 | +0.2639 / 0.0734 | +0.2639 / 0.0734 | 7196_sparse_g.npy |
| 10061 | 21 / 0.1620 | mean g | 0.02 | +0.2005 / 0.0851 | +0.2005 / 0.0851 | 10061_mean_g.npy |
| 6771 | 27 / 0.1453 | w | 0.10 | +0.1314 / 0.0850 | +0.1314 / 0.0850 | 6771_w.npy |

（所有数字来自 2 个 held-out site；expected 与 verified 相同，因为 verification 复用了
同一批 held-out site。）

## 怎么用

    import numpy as np
    v = np.load("experiments/steering_recipe_v1/vectors/7196_sparse_g.npy")
    alpha = dose * np.linalg.norm(h_block20_last)
    h_block20_last += alpha * v
    # 然后在你的前缀上重新测 target marker logp / KL

- 注入层：block-20 input 的最后一个位置。
- dose：0.02 / 0.10 等，乘以该位置的 block-20 输入 L2 范数。
- 换前缀、层、模型、dose 后必须重新验证；不要直接复用本页数字。
- frontend/public/latent/data/steering_recipes/ 下有同一批 .npy 的网页下载副本。

## 每个文件旁边必须带上的限制

- verification 用的是 transfer/sweep 的 held-out site，**不是第三个独立 split**。
- 单模型、单层 20、短 AIME 前缀、单 alpha 网格；不能直接外推到生产。
- mean g / sparse g 是数值方向，不保证语义；高 dose 可能 off-manifold。
- 只测了 target marker logp 与全局 KL/熵，没有测任务级正确率/生成质量。
- 6771 的推荐方向是原始 w（它在 sweep 的 KL 预算内最好），不是新构造的梯度方向。

## 复现

    .cache/venv_steer/bin/python backend/examples/compile_steering_recipe.py
    python3 backend/examples/build_steering_design.py

依赖：readout_atlas_v1 / steering_transfer_v1 / steering_sweep_v1 的产物。
输出：

- experiments/steering_recipe_v1/steering_recipe.json
- experiments/steering_recipe_v1/vectors/*.npy
- frontend/public/latent/data/steering_recipe.json（页面读取；被 .gitignore 忽略）
- frontend/public/latent/data/steering_recipes/*.npy（网页下载副本）

测试：

    python3 -m pytest backend/tests/test_steering_recipe.py backend/tests/test_steering_design.py -q

## 下一步

1. **独立第三 split**：当前 verification 与 transfer/sweep 共用 held-out；需要新 site。
2. **任务级指标**：正确率、其它 marker 的 per-marker 概率、生成质量，而不是只有 KL。
3. **正则化方向**：clip / low-rank / unit-sparse，在相同 Δlogp 下比较 KL。
4. **第二模型/第二向量**，以及把 recipe 规则预登记。
5. 给每个 .npy 配一个 sidecar JSON（source hashes、dose、caveats），方便脱离本页使用。
