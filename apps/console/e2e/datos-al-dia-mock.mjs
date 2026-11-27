/**
 * La API simulada de la spec 082 (datos al día), solo para `datos-al-dia.config.ts`.
 *
 * Una persona del cliente «Spa Jemma» con Bandeja y Reservas (modo Servicios).
 * Lo que la consola escribe cambia el estado al momento, como una base ya
 * confirmada: si la pantalla no lo pinta, el fallo es de la consola.
 *
 * - `POST /__test/reset` vuelve al principio.
 * - `POST /__test/booking` `{name, start}` crea una reserva «del agente» por
 *   detrás, sin que la consola lo pida.
 * - `POST /__test/emit` `{event, data}` manda un evento por las líneas SSE abiertas.
 * - `POST /__test/drop` corta las líneas SSE abiertas (la consola reconecta).
 * - `POST /__test/inbound` `{text}` deja un mensaje entrante y sube los no leídos.
 * - `GET /__test/state` enseña lo que llegó (lecturas por ruta).
 *
 * No verifica tokens: no es la puerta, es el otro lado del cable.
 */
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8722);
const TZ = "America/Caracas";
const LUCIA = "00000000-0000-4000-8000-0000000000a1";
const CORTE = "00000000-0000-4000-8000-0000000000b1";
const CONV = "00000000-0000-4000-8000-000000000c01";
// Spec 082 (T041): un contacto solo con número, sin letras para las iniciales.
const NAMELESS = "00000000-0000-4000-8000-000000000c02";
const AGENT = "00000000-0000-4000-8000-0000000000a9";

const base = {
  user_id: "00000000-0000-4000-8000-0000000000e5",
  locale: "es",
  access: "ok",
  membership_id: "00000000-0000-4000-8000-0000000000e3",
  partner_id: "00000000-0000-4000-8000-0000000000e4",
  partner_slug: "autprod",
  partner_name: "Autprod",
  partner_status: "active",
  permissions: [],
  console_enabled: true,
};
const MODULES = ["panel", "inbox", "reservas"];
const CLIENT = {
  ...base,
  email: "jemma@spa.example",
  display_name: "Jemma",
  role: "client",
  kind: "client",
  client_name: "Spa Jemma",
  modules: MODULES,
};

/** Today in the business's zone, as the console computes it. */
function today() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

const pad = (n) => String(n).padStart(2, "0");
const plus = (hm, minutes) => {
  const [h, m] = hm.split(":").map(Number);
  const t = h * 60 + m + minutes;
  return `${pad(Math.floor(t / 60) % 24)}:${pad(t % 60)}`;
};

function booking(name, start, over = {}) {
  const date = today();
  const end = plus(start, 45);
  return {
    id: randomUUID(),
    mode: "services",
    status: "confirmed",
    // Caracas is UTC-4 all year.
    starts_at: new Date(`${date}T${start}:00-04:00`).toISOString(),
    ends_at: new Date(`${date}T${end}:00-04:00`).toISOString(),
    local: { date, start, end },
    party_size: 1,
    staff: { id: LUCIA, name: "Lucía" },
    service: { id: CORTE, name: "Manicura", duration_minutes: 45 },
    price: { amount_minor: 3000, currency: "USD" },
    contact: { name, phone: "+584121112222", conversation_id: null },
    origin: "agent",
    channel: "whatsapp",
    created_by: { kind: "agent", name: "Agente" },
    created_at: new Date().toISOString(),
    note: null,
    arrived_at: null,
    cancelled: null,
    wants_earlier: false,
    any_staff: false,
    late_minutes: null,
    clash: null,
    allowed: ["confirm", "move", "cancel"],
    version: 1,
    ...over,
  };
}

const day = [
  { from: "08:00", to: "13:00" },
  { from: "14:00", to: "22:00" },
];
const week = { monday: day, tuesday: day, wednesday: day, thursday: day, friday: day, saturday: day, sunday: day };
const shift = (open, close) => ({ open, close, overnight: false });
const fichaDay = [shift("08:00", "13:00"), shift("14:00", "22:00")];

function settings() {
  return {
    mode: "services",
    capacity_kind: null,
    timezone: TZ,
    currency: "USD",
    business_hours: week,
    business_hours_label: "Todos los días de 8:00 a 22:00",
    hours: {
      revision: 1,
      state: "complete",
      allowed: ["edit"],
      location_id: null,
      inherits: false,
      layout: "blocks",
      days: { mon: fichaDay, tue: fichaDay, wed: fichaDay, thu: fichaDay, fri: fichaDay, sat: fichaDay, sun: fichaDay },
      label: "Todos los días de 8:00 a 22:00.",
    },
    location_hours: [],
    hours_missing: false,
    slot_step_minutes: 30,
    waitlist: { enabled: false, lead_minutes: 120 },
    agent: { min_notice_minutes: 60, max_days_ahead: 60 },
    confirmation: { enabled: false, when: "24h" },
    reminder_enabled: false,
    release_unconfirmed: false,
    capacity: null,
    version: 1,
  };
}

function fresh() {
  return {
    bookings: [booking("Ana Pérez", "10:00"), booking("Rosa Díaz", "12:00")],
    reads: {},
    // `POST /__test/slow-read`: the next bookings read takes what is there NOW and answers late.
    slowNext: 0,
    unread: 0,
    inbound: [],
  };
}
let state = fresh();
const streams = new Set();

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", ...headers });
  res.end(body === undefined || status === 204 ? "" : JSON.stringify(body));
}
async function json(req) {
  let out = "";
  for await (const chunk of req) out += chunk;
  return out ? JSON.parse(out) : {};
}
const ifMatch = (req) => Number(String(req.headers["if-match"] ?? "").replace(/^W\//, "").replaceAll('"', ""));
const count = (route) => (state.reads[route] = (state.reads[route] ?? 0) + 1);

function emit(event, data) {
  for (const res of streams) res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

const detailOf = (b) => ({ ...b, events: [{ kind: "created", at: b.created_at, actor: { kind: "agent", name: "Agente" }, data: {} }] });

function conversation(id = CONV) {
  const last = state.inbound.at(-1);
  const nameless = id === NAMELESS;
  return {
    id,
    contact: nameless
      ? { name: "+58 412 999 0000", handle: "+58 412 999 0000", initials: "·" }
      : { name: "Ana Pérez", handle: "+58 412 111 2222", initials: "AP" },
    channel: { kind: "whatsapp" },
    agent: { id: AGENT, name: "Agente" },
    state: "agent",
    waiting: null,
    assignee: null,
    last_message: { at: last?.at ?? "2026-11-26T12:00:00Z", author: { kind: "contact", name: "Ana Pérez", is_me: false }, preview: last?.text ?? "Hola", has_media: false },
    unread: state.unread > 0,
    tags: [],
  };
}

/** The open conversation (spec 082, 5.4): Ana has a WhatsApp username, the number has none. */
function detail(id) {
  const nameless = id === NAMELESS;
  return {
    id,
    state: "agent",
    assignee: null,
    agent: { id: AGENT, name: "Agente" },
    control_version: 1,
    window: { open: true, closes_at: "2026-11-27T12:00:00Z" },
    channel: { kind: "whatsapp", connected: true },
    contact: nameless
      ? { name: "+58 412 999 0000", handle: "+58 412 999 0000", first_message_at: "2026-11-20T10:00:00Z", conversations: 1, username: null }
      : { name: "Ana Pérez", handle: "+58 412 111 2222", first_message_at: "2026-11-20T10:00:00Z", conversations: 2, username: "ana.perez" },
    summary: null,
    waiting_reason: null,
    waiting_since: null,
    tags: [],
    note: { body: "", updated_at: null },
    activity: [],
  };
}

function thread() {
  return {
    items: [
      {
        type: "message",
        id: "00000000-0000-4000-8000-0000000000f1",
        at: "2026-11-26T12:00:00Z",
        direction: "inbound",
        author: { kind: "contact", name: null, is_me: false },
        text: "Hola, ¿tenéis hueco mañana?",
        media: null,
        delivery: null,
        failure_reason: null,
        kind: null,
        detail: null,
      },
    ],
    next_before: null,
  };
}

async function reservas(req, res, path, url) {
  const R = "/console/lite/reservas";
  const route = `${req.method} ${path}`;
  if (route === `GET ${R}/settings`) return send(res, 200, settings());
  if (route === `GET ${R}/staff`)
    return send(res, 200, {
      items: [{ id: LUCIA, name: "Lucía", email: null, hours: null, effective_hours: week, position: 1, archived: false, calendar: { status: "none" } }],
    });
  if (route === `GET ${R}/services`)
    return send(res, 200, {
      items: [{ id: CORTE, name: "Manicura", duration_minutes: 45, price: { kind: "amount", amount_minor: 3000 }, currency: "USD", staff: "all", staff_ids: [], position: 1, archived: false }],
    });
  if (route === `GET ${R}/bookings`) {
    count(route);
    const from = url.searchParams.get("from") ?? "0000-00-00";
    const to = url.searchParams.get("to") ?? "9999-99-99";
    // A copy now: what a read sees is what the base had when it started.
    const items = structuredClone(state.bookings.filter((b) => b.local.date >= from && b.local.date <= to));
    if (state.slowNext > 0) {
      const ms = state.slowNext;
      state.slowNext = 0;
      await new Promise((r) => setTimeout(r, ms));
    }
    return send(res, 200, { items, closed_days: [], truncated: false });
  }
  if (route === `GET ${R}/waitlist`) return send(res, 200, { enabled: false, items: [] });
  if (route === `GET ${R}/offers`) return send(res, 200, { items: [] });
  if (route === `GET ${R}/templates`) return send(res, 200, { whatsapp: false, approved: 0, items: [] });

  const one = path.match(/^\/console\/lite\/reservas\/bookings\/([0-9a-f-]{36})(?:\/(.+))?$/);
  if (one) {
    const b = state.bookings.find((x) => x.id === one[1]);
    if (!b) return send(res, 404, { detail: { code: "not_found" } });
    const tail = one[2] ?? "";
    if (req.method === "GET" && tail === "") return send(res, 200, detailOf(b));
    if (req.method === "GET" && tail === "cancel-preview") return send(res, 200, { can_offer: false, candidates: 0, why_not: "waitlist_off" });
    if (req.method === "POST" && tail === "cancel") {
      if (ifMatch(req) !== b.version) return send(res, 412, { detail: { code: "stale" } });
      await json(req);
      b.status = "cancelled";
      b.allowed = [];
      b.cancelled = { at: new Date().toISOString(), by: "business", cause: null };
      b.version += 1;
      return send(res, 200, { ...b, offer: null });
    }
    if (req.method === "POST" && tail === "confirm") {
      b.status = "confirmed";
      b.version += 1;
      return send(res, 200, b);
    }
  }
  return send(res, 404, { detail: "Not Found" });
}

async function lite(req, res, path, url) {
  const route = `${req.method} ${path}`;
  if (route === "GET /console/lite/me")
    return send(res, 200, {
      user: { email: CLIENT.email, name: "Jemma" },
      client: { name: "Spa Jemma", modules: MODULES },
      balance_contact: { kind: "partner", name: "Autprod" },
      agents: [{ id: AGENT, name: "Agente" }],
      channels: [{ kind: "whatsapp", connected: true }],
      nav: MODULES,
      business: { timezone: TZ, hours: null, hours_label: null },
      reservas: { mode: "services" },
    });
  if (route === "GET /console/lite/notifications/unread-count") return send(res, 200, { unread: 0 });
  if (route === "GET /console/lite/notifications") return send(res, 200, { items: [], next_cursor: null, unread: 0 });
  if (route === "GET /console/lite/inbox/counts") {
    count(route);
    return send(res, 200, { unread: state.unread, waiting: 0 });
  }
  if (route === "GET /console/lite/inbox/stream") {
    count(route);
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-store", connection: "keep-alive" });
    res.write("event: ready\ndata: {}\n\n");
    streams.add(res);
    const ping = setInterval(() => res.write("event: ping\ndata: {}\n\n"), 15_000);
    req.on("close", () => {
      clearInterval(ping);
      streams.delete(res);
    });
    return;
  }
  if (route === "GET /console/lite/inbox/conversations") {
    count(route);
    return send(res, 200, { items: [conversation(), conversation(NAMELESS)], next_cursor: null, counts: { unread: state.unread, waiting: 0 }, has_any: true, channel_kinds: ["whatsapp"] });
  }
  const one = path.match(/^\/console\/lite\/inbox\/conversations\/([0-9a-f-]{36})(\/messages|\/read)?$/);
  if (one && [CONV, NAMELESS].includes(one[1])) {
    if (req.method === "GET" && !one[2]) return send(res, 200, detail(one[1]));
    if (req.method === "GET" && one[2] === "/messages") return send(res, 200, thread());
    if (req.method === "POST" && one[2] === "/read") return send(res, 204, null);
  }
  if (route === "GET /console/lite/inbox/settings") return send(res, 200, { autoclose_hours: null });
  if (route === "GET /console/lite/inbox/replies") return send(res, 200, []);
  if (route === "GET /console/lite/inbox/tags") return send(res, 200, { tags: [] });
  if (path.startsWith("/console/lite/reservas/")) return reservas(req, res, path, url);
  return send(res, 404, { detail: "Not Found" });
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  const route = `${req.method} ${path}`;
  process.stderr.write(`[datos-mock] ${route}\n`);
  try {
    if (route === "GET /health") return send(res, 200, { status: "ok" });
    if (route === "POST /__test/reset") {
      state = fresh();
      return send(res, 200, { ok: true });
    }
    if (route === "GET /__test/state") return send(res, 200, { reads: state.reads, bookings: state.bookings, unread: state.unread, streams: streams.size });
    if (route === "POST /__test/slow-read") {
      state.slowNext = (await json(req)).ms ?? 4000;
      return send(res, 200, { ok: true });
    }
    if (route === "POST /__test/booking") {
      const body = await json(req);
      const b = booking(body.name ?? "Nueva", body.start ?? "16:00");
      state.bookings.push(b);
      return send(res, 200, b);
    }
    if (route === "POST /__test/emit") {
      const body = await json(req);
      emit(body.event, body.data ?? {});
      return send(res, 200, { sent: streams.size });
    }
    if (route === "POST /__test/drop") {
      const n = streams.size;
      for (const s of streams) s.destroy();
      streams.clear();
      return send(res, 200, { dropped: n });
    }
    if (route === "POST /__test/inbound") {
      const body = await json(req);
      state.unread += 1;
      state.inbound.push({ text: body.text ?? "Hola", at: new Date().toISOString() });
      return send(res, 200, { unread: state.unread });
    }
    if (route === "POST /console/auth/session") {
      await json(req);
      return send(res, 200, { principal: CLIENT });
    }
    if (path.startsWith("/console/lite/")) return await lite(req, res, path, url);
    return send(res, 404, { detail: "Not Found" });
  } catch (err) {
    process.stderr.write(`[datos-mock] ${route} failed: ${err?.stack ?? err}\n`);
    if (!res.headersSent) send(res, 500, { detail: "mock error" });
  }
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[datos-mock] listening on ${PORT}\n`));
