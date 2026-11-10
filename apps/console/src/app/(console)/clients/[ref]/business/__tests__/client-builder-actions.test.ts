import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { clientBuilderJobAction, startClientBuilderAction } = await import("../client-builder-actions");

const JOB = "66666666-6666-4666-8666-666666666666";

/** Spec 047 (T098) — «Completar con el constructor»: lanzarlo es de `clients:write`; consultarlo, de `clients:read`. */
describe("«Completar con el constructor»", () => {
  beforeEach(() => vi.clearAllMocks());

  it("quien edita la ficha lo lanza y lo consulta; terminado, Negocio se refresca", async () => {
    h.setRole("builder");
    h.backend.startClientBuilder.mockResolvedValueOnce({ job_id: JOB });
    expect(await startClientBuilderAction({ ref: "demo" })).toEqual({ ok: true, data: { job_id: JOB } });
    expect(h.backend.startClientBuilder).toHaveBeenCalledWith("demo");
    h.backend.getConsoleJob.mockResolvedValueOnce({ job_id: JOB, kind: "client_builder", status: "done" });
    await clientBuilderJobAction({ ref: "demo", job: JOB });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/business");
  });

  it("un analista no lo lanza", async () => {
    h.setRole("analyst");
    expect(await startClientBuilderAction({ ref: "demo" })).toEqual(h.denied());
    expect(h.backend.startClientBuilder).not.toHaveBeenCalled();
  });
});
