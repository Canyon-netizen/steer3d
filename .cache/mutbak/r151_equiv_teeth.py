"""修订 151 的等价性证明 + 牙齿测试。

⚠⚠⚴⚠⚴ 本轮只改了 `scan_panel_coverage.py` 的**提示文本**，一个判决条件都没动。
⚠⚠⚴⚠⚴ 而「我以为我没改判决」不是证据 —— 所以这里做两件事：

  A. **等价性**：改前/改后跑同一份现场，**判决行逐位比对**，必须完全相同；
     再比全量输出，差异**只能**出现在新加的指引行上。
     ⚠ 若判决行有任何一字节不同 ⇒ 这就不是一次文案修复，而是口径变更，必须撤回。

  B. **牙齿**：注入「产物过期」，验**改后**印出可执行命令、**改前**不印。
     ⚗⚠⚠⚠ 只验改后会印是不够的 —— 那不能证明原来是个洞。
     ⚠⚠⚴ **「原来有没有洞」本身必须被验**，否则这轮修复可能是在修一个不存在的问题。

⚠⚠⚴⚠⚠⚠⚠ 全程会**真的**改动 `scan_panel_coverage.py` 与两份产物的 mtime。
⚠⚠⚴ 铁律：改动前备份 → finally 还原 → **逐字节核 sha256 / 逐位核 mtime**。
⚗⚠⚠ **「跑完了没报错」不等于「还原了」** —— 另一处教训：
   BSD `xargs -a` 不支持 ⇒ `git rm --cached` 静默失败 ⇒ amend 等于原样重提交，
⚗⚠⚠⚠⚠ **只有回读才发现。**
"""

import ast
import hashlib
import io
import os
import re
import subprocess
import sys
import time
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".cache/xcheck/scan_panel_coverage.py"
REL = ".cache/xcheck/scan_panel_coverage.py"
ARTIFACTS = [
    ROOT / ".cache/browser_verify/panel_blocks.json",
    ROOT / ".cache/browser_verify/panel_blocks_latent.json",
]
BACKUP_DIR = Path(__file__).resolve().parent / "r151_teeth"
CMD_NEEDLE = "probe_panels.mjs"      # 可执行命令的特征串
PY = sys.executable


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    p = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True, cwd=str(ROOT))
    return p.returncode, p.stdout + p.stderr


def verdict_lines(out):
    """只取判决行：[PASS]/[FAIL] 与汇总 RESULT。
    ⚠ 判定等价必须**只看判决** —— 提示文本本来就是本轮要改的东西。"""
    return [ln.rstrip() for ln in out.splitlines()
            if re.match(r"^\[(PASS|FAIL)\]", ln) or ln.startswith("RESULT")]


def main():
    ok = []
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ---- G0 语法 ----
    try:
        ast.parse(SCRIPT.read_text(encoding="utf-8"))
        print("[PASS] G0 改后脚本语法可解析")
        ok.append(True)
    except SyntaxError as exc:
        print("[FAIL] G0 语法错：%s" % exc)
        return 2

    # ---- G1 静态：悬空引用那句话必须已经不在**可执行代码**里 ----
    # ⚠⚠⚴⚠⚴ 第一版这道门写成 `src.count(...)`，当场判红 ——
    #   ⚗ 因为我新写的注释里**引用了那句话**（「…（见上面的两条命令）」），
    #   ⚗⚠⚴⚠ 而**纯 grep 分不出「残留」和「解释为什么删掉它的注释」**。
    # ⚠⚠⚴ ⇒ 只剥掉 COMMENT token；⚗⚠⚠ 字符串 token **保留** ——
    #   万一那句话还留在某条 abort 的提示串里，那才是真回归，必须抓到。
    src = SCRIPT.read_text(encoding="utf-8")
    code_only = "\n".join(
        tok.string for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        if tok.type != tokenize.COMMENT
    )
    dangling = code_only.count("见上面的两条命令")
    in_comment = src.count("见上面的两条命令") - dangling
    good = dangling == 0
    print("[%s] G1 可执行代码里已无「见上面的两条命令」（代码 %d 处 / 注释 %d 处，"
          "注释里那处是本轮写的说明）" % ("PASS" if good else "FAIL", dangling, in_comment))
    ok.append(good)

    # ---- 备份改后版本，并取回改前版本 ----
    new_src = src
    new_sha = sha(SCRIPT)
    (BACKUP_DIR / "scan_new.py").write_text(new_src, encoding="utf-8")
    # ⚠⚠⚴⚠⚴⚠⚴ 基线**必须从受版本控制的快照文件读**，不许从 `git show HEAD:` 取。
    # ⚠⚠⚴⚠⚴⚠⚴⚠⚴⚠ 原因（本测试第一版就是这么写的，当场翻了）：
    #   ⚗⚠ `git show HEAD:` 在**提交之前**是「改前那一版」，
    #   ⚗⚠⚴⚠⚠⚠ 而**提交之后 HEAD 就是改后那一版** ⇒ 「改前」变成「改后」，
    #   ⚗⚠⚴⚠⚠⚠⚠ G6 于是判成「改前也印出命令」⇒ **一个只在提交前成立的测试**。
    # ⚗⚠⚴⚠ **判据的可重复性不能依赖「我还没提交」这个临时状态。**
    base_file = Path(__file__).resolve().parent / "r151_teeth" / "scan_baseline.py"
    if not base_file.exists():
        print("[FAIL] 基线快照不存在：%s" % base_file)
        print("       ⚠⚠⚴ **不许退回去读 HEAD** —— 那正是本测试第一版的陷阱。")
        return 2
    old_src = base_file.read_text(encoding="utf-8")
    try:
        ast.parse(old_src)
    except SyntaxError as exc:
        print("[FAIL] 旧版本语法都不过，无法做等价性比对：%s" % exc)
        return 2

    art_mtimes = {p: p.stat().st_mtime for p in ARTIFACTS}
    baseline_code = None

    def restore_all():
        SCRIPT.write_text(new_src, encoding="utf-8")
        for p, mt in art_mtimes.items():
            if p.exists():
                os.utime(str(p), (mt, mt))

    try:
        # ============ A. 等价性 ============
        new_code, out_new = run()
        baseline_code = new_code
        SCRIPT.write_text(old_src, encoding="utf-8")
        old_code, out_old = run()
        SCRIPT.write_text(new_src, encoding="utf-8")     # 立刻还原，别等 finally

        v_new, v_old = verdict_lines(out_new), verdict_lines(out_old)
        same = v_new == v_old
        print("[%s] G2 判决行逐位相同：%s（各 %d 行）"
              % ("PASS" if same else "FAIL", same, len(v_new)))
        if not same:
            for a, b in zip(v_old, v_new):
                if a != b:
                    print("       改前 | %s" % a)
                    print("       改后 | %s" % b)
            if len(v_old) != len(v_new):
                print("       ⚠⚠⚴ 行数都变了：%d → %d" % (len(v_old), len(v_new)))
        ok.append(same)

        code_same = new_code == old_code
        print("[%s] G3 退出码相同：改前 %d / 改后 %d" % ("PASS" if code_same else "FAIL", old_code, new_code))
        ok.append(code_same)

        # 全量输出应当「只在新指引处不同」：现在现场是新鲜的，
        # 所以新指引那几行本来就不该出现 ⇒ 两种情况都算通过，但要如实说明。
        # ⚠⚠⚴⚠⚴⚠⚠ 第一版的 G4 **天生 flaky**：C0 的明细行里印着「根页 12 秒前」，
        # ⚠⚠⚴⚠ 而两次跑之间时间在走 ⇒ 那一行**必然不同** ⇒ 每跑一次红一次。
        # ⚗⚠⚴⚠⚠⚠⚠ **一个天生红的门比没有门更糟**：它训练你忽略 FAIL。
        # ⚠⇒ 比之前先归一化一切随时间/随轮的量。
        def norm(t):
            t = re.sub(r"\d+ 秒前", "N 秒前", t)
            return t
        nl_new, nl_old = norm(out_new).splitlines(), norm(out_old).splitlines()
        diff = [ln for ln in nl_new if ln not in nl_old]
        extra_old = [ln for ln in nl_old if ln not in nl_new]
        print("[%s] G4 归一化后全量输出无意外差异：改后多 %d 行 / 改前多 %d 行"
              % ("PASS" if not extra_old else "FAIL", len(diff), len(extra_old)))
        if extra_old:
            for ln in extra_old[:8]:
                print("       ⚠ 改后丢了这行 | %s" % ln)
        ok.append(not extra_old)

        # ============ B. 牙齿：注入「产物过期」 ============
        old_mt = time.time() - 7300          # > 7200 窗口；源码 9.9 小时未动，故仍比源码新
        for p in ARTIFACTS:
            os.utime(str(p), (old_mt, old_mt))

        _, aged_new = run()
        SCRIPT.write_text(old_src, encoding="utf-8")
        _, aged_old = run()
        SCRIPT.write_text(new_src, encoding="utf-8")     # 立刻还原

        v_aged_new, v_aged_old = verdict_lines(aged_new), verdict_lines(aged_old)
        aged_same = v_aged_new == v_aged_old
        print("[%s] G5 注入「产物过期」后判决仍逐位相同：%s" % ("PASS" if aged_same else "FAIL", aged_same))
        ok.append(aged_same)

        new_has_cmd = CMD_NEEDLE in aged_new
        old_has_cmd = CMD_NEEDLE in aged_old
        good = new_has_cmd and not old_has_cmd
        print("[%s] G6 改后印出可执行命令=%s / **改前**印出=%s（应为 False —— 证明原来确实是洞）"
              % ("PASS" if good else "FAIL", new_has_cmd, old_has_cmd))
        ok.append(good)

        # 改后那段指引必须**说清两种红的处置相反**，否则只是加了一堆命令
        says_opposite = ("不必先怀疑页面" in aged_new)
        print("[%s] G7 改后指引点明「过期≠比源码旧」的处置差别：%s"
              % ("PASS" if says_opposite else "FAIL", says_opposite))
        ok.append(says_opposite)

    finally:
        restore_all()

    # ---- 还原自查 ----
    same_script = sha(SCRIPT) == new_sha
    same_mt = all(abs(p.stat().st_mtime - mt) < 1e-6 for p, mt in art_mtimes.items() if p.exists())
    print("[%s] G8 脚本逐字节还原：%s" % ("PASS" if same_script else "FAIL", same_script))
    print("[%s] G9 两份产物 mtime 还原：%s" % ("PASS" if same_mt else "FAIL", same_mt))
    if not (same_script and same_mt):
        print("       ⚠⚠⚴ 没还原干净 —— 从 %s 恢复" % BACKUP_DIR)
        return 2
    ok += [same_script, same_mt]

    # ---- 还原后回到干净状态 ----
    # ⚠⚠⚴⚠⚴ 第一版这道门断言 `exit == 0`，当场判红 —— 而**那是我的期望写错了**。
    #   ⚗⚠ 正牌扫描现在就有 C2/C4/C6 三条**真红**，它**本来就该 exit 1**。
    #   ⚗⚠⚴⚠⚠ 写「应该全绿」的断言，等于**把「我要它变绿」伪装成「验证它没变」** ——
    #   ⚗⚠⚴ 若哪天真把 C2 修好了，这道门会**反过来判红**，而那本该是件好事。
    # ⚠⚠⚴ ⇒ 正确的不变量是：**还原后必须回到与首次跑完全相同的状态**。
    final_code, final_out = run()
    good = (baseline_code is not None and final_code == baseline_code
            and "RESULT panel_coverage" in final_out)
    print("[%s] G10 还原后 exit=%d，与首次跑（%s）一致且印出 RESULT"
          % ("PASS" if good else "FAIL", final_code, baseline_code))
    if not good:
        print("       ⚠⚠⚴ 期望的是「与首次跑一致」，**不是** 0 —— 当前现场本就有真红。")
    ok.append(good)

    n = sum(1 for x in ok if x)
    print("\nRESULT r151_equiv  %s %d/%d" % ("OK" if n == len(ok) else "FAIL", n, len(ok)))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
