"""pick_hi_sites.py 的本地先验（假数据）。

远端跑一次要加载模型，选材崩在**任何前向之前**纯属浪费；
这 6 组用例本地 5 秒验完。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_pick_hi_sites.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pick_hi_sites as P   # noqa: E402


def expect_raise(fn, needle):
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        assert needle in msg, f"拒绝理由不含 {needle!r}: {msg}"
        return
    raise AssertionError(f"本该拒绝但没拒绝：{needle}")


def fake(n_hi=None):
    """造 58 行假数据：**必须含**修订 22 用过的 p02–p11，否则排除不掉 10 条。

    默认 n_hi 让**字典序前 30 条之和恰好 = 453**（预登记 §28.5 的值）：
    前 30 条是 p12–p41 ⇒ ids 下标 10..39；给 27 条 15、3 条 16 = 405+48 = 453。
    """
    ids = list(range(2, 12)) + list(range(12, 60))      # 10 + 48 = 58
    assert len(ids) == 58, len(ids)
    default = [15] * 58
    for k in (37, 38, 39):                              # p39/p40/p41
        default[k] = 16
    rows = []
    for k, i in enumerate(ids):
        tid = f"aime__aime25__p{i:02d}__think"
        rows.append({"traj": tid,
                     "n_hi": default[k] if n_hi is None else n_hi[k],
                     "n_sites": 100, "frac": 0.1})
    return rows


def fake_n(n):
    """只改条数的版本（供池大小守卫用）。"""
    rows = fake()
    while len(rows) < n:
        rows.append({"traj": f"x{len(rows):03d}", "n_hi": 15,
                     "n_sites": 100, "frac": 0.1})
    return rows[:n]


# ---- 用例 1：正常路径 + 字典序可核对 ----
rows = fake()
# 排除 p02–p11 后剩 p12–p59，字典序前 30 条应是 p12..p41
chosen, sites = P.pick(rows)
assert len(chosen) == 30, len(chosen)
assert chosen[0]["traj"] == "aime__aime25__p12__think", chosen[0]
assert chosen[-1]["traj"] == "aime__aime25__p41__think", chosen[-1]
assert [r["traj"] for r in chosen] == sorted(r["traj"] for r in chosen), "不是字典序"
assert sites == 453, sites
print("用例1 PASS  字典序取前 30 条，边界 p12/p41 正确")

# ---- 用例 2：位点数不等于预登记值 => 拒绝（防选材被悄悄改过）----
rows = fake(n_hi=[9] * 58)          # 30×9 = 270 ≠ 453
expect_raise(lambda: P.pick(rows), "!= 预登记")
print("用例2 PASS  位点数对不上预登记即拒绝")

# ---- 用例 3：池里只剩 9 条修订 22 用过的轨迹 => 拒绝 ----
# ⚠ 不能直接删掉那 10 行：那样会先被「池应为 58 条」那条守卫拦下，
# 测的就不是本条守卫了。正确造法是**替换**一条，保持条数不变。
rows = fake()
tgt = next(r for r in rows if r["traj"] in P.USED_IN_REV22)
tgt["traj"] = "aime__aime25__p99__think"
assert len(rows) == 58
n_used = sum(1 for r in rows if r["traj"] in P.USED_IN_REV22)
assert n_used == 9, n_used
expect_raise(lambda: P.pick(rows), "应有 10 条修订 22 用过的轨迹")
print("用例3 PASS  只认得出 9 条已用轨迹即拒绝")

# ---- 用例 4：条数不对 => 拒绝 ----
expect_raise(lambda: P.pick(fake_n(57)), "轨迹池应为 58")
expect_raise(lambda: P.pick(fake_n(60)), "轨迹池应为 58")
print("用例4 PASS  池不是 58 条即拒绝")

# ---- 用例 5：frac 不得影响排序（按 frac 排是最隐蔽的挑结果）----
rows = fake()
# 把字典序最靠前的几条 frac 设成最大：若实现偷偷按 frac 排，选中集合会变
for r in rows[:5]:
    r["frac"] = 999.0
chosen2, sites2 = P.pick(rows)
assert sites2 == 453, sites2
assert [r["traj"] for r in chosen2] == [r["traj"] for r in chosen], \
    "frac 影响了选材 —— 选材规则被污染"
print("用例5 PASS  frac 全部置为最大也不影响选材")

# ---- 用例 6：n_hi > n_sites（同一行取的两个数不自洽）=> 拒绝 ----
# ⚠ 必须打在**会被选中**的那一行上：打在 p02 上会被排除规则先剔掉，
# 断言根本没机会跑 —— 那种「测了但没测到」的假通过比失败更糟。
rows = fake()
tgt = next(r for r in rows if r["traj"] == "aime__aime25__p12__think")
assert tgt["traj"] not in P.USED_IN_REV22
tgt["n_hi"], tgt["n_sites"] = 200, 100
expect_raise(lambda: P.pick(rows), "拒绝选材")
print("用例6 PASS  n_hi>n_sites 即拒绝")

# ---- 用例 7：常量与预登记一致 ----
assert (P.N_TRACKS, P.ORTH_THRESHOLD, P.EXPECT_POOL, P.EXPECT_SITES) \
    == (30, 0.1, 48, 453), "选材常量被改动"
assert len(P.USED_IN_REV22) == 10, P.USED_IN_REV22
print("用例7 PASS  选材常量与预登记 §28.1/§28.5 一致")

print("\n全部先验通过：7 组用例 / 5 条拒绝路径")
