"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type InvitationCreated, type LocalExecCeiling, type Member } from "@/lib/backend";
import { requirePrincipal } from "@/lib/principal";

const role = z.enum(["owner", "admin", "builder", "analyst", "billing"]);
const execMode = z.enum(["ask", "always", "never"]);
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


/**
 * El techo de ejecución local del partner (spec 003, R10.1).
 *
 * Vive en Equipo porque es una decisión de **seguridad del equipo**: acota lo
 * que cada persona puede permitirse a sí misma en su propia máquina. Bajarlo
 * tiene efecto en la siguiente invocación; no revoca permisos de argumentos ya
 * concedidos, que se revocan uno a uno desde el puesto de trabajo del cliente.
 */
export async function setLocalExecCeilingAction(raw: unknown): Promise<ActionResult<LocalExecCeiling>> {
  const { ceiling } = z.object({ ceiling: execMode }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).setLocalExecCeiling(ceiling));
  if (res.ok) revalidatePath("/team");
  return res;
}
