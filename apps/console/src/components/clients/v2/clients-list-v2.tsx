"use client";

import { Building2, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, EmptyState, Input, Money, StatusBadge, StatusDot } from "@nexus/ui";

import { clientHref } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Bag, ClientCounts, ClientFilter, ClientRowV2 } from "@/lib/backend/client-records";

import { ClientMenu } from "./client-menu";
import { FILTERS, agentStateText, filterHref, roundDays, stateView } from "./client-v2-model";

const DOT_TONE = { positive: "positive", info: "info", warn: "warning", danger: "danger", muted: "muted" } as const;

function BagCell({ bag }: { bag: Bag | null }) {
  const t = useT();
  if (!bag || bag.state === "unassigned") return <span className="text-sm text-muted-foreground">{t("clients.v2.bag.unassigned")}</span>;
  if (bag.state === "unlimited") return <span className="text-sm text-muted-foreground">{t("clients.v2.bag.unlimited")}</span>;
  if (bag.state === "empty") {
    return (
      <StatusBadge tone="danger">
        {t("clients.v2.bag.empty")}
      </StatusBadge>
    );
  }
  const days = roundDays(bag.days_left);
  return (
    <div className="grid min-w-0 gap-1 text-sm">
      <span className="min-w-0">
        <BagLine bag={bag} />
      </span>
      <span className="text-xs text-muted-foreground tabular-nums">
        {days != null ? t("clients.v2.bag.days", { days }) : t("clients.v2.bag.noEstimate")}
        {bag.pct_left != null ? ` · ${t("clients.v2.bag.pct", { pct: Math.round(bag.pct_left) })}` : ""}
      </span>
    </div>
  );
}

/** «Quedan 8,00 USD de 50,00 USD», con los importes como dinero. */
function BagLine({ bag }: { bag: Bag }) {
  const t = useT();
  if (!bag.balance || !bag.assigned) return null;
  const parts = t("clients.v2.bag.left", { left: "\u0000", assigned: "\u0001" }).split(/(\u0000|\u0001)/);
  return (
    <>
      {parts.map((p, i) =>
        p === "\u0000" ? <Money key={i} value={bag.balance!} /> : p === "\u0001" ? <Money key={i} value={bag.assigned!} /> : <React.Fragment key={i}>{p}</React.Fragment>,
      )}
    </>
  );
}

/**
 * La lista de clientes de la consola nueva (spec 047, T065, requisito 7): quién
 * necesita algo y por qué, sus agentes con un punto del color de su estado, su
 * bolsa y el menú ⋯ con lo permitido. Se busca por nombre o nicho y se filtra
 * con contadores. La tabla se desplaza dentro de su caja por debajo de 760 px:
 * la página nunca. El orden y la regla los pone la API.
 */
export function ClientsListV2({
  items,
  counts,
  filter,
  q,
  total,
  page,
  limit,
}: {
  items: ClientRowV2[];
  counts: ClientCounts;
  filter: ClientFilter;
  q: string;
  total: number;
  page: number;
  limit: number;
}) {
  const t = useT();
  const searchId = React.useId();
  const pages = Math.max(1, Math.ceil(total / limit));
  const href = (p: number) => {
    const base = filterHref(filter, q);
    return p <= 1 ? base : `${base}${base.includes("?") ? "&" : "?"}page=${p}`;
  };

  return (
    <div className="grid min-w-0 gap-4" data-slot="clients-list-v2">
      <form role="search" action="/clients" method="get" className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        <label htmlFor={searchId} className="sr-only">
          {t("clients.v2.search.label")}
        </label>
        <Input id={searchId} name="q" type="search" defaultValue={q} placeholder={t("clients.v2.search.placeholder")} className="min-w-0 sm:max-w-sm" />
        {filter !== "all" ? <input type="hidden" name="filter" value={filter} /> : null}
        <Button type="submit" variant="outline">
          <Search aria-hidden="true" />
          {t("clients.v2.search.submit")}
        </Button>
      </form>

      <nav aria-label={t("clients.v2.filters")} className="min-w-0">
        <ul className="inline-flex w-fit max-w-full min-w-0 items-center gap-1 overflow-x-auto rounded-full bg-muted p-1">
          {FILTERS.map((f) => (
            <li key={f} className="shrink-0">
              <Link
                href={filterHref(f, q)}
                aria-current={f === filter ? "page" : undefined}
                className="inline-flex h-8 items-center rounded-full px-3 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-[current=page]:bg-card aria-[current=page]:text-foreground aria-[current=page]:shadow-sm"
              >
                {t(`clients.v2.filter.${f}` as MessageKey, { n: counts[f] })}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {items.length === 0 ? (
        counts.all === 0 && !q ? (
          <EmptyState readonly icon={Building2} title={t("clients.v2.empty.title")} description={t("clients.v2.empty.body")} />
        ) : (
          <p className="text-sm text-muted-foreground" role="status">
            {q ? t("clients.v2.empty.search", { q }) : t("clients.v2.empty.filter")}
          </p>
        )
      ) : (
        <div className="relative min-w-0 overflow-x-auto rounded-md border border-border" role="region" aria-label={t("clients.v2.table.caption")} tabIndex={0}>
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <caption className="sr-only">{t("clients.v2.table.caption")}</caption>
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">{t("clients.v2.col.client")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("clients.v2.col.state")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("clients.v2.col.agents")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("clients.v2.col.bag")}</th>
                <th scope="col" className="w-12 px-3 py-2 font-medium">
                  <span className="sr-only">{t("clients.v2.col.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const state = stateView(t, row.lifecycle, row.attention, row.bag);
                const summary = row.agents_summary;
                return (
                  <tr key={row.external_client_ref} className="border-t border-border align-top">
                    <td className="max-w-64 px-3 py-3">
                      <Link href={clientHref(row.external_client_ref)} className="block min-w-0 truncate font-medium underline-offset-4 hover:underline" title={row.name}>
                        {row.name}
                      </Link>
                      {row.niche ? (
                        <span className="block min-w-0 truncate text-xs text-muted-foreground" title={row.niche}>
                          {row.niche}
                        </span>
                      ) : null}
                    </td>
                    <td className="max-w-56 px-3 py-3">
                      <StatusBadge tone={state.tone} className="max-w-full">
                        <span className="truncate">{state.label}</span>
                      </StatusBadge>
                      {state.more.length ? <span className="mt-1 block text-xs text-muted-foreground text-pretty">{state.more.join(" · ")}</span> : null}
                    </td>
                    <td className="px-3 py-3">
                      {row.agents.length ? (
                        <div className="grid gap-1">
                          <ul className="flex flex-wrap gap-1" aria-label={t("clients.v2.col.agents")}>
                            {row.agents.map((a) => (
                              <li key={a.agent_id} title={t("clients.v2.agents.dot", { name: a.name, state: agentStateText(t, a.visible_state) })}>
                                <StatusDot tone={DOT_TONE[a.visible_state.tone]} label={t("clients.v2.agents.dot", { name: a.name, state: agentStateText(t, a.visible_state) })} />
                              </li>
                            ))}
                          </ul>
                          {summary ? (
                            <span className="text-xs text-muted-foreground">{t("clients.v2.agents.summary", { serving: summary.serving, total: summary.total })}</span>
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">{t("clients.v2.agents.none")}</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <BagCell bag={row.bag} />
                    </td>
                    <td className="px-3 py-3 text-right">
                      <ClientMenu refId={row.external_client_ref} name={row.name} allowed={row.allowed} afterDelete={null} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 ? (
        <nav aria-label={t("clients.v2.page", { page })} className="flex items-center justify-between gap-2 text-sm">
          {page > 1 ? (
            <Button variant="outline" size="sm" nativeButton={false} render={<Link href={href(page - 1)} />}>
              {t("clients.v2.previous")}
            </Button>
          ) : (
            <span />
          )}
          <span className="text-muted-foreground">{t("clients.v2.page", { page })}</span>
          {page < pages ? (
            <Button variant="outline" size="sm" nativeButton={false} render={<Link href={href(page + 1)} />}>
              {t("clients.v2.next")}
            </Button>
          ) : (
            <span />
          )}
        </nav>
      ) : null}
    </div>
  );
}
