#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r136_append_prereg.py —— 追加修订 136（只追加，不改原文）"""
import hashlib
import sys

PRE = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = """
## 修订 136 —— ⚠⚠⚴⚠⚠ **更正修订 134 的三处**；✅ D3 有牙齿；⚠⚠⚴⚠⚠ 「落地核验过了 + 判据仍绿」有三种可能

### 136.0 ⚠⚠⚴⚠⚠⚠⚠ 本节更正**修订 134 §134.4 的三处结论**

⚠⚠⚴⚠⚠ 修订 134 记的是：

```
臂 pair：pairOpts {before:6, after:1}
[SKIP] D3 切题后 pid 跟着换: 只有一道题，无从切
RESULT OK 34/34        ← ⚠ 分母从 36 变成 34
跳过 1 条（**不进分母**，N/M 里不含它们）
⚠ D3 与 D4 同在一个 else{} 里 ⇒ **一起跳过、不进分母、被单独列名**（修订 118 的纪律，工作正常）
⚠⚠⚴⚠⚠ **但「36」是「本次运行实际执行了 36 条」，跳过时会变。**
```

⚗⚗⚗⚗⚗ **第一处更正：「只有一道题，无从切」这句话是**我自己删出来的**。**

⚠⚠⚴⚠⚠ r134b 的 pair 臂注入块是：

```js
const before = sel ? sel.options.length : -1;
if (sel) { while (sel.options.length > 1) sel.remove(1); sel.selectedIndex = 0; }
```

⚠⚠⚴⚠⚴ **它把下拉从 6 个 option 删到只剩 1 个** ⇒ D3 自然找不到「另一道题」。

⚠⚠⚴⚠⚴⚠⚠ **实跑基线证明页面本来有 6 道题可选**：

```
$ CDP_PORT=9610 node .cache/browser_verify/verify_path.mjs
RESULT OK 36/36          ← 无任何 SKIP 行
```

⚠⚠⚴⚠⚴ `r136a` 的只读测量（`location.href` / `#pathWrap` 1267 字 / pid 三道交叉自证全过）：

```
  <SELECT id="selPair">  optionCount = **6**  selectedIndex=0
    [0] "1983_I_1  共同前缀 27 步  未闭合"     [3] "1986_I_1  共同前缀 23 步  未闭合"
    [1] "1984_I_1  共同前缀 15 步  未闭合"     [4] "1987_I_1  共同前缀 44 步  未闭合"
    [2] "1985_I_1  共同前缀  8 步  未闭合"     [5] "1988_I_1  共同前缀 16 步  未闭合"
  每一道题的 pid 在整页 HTML 里：**6 个全部出现**
```

⚠⚠⚴⚠⚴ **⇒ 修订 134 那次「跳过」是扰动制造的假跳过。**
⚠⚠⚴⚠⚴ **⇒ 「跳过机制工作正常」这半句仍然对**（机制确实按修订 118 的方式工作），
⚠⚠⚴⚠⚴ **但「只有一道题」这个原因是我自己造成的，不是页面的性质。**

⚠⚠⚴⚠⚠ **第二处更正：「36 是本次执行条数，不是判据条数」这个表述要收窄。**

⚠⚠⚴⚠⚴ 基线跑的是 **36 条，D3/D4 在其中且通过了** ⇒ **36 同时也是基线的判据条数**。
⚠⚠⚴⚠⚠ pair 臂的 34 是**因为我的扰动让 2 条失去了运行条件**。
⚠⚠⚴⚠⚴ ⇒ ⚠ **不能推广成「N/M 每次都会变」** —— 变的是**扰动**，不是判据。

⚠⚠⚴⚠⚴⚠⚠ **第三处更正（新病型）：用扰动改变分母，再把分母变化当成判据的性质。**

> ⚠⚠⚴⚠ **扰动制造的现象 ≠ 页面本来的性质。**

⚠⚠⚴⚠⚴ 形态与修订 133「变异已生效 ≠ 经过取值点」同族，但**更基础**：
⚠⚠⚴⚠⚴ 那一类问的是「扰动有没有经过判据的取值点」，
⚠⚠⚴⚠⚴ 这一类问的是「**这个现象原本就在吗**」。

⚠⚠⚴⚠⚴ ⇒ **固化：报告任何「跳过」「不存在」「没有」之前，必须先问
「这是页面本来如此，还是我的扰动造成的」。**
⚠⚠⚴⚠⚴ ⚠ **判别式**：跑一次**无扰动基线**，看现象在不在。
⚠⚠⚴⚠⚴ ⚠⚠⚴ 基线一次 60 秒，比事后更正便宜几个数量级。

### 136.1 ✅ D3 有牙齿

```
臂 d3：{"k":"d3","before":1,"after":0,"note":"拆掉 change 处理器 ⇒ 派发 change 事件也不会换题"}
RED  D3 切题后 pid 真的换了  1983_I_1 → 1983_I_1
RESULT FAIL 35/36
```

⚠ 机制（`index.html:926`）：`sel.onchange = () => loadPair(+sel.value)`。
⚠ 判据 `:197` 走 `sel.dispatchEvent(new Event('change'))` ⇒ 拆掉 `onchange` 就换不了题。

⚠⚠⚴ ⚠ **本次没连带 D4 红**：pid 没换 ⇒ `sw.after === sw.before` ⇒
`q1 = prod.problems[sw.before]` 正是当前题 ⇒ `q1.k === sw.k` ⇒ **D4 绿**。
⚠⚠⚴ ⇒ **D4 要单独立臂**，见 §136.2。

### 136.2 ⚠⚗⚗⚗ d4 臂：**落地核验过了，判据仍绿** —— 而且这次是**我错了**

```
臂 d4：{"k":"d4","before":1,"after":0,"note":"改页面内部 S.dv.problems 里的 k，产物 prod.problems 不动"}
RESULT OK 36/36          ← 扰动落地了，D4 却绿
```

⚠⚠⚴⚠⚠⚠⚠ **若照字面记「D4 假通过」，这就是第 4 次「仪器自己发结论」，
而且会证伪一条好判据。** 当场否掉，查清了真因：

⚠⚠⚴ `renderPathPanel()` 的 `k` 来自 **`S.path`**（`index.html:1599`
`const q = S.path.problems[pid]; const k = q.k;` ⇒ `:1606` 写进 `data-pathk`），
⚠⚠⚴⚠⚴ 而我扰动的是 **`S.dv`** —— 那是**另一个文件**的页面副本：

```
  S.path ← path_readout.json        （index.html:1065-1067）  ← 第 5 屏 + D4 读这份
  S.dv   ← divergence_readout.json  （index.html:979-981）     ← 第 4 屏分叉读出
```

⚠⚠⚴⚠⚠ **⇒ 我改的文件与 D4 读的文件根本不是同一个。**
⚠⚠⚴ **⇒ 本节不给 D4 任何结论**（扰动无效 ⇒ 仪器坏了 ⇒ 仪器坏了不是判据结论）。

⚠⚠⚴ **D4 的口径本身是对的**：它读的 `sw.k`（页面侧）与 `prod.problems[after].k`（产物侧）
**来自同一个 `path_readout.json` 的两个副本** ⇒ 它测的正是「页面 vs 产物」。

⚠⚠⚴⚠⚠⚠⚠ **本节最值钱的一条（三分律）**：

> ⚠⚠⚴⚠ **「落地核验通过」+「判据仍绿」有三种可能，不能只取一种解释：**
>
> | 解释 | 怎么区分 |
> |---|---|
> | ① 判据真的虚绿 | occ 定义在**判据读的那个量**上，且扰动确实经过它 |
> | ② **扰动与判据无关**（仪器坏了） | occ 量的是「我改的对象」，不是「判据读的对象」 |
> | ③ 扰动被中途事件撤销 | occ 过，但被验判据的取值点在扰动之后又渲染过 |
>
> ⚠⚠⚴⚠⚠ **d4 这一轮是 ②。** 而 ② 的危险在于：
> ⚠ **落地核验会通过**（因为 occ 与扰动量一致），
> ⚠ **判据也会绿**（因为它读的是别的东西）——
> ⚠⚠⚴⚠ **两个都「正常」，合起来是一个假发现。**

⚠⚠⚴⚠ ⇒ **固化：occ 一律定义为「被判据断言的那个量，当前是否为真」，转 0/1。**
⚠⚠⚴⚠ ⚠ 这已经是**第三次**栽在这上面（修订 135 的 c4、修订 136 的 d4、以及本节的教训）。
⚠⚠⚴⚠ ⚠⚠⚴ **「我扰动的那个量」与「判据读的那个量」必须是同一个**，机械上查不了
⇒ 台子该加必填 `criterion` 字段并打印（已在 r135 规格里试加，见下）。

⚠⚠⚴ ⚠ **注**：`r136_spec.json` 的 8 个臂已经带 `criterion` 字段（判据表达式原文），
⚠⚠⚴ 台子目前**只打印不校验** ⇒ 它是给人眼核对的，不是闸门。⚠ 待办见 §136.6。

### 136.3 ⚗⚗⚗ 一个**假缺口**，当场撤回

⚠⚠⚴ 静态对账发现：页面同时加载两份产物，**两份都有 `problems[pid].k`**，
⚠⚠⚴ 而第 4 屏用 `S.dv` 的 k、第 5 屏用 `S.path` 的 k。

⚠⚠⚴⚠⚴ 我据此写了一句「⚗ 全部 86 个判据脚本里**没有任何一处**引用 divergence_readout.json」。

⚗⚗⚗⚗⚗ **这句话是错的，当场撤回。**

```
.cache/browser_verify/verify_divergence_readout.mjs:1:
  // 验收：候选词读出这一块（divergence_readout.json）在真实页面里。
.cache/browser_verify/verify_divergence_readout.mjs:5:
  //   divergence_readout.json 是**只有页面读、没有任何判据读**的那两份之一。
```

⚠⚠⚴⚠⚴ **该文件存在，且有 V0–V6 七条判据**，正是为验这份产物写的。

⚠⚠⚴⚠⚠⚠⚠ **错在哪**：

1. ⚠⚠⚴⚠⚠ 那次 `grep -rn divergence_readout .cache/browser_verify/` 的输出**被浏览器 profile
   的二进制缓存污染**（满屏 `Binary file .../Cache_Data/... matches`），
2. ⚠⚠⚴⚠⚠ **任务输出被外部化**，我**读到前两段就下了结论**，没有读完。

⚠⚠⚴⚠ ⚠ **判别式**：

> ⚠⚠⚴⚠ **grep 输出里出现 `Binary file … matches` = 输出不完整。**
> ⚠⚠⚴⚠⚠ 必须换 `-I`（忽略二进制）重跑，**并且必须读全输出**再下结论。
> ⚠⚠⚴⚠⚠ 「什么都没找到」和「没找到是因为我只看了前面」输出形状完全一样。

⚠⚠⚴⚠ **固化两条**：
- ⚠⚠⚴⚠ **任务输出被外部化时必须读全**，不能凭前几段下结论；
- ⚠⚠⚴⚠ **下「不存在」「没有」「无人核」这类结论前，先用 `grep -I` 复核一遍**——
  ⚠⚠⚴ 这种结论会把「没核」和「我没看到」混为一谈。

### 136.4 ⚠ 跨文件 `k` 一致性：**缺口，不是缺陷**

静态对账（纯算术）：

```
  pid          path.k    dv.k   一致?
  1983_I_1          27      27   ✓
  1984_I_1          15      15   ✓
  1985_I_1           8       8   ✓
  1986_I_1          23      23   ✓
  1987_I_1          44      44   ✓
  1988_I_1          16      16   ✓
  一致 6 / 不一致 0 / 缺字段 0
```

⚠ **两份产物的 `k` 当前完全一致** ⇒ **不是产品缺陷。**

⚠⚠⚴ ⚠ **但没有任何判据保证它们一致**：
`verify_divergence_readout.mjs` 核的是那一屏的**显示内容**
（`c4_random_hits`、层选择器、破折号等），**不核它与 `path_readout.json` 的 `k` 是否相同**；
`verify_path.mjs` 的 D4 核的是 path 侧 vs 产物侧，**不碰 divergence 侧**。

⚠⚠⚴⚠ ⇒ **两个判据之间有一条没人核的跨文件约束。**
⚠⚠⚴⚠ **数据现在是对的，所以这是「缺口」不是「缺陷」** —— 但若将来某次重跑只更新一份产物，
⚠⚠⚴⚠ **读者会在第 4 屏和第 5 屏看到不同的 k，而 7+3 条判据全绿。**

⚠⚠⚴ 待拍板（新增第 7 条）：要不要补一条判据核「两份产物的 `k` 逐题一致」。
⚠⚠⚴ ⚠ 改前先算功效（它有 6 个取值点，needle 唯一 ⇒ 预期够得着）。

### 136.5 本轮跑了 2 臂，剩 6 臂**已生成未跑**

| 臂 | 扰动 | 状态 |
|---|---|---|
| d3 | 拆掉 `sel.onchange` | ✅ **已跑，有牙齿** |
| d4 | （改 `S.dv`） | ⚗ 扰动无效，见 §136.2 |
| a1 | 改 `data-pathstate` 为 `broken` | ⚠ 已生成未跑 |
| a7 | 把 `#cv` 变回可见（**极性与其余相反**） | ⚠ 已生成未跑 |
| c1 | 改 `data-pathk` | ⚠ 已生成未跑 |
| c2 | 改分叉行的 `data-patht`（保留 `data-pathfork=1`） | ⚠ 已生成未跑 |
| c3 | 删一个**非分叉**行（occ **实时**查 DOM） | ⚠ 已生成未跑 |
| e1 | 设 `window.renderPathPanel = undefined` | ⚠ 已生成未跑 |

⚠⚠⚴ ⚠ **c3 已预埋一个修订 134 坑 6 的变体**：occ 若用捕获的数组
`rows.length`，`victim.remove()` 之后**数组长度不变** ⇒ 落地核验假通过。
⚠⚠⚴ ⚠ 规格里已改成**实时** `document.querySelectorAll('[data-patht]').length`。

⚠⚠⚴⚠⚴ ⚠ **未跑的臂一律记「未跑」，不记「未验」，也不进任何分母**（修订 118 的纪律）。

### 136.6 本轮新增待拍板（累计 28 条）

1. ⚠⚠⚴⚠ **「两份产物的 k 逐题一致」要不要补判据**（§136.4，当前数据一致，缺的是守卫）
2. ⚠⚠⚴⚠ **台子的 `criterion` 字段要不要从「打印给人看」升成必填闸门**（§136.2）
3. ⚠⚠⚴⚠⚠ **D4 要不要按正确口径重跑**（改 `S.path.problems[pid2].k`，不是 `S.dv`）
4. ⚠⚠⚴⚠ **基线跑一次要固化进流程** —— 60 秒，能挡住「扰动制造的假现象」（§136.0）
5. ⚠⚠⚴⚠ **`grep -rn` 要不要一律加 `-I` 并读全输出**（§136.3）
6. ⚠⚠⚴ **剩下 6 臂（a1/a7/c1/c2/c3/e1）要不要下一轮跑完**（§136.5）
7. ⚠⚠⚴ **c3 臂预期会连带 D2 转红**（D2 数的是同一个 `[data-patht]` 集合）—— 算不算臂不纯

### 136.7 校验

- ⚠ **19 个守卫：17 exit=0 + 2 条有意判红** —— 与修订 134/135 逐条一致 ⇒ 无回归
- ⚠ `verify_path.mjs` **原文件未动**；8 个副本全过台子的门（`node --check` + 逆变换逐字节 +
  反引号计数 + U+FFFD + 落点双向锁定）
- ⚠ 本节只追加披露：**没改任何判据、没改任何产品、没碰任何产物**
"""


def main() -> int:
    with open(PRE, 'r', encoding='utf-8') as f:
        old = f.read()
    assert old.endswith('\n'), 'W 追加前必须以换行结尾'
    before_sha = hashlib.sha256(old.encode('utf-8')).hexdigest()
    print('[追加前] 行数=%d sha256=%s 以换行结尾=OK' % (old.count(chr(10)) + 1, before_sha[:16]))

    new = old + BODY
    assert new.startswith(old), 'W 原文前缀被改动'
    assert hashlib.sha256(new[:len(old)].encode('utf-8')).hexdigest() == before_sha, 'W 原文前缀哈希变了'
    n_bad = new.count(chr(0xFFFD))
    assert n_bad == 0, 'W 追加内容含 U+FFFD（%d 处）' % n_bad
    assert new.endswith('\n'), 'W 追加后必须以换行结尾'

    with open(PRE, 'w', encoding='utf-8') as f:
        f.write(new)
    with open(PRE, 'r', encoding='utf-8') as f:
        chk = f.read()
    assert hashlib.sha256(chk[:len(old)].encode('utf-8')).hexdigest() == before_sha, 'W 回读后原文前缀变了'
    assert chk == new, 'W 回读内容 != 预期'
    print('[追加后] 行数=%d sha256=%s U+FFFD=%d 原文前缀逐字节未变=OK'
          % (chk.count(chr(10)) + 1, hashlib.sha256(chk.encode()).hexdigest()[:16], chk.count(chr(0xFFFD))))
    print('[顶层标题] ' + '\n[顶层标题] '.join(
        l for l in chk.splitlines() if l.startswith('## ') and '修订 136' in l))
    return 0


if __name__ == '__main__':
    sys.exit(main())