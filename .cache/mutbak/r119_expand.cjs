#!/usr/bin/env node
/**
 * 修订 119 —— 判据「展开条数」计算器（第三版：acorn 真 AST）。
 *
 * ⚠⚠ 前两版都失败，且都是**仪器**的错：
 *   v1 逐字符 + 字符串状态机 → 在 heldout 上算出 0（in_str 被未闭合引号噎住）
 *   v2 行级大括号配对 → 在 heldout 上算出 47（跨行模板字面量让行级配对全错位）
 *   v3 AST 嵌套对了，但我把**校准值本身写错**（76 手算成 47−8=39 + 6 + 30 = 75）
 *   ⇒ 三次里前两次是仪器错、第三次是校准值错。这正是本仓纪律
 *     「独立复算的实现本身可能才是坏的东西」连续应验三次。
 *
 * v3 用仓库里已有的 acorn（frontend/node_modules/next/dist/compiled/acorn）
 * 拿真 AST：嵌套不靠猜缩进，注释/字符串/正则由解析器自己处理。
 *
 * ⚠ 校准样本 = verify_heldout.mjs，手算答案 **75**：
 *     47 静态 − 8 循环内站点 = 39 循环外
 *     + transfer 循环 2 站点 × 3 行          =  6
 *     + rows 循环 6 站点 × 6 行，但 C4 的两分支（:268/:272）互斥 ⇒ 5×6 = 30
 *     = 39 + 6 + 30 = 75
 *   算不出 75 ⇒ 本脚本不得用于任何其他文件，直接退出 1。
 *
 * ⚠ 运行期迭代数（AXES / LAYERS / truth.rows / phrases …）来自**产物或源码**，
 *   必须显式给出**出处**；脚本会逐条打印出处，解析不到的**逐条报错**，不猜。
 * ⚠ 表的键是 `文件:循环头行号::循环变量名` —— 因为 `ax` 这个名字在
 *   verify_axis_readout.mjs 的 5 个循环里复用，按变量名定位会张冠李戴。
 */
const fs = require('fs');
const path = require('path');

const ROOT = '/Users/zhourui/code/steer3d';
const DIR = path.join(ROOT, '.cache/browser_verify');
const acorn = require(path.join(ROOT, 'frontend/node_modules/next/dist/compiled/acorn'));

const FILES = [
  'verify_subspace.mjs', 'verify_relamp.mjs', 'verify_scene_link.mjs',
  'verify_hinge_panel.mjs', 'verify_path.mjs', 'verify_heldout.mjs',
  'verify_axis_readout.mjs', 'probe_dedup_rendered.mjs',
];

/** 显式出处表：`文件:行::循环变量` → {n, via} */
const RUNTIME = {
  'verify_heldout.mjs:186::t':   { n: 3, via: 'heldout_readability.json .transfer.length = 3' },
  'verify_heldout.mjs:224::r':   { n: 6, via: 'heldout_readability.json .rows.length = 6' },
  'verify_axis_readout.mjs:113::ax': { n: 4, via: 'axis_readouts.json Object.keys(.axes)=4' },
  'verify_axis_readout.mjs:195::L':  { n: 3, via: 'axis_readouts.json per_layer 键=3（12/14/20），四轴一致' },
  'verify_axis_readout.mjs:338::ax': { n: 4, via: '同上 AXES=4' },
  'verify_axis_readout.mjs:459::ax': { n: 2, via: '源码字面量 [creativity, reasoning]' },
  'verify_axis_readout.mjs:565::ax': { n: 2, via: '源码字面量 [confidence, caution]' },
  'verify_axis_readout.mjs:609::ax': { n: 4, via: '源码字面量 四轴' },
  'verify_subspace.mjs:23::ROWS': { n: 4, via: 'readable_subspace.json .surface_directions.length = 4' },
  'verify_subspace.mjs:245::name_want_got': { n: 2, via: '源码字面量 2 项（caution_absorbed / control.note）' },
  'verify_subspace.mjs:305::key': { n: 4, via: 'ROWS = readable_subspace.json .surface_directions 的 key，length=4' },
  'verify_path.mjs:146::name_needle': { n: 13, via: '源码字面量 B1–B13 共 13 项' },
  'probe_dedup_rendered.mjs:143::k_n':  { n: 8, via: '源码字面量 D.removed 的 8 个键（:105–:112）' },
  'probe_dedup_rendered.mjs:150::k':  { n: 5, via: '源码字面量 5 个键' },
  'probe_dedup_rendered.mjs:188::label_needle': { n: 2, via: '源码字面量 2 项（:185/:186）' },
};

function loopVarOf(loop) {
  const l = loop.left;
  if (!l || l.type !== 'VariableDeclaration') return null;
  const d = l.declarations[0];
  return d && d.id.type === 'Identifier' ? d.id.name
       : (d && d.id.type === 'ArrayPattern' ? d.id.elements.map(e => e.name).join('_') : null);
}

function iterationsOf(loop, fname) {
  const key = `${fname}:${loop.loc.start.line}::${loopVarOf(loop)}`;
  if (RUNTIME[key]) return { kind: 'const', ...RUNTIME[key] };
  const r = loop.right;
  if (!r) return { kind: 'dyn', why: 'for 无右端' };
  if (r.type === 'ArrayExpression') {
    return { kind: 'const', n: r.elements.length, via: `源码字面量 ${r.elements.length} 项` };
  }
  if (r.type === 'CallExpression' && r.callee.type === 'MemberExpression'
      && /querySelectorAll|entries|matchAll/.test(r.callee.property.name || '')) {
    return { kind: 'dom', why: `DOM 依赖：${r.arguments[0] && r.arguments[0].value}` };
  }
  return { kind: 'dyn', why: `右端 ${r.type}，无出处（键 ${key}）` };
}

/* ------------------------------------------------ 互斥 if/else 分支识别 */
function findExclusiveGroups(ast) {
  const groups = [];
  (function walk(n) {
    if (!n || typeof n !== 'object') return;
    if (n.type === 'IfStatement' && n.alternate) {
      const a = countChecks(n.consequent), b = countChecks(n.alternate);
      if (a && b) groups.push({ node: n, lines: [], size: a.length + b.length });
    }
    for (const k of Object.keys(n)) {
      if (k === 'loc' || k === 'type') continue;
      const v = n[k];
      if (Array.isArray(v)) v.forEach(walk); else if (v && typeof v === 'object') walk(v);
    }
  })(ast);
  function countChecks(n) {
    const out = [];
    (function w(x) {
      if (!x || typeof x !== 'object') return;
      if (x.type === 'CallExpression' && x.callee.type === 'Identifier' && x.callee.name === 'check') {
        out.push(x.loc.start.line);
      }
      for (const k of Object.keys(x)) {
        if (k === 'loc' || k === 'type') continue;
        const v = x[k];
        if (Array.isArray(v)) v.forEach(w); else if (v && typeof v === 'object') w(v);
      }
    })(n);
    return out;
  }
  return groups;
}

/* ------------------------------------------------ 主分析 */
function analyse(fname) {
  const src = fs.readFileSync(path.join(DIR, fname), 'utf8');
  const ast = acorn.parse(src, { ecmaVersion: 'latest', sourceType: 'module', locations: true });
  const groups = findExclusiveGroups;   // eslint-disable-line no-unused-vars
  const exclGroup = new Map();   // 行号 -> 互斥组 id
  let gidx = 0;
  for (const g of findExclusiveGroups(ast)) {
    // 该 if/else 体内**第一层**的 check 站点互斥
    const lines = [];
    (function collect(n, depth) {
      if (!n || typeof n !== 'object') return;
      if (n.type === 'CallExpression' && n.callee.type === 'Identifier' && n.callee.name === 'check') {
        lines.push(n.loc.start.line); return;
      }
      for (const k of Object.keys(n)) {
        if (k === 'loc' || k === 'type') continue;
        const v = n[k];
        if (Array.isArray(v)) v.forEach(x => collect(x, depth + 1));
        else if (v && typeof v === 'object') collect(v, depth + 1);
      }
    })(g.node.consequent, 0);
    (function collect(n) {
      if (!n || typeof n !== 'object') return;
      if (n.type === 'CallExpression' && n.callee.type === 'Identifier' && n.callee.name === 'check') {
        lines.push(n.loc.start.line); return;
      }
      for (const k of Object.keys(n)) {
        if (k === 'loc' || k === 'type') continue;
        const v = n[k];
        if (Array.isArray(v)) v.forEach(collect);
        else if (v && typeof v === 'object') collect(v);
      }
    })(g.node.alternate, 0);
    const gid = gidx++;
    for (const l of lines) exclGroup.set(l, gid);
  }

  const sites = [];
  (function walk(n, loops) {
    if (!n || typeof n !== 'object') return;
    let nl = loops;
    if (n.type === 'ForOfStatement' || n.type === 'ForStatement' || n.type === 'ForInStatement') {
      nl = loops.concat([iterationsOf(n, fname)]);
    }
    if (n.type === 'CallExpression' && n.callee.type === 'Identifier' && n.callee.name === 'check') {
      sites.push({ line: n.loc.start.line, loops: nl,
                   excl: exclGroup.has(n.loc.start.line) ? exclGroup.get(n.loc.start.line) : null });
    }
    for (const k of Object.keys(n)) {
      if (k === 'loc' || k === 'type') continue;
      const v = n[k];
      if (Array.isArray(v)) v.forEach(x => walk(x, nl));
      else if (v && typeof v === 'object') walk(v, nl);
    }
  })(ast, []);
  return sites;
}

/* ------------------------------------------------ 展开 */
function expand(sites) {
  let total = 0;
  const unresolved = new Set();
  const vias = [];
  const seenExcl = new Set();
  const per = [];
  for (const s of sites) {
    let m = 1, ok = true;
    for (const l of s.loops) {
      if (l.kind === 'const') { m *= l.n; vias.push(l.via); }
      else { ok = false; unresolved.add(l.why || l.kind); }
    }
    if (!ok) { per.push({ line: s.line, mult: null, loops: s.loops, excl: s.excl }); continue; }
    if (s.excl != null) {
      // 同一 if/else 组内每轮只跑一条 ⇒ 组只计一次
      const gk = s.loops.map(l => JSON.stringify(l)).join('|') + '|gid' + s.excl;
      if (seenExcl.has(gk)) { per.push({ line: s.line, mult: 0, note: '与同组另一分支互斥' }); continue; }
      seenExcl.add(gk);
    }
    total += m;
    per.push({ line: s.line, mult: m, loops: s.loops, excl: s.excl });
  }
  return { total, unresolved: [...unresolved], vias: [...new Set(vias)], per };
}

/* ------------------------------------------------ 报告 */
const all = {};
for (const f of FILES) all[f] = analyse(f);

console.log('=== AST 口径（acorn）===\n');
console.log('文件'.padEnd(24) + '静态'.padStart(6) + '循环内'.padStart(8) + '展开'.padStart(8) + '   说明');
console.log('-'.repeat(104));
let T = { s: 0, e: 0 }, allUnresolved = [];
for (const f of FILES) {
  const sites = all[f];
  const inLoop = sites.filter(s => s.loops.length).length;
  const r = expand(sites);
  if (r.unresolved.length) allUnresolved.push([f, r.unresolved]);
  console.log(f.padEnd(24) + String(sites.length).padStart(6) + String(inLoop).padStart(8)
    + (r.unresolved.length ? '不可确定'.padStart(9) : String(r.total).padStart(9))
    + '   ' + (r.unresolved.length ? '数据依赖：' + r.unresolved.join('；')
      : (inLoop ? '循环迭代数全部有出处' : '无判据级循环')));
  if (!r.unresolved.length) { T.s += sites.length; T.e += r.total; }
}
console.log('-'.repeat(104));
console.log('可静态确定合计：静态=%d 展开=%d', T.s, T.e);
if (allUnresolved.length) {
  console.log('\n⚠⚠ 仍有无法静态确定的循环（**不猜**，必须用实跑或人工补表）：');
  for (const [f, u] of allUnresolved) console.log('  ' + f.padEnd(24) + u.join('；'));
}

console.log('\n=== ⚠ 校准 verify_heldout：手算 = 75 ===');
const h = expand(all['verify_heldout.mjs']);
console.log('  AST 算出 = %d  ⇒ %s', h.total, h.total === 75 ? 'PASS 仪器可信' : 'FAIL ⇒ 退出，不用于其他文件');
if (h.total !== 75) {
  for (const p of h.per) console.log('    ' + String(p.line).padStart(4) + ' ×' + String(p.mult).padEnd(5)
    + ' ' + (p.note || '') + ' ' + JSON.stringify((p.loops || []).map(l => l.via || l.why)));
  process.exit(1);
}
console.log('  互斥分支：:268 / :272（C4 的 if / else）⇒ 每行只计 1 条');
console.log('\n=== 展开出处逐条（每个数都能指回产物或源码）===');
const seen = new Set();
for (const [f, sites] of Object.entries(all)) {
  for (const l of expand(sites).vias) { if (!seen.has(l)) { seen.add(l); console.log('  · ' + l); } }
}
process.exit(0);