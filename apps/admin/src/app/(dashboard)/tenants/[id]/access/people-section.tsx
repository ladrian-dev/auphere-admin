"use client";

import { useState } from "react";

import type { ClientInvitationOut, ClientMemberOut } from "@/lib/backend";

import { InvitationNotices } from "./invitation-notices";
import { InviteForm } from "./invite-form";
import { MembersList } from "./members-list";

/**
 * Spec 030 (R1.4 to R1.9): inviting and managing a client's people. The notices
 * live here, above both, because a link can be killed from either one: inviting
 * or resending retires the previous link of that address, and so does revoking.
 * One notice per address means the page never offers a link that no longer opens.
 */
export function PeopleSection({
  tenantId,
  disabled,
  members,
}: {
  tenantId: string;
  disabled: boolean;
  members: ClientMemberOut[];
}) {
  const [notices, setNotices] = useState<ClientInvitationOut[]>([]);

  function show(result: ClientInvitationOut) {
    setNotices((current) => [result, ...current.filter((n) => n.email !== result.email)]);
  }

  function forget(email: string) {
    setNotices((current) => current.filter((n) => n.email !== email));
  }

  return (
    <>
      <InviteForm tenantId={tenantId} disabled={disabled} onInvited={show} />
      <InvitationNotices notices={notices} onDismiss={forget} />
      <MembersList tenantId={tenantId} members={members} onResent={show} onRevoked={forget} />
    </>
  );
}
