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
    uvicorn server:app --host 0.0.0.0 --port 9503

The port was hard-coded to 8000 here while the frontend probed 9503
(`frontend/lib/ws-endpoint.ts`), so the two could never meet: 8000 was
abandoned on the frontend side precisely because a stray `python
http.server` had squatted it, and nobody moved the backend. A process
listening on 8000 therefore said nothing about whether the UI could
connect. The port is now read from `REASONING3D_PORT` and defaults to
the one the frontend actually probes.
"""

from __future__ import annotations

import asyncio
import os
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
from core.steering import get_registry, InterventionController


# The port the frontend probes. Duplicated in `frontend/lib/ws-endpoint.ts`
# as DEFAULT_WS_PORT_CANDIDATES; the two must agree or the UI silently sits
# at "disconnected" with no error. `GET /health` reports this value so a
# mismatch is something you can read rather than something you infer.
WS_PORT = int(os.environ.get("REASONING3D_PORT", "9503"))


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
        # Bumped whenever a new stream is started or the session is reset.
        # Frames carry the epoch they were produced under, and on_frame
        # drops anything older.
        #
        # Why this is needed: the runner's work runs inside
        # `loop.run_in_executor`, i.e. on a plain thread. Cancelling the
        # asyncio task does NOT stop that thread, and every frame it has
        # already handed to `asyncio.run_coroutine_threadsafe` still
        # lands. So `reset` cleared the UI's token list and then one or
        # two more tokens from the *previous* recording arrived
        # afterwards -- the panel showed a stray token from another
        # problem sitting at the head of a freshly reset trace.
        #
        # `cancelled` alone cannot fix this: run_stream sets it back to
        # False when it begins, so a superseded thread that has not yet
        # reached its next is_cancelled() check sees False and keeps
        # going. An epoch is monotonic, so a stale thread can never
        # un-stale itself.
        self.epoch = 0
        factory = runner_factory or default_runner
        self.runner = factory()
        self.projector = OnlinePCA(d=self.runner.d_model, target_dim=3, window=256)
        self.runner.reset()
        # Active steering interventions for this session. The callback it
        # exposes is what actually gets handed to runner.stream().
        self.interventions = InterventionController(get_registry())


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
    registry = get_registry()
    await websocket.send_json(
        ReadyMessage(
            presets=registry.names,
            layer=state.layer,
            d_model=state.runner.d_model,
            sample_every=1,
            # What this runner can really replay. See ReadyMessage.layers for
            # why the UI is not left to hardcode a list.
            #
            # The list lives on the *runner*, not on the session: the replay
            # runner reports the 28 layers that are actually in the npz.
            # This line used to read `getattr(state, "available_layers", [])`,
            # which never existed on the session, so `layers` was always []
            # and the UI fell back to its own hardcoded guesses. Session first
            # (a demo may set it there), then runner.
            layers=list(
                getattr(state, "available_layers", None)
                or getattr(state.runner, "available_layers", None)
                or []
            ),
            # Which recordings can actually be replayed. The replay runner
            # matches the prompt against these ids and falls back to the
            # first one when nothing matches, so a free-text prompt box
            # silently showed the wrong problem. Handing the list to the UI
            # lets it offer only choices that exist.
            trajectories=list(
                (getattr(state.runner, "describe", None) or (lambda: []))()
            ),
        ).to_dict()
    )
    # Directions carry their own metadata (which layer they were extracted
    # at, how strong the validation effect was) so the UI can show the
    # evidence alongside the control rather than making the user trust us.
    await websocket.send_json({
        "kind": "steering_catalog",
        "payload": {
            "available": registry.loaded,
            "error": registry.load_error,
            "directions": registry.describe(),
            "calibration": registry.calibration(),
        },
    })

    stream_task: Optional[asyncio.Task] = None

    async def run_stream(prompt: str, layer: int):
        """Bridge between the runner (sync-style) and the websocket
        (async). The runner calls `on_frame` from its own loop; we
        marshal those into asyncio using run_coroutine_threadsafe.
        """
        state.cancelled = False
        state.paused = False
        # Capture the epoch this run belongs to. Anything a superseded
        # thread emits afterwards carries an older one and is dropped in
        # on_frame, so a reset or a re-start leaves no residue.
        epoch = state.epoch
        state.runner.reset()
        # Reset projector for a fresh path
        state.projector.reset()

        loop = asyncio.get_running_loop()
        send = websocket.send_json

        async def _send_if_current(ep: int, frame: Frame) -> None:
            """Re-check the epoch on the event loop, immediately before
            the send actually happens.

            Checking in `on_frame` is not enough. That runs on the
            runner's thread and only *schedules* the send via
            run_coroutine_threadsafe; the coroutine then sits in the
            loop's queue. A frame handed over microseconds before the
            next `start` bumps the epoch is therefore already queued, and
            it lands on the socket *after* the new stream began -- the
            UI then shows the tail of the old recording at the head of
            the new one. Re-checking here closes that window: the epoch
            is only ever bumped from the loop too, so "passed the check"
            and "was still current" are the same statement.
            """
            if ep != state.epoch:
                return
            await send(frame.to_dict())

        def on_frame(frame: Frame) -> None:
            if epoch != state.epoch:
                return
            asyncio.run_coroutine_threadsafe(
                _send_if_current(epoch, frame), loop)

        def is_paused() -> bool:
            return state.paused

        def is_cancelled() -> bool:
            # Per-run, not per-session. `state.cancelled` cannot be used
            # here: run_stream sets it back to False when the *new* run
            # begins, so a superseded thread that has not yet reached its
            # next check sees False and keeps streaming to the end of the
            # trajectory. Measured on the two-back-to-back-start case: the
            # old run emitted 294 further frames after being replaced.
            #
            # The epoch is monotonic and only this session bumps it, so
            # "my epoch is no longer current" is the same statement as
            # "I have been replaced" -- and unlike the flag it cannot be
            # reset by the run that replaced me.
            return state.cancelled or epoch != state.epoch

        def get_speed() -> float:
            return state.speed

        # Vector injection. The InterventionController owns which
        # interventions are active and returns their sum; returning None
        # (nothing active) means the runner skips the hook entirely, so
        # an unsteered run costs exactly what it did before.
        inject_vector = state.interventions.make_callback()

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
                # Retire the previous run before the new one starts, so
                # its in-flight frames are dropped rather than appended to
                # the new recording.
                state.epoch += 1
                await asyncio.sleep(0.05)
                state.prompt = str(payload.get("prompt", "Why is the sky blue?"))
                layer = int(payload.get("layer", state.layer))
                state.layer = layer
                stream_task = asyncio.create_task(run_stream(state.prompt, layer))

            elif kind == "cancel":
                state.cancelled = True
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                # Retire the thread, not just the task: see SessionState.epoch.
                state.epoch += 1
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
                # Same reason as `start`: retire the running thread before
                # reset_ack tells the UI to clear its token list.
                state.epoch += 1
                state.paused = False
                state.runner.reset()
                state.projector.reset()
                stream_task = None
                await websocket.send_json({"kind": "reset_ack"})

            # ----- interventions -----

            elif kind == "inject_steering":
                direction = str(payload.get("direction", ""))
                strength = float(payload.get("strength", 0.1))
                layer = int(payload.get("layer", state.layer))
                try:
                    rec = state.interventions.add(direction, strength, layer)
                except KeyError as e:
                    await websocket.send_json({
                        "kind": "error",
                        "payload": {"message": str(e)},
                    })
                    continue
                # Ack with the *resolved* vector norm so the UI can show
                # how big the actual perturbation is, not just the
                # abstract strength the user dragged.
                resolved = state.interventions.registry.scaled(
                    direction, strength, layer
                )
                await websocket.send_json({
                    "kind": "steering_ack",
                    "payload": {
                        "intervention": rec,
                        "injected_norm": (
                            float(np.linalg.norm(resolved)) if resolved is not None else None
                        ),
                        "active": state.interventions.active(),
                    },
                })

            elif kind == "revert_steering":
                iv_id = int(payload.get("intervention_id", -1))
                ok = state.interventions.revert(iv_id)
                await websocket.send_json({
                    "kind": "steering_ack",
                    "payload": {
                        "reverted": iv_id if ok else None,
                        "active": state.interventions.active(),
                    },
                })

            elif kind == "clear_steering":
                n = state.interventions.clear()
                await websocket.send_json({
                    "kind": "steering_ack",
                    "payload": {"cleared": n, "active": []},
                })

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
    """Liveness, plus the two facts a green `ok` used to hide.

    `ok: true` here only means "this process is serving HTTP". It said
    nothing about whether `/ws` could actually be upgraded, and that is
    the only thing the UI needs. It could not: uvicorn ships no
    WebSocket implementation of its own, and with neither `websockets`
    nor `wsproto` installed it answers an upgrade request with a plain
    **404** — not a 501, not an error. The socket never opened and the
    page sat at "disconnected" looking like a frontend problem.

    So report the two things that actually decide whether the page can
    connect, and let a caller notice the mismatch without reading code.
    """
    ws_impl = None
    for mod in ("websockets", "wsproto"):
        try:
            __import__(mod)
            ws_impl = mod
            break
        except Exception:
            continue
    return {
        "ok": True,
        "port": WS_PORT,
        "frontend_expects": 9503,
        "port_matches_frontend": WS_PORT == 9503,
        "ws_upgrade_possible": ws_impl is not None,
        "ws_impl": ws_impl,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WS_PORT)