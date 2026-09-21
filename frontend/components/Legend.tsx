"use client";

/**
 * Legend explaining the color encoding of the 3D ribbon.
 */

export default function Legend() {
  return (
    <div className="absolute bottom-4 left-4 p-3 rounded-lg bg-black/60 backdrop-blur border border-border text-xs text-gray-200 space-y-1.5">
      <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">
        Reasoning Path
      </div>
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
      <div className="flex items-center gap-2">
        <span className="inline-block w-3 h-3 rounded-full bg-orange-400" />
        <span>self-check token</span>
      </div>
      <div className="flex items-center gap-2 pt-1 border-t border-border/50">
        <span className="inline-block w-3 h-3 rounded-full bg-yellow-300" />
        <span>current token</span>
      </div>
    </div>
  );
}