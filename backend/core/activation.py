"""Activation extraction and vector-injection helpers.

This module is the single seam between the model implementation
and the rest of the framework. Everything that needs to touch
PyTorch hooks or capture residual-stream activations goes
through here.

In the synthetic demo these helpers are not exercised (the
SyntheticRunner produces activations in pure Python). In the
real-model demo (`examples/demo_real_model.py`) they provide
the canonical entry points:

  * `install_residual_add_hook(model, layer_idx, vector)` — adds
    `vector` to the residual stream at the input of `layer_idx`.
    The user's vector-injection logic uses this.

  * `get_residual_at_last_token(model, layer_idx, prompt)` —
    captures the residual stream after layer `layer_idx` for the
    last token of `prompt`. Used as the seed for the 3-D path.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Public API (works for any HuggingFace Llama-style model)
# ---------------------------------------------------------------------------


def install_residual_add_hook(model: Any, layer_idx: int, add_vector: np.ndarray):
    """Install a forward-pre-hook that adds `add_vector` (1-D, shape
    `(d_model,)`) to the residual stream input of every transformer
    block at index `layer_idx`.

    Returns the hook handle so the caller can remove it.
    """
    import torch

    block = model.model.layers[layer_idx]
    p = next(block.parameters())
    v = torch.as_tensor(add_vector, dtype=p.dtype, device=p.device)
    if v.dim() == 1:
        v = v.view(1, 1, -1)  # (1, 1, d_model) — broadcast over (T, B)

    def hook(module, inputs):
        x = inputs[0]
        return (x + v,) + inputs[1:]

    return block.register_forward_pre_hook(hook)


def get_residual_at_last_token(
    model: Any, layer_idx: int, prompt: str
) -> np.ndarray:
    """Run the model on `prompt` once and return the residual-stream
    activation at the last token of layer `layer_idx`, as a 1-D
    numpy vector on CPU.

    Convenience wrapper for one-shot extraction during the
    pre-extraction of steering vectors. For streaming extraction
    inside `model_runner.stream()`, do the hook install/remove
    inline so you can capture per-token activations.
    """
    import torch

    captured: list = []

    def hook(module, inputs, outputs):
        h = outputs[0] if not isinstance(outputs, tuple) else outputs[0]
        captured.append(h[:, -1, :].detach().cpu().numpy())

    handle = model.model.layers[layer_idx].register_forward_hook(hook)
    try:
        tok = model.tokenizer(prompt, return_tensors="pt").to(model.model.device)
        with torch.no_grad():
            model(**tok)
    finally:
        handle.remove()
    return captured[0][0]


def remove_hook(handle: Any) -> None:
    """Cleanly remove a previously installed hook handle."""
    handle.remove()