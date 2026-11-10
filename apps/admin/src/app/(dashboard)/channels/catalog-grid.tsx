import { StatusBadge } from "@nexus/ui";

import { ChannelLogo } from "@/components/brand/channel-logo";
import { AVAILABILITY_LABEL } from "@/components/channels/labels";
import type { ChannelAvailability, ChannelCatalogEntry } from "@/lib/backend";

const TONE: Record<ChannelAvailability, "info" | "warning" | "muted" | "positive"> = {
  available: "positive",
  beta: "info",
  pending: "warning",
  coming_soon: "muted",
};

/**
 * Spec 035 (R1) and spec 047 (T172, 54.8): the channel catalog as Auphere
 * keeps it. What works says how many numbers use it; what is «Pendiente» or
 * «Próximamente» says so, with why (constitution 1.2.0: only here and in the
 * partner console's channel catalog).
 */
export function CatalogGrid({ catalog, active }: { catalog: ChannelCatalogEntry[]; active: Record<string, number> }) {
  return (
    <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {catalog.map((entry) => {
        const badge = AVAILABILITY_LABEL[entry.availability];
        const startable = entry.availability === "available" || entry.availability === "beta";
        return (
          <li
            key={entry.key}
            className="flex flex-col items-start gap-2 rounded-md p-4 ring-1 ring-foreground/10"
            aria-disabled={startable ? undefined : true}
          >
            <ChannelLogo channel={entry.key} size="lg" />
            <span className="text-sm font-medium">{entry.name}</span>
            {badge ? <StatusBadge tone={TONE[entry.availability]}>{badge}</StatusBadge> : null}
            {startable ? (
              <span className="text-xs text-muted-foreground tabular-nums">{active[entry.key] ?? 0} activos</span>
            ) : null}
            {!startable && entry.note ? (
              <span className="text-xs text-pretty text-muted-foreground">{entry.note}</span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
