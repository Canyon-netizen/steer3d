"""审计已生成的 120 个 B 路轨迹；仅读取 NPZ 头与小型 token_ids。"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def shape(path, key):
    with zipfile.ZipFile(path) as archive, archive.open(key+".npy") as stream:
        version = np.lib.format.read_magic(stream)
        reader = {(1,0):np.lib.format.read_array_header_1_0,
                  (2,0):np.lib.format.read_array_header_2_0}[version]
        dimensions, _, _ = reader(stream)
        return list(dimensions)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--model",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    manifest = read(args.manifest)
    labels = read(args.root/"labels_full60.json")
    by_id = {row["traj"]:row for row in labels["rows"]}
    assert manifest["n"] == len(manifest["rows"]) == 60
    config = read(args.model/"config.json")
    assert config["hidden_size"] == 2048 and config["num_hidden_layers"] == 28
    rows, expected = [], set()
    for problem in manifest["rows"]:
        for mode in ("think","no_think"):
            tid = problem["traj_prefix"]+"__"+mode
            expected.add(tid)
            sidecar = read(args.root/"gen_b2/aime"/(tid+".json"))
            path = args.root/"gen_b2/aime"/(tid+".npz")
            assert sidecar["trajectory_id"] == tid
            assert sidecar["config"]["model"] == "Qwen/Qwen3-1.7B"
            assert sidecar["config"]["model_path"] == str(args.model)
            assert sidecar["config"]["mode"] == mode
            assert sidecar["config"]["max_new_tokens"] == 8192
            assert hashlib.sha256(sidecar["prompt"].encode()).hexdigest()[:12] == problem["q_sha256_12"]
            assert str(sidecar["ground_truth"]) == problem["answer"]
            n = sidecar["n_generated_tokens"]
            assert 0 < n <= 8192 and len(sidecar["tokens"]) == n
            assert shape(path,"hidden_states") == [n,28,2048]
            assert shape(path,"last_hidden") == [n,2048]
            with np.load(path) as archive:
                tokens = archive["token_ids"].tolist()
            assert tokens == [t["token_id"] for t in sidecar["tokens"]]
            label = by_id[tid]
            assert label["mode"] == mode and label["n_tok"] == n
            assert label["truncated"] == (n == 8192)
            rows.append({"id":tid,"mode":mode,"n_tok":n,"capped":n==8192,
                         "label":label["strict"],"shape":[n,28,2048],"checks_passed":True})
    assert expected == set(by_id) and labels["n"] == len(rows) == 120
    actual = {p.stem for p in (args.root/"gen_b2/aime").glob("*.npz")}
    assert actual == expected
    summary = {}
    for mode in ("think","no_think"):
        selected = [r for r in rows if r["mode"] == mode]
        summary[mode] = {"n":len(selected),"capped":sum(r["capped"] for r in selected),
                         "labels":dict(Counter(r["label"] for r in selected))}
    out = {"complete":True,"schema":"steer3d.bpath_completion_audit/1",
           "scope":"60 manifest problems, two modes, cap 8192; not all possible AIME years",
           "manifest_sha256":hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
           "labels_sha256":hashlib.sha256((args.root/"labels_full60.json").read_bytes()).hexdigest(),
           "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "model":str(args.model),"model_config_sha256":hashlib.sha256((args.model/"config.json").read_bytes()).hexdigest(),
           "summary":summary,"rows":rows}
    args.out.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    print("120/120 shape, token, prompt, model and label-coordinate checks passed.")


if __name__ == "__main__":
    main()
