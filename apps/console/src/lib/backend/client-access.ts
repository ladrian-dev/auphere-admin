import type { Call } from "../backend";

/**
 * Spec 056 (Requisito 3, D3, D4; `contracts/api.md`) — la pestaña «Acceso» de un
 * cliente: encender su consola, elegir sus módulos e invitar o revocar a sus
 * personas. La API llama a los mismos servicios que el panel de Auphere y exige
 * `client_access:manage` (owner y admin). Ningún cuerpo lleva `partner_id` ni
 * `tenant_id`: el cliente sale del `ref`.
 */

/** Los módulos que se le pueden dar a un cliente (Agentes y Negocio salieron con la spec 056). */
export const ACCESS_MODULES = ["panel", "inbox", "reservas", "usage"] as const;
export type AccessModule = (typeof ACCESS_MODULES)[number];
export type ReservasMode = "services" | "capacity";
export const CAPACITY_KINDS = ["restaurant", "bar", "classes", "tours", "rooms", "spa"] as const;
export type CapacityKind = (typeof CAPACITY_KINDS)[number];

export type ClientAccessMember = {
  id: string;
  kind: "member" | "invitation";
  email: string;
  name: string | null;
  /** `active` (persona) · `pending`, `expired`, `revoked` (invitación) · `revoked` (persona). */
  status: string;
  since?: string | null;
  expires_at?: string | null;
};

export type ClientAccessReservas = {
  mode: ReservasMode;
  capacity_kind: CapacityKind | null;
  /** Reservas futuras vivas: cambiar de modo las cancela. */
  live_future: number;
  agents_pending_promotion: { agent_id: string; name: string; version: number }[];
  agents_with_other_calendar?: { agent_id: string; name: string }[];
};

/** `GET /console/clients/{ref}/client-access`: la forma del panel sin `partner`. */
export type ClientAccess = {
  eligible: boolean;
  ineligible_reason: string | null;
  whatsapp_connected: boolean;
  enabled: boolean;
  modules: string[];
  members: ClientAccessMember[];
  reservas?: ClientAccessReservas | null;
};

export type ClientAccessIn = {
  enabled: boolean;
  modules: AccessModule[];
  reservas?: { mode: ReservasMode; capacity_kind?: CapacityKind; on_live?: "cancel_and_notify" };
};

/** Lo que vuelve al invitar o reenviar: el enlace, una sola vez. */
export type ClientInvitation = {
  id: string;
  email: string;
  status: string;
  expires_at: string;
  accept_path: string;
  accept_url: string;
  email_sent: boolean;
};

export function clientAccessApi(call: Call) {
  const base = (ref: string) => `/console/clients/${encodeURIComponent(ref)}`;
  return {
    clientAccess: (ref: string) => call<ClientAccess>(`${base(ref)}/client-access`),
    setClientAccess: (ref: string, body: ClientAccessIn) =>
      call<ClientAccess>(`${base(ref)}/client-access`, { method: "PUT", body }),
    inviteClientMember: (ref: string, body: { email: string; name?: string | null }) =>
      call<ClientInvitation>(`${base(ref)}/client-members`, { method: "POST", body }),
    resendClientMember: (ref: string, memberId: string) =>
      call<ClientInvitation>(`${base(ref)}/client-members/${encodeURIComponent(memberId)}/resend`, { method: "POST" }),
    revokeClientMember: (ref: string, memberId: string) =>
      call<{ member: ClientAccessMember }>(`${base(ref)}/client-members/${encodeURIComponent(memberId)}/revoke`, {
        method: "POST",
      }),
  };
}
