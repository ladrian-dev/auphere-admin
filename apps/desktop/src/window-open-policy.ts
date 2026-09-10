/**
 * Qué hace la cáscara con `window.open` y `target="_blank"` — Requisitos 12.7 y 14.1.
 *
 * La consola abre ventanas en varios sitios (consentimiento de herramientas,
 * documentos, diagnósticos). Dentro de la cáscara **nunca** se abre una ventana
 * de la aplicación sin barra de direcciones: lo que sea `https:` (o el propio
 * origen de la consola) va al navegador del sistema, y todo lo demás se
 * deniega. Función pura para poder probarla sin Electron.
 */

export type WindowOpenDecision = { action: "open_external"; url: string } | { action: "deny" };

export function decideWindowOpen(url: string, consoleOrigin: string): WindowOpenDecision {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { action: "deny" };
  }
  if (parsed.origin === consoleOrigin) return { action: "open_external", url: parsed.toString() };
  if (parsed.protocol === "https:") return { action: "open_external", url: parsed.toString() };
  return { action: "deny" };
}

/** Navegaciones de la vista de la consola: solo dentro de su origen. */
export function navigationAllowed(url: string, consoleOrigin: string): boolean {
  try {
    return new URL(url).origin === consoleOrigin;
  } catch {
    return false;
  }
}
