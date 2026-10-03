import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { setCapabilityAction } = await import("../actions");

/**
 * Spec 017 · R5.4: un clic enciende o apaga una capacidad y eso ya queda
 * guardado en el borrador. Sin «Guardar» aparte, y **un cambio por
 * llamada**: la pantalla vieja mandaba la lista blanca entera, así que dos
 * personas editando a la vez se pisaban sin enterarse.
 */
describe("encender y apagar una capacidad", () => {
  it("un editor la enciende y la llamada nombra solo esa", async () => {
    h.setRole("builder");
    h.backend.setCapability.mockResolvedValueOnce({ capability: { key: "booking.create_appointment" }, draft_created: true });
    const res = await setCapabilityAction({ ref: "demo", key: "booking.create_appointment", kind: "tool", enabled: true });
    expect(res).toMatchObject({ ok: true });
    expect(h.backend.setCapability).toHaveBeenCalledWith("demo", {
      key: "booking.create_appointment",
      kind: "tool",
      enabled: true,
    });
  });

  it("cambiar el modo va por la misma puerta", async () => {
    h.setRole("owner");
    h.backend.setCapability.mockResolvedValueOnce({ capability: {}, draft_created: false });
    await setCapabilityAction({ ref: "demo", key: "booking.create_appointment", kind: "tool", mode: "blocked" });
    expect(h.backend.setCapability).toHaveBeenCalledWith("demo", {
      key: "booking.create_appointment",
      kind: "tool",
      mode: "blocked",
    });
  });

  it("un analista no cambia nada, y no se llega a llamar al backend", async () => {
    h.setRole("analyst");
    h.backend.setCapability.mockClear();
    expect(await setCapabilityAction({ ref: "demo", key: "x.y", kind: "tool", enabled: true })).toEqual(h.denied());
    expect(h.backend.setCapability).not.toHaveBeenCalled();
  });

  it("«requiere aprobación» no sale ni de aquí", async () => {
    // R5.7: se retira. Que la pantalla no pueda pedirlo es la primera
    // barrera; la API lo rechaza igualmente con su motivo.
    h.setRole("owner");
    h.backend.setCapability.mockClear();
    await expect(
      setCapabilityAction({ ref: "demo", key: "x.y", kind: "tool", mode: "needs_approval" }),
    ).rejects.toThrow();
    expect(h.backend.setCapability).not.toHaveBeenCalled();
  });

  it("una llamada que no cambia nada no se manda", async () => {
    h.setRole("owner");
    h.backend.setCapability.mockClear();
    await expect(setCapabilityAction({ ref: "demo", key: "x.y", kind: "tool" })).rejects.toThrow();
    expect(h.backend.setCapability).not.toHaveBeenCalled();
  });
});
