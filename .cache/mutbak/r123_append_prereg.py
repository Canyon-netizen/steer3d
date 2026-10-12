#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 123（判据笔）—— 改 verify_heldout.mjs 的 G2/G3/G4/E2。"""
import io
import sys

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = r'''

---

## 修订 123（判据笔）—— 修 G2/G3/G4/E2；功效验证在**真实页面文字**上做

> 本笔**只改判据**，**不取数**。新基线由修订 124 单独取。
> ⚠ 旧数字披露：改前 `verify_heldout` 实跑 **71/74**，红的正是 **G2 / G3 / G4**。

### 123.0 为什么这次可以动手（不再需要「markdown A/B」拍板）

修订 122 §122.5 已判定：A/B 之争不成立（`Em` 已经在渲染 `**`，
`HeldoutPanel:627/:632` 都在用）。剩下的唯一问题是
「**判据该不该去匹配源记号**」，而本仓已有两条反方向判据
（`verify_hinge_panel` H9、`verify_outcome:876-878`）站在「不许匹配」一侧
⇒ 修法由仓库自身规则确定，不需要新的设计选择。

### 123.1 功效验证（变异跑在**真实页面文字**上，不是手造字符串）

⚠ 底稿：`NC_PAGE = 「这仍然不是因果性：」+ <Em> 处理后的 not_claimed`
= **299 字**，与 §120.1 实跑打印的「边界 299 字」**逐字对上**（§122.6 已校验）。
⚠ 所有阈值（old/new/n_candidates/门槛/perm_min/greedy）**从产物动态取**，不写死。

| 变异 | 旧 G2 | 旧 G3 | 旧 G4 | 旧 E2 | 新 G2 | 新 G3 | 新 G4 | 新 E2 |
|---|---|---|---|---|---|---|---|---|
| M0 基线（真实页面文字） | F | F | F | T | **T** | **T** | **T** | **T** |
| M1 删「下界因此从 12 抬到 14（…）」整句 | F | F | F | **T** | F | F | T | **F** |
| M2 删「而 14 仍然是下界：」 | F | F | F | T | T | T | T | T |
| M3 删「门槛 0.45 就退回 11 条」 | F | F | F | T | T | T | **F** | T |
| M4 把 14 改成 13 | F | F | F | T | **F** | **F** | T | **F** |
| M5 把 11 改成 12 | F | F | F | T | T | T | **F** | T |
| M6 删「同一 perm_min 口径」 | F | F | F | T | T | T | **F** | T |

⚠⚴ **旧谓词在基线上就是红的**（G2/G3/G4 全 F，与实跑的三条红**逐条对上**）
⇒ 它们对任何变异都红（6/6）⇒ **零判别力**；E2 反过来 0/6 ⇒ **零判别力**。

✅ **新谓词基线全真**，且**各自定向变异 100% 转红**：

| 判据 | 定向变异 | 命中 |
|---|---|---|
| G2 | M1（删目标句）、M4（14→13） | **2/2** |
| G3 | M1、M4 | **2/2** |
| G4 | M3（删目标句）、M5（11→12）、M6（删口径句） | **3/3** |
| E2 | M1、M4 | **2/2** |

⚠ M2/M3/M5/M6 不让 G2 红是**正确行为**（单变量：那些变异没动 G2 的锚点），
不是漏网。

### 123.2 判据改动（只动这四处，别的一律没碰）

1. **G2**（`:395`）：`从 A 抬到 \*\*B\*\*` ⇒ `从 A 抬到 B`
2. **G3**（`:400`）：`\*\*B\*\*（…）` ⇒ `B（…）`；
   取样用的 `NC.match(/\*\*\d+\*\*（…）/)` 一并改成 `/[\d]+（[^）]*）/`
3. **G4**（`:407`）：`门槛 X 就退回 \*\*N\*\* 条` ⇒ `门槛 X 就退回 N 条`
4. **E2**（`:336-347`）：**删掉裸 `includes('12')` / `includes('14')`**，
   改成 `new RegExp('下界因此从 ' + _eOld + ' 抬到 ' + _eNew).test(P.notClaimed)`
   ⚠ E2 位于 G 组变量定义之前，故就地单取 `_sh/_eOld/_eNew`
   （值同样来自 `SUB.headline`，不写死）

⚠⚠ **每处都加了「别改回去」的注释**，写明：
`**` 是产物里的**源记号**，不是页面上的**可见文字**；
判据拿【产物原文】匹配 `**` 对，拿【渲染后 innerText】匹配 `**` 错
（并点名 `verify_hinge_panel` H9 与 `verify_outcome:876-878` 为反方向先例）。

### 123.3 顺带更正 §119.3-2 的成因

`verify_heldout.mjs:356-358` 的注释称 `12` 的第二处是「0.45 退回的 12」，
⚠ 但页面上印的是「门槛 0.45 就退回 **11** 条」，那句话里**没有 12**。
真实第二处是「**greedy 估法给 12**」。
⇒ 「E2 是弱断言」这个**结论**成立，但给出的**成因陈旧**，照它修会改错地方。

### 123.4 本笔自检

- `node --check verify_heldout.mjs` ⇒ OK
- 该文件 `U+FFFD` = **0**
- `grep '\\\*\\\*'` 残留 ⇒ **无**
- `git status` = **16** 条（15 条作者制品 + 1 个判据文件），**未碰任何产物**

⚠ 本笔**不发布任何新基线数字**；`71/74` 仍是改前的旧基线。
'''

def main():
    raw = io.open(P, encoding='utf-8').read()
    pre_len = len(raw)
    ends_nl = raw.endswith('\n')
    print('追加前：%d 字符 / %d 行 / U+FFFD=%d' % (pre_len, raw.count('\n'), raw.count('\ufffd')))
    assert raw.count('\ufffd') == 0
    assert '## 修订 123' not in raw, '修订 123 已存在，拒绝重复追加'

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