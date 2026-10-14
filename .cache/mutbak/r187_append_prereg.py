#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 187 追加脚本 —— 用户拍板「1 修了」：p6_readiness.py 两条缺陷已修。

本节三块：
  187.1 缺陷一：补完整性守卫（EXIT=6），四方向证伪
  187.2 缺陷二：「6–7 条」按 cap 条件化，两个分支都验过
  187.3 未改的东西 + 一个被证伪的夹具 + 一个未修的小口子
"""

from pathlib import Path

SECTION = """
## 修订 187 —— 用户拍板「1 修了」：p6_readiness.py 两条缺陷已修并四向证伪

拍板记录：`1修了2改3跑` ⇒ 第 1 项修、第 2 项改、第 3 项跑。
⚠ 第 4、5 项（C4 的 87 条、C6 的 9 条）**本轮未提及，按原状不动**，不擅自扩大范围。

本节两条缺陷的原始记录见修订 180.3，修复方案见修订 180.6。

### 187.1 缺陷一：补完整性守卫，`EXIT_INCOMPLETE = 6`

在身份检查通过之后、**任何判决之前**插入：

    停止规则要求每个 benchmark 的 think 臂各 30 条；
    实测不足或超出 => 打印缺口明细 + 拒绝出判决，EXIT=6

⚠ 守卫的判据写成 `!= 期望规模`，不是 `< 阈值`：
⚠ **多于期望同样是数据不对**（混批 / 重复），只挡「不足」那一种是不够的。

⚠⚠⚴ **退出码为什么用 6 而不是复用 3**：

| 码 | 含义 |
|---|---|
| 3 UNDERPOWERED | 跑够了，但 correct 数不够格 |
| **6 INCOMPLETE** | **还没跑完，判决这件事本身还不存在** |

⚠ 两者若共用一个码，事后从日志里**分不出「结论成立」和「数据没到」**。
⚠ 而这正是修订 180.3 那次事故的本质：18/60 时印的 `EXIT=3` 长得像「判决」。

### 187.2 缺陷二：「6–7 条」按 cap 条件化，两个分支都验过

原样是无条件印：

    「新批次单个 benchmark 的 correct 只有 6–7 条」
    「按预登记的停止点（前 30 题），再多取也到不了 10。」
    「=> 这是设计问题，不是取数问题。」

改成先看当前批次的 cap：

- **cap == 8192**（实测那一批）⇒ 照印，但**连条件一起印**：
  「这条只对 cap 8192 成立（修订 153 在该批次实测）」……
  「⇒ 对 cap 8192 这一批，这是设计问题，不是取数问题。」
- **cap != 8192** ⇒ **不印任何历史数**，改为印：
  「本批次 cap = [32768]，不是实测那批（cap 8192）」、
  「因此这里不印任何历史 correct 数」、
  「历史值 {'aime25': 7, 'aime26': 6} 出自 cap 8192 批次，对本批**不成立**」、
  「拿它外推本批，等于把『本轮要检验的量』先写死成已知」、
  「本批 correct 够不够 10，以上面这一批实测数为准：N」。

历史值提为具名常量 `CAP8192_PER_BENCH_CORRECT = {"aime25": 7, "aime26": 6}`
与 `CAP8192_MEASURED_ON = 8192`，出处仍写在注释里
（账本 `R6_RERUN_PREREG.md:20949`，批次实测 cap 分布 `{8192: 120}`）。

### 187.3 四方向证伪（退出码均脱离管道量）

| 方向 | 输入 | 期望 | 实得 |
|---|---|---|---|
| A | 部分数据 32 行（实测） | 红、拒出判决 | `EXIT=6` `INCOMPLETE`，印 think n={'aime25': 16} 期望 30 |
| B | 完整 60 行 cap 32768（合成） | 过守卫、**拒绝外推** | `EXIT=3`，印「不是实测那批（cap 8192）…不印任何历史 correct 数」 |
| C | 真实 cap 8192 旧批（120 行） | 行为与改前一致 | `EXIT=3` `POOL_ONLY`，单池 [('aime25', 7), ('aime26', 6)] |
| D | 完整 cap 8192 批、合并池 correct<10（合成） | **带上条件**印历史数 | `EXIT=3`，印「这条只对 cap 8192 成立…实测 {'aime25': 7, 'aime26': 6}」 |

⚠ **方向 A 的判据要看仔细**：日志里确实出现了「再多取也到不了 N」六个字，
⚠ 但它出现在**禁止令**里（「特别是：\*不许\*据它说『再多取也到不了 N』」），
⚠ 断言本身已经不存在。方向 B/D 证明断言只在 cap 8192 分支出现。
⚠ ⚠ 用「输出里有没有某串字」当判据会误判 —— 必须看清它出现在哪个分支里。

⚠ **方向 C 是回归**：真实旧批走的是 `POOL_ONLY` 分支（在 P6 底线核对之前），
⚠ 所以本节改的这段压根没被它走到，改动前后行为一致。
⚠ 这条不能证明改动正确，只能证明**没弄坏别的路径** —— 两者都要跑。

### 187.4 本节没有改的东西（写清楚，免得被当成「顺便优化了」）

- `P6_CORRECT_FLOOR = 10`、`KNOWN_NEW_CAPS`、`OLD_CAP`、`OLD_BATCH_BASELINE`：**一律未动**
- 旧批 4/2 回归路径（`OLD_BATCH` 分支）：**未动**
- `POOL_ONLY` 合并池告警：**未动**
- 标签规则：**仍是 `import strict_label` 复用的唯一来源，未复刻**

⚠ 本节**只**加了一道守卫 + 把一段无条件文本改成条件化。
⚠ 判据语义（P6 底线 10、按单池判、不合并判）**一条没改**。

### 187.5 一个被证伪的夹具，和一个没修的小口子

**夹具**：第一版合成「完整 60 行」存成了裸 JSON list，跑出来 `EXIT=1` 崩在
`blob.get("rows")` ⇒ `AttributeError: 'list' object has no attribute 'get'`。
⚠ 查下来是**夹具错、代码没错**：真实标注产物顶层是 `dict`（`{"rows": [...]}`），
而我把夹具存成了 list。改成 dict 形态后即通过。
⚠ ⇒ 与修订 180.4 同族：**判定「代码坏了」之前，先确认输入的形状真的是它吃的形状。**

**没修的小口子**：`p6_readiness.py` 读标注时只认 `dict` 形态，
遇到 list 形态直接崩（`r180_p6_precond.py` 与 `r181_label_drift.py` 都做了兼容）。
⚠ 这是健壮性、不是判据语义，但**本轮不动它** ——
⚠ 理由：改判据代码要拍板，本轮拍的是这两条缺陷，不含这一条。
⚠ 记录在此，等下次一并处理。

### 187.6 本节仍不含 P6 结论

§167 不变：数据没跑满（修订 187 写作时 32/60）不给 P6 结论。
本节证明的是**仪器在未跑满时不再出判决**，不是 P6 的结论。
"""

PRECHECKS = (
    ("无 U+FFFD 坏字", lambda s: chr(0xFFFD) not in s),
    ("无反斜杠续行", lambda s: chr(92) + chr(10) not in s),
    ("以换行结尾", lambda s: s.endswith(chr(10))),
    ("标题格式合规", lambda s: s.lstrip(chr(10)).startswith("## 修订 187 ")),
    ("含本节入口", lambda s: "187.6 " in s),
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