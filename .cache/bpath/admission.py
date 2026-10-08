"""扩源前的准入检查：尾句一致性、答案格式、题面可读性。

判决规则取数前写死：
  T1 尾句统一：60 题必须都以同一句英文引导句结尾（否则「剥尾」不成立）
  T2 答案格式：全部答案可被 parse_aime_answer 接受，且落在 [0,999]
  T3 题面非空且长度合理（> 40 字符），无截断迹象
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
sys.path.insert(0, str(REPO / "backend"))
from core.aime_loader import parse_aime_answer  # noqa: E402

raw = (BASE / "dump_raw.txt").read_text(encoding="utf-8")
dump = json.loads(raw.split("DUMP_JSON_BEGIN", 1)[1].rsplit("DUMP_JSON_END", 1)[0].strip())

GUIDE = "Let's think step by step and output the final answer within \\boxed{}."
rows = []
for name in ("aime25", "aime26"):
    for r in dump[name]["records"]:
        rows.append({"src": name, "year": r["year"], "idx": r["index_in_year"],
                     "question": r["question"], "answer": r["answer"]})

print("=" * 72)
print("T1  尾句统一性（决定能否统一剥尾）")
print("=" * 72)
ends = Counter()
for r in rows:
    q = r["question"]
    ends[q[-len(GUIDE):] if q.endswith(GUIDE) else "<不匹配 GUIDE>"] += 1
for k, v in ends.items():
    print(f"  {v:3d} 条  尾句 = {k!r}")
t1 = len(ends) == 1 and ends.get(GUIDE) == len(rows)
print(f"  -> T1 {'PASS' if t1 else 'FAIL'}：{len(rows)} 题尾句是否完全一致且等于 GUIDE")

print()
print("=" * 72)
print("T2  答案格式")
print("=" * 72)
bad = []
for r in rows:
    v = parse_aime_answer(r["answer"])
    if v is None:
        bad.append((r["year"], r["idx"], r["answer"], "parse 返回 None"))
        continue
    try:
        iv = int(v)
    except (TypeError, ValueError):
        bad.append((r["year"], r["idx"], r["answer"], f"parse={v!r} 非整数"))
        continue
    if not (0 <= iv <= 999):
        bad.append((r["year"], r["idx"], r["answer"], f"parse={iv} 越界"))
print(f"  解析失败/越界: {len(bad)}")
for b in bad[:10]:
    print("   ", b)
ans_ty = Counter(type(r["answer"]).__name__ for r in rows)
print(f"  answer 列类型分布: {dict(ans_ty)}")
t2 = len(bad) == 0
print(f"  -> T2 {'PASS' if t2 else 'FAIL'}")

print()
print("=" * 72)
print("T3  题面长度")
print("=" * 72)
L = [len(r["question"]) for r in rows]
print(f"  min={min(L)} 中位={sorted(L)[len(L)//2]} max={max(L)}")
short = [f"{r['year']}_I_{r['idx']}" for r in rows if len(r["question"]) <= 40]
print(f"  过短(<=40): {short}")
noend = [f"{r['year']}_I_{r['idx']}" for r in rows if r["question"].rstrip()[-1] not in ".?}$"]
print("  疑似截断(不以 . ? } $ 收尾):", noend)
t3 = not short and not noend
print(f"  -> T3 {'PASS' if t3 else 'FAIL'}")

print()
print("=" * 72)
print("剥尾后的 user turn 可比性抽样（是否与现有 48 条同构）")
print("=" * 72)
sample = [r for r in rows if r["src"] == "aime26"][:2]
for r in sample:
    core = r["question"][: -len(GUIDE)] if r["question"].endswith(GUIDE) else r["question"]
    print(f"--- {r['year']}_I_{r['idx']} (剥尾后 {len(core)} 字) ---")
    print(core[:260].replace("\n", " "))
    print()

print("=" * 72)
print(f"总裁决: T1={t1} T2={t2} T3={t3}  -> "
      f"{'全部通过，可进入生成' if (t1 and t2 and t3) else '有红，需处置'}")
json.dump({"t1": t1, "t2": t2, "t3": t3, "guide": GUIDE,
           "bad_answers": bad, "short": short, "truncated": noend},
          open(BASE / "source_admission.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("写出", BASE / "source_admission.json")