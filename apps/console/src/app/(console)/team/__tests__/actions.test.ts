import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { inviteAction, revokeInvitationAction, changeRoleAction, changeStatusAction, removeMemberAction } = await import("../actions");

describe("team actions (spec 016, R8)", () => {
  it("admin manages the roster", async () => {
    h.setRole("admin");
    h.backend.invite.mockResolvedValueOnce({ id: "i1" });
    expect(await inviteAction({ email: "a@b.co", role: "builder" })).toEqual({ ok: true, data: { id: "i1" } });
    expect(await revokeInvitationAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(await changeRoleAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", role: "analyst" })).toMatchObject({ ok: true });
    expect(h.backend.changeMemberRole).toHaveBeenCalledWith("7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", "analyst");
    expect(await changeStatusAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", status: "suspended" })).toMatchObject({ ok: true });
    expect(await removeMemberAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/team");
  });
  it("builder (team:read only): every write is denied before any call", async () => {
    h.setRole("builder");
    const fns = [h.backend.invite, h.backend.revokeInvitation, h.backend.changeMemberRole, h.backend.changeMemberStatus, h.backend.removeMember];
    for (const fn of fns) fn.mockClear();
    expect(await inviteAction({ email: "a@b.co", role: "builder" })).toEqual(h.denied());
    expect(await revokeInvitationAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    expect(await changeRoleAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", role: "analyst" })).toEqual(h.denied());
    expect(await changeStatusAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", status: "active" })).toEqual(h.denied());
    expect(await removeMemberAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    for (const fn of fns) expect(fn).not.toHaveBeenCalled();
  });
});
