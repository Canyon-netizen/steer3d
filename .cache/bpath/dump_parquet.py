"""只读导出远端题源，供本地查重。不写远端工作树。"""
import json
import os

import pandas as pd

ROOT = "/home/zhourui/steer3d"
out = {}

for name in ("aime25", "aime26"):
    p = os.path.join(ROOT, "data", name, "test.parquet")
    df = pd.read_parquet(p)
    out[name] = {
        "path": p,
        "n_rows": int(len(df)),
        "columns": list(df.columns),
        "records": json.loads(df.to_json(orient="records", force_ascii=False)),
    }
    print(name, len(df), list(df.columns))

pj = os.path.join(ROOT, "data", "problem_index_47.json")
if os.path.exists(pj):
    with open(pj, encoding="utf-8") as f:
        arr = json.load(f)
    out["problem_index_47"] = {"path": pj, "n": len(arr), "sample_keys": list(arr[0].keys()) if arr else []}
    print("problem_index_47", len(arr), list(arr[0].keys()) if arr else [])

pl = os.path.join(ROOT, "data", "problems_paired.jsonl")
if os.path.exists(pl):
    rows = []
    with open(pl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    out["problems_paired"] = {"path": pl, "n": len(rows), "records": rows}
    print("problems_paired", len(rows), list(rows[0].keys()) if rows else [])

print("DUMP_JSON_BEGIN")
print(json.dumps(out, ensure_ascii=False))
print("DUMP_JSON_END")