"""B 路 pilot 的判决产物生成器。

写成文件而不是 bash 单行：本轮在单行里塞正则被转义吃掉一层，
`boxed` 计数全线归零，差点把一份假判决写进版本库。
**带正则的 Python 一律写文件。**
"""
from __future__ import annotations

import glob
import json
import re
import statistics
import sys

PATS = [
    ("boxed", re.compile(r"\\boxed\{([^}]*)\}")),
    ("so_the", re.compile(r"so\s+the\s+answer\s+is\s+\$?\s*(-?\d+)", re.I)),
    ("answer_is", re.compile(r"answer\s*(?:is|equals|=)\s*\$?\s*(-?\d+)", re.I)),
    ("final", re.compile(r"(?:final\s+answer|answer)\s*[:=]\s*\$?\s*(-?\d+)", re.I)),
]


def norm_int(s):
    if s is None:
        return None
    t = re.sub(r"[^0-9-]", "", str(s).strip())
    if t in ("", "-"):
        return None
    try:
        return str(int(t))
    except ValueError:
        return None


def scan(path):
    j = json.load(open(path, encoding="utf-8"))
    t = j.get("generated_text") or ""
    hits = []
    for src, pat in PATS:
        for m in pat.finditer(t):
            hits.append((m.start(), src, m.group(1)))
    hits.sort(key=lambda x: x[0])
    stated = norm_int(hits[-1][2]) if hits else None
    src = hits[-1][1] if hits else None
    gt = norm_int(j.get("ground_truth"))
    cap = j["config"]["max_new_tokens"]
    ntok = j["n_generated_tokens"]
    return {
        "traj": j["trajectory_id"],
        "mode": j["config"]["mode"],
        "cap": cap,
        "n_tok": ntok,
        "truncated": ntok >= cap,
        "n_boxed": len(re.findall(r"\\boxed\{([^}]*)\}", t)),
        "n_statements": len(hits),
        "stated": stated,
        "stated_src": src,
        "gt": gt,
        "legacy_correct": bool(j["is_correct"]),
        "wall_s": round(j["extra"]["wallclock_s"], 1),
    }


def label_of(r):
    if r["stated"] is None:
        return "unlabeled"
    return "correct" if r["stated"] == r["gt"] else "wrong"


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else ".cache/bpath/pilot"
    out_path = sys.argv[2] if len(sys.argv) > 2 else ".cache/mutbak/bpath_pilot_verdict.json"
    rows = [scan(p) for p in sorted(glob.glob(f"{src_dir}/*.json"))]
    for r in rows:
        r["strict"] = label_of(r)

    def agg(rs):
        return {
            "n": len(rs),
            "trunc": sum(r["truncated"] for r in rs),
            "labeled": sum(1 for r in rs if r["strict"] != "unlabeled"),
            "correct": sum(1 for r in rs if r["strict"] == "correct"),
            "wrong": sum(1 for r in rs if r["strict"] == "wrong"),
            "tok_med": statistics.median([r["n_tok"] for r in rs]),
            "tok_max": max(r["n_tok"] for r in rs),
            "wall_med_s": statistics.median([r["wall_s"] for r in rs]),
            "wall_sum_s": round(sum(r["wall_s"] for r in rs), 1),
        }

    th = [r for r in rows if r["mode"] == "think"]
    nt = [r for r in rows if r["mode"] == "no_think"]
    mean_th = sum(r["wall_s"] for r in th) / len(th)
    mean_nt = sum(r["wall_s"] for r in nt) / len(nt)

    out = {
        "schema": "bpath_pilot_v2",
        "why_v2": "v1 是在 bash 单行里生成、正则被转义吃掉，boxed 计数全线归零。"
                  "带正则的 Python 必须写文件。v2 由 pilot_verdict2.py 生成。",
        "what": "B 路扩样的 cap 取值 pilot：3 题 x 2 模式，cap 8192",
        "gpu": "zju-53 CVD 7 = nvidia-smi index 3 = RTX PRO 5000 Blackwell",
        "prereg_gates": {
            "P1_think_tocap_le_0.25": "FAIL (实测 33%)",
            "P2_think_has_boxed_ge_0.50": "PASS (实测 67%)",
            "P3_think_median_wall_le_420s": "PASS (实测 205s)",
        },
        "gate_correction": (
            "P1 衡量的是截断，而本实验要解除的约束是「拿不拿得到标签」。"
            "按标签产出率：cap2048 时 think 25%(6/24)，cap8192 时 100%(3/3)。"
            "触顶的那条 p02 恰恰有标签（so the answer is 16）—— 截断不等于无标签。"
        ),
        "think": agg(th),
        "no_think": agg(nt),
        "extrapolation_60_problems": {
            "think_wall_mean_s": round(mean_th, 1),
            "no_think_wall_mean_s": round(mean_nt, 1),
            "total_h": round(60 * (mean_th + mean_nt) / 3600, 2),
        },
        "rows": rows,
    }
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 自检：打印出来的聚合数必须与 rows 一致（防止又写出一份自相矛盾的判决）
    assert out["think"]["labeled"] == sum(1 for r in th if r["strict"] != "unlabeled")
    assert out["think"]["correct"] + out["think"]["wrong"] + (
        len(th) - out["think"]["labeled"]) == len(th)
    assert sum(r["n_boxed"] for r in rows) > 0, "boxed 计数全零 = 正则又被转义吃了"

    print(json.dumps({k: v for k, v in out.items() if k != "rows"},
                     ensure_ascii=False, indent=1))
    print("\n自检通过：聚合数与 rows 一致，且 boxed 计数非零。")
    print("写出", out_path)


if __name__ == "__main__":
    main()