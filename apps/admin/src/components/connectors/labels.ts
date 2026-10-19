/**
 * Spec 035: how connectors read in the panel. A connector is anything that
 * is not a messaging channel; WhatsApp and TikTok rows of the catalog carry
 * `provider_meta.channel_only` and live in Canales.
 */
import type { Connector, ConnectorAuthKind, TenantConnectorStatus } from "@/lib/backend";

/** The partner console's names (spec 018 R4.5). */
export const CATEGORY_LABEL: Record<string, string> = {
  booking: "Citas",
  calendar: "Calendario",
  billing: "Cobros",
  catalog: "Catálogo y ventas",
  ecommerce: "Tienda",
  messaging: "Mensajería",
  docs: "Documentos",
  crm: "Clientes",
};

export function categoryName(key: string): string {
  return CATEGORY_LABEL[key] ?? key;
}

export function isChannelOnly(connector: Pick<Connector, "provider_meta">): boolean {
  return (connector.provider_meta as { channel_only?: boolean } | null)?.channel_only === true;
}

export type Tone = "positive" | "warning" | "danger" | "muted";

/** Chatwoot's «Activado / Deshabilitado», plus the states that need someone. */
export function connectorState(status: TenantConnectorStatus | null | undefined): {
  label: string;
  tone: Tone;
  active: boolean;
} {
  switch (status) {
    case "connected":
      return { label: "Activado", tone: "positive", active: true };
    case "partial":
      return { label: "Activado a medias", tone: "warning", active: true };
    case "pending":
      return { label: "Esperando permiso", tone: "warning", active: false };
    case "needs_reauth":
      return { label: "Requiere atención", tone: "danger", active: false };
    case "error":
      return { label: "Con error", tone: "danger", active: false };
    case "paused":
      return { label: "En pausa", tone: "muted", active: false };
    default:
      return { label: "Deshabilitado", tone: "muted", active: false };
  }
}

/** Lower first: what broke, then what waits, then the rest. */
export function urgency(status: TenantConnectorStatus | null | undefined): number {
  switch (status) {
    case "error":
    case "needs_reauth":
      return 0;
    case "pending":
    case "partial":
      return 1;
    case "paused":
      return 2;
    case "connected":
      return 3;
    default:
      return 4;
  }
}

export const AUTH_KIND_HINT: Record<ConnectorAuthKind, string> = {
  oauth_composio: "El dueño aprueba el acceso desde un enlace que le llega por WhatsApp.",
  browser_credentials: "Auphere entra con las credenciales del negocio.",
  webhook_manual: "El operador pega los datos del proveedor en un asistente.",
  api_key: "Clave de API guardada en los secretos de Auphere.",
};
