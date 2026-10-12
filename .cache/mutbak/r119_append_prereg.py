#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 119 —— 把 §119 追加到预登记。

⚠ 硬约束（沿用前几笔）：
   · **预登记原文一字不改**，只追加
   · 追加前断言文件以 \\n 结尾（本轮实测**否** ⇒ 追加内容自带前导换行）
   · 追加后断言**原文前缀逐字节未变**
   · 写完断言 U+FFFD == 0
"""
import hashlib
import io
import sys

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = r'''

---

## 修订 119 —— 判据覆盖图补全到 8/8 文件；⚗⚴⚴ 更正「231 个调用点」为 **228**

> 状态：**纯披露 + 口径更正**。本节**未改任何判红条件、未改任何判据文件**。
> 本节唯一的写入是把两个**只读计数脚本**入库。

### 119.0 ⚗⚴⚴ 先更正一个被连用多轮的数：231 → **228**

此前记录链：`229`（行首锚定 grep）→ 修订 117 更正为 `231`（+2）。
**今天实测：231 是错的，错了 3。**

三个口径逐层拆开（`r119_count_checks.py`，四道对照全 PASS）：

| 口径 | 命令 / 做法 | 合计 |
|---|---|---|
| A 行首锚定 | `grep -cE "^[ \t]*check\("` | **227** |
| B 不锚定 | `grep -c "\bcheck\("` | **230** |
| C 剥注释后不锚定 | 先剥块注释 + 行注释 | **228** ← **权威** |

⚠ 差值**逐条**解释掉（不是只报差值）：

- **A 比 C 少 1**：`verify_axis_readout.mjs:209`
  `if (cc.missing) { check(\`B1 ${ax}/L${L} 格子存在\`, false, 'missing'); continue; }`
  ⇒ 行首锚定**系统性偏向漏掉条件性分支**，与修订 117 的发现同源。
- **B 比 C 多 2**：两处都是**注释行**
  - `verify_hinge_panel.mjs:29`　`// ⚠ 原写法 \`check('…（跳过）', true, '')\` 会把…`
  - `verify_path.mjs:32`　　　　`// ⚠ 原写法 \`check('D3 …', true, …)\` 会把…`
  ⚠⚠ **这两行注释正是修订 118 自己加进去的** —— 判据文件里**批评某种写法**的注释，
  被同一条 grep 当成了那种写法。

⚗⚴ **病根复盘（这才是本节最该记的）**：
`229` 那个基础数**本身就不等于它自己那版的逐文件之和**
（39+8+21+30+25+47+46+11 = **227**，不是 229）。
⇒ 修订 117 的「+2」是**加在一个已经错的基数上**，所以修正后仍然错。
⇒ 这是「**分母带缺口时所有百分比的分子分母都不是同一口径**」的第三次重演。
⇒ ⚠ 因此**所有基于 231 的覆盖率百分比都要作废**，本节不给百分比。

✅ **两套独立方法交叉验证 228**：`r119_count_checks.py`（剥注释）与
`r119_expand.cjs`（acorn 真 AST，`frontend/node_modules/next/dist/compiled/acorn`）
**各自独立算出 228**。

### 119.1 覆盖图补全：8 个文件全部手读完

| 文件 | 静态调用点 | 手读状态 |
|---|---|---|
| `verify_subspace.mjs` | 39 | 修订 113–114 |
| `verify_relamp.mjs` | 8 | 修订 115 |
| `verify_scene_link.mjs` | 21 | 修订 115 |
| `verify_hinge_panel.mjs` | 28 | 修订 116 |
| `verify_path.mjs` | 28 | 修订 117 |
| `verify_heldout.mjs` | **47** | ✅ **本轮** |
| `verify_axis_readout.mjs` | **46** | ✅ **本轮**（子智能体 + 本机复核） |
| `probe_dedup_rendered.mjs` | **11** | ✅ **本轮** |
| **合计** | **228** | 8/8 |

⚠⚠⚴ **子智能体的展开数不可采信**：它报 `verify_axis_readout` 展开 **66**，
本机 AST 算出 **82**，手算 **82**；又报 `verify_relamp` 无 if/else 组却给 3。
⇒ 已按纪律**逐条核对它的每一条分类**（下面的分桶可信），但**它给的汇总数不采信**。
⚠ 它还把 `cos_per_axis` 说成「只有 creativity/reasoning 是 null」——
实际路径是 `axes[ax].specificity.cos_per_axis`，而它关于**路径**的结论是对的
（confidence/caution 各 4 键，另两个为 null）。

### 119.2 分桶总表（⚠ 每行紧挨它的口径；桶 = 「判定主体读哪一层」）

**`verify_heldout.mjs`（口径：静态 47 / 手算展开 75，未经实跑）**

| 桶 | 静态 | 展开 | 清单 |
|---|---|---|---|
| PAGE_TEXT | 34 | 53 | A3 B4 · B2×3 · C2/C3/C4/C5 各 ×6 · D2 D3 D4 · E1 E1b E2 · G1–G9 · I1 I2 I3 I4 I6 I7 I8 I9 · J0 |
| PAGE_ATTR | 9 | 14 | A1 A2 A4 · B3×3 · C1×6 · D1 · J0b |
| ARTIFACT | 3 | 3 | **B0** D5 **G0** |
| SOURCE | 1 | 1 | J1（读 `HeldoutPanel.tsx`） |
| RUNTIME/几何 | 4 | 4 | X0 · F1 · I5 · 装置兜底 |

**`verify_axis_readout.mjs`（口径：静态 46 / 手算展开 82，未经实跑）**

| 桶 | 静态 | 展开 | 清单 |
|---|---|---|---|
| PAGE_TEXT | 14 | 38 | A3/A4/A5 各 ×4 · B1×12 · C1 C2 C3b C3c C3d · D2 D3 D5 · D4-text×2 · D6×4 |
| PAGE_ATTR | 7 | 12 | A1 · A2×4 · A8 A9 · D1 · D4-cos×2 · D4-role×2 |
| ARTIFACT | 9 | 11 | E1 E2 E3 E4 E5 E8 A10 · E6×2 E7×2 |
| **SOURCE** | **0** | **0** | ⚠ **全文件零条源码级判据**（3 次 `readFileSync` 全是 JSON 产物） |
| RUNTIME | 1 | 1 | X0 |
| **兜底 / 恒绿** | 13 | **31** | A2b×4 · B1-missing×12 · C3a/b/c-miss · A9b · E5/E6/E8-miss · E7b×2 · E8-nos · 装置 |

⚠⚴ **31/82 = 38% 是「缺失才走」的兜底或无条件 `true`** ⇒ 真实有效判据 **51 条**，
其中读可见文字 **38 条**。

**`probe_dedup_rendered.mjs`（口径：静态 11 / 展开 23）**

| 桶 | 展开 | 说明 |
|---|---|---|
| RUNTIME（DOM 计数） | 14 | D1×8（全页 `pcnt`）+ D2 行数×1 + D2 五项×5 |
| PAGE_ATTR | 7 | D3 逐个比值 ×7 |
| PAGE_TEXT | 2 | D4 `innerText.includes(整句)` ×2 |
| SOURCE / ARTIFACT | 0 | — |

⚠✅ **作用域做法是对的**且已写进注释：D1 判「全页 0」（这条主张本就是全局的，
按子树判会**恒真**），D2/D3 判「子树 N」。**分作用域按主张配**，不是一刀切。

### 119.3 ⚗⚠ 本轮新发现的 7 处缺陷（**全部未改**，等拍板）

1. ⚗⚠⚴ **`verify_heldout.mjs:182` B0 的判据名强于它的断言**
   名字是「三个迁移目标都印在页面上」，主体断言是 `truth.transfer.length === 3`
   —— **一个字都没从页面读**。⇒ 「都印在页面上」这句话实际无人判：
   循环里读的是 ρ/地板/倍数**文字**（B2），**迁移目标的 key 名是否印在可见文字里，本文件无判据**。
   （对照：`verify_axis_readout.mjs:347` A9 就把 key 集合钉住了。）
2. ⚗⚠⚴ **`verify_heldout.mjs:324` E2 是该文件自己点名的弱断言，却没改**
   `:356-358` 的注释原文：「E2 就是 `includes('14')`/`includes('12')`，而 '12' 在这段
   文字里出现多次（12→14 的 12、0.45 退回的 12、20 个候选、0.5）⇒ 改对了仍会绿。」
   ⇒ **批评写在注释里，修法也在同文件（G2 的带词锚点正则），但 E2 没动。**
3. ⚗⚠ **`probe_dedup_rendered.mjs:186` 把 `0.7087` 写死**
   同文件 `:180-182` 刚批过「短值必然被邻近相同值喂饱」，
   而 `sub.control.delta['100']` **就在 `:176` 被读进来了**（实测 = `0.7087`，四位小数一致）
   ⇒ 产物改数时 D4 要么误红、要么和页面一起漂。
4. ⚗⚠ **`verify_axis_readout.mjs:345` A9 隐含一条注释没说的禁令**
   `:336` 注释只说「每个有 `cos_per_axis` 的轴，其键数就是它该有的列数」，
   实现却是 **key 集合双向相等** ⇒ 页面**不许出现** confidence/caution 之外的行。
   ⇒ 产品哪天把另两个轴的 `cos_per_axis` 补齐（**这是进步**），A9 反而判红。
5. ⚗⚠⚴ **`verify_axis_readout.mjs:355` A9b 是无条件 `true`** —— 判据名说
   「必须是已知的方向别名（否则是错名）」，但**永远不会红**。
   实测 `alias` 恒为 `['confidence','caution']`（`reasoning_deep` 不在 `AXES` 里），
   detail 每次都打同一句话。⇒ **它以判据的形状计入绿里，却不判任何东西。**
6. ⚗⚠ **`verify_axis_readout.mjs:165` `LABEL_OF` 与 `:176` A3 的 `need` 都是判据侧硬编码**
   而判据名 A4 写的是「与**产物**状态一致」；该文件 `:147-149` 刚批过
   「不要在判据里复制组件的映射表」。⇒ A4 自己就是那张表。
7. ⚗⚠ **三个文件的早退路径都印一个比完整分母小的数**
   （`probe_dedup_rendered` 印 `0/1`、`1/1`；`verify_heldout` 印 `0/N`）
   ⇒ 读者看到 `0/1` **无法区分**「只有 1 条判据」与「应有 23 条但只跑了 1 条」。
   ⚠ 与修订 118「跳过不进分母」同族，但**这里更隐蔽**：早退不是 `skip()`，看不出是异常。

### 119.4 ✅ 正发现（缺陷之外，必须一起记）

- ✅ **`verify_heldout.mjs` 的 G9 与修订 114 的 N1 是同一机制，但**不在同一面板**
  —— G9 核的是 `HeldoutPanel` 判决段里的「对 N 条命名轴」，N1 核的是 `SubspacePanel`
  的命名轴条数。⇒ **不是语义重复，是两块面板各自的覆盖**。
  ⚠ 「同形」≠「重复」：判重必须看**面板**，不能只看判据形状。
- ✅ **`J1`（`verify_heldout.mjs:649`）的注释记着它自己的两版前史**：
  v1 在 JSX 的 `{" "}` 处断掉、v2 漏了 `{2.05}×` / `{(2.05).toFixed(2)}×`
  —— **都是变异台 M-A 抓出来的**。⇒ 这份仓库里「判据的形状假设比产品的写法窄」
  是一个**已被实测证实过**的病，不是假想。
- ✅ **`F1`/`I5` 的裁切溢出检测（`rowOver`/`cellClip`/`spill`）是本仓唯一的
  「DOM 在 ≠ 看得见」几何机制**（`verify_path` 的 `__vp` 遮挡检查是另一个，两者不重叠）。
- ✅ `:382` 注释称 `completeness.json` 有「67 处裸 NaN」，实测 `grep -oE` = **67**，一致
  —— 注释与数据一致的一条正面证据。

### 119.5 ⚠⚠ 展开口径本轮**未取得可信值**（明确报「拿不到」，不填数）

我为「静态 → 展开」写了三个仪器，**全部失败或不可用**：

| 版本 | 做法 | 结果 |
|---|---|---|
| v1 | 逐字符 + 字符串状态机 | heldout 算出 **0**（`in_str` 被未闭合引号噎住） |
| v2 | 行级大括号配对 | heldout 算出 **47**（跨行模板字面量让行级配对全错位） |
| v3 | acorn 真 AST | heldout 校准 **PASS（75）**，但 `verify_relamp` 给 **3**（实跑 7）、`verify_subspace` 给 **54**（实跑 52）、`verify_path` 给 **37**（实跑 36） |

⚠ v3 的病根已定位：**「if/else = 互斥，每轮只计一条」这个规则对嵌套 if/else 不成立**
（`verify_subspace.mjs:534` 与 `:574`、`verify_path.mjs:240` 与 `:252` 两组共用同一批站点，
扁平分组把它们算重了）。
⚠⚴ 而 heldout 的「75」与 v3 的 75 一致**不算独立验证**——两者编码的是同一个互斥假设。

⇒ **本节只发布有实跑证据的展开数**：

| 文件 | 展开 | 证据 |
|---|---|---|
| `verify_subspace.mjs` | **52** | ✅ 实跑（修订 114 取数笔） |
| `verify_hinge_panel.mjs` | **28** | ✅ 实跑（修订 118，含 `[SKIP]` 分开记账） |
| `verify_path.mjs` | **36** | ✅ 实跑（修订 118） |
| `verify_heldout.mjs` | （75，手算） | ⚠ **无实跑**，且与 v3 同源假设 |
| `verify_relamp.mjs` / `verify_scene_link.mjs` / `verify_axis_readout.mjs` / `probe_dedup_rendered.mjs` | **本轮无法判定** | ⚠ 静态数可信（228），展开数无可信仪器 |

⚠ **判据自己也会报出展开数**：每个脚本 `RESULT n/m` 里的 `n` 就是它的实际条数
⇒ **最可靠的展开数来自实跑，不来自静态分析。**

### 119.6 本节新增入库脚本（只读，不改任何判据）

- `.cache/mutbak/r119_count_checks.py` —— 三个口径计数 + 四道阳性对照
  （剥注释仍留真调用点 / 剥注释削掉注释里的 `check(` / C 严格小于 B / C ≥ A）
- `.cache/mutbak/r119_expand.cjs` —— acorn 真 AST 的展开计算器
  ⚠ **已知不可用于发布展开数**（见 119.5），保留是因为它的**静态数 228**
  与 `r119_count_checks.py` **独立互证**，且嵌套归属可查。
- `.cache/mutbak/r119_expand.py` —— ⚠ **v2，已废弃**，保留在本地不提交
  （它在 heldout 上算错 47，是 119.5 那张表的一行证据）

### 119.7 修订 119 结论

1. ⚗⚴⚴ **「231 个调用点」作废，权威值 228**（两套独立方法互证，差值逐条解释）。
   ⚠ 由此作废一切基于 231 的百分比。
2. ✅ 覆盖图**补到 8/8 文件**，共 **228 个静态调用点**，每条都归入「判定主体读哪一层」。
3. ⚗⚠ **7 处新缺陷**已定位并写清证据，**全部未改**，等拍板（其中 §119.3-1/2/5
   是「判据名强于断言」「文件自陈的弱断言没修」「无条件 true 计入绿」三类，
   建议优先处理 2 与 5）。
4. ⚠⚠ **展开口径本轮报「无法判定」**：只有 3 个文件有实跑证据（52 / 28 / 36）。
5. ⚠ 本节**未改任何判红条件、未改任何判据文件、未碰任何产物**；
   作者未提交制品仍是 **15 条**，全程未动。
'''

def main():
    raw = io.open(P, encoding='utf-8').read()
    pre_len = len(raw)
    pre_sha = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    ends_nl = raw.endswith('\n')
    print('追加前：%d 字符 / %d 行 / U+FFFD=%d / 以\\n结尾=%s'
          % (pre_len, raw.count('\n'), raw.count('\ufffd'), ends_nl))
    print('追加前 sha256 = %s' % pre_sha[:32])

    assert raw.count('\ufffd') == 0, '追加前已有坏字，拒绝写入'
    assert '## 修订 119' not in raw, '修订 119 已存在，拒绝重复追加'

    # ⚠ 本文件不以 \n 结尾 ⇒ 追加内容自带前导换行，保证原文逐字节不变
    add = ('' if ends_nl else '\n') + BODY.lstrip('\n')
    if not add.endswith('\n'):
        add += '\n'
    assert '\ufffd' not in add, '追加内容含坏字'

    with io.open(P, 'a', encoding='utf-8', newline='') as f:
        f.write(add)

    after = io.open(P, encoding='utf-8').read()
    assert after[:pre_len] == raw, '⚠⚠ 原文前缀被改动，拒绝发布'
    assert len(after) == pre_len + len(add), '长度对不上'
    print('追加后：%d 字符 / %d 行 / U+FFFD=%d'
          % (len(after), after.count('\n'), after.count('\ufffd')))
    print('原文前缀逐字节未变 = True')
    print('新增 %d 字符' % (len(after) - pre_len))
    if not ends_nl:
        print('（本文件原本不以 \\n 结尾，追加时补了一个换行作为分隔）')
    return 0


if __name__ == '__main__':
    sys.exit(main())