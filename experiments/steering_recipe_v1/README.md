# Compiled Steering Recipes v1

每个 marker 一个候选方向：readout atlas 选层，calibration 梯度均值构造方向，
sweep 选 KL 预算内 dose，held-out site 验证，并保存为 .npy。

- 模型：Qwen3-1.7B，float32，eager，CPU
- 注入：block-20 input 最后位置；dose × input norm
- markers：7196 / 10061 / 6771；每 marker 2 calibration + 2 held-out

## Recipes

| marker | readout layer / AUC | direction | dose | expected Δlogp / KL | verified Δlogp / KL | file |
|---|---|---:|---:|---:|---:|---|
| 7196 | 17 / 0.7305 | sparse g | 0.02 | +0.2639 / 0.0734 | +0.2639 / 0.0734 | vectors/7196_sparse_g.npy |
| 10061 | 21 / 0.1620 | mean g | 0.02 | +0.2005 / 0.0851 | +0.2005 / 0.0851 | vectors/10061_mean_g.npy |
| 6771 | 27 / 0.1453 | w | 0.10 | +0.1314 / 0.0850 | +0.1314 / 0.0850 | vectors/6771_w.npy |

expected 与 verified 相同，因为 verification 复用了 transfer/sweep 的 held-out site。

## 文件

- steering_recipe.json：recipe + verification + source hashes + guards
- vectors/<marker>_<direction>.npy：归一化 float32 向量
- frontend/public/latent/data/steering_recipe.json（页面读取；被 gitignore）
- frontend/public/latent/data/steering_recipes/*.npy（网页下载副本）

## 必须随文件传递的边界

- verification 不是第三个独立 split，与 transfer/sweep 共用 held-out site。
- 单模型、单层 20、短 AIME 前缀、单 alpha 网格；不能直接外推。
- mean g / sparse g 是数值方向，不保证语义；高 dose 可能 off-manifold。
- 只测 target logp 与全局 KL/熵，没有任务级正确率/生成质量。
- 6771 推荐原始 w，不是新构造的梯度方向。

## 复现

    .cache/venv_steer/bin/python backend/examples/compile_steering_recipe.py
    python3 -m pytest backend/tests/test_steering_recipe.py -q
