"use client";

/**
 * Bloque C — subscribe to the per-conversation SSE event stream.
 *
 * Opens an ``EventSource`` to the proxy route at
 * ``/api/conversations/:conv_id/stream?tenant_id=...`` and triggers
 * ``router.refresh()`` whenever a backend event lands. The detail page
 * is a server component, so refresh re-runs the data loaders and the
 * UI rehydrates with the new message rows / toggle state without a
 * manual reload.
 *
 * We don't try to merge events into a client-side store — the page
 * load is already cheap and going through the loader keeps the
 * ``MessageBubble`` rendering path identical to the initial mount.
 * If we ever feel the round-trip on hot conversations, swap this for
 * a reducer that appends to a local list.
 *
 * Events we care about today (from PR-C5):
 *
 * - ``message.new`` — fired by the operator-send endpoint, the inbound
 *   webhook (Phase 2), and the pipeline checkpoint (future).
 * - ``agent.toggled`` — fired by PATCH .../agent.
 *
 * Errors are non-fatal: the browser will reconnect on its own.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function useConversationStream(tenantId: string, conversationId: string) {
  const router = useRouter();
  useEffect(() => {
    const url = `/api/conversations/${conversationId}/stream?tenant_id=${tenantId}`;
    let source: EventSource | null = null;
    try {
      source = new EventSource(url);
    } catch {
      return;
    }
    const onAny = () => router.refresh();
    source.addEventListener("message.new", onAny);
    source.addEventListener("agent.toggled", onAny);
    // Generic "message" handler so payloads sent without an event name
    // still trigger a refresh (defensive).
    source.onmessage = onAny;
    return () => {
      source?.close();
    };
  }, [tenantId, conversationId, router]);
}
