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
RESOLVABILITY = XC / "p6_resolvability.py"
# ⚠⚠ 修订 202：U 检验本体。⛔ 不接进流水线，它就是第二个死开关
# ⚠⚠ —— 本项目已经为同一件事付过两次代价（修订 195 的 pos_ok、
# ⚠⚠   修订 199 的 resolvable_known）。
P6_U = XC / "p6_u_test.py"

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
    # ⚠⚠ 修订 198：这三个一起给才跑可分辨性闸。
    # ⚠ ⚗ 刻意**不给默认值** —— 静默用一个猜的 logit 量级，
    # ⚠   等于偷偷替读数定口径（本项目反复栽的那类错）。
    ap.add_argument("--w-unembed", default=None,
                    help="w_unembed_align.py 的产物 json（取 dot_marker_mean）")
    ap.add_argument("--w-meta", default=None, help="w*.npy.json（取 class_gap）")
    ap.add_argument("--w-name", default=None,
                    help="产物里这条 w 的名字。三项须与 --w-unembed 对应")
    ap.add_argument("--logit-mag", type=float, default=None,
                    help="注入点实测 |logit| 量级（由它**推导**地板）。"
                         "⚠ 实测证明推导值对不上读数量子，能给 --floor 就给 --floor")
    ap.add_argument("--floor", type=float, default=None,
                    help="**直接**给分辨率地板（推荐）。34 个实测读数的公共步长是 0.125")
    ap.add_argument("--floor-source", default=None,
                    help="地板的出处，**必填**。例：empirical-gcd-of-34-readings")
    # ⚠⚠ 修订 202：U 判决仪器的输入。
    # ⚠ ⚗ 同样**刻意不给默认值** —— 找不到产物就应当「未检查」，
    # ⚠   而不是偷偷换个文件或跳过这一步（修订 195 的死开关、199 的第二个死开关）。
    ap.add_argument("--r6-rows", default=None,
                    help="r6_rerun.py 的**测量**产物 json（含 rows 与 "
                         "device_validated）。不给 ⇒ 步骤 8.5 报「未检查」")
    ap.add_argument("--p6-field", default="mark_w+_1.0",
                    help="从 rows 取哪个字段做 Δlogit（§P6 原文口径，默认即它）")
    a = ap.parse_args()

    # ⚠ 三个参数必须齐；只给一部分多半是漏了，而漏了就等于没查。
    _base = [a.w_unembed, a.w_meta, a.w_name]
    _floor = [a.floor, a.logit_mag, a.floor_source]
    if any(_base) and not all(_base):
        print("[错误] 可分辨性闸的三个定位参数必须**一起**给："
              "--w-unembed / --w-meta / --w-name")
        print("        现在给了 %d/3 —— 只给一部分 = 闸没跑，却像是跑过。"
              % sum(1 for x in _base if x is not None))
        return EXIT_USAGE
    if any(_base):
        if not a.floor_source:
            print("[错误] --floor-source 必填：地板这个数**从哪来**必须写下来。")
            return EXIT_USAGE
        if (a.floor is None) == (a.logit_mag is None):
            print("[错误] 地板来源必须**二选一**：--floor（实测）或 "
                  "--logit-mag（推导）。给了两个或都没给都不行。")
            return EXIT_USAGE

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
        _gate_on = bool(a.w_unembed and a.w_meta and a.w_name
                        and a.floor_source
                        and ((a.floor is None) != (a.logit_mag is None)))
        print("  7.5 p6_resolvability.py                       <- 可分辨性闸"
              "（修订 198/200）%s"
              % ("" if _gate_on
                 else "  ⚠ 本次参数不全 ⇒ 该闸**不跑**，届时会打印未检查警告"))
        print("  8. p6_readiness.py --label %s_label.json       <- 判决仪器"
              % STAMP)
        print("  8.5 p6_u_test.py --rows <测量产物>              <- **U 检验本体**"
              "（修订 202）%s"
              % ("" if a.r6_rows else "  ⚠ 本次没给 --r6-rows ⇒ 该步**不跑**，"
                                    "届时会打印未检查警告"))
        print("  9. 汇总会**同时**写进退出码与 RESULT 行（修订 195/202 的两处纪律）")
        print("     ⚠ 它只查**样本量**（correct≥10）；⚗「量测不测得出来」由 7.5 管")
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

    # ---- 步骤 7.5：观测量可分辨性（修订 198 新增）----
    # ⚠⚠ 为什么插在这里：p6_readiness 只查 **样本量**（correct>=10），
    # ⚠⚠ 它不查 **观测量本身是否低于仪器分辨率**。两者是不同的「不成立」。
    # ⚠⚠ 不接这一步的话，本脚本会照常印 ELIGIBLE，
    # ⚠⚠ 而那个 ELIGIBLE **不等于** U 检验跑出来的 p 值可解释。
    resolvable_known = None
    given = (a.w_unembed, a.w_meta)
    if all(given):
        step(75, "p6_resolvability —— 观测量可分辨性（修订 198）")
        rc, out = run([sys.executable, str(RESOLVABILITY),
                       "--w-unembed", a.w_unembed,
                       "--w-meta", a.w_meta,
                       "--name", a.w_name,
                       "--floor", str(a.floor),
                       "--floor-source", a.floor_source])
        print(out)
        print(">>> p6_resolvability EXIT=%d" % rc)
        resolvable_known = (rc == 0)
        if rc == 3:
            print("⛔⛔ **观测量低于仪器分辨率** ⇒ 即使 correct 组够 10 条，")
            print("   Mann–Whitney U 也在拿噪声和噪声比 ⇒ **不跑 P6 全量**。")
            print("   ⚠⚠⚴ **修订 201 已把这道闸降级** —— 实测证明「地板」是")
            print("   ⚗ **伪地板**（P9 每条轨迹只评 6 个组合，样本量太小，公因子是巧合；")
            print("   ⚗ 定点扫描 400 点里 399 个不同值，最小相邻差 6e-06）。")
            print("   ⚠ ⇒ 本次 rc=3 说明的是「按**你给的那个**地板算出观测量偏低」，")
            print("   ⚗ 不等于「测不出来」。⚠ **判决对这个尚未确定的量不稳健。**")
            print("   ⚗ A/B/C/D 选项表**已作废**（201.5 第 3 条）：改注入层(A)、")
            print("   ⚗ 换 pos_offset(B)、提剂量(C) 三条仍全部禁，本脚本不替规则选。")
            print("RESULT pipeline  BLOCKED  below-resolution")
            return EXIT_BLOCKED
    else:
        print("\n" + "-" * 70)
        print("⚠⚠⚠ **观测量可分辨性：未检查**（未给 --w-unembed/--w-meta/--logit-mag）")
        print("⚠ 本脚本**不**据此阻断，但它必须被写下来：")
        print("⚠ `p6_readiness` 印 ELIGIBLE 只说明**样本量够**（correct≥10），")
        print("⚠ ⚗ **不等于**那个量测得出来。真实尺度若低于 bf16 一个 ulp，")
        print("⚠   U 检验就是拿噪声和噪声比，p 值不可解释。")
        print("⚠ 闸：`python3 .cache/xcheck/p6_resolvability.py --w-unembed … "
              "--w-meta … --name … --logit-mag …`")

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

    # ---- 步骤 8.5：U 检验本体（修订 202 新增）----
    # ⚠⚠⚴ 为什么不接这一步，结论会是错的：
    # ⚠⚠⚴ `p6_readiness` 印 ELIGIBLE 只说明**样本量够**（correct≥10 条）。
    # ⚠⚠⚴ 那个「10 条」是**轨迹数**，而 §P6 的 U 检验吃的必须是
    # ⚠⚴⚴ **轨迹级**的数（每条轨迹先对它各位置的 Δlogit 取均值）。
    # ⚠⚠⚴ 不跑它 ⇒ 没人知道 (a) 装置验没验（device_validated）、
    # ⚠⚠⚴ (b) 两组到底是 n=11 还是被伪重复撑成的 n=66、
    # ⚠⚠⚴ (c) 功效够不够 —— 而这三条每一条都会改变结论的**含义**。
    p6_verdict = "NOT-RUN"
    p6_rc = None
    if a.allow_partial:
        print("\n" + "-" * 70)
        print(">>> 跳过 8.5（不是失败，是设计）：批次未跑满。")
        print("   同 8：部分数据上 p6_u_test 的 n<10 底线与功效披露都会说假话（修订 180）。")
    elif not a.r6_rows:
        print("\n" + "-" * 70)
        print("⚠⚠⚠ **U 检验未检查**（没给 --r6-rows，指定义是 r6_rerun 的测量产物）")
        print("⚠ 本脚本**不**据此阻断，但这一条必须被写下来：")
        print("⚠ ⚗ 上面那个 ELIGIBLE **不是** P6 的判决，只是「样本量够进入判决」。")
        print("⚠ ⚗ 装置验没验（`device_validated`）、两组是**轨迹级**还是被伪重复")
        print("⚗   撑大的行数、功效够不够 —— 这三条**一条都还没查**。")
        print("⚠ 闸：`python3 .cache/xcheck/p6_u_test.py --rows <测量产物>`")
    else:
        step(85, "p6_u_test —— U 检验本体（修订 202）")
        rc, out = run([sys.executable, str(P6_U),
                       "--rows", a.r6_rows, "--field", a.p6_field])
        print(out)
        print(">>> p6_u_test EXIT=%d" % rc)
        p6_rc = rc
        if rc == 0:
            p6_verdict = "RUN"
        else:
            p6_verdict = "BLOCKED(rc=%d)" % rc
            print("⛔⛔ **U 检验未能出判决（EXIT=%d）** —— 上面那个 ELIGIBLE" % rc)
            print("   **不是** P6 结论。常见原因（按可能性排序）：")
            print("   · EXIT 4 且 `device_validated=false` ⇒ P9 装置闸没过（修订 195/196）")
            print("   · EXIT 4 且 correct **轨迹数** < 10 ⇒ §P6「样本不足，不构成结论」")
            print("   · EXIT 4 且 rows 缺 `traj` ⇒ 无法按轨迹聚合，拒绝出判决（修订 202）")
            print("   · EXIT 3 ⇒ 产物里没有 usable 的 correct/wrong 读数")
            print("RESULT pipeline  BLOCKED  p6-u-test-rc=%d  u_verdict=%s"
                  % (rc, p6_verdict))
            return EXIT_BLOCKED

    print("\n" + "=" * 70)
    print("汇总：完整性闸 0 · 身份闸 0 · 漂移 EXIT=%d · 口径 0" % drift_rc)
    print("     U 检验（修订 202）：%s" % p6_verdict)
    if p6_verdict == "NOT-RUN":
        # ⚠⚠⚴ 纪律：没跑必须写在**结果**里，不能只留在上面的过程输出里。
        # ⚠⚴ 只打印不记账 = 下一个人读 RESULT 行会以为 P6 判过了。
        print("⚠⚠⚴ **本次没有出 P6 的 U 判决。** 上面那个 ELIGIBLE 只是")
        print("       「样本量够进入判决」，⛔ 不是判决本身。")
    if drift_rc != 0:
        print("⚠ 检出标签漂移 —— 两批 correct 数之差**不能**直接归因于抬 cap。")
    print("RESULT pipeline  DONE  n=%d  mode=%s  u_verdict=%s"
          % (n_remote, "partial" if a.allow_partial else "full", p6_verdict))
    return EXIT_OK if drift_rc == 0 else EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())