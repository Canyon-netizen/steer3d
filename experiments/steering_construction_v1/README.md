# Steering Construction Probe v1

在 6 条短 AIME 前缀上，比较 w、−w、g、w+g、random 对 f = log p(marker) 的效应；
g = d f / d h（block-20 输入，最后前缀位置）。同时把 g 分解到 layer 20-27 的原生
SwiGLU 单元（response / first-order contribution / 四象限）。

- 模型：Qwen3-1.7B，float32，eager，CPU
- 向量：.cache/bpath/results_B/w_L19_m0.npy（SHA-256 与 B 路/circuit 一致）
- 注入：block-20 input 最后位置；alpha = 0.1 × 该位置 L2 norm
- 生成器：backend/examples/probe_steering_construction.py
- 纯函数：backend/core/steering_construction.py

## 主结果（均值 delta log p(marker)，括号为改善比例）

| marker | n | w | −w | g | w+g | random |
|---|---:|---:|---:|---:|---:|---:|
| 7196 | 2 | −0.0083 (50%) | +0.0022 (50%) | **+0.0159 (100%)** | +0.0158 (100%) | +0.0011 (50%) |
| 10061 | 2 | +0.1254 (100%) | −0.3248 (0%) | **+0.3643 (100%)** | +0.3527 (100%) | +0.0252 (100%) |
| 6771 | 2 | +0.1215 (100%) | −0.1822 (0%) | **+0.3419 (100%)** | +0.3418 (100%) | +0.0020 (50%) |

⇒ g 在全部 site 上提高 f；w 对 7196 平均为负，对另外两个 marker 弱于 g。

## 文件

- steering_construction.json：6 sites + aggregate + 400 点四象限散点
- steering_construction.png：逐 site 候选 / 四象限 / 按 marker 聚合
- frontend/public/latent/data/steering_construction.json（页面读取；目录被 gitignore）

## 边界

- 局部白盒，6 sites / 3 markers / 单模型 / 单 alpha；不是通用配方。
- g 是数值方向，不保证语义；依赖前缀、层、剂量。
- unit decomposition 是一阶诊断；sum c / measured Δ 的 ratio 跨 site 从 +0.36 到 −5.4，
  不能报成 mediation 百分比。
- naive 去掉 write-direction 分量的修复原型失败；修复需要精确 grad_h a_i 或 unit-level 干预。

## 复现

    .cache/venv_steer/bin/python backend/examples/probe_steering_construction.py
    python3 -m pytest backend/tests/test_steering_construction.py -q
