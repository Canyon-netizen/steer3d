#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据：**每一份已发布产物**都必须说得出「谁在读它」。

## 为什么有这条（§8.9 第二十三笔）

第二十一笔发现 `verify_backmap.mjs` 有 14 条判据却不在门禁里 ——
「有判据但没人跑」。这一条是它的**数据侧**同族：
**产物被渲染着，却没有任何判据读它**。

第一次普查我用 `grep -rl "cot_effect.json"` 找消费方，
结果它「有 1 个判据消费者」——
而那一条其实是在读 `cot_effect_32k.json`，
**`cot_effect.json` 是它的子串**。
⇒ 按子串找「谁引用了这份产物」会给出**虚假的信心**，
  和第十八笔「带 haystack 的 includes 必然假绿」是同一族。
  ⇒ 下面匹配的是**完整文件名**（后跟 JSON 字符串边界），不是子串。

## 四种桶，以及为什么只有两种该判红

    both   页面 + 判据都读        正常
    page   只有页面读              **渲染着，无人核** ← 真缺口
    judg   只有判据读              数据没上页面（可以是刻意的，须自报）
    none   两边都无                死重（或漏了），**必须为 0**

`page` 桶不直接判红，而是**必须写进例外名单并给出理由**：
有的产物确实没有对应面板（那是刻意的），但理由要落在文件里，
不能靠下一个人记得。

## 为什么不用「每个产物都得有面板」当判据

那会把「刻意不渲染」判成缺陷。
⇒ 判据只强制「**例外必须显式**」，不强制「例外不存在」。
"""
import io
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"
PAGE_DIRS = [ROOT / "frontend/public/latent", ROOT / "frontend/components"]
JUDGE_DIRS = [ROOT / ".cache/browser_verify", ROOT / ".cache/xcheck"]

# 已知「只有页面读」的产物 + 为什么。**每加一条都要写理由**，
# 理由要能被下一个人核对，而不是「先放着」。
ALLOW_PAGE_ONLY = {
    "cot_effect.json":
        "① 它提供批次规模（n_runs / n_problems / layer / steps_per_run）"
        "与截断标记，页面上作为背景印出；"
        "② 其中 n_problems 已被 answer_power 的自证 1 与 cot_effect_32k.json 对齐，"
        "但 cot_effect.json 本身没有逐字段判据 ⇒ 这是**已知缺口**，不是「没问题」。"
        "③ ⚠⚠ 第二十三笔更正：这条登记原来只说「页面读了它」，"
        "读起来像是「页面正常展示着，只是没人核」。**真相更糟** —— "
        "承载它的那块（data-cotblock）在第二十三笔之前"
        "**从来没在默认视图里渲染过**（吊在 drawDeltaSide() 的 !S.pMeta 早退后面），"
        "所以它是「页面源码读了、读者永远看不到」。"
        "本轮已把那块搬进 #extras 并加了渲染层判据 W1/W5；"
        "**剩下的缺口只剩「无逐字段判据」这一条**。",
    # divergence_readout.json 原先也在这份名单里（第二十三笔补的判据
    # verify_divergence_readout.mjs 已在跑）。保留这条注释是为了说明
    # K3「不许有过期条目」不是摆设：产物一有判据读了，条目必须删。
}


def sources(dirs):
    out = []
    for d in dirs:
        if not d.is_dir():
            continue
        for pat in ("*.mjs", "*.py", "*.html", "*.tsx", "*.ts"):
            out.extend(sorted(d.glob(pat)))
    return out


def consumers(name, files):
    """谁引用了这份产物 —— 完整文件名，不含子串误配。

    `cot_effect.json` 不应被 `cot_effect_32k.json` 的那几行算成消费方：
    所以要求名字后面紧跟 JSON 字符串的结束边界。
    """
    hits = []
    esc = re.escape(name)
    # ⚠ 第一版写成 `["'`]` + name + `["'`]`，判据里几乎全是**完整路径**引用
    #   （'.../frontend/public/latent/data/token_backmap.json'），
    #   名字前面那个字符是 `/` 而不是引号 ⇒ 全部漏判，
    #   于是普查把 8 份「有判据读」误报成「无判据读」。
    #   ⇒ 左边只要求「不是词字符」，右边仍要求紧跟 JSON 字符串边界 ——
    #     右边这一条是**子串误配**的防线：`cot_effect_32k.json"`
    #     里不会匹配到 `cot_effect.json"`。
    pat = re.compile(r'(?<![\w-])' + esc + r'(?=["\'`])')
    for f in files:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(t):
            hits.append(f.name)
    return hits


def main():
    arts = sorted(p.name for p in DATA.glob("*.json"))
    page_files = sources(PAGE_DIRS)
    judge_files = [f for f in sources(JUDGE_DIRS)
                   if f.name != Path(__file__).name]
    rows = []
    for a in arts:
        p = consumers(a, page_files)
        j = consumers(a, judge_files)
        bucket = ("both" if p and j else "page" if p else
                  "judg" if j else "none")
        rows.append((a, p, j, bucket))

    R = []

    def rec(name, ok, detail):
        R.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}\n       {detail}")

    rec("K0 已发布产物目录存在且非空（普查本身要能跑）",
        len(rows) > 0,
        f"读了 {len(rows)} 份；页面源 {len(page_files)} 个、判据源 {len(judge_files)} 个")

    none = [r[0] for r in rows if r[3] == "none"]
    rec("K1 不得有「页面与判据都不读」的产物（死重或漏了）",
        not none,
        f"{len(none)} 份：{none}" if none
        else f"{len(rows)} 份里没有死重（每份至少有一类消费方）")

    page_only = [r[0] for r in rows if r[3] == "page"]
    undocumented = [a for a in page_only if a not in ALLOW_PAGE_ONLY]
    rec("K2 「只有页面读」的产物必须逐条写进例外名单并给出理由",
        not undocumented,
        f"只有页面读 {len(page_only)} 份：{page_only}；"
        + (f"其中**未登记** {undocumented} ⇒ 下一个人无从判断这是缺口还是刻意"
           if undocumented
           else f"全部 {len(page_only)} 份都在例外名单里且各自带理由"
                "（名单里写的是「已知缺口」，不是「没问题」）"))

    stale = [a for a in ALLOW_PAGE_ONLY if a not in page_only]
    rec("K3 例外名单里不许有过期条目（产物已经有判据读了却还挂着）",
        not stale,
        f"过期 {len(stale)} 条：{stale}" if stale
        else f"名单 {len(ALLOW_PAGE_ONLY)} 条，全部对应当前确实无判据的产物")

    by_b = {}
    for _, _, _, b in rows:
        by_b[b] = by_b.get(b, 0) + 1
    print("\n  消费方分布：", json.dumps(by_b, ensure_ascii=False))
    for a, p, j, b in rows:
        if b != "both":
            print(f"    [{b:4s}] {a:26s} 页面 {len(p)} 处 · 判据 {len(j)} 处")

    n = len(R)
    p = sum(1 for x in R if x)
    print(f"\nRESULT artifact_consumers  {'GREEN' if p == n else 'RED'}  {p}/{n} 条通过")
    return 0 if p == n else 1


if __name__ == "__main__":
    sys.exit(main())
