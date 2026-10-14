#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 判决流水线（修订 182 立）—— 把「跑满那一刻」的手工链固化成有闸的编排。

为什么要有这个脚本：
    判决那一刻的链条是 5 个手工步骤（远端数文件 → 标注 → 拉回 → 过闸 → 出判决）。
    每一步都是一个机会：读到旧文件、跑错顺序、跳过闸。而那正是决定性的一刻 ——
    修订 180 实测到 p6_readiness.py 在部分数据上会印「别急着去取数据」，
    说明这条链**确实**会被人误用，不是假想风险。

本脚本**不下判决**，只做编排与放行：
    步骤 1  远端数产物条数            —— 不足则直接停，什么都不做
    步骤 2  远端 strict_label_r167 标注
    步骤 3  scp 拉回
    步骤 4  r180_p6_precond   硬闸    —— 不绿则**停止**，且明确说为什么
    步骤 5  r177_batch_identity 硬闸   —— 不绿则停止
    步骤 6  r181_label_drift  观测     —— 漂移 > 0 打印警告，但不阻断（它是测量结果）
    步骤 7  r178_uncapped_fate 权威口径 —— 全程可跑（它自己分已测/未测）
    步骤 8  p6_readiness      判决仪器 —— **只有步骤 1/4/5 全绿才允许跑**

用法：
    # 增量测量：部分数据也允许跑，但结构上**禁止**跑 p6_readiness
    python3 r182_verdict_pipeline.py --allow-partial

    # 完整判决：必须 60/60，过闸才跑 p6_readiness
    python3 r182_verdict_pipeline.py

    python3 r182_verdict_pipeline.py --dry-run     # 只列计划，不连远端

退出码：
    0  全部步骤按预期完成（--allow-partial 下即为增量测量完成）
    4  某道闸红了 / 未跑满 / 漂移检出
    2  用法或环境错误
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BLOCKED = 4

ROOT = Path(__file__).resolve().parents[2]
MUT = ROOT / ".cache/mutbak"
XC = ROOT / ".cache/xcheck"

HOST = "zju-53"
REMOTE_DIR = "/home/zhourui/steer3d_bpath"
REMOTE_GLOBDIR = "gen_b2_max32768/aime"
PY = "/home/zhourui/miniconda3/envs/easysteer/bin/python"   # 3.12.13，不用裸 python3

EXPECT_CAP = 32768
EXPECT_ROWS = 60

OLD_LABEL = MUT / "strict_label_b2_full60.json"
PRECOND = MUT / "r180_p6_precond.py"
IDENTITY = MUT / "r177_batch_identity.py"
DRIFT = MUT / "r181_label_drift.py"
FATE = MUT / "r178_uncapped_fate.py"
P6 = XC / "p6_readiness.py"

STAMP = "r182"


def run_tag():
    """每次运行的唯一标签。

    ⚠ 修订 186 修正：原先落盘名是写死的 `r182_label.json`，
      于是**第二次运行会把第一次的产物整个覆盖掉**。
      实测踩到：修订 182 入库的是 20 行那一版，
      隔一轮再跑增量模式，工作区那份被静默覆盖成 32 行 ——
      **「结论对但证据没进仓库」的另一种形态：证据被覆盖后，
      账本里引用的那份文件已经不存在了。**
    ⇒ 落盘名带运行标签（默认取本地时间戳），不再跨运行复用同一个名字。
    """
    import time
    return time.strftime("%m%d_%H%M%S")


def run(cmd, cwd=None):
    """跑一条命令，返回 (exit_code, 输出)。退出码直接从 returncode 取，不经管道。"""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def ssh(remote_cmd):
    return run(["ssh", HOST, remote_cmd])


def step(n, title):
    print("\n" + "=" * 70)
    print("[步骤 %s] %s" % (n, title))
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--allow-partial", action="store_true",
                    help="允许部分数据（只跑观测步骤，结构上禁止 p6_readiness）")
    ap.add_argument("--dry-run", action="store_true", help="只列计划，不连远端")
    a = ap.parse_args()

    if not DRIFT.exists() or not PRECOND.exists():
        print("[错误] 判据脚本缺失，先确认 .cache/mutbak/ 下文件在不在")
        return EXIT_USAGE

    global STAMP
    STAMP = "%s_%s" % (STAMP, run_tag())
    if not a.dry_run:
        print("本次运行标签：%s（落盘名 %s_label.json，不再覆盖旧运行）" % (STAMP, STAMP))

    if a.dry_run:
        print("=== 计划（未执行）===")
        print("  1. ssh %s 数 %s/*.json 条数" % (HOST, REMOTE_GLOBDIR))
        print("  2. ssh %s %s strict_label_r167.py %s/*.json --out %s" %
              (HOST, PY, REMOTE_GLOBDIR, "%s_label.json" % STAMP))
        print("  3. scp 回 .cache/mutbak/%s_label.json" % STAMP)
        print("  4. r180_p6_precond.py %s_label.json %d %d   <- 硬闸"
              % (STAMP, EXPECT_CAP, EXPECT_ROWS))
        print("  5. r177_batch_identity.py %s_label.json %d %d <- 硬闸"
              % (STAMP, EXPECT_CAP, EXPECT_ROWS))
        print("  6. r181_label_drift.py <旧批> <新批>          <- 观测")
        print("  7. r178_uncapped_fate.py %s_label.json         <- 权威口径" % STAMP)
        print("  8. p6_readiness.py --label %s_label.json       <- 判决仪器"
              % STAMP)
        print("\n模式：%s"
              % ("增量测量（禁止跑第 8 步）" if a.allow_partial
                 else "完整判决（要求 %d/%d）" % (EXPECT_ROWS, EXPECT_ROWS)))
        return EXIT_OK

    # ---- 步骤 1：数远端产物 ----
    step(1, "数远端产物条数")
    rc, out = ssh("ls -1 %s/%s/*.json 2>/dev/null | wc -l"
                  % (REMOTE_DIR, REMOTE_GLOBDIR))
    if rc != 0:
        print("ssh 失败：\n%s" % out)
        return EXIT_USAGE
    n_remote = int(out.strip().splitlines()[-1])
    print("远端 %s/*.json = %d 条（期望 %d）" % (REMOTE_GLOBDIR, n_remote, EXPECT_ROWS))

    if n_remote != EXPECT_ROWS and not a.allow_partial:
        print("\n⛔ 远端未跑满（%d/%d），且未给 --allow-partial。" % (n_remote, EXPECT_ROWS))
        print("   按 §167，数据没跑完不给 P6 结论 —— 本次到此为止，**不做任何标注**。")
        print("RESULT pipeline  NOT-READY  %d/%d" % (n_remote, EXPECT_ROWS))
        return EXIT_BLOCKED

    # 闸该按多少行去验身份？
    #   完整模式：按 60 —— 少一条就该红，这就是它的职责。
    #   增量模式：按**已存在的完整题数**（奇数条时向下取整到成对的题）。
    #     ⚠ 修订 182 修正：第一版在增量模式下也按 60 传，于是两道闸必然红、
    #       脚本在第 4 步就返回，永远到不了第 6/7 步的增量测量 ——
    #       闸把它自己要守的性质当成了阻断理由。
    #     现在闸只守「身份」，跑满与否由第 8 步单独把关。
    n_complete = (n_remote // 2) * 2
    gate_rows = EXPECT_ROWS if n_remote == EXPECT_ROWS else n_complete
    complete = n_remote == EXPECT_ROWS
    print("完整度：%d/%d（成对完整题数 %d）=> %s"
          % (n_remote, EXPECT_ROWS, n_complete,
             "完整" if complete else "未跑满，闸按 %d 行验身份" % gate_rows))

    # ---- 步骤 2：远端标注 ----
    step(2, "远端标注（strict_label_r167.py，R-27 规则唯一来源）")
    rc, out = ssh("cd %s && %s strict_label_r167.py %s/*.json --out %s_label.json"
                  % (REMOTE_DIR, PY, REMOTE_GLOBDIR, STAMP))
    print(out[-1200:] if out else "(无输出)")
    if rc != 0:
        print("⛔ 远端标注失败 rc=%d" % rc)
        return EXIT_USAGE

    # ---- 步骤 3：拉回 ----
    step(3, "拉回标注产物")
    dest = MUT / ("%s_label.json" % STAMP)
    rc, out = run(["scp", "-q", "%s:%s/%s_label.json" % (HOST, REMOTE_DIR, STAMP),
                   str(dest)])
    if rc != 0:
        print("⛔ scp 失败：\n%s" % out)
        return EXIT_USAGE
    print("已拉到 %s（%d 字节）" % (dest.name, dest.stat().st_size))

    # ⚠ 生成还在跑：从步骤 1 数条数到这一步，行数可能已经变了。
    #   以**拉回来的实际行数**为准，并把差异当竞态指标印出来。
    try:
        d = __import__("json").load(open(dest, encoding="utf-8"))
        n_pulled = len(d["rows"] if isinstance(d, dict) and "rows" in d else d)
    except Exception as e:                       # noqa: BLE001
        print("⛔ 拉回的标注读不出来：%s" % e)
        return EXIT_USAGE
    if n_pulled != n_remote:
        print("⚠ 竞态：步骤 1 数到 %d 条，拉回后是 %d 条（生成仍在推进）。"
              % (n_remote, n_pulled))
        print("   以下一律以**拉回的实际行数 %d** 为准。" % n_pulled)
    else:
        print("行数与步骤 1 一致：%d" % n_pulled)
    n_remote = n_pulled
    complete = n_remote == EXPECT_ROWS
    gate_rows = EXPECT_ROWS if complete else n_remote

    # ---- 步骤 4/5：硬闸 ----
    step(4, "r180_p6_precond —— 身份/结构闸（按 %d 行）" % gate_rows)
    rc, out = run([sys.executable, str(PRECOND), str(dest),
                   str(EXPECT_CAP), str(gate_rows)])
    print(out)
    print(">>> r180_p6_precond EXIT=%d" % rc)
    if rc != 0:
        print("\n⛔ 结构闸红了 —— **不跑 p6_readiness**。")
        print("RESULT pipeline  BLOCKED  p6_precond=%d" % rc)
        return EXIT_BLOCKED

    step(5, "r177_batch_identity —— 批次身份闸（按 %d 行）" % gate_rows)
    rc, out = run([sys.executable, str(IDENTITY), str(dest),
                   str(EXPECT_CAP), str(gate_rows)])
    print(out)
    print(">>> r177_batch_identity EXIT=%d" % rc)
    if rc != 0:
        print("\n⛔ 批次身份闸红了 —— 判决作废（数据来源身份不明）。")
        print("RESULT pipeline  BLOCKED  identity=%d" % rc)
        return EXIT_BLOCKED

    # ---- 步骤 6：漂移观测 ----
    step(6, "r181_label_drift —— 混淆项观测（红不阻断，但要看见）")
    rc, out = run([sys.executable, str(DRIFT), str(OLD_LABEL), str(dest)])
    print(out)
    print(">>> r181_label_drift EXIT=%d" % rc)
    drift_rc = rc

    # ---- 步骤 7：权威口径 ----
    step(7, "r178_uncapped_fate —— P6 权威口径（修订 179）")
    rc, out = run([sys.executable, str(FATE), str(dest)])
    print(out)
    print(">>> r178_uncapped_fate EXIT=%d" % rc)
    if rc != 0:
        print("⛔ 权威口径脚本失败")
        return EXIT_USAGE

    # ---- 步骤 8：判决仪器 ----
    step(8, "p6_readiness —— 判决仪器")
    if a.allow_partial:
        print("⛔ 批次未跑满（%d/%d），**不跑**这一支。" % (n_remote, EXPECT_ROWS))
        print("   它在部分数据上会印「再多取也到不了 10 / 这是设计问题，不是取数问题」，")
        print("   而那两句此时都是假话（修订 180 实测）。")
        print(">>> 跳过（不是失败，是设计）")
    elif not complete:
        print("⛔ 未跑满但未给 --allow-partial —— 按 §167 到此为止。")
        print("RESULT pipeline  BLOCKED  not-ready")
        return EXIT_BLOCKED
    else:
        rc, out = run([sys.executable, str(P6), "--label", str(dest)])
        print(out)
        print(">>> p6_readiness EXIT=%d" % rc)

    print("\n" + "=" * 70)
    print("汇总：完整性闸 0 · 身份闸 0 · 漂移 EXIT=%d · 口径 0" % drift_rc)
    if drift_rc != 0:
        print("⚠ 检出标签漂移 —— 两批 correct 数之差**不能**直接归因于抬 cap。")
    print("RESULT pipeline  DONE  n=%d  mode=%s"
          % (n_remote, "partial" if a.allow_partial else "full"))
    return EXIT_OK if drift_rc == 0 else EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())