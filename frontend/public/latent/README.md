# Qwen3-1.7B 隐空间观察台

## 怎么看

```bash
python3 -m http.server 8899 --directory frontend/public
# 打开 http://localhost:8899/latent/index.html
```

必须用 HTTP 打开，不能双击 `index.html`（`file://` 下浏览器不允许 fetch 本地文件）。

## 里面是什么

`data/` 是 80MB 的二进制数据包，由 `backend/examples/build_latent_bundle.py`
从 `datasets/aime_qwen3_1p7b_16k_fp16/` 重新生成，不进版本库。

| 文件 | 内容 |
|---|---|
| `manifest.json` | 12 条轨迹的元信息 + 逐 token 文本/熵/top1 |
| `hs_NN.bin` | 原始 hidden states `(48, 28, 2048)` float16 |
| `pca_NN.bin` | 全部 28 层的 PCA 基 `(28, 2048, 2)` float32 |
| `mean_NN.bin` | 全部 28 层的均值 `(28, 2048)` float32 |
| `proj_NN.bin` | 全部 28 层的二维坐标 `(28, 2T)` float32 |
| `topk_NN.bin` / `topki_NN.bin` | 逐 step 的 top-64 候选词分数与 id |
| `vocab.json` | 完整 151936 词表（id → 文字） |
| `dim_names.json` | 2048 个维度各自最偏向的词，由服务器上的模型算出 |

`data/pairs/` 是**干预 vs 对照**那一屏的数据，由
`backend/examples/run_paired_steering.py` 采集、`build_paired_bundle.py` 打包。
同一道题跑两遍，一遍不干预一遍在 L20 注入 steering 向量，两条是**独立**的
贪心流（不是 teacher-forced 的 shadow —— 那种一旦分叉就在描述一个不存在的
世界）。

| 文件 | 内容 |
|---|---|
| `pairs/pairs.json` | 配对题目的元信息、逐层统计、被推最多的维度及其词名 |
| `pairs/pc_*_control_L*.bin` | 对照流原始向量 `(T, 2048)` fp16 |
| `pairs/pc_*_delta_L*.bin` | 逐点位移 Δ `(prefix, 2048)` fp16 |
| `pairs/pc_*_ids.bin` | 两条流各自的 token id 序列（int32） |
| `pairs/steer_unit.bin` | 注入方向的单位向量，用作 Δ 散点图里的参考箭头 |

## 关键点：投影是实时算的

`pca_NN.bin` 随数据一起打包，所以网页能拿原始 2048 维向量，在浏览器里
减掉该层均值、用**该层自己的** PCA 基投影。拖动层滑块时点云会真的重新投影，
不是播放预渲染图。已验证浏览器端算出的 28 层坐标与服务器预计算的逐位一致。

配对数据**共用同一套 PCA 基**（`pca_00.bin`），这样无干预轨迹和配对轨迹在
同一张 2-D 图里位置可比。重新拟合一次会把同一条轨迹放进另一张无关的图里，
"点云被推走了"就会变成两个投影之间的差别而不是干预的差别。

## 关键点：Δ 是存下来的，不是浏览器减出来的

网页里的"干预后"轨迹是 `control + delta` 现算的，`delta` 由服务器在
float32 里算完再存成 fp16。**不要**改成用两条 fp16 流相减：

fp16 有 11 位尾数，每个分量量化到相对 2^-11，误差在 2048 维上按
sqrt(2048) = 45.3 累积。相减两条独立量化的 `h`，残留误差约 0.022·‖h‖，
而要恢复的信号 Δ 只有 `rel_shift·‖h‖`。实测 SNR（‖真值‖/‖误差‖）：

| rel_shift | h+steered 浏览器相减 | h+delta 重建 steered |
|---|---|---|
| 0.10 | 339 | 4823 |
| 0.01 | 34 | 4813 |
| 0.001 | **3.4** | **4837** |

SNR 3.4 已经看不出位移方向。而且**注入点之前**的层 Δ 理论上接近零，正是
最容易变成一团量化噪声的地方。存 Δ 的体积和存两条流一样（都是两个矩阵），
`pairs.json` 里每层都记了两种做法的实际 SNR。

## 重新生成

```bash
python3 backend/examples/build_latent_bundle.py \
    --dataset datasets/aime_qwen3_1p7b_16k_fp16 \
    --variant think --problems 12 --tokens 48 \
    --out frontend/public/latent/data

# 维度名字需要模型权重（本地 datasets/models/Qwen3-1.7B 即可）
python3 backend/examples/build_dim_dictionary.py \
    --model-path datasets/models/Qwen3-1.7B --device cpu \
    --out frontend/public/latent/data/dim_names.json
```

配对数据（在服务器上跑；本机 CPU 也够，只是慢，见下）：

```bash
# 先跑接线自检（44 项断言，其中一组会真的驱动 main() 跑完整流程）
python3 backend/examples/test_paired_steering.py

# CPU 版：32 核机器上约 4.7 tok/s，6 题 × 2 臂 × 1024 步 ≈ 45 分钟
PYTHONPATH=/path/to/pylibs python3 backend/examples/run_paired_steering.py \
    --model-path <Qwen3-1.7B> --device cpu --dtype float32 \
    --problems output/problem_index.json \
    --limit 6 --max-new-tokens 1024 \
    --layers 4,12,20,26 --layer 20 \
    --direction confidence_up --strength 0.2 --outdir output/paired

python3 backend/examples/build_paired_bundle.py \
    --paired-dir output/paired --out-subdir pairs
```

层选 `{4, 12, 20, 26}` 是有意的：刻意跨过注入点 L20，好回答"注入之前动
了吗 / 注入点本身 / 传了多远"这三个不同的问题。只答其中一个，就会把
steering 的演示写成 steering 的断言。

### 一个必须写明的口径差异

本包里的配对数据是在 **CPU float32** 下采的，不是 GPU bfloat16。原因很现实：
采集节点上能用的那份 torch 是 `2.14.1+cpu`（`CUDA_VISIBLE_DEVICES` 对它无效）。

这件事的影响范围是**有边界的**，别过度声明：

- **配对对比本身完全有效。** 两条臂在同一份 float32 权重、同一套贪心解码下
  跑，Δ 是同一个模型内部的差。
- **但第 4 屏的绝对数值不能和 32k GPU 研究（Finding 11）横向比。**
  `first_diverged_step`、`rel_shift` 这类量对数值精度敏感，bf16 与 fp32 下
  贪心解码会在不同步数上分叉。两个来源的数字各自内部自洽，跨来源不可比。
- 文档里凡是引用 GPU 数字的地方都标注了来源，不要把它们和本页的数据混着读。
