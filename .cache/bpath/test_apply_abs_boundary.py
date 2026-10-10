"""apply_abs_boundary.py 的本地先验（假数据，不碰任何真产物）。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_apply_abs_boundary.py

⚠ 全部用显式 raise，不用 `assert` —— `python -O` 会关掉 assert，
守卫就静默失效（本项目 bpath 工具链的既定纪律）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_abs_boundary import ORTH_MIN, apply_boundary   # noqa: E402

FAILS = []


def ok(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def pick_of(*tracks):
    return {"schema": "extreme_pick/1", "decile": 0.1, "tracks": list(tracks)}


def site(t, aw):
    return {"t": t, "w": aw * 0.5, "aw": aw}


print("\n=== 1. 基本过滤：只留 aw > 0.10 ===")
p = pick_of({"traj": "A", "n_sites": 20,
             "sites": [site(1, 0.05), site(2, 0.11), site(3, 0.30),
                       site(4, 0.10), site(5, 0.09)]})
kept, dropped = apply_boundary(p)
ok("只留 2 个", len(kept) == 1 and kept[0]["n_kept"] == 2, kept)
ok("位点是 t=2,3",
   [s["t"] for s in kept[0]["sites"]] == [2, 3],
   [s["t"] for s in kept[0]["sites"]])
ok("保序（按 t 升序）",
   [s["t"] for s in kept[0]["sites"]] == sorted(s["t"] for s in kept[0]["sites"]))

print("\n=== 2. 边界是严格 >：aw 恰为 0.10 不算高对齐 ===")
p = pick_of({"traj": "A", "n_sites": 3, "sites": [site(1, 0.10), site(2, 0.10)]})
kept, dropped = apply_boundary(p)
ok("0.10 被丢弃", len(kept) == 0)
ok("轨迹进 dropped", len(dropped) == 1 and dropped[0]["traj"] == "A")
ok("dropped 记了十分位位数", dropped[0]["decile_n"] == 2, dropped[0])

print("\n=== 3. 零位点轨迹被丢，且不静默 ===")
p = pick_of({"traj": "LO", "n_sites": 5,
             "sites": [site(i, 0.03) for i in range(5)]},
            {"traj": "HI", "n_sites": 5,
             "sites": [site(i, 0.2 + i / 100) for i in range(5)]})
kept, dropped = apply_boundary(p)
ok("只留 HI", [t["traj"] for t in kept] == ["HI"], [t["traj"] for t in kept])
ok("dropped 只记 LO", [d["traj"] for d in dropped] == ["LO"])
ok("LO 的十分位位数记下来", dropped[0]["decile_n"] == 5)
# ⚠ 断言只抓语义片段，不逐字比对整句 —— 逐字比对让改个措辞就红，
#    就会有人去迁就断言而不是让理由文本更好读。
ok("LO 有原因文本（说清是哪个边界没过来）",
   "最高十分位" in dropped[0]["reason"] and "没有" in dropped[0]["reason"]
   and str(ORTH_MIN) in dropped[0]["reason"],
   dropped[0]["reason"])

print("\n=== 4. 缺 aw 必须炸，不能静默当 None ===")
p = pick_of({"traj": "A", "n_sites": 1, "sites": [{"t": 1, "w": 0.3}]})
try:
    apply_boundary(p)
    ok("缺 aw 抛错", False, "竟然没抛")
except KeyError as e:
    ok("缺 aw 抛 KeyError", "aw" in str(e), str(e))

print("\n=== 5. aw 非数值必须炸 ===")
for bad in (None, "0.3", [0.3]):
    p = pick_of({"traj": "A", "n_sites": 1, "sites": [{"t": 1, "aw": bad}]})
    try:
        apply_boundary(p)
        ok(f"aw={bad!r} 抛错", False, "竟然没抛")
    except TypeError:
        ok(f"aw={bad!r} 抛 TypeError", True)

print("\n=== 6. 空 sites 列表 → 丢，不崩 ===")
p = pick_of({"traj": "E", "n_sites": 0, "sites": []})
kept, dropped = apply_boundary(p)
ok("空轨迹被丢", len(kept) == 0 and len(dropped) == 1)

print("\n=== 7. 边界不受输入里混入的低位点影响（k 已定） ===")
# 模拟「k 由 marker 总数决定」：过滤只作用在已取好的 top 集合上，
# 不因为少了一个低位点就把名次往前挪。混入一个 aw 极小的位点在 top 里
# 必须被丢，且不影响其它位点。
p = pick_of({"traj": "A", "n_sites": 4,
             "sites": [site(1, 0.9), site(2, 0.001), site(3, 0.8)]})
kept, _ = apply_boundary(p)
ok("只丢那个 0.001", [s["t"] for s in kept[0]["sites"]] == [1, 3],
   [s["t"] for s in kept[0]["sites"]])

print("\n=== 8. CLI 守卫：期望不符必须拒写，且不落盘 ===")
inp = pick_of({"traj": "A", "n_sites": 3,
               "sites": [site(1, 0.2), site(2, 0.3), site(3, 0.05)]})
with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, "in.json")
    out = os.path.join(td, "out.json")
    with open(src, "w", encoding="utf-8") as f:
        json.dump(inp, f)

    def run(args):
        return subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "apply_abs_boundary.py")] + args,
            capture_output=True, text=True)

    r = run(["--inp", src, "--out", out, "--expect-tracks", "99"])
    ok("轨迹数不符 → 非零退出", r.returncode != 0, r.returncode)
    ok("轨迹数不符 → 不落盘", not os.path.exists(out))
    ok("轨迹数不符 → 说了不符", "拒绝过滤" in r.stderr, r.stderr.strip()[-120:])

    r = run(["--inp", src, "--out", out, "--expect-sites", "99"])
    ok("位点数不符 → 拒写", r.returncode != 0 and not os.path.exists(out))

    r = run(["--inp", src, "--out", out, "--expect-kept-sites", "99"])
    ok("过边界后位点不符 → 拒写", r.returncode != 0 and not os.path.exists(out))

    r = run(["--inp", src, "--out", out, "--expect-sites", "3"])
    ok("都符 → 成功落盘", r.returncode == 0 and os.path.exists(out),
       r.stderr.strip()[-160:])
    if os.path.exists(out):
        o = json.load(open(out, encoding="utf-8"))
        ok("产物 schema 对", o["schema"] == "extreme_pick_abs/1")
        ok("产物 n_sites 对", o["n_sites"] == 2, o["n_sites"])
        ok("产物记了来源", o["derived_from"] == src)

    # schema 不对必须拒
    bad = os.path.join(td, "bad.json")
    with open(bad, "w", encoding="utf-8") as f:
        json.dump({"schema": "ortho_frac/1", "tracks": []}, f)
    r = run(["--inp", bad, "--out", out])
    ok("schema 不符 → 拒", r.returncode != 0 and "extreme_pick/1" in r.stderr,
       r.stderr.strip()[-120:])

print()
if FAILS:
    print(f"✗ {len(FAILS)} 条不过：{FAILS}")
    sys.exit(1)
print("✓ apply_abs_boundary.py 全部先验通过")
