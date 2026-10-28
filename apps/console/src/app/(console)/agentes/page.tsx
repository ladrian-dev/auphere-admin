import type { Metadata } from "next";

import { LiteAgentsView } from "@/components/lite/lite-agents";
import { pageTitle } from "@/i18n/metadata";
import { backendFor } from "@/lib/backend";
import { requireClientPrincipal } from "@/lib/principal";

export const generateMetadata = (): Promise<Metadata> => pageTitle("nav.agents");

/**
 * Spec 047 (T168; requisitos 50.1 y 50.2): «Agentes» de la persona del cliente.
 * Solo la persona de un cliente con el módulo `agents`; a cualquier otra la
 * lleva a lo suyo la guarda. Si la lista no llega, la pantalla lo dice y deja
 * reintentar (`null`).
 */
export default async function AgentesPage() {
  const principal = await requireClientPrincipal("agents", "/agentes");
  const data = await backendFor(principal)
    .liteAgents()
    .catch(() => null);
  return <LiteAgentsView initial={data} />;
}
