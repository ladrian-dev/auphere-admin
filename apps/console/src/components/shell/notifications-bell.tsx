"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import {
  Button,
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
  Skeleton,
  StatusDot,
  cn,
  formatRelative,
} from "@nexus/ui";

import { attentionAction, listNotificationsAction, markAllNotificationsReadAction } from "@/app/(console)/notifications/actions";
import { attentionKey } from "@/components/attention/attention-model";
import { AttentionRow } from "@/components/attention/attention-row";
import { notificationText, severityTone } from "@/components/notifications/render";
import { useLocale, useT } from "@/i18n/client";
import type { PanelAttention } from "@/lib/backend/home-usage";
import type { Notification } from "@/lib/backend/onboarding";

/**
 * The unread count (CP-29): soft polling every 60 s, paused when the tab is
 * hidden, refreshed on route change. Never blocks render. Shared by today's
 * bell and the new one so both count the same way.
 *
 * It reads `GET /api/notifications/count`, not server actions: a server action
 * goes through the router's queue, and one that was still running when a link
 * was clicked put the page back to where it started once it finished (spec
 * 074). A background read must never navigate.
 */
function useUnreadNotifications(initialUnread: number | null) {
  const pathname = usePathname();
  const [unread, setUnread] = React.useState<number | null>(initialUnread);

  React.useEffect(() => {
    let alive = true;
    async function tick() {
      if (document.visibilityState === "hidden") return;
      try {
        // Spec 071 (3.1): el número es lo que te necesita ahora más los avisos
        // sin leer; la ruta ya lo suma. La API no cuenta como «sin leer» los de una condición.
        const res = await fetch("/api/notifications/count", { cache: "no-store", headers: { accept: "application/json" } });
        if (!res.ok) return;
        const body = (await res.json()) as { unread: number };
        if (alive) setUnread(body.unread);
      } catch {
        /* keep the last value */
      }
    }
    void tick();
    const h = setInterval(tick, 60_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      alive = false;
      clearInterval(h);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [pathname]);

  return [unread, setUnread] as const;
}

function UnreadBadge({ unread }: { unread: number | null }) {
  if (!unread) return null;
  return (
    <span
      aria-hidden="true"
      className="absolute -top-2 -right-2 grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-xs leading-none font-semibold text-primary-foreground tabular-nums ring-2 ring-background"
    >
      {unread > 99 ? "99+" : unread}
    </span>
  );
}

/**
 * Header bell (CP-29): unread badge, soft polling every 60 s (paused when
 * the tab is hidden), refreshed on route change. Never blocks render.
 * Today's console (v1): the bell goes to the Notifications page.
 */
export function NotificationsBell({ initialUnread }: { initialUnread: number | null }) {
  const t = useT();
  const pathname = usePathname();
  const [unread] = useUnreadNotifications(initialUnread);

  const label = unread ? `${t("notif.bell")} — ${t("notif.bell.unread", { count: unread })}` : t("notif.bell");
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      nativeButton={false}
      className="relative"
      aria-label={label}
      aria-current={pathname === "/notifications" ? "page" : undefined}
      render={<Link href="/notifications" />}
    >
      <Bell className="size-4" aria-hidden="true" />
      <UnreadBadge unread={unread} />
    </Button>
  );
}

const LIMIT = 5;

type Feed =
  | { state: "loading" }
  | { state: "error" }
  | { state: "ready"; items: Notification[]; markError: boolean; announce: boolean };
/** Spec 071: «Ahora», la lista viva. `null`: no se pudo leer. */
type Now = PanelAttention[] | null;

/**
 * Spec 047 (R47.3): the bell of the new frame opens a panel with the 5
 * latest notices, «Marcar todo como leído» and «Ver todas».
 *
 * Its five states: loading (rows of skeleton the size of a row), empty (it
 * says so and still offers «Ver todas»), error (in the console's words, with
 * «Reintentar»), partial (the list arrived but «Marcar todo» failed: the list
 * stays and an inline alert says what failed) and ideal. The panel is a
 * non-modal dialog (`Popover`): Escape closes it and focus goes back to the bell.
 */
export function NotificationsBellMenu({ initialUnread }: { initialUnread: number | null }) {
  const t = useT();
  const locale = useLocale();
  const [unread, setUnread] = useUnreadNotifications(initialUnread);
  const [open, setOpen] = React.useState(false);
  const [feed, setFeed] = React.useState<Feed>({ state: "loading" });
  const [marking, setMarking] = React.useState(false);
  const [now, setNow] = React.useState<Now>([]);
  const seq = React.useRef(0);

  const load = React.useCallback(async () => {
    const my = ++seq.current;
    setFeed({ state: "loading" });
    try {
      const [res, live] = await Promise.all([listNotificationsAction({ limit: LIMIT }), attentionAction().catch(() => null)]);
      if (my !== seq.current) return;
      const items = live && live.ok ? live.data.items : null;
      setNow(items);
      if (!res.ok) return setFeed({ state: "error" });
      setFeed({ state: "ready", items: res.data.items.slice(0, LIMIT), markError: false, announce: false });
      setUnread(res.data.unread + (items?.length ?? 0));
    } catch {
      if (my === seq.current) setFeed({ state: "error" });
    }
  }, [setUnread]);

  async function markAll() {
    if (feed.state !== "ready") return;
    setMarking(true);
    try {
      const res = await markAllNotificationsReadAction();
      if (!res.ok) return setFeed({ ...feed, markError: true, announce: false });
      setFeed({ state: "ready", items: feed.items.map((n) => (n.condition ? n : { ...n, read: true })), markError: false, announce: true });
      // Lo de «Ahora» no se marca como leído: se arregla (3.3).
      setUnread(now?.length ?? 0);
    } catch {
      setFeed({ ...feed, markError: true, announce: false });
    } finally {
      setMarking(false);
    }
  }

  const label = unread ? `${t("notif.bell")} — ${t("notif.bell.unread", { count: unread })}` : t("notif.bell");
  // Spec 071 (3.3): «Marcar todo como leído» solo toca los informativos.
  const anyUnread = feed.state === "ready" && feed.items.some((n) => !n.read && !n.condition);

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) void load();
      }}
    >
      <PopoverTrigger
        // Como el prototipo: la campana con su borde a la vista, de la altura del buscador.
        render={<Button variant="outline" size="icon-sm" className="relative" aria-label={label} />}
      >
        <Bell className="size-4" aria-hidden="true" />
        <UnreadBadge unread={unread} />
      </PopoverTrigger>
      <PopoverContent className="w-96">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <PopoverTitle className="flex-1">{t("notif.title")}</PopoverTitle>
          {anyUnread ? (
            <Button variant="ghost" size="sm" onClick={markAll} disabled={marking}>
              {t("shell.bell.markAll")}
            </Button>
          ) : null}
        </div>

        <div className="min-h-0 px-2 py-2">
          {/* Spec 071 (D1): «Ahora», lo que te necesita y se arregla aquí. */}
          {feed.state !== "loading" && (now === null || now.length > 0) ? (
            <section aria-labelledby="bell-now-h" className="mb-1 border-b border-border pb-1" data-slot="bell-now">
              <h3 id="bell-now-h" className="px-2 pt-1 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
                {t("att.bell.now")}
              </h3>
              {now === null ? (
                <p role="status" className="px-2 py-2 text-xs text-muted-foreground">
                  {t("att.bell.nowError")}
                </p>
              ) : (
                <ul className="divide-y divide-border px-2">
                  {now.map((row) => (
                    <AttentionRow key={attentionKey(row)} row={row} compact />
                  ))}
                </ul>
              )}
            </section>
          ) : null}
          {feed.state !== "loading" && (now === null || now.length > 0) ? (
            <h3 className="px-2 pt-2 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">{t("att.bell.before")}</h3>
          ) : null}
          {feed.state === "loading" ? (
            <div role="status" aria-label={t("ui.loading")} className="flex flex-col">
              {Array.from({ length: 3 }, (_, i) => (
                <div key={i} className="flex items-start gap-3 px-2 py-3">
                  <Skeleton className="mt-1 size-2 rounded-full" />
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
              ))}
            </div>
          ) : feed.state === "error" ? (
            <div role="alert" className="flex flex-col items-center gap-3 px-4 py-6 text-center">
              <p className="text-sm text-pretty">{t("notif.error")}</p>
              <Button variant="outline" size="sm" onClick={() => void load()}>
                {t("ui.retry")}
              </Button>
            </div>
          ) : feed.items.length === 0 ? (
            <div className="flex flex-col items-center gap-1 px-4 py-6 text-center">
              <p className="text-sm font-medium">{t("notif.empty.title")}</p>
              <p className="text-xs text-pretty text-muted-foreground">{t("notif.empty.body")}</p>
            </div>
          ) : (
            <ul className="flex flex-col">
              {feed.items.map((n) => {
                const text = notificationText(locale, n);
                const href = n.href ?? (n.external_client_ref ? `/clients/${encodeURIComponent(n.external_client_ref)}` : "/notifications");
                return (
                  <li key={n.id}>
                    <Link
                      href={href}
                      onClick={() => setOpen(false)}
                      className="flex min-w-0 items-start gap-3 rounded-sm px-2 py-3 hover:bg-muted"
                    >
                      <StatusDot tone={n.handled ? "muted" : severityTone(n.severity)} className="mt-2" />
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className={cn("text-sm text-pretty", !n.read && !n.condition && "font-medium", n.handled && "text-muted-foreground")}>
                          {text}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatRelative(n.created_at, locale)}
                          {n.handled ? (
                            <>
                              {" · "}
                              <span data-slot="bell-resolved">{t("att.bell.resolved")}</span>
                            </>
                          ) : !n.read && !n.condition ? (
                            <>
                              {" · "}
                              <span>{t("shell.bell.unread")}</span>
                            </>
                          ) : null}
                        </span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          {feed.state === "ready" && feed.markError ? (
            <p role="alert" className="mx-2 mt-2 rounded-sm bg-status-danger-bg px-3 py-2 text-xs text-status-danger-text">
              {t("shell.bell.markAllError")}
            </p>
          ) : null}
          <p role="status" className="sr-only">
            {feed.state === "ready" && feed.announce ? t("notif.empty.unread") : ""}
          </p>
        </div>

        <div className="border-t border-border px-2 py-2">
          <Link
            href="/notifications"
            onClick={() => setOpen(false)}
            className="flex h-10 items-center justify-center rounded-sm text-sm font-medium text-primary-text hover:bg-muted"
          >
            {t("shell.bell.viewAll")}
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
