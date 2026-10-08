"""查：触顶(truncated)轨迹的 is_correct 是否可信。

背景：现有 48 条里 think 模式 22/24 全部跑满 max_new_tokens 未发 EOS。
若 is_correct 是从「截断前偶然写下的 \\boxed{}」抽出来的，那 correct/incorrect
分组就掺了噪声，而 R-5/R-6 的分组分析正是建在这个分组上。

判决规则取数前写死：
  D1 触顶轨迹里，必须存在 \\boxed{...} 才能被判 correct；
     没有 boxed 却被判 correct => 标签是抽取器幻觉 => 判红。
  D2 抽取到的答案必须来自 boxed（而不是"最后一个整数"兜底路径）。
  D3 think 与 no_think 分开报，因为 no_think 触顶率低得多。
"""
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
from core.aime_loader import parse_aime_answer  # noqa: E402

rows = [json.load(open(p)) for p in sorted(glob.glob(str(REPO / "datasets/aime_qwen3_1p7b_16k_fp16/aime/*.json")))]

print("=" * 76)
print("D1/D2  触顶轨迹的 correct 标签来源")
print("=" * 76)
hdr = f"{'trajectory':44s} {'cap':>5s} {'tok':>5s} {'boxed?':>7s} {'nbox':>5s} {'label':>6s} {'ans':>6s} {'gt':>5s}"
print(hdr)
stats = Counter()
d1_viol, d2_viol = [], []
for r in rows:
    cap = r["config"]["max_new_tokens"]
    tok = r["n_generated_tokens"]
    trunc = tok >= cap
    txt = r["generated_text"]
    boxes = re.findall(r"\\boxed\{([^}]*)\}", txt)
    tag = "THINK" if r["config"]["mode"] == "think" else "nothk"
    flag = ""
    if trunc and r["is_correct"]:
        if not boxes:
            flag = "  <== D1 红：无 boxed 却判 correct"
            d1_viol.append(r["trajectory_id"])
        else:
            # 走的是 "answer is N" 或 "最后一个整数" 兜底吗
            if parse_aime_answer(txt) != (boxes[-1].strip() if boxes else None):
                flag = "  <== D2 红：答案非来自最后一个 boxed"
                d2_viol.append(r["trajectory_id"])
    print(f"{r['trajectory_id']:44s} {cap:5d} {tok:5d} {str(bool(boxes)):>7s} "
          f"{len(boxes):5d} {str(r['is_correct']):>6s} {str(r['generated_answer']):>6s} "
          f"{str(r['ground_truth']):>5s}{flag}")
    stats[(tag, trunc)] += 1

print()
print("=" * 76)
print("汇总")
print("=" * 76)
for k in sorted(stats):
    print(f"  {k[0]:6s} 触顶={str(k[1]):5s} : {stats[k]:2d} 条")
print(f"  D1 违例: {len(d1_viol)} -> {d1_viol}")
print(f"  D2 违例: {len(d2_viol)} -> {d2_viol}")

print()
print("=" * 76)
print("关键分组口径：触顶轨迹算不算「完整 CoT」")
print("=" * 76)
for mode in ("think", "no_think"):
    rs = [r for r in rows if r["config"]["mode"] == mode]
    tr = [r for r in rs if r["n_generated_tokens"] >= r["config"]["max_new_tokens"]]
    nt = [r for r in rs if r["n_generated_tokens"] < r["config"]["max_new_tokens"]]
    print(f"{mode:9s} n={len(rs):2d}  触顶={len(tr):2d} ({len(tr)/len(rs)*100:.0f}%)  自然结束={len(nt):2d}")
    print(f"          触顶组答对 {sum(r['is_correct'] for r in tr)}/{len(tr)}"
          f" | 自然结束组答对 {sum(r['is_correct'] for r in nt)}/{len(nt)}")

print()
print("=" * 76)
print("若把触顶轨迹剔除，correct/incorrect 分组会变成什么样")
print("=" * 76)
clean = [r for r in rows if r["n_generated_tokens"] < r["config"]["max_new_tokens"]]
print(f"  全量 48 条: correct={sum(r['is_correct'] for r in rows)}")
print(f"  剔除触顶后剩 {len(clean)} 条: correct={sum(r['is_correct'] for r in clean)}")
print(f"  触顶轨迹里被判 correct 的: "
      f"{[r['trajectory_id'] for r in rows if r['n_generated_tokens']>=r['config']['max_new_tokens'] and r['is_correct']]}")