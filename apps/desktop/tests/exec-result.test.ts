/**
 * Requisito 3.3 — lo que la máquina contesta, y lo que **no** manda nunca.
 *
 * Dos mitades: el trabajo llega en el formato del cable y se traduce aquí (si
 * llega a medias, no se ejecuta), y el resultado vuelve con una muestra
 * acotada y su código de denegación, sin nada más de esta máquina.
 */
import { describe, expect, it, vi } from "vitest";

import { HttpTransport } from "../src/http-transport.js";
import { STDOUT_SAMPLE_LIMIT } from "../src/executor.js";

function transport(fetchImpl: typeof fetch) {
  return new HttpTransport({
    baseUrl: "https://api.test",
    appVersion: "1.2.3",
    fetch: fetchImpl as never,
    token: () => "t",
  } as never);
}

const ok = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });

describe("el trabajo que llega por el puente", () => {
  const work = {
    execution_id: "11111111-2222-4333-8444-555555555555",
    client_ref: "cultor",
    executable: "make",
    args: ["test"],
    cwd_relative: "src",
    timeout_ms: 600000,
    idle_timeout_ms: 300000,
  };

  it("se traduce del cable a lo que la aplicación entiende", async () => {
    const t = transport(vi.fn(async () => ok({ work: [work], links: [] })) as never);
    const polled = await t.pollAll();
    expect(polled.work).toEqual([
      {
        kind: "execute",
        executionId: work.execution_id,
        executable: "make",
        args: ["test"],
        cwdRelative: "src",
        timeoutMs: 600000,
        clientRef: "cultor",
      },
    ]);
  });

  it("lo que llega a medias NO se ejecuta", async () => {
    const roto = [
      { ...work, executable: undefined },
      { ...work, execution_id: undefined },
      // Un argumento que no es cadena: no se adivina lo que quería decir.
      { ...work, args: ["test", { rm: "-rf" }] },
      "no soy un objeto",
    ];
    const t = transport(vi.fn(async () => ok({ work: roto, links: [] })) as never);
    expect((await t.pollAll()).work).toEqual([]);
  });
});

describe("el resultado que vuelve", () => {
  it("lleva la muestra acotada y el código de denegación, y nada más", async () => {
    const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
    const t = transport(
      vi.fn(async (url: string, init: RequestInit) => {
        calls.push({ url, body: JSON.parse(String(init.body)) });
        return new Response(null, { status: 204 });
      }) as never,
    );
    await t.send({
      kind: "execution_result",
      executionId: "e1",
      outcome: "denegada",
      exitCode: null,
      childrenReaped: 0,
      stdoutSample: "x".repeat(STDOUT_SAMPLE_LIMIT * 3),
      denialCode: "fuera_del_directorio",
    });
    expect(calls[0]?.url).toBe("https://api.test/device/result");
    const body = calls[0]!.body;
    expect(String(body.stdout_sample)).toHaveLength(STDOUT_SAMPLE_LIMIT);
    expect(body.denial_code).toBe("fuera_del_directorio");
    expect(Object.keys(body).sort()).toEqual(
      ["children_reaped", "denial_code", "execution_id", "exit_code", "outcome", "stdout_sample"].sort(),
    );
  });

  it("sin muestra no manda la clave vacía", async () => {
    const calls: Array<Record<string, unknown>> = [];
    const t = transport(
      vi.fn(async (_url: string, init: RequestInit) => {
        calls.push(JSON.parse(String(init.body)));
        return new Response(null, { status: 204 });
      }) as never,
    );
    await t.send({
      kind: "execution_result",
      executionId: "e1",
      outcome: "completada",
      exitCode: 0,
      childrenReaped: 0,
    });
    expect(calls[0]?.stdout_sample).toBeUndefined();
  });
});
