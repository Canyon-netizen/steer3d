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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "ready",
            "payload": asdict(self),
        }