"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Meter,
  NativeSelect,
  StatusBadge,
} from "@nexus/ui";

import { creditTone } from "@/components/clients/credit-tone";
import { RowActions } from "@/components/row-actions";
import { useLocale, useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import { formatMoney, moneyInputValue, parseMoney } from "@/lib/money";

import { moveAllocationAction, saveAllocationAction } from "./actions";

export type BalanceRow = { ref: string; name: string; capCents: number; remainingCents: number; monthCents: number };
type Client = { ref: string; name: string };
type Open = { kind: "cap"; row: BalanceRow } | { kind: "move"; row: BalanceRow } | { kind: "assign" } | null;

/**
 * «Saldo por cliente» (spec 028): no field to edit in the table. Each row
 * says the cap, what was spent this month and what is left; changing the
 * cap or moving balance happens in a dialog opened from «⋯» (owner's
 * three-dot rule), assigning to a client without a cap from one button.
 */
export function BalanceTable({ rows, unassigned, everyone, canWrite, exhausted }: { rows: BalanceRow[]; unassigned: Client[]; everyone: Client[]; canWrite: boolean; exhausted: boolean }) {
  const t = useT();
  const locale = useLocale();
  const money = (c: number) => formatMoney(c, locale);
  const [open, setOpen] = React.useState<Open>(null);
  const close = () => setOpen(null);

  return (
    <div className="flex flex-col">
      {canWrite && unassigned.length > 0 ? (
        <div className="flex justify-end px-4 pb-2">
          <Button size="sm" variant="outline" onClick={() => setOpen({ kind: "assign" })}>
            {t("hu.usage.balance.assign")}
          </Button>
        </div>
      ) : null}
      {rows.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-muted-foreground">{t("hu.usage.allocations.empty")}</p>
      ) : (
        <div className="min-w-0 overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">{t("hu.usage.balance.title")}</caption>
            <thead>
              <tr className="border-y text-left text-xs text-muted-foreground">
                <th className="h-9 px-4 font-medium">{t("usage.client")}</th>
                <th className="h-9 px-2 text-right font-medium">{t("hu.usage.allocations.cap")}</th>
                <th className="h-9 px-2 text-right font-medium">{t("hu.usage.balance.spent")}</th>
                <th className="h-9 w-1/3 px-2 font-medium">{t("hu.usage.allocations.remaining")}</th>
                <th className="h-9 w-10 px-2">
                  <span className="sr-only">{t("common.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const out = row.remainingCents <= 0 || exhausted;
                return (
                  <tr key={row.ref} id={`allocation-${row.ref}`} className="border-b last:border-0">
                    <td className="max-w-56 truncate px-4 py-2">
                      <Link href={`/clients/${encodeURIComponent(row.ref)}`} className="font-medium hover:underline" title={row.name}>
                        {row.name}
                      </Link>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">{money(row.capCents)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{money(row.monthCents)}</td>
                    <td className="px-2 py-2">
                      {out ? (
                        <StatusBadge tone="danger">{t("hu.usage.allocations.outOfQuota")}</StatusBadge>
                      ) : (
                        <Meter
                          size="sm"
                          label={t("hu.usage.allocations.remaining")}
                          labelHidden
                          value={row.remainingCents}
                          max={row.capCents}
                          tone={creditTone({ cap_cents: row.capCents, remaining_cents: row.remainingCents })}
                          valueLabel={money(row.remainingCents)}
                        />
                      )}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <RowActions
                        menu
                        ariaLabel={t("hu.home.actions.aria", { who: row.name })}
                        actions={[
                          ...(canWrite
                            ? [
                                { label: t("hu.usage.balance.action.cap"), onSelect: () => setOpen({ kind: "cap", row }), primary: true },
                                ...(everyone.length > 1 && row.capCents > 0 ? [{ label: t("hu.usage.balance.action.move"), onSelect: () => setOpen({ kind: "move", row }) }] : []),
                              ]
                            : []),
                          { label: t("hu.usage.balance.action.usage"), href: `/usage?client=${encodeURIComponent(row.ref)}#gasto` },
                          { label: t("hu.home.actions.client"), href: `/clients/${encodeURIComponent(row.ref)}` },
                        ]}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {open?.kind === "cap" ? <CapDialog row={open.row} onClose={close} /> : null}
      {open?.kind === "move" ? <MoveDialog row={open.row} destinations={everyone.filter((c) => c.ref !== open.row.ref)} onClose={close} /> : null}
      {open?.kind === "assign" ? <AssignDialog clients={unassigned} onClose={close} /> : null}
    </div>
  );
}

function AmountField({ id, label, value, onChange, hint }: { id: string; label: string; value: string; onChange: (v: string) => void; hint?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <span className="flex items-center gap-2">
        <Input id={id} inputMode="decimal" autoFocus value={value} onChange={(e) => onChange(e.target.value)} className="w-36 text-right tabular-nums" />
        <span aria-hidden="true" className="text-sm text-muted-foreground">
          US$
        </span>
      </span>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function CapDialog({ row, onClose }: { row: BalanceRow; onClose: () => void }) {
  const t = useT();
  const locale = useLocale();
  const [value, setValue] = React.useState(moneyInputValue(row.capCents, locale));
  const [error, setError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  function save(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseMoney(value);
    if (parsed.kind !== "money") return void setError(t("hu.usage.allocations.invalidCap"));
    start(async () => {
      const res = await saveAllocationAction({ client_ref: row.ref, cap_cents: parsed.cents });
      if (!res.ok) return void setError(res.status === 409 ? t("hu.usage.allocations.over") : actionErrorText(res, t));
      toast.success(t("hu.usage.allocations.saved"));
      onClose();
    });
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={save} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t("hu.usage.balance.cap.title", { client: row.name })}</DialogTitle>
            <DialogDescription>{t("hu.usage.balance.cap.body")}</DialogDescription>
          </DialogHeader>
          <AmountField id="cap-amount" label={t("hu.usage.balance.amount")} value={value} onChange={(v) => (setValue(v), setError(null))} />
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={pending} aria-busy={pending}>
              {t("hu.usage.allocations.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MoveDialog({ row, destinations, onClose }: { row: BalanceRow; destinations: Client[]; onClose: () => void }) {
  const t = useT();
  const locale = useLocale();
  const money = (c: number) => formatMoney(c, locale);
  const [to, setTo] = React.useState(destinations[0]?.ref ?? "");
  const [value, setValue] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  function move(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseMoney(value);
    if (!to) return void setError(t("hu.usage.allocations.move.pick"));
    if (parsed.kind !== "money" || parsed.cents <= 0) return void setError(t("hu.usage.allocations.move.invalid"));
    if (parsed.cents > row.capCents) return void setError(t("hu.usage.allocations.move.insufficient_cap", { from: row.name, cap: money(row.capCents) }));
    const target = destinations.find((d) => d.ref === to);
    start(async () => {
      const res = await moveAllocationAction({ from_ref: row.ref, to_ref: to, amount_cents: parsed.cents });
      if (!res.ok) {
        if (res.code === "insufficient_cap") return void setError(t("hu.usage.allocations.move.insufficient_cap", { from: row.name, cap: money(typeof res.info?.cap_cents === "number" ? res.info.cap_cents : row.capCents) }));
        if (res.code === "same_client") return void setError(t("hu.usage.allocations.move.same_client"));
        return void setError(actionErrorText(res, t));
      }
      toast.success(t("hu.usage.allocations.move.done", { amount: money(parsed.cents), from: row.name, to: target?.name ?? to }));
      onClose();
    });
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={move} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t("hu.usage.balance.move.title", { client: row.name })}</DialogTitle>
            <DialogDescription>{t("hu.usage.allocations.move.hint")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1">
            <Label htmlFor="move-to">{t("hu.usage.allocations.move.to")}</Label>
            <NativeSelect id="move-to" value={to} onChange={(e) => (setTo(e.target.value), setError(null))}>
              {destinations.map((c) => (
                <option key={c.ref} value={c.ref}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          <AmountField id="move-amount" label={t("hu.usage.allocations.move.qty")} value={value} onChange={(v) => (setValue(v), setError(null))} hint={t("hu.usage.balance.move.max", { cap: money(row.capCents) })} />
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={pending} aria-busy={pending}>
              {t("hu.usage.allocations.move")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AssignDialog({ clients, onClose }: { clients: Client[]; onClose: () => void }) {
  const t = useT();
  const [ref, setRef] = React.useState(clients[0]?.ref ?? "");
  const [value, setValue] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  function assign(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseMoney(value);
    if (!ref) return void setError(t("hu.usage.allocations.assign.pick"));
    if (parsed.kind !== "money") return void setError(t("hu.usage.allocations.invalidCap"));
    start(async () => {
      const res = await saveAllocationAction({ client_ref: ref, cap_cents: parsed.cents });
      if (!res.ok) return void setError(res.status === 409 ? t("hu.usage.allocations.over") : actionErrorText(res, t));
      toast.success(t("hu.usage.allocations.saved"));
      onClose();
    });
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={assign} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t("hu.usage.balance.assign")}</DialogTitle>
            <DialogDescription>{t("hu.usage.balance.cap.body")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1">
            <Label htmlFor="assign-client">{t("hu.usage.allocations.assign.client")}</Label>
            <NativeSelect id="assign-client" value={ref} onChange={(e) => (setRef(e.target.value), setError(null))}>
              {clients.map((c) => (
                <option key={c.ref} value={c.ref}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          <AmountField id="assign-amount" label={t("hu.usage.balance.amount")} value={value} onChange={(v) => (setValue(v), setError(null))} />
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={pending} aria-busy={pending}>
              {t("hu.usage.allocations.assign")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
