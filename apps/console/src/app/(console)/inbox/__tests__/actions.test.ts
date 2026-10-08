import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../actions");
const ID = "5b0a5f0e-7c2d-4c39-9d6f-1e1c9f3a1b22";
const forbidden = { ok: false, status: 403, message: "forbidden" };

/** Spec 030 (T062): the Inbox's actions are for a client person with the Inbox, nobody else. */
describe("inbox actions", () => {
  it("serve a client with the Inbox", async () => {
    h.setClient(["panel", "inbox"]);
    h.backend.inboxDetail.mockResolvedValue({ id: ID });
    h.backend.inboxThread.mockResolvedValue({ items: [], next_before: null });
    const opened = await actions.openConversationAction({ id: ID });
    expect(opened).toEqual({ ok: true, data: { detail: { id: ID }, thread: { items: [], next_before: null } } });
    expect(h.backend.inboxMarkRead).toHaveBeenCalledWith(ID);

    await actions.takeOverAction({ id: ID, version: 4 });
    expect(h.backend.inboxTakeOver).toHaveBeenCalledWith(ID, 4);
    await actions.sendMessageAction({ id: ID, text: "Hola" });
    expect(h.backend.inboxSend).toHaveBeenCalledWith(ID, "Hola");
    await actions.listConversationsAction({ filter: "waiting", q: "  ana " });
    expect(h.backend.inboxList).toHaveBeenCalledWith({ filter: "waiting", q: "ana", cursor: undefined });
  });

  it("refresh without marking read when asked (a live update while the tab is hidden)", async () => {
    h.setClient(["inbox"]);
    h.backend.inboxMarkRead.mockClear();
    await actions.openConversationAction({ id: ID, markRead: false });
    expect(h.backend.inboxMarkRead).not.toHaveBeenCalled();
  });

  it("deny a client without the Inbox and a partner member, without calling the backend", async () => {
    h.backend.inboxList.mockClear();
    h.setClient(["panel", "usage"]);
    expect(await actions.listConversationsAction({})).toEqual(forbidden);
    h.setRole("owner");
    expect(await actions.listConversationsAction({})).toEqual(forbidden);
    expect(await actions.sendMessageAction({ id: ID, text: "x" })).toEqual(forbidden);
    expect(h.backend.inboxList).not.toHaveBeenCalled();
    expect(h.backend.inboxSend).not.toHaveBeenCalledWith(ID, "x");
  });

  it("a stale version travels back with the real conversation (412)", async () => {
    h.setClient(["inbox"]);
    h.fail("inboxTakeOver", 412, "", null, { error: "version_mismatch", conversation: { id: ID, state: "person" } });
    const r = await actions.takeOverAction({ id: ID, version: 1 });
    expect(r).toMatchObject({ ok: false, status: 412, info: { conversation: { id: ID, state: "person" } } });
  });

  it("validates before asking: a blank message never leaves", async () => {
    h.setClient(["inbox"]);
    await expect(actions.sendMessageAction({ id: ID, text: "   " })).rejects.toThrow();
    await expect(actions.openConversationAction({ id: "not-a-uuid" })).rejects.toThrow();
  });
});
