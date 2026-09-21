"""Model runner for Reasoning3D.

Two implementations are provided:

  * `SyntheticRunner`  — deterministic, GPU-free. Produces a
    believable CoT-shaped 3-D trajectory so the visualization can
    be developed and demoed on any laptop.

  * `HFTransformerRunner` — real HuggingFace causal LM. Wires
    PyTorch hooks to capture residual-stream activations and
    (optionally) inject user-supplied vectors at a chosen layer.

The user's vector injection logic lives entirely in
`HFTransformerRunner.stream()` — `install_residual_add_hook`
already exposes a clean hook point.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

from .protocol import Frame, Point3D


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Heuristic phrases that often appear in CoT "self-check" steps.
_SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|let me reconsider|on second thought|"
    r"let me check|let me think again|double[- ]check)\b",
    re.IGNORECASE,
)


def looks_like_self_check(token: str) -> bool:
    return bool(_SELF_CHECK_RE.search(token or ""))


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseModelRunner:
    """Generates streaming Frames for a given prompt."""

    d_model: int

    def reset(self) -> None:
        raise NotImplementedError

    async def stream(
        self,
        prompt: str,
        layer: int,
        on_frame: Callable[[Frame], None],
        is_paused: Callable[[], bool],
        is_cancelled: Callable[[], bool],
        set_speed: Callable[[], float],
        inject_vector: Optional[Callable[[int, str], Optional[np.ndarray]]] = None,
    ) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Synthetic runner — no GPU needed
# ---------------------------------------------------------------------------


@dataclass
class _SyntheticState:
    step: int = 0
    token_idx: int = 0


class SyntheticRunner(BaseModelRunner):
    """Generates a CoT-shaped trajectory using synthetic activations.

    Trajectory design:
      * Slow drift in 3-D (Z axis encodes 'reasoning depth')
      * Periodic 'self-check' moment (step % 17) where the path
        briefly reverses and the renderer can flag is_self_check.
      * Different prompts yield different path shapes via the
        prompt-hash seed.
    """

    # Toy vocabulary — looks like real CoT for the demo
    VOCAB = [
        "When", "we", "think", "about", "language", "models", "we", "often",
        "imagine", "them", "as", "black", "boxes", ".", "However", ",",
        "inside", "there", "is", "structure", "—", "geometry", "that",
        "responds", "to", "interventions", ".", "Specifically", ",",
        "the", "residual", "stream", "encodes", "semantic", "information",
        "that", "we", "can", "extract", "and", "visualize", ".", "Each",
        "token", "corresponds", "to", "a", "point", "in", "this", "high",
        "-", "dimensional", "space", ".",
    ]

    SELF_CHECK_TOKENS = {"Wait", "Actually", "Hmm"}

    def __init__(self, d_model: int = 4096):
        self.d_model = d_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        pass

    async def stream(
        self,
        prompt: str,
        layer: int,
        on_frame: Callable[[Frame], None],
        is_paused: Callable[[], bool],
        is_cancelled: Callable[[], bool],
        set_speed: Callable[[], float],
        inject_vector: Optional[Callable[[int, str], Optional[np.ndarray]]] = None,
    ) -> None:
        state = _SyntheticState()
        prompt_h = abs(hash(prompt)) % (2**31)
        # Build a deterministic base direction per prompt so different
        # prompts feel visually different.
        base_angle = (prompt_h % 360) * math.pi / 180
        base_dir_x = math.cos(base_angle)
        base_dir_y = math.sin(base_angle)

        n_tokens = 60  # synthetic generation length

        prev_xyz = np.zeros(3)
        # Track the path's instantaneous direction so we know when it
        # 'revisits' (reverses) — that triggers is_revisit=True.
        last_delta = np.zeros(3)

        while state.token_idx < n_tokens:
            if is_cancelled():
                return

            # Honor pause
            while is_paused() and not is_cancelled():
                await asyncio.sleep(0.05)

            # Speed control
            speed = max(0.05, min(8.0, set_speed()))
            # 50 ms per step at 1x; scale by 1/speed.
            await asyncio.sleep(0.05 / speed)

            i = state.token_idx
            tok = self.VOCAB[i % len(self.VOCAB)]
            tok_id = i  # fake

            # Build a 3-D 'activation'. Real Z grows with depth (model
            # 'going deeper into reasoning'); XY wander.
            t = state.token_idx
            z = 0.18 * t + 0.5 * math.sin(t * 0.4)
            x = 0.6 * math.cos(t * 0.25 + base_angle) + 0.1 * math.sin(t * 0.7)
            y = 0.6 * math.sin(t * 0.25 + base_angle) + 0.1 * math.cos(t * 0.7)
            xyz = np.array([x, y, z])

            delta = xyz - prev_xyz
            reversed_now = (
                np.linalg.norm(last_delta) > 0.01
                and np.linalg.norm(delta) > 0.01
                and float(np.dot(delta, last_delta)) < 0
            )
            last_delta = delta
            prev_xyz = xyz

            # Inject-vector hook (no-op for synthetic unless provided)
            injected = None
            if inject_vector is not None:
                injected = inject_vector(i, tok)
                if injected is not None:
                    xyz = xyz + injected  # nudge in 3-D directly

            # Top token probability + entropy (synthetic, but plausible)
            top1_prob = max(0.05, 0.7 - 0.005 * (i % 15))
            entropy = 1.5 + 0.3 * math.sin(t * 0.5)
            perplexity = 1.0 / top1_prob

            is_self_check = tok in self.SELF_CHECK_TOKENS or looks_like_self_check(tok)

            frame = Frame(
                ts=time.time(),
                step_id=i,
                token=tok,
                token_id=tok_id,
                point=Point3D(x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2])),
                perplexity=perplexity,
                entropy=entropy,
                loss=None,
                is_self_check=is_self_check,
                is_revisit=bool(reversed_now),
            )
            on_frame(frame)
            state.token_idx += 1


# ---------------------------------------------------------------------------
# Real-model runner — HF transformers + nnsight-friendly hooks
# ---------------------------------------------------------------------------


class HFTransformerRunner(BaseModelRunner):
    """Streams hidden states from a HuggingFace causal LM.

    Wire-up for the user's vector injection logic:
        The `stream()` method calls `inject_vector(step_id, token)`
        before each generation step. Whatever the callback returns is
        added to the residual stream at `layer` via
        `install_residual_add_hook`. Returning None = no injection.

    Note: this class is a TODO scaffold. The skeleton shows exactly
    where to plug in streaming + hook install + capture + cleanup.
    The synthetic demo shows the full visualization; once this is
    filled in, the frontend works unchanged.
    """

    def __init__(
        self,
        model_name: str = "meta-llama/Llama-3.1-8B-Instruct",
        torch_dtype=None,
    ):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if torch_dtype is None:
            torch_dtype = torch.bfloat16
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=torch_dtype, device_map="auto"
        )
        self.model.eval()
        self.d_model = self.model.config.hidden_size
        self._handles: list = []

    # ------------------------------------------------------------------
    # Hook helpers (also imported by activation.py)
    # ------------------------------------------------------------------

    def _install_add_hook(self, layer_idx: int, vector: np.ndarray):
        import torch

        block = self.model.model.layers[layer_idx]
        v = torch.as_tensor(vector, dtype=next(block.parameters()).dtype).to(
            next(block.parameters()).device
        )

        def hook(module, inputs):
            x = inputs[0]
            return (x + v,) + inputs[1:]

        h = block.register_forward_pre_hook(hook)
        self._handles.append(h)
        return h

    def _remove_all_hooks(self):
        for h in self._handles:
            h.remove()
        self._handles = []

    def _capture_residual(self, layer_idx: int, tokens) -> np.ndarray:
        """Run a forward pass and grab the residual stream at
        layer `layer_idx` for the last token position.
        """
        import torch

        captured: list = []

        def hook(module, inputs, outputs):
            h = outputs[0] if not isinstance(outputs, tuple) else outputs[0]
            captured.append(h[:, -1, :].detach().cpu().numpy())

        handle = self.model.model.layers[layer_idx].register_forward_hook(hook)
        try:
            with torch.no_grad():
                self.model(**tokens)
        finally:
            handle.remove()
        return captured[0][0]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._remove_all_hooks()

    async def stream(
        self,
        prompt: str,
        layer: int,
        on_frame: Callable[[Frame], None],
        is_paused: Callable[[], bool],
        is_cancelled: Callable[[], bool],
        set_speed: Callable[[], float],
        inject_vector: Optional[Callable[[int, str], Optional[np.ndarray]]] = None,
    ) -> None:
        """Stream tokens + hidden states from the real model.

        For each generated token:
          1. (Optional) call inject_vector(step_id, token) -> vec.
          2. If vec is provided, install_residual_add_hook(layer, vec).
          3. Generate ONE more token (use a custom LogitsProcessor
             or TextStreamer with HF's generate()).
          4. _capture_residual(layer, current_tokens) -> h.
          5. Remove hooks.
          6. Compute perplexity/entropy from logits.
          7. Emit Frame(point=projector.update(h), ...).

        The implementation of step 3 (streaming single-token
        generation while honoring pause/cancel/speed) is the bulk
        of the work; once you wire it up, the rest follows the
        shape of SyntheticRunner.stream().
        """
        raise NotImplementedError(
            "HFTransformerRunner.stream() is a scaffold — fill in the "
            "single-token streaming loop. See the docstring above."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def default_runner() -> BaseModelRunner:
    return SyntheticRunner()