"""加严查重：id 不可信（内置 2025_I_1 与 parquet 2025_I_1 是两道不同的题），
改用「题面 token 集合 Jaccard 近重复」判定，并审计两个已有数据集的完整性。
"""
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
raw = (BASE / "dump_raw.txt").read_text(encoding="utf-8")
blob = raw.split("DUMP_JSON_BEGIN", 1)[1].rsplit("DUMP_JSON_END", 1)[0].strip()
dump = json.loads(blob)
builtin = json.loads((BASE / "builtin24.json").read_text(encoding="utf-8"))

STOP = set("the a an of and or to in is are be for with that this it as on at by from find".split())


def toks(s: str):
    s = re.sub(r"\\[a-zA-Z]+", " ", s)  # 去掉 \sqrt \frac 等命令
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return {t for t in s.split() if t not in STOP}


def jac(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


built_toks = [(p["id"], toks(p["problem"])) for p in builtin]

print("=" * 70)
print("A) 近重复检查（内置 24 × parquet 60），只看 Jaccard >= 0.5 的对")
print("=" * 70)
hits = []
for name in ("aime25", "aime26"):
    for r in dump[name]["records"]:
        t = toks(r["question"])
        best = max(((jac(t, bt), bid) for bid, bt in built_toks), default=(0.0, None))
        if best[0] >= 0.5:
            hits.append((name, f"{r['year']}_I_{r['index_in_year']}", best[1], round(best[0], 3)))
print(f"Jaccard>=0.5 的近重复对: {len(hits)}")
for h in hits:
    print("  ", h)
mx = 0
for name in ("aime25", "aime26"):
    for r in dump[name]["records"]:
        t = toks(r["question"])
        mx = max(mx, max(jac(t, bt) for _, bt in built_toks))
print(f"全部 60 题 vs 内置 24 题的最大 Jaccard = {mx:.3f}  -> {'可能有重叠' if mx>=0.5 else '确认为两组不相交的题'}")

print()
print("=" * 70)
print("B) 索引基准核对（0-based 还是 1-based）")
print("=" * 70)
for name in ("aime25", "aime26"):
    idx = [r["index_in_year"] for r in dump[name]["records"]]
    print(f"{name}: min={min(idx)} max={max(idx)} n={len(idx)} -> "
          f"{'0-based' if min(idx)==0 else '1-based'}")

print()
print("=" * 70)
print("C) prompt 后缀核对：parquet 题面是否已含引导句")
print("=" * 70)
GUIDE = "let us think step by step"
for name in ("aime25", "aime26"):
    n_g = sum(1 for r in dump[name]["records"] if GUIDE in r["question"].lower())
    n_box = sum(1 for r in dump[name]["records"] if "boxed" in r["question"].lower())
    print(f"{name}: 含 think 引导句 {n_g}/{len(dump[name]['records'])}, 含 boxed {n_box}/30")
b_g = sum(1 for p in builtin if GUIDE in p["problem"].lower())
b_box = sum(1 for p in builtin if "boxed" in p["problem"].lower())
print(f"builtin: 含 think 引导句 {b_g}/24, 含 boxed {b_box}/24")

print()
print("=" * 70)
print("D) 已生成两个数据集的完整性（题 × 模式矩阵）")
print("=" * 70)
for ds in ("aime_qwen3_1p7b_16k_fp16", "aime_qwen3_1p7b_32k_fp32"):
    d = REPO / "datasets" / ds / "aime"
    mats = {}
    for p in d.glob("*.npz"):
        _, year, pid, mode = p.name[:-4].split("__")
        mats.setdefault(f"{year}__{pid}", set()).add(mode)
    modes = Counter()
    for v in mats.values():
        modes[tuple(sorted(v))] += 1
    full = modes.get(("no_think", "think"), 0)
    print(f"{ds}: 题数={len(mats)}  双模式齐={full}  仅单模式={len(mats)-full}")
    if len(mats) - full:
        odd = [k for k, v in mats.items() if v != {"no_think", "think"}]
        print(f"    缺模式: {odd[:8]}{' ...' if len(odd)>8 else ''}")

print()
print("=" * 70)
print("E) 扩源后可得的轨迹规模")
print("=" * 70)
cur_q = 24
new_q = 60
print(f"现有: {cur_q} 题 × 2 模式 = {cur_q*2} 条轨迹 (16k_fp16)")
print(f"新增: {new_q} 题 × 2 模式 = {new_q*2} 条轨迹 (aime25+aime26)")
print(f"合计: {cur_q+new_q} 题 = {(cur_q+new_q)*2} 条轨迹, 相对现在 x{(cur_q+new_q)/cur_q:.2f}")