"use server";

/**
 * Spec 052: invitar, reenviar y revocar al propietario de un partner.
 *
 * El operador de la sesión firma cada acción. Si la respuesta lleva el enlace,
 * viaja del servidor al cliente esta vez y no se guarda en ningún sitio: ni en la
 * URL, ni en una cookie, ni en el navegador (R6.6).
 *
 * **Ninguna revalida.** Revalidar aquí vuelve a pintar la página en la misma
 * respuesta, y si esa lectura falla la pestaña se desmonta con el único ejemplar
 * del enlace dentro. Refresca el cliente, cuando no queda ningún enlace en
 * pantalla (`owner-invitation-panel.tsx`).
 */

import { toFailure, type Result } from "@/lib/action-result";
import {
  BackendError,
  backend,
  type OwnerInvitationResult,
  type OwnerInvitationRevoked,
} from "@/lib/backend";
import { requireOperator } from "@/lib/session";

import { INVITATION_WORDS, OPERATOR_DISABLED, UNKNOWN_OUTCOME } from "./messages";

function failure(err: unknown): Result<never> {
  // Sin respuesta, o un error de la API: no se sabe si se hizo.
  if (!(err instanceof BackendError) || err.status >= 500) {
    return { ok: false, code: "unknown_outcome", error: UNKNOWN_OUTCOME };
  }
  return toFailure(err, INVITATION_WORDS);
}

export async function inviteOwnerAction(
  partnerId: string,
  email: string,
): Promise<Result<OwnerInvitationResult>> {
  const operator = await requireOperator();
  if (operator.access !== "ok") return { ok: false, error: OPERATOR_DISABLED };
  try {
    const data = await backend.inviteOwner(partnerId, email, operator.id);
    if (!data) return { ok: false, code: "unknown_outcome", error: UNKNOWN_OUTCOME };
    return { ok: true, data };
  } catch (err) {
    return failure(err);
  }
}

export async function resendOwnerInvitationAction(
  partnerId: string,
  invitationId: string,
): Promise<Result<OwnerInvitationResult>> {
  const operator = await requireOperator();
  if (operator.access !== "ok") return { ok: false, error: OPERATOR_DISABLED };
  try {
    const data = await backend.resendOwnerInvitation(partnerId, invitationId, operator.id);
    if (!data) return { ok: false, code: "unknown_outcome", error: UNKNOWN_OUTCOME };
    return { ok: true, data };
  } catch (err) {
    return failure(err);
  }
}

export async function revokeOwnerInvitationAction(
  partnerId: string,
  invitationId: string,
): Promise<Result<OwnerInvitationRevoked>> {
  const operator = await requireOperator();
  if (operator.access !== "ok") return { ok: false, error: OPERATOR_DISABLED };
  try {
    const data = await backend.revokeOwnerInvitation(partnerId, invitationId, operator.id);
    if (!data) return { ok: false, code: "unknown_outcome", error: UNKNOWN_OUTCOME };
    return { ok: true, data };
  } catch (err) {
    return failure(err);
  }
}
