import "server-only";

import { headers } from "next/headers";

import { isDesktopShellUserAgent } from "./shell-ua";

/**
 * ¿Está cargando la consola la aplicación de escritorio? — spec 002, R12.7.
 *
 * Se usa en **un solo sitio**: el control de conectar canales de Meta, que
 * dentro de la aplicación no funciona (la ventana emergente de Meta no vuelve)
 * y se sustituye por «continúa en el navegador». `shell-detect.test.ts` afirma
 * que este módulo se importa exactamente una vez fuera de aquí: la segunda
 * bifurcación exige su propia spec.
 */
export async function isDesktopShell(): Promise<boolean> {
  const h = await headers();
  return isDesktopShellUserAgent(h.get("user-agent"));
}

export { DESKTOP_SHELL_UA_TOKEN, isDesktopShellUserAgent } from "./shell-ua";
