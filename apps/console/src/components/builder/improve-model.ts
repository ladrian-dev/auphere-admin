import type { BlockChartColumn } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";
import type { AgentPerformance, Improvement, PerformancePeriod } from "@/lib/backend/agent-improve-types";
import { PERFORMANCE_PERIODS } from "@/lib/backend/agent-improve-types";
import type { AgentSpec } from "@/lib/backend/builder-types";

/**
 * Spec 047 (T174, T178) — las cuentas puras del Rendimiento, las Mejoras y la
 * Recepción de un agente: las columnas de la gráfica, las palabras de cada
 * motivo de traspaso (`events.md` §2), cuánto duró una conversación, el resumen
 * de una mejora y la sección Recepción del AgentSpec. Sin React: se prueban solas.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const DAY_LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" });
const DAY_NUM = new Intl.DateTimeFormat("es-ES", { day: "numeric", timeZone: "UTC" });
const WEEKDAY = new Intl.DateTimeFormat("es-ES", { weekday: "short", timeZone: "UTC" });
const asDate = (iso: string) => new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);

/** `?days=` de la URL o del estado: 7, 30 o 90; cualquier otra cosa, 30 (51.1). */
export function performancePeriod(raw: number | string | null | undefined): PerformancePeriod {
  const n = Number(raw);
  return (PERFORMANCE_PERIODS as readonly number[]).includes(n) ? (n as PerformancePeriod) : 30;
}

/** Las columnas de «Conversaciones por día»: resueltas sin persona y pasadas a una persona. */
export function performanceColumns(t: T, perf: Pick<AgentPerformance, "series">): BlockChartColumn[] {
  const n = perf.series.length;
  return perf.series.map((d, i) => {
    const date = asDate(d.day);
    const title = DAY_LONG.format(date);
    return {
      key: d.day,
      label: i === n - 1 ? t("money.chart.today") : n <= 7 ? WEEKDAY.format(date) : DAY_NUM.format(date),
      title: title.charAt(0).toUpperCase() + title.slice(1),
      values: [d.resolved_without_person, d.handed_to_person],
    };
  });
}

/** «45 s», «3 min», «1 h 20 min». `null` si la API no la sabe. */
export function durationText(t: T, seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return t("improve.duration.seconds", { n: Math.round(seconds) });
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return t("improve.duration.minutes", { n: minutes });
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? t("improve.duration.hoursMinutes", { h, m }) : t("improve.duration.hours", { h });
}

const REASONS = new Set([
  "no_balance",
  "agent_cap",
  "paused_agent",
  "paused_channel",
  "paused_client",
  "archived_client",
  "channel_problem",
  "agent_unpublished",
  "no_model",
  "provider_failure",
  "turn_limit",
  "escalated",
  "human_takeover",
  "reception_loop",
  "taken_by_person",
]);

/** El motivo del traspaso, en palabras (`events.md` §2); un código nuevo, «Otro motivo». */
export function reasonKey(code: string | null): MessageKey | null {
  if (!code) return null;
  return (REASONS.has(code) ? `waiting.reason.${code}` : "waiting.reason.other") as MessageKey;
}

/** «WhatsApp», o el tipo tal cual si es otro. */
export function channelLabel(t: T, type: string | null): string {
  if (!type) return "—";
  return type === "whatsapp" ? t("lite.agents.channel.whatsapp") : type;
}

/** «12 conversaciones de 9 clientes» de una sugerencia; una corrección viene de una sola. */
export function improvementReach(t: T, item: Pick<Improvement, "kind" | "conversations_count" | "contacts_count">): string {
  if (item.kind === "correction") return t("improve.reach.correction");
  return t("improve.reach", { conversations: item.conversations_count, contacts: item.contacts_count });
}

/** «Desde la web» o «Desde la app»: de dónde mandó la persona del cliente su corrección. */
export function originKey(origin: string | null): MessageKey {
  if (origin === "app") return "improve.origin.app";
  if (origin === "lite_web") return "improve.origin.web";
  return "improve.origin.other";
}

// ── Recepción (requisito 53) ────────────────────────────────────────────────

export type ReceptionTarget = { agent_id: string; when: string };
export type Reception = { enabled: boolean; targets?: ReceptionTarget[] };

/** Los límites del esquema (`ReceptionTarget.when` y `Reception.targets`). */
export const RECEPTION_LIMITS = { when: 300, targets: 10 } as const;

/** La sección Recepción del AgentSpec, leída con cuidado: sin ella, apagada y sin destinos. */
export function receptionOf(spec: AgentSpec | null | undefined): Reception {
  const raw = spec?.reception;
  if (!raw || typeof raw !== "object") return { enabled: false, targets: [] };
  const section = raw as { enabled?: unknown; targets?: unknown };
  const targets = Array.isArray(section.targets)
    ? section.targets.flatMap((x) => {
        if (!x || typeof x !== "object") return [];
        const item = x as { agent_id?: unknown; when?: unknown };
        return typeof item.agent_id === "string" ? [{ agent_id: item.agent_id, when: typeof item.when === "string" ? item.when : "" }] : [];
      })
    : [];
  return { enabled: section.enabled === true, targets };
}

export type ReceptionProblem = "no_targets" | "when_required" | "when_too_long" | "too_many";

/**
 * ¿Se puede guardar? Encendida necesita al menos un destino, cada destino su
 * «cuándo» (1 a 300 caracteres) y como mucho 10 (los mismos límites que la API).
 */
export function receptionProblems(reception: Reception): { problem: ReceptionProblem; agent_id?: string }[] {
  const out: { problem: ReceptionProblem; agent_id?: string }[] = [];
  const targets = reception.targets ?? [];
  if (!reception.enabled) return out;
  if (!targets.length) out.push({ problem: "no_targets" });
  if (targets.length > RECEPTION_LIMITS.targets) out.push({ problem: "too_many" });
  for (const target of targets) {
    const when = target.when.trim();
    if (!when) out.push({ problem: "when_required", agent_id: target.agent_id });
    else if (when.length > RECEPTION_LIMITS.when) out.push({ problem: "when_too_long", agent_id: target.agent_id });
  }
  return out;
}

/** Lo que se guarda: los «cuándo» sin espacios de más; apagada, sin destinos (no deriva). */
export function receptionPayload(reception: Reception): Reception {
  if (!reception.enabled) return { enabled: false };
  return {
    enabled: true,
    targets: (reception.targets ?? []).map((target) => ({ agent_id: target.agent_id, when: target.when.split(/\s+/).filter(Boolean).join(" ") })),
  };
}
