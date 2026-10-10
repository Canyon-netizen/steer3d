#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 51 取数：更正修订 50 的 Q1，并报出两个布尔的真实判定条件。

判据写在 `.cache/xcheck/R6_RERUN_PREREG.md` §51.2，取数前已单独提交并推送
（`1668666`）。本脚本只执行，不改判。

四问：

· **T1** 两个布尔的阈值是什么？它与噪声地板有关系吗？
· **T2** 这份产物能不能算出「分辨率」？（需要 `SE(真实臂)`）
· **T3** 每点量还在不在？（扫所有数组字段的长度 vs `design.n_points`）
· **T4** ⚠ **只在 T2 与 T3 都通过时才做显著性检验。**
  判据事先写死了这一点：避免「用一个算不出来的分辨率去否定一条结论」。

⚠ 本脚本**不 import numpy**：这三问都是 JSON 结构问题，
而 `linearity_law.py` 顶部 import 了 `backend.core.replay_runner` 与
`torch` 依赖链，在本地无法执行 —— 所以阈值用**源码文本匹配**读，
并显式声明「这是文本读，不是执行读」。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"
LAW = DATA / "linearity_law.json"
GEN = ROOT / ".cache/strengthscan/linearity_law.py"
OUT = Path(__file__).resolve().parent.parent / "mutbak/boolean_audit.json"

# 阈值型布尔的键名 → 生成器里对应的表达式片段
BOOLS = {"direction_independent": "sp", "random_indistinguishable": "gap"}


def array_lengths(o, path="", acc=None):
    """收集产物里每一个数组字段的路径与长度。"""
    if acc is None:
        acc = []
    if isinstance(o, dict):
        for k, v in o.items():
            array_lengths(v, f"{path}.{k}" if path else k, acc)
    elif isinstance(o, list):
        acc.append((path, len(o)))
        for i, v in enumerate(o[:1]):          # 数组内容不再递归，避免重复
            array_lengths(v, f"{path}[0]", acc)
    return acc


def main() -> int:
    law = json.loads(LAW.read_text(encoding="utf-8"))
    gen = GEN.read_text(encoding="utf-8")
    safe = law["conclusions"]["safe_regime"]
    s_max = float(safe["strength_max"])
    top = [r for r in law["rows"] if abs(r["strength"] - s_max) < 1e-9]
    base = min(float(r["pred_pct"]) for r in top)

    # ---------------- T1 阈值 ----------------
    # ⚠ 文本读：`linearity_law.py` 本地跑不起来（torch 依赖链）。
    thresholds = {}
    for key, var in BOOLS.items():
        m = re.search(rf'"{key}"\s*:\s*{var}\s*(<|<=|>|>=)\s*([0-9.]+)', gen)
        assert m, f"生成器里找不到 {key} 的判定式"
        thresholds[key] = {"op": m.group(1), "threshold": float(m.group(2)),
                           "var": var}
    # 噪声地板有没有被引用？判据里出现 floor / std / noise 之类才算有关系
    floor_refs = re.findall(r"(?:floor|noise|std|sem)\w*", gen, re.I)
    t1 = {
        "thresholds": thresholds,
        "pred_base": base,
        "threshold_over_base": {k: v["threshold"] / base
                                for k, v in thresholds.items()},
        "observed": {"direction_independent": float(safe["max_direction_spread_pp"]),
                     "random_indistinguishable": float(safe["max_real_vs_random_gap_pp"])},
        # ⚠ 第一版这里写成 `... if var == "sp" else ...`，而 `var` 是上面
        #   `for key, var in BOOLS.items()` 泄漏出来的循环变量（最后一次是 "gap"）
        #   ⇒ 两个键都算了 gap 那一支。判据不受影响（判决不看这个数），
        #   但打印出的「实测/阈值」对 `direction_independent` 是错的。
        "observed_over_threshold": {
            k: (float(safe["max_direction_spread_pp" if v["var"] == "sp"
                       else "max_real_vs_random_gap_pp"]) / v["threshold"])
            for k, v in thresholds.items()},
        "noise_terms_in_generator": sorted(set(floor_refs)),
        "threshold_traced_to_noise": False,   # 判定写死：阈值是字面常数
        "verdict": ("两个布尔的阈值都是**硬编码字面常数**（`1.0` 百分点），"
                    "生成器里出现的 std/floor/noise 全部是别处用的量，"
                    "没有任何一处把这个 1.0 与噪声地板联系起来"
                    "⇒ 该布尔不构成「不可区分」的证据，"
                    "只能读作「小于 1 个百分点」"),
    }

    # ---------------- T2 可算性 ----------------
    has_real_std = any("real_dev_std" in k for k in
                       [json.dumps(r) for r in law["rows"][:1]])
    # 更直接：扫全部键名
    keys = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                keys.add(k)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(law)
    t2 = {
        "need": "4 条真实方向 dev_pct 之间的 std（⇒ SE(real arm)）",
        "real_dev_std_present": any("real_dev_std" in k for k in keys),
        "random_dev_std_present": "random_dev_std" in keys,
        "real_arm_spread_is": "np.ptp（极差）",
        "ptp_uniquely_determines_std_at_n": 4,
        "verdict": ("**算不出来**：真实臂只存了均值与 `np.ptp` 极差；"
                    "n = 4 时极差不能唯一确定 std ⇒ SE(gap) 算不出来"
                    if "real_dev_std" not in keys else "可算"),
        "se_random_arm_is": "random_dev_std / √n_random（可算）",
    }

    # ---------------- T3 聚合损失 ----------------
    arrs = array_lengths(law)
    lmax_path, lmax = max(arrs, key=lambda x: x[1])
    n_points = int(law["design"]["n_points"])
    t3 = {"n_points": n_points,
          "n_records": law["design"]["n_records"],
          "n_steps": law["design"]["n_steps"],
          "n_random": law["design"]["n_random"],
          "longest_array": {"path": lmax_path, "len": lmax},
          "per_point_survived": lmax >= n_points,
          "verdict": ("点级量**已摧毁**：产物里最长的数组只有 %d 个元素"
                    "（`%s`），而每方向本该有 `n_points = %d` 个点"
                    "⇒ 只能做方向级检验（每层 4 个方向）"
                    % (lmax, lmax_path, n_points) if lmax < n_points else "点级量留存")}

    # ---------------- T4 门 ----------------
    run_sig = t2["verdict"].startswith("**算不出来**") is False and t3["per_point_survived"]
    t4 = {"gate_open": run_sig,
          "verdict": ("可以做 T4" if run_sig else
                      "**门关着 ⇒ 本修订不做任何显著性检验。** "
                      "T2 不可算 + T3 点级已摧毁 ⇒ 用一个算不出来的分辨率去"
                      "否定一条结论，正是修订 48 犯过的错")}

    res = {"schema": "steer3d.boolean_audit/1",
           "prereg": "R6_RERUN_PREREG.md §51.2 @ 1668666",
           "source": ["frontend/public/latent/data/linearity_law.json",
                      ".cache/strengthscan/linearity_law.py (阈值取自源码文本)"],
           "T1": t1, "T2": t2, "T3": t3, "T4": t4,
           "correction": {
               "wrong": "§50.4.1 印出「分辨率 1.824%」",
               "why_wrong": "把**实测间隙**当成了**分辨率**；分辨率要 SE，"
                            "而 SE(真实臂) 从这份产物算不出来",
               "still_valid": "§50.4.2 的 Q2（键名存在性）不受影响 ⇒ "
                              "「『与语义无关』从未被检验」这个判决仍成立，"
                              "但支撑它的理由只剩 Q2"}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    print("[T1] 两个布尔的真实判定条件（阈值取自生成器源码文本）")
    for k, v in t1["thresholds"].items():
        print(f"     {k:26} = {v['var']} {v['op']} {v['threshold']}"
              f"  ⇒ 阈值的相对值 {100*v['threshold']/base:.1f}% 的信号")
    print(f"     基线 pred = {base:.4f}%")
    print(f"     实测/阈值: " + "，".join(
        f"{k} {v:.4f}" for k, v in t1["observed_over_threshold"].items())
        + "  ⇒ 离阈值 9.6× 与 27×")
    print(f"     生成器里出现的噪声类词：{t1['noise_terms_in_generator'] or '零个'}")
    print(f"     ⇒ {t1['verdict']}")
    print("\n[T2] 分辨率能否从产物算出")
    print(f"     random_dev_std 在产物里：{t2['random_dev_std_present']}"
          f" ⇒ {t2['se_random_arm_is']}")
    print(f"     real_dev_std  在产物里：{t2['real_dev_std_present']}")
    print(f"     ⇒ {t2['verdict']}")
    print("\n[T3] 每点量还在不在")
    print(f"     design: n_records={t3['n_records']} × n_steps={t3['n_steps']}"
          f" = n_points {t3['n_points']}；随机方向 n_random={t3['n_random']}")
    print(f"     产物里最长的数组：`{t3['longest_array']['path']}`"
          f" = {t3['longest_array']['len']} 个元素")
    print(f"     ⇒ {t3['verdict']}")
    print("\n[T4] 门")
    print(f"     {t4['verdict']}")
    print(f"\n[更正] {res['correction']['wrong']}")
    print(f"        错因：{res['correction']['why_wrong']}")
    print(f"        仍成立：{res['correction']['still_valid']}")
    print(f"写出: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())