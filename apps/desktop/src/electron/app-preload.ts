/**
 * El `preload` de la pantalla de operar — spec 003, Requisito 12.1.
 *
 * Expone bajo `window.auphere` exactamente lo que `app-ipc.ts` enumera, y lo
 * construye `buildAppBridge` (puro, con test). Ninguna función de aquí lee
 * cookies, sesión ni credenciales: el renderer pregunta y el principal
 * contesta ya redactado.
 */
import { contextBridge, ipcRenderer } from "electron";

import { buildAppBridge } from "../app-bridge.js";

contextBridge.exposeInMainWorld("auphere", buildAppBridge(ipcRenderer));
