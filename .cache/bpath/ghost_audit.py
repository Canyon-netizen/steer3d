"""查 D1 幽灵到底是不是幻觉：它们有没有写出自然语言形式的答案？

触发：cap=8192 的新数据里，p02 think 触顶、0 个 \\boxed{}、
is_correct=True、抽取答案 16 恰好等于 gt=16。若模型其实写了
"the answer is 16"，那它不是抽取器幻觉，而是我的严格规则过严。

判决规则（取数前写死）：
  E1 若文本里存在「答案陈述」——`\\boxed{}` 或 `answer is/equals/= N`
     或 `final answer ... N` —— 则标签**有效**，只是形式非规范。
  E2 若三者皆无，答案只是文本里恰好出现的某个整数 ⇒ 判为幻觉。
  E3 三条 D1 违例（1983 / 2020 / p02）逐条给出是哪一种。
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

PATS = {
    "boxed": re.compile(r"\\boxed\{([^}]*)\}"),
    "answer_is": re.compile(r"answer\s*(?:is|equals|=)\s*\$?\s*(-?\d+)", re.I),
    "final_answer": re.compile(r"(?:final\s+answer|answer)\s*[:=]?\s*\$?\s*(-?\d+)", re.I),
    "so_the": re.compile(r"so\s+the\s+answer\s+is\s+\$?\s*(-?\d+)", re.I),
}


def last_int(s: str):
    n = re.findall(r"-?\d+", s)
    return n[-1] if n else None


def audit(path: str) -> dict:
    j = json.load(open(path, encoding="utf-8"))
    t = j.get("generated_text") or ""
    gt = str(j.get("ground_truth", "")).strip()
    found = {k: [m.group(1) for m in p.finditer(t)] for k, p in PATS.items()}
    boxes = found["boxed"]
    # 依次取最可靠的答案陈述
    stated, source = None, None
    for k in ("boxed", "so_the", "answer_is", "final_answer"):
        if found[k]:
            stated = found[k][-1].strip()
            source = k
            break
    tail = t[-70:].replace("\n", "\\n")
    return {
        "traj": j.get("trajectory_id", Path(path).stem),
        "cap": j["config"]["max_new_tokens"],
        "n_tok": j["n_generated_tokens"],
        "truncated": j["n_generated_tokens"] >= j["config"]["max_new_tokens"],
        "gt": gt,
        "legacy_correct": bool(j["is_correct"]),
        "legacy_answer": str(j.get("generated_answer")),
        "n_boxed": len(boxes),
        "n_answer_is": len(found["answer_is"]),
        "n_final": len(found["final_answer"]),
        "n_so_the": len(found["so_the"]),
        "stated_answer": stated,
        "stated_source": source,
        "stated_is_gt": (stated is not None and stated.lstrip("0") == gt.lstrip("0")),
        "last_int_in_text": last_int(t),
        "tail": tail,
    }


targets = []
for g in sys.argv[1:]:
    targets += sorted(glob.glob(g))

rows = [audit(p) for p in targets]
print(f"{'traj':40s} {'trunc':>5s} {'box':>4s} {'ans_is':>6s} {'final':>5s} "
      f"{'陈述答案':>8s} {'来源':>10s} {'=gt?':>5s} {'末整数':>7s} {'gt':>5s}")
for r in rows:
    print(f"{r['traj']:40s} {str(r['truncated']):>5s} {r['n_boxed']:4d} {r['n_answer_is']:6d} "
          f"{r['n_final']:5d} {str(r['stated_answer']):>8s} {str(r['stated_source']):>10s} "
          f"{str(r['stated_is_gt']):>5s} {str(r['last_int_in_text']):>7s} {r['gt']:>5s}")

print()
print("=" * 78)
print("E1/E2/E3 判决")
print("=" * 78)
for r in rows:
    ghost_strict = r["legacy_correct"] and r["n_boxed"] == 0
    if not ghost_strict:
        continue
    verdict = "E1 真答案（非规范形式）" if r["stated_answer"] is not None else "E2 抽取器幻觉"
    print(f"\n{r['traj']}")
    print(f"  {verdict}")
    print(f"    无 boxed；找到的答案陈述: {r['stated_source']} -> {r['stated_answer']!r}")
    print(f"    文本末尾: ...{r['tail']!r}")
    if r["stated_answer"] is None:
        print(f"    文本里最后一个整数 = {r['last_int_in_text']}（标准答案 {r['gt']}，纯属撞上）")

n_e1 = sum(1 for r in rows if r["legacy_correct"] and r["n_boxed"] == 0 and r["stated_answer"] is not None)
n_e2 = sum(1 for r in rows if r["legacy_correct"] and r["n_boxed"] == 0 and r["stated_answer"] is None)
print(f"\n合计：无 boxed 却判 correct 的 {n_e1 + n_e2} 条 -> "
      f"E1 真答案 {n_e1} 条 / E2 幻觉 {n_e2} 条")