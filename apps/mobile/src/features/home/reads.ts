import { useQuery } from "@tanstack/react-query";

import { endpoints, type Conversation, type InboxFilter } from "@/api/endpoints";
import { keys } from "@/api/query";
import { useInboxList } from "@/api/v13-bandeja-hooks";

/**
 * The Bandeja as Inicio reads it (spec 069, R8.3, R8.4). Only with the module:
 * without it the API answers 403 and every visit to Inicio would re-read
 * `/me`. The very reads of the Bandeja's tab (`useInboxList`, no search, no
 * agent, every channel) and of the tab's badge (`keys.counts`), so one cache
 * serves both, what the Bandeja changes shows here, and the live line's
 * `invalidateInbox` refreshes Inicio too.
 */
export type InboxPeek = { state: "loading" } | { state: "error"; retry: () => void } | { state: "ready"; items: Conversation[] };

function useFirstPage(filter: InboxFilter, enabled: boolean) {
  return useInboxList(filter, "", null, null, enabled);
}

function peekOf(query: ReturnType<typeof useFirstPage>, enabled: boolean): InboxPeek | null {
  if (!enabled) return null;
  const first = query.data?.pages[0];
  if (first) return { state: "ready", items: first.items };
  if (query.isError) return { state: "error", retry: () => void query.refetch() };
  return { state: "loading" };
}

/**
 * The open conversations (`all`) and the ones waiting for a person
 * (`waiting`), first page each. The waiting list is read only while `/home`
 * says someone waits: most openings of Inicio save that request (R22.2).
 */
export function useHomeInbox(hasInbox: boolean, someoneWaits: boolean): { latest: InboxPeek | null; waiting: InboxPeek | null; refetch: () => Promise<unknown> } {
  const all = useFirstPage("all", hasInbox);
  const readWaiting = hasInbox && someoneWaits;
  const waiting = useFirstPage("waiting", readWaiting);
  return {
    latest: peekOf(all, hasInbox),
    waiting: peekOf(waiting, readWaiting),
    refetch: () => (hasInbox ? Promise.all([all.refetch(), readWaiting ? waiting.refetch() : null]) : Promise.resolve()),
  };
}

/** The Bandeja's counts (unread, waiting): the same read as the tab's badge. */
export function useHomeCounts(hasInbox: boolean) {
  return useQuery({ queryKey: keys.counts, queryFn: endpoints.counts, enabled: hasInbox, staleTime: 10_000 });
}
