/**
 * Tipos puros de la página de cada canal, de su menú ⋯ y del enlace del dueño
 * por agente (spec 047, historias 10 y 11; T111, T112, T114 y T115). Reflejan
 * `api/console/channel_config.py` y `services/channel_config.py`
 * (`contracts/console-api.md` §5). Sin imports con efectos: valen para
 * componentes de cliente y para los tests. El cliente de la API es
 * `./channel-config.ts`.
 *
 * Ninguna respuesta lleva mensajes de clientes finales ni costes.
 */

import type { MetaSocialOffer } from "./channels";

/** A quién responde el agente en este número (32.1): sin decidir, solo el equipo o todos. */
export type AudienceMode = "unset" | "team_only" | "everyone";
/** Por dónde se avisa a una persona cuando el agente escala (33.1). */
export type RecipientVia = "whatsapp" | "email" | "inbox";

export type Recipient = {
  name: string;
  via: RecipientVia | string;
  phone_e164?: string | null;
  email?: string | null;
  /** Bandeja: una persona concreta del cliente, o nulo para todas. */
  client_user_id?: string | null;
};

/** Lo que se guarda (sin `notify_from`, que es de solo lectura). */
export type ChannelConfigIn = {
  audience: { mode: AudienceMode; test_numbers: string[]; exceptions: string[] };
  escalation: { recipients: Recipient[]; summary: boolean };
  wait_message: string | null;
};

export type ChannelConfig = ChannelConfigIn & {
  /** De qué número saldrán los avisos por WhatsApp (33.3): del canal o del de Auphere. */
  notify_from: "channel" | "auphere" | string;
};

/** El estado visible de un canal (`contracts/events.md` §1.2), un solo cálculo en la API. */
export type ChannelVisibleState = { code: string; tone: string; reason: string | null };

/** Una comprobación de la página (32.8): `warn` avisa, `block` impide «A todos». */
export type ChannelCheck = { code: string; ok: boolean; level: "warn" | "block" | string; fix: string | null };

export type ChannelAction = "configure" | "move" | "pause" | "resume" | "disconnect";
export type AgentRef = { id: string; name: string };

/** Un disparador del escalado del agente, en solo lectura (33.5). */
export type ChannelTrigger = string | { custom: string };

/** Spec 050: an alert Meta raised on the account, still active. */
export type WhatsAppAlert = { type: string | null; severity: string | null; status: string | null; at: string | null };

/** Spec 050: what Meta says about a WhatsApp number (webhook and health check). Read only. */
export type WhatsAppAccount = {
  verified_name: string | null;
  name_status: string | null;
  name_decision: string | null;
  requested_name: string | null;
  name_rejection_reason: string | null;
  username: string | null;
  username_status: string | null;
  quality_rating: string | null;
  messaging_limit: string | null;
  account_review: string | null;
  alerts: WhatsAppAlert[];
};

export type ChannelPage = {
  id: string;
  type: string;
  identifier: string;
  status: string;
  problem_reason: string | null;
  visible_state: ChannelVisibleState;
  agent: AgentRef | null;
  config: ChannelConfig;
  /** El agente viene de una plantilla de solo administradores: «A todos» no se puede elegir (32.5). */
  admin_only_template: boolean;
  triggers: ChannelTrigger[];
  checks: ChannelCheck[];
  revision: number;
  /** Hasta cuándo se puede deshacer el último cambio; nulo si ya no. */
  undo_until: string | null;
  /** Los otros agentes del cliente que no son borradores (34.1). */
  move_targets: AgentRef[];
  /** Solo lo que esta persona puede hacer (§V). */
  allowed: ChannelAction[];
  /** Spec 050: la cuenta en Meta de un número de WhatsApp; ausente en los demás. */
  whatsapp?: WhatsAppAccount | null;
};

/** Una fila del historial del canal, con el antes y el después (32.7). */
export type ChannelChange = {
  id: string;
  at: string;
  actor: string;
  /** `console`, `undo`, `connect`… */
  origin: string;
  before: Partial<ChannelConfigIn> | null;
  after: Partial<ChannelConfigIn>;
  undo_until: string | null;
  undone_at: string | null;
};

/** Un número del agente con su estado visible (29.4). */
export type AgentChannel = { id: string; type: string; identifier: string; visible_state: ChannelVisibleState };

export type OwnerLinkMode = "coexistence" | "cloud_api" | "whatsapp_login";

/** El enlace del dueño pendiente: se ve su modo y su caducidad, nunca el enlace (31.7). */
export type PendingOwnerLink = { id: string; mode: OwnerLinkMode | string; expires_at: string };

export type AgentChannels = {
  channels: AgentChannel[];
  pending_link: PendingOwnerLink | null;
  /** Spec 049: Instagram / Messenger this partner may connect, or none. */
  meta_social?: MetaSocialOffer | null;
};

/** El enlace recién creado: la URL va **solo** en esta respuesta (31.1). */
export type OwnerLink = { id: string; url: string; mode: OwnerLinkMode | string; expires_at: string };
