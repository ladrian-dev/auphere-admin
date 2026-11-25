"use client";

import { Building2, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, EmptyState, Input, Money, NativeSelect, StatusBadge, cn } from "@nexus/ui";

import { moneyText } from "@/components/money/money-model";
import { clientHref } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AgentVisible, Bag, ClientCounts, ClientFilter, ClientRowV2 } from "@/lib/backend/client-records";

import { ClientMenu } from "./client-menu";
import { FILTERS, agentStateText, agentsText, bagBar, bagPace, filterHref, liveAgents, parseFilter, stateView } from "./client-v2-model";
import { BagMeter } from "./bag-meter";

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

/**
 * La columna «Saldo» — spec 072 (2.1–2.3, 2.6): «17,70 USD · quedan de 60,00
 * USD», la minibarra de lo que queda y cuánto dura a este ritmo. La barra dice
 * lo mismo que se lee; el ámbar, en la barra y en su texto, nunca en la fila.
 */
function BagCell({ bag, wide = false }: { bag: Bag | null; wide?: boolean }) {
  const t = useT();
  const bar = bagBar(bag);
  if (!bar) return <span className="text-ui text-muted-foreground">{t("clients.v2.bag.unlimited")}</span>;
  const assigned = bag && bag.state !== "unassigned" && bag.assigned ? bag : null;
  const pace = bagPace(t, bag);
  const label = [assigned?.balance && assigned.assigned ? bagLeftText(t, assigned) : t("clients.v2.bag.unassigned"), pace].filter(Boolean).join(". ");
  return (
    <div className="grid min-w-0 gap-1">
      <span data-slot="bag-line" className={cn("text-ui tabular-nums", wide ? "min-w-0 break-words" : "whitespace-nowrap")}>
        {assigned ? <BagLine bag={assigned} /> : t("clients.v2.bag.unassigned")}
      </span>
      <BagMeter bag={bag} bar={bar} label={label} pace={pace} className={wide ? "w-full" : "w-30 max-w-full"} />
    </div>
  );
}

/** La misma línea, en texto (el nombre de la barra). */
function bagLeftText(t: ReturnType<typeof useT>, bag: Bag): string {
  return t("clients.v2.bag.left", { left: moneyText(bag.balance!), assigned: moneyText(bag.assigned!) });
}

/** «17,70 USD · quedan de 60,00 USD», con los importes como dinero. */
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
 * Los agentes de un cliente: un punto por agente y el texto (prototipo §1.3).
 * En la tabla no se parte; en la tarjeta del móvil, si no cabe, baja de línea.
 */
function AgentsCell({ row, wrap = false }: { row: ClientRowV2; wrap?: boolean }) {
  const t = useT();
  const agents = liveAgents(row.agents);
  return (
    <div className={cn("flex min-w-0 items-center gap-2", wrap && "flex-wrap")}>
      {agents.length ? (
        <ul className={cn("flex shrink-0 items-center gap-1", wrap && "flex-wrap")} aria-label={t("clients.v2.col.agents")}>
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
      <span className={cn("text-ui text-muted-foreground", wrap ? "min-w-0" : "whitespace-nowrap")}>{agentsText(t, row.agents_summary, row.agents)}</span>
    </div>
  );
}

/** El punto de ruptura de la lista: la anchura que pide la tabla (`min-w-[760px]`). */
const PHONE_ONLY = "min-[760px]:hidden";
const WIDE_ONLY = "max-[760px]:hidden";

/**
 * La lista de clientes de la consola nueva (spec 047, T065, requisito 7), como
 * el prototipo aprobado (`clientes.md` §2, hueco H6): el buscador con lupa que
 * filtra mientras se escribe, el filtro en un select con sus cuentas, y la
 * tabla con quién necesita algo («Al día» si nada), sus agentes en puntos y en
 * texto, su saldo con la minibarra de lo gastado y el menú ⋯. Toda la fila
 * abre el cliente; el nombre sigue siendo el enlace (el foco de teclado). La
 * tabla se desplaza dentro de su caja si su caja no llega a 760 px: la página
 * nunca. Por debajo de 760 px de pantalla (el móvil), spec 074 (M01): «una sola
 * navegación en el móvil, sin perder acciones», así que cada cliente es una
 * tarjeta con todo lo de su fila (nombre y nicho, estado, agentes, saldo con su
 * barra y el mismo ⋯) en lugar de una tabla que esconde columnas. La tarjeta
 * entera abre el cliente y el nombre sigue siendo el foco de teclado; el nombre
 * y el ⋯ miden al menos 44 × 44. El orden y la regla los pone la API.
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
  function openRow(event: React.MouseEvent<HTMLElement>, to: string) {
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
            className={cn("relative min-w-0 overflow-x-auto rounded-lg border border-border bg-card", WIDE_ONLY)}
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
                          <AgentsCell row={row} />
                        </td>
                        <td className="px-3 py-4">
                          <BagCell bag={row.bag} />
                        </td>
                        <td className="px-3 py-4 text-right">
                          <ClientMenu refId={row.external_client_ref} name={row.name} allowed={row.allowed} deleteBlocked={row.delete_blocked ?? null} afterDelete={null} />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Spec 074 (M01): el móvil, una tarjeta por cliente con todo lo de su fila. */}
          {items.length === 0 ? (
            <div data-slot="clients-cards-empty" className={cn("rounded-lg border border-border bg-card px-5 py-10 text-center", PHONE_ONLY)}>
              <p className="text-sm text-muted-foreground" role="status">
                {q ? t("clients.v2.empty.search", { q }) : t("clients.v2.empty.filter")}
              </p>
            </div>
          ) : (
            <ul
              data-slot="clients-cards"
              aria-label={t("clients.v2.table.caption")}
              className={cn("grid min-w-0 divide-y divide-border rounded-lg border border-border bg-card", PHONE_ONLY)}
            >
              {items.map((row) => {
                const state = stateView(t, row.lifecycle, row.attention, row.bag);
                const to = clientHref(row.external_client_ref);
                return (
                  <li
                    key={row.external_client_ref}
                    data-slot="client-card"
                    onClick={(e) => openRow(e, to)}
                    className="grid min-w-0 cursor-pointer gap-3 px-4 pt-1 pb-4 transition-colors duration-[120ms] first:rounded-t-lg last:rounded-b-lg hover:bg-muted motion-reduce:transition-none"
                  >
                    <div className="flex min-w-0 items-start gap-2">
                      <div className="grid min-w-0 flex-1">
                        {/* `py-3`: el nombre mide 44 px de alto, el objetivo táctil del móvil. */}
                        <Link
                          href={to}
                          className="block min-w-0 truncate py-3 font-medium underline-offset-4 outline-none hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring"
                          title={row.name}
                        >
                          {row.name}
                        </Link>
                        {row.niche ? (
                          <span className="-mt-2 block min-w-0 truncate text-ui text-muted-foreground" title={row.niche}>
                            {row.niche}
                          </span>
                        ) : null}
                      </div>
                      <ClientMenu
                        refId={row.external_client_ref}
                        name={row.name}
                        allowed={row.allowed}
                        deleteBlocked={row.delete_blocked ?? null}
                        afterDelete={null}
                        triggerClassName="-mr-2 size-11"
                      />
                    </div>
                    <div className="flex min-w-0">
                      <StatusBadge tone={state.tone} className="max-w-full">
                        {state.label}
                      </StatusBadge>
                    </div>
                    <AgentsCell row={row} wrap />
                    <BagCell bag={row.bag} wide />
                  </li>
                );
              })}
            </ul>
          )}
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
