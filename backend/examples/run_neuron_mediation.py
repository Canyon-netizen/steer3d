"""Run the preregistered native SwiGLU mediation experiment without retraining v."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.neuron_mediation import native_forward, select_units, matched_random_groups, sign_regimes


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lse(x):
    x = np.asarray(x,dtype=np.float64)
    m = float(x.max())
    return m+float(np.log(np.exp(x-m).sum()))


def outcome(logits, groups, kind):
    z = lse(logits)
    first, second = [lse(logits[ids]) for ids in groups]
    chosen = int(np.argmax(logits))
    if kind == "equation":
        return {"score":first-second,"p_correct":float(np.exp(first-z)),
                "answer_set_coverage":float(np.exp(first-z)+np.exp(second-z)),
                "argmax_correct":chosen in groups[0],"argmax_incorrect":chosen in groups[1],
                "argmax_outside_answer_set":chosen not in groups[0]+groups[1],"argmax_id":chosen}
    return {"score":first-z,"marker_logprob":first-z,"marker_lse":first,
            "p_marker":float(np.exp(first-z)),"argmax_id":chosen}


def problem_specs(protocol):
    rows = []
    for index, ((a,b),offset) in enumerate(zip(protocol["multiplications"],protocol["error_offsets"])):
        split = "discovery" if index in protocol["discovery_problem_indices"] else "evaluation"
        assert index in protocol[split+"_problem_indices"]
        for correct in (True,False):
            result = a*b if correct else a*b+offset
            assert (a*b == result) is correct
            for wording,prefix in protocol["wording_prefixes"].items():
                user = protocol["user_template"].format(prefix=prefix,a=a,b=b,result=result)
                rows.append({"id":f"math{index:02d}_{int(correct)}_{wording}","problem_id":f"math{index:02d}",
                    "split":split,"kind":"equation","correct_equation":correct,"wording":wording,
                    "a":a,"b":b,"stated_result":result,"computed_result":a*b,
                    "messages":[{"role":"system","content":protocol["system_prompt"]},{"role":"user","content":user}],
                    "answer": "A" if correct else "B"})
    return rows


def aime_specs(root,protocol,tokenizer,r6_path):
    spec = importlib.util.spec_from_file_location("neuron_original_r6",r6_path)
    r6 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r6)
    rows, exclusions = [], []
    rules = protocol["aime_transfer"]
    for index in rules["problem_indices"]:
        for mode in rules["modes"]:
            tid = f"aime__aime25__p{index:02d}__{mode}"
            path = root/(tid+".json")
            side = read(path)
            if side["config"]["model"] != protocol["model"]:
                raise ValueError("recorded source model differs")
            npz = path.with_suffix(".npz")
            with zipfile.ZipFile(npz) as archive, archive.open("hidden_states.npy") as stream:
                version = np.lib.format.read_magic(stream)
                reader = {(1,0):np.lib.format.read_array_header_1_0,(2,0):np.lib.format.read_array_header_2_0}[version]
                shape = reader(stream)[0]
            assert shape == (side["n_generated_tokens"],28,2048)
            with np.load(npz,allow_pickle=False) as archive:
                generated = archive["token_ids"].tolist()
            assert generated == [t["token_id"] for t in side["tokens"]]
            prompt = tokenizer(side["chat_template_input"],add_special_tokens=False)["input_ids"]
            assert len(prompt) == side["extra"]["prompt_tokens"]
            markers = [i for i,token in enumerate(generated) if token in r6.MARKER_IDS]
            sampled = r6.sample_markers(markers,len(generated))
            valid = [t for t in sampled if 0 < t and len(prompt)+t <= rules["max_prefix_tokens"]][:2]
            if not valid:
                exclusions.append({"trajectory":tid,"reason":"no original sampled marker within prefix bound","sampled":sampled})
            for t in valid:
                rows.append({"id":f"{tid}_t{t}","problem_id":f"aime25_p{index:02d}","split":"transfer", "kind":"aime",
                             "mode":mode,"wording":"recorded","t":t,"marker_id":generated[t],
                             "prefix_ids":prompt+generated[:t],"groups":[r6.MARKER_IDS,[r6.CONTROL_ID]],
                             "sidecar_sha256":sha(path),"source_model":side["config"]["model"]})
    return rows,exclusions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model",type=Path,required=True)
    parser.add_argument("--vector",type=Path,required=True)
    parser.add_argument("--protocol",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--gpu-uuid",required=True)
    parser.add_argument("--aime-root",type=Path,required=True)
    parser.add_argument("--r6-source",type=Path,required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("a completed result must never be overwritten")
    protocol = read(args.protocol)
    assert protocol["schema"] == "steer3d.neuron_mediation_protocol/1"
    assert sha(args.vector) == protocol["vector_sha256"]
    assert set(protocol["discovery_problem_indices"]).isdisjoint(protocol["evaluation_problem_indices"])
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_uuid
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    def require_idle_gpu():
        values = subprocess.check_output(["nvidia-smi","--id="+args.gpu_uuid,
            "--query-gpu=memory.used,memory.free,utilization.gpu","--format=csv,noheader,nounits"],text=True)
        used,free,util = [int(v.strip()) for v in values.strip().split(",")]
        if used > 1024 or free < 24000 or util > 10:
            raise RuntimeError("selected GPU no longer idle; do not contend with existing jobs")
    require_idle_gpu()
    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModelForCausalLM
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    torch.use_deterministic_algorithms(True)
    tokenizer = AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(args.model,local_files_only=True,
        dtype=torch.float32,attn_implementation="eager")
    require_idle_gpu()
    model = model.to("cuda:0").eval()
    assert len(model.model.layers) == 28 and model.config.hidden_act == "silu"
    layer = protocol["injection_block"]
    vector = np.load(args.vector,allow_pickle=False).astype(np.float32)
    assert vector.shape == (model.config.hidden_size,) and np.isfinite(vector).all()
    assert abs(float(np.linalg.norm(vector))-1) < 1e-5
    directions = {"w+":vector,"w-":-vector}
    rng = np.random.default_rng(protocol["seed"])
    for i in range(protocol["random_directions"]):
        value = rng.standard_normal(len(vector)).astype(np.float32)
        directions[f"random{i}"] = value/np.linalg.norm(value)
    answer_ids = {}
    for label,surfaces in protocol["answer_surfaces"].items():
        answer_ids[label] = sorted({tokenizer.encode(s,add_special_tokens=False)[0] for s in surfaces
                                   if len(tokenizer.encode(s,add_special_tokens=False)) == 1})
        if len(answer_ids[label]) != len(surfaces):
            raise ValueError("answer surfaces must be distinct one-token continuations")
    assert set(answer_ids["A"]).isdisjoint(answer_ids["B"])
    cases = problem_specs(protocol)
    for case in cases:
        case["prefix_ids"] = tokenizer.apply_chat_template(case.pop("messages"),tokenize=True,
            add_generation_prompt=True,enable_thinking=False)
        case["groups"] = [answer_ids[case["answer"]],answer_ids["B" if case["answer"] == "A" else "A"]]
    transfer,excluded = aime_specs(args.aime_root,protocol,tokenizer,args.r6_source)
    columns = {i:model.model.layers[i].mlp.down_proj.weight.detach().float().norm(dim=0).cpu().numpy()
               for i in range(layer,len(model.model.layers))}
    result = {"schema":"steer3d.neuron_mediation/1","complete":False,"protocol":protocol,
        "protocol_sha256":sha(args.protocol),"vector_sha256":sha(args.vector),
        "source_sha256":{str(p.name):sha(p) for p in (Path(__file__),Path(__file__).parents[1]/"core/neuron_mediation.py",args.r6_source)},
        "model_config_sha256":sha(args.model/"config.json"),"model":str(args.model),
        "torch":torch.__version__,"transformers":transformers.__version__,"gpu_uuid":args.gpu_uuid,
        "dtype":"float32","attention":"eager","tf32":False,
        "answer_ids":answer_ids,"excluded_aime":excluded,"cases":[],"guards":{}}
    started = time.time()
    cached = {}

    def forward(case,name="baseline",alpha=0,patches=None,collect=False):
        ids = torch.tensor([case["prefix_ids"]],device="cuda:0",dtype=torch.long)
        return native_forward(model,ids,injection_layer=layer,vector=directions.get(name),alpha=alpha,
            patches=patches,collect=collect,max_control_scale=protocol["max_control_scale"],
            control_norm_rtol=protocol["control_norm_rtol"])

    def measure(case,full=True):
        base = forward(case,collect=True)
        alpha = protocol["primary_strength"]*base["input_norm"]
        primary = forward(case,"w+",alpha,collect=True)
        base_read = outcome(base["logits"],case["groups"],case["kind"])
        payload = {k:v for k,v in case.items() if k not in ("prefix_ids","groups")}
        payload.update({"n_prefix_tokens":len(case["prefix_ids"]),
            "prefix_sha256":hashlib.sha256(np.asarray(case["prefix_ids"],dtype="<i8").tobytes()).hexdigest(),
            "prefix_tail":tokenizer.decode(case["prefix_ids"][-64:]),"baseline":base_read,
            "input_norm":base["input_norm"],"primary_alpha":alpha,"responses":[]})
        for name in directions:
            strengths = protocol["strengths"] if full and name in ("w+","w-") else [protocol["primary_strength"]]
            if not full and name.startswith("random"):
                continue
            for strength in strengths:
                data = primary if name == "w+" and strength == protocol["primary_strength"] else forward(case,name,strength*base["input_norm"])
                readout = outcome(data["logits"],case["groups"],case["kind"])
                payload["responses"].append({"direction":name,"strength":strength,"alpha":strength*base["input_norm"],
                    "readout":readout,"delta_score":readout["score"]-base_read["score"]})
        payload["regimes"] = {str(i):{
            name:np.bincount(sign_regimes(capture[i]["effective_gate"],capture[i]["value"]),minlength=5).tolist()
            for name,capture in (("baseline",base["states"]),("steered",primary["states"]))} for i in columns}
        cached[case["id"]] = (case,base,primary,payload)
        return base,primary,payload

    for i,case in enumerate(cases):
        base,primary,payload = measure(case)
        if i == 0:
            ids = torch.tensor([case["prefix_ids"]],device="cuda:0",dtype=torch.long)
            with torch.inference_mode():
                plain = model(input_ids=ids,use_cache=False,return_dict=True).logits[0,-1].float().cpu().numpy()
            zero = forward(case,"w+",0)
            assert np.array_equal(plain,base["logits"]) and np.array_equal(zero["logits"],base["logits"])
            for name,source,alpha in (("baseline",base,0),("w+",primary,payload["primary_alpha"])):
                patches = {j:{"indices":list(range(len(row["product"]))),"donor":row["product"]} for j,row in source["states"].items()}
                identity = forward(case,name,alpha,patches)
                assert np.array_equal(identity["logits"],source["logits"])
            result["guards"].update({"unhooked_equals_captured_baseline":True,"zero_vector_identity":True,
                                     "baseline_and_steered_identity_donor_patches":True})
        print(f"NATIVE {i+1}/{len(cases)} {case['id']}",flush=True)
    discovery = [(base["states"],primary["states"]) for case,base,primary,_ in cached.values() if case["split"] == "discovery"]
    selected,scores,profiles = select_units(discovery,columns,protocol["units_per_layer"])
    random_groups,matching = matched_random_groups(selected,profiles,columns,protocol["random_groups"],protocol["seed"])
    result["selection"] = {"groups":selected,"random_groups":random_groups,"matching":matching,
        "discovery_case_ids":[c["id"] for c in cases if c["split"] == "discovery"],
        "evaluation_problem_ids":sorted({c["problem_id"] for c in cases if c["split"] == "evaluation"}),
        "units":[{"layer":j,"unit":unit,"score":float(scores[j][unit]),"baseline_magnitude":float(profiles[j][unit]),
                  "column_norm":float(columns[j][unit])} for j,ids in selected.items() for unit in ids]}
    stats = {f"{key}_{j}":value for key,group in (("score",scores),("baseline",profiles),("column_norm",columns)) for j,value in group.items()}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.out.with_suffix(".selection.npz"),**stats)
    result["selection_statistics_sha256"] = sha(args.out.with_suffix(".selection.npz"))

    def mediate(case,base,steered,payload,individual):
        def patch_run(group,kind,targets=None):
            source = base if kind == "block" else steered
            name,alpha = ("w+",payload["primary_alpha"]) if kind == "block" else ("baseline",0)
            patches = {j:{"indices":ids,"donor":source["states"][j]["product"],
                          **({"target_write_norm":targets[j]["applied_write_norm"]} if targets is not None else {})}
                       for j,ids in group.items()}
            arm = forward(case,name,alpha,patches)
            arm_read = outcome(arm["logits"],case["groups"],case["kind"])
            reference = next(r["readout"] for r in payload["responses"] if r["direction"] == "w+" and r["strength"] == protocol["primary_strength"]) if kind == "block" else payload["baseline"]
            return {"kind":kind,"readout":arm_read,"effect":reference["score"]-arm_read["score"] if kind == "block" else arm_read["score"]-reference["score"],"writes":arm["writes"]}
        payload["mediation"] = {}
        for kind in ("block","restore"):
            main = patch_run(selected,kind)
            payload["mediation"]["joint_"+kind] = main
            for r,group in enumerate(random_groups):
                payload["mediation"][f"random{r}_{kind}"] = patch_run(group,kind,main["writes"])
            if individual:
                for j,ids in selected.items():
                    payload["mediation"][f"layer{j}_{kind}"] = patch_run({j:ids},kind)

    evaluation = [c for c in cases if c["split"] == "evaluation"]
    for i,case in enumerate(evaluation):
        _,base,primary,payload = cached[case["id"]]
        mediate(case,base,primary,payload,True)
        print(f"MEDIATION {i+1}/{len(evaluation)} {case['id']}",flush=True)
    for i,case in enumerate(transfer):
        base,primary,payload = measure(case,False)
        mediate(case,base,primary,payload,False)
        print(f"TRANSFER {i+1}/{len(transfer)} {case['id']}",flush=True)
    for case,base,primary,payload in cached.values():
        payload["selected_native_units"] = {str(j):{"indices":ids,**{
            name+"_"+key:capture["states"][j][key][ids].tolist()
            for name,capture in (("baseline",base),("steered",primary)) for key in ("gate","effective_gate","value","product")}}
            for j,ids in selected.items()}
        result["cases"].append(payload)
    result["guards"].update({"native_product_reconstruction":True,"random_control_norm_matching":True,
        "all_fixed_synthetic_cases":len(cases)==48,"discovery_evaluation_disjoint":True})
    result.update({"complete":True,"elapsed_seconds":time.time()-started})
    pending = args.out.with_suffix(".pending")
    pending.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(",",":")),encoding="utf-8")
    pending.replace(args.out)
    print(f"ALLDONE cases={len(result['cases'])} bytes={args.out.stat().st_size}",flush=True)


if __name__ == "__main__":
    main()
