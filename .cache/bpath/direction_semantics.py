#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 50 取数：L1 那条「真实 vs 随机 ⇒ 与语义无关」到底测了什么。

判据写在 `.cache/xcheck/R6_RERUN_PREREG.md` §50.2，取数前已单独提交并推送
（`8715cda`）。本脚本只执行，不改判。

三问：

· **Q1 分辨率** —— 那条 null 能分辨多小的差别？
  `r_res = max_real_vs_random_gap_pp / pred 基线`；与同一个观测量里**已知存在**
  的方向依赖 `c_amp = max_c max f(c) − min_c f(c)`，`f(c)=(1−ac)/(1+ac)`。
  阈值 **1 是定义不是调参**：`c_amp/r_res > 1` ⇒ 这条 null 不构成「无关」的证据。

· **Q2 语义地位** —— `linearity_law.json` 里**有没有任何字段**记载那四条真实
  方向的可读性分数或专属性 margin？只判**在不在**，不判取值。
  （判据第 14 条要求：宣称「与 X 无关」前必须报出决定 X 的那个标量。）

· **Q3 两臂定义** —— 「真实」那一臂到底是什么、它的语义由谁担保。
  只报事实，不下因果结论。

⚠ 为什么 Q2 要**单独判「在不在」**：这个产物里全是数字，键名扫描是最强的形式
—— 若连键名都没有，那这个标量就**从未进入过**这次测量，
不是「记了但值不好看」。两者要分开。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"
LAW = DATA / "linearity_law.json"
SUB = DATA / "readable_subspace.json"
VECDOC = ROOT / "backend/examples/output/steering_vectors/steering_vectors.json"
PRESET = ROOT / "backend/core/steering.py"
OUT = Path(__file__).resolve().parent.parent / "mutbak/direction_semantics.json"

SEMANTIC_KEY_RE = re.compile(
    r"readab|specific|exclusive|dedicat|semantic|meaning|concept|"
    r"margin|specificity|separat", re.I)

REAL4 = ["caution", "confidence_up", "creativity", "reasoning_deep"]


def all_keys(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            acc.add(k)
            all_keys(v, acc)
    elif isinstance(o, list):
        for v in o:
            all_keys(v, acc)
    return acc


def main() -> int:
    law = json.loads(LAW.read_text(encoding="utf-8"))
    sub = json.loads(SUB.read_text(encoding="utf-8"))
    vec = json.loads(VECDOC.read_text(encoding="utf-8")) if VECDOC.exists() else {}

    safe = law["conclusions"]["safe_regime"]
    s_max = float(safe["strength_max"])
    top = [r for r in law["rows"] if abs(r["strength"] - s_max) < 1e-9]
    base = min(float(r["pred_pct"]) for r in top)

    # ---------------- Q1 分辨率 ----------------
    r_res = float(safe["max_real_vs_random_gap_pp"]) / base
    c_amp = 0.0
    for r in top:
        a = max(float(v["a_mean"]) for v in r["real"].values())
        f = [(1 - a * float(v["cos_mean"])) / (1 + a * float(v["cos_mean"]))
             for v in r["real"].values()]
        c_amp = max(c_amp, max(f) - min(f))
    ratio = c_amp / r_res
    q1_pass = ratio <= 1.0
    q1_verdict = ("该 null 的分辨率足以排除一个已知的方向依赖，可作正证据"
                  if q1_pass else
                  "该 null **不构成**「无关」的证据（分辨率 %.2f%% < 已知方向依赖 %.2f%%）"
                  % (100 * r_res, 100 * c_amp))

    # ---------------- Q2 语义地位：键名在不在 ----------------
    keys = all_keys(law, set())
    semantic_keys = sorted(k for k in keys if SEMANTIC_KEY_RE.search(k))
    q2_pass = bool(semantic_keys)
    q2_verdict = ("产物里存在相关字段：" + "、".join(semantic_keys)) if q2_pass else \
        ("`linearity_law.json` 的 %d 个键名里**没有**任何一个记载可读性 / 专属性 / "
         "语义地位 ⇒ 决定「语义」的那个标量**从未进入这次测量**" % len(keys))

    # ---------------- Q3 两臂定义 ----------------
    prov = {}
    for nm in REAL4:
        e = vec.get(nm, {})
        prov[nm] = {"method": e.get("method"),
                    "positive_group": e.get("positive_group"),
                    "negative_group": e.get("negative_group"),
                    "label": e.get("description") or e.get("label")}
    absorbed = [a for a in sub["headline"].get("absorbed", []) if isinstance(a, str)]
    q3 = {
        "real_arm": REAL4,
        "n_random": law["design"]["n_random"],
        "provenance": prov,
        "readable_question": sub["question"],
        "named_axes": sub["headline"]["named_axes"],
        "n_candidates": sub["headline"]["n_candidates"],
        "absorbed_in_readable": absorbed,
        "caution_absorbed": sub["headline"].get("caution_absorbed"),
        "all_four_method_diff_of_means":
            all(v["method"] == "diff_of_means" for v in prov.values()),
    }
    # 四条里有没有哪条被本项目自己的可读性判据明确记为不合格
    dropped = [nm for nm in REAL4
               if any(f"axis:{nm}" == a for a in absorbed)]
    q3["dropped_by_readability"] = dropped

    # ---------------- 判决（Q1 与 Q2 合取）----------------
    if not q1_pass and not q2_pass:
        verdict = "「与语义无关」**从未被检验**（不是被证伪）"
        action = ("L1 note 给「真实-vs-随机」补分辨率与前提限定；claim 不动")
    elif not q1_pass:
        verdict = "语义地位有出处，但分辨率不足"
        action = "同左，另引该字段"
    else:
        verdict = "该 null 有分辨率"
        action = "不动"

    res = {"schema": "steer3d.direction_semantics/1",
           "prereg": "R6_RERUN_PREREG.md §50.2 @ 8715cda",
           "source": ["frontend/public/latent/data/linearity_law.json",
                      "frontend/public/latent/data/readable_subspace.json",
                      "backend/examples/output/steering_vectors/steering_vectors.json"],
           "Q1": {"pred_base": base,
                  "gap_pp": float(safe["max_real_vs_random_gap_pp"]),
                  "resolution_rel": r_res,
                  "known_direction_effect_rel": c_amp,
                  "ratio": ratio, "pass": q1_pass, "verdict": q1_verdict},
           "Q2": {"n_keys": len(keys), "semantic_keys": semantic_keys,
                  "pass": q2_pass, "verdict": q2_verdict},
           "Q3": q3,
           "verdict": verdict, "action": action}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    print("[Q1] 分辨率")
    print(f"     pred 基线（s={s_max}，从产物读） = {base:.4f}%")
    print(f"     真实-vs-随机 间隙 {safe['max_real_vs_random_gap_pp']:.6f} pp"
          f"  ⇒ 分辨率 {100*r_res:.3f}%")
    print(f"     已知的方向依赖（同观测量、同样四条方向） = {100*c_amp:.3f}%")
    print(f"     比值 = {ratio:.2f}×   ⇒ {'通过' if q1_pass else '**不通过**'}")
    print(f"     {q1_verdict}")
    print("\n[Q2] 语义地位（只判在不在）")
    print(f"     linearity_law.json 共 {len(keys)} 个键名；"
          f"命中可读性/专属性/语义类的：{semantic_keys or '**零个**'}")
    print(f"     {q2_verdict}")
    print("\n[Q3] 两臂定义")
    print(f"     真实臂 = {REAL4}；随机臂 n_random = {law['design']['n_random']}")
    for nm, v in prov.items():
        print(f"       {nm:15} method={v['method']} "
              f"{v['positive_group']} vs {v['negative_group']}")
    print(f"     四条是否全部 diff_of_means：{q3['all_four_method_diff_of_means']}")
    print(f"     可读性判据的 question：{sub['question']}")
    print(f"     named_axes={q3['named_axes']} n_candidates={q3['n_candidates']}")
    print(f"     其中被本项目可读性判据记为不合格：{dropped or '无'}")
    if dropped:
        print(f"     ↳ {sub['headline']['caution_absorbed'][:110]}")
    print(f"\n[判决] **{verdict}**")
    print(f"[动作] {action}")
    print(f"写出: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())