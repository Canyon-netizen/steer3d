#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r182_verdict_pipeline.py` 步骤 8.5 的接线自检（修订 202 立）。

⚠⚠⚴ **为什么必须有这个文件**：修订 195（pos_ok）与修订 199（resolvable_known）
⚠⚠⚴ 都栽在同一件事上 —— 闸写了，但**没接到出口**。
⚠⚠⚴ 那种错误在代码里完全看不出来：闸照常跑、照常打印，只是**没人被它挡住**。
⚗⇒ 本台只验接线：**rc 到没到出口、记没记进 RESULT 行**。

⚠ 只替网络（`ssh` 与 `scp`），**其余本地判据全部真跑** ——
⚗ 桩太多的话，测的就是桩而不是接线了。

四组：
  W1 不给 --r6-rows      ⇒ RESULT 必须记 u_verdict=NOT-RUN，且明说「没出判决」
  W2 device_validated=false ⇒ 退出码 4 + RESULT 记 BLOCKED(rc=4)
  W3 有效产物            ⇒ 退出码 0 + RESULT 记 RUN
  W4 --dry-run 计划      ⇒ 必须列出 8.5，且缺参时带警告

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import io
import json
import shutil
import sys
import tempfile
import traceback
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUT = ROOT / ".cache/mutbak"
# ⚠ 允许变异台把**变异副本**指过来（副本放在 MUT 里，ROOT/MUT/XC 才能解析对）。
# ⚠ 第一版这里写死了路径，于是变异台根本没法跑 —— 判据改不动 = 变异台是装饰。
PIPE = Path(sys.argv[1]) if len(sys.argv) > 1 else (MUT / "r182_verdict_pipeline.py")
# ⛔ 用**真实的** 60 行 / cap=32768 标注文件做桩的 scp 源，
# ⛔ 不用人造夹具 —— 人造夹具会让 precond/identity 的行为变样，
# ⛔ 而那正是我要顺路验的东西。
REAL_LABEL = MUT / "r182_1015_003713_label.json"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-56s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load_pipe():
    import importlib.util
    spec = importlib.util.spec_from_file_location("pipe202", PIPE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def mk_r6(path, device_validated, pos_ok, n_c=11, n_w=17, per_traj=3,
          vc=1.0, vw=-1.0, with_traj=True):
    rows = []
    kt = 0
    for lab, n, val in (("correct", n_c, vc), ("wrong", n_w, vw)):
        for _ in range(n):
            tid = "r6tj%03d" % kt
            kt += 1
            for j in range(per_traj):
                r = {"traj": tid, "t": j, "mode": "think", "label": lab,
                     "mark_w+_1.0": val + j * 0.01}
                if not with_traj:
                    r.pop("traj")
                rows.append(r)
    path.write_text(json.dumps(
        {"device_validated": device_validated, "pos_ok": pos_ok, "rows": rows}),
        encoding="utf-8")
    return path


def drive(mod, argv, label=""):
    """跑一次 main()，桩掉网络，返回 (rc, 输出文本)。

    ⚠⚠⚴ 变异台第一版是靠扫 `out` 判「有没有跑到 8.5」的，
    ⚠⚠⚴ 而流水线的输出被 `redirect_stdout` 收进了缓冲、**不会**出现在
    ⚠⚠⚴ 自检的 stdout 里 ⇒ 那个检查永远判「否」，把好台架误报成坏的。
    ⚗⇒ 现在由 drive() 自己把「到达 8.5」**打到真实 stdout**，
    ⚗   台架才有办法验「这次测量本身有效吗」。
    """
    real_run = mod.run
    tmpdir = Path(tempfile.mkdtemp(prefix="pipe_w_", dir=str(MUT)))

    def fake_run(cmd, cwd=None):
        # 只拦 scp：把**真实**标注文件放到 dest，其余一律真跑。
        if cmd and cmd[0] == "scp":
            shutil.copy(REAL_LABEL, cmd[-1])
            return 0, ""
        return real_run(cmd, cwd=cwd)

    def fake_ssh(remote_cmd):
        if "wc -l" in remote_cmd:
            return 0, "60\n"          # 远端跑满
        return 0, ""                  # 标注：产物已由 fake_run 造好

    mod.run = fake_run
    mod.ssh = fake_ssh
    mod.MUT = tmpdir                 # 别把桩产物写进真 mutbak
    old = sys.argv
    sys.argv = ["r182_verdict_pipeline"] + argv
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = mod.main()
    except SystemExit as e:           # argparse 用 SystemExit 报用法错
        rc = e.code if isinstance(e.code, int) else 1
    except Exception:                 # noqa: BLE001
        buf.write("\n[异常]\n" + traceback.format_exc())
        rc = 99
    finally:
        sys.argv = old
        mod.run = real_run
        shutil.rmtree(tmpdir, ignore_errors=True)
    reached = ">>> p6_u_test EXIT=" in buf.getvalue()
    print("    [台架] %s 到达 8.5：%s" % (label or "-", "是" if reached else "否"))
    return rc, buf.getvalue()


def result_line(txt):
    for l in txt.splitlines():
        if l.startswith("RESULT pipeline"):
            return l.strip()
    return "<没有 RESULT 行>"


def main():
    if not REAL_LABEL.exists():
        print("[错误] 缺真实标注文件 %s（不应人工造夹具）" % REAL_LABEL)
        return 2
    try:
        mod = load_pipe()
    except Exception:                 # noqa: BLE001
        print("[错误] 导入流水线失败：\n%s" % traceback.format_exc())
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="pipe_wfix_", dir=str(MUT)))

    print("=== W1：不给 --r6-rows ⇒ 必须自报「未检查」，不得静默 ===")
    rc, txt = drive(mod, [], "W1-无参")
    line = result_line(txt)
    check("W1a RESULT 行必须记 u_verdict=NOT-RUN",
          "u_verdict=NOT-RUN" in line, "实得 %r" % line)
    check("W1b ⛔ 且必须明说「本次没有出 P6 的 U 判决」",
          "没有出 P6 的 U 判决" in txt)
    check("W1c 且不得把 ELIGIBLE 说成判决",
          "ELIGIBLE 不是判决" in txt or "不是**判决" in txt
          or "不是判决本身" in txt)

    print("\n=== W2：device_validated=false ⇒ 记进 RESULT 且不得印 DONE ===")
    bad = mk_r6(tmp / "bad.json", False, False)
    rc, txt = drive(mod, ["--r6-rows", str(bad)], "W2-装置未验")
    line = result_line(txt)
    # ⚠⚠⚴ **W2a 第一版写成「退出码必须是 4」，那条判据没有分辨力。**
    # ⚠⚠⚴ 变异台 W-M1 把闸后的 `return EXIT_BLOCKED` 拆掉后，出口码**仍然是 4**
    # ⚠⚠⚴ —— 因为末尾是 `EXIT_OK if drift_rc == 0 else EXIT_BLOCKED`，
    # ⚠⚠⚴ 而漂移闸对本批必然非零（真实 P6 那次也是「漂移 EXIT=4」）。
    # ⚠⚠⚴ ⇒ **出口码被漂移闸垄断了，对「这道闸有没有生效」零信息。**
    # ⚗⇒ 有分辨力的是：RESULT 行**点名是哪一道闸**，以及有没有误印 DONE。
    check("W2a ⛔ 出口码必须非 0", rc != 0, "实得 %r" % rc)
    check("W2a2 ⛔ RESULT 必须点名是 u-test 这道闸挡的（不能只有泛泛的 BLOCKED）",
          "p6-u-test-rc=4" in line, "实得 %r" % line)
    # ⚠ 阻断时的 RESULT 形式是**流水线既有约定**：所有闸都印
    #   `RESULT pipeline  BLOCKED  <闸名>=<rc>`（p6_precond= / identity= / below-resolution）。
    # ⚠ ⚗ 我第一条版本机要求 `u_verdict=BLOCKED(rc=4)`，那是**我硬要了一个
    #   不存在的格式** —— 断言错，代码对。（又一个「断言写死格式」的坑。）
    check("W2b ⛔ RESULT 行必须按约定记 p6-u-test-rc=4",
          "BLOCKED  p6-u-test-rc=4" in line, "实得 %r" % line)
    # ⚠⚠⚴ W2b2 来自变异台 W-M2：`p6_verdict = "BLOCKED(rc=%d)"` 曾是**死赋值**
    # ⚠⚠⚴ —— 阻断路径赋完立刻 return，没人读它 ⇒ 改它没有任何可观测后果。
    # ⚗⇒ 现在它进 RESULT 行，赋值与出口码**接到同两处**（修订 195 的纪律）。
    check("W2b2 ⛔ 且必须同时记 u_verdict=BLOCKED(rc=4)（曾是死赋值）",
          "u_verdict=BLOCKED(rc=4)" in line, "实得 %r" % line)
    check("W2c ⛔ 阻断路径不得印出 DONE（否则读 RESULT 的人会以为跑通了）",
          "RESULT pipeline  DONE" not in txt)
    check("W2d 且列出可能原因（含 device_validated / 轨迹数 / traj）",
          "device_validated" in txt and "轨迹数" in txt and "traj" in txt)

    print("\n=== W3：有效产物 ⇒ 记 RUN 且本步确实被调用 ===")
    ok = mk_r6(tmp / "ok.json", True, True)
    rc, txt = drive(mod, ["--r6-rows", str(ok)], "W3-有效")
    line = result_line(txt)
    # ⚠⚠ **退出码不是 0**，因为末尾是 `EXIT_OK if drift_rc == 0 else EXIT_BLOCKED`，
    # ⚠⚠ 而漂移闸对「拿本批当新批、与旧批比」必然非零 —— 这是**既有行为**，
    # ⚠⚠ 真实 P6 那次跑出来也是「漂移 EXIT=4 + DONE」。
    # ⚠⚠ ⇒ 拿退出码判「8.5 有没有生效」是错的判据；要看 u_verdict 与本步有没有跑。
    check("W3a RESULT 行必须记 u_verdict=RUN",
          "u_verdict=RUN" in line, "实得 %r" % line)
    check("W3b 本步确实被调用（[步骤 85]，与既有 [步骤 75] 同约定）",
          "[步骤 85]" in txt and ">>> p6_u_test EXIT=0" in txt)
    check("W3c ⛔ 且不得打印「未检查」警告（给了 --r6-rows 就不是未检查）",
          "U 检验未检查" not in txt)

    print("\n=== W3d：⛔ 伪重复在这一层也被挡住（行数 vs 轨迹数必须被透出）===")
    # 33 行 / 51 行 ⇒ 按行 n1=33 ≥ 10 会放行；按轨迹 n1=11 才合法。
    # 这一项验的是**接线把仪器的结论原样透出**，不是仪器自己（那由 p6_u_test 的 T7 管）。
    check("W3e 输出里必须能看到「行 → 轨迹」的换算",
          ("→ 轨迹" in txt), "实得文本里没有该行")
    check("W3f ⛔ 且必须能看到轨迹级 n=11（不是行级 n=33）",
          "correct 组 n=11 " in txt,
          "实得：%s" % [l.strip() for l in txt.splitlines() if "组 n=" in l])

    print("\n=== W4：--dry-run 计划必须列出 8.5 并在缺参时警告 ===")
    rc, txt = drive(mod, ["--dry-run"], "W4a-dryrun")
    check("W4a 计划里必须出现 8.5", "8.5 p6_u_test.py" in txt)
    check("W4b 缺参时必须标警告", "--r6-rows" in txt and "不跑" in txt)
    rc, txt = drive(mod, ["--dry-run", "--r6-rows", str(ok)], "W4c-dryrun")
    check("W4c 给了 --r6-rows 时计划里不得再标「不跑」",
          "8.5 p6_u_test.py" in txt
          and "本次没给 --r6-rows ⇒ 该步**不跑**" not in txt)

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT pipe_wiring_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], FAILS))
        return 1
    print("RESULT pipe_wiring_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
