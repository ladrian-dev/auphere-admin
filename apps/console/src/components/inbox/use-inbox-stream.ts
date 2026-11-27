import * as React from "react";

import { useLiveStream } from "@/components/live/live-stream";

export type InboxEvent = {
  event: "conversation.updated" | "message.new" | "message.status";
  conversation_id: string;
  message_id?: string;
  direction?: "inbound" | "outbound";
  status?: string;
};

export type StreamStatus = "connecting" | "live" | "reconnecting";

/**
 * The Inbox, live (spec 030, D17). Since spec 082 it does not open a line of
 * its own: it listens to the console's shared one (`LiveStreamProvider`, one
 * per tab, R3.11). Events say WHAT changed, never the text — the caller
 * re-reads it through its RLS routes. While the line is down the status says
 * «reconnecting» so the screen can say it (no silent staleness, §V); on each
 * drop `onDown` lets the caller check the session another way, and when it
 * comes back `onBack` re-reads what was missed meanwhile (R3.10).
 */
export function useInboxStream(
  onEvent: (e: InboxEvent) => void,
  onDown?: () => void,
  enabled = true,
  onBack?: () => void,
): StreamStatus {
  const { status, subscribe } = useLiveStream();
  const handlers = React.useRef({ onEvent, onDown, onBack });
  React.useEffect(() => {
    handlers.current = { onEvent, onDown, onBack };
  });

  React.useEffect(() => {
    if (!enabled) return;
    return subscribe((e) => {
      if (e.name === "down") return handlers.current.onDown?.();
      if (e.name === "back") return handlers.current.onBack?.();
      if (e.name === "reservations.changed") return;
      if (typeof e.data.conversation_id !== "string") return;
      handlers.current.onEvent({ ...(e.data as Omit<InboxEvent, "event">), event: e.name, conversation_id: e.data.conversation_id });
    });
  }, [enabled, subscribe]);

  return status === "off" ? "connecting" : status;
}

/** The counts the sidebar badge shows (R3.5), shared without a store: one window event. */
export const INBOX_COUNTS_EVENT = "nexus:inbox-counts";
export function announceCounts(counts: { unread: number; waiting: number }): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INBOX_COUNTS_EVENT, { detail: counts }));
}
