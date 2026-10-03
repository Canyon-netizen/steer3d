#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前的零成本前置检查：不写文件、不 build、不起服务。

查三件事：
  1. check_table_consistency()  —— MUTS 与 apply() 的分支一一对应
  2. verify_source_untouched()  —— 源码不是残留的变异版（并重刷 pristine）
  3. 每条变异的每一个锚点，在**应用那一刻**恰好命中 1 次

第 3 条用虚拟文件系统跑：apply() 会连着调两三次 edit()，而 edit() 每次
都从磁盘重读。真写盘太慢，直接写会把前一次编辑抹掉，最后一次 write
拿到的其实是「原文 + 最后一次编辑」—— 于是「前一次编辑没生效」这类
bug 在模拟里完全看不见。VFS 让 read/write 都在内存里。

为什么值得单独做这一步：O14 的锚点漏了源码行开头的 `[`，
`src.count(old) == 0`，真跑起来会 ABORT，白扔一整轮 build + 浏览器。
而 18 条里错 1 条 ⇒ 值得在提交前跑，不值得等变异台报回来。
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "rmo", os.path.join(HERE, "run_mut_outcome.py"))
rmo = importlib.util.module_from_spec(spec)
sys.modules["rmo"] = rmo
spec.loader.exec_module(rmo)

fail = []


def note(good, tag, msg):
    print("[%s] %s: %s" % ("PASS" if good else "FAIL", tag, msg))
    if not good:
        fail.append(tag)


# ---- 1. 表结构 ----
try:
    rmo.check_table_consistency()
    note(True, "table", "MUTS %d / apply 分支一一对应" % len(rmo.MUTS))
except SystemExit as e:
    note(False, "table", str(e))

# ---- 2. 源码状态 + 重刷 pristine ----
try:
    rmo.verify_source_untouched()
    note(True, "source", "源码含全部必需标记")
except SystemExit as e:
    note(False, "source", str(e))
    print("    ⇒ 停下来。pristine 已被污染过，build 再多也没用。")

if "source" not in fail:
    rmo.backup()
    pristine = {p: rmo.read(p) for p in (rmo.PANEL, rmo.WSEND)}
    print("[PASS] pristine 已重刷")

    # ---- 3. 锚点在虚拟文件系统里逐条走一遍 ----
    real_read, real_write = rmo.read, rmo.write
    vfs = dict(pristine)
    seen_counts = {}   # (which, tag) -> src.count(old) at apply time

    def vread(p):
        return vfs.get(p) or real_read(p)

    def vwrite(p, t):
        vfs[p] = t
        return t

    def vedit(path, old, new, tag):
        s = vread(path)
        n = s.count(old)
        who = getattr(vedit, "_which", "?")
        seen_counts[(who, tag)] = n
        if n != 1:
            raise AssertionError(
                "锚点 %s 在 %s 里命中 %d 次（应为 1）" % (tag, os.path.basename(path), n))
        vwrite(path, s.replace(old, new, 1))

    rmo.read, rmo.write, rmo.edit = vread, vwrite, vedit

    touched_outside, not_applied, unchanged = [], [], []
    for which in sorted(k for k in rmo.MUTS if k != "BASE"):
        vedit._which = which
        vfs.clear()
        vfs.update(pristine)
        before = len(seen_counts)
        try:
            rmo.apply(which)
        except AssertionError as e:
            note(False, "anchor-%s" % which, str(e))
            continue
        except SystemExit as e:
            not_applied.append((which, str(e)))
            continue
        except Exception as e:  # noqa: BLE001
            note(False, "anchor-%s" % which, "apply() 抛异常 %r" % (e,))
            continue
        if len(seen_counts) == before:
            not_applied.append((which, "一次 edit 都没调"))
        for p in vfs:
            if p not in pristine:
                touched_outside.append((which, p))
        if all(vfs[p] == pristine[p] for p in pristine):
            unchanged.append(which)

    rmo.read, rmo.write, rmo.edit = real_read, real_write, real_write

    for w, why in not_applied:
        note(False, "apply-%s" % w, why)
    for w, p in touched_outside:
        note(False, "scope-%s" % w, "写了台外文件 %s" % p)
    for w in unchanged:
        note(False, "effect-%s" % w, "apply() 跑完产物与原文逐字相同 ⇒ 没变异")

    # ⚠ 汇总行必须把**逐条失败**也算进去。
    #   我第一版只判 not_applied / touched_outside / unchanged 三个列表，
    #   而逐条的 note(False, "anchor-XXX") 是记进 `fail` 的 ——
    #   于是「N3 锚点命中 0 次」和末尾的
    #   「[PASS] anchor: 48 条变异 / 51 个锚点」**同时打了出来**。
    #   一个会在有失败时还说 PASS 的汇总，比没有汇总更坏。
    if not (not_applied or touched_outside or unchanged
            or any(f.startswith("anchor-") for f in fail)):
        n = len([k for k in rmo.MUTS if k != "BASE"])
        note(True, "anchor",
             "%d 条变异 / %d 个锚点：每个恰好命中 1 次，产物均与原文不同"
             % (n, len(seen_counts)))

print()
print("RESULT %s" % ("BAD -> " + ",".join(fail) if fail else "OK"))
sys.exit(1 if fail else 0)
