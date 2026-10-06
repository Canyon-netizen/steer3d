"use client";

/**
 * WebSocket client. Reconnects with exponential backoff on close.
 */

import type { ReadyMessage, ServerMessage, ControlMessage } from "./frame-types";

export type FrameHandler = (msg: ServerMessage) => void;

/**
 * ⚠⚠ 连接状态必须来自 socket 自己的事件，不能来自「我调用了 connect()」。
 *
 * 原来 page.tsx 在 `client.connect()` 之后**立刻** `setConnected(true)`。
 * 而 `connect()` 只是 `new WebSocket(url)`，此刻连 TCP 握手都还没开始 ——
 * 后端不在时（实测 9503 无人监听、curl 探活 000）页面照样把 `connected`
 * 写成 true，于是：
 *   · 右上角那颗状态点一直是**绿的**，并印着 "connected"；
 *   · 任何拿 `connected` 当「后端在场」前提的判据都恒真。
 * 「前置没建立」被报成「前置已建立」，而它恰恰是最该被看见的那种失败。
 */
export type StatusHandler = (connected: boolean) => void;

export class SteeringWSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectDelay = 1000;
  private handler: FrameHandler;
  private closed = false;
  private wantAutoStart: boolean;
  private started = false;
  private onStatus: StatusHandler | null;

  constructor(
    url: string,
    handler: FrameHandler,
    autoStart = true,
    onStatus: StatusHandler | null = null,
  ) {
    this.url = url;
    this.handler = handler;
    this.wantAutoStart = autoStart;
    this.onStatus = onStatus;
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
    //
    // ⚠ `open` 仍然要报连接状态 —— 只是**不**用来触发回放。上一版这里是个空壳
    //   `() => {}`，于是上层没有任何途径知道 socket 到底开没开。
    this.ws.onopen = () => this.onStatus?.(true);

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
      // 先报 false，再排重连 —— 顺序反了会出现「已经断了但状态点还绿着」。
      this.onStatus?.(false);
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
    // close() 不走 onclose 的重连分支，但状态仍要归零 —— 组件卸载后
    // 再挂回来时不能继承一个「还连着」的假状态。
    this.onStatus?.(false);
    if (this.ws) this.ws.close();
  }
}
