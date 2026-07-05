import { PageHeader } from "@/components/brand/page-header";

import { NewPartnerForm } from "./new-partner-form";

export const metadata = { title: "Nuevo partner" };

export default function NewPartnerPage() {
  return (
    <>
      <PageHeader
        eyebrow="Partners"
        title="Nuevo partner"
        description="Identidad básica del partner. Las API keys, origins y mapeos de tenants se gestionan en el detalle después del alta."
      />
      <div className="rounded-md border border-border bg-card p-6 max-w-3xl">
        <NewPartnerForm />
      </div>
    </>
  );
}
