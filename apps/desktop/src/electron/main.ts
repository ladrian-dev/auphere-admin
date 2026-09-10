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
import { BaseWindow, WebContentsView, app, ipcMain, session } from "electron";
import { hostname as osHostname } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { AppRuntime } from "../app-runtime.js";
import { GatewayApprovals } from "../approvals-client.js";
import { CredentialStore } from "../credential-store.js";
import { HttpTransport } from "../http-transport.js";
import { HEARTBEAT_INTERVAL_MS } from "../presence.js";
import { SessionGate } from "../session-gate.js";
import {
  HUMAN_PARTITION,
  assertPartitionsAreSeparate,
  barWebPreferences,
  consoleWebPreferences,
} from "../session-isolation.js";
import { decideWindowOpen, navigationAllowed } from "../window-open-policy.js";
import {
  consoleWhoami,
  nativeDirectoryPicker,
  nodeDirectoryFs,
  openExternal,
  safeStorageCipher,
  sessionCookieWatcher,
  userDataFile,
} from "./adapters.js";

const CONSOLE_URL = process.env.AUPHERE_CONSOLE_URL ?? "https://console.auphere.com";
const API_URL = process.env.AUPHERE_API_URL ?? "https://api.auphere.com";
const GATEWAY_URL = process.env.AUPHERE_GATEWAY_URL ?? "http://localhost:5476";
const BAR_HEIGHT = 44;
// ESM: no hay `__dirname`; la ruta de este fichero sale de `import.meta.url`.
const HERE = dirname(fileURLToPath(import.meta.url));

function layout(window: BaseWindow, consoleView: WebContentsView, barView: WebContentsView): void {
  const { width, height } = window.getContentBounds();
  consoleView.setBounds({ x: 0, y: 0, width, height: Math.max(0, height - BAR_HEIGHT) });
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
  const barView = new WebContentsView({
    webPreferences: barWebPreferences(join(HERE, "bar-preload.cjs")),
  });
  window.contentView.addChildView(consoleView);
  window.contentView.addChildView(barView);
  layout(window, consoleView, barView);
  window.on("resize", () => layout(window, consoleView, barView));

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
  const gate = new SessionGate({ whoami: consoleWhoami(CONSOLE_URL), store });
  gate.onDecision((decision) => void runtime.applyGate(decision));
  gate.watch(sessionCookieWatcher());

  await barView.webContents.loadFile(join(HERE, "..", "bar", "index.html"));
  await consoleView.webContents.loadURL(CONSOLE_URL);
  void runtime.applyGate(await gate.evaluate());

  const timer = setInterval(() => void runtime.tick(), HEARTBEAT_INTERVAL_MS);
  window.on("closed", () => {
    clearInterval(timer);
    runtime.stop();
  });
}

if (process.env.NODE_ENV !== "test") {
  void app.whenReady().then(bootstrap);
  app.on("window-all-closed", () => app.quit());
}
