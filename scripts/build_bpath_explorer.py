"""从原始 B 路产物构建交互数据，保留原 P9，不混合批次或向量。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def original_d4_bug(data):
    """历史实现原样保留，仅用于证实筛选后再判断会恒绿。"""
    def mono_up(values):
        return all(b >= a for a,b in zip(values,values[1:]))
    pos_ok = [t for t,r in data["traj"].items()
              if mono_up([statistics.median(r["curve"][f"w+@{d}"]) for d in data["dose"]])]
    return all(mono_up([statistics.median(data["traj"][t]["curve"][f"w+@{d}"])
                        for d in data["dose"]]) for t in pos_ok)


def audit_dose(data, expected_doses):
    if data["dose"] != expected_doses:
        raise ValueError("dose ladder differs from original executing code")
    def values(record, name):
        return [statistics.median(record["curve"][f"{name}@{d}"]) for d in expected_doses]
    controls = [r for r in data["traj"].values() if r["mode"] == "no_think"]
    up = lambda v: all(b >= a for a,b in zip(v,v[1:]))
    down = lambda v: all(b <= a for a,b in zip(v,v[1:]))
    return {"d3": bool(data["traj"]) and all(down(values(r,"w-")) for r in data["traj"].values()),
            "d4": len(controls) == 2 and all(up(values(r,"w+")) for r in controls),
            "d4_original_implementation": original_d4_bug(data),
            "d4_warning": "原实现先筛选已单调的轨迹再判单调，不能用于拒绝失败或缺失正控；本审计检查两条完整 no_think。"}


def selfcheck_d4(data, doses):
    clean = copy.deepcopy(data)
    for r in clean["traj"].values():
        for i,d in enumerate(doses):
            r["curve"][f"w+@{d}"] = [float(i)]
            r["curve"][f"w-@{d}"] = [-float(i)]
    assert audit_dose(clean,doses)["d4"] and original_d4_bug(clean)
    failed = copy.deepcopy(clean)
    control = next(r for r in failed["traj"].values() if r["mode"] == "no_think")
    control["curve"][f"w+@{doses[-1]}"] = [-100.0]
    assert original_d4_bug(failed) and not audit_dose(failed,doses)["d4"]
    missing = copy.deepcopy(clean)
    missing["traj"] = {t:r for t,r in missing["traj"].items() if r["mode"] != "no_think"}
    assert original_d4_bug(missing) and not audit_dose(missing,doses)["d4"]
    print("D4 selfcheck: clean passes; nonmonotone and missing controls rejected; original incorrectly passes both.")


def calibration_valid(cal, n_targets):
    fields = ("prediction","observed","residual","error_bound")
    if not all(len(cal[k]) == n_targets and all(math.isfinite(x) for x in cal[k]) for k in fields):
        return False
    return (cal["effective_delta_norm"] > 0 and any(abs(p) > 0 for p in cal["prediction"])
            and all(b >= 0 and abs(r) <= b and abs(o-p-r) < 1e-10
                    for p,o,r,b in zip(*(cal[k] for k in fields))))


def selfcheck_calibration(cal, n_targets):
    assert calibration_valid(cal,n_targets)
    wrong = copy.deepcopy(cal)
    wrong["prediction"] = [-p for p in cal["prediction"]]
    wrong["residual"] = [o-p for p,o in zip(wrong["prediction"],wrong["observed"])]
    assert not calibration_valid(wrong,n_targets), "wrong-sign calibration must be rejected"
    empty = copy.deepcopy(cal)
    for key in ("prediction","observed","residual","error_bound"):
        empty[key] = [0.0]*n_targets
    empty["effective_delta_norm"] = 0.0
    assert not calibration_valid(empty,n_targets), "zero intervention must not calibrate"
    print("Calibration selfcheck: measured response passes; wrong sign and zero intervention rejected.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(".cache/bpath/results_B"))
    parser.add_argument("--out", type=Path, default=Path("frontend/public/latent/data/bpath_explorer.json"))
    args = parser.parse_args()
    root = args.source
    r6 = module("builder_r6",root/"r6_rerun.py")
    dose_module = module("builder_dose",root/"dose_sweep.py")
    scan = read(root/"bpath_scan_B.json")
    if not scan["complete"] or scan["schema"] != "steer3d.bpath_scan/1":
        raise ValueError("scan not complete")
    assert scan["dose"] == dose_module.DOSE
    assert scan["marker_ids"] == r6.MARKER_IDS and scan["layer"] == r6.LAYER
    vector_hash = hashlib.sha256((root/"w_L19_m0.npy").read_bytes()).hexdigest()
    assert vector_hash == scan["vector_sha256"]
    assert scan["scan_script_sha256"] == hashlib.sha256((root.parent/"bpath_evidence_scan.py").read_bytes()).hexdigest()
    for name in ("r6_rerun.py","dose_sweep.py","layer_inject_sweep.py"):
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == scan["sources"][name]
    for trajectory in scan["trajectories"]:
        assert trajectory["positions"] == [s["t"] for s in trajectory["sites"]]
        for site in trajectory["sites"]:
            assert site["baseline_repeated_exact"]
            expected = {(name,d) for name in ("w+","w-","rand") for d in dose_module.DOSE}
            actual = {(v["direction"],v["rel"]) for v in site["variants"]}
            assert len(site["variants"]) == len(expected) and actual == expected
            for v in site["variants"]:
                assert set(v["projection"]) == set(scan["pca"])
            if site["layers"]:
                cal = next(row["calibration"] for row in site["layers"] if row["layer"] == -1)
                assert cal["ok"] and calibration_valid(cal,len(r6.MARKER_IDS)+1)
                selfcheck_calibration(cal,len(r6.MARKER_IDS)+1)
    frequency = read(root/"marker_freq5.json")
    arm_manifest = read(root/"w5.json")
    arm = next(name for name,path in arm_manifest.items() if Path(path).name == "w_L19_m0.npy")
    freq = frequency["rows"][arm]
    assert frequency["total_markers"] == sum(freq["freq"].values())
    scan["frequency"] = {"total": frequency["total_markers"], "rows": [
        {"id": tid, "dot": freq["dots"][str(tid)], "count": freq["freq"][str(tid)], "text": text}
        for tid,text in zip(scan["marker_ids"],scan["marker_text"])]}
    smoke = read(root/"r6_smoke_L19m0.json")
    modes = {t:v["mode"] for t,v in smoke["bench_v"].items()}
    verdict, ok = r6.p9_verdict(smoke["bench"],modes)
    assert ok == smoke["pos_ok"] and verdict == smoke["bench_v"]
    scan["original_p9"] = {"passed": sum(v["ok"] for v in verdict.values()), "total": len(verdict), "ok": ok}
    old_dose = read(root/"dose_sweep_B.json")
    selfcheck_d4(old_dose,dose_module.DOSE)
    scan["original_dose_audit"] = audit_dose(old_dose,dose_module.DOSE)
    norm = read(root/"bpath_norm_B.json")
    assert norm["schema"] == "steer3d.bpath_norm_transport/1" and norm["complete"]
    assert norm["vector_sha256"] == vector_hash
    assert norm["dose"] == scan["dose"] and norm["gap"] == scan["gap"] and norm["layer"] == scan["layer"]
    assert norm["script_sha256"] == hashlib.sha256((root.parent/"bpath_norm_transport.py").read_bytes()).hexdigest()
    assert len(norm["trajectories"]) == len(scan["trajectories"])
    for trajectory, record in zip(scan["trajectories"],norm["trajectories"]):
        site = trajectory["sites"][0]
        assert record["id"] == trajectory["id"] and record["t"] == site["t"]
        assert len(record["variants"]) == len(site["variants"])
        for old, new in zip(site["variants"],record["variants"]):
            assert (old["direction"],old["rel"]) == (new["direction"],new["rel"])
            assert new["norm_reconstruction_ok"]
            assert new["injected_delta_norm"] > 0 and new["pre_norm_delta_norm"] > 0
            for key in ("d_marker_lse","d_marker_logprob"):
                assert abs(old[key]-new[key]) < 1e-9, "norm scan changed the measured response"
        trajectory["norm_transport"] = record
    scan["norm_transport_metadata"] = {k:v for k,v in norm.items() if k != "trajectories"}
    scan["schema"] = "steer3d.bpath_explorer/1"
    scan["artifact_sources"] = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                               ("bpath_scan_B.json","bpath_norm_B.json","dose_sweep_B.json","marker_freq5.json","r6_smoke_L19m0.json")}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(scan,ensure_ascii=False,allow_nan=False,separators=(",",":")),encoding="utf-8")
    print(f"Built {args.out}: {len(scan['trajectories'])} trajectories, "
          f"{sum(len(t['sites']) for t in scan['trajectories'])} sites, "
          f"P9={scan['original_p9']['passed']}/{scan['original_p9']['total']} unchanged.")


if __name__ == "__main__":
    main()
