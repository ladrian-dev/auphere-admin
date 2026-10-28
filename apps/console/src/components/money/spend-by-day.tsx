"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { BlockChart, NativeSelect, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Currency, UsageDaily, UsageLine } from "@/lib/backend/money-types";
import { USAGE_LINES } from "@/lib/backend/money-types";

import { LINE_LABEL, chartColumns, chartLines, chartTotal, microsText } from "./money-model";

const PERIODS = [7, 30, 90] as const;

/**
 * Los filtros de «Gasto por día» (46.3): el periodo, el cliente y la partida.
 * Son la URL (`?days=&client=&line=`): lo que se ve se puede compartir.
 */
export function SpendFilters({ days, client, line, clients }: { days: number; client: string; line: UsageLine | null; clients: { ref: string; name: string }[] }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const go = (next: Record<string, string>) => {
    const sp = new URLSearchParams(params?.toString() ?? "");
    for (const [k, v] of Object.entries(next)) {
      if (v) sp.set(k, v);
      else sp.delete(k);
    }
    const qs = sp.toString();
    router.push(`${pathname}${qs ? `?${qs}` : ""}#gasto`, { scroll: false });
  };
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2" data-slot="spend-filters">
      <div role="group" aria-label={t("money.chart.period")} className="inline-flex max-w-full flex-wrap rounded-md bg-muted p-1">
        {PERIODS.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={days === d}
            onClick={() => go({ days: d === 30 ? "" : String(d) })}
            className={cn("rounded-sm px-3 py-1 text-xs font-medium", days === d ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
          >
            {t("money.chart.days", { n: d })}
          </button>
        ))}
      </div>
      <NativeSelect wrapperClassName="max-w-56" aria-label={t("money.chart.client")} value={client} onChange={(e) => go({ client: e.target.value })}>
        <option value="">{t("money.chart.allClients")}</option>
        {clients.map((c) => (
          <option key={c.ref} value={c.ref}>
            {c.name}
          </option>
        ))}
      </NativeSelect>
      <NativeSelect wrapperClassName="max-w-64" aria-label={t("money.chart.line")} value={line ?? ""} onChange={(e) => go({ line: e.target.value })}>
        <option value="">{t("money.chart.partnerPays")}</option>
        {USAGE_LINES.map((l) => (
          <option key={l} value={l}>
            {t(LINE_LABEL[l])}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}

/**
 * «Gasto por día» (spec 047, requisito 46.3): una gráfica de bloques de 7, 30 o
 * 90 días, en la moneda de la cuenta, con su tabla equivalente para lectores de
 * pantalla (la lleva `BlockChart`). Sin filtro de partida enseña lo que sale del
 * dinero del partner —conversaciones y Companion—, las dos series que suman el
 * «Gasto del mes»; Meta y «Construcción y pruebas» se ven eligiendo su partida.
 */
export function SpendByDay({ daily, line, currency }: { daily: UsageDaily | null; line: UsageLine | null; currency: Currency }) {
  const t = useT();
  const fmt = React.useCallback((v: number) => microsText(v, currency), [currency]);
  if (!daily) return <BlockChart title={t("money.chart.title")} series={[]} columns={[]} copy={copy(t)} error={t("money.chart.error")} />;
  const lines = chartLines(daily, line);
  const approx = lines.some((l) => daily.approx_lines.includes(l));
  const series = lines.map((l) => ({ key: l, label: t(LINE_LABEL[l]) + (daily.approx_lines.includes(l) ? ` (${t("money.approx")})` : "") }));
  const total = chartTotal(daily, lines);
  return (
    // `relative` y `overflow-x-clip`: la tabla para lectores de pantalla de la
    // gráfica es `sr-only` (absoluta), y una tabla no encoge por debajo de su
    // contenido. Sin recortarla aquí, a 390 px ensanchaba la página entera.
    <div className="relative grid min-w-0 gap-2 overflow-x-clip" data-slot="spend-by-day">
      <p className="text-sm text-muted-foreground">
        {t("money.chart.total", { amount: fmt(total), days: daily.days.length })}
      </p>
      <BlockChart
        title={t("money.chart.title")}
        description={line ? t(`money.line.${line}.payer` as MessageKey) + (approx ? ` ${t("money.chart.approxNote")}` : "") : t("money.chart.partnerPaysNote")}
        series={series}
        columns={chartColumns(t, daily, lines)}
        copy={copy(t)}
        formatValue={fmt}
      />
    </div>
  );
}

function copy(t: (k: MessageKey, v?: Record<string, string | number>) => string) {
  return {
    column: t("money.chart.day"),
    total: t("money.chart.columnTotal"),
    top: t("money.chart.top"),
    noData: t("money.chart.noData"),
    empty: t("money.chart.empty"),
    totalOf: (formatted: string) => formatted,
  };
}
