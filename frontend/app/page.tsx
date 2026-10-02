"use client";

import { useEffect, useRef, useState } from "react";

import { useApp } from "@/lib/store";
import { SteeringWSClient } from "@/lib/ws-client";
import { resolveWsUrl } from "@/lib/ws-endpoint";
import type { SteeringAckMessage } from "@/lib/frame-types";

import ControlPanel from "@/components/ControlPanel";
import InterventionOutcomePanel from "@/components/InterventionOutcomePanel";
import VectorStructurePanel from "@/components/VectorStructurePanel";
import StrengthLawPanel from "@/components/StrengthLawPanel";
import LayerDerivationPanel from "@/components/LayerDerivationPanel";
import TokenStreamPanel from "@/components/TokenStreamPanel";
import InterpretationPanel from "@/components/InterpretationPanel";
import SteeringControl from "@/components/SteeringControl";
import ArchivedExperiments from "@/components/ArchivedExperiments";
import Legend from "@/components/Legend";

// Imported statically, not through next/dynamic({ ssr: false }).
//
// The lazy form silently fails to mount in this app: the page renders,
// the WebSocket connects, the panels populate — and the 3-D canvas is
// simply absent, with nothing in the console. Verified by contrast: the
// static import makes / grow 1.16 kB -> 227 kB and `<canvas>` appear.
import Scene3D from "@/components/Scene3D";

// The backend URL is resolved at runtime, not baked in at module scope.
// See lib/ws-endpoint.ts: port 8000 is frequently occupied by something
// unrelated, and a hard-coded port made that failure look like a broken app.
export default function Page() {
  const ingestFrame = useApp((s) => s.ingestFrame);
  const ingestReady = useApp((s) => s.ingestReady);
  const ingestSteeringCatalog = useApp((s) => s.ingestSteeringCatalog);
  const setActiveInterventions = useApp((s) => s.setActiveInterventions);
  const setConnected = useApp((s) => s.setConnected);
  const setError = useApp((s) => s.setError);

  const clientRef = useRef<SteeringWSClient | null>(null);
  const [wsUrl, setWsUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    resolveWsUrl(window.location.hostname).then((url) => {
      if (cancelled) return;
      setWsUrl(url);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!wsUrl) return;
    const client = new SteeringWSClient(wsUrl, (msg) => {
      const k = (msg as { kind?: string }).kind;
      if (k === "ready") {
        ingestReady(msg as Parameters<typeof ingestReady>[0]);
      } else if (k === "steering_catalog") {
        ingestSteeringCatalog(
          msg as Parameters<typeof ingestSteeringCatalog>[0]
        );
      } else if (k === "steering_ack") {
        // The backend is authoritative about which interventions are
        // live; mirror its list so the UI can't drift out of sync.
        setActiveInterventions(
          (msg as SteeringAckMessage).payload.active
        );
      } else if (k === "error") {
        setError((msg as { payload: { message: string } }).payload.message);
      } else if (k === "reset_ack") {
        useApp.getState().reset();
      } else {
        ingestFrame(msg as Parameters<typeof ingestFrame>[0]);
      }
    });
    client.connect();
    setConnected(true);
    clientRef.current = client;
    return () => {
      client.close();
      setConnected(false);
    };
  }, [
    wsUrl,
    ingestFrame,
    ingestReady,
    ingestSteeringCatalog,
    setActiveInterventions,
    setConnected,
    setError,
  ]);

  const sendControl = (msg: Parameters<SteeringWSClient["sendControl"]>[0]) => {
    clientRef.current?.sendControl(msg);
  };

  const connected = useApp((s) => s.connected);
  const error = useApp((s) => s.error);
  const latest = useApp((s) => s.latest);

  return (
    // h-screen + overflow-hidden, not min-h-screen: the control sidebar is
    // taller than the viewport, and with min-h-screen the grid grew to fit
    // it, which dragged the 3-D pane along to 1239x2663. A perspective
    // projection keys its vertical fov to the element height, so that made
    // the effective horizontal fov tiny and the trajectory spanned 90% of the
    // width -- it read as scattered lines rather than a path. The pane is now
    // exactly one viewport tall and the sidebar scrolls inside its own column.
    <main className="h-screen w-screen overflow-hidden bg-bg text-gray-200 font-sans flex flex-col">
      <header className="flex items-center justify-between px-6 border-b border-border bg-panel">
        <div className="flex items-baseline gap-3 py-3">
          <h1 className="text-lg font-bold text-gray-100">Reasoning3D</h1>
          <span className="text-xs text-gray-500">
            live 3-D visualization of LLM hidden states during reasoning
          </span>
        </div>
        <div className="text-xs flex items-center gap-2 py-3">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              connected ? "bg-green-400" : "bg-red-500"
            }`}
          />
          <span>{connected ? "connected" : "disconnected"}</span>
          {latest && (
            <span className="ml-3 text-gray-500 font-mono">
              {latest.step_id} steps
            </span>
          )}
          {error && (
            <span className="ml-3 text-red-400 font-mono">{error}</span>
          )}
        </div>
      </header>

      <div className="grid grid-cols-[1fr_360px] flex-1 min-h-0">
        <div className="relative min-h-0 overflow-hidden border-r border-border">
          <Scene3D />
          <Legend />
        </div>

        <aside className="flex flex-col gap-4 p-4 overflow-hidden min-h-0">
          <ControlPanel sendControl={sendControl} />
          <LayerDerivationPanel />
          <SteeringControl sendControl={sendControl} />
          <InterventionOutcomePanel />
          <VectorStructurePanel />
          <StrengthLawPanel />
          <ArchivedExperiments />
          <InterpretationPanel />
          <TokenStreamPanel />
        </aside>
      </div>
    </main>
  );
}