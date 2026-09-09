import { describe, expect, it } from "vitest";

import {
  HEARTBEAT_INTERVAL_MS,
  PRESENCE_EXPIRY_MS,
  derivePresence,
  secondsSinceHeartbeat,
} from "../src/presence.js";

describe("presencia derivada del latido (Requisito 4.1, 4.2)", () => {
  it("un dispositivo nunca visto está ausente", () => {
    expect(derivePresence(null, 1_000_000)).toBe("ausente");
  });

  it("dentro de la ventana está presente", () => {
    const now = 1_000_000;
    expect(derivePresence(now - (PRESENCE_EXPIRY_MS - 1), now)).toBe("presente");
  });

  it("al caducar la ventana pasa a ausente", () => {
    const now = 1_000_000;
    expect(derivePresence(now - PRESENCE_EXPIRY_MS, now)).toBe("ausente");
  });

  it("la caducidad cabe dentro del minuto que exige CE-004", () => {
    expect(PRESENCE_EXPIRY_MS).toBeLessThan(60_000);
  });

  it("hay margen para perder latidos antes de declarar ausencia", () => {
    expect(PRESENCE_EXPIRY_MS).toBeGreaterThanOrEqual(HEARTBEAT_INTERVAL_MS * 2);
  });

  it("informa desde cuándo está desconectado, para que sea estado y no error", () => {
    const now = 1_000_000;
    expect(secondsSinceHeartbeat(now - 45_000, now)).toBe(45);
    expect(secondsSinceHeartbeat(null, now)).toBeNull();
  });
});
