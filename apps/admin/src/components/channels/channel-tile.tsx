import Link from "next/link";

import { cn } from "@nexus/ui";

import { ChannelIcon } from "@/components/brand/channel-icon";
import type { ChannelCatalogEntry } from "@/lib/backend";

import { AVAILABILITY_LABEL, canStart } from "./labels";

/**
 * Spec 035: a channel of the catalog, laid out like Chatwoot's «Elegir canal»
 * tile — the mark in a circle, the name, one line of what it does. A channel
 * that cannot start yet keeps its place with its state («Pendiente»,
 * «Próximamente») and is not a link (constitution §V, amendment 1.1.0: the
 * operator panel only).
 */
export function ChannelTile({ entry, href }: { entry: ChannelCatalogEntry; href?: string }) {
  const startable = canStart(entry.availability) && Boolean(href);
  const badge = AVAILABILITY_LABEL[entry.availability];
  const body = (
    <>
      <span className="grid size-10 place-items-center rounded-full bg-muted text-foreground">
        <ChannelIcon channel={entry.key} className="size-5" />
      </span>
      <span className="mt-6 flex items-center gap-2">
        <span className="text-base font-medium">{entry.name}</span>
        {badge ? (
          <span
            className={cn(
              "rounded-sm px-2 py-1 text-xs leading-none font-medium",
              entry.availability === "beta" ? "bg-status-info-bg text-status-info-text" : "bg-muted text-muted-foreground",
            )}
          >
            {badge}
          </span>
        ) : null}
      </span>
      <span className="mt-2 text-sm text-pretty text-muted-foreground">{entry.description}</span>
      {!startable && entry.note ? <span className="mt-2 text-xs text-muted-foreground">{entry.note}</span> : null}
    </>
  );
  const frame = "flex h-full flex-col items-start rounded-md p-6 text-left ring-1 ring-foreground/10";
  if (startable && href) {
    return (
      <Link
        href={href}
        className={cn(frame, "bg-card outline-none transition-shadow hover:shadow-md hover:ring-primary/50 focus-visible:ring-2 focus-visible:ring-ring")}
      >
        {body}
      </Link>
    );
  }
  return (
    <div aria-disabled="true" className={cn(frame, "bg-muted/30 opacity-70")}>
      {body}
    </div>
  );
}
