/**
 * La API simulada de la pestaña Conocimiento de un agente, su sección Canales,
 * la página de cada canal y el enlace del dueño — spec 047, historias 10, 11 y
 * 22 (T111, T115 y T134), solo para `agent-channels.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §4 y §5 lo justo para:
 * el conocimiento propio del agente (quitar con 10 minutos para restaurar,
 * «Enseñar» con su alcance), los números del agente con su estado visible, el
 * ⋯ de cada uno (pasar, pausar, desconectar con un paso pendiente en Meta), el
 * enlace del dueño (uno pendiente por agente, «WhatsApp login» fuera de la
 * beta) y la página del canal con `If-Match`, «A todos» bloqueado por la bolsa,
 * deshacer e historial. Guarda el estado en memoria.
 *
 * `POST /__test/reset` vuelve al principio, `POST /__test/bump` simula que otra
 * persona guardó la configuración y `GET /__test/state` enseña lo que llegó. No
 * verifica tokens: no es la puerta, es el otro lado del cable.
 */
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8717);
const REF = "barberia-cultor";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";
const CH1 = "00000000-0000-4000-8000-0000000000c1";
const CH2 = "00000000-0000-4000-8000-0000000000c2";
const DOC1 = "00000000-0000-4000-8000-0000000000d1";
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
const TONE = { pending_link: "info", disconnected: "muted", problem: "danger", paused: "warn", unconfigured: "muted", team_only: "info", everyone: "positive" };

function doc(over) {
  return {
    id: randomUUID(),
    kind: "file",
    title: "",
    source_url: null,
    mime: "application/pdf",
    size_bytes: 20480,
    status: "indexed",
    error_code: null,
    chunk_count: 3,
    created_by: PRINCIPAL.email,
    created_at: NOW,
    updated_at: NOW,
    indexed_at: NOW,
    agent_id: RECEPCION,
    removed_at: null,
    restore_until: null,
    ...over,
  };
}

function fresh() {
  return {
    docs: [
      doc({ id: DOC1, title: "Tarifas mayoristas" }),
      doc({ title: "Carta del negocio", agent_id: null }),
      doc({ title: "Política de cancelación", agent_id: null, kind: "url", source_url: "https://cultor.example/cancelar", mime: "text/html" }),
    ],
    taught: [],
    channels: {
      [CH1]: {
        id: CH1,
        identifier: "+34 611 20 48 93",
        status: "active",
        problem_reason: null,
        agent: RECEPCION,
        revision: 3,
        config: {
          audience: { mode: "team_only", test_numbers: ["+34611204893"], exceptions: [] },
          escalation: { recipients: [{ name: "Marta", via: "whatsapp", phone_e164: "+34600000009", email: null, client_user_id: null }], summary: true },
          wait_message: null,
        },
        history: [],
        lastUndo: null,
      },
      [CH2]: {
        id: CH2,
        identifier: "+34 611 20 48 94",
        status: "degraded",
        problem_reason: "coexistence_inactive",
        agent: RECEPCION,
        revision: 1,
        config: { audience: { mode: "everyone", test_numbers: [], exceptions: [] }, escalation: { recipients: [], summary: true }, wait_message: null },
        history: [],
        lastUndo: null,
      },
    },
    link: null,
    links: [],
    saves: [],
    moves: [],
    disconnects: [],
  };
}
let state = fresh();

const agents = {
  [RECEPCION]: { id: RECEPCION, name: "Recepción", is_default: true },
  [VENTAS]: { id: VENTAS, name: "Ventas", is_default: false },
};

function card(a) {
  const channels = Object.values(state.channels)
    .filter((c) => c.agent === a.id && c.status !== "disconnected")
    .map((c) => ({ id: c.id, display: c.identifier }));
  return {
    id: a.id,
    name: a.name,
    status: "active",
    is_principal: a.is_default,
    channels,
    active_version: 2,
    draft_version: null,
    lifecycle: "published",
    pause_reason: null,
    is_default: a.is_default,
    visible_state: channels.length ? { code: "testing", tone: "info", reason: null } : { code: "ready_no_channel", tone: "info", reason: null },
    opens: channels.length ? "overview" : "channels",
  };
}

function header(a) {
  return {
    id: a.id,
    name: a.name,
    lifecycle: "published",
    pause_reason: null,
    visible_state: card(a).visible_state,
    is_default: a.is_default,
    open_conversations: 0,
    paused_by_kind: null,
    paused_origin: null,
    allowed: ["rename", "pause", "archive"],
  };
}

const SPEC = (name) => ({
  schema_version: "1",
  mode: "structured",
  identity: { name, description: "Atiende las citas de la barbería por WhatsApp y recuerda la política de cancelación." },
  voice: { tone: "Cercano", languages: ["es"], register: "tu" },
  instructions: { sections: [{ title: "Qué haces", body: "Reservas citas y respondes dudas." }] },
  procedures: [],
  services: { mode: "all" },
  skills: [],
  tools: [],
  escalation: { triggers: ["asks_for_human", { custom: "Si pide factura" }], failed_attempts: 2 },
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
    exists: false,
    number: null,
    version: null,
    status: null,
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
    allowed: ["edit"],
    spec: SPEC(a.name),
    tests: { total: 1, stale: 0, case: 1, sector: 0 },
  };
}

const SUITE = () => ({
  summary: { passed: 1, flaky: 0, failed: 0, unknown: 0, not_run: 0, not_applicable: 0, total: 1, stale: 0, critical_failed: [], rate: 100 },
  tests: [
    { id: "00000000-0000-4000-8000-0000000000f1", kind: "case", name: "Pregunta el horario", persona: "", first_message: "¿Abrís el domingo?", plan: "", expected_state: {}, criteria: [], critical: false, not_applicable_reason: null, sector_test_ref: null, stale: false, status: "passed", passes: 3, decided: 3, why_failed: null },
  ],
  judge_calibrated: true,
  allowed: ["add", "edit", "run"],
});

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
  niche: "Barbería de barrio",
  info: null,
  website: null,
  country: "ES",
  price_currency: "EUR",
  wallet_currency: "USD",
  eu_only: true,
  lifecycle: "active",
  revision: 3,
  allowed: ["edit", "assign_balance", "new_agent", "archive"],
});

function visible(c) {
  let code;
  if (c.status === "disconnected") code = "disconnected";
  else if (c.status === "degraded") return { code: "problem", tone: "danger", reason: c.problem_reason };
  else if (c.status === "paused") code = "paused";
  else if (c.config.audience.mode === "unset") code = "unconfigured";
  else code = c.config.audience.mode;
  return { code, tone: TONE[code], reason: null };
}

function page(c) {
  const others = Object.values(agents).filter((a) => a.id !== c.agent);
  const disconnected = c.status === "disconnected";
  const allowed = disconnected ? [] : ["configure", ...(others.length ? ["move"] : []), c.status === "paused" ? "resume" : "pause", "disconnect"];
  const checks = [
    { code: "tests_up_to_date", ok: true, level: "warn", fix: null },
    { code: "escalation_recipient", ok: c.config.escalation.recipients.length > 0, level: "warn", fix: c.config.escalation.recipients.length ? null : "add_recipient" },
  ];
  if (c.config.audience.mode !== "team_only") checks.push({ code: "bag_empty", ok: false, level: "block", fix: "assign_balance" });
  const lastUndo = c.lastUndo && Date.parse(c.lastUndo) > Date.now() ? c.lastUndo : null;
  return {
    id: c.id,
    type: "whatsapp",
    identifier: c.identifier,
    status: c.status,
    problem_reason: c.problem_reason,
    visible_state: visible(c),
    agent: { id: c.agent, name: agents[c.agent].name },
    config: { ...c.config, notify_from: c.id === CH1 ? "channel" : "auphere" },
    admin_only_template: false,
    triggers: ["asks_for_human", { custom: "Si pide factura" }],
    checks,
    revision: c.revision,
    undo_until: lastUndo,
    move_targets: others.map((a) => ({ id: a.id, name: a.name })),
    allowed,
  };
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", ...headers });
  res.end(body === undefined || status === 204 ? "" : JSON.stringify(body));
}

async function raw(req) {
  let out = "";
  for await (const chunk of req) out += chunk;
  return out;
}
async function json(req) {
  const text = await raw(req);
  return text ? JSON.parse(text) : {};
}

const base = `/console/clients/${REF}`;
const E164 = /^\+[1-9]\d{6,14}$/;

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  const route = `${req.method} ${path}`;
  process.stderr.write(`[channels-mock] ${route}\n`);

  if (route === "GET /health") return send(res, 200, { status: "ok" });
  if (route === "POST /__test/reset") {
    state = fresh();
    return send(res, 200, { ok: true });
  }
  if (route === "POST /__test/bump") {
    const c = state.channels[CH1];
    c.revision += 1;
    c.config = { ...c.config, wait_message: "Ahora mismo te atiende una persona." };
    return send(res, 200, { revision: c.revision });
  }
  if (route === "GET /__test/state")
    return send(res, 200, { docs: state.docs, taught: state.taught, links: state.links, saves: state.saves, moves: state.moves, disconnects: state.disconnects, channels: state.channels });
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
  if (route === `GET ${base}/agents`) return send(res, 200, Object.values(agents).map(card));

  // ── Negocio › Documentos y webs (la capa del negocio) ──
  if (route === `GET ${base}/knowledge`) {
    const items = state.docs.filter((d) => d.agent_id === null && !d.removed_at);
    return send(res, 200, { items, total: items.length, indexed_chars: 4000, prompt_char_cap: 20000 });
  }
  const bk = path.match(new RegExp(`^${base}/knowledge/([0-9a-f-]{36})(/restore)?$`));
  if (bk) {
    const d = state.docs.find((x) => x.id === bk[1] && x.agent_id === null);
    if (!d) return send(res, 404, { detail: "document not found" });
    if (req.method === "DELETE" && !bk[2]) {
      d.removed_at = new Date().toISOString();
      d.restore_until = new Date(Date.now() + 600_000).toISOString();
      return send(res, 204);
    }
    if (req.method === "POST" && bk[2]) {
      d.removed_at = null;
      d.restore_until = null;
      return send(res, 200, d);
    }
  }

  // ── un canal ──
  const cm = path.match(new RegExp(`^${base}/channels/([0-9a-f-]{36})(/.*)?$`));
  if (cm) {
    const c = state.channels[cm[1]];
    if (!c) return send(res, 404, { detail: "Unknown channel" });
    const sub = cm[2] ?? "";
    if (req.method === "GET" && sub === "") return send(res, 200, page(c), { etag: `"${c.revision}"` });
    if (req.method === "GET" && sub === "/history") return send(res, 200, c.history);
    if (req.method === "PUT" && sub === "/config") {
      const match = (req.headers["if-match"] ?? "").replaceAll('"', "");
      if (!match) return send(res, 428, { detail: { code: "revision_required" } });
      const body = await json(req);
      if (Number(match) !== c.revision) return send(res, 412, { detail: { code: "revision_conflict", current: c.revision, changes: ["wait_message"] } });
      for (const n of [...body.audience.test_numbers, ...body.audience.exceptions]) {
        if (!E164.test(n)) return send(res, 422, { detail: { code: "invalid_phone", value: n } });
      }
      if (body.audience.mode === "team_only" && !body.audience.test_numbers.length) return send(res, 422, { detail: { code: "channel_test_numbers_required" } });
      if (body.escalation.recipients.length > 10) return send(res, 422, { detail: { code: "too_many_recipients", limit: 10 } });
      if (body.audience.mode === "everyone") return send(res, 409, { detail: { code: "bag_empty", fix: "assign_balance", blocking: ["bag_empty"] } });
      const before = c.config;
      c.config = body;
      c.revision += 1;
      c.lastUndo = new Date(Date.now() + 600_000).toISOString();
      c.history.unshift({ id: randomUUID(), at: new Date().toISOString(), actor: PRINCIPAL.email, origin: "console", before, after: body, undo_until: c.lastUndo, undone_at: null });
      state.saves.push({ revision: Number(match), config: body });
      return send(res, 200, page(c), { etag: `"${c.revision}"` });
    }
    if (req.method === "POST" && sub === "/config/undo") {
      const last = c.history.find((h) => h.origin === "console" && !h.undone_at);
      if (!last || !c.lastUndo || Date.parse(c.lastUndo) < Date.now()) return send(res, 409, { detail: { code: "undo_window_closed" } });
      const current = c.config;
      c.config = last.before;
      c.revision += 1;
      last.undone_at = new Date().toISOString();
      c.lastUndo = null;
      c.history.unshift({ id: randomUUID(), at: new Date().toISOString(), actor: PRINCIPAL.email, origin: "undo", before: current, after: c.config, undo_until: null, undone_at: null });
      return send(res, 200, page(c));
    }
    if (req.method === "POST" && sub === "/move") {
      const body = await json(req);
      if (!agents[body.to_agent_id]) return send(res, 422, { detail: { code: "unknown_target_agent" } });
      c.agent = body.to_agent_id;
      state.moves.push({ channel: c.id, to: body.to_agent_id });
      return send(res, 200, page(c));
    }
    if (req.method === "POST" && sub === "/pause") {
      c.before = c.status;
      c.status = "paused";
      return send(res, 200, page(c));
    }
    if (req.method === "POST" && sub === "/resume") {
      c.status = c.before ?? "active";
      return send(res, 200, page(c));
    }
    if (req.method === "POST" && sub === "/disconnect") {
      const first = c.status !== "disconnected";
      c.status = "disconnected";
      state.disconnects.push(c.id);
      return send(res, 200, {
        id: c.id,
        type: "whatsapp",
        provider: "whatsapp_meta",
        provider_identifier: c.identifier,
        status: "disconnected",
        role: "agent",
        last_health_check_at: null,
        created_at: NOW,
        quality_rating: null,
        messaging_tier: null,
        verified_name: null,
        mode: "coexistence",
        agent_enabled: true,
        logo_url: null,
        // La primera vez Meta no confirma la baja; «Reintentar» la termina.
        unlink_pending: first ? ["deregister"] : [],
        catalog: null,
        catalog_state: "none",
        catalog_error: null,
      });
    }
  }

  // ── un agente ──
  const am = path.match(new RegExp(`^${base}/agents/([0-9a-f-]{36})(/.*)?$`));
  if (am) {
    const a = agents[am[1]];
    if (!a) return send(res, 404, { detail: "Unknown agent" });
    const sub = am[2] ?? "";
    if (req.method === "GET" && sub === "") return send(res, 200, header(a));
    if (req.method === "GET" && sub === "/draft") return send(res, 200, draft(a), { etag: '"4"' });
    if (req.method === "GET" && sub === "/proposals") return send(res, 200, []);
    if (req.method === "GET" && sub === "/tests") return send(res, 200, SUITE());
    if (req.method === "GET" && sub === "/review") return send(res, 200, { version_number: 2, findings: [], checks: [{ check: "hours", ok: true, findings: 0 }], blocking: 0 });
    if (req.method === "GET" && sub === "/publish-preview") return send(res, 200, { action: "save_changes", has_draft: false, has_channels: true, diff: [], gate: null, can_override: true });
    if (req.method === "GET" && sub === "/history") return send(res, 200, []);
    if (req.method === "GET" && sub === "/playground/sessions") return send(res, 200, []);

    // Conocimiento (historia 22)
    if (req.method === "GET" && sub === "/knowledge") {
      const items = state.docs.filter((d) => d.agent_id === a.id);
      const business = state.docs.filter((d) => d.agent_id === null && !d.removed_at && d.status === "indexed").length;
      return send(res, 200, { items, business_sources: business });
    }
    if (req.method === "POST" && sub === "/knowledge/url") {
      const body = await json(req);
      const d = doc({ kind: "url", title: body.title || body.url, source_url: body.url, mime: "text/html", size_bytes: 0, agent_id: a.id });
      state.docs.unshift(d);
      return send(res, 201, d);
    }
    if (req.method === "POST" && sub === "/knowledge") {
      await raw(req);
      const d = doc({ title: "Archivo subido", agent_id: a.id });
      state.docs.unshift(d);
      return send(res, 201, d);
    }
    const km = sub.match(/^\/knowledge\/([0-9a-f-]{36})(\/restore)?$/);
    if (km) {
      const d = state.docs.find((x) => x.id === km[1] && x.agent_id === a.id);
      if (!d) return send(res, 404, { detail: "document not found" });
      if (req.method === "DELETE" && !km[2]) {
        d.removed_at = new Date().toISOString();
        d.restore_until = new Date(Date.now() + 600_000).toISOString();
        return send(res, 204);
      }
      if (req.method === "POST" && km[2]) {
        if (!d.restore_until || Date.parse(d.restore_until) < Date.now()) return send(res, 409, { detail: { code: "undo_window_closed" } });
        d.removed_at = null;
        d.restore_until = null;
        return send(res, 200, d);
      }
    }
    if (req.method === "POST" && sub === "/teach") {
      const body = await json(req);
      if (!["business", "agent"].includes(body.scope)) return send(res, 422, { detail: "scope required" });
      const d = doc({ kind: "note", title: body.text.split("\n")[0].slice(0, 80), mime: "text/plain", size_bytes: body.text.length, agent_id: body.scope === "agent" ? a.id : null });
      state.docs.unshift(d);
      state.taught.push(body);
      return send(res, 201, d);
    }

    // Canales (historias 10 y 11)
    if (req.method === "GET" && sub === "/channels") {
      const list = Object.values(state.channels)
        .filter((c) => c.agent === a.id && c.status !== "disconnected")
        .map((c) => ({ id: c.id, type: "whatsapp", identifier: c.identifier, visible_state: visible(c) }));
      const pending = state.link && state.link.agent === a.id ? { id: state.link.id, mode: state.link.mode, expires_at: state.link.expires_at } : null;
      return send(res, 200, { channels: list, pending_link: pending });
    }
    if (req.method === "POST" && sub === "/channels/owner-links") {
      const body = await json(req);
      if (body.mode === "whatsapp_login") return send(res, 409, { detail: { code: "whatsapp_login_unavailable" } });
      if (state.link && state.link.agent === a.id && !body.replace) return send(res, 409, { detail: { code: "link_pending_exists", link_id: state.link.id } });
      const id = randomUUID();
      state.link = { id, agent: a.id, mode: body.mode, expires_at: "2026-11-03T10:00:00Z" };
      state.links.push(body);
      return send(res, 201, { id, url: `http://localhost/connect/whatsapp/tok_${id.replaceAll("-", "")}`, mode: body.mode, expires_at: state.link.expires_at });
    }
    const lm = sub.match(/^\/channels\/owner-links\/([0-9a-f-]{36})$/);
    if (lm && req.method === "DELETE") {
      if (!state.link || state.link.id !== lm[1]) return send(res, 404, { detail: "Unknown link" });
      state.link = null;
      return send(res, 204);
    }
  }
  return send(res, 404, { detail: "Not Found" });
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[channels-mock] listening on ${PORT}\n`));
