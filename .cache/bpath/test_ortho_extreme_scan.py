"""ortho_extreme_scan.py 的本地先验（假数据，不碰任何真产物）。

远端跑一次要读 28 个 0.88 GiB 的 npz（几十分钟），选材崩在**任何前向之前**
纯属浪费。这几组用例本地秒级验完。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_ortho_extreme_scan.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ortho_extreme_scan as S   # noqa: E402


def expect_raise(fn, needle):
    try:
        fn()
    except SystemExit as e:
        assert needle in str(e), f"拒绝理由不含 {needle!r}: {e}"
        return
    raise AssertionError(f"本该拒绝但没拒绝：{needle}")


def mk(n, step=0.01, start=0.05):
    """造 n 个 (t, w)，w 从 start 线性升高到 start+step*n。"""
    return [(i, start + step * i) for i in range(n)]


# ---- 用例 1：十分位的个数 ----
for n, want in ((80, 8), (85, 8), (177, 17), (28, 2), (5, 1), (1, 1)):
    got = len(S.pick_top_decile(mk(n)))
    assert got == want, f"n={n} 时取 {got} 个，期望 {want}"
print("用例1 PASS  十分位个数 = max(1, floor(n*0.10))，含 n<10 的下限")

# ---- 用例 2：取的是**最高**的那几个，而不是最低的 ----
pairs = [(i, float(i)) for i in range(100)]        # w 从 0 升到 99
top = S.pick_top_decile(pairs)
assert len(top) == 10
assert min(w for _, w in top) == 90.0, sorted(w for _, w in top)
print("用例2 PASS  取的是 |w| 最高的一档")

# ---- 用例 3：负的 w 也按**绝对值**排（|w| 大的才是「对齐好」）----
pairs = [(i, -float(i)) for i in range(100)]       # 全是负的
top = S.pick_top_decile(pairs)
assert min(abs(w) for _, w in top) == 90.0
print("用例3 PASS  负 w 也按 |w| 排序，没退化成按 w 排序")

# ---- 用例 4：并列时按 t 升序，保证同样的输入必得同样的清单 ----
pairs = [(5, 0.3), (3, 0.3), (9, -0.3), (1, 0.3), (7, 0.3)]
got = S.pick_top_decile(pairs, decile=0.5)         # k = max(1, int(5*0.5)) = 2
# |w| 全同 ⇒ 并列规则按 t 升序：先取 (1,0.3),(3,0.3)，再按 t 保序输出
assert [t for t, _ in got] == [1, 3], got
assert S.pick_top_decile(list(reversed(pairs)), decile=0.5) == got, \
    "输入顺序不同却得到不同清单 ⇒ 选材不可复算"
print("用例4 PASS  并列时按 t 升序；打乱输入顺序结果不变（可复算）")

# ---- 用例 5：空输入返回空，不抛 ----
assert S.pick_top_decile([]) == []
print("用例5 PASS  空输入返回空")

# ---- 用例 6：常量与预登记 §30.3 一致 ----
assert (S.DECILE, S.NPZ, S.EXPECT_POOL) == (0.10, 19, 28), "常量被改动"
assert len(S.MK) == 7, S.MK
print("用例6 PASS  常量与 §30.3 一致（十分位 0.10 / npz 第 19 层 / 池 28 条）")

print("\n全部先验通过：6 组用例")
