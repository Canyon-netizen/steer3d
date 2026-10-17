# Alpha & Side-Effect Sweep v1

在 held-out marker site 上扫描 dose，比较 w、−w、mean g、sparse g、random 的
Δlogp、KL、熵变化与其它 marker 质量。

- 模型：Qwen3-1.7B，float32，eager，CPU
- 向量：.cache/bpath/results_B/w_L19_m0.npy（SHA-256 与 B 路/circuit 一致）
- 注入：block-20 input 最后位置；dose = 0.02/0.05/0.1/0.2/0.3/0.5 × input norm
- markers：7196 / 10061 / 6771；每 marker 2 calibration + 2 held-out
- 生成器：backend/examples/build_steering_sweep.py
- 纯函数：backend/core/steering_sweep.py

## 有用窗口（mean KL <= 0.1）

| marker | direction | dose | Δlogp | mean KL |
|---|---|---:|---:|---:|
| 7196 | sparse g | 0.02 | +0.2639 | 0.0734 |
| 10061 | mean g | 0.02 | +0.2005 | 0.0851 |
| 6771 | w | 0.10 | +0.1314 | 0.0850 |

## dose 0.05 的权衡

| marker | w Δlogp / KL | mean g Δlogp / KL | sparse g Δlogp / KL |
|---|---|---|---|
| 7196 | +0.064 / 0.011 | +0.563 / 0.672 | +0.476 / 0.366 |
| 10061 | +0.017 / 0.010 | +0.339 / 0.372 | +0.273 / 0.204 |
| 6771 | +0.087 / 0.027 | +0.191 / 0.450 | +0.177 / 0.248 |

⇒ mean g 效果最大但 KL/熵代价最大；sparse g 同 dose 更省；w 最安全但更弱。
高 dose 的 −w 极端 off-manifold（KL 可到 10-22）。

## 文件

- steering_sweep.json：aggregate / useful_window / 180 行逐 site 读数
- steering_sweep.png：dose response / KL vs dose / effect vs side effect
- frontend/public/latent/data/steering_sweep.json（页面读取；被 gitignore）

## 边界

- 每 marker 2 个 held-out site；dose 网格是描述性，不是统计检验。
- KL/熵是全局副作用；other-marker mass 在本数据里几乎不变。
- 单模型/单层/单 alpha 网格；高 dose 可能 off-manifold。
- 有用窗口是按 KL 预算挑的，不是通用配方。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_steering_sweep.py
    python3 -m pytest backend/tests/test_steering_sweep.py -q
