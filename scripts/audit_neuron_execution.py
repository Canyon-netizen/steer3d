"""Replay native-unit selection and verify the executed source/artifact identities."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from backend.core.neuron_mediation import matched_random_groups


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root):
    data = json.loads((root/"native_mediation_v1.json").read_bytes())
    protocol = data["protocol"]
    assert data["complete"] and int((root/"run.exit").read_text()) == 0
    assert sha(root/"config.json") == data["model_config_sha256"]
    assert sha(REPO/"experiments/neuron_mediation_v1/protocol.json") == data["protocol_sha256"]
    source_paths = {"run_neuron_mediation.py":REPO/"backend/examples/run_neuron_mediation.py",
                    "neuron_mediation.py":REPO/"backend/core/neuron_mediation.py",
                    "original_r6.py":REPO/".cache/bpath/results_B/r6_rerun.py"}
    for name,path in source_paths.items():
        assert sha(path) == data["source_sha256"][name]
    assert sha(REPO/".cache/bpath/results_B/w_L19_m0.npy") == data["vector_sha256"] == protocol["vector_sha256"]
    assert sha(root/"native_mediation_v1.selection.npz") == data["selection_statistics_sha256"]
    selected = {int(k):v for k,v in data["selection"]["groups"].items()}
    profiles,columns,shapes = {},{},{}
    with np.load(root/"native_mediation_v1.selection.npz",allow_pickle=False) as archive:
        assert set(archive.files) == {f"{key}_{j}" for key in ("score","baseline","column_norm") for j in selected}
        for layer,ids in selected.items():
            score,baseline,norm = [archive[f"{key}_{layer}"] for key in ("score","baseline","column_norm")]
            assert score.ndim == 1 and score.shape == baseline.shape == norm.shape
            assert all(np.isfinite(a).all() and np.min(a) >= 0 for a in (score,baseline,norm))
            expected = sorted(np.lexsort((np.arange(len(score)),-score))[:protocol["units_per_layer"]].tolist())
            assert ids == expected
            profiles[layer],columns[layer],shapes[layer] = baseline,norm,list(score.shape)
            records = [r for r in data["selection"]["units"] if r["layer"] == layer]
            assert len(records) == len(ids) and {r["unit"] for r in records} == set(ids)
            for row in records:
                unit = row["unit"]
                assert row["score"] == float(score[unit])
                assert row["baseline_magnitude"] == float(baseline[unit])
                assert row["column_norm"] == float(norm[unit])
        groups,matching = matched_random_groups(selected,profiles,columns,protocol["random_groups"],protocol["seed"])
        assert json.loads(json.dumps(groups)) == data["selection"]["random_groups"]
        assert json.loads(json.dumps(matching)) == data["selection"]["matching"]
    discovery = [r["id"] for r in data["cases"] if r["split"] == "discovery"]
    assert len(discovery) == len(data["selection"]["discovery_case_ids"])
    assert set(discovery) == set(data["selection"]["discovery_case_ids"])
    writes = [w for row in data["cases"] if "mediation" in row
              for name,arm in row["mediation"].items() if name.startswith("random") for w in arm["writes"].values()]
    errors = [abs(w["applied_write_norm"]-w["target_write_norm"])/max(w["target_write_norm"],1e-12) for w in writes]
    assert max(errors) <= protocol["control_norm_rtol"]
    assert max(w["scale"] for w in writes) <= protocol["max_control_scale"]
    return {"passed":True,"model_config_sha256":data["model_config_sha256"],
        "execution_source_sha256":data["source_sha256"],"vector_sha256":data["vector_sha256"],
        "selection_statistics_sha256":data["selection_statistics_sha256"],
        "selection_rule_replayed":True,"random_groups_and_matching_replayed":True,
        "discovery_case_ids_verified":True,"unit_statistics_shapes":shapes,
        "n_selected_units":sum(map(len,selected.values())),
        "matching_fallbacks":sum(x["fallback"] for r in matching for x in r.values()),
        "control_write_checks":len(writes),"max_relative_write_norm_error":max(errors),
        "max_control_scale":max(w["scale"] for w in writes),"measurement_seconds":data["elapsed_seconds"],
        "exit_code":0,"audit_code_sha256":sha(__file__)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",type=Path,default=REPO/"experiments/neuron_mediation_v1/results")
    args = parser.parse_args()
    result = audit(args.results)
    (args.results/"execution_audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
