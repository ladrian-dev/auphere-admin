import type { Call } from "../backend";

import type {
  AgentReview,
  HistoryEntry,
  PlaygroundReply,
  PlaygroundSession,
  PublishBody,
  PublishPreview,
  QualityJob,
  RestoreResult,
  TestBody,
  TestPatch,
  TestRunAccepted,
  TestRunScope,
  TestSuite,
} from "./agent-quality-types";

/**
 * Carril de lo que pasa entre el borrador y los clientes de verdad (spec 047,
 * historias 8 y 9; T089 y T094): el playground con hora y agenda de mentira,
 * las pruebas y sus pasadas, la revisión, «Guardar» con su puerta, deshacer,
 * el historial y restaurar. `contracts/console-api.md` §4. Se esparce en
 * `backendFor`.
 *
 * Los errores llegan como `BackendError` con su código: `turn_in_progress`
 * (409), `turn_timeout` (504), `unknown_session`, `not_applicable_only_sector`,
 * `reason_required`, `nothing_to_run`, `no_version`, `override_forbidden`
 * (403), `no_draft`, `undo_window_closed` y `unknown_version`.
 */

export * from "./agent-quality-types";

export function agentQualityApi(call: Call) {
  const enc = encodeURIComponent;
  const agent = (ref: string, agentId: string) => `/console/clients/${enc(ref)}/agents/${enc(agentId)}`;
  const pg = (ref: string, agentId: string) => `${agent(ref, agentId)}/playground/sessions`;
  return {
    // ── el playground ──
    openPlaygroundSession: (ref: string, agentId: string, body: { version?: "draft" | number; now?: string }) =>
      call<PlaygroundSession>(pg(ref, agentId), { method: "POST", body }),
    listPlaygroundSessions: (ref: string, agentId: string) => call<PlaygroundSession[]>(pg(ref, agentId)),
    getPlaygroundSession: (ref: string, agentId: string, sessionId: string) =>
      call<PlaygroundSession>(`${pg(ref, agentId)}/${enc(sessionId)}`),
    sendPlaygroundMessage: (ref: string, agentId: string, sessionId: string, text: string) =>
      call<PlaygroundReply>(`${pg(ref, agentId)}/${enc(sessionId)}/messages`, { method: "POST", body: { text } }),
    setPlaygroundTime: (ref: string, agentId: string, sessionId: string, now: string) =>
      call<PlaygroundSession>(`${pg(ref, agentId)}/${enc(sessionId)}`, { method: "PATCH", body: { now } }),
    closePlaygroundSession: (ref: string, agentId: string, sessionId: string) =>
      call<null>(`${pg(ref, agentId)}/${enc(sessionId)}`, { method: "DELETE" }),

    // ── las pruebas ──
    getAgentTests: (ref: string, agentId: string) => call<TestSuite>(`${agent(ref, agentId)}/tests`),
    addAgentTest: (ref: string, agentId: string, body: TestBody) =>
      call<TestSuite>(`${agent(ref, agentId)}/tests`, { method: "POST", body }),
    editAgentTest: (ref: string, agentId: string, testId: string, body: TestPatch) =>
      call<TestSuite>(`${agent(ref, agentId)}/tests/${enc(testId)}`, { method: "PATCH", body }),
    runAgentTests: (ref: string, agentId: string, scope: TestRunScope, testId?: string) =>
      call<TestRunAccepted>(`${agent(ref, agentId)}/test-runs`, {
        method: "POST",
        body: testId ? { scope, test_id: testId } : { scope },
      }),
    /** Un trabajo (`tests`, `publish`), consultado con espera creciente. */
    getConsoleJob: (jobId: string) => call<QualityJob>(`/console/jobs/${enc(jobId)}`),

    // ── la revisión ──
    getAgentReview: (ref: string, agentId: string) => call<AgentReview>(`${agent(ref, agentId)}/review`),

    // ── «Guardar», deshacer, historial y restaurar ──
    getPublishPreview: (ref: string, agentId: string) => call<PublishPreview>(`${agent(ref, agentId)}/publish-preview`),
    publishAgent: (ref: string, agentId: string, body: PublishBody) =>
      call<{ job_id: string }>(`${agent(ref, agentId)}/publish`, { method: "POST", body }),
    undoPublish: (ref: string, agentId: string) => call<{ number: number }>(`${agent(ref, agentId)}/publish/undo`, { method: "POST" }),
    getAgentHistory: (ref: string, agentId: string) => call<HistoryEntry[]>(`${agent(ref, agentId)}/history`),
    restoreAgentVersion: (ref: string, agentId: string, number: number) =>
      call<RestoreResult>(`${agent(ref, agentId)}/versions/${number}/restore`, { method: "POST" }),
  };
}
