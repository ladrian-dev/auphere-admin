"use client";

import * as React from "react";

import {
  EmptyState,
  ErrorState,
  Skeleton,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
  formatNumber,
} from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import { formatAmount } from "@/lib/amount";
import { ADS_PERIODS, type AdsPeriod, type AdsReport, type AdsReportRow } from "@/lib/backend/ads";

type Load = (args: { ref: string; days: AdsPeriod }) => Promise<{ ok: true; data: AdsReport } | { ok: false; status?: number }>;

/**
 * Spec 076 (requisito 3): el informe de anuncios de un cliente. Una fila por
 * anuncio, con las conversaciones que empezaron desde él, las reservas del agente
 * atribuidas y su importe por moneda; 7, 30 o 90 días. Debajo de la tabla, qué
 * mide cada columna, porque no miden lo mismo (research D4). Sin datos, explica
 * que se llena solo; si falla, lo dice y deja reintentar. Ni nombres ni
 * teléfonos: el titular es texto del anunciante.
 */
export function AdsReportView({ refId, initial, load }: { refId: string; initial: AdsReport | null; load: Load }) {
  const t = useT();
  const locale = useLocale();
  const [days, setDays] = React.useState<AdsPeriod>(() => (initial && (ADS_PERIODS as readonly number[]).includes(initial.days) ? (initial.days as AdsPeriod) : 30));
  const [report, setReport] = React.useState<AdsReport | null>(initial);
  const [loading, setLoading] = React.useState(false);
  const tablist = React.useId();
  const n = (v: number) => formatNumber(v, locale);

  async function fetchPeriod(next: AdsPeriod) {
    setDays(next);
    setLoading(true);
    const res = await load({ ref: refId, days: next });
    setLoading(false);
    setReport(res.ok ? res.data : null);
  }

  function onKey(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const next = ADS_PERIODS[(index + (event.key === "ArrowRight" ? 1 : ADS_PERIODS.length - 1)) % ADS_PERIODS.length]!;
    void fetchPeriod(next);
    document.getElementById(`${tablist}-${next}`)?.focus();
  }

  return (
    <section className="grid min-w-0 gap-4 rounded-lg border border-border bg-card p-4 sm:px-5" aria-busy={loading || undefined} data-slot="ads-report">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1">
          <h2 className="text-base font-semibold text-balance">{t("ads.title")}</h2>
          <p className="max-w-prose text-sm text-muted-foreground text-pretty">{t("ads.intro")}</p>
        </div>
        <div role="tablist" aria-label={t("ads.period")} className="inline-flex max-w-full flex-wrap gap-1">
          {ADS_PERIODS.map((d, i) => (
            <button
              key={d}
              id={`${tablist}-${d}`}
              type="button"
              role="tab"
              aria-selected={days === d}
              tabIndex={days === d ? 0 : -1}
              onClick={() => void fetchPeriod(d)}
              onKeyDown={(e) => onKey(e, i)}
              className={cn(
                "inline-flex min-h-8 items-center rounded-full border px-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none",
                days === d ? "border-foreground text-foreground" : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {t("ads.period.days", { n: d })}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div role="status" aria-label={t("ads.loading")} className="grid gap-2">
          {/* La forma de la tabla: la cabecera y tres filas. */}
          <Skeleton className="h-9 w-full" />
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      ) : report === null ? (
        <ErrorState
          className="py-6"
          title={t("ads.error")}
          description={t("ads.error.hint")}
          onRetry={() => void fetchPeriod(days)}
          retryLabel={t("ads.retry")}
        />
      ) : report.rows.length === 0 ? (
        <EmptyState readonly title={t("ads.empty.title")} description={t("ads.empty.hint")} />
      ) : (
        <>
          <div className="min-w-0 overflow-x-auto" data-scroll-x>
            <table className="w-full min-w-[36rem] text-sm">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("ads.col.ad")}</TableHead>
                  <TableHead className="text-right">{t("ads.col.conversations")}</TableHead>
                  <TableHead className="text-right">{t("ads.col.bookings")}</TableHead>
                  <TableHead className="text-right">{t("ads.col.amount")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.rows.map((row) => (
                  <TableRow key={row.ad_id ?? "none"}>
                    <TableCell className="max-w-[22rem] min-w-0">
                      <AdName row={row} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{n(row.conversations)}</TableCell>
                    <TableCell className="text-right tabular-nums">{n(row.bookings)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.amounts.length === 0 ? "—" : row.amounts.map((a) => formatAmount(a, locale)).join(" · ")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </table>
          </div>
          <div className="grid gap-1 text-xs text-muted-foreground">
            <p className="text-pretty">{t("ads.help.conversations")}</p>
            <p className="text-pretty">{t("ads.help.bookings")}</p>
          </div>
        </>
      )}
    </section>
  );
}

function AdName({ row }: { row: AdsReportRow }) {
  const t = useT();
  const name = row.ad_headline ?? (row.ad_kind === "post" ? t("ads.unnamed.post") : t("ads.unnamed.ad"));
  if (!row.ad_url) return <span className="block truncate" title={name}>{name}</span>;
  return (
    <a
      href={row.ad_url}
      target="_blank"
      rel="noopener noreferrer"
      title={`${name} · ${t("ads.opens")}`}
      className="block truncate font-medium text-primary-text underline-offset-4 hover:underline"
    >
      {name}
      <span className="sr-only"> ({t("ads.opens")})</span>
    </a>
  );
}
