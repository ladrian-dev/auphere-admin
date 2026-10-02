import { formatRelative } from "@nexus/ui";

import type { AuditEntry } from "@/lib/backend";
import type { Locale } from "@/i18n/messages";

/** «Actividad reciente» (spec 026, Historia 6): the last things that happened, in words. */
export function ActivityFeed({ items, locale, empty }: { items: AuditEntry[]; locale: Locale; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ol className="flex flex-col gap-3">
      {items.map((e) => (
        <li key={e.id} className="flex min-w-0 flex-col gap-1">
          <span className="text-sm text-pretty">{e.summary}</span>
          <time dateTime={e.at} className="text-xs text-muted-foreground">
            {formatRelative(e.at, locale)}
          </time>
        </li>
      ))}
    </ol>
  );
}
