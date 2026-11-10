/**
 * Spec 047 (T150): the words and the pure rules of the catalog screen —
 * labels, formats and the validation of what the operator types before it
 * goes to the API. The API validates again; this only spares a round trip and
 * says what is wrong next to the field.
 */
import type { StatusBadgeTone } from "@nexus/ui";

import type {
  DeploymentIn,
  DeploymentStatus,
  PriceContract,
  PriceIn,
  ProposalOut,
  Residency,
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
  partial_weights: "Los pesos del medidor van los tres o ninguno.",
  deployment_exists: "Ya hay un despliegue con esa clave.",
  bad_capabilities: "Las capacidades no son válidas.",
  in_the_past: "La fecha de retirada ya pasó.",
  naive_date: "La fecha necesita su zona horaria.",
  not_servable: "Un despliegue retirado o no disponible no se puede retirar otra vez.",
  unknown_deployment: "Ese despliegue ya no existe.",
  reason_required: "Hace falta el motivo.",
};

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

/** A price enters with its date and its source (41.1, 41.8). */
export function priceBody(form: PriceForm): Checked<PriceIn> {
  const errors: Record<string, string> = {};
  if (!DAY.test(form.valid_from)) errors.valid_from = "La fecha de vigencia, AAAA-MM-DD.";
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
