#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r134b 重复采样：判「独立臂红 / 合并版绿」到底是结构性的还是 flakiness。

⚠ 修订 188 为什么要重做这个测量：
  修订 175 用**每臂各一次**的运行得出「合并版没有牙齿（扰动落到了判据跑完之后）」。
  但本轮实测两件事与那个归因冲突：

  (1) **结构上它们是同一份东西**：`r134b_fork.mjs` 与 `r145_probe_all.mjs`
      在注入区（注入@175-176、cBefore@215-216、D1@221-222）**逐行同构**，
      只多几条 arm=='fork' 时不会进入的 `else if`。⇒ 位置不是它们的差别。
  (2) 账本 `R6_RERUN_PREREG.md:22794` 自己记着一句反证：
      合并版上**「扰动已落地」与「36/36 全绿」两行同时出现**。
      扰动落地（注入时 before=True / after=False 已验）而 D1 仍绿
      ⇒ 只可能是**元素在注入与读数之间被页面重新渲染回来了**。

  ⇒ 「按臂分位置」这个改法，**前提可能就不成立**。
  ⇒ 本脚本不是去实现那个改法，而是先量清楚：**重复采样，看它稳不稳。**

用法：
    python3 r189_r134b_repeat.py --reps 3
退出码：
    0  跑完并出表
    2  用法/环境错
"""

import argparse
import re
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUT = ROOT / ".cache/mutbak"

MERGED = MUT / "r145_probe_all.mjs"
ARMS = ("fork", "all", "pair", "xy")

RESULT_RE = re.compile(r"^RESULT\s+(\S+)\s+(\d+)/(\d+)", re.M)
FAIL_RE = re.compile(r"^\[(?:FAIL|扰动未落地)\].*$", re.M)


def one_run(script, arm, base_url, cdp_port, timeout=240):
    # ⚠ 修订 189：原先用受限 PATH 找 node，实测 FileNotFoundError —— 崩在
    #   「找不到解释器」这一步，而不是判据上。
    #   ⇒ 与修订 180.4 同族：**先把要用的东西找对，再谈别的**。
    node = shutil.which("node") or "/Users/zhourui/.hermes/node/bin/node"
    if not Path(node).exists():
        print("[错误] 找不到 node，先修环境再跑本脚本")
        raise SystemExit(2)
    env = dict(os.environ)              # 继承完整环境，只覆盖必要的
    env.update({
        "T3D_URL": base_url,
        "CDP_PORT": str(cdp_port),
        "R134_ARM": arm,
    })
    t0 = time.time()
    try:
        p = subprocess.run([node, str(script)], env=env,
                           capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        out, rc = "(超时)", -9
    dt = time.time() - t0

    m = RESULT_RE.search(out)
    res = "%s %s/%s" % (m.group(1), m.group(2), m.group(3)) if m else "无 RESULT 行"
    fails = FAIL_RE.findall(out)
    landed = "[扰动已落地]" in out
    return {"arm": arm, "script": script.name, "rc": rc, "result": res,
            "landed": landed, "fails": fails[:3], "secs": dt}


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--url", default="http://127.0.0.1:22655")
    ap.add_argument("--arms", default=",".join(ARMS))
    a = ap.parse_args()

    if not MERGED.exists():
        print("[错误] 找不到合并版：%s" % MERGED)
        return 2

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    rows = []
    port = 9700
    print("=== r134b 重复采样（每臂 %d 次，串行，端口每轮换）===" % a.reps)
    print("base_url=%s" % a.url)

    for arm in arms:
        indep = MUT / ("r134b_%s.mjs" % arm)
        for tag, script in (("合并", MERGED), ("独立", indep)):
            if not script.exists():
                print("[跳过] %s 不存在：%s" % (tag, script))
                continue
            for rep in range(1, a.reps + 1):
                port += 1
                r = one_run(script, arm, a.url, port)
                rows.append(r)
                print("  %-4s %-4s 第%d次  %-14s 落地=%-5s rc=%-3d %.0fs"
                      % (arm, tag, rep, r["result"], r["landed"], r["rc"], r["secs"]))
                if r["fails"]:
                    for f in r["fails"]:
                        print("        %s" % f[:150])
                sys.stdout.flush()

    print("\n=== 汇总：同一个臂，重复采样是否稳定 ===")
    from collections import Counter
    for arm in arms:
        for tag in ("合并", "独立"):
            sub = [r for r in rows if r["arm"] == arm
                   and ((tag == "合并" and r["script"] == MERGED.name)
                        or (tag == "独立" and r["script"] != MERGED.name))]
            if not sub:
                continue
            c = Counter(r["result"] for r in sub)
            stable = "✅ 稳定" if len(c) == 1 else "⚠⚠⚴ **不稳定（flaky）**"
            print("  %-4s %-4s n=%d  %s   %s"
                  % (arm, tag, len(sub), dict(c), stable))

    print("\n⚠ 判读：只有当「合并」与「独立」各自**稳定且不同**时，")
    print("  「按臂分位置」才有意义。若任一侧 flaky，本轮结论不成立，")
    print("  要先解释 flakiness（页内重渲染 / 时序），而不是改位置。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())