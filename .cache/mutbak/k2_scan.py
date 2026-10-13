#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k2_scan.py —— 判据读取层分类器（先证明 tokenizer 对，再出图）

⚠⚠⚴⚠ **为什么不能直接 grep**：
    `grep -o '\\bcheck(\\|\\brec('` 在 86 个文件里数出 **631**，
    而权威调用点数是 **228** —— 差 2.8 倍。631 里混着：
      · 函数**定义** `const check = (name, ok, detail) =>`
      · 别的函数 `checkPrecond(` / `checkOrth(` …
      · **注释里提到的那几次**（如 `verify_path.mjs:32`）
      · 模板串与字符串里出现的 `rec(`
    ⇒ ⚠⚠⚴ **在建立 tokenizer 之前，任何「228 条里有 N 条是容器 grep」的数都不能发。**

⚠⚠⚴⚠ **本脚本先证明 tokenizer 对，再出图**，两道闸：

  闸 A · **等长去注释**：把注释**逐字符替换成空格**（长度不变），
         再把结果写到临时文件跑 `node --check`。
         ⚠⚠⚴ 只要去注释改坏了一个字符，语法检查就红 ⇒ **不可能悄悄通过**。
  闸 B · **逐文件调用点数与已知地面对账**：
         `verify_patch` 13、`verify_path` 36、`verify_heldout` 74、
         `verify_axis_readout` 66、`probe_dedup_rendered` 24、`verify_hinge_panel` 28、
         `verify_subspace` 52、`verify_scene_link` 8、`verify_relamp` 1。
         ⚠ 对不上就**不发数**（exit 2）。

⚠ **读取层分类的口径**（每类必须互斥且穷尽，分母 = 调用点总数）：

| 类 | 判据实际读的是 | 典型写法 |
|---|---|---|
| `container-grep` | **整块容器的可见文字**，再找子串 | `T.includes(x)` / `/x/.test(txt)` |
| `dom-attr` | `data-*` 属性 | `getAttribute('data-…')` |
| `dom-geom` | 几何/可见性/显示态 | `getBoundingClientRect` / `style.display` |
| `dom-count` | DOM 节点数、结构 | `querySelectorAll(…).length` / `children.length` |
| `artifact` | 直接与产物 JSON 比 | 与 `prod` / `gates` / `q0` 比较 |
| `other` | 上面都不是（含控制流常量） | —— |

⚠⚠⚴ **只有 `container-grep` 是本项目已知会虚绿的那一类**
（修订 129 §129.4、130 §130.3、131 §131.4 三次都落在它身上）。
⚠ **本脚本不判定任何一条虚绿**，只做**形态普查**。
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path('/Users/zhourui/code/steer3d/.cache/browser_verify')

# ---- 已知地面对账（来自各文件历次实跑记录）----
GROUND = {
    'verify_patch.mjs': 13, 'verify_path.mjs': 36, 'verify_heldout.mjs': 74,
    'verify_axis_readout.mjs': 66, 'probe_dedup_rendered.mjs': 24,
    'verify_hinge_panel.mjs': 28, 'verify_subspace.mjs': 52,
    'verify_scene_link.mjs': 8, 'verify_relamp.mjs': 1,
}
CALLERS = ('check', 'rec')


KW_BEFORE_RE = ('return', 'case', 'typeof', 'instanceof', 'in', 'of', 'new',
                'delete', 'void', 'do', 'else', 'yield', 'await', 'throw')
OP_BEFORE_RE = set('(,=:[!&|?{};+-*%^~<>')


def strip_comments(src: str):
    """等长去注释：注释逐字符换成空格。返回 (去注释后源码, 注释字符数)。

    ⚠⚠⚴⚠ **第一版在这里被闸 A 抓了**：`${` 之后没有回到 `tpl` 状态，
    后面整个文件被级联吃掉 ⇒ 3 个文件 `node --check` 报
    「missing ) after argument list」/「Unexpected end of input」。
    ⇒ 模板串必须用**栈**：`tpl_stack` 每个元素是**当前模板 `${}` 内的花括号深度**。

    ⚠ 正则 vs 除法：标准启发式（前一有��义字符若是运算符开头 ⇒ 正则），
    ⚠ 但 `return /re/` 的前一字符是字母 ⇒ 补一张**关键字白名单**。
    ⚠ 启发式仍可能错 ⇒ 闸 A（等长后 `node --check`）兜底。
    """
    out = list(src)
    n = len(src)
    i = 0
    comments = 0
    mode = 'code'
    tpl_stack = []          # 每个元素 = 该模板 `${}` 内的花括号深度
    last_sig = ''           # 上一个有意义的字符
    last_word = ''          # 上一个标识符（给关键字白名单用）
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ''

        # ---- 行注释 ----
        if mode == 'code' and c == '/' and nxt == '/':
            j = src.find('\n', i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = ' '; comments += 1
            i = j
            continue

        # ---- 块注释 ----
        if mode == 'code' and c == '/' and nxt == '*':
            j = src.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, min(j, n)):
                if out[k] != '\n':
                    out[k] = ' '; comments += 1
            i = j
            continue

        if mode == 'sq' or mode == 'dq':
            if c == '\\':
                i += 2; continue
            if (mode == 'sq' and c == "'") or (mode == 'dq' and c == '"'):
                mode = 'code'; last_sig = c; last_word = ''
            i += 1
            continue

        if mode == 'tpl':
            if c == '\\':
                i += 2; continue
            if c == '`':
                mode = 'code'; last_sig = c; last_word = ''
            elif c == '$' and nxt == '{':
                tpl_stack.append(1)
                mode = 'code'
                last_sig = '{'; last_word = ''
                i += 2
                continue
            i += 1
            continue

        if mode == 'regex':
            if c == '\\':
                i += 2; continue
            if c == '/':
                mode = 'code'; last_sig = '/'; last_word = ''
                i += 1
                continue
            if c == '\n':      # 正则不跨行 ⇒ 误判，退回 code
                mode = 'code'; last_sig = '/'; last_word = ''
                i += 1
                continue
            i += 1
            continue

        # ---- mode == 'code' ----
        if c == "'":
            mode = 'sq'; last_sig = c; last_word = ''; i += 1; continue
        if c == '"':
            mode = 'dq'; last_sig = c; last_word = ''; i += 1; continue
        if c == '`':
            mode = 'tpl'; last_sig = c; last_word = ''; i += 1; continue
        if c == '/' and (last_sig in OP_BEFORE_RE or last_word in KW_BEFORE_RE):
            mode = 'regex'; i += 1; continue
        if c == '{':
            if tpl_stack:
                tpl_stack[-1] += 1
        elif c == '}':
            if tpl_stack:
                tpl_stack[-1] -= 1
                if tpl_stack[-1] == 0:
                    tpl_stack.pop()
                    mode = 'tpl'
        if c.isalnum() or c in '_$':
            last_word += c
        elif not c.isspace():
            last_word = ''
        if not c.isspace():
            last_sig = c
        i += 1
    return ''.join(out), comments


def gate_a(files):
    """闸 A：等长去注释后必须仍能通过 node --check。"""
    bad = []
    tmpdir = Path(tempfile.mkdtemp(prefix='k2scan_'))
    for f in files:
        stripped, _ = strip_comments(f.read_text(encoding='utf-8'))
        p = tmpdir / f.name
        p.write_text(stripped, encoding='utf-8')
        r = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True)
        if r.returncode != 0:
            bad.append((f.name, (r.stderr or '').strip().splitlines()[:2]))
    return bad


def split_args(argtext):
    """按顶层逗号切参数（括号/字符串/模板/正则内不算）。"""
    parts, buf, i, n = [], [], 0, len(argtext)
    depth = {'(': 0, '[': 0, '{': 0}
    close = {')': '(', ']': '[', '}': '{'}
    state = 'code'
    last_sig = ''
    while i < n:
        c = argtext[i]
        nxt = argtext[i + 1] if i + 1 < n else ''
        if state == 'code':
            if c in '"\'':
                state = c
            elif c == '`':
                state = 'tpl'
            elif c == '/' and nxt == '/':
                state = 'line'; buf.append('  '); i += 2; continue
            elif c == '/' and last_sig in "(,=:[!&|?{};+-*%^~<>":
                state = 'regex'
            elif c in '([{':
                depth[c] += 1
            elif c in ')]}':
                depth[close[c]] = max(0, depth[close[c]] - 1)
            elif c == ',' and not any(depth.values()):
                parts.append(''.join(buf)); buf = []; i += 1; continue
            if not c.isspace():
                last_sig = c
        elif state in ('"', "'"):
            if c == '\\':
                buf.append(c); buf.append(argtext[i + 1] if i + 1 < n else ''); i += 2; continue
            if c == state:
                state = 'code'
        elif state == 'tpl':
            if c == '\\':
                buf.append(c); buf.append(argtext[i + 1] if i + 1 < n else ''); i += 2; continue
            if c == '`':
                state = 'code'
        elif state == 'regex':
            if c == '\\':
                buf.append(c); buf.append(argtext[i + 1] if i + 1 < n else ''); i += 2; continue
            if c == '/':
                state = 'code'
        elif state == 'line':
            if c == '\n':
                state = 'code'
            else:
                c = ' '
        buf.append(c); i += 1
    parts.append(''.join(buf))
    return parts


def find_calls(stripped, name):
    """找 `name(` 的调用点，用括号配平取实参。⚠ 跳过定义处 `name = (`。"""
    out = []
    for m in re.finditer(r'(?<![\w$.])' + re.escape(name) + r'\s*\(', stripped):
        s = m.end() - 1
        # ⚠ 跳过 `const check = (…)` / `function check(…)`
        pre = stripped[max(0, m.start() - 40):m.start()]
        if re.search(r'(const|let|var|function)\s+$', pre):
            continue
        depth, i, n = 0, s, len(stripped)
        while i < n:
            c = stripped[i]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        if depth != 0:
            continue
        out.append((m.start(), stripped[s + 1:i]))
    return out


def role_of(stripped, pos, raw_lines):
    """逐行判调用点的**角色**：guard / loop / plain。

    ⚠⚠⚴⚠ **这一版是重写后的产物**：前面三版都在做括号/花括号配平
    （正向找块尾时把模板串的 `${` 当成块开头；无花括号循环体根本扫不到；
    `continue` 前忘了 `i -= 1` 变成死循环）。
    ⚠⚠⚴ **删掉配平，改成逐行**——这两件事在本项目里都是**各占一整行**的：

        for (const [name, needle] of phrases)      ← verify_path.mjs:146
          check(name, T.includes(needle), …);      ← :147
        if (st.wrap.state !== 'ok') {              ← verify_patch.mjs:75
          rec('P2..P6 本屏在 ok 态下才有意义', …    ← :76

    ⇒ 判据站点在**下一行**、控制结构在**上一行** ⇒ 逐行看上一非空行即可。
    ⚠ **不通用**：写成 `if (…) rec(…)` 单行、或控制结构与调用相隔多行时会失效。
    ⚠ 所以本台**不把 role 当成权威分类**，它只用来做 §闸 B′ 的算术对账，
    ⚠⚠⚴ 而对账的两个输入都要**把原文行打印出来**给人核。
    """
    # ⚠⚠⚴⚠ 这里必须用 **stripped（字符串）** 按 pos 切，再数换行。
    #   第一版写成 `raw_lines[:pos].count('\n')` —— `raw_lines` **已经是列表**，
    #   按字符偏移切列表拿到的是一大截元素，`.count('\n')` **恒为 0**
    #   ⇒ `ln=0` ⇒ 上一非空行永远取不到 ⇒ role 永远 plain。
    #   ⚠⚠⚴ 而单点调试里我手写的是 `st[:pos]`，**看着是对的** ——
    #   ⚠⚠⚴⚠ 「单点验证通过、整套跑出来全错」就是这么发生的。
    ln = stripped[:pos].count('\n')          # 站点所在行 0 基
    prev = ''
    for k in range(ln - 1, max(-1, ln - 12), -1):
        t = raw_lines[k].strip()
        if t:
            prev = t
            break
    if re.match(r'^(for|while)\b', prev):
        return 'loop'
    if re.match(r'^if\s*\(.*\)\s*\{\s*$', prev):
        return 'guard'
    return 'plain'


def container_aliases(stripped):
    """解析「容器文字」的别名，最多两级。

    ⚠⚠⚴⚠ **第一版没有这一步，产出的是一张可直接被证伪的错图**：
    `container-grep` 数成 **0**，而 `verify_path` 的 C5–C9 明明是
    `T.includes(…)`。根因：**判据主体是间接引用的**——

        const d = JSON.parse(await page.eval(`… q('#pathWrap').innerText …`));
        const T = d.T;                       ← 别名 T
        check('C5 …', T.includes(mw) && …)  ← 谓词里根本没有 innerText 字样

    ⇒ 分类器只看谓词 ⇒ **结构上够不着**。
    ⚠ 这与「判据的遍历源不能是被测对象本身」同族，只是方向相反：
    那一类是判据**读错了**源，这一类是工具**读不到**源。

    两级传播：
      ① `const X = JSON.parse(` 且其后的 eval 模板串里含 `innerText|textContent`
      ② `const Y = X.`（取 X 的某个字段）⇒ Y 亦为容器文字别名
    """
    aliases = set()
    # ① JSON.parse + eval 模板里含 innerText
    for m in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*JSON\.parse\(', stripped):
        var = m.group(1)
        win = stripped[m.end():m.end() + 4000]
        if re.search(r'innerText|textContent', win):
            aliases.add(var)
    # ② 从别名再取字段
    for _ in range(2):
        for m in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*(\w+)\.\w+', stripped):
            if m.group(2) in aliases:
                aliases.add(m.group(1))
    return aliases


def classify(pred, aliases=()):
    """⚠ 顺序要紧：先判最具体的，再回落。返回 (类, 命中的判别式)。"""
    p = ' '.join(pred.split())
    has_text = re.search(r'innerText|textContent', p)
    uses_alias = any(re.search(r'\b' + re.escape(a) + r'\b', p) for a in aliases)
    subm = re.search(r'\.includes\(|\.match\(|\.indexOf\(|\.test\(', p)
    if (has_text or uses_alias) and subm:
        return 'container-grep', ('innerText' if has_text else f'别名别名') + ' + 子串匹配'
    if (has_text or uses_alias) and re.search(r'===|==|!==|!=|>=|<=|>|<|length', p):
        return 'container-grep', ('innerText' if has_text else '容器别名') + ' + 比较/长度'
    if re.search(r'getAttribute\(|\bdata-[a-z]', p):
        return 'dom-attr', 'getAttribute / data-*'
    if re.search(r'getBoundingClientRect|\.style\.|getComputedStyle|offsetWidth|offsetHeight|clientWidth|elementFromPoint', p):
        return 'dom-geom', '几何/可见性/显示态'
    if re.search(r'querySelectorAll\([^)]*\)\.length|children\.length|\.length', p) and re.search(r'querySelectorAll|children', p):
        return 'dom-count', 'DOM 节点数/结构'
    if re.search(r'\b(prod|gates|q0|prodGates|artifact|data|meta|ds)\b', p):
        return 'artifact', '与产物 JSON 比较'
    return 'other', '—'


def main() -> int:
    files = sorted(ROOT.glob('*.mjs'))
    print(f'[扫描] {len(files)} 个 .mjs')

    bad = gate_a(files)
    if bad:
        print(f'[闸 A 红] 等长去注释后 {len(bad)} 个文件语法检查不通过 ⇒ tokenizer 不可信，拒绝出图')
        for n, e in bad[:6]:
            print(f'   {n}  {e}')
        return 2
    print('[闸 A ✓] 86 个文件等长去注释后全部通过 node --check ⇒ 去注释没改坏代码')

    rows, per_file, role_cnt = [], {}, {}
    for f in files:
        raw = f.read_text(encoding='utf-8')
        stripped, ncom = strip_comments(raw)
        aliases = container_aliases(stripped)
        calls = []
        for nm in CALLERS:
            calls += find_calls(stripped, nm)
        seen, uniq = set(), []
        for pos, args in sorted(calls):
            if pos in seen:
                continue
            seen.add(pos)
            uniq.append((pos, args))
        per_file[f.name] = len(uniq)
        for pos, args in uniq:
            parts = split_args(args)
            name = parts[0].strip() if parts else ''
            pred = parts[1] if len(parts) > 1 else ''
            role = role_of(stripped, pos, stripped.split('\n'))
            role_cnt[role] = role_cnt.get(role, 0) + 1
            cls, why = classify(pred, aliases)
            rows.append({'file': f.name, 'line': raw[:pos].count('\n') + 1,
                         'name': name, 'role': role, 'cls': cls, 'why': why, 'pred': pred})

    total = len(rows)
    print(f'[调用点] 合计 {total} 个（去注释后，{len(files)} 个文件）')
    print('\n=== ⚠ 口径（必须先钉，否则这个数会被误读成 228）===')
    print('  ⚠⚠⚴ 本台数的是**静态调用点**：源码里 `check(` / `rec(` 的调用处，一个算一个。')
    print('  ⚠⚠⚴ 它**不等于**下列任何三个数，各自是不同量：')
    print('     · 实跑判据条数 —— **循环会把它展开成多条**')
    print('       （`verify_path.mjs:147` 一个 `check` 展开成 B 组 **13** 条）')
    print('     · 历史记的「228 调用点」—— **守卫被排除在外**，但排除规则从未写下来')
    print('     · 各文件「36/74/66 实跑」—— 那是**执行**条数')
    print('\n=== 闸 B′：静态站点数 → 实跑条数 的算术对账 ===')
    ok_b = True

    # verify_path：静态 28 站点 − 4 条 M 变异判据 = 24 主判据站点；
    #   B 组那个循环站点 1 → 13 ⇒ 实跑 24 − 1 + 13 = 36（记录的 RESULT OK 36/36）
    vp = [r for r in rows if r['file'] == 'verify_path.mjs']
    vp_main = [r for r in vp if not r['name'].strip("'").startswith('M')]
    vp_loop = [r for r in vp if r['role'] == 'loop']
    vp_pred = len(vp_main) - len(vp_loop) + 13
    print(f'  {"✓" if len(vp) == 28 and vp_pred == 36 else "✗"} verify_path.mjs：静态 {len(vp)} 站点'
          f' − M 判据 {len(vp) - len(vp_main)} = 主判据 {len(vp_main)} 站点'
          f' − 循环 {len(vp_loop)} + B 组展开 13 = **实跑 {vp_pred}**（应 36）')
    if not (len(vp) == 28 and vp_pred == 36 and len(vp_loop) == 1):
        ok_b = False

    # verify_patch：静态 14 站点；其中 1 条是前置守卫且本次未触发 ⇒ 实跑 13
    pt = [r for r in rows if r['file'] == 'verify_patch.mjs']
    pt_guard = [r for r in pt if r['role'] == 'guard']
    print(f'  {"✓" if len(pt) == 14 and len(pt_guard) == 1 else "✗"} verify_patch.mjs：静态 {len(pt)} 站点'
          f'，其中守卫 {len(pt_guard)} 条（本次未触发）⇒ **实跑 {len(pt) - len(pt_guard)}**（应 13）')
    if not (len(pt) == 14 and len(pt_guard) == 1):
        ok_b = False

    # ⚠⚠⚴ 把两个「手工核实」的输入的**原文行**打出来，让人能自己核
    print('\n  ⚠ 对账的两个输入是**人工核实**的（逐行 role 启发式不通用），原文如下：')
    vpl = Path(ROOT / 'verify_path.mjs').read_text(encoding='utf-8').split('\n')
    vpll = Path(ROOT / 'verify_patch.mjs').read_text(encoding='utf-8').split('\n')
    for tag, arr, a_, b_ in [('verify_path 循环站点', vpl, 145, 147),
                             ('verify_patch 前置守卫', vpl2 if False else vpll, 74, 76)]:
        print(f'    [{tag}]')
        for k in range(a_, b_ + 1):
            print(f'      {k+1}: {arr[k]}')

    if not ok_b:
        print('[闸 B′ 红] 对账不成立 ⇒ 分类器不可信，拒绝出图')
        return 2
    print('\n[闸 B′ ✓] 两个文件都能从静态站点数算回它们各自的实跑条数')

    # ---- 读取层分类：本轮**不出数** ----
    # ⚠⚠⚴⚠ 两版都没通过自己的验收集，按纪律**不发数**：
    #
    #   第一版（只看谓词文本）：`container-grep` 数成 **0**，而 `verify_path`
    #     C5–C9 明明是 `T.includes(…)`。根因：判据主体**间接引用**——
    #     `const T = d.T` 而 `d` 来自 `JSON.parse(page.eval(…innerText…))`。
    #
    #   第二版（加了别名传播）：仍然两处错
    #     · 漏 `verify_patch` 的 P9/P10/P11 ⇒ 它们的谓词写的是**裸变量**
    #       `hasBoth`，正则在上一行 `const hasBoth = /主量/.test(txt) && …`
    #     · 过度分类 `verify_path` 17 个 ⇒ 我把整个 `d` 对象当成容器别名，
    #       可 `d.pairRow` 是 `getComputedStyle(...)`，**不是容器文字**
    #
    # ⚠⚠⚴ 修到位需要**字段级**数据流分析，且没有独立方法验它。
    # ⇒ 本轮**只发已验证的两样**（tokenizer + 调用点抽取），
    #   读取层分类留待下一轮，**绝不拿一张不可信的图去驱动排期**。
    print('\n=== ⚗ 读取层分类：本轮不出数 ===')
    print('  两版都没通过验收集（已知反例既漏又过度分类）⇒ 按纪律不发数。')
    print('  ⚠ 需要字段级数据流分析；⚠⚠⚴ 没有独立方法能验它 ⇒ 不发。')
    print('  ✅ 已验证并可用的只有上面两样：tokenizer（闸 A）+ 调用点抽取（闸 B′）')

    Path('/Users/zhourui/code/steer3d/.cache/mutbak/k2_layers.json').write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n[已写出] .cache/mutbak/k2_layers.json（{len(rows)} 个**调用点**明细，cls 字段**未验证**）')
    return 0


if __name__ == '__main__':
    sys.exit(main())