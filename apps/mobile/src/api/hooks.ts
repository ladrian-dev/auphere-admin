import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { endpoints, type InboxFilter } from "./endpoints";
import { ApiError } from "./errors";
import { keys } from "./query";

/**
 * The reads the screens make. A 403 on a module's read means the module went
 * away while the screen was open (R3.5): re-read `/me`, and the tabs follow.
 */
function useForbiddenRereadsMe(error: unknown) {
  const qc = useQueryClient();
  useEffect(() => {
    if (error instanceof ApiError && error.status === 403) void qc.invalidateQueries({ queryKey: keys.me });
  }, [error, qc]);
}

/** The public config: the minimum version and whether Google is on (R1.3, R13). */
export function useAppConfig() {
  return useQuery({ queryKey: keys.appConfig, queryFn: endpoints.config, staleTime: 5 * 60_000, retry: 1 });
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: endpoints.me, staleTime: 30_000 });
}

export function useHome() {
  const q = useQuery({ queryKey: keys.home, queryFn: endpoints.home });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useUsageSummary() {
  const q = useQuery({ queryKey: keys.usageSummary, queryFn: endpoints.usageSummary });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useUsageSpend(days: number, agent: string | null, enabled = true) {
  const q = useQuery({
    queryKey: keys.usageSpend(days, agent),
    queryFn: () => endpoints.usageSpend(days, agent),
    placeholderData: (prev) => prev,
    enabled,
  });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useConversations(filter: InboxFilter, q: string, agent: string | null) {
  const query = useInfiniteQuery({
    queryKey: keys.conversations(filter, q, agent),
    queryFn: ({ pageParam }) => endpoints.conversations({ filter, q, agent, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  useForbiddenRereadsMe(query.error);
  return query;
}

export function useCounts(enabled: boolean) {
  return useQuery({ queryKey: keys.counts, queryFn: endpoints.counts, enabled, staleTime: 10_000 });
}

export function useConversation(id: string) {
  const q = useQuery({ queryKey: keys.conversation(id), queryFn: () => endpoints.conversation(id) });
  useForbiddenRereadsMe(q.error);
  return q;
}

export function useThread(id: string) {
  return useInfiniteQuery({
    queryKey: keys.thread(id),
    queryFn: ({ pageParam }) => endpoints.thread(id, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
}

export function useReplies(enabled: boolean) {
  return useQuery({ queryKey: keys.replies, queryFn: endpoints.replies, enabled, staleTime: 60_000 });
}

export function useSuggestedTags(enabled: boolean) {
  return useQuery({ queryKey: keys.tags, queryFn: endpoints.suggestedTags, enabled, staleTime: 60_000 });
}

export function useNotices(enabled: boolean) {
  return useQuery({ queryKey: keys.notices, queryFn: endpoints.notices, enabled });
}
