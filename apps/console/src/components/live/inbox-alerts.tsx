"use client";

import * as React from "react";

import { useInboxUnread } from "@/components/shell/use-inbox-unread";

import { RING_GAP_MS, armChime, playChime, soundOn } from "./chime";
import { useLiveStream } from "./live-stream";
import { useTitleCount } from "./title-count";

/** The person has this very conversation open, and the tab in front (R3.2). */
export function isOpenAndVisible(conversationId: string): boolean {
  if (document.visibilityState !== "visible") return false;
  if (window.location.pathname !== "/inbox") return false;
  return new URLSearchParams(window.location.search).get("c") === conversationId;
}

/**
 * The Inbox tells, wherever the person is in the console (spec 082, Historia 3):
 * a short sound for each message from a customer (R3.1), not for the one open
 * and in front (R3.2), at most once every 3 s (R3.3), unless switched off
 * (R3.4); and the unread count at the head of the tab's title (R3.6). Mounted
 * only for a client person with the Inbox: without it there is no sound, no
 * count and no number in the title (§V).
 */
export function InboxAlerts() {
  const unread = useInboxUnread(true);
  useTitleCount(unread);
  const { subscribe } = useLiveStream();
  const last = React.useRef(0);

  React.useEffect(() => armChime(), []);
  React.useEffect(
    () =>
      subscribe((e) => {
        if (e.name !== "message.new" || e.data.direction !== "inbound") return;
        if (!soundOn()) return;
        const id = typeof e.data.conversation_id === "string" ? e.data.conversation_id : "";
        if (id && isOpenAndVisible(id)) return;
        const now = Date.now();
        if (now - last.current < RING_GAP_MS) return;
        // Before the first touch the browser does not let it sound: nothing is said (R3.5).
        if (playChime()) last.current = now;
      }),
    [subscribe],
  );
  return null;
}
