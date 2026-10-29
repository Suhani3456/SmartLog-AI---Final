/**
 * SmartLog AI — WebSocket client for WS /ws/stream with auto-reconnect.
 *
 * Behavior:
 * - exponential backoff, capped at 15 s, then reconnect forever
 * - callbacks: onIncident (one frame) and onOpen (used to clear backoff)
 * - close() fully stops the client (used on unmount)
 */

import { API_URL } from "./api";
import type { StreamFrame } from "../types";

export interface StreamClientOptions {
  onFrame: (frame: StreamFrame) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

const HTTP_TO_WS = (url: string) => url.replace(/^http/, "ws");
const MAX_BACKOFF_MS = 15000;

export function createStreamClient({ onFrame, onOpen, onClose }: StreamClientOptions) {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  function connect() {
    if (disposed) return;
    ws = new WebSocket(`${HTTP_TO_WS(API_URL)}/ws/stream`);
    ws.onopen = () => {
      attempt = 0; // reset backoff once healthy
      onOpen?.();
    };
    ws.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data) as StreamFrame;
        if (frame?.type) onFrame(frame);
      } catch {
        /* ignore malformed frames; keep the stream alive */
      }
    };
    ws.onclose = () => {
      onClose?.();
      scheduleReconnect();
    };
    ws.onerror = () => {
      // onclose fires right after; nothing else to do here
    };
  }

  function scheduleReconnect() {
    if (disposed) return;
    const wait = Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS);
    attempt += 1;
    retryTimer = setTimeout(connect, wait);
  }

  connect();

  return {
    close() {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (ws) ws.onclose = null; // suppress reconnect on manual close
      ws?.close();
    },
  };
}
