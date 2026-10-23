#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_phase0_gate_24479.py —— 244.79 固定剂量「合池判决层」**Phase-0 可行性闸门**（零 GPU、纯 CPU）。

⛔ **这是写正式分析器之前的闸门**：闸不过 ⇒ 停。
⛔ **一切运行都在服务器上**（本地只 `compile()` 语法检查）。

## 三道闸

| 闸 | 内容 |
|---|---|
| **G0-1** | 拆分器在**旧批日志**（137 格、单 `pos_frac=0.5`）上跑 ⇒ 拆出产物**逐字节**等于原日志（格区）⇒ 读数器读两份都 rc=0、格数都 137、输出逐行 diff |
| **G0-2** | 统计核心夹具自检：基准 / 多数规则 / 零格 / 未量到格 / 中位数等价 / Wilson / Newcombe / 精确 Fisher / 块级 |
| **G0-3** | 旧批交叉对照：全部格 `w 12/14`、`rand 6/14`；`scope=k` ⇒ `w 10/14` |

## ⚠⚠ 两条**已知的事实偏差**（本脚本按**实测事实**走，不按口头前提走）

1. **旧批日志其实**有 NMAP 来源戳**（`NMAP rows=60 md5=c0d30d22226765b71107ba4db8a2f5af`）
   ⇒ ⇒ 拆出来的那份带的戳**与原日志逐字节相同** ⇒ ⇒ 读数器「`n_eff` 独立来源」那道守卫
   **两边措辞完全一致** ⇒ ⇒ **预期差异行数 = 0**（不是「可能是恒等式」vs「能红」）。
2. **旧批格清单** `warm_cells.txt` 是 **3 列、无表头** ⇒ 拆分器 `read_cells_list()` 会抛
   `ValueError` ⇒ ⇒ 本脚本**从旧批日志自身**导出 4 列带表头清单再喂进去。
   ⚠⚠ **由此带来的副作用（必须记成事实）**：拆分器的 **J1「序号 ⇔ 清单对应行」变成「日志自证」**
   ⇒ ⇒ **J1 在 G0-1 里不是独立验证，不计入独立证据**
   ⇒ ⇒ G0-1 的结论**只**限定在「拆分器没有改动任何一格的内容」（逐字节对照 + 读数器两份输出逐行 diff）。

## 退出码

0 全绿；1 有判据红；2 前置不过（缺文件/解释器不对/输入 md5 不符）。
"""
import argparse
import difflib
import glob
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import OrderedDict
from fractions import Fraction

# ------------------------------------------------------------------ 常量
Z95 = 1.959963984540054
SEED = 20261023

EXPECT_READER_MD5 = "1e31c78ed8f88a61099d2b7fd89665d5"
EXPECT_SPLITTER_MD5 = "f12a56a4227beae503ca1c5f79474e14"

# 旧批输入的 md5（bpath 上的既有产物）
EXPECT_MD5 = {
    "r244_warm_w.log": "6b5ace9922dd26626496677a3428acb2",
    "r244_warm_w_status.txt": "3bf9cce36f17b8fb69904bef52ff5118",
    "warm_cells.txt": "f320436ec2353caa93a1721edf6ad4ec",
    "n_eff_map_pf025.tsv": "942165e3c155f4d69eba4ed933a10eeb",
    "n_eff_map_pf050.tsv": "c0d30d22226765b71107ba4db8a2f5af",
    "n_eff_map_pf075.tsv": "8c865128a5fe73a54664be8f31a76659",
}

# G0-3 的登记值（⛔ **独立字面量**，⛔ 不从被检对象派生）
REG_PANEL = {"w": (12, 14), "rand": (6, 14)}
REG_SCOPE_K_W = (10, 14)

# 独立解析旧批日志用的正则（⛔ **独立于**拆分器/读数器的正则）
BLOCK_BEGIN_RE = re.compile(r"^###\s+BEGIN\s+(\S+)\s+\[(\d+)/(\d+)\]\s*(.*)$")
SCOPE_RE = re.compile(r"--inject-scope\s+(\S+)")
NSITES_RE = re.compile(r"--inject-n-sites\s+(\d+)")
PINNED_RE = re.compile(r"^PINNED\s")
PINNED_PF_RE = re.compile(r"\bPOS_FRAC=([0-9.]+)")
PINNED_EXP_RE = re.compile(r"\bEXPECT_CELLS=(\d+)")
NMAP_STAMP_RE = re.compile(r"^NMAP rows=(\d+) md5=([0-9a-f]{32})(?:\s|$)")
STATUS_PREFIX_RE = re.compile(r"^(?P<tid>\S+) (?P<k>k=(?P<n>\d+)|scope=(?P<s>\S+)) rc=")

# 「读数器两份输出的差异」里**允许**出现的行（来源戳/NMAP 守卫措辞）
BENIGN_DIFF_PAT = ("NMAP", "来源戳", "n_eff 交叉校验", "n_eff 独立来源")


# ------------------------------------------------------------------ 小工具
def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def md5_bytes(b):
    return hashlib.md5(b).hexdigest()


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def split_lines_keepends(data):
    """⚠⚠ **只按 `\\n` 切行**（⛔ **不许**用 `bytes.splitlines()`：它连 `\\r`、
    `\\v`、`\\f` 都当行分隔符 ⇒ 跑批日志里 tqdm 的 `\\r` 会把行结构切碎
    ⇒ ⇒ 逐字节对照会凭空多出几百处「差异」）。
    ⚖ 与拆分器 `text.split("\\n")` 的口径一致。
    """
    parts = data.split(b"\n")
    out = []
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            out.append(p + b"\n")
        elif p:
            out.append(p)
    return out


def diff_lines(a, b, na="A", nb="B"):
    """逐行 diff ⇒ 列出**每一处不同**（含两边行号与原文）。"""
    out = []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                la = a[i1 + k] if i1 + k < i2 else None
                lb = b[j1 + k] if j1 + k < j2 else None
                out.append({"kind": "replace", "a_line": i1 + k + 1, "b_line": j1 + k + 1,
                            "a": la, "b": lb})
        elif tag == "delete":
            for k in range(i1, i2):
                out.append({"kind": "delete", "a_line": k + 1, "b_line": None,
                            "a": a[k], "b": None})
        elif tag == "insert":
            for k in range(j1, j2):
                out.append({"kind": "insert", "a_line": None, "b_line": k + 1,
                            "a": None, "b": b[k]})
    return out


def show_diff(diffs, maxn=200):
    L = []
    for d in diffs[:maxn]:
        L.append("      [%s] %s第 %s 行: %r" % (d["kind"], "原" if d["a_line"] else "拆",
                                               d["a_line"] if d["a_line"] else d["b_line"],
                                               d["a"] if d["a"] is not None else d["b"]))
    if len(diffs) > maxn:
        L.append("      …（还有 %d 处差异）" % (len(diffs) - maxn))
    return L


_MODCACHE = {}


def load_mod(path, name):
    key = os.path.abspath(path)
    if key in _MODCACHE:
        return _MODCACHE[key]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _MODCACHE[key] = mod
    return mod


def patch_all(fname, attr, newval):
    """把**所有**别名实例（同一文件被不同模块名加载出的多个副本）都打上补丁。

    ⚠ 必须按**文件名**打（不能只改一个实例）⇒ `dose_confound_audit.py` 被
    `verdict_panel_audit` / `ledger_cell_census` / `dose_layer_audit` 各自
    加载成三个不同对象 ⇒ 只改一个 ⇒ 变异存活（假绿）。
    """
    hits = []
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if not f or os.path.basename(f) != fname:
            continue
        if not hasattr(mod, attr):
            continue
        setattr(mod, attr, newval)
        hits.append(name)
    return hits


def unpatch_all(fname, attr, orig):
    return patch_all(fname, attr, orig)


# ------------------------------------------------------------------ 闸门容器
class Gate(object):
    def __init__(self, gid, title):
        self.gid = gid
        self.title = title
        self.checks = []
        self.lines = []
        self.defects = []

    def ck(self, cid, name, ok, observed=None, expected=None, detail=""):
        self.checks.append({"id": cid, "name": name, "ok": bool(ok),
                            "expected": expected, "observed": observed,
                            "detail": detail})
        self.lines.append("  [%s] %-12s %s" % ("PASS" if ok else "FAIL", cid, name))
        if observed is not None:
            self.lines.append("        实测: %s" % _fmt_obs(observed))
        if expected is not None:
            self.lines.append("        期望: %s" % _fmt_obs(expected))
        if detail:
            for ln in str(detail).split("\n"):
                self.lines.append("        %s" % ln)
        return bool(ok)

    def defect(self, did, name, ok, observed=None, detail=""):
        """⚠ **缺陷登记项**：⛔ **不参与闸门判决**（不把它算成「闸红」），
        ⛔ 但必须**逐条报告**（不许藏）。"""
        self.defects.append({"id": did, "name": name, "ok": bool(ok),
                             "observed": observed, "detail": detail})
        self.lines.append("  [%s] %-12s 【缺陷登记项 · 不参与闸门判决】%s"
                          % ("OK  " if ok else "WARN", did, name))
        if observed is not None:
            self.lines.append("        实测: %s" % _fmt_obs(observed))
        if detail:
            for ln in str(detail).split("\n"):
                self.lines.append("        %s" % ln)
        return bool(ok)

    def say(self, s=""):
        self.lines.append(s)

    @property
    def n_pass(self):
        return sum(1 for c in self.checks if c["ok"])

    @property
    def n_fail(self):
        return sum(1 for c in self.checks if not c["ok"])

    @property
    def status(self):
        return "PASS" if self.n_fail == 0 else "FAIL"


def _fmt_obs(o):
    if isinstance(o, dict):
        return " ｜ ".join("%s=%s" % (k, _fmt_obs(v)) for k, v in o.items())
    if isinstance(o, (list, tuple)):
        return "[" + ", ".join(_fmt_obs(v) for v in o) + "]"
    if isinstance(o, float):
        return ("%.10g" % o)
    return str(o)


class Ctx(object):
    def __init__(self, args):
        self.args = args
        self.tree = os.path.abspath(args.tree)
        self.r244 = os.path.join(self.tree, ".cache", "r244")
        self.mutbak = os.path.join(self.tree, ".cache", "mutbak")
        self.dev = os.path.abspath(args.dev)
        self.bpath = os.path.abspath(args.bpath)
        self.outdir = os.path.abspath(args.outdir)
        self.split_dir = os.path.join(self.outdir, "split_old")
        self.cells_dir = os.path.join(self.outdir, "cells")
        self.reader = os.path.join(self.dev, "_k23_reader_r227_kcurve.py")
        self.splitter = os.path.join(self.dev, "fixed_dose_split_log.py")
        self.orig_log = os.path.join(self.bpath, "r244_warm_w.log")
        self.orig_status = os.path.join(self.bpath, "r244_warm_w_status.txt")
        self.old_cells = os.path.join(self.bpath, "warm_cells.txt")
        self.nmap_prefix = os.path.join(self.bpath, "n_eff_map")
        self.cells_tsv = os.path.join(self.cells_dir, "old_cells_4col.tsv")

    def r(self, *p):
        return os.path.join(self.r244, *p)


# ================================================================== G0-1
def parse_old_log(path):
    """**独立**解析旧批日志（⛔ 不用拆分器/读数器的正则）⇒ 只用于派生 4 列清单 + 逐字节对照。"""
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    head, blocks, cur = [], [], None
    for ln in text.split("\n"):
        m = BLOCK_BEGIN_RE.match(ln)
        if m:
            if cur is not None:
                blocks.append(cur)
            cur = {"begin": ln, "tid": m.group(1), "idx": int(m.group(2)),
                   "tot": int(m.group(3)), "rest": m.group(4), "lines": []}
            continue
        if cur is None:
            head.append(ln)
        else:
            cur["lines"].append(ln)
    if cur is not None:
        blocks.append(cur)
    return head, blocks


def block_reading(block):
    for ln in block["lines"]:
        s = ln.strip()
        if s.startswith("{") and '"tid"' in s:
            try:
                return json.loads(s.rstrip(","))
            except Exception:
                return None
    return None


def derive_cells_tsv(ctx):
    """从**旧批日志自身**导出 4 列带表头清单。

    ⚠⚠ **事实记录**：由此导出 ⇒ 拆分器的 **J1 变成「日志自证」**
    ⇒ ⇒ J1 在 G0-1 里**不是独立验证**，不计入独立证据。
    """
    head, blocks = parse_old_log(ctx.orig_log)
    pinned = {}
    for ln in head:
        if PINNED_RE.match(ln):
            mp = PINNED_PF_RE.search(ln)
            me = PINNED_EXP_RE.search(ln)
            if mp:
                pinned["pos_frac"] = float(mp.group(1))
            if me:
                pinned["expect_cells"] = int(me.group(1))
    rows, bad = [], []
    for b in blocks:
        rd = block_reading(b)
        ms = SCOPE_RE.search(b["rest"])
        mn = NSITES_RE.search(b["rest"])
        if rd is None or ms is None:
            bad.append(b["tid"])
            continue
        # ⚖ 端点格（scope = single / all）的 BEGIN 行**没有** `--inject-n-sites`
        #   ⇒ `n_sites` 记 0（拆分器只在 scope=='k' 时用它做 status 前缀匹配）
        n_sites = int(mn.group(1)) if mn is not None else 0
        rows.append({"tid": b["tid"], "scope": ms.group(1),
                     "n_sites": n_sites,
                     "pos_frac": float(rd["pos_frac"])})
    if not os.path.isdir(ctx.cells_dir):
        os.makedirs(ctx.cells_dir)
    with open(ctx.cells_tsv, "w", encoding="utf-8") as fh:
        fh.write("tid\tscope\tn_sites\tpos_frac\n")
        for r in rows:
            fh.write("%s\t%s\t%d\t%.2f\n" % (r["tid"], r["scope"], r["n_sites"], r["pos_frac"]))
    return head, blocks, rows, pinned, bad


def _head_body_lines(path):
    data = read_bytes(path)
    lines = split_lines_keepends(data)
    for i, ln in enumerate(lines):
        if ln.startswith(b"### BEGIN"):
            return lines, i
    return lines, len(lines)


def c_g0_1_bytes(ctx, state):
    """G0-1.3：逐字节对照（**格区** = 「拆分器没有改动任何一格」）。

    返回 (ok, obs, detail_lines) —— `ok` 只覆盖**格区**（任务书 G0-1.3 明说
    「去掉头部 SPLIT 行与来源戳行之后」⇒ 头部**不**属于比较对象）。
    """
    shard = state["shard"]
    ol, oi = _head_body_lines(ctx.orig_log)
    sl, si = _head_body_lines(shard)
    obs, detail = {}, []

    ohead = [l.decode("utf-8", "replace").rstrip("\n") for l in ol[:oi]]
    shead = [l.decode("utf-8", "replace").rstrip("\n") for l in sl[:si]]
    detail.append("原日志头部 %d 行：%s" % (oi, ohead))
    detail.append("分片头部 %d 行：%s" % (si, shead))

    # ---- 3a 格区（首个 '### BEGIN' 起）逐字节 ----
    ob, sb = b"".join(ol[oi:]), b"".join(sl[si:])
    raw_ok = (ob == sb)
    on, sn = ob.rstrip(b"\n"), sb.rstrip(b"\n")
    norm_ok = (on == sn)
    trail_o = len(ob) - len(on)
    trail_s = len(sb) - len(sn)
    obs["3a 格区字节"] = {"原": len(ob), "拆": len(sb),
                          "md5_原": md5_bytes(ob), "md5_拆": md5_bytes(sb),
                          "原尾部换行字节": trail_o, "拆尾部换行字节": trail_s,
                          "原始逐字节相同": raw_ok}
    detail.append("3a 格区：原 %d 字节 md5=%s ｜ 拆 %d 字节 md5=%s"
                  % (len(ob), md5_bytes(ob), len(sb), md5_bytes(sb)))
    detail.append("    原始逐字节比较：%s"
                  % ("相同 ✅" if raw_ok else
                     "不同（尾部换行：原 %d 个 / 拆 %d 个；**内容部分** md5 %s vs %s ⇒ %s）"
                     % (trail_o, trail_s, md5_bytes(on), md5_bytes(sn),
                        "内容逐字节相同 ✅" if norm_ok else "⛔ 内容也不同")))

    # ---- 3c 行级对照 ----
    # 3c-1 **格区**逐行对照 ⇒ 必须**零差异**（尾部纯换行行除外）
    def drop_tail_newlines(lines):
        out = list(lines)
        while out and out[-1].strip() == b"":
            out.pop()
        return out
    ob_lines = drop_tail_newlines(ol[oi:])
    sb_lines = drop_tail_newlines(sl[si:])
    cell_diffs = diff_lines(ob_lines, sb_lines)
    # 3c-2 **整文件**逐行对照（只从分片去掉 SPLIT+NMAP，原日志不动）⇒ 差异清单（任务书要求逐行列出）
    full_diffs = diff_lines(ol, sl)
    out_of_head = [d for d in full_diffs
                   if (d["a_line"] is not None and d["a_line"] > oi)
                   or (d["b_line"] is not None and d["b_line"] > si)]
    c_ok = (len(cell_diffs) == 0)
    obs["3c 格区行级差异处数"] = len(cell_diffs)
    obs["3c 整文件差异处数"] = len(full_diffs)
    obs["3c 整文件差异落在格区之外的处数"] = len(out_of_head)
    detail.append("3c-1 **格区**逐行对照（尾部纯换行行除外）：差异 %d 处 ⇒ %s"
                  % (len(cell_diffs), "零差异 ✅" if c_ok else "⛔ 有差异"))
    detail.append("3c-2 **整文件**逐行对照（只从分片去掉 SPLIT+NMAP、原日志不动）：差异 %d 处，"
                  "其中落在格区之外的 %d 处 ⇒ %s"
                  % (len(full_diffs), len(out_of_head),
                     "全部只是原日志的头部行（预期）" if not out_of_head else "⛔ 有格区内的差异"))
    detail.append("   —— 整文件逐处差异（行号 + 原文）——")
    detail.extend(show_diff(full_diffs))
    if cell_diffs:
        detail.append("   —— 格区逐处差异（行号 + 原文）——")
        detail.extend(show_diff(cell_diffs))

    ok = norm_ok and c_ok
    if not norm_ok:
        n_cr_o = sum(1 for l in ol[oi:] if b"\r" in l)
        n_cr_s = sum(1 for l in sl[si:] if b"\r" in l)
        obs["裸 \\r 行数 原/拆"] = (n_cr_o, n_cr_s)
        detail.append("")
        detail.append("⚠⚠⚠ **根因（已定位）**：拆分器的 `_read()` 用 "
                      "`open(path, encoding='utf-8').read()` ⇒ **Python 通用换行模式**")
        detail.append("    ⇒ **裸 `\\r`（tqdm 进度条写的 CR，不带 LF）被当作行分隔符并改写成 `\\n`**")
        detail.append("    ⇒ 原日志含裸 `\\r` 的行 %d 行；拆出来的分片含裸 `\\r` 的行 %d 行"
                      % (n_cr_o, n_cr_s))
        detail.append("    ⇒ ⇒ **拆分器确实改动了日志的字节**（改的是 tqdm 进度条那行，"
                      "**不是**读数 JSON ⇒ 读数一个数都没变）")
        detail.append("    ⇒ ⇒ 违反拆分器自己的契约「⛔ **不改任何一个读数**…逐字节照抄」"
                      "在**整份日志**层面的推广")
        detail.append("    ⇒ ⇒ 修法：`_read()` 改成 `open(path, encoding='utf-8', newline='')`"
                      "（⛔ 保留裸 `\\r`）⇒ 才能真正逐字节保真")
    return ok, obs, detail


def c_g0_1_stamp(ctx, state):
    """G0-1.D1：**缺陷登记项**（不参与闸门判决，但必须报告）——
    拆出来的来源戳行是否与原日志的那一行**逐字节相同**。"""
    shard = state["shard"]
    ol, oi = _head_body_lines(ctx.orig_log)
    sl, si = _head_body_lines(shard)
    o_stamp = None
    for l in ol[:oi]:
        if NMAP_STAMP_RE.match(l.decode("utf-8", "replace")):
            o_stamp = l
            break
    s_stamp = None
    for l in sl[:si]:
        if NMAP_STAMP_RE.match(l.decode("utf-8", "replace")):
            s_stamp = l
            break
    same = (o_stamp is not None and o_stamp == s_stamp)
    obs = {"原来源戳": o_stamp.decode("utf-8", "replace").rstrip("\n") if o_stamp else None,
           "拆来源戳": s_stamp.decode("utf-8", "replace").rstrip("\n") if s_stamp else None,
           "逐字节相同": same}
    detail = []
    if not same:
        mo = NMAP_STAMP_RE.match(o_stamp.decode("utf-8", "replace")) if o_stamp else None
        ms = NMAP_STAMP_RE.match(s_stamp.decode("utf-8", "replace")) if s_stamp else None
        if mo and ms:
            obs["rows 原/拆"] = (int(mo.group(1)), int(ms.group(1)))
            obs["md5 原/拆"] = (mo.group(2), ms.group(2))
        detail.append("⚠⚠ **缺陷**：拆出来的来源戳行与原日志的**不是**同一行。")
        detail.append("    原：%r" % (o_stamp.decode("utf-8", "replace").rstrip("\n") if o_stamp else None))
        detail.append("    拆：%r" % (s_stamp.decode("utf-8", "replace").rstrip("\n") if s_stamp else None))
        detail.append("    ⇒ 根因：生产者 `_make_nmap_24477.sh:35` 的口径是 `wc -l − 1`"
                      "（= **数据行数**），拆分器 `fixed_dose_split_log.py:158` 的口径是"
                      " `len(read().split('\\n')) − 1`（= **总行数**）⇒ **差 1**。")
        detail.append("    ⇒ ⚠ **拆分器的 J9 抓不到它**：J9 拿写出去的戳去比它自己算的"
                      " `w['rows']` ⇒ **自指 ⇒ 恒绿**。")
        detail.append("    ⇒ 影响面：`md5` 相同（表的身份没问题）⇒ 读数一个数都没变；"
                      "但读数器收据里「来源戳 rows=…」这一行会与原日志不同 ⇒"
                      " 那是**预期措辞差异**，不是红。")
    else:
        detail.append("来源戳行逐字节相同 ✅")
    return same, obs, detail


def run_reader(ctx, log, status):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, ctx.reader, "--log", log, "--status", status],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    return (p.returncode,
            p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def c_g0_1_reader(ctx, state):
    """G0-1.4：读数器对账。返回 (ok, obs, detail_lines)"""
    rc_o, out_o, err_o = run_reader(ctx, ctx.orig_log, ctx.orig_status)
    rc_s, out_s, err_s = run_reader(ctx, state["shard"], state["shard_status"])
    a = out_o.split("\n")
    b = out_s.split("\n")
    diffs = diff_lines(a, b)

    def _cls(d):
        txt = (d["a"] or "") + (d["b"] or "")
        if any(p in txt for p in BENIGN_DIFF_PAT):
            return "来源戳/NMAP 守卫措辞"
        if "ALLDONE" in txt:
            return "status 尾行措辞"
        return "**读数层**"

    buckets = OrderedDict()
    for d in diffs:
        buckets.setdefault(_cls(d), []).append(d)
    benign = buckets.get("来源戳/NMAP 守卫措辞", []) + buckets.get("status 尾行措辞", [])
    hard = buckets.get("**读数层**", [])

    def n_cells(txt):
        m = re.search(r"共\s+(\d+)\s+格\s+——\s+有读数\s+(\d+)", txt)
        return (int(m.group(1)), int(m.group(2))) if m else (None, None)

    co, cs = n_cells(out_o), n_cells(out_s)
    obs = {
        "原 rc": rc_o, "拆 rc": rc_s,
        "原 格数/有读数": co, "拆 格数/有读数": cs,
        "输出行数 原/拆": (len(a), len(b)),
        "差异处数": len(diffs),
        "差异分类": dict((k, len(v)) for k, v in buckets.items()),
        "读数层差异处数": len(hard),
        "原 stderr": err_o.strip()[:200], "拆 stderr": err_s.strip()[:200],
    }
    detail = ["读数器（原日志+原 status）rc=%d ｜ 格数=%s" % (rc_o, co),
              "读数器（拆片+拆 status）rc=%d ｜ 格数=%s" % (rc_s, cs),
              "两份输出的差异共 %d 处 ｜ 分类：%s"
              % (len(diffs), dict((k, len(v)) for k, v in buckets.items())),
              "   —— 逐处差异（行号 + 原文）——"]
    detail.extend(show_diff(diffs))
    if not diffs:
        detail.append("      （**没有任何差异行** ⇒ 两份收据逐行相同）")
    ok = (rc_o == 0 and rc_s == 0 and co == (137, 137) and cs == (137, 137)
          and len(hard) == 0)
    return ok, obs, detail, buckets


def run_g0_1(ctx, state):
    G = Gate("G0-1", "拆分器不改动任何一格")
    G.say("=" * 78)
    G.say("【G0-1】拆分器不改动任何一格（对象 = 旧批 137 格 / 单 pos_frac=0.5）")
    G.say("=" * 78)

    # ---- 前置 ----
    rmd5 = md5_file(ctx.reader) if os.path.isfile(ctx.reader) else "MISSING"
    G.ck("G0-1.P0", "权威读数器 md5 == %s" % EXPECT_READER_MD5,
        rmd5 == EXPECT_READER_MD5, {"实测": rmd5}, {"期望": EXPECT_READER_MD5},
        "文件：%s" % ctx.reader)
    smd5 = md5_file(ctx.splitter) if os.path.isfile(ctx.splitter) else "MISSING"
    smtime = (time.strftime("%Y-%m-%dT%H:%M:%S",
                             time.localtime(os.path.getmtime(ctx.splitter)))
              if os.path.isfile(ctx.splitter) else "MISSING")
    G.ck("G0-1.P1", "被检拆分器**指纹**（记录用；⛔ 不作为判据：它是别人正在改的活文件）",
        os.path.isfile(ctx.splitter),
        {"md5": smd5, "字节": os.path.getsize(ctx.splitter) if os.path.isfile(ctx.splitter) else None,
         "mtime": smtime,
         "任务书登记的 md5": EXPECT_SPLITTER_MD5,
         "是否仍等于任务书登记值": smd5 == EXPECT_SPLITTER_MD5},
        None,
        "⚠ 记录：拆分器 md5 在本闸门跑动期间**变了**（任务书登记 %s ⇒ 现为 %s）\n"
        "        ⇒ 本闸门的全部结论都是对**当前这版**（%s，%s 字节）做的。"
        % (EXPECT_SPLITTER_MD5, smd5, smd5,
           os.path.getsize(ctx.splitter) if os.path.isfile(ctx.splitter) else "?"))

    md5s = OrderedDict()
    bad_md5 = []
    for name, want in EXPECT_MD5.items():
        p = os.path.join(ctx.bpath, name)
        got = md5_file(p) if os.path.isfile(p) else "MISSING"
        md5s[name] = got
        if got != want:
            bad_md5.append("%s 实测 %s 期望 %s" % (name, got, want))
    G.ck("G0-1.P2", "旧批输入 md5 逐条相符（5 个既有产物）",
        not bad_md5, md5s, "见任务书登记值", "; ".join(bad_md5))

    # ---- 旧批 status 排版（拆分器用前缀 'tid k=N ' / 'tid scope=S ' 匹配）----
    st_lines = [l for l in open(ctx.orig_status, encoding="utf-8").read().split("\n") if l]
    n_k = sum(1 for l in st_lines if STATUS_PREFIX_RE.match(l) and l.split(" ")[1].startswith("k="))
    n_sc = sum(1 for l in st_lines if STATUS_PREFIX_RE.match(l) and l.split(" ")[1].startswith("scope="))
    n_all = sum(1 for l in st_lines if STATUS_PREFIX_RE.match(l))
    # ⚖ 旧批 status 末行是 `ALLDONE 21:16:01`（**带钟面**）⇒ 用 `startswith`
    n_alldone = sum(1 for l in st_lines if l.strip().startswith("ALLDONE"))
    G.ck("G0-1.P3", "旧批 status 行排版 = 'tid k=N rc=0' / 'tid scope=S rc=0'（拆分器前缀匹配适用 ⇒ J8 适用）",
        (n_all == len(st_lines) - n_alldone) and n_k > 0 and n_sc > 0,
        {"总行数": len(st_lines), "匹配 'tid k=N '": n_k, "匹配 'tid scope=S '": n_sc,
         "ALLDONE 行": n_alldone},
        {"期望": "全部非 ALLDONE 行都能被前缀匹配（109 + 28 = 137）"},
        "样例：%r / %r / 末行 %r"
        % (st_lines[0] if st_lines else None,
           next((l for l in st_lines if " scope=" in l), None),
           st_lines[-1] if st_lines else None))

    # ---- 派生 4 列清单 ----
    head, blocks, rows, pinned, badrows = derive_cells_tsv(ctx)
    pfs = sorted(set(r["pos_frac"] for r in rows))
    G.ck("G0-1.P4", "从**旧批日志自身**导出 4 列清单（warm_cells.txt 是 3 列无表头，喂不进拆分器）",
        (not badrows) and len(rows) == 137 and pfs == [0.5],
        {"导出格数": len(rows), "pos_frac 集合": pfs,
         "日志 PINNED POS_FRAC": pinned.get("pos_frac"),
         "日志 PINNED EXPECT_CELLS": pinned.get("expect_cells"),
         "解析失败行": badrows[:3]},
        {"期望格数": 137, "pos_frac": [0.5]},
        "⚠⚠ **事实**：由此导出 ⇒ 拆分器的 J1「序号 ⇔ 清单对应行」变成**日志自证**\n"
        "        ⇒ ⇒ **J1 在 G0-1 里不是独立验证，不计入独立证据**\n"
        "        ⇒ ⇒ G0-1 的结论只限定在「拆分器没有改动任何一格的内容」。")

    # ---- 跑拆分器（真 CLI）----
    if os.path.isdir(ctx.split_dir):
        shutil.rmtree(ctx.split_dir)
    os.makedirs(ctx.split_dir)
    cmd = [sys.executable, ctx.splitter,
           "--log", ctx.orig_log, "--status", ctx.orig_status,
           "--cells", ctx.cells_tsv, "--nmap-prefix", ctx.nmap_prefix,
           "--outdir", ctx.split_dir]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    so = p.stdout.decode("utf-8", "replace")
    se = p.stderr.decode("utf-8", "replace")
    state["split_stdout"] = so
    jrows = [l for l in so.split("\n") if l.startswith("[OK  ]") or l.startswith("[FAIL]")]
    j_ok = [l for l in jrows if l.startswith("[OK  ]")]
    j_bad = [l for l in jrows if l.startswith("[FAIL]")]
    # ⚖ **读数层**判据（与「有没有改任何一格的内容」直接相关）
    READ_J = ("J2", "J3", "J6", "J7", "J8", "J10")
    read_j_bad = [l for l in j_bad if any(("%s " % j) in l for j in READ_J)]
    G.ck("G0-1.1", "拆分器 CLI 在旧批上跑完，且**读数层判据**（J2/J3/J6/J7/J8/J10）全绿",
        (p.returncode in (0, 1) and not read_j_bad and len(j_ok) >= 6),
        {"rc": p.returncode, "判据绿/红": (len(j_ok), len(j_bad)),
         "红了的判据": [l.split("]")[1].split("（")[0].strip() for l in j_bad],
         "读数层判据是否全绿": not read_j_bad,
         "checks_failed 行": [l for l in so.split("\n") if l.startswith("checks_failed=")]},
        {"读数层判据": "全绿（J6 读数 JSON 逐字节相同）"},
        "stderr：%s" % (se.strip()[:400] or "（空）"))
    # ---- 缺陷登记项：拆分器自带 11 条判据在**旧批形状**上不全绿 ----
    if j_bad:
        _hb, _bl = parse_old_log(ctx.orig_log)
        n_cells = len(_bl)
        n_tid = len(set(b["tid"] for b in _bl))
        G.defect("G0-1.D2", "拆分器自带 11 条判据在**旧批形状**上不全绿",
                 False,
                 {"红了的判据": [l.split("]")[1].split("（")[0].strip() for l in j_bad],
                  "旧批格数": n_cells, "旧批轨迹数": n_tid,
                  "按 (tid,pos_frac) 去重后的唯一键数": n_tid,
                  "J4 会报的重复数": n_cells - n_tid},
                 "⚠⚠ **根因**：`fixed_dose_split_log.py` 的 J4 用 **(tid, pos_frac)** 做唯一键，\n"
                 "        而**旧批**里同一个 tid 在同一个 pos_frac=0.5 上有 **9~10 个格**\n"
                 "        （k=1,6,27,…,single,all）⇒ 唯一键**不唯一** ⇒ J4 必然报「重复」。\n"
                 "        ⇒ ⇒ **J4 的口径只在新批形状（一 tid 一 pos_frac 一格）上成立**。\n"
                 "        ⇒ ⇒ 旧批 %d 格 / %d 条轨迹 ⇒ 唯一键 %d 个 ⇒ J4 会报 %d 处「重复」。\n"
                 "        ⇒ ⇒ **这是判据口径与批次形状不兼容，不是拆分器改坏了数据**。\n"
                 "        ⇒ ⇒ ⚠ 拆分器**自带的 11 条判据在旧批上不能当独立验证用**。"
                 % (n_cells, n_tid, n_tid, n_cells - n_tid))

    # ---- 只有一个分片、137 格 ----
    shards = sorted(glob.glob(os.path.join(ctx.split_dir, "pf*.log")))
    shard = shards[0] if shards else None
    shard_status = (shard[:-4] + "_status.txt") if shard else None
    n_blocks = 0
    shard_pfs = set()
    if shard:
        _h, sb = parse_old_log(shard)
        n_blocks = len(sb)
        for b in sb:
            rd = block_reading(b)
            if rd:
                shard_pfs.add(float(rd["pos_frac"]))
    state["shard"] = shard
    state["shard_status"] = shard_status
    G.ck("G0-1.2", "拆出**恰好 1 个**分片（pf=0.50）、含 137 格、内部 pos_frac 单一",
        (len(shards) == 1 and n_blocks == 137 and shard_pfs == {0.5}),
        {"分片数": len(shards), "分片名": [os.path.basename(s) for s in shards],
         "格数": n_blocks, "分片内 pos_frac": sorted(shard_pfs),
         "status 文件": os.path.basename(shard_status) if shard_status else None},
        {"分片数": 1, "格数": 137, "pos_frac": [0.5]})

    # ---- 逐字节对照 ----
    if shard:
        ok, obs, detail = c_g0_1_bytes(ctx, state)
        G.ck("G0-1.3", "逐字节对照（**格区**）：拆分产物**没有改动任何一格**",
            ok, obs, {"格区内容逐字节相同": True},
            "\n".join(detail))
        state["g0_1_bytes_ok"] = ok
        # ---- 缺陷登记项（不参与闸门判决）----
        dok, dobs, ddetail = c_g0_1_stamp(ctx, state)
        G.defect("G0-1.D1", "拆出来的来源戳行 vs 原日志的来源戳行（逐字节）",
                 dok, dobs, "\n".join(ddetail))
        state["g0_1_stamp_ok"] = dok
    else:
        G.ck("G0-1.3", "逐字节对照（**格区**）：拆分产物**没有改动任何一格**",
            False, {"分片": None}, "有分片", "没有分片 ⇒ 无法对照")
        state["g0_1_bytes_ok"] = False

    # ---- 读数器对账 ----
    if shard and os.path.isfile(shard_status):
        ok, obs, detail, buckets = c_g0_1_reader(ctx, state)
        G.ck("G0-1.4", "读数器对账：两份都 rc=0、格数都 137、输出逐行 diff"
                       "（⛔ **读数层**差异必须为 0；措辞差异逐行列出）",
            ok, obs, {"rc": 0, "格数": [137, 137], "读数层差异": 0},
            "\n".join(detail))
        state["g0_1_reader_ok"] = ok
        # ---- 缺陷登记项：status 尾行措辞（拆分器写裸 ALLDONE）----
        if buckets.get("status 尾行措辞"):
            G.defect("G0-1.D3", "status 尾行措辞不同（拆分器写裸 `ALLDONE`，生产者写 `ALLDONE <钟面>`）",
                     False,
                     {"差异处数": len(buckets["status 尾行措辞"]),
                      "原文": [d["a"] for d in buckets["status 尾行措辞"]]},
                     "⚠ 差异**不涉及任何读数**（137 格读数逐行相同）⇒ 只是 status 末行措辞。\n"
                     "        ⇒ 生产者 `r244_warm_sweep.sh` 写 `ALLDONE <钟面>`，"
                     "拆分器写裸 `ALLDONE`。")
    else:
        G.ck("G0-1.4", "读数器对账", False, {"分片": shard, "status": shard_status},
            "有分片与 status", "缺分片/status ⇒ 无法对账")
        state["g0_1_reader_ok"] = False

    G.say("")
    G.say("G0-1 小计：%d 条判据，PASS %d，FAIL %d ⇒ %s"
          % (len(G.checks), G.n_pass, G.n_fail, G.status))
    return G


# ================================================================== G0-2
def build_fixture(seed=SEED, n_prob=28, pfs=(0.25, 0.5, 0.75)):
    """56 tid × 3 pos_frac × 2 臂 = 336 格的**合成**夹具（固定种子）。"""
    rng = random.Random(seed)
    cells = {"w": [], "rand": []}
    for pi in range(n_prob):
        for v in ("think", "no_think"):
            tid = "aime__aime25__p%02d__%s" % (pi, v)
            for pf in pfs:
                n_sites = int(round(400 * pf))
                n_eff = 4 * n_sites          # ⇒ 密度 = n_sites/n_eff = 0.25（三个副本相等）
                for arm in ("w", "rand"):
                    drift = 0.030 if arm == "w" else 0.000
                    lo = rng.gauss(0.0, 0.02)
                    hi = lo + rng.gauss(drift, 0.02)
                    cells[arm].append({
                        "tid": tid, "pos_frac": pf, "inject_scope": "k",
                        "inject_n_sites": n_sites, "n_eff": n_eff,
                        "p9_lo_meas": lo, "p9_hi_meas": hi,
                        "up_mono_meas": bool(hi >= lo), "arm": arm})
    return cells


def pooled_cellset(cells):
    """K5 格集合：`scope=k` ∧ 读数非空 ∧ `n_sites` 真 ∧ **密度相等**。"""
    keep = []
    for c in cells:
        if c.get("inject_scope") != "k":
            continue
        if c.get("p9_lo_meas") is None or c.get("p9_hi_meas") is None:
            continue
        if not c.get("inject_n_sites"):
            continue
        keep.append(c)
    dens = {}
    for c in keep:
        dens.setdefault(c["tid"], set()).add(
            round(c["inject_n_sites"] / float(c["n_eff"]), 12))
    bad = [t for t, s in dens.items() if len(s) > 1]
    if bad:
        raise RuntimeError("密度不等的轨迹：%s" % bad[:3])
    return keep


def by_tid(cells):
    out = OrderedDict()
    for c in cells:
        out.setdefault(c["tid"], []).append(c)
    return out


def median_sign(vals, ge=False):
    """⚙ **可注入**：中位数符号规则。`ge=True` ⇒ 故意破坏版（`>= 0`）。"""
    s = sorted(vals)
    m = s[len(s) // 2]
    return (m >= 0) if ge else (m > 0)


def strict_majority(vals):
    """⚖ 严格多数（平票 False）—— 独立实现（⛔ 不从被检对象派生）。"""
    npos = sum(1 for v in vals if v > 0)
    return npos * 2 > len(vals)


def wilson_grid(x, n, z=Z95, step=1e-6):
    """⚙ **独立**核对：网格反演 Wilson 区间。"""
    phat = x / float(n)
    lo = hi = None
    p = 0.0
    while p <= 1.0 + 1e-12:
        if abs(phat - p) <= z * math.sqrt(max(0.0, p * (1.0 - p)) / n) + 1e-15:
            if lo is None:
                lo = p
            hi = p
        p += step
    return lo, hi


def wald_diff(x1, n1, x2, n2, z=Z95):
    p1, p2 = x1 / float(n1), x2 / float(n2)
    d = p1 - p2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return (d - z * se, d + z * se)


def fisher_enum_exact(a, b, c, d):
    """⚙ **独立**穷举枚举（精确有理数 `Fraction`）：超几何概率之和 ≤ p_obs。"""
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    if n == 0:
        return None
    den = math.comb(n, c1)

    def prob(x):
        return Fraction(math.comb(r1, x) * math.comb(r2, c1 - x), den)
    p_obs = prob(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    tot = Fraction(0)
    for x in range(lo, hi + 1):
        px = prob(x)
        if px <= p_obs:
            tot += px
    return float(min(Fraction(1), tot))


def fisher_normal_approx(a, b, c, d):
    """⚙ 正态近似（**故意破坏**用）：连续性校正的 2×2 比例差 z 检验。"""
    n = a + b + c + d
    if n == 0:
        return None
    p1 = (a + 0.5) / float(a + b + 1.0)
    p2 = (c + 0.5) / float(c + d + 1.0)
    se = math.sqrt(p1 * (1 - p1) / (a + b + 1.0) + p2 * (1 - p2) / (c + d + 1.0))
    if se <= 0:
        return 1.0
    z = abs(p1 - p2) / se
    return math.erfc(z / math.sqrt(2.0))


def analytic_sign_test_p(k_pos, n):
    """⚙ 独立闭式：精确双尾符号检验 p = 2·P(X ≤ min(k, n−k))（X~Bin(n,0.5)）。"""
    m = min(k_pos, n - k_pos)
    if n == 0:
        return None
    if m * 2 == n:
        return 1.0
    tot = sum(math.comb(n, j) for j in range(m + 1))
    return float(Fraction(2 * tot, 2 ** n))


def c_g0_2_base(ctx, state):
    """G0-2.1：`majority_base_p2` 的已知答案。"""
    DLA = state["DLA"]
    want = [((3, 0), 0.5), ((2, 0), 0.25), ((2, 1), 0.25), ((1, 0), 0.5), ((0, 0), 0.5)]
    obs, bad = OrderedDict(), []
    for (a, b), exp in want:
        got = DLA.majority_base_p2(a, b)
        obs["p2(%d,%d)" % (a, b)] = got
        if abs(got - exp) > 1e-12:
            bad.append("p2(%d,%d) 实测 %s 期望 %s" % (a, b, got, exp))
    return (not bad), obs, {"期望": dict(("p2(%d,%d)" % k, v) for k, v in want),
                            "不符": bad}


def c_g0_2_majority(ctx, state):
    """G0-2.2：多数规则（`nT*2 > m`，平票 False，零格进分母）。"""
    DLA = state["DLA"]
    DC = state["DC"]

    def cell(d):
        return {"tid": "T", "inject_scope": "k", "inject_n_sites": 10,
                "p9_lo_meas": 0.10, "p9_hi_meas": 0.10 + d, "up_mono_meas": d > 0}

    cases = [
        ("(+,+,-)", [0.3, 0.2, -0.1], True),
        ("(+,-,-)", [0.3, -0.2, -0.1], False),
        ("(+,+,0)", [0.3, 0.2, 0.0], True),
        ("(+,-,0)", [0.3, -0.2, 0.0], False),
        ("(+,-)", [0.3, -0.2], False),
    ]
    obs, bad = OrderedDict(), []
    for name, ds, exp in cases:
        cs = [cell(d) for d in ds]
        v = DLA.layer_verdicts({"T": cs}, DLA.cell_sign_p9, DLA.cell_zero_p9)["T"]
        obs[name] = {"nT": v["pos"], "nF": v["neg"], "nz": v["nz"],
                     "nzero": v["nzero"], "m": v["m"], "verdict": v["verdict"]}
        if v["verdict"] != exp:
            bad.append("%s 实测 %s 期望 %s（nT=%d nF=%d m=%d）"
                       % (name, v["verdict"], exp, v["pos"], v["neg"], v["m"]))
    # 独立实现对拍
    for name, ds, exp in cases:
        if strict_majority(ds) != exp:
            bad.append("独立实现与期望不符：%s" % name)
    return (not bad), obs, {"期望": dict((c[0], c[2]) for c in cases), "不符": bad}


def c_g0_2_unmeasured(ctx, state):
    """G0-2.3：未量到格 ⇒ 剔出格集合（该轨迹 m==2、该格不进分母）。"""
    DLA = state["DLA"]
    DC = state["DC"]
    cells = [
        {"tid": "T", "pos_frac": 0.25, "inject_scope": "k", "inject_n_sites": 100,
         "n_eff": 400, "p9_lo_meas": 0.10, "p9_hi_meas": 0.20, "up_mono_meas": True},
        {"tid": "T", "pos_frac": 0.50, "inject_scope": "k", "inject_n_sites": 200,
         "n_eff": 800, "p9_lo_meas": 0.10, "p9_hi_meas": 0.05, "up_mono_meas": False},
        {"tid": "T", "pos_frac": 0.75, "inject_scope": "k", "inject_n_sites": 300,
         "n_eff": 1200, "p9_lo_meas": None, "p9_hi_meas": 0.30, "up_mono_meas": True},
    ]
    keep = pooled_cellset(cells)
    v = DLA.layer_verdicts(by_tid(keep), DLA.cell_sign_p9, DLA.cell_zero_p9)["T"]
    # 缺读数 ⇒ `d_of` 必须 HardFail（⛔ 不许当 0）
    hard = False
    err = ""
    try:
        DC.d_of(cells[2])
    except Exception as e:
        hard = True
        err = "%s: %s" % (type(e).__name__, str(e)[:120])
    obs = {"格集合(剔出后)": len(keep), "m": v["m"], "nT": v["pos"], "nF": v["neg"],
           "verdict": v["verdict"], "d_of(缺读数格) 是否 HardFail": hard,
           "HardFail 文案": err}
    bad = []
    if len(keep) != 2:
        bad.append("剔出后格数 %d ≠ 2" % len(keep))
    if v["m"] != 2:
        bad.append("m=%d ≠ 2（未量到格仍进了分母）" % v["m"])
    if not hard:
        bad.append("d_of 对缺读数格没有 HardFail ⇒ 会被当 0")
    return (not bad), obs, {"期望": {"剔出后格数": 2, "m": 2, "d_of": "HardFail"},
                            "不符": bad}


def c_g0_2_equiv(ctx, state, ge=False):
    """G0-2.4：等价性判据 V-P5（中位数符号规则 ≡ 严格多数规则）。

    ⚙ `ge=True` ⇒ 故意把中位数实现改成 `>= 0` ⇒ 必须能红。
    """
    rng = random.Random(SEED + 4)
    triples = []
    perms = [(1, -1, 0), (1, 0, -1), (-1, 1, 0), (-1, 0, 1), (0, 1, -1), (0, -1, 1)]
    for i in range(200):
        if i < 60:
            triples.append(perms[i % len(perms)])
        else:
            while True:
                t = tuple(rng.choice((-2, -1, 0, 1, 2)) for _ in range(3))
                if any(x > 0 for x in t) and any(x < 0 for x in t):
                    triples.append(t)
                    break
    n_zero = sum(1 for t in triples if 0 in t)
    mism = []
    for i, t in enumerate(triples):
        a = median_sign(list(t), ge=ge)
        b = strict_majority(list(t))
        if a != b:
            mism.append({"i": i, "triple": list(t), "median": a, "majority": b})
    obs = {"组数": len(triples), "含零的组数": n_zero,
           "含正/负/零的组数（perm 段）": 60,
           "不一致组数": len(mism), "前 5 处不一致": mism[:5],
           "中位数实现": "median >= 0（故意破坏）" if ge else "median > 0（严格）"}
    bad = []
    if mism:
        bad.append("第 %d 处不一致：%r" % (mism[0]["i"], mism[0]))
    if n_zero == 0:
        bad.append("夹具里没有含零的组 ⇒ 判据覆盖不到零格语义")
    return (not bad), obs, {"期望": {"不一致组数": 0}, "不符": bad}


def c_g0_2_wilson(ctx, state):
    """G0-2.5：`wilson_bounds(0,10)` 与网格反演独立核对（差 ≤ 1e-4）。"""
    IA = state["IA"]
    x, n = 0, 10
    got = IA.wilson_bounds(x, n)
    grid = wilson_grid(x, n)
    dlo = abs(got[0] - grid[0])
    dhi = abs(got[1] - grid[1])
    obs = {"实现 wilson_bounds(0,10)": got, "网格反演（步长 1e-6）": grid,
           "|Δlo|": dlo, "|Δhi|": dhi, "最大差": max(dlo, dhi)}
    bad = []
    if max(dlo, dhi) > 1e-4:
        bad.append("最大差 %.3e > 1e-4" % max(dlo, dhi))
    return (not bad), obs, {"期望": {"最大差": "≤ 1e-4"}, "不符": bad}


def c_g0_2_newcombe(ctx, state):
    """G0-2.6：`newcombe_diff` 三条独立核对。"""
    IA = state["IA"]
    cases_narrow = [(400, 1000, 390, 1000), (500, 1000, 480, 1000),
                    (12, 20, 8, 20), (3, 10, 1, 10), (0, 10, 1, 10)]
    cases_wald = [(400, 1000, 390, 1000), (500, 1000, 495, 1000),
                  (1000, 2000, 980, 2000)]
    rows, bad = [], []
    for (x1, n1, x2, n2) in cases_narrow:
        nb = IA.newcombe_diff(x1, n1, x2, n2)
        nv = IA.naive_diff(x1, n1, x2, n2)
        d = x1 / float(n1) - x2 / float(n2)
        w_nb = nb[1] - nb[0]
        w_nv = nv[1] - nv[0]
        rows.append({"case": "%d/%d vs %d/%d" % (x1, n1, x2, n2),
                     "newcombe": nb, "naive": nv, "点估计差": d,
                     "宽_newcombe": w_nb, "宽_naive": w_nv})
        if not (nb[0] <= d <= nb[1]):
            bad.append("%d/%d vs %d/%d：区间不含点估计差 %g" % (x1, n1, x2, n2, d))
        if not (w_nb < w_nv):
            bad.append("%d/%d vs %d/%d：Newcombe 宽 %g 未比 naive 宽 %g 窄"
                       % (x1, n1, x2, n2, w_nb, w_nv))
    wrows, wbad = [], []
    for (x1, n1, x2, n2) in cases_wald:
        nb = IA.newcombe_diff(x1, n1, x2, n2)
        wd = wald_diff(x1, n1, x2, n2)
        dlo, dhi = abs(nb[0] - wd[0]), abs(nb[1] - wd[1])
        wrows.append({"case": "%d/%d vs %d/%d" % (x1, n1, x2, n2),
                      "newcombe": nb, "wald": wd, "|Δlo|": dlo, "|Δhi|": dhi})
        if max(dlo, dhi) > 1e-3:
            wbad.append("%d/%d vs %d/%d：与 Wald 差 %.3e > 1e-3"
                        % (x1, n1, x2, n2, max(dlo, dhi)))
    obs = {"① 含点估计差 + ② 比 naive 更窄": rows,
           "③ 大 n 比例相近 vs Wald（≤1e-3）": wrows}
    bad.extend(bad)
    bad.extend(wbad)
    return (not bad), obs, {"期望": {"①": "区间含点估计差", "②": "Newcombe 更窄",
                                     "③": "与 Wald 差 ≤ 1e-3"}, "不符": bad}


def c_g0_2_fisher(ctx, state):
    """G0-2.7：`fisher_exact_two_sided` vs 独立穷举枚举（差 ≤ 1e-12）。"""
    AV = state["AV"]
    tables = [(12, 2, 6, 8), (1, 9, 10, 0), (3, 7, 2, 8), (14, 0, 0, 14),
              (5, 15, 15, 5), (2, 8, 1, 9), (7, 7, 7, 7), (0, 14, 6, 8)]
    rows, bad = [], []
    for (a, b, c, d) in tables:
        got = AV.fisher_exact_two_sided(a, b, c, d)
        p_impl = got[0] if isinstance(got, tuple) else got
        p_ind = fisher_enum_exact(a, b, c, d)
        diff = abs(p_impl - p_ind)
        exp_min = sum(1 for (x, y, z, w) in tables
                      if sum([x, y, z, w]) == sum([a, b, c, d]) and x * w < 5)
        rows.append({"表": [[a, b], [c, d]], "实现 p": p_impl, "独立枚举 p": p_ind,
                     "差": diff, "期望频数<5 的格数": exp_min})
        if diff > 1e-12:
            bad.append("[[%d,%d],[%d,%d]] 差 %.3e > 1e-12" % (a, b, c, d, diff))
    obs = {"逐表": rows, "表数": len(tables)}
    return (not bad), obs, {"期望": {"每表差": "≤ 1e-12"}, "不符": bad}


def c_g0_2_blocks(ctx, state):
    """G0-2.8：块级（28 块）⇒ `block_majority` 与 `block_sign_test_p` 的分母 = **块数**。"""
    CPA = state["CPA"]
    blocks, signs = [], {}
    for pi in range(28):
        t_th = "aime__aime25__p%02d__think" % pi
        t_nt = "aime__aime25__p%02d__no_think" % pi
        blocks.append([t_th, t_nt])
        if pi < 20:
            signs[t_th], signs[t_nt] = 1.0, 1.0
        elif pi < 24:
            signs[t_th], signs[t_nt] = 1.0, -1.0
        else:
            signs[t_th], signs[t_nt] = -1.0, -1.0
    k, nb = CPA.block_majority(blocks, signs)
    bs = CPA.block_signs(blocks, signs)
    p_block = CPA.block_sign_test_p(blocks, signs)
    traj_vec = []
    for blk in blocks:
        for t in blk:
            traj_vec.append(signs[t])
    reader = state["READER"]
    p_traj = reader.sign_test(traj_vec)[0]
    p_analytic = analytic_sign_test_p(k, nb)
    obs = {"块数": nb, "正块数": k, "块级符号向量长度": len(bs),
           "block_sign_test_p": p_block,
           "独立闭式（n=%d 块，k=%d）" % (nb, k): p_analytic,
           "轨迹级 sign_test（n=%d 轨迹）" % len(traj_vec): p_traj,
           "块级 p 的理论下界 2/2^n": reader.sign_test(bs)[4]}
    bad = []
    if nb != 28:
        bad.append("块数 %d ≠ 28" % nb)
    if k != 20:
        bad.append("正块数 %d ≠ 20" % k)
    if abs(p_block - p_analytic) > 1e-12:
        bad.append("块级 p %g 与独立闭式 %g 差 > 1e-12" % (p_block, p_analytic))
    if abs(p_block - p_traj) < 1e-15:
        bad.append("块级 p 与轨迹级 p 相同 ⇒ 分母可能用了轨迹数（56）")
    return (not bad), obs, {"期望": {"块数": 28, "正块数": 20,
                                     "块级 p": "= 独立闭式(n=28 块)",
                                     "块级 p vs 轨迹级 p": "必须不同（分母是块数）"},
                            "不符": bad}


def c_g0_2_fixture(ctx, state):
    """G0-2.9：夹具上的 K5 格集合 + 独立多数计数 vs `layer_verdicts`。"""
    DLA = state["DLA"]
    DC = state["DC"]
    fx = state["fixture"]
    out, bad = OrderedDict(), []
    for arm in ("w", "rand"):
        keep = pooled_cellset(fx[arm])
        bt = by_tid(keep)
        v = DLA.layer_verdicts(bt, DLA.cell_sign_p9, DLA.cell_zero_p9)
        indep = {}
        for tid, cs in bt.items():
            ds = [DC.d_of(c) for c in cs]
            indep[tid] = strict_majority(ds)
        impl = dict((t, x["verdict"]) for t, x in v.items())
        disagree = [t for t in indep if indep[t] != impl.get(t)]
        npos = sum(1 for t in indep if indep[t])
        out[arm] = {"夹具格数": len(fx[arm]), "K5 格集合": len(keep),
                    "轨迹数": len(bt), "正轨迹数（独立）": npos,
                    "layer_verdicts 正轨迹数": sum(1 for x in v.values() if x["verdict"]),
                    "与独立实现不一致的轨迹": disagree[:3]}
        if disagree:
            bad.append("%s 臂：%d 条轨迹上 layer_verdicts 与独立多数计数不一致"
                       % (arm, len(disagree)))
        if len(fx[arm]) != 168:
            bad.append("%s 臂夹具格数 %d ≠ 168（56 tid × 3 pos_frac）" % (arm, len(fx[arm])))
    return (not bad), out, {"期望": {"每臂夹具格数": 168,
                                     "layer_verdicts == 独立多数计数": True},
                            "不符": bad}


def run_g0_2(ctx, state):
    G = Gate("G0-2", "统计核心夹具自检（已知答案）")
    G.say("=" * 78)
    G.say("【G0-2】统计核心夹具自检（合成数据 ｜ 已知答案）")
    G.say("  ⚖ 夹具：56 tid × 3 pos_frac × 2 臂 = 336 格 ｜ seed=%d" % SEED)
    G.say("  ⚖ 期望值全部是**独立字面量 / 独立实现**（⛔ 不从被检对象派生）")
    G.say("=" * 78)

    fx = build_fixture()
    state["fixture"] = fx
    specs = [
        ("G0-2.1", "层内零假设基准 `majority_base_p2` 的五个已知答案", c_g0_2_base),
        ("G0-2.2", "多数规则（`nT*2 > m`、平票 False、零格进分母）五个已知案例",
         c_g0_2_majority),
        ("G0-2.3", "未量到格 ⇒ 剔出格集合（m==2、该格不进分母、`d_of` 拒读）",
         c_g0_2_unmeasured),
        ("G0-2.4", "等价性判据 V-P5：中位数符号规则 ≡ 严格多数规则（200 组）",
         c_g0_2_equiv),
        ("G0-2.5", "`wilson_bounds(0,10)` 与**网格反演**独立核对（≤1e-4）",
         c_g0_2_wilson),
        ("G0-2.6", "`newcombe_diff` 三条独立核对（含点估计 / 比 naive 窄 / vs Wald）",
         c_g0_2_newcombe),
        ("G0-2.7", "`fisher_exact_two_sided` vs 独立穷举枚举（≤1e-12）",
         c_g0_2_fisher),
        ("G0-2.8", "块级：28 块 ⇒ `block_majority` 与 `block_sign_test_p` 分母 = 块数",
         c_g0_2_blocks),
        ("G0-2.9", "夹具上的 K5 格集合 + 独立多数计数 vs `layer_verdicts`",
         c_g0_2_fixture),
    ]
    for cid, name, fn in specs:
        try:
            ok, obs, det = fn(ctx, state)
        except Exception as e:
            ok, obs, det = False, {"异常": "%s: %s" % (type(e).__name__, e)}, {}
        G.ck(cid, name, ok, obs, det.get("期望"), det.get("不符"))

    G.say("")
    G.say("G0-2 小计：%d 条判据，PASS %d，FAIL %d ⇒ %s"
          % (len(G.checks), G.n_pass, G.n_fail, G.status))
    return G


# ================================================================== G0-3
def c_g0_3_ledger(ctx, state):
    """G0-3：旧批交叉对照（全部格 12/14、6/14；scope=k 10/14）。"""
    DLA = state["DLA"]
    DC = state["DC"]
    A = DLA.build_all()
    panel = dict((arm, tuple(A["arm"][arm]["panel"])) for arm in ("w", "rand"))
    scope_k = dict((arm, tuple(A["arm"][arm]["scope_k"])) for arm in ("w", "rand"))
    obs = {"全部格 panel": panel, "scope=k": scope_k,
           "模块常量 LEDGER_COUNT": dict(DC.LEDGER_COUNT),
           "模块常量 N_TRAJ": DC.N_TRAJ}
    bad = []
    for arm, want in REG_PANEL.items():
        if panel[arm] != want:
            bad.append("全部格 %s 实测 %d/%d 期望 %d/%d"
                       % (arm, panel[arm][0], panel[arm][1], want[0], want[1]))
    if scope_k["w"] != REG_SCOPE_K_W:
        bad.append("scope=k w 实测 %d/%d 期望 %d/%d"
                   % (scope_k["w"][0], scope_k["w"][1], REG_SCOPE_K_W[0], REG_SCOPE_K_W[1]))
    return (not bad), obs, {"期望": {"全部格": dict((k, "%d/%d" % v) for k, v in REG_PANEL.items()),
                                     "scope=k w": "%d/%d" % REG_SCOPE_K_W}, "不符": bad}


def c_g0_3_census(ctx, state):
    """G0-3.4：照 `verdict_panel_audit.py` 原样调用 `ledger_cell_census` 那套。"""
    VPA = state["VPA"]
    C = VPA.census()
    cells, extra = C.recompute()
    R, L = C.run_census(cells, extra["table"])
    failed = [k for k, v in R.items() if not v]
    obs = {"重算格数": len(cells), "普查判据": dict(R), "红了的判据": failed}
    return (not failed), obs, {"期望": "C1/C2/C3 全绿",
                               "不符": ["普查判据红：%s" % failed] if failed else []}


def run_g0_3(ctx, state):
    G = Gate("G0-3", "旧批交叉对照（能红锚点）")
    G.say("=" * 78)
    G.say("【G0-3】旧批交叉对照（⛔ 期望值是**独立字面量**，⛔ 不从被检对象派生）")
    G.say("  ⚖ 全部格：w 12/14、rand 6/14 ｜ scope=k：w 10/14")
    G.say("=" * 78)
    for cid, name, fn in (("G0-3.1/2/3", "旧批交叉对照：全部格 w 12/14、rand 6/14；scope=k w 10/14",
                           c_g0_3_ledger),
                          ("G0-3.4", "照 `verdict_panel_audit` 原样调用 `ledger_cell_census` 重算",
                           c_g0_3_census)):
        try:
            ok, obs, det = fn(ctx, state)
        except Exception as e:
            import traceback
            ok = False
            obs = {"异常": "%s: %s" % (type(e).__name__, e)}
            det = {"期望": "跑得出来", "不符": ["异常：%s" % traceback.format_exc()[-1200:]]}
        G.ck(cid, name, ok, obs, det.get("期望"), det.get("不符"))
    G.say("")
    G.say("G0-3 小计：%d 条判据，PASS %d，FAIL %d ⇒ %s"
          % (len(G.checks), G.n_pass, G.n_fail, G.status))
    return G


# ================================================================== 变异台（红化反例）
def _restore_shard(ctx, state, pristine):
    if state.get("shard"):
        with open(state["shard"], "wb") as fh:
            fh.write(pristine)


def run_selftest(ctx, state):
    G = Gate("SELFTEST", "红化反例（每条反例必须让对应判据变红）")
    G.say("=" * 78)
    G.say("【SELFTEST】红化反例注入 ⇒ 对应判据必须**变红**")
    G.say("  ⚖ 等价变异（结论恰好不变）记「无效」且**不计入分母**")
    G.say("=" * 78)
    muts = []

    def rec(mid, gate, target, desc, expect_fail, got_fail, detail, effective=None):
        if effective is None:
            effective = bool(got_fail)
        muts.append({"id": mid, "gate": gate, "target_check": target,
                     "mutation": desc, "expect": "FAIL" if expect_fail else "PASS",
                     "observed": "FAIL" if got_fail else "PASS",
                     "effective": effective, "detail": detail})
        G.ck(mid, "反例：%s ⇒ %s 必须变红" % (desc, target),
            bool(got_fail) == bool(expect_fail),
            {"实测": "FAIL（判据红了）" if got_fail else "PASS（判据没红）",
             "有效性": "有效（计入分母）" if effective else "无效（等价变异，不计入分母）"},
            {"期望": "FAIL（判据红了）"},
            detail + ("" if effective else
                      "\n        ⚠ 记「**无效**」（等价变异：结论恰好不变）⇒ **不计入分母**"))

    # ---------------- G0-1 反例 ----------------
    if state.get("shard"):
        pristine = read_bytes(state["shard"])
        # M1：篡改分片里第一格的 n_eff ⇒ 逐字节对照必须红
        txt = pristine.decode("utf-8", "replace")
        m = re.search(r"n_eff=(\d+)", txt)
        if m:
            old = m.group(1)
            new = str(int(old) + 1)
            with open(state["shard"], "w", encoding="utf-8") as fh:
                fh.write(txt.replace("n_eff=%s" % old, "n_eff=%s" % new, 1))
            ok, obs, detail = c_g0_1_bytes(ctx, state)
            _restore_shard(ctx, state, pristine)
            rec("M1", "G0-1", "G0-1.3",
                "把拆出分片第 1 格的 n_eff 从 %s 改成 %s" % (old, new),
                True, (not ok),
                "篡改后逐字节对照实测：%s\n%s"
                % ("不再逐字节相同 ⇒ 判据变红 ✅" if not ok else "仍相同 ⛔ 判据恒绿",
                   "\n".join(detail[:6])))
        # M2：删掉拆出 status 的一行 ⇒ 读数器必须 HardFail ⇒ 对账判据必须红
        if state.get("shard_status") and os.path.isfile(state["shard_status"]):
            sp = state["shard_status"]
            sdata = read_bytes(sp)
            slines = split_lines_keepends(sdata)
            if len(slines) > 2:
                with open(sp, "wb") as fh:
                    fh.write(b"".join(slines[1:]))
                ok, obs, detail, _bk = c_g0_1_reader(ctx, state)
                with open(sp, "wb") as fh:
                    fh.write(sdata)
                rec("M2", "G0-1", "G0-1.4",
                    "删掉拆出 status 的第 1 行（137→136 行）",
                    True, (not ok),
                    "删行后实测：原 rc=%s ｜ 拆 rc=%s ｜ 格数 %s / %s ⇒ %s"
                    % (obs.get("原 rc"), obs.get("拆 rc"),
                       obs.get("原 格数/有读数"), obs.get("拆 格数/有读数"),
                       "拆那份被拒读 ⇒ 对账判据变红 ✅" if not ok else "仍通过 ⛔ 判据恒绿"))
    else:
        G.say("  ⚠ 没有分片 ⇒ G0-1 的红化反例（M1/M2）跳过")

    # ---------------- G0-2 反例 ----------------
    DLA = state["DLA"]
    DC = state["DC"]
    AV = state["AV"]

    # M3：多数规则改成 `>=` ⇒ G0-2.2 必须红
    orig_layer = DLA.layer_verdicts

    def layer_ge(cells_by_tid, sign_fn, zero_fn=None):
        out = {}
        for tid, cs in cells_by_tid.items():
            nT = sum(1 for c in cs if sign_fn(c))
            nF = sum(1 for c in cs if not sign_fn(c))
            out[tid] = {"pos": nT, "neg": nF, "nz": len(cs), "nzero": 0,
                        "m": len(cs), "verdict": nT >= nF}
        return out
    patch_all("dose_layer_audit.py", "layer_verdicts", layer_ge)
    try:
        ok, obs, det = c_g0_2_majority(ctx, state)
    finally:
        patch_all("dose_layer_audit.py", "layer_verdicts", orig_layer)
    rec("M3", "G0-2", "G0-2.2", "把多数规则从 `nT*2 > m` 改成 `nT >= nF`",
        True, (not ok),
        "变异后实测 verdict：%s\n不符：%s"
        % (dict((k, v["verdict"]) for k, v in obs.items()), det.get("不符")))

    # M4：基准硬写 0.5 ⇒ G0-2.1 必须红
    orig_base = DLA.majority_base_p2
    patch_all("dose_layer_audit.py", "majority_base_p2", lambda n_nz, n_zero=0: 0.5)
    try:
        ok, obs, det = c_g0_2_base(ctx, state)
    finally:
        patch_all("dose_layer_audit.py", "majority_base_p2", orig_base)
    rec("M4", "G0-2", "G0-2.1", "把零假设基准硬写成 0.5（⛔ 不许硬写）",
        True, (not ok),
        "变异后实测：%s\n不符：%s" % (obs, det.get("不符")))

    # M5：Fisher 换成正态近似 ⇒ G0-2.7 必须红
    orig_fisher = AV.fisher_exact_two_sided
    patch_all("arm_verdict.py", "fisher_exact_two_sided", fisher_normal_approx)
    try:
        ok, obs, det = c_g0_2_fisher(ctx, state)
    finally:
        patch_all("arm_verdict.py", "fisher_exact_two_sided", orig_fisher)
    rec("M5", "G0-2", "G0-2.7", "把精确 Fisher 换成正态近似",
        True, (not ok),
        "变异后逐表差：%s\n不符：%s"
        % ([{"表": r["表"], "差": r["差"]} for r in obs.get("逐表", [])],
           det.get("不符")))

    # M6：中位数实现改成 `>= 0` ⇒ G0-2.4 必须红
    ok, obs, det = c_g0_2_equiv(ctx, state, ge=True)
    rec("M6", "G0-2", "G0-2.4", "把中位数符号实现改成 `>= 0`（故意破坏等价性）",
        True, (not ok),
        "变异后实测：%s\n不符：%s" % (obs, det.get("不符")))

    # M7：多数规则 `>=` 打到 G0-3 ⇒ 12/14、6/14、10/14 必须红
    orig_mc = DC.majority_count

    def mc_ge(recs):
        g = {}
        for r in recs:
            g.setdefault(r.get("tid"), []).append(DC.d_of(r) > 0)
        return sum(1 for v in g.values() if sum(v) * 2 >= len(v)), len(g)
    patch_all("dose_confound_audit.py", "majority_count", mc_ge)
    try:
        ok, obs, det = c_g0_3_ledger(ctx, state)
    finally:
        patch_all("dose_confound_audit.py", "majority_count", orig_mc)
    rec("M7", "G0-3", "G0-3.1/2/3", "把多数规则改成 `>=`（打旧批交叉对照）",
        True, (not ok),
        "变异后实测：%s\n不符：%s" % (obs, det.get("不符")))

    # M8：`d_of` 换成 `|d|` ⇒ 结论可能不变 ⇒ 记「无效」且不计入分母
    orig_dof = DC.d_of

    def d_abs(rec):
        lo, hi = rec.get("p9_lo_meas"), rec.get("p9_hi_meas")
        if lo is None or hi is None:
            raise DC.HardFail("记录 %r 缺 p9_lo_meas/p9_hi_meas ⇒ **未量到**" % (rec.get("tid"),))
        return abs(float(hi) - float(lo))
    patch_all("dose_confound_audit.py", "d_of", d_abs)
    try:
        ok, obs, det = c_g0_3_ledger(ctx, state)
    finally:
        patch_all("dose_confound_audit.py", "d_of", orig_dof)
    effective = (not ok)
    rec("M8", "G0-3", "G0-3.1/2/3", "把 `d_of` 换成 `|d|`（等价变异探针）",
         True, (not ok),
         "变异后实测：%s\n不符：%s\n⇒ %s"
         % (obs, det.get("不符"),
            "结论变了 ⇒ **有效**反例（计入分母）" if effective
            else "结论恰好不变 ⇒ **无效**等价变异 ⇒ **不计入分母**"),
         effective=effective)

    G.say("")
    n_eff = sum(1 for m in muts if m["effective"])
    n_inv = len(muts) - n_eff
    G.say("SELFTEST 小计：%d 条反例，其中**有效** %d 条（计入分母）、"
          "**无效（等价变异）** %d 条（不计入分母）" % (len(muts), n_eff, n_inv))
    G.mutations = muts
    return G


# ================================================================== 主流程
def force_load_all(ctx):
    mods = {}
    for f in ("dose_confound_audit.py", "dose_layer_audit.py", "interval_audit.py",
              "arm_verdict.py", "cluster_premise_audit.py", "ledger_cell_census.py",
              "verdict_panel_audit.py", "verdict_source_audit.py", "layer_row_audit.py"):
        p = ctx.r(f)
        if os.path.isfile(p):
            mods[f] = load_mod(p, "gate_" + f[:-3])
    state = {}
    state["DC"] = mods["dose_confound_audit.py"]
    state["DLA"] = mods["dose_layer_audit.py"]
    state["IA"] = mods["interval_audit.py"]
    state["AV"] = mods["arm_verdict.py"]
    state["CPA"] = mods["cluster_premise_audit.py"]
    state["VPA"] = mods["verdict_panel_audit.py"]
    state["READER"] = load_mod(os.path.join(ctx.mutbak, "r227_kcurve.py"), "gate_reader")
    # 让面板链条自己的子模块也全部实例化（⇒ 变异能打到所有别名）
    state["VPA"].census()
    state["VPA"].dla()
    state["VPA"].dca()
    state["VPA"].cpa()
    state["VPA"].iaud()
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default="all",
                    choices=["all", "g0_1", "g0_2", "g0_3"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--outdir", default="/dev/shm/_phase0_24479")
    ap.add_argument("--tree", default="/dev/shm/_phase0_24479/tree")
    ap.add_argument("--dev", default="/home/zhourui/steer3d/.cache/r244")
    ap.add_argument("--bpath", default="/home/zhourui/steer3d_bpath")
    a = ap.parse_args()

    ctx = Ctx(a)
    os.makedirs(ctx.outdir, exist_ok=True)
    state = {}

    # ---- 前置 ----
    pre = []
    for p in (ctx.reader, ctx.splitter, ctx.orig_log, ctx.orig_status, ctx.old_cells):
        if not os.path.isfile(p):
            pre.append("缺文件：%s" % p)
    if not os.path.isdir(ctx.r244):
        pre.append("缺暂存树：%s（⛔ 先跑驱动脚本搭树）" % ctx.r244)
    if pre:
        sys.stderr.write("PRECOND_FAIL:\n  " + "\n  ".join(pre) + "\n")
        return 2

    t0 = time.time()
    gates = OrderedDict()
    try:
        state.update(force_load_all(ctx))
    except Exception as e:
        import traceback
        sys.stderr.write("PRECOND_FAIL: 暂存树的模块装载不过：%s\n%s\n"
                         % (e, traceback.format_exc()[-2000:]))
        return 2

    if a.gate in ("all", "g0_1"):
        g = run_g0_1(ctx, state)
        gates["G0-1"] = g
        _write(os.path.join(ctx.outdir, "g0_1.out"), g.lines)
    if a.gate in ("all", "g0_2"):
        g = run_g0_2(ctx, state)
        gates["G0-2"] = g
        _write(os.path.join(ctx.outdir, "g0_2.out"), g.lines)
    if a.gate in ("all", "g0_3"):
        g = run_g0_3(ctx, state)
        gates["G0-3"] = g
        _write(os.path.join(ctx.outdir, "g0_3.out"), g.lines)
    if a.selftest:
        g = run_selftest(ctx, state)
        gates["SELFTEST"] = g
        _write(os.path.join(ctx.outdir, "selftest.out"), g.lines)

    # ---- summary.json ----
    n_checks = sum(len(g.checks) for g in gates.values())
    n_pass = sum(g.n_pass for g in gates.values())
    n_fail = sum(g.n_fail for g in gates.values())
    muts = []
    for g in gates.values():
        muts.extend(getattr(g, "mutations", []))
    n_eff = sum(1 for m in muts if m["effective"])
    n_inv = len(muts) - n_eff
    verdict = "PASS" if (n_fail == 0 and all(m["observed"] == m["expect"] for m in muts)) else "FAIL"
    summary = {
        "task": "244.79", "phase": "0",
        "title": "固定剂量合池判决层 Phase-0 可行性闸门",
        "host": os.uname().nodename, "python": sys.version.split()[0],
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": SEED,
        "elapsed_sec": round(time.time() - t0, 1),
        "paths": {"outdir": ctx.outdir, "tree": ctx.tree, "dev": ctx.dev,
                  "bpath": ctx.bpath},
        "input_md5": dict((n, md5_file(os.path.join(ctx.bpath, n)))
                          for n in sorted(EXPECT_MD5)),
        "reader_md5": md5_file(ctx.reader),
        "splitter_md5": md5_file(ctx.splitter),
        "gates": OrderedDict(
            (gid, {"title": g.title, "status": g.status,
                   "n_checks": len(g.checks), "n_pass": g.n_pass, "n_fail": g.n_fail,
                   "n_defects": len(getattr(g, "defects", [])),
                   "checks": g.checks,
                   "defects": getattr(g, "defects", [])})
            for gid, g in gates.items()),
        "mutations": muts,
        "totals": {"checks": n_checks, "passed": n_pass, "failed": n_fail,
                   "mutations": len(muts), "effective_mutations": n_eff,
                   "invalid_mutations": n_inv},
        "verdict": verdict,
    }
    _write_json(os.path.join(ctx.outdir, "summary.json"), summary)

    print("=" * 78)
    for gid, g in gates.items():
        print("[%s] %-9s %d 条判据 ｜ PASS %d ｜ FAIL %d%s"
              % (g.status, gid, len(g.checks), g.n_pass, g.n_fail,
                 (" ｜ 缺陷登记 %d 条" % len(getattr(g, "defects", [])))
                 if getattr(g, "defects", []) else ""))
    print("总计：%d 条判据 ｜ PASS %d ｜ FAIL %d ｜ 反例 %d（有效 %d / 无效 %d）"
          % (n_checks, n_pass, n_fail, len(muts), n_eff, n_inv))
    for gid, g in gates.items():
        for d in getattr(g, "defects", []):
            print("⚠ 缺陷登记[%s] %s：%s" % (d["id"], d["name"],
                                              "OK" if d["ok"] else "见收据"))
    print("Phase-0 判决：%s" % verdict)
    print("收据目录：%s" % ctx.outdir)
    print("=" * 78)
    return 0 if verdict == "PASS" else 1


def _write(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _write_json(path, obj):
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False))
        fh.write("\n")


if __name__ == "__main__":
    sys.exit(main())
