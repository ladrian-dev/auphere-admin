"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
  StatusBadge,
  Textarea,
} from "@nexus/ui";

import type { OptOut } from "@/lib/backend";

import { liftOptOutAction } from "./actions";

const SOURCE: Record<string, string> = {
  meta: "Desde WhatsApp (Meta)",
  keyword: "Escribió una palabra de baja",
  operator: "La puso Auphere",
};

const LIFT_ERROR: Record<string, string> = {
  lifted_by_person_only: "Esta baja la dio la persona en WhatsApp: solo ella puede reactivarla desde WhatsApp.",
  already_lifted: "Esta baja ya estaba levantada.",
  opt_out_not_found: "La baja ya no existe.",
};

function when(iso: string) {
  return new Date(iso).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short" });
}

/**
 * Spec 050 (5.5): the business's WhatsApp opt-outs. A marketing one stops
 * broadcasts and marketing templates; the agent still answers. One written
 * by a stop word may be lifted with a reason; Meta's is the person's to lift.
 */
export function OptOuts({ tenantId, rows }: { tenantId: string; rows: OptOut[] }) {
  const [lifting, setLifting] = useState<OptOut | null>(null);
  const [reason, setReason] = useState("");
  const [pending, start] = useTransition();
  const active = rows.filter((r) => r.opted_in_at === null);

  return (
    <section aria-labelledby="opt-outs-title" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 id="opt-outs-title" className="text-base font-semibold">
          Bajas de WhatsApp
        </h2>
        <p className="text-sm text-muted-foreground">
          {active.length === 0
            ? "Nadie se ha dado de baja de los mensajes de este negocio."
            : `${active.length} ${active.length === 1 ? "persona no recibe" : "personas no reciben"} difusiones ni plantillas de marketing. El agente les sigue respondiendo.`}
        </p>
      </div>
      {rows.length > 0 ? (
        <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
          {rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3" data-opt-out={r.id}>
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-medium">{r.customer_name ?? r.phone ?? "Persona sin número"}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {SOURCE[r.source] ?? r.source} · {r.scope === "all" ? "De todo" : "De marketing"} · {when(r.opted_out_at)}
                  {r.channel_identifier ? ` · ${r.channel_identifier}` : ""}
                </span>
              </div>
              {r.opted_in_at ? (
                <StatusBadge tone="muted">Levantada</StatusBadge>
              ) : r.liftable ? (
                <Button variant="outline" size="sm" onClick={() => (setLifting(r), setReason(""))}>
                  Levantar
                </Button>
              ) : (
                <StatusBadge tone="info">Solo la persona</StatusBadge>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      <Dialog open={lifting !== null} onOpenChange={(open) => !open && setLifting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Levantar la baja de {lifting?.customer_name ?? lifting?.phone ?? "esta persona"}</DialogTitle>
            <DialogDescription>
              Volverá a recibir difusiones y plantillas de marketing de este negocio. Escribe por qué: queda en la auditoría.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="lift-reason">Motivo</Label>
            <Textarea id="lift-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setLifting(null)} disabled={pending}>
              Cancelar
            </Button>
            <Button
              size="sm"
              disabled={pending || reason.trim().length < 3}
              onClick={() =>
                start(async () => {
                  if (!lifting) return;
                  const res = await liftOptOutAction(tenantId, lifting.id, reason.trim());
                  if (!res.ok) return void toast.error(LIFT_ERROR[res.error] ?? `No se pudo levantar: ${res.error}`);
                  toast.success("Baja levantada.");
                  setLifting(null);
                })
              }
            >
              {pending ? "Levantando…" : "Levantar la baja"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
