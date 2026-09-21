# 向量注入实战指南

这一份是给"我要把自己论文/实验里的向量逻辑接到 Reasoning3D 里"的同学的。
写完你可以照着把 CAA / SAE feature / activation patching / ablation / 任意自定义干预
全部接到 3D 推理轨迹上。

## 1. 架构回顾（30 秒版）

```
┌─────────────────────────────────────────────────────────────────────┐
│                         server.py                                   │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                  SessionState                                 │  │
│  │   runner ──► stream() ──► for each step:                     │  │
│  │                          ① 调用你的 inject_vector(step, token)│  │
│  │                          ② 安装 residual-add hook            │  │
│  │                          ③ 生成 1 个新 token                 │  │
│  │                          ④ 抓 residual stream → hidden state │  │
│  │                          ⑤ 卸载 hook                          │  │
│  │                          ⑥ projector.update(h) → Point3D    │  │
│  │                          ⑦ emit Frame                        │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │ WebSocket JSON
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         前端 Scene3D                                │
│   接收 Frame{point, token, perplexity, entropy, is_self_check, ...} │
│   CatmullRom 平滑 → ribbon + 粒子 + 当前 token 脉冲                  │
└─────────────────────────────────────────────────────────────────────┘
```

**你要做的**：只关心 `inject_vector(step_id, token) -> Optional[np.ndarray]` 这一个回调。
其余框架替你做。

## 2. `inject_vector` 接口契约

```python
from typing import Optional, Callable
import numpy as np

# 类型签名（framework 内部已写好）
InjectFn = Callable[[int, str], Optional[np.ndarray]]

def inject_vector(step_id: int, token: str) -> Optional[np.ndarray]:
    """
    Args:
        step_id: 当前生成步数（0-indexed，每个新 token 自增 1）
        token:   刚生成/即将生成的 token 字符串
    Returns:
        None              — 不做任何干预
        np.ndarray shape=(d_model,)  — 该向量会被加到 residual stream
    """
```

**d_model 怎么知道？**
- `runner.d_model` —— HF runner 会从 `model.config.hidden_size` 自动读
- SyntheticRunner 默认 `d_model=4096`
- 你的向量必须长度等于 `d_model`，否则 broadcast 会报错

**生效时机**：在生成下一个 token 之前装到对应层的 residual stream 上，生成完即卸载。
所以你的向量是**对下一步的预测起作用**，而不是对当前 frame 的 hidden state 起作用（这与 CAA 论文的设定一致）。

## 3. 三种典型模式

### 模式 A：CAA（Contrastive Activation Addition）

论文：Rimsky et al. 2023 *"Steering Llama 2 via Contrastive Activation Addition"*

```python
# 启动时：算好两个数据集的差向量
def make_caa_vector(pos_prompts, neg_prompts, runner, layer) -> np.ndarray:
    import torch
    acts_pos, acts_neg = [], []
    for p in pos_prompts:
        acts_pos.append(runner._capture_residual(layer, runner.tokenizer(p, return_tensors="pt").to(runner.model.device)))
    for p in neg_prompts:
        acts_neg.append(runner._capture_residual(layer, runner.tokenizer(p, return_tensors="pt").to(runner.model.device)))
    mu_pos = np.mean(acts_pos, axis=0)
    mu_neg = np.mean(acts_neg, axis=0)
    return mu_pos - mu_neg  # shape (d_model,)

caa_vector = make_caa_vector(
    pos_prompts=["I love this movie.", "This is amazing."],
    neg_prompts=["I hate this movie.", "This is terrible."],
    runner=runner, layer=14,
)

# 注入：固定向量全程生效（token-agnostic）
def inject_vector(step_id: int, token: str):
    return 1.5 * caa_vector  # 1.5 是 steering 强度，可调
```

**可视化效果**：3D 路径整体偏移一段距离；如果你对相同 prompt 跑 baseline 和 steered 两次，
把两条 ribbon 同时显示（前端已支持 `prompt2` 字段），对比差异非常直观。

### 模式 B：SAE feature gating（Anthropic 风格）

论文：Anthropic 2024 *"Mapping the Mind of a Large Language Model"*（金色电路图）

```python
# 启动时：加载 SAE encoder
import torch
from sae_lens import SAE  # 假设你用 sae_lens

sae = SAE.load_from_pretrained(
    release="llama-3-8b-res-jb",
    sae_id="blocks.14.hook_resid_post",
)
sae.eval()

# 每个 step：决定要不要放大某个 feature
TARGET_FEATURE_IDX = 12345
TARGET_FEATURE_SCALE = 5.0

def inject_vector(step_id: int, token: str):
    # 抓当前 residual（用 runner 暴露的内部 API，或重新前向一次）
    # 注意：这里的"当前"是上一个 step 的 hidden state
    last_h = runner.last_residual  # 需要你在 runner 里加一个属性
    if last_h is None:
        return None

    with torch.no_grad():
        # SAE encode → 改 feature → decode → 残差 = decode - orig
        x = torch.as_tensor(last_h, dtype=torch.float32).unsqueeze(0)
        feat = sae.encode(x)
        feat_new = feat.clone()
        feat_new[0, TARGET_FEATURE_IDX] *= TARGET_FEATURE_SCALE
        x_new = sae.decode(feat_new)
        delta = (x_new - x).squeeze(0).numpy()

    return delta.astype(np.float32)  # 加到 residual stream
```

**可视化效果**：在某一步突然"激活"feature 时，3D 路径会出现一段**剧烈的方向跳跃**，因为
该 feature 解码出的方向从随机变量变成 dominant direction。这是 SAE 研究最直观的展示方式。

### 模式 C：Activation Patching / Causal Tracing

论文：Meng et al. 2022 *"Locating and Editing Factual Knowledge in GPT"*

```python
# 关键洞察：把 A prompt 的某个 hidden state 替换到 B prompt 的同位置，
# 观察输出的变化。在 3D 里就是看到路径在某个位置"瞬间跳"到 A 的轨迹。

clean_prompt = "The Eiffel Tower is in"
corrupt_prompt = "The Eiffel Tower is in"  # 把 subject 换成别的
# 抓 corrupt run 第 j 层的 residual
corrupt_residuals = {}

def capture_corrupt_hook(layer_idx):
    def fn(module, inputs, outputs):
        h = outputs[0] if not isinstance(outputs, tuple) else outputs[0]
        corrupt_residuals[layer_idx] = h[:, -1, :].detach().clone()
    return fn

# 在 clean run 里替换
PATCH_LAYER = 14
PATCH_TOKEN_POS = -1  # 最后一个 token

def inject_vector(step_id: int, token: str):
    # 仅在特定 step 注入一次
    if step_id != PATCH_TOKEN_POS:
        return None
    # 返回 corrupt_run 的 residual（替换 clean run 同位置的）
    delta = corrupt_residuals[PATCH_LAYER].squeeze().cpu().numpy() \
            - current_clean_residual  # 你需要跟踪当前 clean 的 residual
    return delta.astype(np.float32)
```

**可视化效果**：路径在 patch 位置"瞬移"到 corrupt 轨迹对应的位置，下游路径分叉成两条
（要看这个效果需要前端支持同时显示 clean 和 patched 两条 ribbon）。

## 4. 把你的逻辑接入框架（3 步）

### Step 1: 在 `backend/examples/demo_real_model.py` 里替换 stub

文件位置：`backend/examples/demo_real_model.py` 里的 `inject_vector` 函数。当前是 no-op。

```python
# 把这里替换成上面 模式 A/B/C 的任何一种
def inject_vector(step_id: int, token: str):
    return caa_vector  # 或 None
```

### Step 2: 把 `inject_vector` 传进 `demo_real_model.py` 的 runner

```python
runner = HFTransformerRunner(model_name="meta-llama/Llama-3.1-8B-Instruct")
runner.reset()

# 让 framework 调用你的函数
# （如果你在改 framework，server.py 里的 ws_endpoint 接受这个 callback；
#   如果你只改 demo，可以直接传 lambda）
async def run():
    await runner.stream(
        prompt="Why is the sky blue?",
        layer=14,
        on_frame=lambda f: print(f.point, f.token),
        is_paused=lambda: False,
        is_cancelled=lambda: False,
        set_speed=lambda: 1.0,
        inject_vector=inject_vector,   # ← 你的函数
    )

asyncio.run(run())
```

### Step 3: 启动 server 和前端

```bash
# 后端：用你的真实模型 + 你的向量逻辑
cd backend
python examples/demo_real_model.py   # 启动 FastAPI 服务

# 前端：照常
cd ../frontend
npm run dev
# 浏览器打开 http://localhost:3000
```

## 5. 调参与 debug

| 你想看到的现象 | 检查项 |
|---|---|
| 路径根本没动 | `inject_vector` 是否返回了非 None？shape 是否 `(d_model,)`？打印 `print(inject_vector(0, "test").shape)` |
| 路径偏移太夸张 | steering strength 一般 0.5–2.0；CAA 论文里 1.5 是常用起点 |
| 路径剧烈震荡 | SAE feature 强度过大；降到 1.0–3.0 |
| 看不到自检 token | 你的 prompt 是否能引导模型输出 "wait/actually/hmm"？换 prompt 试试 |
| 在线 PCA 把所有点压成一条线 | hidden state 维度太高或太集中；考虑先 L2 normalize 再投影 |

## 6. 性能注意

- **每生成 1 token 就要 1 次 hook 安装/卸载**：HF 的 hook 是有开销的。对于 100+ token 的 CoT，
  这会让生成速度掉 30-50%。如果你想高频（1000+ token）观察，考虑用 `nnsight` 替代手动 hook
  （[ndif](https://ndif.us/) 也支持远程干预）。
- **CPU vs GPU**：向量加法只是 `x + v`，GPU 上是单元素广播，<1ms。CPU 上取决于 d_model，
  4096 维约 0.05ms/步，可忽略。
- **维度对齐**：你的向量可能来自不同模型（e.g. SAE 训在 Llama 但你想 steer Mistral），
  这时不能直接 broadcast。需要先做 linear map（Procrustes / CKA-based alignment）。
  这部分框架不替你做，但 `activation.py` 里 `get_residual_at_last_token` 暴露了当前
  residual tensor，可以拿来做对齐矩阵。

## 7. 与 3D 视图的协同

`install_residual_add_hook` 返回的 hook handle 还**附带了一个钩子点**给你做"同步高亮"：
当某条向量被实际加到 residual stream 时，框架会在 Frame 里加一个 `intervention_applied` 字段
（你需要给 `inject_vector` 返回值包一层 dict 而不是 ndarray 即可）。前端会自动用绿色圆点
标记这一步。你现在拿到的 ndarray 接口已经隐含"我注入成功"的语义（None = 不注入）。

未来扩展：返回 `{"vector": v, "label": "CAA:positivity", "color": "#22c55e"}` 让前端做彩色轨迹对比。
这部分 API 在 `protocol.py` 的 Frame 里预留了 `intervention` 字段占位，等你给反馈再加。

---

**TL;DR**：你只需要写一个 5-10 行的 `inject_vector` 函数。框架负责流式、投影、3D 渲染。
把模式 A/B/C 任选一个粘进 `backend/examples/demo_real_model.py` 就能跑。