"""ortho_nt_scan.py 的本地先验（假数据，不碰任何真产物、不用 GPU）。

⚠ 显式 raise，不用 `assert` —— `python -O` 会关掉 assert。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortho_nt_scan import ORTH_MIN, pick_top_decile, scan_one   # noqa: E402

FAILS = []
HERE = os.path.dirname(os.path.abspath(__file__))


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f" {detail}"))
    if not cond:
        FAILS.append(name)


def W():
    v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    return v / np.linalg.norm(v)


print("\n=== 1. pick_top_decile：先取十分位、再过边界 ===")
# 10 个位点 ⇒ k = 1 ⇒ 只取 |w| 最大的那个。
# ⚠ 系数必须让最大值**严格大于** ORTH_MIN：0.01*10 = 0.1 恰在边界上，
#    按「先取十分位再过边界」会被正确丢弃 —— 第一版就写成了 0.01，
#    于是期望「取 t=10」而实得空，**是用例错了不是代码错了**。
p = [(i, 0.02 * i) for i in range(1, 11)]
got = pick_top_decile(p)
ok("10 点取 k=1", len(got) == 1, got)
ok("取的是 |w| 最大的那个", got[0][0] == 10, got)

# 边界上那个恰好被丢：k=1 选中 t=10(|w|=0.1)，过边界后空
ok("边界上的值过不去（k=1 时整批归零）",
   pick_top_decile([(i, 0.01 * i) for i in range(1, 11)]) == [])

# k=3，但只有 1 个过边界
p = [(1, 0.9), (2, 0.05), (3, 0.02), (4, 0.01)]
got = pick_top_decile(p)
ok("k=1 时只有 |w|=0.9 过边界", [t for t, _ in got] == [1], got)

# ⚠ 顺序不能反：先过边界会把分母缩小，取到的就不是「最高十分位」。
#    要 k=2 必须 n≥20（k = max(1, int(n*0.1))）—— 第一版只给 4 个点，
#    k 其实是 1，期望写成 [1,2] 是**用例算错了 k**。
n = 20
p = [(1, 0.9), (2, 0.8)] + [(i, 0.05 - i / 1000) for i in range(3, n + 1)]
k = max(1, int(n * 0.10))
ok("用例自洽：k=2", k == 2, k)
got = pick_top_decile(p)
ok("先取十分位：低 |w| 的位点不进 top",
   [t for t, _ in got] == [1, 2], got)

print("\n=== 2. 边界是严格 > ===")
p = [(1, 0.10), (2, 0.1000001)]
got = pick_top_decile(p)
ok("0.10 被丢弃、0.1000001 保留", [t for t, _ in got] == [2], got)
ok("ORTH_MIN 就是 0.10", ORTH_MIN == 0.10, ORTH_MIN)

print("\n=== 3. 保序 ===")
# ⚠ k 必须由**列表实际长度**决定（k = max(1, int(len(p)*0.1))），
#    不能由「本来打算放几个」那个变量算 —— 第一版拿 n=30 算 k=3，
#    可夹具因为排除了 17/29 只有 28 个点，实际 k=2，期望又错了一次。
#    要 k=3 ⇒ 长度必须落在 [30, 39]。
specials = [(29, 0.9), (3, 0.8), (17, 0.7)]
filler = [(i, 0.01 * i) for i in range(4, 33) if i not in (17, 29)]
p = specials + filler
k = max(1, int(len(p) * 0.10))
ok("用例自洽：k=3（由 len(p)=%d 算出）" % len(p), k == 3, k)
ok("夹具无重复 t", len({t for t, _ in p}) == len(p), len(p))
got = pick_top_decile(p)
ok("取到的是 |w| 最大的三个（按 t 升序）",
   [t for t, _ in got] == [3, 17, 29], [t for t, _ in got])
ok("返回按 t 升序", [t for t, _ in got] == sorted(t for t, _ in got), got)

print("\n=== 4. 空输入 ===")
ok("空输入返回空", pick_top_decile([]) == [])


def fake_root(tmp, tid, mode, tok_ids, T=12, L=28, D=4, hs_fn=None):
    d = os.path.join(tmp, "gen_b2", "aime")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{tid}.json"), "w", encoding="utf-8") as f:
        json.dump({"config": {"mode": mode},
                   "tokens": [{"token_id": i} for i in tok_ids]}, f)
    hs = np.zeros((T, L, D), dtype=np.float32)
    if hs_fn:
        hs_fn(hs)
    np.savez(os.path.join(d, f"{tid}.npz"), hidden_states=hs)


print("\n=== 5. scan_one 基本通 + t=0 跳过 ===")
with tempfile.TemporaryDirectory() as tmp:
    # marker 在 i=0,1,2 ⇒ 全部 aw=1.0（h 指向 w 方向），k=max(1,int(3*.1))=1
    fake_root(tmp, "x__no_think", "no_think", [13824, 13824, 13824])

    def fill(hs):
        hs[:, NPZ if False else 19, 0] = 1.0        # 第 19 层第 0 维为正

    fake_root(tmp, "y__no_think", "no_think", [13824, 13824, 13824], hs_fn=fill)
    r = scan_one(tmp, "y__no_think", W())
    ok("mode 读回", r["mode"] == "no_think", r["mode"])
    ok("3 个 marker 位点", r["n_sites"] == 3, r["n_sites"])
    ok("n_hi=3（t=0 的位点跳过，只剩 2 个可算）", r["n_hi"] == 2, r)
    ok("t=0 不在清单里", all(s["t"] != 0 for s in r["sites"]), r["sites"])
    ok("aw_max≈1", abs(r["aw_max"] - 1.0) < 1e-5, r["aw_max"])

print("\n=== 6. 没有 marker 位点 ⇒ 0 且带 note，不崩 ===")
with tempfile.TemporaryDirectory() as tmp:
    fake_root(tmp, "z__no_think", "no_think", [1, 2, 3])
    r = scan_one(tmp, "z__no_think", W())
    ok("sites 为空", r["sites"] == [])
    ok("有 note", "marker" in r.get("note", ""), r)

print("\n=== 6b. 有 marker 但十分位全被绝对边界剔掉 ⇒ 也要带 note ===")
# ⚠ 这是远端首跑就崩的那条路径：sites 为空有两种原因（没有 marker /
#    边界剔光），第一版只给一种 note，调用方直接 KeyError。
with tempfile.TemporaryDirectory() as tmp:
    # h 指向 -w 方向 ⇒ w·ĥ = -1 ⇒ |w·ĥ| = 1 > 0.1，**不会**被剔 ⇒ 改用垂直方向
    def perpendicular(hs):
        hs[:, 19, 1] = 1.0          # 第 1 维，w 只在第 0 维 ⇒ w·ĥ = 0

    fake_root(tmp, "p__no_think", "no_think", [13824] * 10, hs_fn=perpendicular)
    r = scan_one(tmp, "p__no_think", W())
    ok("sites 为空", r["sites"] == [], r["sites"])
    ok("note 说清是边界剔的，不是没有 marker",
       "绝对边界" in r.get("note", "") or "aw 最大" in r.get("note", ""),
       r.get("note"))
    ok("note 非空（任何空情形都必须有原因）", bool(r.get("note")), r)
    # 关键：note 键**必须存在**，不能靠调用方 .get 兜底掩盖
    ok("note 是键而不是缺省", "note" in r, list(r))


print("\n=== 7. 维度守卫：层数不对必须炸 ===")
with tempfile.TemporaryDirectory() as tmp:
    fake_root(tmp, "bad__no_think", "no_think", [13824, 13824], L=12)
    try:
        scan_one(tmp, "bad__no_think", W())
        ok("层数不对抛错", False, "竟然没抛")
    except SystemExit as e:
        ok("层数不对抛 SystemExit", "!= 28" in str(e), str(e))
    fake_root(tmp, "bad2__no_think", "no_think", [13824, 13824], L=28, D=4)
    # 人为造一个 2 维数组
    d = os.path.join(tmp, "gen_b2", "aime")
    np.savez(os.path.join(d, "bad2__no_think.npz"), hidden_states=np.zeros((12, 4)))
    try:
        scan_one(tmp, "bad2__no_think", W())
        ok("维度不对抛错", False, "竟然没抛")
    except SystemExit as e:
        ok("维度不对抛 SystemExit", "维度" in str(e), str(e))

print("\n=== 8. CLI：--mode 白名单 + --expect-pool 不符就拒 ===")
with tempfile.TemporaryDirectory() as tmp:
    d = os.path.join(tmp, "gen_b2", "aime")
    os.makedirs(d)
    # 只放 json（不放 npz），CLI 只数候选不加载
    for t in ("a__no_think", "b__no_think", "c__think"):
        with open(os.path.join(d, f"{t}.json"), "w", encoding="utf-8") as f:
            json.dump({"config": {"mode": t.split("__")[1]},
                       "tokens": []}, f)

    def run(args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "ortho_nt_scan.py")] + args,
            capture_output=True, text=True)

    r = run(["--root", tmp, "--mode", "bogus", "--out", os.path.join(tmp, "o.json")])
    ok("非法 mode 被拒", r.returncode != 0 and "invalid choice" in r.stderr,
       r.stderr.strip()[-100:])
    r = run(["--root", tmp, "--mode", "no_think", "--out",
             os.path.join(tmp, "o.json"), "--expect-pool", "99"])
    ok("expect-pool 不符 → 拒", r.returncode != 0 and "实际 2" in r.stderr,
       r.stderr.strip()[-120:])
    ok("拒时不落盘", not os.path.exists(os.path.join(tmp, "o.json")))

print("\n=== 9. 键集合恒定：无论走哪条分支 ===")
# ⚠ 这是同一函数的**第二次** KeyError（第一条是缺 note、第二条是缺 n_hi）。
#    两处都在「另一条返回路径」上 —— 一条路径永远测不到另一条。
#    ⇒ 结构性的守卫：不同分支产出的记录，键集合必须**完全相同**。
with tempfile.TemporaryDirectory() as tmp:
    keysets = set()

    def perp(hs):
        hs[:, 19, 1] = 1.0

    # 分支 A：没有 marker 位点
    fake_root(tmp, "a__no_think", "no_think", [1, 2, 3])
    keysets.add(tuple(sorted(scan_one(tmp, "a__no_think", W()))))
    # 分支 B：有 marker，但十分位全被边界剔掉
    fake_root(tmp, "b__no_think", "no_think", [13824] * 10, hs_fn=perp)
    keysets.add(tuple(sorted(scan_one(tmp, "b__no_think", W()))))
    # 分支 C：正常有产出
    def along(hs):
        hs[:, 19, 0] = 1.0

    fake_root(tmp, "c__no_think", "no_think", [13824] * 10, hs_fn=along)
    keysets.add(tuple(sorted(scan_one(tmp, "c__no_think", W()))))

    ok("三条分支键集合完全相同", len(keysets) == 1, keysets)
    need = {"traj", "mode", "n_sites", "n_hi", "aw_max", "note", "sites"}
    ok("必需键都在", need <= set(next(iter(keysets))),
       need - set(next(iter(keysets))))

print()
if FAILS:
    print(f"✗ {len(FAILS)} 条不过：{FAILS}")
    sys.exit(1)
print("✓ ortho_nt_scan.py 全部先验通过")