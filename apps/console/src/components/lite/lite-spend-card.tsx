import { CircleDollarSign } from "lucide-react";
import Link from "next/link";

import { Button, cn } from "@nexus/ui";

import type { Locale, MessageKey } from "@/i18n/messages";
import type { LiteHome } from "@/lib/backend/lite";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const SLICE = ["bg-primary", "bg-primary-deep", "bg-accent-mid", "bg-muted-foreground/40", "bg-status-info"] as const;

function money(cents: number, locale: Locale): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency: "USD" }).format(cents / 100);
}

/**
 * «Gasto del mes» of one client (spec 030, R4.2): the same money the partner
 * sees for this client, never Auphere's cost. With more than one agent it
 * splits by agent; with one, it is just the amount — a single slice says
 * nothing (constitution §V: absence is designed).
 */
export function LiteSpendCard({
  spend,
  showUsageLink,
  t,
  locale,
}: {
  spend: NonNullable<LiteHome["spend_month"]>;
  showUsageLink: boolean;
  t: T;
  locale: Locale;
}) {
  const parts = new Intl.NumberFormat(locale, { style: "currency", currency: "USD" }).formatToParts(spend.total_cents / 100);
  const byAgent = spend.by_agent && spend.by_agent.length > 1 ? spend.by_agent : null;
  const total = byAgent ? byAgent.reduce((s, a) => s + a.cents, 0) : 0;
  return (
    <section aria-labelledby="lite-spend-h" className="flex h-full flex-col gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10" data-slot="lite-spend">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
            <CircleDollarSign className="size-4" />
          </span>
          <h2 id="lite-spend-h" className="truncate text-sm font-medium">
            {t("lite.spend.title")}
          </h2>
        </div>
        {showUsageLink ? (
          <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/usage" />}>
            {t("lite.spend.see")}
          </Button>
        ) : null}
      </div>
      <p className="text-4xl font-semibold tracking-tight tabular-nums" aria-label={money(spend.total_cents, locale)}>
        {parts.map((p, i) => (
          <span key={i} aria-hidden="true" className={cn((p.type === "decimal" || p.type === "fraction" || p.type === "currency") && "text-2xl text-muted-foreground")}>
            {p.value}
          </span>
        ))}
      </p>
      {byAgent ? (
        <>
          <div className="flex h-3 gap-1" aria-hidden="true">
            {/* Inline `flex` on purpose: each slice's size is the datum (its spend), not a style. */}
            {byAgent.map((a, i) => (
              <span key={a.agent_id} className={cn("min-w-1 rounded-sm", SLICE[i % SLICE.length])} style={{ flex: Math.max(a.cents, 1) }} />
            ))}
          </div>
          <ul className="flex flex-col gap-1 text-sm">
            {byAgent.map((a, i) => (
              <li key={a.agent_id} className="flex items-center gap-2">
                <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-sm", SLICE[i % SLICE.length])} />
                <span className="min-w-0 flex-1 truncate">{a.name}</span>
                <span className="text-muted-foreground tabular-nums">{total > 0 ? Math.round((a.cents / total) * 100) : 0} %</span>
                <span className="w-24 text-right font-medium tabular-nums">{money(a.cents, locale)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
