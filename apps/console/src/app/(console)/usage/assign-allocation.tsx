"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { saveAllocationAction } from "./actions";
import { parseCapInput } from "./parse-cap-input";

type Client = { ref: string; name: string };

export function AssignAllocationForm({ clients }: { clients: Client[] }) {
  const t = useT();
  const [clientRef, setClientRef] = React.useState(clients[0]?.ref ?? "");
  const [value, setValue] = React.useState("");
  const [pending, start] = React.useTransition();

  if (clients.length === 0) return null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!clientRef) {
      toast.error(t("hu.usage.allocations.assign.pick"));
      return;
    }
    const parsed = parseCapInput(value);
    if (parsed.kind === "empty") {
      toast.info(t("hu.usage.allocations.emptyCap"));
      return;
    }
    if (parsed.kind === "invalid") {
      toast.error(t("hu.usage.allocations.invalidCap"));
      return;
    }
    start(async () => {
      const res = await saveAllocationAction({ client_ref: clientRef, cap: parsed.n });
      if (!res.ok) {
        if (res.status === 409) return void toast.error(t("hu.usage.allocations.over"));
        return void toast.error(res.status === 403 ? t("common.forbidden") : res.message);
      }
      setValue("");
      toast.success(t("hu.usage.allocations.saved"));
    });
  }

  const selectClass =
    "h-8 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <select
        className={selectClass}
        value={clientRef}
        onChange={(e) => setClientRef(e.target.value)}
        disabled={pending}
        aria-label={t("hu.usage.allocations.assign.client")}
      >
        {clients.map((c) => (
          <option key={c.ref} value={c.ref}>
            {c.name}
          </option>
        ))}
      </select>
      <Input
        aria-label={t("hu.usage.allocations.cap")}
        inputMode="numeric"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={pending}
        className="h-8 w-32 text-right tabular-nums"
      />
      <Button type="submit" size="sm" disabled={pending}>
        {t("hu.usage.allocations.assign")}
      </Button>
    </form>
  );
}
