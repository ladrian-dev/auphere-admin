/**
 * T001 — spike con display: BaseWindow + dos WebContentsView.
 *
 * (a) la consola carga en su vista, sin `preload`;
 * (b) desde la vista de la consola `window.auphere` es `undefined`, y desde la
 *     barra es un objeto (el preload solo existe en la barra);
 * (c) tres particiones distintas, la de la barra y la del agente sin `persist:`.
 *
 * Escribe `result.json` y `screenshot.png` en este directorio y se cierra.
 */
import { app, BaseWindow, WebContentsView, session } from "electron";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const CONSOLE_URL = process.env.AUPHERE_CONSOLE_URL ?? "https://console.auphere.com/login";
const HUMAN = "persist:auphere-console";
const BAR = "auphere-bar";
const AGENT = "auphere-agent";

const BAR_HTML = `data:text/html;charset=utf-8,${encodeURIComponent(
  `<!doctype html><html><body style="margin:0;height:44px;display:flex;align-items:center;padding:0 12px;font:13px ui-monospace,monospace;background:#0D0F01;color:#F1F7F6">barra del puesto · spike T001</body></html>`,
)}`;

app.whenReady().then(async () => {
  const result = { partitions: { human: HUMAN, bar: BAR, agent: AGENT } };
  try {
    const win = new BaseWindow({ width: 1200, height: 800, title: "Auphere — spike T001" });
    const consoleView = new WebContentsView({
      webPreferences: { partition: HUMAN, contextIsolation: true, nodeIntegration: false, sandbox: true },
    });
    const barView = new WebContentsView({
      webPreferences: {
        partition: BAR,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        preload: join(here, "bar-preload.cjs"),
      },
    });
    win.contentView.addChildView(consoleView);
    win.contentView.addChildView(barView);
    const layout = () => {
      const { width, height } = win.getContentBounds();
      consoleView.setBounds({ x: 0, y: 0, width, height: height - 44 });
      barView.setBounds({ x: 0, y: height - 44, width, height: 44 });
    };
    layout();
    win.on("resize", layout);

    await barView.webContents.loadURL(BAR_HTML);
    const t0 = Date.now();
    await consoleView.webContents.loadURL(CONSOLE_URL);
    result.consoleLoadedMs = Date.now() - t0;
    result.consoleTitle = consoleView.webContents.getTitle();
    result.consoleUrl = consoleView.webContents.getURL();
    result.consoleHasLoginForm = await consoleView.webContents.executeJavaScript(
      `!!document.querySelector('input[type="password"], input[name="password"], form')`,
    );
    result.auphereInConsoleView = await consoleView.webContents.executeJavaScript("typeof window.auphere");
    result.auphereInBarView = await barView.webContents.executeJavaScript("typeof window.auphere");
    result.barPing = await barView.webContents.executeJavaScript("window.auphere && window.auphere.ping()");
    result.humanIsPersistent = session.fromPartition(HUMAN).isPersistent();
    result.barIsPersistent = session.fromPartition(BAR).isPersistent();
    result.agentIsPersistent = session.fromPartition(AGENT).isPersistent();
    const image = await win.contentView.children.length ? await consoleView.webContents.capturePage() : null;
    if (image) writeFileSync(join(here, "screenshot-console.png"), image.toPNG());
    const bar = await barView.webContents.capturePage();
    writeFileSync(join(here, "screenshot-bar.png"), bar.toPNG());
    result.ok =
      result.auphereInConsoleView === "undefined" &&
      result.auphereInBarView === "object" &&
      result.barPing === "pong" &&
      result.humanIsPersistent === true &&
      result.barIsPersistent === false &&
      result.agentIsPersistent === false;
  } catch (error) {
    result.ok = false;
    result.error = String(error && error.stack ? error.stack : error);
  }
  writeFileSync(join(here, "result.json"), JSON.stringify(result, null, 2));
  app.quit();
});
