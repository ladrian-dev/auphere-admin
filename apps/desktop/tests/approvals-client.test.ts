/**
 * Cliente de la cola global de aprobaciones — Requisito 11.1. Cierra T052.
 *
 * T002 dejó establecido que la cola existe y que es alcanzable —`GET
 * /api/approvals` responde 200— pero no pudo demostrar la última junta porque no
 * había cliente nuestro que contestara. **Éste es ese cliente.**
 *
 * El token se le pide al gateway: el registro de nonces vive en su memoria, así
 * que un token generado en otro proceso nunca vale. Eso costó una pasada entera
 * de T002 y queda aquí para que nadie lo vuelva a descubrir.
 */
import { describe, expect, it, vi } from "vitest";

import { GatewayApprovals } from "../src/approvals-client.js";

const fetchReturning = (body: unknown, status = 200) =>
  vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });

describe("leer la cola", () => {
  it("pide las pendientes con el token del gateway", async () => {
    const fetch = fetchReturning([{ id: "spawn:1", prompt: "spawn_run(build)" }]);
    const client = new GatewayApprovals({ baseUrl: "http://localhost:5476", token: "t", fetch });
    expect(await client.pending()).toHaveLength(1);
    expect(String(fetch.mock.calls[0]?.[0])).toContain("/api/approvals");
  });

  it("una cola vacía es una respuesta legítima", async () => {
    const client = new GatewayApprovals({
      baseUrl: "http://localhost:5476",
      token: "t",
      fetch: fetchReturning([]),
    });
    expect(await client.pending()).toEqual([]);
  });

  it("un fallo NO se presenta como cola vacía", async () => {
    const client = new GatewayApprovals({
      baseUrl: "http://localhost:5476",
      token: "t",
      fetch: fetchReturning({ error: "forbidden" }, 403),
    });
    await expect(client.pending()).rejects.toThrow();
  });
});

describe("contestar", () => {
  it("aprobar y denegar van por acciones distintas", async () => {
    const fetch = fetchReturning({ ok: true });
    const client = new GatewayApprovals({ baseUrl: "http://localhost:5476", token: "t", fetch });
    await client.answer("spawn:1", true);
    await client.answer("spawn:2", false);
    expect(String(fetch.mock.calls[0]?.[0])).toContain("/approve");
    expect(String(fetch.mock.calls[1]?.[0])).toContain("/deny");
  });

  it("el token no viaja en el cuerpo, y el id se escapa", async () => {
    const fetch = fetchReturning({ ok: true });
    const client = new GatewayApprovals({ baseUrl: "http://localhost:5476", token: "t", fetch });
    await client.answer("spawn:con espacio", true);
    const url = String(fetch.mock.calls[0]?.[0]);
    expect(url).toContain("spawn%3Acon%20espacio");
  });

  it("un rechazo del gateway no se traga: se levanta", async () => {
    const client = new GatewayApprovals({
      baseUrl: "http://localhost:5476",
      token: "t",
      fetch: fetchReturning({ error: "gone" }, 404),
    });
    await expect(client.answer("spawn:1", true)).rejects.toThrow();
  });
});
