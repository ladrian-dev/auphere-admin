import { CircleDollarSign } from "lucide-react";
import Link from "next/link";

import { Button, cn } from "@nexus/ui";

import type { Locale, MessageKey } from "@/i18n/messages";
import type { HomeSpend } from "@/lib/backend/home-usage";

import { spendShares } from "./home-model";

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
    <p className="text-3xl font-semibold tracking-tight tabular-nums" aria-label={money(cents, currency, locale)}>
      {parts.map((p, i) => (
        <span key={i} aria-hidden="true" className={cn((p.type === "decimal" || p.type === "fraction" || p.type === "currency") && "text-xl text-muted-foreground")}>
          {p.value}
        </span>
      ))}
    </p>
  );
}

/**
 * «Gasto del mes» (spec 026): the month's credit in money at the price the
 * partner pays for it, and who it goes to. Never Auphere's cost, never
 * credits (spec 027). The owner
 * dropped the comparison and the projection tiles (2026-10-02): the card
 * answers «how much and on whom», nothing else.
 */
export function SpendCard({ spend, t, locale }: { spend: HomeSpend; t: T; locale: Locale }) {
  const { currency } = spend;
  const shares = spendShares(spend.by_client);
  const label = (kind: string, name: string | null, ref: string | null) =>
    kind === "rest" ? t("hu.home.chart.rest") : kind === "outside" ? t("hu.home.spend.outside") : (name ?? ref ?? "");
  return (
    <section aria-labelledby="home-spend-h" className="flex h-full flex-col gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10" data-slot="home-spend">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
            <CircleDollarSign className="size-4" />
          </span>
          <h2 id="home-spend-h" className="truncate text-sm font-medium">
            {t("hu.home.spend.title")}
          </h2>
        </div>
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/usage" />}>
          {t("hu.home.spend.see")}
        </Button>
      </div>
      <BigAmount cents={spend.cents} currency={currency} locale={locale} />
      {shares.length > 0 ? (
        <>
          <div className="flex h-3 gap-1" role="img" aria-label={t("hu.home.spend.aria")}>
            {shares.map((s, i) => (
              <span key={`${s.kind}-${s.external_client_ref ?? i}`} className={cn("min-w-1 basis-0 rounded-sm", SLICE[i] ?? SLICE[3])} style={{ flexGrow: s.cents }} />
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
    </section>
  );
}
