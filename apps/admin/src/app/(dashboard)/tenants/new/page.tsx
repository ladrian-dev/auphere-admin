import { PageHeader } from "@/components/brand/page-header";

import { NewTenantWizard } from "./wizard-form";

export const metadata = { title: "Nuevo tenant · Nexus" };

export default function NewTenantPage() {
  return (
    <>
      <PageHeader
        eyebrow="Onboarding"
        title="Nuevo tenant"
        description="Phase 1: identidad básica + alerta de costo. WhatsApp y AgendaPro se conectan en el siguiente paso."
      />
      <div className="rounded-md border border-border bg-card p-6 max-w-3xl">
        <NewTenantWizard />
      </div>
    </>
  );
}
