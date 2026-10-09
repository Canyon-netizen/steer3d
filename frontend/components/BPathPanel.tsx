"use client";

/**
 * B 路干预面板：把「学一个方向去抬 \\boxed 标记 token」的结果摆出来。
 *
 * ## 它是什么，不是什么
 *
 * **是**：一组实测读数 —— 可读性（静态）、装置符号基准（干预）、
 *   剂量-位置扫描、层剖面，外加它们与既有八级证据阶梯的对应。
 * **不是**：关于模型内部机制的理论。它回答的是
 * 「在本项目这一条臂上，哪些话有证据、哪些没有」。
 *
 * ## 为什么数字必须来自 `bpath_marker_steering.json` 而不是写死在这里
 *
 * 这一条路的代价是实测出来的：三个坐标错误（token 位置、索引基数、**层**）
 * 让 `w` 训在错的空间里，**三次都不报错**，而所有 class_gap / 正负打分差 /
 * w·U 数字都「看起来正常」。手打数字会把同一个错再抄一遍且无从发现。
 * 所以数字由 `.cache/bpath/build_bpath_evidence.py` 从五份产物里**读**出来，
 * 它不新增任何数字，只做汇总。
 *
 * ## 这一块刻意不做的事
 *
 * 不把 P9 画成「差一点就到了」。P9 是 1/3，且 think 上剂量响应 0/2 单调 ——
 * 阶梯的价值恰恰在于它**留白**。
 *
 * ## 一句话结论（面板标题下面那行）
 *
 * **可读性 ≠ 可控性。** `w·U[marker] > 0` 一次前向都不用；
 * 「注入后剂量响应稳定单调」必须真跑模型、逐位置逐剂量地测。
 * `no_think` 上二者同时成立；`think` 上可读性成立而可控性不成立。
 */

import { useEffect, useState } from "react";

type LadderRow = { level: string; claim: string; bpath_state: string; here: string; note: string };
type DoseTraj = {
  traj: string; mode: string; n_pos: number; pos: number[];
  dose: number[];
  // ⚠ 这些键名里的 `+` 在 TS 里是运算符，**必须**加引号。
  // 漏一个就是 TS1131，不是运行时报错，是整份文件解析失败。
  "w+_median": number[]; "w-_median": number[];
  "w+_monotone_up": boolean; "w-_monotone_down": boolean;
};
type ByMode = {
  n_traj: number;
  "n_w+_monotone_up": number; "n_w-_monotone_down": number;
  "w+_small_dose_median": Record<string, number>;
};
type BPath = {
  schema: string; arm: string; selfcheck: string;
  // ⚠ 产物里这两个是**分开的两个键**（`selfcheck_passed` 布尔 + `selfcheck` 串）。
  // 类型只声明了串，那个布尔就没人读 —— 而它恰好是「这批数字自检过没有」的唯一开关。
  selfcheck_passed: boolean;
  the_one_line: string;
  coordinates: {
    layer_block: number; npz_layer: number; pos_offset: number;
    note: string; guards: string[];
  };
  readability_static: {
    arith_mean: number; freq_weighted: number;
    n_ids_positive: number; n_ids: number; freq_total: number;
    per_id: Record<string, { dot: number; freq: number; share: number }>;
    neg_in_high_freq: string[]; caveat: string;
  };
  p9_device_benchmark: {
    n_pass: number; n: number; has_random_arm: boolean;
    why_not_rand_floor: string;
    rows: { traj: string; mode: string; ok: boolean; why: string[];
            "w+": (number | null)[]; "w-": (number | null)[];
            "rand@1.0": number | null }[];
  };
  dose_position_scan: {
    dose_ladder: number[];
    headline: string;
    by_mode: Record<string, ByMode>;
    per_traj: Record<string, DoseTraj>;
  };
  layer_profile: {
    layer_ladder: number[]; calibration: string; headline: string;
    // ⚠ `arm` / `arm_note` / `retracted` 是预登记修订 14 加的：
    // 这一块初版读的是**臂 A**的层扫描，与页面其余部分的臂 B 不是同一个 `w`，
    // 由此得出的「高估 43 倍」已撤回。三个字段把这件事**印在页面上**，
    // 否则读者看到的仍是被撤回的结论。
    arm: string; arm_note: string; retracted: string;
    rows: { traj: string; mode: string; by_layer: Record<string, number> }[];
  };
  // 预登记修订 15–18：正交度探针。这是本项目**第一条机制级反直觉结论**，
  // 且 H 在 no_think 上是「无法判定」而不是「证伪」——两者的措辞必须分开印。
  orthogonality: {
    what: string; prereg: string;
    hypothesis: string; headline: string; scale: string;
    q3: { no_think_above_noise: number; no_think_direction: string;
          no_think_rho: number; final: string; note: string };
    q4_caveat: string; scope: string;
    // ⚠ 预登记修订 22–23：独立复核**不支持**推广 ——
    // 「对齐度反向」是 p01_think 一条轨迹的局部性质。
    // 这段必须印在页面上，否则读者会把下面那些数字当成一般结论。
    scope_warning: string;
    generalization: {
      prereg: string; n_traj: number; excluded: string[];
      n_sites: number; n_above: number;
      g1: Record<string, unknown>; g3: Record<string, unknown>;
      g4: Record<string, unknown>; final: string;
    };
    /** 修订 26：每组补 `n_ctrl_ge`（该组里同范数随机方向动得更多或一样多的位点数）
     *  与 `verdict_note`（n<8 时按 §17.4 只作描述）。⚠ 只增字段，原字段未改。 */
    groups_think: Record<string, { n: number; median: number; frac_pos: number;
      n_ctrl_ge?: number; verdict_note?: string }>;
    groups_no_think: Record<string, { n: number; median: number; frac_pos: number;
      n_ctrl_ge?: number; verdict_note?: string }>;
    /** 修订 27：取样缺陷的判定（M1/M2/M3）。判据写死于修订 24，判定在修订 27。
     *  ⚠ 这段的用处是**撤回**「不具推广性」——它必须与 scope_warning 一起出现，
     *  否则读者只看到更正后的措辞，却拿不出支撑它的数。 */
    sampling_defect27?: {
      prereg: string; method_selfcheck: string;
      n_tracks: number; n_sites_total: number; n_hi_total: number;
      median: number; fresh_batch_frac: number;
      M1: { value: number; pass: boolean };
      M2: { rank: number; pass: boolean };
      M3_action: string; p01_rank_literal: number;
      p01_rank_true_value: number; p01_window_track: string;
      headline: string; debt: string;
    };
    /** 修订 26：三处取数口径不一致的披露（地板口径 / Q1 批次 / 对照臂比较）。
     *  **只披露，不替换任何已发布数字。** */
    caliber26?: {
      prereg: string; batch: string; q1_split: string;
      floor_published: number; floor_published_n: number;
      floor_same_slice: number; floor_same_slice_n: number;
      n_above_published: number; n_above_same_slice: number;
      note_floor: string; note_control: string; note_batch: string;
    };
  };
  ladder_mapping: LadderRow[];
  answerable: string[]; not_answerable: string[];
};

const STATE_TXT: Record<string, string> = {
  done: "有",
  partial: "部分",
  missing: "没有",
  evidence_against_naive_reading: "反例",
};
const STATE_CLS: Record<string, string> = {
  done: "text-emerald-300",
  partial: "text-amber-300",
  missing: "text-gray-500",
  evidence_against_naive_reading: "text-sky-300",
};
const MARK: Record<string, string> = {
  done: "✓", partial: "◐", missing: "—", evidence_against_naive_reading: "⊘",
};

/**
 * 把产物里的 `**粗体**` 标记渲染成 `<strong>`。
 *
 * ## 为什么在渲染侧做，而不是改构建器
 *
 * `bpath_marker_steering.json` 同时被 `docs/BPATH_MARKER_STEERING.md` 当 markdown 读，
 * 那边的 `**` 是有意义的。所以**不删产物里的标记**（删了文档就少一层强调），
 * 改为在渲染侧消费。
 *
 * ## 为什么不写正则
 *
 * 这些串里含 `⇒`、`×`、`≈`、全角括号与 `w·U[marker]`，没有一个含 `<` `>`，
 * 用 React 子节点渲染天然免掉 XSS；正则只需处理成对的 `**`，
 * 且**奇数个 `**` 时原样保留**（宁可露出标记，也不要悄悄吃掉半个强调）。
 */
function Em({ s }: { s: string }) {
  const parts = s.split("**");
  if (parts.length < 3) return <>{s}</>;
  return (
    <>
      {parts.map((p, i) => (i % 2 === 1 ? <strong key={i}>{p}</strong> : <span key={i}>{p}</span>))}
    </>
  );
}

/** 极简折线：只画形状，不引入图表依赖。 */
function Spark({ xs, ys, w = 108, h = 26 }: { xs: number[]; ys: number[]; w?: number; h?: number }) {
  if (!ys.length) return null;
  const lo = Math.min(...ys, 0), hi = Math.max(...ys, 0);
  const span = hi - lo || 1;
  const px = (i: number) => (xs.length <= 1 ? 0 : (i / (xs.length - 1)) * (w - 2) + 1);
  const py = (v: number) => h - 2 - ((v - lo) / span) * (h - 4);
  const zeroY = py(0);
  return (
    <svg width={w} height={h} className="overflow-visible">
      <line x1={1} y1={zeroY} x2={w - 1} y2={zeroY} stroke="#39414f" strokeWidth={0.6} />
      <polyline
        points={ys.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ")}
        fill="none" stroke="#7aa2c8" strokeWidth={1.3}
      />
      {ys.map((v, i) => (
        <circle key={i} cx={px(i)} cy={py(v)} r={1.4} fill="#c9d6e4" />
      ))}
    </svg>
  );
}

export default function BPathPanel() {
  const [d, setD] = useState<BPath | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/latent/data/bpath_marker_steering.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => { if (alive) setD(j); })
      .catch((e) => { if (alive) setErr(String(e.message || e)); });
    return () => { alive = false; };
  }, []);

  if (err) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3 text-[10px] text-red-300"
           data-bpath="error">
        B 路证据加载失败：{err}（还没跑 <code>build_bpath_evidence.py</code>）
      </div>
    );
  }
  if (!d) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3 text-[10px] text-gray-500"
           data-bpath="loading">
        载入 B 路干预证据…
      </div>
    );
  }

  const rs = d.readability_static;
  const p9 = d.p9_device_benchmark;
  const ds = d.dose_position_scan;
  const nt = ds.by_mode["no_think"], tk = ds.by_mode["think"];

  return (
    <div className="rounded bg-bg/40 border border-border p-3"
         data-bpath="ready" data-schema={d.schema} data-arm={d.arm}
         data-p9-pass={String(p9.n_pass)} data-p9-n={String(p9.n)}
         data-ids-positive={`${rs.n_ids_positive}/${rs.n_ids}`}
         data-nothink-mono={`${nt ? nt["n_w+_monotone_up"] : "?"}/${nt ? nt.n_traj : "?"}`}
         data-think-mono={`${tk ? tk["n_w+_monotone_up"] : "?"}/${tk ? tk.n_traj : "?"}`}
         data-freq-weighted={String(rs.freq_weighted)}
         data-layer-arm={d.layer_profile.arm}
         data-retracted={d.layer_profile.retracted ? "yes" : "no"}
         data-ortho-think-neg={String(
           (1 - (d.orthogonality.groups_think["w·ĥ>0"]?.frac_pos ?? 0)) * 100)}>
      <h2 className="text-[12px] font-semibold text-gray-200 mb-0.5">
        干预实验：可读性 ≠ 可控性
      </h2>
      <p className="text-[9.5px] text-sky-200 leading-relaxed mb-2"
         data-bpath="thesis">
        <strong>可读性</strong>是「这个方向指向目标 token」，
        纯静态、<strong>一次前向都不用</strong>；
        <strong>可控性</strong>是「注入后剂量响应稳定、单调、符号正确」，
        必须<strong>真跑模型、逐位置、逐剂量</strong>地测。
        这一块实测到的是：<strong>no_think 上二者同时成立，think 上可读性成立而可控性不成立</strong>
        （no_think 剂量单调 {nt ? `${nt["n_w+_monotone_up"]}/${nt.n_traj}` : "—"} 条轨迹，
        think {tk ? `${tk["n_w+_monotone_up"]}/${tk.n_traj}` : "—"} 条）。
        <span className="text-gray-400">
          所以 <strong>不能用 unembedding 对齐度替代因果响应验证</strong>。
        </span>
      </p>

      {/* ---- 可读性：逐 id 点积 × 语料频次 ---- */}
      <div className="mb-2" data-bpath-block="readability">
        <div className="text-[10px] text-gray-300 mb-1">
          可读性（静态）：w·U[marker] 频次加权 <strong>{rs.freq_weighted >= 0 ? "+" : ""}{rs.freq_weighted}</strong>
          ，{rs.n_ids_positive}/{rs.n_ids} 个 id 为正，
          语料共 {rs.freq_total} 次 marker
        </div>
        <div className="flex flex-col gap-0.5">
          {Object.entries(rs.per_id).map(([id, v]) => (
            <div key={id} className="flex items-center gap-1.5 text-[9px] px-1"
                 style={{ background: "#101722" }}
                 data-marker-id={id} data-dot={String(v.dot)} data-share={String(v.share)}>
              <span className="text-gray-500 w-14">id {id}</span>
              <span className="text-gray-400 w-14">
                {(v.share * 100).toFixed(1)}%
              </span>
              <span className={v.dot > 0 ? "text-emerald-300" : "text-rose-400"}>
                {v.dot >= 0 ? "+" : ""}{v.dot.toFixed(5)}
              </span>
              <span className="text-gray-600">
                {v.dot > 0 ? "→ 注入 +w 会抬它" : "→ 注入 +w 会压它"}
              </span>
            </div>
          ))}
        </div>
        <p className="text-[9px] text-gray-500 mt-1 leading-relaxed">
          <Em s={rs.caveat} />
        </p>
      </div>

      {/* ---- 剂量-位置扫描：本面板最关键的一张图 ---- */}
      <div className="mb-2" data-bpath-block="dose">
        <div className="text-[10px] text-gray-300 mb-1">
          可控性：剂量响应（w+ 中位，横轴 rel 剂量 {ds.dose_ladder.join(" / ")}）
        </div>
        <div className="flex flex-col gap-0.5">
          {Object.entries(ds.per_traj).map(([tid, t]) => (
            <div key={tid} className="flex items-center gap-2 px-1 py-0.5 text-[9px]"
                 style={{ background: "#101722" }}
                 data-dose-traj={tid} data-mode={t.mode}
                 data-wplus-mono={String(t["w+_monotone_up"])}
                 data-wminus-mono={String(t["w-_monotone_down"])}>
              <span className={t.mode === "think" ? "text-amber-300" : "text-gray-400"}>
                {t.mode === "think" ? "think" : "no_think"}
              </span>
              <span className="text-gray-500 w-28 truncate">{tid.split("__").slice(1).join("__")}</span>
              <Spark xs={ds.dose_ladder} ys={t["w+_median"]} />
              <span className="text-gray-500">w+</span>
              <Spark xs={ds.dose_ladder} ys={t["w-_median"]} />
              <span className="text-gray-500">w−</span>
              <span className={t["w+_monotone_up"] ? "text-emerald-300" : "text-rose-400"}>
                {t["w+_monotone_up"] ? "w+ 单调升" : "w+ 非单调"}
              </span>
            </div>
          ))}
        </div>
        <p className="text-[9px] text-amber-200 mt-1 leading-relaxed">
          <Em s={ds.headline} />
        </p>
      </div>

      {/* ---- 装置符号基准 ---- */}
      <div className="mb-2" data-bpath-block="p9">
        <div className="text-[10px] text-gray-300 mb-1">
          装置符号基准（P9）：<strong>{p9.n_pass}/{p9.n}</strong> 条通过
          {p9.has_random_arm ? "，带同剂量随机方向臂" : ""}
        </div>
        {p9.rows.map((r) => (
          <div key={r.traj} className="flex items-center gap-1.5 text-[9px] px-1"
               style={{ background: "#101722" }}
               data-p9-traj={r.traj} data-p9-ok={String(r.ok)}>
            <span className={r.ok ? "text-emerald-300" : "text-rose-400"}>{r.ok ? "✓" : "✗"}</span>
            <span className="text-gray-400 w-28 truncate">{r.traj.split("__").slice(1).join("__")}</span>
            <span className="text-gray-500">w+ {r["w+"][0]}→{r["w+"][1]}</span>
            <span className="text-gray-500">w− {r["w-"][0]}→{r["w-"][1]}</span>
            <span className="text-gray-600">随机 {r["rand@1.0"]}</span>
            {r.why.length > 0 && <span className="text-gray-500">（{r.why.join("；")}）</span>}
          </div>
        ))}
        <p className="text-[9px] text-gray-500 mt-1 leading-relaxed">
          <Em s={p9.why_not_rand_floor} />
        </p>
      </div>

      {/* ---- 层剖面：一阶预测在哪里成立、在哪里失效 ---- */}
      <div className="mb-2" data-bpath-block="layer">
        <div className="text-[10px] text-gray-300 mb-1">
          注入层剖面<span className="text-gray-500">（臂 {d.layer_profile.arm}）</span>
        </div>
        {/* ⚠ 撤回声明必须**印在页面上**，不能只躺在产物 JSON 里：
            初版这里印的是「高估约 43 倍」，而那条已按预登记修订 14 撤回。
            只在 JSON 留字段、页面不印，读者看到的仍是被撤回的结论。 */}
        <p className="text-[9px] text-amber-200/90 mb-1 leading-relaxed"
           data-bpath-retracted>
          ⚠ 已撤回：<Em s={d.layer_profile.retracted} />
        </p>
        <p className="text-[9px] text-gray-500 mb-1 leading-relaxed">
          <Em s={d.layer_profile.arm_note} />
        </p>
        {d.layer_profile.rows.map((r) => (
          <div key={r.traj} className="flex items-center gap-2 text-[9px] px-1 mb-0.5"
               style={{ background: "#101722" }}
               data-layer-traj={r.traj}>
            <span className="text-gray-500 w-28 truncate">{r.traj.split("__").slice(1).join("__")}</span>
            <Spark xs={d.layer_profile.layer_ladder} ys={Object.values(r.by_layer)} w={150} />
            <span className="text-gray-600">注入层 0…−1</span>
          </div>
        ))}
        <p className="text-[9px] text-sky-200 mt-1 leading-relaxed">
          <Em s={d.layer_profile.headline} />
        </p>
        <p className="text-[9px] text-gray-500 leading-relaxed">
          校准点：<Em s={d.layer_profile.calibration} />
        </p>
      </div>

      {/* ---- 正交度：为什么「对齐好」反而更糟 ---- */}
      <div className="mb-2" data-bpath-block="ortho">
        <div className="text-[10px] text-gray-300 mb-1">
          正交度探针<span className="text-gray-500">（{d.orthogonality.prereg}）</span>
        </div>
        {/* ⚠⚠ 适用范围警告必须在**数字之前**印：否则读者先看到
            「20/20 全负」再看到限定，顺序会让人把结论带走。 */}
        <p className="text-[9px] text-rose-200 mb-1 leading-relaxed"
           data-bpath-generalization="not-tested">
          <Em s={d.orthogonality.scope_warning} />
        </p>
        {/* 修订 27：支撑上面那句更正的实测。**紧跟其后**印，
            否则读者只看到措辞变了、拿不出为什么变。 */}
        {d.orthogonality.sampling_defect27 && (
          <div className="text-[9px] text-amber-200/90 mb-1 leading-relaxed"
               data-bpath-sampling="rev27"
               data-m1-pass={String(d.orthogonality.sampling_defect27.M1.pass)}
               data-m2-pass={String(d.orthogonality.sampling_defect27.M2.pass)}>
            <p><Em s={d.orthogonality.sampling_defect27.headline} /></p>
            <p className="text-gray-400">
              <Em s={d.orthogonality.sampling_defect27.method_selfcheck} />
            </p>
            <p className="text-gray-400"><Em s={d.orthogonality.sampling_defect27.debt} /></p>
          </div>
        )}
        <p className="text-[9px] text-gray-500 mb-1 leading-relaxed">
          曾提出的假设：<Em s={d.orthogonality.hypothesis} />
        </p>
        <div className="flex flex-col gap-0.5 mb-1">
          {(Object.entries(d.orthogonality.groups_think) as
            [string, { n: number; median: number; frac_pos: number;
              n_ctrl_ge?: number; verdict_note?: string }][]).map(
            ([lab, g]) => (
            <div key={lab} className="flex flex-col text-[9px] px-1 py-0.5"
                 style={{ background: "#101722" }}
                 data-ortho-group={lab} data-ortho-n={String(g.n)}
                 data-ortho-median={String(g.median)}
                 data-ortho-frac-pos={String(g.frac_pos)}
                 data-ortho-ctrl-ge={String(g.n_ctrl_ge ?? "")}>
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500 w-16">{lab}</span>
                <span className="text-gray-500 w-12">{g.n} 个</span>
                <span className={g.median > 0 ? "text-emerald-300" : "text-rose-400"}>
                  Δ 中位 {g.median >= 0 ? "+" : ""}{g.median.toFixed(4)}
                </span>
                <span className="text-gray-500">
                  {(g.frac_pos * 100).toFixed(0)}% 为正
                </span>
              </div>
              {/* 修订 26：`n<8` 的组必须自己说清「不作判决」，
                  并把「同一位点上对照臂动得更多」摆在读者眼前 ——
                  否则 n=1 的一行看起来和 n=20 一样有分量。 */}
              {g.n < 8 && (
                <div className="text-amber-300/90 mt-0.5">
                  ⚠ 样本不足 ⇒ 按 §17.4 第 3 条只作描述、不作判决
                  {g.n_ctrl_ge !== undefined && g.n_ctrl_ge > 0 &&
                    <>；该位点同范数随机方向动得<b>更多</b></>}
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="text-[9px] text-amber-200 mt-1 leading-relaxed">
          <Em s={d.orthogonality.headline} />
        </p>
        <p className="text-[9px] text-gray-400 mt-0.5 leading-relaxed">
          <Em s={d.orthogonality.scale} />
        </p>
        {/* 修订 26：三处口径不一致的披露。放在紧挨 Q1 那句的下面，
            否则读者会把「p=6.98e-05（179 位点批次）」和「10/40（494 位点批次）」
            当成同一份数据的两个说法。 */}
        {d.orthogonality.caliber26 && (
          <div className="text-[9px] text-amber-200/80 mt-1 leading-relaxed"
               data-bpath-caliber="rev26">
            <p><Em s={d.orthogonality.caliber26.note_control} /></p>
            <p className="text-gray-400"><Em s={d.orthogonality.caliber26.note_batch} /></p>
            <p className="text-gray-400"><Em s={d.orthogonality.caliber26.note_floor} /></p>
          </div>
        )}
        {/* Q3 的「无法判定」必须与 think 的「证伪」分开印：
            混在一起读起来就像「两边都测了、都反了」。 */}
        <p className="text-[9px] text-sky-200 mt-1 leading-relaxed"
           data-ortho-q3={d.orthogonality.q3.no_think_direction}>
          <Em s={d.orthogonality.q3.note} />
        </p>
        <p className="text-[9px] text-gray-500 mt-0.5 leading-relaxed">
          <Em s={d.orthogonality.q4_caveat} />
        </p>
        <p className="text-[9px] text-gray-500 mt-0.5 leading-relaxed">
          <Em s={d.orthogonality.scope} />
        </p>
      </div>

      {/* ---- 挂到八级阶梯上 ---- */}
      <div className="flex flex-col gap-1 mb-2" data-bpath-block="ladder">
        {d.ladder_mapping.map((r) => (
          <div key={r.level} className="px-1.5 py-1 rounded"
               style={{ background: "#101722", borderLeft: `2px solid ${
                 r.bpath_state === "done" ? "#3f8f6b"
                   : r.bpath_state === "partial" ? "#a8792e"
                     : r.bpath_state === "missing" ? "#39414f" : "#4a7fa5" }` }}
               data-bpath-rung={r.level} data-bpath-rung-state={r.bpath_state}>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-gray-500 w-6">{r.level}</span>
              <span className={STATE_CLS[r.bpath_state]}>
                {MARK[r.bpath_state]} {STATE_TXT[r.bpath_state]}
              </span>
              <span className="text-[10px] text-gray-300">{r.claim}</span>
            </div>
            <div className="text-[9px] text-gray-400 pl-7"><Em s={r.here} /></div>
            <div className="text-[9px] text-gray-500 pl-7 leading-relaxed"><Em s={r.note} /></div>
          </div>
        ))}
      </div>

      {/* ---- 坐标系：三条守卫，别只写在这里 ---- */}
      <div className="mb-2 text-[9px] text-gray-500 leading-relaxed" data-bpath-block="coords">
        <span className="text-gray-400">坐标系：</span>
        注入 block {d.coordinates.layer_block} 的<strong>输入</strong> = npz 第{" "}
        {d.coordinates.npz_layer} 层（不是 {d.coordinates.layer_block}）。
        守卫：{d.coordinates.guards.join("；")}。
        <br />
        <Em s={d.coordinates.note} />
        <div className="mt-0.5">
          一致性自检（{d.selfcheck_passed ? "本次全过" : "未过"}）：{d.selfcheck}。
        </div>
      </div>

      {/* ---- 能答 / 不能答 ---- */}
      <div className="flex flex-col gap-1" data-bpath-block="scope">
        <div className="text-[9.5px] text-emerald-200 leading-relaxed">
          <strong>能答：</strong>
          {d.answerable.map((s, i) => (<span key={i}>（{i + 1}）<Em s={s} /> </span>))}
        </div>
        <div className="text-[9.5px] text-rose-200 leading-relaxed">
          <strong>不能答：</strong>
          {d.not_answerable.map((s, i) => (<span key={i}>（{i + 1}）<Em s={s} /> </span>))}
        </div>
      </div>
    </div>
  );
}