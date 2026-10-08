"use client";

import { Search } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { ShortcutKbd } from "@nexus/ui";

import { INBOX_SEARCH_ID } from "@/components/inbox/conversation-list";
import { useT } from "@/i18n/client";
import type { ClientModule } from "@/lib/principal-access";

/**
 * Spec 030 (US12, R7.4): searching from any screen of the client console.
 * ⌘K / Ctrl+K focuses it; Enter opens the Inbox filtered by what was typed.
 * On the Inbox itself the list has its own search box, so this one steps
 * aside and the shortcut focuses that box instead. A client without the
 * Inbox has nothing to search here, so there is no field and no shortcut.
 */
export function LiteSearch({ modules }: { modules: readonly ClientModule[] }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const enabled = modules.includes("inbox");
  const onInbox = pathname === "/inbox" || pathname.startsWith("/inbox/");
  const input = React.useRef<HTMLInputElement>(null);
  const [q, setQ] = React.useState("");

  React.useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const inPage = document.getElementById(INBOX_SEARCH_ID);
        (inPage ?? input.current)?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);

  if (!enabled || onInbox) return null;
  return (
    <form
      role="search"
      className="hidden h-8 w-64 items-center gap-2 rounded-sm border border-border bg-card px-3 text-muted-foreground focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring sm:flex"
      onSubmit={(e) => {
        e.preventDefault();
        const v = q.trim();
        router.push(v ? `/inbox?q=${encodeURIComponent(v)}` : "/inbox");
        setQ("");
      }}
    >
      <Search className="size-4 shrink-0" aria-hidden="true" />
      <label htmlFor="lite-search" className="sr-only">
        {t("inbox.globalSearch")}
      </label>
      <input
        id="lite-search"
        ref={input}
        type="search"
        value={q}
        maxLength={120}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("inbox.globalSearch")}
        className="min-w-0 flex-1 border-0 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
      />
      <ShortcutKbd keyName="K" aria-hidden="true" />
    </form>
  );
}
