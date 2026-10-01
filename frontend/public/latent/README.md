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

## 关键点：投影是实时算的

`pca_NN.bin` 随数据一起打包，所以网页能拿原始 2048 维向量，在浏览器里
减掉该层均值、用**该层自己的** PCA 基投影。拖动层滑块时点云会真的重新投影，
不是播放预渲染图。已验证浏览器端算出的 28 层坐标与服务器预计算的逐位一致。

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
