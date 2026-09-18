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

/**
 * Lo que la pantalla puede decir de la actualización — spec 010, R6.1 y R6.3.
 *
 * `esperando_trabajo` existía en el tipo de la barra desde la spec 008 y **no
 * se pintaba nunca**, porque nadie lo emitía. Ese es exactamente el bug: el
 * ciclo entero funcionaba y su resultado sólo llegaba al registro.
 */
export type UpdateState =
  | { state: "idle" }
  | { state: "descargando"; version: string }
  | { state: "lista"; version: string }
  | { state: "esperando_trabajo"; version: string };

export type UpdaterPorts = {
  /** Qué está pasando ahora en la máquina. Lo aporta `main.ts`. */
  readActivity: () => Activity;
  /** Para dejar rastro de por qué no se actualizó, que es lo que se pregunta. */
  log: (message: string, detail?: Record<string, unknown>) => void;
  /**
   * Cómo se lo cuenta a la persona. Sin esto, `log` era el único destino — y
   * nadie lee el registro de una aplicación de escritorio.
   */
  announce: (state: UpdateState) => void;
};

/**
 * Lo que el ciclo devuelve.
 *
 * `stop` existe porque una prueba que no pueda parar un `setInterval` deja el
 * proceso colgado. `check` entra con la spec 010: el menú tiene una orden
 * «Buscar actualizaciones» (R6.5), y sin esto la única forma de comprobar el
 * canal era esperar al siguiente latido.
 */
export type UpdaterHandle = {
  stop: () => void;
  check: () => void;
  /**
   * Instalar **ahora**, porque la persona lo pidió (R6.2). Devuelve `busy`
   * cuando hay trabajo vivo: no instala y lo dice, en vez de callar o de
   * llevarse por delante una decisión sin tomar (R6.3).
   */
  install: () => { ok: true } | { error: "busy" | "none" };
};

export async function startUpdater(ports: UpdaterPorts): Promise<UpdaterHandle> {
  const build = await detectBuildKind();

  if (!feedIsAcceptable(FEED_URL)) {
    ports.log("updater apagado: el canal no es aceptable", { feed: FEED_URL });
    return {
      stop: () => {},
      check: () => ports.log("el canal no es aceptable", { feed: FEED_URL }),
      install: () => ({ error: "none" }),
    };
  }

  const first = decideUpdate({ build, activity: ports.readActivity(), downloaded: null, available: null });
  if (first.kind === "do-not-check") {
    // No se enseña nada en pantalla: una aplicación que no puede actualizarse
    // sola no tiene un botón apagado que lo explique (constitución §V). Queda
    // en el registro, que es donde alguien va a buscarlo.
    ports.log("updater apagado", { reason: first.reason });
    // Sin canal no hay nada que comprobar, y decirlo es más honesto que un
    // botón que no hace nada (§V).
    return {
      stop: () => {},
      check: () => ports.log("no hay canal que comprobar", {}),
      install: () => ({ error: "none" }),
    };
  }

  // **Por `default`, y no desestructurando el espacio de nombres.**
  //
  // `electron-updater` es CommonJS y expone `autoUpdater` con un getter
  // perezoso (`out/main.js:78`). Node construye las exportaciones nombradas de
  // un CJS importado desde ESM con `cjs-module-lexer`, que es un analizador
  // **estático** y no reconoce esa forma: el desestructurado directo daba
  // `undefined` y la línea siguiente lanzaba un `TypeError`. Es lo que dejó a
  // v0.1.0 y v0.1.1 sin comprobar el canal ni una vez.
  //
  // El `?? updaterModule` no es defensa por si acaso: si una versión futura
  // publica ESM, el valor pasa a estar en el espacio de nombres y esto sigue
  // funcionando en lugar de romperse al revés.
  //
  // **Vitest no reproduce esto**: su interop de CJS sí expone la nombrada, así
  // que un test escrito con su `import` daría verde. La comprobación vive en
  // `tests/updater-module-shape.test.ts` y sale a un `node` de verdad.
  const updaterModule = await import("electron-updater");
  const { autoUpdater } = updaterModule.default ?? updaterModule;
  autoUpdater.autoDownload = true;
  // Nunca reinicia por su cuenta: se instala al salir, y quien sale es la
  // persona. `decideUpdate` vuelve a decidirlo justo antes de cerrar.
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.setFeedURL({ provider: "generic", url: FEED_URL });

  let downloaded: { version: string } | null = null;

  /**
   * Lo que la pantalla ve. Se recalcula a partir de lo mismo que decide la
   * instalación, para que no haya dos verdades: «lista» y «esperando a que
   * termine el trabajo» son la misma descarga vista con la máquina ocupada o
   * libre, no dos estados que alguien tenga que mantener en sincronía.
   */
  const announceCurrent = () => {
    if (!downloaded) return;
    const decision = decideUpdate({ build, activity: ports.readActivity(), downloaded, available: null });
    ports.announce(
      decision.kind === "wait"
        ? { state: "esperando_trabajo", version: downloaded.version }
        : { state: "lista", version: downloaded.version },
    );
  };

  autoUpdater.on("update-available", (info: { version: string }) => {
    ports.announce({ state: "descargando", version: info.version });
  });
  autoUpdater.on("update-downloaded", (info: { version: string }) => {
    downloaded = { version: info.version };
    ports.log("actualización descargada", { version: info.version });
    // R6.1: aquí estaba el silencio. La descarga terminaba y sólo lo sabía el
    // registro; la persona se enteraba al reiniciar, si se enteraba.
    announceCurrent();
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
    // Con la descarga hecha, cada latido revisa si el trabajo vivo terminó: es
    // lo que convierte «esperando a que termines» en «lista» sin que nadie
    // tenga que recargar nada.
    announceCurrent();
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

  /**
   * R6.2 y R6.3 — instalar cuando la persona lo pide.
   *
   * Comparte decisión con la salida: si hay trabajo vivo **no instala**, y el
   * `busy` sube hasta la pantalla para que se diga en vez de que el botón
   * parezca roto.
   */
  const install = (): { ok: true } | { error: "busy" | "none" } => {
    if (!downloaded) return { error: "none" };
    const decision = decideUpdate({ build, activity: ports.readActivity(), downloaded, available: null });
    if (decision.kind !== "install-on-quit") {
      announceCurrent();
      return { error: "busy" };
    }
    ports.log("instalando a petición", { version: decision.version });
    autoUpdater.quitAndInstall(true, true);
    return { ok: true };
  };

  tick();
  const timer = setInterval(tick, CHECK_INTERVAL_MS);
  return { stop: () => clearInterval(timer), check: tick, install };
}
