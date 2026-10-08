"""pilot 判决：cap=8192 到底能不能让 think 轨迹自然结束？

判决规则（取数前写死，跑之前就写在这）：
  P1 主要问题：think 轨迹的触顶率必须**明显低于**现状的 92%（20/22）。
     阈值取 <= 25%（即 4 条 pilot 里最多 1 条触顶）。
  P2 think 轨迹必须能拿到 \\boxed{}，否则严格标签仍是 unlabeled，
     R-6 需要的 correct/incorrect 对照还是建不起来。
     判据：pilot 的 think 轨迹 n_boxed >= 1 的比例 >= 50%。
  P3 单条耗时上限，用来外推全量成本。
     判据：think 单条 wallclock 中位数 <= 420 s（= 8192 token / 19.5 tok/s）。

P1/P2 不达标 ⇒ 提高 cap 这条路走不通，B 路必须换思路（换更大的模型、
换更短的问题、或改用 no_think 模式做对照）。
"""
from __future__ import annotations

import glob
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/zhourui/steer3d_bpath/pilot8192/aime")
THINK_TOCAP = 0.25
THINK_BOXED = 0.50
THINK_WALL = 420.0

rows = []
for p in sorted(glob.glob(str(ROOT / "*.json"))):
    j = json.load(open(p, encoding="utf-8"))
    txt = j.get("generated_text") or ""
    boxes = re.findall(r"\\boxed\{([^}]*)\}", txt)
    cap = j["config"]["max_new_tokens"]
    ntok = j["n_generated_tokens"]
    w = j["extra"]["wallclock_s"]
    rows.append({
        "traj": j["trajectory_id"], "mode": j["config"]["mode"], "cap": cap,
        "n_tok": ntok, "truncated": ntok >= cap, "n_boxed": len(boxes),
        "last_boxed": boxes[-1].strip() if boxes else "",
        "gt": str(j["ground_truth"]).strip(),
        "legacy_correct": bool(j["is_correct"]), "wall": w,
        "end": txt.rstrip()[-40:],
    })

print(f"pilot 轨迹 {len(rows)} 条 @ {ROOT}")
print(f"{'traj':40s} {'mode':9s} {'tok':>5s} {'wall':>6s} {'box':>4s} {'旧':>5s} {'末次boxed':>8s} {'gt':>5s}  结尾")
for r in rows:
    print(f"{r['traj']:40s} {r['mode']:9s} {r['n_tok']:5d} {r['wall']:6.0f} {r['n_boxed']:4d} "
          f"{str(r['legacy_correct']):>5s} {r['last_boxed'][:8]:>8s} {r['gt']:>5s}  {r['end']!r}")

print()
for mode in ("think", "no_think"):
    rs = [r for r in rows if r["mode"] == mode]
    if not rs:
        continue
    tr = [r for r in rs if r["truncated"]]
    bx = [r for r in rs if r["n_boxed"] >= 1]
    w = [r["wall"] for r in rs]
    t = [r["n_tok"] for r in rs]
    print(f"{mode:9s} n={len(rs)}  触顶={len(tr)}/{len(rs)} ({len(tr)/len(rs)*100:.0f}%)  "
          f"有 boxed={len(bx)}/{len(rs)} ({len(bx)/len(rs)*100:.0f}%)  "
          f"tok med={statistics.median(t):.0f} max={max(t)}  "
          f"wall med={statistics.median(w):.0f}s sum={sum(w):.0f}s")

think = [r for r in rows if r["mode"] == "think"]
if not think:
    print("\n没有 think 轨迹，无法判决")
    sys.exit(2)

p1 = sum(r["truncated"] for r in think) / len(think) <= THINK_TOCAP
p2 = sum(r["n_boxed"] >= 1 for r in think) / len(think) >= THINK_BOXED
p3 = statistics.median([r["wall"] for r in think]) <= THINK_WALL

print()
print("=" * 70)
print(f"P1 think 触顶率 <= {THINK_TOCAP:.0%}          : 实测 "
      f"{sum(r['truncated'] for r in think)/len(think):.0%}  -> {'PASS' if p1 else 'FAIL'}")
print(f"P2 think 有 boxed 比例 >= {THINK_BOXED:.0%}   : 实测 "
      f"{sum(r['n_boxed']>=1 for r in think)/len(think):.0%}  -> {'PASS' if p2 else 'FAIL'}")
print(f"P3 think 单条中位耗时 <= {THINK_WALL:.0f}s : 实测 "
      f"{statistics.median([r['wall'] for r in think]):.0f}s  -> {'PASS' if p3 else 'FAIL'}")
print("=" * 70)

if p1 and p2 and p3:
    n = 60
    tw = statistics.median([r["wall"] for r in think])
    nw = statistics.median([r["wall"] for r in rows if r["mode"] == "no_think"]) \
        if any(r["mode"] == "no_think" for r in rows) else 45.0
    print(f"\n外推 60 题 × 2 模式: think {tw:.0f}s + no_think {nw:.0f}s "
          f"=> {(tw+nw)*n/3600:.1f} h")
    print(f"外推存储: 约 {n*(tw*19.5*28*2048*2 + nw*19.5*28*2048*2)/2**30:.0f} GiB (fp16)")
else:
    print("\n提高 cap 这条路**不成立**，B 路需要换方案。")

sys.exit(0 if (p1 and p2 and p3) else 1)