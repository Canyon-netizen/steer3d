#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 181 追加脚本 —— 旧批 vs 新批的混淆项检查。

本节回答一个问题，且只回答这一个问题：
    新批（cap 32768）与旧批（cap 8192）在**同一批题、同一臂**上，
    旧批已经确立的标签有没有被重跑扰动？

为什么必须先关掉它：
    P6 要比较的是「旧批 correct 数」与「新批 correct 数」。
    如果重跑本身会把 correct 翻成 wrong，那么两批 correct 数之差
    就同时混着「抬 cap 的效果」与「重跑的扰动」两件事，
    分不开就不能归因。§167 的读数规则管的是「不许提前下结论」，
    本节管的是「数据到齐之后，那个结论到底能不能这么读」。
"""

from pathlib import Path

SECTION = """
## 修订 181 —— 混淆项检查：18 条同题同臂可比，旧批已确立标签 0 处翻转

### 181.1 本节只回答一个问题

新批（cap 32768）与旧批（cap 8192）在**同一批题、同一臂**上可比的有 18 条
（p00..p08 × think/no_think）。把旧标签 -> 新标签的转移矩阵列全：

| 旧标签 | -> 新标签 | 条数 |
|---|---|---:|
| correct | correct | 7 |
| wrong | wrong | 8 |
| unlabeled | unlabeled | 1 |
| unlabeled | wrong | 2 |

**correct -> wrong = 0 条，wrong -> correct = 0 条。**

不一致的只有两条，且两条都是 `unlabeled -> wrong`：

| 题 | n_tok | truncated |
|---|---|---|
| aime25 p04 think | 8192 -> 20360 | True -> False |
| aime25 p08 think | 8192 -> 23338 | True -> False |

### 181.2 关键那条：已确立标签 15/15 保持

把分母限定在「旧批本来就**不是** unlabeled」的那 15 条上（这才是「重跑会不会扰动
已确立事实」的真正问法）：

| 臂 | n | 一致 | 不一致 |
|---|---:|---:|---:|
| think | 6 | **6** | 0 |
| no_think | 9 | **9** | 0 |

think 侧明细：5 correct 保持 correct、1 wrong 保持 wrong。
no_think 侧明细：2 correct 保持 correct、7 wrong 保持 wrong。

=> **重跑没有扰动任何一条已确立标签。**
=> 因此 P6 的 correct 数之差**不能**归因于「重跑扰动」，
   两批之差只剩「抬 cap」这一个变量。

⚠ 这个结论的适用范围要说死：它只覆盖**已生成的 p00..p08 这 9 题**。
⚠ 剩余 21 题尚未生成，届时本节要**重跑一遍**，不能拿现在这条当全池结论。

### 181.3 附带量到的一个结构事实

新批 9 题里 `no_think` 触顶 **0/9**（n_tok 441 ~ 4014，`truncated` 全为 False），
而 `think` 触顶 1/9。

=> **截断是 think 臂特有的。**
=> 修订 178 的 19 条候选池本来就只是 think 臂的，这一条把它坐实了：
   no_think 对 P6 的贡献恒为 0，不是因为它答错，是因为它根本不触顶。

⚠ 这一条**不**意味着 no_think 可以从流程里去掉：P0 明写不合并判，
⚠ 而 no_think 仍要作为对照臂跑满 30 题。

### 181.4 本节仍然不含 P6 结论

§167 读数规则不变：数据没跑完（当前 18/60）不许给 P6 结论。
本节给出的是**可归因性**，不是**结论**：

- 可以说的：旧批已确立标签未被扰动 ⇒ 抬 cap 是两批 correct 数之差的唯一变量
- 还要等：剩余 16 条候选的归宿（当前已测 3 条 A=1 B=2 C=0，见修订 180.2），
  以及全池 correct 是否够 10（缺口 3，见修订 179）

引用规则不变：P6 相关数一律以 `r178_uncapped_fate.py` 为准（修订 179）。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 181 ")),
    ("含本节入口", lambda s: "181.4 " in s),
)


def main():
    target = Path(__file__).resolve().parents[2] / ".cache/xcheck/R6_RERUN_PREREG.md"
    before_lines = len(target.read_text(encoding="utf-8").splitlines())

    bad = [name for name, fn in PRECHECKS if not fn(SECTION)]
    if bad:
        print("[前置检查失败] " + " / ".join(bad))
        return 2

    with target.open("a", encoding="utf-8") as fh:
        fh.write(SECTION)
    after_lines = len(target.read_text(encoding="utf-8").splitlines())

    print("追加完成：%d -> %d 行（+%d）" % (before_lines, after_lines,
                                        after_lines - before_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())