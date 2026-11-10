import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PartnerInvitation, PartnerMembersOut, PartnerOwnerState } from "@/lib/backend";

import { OwnerNotice } from "../owner-notice";

const owner: PartnerOwnerState = {
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

function team(state: Partial<PartnerOwnerState>, invitations: PartnerInvitation[] = []): PartnerMembersOut {
  return { members: [], invitations, owner: { ...owner, ...state } };
}

describe("OwnerNotice (spec 052, R3.12)", () => {
  it("says nothing when there is an active owner", () => {
    const { container } = render(<OwnerNotice partnerId="p1" team={team({ has_active_owner: true })} />);
    expect(container.textContent).toBe("");
  });

  it("does not claim anything if the team could not be read", () => {
    const { container } = render(<OwnerNotice partnerId="p1" team={null} />);
    expect(container.textContent).toBe("");
  });

  it("says there is no owner, with the link to the team", () => {
    render(<OwnerNotice partnerId="p1" team={team({})} />);
    expect(document.body.textContent).toMatch("Sin propietario activo");
    expect(screen.getByRole("link").getAttribute("href")).toBe("/partners/p1/team");
  });

  it("a live invitation with no send on record says so", () => {
    render(<OwnerNotice partnerId="p1" team={team({}, [invitation])} />);
    expect(document.body.textContent).toMatch("duena@acme.test");
    expect(document.body.textContent).toMatch("no consta el envío");
  });

  it("a sent invitation says it was sent", () => {
    render(
      <OwnerNotice partnerId="p1" team={team({}, [{ ...invitation, last_sent_at: "2026-11-03T19:00:01Z" }])} />,
    );
    expect(document.body.textContent).toMatch(/enviada/);
    expect(document.body.textContent).not.toMatch("no consta el envío");
  });

  it("an expired invitation says it with its date", () => {
    render(
      <OwnerNotice
        partnerId="p1"
        team={team({ expired_email: "vieja@acme.test", expired_at: "2026-11-01T10:00:00Z" })}
      />,
    );
    expect(document.body.textContent).toMatch("vieja@acme.test");
    expect(document.body.textContent).toMatch("1 de noviembre de 2026");
  });

  it("an invitation that is not Auphere's is not presented as the owner's", () => {
    render(<OwnerNotice partnerId="p1" team={team({}, [{ ...invitation, from_auphere: false, email: "ajena@acme.test" }])} />);
    expect(document.body.textContent).not.toMatch("ajena@acme.test");
  });
});
