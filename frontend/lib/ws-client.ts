"use client";

/**
 * WebSocket client. Reconnects with exponential backoff on close.
 */

import type { ServerMessage, ControlMessage } from "./frame-types";

export type FrameHandler = (msg: ServerMessage) => void;

export class SteeringWSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectDelay = 1000;
  private handler: FrameHandler;
  private closed = false;
  private wantAutoStart: boolean;

  constructor(url: string, handler: FrameHandler, autoStart = true) {
    this.url = url;
    this.handler = handler;
    this.wantAutoStart = autoStart;
  }

  connect() {
    if (this.closed) return;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      // Auto-start streaming so the synthetic demo lights up immediately.
      if (this.wantAutoStart) {
        this.sendControl({
          kind: "start",
          payload: { prompt: "Why is the sky blue?", layer: 14 },
        });
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as ServerMessage;
        this.handler(msg);
      } catch (err) {
        console.warn("[SteeringWSClient] failed to parse message", err);
      }
    };

    this.ws.onclose = () => {
      if (this.closed) return;
      setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 8000);
    };

    this.ws.onerror = (err) => {
      console.warn("[SteeringWSClient] socket error", err);
    };
  }

  sendControl(msg: ControlMessage) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(msg));
  }

  close() {
    this.closed = true;
    if (this.ws) this.ws.close();
  }
}