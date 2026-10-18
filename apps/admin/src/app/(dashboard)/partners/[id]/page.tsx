import { notFound } from "next/navigation";

import { DescriptionList, Section } from "@nexus/ui";

import { backend } from "@/lib/backend";
import { fullDateTime } from "@/lib/format";

import { ProfileForm } from "./profile-form";

/**
 * Spec 031 (R4.3, R4.4): the partner's summary — who they are, how to reach
 * them, and what their console has switched on. Keys, limits and models
 * live in Configuración.
 */
export default async function PartnerSummaryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const partner = await backend.getPartner(id);
  if (!partner) notFound();
  const yes = (v: boolean) => (v ? "Sí" : "No");
  return (
    <div className="grid gap-6">
      <Section title="Datos del partner" description="Cómo se llama y a dónde le escribimos. El correo de facturación recibe los recibos mensuales.">
        <ProfileForm
          partnerId={partner.id}
          initial={{ name: partner.name, contact_email: partner.contact_email, billing_email: partner.billing_email }}
        />
      </Section>
      <Section title="Consola" description="Lo que el partner tiene encendido en su consola.">
        <DescriptionList
          layout="stacked"
          columns={3}
          items={[
            { key: "console", term: "Consola", detail: partner.console_enabled ? "Encendida" : "Apagada" },
            { key: "companion", term: "Companion", detail: yes(partner.companion_enabled) },
            { key: "activated", term: "Activado", detail: fullDateTime(partner.activated_at) },
            { key: "max_clients", term: "Clientes máximos", detail: partner.max_clients ?? "—" },
            { key: "max_channels", term: "Canales por cliente", detail: partner.max_channels_per_client ?? "—" },
            { key: "updated", term: "Última modificación", detail: fullDateTime(partner.updated_at) },
          ]}
        />
      </Section>
    </div>
  );
}
