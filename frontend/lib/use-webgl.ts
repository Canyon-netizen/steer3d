"use client";

import { useEffect, useState } from "react";

/**
 * Whether this browser can actually give us a WebGL context.
 *
 * This has to be answered *before* anything mounts <Canvas>. React-three-
 * fiber does not degrade when the context is missing: three.js throws
 * while creating the context and the error unwinds the whole React tree,
 * taking the panels and the token stream down with it. So the decision
 * gates the render, it is not a try/catch around one.
 *
 * `null` means "not answered yet" (the first client render, and every
 * server render). Callers must treat it as unknown rather than defaulting
 * to either branch, or the server and client will disagree about what to
 * paint and React will warn about the mismatch.
 *
 * `?render=2d` and `?render=webgl` force a branch. That exists so the 2-D
 * path can be verified in a browser that *does* have WebGL -- otherwise
 * it would only ever be exercised on the machines that have no other
 * option, which is exactly the population least able to report a problem.
 */
export function useWebGLSupport(): boolean | null {
  const [supported, setSupported] = useState<boolean | null>(null);

  useEffect(() => {
    let forced: string | null = null;
    try {
      forced = new URLSearchParams(window.location.search).get("render");
    } catch {
      forced = null;
    }
    if (forced === "2d") { setSupported(false); return; }
    if (forced === "webgl") { setSupported(true); return; }

    let ok = false;
    try {
      const c = document.createElement("canvas");
      const gl =
        c.getContext("webgl2") ||
        c.getContext("webgl") ||
        c.getContext("experimental-webgl");
      ok = !!gl;
      // Release the probe context immediately; browsers cap how many are
      // live and we just used one.
      const lose = (gl as WebGLRenderingContext | null)?.getExtension("WEBGL_lose_context");
      lose?.loseContext();
    } catch {
      ok = false;
    }
    setSupported(ok);
  }, []);

  return supported;
}
