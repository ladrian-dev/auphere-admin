import { Inbox, Search } from "lucide-react";

import { Alert, AlertDescription, Button, NativeSelect, Skeleton, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { InboxCounts, InboxFilter, InboxPage } from "@/lib/backend/inbox";

import { ConversationRow } from "./conversation-row";

/** The id the global search (⌘K) focuses — R7.4. */
export const INBOX_SEARCH_ID = "inbox-search";

const FILTERS: InboxFilter[] = ["all", "unread", "waiting", "resolved"];

/**
 * The list column (spec 030, R7): search, the four filters — plus the agent,
 * for a client with more than one (R4.2) — and the rows.
 * Five states, each its own: loading (rows the size of real ones), an inbox
 * that never had a conversation, filters that match nothing, a failed read,
 * and the list. «Más» loads the next page by cursor.
 */
export function ConversationList({
  page,
  loading,
  failed,
  filter,
  query,
  agent,
  agents,
  counts,
  selectedId,
  now,
  loadingMore,
  onFilter,
  onQuery,
  onAgent,
  onOpen,
  onMore,
  onRetry,
  onClear,
}: {
  page: InboxPage | null;
  loading: boolean;
  failed: boolean;
  filter: InboxFilter;
  query: string;
  agent: string | null;
  /** Empty with one agent: then there is nothing to choose. */
  agents: { id: string; name: string }[];
  counts: InboxCounts;
  selectedId: string | null;
  now: Date;
  loadingMore: boolean;
  onFilter: (f: InboxFilter) => void;
  onQuery: (q: string) => void;
  onAgent: (agent: string | null) => void;
  onOpen: (id: string) => void;
  onMore: () => void;
  onRetry: () => void;
  onClear: () => void;
}) {
  const t = useT();
  const label = (f: InboxFilter) =>
    f === "all"
      ? t("inbox.filter.all")
      : f === "unread"
        ? t("inbox.filter.unread")
        : f === "waiting"
          ? counts.waiting > 0
            ? t("inbox.filter.waiting.count", { count: counts.waiting })
            : t("inbox.filter.waiting")
          : t("inbox.filter.resolved");

  return (
    <section aria-label={t("inbox.list")} className="flex min-h-0 min-w-0 flex-col">
      <div className="flex flex-col gap-2 p-3">
        <label className="flex h-8 items-center gap-2 rounded-sm border border-border-strong bg-card px-3 text-muted-foreground focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring">
          <Search className="size-4 shrink-0" aria-hidden="true" />
          <span className="sr-only">{t("inbox.search.label")}</span>
          <input
            id={INBOX_SEARCH_ID}
            type="search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder={t("inbox.search")}
            maxLength={120}
            className="min-w-0 flex-1 border-0 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>
        <div role="group" aria-label={t("inbox.filters")} className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <Button
              key={f}
              type="button"
              size="sm"
              variant={filter === f ? "secondary" : "ghost"}
              aria-pressed={filter === f}
              onClick={() => onFilter(f)}
              className={cn(f === "waiting" && counts.waiting > 0 && filter !== f && "text-status-warning-text")}
            >
              {label(f)}
            </Button>
          ))}
        </div>
        {agents.length > 1 ? (
          <NativeSelect
            size="sm"
            aria-label={t("inbox.filter.agent")}
            value={agent ?? ""}
            onChange={(e) => onAgent(e.target.value || null)}
          >
            <option value="">{t("inbox.filter.agent.all")}</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </NativeSelect>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto border-t border-border-soft">
        {failed ? (
          <div className="flex flex-col items-start gap-3 p-3">
            <Alert variant="destructive" role="alert">
              <AlertDescription>{t("inbox.error")}</AlertDescription>
            </Alert>
            <Button type="button" variant="outline" size="sm" disabled={loading} onClick={onRetry}>
              {t("inbox.thread.retry")}
            </Button>
          </div>
        ) : loading && !page ? (
          <ListSkeleton label={t("inbox.list.loading")} />
        ) : page && page.items.length === 0 ? (
          page.has_any ? (
            <div role="status" className="flex flex-col items-center gap-3 px-5 py-10 text-center">
              <p className="text-sm text-muted-foreground text-pretty">{t("inbox.empty.filtered")}</p>
              <Button type="button" variant="outline" size="sm" onClick={onClear}>
                {t("inbox.empty.clear")}
              </Button>
            </div>
          ) : (
            <div role="status" className="flex flex-col items-center gap-3 px-5 py-12 text-center">
              <span className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
                <Inbox className="size-5" aria-hidden="true" />
              </span>
              <p className="text-sm font-medium text-balance">{t("inbox.empty.title")}</p>
              <p className="max-w-xs text-sm text-muted-foreground text-pretty">{t("inbox.empty.body")}</p>
            </div>
          )
        ) : page ? (
          <ul className="flex flex-col" aria-busy={loading || undefined}>
            {page.items.map((c) => (
              <li key={c.id}>
                <ConversationRow conversation={c} selected={c.id === selectedId} onOpen={onOpen} now={now} />
              </li>
            ))}
            {page.next_cursor ? (
              <li className="p-3">
                <Button type="button" variant="outline" size="sm" className="w-full" disabled={loadingMore} onClick={onMore}>
                  {t("inbox.list.more")}
                </Button>
              </li>
            ) : null}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

function ListSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex items-start gap-3 border-b border-border-soft px-3 py-3">
          <Skeleton className="size-10 shrink-0 rounded-full" />
          <div className="flex min-w-0 flex-1 flex-col gap-2 pt-1">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-4/5" />
          </div>
        </div>
      ))}
    </div>
  );
}
