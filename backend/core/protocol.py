"""Frame protocol for Reasoning3D.

The wire format is JSON over WebSocket. Per generated token, the
backend pushes one Frame; the frontend may push ControlMessages
to change configuration (prompt, layer, playback rate).

Design goals:
  * Tiny surface area. Just enough to render a 3-D path and
    show the surrounding metadata.
  * Lossless: 3-D coordinates are produced by the server's
    online projector (PCA / UMAP) and shipped directly. The
    frontend doesn't re-project.
  * Optional metadata: confusion / token entropy / loss are
    optional so the synthetic runner can leave them blank.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Literal


# ---------------------------------------------------------------------------
# Outbound: server -> client frames
# ---------------------------------------------------------------------------


@dataclass
class Point3D:
    """A 3-D point in the projected (online PCA / UMAP) space."""

    x: float
    y: float
    z: float


@dataclass
class TokenInfo:
    """Metadata about the token that was just emitted."""

    token: str
    token_id: int


@dataclass
class Frame:
    """A single per-token frame."""

    # ----- Token -----
    ts: float           # unix seconds, server clock
    step_id: int        # monotonic counter for this stream
    token: str
    token_id: int

    # ----- 3-D path -----
    point: Point3D      # 3-D projection of the hidden state at the
                        # configured layer for the *current* token

    # ----- Optional scalar metrics -----
    perplexity: Optional[float] = None  # 1 / p(top-1). None if unknown.
    entropy: Optional[float] = None     # Shannon entropy (nats) of the policy
    loss: Optional[float] = None        # generic loss-like scalar

    # ----- Status flags (frontend can use to render highlights) -----
    is_self_check: bool = False  # model said "wait", "actually", "hmm"
    is_revisit: bool = False     # the path direction reversed

    # ----- Intervention telemetry -----
    # Populated only while a steering intervention is active. These are
    # what turn "we injected a vector" into something you can *read*:
    # how much the state moved, how far it moved along the steering
    # direction specifically, and how far it drifted off the
    # unperturbed path.
    steer_active: bool = False
    steer_norm: Optional[float] = None        # ||injected vector||
    steer_alignment: Optional[float] = None   # cos(h_t, v_injected), pre-add
    steer_shift: Optional[float] = None       # ||h_t - h_t^baseline|| (cosine dist)
    steer_projection: Optional[float] = None  # component of h_t along v

    def to_dict(self) -> Dict[str, Any]:
        # Every other server message is tagged with `kind` (ready,
        # steering_catalog, steering_ack, error, reset_ack). Frames were not,
        # and the frontend had to fall back to "anything unrecognised is a
        # frame". That is fragile in both directions: a client cannot tell a
        # frame from a future message type it does not know yet, and a frame
        # with a stray `kind` would be routed to the wrong handler. Tag it.
        return {"kind": "frame", **asdict(self)}


# ---------------------------------------------------------------------------
# Inbound: client -> server control messages
# ---------------------------------------------------------------------------


ControlKind = Literal[
    "start",
    "cancel",
    "pause",
    "resume",
    "set_layer",
    "set_prompt",
    "set_speed",
    "reset",
    "inject_steering",
    "revert_steering",
    "clear_steering",
]

SteeringDirection = Literal[
    "confidence_up",
    "confidence_down",
    "reasoning_deep",
    "reasoning_shallow",
    "creativity",
    "caution",
    "custom",
]


@dataclass
class ControlMessage:
    kind: ControlKind
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "payload": self.payload}


# ---------------------------------------------------------------------------
# One-shot hello message on connect
# ---------------------------------------------------------------------------


@dataclass
class ReadyMessage:
    presets: List[str]           # future use (vector injection presets)
    layer: int                   # default layer
    d_model: int                 # hidden dim (debug info)
    sample_every: int            # how often a hidden state is sent (1 = every token)
    # Layers this runner can actually replay, ascending. Declared rather than
    # left to the UI to guess: the frontend used to carry a hardcoded
    # [4,8,12,14,16,20,24,28,32], which overlaps the real [4,12,20,26] only
    # by accident -- it offered layers the data does not have and omitted one
    # it does. Empty means "runner does not say"; the UI keeps its defaults.
    layers: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "ready",
            "payload": asdict(self),
        }