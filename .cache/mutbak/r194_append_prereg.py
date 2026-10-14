#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 194 追加脚本 —— 跑满 60/60，P6 完整判决 ELIGIBLE。

本节四块：
  194.1 跑批收官与完整判决
  194.2 ⛔ ELIGIBLE 不等于「P6 通过」——判决仪器自己印的那句话
  194.3 ⚠⚠ 功效披露：wrong 组只有 17 条
  194.4 修订 193 的修正在这次完整跑里被直接验到
"""

from pathlib import Path

SECTION = """
## 修订 194 —— ✅ 跑满 60/60，**P6 完整判决 ELIGIBLE**（think correct=11 ≥ 10）

远端生成 00:12:00 `exit=0` 结束，`gen_b2_max32768/aime/` = **60/60**。
⚠⇒ §167 的「数据没跑满不给结论」前置**已解除**，本节是本批第一次可以
⚠⇒ 对整批下结论的地方。

### 194.1 完整模式判决（不带 `--allow-partial`）

    RESULT p6_readiness  ELIGIBLE  think correct=11 wrong=17      EXIT=0
    RESULT pipeline  DONE  n=60  mode=full
    汇总：完整性闸 0 · 身份闸 0 · 漂移 EXIT=4 · 口径 0

最终数字（60/60，cap 全 32768）：

| 量 | 值 |
|---|---|
| think | n=30，**correct=11**，wrong=17，unlabeled=2，触顶 4（13%） |
| no_think | n=30，correct=4，wrong=23，unlabeled=3，触顶 3（10%） |
| 幻觉（D1 红） | **0** |
| 候选池归宿 | A=3 · B=13 · C=3 = **19 全测完，未测 0** |
| 两路贡献 | 锁死 **8** + 落袋 **3** = 到手 **11** ⇒ 缺口 **0** |

⚠ 最后一条是 p29（`n_tok 21505`），归宿 **B 跑完但 wrong**
⚠⇒ correct 从 58/60 时的 11 **保持 11**，没有再涨。
⚗⚠ 终点值与 52/60 时的单调下界（≥10）一致，**下界没有被打破**。

⚠⚠ **两份独立标注互验**：流水线自己远端重标得
⚠⚠ `r182_1015_003713_label.json`，我另拉一份 `r194_label.json`，
⚠⚠ 两者 md5 相同（`1be444e5…`）、60 行**逐行一致** ⇒ 标注可复现。

⚠ **流水线 EXIT=4 的含义**：`EXIT=4` 来自 `r181_label_drift` 那一步
⚠（漂移 1 条：p18 `wrong -> correct`）。它是**混淆项观测，红不阻断**
⚠ —— 流水线照常跑到了步骤 8 并出了判决。
⚗⚠ **退出码非零 ≠ 崩**：这里它是「有一处必须披露的混杂」，不是失败。

### 194.2 ⛔ `ELIGIBLE` 不等于「P6 通过」

判决仪器自己在同一段输出里印了这句：

    ⚠⚠⚴ 本脚本不代跑 P6 —— 它只判「够不够资格算 p 值」。

⚠⚠⚴ **必须照抄进报告，不能只写「ELIGIBLE」**：
⚠⚠⚴ `ELIGIBLE` 的全义是「**样本量够资格进入 P6 检验**」，
⚠⚠⚴ **不是**「P6 检验通过」、也不是「结论成立」。
⚗⚠ 后面那一步（本脚本**不代跑**）才是 P6 本身，尚未执行。

### 194.3 ⚠⚠ 功效披露：wrong 组只有 17 条

同一段输出：

    ⚠⚠⚴⚠⚠ 且 wrong 组只有 17 条：⚗ P6 没给 wrong 设底线，
    但 n=17 做 U 检验功效极低 —— ⚗⚠⚠ 这一格必须在报告里显式披露，
    ⚠⚠⚴ 不许只报 correct 够格。

⚠⚠⚴ **P6 只给 correct 组设了底线（≥10），没给 wrong 设。**
⚠⚠⚴ ⇒ 「correct=11 ≥ 10 ✅」这一格过得很轻松，
⚠⚠⚴ 但**对照格 n=17 已经很薄**，U 检验功效极低。
⚗⚠ **只报「ELIGIBLE」而不报这一句，就是仪器明文禁止的那种报法。**

### 194.4 修订 193 的修正在这次完整跑里被直接验到

⚠⚠⚴ 修订 193 修的正是 `r178` 的「只数锁死那一路」。
⚠⚠⚴ 若那个缺陷还在，**这一次完整跑的输出会自相矛盾**：

    r178（权威口径）      ⇒ 还需 correct = 2      ← 缺陷版
    p6_readiness（判决）  ⇒ ELIGIBLE correct=11  ← 实际

⚗⚠ 同一份流水线里，**权威口径说还差 2、判决仪器说够格了**，
⚗⚠ 而两者读的是同一个标注文件。
⚠⇒ 修订 193 的修正在这一跑里**被真实数据直接验到**，不是自证。

⚠⚠⚴⚠ 顺带记一条**同族的方法论教训**（修订 193 的修法给的）：
⚠⚠⚴⚠ **`p6_readiness.py` 之所以一直没暴露这个缺陷，是因为它数的是
⚠⚠⚴⚠ raw correct、不分来源** ⇒ 它一直是对的。
⚠⚠⚴⚠ 错的只有那个「按来源拆开算缺口」的 `r178`。
⚗⇒ **「多拆一维」既让 r178 更精确，也让 r178 更容易漏项** ——
⚗⇒ 拆开的那几维之间**不是独立的**，而修法只当它们独立。

### 194.5 本节的边界

✅ 可以说的：**本批 60/60 跑满，correct=11 ≥ 底线 10，够格进入 P6 检验。**
⛔ 不能说的：
  1. ⛔ **「P6 通过」** —— P6 本身还没跑（194.2）。
  2. ⛔ **「抬 cap 带来了 X 的提升」** —— 漂移 1 条 + 单批，
     ⚠⚠⚴ 两批 correct 数之差**不能**直接归因于抬 cap（`r181` 原文警告）。
  3. ⛔ 任何**功效层面**的结论（wrong n=17，见 194.3）。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 194 ")),
    ("含本节入口", lambda s: "194.5 " in s),
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
