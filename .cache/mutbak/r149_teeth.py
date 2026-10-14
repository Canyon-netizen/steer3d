"""`recheck_c4_denominator.py` 的牙齿测试 —— 验它的三条**拒绝**路径真的会拒。

⚠⚠⚴ 为什么必须有这个
──────────────────
`recheck_c4_denominator.py` 现在的实跑结果是「exit 0 / 对上账」。
⚠⚠⚴⚠ **一个永远 PASS 的检查，和没有检查，在日志上长得一模一样。**
⚗⚠ ⚠⚠⚴ 所以必须逐条注入失效，验它**该拒的时候确实拒**。

⚠ 三条注入（每条只改一个变量）：
  T1 规模对不上指纹   —— 模拟「产物被别的模式顶掉了」
  T2 产物超过 7200 秒 —— 模拟「产物过期」
  T3 自报 page 不符   —— 模拟「跑错页」
⇒ 三条都**必须** exit 2，且理由行必须指认到对应的那一条。
⚗⚠ 若只改规模就能骗过 T3，那就说明指纹只挡了数量没挡身份。

⚠⚠⚴⚠⚠⚠⚠ 真实产物会被本测试**暂时改动**。三条铁律：
  ⚠⚠⚴ 1. 每次改动前先备份到 `.cache/mutbak/r149_teeth/`；
  ⚠⚠⚴ 2. 无论中途怎么失败，finally 里必须按备份**还原**；
  ⚠⚠⚴ 3. 还原后逐字节核 sha256 —— ⚠⚠ **「跑完了没报错」不等于「还原了」**。
⚗⚠⚠⚗ **教训来自另一处：BSD 的 `xargs -a` 不支持，`git rm --cached` **静默失败**，
⚗⚠⚠ 随后 amend 等于原样重提交 —— ⚠⚠ **只有回读才发现。**
"""

import ast
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".cache/xcheck/recheck_c4_denominator.py"
BLOCKS = ROOT / ".cache/browser_verify/panel_blocks.json"
LAT_BLOCKS = ROOT / ".cache/browser_verify/panel_blocks_latent.json"
BACKUP_DIR = Path(__file__).resolve().parent / "r149_teeth"

PY = sys.executable


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_script():
    proc = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def expect_reject(name, inject, needle):
    """注入一处失效，验脚本拒绝出数字且理由指认到这一条。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bak = BACKUP_DIR / (BLOCKS.name + "." + name)
    shutil.copy2(str(BLOCKS), str(bak))
    try:
        inject()
        code, out = run_script()
        rejected = code == 2
        blamed = needle in out
        print("[%s] %-22s exit=%d  %s"
              % ("PASS" if (rejected and blamed) else "FAIL", name, code,
                 "拒了，且理由指认到本条" if (rejected and blamed)
                 else ("拒了，但理由没指认到本条" if rejected else "⚠⚠ 没拒 —— 判据无牙齿")))
        if not (rejected and blamed):
            print("       期望理由里含：%r" % needle)
            for line in out.splitlines():
                print("       | %s" % line)
        return rejected and blamed
    finally:
        shutil.copy2(str(bak), str(BLOCKS))   # ⚠⚠⚠ 必须还原
        os.utime(str(BLOCKS), (time.time(), time.time()))


def main():
    ok = []

    # ---- 门 0：被测脚本本身能被 Python 解析（否则下面测的是个 SyntaxError）----
    try:
        ast.parse(SCRIPT.read_text(encoding="utf-8"))
        print("[PASS] G0 被测脚本语法可解析")
        ok.append(True)
    except SyntaxError as exc:
        print("[FAIL] G0 被测脚本语法错：%s" % exc)
        return 2

    # ---- 门 1：基线跑一遍必须是 exit 0（否则「它会拒」这件事无从谈起）----
    base_code, base_out = run_script()
    print("[%s] G1 基线 exit=%d（应为 0）" % ("PASS" if base_code == 0 else "FAIL", base_code))
    if base_code != 0:
        print(base_out)
        return 2
    ok.append(True)

    # ⚠ 备份真实产物，记下指纹，还原后要核它没变
    before_sha = sha(BLOCKS)
    before_lat_sha = sha(LAT_BLOCKS)

    def t1_clobbered():
        """规模对不上：把标记数改掉，模拟「被别的模式顶掉的产物」。"""
        raw = json.loads(BLOCKS.read_text(encoding="utf-8"))
        raw["beforeNames"] = ["data-outcome", "data-hinge"]
        raw["afterNames"] = ["data-outcome", "data-hinge"]
        BLOCKS.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    def t2_expired():
        """只改 mtime，不动内容 —— 验它拒绝的理由真的是「过期」而不是别的。"""
        old = time.time() - 7201
        os.utime(str(BLOCKS), (old, old))

    def t3_wrong_page():
        """只改自报的 page，别的都不动 —— 验指纹没有白放。"""
        raw = json.loads(BLOCKS.read_text(encoding="utf-8"))
        raw["page"] = "latent"
        BLOCKS.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    ok.append(expect_reject("T1 规模不符(被顶掉)", t1_clobbered, "很可能已经被顶掉了"))
    ok.append(expect_reject("T2 产物已过期",    t2_expired,    "产物已过期"))
    ok.append(expect_reject("T3 自报页不符",    t3_wrong_page, "跑错页"))

    # ---- 还原自查：逐字节核。⚠⚠ amend 返回 0 那次教训：必须回读 ----
    same = sha(BLOCKS) == before_sha and sha(LAT_BLOCKS) == before_lat_sha
    print("[%s] G2 三次注入后产物逐字节还原：%s" % ("PASS" if same else "FAIL", same))
    if not same:
        print("       ⚠⚠⚴ 真实产物已被改动且没能还原 —— 从 %s 恢复" % BACKUP_DIR)
        return 2
    ok.append(True)

    # ---- 门 3：还原后再跑一次，必须回到 exit 0 ----
    after_code, after_out = run_script()
    print("[%s] G3 还原后 exit=%d（应回到 0）" % ("PASS" if after_code == 0 else "FAIL", after_code))
    if after_code != 0:
        print(after_out)
    ok.append(after_code == 0)

    # ---- 门 4：把 EXPECTED_TOTAL 改错，它必须 exit 3 而不是含糊地 PASS ----
    src = SCRIPT.read_text(encoding="utf-8")
    if "EXPECTED_TOTAL = 390" not in src:
        print("[FAIL] G4 找不到 EXPECTED_TOTAL = 390 这一行 —— 脚本被改过，测试失效")
        return 2
    try:
        SCRIPT.write_text(src.replace("EXPECTED_TOTAL = 390", "EXPECTED_TOTAL = 999"),
                          encoding="utf-8")
        code, out = run_script()
        good = code == 3 and "对不上" in out
        print("[%s] G4 期望值改成 999 后 exit=%d（应为 3 且印「对不上」）" % ("PASS" if good else "FAIL", code))
        if not good:
            for line in out.splitlines()[-6:]:
                print("       | %s" % line)
        ok.append(good)
    finally:
        SCRIPT.write_text(src, encoding="utf-8")     # ⚠⚠⚴ 还原被测脚本
        restored = SCRIPT.read_text(encoding="utf-8") == src
        print("[%s] G5 被测脚本逐字节还原：%s" % ("PASS" if restored else "FAIL", restored))
        if not restored:
            return 2

    final_code, _ = run_script()
    good = final_code == 0
    print("[%s] G6 全部还原后 exit=%d（应为 0）" % ("PASS" if good else "FAIL", final_code))
    ok.append(good)

    n_ok = sum(1 for x in ok if x)
    print("\nRESULT recheck_teeth  %s %d/%d" % ("OK" if n_ok == len(ok) else "FAIL", n_ok, len(ok)))
    return 0 if n_ok == len(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
