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
};

const F = "/latent/data";

/** 从页面可见文案里取数字。 */
function num(s: string | null | undefined): number | null {
  if (!s) return null;
  const m = s.match(/-?\d+\.\d+|-?\d+/);
  return m ? Number(m[0]) : null;
}
function allNums(s: string | null | undefined): number[] {
  if (!s) return [];
  return (s.match(/-?\d+\.\d+|-?\d+/g) || []).map(Number);
}

/** 可见文案里必须**没有**某个数（用来抓「不该出现的数出现了」）。 */
const GONE: Array<[string, string, number]> = [
  // 3 条 INSIDE 轴的配对差都必须印出来；任何一个缺失都判红。
  ["reasoning", "reasoning", 0],
];

export default function VerifyRandomControl(): JSX.Element | null {
  const [txt, setTxt] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [sawPanel, setSawPanel] = useState(false);

  useEffect(() => {
    let alive = true;
    // ⚠⚠ 第一版在**挂载瞬间**抓一次 DOM。那一刻 RandomControlPanel 自己
    //   还在 fetch（`[data-rc="ok"]` 尚未渲染、limits 列表还是空的），
    //   于是判据读到 0 条限制并报 BAD —— 探针明明等了 12 s，是我判据抓早了。
    //   ⇒ 改成**轮询等面板真的渲染完**再抓，且把「等了多久」也报出来，
    //   这样「等不到」与「等到了但内容不对」是两种不同的红。
    const t0 = Date.now();
    const grab = () => {
      const ok = document.querySelector('[data-rc="ok"]');
      if (!ok) return false;
      setTxt(ok.textContent ?? "");
      setSawPanel(true);
      return true;
    };
    let waited = 0;
    const iv = window.setInterval(() => {
      if (!alive) return;
      waited += 250;
      if (grab() || waited >= 20000) {
        window.clearInterval(iv);
        if (!grab()) setResults(["BAD 面板 20 s 内没渲染出 [data-rc=ok]"]);
      }
    }, 250);

    Promise.all([
      fetch(`${F}/repetition_collapse.json`).then((r) => r.json() as Promise<RC>),
      fetch(`${F}/axis_generalisation.json`).then((r) => r.json() as Promise<AX>),
    ]).then(([c, a]) => {
      if (!alive) return;
      // ⚠⚠ 第二处同源问题：这里读的是 React state 里的 `txt`/`notes`，
      //   那是**闭包快照**，不随上面的轮询更新 ⇒ 面板后来渲染了也读不到。
      //   正确做法：在**这里**直接重读 DOM。
      const t = document.querySelector('[data-rc="ok"]')?.textContent ?? "";
      const lim = Array.from(document.querySelectorAll('[data-rc="limits"] li'))
        .map((n) => n.textContent ?? "");
      setTxt(t);
      const out: string[] = [];
      const push = (ok: boolean, m: string) => out.push(`${ok ? "ok" : "BAD"} ${m}`);

      // ① not_claimed 条数：页面印的条数必须与产物一致
      push(lim.length === c.not_claimed.length,
           `not_claimed 条数 页面 ${lim.length} vs 产物 ${c.not_claimed.length}`);

      // ② 9 个随机方向的中位数必须在页面上找得到（逐个）
      const r9 = c.random_direction_distribution;
      if (r9?.random_median_sorted) {
        const missing = r9.random_median_sorted.filter(
          (v: number) => !t.includes(v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "")));
        push(missing.length === 0,
             `9 个随机中位都在页面上，缺 ${missing.length} 个 ${JSON.stringify(missing)}`);
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

      // ⑦ **不该出现**的数：3 条 INSIDE 轴不得被印成 OUTSIDE
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

      if (alive) setResults(out);
    }).catch((e) => {
      if (alive) setResults([`BAD 抓产物失败: ${String(e)}`]);
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
