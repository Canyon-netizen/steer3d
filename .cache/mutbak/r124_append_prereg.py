#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 124（取数笔）—— 新基线 74/74。"""
import io
import sys

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = r'''

---

## 修订 124（取数笔）—— `verify_heldout` 新基线 **74/74**

> 本笔**只记录实跑结果**，未再改任何判据。
> 判据笔 = 修订 123（`2647f98`），**已先推送**，本笔在其后。

### 124.1 取数

```
BV_URL=http://127.0.0.1:9006/ node .cache/browser_verify/verify_heldout.mjs
RESULT PASS 74/74
```

| | 旧基线（修订 120 首跑） | 新基线（本笔） |
|---|---|---|
| 总数 | 74 | **74**（未变） |
| PASS | 71 | **74** |
| FAIL | **3**（G2 / G3 / G4） | **0** |

⚠ **分母未变**：改的只是三条谓词的形态，没有增删判据
⇒ 「PASS 从 71 到 74」是**红转绿**，不是「放宽了口径换来的绿」。

⚠⚠ 但**必须同时记住**（披露，不是辩护）：
新谓词已经过了功效验证（修订 123 §123.1）——
在**真实页面文字**上，G2/G3/G4/E2 各自定向变异 **2/2、2/2、3/3、2/2 转红**。
⇒ 「74/74」不等于「什么都能测出来」，它只表示
**这 74 条在当前页面上都成立，且其中四条已被证明有牙齿**。

### 124.2 四条的实跑 detail（原样摘录，便于回查）

```
[PASS] E2 …：边界 299 字　现算 old=12 new=14　「12」出现 2 次、「14」出现 2 次
[PASS] G2 …：现算 old=12 new=14；原文：下界因此从 12 抬到 14
[PASS] G3 …：现算 n_candidates=20 选定门槛=0.5；原文：14（20 个候选、|cos|<0.5）
[PASS] G4 …：现算：门槛 0.45 → perm_min 11（greedy 给 12，perm 11–12）；
        原文：门槛 0.45 就退回 11 条 —— 同一 perm_min 口径；…
```

⚠⚴ **注意 E2 那行 detail 里的「12 出现 2 次、14 出现 2 次」**：
这正是修订 123 §123.3 更正过的点——第二处 `12` 来自「greedy 估法给 12」，
**不是**旧注释说的「0.45 退回的 12」（页面上那句印的是「退回 **11** 条」）。
把命中处数**印在 detail 里**，就是为了让下一次不必再翻注释。

### 124.3 本次未做（仍然挂着）

- ⚠ ⚠ `verify_heldout` 其余 70 条**仍未验过牙齿**：
  功效验证只覆盖了 G2/G3/G4/E2 四条。K1（doctored 产物）**测不了它们**
  （页面与判据读同一文件 ⇒ 一起变），须走 K2 页面实例扰动。
- ⚠ `verify_scene_link` 的 **J11c**（空串放行）与
  `verify_relamp` 的**双 RESULT 分母矛盾**仍未修。
- ⚠ 产物两副本裂缝（`control.delta` vs `control.note`）仍未加判据对齐。

### 124.4 至此，8 个判据文件的实跑基线

| 文件 | 基线 | 最近一次 |
|---|---|---|
| `verify_subspace` | **52/52** | 修订 114 |
| `verify_hinge_panel` | **28/28** | 修订 118 |
| `verify_path` | **36/36** | 修订 118 |
| `verify_heldout` | **74/74** | ✅ **修订 124（本笔）** |
| `verify_axis_readout` | **66/66** | 修订 120 |
| `probe_dedup_rendered` | **24/24** | 修订 120 |
| `verify_relamp` | **0/1**（环境红，R1b–R6 不可判定） | 修订 120 |
| `verify_scene_link` | **6/8**（环境红，J11/J11b） | 修订 120 |
'''

def main():
    raw = io.open(P, encoding='utf-8').read()
    pre_len = len(raw)
    ends_nl = raw.endswith('\n')
    print('追加前：%d 字符 / %d 行 / U+FFFD=%d' % (pre_len, raw.count('\n'), raw.count('\ufffd')))
    assert raw.count('\ufffd') == 0
    assert '## 修订 124' not in raw, '修订 124 已存在，拒绝重复追加'

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