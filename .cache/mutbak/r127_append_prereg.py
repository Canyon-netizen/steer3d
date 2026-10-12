#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 127 追加器 —— 纯披露 + 撤回一条。

纪律：
  · 预登记原文**只追加、不改写**；
  · 追加前断言文件以 '\\n' 结尾；
  · 追加后断言**原文前缀逐字节未变**；
  · 断言 U+FFFD == 0。
"""
import hashlib
import os

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

SECTION = """
## 修订 127 —— 撤回 §126.3 一条（前提是跑错页面）；⚠⚠⚴ 判据分两族、两个页面；新病型「双层区分度失配」

### 127.0 ⚗⚗⚗ 撤回 §126.3 的一条 —— 它的前提是**跑错了页面**

§126.3 原文写：「⚠ 实测**全页 8 个** `[data-verdict]`，其中 4 个不在任何
`[data-axis-row]` 内」「⚠⚠ `verify_patch.mjs:128` 用的是裸
`document.querySelectorAll('[data-verdict]')` ⇒ 与
`probe_dedup_rendered.mjs:88-90` 同族」。

⚠⚴⚴⚴ **那条「全页 8 个」是在 `http://127.0.0.1:9006/`（Next.js 的 **React 页**）
上数出来的**，而 `verify_patch.mjs` 用的是 `LAT_URL`，验的是
`http://127.0.0.1:9006/latent/index.html`（**静态产物页**）。
⇒ **两个不同的页面、同一个端口、靠路径区分。**
⇒ §126.3 的「实测 8 个」「4 个在 axis-row 外」**整条作废**，
    「跨面板误判」的推断也随之作废。

✅ **权威证据（用目标程序自己的输出，不用外部复算）**：

```
LAT_URL=http://127.0.0.1:9006/latent/index.html node .cache/browser_verify/verify_patch.mjs
→ 13/13 passed
[PASS] P3 判决表三态用的都是人看得见的字（成立/不成立/没测），不是只有 data-*
       页面出现：{"fail":7,"na":13,"pass":9}；产物里 pass/fail/na 的门数：9/7/13
[PASS] P2 判决表按**门键**与产物 gates[] 逐行一致
       DOM 29 行 / 产物 29 门；不一致 []
```

✅ **独立复核**（本轮新写的探针 `.cache/mutbak/r127_patch_scope_probe.mjs`，
跑在**正确页面**上、已切到 `tabPatch`、已关导读浮层）：

```
[data-verdict] 29 个 · [data-gate] 行 29 个
其中在 [data-gate] 行内：29/29  ⇒ ✅ 同一批元素（数目相等不是巧合）
门键对账：DOM 29 / 产物 29 · 只在 DOM [] · 只在产物 []
```

⚠⚴ **口径**：判定「是不是同一批元素」用的是 **`closest('[data-gate]')`**，
**不是**数目相等 —— 两个数相等也可能是两批各 29 个。
⚠ 这一步是「两个独立方法一致不构成验证」的同族：数目一致只能排除巧合，
**归属关系**才是那件事本身。

⇒ 结论：`verify_patch.mjs` 的裸选择器**当前不构成误判**。
⚠⚠ **但「当前不」≠「结构上不会」** —— 它仍然是**裸 `document` 作用域**，
哪天别的面板印出「成立/不成立/没测」就会被喂饱。
⚠ 与 `verify_path.mjs:95` 的对比见 §127.4：**同一屏里 P2 有作用域、P3 没有**。

---

### 127.1 ⚠⚠⚴⚠ 判据**分两族、跑在两个页面**上 —— 而「228 个调用点」跨了两页

| 判据脚本 | URL 变量 | 实际页面 | 屏 |
|---|---|---|---|
| `verify_subspace` | `BV_URL` | `9006/` **React 页** | Subspace |
| `verify_relamp` | `BV_URL` | 同上 | relamp |
| `verify_scene_link` | `BV_URL` | 同上 | Scene3D |
| `verify_hinge_panel` | `BV_URL` | 同上 | hinge |
| `verify_heldout` | `BV_URL` | 同上 | Heldout |
| `verify_axis_readout` | `BV_URL` | 同上 | AxisReadout |
| `probe_dedup_rendered` | `BV_URL` | 同上 | dedup |
| **`verify_path`** | **`LAT_URL`** | **`9006/latent/index.html` 静态产物页** | `tabPath` |
| **`verify_patch`** | **`LAT_URL`** | **同上** | `tabPatch` |

⚠⚠ **这不是本轮的新发现，仓库早就写明了** ——
`verify_path.mjs:47` 的注释原文：「⚠ 目标页是 **latent 静态页**，不是根页。
`scan_panel_coverage.py` 按 …」

⚠⚠⚴⚴ 但它**污染了一个一直在用的数**：§119 的**「228 个调用点」**
是**八个文件的和**，而这八个文件分属**两个不同页面**
⇒ 那个「合起来 228」**不是「一个页面的判据总量」**。
⚠ 我此前一直用它算「PAGE_TEXT 桶多少条」「覆盖率多少」，
**那些百分比分母的口径必须重述**：
- **React 页**：**200**（= 228 − path 的 28）
- **静态产物页**：**28**（全部是 `verify_path`）
- ⚠⚴ `verify_patch.mjs` **不在这 228 之内** —— 它一直是独立统计的 13 条
⚠⚠⚴⚠⚴ **预登记里从来没有「页面归属」这一列** ——
§119.1 的逐文件表只有「静态调用点」与「手读状态」两列。
⇒ 这就是为什么 228 会被当成「一个页面的判据总量」连用了 8 个修订。
⚠ **建议**给 §119.1 那张表补一个页面归属列（本节不代改 §119.1：原文只追加、不改写）。

⚠⚠⚴ **§119.0 与 §119.1 的逐文件数不同，别引错版本**：

| 出处 | hinge_panel | path | 合计 |
|---|---|---|---|
| §119.0 复盘里引用的那一版 | 30 | 25 | 227 ← **历史值** |
| **§119.1 逐文件表（权威）** | **28** | **28** | **228** ✅ 与合计自洽 |

⚠ §119.0 那句「`229` 基础数不等于它那版的逐文件之和
（39+8+21+**30+25**+47+46+11 = 227）」引的是**旧版**分文件数。
⇒ ⚠ **引用逐文件数只能用 §119.1**；
⚠⚠⚴ 混用两版会让「228 − 静态页那份」算成 **202** 而不是 **200**。

⚠⚠⚴⚠⚴⚠⚴ **更要紧的是产品侧：这两个页面是两套独立的屏实现。**

| | React 页 `/` | 静态产物页 `/latent/index.html` |
|---|---|---|
| 实现 | `frontend/components/*.tsx` | `frontend/public/latent/index.html`（318 KB 手写 HTML） |
| 屏 | `SubspacePanel` / `AxisReadoutPanel` / `HeldoutPanel` / `Scene3DFallback` / `SteeringControl` … | `tabBar` `tabDelta` `tabDim` `tabLtv` `tabPatch` `tabPath` `tabThresh` `tabXY`（8 屏） |
| markdown 处理 | `md.tsx:13-21` 的 `Em`（`split("**")` + `<strong>`） | **无 `<strong>`、无 `split("**")`**（实测 §127.3） |

⇒ ⚠⚠⚴⚠⚴ **改一边，另一边不会跟着改** —— 这是**结构性漂移源**，
和之前那些「同一份逻辑写两遍」的裂缝是同一个病，但后果更大：
**读者看到的是哪一套，尚未有人拍板。**

⚠⚠⚴ **静态产物页的 8 屏里只有 2 屏有判据**（`tabPath` 36 条 / `tabPatch` 13 条）
⇒ **`tabBar` / `tabDelta` / `tabDim` / `tabLtv` / `tabThresh` / `tabXY` 六屏无判据。**

⚠⚠⚴⚠⚴ **并且静态页这 49 条（36 + 13）从未做过牙齿验证** ——
§125/§126 的 K2 台跑的是 `9006/`（React 页），**一页都没覆盖到静态页**。

---

### 127.2 ⚠⚠⚴⚠ 新病型：**双层区分度失配**（patch 判决表）

先说**被我自己的推断当场否掉**的那一步，免得下一轮照着错的方向修：

⚠⚠⚴ 产物侧实测：`path_patching.json` 的 **29 道门只有 8 种 `name`、
15 种 `(name, claim, arm_label)` 三元组，仍有 7 组重复**；
最刺眼的是 `「描述-因果重叠」` ×6 —— name / claim / arm_label **三者字面全同**。

⇒ 我据此推断「页面可见文字必然大量重复」。
⚠⚴⚴ **实测否掉了它**：判决表**第 1 列 29 行全部不同**。

```javascript
// frontend/public/latent/index.html（判决表渲染）
const who = [g.arm ? "["+g.arm+"]" : "", g.measure ? "["+g.measure+"]" : ""].join("");
<td><code>${esc3(who + (g.claim||""))}</code>
```

⚠⚴ **方括号是页面加的**：产物 `arm` 的值是裸 `"word"`，不是 `"[word]"`。
⚠⚴ 而 `G5` 那 6 道门的 claim 字面**完全相同、不含 measure 名**
⇒ **`[excessm]` / `[transfer]` / `[excess]` 是它们唯一的区分来源。**

⚠⚠⚴⚠⚴ **所以「`[measure]` 冗余、删掉即可」是错的修法** ——
照它改，`G5` 的 6 道门会彻底不可区分。
⇒ 这是「⚠⚠ 给出修复建议前先问『照这条做，结果真会变吗』」的又一次实例。

⚠⚠⚴⚠⚴ 病态的准确表述（三层口径，不可混算）：

| 层 | 区分度 | 谁给的 |
|---|---|---|
| `data-key`（data 层） | **29 种** ✅ | 产物 `gate_order` |
| 可见第 1 列 | **29 种** ✅ | ⚠ **页面拼的 `[arm][measure]` 机器记号** |
| 可见第 1 列**剔掉方括号记号后** | **16 种 / 29 行** ❌ | —— |

> ⚠⚴⚴⚠⚴ **读者能分清 29 道门，唯一的办法是读懂 `[word][excessm]` 这种记号。**
> **读者读不懂 ⇒ 等于没有区分度。**

⚠ 13 行重复的构成：`num` 组 13 道门的可见文字**字面全同**；
另 2 行是 `G4[word/excessm]` / `G4[word/transfer]` 同为「节点 1、2、3…」。

⚠⚠⚴ 汇总块更糟（`[data-patch-fails]`，实测 320 字**未截断**）：

```
20 / 29 道门没有通过 不成立：[word]内容窗可定位、[word]内容窗可定位、
[word]描述-因果重叠、[word]对照不等价、[word]内容窗可定位、
[word]描述-因果重叠、[word]对照不等价 　｜　没测：[num]反事实存在、
[num]存在方向性层、[num]存在方向性层、[num]存在方向性层、…
```

⚠⚴ **7 道不成立的门印成 4 种字符串**（`[word]内容窗可定位` 出现 3 次）。
⚠⚴ `[word]` ×7 + `[num]` ×13 = **20 次**，恰好等于 20/29 道门没通过
⇒ **每一道没过的门都在汇总块里印了一次机器记号。**

⚠⚠⚴⚠⚴ **判据侧的确定性缺陷**：
`verify_patch.mjs:95` 里
`claim: (tr.querySelector('td code')||{}).textContent || ''`
—— ⚠⚠ **判据把判决表第 1 列的完整可见文字读进来了，
而 `mism` 只 `push` `gate` / `key` / `verdict` 三类，`claim` 与 `evidence`
**一个都没被核**。**
⚠ 也就是说：**判据手里握着唯一能抓到上面这个缺陷的字段，放着没用。**
⚠ `claim` 一旦要核，现在就会红（16/29）⇒ 新判据上线即红是**正确的**
（它标出了一个真缺陷，不是口径收紧）。

⚠ `data-gate="${g.name}"` ⇒ ⚠⚴⚠ **`data-gate` 装的是 `name`（8 种），
不是 `key`（29 种）** ⇒ §`verify_patch.mjs:84` 注释警告的
「按门名匹配会把它们认成同一个」在**实现上是对的**（用的是 `data-key`），
⚠ 但**任何改用 `data-gate` 做唯一性判断的后续改动都会立刻失效**。

⚠ `arm_label` 现成是人话（`改数字（同一道题）` / `改说法（同一道题）`），
⚠⚠⚴ **页面一行都没用**；⚠ 且 `G0` / `G0b` 两道门的 `arm_label` 是 `null`
⇒ 换成人话标签时这两道要单独处理，否则会印出 `null`。

---

### 127.3 ⚠⚠⚴⚠ 静态产物页实测：`**` **原样露给读者**，而有判据的两屏全绿放过

⚠⚠ 源码层证据（`frontend/public/latent/index.html`）：
**无 `<strong>`、无 `split("**")`**。
⚠ 但「源码没找到处理」**不等于**「页面上没有」⇒ 必须实测每一屏的 `innerText`。

✅ 实测（探针 `.cache/mutbak/r127_latent_markdown_probe.mjs`，
逐屏点 8 个 tab，量该屏可见文字里 `**` 的出现次数）：

| 屏 | 该屏可见字数 | `**` 次数 | 有判据？ |
|---|---|---|---|
| `tabBar` | 20173 | 0 | ⚗ 无判据 |
| `tabDelta` | 31880 | 0 | ⚗ 无判据 |
| `tabDim` | 20183 | 0 | ⚗ 无判据 |
| **`tabLtv`** | 28697 | **32** | ⚗ **无判据** |
| **`tabPatch`** | 25010 | **30** | ✅ `verify_patch.mjs`（13 条） |
| **`tabPath`** | 21184 | **2** | ✅ `verify_path.mjs`（36 条） |
| **`tabThresh`** | 21118 | **4** | ⚗ **无判据** |
| `tabXY` | 20172 | 0 | ⚗ 无判据 |

⚠⚠⚴⚠⚴ **两条并列的结论**：

1. ⚗ **无判据的屏里，`tabLtv` 32 + `tabThresh` 4 = 36 处 `**` 露出，
   连判据都没有。**
2. ⚗⚠⚴ **有判据的两屏，`tabPatch` 30 + `tabPath` 2 = 32 处露出，
   `verify_patch` 13/13、`verify_path` 36/36 全绿放过。**
   ⚠⚠⚴⚠⚴ 而 grep 证实：**这两个脚本里没有任何一条判据表达式涉及 `**`**
   （`verify_path.mjs` 14 处命中、`verify_patch.mjs` 10 处命中，
   **全部在注释里**）⇒ 判据**结构上就不可能**抓到它。

⚠⚠⚴⚠⚴⚠⚴ **这直接限定了 §122 的结论口径。**

§122 判定「G2/G3/G4 结构上永不可能通过」，依据是
`frontend/components/md.tsx:13-21` 的 `Em` 全部功能就是 `split("**")`。
⚠⚠⚴ **那是 React 页。** 静态产物页**没有** `Em`
⇒ ⚠⚠⚴⚠⚴ **同一个 `**`，在 React 页上永不出现、在静态产物页上原样露出。**
⇒ §122 的结论**只覆盖 `verify_heldout` 所在的那一页**，
**不能外推到静态产物页**。

⚠⚠⚴⚠⚴⚠⚴ **而仓库里早就有一条方向相反的既定判据**：
`verify_hinge_panel.mjs:262` 的 **H9**「页面无 markdown 残留与内部路径」
（React 页）⇒ **「不许露」这条规则已经存在**，
只是**只对 React 页生效**，静态产物页那 32 处没人管。

⚠ 产物侧对照：全库 34 个 JSON 里 `**` 共 **2627** 处，其中
`vocab.json` 1558 / `bpath_marker_steering.json` 426 / `answer_readout.json` 209 /
`path_patching.json` 30 / `heldout_readability.json` 16 …
⚠⚴ **静态页实际取用哪些产物，本轮未测准** —— 它的路径是
`base + "xxx.json"` / `dataBase()` **拼出来的**（§127.6-4），
⇒ 「取用面」这个数**本轮无法判定**，不报数。

---

### 127.4 ⚠⚠⚴ 「同一屏内作用域不一致」：`P2` 有作用域、`P3` 没有

```javascript
// verify_patch.mjs:95 —— P2
[...document.querySelectorAll('[data-gate]')].map(tr => ({ key: tr.getAttribute('data-key'), … }))
// verify_patch.mjs:128 —— P3
[...document.querySelectorAll('[data-verdict]')].map(tr => tr.children[1] ? … )
```

⚠⚴ `P2` 用 `[data-gate]`（**判决表自己的行**），
`P3` 用裸 `[data-verdict]`（**全页同名属性**）。
⚠⚴⚠⚴ **同一屏、同一份判据脚本里，两个判据的取数作用域不一致。**

⚠ 本轮实测这**没有**造成误判（29/29 都在 `[data-gate]` 行内，§127.0），
⚠ **但它成立的原因不是判据写对了，而是那个页面上恰好只有判决表在用这个属性名**。
⚠ 与 `probe_dedup_rendered.mjs:88-90` 已修过的那条同族。

⚠⚠ **口径提醒**：P3 的匹配是 `w === need[k]`（**严格相等**），
而本轮的探针用的是 `includes` ⇒ **两个口径**。
本轮两者**都**没在错误的元素上命中，**结论一致**；但**计数必须紧挨口径**印。

---

### 127.5 ⚠⚠⚴ 本轮仪器自己栽的五个跟头（全部已修，记录以免复发）

⚠⚠⚴⚠⚴ 这一轮仪器错了 **5 次**，其中 3 次会输出**看起来正常的错误结论**：

1. ⚠⚠⚴⚠⚴ **跑错页面**（§127.0）
   第一版探针跑 `9006/`（React 页），却要验用 `LAT_URL` 的 `verify_patch.mjs`
   ⇒ 整份结论作废，且作废前的输出**读起来完全合理**。
   ⇒ **判据脚本用哪个 URL 变量，决定了它验的是哪个页面；
   两个变量名不同、默认端口也不同（8 个脚本 8 个历史端口：
   10410 / 10330 / 10370 / 10462 / 10340 / 22234…）。**
   ⚠ 手册动作：**写探针时第一件事是把这个判据脚本的 URL 变量读出来**，
   并在探针开头**印出它实际访问的 `location.href`** 做自证。

2. ⚠⚠⚴⚠⚴ **四级转义 ⇒ 假绿**（`r127_patch_scope_probe.mjs` 第一版）
   在**模板字符串**里写 `/\\\\s+/g` ⇒ 页面侧拿到 `/\\s+/g`
   ⇒ 匹配的是**字面反斜杠**，空白**根本没被折叠**
   ⇒ 各行换行差异会**假装成**区分度 ⇒ 会报出「每行可见文字都不同」的**假绿**。
   ⇒ **修法**（已落地）：页面侧**不写正则**，改 `split/join`；
   并且**页面侧自报折叠是否生效**，**不过则本台当场作废**
   （`throw new Error('页面侧空白折叠自检失败 ⇒ 本台作废')`）。
   ⚠⚠ **「仪器自己给自己发绿」比「仪器报错」危险得多** ——
   报错至少会停下。

3. ⚠⚠⚴ `q.inVerdict` 拼错（正确是 `q.inGate`）
   ⇒ `undefined === 29` 为 false ⇒ 会把「**同一批元素**」误报成「不是」。
   ⚠ 被 `node --check` **抓不到**（语法合法），是**跑前自检**
   （`残留 inVerdict: 1`）抓到的。

4. ⚠⚴ `q.cells.indexOf(c)` 取行索引
   ⇒ 相同数组会取到**第一行** ⇒ 静默给错归属 ⇒ 改按行索引取 `rowKey[ri]`。

5. ⚠⚠⚴⚠⚴ **grep 抓到的不是引用，是散文**
   我用 `grep 'data/xxx\\.json'` 数静态页取用哪些产物 ⇒ 只抓到 **1 个**，
   且那个 `problem_index_24.json` 在 `index.html:1858-1863` 的**文档段**
   （讲 `build_problem_index_24.py` 的输入），**不是 fetch 引用**
   ⇒ 我据此推断的「死引用」**是错的**。
   ⚠ 真实机制：静态页用 `base + "xxx.json"` / `dataBase()` **拼接**
   ⇒ 字面量 grep **结构性测不到**。
   ⚠⚠ 这是「⚠⚠ 仪器读不到 ≠ 对象不存在」的**反向版本**：
   **仪器测到的东西，也可能不是它要找的那个。**

⇒ ⚠⚴⚠⚴ **固化**：
1. ⚠⚴ **探针第一件事：印 `location.href` 自证页面身份**，并**从被验脚本里读 URL 变量**。
2. ⚠⚴ **页面侧不许写正则**（转义层级数不可控）⇒ 用 `split/join`，
   并**让页面侧自报这个工具本身是否生效**。
3. ⚠⚴ **跑前自检要查「拼错的变量名」**：`node --check` 只管语法，不管名字。
4. ⚠⚠ **「数目一致」与「归属相同」是两件事** ⇒ 判归属要用归属谓词
   （`closest()`），不是数目。
5. ⚠⚠ **grep 到的字面量先问「这是引用还是散文」** —— 尤其是它出现在
   「输入文件 / 产物说明」这类文档段里的时候。

---

### 127.6 口径（本轮不变）

- ⚠ **K1（doctored 产物）/ K2（页面实例扰动）的分类不变**（§121），
  本轮**没有新增**任何 K1/K2 实验。
- ⚠ **静态页的 49 条判据仍属「未验牙齿」** ⇒ 本轮**不给**它们任何红绿结论。
- ⚠⚠⚴ **§122 的 `**` 结论限缩到 React 页**（§127.3）——
  这是**口径限缩**，不是**结论翻案**：G2/G3/G4 的修法（修订 123）依然成立，
  ⚠ 但「`**` 永不出现」这句话**不能**再被当成全站事实引用。
- ⚠⚠⚴ **§119 的「228 个调用点」按页重述**（§127.1）；
  ⚠⚴ 它**不是**「一个页面的判据总量」，任何以它为分母的百分比
  都必须**紧挨它自己的页归属**一起印。
"""


def main():
    assert os.path.exists(P), '预登记不存在'
    with open(P, 'rb') as f:
        before = f.read()
    assert before.endswith(b'\n'), '原文件不以 \\n 结尾，拒绝追加'
    n_before = before.count(b'\n')
    h_before = hashlib.sha256(before).hexdigest()

    with open(P, 'ab') as f:
        f.write(SECTION.encode('utf-8'))

    with open(P, 'rb') as f:
        after = f.read()
    assert after[:len(before)] == before, '原文前缀被改动 —— 违反「只追加」'
    h_after_prefix = hashlib.sha256(after[:len(before)]).hexdigest()
    assert h_before == h_after_prefix, '原文前缀哈希不一致'
    assert after.endswith(b'\n'), '追加后不以 \\n 结尾'
    assert after.decode('utf-8').count('\ufffd') == 0, '含 U+FFFD'

    print('✅ 已追加修订 127')
    print('   原文行数 %d → 全文 %d（+%d）' % (
        n_before, after.count(b'\n'), after.count(b'\n') - n_before))
    print('   原文字节 %d → 全文 %d（+%d）' % (
        len(before), len(after), len(after) - len(before)))
    print('   原文前缀 sha256 追加前后一致：%s' % h_before[:16])
    print('   U+FFFD = %d' % after.decode('utf-8').count('\ufffd'))


if __name__ == '__main__':
    main()
