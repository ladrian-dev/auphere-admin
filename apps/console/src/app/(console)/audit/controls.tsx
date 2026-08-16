"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

type Props = { actor: string; action: string; after: string; before: string; nextCursor: string | null; csvHref: string };

export function AuditControls({ actor, action, after, before, nextCursor, csvHref }: Props) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [a, setA] = React.useState(actor);
  const [act, setAct] = React.useState(action);
  const [from, setFrom] = React.useState(after);
  const [to, setTo] = React.useState(before);
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
        set({ actor: a || undefined, action: act || undefined, after: from || undefined, before: to || undefined, cursor: undefined });
      }}
    >
      <Input value={a} onChange={(e) => setA(e.target.value)} placeholder={t("audit.filter.actor")} aria-label={t("audit.filter.actor")} className="w-56" />
      <Input value={act} onChange={(e) => setAct(e.target.value)} placeholder={t("audit.filter.action")} aria-label={t("audit.filter.action")} className="w-56 font-mono" />
      <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label={t("hu.audit.after")} className="w-40" />
      <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label={t("hu.audit.before")} className="w-40" />
      <Button type="submit" variant="outline" size="sm">
        OK
      </Button>
      <Button type="button" variant="ghost" size="sm" onClick={() => { setA(""); setAct(""); setFrom(""); setTo(""); set({ actor: undefined, action: undefined, after: undefined, before: undefined, cursor: undefined }); }}>
        {t("hu.audit.clear")}
      </Button>
      <Button nativeButton={false} variant="outline" size="sm" render={<a href={csvHref} download />}>
        {t("hu.audit.export")}
      </Button>
      {nextCursor ? (
        <Button type="button" variant="ghost" size="sm" className="ml-auto" onClick={() => set({ cursor: nextCursor })}>
          {t("audit.more")}
        </Button>
      ) : null}
    </form>
  );
}
