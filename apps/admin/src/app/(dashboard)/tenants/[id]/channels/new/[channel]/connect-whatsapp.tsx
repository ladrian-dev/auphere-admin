"use client";

import { useRouter } from "next/navigation";

import { MetaConnectOwnedDialog } from "../../../_integrations/meta-connect-owned-dialog";
import { MetaWhatsAppSetupDialog } from "../../../_integrations/meta-signup-dialog";
import { SignupLinkDialog } from "../../../_integrations/signup-link-dialog";

/**
 * Spec 035: WhatsApp's provider choice, like Chatwoot's (Cloud vs Twilio) —
 * here the two ways Auphere connects a number. Each one opens the flow that
 * already exists; when it connects, the wizard moves on.
 */
export function ConnectWhatsApp({
  tenantId,
  businessName,
  hasLiveLink = false,
}: {
  tenantId: string;
  businessName: string;
  hasLiveLink?: boolean;
}) {
  const router = useRouter();
  const next = () => router.push(`/tenants/${tenantId}/channels/new/whatsapp/agent`);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Spec 040: the usual path — the owner does it on their own device. */}
      <div className="flex flex-col gap-3 rounded-md p-6 ring-1 ring-primary/40 md:col-span-2">
        <h3 className="text-base font-medium">Enviar un enlace al dueño del negocio</h3>
        <p className="text-sm text-pretty text-muted-foreground">
          Lo abre en su teléfono o su computadora, donde ya tiene su cuenta de Meta, y conecta él mismo su número. Es
          lo más seguro y lo único que funciona bien para la coexistencia con la app WhatsApp Business. El número
          aparece en Canales cuando termina.
        </p>
        <div className="mt-auto">
          <SignupLinkDialog tenantId={tenantId} businessName={businessName} hasLiveLink={hasLiveLink} />
        </div>
      </div>
      <div className="flex flex-col gap-3 rounded-md p-6 ring-1 ring-foreground/10">
        <h3 className="text-base font-medium">Registro integrado de Meta, desde aquí</h3>
        <p className="text-sm text-pretty text-muted-foreground">
          El dueño del negocio inicia sesión con Meta y elige su número: API de Cloud o coexistencia con la app de
          WhatsApp Business. Es el camino normal.
        </p>
        <div className="mt-auto">
          <MetaWhatsAppSetupDialog tenantId={tenantId} alreadyConnected={false} onConnected={next} />
        </div>
      </div>
      <div className="flex flex-col gap-3 rounded-md p-6 ring-1 ring-foreground/10">
        <h3 className="text-base font-medium">Número propio con usuario del sistema</h3>
        <p className="text-sm text-pretty text-muted-foreground">
          Para números del negocio de Auphere o de un partner, conectados con un token de usuario del sistema y los
          identificadores de la cuenta de WhatsApp Business.
        </p>
        <div className="mt-auto">
          <MetaConnectOwnedDialog tenantId={tenantId} onConnected={next} />
        </div>
      </div>
    </div>
  );
}
