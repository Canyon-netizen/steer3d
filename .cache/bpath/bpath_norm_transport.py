"""补充 RMSNorm 分解；只增加 norm 输入读取，不更改方向、剂量或位置规则。

固定四条轨迹的首个 R6 抽样位置，沿用 DOSE、seed=42 和原 bfloat16 forward。
目的：分别量化后续 block 对状态位移的传播与最终 RMSNorm 的有限变换。
不修改 P9，不据此发布分组判决；范数增益不是目标语义的因果贡献比例。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np
from bpath_evidence_scan import TIDS, load_module, lse, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--gpu-uuid", required=True)
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_uuid
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    free = subprocess.check_output(["nvidia-smi", "--id="+args.gpu_uuid,
        "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True)
    assert int(free.strip()) >= 16000
    root = Path(args.root)
    r6 = load_module("norm_r6",root/"r6_rerun.py")
    dose = load_module("norm_dose",root/"dose_sweep.py")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    vector = np.load(root/"w_L19_m0.npy").astype(np.float32)
    meta = json.loads((root/"w_L19_m0.npy.json").read_text(encoding="utf-8"))
    gap = float(meta["class_gap"])
    random = np.random.default_rng(42).standard_normal(len(vector)).astype(np.float32)
    random /= np.linalg.norm(random)
    directions = {"w+":vector,"w-":-vector,"rand":random}
    tokenizer = AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(args.model,dtype=torch.bfloat16,
        local_files_only=True).to("cuda:0").eval()
    weights = model.lm_head.weight[r6.MARKER_IDS].detach().float().cpu().numpy().astype(np.float64)
    gamma = model.model.norm.weight.detach().float().cpu().numpy().astype(np.float64)
    epsilon = float(model.model.norm.variance_epsilon)
    d = len(vector)
    fp32_u = 2.0**-24
    gamma32 = d*fp32_u/(1-d*fp32_u)
    bf16_u = 2.0**-8
    records = []

    def forward(ids, v=None, alpha=0):
        states = {}
        def pre(module, inputs):
            h = inputs[0]
            if alpha != 0:
                h = h.clone()
                h[:,-1,:] += alpha*torch.as_tensor(v,dtype=h.dtype,device=h.device)
            states["injected"] = h[0,-1].detach().float().cpu().numpy().astype(np.float64)
            return (h,)+inputs[1:] if alpha != 0 else None
        def norm(module, inputs, output):
            states["before"] = inputs[0][0,-1].detach().float().cpu().numpy().astype(np.float64)
            states["after"] = output[0,-1].detach().float().cpu().numpy().astype(np.float64)
        hooks = [model.model.layers[r6.LAYER].register_forward_pre_hook(pre),
                 model.model.norm.register_forward_hook(norm)]
        try:
            with torch.inference_mode():
                out = model(input_ids=ids.unsqueeze(0),use_cache=False,return_dict=True)
            logits = out.logits[0,-1].float().cpu().numpy().astype(np.float64)
        finally:
            for hook in hooks:
                hook.remove()
        return states,logits

    for tid in TIDS:
        sidecar = json.loads((root/"gen_b2/aime"/(tid+".json")).read_text(encoding="utf-8"))
        with np.load(root/"gen_b2/aime"/(tid+".npz")) as z:
            gen = z["token_ids"].tolist()
        markers = [i for i,t in enumerate(sidecar["tokens"]) if t["token_id"] in r6.MARKER_IDS]
        t = r6.sample_markers(markers,sidecar["n_generated_tokens"])[0]
        pid = tokenizer(sidecar["chat_template_input"],add_special_tokens=False)["input_ids"]
        assert len(pid) == sidecar["extra"]["prompt_tokens"]
        ids = torch.tensor(pid+gen[:t],dtype=torch.long,device="cuda:0")
        baseline, base_logits = forward(ids)
        h0 = baseline["before"]
        r0 = np.sqrt(np.mean(h0*h0)+epsilon)
        ideal0 = gamma*h0/r0
        record = {"id":tid,"t":t,"baseline_rms":float(r0),"variants":[]}
        for name,v in directions.items():
            for rel in dose.DOSE:
                states,logits = forward(ids,v,rel*gap)
                h1 = states["before"]
                r1 = np.sqrt(np.mean(h1*h1)+epsilon)
                ideal1 = gamma*h1/r1
                delta_block = h1-h0
                transmitted = gamma*delta_block/r1
                rescaled = gamma*h0*(1/r1-1/r0)
                reconstructed = transmitted+rescaled
                observed = states["after"]-baseline["after"]
                bound = (2*bf16_u+bf16_u*bf16_u+gamma32)*(np.abs(ideal0)+np.abs(ideal1))+2.0**-126
                residual = observed-reconstructed
                assert np.all(np.abs(residual) <= bound), "RMSNorm reconstruction outside numeric bound"
                actual_input = states["injected"]-baseline["injected"]
                block_norm = float(np.linalg.norm(delta_block))
                input_norm = float(np.linalg.norm(actual_input))
                after_norm = float(np.linalg.norm(observed))
                record["variants"].append({"direction":name,"rel":rel,"alpha":rel*gap,
                    "injected_delta_norm":input_norm,"pre_norm_delta_norm":block_norm,
                    "post_norm_delta_norm":after_norm,
                    "block_norm_gain":block_norm/input_norm if input_norm else None,
                    "norm_norm_gain":after_norm/block_norm if block_norm else None,
                    "post_norm_alignment":float(observed@v/(after_norm*np.linalg.norm(v))) if after_norm else None,
                    "rms_after":float(r1),"norm_reconstruction_ok":True,
                    "norm_max_abs_error":float(np.max(np.abs(residual))),
                    "norm_max_error_bound":float(np.max(bound)),
                    "marker_logit_transmitted":(weights@transmitted).tolist(),
                    "marker_logit_rescaled":(weights@rescaled).tolist(),
                    "marker_logit_effective":(weights@observed).tolist(),
                    "d_marker_lse":lse(logits[r6.MARKER_IDS])-lse(base_logits[r6.MARKER_IDS]),
                    "d_marker_logprob":lse(logits[r6.MARKER_IDS])-lse(logits)
                        -lse(base_logits[r6.MARKER_IDS])+lse(base_logits)})
        records.append(record)
        print(f"{tid} t={t} RMSNorm reconstruction 18/18",flush=True)
    result = {"schema":"steer3d.bpath_norm_transport/1","complete":True,
        "vector_sha256":sha(root/"w_L19_m0.npy"),"script_sha256":sha(__file__),
        "dose":dose.DOSE,"gap":gap,"layer":r6.LAYER,"epsilon":epsilon,
        "gamma_sha256":hashlib.sha256(gamma.tobytes()).hexdigest(),"trajectories":records}
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=1),encoding="utf-8")
    print("ALLDONE",flush=True)


if __name__ == "__main__":
    main()
