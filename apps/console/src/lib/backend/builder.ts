import type { Call } from "../backend";

import { ifMatch } from "./agent-draft";
import type {
  AgentSpec,
  AnswersResult,
  BuilderAnswer,
  BuilderDraft,
  DraftJob,
  DraftJobAccepted,
  DraftJobBody,
  DraftOptions,
  Proposal,
  ProposalDecision,
} from "./builder-types";

/**
 * Carril del constructor de agentes (spec 047, historia 7; T081 sobre T080):
 * «Nuevo agente» (ejemplos y plantillas), «Generar borrador» como trabajo con
 * progreso por bloques, las respuestas a sus preguntas, el borrador con su
 * AgentSpec (escrito entero con `If-Match`) y las propuestas que se aplican o
 * se rechazan. `contracts/console-api.md` §4. Se esparce en `backendFor`.
 *
 * Los errores llegan como `BackendError` con su código: `name_taken`,
 * `name_length`, `description_length`, `template_required`, `spec_invalid`
 * (con `problems`), `revision_conflict` (412, con `current` y `changes`),
 * `proposal_stale`, `proposal_closed`, `proposal_expired` e `invalid_proposal`.
 */

export * from "./builder-types";

export function builderApi(call: Call) {
  const enc = encodeURIComponent;
  const agents = (ref: string) => `/console/clients/${enc(ref)}/agents`;
  const agent = (ref: string, agentId: string) => `${agents(ref)}/${enc(agentId)}`;
  return {
    getDraftOptions: (ref: string) => call<DraftOptions>(`${agents(ref)}/draft-options`),
    startDraftJob: (ref: string, body: DraftJobBody) =>
      call<DraftJobAccepted>(`${agents(ref)}/draft-jobs`, { method: "POST", body }),
    /** El trabajo, que la pantalla consulta con espera creciente. */
    getDraftJob: (jobId: string) => call<DraftJob>(`/console/jobs/${enc(jobId)}`),
    answerDraftJob: (jobId: string, answers: BuilderAnswer[]) =>
      call<AnswersResult>(`/console/jobs/${enc(jobId)}/answers`, { method: "POST", body: { answers } }),
    getBuilderDraft: (ref: string, agentId: string) => call<BuilderDraft>(`${agent(ref, agentId)}/draft`),
    /** El AgentSpec entero, con la revisión que leyó la pantalla. */
    saveAgentSpec: (ref: string, agentId: string, revision: number, spec: AgentSpec, note?: string) =>
      call<BuilderDraft>(`${agent(ref, agentId)}/draft`, {
        method: "PATCH",
        body: note ? { spec, note } : { spec },
        headers: ifMatch(revision),
      }),
    listProposals: (ref: string, agentId: string) => call<Proposal[]>(`${agent(ref, agentId)}/proposals`),
    applyProposal: (ref: string, agentId: string, proposalId: string) =>
      call<ProposalDecision>(`${agent(ref, agentId)}/proposals/${enc(proposalId)}/apply`, { method: "POST" }),
    rejectProposal: (ref: string, agentId: string, proposalId: string) =>
      call<ProposalDecision>(`${agent(ref, agentId)}/proposals/${enc(proposalId)}/reject`, { method: "POST" }),
  };
}
