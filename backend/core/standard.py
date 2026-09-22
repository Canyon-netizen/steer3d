"""Standardized on-disk format for Reasoning3D trajectories.

Goal: every run we collect (Qwen3-1.7B on AIME, in thinking mode or not,
at all layers, etc.) lands in the same shape so downstream tools can
load it without ad-hoc parsing.

A single "trajectory" is one problem's full generation, saved as a pair:

  <id>.json   — metadata: prompt, answer, mode, config, per-token scalars
  <id>.npz    — arrays: hidden states, logits, token ids, attention mask

File naming convention::

  <dataset>__<split>__<id>__<mode>.json
  <dataset>__<split>__<id>__<mode>.npz

e.g. ``aime__2024__0001__think.json`` + ``...__think.npz``.

This module provides:

  * ``TrajectorySchema``  — constants / dataclass describing the schema
  * ``save_trajectory``   — write a JSON + NPZ pair
  * ``TrajectoryDataset`` — reader/iterator over a directory of pairs
  * ``load_trajectory``   — convenience loader returning a dataclass
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np


SCHEMA_VERSION = "1.1"
# v1.1: add per-token hidden states for the chat-template prompt tokens
#   (keyed ``prompt_hidden_states``/``prompt_last_hidden``/``prompt_token_ids``
#    in the NPZ; ``n_prompt_tokens`` field promoted to TrajectoryMeta top-level).
# v1.0 (legacy): gen-only hidden states. Still readable by v1.1 loader.


# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    """How this trajectory was generated.

    Stored verbatim inside the JSON sidecar so a downstream tool can
    reconstruct the generation config without guessing.
    """
    model: str                 # e.g. "Qwen/Qwen3-1.7B"
    model_path: str            # local snapshot path
    mode: str                  # "think" | "no_think"
    max_new_tokens: int        # generation budget
    max_context: int           # context length cap (e.g. 16384)
    temperature: float         # sampling temperature (0 = greedy)
    top_p: float
    top_k: int
    seed: int
    chat_template_kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenRecord:
    """Per-token scalar metadata. (Hidden states are in NPZ.)

    For generated tokens: perplexity/entropy/top1_prob are populated,
    is_prompt=False.
    For prompt tokens (v1.1 only, the collectors currently keep the
    ``tokens`` list gen-only — the prompt block lives in the NPZ as
    ``prompt_*`` arrays with ``n_prompt_tokens`` indexing them):
    perplexity/entropy/top1_prob are None, is_prompt=True.
    """
    step_id: int
    token_id: int
    token: str                 # decoded text (may contain spaces/newlines)
    ts: float                  # unix seconds
    perplexity: Optional[float]
    entropy: Optional[float]
    top1_prob: Optional[float]
    is_self_check: bool
    is_in_think_block: bool    # inside <think>...</think>
    is_after_think: bool       # answer section
    is_prompt: bool = False    # True iff this is a chat-template prompt token


@dataclass
class TrajectoryMeta:
    """Top-level metadata for a single generation."""
    schema_version: str
    trajectory_id: str         # unique key (e.g. "aime__2024__0001__think")
    dataset: str               # "aime"
    split: str                 # "2024"
    problem_id: str            # original problem id within the split
    prompt: str                # user prompt as fed to the model
    system_prompt: Optional[str]
    chat_template_input: str   # what apply_chat_template produced
    ground_truth: str          # expected answer (raw)
    generated_text: str        # full model output (incl. <think>...</think>)
    generated_answer: str      # parsed answer (best-effort)
    is_correct: Optional[bool] # None if ground truth missing
    n_tokens: int              # == n_prompt_tokens + n_generated_tokens (i.e. total tokens the model saw)
    n_generated_tokens: int    # tokens generated (excludes prompt)
    n_layers: int              # model hidden_size dim
    d_model: int               # hidden state dim (e.g. 2048)
    config: RunConfig
    tokens: List[TokenRecord]
    n_prompt_tokens: int = 0   # v1.1: tokens of the chat-template prompt; 0 if not captured
    extra: Dict[str, Any] = field(default_factory=dict)


# NPZ arrays (per-token, in the same order as ``tokens``):
#
#   hidden_states   (T, L, D)   float32  — every generated token × every layer × hidden_dim
#   logits          (T, V)      float32  — full softmax logits (for re-analysis)
#   last_hidden     (T, D)      float32  — final-layer residual stream (alias of hidden_states[:, -1])
#   token_ids       (T,)        int32    — generated token ids
#   attention_mask  (T,)        int8     — valid mask (1 = real, 0 = pad)
#   topk_logits     (T, K)      float32  — top-K logits (smaller than full logits for quick inspection)
#   topk_indices    (T, K)      int32    — token ids of top-K logits
#
#   prompt_hidden_states  (T_p, L, D)   — v1.1, OPTIONAL: per-layer hidden state at every
#                                          chat-template prompt token (positions [0..n_prompt_tokens-1]
#                                          of the same forward pass that produced the gen block).
#   prompt_last_hidden    (T_p, D)      — v1.1, OPTIONAL: alias of prompt_hidden_states[:, -1, :].
#   prompt_token_ids       (T_p,)        — v1.1, OPTIONAL: token ids of the chat-template prompt.
#
# Where T = n_generated_tokens, T_p = n_prompt_tokens, L = n_layers, D = d_model, V = vocab_size, K = top_k.
# (The gen-only block is unchanged across schema versions; the prompt_* arrays
# are additive and absent in v1.0 files.)
#
# Precision policy:
#   We default to float32 for hidden_states and logits because downstream
#   analysis (cosine similarity, PCA, layer-wise norm, steering vectors)
#   is sensitive to float16 round-off — particularly when subtracting
#   two close activations to isolate a direction. The on-disk cost is
#   ~2× compared to float16; one trajectory is then ~0.5 GB instead of
#   ~0.25 GB. Override with ``save_trajectory(..., dtype="float16")``.
#   The same precision is used for prompt_hidden_states when captured.
#
NPZ_KEYS = ("hidden_states", "logits", "last_hidden", "token_ids",
            "attention_mask", "topk_logits", "topk_indices",
            # v1.1 (all optional; only present if --include-prompt-hidden was set):
            "prompt_hidden_states", "prompt_last_hidden", "prompt_token_ids")

PROMPT_NPZ_KEYS = ("prompt_hidden_states", "prompt_last_hidden",
                   "prompt_token_ids")


# ---------------------------------------------------------------------------
# Saver
# ---------------------------------------------------------------------------


def trajectory_filename(meta: TrajectoryMeta) -> Tuple[str, str]:
    """Return (json_path, npz_path) under the given directory."""
    tid = meta.trajectory_id
    return (f"{tid}.json", f"{tid}.npz")


def save_trajectory(out_dir: str | Path, meta: TrajectoryMeta,
                    hidden_states: np.ndarray,
                    logits: np.ndarray,
                    token_ids: np.ndarray,
                    attention_mask: np.ndarray,
                    *,
                    save_full_logits: bool = True,
                    topk: int = 64,
                    compress: bool = False,
                    dtype: str = "float32",
                    # v1.1 prompt-block (all optional). Either all three None
                    # (writes a v1.0-shape file) or all three arrays (writes
                    # the prompt_* arrays in the NPZ + n_prompt_tokens in JSON).
                    prompt_hidden_states: Optional[np.ndarray] = None,
                    prompt_last_hidden:   Optional[np.ndarray] = None,
                    prompt_token_ids:     Optional[np.ndarray] = None,
                    ) -> Tuple[Path, Path]:
    """Write a single trajectory as JSON + NPZ.

    Args:
        out_dir:         directory to write into
        meta:            TrajectoryMeta (must match array shapes)
        hidden_states:   (T, L, D)
        logits:          (T, V)
        token_ids:       (T,)     int32
        attention_mask:  (T,)     int8
        save_full_logits: if False, do not store the full V-sized logits
                          (saves ~T*V*4 bytes at float32, ~T*V*2 at float16)
        topk:            save the top-k logits for each token (always on)
        compress:        use np.savez_compressed (slow on big arrays,
                          default False for ~30x speedup)
        dtype:           "float32" (default, full precision) or "float16"
                          (half precision, ~2× smaller on disk). float32 is
                          recommended for downstream analysis.
        prompt_hidden_states: (T_p, L, D) — v1.1, optional
        prompt_last_hidden:   (T_p, D)    — v1.1, optional (defaults to
                              prompt_hidden_states[:, -1, :] if None)
        prompt_token_ids:     (T_p,) int32 — v1.1, optional

    Returns:
        (json_path, npz_path)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_name, npz_name = trajectory_filename(meta)

    if dtype not in ("float16", "float32"):
        raise ValueError(f"dtype must be 'float16' or 'float32', got {dtype!r}")
    target_dtype = np.float16 if dtype == "float16" else np.float32

    # Validate shapes
    T = meta.n_generated_tokens
    L = meta.n_layers
    D = meta.d_model
    V = logits.shape[-1]
    if hidden_states.shape != (T, L, D):
        raise ValueError(f"hidden_states must be (T={T}, L={L}, D={D}), "
                         f"got {hidden_states.shape}")
    if logits.shape != (T, V):
        raise ValueError(f"logits must be (T={T}, V={V}), got {logits.shape}")
    if token_ids.shape != (T,):
        raise ValueError(f"token_ids must be (T={T},), got {token_ids.shape}")
    if attention_mask.shape != (T,):
        raise ValueError(f"attention_mask must be (T={T},), got {attention_mask.shape}")

    # Validate prompt block (v1.1). All three None => gen-only file.
    # If prompt_hidden_states is given, then prompt_token_ids is required;
    # prompt_last_hidden is optional and defaults to prompt_hidden_states[:, -1, :].
    has_prompt_block = prompt_hidden_states is not None
    if has_prompt_block:
        if prompt_token_ids is None:
            raise ValueError(
                "prompt_hidden_states is given but prompt_token_ids is None. "
                "Either pass both, or pass neither (gen-only file)."
            )
        T_p = meta.n_prompt_tokens
        if prompt_hidden_states.shape != (T_p, L, D):
            raise ValueError(
                f"prompt_hidden_states must be (T_p={T_p}, L={L}, D={D}), "
                f"got {prompt_hidden_states.shape}"
            )
        if prompt_token_ids.shape != (T_p,):
            raise ValueError(
                f"prompt_token_ids must be (T_p={T_p},), got {prompt_token_ids.shape}"
            )
        if prompt_last_hidden is None:
            prompt_last_hidden = prompt_hidden_states[:, -1, :]
        elif prompt_last_hidden.shape != (T_p, D):
            raise ValueError(
                f"prompt_last_hidden must be (T_p={T_p}, D={D}), "
                f"got {prompt_last_hidden.shape}"
            )

    # Top-K of logits, computed once for both saves
    K = min(topk, V)
    # argpartition is faster than full sort
    topk_idx = np.argpartition(-logits, kth=K - 1, axis=-1)[..., :K]
    # Re-sort those K by descending value so consumers can read off ranks
    rows = np.arange(T)[:, None]
    topk_vals = logits[rows, topk_idx]
    order = np.argsort(-topk_vals, axis=-1)
    topk_vals = topk_vals[rows, order].astype(target_dtype, copy=False)
    topk_idx = topk_idx[rows, order].astype(np.int32, copy=False)

    # Build the npz dict
    npz_dict = dict(
        hidden_states=hidden_states.astype(target_dtype, copy=False),
        last_hidden=hidden_states[:, -1, :].astype(target_dtype, copy=False),
        token_ids=token_ids.astype(np.int32, copy=False),
        attention_mask=attention_mask.astype(np.int8, copy=False),
        topk_logits=topk_vals,
        topk_indices=topk_idx,
    )
    if save_full_logits:
        npz_dict["logits"] = logits.astype(target_dtype, copy=False)
    # v1.1 prompt block
    if has_prompt_block:
        npz_dict["prompt_hidden_states"] = prompt_hidden_states.astype(target_dtype, copy=False)
        npz_dict["prompt_last_hidden"]   = prompt_last_hidden.astype(target_dtype, copy=False)
        npz_dict["prompt_token_ids"]     = prompt_token_ids.astype(np.int32, copy=False)

    npz_path = out_dir / npz_name
    saver = np.savez_compressed if compress else np.savez
    saver(npz_path, **npz_dict)

    # JSON
    json_path = out_dir / json_name
    payload = {
        "schema_version": SCHEMA_VERSION,
        "trajectory_id": meta.trajectory_id,
        "dataset": meta.dataset,
        "split": meta.split,
        "problem_id": meta.problem_id,
        "prompt": meta.prompt,
        "system_prompt": meta.system_prompt,
        "chat_template_input": meta.chat_template_input,
        "ground_truth": meta.ground_truth,
        "generated_text": meta.generated_text,
        "generated_answer": meta.generated_answer,
        "is_correct": meta.is_correct,
        "n_prompt_tokens": meta.n_prompt_tokens,
        "n_tokens": meta.n_tokens,
        "n_generated_tokens": meta.n_generated_tokens,
        "n_layers": meta.n_layers,
        "d_model": meta.d_model,
        "config": asdict(meta.config),
        "tokens": [asdict(t) for t in meta.tokens],
        "extra": {**meta.extra, "stored_dtype": dtype},
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=_json_default)

    return json_path, npz_path


def _json_default(o):
    """Fallback encoder for non-standard types."""
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        if np.isnan(o):
            return None
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not serialisable: {type(o)}")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


@dataclass
class Trajectory:
    """In-memory representation of one trajectory."""
    meta: TrajectoryMeta
    # Arrays (default precision is float32; check ``meta.extra["stored_dtype"]``)
    hidden_states: np.ndarray           # (T, L, D) float32 (or float16 if downgraded)
    last_hidden: np.ndarray             # (T, D)   float32
    token_ids: np.ndarray               # (T,)     int32
    attention_mask: np.ndarray          # (T,)     int8
    # Optional
    logits: Optional[np.ndarray] = None      # (T, V)   float32 — may be None if not saved
    topk_logits: Optional[np.ndarray] = None # (T, K)   float32
    topk_indices: Optional[np.ndarray] = None # (T, K)   int32
    # v1.1 prompt block (None if not captured / v1.0 file)
    prompt_hidden_states: Optional[np.ndarray] = None  # (T_p, L, D)
    prompt_last_hidden:   Optional[np.ndarray] = None  # (T_p, D)
    prompt_token_ids:     Optional[np.ndarray] = None  # (T_p,) int32

    @property
    def stored_dtype(self) -> str:
        """The on-disk precision stored in ``hidden_states`` and ``logits``."""
        if self.hidden_states is None:
            return "(no data)"
        return "float16" if self.hidden_states.dtype == np.float16 else "float32"

    @property
    def is_correct(self) -> Optional[bool]:
        return self.meta.is_correct

    @property
    def mode(self) -> str:
        return self.meta.config.mode

    @property
    def has_logits(self) -> bool:
        return self.logits is not None

    @property
    def has_prompt_hidden(self) -> bool:
        """True iff v1.1 prompt hidden states were captured."""
        return self.prompt_hidden_states is not None

    @property
    def think_hidden(self) -> np.ndarray:
        """Hidden states (T_think, L, D) for tokens inside <think>."""
        mask = np.array([t.is_in_think_block for t in self.meta.tokens], dtype=bool)
        return self.hidden_states[mask]

    @property
    def answer_hidden(self) -> np.ndarray:
        """Hidden states for tokens in the answer section."""
        mask = np.array([t.is_after_think for t in self.meta.tokens], dtype=bool)
        return self.hidden_states[mask]

    @property
    def all_hidden_states(self) -> Optional[np.ndarray]:
        """(T_p + T, L, D) — concatenated prompt + gen, or None if prompt
        hidden states were not captured.

        dtype matches ``hidden_states`` (the gen block); prompt is cast
        if it was stored at a different precision.
        """
        if self.prompt_hidden_states is None:
            return None
        if self.prompt_hidden_states.dtype != self.hidden_states.dtype:
            return np.concatenate([
                self.prompt_hidden_states.astype(self.hidden_states.dtype, copy=False),
                self.hidden_states,
            ], axis=0)
        return np.concatenate([self.prompt_hidden_states, self.hidden_states], axis=0)


def load_trajectory(json_path: str | Path) -> Trajectory:
    """Load a single trajectory (JSON + NPZ).

    Backwards compatible with both v1.0 (gen-only) and v1.1 (with prompt
    block) files. The prompt arrays are simply absent on v1.0 files.
    """
    json_path = Path(json_path)
    npz_path = json_path.with_suffix(".npz")
    if not npz_path.exists():
        raise FileNotFoundError(f"missing sidecar: {npz_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    data = np.load(npz_path)
    cfg = RunConfig(**payload["config"])
    tokens = [TokenRecord(**t) for t in payload["tokens"]]
    # n_prompt_tokens: v1.1 top-level OR fallback to extra dict (legacy)
    if "n_prompt_tokens" in payload:
        n_prompt_tokens = int(payload["n_prompt_tokens"])
    else:
        n_prompt_tokens = int(payload.get("extra", {}).get("prompt_tokens", 0))
    meta = TrajectoryMeta(
        schema_version=payload["schema_version"],
        trajectory_id=payload["trajectory_id"],
        dataset=payload["dataset"],
        split=payload["split"],
        problem_id=payload["problem_id"],
        prompt=payload["prompt"],
        system_prompt=payload.get("system_prompt"),
        chat_template_input=payload.get("chat_template_input", ""),
        ground_truth=payload["ground_truth"],
        generated_text=payload["generated_text"],
        generated_answer=payload.get("generated_answer", ""),
        is_correct=payload.get("is_correct"),
        n_prompt_tokens=n_prompt_tokens,
        n_tokens=payload["n_tokens"],
        n_generated_tokens=payload["n_generated_tokens"],
        n_layers=payload["n_layers"],
        d_model=payload["d_model"],
        config=cfg,
        tokens=tokens,
        extra=payload.get("extra", {}),
    )
    return Trajectory(
        meta=meta,
        hidden_states=data["hidden_states"],
        last_hidden=data["last_hidden"],
        token_ids=data["token_ids"],
        attention_mask=data["attention_mask"],
        logits=data["logits"] if "logits" in data.files else None,
        topk_logits=data["topk_logits"] if "topk_logits" in data.files else None,
        topk_indices=data["topk_indices"] if "topk_indices" in data.files else None,
        prompt_hidden_states=(data["prompt_hidden_states"]
                              if "prompt_hidden_states" in data.files else None),
        prompt_last_hidden=(data["prompt_last_hidden"]
                            if "prompt_last_hidden" in data.files else None),
        prompt_token_ids=(data["prompt_token_ids"]
                          if "prompt_token_ids" in data.files else None),
    )


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


_FN_RE = re.compile(
    r"^(?P<dataset>[^_]+)__(?P<split>[^_]+)__(?P<pid>.+)__(?P<mode>[^/\\.]+)\.json$"
)


@dataclass
class TrajectoryFilter:
    """Selectors for ``TrajectoryDataset.iter_trajectories``."""
    mode: Optional[str] = None           # "think" / "no_think"
    dataset: Optional[str] = None
    split: Optional[str] = None
    only_correct: Optional[bool] = None  # True/False/None (no filter)
    min_tokens: int = 0
    max_tokens: Optional[int] = None

    def matches(self, traj: Trajectory) -> bool:
        if self.mode is not None and traj.mode != self.mode:
            return False
        if self.dataset is not None and traj.meta.dataset != self.dataset:
            return False
        if self.split is not None and traj.meta.split != self.split:
            return False
        if self.only_correct is not None and traj.is_correct != self.only_correct:
            return False
        if traj.meta.n_generated_tokens < self.min_tokens:
            return False
        if self.max_tokens is not None and traj.meta.n_generated_tokens > self.max_tokens:
            return False
        return True


class TrajectoryDataset:
    """A directory of trajectory pairs.

    Use::

        ds = TrajectoryDataset("/data/.../trajectories")
        for traj in ds.iter_trajectories():
            print(traj.meta.trajectory_id, traj.is_correct)

        correct = ds.filter(TrajectoryFilter(mode="think", only_correct=True))
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self._index: Dict[str, Path] = {}
        self._scan()

    def _scan(self):
        for p in self.root.glob("*.json"):
            m = _FN_RE.match(p.name)
            if not m:
                continue
            tid = m.group(0)[:-len(".json")]  # trajectory_id
            self._index[tid] = p

    # ----- Inspection --------------------------------------------------

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, tid: str) -> bool:
        return tid in self._index

    def ids(self) -> List[str]:
        return sorted(self._index.keys())

    def summary(self) -> Dict[str, Any]:
        """Aggregate stats over the dataset."""
        modes: Dict[str, int] = {}
        correct = {"yes": 0, "no": 0, "unknown": 0}
        token_counts: List[int] = []
        for tid in self.ids():
            json_path = self._index[tid]
            with open(json_path) as f:
                m = json.load(f)
            mode = m["config"]["mode"]
            modes[mode] = modes.get(mode, 0) + 1
            ic = m.get("is_correct")
            if ic is True:
                correct["yes"] += 1
            elif ic is False:
                correct["no"] += 1
            else:
                correct["unknown"] += 1
            token_counts.append(m.get("n_generated_tokens", 0))
        return {
            "n_trajectories": len(self._index),
            "by_mode": modes,
            "correctness": correct,
            "tokens_min": min(token_counts) if token_counts else 0,
            "tokens_max": max(token_counts) if token_counts else 0,
            "tokens_mean": (sum(token_counts) / len(token_counts)) if token_counts else 0,
        }

    # ----- Iteration ---------------------------------------------------

    def iter_trajectories(self, flt: Optional[TrajectoryFilter] = None,
                          lazy: bool = False) -> Iterator[Trajectory]:
        flt = flt or TrajectoryFilter()
        for tid in self.ids():
            json_path = self._index[tid]
            if lazy:
                yield self._lazy(tid, json_path, flt)
            else:
                traj = load_trajectory(json_path)
                if flt.matches(traj):
                    yield traj

    def _lazy(self, tid: str, json_path: Path, flt: TrajectoryFilter):
        # Light pre-check from JSON only, then full load
        with open(json_path) as f:
            payload = json.load(f)
        n_prompt_tokens = int(payload.get(
            "n_prompt_tokens",
            payload.get("extra", {}).get("prompt_tokens", 0),
        ))
        meta_stub = TrajectoryMeta(
            schema_version=payload["schema_version"],
            trajectory_id=tid,
            dataset=payload["dataset"],
            split=payload["split"],
            problem_id=payload["problem_id"],
            prompt=payload["prompt"],
            system_prompt=payload.get("system_prompt"),
            chat_template_input=payload.get("chat_template_input", ""),
            ground_truth=payload["ground_truth"],
            generated_text=payload["generated_text"],
            generated_answer=payload.get("generated_answer", ""),
            is_correct=payload.get("is_correct"),
            n_prompt_tokens=n_prompt_tokens,
            n_tokens=payload["n_tokens"],
            n_generated_tokens=payload["n_generated_tokens"],
            n_layers=payload["n_layers"],
            d_model=payload["d_model"],
            config=RunConfig(**payload["config"]),
            tokens=[TokenRecord(**t) for t in payload["tokens"]],
            extra=payload.get("extra", {}),
        )
        # Re-use TrajectoryFilter.matches through a stub Trajectory
        stub = Trajectory(meta=meta_stub, hidden_states=None, last_hidden=None,
                          token_ids=None, attention_mask=None)
        if not flt.matches(stub):
            return
        yield load_trajectory(json_path)

    def filter(self, flt: TrajectoryFilter) -> "TrajectoryDataset":
        """Return a NEW dataset that only contains matching trajectories."""
        sub = TrajectoryDataset.__new__(TrajectoryDataset)
        sub.root = self.root
        sub._index = {
            tid: p for tid, p in self._index.items()
            if self._match_from_json(tid, p, flt)
        }
        return sub

    def _match_from_json(self, tid: str, json_path: Path,
                         flt: TrajectoryFilter) -> bool:
        try:
            with open(json_path) as f:
                m = json.load(f)
            cfg = m["config"]
            if flt.mode is not None and cfg.get("mode") != flt.mode:
                return False
            if flt.dataset is not None and m.get("dataset") != flt.dataset:
                return False
            if flt.split is not None and m.get("split") != flt.split:
                return False
            if flt.only_correct is not None and m.get("is_correct") != flt.only_correct:
                return False
            ng = m.get("n_generated_tokens", 0)
            if ng < flt.min_tokens:
                return False
            if flt.max_tokens is not None and ng > flt.max_tokens:
                return False
            return True
        except Exception:
            return False

    def get(self, trajectory_id: str) -> Trajectory:
        if trajectory_id not in self._index:
            raise KeyError(trajectory_id)
        return load_trajectory(self._index[trajectory_id])

    # ----- Convenience collections ------------------------------------

    def by_mode(self) -> Dict[str, List[Trajectory]]:
        out: Dict[str, List[Trajectory]] = {"think": [], "no_think": []}
        for traj in self.iter_trajectories():
            if traj.mode in out:
                out[traj.mode].append(traj)
        return out

    def by_correctness(self) -> Dict[str, List[Trajectory]]:
        out: Dict[str, List[Trajectory]] = {"correct": [], "wrong": [], "unknown": []}
        for traj in self.iter_trajectories():
            if traj.is_correct is True:
                out["correct"].append(traj)
            elif traj.is_correct is False:
                out["wrong"].append(traj)
            else:
                out["unknown"].append(traj)
        return out

    def pair(self, trajectory_id_prefix: str) -> Optional[Tuple[Trajectory, Trajectory]]:
        """Return (think, no_think) trajectories for a given problem id prefix
        like ``aime__2024__2024_I_1``."""
        think = self.get(trajectory_id_prefix + "__think")
        nothink = self.get(trajectory_id_prefix + "__no_think")
        return (think, nothink)
