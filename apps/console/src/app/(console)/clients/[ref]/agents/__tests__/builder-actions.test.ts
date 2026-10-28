import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { answerDraftJobAction, builderDraftAction, decideProposalAction, draftJobAction, saveAgentSpecAction, startDraftJobAction } =
  await import("../builder-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const JOB = "22222222-2222-4222-8222-222222222222";
const PROPOSAL = "44444444-4444-4444-8444-444444444444";
const DESCRIPTION = "Atiende las citas de la barbería por WhatsApp.";
const SPEC = {
  schema_version: "1",
  mode: "structured",
  identity: { name: "Recepción", description: DESCRIPTION },
  ai_disclosure: { decided: false },
};

/**
 * Spec 047 (historia 7, T081) — las acciones del constructor: `agents:write`
 * para generar, responder, guardar y decidir; `agents:read` para consultar el
 * trabajo. Los límites se comprueban aquí antes de llamar, y los códigos de la
 * API vuelven tal cual para que la pantalla los diga con palabras.
 */
describe("las acciones del constructor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("«Generar borrador» manda el nombre recortado y la descripción", async () => {
    h.backend.startDraftJob.mockResolvedValueOnce({ job_id: JOB, status: "queued", agent_id: null });
    expect(await startDraftJobAction({ ref: "demo", name: " Recepción ", description: DESCRIPTION, start: "describe" })).toMatchObject({ ok: true });
    expect(h.backend.startDraftJob).toHaveBeenLastCalledWith("demo", { name: "Recepción", start: "describe", description: DESCRIPTION });
    // El agente aún no existe: no hay nada que refrescar.
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalled();
  });

  it("los límites se comprueban antes de llamar", async () => {
    await expect(startDraftJobAction({ ref: "demo", name: "x".repeat(41), description: DESCRIPTION, start: "describe" })).rejects.toThrow();
    await expect(startDraftJobAction({ ref: "demo", name: "Recepción", description: "corta", start: "describe" })).rejects.toThrow();
    await expect(startDraftJobAction({ ref: "demo", name: "Recepción", start: "template" })).rejects.toThrow();
    expect(h.backend.startDraftJob).not.toHaveBeenCalled();
  });

  it("desde una plantilla no manda una descripción que no vale, y refresca el cliente", async () => {
    h.backend.startDraftJob.mockResolvedValueOnce({ job_id: JOB, status: "done", agent_id: AGENT });
    await startDraftJobAction({ ref: "demo", name: "Ventas", description: "corta", start: "template", template_id: "barber_v1" });
    expect(h.backend.startDraftJob).toHaveBeenLastCalledWith("demo", { name: "Ventas", start: "template", template_id: "barber_v1" });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
  });

  it("las respuestas viajan con su `scope`", async () => {
    h.backend.answerDraftJob.mockResolvedValueOnce({ applied: [{ question_id: "q1", scope: "business", target: "/policies/cancellation" }], agent_id: AGENT, draft_revision: 2, tests_stale: 8 });
    const answers = [{ question_id: "q1", value: "24 horas antes", scope: "business" as const }];
    expect(await answerDraftJobAction({ ref: "demo", job: JOB, answers })).toMatchObject({ ok: true });
    expect(h.backend.answerDraftJob).toHaveBeenCalledWith(JOB, answers);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/business");
  });

  it("guardar el AgentSpec lleva la revisión, y un `spec_invalid` vuelve con sus problemas", async () => {
    expect(await saveAgentSpecAction({ ref: "demo", agent: AGENT, revision: 4, spec: SPEC })).toMatchObject({ ok: true });
    expect(h.backend.saveAgentSpec).toHaveBeenLastCalledWith("demo", AGENT, 4, SPEC, undefined);
    const problems = [{ pointer: "/rules/0", code: "too_long", message: "Larga" }];
    h.fail("saveAgentSpec", 422, "", "spec_invalid", { problems });
    expect(await saveAgentSpecAction({ ref: "demo", agent: AGENT, revision: 4, spec: SPEC })).toMatchObject({
      ok: false,
      status: 422,
      code: "spec_invalid",
      info: { problems },
    });
  });

  it("aplicar y rechazar van cada uno a su ruta", async () => {
    await decideProposalAction({ ref: "demo", agent: AGENT, proposal: PROPOSAL, decision: "apply" });
    expect(h.backend.applyProposal).toHaveBeenCalledWith("demo", AGENT, PROPOSAL);
    await decideProposalAction({ ref: "demo", agent: AGENT, proposal: PROPOSAL, decision: "reject" });
    expect(h.backend.rejectProposal).toHaveBeenCalledWith("demo", AGENT, PROPOSAL);
    h.fail("applyProposal", 409, "", "proposal_stale");
    expect(await decideProposalAction({ ref: "demo", agent: AGENT, proposal: PROPOSAL, decision: "apply" })).toMatchObject({ ok: false, code: "proposal_stale" });
  });

  it("un analista consulta el trabajo y el borrador, pero no genera, no guarda y no decide", async () => {
    h.setRole("analyst");
    h.backend.getDraftJob.mockResolvedValueOnce({ job_id: JOB, status: "running" });
    expect(await draftJobAction({ ref: "demo", job: JOB })).toMatchObject({ ok: true });
    h.backend.getBuilderDraft.mockResolvedValueOnce({ agent_id: AGENT });
    h.backend.listProposals.mockResolvedValueOnce([]);
    expect(await builderDraftAction({ ref: "demo", agent: AGENT })).toMatchObject({ ok: true, data: { proposals: [] } });
    expect(await startDraftJobAction({ ref: "demo", name: "Recepción", description: DESCRIPTION, start: "describe" })).toEqual(h.denied());
    expect(await answerDraftJobAction({ ref: "demo", job: JOB, answers: [{ question_id: "q1", value: "sí" }] })).toEqual(h.denied());
    expect(await saveAgentSpecAction({ ref: "demo", agent: AGENT, revision: 4, spec: SPEC })).toEqual(h.denied());
    expect(await decideProposalAction({ ref: "demo", agent: AGENT, proposal: PROPOSAL, decision: "apply" })).toEqual(h.denied());
    expect(h.backend.startDraftJob).not.toHaveBeenCalled();
    expect(h.backend.answerDraftJob).not.toHaveBeenCalled();
    expect(h.backend.saveAgentSpec).not.toHaveBeenCalled();
    expect(h.backend.applyProposal).not.toHaveBeenCalled();
  });
});
