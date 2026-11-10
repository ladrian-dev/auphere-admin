/**
 * Spec 047 — las URL de las pantallas nuevas de un cliente y de un agente
 * (`plan.md`, olas 2 y 3: `clients/[ref]` con sus pestañas Panel, Negocio y
 * Agentes, y `clients/[ref]/agents/[agentId]`). Spec 056 (requisito 3.1): Acceso,
 * la cuarta, solo para owner y admin. Un solo sitio: la paleta, las
 * migas y las pantallas que vienen después las escriben igual.
 */
export type ClientTab = "panel" | "business" | "agents" | "access";

export function clientHref(ref: string, tab: ClientTab = "panel"): string {
  const base = `/clients/${encodeURIComponent(ref)}`;
  return tab === "panel" ? base : `${base}/${tab}`;
}

export function agentHref(ref: string, agentId: string): string {
  return `${clientHref(ref, "agents")}/${encodeURIComponent(agentId)}`;
}
