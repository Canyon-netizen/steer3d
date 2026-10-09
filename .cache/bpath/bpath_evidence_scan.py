"""固定既有方向、剂量与抽样规则，补位置、层响应、概率与状态位移。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

import numpy as np


TIDS = [f"aime__aime25__p{p:02d}__{mode}" for p in (0, 1)
        for mode in ("think", "no_think")]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def npz_shape(path, key):
    with zipfile.ZipFile(path) as archive, archive.open(key + ".npy") as stream:
        version = np.lib.format.read_magic(stream)
        reader = (np.lib.format.read_array_header_1_0 if version == (1, 0)
                  else np.lib.format.read_array_header_2_0)
        return reader(stream)[0]


def lse(values):
    values = np.asarray(values, dtype=np.float64)
    maximum = float(np.max(values))
    return maximum + float(np.log(np.exp(values - maximum).sum()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--gpu-uuid", required=True)
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_uuid
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    free = subprocess.check_output([
        "nvidia-smi", "--id=" + args.gpu_uuid,
        "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True)
    assert int(free.strip()) >= 16000, "selected GPU no longer has enough free memory"
    root = Path(args.root)
    r6 = load_module("scan_r6", root / "r6_rerun.py")
    dose = load_module("scan_dose", root / "dose_sweep.py")
    layer = load_module("scan_layer", root / "layer_inject_sweep.py")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    vector_path = root / "w_L19_m0.npy"
    metadata = json.loads(Path(str(vector_path) + ".json").read_text(encoding="utf-8"))
    vector = np.load(vector_path).astype(np.float32)
    assert vector.shape == (2048,) and np.isfinite(vector).all()
    assert abs(float(np.linalg.norm(vector)) - 1) < 1e-5
    assert metadata["layer"] == r6.LAYER and metadata["npz_layer"] == r6.NPZ_LAYER
    gap = float(metadata["class_gap"])
    random = np.random.default_rng(42).standard_normal(len(vector)).astype(np.float32)
    random /= np.linalg.norm(random)
    directions = {"w+": vector, "w-": -vector, "rand": random}
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, local_files_only=True).to("cuda:0").eval()
    assert model.config.num_hidden_layers == r6.N_BLOCKS
    marker_ids = list(r6.MARKER_IDS)
    target_ids = marker_ids + [r6.CONTROL_ID]
    target_weights = model.lm_head.weight[target_ids].detach().float().cpu().numpy().astype(np.float64)
    direct_dots = target_weights @ vector.astype(np.float64)
    state_layers = list(range(r6.LAYER, r6.N_BLOCKS)) + [-1]
    started = time.time()

    def forward(ids, direction=None, alpha=0.0, inject_layer=r6.LAYER, capture=False):
        hooks, states = [], {}
        norm = None
        def alter(h):
            changed = h.clone()
            changed[:, -1, :] += alpha * torch.as_tensor(direction, dtype=h.dtype, device=h.device)
            return changed
        def pre(index):
            def hook(module, inputs):
                h = inputs[0]
                if index == inject_layer and alpha != 0:
                    h = alter(h)
                if capture and index in state_layers:
                    states[index] = h[0, -1].detach().float().cpu().numpy().copy()
                return (h,) + inputs[1:] if index == inject_layer and alpha != 0 else None
            return hook
        def norm_hook(module, inputs, output):
            nonlocal norm
            h = alter(output) if inject_layer == -1 and alpha != 0 else output
            norm = h[0, -1].detach().float().cpu().numpy().copy()
            if capture:
                states[-1] = norm
            return h if inject_layer == -1 and alpha != 0 else None
        for index, block in enumerate(model.model.layers):
            if capture or index == inject_layer:
                hooks.append(block.register_forward_pre_hook(pre(index)))
        hooks.append(model.model.norm.register_forward_hook(norm_hook))
        try:
            with torch.inference_mode():
                output = model(input_ids=ids.unsqueeze(0), use_cache=False, return_dict=True)
            logits = output.logits[0, -1].float().cpu().numpy().astype(np.float64)
        finally:
            for hook in hooks:
                hook.remove()
        return logits, norm, states

    def readings(logits):
        partition = lse(logits)
        marker_lse = lse(logits[marker_ids])
        return {"marker_lse": marker_lse, "marker_logprob": marker_lse - partition,
                "control_logit": float(logits[r6.CONTROL_ID]),
                "control_logprob": float(logits[r6.CONTROL_ID]) - partition,
                "argmax_id": int(logits.argmax()),
                "marker_logits": [float(logits[j]) for j in marker_ids],
                "marker_logprobs": [float(logits[j] - partition) for j in marker_ids]}

    result = {"schema": "steer3d.bpath_scan/1", "complete": False,
              "scan_script_sha256": sha(__file__),
              "model": args.model, "dtype": "bfloat16", "gpu_uuid": args.gpu_uuid,
              "vector_sha256": sha(vector_path), "vector_metadata": metadata,
              "dose": dose.DOSE, "gap": gap, "layer": r6.LAYER,
              "layer_ladder": layer.LAYER_LADDER, "marker_ids": marker_ids,
              "control_id": r6.CONTROL_ID,
              "marker_text": [tokenizer.decode([j]) for j in marker_ids],
              "direct_dots": direct_dots.tolist(), "trajectories": [],
              "sources": {name: sha(root / name) for name in
                          ("r6_rerun.py", "dose_sweep.py", "layer_inject_sweep.py")},
              "coordinate": "prefix ids[:P+t]; inject last input P+t-1; recorded NPZ[t-1,19]",
              "random_seed": 42, "random_sha256": hashlib.sha256(random.tobytes()).hexdigest()}
    displacements = {index: [] for index in state_layers}
    targets = []
    for tid in TIDS:
        sidecar_path = root / "gen_b2" / "aime" / (tid + ".json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        npz_path = sidecar_path.with_suffix(".npz")
        n_tok = sidecar["n_generated_tokens"]
        assert tuple(npz_shape(npz_path, "hidden_states")) == (n_tok, r6.N_BLOCKS, 2048)
        with np.load(npz_path) as z:
            generated = z["token_ids"].tolist()
        assert len(generated) == n_tok
        prompt = tokenizer(sidecar["chat_template_input"], add_special_tokens=False)["input_ids"]
        assert len(prompt) == sidecar["extra"]["prompt_tokens"]
        markers = [i for i, token in enumerate(sidecar["tokens"]) if token["token_id"] in marker_ids]
        positions = r6.sample_markers(markers, n_tok)
        assert positions and all(generated[t] in marker_ids for t in positions)
        trajectory = {"id": tid, "mode": sidecar["config"]["mode"], "n_tok": n_tok,
                      "sidecar_sha256": sha(sidecar_path), "positions": positions, "sites": []}
        for site_index, t in enumerate(positions):
            ids = torch.tensor(prompt + generated[:t], dtype=torch.long, device="cuda:0")
            assert len(ids) == len(prompt) + t and t > 0
            base_logits, base_norm, baseline_states = forward(ids, capture=True)
            repeated, _, _ = forward(ids)
            assert np.array_equal(base_logits, repeated), "baseline/empty hooks changed logits"
            base = readings(base_logits)
            conditional_marker = np.exp(base_logits[marker_ids] - lse(base_logits[marker_ids]))
            site = {"t": t, "inject_abs": len(ids) - 1, "marker_id": generated[t],
                    "marker_text": tokenizer.decode([generated[t]]), "prefix_tail": tokenizer.decode(ids[-32:].tolist()),
                    "baseline": base, "baseline_repeated_exact": True,
                    "input_norm": float(np.linalg.norm(baseline_states[r6.LAYER])),
                    "conditional_direct_dot": float(conditional_marker @ direct_dots[:len(marker_ids)]),
                    "variants": [], "layers": []}
            for name, direction in directions.items():
                for rel in dose.DOSE:
                    logits, _, states = forward(ids, direction, rel * gap, capture=True)
                    read = readings(logits)
                    variant = {"direction": name, "rel": rel, "alpha": rel * gap,
                               "d_marker_lse": read["marker_lse"] - base["marker_lse"],
                               "d_marker_logprob": read["marker_logprob"] - base["marker_logprob"],
                               "d_control_logit": read["control_logit"] - base["control_logit"],
                               "d_control_logprob": read["control_logprob"] - base["control_logprob"],
                               "readout": read, "projection": {}}
                    for index in state_layers:
                        displacements[index].append(states[index] - baseline_states[index])
                    targets.append(variant)
                    site["variants"].append(variant)
            if site_index == 0:
                for inject_layer in layer.LAYER_LADDER:
                    logits, norm, _ = forward(ids, vector, gap, inject_layer=inject_layer)
                    read = readings(logits)
                    row = {"layer": inject_layer, "d_marker_lse": read["marker_lse"] - base["marker_lse"],
                           "d_marker_logprob": read["marker_logprob"] - base["marker_logprob"],
                           "d_control_logit": read["control_logit"] - base["control_logit"],
                           "d_marker_logits": [float(logits[j] - base_logits[j]) for j in marker_ids]}
                    if inject_layer == -1:
                        effective = norm.astype(np.float64) - base_norm.astype(np.float64)
                        predicted = target_weights @ effective
                        observed = logits[target_ids] - base_logits[target_ids]
                        # FP32 accumulation bound plus two BF16 endpoint roundings.
                        unit = 2.0**-24
                        gamma = (len(vector) * unit) / (1 - len(vector) * unit)
                        products = np.abs(target_weights) @ (np.abs(norm.astype(np.float64)) + np.abs(base_norm.astype(np.float64)))
                        def half_ulp(x):
                            return np.exp2(np.floor(np.log2(np.maximum(np.abs(x), 2.0**-126))) - 8)
                        bound = gamma * products + half_ulp(logits[target_ids]) + half_ulp(base_logits[target_ids])
                        residual = observed - predicted
                        row["calibration"] = {"prediction": predicted.tolist(), "observed": observed.tolist(),
                                              "residual": residual.tolist(), "error_bound": bound.tolist(),
                                              "effective_delta_norm": float(np.linalg.norm(effective)),
                                              "ok": bool(np.linalg.norm(effective) > 0 and np.max(np.abs(predicted)) > 0
                                                         and np.all(np.abs(residual) <= bound))}
                        assert row["calibration"]["ok"], "post-norm linear calibration failed"
                    site["layers"].append(row)
            trajectory["sites"].append(site)
            print(f"{tid} t={t} positions={site_index+1}/{len(positions)} "
                  f"baseline_exact=True elapsed={time.time()-started:.1f}s", flush=True)
            result["trajectories"] = result["trajectories"] + [trajectory] if site_index == 0 else result["trajectories"]
            partial = Path(args.out + ".partial")
            partial.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    pca = {}
    for index, values in displacements.items():
        delta = np.stack(values).astype(np.float64)
        centered = delta - delta.mean(axis=0)
        gram = centered @ centered.T
        eigenvalues, eigenvectors = np.linalg.eigh(gram)
        order = np.argsort(eigenvalues)[::-1][:3]
        eigenvalues = np.maximum(eigenvalues[order], 0)
        axes = np.zeros((3, len(vector)))
        for axis, (value, column) in enumerate(zip(eigenvalues, order)):
            if value > 1e-16:
                axes[axis] = centered.T @ eigenvectors[:, column] / np.sqrt(value)
                if axes[axis, np.argmax(np.abs(axes[axis]))] < 0:
                    axes[axis] *= -1
        coords = delta @ axes.T
        for target, coord in zip(targets, coords):
            target["projection"][str(index)] = [round(float(x), 6) for x in coord]
        denominator = float(np.square(centered).sum())
        pca[str(index)] = {"explained_variance": (eigenvalues / denominator).tolist() if denominator > 0 else [0, 0, 0],
                           "basis_sha256": hashlib.sha256(axes.tobytes()).hexdigest(), "n_points": len(delta),
                           "meaning": "shared basis in this layer; coordinates are delta_h relative to site baseline"}
    result.update({"pca": pca, "complete": True, "elapsed_seconds": time.time() - started})
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=1), encoding="utf-8")
    print(f"ALLDONE sites={sum(len(t['sites']) for t in result['trajectories'])} out={args.out}", flush=True)


if __name__ == "__main__":
    main()
