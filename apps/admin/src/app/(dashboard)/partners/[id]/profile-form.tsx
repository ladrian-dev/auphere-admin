"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, Input, Label } from "@nexus/ui";

import { updatePartnerAction } from "../actions";

type Profile = { name: string; contact_email: string | null; billing_email: string | null };

/**
 * Spec 031 (R4.4): name and the two e-mails, editable from the summary. Only
 * what changed is sent; the API audits before and after.
 */
export function ProfileForm({ partnerId, initial }: { partnerId: string; initial: Profile }) {
  const [name, setName] = useState(initial.name);
  const [contact, setContact] = useState(initial.contact_email ?? "");
  const [billing, setBilling] = useState(initial.billing_email ?? "");
  const [pending, start] = useTransition();

  const changes: Record<string, string> = {};
  if (name.trim() && name.trim() !== initial.name) changes.name = name.trim();
  if (contact.trim() && contact.trim() !== (initial.contact_email ?? "")) changes.contact_email = contact.trim();
  if (billing.trim() && billing.trim() !== (initial.billing_email ?? "")) changes.billing_email = billing.trim();
  const dirty = Object.keys(changes).length > 0;

  return (
    <form
      className="grid gap-4 sm:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!dirty) return;
        start(async () => {
          const r = await updatePartnerAction(partnerId, changes);
          if (r.ok) toast.success("Datos del partner guardados");
          else toast.error("No se pudieron guardar", { description: r.error });
        });
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="p-name">Nombre</Label>
        <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={255} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="p-contact">Correo de contacto</Label>
        <Input id="p-contact" type="email" value={contact} onChange={(e) => setContact(e.target.value)} placeholder="nombre@partner.com" />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="p-billing">Correo de facturación</Label>
        <Input id="p-billing" type="email" value={billing} onChange={(e) => setBilling(e.target.value)} placeholder="facturas@partner.com" />
      </div>
      <div className="sm:col-span-3">
        <Button type="submit" disabled={!dirty || pending}>
          {pending ? "Guardando…" : "Guardar cambios"}
        </Button>
      </div>
    </form>
  );
}
