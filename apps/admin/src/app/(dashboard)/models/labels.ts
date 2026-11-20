/**
 * Spec 047 (T150): the words and the pure rules of the catalog screen —
 * labels, formats and the validation of what the operator types before it
 * goes to the API. The API validates again; this only spares a round trip and
 * says what is wrong next to the field.
 */
import type { StatusBadgeTone } from "@nexus/ui";

import type {
  DeploymentIn,
  DeploymentRow,
  DeploymentStatus,
  ModelUses,
  PriceContract,
  PriceIn,
  ProposalOut,
  Residency,
  SaleInfo,
  SaleLaneKey,
  SalePolicy,
  SalePolicyIn,
  WeightsIn,
  WeightValues,
} from "@/lib/backend-models";

export const STATUS_LABEL: Record<DeploymentStatus, string> = {
  draft: "Borrador",
  certifying: "Certificando",
  active: "Activo",
  retiring: "En retirada",
  retired: "Retirado",
  unavailable: "No disponible",
  deprecated: "Antiguo",
};

export const STATUS_TONE: Record<DeploymentStatus, StatusBadgeTone> = {
  draft: "muted",
  certifying: "info",
  active: "positive",
  retiring: "warning",
  retired: "muted",
  unavailable: "danger",
  deprecated: "muted",
};

/** The filters of the list, in the order an operator looks for things. */
export const STATUS_FILTERS: { key: DeploymentStatus | "all"; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "active", label: "Activos" },
  { key: "draft", label: "Borradores" },
  { key: "retiring", label: "En retirada" },
  { key: "unavailable", label: "No disponibles" },
];

export const RESIDENCY_LABEL: Record<Residency, string> = {
  eu: "UE",
  us: "EE. UU.",
  global: "Global",
};

/** What a refusal of the API means, in words. */
export const ERRORS: Record<string, string> = {
  activation_rejected: "No se puede activar todavía.",
  license_excluded:
    "La licencia no permite ofrecer el modelo como servicio (Llama 4, Qwen3.8-Flash-Next y AGPL están excluidas). La razón queda en la auditoría.",
  unknown_retention: "Esa forma de forzar la retención cero no la sabe aplicar el transporte.",
  partial_weights: "Los pesos van los tres o ninguno.",
  deployment_exists: "Ya hay un despliegue con esa clave.",
  bad_capabilities: "Las capacidades no son válidas.",
  in_the_past: "La fecha de retirada ya pasó.",
  naive_date: "La fecha necesita su zona horaria.",
  not_servable: "Un modelo retirado o no disponible no se puede retirar otra vez.",
  unknown_deployment: "Ese modelo ya no existe.",
  reason_required: "Hace falta el motivo.",
  // Spec 059 (contrato §2, §4–§6).
  model_in_use: "El modelo está en uso: no cambia de estado.",
  defaults_unverified: "No se puede comprobar qué modelos usa el worker: el modelo no cambia de estado.",
  not_retiring: "El modelo ya no está en retirada.",
  not_unavailable: "El modelo ya no está «No disponible».",
  per_minute: "Este modelo se cobra por minuto: no tiene pesos por carril.",
  below_floor: "Algún carril queda por debajo del suelo.",
  // Spec 065: el cuarto carril.
  no_write_tariff: "Este modelo no cobra la escritura en caché: su peso va a 0.",
  // Spec 065: habilitar para responder y el modelo por defecto de los agentes.
  no_respond_profile: "Este modelo no tiene perfil de llamada: no se puede habilitar para responder.",
  not_active: "Solo se puede habilitar para responder un modelo activo.",
  note_required: "Hace falta la pasada de la batería.",
  unknown_model: "Ese modelo no está habilitado para responder en este entorno. Recarga la página y elige otro.",
};

/** The same codes, said of a cost (contrato §3): `in_the_past` is its date, not a retirement's. */
export const PRICE_ERRORS: Record<string, string> = {
  ...ERRORS,
  in_the_past: "Un coste no puede entrar en vigor antes de hoy (UTC): lo ya cobrado no se recalcula.",
};

/** Said of the target multiplier (contrato §7): its `below_floor` is the multiplier's. */
export const POLICY_ERRORS: Record<string, string> = {
  ...ERRORS,
  below_floor: "El multiplicador objetivo no puede ser menor que 1,5, el suelo.",
};

/** The lanes of a model priced by tokens, in the order the partner reads a price. */
export const LANES: readonly SaleLaneKey[] = ["input", "cache_read", "output", "cache_write"];

/** The three every model priced by tokens weighs (spec 007). */
const REQUIRED_LANES: readonly SaleLaneKey[] = ["input", "cache_read", "output"];

export const LANE_LABEL: Record<SaleLaneKey, string> = {
  input: "Entrada",
  cache_read: "Caché",
  output: "Salida",
  cache_write: "Escritura en caché",
};

/**
 * Spec 059 (1.1): the uses of the registry of defaults (research D1), in
 * words. The registry is open: a use it adds tomorrow is shown by its code
 * until it gets its words here.
 */
export const DEFAULT_USE_LABEL: Record<string, string> = {
  respond: "responder",
  respond_fallback: "reserva de responder",
  classify: "clasificar",
  classify_fallback: "reserva de clasificar",
  booking_brake: "freno de reservas",
  outcome_grader: "calificar resultados",
  extract: "extraer datos",
  simulation: "simular",
  qa_classify: "clasificar en el Playground QA",
  qa_respond: "responder en el Playground QA",
  improve: "mejorar agentes",
  companion: "companion",
  transcribe: "transcribir audios",
  vision: "ver imágenes",
  console_fallback: "reserva de la consola",
  partner_default: "modelo por defecto de los partners",
  evals_classify: "clasificar en las evaluaciones",
  evals_respond: "responder en las evaluaciones",
  evals_fallback: "reserva de las evaluaciones",
  evals_judge: "juzgar en las evaluaciones",
  evals_companion: "companion de las evaluaciones",
  knowledge_embedding: "indexar el conocimiento",
  build: "construir agentes",
  read_source: "leer fuentes",
  sector: "identificar el sector",
  customer_sim: "simular clientes",
  judge: "juzgar las pruebas",
  degraded: "turnos degradados",
  // Spec 065: el modelo por defecto de Auphere y la reserva de cada familia.
  agent_default: "los agentes sin modelo elegido",
  respond_fallback_openai: "reserva de los modelos de OpenAI",
  respond_fallback_anthropic: "reserva de los modelos de Anthropic",
};

export function useLabel(code: string): string {
  return DEFAULT_USE_LABEL[code] ?? code;
}

/** «a», «a y b», «a, b y c». */
export function joinEs(items: readonly string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`;
}

const agentsWord = (n: number) => (n === 1 ? "1 agente" : `${n} agentes`);

/**
 * In use (research D3): a default of the platform, an agent answering with it,
 * or a client's assignment in any role. The panel does not offer «Retirar» nor
 * «No disponible» on it; the API refuses them anyway (1.4).
 */
export function isInUse(uses: ModelUses): boolean {
  // Spec 059: an older API sends no uses and does not protect — nothing destructive.
  if (uses.problem === "api_outdated") return true;
  return uses.defaults.length > 0 || uses.agents > 0 || uses.clients.length > 0;
}

/** The two lines under a model in use: its defaults, and who answers with it. */
export function usesLines(uses: Pick<ModelUses, "defaults" | "agents" | "clients"> & Partial<Pick<ModelUses, "problem">>): {
  defaults: string | null;
  agents: string | null;
} {
  const outdated = "problem" in uses && uses.problem === "api_outdated";
  const defaults = outdated
    ? "La API todavía no dice si está en uso"
    : uses.defaults.length
      ? `Por defecto para ${joinEs(uses.defaults.map(useLabel))}`
      : null;
  let agents: string | null = null;
  if (uses.agents > 0) {
    agents = uses.clients.length
      ? `${agentsWord(uses.agents)} de ${joinEs(uses.clients)}`
      : agentsWord(uses.agents);
  } else if (uses.clients.length) {
    agents = `Asignado por ${joinEs(uses.clients)}`;
  }
  return { defaults, agents };
}

/** «Retirada detenida (N agentes)» (1.8); nothing without agents inside. */
export function blockedLabel(agents: number | null): string | null {
  return agents ? `Retirada detenida (${agentsWord(agents)})` : null;
}

const PROBLEM: Record<string, string> = {
  no_heartbeat: "no hay ningún worker en marcha que publique los modelos que usa",
  unpublished: "el worker en marcha no publica los modelos que usa; puede ser una versión anterior, en pleno despliegue",
  mismatch: "lo que publica el worker no coincide con lo que conoce la API",
  api_outdated: "la API todavía es de una versión anterior, en pleno despliegue",
};

export function problemWords(problem: string | null | undefined): string {
  return (problem && PROBLEM[problem]) || "el worker no responde como se espera";
}

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];

/**
 * The refusals whose detail carries more than a code (contrato §2, §6): the
 * uses of a model in use, why the worker's models could not be checked, the
 * lanes under the floor. `null` leaves the sentence to the table of errors.
 */
export function refusalWords(detail: { code: string } & Record<string, unknown>): string | null {
  if (detail.code === "model_in_use") {
    // Spec 065: «Deshabilitar para responder» dice los suyos en `uses`.
    const defaults = strings(detail.defaults ?? detail.uses);
    const agents = typeof detail.agents === "number" ? detail.agents : 0;
    const clients = strings(detail.clients);
    const parts = [
      defaults.length ? `por defecto para ${joinEs(defaults.map(useLabel))}` : null,
      agents > 0
        ? `responden con él ${agentsWord(agents)}${clients.length ? ` de ${joinEs(clients)}` : ""}`
        : clients.length
          ? `lo tiene asignado ${joinEs(clients)}`
          : null,
    ].filter(Boolean);
    return `El modelo está en uso${parts.length ? `: ${parts.join("; ")}` : ""}. Por eso no cambia de estado.`;
  }
  if (detail.code === "defaults_unverified") {
    return `No se puede comprobar qué modelos usa la plataforma: ${problemWords(
      typeof detail.problem === "string" ? detail.problem : null,
    )}. Por seguridad, el modelo no cambia de estado; vuelve a intentarlo en un minuto.`;
  }
  if (detail.code === "below_floor") {
    const lanes = strings(detail.lanes).map((l) => (LANE_LABEL[l as SaleLaneKey] ?? l).toLowerCase());
    if (!lanes.length) return null;
    return `La venta queda por debajo de 1,5 veces el coste en ${joinEs(lanes)}.`;
  }
  return null;
}

/** What the «⋯» menu of a row offers (1.3, 1.6, 1.7, 4.2). */
export type RowMenu = {
  weights: boolean;
  activate: boolean;
  cancelRetirement: boolean;
  restore: boolean;
  retire: boolean;
  unavailable: boolean;
  /** Spec 065: «Habilitar para responder» and «Deshabilitar para responder». */
  respondEnable: boolean;
  respondDisable: boolean;
};

/**
 * Spec 065: whether the model can answer the agents in this environment.
 * `unknown` is an API that does not say it yet (no field): the panel claims
 * nothing and offers nothing. Without a call profile it cannot be enabled.
 */
export type RespondState = "unknown" | "no_profile" | "disabled" | "enabled";

export function respondState(row: DeploymentRow): RespondState {
  if (row.respond_enabled_at === undefined) return "unknown";
  if (row.respond_enabled_at !== null) return "enabled";
  return row.has_respond_profile ? "disabled" : "no_profile";
}

/**
 * Spec 065 (1.4): the uses that keep a model enabled — Auphere's default for the
 * agents and the reserve of each family. «Deshabilitar» is not offered on them;
 * the API refuses it anyway (`409 model_in_use`).
 */
const RESPOND_USES: ReadonlySet<string> = new Set(["agent_default", "respond_fallback_openai", "respond_fallback_anthropic"]);

export function rowMenu(row: DeploymentRow, routerVisible: boolean): RowMenu {
  const status = row.deployment.status;
  const free = !isInUse(row.uses);
  const respond = respondState(row);
  return {
    weights: row.sale.state !== "per_minute" && status !== "retired",
    activate: routerVisible && status !== "active" && status !== "retired" && status !== "retiring",
    cancelRetirement: status === "retiring",
    restore: status === "unavailable",
    retire: free && status === "active",
    unavailable: free && status !== "unavailable" && status !== "retired",
    // The API only enables an active model (`422` otherwise).
    respondEnable: respond === "disabled" && status === "active",
    respondDisable: respond === "enabled" && !row.uses.defaults.some((use) => RESPOND_USES.has(use)),
  };
}

const MONEY = new Intl.NumberFormat("es", { style: "currency", currency: "USD", maximumFractionDigits: 4 });

/** «0,11 US$ entrada · 0,55 US$ salida», per million tokens; or the minute. */
export function formatPrice(price: PriceContract | null): string {
  if (price === null) return "Sin precio";
  const parts: string[] = [];
  if (price.input !== null) parts.push(`${MONEY.format(price.input)} entrada`);
  if (price.output !== null) parts.push(`${MONEY.format(price.output)} salida`);
  if (price.cache_read !== null) parts.push(`${MONEY.format(price.cache_read)} caché`);
  if (price.audio_minute != null) parts.push(`${MONEY.format(price.audio_minute)} el minuto`);
  return parts.length ? parts.join(" · ") : "Sin tarifas";
}

export function proposalLabel(p: ProposalOut): string {
  return p.proposed === "auto" ? "«Automático»" : p.proposed;
}

const KEY = /^[a-z0-9][a-z0-9._:/-]{2,120}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export type NewDeploymentForm = {
  id: string;
  display_name: string;
  model: string;
  provider: string;
  family: string;
  route: string;
  region: string;
  residency: Residency;
  license_id: string;
  license_url: string;
  capabilities: string;
  reason: string;
};

export type Checked<T> = { ok: true; body: T } | { ok: false; errors: Record<string, string> };

/** The draft as the API takes it: always `draft`, without retention or
 * contract until someone checks them (research D44). */
export function newDeploymentBody(form: NewDeploymentForm): Checked<DeploymentIn> {
  const errors: Record<string, string> = {};
  const id = form.id.trim();
  if (!KEY.test(id)) errors.id = "Minúsculas, números y . _ : / -, entre 3 y 121 caracteres.";
  if (!form.display_name.trim()) errors.display_name = "Hace falta un nombre.";
  if (!form.model.trim()) errors.model = "Hace falta el modelo.";
  if (!form.provider.trim()) errors.provider = "Hace falta el proveedor.";
  if (!form.reason.trim()) errors.reason = "Hace falta el motivo.";
  let capabilities: Record<string, unknown> = {};
  if (form.capabilities.trim()) {
    try {
      const parsed: unknown = JSON.parse(form.capabilities);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error();
      capabilities = parsed as Record<string, unknown>;
    } catch {
      errors.capabilities = "Un objeto JSON, por ejemplo {\"tools\": true, \"tier\": \"basic\"}.";
    }
  }
  const licenseId = form.license_id.trim();
  if (Object.keys(errors).length) return { ok: false, errors };
  return {
    ok: true,
    body: {
      id,
      display_name: form.display_name.trim(),
      model: form.model.trim(),
      provider: form.provider.trim(),
      family: form.family.trim() || null,
      route: form.route.trim() || null,
      region: form.region.trim() || null,
      residency: form.residency,
      retention: { zero: false, how: null },
      license: licenseId ? { id: licenseId, url: form.license_url.trim() || null, read_at: null } : null,
      contract: { dpa: false, subprocessor_listed: false },
      capabilities,
      reason: form.reason.trim(),
    },
  };
}

export type PriceForm = {
  valid_from: string;
  input: string;
  cache_read: string;
  cache_write: string;
  output: string;
  audio_minute: string;
  source: string;
  currency: string;
};

const TARIFFS = ["input", "cache_read", "cache_write", "output", "audio_minute"] as const;

function decimal(raw: string): number | null | "bad" {
  const text = raw.trim().replace(",", ".");
  if (!text) return null;
  const value = Number(text);
  return Number.isFinite(value) && value >= 0 ? value : "bad";
}

/**
 * A cost enters with its date and its source (41.1). Spec 059 (4.4): never
 * before today, judged by the UTC day as the API does.
 */
export function priceBody(form: PriceForm, today: string = todayUtc()): Checked<PriceIn> {
  const errors: Record<string, string> = {};
  if (!DAY.test(form.valid_from)) errors.valid_from = "La fecha de vigencia, AAAA-MM-DD.";
  else if (form.valid_from < today)
    errors.valid_from = "No puede entrar en vigor antes de hoy (UTC): lo ya cobrado no se recalcula.";
  if (!/^https?:\/\/\S{4,}$/.test(form.source.trim())) errors.source = "El enlace de donde sale el precio.";
  if (!/^[A-Z]{3}$/.test(form.currency)) errors.currency = "Tres letras, como USD.";
  const body: PriceIn = { valid_from: form.valid_from, source: form.source.trim(), currency: form.currency };
  let any = false;
  for (const key of TARIFFS) {
    const value = decimal(form[key]);
    if (value === "bad") errors[key] = "Un número mayor o igual que cero.";
    else if (value !== null) {
      body[key] = value;
      any = true;
    }
  }
  if (!any && !errors.input) errors.input = "Al menos una tarifa.";
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, body };
}

/** «Retirar» takes a day; the deployment keeps serving until 00:00 UTC of it. */
export function retireAfterIso(day: string): string | null {
  return DAY.test(day) ? `${day}T00:00:00+00:00` : null;
}

// ── Spec 059: the sale of each model (historias 3 y 4) ──────────────────────

const AMOUNT = new Intl.NumberFormat("es", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const TIMES = new Intl.NumberFormat("es", { maximumFractionDigits: 2 });

const asNumber = (value: string | number | null | undefined): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(String(value).replace(",", "."));
  return Number.isFinite(n) ? n : null;
};

/** «4,00», «0,088»: an amount per million, without its currency (the column says it). */
export function formatAmount(value: string | number | null | undefined): string {
  const n = asNumber(value);
  return n === null ? "—" : AMOUNT.format(n);
}

/** «2,2×». */
export function formatMultiplier(value: string | number | null | undefined): string {
  const n = asNumber(value);
  return n === null ? "—" : `${TIMES.format(n)}×`;
}

/** «Hoy» as the API judges a cost's date: the UTC day. */
export function todayUtc(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

// BigInt() and not `n` literals: the panel compiles to a target before ES2020.
const MICRO = BigInt(1_000_000);
const ZERO = BigInt(0);
const TWO = BigInt(2);

/**
 * A decimal (`NUMERIC(12,6)`) in millionths, so that the floor is checked
 * without floating point: «0,06 × 10 = 1,5 × 0,4» holds exactly.
 */
export function toMicros(value: string | number | null | undefined): bigint | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim().replace(",", ".");
  const match = /^(\d+)(?:\.(\d{1,6}))?$/.exec(text);
  if (!match) return null;
  return BigInt(match[1]!) * MICRO + BigInt((match[2] ?? "").padEnd(6, "0"));
}

/** Millionths back to a decimal with a dot and no trailing zeros: «0.88». */
export function fromMicros(micros: bigint): string {
  const whole = micros / MICRO;
  const frac = (micros % MICRO).toString().padStart(6, "0").replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : `${whole}`;
}

/** What the API writes («0.880000») as a person types it («0,88»). */
export function decimalText(value: string | number | null | undefined): string {
  const n = asNumber(value);
  return n === null ? "" : String(n).replace(".", ",");
}

/** `weight × sell ÷ cost`, for showing; `null` without a cost to divide by. */
export function laneMultiplier(
  cost: string | number | null | undefined,
  weight: string | number | null | undefined,
  sell: string | number,
): number | null {
  const c = asNumber(cost);
  const w = asNumber(weight);
  const s = asNumber(sell);
  if (c === null || w === null || s === null || c <= 0) return null;
  return (w * s) / c;
}

/** A lane under the floor: `weight × sell < floor × cost` (3.4). Without a cost there is no floor. */
export function belowFloor(
  cost: string | number | null | undefined,
  weight: string | number | null | undefined,
  policy: Pick<SalePolicy, "floor" | "sell_usd_per_million">,
): boolean {
  const c = toMicros(cost);
  const w = toMicros(weight);
  const f = toMicros(policy.floor);
  const s = toMicros(policy.sell_usd_per_million);
  if (c === null || w === null || f === null || s === null || c === ZERO) return false;
  return w * s < f * c;
}

export type LaneValues = Partial<Record<SaleLaneKey, string | number | null>>;

/** Spec 065: does the model bill cache writes? Then its sale has a fourth lane. */
export function billsWrites(costs: LaneValues): boolean {
  const c = asNumber(costs.cache_write);
  return c !== null && c > 0;
}

/**
 * The lanes a model weighs: the three, and the cache write when it has a tariff
 * (spec 065). Without one, the meter keeps the write inside the input, as before,
 * and the panel does not show a lane that charges nothing.
 */
export function lanesFor(costs: LaneValues): SaleLaneKey[] {
  return billsWrites(costs) ? [...LANES] : [...REQUIRED_LANES];
}

/** The lanes worth naming in a line of weights: the write only when it weighs something. */
export function weightLanes(weights: LaneValues): SaleLaneKey[] {
  const w = asNumber(weights.cache_write);
  return w !== null && w > 0 ? [...LANES] : [...REQUIRED_LANES];
}

/**
 * The weights of a multiplier over a cost: `round(m × cost ÷ sell, 6)`, as the
 * API proposes them (research D8). `null` without the multiplier or a lane's cost.
 */
export function proposalFor(
  costs: LaneValues,
  multiplier: string | number | null | undefined,
  sell: string | number,
): WeightValues | null {
  const m = toMicros(multiplier);
  const s = toMicros(sell);
  if (m === null || s === null || s === ZERO) return null;
  const out: Partial<Record<SaleLaneKey, string>> = {};
  for (const lane of lanesFor(costs)) {
    const c = toMicros(costs[lane]);
    if (c === null) return null;
    out[lane] = fromMicros((m * c + s / TWO) / s);
  }
  return out as WeightValues;
}

/**
 * The same decimals, whatever their trailing zeros. A missing cache-write weight
 * reads as 0, as the meter charges it on a model without a write tariff.
 */
export function sameWeights(a: LaneValues | null, b: LaneValues | null): boolean {
  if (!a || !b) return false;
  return LANES.every((lane) => {
    const pick = (v: LaneValues) => (lane === "cache_write" ? (v[lane] ?? 0) : v[lane]);
    const x = toMicros(pick(a));
    return x !== null && x === toMicros(pick(b));
  });
}

/** The cost of each lane in force: the API's lanes, else the current price. */
export function laneCosts(row: DeploymentRow): LaneValues {
  const price = row.current_price;
  const out: LaneValues = {};
  for (const lane of LANES) out[lane] = row.sale.lanes?.[lane]?.cost ?? price?.[lane] ?? null;
  return out;
}

/** The weights of each lane today: the API's lanes, else the meter's. */
export function currentWeights(row: DeploymentRow): LaneValues {
  const meter = row.deployment.meter_weights;
  const fallback: LaneValues = {
    input: meter.w_in,
    cache_read: meter.w_cache,
    output: meter.w_out,
    cache_write: meter.w_cache_write ?? null,
  };
  const out: LaneValues = {};
  for (const lane of LANES) out[lane] = row.sale.lanes?.[lane]?.weight ?? fallback[lane] ?? null;
  return out;
}

export type ChipTone = StatusBadgeTone;

const SALE_CHIP: Record<SaleInfo["state"], { label: string; tone: ChipTone }> = {
  on_target: { label: "En el objetivo", tone: "positive" },
  drift: { label: "Desfasado", tone: "warning" },
  below_floor: { label: "Bajo el suelo", tone: "danger" },
  unweighted: { label: "Sin pesos", tone: "warning" },
  per_minute: { label: "Por minuto", tone: "muted" },
  no_cost: { label: "Sin coste", tone: "muted" },
  unknown: { label: "Sin objetivo", tone: "muted" },
};

/**
 * The chip of the sale (3.8, 3.11). Without the target multiplier (4.7) the
 * panel does not say whether a model is on target or behind it.
 */
export function saleChip(sale: SaleInfo, targetKnown: boolean): { label: string; tone: ChipTone } | null {
  if (sale.state === "unknown") return null;
  if (!targetKnown && (sale.state === "on_target" || sale.state === "drift")) return null;
  return SALE_CHIP[sale.state];
}

/** The cost dialog starts from the cost in force and today (4.3). */
export function priceFormFrom(row: DeploymentRow, today: string): PriceForm {
  const p = row.current_price;
  return {
    valid_from: today,
    input: decimalText(p?.input),
    cache_read: decimalText(p?.cache_read),
    cache_write: decimalText(p?.cache_write),
    output: decimalText(p?.output),
    audio_minute: decimalText(p?.audio_minute),
    source: p?.source ?? "",
    currency: p?.currency ?? "USD",
  };
}

export type WeightsForm = Record<Exclude<SaleLaneKey, "cache_write">, string> & {
  cache_write?: string;
  reason: string;
};

/**
 * The weights as the API takes them (contrato §6): the three, greater than
 * zero, none of them under the floor of its lane (3.4, 3.5), with a reason.
 * Spec 065: and the cache write on a model that bills it. The API checks it all
 * again.
 */
export function checkWeights(form: WeightsForm, costs: LaneValues, policy: SalePolicy): Checked<WeightsIn> {
  const errors: Record<string, string> = {};
  const body: Partial<WeightsIn> = { reason: form.reason.trim() };
  for (const lane of lanesFor(costs)) {
    const raw = (form[lane] ?? "").trim();
    const micros = toMicros(raw);
    if (!raw) errors[lane] = "Van los tres pesos o ninguno.";
    else if (micros === null || micros === ZERO) errors[lane] = "Un número mayor que cero, con hasta seis decimales.";
    else if (belowFloor(costs[lane], fromMicros(micros), policy)) {
      const times = laneMultiplier(costs[lane], fromMicros(micros), policy.sell_usd_per_million);
      errors[lane] = `Por debajo del suelo: la venta queda en ${formatMultiplier(times)} del coste y el mínimo es ${formatMultiplier(policy.floor)}.`;
    } else body[lane] = fromMicros(micros);
  }
  if (!form.reason.trim()) errors.reason = "Hace falta el motivo.";
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, body: body as WeightsIn };
}

export type MultiplierForm = { multiplier: string; apply_to_all: boolean; reason: string };

/** The target multiplier (contrato §7): never under the floor (3.7), with a reason. */
export function multiplierBody(form: MultiplierForm, floor = "1.5"): Checked<SalePolicyIn> {
  const errors: Record<string, string> = {};
  const m = toMicros(form.multiplier);
  const f = toMicros(floor) ?? BigInt(1_500_000);
  if (m === null) errors.multiplier = "Un número, como 2,2.";
  else if (m < f) errors.multiplier = `No puede ser menor que ${formatMultiplier(floor)}, el suelo.`;
  if (!form.reason.trim()) errors.reason = "Hace falta el motivo.";
  if (Object.keys(errors).length || m === null) return { ok: false, errors };
  return { ok: true, body: { multiplier: fromMicros(m), apply_to_all: form.apply_to_all, reason: form.reason.trim() } };
}
