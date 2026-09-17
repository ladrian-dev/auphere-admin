import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { PROFILE_A } from "@/domain/__tests__/fixtures";
import type { LeadParsed } from "@/domain/validation";

import { buildLeadEmail, csvBlock } from "../email";

const lead: LeadParsed = {
  name: "Ana Pérez",
  company: "Farmacia Central",
  email: "ana@farmacia.com",
  phone: "+34 600 111 222",
  role: undefined,
  interest: "automatizacion_operativa",
  consentContact: true,
  consentMarketing: false,
  resultSnapshot: {
    scoreTotal: 61,
    range: "oportunidad_prioritaria",
    leadTier: "caliente",
    segment: { profile: "decisor_negocio", maturity: "inicial", opportunityCategories: ["automatizacion_operativa", "integraciones_orquestacion"], intent: "media", complexity: "quick_win" },
    recommendationIds: ["clasificacion-solicitudes", "recordatorios-y-seguimiento", "asistente-interno-conocimiento"],
  },
  answers: PROFILE_A,
  campaign: "ia-empresas-2026",
  utm: { source: "qr", medium: "evento" },
  idempotencyKey: "11111111-2222-3333-4444-555555555555",
  fax: undefined,
};
const now = new Date("2026-09-17T18:30:00.000Z");

describe("correo del lead", () => {
  it("el asunto identifica empresa, nivel y oportunidad", () => {
    expect(buildLeadEmail(lead, now).subject).toMatch(/Farmacia Central/);
  });

  it("lleva el contacto, el origen y la clave de idempotencia", () => {
    const { text } = buildLeadEmail(lead, now);
    expect(text).toMatch(/ana@farmacia\.com/);
    expect(text).toMatch(/\+34 600 111 222/);
    expect(text).toMatch(/ia-empresas-2026/);
    expect(text).toMatch(/source=qr/);
    expect(text).toMatch(/11111111-2222-3333-4444-555555555555/);
  });

  it("lleva las doce respuestas en etiquetas legibles", () => {
    const { text } = buildLeadEmail(lead, now);
    for (const label of [
      "Dirección", "Comercio y retail", "11–50 personas", "Consumidores (B2C)", "Explorando",
      "Todavía no", "Hojas de cálculo", "Tareas manuales", "Copiar datos", "Correos y solicitudes",
      "Ahorrar tiempo", "Próximos meses", "Sin equipo técnico", "Para una prueba",
    ]) {
      expect(text, label).toContain(label);
    }
  });

  it("lleva la cualificación con el desglose de la puntuación", () => {
    const { text } = buildLeadEmail(lead, now);
    expect(text).toMatch(/61\/100/);
    expect(text).toMatch(/caliente/);
    expect(text).toMatch(/claridad/i);
    expect(text).toMatch(/urgencia:\s*\d+/i);
  });

  it("no enseña una línea de cargo vacía cuando no se pidió", () => {
    expect(buildLeadEmail(lead, now).text).not.toMatch(/Cargo: —/);
  });

  it("incluye una fila CSV con las columnas documentadas, lista para pegar", () => {
    const { text } = buildLeadEmail(lead, now);
    const documented = readFileSync("docs/leads-sheet-headers.csv", "utf8").trim();
    const { header, row } = csvBlock(lead, now, "live");
    expect(header).toBe(documented);
    expect(text).toContain(header);
    expect(text).toContain(row);
    // Las listas con comas van entrecomilladas para no romper columnas.
    expect(row).toContain('"Tareas manuales, Copiar datos, Correos y solicitudes"');
    const cells = row.split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/);
    expect(cells).toHaveLength(header.split(",").length);
  });

  it("escapa el HTML del contenido", () => {
    const evil = { ...lead, company: '<script>alert("x")</script>' };
    expect(buildLeadEmail(evil, now).html).not.toContain("<script>");
  });
});
