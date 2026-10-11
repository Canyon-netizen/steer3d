#!/usr/bin/env node
/**
 * 修订 79 §79.3 的 Z4：**组件内可见文案**含 `**` 必须经 `<Em>` 渲染。
 *
 * ⚠⚠ 为什么必须用 TypeScript AST 而不是正则（§79.2 的侦察结论）：
 *   组件里含 `**` 的行，压倒性多数是**注释**
 *   （`InterventionOutcomePanel` 全文 32 行含 `**`，其中 124 行是注释行）。
 *   任何「逐行 grep `**`」的判据都会**全假红**，而全假红与恒绿同样无用。
 *   ⇒ 注释在 TS AST 里**根本不是节点**，从机制上就不可能被扫到。
 *   ⚠ 对照 4 与对照 5 是**排除对照**，守的就是这件事。
 *
 * 输出：JSON 到 stdout。判定与报告由调用方（python）做。
 * 用法：node .cache/xcheck/check_em_markdown.js <组件目录> [--selfcheck]
 */
'use strict';
const fs = require('fs');
const path = require('path');
const ts = require(path.join(__dirname, '..', '..', 'frontend', 'node_modules', 'typescript'));

/** §79.3 第 2 条的属性白名单排除：这些不是读者读到的文案。 */
const NON_PROSE_ATTRS = new Set(['className', 'style', 'key', 'id', 'ref']);

function isDataAttr(name) {
  return /^data-/.test(name) || /^aria-/.test(name);
}

/**
 * §79.3 第 3 条：折叠「常量字符串表达式」。
 * ⚠ 含插值的模板串（`${}`）**明确不判** —— 值要运行时才知道，
 *   这是写下来的覆盖缺口，返回 null 表示「不可静态求值」。
 */
function foldConst(node) {
  if (!node) return null;
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isParenthesizedExpression(node)) return foldConst(node.expression);
  if (ts.isAsExpression(node) || ts.isSatisfiesExpression(node) ||
      ts.isTypeAssertionExpression(node) || ts.isNonNullExpression(node)) {
    return foldConst(node.expression);
  }
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const l = foldConst(node.left), r = foldConst(node.right);
    if (l === null || r === null) return null;   // 有一侧不可求值 ⇒ 整体不可求值
    return l + r;
  }
  return null;
}

function scan(file) {
  const src = fs.readFileSync(file, 'utf8');
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.ES2020, true, ts.ScriptKind.TSX);
  const red = [];
  const counts = { n_jsx_text: 0, n_attr: 0, n_const: 0, n_files: 0 };

  // ---- 第 1 遍：谁被 <Em s={…}> 渲染了 ----
  const emNames = new Set();
  function scanEm(n) {
    // ⚠⚠⚠ 连续错了两版，才查了一次 AST 的真实结构：
    //   `JsxOpeningElement.attributes` **和** `JsxSelfClosingElement.attributes`
    //   **两者都是 `JsxAttributes` 节点对象**，数组都在 **`.properties`** 里。
    //   v1：`n.attributes || []` ⇒ 对象 truthy，`||` 不生效，
    //       对**对象**做 `for...of` ⇒ 崩（对照 3/4/5 全崩）。
    //   v2：以为「self-closing 是数组、opening 是节点」⇒ 仍崩，只是全崩。
    //   ⇒ 真值是**两边都要 `.properties`**。
    // ⚠⚠ 教训：**栈信息第一次就指明了行号**，那时该做的是查结构（10 秒），
    //   而我又改了一版碰运气 —— 在 AST 仪器现成的情况下选择了「猜」。
    //   ⚠ `|| []` 这种兜底最坏：它把「结构不同」伪装成「数据缺失」。
    if ((ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
        n.tagName && n.tagName.getText(sf) === 'Em') {
      for (const a of n.attributes.properties) {
        if (a.name && a.name.getText(sf) === 's' && a.initializer) {
          const id = a.initializer.expression;
          if (id && ts.isIdentifier(id)) emNames.add(id.text);
        }
      }
    }
    ts.forEachChild(n, scanEm);
  }
  scanEm(sf);

  // ---- 第 2 遍：可见文案三来源 ----
  //  ⚠ 先记下「被赋值给变量」的常量表达式及其变量名
  const constText = new Map();   // 变量名 -> 折叠后的文本
  function scanConsts(n) {
    if (ts.isVariableDeclaration(n) && n.initializer && n.name &&
        ts.isIdentifier(n.name)) {
      const txt = foldConst(n.initializer);
      if (txt !== null) {
        counts.n_const++;
        constText.set(n.name.text, txt);
      }
    }
    ts.forEachChild(n, scanConsts);
  }
  scanConsts(sf);

  function walk(n) {
    // (1) JSX 文字节点
    if (ts.isJsxText(n)) {
      const t = n.text;
      if (t.trim().length) {
        counts.n_jsx_text++;
        if (t.includes('**')) {
          red.push({ kind: 'jsx_text', line: sf.getLineAndCharacterOfPosition(n.pos).line + 1,
                     name: null, snippet: t.trim().slice(0, 90), via_em: false });
        }
      }
    }
    // (2) JSX 属性上的字符串字面量
    if (ts.isJsxAttribute(n) && n.initializer && n.name) {
      const nm = n.name.getText(sf);
      if (!NON_PROSE_ATTRS.has(nm) && !isDataAttr(nm) && ts.isStringLiteral(n.initializer)) {
        counts.n_attr++;
        if (n.initializer.text.includes('**')) {
          red.push({ kind: 'attr:' + nm,
                     line: sf.getLineAndCharacterOfPosition(n.pos).line + 1,
                     name: null, snippet: n.initializer.text.slice(0, 90), via_em: false });
        }
      }
    }
    ts.forEachChild(n, walk);
  }
  walk(sf);

  // (3) 常量文案：含 `**` 的分两堆 ——
  //     ⚠⚠ **判红与「已处理」必须在输出上分开**。
  //     v1 只把 `via_em` 当信息字段记下，却**照样 push 进 red**
  //     ⇒ 对照 3（常量含 `**` 且过了 <Em>）被判红，
  //     而真实组件里每一个经 <Em> 渲染的文案都会**满屏假红**。
  //     判据 §79.3 第 4 条写的是「经 <Em> 渲染 ⇒ **判绿**」，
  //     实现没实现它 ⇒ **改实现、不改判据**（判据是对的）。
  const covered = [];
  for (const [name, txt] of constText) {
    if (!txt.includes('**')) continue;
    if (emNames.has(name)) {
      covered.push({ kind: 'const', name, snippet: txt.slice(0, 90) });
      continue;
    }
    red.push({ kind: 'const', line: -1, name, snippet: txt.slice(0, 90), via_em: false });
  }

  // ---- 披露项：ObjectLiteral 的字符串值含 `**`（Z4 **不覆盖**）----
  // ⚠⚠ 判据 §79.3 第 2 条只收「被赋值给变量的字符串常量表达式」，
  //   而 `const STATE_TXT: Record<…> = { done: "有", … }` 是 **ObjectLiteral**，
  //   不是可折叠的常量表达式 ⇒ 它的值**落在 Z4 范围之外**。
  // ⚠ 之所以**量化**而不是默默漏掉：`n_const` 只有个位数（口径窄），
  //   而「窄」与「没覆盖到」必须分开说。
  // ⚠ 本项**不参与 exit code**，只报数：将来有人往 ObjectLiteral 里加带星号的
  //   文案时，这里的 N 会立刻从 0 变大 —— 缺口因此是**被钉住的**，不是看不见的。
  const gaps = [];
  function scanObjLit(n) {
    if (ts.isObjectLiteralExpression(n)) {
      for (const pr of n.properties) {
        if (!pr.name) continue;
        const key = pr.name.getText(sf).replace(/^["']|["']$/g, '');
        const val = foldConst(pr.initializer);
        if (val !== null && val.includes('**')) {
          gaps.push({ key, snippet: val.slice(0, 70) });
        }
      }
    }
    ts.forEachChild(n, scanObjLit);
  }
  scanObjLit(sf);

  counts.n_files = 1;
  return { red, covered, gaps, counts, emNames: [...emNames] };
}

function scanDir(dir) {
  let files;
  try {
    files = fs.readdirSync(dir).filter(f => f.endsWith('.tsx') || f.endsWith('.ts'));
  } catch (e) {
    return { error: `读不到组件目录 ${dir}: ${e.message}` };
  }
  const all = [], allCovered = [], allGaps = [];
  const totals = { n_jsx_text: 0, n_attr: 0, n_const: 0, n_objlit: 0, n_files: 0 };
  for (const f of files.sort()) {
    const r = scan(path.join(dir, f));
    totals.n_jsx_text += r.counts.n_jsx_text;
    totals.n_attr += r.counts.n_attr;
    totals.n_const += r.counts.n_const;
    totals.n_objlit += (r.gaps || []).length;
    totals.n_files += 1;
    for (const x of r.red) all.push({ file: f, ...x });
    for (const x of r.covered) allCovered.push({ file: f, ...x });
    for (const x of (r.gaps || [])) allGaps.push({ file: f, ...x });
  }
  return { red: all, covered: allCovered, gaps: allGaps, counts: totals, n_files: files.length };
}

// ---- 阳性对照（§79.4）----
const CHECKS = [
  { id: 1, file: 'c1.tsx',
    code: `export const A = () => <p>这是**裸文字**节点</p>;`,
    expectRed: 1, expectKind: 'jsx_text',
    why: 'JSX 文字节点裸含 `**` ⇒ 必须判红（分支 1 有牙齿）' },
  { id: 2, file: 'c2.tsx',
    code: `const S = "带**星号**的常量";\nexport const B = () => <p>{S}</p>;`,
    expectRed: 1, expectKind: 'const',
    why: '常量含 `**` 但没过 <Em> ⇒ 必须判红（未渲染判定有牙齿）' },
  { id: 3, file: 'c3.tsx',
    code: `const S = "带**星号**的常量";\nexport const C = () => <p><Em s={S} /></p>;`,
    expectRed: 0, expectKind: null, expectCovered: 1,
    why: '常量含 `**` 且过了 <Em> ⇒ 必须判绿（正向不误报）' },
  { id: 4, file: 'c4.tsx',
    code: `// ⚠⚠⚠ 注释里满是 **星号** **到处都有** **全是注释**\n/* 块注释也是 **星号** **一堆** */\nexport const D = () => <p>正文**真有**星号</p>;`,
    expectRed: 1, expectKind: 'jsx_text',
    why: '⚠ 排除对照（**与一条真判红配对**）：注释塞满 `**` 而正文只有一处 ⇒ 期望恰好 1 而不是 0。' +
         '第一版这里期望 0，而正文也不含 `**` ⇒ 判据整个崩掉时同样是 0，' +
         '**那条对照结构上是恒绿的，永远不会失败**' },
  { id: 5, file: 'c5.tsx',
    code: `export const E = () => <p className="text-[9px] **属性不是文案**" data-x="**也不是**">正文**真有**星号</p>;`,
    expectRed: 1, expectKind: 'jsx_text',
    why: '⚠ 排除对照（**与一条真判红配对**）：className/data-* 含 `**` 而正文只有一处 ⇒ 期望恰好 1。' +
         '否则「白名单失效」与「白名单过宽」两种故障都会给出 0，测不出区别' },
  { id: 6, file: 'c6.tsx',
    code: `const MAP: Record<string, string> = { a: "对象里的**文案**", b: "没星号" };\nexport const F = () => <p>{MAP.a}</p>;`,
    expectRed: 0, expectKind: null, expectGap: 1,
    why: '⚠ **披露项自身**的对照：ObjectLiteral 值含 `**` 属**已知缺口**（Z4 不覆盖），' +
         '披露项必须报出 1。⚠ 若没有它，「缺口 0 处」与「披露项坏了」分不开 —— ' +
         '这正是「报 0 的探针必须先证明它能报非零」' },
];

function selfcheck() {
  const tmp = path.join(__dirname, '..', 'mutbak', 'emctl');
  const out = { n_ok: 0, n_total: CHECKS.length, details: [] };
  for (const c of CHECKS) {
    let r;
    try {
      fs.mkdirSync(tmp, { recursive: true });
      fs.writeFileSync(path.join(tmp, c.file), c.code, 'utf8');
      r = scanDir(tmp);
    } catch (e) {
      out.details.push({ id: c.id, ok: false, crashed: true,
                         note: `⚠ 这是**对照没跑**，不是「对照失败」：${e.message}` });
      continue;
    }
    if (r.error) {
      out.details.push({ id: c.id, ok: false, crashed: true,
                         note: `⚠ 这是**对照没跑**：${r.error}` });
      continue;
    }
    // ⚠⚠ 只把**当前这一条对照**的文件算进来 ——
    //   目录里残留别的对照文件时，不该把它们算进本条。
    const mine = r.red.filter(x => x.file === c.file);
    const mineCov = (r.covered || []).filter(x => x.file === c.file);
    const n = mine.length;
    const kindOk = c.expectKind === null ? true : mine.some(x => x.kind === c.expectKind);
    // ⚠⚠ `expectRed: 0` 单独看不够 —— 「压根没扫到」也是 0。
    //   ⇒ 期望判绿的那几条必须同时断言 `covered` 收到了它。
    const covOk = c.expectCovered === undefined
      ? true : mineCov.length === c.expectCovered;
    // ⚠ 披露项自身的对照：期望披露 N 处就必须真的披露 N 处，
    //   否则「缺口 0」与「披露项坏了」在输出上完全一样。
    const gapOk = c.expectGap === undefined
      ? true : (r.gaps || []).filter(x => x.file === c.file).length === c.expectGap;
    const ok = (n === c.expectRed) && kindOk && covOk && gapOk;
    if (ok) out.n_ok++;
    out.details.push({ id: c.id, ok, expect: c.expectRed, got: n,
                       covered: mineCov.length,
                       gap: (r.gaps || []).filter(x => x.file === c.file).length,
                       kinds: mine.map(x => `${x.kind}@${x.line}`), why: c.why });
  }
  return out;
}

const argDir = process.argv[2];
const doSelf = process.argv.includes('--selfcheck');
if (doSelf) {
  process.stdout.write(JSON.stringify(selfcheck(), null, 2));
} else if (!argDir) {
  process.stdout.write(JSON.stringify({ error: '用法: node check_em_markdown.js <组件目录> [--selfcheck]' }));
} else {
  process.stdout.write(JSON.stringify(scanDir(path.resolve(argDir)), null, 2));
}
