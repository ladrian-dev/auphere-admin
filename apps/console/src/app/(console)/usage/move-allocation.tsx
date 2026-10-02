"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, Input, NativeSelect } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import { moveAllocationAction } from "./actions";
import { actionErrorText } from "@/lib/action-error";
import { formatMoney, parseMoney } from "@/lib/money";

/** Spec 027: caps in cents of USD. */
type Row = { ref: string; name: string; capCents: number };

/**
 * Spec 016 (R3.1–R3.4): one confirmation, one call, one result. The API
 * moves the quota in a single transaction; the dialog says exactly what is
 * about to happen and the toast says exactly what happened.
 */
export function MoveAllocationForm({ sources, destinations }: { sources: Row[]; destinations: Row[] }) {
  const t = useT();
  const locale = useLocale();
  // El origen por defecto es el primero **que tenga algo que dar**. Desde
  // que un cliente nace con cero crédito (spec 019), «el primero de la
  // lista» es casi siempre uno vacío, y el primer clic del partner era
  // siempre un error: «no tiene crédito suficiente».
  const primerOrigen = sources.find((r) => r.capCents > 0) ?? sources[0];
  const [fromRef, setFromRef] = React.useState(primerOrigen?.ref ?? "");
  const [toRef, setToRef] = React.useState(destinations.find((d) => d.ref !== primerOrigen?.ref)?.ref ?? "");
  const [value, setValue] = React.useState("");
  const [confirm, setConfirm] = React.useState<{ cents: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  if (sources.length === 0 || destinations.length < 2) return null;

  const from = sources.find((r) => r.ref === fromRef);
  const to = destinations.find((r) => r.ref === toRef);
  const money = (cents: number) => formatMoney(cents, locale);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseMoney(value);
    if (!from || !to || from.ref === to.ref) {
      toast.error(t("hu.usage.allocations.move.pick"));
      return;
    }
    if (parsed.kind !== "money" || parsed.cents <= 0) {
      toast.error(t("hu.usage.allocations.move.invalid"));
      return;
    }
    if (parsed.cents > from.capCents) {
      toast.error(t("hu.usage.allocations.move.insufficient_cap", { from: from.name, cap: money(from.capCents) }));
      return;
    }
    setError(null);
    setConfirm({ cents: parsed.cents });
  }

  function move() {
    if (!from || !to || !confirm) return;
    const { cents } = confirm;
    start(async () => {
      const res = await moveAllocationAction({ from_ref: from.ref, to_ref: to.ref, amount_cents: cents });
      if (!res.ok) {
        if (res.code === "same_client") return void setError(t("hu.usage.allocations.move.same_client"));
        if (res.code === "insufficient_cap") {
          const cap = typeof res.info?.cap_cents === "number" ? money(res.info.cap_cents) : money(from.capCents);
          return void setError(t("hu.usage.allocations.move.insufficient_cap", { from: from.name, cap }));
        }
        return void setError(actionErrorText(res, t));
      }
      setConfirm(null);
      setValue("");
      toast.success(t("hu.usage.allocations.move.done", { amount: money(cents), from: from.name, to: to.name }));
    });
  }

  return (
    <>
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
        <NativeSelect
          wrapperClassName="max-w-56"
          value={fromRef}
          onChange={(e) => setFromRef(e.target.value)}
          disabled={pending}
          aria-label={t("hu.usage.allocations.move.from")}
        >
          {sources.map((c) => (
            <option key={c.ref} value={c.ref}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          wrapperClassName="max-w-56"
          value={toRef}
          onChange={(e) => setToRef(e.target.value)}
          disabled={pending}
          aria-label={t("hu.usage.allocations.move.to")}
        >
          {destinations
            .filter((c) => c.ref !== fromRef)
            .map((c) => (
              <option key={c.ref} value={c.ref}>
                {c.name}
              </option>
            ))}
        </NativeSelect>
        <span className="flex items-center gap-1">
          <Input
            aria-label={t("hu.usage.allocations.move.qty")}
            inputMode="decimal"
            placeholder="10,00"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={pending}
            className="h-8 w-28 text-right tabular-nums"
          />
          <span aria-hidden="true" className="text-xs text-muted-foreground">
            US$
          </span>
        </span>
        <Button type="submit" size="sm" disabled={pending}>
          {t("hu.usage.allocations.move")}
        </Button>
      </form>
      <ConfirmDialog
        open={confirm != null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirm(null);
            setError(null);
          }
        }}
        title={t("hu.usage.allocations.move")}
        description={
          from && to && confirm ? t("hu.usage.allocations.move.confirm", { amount: money(confirm.cents), from: from.name, to: to.name }) : null
        }
        confirmLabel={t("hu.usage.allocations.move")}
        onConfirm={move}
        error={error}
      />
    </>
  );
}
