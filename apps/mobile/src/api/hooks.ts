import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { endpoints, type InboxFilter } from "./endpoints";
import { ApiError } from "./errors";
import { keys } from "./query";
import { demo } from "./reservas";

/**
 * The reads the screens make. A 403 on a module's read means the module went
 * away while the screen was open (R3.5): re-read `/me`, and the tabs follow.
 */
export function useForbiddenRereadsMe(error: unknown) {
  const qc = useQueryClient();
  useEffect(() => {
    if (error instanceof ApiError && error.status === 403) void qc.invalidateQueries({ queryKey: keys.me });
  }, [error, qc]);
}

/** The public config: the minimum version and whether Google is on (R1.3, R13). */
export function useAppConfig() {
  return useQuery({ queryKey: keys.appConfig, queryFn: endpoints.config, staleTime: 5 * 60_000, retry: 1 });
}

/** In a development build with example Reservas, `/me` gains the module (spec 044, D2). */
const withDemo = demo;
const readMe = withDemo ? () => endpoints.me().then((me) => withDemo.me(me)) : endpoints.me;

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: readMe, staleTime: 30_000 });
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

/** Whether the client has a module (`/me.nav`): the screens of spec 047 ask for `agents` and `business`. */
export function useHasModule(module: string): boolean {
  const me = useMe();
  return me.data?.nav.includes(module) ?? false;
}

/** Spec 047 (50.1): the client's agents, with their state, their numbers and what the person can do. */
/** A location's week (its own or the business's it inherits); nothing while `id` is null. */
export function useLocationHours(id: string | null) {
  return useQuery({ queryKey: keys.locationHours(id ?? ""), queryFn: () => endpoints.locationHours(id!), enabled: id !== null });
}

export function useAgents(enabled = true) {
  const q = useQuery({ queryKey: keys.agents, queryFn: endpoints.agents, enabled });
  useForbiddenRereadsMe(q.error);
  return q;
}

/** Spec 047 (50.1): the four sections the business edits — hours, special dates, services, locations — with their history. */
export function useBusiness(enabled = true) {
  const q = useQuery({ queryKey: keys.business, queryFn: endpoints.business, enabled });
  useForbiddenRereadsMe(q.error);
  return q;
}

/** This phone's notices; with example Reservas (spec 044, D2) they live in memory, as the API would reject its kinds. */
export function useNotices(enabled: boolean) {
  return useQuery({ queryKey: keys.notices, queryFn: withDemo ? () => withDemo.notices() : endpoints.notices, enabled });
}
