"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@nexus/ui";

import type { SignupLink } from "@/lib/backend";
import { fullDateTime } from "@/lib/format";

import { revokeSignupLinkAction } from "./actions";

/** Spec 040: links sent to the owner and not used yet — each can be cancelled. */
export function PendingLinks({ tenantId, links }: { tenantId: string; links: SignupLink[] }) {
  const [pending, start] = useTransition();
  if (links.length === 0) return null;
  return (
    <section aria-label="Enlaces enviados" className="flex flex-col gap-2 rounded-md p-4 ring-1 ring-foreground/10">
      <h2 className="text-sm font-medium">Enlaces enviados al dueño, sin usar</h2>
      <ul className="flex flex-col divide-y divide-border">
        {links.map((l) => (
          <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
            <span className="text-muted-foreground">
              {l.mode === "coexistence" ? "Coexistencia" : "Cloud API"} · lo envió {l.created_by.replace(/^(operator|console):/, "")} ·
              caduca el {fullDateTime(l.expires_at)}
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={pending}
              onClick={() =>
                start(async () => {
                  const r = await revokeSignupLinkAction(tenantId, l.id);
                  if (r.ok) toast.success("Enlace anulado.");
                  else toast.error("No se pudo anular", { description: r.error });
                })
              }
            >
              Anular
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
