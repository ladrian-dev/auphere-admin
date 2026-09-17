import { describe, expect, it } from "vitest";

import { AnalyticsEventSchema, AnswersSchema, LeadSchema, StoredSessionSchema } from "../validation";
import { PROFILE_A } from "./fixtures";

const snapshot = {
  scoreTotal: 61, range: "oportunidad_prioritaria", leadTier: "caliente",
  segment: { profile: "decisor_negocio", maturity: "inicial", opportunityCategories: ["automatizacion_operativa"], intent: "media", complexity: "quick_win" },
  recommendationIds: ["clasificacion-solicitudes", "recordatorios-y-seguimiento", "asistente-interno-conocimiento"],
};
const validLead = {
  name: "Ana Pérez", company: "Farmacia Central", email: "Ana@Farmacia.com", role: "Gerente", phone: "+58 412 0000000",
  interest: "automatizacion_operativa", consentContact: true, consentMarketing: false,
  resultSnapshot: snapshot, answers: PROFILE_A, campaign: "ia-empresas-2026", idempotencyKey: "3f6d2c1e-0f0a-4d5e-9b3a-1c2d3e4f5a6b",
};

describe("LeadSchema", () => {
  it("acepta un lead válido y normaliza el correo", () => {
    const r = LeadSchema.safeParse(validLead);
    expect(r.success).toBe(true);
    if (r.success) expect(r.data.email).toBe("ana@farmacia.com");
  });
  it("cargo es opcional", () => {
    const r = LeadSchema.safeParse({ ...validLead, role: "" });
    expect(r.success && r.data.role).toBeUndefined();
  });
  it("teléfono vacío pasa a undefined; inválido falla", () => {
    const r = LeadSchema.safeParse({ ...validLead, phone: "" });
    expect(r.success && r.data.phone).toBeUndefined();
    expect(LeadSchema.safeParse({ ...validLead, phone: "abc" }).success).toBe(false);
  });
  it("rechaza nombre corto, correo inválido y consentimiento sin marcar", () => {
    expect(LeadSchema.safeParse({ ...validLead, name: "A" }).success).toBe(false);
    expect(LeadSchema.safeParse({ ...validLead, email: "no-es-correo" }).success).toBe(false);
    expect(LeadSchema.safeParse({ ...validLead, consentContact: false }).success).toBe(false);
  });
  it("rechaza campos desconocidos e idempotencia no uuid", () => {
    expect(LeadSchema.safeParse({ ...validLead, extra: 1 }).success).toBe(false);
    expect(LeadSchema.safeParse({ ...validLead, idempotencyKey: "x" }).success).toBe(false);
  });
});

describe("AnswersSchema", () => {
  it("valida los perfiles y los límites de selección", () => {
    expect(AnswersSchema.safeParse(PROFILE_A).success).toBe(true);
    expect(AnswersSchema.safeParse({ ...PROFILE_A, frictions: [] }).success).toBe(false);
    expect(AnswersSchema.safeParse({ ...PROFILE_A, frictions: ["a", "b", "c", "d"] }).success).toBe(false);
    expect(AnswersSchema.safeParse({ ...PROFILE_A, goals: ["ahorrar_tiempo", "ahorrar_tiempo"] }).success).toBe(false);
    expect(AnswersSchema.safeParse({ ...PROFILE_A, campaign: "Con Espacios" }).success).toBe(false);
  });
});

describe("StoredSessionSchema y AnalyticsEventSchema", () => {
  it("exige versión 1 y rechaza PII", () => {
    expect(StoredSessionSchema.safeParse({ version: 1, step: "goals", answers: {}, startedAt: 1 }).success).toBe(true);
    expect(StoredSessionSchema.safeParse({ version: 2, step: "goals", answers: {}, startedAt: 1 }).success).toBe(false);
    expect(StoredSessionSchema.safeParse({ version: 1, step: "goals", answers: {}, startedAt: 1, email: "a@b.c" }).success).toBe(false);
  });
  it("los eventos son estrictos", () => {
    expect(AnalyticsEventSchema.safeParse({ name: "lead_submitted", props: { intentLevel: "alta", ts: 1 } }).success).toBe(true);
    expect(AnalyticsEventSchema.safeParse({ name: "lead_submitted", props: { email: "a@b.c", ts: 1 } }).success).toBe(false);
  });
});
