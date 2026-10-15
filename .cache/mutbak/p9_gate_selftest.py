#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P9 出口闸自检（修订 195 立）。

针对的缺陷：`r6_rerun.py` 的 P9 在**全量分支**不是硬闸。
    smoke 分支   return 0 if pos_ok else 1     <= 硬闸
    全量分支     return 0                        <= 无条件，pos_ok 只被打印/写 json

⚠ 按修订 8 §8.3 的同一条纪律：**旧闸门必须被原样抄进本自检当参照**，
⚠ 并断言「同一份数据，旧闸门 PASS（退出 0）、新闸门 FAIL（退出 1）」。
⚗ 只测新闸门的话，「它比旧的严」这句话没有人验。

判据跑前写死，8 项：
  G1  P9 FAIL  ⇒ 新闸退出码 1（不是 0）
  G2  P9 FAIL  ⇒ 产物里 device_validated 落进 **false**
  G3  P9 PASS  ⇒ 新闸退出码 0（闸门可满足，不是永远红）
  G4  P9 PASS  ⇒ device_validated 落进 true
  G5  **对照**：同一份 P9 FAIL 的数据，旧闸门退出 0 ⇒ 旧闸恒绿
  G6  payload 里原有的键一个都不能少（不能为了加字段把别的挤掉）
  G7  `pos_ok` 字段本身仍保留（旧下游可能在读它）
  G8  闸只收紧不放松：P9 FAIL 时新闸必须比旧闸**更严**（1 > 0）

用法：python3 p9_gate_selftest.py     退出码 0 = 全过，1 = 有项红
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FAILS = []


def check(name, cond, detail=""):
    print("  %-46s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)
    return cond


def old_finalize_exit(payload, path, pos_ok):
    """**旧全量分支的原件**，照抄不改一个字，用作参照。

    ⚠ 旧件里 pos_ok 确实被写进 json，但**退出码与它无关**。
    """
    json.dump(dict(payload, pos_ok=pos_ok),
              open(path, "w"), ensure_ascii=False, indent=1)
    return 0


def check_no_bare_return0(path):
    """G9：main() 里不得再出现 `return 0` 字面量。

    ⚠⚠ 这一项是给**自检自己**补的漏：G1–G8 全都在测 `finalize` 这一个函数，
    ⚠⚠ 若有人把全量分支的 `finalize(...)` 调用删掉、只留下自检，
    ⚠⚠ 那 8 项照样全绿 —— **守卫按「函数」圈定范围时，它能漏多少就已经定死了。**
    ⚗⇒ 必须再有一条从**调用点**那一侧看的结构性判据。
    """
    import ast
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "main")

    # ⚠ 禁令的**起点**是 p9_verdict 的调用行，不是函数开头。
    # ⚠ `--train-only` 分支在 p9_verdict 之前就 `return 0`，那是**合法的**：
    # ⚠ 它不加载模型、不跑装置，没有装置读数可言，也就谈不上「未验证的行」。
    # ⚗ 第一版把禁令铺满整个 main()，结果在 train-only 的合法 return 上误报 —— 
    # ⚗ 守卫误报一次，之后就没人信它了（同「恒红且红错理由」）。
    anchor = None
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "p9_verdict"):
            anchor = n.lineno
    if anchor is None:
        check("G9c 找到 p9_verdict 调用点", False, "main() 里没有 p9_verdict 调用")
        return False
    check("G9c 找到 p9_verdict 调用点", True)

    bad = [n.lineno for n in ast.walk(fn)
           if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
           and n.value.value == 0 and n.lineno > anchor]
    n_call = sum(1 for n in ast.walk(fn)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "finalize")
    check("G9a p9_verdict 之后无裸 `return 0`", not bad,
          "仍在第 %s 行（p9_verdict 在第 %d 行）" % (bad, anchor))
    check("G9b finalize 至少被调用两次（smoke+全量）", n_call >= 2,
          "实得 %d 处" % n_call)
    return not bad and n_call >= 2


def main():
    try:
        from r6_rerun import finalize
    except Exception as e:            # noqa: BLE001
        print("[错误] 导入 r6_rerun.finalize 失败：%r" % (e,))
        return 2

    tmp = tempfile.mkdtemp(prefix="p9gate_")

    # ---- 样本 1：P9 判 FAIL（照抄 r6_smoke_L19m0.json 的真实读数）----
    payload_fail = {
        "bench_v": {
            "p00__no_think": {"mode": "no_think", "ok": True},
            "p00__think": {"mode": "think", "ok": False, "why": ["+w 不单调升"]},
            "p01__no_think": {"mode": "no_think", "ok": False,
                              "why": ["+w 效应 1.0 未超过随机方向 1.0"]},
        },
        "rows": [{"traj": "t", "mark_w+_1.0": 1.0}, {"traj": "t2", "mark_w+_1.0": 2.0}],
        "class_gap": 231.978,
        "label_coverage": {"n_traj": 120},
    }
    # ---- 样本 2：P9 全过（构造一条干净的，读数满足新判据）----
    payload_pass = {
        "bench_v": {
            "p00__no_think": {"mode": "no_think", "ok": True},
            "p00__think": {"mode": "think", "ok": True},
        },
        "rows": [{"traj": "t", "mark_w+_1.0": 1.0}],
        "class_gap": 300.0,
        "label_coverage": {"n_traj": 30},
    }

    print("=== G1/G2/G6/G7：P9 FAIL 时 ===")
    p = os.path.join(tmp, "fail.json")
    rc_fail = finalize(payload_fail, p, False)
    got = json.load(open(p, encoding="utf-8"))
    check("G1 退出码为 1", rc_fail == 1, "实得 %r" % (rc_fail,))
    check("G2 device_validated 为 False", got.get("device_validated") is False,
          "实得 %r" % (got.get("device_validated"),))
    check("G6 原有键一个没少", all(k in got for k in payload_fail),
          "缺 %s" % [k for k in payload_fail if k not in got])
    check("G7 pos_ok 仍保留", got.get("pos_ok") is False,
          "实得 %r" % (got.get("pos_ok"),))

    print("\n=== G3/G4：P9 PASS 时（闸门必须可满足）===")
    p2 = os.path.join(tmp, "pass.json")
    rc_pass = finalize(payload_pass, p2, True)
    got2 = json.load(open(p2, encoding="utf-8"))
    check("G3 退出码为 0", rc_pass == 0, "实得 %r" % (rc_pass,))
    check("G4 device_validated 为 True", got2.get("device_validated") is True,
          "实得 %r" % (got2.get("device_validated"),))

    print("\n=== G5/G8：旧闸门在同一份 FAIL 数据上 ===")
    p3 = os.path.join(tmp, "old.json")
    rc_old = old_finalize_exit(payload_fail, p3, False)
    old = json.load(open(p3, encoding="utf-8"))
    check("G5 旧闸门在同一数据上退出 0（恒绿）", rc_old == 0, "实得 %r" % (rc_old,))
    check("G8 新闸更严（1 > 0）", rc_fail > rc_old,
          "新 %r 旧 %r" % (rc_fail, rc_old))
    print("  ⚗ 旧件把 pos_ok=false 写进了 json 却仍退出 0 ——")
    print("     ⇒ 下游若只看退出码，会把未验证的行当成已验证的。")
    print("     本项是新闸存在的全部理由。")

    print("\n=== G9：调用点那一侧的结构性判据 ===")
    r6 = HERE / "r6_rerun.py"
    check_no_bare_return0(r6)

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT p9_gate_selftest  FAIL  %d 项红：%s" % (len(FAILS), FAILS))
        return 1
    print("RESULT p9_gate_selftest  OK  10/10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
