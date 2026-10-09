"""标签供给外推：按当前速率，到多少题才够 P6 的门槛？

**这不是判决，是可行性核算。** P6 的停止规则按**题号**（与标签无关），
本脚本只用标签来回答一个问题：「按现在这个速率，跑到预登记的 60 题，
correct/wrong 两组能不能同时过门槛？」

用法：python3 label_supply_projection.py <strict_label.json> [目标题数...]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

MIN_CORRECT = 10      # 与 r6_verdict.py / 预登记 P6 同源
MIN_WRONG = 8


def wilson(k, n, z=1.96):
    """Wilson 区间：比率的 95% 置信区间，小样本下比正态近似稳。"""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - hw) / d, (c + hw) / d)


def main(inp, targets):
    d = json.load(open(inp, encoding="utf-8"))
    rows = d["rows"]

    # 按题号归并：文件名形如 aime__<split>__pNN__<mode>。
    # ⚠ 题号只在**同一 split 内**唯一：aime25__p19 与 aime26__p19 是两道不同的题。
    #   只取 pNN 会把两道题并成一条，外推出「触顶 130%」这种自相矛盾的东西。
    by = {}
    for r in rows:
        parts = r["traj"].split("__")
        if parts[-1] in ("think", "no_think"):
            pid = "__".join(parts[:-1])          # 含 split，保证跨 split 唯一
        else:
            pid = parts[-1]
        by.setdefault((r["mode"], pid), []).append(r)

    modes = sorted({m for m, _ in by})
    print("=" * 74)
    print(f"输入 {inp}")
    print(f"已抽题数 {len({p for _, p in by})}")
    print("=" * 74)

    summary = {}
    for mode in modes:
        pids = sorted(p for m, p in by if m == mode)
        n = len(pids)
        lab = [by[(mode, p)][0].get("strict", "unlabeled") for p in pids]
        c = sum(1 for s in lab if s == "correct")
        w = sum(1 for s in lab if s == "wrong")
        t = sum(1 for r in rows if r["mode"] == mode and r.get("truncated"))
        rc, rw = wilson(c, n), wilson(w, n)
        summary[mode] = {"n_problems": n, "correct": c, "wrong": w,
                         "truncated": t, "rate_correct": c / n if n else 0,
                         "rate_wrong": w / n if n else 0,
                         "wilson_correct": rc, "wilson_wrong": rw}
        print(f"\n[{mode}] n={n} 题   触顶 {t}/{n} ({t / n:.0%})")
        print(f"  correct {c}/{n} = {c / n:.1%}   Wilson95 [{rc[0]:.1%}, {rc[1]:.1%}]")
        print(f"  wrong   {w}/{n} = {w / n:.1%}   Wilson95 [{rw[0]:.1%}, {rw[1]:.1%}]")

        # 每个模式到多少题才够门槛（用点估计）
        need = []
        if c:
            need.append(("correct>=%d" % MIN_CORRECT,
                         math.ceil(MIN_CORRECT / (c / n))))
        if w:
            need.append(("wrong>=%d" % MIN_WRONG, math.ceil(MIN_WRONG / (w / n))))
        for tag, k in need:
            print(f"  -> {tag} 需约 {k} 题")

    print()
    print("=" * 74)
    print(f"外推到目标题数（点估计；括号内为 Wilson 下界，保守读法）")
    print("=" * 74)
    for tgt in targets:
        print(f"\n--- {tgt} 题 ---")
        for mode in modes:
            s = summary[mode]
            pc = s["rate_correct"] * tgt
            pw = s["rate_wrong"] * tgt
            pc_lo = s["wilson_correct"][0] * tgt
            pw_lo = s["wilson_wrong"][0] * tgt
            ok = (pc >= MIN_CORRECT) and (pw >= MIN_WRONG)
            ok_lo = (pc_lo >= MIN_CORRECT) and (pw_lo >= MIN_WRONG)
            flag = "✅ 过" if ok else "❌ 不过"
            print(f"  [{mode}] correct≈{pc:5.1f}  wrong≈{pw:5.1f}   {flag}"
                  f"   保守读法 correct≈{pc_lo:.1f} wrong≈{pw_lo:.1f} "
                  f"{'✅' if ok_lo else '❌'}")

    print()
    print("=" * 74)
    print("读法提醒")
    print("=" * 74)
    print("· 这是**可行性核算**，不是判决；P6 的停止规则仍按题号，与标签无关。")
    print("· 某模式若外推 wrong≈0，不是「跑够题数就能修好」，而是")
    print("  「该模式的答错轨迹与标签产出是耦合的」——加题数不解除这一条。")
    print("· Wilson 下界是对「速率估计本身有不确定性」的保守读法。")

    out = {"input": inp, "summary": summary,
           "targets": {str(t): {m: {"correct": summary[m]["rate_correct"] * t,
                                    "wrong": summary[m]["rate_wrong"] * t}
                               for m in modes} for t in targets},
           "min_correct": MIN_CORRECT, "min_wrong": MIN_WRONG}
    Path(inp).with_name(Path(inp).stem + "_projection.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n写出", Path(inp).with_name(Path(inp).stem + "_projection.json"))


if __name__ == "__main__":
    tg = [int(a) for a in sys.argv[2:]] or [30, 60, 90, 120]
    main(sys.argv[1], tg)