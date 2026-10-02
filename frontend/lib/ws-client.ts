"use client";

/**
 * WebSocket client. Reconnects with exponential backoff on close.
 */

import type { ReadyMessage, ServerMessage, ControlMessage } from "./frame-types";

export type FrameHandler = (msg: ServerMessage) => void;

export class SteeringWSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectDelay = 1000;
  private handler: FrameHandler;
  private closed = false;
  private wantAutoStart: boolean;
  private started = false;

  constructor(url: string, handler: FrameHandler, autoStart = true) {
    this.url = url;
    this.handler = handler;
    this.wantAutoStart = autoStart;
  }

  connect() {
    if (this.closed) return;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);
    this.started = false;

    // Auto-start on `ready`, not on `open`.
    //
    // `open` only means the socket exists. The backend's `ready` message is
    // what declares which layer it will actually replay, and it arrives
    // after `open`. Starting from `open` therefore requires guessing a layer
    // here, and the guess silently wins: the server is then replaying a layer
    // the UI is not displaying, and the two disagree about a number the whole
    // page is built around. It looked fine at L14, which is where the variance
    // is small enough that the un-normalised scene happened to be legible --
    // so the mismatch stayed invisible until the layer was raised to L26.
    this.ws.onopen = () => {};

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as ServerMessage;
        this.handler(msg);
        const kind = (msg as { kind?: string }).kind;
        if (kind === "ready" && this.wantAutoStart && !this.started) {
          this.started = true;
          const layer = (msg as ReadyMessage).payload.layer;
          this.sendControl({
            kind: "start",
            payload: { prompt: "Why is the sky blue?", layer },
          });
        }
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