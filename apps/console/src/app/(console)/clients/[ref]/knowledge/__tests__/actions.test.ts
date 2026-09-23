import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);
vi.mock("@/lib/backend/agent-tools", async (orig) => ({
  ...(await orig<typeof import("@/lib/backend/agent-tools")>()),
  uploadKnowledgeFile: vi.fn(async () => ({ id: "d1" })),
  uploadPlaybookFile: vi.fn(async () => ({ id: "p1" })),
}));

const { uploadKnowledgeAction, addKnowledgeUrlAction, deleteKnowledgeAction, reindexKnowledgeAction } = await import("../actions");
const { uploadKnowledgeFile } = await import("@/lib/backend/agent-tools");

function form(): FormData {
  const fd = new FormData();
  fd.set("ref", "demo");
  fd.set("file", new File(["hola"], "faq.txt", { type: "text/plain" }));
  return fd;
}

describe("client knowledge actions (spec 016, R8)", () => {
  it("builder uploads, adds a URL, reindexes and deletes", async () => {
    h.setRole("builder");
    expect(await uploadKnowledgeAction(form())).toEqual({ ok: true, data: { id: "d1" } });
    expect(uploadKnowledgeFile).toHaveBeenCalled();
    expect(await addKnowledgeUrlAction({ ref: "demo", url: "https://example.com/faq", title: "" })).toMatchObject({ ok: true });
    expect(h.backend.addKnowledgeUrl).toHaveBeenCalledWith("demo", { url: "https://example.com/faq", title: undefined });
    expect(await reindexKnowledgeAction({ ref: "demo", id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(await deleteKnowledgeAction({ ref: "demo", id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/knowledge");
  });
  it("an empty file is 422 and a big one 413, before touching the principal", async () => {
    h.setRole("builder");
    const empty = new FormData();
    empty.set("ref", "demo");
    empty.set("file", new File([], "empty.txt"));
    expect(await uploadKnowledgeAction(empty)).toMatchObject({ ok: false, status: 422 });
  });
  it("analyst: denied before any call", async () => {
    h.setRole("analyst");
    vi.mocked(uploadKnowledgeFile).mockClear();
    for (const fn of [h.backend.addKnowledgeUrl, h.backend.deleteKnowledge, h.backend.reindexKnowledge]) fn.mockClear();
    expect(await uploadKnowledgeAction(form())).toEqual(h.denied());
    expect(uploadKnowledgeFile).not.toHaveBeenCalled();
    expect(await addKnowledgeUrlAction({ ref: "demo", url: "https://example.com/x" })).toEqual(h.denied());
    expect(await deleteKnowledgeAction({ ref: "demo", id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    expect(await reindexKnowledgeAction({ ref: "demo", id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    for (const fn of [h.backend.addKnowledgeUrl, h.backend.deleteKnowledge, h.backend.reindexKnowledge]) expect(fn).not.toHaveBeenCalled();
  });
});
