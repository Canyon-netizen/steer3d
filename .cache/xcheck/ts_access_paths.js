#!/usr/bin/env node
/**
 * 用 TypeScript AST（不是正则）判定「产物字段有没有被面板读到」。
 *
 * ⚠⚠ 为什么要换掉正则：正则手搓的版本连改三次给出三个数
 *   （84.7% / 70.9% / 82.7%），最后一次的差异完全来自我自己
 *   `.replace('_','.')` 把 `per_id` 打成 `per.id`。
 *   ⇒ **仪器不可信时，任何数字都不能发出去**。
 *   ⇒ 本脚本做三件正则做不到的事：
 *     1. 解析 `const rs = d.readability_static` 这类别名，
 *        把 `rs.per_id` 还原成 `readability_static.per_id`；
 *     2. 认出 `.map((r) => … r.field)` 里回调变量的作用域，
 *        把循环渲染的字段算成「沿这条路径被读到」；
 *     3. 不把 `per_id` 这类下划线名当成分隔符。
 *
 * 输出（JSON）：{ accesses: [...], loops: {...}, known_answers: {...} }
 * 判定分级由调用方按 修订 73 的口径做。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const ts = require(path.join(__dirname, '..', '..', 'frontend', 'node_modules', 'typescript'));

const LOOP_METHODS = new Set(['map', 'forEach', 'flatMap', 'reduce', 'filter', 'some', 'every', 'find']);

function analyse(file, rootName) {
  const src = fs.readFileSync(file, 'utf8');
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

  /** 变量别名：变量名 -> 相对 root 的点分路径 */
  const alias = new Map();
  /** 循环变量名 -> 被迭代容器的点分路径 */
  const loopVar = new Map();
  const accesses = new Set();
  const loops = [];

  function key(...segs) { return segs.filter(Boolean).join('/'); }

  /** 把一个表达式解析成 [rootPath, restSegments]；解析不出返回 null。 */
  function chain(node) {
    if (ts.isPropertyAccessExpression(node)) {
      const base = chain(node.expression);
      if (base === null) return null;
      return { root: base.root, segs: base.segs.concat(node.name.getText(sf)) };
    }
    if (ts.isElementAccessExpression(node) && ts.isStringLiteral(node.argumentExpression)) {
      const base = chain(node.expression);
      if (base === null) return null;
      return { root: base.root, segs: base.segs.concat(node.argumentExpression.text) };
    }
    if (ts.isIdentifier(node)) {
      const name = node.text;
      if (name === rootName) return { root: rootName, segs: [] };
      if (loopVar.has(name)) return { root: loopVar.get(name), segs: ['*'] };
      if (alias.has(name)) {
        const p = alias.get(name);
        return { root: rootName, segs: p ? p.split('.').filter(Boolean) : [] };
      }
      return null;
    }
    if (ts.isParenthesizedExpression(node)) return chain(node.expression);
    // ⚠⚠ `Object.entries(X).map(…)` 里 `.map` 的接收者是一个 **CallExpression**。
    //   第一版 `chain()` 不认它 ⇒ recv 解析成 null ⇒ 整个循环站点被**静默跳过**，
    //   于是 `Object.entries(rs.per_id).map(([id, v]) => … v.dot …)` 里的
    //   `v.dot` 一个都没进访问集合。
    if (ts.isCallExpression(node)) {
      const sig = node.expression;
      if (ts.isPropertyAccessExpression(sig) &&
          sig.expression.getText(sf) === 'Object' &&
          /^(entries|keys|values)$/.test(sig.name.getText(sf)) &&
          node.arguments.length) {
        return chain(node.arguments[0]);
      }
    }
    return null;
  }

  function pathOf(node) {
    const c = chain(node);
    return c === null ? null : key(c.root, ...c.segs);
  }

  // ---- 第 1 遍：收别名（var x = d.<chain> 或 var y = x）----
  function collectAliases(node) {
    if (ts.isVariableDeclaration(node) && node.initializer && ts.isIdentifier(node.name)) {
      const p = pathOf(node.initializer);
      if (p !== null) alias.set(node.name.text, p === rootName ? '' : p.slice(rootName.length + 1));
    }
    ts.forEachChild(node, collectAliases);
  }
  collectAliases(sf);

  // ---- 第 2 遍：收访问与循环站点 ----
  function walk(node) {
    if (ts.isCallExpression(node)) {
      const sig = node.expression;
      if (ts.isPropertyAccessExpression(sig) && LOOP_METHODS.has(sig.name.text)) {
        const recv = pathOf(sig.expression);
        if (recv !== null) {
          loops.push(recv);
          const cb = node.arguments.find(a => ts.isArrowFunction(a) || ts.isFunctionExpression(a));
          if (cb && cb.parameters.length) {
            const p0 = cb.parameters[0];
            if (ts.isIdentifier(p0.name)) loopVar.set(p0.name.text, recv);
            else if (ts.isObjectBindingPattern(p0.name)) {
              // ({ dot, share, freq }) => …
              for (const el of p0.name.elements) {
                const bn = el.propertyName || el.name;
                if (ts.isIdentifier(bn)) loopVar.set(bn.text, recv);
              }
            } else if (ts.isArrayBindingPattern(p0.name)) {
              // ⚠ `Object.entries(X).map(([k, v]) => …)`：**第二个**才是值。
              //   只在迭代源来自 Object.entries/keys/values 时这么绑 ——
              //   对 `ys.map((v, i) => …)` 第二个是**下标**，绑错了会把
              //   `i` 当成整条记录，那比漏报更坏。
              const fromObjectEntries = /Object\.(entries|keys|values)\s*\(/.test(
                sig.expression.getText(sf));
              if (fromObjectEntries) {
                const v = p0.name.elements[1];
                if (v && ts.isIdentifier(v.name)) loopVar.set(v.name.text, recv);
              }
            }
          }
        }
      } else if (ts.isPropertyAccessExpression(sig) &&
                 sig.name.getText(sf) === 'entries' &&
                 sig.expression.getText(sf) === 'Object' && node.arguments.length) {
        const recv = pathOf(node.arguments[0]);
        if (recv !== null) loops.push(recv);
      }
    }
    if (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) {
      const p = pathOf(node);
      if (p !== null) accesses.add(p);
    }
    ts.forEachChild(node, walk);
  }
  walk(sf);

  return { accesses: [...accesses].sort(), loops: [...new Set(loops)].sort(), alias: Object.fromEntries(alias) };
}

// ---- 已知答案（阳性对照）：这三条必须在不调参的前提下就成立 ----
const CHECKS = [
  { panel: 'BPathPanel.tsx', must_access: 'd/orthogonality/hi_sites28/control_arm', why: '源码第 746-748 行确实读了它' },
  { panel: 'BPathPanel.tsx', must_NOT_access: 'd/readability_static/control_arm', why: '新增块，面板里没有任何访问' },
  { panel: 'BPathPanel.tsx', must_loop: 'd/layer_profile/rows', why: '第 527 行 layer_profile.rows.map((r) => …)' },
  // ⚠ 第四条（因 bug 补上）：接收者是 CallExpression 的循环。
  //   `Object.entries(X).map(([id, v]) => … v.dot …)` 必须既进循环站点、
  //   又把 `v.dot` 还原成 `X/*/dot`。第一版两样都没有，**而前三条照样全过**
  //   —— 三条对照全绿却漏掉整整一类机制，正是「对照要覆盖每个条件」。
  { panel: 'BPathPanel.tsx', must_loop: 'd/readability_static/per_id', why: '第 436 行 Object.entries(rs.per_id).map(([id, v]) => …)' },
  { panel: 'BPathPanel.tsx', must_access: 'd/readability_static/per_id/*/dot', why: '同一个循环的回调体里 v.dot / v.share' },
  // ⚠ 反向对照：三条**独立 grep 核过**的「源码里根本没有」，用来盯住 C 级
  //   不能被仪器的高估灌水。
  //   `suites` 只出现在第 65 行的**类型声明**里 —— 它不是表达式访问。
  { panel: 'BPathPanel.tsx', must_NOT_access: 'd/built_from', why: 'grep built_from = 0 处' },
  { panel: 'BPathPanel.tsx', must_NOT_access: 'd/readability_static/what', why: 'grep rs.what = 0 处' },
  { panel: 'BPathPanel.tsx', must_NOT_access: 'd/selfcheck_detail/suites', why: '第 65 行是类型声明，不是访问' },
];

const panels = {
  'BPathPanel.tsx': ['d', 'j', 'x'],
  'HeldoutPanel.tsx': ['d', 'j', 'x'],
  'EvidenceLadderPanel.tsx': ['d', 'j', 'x'],
};

const out = {};
for (const [p, roots] of Object.entries(panels)) {
  const f = path.join(__dirname, '..', '..', 'frontend', 'components', p);
  out[p] = {};
  for (const r of roots) {
    const a = analyse(f, r);
    if (a.accesses.length || a.loops.length) out[p][r] = a;
  }
}

// 已知答案校验
const known = [];
for (const c of CHECKS) {
  const A = out[c.panel] || {};
  const all = Object.values(A).flatMap(v => v.accesses);
  const allLoops = Object.values(A).flatMap(v => v.loops);
  const entry = { check: c, panel: c.panel };
  if (c.must_access) {
    entry.ok = all.some(p => p.startsWith(c.must_access));
    entry.n_matching = all.filter(p => p.startsWith(c.must_access)).length;
  } else if (c.must_NOT_access) {
    entry.ok = !all.some(p => p.startsWith(c.must_NOT_access));
    entry.n_matching = all.filter(p => p.startsWith(c.must_NOT_access)).length;
  } else if (c.must_loop) {
    entry.ok = allLoops.some(p => p === c.must_loop || p.startsWith(c.must_loop + '/'));
    entry.n_matching = allLoops.filter(p => p.startsWith(c.must_loop)).length;
  }
  entry.samples = all.filter(p => (c.must_access || c.must_NOT_access || '').split('/').slice(0, 3).every(s => p.includes(s))).slice(0, 4);
  known.push(entry);
}

console.log(JSON.stringify({ known_answers: known, panels: out }, null, 1));
const nOK = known.filter(k => k.ok).length;
const allOk = nOK === known.length;
// ⚠ 这个数字**必须实算**。第一版硬写着「3/3」而 CHECKS 已经加到 5 条
//   —— 一个会自己过期的成功信息，等于每次都在说「这条判据一直在跑」。
console.error(allOk
  ? `✓ ${nOK}/${known.length} 已知答案成立`
  : `✗ ${nOK}/${known.length} 已知答案成立 ⇒ 仪器不可信，不发数`);
process.exit(allOk ? 0 : 1);