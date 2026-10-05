/** 判据：RandomControlPanel 的可见文案必须与产物一致（不是只查它存在）。 */
import { useEffect, useState } from "react";

type RC = {
  random_direction_distribution?: {
    random_median_sorted?: number[];
    named_median?: number;
    control_median?: number;
    grade?: string;
    decision_rule_fixed_before_data?: boolean;
  };
  not_claimed: string[];
  batches: Array<{ batch: string; n: number; rep_median: Record<string, number> }>;
};

type AX = {
  threshold_paired?: number;
  axes: Array<{ axis: string; axis_value: number; grade: string }>;
  verdict: string;
  per_problem_caveat?: {
    per_problem_null_max: Record<string, number>;
    n_axes_exceeding: number;
    n_axes: number;
  };
};

const F = "/latent/data";

/** occurrence_23.json：confidence +v 的发生率。 */
type OCC = {
  n_problems: number;
  prefix_words: number;
  full_text: { pos: number; p_two_sided: number; median_diff: number };
  fixed_prefix: {
    pos: number; p_two_sided: number; median_diff: number;
    wilson95: [number, number];
  };
  cap_censoring?: {
    cap_tokens: number; up_hit_cap: number; zero_hit_cap: number;
    n_problems: number;
    prefix_fraction_of_up_when_capped_median: number | null;
    collapse_position_in_new_rate_curve: number;
    length_ratio_vs_prefix_diff_pearson_r: number;
  };
  per_problem: Array<{ problem: string; d_pre: number }>;
};

/** 从页面可见文案里取数字。 */
function num(s: string | null | undefined): number | null {
  if (!s) return null;
  const m = s.match(/-?\d+\.\d+|-?\d+/);
  return m ? Number(m[0]) : null;
}

/** 可见文案里必须**没有**某个数（用来抓「不该出现的数出现了」）。 */
const GONE: Array<[string, string]> = [
  // reasoning 的配对差必须仍是 INSIDE，不得被误升为 OUTSIDE。
  ["reasoning", "reasoning"],
];

/**
 * 逐条核。**只在两个前提都成立之后被调一次**。
 *
 * ⚠⚠ 这一整块是从组件里搬出来的，原因见 useEffect 里的三处同源问题：
 *   它必须能「拿到当刻的 DOM 快照」并一次性判完，不能在中途被 React state
 *   的闭包快照污染。搬成纯函数之后，「读到什么」与「判出什么」分成两件事，
 *   也就好单独验。
 */
function runChecks(
  t: string,
  lim: string[],
  c: RC,
  a: AX,
  o: OCC | null,
): string[] {
  const out: string[] = [];
  const push = (ok: boolean, m: string) => out.push(`${ok ? "ok" : "BAD"} ${m}`);

  // ① not_claimed 条数：页面印的条数必须与产物一致
  push(lim.length === c.not_claimed.length,
       `not_claimed 条数 页面 ${lim.length} vs 产物 ${c.not_claimed.length}`);

  // ② 9 个随机方向的中位数必须在**可见文案**里找得到（逐个）
  //   ⚠ 这条真的红过：9 个数原先只写在每根柱子的 title= 里（悬停才出现），
  //     页面上读不到 ⇒ 读者没法核「命名臂高于全部 9 个」。
  const r9 = c.random_direction_distribution;
  if (r9?.random_median_sorted) {
    const missing = r9.random_median_sorted.filter(
      (v: number) => !t.includes(v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "")));
    push(missing.length === 0,
         `9 个随机中位都在可见文案里，缺 ${missing.length} 个 ${JSON.stringify(missing)}`);
    const nm = num(t.match(/命名轴[\s\S]{0,20}?(\d\.\d{4})/)?.[1]);
    push(nm === r9.named_median,
         `命名臂中位 页面 ${nm} vs 产物 ${r9.named_median}`);
  }

  // ③ 判决阈值必须在页面上
  if (a.threshold_paired != null) {
    const tv = num(t.match(/判决阈值[\s\S]{0,40}?(-?\d\.\d+)/)?.[1]);
    push(tv === a.threshold_paired,
         `阈值 页面 ${tv} vs 产物 ${a.threshold_paired}`);
  }

  // ④ 4 条轴的中位必须逐条印出
  for (const x of a.axes) {
    const v = num(t.match(new RegExp(`${x.axis}[\\s\\S]{0,40}?(-?\\d\\.\\d{4})`))?.[1]);
    push(v === x.axis_value,
         `${x.axis} 配对中位 页面 ${v} vs 产物 ${x.axis_value}`);
  }

  // ⑤ OUTSIDE 的轴数必须与「越过了它」那句一致
  const outside = a.axes.filter((x) => x.grade === "OUTSIDE");
  const said = t.match(/只有[\s\S]{0,20}?越过了它/);
  push(!!said, `「越过了它」那句在页面上 = ${!!said}`);
  push(outside.length >= 1,
       `OUTSIDE 轴数 = ${outside.length}（${outside.map((x) => x.axis).join(",")}）`);

  // ⑥ 32k 那批的题数必须印出，且与产物一致
  const b32 = c.batches.find((b) => /32k/.test(b.batch));
  if (b32) {
    const m = t.match(/32k 批[，,]?\s*(\d+)\s*题/);
    push(Number(m?.[1]) === b32.n, `32k 题数 页面 ${m?.[1]} vs 产物 ${b32.n}`);
  }

  // ⑦ **不该出现**的数：INSIDE 的轴不得被印成 OUTSIDE
  for (const [axis] of GONE) {
    const x = a.axes.find((y) => y.axis === axis);
    if (x) push(x.grade === "INSIDE", `${axis} 仍是 INSIDE（未被误升）`);
  }

  // ⑧ 全部 not_claimed 的关键措辞必须在页面上
  const key = ["两阶段", "发生率", "不能外推", "对标", "自信", "追溯"];
  for (const k of key) {
    const inPage = lim.some((n) => n.includes(k)) || t.includes(k);
    push(inPage, `限制里出现「${k}」= ${inPage}`);
  }

  // ⑨ 面板里三个**承载论证的散文块**必须真被读到，
  //    否则它们对覆盖扫描器就是「无归属块」—— 而它们不是装饰。
  for (const [mark, must] of [
    ["caliber", "范数效应"],
    ["mechanism-note", "塌到"],
    ["axes-note", "越过了它"],
  ] as Array<[string, string]>) {
    const el = document.querySelector(`[data-rc="${mark}"]`);
    const s = el?.textContent ?? "";
    push(!!el && s.includes(must),
         `[data-rc="${mark}"] 在页面上且含「${must}」= ${!!el && s.includes(must)}`);
  }

  // ⑩ **逐题反例必须印在页面上**（第三十五笔）。
  //    产物里那句「其余轴落在随机分布内」只在跨题中位层面成立；
  //    逐题看有 3/4 条轴在个别题上越过了该题零分布上界。
  //    ⇒ 产物记了、页面不印，等于对读者不存在。
  //    这一条查的是**页面上有没有那句限定**，不是查数对不对。
  const pp = a.per_problem_caveat;
  if (pp && pp.n_axes_exceeding > 0) {
    const el = document.querySelector('[data-rc="axes-pp-caveat"]');
    const s = el?.textContent ?? "";
    const elTok = !!el && s.includes("逐题看不是全干净");
    push(elTok,
         `[data-rc="axes-pp-caveat"] 印出了逐题反例限定 = ${elTok}`);
    // 三个上界数必须逐个印出来，否则读者仍看不到那三道题的门不一样高
    const miss = Object.entries(pp.per_problem_null_max)
      .filter(([p, v]) => !s.includes(p) || !s.includes(String(v)));
    push(miss.length === 0,
         `逐题零分布上界 ${pp.n_axes_exceeding}/${pp.n_axes} 都在页面上，`
         + `缺 ${miss.length} 个 ${JSON.stringify(miss.map(([p]) => p))}`);
    // 还要印「这不推翻判决」—— 否则读者会把 caveat 读成翻案
    push(s.includes("不推翻") || s.includes("可能是运气"),
         `caveat 同时印了「不推翻判决」= `
         + `${s.includes("不推翻") || s.includes("可能是运气")}`);
  }

  // ⑪ **发生率**：产物里有、面板没印 = 对读者不存在。
  //    而且这里只查**页面上找得到这些数**，不重算 —— 重算是第三层的事。
  // ⚠ `querySelector` 返回 `Element`，而 `innerText` 在 `HTMLElement` 上
  //   （第一版没写这个断言，tsc 判死 TS2339 —— 又一次是 tsc 在守边界）。
  const oEl = document.querySelector('[data-rc="occurrence"]') as HTMLElement | null;
  const oT = oEl?.innerText ?? "";
  // ⚠ 与 ⑫ 同一个洞：这一整块也可能被折起来或压根没渲染，
  //   而 `textContent` 仍是空串 ⇒ 下面的 includes 全 false ⇒ 会判红。
  //   但反过来，「DOM 里有块」也不能当「读者看得见」。
  //   ⇒ 先判**块本身可见**，再判内容。
  const oVis = !!oEl && oEl.getBoundingClientRect().height > 0;
  if (o) {
    push(oVis, `[data-rc="occurrence"] 块**可见**（高度>0）= ${oVis}`);
    const nd = oT.match(new RegExp(`${o.n_problems}`));
    push(!!nd && oT.includes(`${o.fixed_prefix.pos}/${o.n_problems}`),
         `发生率 定长前缀 ${o.fixed_prefix.pos}/${o.n_problems} 在页面上 = `
         + `${!!nd && oT.includes(`${o.fixed_prefix.pos}/${o.n_problems}`)}`);
    // ⚠ 两个口径都要印。只印全长那个 = 把「多长」说成「更重复」。
    push(oT.includes(String(o.full_text.median_diff))
         && oT.includes(String(o.fixed_prefix.median_diff)),
         `全长中位差 ${o.full_text.median_diff} 与定长 ${o.fixed_prefix.median_diff} 都印出 = `
         + `${oT.includes(String(o.full_text.median_diff)) && oT.includes(String(o.fixed_prefix.median_diff))}`);
    // 区间也要印：22/23 单看像「几乎必然」，区间才说得出「不排除偶然」
    const w = o.fixed_prefix.wilson95;
    push(oT.includes(String(w[0])) && oT.includes(String(w[1])),
         `Wilson 95% [${w[0]}, ${w[1]}] 印出 = `
         + `${oT.includes(String(w[0])) && oT.includes(String(w[1]))}`);
    // 逐题 n=1 这件事必须跟着数字一起出现
    push(oT.includes("n=1"),
         `「逐题 n=1（无重复测量）」跟着印出来了 = ${oT.includes("n=1")}`);
  } else {
    push(false, "occurrence_23.json 没取到 ⇒ 发生率那一块是空的");
  }

  // ⑫ 反例必须**真的看得见**，印出来。
  //    ⚠⚠ 第一版用 `textContent` 查它 ⇒ 判绿了。而那版把反例塞在
  //    **折叠的 `<details>`** 里：`textContent` 读得到、`innerText` 读不到，
  //    读者看到的是后者 ⇒ 22/23 的那 1 道反例对多数人是不可见的。
  //    「DOM 里有」不等于「印出来了」——
  //    与 latent 页「搬进 #extras 后默认视图里从来没渲染过」同源。
  //    ⇒ 查**可见性**（渲染高度 > 0），并用 innerText（读者读到的那个）。
  // ⚠ `as` 断言**必须和表达式同一行**。写成换行续写时 TSX 解析器会在
  //   `const cEl = document.querySelector(…)` 之后断句，把下一行的 `as`
  //   当成新语句的开头 ⇒ TS1434。第一次就踩了。
  const cEl: HTMLElement | null =
    document.querySelector('[data-rc="occurrence-counterexample"]');
  const cS = cEl?.innerText ?? "";
  const cVis = !!cEl && cEl.getBoundingClientRect().height > 0;
  if (o && o.per_problem.some((r) => r.d_pre <= 0)) {
    const miss = o.per_problem.filter((r) => r.d_pre <= 0)
      .filter((r) => !cS.includes(r.problem));
    push(cVis && miss.length === 0,
         `没出现的那道题**可见地**印在页面上 = ${cVis && miss.length === 0}`
         + (miss.length ? `，缺 ${JSON.stringify(miss.map((r) => r.problem))}` : "")
         + `（可见=${cVis}）`);
  }

  // ⑬ 截尾披露必须印出来。定长前缀那个中位差是**下界**，
  //    而「下界」这件事只存在于产物里、页面上没写 ⇒ 读者会当它是另一个估计值。
  const capEl = document.querySelector('[data-rc="occurrence-cap"]') as HTMLElement | null;
  const capS = capEl?.innerText ?? "";
  if (o?.cap_censoring) {
    const cc = o.cap_censoring;
    push(!!capEl && capEl.getBoundingClientRect().height > 0,
         `[data-rc="occurrence-cap"] 截尾披露可见 = `
         + `${!!capEl && capEl.getBoundingClientRect().height > 0}`);
    push(capS.includes(`${cc.up_hit_cap}/${cc.n_problems}`)
         && capS.includes(String(cc.zero_hit_cap)),
         `截尾计数 +v ${cc.up_hit_cap}/${cc.n_problems} 与零臂 ${cc.zero_hit_cap} 都印出 = `
         + `${capS.includes(`${cc.up_hit_cap}/${cc.n_problems}`) && capS.includes(String(cc.zero_hit_cap))}`);
    // ⚠「是下界」这三个字必须在页面上。只印数字不给定性，
    //   等于让读者自己猜那个数该怎么读 —— 而他多半会当成「另一个口径的值」。
    push(capS.includes("是下界"),
         `「是下界」这一定性印在页面上 = ${capS.includes("是下界")}`);
    push(capS.includes(String(cc.length_ratio_vs_prefix_diff_pearson_r)),
         `长度比与前缀配对差的 r=${cc.length_ratio_vs_prefix_diff_pearson_r} 印出 = `
         + `${capS.includes(String(cc.length_ratio_vs_prefix_diff_pearson_r))}`);
  }

  return out;
}

export default function VerifyRandomControl(): JSX.Element | null {
  const [results, setResults] = useState<string[]>([]);
  const [sawPanel, setSawPanel] = useState(false);

  useEffect(() => {
    let alive = true;
    // ⚠⚠ 三处同源问题，都在「读的是**当时的** DOM」这一件事上：
    //   ① 第一版在**挂载瞬间**抓一次。那一刻 RandomControlPanel 自己还在 fetch
    //      （`[data-rc="ok"]` 尚未渲染、limits 列表还是空的），
    //      于是判据读到 0 条限制并报 BAD —— 探针明明等了 12 s，是我判据抓早了。
    //   ② 第二版改成轮询，但**检查仍在 fetch 的 .then() 里**重读 DOM。
    //      fetch 常常**先于**面板自己的两个 fetch 完成 ⇒ 读到空串，
    //      21 条里 19 条变成「页面 null vs 产物 x」。
    //      实测：同一份代码上一轮只红 1 条、这一轮红 19 条 —— **纯时序侥幸**。
    //      会飘的判据比没有判据更糟：它的绿不携带信息。
    //   ③ 而读 React state 里的 `txt` 又是**闭包快照**，不随轮询更新。
    //
    // ⇒ 正确形状：**两个前提都成立之后，只判一次**。
    //   前提 A = 产物取到；前提 B = 面板真的渲染出 `[data-rc="ok"]`。
    //   哪个前提没成立，**分别**报出来 —— 「等不到」与「等到了但内容不对」
    //   是两种不同的红，混成一条就等于把装置故障说成页面有问题。
    let panelText: string | null = null;
    let limTexts: string[] = [];
    const grab = () => {
      const ok = document.querySelector('[data-rc="ok"]');
      if (!ok) return false;
      panelText = ok.textContent ?? "";
      limTexts = Array.from(document.querySelectorAll('[data-rc="limits"] li'))
        .map((n) => n.textContent ?? "");
      setSawPanel(true);
      return true;
    };

    let cc: RC | null = null;
    let aa: AX | null = null;
    let oo: OCC | null = null;
    let waited = 0;
    let judged = false;

    // ⚠⚠ 只有**轮询**能宣布「等不到」。fetch 完成时也调它，但那时
    //   panelText 往往还是 null —— 第一版在这里直接判「面板没渲染」，
    //   而那一刻才过了 ~1s，20 s 的预算根本没用上。
    //   ⇒ 前提没齐就 return（继续等），只有 20 s 到了才准下结论。
    //   「等不到」与「等到了但内容不对」是两种红，混成一条就把
    //   **时序**说成**页面有问题**。
    const tryJudge = () => {
      if (judged || !alive || !cc || !aa || !oo || !panelText) return;
      judged = true;
      window.clearInterval(iv);
      try {
        setResults(runChecks(panelText, limTexts, cc as RC, aa as AX, oo));
      } catch (e) {
        // ⚠ 判据自己抛了要说成**装置故障**，不能算页面的问题。
        setResults([`BAD 判据自己抛了（装置故障，不是页面有问题）: ${String(e)}`]);
      }
    };

    const giveUp = () => {
      if (judged || !alive) return;
      judged = true;
      window.clearInterval(iv);
      if (!cc || !aa || !oo) {
        setResults([`BAD 前提未建立：20 s 内产物没取到`
          + `（c=${!!cc} a=${!!aa} occ=${!!oo}）`]);
      } else if (!panelText) {
        setResults(["BAD 前提未建立：20 s 内面板没渲染出 [data-rc=ok]"]);
      }
    };

    const iv = window.setInterval(() => {
      if (!alive || judged) return;
      waited += 250;
      grab();
      tryJudge();
      if (!judged && waited >= 20000) giveUp();
    }, 250);

    Promise.all([
      fetch(`${F}/repetition_collapse.json`).then((r) => r.json() as Promise<RC>),
      fetch(`${F}/axis_generalisation.json`).then((r) => r.json() as Promise<AX>),
      // ⚠ 发生率这一份**也算前提**。它带着本面板最强的数（22/23），
      //   缺了它而其余照常显示，读者会以为「发生率没估」——
      //   实际是「估了但没送到」。⇒ 不取到就不判，不给「半份判决」。
      fetch(`${F}/occurrence_23.json`).then((r) => r.json() as Promise<OCC>),
    ]).then(([c, a, o]) => {
      if (!alive) return;
      cc = c;
      aa = a;
      oo = o;
      tryJudge();
    }).catch((e) => {
      if (alive && !judged) {
        judged = true;
        window.clearInterval(iv);
        setResults([`BAD 抓产物失败: ${String(e)}`]);
      }
    });
    return () => { alive = false; window.clearInterval(iv); };
  }, []);

  // ⚠ `results` 只装**判据结果**，不装被读的页面文本。
  //   第一版两者共用一个 state，于是 data-rc-verify-line 里出现的是
  //   not_claimed 原文（限制的正文），而不是 ok/BAD 的判定 ——
  //   探针读到会以为判据在复述限制，而不是在报判决。
  const bad = results.filter((n) => n.startsWith("BAD"));
  return (
    <div data-rc-verify={results.length === 0 ? "pending" : bad.length ? "BAD" : "ok"}
         data-rc-verify-n={results.length}
         data-rc-verify-bad={bad.length}
         data-rc-verify-saw-panel={sawPanel ? "yes" : "no"}
         className="hidden">
      {results.map((n, i) => <div key={i} data-rc-verify-line={n}>{n}</div>)}
    </div>
  );
}
