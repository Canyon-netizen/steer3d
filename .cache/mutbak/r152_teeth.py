"""`p6_readiness.py` 的牙齿测试 —— 验它的五种状态**真的会分开报**。

⚠⚠⚴⚠⚴ 为什么必须有
──────────────────
`p6_readiness.py` 现在的实跑结果是「exit 3 / 样本不足」，
而它的**职责就是分清五种状态**（崩 / 批次不匹配 / 样本不足 / 够格 / 旧批次）。
⚠⚠⁴⚠⚴⚠ **一个只会说「样本不足」的脚本，等于没有分状态能力** ——
⚗⚠⚴ 而「把崩当成样本不足」恰恰是最贵的错：⚗⚠ **它会让人以为数据不够，
⚗⚠⚴⚗⚠⚠⚠ 而真因是文件坏了，去拼命补数据。**

⚠ 四条注入（每条只改一个变量）：
  T1 抬 P6 底线到 99        ⇒ 必须 UNDERPOWERED（证这条底线真的在判，不是摆设）
  T2 改回归常量             ⇒ 必须「未复现」（证它比的是常量，不是现算现比）
  T3 喂混合 cap 的标签产物   ⇒ 必须 MISMATCH（证 P0 的「不混池」真的在判）
  T4 喂不存在的路径         ⇒ 必须 CRASH exit 5（证崩不会被当成样本不足）
⚗⚠ 其中 T4 最要紧：⚗⚠⚠⚠ **崩与样本不足必须分开**，否则补数据的力气全白费。

⚠⚠⁴⚠⚠⚠⚠ T1/T2 会临时改 `p6_readiness.py`，铁律：
  备份 → finally 还原 → **逐字节核 sha256**。
"""

import ast
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".cache/xcheck/p6_readiness.py"
BACKUP = Path(__file__).resolve().parent / "r152_teeth" / "p6_readiness.bak.py"
FULL = ROOT / ".cache/mutbak/strict_label_b2_full60.json"
OLD_TRAJ = "datasets/aime_qwen3_1p7b_16k_fp16/aime"
PY = sys.executable


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(*args):
    p = subprocess.run([PY, str(SCRIPT)] + list(args), capture_output=True, text=True, cwd=str(ROOT))
    return p.returncode, p.stdout + p.stderr


def patch(old, new, tag):
    """临时替换脚本里的一处常量，跑完立刻还原。"""
    src = SCRIPT.read_text(encoding="utf-8")
    if src.count(old) != 1:
        print("[FAIL] T%s 锚点命中 %d 次（应为 1）—— 脚本被改过，测试失效"
              % (tag, src.count(old)))
        return None
    return src.replace(old, new)


def main():
    ok = []
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    orig = SCRIPT.read_text(encoding="utf-8")
    orig_sha = sha(SCRIPT)
    BACKUP.write_text(orig, encoding="utf-8")

    try:
        ast.parse(orig)
        print("[PASS] G0 被测脚本语法可解析")
        ok.append(True)

        # ---- 基线：本机新批次应判「样本不足」exit 3 ----
        code, out = run()
        good = code == 3 and "UNDERPOWERED" in out
        print("[%s] G1 基线 exit=%d 且判 UNDERPOWERED（应为 3）" % ("PASS" if good else "FAIL", code))
        ok.append(good)

        # ---- T1 抬高底线 ⇒ 仍 UNDERPOWERED，且理由指向底线 ----
        new = patch("P6_CORRECT_FLOOR = 10", "P6_CORRECT_FLOOR = 99", "1")
        if new is not None:
            SCRIPT.write_text(new, encoding="utf-8")
            c1, o1 = run()
            good = c1 == 3 and "UNDERPOWERED" in o1 and "99" in o1
            print("[%s] T1 底线抬到 99 ⇒ exit=%d（仍 UNDERPOWERED，证这条底线真在判）"
                  % ("PASS" if good else "FAIL", c1))
            ok.append(good)
        SCRIPT.write_text(orig, encoding="utf-8")

        # ---- T2 改回归常量 ⇒ 必须「未复现」，证明比的是常量而非现算现比 ----
        new = patch('"think_correct": 4', '"think_correct": 99', "2")
        if new is not None:
            SCRIPT.write_text(new, encoding="utf-8")
            c2, o2 = run("--traj", OLD_TRAJ)
            good = "FAIL" in o2 and "未" in o2 and "复现" in o2
            print("[%s] T2 回归常量改成 99 ⇒ 必须判「未复现」（证比常量，非现算现比）"
                  % ("PASS" if good else "FAIL"))
            if not good:
                for ln in o2.splitlines()[-5:]:
                    print("       | %s" % ln)
            ok.append(good)
        SCRIPT.write_text(orig, encoding="utf-8")

        # ---- T3 混合 cap ⇒ MISMATCH（P0「不混池」真的在判）----
        mixed = json.loads(FULL.read_text(encoding="utf-8"))
        for r in mixed["rows"][:10]:
            r["cap"] = 2048          # ⚠ 只改这一个字段，其余不动
        tmp = BACKUP.parent / "mixed_caps.json"
        tmp.write_text(json.dumps(mixed, ensure_ascii=False), encoding="utf-8")
        c3, o3 = run("--label", str(tmp))
        good = c3 == 4 and "MISMATCH" in o3
        print("[%s] T3 前 10 条 cap 改成 2048 ⇒ exit=%d 且 MISMATCH（证不混池在判）"
              % ("PASS" if good else "FAIL", c3))
        ok.append(good)

        # ---- T4 不存在的路径 ⇒ CRASH exit 5（崩不许被当成样本不足）----
        c4, o4 = run("--traj", "datasets/__definitely_not_here__")
        good = c4 == 5 and "CRASH" in o4
        print("[%s] T4 不存在的路径 ⇒ exit=%d 且 CRASH（⚠ 崩与样本不足必须分开）"
              % ("PASS" if good else "FAIL", c4))
        ok.append(good)

        # ---- T5 不存在的标签文件 ⇒ CRASH ----
        c5, o5 = run("--label", str(BACKUP.parent / "no_such.json"))
        good = c5 == 5 and "CRASH" in o5
        print("[%s] T5 不存在的标签文件 ⇒ exit=%d 且 CRASH" % ("PASS" if good else "FAIL", c5))
        ok.append(good)

    finally:
        SCRIPT.write_text(orig, encoding="utf-8")

    restored = sha(SCRIPT) == orig_sha
    print("[%s] G2 被测脚本逐字节还原：%s" % ("PASS" if restored else "FAIL", restored))
    if not restored:
        print("       ⚠⚠⚴ 从 %s 恢复" % BACKUP)
        return 2
    ok.append(restored)

    # ---- 还原后回到基线 ----
    c6, o6 = run()
    good = c6 == 3 and "UNDERPOWERED" in o6
    print("[%s] G3 还原后回到基线 exit=%d" % ("PASS" if good else "FAIL", c6))
    ok.append(good)

    # ---- 全量批次必须判 POOL_ONLY（证 T3 的临时文件没污染真数据，
    #      且**合并池确实被拦下**）----
    c7, o7 = run("--label", str(FULL))
    good = c7 == 3 and "POOL_ONLY" in o7
    print("[%s] G4 全量 120 条判 POOL_ONLY exit=%d（证 T3 没污染 + 合并池被拦）"
          % ("PASS" if good else "FAIL", c7))
    ok.append(good)

    # ---- T6 核心：单池达标但合并池超标时，必须判 POOL_ONLY 而非 ELIGIBLE ----
    # ⚠⚠⚴⚠⚴⚠⚴⚠⚴⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚠⚴⚴⚴
    # ⚠⚠ 修订 153 的教训：**我上一轮就是被合并池骗过**，报出「全量够格」。
    # ⚠⚠⇒ 这道门必须能证明「合并池够格」时它**仍然拒**。
    # ⚗⚠ 做法：把底线临时降到 6（单池 aime25=7 ≥ 6）⇒ 此时
    # ⚗⚠ **单池与合并池都达标** ⇒ 应判 ELIGIBLE；
    # ⚗⚠ 再降到 8（单池 7 < 8 ≤ 合并 13）⇒ 必须判 POOL_ONLY。
    new6 = patch("P6_CORRECT_FLOOR = 10", "P6_CORRECT_FLOOR = 8", "6a")
    if new6 is not None:
        SCRIPT.write_text(new6, encoding="utf-8")
        c6a, o6a = run("--label", str(FULL))
        g6a = c6a == 3 and "POOL_ONLY" in o6a
        print("[%s] T6a 底线降到 8（单池 7<8≤合并 13）⇒ exit=%d 且 POOL_ONLY"
              % ("PASS" if g6a else "FAIL", c6a))
        if not g6a:
            for ln in o6a.splitlines()[-6:]:
                print("       | %s" % ln)
        ok.append(g6a)
    SCRIPT.write_text(orig, encoding="utf-8")

    new6b = patch("P6_CORRECT_FLOOR = 10", "P6_CORRECT_FLOOR = 6", "6b")
    if new6b is not None:
        SCRIPT.write_text(new6b, encoding="utf-8")
        c6b, o6b = run("--label", str(FULL))
        g6b = c6b == 0 and "ELIGIBLE" in o6b
        print("[%s] T6b 底线降到 6（单池 7≥6，两池都达标）⇒ exit=%d 且 ELIGIBLE"
              % ("PASS" if g6b else "FAIL", c6b))
        ok.append(g6b)
    SCRIPT.write_text(orig, encoding="utf-8")

    n = sum(1 for x in ok if x)
    print("\nRESULT p6_teeth  %s %d/%d" % ("OK" if n == len(ok) else "FAIL", n, len(ok)))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
