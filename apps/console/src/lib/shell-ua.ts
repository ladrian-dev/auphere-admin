/**
 * La parte pura de `lib/shell.ts`: sin `server-only`, para poder probarla.
 * La cáscara de escritorio añade `AuphereDesktop/<versión>` a su agente de
 * usuario, y **eso es todo lo que la consola sabe de ella** (spec 002, R12.7).
 */
export const DESKTOP_SHELL_UA_TOKEN = "AuphereDesktop/";

export function isDesktopShellUserAgent(userAgent: string | null | undefined): boolean {
  return typeof userAgent === "string" && userAgent.includes(DESKTOP_SHELL_UA_TOKEN);
}
