#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mut_ledger_placeholder_audit —— `ledger_placeholder_audit.py` 的**变异台**（修订 244.63）

⚠⚠⚖ **本台架问什么**

  244.63 查账本残留占位符时发现：**244.62 那段在账本里留着 14 处裸占位符**（8 个标记），
  本该是数字的地方是空的。根因 = 244.62 追加脚本里的**链式占位符** + **替换后没有残留检查**。
  ⇒ 本轮补了 `ledger_placeholder_audit.py`（8 条判据 + 独立写死的登记表 + 程序化重算的应填值）。
  ⇒ 台架必须保证：那 **8 条判据每一条**都**抓得住**对应的实现写错，
     且**关掉任何一条**都不至于让洞彻底隐形。

⚖⚖⚖⚖ **三类变异（各有分工）**

  ① **代码突变**（改工具源码，跑**真账本**）⇒ 目标判据必须红
  ② **输入突变**（改**账本副本**，跑**未变异**的工具）⇒ 目标判据必须红
  ③ **独苗检查**（**关掉**一条判据 + 配一个特定输入）⇒ 证明那条判据**不可替代**
     ⚖ 这类**期望「变绿」**：关掉 C5 之后，「藏在代码段里的洞」就**彻底隐形**了
     ⇒ 这正说明 C5 是**独苗**（不是冗余）⇒ 算**通过**，不是「存活」。

⚖⚖⚖⚖⚖ **必须能红**的变异（14 条）

  M1  登记的行号被挪一行              ⇒ C2
  M2  登记行的归一化原文被改一个字     ⇒ C3
  M3  登记的应填值被改错               ⇒ C4
  M4  **现算**的尺子被改错（证明 C4 不是拿登记表自己当尺子） ⇒ C4
  M5  登记里多一个账本上没有的标记     ⇒ C5
  M6  登记表少一行（总数对不上）       ⇒ C6
  M7  登记了一个没有核验途径的标记     ⇒ C7
  M8  正文里长出一个没登记的新洞       ⇒ C1
  M9  洞藏在**代码段**里（只有 C5 能抓） ⇒ C5
  M10 一处登记的洞被悄悄填掉           ⇒ C2
  M11 C1 被关掉 ⇒ 洞仍被 C5/C6 兜住（**防恒绿**） ⇒ C5
  M12 C5 被关掉 ⇒ 洞**彻底隐形**（**独苗**：C5 不可替代） ⇒ 期望变绿
  M13 双重加粗残留的登记表被清空       ⇒ C8
  M14 正文里新长出一处字面 `****`      ⇒ C8

⚖⚖⚖⚖⚖ **纪律（与别处一致）**

  1. **基线必须绿**：未变异的源码 ⇒ 真账本全绿 **且** 自检全绿。
  2. 每条变异**只改一处**；⛔ 不改注释/散文（落点串必须**恰好命中 1 处**）。
  3. **崩 ≠ 抓到**；**切坏语法的变异判「无效」**。
  4. **期望标签必须存在**（244.62 踩过：改名后期望还写着旧号 ⇒ 期望指向不存在的判据
     ⇒ 变异明明让真判据红了，台架却报「存活」）⇒ 现在是守卫：**不在基线判据集合里 ⇒ 判无效**。
  5. ⛔ **绝不改工作区里的文件**：代码突变在**内存**里 exec；输入突变写在**系统临时目录**。

跑法：python3 mut_ledger_placeholder_audit.py
"""

import argparse
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(HERE, "ledger_placeholder_audit.py")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")

# ⚖ 账本尾部的锚（唯一）⇒ 输入突变都**追加在末尾** ⇒ ⛔ 不挪动已登记行的行号
TAIL = "（244.59 已登记）\n"

# (mid, kind, old, new, want, why)
#   kind = "code"   ⇒ 改**工具源码**，跑真账本
#   kind = "input"  ⇒ 改**账本副本**（old→new 替换），跑未变异的工具
#   kind = "append" ⇒ **追加**一段到账本副本末尾（⛔ 不挪动已登记行的行号），跑未变异的工具
#   kind = "sole"   ⇒ 关掉一条判据 + 配输入 ⇒ **期望变绿**（证明那条判据不可替代）
MUTATIONS = [
    ("M1", "code",
     '(38289, ("@NS@",),', '(38290, ("@NS@",),', "C2",
     "登记的行号被挪一行"),
    ("M2", "code",
     "个场景**（244.51 那个族，逐条复用）", "个场次**（244.51 那个族，逐条复用）", "C3",
     "登记行的归一化原文被改一个字"),
    ("M3", "code",
     '    "@NS@": "5",', '    "@NS@": "6",', "C4",
     "登记的应填值被改错"),
    ("M4", "code",
     '        "NS": str(len(sc)),', '        "NS": str(len(sc) + 1),', "C4",
     "现算的尺子被改错（C4 不是拿登记表自己当尺子）"),
    # ⚖⚠⚖⚖ **244.65 改的落点**：`ledger_placeholder_audit.py` 的 `HOLE_VALUES` 里
    #   `@NORMSAME@` 不再是**最后一项**（后面还有 6 项）⇒ 旧落点串命中 0 处 ⇒ 变异**无效**。
    #   ⇒ M5 改挂到**末项** `@WPALL@`（`HOLE_VALUES` 的最后一行）⇒ 仍是「多登记一个标记」。
    ("M5", "code",
     '    "@WPALL@": "0.0002",\n}',
     '    "@WPALL@": "0.0002",\n    "@FOO@": "1",\n}', "C5",
     "登记里多一个账本上没有的标记"),
    # ⚖⚠⚖⚖ **244.65 改的落点**：`HOLE_LINES` 第三元素从「归一化原文」改成「**原文**」
    #   ⇒ 38356 那行的**原文**变了（`p = «»` → `p = @RPMIN@`）⇒ 旧落点串命中 0 处。
    ("M6", "code",
     "    (38356, (\"@RPMIN@\",),\n"
     "     '  ⇒ ⇒ 那些场景的显著性**本来就未定** ⇒ 只印 p = @RPMIN@ 会让人以为「rand 臂也显著了」，'),\n",
     "", "C6",
     "登记表少一行 ⇒ 总数对不上"),
    ("M7", "code",
     '    "@SKR@": "SKR",\n}', '    "@SKR@": "SKR",\n    "@BAR@": "NS",\n}', "C7",
     "登记了一个没有核验途径的标记"),
    ("M8", "append",
     "", "\n⚖ 这是一个没被回填的洞 @ZZZ@ 还在\n", "C1",
     "正文里长出一个没登记的新洞"),
    ("M9", "append",
     "", "\n⚖ 洞藏在代码段里 `@ZZZ@` 也得被抓\n", "C5",
     "洞藏在代码段里 ⇒ 只有 C5 能抓"),
    ("M10", "input",
     "### 【1】⚖ 扰动族：**4 个变体 ＋ 基准 = @NS@ 个场景**（244.51 那个族，逐条复用）",
     "### 【1】⚖ 扰动族：**4 个变体 ＋ 基准 = 5 个场景**（244.51 那个族，逐条复用）", "C2",
     "一处登记的洞被悄悄填掉"),
    ("M11", "sole",
     '    if bad:\n        return False, "未登记的占位符：%s（⛔ 新洞）" % bad',
     '    if False and bad:\n        return False, "未登记的占位符：%s（⛔ 新洞）" % bad', "C1",
     "C1 被关掉 ⇒ 洞仍被 C5/C6 兜住（防恒绿）"),
    ("M12", "sole",
     '    if got != want:\n        return False, "全账本标记集合 %s ≠ 登记 %s" % (got, want)',
     '    if False and got != want:\n        return False, "全账本标记集合 %s ≠ 登记 %s" % (got, want)',
     "C5",
     "C5 被关掉 ⇒ 洞彻底隐形（独苗：C5 不可替代）"),
    ("M13", "code",
     'BOLD_LINES = [\n    (38328, "      ⇒ 判决：«»不成立«»　⚠⚠ **翻转**"),\n]',
     'BOLD_LINES = []', "C8",
     "双重加粗残留的登记表被清空"),
    ("M14", "append",
     "", "\n⚖ 判决：****成立****\n", "C8",
     "正文里新长出一处字面 `****`"),
]

# ⚖ M11/M12 配的输入（与 M8/M9 同一个洞：M11 放正文 ⇒ C1 本该抓；M12 放代码段 ⇒ C1 看不见）
SOLE_INPUT = {
    "M11": "\n⚖ 这是一个没被回填的洞 @ZZZ@ 还在\n",
    "M12": "\n⚖ 洞藏在代码段里 `@ZZZ@` 也得被抓\n",
}
# ⚖ M11 关掉的是 C1 ⇒ 期望**别的**判据（C5）兜住；M12 关掉的是 C5 ⇒ 期望**整体变绿**
SOLE_EXPECT = {"M11": "C5", "M12": None}


def _load(path, src=None):
    mod = types.ModuleType("lpa_mut")
    mod.__file__ = os.path.abspath(path)
    exec(compile(src if src is not None
                 else io.open(path, encoding="utf-8").read(), path, "exec"),
         mod.__dict__)
    return mod


def run_audit(mod, ledger=None):
    """⚖ 真实数据路：返回 ({判据号: 是否通过}, 错误信息)。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _res, _allok = mod.run(ledger)
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)
    return {c: o for c, o, _d in _res}, None


def run_selftest_fails(mod):
    """⚖ 自检路：返回失败的 token 集合。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.selftest()
    except Exception as e:
        return set(), "%s: %s" % (type(e).__name__, e)
    fails = set()
    for line in buf.getvalue().split("\n"):
        if line.startswith("[FAIL]"):
            m = re.match(r"\[FAIL\]\s+(\S+)", line)
            if m:
                fails.add(m.group(1))
    return fails, None


def _apply(src, old, new):
    n = src.count(old)
    if n != 1:
        raise AssertionError("落点串命中 %d 处（必须恰好 1 处）" % n)
    return src.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--ledger", default=LEDGER)
    args = ap.parse_args()

    src = io.open(args.target, encoding="utf-8").read()
    led = io.open(args.ledger, encoding="utf-8").read()

    base = _load(args.target, src)
    R0, err0 = run_audit(base)
    if err0:
        print("⛔ 基线崩了：%s" % err0)
        return 1
    red0 = set(c for c, v in R0.items() if not v)
    sf0, serr0 = run_selftest_fails(base)
    print("基线（真实账本）：%d/%d 通过%s"
          % (sum(1 for v in R0.values() if v), len(R0),
             ("（红：%s）" % ",".join(sorted(red0))) if red0 else ""))
    print("基线（自检）：失败集合 %s" % (",".join(sorted(sf0)) or "空"))
    if red0 or sf0 or serr0:
        print("⛔ 基线不绿 ⇒ 先修基线，台架不许跑（%s%s）"
              % (err0 or "", ",".join(sorted(sf0))))
        return 1

    caught, survived, invalid, crashed = [], [], [], []
    known = set(R0.keys())   # ⚖⚠⚖⚖ **期望标签必须存在**（244.62 的教训 ⇒ 守卫）
    tmpdir = tempfile.mkdtemp(prefix="lpa_mut_")
    try:
        for mid, kind, old, new, want, why in MUTATIONS:
            if want not in known:
                invalid.append((mid, "期望标签 %s 不在基线判据集合里（%s）⇒ 标签过期"
                                % (want, ",".join(sorted(known)))))
                print("[SKIP] %s 期望标签 %s **不存在** ⇒ 期望**过期**（⛔ 不许报存活）"
                      % (mid, want))
                continue
            tmp_led = None
            try:
                if kind in ("code", "sole"):
                    msrc = _apply(src, old, new)
                    try:
                        mod = _load(args.target, msrc)
                    except SyntaxError as e:
                        invalid.append((mid, "切完后语法错（%s）⇒ 变异**无效**" % e))
                        print("[SKIP] %s 切完后语法错 ⇒ 变异**无效**（%s）" % (mid, e))
                        continue
                if kind in ("input", "append", "sole"):
                    if kind == "input":
                        _led = _apply(led, old, new)
                    elif kind == "append":
                        _led = led + new
                    else:
                        _led = led + SOLE_INPUT[mid]
                    tmp_led = os.path.join(tmpdir, "ledger_%s.md" % mid)
                    io.open(tmp_led, "w", encoding="utf-8").write(_led)
                else:
                    tmp_led = args.ledger
                R, err = run_audit(mod if kind in ("code", "sole") else base, tmp_led)
            except AssertionError as e:
                invalid.append((mid, str(e)))
                print("[SKIP] %s 变异**无效**（%s）" % (mid, e))
                continue
            if err:
                crashed.append((mid, err))
                print("[CRASH] %s 崩了：%s（⚠ 崩 ≠ 抓到）" % (mid, err))
                continue
            red = set(c for c, v in R.items() if not v)

            if kind == "sole":
                exp = SOLE_EXPECT[mid]
                if exp is None:
                    # ⚖ 独苗：期望**整体变绿**（洞彻底隐形 ⇒ 这条判据不可替代）
                    if red:
                        survived.append((mid, want, "关掉 %s 后整体仍红：%s"
                                         % (want, ",".join(sorted(red)))))
                        print("[SURVIVED] %s 关掉 %s 后整体仍红（%s）⇒ **没证明独苗**"
                              % (mid, want, ",".join(sorted(red))))
                    else:
                        caught.append(mid)
                        print("[CAUGHT] %s 关掉 %s ⇒ 洞**彻底隐形**（整体全绿）"
                              " ⇒ 证明 %s **不可替代**（独苗）｜%s"
                              % (mid, want, want, why))
                else:
                    # ⚖ 防恒绿：被关掉的那条应变绿，**别的**判据必须兜住
                    off = [c for c in known if c not in red]
                    if want in red:
                        survived.append((mid, want, "判据 %s 没能被关掉 ⇒ 变异无效" % want))
                        print("[SURVIVED] %s 判据 %s 没能被关掉 ⇒ 变异**无效**"
                              % (mid, want))
                    elif exp not in red:
                        survived.append((mid, exp, "兜底判据 %s 没红（红=%s）"
                                         % (exp, ",".join(sorted(red)) or "无")))
                        print("[SURVIVED] %s 关掉 %s 后，兜底判据 %s **没红**（红=%s）"
                              " ⇒ **变异存活**" % (mid, want, exp,
                                                  ",".join(sorted(red)) or "无"))
                    else:
                        caught.append(mid)
                        print("[CAUGHT] %s 关掉 %s ⇒ 它变绿，但 %s 兜住了（红=%s）"
                              " ⇒ 护栏**不是恒绿**｜%s"
                              % (mid, want, exp, ",".join(sorted(red)), why))
                continue

            if want in red:
                caught.append(mid)
                print("[CAUGHT] %s ⇒ %s 红｜%s" % (mid, want, why))
            else:
                survived.append((mid, want, "红=%s" % (",".join(sorted(red)) or "无")))
                print("[SURVIVED] %s 期望 %s 红，实际红=%s ⇒ **变异存活**"
                      % (mid, want, ",".join(sorted(red)) or "无"))
    finally:
        # ⚖⚠⚠⚠ 临时目录**跑完再删**
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("")
    print("变异台：抓住 %d / %d" % (len(caught), len(MUTATIONS)))
    if survived:
        print("⛔ 存活 %d 条：%s" % (len(survived),
                                "；".join("%s（期望 %s）" % (m, w) for m, w, _ in survived)))
    if invalid:
        print("⚠ 无效变异 %d 条：%s" % (len(invalid),
                                   "；".join("%s（%s）" % (m, why) for m, why in invalid)))
    if crashed:
        print("⚠ 崩了 %d 条：%s" % (len(crashed),
                                   "；".join("%s（%s）" % (m, e) for m, e in crashed)))
    if survived:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
