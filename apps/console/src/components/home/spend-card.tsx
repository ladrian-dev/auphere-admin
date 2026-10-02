import { ArrowDownRight, ArrowUpRight, CircleDollarSign } from "lucide-react";
import Link from "next/link";

import { Button, cn, formatCompact } from "@nexus/ui";

import type { Locale, MessageKey } from "@/i18n/messages";
import type { HomeSpend } from "@/lib/backend/home-usage";

import { spendShares, trendDelta } from "./home-model";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Slice colours, in order: three clients, the rest, outside any client. */
const SLICE = ["bg-primary", "bg-primary-deep", "bg-accent-mid", "bg-muted-foreground/40", "bg-status-info"] as const;

function money(cents: number, currency: string, locale: Locale): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(cents / 100);
}

/** «12,40 US$» with the cents smaller, as a person reads an amount. */
function BigAmount({ cents, currency, locale }: { cents: number; currency: string; locale: Locale }) {
  const parts = new Intl.NumberFormat(locale, { style: "currency", currency }).formatToParts(cents / 100);
  return (
    <p className="text-4xl font-semibold tracking-tight tabular-nums" aria-label={money(cents, currency, locale)}>
      {parts.map((p, i) => (
        <span key={i} aria-hidden="true" className={cn((p.type === "decimal" || p.type === "fraction" || p.type === "currency") && "text-2xl text-muted-foreground")}>
          {p.value}
        </span>
      ))}
    </p>
  );
}

/**
 * «Gasto del mes» (spec 026): the month's credit in money at the price the
 * partner pays for it, the change against the same days of last month, where
 * the month closes at this pace and who it goes to. Never Auphere's cost.
 */
export function SpendCard({ spend, t, locale }: { spend: HomeSpend; t: T; locale: Locale }) {
  const { currency } = spend;
  const delta = trendDelta(spend.cents, spend.previous_cents);
  const shares = spendShares(spend.by_client);
  const label = (kind: string, name: string | null, ref: string | null) =>
    kind === "rest" ? t("hu.home.chart.rest") : kind === "outside" ? t("hu.home.spend.outside") : (name ?? ref ?? "");
  return (
    <section aria-labelledby="home-spend-h" className="flex flex-col gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10" data-slot="home-spend">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="home-spend-h" className="text-base font-semibold">
          {t("hu.home.spend.title")}
        </h2>
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/usage" />}>
          {t("hu.home.spend.see")}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <BigAmount cents={spend.cents} currency={currency} locale={locale} />
        {delta.kind !== "none" ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 text-xs font-medium tabular-nums" data-slot="spend-delta">
            {delta.kind === "up" ? <ArrowUpRight aria-hidden="true" className="size-3" /> : delta.kind === "down" ? <ArrowDownRight aria-hidden="true" className="size-3" /> : null}
            <span aria-hidden="true">{delta.kind === "same" ? "=" : `${delta.pct} %`}</span>
            <span className="sr-only">{t(`hu.home.spend.delta.${delta.kind}`, { pct: delta.pct })}</span>
          </span>
        ) : null}
      </div>
      {spend.cents > 0 ? <p className="text-sm text-pretty">{t("hu.home.spend.pace", { amount: money(spend.projected_cents, currency, locale) })}</p> : null}
      <p className="inline-flex w-fit items-center gap-2 rounded-md bg-muted px-3 py-1 text-sm">
        <CircleDollarSign aria-hidden="true" className="size-4 text-primary" />
        {spend.previous_cents != null ? (
          <>
            {t("hu.home.spend.previous")}
            <span className="font-medium tabular-nums">{money(spend.previous_cents, currency, locale)}</span>
          </>
        ) : (
          t("hu.home.spend.noPrevious")
        )}
      </p>
      {shares.length > 0 ? (
        <>
          <div className="flex h-8 gap-1" role="img" aria-label={t("hu.home.spend.aria")}>
            {shares.map((s, i) => (
              <span key={`${s.kind}-${s.external_client_ref ?? i}`} className={cn("min-w-1 basis-0 rounded-sm", SLICE[i] ?? SLICE[3])} style={{ flexGrow: s.credits }} />
            ))}
          </div>
          <ul className="flex flex-col gap-1 text-sm">
            {shares.map((s, i) => (
              <li key={`${s.kind}-${s.external_client_ref ?? i}`} className="flex items-center gap-2">
                <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-sm", SLICE[i] ?? SLICE[3])} />
                <span className="min-w-0 flex-1 truncate">{label(s.kind, s.client_name, s.external_client_ref)}</span>
                <span className="tabular-nums text-muted-foreground">{s.pct} %</span>
                <span className="w-20 text-right font-medium tabular-nums">{money(s.cents, currency, locale)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">{t("hu.home.spend.empty")}</p>
      )}
      <p className="text-xs text-muted-foreground">
        {t("hu.home.spend.rate", { credits: formatCompact(spend.credits, locale), rate: money(spend.usd_per_million_credits * 100, currency, locale) })}
      </p>
    </section>
  );
}
