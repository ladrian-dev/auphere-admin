import type { WireEvent } from "../state";

/**
 * SSE fixtures carrying the **literal payloads of §2 of
 * `docs/companion/CONTRACT-V1.md`**.
 *
 * These are doubles on purpose. CO-04 builds the write path in parallel,
 * so `plan.proposed`, `intake.missing`, `hitl.requested`, `hitl.resolved`
 * and `verify.result` are emitted by nothing yet. Testing against the
 * frozen contract instead of against an implementation is the only thing
 * that keeps CO-03 and CO-04 in sync while neither can see the other —
 * and the key names below are copied character for character, because the
 * publisher silently drops any key the catalogue does not declare, so a
 * misspelt name would fail quietly in production rather than loudly here.
 */
export const ev = (seq: number, event: string, data: Record<string, unknown>): WireEvent => ({ seq, event, data });

export const runStarted = (seq: number, runId: string, threadId = "thread-1"): WireEvent =>
  ev(seq, "run.started", { run_id: runId, thread_id: threadId, started_at: "2026-08-18T14:00:00Z" });

export const runCompleted = (seq: number, runId: string, status = "completed", unsupported = false): WireEvent =>
  ev(seq, "run.completed", {
    run_id: runId,
    ended_at: "2026-08-18T14:05:00Z",
    status,
    error: status === "error" ? "boom" : null,
    unsupported,
  });

export const phase = (seq: number, name: string): WireEvent =>
  // `label` is hardcoded Spanish from the backend and MUST NOT be painted
  // (§1.4). It is included here precisely so a test can prove we ignore it.
  ev(seq, "phase.changed", { phase: name, label: "ETIQUETA DEL BACKEND" });

export const textDelta = (seq: number, text: string, messageId = "m1"): WireEvent =>
  ev(seq, "text.delta", { message_id: messageId, text });

export const reasoningDelta = (seq: number, text: string, messageId = "r1"): WireEvent =>
  ev(seq, "reasoning.delta", { message_id: messageId, text });

export const toolStarted = (seq: number, id: string, name = "console.get_usage"): WireEvent =>
  ev(seq, "tool.call.started", { tool_call_id: id, name, label: "Consultando el consumo de Boreal", args: { client_ref: "boreal" } });

export const toolCompleted = (seq: number, id: string, ok = true, citationId: string | null = null): WireEvent =>
  ev(seq, "tool.call.completed", {
    tool_call_id: id,
    name: "console.get_usage",
    ok,
    latency_ms: 240,
    error: ok ? null : "upstream 500",
    citation_id: citationId,
  });

export const citation = (seq: number, id: string): WireEvent =>
  ev(seq, "citation", {
    citation_id: id,
    claim: "Consumo del partner (client_ref=boreal)",
    source: "GET /console/usage",
    fetched_at: "2026-08-18T14:01:00Z",
  });

export const costUpdated = (seq: number): WireEvent =>
  ev(seq, "cost.updated", { input_tokens: 12000, output_tokens: 800, model: "claude-opus-5" });

export const contextUpdated = (seq: number, percent = 47): WireEvent =>
  ev(seq, "context.updated", {
    input_tokens: 94000,
    max_context: 200000,
    percent,
    compacted: false,
    model: "claude-opus-5",
  });

export const budgetUpdated = (seq: number, exhausted = false): WireEvent =>
  ev(seq, "budget.updated", {
    used: 310000,
    cap: 500000,
    remaining: 190000,
    percent: 62,
    exhausted,
    period: "2026-08",
    resets_at: "2026-09-01T00:00:00Z",
  });

// ── CO-04 events — literal from §2 ───────────────────────────────────

export const planProposed = (seq: number, planId = "3f2a"): WireEvent =>
  ev(seq, "plan.proposed", {
    plan_id: planId,
    steps: [
      {
        index: 1,
        kind: "prompt",
        tool: "console.propose_prompt",
        title: "Ajustar el prompt de Clínica Boreal",
        client_ref: "boreal",
        reversible: true,
      },
    ],
    risk: "low",
    reversible: true,
    estimated_tokens: 18000,
  });

export const intakeMissing = (seq: number): WireEvent =>
  ev(seq, "intake.missing", {
    slots: [
      {
        key: "forbidden_behaviour",
        label: "Qué NO debe hacer el agente",
        why: "Es el campo que nadie escribe y el que causa los incidentes.",
        examples: ["No dar precios por WhatsApp", "No agendar sin seña"],
        required: true,
      },
    ],
  });

export const hitlRequested = (seq: number, actionId = "9c1e", expiresAt = "2126-08-18T14:33:00Z"): WireEvent =>
  ev(seq, "hitl.requested", {
    action_id: actionId,
    kind: "prompt",
    title: "Publicar la v8 del agente de Clínica Boreal",
    preview: { client_ref: "boreal", summary: "3 líneas cambiadas, 1 herramienta activada" },
    diff: [
      { op: "del", line: 12, before: "Responde siempre en inglés." },
      { op: "add", line: 12, after: "Responde en el idioma del cliente." },
    ],
    impact: [{ key: "channels_affected", value: "2", severity: "info" }],
    expires_at: expiresAt,
  });

export const hitlResolved = (seq: number, actionId = "9c1e", decision = "confirm"): WireEvent =>
  ev(seq, "hitl.resolved", {
    action_id: actionId,
    decision,
    by: "user_a_ab12cd34",
    at: "2026-08-18T14:21:07Z",
    note: decision === "confirm" ? null : "Mejor sin tocar el horario.",
  });

export const verifyResult = (seq: number, actionId = "9c1e", ok = false): WireEvent =>
  ev(seq, "verify.result", {
    action_id: actionId,
    checks: [
      { name: "active_version", expected: "8", actual: "8", ok: true },
      { name: "tools_enabled", expected: "3", actual: ok ? "3" : "2", ok },
    ],
    ok,
  });

export const resumeGap = (seq: number): WireEvent =>
  ev(seq, "resume.gap", { gap_kind: "rotated", since_seq: 5, available_from: 40 });

/**
 * `GET …/threads/{id}/runs` — §5.2 of the contract (v1.1). Ascending by
 * `started_at`, no pagination in Ola 1. Doubled here because CO-04 is
 * building the endpoint in parallel; this shape is the contract's literal
 * `CompanionThreadRunsOut`.
 */
export const threadRuns = (
  threadId: string,
  runs: Array<{ run_id: string; status?: string }>,
): { thread_id: string; runs: Array<{ run_id: string; status: string; started_at: string; ended_at: string | null }> } => ({
  thread_id: threadId,
  runs: runs.map((r, i) => ({
    run_id: r.run_id,
    status: r.status ?? "completed",
    started_at: `2026-08-18T14:0${i}:00Z`,
    ended_at: (r.status ?? "completed") === "running" ? null : `2026-08-18T14:0${i}:30Z`,
  })),
});
