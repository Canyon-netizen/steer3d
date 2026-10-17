# Steering Construction Probe

> **一句话**：在短 AIME 前缀上把 f = log p(marker) 对 block-20 输入求梯度 g，
> 比较 w、−w、g、w+g、random 在同一 alpha 下对 f 的改变，并把 g 分解到
> layer 20-27 的原生单元。它回答 **“在这个前缀/层/剂量下，往哪个方向推能提高 f”**，
> 不是通用构造配方。

页面：/steering-construction
数据：experiments/steering_construction_v1/steering_construction.json
生成器：backend/examples/probe_steering_construction.py
纯函数：backend/core/steering_construction.py

## 方法

对每个 site：

    f = log p(marker)  at the next position
    g = d f / d h      at block-20 input, last prefix position
    alpha = 0.1 * ||h_block20_last||

候选方向（同一 alpha、同一前向）：

    w, -w, g, w + g, w - g, random

同时用 baseline / +w 两次前向收集每层 MLP product，计算：

    Delta a_i = a_i(+w) - a_i(baseline)
    s_i       = g_l . d_i                  (d_i = down_proj column)
    r_i       = |Delta a_i| * ||d_i||      (response)
    c_i       = s_i * Delta a_i            (first-order contribution)

高响应阈值取每 site 的 response 90 分位；四象限为 carrier / compensator /
silent / neutral。

## 当前结果（6 sites, 3 markers, prefix 132-234）

按 marker 的均值（delta = 注入后 f − baseline f；括号内为改善 site 比例）：

| marker | n | w | −w | g | w+g | random |
|---|---:|---:|---:|---:|---:|---:|
| 7196 | 2 | −0.0083 (50%) | +0.0022 (50%) | **+0.0159 (100%)** | +0.0158 (100%) | +0.0011 (50%) |
| 10061 | 2 | +0.1254 (100%) | −0.3248 (0%) | **+0.3643 (100%)** | +0.3527 (100%) | +0.0252 (100%) |
| 6771 | 2 | +0.1215 (100%) | −0.1822 (0%) | **+0.3419 (100%)** | +0.3418 (100%) | +0.0020 (50%) |

⇒ **g 在全部 6 个 site 上提高 f，是三个 marker 的最佳候选**；w 对 7196 平均为负，
对 10061/6771 为正但明显弱于 g；w+g 与 g 几乎一样；w−g 灾难性为负。

## 能说什么 / 不能说什么

能说：

- 在这 6 个短前缀、这一 alpha、block 20 注入下，局部梯度方向比存储的 w 更可靠。
- 对 7196，w 的符号是错的；per-marker readout atlas 也显示 7196 是唯一正向读出的 marker。
- g 的效应可以被分解到原生单元；top carriers / compensators 可点开查看。

不能说：

- 不能把 g 当成“有语义的 steering vector”；它只是局部白盒方向，依赖前缀/层/剂量。
- 不能把 sum c / measured Δ 当成 mediation 百分比：6 个 site 的 ratio 从 +0.36 到 −5.4 不等。
- 不能把四象限当成因果结论：阈值是 90 分位，c_i 是一阶近似。
- **naive 去掉 write-direction 分量的修复原型失败**（在 7196 140 上 λ=0.25/0.5/1.0 都让 f 更负）；
  修复需要精确的 grad_h a_i 或直接做 unit-level 干预，而不是投影 d_i。
- 6 sites / 3 markers / 单模型，不能外推。

## 复现

    .cache/venv_steer/bin/python backend/examples/probe_steering_construction.py
    python3 backend/examples/build_steering_design.py

第一条需要 torch + transformers（CPU 即可；本机 140-token 前向约 0.6 s，反向约 2.6 s）。
输出：

- experiments/steering_construction_v1/steering_construction.json
- experiments/steering_construction_v1/steering_construction.png
- frontend/public/latent/data/steering_construction.json（页面读取；被 .gitignore 忽略）
- steering_design.json 会吸收 construction aggregate，新增两条建议。

测试：

    python3 -m pytest backend/tests/test_steering_construction.py backend/tests/test_steering_design.py -q

## 下一步

1. **held-out 构造**：在一个 site 上选 compensators/构造方向，在另一个 site 上评估；
   当前是 per-site 测量，还不是可迁移的构造。
2. **token 构成控制**：同一前缀位置交换 marker，比较 g 的方向是否只对该 token 有效。
3. **正则化**：g 可能走到 off-manifold；比较 g、clip(g)、g 的低秩/单元稀疏版本。
4. **精确 unit 干预**：用 grad_h a_i 做修复，或直接改 unit product（block/restore），
   验证四象限预测。
5. **第二模型/第二向量**，以及 alpha 扫描（当前只有一个剂量）。
