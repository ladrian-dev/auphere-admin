import { usePathname } from "next/navigation";
import * as React from "react";

import { inboxCountsAction } from "@/app/(console)/inbox/actions";
import { INBOX_COUNTS_EVENT } from "@/components/inbox/use-inbox-stream";

/**
 * Spec 030 (R3.5): how many conversations this person has not read, for the
 * number next to «Bandeja de entrada». Read on mount and on navigation, every
 * 60 s while the tab is visible, and at once when the open Inbox announces
 * new counts (it is the one listening to the live stream).
 */
export function useInboxUnread(enabled: boolean): number {
  const pathname = usePathname();
  const [unread, setUnread] = React.useState(0);

  React.useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const load = async () => {
      const r = await inboxCountsAction();
      if (alive && r.ok) setUnread(r.data.unread);
    };
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 60_000);
    const onCounts = (e: Event) => {
      const detail = (e as CustomEvent<{ unread?: unknown }>).detail;
      if (typeof detail?.unread === "number") setUnread(detail.unread);
    };
    window.addEventListener(INBOX_COUNTS_EVENT, onCounts);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener(INBOX_COUNTS_EVENT, onCounts);
    };
  }, [enabled, pathname]);

  return enabled ? unread : 0;
}
