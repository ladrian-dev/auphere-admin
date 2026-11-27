import { describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() =>
  vi.fn((to: string) => {
    throw new Error(`NEXT_REDIRECT ${to}`);
  }),
);
vi.mock("next/navigation", () => ({ redirect }));
const guard = vi.hoisted(() => vi.fn(async () => ({ kind: "partner", role: "billing" })));
vi.mock("@/lib/principal", () => ({ requirePartnerPrincipal: guard }));

const { default: ClientReportRedirect } = await import("../page");

/**
 * Spec 083, enmienda del 2026-11-27 (T023; requisito 11.8, D22): la pestaña
 * «Informe» ya no existe. Quien llegue con un enlace viejo va a Métricas con
 * ese cliente elegido; Métricas pide sus propios permisos.
 */
describe("/clients/[ref]/report", () => {
  it("lleva a /usage?client=<ref>", async () => {
    await expect(ClientReportRedirect({ params: Promise.resolve({ ref: "jemma-hair" }) })).rejects.toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/usage?client=jemma-hair");
    // La guarda de siempre, antes de redirigir.
    expect(guard).toHaveBeenCalledWith("/clients/jemma-hair/report");
  });

  it("la referencia va codificada", async () => {
    await expect(ClientReportRedirect({ params: Promise.resolve({ ref: "café & co" }) })).rejects.toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenLastCalledWith("/usage?client=caf%C3%A9%20%26%20co");
  });
});
