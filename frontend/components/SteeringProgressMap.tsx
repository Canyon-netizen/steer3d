"use client";

/**
 * 进度图面板 —— 这块是"这个页面现在能声称什么"的唯一出口。
 *
 * ## 它是什么
 *
 * 两张表：
 *  1. **证据阶梯 × 作用对象**：行 = L0–L7 + L2′，列 = 向量 / 层 / 单元组 / 单单元 / 高层语义变量。
 *  2. **阶段路线条** S0–S5：每一级的门禁状态与阻塞依赖。
 *
 * ## 它的数字必须来自产物
 *
 * 这里**不写死任何一个数字**。`steering_progress.json` 由
 * `backend/examples/build_circuit_landscape.py` 从磁盘上的产物生成：
 * L0–L7 的行来自 `evidence_ladder.json`，L2′ 与阶段门禁来自这次构建**真的产出了什么**。
 * 框架 §8.3 ⑨ 的规矩在这里是硬约束：一个写死在组件里的数字会静默过期，
 * 而**过期的进度图比没有进度图更坏** —— 它会让人以为"当前 = L4"是当前的量。
 *
 * ## 两条不能省的规矩（框架 §8.6 / §8.9）
 *
 * 1. **"未测"必须写成"未测"**，不能被读成 0。
 * 2. **"最高能声称"与"最高有数据"是两个量**，必须分开印。
 * 3. `needs` 解锁的是**本级**，不是下一级 —— "最便宜的下一级"是算出来的，不是抄来的
 *    （框架 §8.6 的第三条设计错误就是把它错位了一级）。
 */
import { useEffect, useState } from "react";
import type { CellState, Progress, ProgressRow, Stage } from "@/lib/steering-progress";

const MARK: Record<CellState, string> = { done: "✓", partial: "◐", missing: "未测" };
const MARK_CLS: Record<CellState, string> = {
  done: "text-emerald-300",
  partial: "text-amber-300",
  missing: "text-gray-500",
};
const STAGE_CLS: Record<Stage["state"], string> = {
  pass: "border-emerald-800/70 bg-emerald-950/40 text-emerald-200",
  fail: "border-rose-800/70 bg-rose-950/40 text-rose-200",
  locked: "border-slate-700 bg-slate-900/60 text-slate-400",
};
const STAGE_MARK: Record<Stage["state"], string> = { pass: "✓", fail: "✗", locked: "🔒" };

export default function SteeringProgressMap() {
  const [d, setD] = useState<Progress | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/latent/data/steering_progress.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Progress) => { if (alive) setD(j); })
      .catch((e) => { if (alive) setErr(String(e.message || e)); });
    return () => { alive = false; };
  }, []);

  if (err) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3 text-[10px] text-red-300"
           data-progress="error">
        进度图加载失败：{err}（还没跑 build_circuit_landscape.py）
      </div>
    );
  }
  if (!d) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3 text-[10px] text-gray-500"
           data-progress="loading">
        载入进度图…
      </div>
    );
  }

  const decision = d.readout_summary?.decision;
  const floor = d.readout_summary?.floor;
  const all = d.readout_summary?.all;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
         data-progress="ready"
         data-rows={String(d.rows.length)}
         data-stages={String(d.stages.length)}
         data-level-claimed={String(d.ladder_max_level_claimed ?? "")}
         data-level-with-data={String(d.ladder_max_level_with_data ?? "")}
         data-payload-bytes={String(d.guards?.payload_bytes ?? 0)}>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-white">进度图：这个页面现在能声称什么</h2>
          <p className="mt-1 text-[11px] leading-5 text-slate-500">
            行 = 证据阶梯，列 = 作用对象。数字全部由 <code>build_circuit_landscape.py</code> 从产物生成，
            组件里不写死任何一个数。
          </p>
        </div>
        {d.ladder_source && (
          <span className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-400">
            阶梯来源：{d.ladder_source}
          </span>
        )}
      </div>

      {/* ---- "最高能声称" 与 "最高有数据" 必须分开印 ---- */}
      {d.ladder_max_level_claimed && (
        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3"
             data-progress-levels="true">
          <p className="text-[11px] text-slate-300">
            <b>最高能声称 {d.ladder_max_level_claimed}</b>
            <span className="text-slate-500">，</span>
            <b className="text-amber-300">最高有数据 {d.ladder_max_level_with_data}</b>
          </p>
          {d.why_two_numbers && (
            <p className="mt-1 text-[10px] leading-5 text-slate-500">{d.why_two_numbers}</p>
          )}
        </div>
      )}

      {/* ---- 阶梯 × 作用对象 ---- */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-[10px]" data-progress-matrix="true">
          <thead>
            <tr className="border-b border-slate-800 text-slate-500">
              <th className="px-2 py-2 font-medium">级</th>
              {d.objects.map((o) => (
                <th key={o} className="px-2 py-2 font-medium">{o}</th>
              ))}
              <th className="px-2 py-2 font-medium">最便宜的下一级</th>
            </tr>
          </thead>
          <tbody>
            {d.rows.map((row: ProgressRow) => {
              // 下一级：优先取"向量"那一列的；没有就取这一行里任何一个非空的 next
              const next = row.cells?.["向量"]?.next
                || Object.values(row.cells || {}).map(c => c.next).find(Boolean)
                || "";
              return (
                <tr key={row.level} className="border-b border-slate-800/60 align-top"
                    data-progress-row={row.level} data-progress-row-state={row.state}>
                  <td className="px-2 py-2 font-mono text-slate-300">{row.level}</td>
                  {d.objects.map((o) => {
                    const cell = row.cells?.[o];
                    if (!cell) {
                      return (
                        <td key={o} className="px-2 py-2 text-slate-600"
                            data-progress-cell={`${row.level}|${o}`}
                            data-progress-cell-state="n-a"
                            title="该级不按此对象分级（不是 0）">
                          —
                        </td>
                      );
                    }
                    return (
                      <td key={o} className="px-2 py-2"
                          data-progress-cell={`${row.level}|${o}`}
                          data-progress-cell-state={cell.state}
                          data-progress-cell-next={cell.next}
                          title={`本级门禁：${cell.gate}\n最便宜的下一级：${cell.next}`}>
                        <span className={`font-mono ${MARK_CLS[cell.state]}`}>{MARK[cell.state]}</span>
                        <span className="ml-1 text-slate-500">{cell.here}</span>
                      </td>
                    );
                  })}
                  <td className="px-2 py-2 text-slate-500">{next || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] leading-5 text-slate-500">
        <b className="text-emerald-300">✓</b> 已成立且可引用 ·
        <b className="text-amber-300"> ◐</b> 有数据但不足以声称 ·
        <b className="text-gray-500"> 未测</b> 显式写成"未测"，不是 0 ·
        <span className="text-slate-600"> —</span> 该级不按此对象分级。
      </p>

      {/* ---- 阶段路线条 ---- */}
      <div className="mt-5">
        <h3 className="text-[12px] font-semibold text-slate-200">阶段路线</h3>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {d.stages.map((s) => (
            <div key={s.id} className={`rounded-xl border p-3 ${STAGE_CLS[s.state]}`}
                 data-progress-stage={s.id} data-progress-stage-state={s.state}>
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-[11px]">{s.id}</span>
                <span className="text-[12px] font-medium">{s.title}</span>
                <span className="ml-auto font-mono text-[11px]">{STAGE_MARK[s.state]}</span>
              </div>
              <p className="mt-1 text-[10px] leading-4 opacity-80">{s.goal}</p>
              <p className="mt-1 text-[10px] leading-4 opacity-70">门禁：{s.gate}</p>
              {s.blocks.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-[10px] leading-4 opacity-70">
                  {s.blocks.map((b) => <li key={b}>· {b}</li>)}
                </ul>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ---- 读数分带：两个 regime 绝不可混算 ---- */}
      {decision && (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/60 p-3"
             data-progress-readout="true">
          <p className="text-[11px] font-medium text-slate-300">读数分带（同一向量、同一相对剂量、同一读数）</p>
          <div className="mt-2 grid gap-2 text-[10px] sm:grid-cols-3">
            <div data-progress-band="decision">
              <b className="text-emerald-300">决策带</b>
              <span className="text-slate-500"> · {decision.n_sites} site</span>
              <div className="mt-1 font-mono text-slate-300">
                +v {decision.arms.plus.mean >= 0 ? "+" : ""}{decision.arms.plus.mean.toFixed(4)} nats
              </div>
              <div className="text-slate-500">
                −v {decision.arms.minus.mean.toFixed(4)} · random {decision.arms.random.mean.toFixed(4)}
              </div>
              <div className="text-slate-500">信噪比中位数 {decision.snr_median ?? "—"}</div>
            </div>
            {floor && (
              <div data-progress-band="floor">
                <b className="text-gray-400">底噪带</b>
                <span className="text-slate-500"> · {floor.n_sites} site</span>
                <div className="mt-1 font-mono text-slate-400">
                  +v {floor.arms.plus.mean >= 0 ? "+" : ""}{floor.arms.plus.mean.toFixed(4)} nats
                </div>
                <div className="text-amber-400/80">尾概率变化，不可用于行为主张</div>
              </div>
            )}
            {all && (
              <div data-progress-band="all">
                <b className="text-slate-400">全样本（混算）</b>
                <span className="text-slate-500"> · {all.n_sites} site</span>
                <div className="mt-1 font-mono text-slate-400">
                  +v {all.arms.plus.mean >= 0 ? "+" : ""}{all.arms.plus.mean.toFixed(4)} nats
                </div>
                <div className="text-slate-500">混算会把它读大约 12 倍，别用</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
