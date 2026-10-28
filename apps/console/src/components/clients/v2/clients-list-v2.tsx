"use client";

import { Building2, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, EmptyState, Input, Money, NativeSelect, StatusBadge, cn } from "@nexus/ui";

import { clientHref } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AgentVisible, Bag, ClientCounts, ClientFilter, ClientRowV2 } from "@/lib/backend/client-records";

import { ClientMenu } from "./client-menu";
import { FILTERS, agentStateText, agentsText, bagBar, bagBarTitle, filterHref, liveAgents, parseFilter, stateView, type BagBar } from "./client-v2-model";

/** La espera del buscador antes de pedir la lista (prototipo §2.2: filtra al escribir). */
const SEARCH_DELAY_MS = 250;

/**
 * El punto de cada agente (prototipo §1.3): relleno si atiende, prueba o está
 * en pausa; un anillo vacío si es un borrador o está listo sin canal.
 */
const DOT: Record<AgentVisible, string> = {
  serving: "bg-status-positive",
  testing: "bg-status-info",
  paused: "bg-status-warning",
  ready_no_channel: "border-[1.5px] border-status-info",
  draft: "border-[1.5px] border-muted-foreground/45",
  archived: "bg-muted-foreground/40",
};

const BAR_FILL: Record<BagBar["tone"], string> = {
  ok: "bg-series-1",
  warn: "bg-status-warning",
  danger: "bg-status-danger",
};

/** La columna «Saldo»: la minibarra de lo gastado y «Quedan {x} de {y}» o «Sin saldo asignado». */
function BagCell({ bag }: { bag: Bag | null }) {
  const t = useT();
  const bar = bagBar(bag);
  if (!bar) return <span className="text-ui text-muted-foreground">{t("clients.v2.bag.unlimited")}</span>;
  const assigned = bag && bag.state !== "unassigned" && bag.assigned ? bag : null;
  return (
    <div className="grid min-w-0 gap-2">
      <span
        data-slot="bag-bar"
        data-tone={bar.tone}
        title={bagBarTitle(t, bag)}
        aria-hidden="true"
        className="block h-2 w-30 max-w-full overflow-hidden rounded-full bg-muted"
      >
        <span className={cn("block h-full rounded-full", BAR_FILL[bar.tone])} style={{ width: `${bar.pct}%` }} />
      </span>
      <span data-slot="bag-line" className="text-ui whitespace-nowrap text-muted-foreground tabular-nums">
        {assigned ? <BagLine bag={assigned} /> : t("clients.v2.bag.unassigned")}
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
 * La lista de clientes de la consola nueva (spec 047, T065, requisito 7), como
 * el prototipo aprobado (`clientes.md` §2, hueco H6): el buscador con lupa que
 * filtra mientras se escribe, el filtro en un select con sus cuentas, y la
 * tabla con quién necesita algo («Al día» si nada), sus agentes en puntos y en
 * texto, su saldo con la minibarra de lo gastado y el menú ⋯. Toda la fila
 * abre el cliente; el nombre sigue siendo el enlace (el foco de teclado). La
 * tabla se desplaza dentro de su caja por debajo de 760 px: la página nunca.
 * El orden y la regla los pone la API.
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
  const router = useRouter();
  const searchId = React.useId();
  const filterId = React.useId();
  const pages = Math.max(1, Math.ceil(total / limit));
  const href = (p: number) => {
    const base = filterHref(filter, q);
    return p <= 1 ? base : `${base}${base.includes("?") ? "&" : "?"}page=${p}`;
  };

  // Lo que se escribe manda en el buscador; lo último pedido evita repetirlo y
  // deja entrar una búsqueda que llegue de fuera (atrás, un enlace).
  const [value, setValue] = React.useState(q);
  const [current, setCurrent] = React.useState(filter);
  const [shownFilter, setShownFilter] = React.useState(filter);
  if (shownFilter !== filter) {
    setShownFilter(filter);
    setCurrent(filter);
  }
  const sent = React.useRef(q);
  React.useEffect(() => {
    if (q.trim() === sent.current.trim()) return;
    sent.current = q;
    setValue(q);
  }, [q]);
  React.useEffect(() => {
    if (value.trim() === sent.current.trim()) return;
    const id = window.setTimeout(() => {
      sent.current = value;
      router.replace(filterHref(current, value), { scroll: false });
    }, SEARCH_DELAY_MS);
    return () => window.clearTimeout(id);
  }, [value, current, router]);

  function search(event: React.FormEvent) {
    event.preventDefault();
    sent.current = value;
    router.replace(filterHref(current, value), { scroll: false });
  }

  function changeFilter(next: ClientFilter) {
    setCurrent(next);
    sent.current = value;
    router.replace(filterHref(next, value), { scroll: false });
  }

  /** Toda la fila abre el cliente, salvo sus controles y lo que se abre desde ella (menú, ventanas). */
  function openRow(event: React.MouseEvent<HTMLTableRowElement>, to: string) {
    const target = event.target as Element;
    if (!event.currentTarget.contains(target)) return;
    if (target.closest("a, button, input, select, textarea, [role=menuitem]")) return;
    if (window.getSelection?.()?.toString()) return;
    if (event.metaKey || event.ctrlKey) {
      window.open(to, "_blank", "noopener");
      return;
    }
    router.push(to);
  }

  const noClients = counts.all === 0 && !q;

  return (
    <div className="grid min-w-0 gap-5" data-slot="clients-list-v2">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <form role="search" onSubmit={search} className="relative max-w-110 min-w-50 flex-1">
          <label htmlFor={searchId} className="sr-only">
            {t("clients.v2.search.label")}
          </label>
          <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id={searchId}
            name="q"
            type="search"
            autoComplete="off"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={t("clients.v2.search.placeholder")}
            className="pl-8"
          />
        </form>
        <label htmlFor={filterId} className="sr-only">
          {t("clients.v2.filters")}
        </label>
        <NativeSelect id={filterId} value={current} onChange={(e) => changeFilter(parseFilter(e.target.value))} wrapperClassName="min-w-60">
          {FILTERS.map((f) => (
            <option key={f} value={f}>
              {t(`clients.v2.filter.${f}` as MessageKey, { n: counts[f] })}
            </option>
          ))}
        </NativeSelect>
      </div>

      {noClients ? (
        <EmptyState readonly icon={Building2} title={t("clients.v2.empty.title")} description={t("clients.v2.empty.body")} />
      ) : (
        <div className="grid min-w-0 gap-3">
          <div
            className="relative min-w-0 overflow-x-auto rounded-lg border border-border bg-card"
            role="region"
            aria-label={t("clients.v2.table.caption")}
            tabIndex={0}
          >
            <table className="w-full min-w-[760px] border-collapse text-left text-sm">
              <caption className="sr-only">{t("clients.v2.table.caption")}</caption>
              <thead className="text-ui text-muted-foreground">
                <tr>
                  <th scope="col" className="w-[32%] px-3 py-3 font-medium">
                    {t("clients.v2.col.client")}
                  </th>
                  <th scope="col" className="px-3 py-3 font-medium">{t("clients.v2.col.state")}</th>
                  <th scope="col" className="px-3 py-3 font-medium">{t("clients.v2.col.agents")}</th>
                  <th scope="col" className="px-3 py-3 font-medium">{t("clients.v2.col.bag")}</th>
                  <th scope="col" className="w-12 px-3 py-3 font-medium">
                    <span className="sr-only">{t("clients.v2.col.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr className="border-t border-border">
                    <td colSpan={5} className="px-5 py-10 text-center">
                      <p className="text-sm text-muted-foreground" role="status">
                        {q ? t("clients.v2.empty.search", { q }) : t("clients.v2.empty.filter")}
                      </p>
                    </td>
                  </tr>
                ) : (
                  items.map((row) => {
                    const state = stateView(t, row.lifecycle, row.attention, row.bag);
                    const agents = liveAgents(row.agents);
                    const to = clientHref(row.external_client_ref);
                    return (
                      <tr
                        key={row.external_client_ref}
                        onClick={(e) => openRow(e, to)}
                        className="cursor-pointer border-t border-border align-middle transition-colors duration-[120ms] hover:bg-muted motion-reduce:transition-none"
                      >
                        <td className="max-w-64 px-3 py-4">
                          <Link
                            href={to}
                            className="block min-w-0 truncate font-medium underline-offset-4 outline-none hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring"
                            title={row.name}
                          >
                            {row.name}
                          </Link>
                          {row.niche ? (
                            <span className="block min-w-0 truncate text-ui text-muted-foreground" title={row.niche}>
                              {row.niche}
                            </span>
                          ) : null}
                        </td>
                        <td className="max-w-56 px-3 py-4">
                          <StatusBadge tone={state.tone} className="max-w-full">
                            {state.label}
                          </StatusBadge>
                        </td>
                        <td className="px-3 py-4">
                          <div className="flex min-w-0 items-center gap-2">
                            {agents.length ? (
                              <ul className="flex shrink-0 items-center gap-1" aria-label={t("clients.v2.col.agents")}>
                                {agents.map((a) => {
                                  const label = t("clients.v2.agents.dot", { name: a.name, state: agentStateText(t, a.visible_state) });
                                  return (
                                    <li key={a.agent_id} title={label}>
                                      <span role="img" aria-label={label} className={cn("block size-2 rounded-full", DOT[a.visible_state.code])} />
                                    </li>
                                  );
                                })}
                              </ul>
                            ) : null}
                            <span className="text-ui whitespace-nowrap text-muted-foreground">{agentsText(t, row.agents_summary, row.agents)}</span>
                          </div>
                        </td>
                        <td className="px-3 py-4">
                          <BagCell bag={row.bag} />
                        </td>
                        <td className="px-3 py-4 text-right">
                          <ClientMenu refId={row.external_client_ref} name={row.name} allowed={row.allowed} afterDelete={null} />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">{t("clients.proto.footer")}</p>
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
