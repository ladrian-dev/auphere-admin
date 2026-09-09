/**
 * El ciclo de vida de la aplicación — Requisitos 15, 6 y 12.
 *
 * Aquí se prueba **la lógica**, no Electron. La ventana en sí es pegamento fino:
 * crea un `BrowserWindow`, carga la consola y arranca esto. Probar Electron de
 * verdad exige un display y un runner gráfico; probar lo que decide, no.
 *
 * Y lo que decide es lo que puede salir mal: que el puente arranque antes de
 * comprobar el aislamiento, que se ofrezcan herramientas sin puente, o que un
 * fallo de red se pinte como un error del producto.
 */
import { describe, expect, it, vi } from "vitest";

import { AppRuntime } from "../src/app-runtime.js";

function runtime(over: Partial<ConstructorParameters<typeof AppRuntime>[0]> = {}) {
  return new AppRuntime({
    consoleUrl: "https://console.auphere.com",
    workdir: "/Users/luis/proyecto",
    transport: { send: vi.fn().mockResolvedValue(undefined), poll: vi.fn().mockResolvedValue([]) },
    approvals: { pending: vi.fn().mockResolvedValue([]), answer: vi.fn().mockResolvedValue(true) },
    ...over,
  });
}

describe("el arranque comprueba antes de conectar (15.3)", () => {
  it("verifica el aislamiento de sesión antes de abrir el puente", async () => {
    const order: string[] = [];
    const app = runtime({
      transport: {
        send: vi.fn(async () => void order.push("puente")),
        poll: vi.fn().mockResolvedValue([]),
      },
    });
    app.onIsolationChecked = () => order.push("aislamiento");
    await app.start();
    expect(order[0]).toBe("aislamiento");
  });

  it("si el aislamiento no se sostiene, la app no arranca el puente", async () => {
    const send = vi.fn();
    const app = runtime({ transport: { send, poll: vi.fn() } });
    app.forceBrokenIsolation = true;
    await expect(app.start()).rejects.toThrow();
    expect(send).not.toHaveBeenCalled();
  });
});

describe("qué se ofrece y cuándo (15.4, 4.2)", () => {
  it("recién arrancada no ofrece herramientas locales", () => {
    expect(runtime().localToolsOffered()).toBe(false);
  });

  it("con puente y latido, sí", async () => {
    const app = runtime();
    await app.start();
    await app.tick();
    expect(app.localToolsOffered()).toBe(true);
  });

  it("si el puente cae, dejan de ofrecerse en el acto", async () => {
    const app = runtime({
      transport: { send: vi.fn().mockRejectedValue(new Error("sin red")), poll: vi.fn() },
    });
    await app.start();
    await app.tick();
    expect(app.linkState).toBe("reconectando");
    expect(app.localToolsOffered()).toBe(false);
  });
});

describe("una caída no es un error del producto (§V)", () => {
  it("perder la red deja `reconectando`, no un fallo", async () => {
    const app = runtime({
      transport: { send: vi.fn().mockRejectedValue(new Error("sin red")), poll: vi.fn() },
    });
    await app.start();
    await app.tick();
    expect(app.status().tone).toBe("estado");
  });
});

describe("aprobaciones desde la app (11.1, cierra T052)", () => {
  it("las pendientes se leen de la cola global", async () => {
    const pending = vi.fn().mockResolvedValue([{ id: "spawn:1", prompt: "spawn_run(build)" }]);
    const app = runtime({ approvals: { pending, answer: vi.fn() } });
    await app.start();
    expect(await app.pendingApprovals()).toHaveLength(1);
  });

  it("contestar una aprobación la manda a la cola, no a un prompt local", async () => {
    const answer = vi.fn().mockResolvedValue(true);
    const app = runtime({ approvals: { pending: vi.fn().mockResolvedValue([]), answer } });
    await app.start();
    await app.answerApproval("spawn:1", true);
    expect(answer).toHaveBeenCalledWith("spawn:1", true);
  });
});
