import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { acceptCorrectionBatchAction, discardCorrectionBatchAction } = await import("../improve-actions");

const BATCH = "00000000-0000-4000-8000-0000000000b1";

/**
 * Spec 056 (9.2): el lote de «Todo el negocio» se decide en todos sus agentes a
 * la vez. Como decidir una sola corrección, pide `agents:write`: owner, admin y
 * builder pueden; analyst, billing y la persona de un cliente no llegan a la API.
 */
describe("decidir el lote de una corrección", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each(["owner", "admin", "builder"] as const)("%s acepta y descarta el lote", async (role) => {
    h.setRole(role);
    await acceptCorrectionBatchAction({ ref: "demo", batch: BATCH });
    expect(h.backend.acceptCorrectionBatch).toHaveBeenCalledWith("demo", BATCH);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
    await discardCorrectionBatchAction({ ref: "demo", batch: BATCH, reason: "  No aplica  " });
    expect(h.backend.discardCorrectionBatch).toHaveBeenCalledWith("demo", BATCH, "No aplica");
  });

  it.each(["analyst", "billing"] as const)("%s no puede", async (role) => {
    h.setRole(role);
    expect(await acceptCorrectionBatchAction({ ref: "demo", batch: BATCH })).toEqual(h.denied());
    expect(await discardCorrectionBatchAction({ ref: "demo", batch: BATCH, reason: "No aplica" })).toEqual(h.denied());
    expect(h.backend.acceptCorrectionBatch).not.toHaveBeenCalled();
    expect(h.backend.discardCorrectionBatch).not.toHaveBeenCalled();
  });

  it("la persona de un cliente tampoco", async () => {
    h.setClient(["panel", "inbox"]);
    expect(await acceptCorrectionBatchAction({ ref: "demo", batch: BATCH })).toEqual(h.denied());
    expect(h.backend.acceptCorrectionBatch).not.toHaveBeenCalled();
  });

  it("un lote que no es un id, o un motivo corto, no sale", async () => {
    h.setRole("owner");
    await expect(acceptCorrectionBatchAction({ ref: "demo", batch: "lote" })).rejects.toThrow();
    await expect(discardCorrectionBatchAction({ ref: "demo", batch: BATCH, reason: "no" })).rejects.toThrow();
    expect(h.backend.discardCorrectionBatch).not.toHaveBeenCalled();
  });

  it("los «no» de la API vuelven con su código", async () => {
    h.setRole("owner");
    h.fail("acceptCorrectionBatch", 409, "", "improvement_closed");
    expect(await acceptCorrectionBatchAction({ ref: "demo", batch: BATCH })).toMatchObject({ ok: false, code: "improvement_closed" });
  });
});
