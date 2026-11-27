import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { inboxCountsAction } from "@/app/(console)/inbox/actions";
import { INBOX_COUNTS_EVENT } from "@/components/inbox/use-inbox-stream";
import { useLiveStream } from "@/components/live/live-stream";
import { keys, unwrap } from "@/lib/query";

/** Spec 082 (R3.8): with the live line down, the counter reads every 60 s, as before. */
export const UNREAD_POLL_MS = 60_000;

/**
 * Spec 030 (R3.5), spec 082 (R3.7, R3.8): how many conversations this person
 * has not read — the number next to «Bandeja de entrada» and at the head of the
 * tab's title. One query (`["inbox","counts"]`) for the whole console: the live
 * line makes it stale on each conversation event, and the open Inbox hands it
 * the counts it just read. It polls only while the line is down.
 */
export function useInboxUnread(enabled: boolean): number {
  const qc = useQueryClient();
  const { status } = useLiveStream();
  const query = useQuery({
    queryKey: keys.inboxCounts,
    queryFn: async () => unwrap(await inboxCountsAction()),
    enabled,
    refetchInterval: status === "live" ? false : UNREAD_POLL_MS,
  });

  React.useEffect(() => {
    if (!enabled) return;
    const onCounts = (e: Event) => {
      const detail = (e as CustomEvent<{ unread?: unknown; waiting?: unknown }>).detail;
      if (typeof detail?.unread === "number") {
        qc.setQueryData(keys.inboxCounts, { unread: detail.unread, waiting: typeof detail.waiting === "number" ? detail.waiting : 0 });
      }
    };
    window.addEventListener(INBOX_COUNTS_EVENT, onCounts);
    return () => window.removeEventListener(INBOX_COUNTS_EVENT, onCounts);
  }, [enabled, qc]);

  return enabled ? (query.data?.unread ?? 0) : 0;
}
