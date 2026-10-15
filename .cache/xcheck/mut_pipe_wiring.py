#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r182_verdict_pipeline.py` 步骤 8.5 接线台的**变异台**（修订 202）。

⚠⚠⚴ **本台存在的唯一理由**：
⚠⚠⚴ 修订 195（pos_ok）与 199（resolvable_known）栽的同一个坑是
⚠⚠⚴ 「闸写了、跑通了、打印了，就是没接到出口」。
⚠⚠⚴ 那种 bug 在**任何**正向自检里都是绿的 —— 因为闸确实跑了。
⚗⇒ 唯一能抓它的办法：**把接线拆掉，看判据会不会红**。

每个变异都必须让判据在**预期的那一项**上红；
「变红了但红在别处」与「没变红」同样算失败。

退出码：0 全部被抓 / 1 有变异存活
"""

import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MUT = ROOT / ".cache/mutbak"
PIPE = MUT / "r182_verdict_pipeline.py"
SELFTEST = HERE / "pipe_wiring_selftest.py"

# (变异名, 原片段, 替换片段, 预期必须红的判据关键词)
MUTS = [
    # ⚠⚠⚴ 每一项的「预期红在哪」都是**实测**出来的，不是推的：
    # ⚠⚠⚴ 第一版我按直觉填了 W2a/W3a/W3b，实测三个全错位或存活。
    ("W-M1 ⛔ 拆掉闸后的 return EXIT_BLOCKED（最典型的死开关）",
     '                  % (rc, p6_verdict))\n            return EXIT_BLOCKED',
     '                  % (rc, p6_verdict))\n            p6_verdict = "RUN"   # 变异：不阻断',
     "W2c"),

    ("W-M2 ⛔ 阻断时把 verdict 改记成 RUN（结果行说谎；曾是死赋值）",
     '            p6_verdict = "BLOCKED(rc=%d)" % rc',
     '            p6_verdict = "RUN"          # 变异：掩盖阻断',
     "W2b2"),

    ("W-M3 ⛔ 步骤 8.5 根本不调用仪器（本步成装饰）",
     '        rc, out = run([sys.executable, str(P6_U),\n'
     '                       "--rows", a.r6_rows, "--field", a.p6_field])',
     '        rc, out = (0, "变异：没调用 p6_u_test")   # 变异：跳过',
     "W2b"),

    ("W-M4 ⛔ RESULT 行不再记 u_verdict（「没跑」不可见）",
     '    print("RESULT pipeline  DONE  n=%d  mode=%s  u_verdict=%s"',
     '    print("RESULT pipeline  DONE  n=%d  mode=%s"',
     "W1a"),

    ("W-M5 ⛔ 未检查时不打印警告（静默通过）",
     '        print("⚠⚠⚴ **本次没有出 P6 的 U 判决。** 上面那个 ELIGIBLE 只是")',
     '        print("（变异：警告被删）")',
     "W1b"),

    # ⚠⚠⚴ 第一版这条**红错了理由**：我只改了 print 的第一行，留下
    # ⚠⚠⚴ `% (rc, p6_verdict)` 两个实参去填一个 `%d` ⇒ 抛 TypeError，
    # ⚠⚠⚴ 于是它是被「崩溃」抓到的，**不是**被「阻断路径印了 DONE」抓到的。
    # ⚗⇒ 「红了」不等于「被正确的理由抓住」—— 本台的三态（存活 / 抓对 /
    #    抓错）之外，还差第四态：**被无关错误抓住**。
    # ⚗⇒ 修法：整条 print 连占位符一起换掉，参数个数保持一致。
    ("W-M6 ⛔ 阻断路径也印 DONE（必须仍能正常跑完）",
     '            print("RESULT pipeline  BLOCKED  p6-u-test-rc=%d  u_verdict=%s"\n'
     '                  % (rc, p6_verdict))',
     '            print("RESULT pipeline  DONE  p6-u-test-rc=%d  u_verdict=%s"\n'
     '                  % (rc, p6_verdict))',
     "W2c"),
]


def run_selftest(pipe_path):
    env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    r = subprocess.run([sys.executable, str(SELFTEST), str(pipe_path)],
                       capture_output=True, text=True, env=env, cwd=str(ROOT))
    return r.returncode, r.stdout + r.stderr


def reached_85(out):
    """W3（有效产物）那次运行**真的**跑到步骤 8.5 了吗？

    ⚠⚠⚴ 这道守卫是被迫加的，而且它自己也错了一版：
    ⚠⚠⚴ 第一版把变异副本放在 MUT 的**子目录**，而流水线用
    ⚠⚠⚴ `Path(__file__).resolve().parents[2]` 推 ROOT —— 深度一变，
    ⚠⚠⚴ ROOT 从仓库根变成 `.cache`，`DRIFT/PRECOND` 找不到，
    ⚠⚠⚴ 每次变异都在第 1 步 `EXIT_USAGE` 返回，**一步 8.5 都没跑**，
    ⚠⚠⚴ 而判据「有红就算抓到」把**仪器故障**读成了**检出成功**（5 个假 ✅）。
    ⚠⚠⚴ 第二版又因为扫错地方（自检把流水线输出收进了缓冲）把好台架误报成坏的。
    ⚗⇒ 两条固化：① 副本必须与原文件**同深度**；② 任何变异台都要先验
    ⚗   「这次测量本身有效吗」，否则台架的绿与红都没有意义。
    """
    return "[台架] W3-有效 到达 8.5：是" in out


def main():
    base = io.open(PIPE, encoding="utf-8").read()

    # 基线：不变异必须全绿，否则「变异被抓」没有意义
    rc0, out0 = run_selftest(PIPE)
    n0 = [l for l in out0.splitlines() if l.startswith("RESULT pipe_wiring")]
    print("基线（未变异）：EXIT=%d  %s" % (rc0, n0[0] if n0 else "〈无 RESULT 行〉"))
    if rc0 != 0:
        print("⛔ 基线本身就不绿 ⇒ 变异台无意义，先修接线自检。")
        return 1
    if not reached_85(out0):
        print("⛔ 基线都没跑到步骤 8.5 ⇒ 台架无效（见 reached_85 的说明）。")
        return 1
    print("台架自检：基线确实跑到了 8.5 ✅")

    survivors = []
    # ⚠⚠ 副本必须与原文件**同深度**（直接放在 MUT 里，名字唯一）：
    # ⚠⚠ 放子目录会让 parents[2] 解析错，台架静默失效 —— 就是第一版那个坑。
    victims = []
    try:
        for i, (name, old, new, want) in enumerate(MUTS):
            victim = MUT / ("_mutpipe%d_r182_verdict_pipeline.py" % i)
            victims.append(victim)
            if old not in base:
                print("  %-44s ⛔ 变异点找不到（源已改）" % name)
                survivors.append(name + "（变异点失效）")
                continue
            victim.write_text(base.replace(old, new, 1), encoding="utf-8")
            rc, out = run_selftest(victim)
            reds = [l.strip() for l in out.splitlines() if "FAIL" in l]
            got = [l for l in reds if want in l]
            if not reached_85(out):
                # ⚠⚠ 台架无效 ⇒ **不能**判「抓到」也不能判「存活」，要判「台架坏了」
                print("  %-44s ⚠ 台架无效：这次没跑到 8.5（不算抓到，也不算存活）" % name)
                survivors.append(name + "（台架无效）")
            elif rc == 0:
                print("  %-44s ❌ 存活（判据没红）" % name)
                survivors.append(name)
            elif not got:
                print("  %-44s ❌ 红了但红错地方（要 %s，实得 %s）"
                      % (name, want, [r[:60] for r in reds[:2]]))
                survivors.append(name + "（红错地方）")
            else:
                print("  %-44s ✅ 被抓（%s）" % (name, want))
                for l in reds[:2]:
                    print("        %s" % l)
    finally:
        for v in victims:
            try:
                v.unlink()
            except OSError:
                pass

    print("\n=== 汇总 ===")
    if survivors:
        print("RESULT mut_pipe_wiring  FAIL  %d 个变异存活：%s"
              % (len(survivors), survivors))
        return 1
    print("RESULT mut_pipe_wiring  OK  %d/%d 变异全部被抓" % (len(MUTS), len(MUTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
