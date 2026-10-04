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
M2 还原后 ⇒ 真孤儿回到原值，失败判据集合与基线相同。
   ⚠ 第三十三笔之十四把 M2c 拆成三条，因为原来的「逐字同签名」**问错了**：
   它拿 root 的**总数**当可复现量，而 root 有一条会自己往前走的轨迹读数 ——
   同一份源码连跑 3 次，真孤儿**总数恒为 61**，但**每轮有 8~11 条换一批身份**。
   ⇒ 现在比的是：① 失败判据集合 ② latent 页逐条身份（变异真正作用的那页）
     ③ root **稳定块**的身份集合。会自己变的那批由探针自报 `volatile`，
     按设计不可比，条数照印。
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

# ⚠⚠ 第三十三笔之十四：**M3 的期望整个反过来了。**
#   原 M3 断言「导读那 11 条逐条**在**缺口清单里」—— 那时的目的是证明
#   「新口径第一次看得见这 11 个洞」。而 4e576a3 已经把它们**还掉了**
#   （加了 10 个 data-orient-part 标记 + Z12/Z13/Z14）。
#   ⇒ 实测 M3a/M3c 全红，**11 条一条都不在清单里**。
#   ⇒ 但红的原因不是台子坏了，是**期望过期了** ——
#     断言「它们已被还掉」才是现在该断言的东西。
#   ⇒ 而且要断得**更强**：不是「不在清单里」就算过，
#     而是**抽掉一个标记，那一条必须按身份回到清单里** ——
#     这才证明「正是那些标记把它们移出清单的」，是因果不是相关。
#
# 身份基准：(标签, 字数, head 前缀)。⚠ 必须用**前缀**匹配：
#   底部按钮栏 #orientFoot 的 head 是
#   「我读完了，开始看 重置：下次打开再弹一次 关掉之后这一页不会再挡你；…」
#   ——它**包含**那句提示语的全文 ⇒ 用 `in` 匹配「关掉之后…」会命中**按钮栏**
#     而不是提示语本身，于是第 11 条会被一个别的元素顶账，而清单其实少了它。
#   （第一版就是这么写的：11 条「全部 OK」，其实第 11 条是第 10 条顶的账。）
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
# 变异 M3d 用的那一条：抽掉「三 · 你会在这页上遇到的词」这个 h2 的
# data-orient-part 标记。它**必须**回到缺口清单里。
M3D_TAG, M3D_LEN, M3D_PRE = "h2", 14, "三 · 你会在这页上遇到的词"
M3D_OLD = '<h2 data-orient-part="sec3">'
M3D_NEW = "<h2>"

results = []
# 基线 sha256（main 里填）。收尾拿它比对 —— ⚠ 别写成 `sha256(SRC) == sha256(SRC)`
#   那种恒真的比较：它**看起来**在核对，其实什么都没核对。
BASE_SHA = None
# ⚠ 异常路径要用的两份底：崩在 write_src 之后时，靠它兜底还原源码。
#   （我第三版就崩在一个格式串上 —— `"　身份 = %s" % (4 元组)` 只给了一个
#     占位符，Python 报 not all arguments converted —— 而它崩在打印细节
#     的那一行，位置在 write_src **之后** ⇒ index.html 被留在变异态，
#     症状和「判据没红」长得一模一样。收尾只能靠 git checkout 救回来。）
_PRISTINE = None


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


# ---- 第三十三笔之十四：按页、按「会不会自己变」取身份集合 ----------------
# 身份 = 标签 + 自己那段话的前缀。**不拿 len 当身份的一部分**：
# 步进块的长度本身随内容变，拿它当身份会把「同一块的不同步」算成两块
# —— 而那正是这一族 bug 的来源（数对了、身份错了）。
def _ident(u):
    return (u.get("tag"), (u.get("ownHead") or u.get("head") or "").strip()[:70])


def _page_orphans(items, page):
    return [u for u in items
            if u.get("page") == page and u.get("orphan") and not u.get("shell")]


def latent_ids(items):
    """latent 页**全部**真孤儿（实测那一页 volatile 恒为 0，所以全比）。"""
    return {_ident(u) for u in _page_orphans(items, "latent")}


def root_stable_and_volatile(items):
    """root 页真孤儿按「会自己变 / 不变」分成两个身份集合。

    ⚠ 刻意**不**留 `root_stable_ids()` 那种单返回一个的包装：
      M2e 第一版用它当分区依据，而那个分区本身带噪（volatile 是
      采样窗口相关的下界）⇒ 报出假红。改成一次返回两个集合之后，
      「取交集」这件事在**调用点**看得见，而不是藏在一个只返回稳定块的
      助手里 —— 后者会让人以为稳定块是确定的。
    ⚠ 同样没有 `root_vol_count()`：条数在 M2e 的详情里直接从两个集合
      取长度，不需要单独一个函数（留着只会变成没人调的第二个真相）。
    """
    st, vo = set(), set()
    for u in _page_orphans(items, "root"):
        (vo if u.get("volatile") else st).add(_ident(u))
    return st, vo


def items2_now():
    """还原后的清单 —— 必须在 restore + probe_both 之后调用。"""
    return merged_list()


def assert_orient_11(items, want_present, where):
    """逐条断言**真孤儿身份**（标签 + 字数 + 前缀 + 祖先链为空 + 来自 latent 页）。

    ⚠⚠ `want_present=False` 那一支判的是「**不是真孤儿**」，
      **不是**「不出现在清单里」—— 这两个不是一回事：
      第 11 条（#orientFoot 里的提示行）**仍然在清单里**，
      但它 `orphan=False`，因为它父级 #orientFoot 拿到了 data-orient-part="foot"
      ⇒ 它有带标记的祖先，按定义就不是真孤儿。
      我第一版断言「11 条都不在清单里」⇒ 那一条永远红 ⇒ 整条断言作废。
    ⇒ 目标统一成「是不是真孤儿」，两个方向都比的是同一个量。
    """
    bad = []
    for wtag, wlen, wpre in ORIENT_11:
        if want_present:
            hit = [x for x in items
                   if x["head"].startswith(wpre) and x.get("orphan")]
            if len(hit) != 1:
                bad.append("%s… 命中 %d 个真孤儿（要求恰好 1）" % (wpre[:12], len(hit)))
                continue
            x = hit[0]
            if (x["tag"], x["len"], x["page"]) != (wtag, wlen, "latent"):
                bad.append("%s… 身份不对：%s" % (wpre[:12],
                         (x["tag"], x["len"], x["page"])))
        else:
            still = [x for x in items
                     if x["head"].startswith(wpre) and x.get("orphan")]
            if still:
                bad.append("%s… 仍是真孤儿（应已还掉）" % wpre[:12])
    verb = "是真孤儿" if want_present else "**都不是**真孤儿"
    return (not bad), ("11 条真缺口逐条%s" % verb
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
    global _PRISTINE
    _PRISTINE = pristine
    shutil.copyfile(str(SRC), str(BAK))
    print("基线 sha256 = %s" % base_sha)
    print("备份：%s\n" % BAK.relative_to(ROOT))

    # ---- 1. 基线 ----
    print("── 步骤 1/4：基线（不改任何东西）", flush=True)
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
    ok, why = assert_orient_11(items0, False, "基线")
    check("M3a 导读那 11 条真缺口**都不是真孤儿**了"
          "（4e576a3 给它们加了 data-orient-part 标记 ⇒ 有人能读到了）",
          ok, "%s；清单合计 %d 段" % (why, len(items0)))
    check("M3b 基线真孤儿不是 0（旧工具印的「0 段」是漏了一页 + 标签太窄）",
          s0["total"] and s0["total"] > 0,
          "真孤儿 %d 段（latent %s / root %s）"
          % (s0["total"], s0["per"]["latent"], s0["per"]["root"]))

    # ---- 2. 变异：删掉 li[data-bound="summary"] 的标记 ----
    print("\n── 步骤 2/4：变异（删掉 :316 那条 li 的 data-bound=\"summary\"）", flush=True)
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
    print("\n── 步骤 3/4：还原", flush=True)
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
    # ⚠⚠⚠ 第三十三笔之十四：M2c 原来判「总数严格相等」，**根页这一半是错的**。
    #   它报过假红：基线 root 62 ↔ 还原 root 61，而那一轮**只改了
    #   latent/index.html**，压根碰不到根页 ⇒ 先怀疑量本身。
    #   同一份源码连跑 3 次实测：root 真孤儿**总数恒为 61**，但
    #   **8~11 条每轮换一批身份**（connected ### steps / step ### · ppl /
    #   path length / mean step / direction reversals / ### tokens …）
    #   —— 根页有一条会自己往前走的轨迹读数。latent 侧同期 **0 条会变**。
    #   ⇒ 「总数一样」也会骗人（62 那次是重画中途多出一块），
    #     **而变的是身份**：任何按块内容对账的东西都会被搅乱。
    #   ⇒ 处置**不是**放松判据，是把它改成问对了的问题：
    #     ① 失败判据集合严格相等（这才是「工具状态」的指纹）；
    #     ② latent 页严格相等（**变异真正作用的那一页**）；
    #     ③ 根页比**稳定块的身份集合**（不是总数）——
    #        会自己变的那批由探针自报 `volatile`，按设计不可比，印出条数。
    #   ⇒ 这样判据比原来**更强**：原来只比一个总数，现在比的是逐条身份。
    fail_same = s2["fails"] == s0["fails"] and s2["state"] == s0["state"]
    check("M2c 还原后**失败判据集合**与基线相同（工具状态指纹）",
          bool(s0.get("parsed")) and bool(s2.get("parsed")) and fail_same,
          "基线 %s/%s ↔ 还原 %s/%s"
          % (s0["state"], s0["fails"], s2["state"], s2["fails"]))
    check("M2d 还原后 latent 真孤儿**逐条身份**回到基线"
          "（变异真正作用的那一页；根页不比是因为它有会自己变的读数块）",
          latent_ids(items0) == latent_ids(items2_now()),
          "latent 稳定块 %d 条；基线独有 %d、还原独有 %d"
          % (len(latent_ids(items0)),
             len(latent_ids(items0) - latent_ids(items2_now())),
             len(latent_ids(items2_now()) - latent_ids(items0))))
    # ⚠⚠⚠ M2e 第一版比「各自判稳定的集合」，**它自己也会飘**：
    #   实测基线标 8 条会变、还原只标 6 条 ⇒ 同一批块里 2 条在基线被抓住 tick、
    #   在还原时**没被抓住**（4 秒窗口比动画周期短，赶上才算）。
    #   ⇒ 「volatile」是**采样窗口相关**的量，不是块的固有属性。
    #     拿它当划分依据去比身份，等于**用一个噪声量做分区** ——
    #     这与「拿波动当信号」是同一族。
    #   ⇒ 改成比**两轮都判稳定的那部分**（交集）：那才是真正可复现的，
    #     而两轮的 volatile 条数照印，不藏。
    #   ⚠ 这不是放松：latent 页那条（M2d）仍是**全量严格相等**，
    #     而 M2d 才是「变异可逆」这个主张真正该由它承担的地方。
    st0, vo0 = root_stable_and_volatile(items0)
    st2, vo2 = root_stable_and_volatile(items2_now())
    both = st0 & st2
    check("M2e 还原后 root **两轮都判稳定**的块身份一致"
          "（会自己变的那批按设计不可比；⊘ volatile 是采样窗口相关的量，"
          "只当**下界**用，两轮条数都印在这里）",
          both == st0 and both == st2,
          "基线 稳定%d/会变%d ↔ 还原 稳定%d/会变%d；两轮都稳定 %d 条，"
          "只在基线稳定 %d、只在还原稳定 %d"
          % (len(st0), len(vo0), len(st2), len(vo2), len(both),
             len(st0 - st2), len(st2 - st0))
          + ("" if both == st0 == st2
             else "；基线独有 %d、还原独有 %d"
                  % (len(st0 - st2), len(st2 - st0))))
    print("       ⚠ 注意：还原后扫描**仍然是 RED**，而这是**对的** ——")
    print("         基线本身就 RED（C6 第一次看得见那 11 个洞）。")
    print("         要让它 GREEN 就得放宽口径 —— 那正是这个项目反复栽的坑。")
    print("         本台子的 GREEN 指的是**它自己的断言全绿**，不是扫描变绿。")
    ok3, why3 = assert_orient_11(merged_list(), False, "还原后")
    check("M3c 还原后那 11 条仍**都不是真孤儿**（还原没有把标记一起弄丢）",
          ok3, why3)

    # ---- 步骤 4/4：M3d 抽掉一个 data-orient-part ⇒ 那一条必须**按身份**回来 ----
    # ⚠ 这一条是本组**唯一证明因果**的：M3a 只说「标记在 ⇒ 不在清单」，
    #   M3d 说「标记没了 ⇒ 它**就是**按身份回到清单里」。
    #   前者是相关，后者是因果 —— 少了 M3d，一个「标记加了但其实没起作用」
    #   的页面也能让 M3a 绿。
    print("\n── 步骤 4/4：M3d 抽掉「三 · 你会在这页上遇到的词」的 data-orient-part", flush=True)
    nd = pristine.count(M3D_OLD)
    if nd != 1:
        return finish(1, "源码里 %s 出现 %d 次（要求恰好 1 次）—— 不猜，改完再说"
                      % (M3D_OLD, nd))
    write_src(pristine.replace(M3D_OLD, M3D_NEW))
    # ⚠⚠⚠ **必须先 probe_both() 再 scan()**，顺序照抄 M1。
    #   我第一版写成 write_src → scan() → merged_list()，少了中间那一步，
    #   于是 C0 判「产物比源码旧」并**直接中止扫描**（`RESULT FAIL 1/2`
    #   —— 一条都没跑完），`s3["total"]` 解析成 None，
    #   紧接着那句 print 拿 None 去 %d ⇒ TypeError，
    #   而它崩在 write_src **之后** ⇒ 源码被留在变异态、备份也没了。
    #   ⇒ 三条要记住的：
    #     ① C0 拒绝在过期产物上继续，这是**特性不是故障**；
    #     ② 崩在写盘之后的台子会留残留 ⇒ 收尾永远先查盘上真实状态；
    #     ③ 「变异跑不出来」第一嫌疑是**台子自己写错了**，不是判据坏了。
    #   （probe_both 的 docstring 里早就写着「C0 要求两份产物都比源码新」。）
    rc3, _, _ = probe_both()
    if rc3:
        restore(pristine, base_sha)
        return finish(1, "M3d 变异态下探针跑失败（已还原源码）")
    s3, _out3 = scan()
    if s3 is None:
        restore(pristine, base_sha)
        return finish(1, "M3d 变异态下扫描没打出 RESULT 行（已还原源码）")
    # ⚠ 解析不到就自己判失败，不许拿 None 去 %d（那是 TypeError，不是判决）
    if not (s3.get("parsed") and s3.get("total") is not None):
        restore(pristine, base_sha)
        return finish(1, "M3d 扫描结果解析失败：%s（已还原源码）" % s3)
    items3 = merged_list()
    print("M3d 变异后：真孤儿 %d 段（latent %s / root %s）"
          % (s3["total"], s3["per"]["latent"], s3["per"]["root"]))
    hit3 = [x for x in items3 if x["head"].startswith(M3D_PRE)]
    check("M3d 抽掉那个 h2 的 data-orient-part ⇒ 它**按身份**回到缺口清单里"
          "（这一步才是因果：M3a 只证明了相关）",
          len(hit3) == 1
          and (hit3[0]["tag"], hit3[0]["len"], hit3[0].get("orphan"),
               hit3[0]["page"]) == (M3D_TAG, M3D_LEN, True, "latent"),
          "命中 %d 个" % len(hit3)
          # ⚠ 四个占位符配四元组。上一版这里只写了一个 `%s` 配四元组 ⇒
          #   not all arguments converted，而它是**详情行**、在 write_src
          #   之后求值 ⇒ 崩 ⇒ 源码留在变异态。详情行不是装饰，它在关键路径上。
          + ("　身份 = tag=%s len=%s orphan=%s page=%s"
             % (hit3[0]["tag"], hit3[0]["len"],
                hit3[0].get("orphan"), hit3[0]["page"])
             if len(hit3) == 1 else "　（要求恰好 1 个）"))
    restore(pristine, base_sha)
    # ⚠⚠⚠ 还原后**必须重跑探针**再读清单。
    #   我第一版这里直接 `merged_list()`，而那份 JSON 是上面 `probe_both()`
    #   在**变异态**下产出的 ⇒ 拿变异态的产物判还原后的状态 ⇒ M3e 必然红，
    #   而且红得**像真问题**（「还原后它仍是真孤儿」），实际是台子没重测。
    #   步骤 3（M2）就是先 `restore` 再 `probe_both` 再 `scan` —— 这里照抄它。
    #   ⇒ 「还原」有两件事：把文件写回去，**和**把测量重新做一遍。
    rc4, _, _ = probe_both()
    if rc4:
        return finish(1, "M3d 还原后探针跑失败（源码已还原，但本轮没量到东西）")
    ok4, why4 = assert_orient_11(merged_list(), False, "M3d 还原后")
    check("M3e M3d 还原后它又不是真孤儿了（变异可逆，没把工具永久改成红）",
          ok4 and "三 · 你会在这页上遇到的词" not in why4,
          why4)

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
    try:
        sys.exit(main())
    except BaseException:
        # ⚠⚠ 异常路径**也必须**还原源码。上面每一步的 `return finish(...)`
        #   都记得还原，但**异常绕过了它们全部** —— 一个格式串错误就足以
        #   把 index.html 留在变异态，而症状（「M3d 没跑出结果」）和
        #   「判据坏了」完全同形。
        #   ⇒ 这里自己写回原文，并**自己核对 sha**（不写就算还原过）。
        if _PRISTINE is not None and BASE_SHA:
            write_src(_PRISTINE)
            now = sha256(SRC)
            print("\n⚠ 台子崩在中途，已兜底还原源码：sha256=%s（基线 %s，相同=%s）"
                  % (now[:16], BASE_SHA[:16], now == BASE_SHA), file=sys.stderr)
            if now != BASE_SHA:
                print("⚠⚠ 兜底还原**没成功** —— 需要手工 git checkout "
                      "%s（基线 sha256[:16]=%s）" % (SRC, BASE_SHA[:16]),
                      file=sys.stderr)
        raise
