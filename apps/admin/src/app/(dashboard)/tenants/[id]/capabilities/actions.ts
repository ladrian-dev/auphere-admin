"use server";

import { revalidatePath } from "next/cache";

import { BackendError, backend, type CapabilityKind, type CapabilityModeChange } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

type Result = { ok: true } | { ok: false; error: string };

const ERRORS: Record<string, string> = {
  unknown_capability: "Esa habilidad ya no existe.",
  skill_not_published: "Esa habilidad todavía no está publicada en este entorno.",
  mode_not_supported: "Ese modo no se puede elegir.",
};

/** Spec 037: one capability, one change, signed by the operator. */
export async function setCapabilityAction(input: {
  tenantId: string;
  key: string;
  kind: CapabilityKind;
  enabled?: boolean;
  mode?: CapabilityModeChange;
  agent?: string;
}): Promise<Result> {
  const operator = await requireOperator();
  try {
    await backend.setCapability(
      input.tenantId,
      { key: input.key, kind: input.kind, enabled: input.enabled, mode: input.mode },
      operator.id,
      input.agent,
    );
    revalidatePath(`/tenants/${input.tenantId}`, "layout");
    return { ok: true };
  } catch (err) {
    if (err instanceof BackendError) {
      const detail = (err.body as { detail?: unknown } | null)?.detail;
      return { ok: false, error: (typeof detail === "string" && ERRORS[detail]) || `Error ${err.status}` };
    }
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}
