"""验 `r100_build_index.py` 新增的「行范围自检闸门」到底有没有牙齿。

做法：两次变异，都必须让闸门变红（exit 2）——
  M1  span 换回旧口径 `end2 - start`（end2 仍是新口径）
  M2  **重建修复前的原版生成器**（`end2 = 下一条标题的 0-based 下标 or len(lines)`
      + `span = end2 - start`）—— 这才是历史上真正写下去的那份
恢复后必须 exit 0，且两次写出的索引逐字节相同。

⚠ 第一版把这个测试写成「报出的不合口径行数 == 9」，结果拿到 20（打印上限）。
  错在把两件事混了：
    · 「旧 end2 口径下 span 少算 1 行的段落」= 9 行（修订 100、110–117）
    · 「新闸门下被判红的行数」= 与生成器怎么算 end2 有关，不能拿 9 去卡
  ⇒ 断言要卡的是**闸门会不会红**，不是**会红几行**；行数从输出里正则取。
"""

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / ".cache/mutbak/r100_build_index.py"
IDX = ROOT / ".cache/xcheck/R6_RERUN_INDEX.md"
BAK = ROOT / ".cache/mutbak/R6_RERUN_INDEX.teethbak.md"

NEW_SPAN = "        span = end2 - start + 1\n"
OLD_SPAN = "        span = end2 - start\n"

PREFIX_FIX = "        lim = "
PREFIX_POST = "        emitted.append("


def run():
    return subprocess.run([sys.executable, str(GEN)], capture_output=True, text=True)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def n_flagged(stdout):
    m = re.search(r"不合口径 (\d+)", stdout)
    return int(m.group(1)) if m else -1


def to_prefix_fix(src):
    """把 lim/j/end2/span 那一整块换回修复前的写法。"""
    head, rest = src.split(PREFIX_FIX, 1)
    _mid, tail = rest.split(PREFIX_POST, 1)
    return (head
            + "        end2 = by_rev[nxt[0]][0][0] if nxt else len(lines)\n"
            + OLD_SPAN
            + PREFIX_POST + tail)


def main():
    src = GEN.read_text(encoding="utf-8")
    if NEW_SPAN not in src or PREFIX_FIX not in src or PREFIX_POST not in src:
        print("[错误] 生成器结构与本脚本不同步，不测")
        sys.exit(2)
    shutil.copy2(IDX, BAK)
    results = {}
    try:
        for tag, mutant in (("M1 旧 span 公式", src.replace(NEW_SPAN, OLD_SPAN)),
                            ("M2 修复前原版", to_prefix_fix(src))):
            GEN.write_text(mutant, encoding="utf-8")
            r = run()
            results[tag] = (r.returncode, n_flagged(r.stdout))
            print(f"[{tag}] 退出码 {r.returncode} / 闸门判红 {n_flagged(r.stdout)} 行")

        GEN.write_text(src, encoding="utf-8")
        r_good = run()
        same = sha(IDX) == sha(BAK)
        print(f"[恢复新口径] 退出码 {r_good.returncode} / 索引 sha256 {sha(IDX)[:16]}")
        print(f"[逐字节回到闸门通过版] {same}")

        teeth = all(rc == 2 and nf > 0 for rc, nf in results.values())
        ok = teeth and r_good.returncode == 0 and same
        print("=== 闸门有牙齿 ===" if ok else "=== 闸门没牙齿 / 测试本身有问题 ===")
        sys.exit(0 if ok else 2)
    finally:
        GEN.write_text(src, encoding="utf-8")   # 无条件还原
        run()


if __name__ == "__main__":
    main()