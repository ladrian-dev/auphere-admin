/**
 * Qué dice cada entrada del historial del agente (spec 017, R3.6).
 *
 * «Agente» era una lista de versiones con su fecha: decía CUÁNDO pasó algo,
 * nunca QUÉ. El borrador pendiente ya sabe en qué pantallas difiere de la
 * versión que atiende, así que la entrada lo dice en vez de obligar a
 * abrirla para averiguarlo.
 *
 * Módulo puro: se prueba sin montar React.
 */
import type { AgentBundle, AgentVersion, DraftScreen } from "@/lib/backend";

/** El borrador actual: el más nuevo por encima de la activa. Las versiones
 *  preparadas y luego superadas no son «el borrador». */
export function isCurrentDraft(v: AgentVersion, bundle: AgentBundle): boolean {
  if (v.status !== "staged") return false;
  if (v.version === bundle.active_version) return false;
  const newerStaged = bundle.versions.some((o) => o.status === "staged" && o.version > v.version);
  if (newerStaged) return false;
  return bundle.active_version === null || v.version > bundle.active_version;
}

/** Las pantallas que esta entrada cambia; vacío cuando no hay nada que decir. */
export function changedScreens(v: AgentVersion, bundle: AgentBundle): DraftScreen[] {
  return isCurrentDraft(v, bundle) ? bundle.draft_screens : [];
}
