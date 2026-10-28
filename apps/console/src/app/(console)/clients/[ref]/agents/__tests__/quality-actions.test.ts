import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../quality-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const SESSION = "55555555-5555-4555-8555-555555555555";
const JOB = "66666666-6666-4666-8666-666666666666";
const TEST = "77777777-7777-4777-8777-000000000001";
const ids = { ref: "demo", agent: AGENT };

/**
 * Spec 047 (T089, T094) — las acciones del probador, las pruebas, la revisión
 * y «Guardar»: leer con `agents:read` (el analyst lo ve todo, 20.5) y
 * escribir, probar y guardar con `agents:write`. Los límites se comprueban
 * antes de llamar y los códigos de la API vuelven tal cual.
 */
describe("las acciones de probar y guardar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("el probador: abrir con una versión, escribir, cambiar la hora y cerrar", async () => {
    await actions.openPlaygroundAction({ ...ids, version: 2 });
    expect(h.backend.openPlaygroundSession).toHaveBeenCalledWith("demo", AGENT, { version: 2 });
    await actions.sendPlaygroundAction({ ...ids, session: SESSION, text: " quiero reservar " });
    expect(h.backend.sendPlaygroundMessage).toHaveBeenCalledWith("demo", AGENT, SESSION, "quiero reservar");
    await actions.setPlaygroundTimeAction({ ...ids, session: SESSION, now: "2026-11-01T20:30:00" });
    expect(h.backend.setPlaygroundTime).toHaveBeenCalledWith("demo", AGENT, SESSION, "2026-11-01T20:30:00");
    await actions.closePlaygroundAction({ ...ids, session: SESSION });
    expect(h.backend.closePlaygroundSession).toHaveBeenCalledWith("demo", AGENT, SESSION);
    await expect(actions.sendPlaygroundAction({ ...ids, session: SESSION, text: "x".repeat(1001) })).rejects.toThrow();
    await expect(actions.setPlaygroundTimeAction({ ...ids, session: SESSION, now: "mañana" })).rejects.toThrow();
    h.fail("sendPlaygroundMessage", 409, "", "turn_in_progress");
    expect(await actions.sendPlaygroundAction({ ...ids, session: SESSION, text: "hola" })).toMatchObject({ ok: false, code: "turn_in_progress" });
  });

  it("las pruebas: ejecutar con su alcance y «No aplica» con su razón", async () => {
    await actions.runTestsAction({ ...ids, scope: "all" });
    expect(h.backend.runAgentTests).toHaveBeenLastCalledWith("demo", AGENT, "all", undefined);
    await actions.runTestsAction({ ...ids, scope: "one", test: TEST });
    expect(h.backend.runAgentTests).toHaveBeenLastCalledWith("demo", AGENT, "one", TEST);
    await expect(actions.runTestsAction({ ...ids, scope: "one" })).rejects.toThrow();
    await actions.setNotApplicableAction({ ...ids, test: TEST, reason: "  no atendemos mascotas " });
    expect(h.backend.editAgentTest).toHaveBeenCalledWith("demo", AGENT, TEST, { not_applicable_reason: "no atendemos mascotas" });
    h.fail("runAgentTests", 409, "", "nothing_to_run");
    expect(await actions.runTestsAction({ ...ids, scope: "affected" })).toMatchObject({ ok: false, code: "nothing_to_run" });
  });

  it("«Guardar»: la nota, «Guardar igualmente» y el motivo viajan solo si se dan", async () => {
    await actions.publishAction({ ...ids });
    expect(h.backend.publishAgent).toHaveBeenLastCalledWith("demo", AGENT, {});
    await actions.publishAction({ ...ids, note: " Lista de espera ", accept_normal_failures: true, override_reason: "Se conecta mañana" });
    expect(h.backend.publishAgent).toHaveBeenLastCalledWith("demo", AGENT, {
      note: "Lista de espera",
      accept_normal_failures: true,
      override_reason: "Se conecta mañana",
    });
    await expect(actions.publishAction({ ...ids, override_reason: "no" })).rejects.toThrow();
    h.fail("publishAgent", 403, "", "override_forbidden");
    expect(await actions.publishAction({ ...ids, override_reason: "porque sí" })).toMatchObject({ ok: false, status: 403, code: "override_forbidden" });
  });

  it("un trabajo de «Guardar» terminado refresca el cliente, y deshacer y restaurar también", async () => {
    h.backend.getConsoleJob.mockResolvedValueOnce({ job_id: JOB, kind: "publish", status: "done" });
    await actions.qualityJobAction({ ref: "demo", job: JOB });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
    vi.clearAllMocks();
    h.backend.getConsoleJob.mockResolvedValueOnce({ job_id: JOB, kind: "tests", status: "done" });
    await actions.qualityJobAction({ ref: "demo", job: JOB });
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalled();
    await actions.undoPublishAction(ids);
    await actions.restoreVersionAction({ ...ids, number: 2 });
    expect(h.backend.restoreAgentVersion).toHaveBeenCalledWith("demo", AGENT, 2);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledTimes(2);
  });

  it("un analista lo lee todo y no prueba, ni escribe, ni guarda", async () => {
    h.setRole("analyst");
    for (const read of [
      actions.playgroundSessionsAction(ids),
      actions.testsAction(ids),
      actions.reviewAction(ids),
      actions.publishPreviewAction(ids),
      actions.historyAction(ids),
      actions.qualityJobAction({ ref: "demo", job: JOB }),
    ]) {
      expect(await read).toMatchObject({ ok: true });
    }
    for (const write of [
      actions.openPlaygroundAction(ids),
      actions.sendPlaygroundAction({ ...ids, session: SESSION, text: "hola" }),
      actions.setPlaygroundTimeAction({ ...ids, session: SESSION, now: "2026-11-01T20:30" }),
      actions.closePlaygroundAction({ ...ids, session: SESSION }),
      actions.runTestsAction({ ...ids, scope: "all" }),
      actions.setNotApplicableAction({ ...ids, test: TEST, reason: "no aplica" }),
      actions.addTestAction({ ...ids, test: { name: "x", first_message: "hola" } }),
      actions.publishAction(ids),
      actions.undoPublishAction(ids),
      actions.restoreVersionAction({ ...ids, number: 2 }),
    ]) {
      expect(await write).toEqual(h.denied());
    }
    expect(h.backend.publishAgent).not.toHaveBeenCalled();
    expect(h.backend.runAgentTests).not.toHaveBeenCalled();
    expect(h.backend.openPlaygroundSession).not.toHaveBeenCalled();
  });
});
