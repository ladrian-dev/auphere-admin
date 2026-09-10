/**
 * Requisito 12.1 — el canal de la pantalla es una lista cerrada.
 *
 * `app-ipc.ts` es el contrato (`contracts/desktop-app-ipc.md`); el `preload`
 * lo construye con `buildAppBridge`. Aquí se afirma que lo expuesto es
 * exactamente la lista —ni un canal más, ni `ipcRenderer` a secas— y que la
 * validación de entradas no adivina.
 */
import { describe, expect, it, vi } from "vitest";

import { buildAppBridge, methodName, type IpcRendererLike } from "../src/app-bridge.js";
import { APP_INVOKE_CHANNELS, APP_PUSH_CHANNELS, InvalidIpcInput, validateInput } from "../src/app-ipc.js";

const CONTRACT = [
  "app:whoami", "app:roster.list", "app:roster.create", "app:roster.update", "app:roster.archive", "app:roster.jobs",
  "app:thread.open", "app:thread.runs", "app:run.events", "app:thread.send", "app:thread.cancel",
  "app:stream.open", "app:stream.close",
  "app:inbox.list", "app:inbox.decide", "app:tasks.list", "app:tasks.cancel",
  "app:policy.prefs", "app:policy.setPref", "app:usage", "app:env.forThread",
  "app:openConsole", "app:notifications.prefs",
];
const PUSH = ["app:event", "app:inbox", "app:inbox.focus", "app:stream.end", "app:inbox.changed", "app:task.state", "app:session", "app:presence"];

function fakeIpc(): IpcRendererLike & { invoke: ReturnType<typeof vi.fn> } {
  return { invoke: vi.fn(async () => ({})), on: vi.fn(), removeListener: vi.fn() };
}

describe("la lista es el contrato (12.1)", () => {
  it("los canales de invocación son exactamente los del contrato, sin duplicados", () => {
    expect(APP_INVOKE_CHANNELS.map((c) => c.name)).toEqual(CONTRACT);
    expect(new Set(APP_INVOKE_CHANNELS.map((c) => c.name)).size).toBe(CONTRACT.length);
    expect([...APP_PUSH_CHANNELS]).toEqual(PUSH);
  });

  it("el preload expone una función por canal y `on`, y nada más", () => {
    const bridge = buildAppBridge(fakeIpc());
    const expected = [...CONTRACT.map(methodName), "on"].sort();
    expect(Object.keys(bridge).sort()).toEqual(expected);
    expect(bridge).not.toHaveProperty("invoke");
    expect(bridge).not.toHaveProperty("ipcRenderer");
    expect(bridge).not.toHaveProperty("send");
  });

  it("cada función invoca su canal con la entrada tal cual", async () => {
    const ipc = fakeIpc();
    const bridge = buildAppBridge(ipc);
    await bridge.rosterList?.();
    await bridge.threadSend?.({ thread_id: "t", text: "hola" });
    expect(ipc.invoke).toHaveBeenNthCalledWith(1, "app:roster.list", undefined);
    expect(ipc.invoke).toHaveBeenNthCalledWith(2, "app:thread.send", { thread_id: "t", text: "hola" });
  });

  it("`on` solo acepta canales de empuje de la lista", () => {
    const bridge = buildAppBridge(fakeIpc());
    expect(() => bridge.on("app:event", () => {})).not.toThrow();
    expect(() => bridge.on("app:cookies" as never, () => {})).toThrow(/fuera de la lista/);
  });
});

describe("la entrada se valida, no se adivina", () => {
  const id = "11111111-2222-4333-8444-555555555555";
  it("acepta lo bien formado", () => {
    expect(() => validateInput("app:thread.send", { thread_id: id, text: "hola" })).not.toThrow();
    expect(() => validateInput("app:stream.open", { run_id: id, since_seq: 0 })).not.toThrow();
    expect(() => validateInput("app:policy.setPref", { executable: null, mode: "never" })).not.toThrow();
    expect(() => validateInput("app:openConsole", { path: "/clients/cultor" })).not.toThrow();
  });
  it("rechaza canales fuera de la lista y entradas mal formadas", () => {
    expect(() => validateInput("app:shell", {})).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:thread.send", { thread_id: "no", text: "x" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:inbox.decide", { action_id: id, run_id: id, decision: "maybe" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:openConsole", { path: "//evil" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:openConsole", { path: "https://evil" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:policy.setPref", { executable: "make", mode: "sometimes" })).toThrow(InvalidIpcInput);
  });
});
