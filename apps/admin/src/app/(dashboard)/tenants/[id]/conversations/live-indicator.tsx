"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

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

// Drop to polling after this many ms if SSE neither opened nor errored.
// The 2026-05-13 review caught the badge stuck on "Conectando…" because
// the original 8s margin was longer than the time most operators stay
// on the conversations tab to verify health. 3.5s is enough to cover
// a cold proxy boot (~1.5s in our Vercel logs) and still feels alive.
const SSE_OPEN_TIMEOUT_MS = 3500;

// Polling fallback cadence. When SSE is unavailable we still want
// fresh rows — refresh the server component on this interval.
const POLLING_INTERVAL_MS = 12_000;

/**
 * Live indicator for the conversations stream.
 *
 * Tries SSE first; if the stream stalls or errors out (Vercel Hobby
 * has a 5-min cap, some networks block long-poll), it degrades to a
 * "polling" badge AND starts a real ``router.refresh()`` timer so Lee
 * still sees fresh rows — earlier revisions only flipped the badge
 * but did nothing else, which left the page stale until a manual
 * reload.
 *
 * In Phase 1 we don't consume the SSE messages — we use the connection
 * state as a health signal. Phase 2 wires per-message updates into the
 * table without a full refetch.
 */
export function LiveIndicator({ tenantId }: { tenantId: string }) {
  const router = useRouter();
  const [state, setState] = useState<State>("connecting");

  useEffect(() => {
    const controller = new AbortController();
    let source: EventSource | null = null;
    let opened = false;
    try {
      source = new EventSource(
        `/api/conversations/stream?tenant_id=${tenantId}`,
      );
      source.onopen = () => {
        opened = true;
        setState("live");
      };
      source.onerror = () => {
        // EventSource emits ``onerror`` both on a real failure and on
        // transient reconnects. If we never managed to open the stream
        // we hard-fall to polling; if we *had* opened it we let the
        // browser retry once before degrading.
        if (!opened) {
          source?.close();
          setState("polling");
        }
      };
    } catch {
      queueMicrotask(() => setState("polling"));
    }

    const fallback = setTimeout(() => {
      setState((prev) => (prev === "connecting" ? "polling" : prev));
    }, SSE_OPEN_TIMEOUT_MS);

    return () => {
      clearTimeout(fallback);
      source?.close();
      controller.abort();
    };
  }, [tenantId]);

  // Real polling when SSE is unavailable. ``router.refresh()`` re-runs
  // the server components on the conversations page so the table picks
  // up new rows without a full reload.
  useEffect(() => {
    if (state !== "polling") return;
    const id = setInterval(() => {
      router.refresh();
    }, POLLING_INTERVAL_MS);
    return () => clearInterval(id);
  }, [state, router]);

  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border border-border px-2 py-0.5 text-xs font-mono uppercase text-muted-foreground"
      style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      aria-live="polite"
      title={
        state === "polling"
          ? `SSE no disponible — refrescando cada ${POLLING_INTERVAL_MS / 1000}s`
          : undefined
      }
    >
      <StatusDot tone={TONE[state]} pulse={state === "live"} />
      {COPY[state]}
    </span>
  );
}
