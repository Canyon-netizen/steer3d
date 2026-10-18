# Unit-basis Steering Design v1

把 per-marker mean gradient 投影到 block-20 的原生 SwiGLU 单元输入方向，
用 OMP 选 unit、最小二乘定系数；k 是显式设计变量。

- 模型：Qwen3-1.7B，float32，eager，CPU
- 注入：block-20 input 最后位置；dose × input norm
- 每 marker：2 calibration + 2 held-out（interleaved by prefix length）
- 核心：backend/core/unit_design.py
- 生成器：backend/examples/build_unit_design.py
- 图：backend/examples/render_unit_design.py

## 结果（held-out，dose 0.02）

| marker | k=1 Δ / KL | k=200 Δ / KL | k=500 Δ / KL | mean g Δ / KL |
|---|---:|---:|---:|---:|
| 7196 | +0.144 / 0.016 | +0.201 / 0.035 | +0.215 / 0.040 | +0.226 / 0.045 |
| 10061 | +0.088 / 0.013 | +0.113 / 0.026 | +0.129 / 0.035 | +0.138 / 0.040 |
| 6771 | −0.028 / 0.002 | +0.117 / 0.059 | +0.129 / 0.079 | +0.134 / 0.090 |

重建 cosine 对 mean g：k=1 0.15-0.36；k=200 0.78-0.81；k=500 0.93-0.94。

结论：mean gradient 在 native unit basis 中是分布的；几个 unit 不能组成
可复现的紧凑向量。k=500 的 unit-k 接近 mean g，但它是 6144 个 unit 的 8%。

## 文件

- unit_design.json：curve / baselines / selected / hybrid / top_units / sites
- unit_design.png：reconstruction / effect / KL vs k
- frontend/public/latent/data/unit_design.json（页面读取；被 gitignore）

## 边界

- 单模型、单层 20、短 AIME 前缀；2+2 site；interleaved split。
- OMP 是局部最小二乘编码，不是因果分解。
- selected k/dose 在 calibration 上选；calibration 的 KL 已超预算，
  held-out 更低，说明 site 差异仍然存在。
- 不是“几个关键 unit = circuit vector”的证据。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_unit_design.py
    .cache/venv_steer/bin/python backend/examples/render_unit_design.py
    python3 -m pytest backend/tests/test_unit_design.py -q
