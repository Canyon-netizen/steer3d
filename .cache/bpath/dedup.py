"""查重：远端 parquet(aime25/aime26) vs 内置 24 题 vs 已生成 48 条轨迹的题面。

只读本地 .cache/bpath/ 下的产物，不碰生成脚本。
"""
import json
import re
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent
raw = (BASE / "dump_raw.txt").read_text(encoding="utf-8")
blob = raw.split("DUMP_JSON_BEGIN", 1)[1].rsplit("DUMP_JSON_END", 1)[0].strip()
dump = json.loads(blob)
builtin = json.loads((BASE / "builtin24.json").read_text(encoding="utf-8"))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def ans_key(a) -> str:
    return re.sub(r"[^0-9]", "", str(a))


# 已生成过的题：文件名形如 aime__<year>__<problem_id>__<mode>.npz
REPO = BASE.parent.parent
gen_ids = set()
gen_counts = {}
for ds in ("aime_qwen3_1p7b_16k_fp16", "aime_qwen3_1p7b_32k_fp32"):
    d = REPO / "datasets" / ds / "aime"
    if not d.exists():
        continue
    ids = {p.name.split("__")[2] for p in d.glob("*.npz")}
    gen_counts[ds] = {"npz": len(list(d.glob("*.npz"))), "questions": len(ids)}
    gen_ids |= ids
report_gen = gen_counts
print("已生成:", gen_counts, "| 题目并集", len(gen_ids))

built_by_norm = {}
for p in builtin:
    built_by_norm[norm(p["problem"])] = p["id"]

report = {"sources": {}, "overlap_with_builtin": {}}

for name in ("aime25", "aime26"):
    recs = dump[name]["records"]
    src = {
        "n": len(recs),
        "years": sorted({r["year"] for r in recs}),
        "new_ids": [],
        "dup_of_builtin": [],
        "ans_conflict": [],
        "already_generated": [],
    }
    for r in recs:
        rid = f"{r['year']}_I_{r['index_in_year']}"
        item = {"id": rid, "answer": r["answer"], "q_head": r["question"][:70].replace("\n", " ")}
        hit = built_by_norm.get(norm(r["question"]))
        if hit:
            item["same_as"] = hit
            src["dup_of_builtin"].append(item)
            b = next(x for x in builtin if x["id"] == hit)
            if ans_key(b["answer"]) != ans_key(r["answer"]):
                item["builtin_answer"] = b["answer"]
                src["ans_conflict"].append(item)
        else:
            src["new_ids"].append(item)
        if rid in gen_ids:
            src["already_generated"].append(rid)
    report["overlap_with_builtin"][name] = src
    print(f"\n=== {name}: {src['n']} 题, year={src['years']}")
    print(f"  与内置 24 题重复: {len(src['dup_of_builtin'])}  -> {[d['id'] for d in src['dup_of_builtin']]}")
    print(f"  答案冲突: {len(src['ans_conflict'])}")
    print(f"  真新增: {len(src['new_ids'])} -> {[d['id'] for d in src['new_ids']]}")
    print(f"  已生成过: {len(src['already_generated'])}")

# 三方题目集合并集
all_new = []
for name in ("aime25", "aime26"):
    all_new += report["overlap_with_builtin"][name]["new_ids"]
print("\n两 parquet 去重后真新增合计:", len(all_new))
print("与内置 24 题并集后总题数:", len(builtin) + len(all_new))

(BASE / "dedup_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("\n写出", BASE / "dedup_report.json")