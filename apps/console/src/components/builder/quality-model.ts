import type { MessageKey } from "@/i18n/messages";
import { TEST_STOPS, type AgentTest, type ReviewFix, type TestStatus, type TestStop, type TestTurn } from "@/lib/backend/agent-quality-types";

import { POLL_FIRST_MS, nextDelay, type Result } from "./builder-model";

/**
 * Spec 047 (historias 8 y 9; T089 y T094) — lo que el probador, las pruebas,
 * la revisión y «Guardar» deciden sin pintar nada: la espera de un trabajo, la
 * hora simulada en la zona del negocio, cómo se agrupan y se nombran las
 * pruebas y adónde lleva cada arreglo. Puro: lo prueban los tests sin montar
 * la pantalla.
 */

type Job = { status: string; progress?: { step?: string | null } | null };

/**
 * Espera a que un trabajo termine (`done` o `failed`) con la espera creciente
 * de siempre (1, 2, 4… 10 s), que vuelve a 1 s cuando el trabajo cambia de
 * paso. `null` si se canceló; el último `Result` si la API dijo que no.
 */
export async function waitForJob<J extends Job>(
  poll: () => Promise<Result<J>>,
  opts: { wait: (ms: number) => Promise<void>; cancelled?: () => boolean; onUpdate?: (job: J) => void },
): Promise<Result<J> | null> {
  let delay = POLL_FIRST_MS;
  let step: string | null | undefined;
  for (;;) {
    await opts.wait(delay);
    if (opts.cancelled?.()) return null;
    const res = await poll();
    if (opts.cancelled?.()) return null;
    if (!res.ok) {
      if (res.status === 401 || res.status === 403 || res.status === 404) return res;
      delay = nextDelay(delay, false);
      continue;
    }
    opts.onUpdate?.(res.data);
    if (res.data.status === "done" || res.data.status === "failed") return res;
    const now = res.data.progress?.step;
    delay = nextDelay(delay, now !== step);
    step = now;
  }
}

/** «mar, 27 oct, 11:20» en la zona del negocio. */
export function simTimeLabel(now: string, timezone: string, locale: string): string {
  const at = new Date(now);
  if (Number.isNaN(at.getTime())) return now;
  try {
    return new Intl.DateTimeFormat(locale, {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: timezone,
    }).format(at);
  } catch {
    return at.toISOString();
  }
}

/** «Mar 11:20» en la zona del negocio: la hora del chat de prueba, como el prototipo. */
export function simTimeShort(now: string, timezone: string, locale: string): string {
  const at = new Date(now);
  if (Number.isNaN(at.getTime())) return now;
  try {
    const parts = new Intl.DateTimeFormat(locale, { weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: timezone }).formatToParts(at);
    const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
    const day = get("weekday").replace(/\.$/, "");
    return `${day.charAt(0).toUpperCase()}${day.slice(1)} ${get("hour")}:${get("minute")}`;
  } catch {
    return at.toISOString();
  }
}

/**
 * La hora de pared de la hora simulada, para el campo `datetime-local`: la API
 * la manda ya en la zona del negocio con su desfase (`2026-10-27T11:20:00+01:00`),
 * así que son sus primeros 16 caracteres. Sin desfase, se calcula en la zona.
 */
export function wallTime(now: string, timezone: string): string {
  const m = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/.exec(now);
  if (m && /([+-]\d{2}:\d{2})$/.test(now)) return m[1]!;
  const at = new Date(now);
  if (Number.isNaN(at.getTime())) return m?.[1] ?? "";
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: timezone,
    }).formatToParts(at);
    const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "00";
    return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
  } catch {
    return m?.[1] ?? "";
  }
}

/** Los grupos de la lista de pruebas, en este orden (21.1). */
export const TEST_KINDS = ["case", "sector", "person", "other"] as const;
export type TestKindGroup = (typeof TEST_KINDS)[number];

export function kindGroup(kind: string): TestKindGroup {
  return kind === "case" || kind === "sector" || kind === "person" ? kind : "other";
}

export function groupTests(tests: readonly AgentTest[]): { kind: TestKindGroup; tests: AgentTest[] }[] {
  return TEST_KINDS.map((kind) => ({ kind, tests: tests.filter((t) => kindGroup(t.kind) === kind) })).filter((g) => g.tests.length > 0);
}

export const STATUS_TONE: Record<TestStatus, "positive" | "warn" | "danger" | "info" | "muted"> = {
  passed: "positive",
  flaky: "warn",
  failed: "danger",
  unknown: "info",
  not_run: "muted",
  not_applicable: "muted",
};

/** Las que no pasan y hay que mirar: tienen «Por qué falló». */
export function isFailing(status: TestStatus): boolean {
  return status === "failed" || status === "flaky" || status === "unknown";
}

/**
 * La conversación que enseña «Por qué falló» (61.6): la de la prueba si la API
 * la manda en la prueba; si no, la de la primera pasada que falló (o, si
 * ninguna dice que falló, la primera con conversación). `null` sin conversación
 * guardada, como las pruebas de antes de la fase 27. Un motivo de parada que la
 * consola no conoce no se enseña.
 */
export function failedConversation(test: AgentTest): { transcript: TestTurn[]; stop: TestStop | null } | null {
  const stopOf = (stop: unknown): TestStop | null => ((TEST_STOPS as readonly unknown[]).includes(stop) ? (stop as TestStop) : null);
  if (test.transcript?.length) return { transcript: test.transcript, stop: stopOf(test.stop) };
  const attempts = (test.attempts ?? []).filter((a) => a.transcript?.length);
  const chosen = attempts.find((a) => a.passed === false) ?? attempts.find((a) => a.passed !== true);
  return chosen ? { transcript: chosen.transcript!, stop: stopOf(chosen.stop) } : null;
}

/**
 * Spec 047, enmienda del 2026-10-30 (65.8): la razón de una prueba que no
 * aplica, sin el «No aplica» con el que puede llegar, porque la pantalla ya lo
 * pone delante («No aplica: {razón}»).
 */
export function naReason(reason: string): string {
  return reason.replace(/^\s*no aplica\s*[:.,-]\s*/i, "").trim() || reason.trim();
}

/** Una prueba de la guía generada para este cliente: lleva «Generada» (58.4). */
export function isGenerated(test: Pick<AgentTest, "origin">): boolean {
  return test.origin === "generated";
}

const PARTS = new Set([
  "identity",
  "voice",
  "instructions",
  "procedures",
  "services",
  "skills",
  "tools",
  "connection_requests",
  "escalation",
  "rules",
  "team_access",
  "ai_disclosure",
  "model_policy",
  "memory",
  "reception",
  "prompt",
]);

/** `console:luis@…` → `luis@…`: el origen no es de la persona. */
export function cleanActor(actor: string): string {
  return actor.replace(/^[a-z_]+:/, "");
}

/** La clave de una parte del AgentSpec; `null` si la consola no tiene palabra para ella. */
export function partKey(part: string): MessageKey | null {
  return PARTS.has(part) ? (`builder.part.${part}` as MessageKey) : null;
}

/** Adónde lleva un arreglo «link» de la revisión y con qué palabras. */
export function reviewFixLink(refId: string, fix: Extract<ReviewFix, { kind: "link" }>): { href: string; label: MessageKey } | null {
  const base = `/clients/${encodeURIComponent(refId)}`;
  switch (fix.target) {
    case "integrations":
      return { href: `${base}/integrations`, label: "builder.review.fix.integrations" };
    case "business/services":
      return { href: `${base}/business#business-services`, label: "builder.review.fix.services" };
    case "business/hours":
      return { href: `${base}/business#business-hours`, label: "builder.review.fix.hours" };
    case "capabilities":
      return { href: `${base}/capabilities`, label: "builder.review.fix.capabilities" };
    case "channel":
      return { href: channelsHref(refId), label: "builder.review.fix.channel" };
    default:
      return null;
  }
}

/**
 * Los canales del cliente: donde «Guardar y conectar un canal» lleva después de
 * guardar (23.4). Cuando el agente tenga su propia pestaña de canales (historia
 * 10), cambia aquí.
 */
export function channelsHref(refId: string): string {
  return `/clients/${encodeURIComponent(refId)}/channels`;
}

/** ¿Sigue abierta la ventana de «Deshacer»? */
export function undoOpen(undoUntil: string | null | undefined, now: number = Date.now()): boolean {
  if (!undoUntil) return false;
  const at = Date.parse(undoUntil);
  return !Number.isNaN(at) && at > now;
}
