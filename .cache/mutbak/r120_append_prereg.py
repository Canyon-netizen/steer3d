#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 120 —— 8 个判据文件**首次全部拿到实跑口径**；两条判据被实跑证伪。

硬约束同前：预登记原文一字不改，只追加；追加后断言原文前缀逐字节未变。
"""
import hashlib
import io
import sys

P = '/Users/zhourui/code/steer3d/.cache/xcheck/R6_RERUN_PREREG.md'

BODY = r'''

---

## 修订 120 —— 8 个判据文件**首次全部拿到实跑口径**；⚗⚴⚴ 两条判据被实跑证伪

> 状态：**纯披露**。本节**未改任何判据文件、未改任何判红条件、未碰任何产物**。
> 本节唯一的动作是对 5 个**此前从未在活页面上跑过**的判据脚本跑首跑。
> ⚠ 实跑通道 = 隔离农场 **9006**（`.next-rev81`，HTTP 200），
> ⚠ **9005 已死**（HTTP 000）、8995–9004 全失联。

### 120.1 实跑总表（8/8 都有实跑证据了）

| 文件 | 实跑 | 静态调用点 | 证据来源 |
|---|---|---|---|
| `verify_subspace.mjs` | **52/52** | 39 | 修订 114 取数笔 |
| `verify_hinge_panel.mjs` | **28/28** | 28 | 修订 118 |
| `verify_path.mjs` | **36/36** | 28 | 修订 118 |
| `verify_heldout.mjs` | ⚗ **71/74** | 47 | ✅ **本轮首跑** |
| `verify_axis_readout.mjs` | ✅ **66/66** | 46 | ✅ **本轮首跑** |
| `probe_dedup_rendered.mjs` | ✅ **24/24** | 11 | ✅ **本轮首跑** |
| `verify_relamp.mjs` | ⚗ **0/1** | 8 | ✅ **本轮首跑** |
| `verify_scene_link.mjs` | ⚗ **6/8** | 21 | ✅ **本轮首跑** |

⇒ 修订 119 §119.5 那句「**展开口径本轮无法判定**」**到此作废**：
228 个静态调用点全部有了对应的实跑口径。

### 120.2 ⚗⚴⚴ 更正修订 119 的两个数（**我错了两处**）

1. ⚗⚴ **`verify_axis_readout` 展开 = 66，子智能体是对的，我错怪了它。**
   修订 119 §119.1 写「它报 66，本机 AST 算 82，⇒ 它的汇总数不采信」——
   **实跑 66/66，AST 的 82 是错的**。
   ⚠ 差 16 = `A2b ×4` + `B1-missing ×12` 这两条**正常路径上一次都不跑**的兜底分支，
   AST 把它们算进了分母。
   ⚠⇒ 修订 119 §119.1 那句「子智能体给的汇总数不采信」**一并作废**；
   它的**逐条分类**是对的（见 §119.2），错的只有「if/else 互斥」那条展开启发式。
2. ⚗⚴ **`verify_heldout` 展开 = 74，不是我写的 75。**
   差的那 1 条是 `:698` 的 `装置` 兜底（只在抛异常时才跑）。
   39（循环外且非兜底）+ 6（transfer）+ 30（rows）= **74**。

⚠⚠ **两处都栽在同一条规则上**：**把「缺失才走」的兜底分支算进分母**。
⇒ 这是「恒绿不是绿，是量不到东西」在**分母侧**的变体，
也是本轮第 4 次栽在「独立复算的实现上」。

### 120.3 ⚗⚴⚴ `verify_heldout` 三条红的根因：`**` 星号未渲染

首跑 **71/74**，红的是 **G2 / G3 / G4**，三条全部指向同一段文字（`[data-heldout-not-claimed]`）：

| 判据 | 要求（正则） | 页面实际印的 | 差在哪 |
|---|---|---|---|
| G2 | `从 12 抬到 **14**` | `下界因此从 12 抬到 14` | **少 `**`**，数字对 |
| G3 | `**14**（20 个候选、\|cos\|<0.5）` | 抓不到 | **少 `**`** |
| G4 | `门槛 0.45 就退回 **11** 条` | `门槛 0.45 就退回 11 条` | **少 `**`**，数字对 |

⚠ G4 那条尤其说明问题：产物现算是 `perm_min=11 / greedy=12`，
页面印的**正是 11**，而且 `同一 perm_min 口径` 与 `两个估计量不是一回事` 都在
⇒ **数值层面全对，只是少了星号**。

✅✅ **内建对照（本次最强的证据）**：**G5 PASS**。
G5 的两条正则 `greedy 估法给 12` / `不是一回事` **不要求 `**`**，
它读的是**同一段文字**、**同一批数字** ⇒ 红绿之差**只有「要不要星号」这一个变量**。

⚠⚴ 这把 §119.3-1 那条待拍板项（「markdown 渲染规则 A/B」）**顶到了最前面**：
G2/G3/G4 是**已经判红的三条**，它们站在「`**` 应当被渲染掉、页面不该出现星号」那一侧；
而 §112 定的既成 markdown 子集恰好是 `**` ⇒ 若产品补上 `<Em>`，这三条同时转绿。
⇒ **A/B 未拍板 ⇒ 这三条红的处置无法决定。**

⚠ 附带定位：`HeldoutPanel` 的边界声明**也没有**包 `<Em>`，
与已知的 `SubspacePanel.tsx:349` 裸 `{d.not_claimed}` **同族、不同文件**。

### 120.4 ⚗⚠⚴ 两条判据被**实跑证伪**（不是推断，是当场测到的）

1. ⚗⚠⚴⚴ **`verify_scene_link.mjs:252` 的 J11c 在它自称要抓的病上是绿的。**
   - J11c 的主体断言 `attrsPresent` 只判 `getAttribute(...) !== null`（`:249-251`）。
   - 而 `Scene3DFallback.tsx:269-270` 在算不出范围时**主动写空串**：
     `data-extent-maxabs = ext ? … : ""`、`data-extent-fraction = frac == null ? "" : …`。
   - ⚠⚴ **本次实跑证据**：`data-extent-maxabs="" data-extent-fraction=""
     data-has-entropy="false" data-layer="14"` —— 三个属性分别是无值 / 无值 / false，
     **J11c 照样 PASS**。而 J11c 的注释原文就是「null = 绘制循环半途而废」。
     ⇒ **它要抓的形态是空串，而它只判 `!== null` ⇒ 恒绿。**
   - ⚠ 另：四个属性里的 `data-layer` 是 `Scene3DFallback.tsx:116` 的
     **默认值 14**，无帧时恒为 14 ⇒ 它也不是「循环跑过」的证据。
   - ✅ 修法现成（**本节不改**）：`!== null` 收紧为
     「非空串且 `Number.isFinite(Number(v))`」；`data-has-entropy` 限 `'true'/'false'`。
2. ⚗⚠⚴ **`verify_relamp.mjs` 打出两个 RESULT 行，分母互相矛盾。**
   - `:61` **硬编码** `console.log('\nRESULT FAIL  1/6')`
   - `:122` 又按 `results.length` 印 `RESULT FAIL  0/1`
   - 本次实跑两行都出现了：`RESULT FAIL 1/6` 与 `RESULT FAIL 0/1`。
   - ⚠⚠ **更要紧的**：R1 红 ⇒ 走 `else` 之前的 `return` 不存在，
     `:62` 的 `else` 分支整块被跳过 ⇒ **R1b–R6 六条判据一条都没跑**，
     而报告形式上完全看不出来 ⇒ **这正是修订 118「跳过必须显式报」要治的病，
     而 `verify_relamp` 没有治**。

### 120.5 ⚠ 环境根因（两处红的**共同**来源，不是产品红）

9006 隔离农场**没有后端 WebSocket**：

- ⚠ `lib/store.ts:116` `steeringCalibration: null`（初值），
  `:143` 只由后端消息 `m.payload.calibration` 填充
  ⇒ `SteeringControl.tsx:245` 的门控 `calibrated && rmsPrev > 0` 永不成立
  ⇒ `[data-relamp]` **永不渲染** ⇒ **R1 红（环境红）**。
- ⚠ `Scene3DFallback.tsx:120` `framesRef.current = s.frames` 取自**同一个 store**
  ⇒ 无帧 ⇒ `painted=0` 个点、`trajectoryExtent([])` 为 null
  ⇒ **J11 / J11b 红（环境红）**。

⚠ 排查过程中**排除掉的一个可能**：`/layer_profiles.json` 在 9006 上
**HTTP 200、11284 字节**（农场与主仓 `public/` 都有），⇒ **不是文件缺失**。
⚠⚴ **判定依据必须写出来：「静态文件 200」与「后端推来活数据」是两回事**，
前者只排除了一种可能，不构成「数据到位」的证据。

⚠⚴ 一条**标签陷阱**：`data-painted="1"` 是 `Scene3DFallback.tsx:272` 写死的
「循环至少跑过」标志位，**不是点数**；真正的点数是 `data-rendered-points="0"`。
而 J11 的诊断行印的是 `painted=1` ⇒ 读者极易读成「画了 1 个点」。
⇒ **短值/同名字段当计数用时，判据与报告都必须紧挨口径。**

### 120.6 ✅ 正发现（但**不是**「可以放心了」）

- ✅ `verify_axis_readout` 与 `probe_dedup_rendered` **首跑即全绿**（66/66、24/24）。
- ✅ `verify_heldout` 71 条干净，且 3 红**全部归因到单一已知机制**。
- ⚠⚠ **「首跑即全绿」不等于判据有牙齿**：按修订 116 的纪律，
  **新基线必须扰动后才算验过**。
  ⇒ 三个新基线（`axis_readout` 66 条 / `dedup` 24 条 / `heldout` 71 条）
  **一条都还没做过扰动**，`probe_dedup` 的 `D4` 写死值（§119.3-3）与
  `axis_readout` 的 A9b 恒绿（§119.3-5）都还没被扰动台碰过。
  ⚠ 而 `r118_doctor_hinge.py` 这套「doctored 产物 + 逐字节还原」的手段**可直接复用**。

### 120.7 本节结论

1. ✅ 8/8 文件的实跑口径齐了；「展开数无法判定」作废。
2. ⚗⚴⚴ **更正修订 119 两处**：`axis_readout` 66（子智能体对、我错）、
   `heldout` 74（我写 75）。两处都因**把兜底分支算进分母**。
3. ⚗⚴⚴ `heldout` G2/G3/G4 三红 100% 因于 `**` 未渲染，**G5 是内建对照**；
   ⇒ **markdown 子集 A/B 的拍板优先级升到最高**。
4. ⚗⚠⚴ **两条判据已被实跑证伪**：J11c 空串放行、relamp 双 RESULT 分母矛盾。
5. ⚠ relamp / scene_link 的红**是环境红**（农场无后端），已用「文件 200 + store 初值 null」双向定位。
6. ⚠ 本节**未改任何判据文件**；修 J11c 与 relamp 记账须**先验功效、单独立修订**。
'''

def main():
    raw = io.open(P, encoding='utf-8').read()
    pre_len = len(raw)
    ends_nl = raw.endswith('\n')
    print('追加前：%d 字符 / %d 行 / U+FFFD=%d / 以\\n结尾=%s'
          % (pre_len, raw.count('\n'), raw.count('\ufffd'), ends_nl))
    assert raw.count('\ufffd') == 0, '追加前已有坏字，拒绝写入'
    assert '## 修订 120' not in raw, '修订 120 已存在，拒绝重复追加'

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