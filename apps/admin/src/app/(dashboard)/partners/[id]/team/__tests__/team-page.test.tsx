import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PartnerInvitation, PartnerMembersOut } from "@/lib/backend";

const getPartner = vi.fn();
const getPartnerMembers = vi.fn();
vi.mock("@/lib/backend", () => ({
  backend: {
    getPartner: (...a: unknown[]) => getPartner(...a),
    getPartnerMembers: (...a: unknown[]) => getPartnerMembers(...a),
  },
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("../../../_invitation/actions", () => ({
  inviteOwnerAction: vi.fn(),
  resendOwnerInvitationAction: vi.fn(),
  revokeOwnerInvitationAction: vi.fn(),
}));

import PartnerTeamPage from "../page";

const owner: PartnerMembersOut["owner"] = {
  has_active_owner: false,
  can_invite: true,
  can_resend: true,
  block: null,
  expired_email: null,
  expired_at: null,
  suggested_email: null,
};
const invitation: PartnerInvitation = {
  id: "i1",
  email: "duena@acme.test",
  role: "owner",
  expires_at: "2026-11-24T19:00:00Z",
  created_at: "2026-11-03T19:00:00Z",
  last_sent_at: null,
  from_auphere: true,
};

async function page() {
  render(await PartnerTeamPage({ params: Promise.resolve({ id: "p1" }) }));
}

describe("PartnerTeamPage (spec 052)", () => {
  beforeEach(() => {
    getPartner.mockReset();
    getPartnerMembers.mockReset();
    getPartner.mockResolvedValue({ id: "p1", name: "Acme" });
  });

  it("does not promise an invitation that does not exist", async () => {
    getPartnerMembers.mockResolvedValue({ members: [], invitations: [], owner });
    await page();
    const empty = screen.getByText("Nadie ha entrado todavía").parentElement as HTMLElement;
    expect(empty.textContent).not.toMatch(/Cuando el partner acepte su invitación/);
    expect(empty.textContent).toMatch(/ninguna viva/);
  });

  it("says who it is waiting for when there is an invitation", async () => {
    getPartnerMembers.mockResolvedValue({ members: [], invitations: [invitation], owner: { ...owner, can_invite: false } });
    await page();
    expect(screen.getByText("Cuando duena@acme.test acepte la invitación aparecerá aquí.")).toBeTruthy();
  });

  it("shows other people's invitations as today, with no actions, and never says the links were sent", async () => {
    getPartnerMembers.mockResolvedValue({
      members: [],
      invitations: [{ ...invitation, id: "i2", email: "ajena@acme.test", role: "admin", from_auphere: false }],
      owner,
    });
    await page();
    const section = screen.getByRole("region", { name: "Invitaciones pendientes" });
    expect(within(section).getByText("ajena@acme.test")).toBeTruthy();
    expect(within(section).queryByRole("button")).toBeNull();
    expect(section.textContent).not.toMatch(/Enlaces enviados/);
    expect(document.body.textContent).not.toMatch(/Enlaces enviados/);
  });

  it("if the team cannot be read it says so", async () => {
    getPartnerMembers.mockRejectedValue(new Error("down"));
    await page();
    expect(screen.getByText("No se pudo leer el equipo")).toBeTruthy();
  });
});
