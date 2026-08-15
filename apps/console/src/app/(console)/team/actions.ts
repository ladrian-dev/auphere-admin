"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type InvitationCreated, type Member } from "@/lib/backend";
import { requirePrincipal } from "@/lib/principal";

const role = z.enum(["owner", "admin", "builder", "analyst", "billing"]);
const id = z.string().uuid();

export async function inviteAction(raw: unknown): Promise<ActionResult<InvitationCreated>> {
  const body = z.object({ email: z.string().email(), role }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).invite(body));
  if (res.ok) revalidatePath("/team");
  return res;
}
export async function revokeInvitationAction(raw: unknown): Promise<ActionResult<null>> {
  const { id: invitationId } = z.object({ id }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).revokeInvitation(invitationId));
  if (res.ok) revalidatePath("/team");
  return res;
}
export async function changeRoleAction(raw: unknown): Promise<ActionResult<Member>> {
  const { id: memberId, role: r } = z.object({ id, role }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).changeMemberRole(memberId, r));
  if (res.ok) revalidatePath("/team");
  return res;
}
export async function changeStatusAction(raw: unknown): Promise<ActionResult<Member>> {
  const { id: memberId, status } = z.object({ id, status: z.enum(["active", "suspended"]) }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).changeMemberStatus(memberId, status));
  if (res.ok) revalidatePath("/team");
  return res;
}
export async function removeMemberAction(raw: unknown): Promise<ActionResult<null>> {
  const { id: memberId } = z.object({ id }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).removeMember(memberId));
  if (res.ok) revalidatePath("/team");
  return res;
}
