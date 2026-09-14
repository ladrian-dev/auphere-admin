import { describe, expect, it } from "vitest";

import type { SignupRowOut } from "@/lib/backend";
import {
  canResend,
  entryRouteLabel,
  isHalfFinished,
  signupStatusLabel,
  signupTone,
} from "@/lib/signups";

/**
 * El vocabulario del alta autónoma en el panel — spec 006, Requisito 8.
 *
 * Lo que se vigila aquí no es el texto, es el criterio: que un registro a
 * medias **no** pueda pasar por una empresa, y que sólo lo vivo se reenvíe.
 */
function row(over: Partial<SignupRowOut> = {}): SignupRowOut {
  return {
    id: "s1",
    email: "maria@agencia.com",
    status: "pending",
    provider: "password",
    created_at: "2026-09-14T10:00:00Z",
    expires_at: new Date(Date.now() + 3_600_000).toISOString(),
    consumed_at: null,
    partner: null,
    ...over,
  };
}

describe("la vía de entrada se nombra", () => {
  it("Google y contraseña, nunca un null que haya que interpretar", () => {
    expect(entryRouteLabel("google")).toBe("Google");
    expect(entryRouteLabel("password")).toBe("Contraseña");
  });
});

describe("un registro a medias no es una empresa", () => {
  it("sin partner y pendiente: a medias", () => {
    expect(isHalfFinished(row())).toBe(true);
  });

  it("con partner NO es a medias, aunque el estado dijera otra cosa", () => {
    const conEmpresa = row({
      status: "pending",
      partner: { id: "p1", name: "Agencia", slug: "agencia", status: "active", tier: "free" },
    });
    expect(isHalfFinished(conEmpresa)).toBe(false);
  });

  it("caducada sin partner tampoco es «a medias»: ya no espera a nadie", () => {
    expect(isHalfFinished(row({ status: "expired" }))).toBe(false);
  });
});

describe("pendiente se pinta como aviso, no como éxito", () => {
  it("hay alguien esperando con un reloj corriendo", () => {
    expect(signupTone("pending")).toBe("warning");
    expect(signupTone("consumed")).toBe("positive");
    expect(signupTone("expired")).toBe("muted");
    expect(signupTone("revoked")).toBe("muted");
  });

  it("cada estado tiene su palabra y ninguna se repite", () => {
    const labels = (["pending", "consumed", "expired", "revoked"] as const).map(
      signupStatusLabel,
    );
    expect(new Set(labels).size).toBe(4);
  });
});

describe("sólo lo vivo se reenvía", () => {
  it("pendiente y sin caducar, sí", () => {
    expect(canResend(row())).toBe(true);
  });

  it("pendiente PERO caducada, no — el plazo no es una sugerencia", () => {
    expect(canResend(row({ expires_at: new Date(Date.now() - 1000).toISOString() }))).toBe(false);
  });

  it("consumida, no: ya tiene cuenta y la mandaría a rehacer lo hecho", () => {
    expect(canResend(row({ status: "consumed" }))).toBe(false);
  });
});
