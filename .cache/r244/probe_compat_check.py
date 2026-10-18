#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_compat_check.py —— 探针改动的**兼容性预检**（零 GPU，不动真文件）

🔴 **为什么要有这个工具**
  244.34/244.35 的结论：那个「只差一个位点」的配对对照**设计上成立**，
  ⛔ 但**探针跑不出**（`_k_positions` 没有强制指定位点的能力）。
  ⚖⚠ 而改探针有风险：`.cache/mutbak/r204_noise_probe.py` 是
     `ladder_position_audit` / `dose_axis_audit` / `pair_ladder_preflight`
     **三个工具** AST 抽函数的**唯一来源** ⇒ 改签名会**同时**波及三处判据。
  ⚗⇒ 在动那个文件之前，先把「候选改动向后兼容吗」**验出来**。

⚖⚖⚖ **修订 244.36 的头号发现：存在一条「抽取契约」，本工具第一版踩了**

  ⚖ 三个工具抽 `_k_positions` 的方式**完全一样**：
        对 `ast.parse(src).body` 找 `FunctionDef(name="_k_positions")`
        → `ast.get_source_segment(src, node)` **只取那一个 def**
        → 在空命名空间 `ns = {}` 里 exec（只预置 `import numpy as _np`）
  ⚖⚠⚠ **那只取一个 def** 意味着：候选改动**必须自包含** ——
     它只能引用 builtins 与 numpy，⛔ 不能调用任何**兄弟函数**。

  ⚖ 本工具第一版的补丁是「包装器」：原函数改名 `_k_positions_base`，
     新 `_k_positions` 调它。它在**真探针里逻辑上成立**，
     ⚖⚠⚠⚖ 但**违反契约** —— 单独抽出来时 `_k_positions_base` 根本不在命名空间里：
        NameError: name '_k_positions_base' is not defined
  ⚖⚠ 而如果只看「打上补丁的文件能不能 import」⇒ **它是绿的** ⛔ 绿色信号。
  ⚗⇒ 这就是为什么 J6 必须**抽出来真的调**，而不是 `callable(fn)`。

⚖⚠⚖ **第二处：J1 网格原本只测 `nested=False`**
  ⚖ 补丁改的恰恰是 **`nested=True` 那条 return** ——
     而默认参数就是 `nested=False` ⇒ 旧 J1 **根本没盖住被改的那条路**。
  ⛔ 「判据绿了」与「被改的地方没被验」可以同时成立。
  ⚗⇒ 修法：J1 对 `nested ∈ {False, True}` **两条路都跑**。

⚖⚖ **第三处：`run()` 的 §2 仍在用非嵌套调用拿 base**
  ⚖ 新设计里「非嵌套 + force」是**大声报错**，不是静默忽略
  ⇒ §2 若还用 `new(n, k)` 拿 base、再 `new(n, k, force=…)`，
     它会**第一格就抛**。这正是「让静默失效变大声报错」的价值。

⛔ 本工具：⛔ 不修改真探针；⛔ 不跑批；⛔ 只在**临时目录**里造一份打过补丁的副本。
⚖⚠ 报告里所有数都**从数据算出来**再印，⛔ 不写死「三处都过」之类。
"""

import argparse
import ast
import contextlib
import importlib.util
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
PROBE_REL = ".cache/mutbak/r204_noise_probe.py"

# ⚖ 三个从探针 AST 抽函数的工具：改动若破坏它们的抽取，这里必须报红。
EXTRACTORS = ("ladder_position_audit", "dose_axis_audit", "pair_ladder_preflight")

# ⚖⚠⚠⚖ 候选补丁 = **三处自包含内联**替换。
# ⚖⚠⚠⛔ 它**不**新增兄弟函数、不**不**改名原函数 ——
#     因为三个工具的抽取契约只给那**一个 def**（见文件头）。
SIG_OLD = "def _k_positions(n, k, seed=0, nested=False):"
SIG_NEW = "def _k_positions(n, k, seed=0, nested=False, force=None):"

# ⚖ force 的**非嵌套守卫**：插在恒等捷径之前 ⇒ 无论 k 多大都先炸。
# ⚖⚠ 为什么不放后面：`k==n` 时 force 本就无事可做，
#    放后面会让「非嵌套 + force」在 k==n 时**静默通过** ⇒ 契约不一致。
SHORTCUT_ANCHOR = "    if k == n:\n        return list(range(n))"
FORCE_GUARD = (
    "    if force is not None and not nested:\n"
    "        raise ValueError(\n"
    '            "force 只在 nested=True 下有定义（非嵌套抽取没有『下一个位点』"\n'
    '            "可换）；⛔ 不许静默忽略")\n'
)

# ⚖ 嵌套分支：`force` 把指定位点**换进**集合（已在集内则不动）。
# ⚖⚠⚠⚖ 第三处发现（244.36）：默认路径那一行**必须逐字保留**。
#   `ladder_position_audit` 的自检 **A4** 是按**这一行的字面文本**做夹具变异：
#     seg.replace("return sorted(int(x) for x in _rng.permutation(n)[:k])",
#                 "return sorted(int(x) for x in _rng.permutation(n)[:k - 1])")
#     assert bad != seg, "没改到夹具"
#   我第一版把它改写成 `_perm = ...; pos = ...`（**行为完全等价**），
#   ⚖⚠⚠ 于是那个 `str.replace` **静默变成空操作** ⇒ A4 靠自己的
#   `assert bad != seg` 当场报红 ⛔ 这正是本项目那一条「静默失效」。
#   ⚖⇒ **行为级兼容 ≠ 文本级兼容**，而下游工具真的按文本建夹具。
NESTED_OLD = "        return sorted(int(x) for x in _rng.permutation(n)[:k])"
NESTED_NEW = (
    "        # ⚖⚠⚠⚖ 默认路径这一行**逐字**保留旧实现 ⛔ 不许改写它：\n"
    "        #   `ladder_position_audit` 的自检 A4 按**这一行的文本**做\n"
    "        #   夹具变异（`[:k]` -> `[:k-1]`）来证明「位数 != k ⇒ 硬失败」。\n"
    "        #   改写成等价形式 ⇒ 那个 str.replace **静默变空操作**。\n"
    "        if force is None:\n"
    "            return sorted(int(x) for x in _rng.permutation(n)[:k])\n"
    "        _perm = _rng.permutation(n)\n"
    "        pos = sorted(int(x) for x in _perm[:k])\n"
    "        if int(force) not in pos:\n"
    "            pos = sorted([p for p in pos if p != int(_perm[k - 1])]\n"
    "                        + [int(force)])\n"
    "        return pos"
)

ANCHORS = (("SIG_OLD", SIG_OLD), ("SHORTCUT", SHORTCUT_ANCHOR), ("NESTED_RET", NESTED_OLD))


class HardFail(Exception):
    pass


# --------------------------------------------------------------- 取函数
def load_by_path(path, name):
    """⚖ 从**指定文件**抽出函数并 exec —— ⛔ 不手抄。

    ⚖⚠⚖ 这里**刻意**复刻三个工具的抽取方式（只取那一个 def、干净命名空间），
       因为「候选改动能否被抽取」本身就是待验的性质。
    """
    src = open(path, encoding="utf-8").read()
    fn = None
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            fn = node
            break
    if fn is None:
        raise HardFail("%s 里找不到 %s" % (path, name))
    ns = {}
    exec(compile("import numpy as _np\n"
                 + ast.get_source_segment(src, fn), path, "exec"), ns)
    return ns[name]


def _extractor(modname):
    """⚖ 载入一个「从探针抽函数」的工具模块。⛔ 只读，不改它。"""
    path = os.path.join(HERE, modname + ".py")
    if not os.path.exists(path):
        raise HardFail("找不到 %s ⇒ ⛔ 拒读（不能假装三个都验过）" % path)
    spec = importlib.util.spec_from_file_location(modname + "_compat", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------- 打补丁
def anchor_counts(src):
    """⚖ 返回每个锚点在该源码里的命中次数。⛔ 必须**恰好 1**。"""
    return [(nm, src.count(anc)) for nm, anc in ANCHORS]


def make_patched(probe_path, out_path):
    """⚖ 在**临时副本**上施加候选补丁。⛔ 原文件一个字都不动。"""
    src = open(probe_path, encoding="utf-8").read()
    for nm, c in anchor_counts(src):
        if c != 1:
            raise HardFail("补丁锚点 %s 命中 %d 处（要求恰好 1）"
                           "⇒ 探针形态已变，⛔ 拒读" % (nm, c))
    patched = (src.replace(SIG_OLD, SIG_NEW)
                  .replace(SHORTCUT_ANCHOR, FORCE_GUARD + "\n" + SHORTCUT_ANCHOR)
                  .replace(NESTED_OLD, NESTED_NEW))
    if patched == src:
        raise HardFail("补丁打完没有任何变化 ⇒ ⛔ 拒读")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(patched)
    return patched


# --------------------------------------------------------------- 判据
def j1_equiv(a, b, grid, nested):
    """⚖ **J1**：默认调用下，候选函数与原函数在网格上**逐档相同**。

    ⚖⚠⚠⚖ `nested` 两条路**都必须跑**。第一版只跑 `nested=False`，
       而补丁改的恰恰是 `nested=True` 那条 return
       ⇒ 旧判据「绿」而**被改的那条路从未被验**。
    """
    for n, k in grid:
        if sorted(int(x) for x in a(n, k, nested=nested)) != \
           sorted(int(x) for x in b(n, k, nested=nested)):
            return False
    return True


def _ranks(n, nested):
    """⚖ 位点 id → 它在**那次抽取顺序**里的名次。"""
    import numpy as np
    if nested:
        order = np.random.default_rng(0).permutation(n).tolist()
    else:
        order = np.random.default_rng(0).choice(n, size=n, replace=False).tolist()
    return {int(v): i for i, v in enumerate(order)}


def j3_force_swap(base, forced, k):
    """⚖ **J3**：`force` 版与基础版**恰好差一个元素**，且两边都仍是 k 个。"""
    sb, sf = set(base), set(forced)
    return sb != sf and len(sb) == k and len(sf) == k and len(sb ^ sf) == 2


def j4_dropped_is_maxrank(base, forced, n, nested=True):
    """⚖ **J4**：被换掉的必须是**抽取序里最靠后**的那个。

    ⚖⚠⚠⛔ 第一版这一条是**恒绿**的：末尾那句 `ranks.get(worst, -1) >= -1`
      **恒为真**（秩恒 ≥0），所以它验不了任何东西。
    ⚖⚠⚠ 而且它比的是**数值最大**（`sorted(sb)[-1]`），⛔ 不是**秩最大** ——
      两者通常**不是同一个位点**。
    ⚗⇒ 修法：名次表按**真实抽取序**重建（`_ranks`），
      再比「基础集里名次最大的那个」是不是被换掉的那个。
    """
    sb, sf = set(base), set(forced)
    dropped, added = sb - sf, sf - sb
    if len(dropped) != 1 or len(added) != 1:
        return False
    ranks = _ranks(n, nested)
    worst = max(sb, key=lambda j: ranks[j])
    return next(iter(dropped)) == worst


def rebind_probe(ns, new_path):
    """⚖ 把命名空间里指向**真探针**的路径，全部改指到 `new_path`。

    ⚖⚠⚠⚠ 陷阱：`def load_k_positions(probe_path=PROBE, ...)` 的默认值
       在**函数定义那一刻**就把字符串绑定了 ⇒ 之后 `ns["PROBE"] = x`
       **改不动它**（自检 C9 用一个两行夹具当场证明）。
    ⚖⚠ 而三个工具**全都**是 `def f(path=PROBE_常量)` 这种写法
       ⇒ ⚠⚠⚠ 只改全局变量的 J9 会**静默地继续读真探针** ⇒ **恒绿**。
    ⚖⚠ 而恒绿的 J9 比没有 J9 **更危险**：它会让「三个自检都过」这句结论
       在根本没验过补丁的情况下被印出来。
    ⚗⇒ 所以必须同时改 `__defaults__`，并且**回读**有没有漏网的。

    ⚖ 返回 `(改掉的旧路径列表, 改掉的默认参数个数, 仍然卡住的函数名)`。
    """
    olds = set()
    for g in ("PROBE", "PROBE_REL"):
        v = ns.get(g)
        if isinstance(v, str) and "r204_noise_probe" in v:
            olds.add(v)
            ns[g] = new_path
    ndef = 0
    for _name, obj in list(ns.items()):
        d = getattr(obj, "__defaults__", None)
        if not d:
            continue
        nd = tuple(new_path if (isinstance(x, str) and x in olds) else x for x in d)
        if nd != d:
            obj.__defaults__ = nd
            ndef += 1
    stuck = sorted({name for name, obj in ns.items()
                    if any(isinstance(x, str) and x in olds
                           for x in (getattr(obj, "__defaults__", None) or ()))})
    return sorted(olds), ndef, stuck


def j7_isolated_call(fn, n=997, k=249):
    """⚖ **J7 抽取契约**：单独抽出来**必须真的能调**，不只是 `callable`。

    ⚖⚠⚠⚖ 头号发现就是这一条抓到的：包装器方案抽出来是 `callable(fn) == True`
       （函数对象确实存在），⚖⚠ 但**一调就 NameError**
       ⇒ ⛔ 只验「能抽」会把破坏读成通过。
    """
    try:
        out = list(fn(n, k, nested=True))
    except Exception as e:                      # ⚖ 这里要的是「干净的失败信息」
        return False, "%s: %s" % (type(e).__name__, str(e)[:56])
    if len(out) != k or len(set(int(x) for x in out)) != k:
        return False, "调通了但位数不对：%d/%d" % (len(out), k)
    return True, ""


# --------------------------------------------------------------- 合成夹具
SYNTH_PROBE = '''def _k_positions(n, k, seed=0, nested=False):
    """合成夹具：真探针 `_k_positions` 的**骨架**（四条锚点齐全）。"""
    import numpy as _np
    n, k = int(n), int(k)
    if n <= 0:
        raise ValueError("n<=0")
    if k < 0 or k > n:
        raise ValueError("k 越界")
    if k == n:
        return list(range(n))
    if k == 0:
        return []
    _rng = _np.random.default_rng(int(seed))
    if nested:
        return sorted(int(x) for x in _rng.permutation(n)[:k])
    return sorted(_rng.choice(n, size=k, replace=False).tolist())


def _use_it(n, k):
    return _k_positions(n, k, nested=True)
'''

# ⚖⚠⚠⚖ 反面夹具：**包装器**方案 —— 逻辑对，但**违反抽取契约**。
# ⚖ 它的存在是为了让自检能证明「契约这一关真的能红」。
SYNTH_WRAPPED = '''def _k_positions_base(n, k, seed=0, nested=False):
    import numpy as _np
    n, k = int(n), int(k)
    if k == n:
        return list(range(n))
    if k == 0:
        return []
    _rng = _np.random.default_rng(int(seed))
    if nested:
        return sorted(int(x) for x in _rng.permutation(n)[:k])
    return sorted(_rng.choice(n, size=k, replace=False).tolist())


def _k_positions(n, k, seed=0, nested=False, force=None):
    return _k_positions_base(n, k, seed=seed, nested=nested)


def _use_it(n, k):
    return _k_positions(n, k, nested=True)
'''


# --------------------------------------------------------------- 主流程
def run(probe_path=PROBE_REL):
    fd, tmp = tempfile.mkstemp(suffix="_patched_probe.py")
    os.close(fd)
    L = []
    try:
        make_patched(probe_path, tmp)
        orig = load_by_path(probe_path, "_k_positions")
        new = load_by_path(tmp, "_k_positions")

        grid = []
        for n in (385, 490, 617, 758, 1141, 1156, 1762, 1878, 2210,
                  3200, 3786, 3956, 4161, 5320):
            for frac in (1, 2, 4, 8, 64, 256, 1024):
                k = max(1, n // frac)
                if k < n:
                    grid.append((n, k))

        L.append("【1】J1 行为等价：force=None 时必须与原函数**逐档相同**")
        L.append("  ⚖ 网格 %d 格（14 个真实 n_eff × 7 个档比例）" % len(grid))
        eqT = j1_equiv(orig, new, grid, nested=True)
        eqF = j1_equiv(orig, new, grid, nested=False)
        L.append("  ⚖⚠ **两条路都跑**（补丁改的正是 nested=True 那条 return）")
        for tag, val in (("nested=True ", eqT), ("nested=False", eqF)):
            L.append("    %s ⇒ %s" % (tag, "✅ 逐档全部相同" if val
                                       else "⛔ 有格不等 ⇒ 候选改动破坏既有判据"))
        if not (eqT and eqF):
            return "\n".join(L), 1

        import numpy as np
        L.append("")
        L.append("【2】force 语义（J2/J3/J4/J5）—— 全部在 nested=True 下")
        L.append("  %-8s %-7s %-7s %-8s %-9s %s"
                 % ("n_eff", "k", "读出秩", "|base|", "|forced|", "相差元素数"))
        ok2 = ok3 = ok4 = ok5 = True
        usable = 0
        for n in (385, 490, 758, 1141, 1762, 2210, 3200, 3956, 5320):
            k = max(1, n // 4)
            base = sorted(int(x) for x in new(n, k, nested=True))
            rank = int(np.where(np.random.default_rng(0).permutation(n) == n - 1)[0][0])
            if rank >= k:
                usable += 1
                forced = sorted(int(x) for x in new(n, k, nested=True, force=n - 1))
                ok2 = ok2 and len(forced) == k
                ok3 = ok3 and j3_force_swap(base, forced, k)
                ok4 = ok4 and j4_dropped_is_maxrank(base, forced, n)
                inside = sorted(new(n, k, nested=True, force=base[0]))
                ok5 = ok5 and (inside == base)
                L.append("  %-8d %-7d %-7d %-8d %-9d %d"
                         % (n, k, rank, len(base), len(forced),
                            len(set(base) ^ set(forced)) // 2))
            else:
                L.append("  %-8d %-7d %-7d %-8d %-9s %s"
                         % (n, k, rank, len(base), "—",
                            "读出位点已在基础集内 ⇒ force 无事可做"))
        L.append("  ⚖ 可检验的 n 有 **%d** 个（其余的读出位点本来就在基础集里）" % usable)
        L.append("  J2（force 后位数不变）%s / J3（恰好差一个元素且两边都 k 个）%s"
                 % ("✅" if ok2 else "⛔", "✅" if ok3 else "⛔"))
        L.append("  J4（换掉的是**抽取序里最靠后**的那个）%s / J5（已在集内⇒不动）%s"
                 % ("✅" if ok4 else "⛔", "✅" if ok5 else "⛔"))

        # ⚖⚠ 守卫不能只查嵌套路：非嵌套 + force **必须**抛，否则补丁静默失效。
        try:
            new(1000, 250, nested=False, force=999)
            loud, loud_why = False, "非嵌套 + force **没有报错** ⇒ 静默失效"
        except ValueError:
            loud, loud_why = True, ""
        except Exception as e:
            loud, loud_why = False, "报的不是 ValueError：%s" % type(e).__name__
        L.append("  J6（非嵌套 + force ⇒ **大声报错**，不许静默忽略）%s%s"
                 % ("✅" if loud else "⛔", "" if loud else "：" + loud_why))

        L.append("")
        L.append("【3】J7 抽取契约：三个工具的 `load_k_positions` 抽出来的函数"
                 "**必须真能调**")
        L.append("  ⚖⚠⚠ 第一版这里写的是 `callable(fn)` ⇒ 包装器方案**照过不误**")
        L.append("     （函数对象确实存在），⚖⚠ 而它一调就 NameError。")
        res7 = []
        for m in EXTRACTORS:
            try:
                fn = _extractor(m).load_k_positions(tmp)
                fn = fn[0] if isinstance(fn, tuple) else fn
                good, why = j7_isolated_call(fn)
                res7.append((m, good, why))
            except Exception as e:
                res7.append((m, False, "%s: %s" % (type(e).__name__, str(e)[:44])))
        for m, good, why in res7:
            L.append("  %-26s %s%s" % (m, "✅" if good else "⛔", why))

        # ⚖ 再加一道：抽出来的函数与**原函数**在小网格上必须逐位相同。
        #    ⛔「能调」不等于「算的是同一组位点」—— 那才是三个工具真正在意的。
        drift = []
        try:
            for m in EXTRACTORS:
                fn = _extractor(m).load_k_positions(tmp)
                fn = fn[0] if isinstance(fn, tuple) else fn
                if not j1_equiv(orig, fn, [(997, 249), (2210, 552), (385, 96)],
                                 nested=True):
                    drift.append(m)
        except Exception as e:
            drift.append("抽取异常:%s" % type(e).__name__)
        L.append("  J8（抽出来的与原函数在小网格上**逐位相同**）%s%s"
                 % ("✅" if not drift else "⛔",
                    "" if not drift else "：" + ", ".join(drift)))

        # ⚖⚠⚠⚖ J9 端到端：把模块重指到**打过补丁的探针**，跑三个工具各自的
        #   自检。⚖⚠⚠ 这一关第一版被本工具自己点名「还没验」——
        #   能点名且能补上，就必须补上，否则报告里那句「还没验」就永远在那儿。
        L.append("")
        L.append("【4】J9 端到端：三个工具的自检在**打过补丁的探针**上还绿吗")
        L.append("  ⚖⚠⚠⚠ 陷阱：`def f(p=PROBE)` 的默认值在**定义时**绑定，"
                 "只改模块全局**改不动**它")
        L.append("     ⇒ 那样 J9 会**静默地继续读真探针** ⇒ **恒绿**。"
                 "⚖⚠ 恒绿的 J9 比没有 J9 更危险。")
        res9 = []
        for m in EXTRACTORS:
            try:
                mod = _extractor(m)
                olds, ndef, stuck = rebind_probe(mod.__dict__, tmp)
            except Exception as e:
                res9.append((m, False, "%s: %s" % (type(e).__name__, str(e)[:40])))
                continue
            if stuck:
                res9.append((m, False,
                             "⛔ %d 个默认参数仍指向真探针（%s）⇒ 拒读本工具的结果"
                             % (len(stuck), ",".join(sorted(set(stuck))[:2]))))
                continue
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    rc = mod.selftest(tmp) if m == "dose_axis_audit" else mod.selftest()
            except Exception as e:
                res9.append((m, False, "自检崩了：%s: %s"
                             % (type(e).__name__, str(e)[:40])))
                continue
            o = buf.getvalue()
            np_ = o.count("[PASS]")
            nf = o.count("[FAIL]")
            res9.append((m, (rc == 0 and nf == 0),
                         "自检 %d/%d 通过、%d 失败、rc=%s；"
                         "重指 默认参数 %d 个（源 %s）"
                         % (np_, np_ + nf, nf, rc, ndef,
                            ", ".join(os.path.basename(p) for p in olds) or "—")))
        for m, good, why in res9:
            L.append("  %-26s %s%s" % (m, "✅" if good else "⛔", why))

        allok = (ok2 and ok3 and ok4 and ok5 and loud
                 and all(g for _, g, _ in res7) and not drift
                 and all(g for _, g, _ in res9))
        L.append("")
        L.append("【5】汇总")
        L.append("  ⚖ 候选改动：**%s**"
                 % ("✅ 向后兼容，且 force 语义成立" if allok
                    else "⛔ 不满足要求，⛔ 不得采用"))
        L.append("  ⚖⚠ 本工具⛔ **没有改真探针**，⛔ 没有跑批，也没有批准任何改动。")
        L.append("  ⚖⚠⚠ 仍未验的：J9 只跑了三个工具的**自检**与**位点抽取**；")
        L.append("     ⛔ 真跑 56 格的结果、以及真探针里 `inject_at`/`run()`")
        L.append("     是否会**误传** force，那是 GPU 跑批阶段的事。")
        return "\n".join(L), (0 if allok else 1)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------- 自检
def _base_fn(n, k, seed=0, nested=False):
    """⚖ 夹具：原函数的忠实副本（含 `k==n` 恒等捷径）。"""
    import numpy as np
    n, k = int(n), int(k)
    if k == n:
        return list(range(n))
    if k == 0:
        return []
    if nested:
        return sorted(int(x) for x in np.random.default_rng(int(seed)).permutation(n)[:k])
    return sorted(np.random.default_rng(int(seed)).choice(n, size=n,
                                                          replace=False).tolist()[:k])


def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    _PROBE = PROBE_REL if os.path.exists(PROBE_REL) else None
    tmpdir = tempfile.mkdtemp(prefix="compat_st_")

    # C1 三个锚点必须**各恰好 1**（真探针）
    if _PROBE:
        src = open(_PROBE, encoding="utf-8").read()
        cs = anchor_counts(src)
        chk("C1", all(c == 1 for _, c in cs),
            "锚点 %s（各须恰好 1）" % ", ".join("%s=%d" % (n, c) for n, c in cs))
    else:
        chk("C1", False, "探针源码不可达（%r）⇒ 锚点未验" % PROBE_REL)

    # C2 J1 双向 × **两条路**：同函数⇒过；候选多吐一个⇒不过
    def drift_fn(n, k, seed=0, nested=False):
        if k == n:
            return list(range(n))
        if k == 0:
            return []
        import numpy as np
        p = np.random.default_rng(int(seed)).permutation(n)
        return sorted(int(x) for x in p[:k]) + ([int(p[k])] if k < n else [])

    grid = [(1000, 250), (1000, 500), (2210, 552)]
    chk("C2", all(j1_equiv(_base_fn, _base_fn, grid, nd) is True
                  and j1_equiv(_base_fn, drift_fn, grid, nd) is False
                  for nd in (False, True)),
        "J1：两条路都验（nested=False/True）；同函数⇒过，漂移⇒不过")

    # C3 J3 双向。⚖⚠⚠ 反例必须**各只违反一条**：
    #   原第三例写的是 `[5,9,12,30]`（4 个）⇒ 它同时违反「两边都 k 个」
    #   ⇒ 被**另一条**子句接住 ⇒ 「恰好差一个」那条子句**没有自己的用例**
    #   ⇒ 把它放宽成 `>= 0` 时 C3 照样全绿（变异 Q2 存活）。
    #   ⚗⇒ 每条子句都要有一条「只有它能判」的用例。
    b3, f3 = [5, 9, 12], [5, 9, 19]
    chk("C3", j3_force_swap(b3, f3, 3) is True
        and j3_force_swap(b3, b3, 3) is False
        and j3_force_swap(b3, [5, 19, 30], 3) is False      # 同为 3 个，⛔ 只差 2 个
        and j3_force_swap(b3, [5, 9], 3) is False,         # 位数不符 ⇒ 另一条子句
        "J3：差一个⇒过；相同⇒不过；同为 k 个但差 2 个⇒不过；位数不符⇒不过")

    # C4 ⚠⚠ J4 必须是**真能红**的
    import numpy as np
    N = 1000
    perm = np.random.default_rng(0).permutation(N).tolist()
    kb = max(1, N // 4)
    base = sorted(int(x) for x in perm[:kb])
    worst = max(base, key=lambda j: perm.index(j))
    ok_force = sorted([p for p in base if p != worst] + [N - 1])
    bad_force = sorted([p for p in base if p != base[0]] + [N - 1])
    chk("C4", j4_dropped_is_maxrank(base, ok_force, N) is True
        and j4_dropped_is_maxrank(base, bad_force, N) is False,
        "J4：换掉抽取序最靠后者⇒过；换掉别的⇒不过（worst=%d）" % worst)

    # C5 J4 对「数值最大」必须不过 —— 这正是第一版写错的那条
    num_max = max(base)
    if num_max != worst:
        chk("C5", j4_dropped_is_maxrank(
            base, sorted([p for p in base if p != num_max] + [N - 1]), N) is False,
            "J4：换掉数值最大（%d ≠ 抽取序最靠后 %d）⇒ 必须不过" % (num_max, worst))
    else:
        chk("C5", True, "本 n 下数值最大恰好也是抽取序最靠后 ⇒ 该反例不可构造")

    # ⚖⚠⚠⚖ C6 **抽取契约**这一关必须能红 —— 用合成夹具证明它不是恒绿。
    p_good = os.path.join(tmpdir, "good.py")
    p_bad = os.path.join(tmpdir, "bad.py")
    with open(p_good, "w", encoding="utf-8") as f:
        f.write(SYNTH_PROBE)
    with open(p_bad, "w", encoding="utf-8") as f:
        f.write(SYNTH_WRAPPED)
    try:
        g_ok, g_why = j7_isolated_call(load_by_path(p_good, "_k_positions"))
    except Exception as e:
        g_ok, g_why = False, "%s: %s" % (type(e).__name__, str(e)[:40])
    try:
        b_ok, b_why = j7_isolated_call(load_by_path(p_bad, "_k_positions"))
    except Exception as e:
        b_ok, b_why = False, "%s: %s" % (type(e).__name__, str(e)[:40])
    chk("C6", g_ok is True and b_ok is False,
        "抽取契约：自包含⇒能调（%s）；包装器⇒必须报红，实际 %s"
        % (g_why or "OK", b_why or "居然过了 ⇒ 这一关恒绿"))

    # C6b ⚠⚠ `j7_isolated_call` 里的**位数自证**必须自己有用例。
    #    变异 Q4 把 `if len(out) != k or ...` 改成 `if False:`，
    #    而 C6 只验「能不能调」⇒ 变异**存活** ⛔ 那条自证本来就没被验。
    def wrong_count(n, k, seed=0, nested=False, force=None):
        return list(range(k - 1))
    wc_ok, wc_why = j7_isolated_call(wrong_count)
    chk("C6b", wc_ok is False,
        "位数不符的函数⇒必须判不过（实际 %s）" % (wc_why or "居然过了 ⇒ 位数自证恒绿"))

    # C7 ⚠⚠⚖ 打在**合成夹具**上的补丁，默认路径必须逐位不变。
    p_pat = os.path.join(tmpdir, "pat.py")
    try:
        make_patched(p_good, p_pat)
        f_o = load_by_path(p_good, "_k_positions")
        f_n = load_by_path(p_pat, "_k_positions")
        same = all(j1_equiv(f_o, f_n, grid, nd) for nd in (False, True))
        pf_ok, pf_why = j7_isolated_call(f_n)
        chk("C7", same and pf_ok,
            "合成夹具上打补丁：两条路逐位不变=%s、抽出来能调=%s"
            % (same, pf_why or "OK"))
    except Exception as e:
        chk("C7", False, "补丁在合成夹具上炸了：%s: %s" % (type(e).__name__, str(e)[:40]))

    # C8 锚点非唯一 ⇒ 必须 HardFail（探针形态已变的护栏）
    dup = os.path.join(tmpdir, "dup.py")
    with open(dup, "w", encoding="utf-8") as f:
        # ⚖⚠⚠ 必须重复的是**旧签名本身**，否则命中数仍是 1 ⇒ 这一关测不到东西。
        f.write(SYNTH_PROBE + "\n\n" + SIG_OLD + "\n    return []\n")
    raised = False
    try:
        make_patched(dup, os.path.join(tmpdir, "dup_out.py"))
    except HardFail:
        raised = True
    except Exception:
        raised = False
    chk("C8", raised, "锚点出现 2 处 ⇒ 必须 HardFail（不许悄悄打完）")

    # C9 ⚠⚠⚠ 「只改模块全局」是**无效**的：默认值在 def 时就绑定了。
    #    用**两个互不相干**的命名空间分别演示「天真写法」与「修法」。
    #    ⚖⚠⚠⚠ 必须分开：若先在天真那一侧改了全局，`rebind_probe` 读到的
    #      「旧路径」就变成了**已经覆盖过的那个值** ⇒ 它一个默认参数都改不到
    #      ⇒ 而 `stuck` 还会是空的（它比的是同一个被污染的 olds）
    #      ⛔ 看起来「改成功了」，实际一个都没改。这本身就是同一条教训。
    REAL9 = "REALDIR/r204_noise_probe.py"
    TMP9 = "TMPDIR/r204_noise_probe.py"
    SRC9 = ("PROBE = %r\n"
            "def f(p=PROBE):\n"
            "    return p\n")

    ns_naive = {}
    exec(SRC9 % REAL9, ns_naive)
    ns_naive["PROBE"] = TMP9                 # ⛔ 只改全局（天真写法）
    only_global = ns_naive["f"]() == REAL9   #    期望：仍是真探针 ⇒ 改不动

    ns_fix = {}
    exec(SRC9 % REAL9, ns_fix)
    _o, ndef9, stuck9 = rebind_probe(ns_fix, TMP9)
    chk("C9", only_global and ndef9 >= 1 and not stuck9 and ns_fix["f"]() == TMP9,
        "只改全局 ⇒ 仍读到真探针=%s；改 __defaults__ 后读到 %r（改了 %d 个，"
        "仍卡住 %d 个）" % (only_global, ns_fix["f"](), ndef9, len(stuck9)))

    for p in (p_good, p_bad, p_pat, dup):
        try:
            os.unlink(p)
        except OSError:
            pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass

    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % ", ".join(bad))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="探针改动的兼容性预检（零 GPU）")
    ap.add_argument("--probe", default=PROBE_REL)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    txt, rc = run(args.probe)
    print(txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
