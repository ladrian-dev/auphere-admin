/**
 * La ventana — Requisito 15.1, 15.2 y 15.3.
 *
 * **Pegamento fino a propósito.** Todo lo que decide vive en `AppRuntime`, que se
 * prueba sin display. Aquí solo hay lo que exige Electron, y por eso este fichero
 * no tiene tests unitarios: probar `BrowserWindow` de verdad necesita un runner
 * gráfico, y probarlo con dobles solo demostraría que los dobles hacen lo que les
 * dijimos.
 *
 * Tres decisiones que se ven en las primeras líneas:
 *
 * * **La consola se carga, no se reimplementa** (15.1). Dos implementaciones de la
 *   misma pantalla divergen, y la que se queda atrás miente.
 * * **La partición de la persona es la única persistente** (15.3). La del agente
 *   no toca disco: no hay dónde quedarse una sesión.
 * * **`nodeIntegration` apagado y `contextIsolation` encendido**: la consola es
 *   una web, y una web con acceso a Node en la máquina del partner es la
 *   superficie que esta aplicación existe para *no* abrir.
 */
import { BrowserWindow, app } from "electron";

import { AppRuntime } from "../app-runtime.js";
import { GatewayApprovals } from "../approvals-client.js";
import { HttpTransport } from "../http-transport.js";
import { HEARTBEAT_INTERVAL_MS } from "../presence.js";
import { HUMAN_PARTITION, assertPartitionsAreSeparate } from "../session-isolation.js";

const CONSOLE_URL = process.env.AUPHERE_CONSOLE_URL ?? "https://console.auphere.com";
const API_URL = process.env.AUPHERE_API_URL ?? "https://api.auphere.com";
const GATEWAY_URL = process.env.AUPHERE_GATEWAY_URL ?? "http://localhost:5476";

/**
 * La credencial que el alta entregó una sola vez. Sin ella la app no puede
 * hablar con la plataforma — y **no arranca el puente** en vez de latir contra
 * un 401 en bucle, que llenaría los logs sin decir nada útil.
 */
const DEVICE_TOKEN = process.env.AUPHERE_DEVICE_TOKEN ?? "";

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    title: "Auphere",
    webPreferences: {
      partition: HUMAN_PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  void window.loadURL(CONSOLE_URL);
  return window;
}

export async function bootstrap(): Promise<void> {
  // Antes de nada y antes de abrir el puente: si las particiones se han igualado
  // en algún refactor, esto no arranca en vez de filtrar en silencio.
  assertPartitionsAreSeparate();

  const window = createWindow();

  const runtime = new AppRuntime({
    consoleUrl: CONSOLE_URL,
    workdir: process.env.AUPHERE_WORKDIR ?? app.getPath("home"),
    transport: new HttpTransport({ baseUrl: API_URL, token: DEVICE_TOKEN }),
    approvals: new GatewayApprovals({
      baseUrl: GATEWAY_URL,
      token: process.env.AUPHERE_GATEWAY_TOKEN ?? "",
    }),
  });

  if (!DEVICE_TOKEN) {
    // La ventana se abre igual: la consola es útil sin puente. Lo que no se hace
    // es fingir que hay dispositivo — sin credencial no hay herramientas locales.
    window.on("closed", () => undefined);
    return;
  }

  await runtime.start();
  const timer = setInterval(() => void runtime.tick(), HEARTBEAT_INTERVAL_MS);
  window.on("closed", () => clearInterval(timer));
}

if (process.env.NODE_ENV !== "test") {
  void app.whenReady().then(bootstrap);
  app.on("window-all-closed", () => app.quit());
}
