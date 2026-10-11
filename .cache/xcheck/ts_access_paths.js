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
const allOk = known.every(k => k.ok);
console.error(allOk ? '✓ 3/3 已知答案成立' : '✗ 已知答案未全部成立 ⇒ 仪器不可信，不发数');
process.exit(allOk ? 0 : 1);