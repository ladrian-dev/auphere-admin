import type { MessageKey } from "@/i18n/messages";
import type { AgentSpec, MissingCapability, SpecProblem } from "@/lib/backend/builder-types";

import { NEVER_CONNECT, integrationName } from "./builder-model";

/**
 * Spec 047, enmienda del 2026-10-30 «Solo lo que tenemos» (T228; requisitos
 * 65.3 y 65.4; `contracts/console-api.md` §11) — lo que la consola decide sin
 * pintar nada sobre lo que no tenemos: la lista que se enseña, a qué nunca se
 * le pone «Conectar {X}» y cómo se dice un `integration_unknown` del
 * validador. Puro: lo prueban los tests sin montar la pantalla.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const KINDS: ReadonlySet<string> = new Set(["integration", "module", "tool", "action"]);

/**
 * La lista que se enseña de `missing_capabilities`: un elemento por clase y
 * clave, en el orden en que llega. Se usa su `label`; si no la trae, se nombra
 * por su clave (el estado parcial). Sin `label` ni clave no se inventa nada.
 * Lo que no es una lista cuenta como «nada que se sepa».
 */
export function missingCapabilities(raw: unknown): MissingCapability[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const out: MissingCapability[] = [];
  for (const item of raw as unknown[]) {
    if (!item || typeof item !== "object") continue;
    const m = item as Partial<MissingCapability>;
    const key = typeof m.key === "string" ? m.key.trim() : "";
    const given = typeof m.label === "string" ? m.label.trim() : "";
    const label = given || (key ? integrationName(key) : "");
    if (!label) continue;
    const kind = typeof m.kind === "string" && KINDS.has(m.kind) ? m.kind : "tool";
    // La misma promesa en dos textos sale una vez: arreglada la primera, la
    // siguiente llega en la lectura de después.
    const id = `${kind}:${key || label}`;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({
      kind,
      key,
      label,
      reason: (m.reason ?? "no_tool") as MissingCapability["reason"],
      source: (m.source ?? "text") as MissingCapability["source"],
      pointer: typeof m.pointer === "string" && m.pointer ? m.pointer : null,
    });
  }
  return out;
}

/**
 * Lo que falta según el borrador, que siempre lo trae (`AgentDraftOut`). Una
 * respuesta de antes sin el campo cae en lo que dejó el trabajo que lo
 * escribió (`result.missing_capabilities`), que es lo mismo recién creado.
 */
export function missingFrom(fromDraft: unknown, fromJob: unknown): MissingCapability[] {
  return missingCapabilities(fromDraft === undefined || fromDraft === null ? fromJob : fromDraft);
}

/** Las claves que la API dice que no ofrecemos como conector o que son un módulo apagado. */
export function notOfferedKeys(missing: readonly MissingCapability[]): Set<string> {
  return new Set(missing.filter((m) => (m.kind === "integration" || m.kind === "module") && m.key).map((m) => m.key));
}

/** ¿Se le puede poner «Conectar {X}»? Nunca a Reservas ni a lo que no ofrecemos (65.3). */
export function canConnect(integration: string, notOffered: ReadonlySet<string> = new Set()): boolean {
  return !NEVER_CONNECT.has(integration) && !notOffered.has(integration);
}

/** El valor al que apunta un puntero JSON (`/skills/0/integration`) dentro del AgentSpec. */
export function pointerValue(spec: AgentSpec | null | undefined, pointer: string): unknown {
  if (!spec || !pointer.startsWith("/")) return undefined;
  let at: unknown = spec;
  for (const raw of pointer.slice(1).split("/")) {
    const part = raw.replace(/~1/g, "/").replace(/~0/g, "~");
    if (Array.isArray(at)) at = at[Number(part)];
    else if (at && typeof at === "object") at = (at as Record<string, unknown>)[part];
    else return undefined;
  }
  return at;
}

/**
 * Un problema del validador, en palabras. `integration_unknown` (65.3) lo dice
 * la consola, con el conector que pide si se encuentra en el AgentSpec; los
 * demás siguen con su mensaje, o con su código si no lo traen.
 */
export function specProblemText(problem: SpecProblem, spec: AgentSpec | null | undefined, t: T): string {
  if (problem.code === "integration_unknown") {
    const value = pointerValue(spec, problem.pointer);
    return typeof value === "string" && value
      ? t("builder.problem.integration_unknown", { name: integrationName(value) })
      : t("builder.problem.integration_unknown.generic");
  }
  return problem.message || problem.code;
}
