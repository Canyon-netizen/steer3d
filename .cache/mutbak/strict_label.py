"""严格标签：把抽取器的兜底路径从「答对/答错」里剔出去。

背景（CAUSAL_PREREG.md R-26）：`parse_aime_answer` 有三条兜底路径 ——
`\boxed{}` → "answer is N" → 文本里最后一个整数。
think 轨迹在 cap 处被切断时落到第三条，于是
`1983_I_1__think` / `2020_I_1__think` 这两条
「通篇无 `\boxed{}`、答案却等于标准答案」的轨迹被判成 correct。

本脚本**只读轨迹文本**，不依赖 GPU，可对任意批次的轨迹目录施加同一规则。

## 规则（取数前写死）

  n_boxed   = 文本里 `\boxed{...}` 的个数
  last_box  = 最后一个 boxed 的内容（归一化后）
  correct_strict = (n_boxed >= 1) 且 (last_box == ground_truth)
  wrong_strict   = (n_boxed >= 1) 且 (last_box != ground_truth)
  unlabeled      = n_boxed == 0     ← 不计入 correct 也不计入 incorrect

  truncated = n_generated_tokens >= config.max_new_tokens

## 输出

每条轨迹一行：旧标签 / 严格标签 / 触顶标记 / boxed 数 / 末次 boxed 内容
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path


def norm_int(s: str) -> str:
    """把 boxed 内容归一化成不带前导零的整数串。"""
    if s is None:
        return ""
    t = str(s).strip()
    m = re.fullmatch(r"\$?\\?\(?\s*(-?\d+)\s*\)?\$?", t)
    if m:
        t = m.group(1)
    t = re.sub(r"[^0-9-]", "", t)
    if t in ("", "-"):
        return ""
    try:
        return str(int(t))
    except ValueError:
        return ""


def label(path: str) -> dict:
    j = json.load(open(path, encoding="utf-8"))
    txt = j.get("generated_text") or ""
    boxes = re.findall(r"\\boxed\{([^}]*)\}", txt)
    gt = norm_int(j.get("ground_truth", ""))
    last = norm_int(boxes[-1]) if boxes else ""
    cfg = j.get("config", {})
    cap = cfg.get("max_new_tokens")
    ntok = j.get("n_generated_tokens")
    truncated = bool(cap and ntok is not None and ntok >= cap)

    if not boxes:
        strict = "unlabeled"
    elif gt and last == gt:
        strict = "correct"
    else:
        strict = "wrong"

    return {
        "traj": j.get("trajectory_id", Path(path).stem),
        "mode": cfg.get("mode"),
        "cap": cap,
        "n_tok": ntok,
        "truncated": truncated,
        "n_boxed": len(boxes),
        "last_boxed": last,
        "gt": gt,
        "legacy_correct": bool(j.get("is_correct")),
        "legacy_answer": j.get("generated_answer"),
        "strict": strict,
        # 旧标签判 correct 而严格标签不是 => 抽取器幻觉
        "ghost": bool(j.get("is_correct")) and strict != "correct",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("globs", nargs="+", help="轨迹 json 的 glob")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    paths = []
    for g in a.globs:
        paths += sorted(glob.glob(g))
    rows = [label(p) for p in paths]

    c = Counter(r["strict"] for r in rows)
    gh = [r for r in rows if r["ghost"]]
    tr = [r for r in rows if r["truncated"]]

    if not a.quiet:
        print(f"{'trajectory':46s} {'mode':9s} {'cap':>5s} {'tok':>5s} {'box':>4s} "
              f"{'旧':>5s} {'严格':>10s}  备注")
        for r in rows:
            note = []
            if r["truncated"]:
                note.append("触顶")
            if r["ghost"]:
                note.append("<<D1 红：旧标签幻觉")
            if r["n_boxed"] == 0 and not r["ghost"]:
                note.append("无 boxed -> unlabeled")
            print(f"{r['traj']:46s} {str(r['mode']):9s} {str(r['cap']):>5s} {str(r['n_tok']):>5s} "
                  f"{r['n_boxed']:4d} {str(r['legacy_correct']):>5s} {r['strict']:>10s}  {' '.join(note)}")

    print()
    print(f"轨迹总数 {len(rows)}")
    print(f"  严格: correct={c['correct']}  wrong={c['wrong']}  unlabeled={c['unlabeled']}")
    print(f"  旧标签: correct={sum(r['legacy_correct'] for r in rows)}")
    print(f"  触顶: {len(tr)}/{len(rows)}")
    print(f"  **旧标签幻觉 (D1 红): {len(gh)}** -> {[r['traj'] for r in gh]}")

    # 按 mode 拆开：think 的触顶率与幻觉率是重点
    print()
    for mode in ("think", "no_think"):
        rs = [r for r in rows if r["mode"] == mode]
        if not rs:
            continue
        cc = Counter(r["strict"] for r in rs)
        lab = cc["correct"] + cc["wrong"]
        print(f"{mode:9s} n={len(rs):3d}  触顶={sum(r['truncated'] for r in rs):3d} "
              f"({sum(r['truncated'] for r in rs)/len(rs)*100:3.0f}%)  "
              f"有标签={lab:3d} ({lab/len(rs)*100:3.0f}%)  "
              f"correct={cc['correct']:2d} wrong={cc['wrong']:2d} unlabeled={cc['unlabeled']:2d}  "
              f"幻觉={sum(r['ghost'] for r in rs)}")

    if a.out:
        json.dump({"n": len(rows), "counter": dict(c),
                   "ghosts": [r["traj"] for r in gh],
                   "rows": rows},
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n写出", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())