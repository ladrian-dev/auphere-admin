import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const {
  liteUnreadCountAction,
  liteListNotificationsAction,
  liteReadAllNotificationsAction,
  liteMarkNotificationReadAction,
} = await import("../lite-notifications-actions");

/** Spec 030 (R15.1, R15.2): the lite bell is the client user's, nobody else's. */
describe("lite notification actions", () => {
  it("serve a client user", async () => {
    h.setClient(["panel"]);
    h.backend.liteUnreadNotifications.mockResolvedValue({ unread: 2 });
    expect(await liteUnreadCountAction()).toEqual({ ok: true, data: { unread: 2 } });
    await liteListNotificationsAction();
    expect(h.backend.liteNotifications).toHaveBeenCalledWith({ limit: 20 });
    await liteReadAllNotificationsAction();
    expect(h.backend.liteReadAllNotifications).toHaveBeenCalled();
    await liteMarkNotificationReadAction({ id: "5b0a5f0e-7c2d-4c39-9d6f-1e1c9f3a1b22" });
    expect(h.backend.liteMarkNotificationRead).toHaveBeenCalledWith("5b0a5f0e-7c2d-4c39-9d6f-1e1c9f3a1b22");
  });

  it("deny a partner member without calling the backend", async () => {
    h.setRole("owner");
    h.backend.liteUnreadNotifications.mockClear();
    expect(await liteUnreadCountAction()).toEqual(h.denied());
    expect(h.backend.liteUnreadNotifications).not.toHaveBeenCalled();
  });
});
