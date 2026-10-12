#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 121 —— 新基线扰动验证（K1）；⚗⚠⚴ 发现产物内部一处无人管的裂缝。"""
import hashlib
import io
import sys

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = r'''

---

## 修订 121 —— 新基线扰动验证；⚗⚠⚴⚴ 发现产物内部一处**无人管的裂缝**

> 状态：**纯披露**。本节**未改任何判据文件、未改任何判红条件**。
> 本节动作 = 两次**扰动 + 还原**（产物只在扰动窗口内被临时替换，
> 两次均按事先备份**逐字节**还原并核对）。
> ⚠ 实跑通道 = 隔离农场 **9006**。

### 121.0 起点

修订 120 §120.6 记：「三个新基线（`axis_readout` 66 / `dedup` 24 / `heldout` 71）
**一条都还没做过扰动**」⇒ 本节做这件事。

### 121.1 ⚗⚠⚴ 先立一条分类：扰动分 K1 / K2，而 **K1 测不了大部分判据**

- **K1 = doctored 产物**（本节用的手段，`.cache/mutbak/r121_doctor.py`）
- **K2 = 页面实例扰动**（修订 116 的 `selfTest()` 模式：改**已渲染 DOM** 的 `innerText`，
  不重建、不碰源码、不碰产物）

⚠⚠⚠ **K1 的致命限制（本节最重要的产出）**：
页面上的字与属性是**由产物渲染出来的**，而判据脚本**也从同一个文件**读期望值
⇒ **改产物 ⇒ 页面与判据一起变 ⇒ 恒绿。**

⇒ 因此 **K1 结构上测不了 PAGE_TEXT / PAGE_ATTR 桶**（本仓判据的大头）。
⇒ K1 真正能测的只有两类：
  ① **判据/产物内部一致性**（ARTIFACT 桶）—— 页面上没有对应渲染
  ② **判据侧写死的字面量**—— needle 不来自产物，产物一变它就不动

⚠ 这一条把「扰动验证」的覆盖面从「看起来全跑了」变成
「**明确知道哪几类没测**」—— 这正是修订 116「先验功效」的前置条件。

### 121.2 扰动 A：`readable_subspace.json` 的 `control.delta["100"]` 0.7087 → 0.9

**单变量**（只改结构字段一处）。跑 `probe_dedup_rendered` ⇒ **24/24 全绿**。

- `D3 data-control-value`：页面 `["0.9"]` vs 产物 `0.9` ⇒ **绿**
  ⇒ 正是 §121.1 那条限制的**实测印证**
- ⚠⚴⚴ `D4 可见文字里仍有 对照 Δ=100 四位小数`（needle 写死 `'0.7087'`）⇒ **仍然绿**

⚠ 追查 `0.7087` 的出处时发现（**这才是重点**）：

- 前端源码**没有**写死 `0.7087`（`grep -rn "0\.7087" frontend/ --include=*.tsx --include=*.ts` 全空）
- 它在 **`readable_subspace.json:235` 的散文 `control.note`** 里：
  「它在 Δ=100 仍有 **0.7087**、几乎不衰减 ⇒ 装置有能力测出持续方向，而它测出的是位置轴。」

⚗⚠⚴⚴ **由此发现一个此前没人知道的事实：同一个量在产物里有两份副本，
而没有任何判据把它们对齐。**

| 副本 | 产物字段 | 页面渲染点 | 可见文字？ |
|---|---|---|---|
| **结构** | `control.delta["100"]` | `SubspacePanel.tsx:331-334` | ✅ 印 `Δ=100 {…toFixed(4)}` |
| **散文** | `control.note`（内含字面量 0.7087） | `SubspacePanel.tsx:339` | ✅ `{d.control.note}` 整段 |

⇒ 扰动窗口内，**同一屏上同时印着**：
`Δ=100 0.9000`　与　「它在 Δ=100 仍有 0.7087、几乎不衰减」
⇒ **页面上出现两个互相矛盾的 Δ=100 值**，而**全部 24 条判据一条都没红**。

⚠⚠⚴ **`verify_subspace.mjs` 的 G7 覆盖不到这里**：
G7 核的是「产物说什么」vs「页面有没有照抄」（`flat(got) === flat(want)`）
⇒ 它管**转录保真度**，不管**两份副本之间的一致性**。
⚠⚠ 而 `SubspacePanel.tsx:325` 的注释**正是拿 G7 作为删除 `data-control-delta100` 的依据**
（「G7 逐字核了 control.note 全文（那句里就有…）」）
⇒ **删除重复属性时援引的判据，管的不是「重复」的那一层。**

⚠ 与已知的 §98.9「表格 0.35→9 vs 散文 0.35→7」**同族**：
那里有 `scan_live_blocks.py` 管住**一处**，这里**一处都没有**。

⇒ ⚗ **本节最实质的发现不是「判据弱」，而是产物内部有一条没人管的裂缝**，
而扰动把它当场撑开了。

⚠ **同时更正修订 119 §119.3-3**：那条写的是「`probe_dedup:186` 把 `0.7087` 写死」——
**方向对但说小了**。真正的问题是**产物侧有一份手写散文重复了这个数**，
而判据侧那个写死的 needle **恰好命中的是散文副本、不是它声称要核的结构字段**
⇒ **标签指向一个量，needle 命中的是另一个副本。**

### 121.3 扰动 B：`axis_readouts.json` 的 `axes.caution.specificity.cos_per_axis.confidence` 0.3341 → 0.9

**单变量**（一处）。跑 `verify_axis_readout` ⇒ **`RESULT FAIL 65/66`**，
**唯一红的是 E4**：

```
[FAIL] E4 caution 的归属论证里三个数必须等于 cos_per_axis / pair_cos:
  note=「同一格上 confidence 轴的余弦 0.3341 高于 caution 轴的 0.3077…」；
  应含 ["0.9000","0.3077","0.5537"]；缺 ["0.9000"]
```

- ✅ **E4 有牙齿**，且**单变量精确命中**：另外 65 条**一条没跟着动**
  ⇒ 「改一个数只红一条」本身就是「其余判据没被这一处牵连」的证据。
- ⚠⚴ **同一次运行里的内建对照**：
  `D4 caution 归属检验的 4 个余弦都印出且与产物一致` 仍 **PASS**（`confidence=0.9`）
  —— 因为页面跟着产物一起变
  ⇒ **实测印证 §121.1**：K1 能证伪 ARTIFACT 桶，**证不了 PAGE 桶**。

### 121.4 ⚠ 工具自己失败了一次（后果是真产物**留在扰动态**）

`r121_doctor.py restore` 起初**无差别**地要求 3 个参数，
而 `restore` 只需要 1 个 ⇒ 在**最需要还原的时刻**打印用法并 `exit 2`
⇒ 产物**真的留在了扰动态**（`git status` 16 条，sha256 与备份不符）。

⇒ ⚠⚴ **是独立复核发现的，不是工具的回执**：单独 `shasum` 了产物、
单独 `json.load` 读了 `control.delta`、单独数了 `git status` 条数，才发现没还原。
⇒ 已修（`set` / `show` / `restore` 各自校验参数数目），修完立刻还原成功。

⚠ **两条固化**：
1. ⚠⚴ **还原流程不能只有一个入口**；工具出任何意外都按「没还原」处理，重新核对。
2. ⚠⚴ **还原后必须独立复核**（sha256 + 值 + `git status` 三样），
   **工具自己说成功不算证据** —— 本轮正是独立复核拦住的。

### 121.5 ⚠ 仍未验的清单（明确的「没测过」，不是「测过没问题」）

| 范围 | 条数 | 状态 |
|---|---|---|
| `verify_axis_readout` ARTIFACT 桶 | 11 | ✅ **本轮验过**（E4 单变量命中） |
| `verify_axis_readout` PAGE 桶 | ~50 | ❌ **未验**（K1 结构上测不了） |
| `probe_dedup_rendered` | 24 | ❌ **未验**（K1 测不动） |
| `verify_heldout` | 71 | ❌ **未验**（K1 测不动） |

⇒ 下一步**只能靠 K2**（页面实例扰动，修订 116 的 `selfTest()` 模式），
且按修订 116 的纪律，**新写的 K2 扰动台必须先在有已知答案的样本上校准**
（范本：`.cache/mutbak/r116_n1_selftest.mjs` 的四道）。

### 121.6 本节结论

1. ✅ 立起 **K1 / K2 分类**，并**两次实测印证**：K1 对 PAGE 桶结构性无效
   （扰动 A 的 D3 绿、扰动 B 的 D4 绿，都是同一现象）。
2. ⚗⚠⚴⚴ **发现产物内部一处无人管的裂缝**：`control.delta["100"]` 与 `control.note`
   各印一份、互相对齐无人管；扰动期间页面上同时出现两个矛盾的 Δ=100 值，
   **24 条判据无一红**。⇒ 已更正修订 119 §119.3-3 的说法（方向对但说小了）。
3. ✅ `E4` 有牙齿，单变量精确命中 `65/66`。
4. ⚠ 扰动台失败一次（`restore` 参数校验），**产物真的留在扰动态**，
   由**独立复核**而非工具回执发现；已修。
5. ⚠ 本节**未改任何判据、未改任何产物**：两次扰动均按事先备份**逐字节**还原
   （`readable_subspace.json` sha256 `c8e64fc8…`、`axis_readouts.json` sha256 `a815f94a…`
   两次均与备份一致，`git status` 回到 **15** 条作者制品）。
'''

def main():
    raw = io.open(P, encoding='utf-8').read()
    pre_len = len(raw)
    ends_nl = raw.endswith('\n')
    print('追加前：%d 字符 / %d 行 / U+FFFD=%d / 以\\n结尾=%s'
          % (pre_len, raw.count('\n'), raw.count('\ufffd'), ends_nl))
    assert raw.count('\ufffd') == 0, '追加前已有坏字，拒绝写入'
    assert '## 修订 121' not in raw, '修订 121 已存在，拒绝重复追加'

    add = ('' if ends_nl else '\n') + BODY.lstrip('\n')
    if not add.endswith('\n'):
        add += '\n'
    assert '\ufffd' not in add, '追加内容含坏字'

    with io.open(P, 'a', encoding='utf-8', newline='') as f:
        f.write(add)

    after = io.open(P, encoding='utf-8').read()
    assert after[:pre_len] == raw, '⚠⚠ 原文前缀被改动，拒绝发布'
    assert len(after) == pre_len + len(add)
    print('追加后：%d 字符 / %d 行 / U+FFFD=%d' % (len(after), after.count('\n'), after.count('\ufffd')))
    print('原文前缀逐字节未变 = True；新增 %d 字符' % (len(after) - pre_len))
    return 0


if __name__ == '__main__':
    sys.exit(main())