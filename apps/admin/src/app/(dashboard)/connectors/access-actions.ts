"use server";

import { revalidatePath } from "next/cache";

import { BackendError } from "@/lib/backend";
import {
  type AccessImpact,
  connectorAccessBackend,
  type PartnerConnectorState,
} from "@/lib/backend-connector-access";
import { requireOperator } from "@/lib/session";

/**
 * Spec 060: las dos vistas (la ficha del partner y la del conector) guardan por
 * aquí. Un `409 confirm_required` vuelve con los afectados para que la pantalla
 * los enseñe antes de confirmar; un `409 partner_default_connector`, con los
 * partners que primero tienen que cambiar su conector por defecto.
 */
export type AccessOutcome =
  | { ok: true }
  | { ok: false; code: "confirm_required"; impact: AccessImpact }
  | { ok: false; code: "partner_default_connector"; partners: { id: string; name: string }[] }
  | { ok: false; code: string; error: string };

const WORDS: Record<string, string> = {
  reason_required: "Hace falta un motivo de al menos 3 caracteres.",
  connector_not_managed: "Los canales y Google Calendar no se gestionan aquí.",
  connector_not_found: "Ese conector ya no está en el catálogo.",
  partner_not_found: "Ese partner ya no existe.",
};

function outcome(err: unknown): AccessOutcome {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? (err.body as { detail: unknown }).detail
        : null;
    if (detail && typeof detail === "object" && "code" in detail) {
      const d = detail as Record<string, unknown>;
      const code = String(d.code);
      if (code === "confirm_required") {
        return {
          ok: false,
          code,
          impact: { affected: d.affected as AccessImpact["affected"], totals: d.totals as AccessImpact["totals"] },
        };
      }
      if (code === "partner_default_connector") {
        return { ok: false, code, partners: d.partners as { id: string; name: string }[] };
      }
      return { ok: false, code, error: WORDS[code] ?? code };
    }
    return { ok: false, code: "http", error: `La API respondió ${err.status}.` };
  }
  return { ok: false, code: "error", error: err instanceof Error ? err.message : String(err) };
}

function refresh(slug: string, partnerId?: string) {
  revalidatePath(`/connectors/${slug}`);
  revalidatePath("/connectors");
  if (partnerId) revalidatePath(`/partners/${partnerId}`, "layout");
}

export async function setConnectorPartnerStateAction(
  slug: string,
  partnerId: string,
  body: { state: PartnerConnectorState; reason: string; confirm: boolean },
): Promise<AccessOutcome> {
  const operator = await requireOperator();
  try {
    await connectorAccessBackend.setPartnerState(slug, partnerId, body, operator.id);
    refresh(slug, partnerId);
    return { ok: true };
  } catch (err) {
    return outcome(err);
  }
}

export async function setConnectorDefaultAction(
  slug: string,
  body: { enabled: boolean; reason: string; confirm: boolean },
): Promise<AccessOutcome> {
  const operator = await requireOperator();
  try {
    await connectorAccessBackend.setDefault(slug, body, operator.id);
    refresh(slug);
    return { ok: true };
  } catch (err) {
    return outcome(err);
  }
}
