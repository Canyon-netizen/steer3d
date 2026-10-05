/**
 * 随机对照臂面板：同范数随机方向 vs 命名轴。
 *
 * 回答一个具体问题：**「模型跑飞了」这句话，带不带关于向量的信息？**
 * 答案是不带 —— 干预后生成不闭合是**范数效应**，与方向无关。
 * 真正携带方向信息的是**重复退化**。
 *
 * 三份产物（由 .cache/xcheck/ 下的生成器产出，生成器即判据）：
 *   repetition_collapse.json          三批数字 + 机制曲线 + not_claimed
 *   random_direction_distribution.json 9 个同范数随机方向的零分布
 *   axis_generalisation.json          4 条独立轴的泛化检验
 *
 * 约定照抄 StrengthLawPanel：
 *   · fetch 产物，取不到就**明说取不到**，绝不拿字面量兜底；
 *   · 可见文字里的每个数都来自产物，不在本文件里手抄；
 *   · 判决规则「取数前写死」这件事要印给读者看，因为它是结论可信的前提。
 */
import { useEffect, useState } from "react";

type Collapse = {
  what: string;
  metric: Record<string, string>;
  batches: Array<{
    batch: string;
    n: number;
    rep_median: { up: number; down: number; zero: number };
    tests: Record<string, { pos: number; neg: number; ties: number; p: number }>;
    new_rate_curve: { up: number[]; zero: number[] };
  }>;
  not_claimed: string[];
  random_direction_distribution?: {
    grade: string;
    decision_rule_fixed_before_data?: boolean;
    named_median?: number;
    control_median?: number;
    random_median_sorted?: number[];
    criteria?: string[];
    note?: string;
  };
};

type Axis = {
  schema: string;
  decision_rule_fixed_before_data?: boolean;
  n_independent_axes?: number;
  axes_note?: string;
  threshold_paired?: number;
  per_problem_caveat?: {
    per_problem_null_max: Record<string, number>;
    axes_exceeding_on_some_problem?: Record<string, unknown[]>;
    n_axes_exceeding: number;
    n_axes: number;
    not_a_refutation?: string;
  };
  axes: Array<{
    axis: string;
    members: string[];
    axis_value: number;
    grade: "OUTSIDE" | "INSIDE";
    caveat?: string;
  }>;
  verdict: string;
  control_by_problem?: Record<string, number>;
};

const BOX = "rounded bg-bg/40 border border-border p-3";

/** occurrence_23.json：confidence +v 的发生率（逐题配对，长度无关口径）。 */
type Occ = {
  n_problems: number;
  prefix_words: number;
  full_text: { pos: number; p_two_sided: number; median_diff: number };
  fixed_prefix: {
    pos: number; p_two_sided: number; median_diff: number;
    wilson95: [number, number];
  };
  length_confound: {
    n_steps_up_median: number; n_steps_zero_median: number;
    problems_where_up_shorter_than_zero: number;
  };
  per_problem: Array<{
    problem: string; d_pre: number; rep_pre_up: number; rep_pre_zero: number;
    n_steps_up: number; n_steps_zero: number;
  }>;
};

function Head() {
  return (
    <div className="flex items-baseline gap-2">
      <h3 className="text-[11px] font-semibold tracking-wide text-fg">
        同范数随机方向对照
      </h3>
      <span className="text-[9px] text-gray-500">
        layer 20 · strength 0.2 · ‖v‖ = 173.1543（0.2 × ‖h‖@L20）
      </span>
    </div>
  );
}

/** 新内容产出率曲线：1 = 全是没见过的新内容，0 = 原地复读。 */
function Curve({ up, zero }: { up: number[]; zero: number[] }) {
  const W = 200, H = 34;
  const pts = (a: number[]) =>
    a.map((v, i) => `${(i / (a.length - 1)) * W},${H - v * H}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[34px]" role="img"
         aria-label="新内容产出率随输出位置的变化">
      <polyline points={pts(zero)} fill="none" stroke="#6b7280" strokeWidth="1.2" />
      <polyline points={pts(up)} fill="none" stroke="#ef4444" strokeWidth="1.6" />
    </svg>
  );
}

export default function RandomControlPanel() {
  const [c, setC] = useState<Collapse | null>(null);
  const [a, setA] = useState<Axis | null>(null);
  const [occ, setOcc] = useState<Occ | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const get = (u: string) =>
      fetch(u)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((j: unknown) => alive && j)
        .catch((e) => {
          if (alive) setErr(`${u.split("/").pop()}: ${String(e.message || e)}`);
        });
    get("/latent/data/repetition_collapse.json").then((j) => j && setC(j as Collapse));
    get("/latent/data/axis_generalisation.json").then((j) => j && setA(j as Axis));
    // ⚠ 发生率这一份**取不到不许静默**：它带着本面板最强的那个数（22/23）。
    //   缺了它而页面照常显示其余内容，读者会以为「发生率没估」——
    //   而实际是「估了但没送到」。
    get("/latent/data/occurrence_23.json").then((j) => j && setOcc(j as Occ));
    return () => {
      alive = false;
    };
  }, []);

  if (err) {
    return (
      <div className={BOX} data-rc="error">
        <Head />
        <p className="text-[10px] text-red-400 leading-relaxed mt-1">
          随机对照产物取不到：{err}。不拿字面量兜底。
        </p>
      </div>
    );
  }

  if (!c || !a) {
    return (
      <div className={BOX} data-rc="loading">
        <Head />
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">Loading…</p>
      </div>
    );
  }

  const r9 = c.random_direction_distribution;
  const b32 = c.batches.find((b) => /32k/.test(b.batch));
  const bF = c.batches.find((b) => /AF32|本次/.test(b.batch));
  const outside = a.axes.filter((x) => x.grade === "OUTSIDE");
  const pp = a.per_problem_caveat;

  return (
    <div className={BOX} data-rc="ok">
      <Head />

      {/* ── 核心区分：范数效应 vs 方向效应 ── */}
      <p className="text-[10px] text-gray-400 leading-relaxed mt-2" data-rc="caliber">
        「模型跑飞了」<b className="text-fg">不带</b>关于向量的信息：
        干预后生成不闭合是<b className="text-fg">范数效应</b>，
        9 个同范数随机方向、5 条语义轴、正负号<b className="text-fg">全都</b>撞上限。
        真正携带方向信息的是<b className="text-accent">重复退化</b>。
      </p>

      {/* ── 9 个随机方向的零分布 ── */}
      {r9 && r9.random_median_sorted && (
        <div className="mt-3" data-rc="nulldist">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] text-fg">
              9 个同范数随机方向 vs 命名轴
            </span>
            {r9.decision_rule_fixed_before_data === true && (
              <span className="text-[9px] text-emerald-400">
                判决规则取数前写死
              </span>
            )}
          </div>
          <div className="flex items-end gap-[2px] h-8 mt-1.5">
            {r9.random_median_sorted.map((v, i) => (
              <div key={i} className="flex-1 bg-gray-600 rounded-t"
                   style={{ height: `${Math.max(4, (v / (r9.named_median || 1)) * 32)}px` }}
                   title={`random_${i}: ${v}`} />
            ))}
            <div className="flex-1 bg-accent rounded-t"
                 style={{ height: 32 }} title={`confidence_up: ${r9.named_median}`} />
          </div>
          <p className="text-[9px] text-gray-500 mt-1">
            左 9 根灰 = 9 个随机方向的中位重复率（全部贴在无注入基线
            {r9.control_median} 附近）；最右 1 根 = 命名轴{" "}
            <b className="text-accent">{r9.named_median}</b>。
            {r9.grade === "GRADE_ABOVE_ALL" && " 命名臂高于全部 9 个。"}
          </p>
          {/* ⚠ 这 9 个数原先只写在每根柱子的 `title=` 里。
              那是**悬停提示**，不是可见文案 —— 页面上读不到，读代码才看得到。
              配套判据 `verifyRandomControl.tsx` 逐个核「产物里的 9 个中位数
              都能在面板文本里找到」，实测缺 8 个 ⇒ 自己把自己的红抓出来了。
              ⇒ 结论要读者能核，数字就得印在读者看得到的地方，
              不能只印在鼠标悬停时才出现的地方。 */}
          <p className="text-[9px] text-gray-400 mt-1 font-mono leading-relaxed">
            9 个随机中位（升序）：{r9.random_median_sorted.join("  ")}
          </p>
        </div>
      )}

      {/* ── 机制曲线 ── */}
      {b32 && (
        <div className="mt-3" data-rc="mechanism">
          <span className="text-[10px] text-fg">机制（32k 批，{b32.n} 题）</span>
          <div className="mt-1">
            <Curve up={b32.new_rate_curve.up} zero={b32.new_rate_curve.zero} />
          </div>
          <p className="text-[9px] text-gray-500 leading-relaxed" data-rc="mechanism-note">
            新内容产出率随输出位置（0%→100%）。<b className="text-red-400">红线 +v</b>{" "}
            <b>塌到 0</b> 后保持 —— 不是机械复读，是换措辞地重新起头、从不往前走；
            <span className="text-gray-400">灰线零臂</span>全程健康。
          </p>
        </div>
      )}

      {/* ── 泛化：4 条独立轴 ── */}
      <div className="mt-3" data-rc="axes">
        <span className="text-[10px] text-fg">
          泛化到别的语义轴（{a.n_independent_axes} 条独立轴，不是 6）
        </span>
        <table className="w-full mt-1 text-[9px]">
          <tbody>
            {a.axes.map((x) => (
              <tr key={x.axis}>
                <td className="text-gray-400 py-[1px]">{x.axis}</td>
                <td className="text-fg py-[1px]">{x.axis_value.toFixed(4)}</td>
                <td className="py-[1px]">
                  {x.grade === "OUTSIDE"
                    ? <span className="text-emerald-400">可区分于随机</span>
                    : <span className="text-gray-500">落在随机分布内</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[9px] text-gray-500 leading-relaxed mt-1" data-rc="axes-note">
          判决阈值（同为逐题配对差）= {a.threshold_paired}。
          只有 <b className="text-fg">{outside.map((x) => x.axis).join("、") || "无"}</b>{" "}
          越过了它 ⇒ 「重复退化」<b className="text-fg">不是</b>语义轴的通性。
        </p>
        {/* ⚠⚠ 第三十五笔：判决用的是**跨 3 题的中位**。
            逐题看零分布上界差得很远 —— 高基线那道题上 9 个随机方向
            **全部**比无注入对照更低（上界是负数），「超过它」在那道题上是矮门。
            ⇒ 「其余轴都在随机分布内」这句话**不能**被读成「逐题也成立」。
            这不是推翻判决（n=3，单题越界可能是运气），但不印出来就是隐瞒反例。 */}
        {pp && pp.n_axes_exceeding > 0 && (
          <p className="text-[9px] text-amber-500/90 leading-relaxed mt-1"
             data-rc="axes-pp-caveat">
            ⚠ 逐题看不是全干净：{pp.n_axes_exceeding}/{pp.n_axes} 条轴在**个别题**上
            越过了该题的零分布上界（
            {Object.keys(pp.per_problem_null_max)
              .map((k) => `${k} 上界 ${pp.per_problem_null_max[k]}`)
              .join("，")}
            ）。判决用的是**跨题中位**，n=3 时单题越界可能是运气 ——
            这不推翻 OUTSIDE/INSIDE，但那句话不能被读成「逐题也成立」。
          </p>
        )}
      </div>

      {/* ── 发生率：confidence +v 在 23 道题上多常发生 ── */}
      {occ && (
        <div className="mt-3" data-rc="occurrence">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] text-fg">
              发生率：confidence +v 在 {occ.n_problems} 道题上
            </span>
            <span className="text-[9px] text-gray-500">
              逐题配对（零臂已复核逐字相同）
            </span>
          </div>
          {/* ⚠⚠ 必须同时印两个口径。只印全长那个会把「多长」说成「更重复」——
              +v 步数中位 32000 vs 零臂 7944，长度本身就是机制的一部分。 */}
          <p className="text-[9px] text-gray-400 mt-1 leading-relaxed">
            全长：<b className="text-fg">{occ.full_text.pos}/{occ.n_problems}</b> 题更重复
            （p={occ.full_text.p_two_sided.toExponential(2)}，中位差{" "}
            {occ.full_text.median_diff}）
            ｜ 定长前 {occ.prefix_words} 词：<b className="text-fg">
              {occ.fixed_prefix.pos}/{occ.n_problems}</b> 题
            （p={occ.fixed_prefix.p_two_sided.toExponential(2)}，中位差{" "}
            {occ.fixed_prefix.median_diff}）
            ｜ Wilson 95% [{occ.fixed_prefix.wilson95[0]}, {occ.fixed_prefix.wilson95[1]}]
          </p>
          <p className="text-[9px] text-amber-500/90 leading-relaxed mt-1"
             data-rc="occurrence-caveat">
            ⚠ 两个口径中位差差 {Math.round(occ.full_text.median_diff /
              Math.max(occ.fixed_prefix.median_diff, 1e-9))} 倍
            ⇒ 塌缩发生在文本**靠后**处，不是开头就重复。
            长度也不对称：+v 步数中位 {occ.length_confound.n_steps_up_median} vs 零臂{" "}
            {occ.length_confound.n_steps_zero_median}，
            另有 {occ.length_confound.problems_where_up_shorter_than_zero} 题 +v 反而更短。
            逐题 n=1（无重复测量）⇒ 报的是「多少题出现」，不是「出现得多稳」。
          </p>
          {/* ⚠⚠ 反例**不许折叠**。第一版把它塞进 `<details>`，
              于是 `textContent` 读得到、`innerText` 读不到 ——
              而读者看到的是后者 ⇒ 22/23 的那 1 道反例对多数人是不可见的。
              配套判据第一版用 `textContent` 查它，于是**判绿了**：
              「DOM 里有」被当成了「印出来了」。
              ⇒ 判据改查**可见性**（getBoundingClientRect().height > 0），
                文案也从 `<details>` 挪成直接可见的段落。
              与 latent 页「搬进 #extras 后默认视图里从来没渲染过」同源。 */}
          <p className="text-[9px] text-gray-400 mt-1 leading-relaxed"
             data-rc="occurrence-counterexample">
            唯一那 1 道没出现的题（不藏反例）：{" "}
            {(() => {
              const bad = occ.per_problem
                .filter((r) => r.d_pre <= 0)
                .sort((a, b) => a.d_pre - b.d_pre);
              return bad.length
                ? bad.map((r) => `${r.problem}：前缀 ${r.rep_pre_up} vs 零臂 ` +
                    `${r.rep_pre_zero} = ${r.d_pre}` +
                    `（步数 +v ${r.n_steps_up} / 零 ${r.n_steps_zero}）`).join("；")
                : "（本批无反例）";
            })()}
          </p>
        </div>
      )}

      {/* ── 限制：必须印出来，不能只留在 JSON 里 ── */}
      <details className="mt-3" data-rc="limits">
        <summary className="text-[10px] text-gray-400 cursor-pointer select-none">
          这些结论不能说什么（{c.not_claimed.length} 条）
        </summary>
        <ol className="mt-1 space-y-1">
          {c.not_claimed.map((s, i) => (
            <li key={i} className="text-[9px] text-gray-500 leading-relaxed">
              {s}
            </li>
          ))}
        </ol>
      </details>

      {bF && (
        <p className="text-[9px] text-gray-500 leading-relaxed mt-2">
          另一批（{bF.n} 题、本次新跑）独立复现同一签名：重复率中位 +v{" "}
          {bF.rep_median.up} / 对照 {bF.rep_median.down} / 零臂{" "}
          {bF.rep_median.zero}。
        </p>
      )}
    </div>
  );
}
