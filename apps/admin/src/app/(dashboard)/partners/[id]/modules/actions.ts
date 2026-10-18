"use server";

import { revalidatePath } from "next/cache";

import { BackendError, backend, type PartnerAccessOut, type PartnerModule } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

import { ACCESS_ERRORS } from "./messages";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function toError(err: unknown): string {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? (err.body as { detail: unknown }).detail
        : null;
    if (detail && typeof detail === "object" && "code" in detail) {
      const code = String((detail as { code: unknown }).code);
      return ACCESS_ERRORS[code] ?? code;
    }
    if (typeof detail === "string") return detail;
    return `Error ${err.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}

/** Spec 032: the operator of the panel session signs the change. */
export async function setPartnerAccessAction(
  partnerId: string,
  body: { console_enabled: boolean; modules: PartnerModule[] },
): Promise<Result<PartnerAccessOut>> {
  const operator = await requireOperator();
  try {
    const data = await backend.setPartnerAccess(partnerId, body, operator.id);
    revalidatePath(`/partners/${partnerId}`, "layout");
    if (!data) return { ok: false, error: "Respuesta vacía del backend" };
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}
