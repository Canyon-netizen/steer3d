# Unit-basis Design：向量到底该怎么设计？

> **一句话**：把 per-marker mean gradient 投影到 block-20 的原生 SwiGLU 单元输入方向，
> 用 OMP 选 unit、最小二乘定系数，得到一个可解释的稀疏编码；k 是显式设计变量。
> 结论是：mean gradient 在 unit basis 里是**分布式**的——1 个 unit 只重建 15-36%，
> 约 200 个 unit 到 80%，500 个到 92-94%。因此“用几个 unit 组成一个紧凑向量”
> 在当前模型/层上不成立；设计要么接受 dense mean g，要么接受 k≈200-500 的 unit-k。

页面：/steering-workbench.html 的 Unit design tab
数据：experiments/unit_design_v1/unit_design.json
图：experiments/unit_design_v1/unit_design.png
生成器：backend/examples/build_unit_design.py
渲染：backend/examples/render_unit_design.py
核心：backend/core/unit_design.py

## 设计算法（可执行）

1. 取目标 marker 的 calibration 前缀；在 block-20 input 最后位置取 h，
   计算 g = ∂ log p(marker) / ∂ h。
2. 在参考状态 h_ref（calibration 平均 h）上，对每个 native SwiGLU unit 计算输入方向
   u_i = ∂a_i/∂h = silu'(z_i)·v_i·W_gate[i] + silu(z_i)·W_up[i]。
3. 用 OMP（orthogonal matching pursuit）在 u_i 上稀疏重建 mean g：
   每步选与残差最相关的 unit，最小二乘求系数，直到 k 个 unit。
4. 得到 v_k = normalize(Σ_{i∈S_k} c_i u_i)；k 是稀疏度/可解释性旋钮。
5. 在 calibration 上选 k 和 dose（KL 预算），在 held-out 上验证。
6. 如果 k 需要很大，直接使用 mean g；如果 k 很小，接受效果下降。

## 结果（held-out，dose 0.02）

| marker | k=1 Δ / KL | k=200 Δ / KL | k=500 Δ / KL | mean g Δ / KL |
|---|---:|---:|---:|---:|
| 7196 | +0.144 / 0.016 | +0.201 / 0.035 | **+0.215 / 0.040** | +0.226 / 0.045 |
| 10061 | +0.088 / 0.013 | +0.113 / 0.026 | **+0.129 / 0.035** | +0.138 / 0.040 |
| 6771 | −0.028 / 0.002 | +0.117 / 0.059 | **+0.129 / 0.079** | +0.134 / 0.090 |

重建 cosine（对 mean g）：k=1 为 0.15-0.36；k=200 为 0.78-0.81；k=500 为 **0.93-0.94**。

⇒ 500 个 unit 的 unit-k 已经接近 mean g 的效果，KL 略低；但它是 6144 个 unit 中的 8%，
不是“几个 circuit”。k=1-10 的紧凑向量不能可靠复现 mean g（6771 在 k=1 甚至为负）。

![unit design](experiments/unit_design_v1/unit_design.png)

## 这解释了什么

- **向量方向**：mean g 是当前最可靠的 per-marker 方向；它在 unit basis 中的表示是分布的。
- **向量稀疏性**：k 是显式代价；k 越大越接近 mean g，越小越可解释但效果下降。
- **剂量**：held-out KL 随 k 增长；k=500 的 KL 仍低于 mean g（0.040 vs 0.045 等）。
- **calibration 与 held-out 的差异**：k=500 在 calibration 上 KL 超过 0.1，说明
  calibration site 对强干预更敏感；所以“选 k/dose”的规则本身还需要独立 split 验证。

## 能说 / 不能说

能说：

- 当前模型/层下，native unit basis 对 mean gradient 的重建是分布式、需要数百个 unit；
- unit-k 设计曲线给出了 effect / KL / sparsity 的显式折中；
- 对 7196/10061/6771，k=500 的 held-out 效果接近 mean g，KL 略低。

不能说：

- “找到了几个关键 unit 组成的 circuit 向量”——数据不支持；
- unit 系数是因果贡献；OMP 只是局部最小二乘编码；
- selected k/dose 是验证过的通用配方；calibration/held-out 仍有差异；
- 结果可外推到其它模型/层/任务。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_unit_design.py
    .cache/venv_steer/bin/python backend/examples/render_unit_design.py
    python3 -m pytest backend/tests/test_unit_design.py -q

## 下一步

1. 用独立第三 split 选 k/dose，避免 calibration 过拟合；
2. 试其它基（attention head、SAE feature、token-specific direction），看能否更稀疏；
3. 任务级副作用（正确率/生成质量）；
4. 第二模型/第二层，检验“分布式”是否是 Qwen3-1.7B block 20 的特例。
