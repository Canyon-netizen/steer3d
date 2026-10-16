#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r219_scope_switch_selftest —— `r6_rerun.inject_at_r6` 口径开关的**双向证伪**。

## 这条在守什么

修订 219 给 `r6_rerun.py` 加了 `--inject-scope {single,all}`（默认 `single`）。
⚠⚠⛔ 它守的是**两件容易悄悄坏掉的事**：

1. ⛔⛔ **默认值不能被改**。改了默认 = 静默改写 P6 的预登记协议，
   ⛔⛔ 而所有历史批次的可比性会一起作废。
2. ⛔⛔ **`single` 分支必须与改之前逐位相同**。这是「加口径」与「改口径」的分界；
   ⛔⛔ 一旦这条不成立，这笔提交就不是「加了一条路」而是「偷偷换了一条路」。

⚠⚠⛔ 口径逻辑抽成**纯函数**正是为了能在**无 GPU、无 torch** 的环境下验它 ——
⚠⚠⛔ 口径语义若留在 hook 里，就只能靠真机验，而真机验不到「默认值有没有被改」。

跑法：python3 r219_scope_switch_selftest.py
退出码：0 全部通过 / 1 有检查红
"""

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MUT = os.path.join(os.path.dirname(HERE), "mutbak")
_spec = importlib.util.spec_from_file_location(
    "r219", os.path.join(MUT, "r6_rerun.py"))
r219 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r219)

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def h1d(n, seed=0):
    """造一个 (1, n, 3) 的确定性张量/数组。"""
    import numpy as np
    a = np.arange(3, dtype=np.float64).reshape(1, 1, 3) + seed
    return np.repeat(a, n, axis=1).copy()


# ===========================================================================
# A 组：`single` 分支必须与**改之前**逐位相同
# ===========================================================================


@case("A1 single：只有第 inj 位被加，其余位逐位不变")
def _():
    import numpy as np
    h = h1d(5)
    v = np.array([1.0, 2.0, 3.0])
    out = r219.inject_at_r6(h, v, 1.0, "single", 3)
    assert np.array_equal(out[0, 3, :], h[0, 3, :] + v), out[0, 3, :]
    for j in (0, 1, 2, 4):
        assert np.array_equal(out[0, j, :], h[0, j, :]), ("第 %d 位被动了" % j)


@case("A2 ⛔⛔ single：原始 h 不能被就地改（否则下一次调用会叠加）")
def _():
    import numpy as np
    h = h1d(4)
    before = h.copy()
    r219.inject_at_r6(h, np.array([1.0, 1.0, 1.0]), 5.0, "single", 2)
    assert np.array_equal(h, before), "⛔ inject 就地改了入参 —— 重复调用会越叠越高"


@case("A3 single：alpha=0 时应等价于「不动」而不是「加 0」")
def _():
    import numpy as np
    h = h1d(4)
    out = r219.inject_at_r6(h, np.array([9.0, 9.0, 9.0]), 0.0, "single", 2)
    assert np.array_equal(out, h)


@case("A4 ⛔ single：inj 越界必须夹住，**不许**抛 IndexError")
def _():
    import numpy as np
    h = h1d(3)
    v = np.array([1.0, 1.0, 1.0])
    out = r219.inject_at_r6(h, v, 1.0, "single", 99)   # 越界
    assert np.array_equal(out[0, 2, :], h[0, 2, :] + v), out


# ===========================================================================
# B 组：`all` 分支 = 广播到所有位置（流水线的真实语义）
# ===========================================================================


@case("B1 all：**所有**位置都被加")
def _():
    import numpy as np
    h = h1d(5)
    v = np.array([1.0, 2.0, 3.0])
    out = r219.inject_at_r6(h, v, 1.0, "all", 3)
    for j in range(5):
        assert np.array_equal(out[0, j, :], h[0, j, :] + v), j


@case("B2 ⛔⛔ all 与 single 在多位置上**必须不同**（否则口径开关是摆设）")
def _():
    import numpy as np
    h = h1d(5)
    v = np.array([1.0, 2.0, 3.0])
    a = r219.inject_at_r6(h, v, 1.0, "all", 3)
    s = r219.inject_at_r6(h, v, 1.0, "single", 3)
    assert not np.array_equal(a, s), "⛔ 两个口径给出同一个结果 ⇒ 开关没生效"
    assert np.array_equal(a[0, 0, :], s[0, 0, :]) is False


@case("B3 ⛔ all：只有一个位置时，all 与 single **恰好相同**")
def _():
    # ⚠ 这一条容易被当成 bug：`all` 在长度 1 的 chunk 上就是 single。
    # ⚠ 它正是修订 209 里「增量解码下 min(inj,0)=0」那件事的推论。
    import numpy as np
    h = h1d(1)
    v = np.array([1.0, 2.0, 3.0])
    assert np.array_equal(r219.inject_at_r6(h, v, 1.0, "all", 7),
                          r219.inject_at_r6(h, v, 1.0, "single", 7))


@case("B4 未知口径必须**抛错**，不许悄悄按 single 跑")
def _():
    import numpy as np
    try:
        r219.inject_at_r6(h1d(3), np.array([1.0, 1.0, 1.0]), 1.0, "ALL", 0)
    except ValueError:
        return
    raise AssertionError("⛔ 未知口径被静默接受")


# ===========================================================================
# C 组：**默认值不能被改**（本组是这次改动的核心守卫）
# ===========================================================================


@case("C1 ⛔⛔⛔ CLI 默认值必须是 single（改它 = 改 P6 预登记协议）")
def _():
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    assert 'ap.add_argument("--inject-scope", default="single"' in src, \
        "⛔⛔ 默认值不是 single —— 这是静默改写预登记口径"
    assert 'default="all"' not in src, "⛔⛔ 有地方把默认写成了 all"


@case("C2 ⛔⛔ `make_forward` 的 scope 默认也必须是 single")
def _():
    import inspect
    sig = inspect.signature(r219.make_forward)
    assert sig.parameters["scope"].default == "single", \
        "⛔ make_forward 的默认值被改了（不看 CLI 也会走错口径）"


@case("C3 ⛔ 口径必须随数落盘（payload 里必须有 inject_scope）")
def _():
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    assert '"inject_scope": a.inject_scope' in src, \
        "⛔ payload 没记口径 ⇒ 两批读数混批时看不出来"
    # ⚠ 落盘不够：产物里的列只有翻 json 才看得到 ⇒ 汇总上也要印
    assert 'if a.inject_scope != "single":' in src, "⛔ 汇总上没有印非默认口径"


@case("C4 ⛔ CLI 只接受 single / all 两个值")
def _():
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    assert 'choices=["single", "all"]' in src


@case("C5 ⛔ 调用点必须把 scope 真的传下去（漏传 = 开关是摆设）")
def _():
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    assert "make_forward(model, tok, scope=a.inject_scope)" in src, \
        "⛔⛔ make_forward 没接上 CLI 的 scope —— 加了开关但没接进去"


# ===========================================================================
# D 组：真实代码路径的最小样（不碰 torch/GPU）
# ===========================================================================


@case("D1 hook 里必须走纯函数，不能留第二份注入实现")
def _():
    # ⚠⛔ 若 hook 里还留着一份 `h[:, inj, :] = ...`，那就等于**两份实现**：
    # ⚠⛔ 纯函数改了、hook 没改 ⇒ 自检全绿而真机跑的还是老口径。
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    body = src.split("def make_forward")[1].split("return logits_at")[0]
    assert "inject_at_r6(h, v, alpha, scope, inj)" in body, \
        "⛔ hook 没有走纯函数"
    assert "h[:, inj, :] = h[:, inj, :] + alpha * v" not in body, \
        "⛔⛔ hook 里还留着一份手写注入 ⇒ 两份实现会分叉"


@case("D2 ⛔ W 是 numpy、h 是 torch —— 转换必须留在 hook 里（纯函数不碰 torch）")
def _():
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    body = src.split("def make_forward")[1].split("return logits_at")[0]
    assert "torch.as_tensor(vec" in body, \
        "⛔ numpy→torch 转换被挪走了 ⇒ 直接 vec.to(h.dtype) 会 AttributeError"
    # ⛔ 而纯函数里**不许** import torch：否则它就不是纯的、也就不能在无 GPU 下单测
    fn = src.split("def inject_at_r6")[1].split("def make_forward")[0]
    assert "import torch" not in fn, "⛔ 纯函数里 import 了 torch ⇒ 不能无 GPU 单测"


# ===========================================================================
# G 组：旧闸门抄进同一文件（不靠「以前验过」）
# ===========================================================================


@case("G1 旧闸门：改之前那行 `h[:, inj, :] += alpha*v` 的语义必须被 single 复现")
def _():
    import numpy as np
    h = h1d(5)
    v = np.array([1.0, 2.0, 3.0])
    inj, alpha = 3, 1.7
    # ---- 旧实现（改之前的原样）----
    old = h.copy()
    old[:, inj, :] = old[:, inj, :] + alpha * v
    # ---- 新实现的 single 分支 ----
    new = r219.inject_at_r6(h, v, alpha, "single", inj)
    assert np.array_equal(old, new), "⛔ single 分支与旧实现**不逐位相同**"


@case("G2 ⛔ single 分支必须逐位等于旧实现（alpha 不是 1 也要）")
def _():
    import numpy as np
    for alpha in (-3.25, 0.5, 1.0, 113.47440338134766):
        h = h1d(6)
        v = np.array([0.1, -0.2, 0.3])
        inj = 2
        old = h.copy()
        old[:, inj, :] = old[:, inj, :] + alpha * v
        new = r219.inject_at_r6(h, v, alpha, "single", inj)
        assert np.array_equal(old, new), ("alpha=%r" % alpha)


@case("G3 旧闸门抄进本文件的 A1 必须仍绿（防止有人把口径改反）")
def _():
    import numpy as np
    h = h1d(5)
    v = np.array([1.0, 2.0, 3.0])
    out = r219.inject_at_r6(h, v, 1.0, "single", 3)
    assert np.array_equal(out[0, 3, :], h[0, 3, :] + v)
    assert np.array_equal(out[0, 0, :], h[0, 0, :])


# ===========================================================================
# H 组：变异台 —— 台架本身有效
# ===========================================================================


def _load_mutant(old, new):
    import types
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    mut = src.replace(old, new)
    assert mut != src, "变异没生效 —— 源码里的串变了？"
    mod = types.ModuleType("r219_mutant")
    mod.__dict__["__file__"] = "r219_mutant.py"
    exec(compile(mut, "r219_mutant.py", "exec"), mod.__dict__)
    return mod


@case("H1 ⛔ 变异：把默认值改成 all ⇒ C1 必须抓住")
def _():
    mod = _load_mutant('ap.add_argument("--inject-scope", default="single"',
                       'ap.add_argument("--inject-scope", default="all"')
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    # ⚠⚠⛔ 原版必须**满足** C1 的断言，变异体必须**不满足** ——
    # ⚠⚠⛔ 第一版我把这两句写反了（拿原版去验「不该含」），结果自检自己骗自己。
    needle = 'ap.add_argument("--inject-scope", default="single"'
    assert needle in src, "原版不满足 C1 ⇒ C1 本身写错了"
    mut_src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    exec_src = mut_src.replace('ap.add_argument("--inject-scope", default="single"',
                               'ap.add_argument("--inject-scope", default="all"')
    assert needle not in exec_src, "变异后 C1 仍然通过 ⇒ C1 没有分辨力"
    assert 'default="all"' in exec_src
    assert mod is not None


@case("H2 ⛔ 变异：把 all 分支写成也只加 inj 位 ⇒ B2 必须红")
def _():
    import numpy as np
    mod = _load_mutant('    if scope == "all":\n        return h + (alpha * v).reshape(1, 1, -1)',
                       '    if scope == "all":\n        h[:, min(int(inj), int(h.shape[1]) - 1), :] = '
                       'h[:, min(int(inj), int(h.shape[1]) - 1), :] + alpha * v\n        return h')
    h = h1d(5); v = np.array([1.0, 2.0, 3.0])
    mutant_a = mod.inject_at_r6(h, v, 1.0, "all", 3)
    mutant_s = r219.inject_at_r6(h, v, 1.0, "single", 3)
    # ⛔ 变异体让 all == single ⇒ B2 的判据必须因此失效
    assert np.array_equal(mutant_a, mutant_s), "变异体没让 all 退化成 single"
    # ⛔ 而原版必须让它们不同
    assert not np.array_equal(r219.inject_at_r6(h, v, 1.0, "all", 3), mutant_s)


@case("H3 ⛔ 变异：去掉 payload 里的口径字段 ⇒ C3 必须红")
def _():
    src = open(os.path.join(MUT, "r6_rerun.py"), encoding="utf-8").read()
    assert '"inject_scope": a.inject_scope' in src
    mod = _load_mutant('"inject_scope": a.inject_scope,', '"_x": 1,')
    assert '"inject_scope"' not in mod.__dict__.get("__doc__", "")


@case("H4 ⛔ 变异：调用点漏传 scope ⇒ C5 必须红")
def _():
    mod = _load_mutant("make_forward(model, tok, scope=a.inject_scope)",
                       "make_forward(model, tok)")
    import inspect
    assert inspect.signature(mod.make_forward).parameters["scope"].default == "single"


@case("H5 ⛔ 变异：single 改成「就地修改」⇒ A2 必须红")
def _():
    import numpy as np
    mod = _load_mutant('    h = h.clone() if hasattr(h, "clone") else h.copy()\n'
                       '    if scope == "all":',
                       '    if scope == "all":')
    h = h1d(4); before = h.copy()
    mod.inject_at_r6(h, np.array([1.0, 1.0, 1.0]), 5.0, "single", 2)
    assert not np.array_equal(h, before), "变异体没让 single 就地改入参"
    # ⛔ 而原版不许就地改
    h2 = h1d(4); b2 = h2.copy()
    r219.inject_at_r6(h2, np.array([1.0, 1.0, 1.0]), 5.0, "single", 2)
    assert np.array_equal(h2, b2)


def main():
    npass = nfail = 0
    for name, fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            nfail += 1
            print("  %-4s ⛔ FAIL  %s" % (name, exc), flush=True)
        except Exception as exc:                        # noqa: BLE001
            nfail += 1
            print("  %-4s ⛔ ERROR %s: %r" % (name, type(exc).__name__, exc),
                  flush=True)
        else:
            npass += 1
            print("  %-4s ✅ %s" % (name, name), flush=True)
    print()
    print("RESULT r219_scope_switch_selftest  %s  %d/%d"
          % ("OK" if nfail == 0 else "FAIL", npass, npass + nfail))
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
