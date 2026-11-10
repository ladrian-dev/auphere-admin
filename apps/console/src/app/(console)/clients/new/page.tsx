import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { resolveConsoleVersion } from "@/components/shell/console-version";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { NewClientWizard } from "./wizard";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("wizard.title");

/**
 * New-client wizard (CP-10): four steps, real per-stage progress. Quota is
 * checked here (step 1 blocks when full) and again by the API on create.
 */
export default async function NewClientPage() {
  const principal = await requirePartnerPrincipal("/clients/new");
  if (!can(principal.role, "clients:write")) redirect("/clients");
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);
  // Spec 047 (T050): con la consola nueva, el alta es el modal de tres datos de
  // la lista; quien llega aquí (la paleta, un enlace guardado) lo encuentra
  // abierto allí. Sin plantilla: crear un cliente nunca crea un agente.
  if (resolveConsoleVersion(await api.me().catch(() => null)) === "v2") redirect("/clients?new=1");
  const templates = can(principal.role, "agents:read")
    ? await api.listSeedTemplates().catch(() => null)
    : [];
  return (
    <>
      <PageHeader eyebrow={t("nav.clients")} title={t("wizard.title")} description={t("wizard.subtitle")} />
      <NewClientWizard templates={templates} />
    </>
  );
}
