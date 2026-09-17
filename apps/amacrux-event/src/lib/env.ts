/** Configuración pública (prefijo NEXT_PUBLIC_). Sin secretos. */

export type AnalyticsProvider = "noop" | "console" | "plausible";

export function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3120").replace(/\/$/, "");
}

export function isDemoModeFlag(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_MODE === "true";
}

export function analyticsProvider(): AnalyticsProvider {
  const v = process.env.NEXT_PUBLIC_ANALYTICS;
  return v === "console" || v === "plausible" ? v : "noop";
}

export function plausibleDomain(): string | undefined {
  const v = process.env.NEXT_PUBLIC_PLAUSIBLE_DOMAIN;
  return v && v.length > 0 ? v : undefined;
}
