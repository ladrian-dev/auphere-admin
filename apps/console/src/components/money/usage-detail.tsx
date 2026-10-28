"use client";

import { Download } from "lucide-react";

import { Button, StatusBadge, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { UsageDetail, UsageLine } from "@/lib/backend/money-types";
import { meterLabel } from "@/lib/meter-label";

import { LINE_LABEL } from "./money-model";

/** «Descargar CSV»: el detalle del periodo por cliente, agente, medidor, partida y origen (46.6). */
export function usageCsvHref(days: number, client: string): string {
  const params = new URLSearchParams({ days: String(days), lang: "es" });
  if (client) params.set("client", client);
  return `/api/usage/export?${params.toString()}`;
}

const isLine = (l: string | null): l is UsageLine => l === "conversations" || l === "meta" || l === "build" || l === "companion";

/**
 * El detalle técnico de Consumo, plegado (spec 047, requisito 46.6): los
 * medidores —mensajes, multimedia, minutos de voz y uso del modelo— por
 * cliente, agente, partida y origen, con lo que aún no tiene precio marcado, y
 * «Descargar CSV».
 */
export function UsageDetailPanel({ detail, names, days, client }: { detail: UsageDetail | null; names: Record<string, string>; days: number; client: string }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const unpriced = detail ? detail.rows.reduce((sum, r) => sum + r.unpriced, 0) : 0;
  return (
    <details className="group rounded-md bg-card ring-1 ring-foreground/10" data-slot="usage-detail">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 p-4 text-sm font-medium">
        <span>
          {t("money.detail.title")}
          <span className="block text-xs font-normal text-muted-foreground">{t("money.detail.hint")}</span>
        </span>
        <span aria-hidden="true" className="text-muted-foreground transition-transform group-open:rotate-90">
          ›
        </span>
      </summary>
      <div className="flex min-w-0 flex-col gap-4 border-t border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">{t("money.detail.period", { days })}</p>
          <Button nativeButton={false} variant="outline" size="sm" render={<a href={usageCsvHref(days, client)} download />}>
            <Download aria-hidden="true" />
            {t("money.detail.csv")}
          </Button>
        </div>
        {!detail ? (
          <p className="text-sm text-muted-foreground" role="status">
            {t("money.detail.error")}
          </p>
        ) : detail.rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("money.detail.empty")}</p>
        ) : (
          <>
            {unpriced > 0 ? <p className="text-xs text-pretty text-muted-foreground">{t("money.detail.unpricedNote", { n: n(unpriced) })}</p> : null}
            <div className="max-h-112 min-w-0 overflow-auto rounded-md ring-1 ring-foreground/10" role="region" aria-label={t("money.detail.title")} tabIndex={0}>
              <table className="w-full min-w-[760px] text-sm">
                <caption className="sr-only">{t("money.detail.title")}</caption>
                <thead>
                  <tr className="sticky top-0 border-b bg-card text-left">
                    <th scope="col" className="h-10 px-2 font-medium">{t("usage.client")}</th>
                    <th scope="col" className="h-10 px-2 font-medium">{t("money.detail.agent")}</th>
                    <th scope="col" className="h-10 px-2 font-medium">{t("usage.meter")}</th>
                    <th scope="col" className="h-10 px-2 font-medium">{t("money.detail.line")}</th>
                    <th scope="col" className="h-10 px-2 font-medium">{t("usage.source")}</th>
                    <th scope="col" className="h-10 px-2 text-right font-medium">{t("usage.quantity")}</th>
                    <th scope="col" className="h-10 px-2 text-right font-medium">{t("usage.billable")}</th>
                    <th scope="col" className="h-10 px-2 text-right font-medium">{t("usage.records")}</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.rows.map((r, i) => (
                    <tr key={`${r.ref}-${r.agent_id ?? ""}-${r.meter}-${r.source}-${i}`} className="border-b last:border-0" data-unpriced={r.unpriced > 0 || undefined}>
                      <td className="max-w-48 truncate p-2" title={names[r.ref] ?? r.ref}>
                        {names[r.ref] ?? r.ref}
                      </td>
                      <td className="max-w-40 truncate p-2" title={r.agent_name ?? r.agent_id ?? undefined}>
                        {r.agent_name ?? (r.agent_id ? <span className="font-mono text-xs text-muted-foreground">{r.agent_id.slice(0, 8)}</span> : "—")}
                      </td>
                      <td className="p-2" title={r.meter}>
                        {meterLabel(r.meter, t)}
                        {r.unpriced > 0 ? (
                          <StatusBadge tone="warn" className="ml-2">
                            {t("money.detail.unpriced")}
                          </StatusBadge>
                        ) : null}
                      </td>
                      <td className="p-2">{isLine(r.line) ? t(LINE_LABEL[r.line]) : (r.line ?? "—")}</td>
                      <td className="p-2">{r.source === "channel" || r.source === "qa" ? t(`usage.source.${r.source}` as MessageKey) : r.source}</td>
                      <td className="p-2 text-right tabular-nums">{n(r.quantity)}</td>
                      <td className="p-2 text-right tabular-nums">{n(r.billable_qty)}</td>
                      <td className="p-2 text-right tabular-nums">{n(r.records)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </details>
  );
}
