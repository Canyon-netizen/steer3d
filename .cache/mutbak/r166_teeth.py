"""`p6_readiness.py` 的批次身份闸 —— 收进 cap 32768 后的**牙齿测试**。

⚠⚠⚴⚠⚴ 为什么必须有
──────────────────
32768 轮已于 17:00 在 zju-53 卡 3 起跑（60 条 / 30 题），而
`p6_readiness.py` 的 `NEW_CAP = 8192` ⇒ 32768 会落进 `MISMATCH`（return 4）
⇒ **花 4.8 h 算出来的数据会被身份闸当「身份不明」拒掉。**

⚠⚠⚴⚠ **⚗⚠ 但修法不是把 `NEW_CAP` 改成 32768 —— 那样会让已有的 cap 8192
批次（gen_b2）反过来变成「身份不明」，那是倒退。⚗⚠**
⚠⚠ **正确修法：承认一组【已知批次 cap】，同时【继续禁止混池】。**

⚠ 五条牙齿（每条只改一个变量）：
  T1 全部 cap=32768        ⇒ 必须**不再** MISMATCH（证 32768 进了已知身份集）
  T2 混 cap 8192+32768     ⇒ 必须仍 MISMATCH（⚠ 最要紧：证「不混池」没被放宽）
  T3 全部 cap=8192         ⇒ 必须**不再** MISMATCH（回归护栏：旧「新批」没被顶掉）
  T4 全部 cap=2048         ⇒ 必须走 OLD_BATCH（证旧批路由没坏）
  T5 `P6_CORRECT_FLOOR`    ⇒ 必须仍是 10（⚠ 证这次只动身份、没动判决门槛）

⚠⚠⁴ T2 与 T5 才是这次改动的**真风险面**：
  ⚗ T1 只要「放行」就算过，⚗ 但**放宽身份集**最容易顺手把「混池」也放宽了；
  ⚗ 而 T5 挡的是「改身份时顺手把 P6 底线也改了」——那种改动会让结论整个作废。
"""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".cache/xcheck/p6_readiness.py"
FULL = ROOT / ".cache/mutbak/strict_label_b2_full60.json"
FIXDIR = Path(__file__).resolve().parent / "r166_teeth"
PY = sys.executable


def build(name, cap_of):
    """按 cap_of(traj) 给每条行改 cap，写出注入样本。"""
    blob = json.loads(FULL.read_text(encoding="utf-8"))
    rows = blob["rows"]
    for r in rows:
        r["cap"] = cap_of(r["traj"], r["cap"])
    caps = sorted({r["cap"] for r in rows})
    FIXDIR.mkdir(parents=True, exist_ok=True)
    p = FIXDIR / (name + ".json")
    p.write_text(json.dumps({"n": len(rows), "counter": blob["counter"],
                             "ghosts": blob["ghosts"], "rows": rows},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    return p, caps


def run(label_path):
    p = subprocess.run([PY, str(SCRIPT), "--label", str(label_path)],
                       capture_output=True, text=True, cwd=str(ROOT))
    out = p.stdout + p.stderr
    res = [l for l in out.splitlines() if l.startswith("RESULT p6_readiness")]
    return p.returncode, (res[0] if res else "(没有 RESULT 行)")


def verdict_of(result_line):
    parts = result_line.split()
    return parts[2] if len(parts) > 2 else "?"


def main():
    src = SCRIPT.read_text(encoding="utf-8")
    base_rows = json.loads(FULL.read_text(encoding="utf-8"))["rows"]
    half = len(base_rows) // 2

    print("=== 注入样本 ===")
    f32768, c1 = build("all_32768", lambda t, c: 32768)
    fmixed, c2 = build("mixed_8192_32768",
                      lambda t, c: 32768 if base_rows.index(
                          next(r for r in base_rows if r["traj"] == t)) >= half else 8192)
    f8192, c3 = build("all_8192", lambda t, c: 8192)
    f2048, c4 = build("all_2048", lambda t, c: 2048)
    for f, caps in ((f32768, c1), (fmixed, c2), (f8192, c3), (f2048, c4)):
        print("  %-22s cap=%s  n=%d" % (f.name, caps, len(json.loads(
            f.read_text(encoding='utf-8'))["rows"])))

    teeth = []

    # T1 —— 32768 进了已知身份集
    rc, line = run(f32768)
    v = verdict_of(line)
    teeth.append(("T1 纯 32768 不再 MISMATCH", v != "MISMATCH", "rc=%d %s" % (rc, line[:78])))

    # T2 —— ⚠ 最要紧：混池仍必须被拒
    rc, line = run(fmixed)
    v = verdict_of(line)
    teeth.append(("T2 混 8192+32768 仍 MISMATCH", v == "MISMATCH", "rc=%d %s" % (rc, line[:78])))

    # T3 —— 回归护栏：旧的「新批」8192 没被顶掉
    rc, line = run(f8192)
    v = verdict_of(line)
    teeth.append(("T3 纯 8192 不再 MISMATCH", v != "MISMATCH", "rc=%d %s" % (rc, line[:78])))

    # T4 —— 旧批路由没坏
    rc, line = run(f2048)
    v = verdict_of(line)
    teeth.append(("T4 纯 2048 走 OLD_BATCH", v == "OLD_BATCH", "rc=%d %s" % (rc, line[:78])))

    # T5 —— 判决门槛没被动
    ok5 = "P6_CORRECT_FLOOR = 10" in src
    got = [l.strip() for l in src.splitlines() if l.strip().startswith("P6_CORRECT_FLOOR")]
    teeth.append(("T5 P6 底线仍是 10", ok5, "源码行: %s" % (got[0] if got else "(没找到)")))

    print("\n=== 牙齿 ===")
    npass = 0
    for name, ok, detail in teeth:
        print("  [%s] %-32s %s" % ("PASS" if ok else "FAIL", name, detail))
        npass += bool(ok)
    print("\nRESULT r166_teeth  %d/%d" % (npass, len(teeth)))

    print("\n=== 顺带：这次改动的【口径指纹】 ===")
    print("  ⚠ 恒等式断言：本次只动批次身份集，⚗⚠ **没动 P6 底线、没动标签规则**")
    print("  strict_label 仍是唯一标签来源：",
          "strict_label.label()" in src)

    if npass != len(teeth):
        print("\n⚠⚠⚴ 有牙齿没咬住 ⇒ 不许当成通过")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())