#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""p6_u_test 的变异台（修订 202）—— 证明自检**能红**。

⛔ 为什么非要这个：修订 202 一上手时 `p6_u_test_selftest.py` 有 **2 项断言是错的**
（手算错），而同一轮里 `u_pvalue_exact` 有**真 bug**（只数单尾）。
⚠⚠ 若当时只报一句「自检 16/16 全绿」，那两条错断言会**盖住**那个真 bug ——
⚠⚠ 因为错断言是**红**的，红是好事；问题是没人跑它 ⇒ 绿从来没被看见。

⚠⚠⚴ 本台的核心纪律：**每一处变异都必须让判据变红，且红在预期的那一项上。**
⚠⚠⚴ 「变红了但红在别处」和「没变红」同样算失败 —— 前者是仪器指向错了。

用法：
    python3 mut_p6_u_test.py            # 跑全部变异
退出码：0 全部变异都被抓到 / 1 有一个变异存活
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "p6_u_test.py"
SELFTEST = HERE / "p6_u_test_selftest.py"

# (变异名, 原片段, 替换片段, 预期必须红的判据关键词)
MUTS = [
    ("M1 精确 p 退回「2×单尾」",
     "        if abs(s - mu) >= dev - 1e-9:\n            cnt += 1\n"
     "    return cnt / float(total)",
     "        if abs(s - mu) + 1e-9 >= dev - 1e-9 and abs(s - mu) - 1e-9 <= dev - 1e-9:\n"
     "            cnt += 1\n    return min(1.0, 2.0 * cnt / float(total))",
     "T2h"),

    ("M2 缺 device_validated 字段放行",
     "        if dv is None:",
     "        if False:",
     "T4c"),

    ("M3 device_validated=false 也放行",
     "        if dv is False:",
     "        if False:",
     "T4a"),

    ("M4 并列不取平均秩（改成首秩）",
     "        avg = (i + j + 2) / 2.0          # 1-based 秩的平均",
     "        avg = (i + 1) * 1.0              # 变异：并列取首秩而非平均秩",
     "T1b"),

    ("M5 功效警示线调到永不触发",
     "POWER_WARN_N = 20",
     "POWER_WARN_N = 0                    # 变异：small 恒空 ⇒ 警示永不触发",
     "T5a"),

    ("M6 去掉连续性校正",
     "    z = (abs(u - mu) - 0.5) / sqrt(var)     # 连续性校正",
     "    z = abs(u - mu) / sqrt(var)            # 变异：去掉连续性校正",
     "T3a"),

    ("M7 Cliff's delta 分子反号",
     "    return (gt - lt) / float(n1 * n2)",
     "    return (lt - gt) / float(n1 * n2)      # 变异：反号",
     "T2b"),

    ("M8 correct 组底线从 10 改成 0",
     "P6_CORRECT_FLOOR = 10",
     "P6_CORRECT_FLOOR = 0                   # 变异：底线取消",
     "T5b"),

    ("M9 ⛔ 把 device_validated 整个读成 True（闸彻底成死开关）",
     "        dv = d.get(\"device_validated\")",
     "        dv = True                          # 变异：闸被旁路",
     "T4c"),

    ("M10 ⛔ 聚合退回逐行 append（伪重复，n=行数）",
     "        per_traj, n_used, n_no_traj = aggregate_by_traj(rows, field)",
     "        per_traj = {}\n"
     "        for i2, r2 in enumerate(rows):\n"
     "            if r2.get('label') in ('correct','wrong') and r2.get(field) is not None:\n"
     "                per_traj['@r%d' % i2] = (r2['label'], float(r2[field]))\n"
     "        n_used = len(per_traj); n_no_traj = 0    # 变异：每行当一条轨迹",
     "T7b"),

    ("M11 ⛔ --by-position 诊断档给出判决（返回 0）",
     "            print(\"RESULT p6_u_test  DIAGNOSTIC-ONLY  by_position（无判决）\")\n"
     "            return 4",
     "            print(\"RESULT p6_u_test  DIAGNOSTIC-ONLY  by_position（无判决）\")\n"
     "            return 0                        # 变异：伪重复也出判决",
     "T7d"),

    ("M12 ⛔ rows 缺 traj 时静默放行（当每行一条轨迹）",
     "        if n_no_traj:",
     "        if False:                          # 变异：缺 traj 不拦",
     "T7f"),
]


def run_selftest(workdir):
    """在工作目录里跑自检，返回 (退出码, 输出文本)。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run([sys.executable, "p6_u_test_selftest.py"],
                       cwd=str(workdir), capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def main():
    # 基线：不变异必须全绿，否则后面「变异被抓」没有意义
    with tempfile.TemporaryDirectory(prefix="p6u_base_") as td:
        td = Path(td)
        shutil.copy(SRC, td / SRC.name)
        shutil.copy(SELFTEST, td / SELFTEST.name)
        rc0, out0 = run_selftest(td)
        n0 = [l for l in out0.splitlines() if l.startswith("RESULT p6_u_test_selftest")]
    print("基线（未变异）：EXIT=%d  %s" % (rc0, n0[0] if n0 else "〈无 RESULT 行〉"))
    if rc0 != 0:
        print("⛔ 基线本身就不绿 ⇒ 变异台无意义，先修自检。")
        return 1

    base = io.open(SRC, encoding="utf-8").read()
    survivors = []
    for name, old, new, want in MUTS:
        if old not in base:
            print("  %-34s ⛔ 变异点找不到（源已改）" % name)
            survivors.append(name + "（变异点失效）")
            continue
        mutated = base.replace(old, new, 1)
        with tempfile.TemporaryDirectory(prefix="p6u_mut_") as td:
            td = Path(td)
            (td / SRC.name).write_text(mutated, encoding="utf-8")
            shutil.copy(SELFTEST, td / SELFTEST.name)
            rc, out = run_selftest(td)
        reds = [l.strip() for l in out.splitlines() if "FAIL" in l]
        got = [l for l in reds if want in l]
        if rc == 0:
            print("  %-34s ❌ 存活（判据没红）" % name)
            survivors.append(name)
        elif not got:
            print("  %-34s ❌ 红了但红错地方（要 %s，实得 %s）"
                  % (name, want, reds[:2] if reds else "〈无〉"))
            survivors.append(name + "（红错地方）")
        else:
            print("  %-34s ✅ 被抓（%s）" % (name, want))
            for l in reds[:3]:
                print("        %s" % l)

    print("\n=== 汇总 ===")
    if survivors:
        print("RESULT mut_p6_u_test  FAIL  %d 个变异存活：%s" % (len(survivors), survivors))
        return 1
    print("RESULT mut_p6_u_test  OK  %d/%d 变异全部被抓"
          % (len(MUTS), len(MUTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
