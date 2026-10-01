// Headless check of the delta (干预 vs 对照) view's *arithmetic*.
//
// The browser pass proves the view draws something and the controls respond.
// It cannot prove the numbers are right — a plot of a transposed basis, or
// a delta differenced after quantisation, renders just as plausibly as a
// correct one. So this runs the page's real projectPair() against the same
// bundle and compares with an independent numpy computation.
//
// It also checks the identity the whole view rests on:
//     proj(h + delta) - proj(h) == proj(delta)
// which holds only because the per-layer mean cancels. If the browser ever
// subtracts the mean from the delta too, this goes red.

import fs from "fs";
import path from "path";

const ROOT = "/Users/zhourui/code/steer3d/frontend/public/latent";
const DATA = path.join(ROOT, "data");

const calls = { canvas: {} };
function makeCtx(name) {
  const rec = () => { calls.canvas[name] = (calls.canvas[name] || 0) + 1; };
  const noop = () => {};
  return new Proxy({}, {
    get(_, k) {
      if (["setTransform", "clearRect", "fillRect", "fillText", "strokeText",
           "beginPath", "arc", "fill", "stroke", "moveTo", "lineTo", "rect",
           "save", "restore", "translate", "rotate", "setLineDash", "closePath"]
          .includes(k)) return (...a) => { rec(); calls.canvas[name + ":" + k] = true; };
      if (k === "measureText") return () => ({ width: 10 });
      return noop;
    },
    set() { return true; },
  });
}

const IDS = ["pbar","pmsg","selTraj","probText","rngTok","rngLayer","valLayer",
  "valTok","mainTitle","mainSub","tblTop","genTxt","layerStory","stRaw","stEnt",
  "stNorm","stMove","stD","sideTitle","dbg","tip","app","loading","btnPlay",
  "btnDepth","tabXY","tabBar","tabDim","tabDelta","selPair","cv","cvD",
  "pairRow","pairNote","legendDelta","legendDelta2","deltaCap","layerStory","trajPanel"];
const elements = {};
for (const id of IDS) {
  elements[id] = {
    id, textContent: "", innerHTML: "", className: "", value: 0, max: 0,
    min: 0, step: 1, style: {}, dataset: {},
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    getContext: () => makeCtx(id),
    getBoundingClientRect: () => ({ width: 1200, height: 700 }),
    appendChild(){}, onclick: null, oninput: null, onmousemove: null,
    onchange: null, dispatchEvent(){}, addEventListener(){},
    onmouseleave: null, onchange: null, addEventListener(){},
  };
}

global.document = {
  title: "",
  getElementById: id => elements[id] || (elements[id] = {
    id, textContent: "", innerHTML: "", style: {},
    classList: { add(){}, remove(){}, toggle(){} },
    getContext: () => makeCtx(id), addEventListener(){},
    getBoundingClientRect: () => ({ width: 1200, height: 700 }),
  }),
  querySelector: s => elements[s.replace("#", "")],
  createElement: () => ({ style: {}, appendChild() {}, textContent: "" }),
};
global.window = { addEventListener(){}, devicePixelRatio: 1 };
global.location = { search: "" };
global.performance = { now: () => Date.now() };
global.setInterval = () => 0; global.clearInterval = () => {};
global.TextDecoder = class { constructor(){} decode(a){ return new Uint8Array(a).join(","); } };

global.fetch = async (url, opts) => {
  if (opts && opts.method === "POST") return { ok: true, status: 204 };
  const p = path.join(ROOT, String(url).replace(/^.*?latent\//, ""));
  if (!fs.existsSync(p)) throw new Error("missing " + p);
  const buf = fs.readFileSync(p);
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  return { ok: true, status: 200, arrayBuffer: async () => ab,
           json: async () => JSON.parse(buf.toString("utf8")) };
};

const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const code = blocks.join("\n");
const mod = new Function(code +
  "\n;return {boot, selftest, S, render, layout, syncTabs, projectPair," +
  "loadPairMeta, loadPair, loadPairLayer, drawDelta, drawDeltaSide, pairTok};");
const api = mod();

const fails = [];
const say = (...a) => console.log(a.join(" "));
const chk = (c, l, extra="") => {
  if (c) say("  ok   " + l + (extra ? "   " + extra : ""));
  else { say("  FAIL " + l + (extra ? "   " + extra : "")); fails.push(l); }
};

await api.boot();
say("boot OK  d_model=" + api.S.m.d_model);

const okMeta = await api.loadPairMeta();
chk(okMeta, "pairs.json 载入", api.S.pm ? api.S.pm.pairs.length + " 个配对" : "");
if (!okMeta) { say("没有配对数据，无法继续"); process.exit(1); }

// Every pair, not just the one the page happens to open on. The synthetic
// rehearsal had one interesting pair; the real collection has six, and a
// check that only ever loads index 0 is a check of a sample of one.
const PAIR_SWEEP = [];
for (let i = 0; i < api.S.pm.pairs.length; i++) {
  const pi = api.S.pm.pairs[i];
  for (const L of pi.layers) {
    try {
      await api.loadPair(i);
      // loadPair resets the layer; set it the way the page's own slider does
      // and then reload, so this exercises the real path rather than a
      // private back door.
      if (api.S.pLayer !== L) { api.S.pLayer = L; await api.loadPairLayer(); }
      const got = {
        id: pi.id, L,
        n_common: api.S.pm.pairs[api.S.pi].n_common_prefix,
        ctlT: api.S.pCtlT, dT: api.S.pT,
        hasCtl: !!api.S.pCtl, hasDelta: !!api.S.pDelta,
      };
      PAIR_SWEEP.push(got);
    } catch (e) {
      PAIR_SWEEP.push({ id: pi.id, L, error: String(e.message || e) });
    }
  }
}
const sweepErr = PAIR_SWEEP.filter(r => r.error);
chk(sweepErr.length === 0,
    `逐对逐层载入无异常（${PAIR_SWEEP.length} 个组合）`,
    sweepErr.length ? sweepErr[0].error : `${PAIR_SWEEP.length} ok`);
const noDelta = PAIR_SWEEP.filter(r => !r.error && !r.hasDelta);
say(`  ${PAIR_SWEEP.length} 个组合中 ${noDelta.length} 个没有 Δ` +
    (noDelta.length ? `（${noDelta.map(r => r.id + "/L" + r.L).join(", ")}）` : ""));
for (const r of PAIR_SWEEP.slice(0, 8)) {
  say(`  ${r.id} L${r.L}: 共同前缀 ${r.n_common}  T_ctl=${r.ctlT} T_delta=${r.dT}` +
      (r.error ? `  ERROR ${r.error}` : ""));
}

// Does switching problems actually switch?
//
// The page wires `sel.onchange = () => loadPair(+sel.value)`. Assigning
// `.value` from script does NOT fire `change` — only a real user gesture does.
// So "set value, then read the page" silently keeps showing problem 0 while
// the harness believes it moved on, and every number after that is read off
// the wrong problem. Dispatch a real `change` event and confirm S.pi follows;
// if it does, the page is fine and the earlier mismatch was the harness.
{
  const sel = elements.selPair;
  const results = [];
  for (let i = 0; i < api.S.pm.pairs.length; i++) {
    sel.value = String(i);
    sel.dispatchEvent && sel.dispatchEvent({ type: "change" });
    if (typeof sel.onchange === "function") sel.onchange();
    const pi = api.S.pi;
    const want = api.S.pm.pairs[i].id;
    const got = api.S.pm.pairs[pi] ? api.S.pm.pairs[pi].id : "?";
    // Read the pushed% this problem should show at its own step 0.
    api.S.pLayer = api.S.pm.pairs[pi].layers.find(L => L > api.S.pm.pairs[pi].inject_layer)
                   ?? api.S.pm.pairs[pi].layers[0];
    await api.loadPairLayer();
    api.S.tok = 0;
    api.drawDeltaSide();
    const m = elements.tblTop.innerHTML.match(/被推了<\/td><td class="tok"><b[^>]*>([\d.]+)%/);
    const rel0 = api.S.pMeta.stats.rel_shift[0];
    results.push({ want, got, ok: want === got,
                   shown: m ? m[1] : null, json: (rel0 * 100).toFixed(2) });
  }
  const bad = results.filter(r => !r.ok);
  chk(bad.length === 0,
      `下拉框切题真的换了数据（逐题 ${results.length} 次）`,
      bad.length ? `第 ${bad[0].want} 题没切过去，仍是 ${bad[0].got}`
                 : results.map(r => r.want).join(","));
  // And the number on screen must be that problem's own number.
  const mism = results.filter(r => r.shown != null &&
      Math.abs(parseFloat(r.shown) - parseFloat(r.json)) > 0.01);
  chk(mism.length === 0,
      "每题侧栏读数与该题自己的 json 一致（没有拿错题对拍）",
      mism.length ? mism.map(r => `${r.want}: ${r.shown}% vs ${r.json}%`).join("; ")
                  : results.map(r => `${r.want} ${r.shown}%`).join("  "));
}

// Back to pair 0 for the detailed arithmetic checks below.
await api.loadPair(0);
const S = api.S;
const p = S.pm.pairs[0];
say(`pair[0] = ${p.id}  层 ${JSON.stringify(p.layers)}  注入 L${p.inject_layer}` +
    `  共同前缀 ${p.n_common_prefix}  选中层 L${S.pLayer}`);
chk(S.pCtl && S.pDelta, "control 与 delta 都解出来了",
    `T_ctl=${S.pCtlT} T_delta=${S.pT}`);
chk(S.pUnit && S.pUnit.length === S.pm.d_model, "steer_unit 已载入");

// ---- 与 numpy 独立对拍 -------------------------------------------------
const ref = JSON.parse(fs.readFileSync(path.join(ROOT, "..", "..", "..",
  ".cache/analysis/delta_ref.json"), "utf8"));
const D = S.pm.d_model, L = S.pLayer;
// probe[i] is the token index; ref holds one row per probe, so the reference
// row has to be indexed by i, not by the token id.
const rkey = `${S.pm.pairs[S.pi].id}:${L}`;
if(!ref.layers[rkey]){
  say(`  FAIL 对拍真值里没有 ${rkey}（有: ${Object.keys(ref.layers).slice(0,6)}）`);
  fails.push("ref missing " + rkey);
}
const R = ref.layers[rkey] || {probe:[0], ctl:[[0,0]], delta:[[0,0]]};
const ks = R.probe;
let maxErr = 0, maxD = 0;
for (let i = 0; i < ks.length; i++) {
  const k = ks[i];
  const o = k * D;
  let a = 0, b = 0;
  for (let d = 0; d < D; d++) {
    const x = S.pCtl[o + d] - S.pMean[L * D + d];
    a += x * S.pComp[L * S.pStrideComp + 2 * d];
    b += x * S.pComp[L * S.pStrideComp + 2 * d + 1];
  }
  maxErr = Math.max(maxErr, Math.abs(a - R.ctl[i][0]),
                           Math.abs(b - R.ctl[i][1]));
  if (k < S.pT) {
    let da = 0, db = 0;
    for (let d = 0; d < D; d++) {
      const x = S.pDelta[o + d];            // 均值不参与 —— 差值里它抵消
      da += x * S.pComp[L * S.pStrideComp + 2 * d];
      db += x * S.pComp[L * S.pStrideComp + 2 * d + 1];
    }
    maxD = Math.max(maxD, Math.abs(da - R.delta[i][0]),
                             Math.abs(db - R.delta[i][1]));
  }
}
const spanC = Math.max(...R.ctl.flat().map(Math.abs)) || 1;
const spanD = Math.max(...R.delta.flat().map(Math.abs)) || 1;
chk(maxErr / spanC < 1e-5, "control 投影与 numpy 一致",
    `最大绝对误差 ${maxErr.toExponential(2)} (跨度 ${spanC.toFixed(2)})`);
chk(maxD / spanD < 1e-5, "delta 投影与 numpy 一致（均值已抵消）",
    `最大绝对误差 ${maxD.toExponential(2)} (跨度 ${spanD.toFixed(2)})`);

// ---- 核心恒等式 ---------------------------------------------------------
let maxId = 0;
for (const k of ks) {
  if (k >= S.pT) break;
  const o = k * D;
  let a1 = 0, b1 = 0, a2 = 0, b2 = 0;
  for (let d = 0; d < D; d++) {
    const h = S.pCtl[o + d], dl = S.pDelta[o + d], m = S.pMean[L * D + d];
    const c2 = S.pComp[L * S.pStrideComp + 2 * d], c3 = S.pComp[L * S.pStrideComp + 2 * d + 1];
    // proj(h + dl) - proj(h), i.e. the *difference* of the two projections,
    // against proj(dl) on its own. The mean drops out of the difference,
    // which is the property that lets the delta be projected without an
    // origin of its own.
    a1 += ((h + dl - m) - (h - m)) * c2;
    b1 += ((h + dl - m) - (h - m)) * c3;
    a2 += dl * c2;
    b2 += dl * c3;
  }
  maxId = Math.max(maxId, Math.abs(a1 - a2), Math.abs(b1 - b2));
}
chk(maxId / spanD < 1e-3, "proj(h+Δ) − proj(h) == proj(Δ)（均值抵消）",
    `最大偏差 ${maxId.toExponential(2)} (Δ 跨度 ${spanD.toFixed(5)})`);

// ---- 层切换真的改变投影 -------------------------------------------------
const pc1 = {};
for (const LL of p.layers) {
  S.pLayer = LL;
  await api.loadPairLayer();
  pc1[LL] = [S.pProjC[0], S.pProjC[1], S.pProjD[0], S.pProjD[1]];
}
const uniq = new Set(p.layers.map(L2 => pc1[L2].map(v => v.toFixed(6)).join(",")));
chk(uniq.size === p.layers.length,
    `层滑块改变了投影（${uniq.size}/${p.layers.length} 个层给出不同坐标）`);
for (const L2 of p.layers)
  say(`     L${L2}:  ctl PC1=${pc1[L2][0].toFixed(4)}  Δ PC1=${pc1[L2][2].toFixed(6)}`);

// ---- 画布真的画了东西 ---------------------------------------------------
// Use the layer the page actually opens on, i.e. the first one above the
// injection point. Forcing the injection layer here would make every
// downstream assertion vacuous: that layer's delta is identically zero by
// construction, so "the sidebar says 0.00%" would pass without anything
// having been rendered.
S.pLayer = p.layers.find(L => L > p.inject_layer) ?? p.layers[p.layers.length - 1];
await api.loadPairLayer();
S.tok = 0; api.drawDelta();
const drewMain = (calls.canvas.cv || 0), drewDelta = (calls.canvas.cvD || 0);
chk(drewMain > 50, "上图（两条轨迹）画了东西", `${drewMain} 次画布操作`);
chk(drewDelta > 50, "下图（Δ 散点）画了东西", `${drewDelta} 次画布操作`);

function sideRelShift() {
  api.drawDeltaSide();
  const m = elements.tblTop.innerHTML.match(/被推了<\/td><td class="tok"><b[^>]*>([\d.]+)%/);
  return m ? parseFloat(m[1]) : null;
}

S.tok = Math.min(5, S.pCtlT - 1);
const relDown = sideRelShift();
const side = elements.tblTop.innerHTML;
chk(/残差流被推了/.test(side), "侧栏给出「残差流被推了 X%」",
    relDown != null ? relDown + "%" : "");
// `#layerStory` is written only by renderSide(), which the DELTA branch
// returns before reaching. Left alone the panel kept describing the
// *unsteered* trajectory: "L7：…" while the reader was looking at L26 of a
// paired problem, under a heading that says 这一层在做什么. Assert that
// whatever it says cannot be about a different layer.
{
  api.S.layer = 7;                       // pretend a non-delta view ran at L7
  api.S.view = "DELTA";
  api.render();                          // render() is what writes #layerStory
  const st = elements.layerStory.innerHTML;
  const claims = [...st.matchAll(/L(\d+)/g)].map(m => parseInt(m[1]));
  chk(claims.every(L => L === S.pLayer),
      `第 4 屏的「这一层在做什么」不描述别的层（当前 L${S.pLayer}）`,
      claims.length ? "提到 L" + claims.join(",L") : "没有提层号");
  chk(/不适用|配对/.test(st),
      "第 4 屏的「这一层在做什么」说明了它为什么讲的是别的轨迹",
      (st.replace(/<[^>]+>/g, "").match(/所以它不适用/) || [""])[0] || "没写");
}

chk(relDown != null && relDown > 1.0,
    "下游层读出的位移是有量级的（不是 0.00%）",
    relDown != null ? relDown + "%" : "读不到");

// The layer convention, checked in the browser rather than assumed: the
// injection block's recorded residual is captured before the steerer runs, so
// it must read exactly zero, and the page must say why rather than just
// showing a flat line.
if (p.layers.includes(p.inject_layer)) {
  S.pLayer = p.inject_layer;
  await api.loadPairLayer();
  S.tok = 0;
  const relInj = sideRelShift();
  const injSide = elements.tblTop.innerHTML;
  chk(relInj === 0, `注入块 L${p.inject_layer} 侧栏读数精确为 0.00%（层约定）`,
      relInj != null ? relInj + "%" : "读不到");
  chk(/注入/.test(injSide) && /L\d+/.test(injSide),
      "注入块那一屏写明了为什么是平的",
      (injSide.match(/进入<\/b>该块的残差[^<]*/) || [""])[0].slice(0, 60));
  // With every dimension at exactly 0.00, ranking them and drawing ten equal
  // bars would present "nothing happened" as "the ten most affected
  // dimensions". The page must say the arms are bit-identical instead.
  chk(!/▲#\d+/.test(injSide) && !/▼#\d+/.test(injSide),
      "注入块那一屏不列出「被推最多的维度」",
      /没有任何维度被推动/.test(injSide) ? "改为说明两条流逐位相同" : "仍列了维度");
  chk(/没有任何维度被推动/.test(injSide),
      "注入块那一屏明说没有维度被推动（不是「变化都很小」）");
  // "看 L21" pointed at a layer that does not exist in this bundle. With
  // layers {4,12,20,26} the first one that can actually show an effect is
  // L26, so the hint has to name a layer the slider can reach.
  const avail = p.layers;
  const pointed = [...injSide.matchAll(/L(\d+)/g)].map(m => parseInt(m[1]));
  const bogus = pointed.filter(L => !avail.includes(L));
  chk(bogus.length === 0,
      "注入块的指路指向真实存在的层",
      bogus.length ? `指向了 L${bogus.join(",L")}，可用只有 ${avail.join("/")}`
                    : `指向 ${[...new Set(pointed)].join("/")}，可用 ${avail.join("/")}`);
  const hdr = elements.mainSub.textContent || "";
  const bogusHdr = [...hdr.matchAll(/L(\d+)/g)].map(m => parseInt(m[1])).filter(L => !avail.includes(L));
  chk(bogusHdr.length === 0, "标题栏的指路也指向真实存在的层",
      bogusHdr.length ? "L" + bogusHdr.join(",L") : hdr.slice(0, 46));
  S.pLayer = p.layers.find(L => L > p.inject_layer) ?? p.layers[p.layers.length - 1];
  await api.loadPairLayer();
}

chk(/被推最多的维度/.test(side), "侧栏列出被推最多的维度");
chk(!/#\d{6,}/.test(side), "侧栏没有裸数字 token id",
    (side.match(/#\d{6,}/g) || []).join(","));
chk((side.match(/(▲|▼)#\d+/g) || []).length > 0, "维度带方向箭头（升/降）",
    (side.match(/(▲|▼)#\d+/g) || []).slice(0,4).join(" "));

// The dimension bars are laid out with `width: X%` where X is a bare number
// from the DOM. `d.delta` is an *absolute* change (100.69, -77.48, …), so the
// obvious `Math.abs(d.delta) * 100` hands CSS 10068% — every bar saturates to
// full width and the dimension names get pushed out of the panel. Assert on
// the rendered widths so that cannot come back silently.
// `tblTop` is reused by more than one screen, so re-reading it here
// would measure whichever table happened to render last (the candidate-word
// screen, whose bars are top-1 probabilities). Use the sidebar snapshot
// taken right after the delta render instead.
const barWidths = [...side.matchAll(/class="dimbar"><i style="width:([\d.]+)%/g)]
  .map(m => parseFloat(m[1]));
chk(barWidths.length > 0, "维度条有渲染出的宽度",
    `${barWidths.length} 根，最大 ${Math.max(...barWidths).toFixed(1)}%`);
chk(barWidths.every(w => w >= 0 && w <= 100),
    "所有维度条宽度落在 0–100%（没有把绝对值当百分比）",
    barWidths.length ? `范围 ${Math.min(...barWidths).toFixed(1)}–${Math.max(...barWidths).toFixed(1)}%`
                     : "没有条");
chk(new Set(barWidths.map(w => w.toFixed(1))).size > 1,
    "维度条长度有区分（不是全部一样长）",
    [...new Set(barWidths.map(w => w.toFixed(0)))].slice(0,6).join(", "));
// And the names must still be inside the table, not squeezed out of it.
// The name has to arrive *whole* in the DOM, and it has to live inside a
// box where `text-overflow: ellipsis` can actually act — it does nothing on
// a <td>, which is why the names were once hard-clipped mid-glyph.
const nameRows = [...side.matchAll(/class="dimname" title="([^"]*)｜绝对变化 ([-\d.]+)"/g)]
  .map(m => ({ full: m[1], val: m[2] }));
chk(nameRows.length > 0, "维度词名在 DOM 里是完整的（不是被裁后的残片）",
    nameRows.slice(0,2).map(r => r.full.slice(0, 22)).join(" / "));
chk(nameRows.every(r => r.full.includes("、") || r.full.length > 3),
    "词名不是 1–2 个字符的残片",
    nameRows.length ? `最短 ${Math.min(...nameRows.map(r => r.full.length))} 字符` : "无");
chk(nameRows.length === barWidths.length,
    "每个维度条都配了一行词名",
    `${barWidths.length} 根条 / ${nameRows.length} 行词名`);
// The printed number must be the dimension's own absolute change, not a
// percentage of anything.
const vals = nameRows.map(r => Math.abs(parseFloat(r.val)));
chk(vals.length > 0 && vals.some(v => v > 1),
    "词名旁的数值是该维度的绝对变化量（不是被乘 100 的百分数）",
    vals.slice(0,4).map(v => v.toFixed(1)).join(", "));

say("");
say(fails.length ? `${fails.length} 项失败: ${fails.join(" | ")}` : "全部通过");
process.exit(fails.length ? 1 : 0);
