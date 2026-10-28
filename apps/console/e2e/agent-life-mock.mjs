/**
 * La API simulada de la vida de los agentes, el copiloto y «Completar con el
 * constructor» — spec 047, historias 18 a 20 (T124, T099 y T098), solo para
 * `agent-life.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §3 y §4 lo justo para:
 * la pestaña Agentes con el estado visible de cada uno; la cabecera de un
 * agente con su ⋯ (pausar pide confirmar con 3 conversaciones en curso,
 * archivar pide el destino de cada número y, al agente por defecto, otro
 * antes; restaurar lo devuelve en pausa); el copiloto («¿Por qué dijo esto?»
 * con sus citas, y «Arreglar» un dato con su alcance); y Negocio con lo que
 * propone el constructor. Guarda el estado en memoria.
 *
 * `POST /__test/reset` vuelve al principio y `GET /__test/state` enseña lo que
 * llegó. No verifica tokens: no es la puerta, es el otro lado del cable.
 */
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8716);
const REF = "barberia-cultor";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const COBROS = "00000000-0000-4000-8000-0000000000a2";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";
const CH1 = "00000000-0000-4000-8000-0000000000c1";
const CH2 = "00000000-0000-4000-8000-0000000000c2";
const TEST = "00000000-0000-4000-8000-0000000000f2";
const POLICY = "00000000-0000-4000-8000-0000000000d1";
const FAQ = "00000000-0000-4000-8000-0000000000d2";
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

function fresh() {
  return {
    agents: {
      [RECEPCION]: { id: RECEPCION, name: "Recepción", lifecycle: "published", pause_reason: null, is_default: true, channels: [], visible: "serving" },
      [COBROS]: {
        id: COBROS,
        name: "Cobros",
        lifecycle: "published",
        pause_reason: null,
        is_default: false,
        channels: [
          { id: CH1, display: "+34 600 000 001" },
          { id: CH2, display: "+34 600 000 002" },
        ],
        visible: "serving",
      },
      [VENTAS]: { id: VENTAS, name: "Ventas", lifecycle: "published", pause_reason: null, is_default: false, channels: [], visible: "ready_no_channel" },
    },
    archives: [],
    fixes: [],
    decisions: [],
    copilot: [],
    suggestions: [],
  };
}
let state = fresh();

const TONE = { archived: "muted", paused: "warn", draft: "muted", serving: "positive", testing: "info", ready_no_channel: "info" };

function visible(a) {
  if (a.lifecycle === "archived") return { code: "archived", tone: "muted", reason: null };
  if (a.lifecycle === "paused") return { code: "paused", tone: "warn", reason: a.pause_reason ?? "manual" };
  return { code: a.visible, tone: TONE[a.visible], reason: null };
}

function card(a) {
  const v = visible(a);
  return {
    id: a.id,
    name: a.name,
    status: a.lifecycle === "archived" ? "archived" : "active",
    is_principal: a.is_default,
    channels: a.channels,
    active_version: 2,
    draft_version: 3,
    lifecycle: a.lifecycle,
    pause_reason: a.pause_reason,
    is_default: a.is_default,
    visible_state: v,
    opens: v.code === "draft" ? "builder" : v.code === "ready_no_channel" ? "channels" : "overview",
  };
}

function header(a) {
  let allowed;
  if (a.lifecycle === "archived") allowed = ["restore"];
  else {
    allowed = ["rename", "archive", a.lifecycle === "paused" ? "resume" : "pause"];
    if (!a.is_default) allowed.push("make_default");
  }
  return {
    id: a.id,
    name: a.name,
    lifecycle: a.lifecycle,
    pause_reason: a.pause_reason,
    visible_state: visible(a),
    is_default: a.is_default,
    open_conversations: a.lifecycle === "paused" ? 0 : 3,
    paused_by_kind: a.lifecycle === "paused" ? "partner_member" : null,
    paused_origin: a.lifecycle === "paused" ? "console" : null,
    allowed,
  };
}

const SPEC = (name) => ({
  schema_version: "1",
  mode: "structured",
  identity: { name, description: "Atiende las citas de la barbería por WhatsApp y recuerda la política de cancelación." },
  voice: { tone: "Cercano", languages: ["es"], register: "tu" },
  instructions: { sections: [{ title: "Qué haces", body: "Reservas citas y respondes dudas. Abrimos los domingos." }] },
  procedures: [],
  services: { mode: "all" },
  skills: [],
  tools: [],
  escalation: { triggers: ["asks_for_human"], failed_attempts: 2 },
  rules: ["No ofrezcas descuentos"],
  ai_disclosure: { decided: true, mode: "first_message" },
  model_policy: { kind: "profile", profile: "auto" },
  memory: { scope: "shared" },
});

function draft(a) {
  return {
    agent_id: a.id,
    agent_name: a.name,
    revision: 4,
    exists: true,
    number: 3,
    version: 3,
    status: "staged",
    base_number: 2,
    active_number: 2,
    active_version: 2,
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
    spec: SPEC(a.name),
    tests: { total: 2, stale: 0, case: 2, sector: 0 },
  };
}

const SUITE = () => ({
  summary: { passed: 1, flaky: 0, failed: 1, unknown: 0, not_run: 0, not_applicable: 0, total: 2, stale: 0, critical_failed: [TEST], rate: 50 },
  tests: [
    { id: "00000000-0000-4000-8000-0000000000f1", kind: "case", name: "Pregunta el horario", persona: "", first_message: "¿Abrís el domingo?", plan: "", expected_state: {}, criteria: [], critical: false, not_applicable_reason: null, sector_test_ref: null, stale: false, status: "passed", passes: 3, decided: 3, why_failed: null },
    { id: TEST, kind: "case", name: "Dice el horario del domingo", persona: "", first_message: "¿Abrís el domingo?", plan: "", expected_state: {}, criteria: [], critical: true, not_applicable_reason: null, sector_test_ref: null, stale: false, status: "failed", passes: 0, decided: 3, why_failed: "Dijo que abrimos el domingo y la ficha dice cerrado." },
  ],
  judge_calibrated: true,
  allowed: ["add", "edit", "run"],
});

const WHY = () => ({
  text: "Dijo que abrís el domingo porque la instrucción «Qué haces» lo dice, y la ficha dice que el domingo está cerrado.",
  citations: [
    { kind: "business", label: "Horario", excerpt: "Domingo: cerrado", link: { target: "business/hours" } },
    { kind: "instruction", label: "Qué haces", excerpt: "Abrimos los domingos.", link: { target: "agent", pointer: "/instructions/sections/0/body" } },
  ],
  proposals: [],
  fix: { test_id: TEST, scopes: ["business", "agent"] },
});

const meta = { revision: 1, state: "complete", allowed: ["edit"] };
const BASICS = { ...meta, name: "Barbería Cultor", niche: "Barbería de barrio", info: null, website: null, country: "ES", timezone: "Europe/Madrid", price_currency: "EUR", eu_only: true };
const LOCATIONS = { ...meta, items: [], created_id: null };
const HOURS = { ...meta, location_id: null, inherits: false, layout: "blocks", days: { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] }, label: null };
const SPECIAL = { ...meta, items: [], created_id: null };
const SERVICES = { ...meta, items: [], currency: "EUR", exponent: 2, created_id: null, agents: [] };

function suggestionsView() {
  return state.suggestions.map((s) => ({ ...s, current_value: null, source: "builder", source_url: null, translated_from: null, created_at: NOW }));
}

const client = () => ({
  external_client_ref: REF,
  name: "Barbería Cultor",
  status: "active",
  timezone: "Europe/Madrid",
  created_at: NOW,
  updated_at: NOW,
  health: { whatsapp_connected: true, display_phone_number: null, agent_configured: true, agent_version: 2 },
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
const live = () => Object.values(state.agents).filter((a) => a.lifecycle !== "archived");
const jobs = {};

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  const route = `${req.method} ${path}`;
  process.stderr.write(`[life-mock] ${route}\n`);

  if (route === "GET /health") return send(res, 200, { status: "ok" });
  if (route === "POST /__test/reset") {
    state = fresh();
    return send(res, 200, { ok: true });
  }
  if (route === "GET /__test/state")
    return send(res, 200, { archives: state.archives, fixes: state.fixes, decisions: state.decisions, copilot: state.copilot, agents: state.agents });
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
  if (route === `GET ${base}/agents`) return send(res, 200, live().map(card));

  if (route === `PUT ${base}/default-agent`) {
    const body = await json(req);
    for (const a of Object.values(state.agents)) a.is_default = a.id === body.agent_id;
    return send(res, 200, header(state.agents[body.agent_id]));
  }

  // ── Negocio ──
  if (route === `GET ${base}/business`) return send(res, 200, { spec: {}, valid: true, problems: [], sections: [], provenance: {}, suggestions: suggestionsView(), allowed: ["edit", "decide"] });
  if (route === `GET ${base}/business/basics`) return send(res, 200, BASICS);
  if (route === `GET ${base}/business/locations`) return send(res, 200, LOCATIONS);
  if (route === `GET ${base}/business/hours`) return send(res, 200, HOURS);
  if (route === `GET ${base}/business/special-dates`) return send(res, 200, SPECIAL);
  if (route === `GET ${base}/business/services`) return send(res, 200, SERVICES);
  if (route === `POST ${base}/business/builder`) {
    const id = randomUUID();
    jobs[id] = { polls: 0 };
    return send(res, 202, { job_id: id });
  }
  const sm = path.match(new RegExp(`^${base}/business/suggestions/([0-9a-f-]+)/decide$`));
  if (sm && req.method === "POST") {
    const body = await json(req);
    state.decisions.push({ id: sm[1], ...body });
    state.suggestions = state.suggestions.filter((s) => s.id !== sm[1]);
    return send(res, 200, { suggestion_id: sm[1], decision: body.decision, section: "policies", revision: 2 });
  }
  const jm = path.match(/^\/console\/jobs\/([0-9a-f-]+)$/);
  if (jm && req.method === "GET") {
    const job = jobs[jm[1]];
    if (!job) return send(res, 404, { detail: "Unknown job" });
    job.polls += 1;
    if (job.polls < 2) return send(res, 200, { job_id: jm[1], kind: "client_builder", status: "running", agent_id: null, progress: { step: "reading", blocks: [] }, questions: null, result: null, error_code: null, created_at: NOW, finished_at: null });
    if (!state.suggestions.length && !job.done) {
      state.suggestions = [
        { id: POLICY, pointer: "/policies/cancellation", section: "policies", proposed_value: "Se puede cancelar sin coste hasta 24 horas antes." },
        { id: FAQ, pointer: "/faqs/-", section: "faqs", proposed_value: { q: "¿Aceptáis tarjeta?", a: "Sí, todas las tarjetas.", suggested: true } },
      ];
    }
    job.done = true;
    return send(res, 200, {
      job_id: jm[1],
      kind: "client_builder",
      status: "done",
      agent_id: null,
      progress: { step: null, blocks: [] },
      questions: null,
      result: {
        sections: { policies: [POLICY], faqs: [FAQ] },
        agents: [{ name: "Recordatorios", description: "Recuerda las citas del día siguiente y ofrece cambiarlas si el cliente no puede venir." }],
        discarded: ["«¿Dónde estáis?»: ya está entre las preguntas frecuentes."],
      },
      error_code: null,
      created_at: NOW,
      finished_at: NOW,
    });
  }
  if (route === `GET ${base}/agents/draft-options`)
    return send(res, 200, { examples: [], templates: [], default_template: null, name_max: 40, description_min: 20, description_max: 1024 });

  // ── un agente ──
  const am = path.match(new RegExp(`^${base}/agents/([0-9a-f-]{36})(/.*)?$`));
  if (am) {
    const a = state.agents[am[1]];
    if (!a) return send(res, 404, { detail: "Unknown agent" });
    const sub = am[2] ?? "";
    if (req.method === "GET" && sub === "") return send(res, 200, header(a));
    if (req.method === "PATCH" && sub === "") {
      const body = await json(req);
      if (body.name) a.name = body.name;
      return send(res, 200, card(a));
    }
    if (req.method === "POST" && sub === "/pause") {
      const body = await json(req);
      if (!body.confirm) return send(res, 409, { detail: { code: "confirm_required", open_conversations: 3 } });
      a.lifecycle = "paused";
      a.pause_reason = "manual";
      return send(res, 200, header(a));
    }
    if (req.method === "POST" && sub === "/resume") {
      a.lifecycle = "published";
      a.pause_reason = null;
      return send(res, 200, header(a));
    }
    if (req.method === "POST" && sub === "/archive") {
      const body = await json(req);
      if (a.is_default) return send(res, 409, { detail: { code: "default_agent_required" } });
      if (a.channels.some((c) => !body.channels?.find((d) => d.channel_id === c.id))) return send(res, 422, { detail: { code: "channel_destination_required" } });
      state.archives.push({ agent: a.id, channels: body.channels });
      for (const d of body.channels) if (d.to !== "pause" && state.agents[d.to]) state.agents[d.to].channels.push(a.channels.find((c) => c.id === d.channel_id));
      a.channels = [];
      a.lifecycle = "archived";
      return send(res, 200, header(a));
    }
    if (req.method === "POST" && sub === "/restore") {
      a.lifecycle = "paused";
      a.pause_reason = "manual";
      return send(res, 200, header(a));
    }
    if (a.lifecycle === "archived") return send(res, 404, { detail: "Unknown agent" });
    if (req.method === "GET" && sub === "/draft") return send(res, 200, draft(a), { etag: '"4"' });
    if (req.method === "GET" && sub === "/proposals") return send(res, 200, []);
    if (req.method === "GET" && sub === "/tests") return send(res, 200, SUITE());
    if (req.method === "GET" && sub === "/review") return send(res, 200, { version_number: 3, findings: [], checks: [{ check: "hours", ok: true, findings: 0 }], blocking: 0 });
    if (req.method === "GET" && sub === "/publish-preview") return send(res, 200, { action: "save_changes", has_draft: true, has_channels: true, diff: [], gate: null, can_override: true });
    if (req.method === "GET" && sub === "/history") return send(res, 200, []);
    if (req.method === "GET" && sub === "/playground/sessions") return send(res, 200, []);
    if (req.method === "POST" && sub === "/copilot") {
      const body = await json(req);
      state.copilot.push(body);
      return send(res, 200, WHY());
    }
    if (req.method === "POST" && sub === "/copilot/fix") {
      const body = await json(req);
      state.fixes.push(body);
      return send(res, 200, body.scope === "business" ? { scope: "business", faq_id: randomUUID() } : { scope: "agent", pointer: "/services/faqs" });
    }
  }
  return send(res, 404, { detail: "Not Found" });
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[life-mock] listening on ${PORT}\n`));
