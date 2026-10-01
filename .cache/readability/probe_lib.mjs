// 共用的页内探针：可见文本、布局溢出、横向越界。
//
// 这些函数**以真实 JS 源码**传给 Page.eval（走 Function#toString），不拼进
// 模板字符串。verify_final.mjs 曾经把 \d 写进模板字面量，JS 把它解析成字母 d，
// 浏览器里跑的其实是 /分叉点：第 (d+) 步/ —— 永不匹配，而且一直绿。要在本文件
// 里用正则，就正常写在函数体里（真实源码，转义是作者的责任，不是字符串拼接的
// 后果）。
//
// 可见性判据：一个文本"读者看得到"当且仅当同时满足
//   1. 所在元素有布局盒（getClientRects().length > 0，宽高都 ≥ 0.5px）
//   2. 自己与全部祖先：display !== 'none'、visibility !== 'hidden'、opacity ≥ .05
//   3. 不被任何 overflow:hidden/auto/scroll/clip 的祖先裁掉
//   4. 不被不透明浮层盖住：取自身中心点做 elementFromPoint，命中自己、自己的后代
//      或自己的祖先才算数。少了这一条，导读层打开时会把浮层**底下**的页面文字也算
//      进"首屏可见"，量到的是 DOM 顺序而不是读者视线。
//   5. 与视口有非空交集（whole=true 时跳过第 5 条，用于量"往下滚能读到"）
// 第 3 条是本项目真踩过的坑：199 字的警告在 DOM 里一字不差，而表格被撑到
// 613px 塞进 294px 面板，每行都在半个词处被切，末尾 38px 完全看不见 ——
// "在 DOM 里"和"读者看得到"是两件事。

/** 中心点是否真的露在外面（没被浮层盖住）。 */
export function occluded(el) {
  const r = el.getBoundingClientRect();
  const cx = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 1);
  const cy = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 1);
  const hit = document.elementFromPoint(cx, cy);
  if (!hit) return true;
  return !(el.contains(hit) || hit.contains(el));
}

/** 可见文本块，按 DOM 顺序（本页是三列 grid，DOM 顺序 = 阅读顺序）。 */
export function collectVisible(opts) {
  const o = opts || {};
  const whole = !!o.whole;
  const vw = window.innerWidth, vh = window.innerHeight;
  const SKIP_TAG = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'HEAD', 'CANVAS']);
  // 数据载荷与调试件不计入"说明性可见文本"：题面、生成文本、候选词表、tooltip
  const SKIP_ID = new Set(['probText', 'genTxt', 'tblTop', 'dbg', 'tip', 'loading']);
  const CTX = '#orientBody .gitem, #orientBody .ex > div, #orientBody .noitem, ' +
              '#orientBody li, #orientBody p, #orientBody .olead, ' +
              '#orientBody h1, #orientBody h2, #app .panel, #app .col';

  // 注意：下面两个辅助函数在**函数体内部**定义，不引用模块作用域。它们是以
  // Function#toString 的源码送进浏览器的，模块里的另一个函数在那边并不存在 ——
  // 踩过一次：collectVisible 调 occluded，浏览器直接 ReferenceError。
  function isOccluded(el) {
    const r = el.getBoundingClientRect();
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 1);
    const hit = document.elementFromPoint(cx, cy);
    if (!hit) return true;
    return !(el.contains(hit) || hit.contains(el));
  }

  function shown(el) {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      if (parseFloat(cs.opacity) < 0.05) return false;
      // whole=true 量的是"往下滚能读到什么"，所以跳过裁剪判据：被滚动容器裁在
      // 折线以下不等于丢失，读者滚一下就到了。横向裁剪另有 horizontalBleed 盯着。
      if (!whole && n !== el &&
          /hidden|auto|scroll|clip/.test(cs.overflowX + ' ' + cs.overflowY)) {
        const a = n.getBoundingClientRect(), b = el.getBoundingClientRect();
        if (b.right > a.right + 0.5 || b.bottom > a.bottom + 0.5 ||
            b.left < a.left - 0.5 || b.top < a.top - 0.5) return false;
      }
    }
    return true;
  }

  const out = [];
  const root = o.root ? document.querySelector(o.root) : document.body;
  if (!root) return { blocks: [], vw, vh };
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const t = (node.nodeValue || '').replace(/\s+/g, ' ').trim();
      if (!t) return NodeFilter.FILTER_REJECT;
      const el = node.parentElement;
      if (!el || SKIP_TAG.has(el.tagName)) return NodeFilter.FILTER_REJECT;
      for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
        if ((n.id && SKIP_ID.has(n.id)) ||
            (n.classList && n.classList.contains('hide'))) return NodeFilter.FILTER_REJECT;
      }
      if (!el.getClientRects().length) return NodeFilter.FILTER_REJECT;
      const r = el.getBoundingClientRect();
      if (r.width < 0.5 || r.height < 0.5) return NodeFilter.FILTER_REJECT;
      if (!whole && (r.bottom <= 0 || r.top >= vh || r.right <= 0 || r.left >= vw))
        return NodeFilter.FILTER_REJECT;
      if (!shown(el)) return NodeFilter.FILTER_REJECT;
      if (!whole && isOccluded(el)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let i = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement, r = el.getBoundingClientRect();
    const ctx = el.closest(CTX);
    out.push({
      i: i++,
      text: n.nodeValue.replace(/\s+/g, ' ').trim(),
      sel: el.tagName.toLowerCase() +
        (el.id ? '#' + el.id : '') +
        (el.className && typeof el.className === 'string'
          ? '.' + el.className.trim().split(/\s+/).join('.') : ''),
      x: Math.round(r.left), y: Math.round(r.top),
      // 说明容器文本：判"就地解释"用。**必须用 innerText 而不是 textContent**：
      // textContent 会把 display:none 的后代一起算进来，于是 #pairRow（默认隐藏）
      // 里那句"每一步被推了多远"会被当成"左栏面板解释了位移"——隐藏的解释等于没有
      // 解释，正是这个任务要防的那类假绿。
      ctx: ctx ? (ctx.innerText || ctx.textContent || '').replace(/\s+/g, ' ').trim() : '',
      ctxSel: ctx ? (typeof ctx.className === 'string' && ctx.className
                    ? ctx.className.split(/\s+/)[0] : ctx.tagName.toLowerCase()) : '',
      gitemTerm: ctx && ctx.classList.contains('gitem') ? (ctx.getAttribute('data-term') || '') : '',
      inOrient: !!el.closest('#orientation'),
    });
  }
  return { blocks: out, vw, vh, dpr: window.devicePixelRatio };
}

/** 某个选择器当前是不是"读者看得到"（几何 + 裁剪 + 遮挡三重判据）。 */
export function probeVisible(sel) {
  const el = document.querySelector(sel);
  if (!el) return { found: false };
  // 自包含：不能引用模块作用域的 occluded（浏览器里不存在）
  const isOccluded = e => {
    const r = e.getBoundingClientRect();
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 1);
    const hit = document.elementFromPoint(cx, cy);
    if (!hit) return true;
    return !(e.contains(hit) || hit.contains(e));
  };
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const inView = r.bottom > 0 && r.top < window.innerHeight &&
                 r.right > 0 && r.left < window.innerWidth;
  const fullRect = r.top >= -0.5 && r.left >= -0.5 &&
                   r.bottom <= window.innerHeight + 0.5 && r.right <= window.innerWidth + 0.5;
  let clipped = null;
  for (let n = el.parentElement; n; n = n.parentElement) {
    const p = getComputedStyle(n);
    if (/hidden|auto|scroll|clip/.test(p.overflowX + ' ' + p.overflowY)) {
      const a = n.getBoundingClientRect();
      if (r.right > a.right + 0.5 || r.bottom > a.bottom + 0.5 ||
          r.left < a.left - 0.5 || r.top < a.top - 0.5) {
        clipped = { by: n.tagName.toLowerCase() + (n.id ? '#' + n.id : ''),
                    cutRight: Math.round(r.right - a.right),
                    cutBottom: Math.round(r.bottom - a.bottom) };
        break;
      }
    }
  }
  return {
    found: true, display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
    hasHideClass: el.classList.contains('hide'),
    rect: { x: Math.round(r.left), y: Math.round(r.top),
            w: Math.round(r.width), h: Math.round(r.height) },
    inView, fullRect, clipped, occluded: isOccluded(el),
    // 纵向溢出：文案比容器高多少。文案在 DOM 里 ≠ 读者看得到。
    vOver: el.scrollHeight - el.clientHeight,
    text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120),
  };
}

/** 每个 panel/col 的纵向溢出与相对父容器的横向越界。 */
export function layoutOverflow(sel) {
  const rows = [];
  document.querySelectorAll(sel).forEach(el => {
    const r = el.getBoundingClientRect();
    const p = el.parentElement ? el.parentElement.getBoundingClientRect() : null;
    rows.push({
      sel: el.tagName.toLowerCase() +
        (el.id ? '#' + el.id : '') +
        (el.className && typeof el.className === 'string'
          ? '.' + el.className.trim().split(/\s+/)[0] : ''),
      vScroll: el.scrollHeight, vClient: el.clientHeight,
      vOver: el.scrollHeight - el.clientHeight,
      hScroll: el.scrollWidth, hClient: el.clientWidth,
      hOverSelf: el.scrollWidth - el.clientWidth,
      hOverVsParent: p ? Math.round(r.right - p.right) : 0,
      top: Math.round(r.top), left: Math.round(r.left),
      w: Math.round(r.width), h: Math.round(r.height),
    });
  });
  return rows;
}

/** 横向越界总览：元素右边界超出最近的裁剪/滚动祖先右边界。 */
export function horizontalBleed() {
  const bad = [];
  document.querySelectorAll('body *').forEach(el => {
    if (['SCRIPT', 'STYLE', 'CANVAS'].includes(el.tagName)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return;
    for (let p = el.parentElement; p; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (/hidden|auto|scroll|clip/.test(cs.overflowX + ' ' + cs.overflowY)) {
        const a = p.getBoundingClientRect();
        const dRight = Math.round(r.right - a.right);
        if (dRight > 1) bad.push({
          sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
               (el.className && typeof el.className === 'string'
                 ? '.' + el.className.trim().split(/\s+/)[0] : ''),
          cutRightPx: dRight, elRight: Math.round(r.right), ancRight: Math.round(a.right),
          text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 50),
        });
        break;
      }
    }
  });
  return bad;
}

/** 页面级纵向溢出：导读层是 fixed 浮层，不允许把 body 撑出滚动条。 */
export function pageOverflow() {
  const d = document.documentElement;
  return {
    vOver: d.scrollHeight - d.clientHeight,
    hOver: d.scrollWidth - d.clientWidth,
    bodyVOver: document.body.scrollHeight - document.body.clientHeight,
    bodyHOver: document.body.scrollWidth - document.body.clientWidth,
    clientW: d.clientWidth, clientH: d.clientHeight,
  };
}

/** 说明性文字（量句长用），排除数据载荷。导读层自己的散文也算在内。 */
export function collectExplanatory() {
  const SEL = 'h1,h2,.sub,.note,.legend,button,label,.stat,' +
              '#orientBody .ex > div,#orientBody .gitem,#orientBody .noitem,#orientBody li';
  const SKIP = new Set(['probText', 'genTxt', 'tblTop']);
  const out = [];
  document.querySelectorAll(SEL).forEach(el => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement)
      if (n.id && SKIP.has(n.id)) return;
    const inOrient = !!el.closest('#orientBody');
    const t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    if (t) out.push({
      sel: (inOrient ? '#orientBody ' : '') + el.tagName.toLowerCase() +
           (el.id ? '#' + el.id : '') +
           (el.className && typeof el.className === 'string'
             ? '.' + el.className.trim().split(/\s+/)[0] : ''),
      inOrient,
      text: t,
    });
  });
  return out;
}

/** 导读层的结构化读数，供断言用。 */
export function readOrientationStruct() {
  const q = s => document.querySelector(s);
  const items = [...document.querySelectorAll('#orientBody .gitem')].map(el => ({
    term: el.getAttribute('data-term') || '',
    gterm: (el.querySelector('.gterm') || {}).textContent || '',
    plain: ((el.querySelector('.plain') || {}).textContent || '').replace(/\s+/g, ' ').trim(),
    where: ((el.querySelector('.where') || {}).textContent || '').replace(/\s+/g, ' ').trim(),
  }));
  const no = [...document.querySelectorAll('#orientBody .noitem')].map(el =>
    el.textContent.replace(/\s+/g, ' ').trim());
  const ex = [...document.querySelectorAll('#orientBody .ex > div')].map(el =>
    el.textContent.replace(/\s+/g, ' ').trim());
  return {
    title: (q('#orientTitle') || {}).textContent || '',
    lead: ((q('.olead') || {}).textContent || '').replace(/\s+/g, ' ').trim(),
    items, no, ex,
    footButtons: [...document.querySelectorAll('#orientFoot button')].map(b => b.textContent.trim()),
  };
}
