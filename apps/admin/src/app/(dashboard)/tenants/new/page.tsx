import { PageHeader } from "@/components/brand/page-header";

import { NewTenantWizard } from "./wizard-form";

export const metadata = { title: "Nuevo tenant · Nexus" };

export default function NewTenantPage() {
  return (
    <>
      <PageHeader
        eyebrow="Onboarding"
        title="Nuevo tenant"
        description="Identidad básica del cliente y alerta de costo. Los connectors se conectan en el siguiente paso."
      />
      <div className="rounded-md border border-border bg-card p-6 max-w-3xl">
        <NewTenantWizard />
      </div>
    </>
  );
}
