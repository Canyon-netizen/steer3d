"""FastAPI WebSocket server for Reasoning3D.

Streams per-token `Frame` JSON messages to the browser. Each frame
carries:
  * the token text + id,
  * a 3-D point (online PCA projection of hidden state at the
    configured layer),
  * scalar metrics (perplexity, entropy),
  * flags for self-check / revisit moments.

Control messages from the browser can change prompt / layer /
playback speed, or pause / resume / reset.

Run with:
    uvicorn server:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core import (
    Frame,
    Point3D,
    OnlinePCA,
    SyntheticRunner,
    default_runner,
)
from core.protocol import ReadyMessage


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------


app = FastAPI(title="Reasoning3D Backend", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Per-connection session state
# ---------------------------------------------------------------------------


class SessionState:
    """One session per WebSocket connection."""

    def __init__(self, runner_factory=None):
        self.layer = 14
        self.prompt: str = ""
        self.speed: float = 1.0
        self.paused = False
        self.cancelled = False
        factory = runner_factory or default_runner
        self.runner = factory()
        self.projector = OnlinePCA(d=self.runner.d_model, target_dim=3, window=256)
        self.runner.reset()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Allow runtime override of the runner factory via app.state (set by demos).
    factory = getattr(app.state, "runner_factory", None)
    state = SessionState(runner_factory=factory)

    # Greet with config so the UI can populate defaults.
    await websocket.send_json(
        ReadyMessage(
            presets=[],  # placeholder; reserved for future vector presets
            layer=state.layer,
            d_model=state.runner.d_model,
            sample_every=1,
        ).to_dict()
    )

    stream_task: Optional[asyncio.Task] = None

    async def run_stream(prompt: str, layer: int):
        """Bridge between the runner (sync-style) and the websocket
        (async). The runner calls `on_frame` from its own loop; we
        marshal those into asyncio using run_coroutine_threadsafe.
        """
        state.cancelled = False
        state.paused = False
        state.runner.reset()
        # Reset projector for a fresh path
        state.projector.reset()

        loop = asyncio.get_running_loop()
        send = websocket.send_json

        def on_frame(frame: Frame) -> None:
            asyncio.run_coroutine_threadsafe(send(frame.to_dict()), loop)

        def is_paused() -> bool:
            return state.paused

        def is_cancelled() -> bool:
            return state.cancelled

        def get_speed() -> float:
            return state.speed

        # Vector-injection hook stub. The user replaces this with
        # their own logic; returning None means no injection.
        def inject_vector(step_id: int, token: str):
            return None

        await loop.run_in_executor(
            None,
            lambda: _runner_emit_sync(
                state.runner.stream,
                prompt=prompt,
                layer=layer,
                on_frame=_wrap_projector(on_frame, state.projector),
                is_paused=is_paused,
                is_cancelled=is_cancelled,
                get_speed=get_speed,
                inject_vector=inject_vector,
            ),
        )

    # ------------------------------------------------------------------

    try:
        while True:
            msg = await websocket.receive_json()
            kind = msg.get("kind")
            payload = msg.get("payload", {})

            if kind == "start":
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                state.cancelled = True
                await asyncio.sleep(0.05)
                state.prompt = str(payload.get("prompt", "Why is the sky blue?"))
                layer = int(payload.get("layer", state.layer))
                state.layer = layer
                stream_task = asyncio.create_task(run_stream(state.prompt, layer))

            elif kind == "cancel":
                state.cancelled = True
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                stream_task = None

            elif kind == "pause":
                state.paused = True

            elif kind == "resume":
                state.paused = False

            elif kind == "set_layer":
                state.layer = int(payload.get("value", state.layer))

            elif kind == "set_speed":
                state.speed = float(payload.get("value", 1.0))

            elif kind == "set_prompt":
                state.prompt = str(payload.get("value", ""))

            elif kind == "reset":
                state.cancelled = True
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                state.paused = False
                state.runner.reset()
                state.projector.reset()
                stream_task = None
                await websocket.send_json({"kind": "reset_ack"})

            else:
                # Unknown message — ignore
                pass

    except WebSocketDisconnect:
        state.cancelled = True
        if stream_task and not stream_task.done():
            stream_task.cancel()
        return
    except Exception as e:
        try:
            await websocket.send_json(
                {"kind": "error", "payload": {"message": str(e)}}
            )
        except Exception:
            pass
        await websocket.close()


# ---------------------------------------------------------------------------
# Helper: run the (async) runner.stream() in a thread-safe wrapper.
# We can't directly call runner.stream() because it returns a coroutine.
# Instead the runner runs in a thread and calls the sync on_frame.
# ---------------------------------------------------------------------------


def _wrap_projector(
    on_frame: Callable[[Frame], None], projector: OnlinePCA
) -> Callable[[Frame], None]:
    """Apply the projector to a Frame's raw 3-D point before sending.

    The synthetic runner ships 3-D coordinates directly (projector is
    a pass-through). For the HF runner, the runner attaches a
    ``_raw_hidden`` attribute carrying the residual-stream vector;
    we project it via OnlinePCA and overwrite the Frame's ``point``
    field before forwarding.
    """

    def wrapped(frame: Frame) -> None:
        raw = getattr(frame, "_raw_hidden", None)
        if raw is not None and not getattr(frame, "_is_end", False):
            try:
                p = projector.update(np.asarray(raw, dtype=np.float64))
                frame.point.x = float(p.x)
                frame.point.y = float(p.y)
                frame.point.z = float(p.z)
            except Exception:
                # projector can be singular for the very first point;
                # fall back to identity
                frame.point.x = float(raw[0]) * 0.01
                frame.point.y = float(raw[1]) * 0.01
                frame.point.z = float(raw[2]) * 0.01
        on_frame(frame)

    return wrapped


def _runner_emit_sync(
    stream_fn,
    prompt: str,
    layer: int,
    on_frame: Callable[[Frame], None],
    is_paused: Callable[[], bool],
    is_cancelled: Callable[[], bool],
    get_speed: Callable[[], float],
    inject_vector: Optional[Callable[[int, str], Optional[np.ndarray]]],
):
    """Synchronous entry point. Runs the (async) runner.stream() to
    completion. The runner itself uses asyncio.sleep for pacing, so
    we run it via asyncio.run in its own thread.
    """
    import asyncio

    asyncio.run(
        stream_fn(
            prompt=prompt,
            layer=layer,
            on_frame=on_frame,
            is_paused=is_paused,
            is_cancelled=is_cancelled,
            set_speed=get_speed,
            inject_vector=inject_vector,
        )
    )


# ---------------------------------------------------------------------------
# HTTP routes for sanity checks
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {
        "name": "Reasoning3D Backend",
        "version": "0.2.0",
        "websocket": "/ws",
    }


@app.get("/health")
async def health():
    return {"ok": True}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)