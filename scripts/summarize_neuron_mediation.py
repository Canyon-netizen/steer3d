"""Audit all fixed cells before reporting native-unit and intervention results."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np


def per_problem(rows, value):
    groups = defaultdict(list)
    for row in rows:
        groups[row["problem_id"]].append(float(value(row)))
    return {key:float(np.mean(v)) for key,v in sorted(groups.items())}


def description(values):
    v = list(values.values())
    return {"n_problems":len(v),"mean":float(np.mean(v)) if v else None,
            "min":min(v) if v else None,"max":max(v) if v else None,"per_problem":values}


def audit_transfer_sources(data, manifest):
    """Check the complete transfer grid against an independently derived source list."""
    assert manifest["schema"] == "steer3d.neuron_transfer_source_manifest/1"
    assert manifest["protocol_sha256"] == data["protocol_sha256"]
    assert manifest["r6_source_sha256"] == data["source_sha256"]["original_r6.py"]
    rules = data["protocol"]["aime_transfer"]
    expected_trajectories = {f"aime__aime25__p{i:02d}__{mode}"
                            for i in rules["problem_indices"] for mode in rules["modes"]}
    trajectories = manifest["trajectories"]
    assert len(trajectories) == len(expected_trajectories)
    assert {r["trajectory"] for r in trajectories} == expected_trajectories
    expected = {}
    for trajectory in trajectories:
        valid = [t for t in trajectory["original_sampled_markers"]
                 if 0 < t and trajectory["prompt_tokens"]+t <= rules["max_prefix_tokens"]]
        assert trajectory["eligible_markers"] == valid
        assert [r["t"] for r in trajectory["selected_sites"]] == valid[:2]
        assert trajectory["missing_slots"] == 2-len(valid[:2])
        for site in trajectory["selected_sites"]:
            assert site["id"] == f"{trajectory['trajectory']}_t{site['t']}"
            expected[site["id"]] = (trajectory,site)
    actual = [r for r in data["cases"] if r["kind"] == "aime"]
    assert len(actual) == len(expected) == manifest["n_expected_sites"]
    assert {r["id"] for r in actual} == set(expected)
    for row in actual:
        trajectory,site = expected[row["id"]]
        assert row["split"] == "transfer"
        assert row["problem_id"] == trajectory["problem_id"] and row["mode"] == trajectory["mode"]
        assert row["sidecar_sha256"] == trajectory["sidecar_sha256"]
        for key in ("t","marker_id","n_prefix_tokens"):
            assert row[key] == site[key]
        assert row["n_prefix_tokens"] == trajectory["prompt_tokens"]+row["t"]
    excluded = data["excluded_aime"]
    empty = {r["trajectory"] for r in trajectories if not r["selected_sites"]}
    assert len(excluded) == len(empty) and {r["trajectory"] for r in excluded} == empty
    missing = sum(r["missing_slots"] for r in trajectories)
    assert missing == manifest["n_missing_slots"]
    return {"n_trajectories":len(trajectories),"n_expected_sites":len(expected),
            "n_measured_sites":len(actual),"n_missing_slots":missing,
            "missing_by_trajectory":{r["trajectory"]:r["missing_slots"] for r in trajectories if r["missing_slots"]}}


def summarize(data, protocol):
    if data.get("schema") != "steer3d.neuron_mediation/1" or not data.get("complete"):
        raise ValueError("only a completed native experiment can be summarized")
    assert data["protocol"] == protocol
    assert all(data["guards"].values())
    synthetic = [r for r in data["cases"] if r["kind"] == "equation"]
    assert len(synthetic) == 48 and len({r["id"] for r in synthetic}) == 48
    expected_grid = {(f"math{i:02d}",truth,wording) for i in range(len(protocol["multiplications"]))
                     for truth in (True,False) for wording in protocol["wording_prefixes"]}
    assert {(r["problem_id"],r["correct_equation"],r["wording"]) for r in synthetic} == expected_grid
    expected_discovery = {f"math{i:02d}" for i in protocol["discovery_problem_indices"]}
    assert {r["problem_id"] for r in synthetic if r["split"] == "discovery"} == expected_discovery
    expected_layers = set(range(protocol["injection_block"],28))
    selected = data["selection"]["groups"]
    assert {int(k) for k in selected} == expected_layers
    assert all(len(ids) == len(set(ids)) == protocol["units_per_layer"] for ids in selected.values())
    discovery = {r["problem_id"] for r in synthetic if r["split"] == "discovery"}
    evaluation = [r for r in synthetic if r["split"] == "evaluation"]
    assert len(evaluation) == 24 and len({r["problem_id"] for r in evaluation}) == 6
    assert discovery.isdisjoint({r["problem_id"] for r in evaluation})
    for problem in discovery|{r["problem_id"] for r in evaluation}:
        cells = [r for r in synthetic if r["problem_id"] == problem]
        assert {(r["correct_equation"],r["wording"]) for r in cells} == {
            (a,b) for a in (True,False) for b in protocol["wording_prefixes"]}
        assert all((r["a"]*r["b"] == r["stated_result"]) == r["correct_equation"] for r in cells)
    primary = protocol["primary_strength"]
    n_writes = 0
    for case in data["cases"]:
        assert case["primary_alpha"] == primary*case["input_norm"]
        for row in case["selected_native_units"].values():
            for world in ("baseline","steered"):
                gate, value, product = [np.asarray(row[world+"_"+key]) for key in ("effective_gate","value","product")]
                assert len(row["indices"]) == len(gate) == protocol["units_per_layer"]
                np.testing.assert_allclose(gate*value,product,rtol=8*np.finfo(np.float32).eps,atol=8*np.finfo(np.float32).eps)
        expected = {(name,s) for name in ("w+","w-") for s in (protocol["strengths"] if case["kind"] == "equation" else [primary])}
        if case["kind"] == "equation":
            expected |= {(f"random{i}",primary) for i in range(protocol["random_directions"])}
        assert {(r["direction"],r["strength"]) for r in case["responses"]} == expected
        assert len(case["responses"]) == len(expected)
        for response in case["responses"]:
            assert abs(response["delta_score"]-(response["readout"]["score"]-case["baseline"]["score"])) < 1e-10
        if case["split"] == "discovery":
            assert "mediation" not in case
            continue
        expected_patches = {f"joint_{kind}" for kind in ("block","restore")}
        expected_patches |= {f"random{i}_{kind}" for i in range(protocol["random_groups"]) for kind in ("block","restore")}
        if case["kind"] == "equation":
            expected_patches |= {f"layer{i}_{kind}" for i in expected_layers for kind in ("block","restore")}
        assert set(case["mediation"]) == expected_patches
        primary_score = next(r["readout"]["score"] for r in case["responses"] if r["direction"] == "w+" and r["strength"] == primary)
        for patch in case["mediation"].values():
            effect = primary_score-patch["readout"]["score"] if patch["kind"] == "block" else patch["readout"]["score"]-case["baseline"]["score"]
            assert abs(patch["effect"]-effect) < 1e-10
        for kind in ("block","restore"):
            main = case["mediation"]["joint_"+kind]
            assert {int(i) for i in main["writes"]} == expected_layers
            for r in range(protocol["random_groups"]):
                arm = case["mediation"][f"random{r}_{kind}"]
                assert set(arm["writes"]) == set(main["writes"])
                for layer,write in arm["writes"].items():
                    target = main["writes"][layer]["applied_write_norm"]
                    assert write["n_units"] == protocol["units_per_layer"]
                    assert write["target_write_norm"] == target
                    assert abs(write["applied_write_norm"]-target) <= protocol["control_norm_rtol"]*max(target,1e-12)
                    n_writes += 1
    result = {"complete":True,"n_synthetic":48,"n_evaluation_problems":6,"n_evaluation_cells":24,
              "n_transfer_cells":sum(r["kind"] == "aime" for r in data["cases"]),
              "matched_control_layer_checks":n_writes,"response":{},"mediation":{},"factorial":{}}
    def delta(row,name,strength):
        return next(r["delta_score"] for r in row["responses"] if r["direction"] == name and r["strength"] == strength)
    for name in ("w+","w-"):
        result["response"][name] = {str(s):description(per_problem(evaluation,lambda r:delta(r,name,s))) for s in protocol["strengths"]}
    result["response"]["random_primary"] = description(per_problem(evaluation,lambda r:np.mean([
        delta(r,f"random{i}",primary) for i in range(protocol["random_directions"])])))
    result["baseline"] = {"p_correct":float(np.mean([r["baseline"]["p_correct"] for r in evaluation])),
        "argmax_correct":sum(r["baseline"]["argmax_correct"] for r in evaluation),
        "argmax_outside":sum(r["baseline"]["argmax_outside_answer_set"] for r in evaluation),
        "mean_answer_set_coverage":float(np.mean([r["baseline"]["answer_set_coverage"] for r in evaluation]))}
    for key in evaluation[0]["mediation"]:
        result["mediation"][key] = description(per_problem(evaluation,lambda r:r["mediation"][key]["effect"]))
    for truth in (True,False):
        for wording in protocol["wording_prefixes"]:
            subset = [r for r in evaluation if r["correct_equation"] == truth and r["wording"] == wording]
            result["factorial"][f"{truth}_{wording}"] = description(per_problem(subset,lambda r:delta(r,"w+",primary)))
    transfer = [r for r in data["cases"] if r["kind"] == "aime"]
    result["transfer"] = {"total":description(per_problem(transfer,lambda r:delta(r,"w+",primary))),
        **{kind:description(per_problem(transfer,lambda r:r["mediation"]["joint_"+kind]["effect"])) for kind in ("block","restore")}}
    return result


def figures(data, summary, root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    strengths = data["protocol"]["strengths"]
    fig,axes = plt.subplots(1,2,figsize=(11,4),layout="constrained")
    for name,color in (("w+","#16876c"),("w-","#bd4550")):
        records = [summary["response"][name][str(s)] for s in strengths]
        axes[0].plot(strengths,[r["mean"] for r in records],"o-",label=name,color=color)
    axes[0].axhline(0,color="grey",lw=.7)
    axes[0].scatter([data["protocol"]["primary_strength"]],[summary["response"]["random_primary"]["mean"]],marker="x",color="black",label="4 random directions, mean")
    axes[0].set(xlabel="Strength / baseline input norm",ylabel="Change in correct-vs-wrong log odds",title="Held-out arithmetic: 6 equally weighted problems")
    axes[0].legend(fontsize=8)
    keys = ["joint_block","joint_restore"]
    for i,key in enumerate(keys):
        selected = summary["mediation"][key]
        axes[1].scatter([i-.12]*6,list(selected["per_problem"].values()),color="#16876c",alpha=.7,s=22)
        axes[1].scatter(i-.12,selected["mean"],marker="D",s=70,color="#095744")
        kind = key.split("_")[1]
        controls = [summary["mediation"][f"random{r}_{kind}"]["mean"] for r in range(data["protocol"]["random_groups"])]
        axes[1].scatter([i+.12]*len(controls),controls,color="#7e8399",marker="x",s=40)
    axes[1].axhline(0,color="grey",lw=.7)
    axes[1].set(xticks=[0,1],xticklabels=["Block","Restore"],ylabel="Conditional intervention effect (log odds)",title="Selected native units vs write-norm matched controls")
    axes[1].text(.02,.02,"Green dots: problems; diamond: mean\nGrey crosses: random-group means",transform=axes[1].transAxes,fontsize=8)
    fig.savefig(root/"mediation.png",dpi=170)
    plt.close(fig)
    fig,ax = plt.subplots(figsize=(8,3.8),layout="constrained")
    layers = list(range(data["protocol"]["injection_block"],28))
    for kind,color in (("block","#16876c"),("restore","#4a75b5")):
        ax.plot(layers,[summary["mediation"][f"layer{i}_{kind}"]["mean"] for i in layers],"o-",label=kind,color=color)
    ax.axhline(0,color="grey",lw=.7)
    ax.set(xlabel="Patched MLP block (one layer at a time)",ylabel="Conditional effect (log odds)",title="Held-out layer interventions; no additive mediation claim",xticks=layers)
    ax.legend()
    fig.savefig(root/"layers.png",dpi=170)
    plt.close(fig)


def unit_atlas(data):
    """Measured context examples, not global neuron names or causal unit scores."""
    atlas = []
    for layer,indices in data["selection"]["groups"].items():
        for offset,unit in enumerate(indices):
            observations = []
            for case in data["cases"]:
                native = case["selected_native_units"][layer]
                assert native["indices"][offset] == unit
                for world in ("baseline","steered"):
                    observations.append({"case_id":case["id"],"split":case["split"],"kind":case["kind"],"world":world,
                        "gate":native[world+"_gate"][offset],"effective_gate":native[world+"_effective_gate"][offset],
                        "value":native[world+"_value"][offset],"product":native[world+"_product"][offset],
                        "prefix_tail":case["prefix_tail"]})
            ordered = sorted(observations,key=lambda x:x["product"])
            atlas.append({"layer":int(layer),"unit":unit,"n_measured_worlds":len(observations),
                          "smallest_measured_products":ordered[:2],"largest_measured_products":ordered[-2:][::-1]})
    return {"scope":"Extremes among this fixed finite corpus and two worlds; not whole-corpus semantic labels. Causal tests target groups, not each individual unit.","units":atlas}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--protocol",type=Path,default=Path("experiments/neuron_mediation_v1/protocol.json"))
    parser.add_argument("--source-manifest",type=Path,default=Path("experiments/neuron_mediation_v1/source_manifest.json"))
    parser.add_argument("--out-dir",type=Path,required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    data = json.loads(raw)
    protocol_raw = args.protocol.read_bytes()
    assert hashlib.sha256(protocol_raw).hexdigest() == data["protocol_sha256"]
    summary = summarize(data,json.loads(protocol_raw))
    summary["transfer_source_audit"] = audit_transfer_sources(data,json.loads(args.source_manifest.read_bytes()))
    summary["source_manifest_sha256"] = hashlib.sha256(args.source_manifest.read_bytes()).hexdigest()
    summary["result_sha256"] = hashlib.sha256(raw).hexdigest()
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    (args.out_dir/"unit_atlas.json").write_text(json.dumps(unit_atlas(data),ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    figures(data,summary,args.out_dir)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("response","mediation","factorial")},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
