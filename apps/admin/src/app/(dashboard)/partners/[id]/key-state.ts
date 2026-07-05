import type { PartnerApiKeyOut } from "@/lib/backend";

/**
 * Derived lifecycle state of a partner API key. The backend stores raw
 * timestamps; the panel classifies them so every surface (tabla de keys,
 * editor de origins) habla el mismo idioma:
 *
 * - ``active``  — usable.
 * - ``grace``   — rotada: revocada pero sigue autenticando hasta
 *                 ``grace_expires_at`` (deploy sin downtime).
 * - ``revoked`` — muerta (revoke inmediato o gracia vencida).
 * - ``expired`` — pasó su ``expires_at`` sin haber sido revocada.
 */
export type PartnerKeyState = "active" | "grace" | "revoked" | "expired";

export function partnerKeyState(key: PartnerApiKeyOut): PartnerKeyState {
  const now = Date.now();
  if (key.revoked_at) {
    if (
      key.grace_expires_at &&
      new Date(key.grace_expires_at).getTime() > now
    ) {
      return "grace";
    }
    return "revoked";
  }
  if (key.expires_at && new Date(key.expires_at).getTime() <= now) {
    return "expired";
  }
  return "active";
}

export const KEY_STATE_LABEL: Record<PartnerKeyState, string> = {
  active: "Activa",
  grace: "En gracia",
  revoked: "Revocada",
  expired: "Expirada",
};

export const KEY_STATE_TONE: Record<
  PartnerKeyState,
  "positive" | "warning" | "danger" | "muted"
> = {
  active: "positive",
  grace: "warning",
  revoked: "danger",
  expired: "muted",
};
