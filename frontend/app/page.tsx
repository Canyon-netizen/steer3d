"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";

import { useApp } from "@/lib/store";
import { SteeringWSClient } from "@/lib/ws-client";

import ControlPanel from "@/components/ControlPanel";
import TokenStreamPanel from "@/components/TokenStreamPanel";
import Legend from "@/components/Legend";

const Scene3D = dynamic(() => import("@/components/Scene3D"), { ssr: false });

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  (typeof window !== "undefined"
    ? `ws://${window.location.hostname}:8000/ws`
    : "ws://localhost:8000/ws");

export default function Page() {
  const ingestFrame = useApp((s) => s.ingestFrame);
  const ingestReady = useApp((s) => s.ingestReady);
  const setConnected = useApp((s) => s.setConnected);
  const setError = useApp((s) => s.setError);

  const clientRef = useRef<SteeringWSClient | null>(null);

  useEffect(() => {
    const client = new SteeringWSClient(WS_URL, (msg) => {
      const k = (msg as { kind?: string }).kind;
      if (k === "ready") {
        ingestReady(msg as Parameters<typeof ingestReady>[0]);
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
  }, [ingestFrame, ingestReady, setConnected, setError]);

  const sendControl = (msg: Parameters<SteeringWSClient["sendControl"]>[0]) => {
    clientRef.current?.sendControl(msg);
  };

  const connected = useApp((s) => s.connected);
  const error = useApp((s) => s.error);
  const latest = useApp((s) => s.latest);

  return (
    <main className="min-h-screen w-screen bg-bg text-gray-200 font-sans flex flex-col">
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
        <div className="relative border-r border-border">
          <Scene3D />
          <Legend />
        </div>

        <aside className="flex flex-col gap-4 p-4 overflow-hidden min-h-0">
          <ControlPanel sendControl={sendControl} />
          <TokenStreamPanel />
        </aside>
      </div>
    </main>
  );
}