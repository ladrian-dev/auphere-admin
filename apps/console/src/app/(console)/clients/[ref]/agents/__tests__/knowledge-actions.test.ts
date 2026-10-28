import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);
vi.mock("@/lib/backend/agent-knowledge", async (orig) => ({
  ...(await orig<typeof import("@/lib/backend/agent-knowledge")>()),
  uploadAgentKnowledgeFile: vi.fn(async () => ({ id: "d1" })),
}));

const actions = await import("../knowledge-actions");
const { restoreKnowledgeAction } = await import("../../knowledge/actions");
const { uploadAgentKnowledgeFile } = await import("@/lib/backend/agent-knowledge");

const AGENT = "11111111-1111-4111-8111-111111111111";
const DOC = "66666666-6666-4666-8666-666666666661";
const ids = { ref: "demo", agent: AGENT };

function form(over: Record<string, string | File> = {}): FormData {
  const fd = new FormData();
  fd.set("ref", "demo");
  fd.set("agent", AGENT);
  fd.set("file", new File(["hola"], "tarifas.txt", { type: "text/plain" }));
  for (const [k, v] of Object.entries(over)) fd.set(k, v);
  return fd;
}

/**
 * Spec 047 (historia 22, T134) — las acciones del conocimiento de un agente:
 * `knowledge:read` para leer, `knowledge:write` para subir, añadir una web,
 * quitar, restaurar y «Enseñar» (que exige el alcance). Los códigos de la API
 * vuelven tal cual (`undo_window_closed`).
 */
describe("el conocimiento de un agente", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("sube un archivo y añade una web solo para este agente", async () => {
    expect(await actions.uploadAgentKnowledgeAction(form({ title: " Tarifas " }))).toEqual({ ok: true, data: { id: "d1" } });
    const sent = (uploadAgentKnowledgeFile as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(sent.slice(1, 3)).toEqual(["demo", AGENT]);
    expect((sent[3] as FormData).get("title")).toBe("Tarifas");
    await actions.addAgentKnowledgeUrlAction({ ...ids, url: "https://cultor.es/precios", title: "" });
    expect(h.backend.addAgentKnowledgeUrl).toHaveBeenCalledWith("demo", AGENT, { url: "https://cultor.es/precios" });
    await expect(actions.addAgentKnowledgeUrlAction({ ...ids, url: "cultor.es" })).rejects.toThrow();
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith(`/clients/demo/agents/${AGENT}`);
  });

  it("un archivo vacío es 422 y uno de más de 10 MB, 413, sin llamar a la API", async () => {
    expect(await actions.uploadAgentKnowledgeAction(form({ file: new File([], "vacio.txt") }))).toMatchObject({ ok: false, status: 422 });
    const big = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "grande.pdf");
    expect(await actions.uploadAgentKnowledgeAction(form({ file: big }))).toMatchObject({ ok: false, status: 413 });
    expect(uploadAgentKnowledgeFile).not.toHaveBeenCalled();
  });

  it("quitar y restaurar; pasado el plazo, el código vuelve", async () => {
    await actions.removeAgentKnowledgeAction({ ...ids, doc: DOC });
    expect(h.backend.removeAgentKnowledge).toHaveBeenCalledWith("demo", AGENT, DOC);
    h.fail("restoreAgentKnowledge", 409, "", "undo_window_closed");
    expect(await actions.restoreAgentKnowledgeAction({ ...ids, doc: DOC })).toMatchObject({ ok: false, code: "undo_window_closed" });
  });

  it("«Enseñar» exige el alcance y, al negocio, refresca también Negocio", async () => {
    await expect(actions.teachAction({ ...ids, text: "Cerramos en agosto" })).rejects.toThrow();
    await expect(actions.teachAction({ ...ids, text: "  ", scope: "agent" })).rejects.toThrow();
    await actions.teachAction({ ...ids, text: " Cerramos en agosto ", scope: "business" });
    expect(h.backend.teachAgent).toHaveBeenCalledWith("demo", AGENT, { text: "Cerramos en agosto", scope: "business" });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/knowledge");
  });

  it("deshacer «Enseñar» quita la fuente en su capa", async () => {
    await actions.forgetTaughtAction({ ...ids, doc: DOC, scope: "agent" });
    expect(h.backend.removeAgentKnowledge).toHaveBeenCalledWith("demo", AGENT, DOC);
    await actions.forgetTaughtAction({ ...ids, doc: DOC, scope: "business" });
    expect(h.backend.deleteKnowledge).toHaveBeenCalledWith("demo", DOC);
  });

  it("en Negocio, eliminar se deshace durante 10 minutos", async () => {
    expect(await restoreKnowledgeAction({ ref: "demo", id: DOC })).toMatchObject({ ok: true });
    expect(h.backend.restoreKnowledge).toHaveBeenCalledWith("demo", DOC);
  });

  it("un analista lee, pero no cambia nada", async () => {
    h.setRole("analyst");
    expect(await actions.agentKnowledgeAction(ids)).toMatchObject({ ok: true });
    for (const write of [
      actions.uploadAgentKnowledgeAction(form()),
      actions.addAgentKnowledgeUrlAction({ ...ids, url: "https://cultor.es" }),
      actions.removeAgentKnowledgeAction({ ...ids, doc: DOC }),
      actions.restoreAgentKnowledgeAction({ ...ids, doc: DOC }),
      actions.teachAction({ ...ids, text: "x", scope: "agent" }),
      actions.forgetTaughtAction({ ...ids, doc: DOC, scope: "agent" }),
    ]) {
      expect(await write).toEqual(h.denied());
    }
    expect(h.backend.teachAgent).not.toHaveBeenCalled();
    expect(uploadAgentKnowledgeFile).not.toHaveBeenCalled();
  });
});
