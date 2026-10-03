import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { unreadCountAction, listNotificationsAction, markNotificationReadAction, markAllNotificationsReadAction, searchClientsAction } = await import("../actions");

describe("notifications actions (spec 016, R8)", () => {
  it("every role reads the bell (partner:read)", async () => {
    for (const role of ["owner", "admin", "builder", "analyst", "billing"] as const) {
      h.setRole(role);
      h.backend.unreadNotifications.mockResolvedValueOnce({ unread: 1 });
      expect(await unreadCountAction()).toEqual({ ok: true, data: { unread: 1 } });
    }
    h.backend.listNotifications.mockResolvedValueOnce({ items: [], next_cursor: null, unread: 0 });
    expect(await listNotificationsAction({ unread: true })).toMatchObject({ ok: true });
    expect(h.backend.listNotifications).toHaveBeenCalledWith({ unread: true });
    expect(await markNotificationReadAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(await markAllNotificationsReadAction()).toMatchObject({ ok: true });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/notifications");
  });
  it("⌘K search is empty (not an error) for a role without clients:read", async () => {
    h.setRole("billing");
    h.backend.listClients.mockClear();
    expect(await searchClientsAction({ q: "pan" })).toEqual({ ok: true, data: [] });
    expect(h.backend.listClients).not.toHaveBeenCalled();
    h.setRole("analyst");
    h.backend.listClients.mockResolvedValueOnce({ items: [{ external_client_ref: "a" }], total: 1, limit: 8, offset: 0 });
    expect(await searchClientsAction({ q: " pan " })).toEqual({ ok: true, data: [{ external_client_ref: "a" }] });
    expect(h.backend.listClients).toHaveBeenCalledWith({ q: "pan", limit: 8, sort: "updated_at", order: "desc" });
  });
});
