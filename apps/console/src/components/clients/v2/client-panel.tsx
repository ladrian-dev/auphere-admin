"use client";

import { Bot } from "lucide-react";
import Link from "next/link";

import { Button, Callout, Card, CardContent, EmptyState, MICROS_PER_UNIT, Money, StatusBadge, formatDate, formatMoney } from "@nexus/ui";

import { ClientReadCard } from "@/components/clients/client-read-card";
import { AgentCapButton } from "@/components/money/agent-cap";
import { BalanceButton } from "@/components/money/balance-button";
import { clientHref } from "@/components/shell/routes-v2";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientPanel as Panel, Money as MoneyValue } from "@/lib/backend/client-records";

import { agentStateText, missingHref, roundDays, stateView } from "./client-v2-model";

/** Los colores de la barra por agente: las series de las gráficas y, después, tonos del mismo sistema. */
const SERIES = ["bg-series-1", "bg-series-2", "bg-accent-mid", "bg-muted-foreground/50", "bg-muted-foreground/25"];

/**
 * El Panel de un cliente (spec 047, T067, requisito 14): «Saldo» (lo que queda,
 * lo consumido y su porcentaje, los días al ritmo de 7 días, la barra por agente
 * y los avisos del 80 % y del 100 %), «Este mes», «Agentes que más consumen» y
 * una sola línea con lo primero que le falta a la ficha. Mientras dura la
 * lectura de la web, su tarjeta. Todas las cifras vienen de la API, que las saca
 * de las mismas cuentas que Consumo y la consola lite.
 */
/**
 * Spec 047 (T159): lo que el Panel sabe del dinero además de la bolsa: la moneda
 * de la bolsa (para el tope de cada agente), si esta persona puede fijar topes
 * (`usage:write`) y el relleno mensual, si lo tiene.
 */
export type PanelMoney = { currency: "EUR" | "USD"; canSetCap: boolean; refillUpTo: MoneyValue | null };

export function ClientPanelView({
  panel,
  canWrite,
  money,
  openBalance = false,
}: {
  panel: Panel;
  canWrite: boolean;
  money?: PanelMoney;
  /** `?assign=1`: el aviso de saldo (o «Pedir saldo») abre aquí mismo «Asignar saldo» (45.1). */
  openBalance?: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const { bag, month } = panel;
  const days = roundDays(bag.days_left);
  const state = stateView(t, panel.lifecycle, panel.attention, bag);
  const newAgent = panel.allowed.includes("new_agent");
  // «Asignar saldo» en el sitio (45.1); quien no puede asignar, «Pedir saldo» (45.7).
  const balanceMode = panel.allowed.includes("assign_balance") ? "assign" : panel.allowed.includes("request_balance") ? "request" : null;
  const capCurrency = money?.currency ?? bag.balance?.currency ?? null;

  return (
    <div className="grid min-w-0 gap-6" data-slot="client-panel">
      <ClientReadCard refId={panel.ref} initial={panel.read} canWrite={canWrite} />

      {panel.missing ? (
        <div className="flex min-w-0 flex-col gap-2 rounded-md border border-border bg-muted/40 p-3 sm:flex-row sm:items-center sm:justify-between" data-slot="panel-missing">
          <p className="min-w-0 text-sm text-pretty">{t(`panel.missing.${panel.missing.section}` as MessageKey)}</p>
          {canWrite ? (
            <Button size="sm" nativeButton={false} render={<Link href={missingHref(panel.ref, panel.missing.section)} />} className="shrink-0">
              {t(`panel.missing.${panel.missing.section}.action` as MessageKey)}
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="grid min-w-0 gap-3">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold">{t("panel.bag.title")}</h2>
              {panel.attention.needs ? <StatusBadge tone={state.tone}>{state.label}</StatusBadge> : null}
            </div>
            {bag.state === "unassigned" ? (
              <p className="text-sm text-muted-foreground">{t("panel.bag.unassigned")}</p>
            ) : bag.state === "unlimited" ? (
              <p className="text-sm text-muted-foreground">{t("panel.bag.unlimited")}</p>
            ) : (
              <>
                <p className="text-2xl font-semibold tabular-nums">
                  {bag.balance ? <Money value={bag.balance} /> : "—"}
                </p>
                <p className="text-sm text-muted-foreground text-pretty">
                  {days != null && bag.days_estimable ? t("panel.bag.days", { days }) : t("panel.bag.noEstimate")}
                </p>
                {bag.spent && bag.assigned ? (
                  <p className="text-sm tabular-nums text-pretty">
                    {t("panel.bag.spent", {
                      spent: formatMoneyText(bag.spent),
                      assigned: formatMoneyText(bag.assigned),
                      pct: Math.round(bag.pct_spent ?? 0),
                    })}
                  </p>
                ) : null}
                {panel.spend_by_agent.length ? (
                  <div className="grid min-w-0 gap-2">
                    <div
                      className="flex h-3 w-full overflow-hidden rounded-full bg-muted"
                      role="img"
                      aria-label={`${t("panel.bag.byAgent")}: ${panel.spend_by_agent
                        .map((s) => t("panel.bag.share", { name: s.name, amount: formatMoneyText(s.spent), pct: s.share_pct }))
                        .join(", ")}`}
                    >
                      {panel.spend_by_agent.map((s, i) => (
                        <span key={s.agent_id} className={SERIES[i % SERIES.length]} style={{ width: `${s.share_pct}%` }} />
                      ))}
                    </div>
                    <ul className="flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-hidden="true">
                      {panel.spend_by_agent.map((s, i) => (
                        <li key={s.agent_id} className="flex min-w-0 items-center gap-1">
                          <span className={`size-2 shrink-0 rounded-full ${SERIES[i % SERIES.length]}`} />
                          <span className="truncate">{t("panel.bag.share", { name: s.name, amount: formatMoneyText(s.spent), pct: s.share_pct })}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {bag.alerts.includes("empty") ? (
                  <Callout tone="danger">{t("panel.bag.empty")}</Callout>
                ) : bag.alerts.includes("warn_80") ? (
                  <Callout tone="warning">{t("panel.bag.warn_80")}</Callout>
                ) : null}
              </>
            )}
            {money?.refillUpTo ? (
              <p className="text-xs text-muted-foreground" data-slot="panel-refill">
                {t("money.panel.refill", { amount: formatMoneyText(money.refillUpTo) })}
              </p>
            ) : null}
            {balanceMode && panel.lifecycle !== "archived" ? (
              <div className="flex flex-wrap gap-2">
                <BalanceButton
                  refId={panel.ref}
                  name={panel.name}
                  mode={balanceMode}
                  variant={bag.state === "ok" ? "outline" : "default"}
                  defaultOpen={openBalance}
                />
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="grid min-w-0 gap-3">
            <div className="grid min-w-0 gap-1">
              <h2 className="text-base font-semibold">{t("panel.month.title")}</h2>
              <p className="text-xs text-muted-foreground">
                {t("panel.month.period", { from: formatDate(month.period_start, locale), to: formatDate(month.period_end, locale) })}
              </p>
            </div>
            <dl className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-4">
              <Figure label={t("panel.month.conversations")} value={String(month.conversations)} />
              <Figure label={t("panel.month.resolved")} value={month.resolved_pct != null ? `${Math.round(month.resolved_pct)} %` : "—"} />
              <Figure label={t("panel.month.handed")} value={String(month.handed_to_person)} />
              <Figure label={t("panel.month.spent")} value={formatMoneyText(month.spent)} />
            </dl>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="grid min-w-0 gap-3">
          <h2 className="text-base font-semibold">{t("panel.top.title")}</h2>
          {panel.agents_total === 0 ? (
            <EmptyState
              icon={Bot}
              title={t("panel.top.none.title")}
              description={t("panel.top.none.body")}
              action={
                newAgent ? (
                  <Button nativeButton={false} render={<Link href={`${clientHref(panel.ref, "agents")}?new=1`} />}>
                    {t("panel.top.none.action")}
                  </Button>
                ) : undefined
              }
              readonly={!newAgent}
            />
          ) : (
            <div className="relative min-w-0 overflow-x-auto" role="region" aria-label={t("panel.top.title")} tabIndex={0}>
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th scope="col" className="py-2 pr-3 font-medium">{t("panel.top.agent")}</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">{t("panel.top.spent")}</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">{t("panel.top.conversations")}</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">{t("panel.top.perConversation")}</th>
                    <th scope="col" className="py-2 text-right font-medium">{t("panel.top.cap")}</th>
                  </tr>
                </thead>
                <tbody>
                  {panel.top_agents.map((a) => (
                    <tr key={a.agent_id} className="border-t border-border">
                      <td className="max-w-56 py-2 pr-3">
                        <span className="block truncate font-medium" title={a.name}>
                          {a.name}
                        </span>
                        <span className="block text-xs text-muted-foreground">{agentStateText(t, a.visible_state)}</span>
                      </td>
                      <td className="py-2 pr-3 text-right">
                        <Money value={a.spent} />
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">{a.conversations}</td>
                      <td className="py-2 pr-3 text-right">{a.spend_per_conversation ? <Money value={a.spend_per_conversation} /> : "—"}</td>
                      <td className="py-2 text-right">
                        {money?.canSetCap && capCurrency ? (
                          <AgentCapButton refId={panel.ref} agentId={a.agent_id} agentName={a.name} cap={a.cap} currency={capCurrency} canWrite />
                        ) : a.cap ? (
                          <Money value={a.cap} />
                        ) : (
                          <span className="text-muted-foreground">{t("panel.top.noCap")}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 gap-1">
      <dt className="text-xs text-muted-foreground text-pretty">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function formatMoneyText(value: { amount_micros: number; currency: "EUR" | "USD" }): string {
  // El mismo formato que `<Money>` (`es-ES`, el símbolo detrás), en texto para
  // las etiquetas accesibles y las frases.
  return formatMoney(value.amount_micros / MICROS_PER_UNIT, value.currency);
}
