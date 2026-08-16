"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useT } from "@/i18n/client";

const TABS = [
  { seg: "", key: "clients.tabs.overview" },
  { seg: "agent", key: "clients.tabs.agent" },
  { seg: "tools", key: "clients.tabs.tools" },
  { seg: "skills", key: "clients.tabs.skills" },
  { seg: "knowledge", key: "clients.tabs.knowledge" },
  { seg: "playground", key: "clients.tabs.playground" },
  { seg: "channels", key: "clients.tabs.channels" },
  { seg: "conversations", key: "clients.tabs.conversations" },
  { seg: "settings", key: "clients.tabs.settings" },
] as const;

export function ClientTabs({ refId }: { refId: string }) {
  const t = useT();
  const pathname = usePathname();
  const base = `/clients/${encodeURIComponent(refId)}`;
  return (
    <nav aria-label={t("clients.tabs.overview")} className="-mt-2 flex gap-1 overflow-x-auto border-b border-border">
      {TABS.map((tab) => {
        const href = tab.seg ? `${base}/${tab.seg}` : base;
        const active = tab.seg ? pathname.startsWith(href) : pathname === base;
        return (
          <Link
            key={tab.seg}
            href={href}
            aria-current={active ? "page" : undefined}
            className={[
              "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm transition-colors",
              active ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            ].join(" ")}
          >
            {t(tab.key)}
          </Link>
        );
      })}
    </nav>
  );
}
