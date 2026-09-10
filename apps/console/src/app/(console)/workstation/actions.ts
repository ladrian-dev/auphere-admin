"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { MachineClientOut, MachineOut, PairingCodeOut } from "@/lib/backend/workstation";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Server Actions del puesto de trabajo a nivel de partner (spec 002).
 *
 * Todas piden `workstation:pair`: emparejar la propia máquina, vincular sus
 * clientes y archivarla es reclamar lo que es tuyo, y lo tiene quien usa a
 * los teammates (owner · admin · builder). Ver una máquina ajena o archivar
 * cualquiera lo decide la RLS con `workstation:write`; aquí solo se da un 403
 * honesto antes del viaje. Ninguna acción acepta un `workdir`: la consola no
 * teclea rutas — las declara la máquina por el puente (R7.1).
 */

const id = z.string().uuid();
const ref = z.string().min(1).max(255);

function forbidden<T>(): ActionResult<T> {
  return { ok: false, status: 403, message: "forbidden" };
}

export async function issuePairingCodeAction(): Promise<ActionResult<PairingCodeOut>> {
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:pair")) return forbidden();
  return run(() => backendFor(principal).issuePairingCode());
}

export async function renameMachineAction(raw: unknown): Promise<ActionResult<MachineOut>> {
  const body = z.object({ id, display_name: z.string().trim().min(1).max(120) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:pair")) return forbidden();
  return run(async () => {
    const machine = await backendFor(principal).renameMachine(body.id, body.display_name);
    revalidatePath("/workstation");
    return machine;
  });
}

export async function archiveMachineAction(raw: unknown): Promise<ActionResult<null>> {
  const body = z.object({ id }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:pair")) return forbidden();
  return run(async () => {
    await backendFor(principal).archiveMachine(body.id);
    revalidatePath("/workstation");
    return null;
  });
}

export async function linkClientAction(raw: unknown): Promise<ActionResult<MachineClientOut>> {
  const body = z.object({ id, ref }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:pair")) return forbidden();
  return run(async () => {
    const link = await backendFor(principal).linkClient(body.id, body.ref);
    revalidatePath("/workstation");
    return link;
  });
}

export async function unlinkClientAction(raw: unknown): Promise<ActionResult<null>> {
  const body = z.object({ id, ref }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:pair")) return forbidden();
  return run(async () => {
    await backendFor(principal).unlinkClient(body.id, body.ref);
    revalidatePath("/workstation");
    return null;
  });
}
