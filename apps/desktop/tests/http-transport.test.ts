/**
 * El transporte real del puente — Requisitos 6.1 y 6.2.
 *
 * Cierra el recorrido: hasta ahora `AppRuntime` hablaba con un talón porque el
 * otro extremo no existía. Ya existe.
 *
 * Lo que se comprueba no es que llame a las rutas —eso es fontanería— sino las
 * dos propiedades que hacen que el puente sea seguro: **solo sale** y **un fallo
 * no se disfraza de silencio**.
 */
import { describe, expect, it, vi } from "vitest";

import { HttpTransport } from "../src/http-transport.js";

const ok = (body: unknown = {}) =>
  vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body });

describe("solo sale (6.1)", () => {
  it("el latido va por POST y lleva la credencial del dispositivo", async () => {
    const fetch = ok();
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "dev-token", fetch });
    await t.send({ kind: "heartbeat", at: 1 });
    const [url, init] = fetch.mock.calls[0] ?? [];
    expect(String(url)).toContain("/device/heartbeat");
    expect(init?.method).toBe("POST");
    expect(init?.headers?.Authorization).toBe("Bearer dev-token");
  });

  it("el sondeo pide, no escucha", async () => {
    const fetch = ok({ work: [] });
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await t.poll();
    expect(String(fetch.mock.calls[0]?.[0])).toContain("/device/poll");
    expect(fetch.mock.calls[0]?.[1]?.method ?? "GET").toBe("GET");
  });

  it("no expone ninguna forma de escuchar", () => {
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch: ok() });
    expect(Object.keys(Object.getPrototypeOf(t)).concat(Object.keys(t))).not.toContain("listen");
  });
});

describe("un fallo no se disfraza de silencio (§V)", () => {
  it("si el sondeo falla, se levanta en vez de devolver «no hay trabajo»", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) });
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await expect(t.poll()).rejects.toThrow();
  });

  it("si el latido falla, se levanta y el puente pasa a `reconectando`", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("sin red"));
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await expect(t.send({ kind: "heartbeat", at: 1 })).rejects.toThrow();
  });
});

describe("el resultado no lleva la salida del comando (§III)", () => {
  it("solo viaja qué pasó, no qué dijo", async () => {
    const fetch = ok();
    const t = new HttpTransport({ baseUrl: "https://api.auphere.com", token: "x", fetch });
    await t.send({
      kind: "execution_result",
      executionId: "11111111-1111-1111-1111-111111111111",
      outcome: "completada",
      exitCode: 0,
      childrenReaped: 0,
    });
    const body = String(fetch.mock.calls[0]?.[1]?.body ?? "");
    expect(body).toContain("execution_id");
    expect(body).not.toContain("stdout");
    expect(body).not.toContain("output");
  });
});
