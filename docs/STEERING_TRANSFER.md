# Held-out Steering Transfer

> **一句话**：每个 marker 用 calibration sites 的梯度均值构造一个方向，
> 在**没参与构造**的 held-out sites 上评估；再看 source marker 的方向作用到
> target marker 的 cross 矩阵。它回答“一个方向能不能迁移”，而不只是“在这个 site 上有效”。

页面：/steering-transfer
数据：experiments/steering_transfer_v1/steering_transfer.json
生成器：backend/examples/build_steering_transfer.py
纯函数：backend/core/steering_gradient.py

## 方法

- markers：7196 / 10061 / 6771；每个 marker 取 4 个短前缀（<=400 token）。
- 按 prefix 长度排序，前 2 个 calibration、后 2 个 held-out（互不重叠）。
- 对每个 calibration site 计算 g = d log p(marker) / d h（block-20 输入，最后位置）。
- mean g = normalize(mean(normalize(g_i)))；sparse g = 保留 |g| 最大的 10% 坐标再归一化。
- 在 held-out site 上用同一 alpha（0.1 × block-20 input norm）评估：
  w / -w / mean g / sparse g / random / oracle（该 held-out site 自己的梯度，上界）。
- cross：source marker 的 mean g 作用到 target marker 的 held-out site。

## 同 marker held-out 结果（均值 delta log p）

| marker | w | mean g | sparse g | oracle g |
|---|---:|---:|---:|---:|
| 7196 | +0.1026 | **+0.6514** | +0.6113 | +0.6686 |
| 10061 | +0.0192 | **+0.4363** | +0.3801 | +0.4729 |
| 6771 | +0.1314 | **+0.1958** | +0.1942 | +0.1959 |

⇒ mean g 在全部 held-out site 上提高 f，达到 per-site oracle 的约 92-100%；
sparse g 保留 78-100%；w 明显更弱，10061 上几乎无效。

## cross-marker mean g

| source \ target | 7196 | 10061 | 6771 |
|---|---:|---:|---:|
| 7196 | — | **-0.457** | **-5.711** |
| 10061 | +0.317 | — | +0.195 |
| 6771 | +0.258 | +0.308 | — |

⇒ **7196 的均值梯度对其它 marker 是负的**，而 10061/6771 的均值梯度对其它 marker 为正。
7196 方向含 marker-specific 成分；10061/6771 更像共享的 marker-raising 成分。
-5.711 是极端 off-manifold 读数，颜色在图中截断，数字原样保留。

## 能说什么 / 不能说什么

能说：

- 在这 6 个 held-out site、这一 alpha、block 20 下，**用 calibration 平均梯度构造的方向可迁移**，
  比存储的 w 更可靠；sparse 10% 仍保留大部分效应。
- 7196 需要自己的方向；把 10061/6771 的方向用到 7196 上也可能有效，但反向不成立。

不能说：

- 每个 marker 只有 2 个 calibration + 2 个 held-out site；不是统计显著结论。
- 按 prefix 长度切分可能带来长度/位置混杂。
- mean g / sparse g 是局部白盒方向，不保证语义；依赖模型/层/alpha。
- cross 的 -5.711 提醒：方向可能 off-manifold；需要正则化/侧效应检查。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_steering_transfer.py
    python3 backend/examples/build_steering_design.py

输出：

- experiments/steering_transfer_v1/steering_transfer.json
- experiments/steering_transfer_v1/steering_transfer.png
- frontend/public/latent/data/steering_transfer.json（页面读取；被 .gitignore 忽略）
- steering_design.json 会吸收 transfer 摘要，新增两条建议。

测试：

    python3 -m pytest backend/tests/test_steering_gradient.py backend/tests/test_steering_design.py -q

## 下一步

1. **更多 held-out sites**（每 marker 4-8 个），按位置/长度分层切分，报 CI。
2. **alpha 扫描**：当前只有一个剂量；迁移可能只在某个剂量窗口成立。
3. **侧效应**：除 f 外测 KL/熵/其它 marker 的概率，避免“提高 f 但破坏别的”。
4. **正则化**：clip、低秩、SAE/单元稀疏方向，比较迁移与可解释性。
5. **第二模型/向量**，以及 held-out 构造的预登记判据。
