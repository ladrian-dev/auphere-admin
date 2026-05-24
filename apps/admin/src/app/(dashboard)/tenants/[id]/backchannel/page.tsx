import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";

import {
  deregisterOwnerAction,
  registerOwnerAction,
  updateOwnerAction,
} from "./actions";
import { OwnersTable } from "./owners-table";
import { RegisterOwnerForm } from "./register-form";

/**
 * Per-tenant backchannel tab (Bloque D Fase 2 / D7).
 *
 * Two stacked surfaces:
 *
 * 1. **Registered owners** — the phones Auphere recognises as "the
 *    owner of this tenant". Each one can carry an optional pin to a
 *    specific Auphere outbound channel (Auphere CL / AR / MX / etc).
 *    When unpinned, the resolver picks the provider's default channel
 *    — common for single-country tenants.
 *
 * 2. **Add new owner** — registration form with E.164 validation,
 *    optional label and optional channel pin. Cross-tenant phone
 *    collisions surface as 409 with a clear message.
 *
 * The global Auphere channel registry (`/auphere/channels`) lists the
 * available channels — operators can manage them separately.
 */
export default async function BackchannelPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [tenant, owners, channels] = await Promise.all([
    backend.getTenant(id),
    backend.listBackchannelOwners(id),
    backend.listAuphereChannels(false),
  ]);
  if (!tenant) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Backchannel HITL</Eyebrow>
          <CardTitle>Dueños registrados</CardTitle>
          <CardDescription>
            Estos números reciben las consultas que el agente eleva vía{" "}
            <code>operator.consult_owner</code>. La columna{" "}
            <strong>Canal Auphere</strong> determina desde qué número
            saliente Auphere les escribe; si no está fijado, el dispatcher
            usa el default del provider (recomendado para tenants
            mono-país).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <OwnersTable
            tenantId={tenant.id}
            owners={owners}
            channels={channels}
            updateAction={updateOwnerAction}
            deregisterAction={deregisterOwnerAction}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Nuevo dueño</Eyebrow>
          <CardTitle>Registrar número</CardTitle>
          <CardDescription>
            E.164 con prefijo internacional. Un número solo puede estar
            registrado en UN tenant a la vez — si necesitas moverlo,
            primero desregistralo en el otro.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RegisterOwnerForm
            tenantId={tenant.id}
            channels={channels}
            registerAction={registerOwnerAction}
          />
        </CardContent>
      </Card>
    </div>
  );
}
