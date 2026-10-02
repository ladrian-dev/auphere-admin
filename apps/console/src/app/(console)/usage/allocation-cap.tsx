"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Input } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import { moneyInputValue, parseMoney } from "@/lib/money";

import { saveAllocationAction } from "./actions";
import { actionErrorText } from "@/lib/action-error";

export function AllocationCapForm({ clientRef, capCents }: { clientRef: string; capCents: number }) {
  const t = useT();
  const locale = useLocale();
  const initial = moneyInputValue(capCents, locale);
  const [value, setValue] = React.useState(initial);
  // Owner's rule (three dots, 2026-10-02): a column of identical buttons is
  // noise. The save button shows only on the row whose cap was changed.
  const dirty = value.trim() !== initial;
  const [pending, start] = React.useTransition();


  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseMoney(value);
    if (parsed.kind === "empty") {
      toast.info(t("hu.usage.allocations.emptyCap"));
      return;
    }
    if (parsed.kind === "invalid") {
      toast.error(t("hu.usage.allocations.invalidCap"));
      return;
    }
    start(async () => {
      const res = await saveAllocationAction({ client_ref: clientRef, cap_cents: parsed.cents });
      if (!res.ok) {
        if (res.status === 409) return void toast.error(t("hu.usage.allocations.over"));
        return void toast.error(actionErrorText(res, t));
      }
      toast.success(t("hu.usage.allocations.saved"));
    });
  }

  return (
    <form onSubmit={submit} className="flex items-center justify-end gap-2">
      <span className="flex items-center gap-1">
        <Input
          aria-label={t("hu.usage.allocations.cap")}
          inputMode="decimal"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={pending}
          className="h-8 w-28 text-right tabular-nums"
        />
        <span aria-hidden="true" className="text-xs text-muted-foreground">
          US$
        </span>
      </span>
      {dirty ? (
        <Button type="submit" size="sm" disabled={pending}>
          {t("hu.usage.allocations.save")}
        </Button>
      ) : null}
    </form>
  );
}
