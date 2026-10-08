import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { backend, BackendError } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

import { AccessForm } from "./access-form";
import { InviteForm } from "./invite-form";
import { MembersList } from "./members-list";

/**
 * Spec 030 — «Acceso»: the client's own console (consola lite).
 *
 * The Auphere team switches it on, chooses the modules for the whole client
 * (Panel, Bandeja de entrada, Consumo) and invites or revokes its people.
 * Every change is audited with the operator of this session.
 */
export default async function AccessPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const operator = await requireOperator();
  const tenant = await backend.getTenant(id);
  if (!tenant) notFound();

  let access;
  try {
    access = await backend.getClientAccess(id, operator.id);
  } catch (err) {
    const status = err instanceof BackendError ? err.status : 500;
    return (
      <Card>
        <CardHeader>
          <CardTitle>No se pudo leer el acceso</CardTitle>
          <CardDescription>La API respondió {status}. Recarga la página para intentarlo de nuevo.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  if (!access) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Consola lite</Eyebrow>
          <CardTitle>Acceso del cliente</CardTitle>
          <CardDescription>
            {access.partner
              ? `Las personas de ${tenant.name} entran en la consola de Auphere y ven solo lo suyo. Cliente de ${access.partner.name}.`
              : `Las personas de ${tenant.name} entran en la consola de Auphere y ven solo lo suyo.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AccessForm tenantId={id} access={access} />
        </CardContent>
      </Card>
      {access.eligible ? (
        <Card>
          <CardHeader>
            <CardTitle>Personas</CardTitle>
            <CardDescription>
              Cada persona recibe un enlace de un solo uso que caduca en 21 días. Revocar cierra sus sesiones.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6">
            <InviteForm tenantId={id} disabled={!access.enabled} />
            <MembersList tenantId={id} members={access.members} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
