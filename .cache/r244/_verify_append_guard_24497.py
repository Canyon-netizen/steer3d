#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_verify_append_guard_24497.py —— **逐轮**验证落账脚本的「防重复落账」闸（244.92–244.97 **六轮**）。

⚖ **三条测试，每轮都跑**：
  ① **复现**（生产路径）：拿**落账前**那份账本跑脚本 ⇒ ⇒ 产出的账本必须与**当年入库那份逐字节相同**
     ⇒ ⇒ ⇒ 「修闸没有改变落账产物」是**实测**的，不是声称的。
  ② **重跑不得写**（幂等）：对**已落过**的账本再跑一次 ⇒ ⇒ 必须**退出 0**、**一个字节都不许改**、
     并且打印「幂等」；⚠ 再跑一次**不许**追加第二份段。
  ③ **负控**（闸必须能红）：把账本里**那一段**篡改（插一行 X）⇒ ⇒ 再跑必须**停下**（非 0 退出）
     ⇒ ⇒ 且**一个字节都不许改** ⇒ ⇒ ⇒ 这条闸**不是恒绿的**。

⚖ **隔离**：每一轮都在**自己的**临时树里跑（`<work>/r244XX/.cache/...`）
  ⇒ ⇒ 树里的 `.cache/r244`、`.cache/xcheck` 是**符号链接**指向真仓（只读）
  ⇒ ⇒ 树里的 **账本**与 **`docs/BPATH_VERDICT.md`** 是**那一轮当时的副本**
  ⇒ ⇒ ⛔ **真仓一个字都不碰**。

⚖ **为什么页面要「那一轮当时的版本」**：落账脚本会把 `docs/BPATH_VERDICT.md` 的 md5
  写进段里 ⇒ ⇒ 用后来的版本跑，段就不可能与当年入库那份逐字节相同
  ⇒ ⇒ ⇒ 「① 复现」必须是**当年那一版**的页面（从 git 取）。

⚖ 用法：
  python3 _verify_append_guard_24497.py --work /dev/shm/_guardtest24497 \
      --ledgers /dev/shm/_guardtest24497/ledgers --src /home/zhourui/steer3d \
      --receipts /dev/shm/_guardtest24497/rcpt
"""

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys

ROUNDS = ["244.92", "244.93", "244.94", "244.95", "244.96", "244.97"]


def md5b(b):
    return hashlib.md5(b).hexdigest()


def read(p):
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def write(p, t):
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(t)


def build_tree(work, src, rd, receipts=None):
    """⚖ 造一棵**隔离**的树：脚本是**真副本**，其余输入是**符号链接**，账本与页面是**副本**。"""
    tag = rd.replace(".", "")
    root = os.path.join(work, "r" + tag)
    r244 = os.path.join(root, ".cache", "r244")
    xcheck = os.path.join(root, ".cache", "xcheck")
    docs = os.path.join(root, "docs")
    for d in (r244, xcheck, docs):
        if os.path.islink(d):
            os.unlink(d)
        elif os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    real_r244 = os.path.join(src, ".cache", "r244")
    script = "_append_%s.py" % tag

    # ---- `.cache/r244`：脚本是**副本**，其余是**符号链接**（收据允许从别处链进来）----
    names = set(os.listdir(real_r244))
    if receipts and os.path.isdir(receipts):
        for _n in os.listdir(receipts):
            if _n.startswith("_e244"):
                names.add(_n)
    for name in sorted(names):
        if name == script:
            continue
        target = None
        if receipts and os.path.isdir(receipts) and os.path.isdir(os.path.join(receipts, name)):
            target = os.path.join(receipts, name)
        elif os.path.exists(os.path.join(real_r244, name)):
            target = os.path.join(real_r244, name)
        if target is None:
            continue
        try:
            os.symlink(target, os.path.join(r244, name))
        except OSError:
            pass
    shutil.copy2(os.path.join(real_r244, script), os.path.join(r244, script))

    # ---- `.cache/xcheck`：全部**符号链接**（账本除外 —— 那是**副本**）----
    real_x = os.path.join(src, ".cache", "xcheck")
    if os.path.isdir(real_x):
        for _n in sorted(os.listdir(real_x)):
            if _n == "R6_RERUN_PREREG.md":
                continue
            _t = os.path.join(real_x, _n)
            if os.path.exists(os.path.join(xcheck, _n)):
                continue
            try:
                os.symlink(_t, os.path.join(xcheck, _n))
            except OSError:
                pass

    # ---- `docs/BPATH_VERDICT.md`：**那一轮当时的副本**（由调用方放进 pages 目录）----
    page_src = os.path.join(work, "pages", "page_%s.md" % tag)
    if os.path.isfile(page_src):
        shutil.copy2(page_src, os.path.join(docs, "BPATH_VERDICT.md"))
    return root, r244, xcheck


def run_script(root, script):
    p = subprocess.Popen([sys.executable, os.path.join(root, ".cache", "r244", script)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.read().decode("utf-8", "replace")
    p.wait()
    return p.returncode, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--ledgers", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--receipts", default=None,
                    help="收据目录所在处（各 _e2449X/），远端仓里没有 ⇒ 从这里链进去")
    args = ap.parse_args()

    for d in (args.ledgers, args.src):
        if not os.path.isdir(d):
            print("⛔ 缺目录：%s" % d)
            return 2
    if not os.path.isdir(os.path.join(args.work, "pages")):
        print("⛔ 缺页面目录：%s" % os.path.join(args.work, "pages"))
        return 2

    rows = []
    all_ok = True
    for rd in ROUNDS:
        tag = rd.replace(".", "")
        pre_p = os.path.join(args.ledgers, "pre_%s.md" % tag)
        post_p = os.path.join(args.ledgers, "post_%s.md" % tag)
        if not (os.path.isfile(pre_p) and os.path.isfile(post_p)):
            print("⛔ %s：缺 pre/post 账本" % rd)
            return 2
        pre_b = open(pre_p, "rb").read()
        post_b = open(post_p, "rb").read()
        script = "_append_%s.py" % tag

        root, r244, xcheck = build_tree(args.work, args.src, rd, args.receipts)
        led = os.path.join(xcheck, "R6_RERUN_PREREG.md")

        # ---- ① 复现：落账前 → 落账后，必须逐字节相同 ----
        write(led, pre_b.decode("utf-8"))
        rc, out = run_script(root, script)
        produced = open(led, "rb").read()
        t1 = (rc == 0 and produced == post_b)
        t1_md5 = "rc=%d ｜ 产出 %s vs 入库 %s" % (rc, md5b(produced), md5b(post_b))

        # ---- ② 重跑不得写 ----
        before2 = open(led, "rb").read()
        rc2, out2 = run_script(root, script)
        after2 = open(led, "rb").read()
        n_sect = after2.decode("utf-8").count("## 修订 %s " % rd)
        t2 = (rc2 == 0 and after2 == before2 and n_sect == 1 and "幂等" in out2)
        t2_note = "rc=%d ｜ 字节未改=%s ｜ 段数=%d ｜ 打印「幂等」=%s" % (
            rc2, after2 == before2, n_sect, "幂等" in out2)

        # ---- ③ 负控：篡改那一段 ⇒ 必须停下且不改 ----
        txt = after2.decode("utf-8")
        i = txt.index("## 修订 %s " % rd)
        j = txt.find("\n", i)
        corrupt = txt[:j + 1] + "X\n" + txt[j + 1:]
        write(led, corrupt)
        before3 = open(led, "rb").read()
        rc3, out3 = run_script(root, script)
        after3 = open(led, "rb").read()
        t3 = (rc3 != 0 and after3 == before3)
        t3_note = "rc=%d ｜ 字节未改=%s" % (rc3, after3 == before3)

        ok = t1 and t2 and t3
        all_ok = all_ok and ok
        rows.append((rd, ok, t1, t1_md5, t2, t2_note, t3, t3_note))

    print("=" * 78)
    print("落账脚本「防重复落账」闸 · 逐轮验证（244.92–244.97）")
    print("=" * 78)
    for rd, ok, t1, t1_md5, t2, t2_note, t3, t3_note in rows:
        print("── %s ── %s" % (rd, "✅ 全过" if ok else "⛔ 有红"))
        print("   %s ① 复现：落账前 ⇒ ⇒ 产出 == 当年入库那份（逐字节）：%s"
              % ("✅" if t1 else "⛔", t1_md5))
        print("   %s ② 重跑不得写（退出 0 / 字节不变 / 只 1 段 / 打印「幂等」）：%s"
              % ("✅" if t2 else "⛔", t2_note))
        print("   %s ③ 负控：篡改那段 ⇒ ⇒ 必须停下且不改：%s"
              % ("✅" if t3 else "⛔", t3_note))
    print("=" * 78)
    print("VERIFY_RC=%d" % (0 if all_ok else 1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
