/**
 * Las cuentas puras del Panel del partner con la consola nueva (spec 047, T163,
 * requisito 48): el periodo de cada bloque, el nombre de cada parte del gasto,
 * las columnas de «Conversaciones por día» y qué arreglo lleva cada fila de
 * «Necesita tu atención». Sin React: se prueban solas. Las cifras las pone la API
 * con la misma función que Consumo (48.3).
 */
import type { BlockChartColumn } from "@nexus/ui";

import { LINE_LABEL, type T } from "@/components/money/money-model";
import type { MessageKey } from "@/i18n/messages";
import type { HomePanel, PanelAttention, PanelSpendShare } from "@/lib/backend/home-usage";

const DAY = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", timeZone: "UTC" });
const DAY_LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" });
const WEEKDAY = new Intl.DateTimeFormat("es-ES", { weekday: "short", timeZone: "UTC" });

const asDate = (iso: string) => new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);

/** «Del 1 oct al 31 oct»: el periodo del gasto (el mes natural, en UTC). `until` es exclusivo. */
export function monthPeriod(t: T, since: string, until: string): string {
  const end = new Date(asDate(until).getTime() - 1);
  return t("panel.v2.period.month", { from: DAY.format(asDate(since)), to: DAY.format(end) });
}

/** Cómo se llama cada parte del gasto: el cliente, «El resto» o la partida. */
export function shareLabel(t: T, share: PanelSpendShare): string {
  if (share.kind === "client") return share.client_name ?? share.external_client_ref ?? "—";
  if (share.kind === "line" && share.line) return t(LINE_LABEL[share.line]);
  return t("panel.v2.spend.rest");
}

/** Las columnas de «Conversaciones por día»: resueltas sin persona y pasadas a una persona. */
export function conversationColumns(t: T, daily: NonNullable<HomePanel["conversations_per_day"]>): BlockChartColumn[] {
  const n = daily.days.length;
  return daily.days.map((day, i) => {
    const d = asDate(day);
    const title = DAY_LONG.format(d);
    return {
      key: day,
      label: i === n - 1 ? t("money.chart.today") : WEEKDAY.format(d),
      title: title.charAt(0).toUpperCase() + title.slice(1),
      values: [daily.resolved_without_person[i] ?? 0, daily.handed_to_person[i] ?? 0],
    };
  });
}

export function conversationTotal(daily: NonNullable<HomePanel["conversations_per_day"]>): number {
  return [...daily.resolved_without_person, ...daily.handed_to_person].reduce((a, b) => a + b, 0);
}

/**
 * El arreglo de una fila: el saldo se arregla en el sitio (el modal de asignar o
 * «Pedir saldo»); lo demás lleva a su pantalla con el `href` que manda la API.
 */
export type AttentionFix = { kind: "assign" | "request" } | { kind: "link"; href: string; label: MessageKey };

export function attentionFix(row: PanelAttention): AttentionFix {
  switch (row.action) {
    case "assign_balance":
      return { kind: "assign" };
    case "request_balance":
      return { kind: "request" };
    default:
      return { kind: "link", href: row.href, label: `panel.v2.fix.${row.action}` as MessageKey };
  }
}

/** Los bloques que la API no pudo leer, para decirlo en vez de pintar ceros. */
export function failed(panel: HomePanel, block: string): boolean {
  return panel.errors.includes(block);
}
