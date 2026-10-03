"use client";

/**
 * 证据阶梯 —— 这份项目真正的产品。
 *
 * 回答 goal 里那句「能不能提取出一套可以通用的解释向量功能或者效果的可解释性理论」。
 *
 * ## 它是什么，不是什么
 *
 * **是**：一张任何「某 steering vector 编码了概念 X」的断言都能被放上去量的八级阶梯，
 * 加上本项目在每一级上的实际位置。
 * **不是**：关于模型内部的理论。它回答「一个这样的断言需要什么证据才成立」，
 * 不回答「模型在算什么」。
 *
 * ## 为什么数字必须来自 `evidence_ladder.json` 而不是写死在这里
 *
 * 阶梯上每个数字都来自别的产物（L1 的区间来自 linearity_law、L2 的 14 来自
 * readable_subspace、L4 的 82× 来自 heldout_readability、L6 的 92 个 run 来自
 * cot_texts）。写死的话那些产物一改，阶梯就静默过期 ——
 * 而一个**过期的阶梯比没有阶梯更坏**，它会让人以为「L2 = 14」是当前的量。
 * 所以数字由 `.cache/xcheck/build_evidence_ladder.py` 从产物里**读**出来，
 * 并在构建时做六条跨产物一致性自检，不过就不产出文件。
 *
 * ## 这一块刻意不做的事
 *
 * 不把 L5/L7 画成"差一点就到了"。L5 是 0 条（未测），L7 一次都没测；
 * 阶梯的价值恰恰在于它**留白**。
 */

import { useEffect, useState } from "react";

type Rung = {
  level: string;
  claim: string;
  needs: string;
  state: "done" | "partial" | "missing";
  here: string;
  note: string;
};

type Ladder = {
  what: string;
  built_from: string[];
  selfcheck_passed: boolean;
  ladder: Rung[];
  answerable: string[];
  not_answerable: string[];
  max_level_reached: string;
  most_common_overreach: string;
  overreach_numbers: { readable_directions: number; usable_axes: number; note: string };
};

const STATE_TXT: Record<Rung["state"], string> = {
  done: "有",
  partial: "部分",
  missing: "没有",
};

const STATE_CLS: Record<Rung["state"], string> = {
  done: "text-emerald-300",
  partial: "text-amber-300",
  missing: "text-gray-500",
};

const MARK: Record<Rung["state"], string> = { done: "✓", partial: "◐", missing: "—" };

export default function EvidenceLadderPanel() {
  const [d, setD] = useState<Ladder | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/latent/data/evidence_ladder.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => { if (alive) setD(j); })
      .catch((e) => { if (alive) setErr(String(e.message || e)); });
    return () => { alive = false; };
  }, []);

  if (err) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3 text-[10px] text-red-300"
           data-ladder="error">
        证据阶梯加载失败：{err}（还没跑 <code>build_evidence_ladder.py</code>）
      </div>
    );
  }
  if (!d) {
    return (
      <div className="rounded bg-bg/40 border border-border p-3 text-[10px] text-gray-500"
           data-ladder="loading">
        载入证据阶梯…
      </div>
    );
  }

  return (
    <div className="rounded bg-bg/40 border border-border p-3" data-ladder="ready"
         data-max-level={d.max_level_reached}
         data-selfcheck={String(d.selfcheck_passed)}
         data-rungs={String(d.ladder.length)}>
      <h2 className="text-[12px] font-semibold text-gray-200 mb-0.5">
        证据阶梯：一条断言要走到第几级才算数
      </h2>
      <p className="text-[9.5px] text-gray-500 leading-relaxed mb-2">
        {d.what}。数字从 {d.built_from.length} 份产物里读出，构建时做跨产物
        一致性自检（{String(d.selfcheck_passed) ? "本次全过" : "未过"}）。
      </p>

      {/* ---- 阶梯本体 ---- */}
      <div className="flex flex-col gap-1 mb-2" data-rungs>
        {d.ladder.map((r) => (
          <div key={r.level}
               className="px-1.5 py-1 rounded"
               style={{ background: "#101722", borderLeft: `2px solid ${
                 r.state === "done" ? "#3f8f6b"
                   : r.state === "partial" ? "#a8792e" : "#39414f" }` }}
               data-rung={r.level}
               data-rung-state={r.state}
               data-rung-here={r.here}>
            <div className="flex items-baseline gap-1.5 flex-wrap">
              <span className="font-mono text-[10px] text-gray-400 w-7">{r.level}</span>
              <span className={`text-[10px] w-7 ${STATE_CLS[r.state]}`}
                    data-rung-mark={r.state}>
                {MARK[r.state]} {STATE_TXT[r.state]}
              </span>
              <span className="text-[10px] text-gray-300">{r.claim}</span>
            </div>
            <div className="text-[9px] text-gray-500 leading-snug mt-0.5 pl-[4.4rem]">
              需要：{r.needs}
            </div>
            <div className="text-[9.5px] text-gray-400 leading-snug mt-0.5 pl-[4.4rem]">
              本项目：<span className="font-mono">{r.here}</span>
            </div>
            {r.note && (
              <div className="text-[9px] text-gray-500 leading-snug mt-0.5 pl-[4.4rem]">
                {r.note}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ---- 最常见的越级 ---- */}
      <p className="text-[9.5px] text-amber-200/90 leading-relaxed px-1.5 py-1 rounded mb-2"
         style={{ background: "#131a28" }}
         data-overreach>
        <b>最常见的越级：</b>{d.most_common_overreach}。
        本项目 <b>{d.overreach_numbers.readable_directions}</b> 条可读方向，
        可用的轴 <b>{d.overreach_numbers.usable_axes}</b> 条 ——
        {d.overreach_numbers.note}。
      </p>

      {/* ---- 它能回答 / 不能回答 ---- */}
      <div className="grid grid-cols-1 gap-1">
        <p className="text-[9.5px] text-gray-400 leading-relaxed" data-answerable>
          <b className="text-emerald-300">能回答：</b>
          {d.answerable.join("；")}
        </p>
        <p className="text-[9.5px] text-gray-400 leading-relaxed" data-not-answerable>
          <b className="text-red-300">不能回答：</b>
          {d.not_answerable.join("；")}。
        </p>
      </div>
    </div>
  );
}
