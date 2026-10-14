"""C4 那条提示语的**判决中性**牙齿 —— 证明改的只有文案，判的一个字没动。

⚠⚠⁴⚠⚴ 为什么必须有
──────────────────
修订 168 查到：`_stale_k = sorted(k for k in KNOWN_UNREAD if k not in dom and k not in read)`
量的是**捕获时的 DOM**，而提示语写的是「既不在**页面**上」⇒
⚗⚠⚴⚠ 条件渲染的 `data-replay-note` / `data-vec-scale` 会被读成「源码里没有」
⚗⚠⚴⚠ **⇒ 照提示删，会抹掉两条真欠账**（源码里它们都在，注释还写着「加标记让它可被按标记读」）。

⚠⚠⁴ 本次改动**只许动 print 的文案**。§151：修「提示什么」与改「判什么」必须分开。
⚠⚠⚴⚠⚴ 而「只动文案」这件事**不能靠自觉** —— 必须实测判决逐位未变。⚠⚠⚴⚠⚴⚠⚠

⚠⚠⚴⚠⚴ **基线不是「改后的输出」** ——
⚗⚠⚴⚠ 第一版把基线写成「没有就存当前输出」，⚗⚠ **那等于用改后的东西证明改后没变，永远绿。⚗⚠⁴⚗⚠⚴⚗⚠**
⚗⚠⚴⚠ **⇒ 正确做法：备份 → 从 HEAD 取【改前】那份 → 跑一遍存基线 → 还原我的版本 → 再跑一遍比对。**
⚠⚠ **铁律：备份 → finally 还原 → 逐字节核 sha256。**

牙齿：
  G1 语法可解析
  G2 ⚠⚠ **改前 / 改后的判决行【逐字节相同】**（判决中性，本条是核心，且基线来自改前那份）
  G3 C4 计数形状完整且两版一致
  G4 新文案到位、旧误导措辞消失、必须带「不许删」那句
  G5 还原后回到改后版本（sha256 对得上）
"""

import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".cache/xcheck/scan_panel_coverage.py"
BACKUP = Path(__file__).resolve().parent / "r168_teeth" / "scan_panel_coverage.mine.py"
PRISTINE = Path(__file__).resolve().parent / "r168_teeth" / "scan_panel_coverage.head.py"
PY = sys.executable

VERDICT_RE = re.compile(r"^\s*(\[PASS\]|\[FAIL\]|RESULT\b)")
COUNT_RE = re.compile(r"未读 (\d+) = 装饰 (\d+) \+ 已知欠账 (\d+) ＋ \*\*新增未分类 (\d+)\*\*")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verdicts():
    p = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True, cwd=str(ROOT))
    out = p.stdout + p.stderr
    return [l.rstrip() for l in out.splitlines() if VERDICT_RE.match(l)], p.returncode, out


def main():
    teeth = []
    mine = SCRIPT.read_text(encoding="utf-8")

    # ---- G4：文案（与判决无关，先查）----
    teeth.append(("G4a 新措辞在位", "在本次捕获的 DOM 上没出现" in mine, ""))
    teeth.append(("G4b 旧误导措辞已消失", "既不在页面上也不在判据里" not in mine, ""))
    teeth.append(("G4c 带了「不许删」", "不许删" in mine, ""))
    try:
        ast.parse(mine)
        teeth.append(("G1 语法可解析", True, "ast.parse OK"))
    except SyntaxError as e:
        teeth.append(("G1 语法可解析", False, "SyntaxError @%s %s" % (e.lineno, e.msg)))

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    before = None
    try:
        BACKUP.write_text(mine, encoding="utf-8")
        sha_mine = sha(BACKUP)

        # ---- 取【改前】那份（来自 HEAD），跑出基线 ----
        head = subprocess.run(["git", "show", "HEAD:.cache/xcheck/scan_panel_coverage.py"],
                              capture_output=True, text=True, cwd=str(ROOT))
        if head.returncode != 0:
            teeth.append(("G2 判决中性", False,
                          "⚠ 取不到 HEAD 那份：git show 失败 ⇒ **没法证中性**"))
            raise SystemExit(1)
        PRISTINE.write_text(head.stdout, encoding="utf-8")
        SCRIPT.write_text(head.stdout, encoding="utf-8")
        v_before, rc_before, out_before = verdicts()
        c_before = COUNT_RE.search(out_before)
        c_before = c_before.groups() if c_before else None
    finally:
        # ---- 还原我的版本，并逐字节核 ----
        SCRIPT.write_text(BACKUP.read_text(encoding="utf-8"), encoding="utf-8")
        restored_ok = sha(SCRIPT) == sha_mine

    teeth.append(("G5 还原后回到我的版本", restored_ok, "sha256 %s" % ("对上" if restored_ok else "⚠对不上")))

    # ---- G2 ⚠ 判决中性：基线来自改前那份 ----
    v_after, rc_after, out_after = verdicts()
    c_after_m = COUNT_RE.search(out_after)
    c_after = c_after_m.groups() if c_after_m else None
    same = (v_before == v_after)
    if not same:
        d = ([b for b in v_before if b not in v_after][:3]
             + [a for a in v_after if a not in v_before][:3])
        detail = "⚠ 有差异：" + " / ".join(d)
    else:
        detail = "exit %d→%d，%d 行判决全等" % (rc_before, rc_after, len(v_after))
    teeth.append(("G2 ⚠ 判决逐字节未变", same, detail))

    teeth.append(("G3 C4 计数两版一致", c_before is not None and c_before == c_after,
                  "改前 %s / 改后 %s" % (c_before, c_after)))

    print("=== 牙齿 ===")
    npass = 0
    for name, ok, detail in teeth:
        print("  [%s] %-22s %s" % ("PASS" if ok else "FAIL", name, detail))
        npass += bool(ok)
    print("\nRESULT r168_teeth  %d/%d" % (npass, len(teeth)))
    if npass != len(teeth):
        print("\n⚠⚠⚴ 有牙齿没咬住 ⇒ 不许当成通过")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())