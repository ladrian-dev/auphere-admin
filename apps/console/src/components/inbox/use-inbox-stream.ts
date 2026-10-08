import * as React from "react";

import { inboxStreamUrl } from "@/lib/inbox-urls";

export type InboxEvent = {
  event: "conversation.updated" | "message.new" | "message.status";
  conversation_id: string;
  message_id?: string;
  direction?: "inbound" | "outbound";
  status?: string;
};

export type StreamStatus = "connecting" | "live" | "reconnecting";

const NAMES = ["conversation.updated", "message.new", "message.status"] as const;

/**
 * The Inbox, live (spec 030, D17). One `EventSource` on the BFF route; the
 * browser reconnects on its own and the route mints a fresh token each
 * time. Events say WHAT changed, never the text — the caller re-reads it
 * through its RLS routes. While the line is down the status says
 * «reconnecting» so the screen can say it (no silent staleness, §V).
 */
export function useInboxStream(
  onEvent: (e: InboxEvent) => void,
  onDown?: () => void,
  enabled = true,
): StreamStatus {
  const [status, setStatus] = React.useState<StreamStatus>("connecting");
  const handler = React.useRef(onEvent);
  const down = React.useRef(onDown);
  React.useEffect(() => {
    handler.current = onEvent;
    down.current = onDown;
  });

  React.useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const source = new EventSource(inboxStreamUrl);
    // `EventSource` cannot read the status of a failed reconnect. On each
    // drop the caller checks the session another way (`onDown`), so an
    // expired session does not leave the Inbox «reconnecting» forever.
    let isDown = false;
    const up = () => {
      isDown = false;
      setStatus("live");
    };
    source.onopen = up;
    source.onerror = () => {
      if (!isDown) {
        isDown = true;
        down.current?.();
      }
      setStatus("reconnecting");
    };
    const listener = (msg: MessageEvent<string>) => {
      try {
        const data = JSON.parse(msg.data) as InboxEvent;
        if (data && typeof data.conversation_id === "string") handler.current(data);
      } catch {
        /* a malformed frame is ignored, never painted */
      }
    };
    for (const name of NAMES) source.addEventListener(name, listener as EventListener);
    source.addEventListener("ready", up);
    return () => {
      for (const name of NAMES) source.removeEventListener(name, listener as EventListener);
      source.close();
    };
  }, [enabled]);

  return status;
}

/** The counts the sidebar badge shows (R3.5), shared without a store: one window event. */
export const INBOX_COUNTS_EVENT = "nexus:inbox-counts";
export function announceCounts(counts: { unread: number; waiting: number }): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INBOX_COUNTS_EVENT, { detail: counts }));
}
