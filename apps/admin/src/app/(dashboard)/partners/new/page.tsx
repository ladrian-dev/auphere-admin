import { PageHeader } from "@nexus/ui";

import { NewPartnerForm } from "./new-partner-form";

export const metadata = { title: "Nuevo partner" };

// Spec 052: crear espera al proveedor de correo, hasta 25 s si no responde. La
// función no puede morir antes o el operador se queda sin el resultado y sin el
// enlace, con el partner ya creado.
export const maxDuration = 60;

export default function NewPartnerPage() {
  return (
    <>
      <PageHeader
        title="Nuevo partner"
        description="Quién es y quién va a ser su propietario. Lo demás se gestiona en su ficha, después del alta."
      />
      <div className="rounded-md border border-border bg-card p-6 max-w-3xl">
        <NewPartnerForm />
      </div>
    </>
  );
}
