import Link from "next/link";

import { cn } from "@nexus/ui";

import { ChannelLogo } from "@/components/brand/channel-logo";
import type { MessageKey } from "@/i18n/messages";
import type { ChannelCatalogEntry } from "@/lib/backend/channels";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * Spec 046: a channel of the catalog — the app's own icon, its name and one
 * line of what it does. Constitution §V, amendment 1.2.0: a channel that
 * cannot start keeps its place with its state («Pendiente»,
 * «Próximamente»), is not a link and never promises a date.
 */
export function ChannelTile({ entry, href, t }: { entry: ChannelCatalogEntry; href: string; t: T }) {
  const startable = entry.availability === "available";
  const frame = "flex h-full flex-col items-start rounded-md p-5 text-left ring-1";
  const body = (
    <>
      <ChannelLogo channel={entry.key} size="xl" className={startable ? undefined : "grayscale"} />
      <span className="mt-5 flex flex-wrap items-center gap-2">
        <span className="text-base font-medium">{entry.name}</span>
        {startable ? null : (
          <span className="rounded-sm bg-muted px-2 py-1 text-xs leading-none font-medium text-muted-foreground">
            {t(entry.availability === "pending" ? "chw.availability.pending" : "chw.availability.coming_soon")}
          </span>
        )}
      </span>
      <span className="mt-2 text-sm text-pretty text-muted-foreground">{entry.description}</span>
      {!startable && entry.note ? <span className="mt-2 text-xs text-muted-foreground">{entry.note}</span> : null}
      {startable ? <span className="mt-auto pt-4 text-sm font-medium text-primary-text underline-offset-4 group-hover:underline">{t("chw.tile.start")}</span> : null}
    </>
  );
  if (startable) {
    return (
      <Link
        href={href}
        className={cn(
          frame,
          "group bg-card ring-foreground/10 outline-none transition-shadow hover:shadow-md hover:ring-primary/50 focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        {body}
      </Link>
    );
  }
  return (
    <div aria-disabled="true" className={cn(frame, "bg-muted/30 ring-foreground/5")}>
      {body}
    </div>
  );
}
