"""Observe actual residual writes around native_forward, including patched products.

Coordinates are native model coordinates. No learned replacement model is used.
The attention write is the real self_attn output, not attention-weight attribution.
"""
from __future__ import annotations

import numpy as np
from .neuron_mediation import native_forward


def trace_forward(model, input_ids, *, injection_layer, vector=None, alpha=0., patches=None):
    import torch
    records, handles = {}, []

    def clone(value):
        return value[0, -1].detach().float().cpu().numpy().copy()

    def before(layer):
        def hook(module, inputs):
            records[layer] = {"incoming": clone(inputs[0])}
        return hook

    def after_attention(layer):
        def hook(module, inputs):
            records[layer]["after_attention"] = clone(inputs[0])
        return hook

    def output(layer, key):
        def hook(module, inputs, result):
            records[layer][key] = clone(result[0] if isinstance(result, tuple) else result)
            if key == "mlp":
                # This hook runs AFTER any product intervention in native_forward.
                records[layer]["applied_product"] = clone(inputs[0])
        return hook

    try:
        for layer in range(injection_layer, len(model.model.layers)):
            block = model.model.layers[layer]
            handles.append(block.register_forward_pre_hook(before(layer)))
            handles.append(block.self_attn.register_forward_hook(output(layer, "attention")))
            handles.append(block.post_attention_layernorm.register_forward_pre_hook(after_attention(layer)))
            handles.append(block.mlp.down_proj.register_forward_hook(output(layer, "mlp")))
            handles.append(block.register_forward_hook(output(layer, "out")))
        result = native_forward(model, input_ids, injection_layer=injection_layer,
                                vector=vector, alpha=alpha, patches=patches, collect=True)
        for layer, row in records.items():
            row.update(result["states"][layer])
            # Preserve the actual float32 addition used by the model.
            row["input"] = row["incoming"].copy()
            if layer == injection_layer and alpha:
                row["input"] += np.asarray(vector, dtype=np.float32) * np.float32(alpha)
            closure = row["out"].astype(float) - row["input"] - row["attention"] - row["mlp"]
            row["closure_l2"] = float(np.linalg.norm(closure))
            row["closure_relative"] = float(np.linalg.norm(closure) /
                max(np.linalg.norm(row["out"].astype(float)-row["input"]), 1e-12))
            if row["closure_relative"] > 2e-5:
                raise ValueError(f"residual write closure failed at block {layer}")
        result["trace"] = records
        return result
    finally:
        for handle in handles:
            handle.remove()


def fit_basis(points):
    """One fixed, baseline-only, centered linear PCA basis for each block."""
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or min(points.shape) < 3 or not np.isfinite(points).all():
        raise ValueError("need at least three finite hidden states")
    mean = points.mean(axis=0)
    _, singular, vt = np.linalg.svd(points-mean, full_matrices=False)
    basis = vt[:3].copy()
    # Canonical orientation makes repeated exports deterministic.
    for axis in basis:
        if axis[np.argmax(np.abs(axis))] < 0:
            axis *= -1
    return mean, basis, (singular[:3]**2 / max(float((singular**2).sum()), 1e-30))
