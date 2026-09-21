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
          3. Generate ONE more token.
          4. Capture residual stream at `layer` for the new last token.
          5. Remove hooks.
          6. Compute perplexity/entropy from logits.
          7. Emit Frame.

        Implementation: a manual token-by-token loop using KV cache
        (past_key_values) and a forward hook attached to the chosen
        transformer block to capture its output residual stream.
        """
        import torch

        # Clamp layer to valid range
        n_layers = self.model.config.num_hidden_layers
        layer = max(0, min(n_layers - 1, int(layer)))

        # --- Tokenize prompt ---
        if not prompt.strip():
            prompt = " "
        enc = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=True)
        input_ids = enc.input_ids.to(self.model.device)
        attn_mask = enc.attention_mask.to(self.model.device)

        # Capture buffer for residual at chosen layer; this list is
        # written by a forward-hook installed at the start of each step
        # and read after the step's forward returns.
        captured: list = []

        def _capture_hook(module, inputs, outputs):
            h = outputs[0] if not isinstance(outputs, tuple) else outputs[0]
            # Qwen3 decoder layers can return either (B, T, D) or (T, D) tensors
            # depending on whether past_key_values is involved.
            if h.dim() == 3:
                last = h[:, -1, :]
            elif h.dim() == 2:
                last = h[-1:, :]  # keep leading dim for consistency
            else:
                return  # unknown shape, skip
            captured.append(last.detach().to(torch.float32).cpu().numpy())

        target_block = self.model.model.layers[layer]

        def _install_capture_hook():
            captured.clear()
            return target_block.register_forward_hook(_capture_hook)

        def _add_hook(vector: np.ndarray):
            v = torch.as_tensor(
                vector, dtype=next(target_block.parameters()).dtype
            ).to(next(target_block.parameters()).device)
            if v.dim() == 1:
                v = v.view(1, 1, -1)

            def hook(module, inputs):
                x = inputs[0]
                return (x + v,) + inputs[1:]

            return target_block.register_forward_pre_hook(hook)

        # --- Initial forward to prime KV cache + logits for first token ---
        with torch.no_grad():
            out = self.model(
                input_ids=input_ids,
                attention_mask=attn_mask,
                use_cache=True,
                output_hidden_states=False,
                return_dict=True,
            )
        past_kv = out.past_key_values
        next_logits = out.logits[:, -1, :].float()  # (1, V)

        # --- Initial hidden state: forward through the chosen layer
        # one more time with the same input to capture residual at
        # the last prompt token. We use a tiny forward that runs only
        # up through the target layer.
        # Simpler alternative: re-use the same forward with the hook
        # installed. We discard the duplicate logits/KV.
        h_handle = _install_capture_hook()
        try:
            with torch.no_grad():
                _ = self.model(
                    input_ids=input_ids,
                    attention_mask=attn_mask,
                    use_cache=True,
                    output_hidden_states=False,
                    return_dict=True,
                )
        finally:
            h_handle.remove()
        first_hidden = captured[0][0]  # (d_model,)

        # The framework expects the *projected* 3-D point. The
        # SyntheticRunner ships 3-D directly, so for the HF runner
        # we ship the raw residual and let the server's projector
        # handle reduction. Concretely: emit Frame(point=(0,0,0))
        # and stash the hidden state for the projector to read.
        # To keep the protocol identical, we instead build a
        # *raw hidden state* carrier: replace the projector via the
        # _wrap_projector hook in server.py.

        # First-frame special handling: emit hidden state for the
        # last prompt token so the path starts at a meaningful point.
        first_top1 = float(torch.softmax(next_logits[0], dim=-1).max())
        first_entropy = float(
            -(torch.softmax(next_logits[0], dim=-1)
              * torch.log_softmax(next_logits[0], dim=-1)).sum()
        )
        first_token_id = int(torch.argmax(next_logits[0], dim=-1))
        first_token_text = self.tokenizer.decode([first_token_id])

        # Carry the raw hidden vector so the server-side wrapper can
        # project it. We use a small dataclass trick: attach a
        # dynamic attribute on the Frame that the projector wrapper
        # looks for. (See protocol.py for the field name.)
        from .protocol import Frame, Point3D
        import time as _time

        first_frame = Frame(
            ts=_time.time(),
            step_id=-1,
            token="",
            token_id=-1,
            point=Point3D(0.0, 0.0, 0.0),
            perplexity=1.0 / max(first_top1, 1e-6),
            entropy=first_entropy,
            is_self_check=False,
            is_revisit=False,
        )
        # Stash the raw hidden vector for the projector to pick up.
        first_frame._raw_hidden = first_hidden  # type: ignore[attr-defined]
        on_frame(first_frame)

        # --- Greedy decode loop, one token per iteration ---
        cur_input_ids = input_ids
        cur_attn_mask = attn_mask
        generated_ids = [first_token_id]
        step_id = 0
        prev_xyz = np.zeros(3)  # used for is_revisit (set by server)
        last_xyz = np.zeros(3)

        max_new_tokens = 256

        while step_id < max_new_tokens:
            if is_cancelled():
                return

            # Honor pause
            while is_paused() and not is_cancelled():
                await asyncio.sleep(0.05)

            if is_cancelled():
                return

            # Speed control — same as SyntheticRunner (50ms / speed).
            speed = max(0.05, min(8.0, set_speed()))
            await asyncio.sleep(0.05 / speed)

            # --- Vector injection (optional) ---
            tok_text = self.tokenizer.decode([first_token_id] if step_id == 0 else [next_id])
            inject_handle = None
            if inject_vector is not None:
                v = inject_vector(step_id, tok_text)
                if v is not None:
                    inject_handle = _add_hook(v)

            # --- Forward ONE token with KV cache, capture hidden ---
            next_input = torch.tensor([[first_token_id]], device=self.model.device) \
                if step_id == 0 else torch.tensor([[next_id]], device=self.model.device)
            cur_attn_mask = torch.cat(
                [cur_attn_mask, torch.ones((1, 1), device=self.model.device, dtype=cur_attn_mask.dtype)],
                dim=1,
            )

            h_handle = _install_capture_hook()
            try:
                with torch.no_grad():
                    out = self.model(
                        input_ids=next_input,
                        attention_mask=cur_attn_mask,
                        past_key_values=past_kv,
                        use_cache=True,
                        output_hidden_states=False,
                        return_dict=True,
                    )
            finally:
                h_handle.remove()
                if inject_handle is not None:
                    inject_handle.remove()

            past_kv = out.past_key_values
            next_logits = out.logits[:, -1, :].float()
            next_id = int(torch.argmax(next_logits[0], dim=-1))

            # EOS check
            if next_id == self.tokenizer.eos_token_id:
                break

            # Per-token metrics
            probs = torch.softmax(next_logits[0], dim=-1)
            top1 = float(probs.max())
            entropy = float(-(probs * torch.log(probs + 1e-12)).sum())

            h_vec = captured[0][0]

            # Emit frame
            frame = Frame(
                ts=_time.time(),
                step_id=step_id,
                token=tok_text,
                token_id=first_token_id if step_id == 0 else next_id,
                point=Point3D(0.0, 0.0, 0.0),  # server's projector fills in
                perplexity=1.0 / max(top1, 1e-6),
                entropy=entropy,
                is_self_check=looks_like_self_check(tok_text),
                is_revisit=False,
            )
            frame._raw_hidden = h_vec  # type: ignore[attr-defined]
            on_frame(frame)

            generated_ids.append(next_id)
            step_id += 1

        # Emit a final sentinel frame so the client knows we're done.
        end_frame = Frame(
            ts=_time.time(),
            step_id=step_id,
            token="",
            token_id=-1,
            point=Point3D(0.0, 0.0, 0.0),
            perplexity=None,
            entropy=None,
            is_self_check=False,
            is_revisit=False,
        )
        end_frame._raw_hidden = None  # type: ignore[attr-defined]
        end_frame._is_end = True  # type: ignore[attr-defined]
        on_frame(end_frame)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def default_runner() -> BaseModelRunner:
    return SyntheticRunner()


def qwen3_1p7b_runner(
    model_path: str = "/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master",
    device: str = "cuda:7",
    dtype: str = "bfloat16",
) -> BaseModelRunner:
    """Lazy-singleton factory for the Qwen3-1.7B model.

    Loading a 1.7B model takes ~5-15 s on a Blackwell GPU and uses
    ~3.5 GB of VRAM. We cache the loaded runner in a module-level
    variable so multiple WebSocket sessions can share one model
    instance without reloading.
    """
    import torch

    global _qwen3_runner_singleton
    try:
        if _qwen3_runner_singleton is not None:
            return _qwen3_runner_singleton  # type: ignore[name-defined]
    except NameError:
        _qwen3_runner_singleton = None

    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch_dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[dtype]

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        dtype=torch_dtype,
        device_map={"": device},
    )
    model.eval()

    # Build a small HFTransformerRunner-like instance and reuse the
    # stream() implementation we just wrote.
    r = HFTransformerRunner.__new__(HFTransformerRunner)
    r.tokenizer = tokenizer
    r.model = model
    r.d_model = model.config.hidden_size
    r._handles = []
    _qwen3_runner_singleton = r
    return r