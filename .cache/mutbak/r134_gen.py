#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r134_gen.py —— D 组 5 条交互判据的牙齿验证（四臂，由 R134_ARM 选）

⚠⚠⚴⚠ **注入点必须落在取值点上游**（修订 133 的结论）：
   判据自带的 `--mutate` 装在 `:257`，晚于所有判据的取值点，所以只能测辅助函数。
   本台把注入点放在 `const T = d.T;` 之后 ——
   ⚠ `d` 是 :96 捕获的一次性快照、`T` 是它的别名（:118），
   ⚠ A/B/C 全部只读这两个已定值 ⇒ 在 `const T = d.T;` 之后注入**不会污染它们**；
   ⚠ 而 D 组第一条在 :183 ⇒ **注入恰好赶在 D 组取值之前**。

⚠ 四臂各自拆掉一个 D 组依赖的**点击目标**（不碰任何判据代码）：

| 臂 | 拆什么 | 期望红 |
|---|---|---|
| `fork`  | 删 `[data-pathfork="1"]` | D1 |
| `all`   | 删 `[data-pathbtn="all"]` | D2 |
| `pair`  | 只留 `#selPair` 一个 option | D3/D4 **变成 SKIP**（不是红） |
| `xy`    | 删 `#tabXY` | D5 |

⚠⚠⚴ `pair` 臂特意选一个**期望「跳过」而不是「红」**的扰动：
   `verify_path.mjs:204` 的 `if (sw.skipped) skip('D3 …', '只有一道题，无从切')`
   ⇒ 拆掉多选题之后 D3/D4 应当**记为跳过、不进分母**（修订 118 的纪律）。
   ⚠ 这一臂验的是**跳过机制**，不是判据 —— 若它印 `RED` 或混进 N/M，说明跳过机制坏了。

⚠ 纪律：不改已提交的判据文件；注入块**不做任何判定**（结论由未改动的原判据给出）；
   写盘前用**逆变换逐行比对**断言「除注入块外与原文件相同」；
   每次扰动都要**回读确认真的拆掉了**。
"""
import difflib
import os
import sys
from pathlib import Path

SRC = Path('/Users/zhourui/code/steer3d/.cache/browser_verify/verify_path.mjs')
DST = Path('/Users/zhourui/code/steer3d/.cache/mutbak/r134b_path_dgroup.mjs')
CDP = '/Users/zhourui/code/steer3d/.cache/browser_verify/cdp_client.mjs'

# ⚠⚠⚴⚠⚠ **每条臂的注入点必须紧贴它自己那条判据的第一个动作之前。**
#   第一版用统一锚点 `const T = d.T;`（:118，在 D 组之前）：
#     `all` 臂实测「拆掉按钮却仍 36/36」。时间线取证证明页面**本来是对的**
#     （点按钮 6 → 28），⇒ **按钮被重新渲染回来了**：
#     ⚠⚠⚴ D1 在 :179 点分叉行 ⇒ **面板重渲染** ⇒ 按钮复活
#     ⇒ D2 到 :187 点击时它又在了 ⇒ **扰动被中途撤销**。
#   ⇒ 纪律不只是「注入点在取值点上游」，还要「**中间没有重渲染事件**」。
ANCHORS = {
    'fork': ("\nconst nCand = (await page.eval(", "\nconst nCand = (await page.eval("),
    'all':  ("\nconst rFork = await page.eval(", "\nconst rFork = await page.eval("),
    'pair': ("\nconst sw = JSON.parse(await page.eval(", "\nconst sw = JSON.parse(await page.eval("),
    'xy':   ("\nconst back = JSON.parse(await page.eval(", "\nconst back = JSON.parse(await page.eval("),
}

INJECT = r"""
// ===== r134b 注入：拆掉 D 组依赖的点击目标（按 R134_ARM 选臂） =====
// ⚠ 只改页面状态，不做任何判定 ⇒ 结论全部由下面未改动的原判据给出。
const __arm = (process.env.R134_ARM || 'fork').toLowerCase();
const __r134b = JSON.parse(await page.eval(`JSON.stringify((() => {
  const q = s => document.querySelector(s);
  const gone = {};
  if (__ARM__ === 'fork') { const e = q('[data-pathfork="1"]'); const before = !!e; if (e) e.remove(); gone.fork = { before, after: !!q('[data-pathfork="1"]') }; }
  else if (__ARM__ === 'all') { const e = q('[data-pathbtn="all"]'); const before = !!e; if (e) e.remove(); gone.all = { before, after: !!q('[data-pathbtn="all"]') }; }
  else if (__ARM__ === 'pair') {
    const sel = q('#selPair');
    // ⚠⚠⚴⚠ before **必须在删之前**读。第一版写在 while 之后 ⇒ 恒为 1
    //   ⇒ 落地核验永远判「未落地」，而**原因不是页面没拆掉，是我读错了时机**。
    // ⚠⚠⚴⚠⚠⚠ 顺带一条硬纪律：**注入块里不许出现反引号** ——
    //   整个注入块处在 page.eval 的**模板字面量**里，反引号会**提前终止模板**，
    //   ⇒ 语法错误。本轮为此踩了一次（本该写「before」却写成 `before`）。
    const before = sel ? sel.options.length : -1;
    if (sel) { while (sel.options.length > 1) sel.remove(1); sel.selectedIndex = 0; }
    gone.pairOpts = { before, after: sel ? sel.options.length : -1 };
  }
  else if (__ARM__ === 'xy') { const e = q('#tabXY'); const before = !!e; if (e) e.remove(); gone.xy = { before, after: !!q('#tabXY') }; }
  else return { bad: true, arm: __ARM__ };
  return { gone, arm: __ARM__ };
})())`));

// ⚠⚠⚴ **落地核验**：拆掉了必须**真的没了**（或真的只剩一个 option）。
//   拆不掉却继续跑 ⇒ 判据全绿会被读成「判据扛住了扰动」，正是修订 133 的病。
// ⚠⚗⚗⚗⚗⚠ 第一版写成 `gone.all = !q(...)` ⇒ **元素本来就不存在时也判「已落地」**
//   （`!null === true`）——**空落地**。本轮实测：`all` 臂印「已落地」却 RESULT OK 36/36，
//   就是因为 `[data-pathbtn="all"]` 在那一屏**根本不存在**，什么都没拆掉。
//   ⇒ 落地判据必须是「**拆之前确实存在**」且「**拆之后确实不存在**」，两半都要。
const __g = __r134b.gone || {};
const __k = Object.keys(__g)[0];
const __v = __g[__k] || {};
const __ok = !__r134b.bad && (
  (__v.before === true  && __v.after === false) ||        // 单元素臂：存在 → 消失
  (__v.before > 1 && __v.after === 1));                    // pair 臂：多个 → 只剩 1
if (!__ok) { console.log('[扰动未落地] ' + JSON.stringify(__r134b)); process.exit(2); }
console.log('[扰动已落地] 臂 ' + __arm + '：' + JSON.stringify(__r134b.gone));
"""


def main() -> int:
    src = SRC.read_text(encoding='utf-8')
    arm = (os.environ.get('R134_ARM') or 'fork').lower()
    if arm not in ANCHORS:
        print(f'[失败] 未知臂 {arm}；可选 {sorted(ANCHORS)}')
        return 2
    ANCHOR, _unused = ANCHORS[arm]
    # ⚠⚠⚴ HEAD **只能是换行符**：第一版把它设成与 ANCHOR 同样的语句文本
    #   ⇒ 语句被写了两遍，注入仍落在半截表达式后面 ⇒ SyntaxError。
    HEAD, TAIL = '\n', ''
    n = src.count(ANCHOR)
    if n != 1:
        print(f'[失败] 臂 {arm} 的锚点出现 {n} 次（要求 1）⇒ 判据文件结构变了，拒绝生成')
        return 2
    if "from './cdp_client.mjs'" not in src:
        print("[失败] 找不到 import './cdp_client.mjs' ⇒ 判据文件结构变了，拒绝生成")
        return 2
    if 'RESULT ${st}' not in src:
        print("[失败] 找不到汇总行 ⇒ 判据文件结构变了，拒绝生成")
        return 2
    # ⚠⚠⚴ 断言注入点真的落在「**取数之后、D 组取值之前**」
    # ⚠⚠⚴⚠ 第一版把不变式写成了 `C9 < const T < D1` —— **方向错了**：
    #   `const T = d.T` 在 C 组**之前**（C 组读的就是 `T` 和 `d`），
    #   守卫当场拦下。真正要保证的是：
    #     ① `d` 的快照已捕获（:96）—— 否则扰动会污染 A/B/C 的输入
    #     ② 注入点在 D 组第一条（:183）之前 —— 否则扰动赶不上 D 组
    # ⚠⚠⚴ 断言注入点落在**该臂那条判据自己的第一个动作之前**
    i_anchor = src.index(ANCHOR)
    # ⚠⚠⚴⚠ 必须带**行首缩进**去找：`check('D3 ` 在 `:32` 的**注释**里也出现过
    #   （「⚠ 原写法 `check('D3 …', true, '只有一道题，跳过')` 会把『没验』记成『验过了』」），
    #   只按子串 `src.index` 会命中注释那一处 ⇒ 位置算到文件开头 ⇒ 断言误判。
    #   ⇒ 前面带 `\n  ` 才能只命中真正执行的那条。⚠ 这是「grep 抓到注释」的又一例。
    # ⚠ D1/D2/D5 是**顶格**的；只有 D3/D4 在 `else {` 里带 2 空格缩进 ⇒ 两种都要。
    CRIT = {'fork': "\ncheck('D1 ", 'all': "\ncheck('D2 ",
            'pair': "\n  check('D3 ", 'xy': "\ncheck('D5 "}
    i_crit = src.index(CRIT[arm])
    if not i_anchor < i_crit:
        print(f'[失败] 臂 {arm}：注入点({i_anchor}) 不在该判据({i_crit})之前，拒绝生成')
        return 2

    patched = src.replace("from './cdp_client.mjs'", f"from '{CDP}'")
    # ⚠⚠⚴⚠ `__ARM__` 必须**插值**进 eval 串：`page.eval` 的代码在**浏览器**里跑，
    #   Node 侧的 `__arm` 变量它看不见。第一版直接写 `__arm` ⇒
    #   浏览器抛 `ReferenceError: __arm is not defined`，
    #   ⚠⚠⚴ 而错误发生在注入块里 ⇒ **扰动根本没落地**，
    #   ⚠⚠⚴ 若没有落地核验，这条会以「判据全绿」的形式被读成「判据扛住了扰动」。
    # ⚠⚠⚴⚠⚠ **注入块里一个反引号都不许有**：整个注入块处在 `page.eval(` 的
    #   **模板字面量**里，任何一个反引号都会**提前终止模板** ⇒ 后续全被当成
    #   普通代码 ⇒ `SyntaxError: missing ) after argument list`。
    #   ⚠ 本轮为此踩了两次（一次在词里、一次在「本该写成 X 却写成 X」的举例里）。
    #   ⇒ 生成器里**硬断言 + 自动替换**，不靠人眼。
    #   ⚠⚠⚴ **正确的判据不是「一个都没有」，而是「恰好 2 个」** ——
    #   那两个是模板字面量自己的开闭。第一版想「全部替换掉」，
    #   ⚠⚠⚴⚠ 结果连开闭一起换掉 ⇒ `page.eval(「」JSON…` ⇒ 语法错。

    # ⚠ 精确自修：**只清注释行**里的反引号（行首 strip 后以 // 开头），
    #   非注释行（模板字面量的开闭就在那里）**一个不动**。
    _fixed = []
    for _ln in INJECT.split('\n'):
        _fixed.append(_ln.replace('`', '「」') if _ln.strip().startswith('//') else _ln)
    INJECT_S = '\n'.join(_fixed)
    nb = INJECT_S.count('`')
    if nb != 2:
        print(f'[失败] 注入块里有 {nb} 个反引号（要求恰好 2 个：模板字面量的开闭）')
        print('       多出来的在注释里 ⇒ 模板会被提前终止 ⇒ 拒绝生成')
        return 2
    inj = INJECT_S.replace('__ARM__', '${JSON.stringify(__arm)}')
    # ⚠⚠⚴⚠ 注入必须落在**整条语句之前**，不能落在语句中间。
    #   锚点是 `…page.eval(` 这种**半截表达式**，第一版把注入接在它后面
    #   ⇒ `JSON.parse(await page.eval(` 后面跟了一个 `const __arm = …`
    #   ⇒ `node --check` 报 `SyntaxError: Unexpected token 'const'`（本轮实际发生）。
    #   ⇒ 正确做法：锚点自带的前导换行保留，注入插在它与语句之间。
    out = patched.replace(ANCHOR, HEAD + inj + ANCHOR[1:])
    back = out.replace(HEAD + inj + ANCHOR[1:], ANCHOR)
    if back != patched:
        print('[失败] 去掉注入块后与派生源不一致，拒绝写盘')
        for l in list(difflib.unified_diff(patched.splitlines(), back.splitlines(), lineterm=''))[:20]:
            print('   ' + l)
        return 2
    if out.count('\ufffd'):
        print('[失败] 含 U+FFFD，拒绝写盘')
        return 2

    DST.write_text(out, encoding='utf-8')
    print(f'[已生成] {DST}')
    print(f'  原 {len(src.splitlines())} 行 → 副本 {len(out.splitlines())} 行')
    print(f'  臂 = {arm} · 锚点唯一 ✓ · 注入点在该判据之前 ✓ · 除注入块外逐行相同 ✓')
    print(f'  锚点行号 ≈ {src[:i_anchor].count(chr(10)) + 1}；该判据行号 ≈ {src[:i_crit].count(chr(10)) + 1}')
    return 0


if __name__ == '__main__':
    sys.exit(main())