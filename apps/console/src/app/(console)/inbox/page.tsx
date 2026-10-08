import type { Metadata } from "next";
import { z } from "zod";

import { InboxView } from "@/components/inbox/inbox-view";
import { pageTitle } from "@/i18n/metadata";
import { backendFor } from "@/lib/backend";
import type { InboxFilter } from "@/lib/backend/inbox";
import { requireClientPrincipal } from "@/lib/principal";

export const generateMetadata = (): Promise<Metadata> => pageTitle("nav.inbox");

type Search = { c?: string; q?: string; filter?: string; agent?: string };

const FILTERS: readonly InboxFilter[] = ["all", "unread", "waiting", "resolved"];

/**
 * Spec 030 (US5–US10): the client's Bandeja de entrada. Only a client person
 * with the `inbox` module gets here; anyone else is sent where they belong.
 *
 * The first read happens on the server so the list paints with the page; each
 * part degrades on its own (`null` → that part says it could not load).
 * `?c=` opens a conversation — the bell's notice and the Panel's «Atender»
 * land here; `?q=` comes from the search of the top bar (R7.4). `?agent=`
 * narrows to one agent's numbers, only for a client with more than one
 * (R4.2) — an agent that is not one of theirs is ignored.
 */
export default async function InboxPage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requireClientPrincipal("inbox", "/inbox");
  const sp = await searchParams;
  const filter = FILTERS.includes(sp.filter as InboxFilter) ? (sp.filter as InboxFilter) : "all";
  const query = (sp.q ?? "").trim().slice(0, 120);
  const selectedId = z.string().uuid().safeParse(sp.c).success ? (sp.c as string) : null;

  const api = backendFor(principal);
  const agents = await api
    .liteMe()
    .then((me) => (me.agents.length > 1 ? me.agents : []))
    .catch(() => []);
  const agent = agents.some((a) => a.id === sp.agent) ? (sp.agent as string) : null;
  const [page, replies, suggested, open] = await Promise.all([
    api.inboxList({ filter, q: query || undefined, agent: agent ?? undefined }).catch(() => null),
    api.inboxReplies().catch(() => null),
    api
      .inboxSuggestedTags()
      .then((r) => r.tags)
      .catch(() => [] as string[]),
    selectedId
      ? Promise.all([api.inboxDetail(selectedId), api.inboxThread(selectedId)])
          .then(([detail, thread]) => ({ detail, thread }))
          .catch(() => null)
      : Promise.resolve(null),
  ]);

  // A real navigation (the bell's notice, the top-bar search) while already on
  // the Inbox brings new `?c=` / `?q=`: the view starts again from them. The
  // view's own URL updates use `history.replaceState` and do not get here.
  return (
    <InboxView
      key={`${selectedId ?? ""}|${filter}|${query}|${agent ?? ""}`}
      initial={{ filter, query, agent, agents, page, selectedId, open, replies, suggested }}
    />
  );
}
