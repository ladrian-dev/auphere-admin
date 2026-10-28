import type { AgentReview, PublishPreview, ReviewFinding, TestSummary } from "@/lib/backend/agent-quality-types";
import type { EditableBlock } from "@/lib/backend/builder-types";

import { isEditable, type AgentBlockKey } from "./builder-model";

/**
 * «Configuración» como el prototipo aprobado («Consola de partners v2»;
 * `specs/047-la-fabrica-de-agentes/evidence/prototipo/agente.md` §4, §5 y §12),
 * sin pintar nada: en qué fila cae cada bloque del AgentSpec, qué vive en «Más
 * ajustes», en qué punto están las pruebas y qué dice la barra flotante. Puro:
 * lo prueban los tests sin montar la pantalla.
 */

/** Las cinco filas del prototipo, en su orden. */
export const AGENT_ROWS = ["does", "speaks", "knows", "can", "handoff"] as const;
export type AgentRow = (typeof AGENT_ROWS)[number];

/**
 * Los 9 bloques en las 5 filas (§12): qué hace = identidad, instrucciones y
 * reglas; cómo habla = voz y aviso de IA; qué sabe = servicios (y el
 * conocimiento propio, que no es un bloque); qué puede hacer = habilidades (con
 * lo que piden conectar) y procedimientos; cuándo pasa a una persona = escalado.
 */
export const ROW_BLOCKS: Record<AgentRow, readonly AgentBlockKey[]> = {
  does: ["identity", "instructions", "rules"],
  speaks: ["voice", "ai_disclosure"],
  knows: ["services"],
  can: ["skills", "procedures"],
  handoff: ["escalation"],
};

/** El bloque que da título a la fila (`builder.block.*`). */
export const ROW_TITLE_BLOCK: Record<AgentRow, AgentBlockKey> = {
  does: "identity",
  speaks: "voice",
  knows: "services",
  can: "skills",
  handoff: "escalation",
};

export function rowOfBlock(block: string): AgentRow | null {
  return AGENT_ROWS.find((row) => (ROW_BLOCKS[row] as readonly string[]).includes(block)) ?? null;
}

/** La fila de un ancla: `bloque-rules` → «Qué hace»; el conocimiento vive en «Qué sabe». */
export function rowOfSection(id: string | null | undefined): AgentRow | null {
  if (!id) return null;
  if (id === "agente-conocimiento") return "knows";
  return id.startsWith("bloque-") ? rowOfBlock(id.slice("bloque-".length)) : null;
}

/** Los bloques de una fila que tienen editor, en su orden: el lápiz abre el primero. */
export function editableBlocks(row: AgentRow): EditableBlock[] {
  return ROW_BLOCKS[row].filter((b): b is EditableBlock => isEditable(b));
}

/** Lo que no está en el prototipo y queda plegado bajo la tabla. */
const MORE_SECTIONS: ReadonlySet<string> = new Set([
  "agente-recepcion",
  "agente-pruebas",
  "agente-revision",
  "agente-historial",
  "agente-avanzado",
  "agente-calidad",
  "agente-copiloto",
  "agente-propuestas",
]);

/** ¿Está esta sección dentro de «Más ajustes»? Un enlace a ella la abre. */
export function inMore(id: string | null | undefined): boolean {
  return Boolean(id && MORE_SECTIONS.has(id));
}

// ── las pruebas (§5.1) ──────────────────────────────────────────────────────

export type TestsState =
  | { kind: "none" }
  | { kind: "pending"; pending: number; counted: number }
  | { kind: "failing"; failing: number; passed: number; counted: number }
  | { kind: "passing"; passed: number; counted: number };

/**
 * En qué punto están: las que cuentan son todas menos las «No aplica». Con
 * alguna sin ejecutar o desactualizada (editar un bloque las deja así), no han
 * terminado. Terminadas, o pasan todas o se dice cuántas no (falla, inestable o
 * sin decidir).
 */
export function testsState(summary: TestSummary): TestsState {
  const counted = Math.max(0, summary.total - summary.not_applicable);
  if (!counted) return { kind: "none" };
  const pending = Math.min(counted, summary.not_run + summary.stale);
  if (pending > 0) return { kind: "pending", pending, counted };
  const failing = summary.failed + summary.flaky + summary.unknown;
  if (failing > 0) return { kind: "failing", failing, passed: summary.passed, counted };
  return { kind: "passing", passed: summary.passed, counted };
}

// ── la revisión, compacta ───────────────────────────────────────────────────

/**
 * La comprobación de cada hallazgo, por su código (`services/agent_spec/review.py`).
 * La API no la manda junto al hallazgo: un código que no se conoce no se coloca.
 */
export function checkOfFinding(code: string): string | null {
  if (code.startsWith("skill_without")) return "skills_integrations";
  if (code === "service_without_price" || code === "bookable_without_duration") return "services";
  if (code === "no_hours") return "hours";
  if (code.startsWith("contradicts_")) return "contradictions";
  if (code.startsWith("promises_")) return "promises";
  if (code === "unknown_tool") return "tools_exist";
  if (code === "channel_without_recipients") return "escalation_recipients";
  if (code.startsWith("ai_disclosure")) return "ai_disclosure";
  return null;
}

export function findingsByCheck(review: AgentReview): Map<string, ReviewFinding[]> {
  const out = new Map<string, ReviewFinding[]>();
  for (const finding of review.findings) {
    const check = checkOfFinding(finding.code);
    if (!check) continue;
    out.set(check, [...(out.get(check) ?? []), finding]);
  }
  return out;
}

// ── la barra flotante (§4.5) ────────────────────────────────────────────────

export type BarTests = { summary: TestSummary | null; running: boolean; canRun: boolean } | null;

export type BarState =
  | { kind: "readonly" }
  | { kind: "running" }
  | { kind: "failing"; failing: number; total: number; save: boolean }
  | { kind: "passing"; passed: number; total: number; saved: boolean; next: "save" | "connect" | null }
  | { kind: "pending"; draft: boolean }
  /** Sin datos de las pruebas: el texto de siempre y «Guardar». */
  | { kind: "plain" };

/**
 * Qué dice la barra, en el orden del prototipo: pruebas en marcha; terminadas
 * con fallos («Guardar igualmente» si hay algo que guardar); terminadas y todas
 * pasan (guardar lo que diga la API, o conectar un canal si ya está guardado y
 * no tiene ninguno); y el resto, «Borrador completo» con «Ejecutar pruebas».
 * Las preguntas pendientes del prototipo no llegan a esta pantalla (la API no
 * las guarda con el agente). Sin datos de las pruebas, o sin poder
 * ejecutarlas, la barra de siempre.
 */
export function barState({ canWrite, preview, tests }: { canWrite: boolean; preview: PublishPreview; tests: BarTests }): BarState {
  if (!canWrite) return { kind: "readonly" };
  if (!tests?.summary) return { kind: "plain" };
  if (tests.running) return { kind: "running" };
  const state = testsState(tests.summary);
  switch (state.kind) {
    case "failing":
      return { kind: "failing", failing: state.failing, total: state.counted, save: preview.has_draft };
    case "passing":
      return {
        kind: "passing",
        passed: state.passed,
        total: state.counted,
        saved: !preview.has_draft,
        next: preview.has_draft ? "save" : preview.has_channels ? null : "connect",
      };
    case "pending":
      return tests.canRun ? { kind: "pending", draft: preview.has_draft } : { kind: "plain" };
    case "none":
      return { kind: "plain" };
  }
}
