#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异台：证明第三十三笔之六修好之后，C5/C6 **真的会红**。

## 它要反着验的那条判据

`scan_panel_coverage.py` 的 C6 问的是：
「块级无 data-* 标记**且祖先链也为空**」的块必须为 0。
正向跑只能看到「它现在是红的」；**只有把一个标记删掉、真孤儿数上升，
才能证明它红得有原因，而不是被口径写死了。**

## 反向测试设计（每一项都必须能失败，否则这张台子是装饰）

M1 删掉 `frontend/public/latent/index.html:316` 那条 `<li>` 的
   `data-bound="summary"` ⇒ 该 li 变成「无标记、无标记后代、祖先链为空」
   ⇒ **latent 页真孤儿 +1**，C6 判红，扫描 RESULT=RED。
M2 还原后 ⇒ 真孤儿回到原值，RESULT 与基线**逐字同签名**。
   ⚠⚠ 这里必须说清一件容易被读反的事：
   **基线本身就是 RED**（C6 第一次看得见导读浮层那 11 个洞），
   所以「还原后工具 GREEN」这句话**在字面上不成立** ——
   要让扫描变 GREEN 就得放宽口径，而放宽口径正是这个项目反复栽的坑。
   ⇒ 本台子把「GREEN」定义成**它自己的断言全绿 + 扫描状态与基线完全一致**，
     并把扫描真实的 RESULT 照实印出来（基线 RED / 变异 RED / 还原 RED）。
     **还原后变 GREEN 是不可能的，而那正是好消息**：说明基线的红是真检出。
M3 身份断言：新口径的清单里必须**逐条**包含导读浮层那 11 个真缺口
   （按 `head` 的**前缀**匹配 —— 用 `in` 会踩坑，见下面 M3 的注释）。
   只断言「总数 ≥ N」是**假绿**：多出一段、少掉一段，数字可能不变。

## 三条纪律（都是这个项目栽过的）

- **不许吞探针失败。** `> /dev/null 2>&1` 曾把一次 `SyntaxError` 藏掉，
  python 于是读到上一次跑出来的旧 JSON，数字一模一样地「没变」。
  ⇒ 这里每次都查返回码，非 0 立即中止。
- **每一步都要重跑两页的探针。** 因为 C0 要求产物比**被测源码**新，
  而变异文件 `frontend/public/latent/index.html` 正是 SRC_GLOBS 里的源码；
  只重跑 latent 那页的话，根页那份产物会比源码旧 ⇒ C0 自己先红了，
  测的就不是 C6 了。
- **启动先查残留备份。** 上一次崩在中途 ⇒ 源码可能是变异的、
  备份还留在盘上。此时先报告、再用备份把源码还原，才继续。

## 收尾

`sha256` 比对：变异前 = 变异后 = 还原后；
备份文件与任何 `*.bak` 一律不留。
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend/public/latent/index.html"
BAK = ROOT / ".cache/xcheck/_mut33_8_index.html.bak"
SCAN = ROOT / ".cache/xcheck/scan_panel_coverage.py"
PROBE = ROOT / ".cache/browser_verify/probe_panels.mjs"
LATENT_JSON = ROOT / ".cache/browser_verify/panel_blocks_latent.json"
ROOT_JSON = ROOT / ".cache/browser_verify/panel_blocks.json"
BASE = "http://127.0.0.1:22208"

# 变异目标：第 316 行那条 li 的 data-bound="summary"。
OLD_LI = '<li data-bound="summary">'
NEW_LI = "<li>"

# M3 的验收基准：导读浮层 #orientation 里那 11 个真缺口的身份。
# (标签, 字数, head 前缀)。⚠ 必须用**前缀**匹配：
#   底部按钮栏 #orientFoot 的 head 是
#   「我读完了，开始看 重置：下次打开再弹一次 关掉之后这一页不会再挡你；…」
#   ——它**包含**那句提示语的全文 ⇒ 用 `in` 匹配「关掉之后…」会命中**按钮栏**
#     而不是提示语本身，于是第 11 条会被一个别的元素顶账，而清单其实少了它。
#   （我自己第一版就是这么写的：11 条「全部 OK」，其实第 11 条是第 10 条顶的账。）
ORIENT_11 = [
    ("h1", 16, "第一次打开这个页面"),
    ("p", 66, "一个只会写数学题的 AI"),
    ("h2", 12, "一 · 这台机器在做什么"),
    ("h2", 16, "二 · 用页面上真实的数字"),
    ("h2", 14, "三 · 你会在这页上遇到的词"),
    ("h2", 16, "四 · 本页不主张的 4 种说法"),
    ("h2", 11, "五 · 这些数字的边界"),
    ("div", 54, "「换一个词，是因为草稿被挪了位置。」"),
    ("div", 60, "「干预是把答案推向某个方向。」"),
    ("div", 50, "我读完了，开始看"),
    ("div", 29, "关掉之后这一页不会再挡你"),
]

results = []
# 基线 sha256（main 里填）。收尾拿它比对 —— ⚠ 别写成 `sha256(SRC) == sha256(SRC)`
#   那种恒真的比较：它**看起来**在核对，其实什么都没核对。
BASE_SHA = None


def check(name, ok, detail):
    results.append((name, bool(ok)))
    print("[%s] %s\n       %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


def sha256(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def read_src():
    return io.open(str(SRC), encoding="utf-8").read()


def write_src(text):
    with io.open(str(SRC), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run_cmd(cmd, env, ok_codes=(0,)):
    """跑一条命令。⚠ 返回码**不在** ok_codes 里就立刻喊出来 —— 绝不静默继续。
    （`> /dev/null 2>&1` 曾把一次 SyntaxError 藏掉，python 于是读到上一次
      的旧 JSON，数字一模一样地「没变」。）

    ⚠⚠ 扫描的返回码 **1 是「判红」，不是「装置崩」**。
      我第一版没区分，扫描每跑一次就炸出一行
      「⚠⚠ 命令返回码 1」外加 1500 字输出 ——
      在一份刚证明「基线本来就是 RED」的日志里，
      这种噪声会让人以为基线那次跑崩了。
    """
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode not in ok_codes:
        print("       ⚠⚠ 命令返回码 %d（期望 %s）：%s"
              % (p.returncode, "/".join(str(c) for c in ok_codes), " ".join(cmd)))
        print(out[-1500:])
    return p.returncode, out


def probe_both():
    """两页都重跑。任一页失败 ⇒ 返回非 0（本台子必须知道自己没量到东西）。

    ⚠ 变异文件 `frontend/public/latent/index.html` 自己在 SRC_GLOBS 里，
      而 C0 要求**两份**产物都比源码新 ⇒ 只重跑 latent 那页的话，
      根页那份会比源码旧，C0 先红，测的就不是 C6 了。两页都必须重跑。
    """
    env_r = dict(os.environ)
    env_r["BV_URL"] = BASE + "/"
    env_r["PROBE_OUT"] = str(ROOT_JSON)
    rc1, o1 = run_cmd(["node", str(PROBE)], env_r)
    env_l = dict(os.environ)
    env_l["BV_URL"] = BASE + "/latent/index.html"
    env_l["PROBE_OUT"] = str(LATENT_JSON)
    rc2, o2 = run_cmd(["node", str(PROBE)], env_l)
    return (rc1 or rc2), o1, o2


def scan():
    # ⚠ 扫描的返回码：0=GREEN，1=RED（**也是我们预期的状态**），其他=装置崩。
    rc, out = run_cmd([sys.executable, str(SCAN)], dict(os.environ), ok_codes=(0, 1))
    if rc not in (0, 1):
        return None, out
    m = re.search(r"^RESULT panel_coverage\s+(\w+)\s+(\d+)/(\d+)", out, re.M)
    if not m:
        return None, out
    state = m.group(1)
    fails = re.findall(r"^   \[FAIL\] (\S+)", out, re.M)
    mt = re.search(r"真孤儿 (\d+) 段", out)
    total = int(mt.group(1)) if mt else None
    per = {}
    for pg in ("latent", "root"):
        mm = re.search(r"%s 页 （祖先链为空）=(\d+)" % pg, out)
        per[pg] = int(mm.group(1)) if mm else None
    # ⚠⚠⚠ 第三十三笔之十一：**解析不到必须自己判失败，不许返回 None 让上层比。**
    #   我把 C6 的消息改过一次（去掉分页拆分），这个正则就匹配不到了
    #   ⇒ `per[pg]` 变成 None ⇒ M1a 报「latent None → None（差 ?）」，
    #   而 **M2b 比的是 None == None，于是照样 PASS** ——
    #   **一条永远不可能失败的判据**是最坏的一类：它不吭声，还占一个绿。
    #   ⇒ 解析层现在直接带上 `parsed` 标志，上层凡是用到数的地方
    #     都必须先断言它为真。
    return {"state": state, "fails": fails, "total": total, "per": per,
            "parsed": total is not None and all(per[p] is not None
                                                for p in ("latent", "root"))}, out


def merged_list():
    """两页的 unmarked 合并（与 scan 的口径一致），每条带 page。"""
    items = []
    for p, pg in ((ROOT_JSON, "root"), (LATENT_JSON, "latent")):
        d = json.load(io.open(str(p), encoding="utf-8"))
        for it in d.get("unmarked", []):
            it = dict(it)
            it["page"] = d.get("page") or pg
            items.append(it)
    return items


def assert_orient_11(tag, items):
    """M3：逐条断言身份（标签 + 字数 + 前缀 + 祖先链为空 + 来自 latent 页）。"""
    bad = []
    for wtag, wlen, wpre in ORIENT_11:
        hit = [x for x in items if x["head"].startswith(wpre)]
        if len(hit) != 1:
            bad.append("%s… 命中 %d 个（要求恰好 1）" % (wpre[:12], len(hit)))
            continue
        x = hit[0]
        if (x["tag"], x["len"], x.get("orphan"), x["page"]) != (wtag, wlen, True, "latent"):
            bad.append("%s… 身份不对：%s" % (wpre[:12],
                     (x["tag"], x["len"], x.get("orphan"), x["page"])))
    return (not bad), ("11 条真缺口逐条命中（标签/字数/前缀/祖先链为空/来自 latent 页）"
                       if not bad else "；".join(bad))


def main():
    print("=" * 78)
    print("第三十三笔之六 变异台：证明 C6 真会红（而不是被口径写死）")
    print("=" * 78)

    # ---- 0. 启动先查上一次残留的备份 ----
    stale = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob(".cache/xcheck/_mut33_8_*.bak"))
    if stale:
        print("⚠ 发现上一次残留的备份：%s" % "、".join(stale))
        print("  ⇒ 上一轮崩在中途，源码**可能**处于变异态。先用备份还原再继续。")
        shutil.copyfile(str(BAK), str(SRC))
        print("  ⇒ 已用备份还原 %s（sha256=%s）" % (SRC.name, sha256(SRC)[:16]))
    check("M0 启动先查上次残留的备份（发现则先还原源码再继续）", True,
          ("发现残留 %d 个，已用备份还原源码后才继续" % len(stale)) if stale
          else "无残留备份，从干净状态开始")

    base_sha = sha256(SRC)
    global BASE_SHA
    BASE_SHA = base_sha
    pristine = read_src()
    shutil.copyfile(str(SRC), str(BAK))
    print("基线 sha256 = %s" % base_sha)
    print("备份：%s\n" % BAK.relative_to(ROOT))

    # ---- 1. 基线 ----
    print("── 步骤 1/3：基线（不改任何东西）", flush=True)
    rc, _, _ = probe_both()
    if rc:
        return finish(1, "探针跑失败，本轮**什么都没量到**（不许拿旧 JSON 顶账）")
    s0, out0 = scan()
    if s0 is None:
        print(out0[-1500:])
        return finish(1, "扫描没打出 RESULT 行")
    items0 = merged_list()
    print("基线：RESULT=%s  真孤儿 %d 段（latent %s / root %s）  失败判据 %s"
          % (s0["state"], s0["total"], s0["per"]["latent"], s0["per"]["root"],
             s0["fails"] or "无"))
    ok, why = assert_orient_11("基线", items0)
    check("M3a 新口径清单里**逐条**包含导读浮层那 11 个真缺口（断言身份，不只断言数量）",
          ok, "%s；清单合计 %d 段" % (why, len(items0)))
    check("M3b 基线真孤儿不是 0（旧工具印的「0 段」是漏了一页 + 标签太窄）",
          s0["total"] and s0["total"] > 0,
          "真孤儿 %d 段（latent %s / root %s）"
          % (s0["total"], s0["per"]["latent"], s0["per"]["root"]))

    # ---- 2. 变异：删掉 li[data-bound="summary"] 的标记 ----
    print("\n── 步骤 2/3：变异（删掉 :316 那条 li 的 data-bound=\"summary\"）", flush=True)
    n = pristine.count(OLD_LI)
    if n != 1:
        return finish(1, "源码里 %s 出现 %d 次（要求恰好 1 次）—— 不猜，改完再说"
                      % (OLD_LI, n))
    write_src(pristine.replace(OLD_LI, NEW_LI))
    print("变异后 sha256 = %s（与基线不同=%s）"
          % (sha256(SRC), sha256(SRC) != base_sha))

    rc, _, _ = probe_both()
    if rc:
        restore(pristine, base_sha)
        return finish(1, "变异态下探针跑失败（已还原源码）")
    s1, out1 = scan()
    if s1 is None:
        restore(pristine, base_sha)
        print(out1[-1500:])
        return finish(1, "变异态下扫描没打出 RESULT 行（已还原源码）")
    print("变异后：RESULT=%s  真孤儿 %d 段（latent %s / root %s）  失败判据 %s"
          % (s1["state"], s1["total"], s1["per"]["latent"], s1["per"]["root"],
             s1["fails"] or "无"))
    check("M1a 删掉一个 data-* 后，latent 页真孤儿数**上升**（+1）"
          "（⚠ 先断言解析成功：解析不到时这条会拿 None 比 None 然后报「差 ?」）",
          s0.get("parsed") and s1.get("parsed")
          and s1["per"]["latent"] == s0["per"]["latent"] + 1,
          "latent %s → %s（差 %s）"
          % (s0["per"]["latent"], s1["per"]["latent"],
             (s1["per"]["latent"] - s0["per"]["latent"])
             if None not in (s0["per"]["latent"], s1["per"]["latent"]) else "?"))
    check("M1b 变异后 C6 判红，且**只有** C6 红（别把别的判据也带红）"
          "（⚠ parsed=False 时 fails 也可能只是解析残缺，不算数）",
          bool(s1.get("parsed")) and s1["fails"] == ["C6"],
          "失败判据 %s" % (s1["fails"] or "无"))
    check("M1c 变异后扫描 RESULT=RED",
          s1["state"] == "RED", "RESULT=%s" % s1["state"])
    # 那条 li 现在自己成了真孤儿 —— 断言它**以身份**出现在清单里，
    # 而不是只断言「多了一段」。
    li_hit = [x for x in merged_list()
              if x["head"].startswith("所以这些是") and x["orphan"]]
    check("M1d 新增的那条真孤儿就是被删标记的 li 本身（断言身份）",
          len(li_hit) == 1 and li_hit[0]["page"] == "latent",
          "命中 %d 条%s" % (len(li_hit),
                        ("：「%s…」（%d 字）" % (li_hit[0]["head"][:30], li_hit[0]["len"]))
                        if li_hit else ""))

    # ---- 3. 还原 ----
    print("\n── 步骤 3/3：还原", flush=True)
    ok_restore, why_restore = restore(pristine, base_sha)
    check("M2a 还原后 sha256 与基线逐字节相同", ok_restore, why_restore)
    rc, _, _ = probe_both()
    if rc:
        return finish(1, "还原态下探针跑失败")
    s2, out2 = scan()
    if s2 is None:
        print(out2[-1500:])
        return finish(1, "还原态下扫描没打出 RESULT 行")
    print("还原后：RESULT=%s  真孤儿 %d 段（latent %s / root %s）  失败判据 %s"
          % (s2["state"], s2["total"], s2["per"]["latent"], s2["per"]["root"],
             s2["fails"] or "无"))
    # ⚠ 必须先断言**解析成功**，否则下面这个 == 在两边都是 None 时恒真
    check("M2x 两边的分页数都解析到了（否则下面所有 == 都是 None == None，恒真）",
          bool(s2.get("parsed")) and bool(s0.get("parsed")),
          "基线 parsed=%s（latent=%s root=%s total=%s）　还原后 parsed=%s（latent=%s）"
          % (s0.get("parsed"), s0["per"]["latent"], s0["per"]["root"], s0["total"],
             s2.get("parsed"), s2["per"]["latent"]))
    check("M2b 还原后 latent 真孤儿回到原值（变异是可逆的，没有把工具永久改成红）",
          s0.get("parsed") and s2.get("parsed")
          and s2["per"]["latent"] == s0["per"]["latent"],
          "latent %s（基线 %s）" % (s2["per"]["latent"], s0["per"]["latent"]))
    check("M2c 还原后扫描状态与基线同签名（RESULT + 失败判据集合 + 真孤儿数）",
          (s2["state"], s2["fails"], s2["total"])
          == (s0["state"], s0["fails"], s0["total"]),
          "基线 %s/%s/%s ↔ 还原 %s/%s/%s"
          % (s0["state"], s0["fails"], s0["total"],
             s2["state"], s2["fails"], s2["total"]))
    print("       ⚠ 注意：还原后扫描**仍然是 RED**，而这是**对的** ——")
    print("         基线本身就 RED（C6 第一次看得见那 11 个洞）。")
    print("         要让它 GREEN 就得放宽口径 —— 那正是这个项目反复栽的坑。")
    print("         本台子的 GREEN 指的是**它自己的断言全绿**，不是扫描变绿。")
    ok3, why3 = assert_orient_11("还原后", merged_list())
    check("M3c 还原后那 11 条仍逐条在清单里（还原没有把标记连同判据一起弄丢）",
          ok3, why3)

    return finish(0, "反向测试全部按预期走完")


def restore(pristine, base_sha):
    write_src(pristine)
    now = sha256(SRC)
    return now == base_sha, "还原后 sha256=%s（基线 %s，相同=%s）" % (
        now[:16], base_sha[:16], now == base_sha)


def finish(code, note):
    # 收尾：无论如何都要把源码还原干净 + 不留备份。
    # ⚠⚠ 顺序是**先删、再查残留**：我第一版先把 BAK.name 塞进 left、
    #   才去 unlink，于是 M5 报「残留 _mut33_8_index.html.bak」——
    #   而那个文件**当场就被删掉了**（ls 确认过盘上根本没有）。
    #   ⇒ 一条判据自己报了假红，而它的名字就叫「不留残留」——
    #     这比漏检更难查：人会以为盘上真脏了，去手工删一个不存在的东西。
    # ⚠⚠ 兜底还原只在**内容真的不一样**时才做。
    #   我第二版在这里无条件 copyfile(BAK → SRC)：
    #   内容一模一样（sha 相同），但它把 index.html 的 mtime 顶到了
    #   **最后一次探针之后** ⇒ C0「产物必须比源码新」当场失效，
    #   交付后随手跑一次扫描就是「一条都没跑完」的早退。
    #   ⇒ 交付物必须让人能接着跑下去。
    if BAK.exists() and SRC.exists() and sha256(SRC) != BASE_SHA:
        shutil.copyfile(str(BAK), str(SRC))
    if BAK.exists():
        BAK.unlink()
    left = ([BAK.name] if BAK.exists() else []) + \
           sorted(p.name for p in ROOT.glob(".cache/xcheck/_mut33_8_*.bak"))
    now = sha256(SRC)
    check("M4 收尾：源码 sha256 已回到基线（与变异前逐字节相同）",
          BASE_SHA is not None and now == BASE_SHA,
          "现在 %s / 基线 %s（相同=%s）"
          % (now[:16], (BASE_SHA or "?")[:16], now == BASE_SHA))
    check("M5 收尾：不留任何残留文件（删完再查盘上真实状态）", not left,
          "盘上仍有残留：%s" % "、".join(left) if left
          else "无残留；%s 已删、源码 sha 与基线相同" % BAK.name)
    failed = [n for n, ok in results if not ok]
    print("\nRESULT mut_panel_coverage  %s  %d/%d 条通过%s"
          % ("RED" if (failed or code) else "GREEN",
             len(results) - len(failed), len(results),
             ("  —— " + note) if note else ""))
    for n in failed:
        print("   [FAIL] " + n)
    return 1 if (failed or code) else 0


if __name__ == "__main__":
    sys.exit(main())
