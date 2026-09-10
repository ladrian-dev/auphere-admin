/**
 * El `preload` de la BARRA — y solo de la barra (Requisito 12.1, R3.5).
 *
 * La vista de la consola **no tiene ninguno**; el test de aislamiento de
 * particiones lo afirma. Lo que se expone aquí es exactamente lo que el contrato
 * (`contracts/desktop-bar.md`) enumera: seis funciones, ninguna que lea nada de
 * la persona. La barra pregunta y muestra lo que **solo la máquina sabe**.
 */
import { contextBridge, ipcRenderer } from "electron";

import type { BarState } from "../bar-state.js";

const api = {
  getState: (): Promise<BarState> => ipcRenderer.invoke("bar:getState"),
  onState: (callback: (state: BarState) => void): (() => void) => {
    const handler = (_event: unknown, state: BarState) => callback(state);
    ipcRenderer.on("bar:state", handler);
    return () => ipcRenderer.removeListener("bar:state", handler);
  },
  pair: (code: string): Promise<void> => ipcRenderer.invoke("bar:pair", code),
  unpair: (): Promise<void> => ipcRenderer.invoke("bar:unpair"),
  pickDirectory: (clientRef: string): Promise<void> => ipcRenderer.invoke("bar:pickDirectory", clientRef),
  openInBrowser: (url: string): Promise<void> => ipcRenderer.invoke("bar:openInBrowser", url),
};

contextBridge.exposeInMainWorld("auphere", api);

export type BarApi = typeof api;
