import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { CapabilitiesCatalog } from "@/components/capabilities/catalog";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { agentChoice } from "../data";

/**
 * Capacidades (spec 017, R5): lo que el agente sabe hacer, en una sola
 * pantalla donde antes había dos — Herramientas y Habilidades.
 *
 * El filtro por sector viaja en la URL (`?all=1`) en vez de en estado del
 * cliente: así un enlace a «todas» se puede compartir y volver atrás hace lo
 * que el partner espera.
 */
export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("cap.title") };
}

export default async function CapabilitiesPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ all?: string; agent?: string }>;
}) {
  const { ref } = await params;
  const { all, agent } = await searchParams;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/capabilities`);
  if (!can(principal.role, "agents:read")) redirect(`/clients/${encodeURIComponent(ref)}`);
  const { t } = await getT(principal.locale);
  // Spec 030: the capabilities of the agent in `?agent=` (the principal without it).
  const { agentId } = await agentChoice(principal, ref, agent);

  const data = await backendFor(principal).listCapabilities(ref, {
    all: all === "1",
    lang: principal.locale,
    agent: agentId,
  });
  const base = `/clients/${encodeURIComponent(ref)}/capabilities`;
  const own = agentId ? `${base}?agent=${encodeURIComponent(agentId)}` : base;

  return (
    <section aria-label={t("cap.title")} className="flex flex-col gap-(--space-section)">
      <PageHeader title={t("cap.title")} description={t("cap.description")} />
      <CapabilitiesCatalog
        refId={ref}
        data={data}
        canWrite={can(principal.role, "agents:write")}
        seeAllHref={`${own}${agentId ? "&" : "?"}all=1`}
        seeOwnHref={own}
        agentId={agentId}
      />
    </section>
  );
}
