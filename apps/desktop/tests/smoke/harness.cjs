/*
 * Spec 010, T008 — el banco del humo.
 *
 * Abre **la pantalla ya construida** (`dist/app/index.html`) con las mismas
 * preferencias de vista que usa la aplicación, y nada más: ni consola remota,
 * ni sesión, ni red. Lo que se comprueba aquí es lo que sólo se ve cuando el
 * código está compilado y servido desde disco — que la política de contenido no
 * bloquea lo que la pantalla necesita, que las fuentes de marca cargan y que
 * algo se pinta.
 *
 * El recorrido de la aplicación entera, empaquetada y firmada, es otro
 * (T140): éste tiene que poder correr sin red y en cualquier máquina.
 */
const { BrowserWindow, app } = require("electron");
const { join } = require("node:path");

app.whenReady().then(async () => {
  const window = new BrowserWindow({
    width: 1100,
    height: 700,
    show: false,
    backgroundColor: "#101512",
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      // El `preload` de verdad, ya construido: sin él `window.auphere` no
      // existe y la pantalla no llegaría ni a montarse. Nadie atiende sus
      // canales en este banco, así que la pantalla pinta sus estados de error
      // — que es exactamente lo que se quiere poder ver aquí.
      preload: join(__dirname, "..", "..", "dist", "electron", "app-preload.cjs"),
    },
  });

  // Todo lo que la vista escriba en consola sale por stdout con una marca, para
  // que el test lo lea sin depender del protocolo de depuración.
  window.webContents.on("console-message", (event) => {
    const level = typeof event === "object" && event !== null && "level" in event ? event.level : "info";
    const message = typeof event === "object" && event !== null && "message" in event ? event.message : String(event);
    console.log(`[consola] ${level} ${message}`);
  });

  await window.loadFile(join(__dirname, "..", "..", "dist", "app", "index.html"));
});

app.on("window-all-closed", () => app.quit());
