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

/**
 * La pestaña Rendimiento del agente (spec 047, T174; requisitos 51.1 y 51.2): los
 * últimos 30 días (7 y 90 en la píldora) —conversaciones, resueltas sin persona,
 * pasadas a una persona, gasto y gasto medio por conversación— con su gráfica de
 * bloques y su tabla para lectores de pantalla; y la lista de conversaciones
 * **solo con metadatos**: fecha, canal, duración, mensajes, resultado, motivo del
 * traspaso y gasto. Nunca un mensaje ni quién era el cliente final (C1 y C8).
 *
 * `conversations` en `undefined` es que esta persona no puede leerlas: la lista
 * no se pinta (§V). Cada parte carga y falla sola (el estado parcial).
 */
export function AgentPerformancePanel({
  refId,
  agentId,
  performance: initial,
  conversations: initialConversations,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  agentId: string;
  performance: AgentPerformance | null;
  conversations?: AgentConversationPage | null;
  actions?: PerformanceActions;
}) {
  const t = useT();
  const locale = useLocale();
  const [days, setDays] = React.useState<PerformancePeriod>(() => (initial && (PERFORMANCE_PERIODS as readonly number[]).includes(initial.days) ? (initial.days as PerformancePeriod) : 30));
  const [perf, setPerf] = React.useState(initial);
  const [loading, setLoading] = React.useState(false);
  const [page, setPage] = React.useState(initialConversations);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [moreFailed, setMoreFailed] = React.useState(false);
  const tablist = React.useId();
  const n = (v: number) => formatNumber(v, locale);
  const money = (micros: number) => microsText(micros, "USD");

  async function load(next: PerformancePeriod) {
    setDays(next);
    setLoading(true);
    const res = await actions.load({ ref: refId, agent: agentId, days: next });
    setLoading(false);
    setPerf(res.ok ? res.data : null);
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

  return (
    <div className="grid min-w-0 gap-5" data-slot="agent-performance">
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
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="grid gap-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-7 w-16" />
              </div>
            ))}
          </div>
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
        <>
          <dl className="grid min-w-0 grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4" data-slot="performance-figures">
            <Figure label={t("improve.figure.conversations")} value={n(perf.conversations)} />
            <Figure
              label={t("panel.v2.conversations.resolved")}
              value={n(perf.resolved_without_person)}
              note={perf.resolved_pct !== null ? t("improve.figure.pct", { n: formatNumber(Math.round(perf.resolved_pct), locale) }) : undefined}
            />
            <Figure label={t("panel.v2.conversations.handed")} value={n(perf.handed_to_person)} />
            <Figure
              label={t("improve.figure.spent")}
              value={money(perf.spent.amount_micros)}
              note={perf.spend_per_conversation ? t("improve.figure.perConversation", { amount: money(perf.spend_per_conversation.amount_micros) }) : undefined}
            />
          </dl>
          {/* La tabla para lectores de pantalla de la gráfica es `sr-only`: sin recortar, ensancha la página a 390 px. */}
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
        </>
      )}

      {page !== undefined ? (
        <div className="grid min-w-0 gap-3" data-slot="agent-conversations">
          <div className="grid gap-1">
            <h4 className="text-sm font-semibold">{t("improve.conversations.title")}</h4>
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

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="grid min-w-0 content-start gap-1">
      <dt className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums [overflow-wrap:anywhere]">{value}</dd>
      {note ? <dd className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{note}</dd> : null}
    </div>
  );
}
