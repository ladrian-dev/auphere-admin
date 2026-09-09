"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { ExecutableOut } from "@/lib/backend/workstation";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Server Actions del lane `workstation`.
 *
 * Las escrituras piden `workstation:write`, que el rol *builder* **no** tiene:
 * añadir un ejecutable es una decisión de seguridad, no de configuración. El
 * patrón se repite en el backend, así que saltarse esta comprobación no
 * abriría nada — pero fallar aquí da un 403 honesto en vez de un viaje.
 */

const ref = z.string().min(1).max(255);
/** El mismo patrón que el CHECK de la base y el del gate: sin rutas ni shell. */
const executableName = z.string().regex(/^[A-Za-z0-9._+-]{1,128}$/);
const id = z.string().uuid();

function forbidden<T>(): ActionResult<T> {
  return { ok: false, status: 403, message: "forbidden" };
}

const workstationPath = (r: string) => `/clients/${encodeURIComponent(r)}/workstation`;

export async function addExecutableAction(raw: unknown): Promise<ActionResult<ExecutableOut>> {
  const body = z.object({ ref, executable: executableName }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:write")) return forbidden();
  return run(async () => {
    const created = await backendFor(principal).addExecutable(body.ref, body.executable);
    revalidatePath(workstationPath(body.ref));
    return created;
  });
}

export async function archiveExecutableAction(raw: unknown): Promise<ActionResult<null>> {
  const body = z.object({ ref, id }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:write")) return forbidden();
  return run(async () => {
    await backendFor(principal).archiveExecutable(body.ref, body.id);
    revalidatePath(workstationPath(body.ref));
    return null;
  });
}
