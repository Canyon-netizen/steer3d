# Reasoning3D I/O Specification (v1.0)

本规范定义**模型推理过程中产生的所有数据**的**标准格式**以及**读写接口**。
任何想消费 Reasoning3D 数据的工具（前端、Python 脚本、Jupyter notebook、第三方分析）
都应该只通过本规范定义的接口和数据形状来访问。

> 关键原则：**没有"静态 HTML 快照"这种产出物**。所有推理数据要么是
> live stream（WebSocket），要么是用户主动 `save()` 出来的 JSON 文件。
> 任何把数据 bake 进 HTML 的行为都违反本规范。

---

## 1. 数据形状：一个 Run

**一次完整推理** = 1 个 `ReasoningRun`。它包含：

```
ReasoningRun
├── run_id          string   唯一标识（UUID 或 hash）
├── format_version  string   协议版本（"1.0"）
├── model           string   模型标识（如 "Qwen/Qwen3-1.7B"）
├── layer           int      hidden state 抓取的层索引
├── prompt          string   输入 prompt
├── started_at      float    unix 时间戳（秒）
├── finished_at     float?   推理结束时间，未结束为 null
├── metadata        object   自由扩展（temperature / max_new_tokens / steering info / ...）
├── generated_text  string   完整生成文本（拼接自 frames[].token）
└── frames          Frame[]  按 step_id 升序的 token 序列
```

每个 `Frame`：

```
Frame
├── ts             float    该 token 生成的 unix 时间戳
├── step_id        int      该 token 在 run 内的位置（0-indexed）
├── token          string   实际 token 文本（含前导空格等）
├── token_id       int      vocab 中的 id
├── point          Point3D  在线 PCA 后的 3D 坐标
│   ├── x          float
│   ├── y          float
│   └── z          float
├── perplexity     float?   1 / p(top-1)；null = 不可计算
├── entropy        float?   Shannon entropy (nats) of policy
├── loss           float?   用户自定义 loss-like scalar
├── is_self_check  bool     正则匹配的"自检"token（"wait"/"actually"/...）
└── is_revisit     bool     路径方向反转（前几步与当前步 dot < 0）
```

---

## 2. JSON Schema（机器可校验）

完整 JSON Schema 在 `backend/core/reasoning_io.py` 的 `RUN_SCHEMA` 常量里。
任何保存/导出的 `.json` 文件**必须能通过 `jsonschema.validate(...)` 检查**。

最小合法 Run 示例：

```json
{
  "format_version": "1.0",
  "run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "model": "Qwen/Qwen3-1.7B",
  "layer": 14,
  "prompt": "What is the capital of France?",
  "started_at": 1789999437.016,
  "finished_at": 1789999438.456,
  "metadata": {
    "temperature": 0.7,
    "max_new_tokens": 100,
    "steering": null
  },
  "generated_text": " The capital of France is Paris.",
  "frames": [
    {
      "ts": 1789999437.217,
      "step_id": 0,
      "token": " The",
      "token_id": 576,
      "point": {"x": -9.26, "y": 4.92, "z": 39.37},
      "perplexity": 1.0004,
      "entropy": 0.0037,
      "loss": null,
      "is_self_check": false,
      "is_revisit": false
    }
  ]
}
```

---

## 3. Python 接口

### 3.1 读

```python
from core.reasoning_io import ReasoningRun, read_run, stream_run_ws

# 从 JSON 文件读（同步）
run = read_run("/path/to/run.json")

# 从已有 JSON 字符串读
run = ReasoningRun.from_json('{"format_version": "1.0", ...}')

# 从 WebSocket 流读（async）—— 处理 Frame 消息直到收到 finished 或连接关闭
async def consume(ws):
    run = await stream_run_ws(ws, on_frame=lambda f: print(f.token))
    # run.frames 已累积完整；run.finished_at 不为 None
```

### 3.2 写

```python
# 写 JSON 文件
run.save("/path/to/run.json")

# 序列化为 dict（用于内存中传递）
data = run.to_dict()

# 序列化为 JSON 字符串
s = run.to_json()
```

### 3.3 校验

```python
from core.reasoning_io import validate_run, RUN_SCHEMA

# 任何 dict 都可以校验
validate_run(some_dict)  # 抛 ValueError 如果不合规
```

---

## 4. TypeScript 接口

前端使用 `frontend/lib/reasoning-types.ts` 定义的类型。
任何前端消费者**应该只引用这些类型**，不要重新定义。

```typescript
import type { ReasoningRun, Frame, Point3D } from "@/lib/reasoning-types";

// 从 WebSocket 流构造一个 Run
class RunBuilder {
  pushFrame(frame: Frame): void;
  finish(): ReasoningRun;
}
```

---

## 5. 动态 vs 静态：使用模式

### 模式 A：Live 实时消费（推荐）

```
backend server.py → WebSocket frames → 任意 consumer
                                  ├─ browser (live_terrain.html)
                                  ├─ Python script (save_run.py)
                                  └─ Jupyter notebook
```

**关键**：consumer 直接连 WebSocket，**不读 bake 过的 HTML**。

### 模式 B：保存后回放（用于论文、debug）

```
backend server.py → WebSocket frames → Python script (save_run.py)
                                          ↓
                                    .json file (标准格式)
                                          ↓
                                    任何符合本规范的 reader
```

回放时也是动态的：reader 把 JSON 文件按 10 Hz 流式吐 frames 给前端，
前端**不知道也不需要知道**这些 frame 是来自 live 还是 replay。

### 反模式（**禁止**）

- 把 frames bake 成 `view_xxx.html` 静态文件 → **违反规范**
- 在 consumer 端用 eval / Function 解析字符串代码
- 把 hidden state raw vector 也烤进 HTML（太大）

---

## 6. 版本兼容

- 当前：`"format_version": "1.0"`
- 任何不识别的 format_version，**reader 必须抛 ValueError**，不能默默兼容
- 字段新增是兼容的（reader 忽略未知字段）；字段删除/重命名是 breaking change → 必须 bump 版本

---

## 7. 快速验证你的实现

```bash
cd backend
python -c "from core.reasoning_io import ReasoningRun, RUN_SCHEMA; \
           r = ReasoningRun.from_json(open('tests/fixtures/sample_run.json').read()); \
           print('OK' if r.n_tokens > 0 else 'FAIL')"
```

或者跑测试：
```bash
pytest tests/test_reasoning_io.py -v
```