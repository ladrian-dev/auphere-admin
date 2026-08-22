"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { addPurchasedAction } from "./actions";

export function RechargePurchasedForm() {
  const t = useT();
  const [value, setValue] = React.useState("");
  const [pending, start] = React.useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      toast.error(t("hu.usage.wallet.recharge.invalid"));
      return;
    }
    start(async () => {
      const res = await addPurchasedAction({ qty: parsed });
      if (!res.ok) {
        if (res.status === 404) return void toast.error(t("common.forbidden"));
        if (res.status === 409 || res.status === 422) return void toast.error(t("hu.usage.wallet.recharge.invalid"));
        return void toast.error(res.status === 403 ? t("common.forbidden") : res.message);
      }
      setValue("");
      toast.success(t("hu.usage.wallet.recharge.saved"));
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <Input
        aria-label={t("hu.usage.wallet.recharge.qty")}
        inputMode="numeric"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={pending}
        className="h-8 w-32 text-right tabular-nums"
      />
      <Button type="submit" size="sm" disabled={pending}>
        {t("hu.usage.wallet.recharge")}
      </Button>
      <span className="text-xs text-muted-foreground">{t("hu.usage.wallet.tokens")}</span>
    </form>
  );
}
