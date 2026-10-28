import type { ConsoleVersion, Me } from "@/lib/backend";

/**
 * Spec 047 (R55.2) — qué consola ve un partner.
 *
 * Solo `"v2"` abre la nueva, que desde la migración 0204 es la de todos los
 * partners (ya no se activa uno a uno desde el panel). `"v1"`, la ausencia del
 * campo (una API de antes) o un valor que esta consola no conoce pintan la de
 * antes. Lo que no se sabe con certeza nunca enseña la consola nueva.
 */
export function resolveConsoleVersion(me: Pick<Me, "console_version"> | null | undefined): ConsoleVersion {
  return me?.console_version === "v2" ? "v2" : "v1";
}

/** El menú plegado se recuerda por navegador; el `layout` lo lee para pintarlo sin salto. */
export const NAV_COOKIE = "nexus-console.nav";
export const NAV_COLLAPSED = "collapsed";
