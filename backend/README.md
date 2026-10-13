# Steering3D Backend

FastAPI + WebSocket server that streams per-token frames
describing the model's reasoning trajectory and steering state.

## 解释一个给定的 steering vector

理论定义与推导见 [Steering 向量功能的因果理论](../docs/VECTOR_FUNCTION_THEORY.md)。
下面的工具实现关联测量和局部响应，尚未实现理论中的完整功能识别与机制验证。

`examples/explain_vector.py` 接受任意一维 `.npy` 向量，输出严格 JSON 报告。
核心接口在 `core/vector_explanation.py`。目标是回答：这个方向在已有状态中
与什么相关，以及在一个具体推理位置加进去后，实际改变了哪些输出概率。

解释的对象是 `(模型, 向量, 层与注入侧, 文本前缀, token 位置, 强度)`。
同一向量换前缀、层或强度，可能产生不同的效果；向量名字只记录提取意图。

### 从 hidden states 找到可读的关联

从仓库根目录运行：

```bash
python3 backend/examples/explain_vector.py observe \
  --vector backend/examples/output/steering_vectors/confidence_up.npy \
  --data-root datasets/aime_qwen3_1p7b_16k_fp16/aime \
  --hidden-index 14 --evaluation-split overlap \
  --random-directions 64 --seed 20261009 \
  --out backend/examples/output/vector_explanation/confidence_up_observed.json
```

只需要 NumPy 和 SciPy。逐条轨迹读取原始状态，保留指定层，因此无需加载模型。
报告包括沿向量的高、低投影文本片段，以及对以下属性的关联：下一 token 的熵、
top-1 概率、数字、运算符、修订标记、think 块标志和生成位置。
词法标记是可复核的操作性定义，不能直接等同于“谨慎”“创造力”或推理深度。
程序化接口还可以接受其他逐 token 观测量。

每条轨迹内计算 Spearman，再把同一道题的不同模式合并，最后按题等权平均。
主读数使用 `cos(h,v)`，同时报告未经范数归一化的投影相关，帮助判断范数混杂。
置信区间按题 bootstrap；随机对照使用同一批状态、同一掩码与分组。
`random_max_stat_p` 对搜索的全部观测量取最大绝对统计量，使用 `(b+1)/(R+1)`，
因此不会报告“p=0”。它衡量相对各向同性随机方向的几何特异性，
不是标签置换检验，也不代表已经发现语义机制。

`--evaluation-split independent` 只适用于确实未参与向量提取的评估题目；
这项声明需要调用方核对来源，程序无法从一个 `.npy` 判断训练数据。
仓库自带向量在上述轨迹上提取，所以示例明确写 `overlap`。
没有变化的标签返回 `unmeasured`；不会把 think/no_think 的模式差异冒充轨迹内证据。
`--lag 1` 可以读出 `h[t]` 与下一行观测量的关联，它仍然是观察性分析。

### 测量向量经过下游模型后的真实作用

```bash
python3 backend/examples/explain_vector.py respond \
  --vector backend/examples/output/steering_vectors/confidence_up.npy \
  --model-path datasets/models/Qwen3-1.7B \
  --prompt 'What is 17 × 23?' --layer 20 \
  --strengths -0.1 -0.05 0.05 0.1 \
  --target-token 'digit3=3' --target-token 'digit4=4' \
  --random-directions 16 --seed 20261009 \
  --out backend/examples/output/vector_explanation/confidence_up_response_L20.json
```

需要支持模型的 PyTorch / Transformers 版本和本地权重。默认 CPU、float32、
eager attention，只从本地加载。当前机器的可用环境是 `.cache/venv_steer/bin/python`。
也可以用 `--device cuda:0`。模型须提供 Llama 风格的 `model.layers` 和 `model.norm`。

这里的 `--layer 20` 指 **0 起算 block 20 的输入**；`--hidden-index` 只是磁盘
数组的索引，必须按采集器核对输入/输出以及最终 normalization，不能直接互换。
每一臂都从完全相同的 token 前缀重新前向，不用 KV cache，
只在最后一个输入位置注入，因此不会混入前缀文字变化或旧 cache 的干预历史。
绝对注入量 `alpha = strength × 当前前缀在注入点的实测范数`。

报告给出：

- 零强度对照；输出和捕获状态必须逐位相同，否则拒绝生成因果报告。
- ±v 与多剂量下的下一 token、熵、KL 和目标 token 集合的概率质量变化。
- 按 log 概率变化排序的提升/抑制 token，以及按实际概率质量变化排序的 token。
  二者都附原始和干预后概率，避免把罕见 token 的大比例变化误读成主要行为变化。
- 各 block 输出与最终 post-norm 状态的位移，以及位移与注入向量的余弦。
- 经过全部下游 block 的有限差分响应：
  `d log p / d alpha ≈ [log p(+epsilon) − log p(−epsilon)] / (2 epsilon)`。
  同时报告半步长的差异和各剂量的一阶预测误差，显示数值稳定性与非线性。
- 同范数随机方向对照；最大剂量的目标集合比较也对全部目标集合做 max-stat 校正。

`--target-token name=text` 要求 text 恰好是一个 token；多个 token 的集合请用
`--target-ids targets.json`，格式为 `{"revision": [token_id_1, token_id_2]}`。
集合的概率是完整 softmax 上的质量，不是 top-k 内重归一化概率。

也可以直接解释已有推理链上的某一步：

```bash
python3 backend/examples/explain_vector.py respond \
  --vector backend/examples/output/steering_vectors/caution.npy \
  --model-path datasets/models/Qwen3-1.7B \
  --trajectory datasets/aime_qwen3_1p7b_16k_fp16/aime/aime__1989__1989_I_1__think.npz \
  --step 29 --layer 20 --target-token 'hmm= Hmm' \
  --random-directions 16 --seed 20261009 \
  --out backend/examples/output/vector_explanation/caution_response_recorded_step29.json
```

前缀严格取 `prompt_token_ids + token_ids[:29]`，不包含正在预测的第 29 个 token。
报告保留历史下一 token 与重跑 baseline 是否匹配。若不匹配，该结果解释的是
当前权重与精度下的固定前缀响应，不能声称复现了原始采集时的决策。

### 怎样写出有证据支撑的解释

合适的表述是：“在这些题目中该方向关联低熵；在这个前缀、这个层和强度下，
干预将概率质量从 A 移向 B，下游变化集中在这些层。”
关联读出不能证明因果必要性；局部干预不能证明整段推理策略或正确率发生变化。
后者需要在独立题目上做自由生成、±v、多剂量和随机方向对照，再评估实际行为。
要说明“通过哪个内部机制”，还需在候选中介特征、attention/MLP 或路径上做
消融、恢复或 path patching，检验能否消除/恢复已测效果。
现有 `run_paired_steering.py` 和 `run_intervention.py` 可以继续承担生成实验。

### 本地实测示例（2026-10-09）

产物保存在 `examples/output/vector_explanation/`。
`confidence_up_observed.json` 覆盖 48 条轨迹、24 道题、69,155 个生成状态：
熵相关为 −0.625，数字 token 相关为 +0.365。二者的随机方向 max-stat p
均为 1/65；由于提取与分析数据重叠，这些数不能作为独立泛化证据。

`confidence_up_response_L20.json` 在上述乘法问题的生成前缀上，+0.1 干预
使下一 token 熵增加 0.00953 nats；下一 token 的 argmax 仍为 `To`。
“与低熵相关”并不保证每个上下文上的正向注入都降低熵。

`caution_response_recorded_step29.json` 的 baseline 与历史第 29 个 token 匹配。
在该前缀的 L20，+0.1 干预把 ` Hmm` 概率从 96.64% 降到 96.16%，
把 ` Let` 从 2.58% 提到 3.21%；` Hmm` 的随机方向对照 p=13/17≈0.765，
没有体现超过随机方向的特异性。这是一个位置上的实测效果，
不能据此给整个向量重新命名，更不能推断整段思维链减少了自检。

方法参考：[CAA](https://arxiv.org/abs/2312.06681) 提供激活干预的基础；
[Tuned Lens](https://arxiv.org/abs/2303.08112) 提供隐藏层读出思路；
[Circuit Tracing](https://transformer-circuits.pub/2025/attribution-graphs/methods.html)
用特征干预检验机制假设。本接口的有限差分跑完整模型，不等同于 tuned lens 或电路图。

测试：`python3 -m pytest backend/tests -q`。包含数据索引、按题分组、零对照、
上下游位移、hook 清理，以及下游层把词表直投预测符号翻转的明确反例。

## Quick start (synthetic demo, no GPU needed)

```bash
pip install fastapi uvicorn numpy scikit-learn
python examples/demo_synthetic.py
```

This will start:
- HTTP at `http://localhost:8000`
- WebSocket at `ws://localhost:8000/ws`

The server emits `Frame` JSON objects on the WebSocket at a
rate of ~20 Hz (50 ms per simulated token). Frames contain the
3-D projected coordinates of baseline and steered paths plus
top-K token predictions.

## Quick start (real model, needs GPU)

```bash
pip install -r requirements.txt
python examples/demo_real_model.py \
    --model meta-llama/Llama-3.1-8B-Instruct \
    --layer 14 \
    --preset sycophancy
```

## Architecture

The backend is intentionally modular:

```
core/
├── protocol.py     # Frame dataclass + ControlMessage
├── steerer.py      # CAA-style steering vector extraction
├── activation.py   # PyTorch hooks for residual capture/injection
├── projector.py    # OnlinePCA / SketchUMAP for 3-D projection
└── model_runner.py # SyntheticRunner + HFTransformerRunner
server.py            # FastAPI + WebSocket glue
examples/            # demo entry points
```

The protocol is the only contract with the frontend — if you want
to swap in a different model implementation (nnsight, vLLM,
custom CUDA, etc.), just produce `Frame` instances and stream
them. Everything else is unchanged.

## WebSocket protocol

See `docs/PROTOCOL.md` in the project root for the full spec.

Quick summary:

- **Server → Client (Frame)** — sent once per token, contains 3-D
  path points for baseline and steered runs, top-K next-token
  predictions, scalar metrics, and a small projection of the
  steering vector for the front-end arrow.
- **Client → Server (ControlMessage)** — `start`, `cancel`,
  `set_alpha`, `set_preset`, `set_layer`, `reset`.

## Adding a new preset

Edit `core/protocol.py`'s `DEFAULT_PRESETS` dict:

```python
DEFAULT_PRESETS = {
    "my_new_preset": {
        "positive": "Prompt that strongly elicits the trait",
        "negative": "Prompt that strongly suppresses it",
    },
    ...
}
```

At boot, `extract_all_presets()` runs each contrastive pair
through the model and stores the resulting unit vector under
`PRESET_VECTORS[name]`.

## Adding SAE features

Replace the simple `OnlinePCA` in `model_runner.py` with a hybrid
pipeline:

1. Pull the residual stream as usual.
2. Encode via `sae_lens.SAE.from_pretrained(...)`.
3. Treat the top-K SAE indices as a sparse "feature vector" of
   length `d_sae` (e.g. 32 768).
4. Project that vector into 3-D via PCA / UMAP (same code path).

The frontend doesn't care whether the projection axis came from
a raw residual stream or a sparse SAE code; both produce a 3-D
point per token.

## Performance notes

- The synthetic demo generates ~20 frames per second. The
  pipeline uses ~50 ms per frame, so there's headroom for a real
  model on a single A100.
- `OnlinePCA` refits every 16 frames (in `_refit_components`)
  on the rolling 256-point window. The dominant cost is the SVD;
  switch to `IncrementalPCA` (default) which is `O(window * d)`.
- For >1M tokens, switch `OnlinePCA` to a fixed PCA basis that
  you pre-fit on a calibration set; or use a true online
  algorithm like CCIPCA / Oja's.
