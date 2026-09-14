"use server";

/**
 * Acciones del alta autónoma — spec 006, Requisito 8.2.
 *
 * Reenviar el enlace era lo único de este recorrido que obligaba a abrir una
 * consola dentro de la VPC. Aquí es un botón, y el backend sigue siendo quien
 * decide si la solicitud está viva: esta capa no comprueba nada por su cuenta,
 * sólo traduce el error real (409 si ya no es pendiente) para poder decirlo.
 */

import { revalidatePath } from "next/cache";

import { BackendError, backend } from "@/lib/backend";
import { requireOperator } from "@/lib/session";
import type { SignupRowOut } from "@/lib/backend";

export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

export async function resendSignupAction(
  signupId: string,
): Promise<ActionResult<SignupRowOut | null>> {
  await requireOperator();
  try {
    const data = await backend.resendSignup(signupId);
    revalidatePath("/signups");
    return { ok: true, data };
  } catch (e) {
    if (e instanceof BackendError) {
      const body = e.body as { detail?: string } | null;
      const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${e.status}`;
      // El vocabulario del backend no es el del operador.
      const human =
        detail === "signup_not_pending"
          ? "Esa solicitud ya no está viva: o se completó, o caducó. Quien la pidió tiene que volver a pedirla."
          : detail === "signup_not_found"
            ? "Esa solicitud ya no existe."
            : detail;
      return { ok: false, error: human };
    }
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}
