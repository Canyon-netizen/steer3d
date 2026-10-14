#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 182 追加脚本 —— 判决流水线 + 候选池推进到 4/19。

本节三块：
  182.1 候选池 4/19：A=1 B=3 C=0（p09 新增，仍是 B）
  182.2 新增 r182_verdict_pipeline.py：把「跑满那一刻」的手工链固化成有闸的编排
  182.3 写这个脚本时自己踩的两个洞（都已在提交前修掉并复测）
"""

from pathlib import Path

SECTION = """
## 修订 182 —— 候选池 4/19（A=1 B=3 C=0）；判决流水线固化为 r182_verdict_pipeline.py

### 182.1 候选池 4/19：已跑完的候选**全部是 wrong**

新批已到 20/60（p00..p09 各两臂）。候选池四态更新：

| 题 | 新 n_tok | 触顶 | 归宿 |
|---|---:|---|---|
| p04 | 20360 | 否 | B 跑完但 wrong |
| p06 | 32768 | 是 | A 仍触顶，仍 unlabeled |
| p08 | 23338 | 否 | B 跑完但 wrong |
| **p09** | **16858** | **否** | **B 跑完但 wrong** |

即：**跑完的 3 条候选，正确 0 条。**

已测段分母 4（A=1 B=3 C=0），转化率 0.0%。
⚠ 这**不是** P6 结论（§167：数据没跑完不许给结论，当前 20/60）。
⚠ 它现在的作用只有一个：**把「抬 cap 之后会冒出多少 correct」这个问题从
⚠ 「未知」推向「大概率接近 0」**——4 条样本很小，不足以定论，但方向一致。

全池口径（修订 179 钉死）：旧批全池 correct = 7，P6 底线 10，缺口 **3**。
剩余 15 条未测候选里需要产 **≥3 correct**。

标签漂移同步复跑（修订 181 的检查）：已确立标签 **16/16 保持，0 处翻转**
（think 6/6、no_think 10/10）。归因性仍然干净。

### 182.2 新增 `r182_verdict_pipeline.py` —— 跑满那一刻不再靠手工链

判决那一刻原本是 5 个手工步骤（远端数文件 → 标注 → 拉回 → 过闸 → 出判决）。
每一步都是一个机会：读到旧文件、跑错顺序、跳过闸。

⚠ 这不是假想风险：修订 180 已经实测到 `p6_readiness.py` 在部分数据上
会印「别急着去取数据 / 这是设计问题」—— 说明这条链**确实**会被误用。

八步编排与放行规则：

| 步 | 做什么 | 红了怎么办 |
|---|---|---|
| 1 | ssh 数远端产物条数 | 未跑满且无 `--allow-partial` ⇒ 立即停，**不做任何标注** |
| 2 | 远端 `strict_label_r167.py` 标注 | 失败即停 |
| 3 | scp 拉回 | 失败即停 |
| 4 | `r180_p6_precond` 结构/身份闸 | **停止**，不跑 p6_readiness |
| 5 | `r177_batch_identity` 身份闸 | **停止**，判决作废 |
| 6 | `r181_label_drift` 观测 | 打印警告，**不阻断**（它是测量结果，不是闸） |
| 7 | `r178_uncapped_fate` 权威口径 | 失败即停 |
| 8 | `p6_readiness` 判决仪器 | **只有跑满才允许跑** |

关键设计：**第 8 步在 `--allow-partial` 下是结构上被拒绝的**，
不是「跑了再判断」。退出码：`0` 全部按预期 / `4` 有闸红或未跑满 / `2` 环境错。
另有 `--dry-run` 只列计划不连远端。

### 182.3 写这个脚本时自己踩的两个洞（提交前已修并复测）

**洞一：闸把自己要守的性质当成了阻断理由。**
第一版在增量模式下也把 `60` 传给第 4/5 步，于是两道闸**必然**红，
脚本在第 4 步就 `return BLOCKED`，**永远到不了**第 6/7 步的增量测量。
⇒ 增量模式改成：闸按**已存在的成对完整题数**验身份（仍有分辨力），
   跑满与否由第 8 步单独把关。职责拆开：「身份对不对」归闸，「跑满没跑满」归第 8 步。

**洞二：行数竞态。**
步骤 1 数完条数到步骤 3 拉回标注之间，生成仍在推进，两次数的条数可能不同。
⇒ 改为**以拉回的实际行数为准**，并把「与步骤 1 的差异」当竞态指标印出来。
⚠ 若拉到奇数条，说明有一道题只出了一臂，此时闸按实际行数验身份，
⚠ 第 8 步仍被拒绝。

复测（20/60，`--allow-partial`，退出码脱离管道量）：
`RESULT pipeline DONE n=20 mode=partial`，第 8 步印「跳过（不是失败，是设计）」；
完整模式同状态 ⇒ `RESULT pipeline NOT-READY 20/60`，且**没有做任何标注**。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 182 ")),
    ("含本节入口", lambda s: "182.3 " in s),
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