/**
 * El updater — spec 001, Requisito 9.2. **Pegamento, como el resto de
 * `electron/`**: lo que decide está en `update-policy.ts` y se prueba sin
 * Electron; aquí sólo se averigua el estado real y se ejecuta la decisión.
 *
 * Dos cosas que no son obvias y por eso están escritas:
 *
 * * **La aplicación comprueba su propia firma antes de escuchar al canal.**
 *   `app.isPackaged` sólo dice que no es `npm start`; no dice quién lo firmó.
 *   Se ejecuta `codesign --verify --test-requirement` contra nuestro Team ID una
 *   vez, al arrancar, y el resultado se guarda. Una copia recompilada por otro
 *   no llega siquiera a pedirle una versión al servidor.
 * * **Windows devuelve `unpackaged` a propósito.** Esa mitad no está portada
 *   (la contención no lo está), así que no se empaqueta y no se actualiza.
 *   Decirlo aquí es más honesto que un `if` escondido en el empaquetador.
 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { app } from "electron";

import {
  type Activity,
  type BuildKind,
  decideUpdate,
  developerIdRequirement,
  feedIsAcceptable,
} from "../update-policy.js";

const run = promisify(execFile);

/** El equipo que firma. Si cambia, cambia el `designated requirement` y macOS
 *  trata la app como otra distinta — ver la nota de migración del proyecto. */
export const TEAM_ID = "CBSWMG766P";

/** De dónde vienen las actualizaciones. Sobreescribible sólo para staging. */
export const FEED_URL = process.env.AUPHERE_UPDATE_FEED ?? "https://updates.auphere.com/desktop";

/** Cuánto se espera entre comprobaciones. Cuatro horas: esto no es un chat. */
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000;

/**
 * Qué clase de binario es éste. Una sola llamada a `codesign`, al arrancar.
 * Si `codesign` falla por lo que sea, la respuesta es `adhoc` — es decir, **no
 * se actualiza**. Fallar cerrado también cuando la comprobación no se pudo
 * hacer: «no pude verificar» no es «está bien».
 */
export async function detectBuildKind(): Promise<BuildKind> {
  if (!app.isPackaged) return "unpackaged";
  if (process.platform !== "darwin") return "unpackaged";
  try {
    await run("/usr/bin/codesign", [
      "--verify",
      `--test-requirement==${developerIdRequirement(TEAM_ID)}`,
      app.getPath("exe"),
    ]);
    return "signed";
  } catch {
    return "adhoc";
  }
}

export type UpdaterPorts = {
  /** Qué está pasando ahora en la máquina. Lo aporta `main.ts`. */
  readActivity: () => Activity;
  /** Para dejar rastro de por qué no se actualizó, que es lo que se pregunta. */
  log: (message: string, detail?: Record<string, unknown>) => void;
};

/**
 * Arranca el ciclo. Devuelve una función para pararlo, porque una prueba que no
 * pueda parar un `setInterval` deja el proceso colgado.
 */
export async function startUpdater(ports: UpdaterPorts): Promise<() => void> {
  const build = await detectBuildKind();

  if (!feedIsAcceptable(FEED_URL)) {
    ports.log("updater apagado: el canal no es aceptable", { feed: FEED_URL });
    return () => {};
  }

  const first = decideUpdate({ build, activity: ports.readActivity(), downloaded: null, available: null });
  if (first.kind === "do-not-check") {
    // No se enseña nada en pantalla: una aplicación que no puede actualizarse
    // sola no tiene un botón apagado que lo explique (constitución §V). Queda
    // en el registro, que es donde alguien va a buscarlo.
    ports.log("updater apagado", { reason: first.reason });
    return () => {};
  }

  const { autoUpdater } = await import("electron-updater");
  autoUpdater.autoDownload = true;
  // Nunca reinicia por su cuenta: se instala al salir, y quien sale es la
  // persona. `decideUpdate` vuelve a decidirlo justo antes de cerrar.
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.setFeedURL({ provider: "generic", url: FEED_URL });

  let downloaded: { version: string } | null = null;

  autoUpdater.on("update-downloaded", (info: { version: string }) => {
    downloaded = { version: info.version };
    ports.log("actualización descargada", { version: info.version });
  });
  autoUpdater.on("error", (error: Error) => {
    ports.log("el updater falló", { error: error.message });
  });

  const tick = (): void => {
    const decision = decideUpdate({
      build,
      activity: ports.readActivity(),
      downloaded,
      available: null,
    });
    if (decision.kind === "check") void autoUpdater.checkForUpdates();
  };

  app.on("before-quit", () => {
    const decision = decideUpdate({
      build,
      activity: ports.readActivity(),
      downloaded,
      available: null,
    });
    if (decision.kind === "install-on-quit") {
      ports.log("instalando al salir", { version: decision.version });
      autoUpdater.quitAndInstall(true, false);
    } else if (decision.kind === "wait") {
      ports.log("no se instala: hay trabajo vivo", { version: decision.version });
    }
  });

  tick();
  const timer = setInterval(tick, CHECK_INTERVAL_MS);
  return () => clearInterval(timer);
}
