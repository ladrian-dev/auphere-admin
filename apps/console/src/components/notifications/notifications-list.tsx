"use client";

import { Check, CircleAlert, Info, TriangleAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, Card, EmptyState, PageHeader, SegmentedControl, StatusBadge, cn, formatRelative } from "@nexus/ui";

import { listNotificationsAction, markAllNotificationsReadAction, markNotificationReadAction } from "@/app/(console)/notifications/actions";
import { BalanceButton } from "@/components/money/balance-button";
import { useLocale, useT } from "@/i18n/client";
import type { Notification, NotificationPage } from "@/lib/backend/onboarding";

import { notificationText, severityTone } from "./render";

type Filter = "all" | "unread";

/** Spec 047 (45.1, 45.7): el aviso «Pedir saldo» lleva «Asignar saldo» en el propio aviso, para quien puede asignar. */
function balanceRequestRef(n: Notification): string | null {
  if (n.kind !== "client.balance_request") return null;
  const fromData = typeof n.data?.external_client_ref === "string" ? n.data.external_client_ref : null;
  return n.external_client_ref ?? fromData;
}

export function NotificationsList({
  initial,
  initialFilter,
  clientNames,
  canAssign = false,
}: {
  initial: NotificationPage;
  initialFilter: Filter;
  clientNames?: Record<string, string>;
  canAssign?: boolean;
}) {
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

  const SEVERITY_ICON = { critical: CircleAlert, warning: TriangleAlert, info: Info } as const;

  // Spec 047 (prototipo «Consola de partners v2»): la cabecera de la página es
  // de este componente porque «Marcar todas como leídas» depende de cuántas
  // quedan sin leer, y eso cambia aquí sin volver al servidor.
  return (
    <>
      <PageHeader
        size="display"
        title={t("notif.title")}
        description={t("notif.subtitle")}
        actions={
          unread > 0 ? (
            <Button type="button" variant="outline" onClick={markAll} disabled={pending}>
              <Check aria-hidden="true" />
              {t("notif.markAll")}
            </Button>
          ) : undefined
        }
      />
      <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
        <SegmentedControl
          aria-label={t("proto.notif.filter")}
          value={filter}
          onValueChange={changeFilter}
          options={[
            { value: "all", label: t("notif.filter.all") },
            { value: "unread", label: `${t("notif.filter.unread")} (${unread})` },
          ]}
        />

        {error ? (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-status-danger/40 bg-status-danger/10 px-4 py-3 text-sm">
            <span className="min-w-0 flex-1 text-pretty">{error}</span>
            <Button size="sm" variant="outline" onClick={() => reload(filter)}>
              {t("common.retry")}
            </Button>
          </div>
        ) : null}

        {items.length === 0 && !pending ? (
          <EmptyState title={filter === "unread" ? t("notif.empty.unread") : t("notif.empty.title")} description={filter === "unread" ? undefined : t("notif.empty.body")} readonly />
        ) : (
          <Card className="py-0" data-slot="notifications-card">
            <ul className="flex flex-col divide-y divide-border">
              {items.map((n) => {
                const Icon = SEVERITY_ICON[n.severity === "critical" ? "critical" : n.severity === "warning" ? "warning" : "info"];
                const ref = balanceRequestRef(n);
                return (
                  <li key={n.id} className={cn("flex min-w-0 flex-wrap items-center gap-3 px-4 py-3", n.read && "opacity-75")}>
                    {/* El punto de sin leer, o su hueco: así las filas no bailan al leerlas. */}
                    {!n.read ? (
                      <span role="img" aria-label={t("proto.notif.unread")} className="size-2 shrink-0 rounded-full bg-primary" />
                    ) : (
                      <span aria-hidden="true" className="size-2 shrink-0" />
                    )}
                    <StatusBadge tone={severityTone(n.severity)} dot={false} pulse={!n.read && n.severity !== "info"} className="shrink-0">
                      <Icon aria-hidden="true" className="size-3" />
                      {t(n.severity === "critical" ? "notif.severity.critical" : n.severity === "warning" ? "notif.severity.warning" : "notif.severity.info")}
                    </StatusBadge>
                    <div className="flex min-w-0 flex-1 flex-col">
                      <p className={cn("min-w-0 text-sm text-pretty", !n.read && "font-medium")}>{notificationText(locale, n, clientNames)}</p>
                      <time dateTime={n.created_at} className="text-xs text-muted-foreground" title={n.created_at}>
                        {formatRelative(n.created_at, locale)}
                      </time>
                      {canAssign && ref ? (
                        <BalanceButton refId={ref} name={clientNames?.[ref] ?? ref} mode="assign" size="xs" className="mt-2 w-fit" />
                      ) : null}
                    </div>
                    {n.href ? (
                      <Button variant="ghost" size="sm" nativeButton={false} render={<Link href={n.href} />}>
                        {t("notif.open")}
                      </Button>
                    ) : n.external_client_ref ? (
                      <Button variant="ghost" size="sm" nativeButton={false} render={<Link href={`/clients/${encodeURIComponent(n.external_client_ref)}`} />}>
                        {t("notif.openClient")}
                      </Button>
                    ) : null}
                    {!n.read ? (
                      <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={() => markRead(n.id)}>
                        {t("notif.markRead")}
                      </Button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
        {cursor ? (
          <div>
            <Button type="button" variant="outline" onClick={loadMore} disabled={pending}>
              {t("notif.loadMore")}
            </Button>
          </div>
        ) : null}
      </div>
    </>
  );
}
