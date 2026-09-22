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
  "app:whoami", "app:roster.list", "app:roster.create", "app:roster.update", "app:roster.archive", "app:roster.changes", "app:roster.jobs",
  "app:thread.open", "app:thread.create", "app:thread.list", "app:companion.search", "app:thread.runs", "app:run.events", "app:thread.send", "app:thread.cancel",
  "app:stream.open", "app:stream.close",
  "app:inbox.list", "app:inbox.decide", "app:tasks.list", "app:tasks.cancel",
  "app:policy.prefs", "app:policy.setPref", "app:usage", "app:membership", "app:team", "app:env.forThread",
  "app:openConsole", "app:notifications.prefs",
  // Spec 010 — el armazón, el puesto absorbido, la entrada por navegador, la
  // puesta en marcha, la actualización y la vuelta del navegador.
  "app:shell.showSection", "app:shell.contentBounds", "app:shell.prefs",
  "app:signIn.start", "app:signIn.cancel",
  "app:workstation.state", "app:workstation.unpair", "app:workstation.pickDirectory",
  // Spec 013, R3 — lo que escribió un comando ya ejecutado. La salida no se
  // guarda en ninguna tabla: esto la pide mientras dura.
  "app:workstation.execOutput",
  "app:setup.status", "app:update.install", "app:update.check", "app:system.openNotificationSettings", "app:handoff.done",
];
const PUSH = [
  "app:event", "app:inbox", "app:inbox.focus", "app:stream.end", "app:inbox.changed", "app:task.state", "app:session", "app:presence",
  // Spec 010.
  "app:console.location", "app:console.failed", "app:handoff", "app:workstation", "app:signIn", "app:update", "app:waiting", "app:connectivity",
  "app:shell.toggleSidebar",
];

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
    expect(() => validateInput("app:cookies.read", {})).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:thread.send", { thread_id: "no", text: "x" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:inbox.decide", { action_id: id, run_id: id, decision: "maybe" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:openConsole", { path: "//evil" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:openConsole", { path: "https://evil" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:policy.setPref", { executable: "make", mode: "sometimes" })).toThrow(InvalidIpcInput);
  });
});

/**
 * Spec 010 — lo que entra por los canales del armazón.
 *
 * Tres entradas nuevas merecen validación propia porque son las únicas que
 * llevan algo que alguien podría torcer: una sección, un rectángulo y un código
 * de emparejamiento.
 */
describe("el armazón tampoco adivina", () => {
  it("la sección tiene que estar en la lista canónica", () => {
    expect(() => validateInput("app:shell.showSection", { section: "consumo" })).not.toThrow();
    expect(() => validateInput("app:shell.showSection", { section: "hoy" })).not.toThrow();
    expect(() => validateInput("app:shell.showSection", { section: "lo-que-sea" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:shell.showSection", { section: "/billing" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:shell.showSection", {})).toThrow(InvalidIpcInput);
  });

  it("el rectángulo del panel son cuatro enteros no negativos", () => {
    expect(() => validateInput("app:shell.contentBounds", { x: 220, y: 52, width: 880, height: 648 })).not.toThrow();
    expect(() => validateInput("app:shell.contentBounds", { x: 0, y: 0, width: 0, height: 0 })).not.toThrow();
    expect(() => validateInput("app:shell.contentBounds", { x: -1, y: 0, width: 10, height: 10 })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:shell.contentBounds", { x: 0.5, y: 0, width: 10, height: 10 })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:shell.contentBounds", { x: 0, y: 0, width: 10 })).toThrow(InvalidIpcInput);
  });

  it("el canal de emparejar por código ya no existe (spec 012)", () => {
    // Se retiró con el código: la máquina se registra al entrar, desde el
    // proceso principal y con la cookie de la partición humana, así que no hay
    // nada que la ventana tenga que mandar ni que validar aquí.
    expect(APP_INVOKE_CHANNELS.map((c) => c.name)).not.toContain("app:workstation.pair");
    expect(() => validateInput("app:workstation.pair", { code: "K7MP4XQ2" })).toThrow();
  });
  it("las preferencias de la ventana sólo aceptan lo que la lista permite guardar", () => {
    expect(() => validateInput("app:shell.prefs", { theme: "dark" })).not.toThrow();
    expect(() => validateInput("app:shell.prefs", { sidebarWidth: 260 })).not.toThrow();
    expect(() => validateInput("app:shell.prefs", { theme: "morado" })).toThrow(InvalidIpcInput);
    expect(() => validateInput("app:shell.prefs", { sidebarWidth: -20 })).toThrow(InvalidIpcInput);
  });

  it("el traspaso dice de qué vuelve, y sólo hay dos cosas de las que volver", () => {
    expect(() => validateInput("app:handoff.done", { kind: "payment" })).not.toThrow();
    expect(() => validateInput("app:handoff.done", { kind: "sign_in" })).not.toThrow();
    expect(() => validateInput("app:handoff.done", { kind: "otra-cosa" })).toThrow(InvalidIpcInput);
  });

  it("lo que no lleva entrada, no la acepta inventada", () => {
    expect(() => validateInput("app:signIn.start", undefined)).not.toThrow();
    expect(() => validateInput("app:workstation.state", undefined)).not.toThrow();
    expect(() => validateInput("app:setup.status", undefined)).not.toThrow();
    expect(() => validateInput("app:update.install", undefined)).not.toThrow();
  });

  it("elegir directorio va por cliente", () => {
    expect(() => validateInput("app:workstation.pickDirectory", { client_ref: "cultor-barber" })).not.toThrow();
    expect(() => validateInput("app:workstation.pickDirectory", {})).toThrow(InvalidIpcInput);
    // La entrada **se valida, no se adivina**: sin cliente o con un id que no
    // es un uuid, no se llega a tocar la red.
    expect(() =>
      validateInput("app:workstation.execOutput", {
        client_ref: "cultor-barber",
        execution_id: "0f9d5a1e-9a21-4a3f-9a1c-2f1b0c3d4e5f",
      }),
    ).not.toThrow();
    expect(() => validateInput("app:workstation.execOutput", { client_ref: "x" })).toThrow(InvalidIpcInput);
    expect(() =>
      validateInput("app:workstation.execOutput", { client_ref: "x", execution_id: "no-es-uuid" }),
    ).toThrow(InvalidIpcInput);
  });
});
