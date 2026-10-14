"""项目状态生成器 —— 一条命令回答「已完成什么、下一步是什么」。

⚠⚠⁴⚠⚴ 为什么要有这个文件
──────────────────────
本项目现在有 **7 个仪表**，每个只回答一个问题、各自 print 自己的 RESULT 行。
⚗⚠⚴⚠⚴⚠⚴ **⇒ 要看清全局得人工挨个跑一遍并在心里对表。⚗⚠⚴⚴⚗⚗**
⚗⚠⚴⚠⚴⚴ **而「手写的状态汇总」必然过期，且过期时不会报错。⚗⚠⚴⚴⚗⚗⚗⚗**

⚠⚠⁴⚠⚴⇒ 本脚本**现跑现印**，不读任何缓存的结论。

## 五种状态分开记（不许合并）

| 状态 | 含义 | 何时出现 |
|---|---|---|
| ✅ **绿** | 该仪表的问题已答上 | exit 0 且其 RESULT 行含 OK/ELIGIBLE/OLD_BATCH |
| ⚠ **红** | 有实质性的负结果（**不是**仪器坏） | exit 非 0 且 RESULT 行含 RED/FAIL/UNDERPOWERED/POOL_ONLY/MISMATCH |
| ⚗ **崩** | **仪器本身**跑不起来 | 非零退出但**没有** RESULT 行 / 抛异常 / 超时 |
| ○ **跳过** | 该问题当前不在判定范围内 | 仪表自己明说「不适用」 |
| ⚠ **未落地** | 仪表文件不在仓库里 | 文件缺失 |

⚠⚠⁴⚠⚴⚠⚴ **⚗⚠⚴⚴⚴⚠⚴⚠⚴ 崩 与 红 必须分开 ⚗⚠⚴⚴⚴⚠⚴⚴⚠⚴**
⚠⚠⁴ 「崩」的下一步是**修文件**；⚗⚠ 「红」的下一步是**做决定**。
⚗⚠⚴⚴⚴ **判错一次的代价完全相反** ⚗⚠⚴⚴⚴⚠⚠⚴⚴⚗⚠⚠⚗

## 本脚本自己的纪律

⚠⚠⁴⚠⚴⚠⚴ ⚠ **它会先记下探针产物的 mtime，全部跑完后再核一遍。⚠⚠⁴⚠⚴⚠⚴**
⚗⚠⚴⚴⚴⚴⚴⚴ **修订 159 实测：跑一次 `r149_teeth.py` 会把产物年龄刷成 0 秒，
⚗⚠⚴⚴ ⇒ C0 的 7200 秒新鲜度闸被洗绿。⚗⚠⚴⚴⚴⚴⚴⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**
⚠⚠⁴⚠⚴ ⇒ **本脚本若发现产物年龄被改动，必须自己判红并说清是哪一步干的。**

用法：  python3 .cache/xcheck/status.py
退出码：0 = 无崩；1 = 有崩；2 = 有仪表未落地
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
PER_INSTRUMENT_TIMEOUT = 300

ARTIFACTS = [
    ROOT / ".cache/browser_verify/panel_blocks.json",
    ROOT / ".cache/browser_verify/panel_blocks_latent.json",
]

# ⚠ 每条：名字 / 它回答什么问题 / 命令 / 期望在 RESULT 行里出现的绿词
NODE = shutil.which("node") or "node"
BACKEND = ROOT / "backend"

# ⚠⚠⁴⚠⚴ 装置参数**写死在这里**，不靠环境残留 ——
# ⚗⚠⚴⚠ verify_path 默认连 22224 / CDP 9471，而 9471 进场就被两个孤儿
# ⚗⚠⚴⚠ chrome-headless-shell 占着（`launch()` 用 fetch(/json/version) 探测，
# ⚗⚠⚴⚗⚠⚠ 连上别人的浏览器也报成功）。⇒ 基线口径固定为 9472。
T3D_URL = os.environ.get("T3D_URL", "http://127.0.0.1:22224")
CDP_PORT = os.environ.get("CDP_PORT", "9472")
VERIFY_ENV = dict(os.environ, T3D_URL=T3D_URL, CDP_PORT=CDP_PORT)

# ⚠⚠⁴⚠⚴ 每条都要写对**解释器与工作目录** —— ⚗⚠⁴ 写错就是「崩」，
# ⚗⚠⁴ 而「崩」的下一步是修文件，⚗⚠⁴ 不是处理产品问题。⚗⚠⚴ ⚠ 判错代价相反。
INSTRUMENTS = [
    ("verify_path", "39 条静态页判据（基线 39/39）",
     [NODE, str(ROOT / ".cache/browser_verify/verify_path.mjs")], ROOT, VERIFY_ENV),
    ("panel_coverage", "面板覆盖矩阵 C1–C8",
     [PY, str(ROOT / ".cache/xcheck/scan_panel_coverage.py")], ROOT, None),
    ("p6_readiness", "R-6 主判决 P6 够不够格（样本量闸）",
     [PY, str(ROOT / ".cache/xcheck/p6_readiness.py")], ROOT, None),
    ("recheck_c4", "已入库判决的分母能否被独立复算",
     [PY, str(ROOT / ".cache/xcheck/recheck_c4_denominator.py")], ROOT, None),
    ("teeth:recheck", "recheck 的三条拒绝路径真会拒吗",
     [PY, str(ROOT / ".cache/mutbak/r149_teeth.py")], ROOT, None),
    ("teeth:p6", "P6 闸的五种状态与合并池拦截",
     [PY, str(ROOT / ".cache/mutbak/r152_teeth.py")], ROOT, None),
    ("teeth:equiv", "改判据后判决是否逐位未变",
     [PY, str(ROOT / ".cache/mutbak/r151_equiv_teeth.py")], ROOT, None),
    ("backend", "后端单元测试",
     [PY, "-m", "pytest", "tests", "-q"], BACKEND, None),
]

# ⚠⚠⁴⚠⚴ 修订 162：**崩的时候必须给出可执行的修复命令。**
# ⚗⚠⚴⚠⚠⚠⚠⚗ 修订 151 已把这套做给了 C0（scan_panel_coverage.py），
# ⚗⚠⚴⚗⚗⚗⚗⚗ ⚗ **而本生成器一开始只会说「装置故障」，⚗⚠⚴⚗⚗⚗⚗⚗⚗ 不给怎么修。⚗⚠⚴⚗⚗⚗⚗⚗⚗**
# ⚗⚠⚴ ⚗⚠⚴ **⚗⚠⚴⚗⚠⚴⚗⚠⚴ ⚗⚠⚴⚗⚠⚴ 判红却给不出可执行路径的判据，⚗⚠⚴⚗⚠⚴⚗⚠⚴ 等于半个判据。⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**
# ⚗⚠⚴ ⚗⚠⚴⚗⚠⚴⚗⚠⚴ ⚗⚠⚴⚗⚠⚴ **⚗⚠⚴⚗⚠⚴ 本机硬约束（修订 161 实测）：⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗**
# ⚗⚠⚴ ⚗⚠⚴ ⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗ **后台服务 maxRunMs = 3600 秒 ⇒ 服务每 1 小时被回收一次，⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**
# ⚗⚠⚴ ⚗⚠⚴ ⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗ ⚗⚠ **⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗ 而 C0 的窗口是 7200 秒 ⇒ ⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗⚗**
# ⚗⚠⚴ ⚗⚠⚴ ⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗ ⚗⚠⚴⚗⚗⚗⚗⚗⚗ ⚗⚠⚴⚗ **所以「产物新鲜」每 ~1 小时就得重起一次服务，⚗⚠⚴⚗⚗⚗⚗⚗⚗⚗⚗⚗**
FIXES = {
    "verify_path": ("页面服务不在 —— ⚗ 本机 `next start` **每 3600 秒会被后台任务回收一次**，"
                    "⚗⚠ 而 C0 的窗口是 7200 秒 ⇒ **约每 1 小时就得重起一次**。\n"
                    "     → cd frontend && npx next start -p 22224   （⚠ 必须作为后台任务起，别用 `(... &)`）\n"
                    "     → 重跑本脚本即可；产物若也过期，另跑两页探针（见 scan_panel_coverage 的指引）"),
    "backend": "     → cd backend && python3 -m pytest tests -q",
}

GREEN_WORDS = ("OK ", "ELIGIBLE", "OLD_BATCH", "RESULT OK")
RED_WORDS = ("RED", "FAIL", "UNDERPOWERED", "POOL_ONLY", "MISMATCH", "CRASH")


def ages():
    return {p: p.stat().st_mtime for p in ARTIFACTS if p.exists()}


def result_line(out):
    for ln in out.splitlines():
        if ln.startswith("RESULT"):
            return ln.strip()
    return ""


def classify(code, out):
    """返回 (状态, 说明)。⚠⚠⚴ 崩与红必须分开判 —— 判错代价相反。"""
    res = result_line(out)
    if res and any(w in res for w in GREEN_WORDS) and code == 0:
        return "绿", res
    if res and any(w in res for w in RED_WORDS):
        return "红", res
    if code == 0:
        # ⚠⚠⁴⚠⚴ **exit 0 但没打 RESULT 行 ⇒ 这是「绿」，不是「崩」。**
        # ⚗⚠⁴ 第一版把「没有 RESULT 行」直接判崩，⚗⚠⁴ 结果 recheck_c4_denominator.py
        # ⚗⚠⚴⚗⚠⚠ **明明 exit 0、真的对上了账，却被报成崩。⚗⚠⚴⚗⚗⚗**
        # ⚗⚠ **⇒ 「崩」的判据是「**它自己没跑成功**」，⚗⚠⚠⚠⚠ 不是「它没按格式说话」。⚗⚠⚴⚴⚗⚗⚗⚗**
        return "绿", res or "exit=0（⚠ 该仪表未按惯例打 RESULT 行）"
    if not res:
        # ⚠⚠⚴ 没有 RESULT 行 **且** 非零退出 ⇒ 没跑到打印判决那一步 = 崩。
        return "崩", (out.strip().splitlines() or ["(无输出)"])[-1][:90]
    return "红", res or "exit=%d" % code


def main():
    print("=" * 108)
    print("Reasoning3D 项目状态 —— 由 .cache/xcheck/status.py **现跑现印**")
    print("生成时刻 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 108)

    before = ages()
    rows, states = [], []

    for name, question, cmd, cwd, env in INSTRUMENTS:
        label = (ROOT / cmd[1]).relative_to(ROOT) if cmd[1].endswith((".py", ".mjs")) else " ".join(cmd[2:])
        if not (ROOT / cmd[1]).exists() if len(cmd) > 1 and str(cmd[1]).startswith(str(ROOT)) else False:
            rows.append((name, question, "未落地", "文件缺失：%s" % label))
            states.append("未落地")
            continue
        try:
            t = time.time()
            p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd),
                               env=dict(os.environ, **(env or {})),
                               timeout=PER_INSTRUMENT_TIMEOUT)
            out, code, dt = p.stdout + p.stderr, p.returncode, time.time() - t
            st, why = classify(code, out)
            states.append(st)
            rows.append((name, question, st, "%s  [%.1fs]" % (why, dt)))
        except subprocess.TimeoutExpired:
            states.append("崩")
            rows.append((name, question, "崩", "⚠ 超时 >%ds" % PER_INSTRUMENT_TIMEOUT))
        except Exception as exc:                      # 仪器自己抛异常 = 崩
            states.append("崩")
            rows.append((name, question, "崩", "⚠ 异常：%s" % exc))

    print("\n%-18s %-34s %-8s %s" % ("仪表", "它回答的问题", "状态", "依据（RESULT 行 / 备注）"))
    print("-" * 108)
    for name, q, st, why in rows:
        print("%-18s %-34s %-8s %s" % (name, q, st, why))

    from collections import Counter
    cnt = Counter(states)
    # ⚠⚠⁴⚠ 崩的仪表**逐个**给修复命令（判红的不给：红的下一步是拍板，不是修文件）
    crashed = [r for r in rows if r[2] == "崩"]
    if crashed:
        print("\n--- 崩掉的仪表：可执行修复 ---")
        for name, _, _, why in crashed:
            print("  [%s] %s" % (name, why))
            if name in FIXES:
                print(FIXES[name])
            else:
                print("     ⚠ 本脚本未登记该仪表的修复路径 ⇒ 去 %s 看它自己的指引"
                      % ".cache/mutbak/ 或 .cache/xcheck/")
            print()

    print("\n汇总：" + "、".join("%s %d" % (k, v) for k, v in
                                   sorted(cnt.items(), key=lambda kv: -kv[1])))

    # ---- ⚠⚠⁴⚠⚴ 自证：跑这一遍有没有动过产物年龄（修订 159 的教训）----
    after = ages()
    touched = [p.name for p in before if p in after and abs(after[p] - before[p]) > 1e-6]
    print("\n--- 自证：本次运行是否改动了探针产物的年龄 ---")
    for p in ARTIFACTS:
        if p.exists():
            a = before.get(p)
            print("  %-32s %6.0f 秒前%s"
                  % (p.name, time.time() - p.stat().st_mtime,
                     "" if p not in before or not touched or p.name not in touched
                     else "   ⚠⚠⚴ 已被改动（原本 %.0f 秒前）" % (time.time() - a)))
        else:
            print("  %-32s 不存在" % p.name)

    rc = 0
    if touched:
        print("⚠⚠⚴⚠⚴⚠⚴ **本次运行改动了产物年龄 %s** ⇒ C0 的新鲜度闸被洗绿。"
              % touched)
        print("⚠⚠⚴ **别信上面那个 panel_coverage 的绿/红** —— 它量的是被刷新过的产物。")
        rc = 1
    if cnt.get("崩"):
        print("⚗⚠⚴ 有 %d 个仪表**崩了**（仪器本身跑不起来）⇒ 先修文件，别当成产品有问题。"
              % cnt["崩"])
        rc = 1
    if cnt.get("未落地"):
        print("⚠ %d 个仪表未落地（文件不在仓库里）" % cnt["未落地"])
        rc = 2 if rc == 0 else rc

    print("\n%s" % ("RESULT status  OK  无崩" if rc == 0 else
                    "RESULT status  %s  %s" % ("CRASH" if cnt.get("崩") else
                                                ("MISSING" if rc == 2 else "FAIL"),
                                                "崩=%d 未落地=%d" % (cnt.get("崩", 0),
                                                                    cnt.get("未落地", 0)))))
    return rc


if __name__ == "__main__":
    sys.exit(main())