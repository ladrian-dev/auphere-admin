"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, Input, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import { moveAllocationAction } from "./actions";
import { actionErrorText } from "@/lib/action-error";

type Row = { ref: string; name: string; cap: number };

/**
 * Spec 016 (R3.1–R3.4): one confirmation, one call, one result. The API
 * moves the quota in a single transaction; the dialog says exactly what is
 * about to happen and the toast says exactly what happened.
 */
export function MoveAllocationForm({ sources, destinations }: { sources: Row[]; destinations: Row[] }) {
  const t = useT();
  const locale = useLocale();
  const [fromRef, setFromRef] = React.useState(sources[0]?.ref ?? "");
  const [toRef, setToRef] = React.useState(destinations.find((d) => d.ref !== sources[0]?.ref)?.ref ?? "");
  const [value, setValue] = React.useState("");
  const [confirm, setConfirm] = React.useState<{ qty: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  if (sources.length === 0 || destinations.length < 2) return null;

  const from = sources.find((r) => r.ref === fromRef);
  const to = destinations.find((r) => r.ref === toRef);
  const n = (v: number) => formatNumber(v, locale);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = Number(value);
    if (!from || !to || from.ref === to.ref) {
      toast.error(t("hu.usage.allocations.move.pick"));
      return;
    }
    if (!Number.isInteger(parsed) || parsed <= 0) {
      toast.error(t("hu.usage.allocations.move.invalid"));
      return;
    }
    if (parsed > from.cap) {
      toast.error(t("hu.usage.allocations.move.insufficient_cap", { from: from.name, cap: n(from.cap) }));
      return;
    }
    setError(null);
    setConfirm({ qty: parsed });
  }

  function move() {
    if (!from || !to || !confirm) return;
    const { qty } = confirm;
    start(async () => {
      const res = await moveAllocationAction({ from_ref: from.ref, to_ref: to.ref, qty });
      if (!res.ok) {
        if (res.code === "same_client") return void setError(t("hu.usage.allocations.move.same_client"));
        if (res.code === "insufficient_cap") {
          const cap = typeof res.info?.cap === "number" ? n(res.info.cap) : n(from.cap);
          return void setError(t("hu.usage.allocations.move.insufficient_cap", { from: from.name, cap }));
        }
        return void setError(actionErrorText(res, t));
      }
      setConfirm(null);
      setValue("");
      toast.success(t("hu.usage.allocations.move.done", { qty: n(qty), from: from.name, to: to.name }));
    });
  }

  const selectClass =
    "h-8 max-w-56 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

  return (
    <>
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
        <select
          className={selectClass}
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
        </select>
        <select
          className={selectClass}
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
        </select>
        <Input
          aria-label={t("hu.usage.allocations.move.qty")}
          inputMode="numeric"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={pending}
          className="h-8 w-32 text-right tabular-nums"
        />
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
          from && to && confirm ? t("hu.usage.allocations.move.confirm", { qty: n(confirm.qty), from: from.name, to: to.name }) : null
        }
        confirmLabel={t("hu.usage.allocations.move")}
        onConfirm={move}
        error={error}
      />
    </>
  );
}
