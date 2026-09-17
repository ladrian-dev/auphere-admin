/**
 * El `preload` de la BARRA — y solo de la barra (Requisito 12.1, R3.5).
 *
 * La vista de la consola **no tiene ninguno**; el test de aislamiento de
 * particiones lo afirma. Lo que se expone aquí es exactamente lo que el contrato
 * (`contracts/desktop-bar.md`) enumera: **siete** funciones desde la spec 009,
 * ninguna que lea nada de la persona. La barra pregunta y muestra lo que **solo
 * la máquina sabe**.
 *
 * **Eran seis, y ampliarlo costó una spec.** `showApp` entra
 * porque la barra no puede cambiar de superficie ni entregar un código sin un
 * canal al principal — que es justo el propósito de no dárselo. El argumento
 * está en `specs/009-volver-y-entrar-desde-la-app/contracts/bar-preload.md`; el
 * precedente que dijo que no a un séptimo por menos motivo, en `bar/bar.ts`.
 */
import { contextBridge, ipcRenderer } from "electron";

import type { BarState } from "../workstation-state.js";

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
  /** Vuelve a la pantalla del equipo. **No acepta a dónde ir**: sólo sabe
   *  volver, que es menos superficie que auditar (spec 009, R1.1). */
  showApp: (): Promise<void> => ipcRenderer.invoke("bar:showApp"),
};

contextBridge.exposeInMainWorld("auphere", api);

export type BarApi = typeof api;
