import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { discardDraftAction, draftDiffAction, publishFromBarAction, saveDraftAction } = await import("../actions");

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
    expect(h.backend.getDraftDiff).toHaveBeenCalledWith("demo", undefined);
  });

  it("publicar desde la barra dice de dónde salió el clic", async () => {
    h.setRole("builder");
    h.backend.publishAgentVersion.mockResolvedValueOnce({ version: 4 });
    expect(await publishFromBarAction({ ref: "demo", version: 4 })).toMatchObject({ ok: true });
    expect(h.backend.publishAgentVersion).toHaveBeenCalledWith("demo", 4, "draft_bar", undefined);
    // Spec 030: the bar of another agent publishes that agent's draft.
    expect(await publishFromBarAction({ ref: "demo", version: 5, agent: "8f9e0d1c-2b3a-4c5d-8e6f-7a8b9c0d1e2f" })).toMatchObject({ ok: true });
    expect(h.backend.publishAgentVersion).toHaveBeenLastCalledWith("demo", 5, "draft_bar", "8f9e0d1c-2b3a-4c5d-8e6f-7a8b9c0d1e2f");
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

/**
 * Spec 047 · historia 2: la única barra de guardado escribe en el borrador del
 * agente con la revisión que leyó la pantalla, y descartar también la lleva.
 * El 412 no es un error que se esconda: viaja con su código y su `info`.
 */
describe("el único borrador del agente", () => {
  const agent = "8f9e0d1c-2b3a-4c5d-8e6f-7a8b9c0d1e2f";

  it("guardar manda el agente, la revisión y solo lo que cambió", async () => {
    h.setRole("builder");
    h.backend.saveAgentDraft.mockResolvedValueOnce({ revision: 4 });
    expect(await saveDraftAction({ ref: "demo", agent, revision: 3, patch: { system_prompt: "Hola", note: "Más corto" } })).toMatchObject({ ok: true });
    expect(h.backend.saveAgentDraft).toHaveBeenCalledWith("demo", agent, 3, { system_prompt: "Hola", note: "Más corto" });
  });

  it("una escritura vacía o sin agente no sale", async () => {
    h.setRole("owner");
    await expect(saveDraftAction({ ref: "demo", agent, revision: 3, patch: {} })).rejects.toThrow();
    await expect(saveDraftAction({ ref: "demo", revision: 3, patch: { system_prompt: "x" } })).rejects.toThrow();
  });

  it("el 412 llega con su código y lo que cambió", async () => {
    h.setRole("owner");
    h.fail("saveAgentDraft", 412, "", "revision_conflict", { current: { revision: 5 }, changes: [] });
    expect(await saveDraftAction({ ref: "demo", agent, revision: 3, patch: { system_prompt: "x" } })).toMatchObject({
      ok: false,
      status: 412,
      code: "revision_conflict",
      info: { current: { revision: 5 }, changes: [] },
    });
  });

  it("un analista no guarda ni descarta, y no se llega a llamar al backend", async () => {
    h.setRole("analyst");
    h.backend.saveAgentDraft.mockClear();
    h.backend.discardAgentDraft.mockClear();
    expect(await saveDraftAction({ ref: "demo", agent, revision: 3, patch: { system_prompt: "x" } })).toEqual(h.denied());
    expect(await discardDraftAction({ ref: "demo", agent, revision: 3 })).toEqual(h.denied());
    expect(h.backend.saveAgentDraft).not.toHaveBeenCalled();
    expect(h.backend.discardAgentDraft).not.toHaveBeenCalled();
  });

  it("descartar lleva la revisión que se leyó", async () => {
    h.setRole("admin");
    h.backend.discardAgentDraft.mockResolvedValueOnce({ revision: 8, exists: false });
    expect(await discardDraftAction({ ref: "demo", agent, revision: 7 })).toMatchObject({ ok: true });
    expect(h.backend.discardAgentDraft).toHaveBeenCalledWith("demo", agent, 7);
  });
});
