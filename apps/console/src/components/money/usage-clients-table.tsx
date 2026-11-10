"use client";

import Link from "next/link";
import * as React from "react";

import { StatusBadge } from "@nexus/ui";

import { RowActions, type RowAction } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import { clientHref } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
import type { ClientUsage } from "@/lib/backend/money-types";

import { BalanceDialogs } from "./balance-button";
import { CurrencyDialog, MoveDialog, RefillDialog, type BagRef } from "./bag-dialogs";
import { daysText, moneyText, requestedText } from "./money-model";
import { useRequested } from "./request-balance";

type Open =
  | { kind: "assign" | "change" | "request"; row: ClientUsage }
  | { kind: "move" | "refill" | "currency"; row: ClientUsage }
  | null;

/** «Ver su gasto»: la gráfica y el detalle de Consumo filtrados por ese cliente. */
export function spendHref(ref: string, days?: number): string {
  const params = new URLSearchParams({ client: ref });
  if (days && days !== 30) params.set("days", String(days));
  return `/usage?${params.toString()}#gasto`;
}

const bagRef = (row: ClientUsage): BagRef => ({ ref: row.ref, name: row.name ?? row.ref, balance: row.bag, refillUpTo: row.refill_up_to });

/**
 * La tabla por cliente de Consumo (spec 047, requisitos 46.2 y 45.6): su bolsa
 * en su moneda, lo gastado este mes, los días al ritmo de 7 días, el relleno
 * mensual y sus acciones. Los que no tienen saldo salen con «Sin saldo» en rojo.
 * Todas las acciones van en «⋯» (regla de los tres puntos): «Asignar saldo» o
 * «Cambiar saldo», «Mover saldo a otro cliente» y «Ver su gasto» (y el relleno
 * y la moneda); en la columna no se repite ningún botón. Quien no puede asignar
 * ve «Pedir saldo» en el «⋯» y, si ya lo pidió, «Pedido hace…» junto al estado.
 * Se desplaza dentro de su caja.
 */
export function UsageClientsTable({ clients, canWrite, days }: { clients: ClientUsage[]; canWrite: boolean; days: number }) {
  const t = useT();
  const [open, setOpen] = React.useState<Open>(null);
  const close = () => setOpen(null);

  function actionsOf(row: ClientUsage): RowAction[] {
    const see: RowAction = { label: t("money.table.see"), href: spendHref(row.ref, days) };
    // Prototipo: el «⋯» termina siempre en «Abrir ficha del cliente».
    const record: RowAction = { label: t("proto.usage.openClient"), href: clientHref(row.ref) };
    if (!canWrite) return [{ label: t("money.request.cta"), onSelect: () => setOpen({ kind: "request", row }), primary: true }, see, record];
    const out: RowAction[] = [
      row.empty
        ? { label: t("money.assign.cta"), onSelect: () => setOpen({ kind: "assign", row }), primary: true }
        : { label: t("money.table.change"), onSelect: () => setOpen({ kind: "change", row }), primary: true },
    ];
    if (row.bag && row.bag.amount_micros > 0 && clients.length > 1) out.push({ label: t("money.table.move"), onSelect: () => setOpen({ kind: "move", row }) });
    out.push(see);
    out.push({ label: t("money.table.refill"), onSelect: () => setOpen({ kind: "refill", row }) });
    if (row.bag) out.push({ label: t("money.table.currency"), onSelect: () => setOpen({ kind: "currency", row }) });
    out.push(record);
    return out;
  }

  const all = clients.map(actionsOf);
  const menu = foldsIntoMenu(all.reduce((n, a) => n + a.length, 0));

  if (clients.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t("money.table.empty")}</p>;
  }

  return (
    <>
      <div className="relative min-w-0 overflow-x-auto rounded-lg ring-1 ring-foreground/10" role="region" aria-label={t("money.table.title")} tabIndex={0} data-slot="usage-clients">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <caption className="sr-only">{t("money.table.title")}</caption>
          <thead className="text-sm text-muted-foreground">
            <tr>
              <th scope="col" className="px-4 py-3 font-normal">{t("money.table.client")}</th>
              <th scope="col" className="px-4 py-3 text-right font-normal">{t("money.table.bag")}</th>
              <th scope="col" className="px-4 py-3 text-right font-normal">{t("money.table.spent")}</th>
              <th scope="col" className="px-4 py-3 font-normal">{t("money.table.days")}</th>
              <th scope="col" className="px-4 py-3 font-normal">{t("money.table.refill")}</th>
              <th scope="col" className="w-12 px-4 py-3 font-normal">
                <span className="sr-only">{t("money.table.actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {clients.map((row, i) => {
              const name = row.name ?? row.ref;
              return (
                <tr key={row.ref} className="border-t border-border align-middle transition-colors hover:bg-muted/50" data-client={row.ref}>
                  <td className="max-w-64 px-4 py-4">
                    <Link href={clientHref(row.ref)} className="block min-w-0 truncate font-medium underline-offset-4 hover:underline" title={name}>
                      {name}
                    </Link>
                    {/* La moneda de su bolsa, bajo el nombre (prototipo). */}
                    {row.bag ? <span className="block text-xs text-muted-foreground">{row.bag.currency}</span> : null}
                  </td>
                  <td className="px-4 py-4 text-right">
                    {row.empty ? (
                      <span className="inline-flex flex-wrap items-center justify-end gap-2">
                        <StatusBadge tone="danger">{t("money.table.noBalance")}</StatusBadge>
                        {canWrite ? null : <RequestedNote refId={row.ref} />}
                      </span>
                    ) : (
                      <span className="whitespace-nowrap tabular-nums">{moneyText(row.bag, "down")}</span>
                    )}
                  </td>
                  <td className="px-4 py-4 text-right whitespace-nowrap tabular-nums">{moneyText(row.month_spent)}</td>
                  <td className="px-4 py-4 text-muted-foreground">{row.empty ? "—" : daysText(t, row.days_left)}</td>
                  <td className="px-4 py-4 text-muted-foreground">
                    {row.refill_up_to ? t("money.table.refillUpTo", { amount: moneyText(row.refill_up_to) }) : "—"}
                  </td>
                  <td className="px-4 py-4 text-right">
                    <RowActions actions={all[i]!} menu={menu} ariaLabel={t("money.table.actions.aria", { name })} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {open && (open.kind === "assign" || open.kind === "change" || open.kind === "request") ? (
        <BalanceDialogs
          refId={open.row.ref}
          name={open.row.name ?? open.row.ref}
          open={open.kind === "request" ? "request" : "assign"}
          change={open.kind === "change"}
          onClose={close}
        />
      ) : null}
      {open?.kind === "move" ? <MoveDialog from={bagRef(open.row)} onOpenChange={(o) => !o && close()} /> : null}
      {open?.kind === "refill" ? (
        <RefillDialog bag={bagRef(open.row)} currency={open.row.bag?.currency ?? open.row.month_spent.currency} onOpenChange={(o) => !o && close()} />
      ) : null}
      {open?.kind === "currency" && open.row.bag ? <CurrencyDialog bag={bagRef(open.row)} current={open.row.bag.currency} onOpenChange={(o) => !o && close()} /> : null}
    </>
  );
}

/** «Pedido hace…» junto a «Sin saldo» si ya se pidió; pedir va en el «⋯». */
function RequestedNote({ refId }: { refId: string }) {
  const t = useT();
  const at = useRequested(refId);
  if (at === undefined) return null;
  return <span className="text-xs text-muted-foreground">{requestedText(t, at)}</span>;
}
