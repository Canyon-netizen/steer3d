#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 199 追加脚本 —— 把可分辨性闸接进流水线（否则它就是第二个死开关）。

本节三块：
  199.1 修订 198 那道闸当时**没有任何东西调用** —— 与 P9 同一个病
  199.2 接法：可选闸 + 未查时必须自报未查；四参数缺一即拒
  199.3 双向验证
"""

from pathlib import Path

SECTION = """
## 修订 199 —— 把可分辨性闸**接进流水线**，否则它就是第二个死开关

### 199.1 修订 198 那道闸，当时**没有任何东西调用**

⚠⚠⚴ 修订 198 交付了 `p6_resolvability.py`（自检 12/12，能对 `new_p2a` 判红、
⚠⚠⚴ 对 `armB` 判绿）。但它**没有被任何流程调用**。

⚠⚠⚴⚠ **这与修订 195 修掉的那个 P9 是同一个病，一模一样：**

| | P9（修订 195） | 可分辨性闸（修订 198） |
|---|---|---|
| 算出来了 | ✅ | ✅ |
| 打印了 | ✅ | ✅ |
| 存进产物了 | ✅ | ✅ |
| ⚗ **接到出口了吗** | ⛔ 没有 | ⛔ **当时也没有** |

⚗⚠⚴ **闸本身不是闸。** 一个只有自检调用它、主流程从不调用它的检查，
⚗⚠⚴ 在**真实判决路径上**与不存在无异 —— 它只在自己的自检里绿。
⚗⚠⚴ 而自检是**固定输入**，跑一万遍也不会替真实判决把关。

⚠⚠⚴ 讽刺之处：修订 195 的整节就是在讲「解析了不等于用上了 — 死开关」，
⚠⚠⚴ ⚗ 而修订 198 **又造了一个**。⇒ 本节修。

### 199.2 接法：可选闸 + **未查必须自报**

闸的输入（`--w-unembed` / `--w-meta`）是**实验级**的 ——
P2a 重训 w 与 P2b 迁移 w 各一份，标注阶段还不存在。
⇒ 不能做成无条件步骤，否则会卡死标注流水线。

接法三条：

1. **四个参数齐 ⇒ 跑闸；`BELOW_FLOOR` ⇒ `BLOCKED`，不跑 P6 全量**
   （`RESULT pipeline BLOCKED below-resolution`，退出码 4）。
2. **四个都不给 ⇒ 不阻断，但必须打印「未检查」并写明后果**：
   ⚠「`p6_readiness` 印 ELIGIBLE 只说明**样本量够**（correct≥10），
   ⚠⚗ **不等于**那个量测得出来」。
3. ⛔ **只给一部分 ⇒ 直接 `EXIT_USAGE`**，理由写死：
   ⚠「只给一部分 = 闸没跑，却像是跑过」。
   ⚗⚠ 这一条防的是最阴的一种形态：**参数拼错导致闸被静默跳过，
   ⚗⚠ 而流程照样一路绿到底。**

⚗⚠ `--logit-mag` 仍然**没有默认值**（沿用修订 198）：
⚠⚠⚠ 静默用一个猜的 logit 量级 = 偷偷替读数定口径。

⚠ **`--dry-run` 也如实列出 7.5**，并标出「本次未给四个参数 ⇒ 该闸**不跑**」——
⚠ 计划表里写着的闸和实际跑的闸必须一致。

### 199.3 双向验证

| 方向 | 输入 | 期望 | 实测 |
|---|---|---|---|
| A 部分参数 | 只给 `--w-unembed` | **EXIT 2** + 「给了 1/4」 | ✅ EXIT=2 |
| B 全不给 | `--dry-run` | 计划列出 7.5 且标「不跑」 | ✅ |
| C 四个齐 | `--dry-run` + 四参数 | 计划列出 7.5 且**不**标「不跑」 | ✅ |
| D 既有流程 | `--dry-run` | 步骤 1–8 一字不变、退出 0 | ✅ |

⚠⚠⚴ **D 那条最容易漏**：加一道闸最常见的副作用是**把既有流程弄坏**。
⚗⚠ 本节专门验了「不给参数时旧路径完全不受影响」，而不只验「新闸能跑」。

⚠ 闸本身的判红/判绿由 `p6_resolvability_selftest.py` 12 项负责（修订 198），
⚠ 本节只负责**接线**，两件事分开验。

### 199.4 边界

✅ 可说：可分辨性闸已接进 `r182_verdict_pipeline.py` 的判决路径；
   BELOW_FLOOR 会阻断 P6 全量；未给参数时明确自报未检查；
   只给部分参数会被拒；`--dry-run` 与实际执行的步骤一致。
⛔ 不可说：
  1. ⛔ 「P6 已可跑」—— 闸只是把「不可测」显式化，**没有**让量变大。
  2. ⛔ A/B/C/D 任一条已被选定（仍待拍板，修订 197 §197.4）。
  3. ⛔ 本节改了预登记的任何口径 —— 剂量阶梯、注入层、训练位置一字未动。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 199 ")),
    ("含本节入口", lambda s: "199.4 " in s),
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
