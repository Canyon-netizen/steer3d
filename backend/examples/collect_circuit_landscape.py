"""Replay recorded reasoning prefixes and export native hidden-state/write evidence.

Four source trajectories, eight consecutive prefix positions around each first
eligible marker. Each intervention affects ONLY the final input token. This is
a sequence of matched local experiments, not a free-running steered rollout.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.circuit_trace import trace_forward, fit_basis

ARMS = ["baseline", "plus", "minus", "random", "block", "restore"]
MARKERS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def readout(logits, tokenizer):
    x = np.asarray(logits, dtype=float)
    z = np.logaddexp.reduce(x)
    ids = np.argsort(-x)[:5]
    return {"marker_logprob": float(np.logaddexp.reduce(x[MARKERS])-z),
            "top_tokens": [{"id": int(i), "text": tokenizer.decode([int(i)]),
                            "probability": float(np.exp(x[i]-z))} for i in ids]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "vector", "source-root", "mediation", "source-manifest", "out"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--gpu-uuid", required=True)
    args = p.parse_args()
    if args.out.exists():
        raise FileExistsError("never overwrite a completed capture")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_uuid
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    def idle():
        values = subprocess.check_output(["nvidia-smi", "--id="+args.gpu_uuid,
            "--query-gpu=memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], text=True)
        used, free, util = [int(v.strip()) for v in values.strip().split(",")]
        if used > 1024 or free < 24000 or util > 10:
            raise RuntimeError("GPU is occupied; refusing contention")
    idle()
    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModelForCausalLM
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True,
        dtype=torch.float32, attn_implementation="eager")
    idle()
    model = model.to("cuda:0").eval()
    assert model.config.hidden_act == "silu" and len(model.model.layers) == 28
    assert all(b.mlp.down_proj.bias is None for b in model.model.layers)
    vector = np.load(args.vector).astype(np.float32)
    mediation = read(args.mediation)
    assert mediation["complete"] and sha(args.vector) == mediation["vector_sha256"]
    groups = {int(k): v for k, v in mediation["selection"]["groups"].items()}
    assert set(groups) == set(range(20, 28))
    rng = np.random.default_rng(20261017)
    random = rng.standard_normal(len(vector)).astype(np.float32)
    random /= np.linalg.norm(random)
    sources = read(args.source_manifest)["trajectories"][:4]
    weights = {l: model.model.layers[l].mlp.down_proj.weight.detach().float().cpu().numpy()
               for l in groups}
    norms = {l: np.linalg.norm(w, axis=0) for l, w in weights.items()}
    captures, source_rows = [], []
    started = time.time()
    max_closure = 0.
    for source in sources:
        tid = source["trajectory"]
        path = args.source_root/(tid+".json")
        assert sha(path) == source["sidecar_sha256"]
        side = read(path)
        prompt = tokenizer(side["chat_template_input"], add_special_tokens=False)["input_ids"]
        tokens = [r["token_id"] for r in side["tokens"]]
        assert len(prompt) == source["prompt_tokens"]
        anchor = source["selected_sites"][0]["t"]
        positions = list(range(anchor-4, anchor+4))
        assert positions[0] > 0 and len(prompt)+positions[-1] <= 2048
        source_rows.append({"id": tid, "problem_id": source["problem_id"], "mode": source["mode"],
            "anchor": anchor, "sidecar_sha256": sha(path), "question": side.get("prompt", side.get("user_prompt", "")),
            "prompt_text": side["chat_template_input"], "positions": positions})
        for t in positions:
            ids = torch.tensor([prompt+tokens[:t]], device="cuda:0", dtype=torch.long)
            def run(v=None, alpha=0., patches=None):
                return trace_forward(model, ids, injection_layer=20, vector=v, alpha=alpha, patches=patches)
            baseline = run()
            alpha = .1 * baseline["input_norm"]
            plus = run(vector, alpha)
            patches = lambda donor: {l: {"indices": group, "donor": donor["states"][l]["product"]}
                                     for l, group in groups.items()}
            variants = {"baseline": baseline, "plus": plus, "minus": run(-vector, alpha),
                        "random": run(random, alpha), "block": run(vector, alpha, patches(baseline)),
                        "restore": run(patches=patches(plus))}
            if t == positions[0]:
                repeated = run()
                assert np.array_equal(baseline["logits"], repeated["logits"])
                identity = run(patches=patches(baseline))
                assert np.array_equal(baseline["logits"], identity["logits"])
            record = {"trajectory": tid, "t": t, "anchor": t == anchor,
                "prefix_sha256": hashlib.sha256(np.asarray(prompt+tokens[:t], dtype="<i8").tobytes()).hexdigest(),
                "n_prefix_tokens": ids.shape[1], "next_token": tokenizer.decode([tokens[t]]),
                "context_before": tokenizer.decode(tokens[max(0,t-60):t]),
                "context_after": tokenizer.decode(tokens[t:t+24]), "alpha": alpha, "arms": {}}
            for arm, result in variants.items():
                record["arms"][arm] = {"readout": readout(result["logits"], tokenizer), "layers": {}}
                for l, row in result["trace"].items():
                    max_closure = max(max_closure, row["closure_relative"])
                    record["arms"][arm]["layers"][l] = row
            captures.append(record)
            print(f"CAPTURE {tid} t={t} arms={len(variants)} closure={max_closure:.3g}", flush=True)

    bases, pca = {}, {}
    for l in groups:
        points = [r["arms"]["baseline"]["layers"][l][key] for r in captures
                  for key in ("input", "after_attention", "out")]
        mean, basis, explained = fit_basis(points)
        bases[l] = mean, basis
        pca[str(l)] = {"mean": mean.tolist(), "basis": basis.tolist(), "explained_variance": explained.tolist(),
                      "fit": "baseline input / after_attention / output, all four windows; fixed across arms"}
    archive = {}
    exported = []
    unit_columns = {l: set() for l in groups}
    for idx, r in enumerate(captures):
        out = {k: v for k, v in r.items() if k != "arms"}
        out["arms"] = {}
        for arm in ARMS:
            out["arms"][arm] = {"readout": r["arms"][arm]["readout"], "layers": {}}
        for l in groups:
            mean, basis = bases[l]
            base = r["arms"]["baseline"]["layers"][l]
            plus = r["arms"]["plus"]["layers"][l]
            # Local descriptive ranking only: no behavior scores select these nodes.
            active = np.argsort(-np.abs(base["product"])*norms[l], kind="stable")[:6]
            response = np.argsort(-np.abs(plus["product"]-base["product"])*norms[l], kind="stable")[:6]
            units = sorted(set(active.tolist()+response.tolist()))
            unit_columns[l].update(units)
            for arm in ARMS:
                row = r["arms"][arm]["layers"][l]
                key = f"s{idx}_{arm}_L{l}"
                for name in ("incoming", "input", "after_attention", "out", "attention", "mlp"):
                    archive[key+"_"+name] = row[name]
                archive[key+"_units"] = np.asarray(units)
                for name in ("gate", "value", "effective_gate", "product", "applied_product"):
                    archive[key+"_"+name] = row[name][units]
                states = {name: (basis@(row[name]-mean)).tolist()
                          for name in ("incoming", "input", "after_attention", "out")}
                arrows = {name: (basis@row[name]).tolist() for name in ("attention", "mlp")}
                native = []
                for i in units:
                    applied = float(row["applied_product"][i])
                    gate, value = float(row["effective_gate"][i]), float(row["value"][i])
                    native.append({"id": i, "gate": gate, "value": value,
                        "raw_gate": float(row["gate"][i]), "natural_product": float(row["product"][i]),
                        "product": applied, "baseline_product": float(base["applied_product"][i]),
                        "regime": ("+" if gate > 0 else "−" if gate < 0 else "0")+("+" if value > 0 else "−" if value < 0 else "0"),
                        "patched": i in groups[l] and arm in ("block", "restore"),
                        "in_frozen_group": i in groups[l],
                        "write_norm": abs(applied)*float(norms[l][i]),
                        "response_norm": abs(applied-float(base["applied_product"][i]))*float(norms[l][i]),
                        "write": (basis@(weights[l][:,i]*applied)).tolist(),
                        "writer": (basis@weights[l][:,i]).tolist()})
                remainder = np.asarray(arrows["mlp"])-np.sum([n["write"] for n in native], axis=0)
                out["arms"][arm]["layers"][str(l)] = {"states": states, "writes": arrows,
                    "units": native, "remainder": remainder.tolist(), "closure_l2": row["closure_l2"],
                    "closure_relative": row["closure_relative"],
                    "displayed_native_units": len(native), "total_native_units": len(row["product"])}
        exported.append(out)
    for l, ids in unit_columns.items():
        index = sorted(ids)
        archive[f"L{l}_writer_ids"] = np.asarray(index)
        archive[f"L{l}_writers"] = weights[l][:,index]
        archive[f"L{l}_basis"] = bases[l][1]
        archive[f"L{l}_mean"] = bases[l][0]
    raw_path = args.out.with_suffix(".npz")
    np.savez_compressed(raw_path, **archive)
    # Keep the browser payload small; the full basis lives in the audit archive.
    for row in pca.values():
        row.pop("mean")
        row.pop("basis")
    result = {"schema": "steer3d.circuit_landscape/1", "complete": True,
        "model": "Qwen3-1.7B", "dtype": "float32", "torch": torch.__version__,
        "transformers": transformers.__version__, "gpu_uuid": args.gpu_uuid,
        "vector_sha256": sha(args.vector), "mediation_sha256": sha(args.mediation),
        "source_manifest_sha256": sha(args.source_manifest), "model_config_sha256": sha(args.model/"config.json"),
        "script_sha256": sha(__file__), "trace_source_sha256": sha(Path(__file__).parents[1]/"core/circuit_trace.py"),
        "native_forward_sha256": sha(Path(__file__).parents[1]/"core/neuron_mediation.py"),
        "raw_sha256": sha(raw_path), "strength": .1, "injection_block": 20,
        "arms": ARMS, "layers": sorted(groups), "marker_ids": MARKERS,
        "scope": "matched-prefix local interventions, final input token only; not free-running steered rollouts",
        "patch_group": {"units_per_layer": 32, "total_units": 256,
            "selection": "frozen synthetic-discovery group from neuron_mediation_v1; no selection on these trajectories",
            "groups": groups},
        "unit_selection": "union of top 6 baseline write norms and top 6 +v response write norms at each site/block; descriptive only",
        "sources": source_rows, "pca": pca, "sites": exported,
        "guards": {"baseline_repeat_exact": True, "identity_patch_exact": True,
            "max_residual_closure_relative": max_closure, "captured_sites": len(captures),
            "captured_forwards": len(captures)*len(ARMS), "seconds": time.time()-started}}
    args.out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    print("ALL_DONE", json.dumps(result["guards"]), flush=True)


if __name__ == "__main__":
    main()
