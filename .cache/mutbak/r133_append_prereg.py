#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r133_append_prereg.py —— 追加修订 133（只追加，不改原文）"""
import hashlib
import sys

PRE = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = """
## 修订 133 —— ⚠⚠⚴⚠⚠ 判据**自带的变异台装在判据之后**：「变异已生效」与「判据全绿」可以同时为真；✅ A2/A3/A4 其实有牙齿

### 133.0 用了判据自带的能力（之前七轮都没碰过）

`verify_path.mjs:23` 有一个 `--mutate=` 模式，本节第一次用它。
⚠⚠⚴⚠ **它立刻暴露了一个七轮静态审计都没看出来的问题**——
⚠ 而且暴露的方式是**它自己打印的两行字**。

### 133.1 ⚗ 内建变异 `hide_intro`：印「已生效」，却是 36/36

```
RESULT OK 36/36
变异 hide_intro：已生效  (covered-by:__mutOverlay)
```

⚠⚠⚴⚠ 屏幕被一整层 `__mutOverlay`（`position:fixed;inset:0;z-index:99999`）盖住，
⚠⚠⚴⚠ **`A2 容器可见且未被遮挡` 与 `A3 内容块可见且未被遮挡` 照样绿。**

⚠⚠⚴ 而这两条的判据名恰恰是「**未被遮挡**」。

### 133.2 行号给出的解释（本节唯一的依据，不靠印象）

```
:86    await page.eval(`document.querySelector('#tabPath').click(); true`);
:96    const d = JSON.parse(await page.eval(`(() => { …`          ← 取数
:103       visWrap: window.__vp(q('#pathWrap')),                  ← __vp 被调用
:120   check('A2 容器可见且未被遮挡', d.visWrap.ok, …);            ← 当场判决
:121   check('A3 内容块可见且未被遮挡', d.visBlk.ok, …);           ← 当场判决
:257       d.id='__mutOverlay'; …                                 ← 遮挡层，晚 136 行
:265   check('M1 加一层遮挡后，可见性检查必须判「被别的元素盖住」', covered, …);
```

⚠⚠⚴⚠ **A2/A3 在遮挡层存在之前就已经判完了** ⇒ 该变异对它们**零影响**。

⚠⚠⚴⚠⚠ 而 `M1` 测的是 **`window.__vp` 这个辅助函数**，
⚠⚠⚴⚠ **不是用它的判据**。
⚠⚠⚴ 它说得没错（`__vp` 确实判出了 `covered-by:__mutOverlay`），
⚠⚠⚴ **但它没有证明任何一条判据会因为被遮住而变红。**

⇒ ⚠⚠⚴⚠⚠⚠ **新病型**：

> **变异台装在判据之后 ⇒「变异已生效」与「判据全绿」可以同时为真。**
> ⚠⚠⚴ 而输出读起来像「判据扛住了扰动」——
> ⚠⚠⚴⚠ **这是「恒绿」最隐蔽的一种形态：扰动真的发生了，只是它够不着判据。**

### 133.3 ✅ A2/A3/A4 **确实有牙齿**（问题在装置，不在判据）

⚠ 派生副本 `.cache/mutbak/r133a_path_earlyoverlay.mjs`：把遮挡层**提前**到
`:86` 之后、`:96` 取数**之前**（注入块不做任何判定，结论由未改动的原判据给出）：

```
[扰动已落地] #pathWrap {"ok":false,"why":"covered-by:__earlyOverlay"}
             [data-pathblock] {"ok":false,"why":"covered-by:__earlyOverlay"}
RED  A2 容器可见且未被遮挡  {"ok":false,"why":"covered-by:__earlyOverlay"}
RED  A3 内容块可见且未被遮挡  {"ok":false,"why":"covered-by:__earlyOverlay"}
RED  A4 引导页已关（否则整屏被遮）
RESULT FAIL 33/36
```

⚠⚠⚴⚠ **A2/A3/A4 是有牙齿的** ⇒ ⚠⚠⚴⚠ **这条不能记成判据的缺陷**，
⚠⚠⚴ 记成「**验证装置装错了位置**」——
⚠⚠⚴ 而这正是本节要留下的那条：**装置的位置错了，结论就全错，而且看不出来。**

### 133.4 ⚠⚠⚴⚠⚠ 同一个病在 `drop_mech` 上重演，而且这次伤到已验过的判据

```
RESULT OK 36/36
变异 drop_mech：已生效  (文案已不在 innerText)
```

⚠⚠⚴⚠ **机制文案确实被删掉了**（M2 重新读 `innerText`，判「已不在」），
⚠⚠⚴⚠ **而 B4「印出机制结论」仍然绿。**

⚠ 根因与 §133.2 **同源**：

```
:96    const d = JSON.parse(… T: txt …)     ← 取数（txt 来自 #pathWrap.innerText）
…
:136   const T = d.T;                        ← ⚠ T 是**一次性快照**
:146   for (const [name, needle] of phrases)
:147     check(name, T.includes(needle), …)  ← B 组 13 条全部读这个快照
```

⚠⚠⚴⚠⚠ **实测结论**：

> **B 组 13 条 + C 组 5 条（C5–C9）= 18 条 needle 判据，全部读 `:96` 的一次性快照 `T`。**
> ⚠⚠⚴⚠ ⇒ **它们对「取数之后发生的页面变化」完全无感**——
> ⚠⚠⚴⚠ `drop_mech` 这一轮就是证据：页面真的丢了那句话，B4 仍然绿。

⚠⚠⚴⚠ **这不推翻修订 128/131 的结论**，但**限定**它：
⚠⚠⚴ 修订 128/131 证明的是「**判据读到了屏上那句话**」（扰动的是快照内容，判据跟着红），
⚠⚠⚴⚠ **没有**证明「**判据读的是读者当下看到的那句话**」——
⚠⚠⚴⚠ 因为快照与读者所见之间可以隔着一次重渲染。

⚠⚠⚴ 另注：D3 会**切题**（`:192-210`），切完之后 `T` 与 `d.pid` 都还是**切题前**的。
⚠⚠⚴ B/C 组在切题后**不再重跑** ⇒ 它们验的是**原题**的文案与数值，**自洽但已旧**。
⚠ 本节**不判这是缺陷**（它与本屏的设计意图是否一致，属产品口径），只登记事实。

### 133.5 ⚠⚠⚴ A4 的 detail 串**在判红时说相反的话**

`verify_path.mjs:122-123`：

```javascript
check('A4 引导页已关（否则整屏被遮）', !hadIntro || d.visWrap.ok,
  hadIntro ? '引导页开过，但关掉后容器可见' : '本次没出现引导页');
```

⚠⚠⚴⚠ detail 是**按 `hadIntro` 二选一的常量**，与 `d.visWrap.ok` **毫无关系**。
⚠⚠⚴ 本节实跑：A4 **判红**，而它打出来的是：

```
RED  A4 引导页已关（否则整屏被遮）  引导页开过，但关掉后容器可见
```

⚠⚠⚴⚠ **判红的同一条，detail 在断言「可见」。**
⚠⚠⚴ 这是「披露 ≠ 判决」的又一例：detail 是给人看的说明，
⚠⚠⚴⚠ **它不参与判定，却会被人当成判定结果读**。

⚠ 与 A2/A3 的对比很清楚：这两条的 detail 是 `JSON.stringify(d.visWrap)`，
⚠⚠⚴ **由实际取值派生** ⇒ 不会说反话。⚠⇒ **detail 应当一律由结果派生**。

### 133.6 本节口径与**没有**做的事

- ⚠ 本节**没有改任何判据、没有改任何产品、没有改任何产物**；
  `verify_path.mjs` 是从已提交版本派生副本跑的，原文件未动。
- ⚠⚠⚴⚠ **本节没有说 A2/A3/A4 是虚绿**——恰恰相反，**实测证明它们有牙齿**（§133.3）。
  ⚠⚠⚴⚠ 本节说的是**验证装置装错了位置**。
- ⚠⚠⚴ 本节**没有**推翻修订 128/131，只是**限定**了它们证明的范围（§133.4）。
- ⚠ 派生副本的注入块**只加遮挡层、不做任何判定**，
  ⚠⚠⚴ 且**落地核验**（`__vp` 自己必须判出 `covered-by`）写在注入块里，
  ⚠⚠⚴⚠ 否则「没遮住」会被读成「判据扛住了扰动」。

### 133.7 新增待拍板（本节产出，与既有 19 条并列为 22）

1. ⚠⚠⚴⚠⚠ **内建变异台要不要重排**：`--mutate` 的注入点目前在取数之后，
   ⚠⚠⚴⇒ 它只能测辅助函数，测不到任何一条主判据。
   ⚠⚠⚴⚠ 修法是**每条判据配自己的变异**（A 组配遮挡、B/C 组配文字删除、
   D 组配点击失效），⚠⚠⚴ **且注入点必须在取数之前**。
   ⚠⚠⚴ 改前先算功效（修订 123 的做法）。
2. ⚠⚠⚴⚠⚠ **B/C 组 18 条要不要改成实时读 `innerText`**：
   ⚠⚠⚴ 现在读 `:96` 的一次性快照，⚠⚠⚴ **对取数之后的页面变化无感**（`drop_mech` 实测）。
   ⚠⚠⚴⚠ 这是**判据侧**改动；⚠⚠⚴ 但会牵动修订 128/131 已验过的 18 条，**须一并重验**。
3. ⚠⚠⚴ **A4 的 detail 要不要改成由结果派生**（照 A2/A3 的写法）。
4. ⚠⚠⚴ **D3 切题后 B/C 组不重跑**是否算缺陷，取决于本屏设计意图（产品口径）。
"""


def main() -> int:
    with open(PRE, 'r', encoding='utf-8') as f:
        old = f.read()
    assert old.endswith('\n'), '⚠ 追加前必须以 \\n 结尾'
    before_sha = hashlib.sha256(old.encode('utf-8')).hexdigest()
    print(f'[追加前] 行数={old.count(chr(10)) + 1} sha256={before_sha[:16]} 以\\n结尾=✓')

    new = old + BODY
    assert new.startswith(old), '⚠ 原文前缀被改动'
    assert hashlib.sha256(new[:len(old)].encode('utf-8')).hexdigest() == before_sha, '⚠ 原文前缀哈希变了'
    assert new.count('\ufffd') == 0, '⚠ 追加内容含 U+FFFD'
    assert new.endswith('\n'), '⚠ 追加后必须以 \\n 结尾'

    with open(PRE, 'w', encoding='utf-8') as f:
        f.write(new)
    with open(PRE, 'r', encoding='utf-8') as f:
        chk = f.read()
    assert hashlib.sha256(chk[:len(old)].encode('utf-8')).hexdigest() == before_sha, '⚠ 回读后原文前缀变了'
    assert chk == new, '⚠ 回读内容 != 预期'
    print(f'[追加后] 行数={chk.count(chr(10)) + 1} sha256={hashlib.sha256(chk.encode()).hexdigest()[:16]}'
          f' U+FFFD={chk.count(chr(0xfffd))} 原文前缀逐字节未变=✓')
    print('[顶层标题] ' + '\n[顶层标题] '.join(
        l for l in chk.splitlines() if l.startswith('## ') and '修订 133' in l))
    return 0


if __name__ == '__main__':
    sys.exit(main())