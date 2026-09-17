import { CATEGORY_LABELS, frictionLabel, goalLabel } from "@/domain/copy";
import { OPPORTUNITIES } from "@/domain/opportunities";
import { optionLabel } from "@/domain/questions";
import type { Answers, Segment, Utm } from "@/domain/types";
import type { LeadParsed } from "@/domain/validation";

import type { LeadStorageConfig } from "../env.server";

/** Fila de `public.leads` (ver supabase/migrations/0001_leads.sql). */
export interface LeadRow {
  idempotency_key: string;
  name: string;
  company: string;
  email: string;
  phone: string | null;
  role: string | null;
  interest: string;
  consent_contact: boolean;
  consent_marketing: boolean;
  campaign: string | null;
  utm: Utm | null;
  answers: Answers;
  answers_labels: {
    rol: string; sector: string; tamano_equipo: string; clientes: string; como_trabajan: string; uso_ia: string; datos: string;
    fricciones: string[]; objetivos: string[]; urgencia: string; apoyo_tecnico: string; inversion: string;
  };
  score_total: number;
  score_range: string;
  lead_tier: string;
  segment: Segment;
  recommendations: Array<{ id: string; title: string; category: string; category_label: string }>;
  email_delivered: boolean | null;
  email_id: string | null;
  mode: "live" | "demo";
}

export class LeadStoreError extends Error {
  constructor(
    public readonly kind: "network" | "rejected",
    public readonly status?: number,
  ) {
    super(kind);
    this.name = "LeadStoreError";
  }
}

type StorageOn = Extract<LeadStorageConfig, { enabled: true }>;

/** Fila plana para una hoja de cálculo: una columna por dato, listas unidas por comas. */
export function flattenLeadRow(row: LeadRow): Record<string, string | number | boolean | null> {
  const l = row.answers_labels;
  return {
    fecha: new Date().toISOString(),
    nombre: row.name,
    empresa: row.company,
    correo: row.email,
    telefono: row.phone,
    rol: l.rol,
    sector: l.sector,
    tamano_equipo: l.tamano_equipo,
    clientes: l.clientes,
    como_trabajan: l.como_trabajan,
    uso_ia: l.uso_ia,
    datos: l.datos,
    fricciones: l.fricciones.join(", "),
    objetivos: l.objetivos.join(", "),
    urgencia: l.urgencia,
    apoyo_tecnico: l.apoyo_tecnico,
    inversion: l.inversion,
    puntuacion: row.score_total,
    nivel: row.score_range,
    etiqueta_interna: row.lead_tier,
    recomendacion_1: row.recommendations[0]?.title ?? null,
    recomendacion_2: row.recommendations[1]?.title ?? null,
    recomendacion_3: row.recommendations[2]?.title ?? null,
    campana: row.campaign,
    consentimiento_contacto: row.consent_contact,
    modo: row.mode,
    idempotency_key: row.idempotency_key,
  };
}

/** Envía la fila plana al webhook (n8n → Google Sheets). */
export async function postLeadWebhook(config: { url: string; secret?: string }, row: LeadRow, fetchImpl: typeof fetch = (...args) => fetch(...args)): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (config.secret) headers["X-Leads-Secret"] = config.secret;
  let res: Response;
  try {
    res = await fetchImpl(config.url, { method: "POST", headers, body: JSON.stringify(flattenLeadRow(row)) });
  } catch {
    throw new LeadStoreError("network");
  }
  if (!res.ok) throw new LeadStoreError("rejected", res.status);
}

export function buildLeadRow(lead: LeadParsed, opts: { mode: "live" | "demo" }): LeadRow {
  const a = lead.answers;
  const snap = lead.resultSnapshot;
  return {
    idempotency_key: lead.idempotencyKey,
    name: lead.name,
    company: lead.company,
    email: lead.email,
    phone: lead.phone ?? null,
    role: lead.role ?? null,
    interest: lead.interest,
    consent_contact: lead.consentContact,
    consent_marketing: lead.consentMarketing,
    campaign: lead.campaign ?? null,
    utm: lead.utm ?? null,
    answers: a,
    answers_labels: {
      rol: optionLabel("profile", a.profile),
      sector: optionLabel("sector", a.sector),
      tamano_equipo: optionLabel("teamSize", a.teamSize),
      clientes: optionLabel("customerType", a.customerType),
      como_trabajan: optionLabel("workLevel", a.workLevel),
      uso_ia: optionLabel("aiUsage", a.aiUsage),
      datos: optionLabel("dataLocation", a.dataLocation),
      fricciones: a.frictions.map(frictionLabel),
      objetivos: a.goals.map(goalLabel),
      urgencia: optionLabel("urgency", a.urgency),
      apoyo_tecnico: optionLabel("techCapacity", a.techCapacity),
      inversion: optionLabel("investment", a.investment),
    },
    score_total: snap.scoreTotal,
    score_range: snap.range,
    lead_tier: snap.leadTier,
    segment: snap.segment,
    recommendations: snap.recommendationIds.map((id) => {
      const o = OPPORTUNITIES.find((x) => x.id === id);
      return { id, title: o?.title ?? id, category: o?.category ?? "", category_label: o ? CATEGORY_LABELS[o.category] : "" };
    }),
    email_delivered: null,
    email_id: null,
    mode: opts.mode,
  };
}

function headers(config: StorageOn, prefer: string): Record<string, string> {
  return {
    apikey: config.serviceKey,
    Authorization: `Bearer ${config.serviceKey}`,
    "Content-Type": "application/json",
    Prefer: prefer,
  };
}

async function call(config: StorageOn, path: string, init: RequestInit, fetchImpl: typeof fetch): Promise<void> {
  let res: Response;
  try {
    res = await fetchImpl(`${config.url}${path}`, init);
  } catch {
    throw new LeadStoreError("network");
  }
  if (!res.ok) throw new LeadStoreError("rejected", res.status);
}

/** Inserta la fila; una `idempotency_key` repetida no falla ni duplica. */
export async function insertLead(config: StorageOn, row: LeadRow, fetchImpl: typeof fetch = (...args) => fetch(...args)): Promise<void> {
  await call(config, "/rest/v1/leads", { method: "POST", headers: headers(config, "resolution=ignore-duplicates,return=minimal"), body: JSON.stringify(row) }, fetchImpl);
}

/** Anota en la fila que el correo salió (best-effort). */
export async function markEmailDelivered(config: StorageOn, idempotencyKey: string, emailId: string, fetchImpl: typeof fetch = (...args) => fetch(...args)): Promise<void> {
  await call(
    config,
    `/rest/v1/leads?idempotency_key=eq.${encodeURIComponent(idempotencyKey)}`,
    { method: "PATCH", headers: headers(config, "return=minimal"), body: JSON.stringify({ email_delivered: true, email_id: emailId }) },
    fetchImpl,
  );
}
