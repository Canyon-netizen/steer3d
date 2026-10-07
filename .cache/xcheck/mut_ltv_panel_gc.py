#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异台：证明面板判据 L19 / L20 **会变红**。

## 它要反着验的那两条判据

`.cache/browser_verify/verify_ltv_panel.mjs` 新加了：

- **L19** G-c 逐档读数块**可见**，三臂率 / Δ / 三条子判据与产物逐格相符
- **L20** G-c 真被测过之后，页面不再印「那一道门本轮仍是没测」

正向跑只能看到它们现在是绿的。**只有把页面改坏，它们红得有原因，
才能证明它们不是装饰。**

## 为什么变异改的是**页面源码**而不是产物

L19 判的是「页面印的数 == 产物里的数」。如果改产物，页面会跟着改，
两边永远相等 —— 那种变异打不到任何东西（这是「变异打空」，
不是「判据没牙齿」，两者必须分开）。
所以这里改 `index.html` 的渲染表达式，让页面**说错话**，
而产物保持为真的那一份。

## 还原是硬要求

改的是仓库里的真实文件。每一步都在 `finally` 里还原，
并且最后回读 sha256 —— `2>/dev/null` 那种吞错误水的写法这里一律不用。
"""

import hashlib
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
# ⚠ 变异必须改**服务实际在读的那一份** index.html。
#   服务跑隔离副本时（.next 被两个 dev server 踩坏过，见 next.config.js 的注释），
#   改仓库里那份对页面毫无影响 ⇒ 那是「变异打空」。
#   用 PANEL_SRC 指到服务在读的那份；不设就改仓库里那份。
SRC = os.environ.get("PANEL_SRC", os.path.join(
    ROOT, "frontend", "public", "latent", "index.html"))
BAK = os.path.join(ROOT, ".cache", "mutbak", "_mutpanel.bak.html")
# ⚠⚠ 备份**不许**放在 .cache/xcheck/ 或 .cache/browser_verify/ 里。
#   `scan_artifact_consumers.sources()` 正好 glob 这两个目录下的
#   `*.html` —— 一份 index.html 备份躺在 xcheck/ 里，扫描器就把它
#   算成「有判据读了 cot_effect.json」，K3 随即把例外名单里那条判成过期，
#   全链 RED 3/4。
#   ⚠ 这不是「判据坏了」，是**临时文件放进了判据扫描目录**。
#   判红先查自己有没有在扫描目录里落下东西。
VER = os.path.join(ROOT, ".cache", "browser_verify", "verify_ltv_panel.mjs")
URL = os.environ.get("LAT_URL", "")

# M1：把 G-c 那一块整个不渲染（等价于「这一屏退回没有 G-c 的老样子」）
#     ⇒ L19 找不到块（红），L20 也会红（那句过时的「仍是没测」回来了）
M1_OLD = '${gcMeasured ? `\n  <div data-ltvgc="1"'
M1_NEW = '${false ? `\n  <div data-ltvgc="1"'

# M2：三臂率印成固定的 0.000（页面说错话，产物不变）
#     ⇒ L19 的「三臂率不符」应当红，L20 不该红
M2_OLD = '<td>${Number(rt.arm||0).toFixed(3)}</td>'
M2_NEW = '<td>0.000</td>'

# M3：把「不成立」显示成「成立」——最容易发生也最危险的一种假绿
#     ⇒ L19 的子判据不符应当红
M3_OLD = '<td>${r.all_three_hold\n              ? `<span style="color:#7ee08a">成立</span>`'
M3_NEW = '<td>${true\n              ? `<span style="color:#7ee08a">成立</span>`'

MUTATIONS = [
    ("M1_gc_block_removed", "L19 G-c 逐档读数块", [(M1_OLD, M1_NEW)]),
    ("M2_rates_faked", "L19 G-c 逐档读数块", [(M2_OLD, M2_NEW)]),
    ("M3_fail_shown_as_ok", "L19 G-c 逐档读数块", [(M3_OLD, M3_NEW)]),
    ("M1b_stale_comes_back", "L20 G-c 真被测过之后",
     [("""${gcMeasured ? `<b>那一道门这一轮测了，判「不成立」</b>：注入""",
       """${false ? `<b>那一道门这一轮测了，判「不成立」</b>：注入""")]),
]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def run_verifier():
    env = dict(os.environ)
    env["LAT_URL"] = URL
    # ⚠ 改完源码后 Next dev 要重新编译；不等就会拿**改动前**的 DOM 去跑判据，
    #   于是「该红没红」—— 那是环境没跟上，不是判据没牙齿。
    time.sleep(6)
    p = subprocess.run(["node", VER], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def main():
    if not URL:
        print("缺 LAT_URL：面板判据要一个真浏览器去看这个页面")
        return 2
    if not os.path.exists(BAK):
        os.makedirs(os.path.dirname(BAK), exist_ok=True)
        shutil.copyfile(SRC, BAK)
    base_sha = sha(BAK)

    rc, out = run_verifier()
    base_tail = [l for l in out.splitlines() if l.startswith("=== ")]
    base_pass = None
    if base_tail:
        try:
            base_pass = int(base_tail[-1].split()[1].split("/")[0])
        except Exception:
            base_pass = None
    print(f"基线：{base_tail[-1] if base_tail else '（没跑出汇总行）'}")
    if base_pass is None:
        print("基线自己就没跑出汇总行 ⇒ 后面的红绿都不可信，先修基线")
        return 2

    fails = 0
    try:
        for name, expect, subs in MUTATIONS:
            txt = open(BAK, encoding="utf-8").read()
            applied = []
            for old, new in subs:
                if txt.count(old) != 1:
                    applied.append(f"锚点出现 {txt.count(old)} 次（应为 1）")
                    break
                txt = txt.replace(old, new, 1)
                applied.append("ok")
            if any(a != "ok" for a in applied):
                print(f"[红] {name}：变异构造失败 {applied} ⇒ 这是**变异打空**，"
                      f"不是判据没牙齿")
                fails += 1
                continue
            with open(SRC, "w", encoding="utf-8") as f:
                f.write(txt)
            _, mout = run_verifier()
            red = [l for l in mout.splitlines() if l.startswith("[FAIL]")]
            tail = [l for l in mout.splitlines() if l.startswith("=== ")]
            hit = any(expect in l for l in red)
            print(("[绿] " if hit else "[红] ") + name +
                  f"：{tail[-1] if tail else '（无汇总）'}；"
                  + ("命中 '" + expect + "'" if hit else "**没命中** '" + expect + "'") +
                  f"；红条 {len(red)}")
            if not hit:
                fails += 1
    finally:
        shutil.copyfile(BAK, SRC)

    ok = sha(SRC) == base_sha
    print(f"还原：sha256 与基线逐字节相同 = {ok}")
    if not ok:
        print("[红] 还原失败 —— 页面源码已不是基线那份，**先停下**")
        return 1
    if fails:
        print(f"{fails} 条变异没被抓住")
        return 1
    print("全部变异都被抓住（L19 / L20 有牙齿）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())