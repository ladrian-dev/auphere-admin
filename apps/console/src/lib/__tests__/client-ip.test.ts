/**
 * Requisito 7.1 — la IP del visitante llega a la API o no llega nada.
 */
import { describe, expect, it } from "vitest";

import { CLIENT_IP_HEADER, clientIpFrom, clientIpHeader } from "../client-ip";

const headers = (map: Record<string, string>) => ({
  get: (name: string) => map[name.toLowerCase()] ?? null,
});

describe("de dónde sale la IP del visitante", () => {
  it("el primer valor de x-forwarded-for es el cliente, el resto son proxies", () => {
    expect(clientIpFrom(headers({ "x-forwarded-for": "203.0.113.7, 70.41.3.18, 150.172.238.178" })))
      .toBe("203.0.113.7");
  });

  it("cae a x-real-ip cuando no hay forwarded", () => {
    expect(clientIpFrom(headers({ "x-real-ip": "203.0.113.9" }))).toBe("203.0.113.9");
  });

  it("prefiere forwarded sobre real-ip", () => {
    expect(clientIpFrom(headers({ "x-forwarded-for": "1.1.1.1", "x-real-ip": "2.2.2.2" }))).toBe("1.1.1.1");
  });
});

describe("cuando no se sabe, no se inventa", () => {
  it("sin ninguna cabecera devuelve null", () => {
    expect(clientIpFrom(headers({}))).toBeNull();
  });

  it("con valores vacíos devuelve null, no cadena vacía", () => {
    expect(clientIpFrom(headers({ "x-forwarded-for": "", "x-real-ip": "  " }))).toBeNull();
  });

  it("y entonces NO se manda la cabecera: la API cae a su cubo único con nombre", () => {
    // Mandar la cabecera vacía sería peor que no mandarla: la API tendría que
    // decidir si una cadena vacía es una IP, y ya lo decide una sola vez.
    expect(clientIpHeader(headers({}))).toEqual({});
  });
});

describe("la cabecera que se manda", () => {
  it("lleva el nombre que la API espera", () => {
    expect(clientIpHeader(headers({ "x-forwarded-for": "203.0.113.7" }))).toEqual({
      [CLIENT_IP_HEADER]: "203.0.113.7",
    });
    expect(CLIENT_IP_HEADER.toLowerCase()).toBe("x-nexus-client-ip");
  });
});
