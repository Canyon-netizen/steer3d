#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 126 —— K2 扩到第二个文件（15/15）；⚠⚴⚴ 一次被当场否掉的误判。"""
import io
import sys

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = r'''

---

## 修订 126 —— K2 扩到 `verify_axis_readout`：**15/15**；⚠⚴⚴ 一次误判被当场否掉

> 状态：**纯披露 + 只读台扩展**。未改任何判据文件、未改任何产物。

### 126.1 结果

```
[自证] 9 条谓词逐字出自 verify_heldout.mjs：E1b D3 I4 B4 G1 G5 G6 G7 G9
[自证] 6 条谓词逐字出自 verify_axis_readout.mjs：D2 D3 D5 D6-caution C1 C2
RESULT PASS 15/15（真实绿 + 同句改错转红 + 还原回读，三道同时成立才算过）
```

⚠ **污染对照覆盖 10 条**（E1b B4 G1 G5 G6 G7 G9 D5 C1 C2），全部仍绿；
`D2 / D3 / D6-caution` 所在元素未被本轮污染 ⇒ 它们只有三道对照。

⚠⚠ **D2 特别值得记**：它是**否定性断言**（「位置轴那一行不得声称 token 局部」），
它的变异方向与别的相反 —— 必须**往元素里注入** `token 局部` 才验得了；
不注入的话它被平凡满足。
⚠ 实测注入 118 字 → 131 字后**转红** ⇒ D2 有牙齿。

### 126.2 ⚠⚴⚴ **我的一次误判，被 DOM 探针当场否掉**

**经过**（原样记录，因为它比结论更值得记）：

1. K2 台在 `D2` 上读到 `null`。
2. 我据 `verify_axis_readout.mjs:543` 的
   `const v = el && el.querySelector('[data-verdict]'); return v ? … : ''`
   推断：`el` 非空而 `v` 为空 ⇒ `posText === ''` ⇒
   `!''.includes('token 局部')` 恒真 ⇒ **D2 被平凡满足**。
3. ⚠⚴ **这个推断是错的。** 单独写的 DOM 探针
   （`.cache/mutbak/r125_probe_verdict_dom.mjs`）给出：
   ```
   [data-axis-row] 行数 = 4
   行 reasoning  [data-verdict] 后代数 = 1
      verdict 文字: 「Δ=0 上 0/3 层超过对照。 中位 0.339 vs 对照 0.628 （0.54×」
   ```
   ⇒ **元素存在、有 118 字真实文字，D2 不空、不平凡满足。**

⚠⚴⚴ **真因是仪器，不是页面，更不是判据**：
`C1`/`C2` 扰动的是 `[data-axis]`——**整块面板**。
`el.innerText = x` 会**重新解析出整棵新子树**，而这些节点**不被 React 持有**；
React 下一次 reconcile 会把它们清掉
⇒ 排在后面的 `D2 / D3 / D6-caution` 读到的是**被冲掉的结构**。

⇒ **处置**：① 容器级 spec **排到最后**；② 跑完一个容器级 spec 就
**重新导航**（`Page.navigate` + 等就绪）再继续。
⚠ 修完同一条命令直接 **15/15**，D2/D3/D5/D6-caution 全部转绿。

⚠⚴ **固化**：
1. ⚠ **读不到东西时，先怀疑「自己上一条扰动弄坏了页面」，再怀疑页面。**
   「判红先怀疑判据/变异/环境」—— 这次**环境就是仪器自己**。
2. ⚠⚴ **仪器读不到 ≠ 对象不存在。** 空结果必须由**独立仪器**复核后才许下结论。
   本轮若没有那个 DOM 探针，我会把一个「有 118 字真实文字」的判据
   写成「恒绿」，并据此去改判据 —— **那是把工具的缺陷写成世界的性质。**
3. ⚠ **`innerText` 扰动只对叶子元素安全**；动容器等于换掉子树，
   **「还原」不等于「恢复原结构」**。

### 126.3 ⚠ 新发现：`[data-verdict]` 这个属性名**被三个组件复用**

| 组件 | 行 | 语义 |
|---|---|---|
| `SubspacePanel.tsx` | `:343` | 整块面板的判决段（`data-verdict="true"`） |
| `AxisReadoutPanel.tsx` | `:311` | 每轴一行（`data-verdict={a.status}`） |
| `InterventionOutcomePanel.tsx` | `:609` | 干预结果（`data-verdict={k}`） |

⚠ 实测**全页 8 个** `[data-verdict]`，其中 **4 个不在任何 `[data-axis-row]` 内**。

- ✅ `verify_axis_readout.mjs:117/:543/:555`、`verify_subspace.mjs:101`、
  `verify_outcome.mjs:129`（`el = [data-outcome]`）**都限定了作用域** ⇒ 安全。
- ⚠⚠ **`verify_patch.mjs:128` 用的是裸 `document.querySelectorAll('[data-verdict]')`**
  ⇒ 与 `probe_dedup_rendered.mjs:88-90` 已修过的那条**同族**
  （那里注释原文：「选择器是**全页作用域**，而 HeldoutPanel.tsx:242 也发
  `data-kind="floor"` ⇒ 4 行 + 3 个对照格 = 7」）。
- ⚠⚠ **它当前是否真的误判，本轮未验** —— 另两个组件那些元素的
  `children[1]` 到底含不含「成立 / 不成立 / 没测」**没有查**。
  ⇒ 明写「未验」，不写成缺陷。

### 126.4 覆盖面（口径紧挨数字）

| 文件 | PAGE_TEXT 桶 | 已验牙齿 | 仍未验 |
|---|---|---|---|
| `verify_heldout` | 53 | 13（修订 123 的 4 + 修订 125 的 9） | **40** |
| `verify_axis_readout` | 约 50（手读估算） | **6**（本轮） | 约 44 |
| `probe_dedup_rendered` | 2（PAGE_TEXT 部分） | 0 | 2 |

⚠ **本轮没测到「作用域」这一维**：`C1`/`C2` 的 haystack 是**整块面板 2236 字**，
而本轮的变异是把 `step_frac` / `搜索` / `付过钱` **在全文里全部替换**
⇒ 只证明了「它对全文敏感」，**没**证明「它锁在那一句上」。
⚠ 仓库里已有的同族教训（`verify_axis_readout.mjs:229-236` 的注释原文）：
「**haystack 比作用域大** ⇒ caveat 被整个删掉，C3 照样绿」——
⚠ **那正是本轮 C1/C2 未覆盖的风险。**

### 126.5 口径（不变）

页面实例级扰动：✅ 证明「判据读的就是读者看到的那句话」；
❌ **不**证明「组件写错时一定红」——那要改源码 + 重建。
⚠ 且本轮实测到：**对容器动 `innerText` 会换掉子树**，
所以「同一页里连着跑多条」必须把容器级排到最后并重载。
'''

def main():
    raw = io.open(P, encoding='utf-8').read()
    pre_len = len(raw)
    ends_nl = raw.endswith('\n')
    print('追加前：%d 字符 / %d 行 / U+FFFD=%d' % (pre_len, raw.count('\n'), raw.count('\ufffd')))
    assert raw.count('\ufffd') == 0
    assert '## 修订 126' not in raw, '修订 126 已存在，拒绝重复追加'

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