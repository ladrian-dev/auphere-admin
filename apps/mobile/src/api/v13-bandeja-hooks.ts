import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type { ImageSource } from "expo-image";
import { useEffect, useMemo, useState } from "react";

import type { InboxFilter } from "./endpoints";
import { useForbiddenRereadsMe } from "./hooks";
import { keys } from "./query";
import { avatarUrl, bandejaApi, credentialHeaders, type ChannelType } from "./v13-bandeja";

/**
 * The Bandeja's reads that spec 069 adds. The list's key starts with
 * `keys.inboxLists` (`["inbox", "list", …]`), so everything that invalidates
 * the inbox today — the live line, an action, a push — refreshes it too.
 */
export function inboxListKey(filter: InboxFilter, q: string, agent: string | null, channel: ChannelType | null) {
  return [...keys.conversations(filter, q, agent), channel] as const;
}

export function useInboxList(filter: InboxFilter, q: string, agent: string | null, channel: ChannelType | null, enabled = true) {
  const query = useInfiniteQuery({
    queryKey: inboxListKey(filter, q, agent, channel),
    queryFn: ({ pageParam }) => bandejaApi.conversations({ filter, q, agent, channel, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled,
  });
  useForbiddenRereadsMe(query.error);
  return query;
}

/** The post a comment was left on (spec 049 R4, spec 069 R11.6). Read once; a missing one is `null`. */
export function useCommentPost(conversationId: string, messageId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["inbox", "post", conversationId, messageId] as const,
    queryFn: () => bandejaApi.post(conversationId, messageId),
    enabled,
    staleTime: 10 * 60_000,
    retry: false,
  });
}

/**
 * The contact's photo as an image source, or `null` when the API has none
 * (then the initials). The phone's credential is read when the row or the
 * sheet mounts — it lives in memory, and a renewal is shared — rather than
 * through a query: a list of photos is not a read the inbox invalidates.
 */
export function useAvatarSource(conversationId: string, hasAvatar: boolean): ImageSource | null {
  const [headers, setHeaders] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    if (!hasAvatar) return;
    let live = true;
    void credentialHeaders().then((h) => {
      if (live) setHeaders(h);
    });
    return () => {
      live = false;
    };
  }, [hasAvatar]);
  return useMemo(() => (hasAvatar && headers ? avatarSource(conversationId, headers) : null), [conversationId, hasAvatar, headers]);
}

/** One place that builds the source, for a list that reads the headers once for all its rows. */
export function avatarSource(conversationId: string, headers: Record<string, string>): ImageSource {
  return { uri: avatarUrl(conversationId), headers, cacheKey: `avatar-${conversationId}` };
}
