# Readout Atlas v1

投影 hidden states 到 steering 向量 w，按“下一个 token 是否为 marker”计算逐层 rank AUC。

- 数据：datasets/aime_qwen3_1p7b_32k_fp32/aime/*.npz（30 条轨迹，已存 float32）
- 向量：.cache/bpath/results_B/w_L19_m0.npy（SHA-256 与 B 路/circuit 一致）
- 生成器：backend/examples/build_readout_atlas.py
- 统计核心：backend/core/readout_atlas.py

## 主结果

| 量 | 值 |
|---|---|
| best layer | 21 |
| raw cos AUC | 0.1991 |
| oriented cos AUC | 0.8009 |
| orientation | -1 |
| 负向轨迹 | 24 / 24 |
| norm control AUC | 0.5632 |
| residualised raw AUC | 0.1927 |
| marker 次数 | 384 |
| 有效轨迹（两类都有） | 24 / 30 |

**读法**：raw cos AUC < 0.5 表示 marker next-token 位置的 cos(h,w) 更低；oriented
只是 1 - AUC 的描述性上界。norm control 与残差化都表明信号不是范数混杂。

## per-marker（set-level AUC 掩盖符号分裂）

| marker | n | 有效轨迹 | best layer | raw cos AUC | orientation |
|---|---:|---:|---:|---:|---:|
| 6771 | 119 | 13 | 27 | 0.1453 | -1 |
| 7196 | 105 | 9 | 17 | 0.7305 | +1 |
| 10061 | 70 | 20 | 21 | 0.1620 | -1 |
| 14190 | 46 | 12 | 19 | 0.3690 | -1 |
| 13824 | 34 | 9 | 27 | 0.0725 | -1 |
| 88190 | 6 | 5 | 18 | 0.0297 | -1（n<10） |
| 80022 | 4 | 2 | 9 | 0.0197 | -1（n<10） |

⇒ 7196 是唯一正向读出；其余为负。B 路又实测 +w 压制 7196 ⇒ 读出符号不能直接当注入方向。

## 文件

- readout_atlas.json：aggregate + 30 条轨迹的 marker 统计 + 3 条逐 token 序列
- readout_atlas.png：AUC 曲线 + 一条轨迹的 cos 热图
- frontend/public/latent/data/readout_atlas.json：页面读取的副本（目录被 gitignore）

## 边界

- 描述性关联，不是因果；没有 patch/ablation。
- 7 个 marker 被当成一个标签；B 路已实测 marker 之间符号异质（7196 被压制，其余被抬高）。
- 序列相关：384 个 marker 不是 384 个独立样本。
- 单模型、单向量。

## 复现

    .cache/venv_steer/bin/python backend/examples/build_readout_atlas.py
    python3 -m pytest backend/tests/test_readout_atlas.py -q
