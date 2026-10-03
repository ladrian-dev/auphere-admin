import { Sparkline, formatNumber } from "@nexus/ui";

import type { Locale, MessageKey } from "@/i18n/messages";
import { meterLabel } from "@/lib/meter-label";
import type { MeterGroup } from "@/lib/usage-projection";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * The technical detail as one compact list (spec 028, owner 2026-10-03):
 * each measurement on its own row — readable name, the period total and a
 * small daily trend — grouped by what it measures. Different units never
 * share a scale, so no stacked chart of tokens on top of messages.
 */
export function MeterList({ groups, t, locale, messagesExtra = [] }: { groups: MeterGroup[]; t: T; locale: Locale; messagesExtra?: Array<{ label: string; value: string; title?: string }> }) {
  const n = (v: number) => formatNumber(v, locale);
  return (
    // Columns that fill on their own (owner, 2026-10-03): a grid aligns by
    // rows, so a short group next to a tall one left an empty hole.
    <div className="gap-4 md:columns-2">
      {groups.map((g) => (
        <section key={g.key} aria-labelledby={`meters-${g.key}`} className="mb-4 flex break-inside-avoid flex-col">
          <h3 id={`meters-${g.key}`} className="pb-1 text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">
            {t(`hu.usage.meters.${g.key}` as MessageKey)}
          </h3>
          <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
            {g.rows.map((r) => (
              <li key={r.meter} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm" title={r.meter}>
                  {meterLabel(r.meter, t)}
                </span>
                <Sparkline values={r.series} ariaLabel={t("hu.usage.meters.trend", { meter: meterLabel(r.meter, t) })} className="h-6 w-24 shrink-0 text-primary" />
                <span className={r.total > 0 ? "w-24 shrink-0 text-right text-sm font-medium tabular-nums" : "w-24 shrink-0 text-right text-sm tabular-nums text-muted-foreground"}>
                  {n(r.total)}
                </span>
              </li>
            ))}
            {g.key === "messages"
              ? messagesExtra.map((x) => (
                  <li key={x.label} className="flex items-center gap-3 px-3 py-2" title={x.title}>
                    <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{x.label}</span>
                    <span className="w-24 shrink-0 text-right text-sm font-medium tabular-nums">{x.value}</span>
                  </li>
                ))
              : null}
          </ul>
        </section>
      ))}
    </div>
  );
}
