#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.87 提交后双回读**（账本 ＋ 索引 ＋ 提交清单，含「这套断言能红」的自证）。

⚖ **断言的期望值从哪来**：
   · **旧前缀**（追加 244.87 之前的那份账本）⇒ ⇒ **硬编码**（＝ 244.86 那次提交里的那份字节）
     ⇒ ⇒ 「落账没动旧字节」这条**不依赖任何生成物**。
   · **追加之后的整份** ⇒ ⇒ 由 `_gen_readback_24487.py` 在**落账之后、提交之前**写进本文件
     ⇒ ⇒ 提交后再回读 ⇒ ⇒ 若有人在生成与提交之间动过账本 ⇒ ⇒ 这里立刻判红。
   · **自证**：把账本**截短**再跑一遍同一套断言 ⇒ ⇒ 必须判红 ⇒ ⇒ 证明它**不是恒绿的**。

⚖⚖⚖ **H 项的加强**（沿用 244.86 的教训）：不只对账本 md5，**还要**独立确认
   **R8 全回归本身是绿的**（`REG_RC=0` ＋ 清单 diff added/removed）⇒ ⇒
   否则「收据里的账本 md5 对得上」也可能是**一份红的回归**留下的。
"""

import hashlib
import io
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LEDGER = ".cache/xcheck/R6_RERUN_PREREG.md"
INDEX = ".cache/xcheck/R6_RERUN_INDEX.md"

# ==== BEGIN FACTS（由 _gen_readback_24487.py 写入）====
PREFIX_BYTES = 2609372
PREFIX_MD5 = "c762e1ae1cf9971e0bef11d49873efcb"
FULL_LINES = 42138
FULL_BYTES = 2626945
FULL_MD5 = "8e89b6d1ba2fc220073d86fca7f329ed"
FENCES = 761
REV_ROWS = {'244.1': [31543], '244.2': [31808], '244.3': [31944], '244.4': [32037], '244.5': [32171], '244.6': [32286], '244.7': [32320], '244.8': [32528], '244.9': [32674], '244.10': [32861], '244.11': [32942], '244.12': [33021], '244.13': [33119], '244.14': [33202], '244.15': [33302], '244.16': [33373], '244.17': [33440], '244.18': [33499], '244.19': [33558], '244.20': [33618], '244.21': [33657], '244.22': [33727], '244.23': [33890], '244.24': [34016], '244.25': [34207], '244.26': [34387], '244.27': [34530], '244.28': [34646], '244.29': [34748], '244.30': [34826], '244.31': [34900], '244.32': [35008], '244.33': [35118], '244.34': [35186], '244.35': [35292], '244.36': [35336], '244.37': [35452], '244.38': [35537], '244.39': [35623], '244.40': [35704], '244.41': [35837], '244.42': [35986], '244.43': [36084], '244.44': [36189], '244.45': [36294], '244.46': [36386], '244.47': [36482], '244.48': [36576], '244.49': [36647], '244.50': [36711], '244.51': [36822], '244.52': [36918], '244.53': [37006], '244.54': [37093], '244.55': [37215], '244.56': [37381], '244.57': [37515], '244.58': [37632], '244.59': [37790], '244.60': [37966], '244.61': [38154], '244.62': [38269], '244.63': [38388], '244.64': [38584], '244.65': [38882], '244.66': [39091], '244.67': [39230], '244.68': [39331], '244.69': [39485], '244.70': [39600], '244.71': [39805], '244.72': [40180], '244.74': [40366, 40466], '244.75': [40527, 40662, 40726], '244.76': [40802], '244.77': [40936], '244.78': [41030], '244.79': [41092], '244.80': [41249], '244.81': [41382], '244.82': [41522], '244.83': [41590], '244.84': [41670], '244.85': [41777], '244.86': [41915], '244.87': [42024]}
# ==== END FACTS ====

WHITELIST = [
    ".cache/r244/cmax_robustness_audit.py",
    ".cache/r244/mut_cmax_robustness_audit.py",
    ".cache/r244/_cross_check_24487.py",
    ".cache/r244/_spec_crosscheck_24487.py",
    ".cache/r244/_run_24487_verify.sh",
    ".cache/r244/_run_24487_reg_shm.sh",
    ".cache/r244/_append_24487.py",
    ".cache/r244/_commit_msg_24487.py",
    ".cache/r244/_make_handoff_24487.py",
    ".cache/r244/_gen_readback_24487.py",
    ".cache/r244/_post_commit_readback_24487.py",
    ".cache/r244/_commit_24487.sh",
    ".cache/xcheck/R6_CMAX_ROBUSTNESS_PREREG.md",
    LEDGER,
    INDEX,
]


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _read_bytes(rel):
    with io.open(os.path.join(REPO, rel), "rb") as fh:
        return fh.read()


def _git(*a):
    p = subprocess.Popen(["git"] + list(a), cwd=REPO, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        return None
    return out


def _assertions(ledger_bytes, index_text, tag):
    res = []
    ok = True

    def chk(name, cond, detail):
        nonlocal ok
        res.append((name, bool(cond), detail))
        if not cond:
            ok = False

    pre = ledger_bytes[:PREFIX_BYTES]
    chk("A 旧前缀逐字节不变", len(pre) == PREFIX_BYTES and _md5(pre) == PREFIX_MD5,
        "前 %d 字节 md5 = %s（期望 %s）"
        % (PREFIX_BYTES, _md5(pre) if len(pre) == PREFIX_BYTES else "(不足)", PREFIX_MD5))
    t = ledger_bytes.decode("utf-8")
    nlines = t.count("\n")
    chk("B 账本总量", nlines == FULL_LINES and len(ledger_bytes) == FULL_BYTES
        and _md5(ledger_bytes) == FULL_MD5,
        "%d 行 / %d 字节 / md5 %s（期望 %d / %d / %s）"
        % (nlines, len(ledger_bytes), _md5(ledger_bytes), FULL_LINES, FULL_BYTES, FULL_MD5))
    fences = sum(1 for l in t.split("\n") if l.strip().startswith("```"))
    chk("C 围栏数不变", fences == FENCES, "%d（期望 %d）" % (fences, FENCES))
    lines = t.split("\n")
    for rev, rows in REV_ROWS.items():
        idx = [i + 1 for i, l in enumerate(lines) if l.startswith("## 修订 %s " % rev)]
        chk("D 标题「## 修订 %s」" % rev, idx == list(rows),
            "%d 条，行号 %s（期望 %s）" % (len(idx), idx, list(rows)))
    for rev, rows in REV_ROWS.items():
        # ⚖⚖⚖ **必须带 token 边界**：⛔ 用子串「修订 244.1」会把「修订 244.10」…「修订 244.19」、
        #   以及**兄弟修订**「修订 244.1b」「修订 244.2b」**一起**匹上
        pat = re.compile(r"修订 %s(?![0-9A-Za-z.])" % re.escape(rev))
        hit = [l for l in index_text.split("\n") if pat.search(l)]
        chk("E 索引命中「修订 %s」" % rev, len(hit) == len(rows),
            "%d 条（期望 %d：账本里这个修订有 %d 段，索引几段都列）"
            % (len(hit), len(rows), len(rows)))
    print("──── %s ────" % tag)
    for name, good, detail in res:
        print("  %s %-28s %s" % ("✅" if good else "⛔", name, detail))
    return ok, res


def main():
    if not FULL_MD5 or not REV_ROWS:
        print("⛔ FACTS 块是空的 ⇒ ⇒ 先跑 `_gen_readback_24487.py`")
        return 1
    names = _git("show", "--name-only", "--pretty=format:", "HEAD")
    got = sorted([n for n in (names or b"").decode("utf-8").split("\n") if n.strip()])
    want = sorted(WHITELIST)
    extra = [n for n in got if n not in want]
    missing = [n for n in want if n not in got]
    g_ok = (not extra) and (not missing)
    print("──── G 这次提交只带白名单路径 ────")
    print("  %s 提交带了 %d 个路径（期望 %d）｜ 清单外 %s ｜ 清单内漏掉 %s"
          % ("✅" if g_ok else "⛔", len(got), len(want), extra or "无", missing or "无"))
    if not g_ok:
        return 1

    f_ok = True
    print("──── F 工作区 vs HEAD 逐位一致 ────")
    for rel in (LEDGER, INDEX):
        a = _read_bytes(rel)
        b = _git("show", "HEAD:%s" % rel)
        if b is None:
            print("  ⛔ %s ｜ HEAD 里读不到" % rel)
            f_ok = False
            continue
        same = (_md5(a) == _md5(b))
        if not same:
            f_ok = False
        print("  %s %s ｜ 工作区 md5 = %s ｜ HEAD md5 = %s"
              % ("✅" if same else "⛔", rel, _md5(a), _md5(b)))
    if not f_ok:
        return 1

    ledger_bytes = _read_bytes(LEDGER)
    index_text = _read_bytes(INDEX).decode("utf-8")
    ok, _res = _assertions(ledger_bytes, index_text, "A–E 账本 / 索引断言")
    if not ok:
        return 1

    # ---- E 的「能红」自证：把索引里某个**多段**修订的**一条**删掉 ⇒ ⇒ E 必须判红
    _tgt = None
    for _r, _rows in REV_ROWS.items():
        if len(_rows) >= 2:
            _tgt = (_r, list(_rows))
            break
    print("──── E 能红自证（索引里删掉一条 ⇒ 必须判红）────")
    if not _tgt:
        print("  ⚠ 账本里没有多段修订 ⇒ ⇒ 改用「截短账本」自证 A–D")
    else:
        _r, _rows = _tgt
        _pat = re.compile(r"修订 %s(?![0-9A-Za-z.])" % re.escape(_r))
        _hit = [l for l in index_text.split("\n") if _pat.search(l)]
        _bad = index_text.replace(_hit[0] + "\n", "", 1)
        _hit2 = [l for l in _bad.split("\n") if _pat.search(l)]
        _red = (len(_hit2) != len(_rows))
        print("  %s 索引里删掉「修订 %s」的一条 ⇒ 条数 %d → %d（期望 %d）⇒ ⇒ %s"
              % ("✅" if _red else "⛔", _r, len(_hit), len(_hit2), len(_rows),
                 "E 判红（它不是恒绿的）" if _red else "⛔E 居然还绿 ⇒ 它是恒绿的，不可用"))
        if not _red:
            return 1

    cut = ledger_bytes.rfind(b"\n", 0, PREFIX_BYTES - 10)

    # ---- H：R8 收据里的账本 md5 == 本次提交里那份（⇒ 「R8 验的就是提交里那份字节」）
    #   ⚖⚖⚖ **加严**：不只对 md5，还要**独立确认 R8 本身是绿的**
    regp = os.path.join(REPO, ".cache", "r244", "_e24487", "reg_24487.txt")
    if os.path.isfile(regp):
        reg = io.open(regp, encoding="utf-8", errors="replace").read()
        m = re.search(r"ledger_lines=(\d+)\s+ledger_md5=(\w+)", reg)
        h_ok = False
        if m:
            h_ok = (m.group(1) == str(FULL_LINES) and m.group(2) == FULL_MD5)
            print("  %s H-1 R8 收据锚的账本 == 提交里那份：%s 行 / %s"
                  % ("✅" if h_ok else "⛔", m.group(1), m.group(2)))
        else:
            print("  ⛔ H-1 R8 收据里没有账本行数/md5")
        mrc = re.search(r"REG_RC=(\d+)", reg)
        reg_rc = mrc.group(1) if mrc else "(缺)"
        mdiff = re.search(r"added=(\d+)\s+removed=(\d+)", reg)
        dr = mdiff.groups() if mdiff else ("?", "?")
        h2_ok = (reg_rc == "0" and dr == ("4", "0"))
        print("  %s H-2 R8 本身是绿的：REG_RC=%s ｜ 清单 diff added/removed=%s/%s（期望 4/0）"
              % ("✅" if h2_ok else "⛔", reg_rc, dr[0], dr[1]))
        mled = re.search(r"ledger_md5=([0-9a-f]{32})", reg)
        h3_ok = bool(mled) and mled.group(1) == FULL_MD5
        print("  %s H-3 R8 收据里的账本 md5 == 提交里那份：%s"
              % ("✅" if h3_ok else "⛔", mled.group(1) if mled else "(缺)"))
        if not (h_ok and h2_ok and h3_ok):
            return 1
    else:
        print("  ⛔ 缺 R8 收据：%s ⇒ ⇒ 中止" % regp)
        return 1

    # ---- 截短自证：把账本截短 ⇒ ⇒ A–D 必须判红 ⇒ ⇒ 证明它**不是恒绿的**
    print("──── 截短自证（账本截短 ⇒ 必须判红）────")
    ok2, res2 = _assertions(ledger_bytes[:cut], index_text, "截短后")
    n_red = sum(1 for _n, g, _d in res2 if not g)
    print("  %s 自证：截短后有 %d 条判红（%s）⇒ ⇒ 这套断言**能红**"
          % ("✅" if n_red > 0 else "⛔", n_red,
             [n for n, g, _d in res2 if not g]))
    if n_red <= 0:
        return 1

    print("✅ 提交后双回读全过（账本 ＋ 索引 ＋ 提交清单 ＋ R8 收据）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
