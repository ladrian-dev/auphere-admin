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
import { BaseWindow, Menu, WebContentsView, app, ipcMain, session } from "electron";
import { hostname as osHostname } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { AppRuntime } from "../app-runtime.js";
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
  barWebPreferences,
  consoleWebPreferences,
} from "../session-isolation.js";
import type { InboxItem } from "../inbox-watcher.js";
import { StreamHub } from "../stream-hub.js";
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
  userDataFile,
} from "./adapters.js";
import { registerAppSurface, sessionForRenderer } from "./app-surface.js";

const CONSOLE_URL = process.env.AUPHERE_CONSOLE_URL ?? "https://console.auphere.com";
const API_URL = process.env.AUPHERE_API_URL ?? "https://api.auphere.com";
const GATEWAY_URL = process.env.AUPHERE_GATEWAY_URL ?? "http://localhost:5476";
const BAR_HEIGHT = 44;
// ESM: no hay `__dirname`; la ruta de este fichero sale de `import.meta.url`.
const HERE = dirname(fileURLToPath(import.meta.url));

type Surface = "app" | "console";

function layout(window: BaseWindow, views: WebContentsView[], barView: WebContentsView): void {
  const { width, height } = window.getContentBounds();
  for (const view of views) view.setBounds({ x: 0, y: 0, width, height: Math.max(0, height - BAR_HEIGHT) });
  barView.setBounds({ x: 0, y: Math.max(0, height - BAR_HEIGHT), width, height: BAR_HEIGHT });
}

export async function bootstrap(): Promise<void> {
  // Antes de nada y antes de abrir el puente: si las particiones se han igualado
  // en algún refactor, esto no arranca en vez de filtrar en silencio.
  assertPartitionsAreSeparate();

  // La consola sabe que la carga la cáscara **solo** por esto (R12.7, D9).
  const human = session.fromPartition(HUMAN_PARTITION);
  human.setUserAgent(`${human.getUserAgent()} AuphereDesktop/${app.getVersion()}`);

  const window = new BaseWindow({ width: 1280, height: 820, title: "Auphere" });
  const consoleView = new WebContentsView({ webPreferences: consoleWebPreferences() });
  // Spec 003 — la pantalla de operar: la segunda superficie propia, con su
  // partición y su `preload`. La consola sigue cargándose para administrar y
  // para operar clientes; se enseña una u otra, nunca las dos.
  const appView = new WebContentsView({
    webPreferences: appWebPreferences(join(HERE, "app-preload.cjs")),
  });
  const barView = new WebContentsView({
    webPreferences: barWebPreferences(join(HERE, "bar-preload.cjs")),
  });
  window.contentView.addChildView(consoleView);
  window.contentView.addChildView(appView);
  window.contentView.addChildView(barView);
  layout(window, [consoleView, appView], barView);
  window.on("resize", () => layout(window, [consoleView, appView], barView));

  let surface: Surface = "app";
  const showSurface = (next: Surface) => {
    surface = next;
    appView.setVisible(next === "app");
    consoleView.setVisible(next === "console");
  };
  const showConsole = (path: string) => {
    const target = new URL(path, CONSOLE_URL).toString();
    if (consoleView.webContents.getURL() !== target) void consoleView.webContents.loadURL(target);
    showSurface("console");
  };
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      ...(process.platform === "darwin" ? [{ role: "appMenu" as const }] : []),
      { role: "editMenu" as const },
      {
        label: "Ver",
        submenu: [
          { label: "Equipo", accelerator: "CommandOrControl+1", click: () => showSurface("app") },
          { label: "Consola", accelerator: "CommandOrControl+2", click: () => showConsole("/") },
          { type: "separator" },
          { role: "reload" as const },
          { role: "togglefullscreen" as const },
        ],
      },
      { role: "windowMenu" as const },
    ]),
  );

  // La pantalla de operar no navega: es una página local. Un enlace se abre en
  // la consola (`app:openConsole`) o en el navegador del sistema, nunca dentro
  // de la vista, que es lo que la mantiene siendo una pantalla y no un navegador.
  appView.webContents.setWindowOpenHandler(({ url }) => {
    const decision = decideWindowOpen(url, new URL(CONSOLE_URL).origin);
    if (decision.action === "open_external") void openExternal(decision.url);
    return { action: "deny" };
  });
  appView.webContents.on("will-navigate", (event) => event.preventDefault());

  // Ninguna ventana de la aplicación sin barra de direcciones (R12.7, 14.1).
  const consoleOrigin = new URL(CONSOLE_URL).origin;
  consoleView.webContents.setWindowOpenHandler(({ url }) => {
    const decision = decideWindowOpen(url, consoleOrigin);
    if (decision.action === "open_external") void openExternal(decision.url);
    return { action: "deny" };
  });
  consoleView.webContents.on("will-navigate", (event, url) => {
    if (!navigationAllowed(url, consoleOrigin)) {
      event.preventDefault();
      const decision = decideWindowOpen(url, consoleOrigin);
      if (decision.action === "open_external") void openExternal(decision.url);
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

  // La barra: estado empujado, acciones por IPC. Exactamente las del contrato.
  const pushState = () => {
    if (!barView.webContents.isDestroyed()) barView.webContents.send("bar:state", runtime.barState);
  };
  runtime.onBarState(pushState);
  ipcMain.handle("bar:getState", () => runtime.barState);
  ipcMain.handle("bar:pair", (_event, code: unknown) => runtime.pair(String(code)));
  ipcMain.handle("bar:unpair", () => runtime.unpair());
  ipcMain.handle("bar:pickDirectory", (_event, clientRef: unknown) =>
    runtime.declareDirectory(String(clientRef), nativeDirectoryPicker(window, "Elige el directorio del cliente")),
  );
  ipcMain.handle("bar:openInBrowser", (_event, url: unknown) => {
    const decision = decideWindowOpen(String(url), consoleOrigin);
    return decision.action === "open_external" ? openExternal(decision.url) : undefined;
  });

  // Quién está dentro lo lee el proceso principal, no la página (D6).
  const whoami = consoleWhoami(CONSOLE_URL);
  const gate = new SessionGate({ whoami, store });
  const pushApp = (channel: string, payload: unknown) => {
    if (!appView.webContents.isDestroyed()) appView.webContents.send(channel, payload);
  };
  gate.onDecision((decision) => {
    void runtime.applyGate(decision);
    pushApp("app:session", sessionForRenderer(decision));
    // Sin sesión, la pantalla no puede hacer nada útil: se enseña la consola
    // para que la persona entre; al volver la sesión, vuelve la pantalla.
    if (decision.kind === "stop") {
      inbox.stop();
      inbox.reset();
      showConsole("/");
    } else if (surface === "console" && consoleView.webContents.getURL().includes("/login")) showSurface("app");
  });
  gate.watch(sessionCookieWatcher());

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
      applyNotificationEffects(effects, (actionId) => {
        showSurface("app");
        pushApp("app:inbox.focus", { action_id: actionId });
      }),
    push: (channel, payload) => pushApp(channel, payload),
    prefs: () => notificationPrefs.read(),
    wait: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  });
  registerAppSurface({
    ipcMain,
    platform,
    streams,
    whoami,
    push: pushApp,
    showConsole,
    onSessionLost: () => void gate.refresh(),
    inbox,
    notificationPrefs,
  });
  runtime.onBarState((state) =>
    pushApp("app:presence", {
      machine: state.machine ?? null,
      presence: state.status === "conectada" ? "presente" : "ausente",
      links: state.links,
    }),
  );

  await barView.webContents.loadFile(join(HERE, "..", "bar", "index.html"));
  await appView.webContents.loadFile(join(HERE, "..", "app", "index.html"));
  await consoleView.webContents.loadURL(CONSOLE_URL);
  showSurface("app");
  const first = await gate.evaluate();
  void runtime.applyGate(first);
  pushApp("app:session", sessionForRenderer(first));
  if (first.kind === "stop") showConsole("/");
  else void inbox.start();

  // Evidencia de desarrollo (spec 003, quickstart §3): con
  // `AUPHERE_EVIDENCE_DIR` se guardan capturas y el texto de la pantalla a los
  // pocos segundos de arrancar. No hace nada sin la variable.
  const evidenceDir = process.env.AUPHERE_EVIDENCE_DIR;
  if (evidenceDir) {
    const logs: string[] = [];
    appView.webContents.on("console-message", (event) => logs.push(`${event.level}: ${event.message}`.slice(0, 300)));
    appView.webContents.on("did-fail-load", (_e, code, desc) => logs.push(`did-fail-load ${code} ${desc}`));
    appView.webContents.on("preload-error", (_e, path, error) => logs.push(`preload-error ${path} ${String(error)}`));
    setTimeout(() => void captureEvidence(evidenceDir, appView, consoleView, surface, logs), 6000);
  }

  const timer = setInterval(() => void runtime.tick(), HEARTBEAT_INTERVAL_MS);
  window.on("closed", () => {
    clearInterval(timer);
    streams.closeAll();
    inbox.stop();
    runtime.stop();
  });
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
  // Abre el hilo del primer teammate: es el recorrido del quickstart §4.1.
  await appView.webContents
    .executeJavaScript("Array.from(document.querySelectorAll('nav ul button')).at(-1)?.click(), true")
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
  void app.whenReady().then(bootstrap);
  app.on("window-all-closed", () => app.quit());
}
