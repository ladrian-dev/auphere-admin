"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, Callout, Card, CardContent, MICROS_PER_UNIT, Money, StatusBadge, cn, formatMoney, formatNumber } from "@nexus/ui";

import { AgentCapButton } from "@/components/money/agent-cap";
import { BalanceButton, BalanceDialogs } from "@/components/money/balance-button";
import { agentHref, clientHref } from "@/components/shell/routes-v2";
import { useLocale, useT } from "@/i18n/client";
import type { ClientPanel as Panel, Money as MoneyValue } from "@/lib/backend/client-records";

import { agentStateText, capPct, periodLabel, roundDays, spendSegments } from "./client-v2-model";

/** Las series del prototipo (`--s1`…`--s4`): los tramos de la barra y los puestos de la lista. */
const SERIES = ["bg-series-1", "bg-series-2", "bg-accent-mid", "bg-status-warning"];

/** Cuántos agentes enseña «Agentes que más consumen» (prototipo §4.4). */
const TOP = 4;

/**
 * Spec 047 (T159): lo que el Panel sabe del dinero además de la bolsa: la moneda
 * de la bolsa (para el tope de cada agente y los ceros sin saldo asignado), si
 * esta persona puede fijar topes (`usage:write`) y el relleno mensual, si lo
 * tiene.
 */
export type PanelMoney = { currency: "EUR" | "USD"; canSetCap: boolean; refillUpTo: MoneyValue | null };

/**
 * El Panel de un cliente (spec 047, T067, requisito 14) como el prototipo
 * aprobado (`clientes.md` §4, hueco H4): dos columnas, 1,35 : 1. A la
 * izquierda, mientras dura la lectura de la web, su tarjeta; «Saldo» (lo que
 * queda en grande, lo consumido y lo disponible, la barra por agente medida
 * contra lo asignado con «Disponible» en la leyenda y los avisos) con «Asignar
 * saldo» en su cabecera; y «Este mes» con tres cifras. A la derecha, «Agentes
 * que más consumen», con el tope de cada uno todavía editable desde su línea.
 * Lo que le falta a la ficha no se anuncia aquí: se ve en Negocio, con su
 * marca (Andrés, 2026-10-28). Todas las
 * cifras vienen de la API, que las saca de las mismas cuentas que Consumo y la
 * consola lite.
 */
export function ClientPanelView({
  panel,
  money,
  openBalance = false,
  now,
}: {
  panel: Panel;
  money?: PanelMoney;
  /** `?assign=1`: el aviso de saldo (o «Pedir saldo») abre aquí mismo «Asignar saldo» (45.1). */
  openBalance?: boolean;
  /** Hoy, para el periodo de «Este mes»; los tests lo fijan. */
  now?: Date;
}) {
  // «Asignar saldo» en el sitio (45.1); quien no puede asignar, «Pedir saldo» (45.7).
  const balanceMode = panel.lifecycle === "archived" ? null : panel.allowed.includes("assign_balance") ? "assign" : panel.allowed.includes("request_balance") ? "request" : null;

  return (
    <div className="grid min-w-0 gap-4" data-slot="client-panel">
      <div data-slot="client-panel-grid" className="grid min-w-0 items-start gap-4 min-[980px]:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="grid min-w-0 gap-4">
          <BalanceCard panel={panel} money={money} mode={balanceMode} openBalance={openBalance} />
          <MonthCard panel={panel} now={now} />
        </div>
        <TopAgentsCard panel={panel} money={money} />
      </div>
    </div>
  );
}

/** Una tarjeta con su título (una región con nombre) y lo que va a su derecha. */
function PanelCard({ title, aside, children, slot }: { title: string; aside?: React.ReactNode; children: React.ReactNode; slot: string }) {
  const id = React.useId();
  return (
    <section aria-labelledby={id} className="min-w-0" data-slot={slot}>
      <Card>
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 px-4">
          <h2 id={id} className="text-base font-semibold">
            {title}
          </h2>
          {aside}
        </div>
        <CardContent className="grid min-w-0 gap-4">{children}</CardContent>
      </Card>
    </section>
  );
}

/** «Saldo» (prototipo §4.2). */
function BalanceCard({ panel, money, mode, openBalance }: { panel: Panel; money?: PanelMoney; mode: "assign" | "request" | null; openBalance: boolean }) {
  const t = useT();
  const { bag } = panel;
  const currency = money?.currency ?? bag.balance?.currency ?? bag.assigned?.currency ?? null;
  const zero: MoneyValue | null = currency ? { amount_micros: 0, currency } : null;
  const unassigned = bag.state === "unassigned" || !bag.assigned;
  const pct = Math.min(100, Math.max(0, Math.round(bag.pct_spent ?? 0)));
  const avail = 100 - pct;
  const days = roundDays(bag.days_left);
  const segments = spendSegments(bag, panel.spend_by_agent);
  const left = unassigned ? zero : (bag.balance ?? zero);
  const spent = unassigned ? zero : (bag.spent ?? zero);
  const assigned = unassigned ? zero : bag.assigned;

  const aside =
    mode === "assign" ? (
      <AssignBalanceButton refId={panel.ref} name={panel.name} defaultOpen={openBalance} />
    ) : mode === "request" ? (
      <BalanceButton refId={panel.ref} name={panel.name} mode="request" variant="outline" size="sm" defaultOpen={openBalance} />
    ) : null;

  if (bag.state === "unlimited") {
    return (
      <PanelCard title={t("panel.bag.title")} aside={aside} slot="panel-balance">
        <p className="text-sm text-muted-foreground">{t("panel.bag.unlimited")}</p>
      </PanelCard>
    );
  }

  const stackLabel = unassigned
    ? t("panel.bag.byAgent")
    : `${t("panel.bag.byAgent")}: ${[
        ...segments.map((s) => t("panel.bag.share", { name: s.name, amount: formatMoneyText(s.spent) })),
        t("panel.proto.legend.availablePct", { pct: avail }),
      ].join(", ")}`;

  return (
    <PanelCard title={t("panel.bag.title")} aside={aside} slot="panel-balance">
      <div className="flex min-w-0 flex-wrap items-end justify-between gap-4">
        <div className="grid min-w-0 gap-1">
          <span className="text-xs text-muted-foreground">{t("panel.proto.left")}</span>
          <span data-slot="panel-left" className="text-2xl font-semibold tracking-tight tabular-nums">
            {left ? <Money value={left} /> : "—"}
          </span>
          {!unassigned ? (
            <span className="text-xs text-pretty text-muted-foreground">
              {days != null && bag.days_estimable ? t("panel.bag.days", { days }) : t("panel.bag.noEstimate")}
            </span>
          ) : null}
        </div>
        <div className="grid min-w-0 gap-1 text-right text-ui">
          <span className="tabular-nums">
            {spent && assigned
              ? fill(unassigned ? t("panel.proto.spent", { spent: A, assigned: B }) : t("panel.bag.spent", { spent: A, assigned: B, pct }), {
                  [A]: (
                    <strong className="font-medium">
                      <Money value={spent} />
                    </strong>
                  ),
                  [B]: <Money value={assigned} />,
                })
              : "—"}
          </span>
          <span className="text-muted-foreground">{unassigned ? t("panel.proto.shared") : t("panel.proto.available", { pct: avail })}</span>
        </div>
      </div>

      <div className="grid min-w-0 gap-3">
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label={stackLabel}>
          {segments.map((s, i) => (
            <span
              key={s.agent_id}
              title={s.name}
              className={cn("block h-full shrink-0", SERIES[i % SERIES.length], i > 0 && "shadow-[-1px_0_0_var(--card)]")}
              style={{ width: `${s.pct}%` }}
            />
          ))}
        </div>
        {!unassigned ? (
          <ul data-slot="panel-legend" aria-hidden="true" className="flex min-w-0 flex-wrap gap-x-4 gap-y-2 text-ui text-muted-foreground">
            {segments.map((s, i) => (
              <li key={s.agent_id} className="flex min-w-0 items-center gap-2">
                <span className={cn("size-2 shrink-0 rounded-sm", SERIES[i % SERIES.length])} />
                <span className="truncate">{s.name}</span>
              </li>
            ))}
            <li className="flex items-center gap-2">
              <span className="size-2 shrink-0 rounded-sm bg-muted ring-1 ring-input ring-inset" />
              {t("panel.proto.legend.available")}
            </li>
          </ul>
        ) : null}
      </div>

      {unassigned ? (
        <Callout tone="danger">
          <strong className="font-medium">{t("panel.proto.unassigned.lead")}</strong> {t("panel.proto.unassigned.body")}
        </Callout>
      ) : bag.alerts.includes("empty") ? (
        <Callout tone="danger">{t("panel.bag.empty")}</Callout>
      ) : bag.alerts.includes("warn_80") ? (
        <Callout tone="warning">
          <strong className="font-medium">{t("panel.proto.warn.lead")}</strong> {t("panel.proto.warn.body")}
        </Callout>
      ) : null}

      {money?.refillUpTo ? (
        <p className="text-xs text-muted-foreground" data-slot="panel-refill">
          {t("money.panel.refill", { amount: formatMoneyText(money.refillUpTo) })}
        </p>
      ) : null}
    </PanelCard>
  );
}

/** «+ Asignar saldo», pequeño y en contorno, que abre la ventana aquí mismo (45.1). */
function AssignBalanceButton({ refId, name, defaultOpen }: { refId: string; name: string; defaultOpen: boolean }) {
  const t = useT();
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)} data-slot="assign-balance">
        <Plus aria-hidden="true" />
        {t("money.assign.cta")}
      </Button>
      <BalanceDialogs refId={refId} name={name} open={open ? "assign" : null} onClose={() => setOpen(false)} />
    </>
  );
}

/** «Este mes» (prototipo §4.3): tres cifras y el periodo, del día 1 a hoy. */
function MonthCard({ panel, now }: { panel: Panel; now?: Date }) {
  const t = useT();
  const locale = useLocale();
  const { month } = panel;
  const period = periodLabel(month.period_start, month.period_end, now ?? new Date(), locale);
  return (
    <PanelCard
      title={t("panel.month.title")}
      slot="panel-month"
      aside={
        // «Hoy» puede cambiar entre el servidor y el navegador justo a medianoche (UTC).
        <span className="text-xs text-muted-foreground" suppressHydrationWarning>
          {period}
        </span>
      }
    >
      <dl className="grid min-w-0 grid-cols-3 gap-3">
        <Figure label={t("panel.month.conversations")} value={formatNumber(month.conversations, locale)} />
        <Figure label={t("panel.month.resolved")} value={month.conversations && month.resolved_pct != null ? `${Math.round(month.resolved_pct)} %` : "—"} />
        <Figure label={t("panel.month.handed")} value={formatNumber(month.handed_to_person, locale)} />
      </dl>
    </PanelCard>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 content-start gap-1">
      <dt className="order-2 text-ui text-pretty text-muted-foreground">{label}</dt>
      <dd className="order-1 text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

/** «Agentes que más consumen» (prototipo §4.4): los cuatro primeros, con su barra y su línea. */
function TopAgentsCard({ panel, money }: { panel: Panel; money?: PanelMoney }) {
  const t = useT();
  const locale = useLocale();
  const top = panel.top_agents.slice(0, TOP);
  const max = Math.max(0, ...top.map((a) => a.spent.amount_micros));
  const capCurrency = money?.currency ?? panel.bag.balance?.currency ?? null;
  const canSetCap = Boolean(money?.canSetCap && capCurrency);
  const viewAll = (
    <Link
      href={clientHref(panel.ref, "agents")}
      className="rounded-sm text-ui font-medium text-status-positive-text underline decoration-status-positive-text/40 underline-offset-4 outline-none hover:decoration-current focus-visible:ring-2 focus-visible:ring-ring"
    >
      {t("panel.proto.viewAll")}
    </Link>
  );

  return (
    <PanelCard title={t("panel.top.title")} aside={viewAll} slot="panel-top">
      {panel.agents_total === 0 ? (
        <div className="grid justify-items-center gap-3 py-4 text-center">
          {/* Sin botón: «Nuevo agente» ya está en la cabecera del cliente (un primario por vista). */}
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("panel.top.none.body")}</p>
        </div>
      ) : (
        <ol className="grid min-w-0">
          {top.map((a, i) => {
            const width = max > 0 ? Math.round((a.spent.amount_micros / max) * 10_000) / 100 : 0;
            const capNode = canSetCap ? (
              <AgentCapButton refId={panel.ref} agentId={a.agent_id} agentName={a.name} cap={a.cap} currency={capCurrency!} canWrite />
            ) : a.cap ? (
              formatMoneyText(a.cap)
            ) : null;
            return (
              <li key={a.agent_id} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 border-b border-border py-3 last:border-b-0">
                <div className="flex min-w-0 items-center gap-2">
                  <Link
                    href={agentHref(panel.ref, a.agent_id)}
                    title={a.name}
                    className="min-w-0 truncate rounded-sm font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {a.name}
                  </Link>
                  <StatusBadge tone={a.visible_state.tone}>{agentStateText(t, a.visible_state)}</StatusBadge>
                </div>
                <span className="text-right font-medium tabular-nums">
                  <Money value={a.spent} />
                </span>
                <span data-slot="rank-bar" aria-hidden="true" className="col-span-2 block h-2 overflow-hidden rounded-full bg-muted">
                  <span className={cn("block h-full rounded-full", SERIES[i % SERIES.length])} style={{ width: `${width}%` }} />
                </span>
                <p data-slot="rank-sub" className="col-span-2 text-xs text-pretty text-muted-foreground tabular-nums">
                  {t(a.conversations === 1 ? "panel.proto.conversations.one" : "panel.proto.conversations.other", { n: formatNumber(a.conversations, locale) })}
                  {a.conversations && a.spend_per_conversation ? ` · ${t("panel.proto.perConversation", { amount: formatMoneyText(a.spend_per_conversation) })}` : null}
                  {a.cap && capNode ? (
                    <>
                      {" · "}
                      {fill(t("panel.proto.cap", { amount: A, pct: capPct(a.spent, a.cap) }), { [A]: capNode })}
                    </>
                  ) : capNode ? (
                    <>
                      {" · "}
                      {capNode}
                    </>
                  ) : null}
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </PanelCard>
  );
}

/** Marcas para meter nodos (dinero, enlaces) dentro de una frase traducida. */
const A = "\u0000";
const B = "\u0001";

function fill(text: string, nodes: Record<string, React.ReactNode>): React.ReactNode {
  return text.split(/(\u0000|\u0001)/).map((part, i) => <React.Fragment key={i}>{Object.hasOwn(nodes, part) ? nodes[part] : part}</React.Fragment>);
}

function formatMoneyText(value: { amount_micros: number; currency: "EUR" | "USD" }): string {
  // El mismo formato que `<Money>` (`es-ES`, el símbolo detrás), en texto para
  // las etiquetas accesibles y las frases.
  return formatMoney(value.amount_micros / MICROS_PER_UNIT, value.currency);
}
