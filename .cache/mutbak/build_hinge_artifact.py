#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把动摇点 + 逐层读数导成网站可读的 `hinge_hinges.json`。

⚠ 产物里**必须自带诚实边界**（`caveats` 字段），因为网站读者
  看不到本轮这些脚本，只能看到页面。任何在报告里说过「不许说」
  的东西，都必须在产物里跟着数字一起走，否则页面就成了那个
  「替未测量的东西作证」的地方（本项目栽过：`index.html` 第二十五笔）。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HINGE = os.path.join(ROOT, ".cache", "xcheck", "hinge.json")
AUDIT = os.path.join(ROOT, ".cache", "mutbak", "hinge_audit.json")
LENS = os.path.join(ROOT, ".cache", "mutbak", "logit_lens_hinge.json")
PROBE = os.path.join(ROOT, ".cache", "mutbak", "probe_verdict.json")
OFFSETS = os.path.join(ROOT, ".cache", "mutbak", "probe_offsets.json")
OUT = os.path.join(ROOT, "frontend", "public", "latent", "data",
                   "hinge_hinges.json")


def main() -> int:
    h = json.load(open(HINGE, encoding="utf-8"))
    au = {(x["traj"], x["start"]): x for x in json.load(open(AUDIT, encoding="utf-8"))}
    lens = json.load(open(LENS, encoding="utf-8"))
    pv = json.load(open(PROBE, encoding="utf-8"))
    off = json.load(open(OFFSETS, encoding="utf-8"))

    by_id = {}
    for tr in lens["trajectories"]:
        by_id[tr["id"]] = {s["t"]: s for s in tr["steps"]}

    rows = []
    for r in h["rows"]:
        tid = r["trajectory_id"]
        items = []
        for x in r["hinges"]:
            st = by_id.get(tid, {}).get(x["tok"])
            a = au.get((tid, x["start"]))
            if st is None:
                continue
            items.append({
                "tok": x["tok"],
                "cls": x["cls"],
                "sentence": x["sentence"],
                "audited": (a or {}).get("verdict", "needs_human"),
                "audited_note": (a or {}).get("note", ""),
                "first_layer_correct": st["first_layer_correct"],
                "n_layers_correct": st["n_layers_correct"],
                "monotone": st["monotone"],
                "real_margin": st["real_margin"],
                "decidable": st["decidable"],
                "anchor_ok": st["anchor_ok"],
                "final_id": st["final_id"],
            })
        if items:
            rows.append({"trajectory_id": tid, "n": len(items), "hinges": items})

    n = sum(r["n"] for r in rows)
    audited = sum(1 for r in rows for x in r["hinges"]
                  if x["audited"] != "needs_human")
    correct = sum(1 for r in rows for x in r["hinges"]
                  if x["audited"] == "true_hinge")

    out = {
        "schema": "hinge_hinges/1",
        "title": "模型在推理中途动摇的位置",
        "title_en": "positions where the model second-guesses itself mid-derivation",
        "what_this_is":
            "这是「模型自己说我可能错了」的位置。判据把它们挑出来之后，"
            "逐条人工读过（不是只跑自动判据）。"
            "它不是「算式两边对不上」那一支找到的位置 —— 那一支的 14 条"
            "逐条读后全是抽取器假阳性，详见下方「为什么」。",
        "n_hinges": n,
        "n_traces": len(rows),
        "n_audited": audited,
        "audit_accuracy": correct / audited if audited else None,
        "audit_note":
            f"{audited}/{n} 条经过人工裁决，其中 {correct} 条判为真动摇"
            f"（{correct/audited*100:.1f}%）。剩下的 {n-audited} 条尚未裁决，"
            f"页面上逐条标着。",
        "why_not_arithmetic":
            "P0 装置用「算式两边对不上」找错，交付 14 个位置，"
            "**逐条读原文后 14/14 全是假阳性**（`10^6 = 11,232,000` 被抽成 "
            "`6 = 11,232,000`；`sqrt(16) = 4` 被抽成 `16 = 4`；"
            "`0²=0, 1=1, 2=4` 里的 `2=4` 本读作 `2²=4`）。"
            "更致命的是覆盖面：19 条答案错的轨迹里 **12 条抽取器零判错**，"
            "人工读那些收尾，错因是**误解题意 / 假设错 / 算术对但推理链断**。"
            "⇒ **1.7B 的错误主要不在算术层**，所以换了判据类型。",
        "per_step_field_doc": {
            "first_layer_correct": "逐层 logit lens 里，argmax **第一次**等于最终"
                                   "token 的层号（0–27）。测的是**token 身份**"
                                   "何时定型，**不是**「知道什么」。",
            "n_layers_correct": "28 层里有几层的 argmax 等于最终 token。",
            "monotone": "一旦某层正确，之后每层都正确。",
            "real_margin": "模型自己在该步的 top1−top2 logit 差。0 = 完全无差别。",
            "decidable": "real_margin ≥ 1.0。margin 太小的步，"
                         "float16 重建误差就能左右结果，**不计入分层结论**。",
            "anchor_ok": "lens 在末层能否复现模型实际选的 token。"
                         "未通过的步是模型**自己也无所谓**的那些（margin=0）。",
        },
        "probe": {
            "question": "在**标记词还没写出来**的位置上，这个信号有多可读？",
            "design": "取 h(t-1) 处的隐状态（该处 token 是句号/空格/逗号，"
                      "`Wait` 一个字都还没出现），训线性方向区分"
                      "「此处将出现动摇」与「此处是同轨迹的非动摇点」。"
                      "切分一律**按轨迹分组**（同轨迹的位置高度相关，"
                      "随机划分会让分数虚高）。",
            "auroc_before_marker": {
                "off0_已写下标记词": max(off["off0_d20"]),
                "off1_标记词尚未写出": max(off["off1_d20"]),
                "off2": max(off["off2_d20"]),
                "off3": max(off["off3_20"]) if "off3_20" in off else max(off["off3_d20"]),
            },
            "auroc_null_controls": pv["ctrl_peaks"],
            "verdict": pv["verdict"],
            "p4_提前可读": pv["p4"],
            "p5_不是纯位置效应": pv["p5"],
        },
        "caveats": [
            "**探针测的是可分性，不是知识。** 说「存在一个线性方向能区分」"
            "是可以的；说「模型在第 L 层知道自己错了」**不行**。",
            "**本轮没有做任何干预，所以不是因果。** 相关不等于因果。",
            "**h(t-1) 仍在同一上下文里，且 t-1 常是句号位置。** "
            "所以连「提前」也只是「在写下标记词之前」这个字面意思。",
            "**分数随负例的语义差异变化**：Δ=20 时 0.993，Δ=1 时 0.986。"
            "测到的是「此处与别处的差异」，不是「此处与 1 token 之差的差异」。",
            "**浅层=感知、深层=推理是外部叙事，本轮不测。** "
            "层号只表示「token 身份何时定型」或「该方向何时可分」。",
            "121 个位置里有些步 real_margin=0（模型自己也无所谓），"
            "这些步的 lens 结论不可靠，已在 per_step 的 decidable 字段标出。",
        ],
        "trajectories": rows,
    }
    # ⚠⚠ 产物是给 **React** 消费的，而 React **不渲染 markdown**。
    #   第一版产物里带着 42 处 `**`，截图一看就是页面上一堆星号
    #   （「`**探针测的是可分性，不是知识。**`」原样印出来）。
    #   ⇒ 这里统一剥掉 `**`；语义靠**句子本身**承载，不靠标记。
    #   ⚠ 内部路径（`.cache/...`）也不该出现在读者眼前 —— 换成读者能懂的话。
    _PATH_FIX = {
        "`.cache/mutbak/audit_hinge.py` 的 VERDICTS 表里": "逐条的裁决理由见项目判据脚本",
    }

    def demd(o):
        if isinstance(o, str):
            s = o.replace("**", "")
            for a, b in _PATH_FIX.items():
                s = s.replace(a, b)
            return s
        if isinstance(o, list):
            return [demd(x) for x in o]
        if isinstance(o, dict):
            return {k: demd(v) for k, v in o.items()}
        return o

    out = demd(out)
    left = json.dumps(out, ensure_ascii=False).count("**")
    if left:
        raise SystemExit(f"ABORT 产物里还剩 {left} 处 ** —— 读者会看到星号")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    size = os.path.getsize(OUT)
    print(f"wrote {OUT}  ({size/1024:.1f} KB)")
    print(f"  {out['n_hinges']} 个动摇点 / {out['n_traces']} 条轨迹")
    print(f"  人工裁决 {out['n_audited']} 条，准确率 {out['audit_accuracy']*100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())