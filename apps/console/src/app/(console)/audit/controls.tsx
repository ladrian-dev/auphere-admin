"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

export function AuditControls({ actor, action, nextCursor }: { actor: string; action: string; nextCursor: string | null }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [a, setA] = React.useState(actor);
  const [act, setAct] = React.useState(action);
  function set(patch: Record<string, string | undefined>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    router.push(`${pathname}?${next.toString()}`);
  }
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        set({ actor: a || undefined, action: act || undefined, cursor: undefined });
      }}
    >
      <Input value={a} onChange={(e) => setA(e.target.value)} placeholder={t("audit.filter.actor")} aria-label={t("audit.filter.actor")} className="w-56" />
      <Input value={act} onChange={(e) => setAct(e.target.value)} placeholder={t("audit.filter.action")} aria-label={t("audit.filter.action")} className="w-56 font-mono" />
      <Button type="submit" variant="outline" size="sm">
        OK
      </Button>
      {nextCursor ? (
        <Button type="button" variant="ghost" size="sm" className="ml-auto" onClick={() => set({ cursor: nextCursor })}>
          {t("audit.more")}
        </Button>
      ) : null}
    </form>
  );
}
