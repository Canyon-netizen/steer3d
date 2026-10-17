"""A complete fixed grid must pass; missing or misreported evidence must fail."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("native_audit",ROOT/"scripts/summarize_neuron_mediation.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
protocol = json.loads((ROOT/"experiments/neuron_mediation_v1/protocol.json").read_text())


def fixture():
    rows = []
    baseline = {"score":1.,"p_correct":.7,"answer_set_coverage":.9,"argmax_correct":True,"argmax_outside_answer_set":False}
    for i,((a,b),offset) in enumerate(zip(protocol["multiplications"],protocol["error_offsets"])):
        split = "discovery" if i < 6 else "evaluation"
        for truth in (True,False):
            for wording in protocol["wording_prefixes"]:
                row = {"id":f"{i}_{truth}_{wording}","problem_id":f"math{i:02d}","kind":"equation","split":split,
                       "a":a,"b":b,"stated_result":a*b if truth else a*b+offset,"correct_equation":truth,
                       "wording":wording,"baseline":baseline.copy(),"input_norm":10.,"primary_alpha":1.,"responses":[],
                       "selected_native_units":{}}
                for layer in range(20,28):
                    row["selected_native_units"][str(layer)] = {"indices":list(range(32)),
                        **{world+"_"+key:[1.]*32 for world in ("baseline","steered") for key in ("effective_gate","value","product")}}
                for name in ("w+","w-","random0","random1","random2","random3"):
                    for strength in protocol["strengths"] if name in ("w+","w-") else [.1]:
                        row["responses"].append({"direction":name,"strength":strength,"delta_score":.2,"readout":{"score":1.2}})
                if split == "evaluation":
                    row["mediation"] = {}
                    writes = {str(j):{"n_units":32,"applied_write_norm":1.,"target_write_norm":1.} for j in range(20,28)}
                    for kind in ("block","restore"):
                        for name in ("joint","random0","random1","random2","random3",*[f"layer{j}" for j in range(20,28)]):
                            row["mediation"][name+"_"+kind] = {"kind":kind,"readout":{"score":1.1},"effect":.1,"writes":copy.deepcopy(writes)}
                rows.append(row)
    return {"schema":"steer3d.neuron_mediation/1","complete":True,"protocol":protocol,"guards":{"verified":True},
            "selection":{"groups":{str(j):list(range(32)) for j in range(20,28)}},"cases":rows}


def test_complete_grid_has_problem_level_units_and_all_control_norm_checks():
    result = audit.summarize(fixture(),protocol)
    assert result["n_evaluation_problems"] == 6 and result["n_evaluation_cells"] == 24
    assert result["matched_control_layer_checks"] == 24*2*4*8
    assert result["mediation"]["joint_block"]["n_problems"] == 6


@pytest.mark.parametrize("mutation",["missing_cell","wrong_truth","wrong_effect","norm_mismatch","product_mismatch","leaked_split","missing_random"])
def test_corrupted_evidence_is_rejected(mutation):
    data = fixture()
    row = next(r for r in data["cases"] if r["split"] == "evaluation")
    if mutation == "missing_cell":
        data["cases"].pop()
    elif mutation == "wrong_truth":
        row["stated_result"] += 1
    elif mutation == "wrong_effect":
        row["mediation"]["joint_block"]["effect"] = -99.
    elif mutation == "norm_mismatch":
        row["mediation"]["random0_restore"]["writes"]["20"]["applied_write_norm"] = 5.
    elif mutation == "product_mismatch":
        row["selected_native_units"]["20"]["baseline_product"][0] = -8.
    elif mutation == "leaked_split":
        row["split"] = "discovery"
    else:
        del row["mediation"]["random3_block"]
    with pytest.raises((AssertionError,ValueError)):
        audit.summarize(data,protocol)
