"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { Button } from "@nexus/ui";

import { unreadCountAction } from "@/app/(console)/notifications/actions";
import { useT } from "@/i18n/client";

/**
 * Header bell (CP-29): unread badge, soft polling every 60 s (paused when
 * the tab is hidden), refreshed on route change. Never blocks render.
 */
export function NotificationsBell({ initialUnread }: { initialUnread: number | null }) {
  const t = useT();
  const pathname = usePathname();
  const [unread, setUnread] = React.useState<number | null>(initialUnread);

  React.useEffect(() => {
    let alive = true;
    async function tick() {
      if (document.visibilityState === "hidden") return;
      try {
        const res = await unreadCountAction();
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
      {unread ? (
        <span
          aria-hidden="true"
          className="absolute -top-1 -right-1 grid h-4 min-w-4 place-items-center rounded-full bg-primary px-1 font-mono text-xs leading-none text-primary-foreground tabular-nums"
        >
          {unread > 99 ? "99+" : unread}
        </span>
      ) : null}
    </Button>
  );
}
