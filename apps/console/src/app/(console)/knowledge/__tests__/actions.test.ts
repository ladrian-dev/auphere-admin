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

const { uploadPlaybookAction, addPlaybookUrlAction, deletePlaybookAction, reindexPlaybookAction } = await import("../actions");
const { uploadPlaybookFile } = await import("@/lib/backend/agent-tools");

function form(): FormData {
  const fd = new FormData();
  fd.set("file", new File(["guía"], "playbook.md", { type: "text/markdown" }));
  fd.set("title", "Guía");
  return fd;
}

describe("playbook actions (spec 016, R8)", () => {
  it("admin manages the partner playbook (playbook:write)", async () => {
    h.setRole("admin");
    expect(await uploadPlaybookAction(form())).toEqual({ ok: true, data: { id: "p1" } });
    expect(uploadPlaybookFile).toHaveBeenCalled();
    expect(await addPlaybookUrlAction({ url: "https://example.com/guide", title: "Guía" })).toMatchObject({ ok: true });
    expect(h.backend.addPlaybookUrl).toHaveBeenCalledWith({ url: "https://example.com/guide", title: "Guía" });
    expect(await reindexPlaybookAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(await deletePlaybookAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/knowledge");
  });
  it("builder (reads the playbook, does not write it): denied before any call", async () => {
    h.setRole("builder");
    vi.mocked(uploadPlaybookFile).mockClear();
    for (const fn of [h.backend.addPlaybookUrl, h.backend.deletePlaybook, h.backend.reindexPlaybook]) fn.mockClear();
    expect(await uploadPlaybookAction(form())).toEqual(h.denied());
    expect(uploadPlaybookFile).not.toHaveBeenCalled();
    expect(await addPlaybookUrlAction({ url: "https://example.com/x" })).toEqual(h.denied());
    expect(await deletePlaybookAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    expect(await reindexPlaybookAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    for (const fn of [h.backend.addPlaybookUrl, h.backend.deletePlaybook, h.backend.reindexPlaybook]) expect(fn).not.toHaveBeenCalled();
  });
});
