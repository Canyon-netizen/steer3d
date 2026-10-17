"""Native SwiGLU measurements and same-prefix product interventions.

The unit is the actual input coordinate of down_proj, not a learned dictionary.
Blocking/restoration establish conditional effects of internal interventions;
they do not identify a reasoning algorithm or additive mediation percentages.
"""
from __future__ import annotations

from typing import Mapping, Optional
import numpy as np


def sign_regimes(gate, value):
    g, u = np.asarray(gate), np.asarray(value)
    if g.shape != u.shape or not np.isfinite(g).all() or not np.isfinite(u).all():
        raise ValueError("gate/value must have the same finite shape")
    return np.where((g == 0) | (u == 0), 4,
                    np.where(g > 0, np.where(u > 0, 0, 1), np.where(u > 0, 2, 3)))


def select_units(discovery_pairs, column_norms, k):
    """Rank on discovery response only; ties use unit id, never evaluation data."""
    if not discovery_pairs or k < 1:
        raise ValueError("need nonempty discovery and positive k")
    groups, scores, profiles = {}, {}, {}
    for layer, norms in column_norms.items():
        norms = np.asarray(norms, dtype=float)
        if norms.ndim != 1 or not np.isfinite(norms).all() or len(norms) <= 2*k:
            raise ValueError("invalid native column norms or insufficient control units")
        deltas = np.stack([np.abs(b[layer]["product"]-a[layer]["product"]) for a,b in discovery_pairs])
        baseline = np.stack([np.abs(a[layer]["product"]) for a,_ in discovery_pairs])
        score = deltas.mean(axis=0)*norms
        if not np.isfinite(score).all() or np.max(score) == 0:
            raise ValueError("candidate selection has no measured response")
        ids = np.lexsort((np.arange(len(score)),-score))[:k]
        groups[layer] = sorted(ids.tolist())
        scores[layer] = score
        profiles[layer] = baseline.mean(axis=0)
    return groups, scores, profiles


def matched_random_groups(selected, profiles, column_norms, count=4, seed=0):
    """Match discovery activation and writer-size quartiles, without reuse."""
    rng = np.random.default_rng(seed)
    output, matching = [], []
    for _ in range(count):
        group, audit = {}, {}
        for layer, ids in selected.items():
            magnitude, norms = np.asarray(profiles[layer]), np.asarray(column_norms[layer])
            bins = np.searchsorted(np.quantile(magnitude,[.25,.5,.75]),magnitude,side="right")*4
            bins += np.searchsorted(np.quantile(norms,[.25,.5,.75]),norms,side="right")
            available = set(range(len(bins)))-set(ids)
            chosen, fallback = [], 0
            for unit in ids:
                pool = sorted(i for i in available if bins[i] == bins[unit])
                if not pool:
                    fallback += 1
                    distances = {i:abs(int(bins[i]//4-bins[unit]//4))+abs(int(bins[i]%4-bins[unit]%4)) for i in available}
                    best = min(distances.values())
                    pool = sorted(i for i in available if distances[i] == best)
                item = int(rng.choice(pool))
                chosen.append(item)
                available.remove(item)
            group[layer] = sorted(chosen)
            audit[layer] = {"n":len(chosen),"fallback":fallback}
        output.append(group)
        matching.append(audit)
    return output, matching


def native_forward(model, input_ids, *, injection_layer, vector=None, alpha=0.0,
                   patches: Optional[Mapping[int,dict]]=None, collect=True,
                   max_control_scale=1e6, control_norm_rtol=.005):
    """Run the actual model; inject/patch ONLY final input position, batch=1.

    A patch contains unique `indices`, full natural `donor` product, and optional
    `target_write_norm`. Norm-matched controls may be scaled off the donor state;
    that scale and the actual written norm are recorded explicitly.
    """
    import torch
    blocks = model.model.layers
    if input_ids.ndim != 2 or input_ids.shape[0] != 1 or input_ids.shape[1] < 1:
        raise ValueError("one nonempty token prefix required")
    if not 0 <= injection_layer < len(blocks):
        raise ValueError("invalid injection block")
    patches = {} if patches is None else dict(patches)
    if any(not injection_layer <= layer < len(blocks) for layer in patches):
        raise ValueError("patch must be downstream of injection")
    states, writes, hooks = {}, {}, []
    measured_input_norm = None
    training = model.training
    model.eval()

    def inject(module, inputs):
        nonlocal measured_input_norm
        h = inputs[0]
        measured_input_norm = float(h[0,-1].float().norm().item())
        if alpha == 0:
            return None
        v = torch.as_tensor(vector,device=h.device,dtype=h.dtype)
        if v.shape != h.shape[-1:] or not torch.isfinite(v).all() or not np.isfinite(alpha):
            raise ValueError("invalid vector/dose")
        changed = h.clone()
        changed[:,-1] += alpha*v
        return (changed,)+inputs[1:]

    def capture_value(layer,key):
        def hook(module,inputs,output):
            states[layer][key] = output[0,-1].detach().clone()
        return hook

    def product_hook(layer):
        def hook(module,inputs):
            a = inputs[0]
            if collect:
                states[layer]["product"] = a[0,-1].detach().clone()
                states[layer]["effective_gate"] = blocks[layer].mlp.act_fn(states[layer]["gate"])
                reconstructed = states[layer]["effective_gate"]*states[layer]["value"]
                eps = torch.finfo(a.dtype).eps
                if not torch.allclose(reconstructed,a[0,-1],rtol=8*eps,atol=8*eps):
                    raise ValueError("native SwiGLU product reconstruction failed")
                states[layer]["product_max_error"] = float((reconstructed-a[0,-1]).abs().max())
            if layer not in patches:
                return None
            spec = patches[layer]
            indices = list(spec["indices"])
            if not indices or len(set(indices)) != len(indices) or min(indices) < 0 or max(indices) >= a.shape[-1]:
                raise ValueError("patch indices must be nonempty unique native units")
            donor = torch.as_tensor(spec["donor"],device=a.device,dtype=a.dtype)
            if donor.shape != a.shape[-1:] or not torch.isfinite(donor).all():
                raise ValueError("invalid donor product")
            idx = torch.tensor(indices,device=a.device,dtype=torch.long)
            delta = donor[idx].double()-a[0,-1,idx].double()
            weights = module.weight[:,idx].double()
            raw_norm = float((weights@delta.double()).norm().item())
            target = spec.get("target_write_norm")
            scale = 1.0
            if target is not None:
                if not np.isfinite(target) or target < 0 or (target > 0 and raw_norm == 0):
                    raise ValueError("unmatchable random-control write norm")
                scale = target/raw_norm if raw_norm else 0.0
                if scale > max_control_scale:
                    raise ValueError("random-control scale exceeds frozen bound")
                delta = delta*scale
            changed = a.clone()
            if target is None:
                changed[0,-1,idx] = donor[idx]
            else:
                changed[0,-1,idx] = (a[0,-1,idx].double()+delta).to(a.dtype)
            effective = changed[0,-1,idx].double()-a[0,-1,idx].double()
            effective_norm = float((weights@effective.double()).norm().item())
            if target is not None and abs(effective_norm-target) > control_norm_rtol*max(target,1e-12):
                raise ValueError("actual control write norm outside declared tolerance")
            writes[layer] = {"n_units":len(indices),"raw_write_norm":raw_norm,
                             "applied_write_norm":effective_norm,"target_write_norm":target,"scale":scale}
            return (changed,)+inputs[1:] if torch.count_nonzero(effective) else None
        return hook

    try:
        hooks.append(blocks[injection_layer].register_forward_pre_hook(inject))
        for layer in range(injection_layer,len(blocks)):
            mlp = blocks[layer].mlp
            if not all(hasattr(mlp,key) for key in ("gate_proj","up_proj","down_proj","act_fn")):
                raise ValueError("model must expose a native gated MLP")
            if collect:
                states[layer] = {}
                hooks.append(mlp.gate_proj.register_forward_hook(capture_value(layer,"gate")))
                hooks.append(mlp.up_proj.register_forward_hook(capture_value(layer,"value")))
            if collect or layer in patches:
                hooks.append(mlp.down_proj.register_forward_pre_hook(product_hook(layer)))
        with torch.inference_mode():
            output = model(input_ids=input_ids,use_cache=False,return_dict=True)
        logits = output.logits[0,-1].detach().float().cpu().numpy().copy()
        if not np.isfinite(logits).all():
            raise ValueError("nonfinite actual output")
        captured = {layer:{key:(value.detach().float().cpu().numpy().copy() if torch.is_tensor(value) else value)
                          for key,value in row.items()} for layer,row in states.items()}
        return {"logits":logits,"states":captured,"writes":writes,"input_norm":measured_input_norm}
    finally:
        for handle in hooks:
            handle.remove()
        model.train(training)
