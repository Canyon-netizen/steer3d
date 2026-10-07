"use client";

/**
 * HingePanel —「模型在推理中途动摇的位置」。
 *
 * 数据：`/latent/data/hinge_hinges.json`（由 `.cache/mutbak/build_hinge_artifact.py`
 * 从 `.cache/xcheck/hinge_points.py` 的判据产物 + 逐层 lens + 探针读数生成）。
 *
 * ⚠⚠ 这个面板存在的理由是**换掉一个已被证伪的说法**。
 *   上一版页面/产物里「推理中途某个数算错了」那一支（P0），逐条人工读原文后
 *   **14/14 全是抽取器假阳性**：真算错 0 条。更致命的是 19 条答案错的轨迹里
 *   **12 条抽取器零判错**，人工读那些收尾，错因是误解题意 / 假设错 /
 *   算术对但推理链断 ⇒ **1.7B 的错误主要不在算术层**。
 *   所以这个面板展示的是**另一类位置**：模型**自己说**「我可能错了」的地方。
 *
 * ⚠ 诚实边界必须跟着数字一起显示（不是折叠起来的小字）：
 *   · 探针测的是**可分性**，不是**知识**；
 *   · 本轮**没有干预**，所以不是**因果**；
 *   · `h(t-1)` 仍在同一上下文里，「提前」只是「在写下标记词之前」的字面意思；
 *   · 分数随负例的语义差异变化（Δ=20 时 0.993 vs Δ=1 时 0.986）。
 *   这些写在 `caveats` 字段里，由产物携带 —— 页面只负责把它们显示出来。
 */

import { useEffect, useMemo, useState } from "react";

interface HingeStep {
  tok: number;
  cls: "A" | "B";
  sentence: string;
  audited: "true_hinge" | "false_positive" | "needs_human";
  audited_note: string;
  first_layer_correct: number | null;
  n_layers_correct: number;
  monotone: boolean;
  real_margin: number;
  decidable: boolean;
  anchor_ok: boolean;
  final_id: number;
}

interface HingeTraj {
  trajectory_id: string;
  n: number;
  hinges: HingeStep[];
}

interface HingeArtifact {
  schema: string;
  title: string;
  what_this_is: string;
  n_hinges: number;
  n_traces: number;
  n_audited: number;
  audit_accuracy: number | null;
  audit_note: string;
  why_not_arithmetic: string;
  per_step_field_doc: Record<string, string>;
  probe: {
    question: string;
    design: string;
    auroc_before_marker: Record<string, number>;
    auroc_null_controls: Record<string, number>;
    verdict: string;
    p4_提前可读: boolean;
    p5_不是纯位置效应: boolean;
  };
  caveats: string[];
  trajectories: HingeTraj[];
}

const CLS_LABEL: Record<string, string> = {
  A: "自查（Let me check again / Wait, no）",
  B: "自疑（maybe I made a mistake）",
};

function firstLayerTone(h: HingeStep): { text: string; cls: string } {
  // ⚠ 分档文案必须与产物里的口径一致：first_layer_correct 测的是
  //   **token 身份何时定型**，不是「知道什么」。所以这里只描述深浅，
  //   不断言任何关于「知道」的结论。
  const f = h.first_layer_correct;
  if (f == null) return { text: "未读出", cls: "text-gray-500" };
  if (f <= 6) return { text: `L${f}（很浅）`, cls: "text-emerald-400" };
  if (f <= 15) return { text: `L${f}`, cls: "text-sky-400" };
  if (f <= 23) return { text: `L${f}（深）`, cls: "text-amber-400" };
  return { text: `L${f}（最深的几层）`, cls: "text-orange-400" };
}

export default function HingePanel() {
  const [data, setData] = useState<HingeArtifact | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [trajId, setTrajId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/latent/data/hinge_hinges.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j: HingeArtifact) => {
        if (!alive) return;
        setData(j);
        if (j.trajectories?.length) setTrajId(j.trajectories[0].trajectory_id);
      })
      .catch((e) => alive && setErr(String(e.message || e)));
    return () => {
      alive = false;
    };
  }, []);

  const traj = useMemo(
    () => data?.trajectories.find((t) => t.trajectory_id === trajId) ?? null,
    [data, trajId],
  );

  const header = (
    <div className="flex items-baseline gap-2 flex-wrap">
      <h3 className="text-[11px] font-semibold text-gray-200">
        {data?.title ?? "模型在推理中途动摇的位置"}
      </h3>
      {data && (
        <span className="text-[9px] text-gray-500 font-mono">
          {data.n_hinges} 处 / {data.n_traces} 条录制
        </span>
      )}
    </div>
  );

  if (err) {
    return (
      <div
        className="rounded bg-bg/40 border border-border p-3"
        data-hinge="error"
      >
        {header}
        <p className="text-[10px] text-red-400 leading-relaxed mt-1">
          hinge_hinges.json unavailable: {err}
        </p>
      </div>
    );
  }

  if (!data) {
    return (
      <div
        className="rounded bg-bg/40 border border-border p-3"
        data-hinge="loading"
      >
        {header}
        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
          Loading the hinge positions…
        </p>
      </div>
    );
  }

  const p = data.probe;
  const off1 = p.auroc_before_marker["off1_标记词尚未写出"];
  const off0 = p.auroc_before_marker["off0_已写下标记词"];
  const nullMax = Math.max(...Object.values(p.auroc_null_controls));

  return (
    <div className="rounded bg-bg/40 border border-border p-3 text-gray-300"
         data-hinge="ready">
      {header}

      <p className="text-[10px] leading-relaxed mt-1.5 text-gray-400">
        {data.what_this_is}
      </p>

      {/* —— 这一段是「为什么不是算错」：本页之前那个说法已被证伪 ——
          ⚠ 措辞上**不用**「算错了的位置」这个字面串。它在本段里是
          **被否定的对象**（「为什么不是…」），但读者快速扫过时很容易
          只捕到那六个字 —— 判据 H8 第一版就是这么误报的：纯字符串匹配
          分不清肯定与否定。改成不复用被否定说法本身的措辞。 */}
      <details className="mt-2" data-hinge="why">
        <summary className="text-[10px] text-amber-400/90 cursor-pointer">
          为什么不是「用算式两边对不上找错」那一支
        </summary>
        <p className="text-[10px] leading-relaxed mt-1 text-gray-400">
          {data.why_not_arithmetic}
        </p>
      </details>

      {/* —— 探针读数 —— */}
      <div className="mt-2 rounded bg-bg/30 border border-border p-2"
           data-hinge="probe">
        <p className="text-[10px] text-gray-300 font-semibold">
          {p.question}
        </p>
        <p className="text-[9px] leading-relaxed mt-1 text-gray-500">
          {p.design}
        </p>
        <table className="mt-1.5 w-full text-[10px] font-mono">
          <tbody>
            <tr data-hinge-row="off0">
              <td className="text-gray-400 py-0.5 pr-2">
                标记词已写出之后
              </td>
              <td className="text-right text-gray-300">
                AUROC {off0.toFixed(3)}
              </td>
            </tr>
            <tr data-hinge-row="off1">
              <td className="text-gray-300 py-0.5 pr-2 font-semibold">
                标记词尚未写出之前
              </td>
              <td className="text-right text-emerald-400 font-semibold">
                AUROC {off1.toFixed(3)}
              </td>
            </tr>
            <tr data-hinge-row="null">
              <td className="text-gray-500 py-0.5 pr-2">
                随机位置对照
              </td>
              <td className="text-right text-gray-500">
                {nullMax.toFixed(3)}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="text-[9px] leading-relaxed mt-1.5 text-gray-400"
           data-hinge="probe-verdict">
          判决：{p.verdict === "PASS" ? "通过" : "不成立"}
          （提前可读 {p.p4_提前可读 ? "✓" : "✗"} ·
          不是纯位置效应 {p.p5_不是纯位置效应 ? "✓" : "✗"}）
        </p>
      </div>

      {/* —— 诚实边界：必须与数字**同屏**，不许默认折叠 ——
          ⚠ 第一版写的是 `<details open={open} onToggle=…>`，判据 H3 判红：
          React 在挂载后会用 state（初值 false）把 open 覆盖回去，
          于是页面上一上来是**折着的** —— 而这正是本项目栽过的那类
          （「解释藏在用户不会点开的地方」）。现在用 uncontrolled
          `<details open>`：默认展开，且用户可以自己折。
      */}
      <details className="mt-2" data-hinge="caveats" open>
        <summary className="text-[10px] text-gray-400 cursor-pointer">
          这组读数不能说明什么（{data.caveats.length} 条）
        </summary>
        <ul className="list-disc ml-4 mt-1 space-y-0.5">
          {data.caveats.map((c, i) => (
            <li key={i} className="text-[9px] leading-relaxed text-gray-500">
              {c}
            </li>
          ))}
        </ul>
      </details>

      {/* —— 逐条 —— */}
      <div className="mt-2 flex items-center gap-2" data-hinge="picker">
        <select
          value={trajId ?? ""}
          onChange={(e) => setTrajId(e.target.value)}
          className="flex-1 bg-bg/60 border border-border rounded text-[10px] px-1 py-0.5"
          data-hinge-traj
          aria-label="pick a recording"
        >
          {data.trajectories.map((t) => (
            <option key={t.trajectory_id} value={t.trajectory_id}>
              {t.trajectory_id.replace("aime__", "").replace("__think", "")} ·{" "}
              {t.n} 处
            </option>
          ))}
        </select>
      </div>

      <p className="text-[9px] text-gray-500 mt-1" data-hinge="audit">
        {data.audit_note}
      </p>

      {traj && (
        <ol className="mt-1.5 space-y-1 max-h-72 overflow-y-auto"
            data-hinge-list>
          {traj.hinges.map((h) => {
            const tone = firstLayerTone(h);
            return (
              <li key={h.tok}
                  className="rounded bg-bg/30 border border-border p-1.5"
                  data-hinge-item
                  data-hinge-tok={h.tok}
                  data-hinge-verdict={h.audited}
                  data-hinge-decidable={String(h.decidable)}
              >
                <div className="flex items-baseline gap-1.5 flex-wrap">
                  <span className="text-[9px] font-mono text-gray-500">
                    tok {h.tok}
                  </span>
                  <span className="text-[9px] font-mono text-gray-500">
                    类{h.cls}
                  </span>
                  <span className={`text-[9px] font-mono ${tone.cls}`}
                        data-hinge-first-layer>
                    首个定型层 {tone.text}
                  </span>
                  {h.decidable ? (
                    <span className="text-[9px] font-mono text-gray-600">
                      margin {h.real_margin.toFixed(2)}
                    </span>
                  ) : (
                    <span className="text-[9px] font-mono text-amber-600"
                          data-hinge-indecidable>
                      margin {h.real_margin.toFixed(2)}（不可判定）
                    </span>
                  )}
                </div>
                <p className="text-[10px] leading-snug mt-0.5 text-gray-200">
                  “{h.sentence}”
                </p>
                <p className="text-[9px] leading-relaxed mt-0.5 text-gray-500">
                  {h.audited === "true_hinge"
                    ? "人工读：真动摇。"
                    : h.audited === "false_positive"
                      ? "人工读：假阳性（抽取器抓错了片段）。"
                      : "尚未人工裁决。"}
                  {h.audited_note ? ` ${h.audited_note}` : ""}
                </p>
                {!h.decidable && (
                  <p className="text-[9px] leading-relaxed mt-0.5 text-amber-600">
                    ⚠ 这一步模型自己的 top1−top2 差只有{" "}
                    {h.real_margin.toFixed(2)}，float16 重建误差就能左右
                    结果 ⇒ 这一行的层号不可信。
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      )}

      <details className="mt-2" data-hinge="fielddoc">
        <summary className="text-[10px] text-gray-400 cursor-pointer">
          每个字段量的是什么
        </summary>
        <dl className="mt-1 space-y-0.5">
          {Object.entries(data.per_step_field_doc).map(([k, v]) => (
            <div key={k}>
              <dt className="text-[9px] font-mono text-gray-300">{k}</dt>
              <dd className="text-[9px] leading-relaxed text-gray-500">{v}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}
