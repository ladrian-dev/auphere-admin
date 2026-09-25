/** ES/EN messages of lane `record` — la ficha de cliente (spec 017).
 *  Se esparce en `i18n/messages.ts`. Una clave sin consumidor es huérfana
 *  y la caza `__tests__/no-orphan-keys.test.ts`, así que aquí solo entra
 *  lo que la iteración en curso usa. */
export const recordMessages = {
  // ── navegación de la ficha (R2) ───────────────────────────────────
  "clients.nav.label": { es: "Sección de la ficha", en: "Record section" },
  "clients.nav.group.observe": { es: "Observar", en: "Observe" },
  "clients.nav.group.configure": { es: "Configurar", en: "Configure" },
  "clients.nav.group.connect": { es: "Conectar", en: "Connect" },
  "clients.nav.capabilities": { es: "Capacidades", en: "Capabilities" },
  "clients.nav.integrations": { es: "Integraciones", en: "Integrations" },
  "clients.nav.mark.draft": { es: "cambios sin publicar", en: "unpublished changes" },
  "clients.nav.mark.incident": { es: "incidencia", en: "incident" },
  "clients.nav.suffix.draft": { es: "sin publicar", en: "unpublished" },
  "clients.nav.suffix.incident": { es: "incidencia", en: "incident" },
} as const;
