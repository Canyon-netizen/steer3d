#!/usr/bin/env node
/**
 * 修订 83 K3 的 AST 仪器：把 `frontend/` 里所有运行时 `fetch()` 的数据文件
 * **完整**还原出来（输出 JSON 到 stdout；判定与报告由 python 守卫做）。
 *
 * 用法：node .cache/xcheck/ts_fetch_paths.js <frontend 目录>
 *
 * ⚠⚠⚴ 为什么必须用 AST 而不是正则（这是我上一轮刚踩的坑，见 §82.8）：
 *   全站 30 处 `fetch(` 里只有 **17 处**是字面量 URL，其余是三种非字面量形式：
 *     ① `fetch(u)`            —— u 是 `const get = (u) => fetch(u)` 的形参
 *     ② `fetch(file.url)`     —— file 来自一个含 `url:` 字面量的数组
 *     ③ ``fetch(`${F}/x.json`)`` —— F 是模块级字符串常量
 *   ⚠ 逐行正则只能看到 ① 前半，**分母会低报**。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const ts = require(path.join(__dirname, '..', '..', 'frontend', 'node_modules', 'typescript'));


function propName(n) {
  if (ts.isIdentifier(n)) return n.text;
  if (ts.isStringLiteral(n) || ts.isNumericLiteral(n)) return n.text;
  return null;
}

/** 顶层/函数内的 `const X = <string 字面量>` */
function stringConsts(sf) {
  const m = new Map();
  const w = (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer &&
        ts.isStringLiteral(n.initializer)) m.set(n.name.text, n.initializer.text);
    ts.forEachChild(n, w);
  };
  w(sf);
  return m;
}

/** 所有 `X = <对象数组字面量>` 里 `url:` 属性的字符串值 */
function urlProps(sf) {
  const out = new Set();
  const w = (n) => {
    if (ts.isPropertyAssignment(n) && propName(n.name) === 'url' && ts.isStringLiteral(n.initializer)) {
      out.add(n.initializer.text);
    }
    ts.forEachChild(n, w);
  };
  w(sf);
  return out;
}

/** `const NAME = (arg) => fetch(arg)` ⇒ 返回 NAME → arg 的映射。
 *  ⚠⚠ 第一版推的是**形参名**却拿**函数名**去匹配（`includes("get")` vs 存的 `"u"`）
 *     ⇒ 6 个真实路径全部落进「未还原」，分母低报 6。这正是本轮要立的教训。 */
function fetchHelperMap(sf) {
  const m = new Map();                    // 函数名 -> 形参名
  const w = (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer &&
        ts.isArrowFunction(n.initializer) && n.initializer.parameters.length >= 1 &&
        ts.isIdentifier(n.initializer.parameters[0].name)) {
      let usesFetch = false;
      const inner = (x) => {
        if (ts.isCallExpression(x) && ts.isIdentifier(x.expression) && x.expression.text === 'fetch') usesFetch = true;
        ts.forEachChild(x, inner);
      };
      inner(n.initializer.body);
      if (usesFetch) m.set(n.name.text, n.initializer.parameters[0].name.text);
    }
    ts.forEachChild(n, w);
  };
  w(sf);
  return m;
}

/** 形参名 → 函数名 */
function helperMapInverse(m, param) {
  for (const [k, v] of m) if (v === param) return k;
  return null;
}

function walkFiles(dir, acc = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name === '.next' || e.name.startsWith('.')) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walkFiles(p, acc);
    else if (/\.tsx?$/.test(e.name)) acc.push(p);
  }
  return acc;
}

function main() {
  const fe = process.argv[2];
  const rows = [];
  let nFetchCalls = 0, nLiteral = 0, nViaHelper = 0, nViaUrlProp = 0, nViaConst = 0, nUnresolved = 0;

  for (const file of walkFiles(fe)) {
    const sf = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'),
                                   ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const consts = stringConsts(sf);
    const urls = urlProps(sf);
    const helperMap = fetchHelperMap(sf);

    const helperArgs = new Map();
    const collectHelperArgs = (n) => {
      if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) &&
          helperMap.has(n.expression.text) &&
          n.arguments.length >= 1 && ts.isStringLiteral(n.arguments[0])) {
        if (!helperArgs.has(n.expression.text)) helperArgs.set(n.expression.text, []);
        helperArgs.get(n.expression.text).push(n.arguments[0].text);
      }
      ts.forEachChild(n, collectHelperArgs);
    };
    collectHelperArgs(sf);

    const rel = path.relative(fe, file);
    const visit = (n) => {
      if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) &&
          n.expression.text === 'fetch' && n.arguments.length >= 1) {
        nFetchCalls += 1;
        const arg = n.arguments[0];
        const line = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
        const push = (u, how) => rows.push({ url: u, file: rel, line, how });
        if (ts.isStringLiteral(arg)) { nLiteral += 1; push(arg.text, 'literal'); }
        else if (ts.isIdentifier(arg)) {
          const hn = helperMapInverse(helperMap, arg.text);
          if (hn && helperArgs.has(hn)) {
            nViaHelper += 1;
            for (const a of helperArgs.get(hn)) push(a, 'helper:' + hn);
          } else { nUnresolved += 1; push(null, 'UNRESOLVED'); }
        }
        else if (ts.isPropertyAccessExpression(arg) && propName(arg.name) === 'url') {
          if (urls.size) { nViaUrlProp += 1; for (const u of urls) push(u, 'url-prop'); }
          else { nUnresolved += 1; push(null, 'UNRESOLVED'); }
        }
        else if (ts.isTemplateExpression(arg)) {
          let ok = true, out = '';
          for (const sp of arg.templateSpans) {
            const e = sp.expression;
            if (!e || !ts.isIdentifier(e) || !consts.has(e.text)) { ok = false; break; }
            out += consts.get(e.text) + sp.literal.text;
          }
          if (ok) { nViaConst += 1; push(out, 'template-const'); }
          else { nUnresolved += 1; push(null, 'UNRESOLVED'); }
        }
        else { nUnresolved += 1; push(null, 'UNRESOLVED'); }
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);
  }

  const byUrl = new Map();
  const unresolved = [];
  for (const r of rows) {
    if (r.url === null) { unresolved.push({ file: r.file, line: r.line }); continue; }
    if (!byUrl.has(r.url)) byUrl.set(r.url, []);
    byUrl.get(r.url).push(`${r.file}:${r.line} (${r.how})`);
  }
  console.log(JSON.stringify({
    n_fetch_calls: nFetchCalls,
    by_kind: { literal: nLiteral, helper: nViaHelper, url_prop: nViaUrlProp, template_const: nViaConst },
    n_paths: byUrl.size,
    n_unresolved_sites: unresolved.length,
    paths: [...byUrl].sort().map(([u, sites]) => ({ url: u, sites })),
    unresolved,
  }, null, 2));
}
main();
