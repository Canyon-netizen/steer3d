#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""p_identity_audit.py —— 探针的 `P` 到底等不等于 `len(pid)`（零 GPU）

🔴🔴🔴 **本工具问什么**

  244.50 把分母更正成 `inj = P + floor(n_gen x pos_frac) - 1` 之后，
  自己登记了一条**没验的前提**：

      「`P == len(pid)`」—— ⛔ 当时**没验**。

  为什么它重要：探针的截断语句是
      `ids = torch.tensor([(pid + gen)[: P + t]])`
  ⇒ 只有在 `P == len(pid)` 时，`P + t` 才等于「prompt 长度 + 注入长度」；
  否则离线复算的 `inj` 与探针实际用的 `inj` 不是同一个数，
  ⇒ 244.50 的分位点 / 分档 / rho 全部要重新算。

⚖⚖⚖ **本工具的结论（先给）**

  · ✅ **源码层是恒等式**（不是巧合，也不是「两边都读同一个数」的巧合）：
    探针的 `len(pid)`、`recomp_p.py` 的 `recomp`、`precompute_n_eff.py` 的 `P`
    三者**逐字同形**（同一个 MODEL 字面量、同一个 `chat_template_input` 字段、
    同一个 `add_special_tokens=False`）⇒ 取自同一份输入时**必然相等**。
    ⛔ 恒等式**不需要实测**，但必须**逐条验到字面量**才算数。
  · ✅ **数据层**：本批 14 个 tid 的**记录 P**（探针产出）== 权威 map 的 **P**
    （`precompute_n_eff.py` 独立重算产出）**14/14 逐条相等**。
  · ✅ **截断不触发**：`t <= n` 对 60 行**逐行实测**成立
    （跑批日志 PINNED 行钉死 `POS_FRAC=0.5`）⇒ `P + t <= len(pid) + n`。
  · ⚠ **残留前提必须印成「未量到」**（见输出末尾 R1/R2/R3）——
    **同一路径 ≠ 同一内容**，本地量不到。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不连远端、⛔ 不写/删任何文件。
⚖⚠⚖⚖ 每条判据都必须**能红**：变异台改的是**判据本身**或**喂进去的夹具**。
"""

import argparse
import ast
import hashlib
import io
import json
import os
import re
import sys
from glob import glob

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# ⚖ 三个**生产者**的源码：三方必须同形，这是「P == len(pid)」的恒等式基础
PROBE_SRC = os.path.join(REPO, ".cache/mutbak/r204_noise_probe.py")
RECOMP_SRC = os.path.join(HERE, "recomp_p.py")
PRE_SRC = os.path.join(HERE, "precompute_n_eff.py")
# ⚖ 244.45 打过 force 补丁前的探针快照 ⇒ 用来证明补丁没碰分母那几行
PROBE_SNAP = os.path.join(HERE, "probe_prepatch_snapshot.py")

MAP_GLOB = os.path.join(HERE, "n_eff_map*.tsv")
RESULT_FILES = {"w": os.path.join(HERE, "_an.txt"),
                "rand": os.path.join(HERE, "_ra.txt")}
LOG_GLOB = os.path.join(HERE, "r244_warm_*.log")
LAUNCH_LOG = os.path.join(HERE, "r244_run274_launch.log")

# ⚖ 账本 244.7.2 记的**复算**分布 —— 本工具必须**逐项复现**它
LEDGER_P_DIST = {"n": 60, "min": 108, "max": 914, "mean": 256.033, "uniq": 56}
# ⚖ 账本 244.7.2 记的实测结论：侧车自报 vs 独立重算 **60/60 逐位相等**
LEDGER_SIDECAR_VS_RECOMP = {"n": 60, "match": 60, "mismatch": 0}
# ⚖ 跑批日志 PINNED 行里的 POS_FRAC（本批的实测值）
LEDGER_POS_FRAC = 0.5

STAMP_RE = re.compile(r"NMAP rows=(\d+) md5=([0-9a-f]{32})")
LAUNCH_RE = re.compile(r"nmap_md5=([0-9a-f]{32})")
PINNED_RE = re.compile(r"POS_FRAC=([0-9.]+)")


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 小工具
def md5_of(path):
    return hashlib.md5(io.open(path, "rb").read()).hexdigest()


def read_map(path):
    rows = [l.split("\t") for l in io.open(path, encoding="utf-8").read().split("\n")
            if l.strip()]
    if not rows:
        raise HardFail("map %s 是空的 ⇒ ⛔ 拒读" % path)
    return rows[0], rows[1:]


def read_result(path):
    """⚖ 读结果文件：头部的戳行与 JSON 行都要拿到。"""
    stamp, recs = None, []
    for line in io.open(path, encoding="utf-8", errors="replace"):
        t = line.strip()
        if t.startswith("NMAP "):
            m = STAMP_RE.search(t)
            if m:
                stamp = (int(m.group(1)), m.group(2))
            continue
        if not t.startswith("{"):
            continue
        try:
            recs.append(json.loads(t))
        except Exception:
            raise HardFail("结果文件 %s 有坏 JSON 行 ⇒ ⛔ 拒读" % path)
    if not recs:
        raise HardFail("结果文件 %s 一条记录都没有 ⇒ ⛔ 拒读" % path)
    return stamp, recs


def p_dist(body, i_p):
    Ps = sorted(int(r[i_p]) for r in body)
    return {"n": len(Ps), "min": min(Ps), "max": max(Ps),
            "mean": round(sum(Ps) / float(len(Ps)), 3), "uniq": len(set(Ps))}


# --------------------------------------------------------------- AST 小工具
def parse_src(path):
    src = io.open(path, encoding="utf-8").read()
    return ast.parse(src), src


def assigns_in(scope, name):
    """⚖ 取**某个作用域内**赋给 `name` 的值表达式。

    ⚠⚠⚠ **必须按作用域取**，⛔ 不能全树扫完取最后一个 ——
      真探针里 `n` 有两个赋值：
        `:253  n = alphas.size`      （在 `analyze` 里）
        `:407  n = len(gen)`         （在 `run_cell` 里）  ← 这才是分母用的那个
      本轮第一版全树扫取最后一个 ⇒ 拿到 `alphas.size` ⇒ 判据报「n 不是 len(gen)」
      ⇒ **工具自己写错、报了个自信的错话**。

    ⚖ 嵌套的 function/class **不进**（它们是别的作用域）。"""
    out = []

    def visit(stmts):
        for st in stmts:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(st, ast.Assign):
                for t in st.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        out.append(st.value)
            elif isinstance(st, ast.AnnAssign):
                if isinstance(st.target, ast.Name) and st.target.id == name:
                    out.append(st.value)
            for field in ("body", "orelse", "finalbody", "handlers"):
                sub = getattr(st, field, None)
                if sub:
                    visit(sub)

    visit(scope.body)
    return out


def scope_of(tree, node):
    """⚖ 找到包含 `node` 的**最内层**函数；没有则在模块里。"""
    best = None
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(sub is node for sub in ast.walk(fn)):
            continue
        span = (getattr(fn, "end_lineno", None) or fn.lineno) - fn.lineno
        if best is None or span < best[0]:
            best = (span, fn)
    return best[1] if best else tree


def unparse(node):
    """⚖⚖⚖ 一律用 `ast.unparse`，⛔ 不用 `get_source_segment`
    （py3.9 的 `ast.comprehension` 没有位置信息 ⇒ 那里返回 `None`
      ⇒ 文本选择器**静默失配** ⇒ 曾报出「探针形状已变」这种**自信的错话**）。"""
    return ast.unparse(node)


def const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def model_literal(tree):
    """⚖ 取模块级 `MODEL = "..."` 的字面量。"""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "MODEL":
                    return const_str(node.value)
    return None


def calls(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def tokenizer_load(tree):
    """⚖ 找 `AutoTokenizer.from_pretrained(<arg>)` ⇒ 返回 <arg> 的文本。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if (isinstance(f, ast.Attribute) and f.attr == "from_pretrained"
                and isinstance(f.value, ast.Name) and f.value.id == "AutoTokenizer"):
            return [unparse(a) for a in node.args]
    return None


def tok_call_node(tree):
    """⚖ 找 `tok(...)` 调用**节点**（要拿它的作用域，⛔ 不能只拿文本）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "tok":
            return node
    return None


def tok_call(tree):
    """⚖ 找 `tok(...)` 调用 ⇒ 返回 (flag 文本 or None, 第一个实参文本)。"""
    c = tok_call_node(tree)
    if c is None:
        return None, None
    flag = None
    for kw in c.keywords:
        if kw.arg == "add_special_tokens":
            flag = unparse(kw.value)
    first = unparse(c.args[0]) if c.args else ""
    return flag, first


def field_from_tokenize(value):
    """⚖ 探针那一支：`tok(cti["chat_template_input"], …)` ⇒ 字段名 = 下标的常量。"""
    for c in calls(value):
        if isinstance(c.func, ast.Name) and c.func.id == "tok" and c.args:
            a0 = c.args[0]
            if isinstance(a0, ast.Subscript):
                return const_str(a0.slice)
    return None


def field_from_cti_assign(value):
    """⚖ 另两支：`cti = j.get("chat_template_input")` ⇒ 字段名 = get() 的常量实参。"""
    for c in calls(value):
        if isinstance(c.func, ast.Attribute) and c.func.attr == "get" and c.args:
            s = const_str(c.args[0])
            if s:
                return s
    return None


def pos_frac_guards(tree):
    """⚖ 数一数**比较** `pos_frac` 的 Compare 节点 ⇒ 上界守卫的个数。

    ⚖ 判据：探针**没有**上界守卫（`--pos-frac` 只有 `type=float, default=0.5`），
      而 map 生产者 `precompute_n_eff.py` **有**（`0.0 < pos_frac <= 1.0`）。
      ⇒ 「截断不触发」这条**靠跑批日志钉死的 POS_FRAC**，
        ⛔ 不能靠「代码保证了 pos_frac ≤ 1」来说。"""
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        txt = unparse(node)
        if "pos_frac" in txt:
            n += 1
    return n


# --------------------------------------------------------------- 判据
def audit(probe_src=PROBE_SRC, recomp_src=RECOMP_SRC, pre_src=PRE_SRC,
          probe_snap=PROBE_SNAP, map_glob=MAP_GLOB, results=None, logs=None,
          launch=None):
    results = results or RESULT_FILES
    L = ["【P 恒等性审计：探针的 P == len(pid) 吗】"]
    R = {}

    def mark(cid, ok, line):
        R[cid] = bool(ok)
        L.append("  %-4s %s" % (cid, line))

    # ================= 源码层：恒等式（⛔ 不需要实测，但要验到字面量）=====
    trees = {}
    for tag, p in (("probe", probe_src), ("recomp", recomp_src), ("pre", pre_src)):
        if not os.path.exists(p):
            mark("S0", False, "⛔ 源文件不存在：%s（%s）" % (p, tag))
            return L, 1, R
        trees[tag] = parse_src(p)[0]
    L.append("  ── 源码层（恒等式：⛔ 不需要实测，但必须逐条验到字面量）──")

    # ⚖ 作用域：每个文件里**含 `tok(...)` 调用**的那个函数
    #   （探针 = `run_cell`，另两处 = `main`）⇒ 下面的同名变量只在这个作用域里取
    scopes = {}
    for t, tr in trees.items():
        node = tok_call_node(tr)
        scopes[t] = scope_of(tr, node) if node is not None else tr
    L.append("  S0  作用域：%s"
             % ", ".join("%s=%s" % (t, getattr(scopes[t], "name", "<module>"))
                         for t in ("probe", "recomp", "pre")))

    models = {t: model_literal(tr) for t, tr in trees.items()}
    same_model = (len(set(models.values())) == 1 and None not in models.values())
    L.append("  S1  MODEL 字面量：")
    for t in ("probe", "recomp", "pre"):
        L.append("       %-7s %r" % (t, models[t]))
    mark("S1", same_model,
         "S1 %s 三方 MODEL **逐位相同** ⇒ 同一个 tokenizer 文件"
         % ("✅" if same_model else "⛔"))

    loads = {t: tokenizer_load(tr) for t, tr in trees.items()}
    same_load = (len({tuple(v or ()) for v in loads.values()}) == 1
                 and all(loads.values()))
    L.append("  S2  tokenizer 加载：")
    for t in ("probe", "recomp", "pre"):
        L.append("       %-7s AutoTokenizer.from_pretrained(%s)"
                 % (t, (loads[t] or ["<没找到>"])[0]))
    mark("S2", same_load,
         "S2 %s 三方都是 `AutoTokenizer.from_pretrained(MODEL)`"
         % ("✅" if same_load else "⛔"))

    flags = {t: tok_call(tr)[0] for t, tr in trees.items()}
    same_flag = (len(set(flags.values())) == 1 and None not in flags.values())
    L.append("  S3  add_special_tokens flag：")
    for t in ("probe", "recomp", "pre"):
        L.append("       %-7s %s" % (t, flags[t]))
    mark("S3", same_flag,
         "S3 %s 三方 flag **逐位相同** ⇒ `len(pid)`/`recomp`/map 的 `P` "
         "是**同一个表达式**" % ("✅" if same_flag else "⛔"))

    # ⚖ 字段名**从具体表达式**取：探针取 `tok(cti[…])` 的下标常量，
    #   另两处取 `cti = j.get(…)` 的常量实参。
    #   ⛔ 不能全树扫第一个 Subscript（真探针里 `steps["n_ran"]` 会排在前面
    #      ⇒ 本轮第一版就取到了 'n_ran' ⇒ **工具自己写错**）。
    pid_exprs = assigns_in(scopes["probe"], "pid")
    flds = {
        "probe": field_from_tokenize(pid_exprs[-1]) if pid_exprs else None,
        "recomp": None, "pre": None,
    }
    for t in ("recomp", "pre"):
        cti_exprs = assigns_in(scopes[t], "cti")
        flds[t] = field_from_cti_assign(cti_exprs[-1]) if cti_exprs else None
    same_field = (len(set(flds.values())) == 1 and None not in flds.values())
    L.append("  S4  输入字段：")
    for t in ("probe", "recomp", "pre"):
        L.append("       %-7s %r" % (t, flds[t]))
    mark("S4", same_field,
         "S4 %s 三方取**同一个字段** ⇒ 同一个输入字符串"
         % ("✅" if same_field else "⛔"))

    p_exprs = assigns_in(scopes["probe"], "P")
    p_txt = unparse(p_exprs[-1]) if p_exprs else ""
    has_sidecar = "prompt_tokens" in p_txt
    has_fallback = "len(pid)" in p_txt
    L.append("  S5  探针的 P 表达式：%s" % p_txt)
    mark("S5", bool(p_exprs) and has_sidecar and has_fallback,
         "S5 %s P 同时含「侧车自报」与「len(pid) 回退」两支"
         % ("✅" if (p_exprs and has_sidecar and has_fallback) else "⛔"))

    ids_exprs = assigns_in(scopes["probe"], "ids")
    ids_txt = unparse(ids_exprs[-1]) if ids_exprs else ""
    t_exprs = assigns_in(scopes["probe"], "t")
    t_txt = unparse(t_exprs[-1]) if t_exprs else ""
    n_exprs = assigns_in(scopes["probe"], "n")
    n_txt = unparse(n_exprs[-1]) if n_exprs else ""
    cut_ok = bool(re.search(r"\[:\s*P\s*\+\s*t\s*\]", ids_txt))
    t_ok = ("max(1, int(" in t_txt) and ("pos_frac" in t_txt)
    n_ok = (n_txt == "len(gen)")
    L.append("  S6  截断语句：%s" % ids_txt)
    L.append("       t 公式：%s ｜ n：%s" % (t_txt, n_txt))
    mark("S6", cut_ok and t_ok and n_ok,
         "S6 %s 截断形状 = `[: P + t]`，t = max(1,int(n*pos_frac))，n = len(gen)"
         % ("✅" if (cut_ok and t_ok and n_ok) else "⛔"))

    g_probe = pos_frac_guards(trees["probe"])
    g_pre = pos_frac_guards(trees["pre"])
    guard_ok = (g_probe == 0 and g_pre >= 1)
    L.append("  S7  pos_frac 上界守卫：探针 %d 处 / map 生产者 %d 处"
             % (g_probe, g_pre))
    mark("S7", guard_ok,
         "S7 %s 探针**无**上界守卫、map 生产者**有** ⇒ 「截断不触发」这条"
         "只能靠**跑批日志钉死的 POS_FRAC**，⛔ 不能靠代码保证"
         % ("✅" if guard_ok else "⛔"))

    # ⚖ 244.45 的 force 补丁不许动分母那几行
    if os.path.exists(probe_snap):
        tr_snap = parse_src(probe_snap)[0]
        snap_node = tok_call_node(tr_snap)
        snap_scope = scope_of(tr_snap, snap_node) if snap_node is not None else tr_snap
        snap_model = model_literal(tr_snap)
        snap_flags = tok_call(tr_snap)[0]
        snap_p = assigns_in(snap_scope, "P")
        snap_p_txt = unparse(snap_p[-1]) if snap_p else ""
        patch_ok = (snap_model == models["probe"] and snap_flags == flags["probe"]
                    and snap_p_txt == p_txt)
        mark("S8", patch_ok,
             "S8 %s 244.45 的 force 补丁**没动**分母那几行（MODEL/flag/P 表达式逐字相同）"
             % ("✅" if patch_ok else "⛔"))
    else:
        mark("S8", False, "S8 ⛔ 补丁前快照不存在：%s" % probe_snap)

    L.append("  ⚖ 恒等式限定：上面 S1–S4 成立 ⇒ 探针的 `len(pid)`、"
             "`recomp_p.py` 的 `recomp`、map 的 `P` 是**同一个表达式**")
    L.append("     ⇒ 取自**同一份输入**时**必然相等**（恒等式，⛔ 不需要实测）。")
    L.append("     ⚖ 但「同一份输入」这件事**不是**源码能证的 ⇒ 见数据层与 R1。")

    # ================= 数据层 ==========================================
    L.append("  ── 数据层（本批实测）──")

    # D1 戳
    stamps = {}
    for arm, p in sorted(results.items()):
        if not os.path.exists(p):
            mark("D1", False, "D1 ⛔ 结果文件不存在：%s" % p)
            return L, 1, R
        st, recs = read_result(p)
        if st:
            stamps["result:" + arm] = (st[0], st[1])
    for lp in sorted(glob(logs or LOG_GLOB)):
        for line in io.open(lp, encoding="utf-8", errors="replace"):
            if line.startswith("NMAP "):
                m = STAMP_RE.search(line)
                if m:
                    stamps["log:" + os.path.basename(lp)] = (int(m.group(1)), m.group(2))
                    break
    if launch and os.path.exists(launch):
        for line in io.open(launch, encoding="utf-8", errors="replace"):
            m = LAUNCH_RE.search(line)
            if m:
                stamps["launch"] = (60, m.group(1))
                break
    vals = set(stamps.values())
    L.append("  D1  戳来源 %d 个 → %s" % (len(stamps), sorted(vals)))
    mark("D1", len(vals) == 1 and len(stamps) >= 2,
         "D1 %s 所有来源的戳**逐位一致** ⇒ 权威 map 唯一"
         % ("✅" if (len(vals) == 1 and len(stamps) >= 2) else "⛔"))
    if not vals:
        return L, 1, R
    rows_n, want_md5 = list(vals)[0]

    # D2 按 md5 定位权威 map，并点名兄弟
    cands = sorted(glob(map_glob))
    auth = [p for p in cands if md5_of(p) == want_md5]
    for p in cands:
        m = md5_of(p)
        L.append("  D2  候选 map %-34s md5=%s %s"
                 % (os.path.basename(p), m,
                    "✅ **权威（与戳相同）**" if m == want_md5
                    else "⚠ **兄弟**：md5 与戳不同，⛔ 不是权威"))
    one_auth = (len(auth) == 1)
    mark("D2", one_auth,
         "D2 %s 恰好一份与戳相符 ⇒ 权威性唯一"
         % ("✅" if one_auth else "⛔ %d 份相符" % len(auth)))
    if not one_auth:
        return L, 1, R
    MAP = auth[0]
    hdr, body = read_map(MAP)
    L.append("       行数 %d（戳记 rows=%d）" % (len(body), rows_n))
    mark("D2b", len(body) == rows_n,
         "D2b %s 行数与戳相符" % ("✅" if len(body) == rows_n else "⛔"))

    iP = hdr.index("P")
    iS = hdr.index("n_gen_sidecar")
    iN = hdr.index("n_gen_npz")
    iT = hdr.index("t")
    iE = hdr.index("n_eff")
    M = {r[0]: r for r in body}

    # D6 POS_FRAC：来自跑批日志的 PINNED 行（⛔ 不是「记录里都是 0.5」）
    pfs = set()
    for lp in sorted(glob(logs or LOG_GLOB)):
        for line in io.open(lp, encoding="utf-8", errors="replace"):
            if line.startswith("PINNED "):
                m = PINNED_RE.search(line)
                if m:
                    pfs.add(float(m.group(1)))
                break
    L.append("  D6  跑批日志 PINNED 行的 POS_FRAC 取值：%s" % sorted(pfs))
    mark("D6", pfs == {LEDGER_POS_FRAC},
         "D6 %s 跑批日志钉死 POS_FRAC=%s（⛔ 不是从记录里反推的）"
         % ("✅" if pfs == {LEDGER_POS_FRAC} else "⛔", LEDGER_POS_FRAC))

    # D3 本批 P 逐条相等
    d3_ok, d3_detail = True, []
    batch_tids = set()
    for arm, p in sorted(results.items()):
        _st, recs = read_result(p)
        used = sorted({r["tid"] for r in recs})
        batch_tids |= set(used)
        miss = [t for t in used if t not in M]
        badp = []
        for r in recs:
            t = r.get("tid")
            if t not in M:
                continue
            if str(M[t][iP]) != str(r.get("P")):
                badp.append((t, M[t][iP], r.get("P")))
        L.append("  D3 %-5s 记录 %d 条 / tid %d / 未命中 map %d / P 不等 %d"
                 % (arm, len(recs), len(used), len(miss), len(badp)))
        if miss or badp:
            d3_ok = False
            d3_detail.append((arm, miss[:3], badp[:3]))
    mark("D3", d3_ok,
         "D3 %s 本批记录 P（探针产出）== 权威 map P（独立重算产出）**逐条相等**"
         % ("✅" if d3_ok else "⛔ %s" % (d3_detail,)))

    # D4 P 分布五项 == 账本 244.7.2
    d = p_dist(body, iP)
    d4_ok = True
    L.append("  D4  权威 map 的 P 分布 vs 账本 244.7.2 记的**复算**分布：")
    for k in ("n", "min", "max", "mean", "uniq"):
        same = (d[k] == LEDGER_P_DIST[k])
        d4_ok &= same
        L.append("       %-5s map=%-10s 账本=%-10s %s"
                 % (k, d[k], LEDGER_P_DIST[k], "✅" if same else "⛔"))
    mark("D4", d4_ok, "D4 %s 五项**逐项**相等" % ("✅" if d4_ok else "⛔"))

    # D5 t 逐条重算 + t <= n（截断不触发）
    # ⚖⚖⚖ 重算用的 pos_frac 必须取**跑批日志里那个**（D6 读出来的），
    #   ⛔ 不能写死 0.5 —— 否则「POS_FRAC=2.0」那种夹具会因为**两个原因**一起红
    #   （t 重算不符 + t>n）⇒ 拆掉「t>n」那一支的变异就变成**死变异**。
    pf_run = sorted(pfs)[0] if len(pfs) == 1 else LEDGER_POS_FRAC
    d5_ok = True
    bad_t, bad_nt, over = [], [], []
    for r in body:
        n_side, n_npz = int(r[iS]), int(r[iN])
        t = int(r[iT])
        if t != max(1, int(n_side * pf_run)):
            bad_t.append((r[0], t, max(1, int(n_side * pf_run))))
        if t != max(1, int(n_npz * pf_run)):
            bad_nt.append((r[0], t, max(1, int(n_npz * pf_run))))
        if t > n_npz:
            over.append((r[0], t, n_npz))
    d5_ok = (not bad_t and not bad_nt and not over)
    L.append("  D5  t 列逐条重算 max(1,int(n*%.2f))：n_gen_sidecar 不符 %d / "
             "n_gen_npz 不符 %d / **t > n** %d"
             % (pf_run, len(bad_t), len(bad_nt), len(over)))
    mark("D5", d5_ok,
         "D5 %s t 逐条可重算（两种 n 来源都一致）且 **t <= n** ⇒ 截断不触发"
         % ("✅" if d5_ok else "⛔ t不符%s t>n%s" % (bad_t[:2], over[:2])))

    # D7 n_eff == P + t
    bad_eff = [r[0] for r in body if int(r[iE]) != int(r[iP]) + int(r[iT])]
    mark("D7", not bad_eff,
         "D7 %s n_eff == P + t（%d/%d 行）"
         % ("✅" if not bad_eff else "⛔ %s" % (bad_eff[:3],), len(body) - len(bad_eff),
            len(body)))

    # ================= 结论 + 残留前提 ================================
    L.append("")
    L.append("  ⚖⚖⚖ **结论**")
    ident = R.get("S1") and R.get("S2") and R.get("S3") and R.get("S4")
    L.append("    · 源码层：%s ⇒ 探针的 `len(pid)` / `recomp_p.py` 的 `recomp` / "
             "map 的 `P` 是**同一个表达式**（恒等式，⛔ 不需要实测）"
             % ("✅ 三方逐位同形" if ident else "⛔ 不同形"))
    L.append("    · 数据层：%s ⇒ 本批 %d 个 tid 的 `P` == `len(pid)`"
             % ("✅ 逐条相等" if R.get("D3") else "⛔ 不等", len(batch_tids)))
    L.append("    · 截断：%s ⇒ `P + t <= len(pid) + n` ⇒ **不截断**"
             % ("✅ t <= n（逐行实测）" if R.get("D5") else "⛔"))
    L.append("    ⇒ %s 244.50 的分母 `inj = P + floor(n_gen x pos_frac) - 1` **精确**"
             % ("✅" if (ident and R.get("D3") and R.get("D5")) else "⛔"))

    L.append("")
    L.append("  ⚠⚠⚠ **残留前提（本工具⛔ 验不到，必须印成「未量到」）**")
    L.append("    R1 探针的 `--sidecar-dir` 与 map 的 `--data-dir` 是否**同一份侧车文件**")
    L.append("       —— 跑批脚本 `r244_warm_sweep.sh` 不在本地 ⇒ **未量到**")
    L.append("       ⚖ 支持性证据：D3 的逐条 P 相等（内容级吻合），"
             "⛔ 但**不是文件指纹证明**")
    L.append("    R2 远端 snapshot 目录的**文件内容**在两次跑批之间有没有变过")
    L.append("       —— **同一路径 ≠ 同一内容** ⇒ 本地量不到 ⇒ **未量到**")
    L.append("       ⚖ 可核修法：远端 `md5sum` 那几个 tokenizer 文件并落进产物")
    L.append("    R3 账本 244.7.2 的「侧车自报 == 独立重算 60/60」是**远端实测**")
    L.append("       —— 本工具**引用**它（`%d 条 / match %d / mismatch %d`），"
             "⛔ **没有重测**"
             % (LEDGER_SIDECAR_VS_RECOMP["n"], LEDGER_SIDECAR_VS_RECOMP["match"],
                LEDGER_SIDECAR_VS_RECOMP["mismatch"]))
    L.append("    R4 `sidecar_prompt_tokens.tsv` 的**来源未查**（仓库里找不到生产者）")
    L.append("       ⇒ ⛔ **不作为判据**（拿 map 的复制品比 map 是恒绿），仅旁证")

    ok = all(R.get(k) for k in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8",
                                "D1", "D2", "D2b", "D3", "D4", "D5", "D6", "D7"))
    return L, (0 if ok else 1), R


# --------------------------------------------------------------- 自检
SYNTH_PROBE = '''# -*- coding: utf-8 -*-
import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "%(model)s"
LAYER = 20


def analyze(alphas, dm, dc):
    # ⚖⚖⚖ **干扰项必须留在夹具里**（对齐真探针 :253 的 `n = alphas.size`、
    #   :371 的 `steps["n_ran"]`）—— 夹具比生产干净 ⇒ 判据的**作用域解析**
    #   就测不到 ⇒ 真数据才会炸。
    n = alphas.size
    out = {"resid_std": dm}
    steps = {"marks": [1, 2, 3]}
    steps["n_ran"] = len(steps["marks"]) - 1
    P = 0
    return n, out, steps, P


def run_cell(a):
    tok = AutoTokenizer.from_pretrained(MODEL)
    z = np.load(os.path.join(a.npz_dir, a.tid + ".npz"))
    gen = z["token_ids"].tolist()
    z.close()
    cti = json.load(open(Path(a.sidecar_dir) / (a.tid + ".json"), encoding="utf-8"))
    pid = tok(cti["chat_template_input"], return_tensors="pt",
              add_special_tokens=False).input_ids[0].tolist()
    P = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)
    n = len(gen)
    t = max(1, int(n * a.pos_frac))
    ids = torch.tensor([(pid + gen)[: P + t]], dtype=torch.long, device="cuda:0")
    inj = ids.shape[1] - 1
    return inj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pos-frac", type=float, default=0.5)
    ap.add_argument("--arm", default="w", choices=["w", "rand"])
    args = ap.parse_args()
    return run_cell(args)
'''

SYNTH_RECOMP = '''# -*- coding: utf-8 -*-
import json
import os
from glob import glob

MODEL = "%(model)s"
SIDECAR = "%(sidecar)s"


def main():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    rows = []
    for f in sorted(glob(os.path.join(SIDECAR, "*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        tid = j.get("trajectory_id") or os.path.basename(f)[:-5]
        cti = j.get("chat_template_input")
        extra = j.get("extra") or {}
        recomp = len(tok(cti, add_special_tokens=False).input_ids)
        rows.append((tid, extra.get("prompt_tokens"), recomp))
    return rows
'''

SYNTH_PRE = '''# -*- coding: utf-8 -*-
import argparse
import json
import os
from glob import glob

MODEL = "%(model)s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pos-frac", type=float, required=True)
    args = ap.parse_args()
    if not (0.0 < args.pos_frac <= 1.0):
        print("PRECOND_FAIL: pos_frac out of range: %%r" %% args.pos_frac)
        return 2
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    rows = []
    for f in sorted(glob(os.path.join(args.data_dir, "*.json"))):
        tid = os.path.basename(f)[:-5]
        j = json.load(open(f, encoding="utf-8"))
        cti = j.get("chat_template_input")
        P = len(tok(cti, add_special_tokens=False).input_ids)
        t = max(1, int(500 * args.pos_frac))
        rows.append((tid, P, t))
    return rows
'''

GOLD_P = [
    112, 120, 139, 140, 150, 154, 159, 163, 164, 165, 166, 171,
    173, 174, 188, 193, 196, 196, 203, 216, 226, 241, 268, 277,
    308, 337, 573, 592, 663, 914, 108, 116, 135, 136, 146, 150,
    155, 159, 160, 161, 162, 167, 169, 170, 184, 189, 192, 192,
    199, 212, 222, 237, 264, 273, 304, 333, 569, 588, 659, 910,
]
GOLD_TIDS = []
for _i in range(30):
    for _sfx in ("no_think", "think"):
        GOLD_TIDS.append("aime__aime25__p%02d__%s" % (_i, _sfx))


def _fixture(d, probe_src=None, recomp_src=None, pre_src=None,
             map_p=None, t_delta=None, stamp_md5=None, pos_frac=0.5,
             bad_record_p=False, launch=True):
    """⚖ 造一份**同形状**的夹具目录：三个源文件 + 权威 map + 兄弟 + 两臂结果 + 日志。"""
    def w(name, s):
        io.open(os.path.join(d, name), "w", encoding="utf-8").write(s)

    w("probe.py", SYNTH_PROBE % {"model": "SYNTH_MODEL"})
    w("recomp.py", SYNTH_RECOMP % {"model": "SYNTH_MODEL", "sidecar": "SYNTH_SIDECAR"})
    w("pre.py", SYNTH_PRE % {"model": "SYNTH_MODEL"})
    if probe_src:
        w("probe.py", probe_src)
    if recomp_src:
        w("recomp.py", recomp_src)
    if pre_src:
        w("pre.py", pre_src)

    Ps = map_p if map_p is not None else GOLD_P
    lines = ["tid\tP\tn_gen_sidecar\tn_gen_npz\tt\tn_eff"]
    for i, t in enumerate(GOLD_TIDS):
        P = Ps[i]
        n = 500
        t_ = max(1, int(n * pos_frac))
        if t_delta is not None:
            t_ = t_ + t_delta
        lines.append("%s\t%d\t%d\t%d\t%d\t%d" % (t, P, n, n, t_, P + t_))
    w("n_eff_map.new.tsv", "\n".join(lines) + "\n")
    # ⚖ 兄弟：内容**必须真的不同**（P 全 +1）⇒ 「选错文件」这个错查得出来
    sib = [lines[0]]
    for l in lines[1:]:
        f = l.split("\t")
        sib.append("%s\t%d%s" % (f[0], int(f[1]) + 1, "".join("\t" + x for x in f[2:])))
    w("n_eff_map.tsv", "\n".join(sib) + "\n")

    auth_md5 = stamp_md5 or md5_of(os.path.join(d, "n_eff_map.new.tsv"))
    stamp = "NMAP rows=60 md5=%s" % auth_md5

    def res(tids_used, tag):
        out = ["# header %s" % tag, stamp]
        for t in tids_used:
            P = int(Ps[GOLD_TIDS.index(t)])
            if bad_record_p and t == tids_used[0]:
                P += 1
            out.append(json.dumps({"tid": t, "arm": tag, "P": P, "n_gen": 500,
                                   "pos_frac": pos_frac, "inject_scope": "k",
                                   "inject_n_sites": 1,
                                   "p9_lo_meas": 0.0, "p9_hi_meas": 1.0}))
        return "\n".join(out) + "\n"

    w("_an.txt", res(GOLD_TIDS[:14], "w"))
    w("_ra.txt", res(GOLD_TIDS[-14:], "rand"))
    w("warm.log", "PINNED GPU=GPU-x CELLS=/b/warm_cells.txt NMAP=/b/n_eff_map.tsv "
                  "POS_FRAC=%s EXPECT_CELLS=137 TAG=_w ARM=w\n" % pos_frac
                  + stamp + "\n")
    w("warm_rand.log", "PINNED GPU=GPU-x CELLS=/b/warm_cells.txt NMAP=/b/n_eff_map.tsv "
                       "POS_FRAC=%s EXPECT_CELLS=137 TAG=_ra ARM=rand\n" % pos_frac
                       + stamp + "\n")
    if launch:
        w("launch.log", "LAUNCH start uuid=GPU-x cells=137 nmap_md5=%s  20:28:56\n"
                        % auth_md5)
    # ⚖ 补丁前快照：默认与探针**逐字相同**（= 补丁没碰分母那几行）
    w("probe_snap.py", io.open(os.path.join(d, "probe.py"), encoding="utf-8").read())
    return {"probe": os.path.join(d, "probe.py"),
            "recomp": os.path.join(d, "recomp.py"),
            "pre": os.path.join(d, "pre.py"),
            "snap": os.path.join(d, "probe_snap.py"),
            "stamp_md5": auth_md5,
            "map_glob": os.path.join(d, "n_eff_map*.tsv"),
            "results": {"w": os.path.join(d, "_an.txt"),
                        "rand": os.path.join(d, "_ra.txt")},
            "logs": os.path.join(d, "warm*.log"),
            "launch": os.path.join(d, "launch.log")}


def _run(fx, **kw):
    return audit(probe_src=fx["probe"], recomp_src=fx["recomp"], pre_src=fx["pre"],
                 probe_snap=fx.get("snap", ""), map_glob=fx["map_glob"],
                 results=fx["results"], logs=fx["logs"], launch=fx["launch"], **kw)


def selftest():
    import tempfile
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    d = tempfile.mkdtemp()

    # ---- 干净夹具必须全绿 -------------------------------------------
    fx = _fixture(d)
    L, rc, R = _run(fx)
    chk("C0", rc == 0, "干净夹具 rc=%d（%s）"
        % (rc, ",".join(k for k, v in R.items() if not v) or "全绿"))
    chk("C1", any("取自**同一份输入**时**必然相等**（恒等式，⛔ 不需要实测）" in x
                  for x in L),
        "必须印出「恒等式」限定")
    chk("C2", sum(1 for x in L if "未量到" in x) >= 3
        and all(any((" %s " % r) in x for x in L) for r in ("R1", "R2", "R3", "R4")),
        "残留前提必须印成「未量到」（≥3 条）且 R1–R4 四条**都在**")
    chk("C3", any("⛔ **不作为判据**" in x for x in L),
        "R4 必须声明 sidecar_prompt_tokens.tsv 不作判据")

    # ---- S1：三方 MODEL 不一致 ⇒ 必须红 -----------------------------
    d2 = tempfile.mkdtemp()
    fx2 = _fixture(d2, recomp_src=SYNTH_RECOMP % {"model": "OTHER_MODEL",
                                                   "sidecar": "SYNTH_SIDECAR"})
    L2, rc2, R2 = _run(fx2)
    chk("S1x", rc2 != 0 and not R2.get("S1"),
        "recomp 的 MODEL 不同 ⇒ S1 必须红（rc=%d）" % rc2)

    # ---- S2：tokenizer 加载不同 ⇒ 必须红 ---------------------------
    d3 = tempfile.mkdtemp()
    src = (SYNTH_PRE % {"model": "SYNTH_MODEL"}).replace(
        "AutoTokenizer.from_pretrained(MODEL)",
        'AutoTokenizer.from_pretrained(MODEL + "-v2")')
    fx3 = _fixture(d3, pre_src=src)
    L3, rc3, R3 = _run(fx3)
    chk("S2x", rc3 != 0 and not R3.get("S2"),
        "pre 的 tokenizer 加载不同 ⇒ S2 必须红（rc=%d）" % rc3)

    # ---- S3：flag 不同 ⇒ 必须红 -------------------------------------
    d4 = tempfile.mkdtemp()
    src = (SYNTH_RECOMP % {"model": "SYNTH_MODEL", "sidecar": "SYNTH_SIDECAR"}
           ).replace("add_special_tokens=False", "add_special_tokens=True")
    fx4 = _fixture(d4, recomp_src=src)
    L4, rc4, R4 = _run(fx4)
    chk("S3x", rc4 != 0 and not R4.get("S3"),
        "recomp 的 flag 变 True ⇒ S3 必须红（rc=%d）" % rc4)

    # ---- S4：字段名不同 ⇒ 必须红 -----------------------------------
    d5 = tempfile.mkdtemp()
    src = (SYNTH_RECOMP % {"model": "SYNTH_MODEL", "sidecar": "SYNTH_SIDECAR"}
           ).replace('j.get("chat_template_input")', 'j.get("chat_template")')
    fx5 = _fixture(d5, recomp_src=src)
    L5, rc5, R5 = _run(fx5)
    chk("S4x", rc5 != 0 and not R5.get("S4"),
        "recomp 取别的字段 ⇒ S4 必须红（rc=%d）" % rc5)

    # ---- S5：探针 P 少了 len(pid) 回退支 ⇒ 必须红 -------------------
    d6 = tempfile.mkdtemp()
    src = (SYNTH_PROBE % {"model": "SYNTH_MODEL"}).replace(
        'P = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)',
        'P = (cti.get("extra") or {}).get("prompt_tokens")')
    fx6 = _fixture(d6, probe_src=src)
    L6, rc6, R6 = _run(fx6)
    chk("S5x", rc6 != 0 and not R6.get("S5"),
        "探针 P 少回退支 ⇒ S5 必须红（rc=%d）" % rc6)

    # ---- S6：截断形状变了 ⇒ 必须红 ---------------------------------
    d7 = tempfile.mkdtemp()
    src = (SYNTH_PROBE % {"model": "SYNTH_MODEL"}).replace(
        "(pid + gen)[: P + t]", "(pid + gen)[: len(pid) + n]")
    fx7 = _fixture(d7, probe_src=src)
    L7, rc7, R7 = _run(fx7)
    chk("S6x", rc7 != 0 and not R7.get("S6"),
        "截断形状变了 ⇒ S6 必须红（rc=%d）" % rc7)

    # ---- S7：探针自己加了上界守卫 ⇒ 必须红 -------------------------
    d8 = tempfile.mkdtemp()
    src = (SYNTH_PROBE % {"model": "SYNTH_MODEL"}).replace(
        "    args = ap.parse_args()\n",
        "    args = ap.parse_args()\n"
        "    if not (0.0 < args.pos_frac <= 1.0):\n"
        "        raise SystemExit(2)\n")
    fx8 = _fixture(d8, probe_src=src)
    L8, rc8, R8 = _run(fx8)
    chk("S7x", rc8 != 0 and not R8.get("S7"),
        "探针有了上界守卫 ⇒ S7 的「探针无守卫」这一支必须红（rc=%d）" % rc8)

    # ---- D1：戳不一致 ⇒ 必须红 -------------------------------------
    d9 = tempfile.mkdtemp()
    fx9 = _fixture(d9)
    io.open(os.path.join(d9, "launch.log"), "w", encoding="utf-8").write(
        "LAUNCH start uuid=GPU-x cells=137 nmap_md5=%s  20:28:56\n" % ("0" * 32))
    L9, rc9, R9 = _run(fx9)
    chk("D1x", rc9 != 0 and not R9.get("D1"),
        "launch log 的戳与别处不一致 ⇒ D1 必须红（rc=%d）" % rc9)

    # ---- D3：记录 P 与 map 不等 ⇒ 必须红 ---------------------------
    d10 = tempfile.mkdtemp()
    fx10 = _fixture(d10, bad_record_p=True)
    L10, rc10, R10 = _run(fx10)
    chk("D3x", rc10 != 0 and not R10.get("D3"),
        "一条记录 P 偏了 ⇒ D3 必须红（rc=%d）" % rc10)

    # ---- D4：P 分布与账本不符 ⇒ 必须红 -----------------------------
    d11 = tempfile.mkdtemp()
    fx11 = _fixture(d11, map_p=[200] * 60)
    L11, rc11, R11 = _run(fx11)
    chk("D4x", rc11 != 0 and not R11.get("D4"),
        "map 的 P 分布与账本 244.7.2 不符 ⇒ D4 必须红（rc=%d）" % rc11)

    # ---- D5：t 不可重算 ⇒ 必须红 -----------------------------------
    d12 = tempfile.mkdtemp()
    fx12 = _fixture(d12, t_delta=1)
    L12, rc12, R12 = _run(fx12)
    chk("D5x", rc12 != 0 and R12.get("D1") and R12.get("D2") and not R12.get("D5"),
        "t 列不可重算（且 D1/D2 仍绿）⇒ D5 必须红（rc=%d）" % rc12)

    # ---- D5：t > n（pos_frac > 1）⇒ 必须红 ------------------------
    # ⚖⚠⚠⚠ 这一支**必须单独**被走到：夹具的 map 用 2.0 造 ⇒ t 重算用
    #   **日志里的 2.0** ⇒ 「t 重算」这一支是绿的 ⇒ 只有「t > n」红
    #   ⇒ 拆掉「t>n」检查的变异才是**活**变异（⛔ 否则就是死变异）。
    d13 = tempfile.mkdtemp()
    fx13 = _fixture(d13, pos_frac=2.0)
    L13, rc13, R13 = _run(fx13)
    chk("D5y", rc13 != 0 and R13.get("D1") and R13.get("D2") and not R13.get("D5"),
        "POS_FRAC=2.0 ⇒ t>n（会截断）且只有这一支红 ⇒ D5 必须红（rc=%d）" % rc13)

    # ---- D6：POS_FRAC 与账本不符 ⇒ 必须红 -------------------------
    d14 = tempfile.mkdtemp()
    fx14 = _fixture(d14, pos_frac=0.25)
    L14, rc14, R14 = _run(fx14)
    chk("D6x", rc14 != 0 and not R14.get("D6"),
        "POS_FRAC=0.25 ≠ 账本记的 0.5 ⇒ D6 必须红（rc=%d）" % rc14)

    # ---- D7：n_eff != P+t ⇒ 必须红 --------------------------------
    d15 = tempfile.mkdtemp()
    fx15 = _fixture(d15)
    p = os.path.join(d15, "n_eff_map.new.tsv")
    lines = io.open(p, encoding="utf-8").read().split("\n")
    f = lines[1].split("\t")
    f[5] = str(int(f[5]) + 1)
    lines[1] = "\t".join(f)
    io.open(p, "w", encoding="utf-8").write("\n".join(lines))
    # ⚖⚠⚠⚠ map 被改了 ⇒ **md5 变了** ⇒ 戳全部失效 ⇒ D1/D2 会先红
    #   ⇒ 期望标签就指不到 D7（= **空过的检查**）。
    #   ⇒ 必须把新 md5 **同步重戳**到结果文件与 launch log，
    #   让「D1/D2 绿、只有 D7 红」这一支**单独**被走到。
    old_md5 = fx15["stamp_md5"]
    new_md5 = md5_of(p)
    for fn in ("_an.txt", "_ra.txt", "launch.log", "warm.log", "warm_rand.log"):
        pp = os.path.join(d15, fn)
        # ⚖⚠⚠⚠ **先读后写**：`io.open(pp,"w").write(io.open(pp).read())`
        #   会先截断再读 ⇒ 写进去的是空串 ⇒ 夹具自己把自己搞没了。
        old = io.open(pp, encoding="utf-8").read()
        io.open(pp, "w", encoding="utf-8").write(old.replace(old_md5, new_md5))
    L15, rc15, R15 = _run(fx15)
    chk("D7x", rc15 != 0 and R15.get("D1") and R15.get("D2") and not R15.get("D7"),
        "一格 n_eff != P+t（且 D1/D2 仍绿）⇒ D7 必须红（rc=%d）" % rc15)

    # ---- S8：补丁前快照与现役探针不一致 ⇒ 必须红 --------------------
    d16 = tempfile.mkdtemp()
    fx16 = _fixture(d16)
    io.open(fx16["snap"], "w", encoding="utf-8").write(
        (SYNTH_PROBE % {"model": "SYNTH_MODEL"}).replace(
            'P = (cti.get("extra") or {}).get("prompt_tokens") or len(pid)',
            'P = (cti.get("extra") or {}).get("prompt_tokens")'))
    L16, rc16, R16 = _run(fx16)
    chk("S8x", rc16 != 0 and not R16.get("S8"),
        "快照的 P 表达式与现役探针不同 ⇒ S8 必须红（rc=%d）" % rc16)

    print("自检：%d/%d" % (len(ok), len(ok) + len(bad)))
    return 0 if not bad else 1


# --------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    L, rc, R = audit()
    for x in L:
        print(x)
    print("rc=%d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
