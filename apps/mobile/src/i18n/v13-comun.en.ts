import type { v13ComunEs } from "./v13-comun.es";

/** Spec 069 — lo común del diseño nuevo (estados, toasts, piezas compartidas), English. Every Spanish key must exist here (`tsc` checks it). */
export const v13ComunEn: Record<keyof typeof v13ComunEs, string> = {
  "v13.settings.notices.loading": "Reading your notices…",
  "v13.settings.notices.error": "Your notices couldn't be read.",
};
