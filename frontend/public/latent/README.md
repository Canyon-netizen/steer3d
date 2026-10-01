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

## 两个模型

左上角的下拉可以切换 **Qwen3-1.7B** 与 **Qwen3-0.6B**。两者层数相同（28 层）、
只差宽度（2048 / 1024），做的是同一批 6 道题、同一个注入方向、同一强度。
`data/` 是 1.7B，`data06/` 是 0.6B。

导读里引用的宽度、参与维度数、净效果占比、随机方向基线**跟着当前模型一起换**。
这些数字来自 `models.json`，而 `models.json` 由
`backend/../.cache/build_model_registry.py` 从 `analyse_spread.py` 与
`analyse_divergence_logits.py` 的输出生成——**不手写**，手写等于在实测结果旁边
再放一份没人维护的副本。

`.cache/two_model/verify_two_models.mjs` 专门验证这件事：既查渲染出的数字与
`models.json` 一致，也查页面文本里**没有串用另一个模型的数字**，还带一个会红的
负控。曾经因为一段没打上数据绑定的文字，让 0.6B 的视图显示着 1.7B 的结论。

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
| `divergence_readout.json` | 分叉步两臂的 top-8 读出 + 前缀每步的第一二名差距 |
| `cot_effect.json` | 干预对**思维链**的影响（仅 1.7B，见下） |
| `INTERPRETABILITY.md` | Finding 1–15 的完整实测记录，页面上「详见 Finding 13/14」指向的就是它 |

`INTERPRETABILITY.md` 随包分发：只下 tar 的人手上没有 `docs/`，那句话会指向一个
不存在的文件——证据被指到了却摸不到。没做 md → html 转换，2000 多行带表格的实测
记录，转错一行比没有更糟；浏览器直接打开 `.md` 就是纯文本。

## 「为什么最后吐出的是这个词」

分叉点只给两个标签（对照吐了 A / 干预吐了 B）只能回答「变了什么」。
`divergence_readout.json` 补上「为什么」：

- **两臂候选词**：分叉那一步，每个候选词各得多少分（`L4/12/20/26/28`）。
  `L28` 是最终读出，也就是模型真正用来选词的那次——`hidden_states[n_layers]`
  在 `model.norm` 之后，所以第 28 层才是最终口径。
- **前缀领先幅度**：共同前缀每一步「第 1 名 − 第 2 名」差多少。差距小 = 那一步
  本来就快翻牌了。1.7B 的 1983 题在改口前第 26 步只差 0.72 分，比分叉那一步
  （1.94）还小。
- **只发 token id**，文案由页面自己的 `vocab.json` 解析。

由 `backend/examples/build_divergence_readout.py` 生成，取自
`analyse_divergence_logits.py` 与 `analyse_common_prefix.py` 的产物。

两个模型复用同一批题号（1983–1988），**id 无法区分模型**，所以归属靠逐题对齐
（分叉步 + 两个 token id）判定，6/6 不过就拒绝出包；dtype 或强度不符的文件只
命中 0–3/6。

页面上另有 `docs/INTERPRETABILITY.md` Finding 13/14：干预确实把残差推走了，
但净效果只占维度总运动的 0.0%–20.7%（等效 587–831 / 2048 维），
**「位移把 token 掰过去的」这个解释不成立**。这一屏给的是「当时在比哪两个词、
差多少」，不是因果。

## 关键点：`L20` 那一行永远是平的，这不是 bug

最容易读错的一处，所以放在最前面。

`hidden_states[L]` 是**进入第 L 个 block 的残差**，不是它的输出。transformers
的 `@capture_outputs` 把第 0 个 block 的**输入**作为第 0 项预置进去，之后每一项
记的是前一个 block 的输出 —— 所以第 i 项恰好就是第 i 个 block 的输入。

而 steering 向量是在 block 20 的 forward **内部**加的，也就是在第 20 项被记录
**之后**。于是：

| | L19 | **L20（注入块）** | L21 |
|---|---|---|---|
| Δ | 0 | **0（按构造）** | 生效 |

在真模型上用 50.0 的探针实测（float32 / CPU）：

```
hs[19]  max|Δ| =  0.000000
hs[20]  max|Δ| =  0.000000   ← 注入块，精确为零
hs[21]  max|Δ| = 49.914597   ← 效应在这里
```

所以「注入点那一行 rel_shift = 0」**不能**读成「干预没起作用」。第 4 屏在选中
注入层或其上游时会直接把这句话写在图旁边，并指出该看 L21。

代码里 `ResidualSteerer` 的 docstring 曾经写的是 "the block's *output*"。那句是
错的，而且错得不会自己暴露 —— 它让注入层在表里看起来是最有意思的一行，而它必然
是最空的一行。

## 关键点：投影是实时算的

`pca_NN.bin` 随数据一起打包，所以网页能拿原始 2048 维向量，在浏览器里
减掉该层均值、用**该层自己的** PCA 基投影。拖动层滑块时点云会真的重新投影，
不是播放预渲染图。已验证浏览器端算出的 28 层坐标与服务器预计算的逐位一致。

配对数据**共用同一套 PCA 基**（`pca_00.bin`），这样无干预轨迹和配对轨迹在
同一张 2-D 图里位置可比。重新拟合一次会把同一条轨迹放进另一张无关的图里，
"点云被推走了"就会变成两个投影之间的差别而不是干预的差别。

## 关键点：Δ 是存下来的，理由是体积，不是精度

网页里的"干预后"轨迹是 `control + delta` 现算的，`delta` 由服务器在
float32 里算完再存成 fp16。

**这里要更正一个早先写在这份文档里的说法。** 当时写的是"不要让浏览器从两条
fp16 流相减，因为 fp16 相减会把信号埋进量化噪声，实测 SNR 低到 3.4"。在真实
配对数据上重算，这个说法**不成立**：

| 路线 | 恢复 Δ 的 SNR（3 题 × L26 实测） |
|---|---|
| 直接读 `delta` 文件 | 5771 / 5785 / 5593 |
| 浏览器相减两条 fp16 流 | **精确，误差 0** |

原因很简单：两条流**本身就是 fp16 存的**。`fp16 → float32 → 相减` 这一步不
引入任何新的舍入，误差恒等于 0。原先那张 SNR 表描述的是另一个情形（把
float32 算出的量先量化再相减），它是真的，但不属于这份数据。

所以存 delta 的真实收益是**体积**：

| | 每层每题 | 3 题 × 4 层实测 |
|---|---|---|
| 只发 delta | 0.1MB | ~0.3MB |
| 两条流都发 | 4.2MB（多一条臂） | ~50MB 额外 |

代价是 delta 自身被量化，引入相对误差约 1.7e-4 —— 对画图毫无影响，但这个
数字该如实写出来，而不是藏在一个算错的 SNR 后面。

`pairs.json` 每层的 `delta` 块都记了 `reconstruction_snr`、
`snr_if_differencing_stored_arms` 和 `delta_is_exactly_zero`，三条一起看。

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

## 窄屏与短屏

版式在 ≥1100px 宽时是三列（300 / 1fr / 320），高度填满视口，右栏内部滚动。
低于 1100px 改成单列堆叠：固定列 300+320+间距+内边距共 668px，三列在 768px 时
会把主画布压到 74px，更窄时文档还有 747px 的宽度地板——390px 手机上右栏整个在
屏幕外（x=427），「为什么是这个词」根本够不着。

右栏的滚动区有 300px 地板。没有它时这块是整列唯一可压缩的元素，会吃掉全部收缩：
实测滚动窗口在 1100/900/800/720/640 高度下分别是 405/205/105/25/0px。13 寸笔记
本浏览器可用高度大约就是 800。

`.cache/responsive/verify_responsive.mjs` 覆盖 10 档宽度 × 6 档高度，负控实测：
撤掉窄屏媒体查询 → 12 条红（docW=747、画布 65px）；撤掉 300px 地板 → 11 条红。

## 对思维链做了什么

上面几屏量的都是分布层面的东西（logit、熵、位移）。**思维链层面**的影响是另一组
实验：`run_intervention.py` 同时产出 `primary_text`（被干预的生成）与
`shadow_text`（同一条 token 序列上的无干预对照，teacher-forced），所以两段文字的
差异来自**同一个前缀带着不同的状态**，而不是两条流走到了不同句子。
`analyse_cot_divergence.py` 把它压成 `cot_effect.json`，页面第 4 屏有对应面板。

结论是个负面结果，而且是个**容易被说过头**的负面结果，所以三条限制与结论同屏：

| | 结果 | 能说什么 |
|---|---|---|
| token 一致率 | 93.5%–95.8% | 每 100 个里约 4–6 个被改 |
| 推理步骤逐字重合 | 4%–10% | 措辞几乎整段重写，但说的是同一件事 |
| 推理长度比 | 0.994–0.998 | 长度没变 |
| 自我检查次数 | Δ p = 0.16–0.33 | **测不出差别**，不是"没有差别" |
| 最终答案 | — | **没测到**，见下 |

1. 对照臂是同一条代码喂零向量，五个量逐项恒等（`build_cot_effect.py` 在出包前
   强制校验，不恒等就拒绝写文件），所以上表不是采集链路的噪声。
2. 自我检查 p 值 0.16–0.33、n=24，只能说在 24 次运行里分辨不出差别。
3. **168 次运行里只有 7 次能解析出最终答案，且没有任何一次跑完 `</think>`**
   （每题只生成 61 步）。这一维是没测到，不是测了没变——页面写"没测到"而不是
   "答案没变"，`verify_cot.mjs` 专门判这一点。

只打包了能证明模型归属的那组运行（`replication_24problems_L20.log` 记录
`model loaded: /tmp/qwen3/master`）。1025 步的那组没有 log，不 shipping——
挂上一个没人能核对的模型标签，和"0.6B 视图显示 1.7B 的数字"是同一种错。
