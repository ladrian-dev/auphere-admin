/**
 * La API simulada del constructor de agentes — spec 047, historia 7 (T081), solo
 * para `builder.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §4 lo justo para recorrer
 * «Nuevo agente» con la consola nueva: la sesión, `GET /console/me` con
 * `console_version: "v2"`, la cabecera del cliente, la pestaña Agentes, las
 * opciones de «Nuevo agente», el trabajo `agent_draft` (que suelta los bloques
 * de tres en tres, una consulta tras otra, y termina con dos preguntas), las
 * respuestas, el borrador con su AgentSpec (`ETag`, `If-Match` y las pruebas que
 * quedan sin ejecutar al editar) y las propuestas. Guarda el estado en memoria.
 *
 * `POST /__test/reset` vuelve al principio; `GET /__test/state` enseña lo que
 * llegó (las respuestas con su `scope`). No verifica tokens: no es la puerta,
 * es el otro lado del cable.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8714);
const REF = "barberia-cultor";
const AGENT = "00000000-0000-4000-8000-0000000000b1";
const JOB = "00000000-0000-4000-8000-0000000000c1";
const MODULES = ["panel", "clients", "usage", "audit", "knowledge", "team", "billing", "keys"];
const PRINCIPAL = {
  user_id: "00000000-0000-4000-8000-0000000000e2",
  email: "lucia@ladrian.studio",
  display_name: "Lucía Pérez",
  locale: "es",
  access: "ok",
  membership_id: "00000000-0000-4000-8000-0000000000e3",
  partner_id: "00000000-0000-4000-8000-0000000000e4",
  partner_slug: "ladrian-studio",
  partner_name: "Ladrian Studio",
  partner_status: "active",
  role: "builder",
  permissions: [],
  console_enabled: true,
  kind: "partner",
  client_name: null,
  modules: MODULES,
};
const NOW = "2026-10-27T10:00:00Z";

const OPTIONS = {
  examples: [
    "Atiende las citas de la barbería por WhatsApp: busca hueco, reserva y recuerda la política de cancelación.",
    "Responde las dudas de la clínica sobre horarios, precios y cómo llegar, y pasa al equipo lo que no sepa.",
  ],
  templates: [
    { id: "barbershop_v1", name: "Barbería", group: "Belleza y bienestar", is_default: true },
    { id: "clinic_v1", name: "Clínica", group: "Salud", is_default: false },
    { id: "generic_v1", name: "Genérica", group: "Otro", is_default: false },
  ],
  default_template: "barbershop_v1",
  name_max: 40,
  description_min: 20,
  description_max: 1024,
};

function specFor(name, description) {
  return {
    schema_version: "1",
    mode: "structured",
    identity: { name, description, goal: "Llenar la agenda sin huecos" },
    voice: { tone: "Cercano y breve", languages: ["es"], greeting: "¡Hola! Soy el asistente de la barbería." },
    instructions: { sections: [{ title: "Qué haces", body: description }] },
    procedures: [
      {
        id: "reservar",
        title: "Reservar una cita",
        when: "Cuando alguien pide una cita o pregunta por huecos",
        steps: "Pregunta el servicio y el día. Busca huecos, ofrece dos y confirma con fecha y hora en palabras.",
        tools: [],
      },
    ],
    services: { mode: "all" },
    skills: [
      { key: "reservas", enabled: true, integration: null },
      { key: "reservas", enabled: true, integration: "googlecalendar", fallback: "Mientras no esté conectada, pasa la conversación al equipo." },
    ],
    tools: [],
    connection_requests: [{ integration: "googlecalendar", reason: "Para reservar en el calendario de la barbería" }],
    escalation: { triggers: ["asks_for_human", "complaint", "failed_attempts"], failed_attempts: 2, message: "Te paso con el equipo." },
    rules: ["No ofrezcas descuentos"],
    ai_disclosure: { decided: false },
    model_policy: { kind: "profile", profile: "auto" },
    memory: { scope: "shared" },
  };
}

const QUESTIONS = [
  {
    id: "cancelacion",
    text: "¿Con cuánto tiempo hay que avisar para cancelar una cita?",
    why: "El agente lo dirá al confirmar cada cita.",
    options: ["24 horas antes", "2 horas antes", "Se puede cancelar en cualquier momento"],
    target: "/policies/cancellation",
    scope: "business",
    can_be_agent_only: true,
  },
  {
    id: "trato",
    text: "¿Cómo trata el agente a los clientes?",
    why: "Cambia todas sus respuestas.",
    options: ["tu", "usted"],
    target: "/voice/register",
    scope: "agent",
    can_be_agent_only: false,
  },
];
const BLOCKS = ["identity", "voice", "instructions", "procedures", "services", "skills", "escalation", "rules", "tests", "questions"];

function fresh() {
  return { agent: null, job: null, polls: 0, answers: [], revision: 0, stale: 0, spec: null };
}
let state = fresh();

function summarize(key, spec) {
  if (key === "tests") return { key, count: 8 };
  if (key === "questions") return { key, count: QUESTIONS.length, discarded: 2 };
  if (key === "skills") return { key, value: spec.skills, connect: spec.connection_requests };
  return { key, value: spec[key] };
}

function jobView() {
  const job = state.job;
  const spec = specFor(job.input.name, job.input.description);
  // Una consulta lee la ficha; cada una de las siguientes suelta tres bloques.
  const shown = Math.max(0, (state.polls - 1) * 3);
  const done = shown >= BLOCKS.length;
  if (done && !state.agent) {
    state.agent = { id: AGENT, name: job.input.name };
    state.spec = spec;
    state.revision = 1;
  }
  return {
    job_id: JOB,
    kind: "agent_draft",
    status: done ? "done" : "running",
    agent_id: done ? AGENT : null,
    progress: {
      step: state.polls <= 1 ? "reading" : "writing",
      blocks: BLOCKS.slice(0, Math.min(shown, BLOCKS.length)).map((k) => summarize(k, spec)),
      input: { name: job.input.name, description: job.input.description },
    },
    questions: null,
    result: done
      ? {
          agent_id: AGENT,
          questions: QUESTIONS,
          discarded: { count: 2, reasons: ["Ya estaba en la ficha del negocio.", "Repetía otra pregunta."] },
          connect: spec.connection_requests,
          dropped_tools: [],
          tests: { case: 8 },
        }
      : null,
    error_code: null,
    created_at: NOW,
    finished_at: done ? NOW : null,
  };
}

function draftView() {
  return {
    agent_id: AGENT,
    agent_name: state.agent.name,
    revision: state.revision,
    exists: true,
    number: 1,
    version: 1,
    status: "staged",
    base_number: null,
    active_number: null,
    active_version: null,
    author: PRINCIPAL.email,
    created_at: NOW,
    updated_at: NOW,
    change_note: "Borrador del constructor",
    system_prompt: "…",
    tools: [],
    skills: [],
    settings: {},
    audience: { mode: "unset", numbers: [], locked: false },
    payment_review: { reviewers: [] },
    screens: [],
    allowed: ["edit", "discard"],
    spec: state.spec,
    tests: { total: 8, stale: state.stale, case: 8, sector: 0 },
  };
}

const client = () => ({
  external_client_ref: REF,
  name: "Barbería Cultor",
  status: "active",
  timezone: "Europe/Madrid",
  created_at: NOW,
  updated_at: NOW,
  health: { whatsapp_connected: false, display_phone_number: null, agent_configured: false, agent_version: null },
  sector: null,
  serving_since: null,
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
  res.end(body === undefined ? "" : JSON.stringify(body));
}

async function json(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}

function revisionOf(req) {
  const raw = req.headers["if-match"];
  return raw === undefined ? null : Number(String(raw).replace(/^W\//, "").replaceAll('"', ""));
}

const base = `/console/clients/${REF}`;
const agentBase = `${base}/agents/${AGENT}`;

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const route = `${req.method} ${url.pathname}`;
  process.stderr.write(`[builder-mock] ${route}${url.search}\n`);
  switch (route) {
    case "GET /health":
      return send(res, 200, { status: "ok" });
    case "POST /__test/reset":
      state = fresh();
      return send(res, 200, { ok: true });
    case "GET /__test/state":
      return send(res, 200, { answers: state.answers, revision: state.revision, stale: state.stale, spec: state.spec });
    case "POST /console/auth/session":
      return send(res, 200, { principal: PRINCIPAL });
    case "GET /console/me":
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
    case "GET /console/notifications/unread-count":
      return send(res, 200, { unread: 0 });
    case "GET /console/notifications":
      return send(res, 200, { items: [], next_cursor: null, unread: 0 });
    case "GET /console/search":
      return send(res, 200, { clients: [], agents: [], screens: [], actions: [] });
    case `GET ${base}`:
      return send(res, 200, client());
    case `GET ${base}/agents`:
      return send(
        res,
        200,
        state.agent
          ? [{ id: AGENT, name: state.agent.name, status: "active", is_principal: true, channels: [], active_version: null, draft_version: 1 }]
          : [],
      );
    case `GET ${base}/agents/draft-options`:
      return send(res, 200, OPTIONS);
    case `POST ${base}/agents/draft-jobs`: {
      const body = await json(req);
      if (body.start !== "describe") return send(res, 422, { detail: { code: "template_required" } });
      state.job = { input: { name: body.name, description: body.description } };
      state.polls = 0;
      return send(res, 202, { job_id: JOB, status: "queued", agent_id: null });
    }
    case `GET /console/jobs/${JOB}`:
      if (!state.job) return send(res, 404, { detail: "Unknown job" });
      state.polls += 1;
      return send(res, 200, jobView());
    case `POST /console/jobs/${JOB}/answers`: {
      const body = await json(req);
      state.answers.push(...body.answers);
      for (const a of body.answers) {
        if (a.question_id === "trato" && state.spec) state.spec.voice = { ...state.spec.voice, register: a.value === "usted" ? "usted" : "tu" };
        if (a.question_id === "cancelacion" && a.scope === "agent" && state.spec) state.spec.rules = [...state.spec.rules, `Cancelación: ${a.value}`];
      }
      state.revision += 1;
      state.stale = 8;
      return send(res, 200, {
        applied: body.answers.map((a) => ({ question_id: a.question_id, scope: a.scope ?? "business", target: "/policies/cancellation" })),
        agent_id: AGENT,
        draft_revision: state.revision,
        tests_stale: state.stale,
      });
    }
    case `GET ${agentBase}/draft`:
      if (!state.agent) return send(res, 404, { detail: "Unknown agent" });
      return send(res, 200, draftView(), { etag: `"${state.revision}"` });
    case `PATCH ${agentBase}/draft`: {
      const expected = revisionOf(req);
      if (expected === null) return send(res, 428, { detail: { code: "revision_required" } });
      if (expected !== state.revision) return send(res, 412, { detail: { code: "revision_conflict", current: draftView(), changes: [] } });
      const body = await json(req);
      if (body.spec) {
        const tooLong = (body.spec.rules ?? []).find((r) => r.length > 300);
        if (tooLong) return send(res, 422, { detail: { code: "spec_invalid", problems: [{ pointer: "/rules/0", code: "too_long", message: "La regla pasa de 300 caracteres." }] } });
        state.spec = body.spec;
      }
      state.revision += 1;
      state.stale = 8;
      return send(res, 200, draftView(), { etag: `"${state.revision}"` });
    }
    case `GET ${agentBase}/proposals`:
      return send(res, 200, []);
    default:
      return send(res, 404, { detail: "Not Found" });
  }
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[builder-mock] listening on ${PORT}\n`));
