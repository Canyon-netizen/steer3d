#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从预登记本身生成修订索引。

⚠⚠ 本脚本**不写预登记** —— 预登记是只追加的，索引不能塞到它前面
  ⇒ 索引是一个**独立文件**，每次从预登记重新生成。

⚠⚠⚴ 标题格式有**三种**（第一版只认一种，漏掉 60 条）：

  形式 1   ## 修订 13：…              —— 覆盖 1–12、42–52、82–99
  形式 2   ## 13.0 起因：…            —— 覆盖 13–32（编号与小数点直接相连）
  形式 3   ## 33. 修订 33：E 批次…    —— 覆盖 33–40、53–81

  ⚠ 判别顺序很要紧：`## 33. 修订 33：` 既像形式 3 又会被
    「数字. 数字」的宽松规则抢走 ⇒ 形式 3 必须**先于**形式 2 判定。

⚠ 修订 48–52 各有**两段**（「判据」+「取数与落地」），
  **这不是重复条目，是两笔 commit** ⇒ 索引里合并成一条并标出两段行号。

⚠ 本脚本只读预登记，不碰它。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / ".cache/xcheck/R6_RERUN_PREREG.md"
OUT = ROOT / ".cache/xcheck/R6_RERUN_INDEX.md"
GEN = ".cache/mutbak/r100_build_index.py"


def classify(body):
    """返回 (kind, rev_num, sub_num)。kind ∈ {rev1, rev3, rev2, base, other}"""
    m = re.match(r"^修订\s*(\d+)", body)
    if m:
        return "rev1", int(m.group(1)), None
    m = re.match(r"^(\d+)\.\s*修订\s*(\d+)", body)      # ⚠ 必须先于 rev2
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a != b:
            return "other", None, None                    # 编号自相矛盾
        return "rev3", a, None
    m = re.match(r"^(\d+)\.(\d+)\s", body)             # 形如 13.0
    if m:
        return "rev2", int(m.group(1)), int(m.group(2))
    return "base", None, None


def main():
    if not PREREG.exists():
        print(f"[错误] 找不到预登记 {PREREG}")
        sys.exit(2)
    raw = PREREG.read_text(encoding="utf-8")
    lines = raw.split("\n")
    # ⚠⚠⚴ `split("\n")` 会把末尾换行之后那个空串也算成一个元素
    #   ⇒ len(lines) 比真实行数（`wc -l`）多 1。
    #   生成修订 137 的索引时踩到：修订 137 是第一条「后面没有下一条标题」的修订，
    #   end2 落到 len(lines) ⇒ 它的行号尾号多 1；:112 的总行数更是每一笔都多 1
    #   （此前各笔都印 18,XXX 而 `wc -l` 少 1，无人核）。
    nlines = len(lines) - 1 if raw.endswith("\n") else len(lines)

    heads = []      # (line_idx, kind, rev, sub, body)
    for i, ln in enumerate(lines):
        if not ln.startswith("## "):
            continue
        body = ln[3:].strip()
        kind, rev, sub = classify(body)
        heads.append((i, kind, rev, sub, body))

    rev_heads = [h for h in heads if h[1].startswith("rev")]
    base_heads = [h for h in heads if h[1] == "base"]
    other = [h for h in heads if h[1] == "other"]
    if not rev_heads:
        print("[错误] 一条修订标题都没解析到 ⇒ 格式又变了，不发数")
        sys.exit(2)
    if other:
        print(f"[错误] 有 {len(other)} 条编号自相矛盾的标题，不发数：")
        for i, _k, _r, _s, b in other[:5]:
            print(f"   {i+1}  {b[:70]}")
        sys.exit(2)

    # 按修订号聚合。⚠⚠ 同一个修订号下的多条 `##` 有**两种性质**，
    #   混在一起会得出错误的结论：
    #     (a) rev2 形式（`## 13.0`/`## 13.1`…）= 同一修订的**小节**
    #     (b) rev1/rev3 形式再次出现 = 同一修订的**第二笔 commit**（判据 + 落地）
    by_rev = {}
    for i, kind, rev, sub, body in rev_heads:
        by_rev.setdefault(rev, []).append((i, kind, sub, body))
    nums = sorted(by_rev)

    def split(v):
        subs = [x for x in v if x[1] == "rev2"]
        segs = [x for x in v if x[1] != "rev2"]
        return subs, segs

    multi_seg, multi_sub = {}, {}
    for n, v in by_rev.items():
        subs, segs = split(v)
        if len(segs) > 1:
            multi_seg[n] = segs
        if len(subs) > 1:
            multi_sub[n] = subs
    gaps = [i for i in range(1, max(nums) + 1) if i not in by_rev]

    fmt_count = {}
    for _i, kind, _r, _s, _b in rev_heads:
        fmt_count[kind] = fmt_count.get(kind, 0) + 1

    o = []
    w = o.append
    w("# R-6 预登记修订索引")
    w("")
    w(f"> **自动生成，勿手改。** 生成器：`{GEN}`（先跑它）")
    w(f"> 数据源：`.cache/xcheck/R6_RERUN_PREREG.md`")
    w("")
    w("## 规模")
    w("")
    w(f"- 预登记 **{nlines:,} 行**、**{raw.count(chr(0xfffd))} 个坏字**（`U+FFFD`）")
    w(f"- 修订 **{len(nums)} 条**，编号 1–{max(nums)}，"
      f"**缺口 {gaps if gaps else '无'}**")
    w(f"- 其中 **{len(multi_sub)} 个修订**用 `## N.M` 小节式展开"
      f"（{sorted(multi_sub) if multi_sub else '无'}）")
    w(f"- **⚠ 与上面完全是两回事**：另有 **{len(multi_seg)} 个修订**"
      f"（{sorted(multi_seg) if multi_seg else '无'}）"
      f"在同一编号下出现**两笔 commit**（判据 + 取数与落地）"
      f"—— 那**不是**重复条目，索引里两段都列")
    w(f"- 另有 **{len(base_heads)} 条 `## N.` 基础章节**（§0 为什么要重跑、"
      f"§1 判决规则、§2 算力预算、§3 明确不做的事、§4 已知风险），不在本索引内")
    w("")
    w("## ⚠ 三种标题格式（第一版索引只认一种，漏掉 60 条）")
    w("")
    w("| 形式 | 样例 | 条数 |")
    w("|---|---|---:|")
    w(f"| 1 | `## 修订 13：…` | {fmt_count.get('rev1', 0)} |")
    w(f"| 2 | `## 13.0 起因：…`（编号与小数点直接相连） | {fmt_count.get('rev2', 0)} |")
    w(f"| 3 | `## 33. 修订 33：…` | {fmt_count.get('rev3', 0)} |")
    w("")
    w("⚠ **判别顺序**：形式 3 必须**先于**形式 2 判定 ——")
    w("`## 33. 修订 33：` 会被「数字. 数字」的宽松规则抢走。")
    w("")
    w("## ⚠ 本索引的局限")
    w("")
    w("1. ⚠ **行号会过期**：预登记只追加，已有修订的行号不变，"
      "但**追加新修订后本文件不会自动更新**，必须重跑生成器。")
    w("2. ⚠ 只给**标题**（标题即摘要），**不给结论、不给数字** —— 数字以正文为准。")
    w("3. ⚠ 「⚠ 待用户拍板」的条目**不在标题里**，用 "
      "`grep -n '交用户拍板' .cache/xcheck/R6_RERUN_PREREG.md` 另找。")
    w("")
    w("## 修订一览")
    w("")
    w("| 修订 | 行范围 | 行数 | 结构 | 标题 |")
    w("|---:|---|---:|---|---|")
    emitted = []
    for n in nums:
        v = by_rev[n]
        start = v[0][0] + 1
        subs, segs = split(v)
        nxt = [i for i in nums if by_rev[i][0][0] > v[0][0]]
        # ⚠⚠⚴ 行范围口径（2026-10-13 修）：
        #   start = 本修订标题的 1-based 行号
        #   end2  = 本修订**最后一行非空行**的 1-based 行号（从下一条标题处向后跳过空行）
        #   span  = end2 - start + 1（本修订占的行数，不含下一条标题前的分隔空行）
        #   原写法 `end2 = 下一条标题的 0-based 下标` 对**最后一条**修订不成立：
        #   那时没有下一条，落 `len(lines)`，而 `len(lines)` 把末尾换行后的空串
        #   也算成一行 ⇒ 修订 137 的尾号被印成 18722（真实末行是 18721）。
        lim = by_rev[nxt[0]][0][0] if nxt else nlines   # 下一条标题 0-based 下标 / 真实行数
        j = lim - 1
        while j > v[0][0] and not lines[j].strip():
            j -= 1
        end2 = j + 1
        span = end2 - start + 1
        emitted.append((n, start, end2, span))
        if subs and segs:
            struct = f"小节×{len(subs)} + 段×{len(segs)}"
        elif subs:
            struct = f"小节×{len(subs)}"
        else:
            struct = f"段×{len(segs)}"
        t = v[0][3].replace("|", "\\|")
        if len(t) > 82:
            t = t[:82] + "…"
        w(f"| {n} | {start}–{end2} | {span} | {struct} | {t} |")
    w("")
    w("## ⚠「两笔 commit」的修订（判据 + 落地，与上面的「小节」不是一回事）")
    w("")
    for n in sorted(multi_seg):
        w(f"- **修订 {n}**")
        for i, kind, sub, body in multi_seg[n]:
            w(f"  - 行 {i+1}：{body[:74]}")
    w("")
    w("## 用 `## N.M` 小节展开的修订（小节数前 10）")
    w("")
    for n in sorted(multi_sub, key=lambda x: -len(multi_sub[x]))[:10]:
        w(f"- **修订 {n}**（{len(multi_sub[n])} 个小节）"
          f"：{multi_sub[n][0][3][:64]}")
    w("")

    OUT.write_text("\n".join(o) + "\n", encoding="utf-8")
    txt = OUT.read_text(encoding="utf-8")
    ends_nl = OUT.read_bytes().endswith(b"\n")
    print(f"已写出 {OUT}")
    print(f"  修订 {len(nums)} 条 / 缺口 {gaps or '无'}")
    print(f"  小节式 {len(multi_sub)} 个 / 两笔 commit {sorted(multi_seg)}")
    print(f"  坏字 {txt.count(chr(0xfffd))} / 以换行结尾 {ends_nl}")
    if txt.count(chr(0xfffd)) or not ends_nl:
        print("[错误] 生成物有问题")
        sys.exit(2)

    # ⚠⚠⚴⚠⚴ 自检闸门：索引里每一行的 (start, end2, span) 必须与预登记**逐字对得上**。
    #   起因：这一族 off-by-one 在同一个文件里犯了两次 ——
    #     ① `len(lines)` 把末尾换行后的空串算成一行 ⇒ 最后一行的尾号/总行数多 1；
    #     ② `span = end2 - start` 在「下一条修订标题前没有空行」的段落少算 1
    #        （实测 9 行：修订 100、110–117）。
    #   两次都是**仪器自己发绿**：脚本正常退出、坏字 0、以换行结尾，一句都没报错。
    #   ⇒ 打印「行数对得上」之前必须逐行对账，不许只看汇总。
    rev_head_lines = {i + 1 for i, kind, _r, _s, _b in rev_heads}
    problems = []
    for n, s, e, sp in emitted:
        why = []
        seg = lines[s - 1:e]                      # 1-based 闭区间切片
        if len(seg) != sp:
            why.append(f"切片 {len(seg)} 行 ≠ span {sp}")
        if not lines[s - 1].startswith("## "):
            why.append("start 不是标题行")
        if not seg[-1].strip():
            why.append("末行是空行")
        if e > nlines:
            why.append("end 越过末行")
        elif lines[e].strip() and not (lines[e].startswith("## ")
                                       and (e + 1) in rev_head_lines):
            why.append("区间外紧跟的内容既非空行也非下一条标题行")
        if why:
            problems.append((n, why))
    print(f"  行范围自检 {len(emitted)} 行 / 不合口径 {len(problems)}")
    if problems:
        for n, why in problems[:20]:
            print(f"    修订 {n}：{'；'.join(why)}")
        print("[错误] 行范围与预登记对不上，不算通过")
        sys.exit(2)


if __name__ == "__main__":
    main()
