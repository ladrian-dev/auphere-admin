// Preload de la BARRA únicamente. La vista de la consola no tiene ninguno.
const { contextBridge } = require("electron");
contextBridge.exposeInMainWorld("auphere", { ping: () => "pong" });
