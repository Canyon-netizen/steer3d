# Alpha & Side-Effect Sweep

> **一句话**：在 held-out marker site 上扫描剂量，比较 w、−w、mean g、sparse g、random
> 的 Δlogp、KL、熵变化与其它 marker 质量。它不找“最强剂量”，而是把
> **效果 vs 副作用**的窗口摆出来。

页面：/steering-sweep
数据：experiments/steering_sweep_v1/steering_sweep.json
生成器：backend/examples/build_steering_sweep.py
纯函数：backend/core/steering_sweep.py

## 方法

- markers：7196 / 10061 / 6771；每 marker 2 个 calibration + 2 个 held-out site。
- 方向：w、−w、mean g（calibration 梯度均值）、sparse g（mean g 的 top 10% 坐标）、random。
- doses：0.02 / 0.05 / 0.1 / 0.2 / 0.3 / 0.5 × block-20 input norm。
- 每个注入测：
  - Δlogp = log p(target marker) − baseline
  - KL(base || injected)（完整 softmax）
  - Δentropy
  - Δother marker mass（其余 marker 的概率质量和）
- 有用窗口 = 在 mean KL <= 0.1 的格子里，选 mean Δlogp 最大的 direction/dose。

## 有用窗口（mean KL <= 0.1）

| marker | direction | dose | Δlogp | mean KL |
|---|---|---:|---:|---:|
| 7196 | sparse g | 0.02 | +0.2639 | 0.0734 |
| 10061 | mean g | 0.02 | +0.2005 | 0.0851 |
| 6771 | w | 0.10 | +0.1314 | 0.0850 |

## 效果 / 副作用权衡（dose 0.05）

| marker | direction | Δlogp | KL | Δentropy |
|---|---|---:|---:|---:|
| 7196 | w | +0.0640 | 0.0114 | -0.0839 |
| 7196 | mean g | +0.5633 | 0.6719 | -0.8009 |
| 7196 | sparse g | +0.4757 | 0.3661 | -0.6024 |
| 10061 | w | +0.0165 | 0.0096 | -0.0295 |
| 10061 | mean g | +0.3391 | 0.3719 | -0.4998 |
| 10061 | sparse g | +0.2732 | 0.2037 | -0.3999 |
| 6771 | w | +0.0871 | 0.0270 | -0.1165 |
| 6771 | mean g | +0.1905 | 0.4504 | -0.4317 |
| 6771 | sparse g | +0.1773 | 0.2480 | -0.3741 |

⇒ **mean g 的 Δlogp 最大，但 KL/熵代价也最大；sparse g 在相同 dose 下 KL 更低；
w 最安全但更弱**。在高 dose 下 −w 的 KL 可以到 10-22，属于 off-manifold，不能当
“方向本身有效”的证据。

## 能说什么 / 不能说什么

能说：

- 在这 6 个 held-out site、单模型、block 20 下，存在按 marker 不同的
  “效果/副作用”窗口；sparse g 通常比 dense mean g 更省副作用。
- 选择方向/剂量应按 KL 预算，而不是只看 Δlogp。

不能说：

- “有用窗口”是描述性挑选，不是统计检验；每格只有 2 个 site。
- KL/熵是全局副作用，不代表所有下游任务；other-marker mass 在这里几乎不变。
- 高 dose 的极端读数可能是 off-manifold 伪影；需要正则化与更多 site。
- 这不是通用配方：单模型/单层/单 alpha 网格。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_steering_sweep.py
    python3 backend/examples/build_steering_design.py

输出：

- experiments/steering_sweep_v1/steering_sweep.json
- experiments/steering_sweep_v1/steering_sweep.png
- frontend/public/latent/data/steering_sweep.json（页面读取；被 .gitignore 忽略）
- steering_design.json 会吸收 sweep 摘要，新增两条建议。

测试：

    python3 -m pytest backend/tests/test_steering_sweep.py backend/tests/test_steering_design.py -q

## 下一步

1. 更多 held-out site（每 marker 4-8 个）与按位置/长度分层切分；
2. 任务级副作用（准确率、其它 marker 的 per-marker 概率、生成质量），不只是 KL；
3. 正则化方向（clip / low-rank / unit-sparse）在相同 Δlogp 下比较 KL；
4. 第二模型/第二向量；
5. 把“选窗口”的规则预登记，再在独立 site 上验证。
