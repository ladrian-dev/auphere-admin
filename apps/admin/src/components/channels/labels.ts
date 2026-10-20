/**
 * Spec 035: how channels read in the panel — pure, shared by the client's
 * Canales tab, the wizard and the global view.
 */
import type { ChannelAvailability } from "@/lib/backend";

export const CHANNEL_NAME: Record<string, string> = {
  whatsapp: "WhatsApp",
  tiktok: "TikTok",
  instagram: "Instagram",
  telegram: "Telegram",
  x: "X",
  threads: "Threads",
  messenger: "Messenger",
  email: "Correo",
  web: "Web",
};

export const CHANNEL_STATUS: Record<string, { label: string; tone: "positive" | "warning" | "danger" | "muted" }> = {
  active: { label: "Activo", tone: "positive" },
  paused: { label: "En pausa", tone: "warning" },
  degraded: { label: "Con problemas", tone: "danger" },
  disconnected: { label: "Desconectado", tone: "muted" },
};

export const ROLE_LABEL: Record<string, string> = {
  agent: "Línea del agente",
  notifications: "Línea de avisos",
};

/** Whether a catalog entry can be started from the panel (constitution §V 1.1.0). */
export function canStart(availability: ChannelAvailability): boolean {
  return availability === "available" || availability === "beta";
}

export const AVAILABILITY_LABEL: Record<ChannelAvailability, string | null> = {
  available: null,
  beta: "Beta",
  pending: "Pendiente",
  coming_soon: "Próximamente",
};
