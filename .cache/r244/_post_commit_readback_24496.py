#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.96 提交后双回读**（账本 ＋ 索引 ＋ 页面 ＋ 提交清单 ＋ R15 收据 ＋ 判决链收据，含「这套断言能红」的自证）。

⚖ **断言的期望值从哪来**：
   · **旧前缀**（追加 244.96 之前的那份账本）⇒ ⇒ **硬编码**（＝ 244.95 那次提交里的那份字节）
     ⇒ ⇒ 「落账没动旧字节」这条**不依赖任何生成物**。
   · **追加之后的整份** ⇒ ⇒ 由 `_gen_readback_24496.py` 在**落账之后、提交之前**写进本文件
     ⇒ ⇒ 提交后再回读 ⇒ ⇒ 若有人在生成与提交之间动过账本 ⇒ ⇒ 这里立刻判红。
   · **自证**：把账本**截短**再跑一遍同一套断言 ⇒ ⇒ 必须判红 ⇒ ⇒ 证明它**不是恒绿的**。

⚖⚖⚖ **H 项**：不只对账本 md5，**还要**独立确认
   · **R15 全回归本身是绿的**（`REG_RC=0` ＋ 清单 diff added/removed ＋ 零 BAD ＋ 两个族的绿数）；
   · **244.96 判决链**「改前 ⇒ 红」「改后 ⇒ A」两份收据都在；
   · **落账前后**判决链的判据块**逐字节相同**（⇒ ⇒ 落账没改变任何判定）
     —— ⚠ 本轮与前几轮不同：E2 那一行**印了账本的总行数**（落账前 42800 ⇒ 落账后 42895）
       ⇒ ⇒ 逐字节比对**必然**有 2 处差异 ⇒ ⇒ 所以这里**不**做死板的整文件比对，
       而是做两件事：
         ① 三个判据块（AUDIT_KEYS / NUM_MATRIX / ROW_VERDICTS）**逐字节相同**（判据块里**没有**账本行数）；
         ② 整份收据的**差异行**必须**逐行对应**，且**掩掉「账本总行数」这个 token 后逐字节相同**
            ⇒ ⇒ ⇒ 「落账唯一改变的东西就是账本的总行数」是**机械可查**的
            ⇒ ⇒ 并且**掩掉的 token 数 > 0**（⇒ ⇒ 归一化**不是**空转）。
   · **远端跑的字节 == 我提交的字节**（判决链收据里登记的 md5 ↔ 本地现算）。
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
PAGE = "docs/BPATH_VERDICT.md"
# ⚖ 落账**前**那轮判决链的收据（跑的是 42800 行那版账本）
RCPT = os.path.join(REPO, ".cache", "r244", "_e24496")
# ⚖ 落账**后**重跑的那轮判决链的收据（跑的是 42895 行那版账本＝ 本次提交里的那份）
RCPT2 = os.path.join(REPO, ".cache", "r244", "_e24496b")

# ==== BEGIN FACTS（由 _gen_readback_24496.py 写入）====
PREFIX_BYTES = 2720326
PREFIX_MD5 = "eb37cfb8dbb089cc5dd97aab43b27ddd"
FULL_LINES = 42895
FULL_BYTES = 2732437
FULL_MD5 = "912f7d6f34aa8b78d4483d7a539ae2b2"
FENCES = 761
REV_ROWS = {'244.1': [31543], '244.1b': [31736], '244.2': [31808], '244.2b': [31877], '244.3': [31944], '244.4': [32037], '244.5': [32171], '244.6': [32286], '244.7': [32320], '244.8': [32528], '244.9': [32674], '244.10': [32861], '244.11': [32942], '244.12': [33021], '244.13': [33119], '244.14': [33202], '244.15': [33302], '244.16': [33373], '244.17': [33440], '244.18': [33499], '244.19': [33558], '244.20': [33618], '244.21': [33657], '244.22': [33727], '244.23': [33890], '244.24': [34016], '244.25': [34207], '244.26': [34387], '244.27': [34530], '244.28': [34646], '244.29': [34748], '244.30': [34826], '244.31': [34900], '244.32': [35008], '244.33': [35118], '244.34': [35186], '244.35': [35292], '244.36': [35336], '244.37': [35452], '244.38': [35537], '244.39': [35623], '244.40': [35704], '244.41': [35837], '244.42': [35986], '244.43': [36084], '244.44': [36189], '244.45': [36294], '244.46': [36386], '244.47': [36482], '244.48': [36576], '244.49': [36647], '244.50': [36711], '244.51': [36822], '244.52': [36918], '244.53': [37006], '244.54': [37093], '244.55': [37215], '244.56': [37381], '244.57': [37515], '244.58': [37632], '244.59': [37790], '244.60': [37966], '244.61': [38154], '244.62': [38269], '244.63': [38388], '244.64': [38584], '244.65': [38882], '244.66': [39091], '244.67': [39230], '244.68': [39331], '244.69': [39485], '244.70': [39600], '244.71': [39805], '244.72': [40180], '244.74': [40366, 40466], '244.75': [40527, 40662, 40726], '244.76': [40802], '244.77': [40936], '244.78': [41030], '244.79': [41092], '244.80': [41249], '244.81': [41382], '244.82': [41522], '244.83': [41590], '244.84': [41670], '244.85': [41777], '244.86': [41915], '244.87': [42024], '244.88': [42139], '244.89': [42259], '244.92': [42420], '244.93': [42522], '244.94': [42610], '244.95': [42712], '244.96': [42802]}
# ==== END FACTS ====

WHITELIST = [
    ".cache/r244/doc_panel_audit.py",
    ".cache/r244/mut_doc_panel_audit.py",
    ".cache/r244/_cross_check_24496.py",
    ".cache/r244/_spec_crosscheck_24496.py",
    ".cache/r244/_run_24496_verify.sh",
    ".cache/r244/_run_24496_reg_shm.sh",
    ".cache/r244/_append_24496.py",
    ".cache/r244/_commit_msg_24496.py",
    ".cache/r244/_make_handoff_24496.py",
    ".cache/r244/_gen_readback_24496.py",
    ".cache/r244/_post_commit_readback_24496.py",
    ".cache/r244/_commit_24496.sh",
    ".cache/xcheck/R6_PANEL_PREREG.md",
    ".cache/mutbak/_idx_probe_24496.py",
    ".cache/r244/_append_24492.py",
    ".cache/r244/_append_24493.py",
    ".cache/r244/_append_24494.py",
    ".cache/r244/_append_24495.py",
    ".cache/r244/_fix_append_guard_24496.py",
    ".cache/r244/_verify_append_guard_24496.py",
    LEDGER,
    INDEX,
    PAGE,
]

# ⚖⚖⚖ R15 的清单 diff 期望（**手写** ⇒ ⛔ 不从被检对象/上一轮输出推导）
EXPECT_ADDED = "2"
EXPECT_REMOVED = "0"
# ⚖⚖⚖ R15 两个族的绿数期望（**手写** ⇒ ⛔ 不从上一轮输出推导）
EXPECT_MUT = "61/61"
EXPECT_ST = "58/58"


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


def _block(text, name):
    m = re.search(r"===== %s =====\n(.*?)===== END_%s =====" % (name, name), text, re.S)
    return m.group(1) if m else None


def _norm_ledger_lines(text):
    """⚖ 掩掉「账本总行数」这个 token（⛔ 只许掩这一个东西 ⇒ ⇒ 其它差异一律现形）。"""
    t = re.sub(r"（\d+ 行）", "（N 行）", text)
    t = re.sub(r"∈ \[1, \d+\]", "∈ [1, N]", t)
    return t


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
        pat = re.compile(r"修订 %s(?![0-9A-Za-z.])" % re.escape(rev))
        hit = [l for l in index_text.split("\n") if pat.search(l)]
        chk("E 索引命中「修订 %s」" % rev, len(hit) == len(rows),
            "%d 条（期望 %d）" % (len(hit), len(rows)))
    print("──── %s ────" % tag)
    for name, good, detail in res:
        print("  %s %-28s %s" % ("✅" if good else "⛔", name, detail))
    return ok, res


def _receipt_inputs(path):
    """⚖ 解析判决链收据里「输入与被检文件的 md5」那一段 ⇒ ⇒ {相对路径: md5}。"""
    t = io.open(path, encoding="utf-8", errors="replace").read()
    out = {}
    for m in re.finditer(r"^([0-9a-f]{32})\s+(\.cache/\S+)$", t, re.M):
        out[m.group(2)] = m.group(1)
    return out


def main():
    if not FULL_MD5 or not REV_ROWS:
        print("⛔ FACTS 块是空的 ⇒ ⇒ 先跑 `_gen_readback_24496.py`")
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
    for rel in (LEDGER, INDEX, PAGE):
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

    # ---- E 的「能红」自证：把索引里某个**多段**修订的**一条**删掉 ⇒ ⇒ E 必须判红 ----
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

    # ---- H-1..H-5：R15 收据（账本 md5 / REG_RC / 清单 diff / 零 BAD / 两个族的绿数）----
    regp = os.path.join(RCPT, "reg_24496.txt")
    if not os.path.isfile(regp):
        print("  ⛔ 缺 R15 收据：%s ⇒ ⇒ 中止" % regp)
        return 1
    reg = io.open(regp, encoding="utf-8", errors="replace").read()
    m = re.search(r"ledger_lines=(\d+)\s+ledger_md5=(\w+)", reg)
    h1_ok = bool(m) and m.group(1) == str(FULL_LINES) and m.group(2) == FULL_MD5
    print("  %s H-1 R15 收据锚的账本 == 提交里那份：%s 行 / %s"
          % ("✅" if h1_ok else "⛔", m.group(1) if m else "(缺)", m.group(2) if m else "(缺)"))
    mrc = re.search(r"REG_RC=(\d+)", reg)
    reg_rc = mrc.group(1) if mrc else "(缺)"
    mdiff = re.search(r"added=(\d+)\s+removed=(\d+)", reg)
    dr = mdiff.groups() if mdiff else ("?", "?")
    h2_ok = (reg_rc == "0" and dr == (EXPECT_ADDED, EXPECT_REMOVED))
    print("  %s H-2 R15 本身是绿的：REG_RC=%s ｜ 清单 diff added/removed=%s/%s（期望 %s/%s）"
          % ("✅" if h2_ok else "⛔", reg_rc, dr[0], dr[1], EXPECT_ADDED, EXPECT_REMOVED))
    mled = re.search(r"ledger_md5=([0-9a-f]{32})", reg)
    h3_ok = bool(mled) and mled.group(1) == FULL_MD5
    print("  %s H-3 R15 收据里的账本 md5 == 提交里那份：%s"
          % ("✅" if h3_ok else "⛔", mled.group(1) if mled else "(缺)"))
    mbad = re.search(r"BAD_n=(\d+)", reg)
    bad_n = mbad.group(1) if mbad else "(缺)"
    h4_ok = (bad_n == "0")
    print("  %s H-4 R15 收据里零 [BAD]：BAD_n=%s" % ("✅" if h4_ok else "⛔", bad_n))
    mut_line = [l for l in reg.split("\n") if l.startswith("变异台 全绿=")]
    st_line = [l for l in reg.split("\n") if l.startswith("自检   全绿=")]
    h5_ok = bool(mut_line and st_line
                 and EXPECT_MUT in mut_line[0] and EXPECT_ST in st_line[0])
    print("  %s H-5 R15 两个族的绿数 == 手写的期望：变异台 %s（期望 %s）｜ 自检 %s（期望 %s）"
          % ("✅" if h5_ok else "⛔",
             mut_line[0].split("=")[1].split("（")[0].strip() if mut_line else "(缺)",
             EXPECT_MUT,
             st_line[0].split("=")[1].split("（")[0].strip() if st_line else "(缺)",
             EXPECT_ST))
    if not (h1_ok and h2_ok and h3_ok and h4_ok and h5_ok):
        return 1

    # ---- H-6：244.96 判决链「改前 ⇒ 红」「改后 ⇒ A」两份收据都在 ----
    bf = io.open(os.path.join(RCPT, "data_before.out"), encoding="utf-8", errors="replace").read()
    af = io.open(os.path.join(RCPT, "data_after.out"), encoding="utf-8", errors="replace").read()
    b_red = re.findall(r"^\[FAIL\] (E\d)：", bf, re.M)
    b_v = re.search(r"^VERDICT=(.*)$", bf, re.M)
    a_v = re.search(r"^VERDICT=(.*)$", af, re.M)
    a_red = re.findall(r"^\[FAIL\] (E\d)：", af, re.M)
    h6_ok = (b_v and b_v.group(1) == "D" and b_red
             and a_v and a_v.group(1) == "A" and not a_red)
    print("  %s H-6 判决链「改前 ⇒ 红」（形态 %s，判红 %s）＋「改后 ⇒ A」（形态 %s，判红 %s）"
          % ("✅" if h6_ok else "⛔", b_v.group(1) if b_v else "(缺)",
             "/".join(b_red) or "无", a_v.group(1) if a_v else "(缺)", "/".join(a_red) or "无"))
    if not h6_ok:
        return 1

    # ---- H-7：落账**前后**判决链的判据块**逐字节相同** ＋ 整份差异**只**是账本行数 ----
    if not os.path.isdir(RCPT2):
        print("  ⛔ H-7 缺落账后的那份收据目录：%s" % RCPT2)
        return 1
    h7_ok = True
    h7_detail = []
    for f in ("data_before.out", "data_after.out", "mut.out", "cross.out", "spec.out",
              "selftest.out", "cross_selftest.out"):
        a = io.open(os.path.join(RCPT, f), encoding="utf-8", errors="replace").read()
        b = io.open(os.path.join(RCPT2, f), encoding="utf-8", errors="replace").read()
        ka, kb = _block(a, "AUDIT_KEYS"), _block(b, "AUDIT_KEYS")
        na, nb = _block(a, "NUM_MATRIX"), _block(b, "NUM_MATRIX")
        va, vb = _block(a, "ROW_VERDICTS"), _block(b, "ROW_VERDICTS")
        same = (ka == kb) and (na == nb) and (va == vb)
        # 整份：差异**只**许落在「账本总行数」这个 token 上
        na_txt = _norm_ledger_lines(a)
        nb_txt = _norm_ledger_lines(b)
        only_len = (na_txt == nb_txt)
        n_tok = len(re.findall(r"（\d+ 行）|∈ \[1, \d+\]", a))
        if not same or not only_len:
            h7_ok = False
            h7_detail.append("%s：判据块同=%s 归一化后同=%s" % (f, same, only_len))
        elif n_tok == 0:
            # ⛔ 这一份**没有**账本行数 token ⇒ 那它必须**整份逐字节相同**（不许靠归一化蒙混）
            if a != b:
                h7_ok = False
                h7_detail.append("%s：没有账本行数 token 却有差异" % f)
        else:
            h7_detail.append("%s：判据块同 ✅ 整份差异只＝账本行数（%d 处 token）" % (f, n_tok))
    print("  %s H-7 落账前后 7 份收据：判据块**逐字节相同** ＋ 整份差异**只**是账本总行数"
          % ("✅" if h7_ok else "⛔"))
    for d in h7_detail:
        print("      · %s" % d)
    if not h7_ok:
        return 1

    # ---- H-8：判决链（落账前）收据里登记的输入文件 md5 == 本地现算 ----
    r1 = _receipt_inputs(os.path.join(RCPT, "receipt.txt"))
    h8_ok = bool(r1)
    n8 = 0
    for rel, md in sorted(r1.items()):
        p = os.path.join(REPO, rel)
        if not os.path.isfile(p):
            print("  ⛔ H-8 收据登记的文件本地不存在：%s" % rel)
            h8_ok = False
            continue
        cur = _md5(_read_bytes(rel))
        if rel == LEDGER:
            # ⚖ 判决链（落账前）跑的是**落账前**那版账本 ⇒ ⇒ 收据里登记的那个 md5
            #    必须 == **旧前缀 md5**（＝244.95 那次提交里的那份字节）
            #    ⛔ 而**当前整本账本**当然不等于它（它已被追加过 244.96 段）
            #    ⇒ ⇒ 这里只比「收据登记的那个值」；「旧前缀逐字节不变」由 A 条单独守。
            good = (md == PREFIX_MD5)
            note = "（收据登记的是**落账前**那版 ⇒ 必须 == 旧前缀 md5 %s；当前整本=%s）" % (
                PREFIX_MD5, cur)
        else:
            good = (cur == md)
            note = ""
        n8 += 1
        if not good:
            h8_ok = False
        print("  %s H-8 判决链收据登记 %s ｜ 远端=%s 本地=%s %s"
              % ("✅" if good else "⛔", rel, md, cur, note))
    if n8 == 0:
        h8_ok = False
    if not h8_ok:
        return 1

    # ---- H-9：判决链（落账后）收据锚的账本 == 提交里那份；7 份收据 md5 == 本地现算 ----
    r2 = _receipt_inputs(os.path.join(RCPT2, "receipt.txt"))
    h9_ok = bool(r2)
    led2 = r2.get(LEDGER)
    print("  %s H-9a 落账后判决链收据锚的账本 == 提交里那份：%s（期望 %s）"
          % ("✅" if led2 == FULL_MD5 else "⛔", led2 or "(缺)", FULL_MD5))
    if led2 != FULL_MD5:
        h9_ok = False
    for f in ("selftest", "data_before", "data_after", "mut", "cross", "cross_selftest", "spec"):
        p = os.path.join(RCPT2, f + ".out")
        if not os.path.isfile(p):
            print("  ⛔ H-9b 缺落账后收据：%s" % p)
            h9_ok = False
            continue
        cur = _md5(_read_bytes(os.path.relpath(p, REPO)))
        # 远端收据里登记的是**远端路径**，用文件名回查
        remote_md = None
        for _m in re.finditer(r"^([0-9a-f]{32})\s+\S*/%s\.out$" % re.escape(f),
                              io.open(os.path.join(RCPT2, "receipt.txt"),
                                      encoding="utf-8", errors="replace").read(), re.M):
            remote_md = _m.group(1)
        good = (remote_md == cur)
        if not good:
            h9_ok = False
        print("  %s H-9b 落账后收据 %s.out ｜ 远端=%s 本地=%s"
              % ("✅" if good else "⛔", f, remote_md or "(缺)", cur))
    if not h9_ok:
        return 1

    # ---- H-10：落账脚本「防重复落账」闸的**修复验证收据**（远端跑的 15/15）----
    gp = os.path.join(REPO, ".cache", "r244", "_guard24496", "verify.out")
    if not os.path.isfile(gp):
        print("  ⛔ H-10 缺守卫验证收据：%s ⇒ ⇒ 中止" % gp)
        return 1
    gt = io.open(gp, encoding="utf-8", errors="replace").read()
    g_rc = re.search(r"VERIFY_RC=(\d+)", gt)
    g_ok = bool(g_rc) and g_rc.group(1) == "0"
    n_ok = gt.count("✅ 全过")
    n_bad = gt.count("⛔ 有红")
    g_ok = g_ok and n_ok == 5 and n_bad == 0
    print("  %s H-10 守卫修复验证：VERIFY_RC=%s ｜ 全过轮数 %d（期望 5）｜ 有红轮数 %d（期望 0）"
          % ("✅" if g_ok else "⛔", g_rc.group(1) if g_rc else "(缺)", n_ok, n_bad))
    if not g_ok:
        return 1
    # ⚖ 收据里登记的 5 份脚本 md5（**远端现算**）必须 == 本地现算
    for _m in re.finditer(r"^([0-9a-f]{32})\s+\.cache/r244/(_append_2449\d\.py)$", gt, re.M):
        _rel = ".cache/r244/" + _m.group(2)
        _cur = _md5(_read_bytes(_rel))
        _same = (_cur == _m.group(1))
        if not _same:
            g_ok = False
        print("  %s H-10 %s ｜ 远端=%s 本地=%s"
              % ("✅" if _same else "⛔", _rel, _m.group(1), _cur))
    if not g_ok:
        return 1

    # ---- 截短自证：把账本截短 ⇒ ⇒ A–D 必须判红 ⇒ ⇒ 证明它**不是恒绿的** ----
    print("──── 截短自证（账本截短 ⇒ 必须判红）────")
    ok2, res2 = _assertions(ledger_bytes[:cut], index_text, "截短后")
    n_red = sum(1 for _n, g, _d in res2 if not g)
    print("  %s 自证：截短后有 %d 条判红（%s）⇒ ⇒ 这套断言**能红**"
          % ("✅" if n_red > 0 else "⛔", n_red,
             [n for n, g, _d in res2 if not g]))
    if n_red <= 0:
        return 1

    print("✅ 提交后双回读全过（账本 ＋ 索引 ＋ 页面 ＋ 提交清单 ＋ R15 收据 ＋ 判决链收据）")
    print("READBACK_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
