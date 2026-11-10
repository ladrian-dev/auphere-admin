/**
 * Spec 047 (T201, 58.5): the rules of «Sectores sin guía» and «Convertir en guía
 * de Auphere», from `contracts/admin-sector-guides.md`. Pure, so they are tested
 * on their own; the API checks all of it again.
 */
import type { StatusBadgeTone } from "@nexus/ui";

import type { SectorTest } from "@/lib/backend-builder";
import type {
  ClientDataFinding,
  ClientDataKind,
  GeneratedGuide,
  GeneratedGuideStatus,
  Guide,
  PromoteBody,
  ReviewBody,
} from "@/lib/backend-sector-guides";
import { actorLabel, reasonError } from "@/lib/levers";

import { TESTS_PER_SECTOR } from "../sector-tests/sector-tests";

export const LIST_PATH = "/builder/sector-guides";
export const guidePath = (tenantId: string, guideId: string) =>
  `${LIST_PATH}/${encodeURIComponent(tenantId)}/${encodeURIComponent(guideId)}`;

// ── the list ───────────────────────────────────────────────────────────────

export const DEFAULT_LIMIT = 20;
export const MAX_LIMIT = 100;

/** `?limit=`: 1–100, 20 when absent or out of range. */
export function parseLimit(raw: string | string[] | undefined): number {
  const text = Array.isArray(raw) ? raw[0] : raw;
  const value = Number(text);
  return text && Number.isInteger(value) && value >= 1 && value <= MAX_LIMIT ? value : DEFAULT_LIMIT;
}

const SAY_AGAIN = "La API no respondió. Vuelve a intentarlo en un momento.";

/** Why a read failed: a `401` is the panel's token, anything else the API. */
export function loadErrorCopy(status: number | null): string {
  if (status === 401) {
    return "La API no acepta el token del panel: caducó o no es el de esta API. Hay que renovar NEXUS_ADMIN_TOKEN y volver a cargar.";
  }
  return SAY_AGAIN;
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** «3 generadas · 1 revisada», or that there are none. */
export function guidesCount(guides: { generated: number; reviewed: number }): string {
  if (!guides.generated && !guides.reviewed) return "Sin guías generadas";
  const parts: string[] = [];
  if (guides.generated) parts.push(plural(guides.generated, "generada", "generadas"));
  if (guides.reviewed) parts.push(plural(guides.reviewed, "revisada", "revisadas"));
  return parts.join(" · ");
}

/** «12 pruebas», or how far it is from the 12 it needs. */
export function testsCount(n: number): { label: string; complete: boolean } {
  return n === TESTS_PER_SECTOR
    ? { label: `${n} pruebas`, complete: true }
    : { label: `${n} de ${TESTS_PER_SECTOR} pruebas`, complete: false };
}

export const GUIDE_STATUS: Record<GeneratedGuideStatus, { label: string; tone: StatusBadgeTone }> = {
  generated: { label: "Sin revisar", tone: "info" },
  reviewed: { label: "Revisada", tone: "positive" },
  promoted: { label: "Convertida", tone: "positive" },
  archived: { label: "Archivada", tone: "muted" },
};

/** Who did it: «ti» for the operator looking, the address otherwise. */
export function whoLabel(actor: string | null, operatorEmail?: string): string {
  const who = actorLabel(actor);
  return operatorEmail && who === operatorEmail ? "ti" : who;
}

// ── the client's data, where it is ─────────────────────────────────────────

export const KIND_LABEL: Record<ClientDataKind, string> = {
  client_name: "Nombre del cliente",
  website: "Web del cliente",
  url: "Dirección web",
  email: "Correo",
  phone: "Teléfono",
  address: "Dirección",
  location: "Sede",
  staff: "Persona del equipo",
};

const PROCEDURE_FIELD: Record<string, string> = { title: "Título", when: "Cuándo", steps: "Pasos" };
const TEST_FIELD: Record<string, string> = {
  key: "Clave",
  name: "Nombre",
  persona: "Persona simulada",
  first_message: "Primer mensaje",
  plan: "Plan",
  expected_state: "Estado esperado",
  criteria: "Criterios",
  critical: "Crítica",
};

/** RFC 6901: `/a~1b/c~0d` → `["a/b", "c~d"]`. */
function segments(pointer: string): string[] {
  if (!pointer.startsWith("/")) return [];
  return pointer
    .slice(1)
    .split("/")
    .map((s) => s.replace(/~1/g, "/").replace(/~0/g, "~"));
}

const index = (seg: string | undefined) => (seg !== undefined && /^\d+$/.test(seg) ? Number(seg) : null);

/** Where a finding is, in words: «Procedimiento 1 · Pasos». */
export function findingPlace(pointer: string): string {
  const [area, list, i, field] = segments(pointer);
  if (area === "guide") {
    const n = index(i);
    if (list === "ask") return n === null ? "Qué preguntar" : `Qué preguntar · frase ${n + 1}`;
    if (list === "risks") return n === null ? "Riesgos" : `Riesgos · frase ${n + 1}`;
    if (list === "tools") return n === null ? "Herramientas" : `Herramientas · ${n + 1}`;
    if (list === "procedures") {
      if (n === null) return "Procedimientos";
      const what = field ? PROCEDURE_FIELD[field] : undefined;
      return what ? `Procedimiento ${n + 1} · ${what}` : `Procedimiento ${n + 1}`;
    }
    return "La guía";
  }
  if (area === "tests") {
    const n = index(list);
    if (n === null) return "Las pruebas";
    const test = `Prueba ${n + 1}`;
    if (i === "criteria") {
      const c = index(field);
      return c === null ? `${test} · Criterios` : `${test} · Criterio ${c + 1}`;
    }
    const what = i ? TEST_FIELD[i] : undefined;
    return what ? `${test} · ${what}` : test;
  }
  return "La guía";
}

/**
 * The field a finding points at, as the screen draws it: the guide's sentences
 * and procedure fields, and each test's fields and criteria. `null` when it is
 * not one field (the whole guide, a whole list).
 */
export function fieldPath(pointer: string): string | null {
  const [area, list, i, field] = segments(pointer);
  if (area === "guide") {
    const n = index(i);
    if (n === null) return null;
    if (list === "ask" || list === "risks" || list === "tools") return `/guide/${list}/${n}`;
    if (list === "procedures") return `/guide/procedures/${n}/${field && PROCEDURE_FIELD[field] ? field : "title"}`;
    return null;
  }
  if (area === "tests") {
    const n = index(list);
    if (n === null) return null;
    if (i === "criteria") {
      const c = index(field);
      return c === null ? `/tests/${n}/criteria` : `/tests/${n}/criteria/${c}`;
    }
    const known = i && i !== "criteria" && i !== "critical" && TEST_FIELD[i];
    return `/tests/${n}/${known ? i : "name"}`;
  }
  return null;
}

/** The id the screen gives a marked field, so the summary can link to it. */
export function findingAnchor(path: string): string {
  return `dato${path.replace(/[^a-z0-9]+/gi, "-")}`;
}

/** Findings grouped by the field they mark. */
export function findingsByField(findings: ClientDataFinding[]): Map<string, ClientDataFinding[]> {
  const out = new Map<string, ClientDataFinding[]>();
  for (const f of findings) {
    const path = fieldPath(f.pointer);
    if (!path) continue;
    out.set(path, [...(out.get(path) ?? []), f]);
  }
  return out;
}

export function findingText(f: ClientDataFinding): string {
  return `Dato del cliente · ${KIND_LABEL[f.kind] ?? f.kind}: «${f.excerpt}»`;
}

/**
 * The findings as errors on the editors' fields: the guide's (`ask.1`,
 * `procedures.0.steps`) and the tests' (`3.first_message`, `3.criteria.0.text`,
 * the keys of `testsFromForms`).
 */
export function findingErrors(findings: ClientDataFinding[]): { guide: Record<string, string>; tests: Record<string, string> } {
  const guide: Record<string, string> = {};
  const tests: Record<string, string> = {};
  const add = (into: Record<string, string>, key: string, text: string) => {
    into[key] = into[key] ? `${into[key]} ${text}` : text;
  };
  for (const f of findings) {
    const path = fieldPath(f.pointer);
    if (!path) continue;
    const [area, ...rest] = segments(path);
    if (area === "guide") add(guide, rest.join("."), findingText(f));
    else if (rest[1] === "criteria" && rest.length === 3) add(tests, `${rest[0]}.criteria.${rest[2]}.text`, findingText(f));
    else add(tests, rest.join("."), findingText(f));
  }
  return { guide, tests };
}

// ── the guide, as the editor shows it ──────────────────────────────────────

export const GUIDE_LIMITS = {
  ask: { min: 1, max: 10, length: 300 },
  procedures: { max: 10, title: 120, when: 300, steps: 1500 },
  risks: { max: 10, length: 300 },
  tools: { max: 20 },
} as const;

export type TextItem = { uid: string; text: string };
export type ProcedureForm = { uid: string; title: string; when: string; steps: string };
export type GuideForm = { ask: TextItem[]; procedures: ProcedureForm[]; risks: TextItem[]; tools: TextItem[] };

let seq = 0;
const nextUid = () => `g${++seq}`;

export const blankItem = (): TextItem => ({ uid: nextUid(), text: "" });
export const blankProcedure = (): ProcedureForm => ({ uid: nextUid(), title: "", when: "", steps: "" });

export function formFromGuide(guide: Guide): GuideForm {
  const items = (list: string[]) => list.map((text) => ({ uid: nextUid(), text }));
  return {
    ask: items(guide.ask),
    procedures: guide.procedures.map((p) => ({ uid: nextUid(), title: p.title, when: p.when ?? "", steps: p.steps })),
    risks: items(guide.risks),
    tools: items(guide.tools),
  };
}

const NUM = new Intl.NumberFormat("es");
const atMost = (n: number) => `Como mucho ${NUM.format(n)} caracteres.`;

export type CheckedGuide = { ok: true; guide: Guide } | { ok: false; errors: Record<string, string> };

/**
 * The guide to send, or what is wrong with it. Error keys: `ask`, `ask.{i}`,
 * `procedures`, `procedures.{i}.{title|when|steps}`, `risks`, `risks.{i}`,
 * `tools`, `tools.{i}`.
 */
export function guideFromForm(form: GuideForm): CheckedGuide {
  const errors: Record<string, string> = {};
  const L = GUIDE_LIMITS;

  if (form.ask.length < L.ask.min) errors.ask = "Hace falta al menos una frase.";
  else if (form.ask.length > L.ask.max) errors.ask = `Como mucho ${L.ask.max} frases.`;
  const ask = form.ask.map((item, i) => {
    const text = item.text.trim();
    if (!text) errors[`ask.${i}`] = "Escribe la frase o quítala.";
    else if (text.length > L.ask.length) errors[`ask.${i}`] = atMost(L.ask.length);
    return text;
  });

  if (form.procedures.length > L.procedures.max) errors.procedures = `Como mucho ${L.procedures.max} procedimientos.`;
  const procedures = form.procedures.map((p, i) => {
    const title = p.title.trim();
    const when = p.when.trim();
    const steps = p.steps.trim();
    if (!title) errors[`procedures.${i}.title`] = "Hace falta el título.";
    else if (title.length > L.procedures.title) errors[`procedures.${i}.title`] = atMost(L.procedures.title);
    if (when.length > L.procedures.when) errors[`procedures.${i}.when`] = atMost(L.procedures.when);
    if (!steps) errors[`procedures.${i}.steps`] = "Hacen falta los pasos.";
    else if (steps.length > L.procedures.steps) errors[`procedures.${i}.steps`] = atMost(L.procedures.steps);
    return { title, when, steps };
  });

  if (form.risks.length > L.risks.max) errors.risks = `Como mucho ${L.risks.max} frases.`;
  const risks = form.risks.map((item, i) => {
    const text = item.text.trim();
    if (!text) errors[`risks.${i}`] = "Escribe la frase o quítala.";
    else if (text.length > L.risks.length) errors[`risks.${i}`] = atMost(L.risks.length);
    return text;
  });

  if (form.tools.length > L.tools.max) errors.tools = `Como mucho ${L.tools.max} herramientas.`;
  const tools = form.tools.map((item, i) => {
    const text = item.text.trim();
    if (!text) errors[`tools.${i}`] = "Escribe el nombre o quítala.";
    else if (text.startsWith("booking.")) errors[`tools.${i}`] = "Una guía no lleva herramientas booking.*: usa las de Reservas.";
    return text;
  });

  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, guide: { ask, procedures, risks, tools } };
}

// ── the review ─────────────────────────────────────────────────────────────

export const NOTE_MAX = 300;

export function noteError(note: string): string | null {
  return note.trim().length > NOTE_MAX ? `La nota admite como mucho ${NOTE_MAX} caracteres.` : null;
}

/** JSON with its keys in order, so two equal values compare equal. */
function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .map((k) => [k, stable((value as Record<string, unknown>)[k])]),
    );
  }
  return value;
}

export function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(stable(a)) === JSON.stringify(stable(b));
}

/**
 * What to send: `guide` and `tests` only when they changed (they replace the
 * saved ones, and the audit says whether it was edited), and the note.
 */
export function buildReviewBody(
  original: GeneratedGuide,
  edited: { guide: Guide; tests: SectorTest[] } | null,
  note: string,
): ReviewBody {
  const body: ReviewBody = {};
  if (edited && !sameJson(edited.guide, original.guide)) body.guide = edited.guide;
  if (edited && !sameJson(edited.tests, original.tests)) body.tests = edited.tests;
  const text = note.trim();
  if (text) body.note = text;
  return body;
}

// ── the conversion ─────────────────────────────────────────────────────────

/** What a guide still needs before «Convertir en guía de Auphere». Empty when it can. */
export function promoteBlockers(g: GeneratedGuide): string[] {
  if (g.status === "promoted") return ["Ya se convirtió."];
  if (g.status === "archived") return ["Está archivada."];
  const out: string[] = [];
  if (g.status === "generated") out.push("Revisarla.");
  if (g.client_data.length) out.push(`Quitar ${plural(g.client_data.length, "dato", "datos")} del cliente.`);
  if (g.tests.length !== TESTS_PER_SECTOR) out.push(`Completar las pruebas: tiene ${g.tests.length} de ${TESTS_PER_SECTOR}.`);
  if (!out.length && !g.promotable) out.push("Volver a revisarla: la API todavía no la da por lista.");
  return out;
}

const KEY = /^[a-z_]{2,40}$/;
export const LABEL_MAX = 40;
export const KEY_TAKEN = "Esa clave ya es de un sector o de otra guía de Auphere.";

/** A key the API accepts, from the label's normalised form: `peluquería canina` → `peluqueria_canina`. */
export function suggestKey(labelKey: string): string {
  const key = labelKey
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40)
    .replace(/_+$/g, "");
  return key.length >= 2 ? key : "";
}

export type PromoteForm = { key: string; label: string; reason: string };
export type CheckedPromote = { ok: true; body: PromoteBody } | { ok: false; errors: Partial<Record<keyof PromoteForm, string>> };

/** The key, the label and the reason, as the API checks them. `taken`: the keys that already have a guide, and `otro`. */
export function checkPromote(form: PromoteForm, taken: readonly string[]): CheckedPromote {
  const errors: Partial<Record<keyof PromoteForm, string>> = {};
  const key = form.key.trim();
  const label = form.label.trim();
  const reason = form.reason.trim();
  if (!key) errors.key = "Hace falta la clave.";
  else if (!KEY.test(key)) errors.key = "Solo minúsculas y «_», de 2 a 40 caracteres.";
  else if (taken.includes(key)) errors.key = KEY_TAKEN;
  if (!label) errors.label = "Hace falta la etiqueta.";
  else if (label.length > LABEL_MAX) errors.label = `Como mucho ${LABEL_MAX} caracteres.`;
  const why = reasonError(reason);
  if (why) errors.reason = why;
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, body: { key, label, reason } };
}

// ── the API's refusals, in words ───────────────────────────────────────────

const UNKNOWN_GUIDE = "Esa guía no existe o ya no es de ese cliente.";

export const REVIEW_ERRORS: Record<string, string> = {
  unknown_guide: UNKNOWN_GUIDE,
  guide_not_reviewable: "La guía ya está convertida o archivada: no se puede revisar.",
  invalid_guide: "La API no acepta la forma de la guía: revisa los límites de cada campo.",
  invalid_test: "La API rechaza el formato de alguna prueba: revisa claves, nombres, primeros mensajes y criterios.",
  twelve_tests_required: `Hacen falta exactamente ${TESTS_PER_SECTOR} pruebas.`,
  duplicate_key: "Dos pruebas tienen la misma clave.",
  client_data_found: "Quedan datos del cliente. Corrígelos y vuelve a marcarla como revisada. No se ha guardado nada.",
};

export const PROMOTE_ERRORS: Record<string, string> = {
  unknown_guide: UNKNOWN_GUIDE,
  guide_not_reviewed: "Antes hay que revisarla: está sin revisar o archivada.",
  guide_already_promoted: "Esta guía ya se convirtió.",
  guide_key_taken: KEY_TAKEN,
  guide_label_taken: "Esa etiqueta ya tiene guía de Auphere.",
  client_data_found: "La guía guardada lleva datos del cliente. Corrígela y márcala otra vez como revisada. No se ha convertido nada.",
  twelve_tests_required: `La guía guardada no tiene sus ${TESTS_PER_SECTOR} pruebas. Corrígelas y vuelve a revisarla.`,
  invalid_test: "La API rechaza alguna prueba de la guía guardada. Corrígela y vuelve a revisarla.",
  invalid_guide: "La API rechaza la forma de la guía guardada. Corrígela y vuelve a revisarla.",
};

export type GuideFailure = { ok: false; error: string; code?: string; findings?: ClientDataFinding[] };
export type GuideResult<T> = { ok: true; data: T } | GuideFailure;

/**
 * A refusal of `review` or `promote`, in words. `client_data_found` brings
 * the findings, so the screen marks them in their place.
 */
export function guideFailure(status: number, body: unknown, action: "review" | "promote"): GuideFailure {
  const words = action === "review" ? REVIEW_ERRORS : PROMOTE_ERRORS;
  const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && "code" in detail) {
    const d = detail as { code: unknown; message?: unknown; findings?: unknown };
    const code = String(d.code);
    const error = words[code] ?? (typeof d.message === "string" ? d.message : code);
    return Array.isArray(d.findings)
      ? { ok: false, code, error, findings: d.findings as ClientDataFinding[] }
      : { ok: false, code, error };
  }
  if (status === 400) return { ok: false, error: "La API no reconoce tu sesión de operador para escribir. Vuelve a entrar en el panel." };
  if (status === 401) return { ok: false, error: loadErrorCopy(401) };
  if (status === 422) {
    return {
      ok: false,
      error:
        action === "promote"
          ? "Revisa la clave, la etiqueta y el motivo: la API no los acepta."
          : "Revisa la guía y las pruebas: la API no las acepta.",
    };
  }
  return { ok: false, error: `La API respondió ${status}. Vuelve a intentarlo en un momento.` };
}
