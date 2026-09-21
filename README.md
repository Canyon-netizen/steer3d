# Reasoning3D —— LLM Hidden States 实时 3D 推理可视化

> 把模型在生成推理链时的 **hidden states 流**实时投到 3D 空间，让你能看到模型"想的过程"的轨迹、节奏和分叉。
>
> 这是个**最小可运行框架**：先跑通合成数据的演示，理解了之后，再把您自己的向量注入逻辑接进来。

## 🎯 核心目标

| 想要 | 解法 |
|------|------|
| 把 LLM 推理过程中每一 token 的 hidden state 拿出来 | backend 流式 hook，每 token 一帧 |
| 在 3D 空间看推理轨迹 | 在线 PCA / UMAP 流式降维 |
| 看到完整的思维链动态 | Three.js 实时渲染 + 粒子流光 |
| 不需要 GPU 也能跑通 | 合成数据模式 (`SyntheticRunner`) |

## 🚀 快速开始（无需 GPU）

```bash
# 后端
cd backend
pip install fastapi uvicorn numpy scikit-learn
python examples/demo_synthetic.py
# → ws://localhost:8000/ws

# 前端（另一个终端）
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

打开浏览器，输入 prompt（如 "Why is the sky blue?"），
点击 **Run**，看到 3D 场景中：
- 一条**彩色 ribbon** 实时延伸（CoT 的轨迹）；
- **当前 token 粒子**带着文字飘出来；
- **历史 token 散点**沿轨迹分布；
- **流光效果**展示生成方向。

## 🧪 接您自己的向量注入

向量注入的 hook 已经在 `core/activation.py` 中预留好：

```python
# backend/core/activation.py
def install_residual_add_hook(model, layer_idx, add_vector):
    """在你选的层注入向量。这是接您自己逻辑的入口。"""
    ...
```

```python
# 在 model_runner.py 的 stream() 里：
# 1. 每个 token 前，先调用您的向量计算函数得到 add_vector
add_vector = my_steering_fn(...)
# 2. 安装 hook
handle = install_residual_add_hook(model, layer_idx, add_vector)
# 3. 生成下一 token
next_token = model.generate_one_token(...)
# 4. 提取 hidden state
h = get_residual_at_last_token(model, layer_idx, prompt)
# 5. 移除 hook
handle.remove()
# 6. 推送 Frame 到 WebSocket
await ws.send_json({
    "ts": time.time(),
    "step_id": i,
    "token": next_token.text,
    "activation_3d": projector.update(h).to_dict(),
    ...
})
```

**前端代码完全不用动**，因为它只关心 `Frame` 协议。

## 🏗 架构

```
┌──────────────────────────────────────────────────────────────┐
│              Browser (Next.js + Three.js)                     │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  3D Scene                                                │  │
│  │   • CoT trajectory（带流光的 ribbon）                  │  │
│  │   • 历史 token 散点                                    │  │
│  │   • 当前 token 粒子 + 文字                            │  │
│  │   • 自检回溯路径（橙黄色高亮）                       │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─Control─────┐  ┌─Token View─────┐                          │
│  │ • prompt     │  │ • 当前 token    │                          │
│  │ • layer 下拉 │  │ • 历史展开     │                          │
│  │ • 速度控制  │  │ • 困惑度曲线   │                          │
│  │ • pause/play│  │                  │                          │
│  └─────────────┘  └──────────────────┘                          │
│                          ↕ WebSocket JSON                       │
└──────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────┐
│             Backend (FastAPI + WebSocket)                      │
│                                                                │
│  server.py      — 流式 hub                                    │
│  core/          — 协议 + 模型 + 投影 + 向量 hook              │
│  examples/      — demo 入口（合成 / 真实）                    │
└──────────────────────────────────────────────────────────────┘
```

## 📁 目录结构

```
steering3d/
├── README.md                       ← 本文件
├── ARCHITECTURE.md                 ← 架构详解
├── docs/PROTOCOL.md                ← WebSocket 协议
├── backend/
│   ├── server.py                   ← 主入口
│   ├── core/
│   │   ├── protocol.py             ← Frame 数据类
│   │   ├── projector.py            ← 在线 PCA / UMAP
│   │   ├── activation.py           ← 激活提取 hook + 向量注入 hook
│   │   └── model_runner.py         ← SyntheticRunner / HFTransformerRunner
│   └── examples/
│       ├── demo_synthetic.py       ← 无 GPU 演示
│       └── demo_real_model.py      ← 接真实模型
├── frontend/
│   ├── app/{page,layout,globals.css}
│   ├── components/
│   │   ├── Scene3D.tsx             ← 3D 推理轨迹
│   │   ├── ControlPanel.tsx        ← prompt + layer + speed
│   │   ├── TokenStreamPanel.tsx    ← 文字流 + 历史展开
│   │   └── Legend.tsx
│   └── lib/
│       ├── frame-types.ts
│       ├── ws-client.ts
│       └── store.ts
```

## 🎮 功能列表

- ✅ **实时流式 3D 路径**：每生成一个 token，添加一个 3D 点
- ✅ **历史展开**：UI 侧栏可滚动看完整 reasoning trace
- ✅ **困惑度曲线**：每个 token 的颜色反映模型当时的不确定性
- ✅ **层选择**：可视化哪一层的 hidden state（默认 14）
- ✅ **暂停/恢复**：可控节奏
- ✅ **速度控制**：0.5x / 1x / 2x
- ✅ **重置**：清空当前 trajectory 开始新一轮
- ⏳ **Hook 点**：在 `activation.py:install_residual_add_hook` 已预留

## 🎯 与 LoT 的关系

Landscape of Thoughts（ICLR 2025/2026）证明了 **2D + 离线 + 观察**这条路。本框架：
- ✅ **3D**（LoT 没做）
- ✅ **实时流式**（LoT 是离线批量）
- ✅ **动态**（LoT 是静态图片 + 时间动画）
- ➕ **向量干预接入点**（LoT 没有）
- ➕ **完整可视化轨迹**（不是景观等高线）

适合做"LLM 内部思维的可视化探索工具"。