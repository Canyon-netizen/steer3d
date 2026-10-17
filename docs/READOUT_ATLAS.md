# Hidden-State Readout Atlas

> **一句话**：把每条轨迹每一层的 hidden state 投影到 steering 向量 w 上，看
> **w·h 在哪一层、以什么方向**区分 7 个 marker 的下一个 token。它回答的是
> **读出（readout）**，不是因果控制。

页面：/readout-atlas
数据：experiments/readout_atlas_v1/readout_atlas.json
生成器：backend/examples/build_readout_atlas.py
统计核心：backend/core/readout_atlas.py

## 方法

对每条轨迹的每个生成位置 t、每一层 l：

    proj[t,l] = w · h[t,l]
    cos[t,l]  = proj[t,l] / (||h[t,l]|| * ||w||)
    label[t]  = (next_token[t] 属于 7 个 marker id)

主读数是 **cos(h,w) 的 rank AUC**（尺度无关）；raw proj 的 AUC 作为对照。
另外报告：

- **norm control**：只看 ||h|| 的 AUC，检查信号是不是范数混杂；
- **residualised raw AUC**：把 proj 对 norm 做线性回归后的残差再算 AUC；
- **orientation**：raw AUC < 0.5 时把方向翻过来看的描述性上界（1 - AUC）。

AUC = 0.5 是随机；> 0.5 表示该层的投影越高越可能是 marker；< 0.5 表示越低越可能。

## 数据范围

- 模型：Qwen3-1.7B，28 层，2048 维；hidden states 为已存的 float32。
- 向量：.cache/bpath/results_B/w_L19_m0.npy，SHA-256 与 B 路/circuit 一致。
- 30 条 AIME 轨迹（think / no_think），共 384 次 marker next-token，30 条中
  24 条同时含 marker 与非 marker（AUC 在这些轨迹上定义）。
- 热图序列：3 条（1989 think / 2010 think / 2025 no_think），存 token 文本、
  逐步 proj/cos/norm、marker 位置。

## 当前结果（2026-10-17 产物）

| 量 | 值 |
|---|---|
| best layer | **21** |
| raw cos AUC | **0.1991** |
| oriented cos AUC | **0.8009** |
| orientation | **-1（反相关）** |
| 负向轨迹 | **24 / 24** |
| norm control AUC | 0.5632 |
| residualised raw AUC | 0.1927 |
| layer 20 raw / oriented | 0.2137 / 0.7868 |
| layer 25 raw / oriented | 0.2414 / 0.7586 |

### per-marker：set-level AUC 掩盖了符号分裂

| marker | n | 有效轨迹 | best layer | raw cos AUC | orientation |
|---|---:|---:|---:|---:|---:|
| 6771 | 119 | 13 | 27 | 0.1453 | −1 |
| 7196 | 105 | 9 | 17 | **0.7305** | **+1** |
| 10061 | 70 | 20 | 21 | 0.1620 | −1 |
| 14190 | 46 | 12 | 19 | 0.3690 | −1 |
| 13824 | 34 | 9 | 27 | 0.0725 | −1 |
| 88190 | 6 | 5 | 18 | 0.0297 | −1（n<10，不可判） |
| 80022 | 4 | 2 | 9 | 0.0197 | −1（n<10，不可判） |

⇒ **7196 是唯一正向读出的 marker**（layer 17，raw AUC 0.7305）；其余 marker 都是负向，
且最佳层从 9 到 27 不等。set-level raw AUC 0.199 是这两组符号混合后的结果。
这也意味着 **不能用一个全局符号/层去服务全部 7 个 marker**。

⚠ **7196 的读出声号与注入效应方向并不一致**：B 路实测 +w **压制** 7196，但 7196 的
natural marker 位置 cos(h,w) 更高。⇒ 读出符号不能直接当作注入方向；这是
readout/control 分离的又一个实例。

⇒ **marker next-token 位置的 cos(h,w) 系统性更低**，在 layer 20-21 最强，且不是
范数混杂（norm AUC 0.56，残差化后信号仍在）。这解释了两件事：

1. 静态 "w·U" 为正（7/7 marker id）**不能**外推成“w·h 正向读出 marker”；
   unembedding 空间的读出与状态空间的投影不是同一个量。
2. "+w" 注入把状态往 "+w" 方向推，而 natural marker 状态在 "-w" 一侧
   ⇒ 与 B 路观察到的“+w 压制 dominant marker 7196”方向一致。

⚠ **不要把这条曲线当成“应该注入 -w”的证明**：AUC 把 7 个 marker 当成一个标签，
而 B 路已实测 marker 之间存在符号异质性（7196 被压制、其余被抬高）。
per-marker 的 AUC/符号尚未测量，见下。

## 这个 atlas 不做什么

- 不重跑模型；只读已存 hidden states。
- 不做因果：AUC 是描述性关联，不是 patch/ablation 的效应。
- 不处理序列相关性：token 之间不独立，AUC 的置信区间不能按 384 个独立样本算。
- per-marker 已经测了，但 88190（n=6）/80022（n=4）样本太少，不可判；
  set-level AUC 仍不能代表每个 marker 同号。
- 不替代 readout/control 区分：它只说明“读得出/读不出”，不说明“注进去会怎样”。

## 复现顺序

    .cache/venv_steer/bin/python backend/examples/build_readout_atlas.py
    python3 backend/examples/build_steering_design.py

第一条需要 numpy + transformers（用于 token 文本）；第二条只需要标准库 + numpy。
输出：

- experiments/readout_atlas_v1/readout_atlas.json
- experiments/readout_atlas_v1/readout_atlas.png
- frontend/public/latent/data/readout_atlas.json（页面读取；目录被 .gitignore 忽略）
- steering_design.json 会吸收 atlas 的 aggregate，新增两条设计建议。

测试：

    python3 -m pytest backend/tests/test_readout_atlas.py backend/tests/test_steering_design.py -q

## 下一步

1. **token 构成控制**：在固定位置交换 marker token，重算 cos 与 AUC。
2. **位置 / 范数匹配对照**：按位置分位和 norm 分位分层，看信号是否仍在。
3. **因果版**：对 layer 17/20/21 的 top 单元做 patch/block，看 marker logit 是否按
   per-marker atlas 预测的方向移动。
4. **per-marker 向量**：以 7196（唯一正向）和其他 marker 分别构造/评估方向，
   而不是继续用一个 set-level 向量。
5. **第二模型 / 第二向量**：确认“per-marker 符号分裂”是不是这个向量的特例。
