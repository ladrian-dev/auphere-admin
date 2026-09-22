/**
 * La ventana — 001-R15 y spec 002 (Requisitos 1, 3, 11, 12, 14).
 *
 * **Pegamento fino a propósito.** Todo lo que decide vive en `AppRuntime`, la
 * puerta de sesión y la máquina de estados de la barra, que se prueban sin
 * display. Aquí solo hay lo que exige Electron.
 *
 * Tres decisiones que se ven en las primeras líneas:
 *
 * * **La consola se carga, no se reimplementa** (15.1), en su propia vista y
 *   **sin `preload`**: la página no puede hablarle a la cáscara (R3.5).
 * * **La barra es una segunda vista**, en su partición no persistente, con el
 *   único `preload` de la aplicación (12.1). El canal entre la consola y la barra
 *   es la persona.
 * * **No hay credencial por variable de entorno.** La máquina la canjea con un
 *   código, la guarda cifrada con el llavero, y solo late con una persona dentro.
 */
import { BaseWindow, Menu, Tray, WebContentsView, app, dialog, globalShortcut, ipcMain, nativeImage, nativeTheme, screen, session } from "electron";
import { randomUUID } from "node:crypto";
import { hostname as osHostname } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { AppRuntime } from "../app-runtime.js";
import { createPkce, listenForLogin } from "../loopback-login.js";
import { type HandoffView, handoffKindFor } from "../handoff-state.js";
import { type SignInView, signInFrom } from "../sign-in-state.js";
import { describeEnvironment } from "../startup-banner.js";
import { GatewayApprovals } from "../approvals-client.js";
import { CredentialStore } from "../credential-store.js";
import { HttpTransport } from "../http-transport.js";
import { InboxWatcher } from "../inbox-watcher.js";
import { PlatformClient } from "../platform-client.js";
import { HEARTBEAT_INTERVAL_MS } from "../presence.js";
import { SessionGate } from "../session-gate.js";
import {
  HUMAN_PARTITION,
  appWebPreferences,
  assertPartitionsAreSeparate,
  consoleWebPreferences,
} from "../session-isolation.js";
import type { InboxItem } from "../inbox-watcher.js";
import { StreamHub } from "../stream-hub.js";
import { trayBadge, trayTooltip, type Waiting } from "../tray-badge.js";
import { countWaiting } from "../waiting.js";
import { toWorkstationView } from "../workstation-state.js";
import { MIN_WINDOW, readWindowState, rememberWindow } from "../window-state.js";
import { decideWindowOpen, navigationAllowed } from "../window-open-policy.js";
import {
  applyNotificationEffects,
  consoleWhoami,
  nativeDirectoryPicker,
  nodeDirectoryFs,
  notificationPrefsStore,
  openExternal,
  partitionFetch,
  safeStorageCipher,
  sessionCookieWatcher,
  appLocale,
  readShortcut,
  userDataFile,
} from "./adapters.js";
import { registerAppSurface, sessionForRenderer } from "./app-surface.js";
import { STRIP_HEIGHT } from "./shell-layout.js";
import { windowBackground } from "./window-colors.js";
import { type ShellPrefs, mergeShellPrefs, normaliseShellPrefs } from "../shell-prefs.js";
import { type Section, pathOf, sectionOfPath } from "../sections.js";
import { losesWhenDenied, nextAfterAttempt } from "../permissions.js";
import { startUpdater, type UpdateState, type UpdaterHandle } from "./updater.js";
import { menuCopy } from "../menu-copy.js";
import type { Activity } from "../update-policy.js";

const CONSOLE_URL = process.env.AUPHERE_CONSOLE_URL ?? "https://console.auphere.com";
const API_URL = process.env.AUPHERE_API_URL ?? "https://api.auphere.com";
const GATEWAY_URL = process.env.AUPHERE_GATEWAY_URL ?? "http://localhost:5476";
// ESM: no hay `__dirname`; la ruta de este fichero sale de `import.meta.url`.
const HERE = dirname(fileURLToPath(import.meta.url));

type Surface = "app" | "console";

/**
 * Spec 010 — la vista de la aplicación ocupa **toda** la ventana: es el
 * armazón. La consola ya no se coloca aquí, sino en el rectángulo del panel
 * que la propia pantalla mide (`placeConsole`).
 *
 * La barra del puesto sigue abajo hasta que T139 la retire; mientras tanto, el
 * armazón le deja su franja.
 */
/**
 * ¿Se está saliendo de verdad?
 *
 * Distingue cerrar la ventana (que la oculta) de salir (que sí termina). Lo
 * pone la orden de salir del menú y del icono de la barra del sistema.
 */
let quitting = false;

/**
 * Lo que hay en marcha ahora mismo: sesiones de agente abiertas y decisiones
 * sin tomar. Lo rellena el arranque, y lo usan el actualizador y el aviso de
 * salida — las dos cosas que no deben pasar por encima de un trabajo vivo.
 */
let readActivityNow: (() => Activity) | null = null;

/**
 * Salir, avisando si hay algo a medias (R3.5).
 *
 * Cerrar la ventana la oculta, así que salir es un gesto deliberado; aun así,
 * salir con una decisión sin tomar o una sesión de agente en vuelo es la clase
 * de cosa que se hace sin querer al pulsar ⌘Q por costumbre.
 */
function quitWithWarning(copy: { title: string; detail: string; quit: string; cancel: string }): void {
  const activity = readActivityNow?.();
  const vivo = (activity?.liveSessions ?? 0) + (activity?.pendingApprovals ?? 0);
  if (vivo > 0) {
    const choice = dialog.showMessageBoxSync({
      type: "question",
      buttons: [copy.cancel, copy.quit],
      defaultId: 0,
      cancelId: 0,
      message: copy.title,
      detail: copy.detail,
    });
    if (choice === 0) return;
  }
  quitting = true;
  app.quit();
}

/**
 * El canal de actualización, cuando esté armado.
 *
 * Vive aquí, a nivel de módulo, porque lo arma el arranque y lo usa el menú, y
 * son dos funciones distintas. `null` mientras no haya canal: entonces «Buscar
 * actualizaciones» no hace nada, que es mejor que fingir que comprueba.
 */
let updater: UpdaterHandle | null = null;
/** Lo último que dijo el updater. Lo lee el menú para poder nombrar la versión. */
let updateState: UpdateState = { state: "idle" };

/**
 * El armazón ocupa **toda la ventana** — spec 010, R1.1.
 *
 * Aquí había una barra de 44 px pegada abajo, con su propia vista, su propio
 * `preload` y su propia partición. Se absorbió en el armazón (D2-A): el estado
 * de la máquina vive al pie de la lista lateral, y emparejar y declarar
 * directorios son diálogos de la aplicación. La barra dejaba sus hojas fuera de
 * la vista por su propio `overflow: hidden`, que fue el P0-2 de la evaluación.
 */
function layout(window: BaseWindow, appView: WebContentsView): void {
  const { width, height } = window.getContentBounds();
  appView.setBounds({ x: 0, y: 0, width, height });
}

export async function bootstrap(): Promise<{ readActivity: () => Activity; announce: (state: UpdateState) => void }> {
  // Lo PRIMERO que se dice, antes de nada: contra qué se está hablando. La
  // aplicación apunta a producción salvo que alguien ponga las variables, así
  // que probar contra el entorno equivocado es el caso fácil — y su síntoma es
  // indistinguible de un fallo de código (spec 009, 2026-09-15).
  console.info("[auphere]", describeEnvironment(CONSOLE_URL, API_URL));

  // Antes de nada y antes de abrir el puente: si las particiones se han igualado
  // en algún refactor, esto no arranca en vez de filtrar en silencio.
  assertPartitionsAreSeparate();

  // La consola sabe que la carga la cáscara **solo** por esto (R12.7, D9).
  const human = session.fromPartition(HUMAN_PARTITION);
  human.setUserAgent(`${human.getUserAgent()} AuphereDesktop/${app.getVersion()}`);

  // Dónde se abre: lo guardado, corregido contra las pantallas de hoy (12.4).
  // La corrección la hace un módulo puro con test; aquí solo se le pregunta.
  const windowFile = userDataFile("window.json");
  const savedWindow = (() => {
    try {
      const raw = windowFile.read();
      return raw ? (JSON.parse(raw.toString("utf8")) as unknown) : null;
    } catch {
      return null;
    }
  })();
  const placement = readWindowState(
    savedWindow,
    screen.getAllDisplays().map((d) => d.workArea),
  );
  const window = new BaseWindow({
    ...(placement.x !== undefined ? { x: placement.x, y: placement.y } : {}),
    width: placement.width,
    height: placement.height,
    minWidth: MIN_WINDOW.width,
    minHeight: MIN_WINDOW.height,
    title: "Auphere",
    /*
     * Spec 010 R1.1 — la barra de título la pinta la aplicación.
     *
     * Los controles del sistema siguen siendo los del sistema (`hidden` los
     * conserva en macOS y no los reimplementa), pero el marco es nuestro: la
     * franja superior y la lista lateral son una sola pieza, como en cualquier
     * aplicación de escritorio de las que sirven de referencia.
     *
     * El spike de la Fase 0 comprobó que arrastrar por esa franja mueve la
     * ventana **con la consola pintada encima del panel**, que era la duda.
     */
    titleBarStyle: "hidden",
    // Centrado en la franja de 52 px: (52 - 16) / 2 ≈ 18.
    ...(process.platform === "darwin" ? { trafficLightPosition: { x: 18, y: 18 } } : {}),
    /*
     * R2.7 — sin destello. La ventana nace con el color del tema activo, así
     * que mientras la vista carga no se ve un rectángulo blanco.
     */
    backgroundColor: windowBackground(nativeTheme.shouldUseDarkColors),
    show: false,
  });
  if (placement.maximised) window.maximize();
  const remember = rememberWindow((state) => windowFile.write(Buffer.from(JSON.stringify(state))));
  const noteBounds = () => {
    const bounds = window.getBounds();
    remember({ ...bounds, maximised: window.isMaximized() });
  };
  window.on("resize", noteBounds);
  window.on("move", noteBounds);
  window.on("close", () => remember.flush());
  const consoleView = new WebContentsView({ webPreferences: consoleWebPreferences() });
  // Spec 003 — la pantalla de operar: la segunda superficie propia, con su
  // partición y su `preload`. La consola sigue cargándose para administrar y
  // para operar clientes; se enseña una u otra, nunca las dos.
  const appView = new WebContentsView({
    webPreferences: appWebPreferences(join(HERE, "app-preload.cjs")),
  });
  /*
   * **El orden es la profundidad, y aquí decide si la consola se ve.**
   *
   * `addChildView` apila: el último va encima. Hasta la spec 010 el armazón iba
   * arriba y daba igual, porque `showSurface` **ocultaba** la pantalla al
   * enseñar la consola — se veía una superficie o la otra.
   *
   * Ahora la pantalla es el armazón y no se oculta nunca: ocupa la ventana
   * entera y la consola se pinta **dentro de su panel**. Con el orden viejo eso
   * dejaba la consola debajo de un armazón opaco de pantalla completa: el panel
   * se veía negro, sin error y sin nada que pulsar, porque el armazón no pinta
   * ahí a propósito. Es lo que pasó en la 0.1.4.
   *
   * La consola va encima, acotada al panel por `placeConsole()`: la franja y la
   * lista lateral siguen visibles y se pueden pulsar.
   */
  window.contentView.addChildView(appView);
  window.contentView.addChildView(consoleView);
  layout(window, appView);
  window.on("resize", () => {
    layout(window, appView);
    placeConsole();
  });

  /*
   * Spec 010 — la consola deja de ser «la otra superficie».
   *
   * La vista de la aplicación ocupa la ventana entera y es dueña del armazón;
   * la de la consola se coloca **dentro del panel de contenido**, en el
   * rectángulo que la propia pantalla mide y reporta. Ya no se turnan: se ve
   * el armazón siempre, y la consola dentro de él cuando toca.
   *
   * El invariante que hace que esto funcione (Fase 0): la consola **nunca**
   * invade la franja superior, que es la única región de arrastre. Aquí se
   * vuelve a acotar aunque la pantalla ya lo respete, porque el arrastre de la
   * ventana no puede depender de que un renderer mida bien.
   */
  let surface: Surface = "app";
  let onSurfaceChanged: (next: Surface) => void = () => {};
  /*
   * El rectángulo que medía la pantalla ya no hace falta: la consola ocupa
   * **todo** lo que hay bajo la franja desde la enmienda del 2026-09-18. El
   * canal `app:shell.contentBounds` se conserva —lo llama el armazón— y su
   * valor deja de usarse para colocar nada.
   */

  /**
   * Dónde va la consola — spec 010 R1.3, enmendado el 2026-09-18.
   *
   * **Todo lo que hay bajo la franja**, no un panel medido. Antes se metía en
   * el hueco que dejaba la lista lateral y se le pedía a la consola que se
   * quitara su propio armazón para caber (modo embebido). El resultado, visto
   * funcionando: dos barras laterales, dos buscadores, dos campanas y dos
   * identidades en la misma ventana.
   *
   * La franja se queda encima siempre: la ventana no tiene barra de título
   * nativa, así que es donde viven los semáforos, el arrastre y la vuelta.
   */
  const placeConsole = () => {
    const { width, height } = window.getContentBounds();
    consoleView.setBounds({
      x: 0,
      y: STRIP_HEIGHT,
      width,
      height: Math.max(0, height - STRIP_HEIGHT),
    });
  };

  const showSurface = (next: Surface) => {
    surface = next;
    // La pantalla no se oculta nunca: es el armazón. Lo que aparece y
    // desaparece dentro de su panel es la consola.
    appView.setVisible(true);
    consoleView.setVisible(next === "console");
    if (next === "console") placeConsole();
    onSurfaceChanged(next);
  };

  /** Coloca el panel donde la pantalla dice que cabe (R1.3). */
  const setPanel = (_rect: { x: number; y: number; width: number; height: number }) => {
    if (surface === "console") placeConsole();
  };

  /**
   * Spec 010 R4.1 — una sección que no carga es **un estado de la aplicación**.
   *
   * Lo que se veía cuando la consola no respondía era la página de error de
   * Chromium dentro del panel: en inglés, con pinta de navegador roto y sin
   * nada que pulsar. Ahora la vista se aparta, la pantalla lo dice en su lengua
   * y ofrece reintentar. Se recuerda **qué** sección falló para poder nombrarla.
   */
  let consoleFailed: Section | null = null;

  const showConsole = (path: string) => {
    const target = new URL(path, CONSOLE_URL).toString();
    // Tras un fallo la vista se queda con la URL de destino puesta, así que
    // comparar direcciones diría «ya estás ahí» y no reintentaría nada.
    if (consoleFailed !== null || consoleView.webContents.getURL() !== target) {
      void consoleView.webContents.loadURL(target).catch(() => {
        // `did-fail-load` ya lo cuenta; esto solo evita un rechazo suelto.
      });
    }
    showSurface("console");
  };

  /**
   * Spec 010 R1.3 — la pantalla pide **secciones**, no rutas.
   *
   * Si la pinta la consola, se muestra en su ruta; si la pinta la pantalla, la
   * consola se aparta y el panel vuelve a ser suyo. La persona no elige
   * superficie: elige sección.
   */
  /**
   * Ir a una sección — R1.3, enmendado.
   *
   * Las secciones de la aplicación se pintan en la pantalla. Cualquier otra
   * **es la consola**, y la consola entra entera: la sección sólo dice por qué
   * ruta abrirla, que es lo que hace que un tope lleve a `/billing` y no a «la
   * consola, búscalo tú».
   */
  const showSection = (section: Section) => {
    const path = pathOf(section);
    if (path === null) {
      showSurface("app");
      return;
    }
    consoleSection = section;
    showConsole(path);
  };

  /** La última sección que se pidió a la consola, para poder nombrarla. */
  let consoleSection: Section | null = null;

  const announceConsoleFailure = (section: Section | null, code = 0) => {
    consoleFailed = section;
    // Con la sección caída el panel vuelve a ser de la pantalla: dejar la vista
    // delante sería enseñar la página de error del navegador.
    if (section !== null) showSurface("app");
    pushApp("app:console.failed", section === null ? null : { section, code });
  };

  /**
   * Las comodidades de ventana. La lista de claves persistibles es cerrada
   * (`shell-state.ts`), así que esto no puede crecer sin pasar por ahí.
   */
  const prefsFile = userDataFile("shell.json");
  const readShellPrefs = (): ShellPrefs => {
    try {
      const raw = prefsFile.read();
      return normaliseShellPrefs(raw ? JSON.parse(raw.toString("utf8")) : {});
    } catch {
      // Un fichero a medias o de otra versión no impide abrir la aplicación.
      return normaliseShellPrefs({});
    }
  };
  const shellPrefs = {
    read: readShellPrefs,
    write: (next: Partial<ShellPrefs>): ShellPrefs => {
      const merged = mergeShellPrefs(readShellPrefs(), next);
      prefsFile.write(Buffer.from(JSON.stringify(merged)));
      /*
       * R2.3 — **una sola fuente de tema**. `nativeTheme.themeSource` gobierna
       * a la vez los marcos nativos y el `prefers-color-scheme` de las tres
       * superficies, incluida la consola embebida, que hasta ahora tenía su
       * propio selector y podía quedarse en claro dentro de una ventana oscura.
       */
      nativeTheme.themeSource = merged.theme;
      return merged;
    },
  };
  // El tema guardado se aplica **antes** de que nada pinte.
  nativeTheme.themeSource = readShellPrefs().theme;
  /*
   * Spec 010 R1.7 — el menú es el índice de lo que la aplicación sabe hacer.
   *
   * Desaparece «Ver → Equipo / Consola» con ⌘1 y ⌘2: esa distinción ya no
   * existe para la persona, que elige secciones. A cambio, **todo lo que hace
   * el armazón tiene su orden aquí**, que es como se descubre un atajo y como
   * se llega a las cosas sin ratón.
   *
   * El menú se reconstruye cuando cambia el idioma de la cuenta: un menú en
   * español dentro de una aplicación en inglés es de las cosas que más delatan
   * que nadie miró (R12.2).
   */
  /**
   * El zoom del contenido — R11, WCAG 1.4.4.
   *
   * `0` vuelve al tamaño real; los demás son pasos relativos. Se aplica a las
   * dos vistas a la vez y se acota: por encima de 3 el armazón deja de caber, y
   * por debajo de -2 el texto es ilegible, así que el control dejaría de
   * ayudar a quien lo usa.
   */
  const applyZoom = (step: number) => {
    const current = step === 0 ? 0 : Math.min(3, Math.max(-2, appView.webContents.getZoomLevel() + step));
    appView.webContents.setZoomLevel(current);
    consoleView.webContents.setZoomLevel(current);
  };

  const buildMenu = () => {
    const m = menuCopy(appLocale());
    /*
     * R6.5 — la versión instalada se ve desde el menú. El panel «Acerca de» es
     * donde macOS la busca, y decirla ahí es una línea en vez de una entrada de
     * menú apagada que no hace nada.
     */
    app.setAboutPanelOptions({ applicationName: "Auphere", applicationVersion: app.getVersion() });
    Menu.setApplicationMenu(
      Menu.buildFromTemplate([
        ...(process.platform === "darwin"
          ? [
              {
                role: "appMenu" as const,
                submenu: [
                  { role: "about" as const, label: m.about },
                  { type: "separator" as const },
                  { label: m.settings, accelerator: "CommandOrControl+,", click: () => showSection("cuenta") },
                  /*
                   * R6.2 y R6.5 — comprobar y, si ya está lista, instalar.
                   *
                   * La misma entrada cambia de significado con el estado en vez
                   * de haber dos, una de ellas siempre apagada: «instalar» sin
                   * nada descargado no lleva a ninguna parte (§V). Y lleva el
                   * número, porque «hay una nueva» sin versión no deja
                   * comprobar nada ni contárselo a soporte.
                   */
                  updateState.state === "lista"
                    ? { label: m.installUpdate.replace("{version}", updateState.version), click: () => updater?.install() }
                    : { label: m.checkUpdates, click: () => updater?.check() },
                  { type: "separator" as const },
                  { role: "hide" as const },
                  { role: "hideOthers" as const },
                  { role: "unhide" as const },
                  { type: "separator" as const },
                  { label: m.quit, accelerator: "CommandOrControl+Q", click: () => quitWithWarning(m) },
                ],
              },
            ]
          : []),
        {
          label: m.file,
          submenu: [{ label: m.newTeammate, accelerator: "CommandOrControl+N", click: () => showSection("hoy") }],
        },
        { role: "editMenu" as const, label: m.edit },
        {
          label: m.view,
          submenu: [
            { label: m.today, click: () => showSection("hoy") },
            { label: m.pending, click: () => showSection("pendientes") },
            { type: "separator" as const },
            { label: m.toggleSidebar, accelerator: "CommandOrControl+B", click: () => pushApp("app:shell.toggleSidebar", {}) },
            { type: "separator" as const },
            /*
             * R11 y WCAG 1.4.4 — se amplía **el contenido**, las dos vistas.
             *
             * Los `role` de Electron amplían el `webContents` que tenga el
             * foco. Con el armazón y la consola en la misma ventana eso deja
             * la mitad pequeña, que es peor que no ampliar: la persona ve
             * media pantalla legible y media no.
             */
            { label: m.zoomReset, accelerator: "CommandOrControl+0", click: () => applyZoom(0) },
            { label: m.zoomIn, accelerator: "CommandOrControl+Plus", click: () => applyZoom(+0.5) },
            { label: m.zoomOut, accelerator: "CommandOrControl+-", click: () => applyZoom(-0.5) },
            { type: "separator" as const },
            { role: "togglefullscreen" as const, label: m.fullscreen },
            { role: "reload" as const, label: m.reload },
          ],
        },
        { role: "windowMenu" as const, label: m.window },
        {
          role: "help" as const,
          label: m.help,
          submenu: [{ label: m.releaseNotes, click: () => showSection("hoy") }],
        },
      ]),
    );
  };
  buildMenu();

  /*
   * Spec 010 R1.4 — quién sabe dónde está la consola.
   *
   * La consola **no tiene `preload`** y no puede contar nada (002 R12.1). El
   * que observa es el proceso principal: cada vez que esa vista navega —también
   * cuando la navegación ocurre dentro de la consola, siguiendo uno de sus
   * enlaces—, traduce la ruta a una sección de la lista canónica y se la empuja
   * a la pantalla para que la marque. Una ruta que no conoce no marca nada:
   * antes que marcar algo falso, no marcar.
   */
  const pushConsoleLocation = (url: string) => {
    try {
      const { pathname } = new URL(url);
      const section = sectionOfPath(pathname);
      if (section) pushApp("app:console.location", { section, path: pathname });
    } catch {
      // Una URL que no se puede leer no dice dónde estamos: no se inventa.
    }
  };
  consoleView.webContents.on("did-navigate", (_event, url) => pushConsoleLocation(url));
  consoleView.webContents.on("did-navigate-in-page", (_event, url) => pushConsoleLocation(url));
  consoleView.webContents.on("did-fail-load", (_event, code, _desc, _url, isMainFrame) => {
    // Sólo el marco principal, y nunca `ERR_ABORTED` (-3): eso es una carga que
    // otra navegación reemplazó, que es lo normal al cambiar de sección.
    if (!isMainFrame || code === -3) return;
    announceConsoleFailure(consoleSection ?? "inicio", code);
  });
  consoleView.webContents.on("did-finish-load", () => {
    if (consoleFailed === null) return;
    announceConsoleFailure(null);
    if (consoleSection !== null) showSurface("console");
  });

  /**
   * Spec 010 R5.3 — **salir al navegador deja de ser un silencio.**
   *
   * Había tres sitios llamando a `openExternal` sin decir nada: «Elegir plan»,
   * «Comprar saldo» y entrar con Google. La ventana se quedaba exactamente
   * igual mientras el navegador se abría detrás, y quien volvía no tenía forma
   * de saber si había pulsado bien.
   */
  let handoff: HandoffView = { state: "idle", kind: null, since: new Date().toISOString() };
  const leaveToBrowser = (url: string) => {
    void openExternal(url);
    /*
     * R9.4 — la ventana **se queda en espera**, y sabe de qué. Reconocer que la
     * salida es un pago es lo que deja releer plan y consumo al volver sin
     * reiniciar nada (R9.5); una salida cualquiera no tiene vuelta que preparar.
     */
    handoff = { state: "esperando", kind: handoffKindFor(url), since: new Date().toISOString(), url };
    pushApp("app:handoff", handoff);
  };


  // La pantalla de operar no navega: es una página local. Un enlace se abre en
  // la consola (`app:openConsole`) o en el navegador del sistema, nunca dentro
  // de la vista, que es lo que la mantiene siendo una pantalla y no un navegador.
  appView.webContents.setWindowOpenHandler(({ url }) => {
    const decision = decideWindowOpen(url, new URL(CONSOLE_URL).origin);
    if (decision.action === "open_external") leaveToBrowser(decision.url);
    return { action: "deny" };
  });
  appView.webContents.on("will-navigate", (event) => event.preventDefault());

  // Ninguna ventana de la aplicación sin barra de direcciones (R12.7, 14.1).
  const consoleOrigin = new URL(CONSOLE_URL).origin;
  consoleView.webContents.setWindowOpenHandler(({ url }) => {
    const decision = decideWindowOpen(url, consoleOrigin);
    if (decision.action === "open_external") leaveToBrowser(decision.url);
    return { action: "deny" };
  });
  consoleView.webContents.on("will-navigate", (event, url) => {
    if (!navigationAllowed(url, consoleOrigin)) {
      event.preventDefault();
      const decision = decideWindowOpen(url, consoleOrigin);
      if (decision.action === "open_external") leaveToBrowser(decision.url);
    }
  });

  const store = new CredentialStore(safeStorageCipher(), userDataFile());
  const transport = new HttpTransport({ baseUrl: API_URL, appVersion: app.getVersion() });
  const runtime = new AppRuntime({
    consoleUrl: CONSOLE_URL,
    transport,
    approvals: new GatewayApprovals({
      baseUrl: GATEWAY_URL,
      token: process.env.AUPHERE_GATEWAY_TOKEN ?? "",
    }),
    store,
    machine: { hostname: osHostname(), platform: process.platform === "win32" ? "windows" : "macos" },
    fs: nodeDirectoryFs,
  });

  /*
   * Spec 010 — **la barra se retira**. Lo que hacía vive ahora en el armazón:
   * el estado de la máquina al pie de la lista lateral (R3.6), emparejar,
   * declarar directorios y desemparejar como diálogos de la aplicación (R8.2 a
   * R8.5), y volver a la pantalla como una sección más. Sus seis canales
   * `bar:*` y su partición se van con ella; los reemplazan los `app:workstation.*`
   * de la lista cerrada, que sí pasan por la validación de entrada.
   */
  onSurfaceChanged = () => {};

  /**
   * El inicio de sesión de la aplicación — spec 009 (2ª enmienda), RFC 8252.
   *
   * Cinco pasos y ninguno guarda un token en la cáscara:
   *
   * 1. Un par PKCE. El `verifier` se queda **en esta función**.
   * 2. Un oyente efímero en `127.0.0.1` (spec 001, criterio 6.5).
   * 3. El navegador del sistema va a `/desktop-auth` con `redirect_uri`,
   *    `state` y `code_challenge`.
   * 4. Se espera el retorno. El `state` lo comprueba el oyente.
   * 5. Se canjea `code` + `verifier` **contra la consola, no contra la API**:
   *    la ruta de la API exige la credencial de servicio del BFF, que esta
   *    cáscara no tiene ni puede tener. Va con el `fetch` de la partición
   *    humana, así que la cookie que devuelve la consola la guarda esa
   *    partición sola — y es esa cookie, no un token en JSON, lo que hace que
   *    `SessionGate` vea que ya se está dentro.
   *
   * `finally` cierra el oyente pase lo que pase: un servidor que sobrevive al
   * flujo es justo el fallo que la enmienda del Requisito 6 podría introducir.
   */
  /**
   * Spec 010 R7.2 y R7.4 — la espera **se cuenta**.
   *
   * Hasta aquí este flujo no tenía quien lo llamara (`009-T029`) y, cuando lo
   * tuviera, habría esperado en silencio: si la persona cancela en el navegador,
   * el retorno vuelve a `/login` sin destino y el oyente se queda los cinco
   * minutos enteros. Ahora cada punto del recorrido sube a la ventana, y lo que
   * se abrió se guarda para poder reabrirlo o copiarlo.
   */
  let signIn: SignInView = { state: "idle", since: new Date().toISOString() };
  let signInListening: { cancel: () => void } | null = null;
  const setSignIn = (next: SignInView) => {
    signIn = next;
    pushApp("app:signIn", next);
  };

  runtime.useBrowserSignIn(async () => {
    const { verifier, challenge } = createPkce();
    const state = randomUUID();
    const listening = await listenForLogin(state);
    signInListening = listening;
    try {
      const authorize = new URL("/desktop-auth", CONSOLE_URL);
      authorize.searchParams.set("redirect_uri", listening.redirectUri);
      authorize.searchParams.set("state", state);
      authorize.searchParams.set("code_challenge", challenge);
      const url = authorize.toString();
      setSignIn({ state: "esperando", since: new Date().toISOString(), url });
      await openExternal(url);

      const returned = await listening.wait;
      if (returned.kind !== "code") {
        setSignIn(signInFrom(returned, new Date().toISOString()));
        return { ok: false };
      }

      const response = await session
        .fromPartition(HUMAN_PARTITION)
        .fetch(`${CONSOLE_URL}/api/desktop/redeem`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: returned.code, code_verifier: verifier }),
        });
      setSignIn(
        signInFrom(response.ok ? { kind: "code" } : { kind: "redeem_failed" }, new Date().toISOString()),
      );
      /*
       * R7.3 — volver del navegador **trae la ventana al frente**. Sin esto la
       * persona termina en el navegador, la aplicación entra sola por detrás y
       * no hay nada que se lo diga: la ventana sigue donde la dejó, quizá
       * oculta desde que la cerró (R3.5).
       */
      if (response.ok) {
        window.show();
        app.focus({ steal: true });
      }
      return { ok: response.ok };
    } finally {
      listening.cancel();
      signInListening = null;
    }
  });

  // Quién está dentro lo lee el proceso principal, no la página (D6).
  const whoami = consoleWhoami(CONSOLE_URL);
  const gate = new SessionGate({ whoami, store });
  const pushApp = (channel: string, payload: unknown) => {
    if (!appView.webContents.isDestroyed()) appView.webContents.send(channel, payload);
  };
  gate.onDecision((decision) => {
    void runtime.applyGate(decision);
    // Cada veredicto trae consigo cómo está la conexión: es lo que distingue
    // «te has desconectado» de «no he podido preguntar» (R3.1).
    pushApp("app:connectivity", gate.connectivity());
    // `null` = no se pudo preguntar (spec 010 R3.2): no hay veredicto nuevo
    // que empujar, y empujar uno falso es exactamente lo que se está quitando.
    const forRenderer = sessionForRenderer(decision);
    if (forRenderer) pushApp("app:session", forRenderer);
    /*
     * Spec 010 R3.4 — perder la sesión **no cambia de superficie**.
     *
     * Antes esto llamaba a `showConsole("/")`: la ventana saltaba al inicio de
     * sesión sin avisar, y lo que la persona estuviera escribiendo se perdía al
     * desmontarse el hilo. Ahora la pantalla lo dice en su sitio, conserva el
     * borrador y ofrece entrar; el salto lo decide la persona.
     *
     * Lo que sí se para es el vigilante: sin sesión no hay nada que vigilar.
     */
    if (decision.kind === "stop") {
      inbox.stop();
      inbox.reset();
    } else if (surface === "console" && consoleView.webContents.getURL().includes("/login")) showSurface("app");
  });
  /**
   * R9.5 — volver del navegador.
   *
   * Se dispara con el foco de la ventana, que es lo que de verdad significa
   * «he vuelto»: nadie pulsa un botón para decirlo. Sólo hace algo si había una
   * espera, y **relee lo que pudo cambiar, no la aplicación entera** — recargar
   * tiraría el hilo abierto y el borrador sin enviar.
   */
  const returnedFromBrowser = () => {
    if (handoff.state !== "esperando") return;
    handoff = { ...handoff, state: "vuelto", since: new Date().toISOString() };
    pushApp("app:handoff", handoff);
    if (handoff.kind === "sign_in") void gate.refresh();
  };
  window.on("focus", returnedFromBrowser);

  gate.watch(sessionCookieWatcher());
  // **Emparejar y desemparejar también mueven la puerta.** Son lo único que
  // cambia la credencial guardada sin tocar la cookie ni perder la sesión, así
  // que sin esto nada volvía a derivar el veredicto: la barra pasaba a
  // `conectada` y el banner de la pantalla seguía diciendo «sin emparejar»
  // hasta el siguiente cambio de cookie, que puede tardar horas.
  //
  // Se refresca en vez de empujar un `app:session` fabricado: la puerta lee la
  // credencial donde está, y una copia mentiría el día que tenga una condición
  // más que mirar.
  /**
   * Spec 010 R8.3 — el emparejamiento llega a **todas** las superficies.
   *
   * La pantalla se entera sola: `onBarState` empuja `app:workstation` en cada
   * cambio, y `gate.refresh()` vuelve a derivar el veredicto. La consola
   * embebida no: su página de Puesto de trabajo se quedaba con la lista de
   * antes y su diálogo seguía con la cuenta atrás de un código ya canjeado
   * —el anexo 04 lo anotó como dos fuentes de verdad—. Se recarga sola, que es
   * lo contrario de que la recargue la persona.
   */
  runtime.onIdentityChanged(() => {
    void gate.refresh();
    if (consoleView.webContents.getURL().includes("/workstation")) consoleView.webContents.reload();
  });

  // La pantalla de operar: el principal habla con el BFF con la sesión de la
  // persona, y le pasa datos ya redactados (R12.2).
  const platform = new PlatformClient({ consoleUrl: CONSOLE_URL, fetch: partitionFetch() });
  const streams = new StreamHub(
    (path, signal, onEvent) => platform.stream(path, signal, onEvent),
    {
      event: (payload) => pushApp("app:event", payload),
      end: (payload) => pushApp("app:stream.end", payload),
    },
  );
  // La bandeja, vigilada desde el principal: el stream acelera, `GET /inbox`
  // manda, y lo que llega nuevo pasa por la política de avisos (R5.3, R7).
  const notificationPrefs = notificationPrefsStore();
  /**
   * Lo que se sabe del permiso de avisos — spec 010, R7.8 y R7.10.
   *
   * macOS no deja consultarlo, así que sólo un intento real lo mueve. Antes de
   * eso, `desconocido`: decir «concedido» sin saberlo pondría la lista de
   * puesta en marcha a dar por hecho algo que quizá nunca ocurrió.
   */
  const rememberNotificationAttempt = (shown: boolean) => {
    const prefs = notificationPrefs.read();
    const permission = nextAfterAttempt(prefs.permission, { shown });
    if (permission !== prefs.permission) notificationPrefs.write({ ...prefs, permission });
  };
  const inbox = new InboxWatcher({
    fetchInbox: async () => {
      const res = await platform.request<InboxItem[]>("/api/teammates/inbox");
      if (!res.ok) throw new Error(res.detail);
      return res.data;
    },
    openStream: (onEvent, signal) =>
      platform.stream("/api/teammates/inbox/stream", signal, (event) =>
        onEvent(event.event, event.data),
      ),
    apply: (effects) =>
      applyNotificationEffects(
        effects,
        (actionId) => {
        /*
         * Spec 010 R5.6 — pulsar un aviso **trae la ventana al frente**.
         *
         * Antes esto sólo cambiaba de superficie y empujaba el foco de la
         * tarjeta. Con la ventana oculta —que desde R3.5 es lo normal al
         * cerrarla— no pasaba absolutamente nada visible: el aviso parecía
         * roto, y quien lo pulsa dos veces acaba desactivándolos.
         */
        window.show();
        // En macOS, con la aplicación en segundo plano, `show()` no la pone
        // delante de la que tiene el foco: eso es `app.focus`.
        app.focus({ steal: true });
        // El objeto que lo produjo vive en Pendientes; `app:inbox.focus`
        // marca cuál dentro de la lista.
        showSection("pendientes");
        pushApp("app:inbox.focus", { action_id: actionId });
        },
        // R7.8: lo único que macOS deja saber del permiso es si un aviso llegó
        // a mostrarse. Eso mueve el estado; nada más lo mueve.
        rememberNotificationAttempt,
      ),
    push: (channel, payload) => {
      // La bandeja del sistema cuenta lo mismo que Pendientes, y solo lo que
      // espera una decisión: lo informativo no sube el número (12.4).
      if (channel === "app:inbox" && Array.isArray(payload)) {
        setTrayWaiting(payload as Waiting[]);
      }
      pushApp(channel, payload);
    },
    prefs: () => notificationPrefs.read(),
    // R5.5: con la ventana delante lo de dentro ya se ve. Se pregunta al
    // avisar, no al arrancar: es lo único que distingue «estabas mirando» de
    // «te fuiste a otra aplicación».
    notifyContext: () => ({ windowFocused: window.isVisible() && window.isFocused(), lang: appLocale() }),
    wait: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  });
  registerAppSurface({
    ipcMain,
    platform,
    streams,
    whoami,
    push: pushApp,
    showConsole,
    showSection,
    setPanelBounds: setPanel,
    shellPrefs,
    workstation: {
      state: () => toWorkstationView(runtime.barState),
      unpair: async () => {
        await runtime.unpair();
        return { ok: true };
      },
      pickDirectory: async (clientRef) => {
        const result = await runtime.declareDirectory(
          clientRef,
          nativeDirectoryPicker(window, menuCopy(appLocale()).pickDirectory),
        );
        if (result.kind === "declared") return { path_shown: result.workdir };
        // R8.4: el motivo viaja. Era exactamente lo que la barra tiraba.
        return result.kind === "invalid"
          ? { error: "invalid", reason: result.failed }
          : { error: "cancelled" };
      },
    },
    onSessionLost: () => void gate.refresh(),
    inbox,
    notificationPrefs,
    /*
     * R7.8 — se pide **al usarlo**, no al arrancar. En macOS no hay una API que
     * pregunte: la autorización la dispara el primer aviso que se muestra, así
     * que pedirlo es mostrar uno y mirar si salió.
     */
    askNotificationPermission: async () => {
      await new Promise<void>((resolve) => {
        applyNotificationEffects(
          [{ kind: "notify", title: "Auphere", body: menuCopy(appLocale()).notificationsProbe, actionId: null }],
          () => {},
          (shown) => {
            rememberNotificationAttempt(shown);
            resolve();
          },
        );
        // Si el sistema no contesta ni con `show` ni con `failed`, no se deja
        // la llamada colgada: lo que no consta se queda como no consta.
        setTimeout(resolve, 2000);
      });
      return notificationPrefs.read();
    },
    // El updater se arma después de la primera ventana, así que aquí puede no
    // existir todavía. Sin él no hay nada descargado que instalar: `none`.
    installUpdate: () => updater?.install() ?? { error: "none" as const },
    signIn: {
      // Sin `await`: el recorrido dura lo que dure en el navegador, y dejar la
      // invocación colgada ahí sería la espera muda que R7.4 prohíbe.
      start: () => void runtime.signInWithBrowser(),
      cancel: () => {
        signInListening?.cancel();
        setSignIn({ state: "cancelada", since: new Date().toISOString() });
      },
      state: () => signIn,
    },
    checkUpdate: () => updater?.check(),
    // Destino fijo: la pantalla no nombra direcciones del sistema operativo.
    openNotificationSettings: () => void openExternal(losesWhenDenied("notifications").settings),
    setup: {
      workstationStatus: () => runtime.barState.status,
      // Sin ejecutor no hay nada que corra en esta máquina, y es una causa con
      // nombre propio desde R3.6: se lee de ahí, no de una copia.
      executorPresent: () => runtime.barState.cause !== "sin_ejecutor",
    },
    // Lo que solo sabe esta máquina: dónde trabaja cada cliente y qué nombraron
    // los comandos de cada tarea. No sube a la plataforma y no baja a nadie.
    machine: {
      presence: () => ({
        machine: runtime.barState.machine ?? null,
        presence: runtime.barState.status === "conectada" ? "presente" : "ausente",
      }),
      links: () => [...runtime.clientLinks],
      filesForTask: (taskId) => runtime.taskFiles.forTask(taskId),
    },
  });
  /*
   * Spec 010 R3.6/R3.7 — el puesto se ve en el armazón.
   *
   * Es lo que sustituye a la barra de 44 px: el mismo estado, con su reloj y su
   * causa, empujado a la pantalla para que lo pinte junto a la identidad. La
   * barra sigue existiendo hasta que T139 la retire, y las dos leen **el mismo
   * objeto**: no hay dos verdades sobre la misma máquina.
   */
  runtime.onBarState((state) => pushApp("app:workstation", toWorkstationView(state)));

  runtime.onBarState((state) =>
    pushApp("app:presence", {
      machine: state.machine ?? null,
      presence: state.status === "conectada" ? "presente" : "ausente",
      links: state.links,
    }),
  );

  // ── comportarse como una aplicación (12.4) ─────────────────────────────
  //
  // El icono de bandeja es lo único que se ve con la ventana cerrada. Dice
  // cuántas cosas esperan una decisión y **no de qué van**: se ve en pantallas
  // compartidas y sin sesión delante.
  const tray = new Tray(nativeImage.createFromPath(join(HERE, "..", "..", "assets", "trayTemplate.png")));
  const showApp = () => {
    if (!window.isVisible()) window.show();
    if (window.isMinimized()) window.restore();
    window.focus();
    showSurface("app");
  };
  // La última lista de espera, retenida. El tray ya la recibía y se perdía; el
  // updater la necesita para no instalar encima de una decisión sin tomar.
  let waitingNow: Waiting[] = [];
  const setTrayWaiting = (waiting: Waiting[]): void => {
    waitingNow = waiting;
    const badge = trayBadge(waiting);
    tray.setToolTip(trayTooltip(waiting, appLocale()));
    // En macOS el número va al lado del icono; en el resto, en el tooltip.
    if (process.platform === "darwin") tray.setTitle(badge ? ` ${badge}` : "");
  };
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Auphere", click: showApp },
      { type: "separator" },
      { label: menuCopy(appLocale()).quit, click: () => quitWithWarning(menuCopy(appLocale())) },
    ]),
  );
  tray.on("click", showApp);
  setTrayWaiting([]);

  // Un atajo global para traer la aplicación al frente. Configurable en
  // `shortcut.json` del directorio de datos y no en una pantalla: la spec no
  // tiene ajustes, y un fichero es una decisión reversible que no inventa una.
  const shortcut = readShortcut();
  if (shortcut && !globalShortcut.isRegistered(shortcut)) {
    // Si otra aplicación lo tiene cogido, no se insiste ni se avisa: es una
    // comodidad, y pelearse por un atajo del sistema no es cosa de esta app.
    globalShortcut.register(shortcut, showApp);
  }
  app.on("will-quit", () => globalShortcut.unregisterAll());

  await appView.webContents.loadFile(join(HERE, "..", "app", "index.html"));
  // R2.7 — la ventana aparece **ya pintada**: el armazón está montado y el
  // fondo es el del tema. Nada de un rectángulo blanco mientras carga.
  window.show();
  showSurface("app");

  /*
   * Spec 010 R3.1 — **la consola no bloquea el arranque**.
   *
   * Esto era `await consoleView.webContents.loadURL(...)`, y ahí estaba el
   * fallo: sin red la promesa se rechazaba, `bootstrap()` se abortaba entero y
   * con él se caían el veredicto de sesión, el vigilante de Pendientes y el
   * latido. La persona veía esqueletos para siempre y ni un solo mensaje.
   *
   * Ahora la carga va por su cuenta y su fallo es **un estado de la ventana**,
   * no el final de la puesta en marcha: se dice «sin conexión», se puede
   * reintentar, y todo lo local sigue funcionando.
   */
  const announceConnectivity = () => pushApp("app:connectivity", gate.connectivity());
  /*
   * R1.10 — se carga **la sección con la que se cerró**, no siempre la portada.
   *
   * Cargar `/` a ciegas tenía un efecto que no se veía venir: `did-navigate`
   * empuja `app:console.location`, y la pantalla se iba a «Inicio» pisando la
   * sección restaurada. Reabrir te dejaba en otro sitio del que cerraste, sin
   * que nadie lo hubiera pedido.
   */
  const restored = pathOf(shellPrefs.read().section as Section) ?? "/";
  if (restored !== "/") consoleSection = shellPrefs.read().section as Section;
  void consoleView.webContents
    .loadURL(new URL(restored, CONSOLE_URL).toString())
    .then(announceConnectivity)
    .catch((error: unknown) => {
      console.info("[auphere] la consola no cargó:", error instanceof Error ? error.message : error);
      announceConnectivity();
    });

  const first = await gate.evaluate();
  announceConnectivity();
  void runtime.applyGate(first);
  const firstForRenderer = sessionForRenderer(first);
  if (firstForRenderer) pushApp("app:session", firstForRenderer);
  // Sin sesión **confirmada** se enseña la consola para entrar. Con
  // `unconfirmed` no: no se ha podido preguntar, y mandar a alguien al inicio
  // de sesión sin red es la peor versión de un corte de wifi.
  if (first.kind === "stop") showConsole("/");
  else if (first.kind !== "unconfirmed") void inbox.start();

  // Evidencia de desarrollo (spec 003, quickstart §3): con
  // `AUPHERE_EVIDENCE_DIR` se guardan capturas y el texto de la pantalla a los
  // pocos segundos de arrancar. No hace nada sin la variable.
  const evidenceDir = process.env.AUPHERE_EVIDENCE_DIR;
  if (evidenceDir) {
    const logs: string[] = [];
    appView.webContents.on("console-message", (event) => logs.push(`${event.level}: ${event.message}`.slice(0, 300)));
    appView.webContents.on("did-fail-load", (_e, code, desc) => logs.push(`did-fail-load ${code} ${desc}`));
    appView.webContents.on("preload-error", (_e, path, error) => logs.push(`preload-error ${path} ${String(error)}`));
    const walks: Record<string, typeof captureEvidence> = { us4: captureUs4, us5: captureUs5 };
    const walk = walks[process.env.AUPHERE_EVIDENCE_WALK ?? ""] ?? captureEvidence;
    setTimeout(() => void walk(evidenceDir, appView, consoleView, surface, logs), 6000);
  }

  const timer = setInterval(() => void runtime.tick(), HEARTBEAT_INTERVAL_MS);
  /*
   * Spec 010 R3.5 — **cerrar la ventana oculta; salir es otra cosa.**
   *
   * Antes, cerrar la ventana cerraba la aplicación entera: con ella se iban el
   * icono de la barra del sistema, los avisos de las decisiones pendientes y el
   * puente. Y la propia pantalla prometía lo contrario —«lo que le pidas sigue
   * aunque cierres la aplicación»—, así que una de las dos cosas mentía.
   *
   * Con la ventana oculta la aplicación sigue viva y avisando, que es lo que
   * hace de esto una aplicación de escritorio y no una pestaña.
   */
  window.on("close", (event) => {
    if (quitting) return;
    event.preventDefault();
    window.hide();
  });

  window.on("closed", () => {
    clearInterval(timer);
    streams.closeAll();
    inbox.stop();
    runtime.stop();
  });

  // Lo que el updater necesita saber para NO reiniciar encima de nada: los
  // streams abiertos son sesiones de agente en vuelo, y la lista de espera son
  // decisiones que una persona todavía no ha tomado. `informativo` no cuenta:
  // no espera a nadie, igual que no marca la bandeja.
  const readActivity = () => ({
    liveSessions: streams.liveCount,
    pendingApprovals: countWaiting(waitingNow),
  });
  readActivityNow = readActivity;
  /*
   * R6.1 — el updater se arma fuera de `bootstrap()` (comprobar la firma
   * cuesta un proceso y no puede retrasar la primera ventana), así que se lleva
   * de aquí lo único que necesita para hablar con la pantalla.
   */
  return {
    readActivity,
    announce: (state: UpdateState) => {
      updateState = state;
      pushApp("app:update", state);
      // La orden del menú dice «Instalar la versión X» sólo cuando la hay, así
      // que el menú se reconstruye con el estado, igual que con el idioma.
      buildMenu();
    },
  };
}

async function captureEvidence(
  dir: string,
  appView: WebContentsView,
  consoleView: WebContentsView,
  surface: Surface,
  logs: string[] = [],
): Promise<void> {
  const { mkdirSync, writeFileSync } = await import("node:fs");
  mkdirSync(dir, { recursive: true });
  const bridgeType = await appView.webContents.executeJavaScript("typeof window.auphere").catch(() => "?");
  const roster = await appView.webContents.executeJavaScript("document.body.innerText").catch(() => "");
  /*
   * Abre el hilo del primer teammate (quickstart §4.1).
   *
   * Spec 010, T138 — **la navegación cambió**. Era «el último botón de la
   * lista», que con el roster viejo era un teammate; con el armazón, el último
   * es una sección de administrar. Ahora se busca el grupo de teammates por su
   * encabezado, que es lo que de verdad identifica la lista.
   */
  await appView.webContents
    .executeJavaScript(
      "(() => { const g = Array.from(document.querySelectorAll('nav h2'))" +
        ".find(h => /Teammates/i.test(h.textContent || ''));" +
        "const b = g?.parentElement?.querySelector('ul button'); b?.click(); return !!b; })()",
    )
    .catch(() => false);
  await new Promise((r) => setTimeout(r, 3500));
  const text = await appView.webContents.executeJavaScript("document.body.innerText").catch(() => "");
  // Y Pendientes, que es la otra mitad de la US2.
  await appView.webContents
    .executeJavaScript(
      "Array.from(document.querySelectorAll('nav button')).find(b => /Pendientes|Pending/.test(b.textContent||''))?.click(), true",
    )
    .catch(() => false);
  await new Promise((r) => setTimeout(r, 1200));
  const inboxText = await appView.webContents.executeJavaScript("document.body.innerText").catch(() => "");
  writeFileSync(join(dir, "inbox.png"), (await appView.webContents.capturePage()).toPNG());
  const states = await appView.webContents
    .executeJavaScript("Array.from(document.querySelectorAll('[data-thread-state]')).map(e => e.dataset.threadState)")
    .catch(() => []);
  writeFileSync(join(dir, "app.png"), (await appView.webContents.capturePage()).toPNG());
  writeFileSync(join(dir, "console.png"), (await consoleView.webContents.capturePage()).toPNG());
  writeFileSync(
    join(dir, "app.json"),
    JSON.stringify(
      { surface, consoleUrl: consoleView.webContents.getURL(), bridgeType, roster, text, inboxText, states, logs },
      null,
      2,
    ),
  );
}

if (process.env.NODE_ENV !== "test") {
  // **Una sola instancia** (12.4). Abrir la aplicación dos veces abriría dos
  // puentes con la misma credencial y dos vigilantes de la bandeja: el segundo
  // avisaría de lo mismo otra vez. La segunda invocación trae la primera al
  // frente, que es lo que la persona quería al hacer doble clic.
  if (!app.requestSingleInstanceLock()) {
    app.quit();
  } else {
    app.on("second-instance", () => {
      const [first] = BaseWindow.getAllWindows();
      if (!first) return;
      if (first.isMinimized()) first.restore();
      first.show();
      first.focus();
    });
    void app.whenReady().then(async () => {
      const bootstrapped = bootstrap();
      await bootstrapped;
      // El updater va DESPUÉS de arrancar: comprobar la propia firma cuesta un
      // proceso, y nada de esto debe retrasar la primera ventana.
      const { readActivity, announce } = await bootstrapped;
      // **Con `catch`, y a propósito.** Sin él, un fallo al armar el updater
      // quedaba como `UnhandledPromiseRejectionWarning` en un `stderr` que
      // nadie lee en una aplicación de escritorio — que es como v0.1.0 y
      // v0.1.1 se publicaron sin actualizarse y sin que se notara.
      //
      // Se traga la excepción a propósito: que el canal no arranque no puede
      // tumbar el puente ni la pantalla, que es para lo que la persona abrió
      // la aplicación. Pero se registra, que es donde alguien va a buscarlo.
      updater = await startUpdater({
        readActivity,
        log: (message, detail) => console.info("[updater]", message, detail ?? {}),
        /*
         * R6.1 — aquí estaba el silencio. El ciclo entero funcionaba y su
         * resultado sólo llegaba al registro: la persona se enteraba de que
         * había una versión nueva al reiniciar, si se enteraba.
         */
        announce,
      }).catch((error: unknown) => {
        console.error("[updater] no se pudo armar", error);
        return null;
      });
    });
    /*
     * R3.5 — en macOS, cerrar la última ventana **no** cierra la aplicación:
     * sigue en la barra del sistema, avisando de lo que espera decisión. En
     * Windows y Linux la convención es la contraria, y se respeta.
     */
    app.on("window-all-closed", () => {
      if (process.platform !== "darwin") app.quit();
    });

    // Volver desde el Dock: la ventana estaba oculta, no cerrada.
    app.on("activate", () => {
      const [first] = BaseWindow.getAllWindows();
      if (first) {
        first.show();
        first.focus();
      }
    });

    // Salir de verdad. Lo llama la orden del menú y la del icono de la barra.
    app.on("before-quit", () => {
      quitting = true;
    });
  }
}


/**
 * El recorrido de la US4 (`AUPHERE_EVIDENCE_WALK=us4`): crear un teammate desde
 * la aplicación, cambiarle el oficio, ver la nota en el hilo y archivarlo.
 *
 * Escribe de verdad contra la plataforma —es lo que se quiere comprobar— así
 * que **archiva lo que crea** al terminar. Archivar no borra (R2.6): la fila
 * queda, que es justo lo que hay que poder ver después.
 */
async function captureUs4(
  dir: string,
  appView: WebContentsView,
  consoleView: WebContentsView,
  surface: Surface,
  logs: string[] = [],
): Promise<void> {
  const { mkdirSync, writeFileSync } = await import("node:fs");
  mkdirSync(dir, { recursive: true });
  const js = (code: string) => appView.webContents.executeJavaScript(code).catch((e: unknown) => String(e));
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const shot = async (name: string) => writeFileSync(join(dir, name), (await appView.webContents.capturePage()).toPNG());
  const text = () => js("document.body.innerText") as Promise<string>;
  const click = (selector: string, match: string) =>
    js(
      `Array.from(document.querySelectorAll(${JSON.stringify(selector)}))` +
        `.find((e) => new RegExp(${JSON.stringify(match)}, "i")` +
        `.test(((e.getAttribute("aria-label") || "") + " " + (e.textContent || "")).trim()))?.click(), true`,
    );
  // React escucha el evento nativo, no la asignación directa a `.value`.
  const type = (selector: string, value: string) =>
    js(
      `(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false;` +
        ` const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;` +
        ` set.call(el, ${JSON.stringify(value)});` +
        ` el.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`,
    );

  const steps: Record<string, string> = {};
  steps.roster = await text();

  await click("button", "crear teammate");
  await wait(1500);
  await shot("new-teammate.png");
  steps.form = await text();

  await type("#teammate-name", "Prueba US4");
  await wait(300);
  await click("button[type=submit]", "crear teammate");
  await wait(2500);
  await shot("created.png");
  steps.created = await text();

  await click("button", "^ajustes$");
  await wait(1200);
  await type("#settings-job", "Finanzas");
  await wait(300);
  await shot("settings.png");
  await click("button[type=submit]", "guardar");
  await wait(2500);
  steps.saved = await text();
  await shot("changed.png");

  await click("button", "^ajustes$");
  await wait(1200);
  await click("button", "^archivar");
  await wait(600);
  steps.confirm = await text();
  await shot("archive-confirm.png");
  await click("button", "sí, archivar");
  await wait(2500);
  steps.archived = await text();
  await shot("archived.png");

  writeFileSync(
    join(dir, "app.json"),
    JSON.stringify({ surface, consoleUrl: consoleView.webContents.getURL(), steps, logs }, null, 2),
  );
}

/**
 * El recorrido de la US5 (`AUPHERE_EVIDENCE_WALK=us5`): abrir Cuenta y leer lo
 * que dice. **No escribe nada**: es una pantalla de lectura, y una evidencia
 * que tocara el consumo del mes para poder enseñarlo sería peor que ninguna.
 */
async function captureUs5(
  dir: string,
  appView: WebContentsView,
  consoleView: WebContentsView,
  surface: Surface,
  logs: string[] = [],
): Promise<void> {
  const { mkdirSync, writeFileSync } = await import("node:fs");
  mkdirSync(dir, { recursive: true });
  const js = (code: string) => appView.webContents.executeJavaScript(code).catch((e: unknown) => String(e));
  await js(
    'Array.from(document.querySelectorAll("nav button")).find((b) => /Cuenta|Account/.test(b.textContent || ""))?.click(), true',
  );
  await new Promise((r) => setTimeout(r, 2500));
  const text = (await js("document.body.innerText")) as string;
  /*
   * Spec 010, T138 — **este recorrido estaba roto**, y en silencio.
   *
   * Buscaba un `<meter>` nativo que Cuenta dejó de pintar: no se puede vestir
   * con los tokens sin pelearse con pseudo-elementos por motor, y se veía como
   * una barra blanca de otro sistema. Lo que quedó es la semántica —un `div`
   * con `role="meter"` y sus tres valores— y el color en tokens. El recorrido
   * seguía «funcionando»: devolvía `null` y nadie miraba.
   */
  const meter = await js(
    '(() => { const m = document.querySelector(\'[role="meter"]\'); return m ? { now: m.getAttribute("aria-valuenow"), max: m.getAttribute("aria-valuemax") } : null; })()',
  );
  // R9 — el plan vive aquí desde la historia 5: es lo que hace que los topes
  // lleven a alguna parte, y lo que antes no existía en esta pantalla.
  const plan = await js(
    '(() => { const s = Array.from(document.querySelectorAll("section")).find((e) => /Tu plan|Your plan/.test(e.getAttribute("aria-label") || "")); return s ? s.innerText : null; })()',
  );
  writeFileSync(join(dir, "account.png"), (await appView.webContents.capturePage()).toPNG());
  writeFileSync(
    join(dir, "app.json"),
    JSON.stringify(
      { surface, consoleUrl: consoleView.webContents.getURL(), text, meter, plan, logs },
      null,
      2,
    ),
  );
}