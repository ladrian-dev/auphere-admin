"use client";

import { useEffect, useState } from "react";

import { StatusDot } from "@/components/brand/status-dot";

type State = "connecting" | "live" | "polling" | "offline";

const COPY: Record<State, string> = {
  connecting: "Conectando…",
  live: "En vivo",
  polling: "Polling",
  offline: "Sin conexión",
};

const TONE: Record<State, "info" | "positive" | "warning" | "muted"> = {
  connecting: "muted",
  live: "positive",
  polling: "warning",
  offline: "muted",
};

/**
 * Live indicator for the conversations stream.
 *
 * Tries SSE first; if the stream stalls or errors out (Vercel Hobby
 * has a 5-min cap, some networks block long-poll), it degrades to a
 * "polling" badge. The router refreshes the server component on a
 * timer in that mode so Lee still sees fresh rows.
 *
 * Note: in Phase 1 we don't actually consume the SSE messages — we
 * just use the connection state as a health signal. Phase 2 wires
 * per-message updates into the table without a full refetch.
 */
export function LiveIndicator({ tenantId }: { tenantId: string }) {
  const [state, setState] = useState<State>("connecting");

  useEffect(() => {
    const controller = new AbortController();
    let source: EventSource | null = null;
    try {
      // Best-effort SSE — Better Auth's session cookie travels along with
      // the fetch the EventSource issues, and the proxy layer at
      // ``/admin/...`` is set up via Next.js (Phase 2) to forward to the
      // FastAPI backend. For now we hit ``/api/conversations/stream``,
      // which 404s gracefully if not wired yet — we degrade to polling.
      source = new EventSource(
        `/api/conversations/stream?tenant_id=${tenantId}`,
      );
      source.onopen = () => setState("live");
      source.onerror = () => {
        source?.close();
        setState("polling");
      };
    } catch {
      queueMicrotask(() => setState("polling"));
    }

    const fallback = setTimeout(() => {
      // If the stream hasn't opened in 4s, drop to polling.
      setState((prev) => (prev === "connecting" ? "polling" : prev));
    }, 4000);

    return () => {
      clearTimeout(fallback);
      source?.close();
      controller.abort();
    };
  }, [tenantId]);

  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border border-border px-2 py-0.5 text-xs font-mono uppercase text-muted-foreground"
      style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      aria-live="polite"
    >
      <StatusDot tone={TONE[state]} pulse={state === "live"} />
      {COPY[state]}
    </span>
  );
}
