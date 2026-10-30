import type {
  AgentSpec,
  BuilderBlock,
  BuilderBlockKey,
  ConnectRequest,
  DraftJob,
  EditableBlock,
  EscalationTrigger,
  SpecProblem,
} from "@/lib/backend/builder-types";
import { BUILDER_BLOCKS } from "@/lib/backend/builder-types";

/**
 * Spec 047 (historia 7, T081) — lo que el constructor necesita saber sin pintar
 * nada: los límites, el orden de los bloques, la espera creciente al consultar
 * el trabajo, los nombres de los conectores y cómo se escribe un bloque dentro
 * del AgentSpec. Puro: lo prueban los tests sin montar la pantalla.
 */

/** Los límites de la descripción cuando la API no pudo decirlos (`draft-options`). */
export const LIMITS = { name_max: 40, description_min: 20, description_max: 1024 } as const;
/** Las instrucciones por secciones suman como mucho esto (requisito 16.1). */
export const INSTRUCTIONS_MAX = 8000;

/** Primera espera, el techo y cómo crece (`console-api.md`, Convenciones). */
export const POLL_FIRST_MS = 1000;
export const POLL_MAX_MS = 10_000;

/**
 * La siguiente espera: 1, 2, 4… hasta 10 s mientras el trabajo no cambia. Si
 * llegó un bloque nuevo vuelve a 1 s, para que el borrador se siga viendo
 * escribir y no a saltos de 10 s.
 */
export function nextDelay(previous: number, advanced: boolean): number {
  if (advanced) return POLL_FIRST_MS;
  return Math.min(previous * 2, POLL_MAX_MS);
}

/** Los bloques que llegaron, uno por clave y en el orden del borrador. */
export function arrivedBlocks(job: DraftJob | null): BuilderBlock[] {
  const raw = job?.progress?.blocks ?? [];
  const byKey = new Map<BuilderBlockKey, BuilderBlock>();
  for (const block of raw) {
    if (block && (BUILDER_BLOCKS as readonly string[]).includes(block.key)) byKey.set(block.key, block);
  }
  return BUILDER_BLOCKS.flatMap((key) => {
    const block = byKey.get(key);
    return block ? [block] : [];
  });
}

export type StepState = "done" | "active" | "wait";

/**
 * Los cuatro pasos de «Preparando el borrador» (prototipo §3.2), leídos del
 * trabajo y de nada más: leer la ficha (hasta que el trabajo pasa a escribir),
 * proponer instrucciones y habilidades (hasta que llegan las pruebas), escribir
 * las pruebas (hasta que llegan las preguntas) y validar las preguntas (hasta
 * que termina). El primero sin hacer está en curso; lo que la consulta no llegó
 * a ver se marca hecho de una vez cuando el trabajo termina.
 */
export function draftSteps(job: DraftJob | null): [StepState, StepState, StepState, StepState] {
  const finished = job?.status === "done";
  const keys = new Set(arrivedBlocks(job).map((b) => b.key));
  const done = [
    finished || job?.progress?.step === "writing" || keys.size > 0,
    finished || keys.has("tests") || keys.has("questions"),
    finished || keys.has("questions"),
    finished,
  ];
  const first = done.indexOf(false);
  return done.map((d, i) => (d ? "done" : i === first ? "active" : "wait")) as [StepState, StepState, StepState, StepState];
}

/** Las pruebas del caso que contó el trabajo (el bloque `tests`); `null` si aún no llegaron. */
export function caseTests(job: DraftJob | null): number | null {
  const block = arrivedBlocks(job).find((b) => b.key === "tests");
  return typeof block?.count === "number" ? block.count : null;
}

/** Marcar o desmarcar un idioma: se añade al final (el primero es el principal), como mucho cinco. */
export function toggleLanguage(codes: readonly string[], code: string): string[] {
  if (codes.includes(code)) return codes.filter((c) => c !== code);
  return codes.length >= 5 ? [...codes] : [...codes, code];
}

/** Lo que escribió la persona, ya recortado como lo recorta la API. */
export function cleanName(name: string): string {
  return name.split(/\s+/).filter(Boolean).join(" ");
}

export type DescribeProblem = "name" | "description" | null;

/** ¿Se puede pedir «Generar borrador»? Los mismos límites que la API (17.1). */
export function describeProblems(
  name: string,
  description: string,
  limits: { name_max: number; description_min: number; description_max: number } = LIMITS,
): { name: boolean; description: boolean } {
  const n = cleanName(name).length;
  const d = description.trim().length;
  return { name: n < 1 || n > limits.name_max, description: d < limits.description_min || d > limits.description_max };
}

/** Los nombres de marca que no salen de poner mayúscula a la clave. */
const BRANDS: Record<string, string> = {
  google_calendar: "Google Calendar",
  googlecalendar: "Google Calendar",
  gcal: "Google Calendar",
  mercadopago: "Mercado Pago",
  mercado_pago: "Mercado Pago",
  woocommerce: "WooCommerce",
  shopify: "Shopify",
  stripe: "Stripe",
  whatsapp: "WhatsApp",
  hubspot: "HubSpot",
  calendly: "Calendly",
  paypal: "PayPal",
};

/** «googlecalendar» → «Google Calendar»; «mi_crm» → «Mi crm». */
export function integrationName(key: string): string {
  return BRANDS[key] ?? humanize(key);
}

/** La clave de una habilidad, legible: «reservas.create_booking» → «Reservas create booking». */
export function skillName(key: string): string {
  return BRANDS[key] ?? humanize(key);
}

function humanize(key: string): string {
  const words = key.replace(/[._]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key;
}

/** «es» → «español» en el idioma de la consola; un código raro se deja como está. */
export function languageName(code: string, locale: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

const LANG = /^[a-z]{2,3}(-[A-Z]{2})?$/;

/** «es, pt-BR» → `["es", "pt-BR"]`; `null` si alguno no es un código o son más de 5. */
export function parseLanguages(text: string): string[] | null {
  const codes = [...new Set(text.split(/[,\s]+/).map((c) => c.trim()).filter(Boolean))];
  if (!codes.length) return [];
  if (codes.length > 5 || codes.some((c) => !LANG.test(c))) return null;
  return codes;
}

/** El id de un procedimiento nuevo (`^[a-z0-9_]{1,40}$`), único entre los que hay. */
export function procedureId(title: string, taken: ReadonlySet<string>): string {
  const base =
    title
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 34) || "procedimiento";
  if (!taken.has(base)) return base;
  for (let i = 2; ; i += 1) {
    const candidate = `${base}_${i}`;
    if (!taken.has(candidate)) return candidate;
  }
}

/**
 * Spec 047, enmienda del 2026-10-30 (65.3): lo que nunca lleva «Conectar {X}».
 * Reservas es un módulo del cliente, no un conector: encendido o apagado, no se
 * «conecta».
 */
export const NEVER_CONNECT: ReadonlySet<string> = new Set(["reservas"]);

/**
 * Los conectores que faltan, con las habilidades que los piden en su fila
 * (17.6). Solo los que se pueden conectar (65.3): nunca Reservas ni lo que la
 * API dice que no ofrecemos (`notOffered`, de `missing_capabilities`).
 */
export function connectByIntegration(connect: readonly ConnectRequest[] | undefined, notOffered: ReadonlySet<string> = new Set()): Map<string, string> {
  const out = new Map<string, string>();
  for (const c of connect ?? []) {
    if (!c?.integration || out.has(c.integration) || NEVER_CONNECT.has(c.integration) || notOffered.has(c.integration)) continue;
    out.set(c.integration, c.reason);
  }
  return out;
}

/** El bloque `key` tal como lo pinta la vista de lectura, sacado del AgentSpec. */
export function blockFromSpec(spec: AgentSpec, key: Exclude<BuilderBlockKey, "tests" | "questions">): BuilderBlock {
  if (key === "skills") return { key, value: spec.skills ?? [], connect: spec.connection_requests ?? [] };
  return { key, value: spec[key] };
}

/** Los bloques de la pantalla del agente, en el orden del borrador. */
// El aviso de IA no lo escribe el constructor (16.6): no está en `BUILDER_BLOCKS`,
// pero aquí se lee y lo decide una persona.
export const AGENT_BLOCKS = ["identity", "voice", "instructions", "procedures", "services", "skills", "escalation", "rules", "ai_disclosure"] as const;
export type AgentBlockKey = (typeof AGENT_BLOCKS)[number];

const EDITABLE: ReadonlySet<string> = new Set<EditableBlock>(["identity", "voice", "instructions", "procedures", "escalation", "rules", "ai_disclosure"]);
export function isEditable(key: string): key is EditableBlock {
  return EDITABLE.has(key);
}

/** El AgentSpec con un bloque nuevo; `undefined` lo quita (si el esquema lo deja). */
export function withBlock<K extends EditableBlock>(spec: AgentSpec, key: K, value: AgentSpec[K] | undefined): AgentSpec {
  const next: AgentSpec = { ...spec };
  if (value === undefined) delete next[key];
  else next[key] = value;
  return next;
}

/** Los problemas del validador que caen dentro de un bloque (`/rules/2` → `rules`). */
export function problemsOf(problems: readonly SpecProblem[], key: string): SpecProblem[] {
  return problems.filter((p) => p.pointer === `/${key}` || p.pointer.startsWith(`/${key}/`));
}

/** El bloque al que apunta un puntero JSON, para decir dónde cambia una propuesta. */
export function blockOfPointer(pointer: string): BuilderBlockKey | "ai_disclosure" | null {
  const first = pointer.split("/")[1] ?? "";
  if (first === "connection_requests" || first === "tools") return "skills";
  if (first === "ai_disclosure") return "ai_disclosure";
  return (BUILDER_BLOCKS as readonly string[]).includes(first) ? (first as BuilderBlockKey) : null;
}

/** Un valor corto y legible de una operación de propuesta. */
export function previewValue(value: unknown, max = 200): string {
  if (value === undefined || value === null) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** ¿Es un motivo de escalado de los del catálogo? */
export function isCustomTrigger(trigger: EscalationTrigger): trigger is { custom: string } {
  return typeof trigger === "object" && trigger !== null && "custom" in trigger;
}

/** Caracteres de las secciones de instrucciones, que suman como mucho 8.000. */
export function sectionsChars(sections: readonly { body: string }[]): number {
  return sections.reduce((n, s) => n + s.body.length, 0);
}

/** Lo que devuelve una acción de servidor (`lib/actions.ts`), visto desde el navegador. */
export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; code?: string | null; info?: Record<string, unknown> };

/** Espera de verdad; los tests pasan una que no espera. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Los grupos de plantillas en el orden en que llegan: la del partner va primero (17.9). */
export function groupTemplates<T extends { group: string }>(templates: readonly T[]): { group: string; items: T[] }[] {
  const out: { group: string; items: T[] }[] = [];
  for (const tpl of templates) {
    const found = out.find((g) => g.group === tpl.group);
    if (found) found.items.push(tpl);
    else out.push({ group: tpl.group, items: [tpl] });
  }
  return out;
}

/**
 * Spec 047 (49.6): los avisos enlazan a la pantalla del agente con `?tab=`
 * (`notifications.LINKS` de la API). Cada pestaña es una sección de la pantalla:
 * la página la lleva a la vista al abrirse. «Calidad» (`model.retirement`,
 * `model.price_change`, T147) cae en Avanzado, en la línea que dice que el
 * modelo lo gestiona Auphere (64.1; D55); las
 * sugerencias de la semana (`agent.suggestions.ready`) llevan a Rendimiento y
 * las correcciones del negocio (`agent.correction.proposed`), a Mejoras (T174).
 * `integrations` (y `connectors`) llevan a los Conectores del agente (T129).
 */
const TAB_SECTION: Record<string, string> = {
  advanced: "agente-avanzado",
  quality: "agente-calidad",
  integrations: "agente-conectores",
  connectors: "agente-conectores",
  channels: "agente-canales",
  tests: "agente-pruebas",
  performance: "agente-rendimiento",
  improvements: "agente-mejoras",
  reception: "agente-recepcion",
};

export function sectionForTab(tab: string | null | undefined): string | null {
  return tab ? (TAB_SECTION[tab] ?? null) : null;
}

/**
 * Las cuatro pestañas de la pantalla del agente, como el prototipo aprobado
 * («Consola de partners v2»): Rendimiento · Configuración · Canales ·
 * Conectores. Todo lo demás (bloques, conocimiento, pruebas, revisión,
 * historial, Avanzado) vive en «Configuración».
 */
export type AgentTab = "perf" | "build" | "channels" | "connectors";

const SECTION_TAB: Record<string, AgentTab> = {
  "agente-rendimiento": "perf",
  "agente-mejoras": "perf",
  "agente-canales": "channels",
  "agente-conectores": "connectors",
};

/** La pestaña que tiene una sección (`agente-…`, `bloque-…`); `null` si no es de la pantalla. */
export function tabOfSection(id: string | null | undefined): AgentTab | null {
  if (!id) return null;
  return SECTION_TAB[id] ?? (id.startsWith("agente-") || id.startsWith("bloque-") ? "build" : null);
}
