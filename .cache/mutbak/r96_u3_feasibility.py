#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 96：U3 判据的机制可行性检验。

⚠ 背景：`check_u3()` 的名字叫「U3 L5 分域陈述」，docstring 自陈弱点
  「查不出『分域了但分错域』」。
⚠⚴ 但真正的毛病更靠前：**它只查「注入」「预测」两个子串是否出现**，
  连「它们在分域」都不验 ⇒ **名字比判据强**（与预登记 §87.4 的
  `counts.n_objlit`、§92 的 counts 混口径同型）。

本脚本做两件事：
  (1) **先证明假绿真实存在** —— 造几条「明明不是分域陈述」的文本，
      看现行 U3 是不是照样判绿。假绿不存在 ⇒ 就没有加强的动机。
  (2) **再验加强版的机制可行性** —— 任何候选规则必须
      **既把假绿判红、又保住真实的那条 L5 文本为绿**。
      保住不了一条真文本的规则 ⇒ 不可行，不能立。

⚠ 本脚本**不改** check_bpath_static.py，只发数。
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / ".cache/xcheck/check_bpath_static.py"
ARTIFACT = ROOT / "frontend/public/latent/data/bpath_marker_steering.json"

spec = importlib.util.spec_from_file_location("cbpath", GUARD)
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)


def l5_here():
    j = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    return next(r["here"] for r in j["ladder_mapping"] if r.get("level") == "L5")


# ── 候选加强规则 ───────────────────────────────────────────────────
def r1_current(t):
    """现行：两个子串同时出现。"""
    return ("注入" in t) and ("预测" in t)


def r2_value_near(t, k=40):
    """两个域标签各自**后面 k 字内**要有值（数字或有/无/是/则）。"""
    def has_value(pos):
        seg = t[pos:pos + k]
        return bool(re.search(r"[0-9]|有|无|是|则|并非|全部|都", seg))
    a = t.find("注入")
    b = t.find("预测")
    if a < 0 or b < 0:
        return False
    return has_value(a) and has_value(b)


def r3_diff_clause(t):
    """两个域标签必须落在**不同子句**里（中间隔 。；，）。"""
    a, b = t.find("注入"), t.find("预测")
    if a < 0 or b < 0:
        return False
    lo, hi = min(a, b), max(a, b)
    return bool(re.search(r"[。；，]", t[lo:hi]))


def r4_contrast(t):
    """两个域之间要有对比连接词（是/则/而/但/并非）。"""
    a, b = t.find("注入"), t.find("预测")
    if a < 0 or b < 0:
        return False
    lo, hi = min(a, b), max(a, b)
    return bool(re.search(r"是|则|而|但|并非|则|≠", t[lo:hi]))


def r5_label_and_value(t):
    """域标签必须带「域」字，且各自后面有值。"""
    out = []
    for w in ("注入", "预测"):
        m = re.search(w + r"[^\s，。；]{0,4}域", t)
        if not m:
            return False
        out.append(bool(re.search(r"[0-9]|有|无|是|则|并非", t[m.end():m.end() + 40])))
    return all(out)


RULES = [("R1 现行（两子串）", r1_current),
         ("R2 两域后 40 字内有值", r2_value_near),
         ("R3 两域分属不同子句", r3_diff_clause),
         ("R4 两域之间有对比词", r4_contrast),
         ("R5 带「域」标签且各有值", r5_label_and_value)]

# ── 假绿样本：都含「注入」「预测」，但都不是分域陈述 ────────────────
FALSES = [
    ("M1 两域并列、无任何陈述",
     "剂量扫描 6 个剂量点；⚠ 注入域与预测域的随机臂情况见附注。"),
    ("M2 把两词当普通名词并列",
     "本批做了注入与预测两类读出，都没有随机对照。"),
    ("M3 单一声称覆盖两域（且与数据相反）",
     "⚠ 注入域、预测域**均未**做随机方向对照（实测注入域有 6 个）。"),
    ("M4 两域的值对调（分域了但分错域）",
     "正交度探针在**注入读出域**的随机臂是 **0**；"
     "**预测域**反而有逐位点独立种子的同范数随机臂。"),
    ("M5 两词只出现在括号附注里，正文是单域断言",
     "本项目级断言：没有任何随机方向对照（细节见注入与预测两处）。"),
]

NEG = ("剂量扫描 6 个剂量点、**没有任何随机方向对照**；"
       "⚠ 但正交度探针在**注入读出域**有同范数随机臂；"
       "**预测域**的随机臂则是 **0**")


def main():
    real = l5_here()
    print("=" * 78)
    print("修订 96 · U3 的机制可行性检验（诊断探针，不改判据）")
    print("=" * 78)
    print(f"\n[真实 L5 here] {len(real)} 字，含「注入」{'注入' in real}、"
          f"「预测」{'预测' in real}")
    print(f"  片段：…{real[60:170]}…")

    # ── (1) 假绿是否真实存在 ──────────────────────────────────────
    print("\n" + "=" * 78)
    print("(1) 现行 U3 判红哪些？—— 若全绿，则「名字比判据强」成立")
    print("=" * 78)
    n_falsegreen = 0
    for name, txt in FALSES:
        j = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        for r in j["ladder_mapping"]:
            if r.get("level") == "L5":
                r["here"] = txt
        p = Path(cb.__file__).parent / "mutbak" / "u3_probe_tmp.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
        res = cb.check_u3(p)
        p.unlink()
        green = res["ok"]
        if green:
            n_falsegreen += 1
        print(f"  {name:<34} 现行U3 判绿 = {green}"
              + ("   ← ⚠ **假绿**" if green else ""))
    print(f"\n  ⇒ {len(FALSES)} 条假样本里现行 U3 判绿 **{n_falsegreen}** 条")

    print(f"\n[负对照] 一条**真的**分域陈述 ⇒ 现行 U3 判绿 = {r1_current(NEG)}"
          f"（必须为 True，否则判据连正确的都抓不住）")
    assert r1_current(NEG), "负对照失效：现行 U3 连正确陈述都判红"

    # ── (2) 加强版的机制可行性 ────────────────────────────────────
    print("\n" + "=" * 78)
    print("(2) 候选规则的可行性：**必须既判红假样本、又保住真样本为绿**")
    print("=" * 78)
    print(f"\n  {'规则':<24}{'真样本绿':<10}{'假样本红':<10}可行")
    viable = []
    for name, fn in RULES:
        real_green = fn(real)          # ⚠ 真实 L5 here（不是简化版）
        n_red = sum(1 for _n, t in FALSES if not fn(t))
        ok = real_green and n_red == len(FALSES)
        if ok:
            viable.append(name)
        print(f"  {name:<24}{str(real_green):<10}{f'{n_red}/{len(FALSES)}':<10}"
              f"{'✅ 可行' if ok else '❌ 不可行'}")
        if not real_green:
            print(f"      ⚠ 对**真实**的那条 L5 here 判红 ⇒ 直接出局")

    print(f"\n[结论]")
    print(f"  现行 U3：{len(FALSES)} 条假样本里判绿 {n_falsegreen} 条"
          f" ⇒ 「U3 L5 分域陈述」这个名字**强于它实际判的东西**。")
    if viable:
        print(f"  可行的加强版：{', '.join(viable)}")
        print(f"  ⚠ **但这些都仍查不出「分域了但分错域」**（M4 全过）——")
        print(f"    因为那需要核**值**，属于另一类判据，不是文本子串判据。")
    else:
        print(f"  ⚠ **没有任何候选规则可行** ⇒ 按「立判据前先验机制可行性」，")
        print(f"    本轮**不立加强版 U3**，只把「名字强于判据」登记下来。")


if __name__ == "__main__":
    main()