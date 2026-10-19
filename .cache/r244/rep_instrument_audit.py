#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rep_instrument_audit.py —— 「rep_n≥2 能不能回答『12/14 是不是噪声』」的 Phase-0 闸门

🔴🔴 **为什么要有这个工具**（修订 244.46）
  账本里剩下的那个 🔴 是：「rand 臂 12/14 到底是系统差异还是噪声」。
  244.41–244.45 钉的全部是「离刀尖一格」，⛔ 一条都不是「噪声」。
  ⚖ 答案要用 `rep_n≥2` 跑批才能得 ⇒ **跑批要占 GPU 小时** ⇒
  ⚠⚠⚠⚠ **在发批之前必须先验仪器**：仪器量不到那个量 ⇒ 这批白跑。

⚖⚠⚠⚖ **结论（纯静态，零 GPU）**

  探针里那一行是
      `vals = [lse_t(forward(W, _al)[mk]) - b_mark for _ in range(max(1, a.repeat))]`
  ⚖ 循环体读到 **6** 个名字：`W / _al / b_mark / forward / lse_t / mk`
  ⚖ 循环变量 `_` **一次都没被用到** ⇒ R 次迭代求的是**同一个表达式**
  ⚖ 而它的每一个输入在迭代间都不变（实测见报告 R1/R2/R3）
  ⚖⚠⚠⚖ ⇒ **R 次读数逐位相同** ⇒ `rep_spread_*=0` / `rep_exact_*=True` /
    `rep_std_*=0.0` 是**结构必然**，⛔ 不是量出来的结论
  ⇒ `--repeat R` 量的是「同进程内同输入是否逐位相同」，
     ⚖ 而那**正是设计已假设的事**（探针自己的 docstring 写着 forward 是确定性的）
  ⇒ **它剥不掉 修订 207 §207.5 死结里的「单读噪声」**。

⚖⚖ **正确的仪器不需要改探针**：batch 模式**每格已经是 `subprocess.run`
  独立进程** ⇒ 把整批**独立 launch R 次**、逐格比 `meas_lo/hi`，
  量到的就是**跨进程 / 跨卡**的单读噪声。
  ⚖⚠ 244.4x 已登记「rand 臂**跨物理卡确定性未量到**」⇒ 那正是这个空着的量。

⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不碰任何数据文件。
⚖⚠⚠⚖ 每条判据都必须**能红**：变异台改的就是**被审计的探针源码**。

⚖⚠⚠⚖⚖⚠ **两条工具自身的教训，写在文件头以免重犯**
  ① **定位循环一律用 AST 结构**（`a.repeat` 这个 Attribute 出现在生成器的
     iter 里）。⛔ 不许用 `get_source_segment` 配文本 ——
     本机 py3.9 的 `ast.comprehension` **没有位置信息** ⇒ 返回 `None`
     ⇒ 文本选择器**静默失配** ⇒ 第一版因此报了「探针形状已变，拒读」，
     而探针**根本没变** ⇒ ⛔ 那是**假的失败信息**，比没有信息更坏。
  ② **判据不许「看起来会红」**。第一版的 R3 判「forward 读且写的名字」——
     ⛔ 而 Python 里函数内赋值即局部变量，闭包变量**不可能**在体内被赋值
     ⇒ 那条判据**恒红**，与探针对错无关 ⇒ 已改成
     「真正的外部输入 + 首次调用后是否被重新赋值」。
"""

import argparse
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"

LOOP_ARGNAME = "repeat"

# ⚖ 已知危险源清单。⚠ **不是定理** ⇒ 报告必须这么写（见【3】）。
RNG_CALLS = ("rand", "randn", "randint", "randperm", "rand_like", "randn_like",
             "multinomial", "normal", "bernoulli", "dropout",
             "native_dropout", "manual_seed", "seed")


class HardFail(Exception):
    pass


_CURRENT_SRC = ""


def unparse(node):
    """⚖ 拿源码文本；`get_source_segment` 在无位置信息的节点上返回 None
    ⇒ 这里**退回** `ast.unparse`，⛔ 不许拿空串当「没找到」。"""
    try:
        seg = ast.get_source_segment(_CURRENT_SRC, node)
    except Exception:
        seg = None
    if seg:
        return seg
    try:
        return ast.unparse(node)
    except Exception:
        return "<拿不到源码>"


def _reads_repeat(node):
    return any(isinstance(n, ast.Attribute) and n.attr == LOOP_ARGNAME
               and isinstance(n.value, ast.Name) and n.value.id == "a"
               for n in ast.walk(node))


def load_names(node):
    return {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def store_names(node):
    return {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def bound_in(node):
    """⚖ 这个作用域里被绑定的名字（形参 + Store + 推导式目标）。"""
    b = set(store_names(node))
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        b |= {a.arg for a in node.args.args}
        b |= {a.arg for a in node.args.kwonlyargs}
    for n in ast.walk(node):
        if isinstance(n, (ast.comprehension,)):
            b |= {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}
    return b


def _repeat_loop(src):
    """⚖ 定位**恰好一个**「iter 里读了 `a.repeat`」的推导式 ⇒ (node, tree)。"""
    tree = ast.parse(src)
    hits = [n for n in ast.walk(tree)
            if isinstance(n, ast.ListComp)
            and any(_reads_repeat(g.iter) for g in n.generators)]
    if len(hits) == 1:
        return hits[0], tree
    n_lit = src.count("a.%s" % LOOP_ARGNAME)
    if len(hits) == 0 and n_lit > 0:
        why = ("源码里有 %d 处 `a.%s` 却一个推导式都没匹配 ⇒ "
               "⛔ 更可能是**本工具的选择器坏了**，⛔ 不许据此说探针变了"
               % (n_lit, LOOP_ARGNAME))
    elif len(hits) == 0:
        why = "源码里 `a.%s` 出现 %d 次 ⇒ 探针里**确实没有**这个循环" % (LOOP_ARGNAME, n_lit)
    else:
        why = "找到 %d 个候选 ⇒ 分不清在量哪一个，⛔ 拒读（⛔ 不许取第一个凑合）" % len(hits)
    raise HardFail(why)


def fn_by_name(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def enclosing_fn(tree, node):
    best = None
    for cand in ast.walk(tree):
        if isinstance(cand, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node in set(ast.walk(cand)):
                if best is None or (cand.lineno <= best.lineno
                                    and cand.end_lineno >= best.end_lineno):
                    best = cand
    return best


def enclosing_loop(tree, node):
    """⚖ 推导式**外面**最近的那层 `for`（没有则 None）。"""
    parent = node
    while True:
        best = None
        for cand in ast.walk(tree):
            if isinstance(cand, (ast.For, ast.AsyncFor)):
                if parent in set(ast.walk(cand)):
                    if best is None or (cand.lineno <= best.lineno
                                        and cand.end_lineno >= best.end_lineno):
                        best = cand
        if best is None:
            return None
        # 这个 for 自己是不是就是推导式？⇒ 不是「外层」。
        if best is not node:
            return best
        return None


def rng_sites(tree):
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if nm in RNG_CALLS:
            out.append((nm, n.lineno))
    return sorted(out, key=lambda x: x[1])


def has_eval(tree):
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "eval" for n in ast.walk(tree))


def subprocess_run_lines(tree):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
           and n.func.attr == "run" and isinstance(n.func.value, ast.Name) \
           and n.func.value.id == "subprocess":
            out.append(n.lineno)
    return sorted(out)


def first_call_line(fn, funcname):
    ls = [n.lineno for n in ast.walk(fn)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
          and n.func.id == funcname]
    return min(ls) if ls else None


# --------------------------------------------------------------- 判据
def audit(src, probe_label="被审计的探针"):
    global _CURRENT_SRC
    _CURRENT_SRC = src
    L = ["【0】被审计对象：%s" % probe_label]
    try:
        loop, tree = _repeat_loop(src)
    except HardFail as e:
        return L + ["【⛔】%s" % e], 1

    fn = enclosing_fn(tree, loop)
    if fn is None:
        return L + ["【⛔】重复循环不在任何函数里 ⇒ 拒读"], 1

    loop_line = min(n.lineno for n in ast.walk(loop) if hasattr(n, "lineno"))
    body_free = sorted(load_names(loop.elt))
    tgt = loop.generators[0].target
    tgt_names = [tgt.id] if isinstance(tgt, ast.Name) else sorted(load_names(tgt))

    L.append("【1】循环体读到 %d 个名字：%s" % (len(body_free), " / ".join(body_free)))
    L.append("  ⚖ 循环变量 = %s ｜ 所在函数 %s() ｜ 第 %d 行"
             % (" / ".join(tgt_names) or "—", fn.name, loop_line))
    L.append("  ⚖ 循环体：%s" % unparse(loop.elt)[:72])
    ok = True

    # ---- R1 循环变量没被用到 → 否则每轮输入不同 ------------------------------
    used = [t for t in tgt_names if t in body_free]
    L.append("  R1 循环变量在循环体里被用到：%s ⇒ %s"
             % ("、".join(used) or "无", "✅ 没用到 ⇒ R 轮求同一个表达式" if not used
                else "⛔ 用到了 ⇒ 每轮输入不同，这是真重复"))
    if used:
        ok = False

    # ---- R2 外层 for 的循环体里，自由变量有没有被改 ---------------------------
    #   ⚖⚠⚠ 只看「外层 for 的循环体」：外层 for 的**目标**(_al)当然每轮重绑，
    #   ⛔ 但那发生在推导式**外面** ⇒ 不影响 R 轮内部。
    outer = enclosing_loop(tree, loop)
    if outer is None:
        L.append("  R2 推导式外面没有 for 循环 ⇒ 无外层迭代可污染 ✅")
    else:
        # ⚖⚠⚠ **只看外层 for 的「体」**：它的 target（`_al`）本来就每轮重绑，
        #   ⛔ 但那发生在推导式**外面** ⇒ 不影响 R 轮内部。
        #   把 target 也算进来 ⇒ `_al` 每一次都被误报（本项目真探针上就误报过一次）。
        body_nodes = list(outer.body)
        late = {}
        for nm in body_free:
            if nm in tgt_names:
                continue
            lns = sorted({n.lineno for bn in body_nodes for n in ast.walk(bn)
                          if isinstance(n, ast.Name) and n.id == nm
                          and isinstance(n.ctx, ast.Store)})
            if lns:
                late[nm] = lns
        L.append("  R2 外层 for（L%d）体内被重新赋值的自由变量：%s ⇒ %s"
                 % (outer.lineno,
                    "；".join("%s@L%s" % (k, v) for k, v in late.items()) or "无",
                    "✅ 全都没被改" if not late
                    else "⛔ 改了 ⇒ 第 2 轮起输入就可能不同"))
        if late:
            ok = False

    # ---- R3 forward 的**真正外部输入**在首次调用后有没有被重新赋值 ----------
    fw = fn_by_name(tree, "forward")
    if fw is None:
        L.append("  R3 ⛔ 探针里没有 forward() ⇒ 拒读")
        ok = False
    else:
        ext = sorted(load_names(fw) - bound_in(fw))
        fc = first_call_line(fw, "model")
        owner = enclosing_fn(tree, fw) or fn
        re_late = {}
        for nm in ext:
            lns = sorted({n.lineno for n in ast.walk(owner)
                          if (isinstance(n, ast.Name) and n.id == nm
                              and isinstance(n.ctx, ast.Store))
                          or (isinstance(n, ast.arg) and n.arg == nm)})
            late = [x for x in lns if fc is not None and x > fc]
            if late:
                re_late[nm] = late
        # ⚖⚠ 判定符号**必须与 R 标签同行**：拆到下一行 ⇒ 变异台只读得到
        #   `R3` 开头那一行 ⇒ 它会报「没转红」而真因是**报告形状**变了。
        L.append("  R3 forward() 的**真正外部输入**%d 个：%s ｜ 首次 model(...) 在 L%s"
                 " ｜ 此后仍被重新赋值：%s ⇒ %s"
                 % (len(ext), " / ".join(ext), fc,
                    "；".join("%s@L%s" % (k, v) for k, v in re_late.items()) or "无",
                    "✅ 一个都没变" if not re_late
                    else "⛔ 变了 ⇒ 第 2 次调用可能看到不同的东西"))
        if re_late:
            ok = False

    # ---- R4 全文件不得有消耗 RNG 的调用 -------------------------------------
    rng = rng_sites(tree)
    L.append("  R4 全文件里消耗 RNG 的调用：%d 处%s ⇒ %s"
             % (len(rng),
                ("（%s）" % "、".join("%s@L%d" % (a, b) for a, b in rng[:5]))
                if rng else "",
                "✅ 一处都没有" if not rng else "⛔ 有 ⇒ 「R 轮逐位相同」不成立"))
    if rng:
        ok = False

    # ---- R4b model 必须 .eval() --------------------------------------------
    ev = has_eval(tree)
    L.append("  R4b 存在 .eval() 调用：%s ⇒ %s"
             % ("有" if ev else "没有", "✅" if ev else "⛔ 没有 ⇒ dropout 在跑，重复就不是自我重复"))
    if not ev:
        ok = False

    # ---- R5 跨进程仪器 -------------------------------------------------------
    sp = subprocess_run_lines(tree)
    L.append("  R5 subprocess.run 调用点 %d 处（行 %s）⇒ %s"
             % (len(sp), sp[:5], "✅ 零探针改动即可量跨进程噪声" if sp
                else "⛔ 没有 ⇒ 跨进程仪器不成立，本节结论要重做"))
    if not sp:
        ok = False

    # ---- 结论 ---------------------------------------------------------------
    L.append("")
    L.append("【2】结论（由上面的实测数推出，⛔ 不是写死的）")
    if ok:
        L.append("  ⚖ 循环体 %d 个自由变量；循环变量 %d 个（**未用到**）；"
                 "forward 外部输入 %d 个、首次调用后**一个都没被重新赋值**；"
                 "RNG 调用 0 处；有 .eval()" % (len(body_free), len(tgt_names), len(ext)))
        L.append("  ⚖⚠⚠⚖ ⇒ `--repeat R` 的 R 轮**逐位相同**")
        L.append("  ⚖⚠⚠⚖ ⇒ `rep_spread_*=0` / `rep_exact_*=True` / `rep_std_*=0.0`"
                 " 是**结构必然**，⛔ 不是量出来的结论")
        L.append("  ⚖⚠⚠⚖ ⇒ 它量的是「同进程内同输入是否逐位相同」，"
                 "而那**正是设计已假设的事**")
        L.append("  ⚖⚠⚠⚖ ⇒ 它**剥不掉** 修订 207 §207.5 死结里的「单读噪声」"
                 " ⇒ ⛔ 用它跑批**买不到**『12/14 是不是噪声』")
        L.append("")
        L.append("  ⚖ 正确的仪器（**零探针改动**）：")
        L.append("     整批**独立 launch R 次**（R=3 起步），逐 (tid,pos) 比较")
        L.append("     `meas_lo` / `meas_hi` 的跨进程散布 ⇒ 那才是「单读噪声」")
        L.append("     ⚖⚠ 跨物理卡再各来一次 ⇒ 244.4x 登记的"
                 "「rand 臂跨物理卡确定性未量到」正好是这个量")
    else:
        L.append("  ⛔ 审计未全过 ⇒ **不许**据此声称 `--repeat R` 有用或无用"
                 "（探针一改结论就会变 ⇒ 每次改探针都要重跑本工具）")

    L.append("")
    L.append("【3】⛔ 本工具没验的（写在这里以免被当成全绿）")
    L.append("  ⛔ CUDA 内核级不确定性（同进程内）**静态量不到**")
    L.append("  ⛔ RNG 危险源清单 %d 条**不是定理** ⇒ 清单外的入口需人工核" % len(RNG_CALLS))
    L.append("  ⛔ 本工具⛔ **没有跑批、没有改探针、没有发批**")
    return L, (0 if ok else 1)


# --------------------------------------------------------------- 自检
SYNTH_HEAD = ("import subprocess\n"
              "MODEL = object()\n"
              "def inject_at(h, v, a, s, i, n=None, ne=False):\n"
              "    return h + v\n"
              "class _M:\n"
              "    def eval(self):\n"
              "        return self\n"
              "def forward(vec, alpha):\n"
              "    blk = None\n"
              "    def pre(m, i):\n"
              "        return None\n"
              "    hk = None\n"
              "    o = MODEL(1)\n"
              "    return o\n"
              "def run_cell(a, W):\n"
              "    mk = 1\n    LAYER = 3\n    inj = 5\n"
              "    ids = None\n    model = _M().eval()\n"
              "    b_mark = 0.0\n    _lab = 0\n    _al = 0.5\n"
              "    M = 1\n"
              "%BODY%"
              "def driver():\n"
              "    subprocess.run([])\n")


def synth(body):
    return SYNTH_HEAD.replace("%BODY%", body)


def selftest(probe_path=PROBE_REL):
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # 合成夹具 1：循环体**用到**循环变量 ⇒ R1 必红
    b1 = ("    vals = [forward(W, 0.5 + _)[mk] - b_mark"
          " for _ in range(max(1, a.repeat))]\n")
    L1, r1 = audit(synth(b1), "A 夹具")
    chk("C1", r1 != 0, "⛔ 用到 `_` ⇒ 必须红（rc=%d）" % r1)
    chk("C2", any(x.lstrip().startswith("R1") and "⛔" in x for x in L1),
        "R1 行上必须同时出现判定符号：%s"
        % next((x.strip()[:60] for x in L1 if x.lstrip().startswith("R1")), "—"))

    # 合成夹具 2：外层 for 体内**重绑**自由变量 ⇒ R2 必红
    b2 = ("    for _lab, _al in ((\"lo\", 0.5), (\"hi\", 1.0)):\n"
          "        b_mark = b_mark + 0.0\n"
          "        vals = [forward(W, _al)[mk] - b_mark"
          " for _ in range(max(1, a.repeat))]\n")
    L2, r2 = audit(synth(b2), "B 夹具")
    chk("C3", r2 != 0, "⛔ 外层 for 体内重绑 b_mark ⇒ 必须红（rc=%d）" % r2)
    chk("C4", any(x.lstrip().startswith("R2") and "⛔" in x for x in L2),
        "R2 行必须红：%s"
        % next((x.strip()[:64] for x in L2 if x.lstrip().startswith("R2")), "—"))

    # 合成夹具 3：干净 ⇒ **必须全绿**（否则判据里混着恒红的假阳性）
    b3 = ("    for _lab, _al in ((\"lo\", 0.5), (\"hi\", 1.0)):\n"
          "        vals = [forward(W, _al)[mk] - b_mark"
          " for _ in range(max(1, a.repeat))]\n")
    L3, r3 = audit(synth(b3), "C 夹具")
    chk("C5", r3 == 0, "干净夹具必须**全绿**（恒红的假阳性会让这里永红）：\n     "
        + " / ".join(x.strip()[:52] for x in L3 if "⛔" in x and "没有跑批" not in x)[:160])

    # 合成夹具 4：有 RNG 消耗 ⇒ R4 必红
    b4 = ("    torch = None\n"
          "    vals = [torch.rand(1)[0] + forward(W, _al)[mk] - b_mark"
          " for _ in range(max(1, a.repeat))]\n")
    L4, r4 = audit(synth(b4), "D 夹具")
    chk("C6", any(x.lstrip().startswith("R4 ") and "⛔" in x for x in L4),
        "R4 必须点名 RNG 调用")

    # 真探针
    if not os.path.exists(probe_path):
        for t in ("C7", "C8", "C9", "C10", "C11"):
            chk(t, False, "探针源码不可达（%r）⇒ 审计未验" % probe_path)
    else:
        src = io.open(probe_path, encoding="utf-8").read()
        L, rc = audit(src, "真探针")
        chk("C7", rc == 0, "真探针审计必须全绿（rc=%d）" % rc)
        chk("C8", any(x.startswith("【1】循环体读到 6 个名字") for x in L),
            "必须报出 6 个自由名字：%s"
            % next((x for x in L if x.startswith("【1】")), "—"))
        chk("C9", any("逐位相同" in x for x in L), "结论必须印出「逐位相同」")
        chk("C10", any("独立 launch" in x for x in L), "必须印出正确仪器")
        chk("C11", any("不是定理" in x for x in L), "必须声明 RNG 清单**不是定理**")

    # 形状漂移 / 选择器坏：两者必须**可区分**
    try:
        _repeat_loop("def g(a):\n    return []\n")
        chk("C12", False, "没有循环时必须 HardFail")
    except HardFail as e:
        chk("C12", "确实没有" in str(e), "没有循环 ⇒ 措辞「确实没有」：%s" % str(e)[:50])
    try:
        _repeat_loop("def g(a):\n    return [x for _ in range(a.repeat)]\n"
                     "def h(a):\n    return [y for _ in range(a.repeat)]\n")
        chk("C13", False, "两个循环时必须 HardFail")
    except HardFail as e:
        chk("C13", "2 个候选" in str(e), "找到多个 ⇒ 必须拒读：%s" % str(e)[:40])
    try:
        _repeat_loop("def g(a):\n    # a.repeat 只是注释里的一句话\n    return []\n")
        chk("C14", False, "注释里有 a.repeat 时必须 HardFail")
    except HardFail as e:
        chk("C14", "选择器坏了" in str(e),
            "源码有 a.repeat 却没匹配 ⇒ 必须说「选择器坏了」：%s" % str(e)[:44])

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="rep_n≥2 的 Phase-0 仪器闸门（零 GPU）")
    ap.add_argument("--probe", default=PROBE_REL)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest(args.probe)
    L, rc = audit(io.open(args.probe, encoding="utf-8").read(), args.probe)
    print("\n".join(L))
    return rc


if __name__ == "__main__":
    sys.exit(main())
