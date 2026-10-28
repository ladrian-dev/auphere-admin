/**
 * La API simulada de las pantallas que cierra la spec 047 (T162, T165, T168,
 * T174, T176 y T178), solo para `fabrica.config.ts`.
 *
 * Contesta a las dos clases de persona según la cookie de sesión que manda la
 * consola a `POST /console/auth/session`:
 * - `e2e-lite`: Marta, persona del cliente «Barbería Cultor», con Panel,
 *   Bandeja, Agentes, Negocio y Consumo (`contracts/lite-app-api.md`): sus
 *   agentes con pausar y reanudar, su ficha con `If-Match`, historial y
 *   deshacer, y «Corregir esta respuesta» con la paráfrasis y los datos
 *   personales que bloquean el envío;
 * - cualquier otra: Luis, owner del partner con la consola nueva
 *   (`contracts/console-api.md` §4): la pantalla del agente con Recepción,
 *   Rendimiento (solo metadatos) y Mejoras, y Equipo.
 *
 * `POST /__test/reset` vuelve al principio; `POST /__test/mode` con
 * `{agents|business|performance|conversations|improvements|stream: ok|empty|fail|slow}`
 * pone cada parte en uno de sus estados; `GET /__test/state` enseña lo que llegó
 * (pausas, claves de idempotencia, correcciones, la Recepción guardada). No
 * verifica tokens: no es la puerta, es el otro lado del cable.
 */
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8719);
const REF = "barberia-cultor";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";
const CITAS = "00000000-0000-4000-8000-0000000000a4";
const CH1 = "00000000-0000-4000-8000-0000000000c1";
const CH2 = "00000000-0000-4000-8000-0000000000c2";
const CONV = "00000000-0000-4000-8000-000000000c01";
const MSG_IN = "00000000-0000-4000-8000-000000000a01";
const MSG_AGENT = "00000000-0000-4000-8000-000000000a02";
const SVC = "00000000-0000-4000-8000-0000000000b1";
const SUG = "00000000-0000-4000-8000-0000000000d1";
const COR = "00000000-0000-4000-8000-0000000000d2";
const NOW = "2026-10-27T10:00:00Z";
const PARTNER_MODULES = ["panel", "clients", "usage", "audit", "knowledge", "team", "billing", "keys"];
const base = {
  user_id: "00000000-0000-4000-8000-0000000000e2",
  locale: "es",
  access: "ok",
  membership_id: "00000000-0000-4000-8000-0000000000e3",
  partner_id: "00000000-0000-4000-8000-0000000000e4",
  partner_slug: "ladrian-studio",
  partner_name: "Ladrian Studio",
  partner_status: "active",
  permissions: [],
  console_enabled: true,
};
const PARTNER = { ...base, email: "luis@ladrian.studio", display_name: "Luis Matos", role: "owner", kind: "partner", client_name: null, modules: PARTNER_MODULES };
const CLIENT = {
  ...base,
  user_id: "00000000-0000-4000-8000-0000000000e5",
  email: "marta@cultor.example",
  display_name: "Marta",
  role: "client",
  kind: "client",
  client_name: "Barbería Cultor",
  modules: ["panel", "inbox", "agents", "business", "usage"],
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const empty = () => ({ mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] });
const shift = (open, close) => ({ open, close, overnight: false });

// ── el estado ───────────────────────────────────────────────────────────────

function liteAgent(id, name, over = {}) {
  return {
    id,
    name,
    is_default: false,
    visible_state: { code: "serving", tone: "positive", reason: null },
    pause_reason: null,
    paused_by_kind: null,
    paused_origin: null,
    open_conversations: 0,
    channels: [],
    allowed: ["pause"],
    ...over,
  };
}

function fresh() {
  return {
    mode: { agents: "ok", business: "ok", performance: "ok", conversations: "ok", improvements: "ok", stream: "ok" },
    agents: [
      liteAgent(RECEPCION, "Recepción", {
        is_default: true,
        open_conversations: 2,
        channels: [{ id: CH1, type: "whatsapp", identifier: "+34 611 20 48 93", visible_state: { code: "everyone", tone: "positive", reason: null }, allowed: ["pause"] }],
      }),
      liteAgent(VENTAS, "Ventas mayoristas", {
        visible_state: { code: "paused", tone: "warn", reason: "no_balance" },
        pause_reason: "no_balance",
        paused_by_kind: "system",
        allowed: [],
        channels: [{ id: CH2, type: "whatsapp", identifier: "+34 611 20 48 94", visible_state: { code: "team_only", tone: "info", reason: null }, allowed: ["pause"] }],
      }),
    ],
    pauses: [],
    business: {
      hours: {
        revision: 4,
        state: "complete",
        allowed: ["edit"],
        location_id: null,
        inherits: false,
        layout: "daily",
        days: { ...empty(), mon: [shift("10:00", "20:00")], tue: [shift("10:00", "20:00")], sat: [shift("10:00", "14:00")] },
        label: "Lunes y martes de 10:00 a 20:00 · sábado de 10:00 a 14:00",
      },
      special_dates: { revision: 1, state: "optional", allowed: ["edit"], items: [], created_id: null },
      services: {
        revision: 7,
        state: "complete",
        allowed: ["edit"],
        currency: "EUR",
        exponent: 2,
        agents: [],
        created_id: null,
        items: [
          {
            id: SVC,
            name: "Corte clásico",
            description: "Con lavado y peinado",
            bookable: true,
            duration_min: 30,
            price: { kind: "amount", amount_minor: 1500 },
            currency: "EUR",
            staff: "all",
            agents: { mode: "all_agents", agent_ids: [] },
            used_by: [{ id: RECEPCION, name: "Recepción" }],
            archived: false,
          },
        ],
      },
      locations: { revision: 2, state: "optional", allowed: ["edit"], items: [], created_id: null },
    },
    history: [],
    keys: [],
    corrections: {},
    draftRevision: 4,
    reception: null,
    specSaves: [],
    improvements: [
      {
        id: SUG,
        kind: "suggestion",
        week: "2026-10-19",
        topic: "12 clientes preguntaron por el aparcamiento y el agente no supo",
        summary: "Añadir dónde se puede aparcar cerca del local.",
        lesson: null,
        origin: null,
        conversations_count: 12,
        contacts_count: 9,
        proposal_id: "00000000-0000-4000-8000-0000000000f1",
        diff: { ops: [{ op: "add", path: "/rules/-", value: "El aparcamiento más cercano está en la calle de atrás." }] },
        test: { name: "Pregunta por el aparcamiento", persona: "Cliente nuevo", first_message: "¿Dónde aparco?", plan: "Pregunta y espera la calle.", criteria: [], critical: false },
        created_at: "2026-10-26T10:00:00Z",
      },
      {
        id: COR,
        kind: "correction",
        week: null,
        topic: "¿Dais citas el día de fiesta?",
        summary: "No des citas los festivos",
        lesson: "No des citas los festivos",
        origin: "app",
        conversations_count: 1,
        contacts_count: 1,
        proposal_id: "00000000-0000-4000-8000-0000000000f2",
        diff: { ops: [{ op: "add", path: "/rules/-", value: "No des citas los festivos." }] },
        test: { name: "Pide cita un festivo", persona: "", first_message: "¿Tenéis hueco el 8 de diciembre?", plan: "", criteria: [], critical: true },
        created_at: "2026-10-27T09:00:00Z",
      },
    ],
    decisions: [],
  };
}
let state = fresh();

// ── lo que comparten ────────────────────────────────────────────────────────

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", ...headers });
  res.end(body === undefined || status === 204 ? "" : JSON.stringify(body));
}
async function json(req) {
  let out = "";
  for await (const chunk of req) out += chunk;
  return out ? JSON.parse(out) : {};
}
const revisionOf = (req) => Number(String(req.headers["if-match"] ?? "").replace(/^W\//, "").replaceAll('"', ""));

/** El modo de una parte: `fail` responde 500, `slow` tarda, `empty` lo dice quien llama. */
async function gate(res, part) {
  const mode = state.mode[part];
  if (mode === "slow") await sleep(4000);
  if (mode === "fail") {
    send(res, 500, { detail: "simulated failure" });
    return null;
  }
  return mode;
}

// ── la consola lite ─────────────────────────────────────────────────────────

const LITE_ME = () => ({
  user: { email: CLIENT.email, name: "Marta" },
  client: { name: "Barbería Cultor", modules: CLIENT.modules },
  balance_contact: { kind: "partner", name: "Ladrian Studio" },
  agents: [
    { id: RECEPCION, name: "Recepción" },
    { id: VENTAS, name: "Ventas mayoristas" },
  ],
  channels: [{ kind: "whatsapp", connected: true }],
  nav: CLIENT.modules,
  business: { timezone: "Europe/Madrid", hours: null, hours_label: null },
  reservas: null,
});

const who = (kind) => ({ kind, name: kind === "contact" ? "Ana López" : kind === "agent" ? "Recepción" : "Marta", is_me: kind === "member" });

const conversation = () => ({
  id: CONV,
  contact: { name: "Ana López", handle: "+34 600 11 22 33", initials: "AL" },
  channel: { kind: "whatsapp" },
  agent: { id: RECEPCION, name: "Recepción" },
  state: "agent",
  waiting: null,
  assignee: null,
  last_message: { at: NOW, author: who("agent"), preview: "No tenemos aparcamiento, lo siento.", has_media: false },
  unread: false,
  tags: [],
  handled_by_agent: { id: RECEPCION, name: "Recepción" },
  waiting_reason: null,
});

const detail = () => ({
  id: CONV,
  state: "agent",
  assignee: null,
  agent: { id: RECEPCION, name: "Recepción" },
  handled_by_agent: { id: RECEPCION, name: "Recepción" },
  control_version: 1,
  window: { open: true, closes_at: "2026-10-28T09:00:00Z" },
  channel: { kind: "whatsapp", connected: true },
  contact: { name: "Ana López", handle: "+34 600 11 22 33", first_message_at: "2026-10-27T09:58:00Z", conversations: 1 },
  summary: null,
  waiting_reason: null,
  waiting_since: null,
  tags: [],
  note: { body: "", updated_at: null },
  activity: [],
});

const message = (id, kind, text, at) => ({
  type: "message",
  id,
  at,
  direction: kind === "contact" ? "inbound" : "outbound",
  author: who(kind),
  text,
  media: null,
  delivery: kind === "contact" ? null : "read",
  failure_reason: null,
  kind: null,
  detail: null,
});

const PHONE = /\+?\d[\d ]{7,}\d/g;
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.]+/g;
const NAMES = /\b(Ana|Ana López)\b/g;

function pii(c) {
  const out = [];
  for (const field of ["lesson", "paraphrase"]) {
    const text = c[field] ?? "";
    for (const [re, kind] of [
      [PHONE, "phone"],
      [EMAIL, "email"],
      [NAMES, "name"],
    ]) {
      for (const m of text.matchAll(re)) out.push({ field, kind, start: m.index, end: m.index + m[0].length });
    }
  }
  return out;
}

const classify = (text) => (/^(no |nunca|siempre)/i.test(text.trim()) ? "behavior" : "data");

function correctionOut(c) {
  return { ...c, pii: pii(c), agent: { id: RECEPCION, name: "Recepción" } };
}

function historyEntry(section, before) {
  for (const h of state.history) if (h.section === section) h.undoable = false;
  const entry = { id: randomUUID(), section, kind: "update", at: new Date().toISOString(), by: { kind: "client_user", name: "Marta" }, origin: "lite_web", undone_at: null, undoable: true, before };
  state.history.unshift(entry);
  return entry;
}

const historyOut = () =>
  state.history.map((h) => {
    const out = { ...h };
    delete out.before;
    return out;
  });

function hoursLabel(days) {
  const names = { mon: "lunes", tue: "martes", wed: "miércoles", thu: "jueves", fri: "viernes", sat: "sábado", sun: "domingo" };
  const parts = Object.entries(days)
    .filter(([, shifts]) => shifts.length)
    .map(([d, shifts]) => `${names[d]} ${shifts.map((s) => `de ${s.open} a ${s.close}`).join(" y ")}`);
  if (!parts.length) return null;
  const text = parts.join(" · ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Escribir una sección: `If-Match`, la clave de idempotencia y el historial. */
function write(req, res, section, mutate, status = 200) {
  const sec = state.business[section];
  const match = revisionOf(req);
  if (!req.headers["if-match"]) return send(res, 428, { detail: { code: "revision_required" } });
  if (match !== sec.revision) return send(res, 412, { detail: { code: "revision_conflict", current: sec, changes: [section] } });
  state.keys.push({ section, key: req.headers["idempotency-key"] ?? null });
  const before = structuredClone(sec);
  mutate(sec);
  sec.revision += 1;
  historyEntry(section, before);
  return send(res, status, sec, { etag: `"${sec.revision}"` });
}

async function lite(req, res, path) {
  const route = `${req.method} ${path}`;
  if (route === "GET /console/lite/me") return send(res, 200, LITE_ME());
  if (route === "GET /console/lite/notifications/unread-count") return send(res, 200, { unread: 0 });
  if (route === "GET /console/lite/notifications") return send(res, 200, { items: [], next_cursor: null, unread: 0 });
  if (route === "GET /console/lite/inbox/counts") return send(res, 200, { unread: 0, waiting: 0 });
  if (route === "GET /console/lite/inbox/stream") {
    if (state.mode.stream !== "ok") return send(res, 503, { detail: "stream down" });
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-store", connection: "keep-alive" });
    res.write("event: ready\ndata: {}\n\n");
    const ping = setInterval(() => res.write(": ping\n\n"), 15_000);
    req.on("close", () => clearInterval(ping));
    return;
  }
  if (route === "GET /console/lite/inbox/conversations")
    return send(res, 200, { items: [conversation()], next_cursor: null, counts: { unread: 0, waiting: 0 }, has_any: true, channel_kinds: ["whatsapp"] });
  if (route === `GET /console/lite/inbox/conversations/${CONV}`) return send(res, 200, detail());
  if (route === `GET /console/lite/inbox/conversations/${CONV}/messages`)
    return send(res, 200, {
      items: [
        message(MSG_IN, "contact", "Hola, ¿tenéis aparcamiento cerca?", "2026-10-27T09:58:00Z"),
        message(MSG_AGENT, "agent", "No tenemos aparcamiento, lo siento.", "2026-10-27T09:58:30Z"),
      ],
      next_before: null,
    });
  if (route === `POST /console/lite/inbox/conversations/${CONV}/read`) return send(res, 204);
  if (route === "GET /console/lite/inbox/replies") return send(res, 200, []);
  if (route === "GET /console/lite/inbox/tags") return send(res, 200, { tags: [] });

  // ── «Corregir esta respuesta» ──
  const cc = path.match(/^\/console\/lite\/inbox\/([0-9a-f-]{36})\/messages\/([0-9a-f-]{36})\/corrections$/);
  if (cc && req.method === "POST") {
    if (cc[2] !== MSG_AGENT) return send(res, 422, { detail: { code: "not_an_agent_reply" } });
    const body = await json(req);
    const key = req.headers["idempotency-key"];
    const existing = Object.values(state.corrections).find((c) => c.key && c.key === key);
    if (existing) return send(res, 200, correctionOut(existing));
    const kind = classify(body.text);
    const c = {
      id: randomUUID(),
      key,
      revision: 1,
      status: "draft",
      kind,
      scope: body.scope,
      lesson: body.text,
      paraphrase: "¿Hay aparcamiento cerca del local?",
      applied_change_id: null,
      proposal_id: null,
      created_at: new Date().toISOString(),
      sent_at: null,
      undone_at: null,
    };
    state.corrections[c.id] = c;
    return send(res, 201, correctionOut(c));
  }
  const cm = path.match(/^\/console\/lite\/corrections\/([0-9a-f-]{36})(\/send|\/undo)?$/);
  if (cm) {
    const c = state.corrections[cm[1]];
    if (!c) return send(res, 404, { detail: { code: "unknown_correction" } });
    const sub = cm[2] ?? "";
    if (req.method === "PATCH" && sub === "") {
      if (revisionOf(req) !== c.revision) return send(res, 412, { detail: { code: "revision_conflict", current: correctionOut(c) } });
      const body = await json(req);
      if (body.lesson !== undefined) {
        c.lesson = body.lesson;
        c.kind = classify(body.lesson);
      }
      if (body.paraphrase !== undefined) c.paraphrase = body.paraphrase || null;
      c.revision += 1;
      return send(res, 200, correctionOut(c));
    }
    if (req.method === "POST" && sub === "/send") {
      if (revisionOf(req) !== c.revision) return send(res, 412, { detail: { code: "revision_conflict", current: correctionOut(c) } });
      const found = pii(c);
      if (found.length) return send(res, 422, { detail: { code: "pii_present", pii: found } });
      if (c.kind === "data" && c.scope === "business" && !c.paraphrase) return send(res, 422, { detail: { code: "paraphrase_required" } });
      c.status = c.kind === "data" ? "applied" : "proposed";
      c.sent_at = new Date().toISOString();
      c.revision += 1;
      if (c.kind === "data") c.applied_change_id = historyEntry("faqs", null).id;
      return send(res, 200, correctionOut(c));
    }
    if (req.method === "POST" && sub === "/undo") {
      if (c.status !== "applied") return send(res, 409, { detail: { code: "not_applied" } });
      c.status = "undone";
      c.undone_at = new Date().toISOString();
      return send(res, 200, correctionOut(c));
    }
  }

  // ── Agentes ──
  if (route === "GET /console/lite/agents") {
    const mode = await gate(res, "agents");
    if (mode === null) return;
    return send(res, 200, { items: mode === "empty" ? [] : state.agents });
  }
  const am = path.match(/^\/console\/lite\/agents\/([0-9a-f-]{36})\/(pause|resume)$/);
  if (am && req.method === "POST") {
    const a = state.agents.find((x) => x.id === am[1]);
    if (!a) return send(res, 404, { detail: "Unknown agent" });
    if (am[2] === "pause") {
      const body = await json(req);
      if (!a.allowed.includes("pause")) return send(res, 409, { detail: { code: "not_allowed" } });
      if (a.open_conversations && !body.confirm) return send(res, 409, { detail: { code: "confirm_required", open_conversations: a.open_conversations } });
      Object.assign(a, { visible_state: { code: "paused", tone: "warn", reason: "manual" }, pause_reason: "manual", paused_by_kind: "client_user", paused_origin: "lite_web", allowed: ["resume"] });
      state.pauses.push({ agent: a.id, confirm: Boolean(body.confirm) });
      return send(res, 200, a);
    }
    if (a.pause_reason !== "manual") return send(res, 409, { detail: { code: "system_pause", pause_reason: a.pause_reason } });
    Object.assign(a, { visible_state: { code: "serving", tone: "positive", reason: null }, pause_reason: null, paused_by_kind: null, paused_origin: null, allowed: ["pause"] });
    return send(res, 200, a);
  }
  const chm = path.match(/^\/console\/lite\/channels\/([0-9a-f-]{36})\/(pause|resume)$/);
  if (chm && req.method === "POST") {
    const ch = state.agents.flatMap((a) => a.channels).find((c) => c.id === chm[1]);
    if (!ch) return send(res, 404, { detail: "Unknown channel" });
    if (chm[2] === "pause") Object.assign(ch, { before: ch.visible_state, visible_state: { code: "paused", tone: "warn", reason: null }, allowed: ["resume"] });
    else Object.assign(ch, { visible_state: ch.before ?? { code: "everyone", tone: "positive", reason: null }, allowed: ["pause"] });
    const out = { ...ch };
    delete out.before;
    return send(res, 200, out);
  }

  // ── Negocio ──
  if (route === "GET /console/lite/business") {
    const mode = await gate(res, "business");
    if (mode === null) return;
    const b = state.business;
    if (mode === "empty") {
      return send(res, 200, {
        hours: { ...b.hours, state: "pending", layout: null, days: empty(), label: null },
        special_dates: { ...b.special_dates, items: [] },
        services: { ...b.services, state: "pending", items: [] },
        locations: { ...b.locations, items: [] },
        provenance: {},
        history: [],
      });
    }
    return send(res, 200, { ...b, provenance: {}, history: historyOut() });
  }
  if (route === "PUT /console/lite/business/hours") {
    const body = await json(req);
    return write(req, res, "hours", (h) => {
      h.layout = body.layout;
      h.days = { ...empty(), ...Object.fromEntries(Object.entries(body.days).map(([d, s]) => [d, s.map((x) => shift(x.open, x.close))])) };
      h.label = hoursLabel(h.days);
    });
  }
  if (route === "POST /console/lite/business/special-dates") {
    const body = await json(req);
    return write(
      req,
      res,
      "special_dates",
      (s) => {
        const id = randomUUID();
        s.items.push({ id, name: body.name ?? "", location_id: body.location_id ?? null, from: body.from, to: body.to, closed: body.closed, shifts: (body.shifts ?? []).map((x) => shift(x.open, x.close)), archived: false });
        s.created_id = id;
      },
      201,
    );
  }
  const sm = path.match(/^\/console\/lite\/business\/services\/([0-9a-f-]{36})(\/archive)?$/);
  if (sm) {
    const body = req.method === "PATCH" ? await json(req) : {};
    if (req.method === "PATCH" && "name" in body) return send(res, 422, { detail: [{ loc: ["body", "name"], msg: "Extra inputs are not permitted" }] });
    return write(req, res, "services", (s) => {
      const item = s.items.find((x) => x.id === sm[1]);
      if (!item) return;
      if (sm[2]) item.archived = true;
      else Object.assign(item, body);
    });
  }
  const um = path.match(/^\/console\/lite\/business\/history\/([0-9a-f-]{36})\/undo$/);
  if (um && req.method === "POST") {
    const h = state.history.find((x) => x.id === um[1]);
    if (!h) return send(res, 404, { detail: { code: "unknown_change" } });
    if (h.undone_at) return send(res, 409, { detail: { code: "already_undone" } });
    if (!h.before) return send(res, 409, { detail: { code: "undo_not_available" } });
    const current = state.business[h.section];
    state.business[h.section] = { ...h.before, revision: current.revision + 1 };
    h.undone_at = new Date().toISOString();
    h.undoable = false;
    state.keys.push({ section: "undo", key: req.headers["idempotency-key"] ?? null });
    return send(res, 200, { section: h.section, revision: state.business[h.section].revision, change_id: randomUUID() });
  }
  return send(res, 404, { detail: "Not Found" });
}

// ── la consola del partner ──────────────────────────────────────────────────

const clientRecord = () => ({
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

const PARTNER_AGENTS = [
  { id: RECEPCION, name: "Recepción", is_default: true, visible: { code: "serving", tone: "positive", reason: null } },
  { id: VENTAS, name: "Ventas mayoristas", is_default: false, visible: { code: "serving", tone: "positive", reason: null } },
  { id: CITAS, name: "Citas", is_default: false, visible: { code: "paused", tone: "warn", reason: "manual" } },
];

const card = (a) => ({
  id: a.id,
  name: a.name,
  status: "active",
  is_principal: a.is_default,
  channels: a.id === RECEPCION ? [{ id: CH1, display: "+34 611 20 48 93" }] : [],
  active_version: 2,
  draft_version: null,
  lifecycle: a.visible.code === "paused" ? "paused" : "published",
  pause_reason: a.visible.reason,
  is_default: a.is_default,
  visible_state: a.visible,
  opens: "overview",
});

const header = (a) => ({
  id: a.id,
  name: a.name,
  lifecycle: "published",
  pause_reason: null,
  visible_state: a.visible,
  is_default: a.is_default,
  open_conversations: 0,
  paused_by_kind: null,
  paused_origin: null,
  allowed: ["rename", "pause", "archive"],
});

const SPEC = (name) => ({
  schema_version: "1",
  mode: "structured",
  identity: { name, description: "Atiende a los clientes de la barbería por WhatsApp y los pasa a quien corresponde." },
  voice: { tone: "Cercano", languages: ["es"], register: "tu" },
  instructions: { sections: [{ title: "Qué haces", body: "Recibes a los clientes y los pasas al agente que corresponde." }] },
  procedures: [],
  services: { mode: "all" },
  skills: [],
  tools: [],
  escalation: { triggers: ["asks_for_human"], failed_attempts: 2 },
  rules: ["No ofrezcas descuentos"],
  ai_disclosure: { decided: true, mode: "first_message" },
  model_policy: { kind: "profile", profile: "auto" },
  memory: { scope: "shared" },
  ...(state.reception ? { reception: state.reception } : {}),
});

const draft = (a) => ({
  agent_id: a.id,
  agent_name: a.name,
  revision: state.draftRevision,
  exists: state.draftRevision > 4,
  number: state.draftRevision > 4 ? 3 : null,
  version: null,
  status: null,
  base_number: 2,
  active_number: 2,
  active_version: 2,
  author: PARTNER.email,
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
});

const SUITE = () => ({
  summary: { passed: 1, flaky: 0, failed: 0, unknown: 0, not_run: 0, not_applicable: 0, total: 1, stale: 0, critical_failed: [], rate: 100 },
  tests: [
    { id: "00000000-0000-4000-8000-0000000000f9", kind: "case", name: "Pregunta el horario", persona: "", first_message: "¿Abrís el domingo?", plan: "", expected_state: {}, criteria: [], critical: false, not_applicable_reason: null, sector_test_ref: null, stale: false, status: "passed", passes: 3, decided: 3, why_failed: null },
  ],
  judge_calibrated: true,
  allowed: ["add", "edit", "run"],
});

const usd = (amount_micros) => ({ amount_micros, currency: "USD" });

function performance(days) {
  const until = Date.UTC(2026, 9, 28);
  const series = Array.from({ length: days }, (_, i) => {
    const day = new Date(until - (days - 1 - i) * 86_400_000).toISOString().slice(0, 10);
    const resolved = (i * 7) % 5;
    const handed = i % 4 === 0 ? 1 : 0;
    return { day, conversations: resolved + handed, resolved_without_person: resolved, handed_to_person: handed, spent: usd((resolved + handed) * 95_000) };
  });
  const sum = (k) => series.reduce((n, d) => n + d[k], 0);
  const conversations = sum("conversations");
  const spent = series.reduce((n, d) => n + d.spent.amount_micros, 0);
  return {
    days,
    since: new Date(until - (days - 1) * 86_400_000).toISOString(),
    until: new Date(until + 86_400_000).toISOString(),
    conversations,
    resolved_without_person: sum("resolved_without_person"),
    handed_to_person: sum("handed_to_person"),
    resolved_pct: conversations ? (sum("resolved_without_person") / conversations) * 100 : null,
    spent: usd(spent),
    spend_per_conversation: conversations ? usd(Math.round(spent / conversations)) : null,
    series,
  };
}

function conversations(cursor) {
  const make = (i, over = {}) => ({
    id: `00000000-0000-4000-8000-0000000c${String(1000 + i).padStart(4, "0")}`,
    started_at: new Date(Date.UTC(2026, 9, 27, 9, 0) - i * 3_600_000).toISOString(),
    last_activity_at: new Date(Date.UTC(2026, 9, 27, 9, 12) - i * 3_600_000).toISOString(),
    channel_type: "whatsapp",
    duration_seconds: 300 + i * 60,
    messages_count: 4 + i,
    outcome: i % 3 === 0 ? "handed_to_person" : "resolved_without_person",
    in_progress: i === 1,
    handoff_reason: i % 3 === 0 ? (i === 0 ? "reception_loop" : "escalated") : null,
    spent: usd(90_000 + i * 5_000),
    ...over,
  });
  if (cursor) return { items: [make(10), make(11)], next_cursor: null };
  return { items: Array.from({ length: 6 }, (_, i) => make(i)), next_cursor: "page-2" };
}

async function partner(req, res, path) {
  const route = `${req.method} ${path}`;
  const clientBase = `/console/clients/${REF}`;
  if (route === "GET /console/me")
    return send(res, 200, {
      user_id: PARTNER.user_id,
      partner_id: PARTNER.partner_id,
      partner_slug: PARTNER.partner_slug,
      partner_name: PARTNER.partner_name,
      role: PARTNER.role,
      modules: PARTNER_MODULES,
      companion_enabled: false,
      console_version: "v2",
    });
  if (route === "GET /console/notifications/unread-count") return send(res, 200, { unread: 0 });
  if (route === "GET /console/notifications") return send(res, 200, { items: [], next_cursor: null, unread: 0 });
  if (route === "GET /console/search") return send(res, 200, { clients: [], agents: [], screens: [], actions: [] });
  if (route === "GET /console/team")
    return send(res, 200, {
      members: [
        { id: "m1", email: PARTNER.email, display_name: "Luis Matos", role: "owner", status: "active", accepted_at: NOW, created_at: NOW, is_you: true },
        { id: "m2", email: "dani@ladrian.studio", display_name: "Dani", role: "builder", status: "active", accepted_at: NOW, created_at: NOW, is_you: false },
      ],
      invitations: [],
    });
  if (route === `GET ${clientBase}`) return send(res, 200, clientRecord());
  if (route === `GET ${clientBase}/agents`) return send(res, 200, PARTNER_AGENTS.map(card));

  const am = path.match(new RegExp(`^${clientBase}/agents/([0-9a-f-]{36})(/.*)?$`));
  if (!am) return send(res, 404, { detail: "Not Found" });
  const a = PARTNER_AGENTS.find((x) => x.id === am[1]);
  if (!a) return send(res, 404, { detail: "Unknown agent" });
  const sub = am[2] ?? "";
  if (req.method === "GET" && sub === "") return send(res, 200, header(a));
  if (req.method === "GET" && sub === "/draft") return send(res, 200, draft(a), { etag: `"${state.draftRevision}"` });
  if (req.method === "PATCH" && sub === "/draft") {
    if (revisionOf(req) !== state.draftRevision) return send(res, 412, { detail: { code: "revision_conflict", current: draft(a), changes: ["system_prompt"] } });
    const body = await json(req);
    const reception = body.spec?.reception ?? null;
    for (const [i, target] of (reception?.targets ?? []).entries()) {
      if (!PARTNER_AGENTS.some((x) => x.id === target.agent_id)) {
        return send(res, 422, { detail: { code: "spec_invalid", problems: [{ pointer: `/reception/targets/${i}/agent_id`, code: "foreign_reference", message: "Ese agente no es de este cliente." }] } });
      }
    }
    state.reception = reception;
    state.specSaves.push({ revision: state.draftRevision, reception });
    state.draftRevision += 1;
    return send(res, 200, draft(a), { etag: `"${state.draftRevision}"` });
  }
  if (req.method === "GET" && sub === "/proposals") return send(res, 200, []);
  if (req.method === "GET" && sub === "/tests") return send(res, 200, SUITE());
  if (req.method === "GET" && sub === "/review") return send(res, 200, { version_number: 2, findings: [], checks: [{ check: "hours", ok: true, findings: 0 }], blocking: 0 });
  if (req.method === "GET" && sub === "/publish-preview") return send(res, 200, { action: "save_changes", has_draft: false, has_channels: true, diff: [], gate: null, can_override: true });
  if (req.method === "GET" && sub === "/history") return send(res, 200, []);
  if (req.method === "GET" && sub === "/playground/sessions") return send(res, 200, []);
  if (req.method === "GET" && sub === "/knowledge") return send(res, 200, { items: [], business_sources: 0 });
  if (req.method === "GET" && sub === "/channels") return send(res, 200, { channels: [], pending_link: null });

  if (req.method === "GET" && sub === "/performance") {
    const mode = await gate(res, "performance");
    if (mode === null) return;
    const days = Number(new URL(req.url, "http://x").searchParams.get("days") ?? 30);
    const perf = performance(days);
    if (mode === "empty") return send(res, 200, { ...perf, conversations: 0, resolved_without_person: 0, handed_to_person: 0, resolved_pct: null, spent: usd(0), spend_per_conversation: null, series: perf.series.map((d) => ({ ...d, conversations: 0, resolved_without_person: 0, handed_to_person: 0, spent: usd(0) })) });
    return send(res, 200, perf);
  }
  if (req.method === "GET" && sub === "/conversations") {
    const mode = await gate(res, "conversations");
    if (mode === null) return;
    if (mode === "empty") return send(res, 200, { items: [], next_cursor: null });
    return send(res, 200, conversations(new URL(req.url, "http://x").searchParams.get("cursor")));
  }
  if (req.method === "GET" && sub === "/improvements") {
    const mode = await gate(res, "improvements");
    if (mode === null) return;
    return send(res, 200, { items: mode === "empty" ? [] : state.improvements, allowed: ["accept", "discard"] });
  }
  const im = sub.match(/^\/improvements\/([0-9a-f-]{36})\/(accept|discard)$/);
  if (im && req.method === "POST") {
    const item = state.improvements.find((x) => x.id === im[1]);
    if (!item) return send(res, 409, { detail: { code: "improvement_closed" } });
    if (im[2] === "discard") {
      const body = await json(req);
      if (!body.reason || body.reason.trim().length < 3) return send(res, 422, { detail: [{ loc: ["body", "reason"], msg: "too short" }] });
      state.improvements = state.improvements.filter((x) => x.id !== item.id);
      state.decisions.push({ id: item.id, decision: "discard", reason: body.reason });
      return send(res, 200, { id: item.id, status: "discarded", suppress_until: item.kind === "suggestion" ? "2026-11-27T10:00:00Z" : null });
    }
    state.improvements = state.improvements.filter((x) => x.id !== item.id);
    state.draftRevision += 1;
    state.decisions.push({ id: item.id, decision: "accept" });
    return send(res, 200, { id: item.id, status: "accepted", draft_revision: state.draftRevision, test_id: randomUUID() });
  }
  return send(res, 404, { detail: "Not Found" });
}

// ── el servidor ─────────────────────────────────────────────────────────────

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  const route = `${req.method} ${path}`;
  process.stderr.write(`[fabrica-mock] ${route}\n`);
  try {
    if (route === "GET /health") return send(res, 200, { status: "ok" });
    if (route === "POST /__test/reset") {
      state = fresh();
      return send(res, 200, { ok: true });
    }
    if (route === "POST /__test/mode") {
      Object.assign(state.mode, await json(req));
      return send(res, 200, state.mode);
    }
    if (route === "GET /__test/state")
      return send(res, 200, { pauses: state.pauses, keys: state.keys, corrections: Object.values(state.corrections), reception: state.reception, specSaves: state.specSaves, decisions: state.decisions, business: state.business });
    if (route === "POST /console/auth/session") {
      const body = await json(req);
      return send(res, 200, { principal: body.token === "e2e-lite" ? CLIENT : PARTNER });
    }
    if (path.startsWith("/console/lite/")) return await lite(req, res, path);
    if (path.startsWith("/console/")) return await partner(req, res, path);
    return send(res, 404, { detail: "Not Found" });
  } catch (err) {
    process.stderr.write(`[fabrica-mock] ${route} failed: ${err?.stack ?? err}\n`);
    if (!res.headersSent) send(res, 500, { detail: "mock error" });
  }
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[fabrica-mock] listening on ${PORT}\n`));
