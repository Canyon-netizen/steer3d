"""Public API for the Reasoning3D backend core package.

The framework exposes the smallest possible surface so the
frontend can stay decoupled from the model implementation:

  * `Frame`, `Point3D`, `ReadyMessage` — wire format
  * `OnlinePCA` / `SketchUMAP` — drop-in projector
  * `install_residual_add_hook` — vector injection seam (you wire
    in your own logic here)
  * `SyntheticRunner` / `HFTransformerRunner` / `default_runner`
"""

from .protocol import (
    Frame,
    Point3D,
    TokenInfo,
    ControlMessage,
    ControlKind,
    ReadyMessage,
)
from .projector import OnlinePCA, SketchUMAP
from .activation import (
    install_residual_add_hook,
    get_residual_at_last_token,
    remove_hook,
)
from .model_runner import (
    BaseModelRunner,
    SyntheticRunner,
    HFTransformerRunner,
    default_runner,
    qwen3_1p7b_runner,
    looks_like_self_check,
)
from .standard import (
    SCHEMA_VERSION,
    RunConfig,
    TokenRecord,
    TrajectoryMeta,
    Trajectory,
    TrajectoryFilter,
    TrajectoryDataset,
    save_trajectory,
    load_trajectory,
)
from .aime_loader import (
    load_aime,
    load_aime_from_jsonl,
    parse_aime_answer,
    check_correct,
)

__all__ = [
    # protocol
    "Frame",
    "Point3D",
    "TokenInfo",
    "ControlMessage",
    "ControlKind",
    "ReadyMessage",
    # projector
    "OnlinePCA",
    "SketchUMAP",
    # activation / hook helpers
    "install_residual_add_hook",
    "get_residual_at_last_token",
    "remove_hook",
    # model runner
    "BaseModelRunner",
    "SyntheticRunner",
    "HFTransformerRunner",
    "default_runner",
    "qwen3_1p7b_runner",
    "looks_like_self_check",
    # standardised trajectory format
    "SCHEMA_VERSION",
    "RunConfig",
    "TokenRecord",
    "TrajectoryMeta",
    "Trajectory",
    "TrajectoryFilter",
    "TrajectoryDataset",
    "save_trajectory",
    "load_trajectory",
    # AIME loader
    "load_aime",
    "load_aime_from_jsonl",
    "parse_aime_answer",
    "check_correct",
]