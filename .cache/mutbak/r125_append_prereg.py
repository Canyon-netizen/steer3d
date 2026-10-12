#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 125 —— K2 页面实例扰动台落地；verify_heldout PAGE_TEXT 桶首次验牙齿 9 条。"""
import io
import sys

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = r'''

---

## 修订 125 —— K2「页面实例级」扰动台落地；PAGE_TEXT 桶**首次**验牙齿

> 状态：**纯披露 + 新增只读台**。本节**未改任何判据文件、未改任何产物**。
> 新增 `.cache/mutbak/r125_k2_teeth.mjs`（只读台，不写任何产物）。

### 125.1 为什么必须有它

修订 121 §121.1 的直接后果：K1（doctored 产物）**结构上测不了**
PAGE_TEXT / PAGE_ATTR 桶 —— 页面上的字与判据的期望值读**同一个文件** ⇒ 一起变 ⇒ 恒绿。
⇒ PAGE 桶只能靠 **K2 = 改**已渲染 DOM 的 `innerText`
（不动源码、不动产物、不重建），范本 = 修订 116 的 `r116_n1_selftest.mjs`。

### 125.2 台的骨架（抄 r116，四道对照缺一不可）

| 对照 | 作用 |
|---|---|
| ① 真实绿 | 谓词对真页面成立 |
| ② 同句改错转红 | 证它读的就是读者看到的那句话 |
| ③ **还原回读** | 改回原句必须重新变绿（⚠ r116 第一版就栽在「阴性之后未证明基线恢复」） |
| ④ **污染对照** | 改**别的**元素 ⇒ 必须仍然绿（否则「什么改动都让它红」= 仪器在喊叫） |

⚠⚠ **反漂移守卫**：每条谓词**逐字出自已提交判据文件**
（`verify_heldout.mjs`），启动时断言；抽不到就 `exit 2`。
`textVar → T` 是**机械替换**，谓词本身未重写（守「不复写判据」）。

⚠ 守卫**首版就拦下了一次**：
`[闸门失败] verify_heldout.mjs 里找不到 E1b 的谓词原文 ⇒ 本台已漂移，拒绝发布`
—— 因为谓词在源文件里是**跨行**的。处置 = 比对前**折叠空白**
（只抹换行/缩进，表达式内容一个字符都不放松）。
⇒ **改表达式仍会被抓住；只改排版不会——这是有意的代价，已写进源码注释。**

### 125.3 ⚠⚴ 仪器自己错了一次（两版都报 9/9，**只有第二版算数**）

首版判的是 **JS 里的 `mutated` 字符串**，而不是**从 DOM 回读的 `dom.now`**。

⚠⚴ 为什么这是实质错误：浏览器可能规范化空白 ⇒ `mutated` 与 `dom.now` 可以不同；
而若「转红」出自**后者**，原因就与「判据有没有牙齿」**无关**——
本台会把自己制造的差异当成判据的判别力。

现处置：
1. 判定改用 `dom.now`；
2. 额外断言 `dom.now === mutated`（**落地不保真 ⇒ 本条直接作废**，不参与判定）；
3. 还原对照也判 `dom.back`，不只是比字符串相等。

⚠⚴ **首版的 9/9 不足以发布** —— 与修订 121 §121.4 那次「工具成功回执不算证据」同族：
**自己造的数、自己判、自己宣布通过，都不算。**

### 125.4 结果

```
RESULT PASS 9/9（真实绿 + 同句改错转红 + 还原回读，三道同时成立才算过）
```

| 判据 | 元素 | 真实绿 | 同句改错转红 | 还原回读 | 落地保真 |
|---|---|---|---|---|---|
| **E1b** 判决段两侧措辞 | `[data-heldout-verdict-text]` | ✓ | ✓ | ✓ | ✓ |
| **D3** 「就是同一个观测量」 | `[data-selfdup-verdict]` | ✓ | ✓ | ✓ | ✓ |
| **I4** 「可注入 ✗」 | `[data-recipe-verdict]` | ✓ | ✓ | ✓ | ✓ |
| **B4** 分母逐行独立估计 | `[data-block="transfer"]` | ✓ | ✓ | ✓ | ✓ |
| **G1** 「补进来 N 条」 | `[data-heldout-not-claimed]` | ✓ | ✓ | ✓ | ✓ |
| **G5** greedy 与 perm_min 不同 | 同上 | ✓ | ✓ | ✓ | ✓ |
| **G6** 「N 个判成同一条方向」 | `[data-heldout-verdict-text]` | ✓ | ✓ | ✓ | ✓ |
| **G7** 同向余量 min–max | 同上 | ✓ | ✓ | ✓ | ✓ |
| **G9** 「对 N 条命名轴」 | 同上 | ✓ | ✓ | ✓ | ✓ |

⚠ **污染对照只覆盖 7 条**（E1b/B4/G1/G5/G6/G7/G9 读的是被污染元素之外的三个块，
**全部仍绿**）；**D3 与 I4 所在元素未被本轮污染** ⇒ 它们只有三道对照，没有第四道。
⇒ 明写出来，不含糊。

### 125.5 覆盖面（口径紧挨数字）

`verify_heldout` 手读分桶（修订 119 §119.2）：
PAGE_TEXT **53** / PAGE_ATTR 14 / ARTIFACT 3 / SOURCE 1 / RUNTIME 4。

| | 条数 | 验证层级 |
|---|---|---|
| 修订 123（`G2 G3 G4 E2`） | 4 | 静态重建的**真实页面文字** |
| 修订 125（本轮 `E1b D3 I4 B4 G1 G5 G6 G7 G9`） | 9 | 浏览器里**已渲染的 DOM** |
| **合计已验** | **13 / 53** | |
| **仍未验** | **40** | |

⚠ **两级口径不同，不可混算**：
- 修订 123 跑在静态重建的文字上 ⇒ 能测**判别力**
- 修订 125 跑在浏览器已渲染的 DOM 上 ⇒ 还能测**「它读的是读者看到的那句」**

⚠ `verify_axis_readout` 的 PAGE 桶（约 **50** 条）与
`probe_dedup_rendered`（**24** 条）**仍一条未验** —— 本台的 SPEC 表只登记了
`verify_heldout` 那 9 条；扩到别的文件只需加 SPEC，但**每个文件都要重新校准**
（元素选择器与 textVar 都不同）。

### 125.6 ⚠ 口径限制（必须随结论一起说）

这是**页面实例级**扰动 —— 改的是已渲染的 DOM。

- ✅ 它证明「该判据读的确实是**页面上读者看到的那句话**」
- ❌ 它**不**证明「组件写错时该判据一定红」—— 那要改源码 + 重建
- ⚠ React 重渲染会把改动冲掉，所以每条都在**同一帧内**读完再还原
'''

def main():
    raw = io.open(P, encoding='utf-8').read()
    pre_len = len(raw)
    ends_nl = raw.endswith('\n')
    print('追加前：%d 字符 / %d 行 / U+FFFD=%d' % (pre_len, raw.count('\n'), raw.count('\ufffd')))
    assert raw.count('\ufffd') == 0
    assert '## 修订 125' not in raw, '修订 125 已存在，拒绝重复追加'

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