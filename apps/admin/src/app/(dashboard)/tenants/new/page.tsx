import { PageHeader } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { NewTenantWizard } from "./wizard-form";

export const metadata = { title: "Nuevo tenant" };

export default async function NewTenantPage() {
  // Spec 077 (T024): a send-only client may hang from a partner. A failed read
  // is said (and blocks a send-only client), never taken for «no partners».
  const partners = await backend.listPartners().catch(() => null);
  const partnersError = partners === null;
  return (
    <>
      <PageHeader
        title="Nuevo tenant"
        description="Identidad básica del cliente y alerta de costo. Los connectors se conectan en el siguiente paso."
      />
      <div className="rounded-md border border-border bg-card p-6 max-w-3xl">
        <NewTenantWizard
          partners={(partners ?? [])
            .filter((p) => p.status === "active")
            .map((p) => ({ id: p.id, name: p.name }))}
          partnersError={partnersError}
        />
      </div>
    </>
  );
}
