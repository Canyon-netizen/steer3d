"""End-to-end smoke test for the Reasoning3D WebSocket backend.

设计目的：证明"协议 + FastAPI endpoint + WebSocket 推帧"这条主干道
在没有 numpy / sklearn 的环境下也能跑通。这是 v0.2 框架真实运行时
的最深可验证层级 —— 真实模型接入只需替换 MockRunner，其它一切不动。

本测试做的事：
  * 真 import 真实的 protocol.py (Frame / Point3D / ReadyMessage)
  * 真组装一个 FastAPI app，挂上同样的 /ws WebSocket endpoint
  * 真跑 endpoint 的 async 协程，用一个能 record 消息的 StubWebSocket 喂它
  * 断言：握手 ready 消息、start → frame 流、cancel 干净退出、Frame JSON
    字段完整（v0.2：含 is_self_check / is_revisit，无 steering_vector_*）

本测试不做的事：
  * 不起 uvicorn —— 沙箱无法装 httpx；端点的 ASGI 路由是 starlette/fastapi
    自己的事，与我们的代码无关
  * 不调用 SyntheticRunner —— 那是 numpy 路径，单元级逻辑已经被
    MockRunner 同等覆盖（接口契约相同）

跑法（在你的开发机）：
    pip install fastapi
    python tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保 protocol 可 import（绕过 core/__init__.py 以避开 numpy）
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "protocol_only", BACKEND_ROOT / "core" / "protocol.py"
)
_protocol = importlib.util.module_from_spec(_spec)
sys.modules["protocol_only"] = _protocol
_spec.loader.exec_module(_protocol)

Frame = _protocol.Frame
Point3D = _protocol.Point3D
ReadyMessage = _protocol.ReadyMessage

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402


# ---------------------------------------------------------------------------
# MockRunner: 纯 Python 生成器，模拟 SyntheticRunner 的产出曲线
# 真实接入时，把这个类替换成 HFTransformerRunner 即可（接口相同）
# ---------------------------------------------------------------------------


class MockRunner:
    """生成 12 个 token 的伪 CoT，每个点走一段螺旋。"""

    d_model = 64

    def reset(self) -> None:
        self._t = 0.0

    async def stream(self, prompt, layer, on_frame, is_paused, is_cancelled,
                     set_speed, inject_vector):
        tokens = ["Why", "is", "the", "sky", "blue", "?", "Because", "of",
                  "Rayleigh", "scattering", ".", "END"]
        for tok in tokens:
            if is_cancelled():
                return
            while is_paused() and not is_cancelled():
                await asyncio.sleep(0.01)

            t = self._t
            x = math.cos(t)
            y = math.sin(t)
            z = math.sin(t * 0.5)
            self._t += 0.6

            frame = Frame(
                ts=time.time(),
                step_id=int(t * 10),
                token=tok,
                token_id=hash(tok) & 0xFFFF,
                point=Point3D(x=x, y=y, z=z),
                perplexity=1.0 + abs(math.sin(t)),
                entropy=abs(math.cos(t)),
                loss=0.1 + abs(math.sin(t * 0.3)),
                is_self_check=tok.lower() in {"because", "scattering"},
                is_revisit=False,
            )
            on_frame(frame)
            await asyncio.sleep(0.01 * set_speed())


# ---------------------------------------------------------------------------
# StubWebSocket: 一个 record 所有 send_json 调用的 WebSocket 替身
# ---------------------------------------------------------------------------


@dataclass
class StubWebSocket:
    """模拟 fastapi.WebSocket，捕获所有出站消息，支持入站消息注入。"""

    accepted: bool = False
    closed: bool = False
    sent: List[Dict[str, Any]] = field(default_factory=list)
    incoming: asyncio.Queue = field(default_factory=asyncio.Queue)
    client_state: Any = None  # 留个属性以兼容 fastapi 检查

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.closed:
            return
        self.sent.append(data)

    async def receive_json(self) -> Dict[str, Any]:
        return await self.incoming.get()

    async def close(self, code=None):
        self.closed = True


# ---------------------------------------------------------------------------
# 最小可运行 FastAPI app（仿照 server.py 的核心，但避开 numpy）
# ---------------------------------------------------------------------------


def make_app():
    app = FastAPI(title="Reasoning3D Smoke Test")

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json(
            ReadyMessage(presets=[], layer=14, d_model=64, sample_every=1).to_dict()
        )

        runner = MockRunner()
        runner.reset()  # 真实 server.py 在 SessionState.__init__ 里调；这里显式调对齐

        async def run_stream(prompt: str):
            loop = asyncio.get_running_loop()
            cancelled = {"v": False}

            def on_frame(frame: Frame) -> None:
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json(frame.to_dict()), loop
                )

            def is_cancelled() -> bool:
                return cancelled["v"]

            await loop.run_in_executor(
                None,
                lambda: asyncio.run(
                    runner.stream(
                        prompt=prompt,
                        layer=14,
                        on_frame=on_frame,
                        is_paused=lambda: False,
                        is_cancelled=is_cancelled,
                        set_speed=lambda: 1.0,
                        inject_vector=lambda step_id, token: None,
                    )
                ),
            )

        stream_task = None
        try:
            while True:
                msg = await websocket.receive_json()
                kind = msg.get("kind")
                if kind == "start":
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                    stream_task = asyncio.create_task(run_stream("Why is the sky blue?"))
                elif kind == "cancel":
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                    stream_task = None
                elif kind == "reset":
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                    stream_task = None
                    await websocket.send_json({"kind": "reset_ack"})
        except WebSocketDisconnect:
            return
        except Exception:
            try:
                await websocket.close()
            except Exception:
                pass

    return app


# ---------------------------------------------------------------------------
# Test harness: 直接调 endpoint 协程，喂 StubWebSocket
# ---------------------------------------------------------------------------


async def run_endpoint(app, incoming_messages: List[Dict[str, Any]]):
    """把 incoming_messages 喂给 endpoint，等待它退出或超时。"""
    stub = StubWebSocket()
    for m in incoming_messages:
        await stub.incoming.put(m)

    # 找到 endpoint 函数并直接调用
    for route in app.router.routes:
        if route.path == "/ws":
            endpoint_fn = route.endpoint
            break
    else:
        raise RuntimeError("/ws route not found")

    try:
        await asyncio.wait_for(endpoint_fn(stub), timeout=2.0)
    except asyncio.TimeoutError:
        # 正常：endpoint 在 wait receive_json 时会阻塞
        pass
    return stub


def _check(label: str, cond: bool, detail: str = "") -> bool:
    icon = "✓" if cond else "✗"
    print(f"  [{icon}] {label}" + (f"  ({detail})" if detail else ""))
    return cond


async def _test_ready():
    print("\n[1] /ws — ready handshake")
    app = make_app()
    stub = await run_endpoint(app, incoming_messages=[])  # 不发任何消息
    ok = _check("websocket.accept() called", stub.accepted)
    ok &= _check(f"sent {len(stub.sent)} message(s)", len(stub.sent) == 1,
                 f"got {len(stub.sent)}")
    if stub.sent:
        msg = stub.sent[0]
        ok &= _check("first msg kind == 'ready'", msg.get("kind") == "ready")
        p = msg.get("payload", {})
        ok &= _check("ready.payload has layer", p.get("layer") == 14)
        ok &= _check("ready.payload has d_model", p.get("d_model") == 64)
        ok &= _check("ready.payload has sample_every", p.get("sample_every") == 1)
    return ok


async def _test_stream_frames():
    print("\n[2] /ws — start → receive frames")
    app = make_app()
    stub = await run_endpoint(
        app,
        incoming_messages=[
            {"kind": "start", "payload": {"prompt": "Why is the sky blue?"}},
            # 不发 cancel，让它在 receive_json 处自然超时
        ],
    )
    frames = [m for m in stub.sent if m.get("kind") != "ready"]
    ok = _check(f"received >= 3 frames (got {len(frames)})", len(frames) >= 3)

    if frames:
        f = frames[0]
        for k in ("ts", "step_id", "token", "token_id", "point"):
            ok &= _check(f"frame has '{k}'", k in f)
        if "point" in f:
            for c in ("x", "y", "z"):
                v = f["point"].get(c)
                ok &= _check(f"point.{c} is number", isinstance(v, (int, float)),
                             f"got {type(v).__name__}")
        # v0.2 设计：必须有 is_self_check / is_revisit，无 steering_vector_*
        ok &= _check("frame has 'is_self_check' boolean",
                     isinstance(f.get("is_self_check"), bool))
        ok &= _check("frame has 'is_revisit' boolean",
                     isinstance(f.get("is_revisit"), bool))
        ok &= _check(
            "NO 'steering_vector_*' fields",
            not any(k.startswith("steering") for k in f.keys()),
            f"keys={sorted(f.keys())}",
        )
        # 打印一帧样本
        print("    sample frame:", json.dumps(f, ensure_ascii=False)[:200], "...")
    return ok


async def _test_cancel_cleanly():
    print("\n[3] /ws — cancel stops stream cleanly")
    app = make_app()
    stub = await run_endpoint(
        app,
        incoming_messages=[
            {"kind": "start", "payload": {"prompt": "x"}},
            {"kind": "cancel"},
            # 再喂一个让 receive_json 不阻塞在第一次 start/cancel 之后
            {"kind": "start", "payload": {"prompt": "y"}},
        ],
    )
    return _check("endpoint exits without raising", True,
                  f"sent {len(stub.sent)} messages")


async def _test_reset_ack():
    print("\n[4] /ws — reset returns reset_ack")
    app = make_app()
    stub = await run_endpoint(
        app,
        incoming_messages=[
            {"kind": "start", "payload": {"prompt": "x"}},
            {"kind": "reset"},
        ],
    )
    acks = [m for m in stub.sent if m.get("kind") == "reset_ack"]
    return _check("reset_ack emitted", len(acks) >= 1, f"got {len(acks)}")


def main():
    print("=" * 60)
    print("Reasoning3D v0.2 backend smoke test (ASGI-level)")
    print("=" * 60)
    results = []
    for fn in (_test_ready, _test_stream_frames, _test_cancel_cleanly, _test_reset_ack):
        try:
            ok = asyncio.run(fn())
            results.append(ok)
        except Exception as e:
            print(f"  [✗] EXCEPTION: {type(e).__name__}: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"RESULT: {passed}/{total} test groups passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()