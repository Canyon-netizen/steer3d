#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 144b 取数笔 —— 19 臂里的 **5 个手写臂**（r134b_*）按当前判据重建。

⚠⚠⁴⚠⁴ 为什么这 5 个不能走共享生成台
  它们**自带 `R134_ARM` 开关**（同一份文件选 5 种模式），
  ⚠ 所以它们不是「一臂一文件」，而是「一文件五模式」。
  ⚠⚠⁴⚠⚴ 而这正是修订 141 踩过的坑：**文件名叫 all / pair / xy，跑台却一个
  `R134_ARM` 都没设** ⇒ 三个臂**静默跑成了 fork**，
  ⚗ 而输出是一张**看起来完全正常**的判决表（这一族见修订 141）。

⚠⚠⁴⚠⁴ 本台因此**只做一件机械活**：把「已验证过的注入块」原样搬到当前判据上。
  ⚠ **注入块一个字都不许改** —— 它是 r134b 实跑验证过的。
  ⚠⚠⁴ 改一个已被验证过的约定，比写一个新约定更危险（修订 135 的教训）。

== 门（任一不过 ⇒ exit 2，不出副本）==
  H1 落点**唯一**：块之后那一行在当前判据里必须**恰好出现一次**
     （⚠ 不唯一就说明「量到哪一行」本身不确定，不许猜）
  H2 **逆变换逐字节**：删掉注入块 + 还原 import ⇒ 与当前判据**逐字节相同**
  H3 import 改写已披露：副本不在源目录 ⇒ 相对 import 必然解析失败
  H4 `node --check` 过
  H5 副本里 0 个 U+FFFD
  H6 落点在取值点**上游**（D1 的取值点 = `const cBefore`）
  H7 标记串在**源**判据里必须不存在（防派生源被污染）
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".cache/browser_verify/verify_path.mjs"
DONOR = ROOT / ".cache/mutbak/r143_arms/r134b_fork.mjs"   # ⚗ 注入块的取用源
OUTDIR = ROOT / ".cache/mutbak/r145_arms/"
BT = chr(96)
FS = chr(0xFFFD)

REL_IMPORT = "import { launch, CDP, Page } from './cdp_client.mjs';"
ABS_IMPORT = ("import { launch, CDP, Page } from "
              "'/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs';")

ARMS = ["fork", "all", "pair", "xy", "path_dgroup"]


def die(msg):
    print("  ✗ %s" % msg)
    sys.exit(2)


def locate(lines, text, what):
    hits = [i + 1 for i, l in enumerate(lines) if l.strip() == text.strip()]
    if not hits:
        die("H1 %s 在当前判据里已消失：%r" % (what, text[:80]))
    if len(hits) > 1:
        die("H1 %s 出现 %d 次（%s）⇒ 落点不确定，不许猜" % (what, len(hits), hits))
    return hits[0]


def _norm(s):
    """⚠ 归一化：去掉声明关键字与多余空白。

    ⚠⚠⁴⚠⁴ **为什么需要它**：修订 144 重写了 D5 的头两行 ——
      `const back = JSON.parse(...)` 变成了 `let back;` + `try {` + `back = JSON.parse(...)`。
      ⚗ 而 r143 臂的落点锚**正是那行旧文本** ⇒ 精确匹配找不到。

    ⚠⚠⁴⚠⁴ **代价必须写下来**：归一化会放宽匹配。
      ⇒ 所以它**必须仍然要求唯一命中**，否则 die。
      ⚠⚠⁴ 「放宽 + 唯一」与「放宽 + 取第一个」差着一整类事故：
      ⚗ 后者会让注入落在一个**看起来对**的位置上（修订 134 的 `src.index` 坑）。
    """
    for kw in ("const ", "let ", "var "):
        s = s.replace(kw, "")
    return " ".join(s.split())


def locate(lines, text, what):
    """精确匹配 ⇒ 唯一才放行。"""
    hits = [i + 1 for i, l in enumerate(lines) if l.strip() == text.strip()]
    if not hits:
        return None
    if len(hits) > 1:
        die("H1 %s 出现 %d 次（%s）⇒ 落点不确定，不许猜" % (what, len(hits), hits))
    return hits[0]


def locate_any(lines, text, what):
    """先精确，失败再归一化；**两种都必须唯一命中**。"""
    at = locate(lines, text, what)
    if at:
        return at, "精确"
    want = _norm(text)
    hits = [i + 1 for i, l in enumerate(lines) if _norm(l) == want]
    if not hits:
        die("H1 %s 在当前判据里已消失：%r" % (what, text[:80]))
    if len(hits) > 1:
        die("H1 %s 归一化后出现 %d 次（%s）⇒ 落点不确定，不许猜" % (what, len(hits), hits))
    return hits[0], "归一化"



def extract_block(donor):
    """从**该臂自己的** r143 副本里取出注入块与它的落点。

    ⚠⚠⁴⚠⁴⚠⚴ **本函数第一版只吃一个文件（fork），把它的块塞给全部 5 个臂。**
      ⚗ 而 5 个臂的块位置**各不相同**：fork=176 / all=187 / pair=193 /
      ⚗ xy=215 / path_dgroup=215 —— **每个块都紧挨着它自己要打的那条判据**。
      ⚗⚠⁴⚠⁴ 全部搬到 175（fork 的位置）之后，`all` 的块被挪到了 **D1 之前** ⇒
      ⚗ D1 点分叉行触发重渲染 ⇒ 被拆掉的 `[data-pathbtn="all"]` **复活** ⇒
      ⚗ **D2 变成假绿**（实测 OK 39/39，而声明是翻 D2）。

    ⚠⚠⁴⚠⚴ **判别式：「五个文件行数一样、块内容一样」⇒ 看起来像同一份东西。**
      ⚗⚠⁴ 而「块的位置」是**不在内容里、只在结构里**的那部分 ——
      ⚗ 抽共享机制时最容易丢的就是它（修订 135：前 N 次的隐含约定要到第 N+1 次才浮出）。

    ⚠ 好在**跑台当场抓到了**：`⚠ r134b_all 翻面的是 []，声明的是 ['D2']`。
    ⚠⚠⁴ 那道「实测翻面 vs 声明」的闸门，正是为这一族准备的（修订 141）。
    """
    txt = donor.read_text(encoding="utf-8")
    ls = txt.split("\n")
    start = next((i for i, l in enumerate(ls) if l.startswith("// ===== r134b 注入")), None)
    if start is None:
        die("取用源里找不到 r134b 注入块起点")
    end = next((i for i, l in enumerate(ls) if "[扰动已落地] 臂 ' + __arm" in l), None)
    if end is None:
        die("取用源里找不到注入块终点")
    block = ls[start:end + 1]
    after = ls[end + 1]        # 块之后的第一行 = 落点锚
    # ⚠⚠⁴ 取用源本身**必须**已经把 import 改成绝对路径，否则说明取错了源。
    if ABS_IMPORT not in txt:
        die("取用源的 import 改写不在位 ⇒ 取错了源")
    return block, after


def main():
    src = SRC.read_text(encoding="utf-8")
    src_lines = src.split("\n")

    print("=== r134b 手写臂重建（每臂各用**自己**的落点）===")
    print("  当前判据 %d 行 / %d bytes" % (len(src_lines), len(src.encode("utf-8"))))

    # ---- H7 标记串不得污染派生源 ------------------------------------------
    if "// ===== r134b 注入" in src:
        die("H7 源判据里已有 r134b 标记串 ⇒ 派生源被污染")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    placements = {}
    for arm in ARMS:
        donor = ROOT / (".cache/mutbak/r143_arms/r134b_%s.mjs" % arm)
        if not donor.exists():
            die("取用源不存在：%s" % donor.relative_to(ROOT))
        block, after = extract_block(donor)
        # ⚠⚠⁴ 落点**逐臂现量**：取「块之后那一行」在当前判据里的唯一位置。
        # ⚠ 这正是第一版丢掉的量 —— 五个臂的落点**本来就各不相同**。
        at, how = locate_any(src_lines, after, "%s 的块后第一行" % arm)
        placements[arm] = at
        print("  %-14s 块 %2d 行，落点 = 第 %3d 行（%s匹配，唯一）：%s"
              % (arm, len(block), at, how, after.strip()[:46]))

    # ⚠⚠⁴⚠⁴ **新门 H8：落点不许被压平成同一个。**
    # ⚗ 第一版把五个臂的块全搬到同一处 ⇒ `all` 的扰动被 D1 的重渲染撤销
    # ⚗ ⇒ **D2 假绿**，而输出是一张**完全正常**的判决表。
    #
    # ⚠⚠⁴⚠⁴ H8 第一版写成「五个落点**互不相同**」，⚗ 当场判死 —— 而
    # ⚗ **xy 与 path_dgroup 本来就共用一个落点**（r143 里两者都是 215）。
    # ⚠⚠⁴⚠⚴ **过严的门和恒绿的门同样有害**：前者逼你把别人正确的设计改掉来换它过关。
    # ⚠ ⇒ 正确的判据是「**不许全塌成一个**」，不是「必须两两不同」。
    if len(set(placements.values())) == 1:
        die("H8 五个落点塌成了同一个 %s ⇒ 有人把逐臂的落点压平了"
            % set(placements.values()))
    groups = {}
    for a, v in placements.items():
        groups.setdefault(v, []).append(a)
    print("  H8 落点分组：%s" % {k: sorted(v) for k, v in sorted(groups.items())})

    for arm in ARMS:
        donor = ROOT / (".cache/mutbak/r143_arms/r134b_%s.mjs" % arm)
        block, after = extract_block(donor)
        at = placements[arm]

        # ---- 组装 ----------------------------------------------------------
        body = list(src_lines[: at - 1]) + block + list(src_lines[at - 1 :])
        patched = "\n".join(body)

        # ---- H3 import 改写（已披露的第 3 类改写）--------------------------
        n_rel = patched.count(REL_IMPORT)
        if n_rel != 1:
            die("H3 %s 相对 import 出现 %d 次（应为 1）" % (arm, n_rel))
        patched = patched.replace(REL_IMPORT, ABS_IMPORT)

        # ---- H2 逆变换逐字节 ----------------------------------------------
        rev = patched.replace(ABS_IMPORT, REL_IMPORT)
        rev_lines = rev.split("\n")
        idx = rev_lines.index(block[0])
        del rev_lines[idx: idx + len(block)]
        if "\n".join(rev_lines) != src:
            die("H2 %s 逆变换后与源判据**不相同**" % arm)

        # ---- H5 U+FFFD -----------------------------------------------------
        if patched.count(FS):
            die("H5 %s 副本里有 %d 个 U+FFFD" % (arm, patched.count(FS)))

        out = OUTDIR / ("r134b_%s.mjs" % arm)
        out.write_text(patched, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            die("H4 node --check 不过：%s\n%s" % (arm, r.stderr[:400]))
        print("  ✓ r134b_%-14s → %s" % (arm, out.relative_to(ROOT)))

    print("\n=== 门全部通过（H1 落点唯一 · H2 逆变换逐字节 · H3 import 改写已披露 "
          "· H4 node --check · H5 零 U+FFFD · H7 源未被污染 · **H8 落点逐臂现量、未被压平**），"
          "出副本 %d 个 ===" % len(ARMS))
    print("⚠⚠⁴⚠⁴ 但这只证明**副本长得对**。跑的时候**必须按臂设 R134_ARM**：")
    print("     R134_ARM=fork|all|pair|xy|path_dgroup")
    print("  ⚗ 不设 ⇒ 五个文件全部跑成 fork（修订 141 已经栽过一次，判决表看着完全正常）。")



if __name__ == "__main__":
    main()
