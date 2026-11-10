"use client";

import * as React from "react";

import {
  BlockChart,
  Button,
  ErrorState,
  Skeleton,
  StatusBadge,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
  formatDateTime,
  formatNumber,
} from "@nexus/ui";

import { conversationsAction, performanceAction } from "@/app/(console)/clients/[ref]/agents/improve-actions";
import { microsText } from "@/components/money/money-model";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import { PERFORMANCE_PERIODS, type AgentConversationPage, type AgentPerformance, type PerformancePeriod } from "@/lib/backend/agent-improve-types";
import type { Money } from "@/lib/backend/money-types";

import type { Result } from "./builder-model";
import { channelLabel, durationText, performanceColumns, reasonKey } from "./improve-model";

export type PerformanceActions = {
  load: (body: { ref: string; agent: string; days: number }) => Promise<Result<AgentPerformance>>;
  more: (body: { ref: string; agent: string; cursor?: string }) => Promise<Result<AgentConversationPage>>;
};

const SERVER_ACTIONS: PerformanceActions = {
  load: (b) => performanceAction(b),
  more: (b) => conversationsAction(b),
};

/** El resumen de arriba es de 30 días (51.1 y 63.2), elija lo que elija la gráfica. */
const SUMMARY_DAYS = 30;

/**
 * La pestaña Rendimiento del agente (spec 047, T174; requisitos 51.1 y 51.2),
 * como el prototipo aprobado (`agente.md` §6, hueco H9; requisito 63.2):
 *
 * - Arriba, en dos columnas (una por debajo de 980 px): «Últimos 30 días» con
 *   tres cifras —conversaciones, resueltas sin persona y lo consumido de la
 *   bolsa, con el tope del agente si lo tiene— y, a la derecha,
 *   `suggestions` («Sugerencias de esta semana», que pinta la pantalla).
 * - Debajo, a todo el ancho (decisión D5): la gráfica de bloques con su
 *   periodo (7, 30 o 90 días) y la lista de conversaciones **solo con
 *   metadatos**: fecha, canal, duración, mensajes, resultado, motivo del
 *   traspaso y gasto. Nunca un mensaje ni quién era el cliente final (C1 y C8).
 *
 * El resumen siempre es de 30 días; la píldora cambia solo la gráfica.
 * `conversations` en `undefined` es que esta persona no puede leerlas: la lista
 * no se pinta (§V). Cada parte carga y falla sola (el estado parcial).
 */
export function AgentPerformancePanel({
  refId,
  agentId,
  performance: initial,
  conversations: initialConversations,
  cap = null,
  suggestions = null,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  agentId: string;
  performance: AgentPerformance | null;
  conversations?: AgentConversationPage | null;
  /** El tope mensual del agente, en la moneda de la bolsa; `null` sin tope o si no se sabe. */
  cap?: Money | null;
  /** La columna derecha: «Sugerencias de esta semana». */
  suggestions?: React.ReactNode;
  actions?: PerformanceActions;
}) {
  const t = useT();
  const locale = useLocale();
  // El resumen de arriba: siempre los 30 días.
  const [month, setMonth] = React.useState(initial && initial.days === SUMMARY_DAYS ? initial : null);
  const [monthLoading, setMonthLoading] = React.useState(false);
  const [days, setDays] = React.useState<PerformancePeriod>(() => (initial && (PERFORMANCE_PERIODS as readonly number[]).includes(initial.days) ? (initial.days as PerformancePeriod) : 30));
  const [perf, setPerf] = React.useState(initial);
  const [loading, setLoading] = React.useState(false);
  const [page, setPage] = React.useState(initialConversations);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [moreFailed, setMoreFailed] = React.useState(false);
  const tablist = React.useId();
  const summaryTitle = React.useId();
  const n = (v: number) => formatNumber(v, locale);
  const money = (micros: number) => microsText(micros, "USD");

  async function load(next: PerformancePeriod) {
    setDays(next);
    setLoading(true);
    const res = await actions.load({ ref: refId, agent: agentId, days: next });
    setLoading(false);
    setPerf(res.ok ? res.data : null);
    if (res.ok && next === SUMMARY_DAYS) setMonth(res.data);
  }

  async function loadMonth() {
    setMonthLoading(true);
    const res = await actions.load({ ref: refId, agent: agentId, days: SUMMARY_DAYS });
    setMonthLoading(false);
    if (!res.ok) return;
    setMonth(res.data);
    if (days === SUMMARY_DAYS) setPerf(res.data);
  }

  async function more(retry = false) {
    setLoadingMore(true);
    setMoreFailed(false);
    const cursor = retry ? undefined : (page?.next_cursor ?? undefined);
    const res = await actions.more({ ref: refId, agent: agentId, cursor });
    setLoadingMore(false);
    if (!res.ok) {
      setMoreFailed(true);
      return;
    }
    setPage((prev) => (retry || !prev ? res.data : { items: [...prev.items, ...res.data.items], next_cursor: res.data.next_cursor }));
  }

  function onKey(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const next = PERFORMANCE_PERIODS[(index + (event.key === "ArrowRight" ? 1 : PERFORMANCE_PERIODS.length - 1)) % PERFORMANCE_PERIODS.length]!;
    void load(next);
    document.getElementById(`${tablist}-${next}`)?.focus();
  }

  const bagLabel = cap ? `${t("improve.figure.bag")} · ${t("improve.figure.cap", { amount: microsText(cap.amount_micros, cap.currency) })}` : t("improve.figure.bag");

  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-performance">
      {/* Como el prototipo (§6): 1.35fr / 1fr, alineadas arriba; una columna por debajo de 980 px. */}
      <div className="grid min-w-0 items-start gap-4 min-[980px]:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]" data-slot="performance-top">
        <section
          id="agente-rendimiento"
          aria-labelledby={summaryTitle}
          aria-busy={monthLoading || undefined}
          className="grid min-w-0 scroll-mt-24 gap-3 rounded-lg border border-border bg-card p-4 sm:px-5"
        >
          <h2 id={summaryTitle} className="text-base font-semibold text-balance">
            {t("improve.period.last", { n: SUMMARY_DAYS })}
          </h2>
          {monthLoading ? (
            <div role="status" aria-label={t("improve.loading")} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {/* Del tamaño de cada cifra: el número (text-xl) y su etiqueta (text-sm). */}
              {Array.from({ length: 3 }, (_, i) => (
                <div key={i} className="grid gap-1">
                  <Skeleton className="h-7 w-16" />
                  <Skeleton className="h-5 w-24" />
                </div>
              ))}
            </div>
          ) : month === null ? (
            <ErrorState
              className="py-4"
              title={t("improve.performance.error")}
              description={t("improve.performance.error.hint")}
              onRetry={() => void loadMonth()}
              retryLabel={t("improve.retry")}
            />
          ) : (
            <dl className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3" data-slot="performance-figures">
              <Figure label={t("improve.figure.conversations")} value={n(month.conversations)} />
              <Figure
                label={t("panel.v2.conversations.resolved")}
                value={month.resolved_pct !== null && month.conversations > 0 ? t("improve.figure.percent", { n: formatNumber(Math.round(month.resolved_pct), locale) }) : "—"}
              />
              <Figure label={bagLabel} value={money(month.spent.amount_micros)} />
            </dl>
          )}
        </section>
        {suggestions}
      </div>

      <div className="grid min-w-0 gap-4 rounded-lg border border-border bg-card p-4 sm:px-5" data-slot="performance-chart">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">{t("improve.period.last", { n: days })}</p>
          <div role="tablist" aria-label={t("improve.period")} className="inline-flex max-w-full flex-wrap gap-1 overflow-x-auto" data-scroll-x>
            {PERFORMANCE_PERIODS.map((d, i) => (
              <button
                key={d}
                id={`${tablist}-${d}`}
                type="button"
                role="tab"
                aria-selected={days === d}
                tabIndex={days === d ? 0 : -1}
                onClick={() => void load(d)}
                onKeyDown={(e) => onKey(e, i)}
                className={cn(
                  "inline-flex min-h-8 items-center rounded-full border px-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none",
                  days === d ? "border-foreground text-foreground" : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {t("money.chart.days", { n: d })}
              </button>
            ))}
          </div>
        </div>
        {loading ? (
          <div role="status" aria-label={t("improve.loading")} className="grid min-w-0 gap-4">
            <Skeleton className="h-40 w-full" />
          </div>
        ) : perf === null ? (
          <ErrorState
            className="py-6"
            title={t("improve.performance.error")}
            description={t("improve.performance.error.hint")}
            onRetry={() => void load(days)}
            retryLabel={t("improve.retry")}
          />
        ) : (
          // La tabla para lectores de pantalla de la gráfica es `sr-only`: sin recortar, ensancha la página a 390 px.
          <div className="relative min-w-0 overflow-x-clip">
            <BlockChart
              title={t("panel.v2.conversations.title")}
              series={[
                { key: "resolved", label: t("panel.v2.conversations.resolved") },
                { key: "handed", label: t("panel.v2.conversations.handed") },
              ]}
              columns={performanceColumns(t, perf)}
              locale={locale}
              copy={{
                column: t("money.chart.day"),
                total: t("money.chart.columnTotal"),
                top: t("money.chart.top"),
                noData: t("money.chart.noData"),
                empty: t("improve.chart.empty", { n: perf.days }),
                totalOf: (formatted) => t("panel.v2.conversations.of", { n: formatted }),
              }}
            />
          </div>
        )}
      </div>

      {page !== undefined ? (
        <div className="grid min-w-0 gap-3 rounded-lg border border-border bg-card p-4 sm:px-5" data-slot="agent-conversations">
          <div className="grid gap-1">
            <h3 className="text-sm font-semibold">{t("improve.conversations.title")}</h3>
            <p className="text-xs text-pretty text-muted-foreground">{t("improve.conversations.privacy")}</p>
          </div>
          {page === null ? (
            <ErrorState className="py-6" title={t("improve.conversations.error")} onRetry={() => void more(true)} retryLabel={t("improve.retry")} />
          ) : page.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("improve.conversations.empty")}</p>
          ) : (
            <>
              {/* La caja que se desplaza toma el foco: sin enlaces dentro, el teclado también la mueve (axe `scrollable-region-focusable`). */}
              <div
                role="group"
                aria-label={t("improve.conversations.title")}
                tabIndex={0}
                className="min-w-0 overflow-x-auto rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                data-scroll-x
              >
                <table data-slot="table" className="w-full caption-bottom text-sm" aria-label={t("improve.conversations.title")}>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("improve.col.date")}</TableHead>
                      <TableHead>{t("improve.col.channel")}</TableHead>
                      <TableHead>{t("improve.col.duration")}</TableHead>
                      <TableHead className="text-right">{t("improve.col.messages")}</TableHead>
                      <TableHead>{t("improve.col.outcome")}</TableHead>
                      <TableHead>{t("improve.col.reason")}</TableHead>
                      <TableHead className="text-right">{t("improve.col.spent")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {page.items.map((c) => {
                      const reason = reasonKey(c.handoff_reason);
                      return (
                        <TableRow key={c.id}>
                          <TableCell className="whitespace-nowrap tabular-nums">{formatDateTime(c.started_at, locale)}</TableCell>
                          <TableCell>{channelLabel(t, c.channel_type)}</TableCell>
                          <TableCell className="tabular-nums">{durationText(t, c.duration_seconds)}</TableCell>
                          <TableCell className="text-right tabular-nums">{n(c.messages_count)}</TableCell>
                          <TableCell>
                            {c.in_progress ? (
                              <StatusBadge tone="info">{t("improve.outcome.in_progress")}</StatusBadge>
                            ) : (
                              <StatusBadge tone={c.outcome === "handed_to_person" ? "warn" : "positive"}>
                                {t(`improve.outcome.${c.outcome}` as MessageKey)}
                              </StatusBadge>
                            )}
                          </TableCell>
                          <TableCell className="min-w-32 whitespace-normal">{reason ? t(reason) : "—"}</TableCell>
                          <TableCell className="text-right tabular-nums">{c.spent ? money(c.spent.amount_micros) : "—"}</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </table>
              </div>
              {moreFailed ? (
                <p role="alert" className="text-sm text-destructive">
                  {t("improve.conversations.error")}
                </p>
              ) : null}
              {page.next_cursor ? (
                <div>
                  <Button type="button" variant="outline" size="sm" loading={loadingMore} onClick={() => void more()}>
                    {t("improve.conversations.more")}
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

/** Una cifra como el prototipo (§6): el número grande arriba y su etiqueta debajo. */
function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-col-reverse justify-end gap-1">
      <dt className="text-sm text-muted-foreground [overflow-wrap:anywhere]">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums [overflow-wrap:anywhere]">{value}</dd>
    </div>
  );
}
