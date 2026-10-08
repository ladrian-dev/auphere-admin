"use client";

import { Bell } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  formatRelative,
} from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Notification } from "@/lib/backend/onboarding";
import type { ClientModule } from "@/lib/principal-access";

import {
  liteListNotificationsAction,
  liteMarkNotificationReadAction,
  liteReadAllNotificationsAction,
  liteUnreadCountAction,
} from "./lite-notifications-actions";

/**
 * Spec 030 (R15): the client user's bell. Same rhythm as the partner's
 * (soft polling every 60 s, paused when the tab is hidden, refreshed on
 * navigation) but it opens a short list in place — the client console has no
 * notifications page — and each notice takes you where it is solved.
 */
type Props = { modules: readonly ClientModule[] };

const TITLE: Record<string, MessageKey> = {
  "inbox.waiting": "lite.notif.inbox.waiting",
  "client.balance_low": "lite.notif.client.balance_low",
  "client.balance_out": "lite.notif.client.balance_out",
};

function hrefFor(n: Notification, modules: readonly ClientModule[]): string | null {
  if (n.kind === "inbox.waiting") {
    if (!modules.includes("inbox")) return null;
    const id = typeof n.data.conversation_id === "string" ? n.data.conversation_id : null;
    return id ? `/inbox?c=${encodeURIComponent(id)}` : "/inbox";
  }
  if (n.kind.startsWith("client.balance_")) return modules.includes("usage") ? "/usage" : modules.includes("panel") ? "/" : null;
  return null;
}

export function LiteNotificationsBell({ modules }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const [unread, setUnread] = React.useState<number | null>(null);
  const [items, setItems] = React.useState<Notification[] | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    async function tick() {
      if (document.visibilityState === "hidden") return;
      try {
        const res = await liteUnreadCountAction();
        if (alive && res.ok) setUnread(res.data.unread);
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

  async function load() {
    setFailed(false);
    const res = await liteListNotificationsAction();
    if (res.ok) {
      setItems(res.data.items);
      setUnread(res.data.unread);
    } else {
      setFailed(true);
    }
  }

  async function open(n: Notification) {
    if (!n.read) {
      void liteMarkNotificationReadAction({ id: n.id });
      setUnread((u) => (u ? u - 1 : u));
    }
    const href = hrefFor(n, modules);
    if (href) router.push(href);
  }

  async function readAll() {
    const res = await liteReadAllNotificationsAction();
    if (res.ok) {
      setUnread(0);
      setItems((list) => list?.map((n) => ({ ...n, read: true })) ?? list);
    }
  }

  const label = unread ? `${t("notif.bell")} — ${t("notif.bell.unread", { count: unread })}` : t("notif.bell");
  return (
    <DropdownMenu onOpenChange={(isOpen) => (isOpen ? void load() : undefined)}>
      <DropdownMenuTrigger
        aria-label={label}
        className="relative grid size-8 place-items-center rounded-sm text-foreground outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Bell className="size-4" aria-hidden="true" />
        {unread ? (
          <span
            aria-hidden="true"
            className="absolute -top-1 -right-1 grid h-4 min-w-4 place-items-center rounded-full bg-primary px-1 text-xs leading-none font-semibold text-primary-foreground tabular-nums"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 max-w-[calc(100vw-2rem)]">
        <DropdownMenuGroup>
          <div className="flex items-center justify-between gap-2 px-2 py-1">
            <DropdownMenuLabel className="p-0 text-sm font-semibold text-foreground">{t("lite.bell.title")}</DropdownMenuLabel>
            {unread ? (
              <button
                type="button"
                onClick={() => void readAll()}
                className="rounded-sm px-1 text-xs font-medium text-primary outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
              >
                {t("lite.bell.readAll")}
              </button>
            ) : null}
          </div>
          <DropdownMenuSeparator />
          {failed ? (
            <p className="px-2 py-3 text-sm text-muted-foreground" role="status">
              {t("lite.bell.error")}
            </p>
          ) : items === null ? (
            <p className="px-2 py-3 text-sm text-muted-foreground" role="status">
              {t("lite.bell.loading")}
            </p>
          ) : items.length === 0 ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">{t("lite.bell.empty")}</p>
          ) : (
            items.map((n) => {
              const key = TITLE[n.kind];
              if (!key) return null;
              const vars = {
                contact: typeof n.data.contact === "string" ? n.data.contact : t("lite.notif.someone"),
                days: typeof n.data.days_left === "number" ? n.data.days_left : 0,
              };
              return (
                <DropdownMenuItem key={n.id} onClick={() => void open(n)} className="items-start gap-3 py-2">
                  <span
                    aria-hidden="true"
                    className={`mt-2 size-2 shrink-0 rounded-full ${n.read ? "bg-muted-foreground/40" : "bg-primary"}`}
                  />
                  <span className="flex min-w-0 flex-col">
                    <span className={`text-sm text-pretty ${n.read ? "" : "font-medium"}`}>{t(key, vars)}</span>
                    <span className="text-xs text-muted-foreground">{formatRelative(n.created_at, locale)}</span>
                  </span>
                </DropdownMenuItem>
              );
            })
          )}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
