"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { saveAllocationAction } from "./actions";

export function AllocationCapForm({ clientRef, cap }: { clientRef: string; cap: number }) {
  const t = useT();
  const [value, setValue] = React.useState(String(cap));
  const [pending, start] = React.useTransition();

  React.useEffect(() => {
    setValue(String(cap));
  }, [cap]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 0) {
      toast.error(t("hu.usage.allocations.invalidCap"));
      return;
    }
    start(async () => {
      const res = await saveAllocationAction({ client_ref: clientRef, cap: parsed });
      if (!res.ok) {
        if (res.status === 409) return void toast.error(t("hu.usage.allocations.over"));
        return void toast.error(res.status === 403 ? t("common.forbidden") : res.message);
      }
      toast.success(t("hu.usage.allocations.saved"));
    });
  }

  return (
    <form onSubmit={submit} className="flex items-center justify-end gap-2">
      <Input
        aria-label={t("hu.usage.allocations.cap")}
        inputMode="numeric"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={pending}
        className="h-8 w-32 text-right tabular-nums"
      />
      <Button type="submit" size="sm" disabled={pending}>
        {t("hu.usage.allocations.save")}
      </Button>
    </form>
  );
}
