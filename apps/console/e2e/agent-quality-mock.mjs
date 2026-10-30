/**
 * La API simulada de probar y guardar un agente — spec 047, historias 8 y 9
 * (T089 y T094), solo para `agent-quality.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §4 lo justo para la
 * pantalla del agente con la consola nueva: la sesión (un owner), la cabecera
 * del cliente, el borrador con su AgentSpec, el probador (hora y agenda
 * simuladas, burbujas y «Lo que habría hecho»), las pruebas y sus pasadas, la
 * revisión, «Guardar» con su puerta (la primera vez una prueba crítica no pasa;
 * con el motivo de un owner, se publica), deshacer, el historial y restaurar.
 * Los trabajos tardan una consulta en terminar. Guarda el estado en memoria.
 *
 * `POST /__test/reset` vuelve al principio y `GET /__test/state` enseña lo que
 * llegó. No verifica tokens: no es la puerta, es el otro lado del cable.
 */
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8715);
const REF = "barberia-cultor";
const AGENT = "00000000-0000-4000-8000-0000000000b1";
const MODULES = ["panel", "clients", "usage", "audit", "knowledge", "team", "billing", "keys"];
const PRINCIPAL = {
  user_id: "00000000-0000-4000-8000-0000000000e2",
  email: "luis@ladrian.studio",
  display_name: "Luis Matos",
  locale: "es",
  access: "ok",
  membership_id: "00000000-0000-4000-8000-0000000000e3",
  partner_id: "00000000-0000-4000-8000-0000000000e4",
  partner_slug: "ladrian-studio",
  partner_name: "Ladrian Studio",
  partner_status: "active",
  role: "owner",
  permissions: [],
  console_enabled: true,
  kind: "partner",
  client_name: null,
  modules: MODULES,
};
const NOW = "2026-10-27T10:00:00Z";
const ACTOR = `console:${PRINCIPAL.email}`;

const SPEC = {
  schema_version: "1",
  mode: "structured",
  identity: { name: "Recepción", description: "Atiende las citas de la barbería por WhatsApp y recuerda la política de cancelación." },
  voice: { tone: "Cercano", languages: ["es"], register: "tu" },
  instructions: { sections: [{ title: "Qué haces", body: "Reservas citas y respondes dudas. Abrimos los domingos." }] },
  procedures: [],
  services: { mode: "all" },
  skills: [{ key: "reservas", enabled: true, integration: "googlecalendar", fallback: "Pasa la conversación al equipo." }],
  tools: [],
  connection_requests: [{ integration: "googlecalendar", reason: "Para reservar en su calendario" }],
  escalation: { triggers: ["asks_for_human"], failed_attempts: 2 },
  rules: ["No ofrezcas descuentos"],
  ai_disclosure: { decided: true, mode: "first_message" },
  model_policy: { kind: "profile", profile: "auto" },
  memory: { scope: "shared" },
};

const TESTS = [
  ["t1", "case", "Pregunta el horario", "¿A qué hora abrís mañana?", false],
  ["t2", "case", "Reserva una cita", "Quiero cita mañana a las 11", true],
  ["t3", "case", "Pide un descuento", "¿Me hacéis descuento?", false],
  ["t4", "sector", "Pregunta por aparcamiento", "¿Hay aparcamiento?", false],
  ["t5", "sector", "Pide cita para un perro", "¿Cortáis el pelo a perros?", false],
].map(([id, kind, name, first, critical]) => ({ id: `00000000-0000-4000-8000-00000000f00${id.slice(1)}`, kind, name, first_message: first, critical }));

function fresh() {
  return {
    versions: [{ number: 1, status: "active", created_at: NOW, published_at: NOW, note: "Primera versión", changed: ["identity"], override_reason: null, rate: 100 }],
    draft: { number: 2, revision: 3 },
    ran: false,
    notApplicable: {},
    stale: 5,
    jobs: {},
    sessions: {},
    publishes: [],
    undoUntil: null,
    restored: [],
  };
}
let state = fresh();

const active = () => state.versions.find((v) => v.status === "active") ?? null;

function testView(t) {
  const na = state.notApplicable[t.id];
  let status = "not_run";
  let passes = 0;
  let decided = 0;
  let why = null;
  if (na) status = "not_applicable";
  else if (state.ran) {
    decided = 3;
    if (t.id.endsWith("f002")) {
      status = "failed";
      why = "La cita no existe en la agenda al terminar: falta conectar Google Calendar.";
    } else if (t.id.endsWith("f003")) {
      status = "flaky";
      passes = 2;
      why = "En una de las tres ofreció un descuento.";
    } else {
      status = "passed";
      passes = 3;
    }
  }
  return {
    id: t.id,
    kind: t.kind,
    name: t.name,
    persona: "Cliente",
    first_message: t.first_message,
    plan: "",
    expected_state: {},
    criteria: [],
    critical: t.critical,
    not_applicable_reason: na ?? null,
    sector_test_ref: t.kind === "sector" ? "barber.x" : null,
    stale: !state.ran && !na,
    status,
    passes,
    decided,
    why_failed: why,
  };
}

function suiteView() {
  const tests = TESTS.map(testView);
  const count = (s) => tests.filter((t) => t.status === s).length;
  return {
    summary: {
      passed: count("passed"),
      flaky: count("flaky"),
      failed: count("failed"),
      unknown: count("unknown"),
      not_run: count("not_run"),
      not_applicable: count("not_applicable"),
      total: tests.length,
      stale: tests.filter((t) => t.stale).length,
      critical_failed: tests.filter((t) => t.critical && t.status !== "passed").map((t) => t.id),
      rate: state.ran ? 77.78 : null,
    },
    tests,
    judge_calibrated: false,
    allowed: ["add", "edit", "run"],
  };
}

function draftView() {
  const act = active();
  const tests = suiteView();
  return {
    agent_id: AGENT,
    agent_name: "Recepción",
    revision: state.draft?.revision ?? 10,
    exists: state.draft !== null,
    number: state.draft?.number ?? act?.number ?? null,
    version: state.draft?.number ?? act?.number ?? null,
    status: state.draft ? "staged" : "active",
    base_number: act?.number ?? null,
    active_number: act?.number ?? null,
    active_version: act?.number ?? null,
    author: PRINCIPAL.email,
    created_at: NOW,
    updated_at: NOW,
    change_note: null,
    system_prompt: "…",
    tools: [],
    skills: [],
    settings: {},
    audience: { mode: "everyone", numbers: [], locked: false },
    payment_review: { reviewers: [] },
    screens: [],
    allowed: ["edit", "discard"],
    spec: SPEC,
    tests: { total: tests.summary.total, stale: tests.summary.stale, case: 3, sector: 2 },
  };
}

const GATE_BLOCKED = () => ({
  conditions: [
    { condition: "validator", ok: true },
    { condition: "critical_tests", ok: false },
    { condition: "regression", ok: true },
    { condition: "ai_disclosure", ok: true },
    { condition: "review", ok: true },
  ],
  hard: [],
  overridable: [{ condition: "critical_tests", code: "critical_test_failing", message: "La prueba crítica «Reserva una cita» no pasa 3 de 3." }],
  normal_failures: ["Pide un descuento"],
  rate: 77.78,
  reference_rate: 100,
});

function publish(body) {
  state.publishes.push(body);
  if (!body.override_reason) return { error: "gate_blocked", gate: GATE_BLOCKED() };
  const number = state.draft.number;
  for (const v of state.versions) if (v.status === "active") v.status = "archived";
  state.undoUntil = new Date(Date.now() + 10 * 60 * 1000).toISOString();
  state.versions.push({
    number,
    status: "active",
    created_at: NOW,
    published_at: new Date().toISOString(),
    note: body.note ?? null,
    changed: ["instructions", "rules"],
    override_reason: body.override_reason,
    rate: 77.78,
  });
  state.draft = null;
  return { result: { agent_id: AGENT, number, undo_until: state.undoUntil, gate: GATE_BLOCKED() } };
}

function jobView(id) {
  const job = state.jobs[id];
  job.polls += 1;
  const base = { job_id: id, kind: job.kind, agent_id: AGENT, questions: null, created_at: NOW };
  if (job.polls < 2) return { ...base, status: "running", progress: { step: job.kind === "publish" ? "testing" : null, blocks: [] }, result: null, error_code: null, finished_at: null };
  if (!job.finished) {
    job.finished = true;
    if (job.kind === "tests") state.ran = true;
    if (job.kind === "publish") job.outcome = publish(job.body);
  }
  if (job.kind === "publish" && job.outcome.error) {
    return { ...base, status: "failed", progress: { step: "blocked", blocks: [{ key: "gate", ...job.outcome.gate }] }, result: null, error_code: job.outcome.error, finished_at: NOW };
  }
  return { ...base, status: "done", progress: { step: null, blocks: [] }, result: job.kind === "publish" ? job.outcome.result : { tests: TESTS.length }, error_code: null, finished_at: NOW };
}

function historyView() {
  const sorted = [...state.versions].sort((a, b) => a.number - b.number);
  const rows = sorted.map((v) => ({
    number: v.number,
    status: v.status,
    author: ACTOR,
    created_at: v.created_at,
    published_at: v.published_at,
    published_by: ACTOR,
    note: v.note,
    changed: v.changed,
    model_policy: { kind: "profile", profile: "auto" },
    tests: v.rate != null ? { rate: v.rate, conditions: [] } : null,
    override_reason: v.override_reason,
  }));
  if (state.draft) {
    rows.push({ number: state.draft.number, status: "staged", author: ACTOR, created_at: NOW, published_at: null, published_by: null, note: null, changed: ["instructions"], model_policy: null, tests: null, override_reason: null });
  }
  return rows.reverse();
}

const REVIEW = () => ({
  version_number: state.draft?.number ?? active()?.number ?? 1,
  findings: [
    {
      code: "skill_without_integration",
      severity: "block",
      message: "La habilidad Reservas necesita Google Calendar y no está conectada.",
      fix: { kind: "link", target: "integrations", integration: "googlecalendar" },
    },
    {
      code: "contradicts_hours",
      severity: "warn",
      message: "Contradice la ficha: horario del domingo.",
      pointer: "/instructions/sections/0/body",
      fix: { kind: "edit", pointer: "/instructions/sections/0/body" },
    },
  ],
  checks: [
    ["skills_integrations", 1],
    ["services", 0],
    ["hours", 0],
    ["contradictions", 1],
    ["promises", 0],
    ["tools_exist", 0],
    ["escalation_recipients", 0],
    ["ai_disclosure", 0],
  ].map(([check, n]) => ({ check, ok: n === 0, findings: n })),
  blocking: 1,
});

const previewView = () => ({
  action: state.draft ? "save_changes" : "save",
  has_draft: state.draft !== null,
  has_channels: true,
  diff: state.draft
    ? [
        { part: "rules", label: "Reglas", change: "add" },
        { part: "instructions", label: "Instrucciones", change: "replace" },
      ]
    : [],
  gate: null,
  can_override: true,
});

function sessionView(s) {
  return {
    session_id: s.id,
    version_number: s.version_number,
    is_draft: s.is_draft,
    timezone: "Europe/Madrid",
    now: s.now,
    agenda: s.agenda,
    services: [{ name: "Corte", bookable: true, duration_min: 30, price: "15 €" }],
    transcript: s.transcript,
    created_by: ACTOR,
    allowed: ["send", "set_time", "close"],
  };
}

const client = () => ({
  external_client_ref: REF,
  name: "Barbería Cultor",
  status: "active",
  timezone: "Europe/Madrid",
  created_at: NOW,
  updated_at: NOW,
  health: { whatsapp_connected: true, display_phone_number: "+34 600 000 000", agent_configured: true, agent_version: 1 },
  sector: null,
  serving_since: NOW,
  setup: null,
  quota: null,
  niche: "Barbería de barrio con dos sedes",
  info: null,
  website: null,
  country: "ES",
  price_currency: "EUR",
  wallet_currency: "USD",
  eu_only: true,
  lifecycle: "active",
  revision: 3,
  allowed: ["edit", "new_agent", "archive"],
});

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", ...headers });
  res.end(body === undefined || status === 204 ? "" : JSON.stringify(body));
}

async function json(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}

const base = `/console/clients/${REF}`;
const agentBase = `${base}/agents/${AGENT}`;
const pg = `${agentBase}/playground/sessions`;

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  const route = `${req.method} ${path}`;
  process.stderr.write(`[quality-mock] ${route}\n`);

  if (route === "GET /health") return send(res, 200, { status: "ok" });
  if (route === "POST /__test/reset") {
    state = fresh();
    return send(res, 200, { ok: true });
  }
  if (route === "GET /__test/state") return send(res, 200, { publishes: state.publishes, notApplicable: state.notApplicable, restored: state.restored, versions: state.versions });
  if (route === "POST /console/auth/session") return send(res, 200, { principal: PRINCIPAL });
  if (route === "GET /console/me")
    return send(res, 200, {
      user_id: PRINCIPAL.user_id,
      partner_id: PRINCIPAL.partner_id,
      partner_slug: PRINCIPAL.partner_slug,
      partner_name: PRINCIPAL.partner_name,
      role: PRINCIPAL.role,
      modules: MODULES,
      companion_enabled: false,
      console_version: "v2",
    });
  if (route === "GET /console/notifications/unread-count") return send(res, 200, { unread: 0 });
  if (route === "GET /console/notifications") return send(res, 200, { items: [], next_cursor: null, unread: 0 });
  if (route === "GET /console/search") return send(res, 200, { clients: [], agents: [], screens: [], actions: [] });
  if (route === `GET ${base}`) return send(res, 200, client());
  if (route === `GET ${base}/agents`)
    return send(res, 200, [{ id: AGENT, name: "Recepción", status: "active", is_principal: true, channels: [{ id: "c1", display: "+34 600 000 000" }], active_version: active()?.number ?? null, draft_version: state.draft?.number ?? null }]);
  if (route === `GET ${agentBase}/draft`) return send(res, 200, draftView(), { etag: `"${draftView().revision}"` });
  if (route === `GET ${agentBase}/proposals`) return send(res, 200, []);

  // ── el probador ──
  if (route === `GET ${pg}`) return send(res, 200, Object.values(state.sessions).map(sessionView));
  if (route === `POST ${pg}`) {
    const body = await json(req);
    const id = randomUUID();
    const draft = body.version === "draft" || body.version === undefined;
    state.sessions[id] = {
      id,
      version_number: draft ? (state.draft?.number ?? active()?.number ?? 1) : body.version,
      is_draft: draft && state.draft !== null,
      now: "2026-10-27T11:20:00+01:00",
      agenda: [{ id: "b1", service: "Corte", when: "28/10/2026 a las 10:00", status: "confirmed" }],
      transcript: [],
    };
    return send(res, 201, sessionView(state.sessions[id]));
  }
  const pgm = path.match(new RegExp(`^${pg}/([0-9a-f-]+)(/messages)?$`));
  if (pgm) {
    const s = state.sessions[pgm[1]];
    if (!s) return send(res, 404, { detail: { code: "unknown_session" } });
    if (req.method === "POST" && pgm[2]) {
      const body = await json(req);
      const turn = {
        role: "agent",
        bubbles: ["¡Claro! Mañana a las 11 tengo hueco para un corte.", "Te la dejo reservada. Si no puedes venir, avísanos con 24 horas."],
        several_bubbles: true,
        actions: [{ tool: "reservas.create", phrase: "crear cita de Corte el 28/10/2026 a las 11:00" }],
      };
      s.transcript.push({ role: "customer", bubbles: [body.text], several_bubbles: false, actions: [] }, turn);
      s.agenda.push({ id: randomUUID(), service: "Corte", when: "28/10/2026 a las 11:00", status: "confirmed" });
      return send(res, 200, { turn, now: s.now, agenda: s.agenda });
    }
    if (req.method === "PATCH") {
      const body = await json(req);
      s.now = `${String(body.now).slice(0, 19)}+01:00`;
      return send(res, 200, sessionView(s));
    }
    if (req.method === "DELETE") {
      delete state.sessions[pgm[1]];
      return send(res, 204);
    }
    if (req.method === "GET") return send(res, 200, sessionView(s));
  }

  // ── las pruebas ──
  if (route === `GET ${agentBase}/tests`) return send(res, 200, suiteView());
  const tm = path.match(new RegExp(`^${agentBase}/tests/([0-9a-f-]+)$`));
  if (tm && req.method === "PATCH") {
    const body = await json(req);
    if (body.not_applicable_reason !== undefined) {
      if (body.not_applicable_reason) state.notApplicable[tm[1]] = body.not_applicable_reason;
      else delete state.notApplicable[tm[1]];
    }
    return send(res, 200, suiteView());
  }
  if (route === `POST ${agentBase}/test-runs`) {
    const id = randomUUID();
    state.jobs[id] = { kind: "tests", polls: 0 };
    return send(res, 202, { job_id: id, run_id: randomUUID(), tests: TESTS.length - Object.keys(state.notApplicable).length });
  }
  const jm = path.match(/^\/console\/jobs\/([0-9a-f-]+)$/);
  if (jm && req.method === "GET") {
    if (!state.jobs[jm[1]]) return send(res, 404, { detail: "Unknown job" });
    return send(res, 200, jobView(jm[1]));
  }

  // ── la revisión, «Guardar», deshacer, historial y restaurar ──
  if (route === `GET ${agentBase}/review`) return send(res, 200, REVIEW());
  if (route === `GET ${agentBase}/publish-preview`) return send(res, 200, previewView());
  if (route === `POST ${agentBase}/publish`) {
    if (!state.draft) return send(res, 409, { detail: { code: "no_draft" } });
    const body = await json(req);
    const id = randomUUID();
    state.jobs[id] = { kind: "publish", polls: 0, body };
    return send(res, 202, { job_id: id });
  }
  if (route === `POST ${agentBase}/publish/undo`) {
    if (!state.undoUntil || Date.parse(state.undoUntil) < Date.now()) return send(res, 409, { detail: { code: "undo_window_closed" } });
    const current = active();
    const previous = [...state.versions].filter((v) => v.status === "archived").sort((a, b) => b.number - a.number)[0];
    current.status = "archived";
    previous.status = "active";
    state.undoUntil = null;
    return send(res, 200, { number: previous.number });
  }
  if (route === `GET ${agentBase}/history`) return send(res, 200, historyView());
  const rm = path.match(new RegExp(`^${agentBase}/versions/(\\d+)/restore$`));
  if (rm && req.method === "POST") {
    const n = Number(rm[1]);
    const number = Math.max(...state.versions.map((v) => v.number), state.draft?.number ?? 0) + 1;
    state.draft = { number, revision: 20 };
    state.restored.push(n);
    return send(res, 200, { draft_number: number, restored_from: n, revision: 20 });
  }
  return send(res, 404, { detail: "Not Found" });
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[quality-mock] listening on ${PORT}\n`));
