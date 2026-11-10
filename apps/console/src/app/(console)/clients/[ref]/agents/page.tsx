import { redirect } from "next/navigation";

import { AgentCards } from "@/components/builder/agent-cards";
import { newAgentHref } from "@/components/builder/life-model";
import { clientHref } from "@/components/shell/routes-v2";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor, callFor } from "@/lib/backend";
import { suggestedAgentsApi } from "@/lib/backend/suggested-agents";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getConsoleVersionCached } from "../data";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("builder.agents.title") };
}

/**
 * La pestaña Agentes de un cliente con la consola nueva (spec 047, historia 7):
 * una tarjeta por agente y «Nuevo agente» para quien puede escribir. Cuelga
 * del marco del cliente (Panel · Negocio · Agentes). Con la consola de hoy no
 * existe: los agentes se llevan desde la pestaña «Agente».
 *
 * `?new=1` (el Panel de un cliente sin agentes) abre «Nuevo agente».
 *
 * Enmienda del 2026-10-29 (T210, requisito 60.6): detrás de sus agentes, los
 * que el sistema sugiere para su ficha, como tarjetas «Sugerido». Si no se
 * pueden leer, la pestaña se pinta igual, sin ellas: no son de este cliente
 * todavía.
 */
export default async function AgentsPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ new?: string }>;
}) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/agents`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}/agent`);
  if (!can(principal.role, "agents:read")) redirect(clientHref(ref));
  const canWrite = can(principal.role, "agents:write");
  if ((await searchParams).new === "1" && canWrite) redirect(newAgentHref(ref));

  const [agents, suggested] = await Promise.all([
    run(() => backendFor(principal).listAgents(ref)),
    run(() => suggestedAgentsApi(callFor(principal)).listSuggestedAgents(ref)),
  ]);
  return (
    <AgentCards refId={ref} agents={agents.ok ? agents.data : null} canWrite={canWrite} suggested={suggested.ok ? suggested.data : null} />
  );
}
