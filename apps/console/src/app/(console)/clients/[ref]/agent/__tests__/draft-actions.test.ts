import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { draftDiffAction, publishFromBarAction } = await import("../actions");

/**
 * Spec 017 · R3.2/R3.3: leer qué cambia un borrador y publicarlo desde la
 * barra, esté el partner en la pestaña que esté.
 *
 * Leer es leer: un analista que no puede publicar sí tiene que poder ver
 * lo que otro dejó preparado. Publicar es otra cosa, y lleva su `can()`.
 */
describe("el borrador, desde cualquier pestaña", () => {
  it("un analista puede leer lo que cambia, aunque no pueda publicarlo", async () => {
    h.setRole("analyst");
    h.backend.getDraftDiff.mockResolvedValueOnce({ version: { draft: 4, active: 3 }, settings: [], capabilities: [], knowledge: [], prompt: { before: "a", after: "b" } });
    expect(await draftDiffAction({ ref: "demo" })).toMatchObject({ ok: true });
    expect(h.backend.getDraftDiff).toHaveBeenCalledWith("demo");
  });

  it("publicar desde la barra dice de dónde salió el clic", async () => {
    h.setRole("builder");
    h.backend.publishAgentVersion.mockResolvedValueOnce({ version: 4 });
    expect(await publishFromBarAction({ ref: "demo", version: 4 })).toMatchObject({ ok: true });
    expect(h.backend.publishAgentVersion).toHaveBeenCalledWith("demo", 4, "draft_bar");
  });

  it("un analista no publica, y no se llega a llamar al backend", async () => {
    h.setRole("analyst");
    h.backend.publishAgentVersion.mockClear();
    expect(await publishFromBarAction({ ref: "demo", version: 4 })).toEqual(h.denied());
    expect(h.backend.publishAgentVersion).not.toHaveBeenCalled();
  });

  it("el rol de facturación ni siquiera lee el borrador", async () => {
    h.setRole("billing");
    h.backend.getDraftDiff.mockClear();
    expect(await draftDiffAction({ ref: "demo" })).toEqual(h.denied());
    expect(h.backend.getDraftDiff).not.toHaveBeenCalled();
  });
});
