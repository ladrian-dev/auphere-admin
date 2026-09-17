/**
 * Configuración de servidor. Solo se importa desde Route Handlers
 * (src/app/api/**). El script check-no-env-leaks.mjs y el test de no
 * acoplamiento fallan si estos nombres aparecen en cualquier otro sitio.
 */
import { isDemoModeFlag } from "./env";

export type LeadDeliveryConfig =
  | { mode: "demo" }
  | { mode: "misconfigured" }
  | { mode: "live"; apiKey: string; to: string[]; from: string };

export type LeadStorageConfig = { enabled: false } | { enabled: true; url: string; serviceKey: string };

/** Correo: `LEADS_TO` admite varias direcciones separadas por comas (Amacrux y Auphere). */
export function leadDeliveryConfig(env: NodeJS.ProcessEnv = process.env): LeadDeliveryConfig {
  const apiKey = env.RESEND_API_KEY?.trim();
  const to = (env.LEADS_TO ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  const from = env.LEADS_FROM?.trim();
  if (isDemoModeFlag() || !apiKey) return { mode: "demo" };
  if (to.length === 0 || !from) return { mode: "misconfigured" };
  return { mode: "live", apiKey, to, from };
}

/** Base de leads en Supabase (Postgres) vía su API REST. Solo la service role escribe. */
export function leadStorageConfig(env: NodeJS.ProcessEnv = process.env): LeadStorageConfig {
  const url = env.SUPABASE_URL?.trim().replace(/\/+$/, "");
  const serviceKey = env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (isDemoModeFlag() || !url || !serviceKey) return { enabled: false };
  return { enabled: true, url, serviceKey };
}

export type LeadWebhookConfig = { enabled: false } | { enabled: true; url: string; secret?: string };

/** Copia de cada lead a un webhook (p. ej. n8n → Google Sheets). Best-effort: nunca bloquea el envío. */
export function leadWebhookConfig(env: NodeJS.ProcessEnv = process.env): LeadWebhookConfig {
  const url = env.LEADS_WEBHOOK_URL?.trim();
  if (isDemoModeFlag() || !url || !/^https:\/\//.test(url)) return { enabled: false };
  const secret = env.LEADS_WEBHOOK_SECRET?.trim();
  return { enabled: true, url, secret: secret || undefined };
}

export type DestinationsMode = "demo" | "live" | "misconfigured";

/** Resumen de destinos: demo si no hay ninguno; live si hay base o correo; misconfigured si el correo está a medias y no hay base. */
export function destinationsMode(storage: LeadStorageConfig, delivery: LeadDeliveryConfig): DestinationsMode {
  if (storage.enabled || delivery.mode === "live") return "live";
  if (delivery.mode === "misconfigured") return "misconfigured";
  return "demo";
}
