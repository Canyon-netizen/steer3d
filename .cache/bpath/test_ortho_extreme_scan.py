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


def mk(n, step=0.01, start=0.15):
    """造 n 个 (t, w)，w 从 start 线性升高到 start+step*n。

    ⚠ 默认起点 **0.15**：必须高于绝对边界 0.1（修订 32），
    否则夹具造出来的位点会被边界全滤掉、用例假装失败。
    """
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

# ---- 用例 4b：绝对边界（修订 32）----
# 整条轨迹都很低对齐 ⇒ 十分位里的 |w·ĥ| 仍 < 0.1 ⇒ 全部被边界滤掉
low = [(i, 0.01 + 0.0005 * i) for i in range(100)]   # |w| 上界 0.0595，整条都在边界下
assert S.pick_top_decile(low) == [], "低对齐轨迹不该产出极对齐位点"
# 一半高一半低：十分位全在高的一半 ⇒ 边界不改变结果
mixed = [(i, 0.5) for i in range(50)] + [(i, 0.02) for i in range(50, 100)]
got = S.pick_top_decile(mixed)
assert len(got) == 10 and all(abs(w) > 0.1 for _, w in got), got
# 边界恰好在 0.1 上：|w|=0.1 不算（严格大于）
edge = [(i, 0.1) for i in range(100)]
assert S.pick_top_decile(edge) == [], "|w|=0.1 应被边界排除（严格大于）"
print("用例4b PASS  绝对边界 |w·ĥ|>0.1：低对齐轨迹产出空、边界值 0.1 被排除")

# ---- 用例 5：空输入返回空，不抛 ----
assert S.pick_top_decile([]) == []
print("用例5 PASS  空输入返回空")

# ---- 用例 6：常量与预登记 §30.3 一致 ----
assert (S.DECILE, S.NPZ, S.EXPECT_POOL, S.ORTH_MIN) == (0.10, 19, 28, 0.10), \
    "常量被改动"
assert S.ORTH_MIN == 0.10, "绝对边界必须是 0.1（与 §24 的正交边界同一个）"
assert len(S.MK) == 7, S.MK
print("用例6 PASS  常量与 §30.3 一致（十分位 0.10 / npz 第 19 层 / 池 28 条）")

print("\n全部先验通过：6 组用例")
