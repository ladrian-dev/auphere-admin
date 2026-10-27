/**
 * Spec 047 (T150, requisitos 40.13 y 54.2): the router's policy as the editor
 * shows it — one row per task — and back. Pure: what the operator does not
 * touch goes back exactly as it came, and nothing raises the ceilings of 40.10
 * (12 calls per turn, 3 escalations per hour). The API checks it all again.
 */
import type { ProfilePolicyJson, RouterPreview, TaskPolicyJson } from "@/lib/backend-models";

export const TIERS = ["basic", "medium", "top"] as const;
export const REASONING = ["none", "low", "medium", "high"] as const;

export const PROFILE_LABEL: Record<string, string> = {
  auto: "Automático",
  economy: "Económico",
  balanced: "Equilibrado",
  max: "Máximo",
  platform: "Plataforma",
};

export const TIER_LABEL: Record<string, string> = { basic: "Básica", medium: "Media", top: "Alta" };

export const OUTCOME_LABEL: Record<RouterPreview["outcome"], string> = {
  routed: "Elegido por el router",
  pinned: "Afinidad de la conversación",
  agent_pinned: "Modelo fijado del agente",
  reserve_model: "Modelo de reserva (anomalía)",
  no_model: "Sin modelo disponible",
};

export const ANOMALY_LABEL: Record<string, string> = {
  reserve_model: "Modelo de reserva",
  no_model: "Sin modelo disponible",
  cooldown: "Enfriado tras un fallo",
  missing_task: "Llamada sin tarea",
};

const REJECTION: Record<string, string> = {
  status: "No está activo",
  not_allowed: "Fuera de la lista permitida del partner",
  residency: "Fuera de la residencia del cliente",
  retention: "Sin retención cero comprobada",
  subprocessor: "Proveedor sin alta de subprocesador",
  sovereign: "Fuera de la restricción soberana",
  same_family: "De la misma familia que el modelo juzgado",
  cooldown: "Enfriado tras un fallo del proveedor",
  tier: "Fuera de la gama del escalado",
  not_certified: "Sin certificación por clase en la tarea",
  below_quality: "Por debajo de la calidad que pide el perfil",
  agent_not_certified: "Sin certificar para este agente",
  over_latency: "Por encima de la latencia p95 del perfil",
  unpriced: "Sin precio en vigor",
  over_cost: "Por encima del techo de coste por llamada",
  unknown: "No está en el catálogo",
  gone: "Ya no está entre los que pasan",
};

/** Why a deployment was discarded, in words; an unknown code, as it is. */
export function rejectionLabel(reason: string): string {
  if (reason.startsWith("capability:")) return `Le falta la capacidad «${reason.slice(11)}»`;
  if (reason.startsWith("agent_pinned:")) {
    return `El modelo fijado no pasa: ${rejectionLabel(reason.slice(13)).toLowerCase()}`;
  }
  return REJECTION[reason] ?? reason;
}

export const ERRORS: Record<string, string> = {
  over_ceiling: "Un perfil puede bajar los techos (12 llamadas por turno, 3 escalados por hora), nunca subirlos.",
  unknown_task: "Hay una tarea que no está en la taxonomía vigente.",
  unknown_reserve: "El modelo de reserva no está en el catálogo.",
  bad_policy: "La política no es válida.",
  no_tasks: "El perfil necesita al menos una tarea.",
  unknown_profile: "Ese perfil no existe.",
  unknown_agent: "Ese agente no tiene versión publicada en ese cliente.",
  no_policy: "Ese perfil no fija esa tarea.",
};

export type TaskRow = {
  task: string;
  min_quality: string;
  max_cost: string;
  escalate_to: string;
  reasoning: string;
  judge_sampling: string;
  reserve: string;
};

export type Limits = {
  max_calls_per_turn: string;
  max_escalations_per_hour: string;
  turn_cost_ceiling_micros: string;
};

const text = (v: unknown): string => (v === null || v === undefined ? "" : String(v));

export function rowsFromPolicy(policy: ProfilePolicyJson): TaskRow[] {
  return Object.entries(policy.tasks).map(([task, t]) => ({
    task,
    min_quality: text(t.min_quality),
    max_cost: text(t.max_cost_per_call_micros),
    escalate_to: text(t.escalate_to),
    reasoning: t.reasoning ?? "none",
    judge_sampling: text(t.judge_sampling),
    reserve: text(t.reserve),
  }));
}

export function limitsFromPolicy(policy: ProfilePolicyJson): Limits {
  return {
    max_calls_per_turn: text(policy.max_calls_per_turn),
    max_escalations_per_hour: text(policy.max_escalations_per_hour),
    turn_cost_ceiling_micros: text(policy.turn_cost_ceiling_micros),
  };
}

function number(raw: string): number | null {
  const value = Number(raw.trim().replace(",", "."));
  return raw.trim() === "" || !Number.isFinite(value) ? null : value;
}

export type CheckedPolicy =
  | { ok: true; policy: ProfilePolicyJson }
  | { ok: false; errors: Record<string, string> };

/** The edited rows back into the policy; everything else of `base` stays. */
export function policyFromRows(
  base: ProfilePolicyJson,
  rows: TaskRow[],
  limits: Limits,
  ceilings: Record<string, number>,
): CheckedPolicy {
  const errors: Record<string, string> = {};
  const tasks: Record<string, TaskPolicyJson> = {};
  for (const row of rows) {
    const key = (field: string) => `${row.task}.${field}`;
    const quality = number(row.min_quality);
    if (quality === null || quality < 0 || quality > 1) errors[key("min_quality")] = "Entre 0 y 1.";
    const cost = row.max_cost.trim() === "" ? null : number(row.max_cost);
    if (row.max_cost.trim() !== "" && (cost === null || cost < 0 || !Number.isInteger(cost))) {
      errors[key("max_cost")] = "Micro-USD enteros, cero o más.";
    }
    const tier = row.escalate_to.trim();
    if (tier && !(TIERS as readonly string[]).includes(tier)) errors[key("escalate_to")] = "Básica, media o alta.";
    if (!(REASONING as readonly string[]).includes(row.reasoning)) errors[key("reasoning")] = "none, low, medium o high.";
    const sampling = row.judge_sampling.trim();
    let judge: string | number | null = null;
    if (sampling === "by_risk") judge = "by_risk";
    else if (sampling) {
      const fraction = number(sampling);
      if (fraction === null || fraction < 0 || fraction > 1) errors[key("judge_sampling")] = "by_risk o una fracción entre 0 y 1.";
      else judge = fraction;
    }
    tasks[row.task] = {
      ...(base.tasks[row.task] ?? {}),
      min_quality: quality ?? 0,
      max_cost_per_call_micros: cost,
      escalate_to: tier || null,
      reasoning: row.reasoning,
      judge_sampling: judge,
      reserve: row.reserve.trim() || null,
    };
  }
  const out: ProfilePolicyJson = { ...base, tasks };
  for (const field of ["max_calls_per_turn", "max_escalations_per_hour"] as const) {
    const value = number(limits[field]);
    const ceiling = ceilings[field] ?? Number.POSITIVE_INFINITY;
    if (value === null || !Number.isInteger(value) || value < 0 || value > ceiling) {
      errors[field] = `Entre 0 y ${ceiling}: un perfil baja el techo, no lo sube.`;
    } else out[field] = value;
  }
  const ceiling = limits.turn_cost_ceiling_micros.trim();
  if (ceiling === "") out.turn_cost_ceiling_micros = null;
  else {
    const value = number(ceiling);
    if (value === null || value < 0 || !Number.isInteger(value)) errors.turn_cost_ceiling_micros = "Micro-USD enteros.";
    else out.turn_cost_ceiling_micros = value;
  }
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, policy: out };
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const isUuid = (value: string): boolean => UUID.test(value.trim());
