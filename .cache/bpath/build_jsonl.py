"""构造 B 路题库：远端 parquet(aime25/aime26) -> 采集脚本可吃的 JSONL。

三条处理，全部取数前写死：
  P1 剥尾：题面尾部统一带一句 "Let's think step by step and output the final
     answer within \\boxed{}."，而现有 48 条的 user turn 是**裸题面**。
     不剥 => 新旧 prompt 不同构，跨批次比较无效。60/60 尾句完全一致（已验）。
  P2 改 id：内置 2025_I_1 与 parquet 2025_I_1 是**两道不同的题**，
     直接用 parquet 的 index 会生成 `aime__2025__2025_I_1__think.npz`
     与现有文件**同名但内容不同**。故 split=aime25/aime26, id=p00..p30，
     文件名变成 aime__aime25__p00__think，结构性不可能撞车。
  P3 索引基准：aime25 是 0-based(0..29)，aime26 是 1-based(1..30)。
     统一补零成两位（p00..p29 / p01..p30），并在 manifest 里记下原值。
"""
import hashlib
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
GUIDE = "Let's think step by step and output the final answer within \\boxed{}."

raw = (BASE / "dump_raw.txt").read_text(encoding="utf-8")
dump = json.loads(raw.split("DUMP_JSON_BEGIN", 1)[1].rsplit("DUMP_JSON_END", 1)[0].strip())
builtin = json.loads((BASE / "builtin24.json").read_text(encoding="utf-8"))

# ---------- 反向依赖检查：剥尾必须真的剥掉东西 ----------
built_ends_with_guide = sum(1 for p in builtin if p["problem"].rstrip().endswith(GUIDE))
assert built_ends_with_guide == 0, "现有 48 条的题面竟带引导句 => 前提错，停下"

problems, manifest = [], []
for src in ("aime25", "aime26"):
    recs = dump[src]["records"]
    for r in recs:
        q = r["question"]
        assert q.endswith(GUIDE), f"{src} 尾句不匹配，剥尾前提不成立: {q[-60:]!r}"
        core = q[: -len(GUIDE)]
        assert core != q
        pid = f"p{int(r['index_in_year']):02d}"
        tid = f"aime__{src}__{pid}"
        assert tid not in {m["traj_prefix"] for m in manifest}, "id 撞车"
        problems.append({
            "id": pid,
            "split": src,
            "problem": core.strip(),
            "answer": str(r["answer"]).strip(),
        })
        manifest.append({
            "traj_prefix": tid,
            "source": src,
            "year": r["year"],
            "orig_index_in_year": r["index_in_year"],
            "index_base": "0-based" if min(x["index_in_year"] for x in recs) == 0 else "1-based",
            "new_id": pid,
            "answer": str(r["answer"]).strip(),
            "n_chars_after_strip": len(core.strip()),
            "q_sha256_12": hashlib.sha256(core.strip().encode()).hexdigest()[:12],
        })

assert len(problems) == 60, len(problems)
assert len({m["q_sha256_12"] for m in manifest}) == 60, "剥尾后题面出现重复"

jl = BASE / "problems_bpath60.jsonl"
with open(jl, "w", encoding="utf-8") as f:
    for p in problems:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

(BASE / "problems_bpath60_manifest.json").write_text(
    json.dumps({"guide_stripped": GUIDE, "n": len(problems), "rows": manifest},
               ensure_ascii=False, indent=1), encoding="utf-8")

print(f"写出 {jl}  n={len(problems)}")
print(f"写出 {BASE/'problems_bpath60_manifest.json'}")
print(f"jsonl 行数校验: {sum(1 for _ in open(jl, encoding='utf-8'))}")
print(f"去重后题面唯一: {len({m['q_sha256_12'] for m in manifest})}/60")
print("\n前 3 条:")
for p in problems[:3]:
    print(f"  {p['split']}/{p['id']} ans={p['answer']:>4s} | {p['problem'][:66]}...")