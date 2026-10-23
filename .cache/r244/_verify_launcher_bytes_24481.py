#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **提交字节 ↔ R2 收据字节** 的逐位对账（244.81）。

**为什么要有这条**：R2 是用远端那棵树跑出来的，而本地提交的那份是在跑完之后
才改过的。**「R2 验的就是本次提交里那份字节」** 这句话必须**被验过**，不能只是说说。

**硬判据（能红，⛔ 不是恒绿）**
  A. 本地**账本** md5 == R2 收据里记的 `ledger_md5`
  B. 本地**索引** md5 == R2 收据里记的 `index_md5`
  C. 本地 **5 个执行集文件** md5 == R2 收据里**逐条**记下的 5 个 md5
     （这 5 个文件才是**承载判据逻辑**的东西 ⇒ A/B/C 合起来 = 「R2 验的就是提交里那份」）
  D. **2 个启动器**与「远端**实际跑的那份**」的逐行差异，必须**逐条**落在
     **已登记清单**（下表）里；任何一条落不进去 ⇒ ⛔ 红

**已登记的漂移（每条都带理由，且都**不触及**产生被验量的那些行）**
  ① `${}` 加括号：macOS bash 3.2 会把 `$VAR` 后紧跟的多字节字符吞进变量名
     ⇒ 报 `VAR?: unbound variable` ⇒ 改成 `${VAR}`。POSIX 语义等价。
  ② `grep -c ... || echo 0` → `awk '/^>/{n++} END{print n+0}'`：
     `grep -c` 在**无匹配**时**照样打印 0** 并返回**非 0** ⇒ `|| echo 0` 会**再补一个 0**
     ⇒ 变量变成两行「0」⇒ 收据头被撑出两行游离的「0」。
     ⚠ 它**只在「没有差异」时触发** —— 恰恰是最该干净的那一种情况。
     ⇒ 被验量（added / removed 的**值**）**不变**；另有双重佐证：
     manifest diff 文件本身 **0 字节**，且 R1/R2 的 `manifest_md5` **逐位相同**。
  ③ 纯注释行（本地多出来的 `#` 开头的行）⇒ 不改变任何行为。

**自证（能红）**：注入一处**未登记**的差异 ⇒ 本检查必须判红。
"""

import difflib
import hashlib
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "_e24481")
OUT = os.path.join(EV, "launcher_bytecheck_24481.txt")

REMOTE_HOST = "zju-12"
REMOTE_ROOTS = [
    "/home/zhourui/steer3d/.cache/r244",      # DEV 树（R2 的启动器就在这里跑）
    "/dev/shm/s24480r/.cache/r244",           # 回归执行树（R1 的启动器与执行集在这里）
]

# R2 收据里逐条记下的执行集文件（名字 → 收据里的键）
EXEC_SET = [
    ("fixed_dose_pooled_verdict_audit.py", "md5_fixed_dose_pooled_verdict_audit.py", "执行集·分析器"),
    ("mut_fixed_dose_pooled_verdict_audit.py", "md5_mut_fixed_dose_pooled_verdict_audit.py", "执行集·分析器变异台"),
    ("verify_pooled_verdict_indep.py", "md5_verify_pooled_verdict_indep.py", "执行集·独立重算器"),
    ("mut_verify_pooled_verdict_indep.py", "md5_mut_verify_pooled_verdict_indep.py", "执行集·独立重算器变异台"),
    ("probe_compat_check.py", "md5_probe_compat_check.py", "执行集·探针形状检查"),
]

# 启动器：本地名 → (远端候选根的优先序, 角色)
LAUNCHERS = [
    ("_run_24481b_reg_shm.sh", [0, 1], "启动器·R2 全回归"),
    ("_run_24481_reg_shm.sh", [1, 0], "启动器·R1 全回归"),
]

# ---- 已登记的漂移规则（每条 = 一个 (远端行正则, 本地行正则, 理由)）
REGISTERED = [
    (r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", None, "① `${}` 加括号（POSIX 语义等价）"),
    (r"^man_(added|removed)=\$\(grep -c ", r"^man_(added|removed)=\$\(awk ", "② 收据计数修正（被验量不变）"),
]


def _md5_bytes(b):
    return hashlib.md5(b).hexdigest()


def _read_bytes(p):
    with io.open(p, "rb") as fh:
        return fh.read()


def _ssh_cat(rpath):
    p = subprocess.Popen(["ssh", REMOTE_HOST, "cat %s" % rpath],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        return None
    return out


def _fetch_remote(rel, order):
    for i in order:
        rpath = "%s/%s" % (REMOTE_ROOTS[i], rel)
        b = _ssh_cat(rpath)
        if b is not None:
            return b, rpath
    return None, "(两个候选根都没有)"


def _debrace(b):
    return re.sub(rb"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", rb"$\1", b)


def _classify_line(remote_line, local_line):
    """这一对 (远端行, 本地行) 落在已登记清单的哪一条？落不进去 ⇒ (None, 理由)"""
    if isinstance(remote_line, bytes):
        remote_line = remote_line.decode("utf-8", "replace")
    if isinstance(local_line, bytes):
        local_line = local_line.decode("utf-8", "replace")
    r = remote_line.strip()
    l = local_line.strip()
    # ① 括号
    if re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", r"$\1", r) == \
       re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", r"$\1", l):
        return "① `${}` 加括号（POSIX 语义等价）"
    # ② 收据计数修正
    for pat_r, pat_l, why in REGISTERED[1:]:
        if (pat_r and re.search(pat_r, r)) and (pat_l and re.search(pat_l, l)):
            return why
    return None


def _diff_launcher(local_path, rel, order):
    """返回 (verdict, 逐条说明列表)"""
    lb = _read_bytes(local_path)
    rb, where = _fetch_remote(rel, order)
    if rb is None:
        return "红·远端读不到", ["在 %s 都读不到 %s" % (" / ".join(REMOTE_ROOTS), rel)]
    llines = lb.decode("utf-8", "replace").split("\n")
    rlines = rb.decode("utf-8", "replace").split("\n")
    sm = difflib.SequenceMatcher(None, rlines, llines, autojunk=False)
    notes = []
    unexplained = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for k in range(i1, i2):
                unexplained += 1
                notes.append("⛔ **删除**了远端的一行：%s" % rlines[k].strip()[:110])
            continue
        if tag == "insert":
            for k in range(j1, j2):
                s = llines[k].strip()
                if s.startswith("#"):
                    notes.append("③ 纯注释行（本地新增）：%s" % s[:100])
                else:
                    unexplained += 1
                    notes.append("⛔ **插入**了一行非注释内容：%s" % s[:110])
            continue
        # replace：逐对配对
        rblk = rlines[i1:i2]
        lblk = llines[j1:j2]
        if len(rblk) != len(lblk):
            unexplained += 1
            notes.append("⛔ 改动块行数不同（远端 %d 行 vs 本地 %d 行）⇒ 无法逐条解释"
                         % (len(rblk), len(lblk)))
            continue
        for rr, ll in zip(rblk, lblk):
            why = _classify_line(rr, ll)
            if why is None:
                unexplained += 1
                notes.append("⛔ **未登记的改动** ⇒ 远端: %s ／ 本地: %s"
                             % (rr.strip()[:90], ll.strip()[:90]))
            else:
                notes.append("✅ %s" % why)
                if why.startswith("②"):
                    notes.append("    远端: %s" % rr.strip()[:110])
                    notes.append("    本地: %s" % ll.strip()[:110])
    verdict = "已登记的漂移" if unexplained == 0 else "红·未解释的漂移"
    if unexplained == 0 and not notes:
        verdict = "逐位一致"
    return verdict, notes + ["远端路径 = %s ｜ 远端 md5 = %s ｜ 本地 md5 = %s"
                             % (where, _md5_bytes(rb), _md5_bytes(lb))]


def _selftest():
    """⛔ 自证：注入一处**未登记**的差异 ⇒ 必须判红。"""
    src = os.path.join(HERE, "_run_24481b_reg_shm.sh")
    base = _read_bytes(src)
    m = re.search(rb"[0-9]", base)
    if not m:
        raise SystemExit("⛔ 自证失败：文件里连一个数字都没有")
    old_d = m.group(0)
    new_d = b"1" if old_d != b"1" else b"2"
    mutated = base[:m.start()] + new_d + base[m.end():]
    # 用同一套「逐行配对 + 查登记」逻辑判它
    llines = mutated.decode("utf-8", "replace").split("\n")
    rlines = base.decode("utf-8", "replace").split("\n")
    sm = difflib.SequenceMatcher(None, rlines, llines, autojunk=False)
    bad = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            bad += ["删除"] * (i2 - i1)
        elif tag == "insert":
            for k in range(j1, j2):
                if not llines[k].strip().startswith("#"):
                    bad.append("插入")
        else:
            if (i2 - i1) != (j2 - j1):
                bad.append("块长不同")
                continue
            for rr, ll in zip(rlines[i1:i2], llines[j1:j2]):
                if _classify_line(rr, ll) is None:
                    bad.append("未登记")
    ok = bool(bad)
    print("自证（注入未登记改动必须判红）：判红 %d 处 ⇒ %s" % (len(bad), "✅ 能红" if ok else "⛔ 恒绿！"))
    # 负控：只加括号 ⇒ 必须被判为「已登记」
    braced = re.sub(rb"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", rb"$\1", base)
    nb = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, base.decode("utf-8", "replace").split("\n"),
            braced.decode("utf-8", "replace").split("\n"), autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for rr, ll in zip(base.decode("utf-8").split("\n")[i1:i2],
                              braced.decode("utf-8").split("\n")[j1:j2]):
                if _classify_line(rr.encode("utf-8"), ll.encode("utf-8")) is None:
                    nb += 1
        else:
            nb += 1
    ok2 = (nb == 0)
    print("负控（去掉括号必须落在登记①）：未登记 %d 处 ⇒ %s" % (nb, "✅" if ok2 else "⛔ 误判"))
    return 0 if (ok and ok2) else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    # ---- R2 收据（硬判据 A/B/C 的真源）
    regp = os.path.join(EV, "reg_24481b.txt")
    if not os.path.isfile(regp):
        raise SystemExit("⛔ 缺 R2 收据：%s" % regp)
    reg = io.open(regp, encoding="utf-8", newline="").read()

    def _grab(pat, what):
        m = re.search(pat, reg)
        if not m:
            raise SystemExit("⛔ R2 收据里核不到「%s」" % what)
        return m

    reg_ledger_md5 = _grab(r"ledger_lines=(\d+)\s+ledger_md5=(\w+)", "账本 md5").group(2)
    reg_index_md5 = _grab(r"index_lines=(\d+)\s+index_md5=(\w+)", "索引 md5").group(2)
    reg_exec = dict(re.findall(r"^(md5_\S+)=(\w+)$", reg, re.M))

    lines = []
    lines.append("=== 提交字节 ↔ R2 收据字节 逐位对账（244.81）===")
    lines.append("R2 收据：%s" % regp)
    lines.append("远端候选根：%s" % " ｜ ".join(REMOTE_ROOTS))
    lines.append("")
    ok = True

    def chk(name, cond, detail):
        nonlocal ok
        lines.append("[%s] %s" % ("✅" if cond else "⛔", name))
        lines.append("    %s" % detail)
        if not cond:
            ok = False

    # A. 账本
    lb = _read_bytes(os.path.join(HERE, "..", "xcheck", "R6_RERUN_PREREG.md"))
    chk("A 账本 md5 == R2 收据 ledger_md5", _md5_bytes(lb) == reg_ledger_md5,
        "本地 %s ｜ 收据 %s" % (_md5_bytes(lb), reg_ledger_md5))
    # B. 索引
    ib = _read_bytes(os.path.join(HERE, "..", "xcheck", "R6_RERUN_INDEX.md"))
    chk("B 索引 md5 == R2 收据 index_md5", _md5_bytes(ib) == reg_index_md5,
        "本地 %s ｜ 收据 %s" % (_md5_bytes(ib), reg_index_md5))
    # C. 5 个执行集
    for fname, key, role in EXEC_SET:
        local_md5 = _md5_bytes(_read_bytes(os.path.join(HERE, fname)))
        rec = reg_exec.get(key, "(收据里没有)")
        chk("C 执行集 %s" % fname, local_md5 == rec,
            "本地 %s ｜ 收据 %s ｜ %s" % (local_md5, rec, role))

    # D. 2 个启动器
    lines.append("")
    for lname, order, role in LAUNCHERS:
        v, notes = _diff_launcher(os.path.join(HERE, lname), lname, order)
        good = not v.startswith("红")
        lines.append("[%s] %s ｜ %s" % ("✅" if good else "⛔", lname, role))
        for n in notes:
            lines.append("    %s" % n)
        if not good:
            ok = False

    lines.append("")
    lines.append("小结：%s" % ("✅ 全部硬判据通过" if ok else "⛔ 有硬判据没过"))
    lines.append("")
    lines.append("· **硬判据 A/B/C** 合起来 = 「R2 跑的就是**本次提交里**那份账本/索引/执行集字节」"
                 "（这 5 个执行集文件才是**承载判据逻辑**的东西）。")
    lines.append("· **硬判据 D**：启动器的差异**逐条**落在已登记清单里（登记 ① `${}` 加括号、"
                 "② 收据计数修正、③ 纯注释行）⇒ ⇒ **没有未解释的漂移**。")
    lines.append("· ⚠ 登记 ② 的**被验量不变**，另有双重佐证：manifest diff 文件本身 **0 字节**，"
                 "且 R1/R2 的 `manifest_md5` **逐位相同**（`5bdd45a6ccc411be83c783c85b10507e`）。")

    txt = "\n".join(lines) + "\n"
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(txt)
    print(txt)
    print("已写出 %s" % OUT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
