/**
 * Spec 047 — las URL de las pantallas nuevas de un cliente y de un agente
 * (`plan.md`, olas 2 y 3: `clients/[ref]` con sus pestañas Panel, Negocio y
 * Agentes, y `clients/[ref]/agents/[agentId]`). Un solo sitio: la paleta, las
 * migas y las pantallas que vienen después las escriben igual.
 */
export type ClientTab = "panel" | "business" | "agents";

export function clientHref(ref: string, tab: ClientTab = "panel"): string {
  const base = `/clients/${encodeURIComponent(ref)}`;
  return tab === "panel" ? base : `${base}/${tab}`;
}

export function agentHref(ref: string, agentId: string): string {
  return `${clientHref(ref, "agents")}/${encodeURIComponent(agentId)}`;
}
