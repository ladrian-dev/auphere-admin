"use client";

import { CheckCheck } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, EmptyState, StatusBadge, cn, formatDateTime } from "@nexus/ui";

import { listNotificationsAction, markAllNotificationsReadAction, markNotificationReadAction } from "@/app/(console)/notifications/actions";
import { useLocale, useT } from "@/i18n/client";
import type { Notification, NotificationPage } from "@/lib/backend/onboarding";

import { notificationText, severityTone } from "./render";

type Filter = "all" | "unread";

export function NotificationsList({ initial, initialFilter }: { initial: NotificationPage; initialFilter: Filter }) {
  const t = useT();
  const locale = useLocale();
  const [filter, setFilter] = React.useState<Filter>(initialFilter);
  const [items, setItems] = React.useState<Notification[]>(initial.items);
  const [cursor, setCursor] = React.useState<string | null>(initial.next_cursor);
  const [unread, setUnread] = React.useState(initial.unread);
  const [pending, start] = React.useTransition();
  const [error, setError] = React.useState<string | null>(null);

  const reload = React.useCallback(
    (f: Filter) => {
      start(async () => {
        setError(null);
        const res = await listNotificationsAction({ unread: f === "unread" ? true : undefined, limit: 20 });
        if (!res.ok) {
          setError(res.message);
          return;
        }
        setItems(res.data.items);
        setCursor(res.data.next_cursor);
        setUnread(res.data.unread);
      });
    },
    [start],
  );

  function changeFilter(f: Filter) {
    setFilter(f);
    reload(f);
  }

  function loadMore() {
    if (!cursor) return;
    start(async () => {
      const res = await listNotificationsAction({ unread: filter === "unread" ? true : undefined, limit: 20, cursor });
      if (!res.ok) {
        setError(res.message);
        return;
      }
      setItems((prev) => [...prev, ...res.data.items]);
      setCursor(res.data.next_cursor);
      setUnread(res.data.unread);
    });
  }

  function markRead(id: string) {
    // optimistic
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setUnread((u) => Math.max(0, u - 1));
    start(async () => {
      const res = await markNotificationReadAction({ id });
      if (!res.ok) {
        toast.error(res.message);
        reload(filter);
      }
    });
  }

  function markAll() {
    start(async () => {
      const res = await markAllNotificationsReadAction();
      if (!res.ok) {
        toast.error(res.message);
        return;
      }
      reload(filter);
    });
  }

  return (
    <div className="flex flex-col gap-4" aria-busy={pending}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="tablist" aria-label={t("notif.title")} className="flex flex-wrap gap-1">
          {(["all", "unread"] as Filter[]).map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              onClick={() => changeFilter(f)}
              className={cn(
                "rounded-full border px-3 py-1 text-sm transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                filter === f ? "border-foreground text-foreground" : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {f === "all" ? t("notif.filter.all") : `${t("notif.filter.unread")} (${unread})`}
            </button>
          ))}
        </div>
        <Button type="button" variant="outline" size="sm" onClick={markAll} disabled={pending || unread === 0}>
          <CheckCheck className="size-4" aria-hidden="true" />
          {t("notif.markAll")}
        </Button>
      </div>

      {error ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-md border border-status-danger/40 bg-status-danger/10 px-4 py-3 text-sm">
          <span className="min-w-0 flex-1 text-pretty">{error}</span>
          <Button size="sm" variant="outline" onClick={() => reload(filter)}>
            {t("common.retry")}
          </Button>
        </div>
      ) : null}

      {items.length === 0 && !pending ? (
        <EmptyState title={filter === "unread" ? t("notif.empty.unread") : t("notif.empty.title")} description={filter === "unread" ? undefined : t("notif.empty.body")} readonly />
      ) : (
        <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-card">
          {items.map((n) => (
            <li key={n.id} className={cn("flex min-w-0 flex-wrap items-start gap-3 px-4 py-3", !n.read && "bg-primary/5")}>
              <StatusBadge tone={severityTone(n.severity)} pulse={!n.read && n.severity !== "info"} className="mt-1 shrink-0">
                {t(n.severity === "critical" ? "notif.severity.critical" : n.severity === "warning" ? "notif.severity.warning" : "notif.severity.info")}
              </StatusBadge>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <p className={cn("min-w-0 text-sm text-pretty", !n.read && "font-medium")}>{notificationText(locale, n)}</p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-muted-foreground">
                  <time dateTime={n.created_at}>{formatDateTime(n.created_at, locale)}</time>
                  <span className="truncate" title={n.kind}>
                    {n.kind}
                  </span>
                  {n.external_client_ref ? (
                    <Link className="underline underline-offset-4 hover:text-foreground" href={`/clients/${encodeURIComponent(n.external_client_ref)}`}>
                      {t("notif.openClient")}
                    </Link>
                  ) : null}
                </div>
              </div>
              {!n.read ? (
                <Button type="button" variant="ghost" size="sm" className="shrink-0" onClick={() => markRead(n.id)} aria-label={t("notif.markRead")}>
                  {t("notif.markRead")}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {cursor ? (
        <div>
          <Button type="button" variant="outline" onClick={loadMore} disabled={pending}>
            {t("notif.loadMore")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
