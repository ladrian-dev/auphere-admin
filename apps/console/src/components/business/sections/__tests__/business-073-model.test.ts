import { describe, expect, it } from "vitest";

import type { Provenance } from "@/lib/backend/client-records";
import type { Service } from "@/lib/backend/business-sections";

import { matchesText, normalizeText } from "../business-search";
import { reviewProgress } from "../review-model";
import { openGroupsByDefault, unusedColumns } from "../services-model";

/** Spec 073 (§4): Negocio que se lee. Lo puro, sin navegador. */
const service = (over: Partial<Service> = {}): Service => ({
  id: over.id ?? "s1",
  name: "Corte",
  description: null,
  category: null,
  bookable: false,
  duration_min: null,
  price: { kind: "none" },
  currency: "EUR",
  staff: "all",
  agents: { mode: "all_agents", agent_ids: [] },
  used_by: [{ id: "a1", name: "Ava" }],
  archived: false,
  ...over,
});

describe("buscar (4.1)", () => {
  it("sin tildes ni mayúsculas, en cualquiera de los textos", () => {
    expect(normalizeText("  Depilación LÁSER ")).toBe("depilacion laser");
    expect(matchesText("laser", "Depilación láser", null)).toBe(true);
    expect(matchesText("uñas", null, "Manicura y uñas de gel")).toBe(true);
    expect(matchesText("tinte", "Corte", "Lavado")).toBe(false);
    expect(matchesText("", "Corte")).toBe(true);
  });
});

describe("las columnas que nadie usa (4.3)", () => {
  it("sin precio, sin reserva y el mismo agente para todos se resumen", () => {
    expect(unusedColumns([service(), service({ id: "s2", name: "Tinte" })])).toEqual({ price: true, booking: true, agent: "Ava" });
  });

  it("basta uno con precio, con reserva u otro agente para que la columna se quede", () => {
    const priced = service({ id: "s2", price: { kind: "amount", amount_minor: 1500 } });
    const booked = service({ id: "s3", bookable: true, duration_min: 30 });
    const other = service({ id: "s4", used_by: [{ id: "a2", name: "Leo" }] });
    expect(unusedColumns([service(), priced, booked, other])).toEqual({ price: false, booking: false, agent: null });
  });

  it("con un solo servicio no se resume nada: la tabla ya lo dice", () => {
    expect(unusedColumns([service()])).toEqual({ price: false, booking: false, agent: null });
  });
});

describe("los grupos plegados (4.2)", () => {
  const groups = [{ category: "Barbería", items: Array.from({ length: 8 }, (_, i) => service({ id: `b${i}` })) }, { category: "Uñas", items: Array.from({ length: 6 }, (_, i) => service({ id: `u${i}` })) }];

  it("con más de 12 servicios, solo el primero abierto", () => {
    expect(openGroupsByDefault(groups)).toEqual(new Set(["Barbería"]));
  });

  it("con 12 o menos, todos abiertos", () => {
    expect(openGroupsByDefault([groups[1]!])).toEqual(new Set(["Uñas"]));
  });
});

describe("lo que queda por revisar (4.5)", () => {
  const p = (review: "pending" | "confirmed"): Provenance => ({ source: "web", by: null, origin: "system", at: "2026-11-20T10:00:00Z", source_url: null, translated_from: null, review });

  it("cuenta lo leído (web, documentos, redes) por sección y lo revisado en total; lo escrito por una persona no cuenta", () => {
    const progress = reviewProgress({
      "/services/0": p("pending"),
      "/services/1": p("pending"),
      "/faqs/0": p("confirmed"),
      "/hours": p("pending"),
      "/business/name": { ...p("confirmed"), source: "person" },
    });
    expect(progress.pending).toEqual({ services: 2, hours: 1 });
    expect(progress.total).toBe(4);
    expect(progress.reviewed).toBe(1);
  });
});
