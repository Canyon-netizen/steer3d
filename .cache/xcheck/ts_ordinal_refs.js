#!/usr/bin/env node
/**
 * 修订 82 §82.4 的 K1 前半：**找出所有「被序数指称的 Record 表」并解析出它的路径**。
 *
 * ⚠⚠ 为什么必须用 TypeScript AST 而不是正则（§82.1 的侦察结论）：
 *   `ArchivedExperiments.tsx:147` 与 `AxisReadoutPanel.tsx:88` 证明
 *   —— 源码里**注释块里**也写着 `Object.keys(...)`，逐行 grep 会把它们算成遍历点。
 *   ⚠ 而 JSX 注释（花括号里包着的星号注释）在 TS AST 里是
 *   `JsxExpression(expression=undefined)`，
 *   **它的文本不在任何 JsxText 节点里** ⇒ 重建可见文本流时**结构上**扫不到。
 *   （已实测确认，见 §82.4「被序数指称的认法」。）
 *
 * ⚠ 为什么必须**重建**文本流而不是逐个 JsxText 节点匹配：
 *   `第 {opIdx >= 0 ? opIdx + 1 : "?"} 档` 在 AST 里是
 *   JsxText("…第 ") + JsxExpr(...) + JsxText(" 档…") —— 「第」与「档」**分属两个节点**。
 *
 * ⚠ 解析不出来就**报 unresolved**（不静默跳过）—— §82.4：样本不足报「无法判定」。
 *
 * 输出：JSON 到 stdout。判定与报告由调用方（python）做。
 * 用法：node .cache/xcheck/ts_ordinal_refs.js <组件目录>
 */
'use strict';
const fs = require('fs');
const path = require('path');
const ts = require(path.join(__dirname, '..', '..', 'frontend', 'node_modules', 'typescript'));

/**
 * §82.4 的样式（**这一行本身在 §82.8 被更正过**，旧版是 `\{([^{}]*)\}` 单个容器）：
 * 序数指称 = `第` + **一串**表达式容器 + 量词。
 *
 * ⚠⚠⚴ **更正的理由是实测的盲区，不是推测**（§82.8 失误 3）：
 *   `SubspacePanel.tsx:205` 的真实文本是
 *       第 {opIdx >= 0 ? opIdx + 1 : "?"}{" "}
 *       档 |cos| &lt; …
 *   `第` 与 `档` 之间有**两个**表达式容器 —— 第二个 `{" "}` 是 JSX 空格 hack
 *   （渲染出来就是一个空格，读者看到的正是「第 4 档」）。
 *   ⚠ 旧正则只允许**一个**容器 ⇒ **恰好漏掉 K1 的目标那处**，
 *   同时把 `Scene3D.tsx` 的 4 处「第 {focusedStep} 步」报成「全站仅有的序数指称」。
 *   ⚠ 这是「静默给出错误答案」的一种新骗法：不是空，是**看起来很合理**的另一个答案。
 *   ⇒ 容器数必须写成 `(?:\{[^{}]*\}\s*)+`（一串），而不是恰好一个。
 */
const ORDINAL = /第\s*((?:\{[^{}]*\}\s*)+)(档|个|条|步|层)/g;

function propName(n) {
  if (ts.isIdentifier(n)) return n.text;
  if (ts.isStringLiteral(n) || ts.isNumericLiteral(n)) return n.text;
  return null;
}

/** `a.b[0].c` → ['a','b','0','c']；含调用/条件 ⇒ null（不可静态还原）
 *  ⚠⚠ **必须处理 ElementAccess 的数字字面量下标**（§82.8 失误 1）：
 *   不处理时 `...Object.keys(x.batches[0].per_token)` 被漏计，而**上一版正则漏计的
 *   也是同一处、也是同一种下标** ⇒ 两把尺子在同一盲点上错，差值恰好互相抵消不了。
 *   非字面量下标（`x[k]`）仍不可静态还原 ⇒ 返回 null。 */
function pathOf(n) {
  if (ts.isPropertyAccessExpression(n)) {
    const p = propName(n.name);
    if (p === null) return null;
    const base = pathOf(n.expression);
    return base === null ? null : [...base, p];
  }
  if (ts.isElementAccessExpression(n)) {
    const arg = n.argumentExpression;
    if (!arg || !ts.isNumericLiteral(arg)) return null;
    const base = pathOf(n.expression);
    return base === null ? null : [...base, String(arg.text)];
  }
  if (ts.isIdentifier(n)) return [n.text];
  return null;
}

/** ⚠ 只要调用形状对就算一个 `Object.keys/entries` 调用点 ——
 *  **不**要求参数路径可解析。**计数与解析是两件事**（§82.8 失误 2）。 */
function isObjectCall(n) {
  if (!ts.isCallExpression(n)) return false;
  const callee = n.expression;
  if (!ts.isPropertyAccessExpression(callee)) return false;
  if (propName(callee.expression) !== 'Object') return false;
  const meth = propName(callee.name);
  return (meth === 'keys' || meth === 'entries') && n.arguments.length === 1;
}

/** 再加上「参数能静态还原成路径」 */
function objectCallOf(n) {
  if (!isObjectCall(n)) return null;
  const arg = pathOf(n.arguments[0]);
  return arg === null ? null : { method: propName(n.expression.name), table_path: arg };
}

/** 把一棵 JSX 子树重建成「读者看到的文本流」：表达式容器塌成 {…}
 *  ⚠ 每段同时记下它在**源文件里的绝对偏移**，这样匹配位置才能换算成真实行号 ——
 *  否则嵌套 JSX 元素（外层容器也包含同一段文本）会把同一处**重复计数**（§82.8 失误 5）。 */
/** 子树里有没有 JSX 节点 */
function containsJsx(n) {
  let found = false;
  const w = (x) => {
    if (found) return;
    if (ts.isJsxElement(x) || ts.isJsxFragment(x) || ts.isJsxSelfClosingElement(x)) { found = true; return; }
    ts.forEachChild(x, w);
  };
  w(n);
  return found;
}

function visibleStream(node, out, sf, base) {
  // ⚠⚠⚴ **属性整体跳过**（§82.8 失误 8）：属性不是读者看到的文案，
  //   而且属性里的标识符能和相邻文本**拼出一条根本不存在的句子**。
  if (ts.isJsxAttribute(node)) return base;
  if (ts.isJsxText(node)) {
    out.push({ kind: 'text', text: node.text, srcStart: node.getStart(sf), srcBase: base });
    base += node.text.length;
    return base;
  }
  if (ts.isJsxExpression(node)) {
    // ⚠ 注释块走这里：expression 为 undefined ⇒ 记成 {JSX_COMMENT}，
    //   它的内容**不在** node.getText() 里（已实测）⇒ 永远不会进正则。
    if (node.expression && containsJsx(node.expression)) {
      // ⚠⚠⚴ **表达式里含 JSX 时绝不能拿 `getText()` 当一段文字**（§82.8 失误 9）：
      //   `getText()` 会把内嵌 JSX 的**源码**整段吞进来。实测 `Scene3D.tsx`：
      //     {focusedStep != null && … && (
      //       <span …>{" "}· 第 {focusedStep} 步不在 3D 窗口内</span>)}
      //   它的 getText() 里含 `第 {focusedStep} 步` ⇒ 正则命中**内层那句真话**，
      //   位置却被记成**外层表达式**的行（186，真句在 189）⇒ 凭空多报一处。
      //   ⇒ 把外层当容器**递归进去**，让内层自己的 JsxText 出声。
      //   （条件本身不是可见文案，丢掉它不影响「读者看到什么」。）
      ts.forEachChild(node.expression, c => { base = visibleStream(c, out, sf, base); });
      return base;
    }
    const body = node.expression ? node.expression.getText() : '{JSX_COMMENT}';
    out.push({ kind: 'expr', text: body, srcStart: node.getStart(sf), srcBase: base });
    base += body.length + 2;
    return base;
  }
  ts.forEachChild(node, c => { base = visibleStream(c, out, sf, base); });
  return base;
}

/** 一个文件里所有 `const/let X = <init>` 的顶层声明（含函数体内） */
function collectDecls(sf) {
  const decls = new Map();
  const visit = (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer) {
      if (!decls.has(n.name.text)) decls.set(n.name.text, []);
      decls.get(n.name.text).push(n);
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return decls;
}

/** 该标识符的某次声明的初始化式里，根调用是不是 Object.keys/entries */
function objectCallViaDecl(decl, decls, seen) {
  if (seen.has(decl.name.text)) return null;
  seen.add(decl.name.text);
  const init = decl.initializer;
  const direct = objectCallOf(init);
  if (direct) return { ...direct, via: decl.name.text, init_src: init.getText() };
  // `Object.keys(X).findIndex(...)` / `Object.keys(X).length` 等：根仍是它
  let root = init;
  while (root && (ts.isPropertyAccessExpression(root) || ts.isCallExpression(root))) {
    if (ts.isCallExpression(root)) { root = root.expression; continue; }
    if (ts.isPropertyAccessExpression(root) && ts.isCallExpression(root.expression)) {
      root = root.expression;
      continue;
    }
    root = root.expression;
  }
  if (root) {
    const viaRoot = objectCallOf(root);
    if (viaRoot) return { ...viaRoot, via: decl.name.text, init_src: init.getText() };
  }
  // 或者：`const L = Object.keys(X).length` 之类再引用一次
  const t = ts.forEachChild;
  let found = null;
  const inner = (n) => {
    if (found) return;
    const c = objectCallOf(n);
    if (c) { found = c; return; }
    if (ts.isIdentifier(n) && decls.has(n.text) && !seen.has(n.text)) {
      for (const d2 of decls.get(n.text)) {
        const r = objectCallViaDecl(d2, decls, seen);
        // ⚠ 原写成 `via: n.text`（被引用的名字），而初始化式属于 decl ⇒ 会把 via 指错
        if (r) { found = { ...r, via: decl.name.text }; return; }
      }
    }
    ts.forEachChild(n, inner);
  };
  ts.forEachChild(init, inner);
  // ⚠ 走到这里说明命中的是 init **内部**的某个 Object.keys/entries（典型：
  //   `const opIdx = Object.keys(T).findIndex(...)`）⇒ `via` 就是这个声明的名字。
  return found ? { ...found, via: decl.name.text, init_src: init.getText() } : null;
}

function lineOf(sf, node) { return sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1; }
function lineOfOffset(sf, off) { return sf.getLineAndCharacterOfPosition(off).line + 1; }

/** flat 下标 → 源文件绝对偏移。⚠ 落在表达式容器里的下标无法精确映射（容器已塌成 `{expr}`，
 *  而 expr 是 `getText()` 的结果、长度与源文本不同）⇒ 返回该容器的起点，足够去重。 */
function srcOffsetOf(segments, flat, idx) {
  let acc = 0;
  for (const s of segments) {
    const piece = (s.kind === 'text' ? s.text : '{' + s.text + '}');
    if (idx < acc + piece.length) {
      if (s.kind === 'text') return s.srcStart + (idx - acc);
      return s.srcStart;
    }
    acc += piece.length;
  }
  return -1;
}

function scanFile(file) {
  const src = fs.readFileSync(file, 'utf8');
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const decls = collectDecls(sf);

  // ---- 普查：Object.keys/entries 的调用点数（注释里不算，AST 机制保证） ----
  let nObjectCalls = 0;
  const walkCalls = (n) => {
    // ⚠ 用 `isObjectCall` 而不是 `objectCallOf`：后者还要求参数路径可解析，
    //   会把 `Object.keys(x.batches[0].per_token)` 这类**下标路径**漏掉
    //   ⇒ 分母会被少报，而「少报的分母」会让读者以为已经扫全了（§82.8 失误 2）。
    if (isObjectCall(n)) nObjectCalls += 1;
    ts.forEachChild(n, walkCalls);
  };
  walkCalls(sf);

  // ---- fetch 的产物 + setState 别名 ----
  const fetches = [];
  const stateNames = new Set();
  // ⚠⚠⚴ setState 目标名 → 状态变量名，**不能**靠 `setX.slice(3)` 猜（§82.8 失误 7）：
  //   真实代码是 `const [d, setD] = useState(...)` ⇒ setter 叫 `setD`、值叫 **`d`**（小写），
  //   `slice(3)` 得到 `"D"` ⇒ 永远匹配不上 ⇒ 成员别名（`const h = d.headline`）解析不出来。
  //   ⇒ 必须读 `useState` 的**解构模式**取第 0 个绑定名，那才是权威来源。
  const setterToValue = new Map();
  const walkFetch = (n) => {
    if (ts.isCallExpression(n)) {
      const c = n.expression;
      if (ts.isIdentifier(c) && c.text === 'fetch' && n.arguments.length >= 1) {
        const a = n.arguments[0];
        if (ts.isStringLiteral(a)) fetches.push(a.text);
      }
      // .then(setX)
      if (ts.isPropertyAccessExpression(c) && propName(c.name) === 'then' &&
          n.arguments.length >= 1 && ts.isIdentifier(n.arguments[0])) {
        setterToValue.set(n.arguments[0].text, null); // 先记下 setter，值稍后由解构补上
      }
    }
    ts.forEachChild(n, walkFetch);
  };
  walkFetch(sf);
  // 从 `const [d, setD] = useState(...)` 的绑定模式取权威配对
  const walkUseState = (n) => {
    if (ts.isVariableDeclaration(n) && ts.isArrayBindingPattern(n.name) &&
        n.initializer && ts.isCallExpression(n.initializer) &&
        ts.isIdentifier(n.initializer.expression) && n.initializer.expression.text === 'useState') {
      const el = n.name.elements;
      const val = el[0] && ts.isBindingElement(el[0]) && ts.isIdentifier(el[0].name) ? el[0].name.text : null;
      const set = el[1] && ts.isBindingElement(el[1]) && ts.isIdentifier(el[1].name) ? el[1].name.text : null;
      if (val && set) { setterToValue.set(set, val); stateNames.add(val); }
    }
    ts.forEachChild(n, walkUseState);
  };
  walkUseState(sf);
  // ⚠ 有 setter 却查不到解构出来的值名 ⇒ **解析不可信**，不猜（§82.4：无法判定 ⇒ 报未判定）
  const unresolvedSetters = [...setterToValue.keys()].filter(k => setterToValue.get(k) === null);
  const dataUrls = [...new Set(fetches)].filter(u => /\/latent\/data\/.+\.json$/.test(u));

  // ---- 找序数指称 ----
  const refs = [];
  const findRefs = (n) => {
    if (ts.isJsxElement(n) || ts.isJsxFragment(n) || ts.isJsxSelfClosingElement(n)) {
      const out = [];
      visibleStream(n, out, sf, 0);
      // 重建：表达式容器塌成 {expr}
      let flat = '';
      for (const s of out) flat += (s.kind === 'text' ? s.text : '{' + s.text + '}');
      ORDINAL.lastIndex = 0;
      let m;
      while ((m = ORDINAL.exec(flat)) !== null) {
        // ⚠ `m[1]` 现在是**一串**容器（§82.8 更正后的正则），逐个拆开。
        const rawContainers = m[1].match(/\{[^{}]*\}/g) || [];
        const bodies = rawContainers.map(c => c.slice(1, -1).trim());
        // ⚠ 空白间隔容器 = 内容是「只含空白的字符串字面量」的容器（`{" "}`）。
        //   ⚠ 不能用「空串」来数：trim 后 `{" "}` 是 `" "` 不是空串（§82.8 失误 6）。
        const isSpacer = (b) => /^(['"`])\s*\1$/.test(b);
        const exprs = bodies.filter(b => b.length > 0 && !isSpacer(b));
        const spacers = bodies.filter(isSpacer).length;
        // 绝对偏移：把 flat 里的匹配起点映射回源文件偏移 ⇒ 真实行号 + 去重键
        const absStart = srcOffsetOf(out, flat, m.index);
        refs.push({ expr_src: exprs.join(' | '), exprs, unit: m[2],
                    n_containers: rawContainers.length, n_spacer_containers: spacers,
                    abs_start: absStart, line: absStart >= 0 ? lineOfOffset(sf, absStart) : null });
      }
    }
    ts.forEachChild(n, findRefs);
  };
  findRefs(sf);
  // ⚠⚠ 去重：嵌套 JSX 元素（外层容器也含同一段文本）会把同一处报多次。
  //   判据是**绝对偏移**相同 ⇒ 同一处；不是「expr 相同」（后者会把两处真站点并掉）。
  const seenAbs = new Set();
  const refsDedup = refs.filter(r => {
    if (r.abs_start < 0 || !seenAbs.has(r.abs_start)) {
      if (r.abs_start >= 0) seenAbs.add(r.abs_start);
      return true;
    }
    return false;
  });

  // ---- 解析每个序数指称背后的表 ----
  const resolved = refsDedup.map((r) => {
    const ids = (r.expr_src.match(/[A-Za-z_$][\w$]*/g) || []);
    let hit = null;
    for (const id of ids) {
      for (const d of decls.get(id) || []) {
        const c = objectCallViaDecl(d, decls, new Set());
        if (c) { hit = { ...c, decl_line: lineOf(sf, d) }; break; }
      }
      if (hit) break;
    }
    if (!hit) {
      // ⚠⚠ 「不是 Record 表」与「解析不出来」必须**分开**（§82.8 失误 4）：
      //   `Scene3D.tsx` 的「第 {focusedStep} 步」背后是数组下标，**合法地**不属于 K1；
      //   而「有个表但我认不出它在哪」才是「无法判定」，必须判红。
      //   ⚠ 旧版把两者都写成 `resolved:false` ⇒ 「无法判定 0」这个数毫无信息量。
      return { ...r, kind: 'not_record_table', resolved: false,
               why: '表达式背后不是由 Object.keys/entries 派生的 Record 表（合法排除）' };
    }
    const rootId = hit.table_path[0];
    // ⚠ 成员别名只认**一跳**，且必须唯一。多个候选 ⇒ 无法判定，不猜（§82.4）。
    let prefix = [];
    let prefix_why = null;
    if (stateNames.has(rootId)) {
      // 根标识符**本身就是** fetch 出来的整份 payload ⇒ 无前缀
      prefix = [];
    } else {
      // ⚠ 找的是 `const <rootId> = <状态变量>.<成员>`，
      //   而**不是** `<状态变量>.<成员>` 作为根（那是上一版的写法，永远匹配不上
      //   `const h = d.headline` 这种「别名 = 状态变量.成员」的真实形状 ⇒ §82.8 失误 10）。
      const cands = new Set();
      for (const [, ds] of decls) for (const d of ds) {
        if (!ts.isIdentifier(d.name) || d.name.text !== rootId) continue;
        if (d.initializer && ts.isPropertyAccessExpression(d.initializer) &&
            ts.isIdentifier(d.initializer.expression) &&
            stateNames.has(d.initializer.expression.text)) {
          const p = propName(d.initializer.name);
          if (p) cands.add(p);
        }
      }
      if (cands.size === 1) prefix = [cands.values().next().value];
      else if (cands.size > 1) prefix_why = `${rootId} 有 ${cands.size} 个成员别名（${[...cands].join('/')}）⇒ 无法判定`;
      else prefix_why = `根标识符 ${rootId} 既不是状态变量，也找不到「const ${rootId} = <状态变量>.<成员>」形式的别名`;
    }
    // 产物文件
    let artifact = null, artifact_why = prefix_why;
    if (dataUrls.length === 1) artifact = dataUrls[0].split('/latent/data/')[1];
    else artifact_why = artifact_why ||
      (dataUrls.length === 0 ? '组件里没有 /latent/data/*.json 的 fetch'
                             : `组件里有 ${dataUrls.length} 个数据 fetch，无法判定用哪个`);
    return {
      ...r,
      kind: artifact ? 'record_table' : 'unresolved',
      resolved: Boolean(artifact),
      why: artifact_why,
      via: hit.via,
      decl_line: hit.decl_line,
      method: hit.method,
      // ⚠ K1b 要求「用 node 执行**面板那行表达式本身**」，不是 Python 复现
      //   ⇒ 必须把初始化式的**源码原文**交出去。
      init_src: hit.init_src,
      alias_name: rootId,
      prefix_path: prefix.join('.'),
      // ⚠ 用了成员别名时**要把根标识符换掉**（§82.8 失误 10）：
      //   `const h = d.headline` + `Object.keys(h.T)` ⇒ 路径是 `headline.T`，
      //   不是 `headline.h.T` —— 否则会把面板里根本不存在的路径印出来。
      table_path: [...prefix, ...hit.table_path.slice(prefix.length ? 1 : 0)].join('.'),
      artifact,
    };
  });

  return { file: path.basename(file), n_object_calls: nObjectCalls,
           n_ordinal_refs: refsDedup.length,
           unresolved_setters: unresolvedSetters,
           refs: resolved };
}

function main() {
  const dir = process.argv[2];
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.tsx')).sort();
  const out = files.map(f => scanFile(path.join(dir, f)));
  console.log(JSON.stringify({ files: out }, null, 2));
}
main();
