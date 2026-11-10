import type { Call } from "../backend";

/**
 * Spec 047, enmienda del 2026-10-29 (T210, requisito 60.6;
 * `contracts/console-api.md` §10): los agentes que el sistema sugiere para un
 * cliente al leer su ficha. Nunca se crean solos: «Crear este agente» abre
 * «Nuevo agente» con su nombre y su descripción, y «Descartar» los quita para
 * esa ficha (no vuelven).
 *
 * Enmienda del 2026-10-30 (T228, requisito 65.7; §11): no hay papeles fijos.
 * `role` es opcional: `null` es lo normal, puede no venir y cualquier valor que
 * la consola no conozca cuenta como `null`. La consola no lo exige ni decide
 * nada con él: solo lo nombra si tiene palabras para él (`suggestedRole`).
 */

/** Los papeles que la consola sabe nombrar. Ninguno es obligatorio. */
export const SUGGESTED_ROLES = ["reception", "sales", "billing", "support"] as const;
export type SuggestedRole = (typeof SUGGESTED_ROLES)[number];
export type SuggestedAgent = { id: string; name: string; description: string; role?: string | null };

/** El papel de una sugerencia si la consola sabe nombrarlo; cualquier otra cosa, `null`. */
export function suggestedRole(role: unknown): SuggestedRole | null {
  return typeof role === "string" && (SUGGESTED_ROLES as readonly string[]).includes(role) ? (role as SuggestedRole) : null;
}

export function suggestedAgentsApi(call: Call) {
  const enc = encodeURIComponent;
  const base = (ref: string) => `/console/clients/${enc(ref)}/suggested-agents`;
  return {
    listSuggestedAgents: async (ref: string) => (await call<{ agents: SuggestedAgent[] }>(base(ref))).agents,
    dismissSuggestedAgent: (ref: string, id: string) => call<null>(`${base(ref)}/${enc(id)}/dismiss`, { method: "POST" }),
  };
}
