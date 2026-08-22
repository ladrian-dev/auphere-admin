"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { moveAllocationAction } from "./actions";

type Row = { ref: string; name: string; cap: number };

export function MoveAllocationForm({ sources, destinations }: { sources: Row[]; destinations: Row[] }) {
  const t = useT();
  const [fromRef, setFromRef] = React.useState(sources[0]?.ref ?? "");
  const [toRef, setToRef] = React.useState(destinations.find((d) => d.ref !== sources[0]?.ref)?.ref ?? "");
  const [value, setValue] = React.useState("");
  const [pending, start] = React.useTransition();

  if (sources.length === 0 || destinations.length < 2) return null;

  const from = sources.find((r) => r.ref === fromRef);
  const to = destinations.find((r) => r.ref === toRef);

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
    start(async () => {
      const res = await moveAllocationAction({
        from_ref: from.ref,
        to_ref: to.ref,
        from_cap: from.cap,
        to_cap: to.cap,
        qty: parsed,
      });
      if (!res.ok) {
        if (res.status === 409) return void toast.error(t("hu.usage.allocations.over"));
        return void toast.error(res.status === 403 ? t("common.forbidden") : res.message);
      }
      setValue("");
      toast.success(t("hu.usage.allocations.move.saved"));
    });
  }

  const selectClass =
    "h-8 max-w-56 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

  return (
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
  );
}
