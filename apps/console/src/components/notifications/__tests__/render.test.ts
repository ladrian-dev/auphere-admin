import { describe, expect, it } from "vitest";

import { notificationText, severityTone } from "../render";

describe("notifications/render", () => {
  it("maps severities to tones", () => {
    expect(severityTone("info")).toBe("info");
    expect(severityTone("warning")).toBe("warning");
    expect(severityTone("critical")).toBe("danger");
  });
  it("renders known kinds in both languages and degrades unknown ones", () => {
    expect(notificationText("es", { kind: "member.joined", data: { email: "a@b.c", role: "admin" }, external_client_ref: null })).toBe(
      "a@b.c se ha unido al equipo como admin",
    );
    expect(notificationText("en", { kind: "usage.threshold", data: { percent: 80, period: "2026-08" }, external_client_ref: null })).toBe(
      "Usage at 80% of the cap (2026-08)",
    );
    expect(notificationText("es", { kind: "client.activated", data: { first: true }, external_client_ref: "acme" })).toContain("acme");
    expect(notificationText("es", { kind: "client.activated", data: { first: true }, external_client_ref: "acme" })).toContain("primer cliente");
    expect(notificationText("en", { kind: "weird.kind", data: {}, external_client_ref: null })).toBe("Notice: weird.kind");
  });
  it("says the agents stop replying, not that a cap was hit", () => {
    // D7 — el saldo corta; el tope comercial de mensajes no. El texto no
    // puede sonar igual en los dos casos.
    expect(notificationText("es", { kind: "wallet.low", data: { percent: 80, period: "2026-09" }, external_client_ref: null })).toContain(
      "dejarán de responder",
    );
    expect(notificationText("es", { kind: "wallet.empty", data: { period: "2026-09" }, external_client_ref: null })).toContain(
      "han dejado de responder",
    );
  });
  it("does not announce an activation that cannot serve as a success", () => {
    // D8 — activado sin cuota no es una buena noticia.
    const text = notificationText("es", { kind: "client.activated", data: { first: true, can_serve: false }, external_client_ref: "acme" });
    expect(text).toContain("acme");
    expect(text).toContain("no puede responder");
    expect(text).not.toContain("primer cliente");
  });
});
