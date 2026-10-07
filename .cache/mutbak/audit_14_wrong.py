#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐条**人工读** Phase-0 那 14 条判错，打印原文上下文供逐条裁决。

⚠ 这个脚本**不下判决**。它只把每条判错的原文按前后窗口原样摊开，
  让人（或下一轮的 agent）看着文本判断「模型这句到底算错没有」。
  自动抽取器的 `lhs` 字段**不可信**——它是回扫出来的片段，不是模型
  真正在断言的那个表达式。

用法：
    PYTHONPATH=.cache/pylibs python3 .cache/mutbak/audit_14_wrong.py
    PYTHONPATH=.cache/pylibs python3 .cache/mutbak/audit_14_wrong.py --json
"""
from __future__ import annotations

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
CLAIMS = os.path.join(ROOT, ".cache", "xcheck", "p0_claims.json")

# 每条判错的人工裁决。key = (trajectory_id, tok)。
# verdict 取值：
#   false_positive —— 抽取器抓错了片段，模型这句是对的
#   true_error     —— 模型这句确实算错了（且错因在算术）
#   needs_human    —— 我读不出来，需要人来看
# note 必须写「为什么」，不能只写结论。
VERDICTS = {
    ("aime__1987__1987_I_1__think", 1952): (
        "false_positive",
        "原文是 φ(s) + 1 = 2，s=1 时 φ(1)=1 ⇒ 1+1=2 正确。抽取器把 "
        "「+ 1」单独当成了等号左边，把 φ(s) 那个部分丢了，于是宣称「1 应等于 2」。",
    ),
    ("aime__1987__1987_I_1__think", 1968): (
        "false_positive",
        "原文是 s=2 时 φ(2)=1，然后说 φ(s)+1=2（承接上一句）。抽出来的是 "
        "「(2)」= 1，这是 φ(2)=1 这一句，φ(2)=1 本身正确。",
    ),
    ("aime__1988__1988_I_1__think", 332): (
        "false_positive",
        "原文是一串平方数列表「0²=0, 1=1, 2=4, 3=9, 4=0, 5=25≡9, …」。"
        "这一项是 2²=4 —— 列表省略了重复的平方记号，2²=4 完全正确。"
        "抽取器把「2」当成被平方的数，于是宣称「2 应等于 4」。",
    ),
    ("aime__1988__1988_I_1__think", 337): (
        "false_positive",
        "同上，列表项 3²=9，正确。",
    ),
    ("aime__1988__1988_I_1__think", 342): (
        "false_positive",
        "同上，列表项 4²=16≡0 (mod 16)，写 0 是对的（这一项自带 ≡0）。"
        "抽取器只看到「4=0」。",
    ),
    ("aime__1992__1992_I_1__think", 963): (
        "false_positive",
        "原文 floor(299/2) = 149 —— 299/2 = 149.5，floor 之后正是 149。"
        "抽取器不认识 floor，把被 floor 的表达式单独拿来比，于是宣称 149 ≠ 149.5。",
    ),
    ("aime__2002__2002_I_1__think", 1173): (
        "false_positive",
        "原文 11.232 * 10^6 = 11,232,000 —— 完全正确。抽取器抓到的是 "
        "指数那个 6（10^6 里的 ^6 被当成独立算式），宣称「6 应等于 11232000」。",
    ),
    ("aime__2010__2010_I_1__think", 913): (
        "false_positive",
        "原文是反证/设元：若 x 是使 6x + 20 = 100 成立的数，则 6x = 80，x ≈ 13.333。"
        "模型在**解方程**，不是在断言恒等式；6x+20=100 → x=80/6 这条推理本身正确"
        "（答案 13 后来是对的，is_correct=True）。抽取器把设元式当成恒等式来验。",
    ),
    ("aime__2016__2016_I_1__think", 1492): (
        "false_positive",
        "原文 x²/25 + y²/9 = 1 —— 椭圆标准式，分母 9 是 b²，正确。"
        "抽取器把 y²/9 里的分母 9 单独抽出来，跟右边的 1 比。",
    ),
    ("aime__2016__2016_I_1__think", 1923): (
        "false_positive",
        "原文 c = sqrt(25 - 9) = sqrt(16) = 4 —— sqrt(16)=4 完全正确。"
        "抽取器不认识 sqrt，把被开方式的 16 单独抽出来比。",
    ),
    ("aime__2020__2020_I_1__think", 760): (
        "false_positive",
        "原文 m = 2^0 * 5^0 = 1 —— 正确（任何数的 0 次方是 1）。"
        "抽取器抓到的是指数 0，宣称「0 应等于 1」。",
    ),
    ("aime__2020__2020_I_1__think", 831): (
        "false_positive",
        "原文 n = 2^(40-40) * 5^(20-20) = 1 —— 指数为 0 ⇒ 值 1，正确。"
        "抽取器只抓到指数那个 (20-20)，跟右边的 1 比。",
    ),
    ("aime__2022__2022_I_1__think", 1788): (
        "false_positive",
        "原文 (a + b)^2 = 16 and (a - b)^2 = 16 —— 这是把方程平方后的结果，"
        "正确。抽取器把平方记号 2 当成被比较的数，跟 16 比。",
    ),
    ("aime__2025__2025_I_1__think", 1212): (
        "false_positive",
        "原文 sqrt(1 + 3) = 2 —— sqrt(4)=2 完全正确。"
        "抽取器不认识 sqrt，把 1+3 单独抽出来跟 2 比。",
    ),
}


def load_wrong():
    d = json.load(open(CLAIMS, encoding="utf-8"))
    out = []
    for r in d["rows"]:
        for c in r["claims"]:
            if not c["ok"]:
                out.append((r["trajectory_id"], c))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ctx", type=int, default=90, help="每个方向取多少字符上下文")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    wrong = load_wrong()
    texts = {}
    rows = []
    for traj, c in wrong:
        if traj not in texts:
            texts[traj] = json.load(
                open(os.path.join(NPZ_DIR, traj + ".json"), encoding="utf-8")
            )
        o = texts[traj]
        text = o.get("generated_text", "")
        s = max(0, c["start"] - a.ctx)
        e = min(len(text), c["end"] + 40)
        v = VERDICTS.get((traj, c["tok"]))
        rows.append({
            "trajectory_id": traj,
            "is_correct": o["is_correct"],
            "ground_truth": o["ground_truth"],
            "generated_answer": o["generated_answer"],
            "tok": c["tok"],
            "span": [c["start"], c["end"]],
            "extractor_lhs": c["lhs"],
            "extractor_stated": c["stated"],
            "extractor_computed": c["computed"],
            "context": text[s:e].replace("\n", " ⏎ "),
            "verdict": v[0] if v else "needs_human",
            "note": v[1] if v else "",
        })

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    n_fp = sum(1 for r in rows if r["verdict"] == "false_positive")
    n_te = sum(1 for r in rows if r["verdict"] == "true_error")
    n_nh = sum(1 for r in rows if r["verdict"] == "needs_human")
    print(f"Phase-0 判错 {len(rows)} 条 —— 逐条人工读原文：")
    print(f"  抽取器假阳性 {n_fp} · 真算错 {n_te} · 待人看 {n_nh}\n")
    for i, r in enumerate(rows, 1):
        print(f"{i:2d}. [{r['trajectory_id'][5:9]}] tok{r['tok']} "
              f"最终答案 {r['generated_answer']}/{r['ground_truth']} "
              f"({'对' if r['is_correct'] else '错'})")
        print(f"    抽取器: lhs={r['extractor_lhs']!r} stated={r['extractor_stated']} "
              f"computed={r['extractor_computed']} ⇒ 判错")
        print(f"    原文  : …{r['context']}…")
        print(f"    裁决  : {r['verdict']} —— {r['note']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())