"use client";

/**
 * Legend for the trajectory view.
 *
 * Two things here are load-bearing rather than decorative:
 *
 * 1. The heat ramp is only offered when entropy was actually recorded.
 *    The archived PCA bundle stores hidden states without logits, so
 *    replaying it gives `entropy: null` on every frame. A legend that
 *    says "blue = confident" over a trajectory that has no confidence
 *    measurement in it teaches the reader to read a value off a pixel
 *    that was never written. When the data is absent the ramp rows are
 *    replaced by an explicit "not recorded" row.
 *
 * 2. The per-layer extent readout. Shallow layers carry far less
 *    variance than deep ones (measured max |coord|: L4 ~14, L12 ~52,
 *    L20 ~344, L26 ~1199), so a single shared normalisation makes L4
 *    collapse to a speck. That is true of the model, not a rendering
 *    artefact, and the reader deserves to see the number instead of
 *    guessing why this path looks smaller than the last one.
 */

import { useMemo } from "react";

import { useApp } from "@/lib/store";
import { trajectoryExtent, extentFraction, PCA_WORLD_SCALE } from "@/lib/view-scale";

export default function Legend() {
  const frames = useApp((s) => s.frames);
  const layer = useApp((s) => s.layer);

  const hasEntropy = useMemo(() => frames.some((f) => f.entropy != null), [frames]);
  const ext = useMemo(
    () => trajectoryExtent(frames.map((f) => f.point)),
    [frames],
  );
  const frac = extentFraction(ext);

  return (
    <div className="absolute bottom-4 left-4 p-3 rounded-lg bg-black/70 backdrop-blur border border-border text-xs text-gray-200 space-y-1.5 max-w-xs">
      <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">
        Reasoning Path
      </div>

      {hasEntropy ? (
        <>
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-cyan-400" />
            <span>confident (low entropy)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-yellow-400" />
            <span>uncertain</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-red-400" />
            <span>very uncertain</span>
          </div>
        </>
      ) : (
        <div className="flex items-start gap-2 text-gray-300">
          <span className="inline-block w-3 h-3 rounded-full mt-0.5 shrink-0" style={{ background: "rgb(158,143,204)" }} />
          <span>
            <b className="text-gray-100">熵未记录</b>：这批采集只存了隐状态，
            没存 logits，所以颜色<span className="text-gray-100">不代表置信度</span>。
            灰色 = 无数据，不是"中性"。
          </span>
        </div>
      )}

      <div className="flex items-center gap-2">
        <span className="inline-block w-3 h-3 rounded-full bg-orange-400" />
        <span>self-check token</span>
      </div>
      <div className="flex items-center gap-2 pt-1 border-t border-border/50">
        <span className="inline-block w-3 h-3 rounded-full bg-yellow-300" />
        <span>current token</span>
      </div>

      {ext && (
        <div className="pt-1.5 border-t border-border/50 text-[11px] text-gray-400 leading-relaxed">
          <div>
            当前层 <span className="text-gray-200 font-mono">L{layer}</span>
            ：坐标最大绝对值{" "}
            <span className="text-gray-200 font-mono">{ext.maxAbs.toFixed(0)}</span>
          </div>
          {frac != null && (
            <div>
              占画面宽度{" "}
              <span className="text-gray-200 font-mono">
                {(frac * 100).toFixed(1)}%
              </span>
              <span className="text-gray-500">
                （全局统一除以 {PCA_WORLD_SCALE}，不按层缩放）
              </span>
            </div>
          )}
          <div className="text-gray-500">
            浅层的轨迹看着小，是因为隐状态方差本身随深度暴涨——这是模型的性质，不是画错了。
          </div>
        </div>
      )}
    </div>
  );
}
