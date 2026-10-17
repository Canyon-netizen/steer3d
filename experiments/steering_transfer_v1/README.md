# Held-out Steering Transfer v1

每个 marker 用 calibration sites 的梯度均值构造一个方向，在没参与构造的 held-out
sites 上评估；cross 矩阵把 source marker 的均值梯度作用到 target marker。

- 模型：Qwen3-1.7B，float32，eager，CPU
- 向量：.cache/bpath/results_B/w_L19_m0.npy（SHA-256 与 B 路/circuit 一致）
- 注入：block-20 input 最后位置；alpha = 0.1 × 该位置 L2 norm
- markers：7196 / 10061 / 6771；每 marker 2 calibration + 2 held-out
- 生成器：backend/examples/build_steering_transfer.py
- 纯函数：backend/core/steering_gradient.py

## 同 marker held-out（均值 delta log p）

| marker | w | mean g | sparse g | oracle g |
|---|---:|---:|---:|---:|
| 7196 | +0.1026 | **+0.6514** | +0.6113 | +0.6686 |
| 10061 | +0.0192 | **+0.4363** | +0.3801 | +0.4729 |
| 6771 | +0.1314 | **+0.1958** | +0.1942 | +0.1959 |

## cross-marker mean g

| source \ target | 7196 | 10061 | 6771 |
|---|---:|---:|---:|
| 7196 | — | -0.457 | -5.711 |
| 10061 | +0.317 | — | +0.195 |
| 6771 | +0.258 | +0.308 | — |

⇒ mean g 可迁移（oracle 的 92-100%）；sparse 10% 保留 78-100%；7196 方向 marker-specific，
10061/6771 方向对其它 marker 也为正。-5.711 是 off-manifold 极端读数。

## 文件

- steering_transfer.json：splits / same_marker / cross / cross_rows / sites
- steering_transfer.png：held-out bars + cross heatmap
- frontend/public/latent/data/steering_transfer.json（页面读取；被 gitignore）

## 边界

- 每 marker 只有 2 calibration + 2 held-out；按 prefix 长度切分；不是统计显著结论。
- mean g / sparse g 是局部白盒方向，不保证语义；单模型/单向量/单 alpha。
- cross 的 -5.711 提醒方向可能 off-manifold；需要正则化与侧效应检查。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_steering_transfer.py
    python3 -m pytest backend/tests/test_steering_gradient.py -q
