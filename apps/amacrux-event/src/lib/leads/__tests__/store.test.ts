import { describe, expect, it, vi } from "vitest";

import { PROFILE_A } from "@/domain/__tests__/fixtures";
import { LeadSchema } from "@/domain/validation";

import { LeadStoreError, buildLeadRow, insertLead, markEmailDelivered } from "../store";

const lead = LeadSchema.parse({
  name: "Ana Pérez", company: "Farmacia Central", email: "ana@farmacia.com", role: "", phone: "+58 412 0000000",
  interest: "automatizacion_operativa", consentContact: true, consentMarketing: false,
  resultSnapshot: {
    scoreTotal: 61, range: "oportunidad_prioritaria", leadTier: "caliente",
    segment: { profile: "decisor_negocio", maturity: "inicial", opportunityCategories: ["automatizacion_operativa"], intent: "media", complexity: "quick_win" },
    recommendationIds: ["clasificacion-solicitudes", "recordatorios-y-seguimiento", "asistente-interno-conocimiento"],
  },
  answers: PROFILE_A, campaign: "ia-empresas-2026", utm: { source: "qr" }, idempotencyKey: "3f6d2c1e-0f0a-4d5e-9b3a-1c2d3e4f5a6b",
});
const config = { enabled: true as const, url: "https://xyz.supabase.co", serviceKey: "service-key" };

describe("buildLeadRow", () => {
  it("aplana el lead con etiquetas legibles y sin campos extra", () => {
    const row = buildLeadRow(lead, { mode: "live" });
    expect(row.idempotency_key).toBe(lead.idempotencyKey);
    expect(row.email).toBe("ana@farmacia.com");
    expect(row.role).toBeNull();
    expect(row.answers).toEqual(PROFILE_A);
    expect(row.answers_labels.rol).toBe("Dirección");
    expect(row.answers_labels.fricciones).toEqual(["Tareas manuales", "Copiar datos", "Correos y solicitudes"]);
    expect(row.answers_labels.objetivos).toEqual(["Ahorrar tiempo"]);
    expect(row.recommendations).toHaveLength(3);
    expect(row.recommendations[0]).toMatchObject({ id: "clasificacion-solicitudes", category: "automatizacion_operativa" });
    expect(row.recommendations[0]!.title.length).toBeGreaterThan(5);
    expect(row.score_total).toBe(61);
    expect(row.lead_tier).toBe("caliente");
    expect(row.mode).toBe("live");
    expect(row.email_delivered).toBeNull();
    expect(Object.keys(row).sort()).toEqual([
      "answers", "answers_labels", "campaign", "company", "consent_contact", "consent_marketing", "email", "email_delivered", "email_id",
      "idempotency_key", "interest", "lead_tier", "mode", "name", "phone", "recommendations", "role", "score_range", "score_total", "segment", "utm",
    ]);
  });
});

describe("insertLead", () => {
  it("hace POST a /rest/v1/leads con las cabeceras de service role e ignora duplicados", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 201 }));
    await insertLead(config, buildLeadRow(lead, { mode: "live" }), fetchImpl as unknown as typeof fetch);
    const [url, init] = fetchImpl.mock.calls[0]! as unknown as [string, RequestInit];
    expect(url).toBe("https://xyz.supabase.co/rest/v1/leads");
    const h = init.headers as Record<string, string>;
    expect(h.apikey).toBe("service-key");
    expect(h.Authorization).toBe("Bearer service-key");
    expect(h.Prefer).toContain("resolution=ignore-duplicates");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string).email).toBe("ana@farmacia.com");
  });

  it("lanza LeadStoreError con el estado cuando Supabase rechaza, y 'network' si fetch falla", async () => {
    const rejected = vi.fn(async () => new Response("bad", { status: 401 }));
    await expect(insertLead(config, buildLeadRow(lead, { mode: "live" }), rejected as unknown as typeof fetch)).rejects.toMatchObject({ kind: "rejected", status: 401 });
    const down = vi.fn(async () => {
      throw new Error("ECONNRESET");
    });
    await expect(insertLead(config, buildLeadRow(lead, { mode: "live" }), down as unknown as typeof fetch)).rejects.toBeInstanceOf(LeadStoreError);
  });

  it("markEmailDelivered hace PATCH por idempotency_key", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    await markEmailDelivered(config, lead.idempotencyKey, "email_1", fetchImpl as unknown as typeof fetch);
    const [url, init] = fetchImpl.mock.calls[0]! as unknown as [string, RequestInit];
    expect(url).toBe(`https://xyz.supabase.co/rest/v1/leads?idempotency_key=eq.${lead.idempotencyKey}`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ email_delivered: true, email_id: "email_1" });
  });
});

describe("postLeadWebhook (copia a Google Sheets vía n8n)", () => {
  it("hace POST JSON con la fila aplanada y la cabecera de secreto", async () => {
    const { postLeadWebhook, flattenLeadRow } = await import("../store");
    const fetchImpl = vi.fn(async () => new Response(null, { status: 200 }));
    const row = buildLeadRow(lead, { mode: "live" });
    await postLeadWebhook({ url: "https://n8n.test/webhook/leads", secret: "s3cret" }, row, fetchImpl as unknown as typeof fetch);
    const [url, init] = fetchImpl.mock.calls[0]! as unknown as [string, RequestInit];
    expect(url).toBe("https://n8n.test/webhook/leads");
    expect((init.headers as Record<string, string>)["X-Leads-Secret"]).toBe("s3cret");
    const body = JSON.parse(init.body as string);
    expect(body.nombre).toBe("Ana Pérez");
    expect(body.fricciones).toBe("Tareas manuales, Copiar datos, Correos y solicitudes");
    expect(body.recomendacion_1).toMatch(/solicitudes/i);
    expect(flattenLeadRow(row).puntuacion).toBe(61);
  });
  it("lanza LeadStoreError si el webhook responde error", async () => {
    const { postLeadWebhook } = await import("../store");
    const bad = vi.fn(async () => new Response("x", { status: 500 }));
    await expect(postLeadWebhook({ url: "https://n8n.test/webhook/leads" }, buildLeadRow(lead, { mode: "live" }), bad as unknown as typeof fetch)).rejects.toBeInstanceOf(LeadStoreError);
  });
});
