import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { NewClientWizard } from "./wizard";

export const metadata = { title: "Nuevo cliente" };

/**
 * New-client wizard (CP-10): four steps, real per-stage progress. Quota is
 * checked here (step 1 blocks when full) and again by the API on create.
 */
export default async function NewClientPage() {
  const principal = await requirePrincipal("/clients/new");
  if (!can(principal.role, "clients:write")) redirect("/clients");
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);
  const [me, templates] = await Promise.all([
    api.me(),
    can(principal.role, "agents:read") ? api.listSeedTemplates().catch(() => null) : [],
  ]);
  return (
    <>
      <PageHeader eyebrow={t("nav.clients")} title={t("wizard.title")} description={t("wizard.subtitle")} />
      <NewClientWizard quota={me.quota} templates={templates} canPublish={can(principal.role, "agents:write")} />
    </>
  );
}
