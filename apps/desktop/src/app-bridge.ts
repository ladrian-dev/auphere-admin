/**
 * Lo que el `preload` de la pantalla construye — spec 003, R12.1.
 *
 * Puro y probado: recibe un `ipcRenderer` (real o de mentira) y devuelve el
 * objeto que va a `window.auphere`. Una función por canal de invocación, y
 * `on(channel, cb)` solo para los canales de empuje de la lista. Nada más:
 * ni `ipcRenderer` a secas, ni `require`, ni una vía genérica.
 */
import { APP_INVOKE_CHANNELS, APP_PUSH_CHANNELS, type PushChannel } from "./app-ipc.js";

export interface IpcRendererLike {
  invoke(channel: string, ...args: unknown[]): Promise<unknown>;
  on(channel: string, listener: (event: unknown, payload: unknown) => void): void;
  removeListener(channel: string, listener: (event: unknown, payload: unknown) => void): void;
}

export type AppBridge = Record<string, (input?: unknown) => Promise<unknown>> & {
  on(channel: PushChannel, callback: (payload: unknown) => void): () => void;
};

/** `app:roster.list` → `rosterList`; `app:openConsole` → `openConsole`. */
export function methodName(channel: string): string {
  return channel
    .replace(/^app:/, "")
    .replace(/[.:_]([a-zA-Z])/g, (_m, c: string) => c.toUpperCase());
}

export function buildAppBridge(ipc: IpcRendererLike): AppBridge {
  const bridge: Record<string, unknown> = {};
  for (const { name } of APP_INVOKE_CHANNELS) {
    bridge[methodName(name)] = (input?: unknown) => ipc.invoke(name, input);
  }
  bridge.on = (channel: PushChannel, callback: (payload: unknown) => void): (() => void) => {
    if (!(APP_PUSH_CHANNELS as readonly string[]).includes(channel)) {
      throw new Error(`canal de empuje fuera de la lista: ${channel}`);
    }
    const listener = (_event: unknown, payload: unknown) => callback(payload);
    ipc.on(channel, listener);
    return () => ipc.removeListener(channel, listener);
  };
  return bridge as AppBridge;
}
