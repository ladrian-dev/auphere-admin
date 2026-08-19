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

/**
 * `intake.missing` — literal from §3.1 of CONTRACT-V2. `work_kind` is new
 * in v2 and titles the chip group.
 */
export const intakeMissing = (seq: number, workKind: string | null = "create_client"): WireEvent =>
  ev(seq, "intake.missing", {
    ...(workKind === null ? {} : { work_kind: workKind }),
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

/**
 * A full `create_client` intake, with the highlighted slot deliberately
 * LAST on the wire so a test can prove the card promotes it to the top.
 * Keys are the closed catalogue of §3.3.
 */
export const intakeCreateClient = (seq: number): WireEvent =>
  ev(seq, "intake.missing", {
    work_kind: "create_client",
    slots: [
      { key: "name", label: "Nombre", why: "", examples: [], required: true },
      { key: "vertical", label: "Vertical", why: "", examples: ["aesthetic-clinic"], required: true },
      { key: "timezone", label: "Zona horaria", why: "", examples: ["America/Caracas"], required: true },
      { key: "language", label: "Idioma", why: "", examples: [], required: true },
      {
        key: "forbidden_behaviour",
        label: "Qué NO debe hacer el agente",
        why: "Es el campo que nadie escribe y el que causa los incidentes.",
        examples: ["No dar precios por WhatsApp"],
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

/**
 * `verify.result` — §7 of CONTRACT-V2 adds `trial`.
 *
 * `trial` defaults to `null` because that is the wire value for "this
 * action admits no trial", and it must stay distinguishable from
 * `{"ran": false}` ("it does and none was run"). Collapsing the two would
 * silently delete the warning publishing depends on.
 */
export const verifyResult = (
  seq: number,
  actionId = "9c1e",
  ok = false,
  trial: Record<string, unknown> | null = null,
): WireEvent =>
  ev(seq, "verify.result", {
    action_id: actionId,
    checks: [
      { name: "active_version", expected: "8", actual: "8", ok: true },
      { name: "tools_enabled", expected: "3", actual: ok ? "3" : "2", ok },
    ],
    ok,
    trial,
  });

/** `trial` with `ran: true` — literal from §7 of CONTRACT-V2. Note there
 *  is NO field carrying the draft agent's reply, and there must not be. */
export const trialRan = (ok = true): Record<string, unknown> => ({
  ran: true,
  thread_id: "4d2b",
  ok,
  tokens: 4210,
  turns: [
    {
      index: 1,
      probe: "¿Cuánto cuesta el bótox?",
      ok,
      latency_ms: 1840,
      checks: [{ name: "no_price_quoted", expected: "true", actual: ok ? "true" : "false", ok }],
    },
  ],
});

/** "It admits a trial and none was run" — NOT the same as `trial: null`. */
export const trialNotRun = (): Record<string, unknown> => ({ ran: false });

/**
 * `support.ticket` — §4.5 of CONTRACT-V2. Emitted in `execute`, after
 * `console.apply` returns 2xx and before `verify.result`.
 */
export const supportTicket = (
  seq: number,
  actionId = "9c1e",
  ref = "AU-142",
  category = "help",
  sla = "business_hours",
): WireEvent =>
  ev(seq, "support.ticket", {
    action_id: actionId,
    ticket_ref: ref,
    category,
    topic: "connector.shopify",
    sla,
  });

/** The proposal that precedes it — `hitl.requested` of a support kind,
 *  with the `preview` of §4.2 literal. */
export const hitlSupportRequested = (
  seq: number,
  actionId = "9c1e",
  kind = "support_help",
  bridge = false,
): WireEvent =>
  ev(seq, "hitl.requested", {
    action_id: actionId,
    kind,
    title: "Abrir una incidencia por el conector de Shopify",
    preview: {
      category: kind === "support_capability" ? "capability" : "help",
      topic: "connector.shopify",
      client_ref: "boreal",
      need: "Sincronizar pedidos de Shopify para que el agente responda por el envío",
      checked: [
        "Catálogo de conectores (14 disponibles, sin Shopify)",
        "Herramientas activas del cliente",
        "Plan del partner",
      ],
      alternative: bridge ? "Clave de API y un webhook, sin conector nativo" : null,
      bridge,
    },
    diff: null,
    impact: [],
    expires_at: "2126-08-18T14:33:00Z",
  });

/**
 * `hitl.requested` of `kind: publish` with the three new preview keys of
 * §7.1. `warning_key ∈ not_tried | trial_failed | null` — an ADVISORY, so
 * a test must be able to prove the buttons stay enabled.
 */
export const hitlPublishRequested = (
  seq: number,
  actionId = "9c1e",
  warningKey: string | null = "not_tried",
): WireEvent =>
  ev(seq, "hitl.requested", {
    action_id: actionId,
    kind: "publish",
    title: "Publicar la v8 del agente de Clínica Boreal",
    preview: {
      client_ref: "boreal",
      from_version: 7,
      to_version: 8,
      evals_run: false,
      evals_warning: "No se ejecutó ninguna evaluación.",
      trial_ran: warningKey !== "not_tried",
      trial_ok: warningKey === "trial_failed" ? false : warningKey === null ? true : null,
      warning_key: warningKey,
    },
    diff: null,
    impact: [],
    expires_at: "2126-08-18T14:33:00Z",
  });

/** `budget.paused` — §6.4 of CONTRACT-V2. The CUT, as opposed to
 *  `budget.updated`, which is the gauge. */
export const budgetPaused = (seq: number): WireEvent =>
  ev(seq, "budget.paused", {
    used: 2000000,
    cap: 2000000,
    period: "2026-08",
    resets_at: "2026-09-01T00:00:00Z",
    scope: "partner",
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
