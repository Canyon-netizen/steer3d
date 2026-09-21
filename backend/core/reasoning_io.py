"""Standardized I/O for Reasoning3D reasoning runs.

This module is the **single source of truth** for the reasoning data
contract. See `docs/REASONING_IO.md` for the full specification.

It defines:
  * `ReasoningRun` — high-level dataclass wrapping prompt + frames +
    metadata + generated text.
  * `Frame` / `Point3D` re-exported from `protocol.py` so consumers
    don't need to import two places.
  * `RUN_SCHEMA` — machine-checkable JSON Schema (format_version 1.0).
  * `read_run` / `write_run` — sync file I/O.
  * `stream_run_ws` — async WebSocket consumer.
  * `validate_run` — JSON Schema validator.
  * `RunBuilder` — incremental accumulator for streaming sources.

Why this exists:
  The previous `view_terrain.html` baked reasoning frames into a
  static HTML file, which violated the principle that reasoning data
  should always be either live-streamed or written to standard JSON.
  This module makes the JSON contract explicit and gives consumers
  (browser, Python scripts, notebooks) a clean uniform interface.
"""

from __future__ import annotations

import json
import uuid
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Iterator, List, Optional, Union

# Robust import: works both as `core.reasoning_io` (relative) and as
# a top-level module loaded by tests via importlib (no parent package).
try:
    from .protocol import Frame, Point3D, ControlMessage
except ImportError:
    from protocol import Frame, Point3D, ControlMessage  # type: ignore


# ---------------------------------------------------------------------------
# Re-exports for convenience
# ---------------------------------------------------------------------------

__all__ = [
    "Frame",
    "Point3D",
    "ReasoningRun",
    "RunBuilder",
    "RUN_SCHEMA",
    "FORMAT_VERSION",
    "read_run",
    "write_run",
    "stream_run_ws",
    "validate_run",
    "iter_run",
]


FORMAT_VERSION = "1.0"


# ---------------------------------------------------------------------------
# JSON Schema (format_version 1.0)
# ---------------------------------------------------------------------------

RUN_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ReasoningRun",
    "type": "object",
    "required": [
        "format_version", "run_id", "model", "layer", "prompt",
        "started_at", "metadata", "frames",
    ],
    "additionalProperties": False,
    "properties": {
        "format_version": {"type": "string", "pattern": r"^\d+\.\d+$"},
        "run_id": {"type": "string", "minLength": 1},
        "model": {"type": "string", "minLength": 1},
        "layer": {"type": "integer", "minimum": 0},
        "prompt": {"type": "string"},
        "started_at": {"type": "number"},
        "finished_at": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "metadata": {"type": "object"},
        "generated_text": {"type": "string"},
        "frames": {
            "type": "array",
            "items": {"$ref": "#/definitions/frame"},
        },
    },
    "definitions": {
        "frame": {
            "type": "object",
            "required": [
                "ts", "step_id", "token", "token_id", "point",
            ],
            "additionalProperties": False,
            "properties": {
                "ts":             {"type": "number"},
                "step_id":        {"type": "integer", "minimum": 0},
                "token":          {"type": "string"},
                "token_id":       {"type": "integer"},
                "point":          {"$ref": "#/definitions/point3d"},
                "perplexity":     {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "entropy":        {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "loss":           {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "is_self_check":  {"type": "boolean"},
                "is_revisit":     {"type": "boolean"},
            },
        },
        "point3d": {
            "type": "object",
            "required": ["x", "y", "z"],
            "additionalProperties": False,
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
        },
    },
}


def validate_run(data: Any) -> None:
    """Validate that `data` matches RUN_SCHEMA. Raises ValueError if not.

    Uses a tiny built-in checker (no jsonschema dep). If you have
    jsonschema installed, prefer the strict version via
    `validate_run_strict`.
    """
    if not isinstance(data, dict):
        raise ValueError(f"ReasoningRun must be a dict, got {type(data).__name__}")

    # Required fields
    missing = set(RUN_SCHEMA["required"]) - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    # Additional properties at top level
    allowed_top = set(RUN_SCHEMA["properties"].keys())
    extra = set(data.keys()) - allowed_top
    if extra:
        raise ValueError(f"Unknown top-level fields: {sorted(extra)}")

    # Type checks
    fv = data["format_version"]
    if not isinstance(fv, str) or not _SEMVER_RE.match(fv):
        raise ValueError(f"format_version must match X.Y.Z, got {fv!r}")
    if not isinstance(data["model"], str) or not data["model"]:
        raise ValueError("model must be a non-empty string")
    if not isinstance(data["layer"], int) or data["layer"] < 0:
        raise ValueError(f"layer must be a non-negative int, got {data['layer']!r}")
    if not isinstance(data["prompt"], str):
        raise ValueError("prompt must be a string")
    if not isinstance(data["started_at"], (int, float)):
        raise ValueError("started_at must be a number")
    if not isinstance(data["metadata"], dict):
        raise ValueError("metadata must be an object")

    finished_at = data.get("finished_at")
    if finished_at is not None and not isinstance(finished_at, (int, float)):
        raise ValueError("finished_at must be a number or null")

    # frames
    frames = data["frames"]
    if not isinstance(frames, list):
        raise ValueError("frames must be an array")
    prev_step = -1
    for i, fr in enumerate(frames):
        _validate_frame(fr, i)
        if fr["step_id"] <= prev_step:
            raise ValueError(
                f"frames must be sorted by step_id ascending; "
                f"got {fr['step_id']} after {prev_step} at index {i}"
            )
        prev_step = fr["step_id"]


import re  # noqa: E402
_SEMVER_RE = re.compile(r"^\d+\.\d+$")


def _validate_frame(fr: Any, idx: int) -> None:
    if not isinstance(fr, dict):
        raise ValueError(f"frame[{idx}] must be a dict")
    missing = {"ts", "step_id", "token", "token_id", "point"} - set(fr.keys())
    if missing:
        raise ValueError(f"frame[{idx}] missing fields: {sorted(missing)}")
    if not isinstance(fr["ts"], (int, float)):
        raise ValueError(f"frame[{idx}].ts must be a number")
    if not isinstance(fr["step_id"], int) or fr["step_id"] < 0:
        raise ValueError(f"frame[{idx}].step_id must be a non-negative int")
    if not isinstance(fr["token"], str):
        raise ValueError(f"frame[{idx}].token must be a string")
    if not isinstance(fr["token_id"], int):
        raise ValueError(f"frame[{idx}].token_id must be an int")
    pt = fr["point"]
    if not isinstance(pt, dict) or not all(k in pt for k in ("x", "y", "z")):
        raise ValueError(f"frame[{idx}].point must be {{x,y,z}} dict")
    for c in ("x", "y", "z"):
        if not isinstance(pt[c], (int, float)):
            raise ValueError(f"frame[{idx}].point.{c} must be a number")
    for opt in ("perplexity", "entropy", "loss"):
        if opt in fr and fr[opt] is not None and not isinstance(fr[opt], (int, float)):
            raise ValueError(f"frame[{idx}].{opt} must be a number or null")
    for opt in ("is_self_check", "is_revisit"):
        if opt in fr and not isinstance(fr[opt], bool):
            raise ValueError(f"frame[{idx}].{opt} must be a boolean")


# ---------------------------------------------------------------------------
# ReasoningRun — the high-level container
# ---------------------------------------------------------------------------


@dataclass
class ReasoningRun:
    """A complete reasoning run: prompt + ordered frames + metadata."""

    run_id: str
    model: str
    layer: int
    prompt: str
    started_at: float
    frames: List[Frame]
    metadata: Dict[str, Any] = field(default_factory=dict)
    format_version: str = FORMAT_VERSION
    finished_at: Optional[float] = None
    generated_text: Optional[str] = None

    # ----- Computed properties ----------------------------------------------

    @property
    def n_tokens(self) -> int:
        return len(self.frames)

    @property
    def generated_text_auto(self) -> str:
        """Concatenate tokens. Use this if generated_text wasn't set."""
        if self.generated_text is not None:
            return self.generated_text
        return "".join(f.token for f in self.frames)

    @property
    def duration_s(self) -> Optional[float]:
        if self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    # ----- Frame iteration ---------------------------------------------------

    def iter_frames(self) -> Iterator[Frame]:
        """Yield frames in order."""
        return iter(self.frames)

    # ----- Serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format_version": self.format_version,
            "run_id": self.run_id,
            "model": self.model,
            "layer": self.layer,
            "prompt": self.prompt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": dict(self.metadata),
            "generated_text": self.generated_text if self.generated_text is not None
                                else self.generated_text_auto,
            "frames": [_frame_to_dict(f) for f in self.frames],
        }

    def to_json(self, *, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReasoningRun":
        validate_run(d)
        frames = [_frame_from_dict(f) for f in d["frames"]]
        return cls(
            format_version=d.get("format_version", FORMAT_VERSION),
            run_id=d["run_id"],
            model=d["model"],
            layer=d["layer"],
            prompt=d["prompt"],
            started_at=d["started_at"],
            finished_at=d.get("finished_at"),
            metadata=dict(d.get("metadata", {})),
            generated_text=d.get("generated_text"),
            frames=frames,
        )

    @classmethod
    def from_json(cls, s: str) -> "ReasoningRun":
        return cls.from_dict(json.loads(s))

    # ----- File I/O ----------------------------------------------------------

    def save(self, path: Union[str, Path], *, indent: Optional[int] = 2) -> None:
        """Save run as JSON to file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(indent=indent), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ReasoningRun":
        """Load run from JSON file."""
        text = Path(path).read_text(encoding="utf-8")
        return cls.from_json(text)


# ---------------------------------------------------------------------------
# Frame ↔ dict helpers
# ---------------------------------------------------------------------------


def _frame_to_dict(f: Frame) -> Dict[str, Any]:
    return {
        "ts": f.ts,
        "step_id": f.step_id,
        "token": f.token,
        "token_id": f.token_id,
        "point": {"x": f.point.x, "y": f.point.y, "z": f.point.z},
        "perplexity": f.perplexity,
        "entropy": f.entropy,
        "loss": f.loss,
        "is_self_check": f.is_self_check,
        "is_revisit": f.is_revisit,
    }


def _frame_from_dict(d: Dict[str, Any]) -> Frame:
    return Frame(
        ts=float(d["ts"]),
        step_id=int(d["step_id"]),
        token=d["token"],
        token_id=int(d["token_id"]),
        point=Point3D(
            x=float(d["point"]["x"]),
            y=float(d["point"]["y"]),
            z=float(d["point"]["z"]),
        ),
        perplexity=(float(d["perplexity"]) if d.get("perplexity") is not None else None),
        entropy=(float(d["entropy"]) if d.get("entropy") is not None else None),
        loss=(float(d["loss"]) if d.get("loss") is not None else None),
        is_self_check=bool(d.get("is_self_check", False)),
        is_revisit=bool(d.get("is_revisit", False)),
    )


# ---------------------------------------------------------------------------
# Convenience: read / write / iterate
# ---------------------------------------------------------------------------


def read_run(source: Union[str, Path, bytes, bytearray, Dict[str, Any]]) -> ReasoningRun:
    """Read a ReasoningRun from any of:
      * file path (str or Path) — JSON file
      * raw bytes / str — JSON content (auto-detected by leading '{' or '[')
      * dict — already parsed
    """
    if isinstance(source, dict):
        return ReasoningRun.from_dict(source)
    if isinstance(source, (bytes, bytearray)):
        return ReasoningRun.from_json(source.decode("utf-8"))
    if isinstance(source, (str, Path)):
        s = str(source)
        # Heuristic: JSON content starts with { or [; otherwise treat as path
        stripped = s.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return ReasoningRun.from_json(s)
        return ReasoningRun.load(Path(s))
    raise TypeError(f"Unsupported source type: {type(source).__name__}")


def write_run(run: ReasoningRun, path: Union[str, Path], *, indent: Optional[int] = 2) -> None:
    """Write a ReasoningRun to a JSON file."""
    run.save(path, indent=indent)


def iter_run(source: Union[str, Path, ReasoningRun, Dict[str, Any]]) -> Iterator[Frame]:
    """Iterate frames from any source (file / dict / run)."""
    if isinstance(source, ReasoningRun):
        return source.iter_frames()
    run = read_run(source)
    return run.iter_frames()


# ---------------------------------------------------------------------------
# RunBuilder — accumulate frames into a Run as they stream in
# ---------------------------------------------------------------------------


@dataclass
class RunBuilder:
    """Incremental accumulator for a streaming reasoning run.

    Use when frames arrive one at a time (WebSocket, async iterator).
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model: str = ""
    layer: int = 0
    prompt: str = ""
    started_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    _frames: List[Frame] = field(default_factory=list)
    _finished_at: Optional[float] = None

    def push_frame(self, frame: Frame) -> None:
        """Append one frame. Validates step_id ordering."""
        if self._frames and frame.step_id <= self._frames[-1].step_id:
            raise ValueError(
                f"Frame step_id must be strictly increasing: "
                f"got {frame.step_id} after {self._frames[-1].step_id}"
            )
        self._frames.append(frame)

    def finish(self, *, finished_at: Optional[float] = None) -> ReasoningRun:
        """Materialize the accumulated frames into a ReasoningRun."""
        ts = finished_at if finished_at is not None else time.time()
        return ReasoningRun(
            run_id=self.run_id,
            model=self.model,
            layer=self.layer,
            prompt=self.prompt,
            started_at=self.started_at,
            finished_at=ts,
            metadata=dict(self.metadata),
            frames=list(self._frames),
            generated_text="".join(f.token for f in self._frames),
        )

    @property
    def n_frames(self) -> int:
        return len(self._frames)


# ---------------------------------------------------------------------------
# WebSocket streaming consumer
# ---------------------------------------------------------------------------


async def stream_run_ws(
    ws,
    *,
    on_frame: Optional[Callable[[Frame], None]] = None,
    model: str = "",
    layer: int = 0,
    prompt: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    timeout_s: float = 600.0,
) -> ReasoningRun:
    """Consume Frames from a WebSocket and return a finished ReasoningRun.

    Wire protocol assumptions (from server.py):
      * On connect, server may send `{kind:"ready", payload:{...}}`.
        We extract `layer` and `d_model` from it if available.
      * Per token, server sends a Frame dict directly. Some servers
        wrap it as `{kind:"frame", payload: {...}}` — we accept both.
      * Run ends on either:
          - WebSocket close
          - `{kind:"end", payload: {...}}` message
          - `{kind:"error", payload: {...}}` message

    Args:
      ws: any object with `recv()` returning awaitable[bytes/str].
          Compatible with `websockets` library client connections.
      on_frame: optional callback invoked for each frame as it arrives.
      timeout_s: max total time to wait before raising.

    Returns:
      ReasoningRun with finished_at set.
    """
    import asyncio as _asyncio

    builder = RunBuilder(
        model=model, layer=layer, prompt=prompt,
        metadata=dict(metadata or {}),
    )

    deadline = time.time() + timeout_s

    async def _recv_text():
        # websockets >=10 uses .recv(); older returns coroutines directly
        msg = await _asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
        if isinstance(msg, bytes):
            return msg.decode("utf-8")
        return msg

    while True:
        if time.time() > deadline:
            raise TimeoutError(f"stream_run_ws: timeout after {timeout_s}s")
        try:
            raw = await _recv_text()
        except (_asyncio.TimeoutError, TimeoutError) as e:
            raise TimeoutError(f"stream_run_ws: idle timeout") from e
        # websockets raises ConnectionClosed when peer closes
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        kind = msg.get("kind")
        payload = msg.get("payload", msg)

        if kind == "ready":
            # Update defaults if server provided them
            if "layer" in payload and not builder.layer:
                builder.layer = int(payload["layer"])
            if "model" in payload and not builder.model:
                builder.model = str(payload["model"])
            continue

        if kind in ("end", "run_end", "finish"):
            return builder.finish(finished_at=payload.get("time"))

        if kind == "error":
            raise RuntimeError(f"server sent error: {payload}")

        # Heuristic: it looks like a frame?
        if (
            isinstance(payload, dict)
            and "point" in payload
            and "token" in payload
            and "step_id" in payload
        ):
            frame = _frame_from_dict(payload)
            builder.push_frame(frame)
            if on_frame is not None:
                on_frame(frame)
            continue

        # Unknown message — silently ignore (forward-compat)
        continue


# ---------------------------------------------------------------------------
# Async iterator helper (matches the live_terrain.html expectations)
# ---------------------------------------------------------------------------


async def aiter_run_ws(
    ws,
    *,
    on_frame: Optional[Callable[[Frame], None]] = None,
    **kwargs,
) -> AsyncIterator[Frame]:
    """Async iterator that yields frames until the run ends.

    Useful for streaming consumers that want frame-by-frame processing
    rather than a complete Run object.
    """
    import asyncio as _asyncio

    timeout_s = kwargs.get("timeout_s", 600.0)
    deadline = time.time() + timeout_s

    while True:
        if time.time() > deadline:
            raise TimeoutError(f"aiter_run_ws: timeout after {timeout_s}s")
        try:
            raw = await _asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
        except _asyncio.TimeoutError:
            continue
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        kind = msg.get("kind")
        payload = msg.get("payload", msg)
        if kind in ("end", "run_end", "finish"):
            return
        if kind == "error":
            raise RuntimeError(f"server error: {payload}")
        if (
            isinstance(payload, dict)
            and "point" in payload
            and "token" in payload
            and "step_id" in payload
        ):
            frame = _frame_from_dict(payload)
            if on_frame:
                on_frame(frame)
            yield frame